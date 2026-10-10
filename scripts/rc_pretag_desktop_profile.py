"""Engineering composition v1; exact validator bytes require external independent review."""
import rc_pretag_ownership_profile as ownership

PROFILE_ID = 'engineering/issue85-desktop-composition-v1'
X = '44ff88373d76b54a22d72eba17c0c7989e0be805'
X_TREE = '032a07be2622e4d2cf475180de650dcb2d819ac4'
X_PARENTS = (ownership.M, '2d06f330785f1cda77265e00072f3ec086fceac6')
SOURCE = '932c48d07ccfc49c312f6ee9b7ffc0ea19c65fe8'
SOURCE_TREE = '40d8139e7b265d7c7c9b3c12bf1bdaf5fa96d19f'
R = 'e2e011f7f2a3a1df838bbd588106205b999db610'
R_TREE = 'c0dfe00fdcc7ebc8e26acaad5d18ff3f94df9ba3'
R_DOCUMENTS = {
    'docs/releases/next-rc-ledger.md': ('100644', 'blob', 'f44a9b8abf0dac1e35cea0e23b36750b297d0704'),
    'docs/releases/next-rc-notes.md': ('100644', 'blob', 'c5cffd2d3dba5ce70f4dbe41167cf9f699c807d3'),
    'docs/releases/source-acceptance-audit.md': ('100644', 'blob', '7dd36643c0931fd5c8b6e2c2de8152b2f4c0366c'),
    'docs/releases/verification-v0.6.0-rc.4.md': ('100644', 'blob', 'de0f6f90e184bb41af7bb714ad425e51f0a9d819'),
}
SOURCE_PARENT_CHAIN = (
    (SOURCE, '8d1cebf82951e14b197083d39c13257c17755e27'),
    ('8d1cebf82951e14b197083d39c13257c17755e27', '69e325c3793ebb0747673c59096848540254a5f8'),
    ('69e325c3793ebb0747673c59096848540254a5f8', X),
)
COMPOSITION = 'scripts/rc_pretag_composition_tests.py'
PROFILE = 'scripts/rc_pretag_desktop_profile.py'
TESTS = 'scripts/rc_pretag_desktop_tests.py'
COLLECTOR = 'scripts/desktop_glib_build_evidence.py'
COMPOSITION_BASE_SHA256 = '5bf44aac60240fb6ee5d0af5afd82a8aa16ff4008ec78530cab937753e47a029'
# Fixed reviewed S additions: mode, blob, SHA256, byte count, line count.
DESKTOP_PINS = {
    'scripts/desktop_glib_build_evidence.py': ('100755', 'a89ddc77966faaf6a46c620b49d06bbe0d8c8f6f',
        'b44851807a17707746ef22b2750b43a77f8e199de2f328d51436ede115785faf', 17257, 307),
    'scripts/desktop_glib_build_contract.py': ('100644', 'f30b292768522616ced954939064143a7061fc4e',
        'a70672bd08151ad9d75ec48ad668bda9e153106ad20632224c95f77eaf2acc01', 27270, 479),
    'scripts/desktop_glib_deb.py': ('100644', 'b2c522d74eae61c64a09c55028dfffbdf23de059',
        'db20ebcbf85cd32910872a173a0ac807f39eb97f54909c11de91c1f88c7d6962', 13973, 241),
    'scripts/desktop_glib_link.py': ('100644', 'aa5d8289966eabf16781996cf39eb3e786559ed6',
        '6c079280e2a72b4a2309554f791595029827bd82a04abaa63c8c8d4dd2f9a7af', 22376, 403),
    'scripts/desktop_glib_probes.py': ('100644', 'a673c4367a64a046826b7f41acdea455589ab3ef',
        '97ba97bfa35cbb36fb3536cd2942a2d62fc680b2428422b0df7bfd4fed075339', 13241, 183),
    'scripts/desktop_glib_build_evidence_tests.py': ('100644', '7cafe9d4c560539bfe0a6df7cba31ab494dd7481',
        '21e93677a8ab28c8611fe0e10c086ccd6858bff332a00220a1175462974743cc', 26455, 460),
    'scripts/desktop_glib_deb_tests.py': ('100644', 'c45ce2a085df5f2dc61e8bb451e35a6573ab292d',
        '024f5ea37f4f2e735fe37c25e6e691fb6b139e0e2591eb8dda5e8624ff894cf2', 24970, 440),
    'scripts/desktop_glib_link_tests.py': ('100644', 'a9c0475d2db534b97aebec3a2a4d3f5645b40915',
        'b05df8daff27fbaba27b91a23110dba1df82ee7befe584522b235747a4068566', 23265, 434),
    'scripts/desktop_glib_probes_tests.py': ('100644', '2b1fca62b0bfe5e568988078a8aa5531fd9e81af',
        '4b782971bd8d3e79855f3b2a888c37824aec609ad9ee77496c83ee79298e3d7c', 18785, 290),
    '.github/workflows/issue85-desktop-glib-deb.yml': ('100644', 'c4a1105646c25d6190f63fe1b5f610de460fac57',
        '71b867b94974e2aa730eaa1382d026aeba42dcac550fa88db0a6282180e71357', 8579, 173),
    'docs/specs/issue85-scoped-additive/requirements.md': ('100644', '704e39b70faf74bf68fe2854b188db2cf3636133',
        '2edd4f55e0738a4587667ec0bb349c344d9f91e0dc379bd5b369044a5fffc9f3', 6191, 42),
    'docs/specs/issue85-scoped-additive/design.md': ('100644', 'a6815946afa6dc42dbcd6e7196311e7a1105416a',
        'b3f4ffd91b7ce380f05312827a34ffff2987c04154be56f02e4d2345c82eae46', 12466, 77),
    'docs/specs/issue85-scoped-additive/tasks.md': ('100644', 'a3daf29eee824b1d9a118d016fe45d746dc3e7de',
        '01f94a7120f84bd9450d9f7e32c7a0db0c6a03ac07418141d42c72b81dec474b', 4927, 58),
}
# Acyclic full-file pins: adapter, tests and specs never contain this module's hash.
AMENDMENT_PINS = {
    'scripts/rc_pretag_composition_tests.py': ('988c4be1175b68feecc2c38f8aee7f932e4589e2',
        'ff5e95e6ff14416aa969e1c9dad9e729c96c3aa624da63af4ff93c9edc397694'),
    'scripts/rc_pretag_desktop_tests.py': ('f1af6905e3b915b1e1dbb3c9c0493d1e16304cd7',
        'd200e4a971c6a94addd28da5d6331968236c8487ef017421a2b85a649b4d94ce'),
    'docs/specs/issue85-desktop-composition/requirements.md': ('b8fa52e7a59ae9fda30f2c6fcf8acfff71286c3f',
        'ca1770f67a56d5aab5670bc13789a05a7d385faf6e621a610489f9a58cd24044'),
    'docs/specs/issue85-desktop-composition/design.md': ('2924ae0dd6dfda2d03cf5ab9f1a37ab652c87ae2',
        '6b7dc758f6ff6114c1cab91f84eb25cd44972bc70e4f43cb97c0196b6e069822'),
    'docs/specs/issue85-desktop-composition/tasks.md': ('ed5645b630808978b855e558d3d39d9db1bd60d0',
        '780cee8188f86b487b6ed9ce22dd32929b9e6654c59aa5715d0be63281e0bb29'),
}
AMENDMENT_CAPS = {
    COMPOSITION: (500, 40), PROFILE: (360, 360), TESTS: (400, 400),
    **{'docs/specs/issue85-desktop-composition/' + name + '.md': (80, 80)
       for name in ('requirements', 'design', 'tasks')},
}
AMENDMENT_DELTA_LIMIT = 1100
EXPECTED_GROUPS = {'rc_pretag_desktop_tests.DesktopCompositionTests': (
    'test_exact_x_preserves_legacy_profile_and_pins test_immutable_source_prefix_and_thirteen_additions '
    'test_exact_source_and_one_amendment_accept test_exact_feature_merge_accepts_equal_tree '
    'test_exact_release_overlay_accepts_four_documents test_wrong_root_and_tree_equal_anchor_reject_before_content '
    'test_missing_reversed_duplicate_and_extra_parents_reject_before_content '
    'test_nested_merge_release_and_postmerge_descendants_reject_before_content '
    'test_amendment_chain_and_wrong_parent_reject_before_content test_merge_tree_drift_rejects_after_valid_topology '
    'test_release_overlay_path_mode_byte_and_deletion_drift_rejects test_each_desktop_blob_and_hash_mutation_rejects '
    'test_desktop_missing_extra_rename_and_type_mutations_reject test_only_pinned_collector_executable_mode_accepts '
    'test_each_historical_protected_entry_remains_exact test_amendment_scope_pins_and_budgets_reject_drift '
    'test_composition_adapter_reconstructs_frozen_x test_legacy_inventory_and_new_named_inventory_are_exact '
    'test_git_context_isolation_and_topology_only_dispatch test_engineering_scope_and_false_claim_boundaries')}


