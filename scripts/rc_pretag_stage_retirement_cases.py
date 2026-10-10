"""Finite stage retirement admission; modeled source checks confer no release authority."""
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
import rc_pretag_supervisor_readiness_profile as previous
import rc_pretag_supervisor_readiness_cases as readiness
import rc_pretag_publisher_executor_cases as publisher
import rc_pretag_integration_admission_cases as admission
import rc_pretag_final_admission_cases as final
import rc_pretag_download_budget_cases as download
import rc_pretag_staging_budget_cases as staging
import rc_pretag_checksum_budget_cases as checksum
import rc_pretag_archive_budget_cases as archive
import rc_pretag_staged_bytes_cases as staged
import rc_pretag_stage_retirement_profile as x
from rc_pretag_source_observation_profile import normalize as source_observation_bytes
from rc_pretag_git_budget_profile import normalize as git_budget_bytes

F_BINDING = ('f0fdfba5cd48b7cad477f1e2cb77bb70153ad657', '84ff6fd8a0936f99d0b1267c78bd50ba52a70fa0', ('69e749736b95b5921b4f6352838f69860c7a0a4e', 'fa2a2931417694a37ab60008a90f1c81aab60159'))
IO = 'scripts/rc_consumer_io.py'
STAGE = 'scripts/rc_publication_stage.py'

def inventory():
    expected = [cls + '.' + name for cls, names in x.NEW_CASES.items() for name in names]
    actual = [item for cls in x.NEW_CASES for item in lc.ids(cls)]
    pt.inventory_ids(expected, 48, x.DIGEST)
    pt.inventory_ids(actual, 48, x.DIGEST)
    assert Counter(actual) == Counter(expected)
    return expected

def execution_valid(loaded, result):
    pt.inventory_ids(loaded, 48, x.DIGEST)
    assert Counter(loaded) == Counter(inventory())
    executed = getattr(result, 'executed_ids', [])
    pt.inventory_ids(executed, 48, x.DIGEST)
    return (result.wasSuccessful() and not result.skipped and not result.expectedFailures
            and not result.unexpectedSuccesses and Counter(executed) == Counter(loaded)
            and result.testsRun == len(set(executed)) == 48)

