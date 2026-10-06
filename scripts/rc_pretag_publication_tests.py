"""Frozen publication composition tests; modeled fixtures confer no release authority."""
import ast
from collections import Counter
from contextlib import ExitStack
import hashlib
import os
import unittest
from unittest.mock import patch

import rc_pretag_composition_tests as c
import rc_pretag_ownership_profile as o
import rc_pretag_desktop_profile as d
import rc_pretag_nginx_profile as n
import rc_pretag_two_hop_profile as t
import rc_pretag_authenticated_two_hop_profile as a
import rc_pretag_authenticated_two_hop_tests as at
import rc_pretag_publication_profile as p

FRAGMENTS = {
    'scripts/rc_pretag_composition_tests.py': (
        ('            data = (ROOT / path).read_bytes()\n            if path in publication.TIMEOUT_BASE_PINS: data = publication.timeout_inverse(path, data)\n            self.assertEqual((_blob(data), hashlib.sha256(data).hexdigest()), (blob, sha256), path)', '            data = (ROOT / path).read_bytes()\n            self.assertEqual((_blob(data), hashlib.sha256(data).hexdigest()), (blob, sha256), path)'),
        ('        current = publication.timeout_inverse(CHECKS, (ROOT / CHECKS).read_bytes())\n', '        current = (ROOT / CHECKS).read_bytes()\n'),
        ('import rc_pretag_authenticated_two_hop_profile as authenticated_two_hop\nimport rc_pretag_publication_profile as publication\n', 'import rc_pretag_authenticated_two_hop_profile as authenticated_two_hop\n'),
        ('expected = publication.selected_profile(', 'expected = authenticated_two_hop.selected_profile('),
        ('EXPECTED_GROUPS.update(authenticated_two_hop.EXPECTED_GROUPS)\nassert not (EXPECTED_GROUPS.keys() & publication.EXPECTED_GROUPS.keys())\nEXPECTED_GROUPS.update(publication.EXPECTED_GROUPS)\n', 'EXPECTED_GROUPS.update(authenticated_two_hop.EXPECTED_GROUPS)\n'),
    ),
    'scripts/rc_pretag_desktop_tests.py': (
        ("            from rc_pretag_publication_tests import inverse_ownership\n            frozen = c._git('show', d.X + ':' + path, root=self.repo)\n            current = (c.ROOT / path).read_bytes()\n            if path == c.publication.OWNERSHIP_TESTS: current = inverse_ownership(current, frozen)\n            self.assertEqual(current, frozen)\n", "            self.assertEqual((c.ROOT / path).read_bytes(), c._git('show', d.X + ':' + path, root=self.repo))\n"),
        ('        complete_historical = previous | c.authenticated_two_hop.EXPECTED_GROUPS\n        self.assertEqual({key: c.EXPECTED_GROUPS[key] for key in complete_historical}, complete_historical)\n        self.assertEqual(c.EXPECTED_GROUPS, complete_historical | c.publication.EXPECTED_GROUPS)\n', '        self.assertEqual(c.EXPECTED_GROUPS, previous | c.authenticated_two_hop.EXPECTED_GROUPS)\n'),
        ("        full_historical = [name for name in loaded if name.rsplit('.', 1)[0] in complete_historical]\n        self.assertEqual((len(full_historical), len(set(full_historical))), (233, 233))\n        self.assertEqual((len(loaded), len(set(loaded))), (283, 283))\n", '        self.assertEqual((len(loaded), len(set(loaded))), (233, 233))\n'),
    ),
    'scripts/rc_pretag_nginx_tests.py': (
        ("            from rc_pretag_publication_tests import inverse_ownership\n            frozen = c._git('show', n.F + ':' + path, root=self.repo)\n            current = (c.ROOT / path).read_bytes()\n            if path == c.publication.OWNERSHIP_TESTS: current = inverse_ownership(current, frozen)\n            self.assertEqual(current, frozen)\n", "            self.assertEqual((c.ROOT / path).read_bytes(), c._git('show', n.F + ':' + path, root=self.repo))\n"),
        ('        complete_historical = previous | c.authenticated_two_hop.EXPECTED_GROUPS\n        self.assertEqual({key: c.EXPECTED_GROUPS[key] for key in complete_historical}, complete_historical)\n        self.assertEqual(c.EXPECTED_GROUPS, complete_historical | c.publication.EXPECTED_GROUPS)\n', '        self.assertEqual(c.EXPECTED_GROUPS, previous | c.authenticated_two_hop.EXPECTED_GROUPS)\n'),
        ("        full_historical = [name for name in loaded if name.rsplit('.', 1)[0] in complete_historical]\n        self.assertEqual((len(full_historical), len(set(full_historical))), (233, 233))\n        self.assertEqual((len(loaded), len(set(loaded))), (283, 283))\n", '        self.assertEqual((len(loaded), len(set(loaded))), (233, 233))\n'),
    ),
    'scripts/rc_pretag_two_hop_tests.py': (
        ("        from rc_pretag_publication_tests import inverse_ownership\n        path = 'scripts/rc_pretag_ownership_tests.py'\n        frozen = c._git('show', t.F + ':' + path, root=self.repo)\n        self.assertEqual(inverse_ownership((c.ROOT / path).read_bytes(), frozen), frozen)\n", "        path = 'scripts/rc_pretag_ownership_tests.py'\n        self.assertEqual((c.ROOT / path).read_bytes(), c._git('show', t.F + ':' + path, root=self.repo))\n"),
        ("        historical_expected = [name for name in all_expected if name.rsplit('.', 1)[0] not in c.publication.EXPECTED_GROUPS]\n        expected = [name for name in historical_expected if name.rsplit('.', 1)[0] not in c.authenticated_two_hop.EXPECTED_GROUPS]\n", "        expected = [name for name in all_expected if name.rsplit('.', 1)[0] not in c.authenticated_two_hop.EXPECTED_GROUPS]\n"),
        ("        self.assertEqual((len(all_loaded), len(set(all_loaded))), (283, 283)); self.assertEqual(Counter(all_loaded), Counter(all_expected))\n        historical_loaded = [name for name in all_loaded if name.rsplit('.', 1)[0] not in c.publication.EXPECTED_GROUPS]\n        self.assertEqual((len(historical_loaded), len(set(historical_loaded))), (233, 233))\n        loaded = [name for name in historical_loaded if name.rsplit('.', 1)[0] not in c.authenticated_two_hop.EXPECTED_GROUPS]; inventory_ids(loaded)\n", "        self.assertEqual((len(all_loaded), len(set(all_loaded))), (233, 233)); self.assertEqual(Counter(all_loaded), Counter(all_expected))\n        loaded = [name for name in all_loaded if name.rsplit('.', 1)[0] not in c.authenticated_two_hop.EXPECTED_GROUPS]; inventory_ids(loaded)\n"),
    ),
    'scripts/rc_pretag_authenticated_two_hop_tests.py': (
        ("        from rc_pretag_publication_tests import inverse_ownership\n        path = 'scripts/rc_pretag_ownership_tests.py'\n        frozen = c._git('show', a.M + ':' + path, root=self.repo)\n        self.assertEqual(inverse_ownership((c.ROOT / path).read_bytes(), frozen), frozen)\n", "        path = 'scripts/rc_pretag_ownership_tests.py'\n        self.assertEqual((c.ROOT / path).read_bytes(), c._git('show', a.M + ':' + path, root=self.repo))\n"),
        ("        self.assertEqual(tuple(o._parents(c.publication.N, self.repo, c._git)), c.publication.N_PARENTS)\n        self.assertEqual(c._git('rev-parse', c.publication.N + '^{tree}', root=self.repo).decode().strip(), c.publication.N_TREE)\n        frozen = self.selected(c.publication.N)\n        self.good = self.source | {p: frozen[p] for p in a.AMENDMENT_CAPS}\n", "        self.good = self.source | {p: ('100644', 'blob', self.blob((c.ROOT / p).read_bytes()))\n                                   for p in a.AMENDMENT_CAPS}\n"),
        ("            self.bad_content(self.changed(path, c._git('show', c.publication.N + ':' + path, root=self.repo) + b'\\n'))\n", "            self.bad_content(self.changed(path, (c.ROOT / path).read_bytes() + b'\\n'))\n"),
        ("        current = c._git('show', c.publication.N + ':' + path, root=self.repo)\n", '        current = (c.ROOT / path).read_bytes()\n'),
        ("        all_expected = [prefix + '.' + name for prefix, names in c.EXPECTED_GROUPS.items() for name in names.split()]\n        expected = [name for name in all_expected if name.rsplit('.', 1)[0] not in c.publication.EXPECTED_GROUPS]\n", "        expected = [prefix + '.' + name for prefix, names in c.EXPECTED_GROUPS.items() for name in names.split()]\n"),
        ("        all_loaded = [case.id() for case in c._flatten(suite)]\n        self.assertEqual((len(all_loaded), len(set(all_loaded))), (283, 283))\n        self.assertEqual(Counter(all_loaded), Counter(all_expected))\n        loaded = [name for name in all_loaded if name.rsplit('.', 1)[0] not in c.publication.EXPECTED_GROUPS]; inventory_ids(loaded)\n", '        loaded = [case.id() for case in c._flatten(suite)]; inventory_ids(loaded)\n'),
    ),
}
ALLOWED_METHODS = {'scripts/rc_pretag_composition_tests.py': {'test_adopted_contracts_are_byte_identical', 'test_fixture_workflow_triggers_and_no_duplicate_regressions', 'test_exact_tracked_tree_modes_and_scope'}, 'scripts/rc_pretag_desktop_tests.py': {'test_exact_x_preserves_legacy_profile_and_pins', 'test_legacy_inventory_and_new_named_inventory_are_exact'}, 'scripts/rc_pretag_nginx_tests.py': {'test_exact_historical_profiles_and_pins_remain_unchanged', 'test_frozen_167_plus_20_inventory_has_exact_loaded_and_executed_ids'}, 'scripts/rc_pretag_two_hop_tests.py': {'test_frozen_historical_profiles_and_pins_remain_exact', 'test_frozen_187_plus_22_inventory_is_exactly_loaded_and_executed'}, 'scripts/rc_pretag_authenticated_two_hop_tests.py': {'test_frozen_four_profiles_and_pins_remain_exact', 'test_frozen_209_plus_24_inventory_is_exactly_loaded_and_executed', 'adapter', 'setUp', 'test_amendment_pins_scope_binary_and_individual_total_budgets_reject'}}
OWNERSHIP_FRAGMENTS = (
    ("        frozen = c._entries(c.publication.N, self.repo)\n        for path in o.CAPS:\n            self.good[path] = frozen[path] if path in (o.CHECKS, c.publication.OWNERSHIP_TESTS) else (\n                '100644', 'blob', self.blob((c.ROOT / path).read_bytes()))\n", "        for path in o.CAPS:\n            self.good[path] = ('100644', 'blob', self.blob((c.ROOT / path).read_bytes()))\n"),
    ('        for path, pin in o.NEW_PINS.items():\n            data = (c.ROOT / path).read_bytes()\n            if path == o.CHECKS: data = c.publication.timeout_inverse(path, data)\n            self.assertEqual(o.pin(data), pin)\n', '        for path, pin in o.NEW_PINS.items(): self.assertEqual(o.pin((c.ROOT / path).read_bytes()), pin)\n'),
    ("        data = {p: c._git('cat-file', 'blob', self.good[p][2], root=self.repo) for p in o.CAPS}\n", '        data = {p: (c.ROOT / p).read_bytes() for p in o.CAPS}\n'),
)
OWNERSHIP_METHODS = {'setUp', 'test_exact_m_ownership_overlay_accepts_only_reviewed_delta', 'test_original_adopter_and_ownership_budgets_are_separate'}
ADAPTER_FRAGMENTS = FRAGMENTS | {p.OWNERSHIP_TESTS: OWNERSHIP_FRAGMENTS}


