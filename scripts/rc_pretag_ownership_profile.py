"""Issue111 test-only reviewed M overlay and finite topology; inert on import."""
import ast
import hashlib
import subprocess

M = '5a270a2ef659fb28500c6541f280849d914d25b9'
M_TREE = 'ddb51315a6dd9bbdcdf4d8fc5a06bdf4d9ba862f'
IO = 'scripts/rc_consumer_io.py'
PROOF = 'scripts/rc_consumer_default_worker_proof_tests.py'
FIXTURE = 'scripts/rc_consumer_c_93c2ad95_io.txt'
CHECKS = '.github/workflows/rc-pretag-evidence-checks.yml'
CAPS = {IO: (400, 120), 'scripts/rc_consumer_io_ownership_tests.py': (490, 490),
    PROOF: (500, 20), 'scripts/rc_consumer_proof_fixtures.py': (120, 120), FIXTURE: (360, 360),
    'scripts/rc_pretag_composition_tests.py': (500, 120),
    'scripts/rc_pretag_ownership_profile.py': (220, 220),
    'scripts/rc_pretag_ownership_tests.py': (300, 300), CHECKS: (90, 20),
    **{'docs/specs/rc-consumer-close-ownership/' + name + '.md': (100, 100)
       for name in ('requirements', 'design', 'tasks')}}
DELTA_LIMIT = 2200
OLD_PINS = {
    IO: ('40bb2fd647a09019884a1f77e3d4515805751ca1', '3856af4ab573a91838ca2e06bb224ac983c8200a29b34f8a6a6c2bc9619b8de9'),
    PROOF: ('f45fee4efd895bdadc7b5efe1a10379765ed2caf', 'df21b751a5415384b02be03ef388e25450201c5911622d2dc2b8f8b220a16f8f'),
}
# Fixed reviewed values, never inferred from the candidate being checked.
NEW_PINS = {IO: ('2719bd8cb0ed3c3a9b149ca5b89832325f5aac52', '4dffc2c0773f107b7abdc6e0970516b8e793826babd9696ac258768b5de00459'), PROOF: ('bcef44e5e047045f6c5fc447d98c020016a0bb1a', '50bcc0421def780a8b119ce709052962ca2e87eb2d87bb48dfed1b5ea1bbee53'),
    'scripts/rc_consumer_proof_fixtures.py': ('ee7f3f7a70fcbe274665bcc71fe66c371ddaa89a', '11e678c770a7ca70fcfcfd8fb920671ac8dd396e716854d5139635830d33ff21'),
    FIXTURE: OLD_PINS[IO], CHECKS: ('a88058a7142ca2d5890e91e9926c66e40240c483', '00565b5a5b5427559c831c820a29971ff58417e6a5d75a3f2095bd9adf3c84ca')}
FILTERS = (IO, 'scripts/rc_consumer_io_ownership_tests.py', PROOF,
    'scripts/rc_consumer_proof_fixtures.py', FIXTURE, 'docs/specs/rc-consumer-close-ownership/**')
BRANCH = 'feat/rc-final-artifact-consumer-io-ownership-m5a270a2'


def pin(data):
    return (hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest(),
            hashlib.sha256(data).hexdigest())


class TopologyError(AssertionError):
    """Parent grammar failed before any candidate content/equality validation."""


def _commit(ref, root, git):
    try:
        return git('rev-parse', '--verify', ref + '^{commit}', root=root).decode().strip()
    except subprocess.CalledProcessError as error:
        raise TopologyError('missing_commit') from error


def _parents(ref, root, git):
    try:
        return git('show', '-s', '--format=%P', ref, root=root).decode().split()
    except subprocess.CalledProcessError as error:
        raise TopologyError('missing_parent') from error


def _pure(ref, root, git):
    for depth in range(17):
        if ref == M:
            if depth: return
            raise TopologyError('empty_candidate')
        if depth == 16: raise TopologyError('chain_limit')
        parents = _parents(ref, root, git)
        if len(parents) != 1: raise TopologyError('nonpure_chain')
        ref = parents[0]
    raise TopologyError('unknown_anchor')


def _nonrelease(ref, root, git):
    parents = _parents(ref, root, git)
    if len(parents) == 2 and parents[0] == M:
        _pure(parents[1], root, git)
        return ref, parents[1]
    _pure(ref, root, git)
    return ref, None


