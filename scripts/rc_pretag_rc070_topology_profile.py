"""Finite #150 topology admission for RC070 packaging tip cd73cd26f7274d9d4c8b950d93165aaeef1f451d; independent review binds self-bytes."""
import hashlib
import rc_pretag_ownership_profile as o
import rc_pretag_publication_profile as p

M = 'cd73cd26f7274d9d4c8b950d93165aaeef1f451d'
M_TREE = 'bc2b5e471d7292527dd685b909b92f02b9eed1c2'
M_PARENTS = ('c90ba82eeaed827b37536483fdf3b15f01ba46f0',)
M_RAW = (835, '5613904106880140490c506bb0bddd1064a3414bf890a86f812cef4d3b0f37d5')
BASE = '41984b1de0ca13efab3646aae5041845bc78cfee'
PROFILE = 'scripts/rc_pretag_rc070_topology_profile.py'
MANIFEST = 'scripts/rc_native_probe_source_manifest.json'
REVIEWED = 'docs/releases/reviewed-source-manifest.json'
NEW = ()
CAPS = {
    PROFILE: (180, 250),
    'scripts/rc_pretag_integration_admission_profile.py': (400, 33),
}
DELTA_LIMIT = 120
BASE_PINS = {
    'scripts/rc_pretag_integration_admission_profile.py': ('100644', 'a9b60253e463917b3b81f693261a818bc92d71bf', 'a8f71f27cb5932d10e3407f0e6d836a7ea6751cfe33a047c91badae1504070b0', 191807, 381),
}
SOURCE_PINS = {
    'scripts/rc_pretag_integration_admission_profile.py': ('100644', '3433a4ca77a1c9e7899e5814754936abd34afb28', '3947c25eaf54519f0828a33553836af5ebb4fe8b467e3931e1d9cecdb6418871', 231694, 400),
}

def _reviewed_only(parent, child, root, git, entries):
    """True iff child tree is parent tree plus sole 100644 REVIEWED path."""
    base, actual = entries(parent, root), entries(child, root)
    if actual.keys() != base.keys() | {REVIEWED}:
        return False
    if any(actual[path] != base[path] for path in base):
        return False
    return actual[REVIEWED][:2] == ('100644', 'blob')


def _overlay_reviewed(base, actual):
    """Admit tip entries as source entries plus sole 100644 REVIEWED path."""
    assert actual.keys() == base.keys() | {REVIEWED}, 'rc070_reviewed_overlay_paths'
    assert all(actual[path] == base[path] for path in base), 'rc070_reviewed_overlay_drift'
    assert actual[REVIEWED][:2] == ('100644', 'blob'), 'rc070_reviewed_overlay_mode'
    return dict(base, **{REVIEWED: actual[REVIEWED]})


def topology(ref, root, git, release):
    """Admit D[M], manifest-only D'[D], one CAPS cascade on D', one refresh cascade on that tip, I[M,D], J[R,I], PR-merge [BASE, D|M]."""
    if release != p.R:
        raise o.TopologyError('rc070_release_anchor')
    parents = o._parents(ref, root, git)
    if ref == M:
        return 'nonrelease', ref, ref
    if parents == [M]:
        kind, tip, source = 'nonrelease', ref, ref
    elif len(parents) == 1 and o._parents(parents[0], root, git) == [M]:
        # D'[D] overlay candidate (select requires reviewed-only delta).
        kind, tip, source = 'nonrelease', ref, parents[0]
    elif (len(parents) == 1
          and len(o._parents(parents[0], root, git)) == 1
          and o._parents(o._parents(parents[0], root, git)[0], root, git) == [M]):
        # One CAPS cascade on D'[D]; select proves parent is reviewed-only on D.
        kind, tip, source = 'nonrelease', ref, ref
    elif (len(parents) == 1
          and len(o._parents(parents[0], root, git)) == 1
          and len(o._parents(o._parents(parents[0], root, git)[0], root, git)) == 1
          and o._parents(o._parents(o._parents(parents[0], root, git)[0], root, git)[0], root, git) == [M]):
        # One reviewed-source / CAPS refresh cascade on the Option R tip; deeper fall through.
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
    if source != ref and source != M and o._parents(source, root, git) != [M]:
        raise o.TopologyError('rc070_candidate_parent')
    return kind, tip, source


def content(ref, root, git, entries, historical, release, release_tree, documents):
    """Fresh M tree identity and exact candidate pins over packaging tip; REVIEWED optional."""
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
    reviewed = {REVIEWED} if REVIEWED in actual else set()
    assert SOURCE_PINS.keys() == paths - {PROFILE}
    assert actual.keys() == baseline.keys() | paths | reviewed
    assert {path for path in actual if actual[path] != baseline.get(path)} == paths | {MANIFEST} | reviewed
    assert all(actual[path] == value for path, value in baseline.items() if path not in paths | {MANIFEST} | reviewed)
    assert all(actual[path][:2] == ('100644', 'blob') for path in paths | {MANIFEST} | reviewed)
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
    parents = o._parents(ref, root, git)
    if tip == source and len(parents) == 1:
        parent_parents = o._parents(parents[0], root, git)
        # Only the CAPS cascade-on-D' shape needs the reviewed-only parent proof.
        if (len(parent_parents) == 1
                and o._parents(parent_parents[0], root, git) == [M]
                and not _reviewed_only(parent_parents[0], parents[0], root, git, entries)):
            return None
    expected = content(source, root, git, entries, historical, release, release_tree, documents)
    actual = entries(tip, root)
    if tip != source:
        if not _reviewed_only(source, tip, root, git, entries):
            assert False, 'rc070_reviewed_overlay'
        expected = _overlay_reviewed(expected, actual)
    assert actual == expected
    if kind == 'release':
        return o.release_content(ref, expected, root, git, entries, release, release_tree, documents)
    return expected
