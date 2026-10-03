#!/usr/bin/env python3
"""Exact union and effective mutations for the selected CI parent only."""
import hashlib
import pathlib
import re
import runpy
import unittest

HERE = pathlib.Path(__file__).parent
ROOT = HERE.parents[1]
PARENT = runpy.run_path(str(HERE / 'parent-candidate-audit.py'))
OLD_NAMES = set(PARENT['OLD_PINS']) | set(PARENT['NAMES'])
NAMES = ('PilotSelectedParent.cs', 'PilotSelectedParentTests.cs')
PINS = {'PilotSelectedParent.cs': '6ed8db8e4b4dd0807e6c02ebc55ab4bf148a93667fddbedee3e932bd1e24a9aa', 'PilotSelectedParentTests.cs': 'e07a6734e5a70c7108fa64aa74ce07ed6105a8c4b726967b30dfe5858f9158f9'}


def coverage(names):
    assert len(OLD_NAMES) == 24
    assert names == OLD_NAMES | set(NAMES) | {'PilotCmdSentinel.cs', 'PilotCmdSentinelTests.cs', 'PilotCmdObservations.cs', 'PilotCmdObservationsTests.cs'}, 'unreviewed/missing executable fixture'
    assert len(names) == len({n.casefold() for n in names})


def inspect(files, old, workflow, pins=True):
    assert set(files) == set(NAMES) and set(old) == OLD_NAMES
    if pins:
        assert set(PINS) == set(NAMES)
        for name in NAMES:
            assert hashlib.sha256(files[name].encode()).hexdigest() == PINS[name]
    methods = PARENT['PILOT']['declared_methods']
    uncomment = PARENT['PILOT']['uncomment']
    previous = set().union(*(methods(s) for n, s in old.items() if n.endswith('.cs')))
    additions = set()
    for name, source in files.items():
        plain = uncomment(source)
        members = methods(source)
        assert not members & previous and not members & additions, 'partial member collision'
        additions |= members
        expected = {'BrokerDirectLauncher'} | ({'SelectedParentReceipt','SelectedParentOperations','PilotSelectedParent'} if name == NAMES[0] else {'SelectedParentTestTrace'})
        types = set(re.findall(r'\bclass\s+(\w+)', plain))
        assert types == expected
        for type_name in types:
            assert not re.search(r'\bstatic\s+' + type_name + r'\s*\(', plain)
        assert 'ModuleInitializer' not in plain and 'static readonly' not in plain
        assert not re.search(r'using\s+\w+\s*=', plain)
        for line in plain.splitlines():
            if re.search(r'^\s*(?:(?:public|private|protected|internal)\s+)?static\s+', line) and ' class ' not in line:
                assert '(' in line and '=' not in line.split('(')[0]
        for forbidden in ('DllImport','CreateFile(', 'CreateProcess(', 'OpenProcessToken(', 'DuplicateToken', 'AccessCheck(',
                          'SetThreadToken(', 'Impersonate', 'AdjustToken', 'SetTokenInformation(', 'ResumeThread(',
                          'AssignProcessToJobObject(', 'SetAccessControl(', 'OwnedAcl(', 'RegOpen', 'Registry.',
                          'WindowsIdentity', 'File.', 'Directory.', 'GetTempPath(', 'GetEnvironmentVariable(',
                          'PilotSetDisposition(', 'CreatePilotOwnedScope(', 'RemovePilotOwnedScope(',
                          'PilotEnumerateDirectory(', 'System.Linq', 'HashSet<', '.TryAdd('):
            assert forbidden not in plain, (name, forbidden)
    helper = files[NAMES[0]]
    tests = files[NAMES[1]]
    assert helper.count('Environment.GetFolderPath(') == 1
    assert 'Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData,Environment.SpecialFolderOption.DoNotVerify)' in helper
    assert 'SpecialFolderOption.Create' not in helper
    for required in ('Policy="localappdata_temp_ci_v1"', 'Path.Combine(exact,"Temp")',
                     'ParentCandidatePathSyntax(local)', 'String.Equals(exact,local,StringComparison.Ordinal)',
                     'String.Equals(Receipt.RequestedPath,Receipt.ResolvedPath,StringComparison.Ordinal)',
                     'selected.Substring(3).Split', 'parts.Length+1>32', 'selected.Substring(0,3)', 'PilotLeafName(part,false)',
                     'PilotOpenHandle(ref h,p,access,true,label,r)', 'return PilotValidateObject(h,p,true,identity,volume)',
                     'PilotValidateParent(h,p,identity,label,r)', 'return PilotCloseHandle(ref h,label,r)',
                     'index==Paths.Length-1?0x00020081u:0x000000A0u',
                     'if(handle==new IntPtr(-1)) {OwnershipUncertain=true;handle=IntPtr.Zero;}',
                     'Handles.Add(handle);if(handle!=IntPtr.Zero) Receipt.AcquiredHandles++',
                     'Operations.Inspect(handle,Paths[index],null,index==0?(uint?)null:Volume)',
                     'if(index==0) Volume=info.volume', 'Identities.Add(identity)',
                     'RecheckSelectedChain(); // Recheck all earlier pins',
                     'CheckSelectedEndpoint();Receipt.Acquired=true;',
                     'if(Closed || Failed || Paths==null || Handles.Count!=Identities.Count)',
                     'Operations.Inspect(Handles[index],Paths[index],Identities[index],Volume)',
                     'if(identity!=Identities[index]) throw',
                     'if(!ParentCandidateAclComplete(observation) || !ParentCandidateCheckerCleanup(observation) ||',
                     '!ParentCandidateNumber(Receipt.Metadata,"selected_parent_broker_owned",1)',
                     'if(guard==null || !Receipt.Acquired || Closed || Failed)',
                     'RecheckSelectedChain();CheckSelectedEndpoint();\n                guard(allowed);\n                RecheckSelectedChain();CheckSelectedEndpoint();Receipt.VerifiedGuards++;',
                     'catch(Exception failure) {MarkSelectedFailure(failure);throw;}',
                     'if(Closed) return Receipt.CloseConfirmed;', 'Closed=true;Receipt.CloseAttempted=true;',
                     'for(int index=Handles.Count-1;index>=0;index--)', 'IntPtr owned=Handles[index];Handles[index]=IntPtr.Zero;',
                     'if(!Operations.Close(ref owned,"selected_pin_"+index,Receipt.Metadata) || owned!=IntPtr.Zero) confirmed=false;',
                     'catch(Exception failure) {confirmed=false;MarkSelectedFailure(failure);}',
                     'confirmed=confirmed && !OwnershipUncertain && ParentCandidateCheckerCleanup(observation);',
                     'finally {lease.CloseSelectedParent();}'):
        assert required in helper, required
    assert helper.count('Operations.Open(') == 1 and helper.count('Operations.Close(') == 1
    assert helper.count('PilotOpenHandle(') == 1 and helper.count('PilotValidateParent(') == 1
    assert 'SelectedParentNativeOperations(' not in tests and 'ResolvePilotSelectedPath(' not in tests
    for required in ('RunSelectedParentContractTests()', 'open_before', 'open_after', 'invalid_output', 'changed_identity',
                     'close_false', 'close_throw', 'stale_success', 'unowned_token', 'free_unknown',
                     'no scan after closure', 'failed scan cannot be bypassed', 'root-to-leaf acquisition',
                     'ambiguous output prevents confirmed cleanup', 'exact ancestor and endpoint access'):
        assert required in tests, required
    runner = old['PilotRunner.cs']
    body = runner[runner.index('    public static PilotRunReceipt RunPilot('):]
    for required in ('CheckSelectedParentRecovery(temp,fixedMarkerGuard,new string[0])',
                     'result.InitialSelectedParent.Failure!=null || !result.InitialSelectedParent.FinalScanConfirmed || !result.InitialSelectedParent.CloseConfirmed',
                     'selectedParent=new PilotSelectedParent(temp,result.SelectedParent,SelectedParentNativeOperations());',
                     'selectedParent.AcquireSelectedParent();',
                     'markerGuard=delegate(string[] allowed) {selectedParent.GuardSelectedRecovery(fixedMarkerGuard,allowed);};',
                     'if(!selectedParent.CloseSelectedParent()) throw',
                     'if(selectedParent!=null) selectedParent.CloseSelectedParent();'):
        assert required in body, required
    order = ['result.InitialSelectedParent=CheckSelectedParentRecovery(', 'journal=new PilotJournal(',
             'selectedParent.AcquireSelectedParent();', 'scope=CreatePilotOwnedScope(',
             'row=RunPilotCase(', 'result.RunRootRemoved=RemovePilotOwnedScope(',
             'result.SelectedParent.FinalScanConfirmed=true;', 'if(!selectedParent.CloseSelectedParent())',
             'WritePilotEvidence(Path.Combine(evidence,"pilot-result.json")', 'journal.BindPreconditions(', 'journal.Resolve();']
    assert all(fragment in body for fragment in order)
    assert [body.index(f) for f in order] == sorted(body.index(f) for f in order)
    assert 'if(!result.RunRootRemoved) throw new InvalidOperationException("run scaffolding removal unconfirmed");\n            journal.VerifyPending();markerGuard(new string[]{journal.Path});\n            result.SelectedParent.FinalScanConfirmed=true;' in body
    success_tail=body[body.index('if(!selectedParent.CloseSelectedParent())'):body.index('        } catch(Exception failure)')]
    for forbidden in ('markerGuard(', 'fixedMarkerGuard(', 'AcquireSelectedParent(', 'GuardSelectedRecovery(', 'CreatePilotOwnedScope(', 'RemovePilotOwnedScope(', 'RunPilotCase('):
        assert forbidden not in success_tail, 'selected namespace operation after final close'
    assert body.index('if(journal!=null) journal.Failed=true;') < body.index('if(selectedParent!=null) selectedParent.CloseSelectedParent();')
    wrapper = old['run-pilot.ps1']
    for required in ('$selectedParent=[BrokerDirectLauncher]::ResolvePilotSelectedPath()',
                     '@($env:RUNNER_TEMP,[IO.Path]::GetTempPath(),$selectedParent)',
                     '[StringComparer]::OrdinalIgnoreCase', 'if(-not $roots.Add($exactRoot)) {continue}',
                     'if(-not $names.Add($candidate.Name))', 'if(-not $names.Add($item.Name))',
                     "$candidate.Name -ieq 'cleanup-uncertain.txt'", "$item.Name -ieq 'cleanup-uncertain.txt'",
                     '($candidate.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0',
                     '$entries -gt 100000', '$next.depth -gt 32',
                     'CheckSelectedParentRecovery($selectedParent,$markerGuard,[string[]]@())',
                     '$null -ne $preflight.Failure -or -not $preflight.FinalScanConfirmed -or -not $preflight.CloseConfirmed',
                     '[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None', '$preflightStream.Flush($true)',
                     '$owned=$preflightStream;$preflightStream=$null;$owned.Dispose()',
                     '$evidencePath,$selectedParent,$port'):
        assert required in wrapper, required
    assert wrapper.count('ResolvePilotSelectedPath()') == 1
    assert wrapper.index('CheckSelectedParentRecovery($selectedParent,') < wrapper.index('New-Item -ItemType Directory') < wrapper.index('::RunPilot(')
    scanner = wrapper[wrapper.index('function Assert-PilotRecoveryScope'):wrapper.index('$markerGuard=[Action[string[]]]')]
    calls=re.findall(r'\bGet-(?:Child)?Item\s+-LiteralPath\s+([^|\n]+)',scanner)
    assert len(calls)==5
    for call in calls:
        assert re.search(r'(?:^|\s)-Force(?:\s|$)',call) and re.search(r'-ErrorAction\s+Stop\b',call)
    assert '-Recurse' not in scanner and 'Where-Object' not in scanner
    assert workflow.count('& tests/windows-broker-direct/run-pilot.ps1') == 1
    assert '& tests/windows-broker-direct/run-parent-candidates.ps1' not in workflow
    for required in ('selected-parent-audit.py', 'RunSelectedParentContractTests()', 'RunParentCandidateContractTests()',
                     'RunPilotPolicyContractTests()', 'RunPilotGateContractTests()', 'RunPilotClassificationContractTests()',
                     '-Evidence evidence/pilot -Foundation evidence/foundation', 'timeout-minutes: 30', 'baseline/run.ps1', 'run-runtime.ps1'):
        assert required in workflow, required
    assert 'continue-on-error' not in workflow


