#!/usr/bin/env python3
"""Source and synthetic receipt contracts only; never compile or call Windows APIs.

check_receipt consumes ONLY the additional Numbers/Identities projection. Callers
must independently bind it to the original case and complete authenticated artifact.
Its finite return is an operation fact, never artifact authentication, root cause,
reading/execution evidence, original-gate acceptance, or Windows runtime acceptance.
"""
import hashlib
import json
import pathlib
import re
import runpy
import sys
import unittest

HERE = pathlib.Path(__file__).parent
BROKER = HERE.parent / 'windows-broker-direct'
ROOT = HERE.parents[1]
NAMES = ('CmdDebugNative.cs', 'CmdDebugSession.cs', 'CmdDebugContractTests.cs')
# Frozen candidate pins for independent review; later changes require repinning and re-review.
PINS = {'CmdDebugNative.cs': 'b88f6c504edf06e5aee16836a0d06f96222be09117e905f5f70e82d9789df547', 'CmdDebugSession.cs': 'e9d5e493b7ae1c79f17ce5b290cd352e5ca26baf7283cdd1d677f71ab13f7155', 'CmdDebugContractTests.cs': '182f3baa5620214d6d62aa74ebec50eb951e881754845340f3a6857eddd55491'}
PREFIX = 'cmd_debug_'
APIS = ('GetProcessId GetProcessTimes IsWow64Process2 GetSystemDirectoryW DebugActiveProcess '
        'WaitForDebugEvent ContinueDebugEvent ReadProcessMemory WriteProcessMemory FlushInstructionCache '
        'GetThreadContext SetThreadContext SuspendThread ResumeThread GetFinalPathNameByHandleW '
        'DuplicateHandle GetCurrentProcess GetFileInformationByHandle CloseHandle WaitForSingleObject '
        'GetExitCodeProcess TerminateProcess').split()
NUMERIC = ('pid main_tid creation_filetime attach_attempted attach_succeeded attach_break_seen '
           'entries_ready_before_resume event_count cleanup_event_count thread_peak module_peak entry_hits '
           'unsupported_names read_bytes write_attempts matched_tid pair_complete desired_access '
           'object_attributes share_access file_attributes create_disposition open_options ntstatus_u32 '
           'object_identity_matched active_patches_at_exit owned_suspends_at_exit exit_event_seen '
           'exit_event_continued process_signaled terminal_exit_u32 abort_terminate_attempted '
           'abort_terminate_error native_error elapsed_ms').split()
ENUMS = {
    'protocol': {'own-child-open-v1'},
    'result': set('incomplete no_match matched_open_failed matched_open_succeeded observed_pending debugger_perturbed'.split()),
    'error': set(('none abi_unsupported target_identity attach_failed attach_unknown bootstrap_incomplete module_identity '
                  'pe_invalid stub_unsupported native_failed read_failed patch_failed context_failed suspend_failed '
                  'resume_failed event_protocol thread_limit module_limit event_limit entry_limit read_limit write_limit '
                  'deadline unsupported_match return_ambiguous pending_io object_mismatch close_uncertain exit_unconfirmed '
                  'selected_case_failed debugger_perturbed internal_exception').split()),
    'error_api': {'none'} | (set(APIS) - {'GetCurrentProcess'}),
    'cleanup': {'not_attached', 'exit_confirmed', 'retained_fatal'},
    'open_api': {'none', 'NtCreateFile', 'NtOpenFile'},
}
FLAGS = set(('attach_attempted attach_succeeded attach_break_seen entries_ready_before_resume pair_complete '
             'exit_event_seen exit_event_continued process_signaled abort_terminate_attempted').split())
COUNTERS = dict(event_count=4096, cleanup_event_count=512, thread_peak=32, module_peak=128,
                entry_hits=128, unsupported_names=128, read_bytes=1048576, write_attempts=264,
                active_patches_at_exit=3, owned_suspends_at_exit=31, native_error=0xffffffff)
MASKS = set('desired_access object_attributes share_access file_attributes create_disposition open_options ntstatus_u32 terminal_exit_u32 abort_terminate_error'.split())
FORBIDDEN = ('NtReadFile NtClose ZwClose DUPLICATE_CLOSE_SOURCE DebugActiveProcessStop DebugBreakProcess '
             'DebugSetProcessKillOnExit VirtualProtect VirtualProtectEx OpenProcess OpenThread CreateProcess '
             'CreateRemoteThread QueueUserAPC AdjustTokenPrivileges SetThreadToken SetTokenInformation '
             'LoadLibrary GetProcAddress CreateToolhelp32Snapshot Thread32First Process32First '
             'EventRegister EventWrite RegOpenKeyEx Socket WSAStartup').split()
