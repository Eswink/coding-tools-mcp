"""Closed Issue40 engineering composition; synthetic trees confer no native authority."""
import ast
from collections import Counter
from contextlib import ExitStack
import json
import os
import unittest
from unittest.mock import patch

import rc_pretag_composition_tests as c
import rc_pretag_desktop_profile as d
import rc_pretag_desktop_tests as dt
import rc_pretag_nginx_profile as n
import rc_pretag_ownership_profile as o


class NginxCompositionTests(unittest.TestCase):
    def setUp(self):
        self.repo, _, self.commit, self.blob = self.enterContext(c._profile_fixture())
        self.source = c._entries(n.P, self.repo)
        self.good = self.source | {p: ('100644', 'blob', self.blob((c.ROOT / p).read_bytes()))
                                   for p in n.AMENDMENT_CAPS}
        self.pure = self.commit([n.P], self.good)
        self.feature = self.commit([n.F, self.pure], self.good)
        self.overlay = self.good | c.RELEASE_DOCS
        self.release = self.commit([n.R, self.feature], self.overlay)

    def selected(self, ref, git=c._git, **kwargs):
        return n.selected_profile(ref, self.repo, git, c._entries, c._feature_profile,
                                  c.RELEASE, c.RELEASE_TREE, c.RELEASE_DOCS, **kwargs)

    def nginx(self, ref, git=c._git):
        return n.nginx_content(ref, self.repo, git, c._entries, c._feature_profile,
                               c.RELEASE, c.RELEASE_TREE, c.RELEASE_DOCS)

    def amended(self, ref, entries=c._entries, git=c._git):
        return n.amendment_content(ref, self.source, self.repo, git, entries)

    def changed(self, path, data, mode='100644', base=None):
        return (self.good if base is None else base) | {path: (mode, 'blob', self.blob(data))}

    def rejects(self, parents, expected):
        ref = self.commit(parents, expected)
        self.assertEqual(c._entries(ref, self.repo), expected)
        self.assertEqual(self.nginx(n.P), self.source)
        if expected == self.source:
            self.assertEqual(self.nginx(ref), expected)
        elif expected == self.good:
            self.assertEqual(self.amended(ref), expected)
        else:
            self.assertEqual(expected, self.overlay)
            self.assertEqual(self.amended(self.pure), self.good)
            self.assertEqual(o.release_content(ref, self.good, self.repo, c._git, c._entries,
                                              n.R, n.R_TREE, n.R_DOCUMENTS), expected)
        with self.assertRaises(o.TopologyError):
            n.nginx_topology(ref, self.repo, c._git, n.R)
        with ExitStack() as stack:
            stopped = [stack.enter_context(patch.object(module, name, side_effect=AssertionError('content ran')))
                       for module, name in ((o, 'content'), (o, 'release_content'), (d, 'desktop_content'),
                           (d, 'amendment_content'), (n, 'nginx_content'), (n, 'amendment_content'))]
            with self.assertRaises(o.TopologyError):
                self.selected(ref)
            for action in stopped:
                action.assert_not_called()

    def bad_content(self, entries, parents=None):
        ref = self.commit([n.P] if parents is None else parents, entries)
        n.nginx_topology(ref, self.repo, c._git, n.R)
        with self.assertRaises(AssertionError) as failure:
            self.selected(ref)
        self.assertNotIsInstance(failure.exception, o.TopologyError)

    def test_exact_historical_profiles_and_pins_remain_unchanged(self):
        for path in (d.PROFILE, 'scripts/rc_pretag_ownership_profile.py', 'scripts/rc_pretag_ownership_tests.py'):
            self.assertEqual((c.ROOT / path).read_bytes(), c._git('show', n.F + ':' + path, root=self.repo))
        self.assertEqual((len(c.ALLOWED), len(o.CAPS), o.DELTA_LIMIT, d.AMENDMENT_DELTA_LIMIT), (22, 13, 2200, 1100))
        self.assertEqual(d.AMENDMENT_PINS[d.COMPOSITION], ('988c4be1175b68feecc2c38f8aee7f932e4589e2',
                         'ff5e95e6ff14416aa969e1c9dad9e729c96c3aa624da63af4ff93c9edc397694'))
        self.assertEqual(d.AMENDMENT_PINS[d.TESTS], ('f1af6905e3b915b1e1dbb3c9c0493d1e16304cd7',
                         'd200e4a971c6a94addd28da5d6331968236c8487ef017421a2b85a649b4d94ce'))
        for ref in (d.X, d.SOURCE, n.F):
            expected = d.selected_profile(ref, self.repo, c._git, c._entries, c._feature_profile,
                                          c.RELEASE, c.RELEASE_TREE, c.RELEASE_DOCS)
            self.assertEqual(self.selected(ref), expected)

    def test_exact_f_anchor_parent_tree_and_legacy_validation(self):
        self.assertEqual((n.F, n.F_TREE, n.F_PARENTS), ('310ad16c8aa9cc8182c4b0f6a196184fcf34bc52',
            '66b0dde07e5dd83883e3978886b61a82badafcd6',
            ('44ff88373d76b54a22d72eba17c0c7989e0be805', 'afca8585ebb231d247080b184f47ceb2012accac')))
        self.assertEqual(tuple(o._parents(n.F, self.repo, c._git)), n.F_PARENTS)
        self.assertEqual(c._git('rev-parse', n.F + '^{tree}', root=self.repo).decode().strip(), n.F_TREE)
        with patch.object(d, 'selected_profile', wraps=d.selected_profile) as legacy:
            self.assertEqual(self.nginx(n.P), self.source)
            self.assertEqual(legacy.call_args.args[0], n.F)
            self.assertIs(legacy.call_args.args[4], c._feature_profile)
        for anchor in (n.F, n.P):
            def wrong_parents(*args, root):
                if args == ('show', '-s', '--format=%P', anchor): return b'\n'
                return c._git(*args, root=root)
            with patch.object(n, 'nginx_content') as content, self.assertRaises(o.TopologyError):
                self.selected(self.pure, wrong_parents)
            content.assert_not_called()
        for anchor in (n.F, n.P):
            def wrong_tree(*args, root):
                if args == ('rev-parse', anchor + '^{tree}'): return b'0' * 40 + b'\n'
                return c._git(*args, root=root)
            with self.assertRaises(AssertionError): self.nginx(n.P, wrong_tree)

    def test_p_source_has_only_nine_exact_additions(self):
        self.assertEqual((n.P, n.P_TREE), ('cf3e59b4b411b7a92bb7d6ef8783c2720fb2fb1d',
                                         'fcdaef969403255b9ba6221437ea0916ac348677'))
        self.assertEqual(o._parents(n.P, self.repo, c._git), [n.F])
        self.assertEqual(c._git('rev-parse', n.P + '^{tree}', root=self.repo).decode().strip(), n.P_TREE)
        original = c._entries(n.F, self.repo)
        self.assertEqual((len(original), len(self.source), len(n.SOURCE_PINS)), (1650, 1659, 9))
        self.assertEqual(self.source.keys() - original.keys(), n.SOURCE_PINS.keys())
        self.assertTrue(all(self.source[p] == value for p, value in original.items()))
        self.assertEqual(self.nginx(n.P), self.source)
        for path, (mode, blob, digest, size, lines) in n.SOURCE_PINS.items():
            data = c._git('show', n.P + ':' + path, root=self.repo)
            self.assertEqual((mode, blob, digest, size, lines),
                             ('100644', *o.pin(data), len(data), len(data.splitlines())))
            self.assertEqual((c.ROOT / path).read_bytes(), data)

    def test_exact_p_and_single_reviewed_amendment_accept(self):
        self.assertEqual(self.selected(n.P), self.source)
        self.assertEqual(self.selected(self.pure), self.good)
        self.assertEqual(len(self.good), 1664)
        self.assertEqual({p for p in self.good if self.good[p] != self.source.get(p)}, n.AMENDMENT_CAPS.keys())
        self.assertEqual(n.AMENDMENT_PINS.keys(), n.AMENDMENT_CAPS.keys() - {n.PROFILE})
        with self.assertRaises(o.TopologyError):
            d.selected_profile(n.P, self.repo, c._git, c._entries, c._feature_profile,
                               c.RELEASE, c.RELEASE_TREE, c.RELEASE_DOCS)
        self.bad_content(self.source)

    def test_exact_ordered_feature_merge_equals_source_tree(self):
        for source, expected in ((n.P, self.source), (self.pure, self.good)):
            feature = self.commit([n.F, source], expected)
            self.assertEqual(self.selected(feature), expected)
            self.assertEqual(o._parents(feature, self.repo, c._git), [n.F, source])
            self.assertEqual(c._git('rev-parse', feature + '^{tree}', root=self.repo),
                             c._git('rev-parse', source + '^{tree}', root=self.repo))
        self.bad_content(self.source, [n.F, self.pure])
        self.bad_content(self.good, [n.F, n.P])
        self.bad_content(self.changed('scripts/rc_consumer_io.py', b'merge resolution\n'), [n.F, self.pure])

    def test_exact_release_overlay_contains_only_four_pinned_documents(self):
        self.assertEqual((n.R, n.R_TREE, n.R_DOCUMENTS), (c.RELEASE, c.RELEASE_TREE, c.RELEASE_DOCS))
        self.assertEqual(len(n.R_DOCUMENTS), 4)
        self.assertEqual(self.selected(self.release), self.overlay)
        self.assertEqual({p for p in self.overlay if self.overlay[p] != self.good[p]}, n.R_DOCUMENTS.keys())
        feature = self.commit([n.F, n.P], self.source)
        self.assertEqual(self.selected(self.commit([n.R, feature], self.source | n.R_DOCUMENTS)),
                         self.source | n.R_DOCUMENTS)

    def test_missing_unknown_and_same_tree_impostor_anchors_reject(self):
        fake_f = self.commit([], c._entries(n.F, self.repo))
        fake_p = self.commit([], self.source)
        fake_r = self.commit([], c._entries(n.R, self.repo))
        foreign = self.commit([], self.good)
        for parents in ([], [foreign], [fake_p], [fake_f, self.pure], ['f' * 40]):
            with self.subTest(parents=parents): self.rejects(parents, self.good)
        self.rejects([], self.source)
        self.rejects([n.F], self.source)
        self.rejects([fake_r, self.feature], self.overlay)
        with patch.object(n, 'nginx_content') as content, self.assertRaises(o.TopologyError):
            self.selected('f' * 40)
        content.assert_not_called()

    def test_reversed_duplicate_missing_and_extra_parents_reject_before_content(self):
        for parents in ([n.F], [n.P, n.F], [self.pure, n.F], [n.F, n.F], [n.P, n.P],
                        [n.F, self.pure, n.P], [n.F, self.pure, self.pure]):
            with self.subTest(parents=parents): self.rejects(parents, self.good)
        for parents in ([self.feature, n.R], [n.R, self.feature, n.P], [n.R, n.R], [n.R, self.pure]):
            with self.subTest(parents=parents): self.rejects(parents, self.overlay)

    def test_amendment_chains_nested_merges_and_postmerge_descendants_reject(self):
        for parents in ([self.pure], [self.feature], [n.F, self.feature], [n.F, self.release], [n.P, self.pure]):
            self.rejects(parents, self.good)
        for parents in ([n.R, self.release], [self.release], [n.R, n.P]):
            self.rejects(parents, self.overlay)

    def test_each_nine_source_blob_and_sha256_mutation_rejects(self):
        for path, row in n.SOURCE_PINS.items():
            data = c._git('show', n.P + ':' + path, root=self.repo)
            for changed in (data + b'\n', b'\0binary\xff\n'):
                with self.subTest(path=path, binary=changed.startswith(b'\0')):
                    self.bad_content(self.changed(path, changed))
            for index, value in ((1, self.blob(b'changed source\n')), (2, '0' * 64), (3, row[3] + 1), (4, row[4] + 1)):
                altered = list(row); altered[index] = value
                with self.subTest(path=path, field=index), patch.object(n, 'SOURCE_PINS', n.SOURCE_PINS | {path: tuple(altered)}):
                    with self.assertRaises(AssertionError): self.nginx(n.P)

    def test_missing_extra_renamed_mode_symlink_and_gitlink_entries_reject(self):
        self.assertEqual([p for p, value in self.good.items() if value[0] == '100755'], [d.COLLECTOR])
        for path in (*n.SOURCE_PINS, *n.AMENDMENT_CAPS):
            missing = dict(self.good); missing.pop(path)
            mutations = [missing, missing | {path + '.renamed': self.good[path]}]
            mutations += [self.good | {path: value} for value in
                          (('100755', *self.good[path][1:]), ('120000', 'blob', self.blob(b'target')),
                           ('160000', 'commit', n.P))]
            for changed in mutations:
                with self.subTest(path=path, entry=changed.get(path)): self.bad_content(changed)
        for path in ('unreviewed-extra.py', 'native-evidence.json', *(f'docs/specs/issue40-nginx-composition/{name}.md'
                     for name in ('sixth', 'seventh', 'eighth'))):
            self.bad_content(self.good | {path: ('100644', 'blob', self.blob(b'unreviewed\n'))})

    def test_each_historical_protected_entry_and_version_slot_remains_exact(self):
        n.nginx_topology(self.pure, self.repo, c._git, n.R)
        self.assertEqual(self.amended(self.pure), self.good)
        original = c._entries(n.F, self.repo)
        bad = self.blob(b'changed protected historical entry\n')
        for path in original.keys() - {n.COMPOSITION, n.DESKTOP_TESTS}:
            mode = '100644' if original[path][0] == '100755' else '100755'
            for value in (('100644', 'blob', bad), (mode, *original[path][1:])):
                changed = self.good | {path: value}
                with self.subTest(path=path, mode=value[0]), self.assertRaises(AssertionError):
                    self.amended(self.pure, entries=lambda ref, root: changed)
        for path, keys in (('package.json', ('version',)), ('package-lock.json', ('version',)),
                           ('package-lock.json', ('packages', '', 'version')), ('src-tauri/tauri.conf.json', ('version',))):
            data = json.loads(c._git('show', n.F + ':' + path, root=self.repo))
            field = data
            for key in keys[:-1]: field = field[key]
            self.assertEqual(field[keys[-1]], '0.6.0-rc.4')
            field[keys[-1]] = '0.6.0-rc.5'
            self.bad_content(self.changed(path, json.dumps(data).encode()))
        for path, before in (('src-tauri/Cargo.toml', 'version = "0.6.0-rc.4"'),
                             ('src-tauri/Cargo.lock', 'name = "coding-tools-mcp-desktop"\nversion = "0.6.0-rc.4"')):
            data = c._git('show', n.F + ':' + path, root=self.repo).decode()
            self.bad_content(self.changed(path, c._replace_once(data, before, before.replace('rc.4', 'rc.5')).encode()))

    def test_release_document_byte_mode_path_and_deletion_drift_rejects(self):
        for path in (*n.R_DOCUMENTS, 'docs/releases/unreviewed.md', 'scripts/rc_consumer_io.py'):
            for value in (None, ('100644', 'blob', self.blob(b'drift\n')), ('100644', 'blob', self.blob(b'\0binary')),
                          ('100755', 'blob', self.blob(b'drift\n')), ('120000', 'blob', self.blob(b'target'))):
                changed = dict(self.overlay)
                if value is None: changed.pop(path, None)
                else: changed[path] = value
                if changed != self.overlay:
                    with self.subTest(path=path, value=value): self.bad_content(changed, [n.R, self.feature])
            if path in n.R_DOCUMENTS:
                changed = dict(self.overlay); value = changed.pop(path); changed[path + '.renamed'] = value
                self.bad_content(changed, [n.R, self.feature])
        for release, tree, documents in (('f' * 40, n.R_TREE, n.R_DOCUMENTS), (n.R, '0' * 40, n.R_DOCUMENTS),
                                         (n.R, n.R_TREE, {})):
            with self.assertRaises(AssertionError):
                n.selected_profile(self.release, self.repo, c._git, c._entries, c._feature_profile,
                                   release, tree, documents)

    def test_amendment_pins_scope_individual_and_total_budgets_reject(self):
        self.assertEqual(self.amended(self.pure), self.good)
        self.assertEqual((len(n.AMENDMENT_CAPS), len(n.AMENDMENT_PINS), n.AMENDMENT_DELTA_LIMIT), (7, 6, 1250))
        for path, pin in n.AMENDMENT_PINS.items():
            self.bad_content(self.changed(path, (c.ROOT / path).read_bytes() + b'\n'))
            for altered in (('0' * 40, pin[1]), (pin[0], '0' * 64)):
                with patch.object(n, 'AMENDMENT_PINS', n.AMENDMENT_PINS | {path: altered}), self.assertRaises(AssertionError):
                    self.amended(self.pure)
        for path, (_, diff_cap) in n.AMENDMENT_CAPS.items():
            cap = len((c.ROOT / path).read_bytes().splitlines()) - 1
            with patch.object(n, 'AMENDMENT_CAPS', n.AMENDMENT_CAPS | {path: (cap, diff_cap)}), self.assertRaises(AssertionError):
                self.amended(self.pure)
            def oversized_diff(*args, root):
                if args == ('diff', '--numstat', n.P, self.pure, '--', path):
                    return f'{diff_cap + 1}\t0\t{path}\n'.encode()
                return c._git(*args, root=root)
            with self.assertRaises(AssertionError): self.amended(self.pure, git=oversized_diff)
        data = (c.ROOT / n.PROFILE).read_bytes()
        cap = n.AMENDMENT_CAPS[n.PROFILE][0]
        self.bad_content(self.changed(n.PROFILE, data + b'# line boundary\n' * (cap + 1 - len(data.splitlines()))))
        self.bad_content(self.changed(n.PROFILE, b'\0binary\xff'))
        total = sum(sum(map(int, c._git('diff', '--numstat', n.P, self.pure, '--', p,
                                       root=self.repo).split()[:2])) for p in n.AMENDMENT_CAPS)
        oversized = data + b'# aggregate\n' * (n.AMENDMENT_DELTA_LIMIT + 1 - total)
        with patch.object(n, 'AMENDMENT_CAPS', {p: (10000, 10000) for p in n.AMENDMENT_CAPS}):
            self.bad_content(self.changed(n.PROFILE, oversized))

    def test_composition_adapter_inverse_recovers_exact_f(self):
        frozen = c._git('show', n.F + ':' + n.COMPOSITION, root=self.repo)
        self.assertEqual(o.pin(frozen), d.AMENDMENT_PINS[d.COMPOSITION])
        current = (c.ROOT / n.COMPOSITION).read_text()
        for before, after in (('import rc_pretag_nginx_profile as nginx\n', ''),
                              ('expected = nginx.selected_profile(', 'expected = desktop.selected_profile('),
                              ('assert not (EXPECTED_GROUPS.keys() & nginx.EXPECTED_GROUPS.keys())\n'
                               'EXPECTED_GROUPS.update(nginx.EXPECTED_GROUPS)\n', '')):
            current = c._replace_once(current, before, after)
        self.assertEqual(current.encode(), frozen)
        self.assertEqual(o.pin((c.ROOT / n.COMPOSITION).read_bytes()), n.AMENDMENT_PINS[n.COMPOSITION])

    def test_desktop_fixture_adapter_preserves_historical_assertions(self):
        frozen = c._git('show', n.F + ':' + n.DESKTOP_TESTS, root=self.repo)
        current = (c.ROOT / n.DESKTOP_TESTS).read_bytes()
        self.assertEqual(o.pin(frozen), d.AMENDMENT_PINS[d.TESTS])
        self.assertEqual(o.pin(current), n.AMENDMENT_PINS[n.DESKTOP_TESTS])
        def methods(data):
            owner = next(node for node in ast.parse(data).body if isinstance(node, ast.ClassDef))
            return {node.name: node for node in owner.body if isinstance(node, ast.FunctionDef)}
        old, new = methods(frozen), methods(current)
        allowed = {'setUp', 'test_composition_adapter_reconstructs_frozen_x',
                   'test_legacy_inventory_and_new_named_inventory_are_exact'}
        self.assertEqual(old.keys(), new.keys())
        self.assertEqual({name for name in old if ast.dump(old[name]) != ast.dump(new[name])}, allowed)
        lines, old_lines = current.decode().splitlines(keepends=True), frozen.decode().splitlines(keepends=True)
        for name in sorted(allowed, key=lambda name: new[name].lineno, reverse=True):
            lines[new[name].lineno - 1:new[name].end_lineno] = old_lines[old[name].lineno - 1:old[name].end_lineno]
        self.assertEqual(''.join(lines).encode(), frozen)
        for name in allowed - {'setUp'}:
            assertions = lambda node: Counter(ast.dump(call) for call in ast.walk(node) if isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute) and call.func.attr.startswith('assert'))
            missing = assertions(old[name]) - assertions(new[name])
            self.assertEqual(sum(missing.values()), 2 if name.endswith('inventory_are_exact') else 0)
        historical = dt.DesktopCompositionTests()
        self.addCleanup(historical.doCleanups); historical.setUp()
        self.assertEqual(historical.good, c._entries(n.F, historical.repo))
        self.assertEqual(historical.selected(historical.pure), historical.good)

    def test_frozen_167_plus_20_inventory_has_exact_loaded_and_executed_ids(self):
        frozen = ast.parse(c._git('show', n.F + ':' + n.COMPOSITION, root=self.repo))
        old = ast.literal_eval(next(node.value for node in frozen.body if isinstance(node, ast.Assign) and
            any(isinstance(target, ast.Name) and target.id == 'EXPECTED_GROUPS' for target in node.targets)))
        self.assertEqual(sum(len(names.split()) for names in old.values()), 147)
        historical = old | d.EXPECTED_GROUPS
        self.assertEqual(sum(len(names.split()) for names in historical.values()), 167)
        self.assertFalse(historical.keys() & n.EXPECTED_GROUPS.keys())
        self.assertEqual(c.EXPECTED_GROUPS, historical | n.EXPECTED_GROUPS)
        names = next(iter(n.EXPECTED_GROUPS.values())).split()
        self.assertEqual((len(names), len(set(names))), (20, 20))
        self.assertEqual(set(names), set(unittest.defaultTestLoader.getTestCaseNames(type(self))))
        suite = unittest.defaultTestLoader.discover(str(c.ROOT / 'scripts'), pattern='rc_pretag*_tests.py')
        loaded = [test.id() for test in c._flatten(suite)]
        expected = [prefix + '.' + name for prefix, names in c.EXPECTED_GROUPS.items() for name in names.split()]
        self.assertEqual(Counter(loaded), Counter(expected))
        self.assertEqual((len(loaded), len(set(loaded))), (187, 187))
        current = ast.parse((c.ROOT / n.COMPOSITION).read_bytes())
        for name in ('run_inventory', 'InventoryResult', '_flatten'):
            extract = lambda tree: ast.dump(next(node for node in tree.body if getattr(node, 'name', '') == name))
            self.assertEqual(extract(current), extract(frozen))

    def test_mutable_refs_and_ambient_git_redirection_cannot_change_identity(self):
        calls = []
        def moving(*args, root):
            calls.append(args)
            if args == ('rev-parse', '--verify', 'moving^{commit}'):
                return ((self.pure if calls.count(args) == 1 else self.release) + '\n').encode()
            return c._git(*args, root=root)
        hostile = dict(GIT_DIR='/nonexistent', GIT_WORK_TREE='/nonexistent', GIT_INDEX_FILE='/nonexistent/index',
            GIT_COMMON_DIR='/nonexistent', GIT_OBJECT_DIRECTORY='/nonexistent', GIT_ALTERNATE_OBJECT_DIRECTORIES='/nonexistent',
            GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='core.worktree', GIT_CONFIG_VALUE_0='/nonexistent', GIT_NO_REPLACE_OBJECTS='0')
        with patch.dict(os.environ, hostile): self.assertEqual(self.selected('moving', moving), self.good)
        self.assertEqual(calls.count(('rev-parse', '--verify', 'moving^{commit}')), 1)
        self.assertEqual(sum(any('moving' in arg for arg in args) for args in calls), 1)
        calls.clear(); n.nginx_topology(self.pure, self.repo, moving, n.R)
        self.assertTrue(all(args[:3] == ('show', '-s', '--format=%P') for args in calls))

    def test_topology_only_dispatch_keeps_legacy_content_failures_terminal(self):
        for module, name, ref in ((o, 'content', d.X), (d, 'desktop_content', n.F)):
            for error in (AssertionError, o.TopologyError):
                with patch.object(module, name, side_effect=error('terminal content failure')), \
                     patch.object(n, 'nginx_content') as content:
                    with self.assertRaisesRegex(error, 'terminal content failure'): self.selected(ref)
                    content.assert_not_called()
        for parent, topology in ((o.M, o.topology), (d.SOURCE, d.desktop_topology)):
            ref = self.commit([parent], self.good)
            topology(ref, self.repo, c._git, n.R)
            with patch.object(n, 'nginx_content') as content, self.assertRaises(AssertionError) as failure:
                self.selected(ref)
            self.assertNotIsInstance(failure.exception, o.TopologyError)
            content.assert_not_called()

    def test_unknown_profile_versions_and_native_release_claims_reject(self):
        self.assertEqual(n.PROFILE_ID, 'engineering/issue40-nginx-composition-v1')
        for profile in (None, 1, '', 'engineering/issue40-nginx-composition-v2', 'native', 'release', 'publish'):
            with patch.object(n, 'nginx_content') as content, self.assertRaises(AssertionError):
                self.selected(self.pure, git=lambda *a, **kw: self.fail('Git ran before profile rejection'), profile=profile)
            content.assert_not_called()
        path = 'deploy/cloud-gateway/current_nginx_include.py'
        data = c._git('show', n.P + ':' + path, root=self.repo).decode()
        for flag in ('upstream_reachability_verified', 'applied', 'production_ready', 'real_host_tls_waf_tested', 'publish_approved'):
            self.assertIn(flag + '=False', data)
            self.bad_content(self.changed(path, data.replace(flag + '=False', flag + '=True').encode()))
        module = ast.parse((c.ROOT / n.PROFILE).read_bytes())
        calls = {getattr(node.func, 'id', getattr(node.func, 'attr', '')) for node in ast.walk(module) if isinstance(node, ast.Call)}
        self.assertFalse(calls & {'open', 'write_bytes', 'write_text', 'Popen', 'run', 'system', 'urlopen', 'dispatch'})
        self.assertEqual(n.AMENDMENT_PINS.keys(), n.AMENDMENT_CAPS.keys() - {n.PROFILE})


if __name__ == '__main__':
    unittest.main()
