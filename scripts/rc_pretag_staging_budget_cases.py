"""Exact staging-budget composition; historical proof evidence grants no release authority."""
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
import rc_pretag_download_budget_profile as previous
import rc_pretag_publisher_executor_cases as old_cases
import rc_pretag_integration_admission_cases as previous_cases
import rc_pretag_final_admission_cases as final_cases
import rc_pretag_download_budget_cases as download_cases
import rc_pretag_staging_budget_profile as x
from rc_pretag_checksum_budget_profile import normalize as checksum_bytes
from rc_pretag_windows_launch_profile import normalize as windows_launch_bytes

def inventory():
    expected = [cls + '.' + name for cls, names in x.NEW_CASES.items() for name in names]
    actual = [item for cls in x.NEW_CASES for item in lc.ids(cls)]
    pt.inventory_ids(expected, 24, x.DIGEST)
    pt.inventory_ids(actual, 24, x.DIGEST)
    assert Counter(actual) == Counter(expected)
    return expected

def execution_valid(loaded, result):
    pt.inventory_ids(loaded, 24, x.DIGEST)
    assert Counter(loaded) == Counter(inventory())
    executed = getattr(result, 'executed_ids', [])
    pt.inventory_ids(executed, 24, x.DIGEST)
    return (result.wasSuccessful() and not result.skipped and not result.expectedFailures
            and not result.unexpectedSuccesses and Counter(executed) == Counter(loaded)
            and result.testsRun == len(set(executed)) == 24)

class StagingBudgetCompositionCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = c._profile_fixture()
        cls.repo, _, commit, blob = cls.fixture.__enter__()
        cls.commit, cls.blob, cls._select = staticmethod(commit), staticmethod(blob), staticmethod(p.selected_profile)
        cls._immutable_m_cache = {}
    @classmethod
    def tearDownClass(cls):
        cls._immutable_m_cache.clear()
        cls.fixture.__exit__(None, None, None)
    def setUp(self):
        self.original = c._entries(x.M, self.repo)
        self.good = self.original | {path: ('100644', 'blob', self.blob(checksum_bytes(path, (c.ROOT / path).read_bytes()))) for path in x.CAPS}
        self.pure = self.commit([x.M], self.good)
        self.feature = self.commit([x.M, self.pure], self.good)
        self.overlay = self.good | c.RELEASE_DOCS
        self.release = self.commit([p.R, self.feature], self.overlay)
        self.args = (self.repo, c._git, c._entries, c._feature_profile, c.RELEASE, c.RELEASE_TREE, dict(c.RELEASE_DOCS))
    def verified_baseline(self, ref, *args, **kwargs):
        callbacks = all(actual is expected for actual, expected in zip(args[1:4], self.args[1:4]))
        immutable = (x.M, x.M_TREE, x.M_PARENTS) == (
            '981d7b23af1c5c8174352c4564aa65b1557cc546', 'c3d7780ce761dac4da71d97a010381ec5074f69f',
            ('7de3244adc367fa60463d1e3b64c92f211d2fda8', 'd52937c98d441f3ee49eb9decd9101cade654748'))
        if ref != x.M or not immutable or kwargs or not callbacks or args != self.args:
            return self._select(ref, *args, **kwargs)
        key = (ref, *args[:6], tuple(sorted(args[6].items())))
        if key not in self._immutable_m_cache:
            self._immutable_m_cache[key] = dict(self._select(ref, *args))
        return dict(self._immutable_m_cache[key])
    def selected(self, ref, git=c._git, fresh=False):
        arguments = (self.repo, git, *self.args[2:])
        if fresh: return self._select(ref, *arguments)
        with patch.object(p, 'selected_profile', side_effect=self.verified_baseline):
            return self._select(ref, *arguments)
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
    def test_exact_m_identity_and_fresh_historical_validation(self):
        self.assertEqual((x.M, x.M_TREE, x.M_PARENTS), (
            '981d7b23af1c5c8174352c4564aa65b1557cc546', 'c3d7780ce761dac4da71d97a010381ec5074f69f',
            ('7de3244adc367fa60463d1e3b64c92f211d2fda8', 'd52937c98d441f3ee49eb9decd9101cade654748')))
        self.assertEqual(self.selected(x.M, fresh=True), self.original)
        self.assertIsNone(x.select(x.M, *self.args))
        with patch.object(previous, 'content', wraps=previous.content) as historical:
            self.assertEqual(self.selected(self.pure, fresh=True), self.good)
            self.assertEqual(self.selected(self.pure, fresh=True), self.good)
            self.assertEqual(historical.call_count, 2)
        for command, replacement in ((('show', '-s', '--format=%P', x.M), b'\n'),
                (('show', '-s', '--format=%P', x.M), ' '.join(reversed(x.M_PARENTS)).encode()),
                (('rev-parse', x.M + '^{tree}'), b'0' * 40 + b'\n')):
            def altered(*args, root):
                return replacement if args == command else c._git(*args, root=root)
            with self.assertRaises(AssertionError):
                self.selected(self.pure, altered)
    def test_ordered_d_i_j_and_exact_four_document_overlay(self):
        with self.assertRaisesRegex(AssertionError, 'unknown_composition_profile'):
            self._select(self.pure, *self.args, profile='unknown')
        for ref, expected in ((self.pure, self.good), (self.feature, self.good), (self.release, self.overlay)):
            self.assertEqual(self.selected(ref), expected)
        self.assertEqual(x.topology(self.release, self.repo, c._git, p.R), ('release', self.feature, self.pure))
        for entries in (self.original, self.overlay, self.changed(x.CASES, b'changed\n')):
            self.bad_content(entries, [x.M, self.pure])
        self.assertEqual((p.R, p.R_TREE, len(c.RELEASE_DOCS)),
            ('e2e011f7f2a3a1df838bbd588106205b999db610', 'c0dfe00fdcc7ebc8e26acaad5d18ff3f94df9ba3', 4))
        for path in c.RELEASE_DOCS:
            for entries in (self.overlay | {path: self.good[path]}, {k: v for k, v in self.overlay.items() if k != path},
                            self.overlay | {path: ('100755', *self.overlay[path][1:])}):
                self.bad_content(entries, [p.R, self.feature])
        self.bad_content(self.overlay | {'extra.md': ('100644', 'blob', self.blob(b'extra'))}, [p.R, self.feature])
    def test_wrong_repeated_nested_correction_and_same_tree_parents_reject(self):
        impostor, correction = self.commit([], self.original), self.commit([self.pure], self.good)
        for parents in ([], [self.pure], [self.pure, x.M], [x.M, self.pure, p.R], [x.M, x.M], [x.M, self.feature],
                [p.R], [p.R, self.pure], [self.feature, p.R], [p.R, self.feature, self.pure], [p.R, self.release],
                [impostor], [impostor, self.pure], [correction], [x.M, correction], [previous.M, self.pure]):
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
    def test_all_thirteen_paths_modes_pins_and_entry_counts_are_exact(self):
        self.assertEqual(self.content(), self.good)
        self.assertEqual((len(self.original), len(self.good), len(x.CAPS), len(x.BASE_PINS)), (1764, 1770, 13, 7))
        self.assertEqual(x.SOURCE_PINS.keys(), x.CAPS.keys() - {x.PROFILE})
        self.assertEqual(x.CAPS[x.PROFILE], (400, 400))
        self.assertEqual(self.good[x.PROFILE][2], c._blob(checksum_bytes(x.PROFILE, (c.ROOT / x.PROFILE).read_bytes())))
        for path, row in x.SOURCE_PINS.items():
            data = checksum_bytes(path, (c.ROOT / path).read_bytes())
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
        self.bad_content(self.changed('unreviewed-extra.py', b'extra\n'))
        self.bad_content(self.changed('services/cloud-agent/src/main.rs', b'changed\n'))
    def test_individual_and_total_budgets_fail_closed(self):
        self.assertEqual((x.DELTA_LIMIT, sum(cap[1] for cap in x.CAPS.values())), (1800, 1734))
        data = {path: checksum_bytes(path, (c.ROOT / path).read_bytes()) for path in x.CAPS}
        def budgets(git=c._git):
            return p.authenticated._budgets(self.pure, x.M, self.repo, git, data, x.CAPS, x.DELTA_LIMIT, 'staging_delta_budget')
        budgets()
        for path, (_, delta) in x.CAPS.items():
            with patch.dict(x.CAPS, {path: (len(data[path].splitlines()) - 1, delta)}), self.assertRaises(AssertionError):
                budgets()
            for row in (f'{delta + 1}\t0\t{path}\n'.encode(), b'', b'-\t-\t' + path.encode(), b'1\t0',
                        b'1\t0\twrong', f'1\t0\t{path}\nextra\n'.encode(), f'-1\t0\t{path}\n'.encode()):
                def malformed(*args, root):
                    return row if args == ('diff', '--numstat', x.M, self.pure, '--', path) else c._git(*args, root=root)
                with self.assertRaises(AssertionError):
                    budgets(malformed)
        with patch.object(x, 'DELTA_LIMIT', 0), self.assertRaisesRegex(AssertionError, 'staging_delta_budget'):
            budgets()
    def test_exact_dispatch_and_seven_inverses_recover_complete_m_bytes(self):
        self.assertEqual((len(x.DISPATCH.splitlines()), len(x.NORMALIZE.splitlines())), (4, 2))
        self.assertEqual(x.FRAGMENTS.keys(), x.BASE_PINS.keys())
        self.assertEqual(len(x.FRAGMENTS), 7)
        for path in x.BASE_PINS:
            current, frozen = (c.ROOT / path).read_bytes(), self.frozen(path)
            with patch('builtins.open', side_effect=AssertionError('IO forbidden')), patch('io.open', side_effect=AssertionError('IO forbidden')), patch('subprocess.check_output', side_effect=AssertionError('git forbidden')), patch('subprocess.Popen', side_effect=AssertionError('process forbidden')), patch('tempfile.TemporaryDirectory', side_effect=AssertionError('extraction forbidden')):
                self.assertEqual(x.normalize(path, current), frozen, path)
                self.assertEqual(x.normalize(path, frozen), frozen, path)
        current = (c.ROOT / x.DISPATCHER).read_bytes()
        self.assertEqual((current.count(x.DISPATCH), current.count(x.NORMALIZE)), (1, 1))
        self.assertEqual(current.replace(x.DISPATCH, b'', 1).replace(x.NORMALIZE, b'', 1), self.frozen(x.DISPATCHER))
        self.assertEqual(c._git('diff', '--numstat', x.M, self.pure, '--', x.DISPATCHER, root=self.repo),
                         f'6\t0\t{x.DISPATCHER}\n'.encode())
        self.assertEqual(x.normalize('unmapped', b'unchanged'), b'unchanged')
        self.assertEqual((len(x.PRIOR_PINS), sum(map(len, x.PRIOR_PINS.values()))), (3, 12))
        self.assertEqual({path: len(pins) for path, pins in x.PRIOR_PINS.items()}, {
            'scripts/rc_pretag_composition_tests.py': 8, 'scripts/rc_publication_executor.py': 1, x.WORKFLOW: 3})
        for path, pins in x.PRIOR_PINS.items():
            self.assertEqual(len(pins), len(set(pins)))
            self.assertNotIn(x.BASE_PINS[path][1:3], pins)
            for pin in pins:
                prior = c._git('cat-file', 'blob', pin[0], root=self.repo)
                self.assertEqual(o.pin(prior), pin)
                with patch('builtins.open', side_effect=AssertionError('IO forbidden')), patch('io.open', side_effect=AssertionError('IO forbidden')), patch('subprocess.check_output', side_effect=AssertionError('git forbidden')), patch('subprocess.Popen', side_effect=AssertionError('process forbidden')), patch('tempfile.TemporaryDirectory', side_effect=AssertionError('extraction forbidden')):
                    self.assertEqual(x.normalize(path, prior), prior)
    def test_missing_duplicate_outside_and_binary_inverse_edits_reject(self):
        for path, fragments in x.FRAGMENTS.items():
            current = checksum_bytes(path, (c.ROOT / path).read_bytes())
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
        for path, pins in x.PRIOR_PINS.items():
            for pin in pins:
                prior = c._git('cat-file', 'blob', pin[0], root=self.repo)
                weakened = prior.replace(b'self.assertEqual(', b'self.assertNotEqual(', 1)
                if weakened == prior: weakened = prior.replace(b'assert ', b'assert False and ', 1)
                for bad in (prior + b'# outside\n', b'\xff' + prior, weakened):
                    if bad == prior: continue
                    with self.assertRaises(AssertionError): x.normalize(path, bad)
        path = 'scripts/rc_pretag_download_budget_cases.py'
        current = (c.ROOT / path).read_bytes()
        bad = current.replace(b'self.assertEqual(', b'self.assertNotEqual(', 1)
        self.assertNotEqual(bad, current)
        with patch.dict(x.SOURCE_PINS, {path: ('100644', *o.pin(bad), len(bad), len(bad.splitlines()))}), self.assertRaises(AssertionError):
            x.normalize(path, bad)
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
        for offset, value in ((5, '0' * 40), (6, {})):
            arguments = list(self.args); arguments[offset] = value
            with self.assertRaises(AssertionError): x.content(self.pure, *arguments)
        with patch.object(p.authenticated, '_budgets', side_effect=AssertionError('budget terminal')), self.assertRaisesRegex(AssertionError, 'budget terminal'):
            self.content()
    def test_actual_candidate_validation_is_never_cached(self):
        with patch.object(x, 'content', wraps=x.content) as checked:
            self.assertEqual(self.selected(self.pure), self.good)
            self.assertEqual(self.selected(self.pure), self.good)
            self.assertEqual(checked.call_count, 2)
        self.bad_content(self.changed(x.CASES, b'changed after valid selection\n'))
        baseline = self.verified_baseline(x.M, *self.args)
        baseline.clear()
        self.assertEqual(self.verified_baseline(x.M, *self.args), self.original)
        for offset, value in ((2, lambda ref, root: {}), (3, lambda ref, root: {}), (5, '0' * 40), (6, {})):
            arguments = list(self.args)
            arguments[offset] = value
            with patch.object(self, '_select', side_effect=AssertionError('fresh required')) as fresh, self.assertRaisesRegex(AssertionError, 'fresh required'):
                self.verified_baseline(x.M, *arguments)
            fresh.assert_called_once()
        with patch.object(x, 'M_TREE', '0' * 40), patch.object(self, '_select', side_effect=AssertionError('fresh required')), self.assertRaisesRegex(AssertionError, 'fresh required'):
            self.verified_baseline(x.M, *self.args)
        runtime = ast.parse((c.ROOT / x.PROFILE).read_text())
        self.assertFalse(any('cache' in (getattr(node, 'id', getattr(node, 'attr', getattr(node, 'name', ''))) or '') for node in ast.walk(runtime)))
    def test_original1328_strict303_consumer452_ids_and_bodies_are_preserved(self):
        original = [item for group in lc.GROUPS for item in lc.inventory(group)] + lc.ids(y.CLASS) + old_cases.inventory() + previous_cases.inventory() + final_cases.inventory() + download_cases.inventory()
        pt.inventory_ids(original, 1328, '8bc7a8cf4180f8bc4463af2491a6993a883067641b6173382e186cf7c80ce862')
        pt.inventory_ids(original + inventory(), 1352, 'ea0dc69cba21c7fc078299270b5944372520607cc2b4401b7c3a231dfb17c03d')
        workflow = old_cases.inventory() + previous_cases.inventory() + final_cases.inventory() + download_cases.inventory()
        pt.inventory_ids(workflow, 144, '90731b8f23afb0a4d31ff3b280e1b5bdc873b61edc0a2c813817b74116ada8c3')
        pt.inventory_ids(workflow + inventory(), 168, 'dd810f84cb50ddd5c5dfdc29b1beafdf481a37ce41b7f49cdf96ce7cba027886')
        method = next(node for node in ast.walk(ast.parse(self.frozen(p.TESTS))) if isinstance(node, ast.FunctionDef)
                      and node.name == 'test_protected_source_versions_gates_workflows_and_old_452_are_unchanged')
        modules = ast.literal_eval(method.body[0].value.func.value).split()
        with patch('tempfile.TemporaryDirectory', side_effect=AssertionError('discovery materialized')):
            strict = [test.id() for test in c._flatten(unittest.defaultTestLoader.discover(str(c.ROOT / 'scripts'), pattern='rc_pretag*_tests.py'))]
            consumer = [item for module in modules for item in lc.ids(module) if item.split('.', 1)[0] == module]
        pt.inventory_ids(strict, 303, '0ecc366c2018a6a1e20d3f59ed9ca66645d9334324cd517682894cabde923125')
        pt.inventory_ids(consumer, 452, 'd01db4e6cd605c6636423e27c8c0409e90aba217cc0e6930474f59a24b57f372')
        allowed = {'rc_pretag_composition_tests': {'test_consumer_inverse_reconstructs_pinned_j',
                'test_extraction_mutations_do_not_reconstruct_j'},
            'rc_pretag_download_budget_cases': {'setUp', 'test_all_paths_modes_pins_and_entry_counts_are_exact',
                'test_individual_and_total_budgets_fail_closed', 'test_exact_dispatch_and_seven_inverses_recover_complete_f_bytes',
                'test_missing_duplicate_outside_and_binary_inverse_edits_reject', 'test_actual_candidate_validation_is_never_cached',
                'test_original1304_strict303_consumer452_ids_and_bodies_are_preserved',
                'test_historical_consumer_envelope_and_readonly_workflow_remain_bounded'}}
        class SourceOperands(ast.NodeTransformer):
            def visit_Call(self, node):
                if isinstance(node.func, ast.Attribute) and node.func.attr == 'decode' and isinstance(node.func.value, ast.Call):
                    inner = node.func.value
                    if isinstance(inner.func, ast.Name) and inner.func.id == 'staging_bytes':
                        result = copy.deepcopy(inner.args[1]); result.func.attr = 'read_text'
                        return result
                node = self.generic_visit(node)
                return node.args[1] if isinstance(node.func, ast.Name) and node.func.id in ('staging_bytes', 'integration_bytes') else node
        def methods(data):
            found = {}
            def collect(node, scope=()):
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    scope += (node.name,)
                    if not isinstance(node, ast.ClassDef): found[scope] = node
                for child in ast.iter_child_nodes(node): collect(child, scope)
            collect(ast.parse(data))
            return found
        changed = set()
        for module in {item.split('.', 1)[0] for item in original}:
            path = 'scripts/' + module + '.py'
            current, frozen = checksum_bytes(path, (c.ROOT / path).read_bytes()), self.frozen(path)
            self.assertEqual(x.normalize(path, current), frozen, path)
            before, after = methods(frozen), methods(current)
            self.assertEqual(before.keys(), after.keys(), path)
            for name in before:
                node = copy.deepcopy(after[name])
                if ast.dump(before[name]) != ast.dump(node):
                    self.assertIn(name[-1], allowed.get(module, set()))
                    changed.add((module, name[-1])); node = SourceOperands().visit(node)
                self.assertEqual(ast.dump(before[name]), ast.dump(node), path + ':' + '.'.join(name))
        self.assertEqual(changed, {(module, name) for module, names in allowed.items() for name in names})
        self.assertFalse(set(original) & set(inventory()))
    def test_readonly_workflow_and_held_sources_remain_bounded(self):
        text = windows_launch_bytes(x.WORKFLOW, (c.ROOT / x.WORKFLOW).read_bytes()).decode()
        for fragment in ("on:\n  push:\n    branches: ['ci/issue88-publisher-executor-*']", 'permissions:\n  contents: read',
                "os: [ubuntu-22.04, ubuntu-24.04]", "python-version: '3.12'", 'fetch-depth: 0, persist-credentials: false',
                "sha == os.environ['GITHUB_SHA']", 'parents == [profile.M]', 'before = checked()', 'checked() == before',
                'x.inventory()', 'x.execution_valid(loaded, result)', 'admission.inventory()', 'admission.execution_valid(loaded, result)',
                'final_admission.inventory()', 'final_admission.execution_valid(loaded, result)',
                'download_budget.inventory()', 'download_budget.execution_valid(loaded, result)',
                'staging_budget.inventory()', 'staging_budget.execution_valid(loaded, result)', 'timeout-minutes: 30',
                'staging-budget-inventory.json', 'staging-budget-cases.log', "'production_ready': False",
                'actions/checkout@11d5960a326750d5838078e36cf38b85af677262',
                'actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065',
                'actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02'):
            self.assertIn(fragment, text)
        for forbidden in ('secrets.', 'GH_TOKEN', 'GITHUB_TOKEN', 'contents: write', 'workflow_dispatch:', 'pull_request:', 'gh release', 'curl ', 'pip install'):
            self.assertNotIn(forbidden, text)
        held = {'docs/specs/rc-source-assembly-engineering/' + name for name in ('README.md', 'design.md', 'requirements.md',
            'tasks.md', 'subspecs/focused-validation/spec.md', 'subspecs/source-evidence/spec.md')}
        held |= {'scripts/rc_source_assembly.py', 'scripts/rc_source_assembly_dispatch_tests.py', 'scripts/rc_source_assembly_tests.py', 'tests/delivery/test_linux_lifecycle_wiring.py'}
        self.assertEqual(len(held), 10)
        self.assertFalse(held & self.good.keys())
        self.assertTrue(all(not (c.ROOT / path).exists() and not (c.ROOT / path).is_symlink() for path in held))
        for path in ('scripts/rc_release_eligibility.py', 'scripts/rc_publication_contract.py', 'scripts/rc_publication_admission.py',
                'scripts/rc_consumer_io.py', 'scripts/rc_consumer_transport.py', 'scripts/rc_consumer_transport_worker.py',
                'scripts/rc_consumer_proof_fixtures.py', 'scripts/rc_consumer_default_worker_proof.py', 'scripts/rc_consumer_default_worker_proof_tests.py',
                'scripts/rc_consumer_c_93c2ad95_io.txt', 'src-tauri/src/workspace_snapshots/filesystem.rs'):
            self.assertEqual(checksum_bytes(path, (c.ROOT / path).read_bytes()), self.frozen(path), path)
        self.assertTrue(all(self.good[path] == value for path, value in self.original.items() if path not in x.CAPS))
    def test_new24_inventory_and_exceptional_outcomes_reject(self):
        loaded = inventory()
        self.assertEqual([len(names) for names in x.NEW_CASES.values()], [12, 12])
        good = dict(executed_ids=loaded, testsRun=24, skipped=[], expectedFailures=[], unexpectedSuccesses=[], wasSuccessful=lambda: True)
        self.assertTrue(execution_valid(loaded, SimpleNamespace(**good)))
        for field, value in (('skipped', [('id', 'reason')]), ('expectedFailures', [('id', 'failure')]),
                            ('unexpectedSuccesses', ['id']), ('testsRun', 23), ('wasSuccessful', lambda: False)):
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
