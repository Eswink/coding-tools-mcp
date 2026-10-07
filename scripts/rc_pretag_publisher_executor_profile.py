"""Finite publisher source composition; independent full-tree review binds this module."""
import rc_pretag_ownership_profile as o
import rc_pretag_publication_profile as p

M = '5beda478f4d04e7a352d0bbc63e1496ee3bca668'
M_TREE = '8daa22b917f985e00ba4b00cae0d5a6f76651678'
M_PARENTS = ('b97c469b1bd7ffb9973a65e19b798d2573561d92', '1564836a538a28f8e6e2aa1c67491dc56f26f47e')
PROFILE = 'scripts/rc_pretag_publisher_executor_profile.py'
CASES = 'scripts/rc_pretag_publisher_executor_cases.py'
DISPATCHER = 'scripts/rc_pretag_yoke_repair_profile.py'
WORKFLOW = '.github/workflows/issue88-publication-executor.yml'
CAPS = {
    'scripts/rc_publication_executor.py': (300, 300),
    'scripts/rc_publication_github.py': (500, 500),
    'scripts/rc_publication_stage.py': (300, 300),
    'scripts/rc_publication_executor_cases.py': (350, 350),
    'scripts/rc_publication_github_cases.py': (450, 450),
    'scripts/rc_publication_stage_cases.py': (350, 350),
    'scripts/rc_publication_https_fixture.py': (300, 300),
    'docs/specs/issue88-publication-executor/requirements.md': (50, 50),
    'docs/specs/issue88-publication-executor/design.md': (90, 90),
    'docs/specs/issue88-publication-executor/tasks.md': (60, 60),
    'scripts/rc_pretag_publisher_executor_profile.py': (220, 220),
    'scripts/rc_pretag_publisher_executor_cases.py': (300, 300),
    '.github/workflows/issue88-publication-executor.yml': (100, 100),
    'scripts/rc_pretag_yoke_repair_profile.py': (160, 4),
}
DELTA_LIMIT = 3400
BASE_PINS = {DISPATCHER: ('100644', '3bd5191c3c39b82d6def2a4b358d014822365dc0', '394c5ad91355ca009999f6a7cc3025ab0436f35dddddd1616eb4942c39693016', 8638, 150)}
# Seal static nonself pins only after every reviewed source file is final.
SOURCE_PINS = {
    'scripts/rc_publication_executor.py': ('100644', 'a64cf4c91ad43c0efd35e0a5c8c0d1de96cdfd11', 'e13ceb317de92c724cecafac06875659f0eacd8e66aa2a76c964fdded176a02e', 9819, 235),
    'scripts/rc_publication_github.py': ('100644', 'b4d250974e89deeb241f2aa32a998cda17688e34', '62fbe64ffc69c15d0def289f13ff282ed4046fee05a584b20b228f92488f1d90', 23025, 474),
    'scripts/rc_publication_stage.py': ('100644', 'b4ecb6e7400c1937b68f1ac960e2f6f0ecda4b65', 'b5d0e8f575f24e9977989b183f7ca415bb7cdf0e6142d645b98ddeeab12c6216', 18170, 295),
    'scripts/rc_publication_executor_cases.py': ('100644', '9b3c84e25470a775329a8bb49704b329409a0576', '32d11ddd521fd9a0a4a947b1d5fb506d1a1dd955a45734afda2cf53a40e1e5fc', 16114, 298),
    'scripts/rc_publication_github_cases.py': ('100644', '1097fd0309671110156bfff25b3ffbd3732edb80', '923f429222a581de256501c86e1b0516a541ca5cde839895e2dbee6436bd7732', 22455, 363),
    'scripts/rc_publication_stage_cases.py': ('100644', '4892c21a527013380182bd2a6199885b891e06ff', '24c66c476a170a97c3251538a0befd9dd7e0253bc1c1c8c7d082ac4e4c645e73', 22516, 350),
    'scripts/rc_publication_https_fixture.py': ('100644', '685c97f89de9fb5c565999c700c306c5376b7442', '24076b28befe41350f86a340f98f058325b6d1df31b83db0fcf3f1c55970b81e', 10537, 214),
    'docs/specs/issue88-publication-executor/requirements.md': ('100644', '313cd182874479677e09013573b96c10f0ee7c55', '0344b09482ea0ef8a927637679735dc4760d591facc8d4a072decea49fa7006b', 4597, 28),
    'docs/specs/issue88-publication-executor/design.md': ('100644', '91f2b0e9d9ca6c796c5c06b15241028d71568011', '33f0e98870b5d55073116d6b0e464458f6f14185b2879136744c7a70dbf6579f', 7744, 35),
    'docs/specs/issue88-publication-executor/tasks.md': ('100644', '336e965a8f528d1625f085b1478fff17097fe2cd', '6a6d7d2be28349f1632a52a8dfcc008a629d139cfe6db500868aec1e8e8c3749', 4383, 47),
    'scripts/rc_pretag_publisher_executor_cases.py': ('100644', '8f95924dd66b6f416e10d6b7ab8f197dbe336358', 'd5c1b8283fc9914da3209e13c09ff9a946fff311baab39672715f6fc7d83b750', 20119, 300),
    '.github/workflows/issue88-publication-executor.yml': ('100644', 'c6cc466d9d2520b668508e6fbd9754f1ac1cc7ef', '850aea3f1d81c00322f8c8ca1adf84a5abddb5c75d916066394f41a521397e4e', 4677, 69),
    'scripts/rc_pretag_yoke_repair_profile.py': ('100644', '5bc06b9f41ce280a4b8e69348431875a03ee17d2', 'c8173c38d30655479a11799a68e6959188ec30f22e0ac29d9601ead8b385794b', 8855, 154),
}
DISPATCH = (
    b'    import rc_pretag_publisher_executor_profile as publisher\n'
    b'    selected = publisher.select(ref, root, git, entries, historical, release, release_tree, documents)\n'
    b'    if selected is not None:\n'
    b'        return selected\n'
)
NEW_CASES = {
    'rc_publication_executor_cases.ExecutorCases': (
        'test_live_entry_is_blocked_without_real_verifiers_and_tag_guarantee',
        'test_real_tls_complete_trace_pauses_until_explicit_request',
        'test_each_mutation_rechecks_current_owner_scope',
        'test_cancellation_before_dispatch_has_no_effect',
        'test_cancellation_after_possible_dispatch_is_sticky_unknown',
        'test_duplicate_reentrant_and_out_of_order_dispatch_reject',
        'test_lost_response_never_retries_or_clears_uncertainty',
        'test_confirmed_mutation_cleanup_failure_retains_known_ids',
        'test_read_failure_uses_existing_core_outcomes',
        'test_publish_request_never_grants_authority',
        'test_pause_close_is_local_only_and_cannot_resume',
        'test_final_cleanup_failure_prevents_success_report',
    ),
    'rc_publication_github_cases.GitHubCases': (
        'test_closed_methods_paths_headers_and_bodies',
        'test_complete_bounded_pagination_and_collision_rejection',
        'test_json_types_duplicates_limits_and_status_failures',
        'test_six_ordered_descriptor_uploads_match_wire_bytes',
        'test_direct_binary_download_rehashes_exact_bytes',
        'test_single_storage_redirect_strips_credentials',
        'test_unsafe_redirect_chain_hosts_and_ports_reject',
        'test_upload_502_starter_is_uncertain_without_retry',
        'test_disconnect_timeout_and_truncated_mutation_responses',
        'test_mismatched_success_retains_uncertain_effect',
        'test_anonymous_verification_and_latest_drift',
        'test_tls_validation_and_error_redaction',
    ),
    'rc_publication_stage_cases.StageCases': (
        'test_exact_selected_consumer_run_job_and_receipt_artifact',
        'test_receipt_zip_layout_and_original_bytes_are_bound',
        'test_missing_foreign_or_mutated_selection_rejects',
        'test_exact_final_archive_reuses_existing_validation',
        'test_original_plan_and_provenance_survive_clock_change',
        'test_six_fixed_rows_and_checksum_bytes_match_plan',
        'test_owned_handles_survive_pause_and_upload_without_reopen',
        'test_file_replacement_link_and_inventory_changes_reject',
        'test_inplace_size_and_hash_drift_rejects',
        'test_no_source_path_or_closed_consumer_ownership_transfer',
        'test_closure_on_success_failure_and_cancel',
        'test_mutable_selection_and_ambient_invocation_cannot_reselect',
    ),
    'rc_pretag_publisher_executor_cases.PublisherCompositionCases': (
        'test_exact_m_identity_and_fresh_historical_validation',
        'test_ordered_d_i_j_and_four_document_overlay',
        'test_wrong_repeated_nested_or_mutable_parents_reject',
        'test_exact_four_line_inverse_recovers_m_dispatcher',
        'test_all_paths_modes_pins_and_entry_counts_are_exact',
        'test_individual_and_total_budgets_fail_closed',
        'test_selected_and_historical_content_errors_are_terminal',
        'test_current_candidate_validation_is_never_cached',
        'test_core_consumer_policy_and_held_sources_unchanged',
        'test_readonly_workflow_and_live_activation_boundaries',
        'test_original1184_and_strict303_inventories_unchanged',
        'test_new48_inventory_and_exceptional_outcomes_reject',
    ),
}
CLASS = 'rc_pretag_publisher_executor_cases.PublisherCompositionCases'
NAMES = NEW_CASES[CLASS]
DIGEST = 'd785d738015c796bff8b27c4a698f0d9ac7e5914da96abcfbe91b0ced956f1e6'


