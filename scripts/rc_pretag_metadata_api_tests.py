"""Hermetic network-wire and supervision tests. Never contact GitHub.

Child bootstrap patches exist only here; production has no host, TLS or test
mode escape hatch. All credentials and response bytes in this suite are fake.
"""
from __future__ import annotations

import base64
import contextlib
import io
import json
import os
from pathlib import Path
import socket
import ssl
import struct
import subprocess
import sys
import time
import unittest
import zlib
from unittest.mock import patch

import rc_pretag_metadata_api as api
import rc_pretag_metadata_worker as worker

TOKEN = 'synthetic-token-DO-NOT-LOG'
SHA = 'a' * 40
REAL_POPEN = subprocess.Popen
WORKER = str(Path(worker.__file__).resolve())


def frame(value):
    raw = json.dumps(value, separators=(',', ':')).encode()
    return struct.pack('!I', len(raw)) + raw


def response(body=b'{}', status=200, headers=b''):
    return (b'HTTP/1.1 ' + str(status).encode() + b' Synthetic\r\n'
            + b'Content-Type: application/json\r\n' + headers
            + b'Content-Length: ' + str(len(body)).encode() + b'\r\n\r\n' + body)


@contextlib.contextmanager
def child(code):
    """Replace only process bootstrap and retain the real pipes/process owner."""
    processes = []

    def start(args, **kwargs):
        assert args == [sys.executable, '-I', '-S', str(api.WORKER_PATH)]
        assert kwargs['shell'] is False and kwargs['close_fds'] is True
        assert kwargs['env'] == {'LC_ALL': 'C', 'LANG': 'C'}
        assert kwargs['stderr'] == subprocess.DEVNULL
        assert TOKEN not in repr(args) + repr(kwargs)
        process = REAL_POPEN([sys.executable, '-I', '-S', '-c', code], **kwargs)
        processes.append(process)
        return process

    try:
        with patch.object(api.subprocess, 'Popen', side_effect=start):
            yield processes
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=2)
            for pipe in (process.stdin, process.stdout):
                pipe.close()


def wire_bootstrap(wire, hold=0, stage=None):
    # A socketpair has no host, DNS, proxy or external network access.
    return f'''
import base64, http.client, runpy, socket, threading, time, zlib
namespace = runpy.run_path({WORKER!r})
original = http.client.HTTPSConnection
class FixtureConnection(original):
    def __init__(self, host, *, timeout, context):
        assert host == 'api.github.com' and context.check_hostname
        http.client.HTTPConnection.__init__(self, host, timeout=timeout)
    def connect(self):
        if {stage!r} in ('dns', 'connect', 'tls'):
            time.sleep(30)
        local, remote = socket.socketpair()
        self.sock = local
        def serve():
            request = b''
            while b'\\r\\n\\r\\n' not in request:
                request += remote.recv(4096)
            if not request.startswith(b'GET /repos/Eswink/coding-tools-mcp HTTP/1.1'):
                raise AssertionError('unexpected route')
            if b'Authorization: Bearer ' + {TOKEN.encode()!r} not in request:
                raise AssertionError('missing synthetic bearer')
            remote.sendall(zlib.decompress(base64.b64decode({base64.b64encode(zlib.compress(wire))!r})))
            time.sleep({hold!r})
            remote.close()
        threading.Thread(target=serve, daemon=True).start()
    def close(self):
        if {stage!r} == 'close':
            time.sleep(30)
        super().close()
http.client.HTTPSConnection = FixtureConnection
namespace['main']()
'''