SIGNATURES = dict(zip(APIS, (
    'uint(IntPtr process)',
    'bool(IntPtr process,out CmdFileTime creation,out CmdFileTime exit,out CmdFileTime kernel,out CmdFileTime user)',
    'bool(IntPtr process,out ushort machine,out ushort native)',
    'uint(StringBuilder buffer,uint size)', 'bool(uint pid)',
    'bool(out CmdEventLayout value,uint milliseconds)', 'bool(uint pid,uint tid,uint disposition)',
    'bool(IntPtr process,IntPtr address,[Out] byte[] buffer,UIntPtr count,out UIntPtr actual)',
    'bool(IntPtr process,IntPtr address,byte[] buffer,UIntPtr count,out UIntPtr actual)',
    'bool(IntPtr process,IntPtr address,UIntPtr count)',
    'bool(IntPtr thread,IntPtr context)', 'bool(IntPtr thread,IntPtr context)',
    'uint(IntPtr thread)', 'uint(IntPtr thread)',
    'uint(IntPtr file,StringBuilder buffer,uint size,uint flags)',
    'bool(IntPtr source,IntPtr target,IntPtr destination,out IntPtr duplicate,uint access,[MarshalAs(UnmanagedType.Bool)] bool inherit,uint options)',
    'IntPtr()', 'bool(IntPtr file,out CmdFileInfoLayout info)', 'bool(IntPtr handle)',
    'uint(IntPtr process,uint milliseconds)', 'bool(IntPtr process,out uint exit)', 'bool(IntPtr process,uint code)',
)))
LEX = re.compile(r'@"(?:""|[^"])*"|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\n]*|/\*.*?\*/', re.S)


def source_text(source, strings=True):
    return LEX.sub(lambda m: m[0] if strings and not m[0].startswith(('/', '/*')) else ' ', source)


def compact(source):
    return re.sub(r'\s+', '', source_text(source))


def require(condition):
    if not condition:
        raise ValueError('invalid cmd debug receipt')


def check_receipt(data):
    """Validate bounded declared facts. The returned label is not an acceptance verdict."""
    require(type(data) is bytes and 0 < len(data) <= 16384)
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result)
            result[key] = value
        return result
    def integer(value):
        require(len(value) <= 20)
        return int(value)
    def reject(_):
        raise ValueError('invalid cmd debug receipt')
    try:
        value = json.loads(data.decode('utf-8', errors='strict'), object_pairs_hook=pairs,
                           parse_int=integer, parse_float=reject, parse_constant=reject)
    except (ValueError, UnicodeError, RecursionError):
        raise ValueError('invalid cmd debug receipt') from None
    require(type(value) is dict and set(value) == {'Numbers', 'Identities'})
    raw_n, raw_i = value['Numbers'], value['Identities']
    require(type(raw_n) is dict and set(raw_n) == {PREFIX + k for k in NUMERIC})
    require(type(raw_i) is dict and set(raw_i) == {PREFIX + k for k in ENUMS})
    n, i = ({k[len(PREFIX):]: v for k, v in values.items()} for values in (raw_n, raw_i))
    require(all(type(v) is int for v in n.values()))
    require(all(type(i[k]) is str and i[k] in choices for k, choices in ENUMS.items()))
    require(all(n[k] in (0, 1) for k in FLAGS))
    require(all(0 <= n[k] <= maximum for k, maximum in COUNTERS.items()))
    require(all(-1 <= n[k] <= 0xffffffff for k in MASKS))
    require(all(n[k] == -1 or 0 < n[k] <= 0xffffffff for k in ('pid', 'main_tid', 'matched_tid')))
    require(n['creation_filetime'] == -1 or 0 < n['creation_filetime'] < 2**63)
    require(n['object_identity_matched'] in (-1, 0, 1) and -1 <= n['elapsed_ms'] <= 35000)
    require(n['attach_succeeded'] <= n['attach_attempted'])
    require(n['attach_break_seen'] <= n['entries_ready_before_resume'] <= n['attach_succeeded'])
    require(n['process_signaled'] <= n['exit_event_continued'] <= n['exit_event_seen'] <= n['attach_succeeded'])
    require(n['abort_terminate_attempted'] <= n['attach_succeeded'])
    require(n['unsupported_names'] <= n['entry_hits'])
    if n['attach_succeeded']:
        require(all(n[k] > 0 for k in ('pid', 'main_tid', 'creation_filetime')))
    if i['cleanup'] == 'exit_confirmed':
        require(n['process_signaled'] == 1 and n['terminal_exit_u32'] >= 0)
    elif i['cleanup'] == 'not_attached':
        require(n['attach_succeeded'] == n['exit_event_seen'] == 0)
    else:
        require(i['error'] != 'none')
    if i['open_api'] == 'none':
        require(n['matched_tid'] == -1 and n['pair_complete'] == 0 and n['ntstatus_u32'] == -1)
        require(all(n[k] == -1 for k in MASKS - {'terminal_exit_u32', 'abort_terminate_error'}))
    else:
        require(all(n[k] >= 0 for k in ('desired_access', 'object_attributes', 'share_access', 'open_options')))
        if i['open_api'] == 'NtOpenFile':
            require(n['file_attributes'] == n['create_disposition'] == -1)
        else:
            require(n['file_attributes'] >= 0 and n['create_disposition'] >= 0)
    status = n['ntstatus_u32']
    if status == 0x103:
        require(i['result'] in ('observed_pending', 'debugger_perturbed'))
        require(n['pair_complete'] == 0 and n['object_identity_matched'] == -1 and i['error'] != 'none')
    if status >= 0x80000000:
        require(n['object_identity_matched'] == -1)
    if n['object_identity_matched'] == 1:
        require(0 <= status < 0x80000000 and status != 0x103)
    if n['pair_complete']:
        require(n['matched_tid'] > 0 and n['attach_break_seen'] == 1 and n['entry_hits'] > 0)
        require(status >= 0 and status != 0x103 and i['open_api'] != 'none')
        require(status >= 0x80000000 or n['object_identity_matched'] == 1)
        expected = 'matched_open_failed' if status >= 0x80000000 else 'matched_open_succeeded'
        require(i['result'] in (expected, 'debugger_perturbed'))
    if i['result'] == 'matched_open_failed':
        require(status >= 0x80000000)
    if i['result'] == 'matched_open_succeeded':
        require(0 <= status < 0x80000000 and status != 0x103 and n['object_identity_matched'] == 1)
    if i['result'] == 'observed_pending':
        require(status == 0x103 and i['error'] == 'pending_io')
    if i['result'] == 'no_match':
        require(n['matched_tid'] == -1 and n['pair_complete'] == 0 and i['error'] != 'none')
    if i['result'] == 'debugger_perturbed':
        require(i['error'] == 'debugger_perturbed')
    if i['error'] == 'none':
        require(n['pair_complete'] == 1 and i['cleanup'] == 'exit_confirmed' and n['terminal_exit_u32'] == 1)
        require(n['active_patches_at_exit'] == n['owned_suspends_at_exit'] == n['abort_terminate_attempted'] == 0)
        require(i['error_api'] == 'none' and n['native_error'] == 0 and n['elapsed_ms'] >= 0)
    if i['result'].startswith('matched_open_') and not n['pair_complete']:
        return 'incomplete'
    return i['result']