class SelectedParentAudit(unittest.TestCase):
    def setUp(self):
        coverage({p.name for p in HERE.iterdir() if p.suffix.lower() in ('.cs','.ps1')})
        self.files={name:(HERE/name).read_text() for name in NAMES}
        self.old={name:(HERE/name).read_text() for name in OLD_NAMES}
        self.workflow=(ROOT/'.github/workflows/windows-lpac-runtime-diagnostic.yml').read_text()

    def test_exact_source_and_boundary(self): inspect(self.files,self.old,self.workflow)
    def test_hash_independent_boundary(self): inspect(self.files,self.old,self.workflow,False)
    def test_union_rejects_unknown_missing_collision(self):
        all_names=OLD_NAMES|set(NAMES)|{'PilotCmdSentinel.cs', 'PilotCmdSentinelTests.cs', 'PilotCmdObservations.cs', 'PilotCmdObservationsTests.cs'}
        coverage(all_names)
        for variant in (all_names|{'extra.cs'},all_names|{'hidden.ps1'},all_names-{'PilotSelectedParent.cs'},all_names|{'pilotselectedparent.cs'}):
            with self.assertRaises(AssertionError): coverage(variant)
    def test_partial_initializer_rejected(self):
        self.files[NAMES[0]]+='\nstatic BrokerDirectLauncher() {}'
        with self.assertRaises(AssertionError): inspect(self.files,self.old,self.workflow,False)
    def test_old_overload_rejected(self):
        self.files[NAMES[0]]+='\nstatic void OwnedAcl(string newArgument) {}'
        with self.assertRaises(AssertionError): inspect(self.files,self.old,self.workflow,False)
    def test_static_field_rejected(self):
        self.files[NAMES[0]]+='\nstatic object surprise = new object();'
        with self.assertRaises(AssertionError): inspect(self.files,self.old,self.workflow,False)


