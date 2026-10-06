"""Exact desktop engineering overlay; synthetic composition is never native evidence."""
import ast
from contextlib import ExitStack
import hashlib
import os
import unittest
from unittest.mock import patch

import rc_pretag_composition_tests as c
import rc_pretag_desktop_profile as d
import rc_pretag_ownership_profile as o


class DesktopCompositionTests(unittest.TestCase):
    def setUp(self):
        self.repo, _, self.commit, self.blob = self.enterContext(c._profile_fixture())
        self.source = c._entries(d.SOURCE, self.repo)
        self.assertEqual(tuple(o._parents(c.nginx.F, self.repo, c._git)), c.nginx.F_PARENTS)
        self.assertEqual(c._git('rev-parse', c.nginx.F + '^{tree}', root=self.repo).decode().strip(),
                         c.nginx.F_TREE)
        frozen = self.selected(c.nginx.F)
        self.good = self.source | {p: frozen[p] for p in d.AMENDMENT_CAPS}
        self.pure = self.commit([d.SOURCE], self.good)
        self.feature = self.commit([d.X, self.pure], self.good)
        self.overlay = self.good | c.RELEASE_DOCS
        self.release = self.commit([c.RELEASE, self.feature], self.overlay)

    def selected(self, ref, git=c._git):
        return d.selected_profile(ref, self.repo, git, c._entries, c._feature_profile,
                                  c.RELEASE, c.RELEASE_TREE, c.RELEASE_DOCS)

    def desktop(self, ref):
        return d.desktop_content(ref, self.repo, c._git, c._entries, c._feature_profile,
                                 c.RELEASE, c.RELEASE_TREE, c.RELEASE_DOCS)

    def amended(self, ref, entries=c._entries):
        return d.amendment_content(ref, self.source, self.repo, c._git, entries)

    def changed(self, path, data, mode='100644', base=None):
        return (self.good if base is None else base) | {path: (mode, 'blob', self.blob(data))}

    def rejects(self, parents, expected):
        ref = self.commit(parents, expected)
        self.assertEqual(c._entries(ref, self.repo), expected)
        self.assertEqual(self.desktop(d.SOURCE), self.source)
        if expected == self.source:
            self.assertEqual(self.desktop(ref), expected)
        elif expected == self.good:
            self.assertEqual(self.amended(ref), expected)
        else:
            self.assertEqual(expected, self.overlay)
            self.assertEqual(self.amended(self.pure), self.good)
            o.release_content(ref, self.good, self.repo, c._git, c._entries,
                              c.RELEASE, c.RELEASE_TREE, c.RELEASE_DOCS)
        with self.assertRaises(o.TopologyError):
            d.desktop_topology(ref, self.repo, c._git, c.RELEASE)
        with ExitStack() as stack:
            stopped = [stack.enter_context(patch.object(module, name, side_effect=AssertionError('content ran')))
                       for module, name in ((d, 'desktop_content'), (d, 'amendment_content'), (o, 'content'))]
            with self.assertRaises(o.TopologyError):
                self.selected(ref)
            for action in stopped:
                action.assert_not_called()

    def bad_content(self, entries, parents=None):
        ref = self.commit([d.SOURCE] if parents is None else parents, entries)
        d.desktop_topology(ref, self.repo, c._git, c.RELEASE)
        with self.assertRaises(AssertionError) as failure:
            self.selected(ref)
        self.assertNotIsInstance(failure.exception, o.TopologyError)

    def test_exact_x_preserves_legacy_profile_and_pins(self):
        expected = o.selected_profile(d.X, self.repo, c._git, c._entries, c._feature_profile,
                                      c.RELEASE, c.RELEASE_TREE, c.RELEASE_DOCS)
        self.assertEqual(self.selected(d.X), expected)
        self.assertEqual(len(expected), 1632)
        self.assertEqual((len(c.ALLOWED), len(o.CAPS), o.DELTA_LIMIT), (22, 13, 2200))
        for path in ('scripts/rc_pretag_ownership_profile.py', 'scripts/rc_pretag_ownership_tests.py'):
            from rc_pretag_publication_tests import inverse_ownership
            frozen = c._git('show', d.X + ':' + path, root=self.repo)
            current = (c.ROOT / path).read_bytes()
            if path == c.publication.OWNERSHIP_TESTS: current = inverse_ownership(current, frozen)
            self.assertEqual(current, frozen)
        with patch.object(o, 'selected_profile', wraps=o.selected_profile) as legacy:
            self.desktop(d.SOURCE)
            self.assertEqual(legacy.call_args.args[0], d.X)
            self.assertIs(legacy.call_args.args[4], c._feature_profile)

    def test_immutable_source_prefix_and_thirteen_additions(self):
        self.assertEqual(self.desktop(d.SOURCE), self.source)
        for child, parent in d.SOURCE_PARENT_CHAIN:
            self.assertEqual(o._parents(child, self.repo, c._git), [parent])
        self.assertEqual(tuple(o._parents(d.X, self.repo, c._git)), d.X_PARENTS)
        added = self.source.keys() - c._entries(d.X, self.repo).keys()
        self.assertEqual(added, d.DESKTOP_PINS.keys())
        self.assertEqual(sum(row[3] for row in d.DESKTOP_PINS.values()), 219755)
        self.assertEqual(sum(row[4] for row in d.DESKTOP_PINS.values()), 3587)

    def test_exact_source_and_one_amendment_accept(self):
        self.assertEqual(self.selected(d.SOURCE), self.source)
        self.assertEqual(self.selected(self.pure), self.good)
        with self.assertRaises(o.TopologyError):
            o.topology(d.SOURCE, self.repo, c._git, c.RELEASE)
        self.bad_content(self.source)

    def test_exact_feature_merge_accepts_equal_tree(self):
        for source, expected in ((d.SOURCE, self.source), (self.pure, self.good)):
            merged = self.commit([d.X, source], expected)
            self.assertEqual(self.selected(merged), expected)
            self.assertEqual(c._git('rev-parse', merged + '^{tree}', root=self.repo),
                             c._git('rev-parse', source + '^{tree}', root=self.repo))

    def test_exact_release_overlay_accepts_four_documents(self):
        self.assertEqual(self.selected(self.release), self.overlay)
        feature = self.commit([d.X, d.SOURCE], self.source)
        overlay = self.source | c.RELEASE_DOCS
        self.assertEqual(self.selected(self.commit([c.RELEASE, feature], overlay)), overlay)
        self.assertEqual(len(c.RELEASE_DOCS), 4)
        self.assertEqual((d.R, d.R_TREE, d.R_DOCUMENTS), (c.RELEASE, c.RELEASE_TREE, c.RELEASE_DOCS))

    def test_wrong_root_and_tree_equal_anchor_reject_before_content(self):
        foreign = self.commit([], self.good)
        fake_x = self.commit([], c._entries(d.X, self.repo))
        fake_s = self.commit([], self.source)
        fake_r = self.commit([], c._entries(c.RELEASE, self.repo))
        for parents in ([], [foreign], [fake_s], [fake_x, self.pure]):
            with self.subTest(parents=parents):
                self.rejects(parents, self.good)
        self.rejects([fake_r, self.feature], self.overlay)
        self.rejects([], self.source)

    def test_missing_reversed_duplicate_and_extra_parents_reject_before_content(self):
        for parents in ([d.X], [self.pure, d.X], [d.X, d.X], [d.SOURCE, d.SOURCE],
                        [d.X, self.pure, d.SOURCE]):
            with self.subTest(parents=parents):
                self.rejects(parents, self.good)
        for parents in ([self.feature, c.RELEASE], [c.RELEASE, self.feature, d.SOURCE],
                        [c.RELEASE, c.RELEASE], [c.RELEASE, self.pure]):
            with self.subTest(parents=parents):
                self.rejects(parents, self.overlay)
        with patch.object(d, 'desktop_content') as content, self.assertRaises(o.TopologyError):
            self.selected('f' * 40)
        content.assert_not_called()

    def test_nested_merge_release_and_postmerge_descendants_reject_before_content(self):
        for parents in ([d.X, self.feature], [self.feature], [d.X, self.release]):
            self.rejects(parents, self.good)
        for parents in ([c.RELEASE, self.release], [self.release], [c.RELEASE, d.SOURCE]):
            self.rejects(parents, self.overlay)

    def test_amendment_chain_and_wrong_parent_reject_before_content(self):
        for parents in ([self.pure], [d.SOURCE_PARENT_CHAIN[0][1]], [d.X], [d.SOURCE, self.pure]):
            self.rejects(parents, self.good)
        def wrong_prefix(*args, root):
            if args == ('show', '-s', '--format=%P', d.SOURCE):
                return (d.X + '\n').encode()
            return c._git(*args, root=root)
        with patch.object(d, 'desktop_content') as content, self.assertRaises(o.TopologyError):
            self.selected(self.pure, wrong_prefix)
        content.assert_not_called()

    def test_merge_tree_drift_rejects_after_valid_topology(self):
        changed = self.changed(d.COLLECTOR, b'unreviewed merge resolution\n', mode='100755')
        self.bad_content(changed, [d.X, self.pure])
        self.bad_content(self.source, [d.X, self.pure])

    def test_release_overlay_path_mode_byte_and_deletion_drift_rejects(self):
        for path in (*c.RELEASE_DOCS, 'unreviewed-release-document.md', 'scripts/rc_consumer_io.py'):
            for value in (None, ('100644', 'blob', self.blob(b'drift\n')),
                          ('100755', 'blob', self.blob(b'drift\n'))):
                changed = dict(self.overlay)
                if value is None:
                    changed.pop(path, None)
                else:
                    changed[path] = value
                if changed != self.overlay:
                    with self.subTest(path=path, value=value):
                        self.bad_content(changed, [c.RELEASE, self.feature])
        fake_r = self.commit([], c._entries(c.RELEASE, self.repo))
        forged = self.commit([fake_r, self.feature], self.overlay)
        self.assertEqual(self.amended(self.pure), self.good)
        o.release_content(forged, self.good, self.repo, c._git, c._entries,
                          c.RELEASE, c.RELEASE_TREE, c.RELEASE_DOCS)
        with patch.object(d, 'desktop_content') as content, self.assertRaises(o.TopologyError):
            d.selected_profile(forged, self.repo, c._git, c._entries, c._feature_profile,
                               fake_r, c.RELEASE_TREE, c.RELEASE_DOCS)
        content.assert_not_called()
        for tree, documents in (('0' * 40, c.RELEASE_DOCS), (c.RELEASE_TREE, {})):
            with self.assertRaises(AssertionError):
                d.selected_profile(self.release, self.repo, c._git, c._entries, c._feature_profile,
                                   c.RELEASE, tree, documents)

    def test_each_desktop_blob_and_hash_mutation_rejects(self):
        for path, row in d.DESKTOP_PINS.items():
            with self.subTest(path=path):
                self.bad_content(self.changed(path, (c.ROOT / path).read_bytes() + b'\n', mode=row[0]))
                altered = dict(d.DESKTOP_PINS)
                altered[path] = (*row[:2], '0' * 64, *row[3:])
                with patch.object(d, 'DESKTOP_PINS', altered), self.assertRaises(AssertionError):
                    self.desktop(d.SOURCE)

    def test_desktop_missing_extra_rename_and_type_mutations_reject(self):
        path = d.COLLECTOR
        missing = dict(self.good)
        missing.pop(path)
        mutations = [missing, self.good | {'extra.py': self.good[path]},
                     missing | {path + '.renamed': self.good[path]},
                     missing | {path + '/child': ('100644', 'blob', self.blob(b'child\n'))}]
        mutations += [self.good | {path: (mode, kind, object_id)} for mode, kind, object_id in
                      (('120000', 'blob', self.blob(b'target')), ('160000', 'commit', d.SOURCE))]
        for entries in mutations:
            with self.subTest(entries=len(entries)):
                self.bad_content(entries)

    def test_only_pinned_collector_executable_mode_accepts(self):
        self.assertEqual([p for p, entry in self.source.items() if entry[0] == '100755'], [d.COLLECTOR])
        for path, entry in self.source.items():
            if path not in d.DESKTOP_PINS:
                continue
            mode = '100644' if path == d.COLLECTOR else '100755'
            self.bad_content(self.good | {path: (mode, *entry[1:])})
        for path in d.AMENDMENT_CAPS:
            self.bad_content(self.good | {path: ('100755', *self.good[path][1:])})

    def test_each_historical_protected_entry_remains_exact(self):
        original = c._entries(d.X, self.repo)
        self.assertTrue(all(self.source[path] == value for path, value in original.items()))
        bad_blob = self.blob(b'changed historical entry\n')
        for path in original.keys() - {d.COMPOSITION}:
            changed = self.good | {path: ('100644', 'blob', bad_blob)}
            with self.subTest(path=path), self.assertRaises(AssertionError):
                self.amended(self.pure, entries=lambda ref, root: changed)

    def test_amendment_scope_pins_and_budgets_reject_drift(self):
        for path in d.AMENDMENT_PINS:
            self.bad_content(self.changed(path, (c.ROOT / path).read_bytes() + b'\n'))
        missing = dict(self.good)
        missing.pop(d.TESTS)
        self.bad_content(missing)
        self.bad_content(self.good | {'scripts/rc_pretag_unreviewed.py': self.good[d.TESTS]})
        source = (c.ROOT / d.PROFILE).read_bytes()
        cap = d.AMENDMENT_CAPS[d.PROFILE][0]
        self.bad_content(self.changed(d.PROFILE, source + b'# boundary\n' * (cap + 1 - len(source.splitlines()))))
        total = sum(sum(map(int, c._git('diff', '--numstat', d.SOURCE, self.pure, '--', p,
                                       root=self.repo).split()[:2])) for p in d.AMENDMENT_CAPS)
        oversized = source + b'# aggregate\n' * (d.AMENDMENT_DELTA_LIMIT + 1 - total)
        with patch.object(d, 'AMENDMENT_CAPS', {p: (10000, 10000) for p in d.AMENDMENT_CAPS}):
            self.bad_content(self.changed(d.PROFILE, oversized))

    def test_composition_adapter_reconstructs_frozen_x(self):
        original = c._git('show', d.X + ':' + d.COMPOSITION, root=self.repo)
        self.assertEqual(hashlib.sha256(original).hexdigest(), d.COMPOSITION_BASE_SHA256)
        current = c._git('show', c.authenticated_two_hop.M + ':' + d.COMPOSITION, root=self.repo).decode()
        for before, after in (
            ('import rc_pretag_two_hop_profile as two_hop\n',
             ''),
            ('expected = two_hop.selected_profile(',
             'expected = nginx.selected_profile('),
            ('assert not (EXPECTED_GROUPS.keys() & two_hop.EXPECTED_GROUPS.keys())\n'
             'EXPECTED_GROUPS.update(two_hop.EXPECTED_GROUPS)\n',
             ''),
        ):
            current = c._replace_once(current, before, after)
        self.assertEqual(current.encode(), c._git('show', c.two_hop.F + ':' + d.COMPOSITION, root=self.repo))
        for before, after in (
            ('import rc_pretag_nginx_profile as nginx\n', ''),
            ('expected = nginx.selected_profile(', 'expected = desktop.selected_profile('),
            ('assert not (EXPECTED_GROUPS.keys() & nginx.EXPECTED_GROUPS.keys())\n'
             'EXPECTED_GROUPS.update(nginx.EXPECTED_GROUPS)\n', ''),
        ):
            current = c._replace_once(current, before, after)
        self.assertEqual(current.encode(), c._git('show', c.nginx.F + ':' + d.COMPOSITION, root=self.repo))
        self.assertEqual(o.pin(current.encode()), d.AMENDMENT_PINS[d.COMPOSITION])
        frozen = current
        replacements = (
            ('import rc_pretag_desktop_profile as desktop\n', ''),
            ('expected = desktop.selected_profile(', 'expected = ownership.selected_profile('),
            ('actual.stat().st_mode & 0o111, int(mode, 8) & 0o111', 'actual.stat().st_mode & 0o111, 0'),
            ('assert not (EXPECTED_GROUPS.keys() & desktop.EXPECTED_GROUPS.keys())\n'
             'EXPECTED_GROUPS.update(desktop.EXPECTED_GROUPS)\n\n\n', ''),
        )
        for before, after in replacements:
            current = c._replace_once(current, before, after)
        self.assertEqual(current.encode(), original)
        old_tree, new_tree = ast.parse(original), ast.parse(frozen)
        def methods(tree):
            owner = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'CompositionTests')
            return {n.name: ast.dump(n, include_attributes=False) for n in owner.body if isinstance(n, ast.FunctionDef)}
        old, new = methods(old_tree), methods(new_tree)
        self.assertEqual(old.keys(), new.keys())
        self.assertEqual([name for name in old if old[name] != new[name]], ['test_exact_tracked_tree_modes_and_scope'])

    def test_legacy_inventory_and_new_named_inventory_are_exact(self):
        original = ast.parse(c._git('show', d.SOURCE + ':' + d.COMPOSITION, root=self.repo))
        node = next(n for n in original.body if isinstance(n, ast.Assign) and
                    any(isinstance(t, ast.Name) and t.id == 'EXPECTED_GROUPS' for t in n.targets))
        old = ast.literal_eval(node.value)
        self.assertEqual(sum(len(names.split()) for names in old.values()), 147)
        self.assertFalse(old.keys() & d.EXPECTED_GROUPS.keys())
        self.assertFalse((old.keys() | d.EXPECTED_GROUPS.keys()) & c.nginx.EXPECTED_GROUPS.keys())
        self.assertEqual(sum(len(names.split()) for names in c.nginx.EXPECTED_GROUPS.values()), 20)
        historical = old | d.EXPECTED_GROUPS | c.nginx.EXPECTED_GROUPS
        self.assertEqual((sum(len(names.split()) for names in (old | d.EXPECTED_GROUPS).values()),
                          sum(len(names.split()) for names in historical.values())), (167, 187))
        self.assertFalse(historical.keys() & c.two_hop.EXPECTED_GROUPS.keys())
        self.assertEqual(sum(len(names.split()) for names in c.two_hop.EXPECTED_GROUPS.values()), 22)
        self.assertEqual({key: c.EXPECTED_GROUPS[key] for key in historical}, old | d.EXPECTED_GROUPS | c.nginx.EXPECTED_GROUPS)
        previous = historical | c.two_hop.EXPECTED_GROUPS
        self.assertEqual({key: c.EXPECTED_GROUPS[key] for key in previous}, historical | c.two_hop.EXPECTED_GROUPS)
        complete_historical = previous | c.authenticated_two_hop.EXPECTED_GROUPS
        self.assertEqual({key: c.EXPECTED_GROUPS[key] for key in complete_historical}, complete_historical)
        self.assertEqual(c.EXPECTED_GROUPS, complete_historical | c.publication.EXPECTED_GROUPS)
        names = next(iter(d.EXPECTED_GROUPS.values())).split()
        self.assertEqual(len(names), 20)
        self.assertEqual(set(names), set(unittest.defaultTestLoader.getTestCaseNames(type(self))))
        suite = unittest.defaultTestLoader.discover(str(c.ROOT / 'scripts'), pattern='rc_pretag*_tests.py')
        loaded = [test.id() for test in c._flatten(suite)]
        expected = [prefix + '.' + name for prefix, names in c.EXPECTED_GROUPS.items() for name in names.split()]
        self.assertEqual(c.Counter(loaded), c.Counter(expected))
        legacy = [name for name in loaded if name.rsplit('.', 1)[0] in historical]
        self.assertEqual((len(legacy), len(set(legacy))), (187, 187))
        prior_loaded = [name for name in loaded if name.rsplit('.', 1)[0] in previous]
        self.assertEqual((len(prior_loaded), len(set(prior_loaded))), (209, 209))
        full_historical = [name for name in loaded if name.rsplit('.', 1)[0] in complete_historical]
        self.assertEqual((len(full_historical), len(set(full_historical))), (233, 233))
        self.assertEqual((len(loaded), len(set(loaded))), (283, 283))

    def test_git_context_isolation_and_topology_only_dispatch(self):
        calls = []
        def moving(*args, root):
            calls.append(args)
            if args == ('rev-parse', '--verify', 'moving^{commit}'):
                return (self.pure + '\n').encode()
            return c._git(*args, root=root)
        hostile = dict(GIT_DIR='/nonexistent', GIT_WORK_TREE='/nonexistent', GIT_INDEX_FILE='/nonexistent/index',
                       GIT_COMMON_DIR='/nonexistent', GIT_OBJECT_DIRECTORY='/nonexistent',
                       GIT_ALTERNATE_OBJECT_DIRECTORIES='/nonexistent', GIT_CONFIG_COUNT='1',
                       GIT_CONFIG_KEY_0='core.worktree', GIT_CONFIG_VALUE_0='/nonexistent')
        with patch.dict(os.environ, hostile):
            self.assertEqual(self.selected('moving', moving), self.good)
        self.assertEqual(calls.count(('rev-parse', '--verify', 'moving^{commit}')), 1)
        calls.clear()
        d.desktop_topology(self.pure, self.repo, moving, c.RELEASE)
        self.assertTrue(all(args[:3] == ('show', '-s', '--format=%P') for args in calls))
        with patch.object(o, 'content', side_effect=AssertionError('legacy content failure')), \
             patch.object(d, 'desktop_content') as content:
            with self.assertRaisesRegex(AssertionError, 'legacy content failure'):
                self.selected(d.X)
            content.assert_not_called()
        legacy_desktop = self.commit([o.M], self.good)
        o.topology(legacy_desktop, self.repo, c._git, c.RELEASE)
        with patch.object(d, 'desktop_content') as content:
            with self.assertRaises(AssertionError) as failure:
                self.selected(legacy_desktop)
            self.assertNotIsInstance(failure.exception, o.TopologyError)
            content.assert_not_called()

    def test_engineering_scope_and_false_claim_boundaries(self):
        self.assertEqual(d.PROFILE_ID, 'engineering/issue85-desktop-composition-v1')
        self.assertEqual(d.SOURCE, '932c48d07ccfc49c312f6ee9b7ffc0ea19c65fe8')
        self.assertNotEqual(self.pure, d.SOURCE)
        data = c._git('show', d.SOURCE + ':scripts/desktop_glib_build_contract.py', root=self.repo)
        tree = ast.parse(data)
        flags = next(n.value for n in tree.body if isinstance(n, ast.Assign) and
                     any(isinstance(t, ast.Name) and t.id == 'FLAGS' for t in n.targets))
        self.assertEqual({arg.arg: ast.literal_eval(arg.value) for arg in flags.keywords}, dict(
            engineering_only=True, installed_desktop_bytes_verified=False, security_approved=False,
            release_approved=False, publish_approved=False, raw_zero_claim=False))
        link = c._git('show', d.SOURCE + ':scripts/desktop_glib_link.py', root=self.repo).decode()
        for flag in ('native_linker_consumption_verified', 'retained_glib_code_verified'):
            self.assertIn("'" + flag + "': False", link)
        module = ast.parse((c.ROOT / d.PROFILE).read_bytes())
        calls = {getattr(n.func, 'id', getattr(n.func, 'attr', '')) for n in ast.walk(module) if isinstance(n, ast.Call)}
        self.assertFalse(calls & {'open', 'write_bytes', 'write_text', 'Popen', 'run', 'system', 'urlopen', 'dispatch'})
        self.assertEqual(d.AMENDMENT_PINS.keys(), d.AMENDMENT_CAPS.keys() - {d.PROFILE})


if __name__ == '__main__':
    unittest.main()
