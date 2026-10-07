"""Owned core execution over real loopback TLS; fixtures grant no authority."""
from contextlib import contextmanager
import sys
import tempfile
import unittest
from unittest.mock import patch

import rc_publication_contract as core
import rc_publication_executor as executor
import rc_publication_github as wire
from rc_publication_https_fixture import HTTPSFixture, authorities, gates
from rc_publication_stage import Selection
from rc_publication_stage_cases import publisher_fixture, artifact_worker, artifact_route


class ExecutorCases(unittest.TestCase):
    @contextmanager
    def session(self):
        with publisher_fixture() as fixture, HTTPSFixture(subject=fixture.selection.subject,
                plan=fixture.plan, payloads=fixture.payloads) as tls:
            tls.route = lambda *args: artifact_route(fixture, *args)
            with patch.object(wire, '_connect', side_effect=tls.connect), authorities(), artifact_worker(fixture, tls):
                session = executor.PublisherSession(fixture.root, fixture.selection, 'fixture-token',
                                                     temporary_parent=fixture.temporary_parent)
                try:
                    yield session, tls, fixture
                finally:
                    try:
                        session.close()
                    except wire.WireFailure:
                        self.assertTrue(session._cleanup_failed)
                self.assertEqual(tls.errors, [])

    @staticmethod
    def request(session):
        pause = session.transition.action
        return core.PublicationRequest('publish-once', 'owner-request-reference',
                                       pause.release_id, pause.subject_digest)

    @staticmethod
    def mutations(tls):
        return [row for row in tls.requests if row[0] in ('POST', 'PATCH', 'DELETE')]

    def test_live_entry_is_blocked_without_real_verifiers_and_tag_guarantee(self):
        from rc_publication_admission_cases import IntegrationTLS
        with IntegrationTLS() as tls, tempfile.TemporaryDirectory() as root:
            selection = tls.selection
            for patched in (False, True):
                tls.requests.clear(); tls.counts.clear()
                with self.subTest(authenticator_only=patched), patch.object(executor, 'stage_selected') as stage:
                    session = executor.PublisherSession(root, selection, 'fixture-token', temporary_parent=root)
                    with patch.object(wire, '_authenticate', side_effect=gates if patched else wire._authenticate):
                        with self.assertRaises(wire.WireFailure) as failure:
                            session.run_until_pause()
                    self.assertEqual((failure.exception.code, failure.exception.effect), ('fence_blocked', 'none'))
                    self.assertEqual(session.outcome, 'blocked_no_effect')
                    self.assertIsNone(session.transition)
                    stage.assert_not_called()
                    self.assertEqual([r[1] for r in tls.requests], [] if patched else tls.expected_paths)
                    self.assertTrue(all(r[0] == 'GET' and r[3] == b'' for r in tls.requests))
                    self.assertEqual(self.mutations(tls), [])
                    session.close()
            with self.assertRaises(TypeError):
                executor.PublisherSession(root, selection, 'fixture-token', temporary_parent=root, enable_live=True)

    def test_real_tls_complete_trace_pauses_until_explicit_request(self):
        with self.session() as (session, tls, fixture):
            pause = session.run_until_pause()
            self.assertIsInstance(pause.action, core.AwaitPublishRequest)
            self.assertEqual(pause.state.intent_count, 22)
            stage = session._stage
            handles = [stage.stream(i) for i in range(6)]
            self.assertTrue(all(not handle.closed for handle in handles))
            count = len(tls.requests)
            self.assertIs(session.run_until_pause(), pause)
            self.assertEqual(len(tls.requests), count)
            final = session.request_publish(self.request(session))
            self.assertEqual(final.state.outcome, 'modeled_verified')
            self.assertEqual(session._attempted, set(range(1, 26)))
            self.assertEqual([r[0] for r in self.mutations(tls)], ['POST'] * 7 + ['PATCH'])
            self.assertEqual({row[0]['name']: row[1] for row in tls.assets.values()}, fixture.payloads)
            self.assertTrue(all(handle.closed for handle in handles))
            self.assertFalse(final.live_publication_verified)

    def test_each_mutation_rechecks_current_owner_scope(self):
        with self.session() as (session, tls, _):
            seen = []
            def owner(op, subject):
                seen.append((op.operation_id, op.kind, subject))
                if op.kind == 'PublishPrerelease':
                    raise wire.WireFailure('denied', 'none')
            with patch.object(wire, '_authorize', side_effect=owner):
                session.run_until_pause()
                final = session.request_publish(self.request(session))
            self.assertEqual([item[0] for item in seen], [2, 5, 8, 11, 14, 17, 20, 24])
            self.assertTrue(all(item[2] == session.transition.state.subject for item in seen))
            self.assertEqual(final.state.outcome, 'partial_draft')
            self.assertEqual(len(self.mutations(tls)), 7)
            self.assertTrue(tls.release['draft'])

    def test_cancellation_before_dispatch_has_no_effect(self):
        with self.session() as (session, tls, _):
            with patch.object(wire, '_authorize', side_effect=lambda *_: session.cancel()):
                result = session.run_until_pause()
            self.assertEqual(result.state.outcome, 'blocked_no_effect')
            self.assertEqual(result.state.code, 'cancelled')
            self.assertEqual(self.mutations(tls), [])
        for cancelled in (False, True):
            with self.subTest(during_staging_cancelled=cancelled), self.session() as (session, tls, fixture):
                original = tls.route
                owners = []
                def late(method, path, headers, body):
                    if path == wire.ROOT + '/actions/artifacts/14/zip':
                        owners.append(session._stage)
                        session.cancel() if cancelled else setattr(session, '_deadline', 0)
                    return original(method, path, headers, body)
                tls.route = late
                with self.assertRaises(wire.WireFailure) as failure:
                    session.run_until_pause()
                self.assertEqual(failure.exception.code, 'cancelled' if cancelled else 'timeout')
                self.assertEqual(failure.exception.effect, 'none')
                self.assertIsNone(session.transition)
                self.assertEqual(session.outcome, 'blocked_no_effect')
                self.assertTrue(owners and all(o._closed for o in owners))
                self.assertEqual(self.mutations(tls), [])

    def test_cancellation_after_possible_dispatch_is_sticky_unknown(self):
        with self.session() as (session, tls, _):
            def cancelled(method, path, headers, body):
                tls._release(method, path, headers, body)
                session.cancel()
                return {}
            tls.routes['POST', wire.ROOT + '/releases'] = cancelled
            result = session.run_until_pause()
            self.assertEqual(result.state.outcome, 'uncertain_remote_effect')
            self.assertEqual(len(self.mutations(tls)), 1)
            self.assertIsNotNone(tls.release)
            with self.assertRaises(wire.WireFailure):
                session.run_until_pause()
            self.assertEqual(len(self.mutations(tls)), 1)

    def test_duplicate_reentrant_and_out_of_order_dispatch_reject(self):
        with self.session() as (session, tls, _):
            with self.assertRaises(wire.WireFailure):
                session.request_publish(core.PublicationRequest('early', 'owner', 100, 'a' * 64))
            observed = []
            def owner(op, subject):
                with self.assertRaises(wire.WireFailure):
                    session.run_until_pause()
                observed.append(op.operation_id)
            with patch.object(wire, '_authorize', side_effect=owner):
                session.run_until_pause()
            self.assertEqual(observed, [2, 5, 8, 11, 14, 17, 20])
            self.assertEqual(len(set(observed)), 7)
            with self.assertRaises(wire.WireFailure):
                session._before_write()
            self.assertEqual(len(self.mutations(tls)), 7)

    def test_lost_response_never_retries_or_clears_uncertainty(self):
        with self.session() as (session, tls, _):
            def lost(method, path, headers, body):
                tls._release(method, path, headers, body)
                return {'raw': b'HTTP/1.1 201 Fixture\r\nContent-Length: 50\r\n\r\n{'}
            tls.routes['POST', wire.ROOT + '/releases'] = lost
            result = session.run_until_pause()
            self.assertEqual(result.state.outcome, 'uncertain_remote_effect')
            self.assertIsNone(result.state.release_id)
            session.close()
            self.assertEqual(session.outcome, 'uncertain_remote_effect')
            self.assertEqual(len(self.mutations(tls)), 1)
        with self.session() as (session, tls, _):
            def lost_and_cleanup(method, path, headers, body):
                tls._release(method, path, headers, body)
                original = session._stage.close
                def fail():
                    original()
                    raise OSError('local closure failed')
                session._stage.close = fail
                return {}
            tls.routes['POST', wire.ROOT + '/releases'] = lost_and_cleanup
            with self.assertRaises(wire.WireFailure) as failure:
                with session:
                    result = session.run_until_pause()
                    self.assertEqual(result.state.outcome, 'uncertain_remote_effect')
            self.assertEqual(failure.exception.effect, 'unknown')
            self.assertEqual(failure.exception.code, result.state.code)
            self.assertEqual(session.outcome, 'uncertain_remote_effect')
            self.assertEqual(len(self.mutations(tls)), 1)

    def test_confirmed_mutation_cleanup_failure_retains_known_ids(self):
        with self.session() as (session, tls, _):
            def closing_socket(host, timeout):
                socket = tls.connect(host, timeout)
                send, close, mutation = socket.sendall, socket.close, []
                def sending(data):
                    if data.startswith(b'POST '):
                        mutation.append(True)
                    return send(data)
                def closing():
                    close()
                    if mutation:
                        raise OSError('fixture close failure')
                socket.sendall, socket.close = sending, closing
                return socket
            with patch.object(wire, '_connect', side_effect=closing_socket):
                result = session.run_until_pause()
            self.assertEqual((result.state.outcome, result.state.release_id), ('partial_draft', 100))
            self.assertEqual(len(self.mutations(tls)), 1)

    def test_read_failure_uses_existing_core_outcomes(self):
        for after_create in (False, True):
            with self.subTest(after_create=after_create), self.session() as (session, tls, _):
                original = tls.route
                def route(method, path, headers, body):
                    if path == wire.ROOT + '/releases?per_page=100&page=1' and bool(tls.release) == after_create:
                        return 503, {}, b'{}'
                    return original(method, path, headers, body)
                tls.route = route
                result = session.run_until_pause()
                self.assertEqual(result.state.outcome, 'partial_draft' if after_create else 'blocked_no_effect')
                self.assertEqual(len(self.mutations(tls)), int(after_create))
        for cancelled in (False, True):
            with self.subTest(late_read_cancelled=cancelled), self.session() as (session, tls, _):
                original = tls.route
                def late(method, path, headers, body):
                    if path == wire.ROOT + '/releases?per_page=100&page=1':
                        session.cancel() if cancelled else setattr(session, '_deadline', 0)
                    return original(method, path, headers, body)
                tls.route = late
                result = session.run_until_pause()
                self.assertEqual(result.state.outcome, 'blocked_no_effect')
                self.assertEqual(result.state.code, 'cancelled' if cancelled else 'timeout')
                self.assertEqual(self.mutations(tls), [])

    def test_publish_request_never_grants_authority(self):
        with self.session() as (session, tls, _):
            session.run_until_pause()
            request = self.request(session)
            with patch.object(wire, '_authenticate', side_effect=wire.WireFailure('denied', 'none')):
                result = session.request_publish(request)
            self.assertEqual(result.state.outcome, 'partial_draft')
            self.assertTrue(tls.release['draft'])
            self.assertEqual(len(self.mutations(tls)), 7)

    def test_pause_close_is_local_only_and_cannot_resume(self):
        for method in ('close', 'cancel', 'cancelled_request'):
            with self.subTest(method=method), self.session() as (session, tls, _):
                pause = session.run_until_pause()
                handles = [session._stage.stream(i) for i in range(6)]
                count = len(tls.requests)
                if method == 'cancelled_request':
                    session._cancelled.set()
                    with self.assertRaises(wire.WireFailure):
                        session.request_publish(self.request(session))
                else:
                    getattr(session, method)()
                self.assertIs(session.transition, pause)
                self.assertIsNone(session.outcome)
                self.assertEqual(len(tls.requests), count)
                self.assertTrue(all(handle.closed for handle in handles))
                with self.assertRaises(wire.WireFailure):
                    session.request_publish(self.request(session))
        with self.session() as (session, tls, _):
            previous, captured = sys.getprofile(), []
            def at_pause(frame, event, result):
                if (frame.f_code is core.advance.__code__ and event == 'return'
                        and isinstance(result.action, core.AwaitPublishRequest)):
                    captured.extend(session._stage.stream(i) for i in range(6))
                    session.cancel()
            sys.setprofile(at_pause)
            try:
                pause = session.run_until_pause()
            finally:
                sys.setprofile(previous)
            self.assertIsInstance(pause.action, core.AwaitPublishRequest)
            self.assertTrue(captured and all(handle.closed for handle in captured))
            self.assertTrue(session._closed)
            self.assertIsNone(session.outcome)
            self.assertEqual(len(self.mutations(tls)), 7)

    def test_final_cleanup_failure_prevents_success_report(self):
        for expired in (False, True):
            with self.subTest(expired=expired), self.session() as (session, tls, _):
                session.run_until_pause()
                stage = session._stage
                original = stage.close
                def fail():
                    original()
                    if expired:
                        session._deadline = 0
                    else:
                        raise OSError('fixture cleanup failed')
                with patch.object(stage, 'close', side_effect=fail):
                    result = session.request_publish(self.request(session))
                self.assertEqual(result.state.outcome, 'published_unverified')
                self.assertEqual(result.state.code, 'timeout' if expired else 'adapter_error')
                self.assertFalse(tls.release['draft'])
                self.assertIs(session._cleanup_failed, not expired)
                self.assertEqual(len(self.mutations(tls)), 8)


if __name__ == '__main__':
    unittest.main()
