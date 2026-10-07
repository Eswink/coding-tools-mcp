"""Exact finite source proofs; fixtures are not native or hosted build evidence."""
import ast
from collections import Counter
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
import rc_pretag_appimage_profile as a
import rc_pretag_appimage_cases as ac
import rc_pretag_linux_package_profile as l
import rc_pretag_linux_package_inverse as inverse

GROUPS = {
    'base815': (815, 'de1e5e1b5272dfe5256fcd5721dc17666d95ed0e4dfb6334888b6b0a56323610', ('appimage_tools_tests', 'cloud_release_bundle_tests', 'exact_build_audit_tests', 'exclusive_native_contract_tests', 'exclusive_native_dialog_tests', 'exclusive_native_revoke_tests', 'exclusive_release_tests', 'final_rc_evidence_tests', 'rc_consumer_archive_tests', 'rc_consumer_contract_boundaries_tests', 'rc_consumer_contract_numeric_tests', 'rc_consumer_contract_parity_tests', 'rc_consumer_contract_tests', 'rc_consumer_default_worker_proof_tests', 'rc_consumer_fence_tests', 'rc_consumer_finalization_tests', 'rc_consumer_io_ownership_tests', 'rc_consumer_io_tests', 'rc_consumer_output_tests', 'rc_consumer_plan_tests', 'rc_consumer_snapshot_tests', 'rc_consumer_source_tests', 'rc_consumer_transport_supervisor_tests', 'rc_consumer_transport_tests', 'rc_consumer_workflow_tests', 'rc_packages_tests', 'rc_pretag_admission_tests', 'rc_pretag_appimage_cases', 'rc_pretag_authenticated_two_hop_tests', 'rc_pretag_collection_tests', 'rc_pretag_composition_tests', 'rc_pretag_desktop_tests', 'rc_pretag_identity_tests', 'rc_pretag_join_once_tests', 'rc_pretag_nginx_tests', 'rc_pretag_ownership_tests', 'rc_pretag_policy_tests', 'rc_pretag_publication_contract_tests', 'rc_pretag_publication_tests', 'rc_pretag_snapshot_warning_cases', 'rc_pretag_two_hop_tests', 'rc_version_gate_tests', 'rc_windows_install_contract_tests', 'release_dependency_capture_tests', 'release_dependency_contract_tests', 'release_tag_gate_tests', 'reviewed_source_gate_tests', 'source_provenance_gate_tests', '发布版本回归v4')),
    'supplemental223': (223, '529ca42e5c16a98db012ade3cd58ab6f64a083c6e3703cfa6fa649afd0e1026e', ('AppImage入口回归v3', 'AppImage模块回归v6', 'AppImage路径回归v5', 'desktop_glib_build_evidence_tests', 'desktop_glib_deb_tests', 'desktop_glib_link_tests', 'desktop_glib_probes_tests', 'native_capture_tests', 'preliminary_package_contract_tests', 'verify_glib_backport_tests', '聊天授权原生回归v6', '跨平台原生回归v8')),
    'provenance68': (68, 'c818742b04fe5b4ca2e44c50c59379a9dc97845b3ae27127f24138fed727f468', ('linux_package_binding_tests', 'linux_package_provenance_tests', 'linux_runtime_provenance_tests', 'linux_runtime_workflow_tests')),
    'relro48': (48, '088ab05b3a7c28bedd6f0baf271b15f0d47b83d8456ddfd803ae1a1f32d3c668', ('appimage_relro_contract_tests', 'appimage_relro_guard_tests', 'appimage_relro_tool_tests')),
    'composition20': (20, '61da1f74c937f638442ec78250d5369b3bfb3692933e287769bb9e7a6a2d6adb', ('rc_pretag_linux_package_cases',)),
}
ALL_DIGEST = 'a40dee60873940221d23eca3b5e8af13e260f57bcbbbd72c7a77de72c93fa90a'


def ids(name):
    return [test.id() for test in c._flatten(unittest.defaultTestLoader.loadTestsFromName(name))]


