"""dns_cancel (stage-signal cancellation fix on rc_bundle D); modeled checks confer no release, native or CI authority."""
from collections import Counter
import subprocess
import unittest
from unittest.mock import patch
import rc_pretag_composition_tests as c
import rc_pretag_ownership_profile as o
import rc_pretag_publication_profile as p
import rc_pretag_publication_tests as pt
import rc_pretag_linux_package_cases as lc
import rc_pretag_rc_bundle_profile as previous
import rc_pretag_windows_launch_profile as windows_launch
import rc_pretag_dns_cancel_profile as x

F_BINDING = ('11aeb60a6d3798a4afae9e0e54a60070b6cec082', '4f03b496fb2bb397c79675ab238e0d2e95493ca4', ('41984b1de0ca13efab3646aae5041845bc78cfee',))
F_RAW = (286, 'd44984e5b9fedcea2bf2e3ce46253e15c43eff75e1d30c36336a3ebdae47bbec')
COUNT = 10
GROUP_COUNTS = {'flake': 3}


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


class DnsCancelCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = c._profile_fixture()
        cls.repo, _, commit, blob = cls.fixture.__enter__()
        cls.addClassCleanup(cls.fixture.__exit__, None, None, None)
        cls.commit, cls.blob, cls._select = staticmethod(commit), staticmethod(blob), staticmethod(p.selected_profile)
        cls._immutable_m = {}
        cls.addClassCleanup(cls._immutable_m.clear)
    def setUp(self):
        self.original = c._entries(x.M, self.repo)
        self.good = self.original | {path: ('100644', 'blob', self.blob((c.ROOT / path).read_bytes())) for path in x.CAPS}
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
        if key not in self._immutable_m:
            self._immutable_m[key] = dict(self._select(ref, *args))
        return dict(self._immutable_m[key])
    def selected(self, ref, fresh=False):
        args = (self.repo, c._git, *self.args[2:])
        if fresh: return self._select(ref, *args)
        with patch.object(p, 'selected_profile', side_effect=self.verified_baseline):
            return self._select(ref, *args)
    def frozen(self, path):
        return c._git('show', x.M + ':' + path, root=self.repo)
    def delegates(self, ref):
        with self.assertRaises(o.TopologyError): x.topology(ref, self.repo, c._git, p.R)
        with patch.object(x, 'content') as content: self.assertIsNone(x.select(ref, *self.args))
        content.assert_not_called()

    def test_actual_m_identity_and_fresh_historical_validation(self):
        self.assertEqual((x.M, x.M_TREE, x.M_PARENTS), F_BINDING)
        self.assertEqual(x.M_RAW, F_RAW)
        self.assertEqual(self.selected(x.M, fresh=True), self.original)
        self.assertIsNone(x.select(x.M, *self.args))
        self.assertEqual(self.selected(self.pure, fresh=True), self.good)

    def test_exact_ordered_d_i_j_selection(self):
        for ref, expected in ((self.pure, self.good), (self.feature, self.good), (self.release, self.overlay)):
            self.assertEqual(self.selected(ref), expected)
        self.assertEqual(x.topology(self.feature, self.repo, c._git, p.R), ('nonrelease', self.feature, self.pure))
        self.assertEqual(x.topology(self.release, self.repo, c._git, p.R), ('release', self.feature, self.pure))

    def test_wrong_topology_delegates_without_content(self):
        for parents in ([], [self.pure], [x.M, x.M], [p.R], [previous.M], [self.pure, x.M], [x.M, self.pure, self.pure],
                        [windows_launch.M], [windows_launch.CORRECTION_PARENT]):
            self.delegates(self.commit(parents, self.good))

    def test_nested_merges_and_correction_chains_never_admit(self):
        side = self.commit([previous.M], self.original)
        nested = self.commit([side, x.M], self.good)
        correction = self.commit([self.pure], self.good)
        stale = self.commit([windows_launch.M], self.good)
        for source in (nested, correction, stale):
            for ref in (self.commit([x.M, source], self.good), self.commit([p.R, self.commit([x.M, source], self.good)], self.overlay)):
                self.delegates(ref)
                with self.assertRaises(o.TopologyError): self.selected(ref)
        self.delegates(self.commit([p.R, self.commit([self.pure, x.M], self.good)], self.overlay))

    def test_extra_missing_and_changed_paths_reject(self):
        some = sorted(x.GROUPS['flake'])[0]
        extra = self.good | {'extra.md': ('100644', 'blob', self.blob(b'extra'))}
        missing = {k: v for k, v in self.good.items() if k != x.CASES}
        changed = self.good | {x.CASES: ('100644', 'blob', self.blob(b'changed'))}
        drift = self.good | {some: ('100644', 'blob', self.blob((c.ROOT / some).read_bytes() + b'\n'))}
        mode = self.good | {some: ('100755', 'blob', self.good[some][2])}
        for entries in (extra, missing, changed, drift, mode, self.original):
            ref = self.commit([x.M], entries)
            with self.assertRaises(AssertionError): self.selected(ref)

    def test_source_pins_and_caps_match_working_tree(self):
        self.assertEqual(x.SOURCE_PINS.keys(), x.CAPS.keys() - {x.PROFILE})
        self.assertEqual(x.FRAGMENTS.keys(), x.BASE_PINS.keys())
        for path, row in x.SOURCE_PINS.items():
            data = (c.ROOT / path).read_bytes()
            self.assertEqual(row, ('100644', *o.pin(data), len(data), len(data.splitlines())), path)
        for path, (lines, _) in x.CAPS.items():
            self.assertLessEqual(len((c.ROOT / path).read_bytes().splitlines()), lines, path)
        self.assertEqual(sum(cap[1] for cap in x.CAPS.values()), x.DELTA_LIMIT)
        self.assertFalse([path for path in x.CAPS if path.endswith('/')])

    def test_normalize_restores_exact_m_bytes_and_rejects_drift(self):
        for path in x.BASE_PINS:
            current = (c.ROOT / path).read_bytes()
            self.assertEqual(x.normalize(path, current), self.frozen(path), path)
            self.assertEqual(x.normalize(path, self.frozen(path)), self.frozen(path), path)
            with self.assertRaises(AssertionError): x.normalize(path, current + b'#')
        self.assertEqual(x.normalize('README.md', b'unrelated'), b'unrelated')
        self.assertEqual(previous.normalize(x.WORKFLOW, (c.ROOT / x.WORKFLOW).read_bytes()),
                         previous.normalize(x.WORKFLOW, self.frozen(x.WORKFLOW)))

    def test_per_pr_groups_are_exact_disjoint_and_droppable(self):
        self.assertEqual({k: len(v) for k, v in x.GROUPS.items()}, GROUP_COUNTS)
        flat = [path for group in x.GROUPS.values() for path in group]
        self.assertEqual(len(flat), len(set(flat)))
        self.assertEqual(set(flat) | x.LAYER, set(x.CAPS))
        self.assertFalse(set(flat) & x.LAYER)

    def test_dns_tls_cancel_is_signal_driven_without_child_timer(self):
        sup = (c.ROOT / 'scripts/rc_consumer_transport_supervisor_tests.py').read_bytes().decode()
        dbc = (c.ROOT / 'scripts/rc_consumer_download_budget_cases.py').read_bytes().decode()
        branch = sup[sup.index("            if mode in {'dns', 'tls'}:"):sup.index("                os._exit(0)")]
        self.assertIn("observed['stage'] = {'entered': time.monotonic()}", branch)
        self.assertIn('while os.read(0, 4096):', branch)
        self.assertNotIn('os.pipe', branch)
        self.assertIn('select.select([parent], [], [])', branch)
        self.assertIn("parent = os.pidfd_open(expected)", sup)
        self.assertIn("if os.getppid() != expected:", sup)
        self.assertNotIn('sleep', branch)
        self.assertNotIn('completed', sup)
        body = dbc[dbc.index('    def test_real_startup_dns_tls_cancellation'):dbc.index('    def network_cases')]
        for needle in ("opener.observations().get('stage') is not None", 'self.assertEqual(cancelled, [None])', 'opener.process.stdin.close()',
                       'self.assertIn(opener.process.returncode, (-signal.SIGTERM, -signal.SIGKILL))',
                       "self.assertNotIn('completed', stage)", 'self.assertEqual(len(opener.requests), 1)'):
            self.assertIn(needle, body)

    def test_worker_exits_when_spawning_parent_is_gone(self):
        import json, sys, tempfile, time
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'fixture.json'
            config.write_text(json.dumps({'responses': [], 'mode': 'dns', 'port': None}))
            dead = subprocess.Popen(['true']); dead.wait()
            other = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
            try:
                for expected in (dead.pid, other.pid):
                    started = time.monotonic()
                    child = subprocess.Popen([sys.executable, '-B', '-I', '-S', str(c.ROOT / 'scripts/rc_consumer_transport_supervisor_tests.py'),
                                              '--worker-fixture', str(config)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                             stderr=subprocess.DEVNULL, close_fds=True,
                                             env={'LC_ALL': 'C', 'LANG': 'C', 'RC_FIXTURE_PARENT': str(expected)})
                    try:
                        self.assertEqual(child.wait(timeout=10), 0)
                    finally:
                        if child.poll() is None: child.kill(); child.wait()
                        child.stdin.close(); child.stdout.close()
                    self.assertLess(time.monotonic() - started, 10)
            finally:
                other.kill(); other.wait()
