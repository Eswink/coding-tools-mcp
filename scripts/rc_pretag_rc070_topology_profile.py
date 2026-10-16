"""Finite #150 topology admission for RC070 packaging tip 05363d94adc8; independent review binds self-bytes."""
import hashlib
import rc_pretag_ownership_profile as o
import rc_pretag_publication_profile as p

M = '05363d94adc89c9eb488282df33ce5205da3a2b4'
M_TREE = '3b5d5ed01eccba4d8714b10d235bedf9f4a3669f'
M_PARENTS = ('cf3cfc6291eeb5ab89976d0068e5c656f5b3a4bc',)
M_RAW = (263, '815d31e5b08bdd485096d56d0c7448909cc08af784df2c946793bae60e08a64f')
BASE = '41984b1de0ca13efab3646aae5041845bc78cfee'
PROFILE = 'scripts/rc_pretag_rc070_topology_profile.py'
MANIFEST = 'scripts/rc_native_probe_source_manifest.json'
NEW = ('scripts/rc_pretag_d1_snapshot_inverse.py', 'scripts/rc_pretag_d1_snapshot_inverse_cases.py')
CAPS = {
    PROFILE: (168, 98),
    'scripts/rc_pretag_archive_budget_profile.py': (183, 7),
    'scripts/rc_pretag_checksum_budget_profile.py': (197, 7),
    'scripts/rc_pretag_ci_repair_profile.py': (139, 6),
    'scripts/rc_pretag_composition_tests.py': (490, 2),
    'scripts/rc_pretag_d1_snapshot_inverse.py': (34, 34),
    'scripts/rc_pretag_d1_snapshot_inverse_cases.py': (44, 44),
    'scripts/rc_pretag_download_budget_profile.py': (219, 7),
    'scripts/rc_pretag_final_admission_profile.py': (255, 42),
    'scripts/rc_pretag_git_budget_profile.py': (207, 7),
    'scripts/rc_pretag_integration_admission_profile.py': (364, 14),
    'scripts/rc_pretag_issue86_root_identity_profile.py': (128, 8),
    'scripts/rc_pretag_reap_safe_profile.py': (113, 6),
    'scripts/rc_pretag_source_observation_profile.py': (188, 20),
    'scripts/rc_pretag_stage_retirement_profile.py': (209, 21),
    'scripts/rc_pretag_staged_bytes_profile.py': (221, 18),
    'scripts/rc_pretag_staging_budget_profile.py': (205, 6),
    'scripts/rc_pretag_supervisor_readiness_profile.py': (183, 14),
    'scripts/rc_pretag_windows_vm_profile.py': (182, 6),
}
DELTA_LIMIT = 367
BASE_PINS = {
    'scripts/rc_pretag_archive_budget_profile.py': ('100644', 'a2c97f9dfd7763cb683f2cbbc58e97c3108d75f8', '4bbfb55ec79d8737fda5483393c8a35275bc9708b53a42e204298ea600fec214', 52260, 184),
    'scripts/rc_pretag_checksum_budget_profile.py': ('100644', '950716133b82623baabf4682004fd7d05a2f941c', '32c27ce7081035e0828b3bef776f1bfbfc232ed43ddf3d518596e61ef9fb0b40', 34692, 198),
    'scripts/rc_pretag_ci_repair_profile.py': ('100644', '2e4c3f78b7bc6237a44b24131faae4cc14bb4ace', '178c29fe58929d4a862e39c0e2e9cd3d43ab838e3d65cb160f787a40621af4b7', 31056, 139),
    'scripts/rc_pretag_composition_tests.py': ('100644', 'a3183e9b20ac12afcbc8aabd310504166cc8ae9c', '77467ccefb25b3cb7208a27c39196acd6a9f21b9a247131de547b94a0aefd988', 36574, 490),
    'scripts/rc_pretag_download_budget_profile.py': ('100644', 'b735d801f14f352363ca761703112eaaead1fecb', '0ccd5d17561b1220152410865592392b38f58cf58664d6d0ef73436f380013ef', 54249, 220),
    'scripts/rc_pretag_final_admission_profile.py': ('100644', '91e8cd4d7f87a7b81863a6767cb0731838b0be5c', 'cceaf9dbdc7123e37f837be15afa5270213ec62bfb5172242f53fa928a5c6129', 48267, 261),
    'scripts/rc_pretag_git_budget_profile.py': ('100644', '9f1399e6454e2c9d0f75cd600ecf8cb9f50861d8', '5af4218d0acebbf6aa36cc4449450daeefaa548c1c78539e8c9e8bdbcff5e7a9', 46752, 208),
    'scripts/rc_pretag_integration_admission_profile.py': ('100644', 'bc85c20c7de97dffe04bef76a702f05ded32a3dc', '5fd82ff2f4818b0fe2235dbdd49604f7e2cebb428a9648c0cdcb832ae2afedb5', 109746, 366),
    'scripts/rc_pretag_issue86_root_identity_profile.py': ('100644', 'b0b2b9b9e7413ae8fdf0bba2c9997b0c1e0da7ac', 'c6f4c7b555dddc2ae00e4833963b7c95b073a80b5cddd3e2e31f9ac9dd31430c', 36633, 126),
    'scripts/rc_pretag_reap_safe_profile.py': ('100644', 'e1157c94f8e6ed2c29d11ac6845ac81f8d71344f', 'c046f25a5f8919ece63476eee99392ac54173a7ba94d1256da4c0491933356aa', 33051, 113),
    'scripts/rc_pretag_source_observation_profile.py': ('100644', '2c5eabd588f893c2bbfaa5d758bf032c55306b42', 'df089a6b1fade2a45ce1e4970827cf4835af853b3f12e4981414e8cf733b424a', 91224, 188),
    'scripts/rc_pretag_stage_retirement_profile.py': ('100644', '134555dc91388fa831589d8ee014f1f92a724983', '2a95664c90755416bf1f637e0537ca4365dbb1663c5404ea1c536c48c8445f4d', 55087, 212),
    'scripts/rc_pretag_staged_bytes_profile.py': ('100644', 'a2a3ba26aa53c5b83c92e27566339fbca15ba345', '434549cee84623f24c9eb3f75efa669ad71d8afc7d7833dd0e0672753c34e915', 51772, 223),
    'scripts/rc_pretag_staging_budget_profile.py': ('100644', 'ea0c4d87541bdd9d066c377417f5e05c51fd6804', '0148cddd2270a6ea984c4fccfffad960dfd51d09bd21f798f17227b1c1074234', 45032, 205),
    'scripts/rc_pretag_supervisor_readiness_profile.py': ('100644', '8d6ea278061f87e04b7a4b51934e3bb7ab5e7c95', '5b4fe041482f59e4e744d68014488ff7996389afea4fb5ae7754e9a580f062b5', 41400, 185),
    'scripts/rc_pretag_windows_vm_profile.py': ('100644', '36a9d28cd9a23e02d70f93f3d3a04b3c7f708535', '2cef3e1410c958b8b4646ab8c6e5c63df2c4906c2b505164a038481bb785a01b', 33801, 182),
}
SOURCE_PINS = {
    'scripts/rc_pretag_archive_budget_profile.py': ('100644', 'a40c0ebd96a42f5902f7a6e27dc41ec7090b5123', 'fada7691ff194208615e25d15427e1529fabaa1072970a858f20fba9b2444797', 57860, 183),
    'scripts/rc_pretag_checksum_budget_profile.py': ('100644', 'd58c7e37cde922d0a81d327bc12caeba206db803', 'd1da6e9f10f2fc41b78fe230a0252cfd48e159019cdc0c7fd77d19c4b90b3620', 37816, 197),
    'scripts/rc_pretag_ci_repair_profile.py': ('100644', '97b53d84cd71696800e8fedba0036d26e00eaac9', 'fe294b340ceafe48d1feab52ce35e475691d79104346f70f5d6b6c485f95513c', 179506, 139),
    'scripts/rc_pretag_composition_tests.py': ('100644', '85ef17d2d346c808ea58c178dd4e88c507365b0c', '0bdac9a41a4b91c7b752d15fa363d3c77b6002b98f0854b3ce0453b99721a556', 36599, 490),
    'scripts/rc_pretag_d1_snapshot_inverse.py': ('100644', 'ac185572d9e1ee26fac563197309695de0582613', 'dbfe8f52d989fc7994d2bfc5555716e6645542a0cffefe9ef29d9216258cb9e4', 2682, 34),
    'scripts/rc_pretag_d1_snapshot_inverse_cases.py': ('100644', '98c5406de5c044bf14321966f51156d12c75af0e', '62eeb148f9180e43749696d298f4e67f0b26afb0334d8730410947030063b89c', 2009, 44),
    'scripts/rc_pretag_download_budget_profile.py': ('100644', 'd7a42c3f2db90fe17341e542b9852b533ff6cb26', 'db633904803870cfbfb486784ff056ba5d34b5e75cad5d5beca8bdb5bac36c4e', 108647, 219),
    'scripts/rc_pretag_final_admission_profile.py': ('100644', 'fa5311f19b4ae9452eaf80bc3ead8697acc385bb', '90ddce5d7d7a2784afd78ff9eb56a1712f31de75bb7499afffede6b33dab9559', 78929, 255),
    'scripts/rc_pretag_git_budget_profile.py': ('100644', 'b88d84560c7566bc8349e41a38f6e0d865a540de', 'ef32e9f9e29213fe0826f5a7eb77625b12b4fca479f9e296637507ef15596111', 88947, 207),
    'scripts/rc_pretag_integration_admission_profile.py': ('100644', '3b3ada6e21d3603bcd76ba729b7092c45e4ed281', '4c0462c323d413c532f333d2071de6b34c1e933747b3206907a9aefcaefe9c72', 131609, 364),
    'scripts/rc_pretag_issue86_root_identity_profile.py': ('100644', 'd775f5bbc5127f187f4bfd18a7780d000d8a4c99', '317a0bcaf881405d918e5df33cc2158581800e579c7be846de4b6a61e2786886', 533205, 128),
    'scripts/rc_pretag_reap_safe_profile.py': ('100644', 'cd23f2cfe98e56d472e27774e1bc7e3c3ceda9db', '9ee255700d6d926e9291681187481040740d32691994720dab076519e7208142', 309876, 113),
    'scripts/rc_pretag_source_observation_profile.py': ('100644', '04709007db1c28b8696f8796594a8161e1cf55e5', '2e0bf288f1d23eb344e0e759a1639d6ca83e4f0aae73f1a7e208c314af8c9f34', 174604, 188),
    'scripts/rc_pretag_stage_retirement_profile.py': ('100644', '8c206ea960ad6ffcf2c50bf46cd01831ea0133de', 'c4f2f56dc9c097f2e1755b0ccb19fafe5d0da9fc03ceee317ec796eb697d931b', 84883, 209),
    'scripts/rc_pretag_staged_bytes_profile.py': ('100644', '1c0bfffaa189b9f6544c309b17a55ff1fa3db0ff', 'a009a67062bbe3c512ca6c4b9ac938b5103cd5d48e291ca36d1906e3fad1b9d2', 64095, 221),
    'scripts/rc_pretag_staging_budget_profile.py': ('100644', 'd44220e4ae6a8fe361c385a03ce9a08ee812146f', 'd8904ad43e16d04fabb8a7cf8ba40e9e927adf37bc9933ed211b3ad5bb8d7fe5', 45578, 205),
    'scripts/rc_pretag_supervisor_readiness_profile.py': ('100644', 'a6e2ee6141ee96f145e70b3b03262778b163e99d', '42b64e7431f1ec709e6d6a7ec954df4edb33a020f9dee53e1e04363c75e399d5', 59857, 183),
    'scripts/rc_pretag_windows_vm_profile.py': ('100644', 'dc1f4232a2984f344bb42818158be587ef94cd3d', '4d63657cdea19e3ab593c6ee89c02464a003f1cfe6142b22c0e4be69753eccd4', 88320, 182),
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
