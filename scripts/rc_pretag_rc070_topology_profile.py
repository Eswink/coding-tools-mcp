"""Finite #150 topology admission for RC070 packaging tip cb87dbb11e30d9f54a2d020395fe03e9c436c8ae; independent review binds self-bytes."""
import hashlib
import rc_pretag_ownership_profile as o
import rc_pretag_publication_profile as p

M = 'cb87dbb11e30d9f54a2d020395fe03e9c436c8ae'
M_TREE = '36d40fd735831e1b6e636bc6fe30f9b76ee8d030'
M_PARENTS = ('24b8b7559582e74c2f788bc750a92f14d94321b6',)
M_RAW = (453, '6b446aef9ca1cf94ec1135601128ffdd88a4e83c4e409a0bf13f03bb67ece492')
BASE = '41984b1de0ca13efab3646aae5041845bc78cfee'
PROFILE = 'scripts/rc_pretag_rc070_topology_profile.py'
MANIFEST = 'scripts/rc_native_probe_source_manifest.json'
NEW = ()
CAPS = {
    PROFILE: (130, 250),
    'scripts/rc_pretag_integration_admission_profile.py': (377, 14),
}
DELTA_LIMIT = 80
BASE_PINS = {
    'scripts/rc_pretag_integration_admission_profile.py': ('100644', '71eb3b4119d8ea2952890767e154f41c2d04641e', '9819f31f31a2e4681a3b272d83c0236ec39db5024b55ea4cdd46be97fab8ac62', 157899, 367),
}
SOURCE_PINS = {
    'scripts/rc_pretag_integration_admission_profile.py': ('100644', '5e1ac472acc8d66360c15253733838bfbd51580b', '45ce68059b44714bbf21c24c0bfb866781bb054cc73b0f43900a7e5ab7fec5b5', 191588, 377),
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
    assert baseline[MANIFEST][:2] == ('100644', 'blob')
    if ref == M:
        return baseline
    actual, paths = entries(ref, root), set(CAPS)
    assert SOURCE_PINS.keys() == paths - {PROFILE}
    assert actual.keys() == baseline.keys() | paths
    assert {path for path in actual if actual[path] != baseline.get(path)} == paths | {MANIFEST}
    assert all(actual[path] == value for path, value in baseline.items() if path not in paths | {MANIFEST})
    assert all(actual[path][:2] == ('100644', 'blob') for path in paths | {MANIFEST})
    data = {path: git('cat-file', 'blob', actual[path][2], root=root) for path in paths}
    manifest = git('cat-file', 'blob', actual[MANIFEST][2], root=root)
    for path, (mode, blob, digest, size, count) in SOURCE_PINS.items():
        assert mode == '100644' and actual[path] == (mode, 'blob', blob), path
        assert o.pin(data[path]) == (blob, digest), path
        assert (len(data[path]), len(data[path].splitlines())) == (size, count), path
    assert len(data[PROFILE].splitlines()) <= CAPS[PROFILE][0]
    for path, row in BASE_PINS.items():
        assert baseline[path] == (row[0], 'blob', row[1]), path
    p.authenticated._budgets(ref, M, root, git, data, CAPS, DELTA_LIMIT, 'rc070_delta_budget')
    assert manifest == _manifest(git('cat-file', 'blob', baseline[MANIFEST][2], root=root), actual, data), 'rc070 manifest'
    return actual


def _manifest(previous, actual, data):
    """Recompute the derived manifest: M manifest with only the finite changed rows replaced by their actual bytes."""
    import json
    table = json.loads(previous)
    assert table['schema'] == 'rc-native-probe-source-manifest/v1' and table['excludes_self'] == MANIFEST
    rows = {row['path']: row for row in table['rows']}
    assert len(rows) == table['entries'] == len(table['rows']) and set(data) - rows.keys() == set(NEW)
    for path, raw in data.items():
        rows[path] = dict(path=path, mode=actual[path][0], blob=actual[path][2], bytes=len(raw),
                          sha256=hashlib.sha256(raw).hexdigest())
    rows = sorted(rows.values(), key=lambda row: row['path'])
    return (json.dumps(dict(schema=table['schema'], excludes_self=MANIFEST, entries=len(rows), rows=rows),
                       indent=1, sort_keys=True) + '\n').encode()


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
