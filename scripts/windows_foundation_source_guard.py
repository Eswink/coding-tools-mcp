#!/usr/bin/env python3
"""Restore and verify a finite source-only SUT; never invoke a compiler/native fixture."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import time

BASE = 'c60f9667fa8431e27fabbc497c19b4abfef5b965'
EXACT73 = 'd4bd2d9813176afd83270ba39971d3204e350105'
TARGET = '19bb292004e0fd4ed02374b35bcd2f22469779f0'
PATCH_SHA = '3d3e83dc6c0122286dd2d44400846895a331cb22ab5bae49a45cbc1bce2d634d'
REPOSITORY = 'https://github.com/Eswink/coding-tools-mcp.git'
PROTECTED = 'src-tauri/src/tools/cloud_host/live/wss_workspace_io_tests.rs'
PROTECTED_SHA = 'c9fcdba432c239cc08a090c6cb4256f51b54368cbefb3afac553c1a6c719b9b8'
MANIFEST_PATH = 'scripts/windows_foundation_source_manifest.json'
# Paths left out of the layer tree the manifest describes. The manifest cannot pin its own bytes.
# No other tracked file pins the manifest's sha256/blob (checked when this layer was written).
LAYER_EXCLUDED = (MANIFEST_PATH,)
# Schema 1 is accepted only on the frozen historical #147 commits that carried the v1 manifest blob.
V1_MANIFEST_BLOB = '424a9b1794ee11c6b6933522cacbd2a51157bb1b'
V1_FROZEN_LAST = '313c3a1688673150b1484bc2af6b5ae95a8a6b2f'


def run_git(repo, *args, index=False, data=None):
    env = os.environ.copy()
    # Ignore any caller-supplied repository or object/index redirection.
    for key in list(env):
        if key.startswith('GIT_'):
            env.pop(key)
    env['GIT_CONFIG_NOSYSTEM'] = '1'
    env['GIT_CONFIG_GLOBAL'] = os.devnull
    env['GIT_NO_REPLACE_OBJECTS'] = '1'
    executable = shutil.which('git')
    if not executable:
        raise RuntimeError('native Git executable is unavailable')
    if index:
        env['GIT_INDEX_FILE'] = str(repo / '.git' / 'foundation-candidate.index')
    result = subprocess.run([executable, '-c', 'core.autocrlf=false', '-c',
                             'core.hooksPath=' + os.devnull, '-C', str(repo), *args],
                            input=data, capture_output=True, env=env, check=False)
    if result.returncode:
        raise RuntimeError('git ' + args[0] + ' failed: ' + result.stderr.decode('utf-8', 'replace')[:4096])
    return result.stdout


def safe_path(value):
    if not isinstance(value, str) or not value or '\\' in value or '\x00' in value:
        raise ValueError('invalid source path')
    p = PurePosixPath(value)
    if p.is_absolute() or str(p) != value or any(x in ('.', '..', '.git') or ':' in x for x in p.parts):
        raise ValueError('unsafe source path')
    return value


def check_blob(data, row):
    if len(data) != row['bytes'] or hashlib.sha256(data).hexdigest() != row['sha256']:
        raise ValueError('source SHA/size mismatch: ' + row['path'])
    blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
    if blob != row['blob']:
        raise ValueError('source blob mismatch: ' + row['path'])


def tree_excluding(repo, tree, excluded=LAYER_EXCLUDED):
    """Shared by generator and guard: temp index <- tree, update-index --force-remove excluded paths (index-only, worktree-independent), write-tree."""
    import tempfile
    with tempfile.TemporaryDirectory(prefix='foundation-layer-index-') as tmp:
        index = Path(tmp) / 'index'
        def git(*args):
            env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
            env.update(GIT_INDEX_FILE=str(index), GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
                       GIT_NO_REPLACE_OBJECTS='1', LC_ALL='C')
            r = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, env=env, check=False)
            if r.returncode:
                raise RuntimeError('git ' + args[0] + ' failed: ' + r.stderr.decode('utf-8', 'replace')[:4096])
            return r.stdout
        git('read-tree', tree)
        for path in excluded:
            git('update-index', '--force-remove', '--', safe_path(path))
        return git('write-tree').decode().strip()


def layer_rows(repo, tree):
    rows = []
    for row in sorted(tree_rows(repo, tree), key=lambda r: r['path'].encode('utf-8')):
        data = run_git(repo, 'cat-file', 'blob', row['blob'])
        rows.append(dict(row, bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
    return rows


def manifest_commit_is_v1_frozen(repo, commit):
    if not repo or not commit or not re.fullmatch('[0-9a-f]{40}', commit):
        return False
    try:
        run_git(repo, 'merge-base', '--is-ancestor', commit, V1_FROZEN_LAST)
        blob = run_git(repo, 'rev-parse', commit + ':' + MANIFEST_PATH).decode().strip()
    except RuntimeError:
        return False
    return blob == V1_MANIFEST_BLOB


def load_manifest(path, local=False, repo=None, commit=None):
    m = json.loads(path.read_text(encoding='utf-8'))
    if type(m.get('schema')) is not int or m['schema'] not in (1, 2):
        raise ValueError('unsupported manifest schema')
    if m['schema'] == 1 and not manifest_commit_is_v1_frozen(repo, commit):
        raise ValueError('schema 1 manifest only admitted on frozen historical commits; schema 2 required')
    if (m['repository'], m['base_commit'], m['exact73_tree'], m['target_tree'],
        m['full43_patch_sha256'], m['target_tree_files'], m['exact73_tree_files'],
        m['protected_positive_path'], m['protected_positive_sha256']) != (
            'Eswink/coding-tools-mcp', BASE, EXACT73, TARGET, PATCH_SHA, 1953, 1913, PROTECTED, PROTECTED_SHA):
        raise ValueError('manifest source identity differs from finite approved source')
    if (m['exact73_backup_commit'], m['full43_backup_commit'], m['exact73_prefix'], m['full43_patch_path']) != (
            '47adc2a11135e692b8de15534debacf9a1cc1948',
            '155eafad649380669130241167e61b37e1f9359a',
            'development-backups/rc070/20261009/checkpoint-01/windows-recovered-exact73/source/',
            'development-backups/rc070/20261009/checkpoint-06/FULL43-FROM-EXACT73.patch'):
        raise ValueError('immutable source lease differs from approved backup commits/prefixes')
    safe_path(m['full43_patch_path'])
    safe_path(m['exact73_prefix'].rstrip('/'))
    for field, count in [('exact73', 73), ('whole_source', 1953)]:
        rows = m[field]
        if len(rows) != count or len({r['path'] for r in rows}) != count:
            raise ValueError('duplicate/missing source rows')
        for row in rows:
            safe_path(row['path'])
            if row['mode'] not in ('100644', '100755') or not isinstance(row['bytes'], int) or row['bytes'] < 0:
                raise ValueError('source mode/size not allowed')
            if not re.fullmatch('[0-9a-f]{40}', row['blob']) or not re.fullmatch('[0-9a-f]{64}', row['sha256']):
                raise ValueError('source hash malformed')
    if m['schema'] == 2:
        if m.get('excluded_paths') != list(LAYER_EXCLUDED):
            raise ValueError('schema 2 excluded paths differ')
        if not re.fullmatch('[0-9a-f]{40}', str(m.get('target_tree_excluding_manifest'))):
            raise ValueError('schema 2 layer tree malformed')
        rows = m.get('layer_source')
        if not isinstance(rows, list) or len(rows) != m.get('target_tree_excluding_manifest_files'):
            raise ValueError('schema 2 layer rows/count differ')
        if [r['path'] for r in rows] != sorted((r['path'] for r in rows), key=lambda p: p.encode('utf-8')):
            raise ValueError('schema 2 layer rows not byte-sorted')
        if any(safe_path(r['path']) in LAYER_EXCLUDED for r in rows):
            raise ValueError('schema 2 layer rows include excluded path')
    return m


def verify_layer(repo, m, commit='HEAD'):
    if m['schema'] != 2:
        raise ValueError('layer verification requires schema 2')
    tree = run_git(repo, 'rev-parse', commit + '^{tree}').decode().strip()
    actual = tree_excluding(repo, tree)
    if actual != m['target_tree_excluding_manifest']:
        raise ValueError('layer tree excluding manifest differs')
    if layer_rows(repo, actual) != m['layer_source']:
        raise ValueError('layer source rows differ')
    return {'layer_tree': tree, 'target_tree_excluding_manifest': actual, 'layer_files': len(m['layer_source'])}


def tree_rows(repo, tree):
    rows = []
    for entry in run_git(repo, 'ls-tree', '-rz', tree).split(b'\0'):
        if not entry:
            continue
        head, path = entry.split(b'\t', 1)
        mode, kind, blob = head.decode('ascii').split()
        name = safe_path(path.decode('utf-8'))
        if kind != 'blob' or mode not in ('100644', '100755'):
            raise ValueError('non-file candidate entry')
        rows.append({'path': name, 'mode': mode, 'blob': blob})
    return rows


def verify_materialized(repo, m):
    if run_git(repo, 'rev-parse', 'HEAD').decode().strip() != BASE:
        raise ValueError('SUT HEAD is not D6')
    actual = run_git(repo, 'write-tree', index=True).decode().strip()
    if actual != TARGET:
        raise ValueError('candidate custom index tree mismatch')
    native = tree_rows(repo, TARGET)
    expected = [{k: row[k] for k in ('path', 'mode', 'blob')} for row in m['whole_source']]
    if native != expected:
        raise ValueError('whole-source manifest differs from native candidate tree')
    digest = hashlib.sha256()
    for row in m['whole_source']:
        path = repo / row['path']
        if path.is_symlink() or not path.is_file():
            raise ValueError('missing or symlink source: ' + row['path'])
        data = path.read_bytes()
        check_blob(data, row)
        if os.name != 'nt' and bool(path.stat().st_mode & 0o111) != (row['mode'] == '100755'):
            raise ValueError('materialized executable mode mismatch: ' + row['path'])
        # On Windows native Git index mode plus actual bytes are verified; NTFS lacks POSIX chmod semantics.
        digest.update(row['path'].encode() + b'\0' + row['mode'].encode() + b'\0' + row['sha256'].encode() + b'\n')
    if hashlib.sha256((repo / PROTECTED).read_bytes()).hexdigest() != PROTECTED_SHA:
        raise ValueError('protected original positive changed')
    if (repo / 'src-tauri/src/tools/cloud_host/windows_workspace/stage.rs').exists():
        raise ValueError('blocked Stage11 source present')
    # Compiler target output is ignored by native Git; untracked source is not allowed into this SUT.
    others = run_git(repo, 'ls-files', '--others', '--exclude-standard', '-z', index=True).split(b'\0')
    if any(x for x in others):
        raise ValueError('untracked source outside ignored compiler output')
    return {'tree': actual, 'files': len(native), 'source_digest': digest.hexdigest(),
            'protected_positive_sha256': PROTECTED_SHA, 'native_positive': 'NOTRUN', 'native_authority': False}


def verify_manager(manager):
    expected_head = os.environ.get('GITHUB_SHA', '')
    actual_head = run_git(manager, 'rev-parse', 'HEAD').decode().strip()
    if not re.fullmatch('[0-9a-f]{40}', expected_head) or actual_head != expected_head:
        raise ValueError('management actual HEAD differs from GITHUB_SHA')
    paths = ['.github/workflows/windows-foundation-source-compile.yml',
             'scripts/windows_foundation_source_compile.ps1',
             'scripts/windows_foundation_source_guard.py',
             'scripts/windows_foundation_source_manifest.json'] + [
        'docs/specs/windows-foundation-source-compile/' + name + '.md'
        for name in ('requirements', 'design', 'tasks')]
    rows = []
    for path in sorted(paths):
        entries = run_git(manager, 'ls-tree', '-z', 'HEAD', '--', path).split(b'\0')
        entries = [entry for entry in entries if entry]
        if len(entries) != 1:
            raise ValueError('management source missing from actual HEAD: ' + path)
        header, actual_path = entries[0].split(b'\t', 1)
        mode, kind, blob = header.decode().split()
        file = manager / path
        if mode != '100644' or kind != 'blob' or actual_path.decode() != path or file.is_symlink():
            raise ValueError('management mode/path mismatch')
        data = file.read_bytes()
        row = {'path': path, 'mode': mode, 'blob': blob, 'bytes': len(data),
               'sha256': hashlib.sha256(data).hexdigest()}
        check_blob(data, row)
        if os.name != 'nt' and file.stat().st_mode & 0o111:
            raise ValueError('management executable mode changed')
        rows.append(row)
    digest = hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'manager_commit': actual_head, 'manager_files': 7, 'management_digest': digest,
            'management_source': rows, 'native_authority': False, 'native_positive': 'NOTRUN'}


def restore_source(manager, destination, m, local_payload=None):
    if destination.exists():
        raise ValueError('fresh SUT destination already exists')
    # Validate all payload bytes and the complete patch before creating the SUT.
    if local_payload:
        payloads = []
        for row in m['exact73']:
            path = local_payload / 'source' / row['path']
            if path.is_symlink() or not path.is_file():
                raise ValueError('local payload missing/symlink')
            data = path.read_bytes()
            check_blob(data, row)
            payloads.append(data)
        patch_file = local_payload / 'FULL43-FROM-EXACT73.patch'
        if patch_file.is_symlink():
            raise ValueError('patch symlink denied')
        patch = patch_file.read_bytes()
    else:
        if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('GITHUB_REPOSITORY') != m['repository']:
            raise ValueError('remote restoration restricted to named repository disposable CI')
        for commit in sorted({m['exact73_backup_commit'], m['full43_backup_commit']}):
            run_git(manager, 'fetch', '--no-tags', REPOSITORY, commit)
        payloads = []
        for row in m['exact73']:
            ref = m['exact73_backup_commit'] + ':' + m['exact73_prefix'] + row['path'] + '.source'
            data = run_git(manager, 'show', ref)
            check_blob(data, row)
            payloads.append(data)
        patch = run_git(manager, 'show', m['full43_backup_commit'] + ':' + m['full43_patch_path'])
    if len(patch) != m['full43_patch_bytes'] or hashlib.sha256(patch).hexdigest() != PATCH_SHA:
        raise ValueError('full43 patch SHA/size mismatch')
    destination.parent.mkdir(parents=True, exist_ok=True)
    run_git(manager, 'clone', '--no-hardlinks', '--no-checkout', str(manager), str(destination))
    run_git(destination, 'config', 'core.autocrlf', 'false')
    run_git(destination, 'checkout', '--detach', BASE)
    run_git(destination, 'read-tree', BASE, index=True)
    for row, data in zip(m['exact73'], payloads):
        blob = run_git(destination, 'hash-object', '-w', '--stdin', data=data).decode().strip()
        if blob != row['blob']:
            raise ValueError('native hash-object source mismatch')
        run_git(destination, 'update-index', '--add', '--cacheinfo', row['mode'] + ',' + blob + ',' + row['path'], index=True)
    actual73 = run_git(destination, 'write-tree', index=True).decode().strip()
    if actual73 != EXACT73 or len(tree_rows(destination, actual73)) != 1913:
        raise ValueError('actual exact73 tree/count differs')
    run_git(destination, 'apply', '--cached', '--check', '--whitespace=nowarn', '-', index=True, data=patch)
    run_git(destination, 'apply', '--cached', '--whitespace=nowarn', '-', index=True, data=patch)
    if run_git(destination, 'write-tree', index=True).decode().strip() != TARGET:
        raise ValueError('full43 native apply produced wrong tree')
    run_git(destination, 'checkout-index', '--all', '--force', index=True)
    return verify_materialized(destination, m)


def write_receipt(path, result):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=('restore', 'verify', 'verify-manager', 'verify-layer'))
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--destination', type=Path)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--manager', type=Path)
    parser.add_argument('--local-payload', type=Path)
    args = parser.parse_args()
    result = {'operation': args.operation, 'passed': False, 'native_positive': 'NOTRUN',
              'compiler': 'NOTRUN_BY_SOURCE_GUARD', 'qualification': 'SOURCE_ONLY_BLOCKED', 'at_unix': time.time()}
    try:
        manager = args.manager.resolve() if args.manager else None
        manager_head = run_git(manager, 'rev-parse', 'HEAD').decode().strip() if manager else None
        manifest = load_manifest(args.manifest, local=args.local_payload is not None, repo=manager, commit=manager_head)
        if args.operation == 'verify-layer':
            if not manager:
                raise ValueError('layer verifier requires management checkout')
            result.update(verify_layer(manager, manifest))
            result['passed'] = True
            write_receipt(args.receipt.resolve(), result)
            print(json.dumps(result, ensure_ascii=False))
            return 0
        if args.operation == 'verify-manager':
            if not args.manager:
                raise ValueError('management verifier requires management checkout')
            result.update(verify_manager(args.manager.resolve()))
            result['passed'] = True
            write_receipt(args.receipt.resolve(), result)
            print(json.dumps(result, ensure_ascii=False))
            return 0
        if not args.destination:
            raise ValueError('SUT operation requires separate destination')
        destination = args.destination.resolve()
        result.update({'manager_commit': run_git(args.manager.resolve(), 'rev-parse', 'HEAD').decode().strip()
                       if args.manager else None, 'base_commit': BASE, 'pure_sut_tree': TARGET,
                       'exact73_backup_commit': manifest['exact73_backup_commit'],
                       'full43_backup_commit': manifest['full43_backup_commit'],
                       'payload_mode': 'LOCAL_GUARD_TEST_ONLY' if args.local_payload else 'IMMUTABLE_REMOTE_CI'})
        if args.operation == 'restore':
            if not args.manager or destination == args.manager.resolve() or args.manager.resolve() in destination.parents:
                raise ValueError('SUT must be separate from management checkout')
            result.update(restore_source(args.manager.resolve(), destination, manifest,
                                         args.local_payload.resolve() if args.local_payload else None))
        else:
            result.update(verify_materialized(destination, manifest))
        result['passed'] = True
    except Exception as error:
        result['error'] = str(error)
    write_receipt(args.receipt.resolve(), result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
