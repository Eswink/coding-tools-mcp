"""Finite Linux package source composition; external review binds this module."""
import rc_pretag_ownership_profile as o
import rc_pretag_publication_profile as p
import rc_pretag_linux_package_inverse as inverse

M = 'fd7b303839aa648d33456f7aaeec6388bfb696c4'
M_TREE = 'e4ab19e2fe4bfbb1fef9e0cd713a6fbb18d03995'
M_PARENTS = ('feeaf299df6c3729285c91511ece18e9984a2503', '23be745924cc85da84901da8cdd4a65db1673734')
PROFILE = 'scripts/rc_pretag_linux_package_profile.py'
CASES = 'scripts/rc_pretag_linux_package_cases.py'
WORKFLOW = '.github/workflows/linux-rc-packages.yml'
CAPS = {
    '.github/workflows/linux-rc-packages.yml': (400, 260),
    'scripts/desktop_glib_build_evidence.py': (350, 65),
    'scripts/desktop_glib_build_contract.py': (500, 140),
    'scripts/linux_package_provenance.py': (450, 450),
    'scripts/linux_package_provenance_contract.py': (460, 460),
    'scripts/rc_packages.py': (270, 110),
    'scripts/AppImage入口配置v3.py': (330, 160),
    'scripts/linux_startup_candidate.py': (300, 90),
    'scripts/Ubuntu原生验收v1.py': (400, 90),
    'scripts/跨平台原生驱动v8.py': (310, 55),
    'scripts/exclusive_native_acceptance.py': (440, 115),
    'scripts/preliminary_package_contract_tests.py': (100, 35),
    'scripts/AppImage入口回归v3.py': (180, 12),
    'scripts/linux_runtime_provenance.py': (500, 500),
    'scripts/linux_package_provenance_tests.py': (460, 460),
    'scripts/linux_package_binding_tests.py': (400, 400),
    'scripts/linux_runtime_provenance_tests.py': (490, 490),
    'scripts/linux_runtime_workflow_tests.py': (220, 220),
    'scripts/appimage_relro_tool.py': (360, 360),
    'scripts/appimage_relro_guard.py': (440, 440),
    'scripts/appimage_relro_contract.py': (480, 480),
    'scripts/appimage_relro_tool_tests.py': (360, 360),
    'scripts/appimage_relro_guard_tests.py': (480, 480),
    'scripts/appimage_relro_contract_tests.py': (480, 480),
    'docs/specs/linux-package-provenance-relro/requirements.md': (150, 150),
    'docs/specs/linux-package-provenance-relro/design.md': (260, 260),
    'docs/specs/linux-package-provenance-relro/tasks.md': (200, 200),
    'scripts/rc_pretag_linux_package_profile.py': (360, 360),
    'scripts/rc_pretag_linux_package_inverse.py': (320, 320),
    'scripts/rc_pretag_linux_package_cases.py': (500, 500),
    'scripts/rc_pretag_publication_profile.py': (500, 5),
    'scripts/rc_pretag_appimage_profile.py': (180, 4),
    'scripts/rc_pretag_appimage_cases.py': (440, 50),
}
MODES = {path: '100644' for path in CAPS}
MODES.update({'scripts/desktop_glib_build_evidence.py': '100755', 'scripts/appimage_relro_guard.py': '100755'})
DELTA_LIMIT = 8500
SOURCE_PINS = {
    '.github/workflows/linux-rc-packages.yml': ('100644', '3b9fdb1fe7cff2cf48dc9802e73e52ed6e652bcc', 'c0df091003f841f44f49454a095fc68fc1f826e6341f05960e5f6d7ef4dd3097', 16594, 294),
    'scripts/desktop_glib_build_evidence.py': ('100755', '46638243c98fbd2c7ba6fd1fc90439fd70c2bd21', '52526fe848208e7a9307a036939f326ed92b2a3b5a09d9029cddd8eb6e2aa5f7', 17886, 318),
    'scripts/desktop_glib_build_contract.py': ('100644', 'e478f26600bf1b2475652119034eb720d94526bb', '8ee538526be11f0672ae104ea33a98771d4e893eed70a611025fd45b212bfbf4', 27738, 489),
    'scripts/linux_package_provenance.py': ('100644', '262563d0cdd5dba3a445b049474eeccfb0921dd4', 'd8846c667d8ec9dba809acd24326460fc9ab7bd008354cd81e9620ee1443f925', 12392, 194),
    'scripts/linux_package_provenance_contract.py': ('100644', 'ef744725b4737fc6da038711243c2fc2a88093f6', '58d30c769c7cbbd5796091134903035ea6268f827190c73ceea6bd888f315b72', 25521, 387),
    'scripts/rc_packages.py': ('100644', 'ea2dde33fd53a0ef8c01626461abe889610bc1e4', 'af0f8d3a0956d51714a0b8f2518532ed84fbbf437edd517b6e8103bebf0b0451', 8983, 186),
    'scripts/AppImage入口配置v3.py': ('100644', 'e44a1702772b6cea8c6f6b51159e1c9bf3bddfeb', '0733088acc34150b1d26e99bb4749b26c688ed5e14c0acdefae6591578985a3c', 11624, 244),
    'scripts/linux_startup_candidate.py': ('100644', '2dcc0087e1525259574e30507600e508b1332060', '69296372d2f0f898d364877b86303b7022b679b39ca27e44f302b1959fa0d554', 13430, 256),
    'scripts/Ubuntu原生验收v1.py': ('100644', 'add9f36fdad5dbc8cc741036d7fcc79cec38f4c0', '54eaf719d486ddefd788e8e4c5cdfec49d911991d7e35e5774518e328e1f5c19', 19123, 358),
    'scripts/跨平台原生驱动v8.py': ('100644', 'eaa8cd1fdbf18137eb2ca6e216ce9b38f44c9bbf', '073b92f8214afad017c12b2a22c23eef3195e38154d72f2fa09b640ea5b324f7', 14463, 274),
    'scripts/exclusive_native_acceptance.py': ('100644', 'b98554aafd78c7e7e376f43cb20a4f4686e2acbd', 'bac190d66cb78cf9a380b05b1da89f37044248072360725a58b12fcbb65c619e', 21690, 368),
    'scripts/preliminary_package_contract_tests.py': ('100644', 'b36c7def1e57352bae60a09a8576733fd6fd77c8', '3739866c667cace00cf325864a6fdff4a96c7150e6a28e92c80201b30a56ff04', 4689, 87),
    'scripts/linux_runtime_provenance.py': ('100644', '8ee48a94be24a5668c29ac107f76d3bf64209c7a', '788bcf8c133239e68f2fe932ddf0af4658625fc3fbbd325e80f068ca2c0c581b', 32688, 500),
    'scripts/linux_package_provenance_tests.py': ('100644', '313f21717e39b8503a341df0566da6429678e552', '1a0899b40b2eb60f30f452045aff4192d973271098e9de7bc01e32b837696707', 17211, 270),
    'scripts/linux_package_binding_tests.py': ('100644', 'd0267aa5ce8ae346f715a8cb015f14623ba3f289', '0c3670a11a4533a6b95bc4c9e7630e9d4316afabd0c316ab68732dbdc2874729', 13678, 207),
    'scripts/linux_runtime_provenance_tests.py': ('100644', 'ad96fe2f2d69bdad423d929dbcf2b3b14c988be1', 'fd1d80f6c76c6d64b54cf03cc4885b8211d331f9b37f6b9c84b2b9fc9e04eb7b', 31049, 459),
    'scripts/linux_runtime_workflow_tests.py': ('100644', '8dcc25051e8fb1af5197077d6cc4f1cccbfbfc8f', '9f875ab3ef4b140712d93450f5b866e0b1ed43c7183781c351aec35ba43a7fc0', 12952, 176),
    'scripts/appimage_relro_tool.py': ('100644', '5e832c201c71bc64c7a08fe82e624fc334bb2265', '9194368ddd2cbc312a1fe77a54049c10fbbb7fc61fd633c3643417771fd297d1', 21557, 343),
    'scripts/appimage_relro_guard.py': ('100755', '6499e660db80dec8886776879551496bc6350b15', '92231c76ac43f8bffecbed03d2140f63d6d48fb0df0c812cb021366c4e8af870', 22554, 440),
    'scripts/appimage_relro_contract.py': ('100644', 'f13ed1202097d0cf3231a3656fa2a6275c8c4ad0', '0b6b0d7028b0ad08c3139aec53d656eb82a56c93249efc1e168c70df5e257eea', 33076, 480),
    'scripts/appimage_relro_tool_tests.py': ('100644', 'a77160515af19afdae2fa8d968c3eb8bbfaaa34a', '782ab9216aaa87cbf209a67ad2793bcf457e01ef443503819f612a2639694267', 17186, 260),
    'scripts/appimage_relro_guard_tests.py': ('100644', 'ee10e30475b26585dd7ffdf519e3a7b163f8e5da', '2df55ff4e31c1dc97dda6c59f7b3b3d1a3b6d3c3772d732db14f0f1e2bde3713', 24252, 406),
    'scripts/appimage_relro_contract_tests.py': ('100644', '12b0c07f1518f793053ef025e0d9eb9e4455af23', '4e955713971552568b0632cece2de68bf9d26d1b1371fa21f6d6bf750521177b', 19862, 305),
    'docs/specs/linux-package-provenance-relro/requirements.md': ('100644', 'b1a967e4d2a4c107b56689148feca8ce004b98f4', '944ac3fcf9c6e5629ddfa7439ecf26d628c59e28607ab28f2e212fefc79deaa8', 9065, 100),
    'docs/specs/linux-package-provenance-relro/design.md': ('100644', '7a4817c2ca43ba4c0ff0d122caae187ad52575a8', '3b3f51941ebd75d26ab54d0e31ec3af8ea599456f1177e08337e438ca60ea41a', 17345, 134),
    'docs/specs/linux-package-provenance-relro/tasks.md': ('100644', '5bf3aaf8cd22f45d6d2d37f24b2e98522af8581d', '4368c446b6c8d05e1f72791d8cee7a1c9b3745a1220b9f4d68ec50c9861d7093', 10717, 98),
    'scripts/rc_pretag_linux_package_inverse.py': ('100644', '6c618f67d81bfb6f915227a6dff7b6a1724f74b9', '484cc7f206fc1be8449d085fd388646516c8898812e6ad2a1a9cc78099a4a7ad', 66686, 147),
    'scripts/rc_pretag_linux_package_cases.py': ('100644', 'dc52986887f088280d8458c8dd6c41f442b35d7c', '0483eee868e7de79111a8a31c138f720c654fef3044cd1fe1587524779baedc4', 30386, 440),
    'scripts/rc_pretag_publication_profile.py': ('100644', 'e2b87b630e4d00406020dc173fdec47a32ed2e96', '687bebbe836960a9ccf6e7c657e2955200aefd593e7b84c136b66d69e8941409', 32493, 499),
    'scripts/rc_pretag_appimage_profile.py': ('100644', '1903473701ad2e8780e7db812f98c7e3d26b7c75', 'e319be4c77e392e1bfc78938e91af1e98684cb710dbe3d6393a22ed200cc8286', 10957, 153),
    'scripts/rc_pretag_appimage_cases.py': ('100644', 'be5464078eb8369452ae28e94d4baa9f446746e0', 'a9fc69726fac6188b6a0650b222bc4b4bb66c22618918d71f88cde426cd2b6eb', 29783, 402),
    'scripts/AppImage入口回归v3.py': ('100644', '30f74f356ee2e4df0a81af711e0f850c4512234c', '6d7b8786f32d28e3186139036d9c644b01459f9aeb6f10c528cada1827096b91', 9036, 167),
}
CLASS = "rc_pretag_linux_package_cases.LinuxPackageCompositionTests"
DIGEST = '61da1f74c937f638442ec78250d5369b3bfb3692933e287769bb9e7a6a2d6adb'
NAMES = (
    'test_exact_m_anchor_tree_parents_and_fresh_history',
    'test_candidate_has_exact_finite_source_paths_and_pins',
    'test_ordered_merge_requires_complete_identical_candidate_tree',
    'test_release_overlay_has_only_four_exact_r_documents',
    'test_missing_extra_reversed_duplicate_nested_parents_reject',
    'test_unknown_same_tree_anchor_and_correction_ancestry_reject',
    'test_every_source_mode_blob_digest_size_and_line_pin_rejects_drift',
    'test_individual_and_aggregate_budgets_reject',
    'test_all_current_inverses_recover_complete_m_bytes',
    'test_inverse_fragments_and_historical_passthrough_pins_are_exact',
    'test_original_815_assertions_and_ids_are_preserved',
    'test_mandatory_supplemental_and_new_inventory_are_disjoint',
    'test_loaded_executed_inventory_rejects_skips_and_duplicates',
    'test_scoped_tool_pins_and_nine_protected_destinations_are_exact',
    'test_collector_single_build_and_original_profile_are_preserved',
    'test_workflow_preserves_four_installed_jobs_and_failure_gates',
    'test_windows_held_runtime_versions_and_release_gates_are_unchanged',
    'test_selected_content_failure_is_terminal_without_fallback',
    'test_mutable_refs_and_ambient_git_do_not_change_identity',
    'test_only_test_fixture_baseline_cache_is_permitted',
)


