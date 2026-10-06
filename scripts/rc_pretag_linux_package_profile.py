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
    'scripts/AppImage入口配置v3.py': (340, 160),
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
    '.github/workflows/linux-rc-packages.yml': ('100644', 'e660cc151871db8a1050efe5c1258de744d5b518', '76e591eccef17a72fb3e8cebf7ed7888ba231369e731985b98a5653ed2e9239f', 17821, 315),
    'scripts/desktop_glib_build_evidence.py': ('100755', '46638243c98fbd2c7ba6fd1fc90439fd70c2bd21', '52526fe848208e7a9307a036939f326ed92b2a3b5a09d9029cddd8eb6e2aa5f7', 17886, 318),
    'scripts/desktop_glib_build_contract.py': ('100644', 'e478f26600bf1b2475652119034eb720d94526bb', '8ee538526be11f0672ae104ea33a98771d4e893eed70a611025fd45b212bfbf4', 27738, 489),
    'scripts/linux_package_provenance.py': ('100644', '766aa3c8fc6d46cd0a3c324b4411fbd1f8d228c3', 'd53470d79814c36b3246965fc53759ac4b6df36993a8a93c9963e7d365ade99f', 15536, 237),
    'scripts/linux_package_provenance_contract.py': ('100644', '6b0378acae68c9c24c91353268b26452d4f4de4d', 'b36f4db65578274bfd35b243f5ee69a8f1acae1dae1460faf71db834e72f8df9', 29511, 446),
    'scripts/rc_packages.py': ('100644', 'ea2dde33fd53a0ef8c01626461abe889610bc1e4', 'af0f8d3a0956d51714a0b8f2518532ed84fbbf437edd517b6e8103bebf0b0451', 8983, 186),
    'scripts/AppImage入口配置v3.py': ('100644', '6ca37b0c7721c7ee7f1fb233c10382c472d38a19', 'a3d73952968afc0e8023c815c37b41d92b72e34aa976afd73de57f79557d2c0e', 18023, 340),
    'scripts/linux_startup_candidate.py': ('100644', '0ee6baad230a200350d118807e125dcd33d7f6e6', '7ee01af30d92486aca0d8af4468753b7546d295d20f071863a04aa18f4c6a0ba', 13398, 255),
    'scripts/Ubuntu原生验收v1.py': ('100644', 'add9f36fdad5dbc8cc741036d7fcc79cec38f4c0', '54eaf719d486ddefd788e8e4c5cdfec49d911991d7e35e5774518e328e1f5c19', 19123, 358),
    'scripts/跨平台原生驱动v8.py': ('100644', 'eaa8cd1fdbf18137eb2ca6e216ce9b38f44c9bbf', '073b92f8214afad017c12b2a22c23eef3195e38154d72f2fa09b640ea5b324f7', 14463, 274),
    'scripts/exclusive_native_acceptance.py': ('100644', 'b98554aafd78c7e7e376f43cb20a4f4686e2acbd', 'bac190d66cb78cf9a380b05b1da89f37044248072360725a58b12fcbb65c619e', 21690, 368),
    'scripts/preliminary_package_contract_tests.py': ('100644', 'e6d76766eb0e5bb85504caab05706ecfcdb6332e', '1a033793506fe46c5c80b4b182d788436335ed57240563ffa2453505f9e918ca', 4713, 87),
    'scripts/linux_runtime_provenance.py': ('100644', '7fc94be49fb3a26ca15496b64a7c9bc5405ffacd', 'dc5de70ed6500a0ba28e6db55077e58a0384461ced6fccc9a81a0d4b9291288f', 32755, 500),
    'scripts/linux_package_provenance_tests.py': ('100644', '80cd1541149cd8a42298a7a6b67bb48ad3e2710c', 'd9139eeb44624e7696632a22a61f3157b52ca2405e44af29a7819cd5208b898d', 28792, 430),
    'scripts/linux_package_binding_tests.py': ('100644', 'bf37a66355301f15edb3ab9a7526b2b144bbf94a', 'b05c10cc01e3c23fcdbea2a3d193db5d0743636137a0cedf8b5eb61d1c215714', 17121, 246),
    'scripts/linux_runtime_provenance_tests.py': ('100644', '9bdb0af4b5c917a6f61c7e92b70b6e993487a4de', '077c5ae16a796183e58a1e31859489af8d67a7e7c9dbb7baa5078e2708546bb5', 33576, 490),
    'scripts/linux_runtime_workflow_tests.py': ('100644', '43d8436639ac983632781d907b08aef055340f4a', 'fbcee72b008b0e6523083913fd03356dc592c46e11e45e6a8ae6e2e39fc74b4a', 16787, 220),
    'scripts/appimage_relro_tool.py': ('100644', '5e832c201c71bc64c7a08fe82e624fc334bb2265', '9194368ddd2cbc312a1fe77a54049c10fbbb7fc61fd633c3643417771fd297d1', 21557, 343),
    'scripts/appimage_relro_guard.py': ('100755', '6499e660db80dec8886776879551496bc6350b15', '92231c76ac43f8bffecbed03d2140f63d6d48fb0df0c812cb021366c4e8af870', 22554, 440),
    'scripts/appimage_relro_contract.py': ('100644', 'f13ed1202097d0cf3231a3656fa2a6275c8c4ad0', '0b6b0d7028b0ad08c3139aec53d656eb82a56c93249efc1e168c70df5e257eea', 33076, 480),
    'scripts/appimage_relro_tool_tests.py': ('100644', 'a77160515af19afdae2fa8d968c3eb8bbfaaa34a', '782ab9216aaa87cbf209a67ad2793bcf457e01ef443503819f612a2639694267', 17186, 260),
    'scripts/appimage_relro_guard_tests.py': ('100644', 'ee10e30475b26585dd7ffdf519e3a7b163f8e5da', '2df55ff4e31c1dc97dda6c59f7b3b3d1a3b6d3c3772d732db14f0f1e2bde3713', 24252, 406),
    'scripts/appimage_relro_contract_tests.py': ('100644', '12b0c07f1518f793053ef025e0d9eb9e4455af23', '4e955713971552568b0632cece2de68bf9d26d1b1371fa21f6d6bf750521177b', 19862, 305),
    'docs/specs/linux-package-provenance-relro/requirements.md': ('100644', 'b1a967e4d2a4c107b56689148feca8ce004b98f4', '944ac3fcf9c6e5629ddfa7439ecf26d628c59e28607ab28f2e212fefc79deaa8', 9065, 100),
    'docs/specs/linux-package-provenance-relro/design.md': ('100644', '5861ba140178432c17d5722de132fc430060a167', '17db55095b69c32280b1a404f1a5c564e93832a4bbfa3a32e1a6ab2e3a0a8947', 21412, 147),
    'docs/specs/linux-package-provenance-relro/tasks.md': ('100644', '5bf3aaf8cd22f45d6d2d37f24b2e98522af8581d', '4368c446b6c8d05e1f72791d8cee7a1c9b3745a1220b9f4d68ec50c9861d7093', 10717, 98),
    'scripts/rc_pretag_linux_package_inverse.py': ('100644', 'c2a1bb5d63bf68a34aaac979c5066f4e1ec94720', 'b7d081cb15d62edd6d1b04901312e97a3d7bd245ab3e62befff71e7eb9668890', 75612, 150),
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
