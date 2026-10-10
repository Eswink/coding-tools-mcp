"""Current supervisor budgets with real children, pipes and loopback fixtures."""
from contextlib import contextmanager
from decimal import Decimal
import hashlib
import os
import signal
from pathlib import Path
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from rc_consumer_io import ConsumerError, PrivateRoot
import rc_consumer_transport as transport
import rc_consumer_transport_tests as fixtures
import rc_consumer_transport_supervisor_tests as supervisor


class DownloadBudgetCases(unittest.TestCase):
    # Alias only fixture methods: old test IDs remain unique and unchanged.
    setUp = fixtures.TransportTests.setUp
    run_download = fixtures.TransportTests.run_download
    redirect = fixtures.TransportTests.redirect
    opener = supervisor.SupervisorTests.opener

    def fresh(self):
        self.root.close()
        self.root = PrivateRoot(self.temp.name, source_root=Path('/source'))
        self.addCleanup(self.root.close)

    def failure(self, opener, code, **kwargs):
        started = time.monotonic()
        with self.assertRaises(ConsumerError) as caught:
            self.run_download(opener, **kwargs)
        self.assertLess(time.monotonic() - started, 1.5)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(caught.exception.args, (code,))
        self.assertIsNone(caught.exception.__context__)
        self.assertIsNone(caught.exception.__cause__)
        if opener.process is not None:
            self.assertIsNotNone(opener.process.poll())
        return caught.exception

    def cancellation(self, when):
        def active():
            if when():
                raise ConsumerError('cancelled')
        return active

    def test_defaults_and_shared_deadline_success_and_clamp(self):
        for supplied in (None, 102, 102.5, 10**10000):
            for callback in (None, lambda: None):
                self.fresh()
                opener = self.opener(); owners, waits = [], []
                start = transport._Download.start
                def record(owner, adapter):
                    owners.append(owner); start(owner, adapter)
                    wait = owner.process.wait
                    def observed(timeout):
                        waits.append(timeout); return wait(timeout=timeout)
                    owner.process.wait = observed
                with self.subTest(kind=type(supplied).__name__, callback=callback is not None), \
                     patch.object(transport._Download, 'start', autospec=True, side_effect=record):
                    path = self.run_download(opener, deadline=supplied, clock=lambda: 100,
                                             check_active=callback)
                self.assertEqual(path.read_bytes(), self.data)
                self.assertEqual(owners[0].deadline, min(supplied, 400) if supplied is not None else 400)
                self.assertIsNotNone(opener.process.poll())
                self.assertGreaterEqual(len(waits), 2)
                if callback is None:
                    self.assertEqual(len(waits), 2)  # One EOF wait, one unchanged cleanup reap.
                    self.assertEqual(waits[0], min(transport.READ_TIMEOUT, owners[0].deadline - 100))
                else:
                    self.assertTrue(all(0 < value <= 0.05 for value in waits[:-1]))

    def test_invalid_expired_boundary_and_huge_deadlines(self):
        class Integer(int): pass
        class Float(float): pass
        bad = (True, False, Integer(2), Float(2), Decimal('2'), 'PRIVATE', object(),
               float('nan'), float('inf'), float('-inf'))
        for value in bad + (0, 99, 100, -10**10000):
            opener = self.opener()
            expected = 'invalid_transport_deadline' if any(value is item for item in bad) else 'transport_deadline_exceeded'
            with self.subTest(kind=type(value).__name__):
                self.failure(opener, expected, deadline=value, clock=lambda: 100)
            self.assertIsNone(opener.process)
        # The shared deadline is checked again immediately before launch.
        times = iter((100, 101))
        opener = self.opener()
        self.failure(opener, 'transport_deadline_exceeded', deadline=101, clock=lambda: next(times))
        self.assertIsNone(opener.process)

    def test_cancelled_or_invalid_activity_prevents_launch(self):
        callbacks = [(value, 'artifact_transport_failed') for value in
                     (False, 0, 'PRIVATE', object(), lambda: False, lambda: 0, lambda: object())]
        callbacks.append((self.cancellation(lambda: True), 'transport_cancelled'))
        for callback, expected in callbacks:
            opener = self.opener()
            self.failure(opener, expected, check_active=callback)
            self.assertIsNone(opener.process)
        now = [10]
        def late():
            now[0] = 11
        opener = self.opener()
        self.failure(opener, 'transport_deadline_exceeded', deadline=11,
                     clock=lambda: now[0], check_active=late)
        self.assertIsNone(opener.process)

    def test_callback_mapping_and_legacy_interrupt_sanitization(self):
        class Malformed(Exception):
            def __init__(self, code): super().__init__('PRIVATE'); self.code = code
        class Hostile(Exception):
            @property
            def code(self): raise KeyboardInterrupt('PRIVATE')
        class String(str): pass
        for error, expected in ((Malformed('cancelled'), 'transport_cancelled'),
                (Malformed('timeout'), 'transport_deadline_exceeded'),
                (Malformed('transport_cancelled'), 'artifact_transport_failed'),
                (Malformed(String('cancelled')), 'artifact_transport_failed'),
                (Malformed([]), 'artifact_transport_failed'), (Hostile('PRIVATE'), 'artifact_transport_failed'),
                (ValueError('PRIVATE'), 'artifact_transport_failed')):
            opener = self.opener('startup')
            def active():
                if opener.process is not None: raise error
            self.failure(opener, expected, check_active=active)
            self.assertIsNotNone(opener.process)
        for exception in (KeyboardInterrupt, SystemExit):
            opener = self.opener('startup')
            def active():
                if opener.process is not None: raise exception('PRIVATE')
            with self.assertRaises(exception) as caught:
                self.run_download(opener, check_active=active)
            self.assertEqual(caught.exception.args, (1,) if exception is SystemExit else ())
            self.assertIsNone(caught.exception.__context__)
            self.assertIsNone(caught.exception.__cause__)
            self.assertIsNotNone(opener.process.poll())

    def test_real_startup_partial_ipc_and_late_launch_deadlines(self):
        for mode in ('startup', 'partial_prefix', 'partial_payload'):
            with self.subTest(mode=mode):
                opener = self.opener(mode)
                self.failure(opener, 'transport_deadline_exceeded', deadline=time.monotonic() + 0.25)
                self.assertIsNotNone(opener.process)
        opener = self.opener('startup'); launch = opener.start_worker
        def late():
            child = launch(); time.sleep(0.15); return child
        with patch.object(opener, 'start_worker', side_effect=late):
            self.failure(opener, 'transport_deadline_exceeded', deadline=time.monotonic() + 0.1)
        self.assertIsNotNone(opener.process)

    def test_real_startup_dns_tls_cancellation(self):
        for mode in ('startup', 'dns', 'tls', 'partial_prefix', 'partial_payload'):
            opener = self.opener(mode); cancel_at = time.monotonic() + 0.25
            if mode in ('dns', 'tls'):
                # Cancel on the child's stage signal, not on a timer started before the child exists.
                cancelled = []
                def signalled(opener=opener, cancelled=cancelled):
                    if opener.observations().get('stage') is not None:
                        # EOF alone (parent closing the write end) must not end the child: probe before cancelling.
                        opener.process.stdin.close(); time.sleep(0.1)
                        cancelled.append(opener.process.poll()); return True
                    return False
                when = signalled
            else:
                when = lambda: time.monotonic() >= cancel_at
            with self.subTest(mode=mode):
                self.failure(opener, 'transport_cancelled', deadline=time.monotonic() + 1.4,
                             check_active=self.cancellation(when))
            if mode in ('dns', 'tls'):
                self.assertEqual(len(opener.requests), 1)
                stage = opener.observations()['stage']
                self.assertEqual(cancelled, [None])  # exactly one cancel, child alive after EOF
                self.assertNotIn('completed', stage)  # DNS/TLS stage never finished
                self.assertIn(opener.process.returncode, (-signal.SIGTERM, -signal.SIGKILL))  # killed, not EOF self-exit

    def network_cases(self, cancelled):
        self.data = b'x' * 160
        self.artifact.update(size_in_bytes=len(self.data), digest='sha256:' + hashlib.sha256(self.data).hexdigest())
        for mode in ('local_headers', 'local_body', 'local_api_headers', 'local_api_status', 'local_storage_status'):
            self.fresh()
            with self.subTest(mode=mode), supervisor.trickle(mode, self.data) as (port, seen):
                opener = self.opener(mode, port); boundary = time.monotonic() + 0.3
                self.failure(opener, 'transport_cancelled' if cancelled else 'transport_deadline_exceeded',
                             deadline=boundary + 2 if cancelled else boundary,
                             check_active=self.cancellation(lambda: time.monotonic() >= boundary) if cancelled else None)
                self.assertTrue(seen)
                if not mode.startswith('local_api'):
                    self.assertNotIn(b'authorization:', seen[0].lower())

    def test_loopback_trickle_obeys_shared_deadline(self):
        self.network_cases(False)

    def test_loopback_trickle_cancellation_reaps_worker(self):
        self.network_cases(True)

    def test_pipe_backpressure_keeps_budget_and_cancellation(self):
        import fcntl  # A real Linux pipe; missing support is a failure, never a skip.
        self.api.token = 'x' * 12000
        for cancelled in (False, True):
            opener = self.opener('request_backpressure'); writes, pipe = [], []
            start, write = transport._Download.start, os.write
            def constrain(owner, adapter):
                start(owner, adapter); pipe.append(owner.process.stdin.fileno())
                self.assertEqual(fcntl.fcntl(pipe[0], fcntl.F_SETPIPE_SZ, 4096), 4096)
                self.assertEqual(fcntl.fcntl(pipe[0], fcntl.F_GETPIPE_SZ), 4096)
            def observed(fd, data):
                try: count = write(fd, data)
                except BlockingIOError:
                    if pipe and fd == pipe[0]: writes.append((len(data), None))
                    raise
                if pipe and fd == pipe[0]: writes.append((len(data), count))
                return count
            boundary = time.monotonic() + 0.25
            with patch.object(transport._Download, 'start', autospec=True, side_effect=constrain), \
                 patch.object(transport.os, 'write', side_effect=observed):
                self.failure(opener, 'transport_cancelled' if cancelled else 'transport_deadline_exceeded',
                             deadline=boundary + 2 if cancelled else boundary,
                             check_active=self.cancellation(lambda: time.monotonic() >= boundary) if cancelled else None)
            self.assertTrue(writes); self.assertGreater(writes[0][0], 4096)
            self.assertTrue(any(count is None or 0 < count < size for size, count in writes))

    def test_owned_file_open_write_fsync_close_checkpoints(self):
        for stage in ('open', 'write', 'fsync', 'close'):
            for cancelled in (False, True):
                self.fresh(); state = {'late': False}; events = []
                opener = self.opener(); original_open, fsync = self.root.open, os.fsync
                def cross(point):
                    events.append(point)
                    if point == stage: state['late'] = True
                @contextmanager
                def destination(*args):
                    with original_open(*args) as stream:
                        cross('open')
                        class Output:
                            def write(_, data):
                                count = stream.write(data); cross('write'); return count
                        yield Output()
                    cross('close')
                def synced(fd):
                    fsync(fd); cross('fsync')
                with self.subTest(stage=stage, cancelled=cancelled), \
                     patch.object(self.root, 'open', side_effect=destination), \
                     patch.object(os, 'fsync', side_effect=synced):
                    self.failure(opener, 'transport_cancelled' if cancelled else 'transport_deadline_exceeded',
                                 deadline=11, clock=lambda: 10 if cancelled or not state['late'] else 11,
                                 check_active=self.cancellation(lambda: state['late']) if cancelled else None)
                self.assertIn(stage, events)
                if stage == 'open': self.assertNotIn('write', events)

    def test_child_exit_and_cleanup_cannot_return_late_success(self):
        # Crossing either fixed boundary between samples must retain its error code.
        for operation, boundary in ((True, 10), (False, 1)):
            for after_wait in (False, True):
                ticks = iter(([0, 0, 0, 0] if after_wait else [0]) +
                             [boundary - 0.1, boundary - 0.1, boundary])
                owner = transport._Download(10, lambda: next(ticks), lambda: None)
                calls = []
                owner.process = SimpleNamespace(wait=lambda timeout: (calls.append(timeout), 0)[1])
                code = 'transport_deadline_exceeded' if operation else 'artifact_transport_failed'
                with self.subTest(operation=operation, after_wait=after_wait), \
                     patch.object(transport, 'READ_TIMEOUT', 20 if operation else 1), \
                     self.assertRaises(ConsumerError) as caught:
                    owner.wait_for_exit()
                self.assertEqual(caught.exception.args, (code,))
                self.assertEqual(len(calls), int(after_wait))
        for operation in (False, True):
            self.fresh(); opener = self.opener('done_no_eof'); waits = []; now = [0.0]
            launch = opener.start_worker
            def single_wait_launch():
                child = launch(); wait = child.wait
                def observed(timeout):
                    waits.append(timeout)
                    try:
                        return wait(timeout=timeout)
                    except transport.subprocess.TimeoutExpired:
                        now[0] += timeout
                        raise
                child.wait = observed; return child
            with patch.object(opener, 'start_worker', side_effect=single_wait_launch), \
                 patch.object(transport, 'READ_TIMEOUT', 2 if operation else 0.15):
                self.failure(opener, 'transport_deadline_exceeded' if operation else 'artifact_transport_failed',
                             deadline=0.25 if operation else 2, clock=lambda: now[0])
            self.assertEqual(len(waits), 3)  # One EOF wait, terminate wait and terminal reap.
        for failure in ('operation', 'eof', 'cancel'):
            self.fresh(); opener = self.opener('done_no_eof'); waits = []; now = [0.0]
            launch = opener.start_worker
            def observed_launch():
                child = launch(); wait = child.wait
                def observed(timeout):
                    waits.append(timeout)
                    try:
                        return wait(timeout=timeout)
                    except transport.subprocess.TimeoutExpired:
                        now[0] += timeout
                        raise
                child.wait = observed; return child
            boundary = 0.25
            with patch.object(opener, 'start_worker', side_effect=observed_launch), \
                 patch.object(transport, 'READ_TIMEOUT', 0.15 if failure == 'eof' else 2):
                self.failure(opener, {'operation': 'transport_deadline_exceeded',
                             'eof': 'artifact_transport_failed', 'cancel': 'transport_cancelled'}[failure],
                             deadline=boundary if failure == 'operation' else boundary + 2,
                             clock=lambda: now[0],
                             check_active=self.cancellation(lambda: failure == 'cancel' and now[0] >= boundary))
            self.assertGreater(len(waits), 3)
            self.assertTrue(all(0 < value <= 0.05 for value in waits[:-2]))
        for final in ('deadline', 'deadline_plain', 'cancelled', 'timeout', 'malformed', 'interrupt', 'exit'):
            self.fresh(); state = {'cleaned': False}; owners, calls = [], []
            opener = self.opener(); cleanup = transport._Download.cleanup
            def late_cleanup(owner):
                owners.append(owner); result = cleanup(owner); state['cleaned'] = True; return result
            def active():
                if not state['cleaned']: return None
                calls.append('final')
                if final in ('cancelled', 'timeout'): raise ConsumerError(final)
                if final == 'malformed': return False
                if final == 'interrupt': raise KeyboardInterrupt('PRIVATE')
                if final == 'exit': raise SystemExit('PRIVATE')
            with patch.object(transport._Download, 'cleanup', autospec=True, side_effect=late_cleanup):
                kwargs = dict(deadline=11, clock=lambda: 11 if state['cleaned'] and final.startswith('deadline') else 10,
                              check_active=None if final == 'deadline_plain' else active)
                if final in ('interrupt', 'exit'):
                    kind = KeyboardInterrupt if final == 'interrupt' else SystemExit
                    with self.assertRaises(kind) as caught: self.run_download(opener, **kwargs)
                    self.assertEqual(caught.exception.args, () if final == 'interrupt' else (1,))
                    self.assertIsNone(caught.exception.__context__); self.assertIsNone(caught.exception.__cause__)
                else:
                    self.failure(opener, {'deadline': 'transport_deadline_exceeded', 'deadline_plain': 'transport_deadline_exceeded', 'cancelled': 'transport_cancelled',
                                 'timeout': 'transport_deadline_exceeded', 'malformed': 'artifact_transport_failed'}[final], **kwargs)
            self.assertEqual(len(owners), 1); self.assertIsNone(owners[0].process)
            self.assertEqual(calls, [] if final.startswith('deadline') else ['final'])
            self.assertIsNotNone(opener.process.poll())

    def test_cleanup_uncertainty_overrides_cancel_and_stays_sticky(self):
        for primary in ('cancelled', 'timeout', 'PRIVATE'):
            opener = self.opener('startup'); owners, closed, waits, activity = [], [], [], []
            start = transport._Download.start
            def acquired(owner, adapter):
                # Capture immediately: start checks activity after taking ownership.
                owners.append(owner); start(owner, adapter)
            launch = opener.start_worker
            def uncertain():
                child = launch(); stream, wait = child.stdin, child.wait
                class Pipe:
                    def close(self):
                        closed.append('stdin'); stream.close(); raise OSError('PRIVATE')
                    def fileno(self): return stream.fileno()
                child.stdin = Pipe()
                def observed(timeout): waits.append(timeout); return wait(timeout=timeout)
                child.wait = observed; return child
            def active():
                activity.append('check')
                if opener.process is not None: raise ConsumerError(primary)
            with patch.object(transport._Download, 'start', autospec=True, side_effect=acquired), \
                 patch.object(opener, 'start_worker', side_effect=uncertain):
                error = self.failure(opener, 'transport_cleanup_uncertain', check_active=active)
            self.assertEqual(error.original_error_code, {'cancelled': 'transport_cancelled',
                             'timeout': 'transport_deadline_exceeded'}.get(primary, 'artifact_transport_failed'))
            self.assertTrue(owners[0].uncertain); before = (len(waits), len(activity))
            self.assertFalse(owners[0].cleanup()); self.assertEqual(before, (len(waits), len(activity)))
            self.assertEqual(closed, ['stdin']); self.assertIsNotNone(opener.process.poll())


if __name__ == '__main__':
    unittest.main()
