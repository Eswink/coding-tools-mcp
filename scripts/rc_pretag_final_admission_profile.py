"""Finite FINAL admission source; independent complete-tree review binds this module."""
import rc_pretag_ownership_profile as o
import rc_pretag_publication_profile as p

M = '08bd1c79d3394321578444a2d2722c2bf9e8eb1d'
M_TREE = '6b3a3f98a2a6d24ef5033ca0c1a648f7928182a8'
M_PARENTS = ('c2b5afb2c46318e2c54283f8442d5996e55f0a73', 'c0d04e87de6d00f5d1117dd817c0e16654a6b9ba')
PROFILE = 'scripts/rc_pretag_final_admission_profile.py'
CASES = 'scripts/rc_pretag_final_admission_cases.py'
DISPATCHER = 'scripts/rc_pretag_integration_admission_profile.py'
WORKFLOW = '.github/workflows/issue88-publication-executor.yml'
CAPS = {
    'scripts/rc_publication_admission.py': (300, 230),
    'scripts/rc_publication_github.py': (486, 4),
    'scripts/rc_release_policy.py': (195, 60),
    'scripts/rc_publication_admission_cases.py': (430, 100),
    'scripts/rc_publication_executor_cases.py': (308, 4),
    'scripts/rc_pretag_policy_tests.py': (256, 8),
    'scripts/rc_pretag_integration_admission_profile.py': (350, 6),
    'scripts/rc_pretag_integration_admission_cases.py': (360, 32),
    '.github/workflows/issue88-publication-executor.yml': (105, 36),
    'scripts/rc_publication_final_admission_cases.py': (480, 480),
    'scripts/rc_pretag_final_admission_profile.py': (400, 400),
    'scripts/rc_pretag_final_admission_cases.py': (400, 400),
    'docs/specs/issue88-final-packaging-admission/requirements.md': (45, 45),
    'docs/specs/issue88-final-packaging-admission/design.md': (80, 80),
    'docs/specs/issue88-final-packaging-admission/tasks.md': (60, 60),
}
BASE_PINS = {
    'scripts/rc_publication_admission.py': ('100644', '4d4c9ab80a80c94e7cddf994af7ddc0b42bad251', '412af5d5110b590d719907e305d564769cd5796cbe24c30ea5c6a79c19db2178', 7801, 155),
    'scripts/rc_publication_github.py': ('100644', '8acb81c087751d0e6554144f365053f2074238cb', '1944d7aa4bab79c32747f3722bd07af8f9d801ce887d9597933ffbafa0c20bb6', 23521, 482),
    'scripts/rc_release_policy.py': ('100644', 'a98cb286d1f963d7c8d2f984b64c5017aab4fbc1', '5a4b8c642dd8a654f423c88bff0314fba4b5e1ddfcad3579e4e9ca72d565b876', 13637, 168),
    'scripts/rc_publication_admission_cases.py': ('100644', '2b4dee642d101127e00229658b720a93662b99ad', 'eb1d75cc4984804b39e22a9de5fb245384afd7e6ac507a599427fb34d449ea04', 23556, 386),
    'scripts/rc_publication_executor_cases.py': ('100644', '0e8251b9a49af68ee1a9ff85e2d013233a5c53cb', 'a86752e0fcf69cb9ff11de39e109565f8896e071cfd783ddff56b5006311c782', 16526, 303),
    'scripts/rc_pretag_policy_tests.py': ('100644', 'bf1725b106ea55dcac2f0c70aeddece436fb2681', 'f9df6c3c9fbea03e70b50fc4f889eee3100e9556f2de6d61892a5cb87c0346ce', 15108, 251),
    'scripts/rc_pretag_integration_admission_profile.py': ('100644', '4567d92941bb3bfec3b8af5ad6628fdca75b6238', 'fb09e30494af5770be8e7815ea1ce81ee8e64e601a4fd61b732d7331da1136ad', 76921, 338),
    'scripts/rc_pretag_integration_admission_cases.py': ('100644', 'd074861b9e655cbc38807bd0f38187690e4d0e3c', 'f3bb03dcbeca0a3c68a55879dbefa37f7e038cfcca774852e9f29a36f4ee480d', 22105, 345),
    '.github/workflows/issue88-publication-executor.yml': ('100644', 'd06143c505bf739dfd4336ea97c20b5850d15128', 'ceb14dd7012995f1d3400e1eb7dfc24533b564cd9a039e2592c74b153d036634', 5636, 79),
}
PRIOR_PINS = {
    'scripts/rc_publication_github.py': (('b4d250974e89deeb241f2aa32a998cda17688e34', '62fbe64ffc69c15d0def289f13ff282ed4046fee05a584b20b228f92488f1d90'),),
    'scripts/rc_release_policy.py': (('58b8aa42255c440ee5bdbe46fe67965e5acb1724', 'f63705d96312f1d1b4dd31394ad6c4d450748ce7a65fbb3c90c6b676d0755c9f'),),
    'scripts/rc_publication_executor_cases.py': (('9b3c84e25470a775329a8bb49704b329409a0576', '32d11ddd521fd9a0a4a947b1d5fb506d1a1dd955a45734afda2cf53a40e1e5fc'),),
    'scripts/rc_pretag_policy_tests.py': (('004133bd73c7ebfa243d79ba42a4565e7b945cd5', 'b78d9f65a1256b8ff819f0b2a7832302e835f429cb8d4c0bac9b1a3728a4c5b0'),),
    '.github/workflows/issue88-publication-executor.yml': (('c6cc466d9d2520b668508e6fbd9754f1ac1cc7ef', '850aea3f1d81c00322f8c8ca1adf84a5abddb5c75d916066394f41a521397e4e'),),
}
DELTA_LIMIT = 2000
# BEGIN SEALED SOURCE
SOURCE_PINS = {
    'scripts/rc_publication_admission.py': ('100644', '63015fea8d851d2581c437dfcfe5939dce3d53f1', '8226f363b9b47fc4028504c787206b6a6a862299e58bb42338fa977205c5ecb5', 11419, 217),
    'scripts/rc_publication_github.py': ('100644', 'fdc12ec5dbff05cdf065c14022a28b43aa20e1f6', '4f202e8cf336095ca439da7381f6205663c8790fb7cc6347e3e04861570a8727', 23519, 482),
    'scripts/rc_release_policy.py': ('100644', '6dafa3aa52b66a10657645b2273cfcf33823bb82', '650bc02d8592a9cfdb143945595d39d95c14c1308abf533f2ea6dd61ad85bafa', 14099, 174),
    'scripts/rc_publication_admission_cases.py': ('100644', '654b5dba8f102d401b4830c4095c4043527a97f6', '0c16ec46f837c9b1ed460469d3c98029f6947e2760a9c56f71f8bbee5f06aa12', 23670, 388),
    'scripts/rc_publication_executor_cases.py': ('100644', 'ab5ea441f645d5a4ccedac48dafc8a05a4de670e', 'b1b8d687fbbf782bc332133d2ce875aae2159e4872d729b0be6d6964fd979ef1', 16527, 303),
    'scripts/rc_pretag_policy_tests.py': ('100644', 'af8b29207151abc6881d189ca54f5712931e43f6', '228eff1efd300061450cf555daea7f7229cc3311c66da4cefc489e17381ebf6c', 15178, 252),
    'scripts/rc_pretag_integration_admission_profile.py': ('100644', '278b5e3ba9db531d01a25d3246f1f28eca5cd534', '5ff9ef8204b27f2fcb6942743a9a732646ca2a37dcc13f963a8457c64beb8281', 77243, 344),
    'scripts/rc_pretag_integration_admission_cases.py': ('100644', '7d8d86c8f88b0805ab81726c032628277575bf6a', '3f11d298c6b4fb78cac7281c041ae8a257c84f94509c7a95433cea3209a8965b', 22325, 346),
    '.github/workflows/issue88-publication-executor.yml': ('100644', 'f3cf8b1e3f337204f423ae200e667aaf9d34e3f8', '5fedc956307b75e7d59c3f5aeda153b6e3e64dd618700141862149c3fda37d7a', 6617, 89),
    'scripts/rc_publication_final_admission_cases.py': ('100644', 'efbc5f826985e144c417b3e39de9c172b9a92680', '50d3079509abd4be85e218ccc5dc2967a80a27ed4f41a9c408ecc1b03df71586', 24352, 384),
    'scripts/rc_pretag_final_admission_cases.py': ('100644', 'c169ac26b007550ba817095a0be4cd606ca7f992', 'af06d235bc76fb56293a0f2f11edd915737758c6e5f7decf210ea41890f7bc5a', 25308, 387),
    'docs/specs/issue88-final-packaging-admission/requirements.md': ('100644', '07d7d4c97f3a298dd1e696586c73c06868a70ec0', 'dbd5dfb40a705388620cabe5afbd5fb1320d4fd85ec7f2460d4641b430d830eb', 4233, 31),
    'docs/specs/issue88-final-packaging-admission/design.md': ('100644', 'd225bf04ebd6ad0fbb47a064e4f815392a8aeb4d', '55700ebb6b3820d5b2dd43f65134d83452cee0d7dc60e95ba679f5c22788ae56', 7447, 43),
    'docs/specs/issue88-final-packaging-admission/tasks.md': ('100644', '14ab9570872d56d15f1ebf8fa2dacfad7cc8e63c', '9299956d436d17def7115108039841653dbb64f0a640ebb035b33ff35e942b5a', 4321, 55),
}
FRAGMENTS = {
    'scripts/rc_publication_admission.py': (
        (b'"""Fixed read-only integration/FINAL metadata; publication remains blocked."""\nfrom dataclasses import asdict, dataclass\nimport hashlib\n', b'"""Fixed read-only integration admission; every other publication gate is blocked."""\nfrom dataclasses import asdict, dataclass\nimport hashlib\n'),
        (b"\n\n@dataclass(frozen=True)\nclass _PackagingReport(_AdmissionReport):\n    final_evidence_sha256: str\n\n    def __post_init__(self):\n        super().__post_init__()\n        need(self.final_evidence_sha256 == self.subject.gate_evidence[\n            GATE_IDS.index('final_packaging')], 'final_digest_mismatch')\n\n    @property\n    def rows(self):\n        return tuple((*row, 'passed' if row[0] in ('full_integration', 'final_packaging') else 'unknown')\n                     for row in core._admission(self.subject))\n\n\ndef _source(api, subject, *, final=False):\n    source, invocation = subject.source, subject.runs[0 if final else 1]\n    role = 'final' if final else 'integration'\n    repository = api.get('/')\n    snapshot._repository(repository, source.repository_id)\n", b"\n\ndef _source(api, subject):\n    source, invocation = subject.source, subject.runs[1]\n    repository = api.get('/')\n    snapshot._repository(repository, source.repository_id)\n"),
        (b"    need(type(value) is dict and value.get('ref') == invocation.ref\n         and type(value.get('object')) is dict and value['object'].get('type') == 'commit'\n         and value['object'].get('sha') == source.source_sha, role + '_ref_mismatch')\n    ref = dict(ref=value['ref'], object=dict(type='commit', sha=source.source_sha))\n    commit = api.get('/git/commits/' + source.source_sha)\n    need(type(commit) is dict and commit.get('sha') == source.source_sha\n         and type(commit.get('tree')) is dict and commit['tree'].get('sha') == source.source_tree,\n         role + '_source_mismatch')\n    tree_sha, trees = source.source_tree, []\n    for name, mode, kind in (('.github', '040000', 'tree'), ('workflows', '040000', 'tree'),\n                             (('final-rc-packages.yml' if final else 'dot-rc-integration.yml'), '100644', 'blob')):\n        tree = api.get('/git/trees/' + tree_sha)\n        need(type(tree) is dict and tree.get('sha') == tree_sha and tree.get('truncated') is False\n             and type(tree.get('tree')) is list, role + '_tree_invalid')\n        rows, names = tree['tree'], set()\n        for row in rows:\n            path = row.get('path') if type(row) is dict else None\n            need(type(path) is str and 0 < len(path) <= 256 and '/' not in path\n                 and path not in ('.', '..') and path not in names, role + '_tree_invalid')\n            names.add(path)\n        matches = [row for row in rows if row['path'] == name]\n        need(len(matches) == 1 and matches[0].get('mode') == mode\n             and matches[0].get('type') == kind, role + '_workflow_mismatch')\n        sha = matches[0].get('sha')\n        need(type(sha) is str and re.fullmatch('[a-f0-9]{40}', sha), role + '_tree_invalid')\n        trees.append(tree_sha)\n        tree_sha = sha\n    need(tree_sha == invocation.workflow_blob, role + '_workflow_mismatch')\n    return dict(repository=dict(id=source.repository_id, full_name=source.repository), ref=ref,\n                commit=dict(sha=source.source_sha, tree=source.source_tree), trees=trees,\n", b"    need(type(value) is dict and value.get('ref') == invocation.ref\n         and type(value.get('object')) is dict and value['object'].get('type') == 'commit'\n         and value['object'].get('sha') == source.source_sha, 'integration_ref_mismatch')\n    ref = dict(ref=value['ref'], object=dict(type='commit', sha=source.source_sha))\n    commit = api.get('/git/commits/' + source.source_sha)\n    need(type(commit) is dict and commit.get('sha') == source.source_sha\n         and type(commit.get('tree')) is dict and commit['tree'].get('sha') == source.source_tree,\n         'integration_source_mismatch')\n    tree_sha, trees = source.source_tree, []\n    for name, mode, kind in (('.github', '040000', 'tree'), ('workflows', '040000', 'tree'),\n                             ('dot-rc-integration.yml', '100644', 'blob')):\n        tree = api.get('/git/trees/' + tree_sha)\n        need(type(tree) is dict and tree.get('sha') == tree_sha and tree.get('truncated') is False\n             and type(tree.get('tree')) is list, 'integration_tree_invalid')\n        rows, names = tree['tree'], set()\n        for row in rows:\n            path = row.get('path') if type(row) is dict else None\n            need(type(path) is str and 0 < len(path) <= 256 and '/' not in path\n                 and path not in ('.', '..') and path not in names, 'integration_tree_invalid')\n            names.add(path)\n        matches = [row for row in rows if row['path'] == name]\n        need(len(matches) == 1 and matches[0].get('mode') == mode\n             and matches[0].get('type') == kind, 'integration_workflow_mismatch')\n        sha = matches[0].get('sha')\n        need(type(sha) is str and re.fullmatch('[a-f0-9]{40}', sha), 'integration_tree_invalid')\n        trees.append(tree_sha)\n        tree_sha = sha\n    need(tree_sha == invocation.workflow_blob, 'integration_workflow_mismatch')\n    return dict(repository=dict(id=source.repository_id, full_name=source.repository), ref=ref,\n                commit=dict(sha=source.source_sha, tree=source.source_tree), trees=trees,\n"),
        (b"\n\ndef _evidence(api, subject, *, final=False):\n    index, role = (0, 'final') if final else (1, 'integration')\n    invocation, source = subject.runs[index], subject.source\n    workflow, jobs = (gate.FINAL_WORKFLOW, gate.FINAL_JOBS) if final else (gate.final.WORKFLOW, gate.final.REQUIRED_JOBS)\n    evidence = gate.successful_run(api, workflow, source.source_sha, jobs)\n    need(evidence['workflow'].get('state') == 'active', role + '_workflow_inactive')\n    strict = snapshot._strict_run(evidence, source.repository_id, source.source_sha,\n                                  invocation.run_id, invocation.run_attempt, final=final)\n    _bind(strict, invocation, subject.job_ids[index])\n    exact = api.get(f'/actions/runs/{invocation.run_id}/attempts/{invocation.run_attempt}')\n    need(snapshot._run(exact, source.repository_id) == strict['run'], role + '_attempt_changed')\n    return strict\n\n", b"\n\ndef _evidence(api, subject):\n    invocation, source = subject.runs[1], subject.source\n    evidence = gate.successful_run(api, gate.final.WORKFLOW, source.source_sha, gate.final.REQUIRED_JOBS)\n    need(evidence['workflow'].get('state') == 'active', 'integration_workflow_inactive')\n    strict = snapshot._strict_run(evidence, source.repository_id, source.source_sha,\n                                  invocation.run_id, invocation.run_attempt)\n    _bind(strict, invocation, subject.job_ids[1])\n    exact = api.get(f'/actions/runs/{invocation.run_id}/attempts/{invocation.run_attempt}')\n    need(snapshot._run(exact, source.repository_id) == strict['run'], 'integration_attempt_changed')\n    return strict\n\n"),
        (b'    need(snapshot._run(current, subject.source.repository_id) == evidence[\'run\'], \'integration_run_changed\')\n    need(_source(reads, subject) == source, \'integration_source_changed\')\n    digest = _digest(subject, source, evidence)\n    reads.check()\n    return _AdmissionReport(subject, digest)\n\n\ndef _digest(subject, source, evidence, *, final=False):\n    invocation = subject.runs[0 if final else 1]\n    record = dict(evidence, run=dict(evidence[\'run\']))\n    for key in (\'repository\', \'head_repository\'):\n        record[\'run\'][key] = {name: evidence[\'run\'][key][name] for name in (\'id\', \'full_name\')}\n    canonical = dict(schema=\'rc-final-packaging-v1\' if final else \'rc-full-integration-v1\',\n        gate_id=\'final_packaging\' if final else \'full_integration\',\n        source=asdict(subject.source), invocation=asdict(invocation), source_observation=source, evidence=record)\n    return hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(\',\', \':\'),\n                                     ensure_ascii=True, allow_nan=False).encode(\'utf-8\')).hexdigest()\n\n\ndef authenticate_packaging(api, selection, *, check_active, deadline):\n    """Observe the two fixed roles under one deadline; all remaining gates stay unknown."""\n    import rc_publication_github as wire\n    need(type(api) is wire.GitHub and api.selection is selection, \'invalid_admission_transport\')\n    need(type(selection) is Selection, \'invalid_publication_selection\')\n    selection.__post_init__()\n    subject = selection.subject\n    invocation, final = subject.runs[1], subject.runs[0]\n    need(invocation.event in (\'push\', \'workflow_dispatch\')\n         and invocation.ref.startswith((\'refs/heads/\', \'refs/tags/\'))\n         and (invocation.event != \'push\' or invocation.ref.startswith(\'refs/heads/\')), \'unsupported_integration_ref\')\n    need(final.event == \'push\' and final.run_attempt == 1 and final.ref.startswith(\'refs/heads/\')\n         and snapshot.CANDIDATE_BRANCH.fullmatch(final.ref[11:]) is not None, \'unsupported_final_producer\')\n    for key, verifier in ((\'full_integration\', \'github_full_integration_v1\'),\n                          (\'final_packaging\', \'github_final_packaging_v1\')):\n        need(next(g.verifier for g in GATES if g.gate_id == key) == verifier, \'packaging_policy_mismatch\')\n    need(type(deadline) in (int, float) and math.isfinite(deadline), \'invalid_admission_deadline\')\n    reads = _Reads(api, check_active, min(deadline, time.monotonic() + wire.DEADLINE))\n    reads.check()\n    sources = tuple(_source(reads, subject, final=role) for role in (False, True))\n    observed = snapshot._ObservedAPI(reads, subject.source.repository_id)\n    evidence = tuple(_evidence(observed, subject, final=role) for role in (False, True))\n    for role, expected in zip((False, True), evidence):\n        need(_evidence(observed, subject, final=role) == expected, \'packaging_evidence_changed\')\n    for expected in evidence:\n        latest = gate.latest_run(observed, expected[\'workflow\'], subject.source.source_sha)\n        need(snapshot._run(latest, subject.source.repository_id) == expected[\'run\'], \'packaging_run_changed\')\n        current = observed.get(f"/actions/runs/{expected[\'run\'][\'id\']}")\n        need(snapshot._run(current, subject.source.repository_id) == expected[\'run\'], \'packaging_run_changed\')\n    for role, expected in zip((False, True), sources):\n        need(_source(reads, subject, final=role) == expected, \'packaging_source_changed\')\n    digests = tuple(_digest(subject, source, record, final=role)\n                    for role, source, record in zip((False, True), sources, evidence))\n    report = _PackagingReport(subject, *digests)\n    reads.check()\n    return report\n', b"    need(snapshot._run(current, subject.source.repository_id) == evidence['run'], 'integration_run_changed')\n    need(_source(reads, subject) == source, 'integration_source_changed')\n    record = dict(evidence, run=dict(evidence['run']))\n    for key in ('repository', 'head_repository'):\n        record['run'][key] = {name: evidence['run'][key][name] for name in ('id', 'full_name')}\n    canonical = dict(schema='rc-full-integration-v1', gate_id='full_integration',\n        source=asdict(subject.source), invocation=asdict(invocation), source_observation=source, evidence=record)\n    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(',', ':'),\n                                     ensure_ascii=True, allow_nan=False).encode('utf-8')).hexdigest()\n    reads.check()\n    return _AdmissionReport(subject, digest)\n"),
    ),
    'scripts/rc_publication_github.py': (
        (b"def _authenticate(selection, api, *, check_active, deadline):\n    try:\n        report = admission.authenticate_packaging(api, selection, check_active=check_active, deadline=deadline)\n    except admission._Interrupted as error:\n        raise WireFailure(error.code, 'none') from None\n", b"def _authenticate(selection, api, *, check_active, deadline):\n    try:\n        report = admission.authenticate_integration(api, selection, check_active=check_active, deadline=deadline)\n    except admission._Interrupted as error:\n        raise WireFailure(error.code, 'none') from None\n"),
    ),
    'scripts/rc_release_policy.py': (
        (b'"""Fixed evidence requirements; integration and FINAL have read-only metadata verifiers."""\nfrom dataclasses import dataclass\n\n', b'"""Fixed evidence requirements; only full_integration has a live read-only verifier."""\nfrom dataclasses import dataclass\n\n'),
        (b"    ROOT + '/actions/runs/{run_id}/attempts/{run_attempt}',\n    ROOT + '/actions/runs/{run_id}/attempts/{run_attempt}/jobs')\nFINAL_READS = tuple(path.replace('dot-rc-integration.yml', 'final-rc-packages.yml')\n                    for path in INTEGRATION_READS)\nREVIEW_READS = (ROOT + '/pulls/36', ROOT + '/pulls/36/reviews',\n                ROOT + '/pulls/36/reviews/{review_id}', ROOT + '/pulls/36/commits')\n", b"    ROOT + '/actions/runs/{run_id}/attempts/{run_attempt}',\n    ROOT + '/actions/runs/{run_id}/attempts/{run_attempt}/jobs')\nREVIEW_READS = (ROOT + '/pulls/36', ROOT + '/pulls/36/reviews',\n                ROOT + '/pulls/36/reviews/{review_id}', ROOT + '/pulls/36/commits')\n"),
        (b"            sequence(value, str, 16)\n        require(all(p in PERMISSIONS for p in self.permissions), 'invalid_policy_permission')\n        require(self.verifier == {'full_integration': 'github_full_integration_v1',\n            'final_packaging': 'github_final_packaging_v1'}.get(self.gate_id, 'unimplemented'),\n            'unsupported_policy_verifier')\n\n\n", b"            sequence(value, str, 16)\n        require(all(p in PERMISSIONS for p in self.permissions), 'invalid_policy_permission')\n        require(self.verifier == ('github_full_integration_v1' if self.gate_id == 'full_integration'\n                                  else 'unimplemented'), 'unsupported_policy_verifier')\n\n\n"),
        (b"    completeness = 'newest same-source run across all statuses; exact current-attempt jobs; bounded complete lists'\n    identity = 'repository ID/name, source SHA/tree, workflow, run/current attempt/job and API ZIP digest/size'\n    if key in ('full_integration', 'final_packaging'):\n        endpoints = INTEGRATION_READS if key == 'full_integration' else FINAL_READS\n        visibility = 'authenticated same-repository source/workflow/run/attempt/job metadata only'\n        identity = 'repository ID/name, source SHA/tree, workflow blob/ref, newest run/current attempt and exact jobs'\n        if key == 'final_packaging':\n            identity += '; candidate branch push, first attempt, thirteen successful selected jobs'\n    if family == 'source':\n        endpoints, permissions = SOURCE_READS, ('contents:read',)\n", b"    completeness = 'newest same-source run across all statuses; exact current-attempt jobs; bounded complete lists'\n    identity = 'repository ID/name, source SHA/tree, workflow, run/current attempt/job and API ZIP digest/size'\n    if key == 'full_integration':\n        endpoints = INTEGRATION_READS\n        visibility = 'authenticated same-repository source/workflow/run/attempt/job metadata only'\n        identity = 'repository ID/name, source SHA/tree, workflow blob/ref, newest run/current attempt and exact jobs'\n    if family == 'source':\n        endpoints, permissions = SOURCE_READS, ('contents:read',)\n"),
        (b"    return GateRequirement(key, scope, ledger, endpoints, contract, permissions, visibility, identity,\n        completeness, 'missing/denied/truncated/stale/failed/skipped/unknown => blocked; no older-green fallback',\n        ('repeat complete source/workflow/run/current attempt/job observations; non-atomic' if key in ('full_integration', 'final_packaging')\n         else 'repeat source/run/current attempt/job/artifact/visibility observations at every admission fence; non-atomic'),\n        verifier={'full_integration': 'github_full_integration_v1',\n                  'final_packaging': 'github_final_packaging_v1'}.get(key, 'unimplemented'))\n\n\n", b"    return GateRequirement(key, scope, ledger, endpoints, contract, permissions, visibility, identity,\n        completeness, 'missing/denied/truncated/stale/failed/skipped/unknown => blocked; no older-green fallback',\n        ('repeat complete source/workflow/run/current attempt/job observations; non-atomic' if key == 'full_integration'\n         else 'repeat source/run/current attempt/job/artifact/visibility observations at every admission fence; non-atomic'),\n        verifier='github_full_integration_v1' if key == 'full_integration' else 'unimplemented')\n\n\n"),
    ),
    'scripts/rc_publication_admission_cases.py': (
        (b'                               for p in self.sources + one*2 + [self.runs, self.current] + self.sources]\n        self.route = self.integration_route\n        from rc_publication_final_admission_cases import add_final\n        add_final(self)\n\n    def reference_digest(self):\n', b'                               for p in self.sources + one*2 + [self.runs, self.current] + self.sources]\n        self.route = self.integration_route\n\n    def reference_digest(self):\n'),
        (b"        with IntegrationTLS() as f:\n            self.blocked(f)\n            self.assertEqual([r[1] for r in f.requests], f.packaging_paths)\n            self.assertEqual([g.gate_id for g in GATES if g.verifier != 'unimplemented'], ['full_integration', 'final_packaging'])\n            with self.assertRaises(wire.WireFailure): wire._remote_constraint(f.subject)\n            with self.assertRaises(wire.WireFailure): wire._authenticated_latest_absence(f.selection)\n", b"        with IntegrationTLS() as f:\n            self.blocked(f)\n            self.assertEqual([r[1] for r in f.requests], f.expected_paths)\n            self.assertEqual([g.gate_id for g in GATES if g.verifier != 'unimplemented'], ['full_integration'])\n            with self.assertRaises(wire.WireFailure): wire._remote_constraint(f.subject)\n            with self.assertRaises(wire.WireFailure): wire._authenticated_latest_absence(f.selection)\n"),
        (b"                self.assertEqual((error.exception.code, session.outcome), ('fence_blocked', 'blocked_no_effect'))\n                self.assertIsNone(session.transition); stage.assert_not_called()\n            self.assertEqual([r[1] for r in f.requests], f.packaging_paths)\n            self.assertTrue(all(r[0] == 'GET' and not r[3] for r in f.requests))\n\n", b"                self.assertEqual((error.exception.code, session.outcome), ('fence_blocked', 'blocked_no_effect'))\n                self.assertIsNone(session.transition); stage.assert_not_called()\n            self.assertEqual([r[1] for r in f.requests], f.expected_paths)\n            self.assertTrue(all(r[0] == 'GET' and not r[3] for r in f.requests))\n\n"),
        (b"                    self.assertEqual((error.exception.code, error.exception.effect), ('fence_blocked', 'none'))\n                    authorize.assert_not_called()\n                self.assertEqual([r[1] for r in f.requests[before:]], f.packaging_paths)\n                self.assertTrue(all(r[0] == 'GET' and not r[3] for r in f.requests))\n\n", b"                    self.assertEqual((error.exception.code, error.exception.effect), ('fence_blocked', 'none'))\n                    authorize.assert_not_called()\n                self.assertEqual([r[1] for r in f.requests[before:]], f.expected_paths)\n                self.assertTrue(all(r[0] == 'GET' and not r[3] for r in f.requests))\n\n"),
        (b"            f.api.get = lambda *args, **kwargs: self.fail('caller GET invoked')\n            self.blocked(f)\n            self.assertEqual([r[1] for r in f.requests], f.packaging_paths)\n            class Foreign(wire.GitHub): pass\n            with self.assertRaises(ConsumerError):\n", b"            f.api.get = lambda *args, **kwargs: self.fail('caller GET invoked')\n            self.blocked(f)\n            self.assertEqual([r[1] for r in f.requests], f.expected_paths)\n            class Foreign(wire.GitHub): pass\n            with self.assertRaises(ConsumerError):\n"),
    ),
    'scripts/rc_publication_executor_cases.py': (
        (b"                    self.assertIsNone(session.transition)\n                    stage.assert_not_called()\n                    self.assertEqual([r[1] for r in tls.requests], [] if patched else tls.packaging_paths)\n                    self.assertTrue(all(r[0] == 'GET' and r[3] == b'' for r in tls.requests))\n                    self.assertEqual(self.mutations(tls), [])\n", b"                    self.assertIsNone(session.transition)\n                    stage.assert_not_called()\n                    self.assertEqual([r[1] for r in tls.requests], [] if patched else tls.expected_paths)\n                    self.assertTrue(all(r[0] == 'GET' and r[3] == b'' for r in tls.requests))\n                    self.assertEqual(self.mutations(tls), [])\n"),
    ),
    'scripts/rc_pretag_policy_tests.py': (
        (b"            self.assertTrue(gate.visibility and gate.identity_binding and gate.completeness)\n            self.assertTrue(gate.failure_semantics and gate.freshness)\n            expected = {'full_integration': 'github_full_integration_v1',\n                        'final_packaging': 'github_final_packaging_v1'}.get(gate.gate_id, 'unimplemented')\n            self.assertEqual(gate.verifier, expected)\n            self.assertLessEqual(set(gate.permissions), set(PERMISSIONS))\n", b"            self.assertTrue(gate.visibility and gate.identity_binding and gate.completeness)\n            self.assertTrue(gate.failure_semantics and gate.freshness)\n            expected = 'github_full_integration_v1' if gate.gate_id == 'full_integration' else 'unimplemented'\n            self.assertEqual(gate.verifier, expected)\n            self.assertLessEqual(set(gate.permissions), set(PERMISSIONS))\n"),
    ),
    'scripts/rc_pretag_integration_admission_profile.py': (
        (b'    """Reverse only sealed new bytes; historical passthrough is a finite pin list."""\n    assert type(path) is str and type(current) is bytes, \'integration inverse input\'\n    from rc_pretag_final_admission_profile import normalize as final_bytes\n    current = final_bytes(path, current)\n    if path not in BASE_PINS:\n        return current\n', b'    """Reverse only sealed new bytes; historical passthrough is a finite pin list."""\n    assert type(path) is str and type(current) is bytes, \'integration inverse input\'\n    if path not in BASE_PINS:\n        return current\n'),
        (b'    """Only topology mismatch delegates; selected and historical content errors escape."""\n    ref = o._commit(ref, root, git)\n    import rc_pretag_final_admission_profile as final\n    selected = final.select(ref, root, git, entries, historical, release, release_tree, documents)\n    if selected is not None:\n        return selected\n    try:\n        kind, tip, source = topology(ref, root, git, release)\n', b'    """Only topology mismatch delegates; selected and historical content errors escape."""\n    ref = o._commit(ref, root, git)\n    try:\n        kind, tip, source = topology(ref, root, git, release)\n'),
    ),
    'scripts/rc_pretag_integration_admission_cases.py': (
        (b'import rc_pretag_publisher_executor_cases as old_cases\nimport rc_pretag_integration_admission_profile as x\nfrom rc_pretag_final_admission_profile import normalize as final_bytes\n\n\n', b'import rc_pretag_publisher_executor_cases as old_cases\nimport rc_pretag_integration_admission_profile as x\n\n\n'),
        (b"    def setUp(self):\n        self.original = c._entries(x.B, self.repo)\n        self.good = self.original | {path: ('100644', 'blob', self.blob(final_bytes(path, (c.ROOT / path).read_bytes()))) for path in x.CAPS}\n        self.pure = self.commit([x.B], self.good)\n        self.feature = self.commit([x.B, self.pure], self.good)\n", b"    def setUp(self):\n        self.original = c._entries(x.B, self.repo)\n        self.good = self.original | {path: ('100644', 'blob', self.blob((c.ROOT / path).read_bytes())) for path in x.CAPS}\n        self.pure = self.commit([x.B], self.good)\n        self.feature = self.commit([x.B, self.pure], self.good)\n"),
        (b"        self.assertEqual(x.SOURCE_PINS.keys(), x.CAPS.keys() - {x.PROFILE})\n        for path, row in x.SOURCE_PINS.items():\n            data = final_bytes(path, (c.ROOT / path).read_bytes())\n            self.assertEqual(row, ('100644', *o.pin(data), len(data), len(data.splitlines())))\n            for index, value in enumerate(('100755', '0' * 40, '0' * 64, row[3] + 1, row[4] + 1)):\n", b"        self.assertEqual(x.SOURCE_PINS.keys(), x.CAPS.keys() - {x.PROFILE})\n        for path, row in x.SOURCE_PINS.items():\n            data = (c.ROOT / path).read_bytes()\n            self.assertEqual(row, ('100644', *o.pin(data), len(data), len(data.splitlines())))\n            for index, value in enumerate(('100755', '0' * 40, '0' * 64, row[3] + 1, row[4] + 1)):\n"),
        (b"    def test_individual_and_total_budgets_fail_closed(self):\n        self.assertEqual((x.DELTA_LIMIT, sum(cap[1] for cap in x.CAPS.values())), (2300, 2132))\n        data = {path: final_bytes(path, (c.ROOT / path).read_bytes()) for path in x.CAPS}\n        def budgets(git=c._git):\n            return p.authenticated._budgets(self.pure, x.B, self.repo, git, data, x.CAPS, x.DELTA_LIMIT, 'integration_delta_budget')\n", b"    def test_individual_and_total_budgets_fail_closed(self):\n        self.assertEqual((x.DELTA_LIMIT, sum(cap[1] for cap in x.CAPS.values())), (2300, 2132))\n        data = {path: (c.ROOT / path).read_bytes() for path in x.CAPS}\n        def budgets(git=c._git):\n            return p.authenticated._budgets(self.pure, x.B, self.repo, git, data, x.CAPS, x.DELTA_LIMIT, 'integration_delta_budget')\n"),
        (b"    def test_missing_duplicate_outside_and_binary_inverse_edits_reject(self):\n        for path, fragments in x.FRAGMENTS.items():\n            current = final_bytes(path, (c.ROOT / path).read_bytes())\n            altered = [current + b'# outside\\n', b'\\xff']\n            for before, _ in fragments:\n", b"    def test_missing_duplicate_outside_and_binary_inverse_edits_reject(self):\n        for path, fragments in x.FRAGMENTS.items():\n            current = (c.ROOT / path).read_bytes()\n            altered = [current + b'# outside\\n', b'\\xff']\n            for before, _ in fragments:\n"),
        (b"        for module in {item.split('.', 1)[0] for item in original}:\n            path = 'scripts/' + module + '.py'\n            current, frozen = final_bytes(path, (c.ROOT / path).read_bytes()), self.frozen(path)\n            self.assertEqual(x.normalize(path, current), frozen, path)\n            methods = lambda data: {node.name: node for node in ast.walk(ast.parse(data)) if isinstance(node, ast.FunctionDef)}\n", b"        for module in {item.split('.', 1)[0] for item in original}:\n            path = 'scripts/' + module + '.py'\n            current, frozen = (c.ROOT / path).read_bytes(), self.frozen(path)\n            self.assertEqual(x.normalize(path, current), frozen, path)\n            methods = lambda data: {node.name: node for node in ast.walk(ast.parse(data)) if isinstance(node, ast.FunctionDef)}\n"),
        (b'\n    def test_readonly_workflow_and_held_sources_remain_bounded(self):\n        text = final_bytes(x.WORKFLOW, (c.ROOT / x.WORKFLOW).read_bytes()).decode()\n        for fragment in ("on:\\n  push:\\n    branches: [\'ci/issue88-publisher-executor-*\']", \'permissions:\\n  contents: read\',\n                "os: [ubuntu-22.04, ubuntu-24.04]", "python-version: \'3.12\'", \'fetch-depth: 0, persist-credentials: false\',\n', b'\n    def test_readonly_workflow_and_held_sources_remain_bounded(self):\n        text = (c.ROOT / x.WORKFLOW).read_text()\n        for fragment in ("on:\\n  push:\\n    branches: [\'ci/issue88-publisher-executor-*\']", \'permissions:\\n  contents: read\',\n                "os: [ubuntu-22.04, ubuntu-24.04]", "python-version: \'3.12\'", \'fetch-depth: 0, persist-credentials: false\',\n'),
        (b"        for path in ('scripts/rc_release_eligibility.py', 'scripts/rc_publication_contract.py', 'scripts/rc_publication_stage.py',\n                'scripts/rc_consumer_io.py', 'scripts/rc_artifact_consumer.py', 'src-tauri/src/workspace_snapshots/filesystem.rs'):\n            self.assertEqual(final_bytes(path, (c.ROOT / path).read_bytes()), self.frozen(path), path)\n        self.assertTrue(all(self.good[path] == value for path, value in self.original.items() if path not in x.CAPS))\n\n", b"        for path in ('scripts/rc_release_eligibility.py', 'scripts/rc_publication_contract.py', 'scripts/rc_publication_stage.py',\n                'scripts/rc_consumer_io.py', 'scripts/rc_artifact_consumer.py', 'src-tauri/src/workspace_snapshots/filesystem.rs'):\n            self.assertEqual((c.ROOT / path).read_bytes(), self.frozen(path), path)\n        self.assertTrue(all(self.good[path] == value for path, value in self.original.items() if path not in x.CAPS))\n\n"),
    ),
    '.github/workflows/issue88-publication-executor.yml': (
        (b"      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065\n        with: {python-version: '3.12'}\n      - name: Admit exact source and execute the frozen one hundred twenty cases\n        shell: python\n        run: |\n", b"      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065\n        with: {python-version: '3.12'}\n      - name: Admit exact source and execute the frozen eighty-four cases\n        shell: python\n        run: |\n"),
        (b"              import rc_pretag_composition_tests as c\n              import rc_pretag_publisher_executor_cases as x\n              import rc_pretag_final_admission_profile as profile\n              import rc_pretag_integration_admission_cases as admission\n              import rc_pretag_final_admission_cases as final_admission\n              git = lambda *args: c._git(*args).decode().strip()\n              assert sys.version_info[:2] == (3, 12) and platform.python_implementation() == 'CPython'\n", b"              import rc_pretag_composition_tests as c\n              import rc_pretag_publisher_executor_cases as x\n              import rc_pretag_integration_admission_profile as profile\n              import rc_pretag_integration_admission_cases as admission\n              git = lambda *args: c._git(*args).decode().strip()\n              assert sys.version_info[:2] == (3, 12) and platform.python_implementation() == 'CPython'\n"),
        (b"              sha, tree = git('rev-parse', 'HEAD'), git('rev-parse', 'HEAD^{tree}')\n              parents = git('show', '-s', '--format=%P', 'HEAD').split()\n              assert sha == os.environ['GITHUB_SHA'] and parents == [profile.M]\n              expected = c.publication.selected_profile(sha, c.ROOT, c._git, c._entries, c._feature_profile, c.RELEASE, c.RELEASE_TREE, c.RELEASE_DOCS)\n              def checked():\n", b"              sha, tree = git('rev-parse', 'HEAD'), git('rev-parse', 'HEAD^{tree}')\n              parents = git('show', '-s', '--format=%P', 'HEAD').split()\n              assert sha == os.environ['GITHUB_SHA'] and parents == [profile.B]\n              expected = c.publication.selected_profile(sha, c.ROOT, c._git, c._entries, c._feature_profile, c.RELEASE, c.RELEASE_TREE, c.RELEASE_DOCS)\n              def checked():\n"),
        (b"              (evidence / 'admission-inventory.json').write_text(json.dumps(receipt, indent=2) + '\\n', encoding='utf-8')\n              assert admission.execution_valid(loaded, result)\n              names = final_admission.inventory()\n              suite = unittest.defaultTestLoader.loadTestsFromNames(names)\n              loaded = [test.id() for test in c._flatten(suite)]\n              with (evidence / 'final-admission-cases.log').open('w', encoding='utf-8') as output:\n                  result = unittest.TextTestRunner(stream=output, verbosity=2, resultclass=c.InventoryResult).run(suite)\n              receipt = {'loaded_ids': loaded, 'executed_ids': result.executed_ids, 'tests_run': result.testsRun,\n                         'skipped': result.skipped, 'expected_failures': result.expectedFailures, 'unexpected_successes': result.unexpectedSuccesses, 'successful': result.wasSuccessful()}\n              (evidence / 'final-admission-inventory.json').write_text(json.dumps(receipt, indent=2) + '\\n', encoding='utf-8')\n              assert final_admission.execution_valid(loaded, result)\n              assert checked() == before and git('rev-parse', 'HEAD') == sha and git('rev-parse', 'HEAD^{tree}') == tree\n              (evidence / 'source-after.json').write_text(json.dumps(binding | {'source_unchanged': True}, indent=2) + '\\n', encoding='utf-8')\n", b"              (evidence / 'admission-inventory.json').write_text(json.dumps(receipt, indent=2) + '\\n', encoding='utf-8')\n              assert admission.execution_valid(loaded, result)\n              assert checked() == before and git('rev-parse', 'HEAD') == sha and git('rev-parse', 'HEAD^{tree}') == tree\n              (evidence / 'source-after.json').write_text(json.dumps(binding | {'source_unchanged': True}, indent=2) + '\\n', encoding='utf-8')\n"),
    ),
}
# END SEALED SOURCE
DISPATCH = (
    b'    import rc_pretag_final_admission_profile as final\n'
    b'    selected = final.select(ref, root, git, entries, historical, release, release_tree, documents)\n'
    b'    if selected is not None:\n'
    b'        return selected\n'
)
NORMALIZE = (
    b'    from rc_pretag_final_admission_profile import normalize as final_bytes\n'
    b'    current = final_bytes(path, current)\n'
)
NEW_CASES = {
    'rc_publication_final_admission_cases.FinalAdmissionCases': (
        'test_exact_thirteen_jobs_returns_two_gate_blocked_report',
        'test_both_canonical_digests_and_incidental_metadata',
        'test_repository_source_and_selected_ref_identities_reject',
        'test_final_candidate_push_first_attempt_required',
        'test_fixed_active_final_workflow_blob_and_path_required',
        'test_exact_selected_final_run_attempt_job_ids_required',
        'test_thirteen_job_inventory_status_and_times_reject',
        'test_newer_unsuccessful_final_never_falls_back',
        'test_complete_paginated_final_selection',
        'test_malformed_duplicate_truncated_and_capped_lists_reject',
        'test_current_and_attempt_drift_reject',
        'test_final_job_fields_drift_reject',
        'test_final_source_ref_workflow_reobserve_drift_reject',
        'test_late_newer_final_blocks_each_closing_pass',
        'test_integration_changes_during_final_are_rejected',
        'test_final_metadata_denial_absence_redirect_and_nonjson_reject',
        'test_final_metadata_duplicate_and_bounds_reject',
        'test_cancellation_entering_and_during_final_returns_no_report',
        'test_caller_deadline_covers_both_gates',
        'test_internal_deadline_is_clamped_once',
        'test_entry_and_direct_sinks_remain_effect_free',
        'test_legacy_integration_negative_endpoints_are_reached',
        'test_fresh_reobservation_and_caller_claims_confer_no_authority',
        'test_distinct_supported_integration_ref_and_final_branch',
    ),
    'rc_pretag_final_admission_cases.FinalAdmissionCompositionCases': (
        'test_exact_m_identity_and_fresh_historical_validation',
        'test_ordered_d_i_j_and_exact_four_document_overlay',
        'test_wrong_repeated_nested_correction_and_same_tree_parents_reject',
        'test_all_paths_modes_pins_and_entry_counts_are_exact',
        'test_individual_and_total_budgets_fail_closed',
        'test_exact_dispatch_and_legacy_inverses_recover_complete_m_bytes',
        'test_missing_duplicate_outside_and_binary_inverse_edits_reject',
        'test_selected_historical_and_release_content_errors_are_terminal',
        'test_actual_candidate_validation_is_never_cached',
        'test_original1268_strict303_ids_and_legacy_assertions_are_preserved',
        'test_readonly_workflow_and_held_sources_remain_bounded',
        'test_new36_inventory_and_exceptional_outcomes_reject',
    ),
}
CLASS = 'rc_pretag_final_admission_cases.FinalAdmissionCompositionCases'
NAMES = NEW_CASES[CLASS]
DIGEST = 'd8b43ffb2a0e1168285244bc11b85bb56cc41d357900cd29ead095021dc10b9a'


