"""Actual child/pipes/loopback lifecycle tests; never live GitHub/TLS evidence."""
import base64
from contextlib import contextmanager
import io
import json
import os
from pathlib import Path
import signal
import socket
import struct
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rc_consumer_transport as transport
import rc_consumer_transport_worker as wire
from rc_consumer_io import ConsumerError
from rc_consumer_transport_tests import HOST, URL, Opener, Response
import rc_consumer_transport_tests as fixtures


def fixture_worker(config):
    with config.open('rb') as stream:
        raw = stream.read(8 * 1024**2 + 1)
    assert len(raw) <= 8 * 1024**2
    value = json.loads(raw)
    mode = value['mode']
    if mode == 'request_backpressure':
        wire.emit(b'R'); time.sleep(3); return 1
    if mode == 'startup':
        time.sleep(3)
        return 1
    if mode == 'ignore_term':
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        time.sleep(3)
        return 1
    if mode == 'partial_prefix':
        sys.stdout.buffer.write(b'\x00\x00'); sys.stdout.buffer.flush(); time.sleep(3)
        return 1
    if mode == 'partial_payload':
        sys.stdout.buffer.write(struct.pack('!I', 10) + b'R'); sys.stdout.buffer.flush(); time.sleep(3)
        return 1
    if mode in {'oversized', 'zero', 'unsolicited'}:
        raw = struct.pack('!I', wire.MAX_FRAME + 1 if mode == 'oversized' else 0)
        sys.stdout.buffer.write(raw if mode != 'unsolicited' else b'\x00\x00\x00\x02Bx')
        sys.stdout.buffer.flush()
        return 1
    wire.TRUSTED_STORAGE_HOSTS = frozenset({HOST})
    # The fixed parent budget owns local slow-phase expiry before per-I/O timeout.
    wire.READ_TIMEOUT = 1.0 if mode.startswith('local_') else 0.10
    observed = {'requests': [], 'closed': []}
    def record():
        raw = json.dumps(observed).encode()
        assert len(raw) <= 131072
        pending = config.parent / 'observed.pending'
        with pending.open('wb') as stream:
            assert stream.write(raw) == len(raw)
        os.replace(pending, config.parent / 'observed.json')
    class ChildOpener:
        def open(self, request, timeout):
            index = len(observed['requests'])
            observed['requests'].append(dict(url=request.full_url, headers=request.header_items(),
                                            method=request.get_method(), timeout=timeout))
            record()
            if mode in {'dns', 'tls'}:
                time.sleep(3)
                raise OSError('simulated network stage')
            if mode.startswith('local_') and (index == 1 or mode.startswith('local_api')):
                import urllib.request
                mapped = urllib.request.Request('http://127.0.0.1:%d/fixture' % value['port'],
                                                headers=dict(request.header_items()), method='GET')
                response = urllib.request.build_opener(urllib.request.ProxyHandler({}), wire.NoRedirect()).open(mapped, timeout=timeout)
            else:
                row = value['responses'][index]
                if row.get('failure') == 'open':
                    raise OSError('synthetic PRIVATE')
                response = Response(row['code'], base64.b64decode(row['body']), row['headers'])
                failure = row.get('failure')
                if failure == 'read':
                    def fail(_):
                        raise TimeoutError('synthetic PRIVATE')
                    response.read1 = fail
                if failure == 'chunk':
                    response.read1 = lambda _: 'not bytes'
                if row.get('http_error'):
                    import urllib.error
                    error = urllib.error.HTTPError(URL, response.code, 'PRIVATE', response.headers, io.BytesIO())
                    def close_error():
                        error.fp.close(); observed['closed'].append(index); record()
                    error.close = close_error
                    raise error
            original_close = response.close
            def close():
                if mode == 'close_hang' and index == 1:
                    time.sleep(3)
                if mode == 'close_error' and index == 1:
                    raise OSError('synthetic PRIVATE')
                original_close(); observed['closed'].append(index); record()
            response.close = close
            return response
    original_emit = wire.emit
    def emit(frame):
        if frame == b'D' and mode == 'missing_done':
            return
        original_emit(frame)
        if frame == b'R' and mode == 'duplicate_ready':
            original_emit(b'R')
        if frame == b'D':
            if mode == 'done_hang':
                time.sleep(3)
            elif mode == 'done_no_eof':
                os.close(1); time.sleep(3)
            elif mode == 'trailing':
                original_emit(b'Bextra')
            elif mode == 'duplicate_done':
                original_emit(b'D')
            elif mode == 'abnormal':
                os._exit(3)
    wire.emit = emit
    return wire.main(ChildOpener())