# Exact guard fragments are mutation-tested independently of whole-source hashes.
GUARDS = {
    NAMES[0]: (
        'allocation=Marshal.AllocHGlobal(1232+15);', '(allocation.ToInt64()+15)&~15L',
        'new int[]{48,56,66,68,120,128,136,144,152,160,168,176,184,192,200,208,216,224,232,240,248}',
        'if(IntPtr.Size!=8 || !BitConverter.IsLittleEndian)', 'Raw=new byte[1232];Put32(48,0x00100003);',
        'expected.Put64(200,before.U64(128));return SameRequested(expected);',
        'CmdRemoteReader.Add(before.U64(248),2)',
        'WriteProcessMemory(process.Value,Pointer(address),new byte[]{value},(UIntPtr)1,out actual)',
        'FlushInstructionCache(process.Value,Pointer(address),(UIntPtr)1)',
        'DuplicateHandle(process.Value,Pointer(target),GetCurrentProcess(),out output,0,false,2)',
        'duplicate=ok?new CmdDuplicate(output):default(CmdDuplicate);',
        'public override bool CloseImage(CmdImageFile file) { return Result(CloseHandle(file.Value)); }',
        'public override bool CloseDuplicate(CmdDuplicate file) { return Result(CloseHandle(file.Value)); }',
        'TerminateProcess(process.Value,91)', 'if(address==0 || delta>UInt64.MaxValue-address)',
        'if(count<=0 || count>1048576-BytesRead)', 'BytesRead+=count;', 'actual!=(ulong)count',
        'sections>=1 && sections<=96', 'CmdU16(header,4)==0x8664', 'CmdU16(optional,0)==0x20b',
        'module.ExportSize<=524288', 'functions<=8192 && names>0 && names<=8192',
        'Require(result[target]==0);', '!(rva>=module.ExportRva && rva-module.ExportRva<module.ExportSize)',
    ),
    NAMES[1]: (
        'subject.OwnershipCertain && subject.ProfileCreated && receipt.Created && receipt.Assigned && !receipt.Resumed',
        'receipt.CreationFlags==0x08080404 && receipt.Kind=="cmd"', 'machine==0 && native==0x8664',
        'N("attach_attempted",1);MayCallOriginalCleanup=false;attachUnknown=true;',
        'bool ok=api.Attach(subject.Process.pid);attachUnknown=false;',
        'if(pending==null || continueAttempted)', 'continueAttempted=true;',
        'Require(api.Continue(pending,disposition),"native_failed","ContinueDebugEvent");pending=null;',
        'e.Pid!=subject.Process.pid', '(cleanup?512:4096)', 'Math.Min(remaining,100)',
        'threads.Count>=32', 'modules.Count>=128', 'N("entry_hits")>=128', 'N("write_attempts")>=264',
        'if(t.IncrementOwned || t.ReleaseAttempted)', 't.ReleaseAttempted=true;',
        'previous==t.Previous+1', 'peer.Handle.Tid!=owner',
        'N("entries_ready_before_resume",1);ready=true;', 'Require(previous==1,"resume_failed","ResumeThread");',
        'p.Uncertain=true;', 'count==1', 'p.Active=arm;p.Uncertain=false;',
        '!c.MatchesAfterMov(beforeStep)', 'PatchByte(stepping,true);SetContext(t,c.WithRipTf(c.U64(248),false));ReleasePeers();',
        'if((c.U32(68)&0x100)!=0)', 'if(!attachBreak)', 'c.U64(152)!=CmdRemoteReader.Add(entryRsp,8)',
        'length>8192 || length>CmdU16(name,2)', 'new UnicodeEncoding(false,false,true)',
        r'String.Equals(text,@"\??\"+subject.Workspace+@"\direct.cmd",',
        'foreach(Patch p in patches) PatchByte(p,false);',
        'if(status==0x103) {I("result","observed_pending");Fault("pending_io");}',
        'uint status=(uint)(c.U64(120)&UInt32.MaxValue);', '(status&0x80000000)!=0',
        'protectedHandles.ContainsKey(candidate.Value)', 'api.CloseDuplicate(candidate)',
        'Continue(0x10002);N("exit_event_continued",1);', 'Math.Min(started+35000,api.NowMilliseconds+5000)',
        'Require(exit==debugExit,"target_identity","GetExitCodeProcess");BindIdentity(false);',
        '(first || value==creation)', 'identityUncertain=true;', 'identityUncertain=false;',
        'if(pending!=null && pending.Code==5) {Exit(true);return;}',
        'if(terminationAttempted) {Retain();return;}terminationAttempted=true;',
        'if(attachUnknown || identityUncertain || (pending!=null && (pending.Pid!=subject.Process.pid || continueAttempted)))',
        'waitUnknown=true;bool ok=api.Wait(', '!terminated || waitUnknown',
        'retainedCmdDebug=this;', 'r.Exit==1', 'pilot_cmd_observation_raw_complete',
        'pilot_cmd_observation_stdout_matches', 'pilot_cmd_observation_stderr_empty',
        '!session.MayCallOriginalCleanup || session.Failed', '!PilotNumber(r,"cmd_debug_pair_complete",1)',
        'row.Fatal=true;row.PositivePassed=false;', 'throw new InvalidOperationException("cmd_debug_incomplete");',
        'SetContext(t,c.WithRipTf(returnPatch.Address,(c.U32(68)&0x100)!=0));',
        'enum ImageOwnership {None,Owned,Attempted,Closed,Unknown}',
        'if(e==null || e.Pid!=subject.Process.pid) Fault("event_protocol");AdoptImage(e);if(e.Tid==0) Fault("event_protocol");',
        'pendingImage=e.File;pendingImageState=ImageOwnership.Unknown;',
        '(e.Code==3 && (e.File==e.Process || e.File==e.Thread))) Fault("close_uncertain");pendingImageState=ImageOwnership.Owned;',
        'if(value!=pendingImage) Fault("close_uncertain");',
        'if(pendingImageState!=ImageOwnership.Owned) Fault("close_uncertain");',
        'pendingImageState=ImageOwnership.Attempted;Require(api.CloseImage(new CmdImageFile(value)),"close_uncertain","CloseHandle");pendingImageState=ImageOwnership.Closed;',
        'if(pendingImageState!=ImageOwnership.None && pendingImageState!=ImageOwnership.Closed) Fault("close_uncertain");continueAttempted=true;',
        'if(pending!=null) {if(pending.Code==3 || pending.Code==6) CloseImage(pending.File);Continue(pending.Code==1?0x80010001u:0x10002u);}',
        'if(N("exit_event_seen")==1 || pendingImageState==ImageOwnership.Attempted || pendingImageState==ImageOwnership.Unknown) {Retain();return;}',
    ),
    NAMES[2]: ('RunCmdDebugContractTests()', 'MOV permits fresh R10=RCX and exact RIP delta',
               'never close original, borrowed or target handles', 'fatal precedes classifier and resolution',
               'pending never reads output or IO_STATUS_BLOCK', 'CmdTestFaultSweep()',
               'return TF preservation is exercised', 'false or exceptional image close is never retried',
               'uncertain early image close retains before any continuation'),
}


