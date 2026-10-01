#!/usr/bin/env python3
"""Portable exact-source and negative audits for a read-only three-parent observer."""
import hashlib
import pathlib
import re
import runpy
import unittest

HERE = pathlib.Path(__file__).parent
ROOT = HERE.parents[1]
PILOT = runpy.run_path(str(HERE / 'pilot-audit.py'))
OLD_PINS = dict(PILOT['LEGACY_PINS'], **PILOT['PILOT_PINS'])
NAMES = ('ParentCandidateObservations.cs', 'ParentCandidateTests.cs', 'run-parent-candidates.ps1')
PINS = {'ParentCandidateObservations.cs': '1084b425a6268010388a0de255d8eead80706504f861229929bf125403a3a456', 'ParentCandidateTests.cs': '3e02679996733a7755ad2d107dfc4ea98fd92e635d3df13cb8c8ac638c3be640', 'run-parent-candidates.ps1': '431b8043b8ad2f911f066e07708a9afea3c641e26d00d65d71c87ae37a10fc3b'}


def fixture_coverage(discovered):
    expected = set(OLD_PINS) | set(NAMES)
    assert len(OLD_PINS) == 21 and not (set(OLD_PINS) & set(NAMES))
    assert discovered == expected, 'missing or unreviewed executable fixture file'
    assert len(discovered) == len({name.casefold() for name in discovered})


