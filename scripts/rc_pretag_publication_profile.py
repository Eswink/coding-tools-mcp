"""Finite publication source and guard composition; external review binds self-bytes."""
import rc_pretag_ownership_profile as ownership
import rc_pretag_desktop_profile as desktop
import rc_pretag_nginx_profile as nginx
import rc_pretag_two_hop_profile as two_hop
import rc_pretag_authenticated_two_hop_profile as authenticated

PROFILE_ID = 'engineering/issue88-publication-core-composition-v1'
N = 'e459c9bec1dc6006eaad6df5f65111491c7b7572'
N_TREE = '1eae7b72539740c2a1cc167a82ec2af3b5f951d6'
N_PARENTS = ('a88be4901623f7c8629b93df984166587253f0be', '65b04eda5d63b8457b5b8879cd97d391e5e2b021')
# Structural source only, never an admissible candidate. Bound after source freeze.
S = 'ca1369c74b7fdd719bda7dc2bf01f020ee2bad05'
S_TREE = '6247cac476e4690560e74da481e086c4e4644f51'
R, R_TREE, R_DOCUMENTS = authenticated.R, authenticated.R_TREE, authenticated.R_DOCUMENTS
CORE = 'scripts/rc_publication_contract.py'
CORE_TESTS = 'scripts/rc_pretag_publication_contract_tests.py'
COMPOSITION = authenticated.COMPOSITION
DESKTOP_TESTS = authenticated.DESKTOP_TESTS
NGINX_TESTS = authenticated.NGINX_TESTS
TWO_HOP_TESTS = authenticated.TWO_HOP_TESTS
AUTHENTICATED_TESTS = authenticated.TESTS
PROFILE = 'scripts/rc_pretag_publication_profile.py'
TESTS = 'scripts/rc_pretag_publication_tests.py'
# Frozen mode/blob/SHA256/byte/line pins, never candidate-derived.
SOURCE_PINS = {
    'docs/specs/issue88-publication-core/design.md': ('100644', '98d4567d5243970bec0e25c7362fdb2a79d49558', '28499cc9c201814b0c1bc89bbafa7781f598f445880acfe7aab9a3cb467464e9', 8064, 80),
    'docs/specs/issue88-publication-core/requirements.md': ('100644', 'b1ce6933f4624dc41440bb1292a64e70bae5ec47', 'ebce98dac09d52a59c08c0d6042a47f47198f91c14950b77d218a49a71ea021d', 5019, 45),
    'docs/specs/issue88-publication-core/tasks.md': ('100644', 'aba7621fa524a0f0e1b7f1cdae01a491c784d61f', '6a555780024ec64d500d25c90cac582ee66a38b045b24d5f7051061e5573b429', 4145, 51),
    'scripts/rc_pretag_publication_contract_tests.py': ('100644', 'b1e1579fc56a1422559d8139f21ba439b8f6e7a2', 'd7aca78c1f701bfb4cec0614317aacf63407247766b2942167e93d238fa601ad', 29736, 481),
    'scripts/rc_publication_contract.py': ('100644', '33d2fcfc41143d7e02a0dadb467667b9c2eef118', 'dcf9c523c1eadf8b01e872522788587cf0478ffa81cc94b582edc3be597f4e80', 23098, 460),
}
SOURCE_CAPS = {CORE: (460, 460), CORE_TESTS: (500, 500),
    'docs/specs/issue88-publication-core/requirements.md': (120, 120),
    'docs/specs/issue88-publication-core/design.md': (180, 180),
    'docs/specs/issue88-publication-core/tasks.md': (120, 120)}
SOURCE_DELTA_LIMIT = 1340
# Six non-self files; independent external manifest binds this profile.
AMENDMENT_PINS = {
    'scripts/rc_pretag_composition_tests.py': ('95dfabcc23ffc2931e035c96e4026cfe2cf241c3', 'f74fb9c64d7b48899820987f21305656c760592365b44755a23d11f6c21a80f7'),
    'scripts/rc_pretag_desktop_tests.py': ('167fd02870b5594aaddb8e35906a724ca60f34be', '30801775c4c5ff7c957d76859e9c47a4bf1cefc73a92f2a77f37af58a865df29'),
    'scripts/rc_pretag_nginx_tests.py': ('5204e288808619e2129a5fbff767ed421c903abc', '980237a9e17a1cbb7a20c0e5bcac701a0ee5d008950e2fc41efe35d64f442ef8'),
    'scripts/rc_pretag_two_hop_tests.py': ('8f6b723614fe803110d2244906ec68d2c0262087', '42c39baf63975f170781e8d2f6c0586cda7f5fe3daac5e9fc9cf562cce7c2fd3'),
    'scripts/rc_pretag_authenticated_two_hop_tests.py': ('60b5b27af58c24b6f5c45e60f309b14873aba8aa', 'df345bd9bad8fe0108d77239297fc06ed6fb6532852fd0413f15d64e1b1635b5'),
    'scripts/rc_pretag_publication_tests.py': ('2cdb3256c4662fd610e93fee1a78b1c80de66d49', 'f87cf266d837ad2f9dbfa04a21c6622623a31aa534a8c2066f569b182f9996b7'),
}
AMENDMENT_CAPS = {COMPOSITION: (500, 24), DESKTOP_TESTS: (400, 36), NGINX_TESTS: (480, 44),
    TWO_HOP_TESTS: (500, 44), AUTHENTICATED_TESTS: (500, 100), PROFILE: (400, 400), TESTS: (500, 500)}
