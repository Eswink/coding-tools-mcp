"""Engineering composition v1; exact profile bytes and candidate tree require external review."""
import rc_pretag_ownership_profile as ownership
import rc_pretag_desktop_profile as desktop

PROFILE_ID = 'engineering/issue40-nginx-composition-v1'
F = '310ad16c8aa9cc8182c4b0f6a196184fcf34bc52'
F_TREE = '66b0dde07e5dd83883e3978886b61a82badafcd6'
F_PARENTS = ('44ff88373d76b54a22d72eba17c0c7989e0be805', 'afca8585ebb231d247080b184f47ceb2012accac')
P = 'cf3e59b4b411b7a92bb7d6ef8783c2720fb2fb1d'
P_TREE = 'fcdaef969403255b9ba6221437ea0916ac348677'
R = 'e2e011f7f2a3a1df838bbd588106205b999db610'
R_TREE = 'c0dfe00fdcc7ebc8e26acaad5d18ff3f94df9ba3'
R_DOCUMENTS = {
    'docs/releases/next-rc-ledger.md': ('100644', 'blob', 'f44a9b8abf0dac1e35cea0e23b36750b297d0704'),
    'docs/releases/next-rc-notes.md': ('100644', 'blob', 'c5cffd2d3dba5ce70f4dbe41167cf9f699c807d3'),
    'docs/releases/source-acceptance-audit.md': ('100644', 'blob', '7dd36643c0931fd5c8b6e2c2de8152b2f4c0366c'),
    'docs/releases/verification-v0.6.0-rc.4.md': ('100644', 'blob', 'de0f6f90e184bb41af7bb714ad425e51f0a9d819'),
}
COMPOSITION = 'scripts/rc_pretag_composition_tests.py'
DESKTOP_TESTS = 'scripts/rc_pretag_desktop_tests.py'
PROFILE = 'scripts/rc_pretag_nginx_profile.py'
TESTS = 'scripts/rc_pretag_nginx_tests.py'
# Reviewed P source additions: mode, blob, SHA256, byte count, line count.
SOURCE_PINS = {
    '.github/workflows/issue40-current-nginx-include.yml': ('100644', '7f098353cb5101a7744b2fcb0457b1b50f040b47',
        '9c05702b8fc8f00d6385bf0f9310959c489e1fe4382be1f627b04e8b1cd15332', 13726, 211),
    'deploy/cloud-gateway/current_nginx_include.py': ('100644', 'b44258e8b2e87bb9c5fa756b2cba99578246d757',
        '9e60b0a778fd3b9da08313679bda6dd497f6c4394c6043762864c38bfcfbb68e', 8145, 159),
    'docs/deployment/current-nginx-include.md': ('100644', 'e6bcf7d9855a2c78a6d04dfd3bbee35551d74045',
        '9866837496cacb9f84f7aa2d36d1b8e4c66cd79f71b5404f865e0c405a10f38a', 9813, 159),
    'docs/specs/issue40-current-nginx-include/design.md': ('100644', 'c7f11244ebed6684ccc1d2428a241b2a555cebf0',
        '52f44613b40a9914419fdd4d8efefe4a8f865d5c31c33ea76accee37f0f7f642', 11625, 72),
    'docs/specs/issue40-current-nginx-include/requirements.md': ('100644', 'd4322c2789e47b2cd1076eae0af075ca61a1351c',
        '1482cd8cb38d50ae741a81278f5a1e5c588498c3ab43cf5f6ebbb4c9d5fd18d2', 7731, 70),
    'docs/specs/issue40-current-nginx-include/tasks.md': ('100644', 'c44e5e985a77be08bd15a76b28c7b060f21de675',
        '0b2ba0e491178d2031efda0ddd2e6c98ae75bc3dc1d830a4aca747b8616f020b', 5735, 65),
    'tests/cloud-gateway-deployment/run_current_nginx_checks.py': ('100644', '0d213532d6101f5146756a0806aa5f4bb4a7f7e5',
        '6c3fc962ba8e396a1bb71258c3367656d80766e75af62ba7a98307f18071058f', 18758, 344),
    'tests/cloud-gateway-deployment/run_current_nginx_runtime.py': ('100644', '3e666fe7ffff945e51db50e96937b1b92aeff3af',
        '79ef3c7ed11ae6b7614edf251f199de33c487991072f0cbbe0951dd29f6a596c', 12793, 214),
    'tests/cloud-gateway-deployment/test_current_nginx_include.py': ('100644', '67c01e305babd19986ae8b64b76a26dcee3befdf',
        'c438afe984c3d31185e601289bc1972eafcb09412f9fc076794e3c95ddb3b5eb', 23223, 406),
}
# Acyclic full-file pins; the profile-self lock belongs in the external reviewed manifest.
AMENDMENT_PINS = {
    'scripts/rc_pretag_composition_tests.py': ('99483e8545add6209aee035b7460d5b56c023a82',
        'f0cf5e2ff2739efd976125d893bf9cd58a5c1d0706a4b9cf95d998811b706488'),
    'scripts/rc_pretag_desktop_tests.py': ('7be8e53f9a9d702fd27211cd7f727f0f760d60ee',
        'c82eed1c5a92fab2c1dd312c0c5d81cd57012483b09c4aa16ff8247ef618517f'),
    'scripts/rc_pretag_nginx_tests.py': ('d55bdd246b3f42b1efc336b54ef253376991bbd7',
        '3f1f86d440e5305b057ccbea97e4a4eb0a67e6469a83d0330876018f3adabc3c'),
    'docs/specs/issue40-nginx-composition/requirements.md': ('eb655b61c532a089256409153fe8e99b665eff01',
        '377a9b780b8a0fafb70b6eb73123fd9f5622a145636f41992ecfaadb822902e4'),
    'docs/specs/issue40-nginx-composition/design.md': ('0679be145df49fbb89aa82260638ea5a538852bc',
        'bdae66bacbd03a2d0a9613d9dcd065e5021f4b54e2b63ea69ba1c40fdb28f5d3'),
    'docs/specs/issue40-nginx-composition/tasks.md': ('fb02ee7031263e9cfcf95c15e63416a0caca0b2a',
        '105fd76acd403876f7548e9c1a3257024c17b671e3863efe92462d08b1b7663f'),
}
AMENDMENT_CAPS = {
    COMPOSITION: (500, 24), DESKTOP_TESTS: (400, 80), PROFILE: (400, 400), TESTS: (480, 480),
    **{'docs/specs/issue40-nginx-composition/' + name + '.md': (80, 80)
       for name in ('requirements', 'design', 'tasks')},
}
AMENDMENT_DELTA_LIMIT = 1250
EXPECTED_GROUPS = {'rc_pretag_nginx_tests.NginxCompositionTests': (
    'test_exact_historical_profiles_and_pins_remain_unchanged '
    'test_exact_f_anchor_parent_tree_and_legacy_validation '
    'test_p_source_has_only_nine_exact_additions '
    'test_exact_p_and_single_reviewed_amendment_accept '
    'test_exact_ordered_feature_merge_equals_source_tree '
    'test_exact_release_overlay_contains_only_four_pinned_documents '
    'test_missing_unknown_and_same_tree_impostor_anchors_reject '
    'test_reversed_duplicate_missing_and_extra_parents_reject_before_content '
    'test_amendment_chains_nested_merges_and_postmerge_descendants_reject '
    'test_each_nine_source_blob_and_sha256_mutation_rejects '
    'test_missing_extra_renamed_mode_symlink_and_gitlink_entries_reject '
    'test_each_historical_protected_entry_and_version_slot_remains_exact '
    'test_release_document_byte_mode_path_and_deletion_drift_rejects '
    'test_amendment_pins_scope_individual_and_total_budgets_reject '
    'test_composition_adapter_inverse_recovers_exact_f '
    'test_desktop_fixture_adapter_preserves_historical_assertions '
    'test_frozen_167_plus_20_inventory_has_exact_loaded_and_executed_ids '
    'test_mutable_refs_and_ambient_git_redirection_cannot_change_identity '
    'test_topology_only_dispatch_keeps_legacy_content_failures_terminal '
    'test_unknown_profile_versions_and_native_release_claims_reject '
)}


