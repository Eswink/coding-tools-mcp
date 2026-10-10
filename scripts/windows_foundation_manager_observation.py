#!/usr/bin/env python3
"""Bounded fixed-public-source metadata only; never change or admit raw source."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
sys.dont_write_bytecode = True
from windows_foundation_source_guard import run_git

MANAGER_PATHS = ('.github/workflows/windows-foundation-source-compile.yml',
    'scripts/windows_foundation_source_compile.ps1', 'scripts/windows_foundation_source_guard.py',
    'scripts/windows_foundation_source_manifest.json',
    'docs/specs/windows-foundation-source-compile/requirements.md',
    'docs/specs/windows-foundation-source-compile/design.md',
    'docs/specs/windows-foundation-source-compile/tasks.md')
MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_RECEIPT_BYTES = 32 * 1024


def byte_metadata(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
        'git_blob': hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest(),
        'LF': data.count(b'\n'), 'CRLF': data.count(b'\r\n'),
        'lone_LF': data.count(b'\n') - data.count(b'\r\n')}


def read_fixed_public_file(manager, name):
    file = manager / name
    # Diagnostic containment checks are not native parent-handle pins or IO authority.
    for parent in [file] + list(file.parents):
        if parent == manager:
            break
        if parent.is_symlink() or (hasattr(parent, 'is_junction') and parent.is_junction()):
            raise ValueError('fixed public source link rejected: ' + name)
    before = file.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_SOURCE_BYTES:
        raise ValueError('fixed public source kind/size rejected: ' + name)
    with file.open('rb') as reader:
        opened = os.fstat(reader.fileno())
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise ValueError('fixed public source changed before read: ' + name)
        data = reader.read(MAX_SOURCE_BYTES + 1)
        after = os.fstat(reader.fileno())
        if len(data) > MAX_SOURCE_BYTES or (after.st_size, after.st_mtime_ns) != (opened.st_size, opened.st_mtime_ns):
            raise ValueError('fixed public source size/change rejected: ' + name)
    return data


def observe_manager_sources(manager):
    expected_head = os.environ.get('GITHUB_SHA', '')
    actual_head = run_git(manager, 'rev-parse', 'HEAD').decode().strip()
    if not re.fullmatch('[0-9a-f]{40}', expected_head) or actual_head != expected_head:
        raise ValueError('diagnostic actual HEAD differs from GITHUB_SHA')
    rows = []
    for name in sorted(MANAGER_PATHS):
        entries = [x for x in run_git(manager, 'ls-tree', '-z', 'HEAD', '--', name).split(b'\0') if x]
        if len(entries) != 1:
            raise ValueError('fixed public source absent from HEAD: ' + name)
        header, path = entries[0].split(b'\t', 1)
        mode, kind, blob = header.decode().split()
        if mode != '100644' or kind != 'blob' or path.decode() != name or not re.fullmatch('[0-9a-f]{40}', blob):
            raise ValueError('fixed public source HEAD entry rejected: ' + name)
        size = run_git(manager, 'cat-file', '-s', blob).decode().strip()
        if not size.isdecimal() or int(size) > MAX_SOURCE_BYTES:
            raise ValueError('fixed public expected source size rejected: ' + name)
        expected = run_git(manager, 'cat-file', 'blob', blob)
        if len(expected) > MAX_SOURCE_BYTES:
            raise ValueError('fixed public expected source oversized: ' + name)
        actual = read_fixed_public_file(manager, name)
        row = {'path': name, 'git_mode': mode, 'expected': byte_metadata(expected),
            'actual': byte_metadata(actual), 'raw_equal': actual == expected,
            'comparison_only_CRLF_to_LF_equals_expected': actual.replace(b'\r\n', b'\n') == expected,
            'comparison_only_expected_LF_to_CRLF_equals_actual': b'\r\n' not in expected and expected.replace(b'\n', b'\r\n') == actual}
        if row['expected']['git_blob'] != blob:
            raise ValueError('fixed public expected Git payload mismatch: ' + name)
        rows.append(row)
    return {'diagnostic_only': True, 'admission': False, 'native_authority': False,
        'compiler': 'NOTRUN_BY_OBSERVER', 'qualification': 'SOURCE_ONLY_BLOCKED',
        'manager_commit': actual_head, 'fixed_source_count': len(rows),
        'all_raw_equal': all(row['raw_equal'] for row in rows),
        'Git_configuration_cause': 'UNKNOWN; byte comparison does not prove checkout configuration', 'rows': rows}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manager', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    result = {'diagnostic_only': True, 'admission': False, 'native_authority': False,
        'transport': 'FAIL', 'qualification': 'SOURCE_ONLY_BLOCKED'}
    try:
        result.update(observe_manager_sources(args.manager.resolve()))
        result['transport'] = 'SUCCESS'
    except (OSError, ValueError, RuntimeError):
        # Preserve cancellation/KeyboardInterrupt/SystemExit; never serialize host paths/errors.
        result['error'] = 'fixed-public-source observation failed; no admission or normalization applied'
    data = (json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode()
    if len(data) > MAX_RECEIPT_BYTES:
        raise ValueError('bounded diagnostic receipt oversized')
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_bytes(data)
    print('fixed-public-source observation transport=' + result['transport'] + '; admission=false')
    return 0 if result['transport'] == 'SUCCESS' else 1


if __name__ == '__main__':
    sys.exit(main())
