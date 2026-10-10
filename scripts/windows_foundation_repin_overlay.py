#!/usr/bin/env python3
"""Repin overlay 01: two leaves on the union1967 SUT (4d42a210 -> c8cc0cf3).

Source-only evidence helper for the native workflow. Results are labelled
'frozen SUT + new prepare step'; never native authority or RC qualification.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import windows_foundation_source_guard as guard
import windows_foundation_union_overlay as union

BASELINE = union.TARGET
TARGET = 'c8cc0cf37d60acdb5e7ec711f1b8ff14c35d0568'
TARGET_FILES = 1968
BACKUP = 'ca629f8e4b7c11b567c57d0e67d80dcd2761a43f'
PREFIX = 'development-backups/rc070/20261010/checkpoint-w147-repin01/'
MANIFEST_NAME = 'REPIN-MANIFEST01.json'
MANIFEST_SHA = 'e45302269d5ab62e1e7d8489f2d585cb94fb5fb2b9767769167d1a912008d80c'
MANIFEST_BYTES = 1146
LEAF_TABLE = (
    {'path': 'services/windows-vm-broker/guest_workspace_output_windows.go', 'mode': '100644',
     'blob': 'f3a672bd398d19540445c8158cd1be0d0d0d10d4', 'bytes': 7603,
     'sha256': '690e033bbaada341a346835946b8b49aa4842cdd24fd994aa02af35e332958e2'},
    {'path': 'services/windows-vm-broker/guest_workspace_output_repin_native_test.go', 'mode': '100644',
     'blob': '81c017fc475a908f3bcab489463cb3ad1a244e7c', 'bytes': 2067,
     'sha256': 'f708d12f50879eb94d18f4ba38e1f8cb705a253bac302e62b1c96de39dab5d4b'},
)


def fetch_payload(repo):
    guard.run_git(repo, 'fetch', '--no-tags', guard.REPOSITORY, BACKUP)
    if guard.run_git(repo, 'cat-file', '-t', BACKUP).strip() != b'commit':
        raise ValueError('repin payload is not the fixed backup commit')
    native = {row['path']: row for row in guard.tree_rows(repo, BACKUP)}
    raw = guard.run_git(repo, 'show', BACKUP + ':' + PREFIX + MANIFEST_NAME)
    if len(raw) != MANIFEST_BYTES or hashlib.sha256(raw).hexdigest() != MANIFEST_SHA:
        raise ValueError('repin manifest SHA/size differs')
    m = json.loads(raw.decode('utf-8'))
    if m['baselineTree'] != BASELINE or m['tree'] != TARGET or m['files'] != TARGET_FILES or m['leaves'] != list(LEAF_TABLE):
        raise ValueError('repin manifest identity differs')
    sources = {}
    for row in LEAF_TABLE:
        name = PREFIX + 'source/' + row['path'] + '.source'
        entry = native.get(name)
        if entry is None or entry['mode'] != '100644' or entry['blob'] != row['blob']:
            raise ValueError('repin payload path/mode/blob differs')
        data = guard.run_git(repo, 'show', BACKUP + ':' + name)
        guard.check_blob(data, row)
        sources[row['path']] = data
    return sources


def apply(repo):
    if guard.run_git(repo, 'rev-parse', 'HEAD').decode().strip() != guard.BASE:
        raise ValueError('SUT HEAD is not original base')
    if guard.run_git(repo, 'write-tree', index=True).decode().strip() != BASELINE:
        raise ValueError('SUT is not the union1967 baseline before repin overlay')
    sources = fetch_payload(repo)
    for row in LEAF_TABLE:
        blob = guard.run_git(repo, 'hash-object', '-w', '--stdin', data=sources[row['path']]).decode().strip()
        if blob != row['blob']:
            raise ValueError('repin written blob differs')
        guard.run_git(repo, 'update-index', '--add', '--cacheinfo', row['mode'] + ',' + blob + ',' + row['path'], index=True)
    if guard.run_git(repo, 'write-tree', index=True).decode().strip() != TARGET:
        raise ValueError('repin overlay tree differs')
    guard.run_git(repo, 'checkout-index', '--force', '--', *[row['path'] for row in LEAF_TABLE], index=True)
    for row in LEAF_TABLE:
        file = repo / row['path']
        if file.is_symlink() or not file.is_file():
            raise ValueError('repin leaf absent or symlink')
        guard.check_blob(file.read_bytes(), row)
    if len(guard.tree_rows(repo, TARGET)) != TARGET_FILES:
        raise ValueError('repin tree file count differs')
    return {'baseline_tree': BASELINE, 'tree': TARGET, 'files': TARGET_FILES, 'backup_commit': BACKUP,
            'label': 'frozen SUT + new prepare step', 'native_authority': False, 'qualification': 'SOURCE_ONLY'}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('operation', choices=('apply',))
    p.add_argument('--destination', type=Path, required=True)
    p.add_argument('--receipt', type=Path, required=True)
    a = p.parse_args()
    result = {'operation': 'apply', 'passed': False}
    try:
        result.update(apply(a.destination.resolve()))
        result['passed'] = True
    except Exception as e:  # receipt records the failure; exit code carries it
        result['error'] = str(e)
    guard.write_receipt(a.receipt, result)
    print(json.dumps(result))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
