#!/usr/bin/env python3
"""Strict compiler-only overlay; retains original source guard and never issues authority."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import windows_foundation_source_guard as guard

TARGET = '6b7e33c45c5e56340b1cfb81a7d304c6c60cf23f'
BACKUP = '4385cf1d47f32eda705ccb34d2f06ff388ebb685'
PREFIX = 'development-backups/rc070/20261009/checkpoint-49/'
SOURCE_NAME = 'hcs.rs.source'
MANIFEST_NAME = 'CANDIDATE-FULL1953-MANIFEST01.json'
SOURCE_SHA = 'd22b143b6b199e743b19bf931b50358cfac9fcc761704d81139e87a6c07ade00'
MANIFEST_SHA = '48c2d6547375b02b738abf11b0e3505fe50c6a1e067d15eb3202a6c6e4ff6764'
PATH = 'src-tauri/src/tools/windows_vm/input/owned_run/hcs.rs'
OLD_SHA = 'dd85d23df558c100c0d63c72fc55b72dbc0a2ba158f7a2ee705470916a098cf5'
NEW_BLOB = '5b2626f0dde7cd96b4af77ff6715a7bd9ec55ef5'
OLD_DECLARATION = b'let result = (|| {'
NEW_DECLARATION = b"let result: Result<(), &'static str> = (|| {"
HELPER = 'scripts/windows_foundation_inference_overlay.py'


def verify_helper_lease(manager):
    expected = os.environ.get('GITHUB_SHA', '')
    if not re.fullmatch('[0-9a-f]{40}', expected) or guard.run_git(manager, 'rev-parse', 'HEAD').decode().strip() != expected:
        raise ValueError('overlay manager HEAD differs from actual GitHub source')
    entries = guard.tree_rows(manager, expected)
    rows = [r for r in entries if r['path'] == HELPER]
    if len(rows) != 1 or rows[0]['mode'] != '100644':
        raise ValueError('overlay helper native mode/path absent')
    file = manager / HELPER
    if file.is_symlink() or not file.is_file():
        raise ValueError('overlay helper missing or symlink')
    data = file.read_bytes()
    row = dict(rows[0], bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    guard.check_blob(data, row)
    if os.name != 'nt' and file.stat().st_mode & 0o111:
        raise ValueError('overlay helper physical executable mode changed')
    return {'manager_commit': expected, 'helper_source': row, 'native_authority': False}


def fetch_inference_payload(repo):
    guard.run_git(repo, 'fetch', '--no-tags', guard.REPOSITORY, BACKUP)
    if guard.run_git(repo, 'cat-file', '-t', BACKUP).strip() != b'commit':
        raise ValueError('immutable overlay lease is not a native commit')
    payload = []
    for name, size, sha in [(MANIFEST_NAME, 510045, MANIFEST_SHA), (SOURCE_NAME, 7163, SOURCE_SHA)]:
        entries = [r for r in guard.tree_rows(repo, BACKUP) if r['path'] == PREFIX + name]
        if len(entries) != 1 or entries[0]['mode'] != '100644':
            raise ValueError('immutable overlay payload path/mode differs')
        data = guard.run_git(repo, 'show', BACKUP + ':' + PREFIX + name)
        row = dict(entries[0], bytes=size, sha256=sha)
        guard.check_blob(data, row)
        payload.append(data)
    return payload[0], payload[1]


def load_candidate(manifest_raw, source, baseline):
    if len(manifest_raw) != 510045 or hashlib.sha256(manifest_raw).hexdigest() != MANIFEST_SHA:
        raise ValueError('candidate manifest literal size/SHA differs')
    if len(source) != 7163 or hashlib.sha256(source).hexdigest() != SOURCE_SHA:
        raise ValueError('candidate source literal size/SHA differs')
    m = json.loads(manifest_raw.decode('utf-8'))
    if (m['schema'], m['repository'], m['baseline_target_tree'], m['target_tree'], m['target_tree_files'],
            m['base_commit'], m['allowed_changed_path'], m['protected_positive_path'], m['protected_positive_sha256']) != (
            1, 'Eswink/coding-tools-mcp', guard.TARGET, TARGET, 1953, guard.BASE, PATH, guard.PROTECTED, guard.PROTECTED_SHA):
        raise ValueError('candidate identity differs from fixed approved inference source')
    if m['old_source'] != next(row for row in baseline['whole_source'] if row['path'] == PATH):
        raise ValueError('candidate old row differs from admitted baseline')
    rows = m['whole_source']
    if len(rows) != 1953 or len({row['path'] for row in rows}) != 1953:
        raise ValueError('candidate missing or duplicate source rows')
    expected = []
    for old in baseline['whole_source']:
        expected.append(m['new_source'] if old['path'] == PATH else old)
    if rows != expected or m['new_source']['path'] != PATH or m['new_source']['mode'] != '100644' or m['new_source']['blob'] != NEW_BLOB:
        raise ValueError('candidate is not the exact one-path original1953 source')
    guard.check_blob(source, m['new_source'])
    return m


def verify_inference_candidate(repo, m):
    if guard.run_git(repo, 'rev-parse', 'HEAD').decode().strip() != guard.BASE:
        raise ValueError('candidate SUT HEAD is not original D6')
    actual = guard.run_git(repo, 'write-tree', index=True).decode().strip()
    if actual != TARGET:
        raise ValueError('new candidate custom index tree differs')
    native = guard.tree_rows(repo, TARGET)
    if native != [{k: row[k] for k in ('path', 'mode', 'blob')} for row in m['whole_source']]:
        raise ValueError('new candidate full native1953 differs')
    digest = hashlib.sha256()
    for row in m['whole_source']:
        guard.safe_path(row['path'])
        file = repo / row['path']
        if file.is_symlink() or not file.is_file():
            raise ValueError('candidate missing or symlink source: ' + row['path'])
        data = file.read_bytes()
        guard.check_blob(data, row)
        if os.name != 'nt' and bool(file.stat().st_mode & 0o111) != (row['mode'] == '100755'):
            raise ValueError('candidate executable mode mismatch: ' + row['path'])
        digest.update(row['path'].encode() + b'\0' + row['mode'].encode() + b'\0' + row['sha256'].encode() + b'\n')
    if hashlib.sha256((repo / guard.PROTECTED).read_bytes()).hexdigest() != guard.PROTECTED_SHA:
        raise ValueError('candidate protected positive changed')
    if (repo / 'src-tauri/src/tools/cloud_host/windows_workspace/stage.rs').exists():
        raise ValueError('blocked Stage11 source present')
    if any(guard.run_git(repo, 'ls-files', '--others', '--exclude-standard', '-z', index=True).split(b'\0')):
        raise ValueError('untracked candidate source outside ignored build output')
    return {'tree': actual, 'files': 1953, 'source_digest': digest.hexdigest(),
            'protected_positive_sha256': guard.PROTECTED_SHA, 'native_positive': 'NOTRUN', 'native_authority': False}


def apply_inference_overlay(repo, baseline, manifest_raw, source):
    # Original verifier admits the entire baseline before any write, unchanged.
    guard.verify_materialized(repo, baseline)
    m = load_candidate(manifest_raw, source, baseline)
    old = (repo / PATH).read_bytes()
    if hashlib.sha256(old).hexdigest() != OLD_SHA or old.count(OLD_DECLARATION) != 1 or NEW_DECLARATION in old:
        raise ValueError('overlay old declaration/bytes differ')
    if source.replace(NEW_DECLARATION, OLD_DECLARATION) != old or source.count(NEW_DECLARATION) != 1:
        raise ValueError('overlay changes more than the sole type annotation')
    blob = guard.run_git(repo, 'hash-object', '-w', '--stdin', data=source).decode().strip()
    if blob != NEW_BLOB:
        raise ValueError('native overlay source blob differs')
    guard.run_git(repo, 'update-index', '--cacheinfo', '100644,' + blob + ',' + PATH, index=True)
    guard.run_git(repo, 'checkout-index', '--force', '--', PATH, index=True)
    return verify_inference_candidate(repo, m)



RUST_CASES = ('sealed_chunks_keep_original_and_detached_owners_independent',
              'chunk_cap_and_cancel_do_not_publish_partial_copy',
              'exact_transfer_binding_rejects_each_field_mismatch',
              'invalid_wire_names_and_nil_binding_never_make_native_authority',
              'checked_close_consumes_data_only_transfer',
              'relative_names_remain_data_not_native_permission',
              'diagnostic_metadata_cannot_authorize_output')
GO_CASES = ('TestTransferAllBindingFieldsChangeDigest',
            'TestTransferBoundEOFHashCancellationAndSingleConsumption',
            'TestTransferRelativeAndMalformedIdentityReject',
            'TestLinuxTransferCannotIssueNativeFileIdentity')
GO_FILES = ('services/windows-vm-broker/transfer.go', 'services/windows-vm-broker/transfer_test.go',
            'services/windows-vm-broker/transfer_identity_linux_test.go',
            'services/windows-vm-broker/workspace_stream.go', 'services/windows-vm-broker/guest_workspace_control.go')
CARGO_VECTOR = ('test', '--locked', '--manifest-path', 'src-tauri/Cargo.toml', '--lib',
                '--config', 'build.rustc-wrapper=""', '--config', 'build.rustc-workspace-wrapper=""')


def read_result_log(directory, name):
    # Literal basenames selected by this consumer, never receipt-supplied authority paths.
    if not re.fullmatch(r'[A-Za-z0-9_.-]+\.log', name):
        raise ValueError('consumer log name differs')
    file = directory / name
    if file.is_symlink() or not file.is_file() or file.stat().st_size > 2 * 1024 * 1024:
        raise ValueError('consumer bounded regular log absent')
    return file.read_text(encoding='utf-8-sig', errors='strict')


def verify_compiler_result(record, mode, directory, current_source, current_manager, current_commit):
    target = TARGET if mode == 'rust' else guard.TARGET
    compiler = 'WHOLE_TEST_COMPILE_AND_7_DATA_PASS' if mode == 'rust' else 'DATA_TEST_PASS'
    if mode not in ('rust', 'go') or record.get('passed') is not True or record.get('mode') != mode:
        raise ValueError('consumer requires exact mode and boolean passed')
    if (record.get('compiler') != compiler or record.get('pureSutTree') != target or
            record.get('baselineSutTree') != guard.TARGET or record.get('managerCommit') != current_commit or
            record.get('nativePositive') != 'NOTRUN' or record.get('qualification') != 'SOURCE_ONLY_BLOCKED' or
            record.get('managerObservationFailed') is not False):
        raise ValueError('consumer terminal/compiler identity differs')
    if any(re.search('error|cancel|unknown|skipped', key, re.I) for key in record):
        raise ValueError('consumer interrupted/unknown/error receipt denied')
    if mode == 'rust' and record.get('sourceOverlayStarted') is not True:
        raise ValueError('Rust overlay was not admitted')
    if mode == 'go' and 'sourceOverlayStarted' in record:
        raise ValueError('Go must retain original baseline without overlay')
    baseline = record.get('sourceBaseline', {})
    if (baseline.get('passed') is not True or baseline.get('tree') != guard.TARGET or
            type(baseline.get('files')) is not int or baseline['files'] != 1953 or
            baseline.get('native_authority') is not False or
            baseline.get('protected_positive_sha256') != guard.PROTECTED_SHA):
        raise ValueError('consumer original full baseline absent')
    for key in ('sourceBefore', 'sourceAfter'):
        source = record.get(key, {})
        if (source.get('passed') is not True or source.get('tree') != target or
                type(source.get('files')) is not int or source['files'] != 1953 or
                source.get('native_authority') is not False or source.get('native_positive') != 'NOTRUN' or
                source.get('source_digest') != current_source['source_digest'] or
                source.get('protected_positive_sha256') != guard.PROTECTED_SHA):
            raise ValueError('consumer whole source before/after differs')
    for key in ('managerSourceBefore', 'managerSourceAfter'):
        manager = record.get(key, {})
        if (manager.get('passed') is not True or type(manager.get('manager_files')) is not int or
                manager['manager_files'] != 7 or manager.get('native_authority') is not False or
                manager.get('manager_commit') != current_commit or
                manager.get('management_digest') != current_manager['management_digest'] or
                manager.get('management_source') != current_manager['management_source']):
            raise ValueError('consumer original manager seven before/after differs')
    runtime = record.get('runtime', {})
    expected = {'git', 'python', 'rustup', 'rustc', 'cargo'} if mode == 'rust' else {'git', 'python', 'go'}
    if not isinstance(runtime, dict) or set(runtime) != expected:
        raise ValueError('consumer complete fixed runtime vector absent')
    for tool, row in runtime.items():
        path = Path(row.get('path', ''))
        before, after = row.get('sha256Before'), row.get('sha256After')
        if (not path.is_absolute() or not path.is_file() or
                not isinstance(before, str) or not re.fullmatch('[0-9a-fA-F]{64}', before) or
                not isinstance(after, str) or before != after or
                hashlib.sha256(path.read_bytes()).hexdigest() != before.lower()):
            raise ValueError('consumer actual runtime before/after bytes differ')
        if tool == 'python' and not path.samefile(sys.executable):
            raise ValueError('consumer interpreter differs from producer pinned payload')
        if mode == 'rust' and tool in ('rustc', 'cargo'):
            payload = Path(row.get('payloadPath', ''))
            sha = row.get('payloadSha256Before')
            if (not payload.is_absolute() or not payload.is_file() or
                    not isinstance(sha, str) or not re.fullmatch('[0-9a-fA-F]{64}', sha) or
                    sha != row.get('payloadSha256After') or hashlib.sha256(payload.read_bytes()).hexdigest() != sha.lower()):
                raise ValueError('consumer actual Rust payload differs')
    commands = record.get('commands')
    if not isinstance(commands, list) or not commands:
        raise ValueError('consumer native command records absent')
    by_log = {}
    for command in commands:
        tool = command.get('executable')
        if tool not in runtime or type(command.get('exitCode')) is not int or command['exitCode'] != 0:
            raise ValueError('consumer native command exit differs')
        expected_path = runtime[tool].get('payloadPath', runtime[tool]['path'])
        if command.get('resolvedExecutable') != expected_path or not isinstance(command.get('arguments'), list):
            raise ValueError('consumer native command selection differs')
        name = command.get('log')
        if not isinstance(name, str) or name in by_log:
            raise ValueError('consumer duplicate/missing command log identity')
        read_result_log(directory, name)
        by_log[name] = command
    required_logs = {'git-version.log', 'python-version.log', 'management-byte-observation-Before.log',
                     'management-before.log', 'source-restore.log', 'source-after.log',
                     'management-after.log', 'management-byte-observation-After.log'}
    if not required_logs <= set(by_log):
        raise ValueError('consumer management/source command vector incomplete')
    if mode == 'go':
        if [c['log'] for c in commands if c['executable'] == 'go'] != ['go-version.log', 'go5-data-test.log']:
            raise ValueError('consumer original Go command vector differs')
        if by_log['go-version.log']['arguments'] != ['version'] or not read_result_log(directory, 'go-version.log').startswith('go version go1.24.13 linux/amd64'):
            raise ValueError('consumer pinned Go version differs')
        if by_log['go5-data-test.log']['arguments'] != ['test', '-v', '-count=1', *GO_FILES]:
            raise ValueError('consumer original Go five-source vector differs')
        log = read_result_log(directory, 'go5-data-test.log')
        names = re.findall(r'^--- PASS: ([A-Za-z0-9_]+) \(', log, re.M)
        if len(names) != 4 or set(names) != set(GO_CASES) or not re.search(r'^PASS\r?$', log, re.M):
            raise ValueError('consumer original Go four unique success identities absent')
    else:
        needed = ['cargo-whole-test-compile.log', 'cargo-whole-test-list.log', *['data-' + case + '.log' for case in RUST_CASES]]
        cargo = [c for c in commands if c['executable'] == 'cargo' and c['log'] != 'cargo-version.log']
        if [c['log'] for c in cargo] != needed:
            raise ValueError('consumer original Rust command order/vector differs')
        if cargo[0]['arguments'] != [*CARGO_VECTOR, '--no-run'] or cargo[1]['arguments'] != [*CARGO_VECTOR, '--', '--list']:
            raise ValueError('consumer whole library compile/list command differs')
        listed = read_result_log(directory, needed[1]).splitlines()
        for case, command in zip(RUST_CASES, cargo[2:]):
            matches = [line[:-6] for line in listed if line.endswith('::' + case + ': test')]
            if len(matches) != 1 or not re.fullmatch(r'tools::windows_vm::(?:input|output_stage)::[A-Za-z0-9_:]+', matches[0]):
                raise ValueError('consumer original Rust case absent/ambiguous/wrong namespace')
            full = matches[0]
            if command['arguments'] != [*CARGO_VECTOR, full, '--', '--exact', '--nocapture', '--test-threads=1']:
                raise ValueError('consumer original Rust unique exact command differs')
            log = read_result_log(directory, command['log'])
            if len(re.findall(r'^test ' + re.escape(full) + r' \.\.\. ok\r?$', log, re.M)) != 1 or not re.search(r'test result: ok\. 1 passed; 0 failed; 0 ignored; 0 measured; [0-9]+ filtered out', log):
                raise ValueError('consumer actual exact Rust success log absent')
    return {'passed': True, 'mode': mode, 'tree': target, 'files': 1953,
            'named_data_count': 7 if mode == 'rust' else 4, 'native_authority': False,
            'native_positive': 'NOTRUN', 'qualification': 'COMPILER_DATA_ONLY'}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=('apply', 'verify', 'verify-result'))
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--manager', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--mode', choices=('rust', 'go'))
    parser.add_argument('--compiler-result', type=Path)
    args = parser.parse_args()
    result = {'passed': False, 'native_authority': False, 'native_positive': 'NOTRUN',
              'baseline_tree': guard.TARGET, 'target_tree': TARGET if args.operation != 'verify-result' or args.mode == 'rust' else guard.TARGET, 'backup_commit': BACKUP}
    primary = None
    try:
        helper = verify_helper_lease(args.manager.resolve())
        baseline = guard.load_manifest(args.manifest.resolve())
        if args.operation == 'verify-result':
            if args.mode is None or args.compiler_result is None:
                raise ValueError('terminal consumer requires mode and actual receipt')
            file = args.compiler_result
            if file.is_symlink() or not file.is_file() or file.stat().st_size > 2 * 1024 * 1024:
                raise ValueError('terminal producer receipt missing or unbounded')
            record = json.loads(file.read_text(encoding='utf-8-sig'))
            if record.get('sourceBaseline', {}).get('payload_mode') != 'IMMUTABLE_REMOTE_CI':
                raise ValueError('terminal requires actual immutable remote CI baseline provenance')
            manager = guard.verify_manager(args.manager.resolve())
            if args.mode == 'rust':
                manifest_raw, source = fetch_inference_payload(args.destination.resolve())
                candidate = load_candidate(manifest_raw, source, baseline)
                current = verify_inference_candidate(args.destination.resolve(), candidate)
            else:
                current = guard.verify_materialized(args.destination.resolve(), baseline)
            result.update(verify_compiler_result(record, args.mode, file.parent, current, manager, helper['manager_commit']))
        else:
            manifest_raw, source = fetch_inference_payload(args.destination.resolve())
            candidate = load_candidate(manifest_raw, source, baseline)
            if args.operation == 'apply':
                result.update(apply_inference_overlay(args.destination.resolve(), baseline, manifest_raw, source))
            else:
                result.update(verify_inference_candidate(args.destination.resolve(), candidate))
        result.update(helper)
        result['passed'] = True
    except BaseException as error:
        result['error_type'] = type(error).__name__
        result['error'] = str(error)
        primary = error
    try:
        guard.write_receipt(args.receipt, result)
    except BaseException as receipt_error:
        if primary is not None:
            raise BaseExceptionGroup('Original overlay failure and receipt failure both preserved.', [primary, receipt_error])
        raise
    if primary is not None:
        raise primary


if __name__ == '__main__':
    main()
