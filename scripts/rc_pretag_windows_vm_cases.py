"""Finite Windows VM engineering admission; modeled source checks confer no release authority."""
import ast
from collections import Counter
import copy
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
import rc_pretag_git_budget_profile as previous
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
import rc_pretag_windows_vm_profile as x

F_BINDING = ('7eb98b76a15f91d2ad59ec8fbde4dd4fb17b1116', '2862d635ab7ce082ad863d9315514537df8864f1', ('8bdd5f327b4603c5570dc764e2d62fecbe6e02d2', '76949e7e496ee4a5a3a7554d26e2cd67691f07e0'))
F_RAW = (1227, '38f560ddd99ace241b4925b558ddb386ec45f40fac111e9134a574be1f73901c')
ADAPTER = 'scripts/rc_pretag_git_budget_cases.py'

def inventory():
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

class WindowsVmCompositionCases(unittest.TestCase):
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
        if key not in self._immutable_f:
            self._immutable_f[key] = dict(self._select(ref, *args))
        return dict(self._immutable_f[key])
    def selected(self, ref, git=c._git, fresh=False):
        args = (self.repo, git, *self.args[2:])
        if fresh: return self._select(ref, *args)
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
        ref = self.commit([x.M] if parents is None else parents, entries)
        x.topology(ref, self.repo, c._git, p.R)
        with self.assertRaises(AssertionError): self.selected(ref)

    def test_actual_f_identity_and_fresh_historical_validation(self):
        self.assertEqual((x.M, x.M_TREE, x.M_PARENTS), F_BINDING)
        self.assertEqual(x.M_RAW, F_RAW)
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
            with self.assertRaises(AssertionError): self.selected(self.pure, altered, fresh=True)

    def test_exact_ordered_d_i_j_and_four_document_overlay(self):
        with self.assertRaisesRegex(AssertionError, 'unknown_composition_profile'):
            self._select(self.pure, *self.args, profile='unknown')
        for ref, expected in ((self.pure, self.good), (self.feature, self.good), (self.release, self.overlay)):
            self.assertEqual(self.selected(ref), expected)
        self.assertEqual(x.topology(self.release, self.repo, c._git, p.R), ('release', self.feature, self.pure))
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
            with self.assertRaises(o.TopologyError): x.topology(ref, self.repo, c._git, p.R)
            with patch.object(x, 'content') as content: self.assertIsNone(x.select(ref, *self.args))
            content.assert_not_called()
            with self.assertRaises(AssertionError): self.selected(ref)
        with self.assertRaises(o.TopologyError): x.topology(self.pure, self.repo, c._git, impostor)
        calls = []
        def moving(*args, root):
            calls.append(args)
            if args == ('rev-parse', '--verify', 'moving^{commit}'):
                return ((self.pure if calls.count(args) == 1 else self.release) + '\n').encode()
            return c._git(*args, root=root)
        with patch.dict(os.environ, {'GIT_DIR': '/absent', 'GIT_INDEX_FILE': '/absent', 'GIT_NO_REPLACE_OBJECTS': '0'}):
            self.assertEqual(self.selected('moving', moving, fresh=True), self.good)
        self.assertEqual(sum(any('moving' in arg for arg in args) for args in calls), 1)

    def test_twenty_four_exact_paths_modes_pins_and_entry_count(self):
        self.assertEqual(self.content(), self.good)
        self.assertEqual((len(self.original), len(self.good), len(x.CAPS), len(x.BASE_PINS)), (1813, 1833, 24, 4))
        self.assertEqual(x.SOURCE_PINS.keys(), x.CAPS.keys() - {x.PROFILE})
        self.assertEqual(x.CAPS, {'src-tauri/src/tools/mod.rs': (50, 3), 'src-tauri/src/tools/windows_vm.rs': (350, 350), 'src-tauri/src/tools/windows_vm/protocol.rs': (495, 495), 'src-tauri/src/tools/windows_vm/tests.rs': (480, 480), 'src-tauri/src/tools/windows_vm/native_tests.rs': (240, 240), 'services/windows-vm-broker/main_windows.go': (190, 190), 'services/windows-vm-broker/owner_windows.go': (330, 330), 'services/windows-vm-broker/channels_windows.go': (215, 215), 'services/windows-vm-broker/guest_windows.go': (150, 150), 'services/windows-vm-broker/protocol_windows.go': (280, 280), 'services/windows-vm-broker/quarantine_windows.go': (200, 200), 'services/windows-vm-broker/owner_windows_test.go': (480, 480), 'services/windows-vm-broker/upstream-defaults.patch': (12, 12), 'services/windows-vm-broker/inputs.json': (40, 40), 'scripts/prepare_windows_vm_session.ps1': (105, 105), '.github/workflows/windows-vm-session.yml': (120, 120), 'docs/specs/windows-vm-session/requirements.md': (100, 100), 'docs/specs/windows-vm-session/design.md': (100, 100), 'docs/specs/windows-vm-session/tasks.md': (100, 100), 'scripts/rc_pretag_windows_vm_profile.py': (350, 350), 'scripts/rc_pretag_windows_vm_cases.py': (450, 450), 'scripts/rc_pretag_git_budget_profile.py': (220, 6), 'scripts/rc_pretag_git_budget_cases.py': (365, 24), '.github/workflows/issue88-publication-executor.yml': (185, 14)})
        self.assertEqual(self.good[x.PROFILE][2], c._blob((c.ROOT / x.PROFILE).read_bytes()))
        donor = {'src-tauri/src/tools/mod.rs': ('c38339b3654295539d1fe293f5a88710ebb6dd23', 'd6c2feb9e7e161188f10dd00fb66206b7c98c978f7d511c55904b798448041ea'), 'src-tauri/src/tools/windows_vm.rs': ('5075599be11ba7e18030912c260bb3f08e8d1b59', 'bf003ec6d4afc3e1fa4edc6fb678ff9b876033074f1d494dd3af0a4032641c95'), 'src-tauri/src/tools/windows_vm/protocol.rs': ('c3b1ebe0d9662574a5dd9282b8f1e5393cbdb835', '2e71022fd52dc66b4df5df0bfed731290de8f2c40fa98b6a6325bddbdf779a01'), 'src-tauri/src/tools/windows_vm/tests.rs': ('455a5f96dd5669593ff3605d331d2b091ccd0b0d', '88f3281578ad21ac756ed43e6f237606137fff78aa491df2fece32a642b098fc'), 'src-tauri/src/tools/windows_vm/native_tests.rs': ('d4191eace9841157b3de6034df1f21313401facd', '45c16f4c1c1b9038bf4dc5f54f38959063738f3b3f568ba29fe9a10a7504161b'), 'services/windows-vm-broker/main_windows.go': ('2fa50dc729fe000b1c8564c0f753877f0ae077f1', '3ea09fa942a7b3e7f2a2a3bd611adaf43c8b4353887bfbd2788a5fe4326b4d20'), 'services/windows-vm-broker/owner_windows.go': ('a1dfab60b966f375e316ebcd22d3fcd35bfb8b92', 'b462eac0a390afac06b48d783a6cccaddcc550da1ee238214e13979647b9ff8c'), 'services/windows-vm-broker/channels_windows.go': ('7465847b52ad8d820b7c0743ef742955308a7e9e', 'cb38b7dcdd809d2418a51b58860e908df1a4b9a7ca965f152d3fd19186c0b9c9'), 'services/windows-vm-broker/guest_windows.go': ('82f249fb00aea1ef2d5db5866e3e117282532be9', '72b681ccd4f19eadbc9ff1fce7e1302c0848114ab71115e321ad337cba0cbc46'), 'services/windows-vm-broker/protocol_windows.go': ('a84c37934000e72f88ac1658fc169b7bce415071', 'a03ae3062d397c3e9b1079077e3ed33904c684642798e003055ef01e5aafcdd1'), 'services/windows-vm-broker/quarantine_windows.go': ('790243e13a58cbae58f042398ba7041180d90926', '6c7e4df40d2d274c2b522aa6612f31af907c95284b3a8cb894adbe976c7d51d7'), 'services/windows-vm-broker/owner_windows_test.go': ('25b0a56d4d28bad9fbd3ccabd6436d528dfc726b', '1655256cad53f27bdf83714eb2bc99af7ebe69a05959bd022b13ee5938e948fa'), 'services/windows-vm-broker/upstream-defaults.patch': ('8c64fa80f3767ef1dca1746d6f618372301bc0cd', 'baebb4177f2f972022dbef62299b81596fef0ee23d40b1bd8b4ad71e7f5290b0'), 'services/windows-vm-broker/inputs.json': ('d7a0c5d717b77499bfbc821622873d3394c3f6f1', '32b8b25c35024830d09cd7257fcac4d05117820ef0850a96733445d804847850'), 'scripts/prepare_windows_vm_session.ps1': ('a38a7ee2a9627a0a45f123ae08b57de5018e6c5e', '58157c707608ed4e83055cb0fea9fa0083f424086cdf79055172becee98eae01')}
        for path, pin in donor.items(): self.assertEqual(o.pin((c.ROOT / path).read_bytes()), pin, path)
        for path, row in x.SOURCE_PINS.items():
            data = (c.ROOT / path).read_bytes()
            self.assertEqual(row, ('100644', *o.pin(data), len(data), len(data.splitlines())))
            for index, value in enumerate(('100755', '0' * 40, '0' * 64, row[3] + 1, row[4] + 1)):
                changed = list(row); changed[index] = value
                with patch.dict(x.SOURCE_PINS, {path: tuple(changed)}), self.assertRaises(AssertionError): self.content()
            self.bad_content(self.changed(path, data + b'\n'))
        for pins in ({k: v for k, v in x.SOURCE_PINS.items() if k != x.CASES}, x.SOURCE_PINS | {'extra': row}):
            with patch.dict(x.SOURCE_PINS, pins, clear=True), self.assertRaises(AssertionError): self.content()
        for path in x.CAPS:
            missing = {k: v for k, v in self.good.items() if k != path}
            self.bad_content(missing); self.bad_content(missing | {path + '.renamed': self.good[path]})
            for entry in (('100755', *self.good[path][1:]), ('120000', 'blob', self.blob(b'target')), ('160000', 'commit', x.M)):
                self.bad_content(self.good | {path: entry})
        self.bad_content(self.changed('unreviewed-extra.py', b'extra'))
        self.bad_content(self.changed('services/cloud-agent/src/main.rs', b'changed'))

    def test_individual_and_aggregate_caps_reject(self):
        self.assertEqual((x.DELTA_LIMIT, sum(cap[1] for cap in x.CAPS.values())), (4700, 4834))
        data = {path: (c.ROOT / path).read_bytes() for path in x.CAPS}
        def budgets(git=c._git):
            return p.authenticated._budgets(self.pure, x.M, self.repo, git, data, x.CAPS, x.DELTA_LIMIT, 'windows_vm_delta_budget')
        budgets()
        for path, (_, delta) in x.CAPS.items():
            with patch.dict(x.CAPS, {path: (len(data[path].splitlines()) - 1, delta)}), self.assertRaises(AssertionError): budgets()
            for row in (f'{delta + 1}\t0\t{path}\n'.encode(), b'', b'-\t-\t' + path.encode(), b'1\t0', b'1\t0\twrong', f'1\t0\t{path}\nextra\n'.encode(), f'-1\t0\t{path}\n'.encode()):
                def malformed(*args, root):
                    return row if args == ('diff', '--numstat', x.M, self.pure, '--', path) else c._git(*args, root=root)
                with self.assertRaises(AssertionError): budgets(malformed)
        with patch.object(x, 'DELTA_LIMIT', 0), self.assertRaisesRegex(AssertionError, 'windows_vm_delta_budget'): budgets()

    def test_four_full_byte_inverses_and_six_dispatch_lines(self):
        self.assertEqual((len(x.DISPATCH.splitlines()), len(x.NORMALIZE.splitlines())), (4, 2))
        self.assertEqual(x.FRAGMENTS.keys(), x.BASE_PINS.keys())
        self.assertEqual(len(x.FRAGMENTS), 4)
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

    def test_ten_historical_workflow_identities_are_finite_and_immutable(self):
        self.assertEqual({path: len(pins) for path, pins in x.PRIOR_PINS.items()}, {x.WORKFLOW: 10})
        expected = {'.github/workflows/issue88-publication-executor.yml': (('2e287f38ffc6cbcdc9da82277bce9e1c25bc7a50', '377086ca7c6edb11fbace99c35340bb4147c2102123d96cd00ef3a3e196f0979'), ('6af82d85156eda76f2fd464a7bd72b1e78ea3e53', '451bbeffce17f243a9f3b02f7e91c03c847e92c62caa2c9d40a3062103354dac'), ('a61797b57dcba000d238dbd2c224247ec077cdbc', '28601d9ded709b55ccad36f966a106e2912d67c48ec47833b9b519e1524045dc'), ('a81e9404bae5e4a56599eb0455026c207acbdc27', 'ef64753deb51f2260812bf136ad4bca0d811bc84e61e601e80697fdef314181c'), ('c6cc466d9d2520b668508e6fbd9754f1ac1cc7ef', '850aea3f1d81c00322f8c8ca1adf84a5abddb5c75d916066394f41a521397e4e'), ('d06143c505bf739dfd4336ea97c20b5850d15128', 'ceb14dd7012995f1d3400e1eb7dfc24533b564cd9a039e2592c74b153d036634'), ('e740760c079a8a831342b3f964f7430dd581002f', 'f0952d0a1238feee4d82f27ccdf725ca4e9cba87e6dedfd493fb2ea015234fd6'), ('f3cf8b1e3f337204f423ae200e667aaf9d34e3f8', '5fedc956307b75e7d59c3f5aeda153b6e3e64dd618700141862149c3fda37d7a'), ('f76a50f14444f1b1c5959fa27097a85d87bfe8b0', '1ba5c751af0b605efc3f6f8165aa9b97f13d3c93d973493b451cc7bca2c53cff'), ('e89d4431fa1490187c55970c8626d725c064e5f0', '4159a606e279f3e3b77814e0398f3dc36f302aa5d38f8aa5ca82af3dfca657df'))}
        self.assertEqual(x.PRIOR_PINS, expected)
        for path, pins in x.PRIOR_PINS.items():
            self.assertEqual(len(pins), len(set(pins))); self.assertNotIn(x.BASE_PINS[path][1:3], pins)
            for pin in pins:
                prior = c._git('cat-file', 'blob', pin[0], root=self.repo)
                self.assertEqual(o.pin(prior), pin); self.assertEqual(x.normalize(path, prior), prior)
                for bad in (prior + b'# outside\n', b'\xff' + prior):
                    with self.assertRaises(AssertionError): x.normalize(path, bad)

    def test_missing_duplicate_outside_and_binary_inverse_changes_reject(self):
        for path, fragments in x.FRAGMENTS.items():
            current = (c.ROOT / path).read_bytes()
            altered = [current + b'# outside\n', b'\xff']
            weakened = current.replace(b'self.assertEqual(', b'self.assertNotEqual(', 1)
            if weakened == current: weakened = current.replace(b'assert ', b'assert False and ', 1)
            if weakened != current: altered.append(weakened)
            for before, _ in fragments:
                self.assertEqual(current.count(before), 1)
                altered.extend((current.replace(before, b'', 1), current.replace(before, before * 2, 1)))
            for data in altered:
                if o.pin(data) in (x.BASE_PINS[path][1:3], *x.PRIOR_PINS.get(path, ())): data += b'# not prior\n'
                row = ('100644', *o.pin(data), len(data), len(data.splitlines()))
                with patch.dict(x.SOURCE_PINS, {path: row}), self.assertRaises(AssertionError): x.normalize(path, data)
        for path, data in ((None, b'x'), (x.DISPATCHER, 'text')):
            with self.assertRaises(AssertionError): x.normalize(path, data)

    def test_selected_historical_and_release_failures_are_terminal(self):
        for error in (AssertionError, o.TopologyError):
            with patch.object(x, 'content', side_effect=error('selected terminal')), patch.object(previous, 'content') as old, self.assertRaisesRegex(error, 'selected terminal'):
                self.selected(self.pure, fresh=True)
            old.assert_not_called()
            with patch.object(previous, 'content', side_effect=error('historical terminal')), patch.object(o, 'selected_profile') as fallback, self.assertRaisesRegex(error, 'historical terminal'):
                self.selected(self.pure, fresh=True)
            fallback.assert_not_called()
            with patch.object(x, 'content', return_value=self.good), patch.object(o, 'release_content', side_effect=error('release terminal')), self.assertRaisesRegex(error, 'release terminal'):
                self.selected(self.release)
        for offset, value in ((5, '0' * 40), (6, {})):
            args = list(self.args); args[offset] = value
            with self.assertRaises(AssertionError): x.content(self.pure, *args)
        with patch.object(p.authenticated, '_budgets', side_effect=AssertionError('budget terminal')), self.assertRaisesRegex(AssertionError, 'budget terminal'): self.content()

    def test_current_candidate_is_never_cached(self):
        with patch.object(x, 'content', wraps=x.content) as checked:
            self.assertEqual(self.selected(self.pure), self.good); self.assertEqual(self.selected(self.pure), self.good)
            self.assertEqual(checked.call_count, 2)
        self.bad_content(self.changed(x.CASES, b'changed after validation'))
        baseline = self.verified_baseline(x.M, *self.args); baseline.clear()
        self.assertEqual(self.verified_baseline(x.M, *self.args), self.original)
        for offset, value in ((2, lambda ref, root: {}), (3, lambda ref, root: {}), (5, '0' * 40), (6, {})):
            args = list(self.args); args[offset] = value
            with patch.object(self, '_select', side_effect=AssertionError('fresh required')) as fresh, self.assertRaisesRegex(AssertionError, 'fresh required'): self.verified_baseline(x.M, *args)
            fresh.assert_called_once()
        with patch.object(x, 'M_TREE', '0' * 40), patch.object(self, '_select', side_effect=AssertionError('fresh required')), self.assertRaisesRegex(AssertionError, 'fresh required'): self.verified_baseline(x.M, *self.args)
        runtime = ast.parse((c.ROOT / x.PROFILE).read_text())
        self.assertFalse(any('cache' in (getattr(n, 'id', getattr(n, 'attr', getattr(n, 'name', ''))) or '') for n in ast.walk(runtime)))

    def test_original1541_strict303_consumer452_ids_and_assertions_are_preserved(self):
        original = [item for group in lc.GROUPS for item in lc.inventory(group)] + lc.ids(y.CLASS)
        groups = (publisher, admission, final, download, staging, checksum, archive, staged)
        original += [item for group in groups for item in group.inventory()]
        pt.inventory_ids(original, 1433, 'bea84742dea5afcad6d7cbcfad99db412aa03e0ac323cda1f29013cd096fc470')
        original += readiness.inventory() + retirement.inventory() + git_budget.inventory()
        self.assertEqual(len(original), len(set(original))); self.assertEqual(len(original), 1541)
        self.assertEqual(len(set(original + inventory())), 1553); self.assertFalse(set(original) & set(inventory()))
        method = next(n for n in ast.walk(ast.parse(self.frozen(p.TESTS))) if isinstance(n, ast.FunctionDef) and n.name == 'test_protected_source_versions_gates_workflows_and_old_452_are_unchanged')
        modules = ast.literal_eval(method.body[0].value.func.value).split()
        with patch('tempfile.TemporaryDirectory', side_effect=AssertionError('discovery materialized')):
            strict = [test.id() for test in c._flatten(unittest.defaultTestLoader.discover(str(c.ROOT / 'scripts'), pattern='rc_pretag*_tests.py'))]
            consumer = [item for module in modules for item in lc.ids(module) if item.split('.', 1)[0] == module]
        pt.inventory_ids(strict, 303, '0ecc366c2018a6a1e20d3f59ed9ca66645d9334324cd517682894cabde923125')
        pt.inventory_ids(consumer, 452, 'd01db4e6cd605c6636423e27c8c0409e90aba217cc0e6930474f59a24b57f372')
        self.assertEqual(len(set(strict + consumer)), 755)
        allowed = {'rc_pretag_git_budget_cases': {'setUp', 'test_seventeen_exact_paths_modes_pins_and_entry_count',
            'test_individual_and_aggregate_caps_reject', 'test_seven_full_byte_inverses_and_six_dispatch_lines',
            'test_missing_duplicate_outside_and_binary_inverse_changes_reject', 'test_current_candidate_is_never_cached',
            'test_new48_inventory_readonly_workflow_and_exceptional_outcomes'}}
        def methods(data):
            return {(cls.name, n.name): n for cls in ast.parse(data).body if isinstance(cls, ast.ClassDef)
                    for n in cls.body if isinstance(n, ast.FunctionDef)}
        def assertions(node):
            return Counter(ast.dump(a) for a in ast.walk(node) if isinstance(a, ast.Call)
                           and isinstance(a.func, ast.Attribute) and a.func.attr.startswith('assert'))
        class UndoOperands(ast.NodeTransformer):
            def visit_Call(self, node):
                decoded = (isinstance(node.func, ast.Attribute) and node.func.attr == 'decode'
                           and isinstance(node.func.value, ast.Call) and isinstance(node.func.value.func, ast.Name)
                           and node.func.value.func.id == 'windows_vm_bytes' and not node.args and not node.keywords)
                node = self.generic_visit(node)
                if decoded:
                    source = node.func.value
                    assert isinstance(source, ast.Call) and isinstance(source.func, ast.Attribute)
                    assert source.func.attr == 'read_bytes' and not source.args and not source.keywords
                    source.func.attr = 'read_text'
                    return source
                if isinstance(node.func, ast.Name) and node.func.id == 'windows_vm_bytes':
                    assert len(node.args) == 2 and not node.keywords
                    return node.args[1]
                return node
        changed = set()
        for module in {item.split('.', 1)[0] for item in original}:
            path = 'scripts/' + module + '.py'
            current, frozen = (c.ROOT / path).read_bytes(), self.frozen(path)
            self.assertEqual(x.normalize(path, current), frozen, path)
            before, after = methods(frozen), methods(current)
            self.assertEqual(before.keys(), after.keys(), path)
            for key, method in before.items():
                adjusted = UndoOperands().visit(copy.deepcopy(after[key]))
                self.assertFalse(assertions(method) - assertions(adjusted), (path, key))
                if ast.dump(method) != ast.dump(after[key]): changed.add((module, key[1]))
                if key[1] not in allowed.get(module, ()): self.assertEqual(ast.dump(method), ast.dump(after[key]), (path, key))
                else: self.assertEqual(ast.dump(method), ast.dump(adjusted), (path, key))
        self.assertEqual(changed, {(module, name) for module, names in allowed.items() for name in names})
        flow = [item for group in groups for item in group.inventory()] + readiness.inventory() + retirement.inventory() + git_budget.inventory()
        self.assertEqual(len(flow), len(set(flow))); self.assertEqual(len(flow), 357)
        self.assertEqual(len(set(flow + inventory())), 369)
        self.assertNotIn('scripts/rc_publication_stage.py', x.CAPS)
        self.assertEqual((c.ROOT / 'scripts/rc_publication_stage.py').read_bytes(), self.frozen('scripts/rc_publication_stage.py'))

    def test_new12_inventory_readonly_workflows_and_exceptional_outcomes(self):
        text = (c.ROOT / x.WORKFLOW).read_text()
        for fragment in ("branches: ['ci/issue88-publisher-executor-*']", 'permissions:\n  contents: read', 'timeout-minutes: 30', 'frozen three hundred sixty nine cases', 'import rc_pretag_windows_vm_profile as profile', 'supervisor_readiness.inventory()', 'supervisor_readiness.execution_valid(loaded, result)', 'supervisor-readiness-cases.log', 'supervisor-readiness-inventory.json', 'stage_retirement.inventory()', 'stage_retirement.execution_valid(loaded, result)', 'stage-retirement-cases.log', 'stage-retirement-inventory.json', 'git_budget.inventory()', 'git_budget.execution_valid(loaded, result)', 'git-budget-cases.log', 'git-budget-inventory.json', 'windows_vm.inventory()', 'windows_vm.execution_valid(loaded, result)', 'windows-vm-cases.log', 'windows-vm-inventory.json', 'parents == [profile.M]', 'checked() == before', "'production_ready': False"):
            self.assertIn(fragment, text)
        for forbidden in ('secrets.', 'GH_TOKEN', 'GITHUB_TOKEN', 'contents: write', 'workflow_dispatch:', 'pull_request:', 'gh release', 'curl ', 'pip install'):
            self.assertNotIn(forbidden, text)
        native = (c.ROOT / '.github/workflows/windows-vm-session.yml').read_text()
        for fragment in ("branches: ['ci/issue88-publisher-executor-windows-vm-20261008']", 'permissions:\n  contents: read', 'timeout-minutes: 45', "if ($parents -cne '" + x.M + "')", "base='" + x.M + "'", '--test-threads=1', '16 passed; 0 failed; 0 ignored', '2 passed; 0 failed; 0 ignored', 'production_admission=$false;workspace_integration=$false;network_denial_proven=$false;production_launch_authority=$false'):
            self.assertIn(fragment, native)
        for forbidden in ('workflow_dispatch:', 'pull_request:', 'contents: write', 'merge-base --is-ancestor', 'secrets.'):
            self.assertNotIn(forbidden, native)
        self.assertLessEqual(len(native.splitlines()), 120)
        self.assertLessEqual(len(text.splitlines()), 185)
        self.assertEqual(sum(len((c.ROOT / path).read_bytes().splitlines()) for path in x.CAPS if path.startswith('docs/specs/windows-vm-session/')), sum(x.SOURCE_PINS[path][4] for path in x.CAPS if path.startswith('docs/specs/windows-vm-session/')))
        self.assertTrue(all(self.good[path] == value for path, value in self.original.items() if path not in x.CAPS))
        held = {'scripts/rc_source_assembly.py', 'scripts/rc_source_assembly_dispatch_tests.py', 'scripts/rc_source_assembly_tests.py', 'tests/delivery/test_linux_lifecycle_wiring.py'}
        self.assertFalse(held & self.good.keys()); self.assertTrue(all(not (c.ROOT / path).exists() for path in held))
        loaded = inventory()
        good = dict(executed_ids=loaded, testsRun=12, skipped=[], expectedFailures=[], unexpectedSuccesses=[], wasSuccessful=lambda: True)
        self.assertTrue(execution_valid(loaded, SimpleNamespace(**good)))
        for field, value in (('skipped', [('id', 'reason')]), ('expectedFailures', [('id', 'failure')]), ('unexpectedSuccesses', ['id']), ('testsRun', 11), ('wasSuccessful', lambda: False)):
            self.assertFalse(execution_valid(loaded, SimpleNamespace(**(good | {field: value}))))
        for invalid in (loaded[:-1], loaded + loaded[:1], loaded[:-1] + ['unknown']):
            with self.assertRaises(AssertionError): execution_valid(invalid, SimpleNamespace(**good))
            with self.assertRaises(AssertionError): execution_valid(loaded, SimpleNamespace(**(good | {'executed_ids': invalid})))

def main():
    suite = unittest.defaultTestLoader.loadTestsFromNames(inventory())
    loaded = [test.id() for test in c._flatten(suite)]
    result = unittest.TextTestRunner(verbosity=2, resultclass=c.InventoryResult).run(suite)
    print(json.dumps(dict(loaded_ids=loaded, executed_ids=getattr(result, 'executed_ids', []), loaded=len(loaded), executed=result.testsRun)))
    return 0 if execution_valid(loaded, result) else 1

if __name__ == '__main__':
    raise SystemExit(main())