def inspect_sources(sources, old, runner, workflow, wrapper, pins=True):
    assert set(sources) == set(NAMES), 'new source inventory'
    if pins:
        assert set(PINS) == set(NAMES), 'candidate source pins not frozen'
        assert all(hashlib.sha256(sources[k].encode()).hexdigest() == PINS[k] for k in NAMES), 'source pin changed'
    old_imports = set(re.findall(r'\bextern\s+\w+\s+(\w+)\(', '\n'.join(old.values())))
    for name, source in sources.items():
        plain, code = source_text(source), source_text(source, False)
        assert len(source.splitlines()) <= 500, 'source line ceiling'
        assert set(re.findall(r'^using ([\w.]+);', plain, re.M)) <= {
            'System', 'System.Collections.Generic', 'System.Text', 'System.Diagnostics', 'System.Runtime.InteropServices'}, 'using boundary'
        assert not re.search(r'\b(?:unsafe|dynamic|async|await|delegate|Task|HashSet|SafeHandle|ModuleInitializer|LibraryImport)\b', code), 'capability boundary'
        assert not re.search(r'(?<!\.)\b(?:File|Directory|Registry|Process|Environment|Assembly|Activator)\s*\.', code), 'managed acquisition boundary'
        assert not re.search(r'\bSystem\.(?:IO|Net|Threading|Reflection)\b|\bSystem\.Diagnostics\.Process\b|\bnew\s+(?:Thread|Timer)\s*\(', code), 'managed execution boundary'
        assert not re.search(r'\b(?:Nt|Zw)\w+\s*\(', code), 'native syscall invocation'
        assert not re.search(r'\b(?:GetDelegateForFunctionPointer|GetFunctionPointerForDelegate|PtrToStructure)\s*\(', code), 'indirect native invocation'
        for forbidden in set(FORBIDDEN) | (old_imports - set(APIS)):
            assert not re.search(r'\b' + re.escape(forbidden) + r'\s*(?:\(|\b)', code), 'forbidden capability'
        if name != NAMES[0]:
            assert not re.search(r'\b(?:DllImport|extern)\b', code), 'native import outside adapter'
            assert not any(re.search(r'\b' + api + r'\s*\(', code) for api in APIS), 'direct API outside adapter'
        if name == NAMES[1]:
            assert not re.search(r'\.\s*(?:Message|StackTrace|InnerException|ToString|GetBaseException)\b', code), 'exception disclosure'
        if name == NAMES[2]:
            assert 'newCmdDebugNative(' not in compact(source), 'native test construction'
        repeated = {NAMES[1]: {10, 15, 39, 57}, NAMES[2]: {5}}
        for position, guard in enumerate(GUARDS[name]):
            assert compact(source).count(compact(guard)) == (2 if position in repeated.get(name, set()) else 1), 'required guard changed'
    native = source_text(sources[NAMES[0]])
    declarations = re.findall(r'\[DllImport\(([^\n]+)\)\]\s*(\[return:MarshalAs\(UnmanagedType.Bool\)\]\s*)?static extern (\w+) (\w+)\(([^;]*)\);', native)
    assert len(declarations) == 22 and {x[3] for x in declarations} == set(APIS), 'exact native inventory'
    assert len(re.findall(r'\bextern\b', native)) == 22, 'extra native declaration'
    for attributes, boolean, result, name, arguments in declarations:
        assert '"kernel32.dll"' in attributes and 'EntryPoint="' + name + '"' in attributes, 'native identity'
        assert 'ExactSpelling=true' in attributes and 'CallingConvention=CallingConvention.Winapi' in attributes, 'native ABI'
        assert compact(result + '(' + arguments + ')') == compact(SIGNATURES[name]), 'typed native signature'
        assert (result == 'bool') == bool(boolean), 'Win32 BOOL ABI'
        assert ('SetLastError=true' in attributes) == (name != 'GetCurrentProcess'), 'native error capture'
        assert ('CharSet=CharSet.Unicode' in attributes) == name.endswith('W'), 'Unicode ABI'
        count = 3 if name in ('CloseHandle', 'ResumeThread') else 2
        assert len(re.findall(r'\b' + name + r'\s*\(', source_text(native, False))) == count, 'native call-site inventory'
    session = compact(sources[NAMES[1]])
    assert session.count('api.Attach(') == session.count('api.ResumeMain(') == session.count('api.Terminate(') == 1, 'one target lifecycle'
    assert session.count('api.ResumePeer(') == session.count('api.CloseDuplicate(') == session.count('api.CloseImage(') == 1, 'one owned release site'
    assert set(re.findall(r'\bN\("([^"]+)"', sources[NAMES[1]])) <= set(NUMERIC), 'numeric emission allowlist'
    emitted = set(re.findall(r'\["cmd_debug_([^"]+)"\]', sources[NAMES[1]]))
    assert emitted <= set(NUMERIC) | set(ENUMS), 'additional field allowlist'
    keys = re.search(r'NumericKeys=\((.*?)\)\.Split', sources[NAMES[1]], re.S)
    assert keys and ''.join(re.findall(r'"([^"]*)"', keys[1])).split() == NUMERIC, 'numeric schema'
    assert set(re.findall(r'\bI\("([^"]+)"', sources[NAMES[1]])) == set(ENUMS), 'enum schema'
    gate = 'RequireCmdDebugComparable(cmdDebug,row);'
    assert runner.count(gate) == 1 and runner.index(gate) < runner.index('ClassifyPilotCase(row,evidence);'), 'preclassifier order'
    cleanup = 'if(cmdDebug!=null && !cmdDebug.MayCallOriginalCleanup)'
    assert runner.count(cleanup) == 1 and runner.index(cleanup) < runner.index('StopQualificationSubject(s);'), 'original cleanup gate'
    assert runner.index('r.Assigned=true;') < runner.index('cmdDebug.Observe();'), 'attach after job assignment'
    assert runner.index('ReadPilotCmdObservation(s,evidence);') < runner.index(gate), 'raw before comparator'
    assert runner.index(gate) < runner.index('journal.BindPreconditions(serialize(row));'), 'gate before resolution'
    assert 'if(cmdDebug.Failed) throw new InvalidOperationException("cmd_debug_observation_failed");' in runner, 'fixed observer exception'
    for name in NAMES[:2]:
        assert wrapper.count(name) == 1 and workflow.count(name) == 1, 'both compile lists'
    assert workflow.count(NAMES[2]) == 1 and NAMES[2] not in wrapper, 'fake test compile isolation'
    assert 'windows-cmd-debugger-observation/*.cs' not in workflow + wrapper, 'no sibling wildcard'
    assert workflow.count('[BrokerDirectLauncher]::RunCmdDebugContractTests()') == 1, 'fake test invocation'
    assert workflow.count('python tests/windows-cmd-debugger-observation/audit.py') == 1, 'audit invocation'


