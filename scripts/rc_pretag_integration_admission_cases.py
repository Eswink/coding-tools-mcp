"""Exact integration composition and inventories; synthetic tests grant no release authority."""
import ast
from collections import Counter
import copy
import hashlib
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
import rc_pretag_linux_package_cases as lc
import rc_pretag_yoke_repair_profile as y
import rc_pretag_publisher_executor_profile as previous
import rc_pretag_publisher_executor_cases as old_cases
import rc_pretag_integration_admission_profile as x
from rc_pretag_final_admission_profile import normalize as final_bytes


def inventory():
    expected = [cls + '.' + name for cls, names in x.NEW_CASES.items() for name in names]
    actual = [item for cls in x.NEW_CASES for item in lc.ids(cls)]
    pt.inventory_ids(expected, 36, x.DIGEST)
    pt.inventory_ids(actual, 36, x.DIGEST)
    assert Counter(actual) == Counter(expected)
    return expected


def execution_valid(loaded, result):
    pt.inventory_ids(loaded, 36, x.DIGEST)
    assert Counter(loaded) == Counter(inventory())
    executed = getattr(result, 'executed_ids', [])
    pt.inventory_ids(executed, 36, x.DIGEST)
    return (result.wasSuccessful() and not result.skipped and not result.expectedFailures
            and not result.unexpectedSuccesses and Counter(executed) == Counter(loaded)
            and result.testsRun == len(set(executed)) == 36)


class IntegrationAdmissionCompositionCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = c._profile_fixture()
        cls.repo, _, commit, blob = cls.fixture.__enter__()
        cls.commit, cls.blob, cls._select = staticmethod(commit), staticmethod(blob), staticmethod(p.selected_profile)
        cls._immutable_b_cache = {}

    @classmethod
    def tearDownClass(cls):
        cls._immutable_b_cache.clear()
        cls.fixture.__exit__(None, None, None)

    def setUp(self):
        self.original = c._entries(x.B, self.repo)
        self.good = self.original | {path: ('100644', 'blob', self.blob(final_bytes(path, (c.ROOT / path).read_bytes()))) for path in x.CAPS}
        self.pure = self.commit([x.B], self.good)
        self.feature = self.commit([x.B, self.pure], self.good)
        self.overlay = self.good | c.RELEASE_DOCS
        self.release = self.commit([p.R, self.feature], self.overlay)
        self.args = (self.repo, c._git, c._entries, c._feature_profile, c.RELEASE, c.RELEASE_TREE, dict(c.RELEASE_DOCS))

    def verified_baseline(self, ref, *args, **kwargs):
        callbacks = all(actual is expected for actual, expected in zip(args[1:4], self.args[1:4]))
        immutable = (x.B, x.B_TREE, x.B_PARENTS) == (
            'c2b5afb2c46318e2c54283f8442d5996e55f0a73', '428da2c6345e99d847094755098af08967578cca',
            ('5beda478f4d04e7a352d0bbc63e1496ee3bca668', '9525dd6cae2c9b8a7fefeb31c71f12b1e05b397f'))
        if ref != x.B or not immutable or kwargs or not callbacks or args != self.args:
            return self._select(ref, *args, **kwargs)
        key = (ref, *args[:6], tuple(sorted(args[6].items())))
        if key not in self._immutable_b_cache:
            self._immutable_b_cache[key] = dict(self._select(ref, *args))
        return dict(self._immutable_b_cache[key])

    def selected(self, ref, git=c._git, fresh=False):
        arguments = (self.repo, git, *self.args[2:])
        if fresh:
            return self._select(ref, *arguments)
        with patch.object(p, 'selected_profile', side_effect=self.verified_baseline):
            return self._select(ref, *arguments)

    def content(self):
        with patch.object(p, 'selected_profile', side_effect=self.verified_baseline):
            return x.content(self.pure, *self.args)

    def frozen(self, path):
        return c._git('show', x.B + ':' + path, root=self.repo)

    def changed(self, path, data):
        return self.good | {path: ('100644', 'blob', self.blob(data))}

    def bad_content(self, entries, parents=None):
        ref = self.commit([x.B] if parents is None else parents, entries)
        x.topology(ref, self.repo, c._git, p.R)
        with self.assertRaises(AssertionError):
            self.selected(ref)

    def test_exact_b_identity_and_fresh_historical_validation(self):
        self.assertEqual((x.B, x.B_TREE, x.B_PARENTS), (
            'c2b5afb2c46318e2c54283f8442d5996e55f0a73', '428da2c6345e99d847094755098af08967578cca',
            ('5beda478f4d04e7a352d0bbc63e1496ee3bca668', '9525dd6cae2c9b8a7fefeb31c71f12b1e05b397f')))
        self.assertEqual(self.selected(x.B, fresh=True), self.original)
        self.assertIsNone(x.select(x.B, *self.args))
        with patch.object(previous, 'content', wraps=previous.content) as historical:
            self.assertEqual(self.selected(self.pure, fresh=True), self.good)
            self.assertEqual(self.selected(self.pure, fresh=True), self.good)
            self.assertEqual(historical.call_count, 2)
        for command, replacement in ((('show', '-s', '--format=%P', x.B), b'\n'),
                (('show', '-s', '--format=%P', x.B), ' '.join(reversed(x.B_PARENTS)).encode()),
                (('rev-parse', x.B + '^{tree}'), b'0' * 40 + b'\n')):
            def altered(*args, root):
                return replacement if args == command else c._git(*args, root=root)
            with self.assertRaises(AssertionError):
                self.selected(self.pure, altered)

    def test_ordered_d_i_j_and_exact_four_document_overlay(self):
        for ref, expected in ((self.pure, self.good), (self.feature, self.good), (self.release, self.overlay)):
            self.assertEqual(self.selected(ref), expected)
        self.assertEqual(x.topology(self.release, self.repo, c._git, p.R), ('release', self.feature, self.pure))
        for entries in (self.original, self.overlay, self.changed(x.CASES, b'changed\n')):
            self.bad_content(entries, [x.B, self.pure])
        self.assertEqual((p.R, p.R_TREE, len(c.RELEASE_DOCS)),
            ('e2e011f7f2a3a1df838bbd588106205b999db610', 'c0dfe00fdcc7ebc8e26acaad5d18ff3f94df9ba3', 4))
        for path in c.RELEASE_DOCS:
            for entries in (self.overlay | {path: self.good[path]}, {k: v for k, v in self.overlay.items() if k != path},
                            self.overlay | {path: ('100755', *self.overlay[path][1:])}):
                self.bad_content(entries, [p.R, self.feature])
        self.bad_content(self.overlay | {'extra.md': ('100644', 'blob', self.blob(b'extra'))}, [p.R, self.feature])

    def test_wrong_repeated_nested_correction_and_same_tree_parents_reject(self):
        impostor, correction = self.commit([], self.original), self.commit([self.pure], self.good)
        for parents in ([], [self.pure], [self.pure, x.B], [x.B, self.pure, p.R], [x.B, x.B], [x.B, self.feature],
                [p.R], [p.R, self.pure], [self.feature, p.R], [p.R, self.feature, self.pure], [p.R, self.release],
                [impostor], [impostor, self.pure], [correction], [x.B, correction], [previous.M, self.pure]):
            ref = self.commit(parents, self.good)
            with self.subTest(parents=parents), self.assertRaises(o.TopologyError):
                x.topology(ref, self.repo, c._git, p.R)
            with patch.object(x, 'content') as content:
                self.assertIsNone(x.select(ref, *self.args))
            content.assert_not_called()
            with self.assertRaises(AssertionError):
                self.selected(ref)
        with self.assertRaises(o.TopologyError):
            x.topology(self.pure, self.repo, c._git, impostor)
        calls = []
        def moving(*args, root):
            calls.append(args)
            if args == ('rev-parse', '--verify', 'moving^{commit}'):
                return ((self.pure if calls.count(args) == 1 else self.release) + '\n').encode()
            return c._git(*args, root=root)
        hostile = {key: '/nonexistent' for key in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE',
            'GIT_COMMON_DIR', 'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES')}
        with patch.dict(os.environ, hostile):
            self.assertEqual(self.selected('moving', moving, fresh=True), self.good)
        self.assertEqual(sum(any('moving' in arg for arg in args) for args in calls), 1)

    def test_all_paths_modes_pins_and_entry_counts_are_exact(self):
        self.assertEqual(self.content(), self.good)
        self.assertEqual((len(self.original), len(self.good), len(x.CAPS), len(x.BASE_PINS)), (1745, 1752, 26, 19))
        self.assertEqual(x.SOURCE_PINS.keys(), x.CAPS.keys() - {x.PROFILE})
        for path, row in x.SOURCE_PINS.items():
            data = final_bytes(path, (c.ROOT / path).read_bytes())
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
            for entry in (('100755', *self.good[path][1:]), ('120000', 'blob', self.blob(b'target')), ('160000', 'commit', x.B)):
                self.bad_content(self.good | {path: entry})
        self.bad_content(self.changed('unreviewed-extra.py', b'extra\n'))
        self.bad_content(self.changed('services/cloud-agent/src/main.rs', b'changed\n'))

    def test_individual_and_total_budgets_fail_closed(self):
        self.assertEqual((x.DELTA_LIMIT, sum(cap[1] for cap in x.CAPS.values())), (2300, 2132))
        data = {path: final_bytes(path, (c.ROOT / path).read_bytes()) for path in x.CAPS}
        def budgets(git=c._git):
            return p.authenticated._budgets(self.pure, x.B, self.repo, git, data, x.CAPS, x.DELTA_LIMIT, 'integration_delta_budget')
        budgets()
        for path, (_, delta) in x.CAPS.items():
            with patch.dict(x.CAPS, {path: (len(data[path].splitlines()) - 1, delta)}), self.assertRaises(AssertionError):
                budgets()
            for row in (f'{delta + 1}\t0\t{path}\n'.encode(), b'', b'-\t-\t' + path.encode(), b'1\t0',
                        b'1\t0\twrong', f'1\t0\t{path}\nextra\n'.encode(), f'-1\t0\t{path}\n'.encode()):
                def malformed(*args, root):
                    return row if args == ('diff', '--numstat', x.B, self.pure, '--', path) else c._git(*args, root=root)
                with self.assertRaises(AssertionError):
                    budgets(malformed)
        with patch.object(x, 'DELTA_LIMIT', 0), self.assertRaisesRegex(AssertionError, 'integration_delta_budget'):
            budgets()

    def test_exact_dispatch_and_legacy_inverses_recover_complete_b_bytes(self):
        self.assertEqual(len(x.DISPATCH.splitlines()), 4)
        self.assertEqual(x.FRAGMENTS.keys(), x.BASE_PINS.keys())
        for path in x.BASE_PINS:
            current, frozen = (c.ROOT / path).read_bytes(), self.frozen(path)
            with patch('builtins.open', side_effect=AssertionError('IO forbidden')), patch('subprocess.check_output', side_effect=AssertionError('git forbidden')):
                self.assertEqual(x.normalize(path, current), frozen, path)
                self.assertEqual(x.normalize(path, frozen), frozen, path)
        current = (c.ROOT / x.DISPATCHER).read_bytes()
        self.assertEqual(current.count(x.DISPATCH), 1)
        self.assertEqual(current.replace(x.DISPATCH, b'', 1), self.frozen(x.DISPATCHER))
        self.assertEqual(c._git('diff', '--numstat', x.B, self.pure, '--', x.DISPATCHER, root=self.repo),
                         f'4\t0\t{x.DISPATCHER}\n'.encode())
        self.assertEqual(x.normalize('unmapped', b'unchanged'), b'unchanged')
        for path, pins in x.PRIOR_PINS.items():
            self.assertEqual(len(pins), len(set(pins)))
            self.assertNotIn(x.BASE_PINS[path][1:3], pins)

    def test_missing_duplicate_outside_and_binary_inverse_edits_reject(self):
        for path, fragments in x.FRAGMENTS.items():
            current = final_bytes(path, (c.ROOT / path).read_bytes())
            altered = [current + b'# outside\n', b'\xff']
            for before, _ in fragments:
                self.assertEqual(current.count(before), 1)
                altered.extend((current.replace(before, b'', 1), current.replace(before, before * 2, 1)))
            for data in altered:
                if o.pin(data) in (x.BASE_PINS[path][1:3], *x.PRIOR_PINS.get(path, ())):
                    data += b'# outside exact prior\n'
                row = ('100644', *o.pin(data), len(data), len(data.splitlines()))
                with patch.dict(x.SOURCE_PINS, {path: row}), self.assertRaises(AssertionError):
                    x.normalize(path, data)
        for path, current in ((None, b'x'), (x.DISPATCHER, 'text')):
            with self.assertRaises(AssertionError):
                x.normalize(path, current)

    def test_selected_historical_and_release_content_errors_are_terminal(self):
        for error in (AssertionError, o.TopologyError):
            with patch.object(x, 'content', side_effect=error('selected terminal')), patch.object(previous, 'content') as old, self.assertRaisesRegex(error, 'selected terminal'):
                self.selected(self.pure, fresh=True)
            old.assert_not_called()
            with patch.object(previous, 'content', side_effect=error('historical terminal')), patch.object(o, 'selected_profile') as fallback, self.assertRaisesRegex(error, 'historical terminal'):
                self.selected(self.pure, fresh=True)
            fallback.assert_not_called()
            with patch.object(x, 'content', return_value=self.good), patch.object(o, 'release_content', side_effect=error('release terminal')), self.assertRaisesRegex(error, 'release terminal'):
                self.selected(self.release)
        with patch.object(p.authenticated, '_budgets', side_effect=AssertionError('budget terminal')), self.assertRaisesRegex(AssertionError, 'budget terminal'):
            self.content()

    def test_actual_candidate_validation_is_never_cached(self):
        with patch.object(x, 'content', wraps=x.content) as checked:
            self.assertEqual(self.selected(self.pure), self.good)
            self.assertEqual(self.selected(self.pure), self.good)
            self.assertEqual(checked.call_count, 2)
        self.bad_content(self.changed(x.CASES, b'changed after valid selection\n'))
        baseline = self.verified_baseline(x.B, *self.args)
        baseline.clear()
        self.assertEqual(self.verified_baseline(x.B, *self.args), self.original)
        for offset, value in ((2, lambda ref, root: {}), (3, lambda ref, root: {}), (5, '0' * 40), (6, {})):
            arguments = list(self.args)
            arguments[offset] = value
            with patch.object(self, '_select', side_effect=AssertionError('fresh required')) as fresh, self.assertRaisesRegex(AssertionError, 'fresh required'):
                self.verified_baseline(x.B, *arguments)
            fresh.assert_called_once()
        with patch.object(x, 'B_TREE', '0' * 40), patch.object(self, '_select', side_effect=AssertionError('fresh required')), self.assertRaisesRegex(AssertionError, 'fresh required'):
            self.verified_baseline(x.B, *self.args)
        runtime = ast.parse((c.ROOT / x.PROFILE).read_text())
        self.assertFalse(any('cache' in (getattr(node, 'id', getattr(node, 'attr', getattr(node, 'name', ''))) or '') for node in ast.walk(runtime)))

    def test_original1232_strict303_ids_and_legacy_assertions_are_preserved(self):
        original = [item for group in lc.GROUPS for item in lc.inventory(group)] + lc.ids(y.CLASS) + old_cases.inventory()
        pt.inventory_ids(original, 1232, '50f1550a62d6b30ff74dcff71fe9c5248e1ab6a00ec21a9ac0602434c00aac36')
        strict = [test.id() for test in c._flatten(unittest.defaultTestLoader.discover(str(c.ROOT / 'scripts'), pattern='rc_pretag*_tests.py'))]
        pt.inventory_ids(strict, 303, '0ecc366c2018a6a1e20d3f59ed9ca66645d9334324cd517682894cabde923125')
        exceptions = {('rc_pretag_policy_tests', 'test_policy_rows_have_full_permission_identity_freshness_map'),
                      ('rc_publication_executor_cases', 'test_live_entry_is_blocked_without_real_verifiers_and_tag_guarantee')}
        class SourceOperands(ast.NodeTransformer):
            def visit_Call(self, node):
                if isinstance(node.func, ast.Attribute) and node.func.attr == 'decode' and isinstance(node.func.value, ast.Call):
                    inner = node.func.value
                    if isinstance(inner.func, ast.Name) and inner.func.id == 'integration_bytes':
                        result = copy.deepcopy(inner.args[1])
                        result.func.attr = 'read_text'
                        return result
                node = self.generic_visit(node)
                return node.args[1] if isinstance(node.func, ast.Name) and node.func.id == 'integration_bytes' else node
        for module in {item.split('.', 1)[0] for item in original}:
            path = 'scripts/' + module + '.py'
            current, frozen = final_bytes(path, (c.ROOT / path).read_bytes()), self.frozen(path)
            self.assertEqual(x.normalize(path, current), frozen, path)
            methods = lambda data: {node.name: node for node in ast.walk(ast.parse(data)) if isinstance(node, ast.FunctionDef)}
            before, after = methods(frozen), methods(current)
            self.assertEqual(before.keys(), after.keys(), path)
            assertions = lambda node: Counter(ast.dump(call) for call in ast.walk(node) if isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute) and call.func.attr.startswith('assert'))
            for name in before:
                if (module, name) not in exceptions:
                    self.assertEqual(assertions(before[name]), assertions(SourceOperands().visit(after[name])), path + ':' + name)
        self.assertFalse(set(original) & set(inventory()))

    def test_readonly_workflow_and_held_sources_remain_bounded(self):
        text = final_bytes(x.WORKFLOW, (c.ROOT / x.WORKFLOW).read_bytes()).decode()
        for fragment in ("on:\n  push:\n    branches: ['ci/issue88-publisher-executor-*']", 'permissions:\n  contents: read',
                "os: [ubuntu-22.04, ubuntu-24.04]", "python-version: '3.12'", 'fetch-depth: 0, persist-credentials: false',
                "sha == os.environ['GITHUB_SHA']", 'parents == [profile.B]', 'before = checked()', 'checked() == before',
                'x.inventory()', 'x.execution_valid(loaded, result)', 'admission.inventory()', 'admission.execution_valid(loaded, result)'):
            self.assertIn(fragment, text)
        for forbidden in ('secrets.', 'GH_TOKEN', 'GITHUB_TOKEN', 'contents: write', 'workflow_dispatch:', 'pull_request:', 'gh release', 'curl ', 'pip install'):
            self.assertNotIn(forbidden, text)
        held = {'docs/specs/rc-source-assembly-engineering/' + name for name in ('README.md', 'design.md', 'requirements.md',
            'tasks.md', 'subspecs/focused-validation/spec.md', 'subspecs/source-evidence/spec.md')}
        held |= {'scripts/rc_source_assembly.py', 'scripts/rc_source_assembly_dispatch_tests.py', 'scripts/rc_source_assembly_tests.py', 'tests/delivery/test_linux_lifecycle_wiring.py'}
        self.assertEqual(len(held), 10)
        self.assertFalse(held & self.good.keys())
        self.assertTrue(all(not (c.ROOT / path).exists() and not (c.ROOT / path).is_symlink() for path in held))
        for path in ('scripts/rc_release_eligibility.py', 'scripts/rc_publication_contract.py', 'scripts/rc_publication_stage.py',
                'scripts/rc_consumer_io.py', 'scripts/rc_artifact_consumer.py', 'src-tauri/src/workspace_snapshots/filesystem.rs'):
            self.assertEqual(final_bytes(path, (c.ROOT / path).read_bytes()), self.frozen(path), path)
        self.assertTrue(all(self.good[path] == value for path, value in self.original.items() if path not in x.CAPS))

    def test_new36_inventory_and_exceptional_outcomes_reject(self):
        loaded = inventory()
        self.assertEqual([len(names) for names in x.NEW_CASES.values()], [24, 12])
        good = dict(executed_ids=loaded, testsRun=36, skipped=[], expectedFailures=[], unexpectedSuccesses=[], wasSuccessful=lambda: True)
        self.assertTrue(execution_valid(loaded, SimpleNamespace(**good)))
        for field, value in (('skipped', [('id', 'reason')]), ('expectedFailures', [('id', 'failure')]),
                            ('unexpectedSuccesses', ['id']), ('testsRun', 35), ('wasSuccessful', lambda: False)):
            self.assertFalse(execution_valid(loaded, SimpleNamespace(**(good | {field: value}))))
        for invalid in (loaded[:-1], loaded + loaded[:1], loaded[:-1] + ['unknown']):
            with self.assertRaises(AssertionError):
                execution_valid(invalid, SimpleNamespace(**good))
            with self.assertRaises(AssertionError):
                execution_valid(loaded, SimpleNamespace(**(good | {'executed_ids': invalid})))


def main():
    suite = unittest.defaultTestLoader.loadTestsFromNames(inventory())
    loaded = [test.id() for test in c._flatten(suite)]
    result = unittest.TextTestRunner(verbosity=2, resultclass=c.InventoryResult).run(suite)
    print(json.dumps(dict(loaded_ids=loaded, executed_ids=getattr(result, 'executed_ids', []), loaded=len(loaded), executed=result.testsRun)))
    return 0 if execution_valid(loaded, result) else 1


if __name__ == '__main__':
    raise SystemExit(main())