def inventory(name):
    count, digest, modules = GROUPS[name]
    loaded = [item for module in modules for item in ids(module) if item.split('.', 1)[0] == module]
    pt.inventory_ids(loaded, count, digest)
    return loaded


def execution_valid(loaded, result):
    pt.inventory_ids(loaded, 20, l.DIGEST)
    assert Counter(loaded) == Counter(l.CLASS + '.' + name for name in l.NAMES)
    executed = getattr(result, 'executed_ids', [])
    pt.inventory_ids(executed, 20, l.DIGEST)
    return (result.wasSuccessful() and not result.skipped and not result.expectedFailures and not result.unexpectedSuccesses
            and Counter(executed) == Counter(loaded) and result.testsRun == len(set(executed)) == 20)


class LinuxPackageCompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = c._profile_fixture()
        cls.repo, _, commit, blob = cls.fixture.__enter__()
        cls.commit, cls.blob = staticmethod(commit), staticmethod(blob)
        cls._select = staticmethod(p.selected_profile)
        cls._immutable_m_cache = {}

    @classmethod
    def tearDownClass(cls):
        cls._immutable_m_cache.clear()
        cls.fixture.__exit__(None, None, None)

    def setUp(self):
        self.original = c._entries(l.M, self.repo)
        self.good = self.original | {path: (l.MODES[path], 'blob', self.blob((c.ROOT / path).read_bytes())) for path in l.CAPS}
        self.pure = self.commit([l.M], self.good)
        self.feature = self.commit([l.M, self.pure], self.good)
        self.overlay = self.good | c.RELEASE_DOCS
        self.release = self.commit([p.R, self.feature], self.overlay)
        self._baseline_args = (self.repo, c._git, c._entries, c._feature_profile, c.RELEASE, c.RELEASE_TREE, dict(c.RELEASE_DOCS))

    def verified_baseline(self, ref, root, git, entries, historical, release, release_tree, documents, **kwargs):
        arguments = (root, git, entries, historical, release, release_tree, documents)
        callbacks = all(actual is expected for actual, expected in zip(arguments[1:4], self._baseline_args[1:4]))
        if ref != l.M or kwargs or not callbacks or arguments != self._baseline_args:
            return self._select(ref, *arguments, **kwargs)
        key = (ref, root, git, entries, historical, release, release_tree, tuple(sorted(documents.items())))
        if key not in self._immutable_m_cache:
            self._immutable_m_cache[key] = dict(self._select(ref, *arguments))
        return dict(self._immutable_m_cache[key])

    def selected(self, ref, git=c._git, fresh=False):
        arguments = (self.repo, git, c._entries, c._feature_profile, c.RELEASE, c.RELEASE_TREE, c.RELEASE_DOCS)
        if fresh:
            return self._select(ref, *arguments)
        with patch.object(p, 'selected_profile', side_effect=self.verified_baseline):
            return self._select(ref, *arguments)

    def content(self, ref=None, git=c._git):
        with patch.object(p, 'selected_profile', side_effect=self.verified_baseline):
            return l.content(ref or self.pure, self.repo, git, c._entries, c._feature_profile, c.RELEASE, c.RELEASE_TREE, c.RELEASE_DOCS)

    def frozen(self, path):
        return c._git('show', l.M + ':' + path, root=self.repo)

    def changed(self, path, data):
        return self.good | {path: (l.MODES.get(path, '100644'), 'blob', self.blob(data))}

    def bad_content(self, entries, parents=None):
        ref = self.commit([l.M] if parents is None else parents, entries)
        l.topology(ref, self.repo, c._git, p.R)
        with self.assertRaises(AssertionError):
            self.selected(ref)  # Changed candidate content is never cached.

    def rejects(self, parents):
        ref = self.commit(parents, self.good)
        with self.assertRaises(o.TopologyError):
            l.topology(ref, self.repo, c._git, p.R)
        with patch.object(l, 'content') as content, self.assertRaises(o.TopologyError):
            self.selected(ref)
        content.assert_not_called()

    def test_exact_m_anchor_tree_parents_and_fresh_history(self):
        self.assertEqual((l.M, l.M_TREE, l.M_PARENTS), ('fd7b303839aa648d33456f7aaeec6388bfb696c4',
            'e4ab19e2fe4bfbb1fef9e0cd713a6fbb18d03995', ('feeaf299df6c3729285c91511ece18e9984a2503', '23be745924cc85da84901da8cdd4a65db1673734')))
        self.assertEqual(self.selected(l.M, fresh=True), self.original)
        with patch.object(a, 'content', wraps=a.content) as historical:
            self.assertEqual(self.selected(self.pure, fresh=True), self.good)
            self.assertEqual(self.selected(self.pure, fresh=True), self.good)
            self.assertEqual(historical.call_count, 2)
        with patch.object(a, 'content', side_effect=AssertionError('fresh history')), self.assertRaisesRegex(AssertionError, 'fresh history'):
            self.selected(self.pure, fresh=True)
        for command, replacement in ((('show', '-s', '--format=%P', l.M), b'\n'),
                                      (('rev-parse', l.M + '^{tree}'), b'0' * 40 + b'\n')):
            def altered(*args, root):
                return replacement if args == command else c._git(*args, root=root)
            with self.assertRaises((AssertionError, o.TopologyError)):
                self.selected(self.pure, altered, fresh=True)

    def test_candidate_has_exact_finite_source_paths_and_pins(self):
        self.assertEqual(self.selected(self.pure), self.good)
        self.assertEqual((len(self.original), len(self.good), len(l.CAPS)), (1705, 1726, 37))
        self.assertEqual({path for path in self.good if self.good[path] != self.original.get(path)}, l.CAPS.keys())
        self.assertEqual(l.SOURCE_PINS.keys(), l.CAPS.keys() - {l.PROFILE})
        self.assertEqual((len(l.CAPS.keys() - self.original.keys()), len(inverse.BASE_PINS)), (21, 16))
        for path, row in l.SOURCE_PINS.items():
            data = (c.ROOT / path).read_bytes()
            self.assertEqual(row, (l.MODES[path], *o.pin(data), len(data), len(data.splitlines())))
            self.assertEqual(bool((c.ROOT / path).stat().st_mode & 0o111), row[0] == '100755', path)
        self.assertEqual(l.MODES['scripts/appimage_relro_guard.py'], '100755')
        self.assertEqual(l.MODES['scripts/desktop_glib_build_evidence.py'], '100755')

    def test_ordered_merge_requires_complete_identical_candidate_tree(self):
        self.assertEqual(self.selected(self.feature), self.good)
        self.assertEqual(l.topology(self.feature, self.repo, c._git, p.R), ('nonrelease', self.feature, self.pure))
        for entries in (self.original, self.changed(l.CASES, b'changed\n'), self.overlay):
            self.bad_content(entries, [l.M, self.pure])

    def test_release_overlay_has_only_four_exact_r_documents(self):
        self.assertEqual(self.selected(self.release), self.overlay)
        self.assertEqual((len(c.RELEASE_DOCS), p.R_DOCUMENTS), (4, c.RELEASE_DOCS))
        self.assertEqual((p.R, p.R_TREE), ('e2e011f7f2a3a1df838bbd588106205b999db610', 'c0dfe00fdcc7ebc8e26acaad5d18ff3f94df9ba3'))
        for path in c.RELEASE_DOCS:
            for entries in (self.overlay | {path: self.good[path]}, {k: v for k, v in self.overlay.items() if k != path},
                            self.overlay | {path: ('100755', *self.overlay[path][1:])}):
                self.bad_content(entries, [p.R, self.feature])
        self.bad_content(self.overlay | {'extra.md': ('100644', 'blob', self.blob(b'extra'))}, [p.R, self.feature])

    def test_missing_extra_reversed_duplicate_nested_parents_reject(self):
        for parents in ([], [self.pure], [self.pure, l.M], [l.M, self.pure, p.R], [l.M, l.M], [l.M, self.feature],
                        [p.R], [p.R, self.pure], [self.feature, p.R], [p.R, self.feature, self.pure], [p.R, self.release]):
            with self.subTest(parents=parents):
                self.rejects(parents)

    def test_unknown_same_tree_anchor_and_correction_ancestry_reject(self):
        impostor = self.commit([], self.original)
        correction = self.commit([self.pure], self.good)
        for parents in ([impostor], [impostor, self.pure], [correction], [l.M, correction], [a.M, self.pure]):
            self.rejects(parents)
        with self.assertRaises(o.TopologyError):
            l.topology(self.pure, self.repo, c._git, impostor)
        self.assertIsNone(l.select(l.M, *self._baseline_args))

    def test_every_source_mode_blob_digest_size_and_line_pin_rejects_drift(self):
        for path, row in l.SOURCE_PINS.items():
            for index, value in enumerate(('100755' if row[0] == '100644' else '100644', '0' * 40, '0' * 64, row[3] + 1, row[4] + 1)):
                changed = list(row); changed[index] = value
                with self.subTest(path=path, field=index), patch.dict(l.SOURCE_PINS, {path: tuple(changed)}), self.assertRaises(AssertionError):
                    self.content()
            self.bad_content(self.changed(path, (c.ROOT / path).read_bytes() + b'\n'))
        for pins in ({k: v for k, v in l.SOURCE_PINS.items() if k != l.CASES}, l.SOURCE_PINS | {'extra': row}):
            with patch.dict(l.SOURCE_PINS, pins, clear=True), self.assertRaises(AssertionError):
                self.content()
        for path in l.CAPS:
            missing = {key: value for key, value in self.good.items() if key != path}
            self.bad_content(missing)
            self.bad_content(missing | {path + '.renamed': self.good[path]})
            mode = '100755' if l.MODES[path] == '100644' else '100644'
            self.bad_content(self.good | {path: (mode, *self.good[path][1:])})
            self.bad_content(self.good | {path: ('120000', 'blob', self.blob(b'target'))})
            self.bad_content(self.good | {path: ('160000', 'commit', l.M)})
            self.bad_content(self.changed(path, b'\0binary\xff'))
        self.bad_content(self.changed('unreviewed-extra.py', b'extra\n'))

    def test_individual_and_aggregate_budgets_reject(self):
        self.assertEqual((l.DELTA_LIMIT, sum(cap[1] for cap in l.CAPS.values())), (8500, 9161))
        data = {path: (c.ROOT / path).read_bytes() for path in l.CAPS}
        def budgets(git=c._git):
            return p.authenticated._budgets(self.pure, l.M, self.repo, git, data, l.CAPS, l.DELTA_LIMIT, 'linux_package_delta_budget')
        budgets()
        for path, (_, delta) in l.CAPS.items():
            lines = len((c.ROOT / path).read_bytes().splitlines())
            with patch.dict(l.CAPS, {path: (lines - 1, delta)}), self.assertRaises(AssertionError):
                budgets()
            def oversized(*args, root):
                return f'{delta + 1}\t0\t{path}\n'.encode() if args == ('diff', '--numstat', l.M, self.pure, '--', path) else c._git(*args, root=root)
            with self.assertRaises(AssertionError):
                budgets(oversized)
        def aggregate(*args, root):
            if args[:5] == ('diff', '--numstat', l.M, self.pure, '--'):
                return f'{l.CAPS[args[5]][1]}\t0\t{args[5]}\n'.encode()
            return c._git(*args, root=root)
        with self.assertRaisesRegex(AssertionError, 'linux_package_delta_budget'):
            budgets(aggregate)
        for row in (b'', b'-\t-\t' + path.encode(), b'1\t0', b'1\t0\twrong', b'1\t0\t' + path.encode() + b'\nextra'):
            def malformed(*args, root):
                return row if args == ('diff', '--numstat', l.M, self.pure, '--', path) else c._git(*args, root=root)
            with self.assertRaises(AssertionError):
                budgets(malformed)

        with patch.object(p.authenticated, '_budgets', side_effect=AssertionError('budget terminal')), self.assertRaisesRegex(AssertionError, 'budget terminal'):
            self.content()

    def test_all_current_inverses_recover_complete_m_bytes(self):
        self.assertEqual(inverse.BASE_PINS.keys(), inverse.CURRENT_PINS.keys())
        self.assertEqual(inverse.BASE_PINS.keys(), inverse.FRAGMENTS.keys())
        for path in inverse.BASE_PINS:
            current, frozen = (c.ROOT / path).read_bytes(), self.frozen(path)
            with patch('builtins.open', side_effect=AssertionError('IO forbidden')), patch('subprocess.check_output', side_effect=AssertionError('git forbidden')):
                self.assertEqual(inverse.inverse(path, current), frozen, path)
            self.assertEqual(inverse.inverse(path, frozen), frozen, path)
            self.assertEqual(o.pin(frozen), inverse.BASE_PINS[path])
            self.assertEqual(o.pin(current), inverse.CURRENT_PINS[path])
        for path in a.BASE_PINS:
            frozen = c._git('show', a.M + ':' + path, root=self.repo)
            self.assertEqual(a.inverse_appimage_adapter(path, (c.ROOT / path).read_bytes()), frozen)
        self.assertEqual((c.ROOT / p.JOIN_ONCE_HELPER).read_bytes(), self.frozen(p.JOIN_ONCE_HELPER))

    def test_inverse_fragments_and_historical_passthrough_pins_are_exact(self):
        self.assertEqual(inverse.PRIOR_PINS.keys(), {p.PROFILE})
        self.assertEqual(inverse.PRIOR_PINS[p.PROFILE], (a.BASE_PINS[p.PROFILE],))
        prior = c._git('show', a.M + ':' + p.PROFILE, root=self.repo)
        self.assertEqual(inverse.inverse(p.PROFILE, prior), prior)
        for path, fragments in inverse.FRAGMENTS.items():
            current = (c.ROOT / path).read_bytes()
            for before, _ in fragments:
                self.assertEqual(current.count(before), 1)
                for replacement in (b'', before * 2):
                    changed = current.replace(before, replacement, 1)
                    if o.pin(changed) == inverse.BASE_PINS[path]:
                        self.assertEqual(inverse.inverse(path, changed), self.frozen(path))
                        changed += b'# outside exact M\n'
                    with self.assertRaises(AssertionError):
                        inverse.inverse(path, changed)
            for changed in (current + b'# outside\n', current.replace(b'assert ', b'# assert ', 1) + b'\n', b'\xff'):
                with self.assertRaises(AssertionError):
                    inverse.inverse(path, changed)
        with self.assertRaises(AssertionError):
            inverse.inverse(p.PROFILE, prior + b'\n')
        with self.assertRaises(AssertionError):
            inverse.inverse('unknown', b'unchanged')
        self.assertEqual(a.inverse_appimage_adapter('unknown', b'unchanged'), b'unchanged')

    def test_original_815_assertions_and_ids_are_preserved(self):
        old = inventory('base815')
        class SourceReadNormalization(ast.NodeTransformer):
            def visit_Call(self, node):
                node = self.generic_visit(node)
                return node.args[1] if isinstance(node.func, ast.Name) and node.func.id == 'normalize' and len(node.args) == 2 else node
        self.assertEqual(set(old), set(ac.old_inventory() + ac.ids(ac.HELPER_CLASS) + ac.ids(a.CLASS)))
        for module in {name.split('.', 1)[0] for name in old}:
            path = 'scripts/' + module + '.py'
            current, frozen = (c.ROOT / path).read_bytes(), self.frozen(path)
            self.assertEqual(inverse.normalize(path, current), frozen, path)
            methods = lambda data: {node.name: node for node in ast.walk(ast.parse(data)) if isinstance(node, ast.FunctionDef)}
            before, after = methods(frozen), methods(current)
            self.assertEqual(before.keys(), after.keys(), path)
            assertions = lambda node: Counter(ast.dump(call) for call in ast.walk(node) if isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute) and call.func.attr.startswith('assert'))
            for name in before:
                self.assertEqual(assertions(before[name]), assertions(SourceReadNormalization().visit(after[name])), path + ':' + name)
        for path in ('scripts/rc_pretag_ownership_profile.py', 'scripts/rc_pretag_desktop_profile.py',
                     'scripts/rc_pretag_nginx_profile.py', 'scripts/rc_pretag_two_hop_profile.py', p.authenticated.PROFILE):
            self.assertEqual((c.ROOT / path).read_bytes(), self.frozen(path), path)
        self.assertEqual(p.PROFILE_ID, 'engineering/issue88-publication-core-composition-v1')

    def test_mandatory_supplemental_and_new_inventory_are_disjoint(self):
        groups = {name: inventory(name) for name in GROUPS}
        all_ids = [item for group in groups.values() for item in group]
        pt.inventory_ids(all_ids, 1174, ALL_DIGEST)
        self.assertEqual(tuple(map(len, groups.values())), (815, 223, 68, 48, 20))
        self.assertFalse(Path(l.CASES).match('rc_pretag*_tests.py'))
        self.assertEqual(Counter(groups['composition20']), Counter(l.CLASS + '.' + name for name in l.NAMES))

    def test_loaded_executed_inventory_rejects_skips_and_duplicates(self):
        loaded = ids(l.CLASS)
        good = dict(executed_ids=loaded, testsRun=20, skipped=[], expectedFailures=[], unexpectedSuccesses=[], wasSuccessful=lambda: True)
        self.assertTrue(execution_valid(loaded, SimpleNamespace(**good)))
        for field, value in (('skipped', [('id', 'reason')]), ('expectedFailures', [('id', 'failure')]),
                             ('unexpectedSuccesses', ['id']), ('testsRun', 19), ('wasSuccessful', lambda: False)):
            self.assertFalse(execution_valid(loaded, SimpleNamespace(**(good | {field: value}))))
        for invalid in (loaded[:-1], loaded + loaded[:1], loaded[:-1] + ['unknown']):
            with self.assertRaises(AssertionError):
                execution_valid(invalid, SimpleNamespace(**good))
            with self.assertRaises(AssertionError):
                execution_valid(loaded, SimpleNamespace(**(good | {'executed_ids': invalid})))

    def test_scoped_tool_pins_and_nine_protected_destinations_are_exact(self):
        protected = {'usr/bin/coding-tools-mcp-desktop', 'usr/lib/libglib-2.0.so.0', 'usr/lib/libgmodule-2.0.so.0'}
        protected |= {'usr/lib/lib' + family + '-2.0.so' + suffix for family in ('gio', 'gobject') for suffix in ('', '.0', '.0.7200.4')}
        self.assertEqual(len(protected), 9)
        import appimage_relro_contract as relro
        self.assertEqual(set(relro.PROTECTED), protected)
        self.assertEqual((relro.OUTER_SIZE, relro.OUTER_OFFSET, relro.OUTER_SHA256),
            (13264064, 193728, 'e762bea85c8eb0d4b3508d46e5c1f037f717d0f9303ae3b4aafc8b04991fa1ef'))
        self.assertEqual((relro.TOOL_SIZE, relro.TOOL_SHA256),
            (1029016, 'c15c1282d9dadcaaf5e492c0ee5f929d34453f8af759cc4aadad03b5b65df879'))
        self.assertEqual(relro.FAMILIES, {
            'glib': (1281808, '86acf2c843bcfaf5e8c24ab959737960c797da53b41658dc8ec6f257c786048c'),
            'gio': (1932688, 'b63a477916c1f95de4b2c80bb4f5940a59ebc5860793d93b271448e90edbfe52'),
            'gobject': (387464, '05a94d6be0a50dba15a579f3ad1f5c6ec12c8d303f3b715a665fd27824ca523e'),
            'gmodule': (22736, '1019fc28ced6829f22b446a091ecb5b76b9fa3b3c458bc6ea936c1d328302cb5')})
        for path, row in relro.PROTECTED.items():
            self.assertEqual(row['mode'], 0o755 if path == relro.MAIN else 0o644)
            self.assertEqual(row['rpath'], '$ORIGIN/../lib' if path == relro.MAIN else '$ORIGIN')
        self.assertEqual((c.ROOT / a.HELPER).read_bytes(), self.frozen(a.HELPER))
        self.assertEqual((c.ROOT / 'scripts/desktop_glib_deb.py').read_bytes(), self.frozen('scripts/desktop_glib_deb.py'))

    def test_collector_single_build_and_original_profile_are_preserved(self):
        path = 'scripts/desktop_glib_build_evidence.py'
        current, frozen = (c.ROOT / path).read_bytes(), self.frozen(path)
        functions = lambda data: {node.name: ast.dump(node) for node in ast.parse(data).body if isinstance(node, ast.FunctionDef)}
        before, after = functions(frozen), functions(current)
        for name in ('build_environment', 'child_environment', 'tool_identities', 'collect'):
            self.assertEqual(before[name], after[name], name)
        self.assertEqual(inverse.inverse(path, current), frozen)
        workflow = (c.ROOT / l.WORKFLOW).read_text()
        self.assertEqual(workflow.count(' collect-linux '), 1)
        self.assertNotIn('npm run tauri -- build', workflow)
        self.assertIn('verify-linux', workflow)
        self.assertEqual((c.ROOT / 'scripts/desktop_glib_link.py').read_bytes(), self.frozen('scripts/desktop_glib_link.py'))

    def test_workflow_preserves_four_installed_jobs_and_failure_gates(self):
        current = (c.ROOT / l.WORKFLOW).read_text()
        frozen = self.frozen(l.WORKFLOW).decode()
        self.assertEqual(inverse.inverse(l.WORKFLOW, current.encode()), frozen.encode())
        for token in ('os: [ubuntu-22.04, ubuntu-24.04]', 'kind: [deb, appimage]', 'fail-fast: false',
                      "if: always() && steps.prerequisites.outcome == 'success'", 'cargo test --no-fail-fast',
                      "if: always() && needs.build.outputs.packages_ready == 'true'", 'contents: read', 'persist-credentials: false'):
            self.assertEqual(current.count(token), frozen.count(token), token)
        self.assertIn('rc_pretag_linux_package_cases.py', current)
        self.assertLess(current.index('id: prerequisites'), current.index('id: regression'))
        self.assertLess(current.index('Launch exact installed bytes'), current.index('Install WebDriver only'))
        self.assertLess(current.index('Install WebDriver only'), current.index('Installed native OAuth'))

    def test_windows_held_runtime_versions_and_release_gates_are_unchanged(self):
        self.assertTrue(all(self.good[path] == value for path, value in self.original.items() if path not in l.CAPS))
        held = {'docs/specs/rc-source-assembly-engineering/' + name for name in ('README.md', 'design.md', 'requirements.md',
                'tasks.md', 'subspecs/focused-validation/spec.md', 'subspecs/source-evidence/spec.md')}
        held |= {'scripts/rc_source_assembly.py', 'scripts/rc_source_assembly_dispatch_tests.py',
                 'scripts/rc_source_assembly_tests.py', 'tests/delivery/test_linux_lifecycle_wiring.py'}
        self.assertEqual(len(held), 10)
        self.assertFalse(held & self.good.keys())
        for path in held:
            self.assertFalse((c.ROOT / path).exists() or (c.ROOT / path).is_symlink(), path)
        for path in ('package.json', 'package-lock.json', 'src-tauri/Cargo.toml', 'src-tauri/Cargo.lock', 'src-tauri/tauri.conf.json',
                     p.CHECKS, p.CONTRACTS, '.github/workflows/rc-pretag-evidence.yml', '.github/workflows/final-rc-packages.yml',
                     'scripts/rc_release_policy.py', 'scripts/rc_release_eligibility.py', 'scripts/AppImage启动入口v3.sh',
                     'services/local-agent/src/process.rs', 'src-tauri/src/workspace_snapshots/filesystem.rs',
                     '.github/workflows/windows-snapshot-warning-scope.yml', '.github/workflows/desktop-glib-backport.yml'):
            if path in self.original:
                self.assertEqual((c.ROOT / path).read_bytes(), self.frozen(path), path)

    def test_selected_content_failure_is_terminal_without_fallback(self):
        for error in (AssertionError, o.TopologyError):
            with patch.object(l, 'content', side_effect=error('terminal Linux package')), patch.object(a, 'content') as old, \
                 self.assertRaisesRegex(error, 'terminal Linux package'):
                self.selected(self.pure)
            old.assert_not_called()
            with patch.object(a, 'content', side_effect=error('terminal historical')), patch.object(l, 'content') as new, \
                 self.assertRaisesRegex(error, 'terminal historical'):
                self.selected(l.M, fresh=True)
            new.assert_not_called()
            with patch.object(l, 'content', return_value=self.good), patch.object(o, 'release_content', side_effect=error('terminal release')), \
                 patch.object(a, 'content') as old, self.assertRaisesRegex(error, 'terminal release'):
                self.selected(self.release)
            old.assert_not_called()

    def test_mutable_refs_and_ambient_git_do_not_change_identity(self):
        calls = []
        def moving(*args, root):
            calls.append(args)
            if args == ('rev-parse', '--verify', 'moving^{commit}'):
                return ((self.pure if calls.count(args) == 1 else self.release) + '\n').encode()
            return c._git(*args, root=root)
        hostile = {name: '/nonexistent' for name in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR',
                   'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES')}
        with patch.dict(os.environ, hostile):
            self.assertEqual(self.selected('moving', moving), self.good)
        self.assertEqual(sum(any('moving' in arg for arg in args) for args in calls), 1)

    def test_only_test_fixture_baseline_cache_is_permitted(self):
        baseline = self.verified_baseline(l.M, *self._baseline_args)
        baseline.clear()
        self.assertEqual(self.verified_baseline(l.M, *self._baseline_args), self.original)
        with patch.object(self, '_select', side_effect=AssertionError('delegated')):
            variants = [(self.pure, {}, {}), (l.M, {0: Path('/other-root')}, {}), (l.M, {1: lambda *a, **k: None}, {}),
                        (l.M, {2: lambda *a, **k: None}, {}), (l.M, {3: lambda *a, **k: None}, {}),
                        (l.M, {4: 'other'}, {}), (l.M, {5: 'other'}, {}), (l.M, {6: {}}, {}), (l.M, {}, {'profile': p.PROFILE_ID})]
            for ref, replacements, kwargs in variants:
                arguments = list(self._baseline_args)
                for index, value in replacements.items():
                    arguments[index] = value
                with self.assertRaisesRegex(AssertionError, 'delegated'):
                    self.verified_baseline(ref, *arguments, **kwargs)
        for module in (l, inverse):
            source = (c.ROOT / 'scripts' / (module.__name__ + '.py')).read_text()
            self.assertNotIn('lru_cache', source)
            self.assertNotIn('_immutable_m_cache', source)
        changed = self.changed(l.CASES, (c.ROOT / l.CASES).read_bytes() + b'# changed\n')
        with patch.object(l, 'content', wraps=l.content) as fresh:
            self.bad_content(changed)
            self.bad_content(changed)
            self.assertEqual(fresh.call_count, 2)


def main():
    suite = unittest.defaultTestLoader.loadTestsFromName(l.CLASS)
    loaded = [test.id() for test in c._flatten(suite)]
    pt.inventory_ids(loaded, 20, l.DIGEST)
    assert Counter(loaded) == Counter(l.CLASS + '.' + name for name in l.NAMES)
    result = unittest.TextTestRunner(verbosity=2, resultclass=c.InventoryResult).run(suite)
    print(json.dumps(dict(loaded_ids=loaded, executed_ids=getattr(result, 'executed_ids', []), loaded=len(loaded), executed=result.testsRun)))
    return 0 if execution_valid(loaded, result) else 1


if __name__ == '__main__':
    raise SystemExit(main())
