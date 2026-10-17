"""Finite #150 topology admission for RC070 packaging tip e1f5695803c9; independent review binds self-bytes."""
import hashlib
import rc_pretag_ownership_profile as o
import rc_pretag_publication_profile as p

M = 'e1f5695803c9c19252095f6b2d830d204d9736d0'
M_TREE = '7bc7d00b3295527346524c64e4b9c03a38d9264b'
M_PARENTS = ('3299b461a3b7c542440051cce1323c193f7e69eb',)
M_RAW = (516, 'cd49611eafea29271875f2b158ab731d678c2c7d36391916846f6735d5320eef')
BASE = '41984b1de0ca13efab3646aae5041845bc78cfee'
PROFILE = 'scripts/rc_pretag_rc070_topology_profile.py'
MANIFEST = 'scripts/rc_native_probe_source_manifest.json'
NEW = ()
CAPS = {
    PROFILE: (133, 47),
    'scripts/exclusive_native_acceptance.py': (392, 26),
    'scripts/rc_pretag_integration_admission_profile.py': (362, 12),
    'scripts/rc_pretag_linux_package_cases.py': (444, 2),
    'scripts/rc_pretag_linux_package_inverse.py': (208, 11),
    'scripts/聊天授权原生验收v6.py': (315, 5),
    'src-tauri/src/app_state.rs': (219, 12),
}
DELTA_LIMIT = 115
BASE_PINS = {
    'scripts/exclusive_native_acceptance.py': ('100644', 'b98554aafd78c7e7e376f43cb20a4f4686e2acbd', 'bac190d66cb78cf9a380b05b1da89f37044248072360725a58b12fcbb65c619e', 21690, 368),
    'scripts/rc_pretag_integration_admission_profile.py': ('100644', '0f4c449234967c18b26444d39a8cb629d63b75e9', '952a7072a3ffacab1d7562396aad19b6f35fcaf54262e0c2d34f880f42820a15', 148038, 362),
    'scripts/rc_pretag_linux_package_cases.py': ('100644', '7ec8ec753fd6a0d150b95aa2c5800acda25e479a', '61e0b3f30a6effa0821433d1598029c34a11645355db3e4b2e09cf4dbcefbcae', 31054, 444),
    'scripts/rc_pretag_linux_package_inverse.py': ('100644', '162b27125fff31d8b141af9b34249045e162c72f', 'ce542198f9114535333b1e9a2b9329c682f09bd5f1d82b0ec936b6600a828d33', 127614, 213),
    'scripts/聊天授权原生验收v6.py': ('100644', '2ff9a18707269380240f03fc5014e1e66cd21a5f', '7155a5ec158b8986eb28c3d801666b61e2a674caede961bd39c21c4396c80464', 18381, 312),
    'src-tauri/src/app_state.rs': ('100644', '2d89e93f56d75c518d73f423d948e638dd542c4e', 'd2cb84e32cb07f2cee7b128ec54e96c02be74494f5ca77aceb675d8bb9e3410c', 6629, 209),
}
SOURCE_PINS = {
    'scripts/exclusive_native_acceptance.py': ('100644', '71a93b4344afa9ee0b41f6548bb8d5e28a10b06d', '0b9f37e2f26e3eae2f8c638716b8fc0806843617d5688c90c0317e88d9bfc013', 22591, 392),
    'scripts/rc_pretag_integration_admission_profile.py': ('100644', '42244a1087458fe6afa000170e899dc4fd60810b', '7d6a2eba5fe7b70920dfda15826526f12ae84ef2a77bd4e3abdecc60d3266aba', 156636, 362),
    'scripts/rc_pretag_linux_package_cases.py': ('100644', 'f016b8d56885d843a5f6a5f5cfd530c88a73b94d', '8c7b248039fffe0d03282140ea141a9db37d75a416ec88411da10d2607ff547f', 31096, 444),
    'scripts/rc_pretag_linux_package_inverse.py': ('100644', 'a90824de57c52ca2de46ff54b2ff3e4af6f4e57c', '94a08b5026b51b9ecf91d9ee25f4b70b1effc8156691cbf719e8f219be9151a2', 126262, 208),
    'scripts/聊天授权原生验收v6.py': ('100644', '716f59a902599fae600ca698f911712e12ca283c', '370c2f64cd635075050f70bad24fd567c020b1498d168ff9ebeb6ae5aa4e1d97', 18583, 315),
    'src-tauri/src/app_state.rs': ('100644', '84800029b207cb9409e1d36c045ae9f708d0323c', '1a9525031b96d68523eaf791344c90298d23e24594bb3bec36079b6c20065a85', 7201, 219),
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
