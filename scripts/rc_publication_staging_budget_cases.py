"""Shared activation controls over real workers/TLS; synthetic authority only."""
from contextlib import ExitStack, contextmanager
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import rc_artifact_consumer as consumer
from rc_consumer_io import ConsumerError, PrivateRoot
import rc_publication_contract as core
import rc_publication_executor as executor
import rc_publication_executor_cases as old
import rc_publication_github as wire
import rc_publication_stage as stage
from rc_publication_stage_cases import publisher_fixture, artifact_worker

transport = consumer.transport


class StagingBudgetCases(unittest.TestCase):
    @contextmanager
    def recording(self, *, pipe=None, root_failure=False, api_failure=False):
        seen = SimpleNamespace(downloads=[], created=[], owners=[], children=[], before=[], returned=[],
            transport_errors=[], stage_errors=[], roots=[], apis=[], retired=[], pipes=[], auth=[], stage=None)
        download, start, cleanup = transport.download_artifact_zip, transport._Download.start, transport._Download.cleanup
        initialize = transport._Download.__init__
        enter, close_root, close_api, authenticate = stage.StagedAssets.__enter__, PrivateRoot.close, wire.GitHub.close, wire._authenticate

        class BadClose:
            def __init__(self, stream):
                self.stream, self.calls = stream, 0

            def __getattr__(self, name):
                return getattr(self.stream, name)

            def close(self):
                self.calls += 1
                self.stream.close()
                raise OSError('injected bounded close failure')

        def initialized(owner, *args, **kwargs):
            initialize(owner, *args, **kwargs)
            seen.created.append(owner)

        def launched(owner, opener):
            seen.before.append(tuple(child.poll() for child in seen.children))
            self.assertTrue(all(code is not None for code in seen.before[-1]))
            try:
                return start(owner, opener)
            finally:
                if owner.process is not None:
                    seen.owners.append(owner)
                    seen.children.append(owner.process)
                    if seen.downloads[-1][0] == pipe:
                        wrapped = BadClose(owner.process.stdin)
                        seen.pipes.append(wrapped)
                        owner.process.stdin = wrapped

        def downloaded(api, metadata, destination, **kwargs):
            seen.downloads.append((metadata['id'], kwargs.copy()))
            try:
                return download(api, metadata, destination, **kwargs)
            except ConsumerError as error:
                seen.transport_errors.append((error.code, getattr(error, 'original_error_code', None)))
                raise
            finally:
                seen.returned.append(tuple(child.poll() for child in seen.children))
                self.assertTrue(all(code is not None for code in seen.returned[-1]))

        def entered(owner):
            seen.stage = owner
            try:
                return enter(owner)
            except BaseException as error:
                seen.stage_errors.append(error)
                raise

        def root_closed(owner):
            seen.roots.append(owner)
            close_root(owner)
            if root_failure and len(seen.roots) == 1:
                raise OSError('injected bounded root close failure')

        def api_closed(owner):
            seen.apis.append(owner)
            close_api(owner)
            if api_failure:
                raise OSError('injected bounded API close failure')

        def retired(owner):
            seen.retired.append(owner)
            return cleanup(owner)

        def authenticated(*args, **kwargs):
            seen.auth.append(kwargs.copy())
            return authenticate(*args, **kwargs)

        with ExitStack() as stack:
            for obj, name, replacement in ((transport, 'download_artifact_zip', downloaded),
                    (transport._Download, '__init__', initialized),
                    (transport._Download, 'start', launched), (transport._Download, 'cleanup', retired),
                    (stage.StagedAssets, '__enter__', entered), (PrivateRoot, 'close', root_closed),
                    (wire.GitHub, 'close', api_closed), (wire, '_authenticate', authenticated)):
                stack.enter_context(patch.object(obj, name, replacement))
            yield seen

    @contextmanager
    def session(self, *, seconds=30, **faults):
        with old.ExecutorCases.session(self) as (session, tls, fixture):
            with self.recording(**faults) as seen, patch.object(executor, 'OPERATION_SECONDS', seconds):
                yield session, tls, fixture, seen

    def children_exited(self, seen, count):
        self.assertEqual(len(seen.children), count)
        self.assertEqual(len({id(child) for child in seen.children}), count)
        self.assertEqual(len({child.pid for child in seen.children}), count)
        self.assertTrue(all(child.poll() is not None and child.returncode is not None for child in seen.children))
        self.assertTrue(all(seen.retired.count(owner) == 1 for owner in seen.owners))
        self.assertEqual(seen.retired, seen.created)
        self.assertEqual(len({id(owner) for owner in seen.retired}), len(seen.retired))
        self.assertTrue(all(owner.disposed for owner in seen.created))
        if count == 2:
            self.assertEqual(len(seen.before[1]), 1)
            self.assertIsNotNone(seen.before[1][0])

    def bindings(self, owner, fixture):
        self.assertEqual(owner.subject, fixture.selection.subject)
        self.assertEqual(owner.plan_bytes, fixture.plan_bytes)
        self.assertEqual(owner.provenance_bytes, fixture.provenance_bytes)
        self.assertEqual(owner.plan.assets, fixture.plan.assets)
        handles = tuple(owner.stream(i) for i in range(6))
        for index, row in enumerate(owner.plan.assets):
            self.assertEqual(handles[index].read(), fixture.payloads[row.name])
        with patch.object(PrivateRoot, 'open', side_effect=AssertionError('must retain handles')):
            for index, handle in enumerate(handles):
                self.assertIs(owner.stream(index), handle)
        return handles

    def activation_failed(self, session, tls, seen, code, count, *, sticky=False):
        self.assertIsNone(session.transition)
        self.assertEqual(session.outcome, 'blocked_no_effect')
        self.assertTrue(session._closed)
        self.assertIsNone(session._stage)
        self.assertIsNone(session._api)
        self.assertEqual(old.ExecutorCases.mutations(tls), [])
        self.assertIs(session._cleanup_failed, sticky)
        self.children_exited(seen, count)
        if seen.stage is not None:
            self.assertTrue(seen.stage._closed)
            self.assertTrue(all(root.fd is None for root in seen.stage._roots))
            self.assertTrue(all(handle.closed for handle in seen.stage._handles))
            self.assertEqual(len(seen.roots), len(seen.stage._roots))
        self.assertEqual(len({id(root) for root in seen.roots}), len(seen.roots))
        self.assertEqual(len(seen.apis), 1)
        counts = tuple(len(getattr(seen, key)) for key in ('roots', 'apis', 'retired', 'children'))
        for finish in (session.close, session.cancel, session.close):
            if sticky:
                with self.assertRaises(wire.WireFailure) as failure:
                    finish()
                self.assertEqual((failure.exception.code, failure.exception.effect), ('adapter_error', 'none'))
            else:
                finish()
        self.assertEqual(counts, tuple(len(getattr(seen, key)) for key in ('roots', 'apis', 'retired', 'children')))
        self.assertIs(session._cleanup_failed, sticky)
        with self.assertRaises(wire.WireFailure) as failure:
            session.run_until_pause()
        self.assertEqual(failure.exception.code, 'invalid_request')

    def failed_run(self, session, code):
        with self.assertRaises(wire.WireFailure) as failure:
            session.run_until_pause()
        self.assertEqual((failure.exception.code, failure.exception.effect), (code, 'none'))

    def blocked_download(self, ident, cancelled, *, pipe=False, root_failure=False, api_failure=False):
        seconds, release, reached = 3, threading.Event(), threading.Event()
        with self.session(seconds=seconds, pipe=ident if pipe else None,
                root_failure=root_failure, api_failure=api_failure) as (session, tls, _, seen):
            path = wire.ROOT + f'/actions/artifacts/{ident}/zip'
            original = tls.route

            def blocked(method, target, headers, body):
                if target == path:
                    reached.set()
                    if cancelled:
                        session.cancel()
                    release.wait(seconds + transport.CLEANUP_TIMEOUT + 2)
                return original(method, target, headers, body)

            tls.route = blocked
            sticky = pipe or root_failure or api_failure
            code = 'adapter_error' if sticky else 'cancelled' if cancelled else 'timeout'
            started = time.monotonic()
            try:
                self.failed_run(session, code)
                elapsed = time.monotonic() - started
                self.assertTrue(reached.is_set())
                self.assertLess(elapsed, seconds + transport.CLEANUP_TIMEOUT + 2)
                self.assertEqual(len(seen.stage._roots), 6)
                count = 1 if ident == 14 else 2
                self.assertEqual(len(seen.retired), count)
                self.activation_failed(session, tls, seen, code, count, sticky=sticky)
                deadline = seen.auth[0]['deadline']
                self.assertEqual(session._deadline, deadline)
                self.assertTrue(all(kwargs['deadline'] == deadline for _, kwargs in seen.downloads))
                self.assertTrue(all(owner.deadline == deadline for owner in seen.owners))
                if ident == 14:
                    self.assertFalse(any(row[1].endswith('/artifacts/13/zip') for row in tls.requests))
                expected = 'transport_cancelled' if cancelled else 'transport_deadline_exceeded'
                self.assertEqual(seen.transport_errors[-1][0], 'transport_cleanup_uncertain' if pipe else expected)
                self.assertIs(seen.stage._cleanup_failed, pipe or root_failure)
                if pipe:
                    self.assertEqual(seen.transport_errors[-1][1], expected)
                    self.assertIsInstance(seen.stage_errors[-1], ConsumerError)
                    self.assertEqual(seen.stage_errors[-1].code, 'transport_cleanup_uncertain')
                    self.assertTrue(all(stream.calls == 1 and stream.stream.closed for stream in seen.pipes))
                    seen.stage.close()
                    self.assertTrue(seen.stage._cleanup_failed)
            finally:
                release.set()

    def test_default_stage_and_consumer_keep_download_defaults(self):
        with publisher_fixture() as fixture, artifact_worker(fixture), self.recording() as seen:
            owner = stage.stage_selected(fixture.root, fixture.selection, fixture.api, temporary_parent=fixture.parent)
            try:
                owner.__enter__()
                handles = self.bindings(owner, fixture)
                self.assertEqual(seen.downloads, [(14, {}), (13, {'opener': None})])
                self.assertTrue(all(owner.check_active is None and not owner.shared for owner in seen.owners))
                self.assertLess(seen.owners[0].deadline, seen.owners[1].deadline)
                self.children_exited(seen, 2)
            finally:
                owner.close()
            owner.close()
            self.assertEqual(len(seen.roots), 6)
            self.assertTrue(all(handle.closed for handle in handles))
            self.assertTrue(all(root.fd is None for root in owner._roots))

    def test_session_shares_activation_deadline_and_bound_callback(self):
        with self.session() as (session, _, fixture, seen):
            pause = session.run_until_pause()
            self.assertIsInstance(pause.action, core.AwaitPublishRequest)
            handles = self.bindings(seen.stage, fixture)
            self.assertEqual([ident for ident, _ in seen.downloads], [14, 13])
            first, second = (kwargs for _, kwargs in seen.downloads)
            deadline = seen.auth[0]['deadline']
            self.assertEqual((first['deadline'], second['deadline']), (deadline, deadline))
            callback = first['check_active']
            self.assertIs(callback, second['check_active'])
            self.assertIs(callback.__self__, session)
            self.assertIs(callback.__func__, executor.PublisherSession._check_active)
            self.assertTrue(all(owner.deadline == deadline and owner.check_active is callback for owner in seen.owners))
            self.children_exited(seen, 2)
            session.close()
            self.assertTrue(all(handle.closed for handle in handles))
            self.assertTrue(all(root.fd is None for root in seen.stage._roots))

    def test_receipt_timeout_reaps_child_and_never_starts_final(self):
        self.blocked_download(14, False)

    def test_receipt_cancellation_reaps_child_and_never_starts_final(self):
        self.blocked_download(14, True)

    def test_final_timeout_reaps_both_children(self):
        self.blocked_download(13, False)

    def test_final_cancellation_reaps_both_children(self):
        self.blocked_download(13, True)

    def between_downloads(self, cancelled):
        with self.session() as (session, tls, fixture, seen):
            clock = SimpleNamespace(expired=False)
            clock.monotonic = lambda: session._deadline + 1 if clock.expired else time.monotonic()
            parse = stage._receipts

            def parsed(*args, **kwargs):
                result = parse(*args, **kwargs)
                self.children_exited(seen, 1)
                self.assertEqual(args[1].read('rc-asset-plan.json'), fixture.plan_bytes)
                self.assertEqual(args[1].read('RC_PROVENANCE.json'), fixture.provenance_bytes)
                session.cancel() if cancelled else setattr(clock, 'expired', True)
                return result

            with patch.object(stage, '_receipts', parsed), patch.object(executor, 'time', clock):
                code = 'cancelled' if cancelled else 'timeout'
                self.failed_run(session, code)
            self.activation_failed(session, tls, seen, code, 1)
            self.assertEqual([ident for ident, _ in seen.downloads], [14, 13])
            self.assertEqual(session._deadline, seen.auth[0]['deadline'])
            self.assertTrue(all(kwargs['deadline'] == session._deadline for _, kwargs in seen.downloads))
            self.assertIs(seen.downloads[0][1]['check_active'], seen.downloads[1][1]['check_active'])
            self.assertFalse(any(row[1].endswith('/artifacts/13/zip') for row in tls.requests))

    def test_deadline_expiring_between_downloads_prevents_second_launch(self):
        self.between_downloads(False)

    def test_cancellation_between_downloads_prevents_second_launch(self):
        self.between_downloads(True)

    def test_transport_cleanup_uncertainty_stays_sticky_on_both_downloads(self):
        for ident in (14, 13):
            for cancelled in (False, True):
                with self.subTest(artifact=ident, cancelled=cancelled):
                    self.blocked_download(ident, cancelled, pipe=True)

    def test_stage_cleanup_failure_overrides_timeout_and_cancel(self):
        for cancelled in (False, True):
            for fault in ('clean', 'root_failure', 'api_failure'):
                with self.subTest(cancelled=cancelled, fault=fault):
                    self.blocked_download(14, cancelled, **({} if fault == 'clean' else {fault: True}))

    def test_transport_uncertainty_survives_secondary_stage_close_failure(self):
        for ident in (14, 13):
            with self.subTest(artifact=ident):
                self.blocked_download(ident, True, pipe=True, root_failure=True)

    def test_failure_mapping_is_closed_and_activation_cleanup_is_one_shot(self):
        class Misleading(RuntimeError):
            code = 'timeout'

        class Hostile:
            def __eq__(self, other):
                raise AssertionError('must not compare arbitrary codes')

        unhashable, hostile = ConsumerError('invalid'), ConsumerError('invalid')
        unhashable.code, hostile.code = [], Hostile()
        cases = ((wire.WireFailure('denied', 'none'), 'denied', False),
            (ConsumerError('transport_deadline_exceeded'), 'timeout', False),
            (ConsumerError('transport_cancelled'), 'cancelled', False),
            (ConsumerError('transport_cleanup_uncertain'), 'adapter_error', True),
            (ConsumerError('unrelated_failure'), 'adapter_error', False),
            (Misleading(), 'adapter_error', False), (RuntimeError(), 'adapter_error', False),
            (unhashable, 'adapter_error', False), (hostile, 'adapter_error', False))
        for error, code, sticky in cases:
            with self.subTest(error=type(error).__name__, code=code), self.session() as (session, tls, _, seen):
                target = (wire, '_authenticate') if isinstance(error, wire.WireFailure) else (stage, '_observe')
                with patch.object(*target, side_effect=error):
                    self.failed_run(session, code)
                self.activation_failed(session, tls, seen, code, 0, sticky=sticky)
                self.assertEqual(seen.downloads, [])
        for cancelled in (False, True):
            with self.subTest(before_first_cancelled=cancelled), self.session() as (session, tls, _, seen):
                clock = SimpleNamespace(expired=False)
                clock.monotonic = lambda: session._deadline + 1 if clock.expired else time.monotonic()
                observe = stage._observe

                def observed(*args, **kwargs):
                    result = observe(*args, **kwargs)
                    session.cancel() if cancelled else setattr(clock, 'expired', True)
                    return result

                with patch.object(stage, '_observe', observed), patch.object(executor, 'time', clock):
                    code = 'cancelled' if cancelled else 'timeout'
                    self.failed_run(session, code)
                self.activation_failed(session, tls, seen, code, 0)
                self.assertEqual([ident for ident, _ in seen.downloads], [14])
                self.assertFalse(any(row[1].endswith('/zip') for row in tls.requests))


if __name__ == '__main__':
    unittest.main()
