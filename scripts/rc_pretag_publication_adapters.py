"""Mechanical historical adapters and exact current-M inverse fragments; inert on import."""
import ast
from collections import Counter

import rc_pretag_composition_tests as c
import rc_pretag_ownership_profile as o
import rc_pretag_authenticated_two_hop_profile as a
import rc_pretag_authenticated_two_hop_tests as at
import rc_pretag_publication_profile as p

# BEGIN EXACT M PUBLICATION ADAPTERS
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
# END EXACT M PUBLICATION ADAPTERS

EXTRACT_BEGIN = "# BEGIN EXACT M PUBLICATION ADAPTERS\n"
EXTRACT_END = "# END EXACT M PUBLICATION ADAPTERS\n"
EXTRACT_IMPORT = 'from rc_pretag_publication_adapters import (\n    FRAGMENTS, ALLOWED_METHODS, OWNERSHIP_FRAGMENTS, OWNERSHIP_METHODS, ADAPTER_FRAGMENTS,\n    inverse_adapter as _historical_inverse, inverse_ownership, inverse_join_once_adapter)\n\n\ndef inverse_adapter(path, current, frozen):\n    return _historical_inverse(path, inverse_join_once_adapter(path, current), frozen)\n'
JOIN_ONCE_FRAGMENTS = {
    'scripts/rc_pretag_composition_tests.py': (
        ('EXPECTED_GROUPS.update(publication.EXPECTED_GROUPS)\nassert not (EXPECTED_GROUPS.keys() & publication.JOIN_ONCE_GROUPS.keys())\nEXPECTED_GROUPS.update(publication.JOIN_ONCE_GROUPS)\n', 'EXPECTED_GROUPS.update(publication.EXPECTED_GROUPS)\n'),
    ),
    'scripts/rc_pretag_desktop_tests.py': (
        ('        self.assertEqual(c.EXPECTED_GROUPS, complete_historical | c.publication.EXPECTED_GROUPS | c.publication.JOIN_ONCE_GROUPS)\n', '        self.assertEqual(c.EXPECTED_GROUPS, complete_historical | c.publication.EXPECTED_GROUPS)\n'),
        ("        original_loaded = [name for name in loaded if name.rsplit('.', 1)[0] not in c.publication.JOIN_ONCE_GROUPS]\n        self.assertEqual((len(original_loaded), len(set(original_loaded))), (283, 283))\n        self.assertEqual((len(loaded), len(set(loaded))), (303, 303))\n", '        self.assertEqual((len(loaded), len(set(loaded))), (283, 283))\n'),
    ),
    'scripts/rc_pretag_nginx_tests.py': (
        ('        self.assertEqual(c.EXPECTED_GROUPS, complete_historical | c.publication.EXPECTED_GROUPS | c.publication.JOIN_ONCE_GROUPS)\n', '        self.assertEqual(c.EXPECTED_GROUPS, complete_historical | c.publication.EXPECTED_GROUPS)\n'),
        ("        original_loaded = [name for name in loaded if name.rsplit('.', 1)[0] not in c.publication.JOIN_ONCE_GROUPS]\n        self.assertEqual((len(original_loaded), len(set(original_loaded))), (283, 283))\n        self.assertEqual((len(loaded), len(set(loaded))), (303, 303))\n", '        self.assertEqual((len(loaded), len(set(loaded))), (283, 283))\n'),
    ),
    'scripts/rc_pretag_two_hop_tests.py': (
        ("        historical_expected = [name for name in all_expected if name.rsplit('.', 1)[0] not in (c.publication.EXPECTED_GROUPS | c.publication.JOIN_ONCE_GROUPS)]\n", "        historical_expected = [name for name in all_expected if name.rsplit('.', 1)[0] not in c.publication.EXPECTED_GROUPS]\n"),
        ("        self.assertEqual((len(all_loaded), len(set(all_loaded))), (303, 303)); self.assertEqual(Counter(all_loaded), Counter(all_expected))\n        historical_loaded = [name for name in all_loaded if name.rsplit('.', 1)[0] not in (c.publication.EXPECTED_GROUPS | c.publication.JOIN_ONCE_GROUPS)]\n", "        self.assertEqual((len(all_loaded), len(set(all_loaded))), (283, 283)); self.assertEqual(Counter(all_loaded), Counter(all_expected))\n        historical_loaded = [name for name in all_loaded if name.rsplit('.', 1)[0] not in c.publication.EXPECTED_GROUPS]\n"),
    ),
    'scripts/rc_pretag_authenticated_two_hop_tests.py': (
        ("        expected = [name for name in all_expected if name.rsplit('.', 1)[0] not in (c.publication.EXPECTED_GROUPS | c.publication.JOIN_ONCE_GROUPS)]\n", "        expected = [name for name in all_expected if name.rsplit('.', 1)[0] not in c.publication.EXPECTED_GROUPS]\n"),
        ('        self.assertEqual((len(all_loaded), len(set(all_loaded))), (303, 303))\n', '        self.assertEqual((len(all_loaded), len(set(all_loaded))), (283, 283))\n'),
        ("        loaded = [name for name in all_loaded if name.rsplit('.', 1)[0] not in (c.publication.EXPECTED_GROUPS | c.publication.JOIN_ONCE_GROUPS)]; inventory_ids(loaded)\n", "        loaded = [name for name in all_loaded if name.rsplit('.', 1)[0] not in c.publication.EXPECTED_GROUPS]; inventory_ids(loaded)\n"),
    ),
}
PUBLICATION_FRAGMENTS = (
    ('    def test_outside_fragment_and_missing_duplicate_fragment_edits_reject(self):\n        inverse_adapter = _historical_inverse\n', '    def test_outside_fragment_and_missing_duplicate_fragment_edits_reject(self):\n'),
    ('            current = inverse_join_once_adapter(path, (c.ROOT / path).read_bytes())\n', '            current = (c.ROOT / path).read_bytes()\n'),
    ("        self.assertEqual(tuple(o._parents(p.JOIN_ONCE_M, self.repo, c._git)), p.JOIN_ONCE_PARENTS)\n        self.assertEqual(c._git('rev-parse', p.JOIN_ONCE_M + '^{tree}', root=self.repo).decode().strip(), p.JOIN_ONCE_TREE)\n        self.good = self.selected(p.JOIN_ONCE_M)\n", "        self.good = self.source | {path: ('100644', 'blob', self.blob((c.ROOT / path).read_bytes()))\n                                   for path in p.AMENDMENT_CAPS | p.ANCILLARY_CAPS}\n"),
    ("            data = c._git('show', p.JOIN_ONCE_M + ':' + path, root=self.repo)\n", '            data = (c.ROOT / path).read_bytes()\n'),
    ("        all_expected = [prefix + '.' + name for prefix, names in c.EXPECTED_GROUPS.items() for name in names.split()]\n        expected = [name for name in all_expected if name.rsplit('.', 1)[0] not in p.JOIN_ONCE_GROUPS]\n", "        expected = [prefix + '.' + name for prefix, names in c.EXPECTED_GROUPS.items() for name in names.split()]\n"),
    ("        all_loaded = [case.id() for case in c._flatten(suite)]\n        self.assertEqual(Counter(all_loaded), Counter(all_expected))\n        loaded = [name for name in all_loaded if name.rsplit('.', 1)[0] not in p.JOIN_ONCE_GROUPS]\n", '        loaded = [case.id() for case in c._flatten(suite)]\n'),
)