def nginx_topology(ref, root, git, release):
    """Only ordered parents, never content; caller has resolved the ref once."""
    if release != R:
        raise ownership.TopologyError('nginx_release_anchor')

    def candidate(tip):
        if tip != P and ownership._parents(tip, root, git) != [P]:
            raise ownership.TopologyError('nginx_candidate_parent')
        return tip

    def feature(tip):
        parents = ownership._parents(tip, root, git)
        if len(parents) != 2 or parents[0] != F:
            raise ownership.TopologyError('nginx_feature_parents')
        return tip, candidate(parents[1])

    parents = ownership._parents(ref, root, git)
    if parents and parents[0] == release:
        if len(parents) != 2:
            raise ownership.TopologyError('nginx_release_parents')
        tip, source = feature(parents[1])
        kind = 'release'
    elif len(parents) == 2 and parents[0] == F:
        tip, source = feature(ref)
        kind = 'nonrelease'
    else:
        tip = source = candidate(ref)
        kind = 'nonrelease'
    if ownership._parents(P, root, git) != [F]:
        raise ownership.TopologyError('nginx_source_parent')
    if tuple(ownership._parents(F, root, git)) != F_PARENTS:
        raise ownership.TopologyError('nginx_anchor_parents')
    return kind, tip, source


def nginx_content(ref, root, git, entries, historical, release, release_tree, documents):
    """Exact F plus nine additions, independently of the caller's parent shape."""
    assert (release, release_tree, documents) == (R, R_TREE, R_DOCUMENTS)
    original = desktop.selected_profile(
        F, root, git, entries, historical, release, release_tree, documents)
    assert git('rev-parse', F + '^{tree}', root=root).decode().strip() == F_TREE
    assert git('rev-parse', P + '^{tree}', root=root).decode().strip() == P_TREE
    assert len(original) == 1650 and len(SOURCE_PINS) == 9
    assert not (original.keys() & SOURCE_PINS.keys())
    expected = original | {path: (mode, 'blob', blob)
                           for path, (mode, blob, _, _, _) in SOURCE_PINS.items()}
    assert entries(P, root) == expected
    assert entries(ref, root) == expected and len(expected) == 1659
    for path, (mode, blob, digest, size, lines) in SOURCE_PINS.items():
        assert mode == '100644', path
        data = git('cat-file', 'blob', blob, root=root)
        assert ownership.pin(data) == (blob, digest), path
        assert (len(data), len(data.splitlines())) == (size, lines), path
    return expected