def inverse_adapter(path, current, frozen):
    pins = p.OWNERSHIP_PINS if path == p.OWNERSHIP_TESTS else a.AMENDMENT_PINS
    assert o.pin(frozen) == pins[path], 'historical N adapter pin'
    try:
        restored = current.decode()
    except UnicodeDecodeError as error:
        raise AssertionError('adapter encoding') from error
    for before, after in ADAPTER_FRAGMENTS[path]:
        restored = c._replace_once(restored, before, after)
    assert restored.encode() == frozen, 'complete N inverse'
    old, new = at.methods(frozen), at.methods(current)
    assert old.keys() == new.keys(), 'method names'
    allowed = OWNERSHIP_METHODS if path == p.OWNERSHIP_TESTS else ALLOWED_METHODS[path]
    assert {name for name in old if ast.dump(old[name]) != ast.dump(new[name])} == allowed
    recovered = at.methods(restored)
    assertions = lambda node: Counter(ast.dump(call) for call in ast.walk(node) if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute) and call.func.attr.startswith('assert'))
    for name in old:
        assert assertions(old[name]) == assertions(recovered[name]), name
    return restored.encode()


def inverse_ownership(current, frozen):
    assert p.OWNERSHIP_PINS.keys() == {p.OWNERSHIP_TESTS} and (len(frozen), len(frozen.splitlines())) == (22471, 372)
    return inverse_adapter(p.OWNERSHIP_TESTS, current, frozen)


