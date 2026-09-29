"""Reconstruct one reviewed product tree in this disposable GitHub CI job only."""
import base64
import hashlib
import json
import lzma
import os
from pathlib import Path
import subprocess

BASE = '2c5d133eaa75d7fc084b8122350d7768ce5b2382'
TREE = '22c8c5e79a737989a42188318994032c603ce556'
LOCAL = 'a53211b716abd7880468a279d6b9eab260f37571'
assert os.environ.get('GITHUB_ACTIONS') == 'true'
assert os.environ.get('GITHUB_REPOSITORY') == 'Eswink/coding-tools-mcp'
assert os.environ.get('GITHUB_REF') == 'refs/heads/ci/issue81-native-drain-v2-20260930'
evidence = Path('evidence')
evidence.mkdir(exist_ok=True)
allowed = ('services/', 'src-tauri/', 'tools/', 'docs/', '.github/workflows/', 'tests/delivery/')
def unpack(pattern, count, size, digest, name, expected_paths):
    encoded = ''.join(Path(pattern.format(i=i)).read_text(encoding='ascii') for i in range(count))
    patch = lzma.decompress(base64.b64decode(encoded, validate=True), memlimit=256 * 1024 * 1024)
    assert len(patch) == size and hashlib.sha256(patch).hexdigest() == digest
    output = evidence / name
    output.write_bytes(patch)
    rows = subprocess.check_output(['git', 'apply', '--numstat', '-z', str(output)]).split(b'\0')
    paths = [row.split(b'\t', 2)[2].decode('utf-8') for row in rows if row]
    assert len(paths) == expected_paths and len(set(paths)) == len(paths)
    assert all(not Path(p).is_absolute() and '..' not in Path(p).parts and p.startswith(allowed) for p in paths)
    return output, paths
base_patch, old_paths = unpack('.ci/issue81-drain-part{i:02d}.txt', 15, 517365,
    'fbc4362f60aede50eb9418ed65134383fdd4b092689aaf71f6bca16481b5d4e3', 'prior-input.patch', 95)
delta_patch, new_paths = unpack('.ci/issue81-drain-v2-part{i:02d}.txt', 5, 153071,
    '0b1636e61a545ff92ebef833344a2be32a834dd71ab1bde3231100859f2af604', 'v2-input.patch', 25)
for patch in (base_patch, delta_patch):
    subprocess.run(['git', 'apply', '--check', str(patch)], check=True)
    subprocess.run(['git', 'apply', str(patch)], check=True)
index = evidence / 'candidate.index'
env = {**os.environ, 'GIT_INDEX_FILE': str(index.resolve())}
subprocess.run(['git', 'read-tree', BASE], env=env, check=True)
for path in sorted(set(old_paths + new_paths)):
    if Path(path).exists():
        assert Path(path).is_file() and not Path(path).is_symlink()
        subprocess.run(['git', 'add', '--', path], env=env, check=True)
    else:
        subprocess.run(['git', 'update-index', '--force-remove', '--', path], env=env, check=True)
tree = subprocess.check_output(['git', 'write-tree'], env=env, text=True).strip()
assert tree == TREE, (tree, TREE)
env.update(GIT_AUTHOR_NAME='CI source verifier', GIT_AUTHOR_EMAIL='ci@users.noreply.github.com',
    GIT_COMMITTER_NAME='CI source verifier', GIT_COMMITTER_EMAIL='ci@users.noreply.github.com',
    GIT_AUTHOR_DATE='2026-09-30T00:00:00+00:00', GIT_COMMITTER_DATE='2026-09-30T00:00:00+00:00')
commit = subprocess.check_output(['git', 'commit-tree', TREE, '-p', BASE, '-m',
    'Exact product checkout for Issue81 native drain v2; not a release commit'], env=env, text=True).strip()
# This guarded disposable CI checkout deliberately excludes all transfer helper files.
subprocess.run(['git', 'reset', '--hard', commit], check=True)
index.unlink(missing_ok=True)
paths = subprocess.check_output(['git', 'diff', '--name-only', '-z', BASE, 'HEAD']).decode().strip('\0').split('\0')
assert len(paths) == len(set(paths)) == 100
files = {}
for path in paths:
    data = Path(path).read_bytes()
    mode = subprocess.check_output(['git', 'ls-files', '--stage', '--', path], text=True).split()[0]
    files[path] = {'sha256': hashlib.sha256(data).hexdigest(),
        'git_blob': hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest(), 'mode': mode}
    output = evidence / 'source' / path
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)
(evidence / 'input.patch').write_bytes(subprocess.check_output(['git', 'diff', '--binary', '--full-index', BASE, 'HEAD']))
(evidence / 'source.json').write_text(json.dumps({'baseline': BASE, 'candidate_tree': TREE,
    'validation_commit': commit, 'workflow_sha': os.environ['GITHUB_SHA'],
    'local_source_commit': LOCAL, 'files': files}, indent=2), encoding='utf-8')
subprocess.run(['git', 'diff', '--exit-code', 'HEAD', '--'], check=True)
print('VERIFIED_PRODUCT_TREE=' + TREE)
