#!/usr/bin/env python3
"""Exact additive cmd scope and effective source mutations; no Windows execution."""
import hashlib
import pathlib
import re
import runpy
import unittest

HERE = pathlib.Path(__file__).parent
ROOT = HERE.parents[1]
SELECTED = runpy.run_path(str(HERE / 'selected-parent-audit.py'))
OLD_NAMES = SELECTED['OLD_NAMES'] | set(SELECTED['NAMES'])
NAMES = ('PilotCmdSentinel.cs', 'PilotCmdSentinelTests.cs')
PINS = {'PilotCmdSentinel.cs': '36a2edb4ae0d5cb5866bf1a464f953d1e790938d6d53f4617e29eb0196388fd4', 'PilotCmdSentinelTests.cs': 'ae3ff1b4018337b46276b5bceb069fdd9161e405b8728cb3ac62066a2539f945'}


def coverage(names):
    assert len(OLD_NAMES) == 26
    assert names == OLD_NAMES | set(NAMES), 'unknown/missing executable fixture'
    assert len(names) == len({name.casefold() for name in names})


def inspect(files, old, workflow, pins=True):
    assert set(files) == set(NAMES) and set(old) == OLD_NAMES
    if pins:
        assert set(PINS) == set(NAMES)
        for name in NAMES:
            assert hashlib.sha256(files[name].encode()).hexdigest() == PINS[name]
    pilot = SELECTED['PARENT']['PILOT']
    methods, uncomment = pilot['declared_methods'], pilot['uncomment']
    previous = set().union(*(methods(s) for n, s in old.items() if n.endswith('.cs')))
    additions = set()
    for name, source in files.items():
        plain = uncomment(source)
        members = methods(plain)
        assert not members & previous and not members & additions, 'partial method collision'
        additions |= members
        types = set(re.findall(r'\bclass\s+(\w+)', plain))
        expected = {'BrokerDirectLauncher'} | ({'PilotCmdCaptureOperations'} if name == NAMES[0] else {'PilotCmdTestStream', 'PilotCmdTestCapture'})
        assert types == expected, 'unreviewed or shadowed type rejected'
        assert not re.search(r'using\s+\w+\s*=', plain), 'using alias rejected'
        for type_name in types:
            assert not re.search(r'\bstatic\s+' + type_name + r'\s*\(', plain), 'type initializer rejected'
        for forbidden in ('DllImport', 'ModuleInitializer', 'static readonly', 'CreateProcess(', 'ResumeThread(',
                          'AssignProcessToJobObject(', 'OpenProcessToken(', 'DuplicateToken', 'AccessCheck(',
                          'SetThreadToken(', 'Impersonate', 'AdjustToken', 'SetTokenInformation(', 'OwnedAcl(',
                          'SetAccessControl(', 'Registry.', 'RegOpen', 'EventRegister', 'WSAStartup', 'WindowsIdentity',
                          'File.', 'Directory.', 'System.Linq', 'HashSet<', '.TryAdd('):
            assert forbidden not in plain, (name, forbidden)
        for line in plain.splitlines():
            if re.search(r'^\s*(?:(?:public|private|protected|internal)\s+)?static\s+', line) and ' class ' not in line:
                assert '(' in line and '=' not in line.split('(')[0], 'static initializer rejected'
    helper, tests = files[NAMES[0]], files[NAMES[1]]
    for forbidden in ('PilotCmdNativeCaptureOperations(', 'CapturePilotOriginalCmdBatch(', 'PilotOpenHandle(', 'OpenPrivate('):
        assert forbidden not in tests
    for exact in (
        'return Quote(privateCmdExe)+" /d /q /c exit 23";',
        'Path.GetFileName(privateCmdExe)!="cmd.exe"',
        'const int PilotCmdBatchLimit=1024*1024;',
        'PilotOpenHandle(ref h,path,0x80000000,false,label,r)',
        'OpenPrivate(ref h,path,0x40000000,1,false,label,r)',
        'return PilotValidateObject(h,path,false,identity,null);',
        'ops.Write=WritePilotBytes;ops.Close=PilotCloseHandle;',
        'new SafeFileHandle(h,false)',
        'stream.Length!=advertised', 'stream.Position!=0',
        'if(stream.ReadByte()!=-1 || stream.Position!=advertised || stream.Length!=advertised)',
        'read<=0 || read>bytes.Length-total',
        '(info.attributes&0x450)!=0 || info.links!=1',
        'info.sizeHigh!=0 || info.sizeLow>PilotCmdBatchLimit',
        'IntPtr owned=handle;handle=IntPtr.Zero;',
        'closed=ops.Close(ref owned,label,s.Receipt) && owned==IntPtr.Zero;',
        'if(!closed) s.OwnershipCertain=false;',
        'if(!PilotCmdStableMetadata(before,after)) throw',
        'if(bytes==null || bytes.Length!=size || bytes.Length>PilotCmdBatchLimit)',
        'finally {closed=ClosePilotCmdCaptureHandle(ref handle,label,s,ops);}',
        'finally {closed=ClosePilotCmdCaptureHandle(ref writer,"pilot_cmd_batch_destination",s,ops);}',
        'if(!closed) throw new InvalidOperationException("cmd batch read close uncertain");',
        'if(!closed) throw new InvalidOperationException("cmd batch destination close uncertain");',
        's.Receipt.Kind!="cmd" || !PilotIdentity(s.Receipt,"pilot_case_id","cmd")',
        's.ProfileCreated || s.Sid!=IntPtr.Zero',
        's.Receipt.CreateAttempted || s.Receipt.Created || s.Receipt.Assigned || s.Receipt.Resumed',
        'Path.Combine(s.Workspace,"direct.cmd")',
        'Path.Combine(evidence,"generated-direct.cmd.bin")',
        'ReadPilotCmdCapture(s,source,null,"pilot_cmd_batch_source",ops)',
        'ops.Write(writer,bytes);',
        'ReadPilotCmdCapture(s,destination,destinationIdentity,"pilot_cmd_batch_readback",ops)',
        'if(!PilotCmdRawEqual(bytes,readback)',
        'pilot_cmd_batch_capture_confirmed"]=0;',
        'pilot_cmd_batch_capture_confirmed"]=1;',
        'row.CmdExit23Observed=false;row.PositivePassed=false;',
        'row.Case=="cmd-exit23" && r.Kind=="cmd" && PilotIdentity(r,"pilot_case_id","cmd-exit23")',
        'PilotNumber(r,"pilot_cmd_same_binary_verified",1)',
        'PilotIdentity(r,"pilot_original_cmd_sha256",r.ExecutableSha256)',
        'PilotNumber(r,"pilot_exit_query_success",1)',
        'r.Assigned && r.Resumed && r.Wait==WAIT_OBJECT_0 && r.Exit==23',
        'sentinel_did_not_attempt_runtime_canary',
        'RunPilotCmdSentinelContractTests()'):
        assert exact in helper + tests, exact
    assert 's.OwnershipCertain=true' not in helper
    assert 'PositivePassed=true' not in helper and 'NetworkDenialProven=true' not in helper
    aggregate = helper[helper.index('    static bool PilotOriginalSixPassed('):]
    assert 'if(rows==null || rows.Count<6) return false;' in aggregate
    assert 'new string[]{"ordinary","reference","node","cmd","powershell","pwsh"}' in aggregate
    assert 'for(int i=0;i<kinds.Length;i++)' in aggregate
    assert 'row.Case!=kinds[i]' in aggregate and 'row.Launcher.Kind!=kinds[i]' in aggregate
    assert '!PilotMayAdvance(row) || !row.ScopedLifecycleCleanupConfirmed' in aggregate
    assert 'if(i>=2 && !row.PositivePassed) return false;' in aggregate
    assert 'return true;' in aggregate and 'rows[6]' not in aggregate
    assert aggregate.count('rows.Count') == 1 and 'cmd-exit23' not in aggregate
    subjects, runner, facts = old['PilotSubjects.cs'], old['PilotRunner.cs'], old['PilotClassification.cs']
    assert 'kind!="pwsh" && kind!="cmd-exit23"' in subjects
    assert 'r.Kind=kind=="cmd-exit23"?"cmd":kind;' in subjects
    assert 'if(kind=="cmd" || kind=="cmd-exit23") CopyPilotFile(Path.Combine(payload,"cmd.exe")' in subjects
    assert 'if(kind=="cmd") CapturePilotOriginalCmdBatch(s,evidence);' in subjects
    assert subjects.count('CapturePilotOriginalCmdBatch(') == 1
    assert subjects.index('r.CommandLine=FixedCommand(') < subjects.index('CapturePilotOriginalCmdBatch(') < subjects.index('CreateAppContainerProfile(') < subjects.index('CreateProcess(')
    assert 'exe=Path.Combine(s.Code,"cmd.exe");r.CommandLine=FixedPilotCmdSentinelCommand(exe);' in subjects
    assert 'row.Launcher.Kind=kind=="cmd-exit23"?"cmd":kind;' in runner
    assert 'r.Identities["pilot_case_id"]=kind;' in runner
    assert 'if(!PilotCmdSha256(originalCmdHash) || originalCmdHash!=r.ExecutableSha256)' in runner
    assert 'r.Identities["pilot_original_cmd_sha256"]=originalCmdHash;' in runner
    assert runner.index('originalCmdHash!=r.ExecutableSha256') < runner.index('ObserveQualificationSource(s)') < runner.index('AssignProcessToJobObject(')
    assert 'Check(GetExitCodeProcess(s.Process.process,out exit),"pilot exit code");r.Exit=exit;r.Numbers["pilot_exit_query_success"]=1;' in runner
    sequence = 'new string[]{"ordinary","reference","node","cmd","powershell","pwsh","cmd-exit23"}'
    assert runner.count(sequence) == 2
    assert 'RequiredCaseCount=7,OriginalPilotRequiredCaseCount=6,AdditiveSentinelRequiredCaseCount=1,OriginalNestedRequiredRows=20;' in runner
    assert 'string runtime=kind=="cmd-exit23"?"cmd":kind;' in runner and '!available.ContainsKey(runtime)' in runner
    assert 'blocked_original_cmd_provenance";row.Fatal=true;row.NoCaseResourcesAllocated=true;' in runner
    assert 'else if(kind=="cmd-exit23" && !PilotCmdSha256(originalCmdHash))' in runner
    assert 'if(kind=="cmd" && PilotNumber(row.Launcher,"pilot_copied_bytes_verified",1)) originalCmdHash=row.Launcher.ExecutableSha256;' in runner
    assignments = re.findall(r'result\.AllFourOfflineCasesPassed\s*=[^;]+;', runner)
    assert assignments == ['result.AllFourOfflineCasesPassed=PilotOriginalSixPassed(result.Cases);'] * 2
    assert runner.index('result.AllFourOfflineCasesPassed=PilotOriginalSixPassed(result.Cases);') < runner.index('"matrix-"')
    assert runner.index('if(kind=="cmd-exit23") result.CmdSentinelObservationPassed=') < runner.index('"matrix-"')
    assert 'row.CmdExit23Observed && row.ScopedLifecycleCleanupConfirmed && !row.Fatal;' in runner
    assert 'result.AllCaseCleanupConfirmed=allCleanup && result.Cases.Count==7;' in runner
    assert runner.count('new PilotJournal(') == 2 and runner.count('RunPilotCase(fixture,') == 1
    assert 'journal=new PilotJournal(evidence,kind,s.Root,s.Profile,r);' in runner
    assert 'if(!PilotMayAdvance(row)) {blocked=true;journal.Failed=true;}' in runner
    assert 'if(!result.AllCaseCleanupConfirmed || journal.Failed) throw' in runner
    assert 'row.NetworkDenialProven=false;row.CmdExit23Observed=false;' in facts
    assert facts.index('row.CmdExit23Observed=false;') < facts.index('if(row.Fatal) return;')
    assert facts.index('if(!row.OutsideUnchanged || !row.OutsideWriteAbsent)') < facts.index('if(row.Case=="cmd-exit23") {ClassifyPilotCmdSentinel(row);return;}')
    wrapper = old['run-pilot.ps1']
    assert 'if(-not $result.AllFourOfflineCasesPassed) {throw' in wrapper
    assert 'if(-not $result.CmdSentinelObservationPassed) {throw' in wrapper
    assert workflow.count('& tests/windows-broker-direct/run-pilot.ps1') == 1
    for exact in ('cmd-sentinel-audit.py', 'RunPilotCmdSentinelContractTests()', 'RunSelectedParentContractTests()',
                  'RunPilotPolicyContractTests()', 'RunPilotGateContractTests()', 'RunPilotClassificationContractTests()',
                  'RunParentCandidateContractTests()', 'timeout-minutes: 30', 'baseline/run.ps1', 'run-runtime.ps1'):
        assert exact in workflow
    assert 'continue-on-error' not in workflow


