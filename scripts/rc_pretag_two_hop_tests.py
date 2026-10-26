"""Exact native-source composition; local synthetic trees confer no native authority."""
import ast
from collections import Counter
from contextlib import ExitStack
import hashlib
import json
import os
import unittest
from unittest.mock import patch

import rc_pretag_composition_tests as c
import rc_pretag_desktop_profile as d
import rc_pretag_nginx_profile as n
import rc_pretag_nginx_tests as nt
import rc_pretag_ownership_profile as o
import rc_pretag_two_hop_profile as t


FRAGMENTS = {
    'scripts/rc_pretag_composition_tests.py': (
        ('EXPECTED_GROUPS.update(nginx.EXPECTED_GROUPS)\nassert not (EXPECTED_GROUPS.keys() & two_hop.EXPECTED_GROUPS.keys())\nEXPECTED_GROUPS.update(two_hop.EXPECTED_GROUPS)\n', 'EXPECTED_GROUPS.update(nginx.EXPECTED_GROUPS)\n'),
        ('expected = two_hop.selected_profile(', 'expected = nginx.selected_profile('),
        ('import rc_pretag_nginx_profile as nginx\nimport rc_pretag_two_hop_profile as two_hop\n', 'import rc_pretag_nginx_profile as nginx\n'),
    ),
    'scripts/rc_pretag_desktop_tests.py': (
        ("        legacy = [name for name in loaded if name.rsplit('.', 1)[0] in historical]\n        self.assertEqual((len(legacy), len(set(legacy))), (187, 187))\n        self.assertEqual((len(loaded), len(set(loaded))), (209, 209))\n", '        self.assertEqual((len(loaded), len(set(loaded))), (187, 187))\n'),
        ('        historical = old | d.EXPECTED_GROUPS | c.nginx.EXPECTED_GROUPS\n        self.assertEqual((sum(len(names.split()) for names in (old | d.EXPECTED_GROUPS).values()),\n                          sum(len(names.split()) for names in historical.values())), (167, 187))\n        self.assertFalse(historical.keys() & c.two_hop.EXPECTED_GROUPS.keys())\n        self.assertEqual(sum(len(names.split()) for names in c.two_hop.EXPECTED_GROUPS.values()), 22)\n        self.assertEqual({key: c.EXPECTED_GROUPS[key] for key in historical}, old | d.EXPECTED_GROUPS | c.nginx.EXPECTED_GROUPS)\n        self.assertEqual(c.EXPECTED_GROUPS, historical | c.two_hop.EXPECTED_GROUPS)\n', '        self.assertEqual(c.EXPECTED_GROUPS, old | d.EXPECTED_GROUPS | c.nginx.EXPECTED_GROUPS)\n'),
        ("        current = (c.ROOT / d.COMPOSITION).read_text()\n        for before, after in (\n            ('import rc_pretag_two_hop_profile as two_hop\\n',\n             ''),\n            ('expected = two_hop.selected_profile(',\n             'expected = nginx.selected_profile('),\n            ('assert not (EXPECTED_GROUPS.keys() & two_hop.EXPECTED_GROUPS.keys())\\n'\n             'EXPECTED_GROUPS.update(two_hop.EXPECTED_GROUPS)\\n',\n             ''),\n        ):\n            current = c._replace_once(current, before, after)\n        self.assertEqual(current.encode(), c._git('show', c.two_hop.F + ':' + d.COMPOSITION, root=self.repo))\n", '        current = (c.ROOT / d.COMPOSITION).read_text()\n'),
    ),
    'scripts/rc_pretag_nginx_tests.py': (
        ("        historical_loaded = [name for name in loaded if name.rsplit('.', 1)[0] in legacy]\n        self.assertEqual((len(historical_loaded), len(set(historical_loaded))), (187, 187))\n        self.assertEqual((len(loaded), len(set(loaded))), (209, 209))\n", '        self.assertEqual((len(loaded), len(set(loaded))), (187, 187))\n'),
        ('        legacy = historical | n.EXPECTED_GROUPS\n        self.assertEqual(sum(len(names.split()) for names in legacy.values()), 187)\n        self.assertEqual({key: c.EXPECTED_GROUPS[key] for key in legacy}, historical | n.EXPECTED_GROUPS)\n        self.assertFalse(legacy.keys() & c.two_hop.EXPECTED_GROUPS.keys())\n        self.assertEqual(sum(len(names.split()) for names in c.two_hop.EXPECTED_GROUPS.values()), 22)\n        self.assertEqual(c.EXPECTED_GROUPS, legacy | c.two_hop.EXPECTED_GROUPS)\n', '        self.assertEqual(c.EXPECTED_GROUPS, historical | n.EXPECTED_GROUPS)\n'),
        ('        current = (c.ROOT / n.DESKTOP_TESTS).read_text()\n        for before, after in (\n            (\'        for before, after in (\\n\'\n             "            (\'import rc_pretag_two_hop_profile as two_hop\\\\n\',\\n"\n             "             \'\'),\\n"\n             "            (\'expected = two_hop.selected_profile(\',\\n"\n             "             \'expected = nginx.selected_profile(\'),\\n"\n             "            (\'assert not (EXPECTED_GROUPS.keys() & two_hop.EXPECTED_GROUPS.keys())\\\\n\'\\n"\n             "             \'EXPECTED_GROUPS.update(two_hop.EXPECTED_GROUPS)\\\\n\',\\n"\n             "             \'\'),\\n"\n             \'        ):\\n\'\n             \'            current = c._replace_once(current, before, after)\\n\'\n             "        self.assertEqual(current.encode(), c._git(\'show\', c.two_hop.F + \':\' + d.COMPOSITION, root=self.repo))\\n",\n             \'\'),\n            (\'        historical = old | d.EXPECTED_GROUPS | c.nginx.EXPECTED_GROUPS\\n\'\n             \'        self.assertEqual((sum(len(names.split()) for names in (old | d.EXPECTED_GROUPS).values()),\\n\'\n             \'                          sum(len(names.split()) for names in historical.values())), (167, 187))\\n\'\n             \'        self.assertFalse(historical.keys() & c.two_hop.EXPECTED_GROUPS.keys())\\n\'\n             \'        self.assertEqual(sum(len(names.split()) for names in c.two_hop.EXPECTED_GROUPS.values()), 22)\\n\'\n             \'        self.assertEqual({key: c.EXPECTED_GROUPS[key] for key in historical}, old | d.EXPECTED_GROUPS | c.nginx.EXPECTED_GROUPS)\\n\'\n             \'        self.assertEqual(c.EXPECTED_GROUPS, historical | c.two_hop.EXPECTED_GROUPS)\\n\',\n             \'        self.assertEqual(c.EXPECTED_GROUPS, old | d.EXPECTED_GROUPS | c.nginx.EXPECTED_GROUPS)\\n\'),\n            ("        legacy = [name for name in loaded if name.rsplit(\'.\', 1)[0] in historical]\\n"\n             \'        self.assertEqual((len(legacy), len(set(legacy))), (187, 187))\\n\'\n             \'        self.assertEqual((len(loaded), len(set(loaded))), (209, 209))\\n\',\n             \'        self.assertEqual((len(loaded), len(set(loaded))), (187, 187))\\n\'),\n        ):\n            current = c._replace_once(current, before, after)\n        current = current.encode()\n        self.assertEqual(current, c._git(\'show\', c.two_hop.F + \':\' + n.DESKTOP_TESTS, root=self.repo))\n', '        current = (c.ROOT / n.DESKTOP_TESTS).read_bytes()\n'),
        ('        self.assertEqual(o.pin(intermediate), n.AMENDMENT_PINS[n.COMPOSITION])\n', '        self.assertEqual(o.pin((c.ROOT / n.COMPOSITION).read_bytes()), n.AMENDMENT_PINS[n.COMPOSITION])\n'),
        ("        current = (c.ROOT / n.COMPOSITION).read_text()\n        for before, after in (\n            ('import rc_pretag_two_hop_profile as two_hop\\n',\n             ''),\n            ('expected = two_hop.selected_profile(',\n             'expected = nginx.selected_profile('),\n            ('assert not (EXPECTED_GROUPS.keys() & two_hop.EXPECTED_GROUPS.keys())\\n'\n             'EXPECTED_GROUPS.update(two_hop.EXPECTED_GROUPS)\\n',\n             ''),\n        ):\n            current = c._replace_once(current, before, after)\n        self.assertEqual(current.encode(), c._git('show', c.two_hop.F + ':' + n.COMPOSITION, root=self.repo))\n        intermediate = current.encode()\n", '        current = (c.ROOT / n.COMPOSITION).read_text()\n'),
        ("            cap = len(c._git('cat-file', 'blob', self.good[path][2], root=self.repo).splitlines()) - 1\n", '            cap = len((c.ROOT / path).read_bytes().splitlines()) - 1\n'),
        ("            self.assertEqual(c._git('show', c.two_hop.F + ':' + path, root=self.repo), data)\n", '            self.assertEqual((c.ROOT / path).read_bytes(), data)\n'),
        ("        self.assertEqual(tuple(o._parents(c.two_hop.F, self.repo, c._git)), c.two_hop.F_PARENTS)\n        self.assertEqual(c._git('rev-parse', c.two_hop.F + '^{tree}', root=self.repo).decode().strip(), c.two_hop.F_TREE)\n        frozen = self.selected(c.two_hop.F)\n        self.good = self.source | {p: frozen[p] for p in n.AMENDMENT_CAPS}\n", "        self.good = self.source | {p: ('100644', 'blob', self.blob((c.ROOT / p).read_bytes()))\n                                   for p in n.AMENDMENT_CAPS}\n"),
    ),
}
ALLOWED_METHODS = {'scripts/rc_pretag_composition_tests.py': {'test_exact_tracked_tree_modes_and_scope'}, 'scripts/rc_pretag_desktop_tests.py': {'test_legacy_inventory_and_new_named_inventory_are_exact', 'test_composition_adapter_reconstructs_frozen_x'}, 'scripts/rc_pretag_nginx_tests.py': {'test_p_source_has_only_nine_exact_additions', 'test_frozen_167_plus_20_inventory_has_exact_loaded_and_executed_ids', 'test_desktop_fixture_adapter_preserves_historical_assertions', 'test_composition_adapter_inverse_recovers_exact_f', 'setUp', 'test_amendment_pins_scope_individual_and_total_budgets_reject'}}

