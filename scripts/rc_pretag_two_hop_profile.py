"""Exact two-hop engineering composition; profile self-bytes require external review."""
import rc_pretag_ownership_profile as ownership
import rc_pretag_desktop_profile as desktop
import rc_pretag_nginx_profile as nginx

PROFILE_ID = 'engineering/issue40-two-hop-composition-v1'
F = '44b9f9b16f6981297bd1252eb3ab238ae581eccc'
F_TREE = '99916334cc77fcc22209c99661e40ba1fd2e1276'
F_PARENTS = ('310ad16c8aa9cc8182c4b0f6a196184fcf34bc52', '0a2554230a1523b0e6e5b43f0574897f4ed3b8a9')
P = 'f8d187dfe9fe30e8641c7f8906d615265811c107'
P_TREE = '0989ac3fc24839e0e83a3003abc41fe4f202ac64'
R = 'e2e011f7f2a3a1df838bbd588106205b999db610'
R_TREE = 'c0dfe00fdcc7ebc8e26acaad5d18ff3f94df9ba3'
R_DOCUMENTS = nginx.R_DOCUMENTS
COMPOSITION = 'scripts/rc_pretag_composition_tests.py'
DESKTOP_TESTS = 'scripts/rc_pretag_desktop_tests.py'
NGINX_TESTS = 'scripts/rc_pretag_nginx_tests.py'
PROFILE = 'scripts/rc_pretag_two_hop_profile.py'
TESTS = 'scripts/rc_pretag_two_hop_tests.py'
# Native P: six replacements and one addition; mode/blob/SHA256/bytes/lines.
SOURCE_PINS = {
    '.github/workflows/issue40-current-nginx-include.yml': ('100644', 'fb7e86d99d968651050cb1de69188557133e7155',
        '3df1582a98066cacbd79203416ed45262328b2debe43d8becb0dc4edd8736ee5', 14843, 226),
    'deploy/cloud-gateway/runtime_topology.py': ('100644', 'e73a6e46134dfe3e6eaf286b5465d9a40115d3a9',
        '34b1ea7411baa28361fd981348c510a098bc6162518264a9481552ed7d58582b', 8051, 121),
    'docs/deployment/current-nginx-include.md': ('100644', '01beb7b156e489d1c43d09d9420f8daa316e0c21',
        '6bac2b14ed871aaec9ff0c8054deffe18a5b0906d3002e37ef83823ac0be0ea0', 12435, 195),
    'tests/cloud-gateway-deployment/run_current_nginx_runtime.py': ('100644', '6c36e33f587c802adbe09c6f6fa792d92b092243',
        '9192d50c388c65874e0517812f65c9e15cf3271ad40204a7d48eb38dd2457c3a', 22679, 394),
    'tests/cloud-gateway-deployment/test_current_nginx_include.py': ('100644', '1d7ad4ccf2261a10bbd73fb73c6e7851b9c65b03',
        'ad771567f4e5c262bb34305cd7f534ce9b0ba313ad2535a8074cdc36747577f1', 23095, 405),
    'tests/cloud-gateway-deployment/test_current_nginx_two_hop.py': ('100644', 'e7ef511c6437a23eac813273ab815c4a55e0ce06',
        'f23f5ecaa4829e7a1b1c1029f41a58d882dba6ed027215c828b18fb08134bce5', 14565, 241),
    'tests/cloud-gateway-deployment/test_runtime_topology.py': ('100644', '3e223868944e9c4b38d9df08ed87feae4b1ff217',
        'f2b6d893a80a9f6868fbf6a0ddb97ac95de0b457d1d3a8d5312c75a37f8fec52', 17059, 254),
}
# Seven finalized non-self pins; external manifest binds this file and full tree.
AMENDMENT_PINS = {
    'scripts/rc_pretag_composition_tests.py': ('6aceb93ede42cecac841e12d30bd35ae156ba8ef',
        '61098cd058653f1585ae35bcec620ab8a209535cf8b81b78dcbb47b62e88c10c'),
    'scripts/rc_pretag_desktop_tests.py': ('f107c9d7fc0fa2dcb9eca989e67727ad74d0c96c',
        'e47b2872a529fb94fbe63940dd99ce5241d3b1750727ae030a29dd38e30956f9'),
    'scripts/rc_pretag_nginx_tests.py': ('137d48b0670e223241bf923f248d74e6f9948085',
        'c7d64fdbb0a881164c8811fc1bbe44ba899afc3802289f9c27f4ad534e2188a5'),
    'scripts/rc_pretag_two_hop_tests.py': ('3ab26fae937d1a057fbe91e3264a8424530a3adf',
        '1ab1fff5f42f13285e3738da3c4fe6172345c71d1c8e39fa5c4d35457190afb4'),
    'docs/specs/issue40-two-hop-composition/requirements.md': ('6c8f0ee64615fd5d30c985f7554d79714d8c4142',
        'e273cdf0e996cfeee330cb48a5a4e9bc42be495d3a03a5e98fad1e4ebe5e72ab'),
    'docs/specs/issue40-two-hop-composition/design.md': ('6789e648336adee487a3010396259cb141482703',
        '4555266b3dd7ac2a4a9ccf27221718531a34036b5890eaa481f3c301016cf487'),
    'docs/specs/issue40-two-hop-composition/tasks.md': ('84ca2d2a568c22b6a4070ecd7abc09896e7b9fe7',
        '6346aa87210ec6f19d04820419ebe9bd0b2448562c60812d70da4d3b395ea29d'),
}
AMENDMENT_CAPS = {
    COMPOSITION: (500, 24), DESKTOP_TESTS: (400, 48), NGINX_TESTS: (480, 128),
    PROFILE: (360, 360), TESTS: (480, 480),
    **{'docs/specs/issue40-two-hop-composition/' + name + '.md': (80, 80)
       for name in ('requirements', 'design', 'tasks')},
}
AMENDMENT_DELTA_LIMIT = 1300
EXPECTED_GROUPS = {'rc_pretag_two_hop_tests.TwoHopCompositionTests': (
    'test_frozen_historical_profiles_and_pins_remain_exact '
    'test_exact_f_parent_tree_and_nginx_validation '
    'test_native_p_sole_parent_tree_and_seven_path_delta '
    'test_exact_p_and_one_reviewed_amendment_accept '
    'test_ordered_feature_merge_requires_complete_source_tree '
    'test_release_overlay_contains_only_four_exact_documents '
    'test_unknown_missing_and_same_tree_impostor_anchors_reject '
    'test_reversed_duplicate_missing_and_extra_parents_reject_before_content '
    'test_amendment_chains_nested_merges_and_descendants_reject '
    'test_each_native_source_blob_digest_size_and_line_pin_rejects_drift '
    'test_missing_extra_rename_mode_symlink_and_gitlink_entries_reject '
    'test_every_historical_protected_entry_and_six_version_slots_remain_exact '
    'test_release_document_byte_mode_path_and_deletion_drift_rejects '
    'test_amendment_pins_scope_binary_and_individual_total_budgets_reject '
    'test_composition_inverse_recovers_exact_f_and_rejects_fragment_drift '
    'test_desktop_adapter_inverse_preserves_all_historical_assertions '
    'test_nginx_adapter_inverse_preserves_historical_fixtures_and_budget_negatives '
    'test_frozen_187_plus_22_inventory_is_exactly_loaded_and_executed '
    'test_mutable_refs_and_ambient_git_redirection_cannot_change_identity '
    'test_topology_dispatch_keeps_all_legacy_content_failures_terminal '
    'test_unknown_profiles_and_native_release_approval_claims_reject '
    'test_old_inner_ingress_and_superseded_source_cannot_replace_native_pins '
)}