def desktop_topology(ref, root, git, release):
    """Closed parent grammar only; caller already bound ref to an exact commit."""
    if release != R:
        raise ownership.TopologyError('desktop_release_anchor')

    def candidate(tip):
        if tip != SOURCE and ownership._parents(tip, root, git) != [SOURCE]:
            raise ownership.TopologyError('desktop_candidate_parent')
        return tip

    def feature(tip):
        parents = ownership._parents(tip, root, git)
        if len(parents) != 2 or parents[0] != X:
            raise ownership.TopologyError('desktop_feature_parents')
        return tip, candidate(parents[1])

    parents = ownership._parents(ref, root, git)
    if parents and parents[0] == release:
        if len(parents) != 2:
            raise ownership.TopologyError('desktop_release_parents')
        tip, source = feature(parents[1])
        kind = 'release'
    elif len(parents) == 2 and parents[0] == X:
        tip, source = feature(ref)
        kind = 'nonrelease'
    else:
        tip = source = candidate(ref)
        kind = 'nonrelease'
    for child, parent in SOURCE_PARENT_CHAIN:
        if ownership._parents(child, root, git) != [parent]:
            raise ownership.TopologyError('desktop_source_prefix')
    if tuple(ownership._parents(X, root, git)) != X_PARENTS:
        raise ownership.TopologyError('desktop_anchor_parents')
    return kind, tip, source


