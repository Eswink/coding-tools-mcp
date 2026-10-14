"""Finite #150 topology admission for RC070 packaging tip ae4e8483c560; independent review binds self-bytes."""
import hashlib
import rc_pretag_ownership_profile as o
import rc_pretag_publication_profile as p

M = 'ae4e8483c560865ffaec80d75f46087c806fe964'
M_TREE = 'f21b089b212b91e9882228b81eaa3d23efbb4fdc'
M_PARENTS = ('dcd7159140f106f192e97d325aae95a882e250d3',)
M_RAW = (508, '94066834394879130531760fc8e3ceaf4c1c13aa56a55560060518a5bc166e25')
BASE = '41984b1de0ca13efab3646aae5041845bc78cfee'
PROFILE = 'scripts/rc_pretag_rc070_topology_profile.py'
CAPS = {
    PROFILE: (120, 39),
    'scripts/rc_pretag_integration_admission_profile.py': (371, 13),
    'scripts/rc_pretag_linux_package_profile.py': (186, 7),
}
DELTA_LIMIT = 64
BASE_PINS = {
    'scripts/rc_pretag_integration_admission_profile.py': ('100644', '514efb0c0e7cf0554e45db38abca67866b91b390', 'ff6f8a08f821ebb1f9c612910b998196d697983a91034089d2da97a579f53c0d', 109166, 364),
    'scripts/rc_pretag_linux_package_profile.py': ('100644', 'f8a5fa41d30dc111c6837845217fa481ed9f5576', 'e59503b43f8f9a44acf7c0ae5aa9040e4c88343e1ee46d749727467a35bd67b8', 14589, 181),
}
SOURCE_PINS = {
    'scripts/rc_pretag_integration_admission_profile.py': ('100644', 'bc85c20c7de97dffe04bef76a702f05ded32a3dc', '5fd82ff2f4818b0fe2235dbdd49604f7e2cebb428a9648c0cdcb832ae2afedb5', 109746, 366),
    'scripts/rc_pretag_linux_package_profile.py': ('100644', 'cdb82073d8ffd0eed7e62d324ea1210025ba2a87', '29b9480129319b8377d51548bfa56a3f9411d17a57fde48c524d7576047b7313', 14589, 181),
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