def normalize(path, current):
    """Reverse only sealed new bytes; historical passthrough is a finite pin list."""
    assert type(path) is str and type(current) is bytes, 'final inverse input'
    from rc_pretag_download_budget_profile import normalize as download_bytes
    current = download_bytes(path, current)
    if path not in BASE_PINS:
        return current
    identity = o.pin(current)
    baseline = BASE_PINS[path]
    if identity == baseline[1:3] or identity in PRIOR_PINS.get(path, ()):
        return current
    row = SOURCE_PINS[path]
    assert (identity, len(current), len(current.splitlines())) == (row[1:3], row[3], row[4]), path
    restored = current
    for before, after in reversed(FRAGMENTS[path]):
        assert before and restored.count(before) == 1, 'final fragment missing or duplicated'
        restored = restored.replace(before, after, 1)
    assert (o.pin(restored), len(restored), len(restored.splitlines())) == (
        baseline[1:3], baseline[3], baseline[4]), 'complete final M inverse'
    return restored


def topology(ref, root, git, release):
    """Only D[M], I[M,D], J[R,I]; no correction chains or ancestry inference."""
    if release != p.R:
        raise o.TopologyError('final_release_anchor')
    parents = o._parents(ref, root, git)
    if parents == [M]:
        kind, tip, source = 'nonrelease', ref, ref
    elif len(parents) == 2 and parents[0] == M:
        kind, tip, source = 'nonrelease', ref, parents[1]
    elif len(parents) == 2 and parents[0] == p.R:
        kind, tip = 'release', parents[1]
        feature_parents = o._parents(tip, root, git)
        if len(feature_parents) != 2 or feature_parents[0] != M:
            raise o.TopologyError('final_feature_parents')
        source = feature_parents[1]
    else:
        raise o.TopologyError('final_candidate_parents')
    if o._parents(source, root, git) != [M]:
        raise o.TopologyError('final_candidate_parent')
    return kind, tip, source