def amendment_content(ref, baseline, root, git, entries):
    """Seven reviewed paths; this profile's own exact bytes need external review."""
    actual = entries(ref, root)
    paths = AMENDMENT_CAPS.keys()
    assert AMENDMENT_PINS.keys() == paths - {PROFILE}
    assert set(baseline) & paths == {COMPOSITION, DESKTOP_TESTS}
    assert actual.keys() == baseline.keys() | paths and len(actual) == 1664
    assert {p for p in actual if actual[p] != baseline.get(p)} == paths
    assert all(actual[p] == value for p, value in baseline.items() if p not in paths)
    assert all(actual[p][:2] == ('100644', 'blob') for p in paths)
    data = {p: git('cat-file', 'blob', actual[p][2], root=root) for p in paths}
    for path, expected in AMENDMENT_PINS.items():
        assert ownership.pin(data[path]) == expected, path
    total = 0
    for path, (line_cap, diff_cap) in AMENDMENT_CAPS.items():
        assert len(data[path].splitlines()) <= line_cap, path
        fields = git('diff', '--numstat', P, ref, '--', path, root=root).split()
        assert len(fields) >= 3 and all(v.isdigit() for v in fields[:2]), path
        delta = sum(map(int, fields[:2]))
        assert delta <= diff_cap, path
        total += delta
    assert total <= AMENDMENT_DELTA_LIMIT, 'nginx_amendment_delta_budget'
    old_data = {p: git('cat-file', 'blob', actual[p][2], root=root) for p in ownership.CAPS}
    ownership.budgets(ref, root, git, old_data)
    return actual


def selected_profile(ref, root, git, entries, historical, release, release_tree, documents, *, profile=PROFILE_ID):
    assert profile == PROFILE_ID, 'unknown_composition_profile'
    ref = ownership._commit(ref, root, git)
    try:
        ownership.topology(ref, root, git, release)
    except ownership.TopologyError:
        pass
    else:
        # Topology acceptance is terminal, including any legacy content failure.
        return ownership.selected_profile(
            ref, root, git, entries, historical, release, release_tree, documents)
    try:
        desktop.desktop_topology(ref, root, git, release)
    except ownership.TopologyError:
        kind, tip, source = nginx_topology(ref, root, git, release)
    else:
        return desktop.selected_profile(
            ref, root, git, entries, historical, release, release_tree, documents)
    expected = nginx_content(P, root, git, entries, historical, release, release_tree, documents)
    if source != P:
        expected = amendment_content(source, expected, root, git, entries)
    if tip != source:
        assert entries(tip, root) == expected
    if kind == 'release':
        return ownership.release_content(
            ref, expected, root, git, entries, release, release_tree, documents)
    return expected
