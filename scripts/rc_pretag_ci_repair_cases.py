"""Exact ci.yml repair admission of 35559f67; modeled checks confer no release, native or CI authority."""
from collections import Counter
import unittest
from unittest.mock import patch
import rc_pretag_composition_tests as c
import rc_pretag_ownership_profile as o
import rc_pretag_publication_profile as p
import rc_pretag_publication_tests as pt
import rc_pretag_linux_package_cases as lc
import rc_pretag_source_observation_profile as previous
import rc_pretag_ci_repair_profile as x

F_BINDING = ('35559f67b3d91cb277879c82e87fc098bbc72038', '2b38877287bc0f20b9bf64d58da3d62844af31ee', ('13cd343d942b7a68912d42a8f9235c02ed647764', '0b254c90e58de30de2955f5598499d742207b0b3'))
COUNT = 9


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


class CiRepairCompositionCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = c._profile_fixture()
        cls.repo, _, commit, blob = cls.fixture.__enter__()
        cls.addClassCleanup(cls.fixture.__exit__, None, None, None)
        cls.commit, cls.blob, cls._select = staticmethod(commit), staticmethod(blob), staticmethod(p.selected_profile)
        cls._immutable = {}
        cls.addClassCleanup(cls._immutable.clear)
    def setUp(self):
        self.anchored = c._entries(x.M, self.repo)
        self.base = c._entries(x.BASE, self.repo)
        self.good = self.anchored | {path: ('100644', 'blob', self.blob((c.ROOT / path).read_bytes())) for path in x.CAPS}
        self.pure = self.commit([x.M], self.good)
        self.feature = self.commit([x.M, self.pure], self.good)
        self.overlay = self.good | c.RELEASE_DOCS
        self.release = self.commit([p.R, self.feature], self.overlay)
        self.args = (self.repo, c._git, c._entries, c._feature_profile, c.RELEASE, c.RELEASE_TREE, dict(c.RELEASE_DOCS))
    def verified_baseline(self, ref, *args, **kwargs):
        callbacks = all(actual is expected for actual, expected in zip(args[1:4], self.args[1:4]))
        if ref != x.BASE or kwargs or not callbacks or args != self.args:
            return self._select(ref, *args, **kwargs)
        key = (ref, *args[:6], tuple(sorted(args[6].items())))
        if key not in self._immutable:
            self._immutable[key] = dict(self._select(ref, *args))
        return dict(self._immutable[key])
    def selected(self, ref, fresh=False):
        args = (self.repo, c._git, *self.args[2:])
        if fresh: return self._select(ref, *args)
        with patch.object(p, 'selected_profile', side_effect=self.verified_baseline):
            return self._select(ref, *args)
    def frozen(self, path):
        return c._git('show', x.BASE + ':' + path, root=self.repo)

    def test_actual_m_identity_and_fresh_base_validation(self):
        self.assertEqual((x.M, x.M_TREE, x.M_PARENTS), F_BINDING)
        self.assertEqual(self.selected(x.BASE, fresh=True), self.base)
        self.assertIsNone(x.select(x.M, *self.args))
        with self.assertRaises(o.TopologyError): self.selected(x.M, fresh=True)
        self.assertEqual(self.selected(self.pure, fresh=True), self.good)

    def test_exact_ordered_d_i_j_selection(self):
        for ref, expected in ((self.pure, self.good), (self.feature, self.good), (self.release, self.overlay)):
            self.assertEqual(self.selected(ref), expected)
        self.assertEqual(x.topology(self.release, self.repo, c._git, p.R), ('release', self.feature, self.pure))

    def test_wrong_topology_delegates_without_content(self):
        other = self.commit([x.BASE, self.commit([x.BASE], self.good)], self.good)
        same_tree = [[], [x.BASE], [x.BASE, x.M], list(reversed(x.M_PARENTS)), [x.M, x.M], [p.R], [previous.M]]
        for ref in [other, self.commit([other], self.good)] + [self.commit(parents, self.good) for parents in same_tree]:
            with self.assertRaises(o.TopologyError): x.topology(ref, self.repo, c._git, p.R)
            with patch.object(x, 'content') as content: self.assertIsNone(x.select(ref, *self.args))
            content.assert_not_called()

    def test_same_parents_different_ci_yml_rejects(self):
        current = (c.ROOT / x.CI).read_bytes()
        for data in (current + b'#', self.frozen(x.CI), current.replace(b'contents: read', b'contents: write', 1)):
            ref = self.commit([x.M], self.good | {x.CI: ('100644', 'blob', self.blob(data))})
            with self.assertRaises(AssertionError): self.selected(ref)
        twin = self.commit([x.BASE, x.M_PARENTS[1]], self.base | {x.CI: self.anchored[x.CI]})
        with self.assertRaises(o.TopologyError): x.topology(self.commit([twin], self.good), self.repo, c._git, p.R)

    def test_extra_missing_and_changed_paths_reject(self):
        extra = self.good | {'extra.md': ('100644', 'blob', self.blob(b'extra'))}
        missing = {k: v for k, v in self.good.items() if k != x.CASES}
        changed = self.good | {x.CASES: ('100644', 'blob', self.blob(b'changed'))}
        for entries in (extra, missing, changed, self.anchored):
            ref = self.commit([x.M], entries)
            with self.assertRaises(AssertionError): self.selected(ref)

    def test_source_pins_and_caps_match_working_tree(self):
        self.assertEqual(x.SOURCE_PINS.keys(), x.CAPS.keys() - {x.PROFILE})
        self.assertEqual(x.FRAGMENTS.keys(), x.BASE_PINS.keys())
        self.assertEqual(x.SOURCE_PINS[x.CI], x.CI_PIN)
        for path, row in x.SOURCE_PINS.items():
            data = (c.ROOT / path).read_bytes()
            self.assertEqual(row, ('100644', *o.pin(data), len(data), len(data.splitlines())), path)
        for path, (lines, _) in x.CAPS.items():
            self.assertLessEqual(len((c.ROOT / path).read_bytes().splitlines()), lines, path)
        self.assertEqual(sum(cap[1] for cap in x.CAPS.values()), x.DELTA_LIMIT)

    def test_normalize_restores_exact_base_bytes_and_rejects_drift(self):
        for path in x.BASE_PINS:
            current = (c.ROOT / path).read_bytes()
            self.assertEqual(x.normalize(path, current), self.frozen(path), path)
            self.assertEqual(x.normalize(path, self.frozen(path)), self.frozen(path), path)
            with self.assertRaises(AssertionError): x.normalize(path, current + b'#')
        self.assertEqual(x.normalize('README.md', b'unrelated'), b'unrelated')
        self.assertEqual(previous.normalize('README.md', b'unrelated'), b'unrelated')
        self.assertEqual(previous.normalize(x.DISPATCHER, (c.ROOT / x.DISPATCHER).read_bytes()),
                         previous.normalize(x.DISPATCHER, self.frozen(x.DISPATCHER)))

    def test_ci_policy_rejects_widened_permissions_and_unpinned_actions(self):
        # The whole-file \b(write|write-all)\b search is intentionally strict; a false positive on the word 'write' is accepted.
        current = (c.ROOT / x.CI).read_bytes()
        self.assertTrue(x.ci_policy(current))
        pinned = current.split(b'actions/checkout@', 1)[1][:40]
        for bad in (current.replace(b'contents: read', b'contents: write', 1),
                    current.replace(b'permissions:\n  contents: read\n', b'permissions: write-all\n', 1),
                    current + b'permissions:\n  contents: read\n',
                    current.replace(b'actions/checkout@' + pinned, b'actions/checkout@v4', 1)):
            with self.assertRaises(AssertionError): x.ci_policy(bad)

    def test_m_anchor_pins_reject(self):
        for name, value in (('M_TREE', '0' * 40), ('M_RAW', (1, '0' * 64)), ('CI_PIN', ('100644', '0' * 40, '0' * 64, 1, 1))):
            with patch.object(x, name, value), self.assertRaises(AssertionError): self.selected(self.pure, fresh=True)