def topology(ref, root, git, release):
    """Only D[M], I[M,D], J[R,I], with complete ordered immutable ancestry."""
    if release != p.R:
        raise o.TopologyError('linux_package_release_anchor')
    parents = o._parents(ref, root, git)
    if parents == [M]:
        kind, tip, source = 'nonrelease', ref, ref
    elif len(parents) == 2 and parents[0] == M:
        kind, tip, source = 'nonrelease', ref, parents[1]
    elif len(parents) == 2 and parents[0] == p.R:
        kind, tip = 'release', parents[1]
        feature_parents = o._parents(tip, root, git)
        if len(feature_parents) != 2 or feature_parents[0] != M:
            raise o.TopologyError('linux_package_feature_parents')
        source = feature_parents[1]
    else:
        raise o.TopologyError('linux_package_candidate_parents')
    if o._parents(source, root, git) != [M]:
        raise o.TopologyError('linux_package_candidate_parent')
    if tuple(o._parents(M, root, git)) != M_PARENTS:
        raise o.TopologyError('linux_package_anchor_parents')
    return kind, tip, source


def content(ref, root, git, entries, historical, release, release_tree, documents):
    """Fresh historical validation and exact fixed pins, modes and finite delta."""
    assert (release, release_tree, documents) == (p.R, p.R_TREE, p.R_DOCUMENTS)
    assert tuple(o._parents(M, root, git)) == M_PARENTS
    assert git('rev-parse', M + '^{tree}', root=root).decode().strip() == M_TREE
    baseline = p.selected_profile(M, root, git, entries, historical, release, release_tree, documents)
    actual, paths = entries(ref, root), CAPS.keys()
    assert len(baseline) == 1705 and len(paths) == 33
    assert SOURCE_PINS.keys() == paths - {PROFILE} and MODES.keys() == paths
    assert baseline.keys() & paths == inverse.BASE_PINS.keys() and len(inverse.BASE_PINS) == 14
    assert actual.keys() == baseline.keys() | paths and len(actual) == 1724
    assert {path for path in actual if actual[path] != baseline.get(path)} == paths
    assert all(actual[path] == value for path, value in baseline.items() if path not in paths)
    assert all(actual[path][:2] == (MODES[path], 'blob') for path in paths)
    assert all(actual[path] == (row[0], 'blob', row[1]) for path, row in SOURCE_PINS.items())
    data = {path: git('cat-file', 'blob', actual[path][2], root=root) for path in paths}
    for path, (mode, blob, digest, size, lines) in SOURCE_PINS.items():
        assert mode == MODES[path] and actual[path][2] == blob and o.pin(data[path]) == (blob, digest), path
        assert (len(data[path]), len(data[path].splitlines())) == (size, lines), path
    for path in inverse.BASE_PINS:
        assert inverse.inverse(path, data[path]) == git('cat-file', 'blob', baseline[path][2], root=root)
    p.authenticated._budgets(ref, M, root, git, data, CAPS, DELTA_LIMIT, 'linux_package_delta_budget')
    return actual


def select(ref, root, git, entries, historical, release, release_tree, documents):
    """Topology mismatch alone may delegate; selected content failure is terminal."""
    try:
        kind, tip, source = topology(ref, root, git, release)
    except o.TopologyError:
        return None
    expected = content(source, root, git, entries, historical, release, release_tree, documents)
    assert entries(tip, root) == expected
    if kind == 'release':
        return o.release_content(ref, expected, root, git, entries, release, release_tree, documents)
    return expected
