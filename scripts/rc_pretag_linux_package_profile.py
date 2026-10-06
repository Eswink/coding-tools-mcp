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
    'scripts/AppImage入口回归v3.py': (180, 12),
    'scripts/exact_build_audit.py': (430, 5),
}
MODES = {path: '100644' for path in CAPS}
MODES.update({'scripts/desktop_glib_build_evidence.py': '100755', 'scripts/appimage_relro_guard.py': '100755'})
DELTA_LIMIT = 8500
SOURCE_PINS = {
    '.github/workflows/linux-rc-packages.yml': ('100644', '47024a7c14b5bd9e1f25cc87f4b2f83ad9a6e34d', '96c483e4120bf764a32d69762b4cdfd23e91f14c918f46192bc3e01454757b4c', 19421, 350),
    'scripts/desktop_glib_build_evidence.py': ('100755', '46638243c98fbd2c7ba6fd1fc90439fd70c2bd21', '52526fe848208e7a9307a036939f326ed92b2a3b5a09d9029cddd8eb6e2aa5f7', 17886, 318),
    'scripts/desktop_glib_build_contract.py': ('100644', '47e8e1a0c0f40fda0a192f12552bba88346a1f3f', 'd4c009e4ac9f07b3734cb74cc920e1e3b1230e828ec0c5d2a9e8147168c2a173', 27948, 497),
    'scripts/linux_package_provenance.py': ('100644', 'c30782f36a89313487edb0ef5f1288d00c261117', 'e4f6fee05001fe9c08b136f434cdf65edc08ecb0d6110682aa972aeffc285127', 16540, 254),
    'scripts/linux_package_provenance_contract.py': ('100644', 'ba5724eea377d91319c0048acebd4cc22fa7f0f3', '377b5cdaf4f8567fc31f99682ce1b60c7867e8def472099d04a1b0b41d3d6330', 30267, 459),
    'scripts/rc_packages.py': ('100644', 'ea2dde33fd53a0ef8c01626461abe889610bc1e4', 'af0f8d3a0956d51714a0b8f2518532ed84fbbf437edd517b6e8103bebf0b0451', 8983, 186),
    'scripts/AppImage入口配置v3.py': ('100644', '6ca37b0c7721c7ee7f1fb233c10382c472d38a19', 'a3d73952968afc0e8023c815c37b41d92b72e34aa976afd73de57f79557d2c0e', 18023, 340),
    'scripts/linux_startup_candidate.py': ('100644', '0ee6baad230a200350d118807e125dcd33d7f6e6', '7ee01af30d92486aca0d8af4468753b7546d295d20f071863a04aa18f4c6a0ba', 13398, 255),
    'scripts/Ubuntu原生验收v1.py': ('100644', 'add9f36fdad5dbc8cc741036d7fcc79cec38f4c0', '54eaf719d486ddefd788e8e4c5cdfec49d911991d7e35e5774518e328e1f5c19', 19123, 358),
    'scripts/跨平台原生驱动v8.py': ('100644', 'eaa8cd1fdbf18137eb2ca6e216ce9b38f44c9bbf', '073b92f8214afad017c12b2a22c23eef3195e38154d72f2fa09b640ea5b324f7', 14463, 274),
    'scripts/exclusive_native_acceptance.py': ('100644', 'b98554aafd78c7e7e376f43cb20a4f4686e2acbd', 'bac190d66cb78cf9a380b05b1da89f37044248072360725a58b12fcbb65c619e', 21690, 368),
    'scripts/preliminary_package_contract_tests.py': ('100644', '70e1fed6c36d10b7a12beb523316df021e5d3daf', '3600a1c881c5772c1315c6395548debb52ab20ad2cf198644a831ba9c927fa50', 5155, 92),
    'scripts/linux_runtime_provenance.py': ('100644', '7fc94be49fb3a26ca15496b64a7c9bc5405ffacd', 'dc5de70ed6500a0ba28e6db55077e58a0384461ced6fccc9a81a0d4b9291288f', 32755, 500),
    'scripts/linux_package_provenance_tests.py': ('100644', '5e5daee97f8fbadd7cbb2affbbaa0ca05c92b13a', '73bdc7986219245a60ca84434a2ef57b91c4b6e2900e65e740f29153d2fe2bf4', 31486, 460),
    'scripts/linux_package_binding_tests.py': ('100644', '6d4c95c0820874b1cf6380f078a25ccc6fe8ce17', 'dfe0585de1ad4769c90034b5e42bd4a062abee80cd81f41e296e63cdfa998cd6', 17170, 247),
    'scripts/linux_runtime_provenance_tests.py': ('100644', '9bdb0af4b5c917a6f61c7e92b70b6e993487a4de', '077c5ae16a796183e58a1e31859489af8d67a7e7c9dbb7baa5078e2708546bb5', 33576, 490),
    'scripts/linux_runtime_workflow_tests.py': ('100644', '86ad6e2e48210582ba7f51726261f32dff6b3f7b', 'ccd93785a9fb43dc961d8770a9fbd696206bdcc1ecfb619b4b4ac9de3695128d', 16816, 220),
    'scripts/appimage_relro_tool.py': ('100644', 'caf725c0eb1fc3c207b572e8036159fd8277418a', '4ea84f1ce4e7b3c83747f0bbaedc444cd55c9a7a556362d09605d3374058fe61', 22044, 351),
    'scripts/appimage_relro_guard.py': ('100755', '464d744c846a85ecba4f510e65c6f99093bacde6', '286634b482acbd5103cf2c672ae9acc47504efcdb7299c33e7dcb90ea2227808', 22555, 440),
    'scripts/appimage_relro_contract.py': ('100644', 'acafabf04315148076a44b794f50b9ace4fd0715', '9cd9aa4d72d2c9d3bf205e5f71dddcd44da77cb7893ebdcdc54d3558ef4ecc92', 33076, 480),
    'scripts/appimage_relro_tool_tests.py': ('100644', '27d416e95be654f93d56352e2bc2f142dd44aa22', 'fb93c313299e12df2ecc46050cc93aef5234ea8747e964d5875cf72760f0e12c', 18336, 280),
    'scripts/appimage_relro_guard_tests.py': ('100644', 'da34f74ae82c7248f0a3014bde00c30e141b0414', '8904bc99dc976fe26da2c93a904133d743bd74091a57bbf3c4614e2cfb5c0389', 24930, 416),
    'scripts/appimage_relro_contract_tests.py': ('100644', 'f82c073af26ae615392c13541353f309a8aaca5d', '026471ea4c20ed9f1c14b5a6d3caff125719352e34bbd655490e55c5209bbf40', 20033, 306),
    'docs/specs/linux-package-provenance-relro/requirements.md': ('100644', 'b1a967e4d2a4c107b56689148feca8ce004b98f4', '944ac3fcf9c6e5629ddfa7439ecf26d628c59e28607ab28f2e212fefc79deaa8', 9065, 100),
    'docs/specs/linux-package-provenance-relro/design.md': ('100644', 'ef69176ecbee468a0f115179faaf33b31bf3d554', '4d649b153918abc286b893f01c5c54e6932ccf4bfa536b8d457308a9d4b2ab84', 23540, 156),
    'docs/specs/linux-package-provenance-relro/tasks.md': ('100644', '33f3a9fd281939850dfd7ac65a864de00e1b71d4', '04ea7476af08d8473cbdae26f60258f9c7884a1c4066ef74d65a5091a59ce43e', 10717, 98),
    'scripts/rc_pretag_linux_package_inverse.py': ('100644', 'f9e661f255b82479fcf047a2b0812d5aca6e61ea', '7637ea224580d49083af23df7c87e3e5dd63ef7f4868eba7e23232488f645cc7', 81491, 162),
    'scripts/rc_pretag_linux_package_cases.py': ('100644', 'e06c8fd4800a3ad92b6cd4932b7af9608c41c32c', 'e15b8892282f184c19699feb11fe263c4720f00b9dfa1649d0b3fb7271bb0baf', 30386, 440),
    'scripts/rc_pretag_publication_profile.py': ('100644', 'e2b87b630e4d00406020dc173fdec47a32ed2e96', '687bebbe836960a9ccf6e7c657e2955200aefd593e7b84c136b66d69e8941409', 32493, 499),
    'scripts/rc_pretag_appimage_profile.py': ('100644', '1903473701ad2e8780e7db812f98c7e3d26b7c75', 'e319be4c77e392e1bfc78938e91af1e98684cb710dbe3d6393a22ed200cc8286', 10957, 153),
    'scripts/rc_pretag_appimage_cases.py': ('100644', 'be5464078eb8369452ae28e94d4baa9f446746e0', 'a9fc69726fac6188b6a0650b222bc4b4bb66c22618918d71f88cde426cd2b6eb', 29783, 402),
    'scripts/AppImage入口回归v3.py': ('100644', '30f74f356ee2e4df0a81af711e0f850c4512234c', '6d7b8786f32d28e3186139036d9c644b01459f9aeb6f10c528cada1827096b91', 9036, 167),
    'scripts/exact_build_audit.py': ('100644', '49c81b1d77a83536ad7330ec0d42169fd423a1c3', '85e8b30e456ac4a83616564389de628a0aa3e9d5447775f0496e9b1c475ccf80', 26407, 426),
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
    assert len(baseline) == 1705 and len(paths) == 34
    assert SOURCE_PINS.keys() == paths - {PROFILE} and MODES.keys() == paths
    assert baseline.keys() & paths == inverse.BASE_PINS.keys() and len(inverse.BASE_PINS) == 15
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
