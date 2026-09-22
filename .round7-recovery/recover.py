#!/usr/bin/env python3
"""One-shot exact-source reconstruction; blob import only, never branch mutation."""
import argparse, base64, hashlib, json, lzma, os, subprocess, urllib.request
from pathlib import Path
BASE = '99ed3d061b8c72bde36fcb64b9a29aca6c703a6d'
TARGET = '9cc8fc6251109c4c5a6fedb5f646ac32e2b6910e'
TREE = '4dab6678d5444edcf961bb97a6d4970389ce06c0'
DIGEST = '983988f6a853ae79f7e2c76cb486e066e50bd792bf10f83259c076d5d9cf7f1b'
REPO = 'Eswink/coding-tools-mcp'
ALLOWED = ('services/cloud-gateway/', 'tools/delivery/', 'tests/delivery/', 'docs/specs/cloud-gateway-agent-runtime/', '.github/workflows/cloud-gateway-', '.github/workflows/cloud-delivery.yml')
PROTECTED = ('src', 'src-tauri', 'AGENTS.md', 'CLAUDE.md', 'package.json', 'package-lock.json', '.agents', '.claude')
def git(*args):
    return subprocess.check_output(['git', *args]).decode().strip()
def reconstruct(directory):
    raw = b''.join((directory / f'part-{n:02}.bin').read_bytes() for n in range(7))
    assert len(raw) == 40444 and hashlib.sha256(raw).hexdigest() == DIGEST
    data = json.loads(lzma.decompress(raw))
    assert (data['base'], data['target'], data['tree']) == (BASE, TARGET, TREE)
    assert git('rev-parse', 'HEAD') == BASE
    assert not git('status', '--porcelain', '--untracked-files=no')
    subprocess.run(['git', 'apply', '--index', '--whitespace=error-all', '-'], input=data['patch'].encode(), check=True)
    paths = git('diff', '--cached', '--name-only').splitlines()
    assert len(paths) == 36 and all(p.startswith(ALLOWED) and '..' not in p.split('/') for p in paths)
    assert not git('diff', '--cached', '--name-only', '--diff-filter=D')
    assert git('write-tree') == TREE
    env = dict(os.environ)
    for kind in ('author', 'committer'):
        for key, value in data[kind].items():
            env['GIT_' + kind.upper() + '_' + key.upper()] = value
    made = subprocess.check_output(['git', 'commit-tree', TREE, '-p', BASE], input=(data['message'].rstrip('\n') + '\n').encode(), env=env).decode().strip()
    assert made == TARGET
    subprocess.run(['git', 'checkout', '--detach', made], check=True)
    for path in PROTECTED:
        assert git('rev-parse', BASE + ':' + path) == git('rev-parse', TARGET + ':' + path)
    print(json.dumps({'source': TARGET, 'tree': TREE, 'protected': 'PASS'}))
def import_blobs(directory):
    assert git('rev-parse', 'HEAD') == TARGET and git('rev-parse', 'HEAD^{tree}') == TREE
    token = os.environ['GH_TOKEN']
    def api(path, body=None):
        req = urllib.request.Request('https://api.github.com/repos/' + REPO + '/' + path,
            data=None if body is None else json.dumps(body).encode(),
            headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json', 'Content-Type': 'application/json', 'X-GitHub-Api-Version': '2022-11-28'})
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.load(response)
    assert api('git/ref/heads/feat/cloud-gateway-agent-runtime')['object']['sha'] == BASE, 'remote changed; stop'
    entries = []
    for path in git('diff', '--name-only', BASE, TARGET).splitlines():
        assert path.startswith(ALLOWED)
        mode, kind, sha = git('ls-tree', TARGET, '--', path).split('\t')[0].split()
        assert mode in ('100644', '100755') and kind == 'blob'
        data = subprocess.check_output(['git', 'cat-file', 'blob', sha])
        result = api('git/blobs', {'content': base64.b64encode(data).decode(), 'encoding': 'base64'})
        assert result['sha'] == sha
        entries.append({'path': path, 'mode': mode, 'type': kind, 'sha': sha})
    directory.mkdir(exist_ok=False)
    (directory / 'receipt.json').write_text(json.dumps({'base': BASE, 'source': TARGET, 'tree': TREE, 'ref_modified': False, 'entries': entries}, indent=2))
    print(json.dumps({'verified_blobs': len(entries), 'ref_modified': False}))
if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('mode', choices=['reconstruct', 'import']); p.add_argument('directory', type=Path); args = p.parse_args()
    if args.mode == 'reconstruct': reconstruct(args.directory)
    else: import_blobs(args.directory)
