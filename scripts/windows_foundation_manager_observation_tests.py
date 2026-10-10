#!/usr/bin/env python3
"""Ordinary owned-native-Git controls; no Run-SourceCompile, VM or fake CI."""
import argparse
import ast
import hashlib
import importlib.util
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import windows_foundation_manager_observation as observer
import windows_foundation_source_guard as guard
PWSH = None


AFTER_CANCELLATION_CONTROL_PS = "param($Source,$PythonExecutable,$Manager,$Guard,$Manifest,$Observer,$OwnedOutput,$BeforeJSON,$Case,$OwnedPythonCopy)\n$ErrorActionPreference='Stop';Set-StrictMode -Version Latest\n$Tokens=$null;$Errors=$null\n$Ast=[System.Management.Automation.Language.Parser]::ParseFile($Source,[ref]$Tokens,[ref]$Errors)\nif($Errors.Count){throw 'Actual source parse error'}\nforeach($Name in @('Resolve-FoundationApplication','Invoke-CheckedCompiler','Invoke-ManagerSourceObservation')) {\n $F=@($Ast.FindAll({param($N)$N -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $N.Name -ceq $Name},$true))\n if($F.Count -ne 1){throw 'Actual function missing'};.([scriptblock]::Create($F[0].Extent.Text))\n}\n$RealInvoke=(Get-Item Function:\\Invoke-CheckedCompiler).ScriptBlock\n$NativeLogNames=[System.Collections.Generic.List[string]]::new()\nfunction Invoke-CheckedCompiler([string]$Executable,[string[]]$Arguments,[string]$LogName) {\n $NativeLogNames.Add($LogName)\n if(($Case -ceq 'before' -and $LogName -ceq 'management-byte-observation-Before.log') -or\n    ($Case -cne 'before' -and $Case -cne 'runtime-drift' -and $LogName -ceq 'management-byte-observation-After.log')) {\n  throw [System.OperationCanceledException]::new('ordinary observer cancellation')\n }\n $ActualResult = & $RealInvoke -Executable $Executable -Arguments $Arguments -LogName $LogName\n if($Case -ceq 'runtime-drift' -and $LogName -ceq 'management-byte-observation-After.log') {\n  $script:PythonExecutable=$OwnedPythonCopy\n }\n $ActualResult\n}\n$T=@($Ast.FindAll({param($N)$N -is [System.Management.Automation.Language.TryStatementAst] -and $N.Body.Extent.Text -match '^\\{\\s*Run-SourceCompile\\s'},$true))\nif($T.Count -ne 1){throw 'Actual top-level try/catch/finally missing'}\n$CatchText=$T[0].CatchClauses[0].Body.Extent.Text;$Catch=[scriptblock]::Create($CatchText.Substring(1,$CatchText.Length-2))\n$FinallyText=$T[0].Finally.Extent.Text;$Finally=[scriptblock]::Create($FinallyText.Substring(1,$FinallyText.Length-2))\n$Dispatch=@($Ast.FindAll({param($N)$N -is [System.Management.Automation.Language.IfStatementAst] -and $N.Extent.Text.StartsWith('if ($null -ne $ObservationCancellation) {')},$true))\nif($Dispatch.Count -ne 1){throw 'Actual cancellation dispatch missing'}\n$Output=New-Item -ItemType Directory -Path $OwnedOutput\n$Destination=Join-Path $OwnedOutput 'no-sut-was-restored'\n$ObservationCancellation=$null;$PrimaryFailure=$null\n$Receipt=[ordered]@{runtime=@{};commands=@();passed=$true;compiler='NOTRUN';sourceBefore=$null;sourceAfter=$null;\n managerSourceBefore=(Get-Content -Raw $BeforeJSON | ConvertFrom-Json);managerSourceAfter=$null;managerObservationFailed=$false}\nif($Case -ceq 'before') {\n try {Invoke-ManagerSourceObservation 'Before';throw 'Before cancellation swallowed'}catch {. $Catch}\n} elseif($Case -ceq 'after-primary') {\n try {throw [System.InvalidOperationException]::new('ordinary original primary delegate failure')}catch {. $Catch}\n}\n$OriginalPrimary=$PrimaryFailure\n. $Finally\nif(-not $NativeLogNames.Contains('management-after.log') -or $null -eq $Receipt.managerSourceAfter){throw 'Required original manager cleanup skipped'}\nif($Receipt.runtime.python.sha256Before -cne $Receipt.runtime.python.sha256After){throw 'Required original runtime-after verification skipped'}\nif(-not (Test-Path (Join-Path $Output 'compiler-result.json')) -or $Receipt.passed){throw 'Actual receipt/finaldeny skipped'}\nif($Case -ceq 'before' -and $NativeLogNames.Contains('management-byte-observation-After.log')){throw 'New After diagnostic child started after Before cancellation'}\nif($Case -cne 'before' -and $NativeLogNames.IndexOf('management-after.log') -gt $NativeLogNames.IndexOf('management-byte-observation-After.log')){throw 'After observation occurred before original cleanup'}\nif($Case -ceq 'runtime-drift') {\n if(-not $Receipt.Contains('runtimeAfterError') -or $Receipt.runtimeAfterError -cne 'Compiler/runtime source changed during the probe.') {throw 'Final original runtime guard did not reject path drift after actual observation'}\n if($null -ne $ObservationCancellation){throw 'Runtime drift invented cancellation'}\n .([scriptblock]::Create($Dispatch[0].Extent.Text))\n Write-Output 'PASS actual observer then final original runtime guard rejects owned-path drift; no compiler/native CI'\n return\n}\ntry {.([scriptblock]::Create($Dispatch[0].Extent.Text));throw 'Cancellation dispatch swallowed'}\ncatch {\n if($Case -ceq 'after-primary') {\n  if($_.Exception -isnot [System.AggregateException] -or $_.Exception.InnerExceptions.Count -ne 2 -or\n   -not [Object]::ReferenceEquals($_.Exception.InnerExceptions[0],$OriginalPrimary) -or\n   -not [Object]::ReferenceEquals($_.Exception.InnerExceptions[1],$ObservationCancellation) -or\n   $Receipt.error -cne 'ordinary original primary delegate failure'){throw 'Original failure/cancellation objects not retained'}\n } elseif($_.Exception -isnot [System.OperationCanceledException] -or\n   -not [Object]::ReferenceEquals($_.Exception,$ObservationCancellation)){throw 'Original typed cancellation not retained'}\n}\nWrite-Output ('PASS actual finally/catch/dispatch AST case '+$Case+'; original cleanup/receipt preserved; no compiler/native CI')\n"


class ObservationControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='manager-public-ordinary-')
        self.root = Path(self.temp.name) / 'manager'; self.root.mkdir()
        self.payload = {}
        for name in observer.MANAGER_PATHS:
            data = (SCRIPTS.parent / name).read_bytes(); self.payload[name] = data
            p = self.root / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data); p.chmod(0o644)
        self.git('init', '-q'); self.git('add', '--', *observer.MANAGER_PATHS)
        self.git('-c', 'user.name=Ordinary public source control', '-c', 'user.email=ordinary@invalid',
            'commit', '-qm', 'Owned public-source control, not candidate or CI')
        self.head = self.git('rev-parse', 'HEAD').decode().strip()
        self.old = os.environ.get('GITHUB_SHA'); os.environ['GITHUB_SHA'] = self.head
        self.name = '.github/workflows/windows-foundation-source-compile.yml'
        self.file = self.root / self.name

    def tearDown(self):
        if self.old is None: os.environ.pop('GITHUB_SHA', None)
        else: os.environ['GITHUB_SHA'] = self.old
        self.temp.cleanup()

    def git(self, *args):
        return subprocess.check_output(['git', '-c', 'core.autocrlf=false', '-C', str(self.root), *args], stderr=subprocess.DEVNULL)

    def test_exact_public_source_and_original_guard(self):
        result = observer.observe_manager_sources(self.root)
        self.assertEqual(result['fixed_source_count'], 7); self.assertFalse(result['admission'])
        self.assertFalse(result['native_authority']); self.assertTrue(result['all_raw_equal'])
        for row in result['rows']:
            self.assertEqual(row['expected'], row['actual'])
            self.assertEqual(row['actual']['git_blob'], self.git('hash-object', '--no-filters', '--', row['path']).decode().strip())
        self.assertLess(len(json.dumps(result).encode()), observer.MAX_RECEIPT_BYTES)
        self.assertEqual(guard.verify_manager(self.root)['manager_files'], 7)

    def test_crlf_metadata_does_not_admit_or_normalize_raw_source(self):
        changed = self.payload[self.name].replace(b'\n', b'\r\n'); self.file.write_bytes(changed)
        result = observer.observe_manager_sources(self.root)
        row = next(v for v in result['rows'] if v['path'] == self.name)
        self.assertFalse(row['raw_equal']); self.assertTrue(row['comparison_only_CRLF_to_LF_equals_expected'])
        self.assertTrue(row['comparison_only_expected_LF_to_CRLF_equals_actual'])
        self.assertGreater(row['actual']['CRLF'], 0)
        with self.assertRaisesRegex(ValueError, 'source blob mismatch'): guard.verify_manager(self.root)
        self.assertEqual(self.file.read_bytes(), changed)
        self.file.write_bytes(self.payload[self.name])
        self.assertEqual(guard.verify_manager(self.root)['manager_files'], 7)
        self.assertTrue(observer.observe_manager_sources(self.root)['all_raw_equal'])

    def test_arbitrary_mutation_is_not_crlf_explanation(self):
        changed = self.payload[self.name] + b'# owned raw mutation\n'; self.file.write_bytes(changed)
        row = next(v for v in observer.observe_manager_sources(self.root)['rows'] if v['path'] == self.name)
        self.assertFalse(row['raw_equal']); self.assertFalse(row['comparison_only_CRLF_to_LF_equals_expected'])
        with self.assertRaisesRegex(ValueError, 'source blob mismatch'): guard.verify_manager(self.root)
        self.assertEqual(self.file.read_bytes(), changed)

    def test_missing_public_file_preserves_original_rejection(self):
        self.file.unlink()
        with self.assertRaises(FileNotFoundError): observer.observe_manager_sources(self.root)
        with self.assertRaises(FileNotFoundError): guard.verify_manager(self.root)

    def test_symlink_never_reads_target(self):
        target = Path(self.temp.name) / 'owned-excluded-canary'; target.write_bytes(b'ordinary excluded canary')
        self.file.unlink(); self.file.symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'link rejected'): observer.observe_manager_sources(self.root)
        with self.assertRaises(ValueError): guard.verify_manager(self.root)
        self.assertEqual(target.read_bytes(), b'ordinary excluded canary')

    def test_actual_oversize_rejected_before_open(self):
        self.file.write_bytes(b'x' * (observer.MAX_SOURCE_BYTES + 1))
        with mock.patch.object(Path, 'open', side_effect=AssertionError('oversize file must not open')):
            with self.assertRaisesRegex(ValueError, 'kind/size rejected'): observer.observe_manager_sources(self.root)

    def test_expected_git_oversize_rejected_before_payload_read(self):
        self.file.write_bytes(b'x' * (observer.MAX_SOURCE_BYTES + 1)); self.git('add', '--', self.name)
        self.git('-c', 'user.name=Ordinary control', '-c', 'user.email=ordinary@invalid', 'commit', '-qm', 'Owned oversize negative')
        os.environ['GITHUB_SHA'] = self.git('rev-parse', 'HEAD').decode().strip()
        with mock.patch.object(observer, 'run_git', wraps=observer.run_git) as native:
            with self.assertRaisesRegex(ValueError, 'expected source size rejected'): observer.observe_manager_sources(self.root)
            self.assertFalse(any(c.args[1:3] == ('cat-file', 'blob') for c in native.call_args_list))

    def test_wrong_real_head_denies(self):
        os.environ['GITHUB_SHA'] = '0' * 40
        with self.assertRaisesRegex(ValueError, 'actual HEAD differs'): observer.observe_manager_sources(self.root)
        with self.assertRaisesRegex(ValueError, 'actual HEAD differs'): guard.verify_manager(self.root)

    def test_cli_cancellation_propagates_without_receipt(self):
        receipt = Path(self.temp.name) / 'cancel.json'
        argv = ['observer', '--manager', str(self.root), '--receipt', str(receipt)]
        with mock.patch.object(sys, 'argv', argv), mock.patch.object(observer, 'observe_manager_sources', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): observer.main()
        self.assertFalse(receipt.exists())

    def test_reader_close_occurs_even_on_read_exception(self):
        class Reader:
            closed = False
            def __enter__(inner): return inner
            def __exit__(inner, *args): inner.closed = True
            def fileno(inner): return 7
            def read(inner, limit): raise RuntimeError('ordinary reader failure')
        reader = Reader(); info = self.file.stat()
        with mock.patch.object(Path, 'open', return_value=reader), mock.patch.object(observer.os, 'fstat', return_value=info):
            with self.assertRaisesRegex(RuntimeError, 'ordinary reader failure'): observer.read_fixed_public_file(self.root, self.name)
        self.assertTrue(reader.closed)

    def test_actual_ps_observation_failure_then_original_delegate_and_final_deny(self):
        # Full actual PS function ASTs; local owned Git identity only, never Run-SourceCompile or GITHUB_ACTIONS.
        script = Path(self.temp.name) / 'ordinary-delegate.ps1'; output = Path(self.temp.name) / 'output'
        output.mkdir(); self.file.unlink()
        script.write_text(r'''param($Source,$PythonExecutable,$Manager,$Guard,$Manifest,$Observer,$Output)
$ErrorActionPreference='Stop'; Set-StrictMode -Version Latest
$Tokens=$null;$Errors=$null
$Ast=[System.Management.Automation.Language.Parser]::ParseFile($Source,[ref]$Tokens,[ref]$Errors)
if($Errors.Count){throw 'Actual source parse error'}
foreach($Name in @('Resolve-FoundationApplication','Invoke-CheckedCompiler','Invoke-ManagerSourceObservation')) {
 $F=@($Ast.FindAll({param($N)$N -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $N.Name -ceq $Name},$true))
 if($F.Count -ne 1){throw 'Actual function missing'};.([scriptblock]::Create($F[0].Extent.Text))
}
$Receipt=[ordered]@{runtime=@{};commands=@();passed=$true;managerObservationFailed=$false}
Invoke-ManagerSourceObservation 'Before'
if(-not $Receipt.managerObservationFailed){throw 'Actual observation failure lost'}
try {Invoke-CheckedCompiler 'python' @($Guard,'verify-manager','--manifest',$Manifest,'--manager',$Manager,'--receipt',(Join-Path $Output 'original-rejection.json')) 'original-rejection.log' | Out-Null;throw 'Original delegate unexpectedly admitted'}
catch {if($_.Exception.Message -notmatch 'actual exit 1'){throw};$Receipt.error=$_.Exception.Message}
Invoke-ManagerSourceObservation 'After'
$D=@($Ast.FindAll({param($N)$N -is [System.Management.Automation.Language.IfStatementAst] -and $N.Extent.Text -ceq 'if ($Receipt.managerObservationFailed) { $Receipt.passed = $false }'},$true))
if($D.Count -ne 1){throw 'Actual final deny AST missing'};.([scriptblock]::Create($D[0].Extent.Text))
if($Receipt.passed -or $Receipt.error -notmatch 'actual exit 1' -or $Receipt.commands.Count -ne 3){throw 'Original rejection/finaldeny/commands changed'}
# Controlled ordinary delegate cancellation: wrapper must rethrow the typed signal, not fabricate native failure.
function Invoke-CheckedCompiler {throw [System.OperationCanceledException]::new('ordinary cancellation')}
try {Invoke-ManagerSourceObservation 'Before';throw 'Cancellation swallowed'}
catch {if($_.Exception -isnot [System.OperationCanceledException]){throw}}
Write-Output 'PASS actual PS observer failures preserve actual raw delegate rejection and finaldeny; ordinary cancellation propagated'
''')
        result = subprocess.run([PWSH, '-NoLogo', '-NoProfile', '-File', str(script), str(SCRIPTS/'windows_foundation_source_compile.ps1'),
            sys.executable, str(self.root), str(SCRIPTS/'windows_foundation_source_guard.py'),
            str(SCRIPTS/'windows_foundation_source_manifest.json'), str(SCRIPTS/'windows_foundation_manager_observation.py'), str(output)], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout.decode(errors='replace') + result.stderr.decode(errors='replace'))
        self.assertIn(b'PASS actual PS observer failures', result.stdout)
        raw = json.loads((output/'original-rejection.json').read_text(encoding='utf-8-sig'))
        self.assertFalse(raw['passed']); self.assertEqual(raw['operation'], 'verify-manager')


    def test_actual_after_cancellation_cleanup_receipt_and_original_failure_objects(self):
        # Actual source finally/catch/dispatch AST portions; no Run-SourceCompile/CI gate/compiler execution.
        script = Path(self.temp.name) / 'ordinary-after-cancellation.ps1'
        script.write_text(AFTER_CANCELLATION_CONTROL_PS)
        before = Path(self.temp.name) / 'actual-before.json'
        before.write_text(json.dumps(guard.verify_manager(self.root)))
        for case in ('after', 'after-primary', 'before'):
            output = Path(self.temp.name) / ('actual-after-' + case)
            result = subprocess.run([PWSH, '-NoLogo', '-NoProfile', '-File', str(script),
                str(SCRIPTS/'windows_foundation_source_compile.ps1'), sys.executable, str(self.root),
                str(SCRIPTS/'windows_foundation_source_guard.py'), str(SCRIPTS/'windows_foundation_source_manifest.json'),
                str(SCRIPTS/'windows_foundation_manager_observation.py'), str(output), str(before), case], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout.decode(errors='replace') + result.stderr.decode(errors='replace'))
            self.assertIn(('PASS actual finally/catch/dispatch AST case '+case).encode(), result.stdout)
            receipt = json.loads((output/'compiler-result.json').read_text(encoding='utf-8-sig'))
            self.assertFalse(receipt['passed']); self.assertEqual(receipt['compiler'], 'NOTRUN')
            self.assertEqual(receipt['managerSourceAfter']['manager_commit'], self.head)
            if case == 'after-primary': self.assertEqual(receipt['error'], 'ordinary original primary delegate failure')


    def test_actual_after_observer_runtime_drift_is_rejected_by_final_original_guard(self):
        # Real helper/native Git executes first; only a test-owned byte-identical Python copy becomes the selected path.
        # The copied binary is never executed and no shared system/runtime bytes are changed.
        owned_python = Path(self.temp.name) / ('owned-python.exe' if os.name == 'nt' else 'owned-python')
        shutil.copy2(sys.executable, owned_python)
        self.assertEqual(hashlib.sha256(owned_python.read_bytes()).digest(), hashlib.sha256(Path(sys.executable).read_bytes()).digest())
        script = Path(self.temp.name) / 'ordinary-final-runtime.ps1'; script.write_text(AFTER_CANCELLATION_CONTROL_PS)
        before = Path(self.temp.name) / 'actual-before.json'; before.write_text(json.dumps(guard.verify_manager(self.root)))
        output = Path(self.temp.name) / 'actual-after-runtime-drift'
        result = subprocess.run([PWSH, '-NoLogo', '-NoProfile', '-File', str(script),
            str(SCRIPTS/'windows_foundation_source_compile.ps1'), sys.executable, str(self.root),
            str(SCRIPTS/'windows_foundation_source_guard.py'), str(SCRIPTS/'windows_foundation_source_manifest.json'),
            str(SCRIPTS/'windows_foundation_manager_observation.py'), str(output), str(before), 'runtime-drift', str(owned_python)], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout.decode(errors='replace') + result.stderr.decode(errors='replace'))
        self.assertIn(b'PASS actual observer then final original runtime guard', result.stdout)
        receipt = json.loads((output/'compiler-result.json').read_text(encoding='utf-8-sig'))
        self.assertFalse(receipt['passed']); self.assertEqual(receipt['compiler'], 'NOTRUN')
        self.assertEqual(receipt['runtimeAfterError'], 'Compiler/runtime source changed during the probe.')
        self.assertTrue(receipt['managerObservationAfter']['all_raw_equal'])
        self.assertFalse(receipt['managerObservationAfter']['admission'])
        self.assertEqual(receipt['managerSourceAfter']['manager_commit'], self.head)
        self.assertEqual(receipt['runtime']['python']['sha256Before'], receipt['runtime']['python']['sha256After'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--pwsh', required=True)
    args, remaining = parser.parse_known_args(); PWSH = args.pwsh
    unittest.main(argv=[sys.argv[0]] + remaining, verbosity=2)
