#!/usr/bin/env python3
"""Portable exact-source/union/mutation audits. Managed C# behavior tests run separately in CI."""
import hashlib
import pathlib
import re
import unittest

HERE = pathlib.Path(__file__).parent
ROOT = HERE.parents[1]
LEGACY_PINS = {'DirectNative.cs': '36123701edbeb11c8227ff903b7c399201acccc4bcaa0e7fe489f14fe028af3f', 'DirectHandles.cs': '927d73169be1bea2f578ad79fa9d508b35d46c000295b41269a93577087c57ca', 'DirectCases.cs': '2dd6d671e8e75c4b64620c08c974eeeb5a4a4c2690b143b716fa8efb31f66932', 'DirectLauncher.cs': '309adbf2b5c00712a914631c1b2849c5ecdac8fd42feb7f43ee7d5869f033a48', 'DirectCapture.cs': 'ee66abb5bc9c79e696eec72d35e97fffdc039d393289fde20db31be0c41c56bd', 'run-direct.ps1': '099443bd437ac9d9b4633ec741089c4df50c734ca3a5ff0eb902f540ba9c0a09', 'AccessCheckObservations.cs': '4731a82554776644026e5006e0ca56644737bed9144a6ef4bae6dcc2b5eeb4a9', 'QualificationSubjects.cs': '833f1deaadaa0ef1eb80f1bad0e8c09c87c076948a07666daad3cae7ae660196', 'QualificationCleanup.cs': '08f0cec58e8079317681a77412c4e480991a5941b4ef68c75b955c639e193b96', 'run-qualification.ps1': '74ba3042c51f232fc5c2b414b7989bb36098f774f4abb7c4f5ab5804817390a3'}
PILOT_NAMES = (
    'PilotOwnedFiles.cs', 'PilotSubjects.cs', 'PilotPolicy.cs', 'PilotJournal.cs',
    'PilotGates.cs', 'PilotRunner.cs', 'PilotClassification.cs', 'PilotPolicyTests.cs',
    'PilotGateTests.cs', 'PilotClassificationTests.cs', 'run-pilot.ps1',
)
PILOT_PINS = {'PilotOwnedFiles.cs': '7638cf9dffa7859bde43df943cfa3bee5384a7c9ee7d52f587abdca43c43ad92', 'PilotSubjects.cs': 'bb12619c082a1b26a6d6ccd5a6af5012a2d64764ebe6c856856ad1be14e36c92', 'PilotPolicy.cs': '1791fa47cf3a5afd62bd4029c4e8a085c674269a0cad2b5190cfd8621bbb16ea', 'PilotJournal.cs': '815e611986e04abd5efa934c2f56e20d50c42ccc0d6b98fbb1850de2d271fa21', 'PilotGates.cs': 'e5f5b416ea63f1ab96014d145a802f82a9de1b809d118ca58de4e93d7c5c88ad', 'PilotRunner.cs': '30c6c51ad2b26b202f776bd453c5fa2de2311eea3e12eca2a42eb179c64e9e2e', 'PilotClassification.cs': 'e8438e7e516ad0a9e842489df11b800e53be65519ff9211c13f6e29e227078ab', 'PilotPolicyTests.cs': 'd6c37576dc802590888616cbe4f8eadf8420718da4e4cb92db6f7fb090a968d8', 'PilotGateTests.cs': 'c1b5495f780633da8c0656e097f54cdea74de2d002274d6afe2afae8194f2b8d', 'PilotClassificationTests.cs': 'b0d8c3613743f9913715e343298611cd78ccd2c48f3591c5c85a1203c4a3dfad', 'run-pilot.ps1': '81ddeaab12758c9dbde5983a5140629d435e6d20e87fb68de1c3c7edfacf45c1'}


def uncomment(source):
    return re.sub(r'/\*.*?\*/|//[^\n]*', '', source, flags=re.S)


def declared_methods(source):
    return set(re.findall(r'^\s*(?:(?:public|private|protected|internal|static|extern|sealed|override|virtual|unsafe|new)\s+)+[^\n=;{}()]*?\b([A-Za-z_]\w*)\s*\(', uncomment(source), re.M))


