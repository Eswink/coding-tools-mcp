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
    'scripts/AppImage入口配置v3.py': (500, 330),
    'scripts/linux_startup_candidate.py': (300, 90),
    'scripts/Ubuntu原生验收v1.py': (400, 90),
    'scripts/跨平台原生驱动v8.py': (310, 55),
    'scripts/exclusive_native_acceptance.py': (440, 115),
    'scripts/preliminary_package_contract_tests.py': (100, 35),
    'scripts/linux_runtime_provenance.py': (500, 500),
    'scripts/linux_package_provenance_tests.py': (460, 460),
    'scripts/linux_package_binding_tests.py': (430, 430),
    'scripts/linux_runtime_provenance_tests.py': (500, 500),
    'scripts/linux_runtime_workflow_tests.py': (300, 300),
    'scripts/appimage_relro_tool.py': (370, 370),
    'scripts/appimage_relro_guard.py': (440, 440),
    'scripts/appimage_relro_contract.py': (495, 495),
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
    'scripts/desktop_glib_file_census.py': (70, 70),
    'scripts/desktop_glib_file_census_cases.py': (170, 170),
    'scripts/desktop_glib_build_evidence_tests.py': (500, 40),
}
MODES = {path: '100644' for path in CAPS}
MODES.update({'scripts/desktop_glib_build_evidence.py': '100755', 'scripts/appimage_relro_guard.py': '100755'})
DELTA_LIMIT = 8500
SOURCE_PINS = {
    '.github/workflows/linux-rc-packages.yml': ('100644', '7acae23c4d96c29f13326a4e172fa4b6c8859746', '66a0a63215a695c1af2678c463d145ec0c91acbbb702404ca38efdcea8d1dda9', 19434, 350),
    'scripts/desktop_glib_build_evidence.py': ('100755', '46638243c98fbd2c7ba6fd1fc90439fd70c2bd21', '52526fe848208e7a9307a036939f326ed92b2a3b5a09d9029cddd8eb6e2aa5f7', 17886, 318),
    'scripts/desktop_glib_build_contract.py': ('100644', '3a0d5c34424f344dfb622b74bc750cc3becd6c9d', '6597e7302058ca15e4198fde9bbfae1132c493fb73d5ac881140438efa54bbf4', 27740, 492),
    'scripts/linux_package_provenance.py': ('100644', 'c30782f36a89313487edb0ef5f1288d00c261117', 'e4f6fee05001fe9c08b136f434cdf65edc08ecb0d6110682aa972aeffc285127', 16540, 254),
    'scripts/linux_package_provenance_contract.py': ('100644', 'ba5724eea377d91319c0048acebd4cc22fa7f0f3', '377b5cdaf4f8567fc31f99682ce1b60c7867e8def472099d04a1b0b41d3d6330', 30267, 459),
    'scripts/rc_packages.py': ('100644', 'ea2dde33fd53a0ef8c01626461abe889610bc1e4', 'af0f8d3a0956d51714a0b8f2518532ed84fbbf437edd517b6e8103bebf0b0451', 8983, 186),
    'scripts/AppImage入口配置v3.py': ('100644', '835278f28d5aa229b40743804deabac7d8198a13', 'fffbff48a1d22ea786754de50fc3e48b1b2c2b569609a8a542649fca81343b5d', 33352, 496),
    'scripts/linux_startup_candidate.py': ('100644', '0ee6baad230a200350d118807e125dcd33d7f6e6', '7ee01af30d92486aca0d8af4468753b7546d295d20f071863a04aa18f4c6a0ba', 13398, 255),
    'scripts/Ubuntu原生验收v1.py': ('100644', 'add9f36fdad5dbc8cc741036d7fcc79cec38f4c0', '54eaf719d486ddefd788e8e4c5cdfec49d911991d7e35e5774518e328e1f5c19', 19123, 358),
    'scripts/跨平台原生驱动v8.py': ('100644', 'eaa8cd1fdbf18137eb2ca6e216ce9b38f44c9bbf', '073b92f8214afad017c12b2a22c23eef3195e38154d72f2fa09b640ea5b324f7', 14463, 274),
    'scripts/exclusive_native_acceptance.py': ('100644', 'b98554aafd78c7e7e376f43cb20a4f4686e2acbd', 'bac190d66cb78cf9a380b05b1da89f37044248072360725a58b12fcbb65c619e', 21690, 368),
    'scripts/preliminary_package_contract_tests.py': ('100644', '70e1fed6c36d10b7a12beb523316df021e5d3daf', '3600a1c881c5772c1315c6395548debb52ab20ad2cf198644a831ba9c927fa50', 5155, 92),
    'scripts/linux_runtime_provenance.py': ('100644', '2fce91a94a77ae9242c504792e64844453d8f6ba', 'f9c8be51aa9a0e449fada77059a2edf2cd22f9433871a8172463e0610b2bdf00', 30690, 457),
    'scripts/linux_package_provenance_tests.py': ('100644', '5e5daee97f8fbadd7cbb2affbbaa0ca05c92b13a', '73bdc7986219245a60ca84434a2ef57b91c4b6e2900e65e740f29153d2fe2bf4', 31486, 460),
    'scripts/linux_package_binding_tests.py': ('100644', '1bb31b4634b624238df34f087334558f7eeea172', '8b1ba7b624c4fcd99c05c8d313c6c759c0954088876138c376bf0497d9669f3a', 29145, 428),
    'scripts/linux_runtime_provenance_tests.py': ('100644', '689f3fc067a9e66062dc6fdbc8155f7549a057a5', '5baa753313e249395d9e748fe9c85fbd970f2961ccf7145c2c07c57ad28cce21', 38030, 500),
    'scripts/linux_runtime_workflow_tests.py': ('100644', '8d45b8be1ccbb9a27c2dba8301bb6520f5feefa5', '71413b9f4809a8796c609adf92d7519b8c8eea5997b60566a680d2e281debf60', 25782, 295),
    'scripts/appimage_relro_tool.py': ('100644', 'fb8b5690dda00c23f45d4b1833eed5d2f9d08bb5', 'a87d92253fab00a83805e93c266763484d5d7e2e64013f0ea35ee58e67cfea6f', 23051, 365),
    'scripts/appimage_relro_guard.py': ('100755', '464d744c846a85ecba4f510e65c6f99093bacde6', '286634b482acbd5103cf2c672ae9acc47504efcdb7299c33e7dcb90ea2227808', 22555, 440),
    'scripts/appimage_relro_contract.py': ('100644', 'b638e21b3d908c5d8828e46df995991a2fc73447', '099068a79e8603077b534d04e3b030f70efee808b6fd92e2852cda10cb0963ab', 33657, 491),
    'scripts/appimage_relro_tool_tests.py': ('100644', '932d454d3027b20e7659e1cba58b1dc0dae93f2c', 'a98f839fd5091ce7f7391aac28a5d3dfcd8380cb327547aab6d503596295b647', 20547, 306),
    'scripts/appimage_relro_guard_tests.py': ('100644', 'da34f74ae82c7248f0a3014bde00c30e141b0414', '8904bc99dc976fe26da2c93a904133d743bd74091a57bbf3c4614e2cfb5c0389', 24930, 416),
    'scripts/appimage_relro_contract_tests.py': ('100644', '6c978251e98eef30c1f10c9b22ce457d162d260d', '94b3408fe134cf311c2417cb44722255786d934a8fe84338928c840f3205a74c', 23405, 352),
    'docs/specs/linux-package-provenance-relro/requirements.md': ('100644', '1c8c37a8842a64787f912b54350e8ff7fbcd03b3', '12b3e03bb062fa1ad6f8c1ba5c30ff9a756fa1ef63987dc6106463c639ad355b', 9785, 103),
    'docs/specs/linux-package-provenance-relro/design.md': ('100644', '17a5ed556378c735264573d048293cec1e2cbf3c', '9ef21fa5d6891b411435b29a4ba8dd90333589a7f17f93e97bfa976c98753c3a', 33112, 190),
    'docs/specs/linux-package-provenance-relro/tasks.md': ('100644', 'a7a3a0c3f912fcba7a35a4397b01b7bb8a6aea78', 'f4b385ee261e1b1543c78ecb332d2f732df629eac91865f21615a6d42e86e103', 12119, 109),
    'scripts/rc_pretag_linux_package_inverse.py': ('100644', 'fe6f6ab0362d1005e3e3a41f573504574118b6af', '22e91e1c47d803dcc2cd002cdea81b9dbf32ef0d358e490038243fd5cb6c45a0', 109917, 172),
    'scripts/rc_pretag_linux_package_cases.py': ('100644', '2e8b789a708ff1b6d9bcbe71a083696c075e0eb4', '94c6c06f480c99f958bd316ae4c985a6182f37851f89408024d97147e3a13168', 30386, 440),
    'scripts/rc_pretag_publication_profile.py': ('100644', 'e2b87b630e4d00406020dc173fdec47a32ed2e96', '687bebbe836960a9ccf6e7c657e2955200aefd593e7b84c136b66d69e8941409', 32493, 499),
    'scripts/rc_pretag_appimage_profile.py': ('100644', '1903473701ad2e8780e7db812f98c7e3d26b7c75', 'e319be4c77e392e1bfc78938e91af1e98684cb710dbe3d6393a22ed200cc8286', 10957, 153),
    'scripts/rc_pretag_appimage_cases.py': ('100644', 'be5464078eb8369452ae28e94d4baa9f446746e0', 'a9fc69726fac6188b6a0650b222bc4b4bb66c22618918d71f88cde426cd2b6eb', 29783, 402),
    'scripts/AppImage入口回归v3.py': ('100644', '30f74f356ee2e4df0a81af711e0f850c4512234c', '6d7b8786f32d28e3186139036d9c644b01459f9aeb6f10c528cada1827096b91', 9036, 167),
    'scripts/exact_build_audit.py': ('100644', '49c81b1d77a83536ad7330ec0d42169fd423a1c3', '85e8b30e456ac4a83616564389de628a0aa3e9d5447775f0496e9b1c475ccf80', 26407, 426),
    'scripts/desktop_glib_file_census.py': ('100644', '1a44e72659619b45e17c5ab6d94fad3b8d207717', '0687d52ebc474213f18dfd73e2dbb763404c769aac0e4ff7da5aaec6427c4afe', 1558, 40),
    'scripts/desktop_glib_file_census_cases.py': ('100644', 'dc183c985645949249bd515837110929ca177030', '54b350ff34ac1f2d22834d5fc60fa87db05d2ae9f614ccab90d1a5ac4d6ea66f', 5867, 132),
    'scripts/desktop_glib_build_evidence_tests.py': ('100644', '229e46713df40af2f8d68c85192aa19e5200e816', '4ceab8c2d5fc68c0923ad42d6c0e4cdbdecd93eece002c1dec86ed46e261cb97', 26644, 464),
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
    assert len(baseline) == 1705 and len(paths) == 37
    assert SOURCE_PINS.keys() == paths - {PROFILE} and MODES.keys() == paths
    assert baseline.keys() & paths == inverse.BASE_PINS.keys() and len(inverse.BASE_PINS) == 16
    assert actual.keys() == baseline.keys() | paths and len(actual) == 1726
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
    import rc_pretag_yoke_repair_profile as yoke
    selected = yoke.select(ref, root, git, entries, historical, release, release_tree, documents)
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
