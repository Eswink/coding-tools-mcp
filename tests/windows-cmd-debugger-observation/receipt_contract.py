"""Pure strict versioned projection contracts; never authenticate full artifacts.

The finite result is an operation fact only. Original case/provenance binding,
root cause, original-gate acceptance and Windows execution remain external.
"""
import json

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
# Prior required fields and enums remain exact; each version has a separate schema.
NUMERIC_V2 = NUMERIC + ['context_mismatch_mask']
CONTEXT_ERRORS = {'context_get_failed', 'context_roundtrip_unavailable', 'context_roundtrip_mismatch'}
ENUMS_V2 = dict(ENUMS, protocol={'own-child-open-v2'}, error=ENUMS['error'] | CONTEXT_ERRORS)
NUMERIC_V3 = NUMERIC_V2 + ['eflags_difference_mask']
ENUMS_V3 = dict(ENUMS_V2, protocol={'own-child-open-v3'})
SCHEMAS = {'own-child-open-v1': (NUMERIC, ENUMS), 'own-child-open-v2': (NUMERIC_V2, ENUMS_V2),
           'own-child-open-v3': (NUMERIC_V3, ENUMS_V3)}


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
    require(type(raw_i) is dict and set(raw_i) == {PREFIX + k for k in ENUMS})
    protocol = raw_i[PREFIX + 'protocol']
    require(type(protocol) is str and protocol in SCHEMAS)
    numeric, enums = SCHEMAS[protocol]
    require(type(raw_n) is dict and set(raw_n) == {PREFIX + k for k in numeric})
    n, i = ({k[len(PREFIX):]: v for k, v in values.items()} for values in (raw_n, raw_i))
    require(all(type(v) is int for v in n.values()))
    require(all(type(i[k]) is str and i[k] in choices for k, choices in enums.items()))
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
    if protocol in ('own-child-open-v2', 'own-child-open-v3'):
        check_context_roundtrip(n, i)
    if protocol == 'own-child-open-v3':
        check_eflags_difference(n)
    if i['result'].startswith('matched_open_') and not n['pair_complete']:
        return 'incomplete'
    return i['result']


def check_context_roundtrip(n, i):
    """Validate only the most recent immediate Set -> Get diagnostic fact."""
    mask = n['context_mismatch_mask']
    require(-1 <= mask <= 0x1fffff)
    if i['error'] in CONTEXT_ERRORS:
        require(n['pair_complete'] == 0)
    if i['error'] == 'context_get_failed':
        require(mask == -1 and i['error_api'] == 'GetThreadContext')
    elif i['error'] == 'context_roundtrip_unavailable':
        require(mask == -1 and i['error_api'] == 'none' and n['native_error'] == 0)
    elif i['error'] == 'context_roundtrip_mismatch':
        require(mask > 0 and i['error_api'] == 'none' and n['native_error'] == 0)
    elif i['error'] == 'context_failed' and i['error_api'] == 'SetThreadContext':
        require(mask == -1 and n['pair_complete'] == 0)
    else:
        require(mask in (-1, 0))
    if i['error'] == 'none':
        require(mask == 0)


def check_eflags_difference(n):
    """Validate paired availability and bit identity, never register values or direction."""
    fields = n['context_mismatch_mask']
    flags = n['eflags_difference_mask']
    require(-1 <= flags <= 0xffffffff)
    require((fields == -1) == (flags == -1))
    if fields >= 0:
        require(((fields & 8) != 0) == (flags != 0))