JOIN_ONCE_METHODS = {
    p.COMPOSITION: set(),
    p.DESKTOP_TESTS: {'test_legacy_inventory_and_new_named_inventory_are_exact'},
    p.NGINX_TESTS: {'test_frozen_167_plus_20_inventory_has_exact_loaded_and_executed_ids'},
    p.TWO_HOP_TESTS: {'test_frozen_187_plus_22_inventory_is_exactly_loaded_and_executed'},
    p.AUTHENTICATED_TESTS: {'test_frozen_209_plus_24_inventory_is_exactly_loaded_and_executed'},
}
M_PROFILE_PIN = ('13e4e067a7d9b501f1f1d5514e6ec0aee9303b0e',
                 '2d732547bb3fae68e37105721699c4f69545f660ee84506f42ec78c601d495c7')
PROFILE_DISPATCH = (
    '    try:\n'
    '        kind, tip, source = join_once_topology(ref, root, git, release)\n'
    '    except ownership.TopologyError:\n'
    '        pass\n'
    '    else:\n'
    '        expected = join_once_content(source, root, git, entries, historical, release, release_tree, documents)\n'
    '        assert entries(tip, root) == expected\n'
    "        if kind == 'release':\n"
    '            return ownership.release_content(ref, expected, root, git, entries, release, release_tree, documents)\n'
    '        return expected\n')