def desktop_content(ref, root, git, entries, historical, release, release_tree, documents):
    """Independent exact-addition check; no parent assumptions about ref."""
    assert (release, release_tree, documents) == (R, R_TREE, R_DOCUMENTS)
    original = ownership.selected_profile(
        X, root, git, entries, historical, release, release_tree, documents)
    assert git('rev-parse', X + '^{tree}', root=root).decode().strip() == X_TREE
    assert git('rev-parse', SOURCE + '^{tree}', root=root).decode().strip() == SOURCE_TREE
    assert len(original) == 1632 and len(DESKTOP_PINS) == 13
    assert not (original.keys() & DESKTOP_PINS.keys())
    expected = original | {path: (mode, 'blob', blob)
                           for path, (mode, blob, _, _, _) in DESKTOP_PINS.items()}
    assert entries(SOURCE, root) == expected
    actual = entries(ref, root)
    assert actual == expected and len(actual) == 1645
    for path, (mode, blob, digest, size, lines) in DESKTOP_PINS.items():
        assert mode == ('100755' if path == COLLECTOR else '100644')
        data = git('cat-file', 'blob', blob, root=root)
        assert ownership.pin(data) == (blob, digest), path
        assert (len(data), len(data.splitlines())) == (size, lines), path
    return expected


def amendment_content(ref, baseline, root, git, entries):
    """Six-path scope guard; this validator's own exact bytes are externally reviewed."""
    actual = entries(ref, root)
    paths = AMENDMENT_CAPS.keys()
    assert AMENDMENT_PINS.keys() == paths - {PROFILE}
    assert set(baseline) & paths == {COMPOSITION}
    assert actual.keys() == baseline.keys() | paths
    assert {p for p in actual if actual[p] != baseline.get(p)} == paths
    assert all(actual[p] == value for p, value in baseline.items() if p not in paths)
    assert all(actual[p][:2] == ('100644', 'blob') for p in paths)
    data = {p: git('cat-file', 'blob', actual[p][2], root=root) for p in paths}
    for path, expected in AMENDMENT_PINS.items():
        assert ownership.pin(data[path]) == expected, path
    total = 0
    for path, (line_cap, diff_cap) in AMENDMENT_CAPS.items():
        assert len(data[path].splitlines()) <= line_cap, path
        fields = git('diff', '--numstat', SOURCE, ref, '--', path, root=root).split()
        delta = sum(map(int, fields[:2])) if fields else 0
        assert delta <= diff_cap, path
        total += delta
    assert total <= AMENDMENT_DELTA_LIMIT, 'desktop_amendment_delta_budget'
    old_data = {p: git('cat-file', 'blob', actual[p][2], root=root) for p in ownership.CAPS}
    ownership.budgets(ref, root, git, old_data)
    return actual


def selected_profile(ref, root, git, entries, historical, release, release_tree, documents):
    # Only this resolution sees a mutable caller ref. Every later read uses object IDs.
    ref = ownership._commit(ref, root, git)
    try:
        ownership.topology(ref, root, git, release)
    except ownership.TopologyError:
        kind, tip, source = desktop_topology(ref, root, git, release)
    else:
        # Deliberately outside the exception handler: legacy content failures are terminal.
        return ownership.selected_profile(
            ref, root, git, entries, historical, release, release_tree, documents)
    expected = desktop_content(SOURCE, root, git, entries, historical, release, release_tree, documents)
    if source != SOURCE:
        expected = amendment_content(source, expected, root, git, entries)
    if tip != source:
        assert entries(tip, root) == expected
    if kind == 'release':
        return ownership.release_content(
            ref, expected, root, git, entries, release, release_tree, documents)
    return expected