def inventory_ids(ids, count=283, digest='8c511a659163f2e88a60246b95f9fbf077efde6d1679f28814ca014a48b3a907'):
    assert len(ids) == len(set(ids)) == count
    assert hashlib.sha256('\n'.join(sorted(ids)).encode()).hexdigest() == digest


class PublicationCompositionTests(unittest.TestCase):
    def setUp(self):
        self.repo, _, self.commit, self.blob = self.enterContext(c._profile_fixture())
        self.original = c._entries(p.N, self.repo)
        self.source = c._entries(p.S, self.repo)
        self.good = self.source | {path: ('100644', 'blob', self.blob((c.ROOT / path).read_bytes()))
                                   for path in p.AMENDMENT_CAPS | p.ANCILLARY_CAPS}
        self.pure = self.commit([p.S], self.good)
        self.feature = self.commit([p.N, self.pure], self.good)
        self.overlay = self.good | c.RELEASE_DOCS
        self.release = self.commit([p.R, self.feature], self.overlay)

    def selected(self, ref, git=c._git, **kwargs):
        return p.selected_profile(ref, self.repo, git, c._entries, c._feature_profile,
                                  c.RELEASE, c.RELEASE_TREE, c.RELEASE_DOCS, **kwargs)

    def source_content(self, ref, git=c._git):
        return p.publication_content(ref, self.repo, git, c._entries, c._feature_profile,
                                     c.RELEASE, c.RELEASE_TREE, c.RELEASE_DOCS)

    def amended(self, ref, git=c._git, entries=c._entries):
        return p.amendment_content(ref, self.source, self.repo, git, entries)

    def changed(self, path, data, base=None):
        return (self.good if base is None else base) | {path: ('100644', 'blob', self.blob(data))}

    def bad_content(self, entries, parents=None):
        ref = self.commit([p.S] if parents is None else parents, entries)
        p.publication_topology(ref, self.repo, c._git, p.R)
        with self.assertRaises(AssertionError) as failure:
            self.selected(ref)
        self.assertNotIsInstance(failure.exception, o.TopologyError)

    def rejects(self, parents, entries):
        ref = self.commit(parents, entries)
        self.assertEqual(c._entries(ref, self.repo), entries)
        with self.assertRaises(o.TopologyError):
            p.publication_topology(ref, self.repo, c._git, p.R)
        with ExitStack() as stack:
            stopped = [stack.enter_context(patch.object(module, name, side_effect=AssertionError('content ran')))
                       for module, name in ((o, 'content'), (d, 'desktop_content'), (n, 'nginx_content'),
                           (t, 'two_hop_content'), (a, 'authenticated_two_hop_content'),
                           (p, 'publication_content'), (p, 'amendment_content'), (o, 'release_content'))]
            with self.assertRaises(o.TopologyError):
                self.selected(ref)
            for action in stopped:
                action.assert_not_called()

    def test_exact_n_anchor_tree_parents_and_historical_validation(self):
        self.assertEqual((p.N, p.N_TREE, p.N_PARENTS), ('e459c9bec1dc6006eaad6df5f65111491c7b7572',
            '1eae7b72539740c2a1cc167a82ec2af3b5f951d6',
            ('a88be4901623f7c8629b93df984166587253f0be', '65b04eda5d63b8457b5b8879cd97d391e5e2b021')))
        self.assertEqual(self.selected(p.N), self.original)
        with patch.object(a, 'selected_profile', wraps=a.selected_profile) as historical:
            self.assertEqual(self.source_content(p.S), self.source)
            self.assertEqual(historical.call_args.args[0], p.N)
            self.assertIs(historical.call_args.args[4], c._feature_profile)
        for anchor in (p.N, p.S):
            def wrong_parents(*args, root):
                return b'\n' if args == ('show', '-s', '--format=%P', anchor) else c._git(*args, root=root)
            with patch.object(p, 'publication_content') as content, self.assertRaises(o.TopologyError):
                self.selected(self.pure, wrong_parents)
            content.assert_not_called()
            def wrong_tree(*args, root):
                return b'0' * 40 + b'\n' if args == ('rev-parse', anchor + '^{tree}') else c._git(*args, root=root)
            with self.assertRaises(AssertionError):
                self.source_content(p.S, wrong_tree)

    def test_source_s_has_only_five_reviewed_additions(self):
        self.assertEqual(o._parents(p.S, self.repo, c._git), [p.N])
        self.assertEqual(c._git('rev-parse', p.S + '^{tree}', root=self.repo).decode().strip(), p.S_TREE)
        self.assertEqual((len(self.original), len(self.source), len(p.SOURCE_PINS)), (1678, 1683, 5))
        self.assertEqual(self.source.keys() - self.original.keys(), p.SOURCE_CAPS.keys())
        self.assertEqual({path for path in self.source if self.source[path] != self.original.get(path)}, p.SOURCE_CAPS.keys())
        self.assertTrue(all(self.source[path] == value for path, value in self.original.items()))
        self.assertEqual(self.source_content(p.S), self.source)
        for path in p.SOURCE_PINS:
            if path not in p.ANCILLARY_CAPS:
                self.assertEqual((c.ROOT / path).read_bytes(), c._git('show', p.S + ':' + path, root=self.repo))

    def test_source_blob_digest_size_lines_and_modes_are_pinned(self):
        for path, row in p.SOURCE_PINS.items():
            data = c._git('show', p.S + ':' + path, root=self.repo)
            self.assertEqual(row, ('100644', *o.pin(data), len(data), len(data.splitlines())))
            for index, value in ((0, '100755'), (1, self.blob(b'drift\n')), (2, '0' * 64), (3, row[3] + 1), (4, row[4] + 1)):
                altered = list(row)
                altered[index] = value
                with self.subTest(path=path, field=index), patch.dict(p.SOURCE_PINS, {path: tuple(altered)}):
                    with self.assertRaises(AssertionError):
                        self.source_content(p.S)
            for changed in (data + b'\n', b'\0binary\xff'):
                self.bad_content(self.changed(path, changed))

    def test_candidate_c_has_only_seven_guard_changes(self):
        self.assertEqual(self.selected(self.pure), self.good)
        self.assertEqual((len(self.good), len(p.AMENDMENT_CAPS), len(p.AMENDMENT_PINS)), (1685, 7, 6))
        self.assertEqual((len(p.ANCILLARY_CAPS), len(p.ANCILLARY_PINS)), (6, 6))
        self.assertEqual({path for path in self.good if self.good[path] != self.source.get(path)}, (p.AMENDMENT_CAPS | p.ANCILLARY_CAPS).keys())
        self.assertEqual(p.AMENDMENT_PINS.keys(), p.AMENDMENT_CAPS.keys() - {p.PROFILE})
        for path, expected in (p.AMENDMENT_PINS | p.ANCILLARY_PINS).items():
            data = (c.ROOT / path).read_bytes()
            self.assertEqual(o.pin(data), expected)
            self.bad_content(self.changed(path, data + b'\n'))
            for altered in (('0' * 40, expected[1]), (expected[0], '0' * 64)):
                with patch.dict(p.ANCILLARY_PINS if path in p.ANCILLARY_CAPS else p.AMENDMENT_PINS, {path: altered}), self.assertRaises(AssertionError):
                    self.amended(self.pure)
        for path, value in self.source.items():
            if path not in p.AMENDMENT_CAPS | p.ANCILLARY_CAPS:
                self.assertEqual(self.good[path], value)

        for pins in (p.AMENDMENT_PINS, p.ANCILLARY_PINS):
            for altered in ({key: value for key, value in pins.items() if key != next(iter(pins))}, pins | {'extra': ('0' * 40, '0' * 64)}):
                with patch.dict(pins, altered, clear=True), self.assertRaises(AssertionError): self.amended(self.pure)
        for path in p.TIMEOUT_BASE_PINS:
            data = (c.ROOT / path).read_bytes(); line = b'    timeout-minutes: 20\n'
            self.assertEqual(p.timeout_inverse(path, data), c._git('show', p.N + ':' + path, root=self.repo))
            for altered in (data + b'# unrelated\n', *(data.replace(line, value) for value in (b'', line * 2, b'    timeout-minutes: 15\n', b'    timeout-minutes: 21\n'))):
                with self.assertRaises(AssertionError): p.timeout_inverse(path, altered)

    def test_source_only_candidate_and_correction_chains_reject(self):
        with self.assertRaises(o.TopologyError):
            self.selected(p.S)
        self.rejects([p.N], self.source)
        self.rejects([p.N, p.S], self.source)
        for parents in ([self.pure], [self.feature], [self.release], [p.S, self.pure]):
            self.rejects(parents, self.good)
        self.bad_content(self.source)

    def test_feature_merge_requires_ordered_parents_and_entire_c_tree(self):
        self.assertEqual(o._parents(self.feature, self.repo, c._git), [p.N, self.pure])
        self.assertEqual(self.selected(self.feature), self.good)
        self.bad_content(self.source, [p.N, self.pure])
        self.bad_content(self.changed(p.CORE, b'changed merge source\n'), [p.N, self.pure])
        self.bad_content(self.overlay, [p.N, self.pure])
        self.rejects([self.pure, p.N], self.good)

    def test_release_overlay_has_only_four_exact_historical_documents(self):
        self.assertEqual((p.R, p.R_TREE, p.R_DOCUMENTS), (a.R, a.R_TREE, a.R_DOCUMENTS))
        self.assertEqual(len(p.R_DOCUMENTS), 4)
        self.assertEqual(o._parents(self.release, self.repo, c._git), [p.R, self.feature])
        self.assertEqual(self.selected(self.release), self.overlay)
        self.assertEqual({path for path in self.overlay if self.overlay[path] != self.good.get(path)}, p.R_DOCUMENTS.keys())
        for path in (*p.R_DOCUMENTS, 'docs/releases/extra.md', p.CORE):
            for value in (None, ('100644', 'blob', self.blob(b'drift\n')), ('120000', 'blob', self.blob(b'target')),
                          ('100755', 'blob', self.blob(b'changed\n'))):
                changed = dict(self.overlay)
                if value is None:
                    changed.pop(path, None)
                else:
                    changed[path] = value
                if changed != self.overlay:
                    self.bad_content(changed, [p.R, self.feature])
        for release, tree, documents in (('f' * 40, p.R_TREE, p.R_DOCUMENTS), (p.R, '0' * 40, p.R_DOCUMENTS), (p.R, p.R_TREE, {})):
            with self.assertRaises(AssertionError):
                p.selected_profile(self.release, self.repo, c._git, c._entries, c._feature_profile, release, tree, documents)

    def test_missing_reversed_extra_duplicate_and_nested_parents_reject(self):
        for parents in ([], [p.N], [p.S, p.N], [p.S, p.S], [self.pure, p.N], [p.N, p.N],
                        [p.N, self.pure, p.S], [p.N, self.pure, self.pure], [p.N, self.feature], [p.N, self.release]):
            self.rejects(parents, self.good)
        for parents in ([self.feature, p.R], [p.R, self.feature, p.S], [p.R, p.R], [p.R, self.pure],
                        [p.R, p.S], [p.R, self.release], [self.release]):
            self.rejects(parents, self.overlay)

    def test_unknown_anchor_and_same_tree_impostor_reject(self):
        fake_n = self.commit([], self.original)
        fake_s = self.commit([], self.source)
        fake_r = self.commit([], c._entries(p.R, self.repo))
        for parents in ([fake_s], [fake_n, self.pure], ['f' * 40], [self.commit([], self.good)]):
            self.rejects(parents, self.good)
        self.rejects([fake_r, self.feature], self.overlay)
        with patch.object(p, 'publication_content') as content, self.assertRaises(o.TopologyError):
            self.selected('f' * 40)
        content.assert_not_called()
        for profile in (None, 1, '', 'engineering/issue88-publication-core-composition-v2', 'release', 'publish'):
            with self.assertRaises(AssertionError):
                self.selected(self.pure, git=lambda *a, **kw: self.fail('Git before profile rejection'), profile=profile)

    def test_missing_extra_renamed_symlink_gitlink_and_binary_paths_reject(self):
        for path in (*p.SOURCE_PINS, *p.AMENDMENT_CAPS, *p.ANCILLARY_CAPS):
            missing = dict(self.good)
            missing.pop(path)
            changes = [missing, missing | {path + '.renamed': self.good[path]}]
            changes += [self.good | {path: value} for value in
                        (('100755', *self.good[path][1:]), ('120000', 'blob', self.blob(b'target')),
                         ('160000', 'commit', p.S), ('100644', 'blob', self.blob(b'\0binary\xff')))]
            for changed in changes:
                with self.subTest(path=path, entry=changed.get(path)):
                    self.bad_content(changed)
        for path in ('unreviewed-extra.py', 'release-authority.json', 'docs/specs/issue88-publication-core/extra.md'):
            self.bad_content(self.changed(path, b'unreviewed\n'))

    def test_individual_and_aggregate_budgets_reject(self):
        self.assertEqual((p.SOURCE_DELTA_LIMIT, p.AMENDMENT_DELTA_LIMIT), (1340, 1050))
        self.assertEqual(sum(p.SOURCE_CAPS[path][1] for path in p.SOURCE_CAPS), 1380)
        for name, baseline, ref, probe in (('SOURCE_CAPS', p.N, p.S, self.source_content),
                                           ('AMENDMENT_CAPS', p.S, self.pure, self.amended), ('ANCILLARY_CAPS', p.S, self.pure, self.amended)):
            caps = getattr(p, name)
            entries = c._entries(ref, self.repo)
            for path, (_, diff_cap) in caps.items():
                cap = len(c._git('cat-file', 'blob', entries[path][2], root=self.repo).splitlines()) - 1
                with patch.dict(caps, {path: (cap, diff_cap)}), self.assertRaises(AssertionError):
                    probe(ref)
                def oversized(*args, root):
                    return f'{diff_cap + 1}\t0\t{path}\n'.encode() if args == ('diff', '--numstat', baseline, ref, '--', path) else c._git(*args, root=root)
                with self.assertRaises(AssertionError):
                    probe(ref, git=oversized)
            for row in (b'', b'-\t-\t' + path.encode() + b'\n', b'1\t0\n', b'1\t0\twrong\n',
                        b'1\t0\t' + path.encode() + b'\textra\n', b'1\t0\t' + path.encode() + b'\n1\t0\twrong\n'):
                def malformed(*args, root):
                    return row if args == ('diff', '--numstat', baseline, ref, '--', path) else c._git(*args, root=root)
                with self.assertRaises(AssertionError):
                    probe(ref, git=malformed)
            limit_name = 'SOURCE_DELTA_LIMIT' if name == 'SOURCE_CAPS' else 'AMENDMENT_DELTA_LIMIT'
            with patch.object(p, limit_name, 0), self.assertRaisesRegex(AssertionError, 'delta_budget'):
                probe(ref)
            budget_caps = p.SOURCE_CAPS if name == 'SOURCE_CAPS' else p.AMENDMENT_CAPS | p.ANCILLARY_CAPS
            def aggregate(*args, root):
                if len(args) == 6 and args[:5] == ('diff', '--numstat', baseline, ref, '--') and args[5] in budget_caps:
                    return f'{budget_caps[args[5]][1]}\t0\t{args[5]}\n'.encode()
                return c._git(*args, root=root)
            with self.assertRaisesRegex(AssertionError, 'delta_budget'):
                probe(ref, git=aggregate)
        data = (c.ROOT / p.PROFILE).read_bytes()
        self.bad_content(self.changed(p.PROFILE, data + b'# boundary\n' * (401 - len(data.splitlines()))))

    def test_five_historical_profiles_and_all_historical_pins_are_immutable(self):
        paths = (*at.PROFILE_DIGESTS, a.PROFILE)
        self.assertEqual(len(paths), 5)
        for path in paths:
            self.assertEqual((c.ROOT / path).read_bytes(), c._git('show', p.N + ':' + path, root=self.repo))
            self.assertEqual(self.good[path], self.original[path])
        for path, digest in at.PROFILE_DIGESTS.items():
            self.assertEqual(hashlib.sha256((c.ROOT / path).read_bytes()).hexdigest(), digest)
        for ref in (d.X, d.SOURCE, n.F, n.P, t.F, t.P, a.M, p.N):
            self.assertEqual(self.selected(ref), a.selected_profile(ref, self.repo, c._git, c._entries,
                             c._feature_profile, c.RELEASE, c.RELEASE_TREE, c.RELEASE_DOCS))
        self.assertEqual((o.DELTA_LIMIT, d.AMENDMENT_DELTA_LIMIT, n.AMENDMENT_DELTA_LIMIT,
                          t.AMENDMENT_DELTA_LIMIT, a.AMENDMENT_DELTA_LIMIT), (2200, 1100, 1250, 1300, 900))

    def test_five_adapter_inverses_recover_exact_n_bytes(self):
        self.assertEqual(set(FRAGMENTS), p.AMENDMENT_CAPS.keys() - {p.PROFILE, p.TESTS})
        for path in ADAPTER_FRAGMENTS:
            current = (c.ROOT / path).read_bytes()
            frozen = c._git('show', p.N + ':' + path, root=self.repo)
            self.assertEqual(inverse_adapter(path, current, frozen), frozen)
        historical = at.AuthenticatedTwoHopCompositionTests()
        self.addCleanup(historical.doCleanups)
        historical.setUp()
        self.assertEqual(historical.good, c._entries(p.N, historical.repo))
        self.assertEqual(historical.selected(historical.pure), historical.good)

    def test_adapter_method_names_and_assertions_are_preserved(self):
        for path in ADAPTER_FRAGMENTS:
            current = (c.ROOT / path).read_bytes()
            frozen = c._git('show', p.N + ':' + path, root=self.repo)
            self.assertEqual(inverse_adapter(path, current, frozen), frozen)
            for name, node in at.methods(current).items():
                text = ast.get_source_segment(current.decode(), node)
                edits = ['', text.replace('def ' + name, 'def renamed_' + name, 1), text + '\n    def extra_method(self): pass']
                if name not in (OWNERSHIP_METHODS if path == p.OWNERSHIP_TESTS else ALLOWED_METHODS[path]):
                    edits.append(text.replace(':\n', ':\n        pass\n', 1))
                for call in ast.walk(node):
                    if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr.startswith('assert'):
                        segment = ast.get_source_segment(current.decode(), call)
                        edits.extend((text.replace(segment, 'None', 1), text.replace(segment, segment + ' or None', 1)))
                for edit in edits:
                    with self.subTest(path=path, method=name), self.assertRaises(AssertionError):
                        inverse_adapter(path, current.replace(text.encode(), edit.encode(), 1), frozen)

    def test_outside_fragment_and_missing_duplicate_fragment_edits_reject(self):
        for path, fragments in ADAPTER_FRAGMENTS.items():
            current = (c.ROOT / path).read_bytes()
            frozen = c._git('show', p.N + ':' + path, root=self.repo)
            for before, _ in fragments:
                for replacement in ('', before * 2):
                    with self.assertRaises(AssertionError):
                        inverse_adapter(path, current.replace(before.encode(), replacement.encode(), 1), frozen)
            for altered in (current + b'# outside\n', b'\n' + current, current + b' ', current + b'\0', current + b'\xff'):
                with self.assertRaises(AssertionError):
                    inverse_adapter(path, altered, frozen)
            for altered in (frozen + b'\n', frozen[:-1]):
                with self.assertRaises(AssertionError):
                    inverse_adapter(path, current, altered)
            pins = p.OWNERSHIP_PINS if path == p.OWNERSHIP_TESTS else a.AMENDMENT_PINS
            for pin in (('0' * 40, pins[path][1]), (pins[path][0], '0' * 64)):
                with patch.dict(pins, {path: pin}), self.assertRaises(AssertionError):
                    inverse_adapter(path, current, frozen)

    def test_historical_content_failure_is_terminal_without_fallback(self):
        for module, name, ref in ((o, 'content', d.X), (d, 'desktop_content', n.F),
                                  (n, 'nginx_content', t.F), (t, 'two_hop_content', a.M),
                                  (a, 'authenticated_two_hop_content', p.N)):
            for error in (AssertionError, o.TopologyError):
                with patch.object(module, name, side_effect=error('terminal content failure')), \
                     patch.object(p, 'publication_content') as content:
                    with self.assertRaisesRegex(error, 'terminal content failure'):
                        self.selected(ref)
                    content.assert_not_called()
        for parent, topology in ((o.M, o.topology), (d.SOURCE, d.desktop_topology), (n.P, n.nginx_topology),
                                  (t.P, t.two_hop_topology), (a.P, a.authenticated_two_hop_topology)):
            ref = self.commit([parent], self.good)
            topology(ref, self.repo, c._git, p.R)
            with patch.object(p, 'publication_content') as content, self.assertRaises(AssertionError) as failure:
                self.selected(ref)
            self.assertNotIsInstance(failure.exception, o.TopologyError)
            content.assert_not_called()
        for name in ('publication_content', 'amendment_content'):
            for error in (AssertionError, o.TopologyError):
                with patch.object(p, name, side_effect=error('selected new content failure')):
                    with self.assertRaisesRegex(error, 'selected new content failure'):
                        self.selected(self.pure)

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
        with patch.dict(os.environ, hostile):
            self.assertEqual(self.selected('moving', moving), self.good)
        self.assertEqual(calls.count(('rev-parse', '--verify', 'moving^{commit}')), 1)
        self.assertEqual(sum(any('moving' in arg for arg in args) for args in calls), 1)
        calls.clear()
        p.publication_topology(self.pure, self.repo, moving, p.R)
        self.assertTrue(all(args[:3] == ('show', '-s', '--format=%P') for args in calls))

    def test_frozen_233_plus_50_named_inventory_is_exact(self):
        expected = [prefix + '.' + name for prefix, names in c.EXPECTED_GROUPS.items() for name in names.split()]
        added = [prefix + '.' + name for prefix, names in p.EXPECTED_GROUPS.items() for name in names.split()]
        historical = [name for name in expected if name.rsplit('.', 1)[0] not in p.EXPECTED_GROUPS]
        inventory_ids(expected)
        at.inventory_ids(historical)
        inventory_ids(added, 50, '6cc0bc92f8a9e8bf329dc81bfb8033ef0739a731454c73995dc31713039faaf5')
        self.assertEqual(set(next(names for prefix, names in p.EXPECTED_GROUPS.items() if prefix.endswith('.PublicationCompositionTests')).split()),
                         set(unittest.defaultTestLoader.getTestCaseNames(type(self))))
        suite = unittest.defaultTestLoader.discover(str(c.ROOT / 'scripts'), pattern='rc_pretag*_tests.py')
        loaded = [case.id() for case in c._flatten(suite)]
        inventory_ids(loaded)
        self.assertEqual(Counter(loaded), Counter(expected))
        for index, name in enumerate(expected):
            for altered in (expected[:index] + expected[index + 1:], expected + [name],
                            [item if item != name else item + '_replaced' for item in expected]):
                with self.assertRaises(AssertionError):
                    inventory_ids(altered)
        frozen, current = ast.parse(c._git('show', p.N + ':' + p.COMPOSITION, root=self.repo)), ast.parse((c.ROOT / p.COMPOSITION).read_bytes())
        for name in ('run_inventory', 'InventoryResult', '_flatten', '_git', '_entries', '_index_entries', '_profile_fixture', '_feature_profile', '_selected_profile'):
            extract = lambda tree: ast.dump(next(node for node in tree.body if getattr(node, 'name', '') == name))
            self.assertEqual(extract(current), extract(frozen))

    def test_protected_source_versions_gates_workflows_and_old_452_are_unchanged(self):
        modules = (
            'cloud_release_bundle_tests exact_build_audit_tests exclusive_native_contract_tests '
            'exclusive_native_dialog_tests exclusive_native_revoke_tests exclusive_release_tests '
            'final_rc_evidence_tests rc_consumer_archive_tests rc_consumer_contract_boundaries_tests '
            'rc_consumer_contract_numeric_tests rc_consumer_contract_parity_tests rc_consumer_contract_tests '
            'rc_consumer_default_worker_proof_tests rc_consumer_fence_tests rc_consumer_finalization_tests '
            'rc_consumer_io_ownership_tests rc_consumer_io_tests rc_consumer_output_tests '
            'rc_consumer_plan_tests rc_consumer_snapshot_tests rc_consumer_source_tests '
            'rc_consumer_transport_supervisor_tests rc_consumer_transport_tests rc_consumer_workflow_tests '
            'rc_packages_tests rc_version_gate_tests rc_windows_install_contract_tests '
            'release_dependency_capture_tests release_dependency_contract_tests release_tag_gate_tests '
            'reviewed_source_gate_tests source_provenance_gate_tests 发布版本回归v4 '
        ).split()
        old_ids = [case.id() for module in modules
                   for case in c._flatten(unittest.defaultTestLoader.loadTestsFromName(module))
                   if case.id().split('.', 1)[0] == module]
        inventory_ids(old_ids, 452, 'd01db4e6cd605c6636423e27c8c0409e90aba217cc0e6930474f59a24b57f372')
        context = p.selected_profile('HEAD', c.ROOT, c._git, c._entries, c._feature_profile,
                                     c.RELEASE, c.RELEASE_TREE, c.RELEASE_DOCS)
        for path, value in self.original.items():
            if path not in FRAGMENTS and path not in p.ANCILLARY_CAPS:
                self.assertEqual(self.good[path], value, path)
                self.assertEqual(o.pin((c.ROOT / path).read_bytes())[0], context[path][2], path)
        for path in ('package.json', 'package-lock.json', 'src-tauri/Cargo.toml', 'src-tauri/Cargo.lock',
                     'src-tauri/tauri.conf.json', 'scripts/rc_release_policy.py', 'scripts/rc_release_eligibility.py',
                     '.github/workflows/final-rc-packages.yml', '.github/workflows/rc-pretag-evidence.yml'):
            self.bad_content(self.changed(path, c._git('show', p.N + ':' + path, root=self.repo) + b'\n'))

    def test_core_exposes_only_closed_inert_operations_and_false_approval_reports(self):
        import rc_publication_contract as core
        import rc_pretag_publication_contract_tests as tests
        self.assertEqual(set(core.OPERATION_KINDS), {'ObserveFence', 'CreateDraft', 'ObserveDraft', 'UploadAsset',
                         'VerifyAsset', 'PublishPrerelease', 'VerifyPublished'})
        self.assertEqual(set(core.RESULT_KINDS), {'FenceObserved', 'DraftCreated', 'DraftObserved', 'AssetUploaded',
                         'AssetVerified', 'PrereleasePublished', 'PublishedVerified', 'OperationFailed', 'OperationUncertain'})
        module = ast.parse((c.ROOT / p.CORE).read_bytes())
        functions = {node.name for node in module.body if isinstance(node, ast.FunctionDef) and not node.name.startswith('_')}
        self.assertEqual(functions, {'start', 'advance', 'request_publish'})
        calls = {getattr(node.func, 'id', getattr(node.func, 'attr', '')) for node in ast.walk(module) if isinstance(node, ast.Call)}
        self.assertFalse(calls & {'open', 'write_bytes', 'write_text', 'Popen', 'run', 'system', 'urlopen', 'dispatch', 'post', 'put', 'delete'})
        transitions = tests.trace()
        self.assertEqual(transitions[0], core.start(*tests.fixture()))
        self.assertEqual(sum(type(item.action) is core.Operation for item in transitions), 25)
        for transition in transitions:
            for flag in ('release_approved', 'publish_approved', 'snapshot_atomic', 'live_publication_verified'):
                self.assertIs(getattr(transition, flag), False)
        self.assertEqual(p.PROFILE_ID, 'engineering/issue88-publication-core-composition-v1')


if __name__ == '__main__':
    unittest.main()
