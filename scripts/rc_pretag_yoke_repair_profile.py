"""Finite supported yoke repair; this module is bound by external exact-tree review."""
import rc_pretag_ownership_profile as o
import rc_pretag_publication_profile as p

F = 'b97c469b1bd7ffb9973a65e19b798d2573561d92'
F_TREE = 'c017dc6e5f2fde6f9f135119500916cbe88efe1e'
F_PARENTS = ('fd7b303839aa648d33456f7aaeec6388bfb696c4', 'decfd70c746c5dd0d7d7c6ceace718c5a49487da')
PROFILE = 'scripts/rc_pretag_yoke_repair_profile.py'
CASES = 'scripts/rc_pretag_yoke_repair_cases.py'
DISPATCHER = 'scripts/rc_pretag_linux_package_profile.py'
LOCKS = ('services/cloud-agent/Cargo.lock', 'services/cloud-gateway/Cargo.lock')
CAPS = {
    LOCKS[0]: (1108, 4),
    LOCKS[1]: (2266, 4),
    DISPATCHER: (185, 4),
    PROFILE: (220, 220),
    CASES: (300, 300),
    'docs/specs/issue85-yoke-derive-repair/requirements.md': (40, 40),
    'docs/specs/issue85-yoke-derive-repair/design.md': (60, 60),
    'docs/specs/issue85-yoke-derive-repair/tasks.md': (40, 40),
    '.github/workflows/issue85-yoke-repair.yml': (100, 100),
}
DELTA_LIMIT = 720
BASE_PINS = {
    LOCKS[0]: ('100644', 'd510afffae9736ba5b2adedf64c46dbe9339268a', '3f8dd94af3320b153a9e603d52de6cb2bb641fc41cfaccaf273f1b6f830e1ca4', 28481, 1108),
    LOCKS[1]: ('100644', 'bf30452d8ec8b189fcaaeb8e8773b7c1864d8557', '07a7ebf07a4eed704b90dd1cea07da86be2db5745d82a49539b50c78c241286c', 56017, 2266),
    DISPATCHER: ('100644', 'd451ff32982277ee8973474e73a8181122acccb8', '1d63404fdda8de88a6044dfc282a25ac52aedf4c72b011156c8573186c370730', 14366, 177),
}
# Static non-self pins are sealed only after all nine reviewed paths are final.
SOURCE_PINS = {
    'services/cloud-agent/Cargo.lock': ('100644', 'aaab1e3d54217797ae117e75632d8c092820d42c', 'c564eb65afd4e45896fcacc66e690dec74ba142bef287383de5a98cf77679a3b', 28481, 1108),
    'services/cloud-gateway/Cargo.lock': ('100644', '3cce48a094cc41f437d339b4c52453fbf5570119', '45d52b90b00056cd3e14bb191ea1ea6c6c8fdd8a4ee955ab64d076d857e53023', 56017, 2266),
    'scripts/rc_pretag_linux_package_profile.py': ('100644', '35c0bf4c4a0d875e4f0be442ed72f5d7038956ed', '5819ac28c0986253b6d9be0f9c4b1f236acdf8005de6ae1d63ce6d2dbe20df2e', 14566, 181),
    'scripts/rc_pretag_yoke_repair_cases.py': ('100644', '47656a740993e6bcdd8b3a532b530045e64a5519', '44d10b8b6c10616bdbb793d2f68889e65359496bac3c6bbac8821335ca946243', 18358, 286),
    'docs/specs/issue85-yoke-derive-repair/requirements.md': ('100644', '0eb6fb0dffadd814548f584015e68fdd205bb465', '346e036e7e40ab2bfcbb79779f95c75f733deadd180ac3f5c92c133fe99f9ae7', 3113, 28),
    'docs/specs/issue85-yoke-derive-repair/design.md': ('100644', 'c8e23c75aa5f1ba65c8a4a3efccc689ebfedda16', 'd723fe0e8d6a421f471894974d266085b4aa9c41ff7b6096ec2ffac33eb61c92', 4707, 37),
    'docs/specs/issue85-yoke-derive-repair/tasks.md': ('100644', '5917b6301f8af3a94710a5e4c3b8b206f43d40a2', '7f81a336e9dd3cbd6f8fbf5c939dd365a2ea444b48fec50c7e0925fcbdd6db9b', 2767, 36),
    '.github/workflows/issue85-yoke-repair.yml': ('100644', 'f6d35e42749e00b74da18134d3f4445cc1936cfa', '0ca4a791605b4e6948a74e5a6ba1e86617fdef033c4d4a04f6d3e6723689194e', 6572, 100),
}
DISPATCH = (
    b'    import rc_pretag_yoke_repair_profile as yoke\n'
    b'    selected = yoke.select(ref, root, git, entries, historical, release, release_tree, documents)\n'
    b'    if selected is not None:\n'
    b'        return selected\n'
)
OLD_BLOCK = b'''[[package]]
name = "yoke-derive"
version = "0.8.3"
source = "registry+https://github.com/rust-lang/crates.io-index"
checksum = "33811428bee40dbceb6d545e95754741d17a6aef9a4849f0fd62e2ba4f412a78"
dependencies = [
 "proc-macro2",
 "quote",
 "syn 3.0.6",
 "synstructure",
]

'''
NEW_BLOCK = OLD_BLOCK.replace(b'version = "0.8.3"', b'version = "0.8.4"').replace(
    b'33811428bee40dbceb6d545e95754741d17a6aef9a4849f0fd62e2ba4f412a78',
    b'ec8ebde2db3681e8c9980cc27822030e68752690ddfa9473e739aeb4dbde6d71')