def topology(ref, root, git, release):
    """No tree reads, content checks or recursive release dispatch."""
    ref = _commit(ref, root, git)
    parents = _parents(ref, root, git)
    if parents and parents[0] == release:
        if len(parents) != 2: raise TopologyError('release_parent_count')
        return ('release', *_nonrelease(parents[1], root, git))
    return ('nonrelease', *_nonrelease(ref, root, git))


def outside_io(data):
    lines = data.decode().splitlines(keepends=True)
    module = ast.parse(data)
    directory = next(n for n in module.body if isinstance(n, ast.FunctionDef) and n.name == '_directory')
    owner = next(n for n in module.body if isinstance(n, ast.ClassDef) and n.name == 'PrivateRoot')
    changed = [directory, *(n for n in owner.body if isinstance(n, ast.FunctionDef)
                            and n.name in ('__init__', '_parent'))]
    assert len(changed) == 3
    for node in sorted(changed, key=lambda n: n.lineno, reverse=True):
        lines[node.lineno - 1:node.end_lineno] = ['<reviewed ' + node.name + '>\n']
    return ''.join(lines)


def proof_contract(data):
    module = ast.parse(data)
    owner = next(n for n in module.body if isinstance(n, ast.ClassDef) and n.name == 'DefaultWorkerProofTests')
    tests = [n for n in owner.body if isinstance(n, ast.FunctionDef) and n.name.startswith('test_')]
    assert len(tests) == 24
    digest = hashlib.sha256('\n'.join(ast.dump(n, include_attributes=False) for n in tests).encode()).hexdigest()
    assert digest == '6f29e88208312c6173ecf26a9beccd8e99ee9f36015f79ac50bf207efe03c271'
    production = next(n for n in owner.body if isinstance(n, ast.FunctionDef) and n.name == 'production')
    assert hashlib.sha256(ast.dump(production, include_attributes=False).encode()).hexdigest() == (
        '03c91fac639ccceec98adc431a10cbf806a07a14ea353550ef6a2395c83501e7')


def budgets(ref, root, git, data):
    total = 0
    for path, (line_cap, diff_cap) in CAPS.items():
        assert len(data[path].splitlines()) <= line_cap, path
        fields = git('diff', '--numstat', M, ref, '--', path, root=root).split()
        delta = sum(map(int, fields[:2])) if fields else 0
        assert delta <= diff_cap, path
        total += delta
    assert total <= DELTA_LIMIT, 'ownership_delta_budget'
    return total


def content(ref, root, git, entries, historical):
    """Independent content check, deliberately without parent-shape assumptions."""
    assert git('rev-parse', M + '^{tree}', root=root).decode().strip() == M_TREE
    original = historical(M, root)
    actual = entries(ref, root)
    assert original.keys() <= actual.keys() and actual.keys() - original.keys() <= CAPS.keys()
    assert {p for p in original.keys() | actual.keys() if original.get(p) != actual.get(p)} == CAPS.keys()
    assert all(actual[p] == value for p, value in original.items() if p not in CAPS)
    assert all(value[:2] == ('100644', 'blob') for value in actual.values())
    data = {p: git('cat-file', 'blob', actual[p][2], root=root) for p in CAPS}
    old = {p: git('cat-file', 'blob', original[p][2], root=root) for p in OLD_PINS}
    for path, expected in OLD_PINS.items(): assert pin(old[path]) == expected, path
    for path, expected in NEW_PINS.items(): assert pin(data[path]) == expected, path
    assert outside_io(old[IO]) == outside_io(data[IO])
    proof_contract(data[PROOF])
    assert len(data[FIXTURE]) == 12953 and len(data[FIXTURE].splitlines()) == 360
    budgets(ref, root, git, data)
    return actual


def release_content(ref, expected, root, git, entries, release, release_tree, documents):
    assert git('rev-parse', release + '^{tree}', root=root).decode().strip() == release_tree
    assert all(entries(release, root)[p] == value for p, value in documents.items())
    expected = expected | documents
    assert entries(ref, root) == expected
    return expected


def selected_profile(ref, root, git, entries, historical, release, release_tree, documents):
    ref = _commit(ref, root, git)  # Bind all subsequent tree reads to the selected object.
    kind, tip, pure = topology(ref, root, git, release)
    expected = content(pure or tip, root, git, entries, historical)
    if pure is not None: assert entries(tip, root) == expected
    if kind == 'release':
        return release_content(ref, expected, root, git, entries, release, release_tree, documents)
    return expected
