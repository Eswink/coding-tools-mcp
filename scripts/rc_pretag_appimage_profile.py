"""Finite pinned AppImage engineering delta; external review binds this module."""
import rc_pretag_ownership_profile as o
import rc_pretag_publication_profile as p

M = 'feeaf299df6c3729285c91511ece18e9984a2503'
M_TREE = '81abcfdbe1bea9ab3a0baae252d4ad86db8b15c5'
M_PARENTS = ('6edd4e6137a6947319183b3ac8801bfa608ac722', '851f3374871f6303b37ec7c7055936e6d74ecc1c')
PROFILE = 'scripts/rc_pretag_appimage_profile.py'
PUBLICATION = 'scripts/rc_pretag_publication_profile.py'
ADAPTERS = 'scripts/rc_pretag_publication_adapters.py'
WARNING = 'scripts/rc_pretag_snapshot_warning_cases.py'
CASES = 'scripts/rc_pretag_appimage_cases.py'
HELPER = 'scripts/appimage_tools.py'
HELPER_TESTS = 'scripts/appimage_tools_tests.py'
WORKFLOW = '.github/workflows/linux-rc-packages.yml'
CAPS = {
    'scripts/appimage_tools.py': (450, 450),
    'scripts/appimage_tools_tests.py': (450, 450),
    'docs/specs/pinned-appimage-engineering-build/requirements.md': (125, 125),
    'docs/specs/pinned-appimage-engineering-build/design.md': (200, 200),
    'docs/specs/pinned-appimage-engineering-build/tasks.md': (125, 125),
    '.github/workflows/linux-rc-packages.yml': (300, 100),
    'scripts/rc_pretag_publication_profile.py': (500, 14),
    'scripts/rc_pretag_publication_adapters.py': (250, 4),
    'scripts/rc_pretag_snapshot_warning_cases.py': (450, 24),
    'scripts/rc_pretag_appimage_profile.py': (300, 300),
    'scripts/rc_pretag_appimage_cases.py': (480, 480),
}
DELTA_LIMIT = 2200
# Static reviewed mode/blob/SHA256/byte/line pins; never derived during admission.
SOURCE_PINS = {
    'scripts/appimage_tools.py': ('100644', '68ed84f625ea7cf5ac547e0e49fdca51388baffd', '176f537bd7f5e0a3ebf1f8c94e7da73b4af575666897e9dfdf39ac2cf9542917', 15312, 291),
    'scripts/appimage_tools_tests.py': ('100644', '0ae70f9f1c954609d5aa45752f662944c19882a8', '329e183fb5b955dadb2ff6d46e2f2faf7571783b8dabeda3113af4fc92c10a7c', 20744, 382),
    'docs/specs/pinned-appimage-engineering-build/requirements.md': ('100644', '530e5ed2ec8ec3374d8a97b294666f9a6561d1e7', 'bf7c09bc9deaa20be999d06e544a1353067a977968fff0549fa887ab4555cc8a', 7552, 85),
    'docs/specs/pinned-appimage-engineering-build/design.md': ('100644', '799af33a4e9af94b565b3e6297de5ffdb7cce403', 'b2fda40e6ecb7c2e1322466bcc411303d7507057c200baca9f644483135a535f', 8460, 84),
    'docs/specs/pinned-appimage-engineering-build/tasks.md': ('100644', 'e8e44102795fd3d222033f8b9ed523b313e00948', '5881c3301f4a6480e87cef31fe03144dd74d9812a2269460ecd2e436e52997b1', 4488, 70),
    '.github/workflows/linux-rc-packages.yml': ('100644', 'fc3523c783f86883800ea133b67bb1a8c47846e0', '847e793bf5768f785c8c3da1f4c803fdd92fb2495f1476966eb4c70c0a96983d', 12527, 236),
    'scripts/rc_pretag_publication_profile.py': ('100644', '90807a2bd251b6169d8f56de93e07615780a3e82', '9aaa8798c0aff5b253a3da7d90c17af55631a60d502c269ff2bdfbc2082c7cd5', 32273, 495),
    'scripts/rc_pretag_publication_adapters.py': ('100644', 'a7b2fa2675551c0d6156192e57266d697cbbf544', '88b4a1452a9f4b050e1f7d7767eb202b07dab3d5bce17c275a60e3e0fd9ae329', 24677, 248),
    'scripts/rc_pretag_snapshot_warning_cases.py': ('100644', 'dcd96b0a4d3b0375a60df3017986b375550ae88e', 'f61985704f42232a5436075d4cf57ee14c311a5957491c45894c969984474713', 29679, 446),
    'scripts/rc_pretag_appimage_cases.py': ('100644', 'd223899eb5ce0d566ca3f86febb9a3c8492777e5', '5b6aace0b5d2237b1f650eb9072abd13dfc6341e35e83f7885ad2f48d751c248', 29107, 394),
}
# Complete original M bytes for the three minimal adapters.
BASE_PINS = {
    'scripts/rc_pretag_publication_profile.py': ('1a43cfc512e29d1d10b263623824ed37b3b3befc', '13907015ff633a03ca0cd61653753d3a13c7153c5d691bafd341411af897ea42'),
    'scripts/rc_pretag_publication_adapters.py': ('5fe498145f77d1f73f8f1142810f2d1441ed0bcd', 'b5a822b35a105e5d7dd64997690ac9612dece7f900447aeb440d1eeb46586687'),
    'scripts/rc_pretag_snapshot_warning_cases.py': ('23b1669bfe2f5565fc6e13b957e6b9451e02eded', '45b4425fc45c2b46d30cd4de970c0f59d46d8bb143fd77d30497f87199e98ec4'),
}
PROFILE_DISPATCH = "    import rc_pretag_appimage_profile as appimage\n    try:\n        kind, tip, source = appimage.topology(ref, root, git, release)\n    except ownership.TopologyError:\n        pass\n    else:\n        expected = appimage.content(source, root, git, entries, historical, release, release_tree, documents)\n        assert entries(tip, root) == expected\n        if kind == 'release':\n            return ownership.release_content(ref, expected, root, git, entries, release, release_tree, documents)\n        return expected\n"
INVERSE_PREFIX = '    from rc_pretag_appimage_profile import inverse_appimage_adapter\n    current = inverse_appimage_adapter(path, current)\n'
FRAGMENTS = {
    PUBLICATION: ((PROFILE_DISPATCH, ""),),
    ADAPTERS: ((INVERSE_PREFIX, ""),),
    WARNING: (
        ('import rc_pretag_publication_tests as pt\nfrom rc_pretag_appimage_profile import inverse_appimage_adapter\n', 'import rc_pretag_publication_tests as pt\n'),
        ("        self.good = self.original | {path: ('100644', 'blob', self.blob(inverse_appimage_adapter(path, (c.ROOT / path).read_bytes()))) for path in p.WARNING_CAPS}\n", "        self.good = self.original | {path: ('100644', 'blob', self.blob((c.ROOT / path).read_bytes())) for path in p.WARNING_CAPS}\n"),
        ('        for path, row in p.WARNING_PINS.items():\n            data = inverse_appimage_adapter(path, (c.ROOT / path).read_bytes())\n', '        for path, row in p.WARNING_PINS.items():\n            data = (c.ROOT / path).read_bytes()\n'),
        ('            lines = len(inverse_appimage_adapter(path, (c.ROOT / path).read_bytes()).splitlines())\n', '            lines = len((c.ROOT / path).read_bytes().splitlines())\n'),
        ('        for path in adapters.WARNING_BASE_PINS:\n            data = inverse_appimage_adapter(path, (c.ROOT / path).read_bytes())\n', '        for path in adapters.WARNING_BASE_PINS:\n            data = (c.ROOT / path).read_bytes()\n'),
    ),
}
CLASS = 'rc_pretag_appimage_cases.AppImageCompositionTests'
DIGEST = 'ebf61fdde11a73759c026c0bca4564de1f5930b72f83a4687ad5dc916fb95526'
NAMES = (
    'test_exact_m_anchor_tree_parents_and_fresh_history',
    'test_candidate_exact_eleven_paths_and_pins',
    'test_ordered_feature_merge_requires_entire_candidate_tree',
    'test_release_overlay_requires_exact_four_r_documents',
    'test_missing_reversed_extra_duplicate_nested_parents_reject',
    'test_unknown_same_tree_anchors_and_correction_chains_reject',
    'test_source_pins_sizes_modes_and_five_tools_are_exact',
    'test_helper_test_inventory_is_twenty_unique_ids',
    'test_workflow_inverse_preserves_all_original_gates_and_jobs',
    'test_workflow_runs_pinned_preparation_and_pre_post_checks',
    'test_missing_extra_rename_symlink_gitlink_binary_reject',
    'test_individual_and_aggregate_budgets_reject',
    'test_current_inverses_recover_complete_m_guards',
    'test_adapter_fragments_missing_duplicate_outside_edits_reject',
    'test_historical_profiles_pins_and_all_775_assertions_preserved',
    'test_selected_content_failure_is_terminal_without_fallback',
    'test_mutable_refs_and_ambient_git_cannot_change_identity',
    'test_old775_plus_new40_ids_are_exact_disjoint',
    'test_new_inventory_execution_rejects_skips_missing_duplicate_unknown',
    'test_protected_runtime_held_versions_and_release_scope_unchanged',
)


