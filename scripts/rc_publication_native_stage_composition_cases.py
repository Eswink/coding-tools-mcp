"""Actual native loop/owned Stage/TLS composition; no live GitHub authority."""
from contextlib import contextmanager
import io
import threading
import time
import unittest
from unittest.mock import patch

import rc_consumer_io as safe
import rc_publication_artifact_admission as artifacts
from rc_publication_artifact_admission_cases import ArtifactTLS
import rc_publication_contract as core
import rc_publication_executor as executor
from rc_publication_executor_cases import ExecutorCases
import rc_publication_github as wire
from rc_publication_https_fixture import gates
import rc_publication_request as owned
import rc_publication_stage as stage
from rc_publication_stage_cases import publisher_fixture, artifact_worker


class NativeStageCompositionCases(unittest.TestCase):
    @contextmanager
    def native_preparation(self):
        # Actual metadata/FINAL validators; production full admission remains
        # blocked. The session, client and ReadScope are created by native code.
        with publisher_fixture() as f, ArtifactTLS(f) as tls, patch.object(
                wire, '_connect', side_effect=tls.connect), artifact_worker(f, tls):
            session = executor.PublisherSession(f.root, f.selection, 'fixture-token',
                                                temporary_parent=f.parent)
            try:
                yield session, tls, f
            finally:
                session.close()
            self.assertEqual(tls.errors, [])
            self.assertEqual(ExecutorCases.mutations(tls), [])

    @contextmanager
    def modeled_upload(self):
        # Existing verified-loopback synthetic authority context. Refresh the
        # actual registered owner exactly as production full authentication
        # does; do not manufacture a ReadScope, operation scope or live grant.
        with ExecutorCases.session(self) as (session, tls, f):
            def modeled(selection, api, *, deadline, check_active):
                owner = artifacts._OWNERS.get(api)
                if owner is not None:
                    self.assertIs(owner, session._artifact_owner)
                    self.assertIs(owner.stage, session._stage)
                    self.assertIs(owner.selection, api.selection)
                    self.assertIs(type(session._read_scope), owned._ReadScope)
                    owner._capture(deadline=deadline, check_active=check_active)
                return gates(selection, api, deadline=deadline, check_active=check_active)
            with patch.object(wire, '_authenticate', side_effect=modeled):
                yield session, tls, f

    def blocked(self, session, code='fence_blocked'):
        with self.assertRaises(wire.WireFailure) as caught:
            session.run_until_pause()
        self.assertEqual((caught.exception.code, caught.exception.effect), (code, 'none'))
        self.assertIsNone(caught.exception.release_id)
        self.assertIsNone(caught.exception.asset)
        self.assertIsNone(session.transition)
        self.assertEqual(session.outcome, 'blocked_no_effect')
        return caught.exception

    def test_native_prepare_uses_canonical_owned_stage_and_remains_blocked(self):
        with self.native_preparation() as (session, tls, f):
            saved_api, seen, handles = session._api, [], []
            real_authenticate = wire._authenticate
            def observe(selection, api, *, deadline, check_active):
                owner, scope = artifacts._OWNERS[api], session._read_scope
                self.assertIs(selection, api.selection)
                self.assertIs(api, saved_api)
                self.assertIsNot(selection, f.selection)
                self.assertIs(owner, session._artifact_owner)
                self.assertIs(owner.stage, session._stage)
                self.assertIs(owner.stage._api, owner.adapter)
                self.assertIs(owner.adapter.api, api)
                self.assertIs(owner.adapter.selection, selection)
                self.assertIs(type(scope), owned._ReadScope)
                self.assertIs(scope._owner, session._owner)
                self.assertTrue(session._lock.locked())
                report = artifacts.authenticate_artifacts(api, selection,
                    deadline=deadline, check_active=check_active)
                self.assertEqual(sum(row[3] == 'passed' for row in report.rows), 5)
                self.assertEqual(sum(row[3] == 'unknown' for row in report.rows), 58)
                self.assertFalse(report.release_approved)
                self.assertFalse(report.publish_approved)
                self.assertFalse(report.snapshot_atomic)
                handles.extend(owner.stage.stream(i) for i in range(6))
                self.assertEqual(handles, owner.stage._handles)
                self.assertTrue(all(not handle.closed for handle in handles))
                seen.append((owner, scope))
                return real_authenticate(selection, api, deadline=deadline, check_active=check_active)
            with patch.object(wire, '_authenticate', side_effect=observe):
                self.blocked(session)
            self.assertEqual(len(seen), 1)
            owner, scope = seen[0]
            self.assertTrue(scope._retired)
            self.assertTrue(owner.closed and owner.stage._closed)
            self.assertNotIn(saved_api, artifacts._OWNERS)
            self.assertTrue(all(handle.closed for handle in handles))
            self.assertIsNone(session._api)
            self.assertIsNone(session._read_scope)
            self.assertTrue(tls.requests)

    def test_first_native_deadline_stops_retained_provenance_after_last_get(self):
        with self.native_preparation() as (session, tls, _):
            armed, reached, codes, returned = [], [], [], []
            real_stream = stage.StagedAssets.stream
            def stream(actual, ordinal):
                handle = real_stream(actual, ordinal)
                if armed and ordinal == 4:
                    scope = session._read_scope
                    self.assertIs(actual, session._artifact_owner.stage)
                    self.assertIs(handle, actual._handles[4])
                    self.assertIs(type(scope), owned._ReadScope)
                    reached.append((len(tls.requests), scope._deadline))
                    # The actual first native deadline expires, with no
                    # controller editing, fake clock or replacement stream.
                    time.sleep(max(0, scope._deadline - time.monotonic()) + 0.03)
                    self.assertGreater(time.monotonic(), scope._deadline)
                return handle
            def observe(selection, api, *, deadline, check_active):
                scope = session._read_scope
                self.assertIs(type(scope), owned._ReadScope)
                # A longer current/caller deadline is a negative input; the
                # native-issued first deadline must remain authoritative.
                session._deadline = scope._deadline + 1000
                armed.append(True)
                try:
                    returned.append(artifacts.authenticate_artifacts(api, selection,
                        deadline=session._deadline, check_active=lambda: None))
                except safe.ConsumerError as error:
                    codes.append(error.code)
                raise wire.WireFailure('fence_blocked', 'none')
            with patch.object(executor, 'OPERATION_SECONDS', 30), patch.object(
                    stage.StagedAssets, 'stream', new=stream), patch.object(
                    wire, '_authenticate', side_effect=observe):
                self.blocked(session)
            self.assertEqual(codes, ['transport_deadline_exceeded'])
            self.assertEqual(returned, [])
            self.assertEqual(len(reached), 1)
            self.assertEqual(len(tls.requests), reached[0][0])

    def test_entered_native_cancel_with_noop_caller_sends_no_new_get(self):
        with self.native_preparation() as (session, tls, _):
            seen = []
            def observe(selection, api, *, deadline, check_active):
                owner, before = artifacts._OWNERS[api], len(tls.requests)
                self.assertIs(owner, session._artifact_owner)
                session.cancel()
                with self.assertRaisesRegex(safe.ConsumerError, '^transport_cancelled$'):
                    artifacts.authenticate_artifacts(api, selection,
                        deadline=deadline + 1000, check_active=lambda: None)
                self.assertEqual(len(tls.requests), before)
                seen.append(owner)
                raise wire.WireFailure('cancelled', 'none')
            with patch.object(wire, '_authenticate', side_effect=observe):
                self.blocked(session, 'cancelled')
            self.assertEqual(len(seen), 1)
            self.assertIsNone(seen[0]._report)

    def test_native_client_without_held_scope_cannot_claim_owned_budget(self):
        with self.native_preparation() as (session, tls, f):
            owner = artifacts._ArtifactOwner(f.root, session._selection, session._api,
                                             temporary_parent=f.parent)
            session._artifact_owner, session._stage = owner, owner.stage
            end = time.monotonic() + 60
            session._deadline = end
            before = len(tls.requests)
            with self.assertRaises((safe.ConsumerError, wire.WireFailure)):
                owner.enter(deadline=end, check_active=session._check_active)
            self.assertIsNone(session._read_scope)
            with self.assertRaises(wire.WireFailure) as caught:
                owner._controls(end + 1000, lambda: None)
            self.assertEqual((caught.exception.code, caught.exception.effect), ('invalid_event', 'none'))
            self.assertEqual(len(tls.requests), before)
            self.assertNotIn(session._api, artifacts._OWNERS)

    def test_registered_artifact_stream_reaches_original_authorizer_denial(self):
        real_authorize = wire._authorize
        with self.modeled_upload() as (session, tls, _):
            observed = []
            # Only CreateDraft is modeled by the existing local fixture. The
            # target upload reaches the original production hard rejection.
            def denied(op, subject, *, request, scope):
                if op.kind == 'CreateDraft':
                    return None
                self.assertEqual(op.kind, 'UploadAsset')
                owner, actual = session._artifact_owner, session._stage
                self.assertIs(artifacts._OWNERS[session._api], owner)
                self.assertIs(owner.stage, actual)
                self.assertIs(actual._api, owner.adapter)
                self.assertIs(owner.adapter.api, session._api)
                self.assertIs(owner.selection, session._api.selection)
                self.assertIs(scope, session._request_scope)
                self.assertIs(scope._owner, session._owner)
                self.assertIs(request._client, session._api)
                self.assertIs(request._scope, scope)
                self.assertIs(request._stream, actual._handles[op.asset_ordinal])
                self.assertEqual(request._stream.tell(), 0)
                scope._check(session._api, op)
                self.assertIs(type(session._read_scope), owned._ReadScope)
                session._read_scope._check(session._api)
                observed.append(request)
                return real_authorize(op, subject, request=request, scope=scope)
            with patch.object(wire, '_authorize', side_effect=denied):
                result = session.run_until_pause()
            self.assertEqual((result.state.outcome, result.state.code), ('partial_draft', 'denied'))
            self.assertEqual(len(observed), 1)
            self.assertEqual([r[0] for r in ExecutorCases.mutations(tls)], ['POST'])
            self.assertFalse(result.live_publication_verified)
            self.assertTrue(tls.release['draft'])

    def test_foreign_upload_handle_cannot_reach_authorizer(self):
        with self.modeled_upload() as (session, tls, _):
            execute, called = session._execute, []
            def operation(op):
                if op.kind == 'UploadAsset':
                    return session._api.upload_asset(op, io.BytesIO(b'foreign'),
                        before_write=session._before_write, check_active=lambda: None,
                        scope=session._request_scope)
                return execute(op)
            def authorize(op, subject, *, request, scope):
                called.append(op.kind)
            with patch.object(session, '_execute', side_effect=operation), patch.object(
                    wire, '_authorize', side_effect=authorize):
                result = session.run_until_pause()
            self.assertEqual((result.state.outcome, result.state.code), ('partial_draft', 'invalid_request'))
            self.assertEqual(called, ['CreateDraft'])
            self.assertEqual([r[0] for r in ExecutorCases.mutations(tls)], ['POST'])
            self.assertFalse(result.live_publication_verified)

    def test_native_no_held_scope_rejects_before_enter_or_control_caller(self):
        with self.native_preparation() as (session, tls, f):
            owner = artifacts._ArtifactOwner(f.root, session._selection, session._api,
                                             temporary_parent=f.parent)
            session._artifact_owner, session._stage = owner, owner.stage
            end, called = time.monotonic() + 60, []
            session._deadline = end
            def caller():
                called.append(True)
                raise RuntimeError('caller must not run without native scope')
            for invoke in (lambda: owner.enter(deadline=end, check_active=caller),
                           lambda: owner._controls(end + 1000, caller)):
                with self.assertRaises(wire.WireFailure) as caught:
                    invoke()
                self.assertEqual((caught.exception.code, caught.exception.effect),
                                 ('invalid_event', 'none'))
                self.assertEqual(called, [])
            self.assertIsNone(session._read_scope)
            self.assertEqual(tls.requests, [])

    def test_actual_entered_wrong_thread_rejects_before_caller(self):
        with self.native_preparation() as (session, tls, _):
            outcomes, called = [], []
            def observe(selection, api, *, deadline, check_active):
                owner, before = artifacts._OWNERS[api], len(tls.requests)
                self.assertIs(type(session._read_scope), owned._ReadScope)
                def caller():
                    called.append(True)
                    raise RuntimeError('foreign thread caller must not run')
                def foreign():
                    try:
                        owner._controls(deadline + 1000, caller)
                    except BaseException as error:
                        outcomes.append(error)
                worker = threading.Thread(target=foreign)
                worker.start(); worker.join(5)
                self.assertFalse(worker.is_alive())
                self.assertEqual(len(tls.requests), before)
                raise wire.WireFailure('fence_blocked', 'none')
            with patch.object(wire, '_authenticate', side_effect=observe):
                self.blocked(session)
            self.assertEqual(called, [])
            self.assertEqual(len(outcomes), 1)
            self.assertIs(type(outcomes[0]), wire.WireFailure)
            self.assertEqual((outcomes[0].code, outcomes[0].effect), ('invalid_event', 'none'))

    def test_actual_paused_retired_owner_does_not_poll_caller(self):
        with self.modeled_upload() as (session, tls, _):
            scopes, called = [], []
            execute = session._execute
            def operation(op):
                scopes.append(session._read_scope)
                return execute(op)
            with patch.object(session, '_execute', side_effect=operation):
                pause = session.run_until_pause()
            self.assertIs(type(pause.action), core.AwaitPublishRequest)
            self.assertTrue(scopes and all(scope._retired for scope in scopes))
            self.assertIsNone(session._read_scope)
            self.assertFalse(session._lock.locked())
            owner, before = session._artifact_owner, len(tls.requests)
            self.assertTrue(owner.entered and not owner.closed)
            def caller():
                called.append(True)
                raise RuntimeError('paused caller must not run')
            with self.assertRaises((safe.ConsumerError, wire.WireFailure)):
                owner._controls(time.monotonic() + 1000, caller)
            self.assertEqual(called, [])
            self.assertEqual(len(tls.requests), before)

    def test_actual_upload_owner_missing_reciprocal_session_is_rejected(self):
        with self.modeled_upload() as (session, tls, _):
            execute, called, observations = session._execute, [], []
            def operation(op):
                if op.kind != 'UploadAsset':
                    return execute(op)
                owner, before = session._artifact_owner, len(tls.requests)
                self.assertIs(owner._session, session)
                self.assertIs(type(session._request_scope), owned._OperationScope)
                self.assertIs(session._request_scope._op, op)
                # Unsupported private mutation is a negative invariant input;
                # neither immutable credential nor actual issued scope changes.
                owner._session = None
                try:
                    return execute(op)
                finally:
                    owner._session = session
                    observations.append((before, len(tls.requests)))
            def authorize(op, subject, *, request, scope):
                called.append(op.kind)
                if op.kind == 'UploadAsset':
                    raise wire.WireFailure('denied', 'none')
            with patch.object(session, '_execute', side_effect=operation), patch.object(
                    wire, '_authorize', side_effect=authorize):
                result = session.run_until_pause()
            self.assertEqual((result.state.outcome, result.state.code),
                             ('partial_draft', 'invalid_request'))
            self.assertEqual(called, ['CreateDraft'])
            self.assertEqual(len(observations), 1)
            self.assertEqual(observations[0][0], observations[0][1])
            self.assertEqual([r[0] for r in ExecutorCases.mutations(tls)], ['POST'])
            self.assertFalse(result.live_publication_verified)

    def test_actual_entered_callback_non_none_cannot_be_ignored(self):
        with self.native_preparation() as (session, tls, _):
            reached = []
            def observe(selection, api, *, deadline, check_active):
                before = len(tls.requests)
                with self.assertRaisesRegex(safe.ConsumerError, '^artifact_transport_failed$'):
                    artifacts.authenticate_artifacts(api, selection,
                        deadline=deadline, check_active=lambda: True)
                self.assertEqual(len(tls.requests), before)
                reached.append(True)
                raise wire.WireFailure('fence_blocked', 'none')
            with patch.object(wire, '_authenticate', side_effect=observe):
                self.blocked(session)
            self.assertEqual(reached, [True])

    def test_actual_entered_callback_unknown_or_confirmed_effect_is_preserved(self):
        with self.native_preparation() as (session, tls, _):
            reached = []
            def observe(selection, api, *, deadline, check_active):
                owner, before = artifacts._OWNERS[api], len(tls.requests)
                for code, effect in (('cancelled', 'unknown'), ('timeout', 'confirmed')):
                    error = wire.WireFailure(code, effect)
                    def caller():
                        raise error
                    with self.assertRaises(wire.WireFailure) as caught:
                        owner._controls(deadline, caller)
                    self.assertIs(caught.exception, error)
                    self.assertEqual((caught.exception.code, caught.exception.effect), (code, effect))
                self.assertEqual(len(tls.requests), before)
                reached.append(True)
                raise wire.WireFailure('fence_blocked', 'none')
            with patch.object(wire, '_authenticate', side_effect=observe):
                self.blocked(session)
            self.assertEqual(reached, [True])


if __name__ == '__main__':
    unittest.main()