def methods(data):
    owner = next(node for node in ast.parse(data).body if isinstance(node, ast.ClassDef))
    return {node.name: node for node in owner.body if isinstance(node, ast.FunctionDef)}


def inverse_adapter(path, current, frozen):
    assert o.pin(frozen) == n.AMENDMENT_PINS[path], 'historical adapter pin'
    try: restored = current.decode()
    except UnicodeDecodeError as error: raise AssertionError('adapter encoding') from error
    for before, after in FRAGMENTS[path]: restored = c._replace_once(restored, before, after)
    assert restored.encode() == frozen, 'complete historical inverse'
    old, new = methods(frozen), methods(current)
    assert old.keys() == new.keys(), 'method names'
    assert {key for key in old if ast.dump(old[key]) != ast.dump(new[key])} == ALLOWED_METHODS[path]
    assertions = lambda node: Counter(ast.dump(call) for call in ast.walk(node) if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute) and call.func.attr.startswith('assert'))
    recovered = methods(restored)
    for name in old: assert assertions(old[name]) == assertions(recovered[name]), name
    return restored.encode()


def inventory_ids(ids):
    assert len(ids) == len(set(ids)) == 209
    assert hashlib.sha256('\n'.join(sorted(ids)).encode()).hexdigest() == '37ccb924975855074b8687a9eefb6ac0342bad4fa4c13b7e84b9e96e11e93695'