def inverse_join_once_adapter(path, current):
    """Exact-once current inventory amendment back to the complete frozen M file."""
    if path == p.OWNERSHIP_TESTS:
        assert o.pin(current) == p.ANCILLARY_PINS[path]
        return current
    assert path in JOIN_ONCE_FRAGMENTS
    assert o.pin(current) == p.JOIN_ONCE_PINS[path][1:3], 'current adapter pin'
    try:
        restored = current.decode()
    except UnicodeDecodeError as error:
        raise AssertionError('adapter encoding') from error
    for before, after in JOIN_ONCE_FRAGMENTS[path]:
        restored = c._replace_once(restored, before, after)
    assert o.pin(restored.encode()) == p.AMENDMENT_PINS[path], 'complete M inverse'
    old, new = at.methods(restored), at.methods(current)
    assert old.keys() == new.keys(), 'method names'
    assert {name for name in old if ast.dump(old[name]) != ast.dump(new[name])} == JOIN_ONCE_METHODS[path]
    return restored.encode()


def publication_tests_inverse(current, adapter_source):
    """Recover the exact removed block, four adapted methods and original wrapper."""
    assert o.pin(current) == p.JOIN_ONCE_PINS[p.TESTS][1:3]
    assert o.pin(adapter_source) == p.JOIN_ONCE_PINS[p.JOIN_ONCE_HELPER][1:3]
    try:
        restored, helper = current.decode(), adapter_source.decode()
    except UnicodeDecodeError as error:
        raise AssertionError('adapter encoding') from error
    assert helper.count(EXTRACT_BEGIN) == helper.count(EXTRACT_END) == 1
    extracted = helper.split(EXTRACT_BEGIN)[1].split(EXTRACT_END)[0]
    for before, after in PUBLICATION_FRAGMENTS:
        restored = c._replace_once(restored, before, after)
    restored = c._replace_once(restored, EXTRACT_IMPORT, extracted)
    assert o.pin(restored.encode()) == p.AMENDMENT_PINS[p.TESTS], 'complete M publication tests'
    return restored.encode()


def publication_profile_inverse(current):
    """The external manifest binds self; this verifies the complete historical prefix."""
    try:
        restored = current.decode()
    except UnicodeDecodeError as error:
        raise AssertionError('profile encoding') from error
    marker = '\n\n# BEGIN JOIN-ONCE M ADOPTION\n'
    assert restored.count(marker) == 1 and restored.count('# END JOIN-ONCE M ADOPTION\n') == 1
    assert restored.endswith('# END JOIN-ONCE M ADOPTION\n')
    restored = c._replace_once(restored.split(marker)[0], PROFILE_DISPATCH, '')
    assert o.pin(restored.encode()) == M_PROFILE_PIN, 'complete M publication profile'
    return restored.encode()
