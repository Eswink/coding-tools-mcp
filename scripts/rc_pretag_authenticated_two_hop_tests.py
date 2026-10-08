"""Exact authenticated source and guard composition; no local native authority."""
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
import rc_pretag_ownership_profile as o
import rc_pretag_two_hop_profile as t
import rc_pretag_two_hop_tests as tt
import rc_pretag_authenticated_two_hop_profile as a
from rc_pretag_windows_launch_profile import normalize as windows_launch_bytes

FRAGMENTS = {
    'scripts/rc_pretag_composition_tests.py': (
        ('EXPECTED_GROUPS.update(two_hop.EXPECTED_GROUPS)\nassert not (EXPECTED_GROUPS.keys() & authenticated_two_hop.EXPECTED_GROUPS.keys())\nEXPECTED_GROUPS.update(authenticated_two_hop.EXPECTED_GROUPS)\n', 'EXPECTED_GROUPS.update(two_hop.EXPECTED_GROUPS)\n'),
        ('expected = authenticated_two_hop.selected_profile(', 'expected = two_hop.selected_profile('),
        ('import rc_pretag_two_hop_profile as two_hop\nimport rc_pretag_authenticated_two_hop_profile as authenticated_two_hop\n', 'import rc_pretag_two_hop_profile as two_hop\n'),
    ),
    'scripts/rc_pretag_desktop_tests.py': (
        ("        prior_loaded = [name for name in loaded if name.rsplit('.', 1)[0] in previous]\n        self.assertEqual((len(prior_loaded), len(set(prior_loaded))), (209, 209))\n        self.assertEqual((len(loaded), len(set(loaded))), (233, 233))\n", '        self.assertEqual((len(loaded), len(set(loaded))), (209, 209))\n'),
        ('        previous = historical | c.two_hop.EXPECTED_GROUPS\n        self.assertEqual({key: c.EXPECTED_GROUPS[key] for key in previous}, historical | c.two_hop.EXPECTED_GROUPS)\n        self.assertEqual(c.EXPECTED_GROUPS, previous | c.authenticated_two_hop.EXPECTED_GROUPS)\n', '        self.assertEqual(c.EXPECTED_GROUPS, historical | c.two_hop.EXPECTED_GROUPS)\n'),
        ("        current = c._git('show', c.authenticated_two_hop.M + ':' + d.COMPOSITION, root=self.repo).decode()\n", '        current = (c.ROOT / d.COMPOSITION).read_text()\n'),
    ),
    'scripts/rc_pretag_nginx_tests.py': (
        ("        current = c._git('show', c.authenticated_two_hop.M + ':' + n.DESKTOP_TESTS, root=self.repo).decode()\n", '        current = (c.ROOT / n.DESKTOP_TESTS).read_text()\n'),
        ("        current = c._git('show', c.authenticated_two_hop.M + ':' + n.COMPOSITION, root=self.repo).decode()\n", '        current = (c.ROOT / n.COMPOSITION).read_text()\n'),
        ("        prior_loaded = [name for name in loaded if name.rsplit('.', 1)[0] in previous]\n        self.assertEqual((len(prior_loaded), len(set(prior_loaded))), (209, 209))\n        self.assertEqual((len(loaded), len(set(loaded))), (233, 233))\n", '        self.assertEqual((len(loaded), len(set(loaded))), (209, 209))\n'),
        ('        previous = legacy | c.two_hop.EXPECTED_GROUPS\n        self.assertEqual({key: c.EXPECTED_GROUPS[key] for key in previous}, legacy | c.two_hop.EXPECTED_GROUPS)\n        self.assertEqual(c.EXPECTED_GROUPS, previous | c.authenticated_two_hop.EXPECTED_GROUPS)\n', '        self.assertEqual(c.EXPECTED_GROUPS, legacy | c.two_hop.EXPECTED_GROUPS)\n'),
    ),
    'scripts/rc_pretag_two_hop_tests.py': (
        ("        all_loaded = [case.id() for case in c._flatten(suite)]\n        self.assertEqual((len(all_loaded), len(set(all_loaded))), (233, 233)); self.assertEqual(Counter(all_loaded), Counter(all_expected))\n        loaded = [name for name in all_loaded if name.rsplit('.', 1)[0] not in c.authenticated_two_hop.EXPECTED_GROUPS]; inventory_ids(loaded)\n", '        loaded = [case.id() for case in c._flatten(suite)]; inventory_ids(loaded)\n'),
        ("        all_expected = [prefix + '.' + name for prefix, names in c.EXPECTED_GROUPS.items() for name in names.split()]\n        expected = [name for name in all_expected if name.rsplit('.', 1)[0] not in c.authenticated_two_hop.EXPECTED_GROUPS]\n", "        expected = [prefix + '.' + name for prefix, names in c.EXPECTED_GROUPS.items() for name in names.split()]\n"),
        ("        current = c._git('show', c.authenticated_two_hop.M + ':' + path, root=self.repo)\n", '        current = (c.ROOT / path).read_bytes()\n'),
        ("            cap = len(c._git('cat-file', 'blob', self.good[path][2], root=self.repo).splitlines()) - 1\n", '            cap = len((c.ROOT / path).read_bytes().splitlines()) - 1\n'),
        ("            self.bad_content(self.changed(path, c._git('cat-file', 'blob', self.good[path][2], root=self.repo) + b'\\n'))\n", "            self.bad_content(self.changed(path, (c.ROOT / path).read_bytes() + b'\\n'))\n"),
        ("            self.assertEqual(c._git('show', c.authenticated_two_hop.M + ':' + path, root=self.repo), data)\n", '            self.assertEqual((c.ROOT / path).read_bytes(), data)\n'),
        ("        self.assertEqual(tuple(o._parents(c.authenticated_two_hop.M, self.repo, c._git)), c.authenticated_two_hop.M_PARENTS)\n        self.assertEqual(c._git('rev-parse', c.authenticated_two_hop.M + '^{tree}', root=self.repo).decode().strip(), c.authenticated_two_hop.M_TREE)\n        frozen = self.selected(c.authenticated_two_hop.M)\n        self.good = self.source | {p: frozen[p] for p in t.AMENDMENT_CAPS}\n", "        self.good = self.source | {p: ('100644', 'blob', self.blob((c.ROOT / p).read_bytes()))\n                                   for p in t.AMENDMENT_CAPS}\n"),
    ),
}
ALLOWED_METHODS = {'scripts/rc_pretag_composition_tests.py': {'test_exact_tracked_tree_modes_and_scope'}, 'scripts/rc_pretag_desktop_tests.py': {'test_composition_adapter_reconstructs_frozen_x', 'test_legacy_inventory_and_new_named_inventory_are_exact'}, 'scripts/rc_pretag_nginx_tests.py': {'test_desktop_fixture_adapter_preserves_historical_assertions', 'test_frozen_167_plus_20_inventory_has_exact_loaded_and_executed_ids', 'test_composition_adapter_inverse_recovers_exact_f'}, 'scripts/rc_pretag_two_hop_tests.py': {'setUp', 'test_native_p_sole_parent_tree_and_seven_path_delta', 'adapter', 'test_frozen_187_plus_22_inventory_is_exactly_loaded_and_executed', 'test_amendment_pins_scope_binary_and_individual_total_budgets_reject'}}
PROFILE_DIGESTS = {'scripts/rc_pretag_ownership_profile.py': '4922466b9eb42d0217d103bf826055dc7db5c56dfaa15d9be5b17f6eb64e6649', 'scripts/rc_pretag_desktop_profile.py': '69e058383db6beeaf884a5198b401e412568ebdfaae0dc63215af5b84a473068', 'scripts/rc_pretag_nginx_profile.py': '7569005c75c9dae73e61172c6979d5ca8e4057e32250d4d7bffb9a5e65f3c019', 'scripts/rc_pretag_two_hop_profile.py': '669a55024c3bbaa267ece2548b8ee3ecdddd66a91f35e249e8ea419ac4469f14'}
SOURCE_PATHS = {'src-tauri/src/tools/cloud_host/live/wss_two_hop_support.rs', 'tests/cloud-gateway-deployment/run_current_nginx_agent.py', 'services/cloud-gateway/tests/host_agent_support/relay.py', 'docs/deployment/current-nginx-include.md', 'tests/cloud-gateway-deployment/container_fixture.py', 'docs/specs/issue40-authenticated-two-hop/tasks.md', 'tests/cloud-gateway-deployment/test_current_nginx_two_hop.py', 'docs/specs/issue40-authenticated-two-hop/design.md', '.github/workflows/issue40-current-nginx-include.yml', 'docs/specs/issue40-authenticated-two-hop/requirements.md', 'src-tauri/src/tools/cloud_host/live/wss_two_hop_tests.rs', 'src-tauri/src/tools/cloud_host/live/wss_tests.rs', 'src-tauri/Cargo.toml'}

