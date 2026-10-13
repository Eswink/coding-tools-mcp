"""True TLS polling and native effect ownership; no live authorization."""
import json
import ssl
import threading
import unittest
from unittest.mock import patch

import rc_publication_artifact_admission as artifacts
import rc_publication_contract as core
import rc_publication_executor as executor
from rc_publication_executor_cases import ExecutorCases
import rc_publication_github as wire
import rc_publication_request as owned
from rc_publication_metadata_effect_cases import MetadataEffectCases, receipt
from rc_publication_native_stage_composition_cases import NativeStageCompositionCases


class HTTPEffectCases(unittest.TestCase):
    native_preparation = NativeStageCompositionCases.native_preparation
    blocked = NativeStageCompositionCases.blocked
    controls = MetadataEffectCases.controls

    def test_actual_native_get_missing_code_is_conservative_after_http_progress(self):
        rows = []
        with self.native_preparation() as (session, tls, _):
            def observe(selection, api, *, deadline, check_active):
                for phase in ('header', 'body', 'close'):
                    armed, calls, received_bytes, decoded, at_arm = [False], [], [], [], []
                    error = wire.WireFailure('timeout', 'confirmed', release_id=100, asset=receipt())
                    del error.code
                    owner, scope, first, end, _ = self.controls(session, api, deadline, lambda: None)
                    delivered = threading.Event()
                    def caller():
                        calls.append(True)
                        if armed[0]: raise error
                    def arm():
                        if not armed[0]:
                            at_arm.append(len(calls))
                            armed[0] = True
                    original_recv, original_send, original_close, original_json = (
                        ssl.SSLSocket.recv, ssl.SSLSocket.sendall, ssl.SSLSocket.close, wire._json)
                    def recv(sock, size, *args, **kwargs):
                        data = original_recv(sock, size, *args, **kwargs)
                        if sock.server_hostname == wire.API and data:
                            received_bytes.append(data)
                            if phase == 'header': arm()
                            if phase == 'body' and size > 1:
                                delivered.set()
                                arm()
                        return data
                    def send(sock, data, *args, **kwargs):
                        if phase == 'body' and sock.server_hostname is None and data.startswith(b'HTTP/'):
                            header, body = data.split(b'\r\n\r\n', 1)
                            original_send(sock, header + b'\r\n\r\n' + body[:1], *args, **kwargs)
                            self.assertTrue(delivered.wait(1))
                            return original_send(sock, body[1:], *args, **kwargs)
                        return original_send(sock, data, *args, **kwargs)
                    def close(sock, *args, **kwargs):
                        client = sock.server_hostname == wire.API
                        result = original_close(sock, *args, **kwargs)
                        if client and phase == 'close': arm()
                        return result
                    def decode(raw):
                        decoded.append(True)
                        return original_json(raw)
                    before, received = len(tls.requests), None
                    with patch.object(ssl.SSLSocket, 'recv', new=recv), patch.object(
                            ssl.SSLSocket, 'sendall', new=send), patch.object(
                            ssl.SSLSocket, 'close', new=close), patch.object(wire, '_json', side_effect=decode):
                        try:
                            # Original public transport binds the raw stronger
                            # caller to the actual current native ReadScope.
                            api.get('/', deadline=end, check_active=caller)
                        except wire.WireFailure as caught:
                            received = caught
                    self.assertEqual([r[1] for r in tls.requests[before:]], [wire.ROOT])
                    self.assertEqual(decoded, [])
                    self.assertEqual(len(calls), at_arm[0] + 1)
                    self.assertIs(session._read_scope, scope)
                    self.assertEqual(scope._deadline, first)
                    self.assertIsNone(owner._report)
                    raw = b''.join(received_bytes)
                    self.assertGreater(len(raw), 0)
                    if phase == 'header': self.assertEqual(raw, b'H')
                    if phase == 'body': self.assertEqual(len(raw.split(b'\r\n\r\n', 1)[1]), 1)
                    print(json.dumps(dict(scope='actual-native-GET-missing-code', phase=phase,
                        actual_bytes=len(raw), json_calls=0, armed_callback_calls=1, get_count=1,
                        code=received.code, effect=received.effect, receipts_clear=received.release_id is None and received.asset is None)))
                    rows.append((phase, received))
                raise wire.WireFailure('fence_blocked', 'none')
            with patch.object(wire, '_authenticate', side_effect=observe):
                self.blocked(session)
        self.assertEqual(len(rows), 3)
        for phase, received in rows:
            with self.subTest(phase=phase):
                self.assertEqual((received.code, received.effect, received.release_id, received.asset),
                    ('adapter_error', 'unknown', None, None))

    def test_actual_header_partial_body_and_postclose_non_none_polling(self):
        rows = []
        with self.native_preparation() as (session, tls, _):
            def observe(selection, api, *, deadline, check_active):
                for phase in ('header', 'body', 'close'):
                    for code, effect in (('cancelled', 'unknown'), ('timeout', 'confirmed')):
                        armed, calls, received_bytes, decoded, exposed = [False], [], [], [], []
                        error = wire.WireFailure(code, effect, release_id=100, asset=receipt())
                        at_arm, delivered = [], threading.Event()
                        def caller():
                            calls.append(True)
                            if armed[0]:
                                raise error
                        owner, scope, first, end, active = self.controls(session, api, deadline, caller)
                        original_recv, original_send, original_close = (
                            ssl.SSLSocket.recv, ssl.SSLSocket.sendall, ssl.SSLSocket.close)
                        original_json, original_get = wire._json, wire.GitHub.get
                        header_done, body_length = [False], []
                        def arm():
                            if not armed[0]:
                                at_arm.append(len(calls))
                                armed[0] = True
                        def recv(sock, size, *args, **kwargs):
                            data = original_recv(sock, size, *args, **kwargs)
                            if sock.server_hostname == wire.API and data:
                                received_bytes.append(data)
                                if size > 1:
                                    header_done[0] = True
                                    delivered.set()
                                    if phase == 'body': arm()
                                elif phase == 'header': arm()
                            return data
                        def send(sock, data, *args, **kwargs):
                            if (phase == 'body' and sock.server_hostname is None
                                    and data.startswith(b'HTTP/') and tls.requests[-1][1] == wire.ROOT):
                                header, body = data.split(b'\r\n\r\n', 1)
                                body_length.append(len(body))
                                self.assertGreater(len(body), 1)
                                original_send(sock, header + b'\r\n\r\n' + body[:1], *args, **kwargs)
                                self.assertTrue(delivered.wait(1))
                                return original_send(sock, body[1:], *args, **kwargs)
                            return original_send(sock, data, *args, **kwargs)
                        def close(sock, *args, **kwargs):
                            client = sock.server_hostname == wire.API
                            result = original_close(sock, *args, **kwargs)
                            if client and phase == 'close': arm()
                            return result
                        def decode(raw):
                            decoded.append(True)
                            return original_json(raw)
                        def get(client, path, **kwargs):
                            try:
                                return original_get(client, path, **kwargs)
                            except wire.WireFailure as caught:
                                exposed.append(caught)
                                raise
                        before, received = len(tls.requests), None
                        with patch.object(ssl.SSLSocket, 'recv', new=recv), patch.object(
                                ssl.SSLSocket, 'sendall', new=send), patch.object(
                                ssl.SSLSocket, 'close', new=close), patch.object(
                                wire, '_json', side_effect=decode), patch.object(wire.GitHub, 'get', new=get):
                            try:
                                artifacts.prepare_admission(selection, api, deadline=end, check_active=active)
                            except BaseException as caught:
                                received = caught
                        self.assertEqual([r[1] for r in tls.requests[before:]], [wire.ROOT])
                        self.assertTrue(all(r[0] == 'GET' for r in tls.requests[before:]))
                        self.assertEqual(decoded, [])
                        self.assertEqual(len(exposed), 1)
                        self.assertEqual(len(calls), at_arm[0] + 1)
                        self.assertIs(session._read_scope, scope)
                        self.assertEqual(scope._deadline, first)
                        self.assertIsNone(owner._report)
                        raw = b''.join(received_bytes)
                        self.assertGreater(len(raw), 0)
                        if phase == 'header': self.assertEqual(raw, b'H')
                        if phase == 'body':
                            self.assertTrue(header_done[0])
                            self.assertEqual(len(raw.split(b'\r\n\r\n', 1)[1]), 1)
                        print(json.dumps(dict(scope='actual-TLS-internal-poll', phase=phase,
                            header_or_body_bytes=len(raw), target_gets=1, decoded=0,
                            armed_callback_calls=1, first_deadline=first, callee_deadline=end,
                            public_effect=exposed[0].effect, prepare_effect=getattr(received, 'effect', None))))
                        rows.append((phase, received, exposed[0], error))
                raise wire.WireFailure('fence_blocked', 'none')
            with patch.object(wire, '_authenticate', side_effect=observe):
                self.blocked(session)
        self.assertEqual(len(rows), 6)
        for phase, received, exposed, error in rows:
            with self.subTest(phase=phase, effect=error.effect):
                self.assertIs(received, exposed)
                self.assertEqual((received.code, received.effect, received.release_id, received.asset),
                    (error.code, error.effect, error.release_id, error.asset))

    def test_actual_confirmed_read_receipt_cannot_issue_mutation_or_server_ownership(self):
        with ExecutorCases.session(self) as (session, tls, _):
            original_execute, original_failure = session._execute, session._failure
            original_factory, original_authorize = owned._operation_scope, wire._authorize
            factories, authorized, observed = [], [], []
            error = wire.WireFailure('cancelled', 'confirmed', release_id=100, asset=receipt())
            def factory(owner, op):
                factories.append(op)
                return original_factory(owner, op)
            def authorize(*args, **kwargs):
                authorized.append(args)
                return original_authorize(*args, **kwargs)
            def execute(op):
                if op.kind != 'ObserveFence': return original_execute(op)
                self.assertIs(op, session._transition.state.pending)
                self.assertIs(type(session._read_scope), owned._ReadScope)
                self.assertIsNone(session._request_scope)
                def caller(): raise error
                return session._api.get('/', deadline=session._deadline, check_active=caller)
            def failure(op, caught):
                result = original_failure(op, caught)
                observed.append((op, caught, result))
                return result
            with patch.object(session, '_execute', side_effect=execute), patch.object(
                    session, '_failure', side_effect=failure), patch.object(
                    owned, '_operation_scope', side_effect=factory), patch.object(
                    wire, '_authorize', side_effect=authorize):
                result = session.run_until_pause()
            self.assertEqual(len(observed), 1)
            op, caught, event = observed[0]
            self.assertEqual((event.effect, event.release_id, event.asset), ('none', None, None))
            self.assertEqual((result.state.outcome, result.state.release_id, result.state.mutated),
                ('blocked_no_effect', None, False))
            self.assertIsNone(result.state.pending)
            self.assertEqual(factories, [])
            self.assertEqual(authorized, [])
            self.assertEqual(ExecutorCases.mutations(tls), [])
            self.assertIsNone(session._request_scope)
            self.assertIsNone(session._read_scope)
            self.assertEqual((caught.code, caught.effect, caught.release_id, caught.asset),
                ('cancelled', 'confirmed', 100, error.asset))

    def test_actual_written_header_canonical_none_cannot_clear_owned_unknown(self):
        for close_failure in (False, True):
            with self.subTest(close_failure=close_failure), ExecutorCases.session(self) as (session, tls, _):
                original_send, original_close = ssl.SSLSocket.sendall, ssl.SSLSocket.close
                original_active, original_failure = session._check_active, session._failure
                actual_header, armed, observed, ready, calls = [], [False], [], threading.Event(), []
                error = wire.WireFailure('cancelled', 'unknown')
                error.effect = 'none'  # Valid-to-valid history cannot be recovered from fields.
                def send(sock, data, *args, **kwargs):
                    result = original_send(sock, data, *args, **kwargs)
                    if sock.server_hostname == wire.API and data.startswith(
                            ('POST ' + wire.ROOT + '/releases HTTP/').encode()):
                        scope, op = session._request_scope, session._inflight
                        self.assertIs(type(scope), owned._OperationScope)
                        self.assertTrue(scope._used)
                        self.assertIn(op.operation_id, session._attempted)
                        self.assertEqual(data, scope._snapshot._header)
                        self.assertIs(scope._snapshot._op, op)
                        self.assertIs(scope._owner, session._owner)
                        actual_header.append((scope, op, bytes(data), scope._deadline))
                    elif sock.server_hostname is None and data.startswith(b'HTTP/1.1 201'):
                        ready.set()
                    elif sock.server_hostname == wire.API and actual_header and data.startswith(b'{'):
                        self.assertTrue(ready.wait(1))
                        armed[0] = True
                    return result
                def active():
                    original_active()
                    if armed[0]:
                        calls.append(True)
                        raise error
                def close(sock, *args, **kwargs):
                    client = sock.server_hostname == wire.API
                    result = original_close(sock, *args, **kwargs)
                    if client and armed[0] and close_failure: raise error
                    return result
                def failure(op, caught):
                    result = original_failure(op, caught)
                    observed.append((op, caught, result))
                    return result
                with patch.object(ssl.SSLSocket, 'sendall', new=send), patch.object(
                        ssl.SSLSocket, 'close', new=close), patch.object(
                        session, '_check_active', side_effect=active), patch.object(
                        session, '_failure', side_effect=failure):
                    result = session.run_until_pause()
                self.assertEqual(len(actual_header), 1)
                scope, op, header, first = actual_header[0]
                self.assertTrue(scope._used and scope._retired)
                self.assertEqual(scope._deadline, first)
                self.assertEqual(calls, [True])
                self.assertEqual(len(observed), 1)
                self.assertEqual((observed[0][1].effect, observed[0][2].effect), ('unknown', 'unknown'))
                self.assertEqual((result.state.outcome, result.state.code), ('uncertain_remote_effect', 'cancelled'))
                self.assertIsNone(result.state.pending)
                self.assertIn(op.operation_id, session._attempted)
                self.assertEqual([r[0] for r in ExecutorCases.mutations(tls)], ['POST'])
                before = len(tls.requests)
                with self.assertRaises(wire.WireFailure) as denied:
                    session.run_until_pause()
                self.assertEqual((denied.exception.code, denied.exception.effect), ('invalid_request', 'none'))
                self.assertIs(session.transition, result)
                self.assertEqual(len(tls.requests), before)
                self.assertFalse(result.live_publication_verified)
                print(json.dumps(dict(scope='actual-header-sticky-unknown', header_bytes=len(header),
                    native_consumed=True, attempted=True, canonical_caller_effect=error.effect,
                    request_effect=observed[0][1].effect, core_effect=observed[0][2].effect,
                    target_posts=1, close_failure=close_failure, callback_calls=len(calls))))
