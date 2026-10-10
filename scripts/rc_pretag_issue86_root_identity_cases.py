"""#86 snapshot-root identity admission on b26b3027; modeled checks confer no release, native or CI authority."""
from collections import Counter
import unittest
from unittest.mock import patch
import rc_pretag_composition_tests as c
import rc_pretag_ownership_profile as o
import rc_pretag_publication_profile as p
import rc_pretag_publication_tests as pt
import rc_pretag_linux_package_cases as lc
import rc_pretag_reap_safe_profile as previous
import rc_pretag_issue86_root_identity_profile as x

F_BINDING = ('b26b3027f68cdb64711196c694be97fd2e111c5b', '73009a15c7feb119eef422393d02fdbea7cda624', ('0cc6039142b50a03e7fcd28d115ce40a4b9e2c96', '48c9fa0ebebe2151fae90fa13690f4cbafdb9eb0'))
F_RAW = (1234, '70d62cfe347868d59722d3798723058aac59b55f828fb99f352284776858340d')
COUNT = 8


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


class Issue86RootIdentityCases(unittest.TestCase):
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
        for parents in ([], [self.pure], [x.M, x.M], [p.R], [previous.M], [self.pure, x.M], [x.M, self.pure, self.pure]):
            self.delegates(self.commit(parents, self.good))

    def test_nested_merges_and_correction_chains_never_admit(self):
        side = self.commit([previous.M], self.original)
        nested = self.commit([side, x.M], self.good)
        correction = self.commit([self.pure], self.good)
        for source in (nested, correction):
            for ref in (self.commit([x.M, source], self.good), self.commit([p.R, self.commit([x.M, source], self.good)], self.overlay)):
                self.delegates(ref)
                with self.assertRaises(o.TopologyError): self.selected(ref)
        self.delegates(self.commit([p.R, self.commit([self.pure, x.M], self.good)], self.overlay))

    def test_extra_missing_and_changed_paths_reject(self):
        rust = sorted(x.RUST)[0]
        extra = self.good | {'extra.md': ('100644', 'blob', self.blob(b'extra'))}
        extra_rust = self.good | {'src-tauri/src/extra.rs': ('100644', 'blob', self.blob(b'// extra\n'))}
        missing = {k: v for k, v in self.good.items() if k != x.CASES}
        changed = self.good | {x.CASES: ('100644', 'blob', self.blob(b'changed'))}
        drift = self.good | {rust: ('100644', 'blob', self.blob((c.ROOT / rust).read_bytes() + b'\n'))}
        mode = self.good | {rust: ('100755', 'blob', self.good[rust][2])}
        for entries in (extra, extra_rust, missing, changed, drift, mode, self.original):
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

    def test_normalize_restores_exact_m_bytes_and_rejects_drift(self):
        for path in x.BASE_PINS:
            current = (c.ROOT / path).read_bytes()
            self.assertEqual(x.normalize(path, current), self.frozen(path), path)
            self.assertEqual(x.normalize(path, self.frozen(path)), self.frozen(path), path)
            with self.assertRaises(AssertionError): x.normalize(path, current + b'#')
        self.assertEqual(x.normalize('README.md', b'unrelated'), b'unrelated')
        self.assertEqual(previous.normalize(x.WORKFLOW, (c.ROOT / x.WORKFLOW).read_bytes()),
                         previous.normalize(x.WORKFLOW, self.frozen(x.WORKFLOW)))

    def test_rust_delta_is_exactly_the_eight_snapshot_files(self):
        self.assertEqual(len(x.RUST), 8)
        self.assertTrue(all(path.startswith('src-tauri/src/') and path.endswith('.rs') for path in x.RUST))
        self.assertEqual(x.CAPS.keys() - x.RUST, {x.PROFILE, x.CASES, x.DISPATCHER, x.DISPATCHER_CASES, x.WORKFLOW})
        new = {path for path in x.RUST if path not in self.original}
        self.assertEqual(new, {'src-tauri/src/workspace_snapshots/root_identity_tests.rs'})
        self.assertEqual(x.RUST - new, x.BASE_PINS.keys() & x.RUST)
