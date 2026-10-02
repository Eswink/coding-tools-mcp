"""Synthetic finalizer contracts only; no hosted, native, or release acceptance.

Source ancestry is mocked only at the finalizer boundary. Native receipt proof is
mocked separately in native finalizer tests; no fixture claims native execution.
Workflow argv and shell bodies are read independently from the workflow itself.
"""
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import rc_source_assembly as assembly
import exact_build_audit as exact

ROOT = Path(os.environ.get('RC_ASSEMBLY_FIXTURE_ROOT', Path(__file__).resolve().parents[1]))
WORKFLOW = Path(__file__).resolve().parents[1] / '.github/workflows/rc-source-assembly.yml'
DIGEST = 'e' * 64
HOST = '/synthetic/host/python'
STEPS = {
    'portable': 'checkout source node python rust versions install check build regression gateway_delivery delivery release_contracts metadata binaries binary_versions standalone rc',
    'native': 'checkout source python host_python rust dependencies compile golden lifecycle kernel stdin',
    'capture': 'checkout source python rust audit_tool contracts collect',
    'verify': 'checkout source python download verify',
}


def text(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding='utf-8')


def workflow_commands(root, evidence, source):
    """Parse fixture argv, without executing any workflow command or shell body."""
    document = WORKFLOW.read_text(encoding='utf-8')
    pattern = r'--name ([a-z-]+) --timeout [0-9]+ -- (.*)'
    variables = {'GITHUB_WORKSPACE': str(root), 'RUNNER_TEMP': str(evidence.parent),
                 'GITHUB_SHA': source['source_sha'], 'VERSION': '0.7.0-rc.1',
                 'HOST_PYTHON': HOST, 'RECEIPT_SHA256': DIGEST}
    commands = {}
    for match in re.finditer(pattern, document):
        name, command = match.groups()
        if command.endswith("-c '"):
            end = re.search(r"^          '\s*$", document[match.end():], re.M)
            if not end:
                raise AssertionError('unterminated workflow shell: ' + name)
            body = re.sub(r'^ {10}', '', document[match.end():match.end() + end.start()], flags=re.M)
            argv = shlex.split(command[:-1]) + [body]
        else:
            command = command.replace('$RUNNER_TEMP/assembly-evidence', str(evidence))
            for variable, value in variables.items():
                command = command.replace('$' + variable, value)
            argv = shlex.split(command)
            expanded = []
            for arg in argv:
                expanded.extend(sorted(p.relative_to(root).as_posix() for p in root.glob(arg))
                                if '*.test.mjs' in arg else [arg])
            argv = expanded
        commands[name] = argv
    return commands


def executed_argv(argv):
    executed = argv
    executable = shutil.which(argv[0])
    if os.name == 'nt' and executable and Path(executable).suffix.lower() in {'.cmd', '.bat'}:
        executed = [os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/s', '/c',
                    subprocess.list2cmdline([executable, *argv[1:]])]
    return executed


def command_receipt(evidence, name, argv, stdout='synthetic output\n'):
    directory = evidence / 'commands' / name
    assembly.write(directory / 'command.json', {
        'command': argv, 'executed_command': executed_argv(argv), 'exit': 0, 'started_at': '2026-10-02T00:00:00Z',
        'completed_at': '2026-10-02T00:00:01Z', 'synthetic': True})
    for filename, value in [('exit-code.txt', '0\n'), ('stdout.txt', stdout), ('stderr.txt', '')]:
        text(directory / filename, value)


def suite_receipts(evidence, kind):
    suites = assembly.RELEASE_SUITES if kind == 'portable' else assembly.CAPTURE_SUITES
    exits = []
    for suite in suites:
        total, skipped = assembly.suite_counts(suite)
        stem = suite if kind == 'portable' else suite.removesuffix('_tests')
        filename = stem + ('.txt' if kind == 'portable' else '-tests.txt')
        result = f'OK (skipped={skipped})' if skipped else 'OK'
        text(evidence / filename, f'SYNTHETIC receipt, no tests executed\nRan {total} tests in 1s\n\n{result}\n')
        exits.append(stem + '=0')
    text(evidence / ('python-exits.txt' if kind == 'portable' else 'capture-contract-exits.txt'), '\n'.join(exits) + '\n')


