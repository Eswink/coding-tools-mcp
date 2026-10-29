"""Finite supervisor fixture admission; modeled source checks confer no release authority."""
import ast
from collections import Counter
import copy
import json
import os
import textwrap
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import rc_pretag_composition_tests as c
import rc_pretag_ownership_profile as o
import rc_pretag_publication_profile as p
import rc_pretag_publication_tests as pt
import rc_pretag_linux_package_cases as lc
import rc_pretag_yoke_repair_profile as y
import rc_pretag_staged_bytes_profile as previous
import rc_pretag_publisher_executor_cases as publisher
import rc_pretag_integration_admission_cases as admission
import rc_pretag_final_admission_cases as final
import rc_pretag_download_budget_cases as download
import rc_pretag_staging_budget_cases as staging
import rc_pretag_checksum_budget_cases as checksum
import rc_pretag_archive_budget_cases as archive
import rc_pretag_staged_bytes_cases as staged
import rc_pretag_supervisor_readiness_profile as x
from rc_pretag_stage_retirement_profile import normalize as retirement_bytes

F_BINDING = ('69e749736b95b5921b4f6352838f69860c7a0a4e', '0b14817a668e8d5f25b23ab3bb088fbf65ca8849', ('f9d414b0c85348da79fee80c3b04bf5a06daf1d7', '7f210716d43bb4a7097778c087e37ecbd86c7ec2'))
SUPERVISOR = 'scripts/rc_consumer_transport_supervisor_tests.py'

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

