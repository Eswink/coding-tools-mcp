"""Exact authenticated two-hop composition; external review binds profile self-bytes."""
import rc_pretag_ownership_profile as ownership
import rc_pretag_desktop_profile as desktop
import rc_pretag_nginx_profile as nginx
import rc_pretag_two_hop_profile as two_hop

PROFILE_ID = 'engineering/issue40-authenticated-two-hop-composition-v1'
M = 'a88be4901623f7c8629b93df984166587253f0be'
M_TREE = '246213487851c01a6def74b7519e58a6d709c180'
M_PARENTS = ('44b9f9b16f6981297bd1252eb3ab238ae581eccc', '3a606e06b0bc0ee834ea4c7021652e9e60aac7f2')
# Frozen structural source; only its exact guard amendment is a candidate.
P = 'fad6b75d6a5d4ae4e5749c26f0371c4c6830d73b'
P_TREE = '3d462c6792b36569820e3b85a90abc35d40f4d66'
R = 'e2e011f7f2a3a1df838bbd588106205b999db610'
R_TREE = 'c0dfe00fdcc7ebc8e26acaad5d18ff3f94df9ba3'
R_DOCUMENTS = two_hop.R_DOCUMENTS
COMPOSITION = 'scripts/rc_pretag_composition_tests.py'
DESKTOP_TESTS = 'scripts/rc_pretag_desktop_tests.py'
NGINX_TESTS = 'scripts/rc_pretag_nginx_tests.py'
TWO_HOP_TESTS = 'scripts/rc_pretag_two_hop_tests.py'
PROFILE = 'scripts/rc_pretag_authenticated_two_hop_profile.py'
TESTS = 'scripts/rc_pretag_authenticated_two_hop_tests.py'
# Thirteen immutable P entries: mode/blob/SHA256/bytes/lines.
SOURCE_PINS = {
    'tests/cloud-gateway-deployment/container_fixture.py': ('100644', '57c859c2454ad179038751edf5f774a18bafb094', 'f2323028e9291846bfa75ca34029c309ed21a51094b05caa1d96f8c695f3ef30', 18234, 275),
    'tests/cloud-gateway-deployment/run_current_nginx_agent.py': ('100644', '72177da0143f23408b569be2db281fdf1b796618', '4331734362699bfc54dce7ddbe76279f601e8776a5738e5bb7c5cc3a2e54d42b', 29730, 500),
    'services/cloud-gateway/tests/host_agent_support/relay.py': ('100644', 'f6ba1cf38e1c4328f4e05d7db1428f792ce5580e', '5e71d38a7cc5eb96dc37458182ef39509ab114e53d6c47a97a8eb0da768f94fe', 4399, 95),
    'src-tauri/src/tools/cloud_host/live/wss_tests.rs': ('100644', '756160521ea1f921bd4f1247756dab1f2ab51abd', '691bd4cc1d57fc7ba5728cce365d2dc28000afad944397131de1a31fa850ae30', 15988, 431),
    'src-tauri/src/tools/cloud_host/live/wss_two_hop_tests.rs': ('100644', 'e3b6b3a31c4076f1d7d59f64b8b9df3ba879f4d2', 'e321044f5b38916abe0867aa0e55410c19fcfec39f3817a50273ed91a7bb3ee9', 11291, 281),
    'src-tauri/src/tools/cloud_host/live/wss_two_hop_support.rs': ('100644', '02d9fdf4df4dde94a99ff15ff78c0aa8c703fa55', '77c054cd6f1237e71bfa5ef284006c134035a5ddf1cdf6f6257caae24b71eaa9', 16494, 438),
    'src-tauri/Cargo.toml': ('100644', 'feead83a470fe3b07ad432806a6c657f3ab7a44e', '9603b57332e9d08a57bc0e31f7b28f2c1409d59cd6548b13c8e2f902796f36c8', 2856, 95),
    'tests/cloud-gateway-deployment/test_current_nginx_two_hop.py': ('100644', '70324dc8933ec9d707823fbce4f927c6ad7d5139', 'd58ae828e94ae3ce97bbe7acc0d924ee68eca81bff7670f90027b4b8b1fcb9ed', 24726, 389),
    '.github/workflows/issue40-current-nginx-include.yml': ('100644', '5334ca48134d6c67d8faeeafd84c20ab4e5405fa', '4eeb34bb40dabdfee0500f6341257cee42fe3c8cc72bdc1be4320805c95f7c9c', 20414, 283),
    'docs/deployment/current-nginx-include.md': ('100644', 'f6eb31c7ed70d5f4088e3efc9df18f526d2bea3c', '833e38d483d6dda45a98ac6be8ac3aab820fcef8303e5a77b4928b5dcb1a51da', 17314, 271),
    'docs/specs/issue40-authenticated-two-hop/requirements.md': ('100644', 'd7344ff181e95eb84a05408da715121c696a9d66', '38f2286683e0fe712b8e14b34e0ad098e1248b68ae81b9486299c0059719b8d6', 4891, 49),
    'docs/specs/issue40-authenticated-two-hop/design.md': ('100644', '8c243c92e080bd7d705052f54381fb17cf512c94', '85d6171c376526c6fc31d703cb608f11cfe9bfa17d4f28a96d5eb3f373f75181', 9115, 67),
    'docs/specs/issue40-authenticated-two-hop/tasks.md': ('100644', '4f1a0abc05329876e77e9f115ab825ca0412e555', '3b4742c82351a28710a548f650dfe96d206cf3e6f85e3e35a6d0ae4c158a1832', 4085, 57),
}
SOURCE_CAPS = {
    'tests/cloud-gateway-deployment/container_fixture.py': (320, 32),
    'tests/cloud-gateway-deployment/run_current_nginx_agent.py': (500, 500),
    'services/cloud-gateway/tests/host_agent_support/relay.py': (160, 180),
    'src-tauri/src/tools/cloud_host/live/wss_tests.rs': (500, 180),
    'src-tauri/src/tools/cloud_host/live/wss_two_hop_tests.rs': (500, 500),
    'src-tauri/src/tools/cloud_host/live/wss_two_hop_support.rs': (500, 500),
    'src-tauri/Cargo.toml': (100, 4),
    'tests/cloud-gateway-deployment/test_current_nginx_two_hop.py': (480, 260),
    '.github/workflows/issue40-current-nginx-include.yml': (440, 240),
    'docs/deployment/current-nginx-include.md': (320, 150),
    'docs/specs/issue40-authenticated-two-hop/requirements.md': (120, 120),
    'docs/specs/issue40-authenticated-two-hop/design.md': (200, 200),
    'docs/specs/issue40-authenticated-two-hop/tasks.md': (120, 120),
}
SOURCE_DELTA_LIMIT = 2200
# Five non-self whole-file pins; external review authenticates this profile.
AMENDMENT_PINS = {
    'scripts/rc_pretag_composition_tests.py': ('00d8e657375a479779d7c06ef33cb847ff9f49d0', 'e8c1ac54d30a4030f9b843aeee1c1ff1a94013641f533f1e97e35603d25e8c74'),
    'scripts/rc_pretag_desktop_tests.py': ('1c88b02960254a83c783dfc2abfbdbabda9b312a', 'd1ead48fbb40a5000dbb3647b11ad9cb4f9c1fde08bd53bf1afa97244358d6df'),
    'scripts/rc_pretag_nginx_tests.py': ('4f5f1eae78c25dd1d89080c52a68a8f2fe011f48', '65800c843734373352109e59b1034c613cea6126478be5784522d0b5f7604818'),
    'scripts/rc_pretag_two_hop_tests.py': ('312eba4905de484e7628b653aaa404f1019c06a4', 'd8de0235d3dca4c2fc84c37d7c3fa0b1c01442c722e2fa1168bedd5fc6884147'),
    'scripts/rc_pretag_authenticated_two_hop_tests.py': ('4765aceb4c96d90d2f3cde6e249abc02706860ef', '80d61839a1c774be3210c3293c3592acdbbbb53e8b5eaa1479a8dba2ac0548a0'),
}
AMENDMENT_CAPS = {COMPOSITION: (500, 24), DESKTOP_TESTS: (400, 32), NGINX_TESTS: (480, 40),
    TWO_HOP_TESTS: (480, 48), PROFILE: (360, 360), TESTS: (480, 480)}