def methods(data):
    owner = next(node for node in ast.parse(data).body if isinstance(node, ast.ClassDef))
    return {node.name: node for node in owner.body if isinstance(node, ast.FunctionDef)}


def inverse_adapter(path, current, frozen):
    assert o.pin(frozen) == t.AMENDMENT_PINS[path], 'historical adapter pin'
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
    assert len(ids) == len(set(ids)) == 233
    assert hashlib.sha256('\n'.join(sorted(ids)).encode()).hexdigest() == '7103bfa9167d9ec365ab7a6e111de4de226bfd70b7e578cef74d85d567d67765'


class AuthenticatedTwoHopCompositionTests(unittest.TestCase):
    def setUp(self):
        self.repo, _, self.commit, self.blob = self.enterContext(c._profile_fixture())
        self.source = c._entries(a.P, self.repo)
        self.assertEqual(tuple(o._parents(c.publication.N, self.repo, c._git)), c.publication.N_PARENTS)
        self.assertEqual(c._git('rev-parse', c.publication.N + '^{tree}', root=self.repo).decode().strip(), c.publication.N_TREE)
        frozen = self.selected(c.publication.N)
        self.good = self.source | {p: frozen[p] for p in a.AMENDMENT_CAPS}
        self.pure = self.commit([a.P], self.good)
        self.feature = self.commit([a.M, self.pure], self.good)
        self.overlay = self.good | c.RELEASE_DOCS
        self.release = self.commit([a.R, self.feature], self.overlay)
        a.authenticated_two_hop_topology(self.pure, self.repo, c._git, a.R)

    def selected(self, ref, git=c._git, **kwargs):
        return a.selected_profile(ref, self.repo, git, c._entries, c._feature_profile,
                                  c.RELEASE, c.RELEASE_TREE, c.RELEASE_DOCS, **kwargs)

    def native(self, ref, git=c._git):
        return a.authenticated_two_hop_content(ref, self.repo, git, c._entries, c._feature_profile,
                               c.RELEASE, c.RELEASE_TREE, c.RELEASE_DOCS)

    def amended(self, ref, entries=c._entries, git=c._git):
        return a.amendment_content(ref, self.source, self.repo, git, entries)

    def changed(self, path, data, mode='100644', base=None):
        return (self.good if base is None else base) | {path: (mode, 'blob', self.blob(data))}

    def rejects(self, parents, expected):
        ref = self.commit(parents, expected)
        self.assertEqual(c._entries(ref, self.repo), expected)
        self.assertEqual(self.native(a.P), self.source)
        if expected == self.source:
            self.assertEqual(self.native(ref), expected)
        elif expected == self.good:
            self.assertEqual(self.amended(ref), expected)
        else:
            self.assertEqual(expected, self.overlay)
            self.assertEqual(self.amended(self.pure), self.good)
            self.assertEqual(o.release_content(ref, self.good, self.repo, c._git, c._entries,
                                              a.R, a.R_TREE, a.R_DOCUMENTS), expected)
        with self.assertRaises(o.TopologyError):
            a.authenticated_two_hop_topology(ref, self.repo, c._git, a.R)
        with ExitStack() as stack:
            stopped = [stack.enter_context(patch.object(module, name, side_effect=AssertionError('content ran')))
                       for module, name in ((o, 'content'), (o, 'release_content'), (d, 'desktop_content'),
                           (d, 'amendment_content'), (n, 'nginx_content'), (n, 'amendment_content'),
                           (t, 'two_hop_content'), (t, 'amendment_content'),
                           (a, 'authenticated_two_hop_content'), (a, 'amendment_content'))]
            with self.assertRaises(o.TopologyError):
                self.selected(ref)
            for action in stopped:
                action.assert_not_called()

    def bad_content(self, entries, parents=None):
        ref = self.commit([a.P] if parents is None else parents, entries)
        a.authenticated_two_hop_topology(ref, self.repo, c._git, a.R)
        with self.assertRaises(AssertionError) as failure:
            self.selected(ref)
        self.assertNotIsInstance(failure.exception, o.TopologyError)

    def test_frozen_four_profiles_and_pins_remain_exact(self):
        for path, digest in PROFILE_DIGESTS.items():
            data = (c.ROOT / path).read_bytes()
            self.assertEqual(data, c._git('show', a.M + ':' + path, root=self.repo))
            self.assertEqual(hashlib.sha256(data).hexdigest(), digest)
        from rc_pretag_publication_tests import inverse_ownership
        path = 'scripts/rc_pretag_ownership_tests.py'
        frozen = c._git('show', a.M + ':' + path, root=self.repo)
        self.assertEqual(inverse_ownership((c.ROOT / path).read_bytes(), frozen), frozen)
        self.assertEqual((len(c.ALLOWED), len(o.CAPS), o.DELTA_LIMIT, d.AMENDMENT_DELTA_LIMIT,
                          n.AMENDMENT_DELTA_LIMIT, t.AMENDMENT_DELTA_LIMIT), (22, 13, 2200, 1100, 1250, 1300))
        for ref in (d.X, d.SOURCE, n.F, n.P, t.F, t.P, a.M):
            expected = t.selected_profile(ref, self.repo, c._git, c._entries, c._feature_profile,
                                          c.RELEASE, c.RELEASE_TREE, c.RELEASE_DOCS)
            self.assertEqual(self.selected(ref), expected)

    def test_exact_m_parent_tree_and_two_hop_validation(self):
        self.assertEqual((a.M, a.M_TREE, a.M_PARENTS), ('a88be4901623f7c8629b93df984166587253f0be',
            '246213487851c01a6def74b7519e58a6d709c180',
            ('44b9f9b16f6981297bd1252eb3ab238ae581eccc', '3a606e06b0bc0ee834ea4c7021652e9e60aac7f2')))
        with patch.object(t, 'selected_profile', wraps=t.selected_profile) as legacy:
            self.assertEqual(self.native(a.P), self.source)
            self.assertEqual(legacy.call_args.args[0], a.M)
            self.assertIs(legacy.call_args.args[4], c._feature_profile)
        for anchor in (a.M, a.P):
            def wrong_parents(*args, root):
                return b'\n' if args == ('show', '-s', '--format=%P', anchor) else c._git(*args, root=root)
            with patch.object(a, 'authenticated_two_hop_content') as content, self.assertRaises(o.TopologyError):
                self.selected(self.pure, wrong_parents)
            content.assert_not_called()
            def wrong_tree(*args, root):
                return b'0' * 40 + b'\n' if args == ('rev-parse', anchor + '^{tree}') else c._git(*args, root=root)
            with self.assertRaises(AssertionError): self.native(a.P, wrong_tree)

    def test_native_p_sole_parent_tree_and_thirteen_path_delta(self):
        self.assertEqual(o._parents(a.P, self.repo, c._git), [a.M])
        self.assertEqual(c._git('rev-parse', a.P + '^{tree}', root=self.repo).decode().strip(), a.P_TREE)
        original = c._entries(a.M, self.repo)
        self.assertEqual((len(original), len(self.source), len(a.SOURCE_PINS)), (1670, 1676, 13))
        self.assertEqual(set(a.SOURCE_PINS), SOURCE_PATHS)
        self.assertEqual({p for p in self.source if self.source[p] != original.get(p)}, SOURCE_PATHS)
        self.assertEqual((len(self.source.keys() - original.keys()), len(original.keys() - SOURCE_PATHS)), (6, 1663))
        self.assertTrue(all(self.source[p] == value for p, value in original.items() if p not in SOURCE_PATHS))
        self.assertEqual(self.native(a.P), self.source)
        for path, (mode, blob, digest, size, lines) in a.SOURCE_PINS.items():
            data = c._git('show', a.P + ':' + path, root=self.repo)
            self.assertEqual((mode, blob, digest, size, lines), ('100644', *o.pin(data), len(data), len(data.splitlines())))
            self.assertEqual(windows_launch_bytes(path, (c.ROOT / path).read_bytes()), data)

    def test_exact_source_p_and_amendment_a_bind_without_p_candidate(self):
        self.assertEqual(self.native(a.P), self.source)
        self.assertEqual(self.selected(self.pure), self.good)
        self.assertEqual(len(self.good), 1678)
        self.assertEqual({p for p in self.good if self.good[p] != self.source.get(p)}, a.AMENDMENT_CAPS.keys())
        self.assertEqual(a.AMENDMENT_PINS.keys(), a.AMENDMENT_CAPS.keys() - {a.PROFILE})
        for ref in (a.P, self.commit([a.M, a.P], self.source)):
            with patch.object(a, 'authenticated_two_hop_content') as content, self.assertRaises(o.TopologyError): self.selected(ref)
            content.assert_not_called()
        with self.assertRaises(o.TopologyError):
            t.selected_profile(self.pure, self.repo, c._git, c._entries, c._feature_profile,
                               c.RELEASE, c.RELEASE_TREE, c.RELEASE_DOCS)
        self.bad_content(self.source)

    def test_ordered_feature_merge_requires_complete_source_tree(self):
        self.assertEqual(self.selected(self.feature), self.good)
        self.assertEqual(o._parents(self.feature, self.repo, c._git), [a.M, self.pure])
        self.assertEqual(c._git('rev-parse', self.feature + '^{tree}', root=self.repo),
                         c._git('rev-parse', self.pure + '^{tree}', root=self.repo))
        self.bad_content(self.source, [a.M, self.pure])
        self.rejects([a.M, a.P], self.good)
        self.bad_content(self.changed('scripts/rc_consumer_io.py', b'merge resolution\n'), [a.M, self.pure])

    def test_release_overlay_contains_only_four_exact_documents(self):
        self.assertEqual((a.R, a.R_TREE, a.R_DOCUMENTS), (c.RELEASE, c.RELEASE_TREE, c.RELEASE_DOCS))
        self.assertEqual(len(a.R_DOCUMENTS), 4)
        self.assertEqual(self.selected(self.release), self.overlay)
        self.assertEqual({p for p in self.overlay if self.overlay[p] != self.good[p]}, a.R_DOCUMENTS.keys())

    def test_unknown_missing_and_same_tree_impostor_anchors_reject(self):
        fake_f = self.commit([], c._entries(a.M, self.repo))
        fake_p = self.commit([], self.source)
        fake_r = self.commit([], c._entries(a.R, self.repo))
        foreign = self.commit([], self.good)
        for parents in ([], [foreign], [fake_p], [fake_f, self.pure], ['f' * 40]):
            with self.subTest(parents=parents): self.rejects(parents, self.good)
        self.rejects([], self.source)
        self.rejects([a.M], self.source)
        self.rejects([fake_r, self.feature], self.overlay)
        with patch.object(a, 'authenticated_two_hop_content') as content, self.assertRaises(o.TopologyError):
            self.selected('f' * 40)
        content.assert_not_called()

    def test_reversed_duplicate_missing_and_extra_parents_reject_before_content(self):
        for parents in ([a.M], [a.P, a.M], [self.pure, a.M], [a.M, a.M], [a.P, a.P],
                        [a.M, self.pure, a.P], [a.M, self.pure, self.pure]):
            with self.subTest(parents=parents): self.rejects(parents, self.good)
        for parents in ([self.feature, a.R], [a.R, self.feature, a.P], [a.R, a.R], [a.R, self.pure]):
            with self.subTest(parents=parents): self.rejects(parents, self.overlay)

    def test_amendment_chains_nested_merges_and_descendants_reject(self):
        for parents in ([self.pure], [self.feature], [a.M, self.feature], [a.M, self.release], [a.P, self.pure]):
            self.rejects(parents, self.good)
        for parents in ([a.R, self.release], [self.release], [a.R, a.P]):
            self.rejects(parents, self.overlay)

    def test_each_native_source_blob_digest_size_and_line_pin_rejects_drift(self):
        for path, row in a.SOURCE_PINS.items():
            data = c._git('show', a.P + ':' + path, root=self.repo)
            for changed in (data + b'\n', b'\0binary\xff\n'):
                with self.subTest(path=path, binary=changed.startswith(b'\0')):
                    self.bad_content(self.changed(path, changed))
            for index, value in ((0, '100755'), (1, self.blob(b'changed source\n')), (2, '0' * 64), (3, row[3] + 1), (4, row[4] + 1)):
                altered = list(row); altered[index] = value
                with self.subTest(path=path, field=index), patch.object(a, 'SOURCE_PINS', a.SOURCE_PINS | {path: tuple(altered)}):
                    with self.assertRaises(AssertionError): self.native(a.P)

    def test_missing_extra_rename_mode_symlink_and_gitlink_entries_reject(self):
        self.assertEqual([p for p, value in self.good.items() if value[0] == '100755'], [d.COLLECTOR])
        for path in (*a.SOURCE_PINS, *a.AMENDMENT_CAPS):
            missing = dict(self.good); missing.pop(path)
            mutations = [missing, missing | {path + '.renamed': self.good[path]}]
            mutations += [self.good | {path: value} for value in
                          (('100755', *self.good[path][1:]), ('120000', 'blob', self.blob(b'target')),
                           ('160000', 'commit', a.P))]
            for changed in mutations:
                with self.subTest(path=path, entry=changed.get(path)): self.bad_content(changed)
        for path in ('unreviewed-extra.py', 'native-evidence.json', *(f'docs/specs/issue40-two-hop-composition/{name}.md'
                     for name in ('sixth', 'seventh', 'eighth'))):
            self.bad_content(self.good | {path: ('100644', 'blob', self.blob(b'unreviewed\n'))})

    def test_historical_protected_entries_and_six_version_slots_remain_exact(self):
        a.authenticated_two_hop_topology(self.pure, self.repo, c._git, a.R)
        self.assertEqual(self.amended(self.pure), self.good)
        original = c._entries(a.M, self.repo)
        bad = self.blob(b'changed protected historical entry\n')
        for path in original.keys() - a.AMENDMENT_CAPS.keys():
            mode = '100644' if original[path][0] == '100755' else '100755'
            for value in (('100644', 'blob', bad), (mode, *original[path][1:])):
                changed = self.good | {path: value}
                with self.subTest(path=path, mode=value[0]), self.assertRaises(AssertionError):
                    self.amended(self.pure, entries=lambda ref, root: changed)
        for path, keys in (('package.json', ('version',)), ('package-lock.json', ('version',)),
                           ('package-lock.json', ('packages', '', 'version')), ('src-tauri/tauri.conf.json', ('version',))):
            data = json.loads(c._git('show', a.M + ':' + path, root=self.repo))
            field = data
            for key in keys[:-1]: field = field[key]
            self.assertEqual(field[keys[-1]], '0.6.0-rc.4')
            field[keys[-1]] = '0.6.0-rc.5'
            self.bad_content(self.changed(path, json.dumps(data).encode()))
        for path, before in (('src-tauri/Cargo.toml', 'version = "0.6.0-rc.4"'),
                             ('src-tauri/Cargo.lock', 'name = "coding-tools-mcp-desktop"\nversion = "0.6.0-rc.4"')):
            data = c._git('show', a.M + ':' + path, root=self.repo).decode()
            self.bad_content(self.changed(path, c._replace_once(data, before, before.replace('rc.4', 'rc.5')).encode()))

    def test_release_document_byte_mode_path_and_deletion_drift_rejects(self):
        for path in (*a.R_DOCUMENTS, 'docs/releases/unreviewed.md', 'scripts/rc_consumer_io.py'):
            for value in (None, ('100644', 'blob', self.blob(b'drift\n')), ('100644', 'blob', self.blob(b'\0binary')),
                          ('100755', 'blob', self.blob(b'drift\n')), ('120000', 'blob', self.blob(b'target'))):
                changed = dict(self.overlay)
                if value is None: changed.pop(path, None)
                else: changed[path] = value
                if changed != self.overlay:
                    with self.subTest(path=path, value=value): self.bad_content(changed, [a.R, self.feature])
            if path in a.R_DOCUMENTS:
                changed = dict(self.overlay); value = changed.pop(path); changed[path + '.renamed'] = value
                self.bad_content(changed, [a.R, self.feature])
        for release, tree, documents in (('f' * 40, a.R_TREE, a.R_DOCUMENTS), (a.R, '0' * 40, a.R_DOCUMENTS),
                                         (a.R, a.R_TREE, {})):
            with self.assertRaises(AssertionError):
                a.selected_profile(self.release, self.repo, c._git, c._entries, c._feature_profile,
                                   release, tree, documents)

    def test_amendment_pins_scope_binary_and_individual_total_budgets_reject(self):
        self.assertEqual(self.amended(self.pure), self.good)
        self.assertEqual((len(a.AMENDMENT_CAPS), len(a.AMENDMENT_PINS), a.AMENDMENT_DELTA_LIMIT), (6, 5, 900))
        self.assertEqual((len(a.SOURCE_CAPS), a.SOURCE_DELTA_LIMIT), (13, 2200))
        for path, pin in a.AMENDMENT_PINS.items():
            self.bad_content(self.changed(path, c._git('show', c.publication.N + ':' + path, root=self.repo) + b'\n'))
            for altered in (('0' * 40, pin[1]), (pin[0], '0' * 64)):
                with patch.object(a, 'AMENDMENT_PINS', a.AMENDMENT_PINS | {path: altered}), self.assertRaises(AssertionError): self.amended(self.pure)
        for name, baseline, ref, probe in (('SOURCE_CAPS', a.M, a.P, self.native), ('AMENDMENT_CAPS', a.P, self.pure, self.amended)):
            caps = getattr(a, name); entries = c._entries(ref, self.repo)
            for path, (_, diff_cap) in caps.items():
                cap = len(c._git('cat-file', 'blob', entries[path][2], root=self.repo).splitlines()) - 1
                with patch.object(a, name, caps | {path: (cap, diff_cap)}), self.assertRaises(AssertionError): probe(ref)
                def oversized(*args, root):
                    return f'{diff_cap + 1}\t0\t{path}\n'.encode() if args == ('diff', '--numstat', baseline, ref, '--', path) else c._git(*args, root=root)
                with self.assertRaises(AssertionError): probe(ref, git=oversized)
            for row in (b'', b'-\t-\t' + path.encode() + b'\n', b'1\t0\n', b'1\t0\twrong\n',
                        b'1\t0\t' + path.encode() + b'\textra\n', b'1\t0\t' + path.encode() + b'\n1\t0\twrong\n'):
                def malformed(*args, root):
                    return row if args == ('diff', '--numstat', baseline, ref, '--', path) else c._git(*args, root=root)
                with self.assertRaises(AssertionError): probe(ref, git=malformed)
            def aggregate(*args, root):
                if len(args) == 6 and args[:5] == ('diff', '--numstat', baseline, ref, '--') and args[5] in caps:
                    return f'{caps[args[5]][1]}\t0\t{args[5]}\n'.encode()
                return c._git(*args, root=root)
            with self.assertRaisesRegex(AssertionError, 'delta_budget'): probe(ref, git=aggregate)
        data = (c.ROOT / a.PROFILE).read_bytes(); cap = a.AMENDMENT_CAPS[a.PROFILE][0]
        self.bad_content(self.changed(a.PROFILE, data + b'# line boundary\n' * (cap + 1 - len(data.splitlines()))))
        self.bad_content(self.changed(a.PROFILE, b'\0binary\xff'))

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
        calls.clear(); a.authenticated_two_hop_topology(self.pure, self.repo, moving, a.R)
        self.assertTrue(all(args[:3] == ('show', '-s', '--format=%P') for args in calls))

    def test_topology_dispatch_keeps_all_legacy_content_failures_terminal(self):
        for module, name, ref in ((o, 'content', d.X), (d, 'desktop_content', n.F),
                                  (n, 'nginx_content', t.F), (t, 'two_hop_content', a.M)):
            for error in (AssertionError, o.TopologyError):
                with patch.object(module, name, side_effect=error('terminal content failure')), \
                     patch.object(a, 'authenticated_two_hop_content') as content:
                    with self.assertRaisesRegex(error, 'terminal content failure'): self.selected(ref)
                    content.assert_not_called()
        for parent, topology in ((o.M, o.topology), (d.SOURCE, d.desktop_topology),
                                  (n.P, n.nginx_topology), (t.P, t.two_hop_topology)):
            ref = self.commit([parent], self.good); topology(ref, self.repo, c._git, a.R)
            with patch.object(a, 'authenticated_two_hop_content') as content, self.assertRaises(AssertionError) as failure:
                self.selected(ref)
            self.assertNotIsInstance(failure.exception, o.TopologyError); content.assert_not_called()

    def test_unknown_profiles_and_native_release_approval_claims_reject(self):
        self.assertEqual(a.PROFILE_ID, 'engineering/issue40-authenticated-two-hop-composition-v1')
        for profile in (None, 1, '', 'engineering/issue40-authenticated-two-hop-composition-v2', 'native', 'release', 'publish'):
            with patch.object(a, 'authenticated_two_hop_content') as content, self.assertRaises(AssertionError):
                self.selected(self.pure, git=lambda *a, **kw: self.fail('Git ran before profile rejection'), profile=profile)
            content.assert_not_called()
        for path, flags in (('deploy/cloud-gateway/current_nginx_include.py',
                'upstream_reachability_verified applied production_ready real_host_tls_waf_tested publish_approved old_ingress_two_hop_supported'),
                ('tests/cloud-gateway-deployment/run_current_nginx_runtime.py',
                 'authenticated_agent_lifecycle_tested pending_websocket_authenticated production_touched')):
            data = c._git('show', a.P + ':' + path, root=self.repo).decode()
            for flag in flags.split():
                self.assertIn(flag + '=False', data)
                self.bad_content(self.changed(path, data.replace(flag + '=False', flag + '=True').encode()))
        module = ast.parse((c.ROOT / a.PROFILE).read_bytes())
        calls = {getattr(node.func, 'id', getattr(node.func, 'attr', '')) for node in ast.walk(module) if isinstance(node, ast.Call)}
        self.assertFalse(calls & {'open', 'write_bytes', 'write_text', 'Popen', 'run', 'system', 'urlopen', 'dispatch'})
        self.assertEqual(a.AMENDMENT_PINS.keys(), a.AMENDMENT_CAPS.keys() - {a.PROFILE})

    def adapter(self, path):
        frozen = c._git('show', a.M + ':' + path, root=self.repo)
        current = c._git('show', c.publication.N + ':' + path, root=self.repo)
        self.assertEqual(inverse_adapter(path, current, frozen), frozen)
        for before, _ in FRAGMENTS[path]:
            for replacement in ('', before * 2):
                with self.subTest(path=path, fragment=before[:50], replacement=len(replacement)), self.assertRaises(AssertionError):
                    inverse_adapter(path, current.replace(before.encode(), replacement.encode(), 1), frozen)
        for changed in (current + b'# outside fragment\n', current + b' ', b'\n' + current, current + b'\0', current + b'\xff'):
            with self.assertRaises(AssertionError): inverse_adapter(path, changed, frozen)
        for altered in (frozen + b'\n', frozen[:-1]):
            with self.assertRaises(AssertionError): inverse_adapter(path, current, altered)
        for pin in (('0' * 40, t.AMENDMENT_PINS[path][1]), (t.AMENDMENT_PINS[path][0], '0' * 64)):
            with patch.dict(t.AMENDMENT_PINS, {path: pin}), self.assertRaises(AssertionError): inverse_adapter(path, current, frozen)
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

    def test_composition_inverse_recovers_exact_m_and_rejects_fragment_drift(self):
        self.adapter(a.COMPOSITION)

    def test_desktop_adapter_inverse_preserves_all_historical_assertions(self):
        self.adapter(a.DESKTOP_TESTS)

    def test_nginx_adapter_inverse_preserves_all_historical_assertions(self):
        self.adapter(a.NGINX_TESTS)

    def test_frozen_209_plus_24_inventory_is_exactly_loaded_and_executed(self):
        all_expected = [prefix + '.' + name for prefix, names in c.EXPECTED_GROUPS.items() for name in names.split()]
        expected = [name for name in all_expected if name.rsplit('.', 1)[0] not in (c.publication.EXPECTED_GROUPS | c.publication.JOIN_ONCE_GROUPS)]
        inventory_ids(expected)
        legacy = [name for name in expected if not name.startswith('rc_pretag_authenticated_two_hop_tests.')]
        self.assertEqual((len(legacy), hashlib.sha256('\n'.join(sorted(legacy)).encode()).hexdigest()),
                         (209, '37ccb924975855074b8687a9eefb6ac0342bad4fa4c13b7e84b9e96e11e93695'))
        names = next(iter(a.EXPECTED_GROUPS.values())).split()
        self.assertEqual((len(names), len(set(names))), (24, 24))
        self.assertEqual(set(names), set(unittest.defaultTestLoader.getTestCaseNames(type(self))))
        suite = unittest.defaultTestLoader.discover(str(c.ROOT / 'scripts'), pattern='rc_pretag*_tests.py')
        all_loaded = [case.id() for case in c._flatten(suite)]
        self.assertEqual((len(all_loaded), len(set(all_loaded))), (303, 303))
        self.assertEqual(Counter(all_loaded), Counter(all_expected))
        loaded = [name for name in all_loaded if name.rsplit('.', 1)[0] not in (c.publication.EXPECTED_GROUPS | c.publication.JOIN_ONCE_GROUPS)]; inventory_ids(loaded)
        self.assertEqual(Counter(loaded), Counter(expected))
        for index, name in enumerate(legacy):
            for altered in (expected[:index] + expected[index + 1:], expected + [name], [x if x != name else x + '_replaced' for x in expected]):
                with self.assertRaises(AssertionError): inventory_ids(altered)
        frozen, current = ast.parse(c._git('show', a.M + ':' + a.COMPOSITION, root=self.repo)), ast.parse((c.ROOT / a.COMPOSITION).read_bytes())
        for name in ('run_inventory', 'InventoryResult', '_flatten', '_git', '_profile_fixture', '_index_entries', '_selected_profile', '_feature_profile'):
            extract = lambda tree: ast.dump(next(node for node in tree.body if getattr(node, 'name', '') == name))
            self.assertEqual(extract(current), extract(frozen))

    def test_historical_unauthenticated_proof_cannot_replace_authenticated_source(self):
        original = c._entries(a.M, self.repo)
        for path in a.SOURCE_PINS:
            changed = dict(self.good)
            if path in original: changed[path] = original[path]
            else: changed.pop(path)
            self.assertNotEqual(changed, self.good); self.bad_content(changed)
        for ref in (t.P, a.M): self.bad_content(c._entries(ref, self.repo))
        self.rejects([a.M], self.source)

    def test_two_hop_adapter_preserves_source_fixtures_and_budget_negatives(self):
        self.adapter(a.TWO_HOP_TESTS)
        historical = tt.TwoHopCompositionTests(); self.addCleanup(historical.doCleanups); historical.setUp()
        self.assertEqual(historical.good, c._entries(a.M, historical.repo))
        self.assertEqual(historical.selected(historical.pure), historical.good)
        self.assertGreater(len((c.ROOT / a.TWO_HOP_TESTS).read_bytes().splitlines()),
                           len(c._git('show', a.M + ':' + a.TWO_HOP_TESTS, root=self.repo).splitlines()))
        for path, (_, delta) in t.AMENDMENT_CAPS.items():
            cap = len(c._git('cat-file', 'blob', historical.good[path][2], root=historical.repo).splitlines()) - 1
            with patch.dict(t.AMENDMENT_CAPS, {path: (cap, delta)}), self.assertRaises(AssertionError): historical.amended(historical.pure)
        for path in t.SOURCE_PINS: historical.bad_content(historical.changed(path, b'corrupted historical source\n'))
        real_git = c._git
        for probe in (('show', '-s', '--format=%P', a.M), ('rev-parse', a.M + '^{tree}')):
            def corrupt(*args, root=c.ROOT):
                return b'0' * 40 + b'\n' if args == probe else real_git(*args, root=root)
            case = tt.TwoHopCompositionTests(); self.addCleanup(case.doCleanups)
            with patch.object(c, '_git', corrupt), self.assertRaises(AssertionError): case.setUp()

    def test_single_publish_candidate_keeps_native_and_validator_identity_separate(self):
        self.assertEqual({p: self.good[p] for p in a.SOURCE_PINS}, {p: self.source[p] for p in a.SOURCE_PINS})
        for path in (*a.SOURCE_PINS, *a.AMENDMENT_PINS):
            changed = self.changed(path, c._git('cat-file', 'blob', self.good[path][2], root=self.repo) + b'\n')
            self.bad_content(changed)


if __name__ == '__main__':
    unittest.main()
