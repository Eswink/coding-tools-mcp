"""Twelve finite Windows verified-launch source-admission cases."""
import ast
from collections import Counter
import copy
import hashlib
import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import rc_pretag_composition_tests as c
import rc_pretag_ownership_profile as o
import rc_pretag_publication_profile as p
import rc_pretag_publication_tests as pt
import rc_pretag_linux_package_cases as lc
import rc_pretag_yoke_repair_profile as y
import rc_pretag_supervisor_readiness_cases as readiness
import rc_pretag_publisher_executor_cases as publisher
import rc_pretag_integration_admission_cases as admission
import rc_pretag_final_admission_cases as final
import rc_pretag_download_budget_cases as download
import rc_pretag_staging_budget_cases as staging
import rc_pretag_checksum_budget_cases as checksum
import rc_pretag_archive_budget_cases as archive
import rc_pretag_staged_bytes_cases as staged
import rc_pretag_stage_retirement_cases as retirement
import rc_pretag_git_budget_cases as git_budget
import rc_pretag_windows_vm_cases as windows_vm
import rc_pretag_source_observation_cases as source_observation
import rc_pretag_source_observation_profile as previous
import rc_pretag_windows_launch_profile as x
# Independent actual-F and loaded historical-inventory bindings.
F_BINDING = ('13cd343d942b7a68912d42a8f9235c02ed647764', 'f2be2e09cca27081cccad11d94ed29858b955df9', ('649dc0fcb0bd299ebf7910e567e09c32b7962a9b', 'af5ca34eebe0a6c1c55153acdd1ef1855df037a9'))
F_RAW = (1236, '7facd10b0d1d2bd44b1cecd637f99a9360acb404a8be5af86cd1731f36933e13')
ENTRY_COUNTS = (1840, 1849)
EXPECTED_CAPS = {
    'src-tauri/Cargo.toml': (100, 3), 'src-tauri/src/tools/windows_vm.rs': (480, 650),
    'src-tauri/src/tools/windows_vm/launch.rs': (495, 495), 'src-tauri/src/tools/windows_vm/image.rs': (285, 285),
    'src-tauri/src/tools/windows_vm/host_io.rs': (450, 450), 'src-tauri/src/tools/windows_vm/launch_tests.rs': (499, 499),
    'src-tauri/src/tools/windows_vm/native_tests.rs': (291, 120), 'scripts/windows_vm_launch_fixture.cpp': (29, 29),
    'scripts/prepare_windows_vm_launch.ps1': (90, 90), '.github/workflows/windows-vm-session.yml': (190, 140),
    'docs/specs/windows-vm-session/requirements.md': (130, 90),
    'docs/specs/windows-vm-session/design.md': (140, 100),
    'docs/specs/windows-vm-session/tasks.md': (170, 110),
    'scripts/rc_pretag_windows_launch_profile.py': (350, 350),
    'scripts/rc_pretag_windows_launch_cases.py': (495, 495),
    'scripts/rc_pretag_source_observation_profile.py': (190, 6),
    'scripts/rc_pretag_source_observation_cases.py': (390, 50),
    'scripts/rc_pretag_windows_vm_cases.py': (351, 6),
    '.github/workflows/issue88-publication-executor.yml': (205, 40),
    'scripts/rc_pretag_authenticated_two_hop_tests.py': (490, 3),
    'scripts/rc_consumer_transport_supervisor_tests.py': (470, 14),
    'scripts/rc_consumer_transport_tests.py': (334, 3),
    'scripts/rc_pretag_staging_budget_cases.py': (390, 3),
    'scripts/rc_pretag_checksum_budget_cases.py': (390, 3),
    'scripts/rc_consumer_fixture_readiness.py': (100, 100),
    'scripts/rc_pretag_archive_budget_cases.py': (399, 3),
}
EXPECTED_PRIOR = {
    '.github/workflows/issue88-publication-executor.yml': (('0bcc32d8c8cf8fe7ae1067bbb7b6cb7ea3fa686f', '7c04fe2a37ce4ad1f8e2dee685e71132ee9660b9acdd84beb678a7d35badefac'), ('2e287f38ffc6cbcdc9da82277bce9e1c25bc7a50', '377086ca7c6edb11fbace99c35340bb4147c2102123d96cd00ef3a3e196f0979'), ('6af82d85156eda76f2fd464a7bd72b1e78ea3e53', '451bbeffce17f243a9f3b02f7e91c03c847e92c62caa2c9d40a3062103354dac'), ('a61797b57dcba000d238dbd2c224247ec077cdbc', '28601d9ded709b55ccad36f966a106e2912d67c48ec47833b9b519e1524045dc'), ('a81e9404bae5e4a56599eb0455026c207acbdc27', 'ef64753deb51f2260812bf136ad4bca0d811bc84e61e601e80697fdef314181c'), ('c1deaabd33200ed0d4795f0e5380a9809192f39e', 'f072b9fd591b9990deb80d7f4d7e45750813f2bea62fd73d0d48b8b13c46d9d0'), ('c6cc466d9d2520b668508e6fbd9754f1ac1cc7ef', '850aea3f1d81c00322f8c8ca1adf84a5abddb5c75d916066394f41a521397e4e'), ('d06143c505bf739dfd4336ea97c20b5850d15128', 'ceb14dd7012995f1d3400e1eb7dfc24533b564cd9a039e2592c74b153d036634'), ('e740760c079a8a831342b3f964f7430dd581002f', 'f0952d0a1238feee4d82f27ccdf725ca4e9cba87e6dedfd493fb2ea015234fd6'), ('e89d4431fa1490187c55970c8626d725c064e5f0', '4159a606e279f3e3b77814e0398f3dc36f302aa5d38f8aa5ca82af3dfca657df'), ('f3cf8b1e3f337204f423ae200e667aaf9d34e3f8', '5fedc956307b75e7d59c3f5aeda153b6e3e64dd618700141862149c3fda37d7a'), ('f76a50f14444f1b1c5959fa27097a85d87bfe8b0', '1ba5c751af0b605efc3f6f8165aa9b97f13d3c93d973493b451cc7bca2c53cff')),
    'scripts/rc_pretag_windows_vm_cases.py': (('5c7f728f2a70ac8e064b270d3960fca41cd21443', 'baf41ff51213f5109cbad49570ec74a50c0784071ff85edcf41c7b0485271e13'),), 'scripts/rc_consumer_transport_supervisor_tests.py': (('e45608f7ae523c25ea5d12cd4d24cbd56a3f1c12', '621c544e5c2062756346cbbd3218a8f7a65ae69bf25fff16ea6746025438e2cb'),),
    'scripts/rc_pretag_staging_budget_cases.py': (('5f0d773cbf81b2650d2a9538aff654bceb05f717', '163ede10fba1845e31bddcc44b814de309fcff438752c5e10471a7cd3c6fdf54'),),
    'scripts/rc_pretag_checksum_budget_cases.py': (('c968e30aeb68cdb23df55d9d6700b01e6ccbf01a', '23ea5f92e7101cfecb94f859956b8cf48982f4de10de1279b0ba8f75a302b4ac'), ('24db3998460a7789d85e93ad131f2a22fed63e46', '86b10cbca916037385d2bb2b0ab5ead39b74ce73141dcdebec38c4c9c056d836')),
    'scripts/rc_pretag_archive_budget_cases.py': (('6e06135e604179635ef670fa32e318f67a03fa20', '90d245703019c8c9aaf5e9147a0df6c1381ce38eec7a2fed2ea0b9be19294f99'),),
}
ORIGINAL_D = (1597, '446bbd979ff7804da23ad9ec41c137dfd0f73c175e91a19be10e671e06cdfa0a')
ORIGINAL_FLOW = (413, '9d39697bc9ed6c2b6d4364f7ea4615c5158430f0179f38438e704178a1aede19')
NEW_TOTALS = (1609, 425)
ADAPTER_METHODS = {
    'setUp': 1, 'test_nineteen_exact_paths_modes_pins_and_entry_count': 2,
    'test_individual_and_aggregate_caps_reject': 1,
    'test_twelve_full_byte_inverses_and_six_dispatch_lines': 1,
    'test_missing_duplicate_outside_and_binary_inverse_changes_reject': 1,
    'test_current_candidate_is_never_cached': 1,
    'test_original1553_strict303_consumer452_ids_and_assertions_are_preserved': 1,
    'test_new44_inventory_early_runtime_workflow_and_exceptional_outcomes': 1,
}
WINDOWS_ADAPTER = 'scripts/rc_pretag_windows_vm_cases.py'
WINDOWS_METHODS = {'test_twenty_four_exact_paths_modes_pins_and_entry_count': 1,
                   'test_new12_inventory_readonly_workflows_and_exceptional_outcomes': 2}