def inspect(files, old, workflow, check_pins=True):
    assert set(files) == set(NAMES) and set(old) == set(OLD_PINS)
    if check_pins:
        assert set(PINS) == set(NAMES)
        for name, digest in dict(OLD_PINS, **PINS).items():
            assert hashlib.sha256((old | files)[name].encode()).hexdigest() == digest, name
    old_members = set().union(*(PILOT['declared_methods'](s) for n, s in old.items() if n.endswith('.cs')))
    new_members = set()
    for name, source in files.items():
        if not name.endswith('.cs'):
            continue
        plain = PILOT['uncomment'](source)
        members = PILOT['declared_methods'](plain)
        assert not members & old_members, 'new partial member collides with frozen helper'
        assert not members & new_members, 'duplicate observer member'
        new_members |= members
        types = set(re.findall(r'\bclass\s+([A-Za-z_]\w*)', plain))
        allowed_types = {'BrokerDirectLauncher'} | ({'ParentCandidateRow', 'ParentCandidateBatch', 'ParentCandidateOperations'} if name == 'ParentCandidateObservations.cs' else {'ParentCandidateTestTrace'})
        assert types == allowed_types, 'unreviewed nested type or shadow'
        assert not re.search(r'using\s+\w+\s*=', plain), 'type alias rejected'
        for type_name in types:
            assert not re.search(r'\bstatic\s+' + re.escape(type_name) + r'\s*\(', plain), 'type initializer'
        assert 'ModuleInitializer' not in plain and 'static readonly' not in plain
        assert 'HashSet<' not in plain and 'System.Linq' not in plain and '.TryAdd(' not in plain
        for line in plain.splitlines():
            if re.search(r'^\s*(?:(?:public|private|protected|internal)\s+)?static\s+', line) and ' class ' not in line:
                assert '(' in line and '=' not in line.split('(')[0], 'static field initializer'
        for forbidden in ('DllImport', 'SetThreadToken(', 'Impersonate', 'AdjustToken', 'OpenProcessToken(',
                          'DuplicateToken', 'AccessCheck(', 'SetTokenInformation(', 'CreateProcess', 'ResumeThread(',
                          'AssignProcessToJobObject(', 'CreateJobObject(', 'CreateDirectory', 'Directory.',
                          'SetAccessControl(', 'SetFileSecurity(', 'RegOpen', 'Registry.', 'GetTempPath(',
                          'WindowsIdentity', 'File.Delete(', 'File.Move(', 'File.Copy(', 'File.Open(',
                          'PilotSetDisposition(', 'CreatePilotOwnedScope(', 'RemovePilotOwnedScope(',
                          'RunPilot(', 'PreparePilotSubject(', 'OwnedAcl(', 'PilotEnumerateDirectory('):
            assert forbidden not in plain, (name, forbidden)
    observer = files['ParentCandidateObservations.cs']
    tests = files['ParentCandidateTests.cs']
    assert observer.count('Environment.GetFolderPath(') == 1
    assert 'Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData,Environment.SpecialFolderOption.DoNotVerify)' in observer
    assert 'SpecialFolderOption.Create' not in observer and 'Environment.GetEnvironmentVariable' not in observer
    assert re.findall(r'Label="([^"\n]+)"', observer) == ['runner_temp_control','local_application_data','local_application_data_temp']
    for required in ('PilotLeafName(part,false)',
                     'r.Identities.TryGetValue(label+"_owner_category",out owner)',
                     'r.Numbers.TryGetValue(ace+"_flags",out flags)',
                     'r.Numbers.TryGetValue(label+"_first_rejected_ace_index",out rejected)',
                     'rejected<0 || rejected>=count',
                     'Path.Combine(batch.Rows[1].ValidatedPath,"Temp")',
                     'Path.GetDirectoryName(batch.Rows[2].ValidatedPath),batch.Rows[1].ValidatedPath,StringComparison.Ordinal)',
                     'Path.GetFileName(batch.Rows[2].ValidatedPath),"Temp",StringComparison.Ordinal',
                     'PilotOwnedPath(row.RequestedPath)',
                     'PilotOpenHandle(ref handle,path,0x00020081,true,label,r)',
                     'return PilotValidateObject(handle,path,true,identity,volume)',
                     'PilotValidateParent(handle,path,identity,label,r)',
                     'return PilotCloseHandle(ref handle,label,r)',
                     'row.Stage=="open" && !row.DirectoryHandleAcquired && openRecorded && (error==2 || error==3) && native!=null && native.NativeErrorCode==error',
                     'row.CheckerCompleted && row.InitialObjectVerified && row.FinalIdentityRechecked && row.CleanupConfirmed',
                     'row.Failure==null && row.RawOpenError==0 && ParentCandidateAclComplete(row)',
                     'row.DirectoryCloseReturned && handleCleared && ParentCandidateNumber(r,label+"_close_confirmed",1)',
                     '(!row.DirectoryHandleAcquired || ParentCandidateNumber(r,label+"_close_error",0))',
                     'ParentCandidateCheckerCleanup(row)',
                     'if(row.InitialObjectVerified)',
                     'operations.Inspect(handle,row.ValidatedPath,row.InitialIdentity,row.Volume)',
                     'if(row.FinalIdentity!=row.InitialIdentity) throw',
                     'row.DirectoryCloseReturned=operations.Close(ref handle,row.Label,row.Checker)',
                     'if(!proceed) {row.Outcome="not_attempted_prior_uncertainty"',
                     'proceed=row.ObservationCompleted && row.CleanupConfirmed',
                     'item.Key.EndsWith("_unowned_output",StringComparison.Ordinal) && item.Value!=0',
                     'row.CheckerAttempted && !ParentCandidateNumber(r,label+"_security_free_confirmed",1)',
                     'label+"_broker_owner_data_free_confirmed",1', 'label+"_broker_owner_token_close_confirmed",1',
                     'label+"_broker_owner_token_close_error",0',
                     'row.ObservationCompleted=row.CleanupConfirmed && (row.CandidateTrustVerified || rejection || row.InitialOpenMissing)',
                     'selected_for_execution=false', 'observation_only=true,selection_made=false',
                     'pilot_invoked=false', 'created_directory_count=0,created_profile_count=0,created_process_count=0'):
        assert required in observer, required
    for call in ('PilotOpenHandle(', 'PilotValidateObject(', 'PilotValidateParent(', 'PilotCloseHandle('):
        assert observer.count(call) == 1, call
        assert call not in tests, 'managed contracts must use injected operations'
    assert 'ObserveParentCandidates(' not in tests and 'Environment.GetFolderPath(' not in tests
    assert 'RunParentCandidateContractTests()' in tests
    for required in ('PrepareParentCandidateBatch(', 'literal Temp containment', 'base alias labeled without replacement',
                     'unvalidated base cannot form a child', 'lookup exception stops later fixed row',
                     'missing or invalid owner evidence rejected', 'C:\\\\NUL', 'C:\\\\temp\\\\CON.txt'):
        assert required in tests, required
    row_body=observer[observer.index('    static void ObserveParentCandidateRow('):observer.index('    static ParentCandidateBatch RunParentCandidateObservations(')]
    assert row_body.index('if(!row.PathValidated)') < row_body.index('operations.Open(')
    assert row_body.count('operations.Close(') == 1
    assert row_body.index('finally {') < row_body.index('operations.Inspect(handle,row.ValidatedPath,row.InitialIdentity,row.Volume)') < row_body.index('operations.Close(')
    assert row_body.index('operations.CheckParent(') < row_body.index('row.CheckerCompleted=true;')
    assert row_body.index('operations.Close(') < row_body.index('FinalizeParentCandidateRow(row,handle==IntPtr.Zero)')
    wrapper = files['run-parent-candidates.ps1']
    assert "ObserveParentCandidates($env:RUNNER_TEMP)" in wrapper
    assert 'selected_for_execution=$false' in wrapper and 'observation_only=$true' in wrapper
    assert "'parent-candidates.json'" in wrapper
    assert '[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None' in wrapper
    assert '$bytes.Length -gt 1048576' in wrapper and '$stream.Flush($true)' in wrapper
    assert '$owned=$stream;$stream=$null' in wrapper and '$owned.Dispose()' in wrapper
    assert 'if(-not $result.ObservationCompleted -or -not $result.CleanupConfirmed)' in wrapper
    assert wrapper.index('$owned.Dispose()') < wrapper.index('if(-not $result.ObservationCompleted -or -not $result.CleanupConfirmed)')
    assert 'Get-Item -LiteralPath $evidencePath -Force -ErrorAction Stop' in wrapper
    assert '-not $directory.PSIsContainer -or ($directory.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0' in wrapper
    for forbidden in ('New-Item', 'RunPilot(', 'Remove-Item', 'Set-Acl', 'Resolve-Path', 'GetTempPath',
                      'TcpListener', 'Start-Process', 'run-pilot.ps1', 'run-direct.ps1', 'run-qualification.ps1'):
        assert forbidden not in wrapper, forbidden
    assert wrapper.count('Get-ChildItem') == 1 and '-LiteralPath $PSScriptRoot -Filter' in wrapper
    assert 'continue-on-error' not in workflow
    for required in ('timeout-minutes: 30', 'baseline/run.ps1', 'run-runtime.ps1', 'qualification-audit.py',
                     'pilot-audit.py', 'parent-candidate-audit.py', 'RunPilotPolicyContractTests()',
                     'RunPilotGateContractTests()', 'RunPilotClassificationContractTests()', 'RunParentCandidateContractTests()',
                     '& tests/windows-broker-direct/run-parent-candidates.ps1 -Evidence evidence'):
        assert required in workflow, required
    for forbidden in ('& tests/windows-broker-direct/run-pilot.ps1', '& tests/windows-broker-direct/run-direct.ps1',
                      '& tests/windows-broker-direct/run-qualification.ps1'):
        assert forbidden not in workflow, forbidden


