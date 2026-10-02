#!/usr/bin/env python3
"""Exact-source focused engineering evidence. Never authorize a release."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import sys
import unittest

import exact_build_audit as exact

REPOSITORY = 'Eswink/coding-tools-mcp'
BRANCH = 'ci/rc-source-assembly-v2-20261001'
WORKFLOW = REPOSITORY + '/.github/workflows/rc-source-assembly.yml@refs/heads/' + BRANCH
ANCHOR = '049ff5d381f345bf681ac3501b952269531b7045'
ANCHOR_TREE = '4e55549810e74236e14eb28a48785c3268ae107d'
FIRST_MERGE = 'c959ef5e6e9913ccb5eeb3139e7d7ecb72358378'
LEGACY_IMPLEMENTATION = '46f88c60f3a5f8726e4c28cee73e941a7f15a36d'
LEGACY_TREE = '1412f9e1408b1dbb7beefa2db37f70b5965fea65'
DISPATCH_TESTS = 'scripts/rc_source_assembly_dispatch_tests.py'
PR96 = '43cc4fcfcee45b65be6faa79c33fedc3dce2407c'
PR93 = 'bd3053eca83cb0fcc07468abb3b81bf6fada1bcf'
PR94 = 'e26e36aedb7db7458adbf17ec5185b998e5641f7'
METADATA_BASE = 'e61aaf2da99baccdb99db4922b39f7d8d5997096'
COMPONENTS = {
    PR96: ('3ddac4a2aacb718a9113b31eb0513713f5c525bb', ['e2a0e08fe490a18f9aa60efc400b60c9dbe22c89']),
    PR93: ('a12999503397d7ad13e8f1ec198b3c84c17e484a', ['171e8e87b735800a629049ddc35c563f748f73f2']),
    PR94: ('51c00c50e05b4c2cf5fb25029bbe8a4f380fdf95', ['171e8e87b735800a629049ddc35c563f748f73f2']),
    FIRST_MERGE: ('7355b842eb2b266de8da4424f30c9d0e2b11bc31', [PR96, PR93]),
    ANCHOR: (ANCHOR_TREE, [FIRST_MERGE, PR94]),
}
SPEC = 'docs/specs/rc-source-assembly-engineering/'
ADDED = {'.github/workflows/rc-source-assembly.yml', 'scripts/rc_source_assembly.py',
         'scripts/rc_source_assembly_frontend.py', 'scripts/rc_source_assembly_tests.py',
         'scripts/rc_source_assembly_evidence_tests.py', DISPATCH_TESTS}
ADDED |= {SPEC + p for p in ('README.md', 'requirements.md', 'design.md', 'tasks.md', 'spec-manifest.json',
          'subspecs/source-evidence/spec.md', 'subspecs/source-evidence/tasks.md',
          'subspecs/focused-validation/spec.md', 'subspecs/focused-validation/tasks.md')}
MODIFIED = {'scripts/engineering_dependency_capture.py'}
SCOPE = ADDED | MODIFIED
LEGACY_ADDED = ADDED - {DISPATCH_TESTS}
FLAGS = dict(engineering_only=True, release_approved=False, publish_approved=False,
             native_verified=False, real_chatgpt_verified=False, full_release_eligible=False)
BINS = {'coding-tools-gateway': 'identity-only', 'coding-tools-agent': 'recovery-only',
        'coding-tools-control-gateway': 'control-only', 'coding-tools-mcp-gateway': 'control-plane'}
UNITS = {'src-tauri': ('src-tauri', 'coding-tools-mcp-desktop', '0.7.0-rc.1'),
         'cloud-gateway': ('services/cloud-gateway', 'coding-tools-cloud-gateway', '0.7.0-rc.1'),
         'cloud-agent': ('services/cloud-agent', 'coding-tools-cloud-agent', '0.1.0'),
         'local-agent': ('services/local-agent', 'coding-tools-local-agent', '0.1.0')}


# Exact YAML-decoded bodies of the six shell blocks in the reviewed workflow.
# No whitespace normalization: CR, quoting and shell line boundaries affect execution.
SHELL_DIGESTS = {
    'release-contracts': 'd4e2a306b2ca21829672cf66b2d7852f08759a283f3daebb233906aaa646c966',
    'metadata': '6f6875f063d31367e9c5fb0ab5c84f1dd790ccb452099437999a8cfe98af0929',
    'native-dependencies': 'e141b1466e7c2368bf51654e1180c95aa23abee8bf3599fd26fed1cf2cee4e2a',
    'native-compile': '9600bb5459a69c53b55f01803e757c43ed0a28133b8c3566baca07fcd0d50f8c',
    'stdin': 'e3db98adf046a3f18a6a0931bf18b1c7f36231fb9e77355cf3a7075caf1a46f0',
    'capture-contracts': '413dde603c1e8c3883a794592d263789c540a7f0b892d1a329fd7407315b383a',
}
RELEASE_SUITES = ('rc_version_gate_tests release_preflight_tests cloud_release_bundle_tests rc_packages_tests '
                  'source_provenance_gate_tests reviewed_source_gate_tests release_tag_gate_tests 发布版本回归v4 '
                  'preliminary_package_contract_tests rc_windows_install_contract_tests rc_source_assembly_tests '
                  'rc_source_assembly_evidence_tests rc_source_assembly_dispatch_tests').split()
CAPTURE_SUITES = ['engineering_dependency_capture_tests', 'release_dependency_capture_tests',
                  'release_dependency_contract_tests', 'exact_build_audit_tests']
PORTABLE_COUNTS = {'Linux': {'portable-standalone': [50, 23], 'portable-rc': [50, 11, 23]},
                   'Windows': {'portable-standalone': [49, 18], 'portable-rc': [49, 10, 18]}}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root, text=True, timeout=30).strip()


def tree_files(root, revision):
    raw = subprocess.check_output(['git', 'ls-tree', '-rz', '--full-tree', revision], cwd=root, timeout=30)
    result = {}
    for entry in raw.decode().split('\0'):
        if entry:
            identity, name = entry.split('\t', 1)
            mode, kind, blob = identity.split()
            exact.need(kind == 'blob' and mode == '100644', 'nonregular_source_entry')
            result[name] = {'mode': mode, 'git_blob': blob}
    return result


def verify_history(root, sha):
    exact.need(re.fullmatch('[0-9a-f]{40}', sha) and git(root, 'rev-parse', 'HEAD') == sha, 'wrong_head')
    for commit, (tree, parents) in COMPONENTS.items():
        exact.need(git(root, 'rev-parse', commit + '^{tree}') == tree and
                   git(root, 'show', '-s', '--format=%P', commit).split() == parents, 'wrong_reviewed_component')
    chain = git(root, 'rev-list', '--reverse', sha, '^' + ANCHOR).splitlines()
    exact.need(1 <= len(chain) <= 32, 'invalid_descendant_count')
    exact.need(chain[0] == LEGACY_IMPLEMENTATION, 'wrong_legacy_implementation')
    before = tree_files(root, ANCHOR)
    previous, records = ANCHOR, []
    for commit in chain:
        exact.need(git(root, 'show', '-s', '--format=%P', commit).split() == [previous], 'nonlinear_or_foreign_history')
        after = tree_files(root, commit)
        added = LEGACY_ADDED if commit == LEGACY_IMPLEMENTATION else ADDED
        tree = git(root, 'rev-parse', commit + '^{tree}')
        exact.need(commit != LEGACY_IMPLEMENTATION or tree == LEGACY_TREE, 'wrong_legacy_tree')
        exact.need(set(after) - set(before) == added and set(before) - set(after) == set(), 'wrong_added_removed_paths')
        changed = {p for p in before if before[p] != after[p]}
        exact.need(changed == MODIFIED, 'protected_source_changed')
        records.append({'sha': commit, 'parent': previous, 'tree': tree,
                        'delta_blobs': {p: after[p] for p in sorted(added | MODIFIED)}})
        previous = commit
    exact.need(previous == sha, 'head_not_in_chain')
    return records


def verify_source(root, sha):
    root = root.resolve(strict=True)
    env = os.environ
    expected = {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': REPOSITORY,
                'GITHUB_REF': 'refs/heads/' + BRANCH, 'GITHUB_EVENT_NAME': 'push',
                'GITHUB_WORKFLOW_REF': WORKFLOW, 'GITHUB_SHA': sha}
    exact.need(all(env.get(k) == v for k, v in expected.items()), 'wrong_assembly_producer')
    workflow_sha = env.get('GITHUB_WORKFLOW_SHA', env.get('WORKFLOW_SHA'))
    exact.need(workflow_sha == sha and env.get('WORKFLOW_SHA', sha) == sha, 'wrong_workflow_sha')
    for key in ('GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'):
        exact.need(re.fullmatch('[1-9][0-9]*', env.get(key, '')), 'invalid_' + key.lower())
    job = env.get('GITHUB_JOB')
    allowed = {'portable': {'ubuntu-22.04', 'ubuntu-24.04', 'windows-2025'},
               'native': {'ubuntu-22.04', 'ubuntu-24.04'},
               'capture': {'ubuntu-24.04'}, 'verify': {'ubuntu-24.04'}}
    exact.need(job in allowed, 'wrong_assembly_job')
    matrix_os = env.get('ASSEMBLY_MATRIX_OS')
    exact.need(matrix_os in allowed[job], 'invalid_assembly_matrix_os')
    expected_runner = 'Windows' if matrix_os == 'windows-2025' else 'Linux'
    exact.need(env.get('RUNNER_OS') == expected_runner, 'matrix_runner_os_mismatch')
    event = exact.decode(exact.read(Path(env.get('GITHUB_EVENT_PATH', ''))))
    exact.need(event.get('ref') == expected['GITHUB_REF'] and event.get('after') == sha and
               event.get('forced') is False and event.get('deleted') is False and
               event.get('repository', {}).get('full_name') == REPOSITORY, 'wrong_push_event')
    chain = verify_history(root, sha)
    previous = event.get('before')
    exact.need(isinstance(previous, str) and re.fullmatch('[0-9a-f]{40}', previous), 'invalid_push_before')
    if previous == '0' * 40:
        exact.need(event.get('created') is True, 'not_initial_branch_creation')
    else:
        exact.need(event.get('created') is False and previous in [ANCHOR] + [r['sha'] for r in chain[:-1]],
                   'foreign_or_rewritten_push_before')
    exact.need(not git(root, 'status', '--porcelain', '--untracked-files=all'), 'unclean_assembly_source')
    files = tree_files(root, sha)
    inputs = {name: {'git_blob': item['git_blob'], 'sha256': exact.digest(exact.read(root / name))}
              for name, item in files.items()}
    return dict(**FLAGS, source_sha=sha, source_tree=chain[-1]['tree'], workflow_sha=workflow_sha,
                workflow_ref=WORKFLOW, repository=REPOSITORY, ref=expected['GITHUB_REF'],
                run_id=env['GITHUB_RUN_ID'], run_attempt=env['GITHUB_RUN_ATTEMPT'], job=env['GITHUB_JOB'],
                runner_os=env.get('RUNNER_OS'), matrix_os=matrix_os, runner_image=env.get('ImageOS'),
                runner_image_version=env.get('ImageVersion'), anchor=ANCHOR, anchor_tree=ANCHOR_TREE,
                components={k: {'tree': t, 'parents': ps} for k, (t, ps) in COMPONENTS.items()},
                push_before=previous, branch_created=event['created'], history=chain, inputs=inputs,
                cargo_target_dir=env.get('CARGO_TARGET_DIR'), scope='focused engineering source assembly')


def capture_command(root, evidence, name, timeout, argv):
    exact.need(re.fullmatch('[a-z][a-z0-9-]*', name) and 1 <= timeout <= 7200 and argv, 'invalid_command')
    directory = evidence / 'commands' / name
    directory.mkdir(parents=True, exist_ok=False)
    record = {'command': argv, 'started_at': datetime.now(timezone.utc).isoformat(), 'timeout_seconds': timeout}
    code = 125
    executed = argv
    executable = shutil.which(argv[0])
    if os.name == 'nt' and argv[0] == 'bash':
        executable = r'C:\Program Files\Git\bin\bash.exe'
        exact.need(os.path.isfile(executable), 'missing_windows_git_bash')
        executed = [executable, *argv[1:]]
    elif os.name == 'nt' and executable and Path(executable).suffix.lower() in {'.cmd', '.bat'}:
        executed = [os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/s', '/c', subprocess.list2cmdline([executable, *argv[1:]])]
    record['executed_command'] = executed
    with (directory / 'stdout.txt').open('wb') as out, (directory / 'stderr.txt').open('wb') as err:
        try:
            child = subprocess.Popen(executed, cwd=root, stdout=out, stderr=err,
                                     start_new_session=os.name != 'nt',
                                     creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)
            try:
                code = child.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                record['timed_out'] = True
                if os.name == 'nt':
                    result = subprocess.run(['taskkill', '/F', '/T', '/PID', str(child.pid)], stdout=err, stderr=err, timeout=10)
                    record['cleanup_exit'] = result.returncode
                    child.kill()
                else:
                    try:
                        os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                child.wait(timeout=10)
                code = 124
        except (OSError, subprocess.SubprocessError) as error:
            err.write((type(error).__name__ + ': ' + str(error) + '\n').encode())
        finally:
            record.update(exit=code, completed_at=datetime.now(timezone.utc).isoformat())
            write(directory / 'command.json', record)
            (directory / 'exit-code.txt').write_text(str(code) + '\n')
    sys.stdout.buffer.write((directory / 'stdout.txt').read_bytes())
    sys.stderr.buffer.write((directory / 'stderr.txt').read_bytes())
    return code



def contract_commands(root, evidence, kind, source):
    import rc_source_assembly_frontend as frontend
    portable = {n: frontend.COMMANDS[n] for n in ('versions', 'npm-ci', 'frontend-check', 'frontend-build', 'frontend-full')}
    portable.update({'gateway-delivery': ['node', '--test', *[p.relative_to(root).as_posix() for d in ('cloud-gateway', 'delivery') for p in sorted((root / 'tests' / d).glob('*.test.mjs'))]],
                     'delivery': ['python', '-m', 'unittest', 'discover', '-s', 'tests/delivery', '-v'],
                     'binary-build': ['cargo', 'build', '--locked', '--bins', '--manifest-path', 'services/cloud-gateway/Cargo.toml'],
                     'binary-versions': ['python', 'scripts/rc_source_assembly.py', 'versions', '--root', str(root), '--evidence', str(evidence)]})
    cargo = ['cargo', 'test', '--locked', '--manifest-path', 'services/cloud-gateway/Cargo.toml', '--lib', '--test', 'service_contracts']
    portable.update({'portable-standalone': cargo, 'portable-rc': cargo + ['--test', 'enrollment_contracts'], 'release-contracts': None, 'metadata': None})
    if kind == 'portable':
        return portable
    if kind == 'native':
        host = os.environ.get('HOST_PYTHON')
        exact.need(bool(host), 'missing_native_host_python')
        return {'native-dependencies': None, 'native-compile': None, 'stdin': None,
                'golden': [host, 'tests/cloud-gateway/sandbox-dispatch/run_probe.py', '--evidence', str(evidence / 'sandbox-dispatch')],
                'lifecycle': [host, 'tests/cloud-gateway/sandbox-lifecycle/run_probe.py', '--evidence', str(evidence / 'sandbox-lifecycle')],
                'kernel': ['cargo', 'test', '--locked', '--manifest-path', 'services/local-agent/Cargo.toml', '--test', 'linux_sandbox']}
    command = ['python', 'scripts/engineering_dependency_capture.py', 'collect' if kind == 'capture' else 'verify', '--root', str(root), '--output', str(evidence / 'capture' if kind == 'capture' else evidence.parent / 'assembly-downloaded/capture'), '--expected-sha', source['source_sha'], '--version', '0.7.0-rc.1']
    if kind == 'capture':
        return {'audit-tool': ['cargo', 'install', 'cargo-audit', '--version', '0.22.2', '--locked', '--root', str(evidence.parent / 'audit-tools')], 'capture-contracts': None,
                'collect': command + ['--audit-bin', str(evidence.parent / 'audit-tools/bin/cargo-audit'), '--audit-db', str(evidence.parent / 'dependency-advisory-db')]}
    digest = os.environ.get('RECEIPT_SHA256', '')
    exact.need(re.fullmatch('[0-9a-f]{64}', digest), 'missing_external_receipt_digest')
    return {'verify': command + ['--expected-receipt-sha256', digest]}


def suite_counts(name):
    def flatten(suite):
        for case in suite:
            yield from flatten(case) if isinstance(case, unittest.TestSuite) else [case]
    cases = list(flatten(unittest.defaultTestLoader.loadTestsFromModule(importlib.import_module(name))))
    exact.need(cases, 'empty_current_source_suite')
    skipped = sum(bool(getattr(c, '__unittest_skip__', False) or getattr(getattr(c, c._testMethodName), '__unittest_skip__', False)) for c in cases)
    return len(cases), skipped


def suite_evidence(evidence, kind):
    suites = RELEASE_SUITES if kind == 'portable' else CAPTURE_SUITES
    filename = 'python-exits.txt' if kind == 'portable' else 'capture-contract-exits.txt'
    names = suites if kind == 'portable' else [n.removesuffix('_tests') for n in suites]
    lines = exact.read(evidence / filename).decode().splitlines()
    exact.need(len(lines) == len(names) and set(lines) == {name + '=0' for name in names}, 'incomplete_or_failed_suite_exits')
    counts = {}
    for name, stem in zip(suites, names):
        text = exact.read(evidence / (stem + ('.txt' if kind == 'portable' else '-tests.txt'))).decode()
        total, skipped = suite_counts(name)
        exact.need(re.findall(r'Ran (\d+) tests?', text) == [str(total)], 'wrong_discovered_suite_count')
        actual_skips = re.findall(r'OK \(skipped=(\d+)\)', text)
        exact.need(actual_skips == [str(skipped)] if skipped else not actual_skips and bool(re.search(r'^OK\s*$', text, re.M)), 'wrong_suite_success_or_skips')
        counts[name] = {'discovered': total, 'executed': total - skipped, 'skipped': skipped}
    write(evidence / 'current-source-suite-counts.json', counts)


def command_result(evidence, name, expected=None):
    folder = evidence / 'commands' / name
    data = exact.decode(exact.read(folder / 'command.json'))
    exact.need(type(data.get('exit')) is int and data['exit'] == 0 and
               exact.read(folder / 'exit-code.txt').strip() == b'0', 'failed_command_' + name)
    times = [datetime.fromisoformat(data[k]) for k in ('started_at', 'completed_at')]
    exact.need(all(t.tzinfo is not None for t in times) and times[0] <= times[1] and
               type(data.get('command')) is list and data['command'], 'invalid_command_receipt')
    actual = data['command']
    exact.need(all(type(x) is str for x in actual) and data.get('timed_out', False) is False, 'invalid_executed_receipt')
    executed = actual
    executable = shutil.which(actual[0])
    if os.name == 'nt' and actual[0] == 'bash':
        executable = r'C:\Program Files\Git\bin\bash.exe'
        exact.need(os.path.isfile(executable), 'missing_windows_git_bash')
        executed = [executable, *actual[1:]]
    elif os.name == 'nt' and executable and Path(executable).suffix.lower() in {'.cmd', '.bat'}:
        executed = [os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/s', '/c', subprocess.list2cmdline([executable, *actual[1:]])]
    exact.need(data.get('executed_command') == executed, 'wrong_executed_command_' + name)
    if name in SHELL_DIGESTS:
        prefix = (['dbus-run-session', '--'] if name == 'stdin' else []) + ['bash', '-euo', 'pipefail', '-c']
        exact.need(actual[:-1] == prefix and exact.digest(actual[-1].encode()) == SHELL_DIGESTS[name], 'wrong_shell_command_' + name)
    elif expected is not None:
        def paths(argv):
            return [os.path.normcase(os.path.normpath(x)) if i and argv[i-1] in {'--root', '--evidence', '--output', '--audit-bin', '--audit-db'} else x for i, x in enumerate(argv)]
        exact.need(paths(actual) == paths(expected), 'wrong_command_' + name)
    exact.read(folder / 'stderr.txt')
    return exact.read(folder / 'stdout.txt').decode(), data


def node_counts(text, count):
    text = re.sub(r'\x1b\[[0-9;]*m', '', text)
    for key, value in [('tests', count), ('pass', count), ('fail', 0), ('cancelled', 0), ('skipped', 0), ('todo', 0)]:
        exact.need(re.findall(r'^(?:#|ℹ) ' + key + r' (\d+)\s*$', text, re.M) == [str(value)], 'wrong_node_' + key)


def rust_counts(text, expected=None, groups=None, sequence=None):
    found = re.findall(r'test result: (\w+)\. (\d+) passed; (\d+) failed; (\d+) ignored; (\d+) measured; (\d+) filtered out;', text)
    exact.need(bool(found) and all(row[0] == 'ok' and int(row[1]) > 0 and row[2:] == ('0', '0', '0', '0') for row in found), 'invalid_rust_results')
    exact.need(expected is None or found == [('ok', str(expected), '0', '0', '0', '0')], 'wrong_rust_count')
    exact.need(groups is None or len(found) == groups, 'wrong_rust_groups')
    exact.need(sequence is None or [int(row[1]) for row in found] == sequence, 'wrong_platform_rust_counts')


def compiled_versions(root, evidence):
    rows = {}
    for name, capability in BINS.items():
        path = root / 'services/cloud-gateway/target/debug' / (name + ('.exe' if os.name == 'nt' else ''))
        result = subprocess.run([str(path), '--version'], capture_output=True, timeout=20)
        expected = f'{name} 0.7.0-rc.1 {capability}\n'.encode()
        exact.need(result.returncode == 0 and result.stdout == expected and not result.stderr, 'wrong_binary_version')
        exact.need(path.is_file() and not path.is_symlink() and 0 < path.stat().st_size < 1024**3, 'invalid_compiled_binary')
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        rows[name] = {'output': result.stdout.decode(), 'sha256': digest}
    report = dict(**FLAGS, source_sha=git(root, 'rev-parse', 'HEAD'), version='0.7.0-rc.1', binaries=rows)
    write(evidence / 'binary-versions.json', report)
    return report


def native_evidence(root, evidence, source):
    for directory, relative, count in [('sandbox-dispatch', 'sandbox-dispatch', 11), ('sandbox-lifecycle', 'sandbox-lifecycle', 7)]:
        folder = evidence / directory
        spec = importlib.util.spec_from_file_location('assembly_' + directory.replace('-', '_'), root / 'tests/cloud-gateway' / relative / 'run_probe.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cases = list(module.CONTROL) + list(module.GAPS) if count == 11 else list(module.CASES)
        report = exact.decode(exact.read(folder / 'result.json'))
        exact.need(report.get('head') == source['source_sha'] and report.get('tree') == source['source_tree'] and
                   report.get('mode') == 'acceptance' and report.get('compile_exit') == 0 and
                   report.get('acceptance_passed') is True and report.get('production_source_restored') is True and
                   not report.get('error') and set(report['tests']) == set(cases) and len(cases) == count, 'invalid_native_receipt')
        hashes = exact.decode(exact.read(folder / 'sha256.json'))
        exact.need(set(hashes) == {'compile.txt', 'result.json'} | {n + '.txt' for n in cases}, 'incomplete_native_streams')
        for file, digest in hashes.items():
            exact.need(exact.digest(exact.read(folder / file)) == digest, 'changed_native_stream')
        for case in cases:
            row = report['tests'][case]
            text = exact.read(folder / (case + '.txt')).decode()
            classifier = module.classify if count == 11 else module.golden.classify
            exact.need(type(row['exit_code']) is int and row['exit_code'] == 0 and row['status'] == 'pass' and
                       classifier(0, text, None) == 'pass' and 'PROBE_SETUP:' not in text, 'invalid_native_case')
            if count == 7:
                exact.need(row.get('test_filter') == module.CASE_PATHS[case], 'wrong_native_filter')
        if count == 7:
            exact.need(report.get('golden_unchanged') is True and report.get('golden_sha256') == module.GOLDEN and
                       report.get('payload_sha256') == {p: source['inputs'][p]['sha256'] for p in module.PAYLOADS.values()}, 'changed_native_payload')
        else:
            exact.need(report.get('probe_sha256') == source['inputs']['tests/cloud-gateway/ubuntu_sandbox_dispatch.rs']['sha256'], 'changed_golden_payload')
    for name in ('sandbox_dispatch_probe', 'sandbox_lifecycle_probe', 'linux_sandbox_lifecycle_support', 'linux_sandbox_deadline'):
        exact.need(not (root / 'src-tauri/src/auth' / (name + '.rs')).exists(), 'leftover_injection')


def finish(root, evidence, kind):
    failures, source, steps = [], {}, {}
    evidence.mkdir(parents=True, exist_ok=True)
    raw_outcomes = os.environ.get('STEP_OUTCOMES', '{}')
    (evidence / 'step-outcomes-raw.txt').write_text(raw_outcomes, encoding='utf-8')
    try:
        steps = exact.decode(raw_outcomes.encode())
        exact.need(type(steps) is dict and all(type(v) is dict for v in steps.values()), 'invalid_step_outcomes')
        write(evidence / 'step-outcomes.json', steps)
    except (OSError, ValueError, TypeError) as error:
        failures.append('step outcomes: ' + str(error))
        steps = {}
    required = {'portable': ['checkout', 'source', 'node', 'python', 'rust', 'versions', 'install', 'check', 'build', 'regression', 'gateway_delivery', 'delivery', 'release_contracts', 'metadata', 'binaries', 'binary_versions', 'standalone', 'rc'],
                'native': ['checkout', 'source', 'python', 'host_python', 'rust', 'dependencies', 'compile', 'golden', 'lifecycle', 'kernel', 'stdin'],
                'capture': ['checkout', 'source', 'python', 'rust', 'audit_tool', 'contracts', 'collect'],
                'verify': ['checkout', 'source', 'python', 'download', 'verify']}[kind]
    failures.extend('failed/skipped step: ' + k for k in required if steps.get(k, {}).get('outcome') != 'success')
    try:
        source = exact.decode(exact.read(evidence / 'source.json'))
        current = verify_source(root, os.environ.get('GITHUB_SHA', ''))
        exact.need(kind == current['job'], 'wrong_finalizer_job')
        exact.need(source == current, 'source_or_inputs_changed')
        commands = contract_commands(root, evidence, kind, source)
        logs = {name: command_result(evidence, name, argv)[0] for name, argv in commands.items()}
        if kind in {'portable', 'capture'}:
            suite_evidence(evidence, kind)
        if kind == 'portable':
            node_counts(logs['frontend-full'], 233)
            node_counts(logs['gateway-delivery'], 147)
            text = logs['delivery'] + exact.read(evidence / 'commands/delivery/stderr.txt').decode()
            skipped = 4 if source['matrix_os'] == 'windows-2025' else 0
            exact.need(re.findall(r'Ran (\d+) tests?', text) == ['88'] and
                       (re.findall(r'OK \(skipped=(\d+)\)', text) == [str(skipped)] if skipped else bool(re.search(r'^OK\s*$', text, re.M))), 'wrong_delivery_count')
            for name, groups in [('portable-standalone', 2), ('portable-rc', 3)]:
                expected = ['cargo', 'test', '--locked', '--manifest-path', 'services/cloud-gateway/Cargo.toml', '--lib', '--test', 'service_contracts']
                if groups == 3:
                    expected += ['--test', 'enrollment_contracts']
                command_result(evidence, name, expected)
                rust_counts(logs[name] + exact.read(evidence / ('commands/' + name + '/stderr.txt')).decode(), groups=groups, sequence=PORTABLE_COUNTS[source['runner_os']][name])
            for key, (unit, package, version) in UNITS.items():
                meta = exact.decode(exact.read(evidence / ('metadata-' + key + '.json')))
                own = [p for p in meta['packages'] if p['name'] == package and p['version'] == version]
                exact.need(len(own) == 1 and meta['resolve']['root'] == own[0]['id'] and bool(meta['resolve']['nodes']) and
                           Path(own[0]['manifest_path']).resolve() == (root / unit / 'Cargo.toml').resolve(), 'invalid_locked_metadata')
            for filename, scope in [('rc-source.json', 'release-candidate-version-and-source'), ('preflight.json', 'release-inputs-only')]:
                report = exact.decode(exact.read(evidence / filename))
                exact.need(report.get('passed') is True and report.get('scope') == scope and report.get('version') == '0.7.0-rc.1', 'invalid_input_preflight')
                exact.need(report.get('source_sha') == source['source_sha'] if filename == 'rc-source.json' else report.get('source_verified') is True and report.get('channel') == 'rc' and report.get('guide') == 'docs/releases/verification-v0.7.0-rc.1.md', 'wrong_preflight_source')
            transition = exact.decode(exact.read(evidence / 'metadata-transition.json'))
            exact.need(transition.get('passed') is True and transition.get('baseline_sha') == METADATA_BASE and len(transition['files']) == 12 and transition.get('version') == '0.7.0-rc.1', 'wrong_metadata_transition')
            report = exact.decode(exact.read(evidence / 'binary-versions.json'))
            exact.need(report.get('source_sha') == source['source_sha'] and set(report['binaries']) == set(BINS), 'missing_binary_versions')
            for name, cap in BINS.items():
                exact.need(report['binaries'][name]['output'] == f'{name} 0.7.0-rc.1 {cap}\n' and re.fullmatch('[0-9a-f]{64}', report['binaries'][name]['sha256']), 'invalid_binary_receipt')
            if source['matrix_os'] == 'ubuntu-24.04':
                import rc_source_assembly_frontend as frontend
                exact.need(steps.get('acceptance', {}).get('outcome') == 'success' and frontend.verify(root, evidence)['passed'] is True, 'frontend_acceptance_failed')
        elif kind == 'native':
            native_evidence(root, evidence, source)
            for name, count in [('kernel', 14), ('stdin', 6)]:
                rust_counts(logs[name] + exact.read(evidence / ('commands/' + name + '/stderr.txt')).decode(), expected=count)
        else:
            result = exact.decode(logs['collect' if kind == 'capture' else 'verify'].encode())
            expected_source = {'sha': source['source_sha'], 'tree': source['source_tree'], 'product_version': '0.7.0-rc.1', 'target': 'x86_64-unknown-linux-gnu',
                               'manifest_sha256': source['inputs'][exact.MANIFEST]['sha256'], 'lock_sha256': source['inputs'][exact.LOCK]['sha256']}
            expected_producer = {'repository': REPOSITORY, 'workflow_ref': WORKFLOW, 'sha': source['source_sha'], 'job': 'capture', 'run_id': source['run_id'], 'run_attempt': source['run_attempt']}
            exact.need(result.get('source') == expected_source and result.get('producer') == expected_producer, 'wrong_capture_summary_identity')
            if kind == 'verify':
                exact.need(result.get('receipt_sha256') == os.environ.get('RECEIPT_SHA256'), 'wrong_verified_receipt_digest')
            exact.need(result.get('pipeline_integrity') == 'verified' and result.get('security_acceptance') == 'not_evaluated' and
                       result.get('raw_zero_claim') is False and result.get('release_approved') is False and
                       result.get('publish_approved') is False and set(result['reports']) == {'desktop', 'cloud-gateway', 'cloud-agent', 'local-agent'}, 'invalid_capture_integrity')
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        failures.append(type(error).__name__ + ': ' + str(error))
    summary = dict(**FLAGS, source_sha=source.get('source_sha'), source_tree=source.get('source_tree'),
                   kind=kind, passed=not failures, failures=failures, full_rc_integration='not_evaluated',
                   security_acceptance='not_evaluated', scope='focused engineering only')
    write(evidence / 'summary.json', summary)
    files = {p.relative_to(evidence).as_posix(): exact.digest(exact.read(p)) for p in evidence.rglob('*')
             if p.is_file() and p.name != 'artifact-manifest.json'}
    write(evidence / 'artifact-manifest.json', files)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('mode', choices=('source', 'run', 'versions', 'finish'))
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--expected-sha')
    parser.add_argument('--name')
    parser.add_argument('--timeout', type=int)
    parser.add_argument('--kind', choices=('portable', 'native', 'capture', 'verify'))
    tokens = sys.argv[1:]
    split = tokens.index('--') if '--' in tokens else len(tokens)
    argv = tokens[split + 1:] if split < len(tokens) else []
    args = parser.parse_args(tokens[:split])
    root, evidence = args.root.resolve(), args.evidence.resolve()
    exact.need(not evidence.is_relative_to(root), 'evidence_must_be_external')
    evidence.mkdir(parents=True, exist_ok=True)
    try:
        if args.mode == 'run':
            return capture_command(root, evidence, args.name, args.timeout, argv)
        if args.mode == 'source':
            result = verify_source(root, args.expected_sha)
            write(evidence / 'source.json', result)
        elif args.mode == 'versions':
            result = compiled_versions(root, evidence)
        else:
            result = finish(root, evidence, args.kind)
        print(json.dumps(result, sort_keys=True))
        return 0 if result.get('passed', True) else 1
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        result = dict(**FLAGS, passed=False, error=type(error).__name__ + ': ' + str(error))
        write(evidence / 'failure.json', result)
        print(json.dumps(result), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