def inverse(path, current):
    """Remove one exact dispatch fragment and recover the complete immutable M blob."""
    assert type(path) is str and path == DISPATCHER and type(current) is bytes
    row = SOURCE_PINS[path]
    assert (o.pin(current), len(current), len(current.splitlines())) == (row[1:3], row[3], row[4])
    assert current.count(DISPATCH) == 1, 'publisher inverse fragment missing or duplicated'
    restored = current.replace(DISPATCH, b'', 1)
    row = BASE_PINS[path]
    assert (o.pin(restored), len(restored), len(restored.splitlines())) == (row[1:3], row[3], row[4])
    return restored


def topology(ref, root, git, release):
    """Only D[M], I[M,D], J[R,I]; content authenticates every immutable anchor."""
    if release != p.R:
        raise o.TopologyError('publisher_release_anchor')
    parents = o._parents(ref, root, git)
    if parents == [M]:
        kind, tip, source = 'nonrelease', ref, ref
    elif len(parents) == 2 and parents[0] == M:
        kind, tip, source = 'nonrelease', ref, parents[1]
    elif len(parents) == 2 and parents[0] == p.R:
        kind, tip = 'release', parents[1]
        feature_parents = o._parents(tip, root, git)
        if len(feature_parents) != 2 or feature_parents[0] != M:
            raise o.TopologyError('publisher_feature_parents')
        source = feature_parents[1]
    else:
        raise o.TopologyError('publisher_candidate_parents')
    if o._parents(source, root, git) != [M]:
        raise o.TopologyError('publisher_candidate_parent')
    return kind, tip, source


