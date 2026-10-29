"""actual child/pipe lifecycle fault cases; no success stand-in."""
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

import exact_build_audit as exact
import rc_consumer_fixed_git as fixed
from rc_consumer_io import ConsumerError
from rc_consumer_git_test_support import Cancelled, fault_child, reaped, source, record_git, observe_pipe


class GitSupervisorCases(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='git-supervisor-case-')
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.root, self.sha = source(self.parent)
        self.reader = fixed.Reader(self.root, check_active=lambda: None)
        self.reader.__enter__()
        self.addCleanup(self.close_reader)

    def close_reader(self):
        try:
            self.reader.close()
        except ConsumerError as error:
            self.assertEqual(error.code, 'transport_cleanup_uncertain')

    def failure(self, script, code='transport_deadline_exceeded', *, seconds=0.15, wrap=None):
        self.reader.deadline = time.monotonic() + seconds
        with fault_child(script, wrap=wrap) as seen, observe_pipe(self.reader) as reads:
            with self.assertRaisesRegex(ConsumerError, '^' + code + '$'):
                self.reader.read('rev-parse', 'HEAD')
            reaped(self, seen.children)
            seen.reads = reads; return seen

    def test_prelaunch_cancel_and_expired_deadline_create_no_child(self):
        def cancel(): raise Cancelled()
        for deadline, callback, code in ((None, cancel, 'transport_cancelled'),
                (time.monotonic() - 1, None, 'transport_deadline_exceeded')):
            self.reader.deadline, self.reader.check_active = deadline, callback
            with patch.object(fixed.subprocess, 'Popen', side_effect=AssertionError('must not launch')):
                with self.assertRaisesRegex(ConsumerError, '^' + code + '$'):
                    self.reader.read('rev-parse', 'HEAD')

    def test_trickle_stdout_cannot_renew_original_deadline(self):
        seen = self.failure("import os,time\nfor x in b'" + self.sha + "\\n':\n os.write(1,bytes([x])); time.sleep(.035)\n", seconds=1.0)
        self.assertGreaterEqual(sum(bool(data) for data, _ in seen.reads), 2); self.assertTrue(0 < sum(len(data) for data, _ in seen.reads) < 41)

    def test_complete_payload_without_eof_still_expires_and_reaps(self):
        seen = self.failure("import os,time; os.write(1,b'" + self.sha + "\\n'); time.sleep(10)", seconds=1.0)
        self.assertEqual(b''.join(data for data, _ in seen.reads), (self.sha + '\n').encode()); self.assertTrue(all(data for data, _ in seen.reads))

    def test_eof_before_process_exit_remains_under_same_deadline(self):
        seen = self.failure("import os,time; os.close(1); time.sleep(10)", seconds=1.0)
        self.assertTrue(any(data == b'' and alive for data, alive in seen.reads))

    def test_each_fixed_output_cap_plus_one_is_detected_before_callback(self):
        operations = [('config', fixed.CONFIG_LIMIT), ('head', 41), ('index', fixed.INDEX_OUTPUT_LIMIT),
            ('status', fixed.STATUS_LIMIT), ('tree', 41), ('files', fixed.FILES_LIMIT)]
        for kind, cap in operations:
            script = f'import os\nleft={cap + 1}\nwhile left:\n n=os.write(1,b"x"*min(left,65536)); left-=n\n'
            self.reader.deadline = time.monotonic() + 5
            read, received = fixed.os.read, [0]
            def observed(fd, amount):
                block = read(fd, amount)
                if self.reader.process is not None and fd == self.reader.process.stdout.fileno():
                    received[0] += len(block)
                return block
            def active():
                if received[0] > cap: raise Cancelled()
            self.reader.check_active = active
            with self.subTest(kind=kind), fault_child(script) as seen, \
                 patch.object(fixed.os, 'read', side_effect=observed):
                with self.assertRaisesRegex(ConsumerError, '^git_output_limit_exceeded$'):
                    self.reader._run(kind, cap)
                self.assertEqual(received[0], cap + 1)
                reaped(self, seen.children)

    def test_child_is_owned_before_callback_and_descriptor_setup(self):
        seen_owner = []
        def active():
            if self.reader.process is not None:
                seen_owner.append(self.reader.process)
                raise Cancelled()
        self.reader.check_active = active
        with fault_child('import time; time.sleep(10)') as seen:
            with self.assertRaisesRegex(ConsumerError, '^transport_cancelled$'):
                self.reader.read('rev-parse', 'HEAD')
            self.assertEqual(seen_owner, seen.children)
            reaped(self, seen.children)
        self.reader.check_active = lambda: None
        with fault_child('import time; time.sleep(10)') as seen, \
             patch.object(fixed.os, 'set_blocking', side_effect=OSError('owned setup failure')):
            with self.assertRaisesRegex(OSError, 'owned setup failure'):
                self.reader.read('rev-parse', 'HEAD')
            reaped(self, seen.children)

    def test_selector_registration_wait_and_pipe_read_faults_reap_real_child(self):
        for fault in ('register', 'select', 'read'):
            with self.subTest(fault=fault), fault_child('import os,time; os.write(1,b"x"); time.sleep(10)') as seen:
                if fault == 'read':
                    original = fixed.os.read
                    def read(fd, amount):
                        if self.reader.process and fd == self.reader.process.stdout.fileno():
                            raise OSError('owned pipe fault')
                        return original(fd, amount)
                    where = patch.object(fixed.os, 'read', side_effect=read)
                else:
                    where = patch.object(fixed.selectors.DefaultSelector, fault, side_effect=OSError('owned pipe fault'))
                with where, self.assertRaisesRegex(OSError, 'owned pipe fault'):
                    self.reader.read('rev-parse', 'HEAD')
                reaped(self, seen.children)

    def test_callback_only_real_git_does_not_invent_operation_clock(self):
        count = []
        self.reader.deadline = None
        self.reader.check_active = lambda: count.append('checked') and None
        with record_git() as seen, patch.object(fixed.time, 'monotonic', side_effect=AssertionError('invented clock')):
            self.assertEqual(self.reader.read('rev-parse', 'HEAD'), self.sha)
            self.reader.check()
        self.assertTrue(count)
        reaped(self, seen.children)

    def test_known_nonzero_exit_wins_over_post_success_cancellation(self):
        selected, original = [], fixed.selectors.DefaultSelector.select
        def active():
            if selected: raise Cancelled()
        def ready(selector, timeout):
            events = original(selector, timeout)
            if events:
                self.reader.process.wait(timeout=2)
                selected.append(True)
            return events
        self.reader.check_active = active
        with fault_child('raise SystemExit(7)') as seen, \
             patch.object(fixed.selectors.DefaultSelector, 'select', ready):
            with self.assertRaisesRegex(exact.EvidenceError, '^git_identity_unavailable$'):
                self.reader.read('rev-parse', 'HEAD')
            reaped(self, seen.children)

    def test_pipe_close_uncertainty_overrides_timeout_once_without_callbacks(self):
        closing, callbacks, wrappers = [], [], []
        self.reader.check_active = lambda: callbacks.append(len(closing)) and None
        class CloseFailure:
            def __init__(self, stream): self.stream, self.calls = stream, 0
            def __getattr__(self, name): return getattr(self.stream, name)
            def close(self):
                self.calls += 1
                closing.append(True)
                self.stream.close()
                raise OSError('after real close')
        def wrap(process):
            wrapper = CloseFailure(process.stdout)
            process.stdout = wrapper
            wrappers.append(wrapper)
            return wrapper
        self.failure('import time; time.sleep(10)', 'transport_cleanup_uncertain', wrap=wrap)
        self.assertTrue(self.reader.uncertain)
        self.assertEqual([w.calls for w in wrappers], [1])
        self.assertTrue(callbacks)
        self.assertEqual(set(callbacks), {0})
        with self.assertRaisesRegex(ConsumerError, '^transport_cleanup_uncertain$'): self.reader.close()
        self.reader.close()
        self.assertEqual([w.calls for w in wrappers], [1])

    def test_term_ignoring_child_is_killed_and_reaped_within_cleanup_bound(self):
        started, ready, read = time.monotonic(), [], fixed.os.read
        self.reader.deadline = started + 5
        def observed(fd, amount):
            block = read(fd, amount)
            if self.reader.process is not None and fd == self.reader.process.stdout.fileno() and block:
                self.assertEqual(block, b'x')
                self.assertFalse(ready)
                ready.append(time.monotonic())
                self.reader.deadline = ready[0] + 0.3
            return block
        script = 'import os,signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); os.write(1,b"x"); time.sleep(10)'
        with fault_child(script) as seen, patch.object(fixed.os, 'read', side_effect=observed):
            with self.assertRaisesRegex(ConsumerError, '^transport_deadline_exceeded$'):
                self.reader.read('rev-parse', 'HEAD')
            self.assertEqual(len(ready), 1)
            reaped(self, seen.children)
            self.assertEqual(seen.children[0].returncode, -signal.SIGKILL)
            self.assertLess(time.monotonic() - ready[0], 0.3 + fixed.CLEANUP_SECONDS + 1.5)
        self.assertLess(time.monotonic() - started, 5 + 0.3 + fixed.CLEANUP_SECONDS + 1.5)
        self.assertFalse(self.reader.uncertain)

    def test_observed_reap_failure_is_sticky_even_if_os_child_is_gone(self):
        def wrap(process):
            wait = process.wait
            def uncertain(*args, **kwargs):
                result = wait(*args, **kwargs)
                raise OSError('reap observation failed after real wait')
            process.wait = uncertain
            return wait
        self.reader.deadline = time.monotonic() + 0.15
        with fault_child('import time; time.sleep(10)', wrap=wrap) as seen:
            try:
                with self.assertRaisesRegex(ConsumerError, '^transport_cleanup_uncertain$'):
                    self.reader.read('rev-parse', 'HEAD')
                self.assertTrue(self.reader.uncertain)
                self.assertIsNotNone(seen.children[0].returncode)
            finally:
                seen.children[0].wait = seen.wrappers[0]
            reaped(self, seen.children)