class SupervisorReadinessCompositionCases(unittest.TestCase):
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
        self.good = self.original | {path: ('100644', 'blob', self.blob(retirement_bytes(path, (c.ROOT / path).read_bytes()))) for path in x.CAPS}
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

    def test_exact_f_identity_and_fresh_historical_validation(self):
        self.assertEqual((x.M, x.M_TREE, x.M_PARENTS), F_BINDING)
        self.assertEqual(x.M_RAW, (1245, '578e9f9415c5f31ad15289e7abbe553a4a736bdf60e2e65e595e1157f01b8619'))
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

    def test_only_exact_d_i_j_topology_is_accepted(self):
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

    def test_all_ten_paths_modes_pins_and_entry_counts_are_exact(self):
        self.assertEqual(self.content(), self.good)
        self.assertEqual((len(self.original), len(self.good), len(x.CAPS), len(x.BASE_PINS)), (1790, 1795, 10, 5))
        self.assertEqual(x.SOURCE_PINS.keys(), x.CAPS.keys() - {x.PROFILE})
        self.assertEqual(x.CAPS, {SUPERVISOR: (462, 34), 'scripts/rc_pretag_composition_tests.py': (490, 2), x.DISPATCHER: (223, 6), 'scripts/rc_pretag_staged_bytes_cases.py': (447, 27), x.WORKFLOW: (149, 14), x.PROFILE: (300, 300), x.CASES: (400, 400), **{'docs/specs/issue88-supervisor-readiness/' + name + '.md': (cap, cap) for name, cap in (('requirements', 40), ('design', 70), ('tasks', 55))}})
        self.assertEqual(self.good[x.PROFILE][2], c._blob(retirement_bytes(x.PROFILE, (c.ROOT / x.PROFILE).read_bytes())))
        for path, row in x.SOURCE_PINS.items():
            data = retirement_bytes(path, (c.ROOT / path).read_bytes())
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

    def test_individual_and_total_budgets_fail_closed(self):
        self.assertEqual((x.DELTA_LIMIT, sum(cap[1] for cap in x.CAPS.values())), (1000, 948))
        data = {path: retirement_bytes(path, (c.ROOT / path).read_bytes()) for path in x.CAPS}
        def budgets(git=c._git):
            return p.authenticated._budgets(self.pure, x.M, self.repo, git, data, x.CAPS, x.DELTA_LIMIT, 'supervisor_readiness_delta_budget')
        budgets()
        for path, (_, delta) in x.CAPS.items():
            with patch.dict(x.CAPS, {path: (len(data[path].splitlines()) - 1, delta)}), self.assertRaises(AssertionError): budgets()
            for row in (f'{delta + 1}\t0\t{path}\n'.encode(), b'', b'-\t-\t' + path.encode(), b'1\t0', b'1\t0\twrong', f'1\t0\t{path}\nextra\n'.encode(), f'-1\t0\t{path}\n'.encode()):
                def malformed(*args, root):
                    return row if args == ('diff', '--numstat', x.M, self.pure, '--', path) else c._git(*args, root=root)
                with self.assertRaises(AssertionError): budgets(malformed)
        with patch.object(x, 'DELTA_LIMIT', 0), self.assertRaisesRegex(AssertionError, 'supervisor_readiness_delta_budget'): budgets()

    def test_five_inverses_restore_complete_f_bytes(self):
        self.assertEqual((len(x.DISPATCH.splitlines()), len(x.NORMALIZE.splitlines())), (4, 2))
        self.assertEqual(x.FRAGMENTS.keys(), x.BASE_PINS.keys())
        self.assertEqual(len(x.FRAGMENTS), 5)
        for path in x.BASE_PINS:
            current, frozen = retirement_bytes(path, (c.ROOT / path).read_bytes()), self.frozen(path)
            with patch('builtins.open', side_effect=AssertionError('IO')), patch('io.open', side_effect=AssertionError('IO')), patch('subprocess.Popen', side_effect=AssertionError('process')), patch('tempfile.TemporaryDirectory', side_effect=AssertionError('extract')):
                self.assertEqual(x.normalize(path, current), frozen, path)
                self.assertEqual(x.normalize(path, frozen), frozen, path)
        current = retirement_bytes(x.DISPATCHER, (c.ROOT / x.DISPATCHER).read_bytes())
        self.assertEqual((current.count(x.DISPATCH), current.count(x.NORMALIZE)), (1, 1))
        self.assertEqual(current.replace(x.DISPATCH, b'', 1).replace(x.NORMALIZE, b'', 1), self.frozen(x.DISPATCHER))
        self.assertEqual(c._git('diff', '--numstat', x.M, self.pure, '--', x.DISPATCHER, root=self.repo), f'6\t0\t{x.DISPATCHER}\n'.encode())
        self.assertEqual(x.normalize('unmapped', b'unchanged'), b'unchanged')

    def test_sixteen_historical_identities_are_exact(self):
        self.assertEqual({path: len(pins) for path, pins in x.PRIOR_PINS.items()}, {'scripts/rc_pretag_composition_tests.py': 9, x.WORKFLOW: 7})
        import rc_pretag_staging_budget_profile as old
        for path, module in (('scripts/rc_pretag_composition_tests.py', old), (x.WORKFLOW, previous)):
            self.assertEqual(x.PRIOR_PINS[path], (module.BASE_PINS[path][1:3], *module.PRIOR_PINS[path]))
        for path, pins in x.PRIOR_PINS.items():
            self.assertEqual(len(pins), len(set(pins))); self.assertNotIn(x.BASE_PINS[path][1:3], pins)
            for pin in pins:
                prior = c._git('cat-file', 'blob', pin[0], root=self.repo)
                self.assertEqual(o.pin(prior), pin); self.assertEqual(x.normalize(path, prior), prior)
                for bad in (prior + b'# outside\n', b'\xff' + prior):
                    with self.assertRaises(AssertionError): x.normalize(path, bad)

    def test_missing_duplicate_outside_binary_and_assertion_edits_reject(self):
        for path, fragments in x.FRAGMENTS.items():
            current = retirement_bytes(path, (c.ROOT / path).read_bytes())
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
            args = list(self.args); args[offset] = value
            with self.assertRaises(AssertionError): x.content(self.pure, *args)
        with patch.object(p.authenticated, '_budgets', side_effect=AssertionError('budget terminal')), self.assertRaisesRegex(AssertionError, 'budget terminal'): self.content()

    def test_actual_candidate_validation_is_never_cached(self):
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
        runtime = ast.parse(retirement_bytes(x.PROFILE, retirement_bytes(x.PROFILE, (c.ROOT / x.PROFILE).read_bytes())).decode())
        self.assertFalse(any('cache' in (getattr(n, 'id', getattr(n, 'attr', getattr(n, 'name', ''))) or '') for n in ast.walk(runtime)))

    def test_original1433_strict303_consumer452_ids_and_assertions_are_preserved(self):
        original = [item for group in lc.GROUPS for item in lc.inventory(group)] + lc.ids(y.CLASS)
        groups = (publisher, admission, final, download, staging, checksum, archive, staged)
        original += [item for group in groups for item in group.inventory()]
        pt.inventory_ids(original, 1433, 'bea84742dea5afcad6d7cbcfad99db412aa03e0ac323cda1f29013cd096fc470')
        self.assertEqual(len(set(original + inventory())), 1445); self.assertFalse(set(original) & set(inventory()))
        method = next(n for n in ast.walk(ast.parse(self.frozen(p.TESTS))) if isinstance(n, ast.FunctionDef) and n.name == 'test_protected_source_versions_gates_workflows_and_old_452_are_unchanged')
        modules = ast.literal_eval(method.body[0].value.func.value).split()
        with patch('tempfile.TemporaryDirectory', side_effect=AssertionError('discovery materialized')):
            strict = [test.id() for test in c._flatten(unittest.defaultTestLoader.discover(str(c.ROOT / 'scripts'), pattern='rc_pretag*_tests.py'))]
            consumer = [item for module in modules for item in lc.ids(module) if item.split('.', 1)[0] == module]
        pt.inventory_ids(strict, 303, '0ecc366c2018a6a1e20d3f59ed9ca66645d9334324cd517682894cabde923125')
        pt.inventory_ids(consumer, 452, 'd01db4e6cd605c6636423e27c8c0409e90aba217cc0e6930474f59a24b57f372')
        for module in {item.split('.', 1)[0] for item in original}:
            path = 'scripts/' + module + '.py'
            restored, frozen = x.normalize(path, retirement_bytes(path, (c.ROOT / path).read_bytes())), self.frozen(path)
            self.assertEqual(restored, frozen, path); self.assertEqual(ast.dump(ast.parse(restored)), ast.dump(ast.parse(frozen)), path)
        flow = [item for group in groups for item in group.inventory()]
        pt.inventory_ids(flow, 249, '0ccb7eed6c4d207f584474438e673e5ee7a9fc84bdfa2980bffe0f76bd4621cc')
        self.assertEqual(len(set(flow + inventory())), 261)

    def test_sustained_phase_readiness_and_bounded_failure_contracts_are_preserved(self):
        current, frozen = retirement_bytes(SUPERVISOR, (c.ROOT / SUPERVISOR).read_bytes()), self.frozen(SUPERVISOR)
        self.assertEqual(x.BASE_PINS[SUPERVISOR][1], 'e45608f7ae523c25ea5d12cd4d24cbd56a3f1c12')
        self.assertEqual(o.pin(current), x.SOURCE_PINS[SUPERVISOR][1:3])
        trees = [ast.parse(data) for data in (frozen, current)]
        classes = [next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'SupervisorTests') for tree in trees]
        methods = [{n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)} for cls in classes]
        self.assertEqual(methods[0].keys(), methods[1].keys())
        self.assertEqual(sum(name.startswith('test_') for name in methods[1]), 15)
        assertions = lambda n: Counter(ast.dump(a) for a in ast.walk(n) if isinstance(a, ast.Call) and isinstance(a.func, ast.Attribute) and a.func.attr.startswith('assert'))
        for name, before in methods[0].items():
            self.assertFalse(assertions(before) - assertions(methods[1][name]))
            if name not in ('failure', 'test_slow_network_phases_cancel_owned_worker'): self.assertEqual(ast.dump(before), ast.dump(methods[1][name]))
        test = methods[1]['test_slow_network_phases_cancel_owned_worker']
        self.assertEqual(sum((assertions(test) - assertions(methods[0][test.name])).values()), 5)
        call = next(n for n in ast.walk(test) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'failure')
        self.assertEqual({k.arg for k in call.keywords}, {'clock', 'deadline', 'check_active'})
        self.assertEqual(ast.literal_eval(next(k.value for k in call.keywords if k.arg == 'deadline')), 0.5)
        clock = next(n for n in ast.walk(test) if isinstance(n, ast.FunctionDef) and n.name == 'clock')
        namespace = {'time': SimpleNamespace(monotonic=lambda: 0)}
        source = 'def bind(progress, ready_by):\n    readiness_failed = False\n' + textwrap.indent(textwrap.dedent(ast.get_source_segment(current.decode(), clock)), '    ') + '\n    return clock\n'
        exec(compile(source, '<reviewed readiness clock>', 'exec'), namespace)
        for first in (1.0, 1.1):
            progress = []; bound = namespace['bind'](progress, 1.0)
            namespace['time'].monotonic = lambda: first
            self.assertEqual(bound(), 0.5); progress.append(0.9)
            self.assertEqual(bound(), 0.5)
        progress = []; bound = namespace['bind'](progress, 1.0)
        def publish(): progress.append(0.8); return 0.7
        namespace['time'].monotonic = publish
        self.assertEqual(bound(), 0.0)
        namespace['time'].monotonic = lambda: 0.9
        self.assertAlmostEqual(bound(), 0.1)
        namespace['time'].monotonic = lambda: 1.31
        self.assertGreaterEqual(bound(), 0.5)
        self.assertEqual(namespace['bind']([1.0], 1.0)(), 0.5)
        old_worker, new_worker = [next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'fixture_worker') for tree in trees]
        self.assertEqual(ast.dump(old_worker), ast.dump(new_worker))

    def test_readonly_workflow_inventory_and_exceptional_outcomes_are_exact(self):
        text = retirement_bytes(x.WORKFLOW, (c.ROOT / x.WORKFLOW).read_bytes()).decode()
        for fragment in ("branches: ['ci/issue88-publisher-executor-*']", 'permissions:\n  contents: read', 'timeout-minutes: 30', 'frozen two hundred sixty one cases', 'import rc_pretag_supervisor_readiness_profile as profile', 'supervisor_readiness.inventory()', 'supervisor_readiness.execution_valid(loaded, result)', 'supervisor-readiness-cases.log', 'supervisor-readiness-inventory.json', 'parents == [profile.M]', 'checked() == before', "'production_ready': False"):
            self.assertIn(fragment, text)
        for forbidden in ('secrets.', 'GH_TOKEN', 'GITHUB_TOKEN', 'contents: write', 'workflow_dispatch:', 'pull_request:', 'gh release', 'curl ', 'pip install'):
            self.assertNotIn(forbidden, text)
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