@contextmanager
def trickle(mode, data, *, progress=None):
    server = socket.socket(); server.bind(('127.0.0.1', 0)); server.listen(1); server.settimeout(2)
    stop, seen, errors = threading.Event(), [], []
    def serve():
        try:
            connection, _ = server.accept()
            with connection:
                connection.settimeout(1)
                request = b''
                while b'\r\n\r\n' not in request and len(request) < 16384:
                    request += connection.recv(4096)
                seen.append(request)
                status = b'302 Found' if mode.startswith('local_api') else b'200 OK'
                if 'status' in mode:
                    connection.sendall(b'HTTP/1.1 ' + status.split()[0] + b' ')
                else:
                    connection.sendall(b'HTTP/1.1 ' + status + b'\r\n')
                    if 'body' in mode:
                        connection.sendall(b'Content-Length: ' + str(len(data)).encode() + b'\r\n\r\n')
                    else:
                        connection.sendall(b'X-Slow: ')
                if progress is not None:
                    progress.append(time.monotonic())
                for _ in range(160):
                    if stop.wait(0.025):
                        break
                    connection.sendall(b'x')
                    if progress is not None:
                        progress.append(time.monotonic())
                if not stop.is_set():
                    if 'body' not in mode:
                        headers = b'\r\nContent-Length: ' + str(len(data)).encode() + b'\r\n'
                        if mode.startswith('local_api'):
                            headers += b'Location: ' + URL.encode() + b'\r\n'
                        connection.sendall(headers + b'\r\n' + data)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as error:
            errors.append(type(error).__name__)
        finally:
            server.close()
    thread = threading.Thread(target=serve); thread.start()
    try:
        yield server.getsockname()[1], seen
    finally:
        stop.set(); thread.join(3)
        assert not thread.is_alive() and not errors, errors