AMENDMENT_DELTA_LIMIT = 900
EXPECTED_GROUPS = {'rc_pretag_authenticated_two_hop_tests.AuthenticatedTwoHopCompositionTests': (
    'test_amendment_chains_nested_merges_and_descendants_reject '
    'test_amendment_pins_scope_binary_and_individual_total_budgets_reject '
    'test_composition_inverse_recovers_exact_m_and_rejects_fragment_drift '
    'test_desktop_adapter_inverse_preserves_all_historical_assertions '
    'test_each_native_source_blob_digest_size_and_line_pin_rejects_drift '
    'test_exact_m_parent_tree_and_two_hop_validation '
    'test_exact_source_p_and_amendment_a_bind_without_p_candidate '
    'test_frozen_209_plus_24_inventory_is_exactly_loaded_and_executed '
    'test_frozen_four_profiles_and_pins_remain_exact '
    'test_historical_protected_entries_and_six_version_slots_remain_exact '
    'test_historical_unauthenticated_proof_cannot_replace_authenticated_source '
    'test_missing_extra_rename_mode_symlink_and_gitlink_entries_reject '
    'test_mutable_refs_and_ambient_git_redirection_cannot_change_identity '
    'test_native_p_sole_parent_tree_and_thirteen_path_delta '
    'test_nginx_adapter_inverse_preserves_all_historical_assertions '
    'test_ordered_feature_merge_requires_complete_source_tree '
    'test_release_document_byte_mode_path_and_deletion_drift_rejects '
    'test_release_overlay_contains_only_four_exact_documents '
    'test_reversed_duplicate_missing_and_extra_parents_reject_before_content '
    'test_single_publish_candidate_keeps_native_and_validator_identity_separate '
    'test_topology_dispatch_keeps_all_legacy_content_failures_terminal '
    'test_two_hop_adapter_preserves_source_fixtures_and_budget_negatives '
    'test_unknown_missing_and_same_tree_impostor_anchors_reject '
    'test_unknown_profiles_and_native_release_approval_claims_reject '
)}


