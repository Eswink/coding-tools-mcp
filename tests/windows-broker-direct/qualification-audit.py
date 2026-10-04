#!/usr/bin/env python3
"""Portable source/mutation contracts for an unadopted, never-resumed observer."""
import ast
import hashlib
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).parent
NAMES = ('AccessCheckObservations.cs', 'QualificationSubjects.cs', 'QualificationCleanup.cs', 'run-qualification.ps1')
# Filled with reviewed source bytes; intentional edits require explicit pin updates.
PINS = {'AccessCheckObservations.cs': '4731a82554776644026e5006e0ca56644737bed9144a6ef4bae6dcc2b5eeb4a9', 'QualificationSubjects.cs': '833f1deaadaa0ef1eb80f1bad0e8c09c87c076948a07666daad3cae7ae660196', 'QualificationCleanup.cs': '08f0cec58e8079317681a77412c4e480991a5941b4ef68c75b955c639e193b96', 'run-qualification.ps1': '74ba3042c51f232fc5c2b414b7989bb36098f774f4abb7c4f5ab5804817390a3'}


LEGACY_NAMES = {'DirectNative.cs', 'DirectHandles.cs', 'DirectCases.cs', 'DirectLauncher.cs', 'DirectCapture.cs', 'run-direct.ps1'}


def legacy_names():
    tree = ast.parse((HERE / 'audit.py').read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'APPROVED_BOUNDARY' for t in node.targets):
            return set(ast.literal_eval(node.value))
    raise AssertionError('legacy source pins missing')


def fixture_coverage(discovered, legacy):
    assert legacy == LEGACY_NAMES
    assert set(PINS) == set(NAMES)
    assert not (legacy & set(NAMES))
    assert discovered == legacy | set(NAMES), 'unreviewed or missing executable fixture file'
    assert len(discovered) == len({name.casefold() for name in discovered})