CLASS = 'rc_pretag_yoke_repair_cases.YokeRepairCompositionTests'
NAMES = (
    'test_exact_f_identity_and_fresh_historical_validation',
    'test_ordered_candidate_merge_and_release_overlay',
    'test_invalid_parent_topologies_and_same_tree_anchors_reject',
    'test_only_two_yoke_derive_records_change',
    'test_source_paths_modes_types_and_pins_are_exact',
    'test_per_file_and_aggregate_budgets_reject',
    'test_dispatch_and_lock_inverses_recover_f_bytes',
    'test_selected_and_historical_failures_are_terminal',
    'test_isolated_git_and_protected_boundaries',
    'test_original_and_new_test_inventories_are_exact',
)
DIGEST = 'd3ad07a7501391fdb93193ce8641610ba28f15ad6796b4c595c6ac9507af3e35'


def inverse(path, current):
    """Recover complete F bytes through one exact reviewed replacement, without IO."""
    assert type(path) is str and type(current) is bytes and path in BASE_PINS
    row = SOURCE_PINS[path]
    assert (o.pin(current), len(current), len(current.splitlines())) == (row[1:3], row[3], row[4])
    before, after = (DISPATCH, b'') if path == DISPATCHER else (NEW_BLOCK, OLD_BLOCK)
    assert current.count(before) == 1, 'yoke inverse fragment missing or duplicated'
    restored = current.replace(before, after, 1)
    row = BASE_PINS[path]
    assert (o.pin(restored), len(restored), len(restored.splitlines())) == (row[1:3], row[3], row[4])
    return restored


def topology(ref, root, git, release):
    """Accept only D[F], I[F,D], J[R,I]; content owns immutable anchor checks."""
    if release != p.R:
        raise o.TopologyError('yoke_release_anchor')
    parents = o._parents(ref, root, git)
    if parents == [F]:
        kind, tip, source = 'nonrelease', ref, ref
    elif len(parents) == 2 and parents[0] == F:
        kind, tip, source = 'nonrelease', ref, parents[1]
    elif len(parents) == 2 and parents[0] == p.R:
        kind, tip = 'release', parents[1]
        feature_parents = o._parents(tip, root, git)
        if len(feature_parents) != 2 or feature_parents[0] != F:
            raise o.TopologyError('yoke_feature_parents')
        source = feature_parents[1]
    else:
        raise o.TopologyError('yoke_candidate_parents')
    if o._parents(source, root, git) != [F]:
        raise o.TopologyError('yoke_candidate_parent')
    return kind, tip, source


def content(ref, root, git, entries, historical, release, release_tree, documents):
    """Freshly validate full F, the nine-path delta, fixed pins and byte inverses."""
    assert (release, release_tree, documents) == (p.R, p.R_TREE, p.R_DOCUMENTS)
    assert tuple(o._parents(F, root, git)) == F_PARENTS, 'yoke F parents'
    assert git('rev-parse', F + '^{tree}', root=root).decode().strip() == F_TREE, 'yoke F tree'
    baseline = p.selected_profile(F, root, git, entries, historical, release, release_tree, documents)
    assert baseline == entries(F, root) and len(baseline) == 1726
    actual, paths = entries(ref, root), CAPS.keys()
    assert len(paths) == 9 and SOURCE_PINS.keys() == paths - {PROFILE}
    assert baseline.keys() & paths == BASE_PINS.keys() and len(BASE_PINS) == 3
    assert actual.keys() == baseline.keys() | paths and len(actual) == 1732
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
    p.authenticated._budgets(ref, F, root, git, data, CAPS, DELTA_LIMIT, 'yoke_delta_budget')
    return actual


def select(ref, root, git, entries, historical, release, release_tree, documents):
    """Only topology mismatch delegates; selected and historical failures propagate."""
    ref = o._commit(ref, root, git)
    try:
        kind, tip, source = topology(ref, root, git, release)
    except o.TopologyError:
        return None
    expected = content(source, root, git, entries, historical, release, release_tree, documents)
    assert entries(tip, root) == expected
    if kind == 'release':
        return o.release_content(ref, expected, root, git, entries, release, release_tree, documents)
    return expected