class ParentCandidateAudit(unittest.TestCase):
    def setUp(self):
        fixture_coverage({p.name for p in HERE.iterdir() if p.suffix.lower() in ('.cs', '.ps1')})
        self.files = {name: (HERE / name).read_text() for name in NAMES}
        self.old = {name: (HERE / name).read_text() for name in OLD_PINS}
        self.workflow = (ROOT / '.github/workflows/windows-lpac-runtime-diagnostic.yml').read_text()

    def test_exact_source_and_boundary(self):
        inspect(self.files, self.old, self.workflow)

    def test_hash_independent_boundary(self):
        inspect(self.files, self.old, self.workflow, False)

    def mutate(self, name, before, after):
        self.assertIn(before, self.files[name])
        self.files[name] = self.files[name].replace(before, after, 1)
        with self.assertRaises(AssertionError):
            inspect(self.files, self.old, self.workflow, False)

    def test_unknown_missing_and_case_collision(self):
        names=set(OLD_PINS) | set(NAMES)
        for changed in (names | {'hidden.cs'}, names | {'new.ps1'}, names - {'DirectLauncher.cs'}, names | {'parentcandidateobservations.cs'}):
            with self.assertRaises(AssertionError): fixture_coverage(changed)

    def test_no_type_initializer(self):
        self.files['ParentCandidateObservations.cs'] += '\nstatic BrokerDirectLauncher() {}'
        with self.assertRaises(AssertionError): inspect(self.files,self.old,self.workflow,False)

    def test_no_static_field_initializer(self):
        self.files['ParentCandidateObservations.cs'] += '\nstatic readonly object surprise = new object();'
        with self.assertRaises(AssertionError): inspect(self.files,self.old,self.workflow,False)

    def test_no_old_member_overload(self):
        self.files['ParentCandidateObservations.cs'] += '\nstatic void OwnedAcl(string x) {}'
        with self.assertRaises(AssertionError): inspect(self.files,self.old,self.workflow,False)

    def test_no_candidate_selection(self):
        self.mutate('run-parent-candidates.ps1','selected_for_execution=$false','selected_for_execution=$true')

    def test_no_output_replacement(self):
        self.mutate('run-parent-candidates.ps1','[IO.FileMode]::CreateNew','[IO.FileMode]::Create')

    def test_capture_bound_required(self):
        self.mutate('run-parent-candidates.ps1','$bytes.Length -gt 1048576','$bytes.Length -lt 0')

    def test_flush_required(self):
        self.mutate('run-parent-candidates.ps1','$stream.Flush($true)','$stream.Flush()')

    def test_evidence_no_reparse(self):
        self.mutate('run-parent-candidates.ps1','-not $directory.PSIsContainer -or ($directory.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0','-not $directory.PSIsContainer')

    def test_cleanup_gate_required(self):
        self.mutate('run-parent-candidates.ps1','-not $result.ObservationCompleted -or -not $result.CleanupConfirmed','-not $result.ObservationCompleted')

    def test_no_runtime_invocation(self):
        self.workflow += '\n& tests/windows-broker-direct/run-pilot.ps1\n'
        with self.assertRaises(AssertionError): inspect(self.files,self.old,self.workflow,False)