WINDOWS_LINES = {149, 323, 330}
AUTH_ADAPTER = 'scripts/rc_pretag_authenticated_two_hop_tests.py'
AUTH_METHODS = {'test_native_p_sole_parent_tree_and_thirteen_path_delta': 1}
STAGING_ADAPTER = 'scripts/rc_pretag_staging_budget_cases.py'
STAGING_METHODS = {'test_readonly_workflow_and_held_sources_remain_bounded': 1}
CHECKSUM_ADAPTER = 'scripts/rc_pretag_checksum_budget_cases.py'
CHECKSUM_METHODS = {'test_readonly_workflow_and_held_sources_remain_bounded': 1}
ARCHIVE_ADAPTER = 'scripts/rc_pretag_archive_budget_cases.py'
ARCHIVE_METHODS = {'test_readonly_workflow_and_held_sources_remain_bounded': 1}
def inventory():
    x.require_sealed()
    expected = [cls + '.' + name for cls, names in x.NEW_CASES.items() for name in names]
    actual = [item for cls in x.NEW_CASES for item in lc.ids(cls)]
    pt.inventory_ids(expected, 12, x.DIGEST)
    pt.inventory_ids(actual, 12, x.DIGEST)
    assert Counter(actual) == Counter(expected)
    return expected


def execution_valid(loaded, result):
    pt.inventory_ids(loaded, 12, x.DIGEST)
    assert Counter(loaded) == Counter(inventory())
    executed = getattr(result, 'executed_ids', [])
    pt.inventory_ids(executed, 12, x.DIGEST)
    return (result.wasSuccessful() and not result.skipped and not result.expectedFailures
            and not result.unexpectedSuccesses and Counter(executed) == Counter(loaded)
            and result.testsRun == len(set(executed)) == 12)


class WindowsLaunchCompositionCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        x.require_sealed()
        cls.fixture = c._profile_fixture()
        cls.repo, _, commit, blob = cls.fixture.__enter__()
        cls.addClassCleanup(cls.fixture.__exit__, None, None, None)
        cls.commit, cls.blob = staticmethod(commit), staticmethod(blob)
        cls._select, cls._immutable_f = staticmethod(p.selected_profile), {}
        cls.addClassCleanup(cls._immutable_f.clear)

    def setUp(self):
        self.original = c._entries(x.M, self.repo)
        self.good = self.original | {path: ('100644', 'blob', self.blob((c.ROOT / path).read_bytes())) for path in x.CAPS}
        self.pure = self.commit([x.CORRECTION_PARENT], self.good)
        self.feature = self.commit([x.M, self.pure], self.good)
        self.overlay = self.good | c.RELEASE_DOCS
        self.release = self.commit([p.R, self.feature], self.overlay)
        self.args = (self.repo, c._git, c._entries, c._feature_profile, c.RELEASE, c.RELEASE_TREE, dict(c.RELEASE_DOCS))

    def verified_baseline(self, ref, *args, **kwargs):
        callbacks = all(actual is expected for actual, expected in zip(args[1:4], self.args[1:4]))
        binding = (x.M, x.M_TREE, x.M_PARENTS, x.M_RAW)
        raw = (len(x.M_RAW_BYTES), hashlib.sha256(x.M_RAW_BYTES).hexdigest())
        if ref != x.M or binding != (*F_BINDING, F_RAW) or raw != F_RAW or kwargs or not callbacks or args != self.args:
            return self._select(ref, *args, **kwargs)
        key = (ref, *args[:6], tuple(sorted(args[6].items())))
        if key not in self._immutable_f:
            self._immutable_f[key] = dict(self._select(ref, *args))
        return dict(self._immutable_f[key])

    def selected(self, ref, git=c._git, fresh=False):
        args = (self.repo, git, *self.args[2:])
        if fresh:
            return self._select(ref, *args)
        with patch.object(p, 'selected_profile', side_effect=self.verified_baseline):
            return self._select(ref, *args)

    def content(self):
        with patch.object(p, 'selected_profile', side_effect=self.verified_baseline):
            return x.content(self.pure, *self.args)

    def frozen(self, path):
        return c._git('show', x.M + ':' + path, root=self.repo)

    def changed(self, path, data):
        return self.good | {path: ('100644', 'blob', self.blob(data))}

    def bad_content(self, entries, parents=None):
        ref = self.commit([x.CORRECTION_PARENT] if parents is None else parents, entries)
        x.topology(ref, self.repo, c._git, p.R)
        with self.assertRaises(AssertionError):
            self.selected(ref)

    def test_actual_f_identity_and_fresh_historical_validation(self):
        self.assertEqual((x.M, x.M_TREE, x.M_PARENTS), F_BINDING)
        self.assertEqual(x.M_RAW, F_RAW)
        self.assertEqual(c._git('cat-file', 'commit', x.M, root=self.repo), x.M_RAW_BYTES)
        self.assertEqual(self.selected(x.M, fresh=True), self.original)
        self.assertIsNone(x.select(x.M, *self.args))
        with patch.object(previous, 'content', wraps=previous.content) as historical:
            self.assertEqual(self.selected(self.pure, fresh=True), self.good)
            self.assertEqual(self.selected(self.pure, fresh=True), self.good)
            self.assertEqual(historical.call_count, 2)
        for command, replacement in ((('show', '-s', '--format=%P', x.M), b'\n'),
                (('show', '-s', '--format=%P', x.M), ' '.join(reversed(x.M_PARENTS)).encode()),
                (('rev-parse', x.M + '^{tree}'), b'0' * 40), (('cat-file', 'commit', x.M), b'unbound raw')):
            def altered(*args, root):
                return replacement if args == command else c._git(*args, root=root)
            with self.assertRaises(AssertionError):
                self.selected(self.pure, altered, fresh=True)

    def test_exact_ordered_d_i_j_and_four_document_overlay(self):
        with self.assertRaisesRegex(AssertionError, 'unknown_composition_profile'):
            p.selected_profile(self.pure, *self.args, profile='unknown')
        for ref, expected in ((self.pure, self.good), (self.feature, self.good), (self.release, self.overlay)):
            self.assertEqual(self.selected(ref), expected)
        self.assertEqual(x.topology(self.release, self.repo, c._git, p.R), ('release', self.feature, self.pure))
        self.assertEqual(x.CORRECTION_PARENT, '110b4febbbcdab0138e2d28de2a53e2f2d61d7d6')
        self.assertEqual(x.CORRECTION_TREE, '485ef3e3a781201b63d92ea0acf958ac89cc5211')
        self.assertEqual((x.PREVIOUS_PARENT, x.PREVIOUS_TREE), ('0def59d1ac429d5dd53bc4b75b626f5e4811d414', 'fa327d8f1b0caaf73c1d2e55bf67eb887bdbc20f'))
        self.assertEqual((x.EARLIER_PARENT, x.EARLIER_TREE), ('b9b4e666c8bfe8c52e35fba3974c935f927c4e2e', '7faa17400b941a69f366f94e3fcf0272948c65de'))
        self.assertEqual((x.OLDER_PARENT, x.OLDER_TREE), ('8d56fbc38910df36837e1865b4242d55ca2aa7c6', '6a40fb578e807ec8ce58eb309ae62707e1539b04'))
        self.assertEqual(x.INITIAL_PARENT, '750b11b20651b3f8bfadba69c19cb7eaf0c11e1e')
        repaired = self.commit([x.CORRECTION_PARENT], self.good)
        integrated = self.commit([x.M, repaired], self.good)
        overlay = self.commit([p.R, integrated], self.overlay)
        for ref, expected in ((repaired, self.good), (integrated, self.good), (overlay, self.overlay)):
            self.assertEqual(self.selected(ref), expected)
        for parents in ([x.M], [repaired], [x.CORRECTION_PARENT, x.CORRECTION_PARENT], [x.M, x.CORRECTION_PARENT]):
            with self.assertRaises((o.TopologyError, AssertionError)):
                self.selected(self.commit(parents, self.good))
        for command, replacement in ((('show', '-s', '--format=%P', x.CORRECTION_PARENT), b'\n'),
                (('rev-parse', x.CORRECTION_PARENT + '^{tree}'), b'0' * 40),
                (('cat-file', 'commit', x.CORRECTION_PARENT), b'changed commit'),
                (('show', '-s', '--format=%P', x.PREVIOUS_PARENT), b'\n'),
                (('rev-parse', x.PREVIOUS_PARENT + '^{tree}'), b'0' * 40),
                (('cat-file', 'commit', x.PREVIOUS_PARENT), b'changed commit'),
                (('show', '-s', '--format=%P', x.EARLIER_PARENT), b'\n'),
                (('rev-parse', x.EARLIER_PARENT + '^{tree}'), b'0' * 40),
                (('cat-file', 'commit', x.EARLIER_PARENT), b'changed commit'),
                (('show', '-s', '--format=%P', x.OLDER_PARENT), b'\n'),
                (('rev-parse', x.OLDER_PARENT + '^{tree}'), b'0' * 40),
                (('cat-file', 'commit', x.OLDER_PARENT), b'changed commit'),
                (('show', '-s', '--format=%P', x.INITIAL_PARENT), b'\n'),
                (('rev-parse', x.INITIAL_PARENT + '^{tree}'), b'0' * 40),
                (('cat-file', 'commit', x.INITIAL_PARENT), b'changed commit')):
            def altered(*args, root):
                return replacement if args == command else c._git(*args, root=root)
            with self.assertRaises(AssertionError):
                self.selected(repaired, altered)
        for entries in (self.original, self.overlay, self.changed(x.CASES, b'changed')):
            self.bad_content(entries, [x.M, self.pure])
        self.assertEqual((p.R, p.R_TREE, len(c.RELEASE_DOCS)), ('e2e011f7f2a3a1df838bbd588106205b999db610', 'c0dfe00fdcc7ebc8e26acaad5d18ff3f94df9ba3', 4))
        for path in c.RELEASE_DOCS:
            for entries in (self.overlay | {path: self.good[path]}, {k: v for k, v in self.overlay.items() if k != path}, self.overlay | {path: ('100755', *self.overlay[path][1:])}):
                self.bad_content(entries, [p.R, self.feature])
        self.bad_content(self.overlay | {'extra.md': ('100644', 'blob', self.blob(b'extra'))}, [p.R, self.feature])

    def test_wrong_repeated_nested_and_same_tree_topologies_reject(self):
        impostor, correction = self.commit([], self.original), self.commit([self.pure], self.good)
        for parents in ([], [self.pure], [self.pure, x.M], [x.M, self.pure, p.R], [x.M, x.M], [x.M, self.feature], [p.R], [p.R, self.pure], [self.feature, p.R], [p.R, self.feature, self.pure], [p.R, self.release], [impostor], [impostor, self.pure], [correction], [x.M, correction], [previous.M, self.pure]):
            ref = self.commit(parents, self.good)
            with self.assertRaises(o.TopologyError):
                x.topology(ref, self.repo, c._git, p.R)
            with patch.object(x, 'content') as content:
                self.assertIsNone(x.select(ref, *self.args))
            content.assert_not_called()
            with self.assertRaises(AssertionError):
                self.selected(ref)
        calls = []
        def moving(*args, root):
            calls.append(args)
            if args == ('rev-parse', '--verify', 'moving^{commit}'):
                return ((self.pure if calls.count(args) == 1 else self.release) + '\n').encode()
            return c._git(*args, root=root)
        with patch.dict(os.environ, {'GIT_DIR': '/absent', 'GIT_INDEX_FILE': '/absent', 'GIT_NO_REPLACE_OBJECTS': '0'}):
            self.assertEqual(self.selected('moving', moving), self.good)
        self.assertEqual(sum(any('moving' in arg for arg in args) for args in calls), 1)

    def test_nineteen_exact_paths_modes_pins_and_entry_count(self):
        self.assertEqual(self.content(), self.good)
        self.assertEqual((len(self.original), len(self.good)), ENTRY_COUNTS)
        self.assertEqual((len(x.CAPS), len(x.BASE_PINS), len(self.good.keys() - self.original.keys())), (26, 17, 9))
        self.assertEqual(x.CAPS, EXPECTED_CAPS)
        self.assertEqual(x.SOURCE_PINS.keys(), x.CAPS.keys() - {x.PROFILE})
        self.assertEqual(self.good[x.PROFILE][2], c._blob((c.ROOT / x.PROFILE).read_bytes()))
        for path, row in x.SOURCE_PINS.items():
            data = (c.ROOT / path).read_bytes()
            self.assertEqual(row, ('100644', *o.pin(data), len(data), len(data.splitlines())))
            for index, value in enumerate(('100755', '0' * 40, '0' * 64, row[3] + 1, row[4] + 1)):
                changed = list(row)
                changed[index] = value
                with patch.dict(x.SOURCE_PINS, {path: tuple(changed)}), self.assertRaises(AssertionError):
                    self.content()
            self.bad_content(self.changed(path, data + b'\n'))
        for pins in ({k: v for k, v in x.SOURCE_PINS.items() if k != x.CASES}, x.SOURCE_PINS | {'extra': row}):
            with patch.dict(x.SOURCE_PINS, pins, clear=True), self.assertRaises(AssertionError):
                self.content()
        for path in x.CAPS:
            missing = {k: v for k, v in self.good.items() if k != path}
            self.bad_content(missing)
            self.bad_content(missing | {path + '.renamed': self.good[path]})
            for entry in (('100755', *self.good[path][1:]), ('120000', 'blob', self.blob(b'target')), ('160000', 'commit', x.M)):
                self.bad_content(self.good | {path: entry})
        self.bad_content(self.changed('unreviewed-extra.py', b'extra'))
        for path in ('src-tauri/src/tools/windows_vm/protocol.rs', 'src-tauri/src/tools/windows_vm/tests.rs', 'src-tauri/src/tools/native_drain.rs', 'src-tauri/Cargo.lock', 'services/windows-vm-broker/main_windows.go'):
            self.assertNotIn(path, x.CAPS)
            self.assertEqual(self.good[path], self.original[path])
            self.bad_content(self.changed(path, b'changed'))

    def test_individual_and_aggregate_caps_reject(self):
        self.assertEqual(x.DELTA_LIMIT, 3800)
        data = {path: (c.ROOT / path).read_bytes() for path in x.CAPS}
        def budgets(git=c._git):
            return p.authenticated._budgets(self.pure, x.M, self.repo, git, data, x.CAPS, x.DELTA_LIMIT, 'windows_launch_delta_budget')
        budgets()
        for path, (_, delta) in x.CAPS.items():
            with patch.dict(x.CAPS, {path: (len(data[path].splitlines()) - 1, delta)}), self.assertRaises(AssertionError):
                budgets()
            for row in (f'{delta + 1}\t0\t{path}\n'.encode(), b'', b'-\t-\t' + path.encode(), b'1\t0', b'1\t0\twrong', f'1\t0\t{path}\nextra\n'.encode(), f'-1\t0\t{path}\n'.encode()):
                def malformed(*args, root):
                    return row if args == ('diff', '--numstat', x.M, self.pure, '--', path) else c._git(*args, root=root)
                with self.assertRaises(AssertionError):
                    budgets(malformed)
        with patch.object(x, 'DELTA_LIMIT', 0), self.assertRaisesRegex(AssertionError, 'windows_launch_delta_budget'):
            budgets()

    def test_eleven_full_byte_inverses_and_six_dispatch_lines(self):
        self.assertEqual((len(x.DISPATCH.splitlines()), len(x.NORMALIZE.splitlines())), (4, 2))
        self.assertEqual(x.FRAGMENTS.keys(), x.BASE_PINS.keys())
        self.assertEqual(len(x.FRAGMENTS), 17)
        for path in x.BASE_PINS:
            current, frozen = (c.ROOT / path).read_bytes(), self.frozen(path)
            with patch('builtins.open', side_effect=AssertionError('IO')), patch('io.open', side_effect=AssertionError('IO')), patch('subprocess.Popen', side_effect=AssertionError('process')), patch('tempfile.TemporaryDirectory', side_effect=AssertionError('extract')):
                self.assertEqual(x.normalize(path, current), frozen, path)
                self.assertEqual(x.normalize(path, frozen), frozen, path)
        current = (c.ROOT / x.DISPATCHER).read_bytes()
        self.assertEqual((current.count(x.DISPATCH), current.count(x.NORMALIZE)), (1, 1))
        self.assertEqual(current.replace(x.DISPATCH, b'', 1).replace(x.NORMALIZE, b'', 1), self.frozen(x.DISPATCHER))
        self.assertEqual(c._git('diff', '--numstat', x.M, self.pure, '--', x.DISPATCHER, root=self.repo), f'6\t0\t{x.DISPATCHER}\n'.encode())
        self.assertEqual(x.normalize('unmapped', b'unchanged'), b'unchanged')

    def test_finite_historical_identities_are_exact_and_immutable(self):
        self.assertEqual(x.PRIOR_PINS, EXPECTED_PRIOR)
        for path, pins in x.PRIOR_PINS.items():
            self.assertEqual(len(pins), len(set(pins)))
            self.assertNotIn(x.BASE_PINS[path][1:3], pins)
            for pin in pins:
                prior = c._git('cat-file', 'blob', pin[0], root=self.repo)
                self.assertEqual(o.pin(prior), pin)
                self.assertEqual(x.normalize(path, prior), prior)
                for bad in (prior + b'# outside\n', b'\xff' + prior):
                    with self.assertRaises(AssertionError):
                        x.normalize(path, bad)

    def test_missing_duplicate_outside_and_binary_inverse_changes_reject(self):
        for path, fragments in x.FRAGMENTS.items():
            current = (c.ROOT / path).read_bytes()
            altered = [current + b'# outside\n', b'\xff']
            weakened = current.replace(b'self.assertEqual(', b'self.assertNotEqual(', 1)
            if weakened == current:
                weakened = current.replace(b'assert ', b'assert False and ', 1)
            if weakened != current:
                altered.append(weakened)
            for before, _ in fragments:
                self.assertEqual(current.count(before), 1)
                altered.extend((current.replace(before, b'', 1), current.replace(before, before * 2, 1)))
            for data in altered:
                if o.pin(data) in (x.BASE_PINS[path][1:3], *x.PRIOR_PINS.get(path, ())):
                    data += b'# not prior\n'
                row = ('100644', *o.pin(data), len(data), len(data.splitlines()))
                with patch.dict(x.SOURCE_PINS, {path: row}), self.assertRaises(AssertionError):
                    x.normalize(path, data)
        for path, data in ((None, b'x'), (x.DISPATCHER, 'text')):
            with self.assertRaises(AssertionError):
                x.normalize(path, data)

    def test_selected_historical_and_release_failures_are_terminal(self):
        for error in (AssertionError, o.TopologyError):
            with patch.object(x, 'content', side_effect=error('selected terminal')), patch.object(previous, 'content') as old, self.assertRaisesRegex(error, 'selected terminal'):
                self.selected(self.pure, fresh=True)
            old.assert_not_called()
            with patch.object(previous, 'content', side_effect=error('historical terminal')), patch.object(o, 'selected_profile') as fallback, self.assertRaisesRegex(error, 'historical terminal'):
                self.selected(self.pure, fresh=True)
            fallback.assert_not_called()
            with patch.object(x, 'content', return_value=self.good), patch.object(o, 'release_content', side_effect=error('release terminal')), self.assertRaisesRegex(error, 'release terminal'):
                self.selected(self.release, fresh=True)
        for offset, value in ((4, '0' * 40), (5, '0' * 40), (6, {})):
            args = list(self.args)
            args[offset] = value
            self.assertIsNone(x.select(x.M, *args))
            with self.assertRaises(AssertionError):
                x.select(self.pure, *args)
        with patch.object(p.authenticated, '_budgets', side_effect=AssertionError('budget terminal')), self.assertRaisesRegex(AssertionError, 'budget terminal'):
            self.content()

    def test_current_candidate_is_never_cached(self):
        with patch.object(x, 'content', wraps=x.content) as checked:
            self.assertEqual(self.selected(self.pure), self.good)
            self.assertEqual(self.selected(self.pure), self.good)
            self.assertEqual(checked.call_count, 2)
        returned = self.selected(self.pure)
        returned.clear()
        self.assertEqual(self.selected(self.pure), self.good)
        self.bad_content(self.changed(x.CASES, b'changed after validation'))
        baseline = self.verified_baseline(x.M, *self.args)
        baseline.clear()
        self.assertEqual(self.verified_baseline(x.M, *self.args), self.original)
        for offset, value in ((2, lambda ref, root: {}), (3, lambda ref, root: {}), (5, '0' * 40), (6, {})):
            args = list(self.args)
            args[offset] = value
            with patch.object(self, '_select', side_effect=AssertionError('fresh required')) as fresh, self.assertRaisesRegex(AssertionError, 'fresh required'):
                self.verified_baseline(x.M, *args)
            fresh.assert_called_once()
        for field, value in (('M_TREE', '0' * 40), ('M_RAW', (0, 'bad')), ('M_RAW_BYTES', b'bad')):
            with patch.object(x, field, value), patch.object(self, '_select', side_effect=AssertionError('fresh required')), self.assertRaisesRegex(AssertionError, 'fresh required'):
                self.verified_baseline(x.M, *self.args)
        runtime = ast.parse((c.ROOT / x.PROFILE).read_bytes())
        self.assertFalse(any('cache' in (getattr(n, 'id', getattr(n, 'attr', getattr(n, 'name', ''))) or '') for n in ast.walk(runtime)))

    def test_original1597_strict303_consumer452_ids_and_assertions_are_preserved(self):
        original = [item for group in lc.GROUPS for item in lc.inventory(group)] + lc.ids(y.CLASS)
        groups = (publisher, admission, final, download, staging, checksum, archive, staged)
        flow = [item for group in groups for item in group.inventory()]
        flow += readiness.inventory() + retirement.inventory() + git_budget.inventory() + windows_vm.inventory() + source_observation.inventory()
        original += flow
        pt.inventory_ids(original, *ORIGINAL_D)
        pt.inventory_ids(flow, *ORIGINAL_FLOW)
        self.assertEqual((len(set(original + inventory())), len(set(flow + inventory()))), NEW_TOTALS)
        self.assertFalse(set(original) & set(inventory()))
        method = next(n for n in ast.walk(ast.parse(self.frozen(p.TESTS))) if isinstance(n, ast.FunctionDef) and n.name == 'test_protected_source_versions_gates_workflows_and_old_452_are_unchanged')
        modules = ast.literal_eval(method.body[0].value.func.value).split()
        with patch('tempfile.TemporaryDirectory', side_effect=AssertionError('discovery materialized')):
            strict = [test.id() for test in c._flatten(unittest.defaultTestLoader.discover(str(c.ROOT / 'scripts'), pattern='rc_pretag*_tests.py'))]
            consumer = [item for module in modules for item in lc.ids(module) if item.split('.', 1)[0] == module]
        pt.inventory_ids(strict, 303, '0ecc366c2018a6a1e20d3f59ed9ca66645d9334324cd517682894cabde923125')
        pt.inventory_ids(consumer, 452, 'd01db4e6cd605c6636423e27c8c0409e90aba217cc0e6930474f59a24b57f372')
        self.assertEqual(len(set(strict + consumer)), 755)
        def methods(data):
            return {(cls.name, n.name): n for cls in ast.parse(data).body if isinstance(cls, ast.ClassDef) for n in cls.body if isinstance(n, ast.FunctionDef)}
        def assertions(node):
            return Counter(ast.dump(a) for a in ast.walk(node) if isinstance(a, ast.Call) and isinstance(a.func, ast.Attribute) and (a.func.attr.startswith('assert') or a.func.attr == 'fail'))
        class UndoOperands(ast.NodeTransformer):
            def __init__(self, path):
                self.count = 0
                self.alias = 'source_observation_bytes' if path == WINDOWS_ADAPTER else 'windows_launch_bytes'
                self.lines = WINDOWS_LINES if path == WINDOWS_ADAPTER else None
            def visit_Call(self, node):
                eligible = self.lines is None or node.lineno in self.lines
                decoded = (eligible and isinstance(node.func, ast.Attribute) and node.func.attr == 'decode' and isinstance(node.func.value, ast.Call) and isinstance(node.func.value.func, ast.Name) and node.func.value.func.id == self.alias and not node.args and not node.keywords)
                node = self.generic_visit(node)
                if decoded:
                    source = node.func.value
                    assert isinstance(source, ast.Call) and isinstance(source.func, ast.Attribute)
                    assert source.func.attr == 'read_bytes' and not source.args and not source.keywords
                    source.func.attr = 'read_text'
                    return source
                if eligible and isinstance(node.func, ast.Name) and node.func.id == self.alias:
                    assert len(node.args) == 2 and not node.keywords
                    self.count += 1
                    return node.args[1]
                return node
        changed = {x.ADAPTER: {}, WINDOWS_ADAPTER: {}, AUTH_ADAPTER: {}, STAGING_ADAPTER: {}, CHECKSUM_ADAPTER: {}, ARCHIVE_ADAPTER: {}}
        for module in {item.split('.', 1)[0] for item in original}:
            path = 'scripts/' + module + '.py'
            current, frozen = (c.ROOT / path).read_bytes(), self.frozen(path)
            self.assertEqual(x.normalize(path, current), frozen, path)
            before, after = methods(frozen), methods(current)
            self.assertEqual(before.keys(), after.keys(), path)
            for key, method in before.items():
                undo = UndoOperands(path)
                adjusted = undo.visit(copy.deepcopy(after[key])) if path in changed else after[key]
                self.assertEqual(assertions(method), assertions(adjusted), (path, key))
                self.assertEqual(ast.dump(method), ast.dump(adjusted), (path, key))
                if undo.count:
                    expected_class = {WINDOWS_ADAPTER: 'WindowsVmCompositionCases', x.ADAPTER: 'SourceObservationCompositionCases', AUTH_ADAPTER: 'AuthenticatedTwoHopCompositionTests', STAGING_ADAPTER: 'StagingBudgetCompositionCases', CHECKSUM_ADAPTER: 'ChecksumBudgetCompositionCases', ARCHIVE_ADAPTER: 'ArchiveBudgetCompositionCases'}[path]
                    self.assertEqual(key[0], expected_class)
                    changed[path][key[1]] = undo.count
        self.assertEqual(changed, {x.ADAPTER: ADAPTER_METHODS, WINDOWS_ADAPTER: WINDOWS_METHODS, AUTH_ADAPTER: AUTH_METHODS, STAGING_ADAPTER: STAGING_METHODS, CHECKSUM_ADAPTER: CHECKSUM_METHODS, ARCHIVE_ADAPTER: ARCHIVE_METHODS})
        self.assertEqual(sum(sum(methods.values()) for methods in changed.values()), 16)

    def test_new12_inventory_readonly_workflows_and_exceptional_outcomes(self):
        text = (c.ROOT / x.WORKFLOW).read_text()
        self.assertEqual(x.normalize(x.WORKFLOW, text.encode()), self.frozen(x.WORKFLOW))
        for fragment in ("branches: ['ci/issue88-publisher-executor-*']", 'permissions:\n  contents: read', 'timeout-minutes: 30', 'frozen four hundred twenty five cases', 'import rc_pretag_windows_launch_profile as profile', 'windows_launch.inventory()', 'windows_launch.execution_valid(loaded, result)', 'windows-launch-cases.log', 'windows-launch-inventory.json', 'parents == [profile.CORRECTION_PARENT]', 'checked() == before', "'production_ready': False"):
            self.assertIn(fragment, text)
        for group in ('x', 'admission', 'final_admission', 'download_budget', 'staging_budget', 'checksum_budget', 'archive_budget', 'staged_bytes', 'supervisor_readiness', 'stage_retirement', 'git_budget', 'windows_vm', 'source_observation', 'windows_launch'):
            self.assertEqual(text.count('names = ' + group + '.inventory()'), 1)
            self.assertEqual(text.count('assert ' + group + '.execution_valid(loaded, result)'), 1)
        for earlier, later in (('windows_launch', 'source_observation'), ('source_observation', 'git_budget'), ('git_budget', 'staging_budget'), ('staging_budget', 'x')):
            self.assertLess(text.index('names = ' + earlier + '.inventory()'), text.index('names = ' + later + '.inventory()'))
        native = (c.ROOT / x.NATIVE_WORKFLOW).read_text()
        for fragment in ("$base='" + x.CORRECTION_PARENT + "'", "if ($base -cnotmatch '^[0-9a-f]{40}$' -or $parents -cne $base)", '16 passed; 0 failed; 0 ignored', '2 passed; 0 failed; 6 ignored', '6 passed; 0 failed; 0 ignored', '2 passed; 0 failed; 0 ignored', 'exact 38 executed outcomes required', '--test-threads=1', '8MB', '2MB'):
            self.assertIn(fragment, native)
        self.assertNotIn('UNSEALED', native)
        self.assertLess(native.index('six actual launch cases required before import'), native.index('-Phase acquire'))
        self.assertLess(native.index('-Phase acquire'), native.index('tools::windows_vm::native_tests:: -- --ignored'))
        for flag in ('production_admission', 'workspace_integration', 'network_denial_proven', 'production_launch_authority', 'general_dll_authority', 'descendant_containment_by_debugger', 'hard_syscall_deadline'):
            self.assertIn(flag + '=$false', native)
        for forbidden in ('secrets.', 'GH_TOKEN', 'GITHUB_TOKEN', 'contents: write', 'workflow_dispatch:', 'pull_request:', 'gh release', 'curl ', 'pip install'):
            self.assertNotIn(forbidden, text)
            self.assertNotIn(forbidden, native)
        loaded = inventory()
        good = dict(executed_ids=loaded, testsRun=12, skipped=[], expectedFailures=[], unexpectedSuccesses=[], wasSuccessful=lambda: True)
        self.assertTrue(execution_valid(loaded, SimpleNamespace(**good)))
        for field, value in (('skipped', [('id', 'reason')]), ('expectedFailures', [('id', 'failure')]), ('unexpectedSuccesses', ['id']), ('testsRun', 11), ('wasSuccessful', lambda: False)):
            self.assertFalse(execution_valid(loaded, SimpleNamespace(**(good | {field: value}))))
        for invalid in (loaded[:-1], loaded + loaded[:1], loaded[:-1] + ['unknown']):
            with self.assertRaises(AssertionError):
                execution_valid(invalid, SimpleNamespace(**good))
            with self.assertRaises(AssertionError):
                execution_valid(loaded, SimpleNamespace(**(good | {'executed_ids': invalid})))


def main():
    x.require_sealed()
    suite = unittest.defaultTestLoader.loadTestsFromNames(inventory())
    loaded = [test.id() for test in c._flatten(suite)]
    result = unittest.TextTestRunner(verbosity=2, resultclass=c.InventoryResult).run(suite)
    print(json.dumps(dict(loaded_ids=loaded, executed_ids=getattr(result, 'executed_ids', []), loaded=len(loaded), executed=result.testsRun)))
    return 0 if execution_valid(loaded, result) else 1


if __name__ == '__main__':
    raise SystemExit(main())