AMENDMENT_DELTA_LIMIT = 1050
EXPECTED_GROUPS = {
    'rc_pretag_publication_contract_tests.PublicationContractTests': (
        'test_exact_six_asset_plan_uses_consumer_payload_contract '
        'test_canonical_rc_subject_and_exact_tag_binding '
        'test_subject_numeric_digest_and_size_bounds '
        'test_missing_extra_duplicate_or_path_asset_rejected '
        'test_original_false_flags_and_blockers_preserved '
        'test_serialized_plan_is_never_authorization '
        'test_module_has_no_io_entrypoint_or_executable_adapter '
        'test_missing_failed_unknown_or_stale_fence_blocks '
        'test_historical_pretag_absence_and_current_tag_are_distinct '
        'test_absent_annotated_moved_or_foreign_tag_blocks '
        'test_collision_or_unproven_draft_visibility_blocks '
        'test_draft_intent_preserves_prerelease_and_latest '
        'test_draft_response_and_inventory_identity_must_match '
        'test_six_uploads_are_ordered_and_nonoverwriting '
        'test_every_upload_requires_fresh_subject_and_byte_fence '
        'test_upload_response_cannot_replace_expected_asset_identity '
        'test_downloaded_size_and_hash_must_match_each_asset '
        'test_exact_final_draft_inventory_required '
        'test_publish_wait_has_no_automatic_effect '
        'test_publish_request_binds_subject_and_draft_but_grants_no_authority '
        'test_publish_requires_new_final_fence '
        'test_publish_intent_cannot_promote_stable_or_latest '
        'test_public_metadata_and_anonymous_six_hashes_required '
        'test_stable_latest_drift_fails_verification '
        'test_duplicate_stale_out_of_order_and_wrong_kind_results_reject '
        'test_confirmed_no_effect_and_partial_draft_are_distinct '
        'test_uncertain_mutation_is_sticky_and_never_retried '
        'test_cancellation_and_adapter_errors_are_sanitized '
        'test_published_unverified_is_not_no_effect_or_success '
        'test_complete_model_trace_is_bounded_and_never_real_approval '
    ),
    'rc_pretag_publication_tests.PublicationCompositionTests': (
        'test_exact_n_anchor_tree_parents_and_historical_validation '
        'test_source_s_has_only_five_reviewed_additions '
        'test_source_blob_digest_size_lines_and_modes_are_pinned '
        'test_candidate_c_has_only_seven_guard_changes '
        'test_source_only_candidate_and_correction_chains_reject '
        'test_feature_merge_requires_ordered_parents_and_entire_c_tree '
        'test_release_overlay_has_only_four_exact_historical_documents '
        'test_missing_reversed_extra_duplicate_and_nested_parents_reject '
        'test_unknown_anchor_and_same_tree_impostor_reject '
        'test_missing_extra_renamed_symlink_gitlink_and_binary_paths_reject '
        'test_individual_and_aggregate_budgets_reject '
        'test_five_historical_profiles_and_all_historical_pins_are_immutable '
        'test_five_adapter_inverses_recover_exact_n_bytes '
        'test_adapter_method_names_and_assertions_are_preserved '
        'test_outside_fragment_and_missing_duplicate_fragment_edits_reject '
        'test_historical_content_failure_is_terminal_without_fallback '
        'test_mutable_refs_and_ambient_git_redirection_cannot_change_identity '
        'test_frozen_233_plus_50_named_inventory_is_exact '
        'test_protected_source_versions_gates_workflows_and_old_452_are_unchanged '
        'test_core_exposes_only_closed_inert_operations_and_false_approval_reports '
    ),
}