def rust_results(counts):
    return ''.join(f'test result: ok. {count} passed; 0 failed; 0 ignored; 0 measured; 0 filtered out;\n' for count in counts)


def source_fixture(matrix, kind):
    return dict(assembly.FLAGS, synthetic=True, source_sha='a' * 40, source_tree='b' * 40,
                matrix_os=matrix, runner_os='Windows' if matrix == 'windows-2025' else 'Linux',
                run_id='123', run_attempt='1', job=kind,
                inputs={exact.MANIFEST: {'sha256': 'c' * 64}, exact.LOCK: {'sha256': 'd' * 64}})


def base_fixture(root, evidence, kind, matrix='ubuntu-24.04'):
    source = source_fixture(matrix, kind)
    assembly.write(evidence / 'source.json', source)
    commands = workflow_commands(root, evidence, source)
    with patch.dict(os.environ, HOST_PYTHON=HOST, RECEIPT_SHA256=DIGEST):
        for name in assembly.contract_commands(root, evidence, kind, source):
            command_receipt(evidence, name, commands[name])
    outcomes = {name: {'outcome': 'success'} for name in STEPS[kind].split()}
    return source, outcomes


def portable_fixture(root, evidence, matrix='ubuntu-24.04'):
    """Reusable complete synthetic portable fixture; Ubuntu24 still needs browser proof."""
    source, outcomes = base_fixture(root, evidence, 'portable', matrix)
    suite_receipts(evidence, 'portable')
    for name, count in [('frontend-full', 233), ('gateway-delivery', 147)]:
        text(evidence / f'commands/{name}/stdout.txt', '\n'.join(
            f'# {key} {value}' for key, value in [('tests', count), ('pass', count),
            ('fail', 0), ('cancelled', 0), ('skipped', 0), ('todo', 0)]) + '\n')
    ending = 'OK (skipped=4)' if matrix == 'windows-2025' else 'OK'
    text(evidence / 'commands/delivery/stdout.txt', f'Ran 88 tests in 1s\n\n{ending}\n')
    counts = {'portable-standalone': [49, 18], 'portable-rc': [49, 10, 18]} if matrix == 'windows-2025' else {
        'portable-standalone': [50, 23], 'portable-rc': [50, 11, 23]}
    for name, sequence in counts.items():
        text(evidence / f'commands/{name}/stdout.txt', rust_results(sequence))
    for key, (unit, package, version) in assembly.UNITS.items():
        assembly.write(evidence / ('metadata-' + key + '.json'), {
            'packages': [{'name': package, 'version': version, 'id': key,
                          'manifest_path': str(root / unit / 'Cargo.toml')}],
            'resolve': {'root': key, 'nodes': [{'id': key}]}})
    assembly.write(evidence / 'rc-source.json', dict(passed=True, version='0.7.0-rc.1',
                   scope='release-candidate-version-and-source', source_sha=source['source_sha']))
    assembly.write(evidence / 'preflight.json', dict(passed=True, version='0.7.0-rc.1',
                   scope='release-inputs-only', source_verified=True, channel='rc',
                   guide='docs/releases/verification-v0.7.0-rc.1.md'))
    assembly.write(evidence / 'metadata-transition.json', dict(passed=True, version='0.7.0-rc.1',
                   baseline_sha=assembly.METADATA_BASE, files={str(i): {} for i in range(12)}))
    assembly.write(evidence / 'binary-versions.json', dict(assembly.FLAGS,
                   source_sha=source['source_sha'], version='0.7.0-rc.1', binaries={
                       name: {'output': f'{name} 0.7.0-rc.1 {capability}\n', 'sha256': 'c' * 64}
                       for name, capability in assembly.BINS.items()}))
    outcomes['acceptance'] = {'outcome': 'skipped'}
    return source, outcomes


