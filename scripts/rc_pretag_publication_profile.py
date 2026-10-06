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
# Seven original guards remain separate from the six exact ancillary replacements.
AMENDMENT_PINS = {
    'scripts/rc_pretag_composition_tests.py': ('959bddf9d5f32767e033418bb4823e8c7ef32a77', '132fb6b5760fbefdb0d728f8400d3ee8544c6218329483e5ec5828d2f6b81cf6'),
    'scripts/rc_pretag_desktop_tests.py': ('37a6158c35fa91f33383b2f2c3d082d94d741239', '7a29c931ad2af686bea514daf2daa75c673fb228668d716fcd18c9d65dd33308'),
    'scripts/rc_pretag_nginx_tests.py': ('06043091e768498c63f3344e3d5a251baf24ead5', '2cc94475d5a25e93cb4e0eb85d3fe674b31b7cf72bbaca9ad3b618e04e388274'),
    'scripts/rc_pretag_two_hop_tests.py': ('eb642096b78b69f182e4d49ed4eab2a572fb42bb', 'a2cee34550cc71f5cdd56454e5c74d8722893dfe074b5c58882c9be415246378'),
    'scripts/rc_pretag_authenticated_two_hop_tests.py': ('a4b1f1b5c62b485616c8436fc78e838acaa3c52c', 'a043244af11254809841ca9980ab7c2bda5298e4c26de8eed97f02c6c1c4cf97'),
    'scripts/rc_pretag_publication_tests.py': ('8e0a4d4a4165b138ea0923a40d133c28146b0a64', 'c67aa17865cc364cc170bb8844a3d4287036452b6b8ed57be694baeb1b023050'),
}
AMENDMENT_CAPS = {COMPOSITION: (500, 24), DESKTOP_TESTS: (400, 36), NGINX_TESTS: (480, 44),
    TWO_HOP_TESTS: (500, 44), AUTHENTICATED_TESTS: (500, 100), PROFILE: (400, 400), TESTS: (500, 500)}
OWNERSHIP_TESTS = 'scripts/rc_pretag_ownership_tests.py'
OWNERSHIP_PINS = {OWNERSHIP_TESTS: ('ec89a839c11dfffb37923086a3c35ba5455a28c8',
    'ab67f3fc6eb172377dfab672e25023c55f9c2936db103e170719b65cd0150fc6')}
CONTRACTS = '.github/workflows/rc-pretag-contract-checks.yml'
CHECKS = '.github/workflows/rc-pretag-evidence-checks.yml'
TIMEOUT_BASE_PINS = {
    CONTRACTS: ('445daa1c6a8f81aab7393e527a04af1819c31851', '287fde1aa2641d4d7ee40060d4116365af7aa8b8ee38ed9140cba576f3532db9'),
    CHECKS: ('a88058a7142ca2d5890e91e9926c66e40240c483', '00565b5a5b5427559c831c820a29971ff58417e6a5d75a3f2095bd9adf3c84ca'),
}
TIMEOUT_SHAPES = {CONTRACTS: (2988, 74), CHECKS: (3292, 81)}
ANCILLARY_CAPS = {CONTRACTS: (74, 2), CHECKS: (81, 2), OWNERSHIP_TESTS: (380, 24),
    'docs/specs/issue88-publication-core/requirements.md': (120, 20),
    'docs/specs/issue88-publication-core/design.md': (180, 50),
    'docs/specs/issue88-publication-core/tasks.md': (120, 20)}
ANCILLARY_PINS = {
    '.github/workflows/rc-pretag-contract-checks.yml': ('7e14b1eac469d701eefcfe0f6217c0dfbdc5e23a', '403c8ff26699ed5ff59f93f6adeff440e46b5abd7acdb23b81a6770f7c95fc50'),
    '.github/workflows/rc-pretag-evidence-checks.yml': ('118cca70c53f4df87afed7de77a8d5c54cdd9eb4', '316460d53ce382dee2c2f4c5039c274e876bdbf41c1fe5f3053763160842f15c'),
    'scripts/rc_pretag_ownership_tests.py': ('4bf8ddbe8b2b2ffc3c0bbea1a473cf0c26d6b56e', '8f40b75ada5a5ba0d6dd652aa015ed28a7fd1af22d2c603db3b0d40b420af0d5'),
    'docs/specs/issue88-publication-core/requirements.md': ('d8c92ca56ca89ae9944310c1d26ec3482c5a6a32', 'c68ec9598f0e39d657a7de9c8683b726ed9a1722dcfa1b1adee88df5e0960acd'),
    'docs/specs/issue88-publication-core/design.md': ('b8b7340f513f01033b39c3b1fd85d68ad83d7ffc', 'af47592753becbffe36d241f53ef41517a0f2c0e30dd3be8681f0e4b377b9784'),
    'docs/specs/issue88-publication-core/tasks.md': ('6cfbd7e7ce0ad9e09b35b778dda83be1320707e2', 'ca0442e103ba78b666dca90536a713d37274416f2d62a98f57dab8bb3f925838'),
}
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


def timeout_inverse(path, current):
    """Accept only the two pinned 15-to-20 changes and recover their entire old bytes."""
    assert path in TIMEOUT_BASE_PINS and ownership.pin(current) == ANCILLARY_PINS[path]
    assert (len(current), len(current.splitlines())) == TIMEOUT_SHAPES[path]
    old, new = b'    timeout-minutes: 15\n', b'    timeout-minutes: 20\n'
    assert current.splitlines(keepends=True).count(new) == 1 and old not in current
    restored = current.replace(new, old, 1)
    assert ownership.pin(restored) == TIMEOUT_BASE_PINS[path], 'complete timeout inverse'
    return restored


def amendment_content(ref, baseline, root, git, entries):
    """Seven guards plus six exact replacements; historical source/pins stay fixed."""
    actual = entries(ref, root)
    assert not AMENDMENT_CAPS.keys() & ANCILLARY_CAPS.keys()
    caps = AMENDMENT_CAPS | ANCILLARY_CAPS
    paths = caps.keys()
    assert AMENDMENT_PINS.keys() == AMENDMENT_CAPS.keys() - {PROFILE}
    assert ANCILLARY_PINS.keys() == ANCILLARY_CAPS.keys()
    assert baseline.keys() & paths == {COMPOSITION, DESKTOP_TESTS, NGINX_TESTS, TWO_HOP_TESTS, AUTHENTICATED_TESTS} | ANCILLARY_CAPS.keys()
    assert actual.keys() == baseline.keys() | paths and len(actual) == 1685
    assert {path for path in actual if actual[path] != baseline.get(path)} == paths
    assert all(actual[path] == value for path, value in baseline.items() if path not in paths)
    assert all(actual[path][:2] == ('100644', 'blob') for path in paths)
    data = {path: git('cat-file', 'blob', actual[path][2], root=root) for path in paths}
    for path, expected in (AMENDMENT_PINS | ANCILLARY_PINS).items():
        assert ownership.pin(data[path]) == expected, path
    for path in TIMEOUT_BASE_PINS: timeout_inverse(path, data[path])
    authenticated._budgets(ref, S, root, git, data, caps, AMENDMENT_DELTA_LIMIT,
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
