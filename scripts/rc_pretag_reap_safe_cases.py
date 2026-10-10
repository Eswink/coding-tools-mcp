"""Reap-safe process-group cleanup admission; modeled checks confer no release or native authority."""
import ast
from collections import Counter
import importlib.util
import os
import signal
import subprocess
import sys
import time
import unittest
from unittest.mock import patch
import rc_pretag_composition_tests as c
import rc_pretag_ownership_profile as o
import rc_pretag_publication_profile as p
import rc_pretag_publication_tests as pt
import rc_pretag_linux_package_cases as lc
import rc_pretag_ci_repair_profile as previous
import rc_pretag_reap_safe_profile as x
from rc_pretag_issue86_root_identity_profile import normalize as issue86_bytes

F_BINDING = ('0cc6039142b50a03e7fcd28d115ce40a4b9e2c96', 'a9bf6bafbbaa1419d81f752e6b13937374956dcf', ('35559f67b3d91cb277879c82e87fc098bbc72038', '0f64359ee65b6225657d27f916853879ad3e04bb'))
F_RAW = (1209, 'ee8ef48e173bd471693288b8af03eae4e6853db980025d012db9906bd12ce417')
COUNT = 14


def inventory():
    expected = [cls + '.' + name for cls, names in x.NEW_CASES.items() for name in names]
    actual = [item for cls in x.NEW_CASES for item in lc.ids(cls)]
    pt.inventory_ids(expected, COUNT, x.DIGEST)
    pt.inventory_ids(actual, COUNT, x.DIGEST)
    assert Counter(actual) == Counter(expected)
    return expected


def execution_valid(loaded, result):
    pt.inventory_ids(loaded, COUNT, x.DIGEST)
    assert Counter(loaded) == Counter(inventory())
    executed = getattr(result, 'executed_ids', [])
    pt.inventory_ids(executed, COUNT, x.DIGEST)
    return (result.wasSuccessful() and not result.skipped and not result.expectedFailures
            and not result.unexpectedSuccesses and Counter(executed) == Counter(loaded)
            and result.testsRun == len(set(executed)) == COUNT)


class ReapSafeCompositionCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = c._profile_fixture()
        cls.repo, _, commit, blob = cls.fixture.__enter__()
        cls.addClassCleanup(cls.fixture.__exit__, None, None, None)
        cls.commit, cls.blob, cls._select = staticmethod(commit), staticmethod(blob), staticmethod(p.selected_profile)
        cls._immutable_f = {}
        cls.addClassCleanup(cls._immutable_f.clear)
    def setUp(self):
        self.original = c._entries(x.M, self.repo)
        self.good = self.original | {path: ('100644', 'blob', self.blob(issue86_bytes(path, (c.ROOT / path).read_bytes()))) for path in x.CAPS}
        self.pure = self.commit([x.M], self.good)
        self.feature = self.commit([x.M, self.pure], self.good)
        self.overlay = self.good | c.RELEASE_DOCS
        self.release = self.commit([p.R, self.feature], self.overlay)
        self.args = (self.repo, c._git, c._entries, c._feature_profile, c.RELEASE, c.RELEASE_TREE, dict(c.RELEASE_DOCS))
    def verified_baseline(self, ref, *args, **kwargs):
        callbacks = all(actual is expected for actual, expected in zip(args[1:4], self.args[1:4]))
        if ref != x.M or (x.M, x.M_TREE, x.M_PARENTS) != F_BINDING or kwargs or not callbacks or args != self.args:
            return self._select(ref, *args, **kwargs)
        key = (ref, *args[:6], tuple(sorted(args[6].items())))
        if key not in self._immutable_f:
            self._immutable_f[key] = dict(self._select(ref, *args))
        return dict(self._immutable_f[key])
    def selected(self, ref, fresh=False):
        args = (self.repo, c._git, *self.args[2:])
        if fresh: return self._select(ref, *args)
        with patch.object(p, 'selected_profile', side_effect=self.verified_baseline):
            return self._select(ref, *args)
    def frozen(self, path):
        return c._git('show', x.M + ':' + path, root=self.repo)

    def test_actual_m_identity_and_fresh_historical_validation(self):
        self.assertEqual((x.M, x.M_TREE, x.M_PARENTS), F_BINDING)
        self.assertEqual(x.M_RAW, F_RAW)
        self.assertEqual(self.selected(x.M, fresh=True), self.original)
        self.assertIsNone(x.select(x.M, *self.args))
        self.assertEqual(self.selected(self.pure, fresh=True), self.good)

    def test_exact_ordered_d_i_j_selection(self):
        for ref, expected in ((self.pure, self.good), (self.feature, self.good), (self.release, self.overlay)):
            self.assertEqual(self.selected(ref), expected)
        self.assertEqual(x.topology(self.release, self.repo, c._git, p.R), ('release', self.feature, self.pure))

    def test_wrong_topology_delegates_without_content(self):
        for parents in ([], [self.pure], [x.M, x.M], [p.R], [previous.M]):
            ref = self.commit(parents, self.good)
            with self.assertRaises(o.TopologyError): x.topology(ref, self.repo, c._git, p.R)
            with patch.object(x, 'content') as content: self.assertIsNone(x.select(ref, *self.args))
            content.assert_not_called()

    def test_extra_missing_and_changed_paths_reject(self):
        extra = self.good | {'extra.md': ('100644', 'blob', self.blob(b'extra'))}
        missing = {k: v for k, v in self.good.items() if k != x.CASES}
        changed = self.good | {x.CASES: ('100644', 'blob', self.blob(b'changed'))}
        for entries in (extra, missing, changed, self.original):
            ref = self.commit([x.M], entries)
            with self.assertRaises(AssertionError): self.selected(ref)

    def test_source_pins_and_caps_match_working_tree(self):
        self.assertEqual(x.SOURCE_PINS.keys(), x.CAPS.keys() - {x.PROFILE})
        self.assertEqual(x.FRAGMENTS.keys(), x.BASE_PINS.keys())
        for path, row in x.SOURCE_PINS.items():
            data = issue86_bytes(path, (c.ROOT / path).read_bytes())
            self.assertEqual(row, ('100644', *o.pin(data), len(data), len(data.splitlines())), path)
        for path, (lines, _) in x.CAPS.items():
            self.assertLessEqual(len(issue86_bytes(path, (c.ROOT / path).read_bytes()).splitlines()), lines, path)
        self.assertLessEqual(sum(cap[1] for cap in x.CAPS.values()), x.DELTA_LIMIT + 200)

    def test_normalize_restores_exact_m_bytes_and_rejects_drift(self):
        for path in x.BASE_PINS:
            current = issue86_bytes(path, (c.ROOT / path).read_bytes())
            self.assertEqual(x.normalize(path, current), self.frozen(path), path)
            self.assertEqual(x.normalize(path, self.frozen(path)), self.frozen(path), path)
            with self.assertRaises(AssertionError): x.normalize(path, current + b'#')
        self.assertEqual(x.normalize('README.md', b'unrelated'), b'unrelated')
        self.assertEqual(previous.normalize(x.WORKFLOW, issue86_bytes(x.WORKFLOW, (c.ROOT / x.WORKFLOW).read_bytes())),
                         previous.normalize(x.WORKFLOW, self.frozen(x.WORKFLOW)))


def _load(name, module):
    spec = importlib.util.spec_from_file_location(module, c.ROOT / 'scripts' / name)
    loaded = importlib.util.module_from_spec(spec); spec.loader.exec_module(loaded)
    return loaded


GROUP = r'''
import os, signal, subprocess, sys, time
signal.signal(signal.SIGTERM, signal.SIG_IGN) if sys.argv[1] == 'stubborn' else None
child = subprocess.Popen([sys.executable, '-c', 'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(600)'])
print(child.pid, flush=True)
if sys.argv[1] == 'exit':
    os._exit(0)
time.sleep(600)
'''


class ReapSafeCleanupCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(c.ROOT / 'scripts'))
        cls.gui = _load('Ubuntu原生验收v1.py', 'reap_safe_native_gui')
    def spawn(self, mode):
        process = subprocess.Popen([sys.executable, '-c', GROUP, mode], stdout=subprocess.PIPE, text=True, start_new_session=True)
        straggler = int(process.stdout.readline())
        self.addCleanup(lambda: process.poll() is None and (os.killpg(process.pid, signal.SIGKILL), process.wait()))
        return process, straggler
    def alive(self, pid):
        try:
            with open(f'/proc/{pid}/stat') as stat: return stat.read().rsplit(')', 1)[1].split()[0] != 'Z'
        except FileNotFoundError: return False

    def test_straggler_killed_and_leader_reaped_last(self):
        process, straggler = self.spawn('stay')
        self.gui.stop_owned_group(process, term=0.5, kill=5)
        self.assertIsNotNone(process.returncode)
        deadline = time.monotonic() + 5
        while self.alive(straggler) and time.monotonic() < deadline: time.sleep(0.05)
        self.assertFalse(self.alive(straggler))

    def test_exited_leader_still_pins_group_for_straggler_cleanup(self):
        process, straggler = self.spawn('exit')
        deadline = time.monotonic() + 5
        while self.gui.leader_running(process) and time.monotonic() < deadline: time.sleep(0.02)
        self.assertFalse(self.gui.leader_running(process))
        self.assertIsNone(process.returncode)
        self.assertTrue(self.alive(straggler))
        self.gui.stop_owned_group(process, term=0.2, kill=5)
        self.assertEqual(process.returncode, 0)
        while self.alive(straggler) and time.monotonic() < deadline + 5: time.sleep(0.05)
        self.assertFalse(self.alive(straggler))

    def test_reaped_leader_is_never_signalled(self):
        process, straggler = self.spawn('exit')
        process.wait(timeout=5)
        with patch.object(self.gui.os, 'killpg') as killpg, patch.object(self.gui.os, 'pidfd_open') as opened, \
                self.assertRaisesRegex(RuntimeError, 'not cleanable: leader already reaped'):
            self.gui.stop_owned_group(process)
        killpg.assert_not_called(); opened.assert_not_called()
        os.kill(straggler, signal.SIGKILL)

    def test_post_kill_timeout_fails_closed_without_reaping(self):
        process, _ = self.spawn('stubborn')
        with patch.object(self.gui.os, 'killpg') as killpg, self.assertRaisesRegex(RuntimeError, 'leader left unreaped'):
            self.gui.stop_owned_group(process, term=0.1, kill=0.1)
        self.assertEqual([call.args[1] for call in killpg.call_args_list], [signal.SIGTERM, signal.SIGKILL])
        self.assertIsNone(process.returncode)
        self.assertTrue(self.gui.leader_running(process))

    def test_leader_running_observes_without_reaping(self):
        process, straggler = self.spawn('exit')
        while self.gui.leader_running(process): time.sleep(0.02)
        self.assertIsNone(process.returncode)
        self.assertIsNotNone(os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT))
        os.kill(straggler, signal.SIGKILL); process.wait(timeout=5)

    def test_close_uses_reap_safe_helpers_only(self):
        tree = ast.parse((c.ROOT / 'scripts/Ubuntu原生验收v1.py').read_text())
        close = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'close')
        calls = {n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, 'id', None) for n in ast.walk(close) if isinstance(n, ast.Call)}
        self.assertTrue({'leader_running', 'stop_owned_group'} <= calls)
        self.assertFalse({'poll', 'killpg', 'wait'} & calls)

    def test_externally_reaped_observer_is_never_group_signalled(self):
        import multiprocessing, tempfile
        provenance = _load('linux_runtime_provenance.py', 'reap_safe_runtime_provenance')
        with tempfile.TemporaryDirectory() as output:
            observer = provenance.Observer({}, output, 'reap-safe')
            worker = multiprocessing.get_context('fork').Process(target=time.sleep, args=(60,))
            worker.start(); observer.worker, observer.worker_fd = worker, os.pidfd_open(worker.pid)
            fd = observer.worker_fd
            os.kill(worker.pid, signal.SIGKILL); os.waitpid(worker.pid, 0)  # Reaped outside the owner.
            with patch.object(provenance.os, 'killpg') as killpg:
                observer._stop_worker()
            killpg.assert_not_called()
            self.assertIn('ChildProcessError', observer.errors)
            self.assertIsNone(observer.worker_fd)
            with self.assertRaises(OSError): os.fstat(fd)

    def test_cleanup_has_no_poll_reap_before_group_signal(self):
        source = (c.ROOT / 'scripts/Ubuntu原生验收v1.py').read_text()
        helper = source[source.index('def stop_owned_group'):source.index('def open_workspace')]
        self.assertLess(helper.index('os.killpg'), helper.index('process.wait('))
        self.assertNotIn('.poll()', helper)
        self.assertIn('os.WNOWAIT', helper)
