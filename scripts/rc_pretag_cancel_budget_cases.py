"""cancel_budget (real-child cancel budget, reap and fd hygiene on dns_cancel D); modeled checks confer no release, native or CI authority."""
from collections import Counter
import os
import signal
import sys
import tempfile
import time
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
import rc_pretag_composition_tests as c
import rc_pretag_ownership_profile as o
import rc_pretag_publication_profile as p
import rc_pretag_publication_tests as pt
import rc_pretag_linux_package_cases as lc
import rc_pretag_dns_cancel_profile as previous
import rc_pretag_windows_launch_profile as windows_launch
import rc_pretag_cancel_budget_profile as x

F_BINDING = ('48e995fa8389a26cc955069c4a02be43e4a76576', 'e6c6dbb347c5403e791a4ea9b3b7e9ea08618453', ('11aeb60a6d3798a4afae9e0e54a60070b6cec082',))
F_RAW = (327, 'eb88b5e790a0abaa238cacc6ce124658b65cc70a8848b5bb42ae1cdc32ed3dd8')
COUNT = 13
GROUP_COUNTS = {'budget': 3, 'timeout': 3}


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


class CancelBudgetCases(unittest.TestCase):
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
        some = sorted(x.GROUPS['budget'])[0]
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

    def budget_case(self):
        import rc_consumer_download_budget_cases as budget
        case = budget.DownloadBudgetCases('test_real_startup_dns_tls_cancellation')
        case.setUp()
        self.addCleanup(case.doCleanups)
        return budget, case

    def test_real_child_budget_fits_assertion_limit(self):
        import rc_consumer_download_budget_cases as budget
        import rc_consumer_transport as transport
        self.assertLessEqual(budget.FIXTURE_DEADLINE + budget.FIXTURE_CLEANUP + budget.MARGIN, budget.LIMIT)
        self.assertGreater(budget.MARGIN, 0)
        self.assertLess(budget.FIXTURE_CLEANUP, transport.CLEANUP_TIMEOUT)
        dbc = (c.ROOT / 'scripts/rc_consumer_download_budget_cases.py').read_bytes().decode()
        self.assertEqual(dbc.count('bounded=True'), 3)
        self.assertEqual(dbc.count('deadline=time.monotonic() + 1.4'), 0)
        self.assertIn("deadline=time.monotonic() + FIXTURE_DEADLINE", dbc)
        self.assertIn("patch.object(transport, 'CLEANUP_TIMEOUT', FIXTURE_CLEANUP) if bounded", dbc)

    def test_slow_sigterm_child_is_killed_within_budget(self):
        budget, case = self.budget_case()
        opener = case.opener('slow_term')
        # Cancel only once the child has installed its slow SIGTERM handler (it publishes that itself).
        case.failure(opener, 'transport_cancelled', bounded=True, deadline=time.monotonic() + budget.FIXTURE_DEADLINE,
                     check_active=case.cancellation(lambda: opener.observations().get('slow_term') is True))
        self.assertEqual(opener.process.returncode, -signal.SIGKILL)

    def test_over_limit_failure_reports_cpu_wall_and_stack(self):
        budget, case = self.budget_case()
        from rc_consumer_io import ConsumerError
        def slow(opener, **kwargs):
            time.sleep(budget.LIMIT + 0.2); raise ConsumerError('transport_cancelled')
        with tempfile.TemporaryFile('w+') as dump, patch.object(sys, 'stderr', dump), patch.object(case, 'run_download', slow):
            with self.assertRaises(AssertionError) as caught:
                case.failure(None, 'transport_cancelled')
            dump.seek(0); stack = dump.read()
        self.assertRegex(str(caught.exception), r'wall=\d+\.\d+ self_cpu=\d+\.\d+ children_cpu=\d+\.\d+')
        self.assertIn('most recent call first', stack)
        self.assertIn('slow', stack)

    def test_unreaped_fixture_child_fails_loudly(self):
        import rc_consumer_transport_tests as fixtures
        budget, case = self.budget_case()
        start = len(fixtures.SPAWNED)
        opener = case.opener('startup')  # keep it: Opener.__del__ would kill and reap the child
        process = opener.start_worker()
        process.kill(); time.sleep(0.2)
        with self.assertRaises(AssertionError) as caught:
            fixtures._reaped_or_fail(self, start)
        self.assertIn(str(process.pid), str(caught.exception))
        self.assertIsNotNone(process.returncode)
        self.assertEqual(len(fixtures.SPAWNED), start)
        process.stdin.close(); process.stdout.close()
        second = case.opener('startup'); reaped = second.start_worker(); reaped.kill(); reaped.wait()
        fixtures._reaped_or_fail(self, start)
        reaped.stdin.close(); reaped.stdout.close()

    def test_fixture_worker_closes_inherited_descriptors(self):
        import json
        read, write = os.pipe()
        os.dup2(read, 50); os.set_inheritable(50, True)
        try:
            with tempfile.TemporaryDirectory() as directory:
                config = Path(directory) / 'fixture.json'
                config.write_text(json.dumps({'responses': [], 'mode': 'fd_probe', 'port': None}))
                child = subprocess.Popen([sys.executable, '-B', '-I', '-S', str(c.ROOT / 'scripts/rc_consumer_transport_supervisor_tests.py'),
                                          '--worker-fixture', str(config)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.DEVNULL, pass_fds=(50,),
                                         env={'LC_ALL': 'C', 'LANG': 'C', 'RC_FIXTURE_PARENT': str(os.getpid())})
                try:
                    observed, end = Path(directory) / 'observed.json', time.monotonic() + 10
                    while not observed.exists() and time.monotonic() < end:
                        time.sleep(0.01)
                    fds = json.loads(observed.read_text())['fds']
                finally:
                    child.kill(); child.wait(); child.stdin.close(); child.stdout.close()
        finally:
            for fd in (read, write, 50): os.close(fd)
        self.assertNotIn(50, fds)
        self.assertEqual(fds[:3], [0, 1, 2])
        self.assertLessEqual(len(fds), 5)  # 0-2 plus the parent pidfd and the listing's own descriptor
