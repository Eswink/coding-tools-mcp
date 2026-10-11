#!/usr/bin/env python3
"""Deterministically regenerate scripts/windows_foundation_source_manifest.json (schema 2).

Reads git objects only (never the working tree). Fixed inputs: base c60f9667, exact73 backup 47adc2a1,
full43 backup 155eafad, frozen tree 19bb2920. Parameter: --target-tree (default HEAD^{tree}); the layer
tree is computed with guard.tree_excluding, the same function the guard uses to verify it.
Usage: gen_windows_foundation_source_manifest.py [--repo .] [--target-tree TREE] [--schema 1|2] > out.json
"""
import argparse, hashlib, json, sys
from pathlib import Path
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import windows_foundation_source_guard as guard

EX_COMMIT = '47adc2a11135e692b8de15534debacf9a1cc1948'
EX_PREFIX = 'development-backups/rc070/20261009/checkpoint-01/windows-recovered-exact73/source/'
F43_COMMIT = '155eafad649380669130241167e61b37e1f9359a'
F43_PATH = 'development-backups/rc070/20261009/checkpoint-06/FULL43-FROM-EXACT73.patch'
QUAL = 'SOURCE_ONLY_BLOCKED; compiler/data CI only; native positive NOTRUN; no RC qualification'


def ls(repo, tree, prefix=''):
    out = []
    for rec in guard.run_git(repo, 'ls-tree', '-r', '-z', '--full-tree', tree).split(b'\0'):
        if not rec:
            continue
        meta, path = rec.split(b'\t', 1)
        mode, kind, oid = meta.decode().split()
        path = path.decode('utf-8')
        if kind != 'blob' or not path.startswith(prefix):
            continue
        path = path[len(prefix):]
        if prefix:
            if not path.endswith('.source'):
                raise ValueError('exact73 payload without .source suffix: ' + path)
            path = path[:-len('.source')]  # backup stores each recovered file as <path>.source
        out.append((path, mode, oid))
    return sorted(out, key=lambda e: e[0].encode('utf-8'))


def entry(repo, path, mode, oid):
    data = guard.run_git(repo, 'cat-file', 'blob', oid)
    return {'path': path, 'mode': mode, 'blob': oid, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def overlay_tree(repo, base_tree, rows):
    import os, subprocess, tempfile
    with tempfile.TemporaryDirectory(prefix='foundation-exact73-index-') as tmp:
        env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        env.update(GIT_INDEX_FILE=str(Path(tmp) / 'index'), LC_ALL='C')
        run = lambda *a, data=None: subprocess.run(['git', '-C', str(repo), *a], input=data, env=env,
                                                   capture_output=True, check=True).stdout
        run('read-tree', base_tree)
        run('update-index', '--add', '--index-info',
            data=''.join(f'{m} {o}\t{p}\n' for p, m, o in rows).encode('utf-8'))
        return run('write-tree').decode().strip()


def generate(repo, target_tree, schema=2):
    base_tree = guard.run_git(repo, 'rev-parse', guard.BASE + '^{tree}').decode().strip()
    ex = ls(repo, EX_COMMIT, EX_PREFIX)
    ex_tree = overlay_tree(repo, base_tree, ex)
    frozen = ls(repo, guard.TARGET)
    patch = guard.run_git(repo, 'cat-file', 'blob', F43_COMMIT + ':' + F43_PATH)
    prot = next(e for e in frozen if e[0] == guard.PROTECTED)
    d = {'schema': schema, 'repository': 'Eswink/coding-tools-mcp', 'base_commit': guard.BASE,
         'base_tree_files': len(ls(repo, base_tree)), 'exact73_tree': ex_tree,
         'exact73_tree_files': len(ls(repo, ex_tree)), 'target_tree': guard.TARGET,
         'target_tree_files': len(frozen), 'exact73_backup_commit': EX_COMMIT, 'exact73_prefix': EX_PREFIX,
         'full43_backup_commit': F43_COMMIT, 'full43_patch_path': F43_PATH,
         'full43_patch_sha256': hashlib.sha256(patch).hexdigest(), 'full43_patch_bytes': len(patch),
         'exact73': [entry(repo, *e) for e in ex], 'whole_source': [entry(repo, *e) for e in frozen],
         'protected_positive_path': guard.PROTECTED,
         'protected_positive_sha256': hashlib.sha256(guard.run_git(repo, 'cat-file', 'blob', prot[2])).hexdigest(),
         'qualification': QUAL}
    if schema == 2:
        layer = guard.tree_excluding(repo, target_tree)
        rows = guard.layer_rows(repo, layer)
        d.update({'excluded_paths': list(guard.LAYER_EXCLUDED), 'target_tree_excluding_manifest': layer,
                  'target_tree_excluding_manifest_files': len(rows), 'layer_source': rows})
    return json.dumps(d, indent=2, ensure_ascii=False) + '\n'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo', type=Path, default=Path('.'))
    ap.add_argument('--target-tree', default='HEAD^{tree}')
    ap.add_argument('--schema', type=int, choices=(1, 2), default=2)
    a = ap.parse_args()
    repo = a.repo.resolve()
    tree = guard.run_git(repo, 'rev-parse', a.target_tree + '^{tree}').decode().strip()
    sys.stdout.buffer.write(generate(repo, tree, a.schema).encode('utf-8'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
