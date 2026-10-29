"""Actual native read lifetime over verified loopback TLS; no publication grant."""
import os
import threading
import time
import unittest
from unittest.mock import patch

import rc_publication_executor as executor
import rc_publication_github as wire
from rc_publication_request_cases import OwnedRequestCases


class OwnedReadCases(unittest.TestCase):
    session = OwnedRequestCases.session

    @staticmethod
    def delayed(response, seconds=0.7):
        status, headers, body = response
        header = (f'HTTP/1.1 {status} Fixture\r\nContent-Length: {len(body)}\r\n' +
                  ''.join(k + ': ' + str(v) + '\r\n' for k, v in headers.items()) + '\r\n').encode()
        return {'delay': seconds, 'raw': header + body}

    def test_01_observe_tag_cancel_stops_before_next_metadata(self):
        with self.session() as (session, tls, _):
            target = wire.ROOT + '/git/ref/tags/' + session._selection.subject.tag
            reached, observing = [], []
            original, observe = tls.route, wire.GitHub.observe
            def observation(api, *args, **kwargs):
                observing.append(True)
                return observe(api, *args, **kwargs)
            def route(method, path, headers, body):
                if path == target and observing:
                    reached.append(len(tls.requests) - 1)
                    session.cancel()
                return original(method, path, headers, body)
            tls.route = route
            with patch.object(wire.GitHub, 'observe', new=observation):
                result = session.run_until_pause()
            self.assertEqual(result.state.code, 'cancelled')
            self.assertEqual(len(reached), 1)
            self.assertEqual(tls.requests[reached[0] + 1:], [])
            self.assertEqual(OwnedRequestCases.mutations(tls), [])

    def test_02_observe_original_deadline_bounds_stalled_tag_tls(self):
        with self.session() as (session, tls, _):
            target = wire.ROOT + '/git/ref/tags/' + session._selection.subject.tag
            reached, observing = [], []
            original, observe = tls.route, wire.GitHub.observe
            def observation(api, *args, **kwargs):
                observing.append(True)
                session._deadline = time.monotonic() + 0.15
                return observe(api, *args, **kwargs)
            def route(method, path, headers, body):
                if path == target and observing:
                    reached.append(time.monotonic())
                    return self.delayed(tls._release(method, path, headers, body))
                return original(method, path, headers, body)
            tls.route = route
            with patch.object(wire.GitHub, 'observe', new=observation):
                result = session.run_until_pause()
            finished = time.monotonic()
            self.assertEqual(result.state.code, 'timeout')
            self.assertEqual(len(reached), 1)
            self.assertLess(finished - reached[0], 0.5)
            self.assertEqual(OwnedRequestCases.mutations(tls), [])

    def test_03_verify_metadata_cancel_stops_before_binary_read(self):
        with self.session() as (session, tls, _):
            target = wire.ROOT + '/releases/assets/200'
            reached = []
            original = tls.route
            def route(method, path, headers, body):
                if path == target and headers['accept'] != 'application/octet-stream':
                    reached.append(len(tls.requests) - 1)
                    session.cancel()
                return original(method, path, headers, body)
            tls.route = route
            result = session.run_until_pause()
            self.assertEqual((result.state.outcome, result.state.code), ('partial_draft', 'cancelled'))
            self.assertEqual(len(reached), 1)
            self.assertEqual(tls.requests[reached[0] + 1:], [])
            self.assertEqual(len(OwnedRequestCases.mutations(tls)), 2)

    def test_04_verify_original_deadline_bounds_stalled_binary_tls(self):
        with self.session() as (session, tls, _):
            target = wire.ROOT + '/releases/assets/200'
            reached = []
            original, execute = tls.route, session._execute
            def operation(op):
                if op.kind == 'VerifyAsset':
                    session._deadline = time.monotonic() + 0.15
                return execute(op)
            def route(method, path, headers, body):
                if path == target and headers['accept'] == 'application/octet-stream':
                    reached.append(time.monotonic())
                    return self.delayed(tls._release(method, path, headers, body))
                return original(method, path, headers, body)
            tls.route = route
            with patch.object(session, '_execute', side_effect=operation):
                result = session.run_until_pause()
            finished = time.monotonic()
            self.assertEqual((result.state.outcome, result.state.code), ('partial_draft', 'timeout'))
            self.assertEqual(len(reached), 1)
            self.assertLess(finished - reached[0], 0.5)
            self.assertEqual(len(OwnedRequestCases.mutations(tls)), 2)

    def test_05_noop_longer_caller_cannot_replace_native_cancel(self):
        with self.session() as (session, tls, _):
            target, reached = wire.ROOT + '/releases/assets/200', []
            original, execute = tls.route, session._execute
            def operation(op):
                if op.kind == 'VerifyAsset':
                    return session._api.verify_asset(op, deadline=time.monotonic() + 1000,
                                                     check_active=lambda: None)
                return execute(op)
            def route(method, path, headers, body):
                if path == target and headers['accept'] != 'application/octet-stream':
                    reached.append(len(tls.requests) - 1)
                    session.cancel()
                return original(method, path, headers, body)
            tls.route = route
            with patch.object(session, '_execute', side_effect=operation):
                result = session.run_until_pause()
            self.assertEqual((result.state.outcome, result.state.code), ('partial_draft', 'cancelled'))
            self.assertEqual(len(reached), 1)
            self.assertEqual(tls.requests[reached[0] + 1:], [])

    def test_06_first_native_controller_deadline_cannot_be_renewed_by_caller(self):
        with self.session() as (session, tls, _):
            target, reached = wire.ROOT + '/releases/assets/200', []
            original, execute = tls.route, session._execute
            budget = executor.OPERATION_SECONDS
            def route(method, path, headers, body):
                if method == 'POST' and path.startswith(wire.ROOT + '/releases/100/assets?'):
                    # The next real native operation issues its own short first
                    # deadline. No private ReadScope is built or rewritten here.
                    executor.OPERATION_SECONDS = 0.15
                if path == target and headers['accept'] == 'application/octet-stream':
                    reached.append(time.monotonic())
                    return self.delayed(tls._release(method, path, headers, body))
                return original(method, path, headers, body)
            def operation(op):
                if op.kind == 'VerifyAsset':
                    session._deadline = time.monotonic() + 1000
                    executor.OPERATION_SECONDS = budget
                    return session._api.verify_asset(op, deadline=session._deadline,
                                                     check_active=lambda: None)
                return execute(op)
            tls.route = route
            with patch.object(executor, 'OPERATION_SECONDS', budget), patch.object(
                    session, '_execute', side_effect=operation):
                result = session.run_until_pause()
            finished = time.monotonic()
            self.assertEqual((result.state.outcome, result.state.code), ('partial_draft', 'timeout'))
            self.assertEqual(len(reached), 1)
            self.assertLess(finished - reached[0], 0.5)

    def test_07_native_cancel_after_json_decode_cannot_return_observation(self):
        with self.session() as (session, tls, _):
            original, observe = wire._json, wire.GitHub.observe
            entered, decoded = [], []
            def observation(api, *args, **kwargs):
                entered.append(True)
                return observe(api, *args, **kwargs)
            def decode(raw):
                value = original(raw)
                if entered and type(value) is dict and value.get('ref') == 'refs/tags/' + session._selection.subject.tag:
                    decoded.append(True)
                    session.cancel()
                return value
            with patch.object(wire.GitHub, 'observe', new=observation), patch.object(wire, '_json', side_effect=decode):
                result = session.run_until_pause()
            self.assertEqual(result.state.code, 'cancelled')
            self.assertEqual(decoded, [True])
            self.assertEqual(OwnedRequestCases.mutations(tls), [])

    def test_08_anonymous_storage_redirect_keeps_native_cancel(self):
        with self.session() as (session, tls, _):
            target, reached = '/asset/200', []
            original = tls.route
            tls.redirects[200] = 'https://' + wire.STORAGE + target
            def route(method, path, headers, body):
                if path == target:
                    reached.append(len(tls.requests) - 1)
                    self.assertNotIn('authorization', headers)
                    session.cancel()
                return original(method, path, headers, body)
            tls.route = route
            result = session.run_until_pause()
            self.assertEqual((result.state.outcome, result.state.code), ('partial_draft', 'cancelled'))
            self.assertEqual(len(reached), 1)
            self.assertEqual(tls.requests[reached[0] + 1:], [])

    def test_09_native_paused_and_retired_read_cannot_fallback_standalone(self):
        with self.session() as (session, tls, _):
            scopes, execute, api = [], session._execute, session._api
            def operation(op):
                scopes.append(session._read_scope)
                return execute(op)
            with patch.object(session, '_execute', side_effect=operation):
                pause = session.run_until_pause()
            self.assertIsNone(session._read_scope)
            self.assertTrue(scopes and all(scope._retired for scope in scopes))
            count = len(tls.requests)
            for operation in (lambda: api.get('/', deadline=time.monotonic() + 1000, check_active=lambda: None),
                              lambda: scopes[0]._check(api)):
                with self.assertRaises(wire.WireFailure) as failure:
                    operation()
                self.assertEqual((failure.exception.code, failure.exception.effect), ('invalid_event', 'none'))
            self.assertEqual(len(tls.requests), count)
            self.assertIs(session.transition, pause)

    def test_10_native_thread_and_fork_copy_cannot_borrow_read_controller(self):
        with self.session() as (session, tls, _):
            rejected = []
            def authority(op, subject, *, request, scope):
                count = len(tls.requests)
                def foreign():
                    try:
                        session._api.get('/', deadline=time.monotonic() + 1000, check_active=lambda: None)
                    except wire.WireFailure as error:
                        rejected.append(('thread', error.code, error.effect))
                worker = threading.Thread(target=foreign)
                worker.start(); worker.join(3)
                self.assertFalse(worker.is_alive())
                read_fd, write_fd = os.pipe()
                child = os.fork()
                if child == 0:
                    os.close(read_fd)
                    value = b'unexpected-success'
                    try:
                        session._api.get('/', deadline=time.monotonic() + 1000, check_active=lambda: None)
                    except wire.WireFailure as error:
                        value = (error.code + ':' + error.effect).encode()
                    except BaseException:
                        value = b'unexpected-error'
                    os.write(write_fd, value)
                    os._exit(0)
                os.close(write_fd)
                try:
                    _, status = os.waitpid(child, 0)
                    self.assertEqual(status, 0)
                    self.assertEqual(os.read(read_fd, 128), b'invalid_event:none')
                finally:
                    os.close(read_fd)
                self.assertEqual(len(tls.requests), count)
                raise wire.WireFailure('denied', 'none')
            with patch.object(wire, '_authorize', side_effect=authority):
                result = session.run_until_pause()
            self.assertEqual(rejected, [('thread', 'invalid_event', 'none')])
            self.assertEqual(result.state.code, 'denied')
            self.assertEqual(OwnedRequestCases.mutations(tls), [])

    def test_11_native_prepare_noop_caller_cannot_replace_cancel(self):
        with self.session() as (session, tls, _):
            original, prepare, reached = tls.route, session._prepare, []
            def preparation():
                session._api.get('/', deadline=time.monotonic() + 1000, check_active=lambda: None)
                return prepare()
            def route(method, path, headers, body):
                if path == wire.ROOT:
                    reached.append(len(tls.requests) - 1)
                    session.cancel()
                return original(method, path, headers, body)
            tls.route = route
            with patch.object(session, '_prepare', side_effect=preparation):
                with self.assertRaises(wire.WireFailure) as failure:
                    session.run_until_pause()
            self.assertEqual((failure.exception.code, failure.exception.effect), ('cancelled', 'none'))
            self.assertEqual(len(reached), 1)
            self.assertEqual(tls.requests[reached[0] + 1:], [])
            self.assertIsNone(session._read_scope)
            self.assertEqual(OwnedRequestCases.mutations(tls), [])

    def test_12_read_socket_cleanup_cancel_cannot_start_binary(self):
        with self.session() as (session, tls, _):
            target, closed = (wire.ROOT + '/releases/assets/200').encode(), []
            def connection(host, timeout):
                sock = tls.connect(host, timeout)
                send, close, selected = sock.sendall, sock.close, []
                def sending(data):
                    if data.startswith(b'GET ' + target + b' ') and b'Accept: application/vnd.github+json\r\n' in data:
                        selected.append(True)
                    return send(data)
                def closing():
                    close()
                    if selected:
                        closed.append(len(tls.requests) - 1)
                        session.cancel()
                sock.sendall, sock.close = sending, closing
                return sock
            with patch.object(wire, '_connect', side_effect=connection):
                result = session.run_until_pause()
            self.assertEqual((result.state.outcome, result.state.code), ('partial_draft', 'cancelled'))
            self.assertEqual(len(closed), 1)
            self.assertEqual(tls.requests[closed[0] + 1:], [])

    def test_13_raw_get_native_rejection_precedes_external_callback(self):
        with self.session() as (session, tls, _):
            called, codes = [], []
            def authority(op, subject, *, request, scope):
                session._cancelled.set()
                try:
                    session._api._request('GET', wire.API, wire.ROOT,
                        deadline=time.monotonic() + 1000, check_active=lambda: called.append(True))
                except wire.WireFailure as error:
                    codes.append((error.code, error.effect))
                raise wire.WireFailure('cancelled', 'none')
            with patch.object(wire, '_authorize', side_effect=authority):
                result = session.run_until_pause()
            self.assertEqual(result.state.code, 'cancelled')
            self.assertEqual(codes, [('cancelled', 'none')])
            self.assertEqual(called, [])
            self.assertEqual(OwnedRequestCases.mutations(tls), [])

    def test_14_native_cancel_polls_while_binary_tls_response_is_stalled(self):
        with self.session() as (session, tls, _):
            target = wire.ROOT + '/releases/assets/200'
            original, reached, cancelled, workers = tls.route, [], [], []
            def route(method, path, headers, body):
                if path == target and headers['accept'] == 'application/octet-stream':
                    reached.append(time.monotonic())
                    def cancellation():
                        time.sleep(0.04)
                        session.cancel()
                        cancelled.append(time.monotonic())
                    worker = threading.Thread(target=cancellation)
                    workers.append(worker)
                    worker.start()
                    return self.delayed(tls._release(method, path, headers, body))
                return original(method, path, headers, body)
            tls.route = route
            result = session.run_until_pause()
            finished = time.monotonic()
            for worker in workers:
                worker.join(3)
                self.assertFalse(worker.is_alive())
            self.assertEqual((result.state.outcome, result.state.code), ('partial_draft', 'cancelled'))
            self.assertEqual(len(reached), 1)
            self.assertEqual(len(cancelled), 1)
            self.assertLess(finished - cancelled[0], 0.4)

    def test_15_recv_poll_retries_do_not_refresh_original_idle_deadline(self):
        with self.session() as (session, tls, _):
            target, reached, original = wire.ROOT + '/releases/assets/200', [], tls.route
            def route(method, path, headers, body):
                if path == target and headers['accept'] == 'application/octet-stream':
                    reached.append(time.monotonic())
                    return self.delayed(tls._release(method, path, headers, body))
                return original(method, path, headers, body)
            tls.route = route
            # Shorten this new fixture's original per-recv idle limit. The
            # unchanged production limit is still 15 seconds, never extended.
            with patch.object(wire, 'TIMEOUT', 0.2):
                result = session.run_until_pause()
            finished = time.monotonic()
            self.assertEqual((result.state.outcome, result.state.code), ('partial_draft', 'timeout'))
            self.assertEqual(len(reached), 1)
            self.assertLess(finished - reached[0], 0.5)

    def test_16_additional_caller_cancel_can_strengthen_native_read(self):
        with self.session() as (session, tls, _):
            target = wire.ROOT + '/releases/assets/200'
            extra, reached = threading.Event(), []
            original, execute = tls.route, session._execute
            def stricter():
                if extra.is_set():
                    raise wire.WireFailure('denied', 'none')
            def operation(op):
                if op.kind == 'VerifyAsset':
                    return session._api.verify_asset(op, deadline=session._deadline,
                                                     check_active=stricter)
                return execute(op)
            def route(method, path, headers, body):
                if path == target and headers['accept'] != 'application/octet-stream':
                    reached.append(len(tls.requests) - 1)
                    extra.set()
                return original(method, path, headers, body)
            tls.route = route
            with patch.object(session, '_execute', side_effect=operation):
                result = session.run_until_pause()
            self.assertEqual((result.state.outcome, result.state.code), ('partial_draft', 'denied'))
            self.assertFalse(session._cancelled.is_set())
            self.assertEqual(len(reached), 1)
            self.assertEqual(tls.requests[reached[0] + 1:], [])

    def test_17_fork_copy_cannot_pass_native_mutation_owner_check(self):
        with self.session() as (session, tls, _):
            observed = []
            def authority(op, subject, *, request, scope):
                read_fd, write_fd = os.pipe()
                child = os.fork()
                if child == 0:
                    os.close(read_fd)
                    value = b'unexpected-success'
                    try:
                        scope._check(session._api, op)
                    except wire.WireFailure as error:
                        value = (error.code + ':' + error.effect).encode()
                    except BaseException:
                        value = b'unexpected-error'
                    os.write(write_fd, value)
                    os._exit(0)
                os.close(write_fd)
                try:
                    _, status = os.waitpid(child, 0)
                    self.assertEqual(status, 0)
                    observed.append(os.read(read_fd, 128))
                finally:
                    os.close(read_fd)
                raise wire.WireFailure('denied', 'none')
            with patch.object(wire, '_authorize', side_effect=authority):
                result = session.run_until_pause()
            self.assertEqual(result.state.code, 'denied')
            self.assertEqual(observed, [b'invalid_event:none'])
            self.assertEqual(OwnedRequestCases.mutations(tls), [])
