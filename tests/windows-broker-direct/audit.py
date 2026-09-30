#!/usr/bin/env python3
"""Portable source/mutation audits, not execution of Windows APIs or runtimes."""
import hashlib
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
FROZEN = {'tests/windows-lpac-runtime/.gitattributes': 'fbb21c6a8f92cc82badddc64d5e3dd180c48264740cc7c072449834f79307888', 'tests/windows-lpac-runtime/Cargo.lock': '826867ceefda64f50bb9b59a6ca52a3286ed71e4f872695f2f95c2829c5c59ab', 'tests/windows-lpac-runtime/Cargo.toml': '2606665bf677878acff777883cbd6d44b465a8946c9cf8a4fab77089f3554d7c', 'tests/windows-lpac-runtime/README.md': '5e7552384f74a2190d5590dd6f11ccdf9f476cb3de38dc7d710c21e0bd78ae5c', 'tests/windows-lpac-runtime/RuntimeLauncher.cs': 'e8aa4e73c4e5119002f22bec07d6f1152c60b001778c01984b2a768c873162de', 'tests/windows-lpac-runtime/audit.py': '15798c18bf4dbe6caaa9f367e759ddc0c22a7d57b901a36edcf79b0727f1f160', 'tests/windows-lpac-runtime/baseline/NativeLauncher.cs': 'e83075d8302a4fc27c91ece3a65cd8122ac6298fb2d9449bd9cb5e41147ef223', 'tests/windows-lpac-runtime/baseline/run.ps1': '8bae4d860fac03959ba11ab9669c649d4063c61eab8c56410716558a4ff8200e', 'tests/windows-lpac-runtime/baseline/windows_sandbox_fixture.rs': '1d9cee541420fa62d880953ebf481fad32350113871fdc6086dc5fd6e4971ec2', 'tests/windows-lpac-runtime/metadata-contract-tests.ps1': 'f7741412ca39dc47a156908741ce9700e85125968f968658d1e3d5fd7043c9d0', 'tests/windows-lpac-runtime/metadata.ps1': '7c83ecfe5cb41a96e459f72de35459a9ffeb929241454a2c02002d5ee7def9e2', 'tests/windows-lpac-runtime/prepare.ps1': 'fd2ea33e0ff7213a48f3fa55402adf227a1e5e94e955eecf2c344e3d32e82d03', 'tests/windows-lpac-runtime/private_stdin.rs': '777222dce5e0719d100656a42f031668951d80192ef061cf1a7d90637107f528', 'tests/windows-lpac-runtime/run-runtime.ps1': '0b86bbf993e6415a4be5ba2f43bd7944e98a09b8f62d18d124449fef6a4985f5', 'tests/windows-lpac-runtime/runtime_contract.rs': '04dfdad318b0b953977bd3534790dbb516426b015072d573f0bdf6cb58c05078', 'tests/windows-lpac-runtime/runtime_fixture.rs': '7514a523d9b0e17028a70996d91cf41baa856d26c2463e31bb676976b8cff437', 'tests/windows-lpac-runtime/spawn_observations.rs': '0d799bef6d042fa10b6a4f7db6b5fa1fdf6cc09a733f007bc8dc6815bc526494'}


# Reviewed new-method bytes: intentional changes require updating these pins in the same reviewed patch.
APPROVED_BOUNDARY = {'DirectNative.cs': '36123701edbeb11c8227ff903b7c399201acccc4bcaa0e7fe489f14fe028af3f', 'DirectHandles.cs': '927d73169be1bea2f578ad79fa9d508b35d46c000295b41269a93577087c57ca', 'DirectCases.cs': '2dd6d671e8e75c4b64620c08c974eeeb5a4a4c2690b143b716fa8efb31f66932', 'DirectLauncher.cs': '309adbf2b5c00712a914631c1b2849c5ecdac8fd42feb7f43ee7d5869f033a48', 'DirectCapture.cs': 'ee66abb5bc9c79e696eec72d35e97fffdc039d393289fde20db31be0c41c56bd', 'run-direct.ps1': '099443bd437ac9d9b4633ec741089c4df50c734ca3a5ff0eb902f540ba9c0a09'}