class StageRetirementCompositionCases(unittest.TestCase):
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
        self.good = self.original | {path: ('100644', 'blob', self.blob(git_budget_bytes(path, (c.ROOT / path).read_bytes()))) for path in x.CAPS}
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
        self.assertEqual(x.M_RAW, (1257, '98d8ec5a92e00342b5b7b40be5b19af2490892f2bcd9b51ad3e42e8ebde3c8a2'))
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

    def test_fifteen_exact_paths_modes_pins_and_entry_count(self):
        self.assertEqual(self.content(), self.good)
        self.assertEqual((len(self.original), len(self.good), len(x.CAPS), len(x.BASE_PINS)), (1795, 1803, 15, 7))
        self.assertEqual(x.SOURCE_PINS.keys(), x.CAPS.keys() - {x.PROFILE})
        self.assertEqual(x.CAPS, {'scripts/rc_consumer_io.py': (480, 90), 'scripts/rc_publication_stage.py': (380, 40), 'scripts/rc_publication_stage_cases.py': (360, 6), 'scripts/rc_publication_staged_bytes_cases.py': (500, 4), 'scripts/rc_publication_retirement.py': (260, 260), 'scripts/rc_publication_retirement_cases.py': (470, 470), 'scripts/rc_publication_retirement_lifetime_cases.py': (280, 280), 'scripts/rc_pretag_supervisor_readiness_profile.py': (185, 6), 'scripts/rc_pretag_supervisor_readiness_cases.py': (350, 30), 'scripts/rc_pretag_stage_retirement_profile.py': (350, 350), 'scripts/rc_pretag_stage_retirement_cases.py': (450, 450), '.github/workflows/issue88-publication-executor.yml': (165, 14), 'docs/specs/issue88-stage-retirement/requirements.md': (60, 60), 'docs/specs/issue88-stage-retirement/design.md': (90, 90), 'docs/specs/issue88-stage-retirement/tasks.md': (70, 70)})
        self.assertEqual(self.good[x.PROFILE][2], c._blob(git_budget_bytes(x.PROFILE, (c.ROOT / x.PROFILE).read_bytes())))
        for path, row in x.SOURCE_PINS.items():
            data = git_budget_bytes(path, (c.ROOT / path).read_bytes())
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
        self.assertEqual((x.DELTA_LIMIT, sum(cap[1] for cap in x.CAPS.values())), (2250, 2220))
        data = {path: git_budget_bytes(path, (c.ROOT / path).read_bytes()) for path in x.CAPS}
        def budgets(git=c._git):
            return p.authenticated._budgets(self.pure, x.M, self.repo, git, data, x.CAPS, x.DELTA_LIMIT, 'stage_retirement_delta_budget')
        budgets()
        for path, (_, delta) in x.CAPS.items():
            with patch.dict(x.CAPS, {path: (len(data[path].splitlines()) - 1, delta)}), self.assertRaises(AssertionError): budgets()
            for row in (f'{delta + 1}\t0\t{path}\n'.encode(), b'', b'-\t-\t' + path.encode(), b'1\t0', b'1\t0\twrong', f'1\t0\t{path}\nextra\n'.encode(), f'-1\t0\t{path}\n'.encode()):
                def malformed(*args, root):
                    return row if args == ('diff', '--numstat', x.M, self.pure, '--', path) else c._git(*args, root=root)
                with self.assertRaises(AssertionError): budgets(malformed)
        with patch.object(x, 'DELTA_LIMIT', 0), self.assertRaisesRegex(AssertionError, 'stage_retirement_delta_budget'): budgets()

    def test_seven_full_byte_inverses_and_six_dispatch_lines(self):
        self.assertEqual((len(x.DISPATCH.splitlines()), len(x.NORMALIZE.splitlines())), (4, 2))
        self.assertEqual(x.FRAGMENTS.keys(), x.BASE_PINS.keys())
        self.assertEqual(len(x.FRAGMENTS), 7)
        for path in x.BASE_PINS:
            current, frozen = git_budget_bytes(path, (c.ROOT / path).read_bytes()), self.frozen(path)
            with patch('builtins.open', side_effect=AssertionError('IO')), patch('io.open', side_effect=AssertionError('IO')), patch('subprocess.Popen', side_effect=AssertionError('process')), patch('tempfile.TemporaryDirectory', side_effect=AssertionError('extract')):
                self.assertEqual(x.normalize(path, current), frozen, path)
                self.assertEqual(x.normalize(path, frozen), frozen, path)
        current = (c.ROOT / x.DISPATCHER).read_bytes()
        self.assertEqual((current.count(x.DISPATCH), current.count(x.NORMALIZE)), (1, 1))
        self.assertEqual(current.replace(x.DISPATCH, b'', 1).replace(x.NORMALIZE, b'', 1), self.frozen(x.DISPATCHER))
        self.assertEqual(c._git('diff', '--numstat', x.M, self.pure, '--', x.DISPATCHER, root=self.repo), f'6\t0\t{x.DISPATCHER}\n'.encode())
        self.assertEqual(x.normalize('unmapped', b'unchanged'), b'unchanged')

    def test_twelve_historical_identities_are_finite_and_immutable(self):
        self.assertEqual({path: len(pins) for path, pins in x.PRIOR_PINS.items()}, {IO: 2, STAGE: 2, x.WORKFLOW: 8})
        import rc_pretag_staged_bytes_profile as staged_profile
        for path, module in ((IO, staged_profile), (STAGE, staged_profile), (x.WORKFLOW, previous)):
            self.assertEqual(x.PRIOR_PINS[path], (module.BASE_PINS[path][1:3], *module.PRIOR_PINS.get(path, ())))
        for path, pins in x.PRIOR_PINS.items():
            self.assertEqual(len(pins), len(set(pins))); self.assertNotIn(x.BASE_PINS[path][1:3], pins)
            for pin in pins:
                prior = c._git('cat-file', 'blob', pin[0], root=self.repo)
                self.assertEqual(o.pin(prior), pin); self.assertEqual(x.normalize(path, prior), prior)
                for bad in (prior + b'# outside\n', b'\xff' + prior):
                    with self.assertRaises(AssertionError): x.normalize(path, bad)

    def test_missing_duplicate_outside_and_binary_inverse_changes_reject(self):
        for path, fragments in x.FRAGMENTS.items():
            current = git_budget_bytes(path, (c.ROOT / path).read_bytes())
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
        runtime = ast.parse(git_budget_bytes(x.PROFILE, (c.ROOT / x.PROFILE).read_bytes()).decode())
        self.assertFalse(any('cache' in (getattr(n, 'id', getattr(n, 'attr', getattr(n, 'name', ''))) or '') for n in ast.walk(runtime)))

    def test_original1445_strict303_consumer452_ids_and_assertions_are_preserved(self):
        original = [item for group in lc.GROUPS for item in lc.inventory(group)] + lc.ids(y.CLASS)
        groups = (publisher, admission, final, download, staging, checksum, archive, staged)
        original += [item for group in groups for item in group.inventory()]
        pt.inventory_ids(original, 1433, 'bea84742dea5afcad6d7cbcfad99db412aa03e0ac323cda1f29013cd096fc470')
        original += readiness.inventory()
        self.assertEqual(len(original), len(set(original))); self.assertEqual(len(original), 1445)
        self.assertEqual(len(set(original + inventory())), 1493); self.assertFalse(set(original) & set(inventory()))
        method = next(n for n in ast.walk(ast.parse(self.frozen(p.TESTS))) if isinstance(n, ast.FunctionDef) and n.name == 'test_protected_source_versions_gates_workflows_and_old_452_are_unchanged')
        modules = ast.literal_eval(method.body[0].value.func.value).split()
        with patch('tempfile.TemporaryDirectory', side_effect=AssertionError('discovery materialized')):
            strict = [test.id() for test in c._flatten(unittest.defaultTestLoader.discover(str(c.ROOT / 'scripts'), pattern='rc_pretag*_tests.py'))]
            consumer = [item for module in modules for item in lc.ids(module) if item.split('.', 1)[0] == module]
        pt.inventory_ids(strict, 303, '0ecc366c2018a6a1e20d3f59ed9ca66645d9334324cd517682894cabde923125')
        pt.inventory_ids(consumer, 452, 'd01db4e6cd605c6636423e27c8c0409e90aba217cc0e6930474f59a24b57f372')
        allowed = {
            'rc_publication_stage_cases': {'test_file_replacement_link_and_inventory_changes_reject'},
            'rc_publication_staged_bytes_cases': {'test_revalidation_drift_and_io_errors_precede_polls'},
            'rc_pretag_supervisor_readiness_cases': {'setUp', 'test_all_ten_paths_modes_pins_and_entry_counts_are_exact',
                'test_individual_and_total_budgets_fail_closed', 'test_five_inverses_restore_complete_f_bytes',
                'test_missing_duplicate_outside_binary_and_assertion_edits_reject', 'test_actual_candidate_validation_is_never_cached',
                'test_original1433_strict303_consumer452_ids_and_assertions_are_preserved',
                'test_sustained_phase_readiness_and_bounded_failure_contracts_are_preserved',
                'test_readonly_workflow_inventory_and_exceptional_outcomes_are_exact'},
        }
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
                           and node.func.value.func.id == 'retirement_bytes' and not node.args and not node.keywords)
                node = self.generic_visit(node)
                if decoded:
                    source = node.func.value
                    assert isinstance(source, ast.Call) and isinstance(source.func, ast.Attribute)
                    assert source.func.attr == 'read_bytes' and not source.args and not source.keywords
                    source.func.attr = 'read_text'
                    return source
                if isinstance(node.func, ast.Name) and node.func.id == 'retirement_bytes':
                    self.assert_valid(node)
                    return node.args[1]
                return node
            @staticmethod
            def assert_valid(node):
                assert len(node.args) == 2 and not node.keywords
        changed = set()
        for module in {item.split('.', 1)[0] for item in original}:
            path = 'scripts/' + module + '.py'
            current, frozen = source_observation_bytes(path, (c.ROOT / path).read_bytes()), self.frozen(path)
            self.assertEqual(x.normalize(path, current), frozen, path)
            before, after = methods(frozen), methods(current)
            self.assertEqual(before.keys(), after.keys(), path)
            for key, method in before.items():
                adjusted = UndoOperands().visit(copy.deepcopy(after[key]))
                self.assertFalse(assertions(method) - assertions(adjusted), (path, key))
                if ast.dump(method) != ast.dump(after[key]): changed.add((module, key[1]))
                if key[1] not in allowed.get(module, ()): self.assertEqual(ast.dump(method), ast.dump(after[key]), (path, key))
                elif module == 'rc_pretag_supervisor_readiness_cases': self.assertEqual(ast.dump(method), ast.dump(adjusted), (path, key))
        self.assertEqual(changed, {(module, name) for module, names in allowed.items() for name in names})
        flow = [item for group in groups for item in group.inventory()] + readiness.inventory()
        self.assertEqual(len(flow), len(set(flow))); self.assertEqual(len(flow), 261)
        self.assertEqual(len(set(flow + inventory())), 309)
        io = (c.ROOT / IO).read_text(); baseline = self.frozen(IO).decode()
        def definition(text, name, cls=None):
            tree = ast.parse(text)
            scope = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls) if cls else tree
            node = next(n for n in scope.body if isinstance(n, ast.FunctionDef) and n.name == name)
            return ast.get_source_segment(text, node)
        self.assertEqual(definition(io, 'close', 'PrivateRoot'), definition(baseline, 'close', 'PrivateRoot'))
        self.assertEqual(definition(io, '_directory'), definition(baseline, '_directory'))
        retirement = (c.ROOT / 'scripts/rc_publication_retirement.py').read_text()
        close = definition(retirement, 'close_stream', 'StageRootOwner')
        self.assertIn('if raw.closed and stream.closed:', close)
        self.assertLess(close.index('if raw.closed and stream.closed:'), close.index('self.close_fd(fd)'))
        self.assertIn('self.unclosed[fd] = stream', close)
        for path in ('requirements', 'design'):
            spec = (c.ROOT / ('docs/specs/issue88-stage-retirement/' + path + '.md')).read_text()
            for text in ('before destruction', 'remaining entries', 'rollback'):
                self.assertIn(text, spec)

    def test_new48_inventory_readonly_workflow_and_exceptional_outcomes(self):
        text = git_budget_bytes(x.WORKFLOW, (c.ROOT / x.WORKFLOW).read_bytes()).decode()
        for fragment in ("branches: ['ci/issue88-publisher-executor-*']", 'permissions:\n  contents: read', 'timeout-minutes: 30', 'frozen three hundred nine cases', 'import rc_pretag_stage_retirement_profile as profile', 'supervisor_readiness.inventory()', 'supervisor_readiness.execution_valid(loaded, result)', 'supervisor-readiness-cases.log', 'supervisor-readiness-inventory.json', 'stage_retirement.inventory()', 'stage_retirement.execution_valid(loaded, result)', 'stage-retirement-cases.log', 'stage-retirement-inventory.json', 'parents == [profile.M]', 'checked() == before', "'production_ready': False"):
            self.assertIn(fragment, text)
        for forbidden in ('secrets.', 'GH_TOKEN', 'GITHUB_TOKEN', 'contents: write', 'workflow_dispatch:', 'pull_request:', 'gh release', 'curl ', 'pip install'):
            self.assertNotIn(forbidden, text)
        self.assertTrue(all(self.good[path] == value for path, value in self.original.items() if path not in x.CAPS))
        held = {'scripts/rc_source_assembly.py', 'scripts/rc_source_assembly_dispatch_tests.py', 'scripts/rc_source_assembly_tests.py', 'tests/delivery/test_linux_lifecycle_wiring.py'}
        self.assertFalse(held & self.good.keys()); self.assertTrue(all(not (c.ROOT / path).exists() for path in held))
        loaded = inventory()
        good = dict(executed_ids=loaded, testsRun=48, skipped=[], expectedFailures=[], unexpectedSuccesses=[], wasSuccessful=lambda: True)
        self.assertTrue(execution_valid(loaded, SimpleNamespace(**good)))
        for field, value in (('skipped', [('id', 'reason')]), ('expectedFailures', [('id', 'failure')]), ('unexpectedSuccesses', ['id']), ('testsRun', 47), ('wasSuccessful', lambda: False)):
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