def capture_fixture(root, evidence, kind='capture'):
    source, outcomes = base_fixture(root, evidence, kind)
    if kind == 'capture':
        suite_receipts(evidence, kind)
    result = dict(source={'sha': source['source_sha'], 'tree': source['source_tree'],
                         'product_version': '0.7.0-rc.1', 'target': 'x86_64-unknown-linux-gnu',
                         'manifest_sha256': 'c' * 64, 'lock_sha256': 'd' * 64},
                  producer=dict(repository=assembly.REPOSITORY, workflow_ref=assembly.WORKFLOW,
                                sha=source['source_sha'], job='capture', run_id='123', run_attempt='1'),
                  pipeline_integrity='verified', security_acceptance='not_evaluated', raw_zero_claim=False,
                  release_approved=False, publish_approved=False, receipt_sha256=DIGEST,
                  reports={name: {'vulnerability_count': 1, 'warning_counts': {'unsound': 1}}
                           for name in ['desktop', 'cloud-gateway', 'cloud-agent', 'local-agent']})
    name = 'collect' if kind == 'capture' else 'verify'
    text(evidence / f'commands/{name}/stdout.txt', json.dumps(result))
    text(evidence / 'capture/raw-findings.txt', 'SYNTHETIC RUSTSEC finding; audit exit=1\n')
    return source, outcomes


class FinalizerEvidenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='assembly-evidence-contract-')
        self.addCleanup(temporary.cleanup)
        self.evidence = Path(temporary.name) / 'assembly-evidence'
        self.enterContext(patch.dict(os.environ, HOST_PYTHON=HOST, RECEIPT_SHA256=DIGEST))

    def fixture(self, kind='portable', matrix='ubuntu-22.04'):
        if kind == 'portable':
            self.source, self.outcomes = portable_fixture(ROOT, self.evidence, matrix)
        elif kind in {'capture', 'verify'}:
            self.source, self.outcomes = capture_fixture(ROOT, self.evidence, kind)
        else:
            self.source, self.outcomes = base_fixture(ROOT, self.evidence, kind)
            for name, count in [('kernel', 14), ('stdin', 6)]:
                text(self.evidence / f'commands/{name}/stdout.txt', rust_results([count]))
        self.kind = kind

    def finish(self):
        # Separate explicit mocks: ancestry is outside these unit tests, as is native proof.
        with patch.dict(os.environ, GITHUB_SHA=self.source['source_sha'], STEP_OUTCOMES=json.dumps(self.outcomes)), \
                patch.object(assembly, 'verify_source', return_value=self.source), \
                patch.object(assembly, 'native_evidence', return_value=None) as native:
            result = assembly.finish(ROOT, self.evidence, self.kind)
            if self.kind != 'native':
                native.assert_not_called()
        self.assertEqual({key: result[key] for key in assembly.FLAGS}, assembly.FLAGS)
        self.assertEqual(result['security_acceptance'], 'not_evaluated')
        self.assertEqual(result['full_rc_integration'], 'not_evaluated')
        return result

    def rejects(self, expected=None):
        result = self.finish()
        self.assertFalse(result['passed'], result)
        if expected:
            self.assertIn(expected, str(result['failures']))

    def mutate_json(self, relative, mutate, expected=None):
        path = self.evidence / relative
        before = path.read_bytes()
        value = json.loads(before)
        mutate(value)
        if relative.endswith('/command.json') and value['command'] != json.loads(before)['command']:
            # Keep transport consistent so argv mutations reach the scope-binding guard.
            value['executed_command'] = executed_argv(value['command'])
        assembly.write(path, value)
        try:
            self.rejects(expected)
        finally:
            path.write_bytes(before)

    def test_complete_portable_linux_and_windows_finalizers(self):
        for matrix in ['ubuntu-22.04', 'windows-2025']:
            with self.subTest(matrix=matrix):
                self.fixture(matrix=matrix)
                self.assertTrue(self.finish()['passed'])
                counts = exact.decode((self.evidence / 'current-source-suite-counts.json').read_bytes())
                self.assertEqual(set(counts), set(assembly.RELEASE_SUITES))
                self.assertEqual(counts[__name__.replace('__main__', 'rc_source_assembly_evidence_tests')]['discovered'],
                                 assembly.suite_counts('rc_source_assembly_evidence_tests')[0])

    def test_ubuntu24_requires_browser_proof_even_without_image_label(self):
        self.fixture(matrix='ubuntu-24.04')
        self.rejects('frontend_acceptance_failed')
        self.outcomes['acceptance']['outcome'] = 'success'
        import rc_source_assembly_frontend as frontend
        with patch.object(frontend, 'verify', return_value={'passed': False}) as browser:
            self.rejects('frontend_acceptance_failed')
            browser.assert_called_once()

    def test_complete_capture_verify_and_narrow_native_finalizers(self):
        for kind in ['capture', 'verify', 'native']:
            with self.subTest(kind=kind):
                self.fixture(kind)
                self.assertTrue(self.finish()['passed'])

    def test_every_named_command_rejects_unrelated_successful_argv(self):
        seen = set()
        for kind in STEPS:
            self.fixture(kind)
            self.assertTrue(self.finish()['passed'])
            for name in assembly.contract_commands(ROOT, self.evidence, kind, self.source):
                with self.subTest(kind=kind, name=name):
                    seen.add(name)
                    self.mutate_json(f'commands/{name}/command.json',
                                     lambda row: row.update(command=['python', '-c', 'print("unrelated")']),
                                     'wrong_shell_command_' if name in assembly.SHELL_DIGESTS else 'wrong_command_')
        self.assertEqual(len(seen), 23)

    def test_every_shell_rejects_changed_scope_or_prefix(self):
        for kind in ['portable', 'native', 'capture']:
            self.fixture(kind)
            for name in assembly.contract_commands(ROOT, self.evidence, kind, self.source):
                if name not in assembly.SHELL_DIGESTS:
                    continue
                for mutation in [lambda row: row['command'].__setitem__(-1, row['command'][-1] + '\ntrue'),
                                 lambda row: row['command'].__setitem__(0, 'sh'),
                                 lambda row: row['command'].__setitem__(-1, row['command'][-1].replace('\n', '\r')),
                                 lambda row: row['command'].__setitem__(-1, row['command'][-1].replace('\n', '\n '))]:
                    with self.subTest(kind=kind, name=name):
                        self.mutate_json(f'commands/{name}/command.json', mutation, 'wrong_shell_command_')

    def test_named_commands_require_exit_streams_and_valid_timestamps(self):
        self.fixture()
        for name in assembly.contract_commands(ROOT, self.evidence, self.kind, self.source):
            for change in [{'exit': 1}, {'exit': False}, {'completed_at': '2026-10-01T23:59:59Z'},
                           {'started_at': '2026-10-02T00:00:00'}, {'timed_out': True},
                           {'executed_command': ['python', '-c', 'print(1)']}]:
                with self.subTest(name=name, change=change):
                    self.mutate_json(f'commands/{name}/command.json', lambda row: row.update(change))
            for filename in ['stdout.txt', 'stderr.txt', 'exit-code.txt']:
                path = self.evidence / f'commands/{name}/{filename}'
                before = path.read_bytes()
                path.unlink()
                with self.subTest(name=name, missing=filename):
                    self.rejects()
                path.write_bytes(before)

    def test_each_current_source_suite_requires_complete_unambiguous_receipts(self):
        for kind in ['portable', 'capture']:
            self.fixture(kind)
            exits = self.evidence / ('python-exits.txt' if kind == 'portable' else 'capture-contract-exits.txt')
            original = exits.read_text()
            for line in original.splitlines():
                for changed in [original.replace(line + '\n', ''), original.replace(line + '\n', line + '\n' + line + '\n'),
                                original.replace(line, line[:-1] + '1')]:
                    text(exits, changed)
                    with self.subTest(kind=kind, line=line), self.assertRaises(ValueError):
                        assembly.suite_evidence(self.evidence, kind)
                    text(exits, original)
                stem = line.split('=')[0]
                path = self.evidence / (stem + ('.txt' if kind == 'portable' else '-tests.txt'))
                before = path.read_bytes()
                for value in ['Ran 1 test in 1s\n\nOK\n', 'Ran 0 tests in 1s\n\nOK\n',
                              before.decode() + before.decode(), before.decode().replace('OK', 'FAILED')]:
                    text(path, value)
                    with self.subTest(kind=kind, suite=stem, value=value[:25]), self.assertRaises(ValueError):
                        assembly.suite_evidence(self.evidence, kind)
                path.unlink()
                with self.assertRaises(ValueError):
                    assembly.suite_evidence(self.evidence, kind)
                path.write_bytes(before)
            assembly.suite_evidence(self.evidence, kind)

    def test_cargo_sequences_reject_one_test_omission_reordering_and_nonzero_fields(self):
        for matrix in ['ubuntu-22.04', 'windows-2025']:
            self.fixture(matrix=matrix)
            for name in ['portable-standalone', 'portable-rc']:
                path = self.evidence / f'commands/{name}/stdout.txt'
                before = path.read_text()
                rows = before.splitlines(keepends=True)
                invalid = [rust_results([1] * len(rows)), ''.join(rows[1:]), ''.join(reversed(rows)), before + rows[0]]
                invalid += [before.replace('0 ' + key, '1 ' + key) for key in ['failed', 'ignored', 'filtered', 'measured']]
                invalid += [before.replace('50 passed', '0 passed').replace('49 passed', '0 passed')]
                for value in invalid:
                    text(path, value)
                    with self.subTest(matrix=matrix, name=name, value=value[:35]):
                        self.rejects()
                text(path, before)

    def test_cargo_argv_requires_every_suite_in_reviewed_order(self):
        self.fixture()
        for name in ['portable-standalone', 'portable-rc']:
            relative = f'commands/{name}/command.json'
            argv = json.loads((self.evidence / relative).read_text())['command']
            variants = [argv[:-2], argv + ['--', '--ignored'], argv[0:2] + argv[3:]]
            if name == 'portable-rc':
                variants.append(argv[:-4] + argv[-2:] + argv[-4:-2])
            for changed in variants:
                with self.subTest(name=name, argv=changed):
                    self.mutate_json(relative, lambda row: row.update(command=changed), 'wrong_command_')

    def test_portable_reports_cannot_be_omitted(self):
        self.fixture()
        names = ['rc-source.json', 'preflight.json', 'metadata-transition.json', 'binary-versions.json']
        names += ['metadata-' + unit + '.json' for unit in assembly.UNITS]
        for name in names:
            path = self.evidence / name
            before = path.read_bytes()
            path.unlink()
            with self.subTest(name=name):
                self.rejects('invalid_evidence_file')
            path.write_bytes(before)

    def test_platform_specific_delivery_skips_and_rust_counts_are_exact(self):
        for matrix in ['ubuntu-22.04', 'windows-2025']:
            self.fixture(matrix=matrix)
            path = self.evidence / 'commands/delivery/stdout.txt'
            before = path.read_bytes()
            wrong = 'OK' if matrix == 'windows-2025' else 'OK (skipped=4)'
            for report in [f'Ran 88 tests in 1s\n\n{wrong}\n', 'Ran 1 test in 1s\n\nOK\n']:
                text(path, report)
                self.rejects('wrong_delivery_count')
            path.write_bytes(before)
            other = [50, 23] if matrix == 'windows-2025' else [49, 18]
            text(self.evidence / 'commands/portable-standalone/stdout.txt', rust_results(other))
            self.rejects('wrong_platform_rust_counts')

    def test_stale_preflight_metadata_and_binary_receipts_reject(self):
        self.fixture()
        mutations = [('rc-source.json', {'source_sha': 'f' * 40}), ('rc-source.json', {'version': '0.6.0-rc.4'}),
                     ('preflight.json', {'source_verified': False}), ('preflight.json', {'version': '0.6.0-rc.4'}),
                     ('preflight.json', {'channel': 'stable'}), ('preflight.json', {'guide': 'wrong.md'}),
                     ('metadata-transition.json', {'baseline_sha': 'f' * 40}),
                     ('metadata-transition.json', {'version': '0.6.0-rc.4'}),
                     ('binary-versions.json', {'source_sha': 'f' * 40})]
        for path, change in mutations:
            with self.subTest(path=path, change=change):
                self.mutate_json(path, lambda row: row.update(change))
        for unit in assembly.UNITS:
            for field, value in [('version', '0.0.0'), ('manifest_path', '/wrong/Cargo.toml')]:
                self.mutate_json('metadata-' + unit + '.json', lambda row: row['packages'][0].update({field: value}))
        for binary in assembly.BINS:
            for change in [{'output': binary + ' 0.6.0-rc.4\n'}, {'sha256': 'invalid'}]:
                self.mutate_json('binary-versions.json', lambda row: row['binaries'][binary].update(change))
        self.mutate_json('metadata-transition.json', lambda row: row['files'].pop('0'))
        self.mutate_json('binary-versions.json', lambda row: row['binaries'].pop(next(iter(assembly.BINS))))

    def test_capture_verify_identity_binding_and_authority(self):
        for kind in ['capture', 'verify']:
            self.fixture(kind)
            filename = 'commands/' + ('collect' if kind == 'capture' else 'verify') + '/stdout.txt'
            for field in ['sha', 'tree', 'product_version', 'target', 'manifest_sha256', 'lock_sha256']:
                with self.subTest(kind=kind, source=field):
                    self.mutate_json(filename, lambda row: row['source'].update({field: 'wrong'}), 'wrong_capture_summary_identity')
            for field in ['repository', 'workflow_ref', 'sha', 'job', 'run_id', 'run_attempt']:
                with self.subTest(kind=kind, producer=field):
                    self.mutate_json(filename, lambda row: row['producer'].update({field: 'wrong'}), 'wrong_capture_summary_identity')
            for field, value in [('pipeline_integrity', 'unknown'), ('security_acceptance', 'passed'),
                                 ('raw_zero_claim', True), ('release_approved', True), ('publish_approved', True)]:
                self.mutate_json(filename, lambda row: row.update({field: value}), 'invalid_capture_integrity')
            self.mutate_json(filename, lambda row: row['reports'].pop('desktop'))
            if kind == 'verify':
                self.mutate_json(filename, lambda row: row.update(receipt_sha256='f' * 64), 'wrong_verified_receipt_digest')
                with patch.dict(os.environ, RECEIPT_SHA256=''):
                    self.rejects('missing_external_receipt_digest')

    def test_raw_nonzero_findings_remain_byte_identical_and_manifested(self):
        for kind in ['capture', 'verify']:
            self.fixture(kind)
            paths = ['capture/raw-findings.txt', 'commands/' + ('collect' if kind == 'capture' else 'verify') + '/stdout.txt']
            before = {name: (self.evidence / name).read_bytes() for name in paths}
            self.assertTrue(self.finish()['passed'])
            manifest = json.loads((self.evidence / 'artifact-manifest.json').read_text())
            for name, data in before.items():
                self.assertEqual((self.evidence / name).read_bytes(), data)
                self.assertEqual(manifest[name], exact.digest(data))

    def test_finish_kind_must_match_fresh_source_job(self):
        kinds = list(STEPS)
        for index, kind in enumerate(kinds):
            self.fixture(kind)
            self.source['job'] = kinds[(index + 1) % len(kinds)]
            assembly.write(self.evidence / 'source.json', self.source)
            with self.subTest(finalizer=kind, source_job=self.source['job']):
                self.rejects('wrong_finalizer_job')

    def test_wrong_source_and_failed_steps_stay_failed_with_raw_outcomes_retained(self):
        for kind in STEPS:
            self.fixture(kind)
            self.mutate_json('source.json', lambda row: row.update(source_sha='f' * 40), 'source_or_inputs_changed')
            for name in STEPS[kind].split():
                self.outcomes[name]['outcome'] = 'skipped'
                self.rejects('failed/skipped step: ' + name)
                self.assertEqual(json.loads((self.evidence / 'step-outcomes-raw.txt').read_text()), self.outcomes)
                self.outcomes[name]['outcome'] = 'success'


if __name__ == '__main__':
    unittest.main()