class CmdSentinelAudit(unittest.TestCase):
    def setUp(self):
        coverage({p.name for p in HERE.iterdir() if p.suffix.lower() in ('.cs', '.ps1')})
        self.files = {n: (HERE/n).read_text() for n in NAMES}
        self.old = {n: (HERE/n).read_text() for n in OLD_NAMES}
        self.workflow = (ROOT/'.github/workflows/windows-lpac-runtime-diagnostic.yml').read_text()

    def test_exact_source_and_contract(self):
        inspect(self.files, self.old, self.workflow)

    def test_hash_independent_contract(self):
        inspect(self.files, self.old, self.workflow, False)

    def test_union_rejects_unknown_missing_collision(self):
        baseline = OLD_NAMES | set(NAMES)
        coverage(baseline)
        for names in (baseline|{'unreviewed.cs'}, baseline|{'hidden.ps1'}, baseline-{'PilotCmdSentinel.cs'}, baseline|{'pilotcmdsentinel.cs'}):
            with self.assertRaises(AssertionError): coverage(names)

    def test_static_constructor_rejected(self):
        self.files[NAMES[0]] += '\nstatic BrokerDirectLauncher() {}'
        with self.assertRaises(AssertionError): inspect(self.files,self.old,self.workflow,False)

    def test_partial_collision_rejected(self):
        self.files[NAMES[0]] += '\nstatic void OwnedAcl(string overload) {}'
        with self.assertRaises(AssertionError): inspect(self.files,self.old,self.workflow,False)


