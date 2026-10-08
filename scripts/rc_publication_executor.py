"""Core-driven owned publication session; actual admission remains unavailable."""
from __future__ import annotations

from pathlib import Path
import threading
import time

import rc_publication_contract as core
import rc_publication_github as wire
from rc_consumer_io import ConsumerError
from rc_publication_stage import Selection, stage_selected

OPERATION_SECONDS = 300


class PublisherSession:
    """One process, one retained stage, no replay or caller-supplied authority."""
    def __init__(self, root, selection, token, *, temporary_parent):
        if type(selection) is not Selection:
            raise wire.WireFailure('invalid_request', 'none')
        self._root, self._selection = Path(root), selection
        self._temporary_parent = temporary_parent
        self._api = wire.GitHub(token, selection)
        self._stage = None
        self._transition = None
        self._activation_outcome = None
        self._cancelled = threading.Event()
        self._lock = threading.Lock()
        self._closed = False
        self._cleanup_failed = False
        self._attempted = set()
        self._inflight = None
        self._deadline = None

    @property
    def transition(self):
        return self._transition

    @property
    def outcome(self):
        return self._transition.state.outcome if self._transition else self._activation_outcome

    def __enter__(self):
        if self._closed:
            raise wire.WireFailure('invalid_request', 'none')
        return self

    def __exit__(self, kind, value, traceback):
        try:
            self.close()
        except wire.WireFailure:
            if value is None:
                raise

    def _prepare(self):
        try:
            self._check_active()
            wire._authenticate(self._selection, self._api, check_active=self._check_active, deadline=self._deadline)
            wire._remote_constraint(self._selection.subject)
            self._stage = stage_selected(self._root, self._selection, self._api,
                temporary_parent=self._temporary_parent, deadline=self._deadline, check_active=self._check_active)
            self._stage.__enter__()
            self._check_active()
            self._transition = core.start(self._stage.subject, self._stage.plan)
        except BaseException as error:
            self._activation_outcome = 'blocked_no_effect'
            transport_code = None
            try:
                if isinstance(error, ConsumerError):
                    transport_code = error.code
            except BaseException:
                pass
            if type(transport_code) is not str:
                transport_code = None
            if transport_code == 'transport_cleanup_uncertain':
                self._cleanup_failed = True
            failed = self._dispose()
            code = error.code if isinstance(error, wire.WireFailure) else 'adapter_error'
            if transport_code is not None:
                code = {'transport_deadline_exceeded': 'timeout',
                        'transport_cancelled': 'cancelled'}.get(transport_code, 'adapter_error')
            if failed:
                code = 'adapter_error'
            raise wire.WireFailure(code, 'none') from None

    def _check_active(self):
        if self._closed:
            raise wire.WireFailure('cancelled', 'none')
        self._check_completion()

    def _check_completion(self):
        if self._cancelled.is_set():
            raise wire.WireFailure('cancelled', 'none')
        if self._deadline is not None and time.monotonic() >= self._deadline:
            raise wire.WireFailure('timeout', 'none')

    def _before_write(self):
        self._check_active()
        op = self._inflight
        if (op is None or self._transition.action is not op
                or self._transition.state.pending is not op
                or op.operation_id in self._attempted):
            raise wire.WireFailure('invalid_event', 'none')
        self._attempted.add(op.operation_id)

    def _execute(self, op):
        fields = {}
        if op.kind in ('ObserveFence', 'ObserveDraft', 'VerifyPublished'):
            check_active = self._check_active
            gates, visibility = wire._authenticate(self._selection, self._api, check_active=check_active, deadline=self._deadline)
            try:
                staged = self._stage.revalidate(deadline=self._deadline, check_active=check_active)
            except ConsumerError as error:
                code = error.code
                codes = {'transport_deadline_exceeded': 'timeout', 'transport_cancelled': 'cancelled'}
                if type(code) is str and code in codes:
                    raise wire.WireFailure(codes[code], 'none') from None
                raise
            self._check_active()
            fields['observation'] = self._api.observe(self._transition.state,
                staged=staged, gates=gates, draft_visibility=visibility)
        elif op.kind == 'CreateDraft':
            fields['release_id'] = self._api.create_draft(op,
                before_write=self._before_write, check_active=self._check_active)
        elif op.kind == 'UploadAsset':
            fields['asset'] = self._api.upload_asset(op, self._stage.stream(op.asset_ordinal),
                before_write=self._before_write, check_active=self._check_active)
            fields['release_id'] = op.release_id
        elif op.kind == 'VerifyAsset':
            fields['asset'] = self._api.verify_asset(op)
            fields['release_id'] = op.release_id
        elif op.kind == 'PublishPrerelease':
            fields['release_id'] = self._api.publish_prerelease(op,
                before_write=self._before_write, check_active=self._check_active)
        else:
            raise wire.WireFailure('invalid_event', 'none')
        try:
            self._check_active()
        except wire.WireFailure as error:
            if op.kind in core.MUTATIONS:
                raise wire.WireFailure(error.code, 'confirmed',
                    fields.get('release_id'), fields.get('asset')) from None
            raise
        if op.kind == 'VerifyPublished':
            if self._dispose():
                raise wire.WireFailure('adapter_error', 'none')
            self._check_completion()
        return core.OperationResult(core.RESULT_KINDS[core.OPERATION_KINDS.index(op.kind)],
            op.operation_id, op.subject_digest, op.kind,
            'confirmed' if op.kind in core.MUTATIONS else 'none', **fields)

    def _failure(self, op, error):
        if isinstance(error, wire.WireFailure):
            code, effect = error.code, error.effect
            release_id, asset = error.release_id, error.asset
        else:
            code = 'adapter_error'
            effect = 'unknown' if op.kind in core.MUTATIONS and op.operation_id in self._attempted else 'none'
            release_id = asset = None
        if op.kind not in core.MUTATIONS:
            effect, release_id, asset = 'none', None, None
        elif effect == 'none' and op.operation_id in self._attempted:
            effect = 'unknown'
        if effect != 'confirmed':
            release_id = asset = None
        return core.OperationResult('OperationUncertain' if effect == 'unknown' else 'OperationFailed',
            op.operation_id, op.subject_digest, op.kind, effect,
            release_id=release_id, asset=asset, code=code)

    def _run(self):
        if self._closed:
            raise wire.WireFailure('invalid_request', 'none')
        if self._transition is None:
            self._deadline = time.monotonic() + OPERATION_SECONDS
            self._prepare()
        while isinstance(self._transition.action, core.Operation):
            op = self._transition.action
            self._deadline = time.monotonic() + OPERATION_SECONDS
            self._inflight = op
            try:
                self._check_active()
                if op.operation_id in self._attempted or self._transition.state.pending is not op:
                    raise wire.WireFailure('invalid_event', 'none')
                if op.kind not in core.MUTATIONS:
                    self._attempted.add(op.operation_id)
                result = self._execute(op)
            except BaseException as error:
                result = self._failure(op, error)
            finally:
                self._inflight = None
            self._transition = core.advance(self._transition.state, result)
        self._deadline = None
        if self._transition.action is None:
            self._dispose()
        return self._transition

    def run_until_pause(self):
        if not self._lock.acquire(blocking=False):
            raise wire.WireFailure('invalid_event', 'none')
        try:
            return self._run()
        finally:
            self._lock.release()
            if (self._cancelled.is_set() and self._transition is not None
                    and isinstance(self._transition.action, core.AwaitPublishRequest)):
                self.cancel()

    def request_publish(self, request):
        if not self._lock.acquire(blocking=False):
            raise wire.WireFailure('invalid_event', 'none')
        try:
            if self._closed or self._cancelled.is_set() or self._transition is None:
                raise wire.WireFailure('invalid_request', 'none')
            self._transition = core.request_publish(self._transition.state, request)
            return self._run()
        finally:
            self._lock.release()
            if (self._cancelled.is_set() and self._transition is not None
                    and isinstance(self._transition.action, core.AwaitPublishRequest)):
                self.cancel()

    def cancel(self):
        self._cancelled.set()
        if self._lock.acquire(blocking=False):
            try:
                if self._transition is None or isinstance(self._transition.action, core.AwaitPublishRequest):
                    if self._transition is None:
                        self._activation_outcome = 'blocked_no_effect'
                    if self._dispose():
                        raise wire.WireFailure('adapter_error', 'none')
            finally:
                self._lock.release()

    def _dispose(self):
        """Retire each owner once; never retry a possibly closed descriptor."""
        self._closed = True
        failed = self._cleanup_failed or bool(self._stage and self._stage._cleanup_failed)
        stage, self._stage = self._stage, None
        api, self._api = self._api, None
        for owner in (stage, api):
            if owner is not None:
                try:
                    owner.close()
                except BaseException:
                    failed = True
        self._cleanup_failed = failed
        return failed

    def close(self):
        self._cancelled.set()
        if not self._lock.acquire(blocking=False):
            raise wire.WireFailure('invalid_event', 'none')
        try:
            if self._dispose():
                if self.outcome == 'uncertain_remote_effect':
                    raise wire.WireFailure(self._transition.state.code, 'unknown')
                raise wire.WireFailure('adapter_error', 'none')
        finally:
            self._lock.release()
