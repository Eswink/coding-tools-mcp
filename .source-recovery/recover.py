#!/usr/bin/env python3
"""One-shot reviewed source reconstruction/blob import; NEVER changes Git refs."""
import argparse, base64, hashlib, json, lzma, os, subprocess, urllib.request
from pathlib import Path

BASE = '5ad89711e67eeb907d496a32a1b54a3f82500c55'
TARGET = '8021ec898142e5a5d9744b2d4ed5657b4db7de8c'
TREE = '5c5730dab9926193a5ab28d4ad41b48978818314'
DIGEST = '64940bc8b6db9c9ff45b0c7698f054ba590b6003ed8a68071fd382bdc2125da9'
REPO = 'Eswink/coding-tools-mcp'
ALLOWED = ('services/cloud-gateway/', 'docs/specs/cloud-gateway-agent-runtime/', '.github/workflows/cloud-gateway-')
PROTECTED = ('src', 'src-tauri', 'AGENTS.md', 'CLAUDE.md', 'package.json', 'package-lock.json', '.agents', '.claude')

def git(*args):
    return subprocess.check_output(['git', *args]).decode().strip()

def load(directory):
    encoded = ''.join((directory / f'part-{i}.b64').read_text().strip() for i in range(6))
    raw = base64.b64decode(encoded, validate=True)
    assert len(raw) == 44304 and hashlib.sha256(raw).hexdigest() == DIGEST, 'payload mismatch'
    obj = json.loads(lzma.decompress(raw, memlimit=256 * 1024 * 1024))
    assert obj['base'] == BASE and obj['target'] == TARGET and len(obj['commits']) == 2
    return obj

def reconstruct(data):
    assert git('rev-parse', 'HEAD') == BASE, 'wrong source base'
    assert not git('status', '--porcelain', '--untracked-files=no'), 'dirty tracked source'
    parent = BASE
    for c in data['commits']:
        assert c['parent'] == parent
        subprocess.run(['git', 'apply', '--index', '--whitespace=error-all', '-'], input=c['patch'].encode(), check=True)
        paths = git('diff', '--cached', '--name-only').splitlines()
        assert paths and all(p.startswith(ALLOWED) and '..' not in p.split('/') for p in paths)
        assert not git('diff', '--cached', '--diff-filter=D', '--name-only'), 'deletion forbidden'
        tree = git('write-tree')
        assert tree == c['tree'], 'source tree mismatch'
        env = dict(os.environ)
        for role in ('author', 'committer'):
            for key, value in c[role].items():
                env['GIT_' + role.upper() + '_' + key.upper()] = value
        commit = subprocess.check_output(['git', 'commit-tree', tree, '-p', parent], input=c['message'].encode(), env=env).decode().strip()
        assert commit == c['sha'], 'commit identity mismatch'
        subprocess.run(['git', 'checkout', '--detach', commit], check=True)
        parent = commit
    assert parent == TARGET and git('rev-parse', 'HEAD^{tree}') == TREE
    for path in PROTECTED:
        assert git('rev-parse', BASE + ':' + path) == git('rev-parse', TARGET + ':' + path), path
    print(json.dumps({'commit': TARGET, 'tree': TREE, 'protected_paths': 'PASS'}))

def import_blobs(data, output):
    token = os.environ['GH_TOKEN']
    def api(method, path, body=None):
        req = urllib.request.Request('https://api.github.com/repos/' + REPO + '/' + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
                     'X-GitHub-Api-Version': '2022-11-28', 'Content-Type': 'application/json'}, method=method)
        with urllib.request.urlopen(req, timeout=40) as response:
            return json.load(response)
    assert git('rev-parse', 'HEAD') == TARGET
    assert api('GET', 'git/ref/heads/feat/cloud-gateway-agent-runtime')['object']['sha'] == BASE, 'remote changed; stop'
    uploaded = []
    for c in data['commits']:
        paths = git('diff', '--name-only', c['parent'], c['sha']).splitlines()
        assert paths and all(p.startswith(ALLOWED) for p in paths)
        for path in paths:
            mode, kind, sha = git('ls-tree', c['sha'], '--', path).split('\t')[0].split()
            assert mode in ('100644', '100755') and kind == 'blob'
            if sha in uploaded:
                continue
            raw = subprocess.check_output(['git', 'cat-file', 'blob', sha])
            made = api('POST', 'git/blobs', {'content': base64.b64encode(raw).decode(), 'encoding': 'base64'})
            assert made['sha'] == sha, 'blob mismatch'
            uploaded.append(sha)
    report = {'base': BASE, 'target': TARGET, 'tree': TREE, 'payload_sha256': DIGEST,
              'uploaded_blobs': uploaded, 'ref_modified': False, 'trees_or_commits_created': False}
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'uploaded_blobs': len(uploaded), 'ref_modified': False}))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['reconstruct', 'import-blobs'])
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output', type=Path, default=Path('import-result.json'))
    args = parser.parse_args()
    data = load(args.directory)
    if args.mode == 'reconstruct':
        reconstruct(data)
    else:
        import_blobs(data, args.output)