class SupervisorTests(unittest.TestCase):
    setUp = fixtures.TransportTests.setUp
    run_download = fixtures.TransportTests.run_download
    redirect = fixtures.TransportTests.redirect
    def opener(self, mode='responses', port=None):
        return Opener(self.redirect(), Response(200, self.data), mode=mode, port=port)

    def failure(self, mode, code=None, opener=None, **kwargs):
        opener = opener or self.opener(mode)
        started = time.monotonic()
        with patch.object(transport, 'TOTAL_TIMEOUT', 0.5), patch.object(transport, 'CLEANUP_TIMEOUT', 0.5):
            with self.assertRaises(ConsumerError) as caught:
                self.run_download(opener, **kwargs)
        self.assertLess(time.monotonic() - started, 1.5)
        self.assertIsNotNone(opener.process.poll())
        self.assertIsNone(caught.exception.__context__)
        self.assertIsNone(caught.exception.__cause__)
        if code:
            self.assertEqual(caught.exception.code, code)
        self.assertNotIn('PRIVATE', str(caught.exception))
        return caught.exception

    def test_slow_network_phases_cancel_owned_worker(self):
        self.data = b'x' * 160
        self.artifact.update(size_in_bytes=len(self.data), digest='sha256:' + __import__('hashlib').sha256(self.data).hexdigest())
        for mode in ('local_headers', 'local_body', 'local_api_headers', 'local_api_status', 'local_storage_status'):
            progress = []
            with self.subTest(mode=mode), trickle(mode, self.data, progress=progress) as (port, seen):
                # Keep a full real half-second of drip after the selected response phase.
                # Bound readiness separately; the owned logical deadline remains fixed.
                ready_by = time.monotonic() + 0.9
                readiness_failed = False
                def clock():
                    nonlocal readiness_failed
                    phase = progress[0] if progress else None
                    now = time.monotonic()
                    if phase is None:
                        readiness_failed |= now >= ready_by
                    else:
                        readiness_failed |= phase >= ready_by
                    return 0.5 if readiness_failed else (now - phase if phase is not None else 0.0)
                error = self.failure(mode, 'transport_deadline_exceeded', self.opener(mode, port),
                                     clock=clock, deadline=0.5, check_active=lambda: None)
                self.assertTrue(seen)
                self.assertFalse(readiness_failed)
                self.assertGreaterEqual(len(progress), 9)
                self.assertLess(progress[0], ready_by)
                self.assertGreaterEqual(progress[-1] - progress[0], 0.35)
                self.assertGreaterEqual(time.monotonic() - progress[0], 0.5)
                if not mode.startswith('local_api'):
                    self.assertNotIn(b'authorization:', seen[0].lower())
            # Each isolated invocation owns a fresh root/file.
            self.root.close()
            self.root = __import__('rc_consumer_io').PrivateRoot(self.temp.name, source_root=Path('/source'))
            self.addCleanup(self.root.close)

    def test_startup_and_simulated_dns_tls_are_deadline_bounded(self):
        for mode in ('startup', 'dns', 'tls', 'partial_prefix', 'partial_payload'):
            with self.subTest(mode=mode):
                opener = self.opener(mode)
                self.failure(mode, 'transport_deadline_exceeded', opener)
                if mode in {'dns', 'tls'}:
                    self.assertEqual(len(opener.requests), 1)

    def test_request_write_backpressure_uses_same_deadline(self):
        import fcntl  # Supported Linux fixture only; absence fails, never skips/passes.
        self.api.token = 'x' * 12000
        opener = self.opener('request_backpressure')
        start, write = transport._Download.start, os.write
        pipe_fd, capacity, writes = None, None, []
        def constrain(owner, adapter):
            nonlocal pipe_fd, capacity
            start(owner, adapter)  # The production owner has the real child and pipes.
            pipe_fd = owner.process.stdin.fileno()
            actual = fcntl.fcntl(pipe_fd, fcntl.F_SETPIPE_SZ, 4096)
            capacity = fcntl.fcntl(pipe_fd, fcntl.F_GETPIPE_SZ)
            self.assertEqual(actual, capacity)
            self.assertEqual(capacity, 4096)
        def record(fd, data):
            try:
                count = write(fd, data)
            except BlockingIOError:
                if fd == pipe_fd: writes.append((len(data), None))
                raise
            if fd == pipe_fd: writes.append((len(data), count))
            return count
        with patch.object(transport._Download, 'start', autospec=True, side_effect=constrain), \
             patch.object(transport.os, 'write', side_effect=record):
            self.failure('request_backpressure', 'transport_deadline_exceeded', opener)
        self.assertTrue(writes)
        self.assertLess(capacity, writes[0][0])  # Actual encoded request write argument.
        self.assertTrue(any(count is None or 0 < count < size for size, count in writes))

    def test_invalid_and_terminal_protocol(self):
        for mode in ('oversized', 'zero', 'unsolicited', 'duplicate_ready', 'duplicate_done',
                     'trailing', 'missing_done', 'abnormal', 'done_hang', 'done_no_eof'):
            with self.subTest(mode=mode):
                self.failure(mode)
                self.root.close()
                self.root = __import__('rc_consumer_io').PrivateRoot(self.temp.name, source_root=Path('/source'))
                self.addCleanup(self.root.close)

    def test_actual_http_close_errors_cannot_complete(self):
        for mode in ('close_error', 'close_hang'):
            with self.subTest(mode=mode):
                opener = self.opener(mode); self.failure(mode, opener=opener)
                self.assertNotIn(1, opener.observations().get('closed', []))
                self.root.close()
                self.root = __import__('rc_consumer_io').PrivateRoot(self.temp.name, source_root=Path('/source'))
                self.addCleanup(self.root.close)

    def test_empty_hosts_prevent_launcher_even_with_bad_adapter(self):
        with patch.object(transport, 'TRUSTED_STORAGE_HOSTS', frozenset()), patch.object(transport.subprocess, 'Popen') as launch:
            with self.assertRaisesRegex(ConsumerError, '^storage_transport_unverified$'):
                self.run_download(object())
            launch.assert_not_called()

    def test_cancellation_reaps_and_preserves_only_type(self):
        for exception in (KeyboardInterrupt, SystemExit):
            opener = self.opener()
            original_read = os.read
            def cancel(fd, size):
                if opener.process is not None and fd == opener.process.stdout.fileno():
                    raise exception('PRIVATE')
                return original_read(fd, size)
            with patch.object(transport.os, 'read', side_effect=cancel):
                with self.assertRaises(exception) as caught:
                    self.run_download(opener)
            self.assertEqual(caught.exception.args, (1,) if exception is SystemExit else ())
            self.assertIsNone(caught.exception.__context__)
            self.assertIsNotNone(opener.process.poll())

    def test_late_file_completion_fails_closed(self):
        original = os.fsync
        def late(fd):
            original(fd); time.sleep(0.25)
        opener = self.opener()
        with patch.object(transport, 'TOTAL_TIMEOUT', 0.20), patch.object(os, 'fsync', late):
            with self.assertRaisesRegex(ConsumerError, '^transport_deadline_exceeded$'):
                self.run_download(opener)
        self.assertIsNotNone(opener.process.poll())

    def test_cleanup_uncertainty_is_sticky_and_never_success(self):
        class Pipe:
            count = 0
            def close(self):
                self.count += 1
                raise OSError('PRIVATE')
        class Process:
            stdin, stdout = Pipe(), Pipe()
            calls = []
            def poll(self): return None
            def terminate(self): self.calls.append('terminate'); raise OSError('PRIVATE')
            def kill(self): self.calls.append('kill'); raise OSError('PRIVATE')
            def wait(self, timeout): self.calls.append(('wait', timeout)); raise subprocess.TimeoutExpired('PRIVATE', timeout)
        owner = transport._Download(time.monotonic() + 1, time.monotonic)
        owner.process = process = Process(); pipes = (process.stdin, process.stdout)
        with patch.object(transport, 'CLEANUP_TIMEOUT', 0.05):
            self.assertFalse(owner.cleanup()); before = list(process.calls)
            self.assertFalse(owner.cleanup())
        self.assertEqual(process.calls, before)
        self.assertIn('kill', process.calls)
        self.assertTrue(owner.uncertain and owner.escalated)
        self.assertTrue(all(pipe.count == 1 for pipe in pipes))

    def test_terminate_failure_still_kills_real_worker(self):
        opener = self.opener('ignore_term'); start = opener.start_worker
        def launch():
            process = start()
            process.terminate = lambda: (_ for _ in ()).throw(OSError('PRIVATE'))
            return process
        with patch.object(opener, 'start_worker', side_effect=launch):
            self.failure('ignore_term', 'transport_cleanup_uncertain', opener)

    def test_launch_failure_lateness_and_fd_setup_are_sanitized(self):
        with patch.object(transport.subprocess, 'Popen', side_effect=OSError('PRIVATE')):
            with self.assertRaisesRegex(ConsumerError, '^artifact_transport_failed$') as caught:
                transport.download_artifact_zip(self.api, self.artifact, self.root)
        self.assertIsNone(caught.exception.__context__)
        for mode in ('late', 'fd'):
            opener = self.opener('startup'); start = opener.start_worker
            def launch():
                process = start()
                if mode == 'late': time.sleep(0.2)
                return process
            with patch.object(opener, 'start_worker', side_effect=launch), \
                 patch.object(transport, 'TOTAL_TIMEOUT', 0.1):
                context = patch.object(transport.os, 'set_blocking', side_effect=OSError('PRIVATE')) if mode == 'fd' else __import__('contextlib').nullcontext()
                with context, self.assertRaises(ConsumerError) as caught:
                    self.run_download(opener)
            self.assertEqual(caught.exception.code, 'transport_deadline_exceeded' if mode == 'late' else 'artifact_transport_failed')
            self.assertIsNone(caught.exception.__context__)
            self.assertIsNotNone(opener.process.poll())

    def test_cleanup_terminal_negative_controls(self):
        for fault in ('kill', 'reap', 'late', 'poll', 'close'):
            calls = []
            class Pipe:
                def close(self):
                    calls.append('close')
                    if fault == 'close': raise OSError('PRIVATE')
            class Process:
                stdin, stdout = Pipe(), Pipe()
                def poll(self):
                    if fault == 'poll': raise OSError('PRIVATE')
                    return None if fault in ('kill', 'reap') else 0
                def terminate(self): calls.append('terminate')
                def kill(self):
                    calls.append('kill')
                    if fault == 'kill': raise OSError('PRIVATE')
                def wait(self, timeout):
                    calls.append(('wait', timeout))
                    if fault in ('kill', 'reap'): raise subprocess.TimeoutExpired('PRIVATE', timeout)
                    if fault == 'late': time.sleep(0.04)
                    return 0
            owner = transport._Download(time.monotonic()+1, time.monotonic); owner.process = Process()
            with self.subTest(fault=fault), patch.object(transport, 'CLEANUP_TIMEOUT', 0.02):
                self.assertFalse(owner.cleanup()); saved = list(calls)
                self.assertFalse(owner.cleanup()); self.assertEqual(calls, saved)
                self.assertTrue(owner.uncertain)

    def test_parent_file_write_failure_is_not_worker_success(self):
        @contextmanager
        def broken(*_):
            class Output:
                def write(self, _): raise OSError('PRIVATE')
            yield Output()
        opener = self.opener()
        with patch.object(self.root, 'open', side_effect=broken):
            with self.assertRaisesRegex(ConsumerError, '^artifact_transport_failed$') as caught:
                self.run_download(opener)
        self.assertIsNone(caught.exception.__context__)
        self.assertIsNotNone(opener.process.poll())

    def test_secret_consumer_error_is_never_propagated_or_retained(self):
        for target in ('launcher', 'destination'):
            for uncertain in (False, True):
                opener = self.opener()
                original = transport._Download.cleanup
                cleanup = patch.object(transport._Download, 'cleanup', autospec=True,
                    side_effect=lambda owner: (original(owner), False)[1]) if uncertain else __import__('contextlib').nullcontext()
                error = ConsumerError('secret_signed_url_token_fixture')
                fault = patch.object(opener, 'start_worker', side_effect=error) if target == 'launcher' else patch.object(self.root, 'open', side_effect=error)
                with self.subTest(target=target, uncertain=uncertain), fault, cleanup:
                    with self.assertRaises(ConsumerError) as caught:
                        self.run_download(opener)
                expected = 'transport_cleanup_uncertain' if uncertain else 'artifact_transport_failed'
                self.assertEqual(caught.exception.code, expected)
                self.assertEqual(caught.exception.args, (expected,))
                self.assertIsNone(caught.exception.__context__)
                self.assertIsNone(caught.exception.__cause__)
                if uncertain:
                    self.assertEqual(caught.exception.original_error_code, 'artifact_transport_failed')
                if opener.process is not None:
                    self.assertIsNotNone(opener.process.poll())

    def test_consumer_boundary_never_revalidates_or_parses_failure(self):
        import rc_artifact_consumer as consumer
        from types import SimpleNamespace
        for code in ('transport_deadline_exceeded', 'transport_cleanup_uncertain'):
            opener = self.opener('startup')
            with patch.object(consumer.snapshot, 'resolve_candidate', return_value={}), \
                 patch.object(consumer.snapshot, 'select_source_runs', return_value={}), \
                 patch.object(consumer.snapshot, 'authenticate_bundle_metadata', return_value=self.artifact), \
                 patch.object(consumer.snapshot, 'derive_final_producer', return_value=SimpleNamespace()), \
                 patch.object(consumer.snapshot, 'revalidate_download') as fence, \
                 patch.object(consumer.archive, 'extract_bounded_zip') as parser, \
                 patch.object(consumer, 'make_asset_plan') as plan, \
                 patch.object(transport, 'TOTAL_TIMEOUT', 0.15):
                extra = patch.object(transport._Download, 'cleanup', autospec=True,
                    side_effect=lambda owner: (original(owner), False)[1]) if code.endswith('uncertain') else __import__('contextlib').nullcontext()
                original = transport._Download.cleanup
                with extra, self.assertRaisesRegex(ConsumerError, '^' + code + '$'):
                    consumer.consume(Path('/source'), {'artifact_id': 42}, {}, self.api,
                                     temporary_parent=self.temp.name, opener=opener)
                fence.assert_not_called(); parser.assert_not_called(); plan.assert_not_called()
            self.assertIsNotNone(opener.process.poll())
            self.assertFalse(list(Path(self.temp.name).glob('rc-consumer-receipts-*')))


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--worker-fixture':
        result = 1
        try:
            result = fixture_worker(Path(sys.argv[2]))
        except BaseException:
            pass
        sys.exit(result)
    unittest.main()