def content(ref, root, git, entries, historical, release, release_tree, documents):
    """Fresh historical admission followed by exact pins, complete-tree join and budgets."""
    assert (release, release_tree, documents) == (p.R, p.R_TREE, p.R_DOCUMENTS)
    assert tuple(o._parents(M, root, git)) == M_PARENTS, 'publisher M parents'
    assert git('rev-parse', M + '^{tree}', root=root).decode().strip() == M_TREE, 'publisher M tree'
    baseline = p.selected_profile(M, root, git, entries, historical, release, release_tree, documents)
    assert baseline == entries(M, root) and len(baseline) == 1732
    actual, paths = entries(ref, root), CAPS.keys()
    assert len(paths) == 14 and SOURCE_PINS.keys() == paths - {PROFILE}
    assert baseline.keys() & paths == BASE_PINS.keys() == {DISPATCHER}
    assert actual.keys() == baseline.keys() | paths and len(actual) == 1745
    assert {path for path in actual if actual[path] != baseline.get(path)} == paths
    assert all(actual[path] == value for path, value in baseline.items() if path not in paths)
    assert all(actual[path][:2] == ('100644', 'blob') for path in paths)
    assert all(actual[path] == (row[0], 'blob', row[1]) for path, row in SOURCE_PINS.items())
    data = {path: git('cat-file', 'blob', actual[path][2], root=root) for path in paths}
    for path, (mode, blob, digest, size, lines) in SOURCE_PINS.items():
        assert mode == '100644' and o.pin(data[path]) == (blob, digest), path
        assert (len(data[path]), len(data[path].splitlines())) == (size, lines), path
    for path, row in BASE_PINS.items():
        assert baseline[path] == (row[0], 'blob', row[1]), path
        assert inverse(path, data[path]) == git('cat-file', 'blob', baseline[path][2], root=root), path
    p.authenticated._budgets(ref, M, root, git, data, CAPS, DELTA_LIMIT, 'publisher_delta_budget')
    return actual


def select(ref, root, git, entries, historical, release, release_tree, documents):
    """Only topology mismatch delegates; selected or historical failures are terminal."""
    ref = o._commit(ref, root, git)
    import rc_pretag_integration_admission_profile as integration
    selected = integration.select(ref, root, git, entries, historical, release, release_tree, documents)
    if selected is not None:
        return selected
    try:
        kind, tip, source = topology(ref, root, git, release)
    except o.TopologyError:
        return None
    expected = content(source, root, git, entries, historical, release, release_tree, documents)
    assert entries(tip, root) == expected
    if kind == 'release':
        return o.release_content(ref, expected, root, git, entries, release, release_tree, documents)
    return expected