class Assertions(unittest.TestCase):
    def assertCode(self, code, call, *args, **kwargs):
        with self.assertRaises(api.MetadataAPIError) as caught:
            call(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(str(caught.exception), code)
        self.assertNotIn(TOKEN, str(caught.exception))


class RoutesAndParsing(Assertions):
    def test_all_typed_routes(self):
        routes = [
            ('repository', {}, worker.BASE),
            ('ref', {'branch': 'refs/heads/feat/rc-pretag-metadata-1dfe'},
             worker.BASE + '/git/ref/heads/feat/rc-pretag-metadata-1dfe'),
            ('commit', {'sha': SHA}, worker.BASE + '/git/commits/' + SHA),
            ('tree', {'sha': SHA}, worker.BASE + '/git/trees/' + SHA),
            ('workflow', {'role': 'integration'}, worker.BASE + '/actions/workflows/dot-rc-integration.yml'),
            ('workflow', {'role': 'final'}, worker.BASE + '/actions/workflows/final-rc-packages.yml'),
            ('runs', {'workflow_id': 2, 'sha': SHA, 'page': 3}, worker.BASE
             + '/actions/workflows/2/runs?head_sha=' + SHA + '&per_page=100&page=3'),
            ('run', {'run_id': 3}, worker.BASE + '/actions/runs/3'),
            ('jobs', {'run_id': 3, 'attempt': 2, 'page': 1}, worker.BASE
             + '/actions/runs/3/attempts/2/jobs?per_page=100&page=1'),
            ('pr', {}, worker.BASE + '/pulls/36'),
            ('reviews', {'page': 1}, worker.BASE + '/pulls/36/reviews?per_page=100&page=1'),
            ('commits', {'page': 1}, worker.BASE + '/pulls/36/commits?per_page=100&page=1'),
        ]
        for operation, arguments, expected in routes:
            with self.subTest(operation=operation, arguments=arguments):
                self.assertEqual(worker.route(operation, arguments), expected)

    def test_routes_reject_before_spawn(self):
        cases = [('GET', {}), ('repository', {'host': 'evil.example'}),
                 ('pr', {'number': 37}), ('run', {'run_id': True}),
                 ('run', {'run_id': 0}), ('run', {'run_id': 2**63}),
                 ('runs', {'workflow_id': 1, 'sha': SHA.upper(), 'page': 1}),
                 ('reviews', {'page': 11}), ('workflow', {'role': 'pretag'})]
        for branch in ['refs/tags/v1', 'refs/heads/main', 'refs/heads/release/full-rc-candidate-x..y',
                       'refs/heads/release/full-rc-candidate-x.', 'refs/heads/feat/rc-pretag-metadata-1dfe%2f',
                       'refs/heads/release/full-rc-candidate-x?x=1', 'https://evil.example']:
            cases.append(('ref', {'branch': branch}))
        with patch.object(api.subprocess, 'Popen') as spawn:
            client = api.MetadataGitHub(TOKEN)
            for operation, arguments in cases:
                with self.subTest(operation=operation, arguments=arguments):
                    with self.assertRaises(api.MetadataAPIError):
                        client.get(operation, **arguments)
            self.assertEqual(client.request_count, 0)
            spawn.assert_not_called()
            client.close()

    def test_token_validation_and_fixed_errors(self):
        for token in [None, '', 'a b', 'a\nsecret', '\x7f', '\u0100', 'a' * 4097]:
            self.assertCode('invalid_token', api.MetadataGitHub, token)
        self.assertCode('worker_failed', worker.require, False, TOKEN)
        client = api.MetadataGitHub('a' * 4096)
        with self.assertRaises(AttributeError):
            client.channel = 'authenticated'
        client.close()

    def test_strict_json_adversaries(self):
        cases = [(b'{"x":1,"x":2}', 'duplicate_json_key'), (b'{"x":NaN}', 'nonfinite_json'),
                 (b'{"x":1e999}', 'nonfinite_json'), (b'{"x":9223372036854775808}', 'json_integer_limit'),
                 (b'{"x":"\\ud800"}', 'json_string_limit'), (b'\xff', 'invalid_json'),
                 (b'{} {}', 'invalid_json'), (b'null', 'invalid_response_shape'),
                 (json.dumps({'x': 'x' * 65537}).encode(), 'json_string_limit'),
                 (json.dumps({'x': [0] * 1001}).encode(), 'json_array_limit'),
                 (json.dumps({str(i): 0 for i in range(129)}).encode(), 'json_object_limit'),
                 (b'[' * 18 + b'0' + b']' * 18, 'json_depth_limit'),
                 (b' ' * (worker.MAX_BODY + 1), 'response_limit')]
        for raw, code in cases:
            with self.subTest(code=code):
                self.assertCode(code, worker.parse_json, raw)
        self.assertEqual(worker.parse_json(b'{"x":9223372036854775807}'), {'x': 2**63 - 1})
        self.assertEqual(len(worker.parse_json(json.dumps([0] * 1000).encode())), 1000)
        self.assertEqual(len(worker.parse_json(json.dumps({'body': 'x' * 65536}).encode())['body']), 65536)
        self.assertEqual(len(worker.parse_json(json.dumps({'body': 'x' * 65536}).encode(),
                                               response=False)['body']), 65536)
        self.assertEqual(worker.parse_json(b'[' * 16 + b'0' + b']' * 16)[0][0][0],
                         json.loads(b'[' * 13 + b'0' + b']' * 13))

    def test_canonical_link_relations(self):
        link = '<' + worker.ORIGIN + worker.route('reviews', {'page': 2}) + '>; rel="next"'
        self.assertEqual(worker.link_relations('reviews', {'page': 1}, link), {'next': 2})
        for bad in [link.replace('api.github.com', 'evil.example'), link + ', ' + link,
                    link.replace('page=2', 'page=3'), link.replace('page=2', 'page=02'),
                    link.replace('per_page=100&page=2', 'page=2&per_page=100'),
                    link.replace('/reviews?', '/commits?'), link.replace('https:', 'http:'),
                    link.replace('api.github.com', 'api.github.com@evil.example'),
                    link + '\r\n', link.replace('page=2', 'page=11')]:
            self.assertCode('invalid_link', worker.link_relations, 'reviews', {'page': 1}, bad)


class WireTests(Assertions):
    def run_wire(self, wire, expected=None, **kwargs):
        with child(wire_bootstrap(wire, **kwargs)) as processes:
            with api.MetadataGitHub(TOKEN) as client:
                if expected:
                    self.assertCode(expected, client.get, 'repository')
                    result = None
                else:
                    result = client.get('repository')
                self.assertEqual(client.request_count, 1)
            self.assertIsNotNone(processes[0].poll())
            self.assertTrue(processes[0].stdin.closed and processes[0].stdout.closed)
            return result

    def test_actual_worker_success_and_utf8(self):
        result = self.run_wire(response('{"id":1360355522,"name":"é"}'.encode()))
        self.assertEqual(result.value, {'id': 1360355522, 'name': 'é'})
        self.assertEqual(result.byte_count, len('{"id":1360355522,"name":"é"}'.encode()))

    def test_large_bounded_ignored_values_cross_real_worker_ipc(self):
        for text in ('x' * 6362, '\"' * 65536):
            body = json.dumps({'body': text}).encode()
            self.assertLess(len(body), worker.MAX_BODY)
            result = self.run_wire(response(body))
            self.assertEqual(result.value['body'], text)
            self.assertLess(len(frame({'value': result.value})), worker.MAX_FRAME)
        self.run_wire(response(json.dumps({'body': 'x' * 65537}).encode()), 'json_string_limit')

    def test_status_no_retry_or_redirect(self):
        statuses = {301: 'redirect_rejected', 302: 'redirect_rejected', 307: 'redirect_rejected',
                    308: 'redirect_rejected', 401: 'unauthorized', 403: 'forbidden',
                    404: 'not_found_or_not_visible', 429: 'rate_limited',
                    500: 'server_error', 503: 'server_error', 201: 'unexpected_status'}
        for status, code in statuses.items():
            with self.subTest(status=status):
                self.run_wire(response(TOKEN.encode(), status, b'Location: https://evil.example\r\n'), code)

    def test_wire_header_and_body_rejections(self):
        for headers in [b'Content-Length: 2\r\n', b'Transfer-Encoding: chunked\r\n',
                        b'Content-Encoding: gzip\r\n', b'Link: <https://evil.example>; rel="next"\r\n',
                        b'X-Synthetic: ' + b'x' * 4097 + b'\r\n']:
            with self.subTest(headers=headers[:40]):
                code = 'invalid_link' if headers.startswith(b'Link:') else 'invalid_headers'
                self.run_wire(response(headers=headers), code)
        self.run_wire(response(b'{"x":1,"x":2}'), 'duplicate_json_key')
        self.run_wire(response(b'[]'), 'invalid_response_shape')
        self.run_wire(response(b'x' * (worker.MAX_BODY + 1)), 'response_limit')
        self.run_wire(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n'
                      b'Transfer-Encoding: chunked\r\n\r\n2\r\n{}\r\n0\r\n\r\n')

    def test_absolute_deadlines_for_blocking_stages(self):
        with patch.object(api, 'REQUEST_SECONDS', 0.2):
            cases = [(b'', 30, None), (b'HTTP/1.1 200 OK\r\nX:', 30, None),
                     (response()[:-1], 30, None), (response(), 0, 'close')]
            cases += [(b'', 0, stage) for stage in ('dns', 'connect', 'tls')]
            for wire, hold, stage in cases:
                with self.subTest(stage=stage, wire=wire[:20]):
                    started = time.monotonic()
                    self.run_wire(wire, 'request_timeout', hold=hold, stage=stage)
                    self.assertLess(time.monotonic() - started, 3)

    def test_tls_context_and_direct_host(self):
        context = ssl.create_default_context()
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        with patch.object(worker.http.client, 'HTTPSConnection', side_effect=ssl.SSLError(TOKEN)) as connect:
            result = worker.fetch('repository', {}, TOKEN)
        self.assertEqual(result, {'code': 'tls_failure', 'byte_count': 0})
        self.assertEqual(connect.call_args.args, ('api.github.com',))
        self.assertNotIn(TOKEN, repr(result))

    def test_exact_body_and_aggregate_caps(self):
        wire = response(b'{}' + b' ' * (worker.MAX_BODY - 2))
        with child(wire_bootstrap(wire)) as processes:
            client = api.MetadataGitHub(TOKEN)
            for _ in range(16):
                self.assertEqual(client.get('repository').byte_count, worker.MAX_BODY)
            self.assertEqual(client.response_bytes, api.MAX_BYTES)
            self.assertCode('aggregate_limit', client.get, 'repository')
            self.assertEqual(client.request_count, 16)
            self.assertIsNotNone(processes[0].poll())
        uncounted = (b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n'
                     + b'{}' + b' ' * worker.MAX_BODY)
        self.run_wire(uncounted, 'response_limit')

    def test_aggregate_header_and_trailer_caps(self):
        fields = (b'X-Bounded: ' + b'x' * 4000 + b'\r\n') * 5
        self.run_wire(response(headers=fields), 'invalid_headers')
        wire = (b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n'
                b'Transfer-Encoding: chunked\r\n\r\n2\r\n{}\r\n0\r\n' + fields + b'\r\n')
        self.run_wire(wire, 'invalid_headers')
        self.run_wire(response(headers=b'Bad Header: ignored\r\n'), 'invalid_headers')

    def test_close_exception_discards_success_data(self):
        class Connection:
            def request(self, *args, **kwargs):
                raise OSError(TOKEN)
            def close(self):
                raise OSError(TOKEN)
        with patch.object(worker.http.client, 'HTTPSConnection', return_value=Connection()):
            self.assertEqual(worker.fetch('repository', {}, TOKEN),
                             {'code': 'close_failure', 'byte_count': 0})


class SupervisorTests(Assertions):
    def test_partial_frames_and_serial_requests(self):
        code = f'''
import runpy, sys, struct, json, time
w = runpy.run_path({WORKER!r})
for sequence in (1, 2):
    size = struct.unpack('!I', w['read_exact'](sys.stdin.buffer, 4))[0]
    request = json.loads(w['read_exact'](sys.stdin.buffer, size))
    raw = json.dumps(dict(id=sequence, operation=request['operation'], value={{}}, link=None, byte_count=2)).encode()
    for byte in struct.pack('!I', len(raw)) + raw:
        sys.stdout.buffer.write(bytes([byte])); sys.stdout.buffer.flush(); time.sleep(.0005)
time.sleep(30)
'''
        with child(code), api.MetadataGitHub(TOKEN) as client:
            self.assertEqual(client.get('repository').value, {})
            self.assertEqual(client.get('pr').value, {})
            self.assertEqual(client.request_count, 2)
            self.assertEqual(client.response_bytes, 4)

    def test_corrupt_duplicate_and_wrong_identity_frames(self):
        good = {'id': 1, 'operation': 'repository', 'value': {}, 'link': None, 'byte_count': 2}
        raws = [b'\xff\xff\xff\xff', frame(dict(good, id=True)), frame(dict(good, id=2)),
                frame(dict(good, operation='pr')), frame(dict(good, extra=1)),
                frame(dict(good, byte_count=True)), frame(dict(good, link=TOKEN)),
                frame(good) + frame(good), b'\0\0\0\x03xxx']
        for raw in raws:
            code = f'import sys,time; sys.stdin.buffer.read(1); sys.stdout.buffer.write({raw!r}); sys.stdout.buffer.flush(); time.sleep(30)'
            with self.subTest(raw=raw[:20]), child(code) as processes:
                client = api.MetadataGitHub(TOKEN)
                with self.assertRaises(api.MetadataAPIError):
                    client.get('repository')
                client.close()
                self.assertIsNotNone(processes[0].poll())

    def test_partial_ipc_stall_and_worker_crash(self):
        for data in [b'\0', b'\0\0\0\x09{']:
            code = f'import sys,time; sys.stdin.buffer.read(1); sys.stdout.buffer.write({data!r}); sys.stdout.buffer.flush(); time.sleep(30)'
            with child(code) as processes, patch.object(api, 'REQUEST_SECONDS', .15):
                client = api.MetadataGitHub(TOKEN)
                self.assertCode('request_timeout', client.get, 'repository')
                self.assertIsNotNone(processes[0].poll())
        with child('raise SystemExit(7)') as processes:
            client = api.MetadataGitHub(TOKEN)
            self.assertCode('worker_failed', client.get, 'repository')
            self.assertIsNotNone(processes[0].poll())

    def test_fake_clock_budgets_and_closed_client(self):
        with patch.object(api.time, 'monotonic', return_value=10):
            client = api.MetadataGitHub(TOKEN)
        with patch.object(api.time, 'monotonic', return_value=130):
            self.assertCode('session_timeout', client.get, 'repository')
        self.assertCode('adapter_closed', client.get, 'repository')
        client = api.MetadataGitHub(TOKEN)
        client._request_count = 128
        self.assertCode('request_limit', client.get, 'repository')
        client = api.MetadataGitHub(TOKEN)
        client._response_bytes = api.MAX_BYTES
        client._request_count = 1
        raw = frame({'id': 1, 'operation': 'repository', 'value': {}, 'link': None, 'byte_count': 2})[4:]
        self.assertCode('aggregate_limit', client._decode, raw, 'repository', {})
        client.close()

    def test_uncertain_cleanup_is_distinct_and_sticky(self):
        class StuckProcess:
            stdin = io.BytesIO()
            stdout = io.BytesIO()
            def poll(self):
                return None
            def terminate(self):
                pass
            def kill(self):
                pass
            def wait(self, timeout):
                raise subprocess.TimeoutExpired('fixed-worker', timeout)
        client = api.MetadataGitHub(TOKEN)
        client._process = StuckProcess()
        for _ in range(2):
            with self.assertRaises(api.CleanupUncertain):
                client.close()
        self.assertIsNone(client._token)

    def test_cancellation_reaps_and_does_not_return_response(self):
        with child('import time; time.sleep(30)') as processes:
            client = api.MetadataGitHub(TOKEN)
            with patch.object(client, '_exchange', side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    client.get('repository')
            self.assertIsNotNone(processes[0].poll())

    def test_exact_request_cap_and_json_escaped_token(self):
        code = f'''
import runpy
w = runpy.run_path({WORKER!r})
w['fetch'].__globals__['fetch'] = lambda *a: dict(value={{}}, link=None, byte_count=2)
w['main']()
'''
        with child(code) as processes:
            client = api.MetadataGitHub('\\' * 4096)
            for _ in range(128):
                client.get('repository')
            self.assertEqual(client.request_count, 128)
            self.assertCode('request_limit', client.get, 'repository')
            self.assertIsNotNone(processes[0].poll())

    def test_conservative_reservation_precedes_request(self):
        client = api.MetadataGitHub(TOKEN)
        client._response_bytes = api.MAX_BYTES - worker.MAX_BODY + 1
        with patch.object(api.subprocess, 'Popen') as spawn:
            self.assertCode('aggregate_limit', client.get, 'repository')
            spawn.assert_not_called()
        self.assertEqual(client.request_count, 0)

    def test_failed_terminate_still_kills_and_reaps(self):
        class Process:
            def __init__(self, fail_terminate):
                self.stdin, self.stdout = io.BytesIO(), io.BytesIO()
                self.status, self.killed, self.fail_terminate = None, False, fail_terminate
            def poll(self):
                return self.status
            def terminate(self):
                if self.fail_terminate:
                    raise OSError(TOKEN)
            def kill(self):
                self.killed, self.status = True, -9
            def wait(self, timeout):
                if self.status is None:
                    raise subprocess.TimeoutExpired('fixed-worker', timeout)
                return self.status
        for failure in (False, True):
            client = api.MetadataGitHub(TOKEN)
            process = client._process = Process(failure)
            client.close()
            self.assertTrue(process.killed and process.stdin.closed and process.stdout.closed)
            self.assertIsNone(client._process)

    def test_start_and_pipe_setup_failures_are_reaped(self):
        with patch.object(api.subprocess, 'Popen', side_effect=OSError(TOKEN)):
            self.assertCode('worker_start_failed', api.MetadataGitHub(TOKEN).get, 'repository')
        with child('import time; time.sleep(30)') as processes:
            with patch.object(api.os, 'set_blocking', side_effect=OSError(TOKEN)):
                client = api.MetadataGitHub(TOKEN)
                self.assertCode('worker_start_failed', client.get, 'repository')
            self.assertIsNotNone(processes[0].poll())

    def test_response_processing_is_inside_deadline(self):
        client = api.MetadataGitHub(TOKEN)
        with child(wire_bootstrap(response())), patch.object(api, 'REQUEST_SECONDS', .15):
            original = client._decode
            def delayed(*args):
                time.sleep(.2)
                return original(*args)
            with patch.object(client, '_decode', side_effect=delayed):
                self.assertCode('request_timeout', client.get, 'repository')
            self.assertIsNone(client._process)

    def test_pipe_close_error_stays_fatal_after_reap(self):
        with child('import time; time.sleep(30)') as processes:
            client = api.MetadataGitHub(TOKEN)
            client._start()
            real_pipe = client._process.stdin
            class BrokenClose:
                def close(self):
                    real_pipe.close()
                    raise OSError(TOKEN)
            client._process.stdin = BrokenClose()
            with self.assertRaises(api.CleanupUncertain):
                client.close()
            client._process.stdin = real_pipe
            self.assertIsNotNone(processes[0].poll())


if __name__ == '__main__':
    unittest.main()