def fixture_coverage(discovered):
    assert set(PILOT_PINS) == set(PILOT_NAMES)
    assert len(LEGACY_PINS) == 10 and not (set(LEGACY_PINS) & set(PILOT_NAMES))
    assert discovered == set(LEGACY_PINS) | set(PILOT_NAMES), 'missing or unreviewed executable fixture file'
    assert len(discovered) == len({name.casefold() for name in discovered})


def inspect(files, legacy, check_pins=True):
    assert set(files) == set(PILOT_NAMES)
    assert set(legacy) == set(LEGACY_PINS)
    if check_pins:
        for name, digest in {**LEGACY_PINS, **PILOT_PINS}.items():
            assert hashlib.sha256((files | legacy)[name].encode()).hexdigest() == digest, name
    old_members = set().union(*(declared_methods(s) for n, s in legacy.items() if n.endswith('.cs')))
    new_members = set()
    for name, source in files.items():
        if not name.endswith('.cs'):
            continue
        plain = uncomment(source)
        members = declared_methods(source)
        assert not members & old_members, 'new partial member collides with frozen helper'
        assert not members & new_members, 'duplicate new member/overload'
        new_members |= members
        allowed_types = {'BrokerDirectLauncher'} | {
            'PilotOwnedFiles.cs': {'PilotOwnedScope', 'PilotDirectoryEntry', 'PilotCleanupBudget'},
            'PilotJournal.cs': {'PilotJournal'},
            'PilotRunner.cs': {'PilotCaseReceipt', 'PilotRunReceipt'},
        }.get(name, set())
        types = set(re.findall(r'\bclass\s+([A-Za-z_]\w*)', plain))
        assert types == allowed_types, 'unreviewed partial/nested type'
        for type_name in types:
            assert not re.search(r'\bstatic\s+' + re.escape(type_name) + r'\s*\(', plain), 'type initializer rejected'
        assert 'ModuleInitializer' not in plain and 'static readonly' not in plain
        assert 'HashSet<' not in plain, 'keep legacy Add-Type default assembly compatibility'
        for line in plain.splitlines():
            if re.search(r'^\s*(?:(?:public|private|protected|internal)\s+)?static\s+', line) and ' class ' not in line:
                assert '(' in line and '=' not in line.split('(')[0], 'non-method static initializer/member'
        for forbidden in ('SetThreadToken(', 'Impersonate', 'AdjustToken', 'SetTokenInformation(', 'CreateProcessAsUser',
                          'CreateProcessWithToken', 'SetAccessControl(', 'SetFileSecurity(', 'RegOpen', 'Registry.',
                          'WindowsIdentity.GetCurrent', 'File.Delete(', 'Directory.Delete(', 'GetStdHandle('):
            assert forbidden not in plain, (name, forbidden)
    subjects = files['PilotSubjects.cs']
    policy = files['PilotPolicy.cs']
    owned = files['PilotOwnedFiles.cs']
    journal = files['PilotJournal.cs']
    runner = files['PilotRunner.cs']
    gates = files['PilotGates.cs']
    wrapper = files['run-pilot.ps1']
    facts = files['PilotClassification.cs']
    assert re.findall(r'capabilities\.\w+\s*=[^;]*;', subjects) == ['capabilities.Sid=s.Sid;']
    assert re.findall(r'limits\.Basic\.flags\s*=[^;]*;', subjects) == ['limits.Basic.flags=KILL_ON_JOB_CLOSE;']
    for required in ('CREATE_SUSPENDED|EXTENDED|UNICODE|0x08000000u',
                     'new IntPtr(0x20002),handles,new IntPtr(3*IntPtr.Size)',
                     'OpenPrivate(ref input,inputPath,0x80000000,3,true,"stdin",r)',
                     'OpenPrivate(ref output,Path.Combine(s.Workspace,"stdout.txt"),0x40000000,1,true,"stdout",r)',
                     'OpenPrivate(ref error,Path.Combine(s.Workspace,"stderr.txt"),0x40000000,1,true,"stderr",r)',
                     'if(profileCheckpoint==null)', 'profileCheckpoint();', 'pilot_profile_owned',
                     'pilot_profile_name', 'pilot_created_pid', 'pilot_created_tid',
                     'candidateProcess=new PROCESS_INFORMATION();', 's.OwnershipCertain=false',
                     'PilotCloseHandle(ref writer,"stdin_writer",r)', 'pilot_copied_bytes_verified'):
        assert required in subjects, required
    assert 'CloseOwned(ref ' not in subjects
    assert subjects.index('profileCheckpoint();') < subjects.index('OwnedAcl(s.Outside') < subjects.index('CreateProcess(exe,')
    assert 'ResumeThread(' not in subjects and 'AssignProcessToJobObject(' not in subjects
    assert 'OpenProcessToken(PilotGetCurrentProcess(),0x8,out returnedToken)' in owned
    assert re.findall(r'GetTokenInformation\(token,(\d+),', owned) == ['1', '1']
    for required in ('if(opened && validOutput) token=returnedToken;', 'if(!opened || !validOutput)',
                     'if(!inspected || (flags&1)!=0)', 'needed>65536', 'if(!queried || returned<header+8 || returned>needed)',
                     'pointer-start<header', 'returned-(pointer-start)<8', 'sidBytes>returned-(pointer-start)',
                     'finally {closed=PilotCloseHandle(ref token,', 'if(!freed || !closed)',
                     'IntPtr owned=handle;handle=IntPtr.Zero;', 'PilotOwnerCategory(owner,user)',
                     'if(GetFileType(handle)!=1 || (info.attributes&0x440)!=0',
                     'PilotSetDisposition(handle,4,ref delete,1)', 'scope.RemovalAttempted=true',
                     'if(error!=18)', 'offset>PilotDirectoryBuffer-header', 'nameBytes>PilotDirectoryBuffer-offset-header',
                     'if(names.ContainsKey(name))', 'names.Add(name,true);', 'if((info.attributes&1)!=0)', 'if((mask&writeMask)!=0',
                     'scope.ParentIdentity', 'scope.RootIdentity', 'scope.Volume',
                     'String.Equals(entry.Name,scope.Leaf,StringComparison.OrdinalIgnoreCase)', 'scope.RemovalConfirmed=valid && closed'):
        assert required in owned, required
    observer = uncomment(owned[owned.index('    static void RecordPilotParentAcl('):owned.index('    static FILE_INFO PilotValidateParent(')])
    validator = uncomment(owned[owned.index('    static FILE_INFO PilotValidateParent('):owned.index('    static List<PilotDirectoryEntry> PilotEnumerateDirectory(')])
    assert 'RecordPilotParentAcl(descriptor,user,label,r);' in validator
    assert validator.index('RecordPilotParentAcl(descriptor,user,label,r);') < validator.index('if((owner!=user') < validator.index('foreach(GenericAce raw')
    observation_order = ['_acl_observation_completed"]=0;', 'foreach(GenericAce raw', '_acl_observed_ace_count"]=observed;', '_acl_observation_completed"]=1;']
    for fragment in observation_order: assert fragment in observer, fragment
    assert [observer.index(fragment) for fragment in observation_order] == sorted(observer.index(fragment) for fragment in observation_order)
    assert 'int observed=0;' in observer and 'observed++;' in observer
    for forbidden in ('break;', 'continue;', 'return;', '_broker_owned', '_first_rejected', 'Create', 'OpenProcessToken(', 'GetTokenInformation(', 'SetFile', 'throw new'):
        assert forbidden not in observer, 'metadata pass must not change authority or terminate early'
    for exact in ('if((owner!=user && owner!="S-1-5-18" && owner!="S-1-5-32-544") ||',
                  '(descriptor.ControlFlags&ControlFlags.DiscretionaryAclPresent)==0 || descriptor.DiscretionaryAcl==null)',
                  'if(ace==null || ace.IsCallback || (ace.AceQualifier!=AceQualifier.AccessAllowed && ace.AceQualifier!=AceQualifier.AccessDenied))',
                  'if(ace.AceQualifier!=AceQualifier.AccessAllowed) continue;', 'const uint writeMask=0x500D0156;',
                  'if((mask&~0xF01F01FFu)!=0)', 'if((mask&writeMask)!=0 && sid!=user && sid!="S-1-5-18" && sid!="S-1-5-32-544")',
                  'int currentIndex=aceIndex++;', '_first_rejected_ace_index\"]=-1;', '_first_rejected_ace_index\"]=currentIndex;'):
        assert exact in validator, exact
    assert len(re.findall(r'\bif\s*\(', validator)) == 8, 'new policy branch requires explicit review'
    assert validator.count('continue;') == 1 and 'AceFlags' not in validator, 'inheritance does not relax this observation-only predicate'
    assert re.findall(r'\bmask\s*=[^;]*;', validator) == ['mask=unchecked((uint)ace.AccessMask);']
    assert re.findall(r'\bsid\s*=[^;]*;', validator) == ['sid=ace.SecurityIdentifier.Value;']
    assert re.findall(r'_first_rejected_ace_index"\]=([^;]+);', validator) == ['-1', 'currentIndex', 'currentIndex', 'currentIndex']
    reasons = re.findall(r'_first_rejected_reason"\]=\"([^\"]+)\";', validator)
    assert reasons == ['not_evaluated', 'none', 'owner_or_dacl', 'unsupported_ace_shape', 'unsupported_access_mask', 'untrusted_write_grant']
    for reason, message in (('owner_or_dacl','pilot parent is not broker-owned'),
                            ('unsupported_ace_shape','pilot parent ACL shape unsupported'),
                            ('unsupported_access_mask','pilot parent ACL access mask unsupported'),
                            ('untrusted_write_grant','pilot parent has an untrusted write grant')):
        tail=validator[validator.index('="'+reason+'";'):]
        assert tail.index('throw new InvalidOperationException("'+message+'")') < tail.index('\n            }')
    assert 'CloseOwned(ref token' not in owned and 'CloseChecked(PilotGetCurrentProcess' not in owned
    assert 'Identities[label+"_broker_owner_sid"]' not in owned
    assert 'DuplicateToken' not in uncomment(owned) and 'AccessCheck(' not in owned
    for required in ('r.TokenVerified', 'r.Assigned || r.Resumed', 'PilotPinnedMethodDiagnostics(r)',
                     '"profile_create_hresult","pilot_process_outputs_owned","pilot_copied_bytes_verified"',
                     '"source_token_requested_access"', '"duplicate_desired_access"', '"token_close_error"',
                     '"duplicate_close_error"', '"accesscheck_observer_cleanup_confirmed"',
                     'ordinary?3:2', 'ordinary?1:0', 'PilotDescriptorDecision(r,"world",0,0',
                     'PilotKnownAccessCheckKey(key)', 'suffix==', '"_error",5', '"_privilege_count_raw"'):
        assert required in policy, required
    assert 'r.Kind!=\"ordinary\" && r.Kind!=\"reference\"' in policy
    assert not re.search(r'ordinary\s*&&\s*r\.Kind|ordinary\s*\?\s*r\.Kind', policy)
    assert 'NetworkDenialProven=true' not in runner + facts
    assert runner.count('AssignProcessToJobObject(') == 1 and runner.count('ResumeThread(') == 1
    for required in ('ObserveQualificationSource(s)', 'ObserveAccessCheckToken(s.SourceToken,r.ProfileSid,r)',
                     'PilotCloseHandle(ref s.SourceToken,"token",r)', 'VerifyPilotSignature(r,ordinary)',
                     '!VerifyPilotSignature(r,false)', 'row.PreResumeReady=PilotMayResume(',
                     'if(!row.PreResumeReady) throw', 'StopQualificationSubject(s)',
                     's.ProcessStopped && s.JobDrained', 'if(!row.IndividualResourceCleanupConfirmed)',
                     'row.CaptureIntegrityConfirmed=captured', 'DeleteAppContainerProfile(s.Profile)',
                     'row.ProfileDeleteApiConfirmed=hr==0', 'if(!row.ProfileDeleteApiConfirmed) throw',
                     'row.OwnedRootRemoved=RemovePilotOwnedScope(owned,r)',
                     'row.CleanupPreconditionsConfirmed=PilotCleanupPreconditions(row)',
                     'journal.BindPreconditions(serialize(row));', 'journal.Resolve();row.CaseMarkerResolved=true;',
                     'row.ScopedLifecycleCleanupConfirmed=row.CleanupPreconditionsConfirmed && row.CaseMarkerResolved;',
                     'case_receipt_persistence_failed', 'runJournal.Failed=true;',
                     'if(!PilotMayAdvance(row)) {blocked=true;journal.Failed=true;}',
                     'markerGuard==null', 'markerGuard(new string[0])',
                     'new string[]{"ordinary","reference","node","cmd","powershell","pwsh"}',
                     'ownership-root.json', 'ownership-profile.json', 'ownership-process.json',
                     'PilotIdentity(r,"fixture_source_sha256",fixtureHash)', 'r.ExecutableSha256!=fixtureHash'):
        assert required in runner, required
    assert runner.index('if(!row.PreResumeReady) throw') < runner.index('AssignProcessToJobObject(') < runner.index('ResumeThread(')
    assert runner.index('StopQualificationSubject(s)') < runner.index('s.ProcessStopped && s.JobDrained') < runner.index('bool captured=true')
    assert 'markerGuard(new string[]{runJournal.Path,journal.Path});\n                bool captured=true;' in runner
    assert 'journal.VerifyPending();markerGuard(new string[]{journal.Path});\n            result.RunRootRemoved=' in runner
    assert 'journal.BindPreconditions(serializeRun(result));\n            journal.VerifyPending();markerGuard(new string[]{journal.Path});\n            journal.Resolve();' in runner
    assert runner.index('result.Cases.Add(row);') < runner.index('"matrix-"') < runner.index('if(!PilotMayAdvance(row))')
    assert 'row.Fatal=true;row.PositivePassed=false;row.OfflineReferenceRouteValid=false;' in runner
    for required in ('PreconditionsPath=', 'planned_root=', 'planned_profile=', 'preconditions_record=',
                     'PreconditionsIdentity=Receipt.Identities[', 'PreconditionsBody=body;PreconditionsBound=true;',
                     'VerifyPilotStoredFile(PreconditionsPath,PreconditionsIdentity,PreconditionsBody',
                     'File.Move(Path,CompletedPath)', 'stream.Flush(true)', 'observed!=identity',
                     'info.sizeLow!=expected.Length', 'stream.ReadByte()!=expected[i]',
                     'if(Resolved || Failed)', 'PilotCommitBoundary(Resolved,Failed,PreconditionsBound,',
                     'if(!closed) throw', '1,false,"evidence_'):
        assert required in journal, required
    assert 'File.Delete(' not in journal and journal.count('File.Move(') == 1
    for required in ('ordinaryWitness && ownershipCertain && profileOwned && !row.Fatal',
                     'VerifyPilotSignature(row.Launcher,false)', 'row.Case!="ordinary"',
                     'row.IndividualResourceCleanupConfirmed && row.CaptureIntegrityConfirmed',
                     'row.ProfileDeleteApiConfirmed && row.OwnedRootRemoved',
                     'row.CaseMarkerResolved && row.ScopedLifecycleCleanupConfirmed',
                     'if(resolved || failed || !bound', 'verifyPending();verifyBinding();rename();'):
        assert required in gates, required
    for required in ('OutsideReadObserved', 'OutsideWriteObserved', 'write=unexpected_success', 'write_type=success',
                     '!row.OutsideWriteObserved', 'row.PositivePassed=false', 'row.Fatal=true',
                     'winsock_initialization_failed_10107', 'NetworkDenialProven=false'):
        assert required in facts, required
    for required in ('-Force -ErrorAction Stop', "$item.Name -ieq 'cleanup-uncertain.txt'", '$item.PSIsContainer -or -not $allow.Contains',
                     '[IO.FileAttributes]::ReparsePoint', "$Allowed.Count -gt 2", '$entries -gt 100000', '$next.depth -gt 32',
                     '$markerGuard=[Action[string[]]]', 'Assert-PilotRecoveryScope -Allowed $allowed',
                     '[string[]]$ready,$markerGuard,$serializeCase,$serializeRun', 'same-run native binary manifest mismatch'):
        assert required in wrapper, required
    scanner = wrapper[wrapper.index('function Assert-PilotRecoveryScope'):wrapper.index('Assert-PilotRecoveryScope -Allowed @()')]
    scan_calls = re.findall(r'\bGet-(?:Child)?Item\s+-LiteralPath\s+([^|\n]+)', scanner)
    assert len(scan_calls) == 4, 'unexpected recovery scanner API surface'
    for call in scan_calls:
        assert re.search(r'(?:^|\s)-Force(?:\s|$)', call), 'hidden entries must be scanned at every site'
        assert re.search(r'-ErrorAction\s+Stop\b', call), 'every scan error must stop'
    assert '-Filter cleanup-uncertain.txt' not in wrapper and 'Remove-Item' not in wrapper
    assert wrapper.index('try {\n    $listener.Start()') < wrapper.index('::RunPilot(') < wrapper.index('$listener.Stop()')
    for name in ('PilotPolicyTests.cs', 'PilotGateTests.cs', 'PilotClassificationTests.cs'):
        plain=uncomment(files[name])
        assert 'DllImport' not in plain
        for forbidden in ('CreateProcess(', 'OpenProcessToken(', 'File.', 'Directory.', 'AccessCheck(', 'ResumeThread('):
            assert forbidden not in plain, (name, forbidden)


