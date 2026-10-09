#!/usr/bin/env python3
"""Fixed17 native-source union; compiler/data only, never native authority."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import windows_foundation_source_guard as guard
import windows_foundation_inference_overlay as original_overlay

TARGET = '4d42a21057b867e6163e6bbe3ce9edca24da5716'
BACKUP = '833e7b4401ffb15b3ce042a6fb56e6a9ced48ba6'
PREFIX = 'development-backups/rc070/20261009/checkpoint-91/'
MANIFEST_NAME = 'CANDIDATE-FULL1967-MANIFEST01.json'
MANIFEST_SHA = '57bcdfae55407031c00a2b96cca9472880823ac48ab3a4e24b7a57a2d4fe07f6'
MANIFEST_BYTES = 516400
TARGET_FILES = 1967
HELPER = 'scripts/windows_foundation_union_overlay.py'
LEAF_TABLE = ({'path': 'services/windows-vm-broker/output_transfer.go', 'mode': '100644', 'sha256': 'e52bb1feb1724a03b1ca352b024ab3f3e93cd5c72bd7ca7595e1f69129e18997', 'blob': '537fe795ab4b8ea21c80c15eae7bd27dab32d7b0', 'bytes': 2137}, {'path': 'services/windows-vm-broker/output_transfer_test.go', 'mode': '100644', 'sha256': '76a4a8db6b5afe6d85dd985228e7b70e6dc8af7199ece876ea95c5a824af155b', 'blob': '9396417698bf0556166a5addde83cac71e6aa25a', 'bytes': 8432}, {'path': 'docs/specs/windows-output-data-recreated/requirements.md', 'mode': '100644', 'sha256': 'b05007f10f40d58ae72063fc36508e4721ba6e63b8a0017ed5cd0c29ab6f7fe1', 'blob': 'dc90f748fcf469f5a6a64eda002d0b9b0960f1bc', 'bytes': 1998}, {'path': 'docs/specs/windows-output-data-recreated/design.md', 'mode': '100644', 'sha256': '31798a40eaf6135003be95025f935b3b1c5b77e9db3f6e174acc6c554c412a6e', 'blob': 'f67e22c0613a6ba711fba29c8e39ff049a0ef4fb', 'bytes': 2066}, {'path': 'docs/specs/windows-output-data-recreated/tasks.md', 'mode': '100644', 'sha256': '224af77267befbb8c0cd907e25c3b82c11deb247a6dfe897badba40b08a357a5', 'blob': '9cbda30b654e2184a7077c393d380359de301e79', 'bytes': 1409}, {'path': 'services/windows-vm-broker/transfer.go', 'mode': '100644', 'sha256': 'a29d443756e783584f42ef2aad9b8bb2f25cf17fe82b72c132475b22ec9236e3', 'blob': '1f4432acbe6b44d6bf6969584a69f68d5fca5afa', 'bytes': 5494}, {'path': 'services/windows-vm-broker/transfer_owner_test.go', 'mode': '100644', 'sha256': 'e691fae89dd8223b0dae56a79c8b45a68d84a609a32d7948dfd5c2d03b8dc160', 'blob': '26b087d8e93446e13bead8d5d3b6ac3dd4987681', 'bytes': 4065}, {'path': 'docs/specs/windows-input-data-once/requirements.md', 'mode': '100644', 'sha256': '7763a7a17d5bdfc0ab58314d677f909807db7c9eeeb6f5eb7be193fee4c54fe2', 'blob': '42815a43d421fa025f27a2539d0d1b0319483449', 'bytes': 2299}, {'path': 'docs/specs/windows-input-data-once/design.md', 'mode': '100644', 'sha256': '7f2a307c937769879e5c4bc7c3aac877bd138a0adf5a88f2d76ded401d986133', 'blob': '99cc424d29e570fc678f853ed51cecc4ca581f44', 'bytes': 1239}, {'path': 'docs/specs/windows-input-data-once/tasks.md', 'mode': '100644', 'sha256': 'f438795076e9418426502380c627ae50a9ba8d9bd6834bc83f275b7a98923906', 'blob': '06756a3582c2c930889080cd956ec36de10f0129', 'bytes': 1132}, {'path': 'src-tauri/src/tools/windows_vm/output_stage/data.rs', 'mode': '100644', 'sha256': '9c03dc93a7223975877096a0ca280d558f9af62ff48d7a048be664c85f938c90', 'blob': '2823d75b38960fff503215ae528db89d32b89f51', 'bytes': 6670}, {'path': 'src-tauri/src/tools/windows_vm/output_stage/data_tests.rs', 'mode': '100644', 'sha256': 'd469e670979abe5395fae1b07fbb640182df7390c7b296e0a3febf8e4ed784e6', 'blob': '9d6eada4016d146fff7d754a8ccc70effab79332', 'bytes': 12329}, {'path': 'src-tauri/src/tools/windows_vm/output_stage/mod.rs', 'mode': '100644', 'sha256': '16157e26bf2a659a967b3d4b65f304ca209f947483dc6fc90a0e265fa49f593b', 'blob': '52292b3ab93e7b5c21c51e5605284698c474f800', 'bytes': 504}, {'path': 'docs/specs/windows-rust-output-data-recreated/requirements.md', 'mode': '100644', 'sha256': '2d6fe7dfdfd29aa826ee762ad9faeaed03d0e3e55303f85f9aaa980adb8213d6', 'blob': '227ad410272e0bf8ebd232563e8f54b7193a5da2', 'bytes': 4614}, {'path': 'docs/specs/windows-rust-output-data-recreated/design.md', 'mode': '100644', 'sha256': '47740c9fc39c49de153edc4c74a68d6b3f690ddd187cabfe898e0f8f3a82781a', 'blob': '27d72a19eec566664efd38d585c2464d7d88f90a', 'bytes': 3546}, {'path': 'docs/specs/windows-rust-output-data-recreated/tasks.md', 'mode': '100644', 'sha256': '917ee254794cca021620de1b90d773c3438b644c983714cf53f4cce31266fb00', 'blob': '7cf00dad695a2a5d3fdb69ec7f4a7ab56708c7e1', 'bytes': 2601}, {'path': 'src-tauri/src/tools/windows_vm/input/owned_run/hcs.rs', 'mode': '100644', 'sha256': 'd22b143b6b199e743b19bf931b50358cfac9fcc761704d81139e87a6c07ade00', 'blob': '5b2626f0dde7cd96b4af77ff6715a7bd9ec55ef5', 'bytes': 7163})
RUST_CASES = ('tools::windows_vm::input::chunk_tests::sealed_chunks_keep_original_and_detached_owners_independent', 'tools::windows_vm::input::chunk_tests::chunk_cap_and_cancel_do_not_publish_partial_copy', 'tools::windows_vm::input::transfer_tests::exact_transfer_binding_rejects_each_field_mismatch', 'tools::windows_vm::input::transfer_tests::invalid_wire_names_and_nil_binding_never_make_native_authority', 'tools::windows_vm::input::publication_tests::checked_close_consumes_data_only_transfer', 'tools::windows_vm::input::tests::relative_names_remain_data_not_native_permission', 'tools::windows_vm::output_stage::tests::diagnostic_metadata_cannot_authorize_output', 'tools::windows_vm::output_stage::data::data_tests::output_direction_capacity_and_roundtrip', 'tools::windows_vm::output_stage::data::data_tests::output_binding_fields_and_terminal_foreign_attempt', 'tools::windows_vm::output_stage::data::data_tests::output_header_sequence_offset_digest_and_EOF_reject', 'tools::windows_vm::output_stage::data::data_tests::output_cancel_reader_error_and_blocked_reader_boundary', 'tools::windows_vm::output_stage::data::data_tests::output_clone_and_concurrent_once', 'tools::windows_vm::output_stage::data::data_tests::output_mutex_poison_remains_denied', 'tools::windows_vm::output_stage::data::data_tests::output_go_golden_vector_is_exact')
GO_FILES = ('services/windows-vm-broker/transfer.go', 'services/windows-vm-broker/transfer_test.go', 'services/windows-vm-broker/transfer_identity_linux_test.go', 'services/windows-vm-broker/workspace_stream.go', 'services/windows-vm-broker/workspace_stream_test.go', 'services/windows-vm-broker/guest_workspace_control.go', 'services/windows-vm-broker/output_transfer.go', 'services/windows-vm-broker/output_transfer_test.go', 'services/windows-vm-broker/transfer_owner_test.go')
GO_CASES = ('TestTransferAllBindingFieldsChangeDigest', 'TestTransferBoundEOFHashCancellationAndSingleConsumption', 'TestTransferRelativeAndMalformedIdentityReject', 'TestLinuxTransferCannotIssueNativeFileIdentity', 'TestWorkspaceRustGoCanonicalVector', 'TestWorkspaceExactZeroAndOneMiBBudgets', 'TestWorkspaceEveryHeaderDimensionPermanentlyPoisons', 'TestWorkspaceTruncationTrailingReplayAndFinalDigestReject', 'TestWorkspaceAllocationBoundCancellationAndChunkFailure', 'TestWorkspaceInputOutputDirectionAndMissingTrustedManifestReject', 'TestWorkspaceConcurrentCancellationWhileDecoderCallbackIsBlocked', 'TestOutputTransferExactDirectionBudgetsAndDetachedBytes', 'TestOutputTransferEveryBindingFieldRejectsForeignWire', 'TestOutputTransferPhysicalEOFHashAndReplayReject', 'TestOutputTransferCancelledNilAndCorruptOwnersAreTerminal', 'TestOutputTransferConcurrentConsumersHaveOnlyOneSuccess', 'TestOutputTransferValueCopiesShareTerminalConsumption', 'TestOutputTransferConcurrentValueCopiesHaveOnlyOneSuccess', 'TestInputDataValueCopyCannotConsumeTwice', 'TestInputDataConcurrentConsumptionIsOnce', 'TestInputDataCopiesCannotRedirectBindingOrPayload', 'TestInputDataCopiedContextCannotReviveCancellation', 'TestInputDataConcurrentValueCopiesHaveOneSuccess')

def verify_union_helper_leases(manager):
    older = original_overlay.verify_helper_lease(manager)
    expected = older['manager_commit']
    rows = [row for row in guard.tree_rows(manager, expected) if row['path'] == HELPER]
    if len(rows) != 1 or rows[0]['mode'] != '100644':
        raise ValueError('union helper current native source mode/path missing')
    file = manager / HELPER
    if file.is_symlink() or not file.is_file():
        raise ValueError('union helper absent or symlink')
    data = file.read_bytes()
    row = dict(rows[0], bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    guard.check_blob(data, row)
    if os.name != 'nt' and file.stat().st_mode & 0o111:
        raise ValueError('union helper physical executable mode changed')
    sources = sorted([older['helper_source'], row], key=lambda value: value['path'])
    digest = hashlib.sha256(json.dumps(sources, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'manager_commit': expected, 'helper_sources': sources, 'helper_digest': digest,
            'native_authority': False}


def fetch_union_payload(repo):
    guard.run_git(repo, 'fetch', '--no-tags', guard.REPOSITORY, BACKUP)
    if guard.run_git(repo, 'cat-file', '-t', BACKUP).strip() != b'commit':
        raise ValueError('union payload is not the fixed native immutable commit')
    native = {row['path']: row for row in guard.tree_rows(repo, BACKUP)}
    path = PREFIX + MANIFEST_NAME
    if path not in native or native[path]['mode'] != '100644':
        raise ValueError('union manifest immutable native path/mode differs')
    raw = guard.run_git(repo, 'show', BACKUP + ':' + path)
    guard.check_blob(raw, dict(native[path], bytes=MANIFEST_BYTES, sha256=MANIFEST_SHA))
    sources = {}
    for row in LEAF_TABLE:
        name = PREFIX + 'source/' + row['path'] + '.source'
        entry = native.get(name)
        if entry is None or entry['mode'] != '100644' or entry['blob'] != row['blob']:
            raise ValueError('union literal payload native path/mode/blob differs')
        data = guard.run_git(repo, 'show', BACKUP + ':' + name)
        guard.check_blob(data, row)
        sources[row['path']] = data
    return raw, sources


def load_union_candidate(manifest_raw, sources, baseline):
    if len(manifest_raw) != MANIFEST_BYTES or hashlib.sha256(manifest_raw).hexdigest() != MANIFEST_SHA:
        raise ValueError('union manifest literal SHA/size differs')
    m = json.loads(manifest_raw.decode('utf-8'))
    if set(m) != {'baselineTree', 'tree', 'files'} or m['baselineTree'] != guard.TARGET or m['tree'] != TARGET:
        raise ValueError('union manifest source identity differs')
    rows = m['files']
    if not isinstance(rows, list) or len(rows) != TARGET_FILES or len({row['path'] for row in rows}) != TARGET_FILES:
        raise ValueError('union whole1967 rows missing or duplicate')
    old = {row['path']: row for row in baseline['whole_source']}
    if len(old) != 1953:
        raise ValueError('original baseline missing1953 unique rows')
    leaves = {row['path']: row for row in LEAF_TABLE}
    if len(leaves) != 17 or set(sources) != set(leaves):
        raise ValueError('union literal17 source payload vector differs')
    expected = dict(old)
    expected.update(leaves)
    if len(expected) != TARGET_FILES or rows != [expected[path] for path in sorted(expected)]:
        raise ValueError('union full source is not exact17 change preserving1950')
    if sum(path in old for path in leaves) != 3 or sum(old.get(path) != row for path, row in leaves.items()) != 17:
        raise ValueError('union expected3 changed/14new identity differs')
    for row in rows:
        guard.safe_path(row['path'])
        if set(row) != {'path', 'mode', 'blob', 'bytes', 'sha256'} or row['mode'] not in ('100644', '100755'):
            raise ValueError('union row shape/mode differs')
        if type(row['bytes']) is not int or row['bytes'] < 0 or not re.fullmatch('[0-9a-f]{40}', row['blob']) or not re.fullmatch('[0-9a-f]{64}', row['sha256']):
            raise ValueError('union row size/hash malformed')
    for row in LEAF_TABLE:
        guard.check_blob(sources[row['path']], row)
    return m


def verify_union_candidate(repo, m):
    if guard.run_git(repo, 'rev-parse', 'HEAD').decode().strip() != guard.BASE:
        raise ValueError('union source HEAD is not original D6')
    actual = guard.run_git(repo, 'write-tree', index=True).decode().strip()
    if actual != TARGET:
        raise ValueError('union actual custom native index tree differs')
    rows = m['files']
    if guard.tree_rows(repo, actual) != [{key: row[key] for key in ('path', 'mode', 'blob')} for row in rows]:
        raise ValueError('union actual full native1967 source differs')
    digest = hashlib.sha256()
    for row in rows:
        guard.safe_path(row['path'])
        file = repo / row['path']
        if file.is_symlink() or not file.is_file():
            raise ValueError('union actual source absent or symlink')
        data = file.read_bytes()
        guard.check_blob(data, row)
        if os.name != 'nt' and bool(file.stat().st_mode & 0o111) != (row['mode'] == '100755'):
            raise ValueError('union physical executable classification differs')
        digest.update(row['path'].encode() + b'\0' + row['mode'].encode() + b'\0' + row['sha256'].encode() + b'\n')
    if hashlib.sha256((repo / guard.PROTECTED).read_bytes()).hexdigest() != guard.PROTECTED_SHA:
        raise ValueError('union protected original positive changed')
    if (repo / 'src-tauri/src/tools/cloud_host/windows_workspace/stage.rs').exists():
        raise ValueError('blocked Stage11 source present')
    if any(guard.run_git(repo, 'ls-files', '--others', '--exclude-standard', '-z', index=True).split(b'\0')):
        raise ValueError('union untracked source outside original ignored build output')
    return {'tree': actual, 'files': TARGET_FILES, 'source_digest': digest.hexdigest(),
            'protected_positive_sha256': guard.PROTECTED_SHA, 'native_positive': 'NOTRUN', 'native_authority': False}


def apply_union_overlay(repo, baseline, manifest_raw, sources):
    # The original1953 verifier runs only on the actual baseline, before any17write.
    guard.verify_materialized(repo, baseline)
    m = load_union_candidate(manifest_raw, sources, baseline)
    for row in LEAF_TABLE:
        data = sources[row['path']]
        blob = guard.run_git(repo, 'hash-object', '-w', '--stdin', data=data).decode().strip()
        if blob != row['blob']:
            raise ValueError('union native written source blob differs')
        guard.run_git(repo, 'update-index', '--add', '--cacheinfo', row['mode'] + ',' + blob + ',' + row['path'], index=True)
    if guard.run_git(repo, 'write-tree', index=True).decode().strip() != TARGET:
        raise ValueError('union native17 overlay tree differs before materialization')
    guard.run_git(repo, 'checkout-index', '--force', '--', *[row['path'] for row in LEAF_TABLE], index=True)
    return verify_union_candidate(repo, m)


def verify_union_compiler_result(record, mode, directory, current_source, current_manager, current_commit, current_helpers, manager_root, destination, ordinary_profile=False):
    if type(ordinary_profile) is not bool:
        raise ValueError('consumer ordinary profile must be an exact boolean')
    if not all(isinstance(path, Path) and path.is_absolute() for path in (directory, manager_root, destination)):
        raise ValueError('consumer requires explicit absolute caller paths')
    baseline_profile = record.get('sourceBaseline', {}).get('payload_mode')
    if ordinary_profile:
        if (mode != 'go' or baseline_profile != 'LOCAL_OWNED_COMPONENT' or
                record.get('componentContext') != 'ACTUAL_OWNED_GO23_NOT_CI' or
                os.environ.get('GITHUB_ACTIONS') != 'false'):
            raise ValueError('consumer ordinary profile requires actual non-CI owned Go local source')
    elif baseline_profile != 'IMMUTABLE_REMOTE_CI' or record.get('componentContext') is not None:
        raise ValueError('consumer production profile denies local/component provenance')
    target = TARGET
    compiler = 'WHOLE_TEST_COMPILE_AND_14_DATA_PASS' if mode == 'rust' else 'DATA_23_RACE_TEST_PASS'
    if mode not in ('rust', 'go') or record.get('passed') is not True or record.get('mode') != mode:
        raise ValueError('consumer requires exact mode and boolean passed')
    if (record.get('compiler') != compiler or record.get('pureSutTree') != target or
            record.get('baselineSutTree') != guard.TARGET or record.get('managerCommit') != current_commit or
            record.get('nativePositive') != 'NOTRUN' or record.get('qualification') != 'SOURCE_ONLY_BLOCKED' or
            record.get('managerObservationFailed') is not False):
        raise ValueError('consumer terminal/compiler identity differs')
    if any(re.search('error|cancel|unknown|skipped', key, re.I) for key in record):
        raise ValueError('consumer interrupted/unknown/error receipt denied')
    if record.get('sourceOverlayStarted') is not True:
        raise ValueError('union overlay was not admitted for exact current mode')
    if record.get('runId') != os.environ.get('GITHUB_RUN_ID', '') or not re.fullmatch('[0-9]+', str(record.get('runId', ''))):
        raise ValueError('consumer actual current run identity differs')
    baseline = record.get('sourceBaseline', {})
    if (baseline.get('passed') is not True or baseline.get('tree') != guard.TARGET or
            type(baseline.get('files')) is not int or baseline['files'] != 1953 or
            baseline.get('native_authority') is not False or
            baseline.get('protected_positive_sha256') != guard.PROTECTED_SHA):
        raise ValueError('consumer original full baseline absent')
    for key in ('sourceBefore', 'sourceAfter'):
        source = record.get(key, {})
        if (source.get('passed') is not True or source.get('tree') != target or
                type(source.get('files')) is not int or source['files'] != TARGET_FILES or
                source.get('native_authority') is not False or source.get('native_positive') != 'NOTRUN' or
                source.get('source_digest') != current_source['source_digest'] or
                source.get('protected_positive_sha256') != guard.PROTECTED_SHA):
            raise ValueError('consumer whole source before/after differs')
        if (source.get('helper_sources') != current_helpers['helper_sources'] or
                source.get('helper_digest') != current_helpers['helper_digest'] or
                source.get('manager_commit') != current_commit):
            raise ValueError('consumer current original/new helper leases differ')
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
        original_overlay.read_result_log(directory, name)
        by_log[name] = command
    guard_path = str(manager_root / 'scripts/windows_foundation_source_guard.py')
    manifest_path = str(manager_root / 'scripts/windows_foundation_source_manifest.json')
    observer_path = str(manager_root / 'scripts/windows_foundation_manager_observation.py')
    union_path = str(manager_root / HELPER)
    root = str(manager_root)
    sut = str(destination)
    baseline_args = ([guard_path, 'verify', '--manifest', manifest_path, '--destination', sut,
                      '--receipt', str(directory / 'source-before.json')] if ordinary_profile else
                     [guard_path, 'restore', '--manifest', manifest_path, '--manager', root,
                      '--destination', sut, '--receipt', str(directory / 'source-before.json')])
    expected_commands = [
        ('git', 'git-version.log', ['--version']),
        ('python', 'python-version.log', ['-c',
         'import sys; assert sys.version_info[:2] == (3, 12), sys.version; print(sys.version)']),
        ('python', 'management-byte-observation-Before.log',
         [observer_path, '--manager', root, '--receipt', str(directory / 'management-byte-observation-Before.json')]),
        ('python', 'management-before.log', [guard_path, 'verify-manager', '--manifest', manifest_path,
         '--manager', root, '--receipt', str(directory / 'management-before.json')]),
        ('python', 'source-restore.log', baseline_args),
        ('python', 'candidate-source-overlay.log', [union_path, 'apply', '--manifest', manifest_path,
         '--manager', root, '--destination', sut, '--receipt', str(directory / 'candidate-source-before.json')]),
    ]
    if mode == 'go':
        expected_commands += [('go', 'go-version.log', ['version']),
                              ('go', 'go9-data-race-test.log', ['test', '-race', '-v', '-count=1', *GO_FILES])]
    else:
        expected_commands += [('rustup', 'rustup-which-before-' + tool + '.log',
                               ['which', '--toolchain', '1.98.1', tool]) for tool in ('rustc', 'cargo')]
        expected_commands += [
            ('rustc', 'rustc-version.log', ['--version', '--verbose']),
            ('cargo', 'cargo-version.log', ['--version', '--verbose']),
            ('cargo', 'cargo-whole-test-compile.log', [*original_overlay.CARGO_VECTOR, '--no-run']),
            ('cargo', 'cargo-whole-test-list.log', [*original_overlay.CARGO_VECTOR, '--', '--list']),
        ]
        expected_commands += [('cargo', 'data-' + case.rsplit('::', 1)[1] + '.log',
                               [*original_overlay.CARGO_VECTOR, case, '--', '--exact', '--nocapture', '--test-threads=1'])
                              for case in RUST_CASES]
    expected_commands += [
        ('python', 'source-after.log', [union_path, 'verify', '--manifest', manifest_path, '--manager', root,
         '--destination', sut, '--receipt', str(directory / 'source-after.json')]),
        ('python', 'management-after.log', [guard_path, 'verify-manager', '--manifest', manifest_path,
         '--manager', root, '--receipt', str(directory / 'management-after.json')]),
        ('python', 'management-byte-observation-After.log',
         [observer_path, '--manager', root, '--receipt', str(directory / 'management-byte-observation-After.json')]),
    ]
    actual_commands = [(command['executable'], command['log'], command['arguments']) for command in commands]
    if any(any(type(argument) is not str for argument in arguments) for _, _, arguments in actual_commands):
        raise ValueError('consumer exact command argv requires strings')
    if mode == 'go':
        if actual_commands != expected_commands:
            raise ValueError('consumer complete exact command transcript differs')
    else:
        after_rustc = ('rustup', 'rustup-which-after-rustc.log', ['which', '--toolchain', '1.98.1', 'rustc'])
        after_cargo = ('rustup', 'rustup-which-after-cargo.log', ['which', '--toolchain', '1.98.1', 'cargo'])
        # The original Hashtable runtime loop allows only these two final permutations.
        if actual_commands not in (expected_commands + [after_rustc, after_cargo],
                                   expected_commands + [after_cargo, after_rustc]):
            raise ValueError('consumer complete exact command transcript differs')
    if mode == 'go':
        if [c['log'] for c in commands if c['executable'] == 'go'] != ['go-version.log', 'go9-data-race-test.log']:
            raise ValueError('consumer original Go command vector differs')
        if by_log['go-version.log']['arguments'] != ['version'] or not original_overlay.read_result_log(directory, 'go-version.log').startswith('go version go1.24.13 linux/amd64'):
            raise ValueError('consumer pinned Go version differs')
        if by_log['go9-data-race-test.log']['arguments'] != ['test', '-race', '-v', '-count=1', *GO_FILES]:
            raise ValueError('consumer original Go five-source vector differs')
        log = original_overlay.read_result_log(directory, 'go9-data-race-test.log')
        names = re.findall(r'^--- PASS: ([A-Za-z0-9_]+) \(', log, re.M)
        runs = re.findall(r'^=== RUN   ([A-Za-z0-9_]+)\r?$', log, re.M)
        if len(names) != 23 or len(runs) != 23 or set(names) != set(GO_CASES) or set(runs) != set(GO_CASES) or 'DATA RACE' in log or not re.search(r'^PASS\r?$', log, re.M):
            raise ValueError('consumer original Go four unique success identities absent')
    else:
        needed = ['cargo-whole-test-compile.log', 'cargo-whole-test-list.log', *['data-' + case.rsplit('::', 1)[1] + '.log' for case in RUST_CASES]]
        cargo = [c for c in commands if c['executable'] == 'cargo' and c['log'] != 'cargo-version.log']
        if [c['log'] for c in cargo] != needed:
            raise ValueError('consumer original Rust command order/vector differs')
        if cargo[0]['arguments'] != [*original_overlay.CARGO_VECTOR, '--no-run'] or cargo[1]['arguments'] != [*original_overlay.CARGO_VECTOR, '--', '--list']:
            raise ValueError('consumer whole library compile/list command differs')
        listed = original_overlay.read_result_log(directory, needed[1]).splitlines()
        for full, command in zip(RUST_CASES, cargo[2:]):
            if listed.count(full + ': test') != 1:
                raise ValueError('consumer exact fullyqualified Rust case absent/duplicate')
            if command['arguments'] != [*original_overlay.CARGO_VECTOR, full, '--', '--exact', '--nocapture', '--test-threads=1']:
                raise ValueError('consumer original Rust unique exact command differs')
            log = original_overlay.read_result_log(directory, command['log'])
            if len(re.findall(r'^test ' + re.escape(full) + r' \.\.\. ok\r?$', log, re.M)) != 1 or not re.search(r'test result: ok\. 1 passed; 0 failed; 0 ignored; 0 measured; [0-9]+ filtered out', log):
                raise ValueError('consumer actual exact Rust success log absent')
    result = {'passed': True, 'mode': mode, 'tree': target, 'files': TARGET_FILES,
              'named_data_count': 14 if mode == 'rust' else 23, 'native_authority': False,
              'native_positive': 'NOTRUN', 'qualification': 'COMPILER_DATA_ONLY'}
    if ordinary_profile:
        result.update(qualification='OWNED_COMPONENT_ONLY', ci=False, qualified=False)
    return result
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
              'baseline_tree': guard.TARGET, 'target_tree': TARGET, 'backup_commit': BACKUP}
    primary = None
    try:
        helper = verify_union_helper_leases(args.manager.resolve())
        baseline = guard.load_manifest(args.manifest.resolve())
        manifest_raw, sources = fetch_union_payload(args.destination.resolve())
        candidate = load_union_candidate(manifest_raw, sources, baseline)
        if args.operation == 'verify-result':
            if args.mode is None or args.compiler_result is None:
                raise ValueError('union terminal consumer requires mode and actual receipt')
            file = args.compiler_result
            if file.is_symlink() or not file.is_file() or file.stat().st_size > 2 * 1024 * 1024:
                raise ValueError('union terminal producer receipt missing or unbounded')
            record = json.loads(file.read_text(encoding='utf-8-sig'))
            if record.get('sourceBaseline', {}).get('payload_mode') != 'IMMUTABLE_REMOTE_CI':
                raise ValueError('union terminal requires actual immutable remote baseline provenance')
            manager = guard.verify_manager(args.manager.resolve())
            current = verify_union_candidate(args.destination.resolve(), candidate)
            result.update(verify_union_compiler_result(record, args.mode, file.parent, current, manager,
                                                       helper['manager_commit'], helper, args.manager.resolve(), args.destination.resolve(),
                                                       ordinary_profile=False))
        elif args.operation == 'apply':
            result.update(apply_union_overlay(args.destination.resolve(), baseline, manifest_raw, sources))
        else:
            result.update(verify_union_candidate(args.destination.resolve(), candidate))
        after_helper = verify_union_helper_leases(args.manager.resolve())
        if after_helper != helper:
            raise ValueError('union original/new helper native source changed during invocation')
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
            raise BaseExceptionGroup('Original union failure and receipt failure both preserved.', [primary, receipt_error])
        raise
    if primary is not None:
        raise primary
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