def inverse_appimage_adapter(path, current):
    """Remove exact-once additions and recover complete immutable M bytes."""
    import rc_pretag_linux_package_inverse as linux_package
    current = linux_package.inverse(path, current) if path in linux_package.BASE_PINS else current
    if path not in BASE_PINS or o.pin(current) == BASE_PINS[path]:
        return current
    assert o.pin(current) == SOURCE_PINS[path][1:3], 'current AppImage adapter pin'
    try:
        restored = current.decode()
    except UnicodeDecodeError as error:
        raise AssertionError('appimage adapter encoding') from error
    for before, after in FRAGMENTS[path]:
        assert restored.count(before) == 1, 'appimage fragment missing or duplicated'
        restored = restored.replace(before, after, 1)
    data = restored.encode()
    assert o.pin(data) == BASE_PINS[path], 'complete M AppImage inverse'
    return data


def topology(ref, root, git, release):
    """Only D[M], I[M,D], J[R,I]; no correction or arbitrary ancestry."""
    if release != p.R:
        raise o.TopologyError('appimage_release_anchor')
    parents = o._parents(ref, root, git)
    if parents == [M]:
        kind, tip, source = 'nonrelease', ref, ref
    elif len(parents) == 2 and parents[0] == M:
        kind, tip, source = 'nonrelease', ref, parents[1]
    elif len(parents) == 2 and parents[0] == p.R:
        kind, tip = 'release', parents[1]
        feature_parents = o._parents(tip, root, git)
        if len(feature_parents) != 2 or feature_parents[0] != M:
            raise o.TopologyError('appimage_feature_parents')
        source = feature_parents[1]
    else:
        raise o.TopologyError('appimage_candidate_parents')
    if o._parents(source, root, git) != [M]:
        raise o.TopologyError('appimage_candidate_parent')
    if tuple(o._parents(M, root, git)) != M_PARENTS:
        raise o.TopologyError('appimage_anchor_parents')
    return kind, tip, source