class PilotAudit(unittest.TestCase):
    def setUp(self):
        fixture_coverage({p.name for p in HERE.iterdir() if p.suffix.lower() in ('.cs', '.ps1')})
        self.files = {name: (HERE / name).read_text() for name in PILOT_NAMES}
        self.legacy = {name: (HERE / name).read_text() for name in LEGACY_PINS}

    def test_frozen_exact_source_and_contract(self):
        inspect(self.files, self.legacy)

    def test_contract_independent_of_hash_pins(self):
        inspect(self.files, self.legacy, check_pins=False)

    def mutate(self, file, before, after):
        self.assertIn(before, self.files[file])
        self.files[file] = self.files[file].replace(before, after, 1)
        with self.assertRaises(AssertionError):
            inspect(self.files, self.legacy, check_pins=False)

    def test_unknown_or_missing_fixture(self):
        names=set(LEGACY_PINS) | set(PILOT_NAMES)
        for changed in (names | {'hidden-helper.cs'}, names | {'Hidden.ps1'}, names - {'DirectLauncher.cs'}):
            with self.assertRaises(AssertionError): fixture_coverage(changed)

    def test_partial_type_initializer_rejected(self):
        self.files['PilotGates.cs'] += '\npublic static partial class BrokerDirectLauncher {static BrokerDirectLauncher(){}}'
        with self.assertRaises(AssertionError): inspect(self.files,self.legacy,False)

    def test_nested_type_initializer_rejected(self):
        self.files['PilotJournal.cs'] += '\nstatic PilotJournal() {}'
        with self.assertRaises(AssertionError): inspect(self.files,self.legacy,False)

    def test_nested_framework_type_shadow_rejected(self):
        self.files['PilotGates.cs'] += '\nclass File {}'
        with self.assertRaises(AssertionError): inspect(self.files,self.legacy,False)

    def test_partial_static_field_rejected(self):
        self.files['PilotGates.cs'] += '\nstatic readonly object surprise = new object();'
        with self.assertRaises(AssertionError): inspect(self.files,self.legacy,False)

    def test_old_member_overload_rejected(self):
        self.files['PilotGates.cs'] += '\nstatic void OwnedAcl(string newOverload) {}'
        with self.assertRaises(AssertionError): inspect(self.files,self.legacy,False)

    def test_workflow_and_old_controls(self):
        workflow=(ROOT/'.github/workflows/windows-lpac-runtime-diagnostic.yml').read_text()
        for fragment in ('baseline/run.ps1','run-runtime.ps1','run-pilot.ps1','qualification-audit.py','pilot-audit.py',
                         'RunPilotPolicyContractTests()', 'RunPilotGateContractTests()', 'RunPilotClassificationContractTests()', 'timeout-minutes: 30'):
            self.assertIn(fragment,workflow)
        self.assertNotIn('continue-on-error',workflow)
        self.assertNotIn('& tests/windows-broker-direct/run-qualification.ps1',workflow)