MUTATIONS = [
    ('unreviewed_type','PilotCmdSentinel.cs','const int PilotCmdBatchLimit','class PilotCmdUnreviewed {}\n    const int PilotCmdBatchLimit'),
    ('alias_injection','PilotCmdSentinel.cs','using System;','using System;\nusing Shadow = System.IO.File;'),
    ('new_command','PilotCmdSentinel.cs',' /d /q /c exit 23',' /d /q /c exit 0'),
    ('source_write_access','PilotCmdSentinel.cs','ref h,path,0x80000000,false','ref h,path,0xC0000000,false'),
    ('output_inherit','PilotCmdSentinel.cs','0x40000000,1,false,label','0x40000000,1,true,label'),
    ('overwrite_capture','PilotCmdSentinel.cs','0x40000000,1,false,label','0x40000000,2,false,label'),
    ('readback_identity','PilotCmdSentinel.cs','destination,destinationIdentity,"pilot_cmd_batch_readback"','destination,null,"pilot_cmd_batch_readback"'),
    ('batch_equality','PilotCmdSentinel.cs','if(!PilotCmdRawEqual(bytes,readback)','if(false'),
    ('close_retry','PilotCmdSentinel.cs','IntPtr owned=handle;handle=IntPtr.Zero;','IntPtr owned=handle;'),
    ('uncertain_close','PilotCmdSentinel.cs','if(!closed) s.OwnershipCertain=false;',''),
    ('false_success_close','PilotCmdSentinel.cs',' && owned==IntPtr.Zero',''),
    ('read_close_gate','PilotCmdSentinel.cs','if(!closed) throw new InvalidOperationException("cmd batch read close uncertain");',''),
    ('destination_close_gate','PilotCmdSentinel.cs','if(!closed) throw new InvalidOperationException("cmd batch destination close uncertain");',''),
    ('source_bound','PilotCmdSentinel.cs','info.sizeLow>PilotCmdBatchLimit','info.sizeLow>Int32.MaxValue'),
    ('actual_bound','PilotCmdSentinel.cs','bytes.Length>PilotCmdBatchLimit','false'),
    ('trailing_bytes','PilotCmdSentinel.cs','stream.ReadByte()!=-1 || ',''),
    ('raw_length','PilotCmdSentinel.cs','bytes.Length!=size || ',''),
    ('metadata_change','PilotCmdSentinel.cs','if(!PilotCmdStableMetadata(before,after)) throw','if(false) throw'),
    ('single_link','PilotCmdSentinel.cs','info.links!=1','info.links<1'),
    ('capture_wrong_case','PilotCmdSentinel.cs','"pilot_case_id","cmd")','"pilot_case_id","cmd-exit23")'),
    ('capture_after_creation','PilotCmdSentinel.cs','s.Receipt.CreateAttempted || s.Receipt.Created || ',''),
    ('sentinel_query_missing','PilotCmdSentinel.cs','PilotNumber(r,"pilot_exit_query_success",1)','true'),
    ('sentinel_timeout','PilotCmdSentinel.cs','r.Wait==WAIT_OBJECT_0 && r.Exit==23','r.Wait==WAIT_TIMEOUT && r.Exit==23'),
    ('sentinel_identity','PilotCmdSentinel.cs','PilotIdentity(r,"pilot_case_id","cmd-exit23")','true'),
    ('sentinel_same_bytes','PilotCmdSentinel.cs','PilotNumber(r,"pilot_cmd_same_binary_verified",1)','true'),
    ('sentinel_original_digest','PilotCmdSentinel.cs','PilotIdentity(r,"pilot_original_cmd_sha256",r.ExecutableSha256)','true'),
    ('original_six_isolation','PilotCmdSentinel.cs','if(rows==null || rows.Count<6)','if(rows==null || rows.Count!=7)'),
    ('original_positive_required','PilotCmdSentinel.cs','if(i>=2 && !row.PositivePassed) return false;',''),
    ('sentinel_positive','PilotCmdSentinel.cs','row.PositivePassed=false;','row.PositivePassed=true;'),
    ('wrong_batch_case','PilotSubjects.cs','if(kind=="cmd") CapturePilotOriginalCmdBatch','if(kind=="cmd-exit23") CapturePilotOriginalCmdBatch'),
    ('wrong_family','PilotSubjects.cs','r.Kind=kind=="cmd-exit23"?"cmd":kind;','r.Kind=kind;'),
    ('binary_comparison','PilotRunner.cs','originalCmdHash!=r.ExecutableSha256','false'),
    ('rewrite_original','PilotRunner.cs','result.AllFourOfflineCasesPassed=PilotOriginalSixPassed(result.Cases);','result.AllFourOfflineCasesPassed=true;'),
    ('omit_seventh','PilotRunner.cs','"pwsh","cmd-exit23"}','"pwsh"}'),
    ('hide_provenance','PilotRunner.cs','blocked_original_cmd_provenance";row.Fatal=true;','blocked_original_cmd_provenance";row.Fatal=false;'),
    ('seventh_cleanup','PilotRunner.cs','result.Cases.Count==7','result.Cases.Count==6'),
    ('reset_stale','PilotClassification.cs','row.CmdExit23Observed=false;',''),
    ('drop_wrapper_gate','run-pilot.ps1','if(-not $result.CmdSentinelObservationPassed) {throw','if($false) {throw'),
]
for label, file, before, after in MUTATIONS:
    def test(self, file=file, before=before, after=after):
        values = self.files if file in self.files else self.old
        self.assertIn(before, values[file])
        values[file] = values[file].replace(before, after, 1)
        with self.assertRaises(AssertionError): inspect(self.files,self.old,self.workflow,False)
    setattr(CmdSentinelAudit, 'test_mutation_'+label, test)

if __name__ == '__main__':
    unittest.main()