def authenticated_two_hop_topology(ref, root, git, release):
    """Only A=[P], I=[M,A], L=[R,I]; P is structural source, never a candidate."""
    if release != R:
        raise ownership.TopologyError('authenticated_release_anchor')

    def candidate(tip):
        if tip == P or ownership._parents(tip, root, git) != [P]:
            raise ownership.TopologyError('authenticated_amendment_parent')
        return tip

    def feature(tip):
        parents = ownership._parents(tip, root, git)
        if len(parents) != 2 or parents[0] != M:
            raise ownership.TopologyError('authenticated_feature_parents')
        return tip, candidate(parents[1])

    parents = ownership._parents(ref, root, git)
    if parents and parents[0] == release:
        if len(parents) != 2:
            raise ownership.TopologyError('authenticated_release_parents')
        tip, source = feature(parents[1]); kind = 'release'
    elif len(parents) == 2 and parents[0] == M:
        tip, source = feature(ref); kind = 'nonrelease'
    else:
        tip = source = candidate(ref); kind = 'nonrelease'
    if ownership._parents(P, root, git) != [M]:
        raise ownership.TopologyError('authenticated_source_parent')
    if tuple(ownership._parents(M, root, git)) != M_PARENTS:
        raise ownership.TopologyError('authenticated_anchor_parents')
    return kind, tip, source


def _budgets(ref, baseline, root, git, data, caps, limit, label):
    total = 0
    for path, (line_cap, diff_cap) in caps.items():
        assert len(data[path].splitlines()) <= line_cap, path
        rows = git('diff', '--numstat', baseline, ref, '--', path, root=root).splitlines()
        assert len(rows) == 1, path
        fields = rows[0].split(b'\t')
        assert len(fields) == 3 and fields[2] == path.encode(), path
        assert all(v and all(48 <= c <= 57 for c in v) for v in fields[:2]), path
        delta = sum(map(int, fields[:2])); assert delta <= diff_cap, path
        total += delta
    assert total <= limit, label