MUTATIONS = [
 ('acl_complete_pass','PilotOwnedFiles.cs','RecordPilotParentAcl(descriptor,user,label,r);',''),
 ('acl_completion_starts_false','PilotOwnedFiles.cs','_acl_observation_completed"]=0;','_acl_observation_completed"]=1;'),
 ('acl_complete_count','PilotOwnedFiles.cs','_acl_observed_ace_count"]=observed;','_acl_observed_ace_count"]=0;'),
 ('acl_completion_marker','PilotOwnedFiles.cs','_acl_observation_completed"]=1;',''),
 ('acl_no_early_break','PilotOwnedFiles.cs','observed++;','observed++;break;'),
 ('acl_first_reject_index','PilotOwnedFiles.cs','_first_rejected_ace_index"]=currentIndex;','_first_rejected_ace_index"]=0;'),
 ('acl_first_reject_reason','PilotOwnedFiles.cs','_first_rejected_reason"]="untrusted_write_grant";','_first_rejected_reason"]="none";'),
 ('acl_inherit_only_not_waived','PilotOwnedFiles.cs','int currentIndex=aceIndex++;','int currentIndex=aceIndex++;if((raw.AceFlags&AceFlags.InheritOnly)!=0) continue;'),
 ('acl_creator_owner_not_trusted','PilotOwnedFiles.cs','sid!="S-1-5-32-544") {','sid!="S-1-5-32-544" && sid!="S-1-3-0") {'),
 ('acl_original_write_mask','PilotOwnedFiles.cs','const uint writeMask=0x500D0156;','const uint writeMask=0x000D0156;'),
 ('capability_count','PilotSubjects.cs','capabilities.Sid=s.Sid;','capabilities.Sid=s.Sid;capabilities.Count=1;'),
 ('job_breakaway','PilotSubjects.cs','limits.Basic.flags=KILL_ON_JOB_CLOSE;','limits.Basic.flags=KILL_ON_JOB_CLOSE|0x800;'),
 ('stdin_write','PilotSubjects.cs','inputPath,0x80000000,3,true','inputPath,0xC0000000,3,true'),
 ('stdout_read','PilotSubjects.cs','"stdout.txt"),0x40000000,1,true','"stdout.txt"),0xC0000000,1,true'),
 ('profile_checkpoint','PilotSubjects.cs','profileCheckpoint();',''),
 ('writer_retry','PilotSubjects.cs','PilotCloseHandle(ref writer,"stdin_writer",r)','CloseOwned(ref writer,"stdin_writer",r)'),
 ('broker_rights','PilotOwnedFiles.cs','PilotGetCurrentProcess(),0x8,out returnedToken','PilotGetCurrentProcess(),0x02000000,out returnedToken'),
 ('broker_query_class','PilotOwnedFiles.cs','GetTokenInformation(token,1,IntPtr.Zero','GetTokenInformation(token,2,IntPtr.Zero'),
 ('broker_failed_output','PilotOwnedFiles.cs','if(opened && validOutput) token=returnedToken;','token=returnedToken;'),
 ('broker_inheritance','PilotOwnedFiles.cs','if(!inspected || (flags&1)!=0)','if(!inspected)'),
 ('broker_pointer_span','PilotOwnedFiles.cs','returned-(pointer-start)<8','false'),
 ('broker_sid_span','PilotOwnedFiles.cs','sidBytes>returned-(pointer-start)','false'),
 ('broker_close','PilotOwnedFiles.cs','finally {closed=PilotCloseHandle(ref token,','finally {closed=true; /*'),
 ('owned_no_reparse','PilotOwnedFiles.cs','(info.attributes&0x440)!=0','false'),
 ('owned_duplicate_name','PilotOwnedFiles.cs','if(names.ContainsKey(name))','if(false)'),
 ('owned_absence_error','PilotOwnedFiles.cs','if(error!=18)','if(false)'),
 ('owned_final_close','PilotOwnedFiles.cs','scope.RemovalConfirmed=valid && closed','scope.RemovalConfirmed=valid'),
 ('owned_readonly_repair','PilotOwnedFiles.cs','if((info.attributes&1)!=0)','if(false)'),
 ('same_run_witness','PilotGates.cs','ordinaryWitness && ownershipCertain','ownershipCertain'),
 ('never_resume_ordinary','PilotGates.cs','row.Case!="ordinary"','true'),
 ('authority_predicate','PilotGates.cs','VerifyPilotSignature(row.Launcher,false)','true'),
 ('profile_cleanup','PilotGates.cs','row.ProfileDeleteApiConfirmed && row.OwnedRootRemoved','row.OwnedRootRemoved'),
 ('root_cleanup','PilotGates.cs','row.ProfileDeleteApiConfirmed && row.OwnedRootRemoved','row.ProfileDeleteApiConfirmed'),
 ('marker_resolution','PilotGates.cs','row.CaseMarkerResolved && row.ScopedLifecycleCleanupConfirmed','row.ScopedLifecycleCleanupConfirmed'),
 ('failed_journal','PilotGates.cs','if(resolved || failed || !bound','if(resolved || !bound'),
 ('binding_before_rename','PilotGates.cs','verifyPending();verifyBinding();rename();','verifyPending();rename();'),
 ('journal_identity','PilotJournal.cs','observed!=identity','false'),
 ('journal_content','PilotJournal.cs','stream.ReadByte()!=expected[i]','false'),
 ('journal_durable_flush','PilotJournal.cs','stream.Flush(true)','stream.Flush()'),
 ('journal_binding','PilotJournal.cs','PreconditionsBody=body;PreconditionsBound=true;','PreconditionsBound=true;'),
 ('guard_required','PilotRunner.cs','markerGuard==null || ','') ,
 ('guard_after_stop','PilotRunner.cs','markerGuard(new string[]{runJournal.Path,journal.Path});\n                bool captured=true;','bool captured=true;'),
 ('profile_delete_check','PilotRunner.cs','row.ProfileDeleteApiConfirmed=hr==0','row.ProfileDeleteApiConfirmed=true'),
 ('advance_after_write','PilotRunner.cs','if(!PilotMayAdvance(row)) {blocked=true;journal.Failed=true;}',''),
 ('case_write_failure','PilotRunner.cs','row.Fatal=true;row.PositivePassed=false;row.OfflineReferenceRouteValid=false;','row.Fatal=false;'),
 ('hidden_marker','run-pilot.ps1','-Force -ErrorAction Stop','-ErrorAction Stop'),
 ('wrong_type_marker','run-pilot.ps1','$item.PSIsContainer -or -not $allow.Contains','-not $allow.Contains'),
 ('scan_error','run-pilot.ps1','-Force -ErrorAction Stop','-Force -ErrorAction SilentlyContinue'),
]
for label, file, before, after in MUTATIONS:
    def case(self, file=file, before=before, after=after): self.mutate(file,before,after)
    setattr(PilotAudit,'test_mutation_'+label,case)

if __name__ == '__main__': unittest.main(verbosity=2)
