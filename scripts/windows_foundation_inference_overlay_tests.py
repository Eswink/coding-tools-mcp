#!/usr/bin/env python3
"""Ordinary owned Git/source controls, never a compiler/native-owner qualification."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import windows_foundation_source_guard as guard
import windows_foundation_inference_overlay as overlay
import windows_foundation_manager_checkout_tests as legacy_checkout

POOL = Path(sys.argv[1]).resolve()
PWSH = sys.argv[2] if len(sys.argv) > 2 else None
CONTROL_EVIDENCE = Path(sys.argv[3]).resolve() if len(sys.argv) > 3 else None
PS_SOURCE_CANCEL_CONTROL = 'param($Source,$PythonExecutable,$Manager,$Guard,$Manifest,$Observer,$InferenceOverlay,$Destination,$Output,$BeforeJSON,$SourceBeforeJSON,$Case)\n$ErrorActionPreference=\'Stop\';Set-StrictMode -Version Latest\n$Tokens=$null;$Errors=$null\n$Ast=[System.Management.Automation.Language.Parser]::ParseFile($Source,[ref]$Tokens,[ref]$Errors)\nif($Errors.Count){throw \'Actual source parse error\'}\nforeach($Name in @(\'Resolve-FoundationApplication\',\'Invoke-CheckedCompiler\',\'Invoke-ManagerSourceObservation\')) {\n $F=@($Ast.FindAll({param($N)$N -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $N.Name -ceq $Name},$true))\n if($F.Count -ne 1){throw \'Actual source function missing\'};.([scriptblock]::Create($F[0].Extent.Text))\n}\n$RealInvoke=(Get-Item Function:\\Invoke-CheckedCompiler).ScriptBlock\n$NativeLogNames=[System.Collections.Generic.List[string]]::new()\n$OwnedCancellation=if($Case -in @(\'after-pipeline\',\'before-pipeline\')){[System.Management.Automation.PipelineStoppedException]::new(\'ordinary pipeline cancellation\')}else{[System.OperationCanceledException]::new(\'ordinary source cancellation\')}\nfunction Invoke-CheckedCompiler([string]$Executable,[string[]]$Arguments,[string]$LogName) {\n $NativeLogNames.Add($LogName)\n if($Case -cne \'before\' -and $LogName -ceq \'source-after.log\'){throw $OwnedCancellation}\n & $RealInvoke -Executable $Executable -Arguments $Arguments -LogName $LogName\n}\n$T=@($Ast.EndBlock.Statements | Where-Object { $_ -is [System.Management.Automation.Language.TryStatementAst] -and $_.Body.Extent.Text -match \'^\\{\\s*Run-SourceCompile\\s\'})\nif($T.Count -ne 1){throw \'Actual top-level catch/finally missing\'}\n$CatchText=$T[0].CatchClauses[0].Body.Extent.Text;$Catch=[scriptblock]::Create($CatchText.Substring(1,$CatchText.Length-2))\n$FinallyText=$T[0].Finally.Extent.Text;$Finally=[scriptblock]::Create($FinallyText.Substring(1,$FinallyText.Length-2))\n$TailText=(@($Ast.EndBlock.Statements | Where-Object {$_.Extent.StartOffset -gt $T[0].Extent.EndOffset} | ForEach-Object {$_.Extent.Text}) -join "`n")\n$Tail=[scriptblock]::Create($TailText)\n$Mode=\'rust\'\n$ObservationCancellation=$null;$SourceCancellation=$null;$PrimaryFailure=$null;$DelegateHandled=$true\n$Receipt=[ordered]@{runtime=@{};commands=@();passed=$true;compiler=\'NOTRUN\';sourceOverlayStarted=$true;\n sourceBefore=(Get-Content -Raw $SourceBeforeJSON | ConvertFrom-Json);sourceAfter=$null;\n managerSourceBefore=(Get-Content -Raw $BeforeJSON | ConvertFrom-Json);managerSourceAfter=$null;managerObservationFailed=$false}\nif($Case -ceq \'before-pipeline\') {\n # Actual main AST with a controlled delegate before any SUT source restoration; no fake CI env.\n $Destination=Join-Path $Output \'no-sut-was-restored\'\n $Receipt.sourceBefore=$null\n $DelegateHandled=$false\n function Run-SourceCompile {throw $OwnedCancellation}\n .([scriptblock]::Create($T[0].Extent.Text))\n throw \'Original main host stop did not propagate\'\n}\nif($Case -ceq \'before\') {try {throw $OwnedCancellation}catch {. $Catch}}\nelseif($Case -ceq \'after-primary\') {try {throw [System.InvalidOperationException]::new(\'ordinary primary before cleanup\')}catch {. $Catch}}\n$OriginalPrimary=$PrimaryFailure\n. $Finally\nif(-not $NativeLogNames.Contains(\'management-after.log\') -or $null -eq $Receipt.managerSourceAfter){throw \'Original manager cleanup skipped\'}\nif($NativeLogNames.Contains(\'management-byte-observation-After.log\')){throw \'New observation child launched after source cancellation\'}\nif($Receipt.runtime.python.sha256Before -cne $Receipt.runtime.python.sha256After){throw \'Original runtime-after skipped\'}\nif(-not (Test-Path -LiteralPath (Join-Path $Output \'compiler-result.json\')) -or $Receipt.passed){throw \'Original receipt/finaldeny skipped\'}\nif($Case -ceq \'after-pipeline\') {\n if(-not [Object]::ReferenceEquals($SourceCancellation,$OwnedCancellation)){throw \'Original sourcecancel object absent before dispatch\'}\n [ordered]@{same_original_object=$true;type=$SourceCancellation.GetType().FullName;passed=$Receipt.passed;\n manager_cleanup=($null -ne $Receipt.managerSourceAfter);runtime_guard=($Receipt.runtime.python.sha256Before -ceq $Receipt.runtime.python.sha256After)} |\n ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $Output \'pre-dispatch-object-proof.json\')\n}\ntry {. $Tail;throw \'Typed source cancellation dispatch swallowed\'}\ncatch {\n if($Case -ceq \'after-primary\') {\n  if($_.Exception -isnot [System.AggregateException] -or $_.Exception.InnerExceptions.Count -ne 2 -or\n    -not [Object]::ReferenceEquals($_.Exception.InnerExceptions[0],$OriginalPrimary) -or\n    -not [Object]::ReferenceEquals($_.Exception.InnerExceptions[1],$OwnedCancellation)){throw \'Original primary/sourcecancel objects obscured\'}\n } elseif(-not [Object]::ReferenceEquals($_.Exception,$OwnedCancellation)){throw \'Original typed source cancellation object obscured\'}\n}\nWrite-Output (\'PASS actual PS source catch/finally/tail \'+$Case+\'; manager/runtime/receipt preserved; no compiler/VM/nativecancel proof\')\n'


class WindowsInferenceOverlayControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.owned = tempfile.TemporaryDirectory(prefix='ordinary-inference-', dir=POOL.parent)
        cls.root = Path(cls.owned.name)
        cls.repo = cls.root / 'sut'
        subprocess.run(['git', 'clone', '--no-hardlinks', '--no-checkout', str(POOL), str(cls.repo)], check=True, capture_output=True)
        cls.baseline = guard.load_manifest(Path(__file__).with_name('windows_foundation_source_manifest.json'))
        cls.manifest_raw, cls.source = overlay.fetch_inference_payload(cls.repo)
        cls.candidate = overlay.load_candidate(cls.manifest_raw, cls.source, cls.baseline)
        cls.manager = cls.root / 'manager'
        cls.manager.mkdir()
        guard.run_git(cls.manager, 'init', '-q')
        helper = cls.manager / overlay.HELPER
        helper.parent.mkdir()
        shutil.copyfile(Path(overlay.__file__), helper)
        for name in legacy_checkout.MANAGER_PATHS:
            dest = cls.manager / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes((Path(__file__).resolve().parent.parent / name).read_bytes())
        guard.run_git(cls.manager, 'add', '--', '.')
        guard.run_git(cls.manager, '-c', 'user.name=Owned Source Control', '-c', 'user.email=owned-source@example.invalid',
                      'commit', '-q', '-m', 'Owned ordinary source fixture')
        cls.manager_head = guard.run_git(cls.manager, 'rev-parse', 'HEAD').decode().strip()

    @classmethod
    def tearDownClass(cls):
        cls.owned.cleanup()

    def setUp(self):
        canary = self.repo / 'ordinary-untracked-canary.txt'
        if canary.exists():
            canary.unlink()
        guard.run_git(self.repo, 'read-tree', guard.TARGET, index=True)
        guard.run_git(self.repo, 'checkout-index', '--all', '--force', index=True)
        self.assertEqual(guard.verify_materialized(self.repo, self.baseline)['tree'], guard.TARGET)

    def test_original_baseline_and_new_full_identity(self):
        with self.assertRaisesRegex(ValueError, 'custom index'):
            overlay.verify_inference_candidate(self.repo, self.candidate)
        admitted = overlay.apply_inference_overlay(self.repo, self.baseline, self.manifest_raw, self.source)
        self.assertEqual((admitted['tree'], admitted['files'], admitted['native_authority']), (overlay.TARGET, 1953, False))
        self.assertEqual(admitted, overlay.verify_inference_candidate(self.repo, self.candidate))
        self.assertEqual(guard.run_git(self.repo, 'diff', '--name-only', guard.TARGET, overlay.TARGET).decode().splitlines(), [overlay.PATH])

    def test_native_immutable_fetch_exact_payload(self):
        manifest, source = overlay.fetch_inference_payload(self.repo)
        self.assertEqual(manifest, self.manifest_raw)
        self.assertEqual(source, self.source)
        self.assertEqual(guard.run_git(self.repo, 'cat-file', '-t', overlay.BACKUP).strip(), b'commit')

    def test_wrong_manifest_denied_before_write(self):
        with self.assertRaisesRegex(ValueError, 'manifest literal'):
            overlay.apply_inference_overlay(self.repo, self.baseline, self.manifest_raw + b' ', self.source)
        self.assertEqual(guard.verify_materialized(self.repo, self.baseline)['tree'], guard.TARGET)

    def test_wrong_source_denied_before_write(self):
        with self.assertRaisesRegex(ValueError, 'source literal'):
            overlay.apply_inference_overlay(self.repo, self.baseline, self.manifest_raw, self.source.replace(b'Result<()>', b'Result<()>x') + b' ')
        self.assertEqual(guard.verify_materialized(self.repo, self.baseline)['tree'], guard.TARGET)

    def test_wrong_baseline_denied_before_write(self):
        file = self.repo / overlay.PATH
        file.write_bytes(file.read_bytes() + b'\n')
        with self.assertRaisesRegex(ValueError, 'source SHA/size'):
            overlay.apply_inference_overlay(self.repo, self.baseline, self.manifest_raw, self.source)
        self.assertEqual(guard.run_git(self.repo, 'write-tree', index=True).decode().strip(), guard.TARGET)

    def test_new_custom_index_drift_denied(self):
        overlay.apply_inference_overlay(self.repo, self.baseline, self.manifest_raw, self.source)
        guard.run_git(self.repo, 'read-tree', guard.TARGET, index=True)
        with self.assertRaisesRegex(ValueError, 'custom index'):
            overlay.verify_inference_candidate(self.repo, self.candidate)

    def test_new_physical_source_drift_denied(self):
        overlay.apply_inference_overlay(self.repo, self.baseline, self.manifest_raw, self.source)
        file = self.repo / overlay.PATH
        file.write_bytes(file.read_bytes() + b'\n')
        with self.assertRaisesRegex(ValueError, 'source SHA/size'):
            overlay.verify_inference_candidate(self.repo, self.candidate)

    def test_protected_and_untracked_denied(self):
        overlay.apply_inference_overlay(self.repo, self.baseline, self.manifest_raw, self.source)
        protected = self.repo / guard.PROTECTED
        protected.write_bytes(protected.read_bytes() + b'\n')
        with self.assertRaisesRegex(ValueError, 'source SHA/size'):
            overlay.verify_inference_candidate(self.repo, self.candidate)
        guard.run_git(self.repo, 'checkout-index', '--force', '--', guard.PROTECTED, index=True)
        (self.repo / 'ordinary-untracked-canary.txt').write_bytes(b'Owned control; no source admission.')
        with self.assertRaisesRegex(ValueError, 'untracked'):
            overlay.verify_inference_candidate(self.repo, self.candidate)

    def test_partial_native_index_failure_denied(self):
        native = guard.run_git
        original = RuntimeError('ordinary owned checkout interruption')
        with patch.object(guard, 'run_git', side_effect=lambda repo, *args, **kw:
                          (_ for _ in ()).throw(original) if args[0] == 'checkout-index' else native(repo, *args, **kw)):
            with self.assertRaises(RuntimeError) as caught:
                overlay.apply_inference_overlay(self.repo, self.baseline, self.manifest_raw, self.source)
        self.assertIs(caught.exception, original)
        self.assertEqual(native(self.repo, 'write-tree', index=True).decode().strip(), overlay.TARGET)
        with self.assertRaisesRegex(ValueError, 'source SHA/size'):
            overlay.verify_inference_candidate(self.repo, self.candidate)

    def test_typed_cancel_preserved_and_after_denies(self):
        native = guard.run_git
        cancellation = KeyboardInterrupt('ordinary owned interruption, no nativecancel claim')
        receipt = self.root / 'cancel-receipt.json'
        argv = ['overlay', 'apply', '--manifest', str(Path(__file__).with_name('windows_foundation_source_manifest.json')),
                '--manager', str(self.manager), '--destination', str(self.repo), '--receipt', str(receipt)]
        opened = []
        actual_open = Path.open
        with patch.object(sys, 'argv', argv), patch.dict(os.environ, {'GITHUB_SHA': self.manager_head}), \
             patch.object(Path, 'open', side_effect=lambda file, *a, **kw: opened.append(actual_open(file, *a, **kw)) or opened[-1], autospec=True), \
             patch.object(guard, 'run_git', side_effect=lambda repo, *args, **kw:
                          (_ for _ in ()).throw(cancellation) if args[0] == 'checkout-index' else native(repo, *args, **kw)):
            with self.assertRaises(KeyboardInterrupt) as caught:
                overlay.main()
        self.assertIs(caught.exception, cancellation)
        self.assertTrue(opened)
        self.assertTrue(all(file.closed for file in opened))
        result = json.loads(receipt.read_text())
        self.assertFalse(result['passed'])
        self.assertEqual(result['error_type'], 'KeyboardInterrupt')
        with self.assertRaisesRegex(ValueError, 'source SHA/size'):
            overlay.verify_inference_candidate(self.repo, self.candidate)
        # Preserve both original typed failure and an actual owned receipt-path failure.
        self.setUp()
        receipt.mkdir(exist_ok=False) if not receipt.exists() else None
        bad_receipt = self.root / 'owned-directory-receipt'
        bad_receipt.mkdir(exist_ok=True)
        argv[-1] = str(bad_receipt)
        with patch.object(sys, 'argv', argv), patch.dict(os.environ, {'GITHUB_SHA': self.manager_head}), \
             patch.object(guard, 'run_git', side_effect=lambda repo, *args, **kw:
                          (_ for _ in ()).throw(cancellation) if args[0] == 'checkout-index' else native(repo, *args, **kw)):
            with self.assertRaises(BaseExceptionGroup) as both:
                overlay.main()
        self.assertIs(both.exception.exceptions[0], cancellation)
        self.assertIsInstance(both.exception.exceptions[1], IsADirectoryError)

    def test_actual_ps_overlay_cancellation_cleanup(self):
        self.assertIsNotNone(PWSH, 'Official explicit pwsh payload required, no silent skip')
        admitted = overlay.apply_inference_overlay(self.repo, self.baseline, self.manifest_raw, self.source)
        source_before = self.root / 'actual-owned-source-before.json'
        source_before.write_text(json.dumps(admitted))
        script = self.root / 'actual-ordinary-source-cancel.ps1'
        script.write_text(PS_SOURCE_CANCEL_CONTROL)
        before = self.root / 'actual-manager-before.json'
        with patch.dict(os.environ, {'GITHUB_SHA': self.manager_head}):
            before.write_text(json.dumps(guard.verify_manager(self.manager)))
            for case in ['before', 'after', 'after-primary', 'after-pipeline', 'before-pipeline']:
                output = self.root / ('actual-source-ps-' + case)
                output.mkdir(exist_ok=True)
                args = [PWSH, '-NoLogo', '-NoProfile', '-File', str(script),
                        str(Path(__file__).with_name('windows_foundation_source_compile.ps1')), sys.executable,
                        str(self.manager), str(Path(guard.__file__)),
                        str(Path(__file__).with_name('windows_foundation_source_manifest.json')),
                        str(Path(__file__).with_name('windows_foundation_manager_observation.py')),
                        str(Path(overlay.__file__)), str(self.repo), str(output), str(before), str(source_before), case]
                result = subprocess.run(args, capture_output=True)
                self.assertIsNotNone(CONTROL_EVIDENCE, 'Explicit outside private evidence destination required')
                evidence = CONTROL_EVIDENCE / case
                evidence.mkdir(parents=True, exist_ok=True)
                (evidence / 'actual-stdout.raw').write_bytes(result.stdout)
                (evidence / 'actual-stderr.raw').write_bytes(result.stderr)
                files = []
                for file in output.iterdir():
                    if file.is_file():
                        raw = file.read_bytes()
                        (evidence / file.name).write_bytes(raw)
                        files.append({'name': file.name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
                (evidence / 'actual-process-result.json').write_text(json.dumps({'exit': result.returncode, 'output_files': files}))
                self.assertEqual(result.returncode, 0, result.stdout.decode(errors='replace') + result.stderr.decode(errors='replace'))
                if case in ['after-pipeline', 'before-pipeline']:
                    receipt = json.loads((evidence / 'compiler-result.json').read_text(encoding='utf-8-sig'))
                    self.assertFalse(receipt['passed'])
                    if case == 'after-pipeline':
                        self.assertTrue(receipt['sourceAfterInterruptedUnknown'])
                    else:
                        self.assertTrue(receipt['delegateInterruptedUnknown'])
                    self.assertEqual(receipt['managerSourceAfter']['management_digest'], receipt['managerSourceBefore']['management_digest'])
                    self.assertEqual(receipt['runtime']['python']['sha256Before'], receipt['runtime']['python']['sha256After'])
                    self.assertEqual(receipt['compiler'], 'NOTRUN')
                    self.assertIn('no new diagnostic child', receipt['managerObservationAfterSkipped'])
                    self.assertNotIn('sourceAfterCancellation', receipt, 'Host signal is not catchable; do not fabricate a captured cancellation type or object')
                else:
                    self.assertIn(('PASS actual PS source catch/finally/tail ' + case).encode(), result.stdout)

    def test_eight_literal_raw_checkout_true_false_unmatched_and_mutation(self):
        scripts = Path(__file__).resolve().parent
        all_paths = list(legacy_checkout.MANAGER_PATHS) + [overlay.HELPER]
        seed = self.root / 'eight-checkout-seed'
        seed.mkdir(exist_ok=True)
        for name in all_paths:
            dest = seed / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes((scripts.parent / name).read_bytes())
        (seed / '.gitattributes').write_bytes((scripts.parent / '.gitattributes').read_bytes())
        unmatched = ['scripts/ordinary-not-helper.py', 'nested/' + overlay.HELPER]
        for name in unmatched:
            dest = seed / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b'Owned unleased text\nsecond line\n')
        guard.run_git(seed, 'init', '-q')
        guard.run_git(seed, 'add', '--', '.')
        guard.run_git(seed, '-c', 'user.name=Owned Source Control', '-c', 'user.email=owned-source@example.invalid', 'commit', '-qm', 'Owned eight source checkout')
        for mode in ['true', 'false']:
            clone = self.root / ('eight-checkout-' + mode)
            subprocess.run(['git', '-c', 'core.hooksPath=' + os.devnull, '-c', 'core.autocrlf=' + mode,
                            'clone', '--no-hardlinks', str(seed), str(clone)], check=True, capture_output=True)
            with patch.dict(os.environ, {'GITHUB_SHA': guard.run_git(clone, 'rev-parse', 'HEAD').decode().strip()}):
                for name in all_paths:
                    expected = guard.run_git(clone, 'show', 'HEAD:' + name)
                    self.assertEqual((clone / name).read_bytes(), expected)
                    self.assertEqual(guard.run_git(clone, 'hash-object', '--no-filters', '--', name).strip(), guard.run_git(clone, 'rev-parse', 'HEAD:' + name).strip())
                self.assertEqual(guard.verify_manager(clone)['manager_files'], 7)
                self.assertFalse(overlay.verify_helper_lease(clone)['native_authority'])
                for name in unmatched:
                    expected = guard.run_git(clone, 'show', 'HEAD:' + name)
                    self.assertEqual((clone / name).read_bytes(), expected.replace(b'\n', b'\r\n') if mode == 'true' else expected)
                    self.assertEqual(guard.run_git(clone, 'check-attr', '-z', 'text', '--', name).split(b'\0')[2], b'unspecified')
                file = clone / overlay.HELPER
                file.write_bytes(file.read_bytes() + b'\n')
                with self.assertRaisesRegex(ValueError, 'blob mismatch'):
                    overlay.verify_helper_lease(clone)

    def test_result_consumer_actual_owned_go4_positive_and_incomplete_case_denial(self):
        # Explicit owned component, not GitHub/Windows/VM and no forged CI environment.
        output = self.root / 'owned-go-consumer'
        output.mkdir()
        tools = {'git': shutil.which('git'), 'python': sys.executable,
                 'go': '/workspace/work/rc070/windows-tools/go/bin/go'}
        runtime = {}
        commands = []
        for name, path in tools.items():
            raw = Path(path).read_bytes()
            runtime[name] = {'path': path, 'sha256Before': hashlib.sha256(raw).hexdigest(), 'sha256After': None}
        with patch.dict(os.environ, {'GITHUB_SHA': self.manager_head}):
            for tool, args, log in [
                    ('git', ['--version'], 'git-version.log'),
                    ('python', ['-c', 'import sys; print(sys.version)'], 'python-version.log'),
                    ('python', [str(Path(overlay.__file__).with_name('windows_foundation_manager_observation.py')), '--manager', str(self.manager), '--receipt', str(output/'obs-before.json')], 'management-byte-observation-Before.log'),
                    ('python', [str(Path(guard.__file__)), 'verify-manager', '--manifest', str(Path(guard.__file__).with_name('windows_foundation_source_manifest.json')), '--manager', str(self.manager), '--receipt', str(output/'manager-before.json')], 'management-before.log'),
                    ('git', ['checkout-index', '--all', '--force'], 'source-restore.log'),
                    ('go', ['version'], 'go-version.log'),
                    ('go', ['test', '-v', '-count=1', *overlay.GO_FILES], 'go5-data-test.log'),
                    ('python', [str(Path(guard.__file__)), 'verify', '--manifest', str(Path(guard.__file__).with_name('windows_foundation_source_manifest.json')), '--manager', str(self.manager), '--destination', str(self.repo), '--receipt', str(output/'source-after.json')], 'source-after.log'),
                    ('python', [str(Path(guard.__file__)), 'verify-manager', '--manifest', str(Path(guard.__file__).with_name('windows_foundation_source_manifest.json')), '--manager', str(self.manager), '--receipt', str(output/'manager-after.json')], 'management-after.log'),
                    ('python', [str(Path(overlay.__file__).with_name('windows_foundation_manager_observation.py')), '--manager', str(self.manager), '--receipt', str(output/'obs-after.json')], 'management-byte-observation-After.log')]:
                # Actual owned checkout-index uses original custom index, never changes authority.
                env = os.environ.copy()
                if log == 'source-restore.log':
                    env['GIT_INDEX_FILE'] = str(self.repo/'.git/foundation-candidate.index')
                result = subprocess.run([tools[tool], *args], cwd=self.repo, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                (output/log).write_bytes(result.stdout)
                self.assertEqual(result.returncode, 0, result.stdout.decode(errors='replace'))
                commands.append({'executable': tool, 'resolvedExecutable': tools[tool], 'arguments': args, 'exitCode': result.returncode, 'log': log})
            source = guard.verify_materialized(self.repo, self.baseline)
            manager = guard.verify_manager(self.manager)
        for name, row in runtime.items():
            row['sha256After'] = hashlib.sha256(Path(row['path']).read_bytes()).hexdigest()
        baseline = dict(source, passed=True, payload_mode='LOCAL_OWNED_COMPONENT')
        record = {'passed': True, 'mode': 'go', 'compiler': 'DATA_TEST_PASS', 'pureSutTree': guard.TARGET,
                  'baselineSutTree': guard.TARGET, 'managerCommit': self.manager_head, 'nativePositive': 'NOTRUN',
                  'qualification': 'SOURCE_ONLY_BLOCKED', 'managerObservationFailed': False,
                  'sourceBaseline': baseline, 'sourceBefore': dict(source, passed=True), 'sourceAfter': dict(source, passed=True),
                  'managerSourceBefore': dict(manager, passed=True), 'managerSourceAfter': dict(manager, passed=True),
                  'runtime': runtime, 'commands': commands, 'componentContext': 'ACTUAL_OWNED_GO_NOT_CI'}
        admitted = overlay.verify_compiler_result(record, 'go', output, source, manager, self.manager_head)
        self.assertEqual(admitted['named_data_count'], 4)
        self.assertFalse(admitted['native_authority'])
        actual = (output/'go5-data-test.log').read_bytes()
        for altered in [actual.replace(('--- PASS: '+overlay.GO_CASES[0]).encode(), b'--- ABSENT:', 1),
                        actual + ('\n--- PASS: '+overlay.GO_CASES[0]+' (0.00s)\n').encode()]:
            (output/'go5-data-test.log').write_bytes(altered)
            with self.assertRaisesRegex(ValueError, 'four unique'):
                overlay.verify_compiler_result(record, 'go', output, source, manager, self.manager_head)
        (output/'go5-data-test.log').write_bytes(actual)
        type(self).consumer_fixture = (record, output, source, manager)
        self.assertIsNotNone(CONTROL_EVIDENCE)
        evidence = CONTROL_EVIDENCE/'actual-owned-go-consumer'
        evidence.mkdir()
        for file in output.iterdir():
            if file.is_file():
                shutil.copyfile(file, evidence/file.name)
        (evidence/'LOCAL-COMPONENT-RECORD.json').write_text(json.dumps(record, indent=2)+'\n')
        (evidence/'COMPONENT-ONLY-RESULT.json').write_text(json.dumps(admitted, indent=2)+'\n')

    def test_result_consumer_rejects_false_typed_unknown_missing_runtime_wrong_commands(self):
        self.assertTrue(hasattr(type(self), 'consumer_fixture'), 'Actual original Go positive must run first')
        record, output, source, manager = type(self).consumer_fixture
        corruptions = []
        for value in [False, 1, 'true', None]:
            item = copy.deepcopy(record); item['passed'] = value; corruptions.append(item)
        for flag in ['delegateInterruptedUnknown', 'sourceAfterInterruptedUnknown', 'sourceCancellation', 'runtimeAfterError']:
            item = copy.deepcopy(record); item[flag] = False; corruptions.append(item)
        item = copy.deepcopy(record); del item['runtime']['git']; corruptions.append(item)
        item = copy.deepcopy(record); item['runtime']['go']['sha256After']=None; corruptions.append(item)
        item = copy.deepcopy(record); item['sourceBefore']['tree']=overlay.TARGET; corruptions.append(item)
        item = copy.deepcopy(record); item['commands'][0]['exitCode']=False; corruptions.append(item)
        item = copy.deepcopy(record); item['commands'][0]['exitCode']=1; corruptions.append(item)
        item = copy.deepcopy(record); item['commands'][-1]['log']='source-after.log'; corruptions.append(item)
        item = copy.deepcopy(record); item['commands'][6]['arguments'][-1]='wrong.go'; corruptions.append(item)
        item = copy.deepcopy(record); item['sourceOverlayStarted']=True; corruptions.append(item)
        for item in corruptions:
            with self.assertRaises(ValueError):
                overlay.verify_compiler_result(item, 'go', output, source, manager, self.manager_head)
        with self.assertRaises(ValueError):
            overlay.verify_compiler_result(record, 'rust', output, source, manager, self.manager_head)
        # Full CLI is exercised only for denial; local component provenance is not native CI authority.
        result_file = output/'local-component-receipt.json'; result_file.write_text(json.dumps(record))
        with patch.dict(os.environ, {'GITHUB_SHA': self.manager_head}):
            for file in [result_file, output/'missing-receipt.json']:
                receipt = output/('terminal-denied-'+file.stem+'.json')
                child = subprocess.run([sys.executable, str(Path(overlay.__file__)), 'verify-result', '--mode', 'go',
                    '--compiler-result', str(file), '--manifest', str(Path(guard.__file__).with_name('windows_foundation_source_manifest.json')),
                    '--manager', str(self.manager), '--destination', str(self.repo), '--receipt', str(receipt)], capture_output=True)
                self.assertNotEqual(child.returncode, 0)
                self.assertIs(json.loads(receipt.read_text())['passed'], False)
        # Actual separate workflow run block must fail even when pinned setupPython is absent.
        workflow = Path(__file__).resolve().parent.parent/'.github/workflows/windows-foundation-source-compile.yml'
        text = workflow.read_text()
        section = text.split('      - name: Independently deny incomplete or false compiler receipts\n', 1)[1].split('      - name: Preserve actual result and failures', 1)[0]
        run = section.split('        run: |\n', 1)[1]
        run = '\n'.join(line[10:] for line in run.splitlines()).replace("${{ matrix.mode }}", 'go')
        for value in ['', '/missing/pinned-python-payload', '/ordinary/Microsoft/WindowsApps/python.exe']:
            script = output/'actual-workflow-consumer-negative.ps1'; script.write_text(run)
            env = os.environ.copy(); env['FOUNDATION_PYTHON_EXECUTABLE']=value
            child = subprocess.run([PWSH, '-NoLogo', '-NoProfile', '-File', str(script)], env=env, capture_output=True)
            self.assertNotEqual(child.returncode, 0)
            self.assertIn(b'no PATH fallback', child.stderr)
        # Real zero-exit host-stop receipts still deny in parser before any native compiler conclusion.
        for case in ['before-pipeline', 'after-pipeline']:
            file = CONTROL_EVIDENCE/case/'compiler-result.json'
            actual = json.loads(file.read_text(encoding='utf-8-sig'))
            self.assertIs(actual['passed'], False)
            with self.assertRaises(ValueError):
                overlay.verify_compiler_result(actual, 'rust', file.parent, source, manager, self.manager_head)

    def test_helper_raw_source_lease_denies_mutation(self):
        with patch.dict(os.environ, {'GITHUB_SHA': self.manager_head}):
            self.assertFalse(overlay.verify_helper_lease(self.manager)['native_authority'])
            file = self.manager / overlay.HELPER
            old = file.read_bytes()
            file.write_bytes(old + b'\n')
            try:
                with self.assertRaisesRegex(ValueError, 'blob mismatch'):
                    overlay.verify_helper_lease(self.manager)
            finally:
                file.write_bytes(old)


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0], '-v'])
