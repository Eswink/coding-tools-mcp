#!/usr/bin/env python3
"""Owned Git/data/parser controls only; no GitHub/native-owner/compiler qualification."""
import atexit
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.dont_write_bytecode = True
import windows_foundation_source_guard as guard
import windows_foundation_union_overlay as overlay
import windows_foundation_inference_overlay as original_overlay
import windows_foundation_inference_overlay_tests as original_controls
import windows_foundation_manager_checkout_tests as legacy_checkout

POOL = Path(sys.argv[1]).resolve()
PWSH = sys.argv[2] if len(sys.argv) > 2 else None
CONTROL_EVIDENCE = Path(sys.argv[3]).resolve() if len(sys.argv) > 3 else None


class UnionOverlayOwnedControls(unittest.TestCase):
    def setUp(self):
        cls = type(self)
        if not hasattr(cls, 'owned'):
            cls.owned = tempfile.TemporaryDirectory(prefix='ordinary-union1967-', dir=POOL.parent)
            atexit.register(cls.owned.cleanup)
            cls.root = Path(cls.owned.name)
            cls.repo = cls.root / 'sut'
            subprocess.run(['git', 'clone', '--no-hardlinks', '--no-checkout', str(POOL), str(cls.repo)],
                           capture_output=True, check=True, timeout=30)
            guard.run_git(cls.repo, 'checkout', '--detach', guard.BASE)
            cls.baseline = guard.load_manifest(Path(guard.__file__).with_name('windows_foundation_source_manifest.json'))
            # This is real native remote fetch/show of the immutable833e payload, not an API adapter.
            cls.manifest_raw, cls.sources = overlay.fetch_union_payload(cls.repo)
            cls.candidate = overlay.load_union_candidate(cls.manifest_raw, cls.sources, cls.baseline)
            cls.manager = cls.root / 'manager'
            cls.manager.mkdir()
            paths = [*legacy_checkout.MANAGER_PATHS, original_overlay.HELPER, overlay.HELPER,
                     'scripts/windows_foundation_manager_observation.py']
            for name in paths:
                dest = cls.manager / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes((Path(__file__).resolve().parent.parent / name).read_bytes())
            guard.run_git(cls.manager, 'init', '-q')
            guard.run_git(cls.manager, 'add', '--', '.')
            guard.run_git(cls.manager, '-c', 'user.name=Owned Source Control',
                          '-c', 'user.email=owned-control@example.invalid', 'commit', '-qm',
                          'Owned ordinary union fixture; not CI or a production candidate')
            cls.manager_head = guard.run_git(cls.manager, 'rev-parse', 'HEAD').decode().strip()
        self.write_owned_baseline()

    def tearDown(self):
        self.write_owned_baseline()

    def write_owned_baseline(self):
        # Remove only14 known new files inside this exclusively created ordinary fixture.
        originals = {row['path'] for row in self.baseline['whole_source']}
        for row in overlay.LEAF_TABLE:
            file = self.repo / row['path']
            if row['path'] not in originals and (file.exists() or file.is_symlink()):
                file.unlink()
        canary = self.repo / 'ordinary-untracked-canary.txt'
        if canary.exists():
            canary.unlink()
        guard.run_git(self.repo, 'read-tree', guard.TARGET, index=True)
        guard.run_git(self.repo, 'checkout-index', '--all', '--force', index=True)
        self.assertEqual(guard.verify_materialized(self.repo, self.baseline)['tree'], guard.TARGET)

    def owned_env(self):
        # Source-lease context only: explicitly false CI; this never grants native authority.
        return patch.dict(os.environ, {'GITHUB_SHA': self.manager_head, 'GITHUB_RUN_ID': '1',
                                       'GITHUB_ACTIONS': 'false'})

    def invoke_production_main(self, operation, receipt, **patches):
        argv = ['union', operation, '--manifest', str(Path(guard.__file__).with_name('windows_foundation_source_manifest.json')),
                '--manager', str(self.manager), '--destination', str(self.repo), '--receipt', str(receipt)]
        with patch.object(sys, 'argv', argv), self.owned_env():
            return overlay.main()

    def run_owned_powershell(self, case):
        self.assertIsNotNone(PWSH)
        self.assertIsNotNone(CONTROL_EVIDENCE)
        source = overlay.apply_union_overlay(self.repo, self.baseline, self.manifest_raw, self.sources)
        source_before = self.root / ('before-' + case + '.json')
        source_before.write_text(json.dumps(dict(source, passed=True)))
        before = self.root / ('manager-before-' + case + '.json')
        with self.owned_env():
            before.write_text(json.dumps(guard.verify_manager(self.manager)))
        script = self.root / 'actual-source-host-control.ps1'
        # Only the controlled fixture parameter name changes; production TryAST/functions are read exact.
        script.write_text(original_controls.PS_SOURCE_CANCEL_CONTROL.replace('$InferenceOverlay', '$UnionOverlay'))
        output = self.root / ('actual-ps-' + case)
        output.mkdir(exist_ok=True)
        args = [PWSH, '-NoLogo', '-NoProfile', '-File', str(script),
                str(Path(__file__).with_name('windows_foundation_source_compile.ps1')), sys.executable,
                str(self.manager), str(self.manager / 'scripts/windows_foundation_source_guard.py'),
                str(self.manager / 'scripts/windows_foundation_source_manifest.json'),
                str(self.manager / 'scripts/windows_foundation_manager_observation.py'),
                str(self.manager / overlay.HELPER), str(self.repo), str(output), str(before), str(source_before), case]
        with self.owned_env():
            result = subprocess.run(args, capture_output=True, timeout=30)
        evidence = CONTROL_EVIDENCE / ('actual-ps-' + case)
        evidence.mkdir(parents=True, exist_ok=True)
        (evidence / 'stdout.raw').write_bytes(result.stdout)
        (evidence / 'stderr.raw').write_bytes(result.stderr)
        for file in output.iterdir():
            if file.is_file():
                shutil.copyfile(file, evidence / file.name)
        (evidence / 'native-result.json').write_text(json.dumps({'nativeExit': result.returncode,
                                                               'compilerSUTExecuted': 0}))
        self.assertEqual(result.returncode, 0, result.stdout.decode(errors='replace') + result.stderr.decode(errors='replace'))
        receipt = json.loads((output / 'compiler-result.json').read_text(encoding='utf-8-sig'))
        self.assertIs(receipt['passed'], False)
        self.assertEqual(receipt['compiler'], 'NOTRUN')
        self.assertEqual(receipt['managerSourceBefore']['management_digest'], receipt['managerSourceAfter']['management_digest'])
        self.assertEqual(receipt['runtime']['python']['sha256Before'], receipt['runtime']['python']['sha256After'])
        self.assertIn('no new diagnostic child', receipt['managerObservationAfterSkipped'])
        if case == 'before-pipeline':
            self.assertIs(receipt['delegateInterruptedUnknown'], True)
        if case == 'after-pipeline':
            self.assertIs(receipt['sourceAfterInterruptedUnknown'], True)
        return receipt

    def owned_true_record(self):
        if hasattr(type(self), 'consumer_fixture'):
            overlay.apply_union_overlay(self.repo, self.baseline, self.manifest_raw, self.sources)
            return type(self).consumer_fixture
        output = self.root / 'actual-owned-go23'
        output.mkdir()
        tools = {'git': shutil.which('git'), 'python': sys.executable,
                 'go': '/workspace/work/rc070/windows-tools/go/bin/go'}
        runtime = {name: {'path': path, 'sha256Before': hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                          'sha256After': None} for name, path in tools.items()}
        commands = []
        manifest = self.manager / 'scripts/windows_foundation_source_manifest.json'
        native_guard = self.manager / 'scripts/windows_foundation_source_guard.py'
        native_helper = self.manager / overlay.HELPER
        observer = self.manager / 'scripts/windows_foundation_manager_observation.py'
        calls = [('git', ['--version'], 'git-version.log'),
                 ('python', ['-c', 'import sys; assert sys.version_info[:2] == (3, 12), sys.version; print(sys.version)'], 'python-version.log'),
                 ('python', [str(observer), '--manager', str(self.manager), '--receipt', str(output / 'management-byte-observation-Before.json')], 'management-byte-observation-Before.log'),
                 ('python', [str(native_guard), 'verify-manager', '--manifest', str(manifest), '--manager', str(self.manager), '--receipt', str(output / 'management-before.json')], 'management-before.log'),
                 # Actual baseline verification, explicitly LOCAL_OWNED_COMPONENT; not remote CI restoration.
                 ('python', [str(native_guard), 'verify', '--manifest', str(manifest), '--destination', str(self.repo), '--receipt', str(output / 'source-before.json')], 'source-restore.log'),
                 ('python', [str(native_helper), 'apply', '--manifest', str(manifest), '--manager', str(self.manager), '--destination', str(self.repo), '--receipt', str(output / 'candidate-source-before.json')], 'candidate-source-overlay.log'),
                 ('go', ['version'], 'go-version.log'),
                 ('go', ['test', '-race', '-v', '-count=1', *overlay.GO_FILES], 'go9-data-race-test.log'),
                 ('python', [str(native_helper), 'verify', '--manifest', str(manifest), '--manager', str(self.manager), '--destination', str(self.repo), '--receipt', str(output / 'source-after.json')], 'source-after.log'),
                 ('python', [str(native_guard), 'verify-manager', '--manifest', str(manifest), '--manager', str(self.manager), '--receipt', str(output / 'management-after.json')], 'management-after.log'),
                 ('python', [str(observer), '--manager', str(self.manager), '--receipt', str(output / 'management-byte-observation-After.json')], 'management-byte-observation-After.log')]
        with self.owned_env():
            for tool, arguments, name in calls:
                env = os.environ.copy()
                env['GOCACHE'] = str(CONTROL_EVIDENCE / 'go-cache')
                child = subprocess.run([tools[tool], *arguments], cwd=self.repo, env=env,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
                (output / name).write_bytes(child.stdout)
                self.assertEqual(child.returncode, 0, child.stdout.decode(errors='replace'))
                commands.append({'executable': tool, 'resolvedExecutable': tools[tool], 'arguments': arguments,
                                 'log': name, 'exitCode': child.returncode})
            source = overlay.verify_union_candidate(self.repo, self.candidate)
            manager = guard.verify_manager(self.manager)
            helpers = overlay.verify_union_helper_leases(self.manager)
        for row in runtime.values():
            row['sha256After'] = hashlib.sha256(Path(row['path']).read_bytes()).hexdigest()
        baseline = json.loads((output / 'source-before.json').read_text())
        baseline['payload_mode'] = 'LOCAL_OWNED_COMPONENT'
        record = {'passed': True, 'mode': 'go', 'runId': '1', 'compiler': 'DATA_23_RACE_TEST_PASS',
                  'pureSutTree': overlay.TARGET, 'baselineSutTree': guard.TARGET, 'managerCommit': self.manager_head,
                  'sourceOverlayStarted': True, 'nativePositive': 'NOTRUN', 'qualification': 'SOURCE_ONLY_BLOCKED',
                  'managerObservationFailed': False, 'sourceBaseline': baseline,
                  'sourceBefore': json.loads((output / 'candidate-source-before.json').read_text()),
                  'sourceAfter': json.loads((output / 'source-after.json').read_text()),
                  'managerSourceBefore': json.loads((output / 'management-before.json').read_text()),
                  'managerSourceAfter': json.loads((output / 'management-after.json').read_text()),
                  'runtime': runtime, 'commands': commands, 'componentContext': 'ACTUAL_OWNED_GO23_NOT_CI'}
        with self.owned_env():
            admitted = overlay.verify_union_compiler_result(record, 'go', output, source, manager, self.manager_head, helpers, self.manager, self.repo, ordinary_profile=True)
        self.assertEqual(admitted['named_data_count'], 23)
        self.assertIs(admitted['native_authority'], False)
        self.assertEqual(admitted['qualification'], 'OWNED_COMPONENT_ONLY')
        self.assertIs(admitted['ci'], False)
        self.assertIs(admitted['qualified'], False)
        type(self).consumer_fixture = (record, output, source, manager, helpers)
        evidence = CONTROL_EVIDENCE / 'actual-owned-go23'
        evidence.mkdir(parents=True, exist_ok=True)
        for file in output.iterdir():
            if file.is_file():
                shutil.copyfile(file, evidence / file.name)
        (evidence / 'LOCAL-ORDINARY-RECORD.json').write_text(json.dumps(record, indent=2) + '\n')
        (evidence / 'COMPONENT-ONLY-RESULT.json').write_text(json.dumps(admitted, indent=2) + '\n')
        return type(self).consumer_fixture

    def test_full_baseline_then_exact_native_1967_overlay_and_verify(self):
        with self.assertRaisesRegex(ValueError, 'index tree'):
            overlay.verify_union_candidate(self.repo, self.candidate)
        admitted = overlay.apply_union_overlay(self.repo, self.baseline, self.manifest_raw, self.sources)
        self.assertEqual((admitted['tree'], admitted['files'], admitted['native_authority']), (overlay.TARGET, 1967, False))
        self.assertEqual(admitted, overlay.verify_union_candidate(self.repo, self.candidate))
        self.assertEqual(set(guard.run_git(self.repo, 'diff', '--name-only', guard.TARGET, overlay.TARGET).decode().splitlines()), set(self.sources))
        self.assertEqual(guard.run_git(self.repo, 'cat-file', '-t', overlay.BACKUP).strip(), b'commit')

    def test_candidate_manifest_exact_rows_modes_and_leaf_allowlist(self):
        for raw in [self.manifest_raw + b' ', self.manifest_raw.replace(b'100644', b'100755', 1)]:
            with self.assertRaisesRegex(ValueError, 'manifest literal'):
                overlay.apply_union_overlay(self.repo, self.baseline, raw, self.sources)
            self.assertEqual(guard.verify_materialized(self.repo, self.baseline)['tree'], guard.TARGET)
        changed = dict(self.sources)
        changed['ordinary-new-source.py'] = b'data only'
        with self.assertRaisesRegex(ValueError, 'payload vector'):
            overlay.load_union_candidate(self.manifest_raw, changed, self.baseline)

    def test_missing_corrupt_extra_or_wrong_mode_payload_deny(self):
        missing = dict(self.sources); del missing[next(iter(missing))]
        corrupt = dict(self.sources); name = next(iter(corrupt)); corrupt[name] += b'\n'
        for sources in [missing, corrupt]:
            with self.assertRaises(ValueError):
                overlay.apply_union_overlay(self.repo, self.baseline, self.manifest_raw, sources)
            self.assertEqual(guard.verify_materialized(self.repo, self.baseline)['tree'], guard.TARGET)
        mode_path = self.repo / 'Cargo.toml'
        if not mode_path.exists():
            mode_path = self.repo / 'src-tauri/Cargo.toml'
        old = mode_path.stat().st_mode
        mode_path.chmod(old | 0o100)
        try:
            with self.assertRaisesRegex(ValueError, 'executable mode'):
                overlay.apply_union_overlay(self.repo, self.baseline, self.manifest_raw, self.sources)
        finally:
            mode_path.chmod(old)

    def test_full_source_after_drift_and_index_mismatch_deny(self):
        overlay.apply_union_overlay(self.repo, self.baseline, self.manifest_raw, self.sources)
        file = self.repo / 'src-tauri/Cargo.toml'
        original = file.read_bytes(); file.write_bytes(original + b'\n')
        with self.assertRaisesRegex(ValueError, 'SHA/size'):
            overlay.verify_union_candidate(self.repo, self.candidate)
        file.write_bytes(original)
        self.assertEqual(overlay.verify_union_candidate(self.repo, self.candidate)['files'], 1967)
        guard.run_git(self.repo, 'read-tree', guard.TARGET, index=True)
        with self.assertRaisesRegex(ValueError, 'index tree'):
            overlay.verify_union_candidate(self.repo, self.candidate)

    def test_partial_apply_and_receipt_failure_deny(self):
        native = guard.run_git
        primary = RuntimeError('ordinary partial native materialization interruption')
        receipt = self.root / 'partial-apply.json'
        with patch.object(guard, 'run_git', side_effect=lambda repo, *args, **kw:
                          (_ for _ in ()).throw(primary) if args[0] == 'checkout-index' else native(repo, *args, **kw)):
            with self.assertRaises(RuntimeError) as caught:
                self.invoke_production_main('apply', receipt)
        self.assertIs(caught.exception, primary)
        self.assertIs(json.loads(receipt.read_text())['passed'], False)
        with self.assertRaises(ValueError):
            overlay.verify_union_candidate(self.repo, self.candidate)
        self.write_owned_baseline()
        bad = self.root / 'owned-receipt-directory'; bad.mkdir(exist_ok=True)
        with patch.object(guard, 'run_git', side_effect=lambda repo, *args, **kw:
                          (_ for _ in ()).throw(primary) if args[0] == 'checkout-index' else native(repo, *args, **kw)):
            with self.assertRaises(BaseExceptionGroup) as caught:
                self.invoke_production_main('apply', bad)
        self.assertIs(caught.exception.exceptions[0], primary)
        self.assertIsInstance(caught.exception.exceptions[1], IsADirectoryError)

    def test_original_exception_cancel_and_close_preserved(self):
        native = guard.run_git
        cancellation = KeyboardInterrupt('owned ordinary cancellation, no nativecancel claim')
        receipt = self.root / 'cancel-closed.json'
        opened = []; actual = Path.open
        with patch.object(Path, 'open', side_effect=lambda file, *a, **kw:
                          opened.append(actual(file, *a, **kw)) or opened[-1], autospec=True), \
             patch.object(guard, 'run_git', side_effect=lambda repo, *args, **kw:
                          (_ for _ in ()).throw(cancellation) if args[0] == 'checkout-index' else native(repo, *args, **kw)):
            with self.assertRaises(KeyboardInterrupt) as caught:
                self.invoke_production_main('apply', receipt)
        self.assertIs(caught.exception, cancellation)
        self.assertTrue(opened)
        self.assertTrue(all(file.closed for file in opened))
        self.assertIs(json.loads(receipt.read_text())['passed'], False)
        self.write_owned_baseline()
        overlay.apply_union_overlay(self.repo, self.baseline, self.manifest_raw, self.sources)
        # Controlled print/receipt error injections are component negatives, not native close/cancel evidence.
        original_print = KeyboardInterrupt('owned printing cancellation')
        with patch('builtins.print', side_effect=original_print):
            with self.assertRaises(KeyboardInterrupt) as caught:
                self.invoke_production_main('verify', self.root / 'printed-after-close.json')
        self.assertIs(caught.exception, original_print)
        self.assertIs(json.loads((self.root / 'printed-after-close.json').read_text())['passed'], True)
        unknown = OSError('owned injected receipt close UNKNOWN; not a native close proof')
        with patch.object(guard, 'write_receipt', side_effect=unknown):
            with self.assertRaises(OSError) as caught:
                self.invoke_production_main('verify', self.root / 'unknown-receipt.json')
        self.assertIs(caught.exception, unknown)

    def test_current_manager_and_both_helper_lease_drift_deny(self):
        with self.owned_env():
            self.assertEqual(len(overlay.verify_union_helper_leases(self.manager)['helper_sources']), 2)
            for name in [original_overlay.HELPER, overlay.HELPER]:
                file = self.manager / name; raw = file.read_bytes(); file.write_bytes(raw + b'\n')
                try:
                    with self.assertRaisesRegex(ValueError, 'blob mismatch'):
                        overlay.verify_union_helper_leases(self.manager)
                finally:
                    file.write_bytes(raw)
            with patch.dict(os.environ, {'GITHUB_SHA': guard.BASE}):
                with self.assertRaises(ValueError):
                    overlay.verify_union_helper_leases(self.manager)

    def test_consumer_rust14_and_go23_vector_integrity(self):
        record, output, source, manager, helpers = self.owned_true_record()
        raw = (output / 'go9-data-race-test.log').read_bytes()
        changed = [raw.replace(('--- PASS: ' + overlay.GO_CASES[0]).encode(), b'--- ABSENT:', 1),
                   raw + ('\n--- PASS: ' + overlay.GO_CASES[0] + ' (0.00s)\n').encode()]
        with self.owned_env():
            for value in changed:
                (output / 'go9-data-race-test.log').write_bytes(value)
                with self.assertRaisesRegex(ValueError, 'unique'):
                    overlay.verify_union_compiler_result(record, 'go', output, source, manager, self.manager_head, helpers, self.manager, self.repo, ordinary_profile=True)
            (output / 'go9-data-race-test.log').write_bytes(raw)
            # Negative-only Rust input: strict ordinary profile rejects Rust before fullname checks.
            # This proves profile denial, not fullname-validation coverage or Windows execution.
            rust = copy.deepcopy(record); rust['mode'] = 'rust'; rust['compiler'] = 'WHOLE_TEST_COMPILE_AND_14_DATA_PASS'
            rust['componentContext'] = 'SYNTHETIC_NEGATIVE_PARSER_INPUT_NOT_WINDOWS_EXECUTION'
            for tool in ['rustup', 'rustc', 'cargo']:
                rust['runtime'][tool] = dict(record['runtime']['go'])
                if tool != 'rustup':
                    rust['runtime'][tool].update(payloadPath=record['runtime']['go']['path'],
                        payloadSha256Before=record['runtime']['go']['sha256Before'],
                        payloadSha256After=record['runtime']['go']['sha256After'])
            del rust['runtime']['go']
            rust['commands'] = [cmd for cmd in rust['commands'] if cmd['executable'] != 'go']
            for arguments, name in [([*original_overlay.CARGO_VECTOR, '--no-run'], 'cargo-whole-test-compile.log'),
                                    ([*original_overlay.CARGO_VECTOR, '--', '--list'], 'cargo-whole-test-list.log')]:
                rust['commands'].append({'executable': 'cargo', 'resolvedExecutable': record['runtime']['go']['path'],
                                        'arguments': arguments, 'exitCode': 0, 'log': name})
                (output / name).write_text('synthetic negative parser input only\n')
            for full in overlay.RUST_CASES:
                name = 'data-' + full.rsplit('::', 1)[1] + '.log'
                rust['commands'].append({'executable': 'cargo', 'resolvedExecutable': record['runtime']['go']['path'],
                                        'arguments': [*original_overlay.CARGO_VECTOR, full, '--', '--exact', '--nocapture', '--test-threads=1'],
                                        'exitCode': 0, 'log': name})
                (output / name).write_text('test ' + full + ' ... ok\ntest result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out\n')
            actual_list = '\n'.join(name + ': test' for name in overlay.RUST_CASES) + '\n'
            for value in [actual_list.replace(overlay.RUST_CASES[-1], 'different_namespace::' + overlay.RUST_CASES[-1].rsplit('::', 1)[1]),
                          actual_list + overlay.RUST_CASES[0] + ': test\n']:
                (output / 'cargo-whole-test-list.log').write_text(value)
                with self.assertRaisesRegex(ValueError, 'ordinary profile'):
                    overlay.verify_union_compiler_result(rust, 'rust', output, source, manager, self.manager_head, helpers, self.manager, self.repo, ordinary_profile=True)
            # There is intentionally no positive call for a synthetic Rust14 receipt.

    def test_consumer_typed_false_unknown_runtime_and_missing_log_deny(self):
        record, output, source, manager, helpers = self.owned_true_record()
        with self.owned_env():
            # Profile comes from the actual caller, never producer data, environment or a CLI flag.
            with self.assertRaisesRegex(ValueError, 'production profile'):
                overlay.verify_union_compiler_result(record, 'go', output, source, manager,
                    self.manager_head, helpers, self.manager, self.repo)
            for profile in [None, 0, 1, 'true', 'false']:
                with self.assertRaisesRegex(ValueError, 'exact boolean'):
                    overlay.verify_union_compiler_result(record, 'go', output, source, manager,
                        self.manager_head, helpers, self.manager, self.repo, ordinary_profile=profile)
            for command_index, original_command in enumerate(record['commands']):
                wrong_argv = copy.deepcopy(record)
                wrong_argv['commands'][command_index]['arguments'] = ['-c', 'owned negative, not executed']
                wrong_tool = copy.deepcopy(record)
                wrong_tool['commands'][command_index]['executable'] = 'git' if original_command['executable'] != 'git' else 'python'
                wrong_tool['commands'][command_index]['resolvedExecutable'] = record['runtime'][wrong_tool['commands'][command_index]['executable']]['path']
                wrong_path = copy.deepcopy(record)
                wrong_path['commands'][command_index]['resolvedExecutable'] += '.owned-wrong'
                nonstring = copy.deepcopy(record)
                nonstring['commands'][command_index]['arguments'] = [None]
                for item in [wrong_argv, wrong_tool, wrong_path, nonstring]:
                    with self.assertRaises(ValueError):
                        overlay.verify_union_compiler_result(item, 'go', output, source, manager,
                            self.manager_head, helpers, self.manager, self.repo, ordinary_profile=True)
            extra = copy.deepcopy(record)
            command = copy.deepcopy(extra['commands'][0]); command['log'] = 'ordinary-extra-command.log'
            (output / command['log']).write_bytes((output / 'git-version.log').read_bytes())
            extra['commands'].append(command)
            reordered = copy.deepcopy(record)
            reordered['commands'][3], reordered['commands'][4] = reordered['commands'][4], reordered['commands'][3]
            missing = copy.deepcopy(record); del missing['commands'][0]
            duplicate = copy.deepcopy(record); duplicate['commands'].append(copy.deepcopy(duplicate['commands'][0]))
            for item in [extra, reordered, missing, duplicate]:
                with self.assertRaises(ValueError):
                    overlay.verify_union_compiler_result(item, 'go', output, source, manager,
                        self.manager_head, helpers, self.manager, self.repo, ordinary_profile=True)
            for manager_root, destination, directory in [(self.manager / 'wrong', self.repo, output),
                                                        (self.manager, self.repo / 'wrong', output),
                                                        (self.manager, self.repo, output / 'wrong')]:
                with self.assertRaises(ValueError):
                    overlay.verify_union_compiler_result(record, 'go', directory, source, manager,
                        self.manager_head, helpers, manager_root, destination, ordinary_profile=True)
            for context in ['SYNTHETIC', None]:
                item = copy.deepcopy(record); item['componentContext'] = context
                with self.assertRaisesRegex(ValueError, 'ordinary profile'):
                    overlay.verify_union_compiler_result(item, 'go', output, source, manager,
                        self.manager_head, helpers, self.manager, self.repo, ordinary_profile=True)
            with patch.dict(os.environ, {'GITHUB_ACTIONS': 'true'}):
                with self.assertRaisesRegex(ValueError, 'ordinary profile'):
                    overlay.verify_union_compiler_result(record, 'go', output, source, manager,
                        self.manager_head, helpers, self.manager, self.repo, ordinary_profile=True)
        items = []
        for value in [False, 1, 'true', None]:
            item = copy.deepcopy(record); item['passed'] = value; items.append(item)
        for key in ['delegateInterruptedUnknown', 'sourceAfterInterruptedUnknown', 'sourceCancellation', 'runtimeAfterError']:
            item = copy.deepcopy(record); item[key] = False; items.append(item)
        item = copy.deepcopy(record); del item['runtime']['git']; items.append(item)
        item = copy.deepcopy(record); item['sourceAfter']['tree'] = guard.TARGET; items.append(item)
        item = copy.deepcopy(record); item['runId'] = 'different'; items.append(item)
        item = copy.deepcopy(record); item['commands'][0]['exitCode'] = False; items.append(item)
        item = copy.deepcopy(record); item['sourceAfter']['helper_digest'] = '0' * 64; items.append(item)
        with self.owned_env():
            for item in items:
                with self.assertRaises(ValueError):
                    overlay.verify_union_compiler_result(item, 'go', output, source, manager, self.manager_head, helpers, self.manager, self.repo, ordinary_profile=True)
            file = output / 'source-after.log'; raw = file.read_bytes(); file.unlink()
            try:
                with self.assertRaises(ValueError):
                    overlay.verify_union_compiler_result(record, 'go', output, source, manager, self.manager_head, helpers, self.manager, self.repo, ordinary_profile=True)
            finally:
                file.write_bytes(raw)
            producer = output / 'local-component.json'; producer.write_text(json.dumps(record))
            denied = output / 'terminal-denied.json'
            child = subprocess.run([sys.executable, str(self.manager / overlay.HELPER), 'verify-result', '--mode', 'go',
                '--compiler-result', str(producer), '--manifest', str(self.manager / 'scripts/windows_foundation_source_manifest.json'),
                '--manager', str(self.manager), '--destination', str(self.repo), '--receipt', str(denied)], capture_output=True, timeout=60)
            self.assertNotEqual(child.returncode, 0)
            self.assertIs(json.loads(denied.read_text())['passed'], False)
            self.assertIn(b'immutable remote baseline', child.stderr)

    def test_actual_main_pipeline_stop_keeps_final_receipt_and_skips_observer(self):
        for case in ['before', 'after', 'after-primary', 'after-pipeline', 'before-pipeline']:
            self.write_owned_baseline()
            self.run_owned_powershell(case)

    def test_literal_raw_checkout_true_false_and_unmatched_paths(self):
        supplemental = [original_overlay.HELPER, overlay.HELPER,
                        'scripts/windows_foundation_union_overlay_tests.py']
        all_paths = [*legacy_checkout.MANAGER_PATHS, *supplemental]
        manager_root = Path(__file__).resolve().parent.parent
        root_raw = (manager_root / '.gitattributes').read_bytes()
        nested_raw = (manager_root / 'scripts/.gitattributes').read_bytes()
        self.assertEqual(hashlib.sha256(root_raw).hexdigest(),
                         'e71eff1d357a5e428d8323d3f8d328e25c3aa57f522dae766fd44f4aa1e1e1bd')
        root_lines = [line.split() for line in root_raw.decode().splitlines()
                      if line.strip() and not line.startswith('#')]
        self.assertEqual(len(root_lines), 7)
        self.assertEqual({line[0] for line in root_lines}, set(legacy_checkout.MANAGER_PATHS))
        nested_lines = [line.split() for line in nested_raw.decode().splitlines()
                        if line.strip() and not line.startswith('#')]
        self.assertEqual(len(nested_lines), 3)
        self.assertEqual({line[0] for line in nested_lines},
                         {'/' + Path(name).name for name in supplemental})
        self.assertTrue(all(len(row) == 2 and row[1] == '-text' and
                            not any(c in row[0] for c in '*?[')
                            for row in [*root_lines, *nested_lines]))
        seed = self.root / 'literal-ten-seed'; seed.mkdir(exist_ok=True)
        for name in all_paths:
            dest = seed / name; dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes((manager_root / name).read_bytes())
        (seed / '.gitattributes').write_bytes(root_raw)
        (seed / 'scripts/.gitattributes').write_bytes(nested_raw)
        unmatched = ['scripts/ordinary-unmatched.py',
                     *['scripts/nested/' + Path(name).name for name in supplemental],
                     *['nested/' + name for name in supplemental]]
        for name in unmatched:
            file = seed / name; file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(b'owned unmatched\nsecond line\n')
        guard.run_git(seed, 'init', '-q'); guard.run_git(seed, 'add', '--', '.')
        guard.run_git(seed, '-c', 'user.name=Owned Source Control', '-c', 'user.email=owned@example.invalid',
                      'commit', '-qm', 'Owned literal ten checkout control; not CI')
        for mode in ['true', 'false']:
            clone = self.root / ('ten-checkout-' + mode)
            subprocess.run(['git', '-c', 'core.hooksPath=' + os.devnull, '-c', 'core.autocrlf=' + mode,
                            'clone', '--no-hardlinks', str(seed), str(clone)], check=True, capture_output=True, timeout=30)
            with patch.dict(os.environ, {'GITHUB_SHA': guard.run_git(clone, 'rev-parse', 'HEAD').decode().strip()}):
                for name in all_paths:
                    self.assertEqual((clone / name).read_bytes(), guard.run_git(clone, 'show', 'HEAD:' + name))
                    self.assertEqual(guard.run_git(clone, 'hash-object', '--no-filters', '--', name).strip(),
                                     guard.run_git(clone, 'rev-parse', 'HEAD:' + name).strip())
                    self.assertEqual(guard.run_git(clone, 'check-attr', '-z', 'text', '--', name).split(b'\0')[2], b'unset')
                self.assertEqual(guard.verify_manager(clone)['manager_files'], 7)
                self.assertEqual(len(overlay.verify_union_helper_leases(clone)['helper_sources']), 2)
                for name in unmatched:
                    source_raw = guard.run_git(clone, 'show', 'HEAD:' + name)
                    self.assertEqual((clone / name).read_bytes(),
                                     source_raw.replace(b'\n', b'\r\n') if mode == 'true' else source_raw)
                    self.assertEqual(guard.run_git(clone, 'check-attr', '-z', 'text', '--', name).split(b'\0')[2], b'unspecified')
                for name in supplemental[:2]:
                    file = clone / name; source_raw = file.read_bytes()
                    file.write_bytes(source_raw + b'owned changed helper\n')
                    try:
                        with self.assertRaisesRegex(ValueError, 'blob mismatch'):
                            overlay.verify_union_helper_leases(clone)
                    finally:
                        file.write_bytes(source_raw)


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0], '-v'])