def authenticated_two_hop_content(ref, root, git, entries, historical, release, release_tree, documents):
    """Exact structural P overlay; this does not admit P as a selected candidate."""
    assert (release, release_tree, documents) == (R, R_TREE, R_DOCUMENTS)
    assert tuple(ownership._parents(M, root, git)) == M_PARENTS
    assert ownership._parents(P, root, git) == [M]
    assert git('rev-parse', M + '^{tree}', root=root).decode().strip() == M_TREE
    assert git('rev-parse', P + '^{tree}', root=root).decode().strip() == P_TREE
    original = two_hop.selected_profile(
        M, root, git, entries, historical, release, release_tree, documents)
    assert len(original) == 1670 and len(SOURCE_PINS) == 13 and SOURCE_PINS.keys() == SOURCE_CAPS.keys()
    assert len(original.keys() & SOURCE_PINS.keys()) == 7
    expected = original | {path: (mode, 'blob', blob)
                           for path, (mode, blob, _, _, _) in SOURCE_PINS.items()}
    assert len(expected) == 1676
    assert {p for p in expected if expected[p] != original.get(p)} == SOURCE_PINS.keys()
    assert entries(P, root) == expected and entries(ref, root) == expected
    source_data = {}
    for path, (mode, blob, digest, size, lines) in SOURCE_PINS.items():
        assert mode == '100644', path
        data = git('cat-file', 'blob', blob, root=root)
        assert ownership.pin(data) == (blob, digest), path
        assert (len(data), len(data.splitlines())) == (size, lines), path
        source_data[path] = data
    _budgets(P, M, root, git, source_data, SOURCE_CAPS, SOURCE_DELTA_LIMIT, 'authenticated_source_delta_budget')
    return expected


def amendment_content(ref, baseline, root, git, entries):
    """Exactly six reviewed guard files; native and historical source stays frozen."""
    actual = entries(ref, root); paths = AMENDMENT_CAPS.keys()
    assert AMENDMENT_PINS.keys() == paths - {PROFILE}
    assert set(baseline) & paths == {COMPOSITION, DESKTOP_TESTS, NGINX_TESTS, TWO_HOP_TESTS}
    assert actual.keys() == baseline.keys() | paths and len(actual) == 1678
    assert {p for p in actual if actual[p] != baseline.get(p)} == paths
    assert all(actual[p] == value for p, value in baseline.items() if p not in paths)
    assert all(actual[p][:2] == ('100644', 'blob') for p in paths)
    data = {p: git('cat-file', 'blob', actual[p][2], root=root) for p in paths}
    for path, expected in AMENDMENT_PINS.items():
        assert ownership.pin(data[path]) == expected, path
    _budgets(ref, P, root, git, data, AMENDMENT_CAPS, AMENDMENT_DELTA_LIMIT, 'authenticated_amendment_delta_budget')
    old_data = {p: git('cat-file', 'blob', actual[p][2], root=root) for p in ownership.CAPS}
    ownership.budgets(ref, root, git, old_data)
    return actual


def selected_profile(ref, root, git, entries, historical, release, release_tree, documents, *, profile=PROFILE_ID):
    assert profile == PROFILE_ID, 'unknown_composition_profile'
    ref = ownership._commit(ref, root, git)
    # Only topology errors permit trying another profile; selected content is terminal.
    for topology, select in ((ownership.topology, ownership.selected_profile),
                             (desktop.desktop_topology, desktop.selected_profile),
                             (nginx.nginx_topology, nginx.selected_profile),
                             (two_hop.two_hop_topology, two_hop.selected_profile)):
        try:
            topology(ref, root, git, release)
        except ownership.TopologyError:
            continue
        return select(ref, root, git, entries, historical, release, release_tree, documents)
    kind, tip, source = authenticated_two_hop_topology(ref, root, git, release)
    expected = authenticated_two_hop_content(P, root, git, entries, historical, release, release_tree, documents)
    expected = amendment_content(source, expected, root, git, entries)
    if tip != source:
        assert entries(tip, root) == expected
    if kind == 'release':
        return ownership.release_content(ref, expected, root, git, entries, release, release_tree, documents)
    return expected