def inspect(sources):
    for name, digest in APPROVED_BOUNDARY.items():
        assert hashlib.sha256(sources[name].encode()).hexdigest() == digest, name
    native, handles, cases, launch, capture, runner = (sources[name] for name in (
        'DirectNative.cs', 'DirectHandles.cs', 'DirectCases.cs', 'DirectLauncher.cs', 'DirectCapture.cs', 'run-direct.ps1'))
    assert native == (ROOT / 'tests/windows-lpac-runtime/RuntimeLauncher.cs').read_text().split(
        '    // root must be a NEW EMPTY directory')[0].replace(
            'public static class LpacRuntimeLauncher {', 'public static partial class BrokerDirectLauncher {') + '}\n'
    for fragment in ['IntPtr.Zero,0,out sid', 'capabilities.Sid=sid', 'new IntPtr(0x20009)',
                     'new IntPtr(0x2000f)', 'KILL_ON_JOB_CLOSE', 'CREATE_SUSPENDED|EXTENDED|UNICODE|0x08000000u']:
        assert fragment in launch, fragment
    for fragment in ['Marshal.AllocHGlobal(3*IntPtr.Size)', 'new IntPtr(0x20002)',
                     'Marshal.WriteIntPtr(handles,0,input)', 'Marshal.WriteIntPtr(handles,IntPtr.Size,output)',
                     'Marshal.WriteIntPtr(handles,2*IntPtr.Size,error)', 'r.HandleListCount=3',
                     'startup.Startup.flags=0x100', 'startup.Startup.input=input',
                     'startup.Startup.output=output', 'startup.Startup.error=error']:
        assert fragment in launch, fragment
    assert launch.index('r.HostStdioClosed=closeCertain') < launch.index('VerifyToken(pi.process') < launch.index('AssignProcessToJobObject(job,pi.process)') < launch.index('ResumeThread(pi.thread)')
    assert 'if(!closeCertain) throw' in launch and 'if(!r.TokenVerified) throw' in launch
    for fragment in ['OpenProcessToken(process,8,out token)', 'app==1 && lpac==1 && capabilities==0',
                     'actualPackage==package && integrity=="S-1-16-4096"', 'return valid && closed',
                     'pointer<start', 'pointer-start<(ulong)header', '(ulong)returned-(pointer-start)<8',
                     'sidBytes>(ulong)returned-(pointer-start)', 'CloseOwned(ref token,"token",r)']:
        assert fragment in handles, fragment
    for fragment in ['GetTokenInformation(token,46,IntPtr.Zero,0,out size)',
                     'r.Numbers["lpac_size_error"]=error', 'Marshal.AllocHGlobal(4)',
                     'Marshal.WriteInt32(data,unchecked((int)0xA5A5A5A5))',
                     'GetTokenInformation(token,46,data,4,out returned)',
                     'if(!success || returned!=4) return null',
                     'r.Numbers["lpac_fixed_value_valid"]=success && returned==4 ? 1 : 0',
                     'int? app=null,lpac=null,capabilities=null',
                     'valid=all && app==1 && lpac==1 && capabilities==0',
                     'r.Numbers[label+"_observation_success"]=success?1:0']:
        assert fragment in handles, fragment
    assert handles.count('all=RequiredTokenObservation(') == 5
    assert handles.count('},"appcontainer",r) && all;') == 1
    assert handles.count('},"lpac",r) && all;') == 1
    assert handles.count('},"capabilities",r) && all;') == 1
    assert handles.count('},"appcontainer_sid",r) && all;') == 1
    assert handles.count('},"integrity_sid",r) && all;') == 1
    assert 'all=all && RequiredTokenObservation' not in handles
    assert '[DllImport("ntdll.dll",ExactSpelling=true)] static extern int NtQueryInformationToken(' in handles
    assert 'static void ObserveNativeDword(' in handles
    assert 'if(kind!=29 && kind!=46) throw' in handles
    assert 'if((data.ToInt64()&3)!=0) throw' in handles
    assert 'uint returned=0xDEADBEEF;' in handles
    assert 'int status=NtQueryInformationToken(token,kind,data,4,ref returned);' in handles
    assert re.findall(r'ObserveNativeDword\(token,(.*)\);', handles) == [
        '29,"native_appcontainer",r', '46,"native_lpac",r']
    assert 'r.Numbers["native_queries_observation_only"]=1;' in handles
    assert 'r.Numbers[label+"_ntstatus_unsigned"]=unchecked((uint)status)' in handles
    assert 'r.Numbers[label+"_buffer_unchanged"]=raw==unchecked((int)0xA5A5A5A5)?1:0' in handles
    assert 'r.Numbers[label+"_return_length_unchanged"]=returned==0xDEADBEEF?1:0' in handles
    native_guard = 'if(r.Numbers.ContainsKey("native_queries_observation_only"))'
    assert native_guard in launch
    assert launch.index('if(!r.TokenVerified) throw') < launch.index(native_guard) < launch.index('AssignProcessToJobObject(job,pi.process)') < launch.index('ResumeThread(pi.thread)')
    assert 'throw new InvalidOperationException("native token observations collected; reference must remain unresumed")' in launch
    predicate = 'valid=all && app==1 && lpac==1 && capabilities==0 && actualPackage==package && integrity=="S-1-16-4096";'
    assert predicate in handles and handles.index(predicate) < handles.index('ObserveNativeDword(token,29,')
    assert handles.index('pointer<start') < handles.index('Marshal.ReadByte(sid,1)') < handles.index('!IsValidSid(sid)')
    assert 'File.WriteAllText(recovery,"Pending owned recovery scope:' in launch
    assert launch.index('File.WriteAllText(recovery,') < launch.index('Directory.CreateDirectory(root)')
    assert 'if(stopped && r.Drained)' in launch
    assert '(!r.Created || (r.TokenVerified && r.Assigned && r.Resumed))' in launch
    assert launch.index('DeleteAppContainerProfile(name)') < launch.index('Directory.Delete(root,true)') < launch.index('File.Delete(recovery)')
    for fragment in ['0x00200080', '(info.attributes&0x410)!=0', 'info.links!=1',
                     'GetFileType(handle)!=1', 'Path.GetFullPath(path)', 'identity!=r.Identities["stdout"]',
                     'identity!=r.Identities["stderr"]', 'new SafeFileHandle(handle,false)',
                     'new FileStream(safe,FileAccess.Read)', 'CloseOwned(ref handle,"capture_"+file,r)']:
        assert fragment in capture, fragment
    expected_opens = [
        'ref writer,inputPath,0x40000000,1,false,"stdin_writer",r',
        'ref input,inputPath,0x80000000,3,true,"stdin",r',
        'ref output,Path.Combine(workspace,"stdout.txt"),0x40000000,1,true,"stdout",r',
        'ref error,Path.Combine(workspace,"stderr.txt"),0x40000000,1,true,"stderr",r',
    ]
    assert re.findall(r'OpenPrivate\((.*)\);', launch) == expected_opens
    assert re.findall(r'capabilities\.\w+\s*=[^;]*;', launch) == ['capabilities.Sid=sid;']
    assert re.findall(r'limits\.Basic\.flags\s*=[^;]*;', launch) == ['limits.Basic.flags=KILL_ON_JOB_CLOSE;']
    for name in ('input', 'output', 'error'):
        label = {'input': 'stdin', 'output': 'stdout', 'error': 'stderr'}[name]
        close = 'closeCertain=CloseOwned(ref '+name+',"'+label+'",r) && closeCertain;'
        assert close in launch and launch.index(close) < launch.index('r.HostStdioClosed=closeCertain')
    assert 'if(error==2 && !(r.StdioValidated && (file=="stdout.txt" || file=="stderr.txt"))) return true;' in capture
    assert 'const long CaptureLimit=1024*1024;' in capture
    assert 'info.sizeHigh!=0 || info.sizeLow>CaptureLimit' in capture
    assert 'Math.Min(buffer.Length,CaptureLimit+1-total)' in capture
    assert 'if(total>CaptureLimit) throw' in capture
    assert 'CopyTo' not in capture
    assert 'File.Copy' not in capture and 'File.OpenRead' not in capture
    assert 'if(kind!="reference" && kind!="node" && kind!="cmd" && kind!="powershell" && kind!="pwsh")' in launch
    assert "@('reference','node','cmd','powershell','pwsh')" in runner
    assert "windows_sandbox_fixture.exe" in runner
    assert "blocked_matched_reference_failed" in runner
    assert "winsock_initialization_failed_10107" in runner
    assert 'sourceHash!=destinationHash' in launch and 'fixtureHash!=privateFixtureHash' in launch
    assert 'new SortedDictionary<string,string>(StringComparer.OrdinalIgnoreCase)' in cases
    for name in ('HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA'):
        assert '{"'+name+'",workspace}' in cases
    assert 'GetEnvironmentVariables' not in cases
    assert 'read_type=' in cases and 'read_hresult=' in cases and 'write_type=' in cases and 'write_hresult=' in cases
    assert 'System.UnauthorizedAccessException' in cases and '-2147024891' in cases and '-band 65535' not in cases
    assert 'script-entry.txt' in launch and 'script-entry.txt' in cases
    assert 'runtime-entered' in cases and cases.count('script-entry.txt') == 3
    assert 'known_startup_status_without_script_entry' in runner
    assert 'no_script_entry_evidence_inconclusive' in runner and 'user_code_positive_operation_failed' in runner
    assert '[IO.Path]::GetTempPath() | Select-Object -Unique' in runner
    assert 'GetHandleInformation(handle,out handleFlags)' in handles
    assert '((handleFlags&1)!=0)!=inherit' in handles
    assert '$row.operation_completed=$safeLaunch -and $row.script_entry_observed -and $row.output_ok -and $row.mutation_ok' in runner
    escape_guard = '$row.positive_passed=$row.positive_passed -and -not $row.runtime_outside_read_observed'
    assert escape_guard in runner
    assert runner.index(escape_guard) < runner.index('$row.status=if(-not $r.Created)') < runner.rindex('$outcomes+=@($row);$outcomes')
    assert 'cmd_errorlevel_is_not_raw_denial_evidence' in runner
    assert "Where-Object {$_ -ceq $line}).Count -ne 1" in runner
    assert 'earlier diagnostic cleanup remains uncertain' in runner
    assert 'if($outcomes.Count -ne 5 -or -not $referenceValid' in runner
    assert "not_covered=@('python','npm.cmd','git','nested_child_support','ConPTY','production_integration')" in runner
    for forbidden in ['CreateProcessAsUser', 'DuplicateToken', 'SetTokenInformation', 'AdjustTokenPrivileges',
                      'SetThreadToken', 'CREATE_BREAKAWAY', 'ExecutionPolicy Bypass', 'internetClient']:
        assert forbidden not in ''.join(sources.values()), forbidden


