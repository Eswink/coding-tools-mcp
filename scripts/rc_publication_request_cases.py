"""Owned request negatives and native verified loopback bytes; no live grants."""
from contextlib import contextmanager
from copy import copy, deepcopy
from dataclasses import replace
import io
import json
import os
import pickle
import tempfile
import time
import unittest
from unittest.mock import patch

import rc_publication_contract as core
import rc_publication_executor as executor
import rc_publication_github as wire
import rc_publication_request as owned
import rc_publication_executor_cases as fixture_cases
from rc_publication_https_fixture import HTTPSFixture
from rc_publication_stage import Selection


class OwnedRequestCases(unittest.TestCase):
    @contextmanager
    def session(self):
        # This trusted helper owns actual staged artifacts and verified loopback
        # TLS. Its fixed authorities context is never a production API.
        with fixture_cases.ExecutorCases().session() as value:
            yield value

    @staticmethod
    def mutations(tls):
        return fixture_cases.ExecutorCases.mutations(tls)

    @staticmethod
    def inert_session():
        fixture = HTTPSFixture()  # no socket/key/credential acquisition
        selected = Selection(fixture.subject, 41, 1, '1' * 64)
        return executor.PublisherSession('.', selected, 'synthetic-owned-token', temporary_parent='.')

    def rejected(self, operation, code=None):
        with self.assertRaises(wire.WireFailure) as caught:
            operation()
        self.assertEqual(caught.exception.effect, 'none')
        if code is not None:
            self.assertEqual(caught.exception.code, code)
        self.assertIsNone(caught.exception.release_id)
        self.assertIsNone(caught.exception.asset)
        self.assertNotIn('synthetic-owned-token', str(caught.exception))
        return caught.exception

    def test_01_supported_credential_api_and_selection_substitution_rejects(self):
        session = self.inert_session()
        self.addCleanup(session.close)
        api, credential = session._api, session._api._credential
        for target, name, value in ((api, 'token', 'replacement'), (api, 'selection', {}),
                                    (session, '_api', api), (credential, '_token', 'replacement')):
            with self.subTest(field=name), self.assertRaises(AttributeError):
                setattr(target, name, value)
        with self.assertRaises(AttributeError):
            api.selection.consumer_artifact_id = 99
        self.assertIs(session._selection, api.selection)
        self.assertNotIn('synthetic-owned-token', repr(credential))
        for operation in (lambda: copy(credential), lambda: deepcopy(credential),
                          lambda: pickle.dumps(credential), lambda: json.dumps(credential)):
            with self.assertRaises(TypeError):
                operation()

    def test_02_cross_client_session_operation_and_equal_copy_rejects(self):
        with self.session() as (session, tls, _):
            foreign = self.inert_session()
            self.addCleanup(foreign.close)
            seen = []
            def authority(op, subject, *, request, scope):
                seen.append(op)
                self.rejected(lambda: foreign._api.create_draft(op, scope=scope,
                    before_write=foreign._before_write, check_active=lambda: None))
                self.rejected(lambda: scope._check(session._api, replace(op)))
                for value in (scope, request, session._owner):
                    with self.assertRaises(TypeError):
                        copy(value)
                raise wire.WireFailure('denied', 'none')
            with patch.object(wire, '_authorize', side_effect=authority):
                result = session.run_until_pause()
            self.assertEqual(len(seen), 1)
            self.assertEqual(result.state.code, 'denied')
            self.assertEqual(self.mutations(tls), [])

    def test_03_dictionary_callback_and_noop_write_control_cannot_mint(self):
        with self.session() as (session, tls, _):
            execute = session._execute
            def operation(op):
                if op.kind == 'CreateDraft':
                    for scope in (None, {}, {'passed': True}, lambda: True):
                        self.rejected(lambda: session._api.create_draft(op, scope=scope,
                            before_write=lambda: None, check_active=lambda: None))
                    return session._api.create_draft(op, scope=session._request_scope,
                        before_write=lambda: None, check_active=lambda: None)
                return execute(op)
            with patch.object(session, '_execute', side_effect=operation), patch.object(wire, '_authorize') as grant:
                result = session.run_until_pause()
            grant.assert_not_called()
            self.assertEqual(result.state.outcome, 'blocked_no_effect')
            self.assertEqual(self.mutations(tls), [])
            self.rejected(lambda: owned._CredentialOwner(object(), 'synthetic', {}, session))

    def test_04_snapshot_header_url_body_and_identity_are_not_importable(self):
        with self.session() as (session, tls, _):
            observed = []
            def authority(op, subject, *, request, scope):
                observed.append(request)
                self.assertIs(request._client, session._api)
                self.assertIs(request._credential, session._api._credential)
                self.assertIs(request._scope, scope)
                self.assertEqual(request._method, 'POST')
                self.assertEqual(request._host, wire.API)
                self.assertEqual(request._path, wire.ROOT + '/releases')
                expected = {'tag_name': subject.tag, 'draft': True, 'prerelease': True,
                            'make_latest': 'false', 'generate_release_notes': False}
                self.assertEqual(json.loads(request._body), expected)
                for field in ('_header', '_body', '_host', '_path', '_credential', '_scope'):
                    with self.subTest(field=field), self.assertRaises(AttributeError):
                        setattr(request, field, b'imported')
                for method, host, path, body in (('DELETE', wire.API, request._path, b''),
                        ('POST', 'evil.invalid', request._path, request._body),
                        ('POST', wire.API, request._path + '?foreign=1', request._body),
                        ('POST', wire.API, request._path, b'{}')):
                    self.rejected(lambda: session._api._request(method, host, path, body=body,
                        op=op, scope=scope, before_write=session._before_write, check_active=lambda: None))
                raise wire.WireFailure('denied', 'none')
            with patch.object(wire, '_authorize', side_effect=authority):
                session.run_until_pause()
            self.assertEqual(len(observed), 1)
            self.assertEqual(self.mutations(tls), [])

    def test_05_foreign_stream_offset_and_fresh_file_drift_reject_before_upload(self):
        # Native CreateDraft succeeds locally; no UploadAsset byte is attempted.
        for fault in ('foreign', 'offset', 'bytes'):
            with self.subTest(fault=fault), self.session() as (session, tls, _):
                execute = session._execute
                def operation(op):
                    if op.kind == 'UploadAsset' and fault == 'foreign':
                        return session._api.upload_asset(op, io.BytesIO(b'foreign'),
                            scope=session._request_scope, before_write=session._before_write,
                            check_active=lambda: None)
                    if op.kind == 'UploadAsset' and fault == 'offset':
                        stream = session._stage.stream(op.asset_ordinal)
                        stream.seek(1)
                        return session._api.upload_asset(op, stream, scope=session._request_scope,
                            before_write=session._before_write, check_active=lambda: None)
                    return execute(op)
                def authority(op, subject, *, request, scope):
                    if op.kind == 'UploadAsset' and fault == 'bytes':
                        path = session._stage._output.path / op.asset.name
                        with path.open('r+b') as stream:
                            first = stream.read(1)
                            stream.seek(0)
                            stream.write(bytes([first[0] ^ 1]))
                            stream.flush()
                            os.fsync(stream.fileno())
                with patch.object(session, '_execute', side_effect=operation), patch.object(wire, '_authorize', side_effect=authority):
                    result = session.run_until_pause()
                self.assertEqual(result.state.outcome, 'partial_draft')
                self.assertEqual(len(self.mutations(tls)), 1)
                self.assertEqual(session._attempted, {1, 2, 3, 4})

    def test_06_native_cancel_and_expiry_survive_noop_caller(self):
        for cancelled in (True, False):
            with self.subTest(cancelled=cancelled), self.session() as (session, tls, _):
                def authority(op, subject, *, request, scope):
                    # A per-instance no-op is not the fixed owned native check.
                    session._check_active = lambda: None
                    session.cancel() if cancelled else setattr(session, '_deadline', 0)
                with patch.object(wire, '_authorize', side_effect=authority):
                    result = session.run_until_pause()
                self.assertEqual(result.state.code, 'cancelled' if cancelled else 'timeout')
                self.assertEqual(result.state.outcome, 'blocked_no_effect')
                self.assertEqual(self.mutations(tls), [])

    def test_07_replay_reentrancy_and_duplicate_snapshots_reject(self):
        with self.session() as (session, tls, _):
            captured = []
            def authority(op, subject, *, request, scope):
                captured.append((op, request, scope))
                self.rejected(session.run_until_pause, 'invalid_event')
                self.rejected(lambda: session._api.create_draft(op, scope=scope,
                    before_write=session._before_write, check_active=lambda: None), 'invalid_event')
                raise wire.WireFailure('denied', 'none')
            with patch.object(wire, '_authorize', side_effect=authority):
                session.run_until_pause()
            op, request, scope = captured[0]
            self.rejected(lambda: scope._consume(request))
            self.rejected(lambda: request._check(request._client))
            self.assertEqual(self.mutations(tls), [])

    def test_08_pause_dispose_import_and_deadline_renewal_do_not_reuse_scope(self):
        with self.session() as (session, tls, _):
            captured = []
            def authority(op, subject, *, request, scope):
                captured.append((op, request, scope))
                if op.kind == 'CreateDraft':
                    original = scope._deadline
                    session._deadline = original + 1000
                    self.assertLessEqual(request._deadline, original)
            with patch.object(wire, '_authorize', side_effect=authority):
                pause = session.run_until_pause()
            self.assertIsInstance(pause.action, core.AwaitPublishRequest)
            self.assertIsNone(session._deadline)
            self.assertIsNone(session._request_scope)
            self.assertEqual(len({id(scope) for _, _, scope in captured}), 7)
            for op, request, scope in captured:
                self.rejected(lambda: scope._check(session._api, op))
                for operation in (lambda: pickle.dumps(request), lambda: deepcopy(scope)):
                    with self.assertRaises(TypeError):
                        operation()
            api = session._api
            session.close()
            self.assertIsNone(session._api)
            self.rejected(lambda: captured[0][1]._check(api))
            self.assertEqual(len(self.mutations(tls)), 7)

    def test_09_wrong_tls_and_fresh_missing_grant_never_send_mutation(self):
        with self.session() as (session, tls, _):
            connect = tls.connect
            def wrong(host, timeout):
                socket = connect(host, timeout)
                socket._owned_wrong_tls = True
                socket.context.check_hostname = False
                return socket
            execute = session._execute
            def operation(op):
                if op.kind == 'CreateDraft':
                    with patch.object(wire, '_connect', side_effect=wrong):
                        return execute(op)
                return execute(op)
            with patch.object(session, '_execute', side_effect=operation):
                result = session.run_until_pause()
            self.assertEqual(result.state.code, 'denied')
            self.assertEqual(self.mutations(tls), [])
        with self.session() as (session, tls, _):
            with patch.object(wire, '_authorize', side_effect=lambda *args, **kwargs:
                              (_ for _ in ()).throw(wire.WireFailure('denied', 'none'))):
                result = session.run_until_pause()
            self.assertEqual(result.state.code, 'denied')
            self.assertEqual(self.mutations(tls), [])

    def test_10_three_production_hard_rejects_and_snapshot_safe_errors_stay_closed(self):
        session = self.inert_session()
        self.addCleanup(session.close)
        subject = session._selection.subject
        self.rejected(lambda: wire._remote_constraint(subject), 'fence_blocked')
        self.rejected(lambda: wire._authenticated_latest_absence(session._selection), 'fence_blocked')
        self.rejected(lambda: wire._authorize(None, subject, request=None, scope={}), 'denied')
        import rc_consumer_snapshot as snapshot
        from rc_consumer_io import ConsumerError
        with self.assertRaises(ConsumerError):
            snapshot._call(None, None)

    def test_native_owned_loopback_exact_bytes_and_one_attempt_each(self):
        with self.session() as (session, tls, fixture):
            checked = []
            def authority(op, subject, *, request, scope):
                request._check(session._api)
                checked.append((op.operation_id, request._header, request._body, scope))
                self.assertIs(scope._owner, session._owner)
                self.assertIs(request._credential, session._api._credential)
            with patch.object(wire, '_authorize', side_effect=authority):
                session.run_until_pause()
                final = session.request_publish(fixture_cases.ExecutorCases.request(session))
            self.assertEqual(final.state.outcome, 'modeled_verified')
            self.assertFalse(final.live_publication_verified)
            self.assertEqual([row[0] for row in checked], [2, 5, 8, 11, 14, 17, 20, 24])
            mutations = self.mutations(tls)
            self.assertEqual(len(mutations), 8)
            for (_, header, body, _), (method, path, headers, actual) in zip(checked, mutations):
                self.assertTrue(header.startswith((method + ' ' + path + ' HTTP/1.1\r\n').encode()))
                self.assertIn(('Authorization: ' + headers['authorization'] + '\r\n').encode(), header)
                self.assertEqual(headers['authorization'], 'Bearer fixture-token')
                if '?name=' not in path:
                    self.assertEqual(actual, body)
            self.assertEqual({row[0]['name']: row[1] for row in tls.assets.values()}, fixture.payloads)
            self.assertEqual(session._attempted, set(range(1, 26)))

    def test_post_dispatch_stream_drift_is_terminal_unknown_no_retry(self):
        sent, headers = [], []
        with self.session() as (session, tls, _):
            connect = tls.connect
            def connection(host, timeout):
                socket = connect(host, timeout)
                send = socket.sendall
                receipt = None
                def sending(data):
                    nonlocal receipt
                    if data.startswith(b'POST '):
                        scope, op = session._request_scope, session._inflight
                        self.assertIs(type(scope), owned._OperationScope)
                        request = scope._snapshot
                        self.assertIs(type(request), owned._RequestSnapshot)
                        self.assertIs(scope._owner, session._owner)
                        self.assertIs(scope._owner._session, session)
                        self.assertIs(scope._owner._client, session._api)
                        self.assertIs(request._scope, scope)
                        self.assertIs(request._client, session._api)
                        self.assertIs(request._credential, session._api._credential)
                        self.assertIs(request._op, op)
                        self.assertIs(session.transition.state.pending, op)
                        self.assertIs(type(session._read_scope), owned._ReadScope)
                        self.assertIs(session._read_scope._owner, session._owner)
                        self.assertIs(session._read_scope._op, op)
                        self.assertEqual(request._method, 'POST')
                        self.assertEqual(data, request._header)
                        self.assertLessEqual(request._deadline,
                                             min(scope._deadline, session._deadline))
                        receipt = dict(request=request, scope=scope,
                                       read_scope=session._read_scope, body=bytearray())
                    if data.startswith(b'POST ') and b'/assets?' in data:
                        stream = session._stage._handles[0]
                        original = stream.read
                        def altered(size=-1):
                            chunk = original(size)
                            return bytes([chunk[0] ^ 1]) + chunk[1:] if chunk else chunk
                        stream.read = altered
                    value = send(data)
                    if data.startswith((b'GET ', b'POST ', b'PATCH ', b'DELETE ')):
                        headers.append(data)
                    if receipt is not None:
                        if data.startswith(b'POST '):
                            self.assertTrue(receipt['scope']._used)
                            self.assertIn(receipt['request']._op.operation_id, session._attempted)
                            sent.append(receipt)
                        else:
                            receipt['body'].extend(data)
                    return value
                socket.sendall = sending
                return socket
            with patch.object(wire, '_connect', side_effect=connection):
                result = session.run_until_pause()
                self.assertEqual(result.state.outcome, 'uncertain_remote_effect')
                self.assertEqual(len(sent), 2)
                self.assertEqual([row['request']._op.kind for row in sent],
                                 ['CreateDraft', 'UploadAsset'])
                self.assertEqual([row['request']._op.operation_id for row in sent], [2, 5])
                count = len(headers)
                self.rejected(session.run_until_pause)
                self.assertEqual(len(headers), count)
                self.assertEqual(len(sent), 2)
        # The original fixture owns the existing join(3); no additional wait
        # is introduced to make its asynchronous server receipt observable.
        self.assertFalse(tls.thread.is_alive())
        self.assertTrue(all(not thread.is_alive() for thread in tls._threads))
        self.assertEqual(len(self.mutations(tls)), 2)
        observed = self.mutations(tls)
        proof = []
        for row, receipt in zip(observed, sent):
            request = receipt['request']
            lines = request._header.decode('ascii').split('\r\n')
            expected_headers = dict((name.lower(), value.strip()) for name, value in
                (line.split(':', 1) for line in lines[1:] if line))
            expected = (request._method, request._path, expected_headers, bytes(receipt['body']))
            proof.append(dict(kind=request._op.kind, method=row[0],
                path_matches=row[1] == request._path, headers_match=row[2] == expected_headers,
                server_body_bytes=len(row[3]), successful_client_body_bytes=len(receipt['body']),
                complete_body_matches=row[3] == bytes(receipt['body']),
                body_delivery='matched' if row[3] == bytes(receipt['body']) else 'UNPROVEN'))
            self.assertTrue(receipt['scope']._retired and receipt['read_scope']._retired)
            self.assertTrue(row[:3] == expected[:3], 'closed server header differs from native snapshot')
        print('POST_DRIFT_HARNESS ' + json.dumps(dict(server_rows=len(observed),
            successful_native_POSTs=len(sent), no_new_headers_after_terminal_rerun=True,
            all_server_threads_stopped=True, rows=proof), sort_keys=True))
        # Complete-body delivery is not proven by this terminal UNKNOWN case.
        # The positive exact-bytes case retains its full-body assertions.
        self.assertEqual(len(self.mutations(tls)), 2)

    def test_fresh_authorizer_cannot_replace_credential_client_or_encoded_bytes(self):
        with self.session() as (session, tls, _):
            checked = []
            def authority(op, subject, *, request, scope):
                checked.append(op.operation_id)
                for target, field in ((session._api, 'token'), (session._api, 'selection'),
                        (session, '_api'), (request, '_header'), (request, '_body')):
                    with self.subTest(field=field), self.assertRaises(AttributeError):
                        setattr(target, field, object())
                request._check(session._api)
                self.assertIs(request._credential, scope._owner._credential)
                raise wire.WireFailure('denied', 'none')
            with patch.object(wire, '_authorize', side_effect=authority):
                result = session.run_until_pause()
            self.assertEqual(checked, [2])
            self.assertEqual(result.state.outcome, 'blocked_no_effect')
            self.assertEqual(self.mutations(tls), [])

    def test_actual_other_thread_cannot_dispatch_or_enter_native_loop(self):
        import threading
        with self.session() as (session, tls, _):
            results = []
            def authority(op, subject, *, request, scope):
                def other_thread():
                    operations = (lambda: session._api.create_draft(op, scope=scope,
                        before_write=session._before_write, check_active=lambda: None), session.run_until_pause)
                    for operation in operations:
                        try:
                            operation()
                        except wire.WireFailure as error:
                            results.append((error.code, error.effect))
                        else:
                            results.append(('unexpected_success', 'unknown'))
                thread = threading.Thread(target=other_thread)
                thread.start()
                thread.join(5)
                self.assertFalse(thread.is_alive())
                raise wire.WireFailure('denied', 'none')
            with patch.object(wire, '_authorize', side_effect=authority):
                result = session.run_until_pause()
            self.assertEqual(results, [('invalid_request', 'none'), ('invalid_event', 'none')])
            self.assertEqual(result.state.outcome, 'blocked_no_effect')
            self.assertEqual(self.mutations(tls), [])

    def test_confirmed_native_mutation_cleanup_failure_keeps_release_identity(self):
        with self.session() as (session, tls, _):
            def connection(host, timeout):
                socket = tls.connect(host, timeout)
                send, close, dispatched = socket.sendall, socket.close, []
                def sending(data):
                    if data.startswith(b'POST '):
                        dispatched.append(True)
                    return send(data)
                def closing():
                    close()
                    if dispatched:
                        raise OSError('synthetic close failure')
                socket.sendall, socket.close = sending, closing
                return socket
            with patch.object(wire, '_connect', side_effect=connection):
                result = session.run_until_pause()
            self.assertEqual((result.state.outcome, result.state.release_id, result.state.code),
                             ('partial_draft', 100, 'adapter_error'))
            self.assertEqual(len(self.mutations(tls)), 1)
            self.assertEqual(session._attempted, {1, 2})

    def test_mutation_redirect_after_attempt_is_unknown_and_never_followed(self):
        with self.session() as (session, tls, _):
            target = wire.ROOT + '/releases'
            tls.routes['POST', target] = (302, {'Location': 'https://api.github.com/foreign'}, b'{}')
            result = session.run_until_pause()
            self.assertEqual(result.state.outcome, 'uncertain_remote_effect')
            self.assertEqual(len(self.mutations(tls)), 1)
            self.assertFalse(any(row[1] == '/foreign' for row in tls.requests))
            self.rejected(session.run_until_pause)
            self.assertEqual(len(self.mutations(tls)), 1)


if __name__ == '__main__':
    unittest.main()