MUTATIONS=[
 ('attributes_only','PilotSelectedParent.cs','0x000000A0u','0x00000080u'),
 ('endpoint_rights','PilotSelectedParent.cs','0x00020081u','0x000F01FFu'),
 ('known_folder_create','PilotSelectedParent.cs','SpecialFolderOption.DoNotVerify','SpecialFolderOption.Create'),
 ('resolution_casefold','PilotSelectedParent.cs','Receipt.ResolvedPath,StringComparison.Ordinal)','Receipt.ResolvedPath,StringComparison.OrdinalIgnoreCase)'),
 ('ancestor_bound','PilotSelectedParent.cs','parts.Length+1>32','parts.Length+1>64'),
 ('ambiguous_ownership','PilotSelectedParent.cs','OwnershipUncertain=true;','OwnershipUncertain=false;'),
 ('prior_pin_recheck','PilotSelectedParent.cs','RecheckSelectedChain(); // Recheck all earlier pins','// Recheck all earlier pins'),
 ('stale_checker','PilotSelectedParent.cs','!ParentCandidateAclComplete(observation)','false'),
 ('checker_cleanup','PilotSelectedParent.cs','!ParentCandidateCheckerCleanup(observation)','false'),
 ('sticky_failure','PilotSelectedParent.cs','Closed || Failed) throw','Closed) throw'),
 ('guard_postcheck','PilotSelectedParent.cs','RecheckSelectedChain();CheckSelectedEndpoint();Receipt.VerifiedGuards++;','Receipt.VerifiedGuards++;'),
 ('reverse_close','PilotSelectedParent.cs','for(int index=Handles.Count-1;index>=0;index--)','for(int index=0;index<Handles.Count;index++)'),
 ('close_transfer','PilotSelectedParent.cs','Handles[index]=IntPtr.Zero;',''),
 ('independent_close','PilotSelectedParent.cs','confirmed=false;MarkSelectedFailure(failure);','confirmed=false;MarkSelectedFailure(failure);break;'),
 ('cleanup_false','PilotSelectedParent.cs','confirmed=confirmed && !OwnershipUncertain && ParentCandidateCheckerCleanup(observation);','confirmed=true;'),
 ('selected_scope','run-pilot.ps1','GetTempPath(),$selectedParent','GetTempPath()'),
 ('hidden_root','run-pilot.ps1','Get-Item -LiteralPath $exactRoot -Force','Get-Item -LiteralPath $exactRoot'),
 ('scan_error','run-pilot.ps1','Get-ChildItem -LiteralPath $exactRoot -Force -ErrorAction Stop','Get-ChildItem -LiteralPath $exactRoot -Force'),
 ('direct_marker','run-pilot.ps1',"$candidate.Name -ieq 'cleanup-uncertain.txt'","$candidate.Name -ieq 'ignored.txt'"),
 ('duplicate_entry','run-pilot.ps1','if(-not $names.Add($candidate.Name))','if($false)'),
 ('wrapper_selected_arg','run-pilot.ps1','$evidencePath,$selectedParent,$port','$evidencePath,$env:RUNNER_TEMP,$port'),
 ('preflight_gate','run-pilot.ps1','-or -not $preflight.CloseConfirmed',''),
 ('mandatory_lease','PilotRunner.cs','selectedParent.AcquireSelectedParent();',''),
 ('wrapped_guard','PilotRunner.cs','selectedParent.GuardSelectedRecovery(fixedMarkerGuard,allowed);','fixedMarkerGuard(allowed);'),
 ('final_close_gate','PilotRunner.cs','if(!selectedParent.CloseSelectedParent()) throw','if(false) throw'),
 ('post_close_scan','PilotRunner.cs','result.Phase="completion_preconditions_persisted";','markerGuard(new string[]{journal.Path});result.Phase="completion_preconditions_persisted";'),
 ('failure_closes','PilotRunner.cs','if(selectedParent!=null) selectedParent.CloseSelectedParent();',''),
]
for label,file,before,after in MUTATIONS:
    def test(self,file=file,before=before,after=after):
        source=self.files if file in self.files else self.old
        self.assertIn(before,source[file]);source[file]=source[file].replace(before,after,1)
        with self.assertRaises(AssertionError): inspect(self.files,self.old,self.workflow,False)
    setattr(SelectedParentAudit,'test_mutation_'+label,test)

if __name__=='__main__': unittest.main(verbosity=2)