def publication_topology(ref, root, git, release):
    """Only C=[S], I=[N,C], J=[R,I]; reject S and correction chains."""
    if release != R:
        raise ownership.TopologyError('publication_release_anchor')

    def candidate(tip):
        if tip == S or ownership._parents(tip, root, git) != [S]:
            raise ownership.TopologyError('publication_candidate_parent')
        return tip

    def feature(tip):
        parents = ownership._parents(tip, root, git)
        if len(parents) != 2 or parents[0] != N:
            raise ownership.TopologyError('publication_feature_parents')
        return tip, candidate(parents[1])

    parents = ownership._parents(ref, root, git)
    if parents and parents[0] == release:
        if len(parents) != 2:
            raise ownership.TopologyError('publication_release_parents')
        tip, source = feature(parents[1])
        kind = 'release'
    elif len(parents) == 2 and parents[0] == N:
        tip, source = feature(ref)
        kind = 'nonrelease'
    else:
        tip = source = candidate(ref)
        kind = 'nonrelease'
    if ownership._parents(S, root, git) != [N]:
        raise ownership.TopologyError('publication_source_parent')
    if tuple(ownership._parents(N, root, git)) != N_PARENTS:
        raise ownership.TopologyError('publication_anchor_parents')
    return kind, tip, source


def publication_content(ref, root, git, entries, historical, release, release_tree, documents):
    """Exactly five additive, pinned source files over authenticated N."""
    assert (release, release_tree, documents) == (R, R_TREE, R_DOCUMENTS)
    assert tuple(ownership._parents(N, root, git)) == N_PARENTS
    assert ownership._parents(S, root, git) == [N]
    assert git('rev-parse', N + '^{tree}', root=root).decode().strip() == N_TREE
    assert git('rev-parse', S + '^{tree}', root=root).decode().strip() == S_TREE
    original = authenticated.selected_profile(
        N, root, git, entries, historical, release, release_tree, documents)
    assert len(original) == 1678 and len(SOURCE_PINS) == 5
    assert SOURCE_PINS.keys() == SOURCE_CAPS.keys()
    assert not original.keys() & SOURCE_PINS.keys()
    expected = original | {path: (mode, 'blob', blob)
                           for path, (mode, blob, _, _, _) in SOURCE_PINS.items()}
    assert len(expected) == 1683
    assert entries(S, root) == expected and entries(ref, root) == expected
    data = {}
    for path, (mode, blob, digest, size, lines) in SOURCE_PINS.items():
        assert mode == '100644', path
        data[path] = git('cat-file', 'blob', blob, root=root)
        assert ownership.pin(data[path]) == (blob, digest), path
        assert (len(data[path]), len(data[path].splitlines())) == (size, lines), path
    authenticated._budgets(S, N, root, git, data, SOURCE_CAPS, SOURCE_DELTA_LIMIT, 'publication_source_delta_budget')
    return expected


def amendment_content(ref, baseline, root, git, entries):
    """Exactly seven guard changes; no historical source/profile repinning."""
    actual = entries(ref, root)
    paths = AMENDMENT_CAPS.keys()
    assert AMENDMENT_PINS.keys() == paths - {PROFILE}
    assert baseline.keys() & paths == {COMPOSITION, DESKTOP_TESTS, NGINX_TESTS, TWO_HOP_TESTS, AUTHENTICATED_TESTS}
    assert actual.keys() == baseline.keys() | paths and len(actual) == 1685
    assert {path for path in actual if actual[path] != baseline.get(path)} == paths
    assert all(actual[path] == value for path, value in baseline.items() if path not in paths)
    assert all(actual[path][:2] == ('100644', 'blob') for path in paths)
    data = {path: git('cat-file', 'blob', actual[path][2], root=root) for path in paths}
    for path, expected in AMENDMENT_PINS.items():
        assert ownership.pin(data[path]) == expected, path
    authenticated._budgets(ref, S, root, git, data, AMENDMENT_CAPS, AMENDMENT_DELTA_LIMIT,
                           'publication_amendment_delta_budget')
    old_data = {path: git('cat-file', 'blob', actual[path][2], root=root) for path in ownership.CAPS}
    ownership.budgets(ref, root, git, old_data)
    return actual


def selected_profile(ref, root, git, entries, historical, release, release_tree, documents, *, profile=PROFILE_ID):
    assert profile == PROFILE_ID, 'unknown_composition_profile'
    ref = ownership._commit(ref, root, git)
    # Catch topology failures only. A selected profile owns every content error.
    for topology, select in ((ownership.topology, ownership.selected_profile),
                             (desktop.desktop_topology, desktop.selected_profile),
                             (nginx.nginx_topology, nginx.selected_profile),
                             (two_hop.two_hop_topology, two_hop.selected_profile),
                             (authenticated.authenticated_two_hop_topology, authenticated.selected_profile)):
        try:
            topology(ref, root, git, release)
        except ownership.TopologyError:
            continue
        return select(ref, root, git, entries, historical, release, release_tree, documents)
    kind, tip, source = publication_topology(ref, root, git, release)
    expected = publication_content(S, root, git, entries, historical, release, release_tree, documents)
    expected = amendment_content(source, expected, root, git, entries)
    if tip != source:
        assert entries(tip, root) == expected
    if kind == 'release':
        return ownership.release_content(ref, expected, root, git, entries, release, release_tree, documents)
    return expected
