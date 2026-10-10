"""rc_bundle (#146/#147/#148 squashed on #89 head); modeled checks confer no release, native or CI authority."""
from collections import Counter
import subprocess
import unittest
from unittest.mock import patch
import rc_pretag_composition_tests as c
import rc_pretag_ownership_profile as o
import rc_pretag_publication_profile as p
import rc_pretag_publication_tests as pt
import rc_pretag_linux_package_cases as lc
import rc_pretag_issue86_root_identity_profile as previous
import rc_pretag_integration_admission_profile as admission
import rc_pretag_windows_launch_profile as windows_launch
import rc_pretag_ci_repair_profile as ci_repair
import rc_pretag_rc_bundle_profile as x

F_BINDING = ('41984b1de0ca13efab3646aae5041845bc78cfee', '72bf89e5a35cf87996f0b96708d503b5f43ab9f6', ('b26b3027f68cdb64711196c694be97fd2e111c5b', '2750b9159dfa5c634c195a9e852dd84f8ace89c0'))
F_RAW = (1283, '3841e4443e82d1fbb002cfaad36181a99314d65ff810693696ee3e88c531adda')
COUNT = 11
GROUP_COUNTS = {'146': 18}
UNSET_TEXT = frozenset()
FIXTURE = 'scripts/rc_publication_https_fixture.py'
REPIN_LINE = ('branches:', '$base=', 'if ((git rev-parse "$($base)^{tree}")', '$previous=', '$earlier=', '$older=', '$origin=',
              'if ((git rev-parse "$($previous)^{tree}")', 'if ((git rev-parse "$($earlier)^{tree}")',
              'if ((git rev-parse "$($older)^{tree}")', 'if ((git rev-parse "$($origin)^{tree}")')


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


class RcBundleCases(unittest.TestCase):
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
        some = sorted(x.GROUPS['146'])[0]
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
        if '148' in x.GROUPS:
            self.assertFalse(x.GROUPS['148'] & x.BASE_PINS.keys())
            self.assertFalse(any(path in x.GROUPS['148'] for path in x.FRAGMENTS))

    def test_native_repins_change_only_trigger_ref_and_sha_lines(self):
        for path, (row, fragments) in x.REPIN.items():
            current = (c.ROOT / path).read_bytes()
            restored = current
            for before, after in reversed(fragments):
                self.assertEqual(restored.count(before), 1, path)
                restored = restored.replace(before, after, 1)
            self.assertEqual((o.pin(restored), len(restored), len(restored.splitlines())), (row[1:3], row[3], row[4]), path)
            for before, after in fragments:
                new, old = before.decode().splitlines(), after.decode().splitlines()
                for line in set(new) ^ set(old):
                    self.assertTrue(line.strip().startswith(REPIN_LINE), (path, line))
            text = current.decode()
            self.assertIn("$base='" + x.M + "'", text)
            self.assertIn(x.M_TREE, text)

    def test_fixture_surfaces_openssl_stderr_keeps_called_process_error_and_gates(self):
        import rc_publication_https_fixture as fixture
        data = (c.ROOT / FIXTURE).read_bytes()
        for new, _ in admission.FRAGMENTS[FIXTURE]:
            self.assertEqual(data.count(new), 1)
        failed = subprocess.CompletedProcess(['/usr/bin/openssl'], 1, None, b'unit openssl diagnostic')
        with patch.object(fixture.subprocess, 'run', return_value=failed), self.assertRaises(subprocess.CalledProcessError) as raised:
            fixture.HTTPSFixture().__enter__()
        self.assertIs(type(raised.exception), subprocess.CalledProcessError)
        self.assertEqual((raised.exception.returncode, raised.exception.stderr), (1, b'unit openssl diagnostic'))
        self.assertIn('unit openssl diagnostic', str(raised.exception.__cause__))

    def test_windows_launch_select_never_fires_and_normalize_is_passthrough(self):
        with patch.object(windows_launch, 'select', side_effect=AssertionError('windows_launch select fired')) as fired:
            for ref, expected in ((self.pure, self.good), (self.feature, self.good), (self.release, self.overlay)):
                self.assertEqual(self.selected(ref), expected)
        fired.assert_not_called()
        for path in windows_launch.BASE_PINS:
            below = ci_repair.normalize(path, (c.ROOT / path).read_bytes())
            self.assertEqual(windows_launch.normalize(path, below), below, path)