def fixture(result='matched_open_failed'):
    n = dict.fromkeys(NUMERIC, -1)
    n.update(dict.fromkeys(FLAGS | set(COUNTERS), 0))
    n.update(pid=41, main_tid=51, creation_filetime=12345, attach_attempted=1, attach_succeeded=1,
             attach_break_seen=1, entries_ready_before_resume=1, event_count=5, thread_peak=1, module_peak=2,
             entry_hits=1, read_bytes=4096, write_attempts=6, matched_tid=51, pair_complete=1,
             desired_access=0x80120089, object_attributes=0x40, share_access=7, file_attributes=0x80,
             create_disposition=1, open_options=0x60, ntstatus_u32=0xc0000022, exit_event_seen=1,
             exit_event_continued=1, process_signaled=1, terminal_exit_u32=1, elapsed_ms=10)
    i = dict(protocol='own-child-open-v1', result=result, error='none', error_api='none', cleanup='exit_confirmed', open_api='NtCreateFile')
    if result == 'matched_open_succeeded':
        n.update(ntstatus_u32=0, object_identity_matched=1)
    if result == 'observed_pending':
        n.update(ntstatus_u32=0x103, pair_complete=0, abort_terminate_attempted=1, abort_terminate_error=0, active_patches_at_exit=1)
        i['error'] = 'pending_io'
    return {'Numbers': {PREFIX + k: v for k, v in n.items()}, 'Identities': {PREFIX + k: v for k, v in i.items()}}