def inspect(files):
    assert set(files) == set(NAMES)
    for name, digest in PINS.items():
        assert hashlib.sha256(files[name].encode()).hexdigest() == digest, name
    observer, subjects, cleanup, runner = (files[name] for name in NAMES)
    for source in (observer, subjects, cleanup):
        for forbidden in ('ResumeThread(', 'AssignProcessToJobObject(', 'CreateProcessAsUser', 'SetThreadToken',
                          'Impersonate', 'OpenThreadToken', 'AdjustToken', 'SetTokenInformation', 'DeleteAppContainerProfile'):
            assert forbidden not in source, forbidden
    for forbidden in ('File.', 'Directory.', 'CreateFile(', 'SetFileSecurity(', 'OwnedAcl(', 'Socket', 'CreateProcess('):
        assert forbidden not in observer, forbidden
    assert 'OpenProcessToken(s.Process.process,0x000A,out candidateToken)' in subjects
    assert 'source_token_unconfirmed_output' in subjects and 'candidateToken=IntPtr.Zero;' in subjects
    assert subjects.index('if(!opened) {') < subjects.index('s.SourceToken=candidateToken;')
    assert 'profile_unconfirmed_output' in subjects and 'create_unconfirmed_outputs' in subjects
    assert 'out candidateSid)' in subjects and 'out candidateProcess)' in subjects
    assert 'candidateProcess=new PROCESS_INFORMATION();' in subjects
    assert 'if(Directory.Exists(s.Parent) || File.Exists(s.Parent)) throw' in subjects
    assert 'IntPtr.Zero,0,out candidateSid)' in subjects
    assert re.findall(r'capabilities\.\w+\s*=[^;]*;', subjects) == ['capabilities.Sid=s.Sid;']
    assert re.findall(r'limits\.Basic\.flags\s*=[^;]*;', subjects) == ['limits.Basic.flags=KILL_ON_JOB_CLOSE;']
    assert 'if(lpac) {' in subjects and 'new IntPtr(0x2000f)' in subjects
    assert 'Marshal.AllocHGlobal(3*IntPtr.Size)' in subjects and 'new IntPtr(0x20002),handles,new IntPtr(3*IntPtr.Size)' in subjects
    assert 'CREATE_SUSPENDED|EXTENDED|UNICODE|0x08000000u' in subjects
    assert 's.OwnershipCertain=closed && s.OwnershipCertain' in subjects
    assert 'QualificationSetupCleanup(s,delegate {Marshal.FreeHGlobal(memory[i]);},"setup_heap_"+i)' in subjects
    assert 'QualificationSetupCleanup(s,delegate {DeleteProcThreadAttributeList(list);},"setup_attribute_cleanup")' in subjects
    assert 'source_allocation_cleanup_uncertain' in subjects
    assert 's.OwnershipCertain=false;r.Numbers["source_inspection_cleanup_uncertain"]=1;throw;' in subjects
    assert 'QualificationSourceObservation(s,delegate' in subjects
    assert 'sourceValid=restricted && type==1 && app==1 && capabilities==0 && sid==r.ProfileSid && integrity=="S-1-16-4096"' in subjects
    assert 'r.TokenVerified=sourceValid && lpacQuery && lpac==1;' in subjects
    assert 'ObserveLpacSizing(s.SourceToken,r)' in subjects and 'ObserveFixedLpacDword(s.SourceToken,r)' in subjects
    assert 'ObserveNativeDword(s.SourceToken,29,"native_appcontainer",r)' in subjects
    assert 'ObserveNativeDword(s.SourceToken,46,"native_lpac",r)' in subjects
    assert 'DuplicateTokenEx(sourceToken,0x0008,IntPtr.Zero,1,2,ref duplicate)' in observer
    assert 'duplicateOwned' in observer and 'duplicate_failed_nonzero_output' in observer
    assert 'GetHandleInformation(duplicate,out flags)' in observer and '(flags&1)!=0' in observer
    for fragment in ('duplicate_type_value"]!=2', 'duplicate_level_value"]!=1', 'duplicate_appcontainer_value"]!=1',
                     'duplicate_capabilities_value"]!=0', 'duplicate_appcontainer_sid"]!=packageSid',
                     'duplicate_integrity_sid"]!="S-1-16-4096"'):
        assert fragment in observer, fragment
    assert 'ACCESSCHECK_PRIVILEGE_BYTES=20' in observer
    assert 'int accessStatus=-1;' in observer and 'granted=ACCESSCHECK_RAW_SENTINEL' in observer
    assert '(!success || accessStatus==0)?(int?)Marshal.GetLastWin32Error():null' in observer
    assert 'privilegeBytes>=8 && privilegeBytes<=ACCESSCHECK_PRIVILEGE_BYTES' in observer
    assert '8L+12L*privilegeCount.Value' in observer and 'span<=privilegeBytes' in observer
    assert 'decisionValid=success && privilegeHeaderValid && privilegeCount.HasValue && privilegeCount.Value==0' in observer
    assert '(accessStatus!=0 || granted==0)' in observer
    assert 'descriptor.Control!=4' in observer and 'descriptor.Sacl!=IntPtr.Zero' in observer
    assert 'descriptor.Dacl==IntPtr.Zero || descriptor.Dacl!=memory[5]' in observer
    assert 'MapGenericMask(ref desired,ref mapping)' in observer and 'desired!=ACCESSCHECK_MAXIMUM_ALLOWED' in observer
    assert 'mapping.GenericRead==0 && mapping.GenericWrite==0 && mapping.GenericExecute==0 && mapping.GenericAll==0' in observer
    assert 'new string[]{"mixed","aap","arap","world"}' in observer
    for fragment in ('masks=new uint[]{3,1,2}', 'masks=new uint[]{1,1}', 'masks=new uint[]{2,2}', 'masks=new uint[]{3}'):
        assert fragment in observer, fragment
    assert 'r.Numbers[label+"_decision_valid"]=0;r.Identities[label+"_interpreted_decision"]="unknown"' in observer
    assert 'return cleanupCertain;' in observer
    assert 'ObservationOnly=true,VerifierAdopted=false' in cleanup
    assert 'CleanupConfirmed=false,RecoveryRetained=true' in cleanup
    assert 'NewQualificationSubject(parent,"ordinary"),NewQualificationSubject(parent,"lpac")' in cleanup
    assert 'PrepareQualificationSubject(subjects[0],fixture,false,port)' in cleanup
    assert 'PrepareQualificationSubject(subjects[1],fixture,true,port)' in cleanup
    assert cleanup.index('PrepareQualificationSubject(subjects[1]') < cleanup.index('ObserveQualificationSource(s)') < cleanup.index('ObserveAccessCheckToken(s.SourceToken')
    assert 'sourcesValid=ObserveQualificationSource(s) && sourcesValid' in cleanup
    assert 'if(!sourcesValid) throw' in cleanup and 'if(!observerClosed) throw' in cleanup
    assert 'try {certain=StopQualificationSubject(s) && certain;}' in cleanup
    assert 'catch(Exception failure) {certain=false;s.Receipt.Identities["cleanup_unhandled_exception"]' in cleanup
    assert 's.ProcessStopped && s.JobDrained && stoppedAndDrained' in cleanup
    assert 'if(stoppedAndDrained)' in cleanup
    assert 'exact_process_stop_confirmed' in cleanup
    assert 'r.CleanupConfirmed=false;' in cleanup
    assert 'File.Delete' not in cleanup and 'Directory.Delete' not in cleanup
    assert 'prior diagnostic recovery marker prohibits qualification' in runner
    assert '[IO.Path]::GetTempPath()' in runner and "'ctm-direct-*'" in runner
    assert '$n.ContainsKey' in runner and '_decision_valid' in runner
    assert 'qualification_matched=$allMatched;verifier_adopted=$false;runtime_attempts=0' in runner
    assert 'reference_resumes=0' in runner and '$rows.Count -eq 8' in runner
    assert "ordinary=@{mixed=@(1,3);aap=@(1,1);arap=@(1,2);world=@(0,0)}" in runner
    assert "lpac=@{mixed=@(1,2);aap=@(0,0);arap=@(1,2);world=@(0,0)}" in runner
    assert 'Remove-Item' not in runner
    assert "throw 'observation-only qualification complete; verifier remains unadopted and recovery retained'" in runner