def two_hop_topology(ref, root, git, release):
    """Closed immutable parent grammar; no tree or candidate-content readers."""
    if release != R:
        raise ownership.TopologyError('two_hop_release_anchor')

    def candidate(tip):
        if tip != P and ownership._parents(tip, root, git) != [P]:
            raise ownership.TopologyError('two_hop_candidate_parent')
        return tip

    def feature(tip):
        parents = ownership._parents(tip, root, git)
        if len(parents) != 2 or parents[0] != F:
            raise ownership.TopologyError('two_hop_feature_parents')
        return tip, candidate(parents[1])

    parents = ownership._parents(ref, root, git)
    if parents and parents[0] == release:
        if len(parents) != 2:
            raise ownership.TopologyError('two_hop_release_parents')
        tip, source = feature(parents[1])
        kind = 'release'
    elif len(parents) == 2 and parents[0] == F:
        tip, source = feature(ref)
        kind = 'nonrelease'
    else:
        tip = source = candidate(ref)
        kind = 'nonrelease'
    if ownership._parents(P, root, git) != [F]:
        raise ownership.TopologyError('two_hop_source_parent')
    if tuple(ownership._parents(F, root, git)) != F_PARENTS:
        raise ownership.TopologyError('two_hop_anchor_parents')
    return kind, tip, source