def encoded(value):
    return json.dumps(value, separators=(',', ':'), ensure_ascii=True).encode()


class ReceiptContracts(unittest.TestCase):
    def test_distinct_operation_facts(self):
        self.assertEqual((len(NUMERIC), len(ENUMS), len(APIS)), (35, 6, 22))
        for result in ('matched_open_failed', 'matched_open_succeeded', 'observed_pending'):
            self.assertEqual(check_receipt(encoded(fixture(result))), result)
        value = fixture('matched_open_succeeded')
        value['Identities'][PREFIX + 'open_api'] = 'NtOpenFile'
        value['Numbers'].update({PREFIX + 'file_attributes': -1, PREFIX + 'create_disposition': -1})
        self.assertEqual(check_receipt(encoded(value)), 'matched_open_succeeded')

    def test_incomplete_and_retained_are_not_paired_evidence(self):
        value = fixture(); n, i = value['Numbers'], value['Identities']
        n[PREFIX + 'pair_complete'] = 0; i[PREFIX + 'error'] = 'context_failed'
        self.assertEqual(check_receipt(encoded(value)), 'incomplete')
        for key in MASKS - {'terminal_exit_u32', 'abort_terminate_error'}:
            n[PREFIX + key] = -1
        n[PREFIX + 'matched_tid'] = -1; n[PREFIX + 'active_patches_at_exit'] = 2
        i.update({PREFIX + 'open_api': 'none', PREFIX + 'result': 'no_match', PREFIX + 'error': 'unsupported_match'})
        self.assertEqual(check_receipt(encoded(value)), 'no_match')
        for key in FLAGS | set(COUNTERS):
            n[PREFIX + key] = 0
        n.update({PREFIX + 'attach_attempted': 1, PREFIX + 'terminal_exit_u32': -1})
        i.update({PREFIX + 'result': 'incomplete', PREFIX + 'error': 'attach_unknown', PREFIX + 'cleanup': 'retained_fatal'})
        self.assertEqual(check_receipt(encoded(value)), 'incomplete')
        i[PREFIX + 'cleanup'] = 'exit_confirmed'
        with self.assertRaises(ValueError):
            check_receipt(encoded(value))

    def test_every_numeric_type_and_range(self):
        for key in NUMERIC:
            for bad in (True, False, None, '123', 1.0, [], {}, -(2**63), 2**64):
                value = fixture(); value['Numbers'][PREFIX + key] = bad
                with self.subTest(key=key, kind=type(bad).__name__), self.assertRaises(ValueError):
                    check_receipt(encoded(value))
        for key, limit in COUNTERS.items():
            value = fixture(); value['Numbers'][PREFIX + key] = limit + 1
            with self.subTest(counter=key), self.assertRaises(ValueError):
                check_receipt(encoded(value))

    def test_every_enum_and_schema_extra_or_missing(self):
        for section, keys in (('Numbers', NUMERIC), ('Identities', ENUMS)):
            for key in keys:
                value = fixture(); del value[section][PREFIX + key]
                with self.subTest(missing=key), self.assertRaises(ValueError):
                    check_receipt(encoded(value))
        for key in ENUMS:
            for bad in ('unknown', 'C:\\secret', 1, True, None, [], {}):
                value = fixture(); value['Identities'][PREFIX + key] = bad
                with self.subTest(enum=key), self.assertRaises(ValueError):
                    check_receipt(encoded(value))
        for section in ('Numbers', 'Identities', None):
            for key in ('path', 'handle', 'pointer', 'exception', 'operations', 'accepted'):
                value = fixture(); destination = value if section is None else value[section]
                destination[PREFIX + key] = 1
                with self.subTest(extra=key, section=section), self.assertRaises(ValueError):
                    check_receipt(encoded(value))

    def test_duplicate_bounded_strict_json(self):
        good = encoded(fixture())
        bad = [b'', b'\xef\xbb\xbf' + good, good + b'\xff', b' ' * 16385, b'[' * 1500 + b']' * 1500,
               good.replace(b'"cmd_debug_pid":41', b'"cmd_debug_pid":41,"cmd_debug_pid":41'),
               good.replace(b'"cmd_debug_pid":41', b'"cmd_debug_pid":NaN'),
               good.replace(b'"cmd_debug_pid":41', b'"cmd_debug_pid":' + b'9' * 100),
               good[:-1] + b',"Numbers":{}}', encoded([fixture(), fixture()])]
        for value in bad:
            with self.subTest(case=bad.index(value)), self.assertRaises(ValueError):
                check_receipt(value)
        for section, entries in fixture().items():
            for key, value in entries.items():
                token = json.dumps(key).encode() + b':' + encoded(value)
                with self.subTest(duplicate=key), self.assertRaises(ValueError):
                    check_receipt(good.replace(token, token + b',' + token, 1))

    def test_pair_cleanup_and_pending_adversaries(self):
        for key, bad in (('pair_complete', 2), ('matched_tid', -1), ('attach_break_seen', 0),
                         ('exit_event_continued', 0), ('process_signaled', 0), ('terminal_exit_u32', 23),
                         ('active_patches_at_exit', 1), ('owned_suspends_at_exit', 1), ('elapsed_ms', 35001),
                         ('object_identity_matched', 1), ('ntstatus_u32', 0x103)):
            value = fixture(); value['Numbers'][PREFIX + key] = bad
            with self.subTest(fact=key), self.assertRaises(ValueError):
                check_receipt(encoded(value))
        for result, key, bad in (('matched_open_succeeded', 'object_identity_matched', 0),
                                 ('observed_pending', 'pair_complete', 1), ('observed_pending', 'object_identity_matched', 1)):
            value = fixture(result); value['Numbers'][PREFIX + key] = bad
            with self.subTest(result=result, fact=key), self.assertRaises(ValueError):
                check_receipt(encoded(value))


class SourceContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = {name: (HERE / name).read_text(encoding='utf-8') for name in NAMES}
        cls.old = {p.name: p.read_text(encoding='utf-8') for p in BROKER.iterdir() if p.suffix in ('.cs', '.ps1')}
        cls.runner = cls.old['PilotRunner.cs']; cls.wrapper = cls.old['run-pilot.ps1']
        cls.workflow = (ROOT / '.github/workflows/windows-lpac-runtime-diagnostic.yml').read_text(encoding='utf-8')

    def inspect(self, sources=None, pins=False):
        inspect_sources(sources or self.sources, self.old, self.runner, self.workflow, self.wrapper, pins)

    def test_exact_source_and_combined_boundary(self):
        self.assertEqual({p.name for p in HERE.iterdir() if p.suffix in ('.cs', '.ps1', '.py')}, set(NAMES) | {'audit.py'})
        self.assertLessEqual(len((HERE / 'audit.py').read_text(encoding='utf-8').splitlines()), 500)
        self.inspect(pins=True)
        sys.path.insert(0, str(BROKER))
        try:
            legacy = runpy.run_path(str(BROKER / 'cmd-observations-audit.py'))
            legacy['coverage'](set(self.old)); legacy['immutable'](self.old)
            case = legacy['CmdObservationSourceAudit']('test_exact_scope')
            result = unittest.TestResult(); case.run(result)
            self.assertTrue(result.wasSuccessful(), 'existing source boundary must also pass')
        finally:
            sys.path.pop(0)

    def test_all_guards_mutated_without_hashes(self):
        self.inspect()
        for name, guards in GUARDS.items():
            for guard in guards:
                changed = dict(self.sources)
                plain = source_text(changed[name]); needle = compact(guard)
                indices = [i for i, char in enumerate(plain) if not char.isspace()]
                start = compact(plain).index(needle)
                changed[name] = plain[:indices[start]] + 'REMOVED_GUARD' + plain[indices[start + len(needle) - 1] + 1:]
                with self.subTest(file=name, guard=guards.index(guard)), self.assertRaises(AssertionError):
                    self.inspect(changed)

    def test_integration_gate_mutations(self):
        changes = (('RequireCmdDebugComparable(cmdDebug,row);', ''),
                   ('if(cmdDebug!=null && !cmdDebug.MayCallOriginalCleanup)', 'if(false)'),
                   ('r.Assigned=true;', 'r.Assigned=false;'),
                   ('"cmd_debug_observation_failed"', 'failure.Message'))
        for before, after in changes:
            with self.subTest(gate=before), self.assertRaises((AssertionError, ValueError)):
                inspect_sources(self.sources, self.old, self.runner.replace(before, after, 1), self.workflow, self.wrapper, False)

    def test_all_imports_forbidden_capabilities_and_exception_leaks(self):
        self.inspect()
        for api in APIS:
            changed = dict(self.sources)
            changed[NAMES[0]] = changed[NAMES[0]].replace('EntryPoint="' + api + '"', 'EntryPoint="Unknown"', 1)
            with self.subTest(api=api), self.assertRaises(AssertionError):
                self.inspect(changed)
        for before, after in (('out output,0,false,2', 'out output,0,false,1'),
                              ('CloseHandle(file.Value)', 'CloseHandle(thread.Value)'),
                              ('UIntPtr count,out UIntPtr actual', 'uint count,out uint actual'),
                              ('UnmanagedType.Bool', 'UnmanagedType.I1')):
            changed = dict(self.sources); changed[NAMES[0]] = changed[NAMES[0]].replace(before, after, 1)
            with self.subTest(abi=before), self.assertRaises(AssertionError):
                self.inspect(changed)
        for code in [name + '();' for name in FORBIDDEN] + ['NtCreateFile();', 'NtOpenFile();', 'ZwWhatever();',
                     'throw new InvalidOperationException(failure.Message);', 'failure.InnerException.ToString();',
                     'CloseHandle(target);', 'api.CloseDuplicate(new CmdDuplicate(target));',
                     'new System.Threading.Thread(()=>{});', 'System.Diagnostics.Process.Start("cmd");']:
            changed = dict(self.sources); changed[NAMES[1]] += '\n' + code
            with self.subTest(capability=code), self.assertRaises(AssertionError):
                self.inspect(changed)


if __name__ == '__main__':
    unittest.main(verbosity=2)