def content(ref, root, git, entries, historical, release, release_tree, documents):
    """Fresh historical validation followed by the exact eleven-path delta."""
    assert (release, release_tree, documents) == (p.R, p.R_TREE, p.R_DOCUMENTS)
    assert tuple(o._parents(M, root, git)) == M_PARENTS
    assert git('rev-parse', M + '^{tree}', root=root).decode().strip() == M_TREE
    baseline = p.selected_profile(M, root, git, entries, historical, release, release_tree, documents)
    actual = entries(ref, root)
    paths = CAPS.keys()
    assert len(baseline) == 1698 and len(paths) == 11
    assert SOURCE_PINS.keys() == paths - {PROFILE}
    assert baseline.keys() & paths == {PUBLICATION, ADAPTERS, WARNING, WORKFLOW}
    assert actual.keys() == baseline.keys() | paths and len(actual) == 1705
    assert {path for path in actual if actual[path] != baseline.get(path)} == paths
    assert all(actual[path] == value for path, value in baseline.items() if path not in paths)
    assert all(actual[path][:2] == ('100644', 'blob') for path in paths)
    data = {path: git('cat-file', 'blob', actual[path][2], root=root) for path in paths}
    for path, (mode, blob, digest, size, lines) in SOURCE_PINS.items():
        assert mode == '100644' and o.pin(data[path]) == (blob, digest), path
        assert (len(data[path]), len(data[path].splitlines())) == (size, lines), path
    for path in BASE_PINS:
        assert inverse_appimage_adapter(path, data[path]) == git('cat-file', 'blob', baseline[path][2], root=root)
    p.authenticated._budgets(ref, M, root, git, data, CAPS, DELTA_LIMIT, 'appimage_delta_budget')
    return actual
