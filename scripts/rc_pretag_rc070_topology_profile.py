"""Finite #150 topology admission for RC070 packaging tip 3299b461a3b7; independent review binds self-bytes."""
import hashlib
import rc_pretag_ownership_profile as o
import rc_pretag_publication_profile as p

M = '3299b461a3b7c542440051cce1323c193f7e69eb'
M_TREE = '4c4d7842a503d8bfca2fc6ccd301fe8c35bae2f2'
M_PARENTS = ('05363d94adc89c9eb488282df33ce5205da3a2b4',)
M_RAW = (305, '51ce40b236f53dbecc9931b0be016868ff607d70690abcc7cb3a406b60b3c77f')
BASE = '41984b1de0ca13efab3646aae5041845bc78cfee'
PROFILE = 'scripts/rc_pretag_rc070_topology_profile.py'
MANIFEST = 'scripts/rc_native_probe_source_manifest.json'
NEW = ()
CAPS = {
    PROFILE: (134, 86),
    'scripts/rc_pretag_integration_admission_profile.py': (362, 14),
    'scripts/rc_pretag_linux_package_cases.py': (444, 2),
    'scripts/rc_pretag_linux_package_inverse.py': (213, 15),
    'src-tauri/Cargo.lock': (6556, 354),
    'src-tauri/Cargo.toml': (95, 2),
    'src-tauri/src/tunnel/frp/client.rs': (1061, 5),
}
DELTA_LIMIT = 478
BASE_PINS = {
    'scripts/rc_pretag_integration_admission_profile.py': ('100644', '3b3ada6e21d3603bcd76ba729b7092c45e4ed281', '4c0462c323d413c532f333d2071de6b34c1e933747b3206907a9aefcaefe9c72', 131609, 364),
    'scripts/rc_pretag_linux_package_cases.py': ('100644', '621c8a41a649c27016595cbf0a977edb7a53d03e', 'f0d28ebf1921633e11c6a86cf13a891c5c9e34f9f93d843a11a23e2f5ebdb393', 31006, 444),
    'scripts/rc_pretag_linux_package_inverse.py': ('100644', '55269c3fc4d2340e5f55ea3d2707c8acc0262c0c', '583ab878f66ffde7eff870518fe530368e9cdc72e4cc608bca0bc0abdf1365e7', 114736, 218),
    'src-tauri/Cargo.lock': ('100644', '73810757f12f5fb692809182168b6c59a5a4fc90', '51a1b8178e8d8933256975acb5a7eb2e4cbfc84805db6f2d9bda7a0c084cd85a', 155415, 6470),
    'src-tauri/Cargo.toml': ('100644', '9bca05716da181f2086ec5bef75b4dced75fc350', 'f2bfbce7f94857ab061c60ec462e137bcb24e51fc8bda190780c337378b7bff2', 2856, 95),
    'src-tauri/src/tunnel/frp/client.rs': ('100644', 'b4398ed557e9f859cad2242b2fd4dd3038f6530a', '0cda12c8381c2fecd1b5cf4868f0c3e86234aa71fd30f388331c9fca3c515cef', 35861, 1058),
}
SOURCE_PINS = {
    'scripts/rc_pretag_integration_admission_profile.py': ('100644', '0f4c449234967c18b26444d39a8cb629d63b75e9', '952a7072a3ffacab1d7562396aad19b6f35fcaf54262e0c2d34f880f42820a15', 148038, 362),
    'scripts/rc_pretag_linux_package_cases.py': ('100644', '7ec8ec753fd6a0d150b95aa2c5800acda25e479a', '61e0b3f30a6effa0821433d1598029c34a11645355db3e4b2e09cf4dbcefbcae', 31054, 444),
    'scripts/rc_pretag_linux_package_inverse.py': ('100644', '162b27125fff31d8b141af9b34249045e162c72f', 'ce542198f9114535333b1e9a2b9329c682f09bd5f1d82b0ec936b6600a828d33', 127614, 213),
    'src-tauri/Cargo.lock': ('100644', '9717ff3d97ee8a7162100ec79615fe7e108e6af0', '314746cb283ae3f9138cd1af2ce288eaebf6c6ef200a8f477546c54037f5376c', 157986, 6556),
    'src-tauri/Cargo.toml': ('100644', 'b6f055be7b2b8b17dea6453f858f504df5f484aa', 'fbc3827202ae8171f22fc774f22ec7ba2f981c0412b1e0250fad12a07b140700', 2861, 95),
    'src-tauri/src/tunnel/frp/client.rs': ('100644', '7a5be415dc123a8f9164f2426fe61c8beec5f457', '2cc1cd65ab28cd97f4f8539881c471d5829805cbcb93815270182be7585fa510', 35990, 1061),
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
