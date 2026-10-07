"""Ten exact finite-composition proofs; fixture success is not native CI evidence."""
from collections import Counter
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import rc_pretag_composition_tests as c
import rc_pretag_ownership_profile as o
import rc_pretag_publication_profile as p
import rc_pretag_publication_tests as pt
import rc_pretag_linux_package_profile as l
import rc_pretag_linux_package_cases as lc
import rc_pretag_yoke_repair_profile as y


def execution_valid(loaded, result):
    pt.inventory_ids(loaded, 10, y.DIGEST)
    assert Counter(loaded) == Counter(y.CLASS + '.' + name for name in y.NAMES)
    executed = getattr(result, 'executed_ids', [])
    pt.inventory_ids(executed, 10, y.DIGEST)
    return (result.wasSuccessful() and not result.skipped and not result.expectedFailures and not result.unexpectedSuccesses
            and Counter(executed) == Counter(loaded) and result.testsRun == len(set(executed)) == 10)


class YokeRepairCompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = c._profile_fixture()
        cls.repo, _, commit, blob = cls.fixture.__enter__()
        cls.commit, cls.blob = staticmethod(commit), staticmethod(blob)
        cls._select = staticmethod(p.selected_profile)
        cls._immutable_f_cache = {}

    @classmethod
    def tearDownClass(cls):
        cls._immutable_f_cache.clear()
        cls.fixture.__exit__(None, None, None)

    def setUp(self):
        self.original = c._entries(y.F, self.repo)
        self.good = self.original | {path: ('100644', 'blob', self.blob((c.ROOT / path).read_bytes())) for path in y.CAPS}
        self.pure = self.commit([y.F], self.good)
        self.feature = self.commit([y.F, self.pure], self.good)
        self.overlay = self.good | c.RELEASE_DOCS
        self.release = self.commit([p.R, self.feature], self.overlay)
        self.args = (self.repo, c._git, c._entries, c._feature_profile, c.RELEASE, c.RELEASE_TREE, dict(c.RELEASE_DOCS))

    def verified_baseline(self, ref, *args, **kwargs):
        callbacks = all(actual is expected for actual, expected in zip(args[1:4], self.args[1:4]))
        if ref != y.F or kwargs or not callbacks or args != self.args:
            return self._select(ref, *args, **kwargs)
        key = (ref, *args[:6], tuple(sorted(args[6].items())))
        if key not in self._immutable_f_cache:
            self._immutable_f_cache[key] = dict(self._select(ref, *args))
        return dict(self._immutable_f_cache[key])

    def selected(self, ref, git=c._git, fresh=False):
        args = (self.repo, git, *self.args[2:])
        if fresh:
            return self._select(ref, *args)
        with patch.object(p, 'selected_profile', side_effect=self.verified_baseline):
            return self._select(ref, *args)

    def content(self):
        with patch.object(p, 'selected_profile', side_effect=self.verified_baseline):
            return y.content(self.pure, *self.args)

    def frozen(self, path):
        return c._git('show', y.F + ':' + path, root=self.repo)

    def changed(self, path, data):
        return self.good | {path: ('100644', 'blob', self.blob(data))}

    def bad_content(self, entries, parents=None):
        ref = self.commit([y.F] if parents is None else parents, entries)
        y.topology(ref, self.repo, c._git, p.R)
        with self.assertRaises(AssertionError):
            self.selected(ref)

    def test_exact_f_identity_and_fresh_historical_validation(self):
        self.assertEqual((y.F, y.F_TREE, y.F_PARENTS), ('b97c469b1bd7ffb9973a65e19b798d2573561d92',
            'c017dc6e5f2fde6f9f135119500916cbe88efe1e', ('fd7b303839aa648d33456f7aaeec6388bfb696c4', 'decfd70c746c5dd0d7d7c6ceace718c5a49487da')))
        self.assertEqual(self.selected(y.F, fresh=True), self.original)
        self.assertIsNone(y.select(y.F, *self.args))
        with patch.object(l, 'content', wraps=l.content) as historical:
            self.assertEqual(self.selected(self.pure, fresh=True), self.good)
            self.assertEqual(self.selected(self.pure, fresh=True), self.good)
            self.assertEqual(historical.call_count, 2)
        for command, replacement in ((('show', '-s', '--format=%P', y.F), b'\n'),
                                      (('show', '-s', '--format=%P', y.F), ' '.join(reversed(y.F_PARENTS)).encode()),
                                      (('rev-parse', y.F + '^{tree}'), b'0' * 40 + b'\n')):
            def altered(*args, root):
                return replacement if args == command else c._git(*args, root=root)
            with self.assertRaises(AssertionError):
                self.selected(self.pure, altered, fresh=True)

    def test_ordered_candidate_merge_and_release_overlay(self):
        self.assertEqual(self.selected(self.pure), self.good)
        self.assertEqual(self.selected(self.feature), self.good)
        self.assertEqual(self.selected(self.release), self.overlay)
        self.assertEqual(y.topology(self.release, self.repo, c._git, p.R), ('release', self.feature, self.pure))
        for entries in (self.original, self.overlay, self.changed(y.CASES, b'changed\n')):
            self.bad_content(entries, [y.F, self.pure])
        self.assertEqual((p.R, p.R_TREE, len(c.RELEASE_DOCS)),
            ('e2e011f7f2a3a1df838bbd588106205b999db610', 'c0dfe00fdcc7ebc8e26acaad5d18ff3f94df9ba3', 4))
        for path in c.RELEASE_DOCS:
            for entries in (self.overlay | {path: self.good[path]}, {k: v for k, v in self.overlay.items() if k != path},
                            self.overlay | {path: ('100755', *self.overlay[path][1:])}):
                self.bad_content(entries, [p.R, self.feature])
        self.bad_content(self.overlay | {'extra.md': ('100644', 'blob', self.blob(b'extra'))}, [p.R, self.feature])

    def test_invalid_parent_topologies_and_same_tree_anchors_reject(self):
        impostor = self.commit([], self.original)
        correction = self.commit([self.pure], self.good)
        for parents in ([], [self.pure], [self.pure, y.F], [y.F, self.pure, p.R], [y.F, y.F], [y.F, self.feature],
                        [p.R], [p.R, self.pure], [self.feature, p.R], [p.R, self.feature, self.pure], [p.R, self.release],
                        [impostor], [impostor, self.pure], [correction], [y.F, correction], [l.M, self.pure]):
            ref = self.commit(parents, self.good)
            with self.subTest(parents=parents), self.assertRaises(o.TopologyError):
                y.topology(ref, self.repo, c._git, p.R)
            with patch.object(y, 'content') as content:
                self.assertIsNone(y.select(ref, *self.args))
            content.assert_not_called()
            with self.assertRaises(AssertionError):
                self.selected(ref)
        with self.assertRaises(o.TopologyError):
            y.topology(self.pure, self.repo, c._git, impostor)

    def test_only_two_yoke_derive_records_change(self):
        import tomllib
        self.assertEqual(set(y.LOCKS), {'services/cloud-agent/Cargo.lock', 'services/cloud-gateway/Cargo.lock'})
        for path in y.LOCKS:
            old, new = self.frozen(path), (c.ROOT / path).read_bytes()
            self.assertEqual((old.count(y.OLD_BLOCK), new.count(y.NEW_BLOCK), new.count(y.OLD_BLOCK)), (1, 1, 0))
            self.assertEqual(new.replace(y.NEW_BLOCK, y.OLD_BLOCK, 1), old)
            before, after = tomllib.loads(old.decode()), tomllib.loads(new.decode())
            records = [(a, b) for a, b in zip(before['package'], after['package']) if a != b]
            self.assertEqual(len(records), 1)
            a, b = records[0]
            self.assertEqual((a['name'], a['version'], b['version']), ('yoke-derive', '0.8.3', '0.8.4'))
            self.assertEqual({k for k in a.keys() | b.keys() if a.get(k) != b.get(k)}, {'version', 'checksum'})
            b['version'], b['checksum'] = a['version'], a['checksum']
            self.assertEqual(before, after)
            self.assertEqual(c._git('diff', '--numstat', y.F, self.pure, '--', path, root=self.repo), f'2\t2\t{path}\n'.encode())

    def test_source_paths_modes_types_and_pins_are_exact(self):
        self.assertEqual(self.content(), self.good)
        self.assertEqual((len(self.original), len(self.good), len(y.CAPS), len(y.BASE_PINS)), (1726, 1732, 9, 3))
        self.assertEqual(y.SOURCE_PINS.keys(), y.CAPS.keys() - {y.PROFILE})
        for path, row in y.SOURCE_PINS.items():
            data = (c.ROOT / path).read_bytes()
            self.assertEqual(row, ('100644', *o.pin(data), len(data), len(data.splitlines())))
            for index, value in enumerate(('100755', '0' * 40, '0' * 64, row[3] + 1, row[4] + 1)):
                changed = list(row)
                changed[index] = value
                with patch.dict(y.SOURCE_PINS, {path: tuple(changed)}), self.assertRaises(AssertionError):
                    self.content()
            self.bad_content(self.changed(path, data + b'\n'))
        for pins in ({k: v for k, v in y.SOURCE_PINS.items() if k != y.CASES}, y.SOURCE_PINS | {'extra': row}):
            with patch.dict(y.SOURCE_PINS, pins, clear=True), self.assertRaises(AssertionError):
                self.content()
        for path in y.CAPS:
            missing = {k: v for k, v in self.good.items() if k != path}
            self.bad_content(missing)
            self.bad_content(missing | {path + '.renamed': self.good[path]})
            for entry in (('100755', *self.good[path][1:]), ('120000', 'blob', self.blob(b'target')), ('160000', 'commit', y.F)):
                self.bad_content(self.good | {path: entry})
        self.bad_content(self.changed('unreviewed-extra.py', b'extra\n'))
        self.bad_content(self.changed('services/cloud-agent/src/main.rs', b'changed\n'))

    def test_per_file_and_aggregate_budgets_reject(self):
        self.assertEqual(y.CAPS, {
            'services/cloud-agent/Cargo.lock': (1108, 4), 'services/cloud-gateway/Cargo.lock': (2266, 4),
            'scripts/rc_pretag_linux_package_profile.py': (185, 4),
            'scripts/rc_pretag_yoke_repair_profile.py': (220, 220), 'scripts/rc_pretag_yoke_repair_cases.py': (300, 300),
            'docs/specs/issue85-yoke-derive-repair/requirements.md': (40, 40),
            'docs/specs/issue85-yoke-derive-repair/design.md': (60, 60),
            'docs/specs/issue85-yoke-derive-repair/tasks.md': (40, 40), '.github/workflows/issue85-yoke-repair.yml': (100, 100),
        })
        data = {path: (c.ROOT / path).read_bytes() for path in y.CAPS}
        def budgets(git=c._git):
            return p.authenticated._budgets(self.pure, y.F, self.repo, git, data, y.CAPS, y.DELTA_LIMIT, 'yoke_delta_budget')
        self.assertEqual((y.DELTA_LIMIT, sum(cap[1] for cap in y.CAPS.values())), (720, 772))
        budgets()
        for path, (_, delta) in y.CAPS.items():
            with patch.dict(y.CAPS, {path: (len(data[path].splitlines()) - 1, delta)}), self.assertRaises(AssertionError):
                budgets()
            for row in (f'{delta + 1}\t0\t{path}\n'.encode(), b'', b'-\t-\t' + path.encode(), b'1\t0', b'1\t0\twrong',
                        f'1\t0\t{path}\nextra\n'.encode(), f'-1\t0\t{path}\n'.encode()):
                def malformed(*args, root):
                    return row if args == ('diff', '--numstat', y.F, self.pure, '--', path) else c._git(*args, root=root)
                with self.assertRaises(AssertionError):
                    budgets(malformed)
        def aggregate(*args, root):
            return f'{y.CAPS[args[5]][1]}\t0\t{args[5]}\n'.encode() if args[:5] == ('diff', '--numstat', y.F, self.pure, '--') else c._git(*args, root=root)
        with self.assertRaisesRegex(AssertionError, 'yoke_delta_budget'):
            budgets(aggregate)

    def test_dispatch_and_lock_inverses_recover_f_bytes(self):
        self.assertEqual(set(y.BASE_PINS), set(y.LOCKS) | {y.DISPATCHER})
        self.assertEqual(len(y.DISPATCH.splitlines()), 4)
        for path in y.BASE_PINS:
            current, frozen = (c.ROOT / path).read_bytes(), self.frozen(path)
            with patch('builtins.open', side_effect=AssertionError('IO forbidden')), patch('subprocess.check_output', side_effect=AssertionError('git forbidden')):
                self.assertEqual(y.inverse(path, current), frozen)
            before = y.DISPATCH if path == y.DISPATCHER else y.NEW_BLOCK
            for changed in (current.replace(before, b'', 1), current.replace(before, before * 2, 1), current + b'# outside\n', b'\xff'):
                row = ('100644', *o.pin(changed), len(changed), len(changed.splitlines()))
                with patch.dict(y.SOURCE_PINS, {path: row}), self.assertRaises(AssertionError):
                    y.inverse(path, changed)
        with self.assertRaises(AssertionError):
            y.inverse('unknown', b'unchanged')

    def test_selected_and_historical_failures_are_terminal(self):
        for error in (AssertionError, o.TopologyError):
            with patch.object(y, 'content', side_effect=error('selected terminal')), patch.object(l, 'content') as old, self.assertRaisesRegex(error, 'selected terminal'):
                self.selected(self.pure, fresh=True)
            old.assert_not_called()
            with patch.object(l, 'content', side_effect=error('historical terminal')), patch.object(o, 'selected_profile') as fallback, self.assertRaisesRegex(error, 'historical terminal'):
                self.selected(self.pure, fresh=True)
            fallback.assert_not_called()
            with patch.object(y, 'content', return_value=self.good), patch.object(o, 'release_content', side_effect=error('release terminal')), self.assertRaisesRegex(error, 'release terminal'):
                self.selected(self.release)
        with patch.object(p.authenticated, '_budgets', side_effect=AssertionError('budget terminal')), self.assertRaisesRegex(AssertionError, 'budget terminal'):
            self.content()

    def test_isolated_git_and_protected_boundaries(self):
        calls = []
        def moving(*args, root):
            calls.append(args)
            if args == ('rev-parse', '--verify', 'moving^{commit}'):
                return ((self.pure if calls.count(args) == 1 else self.release) + '\n').encode()
            return c._git(*args, root=root)
        hostile = {name: '/nonexistent' for name in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR', 'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES')}
        with patch.dict(os.environ, hostile):
            self.assertEqual(self.selected('moving', moving, fresh=True), self.good)
        self.assertEqual(sum(any('moving' in arg for arg in args) for args in calls), 1)
        self.assertTrue(all(self.good[path] == value for path, value in self.original.items() if path not in y.CAPS))
        held = {'docs/specs/rc-source-assembly-engineering/' + name for name in ('README.md', 'design.md', 'requirements.md', 'tasks.md', 'subspecs/focused-validation/spec.md', 'subspecs/source-evidence/spec.md')}
        held |= {'scripts/rc_source_assembly.py', 'scripts/rc_source_assembly_dispatch_tests.py', 'scripts/rc_source_assembly_tests.py', 'tests/delivery/test_linux_lifecycle_wiring.py'}
        self.assertFalse(held & self.good.keys())
        for path in held:
            self.assertFalse((c.ROOT / path).exists() or (c.ROOT / path).is_symlink(), path)
        for path in ('package.json', 'package-lock.json', 'src-tauri/Cargo.lock', 'services/local-agent/Cargo.lock', p.PROFILE,
                     l.CASES, 'scripts/rc_pretag_linux_package_inverse.py', 'scripts/rc_release_policy.py', 'scripts/rc_release_eligibility.py',
                     '.github/workflows/issue40-current-nginx-include.yml', 'services/local-agent/src/process.rs', 'src-tauri/src/workspace_snapshots/filesystem.rs'):
            self.assertEqual((c.ROOT / path).read_bytes(), self.frozen(path), path)
        self.assertNotIn('cache', (c.ROOT / y.PROFILE).read_text())

    def test_original_and_new_test_inventories_are_exact(self):
        old = [item for group in lc.GROUPS for item in lc.inventory(group)]
        pt.inventory_ids(old, 1174, 'a40dee60873940221d23eca3b5e8af13e260f57bcbbbd72c7a77de72c93fa90a')
        for module in {item.split('.', 1)[0] for item in old}:
            self.assertEqual((c.ROOT / 'scripts' / (module + '.py')).read_bytes(), self.frozen('scripts/' + module + '.py'), module)
        strict = [test.id() for test in c._flatten(unittest.defaultTestLoader.discover(str(c.ROOT / 'scripts'), pattern='rc_pretag*_tests.py'))]
        pt.inventory_ids(strict, 303, '0ecc366c2018a6a1e20d3f59ed9ca66645d9334324cd517682894cabde923125')
        loaded = lc.ids(y.CLASS)
        self.assertFalse(set(old) & set(loaded))
        self.assertEqual(len(set(old + loaded)), 1184)
        self.assertFalse(Path(y.CASES).match('*_tests.py'))
        good = dict(executed_ids=loaded, testsRun=10, skipped=[], expectedFailures=[], unexpectedSuccesses=[], wasSuccessful=lambda: True)
        self.assertTrue(execution_valid(loaded, SimpleNamespace(**good)))
        for field, value in (('skipped', [('id', 'reason')]), ('expectedFailures', [('id', 'failure')]), ('unexpectedSuccesses', ['id']), ('testsRun', 9), ('wasSuccessful', lambda: False)):
            self.assertFalse(execution_valid(loaded, SimpleNamespace(**(good | {field: value}))))
        for invalid in (loaded[:-1], loaded + loaded[:1], loaded[:-1] + ['unknown']):
            with self.assertRaises(AssertionError):
                execution_valid(invalid, SimpleNamespace(**good))
            with self.assertRaises(AssertionError):
                execution_valid(loaded, SimpleNamespace(**(good | {'executed_ids': invalid})))


def main():
    suite = unittest.defaultTestLoader.loadTestsFromName(y.CLASS)
    loaded = [test.id() for test in c._flatten(suite)]
    pt.inventory_ids(loaded, 10, y.DIGEST)
    assert Counter(loaded) == Counter(y.CLASS + '.' + name for name in y.NAMES)
    result = unittest.TextTestRunner(verbosity=2, resultclass=c.InventoryResult).run(suite)
    print(json.dumps(dict(loaded_ids=loaded, executed_ids=getattr(result, 'executed_ids', []), loaded=len(loaded), executed=result.testsRun)))
    return 0 if execution_valid(loaded, result) else 1


if __name__ == '__main__':
    raise SystemExit(main())