class DirectAudit(unittest.TestCase):
    def setUp(self):
        self.sources = {p.name: p.read_text() for p in pathlib.Path(__file__).parent.iterdir() if p.suffix in ('.cs', '.ps1')}

    def test_approved_source(self):
        inspect(self.sources)

    def test_all_twenty_nested_controls_byte_identical(self):
        for file, digest in FROZEN.items():
            self.assertEqual(hashlib.sha256((ROOT / file).read_bytes()).hexdigest(), digest, file)

    def mutation(self, file, before, after):
        self.assertIn(before, self.sources[file])
        self.sources[file] = self.sources[file].replace(before, after)
        with self.assertRaises(AssertionError):
            inspect(self.sources)

    def test_added_capability_rejected(self):
        self.mutation('DirectLauncher.cs', 'IntPtr.Zero,0,out sid', 'IntPtr.Zero,1,out sid')

    def test_broader_handle_list_rejected(self):
        self.mutation('DirectLauncher.cs', 'Marshal.AllocHGlobal(3*IntPtr.Size)', 'Marshal.AllocHGlobal(4*IntPtr.Size)')

    def test_token_lpacsid_required(self):
        self.mutation('DirectHandles.cs', 'actualPackage==package && integrity=="S-1-16-4096"', 'true')

    def test_token_capability_zero_required(self):
        self.mutation('DirectHandles.cs', 'app==1 && lpac==1 && capabilities==0', 'app==1')

    def test_token_pointer_bounds_required(self):
        self.mutation('DirectHandles.cs', 'pointer<start', 'false')

    def test_token_span_bounds_required(self):
        self.mutation('DirectHandles.cs', 'sidBytes>(ulong)returned-(pointer-start)', 'false')

    def test_token_close_required(self):
        self.mutation('DirectHandles.cs', 'return valid && closed', 'return valid')

    def test_stopped_before_capture_required(self):
        self.mutation('DirectLauncher.cs', 'if(stopped && r.Drained)', 'if(r.Drained)')

    def test_capture_no_follow_required(self):
        self.mutation('DirectCapture.cs', '0x00200080', '0x80')

    def test_capture_stdio_identity_required(self):
        self.mutation('DirectCapture.cs', 'identity!=r.Identities["stdout"]', 'false')

    def test_power_shell_full_error_required(self):
        self.mutation('DirectCases.cs', '-2147024891', '5')

    def test_native_reference_is_unchanged_fixture(self):
        self.mutation('run-direct.ps1', 'windows_sandbox_fixture.exe', 'windows_runtime_fixture.exe')

    def test_script_entry_checkpoint_required(self):
        self.mutation('DirectCases.cs', 'script-entry.txt', 'missing-entry.txt')

    def test_stdio_inheritance_verified(self):
        self.mutation('DirectHandles.cs', '((handleFlags&1)!=0)!=inherit', 'false')

    def test_actual_temp_recovery_root_checked(self):
        self.mutation('run-direct.ps1', '[IO.Path]::GetTempPath() | Select-Object -Unique', '$env:RUNNER_TEMP | Select-Object -Unique')

    def test_missing_stdio_cannot_be_optional(self):
        self.mutation('DirectCapture.cs', 'error==2 && !(r.StdioValidated && (file=="stdout.txt" || file=="stderr.txt"))', 'error==2')

    def test_optional_script_receipt_can_be_absent(self):
        self.assertIn('if(error==2 && !(r.StdioValidated && (file=="stdout.txt" || file=="stderr.txt"))) return true;', self.sources['DirectCapture.cs'])

    def test_capture_metadata_cap_required(self):
        self.mutation('DirectCapture.cs', 'info.sizeHigh!=0 || info.sizeLow>CaptureLimit', 'false')

    def test_capture_stream_cap_required(self):
        self.mutation('DirectCapture.cs', 'if(total>CaptureLimit) throw', 'if(false) throw')

    def test_stdin_write_authority_rejected(self):
        self.mutation('DirectLauncher.cs', 'inputPath,0x80000000,3', 'inputPath,0xC0000000,3')

    def test_stdout_read_authority_rejected(self):
        self.mutation('DirectLauncher.cs', '"stdout.txt"),0x40000000', '"stdout.txt"),0xC0000000')

    def test_capabilities_assignment_rejected(self):
        self.mutation('DirectLauncher.cs', 'capabilities.Sid=sid;', 'capabilities.Sid=sid;capabilities.Count=1;')

    def test_broker_stdout_close_required(self):
        self.mutation('DirectLauncher.cs', 'closeCertain=CloseOwned(ref output,"stdout",r) && closeCertain;', '')

    def test_job_breakaway_rejected(self):
        self.mutation('DirectLauncher.cs', 'limits.Basic.flags=KILL_ON_JOB_CLOSE;', 'limits.Basic.flags=KILL_ON_JOB_CLOSE|0x800;')

    def test_handle_list_byte_count_required(self):
        self.mutation('DirectLauncher.cs', 'handles,new IntPtr(3*IntPtr.Size)', 'handles,new IntPtr(4*IntPtr.Size)')

    def test_close_failure_prevents_resume(self):
        self.mutation('DirectLauncher.cs', 'if(!closeCertain) throw new InvalidOperationException("broker stdio close uncertain");', '')

    def test_actual_handle_close_required(self):
        self.mutation('DirectHandles.cs', 'bool ok=CloseChecked(handle);', 'bool ok=true;')

    def test_private_operation_independent_of_canary_exit(self):
        self.mutation('run-direct.ps1', '$row.operation_completed=$safeLaunch -and $row.script_entry_observed -and $row.output_ok -and $row.mutation_ok', '$row.operation_completed=$row.positive_passed')

    def test_observed_escape_invalidates_positive_before_serialization(self):
        self.mutation('run-direct.ps1', '$row.positive_passed=$row.positive_passed -and -not $row.runtime_outside_read_observed', '')

    def test_failed_fixed_query_value_never_accepted(self):
        self.mutation('DirectHandles.cs', 'if(!success || returned!=4) return null', 'if(returned!=4) return null')

    def test_fixed_query_exact_length_required(self):
        self.mutation('DirectHandles.cs', 'if(!success || returned!=4) return null', 'if(!success) return null')

    def test_fixed_query_nonpassing_sentinel_required(self):
        self.mutation('DirectHandles.cs', 'Marshal.WriteInt32(data,unchecked((int)0xA5A5A5A5))', 'Marshal.WriteInt32(data,1)')

    def test_missing_capability_query_cannot_default_zero(self):
        self.mutation('DirectHandles.cs', 'int? app=null,lpac=null,capabilities=null', 'int? app=null,lpac=null,capabilities=0')

    def test_exact_lpac_value_one_required(self):
        self.mutation('DirectHandles.cs', 'valid=all && app==1 && lpac==1 && capabilities==0', 'valid=all && app==1 && capabilities==0')

    def test_independent_queries_not_short_circuited(self):
        self.mutation('DirectHandles.cs', 'all=RequiredTokenObservation(', 'all=all && RequiredTokenObservation(')

    def test_original_sizing_observation_preserved(self):
        self.mutation('DirectHandles.cs', 'GetTokenInformation(token,46,IntPtr.Zero,0,out size)', 'GetTokenInformation(token,29,IntPtr.Zero,0,out size)')

    def test_native_observation_no_resume_guard_required(self):
        self.mutation('DirectLauncher.cs', 'if(r.Numbers.ContainsKey("native_queries_observation_only"))', 'if(false)')

    def test_native_observation_cannot_replace_win32_predicate(self):
        self.mutation('DirectHandles.cs', 'valid=all && app==1 && lpac==1 && capabilities==0 && actualPackage==package && integrity=="S-1-16-4096";', 'valid=true;')

    def test_native_classes_are_finite(self):
        self.mutation('DirectHandles.cs', 'ObserveNativeDword(token,46,"native_lpac",r);', 'ObserveNativeDword(token,39,"native_lpac",r);')

    def test_native_buffer_alignment_required(self):
        self.mutation('DirectHandles.cs', 'if((data.ToInt64()&3)!=0) throw', 'if(false) throw')

    def test_native_return_length_sentinel_required(self):
        self.mutation('DirectHandles.cs', 'uint returned=0xDEADBEEF;', 'uint returned=4;')

    def test_native_ntstatus_not_booleanized(self):
        self.mutation('DirectHandles.cs', 'r.Numbers[label+"_ntstatus_unsigned"]=unchecked((uint)status)', 'r.Numbers[label+"_ntstatus_unsigned"]=status==0?1:0')

    def test_native_observation_cannot_flip_valid_after_win32(self):
        self.mutation('DirectHandles.cs', 'ObserveNativeDword(token,46,"native_lpac",r);', 'ObserveNativeDword(token,46,"native_lpac",r);valid=true;')

    def test_existing_workflow_gates_retained(self):
        workflow = (ROOT / '.github/workflows/windows-lpac-runtime-diagnostic.yml').read_text()
        self.assertNotIn('continue-on-error', workflow)
        self.assertIn('timeout-minutes: 30', workflow)
        self.assertIn('tests/windows-lpac-runtime/baseline/run.ps1', workflow)
        self.assertIn('tests/windows-lpac-runtime/run-runtime.ps1', workflow)
        self.assertIn('tests/windows-broker-direct/run-direct.ps1 -Fixture tests/windows-lpac-runtime/target/debug/windows_sandbox_fixture.exe', workflow)


if __name__ == '__main__':
    unittest.main(verbosity=2)