def content(ref, root, git, entries, historical, release, release_tree, documents):
    """Fresh immutable M admission, exact candidate pins and complete reviewed delta."""
    assert (release, release_tree, documents) == (p.R, p.R_TREE, p.R_DOCUMENTS)
    assert tuple(o._parents(M, root, git)) == M_PARENTS, 'final M parents'
    assert git('rev-parse', M + '^{tree}', root=root).decode().strip() == M_TREE, 'final M tree'
    baseline = p.selected_profile(M, root, git, entries, historical, release, release_tree, documents)
    assert baseline == entries(M, root) and len(baseline) == 1752
    actual, paths = entries(ref, root), CAPS.keys()
    assert len(paths) == 15 and SOURCE_PINS.keys() == paths - {PROFILE}
    assert baseline.keys() & paths == BASE_PINS.keys() and len(BASE_PINS) == 9
    assert FRAGMENTS.keys() == BASE_PINS.keys() and PRIOR_PINS.keys() <= BASE_PINS.keys()
    assert actual.keys() == baseline.keys() | paths and len(actual) == 1758
    assert {path for path in actual if actual[path] != baseline.get(path)} == paths
    assert all(actual[path] == value for path, value in baseline.items() if path not in paths)
    assert all(actual[path][:2] == ('100644', 'blob') for path in paths)
    assert all(actual[path] == (row[0], 'blob', row[1]) for path, row in SOURCE_PINS.items())
    data = {path: git('cat-file', 'blob', actual[path][2], root=root) for path in paths}
    for path, (mode, blob, digest, size, count) in SOURCE_PINS.items():
        assert mode == '100644' and o.pin(data[path]) == (blob, digest), path
        assert (len(data[path]), len(data[path].splitlines())) == (size, count), path
    for path, row in BASE_PINS.items():
        assert baseline[path] == (row[0], 'blob', row[1]), path
        assert normalize(path, data[path]) == git('cat-file', 'blob', baseline[path][2], root=root), path
    p.authenticated._budgets(ref, M, root, git, data, CAPS, DELTA_LIMIT, 'final_delta_budget')
    return actual


def select(ref, root, git, entries, historical, release, release_tree, documents):
    """Only topology mismatch delegates; selected and historical content errors escape."""
    ref = o._commit(ref, root, git)
    import rc_pretag_download_budget_profile as download
    selected = download.select(ref, root, git, entries, historical, release, release_tree, documents)
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