MUTATIONS = [
 ('preopen_device_rejection','ParentCandidateObservations.cs','PilotLeafName(part,false)','String.IsNullOrEmpty(part)'),
 ('owner_evidence_required','ParentCandidateObservations.cs','r.Identities.TryGetValue(label+"_owner_category",out owner)','r.Identities.TryGetValue(label+"_other",out owner)'),
 ('ace_flags_required','ParentCandidateObservations.cs','r.Numbers.TryGetValue(ace+"_flags",out flags)','r.Numbers.TryGetValue(ace+"_other",out flags)'),
 ('first_rejection_evidence','ParentCandidateObservations.cs','r.Numbers.TryGetValue(label+"_first_rejected_ace_index",out rejected)','r.Numbers.TryGetValue(label+"_other",out rejected)'),

 ('known_folder_no_create','ParentCandidateObservations.cs','Environment.SpecialFolderOption.DoNotVerify','Environment.SpecialFolderOption.Create'),
 ('candidate_directory_rights','ParentCandidateObservations.cs','PilotOpenHandle(ref handle,path,0x00020081,true,label,r)','PilotOpenHandle(ref handle,path,0x000F01FF,true,label,r)'),
 ('exact_temp_parent','ParentCandidateObservations.cs','Path.GetDirectoryName(batch.Rows[2].ValidatedPath),batch.Rows[1].ValidatedPath,StringComparison.Ordinal','Path.GetDirectoryName(batch.Rows[2].ValidatedPath),batch.Rows[1].ValidatedPath,StringComparison.OrdinalIgnoreCase'),
 ('missing_only_at_open','ParentCandidateObservations.cs','row.Stage=="open" && !row.DirectoryHandleAcquired','!row.DirectoryHandleAcquired'),
 ('missing_error_match','ParentCandidateObservations.cs',' && native.NativeErrorCode==error',''),
 ('normal_checker_completion','ParentCandidateObservations.cs','row.CheckerCompleted && row.InitialObjectVerified','row.InitialObjectVerified'),
 ('final_identity_required','ParentCandidateObservations.cs','row.FinalIdentityRechecked && row.CleanupConfirmed','row.CleanupConfirmed'),
 ('cleanup_required','ParentCandidateObservations.cs','row.FinalIdentityRechecked && row.CleanupConfirmed','row.FinalIdentityRechecked'),
 ('failure_cannot_pass','ParentCandidateObservations.cs','row.Failure==null && row.RawOpenError==0','row.RawOpenError==0'),
 ('exact_final_identity','ParentCandidateObservations.cs','if(row.FinalIdentity!=row.InitialIdentity) throw','if(false) throw'),
 ('unexpected_token_output','ParentCandidateObservations.cs','item.Key.EndsWith("_unowned_output",StringComparison.Ordinal) && item.Value!=0','item.Key.EndsWith("_unowned_output",StringComparison.Ordinal) && false'),
 ('security_free_required','ParentCandidateObservations.cs','row.CheckerAttempted && !ParentCandidateNumber(r,label+"_security_free_confirmed",1)','false'),
 ('token_close_required','ParentCandidateObservations.cs','label+"_broker_owner_token_close_confirmed",1','label+"_broker_owner_token_close_confirmed",0'),
 ('stop_next_observation','ParentCandidateObservations.cs','proceed=row.ObservationCompleted && row.CleanupConfirmed','proceed=true'),
 ('handle_cleared_required','ParentCandidateObservations.cs','row.DirectoryCloseReturned && handleCleared &&','row.DirectoryCloseReturned &&'),
 ('close_success_required','ParentCandidateObservations.cs','(!row.DirectoryHandleAcquired || ParentCandidateNumber(r,label+"_close_error",0))','true'),
 ('no_stale_observation','ParentCandidateObservations.cs','row.ObservationCompleted=row.CleanupConfirmed &&','row.ObservationCompleted='),
]


def mutation_test(item):
    def test(self):
        self.mutate(item[1], item[2], item[3])
    return test


for item in MUTATIONS:
    setattr(ParentCandidateAudit, 'test_mutation_' + item[0], mutation_test(item))


if __name__ == '__main__':
    unittest.main()