def two_hop_content(ref, root, git, entries, historical, release, release_tree, documents):
    """Exact native P overlay, independently of the candidate's parent grammar."""
    assert (release, release_tree, documents) == (R, R_TREE, R_DOCUMENTS)
    assert tuple(ownership._parents(F, root, git)) == F_PARENTS
    assert ownership._parents(P, root, git) == [F]
    assert git('rev-parse', F + '^{tree}', root=root).decode().strip() == F_TREE
    assert git('rev-parse', P + '^{tree}', root=root).decode().strip() == P_TREE
    original = nginx.selected_profile(
        F, root, git, entries, historical, release, release_tree, documents)
    assert len(original) == 1664 and len(SOURCE_PINS) == 7
    assert len(original.keys() & SOURCE_PINS.keys()) == 6
    expected = original | {path: (mode, 'blob', blob)
                           for path, (mode, blob, _, _, _) in SOURCE_PINS.items()}
    assert len(expected) == 1665
    assert {p for p in expected if expected[p] != original.get(p)} == SOURCE_PINS.keys()
    assert entries(P, root) == expected and entries(ref, root) == expected
    for path, (mode, blob, digest, size, lines) in SOURCE_PINS.items():
        assert mode == '100644', path
        data = git('cat-file', 'blob', blob, root=root)
        assert ownership.pin(data) == (blob, digest), path
        assert (len(data), len(data.splitlines())) == (size, lines), path
    return expected


def amendment_content(ref, baseline, root, git, entries):
    """Exactly eight reviewed paths; no old-source or historical-budget rebinding."""
    actual = entries(ref, root)
    paths = AMENDMENT_CAPS.keys()
    assert AMENDMENT_PINS.keys() == paths - {PROFILE}
    assert set(baseline) & paths == {COMPOSITION, DESKTOP_TESTS, NGINX_TESTS}
    assert actual.keys() == baseline.keys() | paths and len(actual) == 1670
    assert {p for p in actual if actual[p] != baseline.get(p)} == paths
    assert all(actual[p] == value for p, value in baseline.items() if p not in paths)
    assert all(actual[p][:2] == ('100644', 'blob') for p in paths)
    data = {p: git('cat-file', 'blob', actual[p][2], root=root) for p in paths}
    for path, expected in AMENDMENT_PINS.items():
        assert ownership.pin(data[path]) == expected, path
    total = 0
    for path, (line_cap, diff_cap) in AMENDMENT_CAPS.items():
        assert len(data[path].splitlines()) <= line_cap, path
        rows = git('diff', '--numstat', P, ref, '--', path, root=root).splitlines()
        assert len(rows) == 1, path
        fields = rows[0].split(b'\t')
        assert len(fields) == 3 and fields[2] == path.encode(), path
        assert all(v and all(48 <= c <= 57 for c in v) for v in fields[:2]), path
        delta = sum(map(int, fields[:2]))
        assert delta <= diff_cap, path
        total += delta
    assert total <= AMENDMENT_DELTA_LIMIT, 'two_hop_amendment_delta_budget'
    old_data = {p: git('cat-file', 'blob', actual[p][2], root=root) for p in ownership.CAPS}
    ownership.budgets(ref, root, git, old_data)
    return actual


def selected_profile(ref, root, git, entries, historical, release, release_tree, documents, *, profile=PROFILE_ID):
    assert profile == PROFILE_ID, 'unknown_composition_profile'
    ref = ownership._commit(ref, root, git)
    # Catch topology rejection only; content exceptions from the chosen profile are terminal.
    for topology, select in ((ownership.topology, ownership.selected_profile),
                             (desktop.desktop_topology, desktop.selected_profile),
                             (nginx.nginx_topology, nginx.selected_profile)):
        try:
            topology(ref, root, git, release)
        except ownership.TopologyError:
            continue
        return select(ref, root, git, entries, historical, release, release_tree, documents)
    kind, tip, source = two_hop_topology(ref, root, git, release)
    expected = two_hop_content(P, root, git, entries, historical, release, release_tree, documents)
    if source != P:
        expected = amendment_content(source, expected, root, git, entries)
    if tip != source:
        assert entries(tip, root) == expected
    if kind == 'release':
        return ownership.release_content(
            ref, expected, root, git, entries, release, release_tree, documents)
    return expected