class QualificationAudit(unittest.TestCase):
    def setUp(self):
        # The new pilot audit checks the exhaustive union; these old mutation contracts stay exact.
        fixture_coverage({p.name for p in HERE.iterdir() if p.name in LEGACY_NAMES | set(NAMES)}, legacy_names())
        self.files = {name: (HERE / name).read_text() for name in NAMES}

    def test_source_contract(self):
        inspect(self.files)

    def mutation(self, name, old, new):
        self.assertIn(old, self.files[name])
        self.files[name] = self.files[name].replace(old, new)
        with self.assertRaises(AssertionError):
            inspect(self.files)

    def test_source_rights_cannot_expand(self):
        self.mutation('QualificationSubjects.cs', '0x000A,out candidateToken', '0xF01FF,out candidateToken')

    def test_duplicate_rights_cannot_expand(self):
        self.mutation('AccessCheckObservations.cs', 'sourceToken,0x0008,IntPtr.Zero,1,2', 'sourceToken,0x02000000,IntPtr.Zero,1,2')

    def test_duplicate_identification_only(self):
        self.mutation('AccessCheckObservations.cs', 'sourceToken,0x0008,IntPtr.Zero,1,2', 'sourceToken,0x0008,IntPtr.Zero,2,2')

    def test_duplicate_not_primary(self):
        self.mutation('AccessCheckObservations.cs', 'sourceToken,0x0008,IntPtr.Zero,1,2', 'sourceToken,0x0008,IntPtr.Zero,1,1')

    def test_no_thread_binding(self):
        self.files['AccessCheckObservations.cs'] += '\nSetThreadToken();\n'
        with self.assertRaises(AssertionError):
            inspect(self.files)

    def test_no_resume(self):
        self.files['QualificationCleanup.cs'] += '\nResumeThread();\n'
        with self.assertRaises(AssertionError):
            inspect(self.files)

    def test_no_assignment(self):
        self.files['QualificationCleanup.cs'] += '\nAssignProcessToJobObject();\n'
        with self.assertRaises(AssertionError):
            inspect(self.files)

    def test_stale_api_failure_cannot_qualify(self):
        self.mutation('AccessCheckObservations.cs', 'decisionValid=success && privilegeHeaderValid', 'decisionValid=privilegeHeaderValid')

    def test_denial_cannot_carry_granted_mask(self):
        self.mutation('AccessCheckObservations.cs', '(accessStatus!=0 || granted==0)', 'true')

    def test_privilege_use_rejected(self):
        self.mutation('AccessCheckObservations.cs', 'privilegeCount.Value==0', 'privilegeCount.Value<=1')

    def test_privilege_length_bound(self):
        self.mutation('AccessCheckObservations.cs', 'privilegeBytes<=ACCESSCHECK_PRIVILEGE_BYTES', 'true')

    def test_null_dacl_rejected(self):
        self.mutation('AccessCheckObservations.cs', 'descriptor.Dacl==IntPtr.Zero || descriptor.Dacl!=memory[5]', 'false')

    def test_denied_last_error_preserved(self):
        self.mutation('AccessCheckObservations.cs', '(!success || accessStatus==0)?', '(!success)?')

    def test_source_missing_capability_not_accepted(self):
        self.mutation('QualificationSubjects.cs', 'capabilities=null', 'capabilities=0')

    def test_only_exact_source_gets_duplicate(self):
        self.mutation('QualificationCleanup.cs', 'if(!sourcesValid) throw', 'if(false) throw')

    def test_close_uncertainty_aborts_observation(self):
        self.mutation('QualificationCleanup.cs', 'if(!observerClosed) throw', 'if(false) throw')

    def test_both_subjects_cleanup_after_exception(self):
        self.mutation('QualificationCleanup.cs', 'try {certain=StopQualificationSubject(s) && certain;}', 'certain=StopQualificationSubject(s) && certain;')

    def test_exact_process_stop_required_for_capture(self):
        self.mutation('QualificationCleanup.cs', 's.ProcessStopped && s.JobDrained && stoppedAndDrained', 's.JobDrained && stoppedAndDrained')

    def test_no_full_cleanup_claim(self):
        self.mutation('QualificationCleanup.cs', 'r.CleanupConfirmed=false;', 'r.CleanupConfirmed=true;')

    def test_negative_control_mask_not_recalibrated(self):
        self.mutation('run-qualification.ps1', 'ordinary=@{mixed=@(1,3)', 'ordinary=@{mixed=@(1,2)')

    def test_no_adoption(self):
        self.mutation('run-qualification.ps1', 'verifier_adopted=$false', 'verifier_adopted=$true')

    def test_failed_source_output_not_owned(self):
        self.mutation('QualificationSubjects.cs', 'candidateToken=IntPtr.Zero;', 's.SourceToken=candidateToken;')

    def test_failed_create_output_not_owned(self):
        self.mutation('QualificationSubjects.cs', 'candidateProcess=new PROCESS_INFORMATION();', 's.Process=candidateProcess;')

    def test_prior_recovery_refusal_not_removed(self):
        self.mutation('run-qualification.ps1', 'prior diagnostic recovery marker prohibits qualification', 'ignore recovery marker')

    def test_unknown_fixture_file_is_rejected(self):
        known = LEGACY_NAMES | set(NAMES)
        for extra in ('unreviewed.cs', 'unreviewed.ps1', 'unreviewed.CS'):
            with self.assertRaises(AssertionError):
                fixture_coverage(known | {extra}, LEGACY_NAMES)

    def test_unknown_legacy_pin_is_rejected(self):
        with self.assertRaises(AssertionError):
            fixture_coverage(LEGACY_NAMES | set(NAMES) | {'unreviewed.cs'}, LEGACY_NAMES | {'unreviewed.cs'})

    def test_setup_frees_independently_wrapped(self):
        self.mutation('QualificationSubjects.cs', 'QualificationSetupCleanup(s,delegate {Marshal.FreeHGlobal(memory[i]);},"setup_heap_"+i)', 'Marshal.FreeHGlobal(memory[i])')

    def test_source_finally_exceptions_are_cleanup_uncertain(self):
        self.mutation('QualificationSubjects.cs', 's.OwnershipCertain=false;r.Numbers["source_inspection_cleanup_uncertain"]=1;throw;', 'throw;')

    def test_routing_preserves_old_controls(self):
        workflow = (ROOT / '.github/workflows/windows-lpac-runtime-diagnostic.yml').read_text()
        self.assertIn('tests/windows-lpac-runtime/baseline/run.ps1', workflow)
        self.assertIn('tests/windows-lpac-runtime/run-runtime.ps1', workflow)
        self.assertIn('tests/windows-broker-direct/qualification-audit.py', workflow)
        self.assertIn('tests/windows-broker-direct/run-pilot.ps1 -Fixture', workflow)
        self.assertNotIn('continue-on-error', workflow)
        self.assertIn('timeout-minutes: 30', workflow)
        self.assertTrue((HERE / 'run-direct.ps1').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