class TwoHopCompositionTests(unittest.TestCase):
    def setUp(self):
        self.repo, _, self.commit, self.blob = self.enterContext(c._profile_fixture())
        self.source = c._entries(t.P, self.repo)
        self.assertEqual(tuple(o._parents(c.authenticated_two_hop.M, self.repo, c._git)), c.authenticated_two_hop.M_PARENTS)
        self.assertEqual(c._git('rev-parse', c.authenticated_two_hop.M + '^{tree}', root=self.repo).decode().strip(), c.authenticated_two_hop.M_TREE)
        frozen = self.selected(c.authenticated_two_hop.M)
        self.good = self.source | {p: frozen[p] for p in t.AMENDMENT_CAPS}
        self.pure = self.commit([t.P], self.good)
        self.feature = self.commit([t.F, self.pure], self.good)
        self.overlay = self.good | c.RELEASE_DOCS
        self.release = self.commit([t.R, self.feature], self.overlay)
        t.two_hop_topology(self.pure, self.repo, c._git, t.R)

    def selected(self, ref, git=c._git, **kwargs):
        return t.selected_profile(ref, self.repo, git, c._entries, c._feature_profile,
                                  c.RELEASE, c.RELEASE_TREE, c.RELEASE_DOCS, **kwargs)

    def native(self, ref, git=c._git):
        return t.two_hop_content(ref, self.repo, git, c._entries, c._feature_profile,
                               c.RELEASE, c.RELEASE_TREE, c.RELEASE_DOCS)

    def amended(self, ref, entries=c._entries, git=c._git):
        return t.amendment_content(ref, self.source, self.repo, git, entries)

    def changed(self, path, data, mode='100644', base=None):
        return (self.good if base is None else base) | {path: (mode, 'blob', self.blob(data))}

    def rejects(self, parents, expected):
        ref = self.commit(parents, expected)
        self.assertEqual(c._entries(ref, self.repo), expected)
        self.assertEqual(self.native(t.P), self.source)
        if expected == self.source:
            self.assertEqual(self.native(ref), expected)
        elif expected == self.good:
            self.assertEqual(self.amended(ref), expected)
        else:
            self.assertEqual(expected, self.overlay)
            self.assertEqual(self.amended(self.pure), self.good)
            self.assertEqual(o.release_content(ref, self.good, self.repo, c._git, c._entries,
                                              t.R, t.R_TREE, t.R_DOCUMENTS), expected)
        with self.assertRaises(o.TopologyError):
            t.two_hop_topology(ref, self.repo, c._git, t.R)
        with ExitStack() as stack:
            stopped = [stack.enter_context(patch.object(module, name, side_effect=AssertionError('content ran')))
                       for module, name in ((o, 'content'), (o, 'release_content'), (d, 'desktop_content'),
                           (d, 'amendment_content'), (n, 'nginx_content'), (n, 'amendment_content'),
                           (t, 'two_hop_content'), (t, 'amendment_content'))]
            with self.assertRaises(o.TopologyError):
                self.selected(ref)
            for action in stopped:
                action.assert_not_called()

    def bad_content(self, entries, parents=None):
        ref = self.commit([t.P] if parents is None else parents, entries)
        t.two_hop_topology(ref, self.repo, c._git, t.R)
        with self.assertRaises(AssertionError) as failure:
            self.selected(ref)
        self.assertNotIsInstance(failure.exception, o.TopologyError)

    def test_frozen_historical_profiles_and_pins_remain_exact(self):
        for path, digest in (('scripts/rc_pretag_ownership_profile.py', '4922466b9eb42d0217d103bf826055dc7db5c56dfaa15d9be5b17f6eb64e6649'),
                (d.PROFILE, '69e058383db6beeaf884a5198b401e412568ebdfaae0dc63215af5b84a473068'),
                (n.PROFILE, '7569005c75c9dae73e61172c6979d5ca8e4057e32250d4d7bffb9a5e65f3c019')):
            self.assertEqual((c.ROOT / path).read_bytes(), c._git('show', t.F + ':' + path, root=self.repo))
            self.assertEqual(hashlib.sha256((c.ROOT / path).read_bytes()).hexdigest(), digest)
        path = 'scripts/rc_pretag_ownership_tests.py'
        self.assertEqual((c.ROOT / path).read_bytes(), c._git('show', t.F + ':' + path, root=self.repo))
        self.assertEqual((len(c.ALLOWED), len(o.CAPS), o.DELTA_LIMIT, d.AMENDMENT_DELTA_LIMIT,
                          n.AMENDMENT_DELTA_LIMIT), (22, 13, 2200, 1100, 1250))
        for ref in (d.X, d.SOURCE, n.F, n.P, t.F):
            expected = n.selected_profile(ref, self.repo, c._git, c._entries, c._feature_profile,
                                          c.RELEASE, c.RELEASE_TREE, c.RELEASE_DOCS)
            self.assertEqual(self.selected(ref), expected)

    def test_exact_f_parent_tree_and_nginx_validation(self):
        self.assertEqual((t.F, t.F_TREE, t.F_PARENTS), ('44b9f9b16f6981297bd1252eb3ab238ae581eccc',
            '99916334cc77fcc22209c99661e40ba1fd2e1276',
            ('310ad16c8aa9cc8182c4b0f6a196184fcf34bc52', '0a2554230a1523b0e6e5b43f0574897f4ed3b8a9')))
        self.assertEqual(tuple(o._parents(t.F, self.repo, c._git)), t.F_PARENTS)
        self.assertEqual(c._git('rev-parse', t.F + '^{tree}', root=self.repo).decode().strip(), t.F_TREE)
        with patch.object(n, 'selected_profile', wraps=n.selected_profile) as legacy:
            self.assertEqual(self.native(t.P), self.source)
            self.assertEqual(legacy.call_args.args[0], t.F)
            self.assertIs(legacy.call_args.args[4], c._feature_profile)
        for anchor in (t.F, t.P):
            def wrong_parents(*args, root):
                if args == ('show', '-s', '--format=%P', anchor): return b'\n'
                return c._git(*args, root=root)
            with patch.object(t, 'two_hop_content') as content, self.assertRaises(o.TopologyError):
                self.selected(self.pure, wrong_parents)
            content.assert_not_called()
            def wrong_tree(*args, root):
                if args == ('rev-parse', anchor + '^{tree}'): return b'0' * 40 + b'\n'
                return c._git(*args, root=root)
            with self.assertRaises(AssertionError): self.native(t.P, wrong_tree)

    def test_native_p_sole_parent_tree_and_seven_path_delta(self):
        self.assertEqual((t.P, t.P_TREE), ('f8d187dfe9fe30e8641c7f8906d615265811c107',
                                         '0989ac3fc24839e0e83a3003abc41fe4f202ac64'))
        self.assertEqual(o._parents(t.P, self.repo, c._git), [t.F])
        self.assertEqual(c._git('rev-parse', t.P + '^{tree}', root=self.repo).decode().strip(), t.P_TREE)
        original = c._entries(t.F, self.repo)
        self.assertEqual((len(original), len(self.source), len(t.SOURCE_PINS)), (1664, 1665, 7))
        self.assertEqual({p for p in self.source if self.source[p] != original.get(p)}, t.SOURCE_PINS.keys())
        self.assertEqual(self.source.keys() - original.keys(), {'tests/cloud-gateway-deployment/test_current_nginx_two_hop.py'})
        self.assertEqual(len(original.keys() - t.SOURCE_PINS.keys()), 1658)
        self.assertTrue(all(self.source[p] == value for p, value in original.items() if p not in t.SOURCE_PINS))
        self.assertEqual(self.native(t.P), self.source)
        for path, (mode, blob, digest, size, lines) in t.SOURCE_PINS.items():
            data = c._git('show', t.P + ':' + path, root=self.repo)
            self.assertEqual((mode, blob, digest, size, lines), ('100644', *o.pin(data), len(data), len(data.splitlines())))
            self.assertEqual(c._git('show', c.authenticated_two_hop.M + ':' + path, root=self.repo), data)

    def test_exact_p_and_one_reviewed_amendment_accept(self):
        self.assertEqual(self.selected(t.P), self.source)
        self.assertEqual(self.selected(self.pure), self.good)
        self.assertEqual(len(self.good), 1670)
        self.assertEqual({p for p in self.good if self.good[p] != self.source.get(p)}, t.AMENDMENT_CAPS.keys())
        self.assertEqual(t.AMENDMENT_PINS.keys(), t.AMENDMENT_CAPS.keys() - {t.PROFILE})
        with self.assertRaises(o.TopologyError):
            n.selected_profile(t.P, self.repo, c._git, c._entries, c._feature_profile,
                               c.RELEASE, c.RELEASE_TREE, c.RELEASE_DOCS)
        self.bad_content(self.source)

    def test_ordered_feature_merge_requires_complete_source_tree(self):
        for source, expected in ((t.P, self.source), (self.pure, self.good)):
            feature = self.commit([t.F, source], expected)
            self.assertEqual(self.selected(feature), expected)
            self.assertEqual(o._parents(feature, self.repo, c._git), [t.F, source])
            self.assertEqual(c._git('rev-parse', feature + '^{tree}', root=self.repo),
                             c._git('rev-parse', source + '^{tree}', root=self.repo))
        self.bad_content(self.source, [t.F, self.pure])
        self.bad_content(self.good, [t.F, t.P])
        self.bad_content(self.changed('scripts/rc_consumer_io.py', b'merge resolution\n'), [t.F, self.pure])

    def test_release_overlay_contains_only_four_exact_documents(self):
        self.assertEqual((t.R, t.R_TREE, t.R_DOCUMENTS), (c.RELEASE, c.RELEASE_TREE, c.RELEASE_DOCS))
        self.assertEqual(len(t.R_DOCUMENTS), 4)
        self.assertEqual(self.selected(self.release), self.overlay)
        self.assertEqual({p for p in self.overlay if self.overlay[p] != self.good[p]}, t.R_DOCUMENTS.keys())
        feature = self.commit([t.F, t.P], self.source)
        self.assertEqual(self.selected(self.commit([t.R, feature], self.source | t.R_DOCUMENTS)),
                         self.source | t.R_DOCUMENTS)

    def test_unknown_missing_and_same_tree_impostor_anchors_reject(self):
        fake_f = self.commit([], c._entries(t.F, self.repo))
        fake_p = self.commit([], self.source)
        fake_r = self.commit([], c._entries(t.R, self.repo))
        foreign = self.commit([], self.good)
        for parents in ([], [foreign], [fake_p], [fake_f, self.pure], ['f' * 40]):
            with self.subTest(parents=parents): self.rejects(parents, self.good)
        self.rejects([], self.source)
        self.rejects([t.F], self.source)
        self.rejects([fake_r, self.feature], self.overlay)
        with patch.object(t, 'two_hop_content') as content, self.assertRaises(o.TopologyError):
            self.selected('f' * 40)
        content.assert_not_called()

    def test_reversed_duplicate_missing_and_extra_parents_reject_before_content(self):
        for parents in ([t.F], [t.P, t.F], [self.pure, t.F], [t.F, t.F], [t.P, t.P],
                        [t.F, self.pure, t.P], [t.F, self.pure, self.pure]):
            with self.subTest(parents=parents): self.rejects(parents, self.good)
        for parents in ([self.feature, t.R], [t.R, self.feature, t.P], [t.R, t.R], [t.R, self.pure]):
            with self.subTest(parents=parents): self.rejects(parents, self.overlay)

    def test_amendment_chains_nested_merges_and_descendants_reject(self):
        for parents in ([self.pure], [self.feature], [t.F, self.feature], [t.F, self.release], [t.P, self.pure]):
            self.rejects(parents, self.good)
        for parents in ([t.R, self.release], [self.release], [t.R, t.P]):
            self.rejects(parents, self.overlay)

    def test_each_native_source_blob_digest_size_and_line_pin_rejects_drift(self):
        for path, row in t.SOURCE_PINS.items():
            data = c._git('show', t.P + ':' + path, root=self.repo)
            for changed in (data + b'\n', b'\0binary\xff\n'):
                with self.subTest(path=path, binary=changed.startswith(b'\0')):
                    self.bad_content(self.changed(path, changed))
            for index, value in ((0, '100755'), (1, self.blob(b'changed source\n')), (2, '0' * 64), (3, row[3] + 1), (4, row[4] + 1)):
                altered = list(row); altered[index] = value
                with self.subTest(path=path, field=index), patch.object(t, 'SOURCE_PINS', t.SOURCE_PINS | {path: tuple(altered)}):
                    with self.assertRaises(AssertionError): self.native(t.P)

    def test_missing_extra_rename_mode_symlink_and_gitlink_entries_reject(self):
        self.assertEqual([p for p, value in self.good.items() if value[0] == '100755'], [d.COLLECTOR])
        for path in (*t.SOURCE_PINS, *t.AMENDMENT_CAPS):
            missing = dict(self.good); missing.pop(path)
            mutations = [missing, missing | {path + '.renamed': self.good[path]}]
            mutations += [self.good | {path: value} for value in
                          (('100755', *self.good[path][1:]), ('120000', 'blob', self.blob(b'target')),
                           ('160000', 'commit', t.P))]
            for changed in mutations:
                with self.subTest(path=path, entry=changed.get(path)): self.bad_content(changed)
        for path in ('unreviewed-extra.py', 'native-evidence.json', *(f'docs/specs/issue40-two-hop-composition/{name}.md'
                     for name in ('sixth', 'seventh', 'eighth'))):
            self.bad_content(self.good | {path: ('100644', 'blob', self.blob(b'unreviewed\n'))})

    def test_every_historical_protected_entry_and_six_version_slots_remain_exact(self):
        t.two_hop_topology(self.pure, self.repo, c._git, t.R)
        self.assertEqual(self.amended(self.pure), self.good)
        original = c._entries(t.F, self.repo)
        bad = self.blob(b'changed protected historical entry\n')
        for path in original.keys() - t.AMENDMENT_CAPS.keys():
            mode = '100644' if original[path][0] == '100755' else '100755'
            for value in (('100644', 'blob', bad), (mode, *original[path][1:])):
                changed = self.good | {path: value}
                with self.subTest(path=path, mode=value[0]), self.assertRaises(AssertionError):
                    self.amended(self.pure, entries=lambda ref, root: changed)
        for path, keys in (('package.json', ('version',)), ('package-lock.json', ('version',)),
                           ('package-lock.json', ('packages', '', 'version')), ('src-tauri/tauri.conf.json', ('version',))):
            data = json.loads(c._git('show', t.F + ':' + path, root=self.repo))
            field = data
            for key in keys[:-1]: field = field[key]
            self.assertEqual(field[keys[-1]], '0.6.0-rc.4')
            field[keys[-1]] = '0.6.0-rc.5'
            self.bad_content(self.changed(path, json.dumps(data).encode()))
        for path, before in (('src-tauri/Cargo.toml', 'version = "0.6.0-rc.4"'),
                             ('src-tauri/Cargo.lock', 'name = "coding-tools-mcp-desktop"\nversion = "0.6.0-rc.4"')):
            data = c._git('show', t.F + ':' + path, root=self.repo).decode()
            self.bad_content(self.changed(path, c._replace_once(data, before, before.replace('rc.4', 'rc.5')).encode()))

    def test_release_document_byte_mode_path_and_deletion_drift_rejects(self):
        for path in (*t.R_DOCUMENTS, 'docs/releases/unreviewed.md', 'scripts/rc_consumer_io.py'):
            for value in (None, ('100644', 'blob', self.blob(b'drift\n')), ('100644', 'blob', self.blob(b'\0binary')),
                          ('100755', 'blob', self.blob(b'drift\n')), ('120000', 'blob', self.blob(b'target'))):
                changed = dict(self.overlay)
                if value is None: changed.pop(path, None)
                else: changed[path] = value
                if changed != self.overlay:
                    with self.subTest(path=path, value=value): self.bad_content(changed, [t.R, self.feature])
            if path in t.R_DOCUMENTS:
                changed = dict(self.overlay); value = changed.pop(path); changed[path + '.renamed'] = value
                self.bad_content(changed, [t.R, self.feature])
        for release, tree, documents in (('f' * 40, t.R_TREE, t.R_DOCUMENTS), (t.R, '0' * 40, t.R_DOCUMENTS),
                                         (t.R, t.R_TREE, {})):
            with self.assertRaises(AssertionError):
                t.selected_profile(self.release, self.repo, c._git, c._entries, c._feature_profile,
                                   release, tree, documents)

    def test_amendment_pins_scope_binary_and_individual_total_budgets_reject(self):
        self.assertEqual(self.amended(self.pure), self.good)
        self.assertEqual((len(t.AMENDMENT_CAPS), len(t.AMENDMENT_PINS), t.AMENDMENT_DELTA_LIMIT), (8, 7, 1300))
        for path, pin in t.AMENDMENT_PINS.items():
            self.bad_content(self.changed(path, c._git('cat-file', 'blob', self.good[path][2], root=self.repo) + b'\n'))
            for altered in (('0' * 40, pin[1]), (pin[0], '0' * 64)):
                with patch.object(t, 'AMENDMENT_PINS', t.AMENDMENT_PINS | {path: altered}), self.assertRaises(AssertionError):
                    self.amended(self.pure)
        for path, (_, diff_cap) in t.AMENDMENT_CAPS.items():
            cap = len(c._git('cat-file', 'blob', self.good[path][2], root=self.repo).splitlines()) - 1
            with patch.object(t, 'AMENDMENT_CAPS', t.AMENDMENT_CAPS | {path: (cap, diff_cap)}), self.assertRaises(AssertionError):
                self.amended(self.pure)
            def oversized_diff(*args, root):
                if args == ('diff', '--numstat', t.P, self.pure, '--', path):
                    return f'{diff_cap + 1}\t0\t{path}\n'.encode()
                return c._git(*args, root=root)
            with self.assertRaises(AssertionError): self.amended(self.pure, git=oversized_diff)
        path = t.PROFILE
        for row in (b'', b'-\t-\t' + path.encode() + b'\n', b'1\t0\n', b'1\t0\twrong\n',
                    b'1\t0\t' + path.encode() + b'\textra\n', b'1\t0\t' + path.encode() + b'\n1\t0\twrong\n'):
            def malformed(*args, root):
                return row if args == ('diff', '--numstat', t.P, self.pure, '--', path) else c._git(*args, root=root)
            with self.assertRaises(AssertionError): self.amended(self.pure, git=malformed)
        data = (c.ROOT / t.PROFILE).read_bytes()
        cap = t.AMENDMENT_CAPS[t.PROFILE][0]
        self.bad_content(self.changed(t.PROFILE, data + b'# line boundary\n' * (cap + 1 - len(data.splitlines()))))
        self.bad_content(self.changed(t.PROFILE, b'\0binary\xff'))
        total = sum(sum(map(int, c._git('diff', '--numstat', t.P, self.pure, '--', p,
                                       root=self.repo).split()[:2])) for p in t.AMENDMENT_CAPS)
        oversized = data + b'# aggregate\n' * (t.AMENDMENT_DELTA_LIMIT + 1 - total)
        with patch.object(t, 'AMENDMENT_CAPS', {p: (10000, 10000) for p in t.AMENDMENT_CAPS}):
            self.bad_content(self.changed(t.PROFILE, oversized))

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
        calls.clear(); t.two_hop_topology(self.pure, self.repo, moving, t.R)
        self.assertTrue(all(args[:3] == ('show', '-s', '--format=%P') for args in calls))

    def test_topology_dispatch_keeps_all_legacy_content_failures_terminal(self):
        for module, name, ref in ((o, 'content', d.X), (d, 'desktop_content', n.F), (n, 'nginx_content', t.F)):
            for error in (AssertionError, o.TopologyError):
                with patch.object(module, name, side_effect=error('terminal content failure')), \
                     patch.object(t, 'two_hop_content') as content:
                    with self.assertRaisesRegex(error, 'terminal content failure'): self.selected(ref)
                    content.assert_not_called()
        for parent, topology in ((o.M, o.topology), (d.SOURCE, d.desktop_topology), (n.P, n.nginx_topology)):
            ref = self.commit([parent], self.good)
            topology(ref, self.repo, c._git, t.R)
            with patch.object(t, 'two_hop_content') as content, self.assertRaises(AssertionError) as failure:
                self.selected(ref)
            self.assertNotIsInstance(failure.exception, o.TopologyError)
            content.assert_not_called()

    def test_unknown_profiles_and_native_release_approval_claims_reject(self):
        self.assertEqual(t.PROFILE_ID, 'engineering/issue40-two-hop-composition-v1')
        for profile in (None, 1, '', 'engineering/issue40-two-hop-composition-v2', 'native', 'release', 'publish'):
            with patch.object(t, 'two_hop_content') as content, self.assertRaises(AssertionError):
                self.selected(self.pure, git=lambda *a, **kw: self.fail('Git ran before profile rejection'), profile=profile)
            content.assert_not_called()
        for path, flags in (('deploy/cloud-gateway/current_nginx_include.py',
                'upstream_reachability_verified applied production_ready real_host_tls_waf_tested publish_approved old_ingress_two_hop_supported'),
                ('tests/cloud-gateway-deployment/run_current_nginx_runtime.py',
                 'authenticated_agent_lifecycle_tested pending_websocket_authenticated production_touched')):
            data = c._git('show', t.P + ':' + path, root=self.repo).decode()
            for flag in flags.split():
                self.assertIn(flag + '=False', data)
                self.bad_content(self.changed(path, data.replace(flag + '=False', flag + '=True').encode()))
        module = ast.parse((c.ROOT / t.PROFILE).read_bytes())
        calls = {getattr(node.func, 'id', getattr(node.func, 'attr', '')) for node in ast.walk(module) if isinstance(node, ast.Call)}
        self.assertFalse(calls & {'open', 'write_bytes', 'write_text', 'Popen', 'run', 'system', 'urlopen', 'dispatch'})
        self.assertEqual(t.AMENDMENT_PINS.keys(), t.AMENDMENT_CAPS.keys() - {t.PROFILE})

    def adapter(self, path):
        frozen = c._git('show', t.F + ':' + path, root=self.repo)
        current = c._git('show', c.authenticated_two_hop.M + ':' + path, root=self.repo)
        self.assertEqual(inverse_adapter(path, current, frozen), frozen)
        for before, _ in FRAGMENTS[path]:
            for replacement in ('', before * 2):
                with self.subTest(path=path, fragment=before[:50], replacement=len(replacement)), self.assertRaises(AssertionError):
                    inverse_adapter(path, current.replace(before.encode(), replacement.encode(), 1), frozen)
        for changed in (current + b'# outside fragment\n', current + b' ', b'\n' + current, current + b'\0', current + b'\xff'):
            with self.assertRaises(AssertionError): inverse_adapter(path, changed, frozen)
        for altered in (frozen + b'\n', frozen[:-1]):
            with self.assertRaises(AssertionError): inverse_adapter(path, current, altered)
        for pin in (('0' * 40, n.AMENDMENT_PINS[path][1]), (n.AMENDMENT_PINS[path][0], '0' * 64)):
            with patch.dict(n.AMENDMENT_PINS, {path: pin}), self.assertRaises(AssertionError): inverse_adapter(path, current, frozen)
        for name, node in methods(current).items():
            text = ast.get_source_segment(current.decode(), node)
            edits = ['', text.replace('def ' + name, 'def renamed_' + name, 1), text + '\n    def added_old_method(self): pass']
            if name not in ALLOWED_METHODS[path]: edits.append(text.replace(':\n', ':\n        pass\n', 1))
            for call in ast.walk(node):
                if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr.startswith('assert'):
                    segment = ast.get_source_segment(current.decode(), call)
                    edits.extend((text.replace(segment, 'None', 1), text.replace(segment, segment.replace(call.func.attr, 'assertTrue', 1) + ' or None', 1)))
            for edit in edits:
                with self.subTest(path=path, method=name), self.assertRaises(AssertionError):
                    inverse_adapter(path, current.replace(text.encode(), edit.encode(), 1), frozen)
        return frozen
    def test_composition_inverse_recovers_exact_f_and_rejects_fragment_drift(self):
        self.adapter(t.COMPOSITION)
    def test_desktop_adapter_inverse_preserves_all_historical_assertions(self):
        self.adapter(t.DESKTOP_TESTS)
    def test_nginx_adapter_inverse_preserves_historical_fixtures_and_budget_negatives(self):
        self.adapter(n.TESTS)
        historical = nt.NginxCompositionTests(); self.addCleanup(historical.doCleanups); historical.setUp()
        self.assertEqual(historical.good, c._entries(t.F, historical.repo))
        self.assertEqual(historical.selected(historical.pure), historical.good)
        self.assertGreater(len((c.ROOT / n.TESTS).read_bytes().splitlines()),
                           len(c._git('show', t.F + ':' + n.TESTS, root=self.repo).splitlines()))
        for path, (_, delta) in n.AMENDMENT_CAPS.items():
            cap = len(c._git('cat-file', 'blob', historical.good[path][2], root=historical.repo).splitlines()) - 1
            with patch.dict(n.AMENDMENT_CAPS, {path: (cap, delta)}), self.assertRaises(AssertionError):
                historical.amended(historical.pure)
        for path in n.SOURCE_PINS:
            historical.bad_content(historical.changed(path, b'corrupted historical source\n'))
        real_git = c._git
        for probe in (('show', '-s', '--format=%P', t.F), ('rev-parse', t.F + '^{tree}')):
            def corrupt(*args, root=c.ROOT):
                return b'0' * 40 + b'\n' if args == probe else real_git(*args, root=root)
            case = nt.NginxCompositionTests(); self.addCleanup(case.doCleanups)
            with patch.object(c, '_git', corrupt), self.assertRaises(AssertionError): case.setUp()
    def test_frozen_187_plus_22_inventory_is_exactly_loaded_and_executed(self):
        all_expected = [prefix + '.' + name for prefix, names in c.EXPECTED_GROUPS.items() for name in names.split()]
        expected = [name for name in all_expected if name.rsplit('.', 1)[0] not in c.authenticated_two_hop.EXPECTED_GROUPS]
        inventory_ids(expected)
        legacy = [name for name in expected if not name.startswith('rc_pretag_two_hop_tests.')]
        self.assertEqual((len(legacy), hashlib.sha256('\n'.join(sorted(legacy)).encode()).hexdigest()),
                         (187, '0544f880134bf01943ecf43a0f5815357bf4283153ba314debb93c55364f2ec9'))
        names = next(iter(t.EXPECTED_GROUPS.values())).split()
        self.assertEqual((len(names), len(set(names))), (22, 22))
        self.assertEqual(set(names), set(unittest.defaultTestLoader.getTestCaseNames(type(self))))
        suite = unittest.defaultTestLoader.discover(str(c.ROOT / 'scripts'), pattern='rc_pretag*_tests.py')
        all_loaded = [case.id() for case in c._flatten(suite)]
        self.assertEqual((len(all_loaded), len(set(all_loaded))), (233, 233)); self.assertEqual(Counter(all_loaded), Counter(all_expected))
        loaded = [name for name in all_loaded if name.rsplit('.', 1)[0] not in c.authenticated_two_hop.EXPECTED_GROUPS]; inventory_ids(loaded)
        self.assertEqual(Counter(loaded), Counter(expected))
        for index, name in enumerate(legacy):
            for altered in (expected[:index] + expected[index + 1:], expected + [name], [x if x != name else x + '_replaced' for x in expected]):
                with self.assertRaises(AssertionError): inventory_ids(altered)
        frozen, current = ast.parse(c._git('show', t.F + ':' + t.COMPOSITION, root=self.repo)), ast.parse((c.ROOT / t.COMPOSITION).read_bytes())
        for name in ('run_inventory', 'InventoryResult', '_flatten', '_git', '_profile_fixture', '_index_entries', '_selected_profile', '_feature_profile'):
            extract = lambda tree: ast.dump(next(node for node in tree.body if getattr(node, 'name', '') == name))
            self.assertEqual(extract(current), extract(frozen))
    def test_old_inner_ingress_and_superseded_source_cannot_replace_native_pins(self):
        path = 'deploy/cloud-gateway/runtime_topology.py'
        old = c._git('show', t.F + ':' + path, root=self.repo)
        self.assertNotEqual(o.pin(old)[0], self.source[path][2])
        self.bad_content(self.changed(path, old))
        self.rejects([t.F], self.source)
        self.rejects([self.commit([], self.source)], self.good)
        for ref in (n.P, t.F):
            self.bad_content(c._entries(ref, self.repo))


if __name__ == '__main__':
    unittest.main()
