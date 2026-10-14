"""Finite #150 topology admission for RC070 packaging tip dcd7159140f1; independent review binds self-bytes."""
import hashlib
import rc_pretag_ownership_profile as o
import rc_pretag_publication_profile as p

M = 'dcd7159140f106f192e97d325aae95a882e250d3'
M_TREE = 'fc12a87f06b45d8fe3a7b1a1e6624a4334c5f940'
M_PARENTS = ('eeb84f93da44dcaf083898998f92416e4cdfd3da',)
M_RAW = (512, '53ee43811ccb089970414cfc9bdde823488bfddf95fcc3bd6b4764013f859acf')
BASE = '41984b1de0ca13efab3646aae5041845bc78cfee'
PROFILE = 'scripts/rc_pretag_rc070_topology_profile.py'
CAPS = {
    PROFILE: (105, 30),
    'scripts/AppImage入口配置v3.py': (496, 2),
    'scripts/rc_pretag_linux_package_inverse.py': (218, 4),
    'scripts/rc_pretag_linux_package_profile.py': (181, 4),
}
DELTA_LIMIT = 40
BASE_PINS = {
    'scripts/AppImage入口配置v3.py': ('100644', '835278f28d5aa229b40743804deabac7d8198a13', 'fffbff48a1d22ea786754de50fc3e48b1b2c2b569609a8a542649fca81343b5d', 33352, 496),
    'scripts/rc_pretag_linux_package_inverse.py': ('100644', 'bd57a890a61a7c1cd9ef4c7d3aacd41f7f2eda6c', '9f4a90fb0faea825a87cc7487c5ca5334456f20f8e032f54875dadf84ff91916', 114736, 218),
    'scripts/rc_pretag_linux_package_profile.py': ('100644', 'dc1336fb7c7182cf605847fff05b27a6185aac09', '820e0364f3e634da54861fb0e267d81f4dad8c4c139e8f46241a6622dc0ec578', 14589, 181),
}
SOURCE_PINS = {
    'scripts/AppImage入口配置v3.py': ('100644', '327b65cc69cf0a3c8452d21983b9a032dca38959', '1df65ca6e3d8de0174b8f758c21806618a511507d32a1915fb61162b57f6eec9', 33352, 496),
    'scripts/rc_pretag_linux_package_inverse.py': ('100644', '55269c3fc4d2340e5f55ea3d2707c8acc0262c0c', '583ab878f66ffde7eff870518fe530368e9cdc72e4cc608bca0bc0abdf1365e7', 114736, 218),
    'scripts/rc_pretag_linux_package_profile.py': ('100644', 'f8a5fa41d30dc111c6837845217fa481ed9f5576', 'e59503b43f8f9a44acf7c0ae5aa9040e4c88343e1ee46d749727467a35bd67b8', 14589, 181),
}


def topology(ref, root, git, release):
    """Admit D[M], I[M,D], J[R,I], and GitHub PR-merge [BASE, D|M] for packaging tip parent graph."""
    if release != p.R:
        raise o.TopologyError('rc070_release_anchor')
    parents = o._parents(ref, root, git)
    if ref == M:
        return 'nonrelease', ref, ref
    if parents == [M]:
        kind, tip, source = 'nonrelease', ref, ref
    elif len(parents) == 2 and parents[0] == M:
        kind, tip, source = 'nonrelease', ref, parents[1]
    elif len(parents) == 2 and parents[0] == BASE and parents[1] == M:
        kind, tip, source = 'nonrelease', ref, M
    elif len(parents) == 2 and parents[0] == BASE and o._parents(parents[1], root, git) == [M]:
        kind, tip, source = 'nonrelease', ref, parents[1]
    elif len(parents) == 2 and parents[0] == p.R:
        kind, tip = 'release', parents[1]
        feature_parents = o._parents(tip, root, git)
        if feature_parents == [M]:
            source = tip
        elif len(feature_parents) == 2 and feature_parents[0] == M:
            source = feature_parents[1]
        else:
            raise o.TopologyError('rc070_feature_parents')
    else:
        raise o.TopologyError('rc070_candidate_parents')
    if source != M and o._parents(source, root, git) != [M]:
        raise o.TopologyError('rc070_candidate_parent')
    return kind, tip, source


def content(ref, root, git, entries, historical, release, release_tree, documents):
    """Fresh M tree identity and exact candidate pins over packaging tip."""
    assert (release, release_tree, documents) == (p.R, p.R_TREE, p.R_DOCUMENTS)
    assert tuple(o._parents(M, root, git)) == M_PARENTS, 'rc070 M parents'
    assert git('rev-parse', M + '^{tree}', root=root).decode().strip() == M_TREE, 'rc070 M tree'
    raw = git('cat-file', 'commit', M, root=root)
    assert (len(raw), hashlib.sha256(raw).hexdigest()) == M_RAW, 'rc070 M raw'
    baseline = entries(M, root)
    assert len(baseline) >= 1800
    if ref == M:
        return baseline
    actual, paths = entries(ref, root), set(CAPS)
    assert SOURCE_PINS.keys() == paths - {PROFILE}
    assert actual.keys() == baseline.keys() | paths
    assert {path for path in actual if actual[path] != baseline.get(path)} == paths
    assert all(actual[path] == value for path, value in baseline.items() if path not in paths)
    assert all(actual[path][:2] == ('100644', 'blob') for path in paths)
    data = {path: git('cat-file', 'blob', actual[path][2], root=root) for path in paths}
    for path, (mode, blob, digest, size, count) in SOURCE_PINS.items():
        assert mode == '100644' and actual[path] == (mode, 'blob', blob), path
        assert o.pin(data[path]) == (blob, digest), path
        assert (len(data[path]), len(data[path].splitlines())) == (size, count), path
    assert len(data[PROFILE].splitlines()) <= CAPS[PROFILE][0]
    for path, row in BASE_PINS.items():
        assert baseline[path] == (row[0], 'blob', row[1]), path
    p.authenticated._budgets(ref, M, root, git, data, CAPS, DELTA_LIMIT, 'rc070_delta_budget')
    return actual


def select(ref, root, git, entries, historical, release, release_tree, documents):
    """Only topology mismatch delegates; selected and historical content errors escape."""
    ref = o._commit(ref, root, git)
    try:
        kind, tip, source = topology(ref, root, git, release)
    except o.TopologyError:
        return None
    if ref == M:
        assert git('rev-parse', ref + '^{tree}', root=root).decode().strip() == M_TREE
        return entries(ref, root)
    expected = content(source, root, git, entries, historical, release, release_tree, documents)
    assert entries(tip, root) == expected
    if kind == 'release':
        return o.release_content(ref, expected, root, git, entries, release, release_tree, documents)
    return expected
