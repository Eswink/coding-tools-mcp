"""Synthetic producer-shaped bytes only; never represents a Windows execution."""
from copy import deepcopy
import hashlib
import json

CASES = ('ordinary', 'reference', 'node', 'cmd', 'powershell', 'pwsh',
         'cmd-exit23', 'cmd-batch-exit23', 'cmd-cwd', 'cmd-read-direct')
NATIVE_HASH = '45216b87a18180c292ca6f490e0f7163c914958f07155269eabea9db5d807527'
CMD_HASH = '8' * 64
PARENT = r'C:\Fixture\Local\Temp'
RUN_ROOT = PARENT + r'\ctm-direct-pilot-00000000000000000000000000000001'
EVIDENCE = r'C:\synthetic-evidence\pilot'
RUN_NONCE = 'f' * 32
MINIMAL = b'exit 23\r\n'
OLD_POSITIVES = ('OrdinaryControlPassed', 'ReferenceRoutePassed', 'AllFourOfflineCasesPassed',
                 'CmdSentinelObservationPassed', 'CmdBatchObservationPassed', 'NetworkDenialProven')
# Copied once from the existing managed policy fixture; no runtime source inspection.
_AUTHORITY = (
    'profile_create_hresult=0;stdin_writer_open_error=0;stdin_writer_desired_access=1073741824;stdin_writer_handle_flags=0;'
    'stdin_writer_file_type=1;stdin_writer_attributes=32;stdin_writer_length=0;stdin_writer_links=1;'
    'stdin_writer_close_error=0;stdin_open_error=0;stdin_desired_access=2147483648;stdin_handle_flags=1;'
    'stdin_file_type=1;stdin_attributes=32;stdin_length=0;stdin_links=1;'
    'stdout_open_error=0;stdout_desired_access=1073741824;stdout_handle_flags=1;stdout_file_type=1;'
    'stdout_attributes=32;stdout_length=0;stdout_links=1;stderr_open_error=0;'
    'stderr_desired_access=1073741824;stderr_handle_flags=1;stderr_file_type=1;stderr_attributes=32;'
    'stderr_length=0;stderr_links=1;configured_lpac_request=1;setup_writer_cleanup_completed=1;'
    'stdin_close_error=0;setup_stdin_cleanup_completed=1;stdout_close_error=0;setup_stdout_cleanup_completed=1;'
    'stderr_close_error=0;setup_stderr_cleanup_completed=1;setup_attribute_cleanup_completed=1;setup_heap_0_completed=1;'
    'setup_heap_1_completed=1;setup_heap_2_completed=1;setup_heap_3_completed=1;setup_heap_4_completed=1;'
    'source_token_requested_access=10;source_token_open_error=0;source_type_size_error=122;source_type_required_bytes=4;'
    'source_type_query_error=0;source_type_returned_bytes=4;source_type_value=1;source_type_observation_success=1;'
    'appcontainer_size_error=122;appcontainer_required_bytes=4;appcontainer_query_error=0;appcontainer_returned_bytes=4;'
    'appcontainer_value=1;appcontainer_observation_success=1;lpac_size_call_success=0;lpac_size_error=87;'
    'lpac_required_bytes=0;lpac_sizing_expected_insufficient_buffer=0;lpac_fixed_buffer_bytes=4;lpac_fixed_initial_value=-1515870811;'
    'lpac_fixed_query_success=0;lpac_fixed_query_error=87;lpac_fixed_returned_bytes=0;lpac_fixed_raw_value=-1515870811;'
    'lpac_fixed_value_valid=0;lpac_observation_success=0;capabilities_size_error=122;capabilities_required_bytes=8;'
    'capabilities_query_error=0;capabilities_returned_bytes=8;capabilities_value=0;capabilities_observation_success=1;'
    'appcontainer_sid_size_error=122;appcontainer_sid_required_bytes=48;appcontainer_sid_query_error=0;appcontainer_sid_returned_bytes=48;'
    'appcontainer_sid_sid_bytes=40;appcontainer_sid_sid_offset=8;appcontainer_sid_observation_success=1;integrity_sid_size_error=122;'
    'integrity_sid_required_bytes=28;integrity_sid_query_error=0;integrity_sid_returned_bytes=28;integrity_sid_sid_bytes=12;'
    'integrity_sid_sid_offset=16;integrity_sid_observation_success=1;source_restricted_properties_verified=1;native_queries_observation_only=1;'
    'native_appcontainer_call_completed=1;native_appcontainer_class=29;native_appcontainer_buffer_bytes=4;native_appcontainer_initial_value=-1515870811;'
    'native_appcontainer_initial_returned_bytes=3735928559;native_appcontainer_ntstatus_signed=0;native_appcontainer_ntstatus_unsigned=0;native_appcontainer_returned_bytes=4;'
    'native_appcontainer_raw_value=1;native_appcontainer_buffer_unchanged=0;native_appcontainer_return_length_unchanged=0;native_appcontainer_complete_dword_observed=1;'
    'native_lpac_call_completed=1;native_lpac_class=46;native_lpac_buffer_bytes=4;native_lpac_initial_value=-1515870811;'
    'native_lpac_initial_returned_bytes=3735928559;native_lpac_ntstatus_signed=-1073741821;native_lpac_ntstatus_unsigned=3221225475;native_lpac_returned_bytes=3735928559;'
    'native_lpac_raw_value=-1515870811;native_lpac_buffer_unchanged=1;native_lpac_return_length_unchanged=1;native_lpac_complete_dword_observed=0;'
    'duplicate_valid=1;accesscheck_observer_completed=1;duplicate_ownership_confirmed=1;accesscheck_call_attempts=4;'
    'accesscheck_observer_cleanup_confirmed=1;duplicate_desired_access=8;duplicate_attributes_null=1;duplicate_requested_level=1;'
    'duplicate_requested_type=2;duplicate_api_success=1;duplicate_error=0;duplicate_handle_flags_success=1;'
    'duplicate_handle_flags_error=0;duplicate_handle_flags=0;duplicate_type_valid=1;duplicate_type_size_call_success=0;'
    'duplicate_type_size_error=122;duplicate_type_required_bytes=4;duplicate_type_query_success=1;duplicate_type_query_error=0;'
    'duplicate_type_returned_bytes=4;duplicate_type_value=2;duplicate_type_free_completed=1;duplicate_level_valid=1;'
    'duplicate_level_size_call_success=0;duplicate_level_size_error=122;duplicate_level_required_bytes=4;duplicate_level_query_success=1;'
    'duplicate_level_query_error=0;duplicate_level_returned_bytes=4;duplicate_level_value=1;duplicate_level_free_completed=1;'
    'duplicate_appcontainer_valid=1;duplicate_appcontainer_size_call_success=0;duplicate_appcontainer_size_error=122;duplicate_appcontainer_required_bytes=4;'
    'duplicate_appcontainer_query_success=1;duplicate_appcontainer_query_error=0;duplicate_appcontainer_returned_bytes=4;duplicate_appcontainer_value=1;'
    'duplicate_appcontainer_free_completed=1;duplicate_capabilities_valid=1;duplicate_capabilities_size_call_success=0;duplicate_capabilities_size_error=122;'
    'duplicate_capabilities_required_bytes=8;duplicate_capabilities_query_success=1;duplicate_capabilities_query_error=0;duplicate_capabilities_returned_bytes=8;'
    'duplicate_capabilities_value=0;duplicate_capabilities_free_completed=1;duplicate_appcontainer_sid_valid=1;duplicate_appcontainer_sid_size_call_success=0;'
    'duplicate_appcontainer_sid_size_error=122;duplicate_appcontainer_sid_required_bytes=48;duplicate_appcontainer_sid_query_success=1;duplicate_appcontainer_sid_query_error=0;'
    'duplicate_appcontainer_sid_returned_bytes=48;duplicate_appcontainer_sid_sid_bytes=40;duplicate_appcontainer_sid_sid_offset=8;duplicate_appcontainer_sid_free_completed=1;'
    'duplicate_integrity_sid_valid=1;duplicate_integrity_sid_size_call_success=0;duplicate_integrity_sid_size_error=122;duplicate_integrity_sid_required_bytes=28;'
    'duplicate_integrity_sid_query_success=1;duplicate_integrity_sid_query_error=0;duplicate_integrity_sid_returned_bytes=28;duplicate_integrity_sid_sid_bytes=12;'
    'duplicate_integrity_sid_sid_offset=16;duplicate_integrity_sid_free_completed=1;accesscheck_mixed_descriptor_valid=1;accesscheck_mixed_decision_valid=1;'
    'accesscheck_mixed_api_called=1;accesscheck_mixed_api_success=1;accesscheck_mixed_access_status_raw=1;accesscheck_mixed_granted_access_raw=2;'
    'accesscheck_mixed_privilege_count_raw=0;accesscheck_mixed_privilege_header_valid=1;accesscheck_mixed_error=-1;accesscheck_mixed_error_available=0;'
    'accesscheck_mixed_sd_revision=1;accesscheck_mixed_sd_control=4;accesscheck_mixed_acl_bytes=76;accesscheck_mixed_ace_count=3;'
    'accesscheck_mixed_ace_0_type=0;accesscheck_mixed_ace_0_flags=0;accesscheck_mixed_ace_0_bytes=20;accesscheck_mixed_ace_0_mask=3;'
    'accesscheck_mixed_ace_1_type=0;accesscheck_mixed_ace_1_flags=0;accesscheck_mixed_ace_1_bytes=24;accesscheck_mixed_ace_1_mask=1;'
    'accesscheck_mixed_ace_2_type=0;accesscheck_mixed_ace_2_flags=0;accesscheck_mixed_ace_2_bytes=24;accesscheck_mixed_ace_2_mask=2;'
    'accesscheck_mixed_sacl_present=0;accesscheck_mixed_dacl_present=1;accesscheck_mixed_desired_access_before_mapping=33554432;accesscheck_mixed_desired_access_after_mapping=33554432;'
    'accesscheck_mixed_mapping_read=0;accesscheck_mixed_mapping_write=0;accesscheck_mixed_mapping_execute=0;accesscheck_mixed_mapping_all=0;'
    'accesscheck_mixed_privilege_allocation_bytes=20;accesscheck_mixed_privilege_initial_count=2779096485;accesscheck_mixed_privilege_returned_bytes=20;accesscheck_mixed_privilege_control_raw=0;'
    'accesscheck_mixed_privilege_entry_span_bytes=8;accesscheck_mixed_interpreted_granted_access=2;accesscheck_mixed_memory_7_free_completed=1;accesscheck_mixed_memory_6_free_completed=1;'
    'accesscheck_mixed_memory_5_free_completed=1;accesscheck_mixed_memory_4_free_completed=1;accesscheck_mixed_memory_3_free_completed=1;accesscheck_mixed_memory_2_free_completed=1;'
    'accesscheck_mixed_memory_1_free_completed=1;accesscheck_mixed_memory_0_free_completed=1;accesscheck_mixed_observation_completed=1;accesscheck_aap_descriptor_valid=1;'
    'accesscheck_aap_decision_valid=1;accesscheck_aap_api_called=1;accesscheck_aap_api_success=1;accesscheck_aap_access_status_raw=0;'
    'accesscheck_aap_granted_access_raw=0;accesscheck_aap_privilege_count_raw=0;accesscheck_aap_privilege_header_valid=1;accesscheck_aap_error=5;'
    'accesscheck_aap_error_available=1;accesscheck_aap_sd_revision=1;accesscheck_aap_sd_control=4;accesscheck_aap_acl_bytes=52;'
    'accesscheck_aap_ace_count=2;accesscheck_aap_ace_0_type=0;accesscheck_aap_ace_0_flags=0;accesscheck_aap_ace_0_bytes=20;'
    'accesscheck_aap_ace_0_mask=1;accesscheck_aap_ace_1_type=0;accesscheck_aap_ace_1_flags=0;accesscheck_aap_ace_1_bytes=24;'
    'accesscheck_aap_ace_1_mask=1;accesscheck_aap_sacl_present=0;accesscheck_aap_dacl_present=1;accesscheck_aap_desired_access_before_mapping=33554432;'
    'accesscheck_aap_desired_access_after_mapping=33554432;accesscheck_aap_mapping_read=0;accesscheck_aap_mapping_write=0;accesscheck_aap_mapping_execute=0;'
    'accesscheck_aap_mapping_all=0;accesscheck_aap_privilege_allocation_bytes=20;accesscheck_aap_privilege_initial_count=2779096485;accesscheck_aap_privilege_returned_bytes=20;'
    'accesscheck_aap_privilege_control_raw=0;accesscheck_aap_privilege_entry_span_bytes=8;accesscheck_aap_interpreted_granted_access=0;accesscheck_aap_memory_7_free_completed=1;'
    'accesscheck_aap_memory_6_free_completed=1;accesscheck_aap_memory_5_free_completed=1;accesscheck_aap_memory_3_free_completed=1;accesscheck_aap_memory_2_free_completed=1;'
    'accesscheck_aap_memory_1_free_completed=1;accesscheck_aap_memory_0_free_completed=1;accesscheck_aap_observation_completed=1;accesscheck_arap_descriptor_valid=1;'
    'accesscheck_arap_decision_valid=1;accesscheck_arap_api_called=1;accesscheck_arap_api_success=1;accesscheck_arap_access_status_raw=1;'
    'accesscheck_arap_granted_access_raw=2;accesscheck_arap_privilege_count_raw=0;accesscheck_arap_privilege_header_valid=1;accesscheck_arap_error=-1;'
    'accesscheck_arap_error_available=0;accesscheck_arap_sd_revision=1;accesscheck_arap_sd_control=4;accesscheck_arap_acl_bytes=52;'
    'accesscheck_arap_ace_count=2;accesscheck_arap_ace_0_type=0;accesscheck_arap_ace_0_flags=0;accesscheck_arap_ace_0_bytes=20;'
    'accesscheck_arap_ace_0_mask=2;accesscheck_arap_ace_1_type=0;accesscheck_arap_ace_1_flags=0;accesscheck_arap_ace_1_bytes=24;'
    'accesscheck_arap_ace_1_mask=2;accesscheck_arap_sacl_present=0;accesscheck_arap_dacl_present=1;accesscheck_arap_desired_access_before_mapping=33554432;'
    'accesscheck_arap_desired_access_after_mapping=33554432;accesscheck_arap_mapping_read=0;accesscheck_arap_mapping_write=0;accesscheck_arap_mapping_execute=0;'
    'accesscheck_arap_mapping_all=0;accesscheck_arap_privilege_allocation_bytes=20;accesscheck_arap_privilege_initial_count=2779096485;accesscheck_arap_privilege_returned_bytes=20;'
    'accesscheck_arap_privilege_control_raw=0;accesscheck_arap_privilege_entry_span_bytes=8;accesscheck_arap_interpreted_granted_access=2;accesscheck_arap_memory_7_free_completed=1;'
    'accesscheck_arap_memory_6_free_completed=1;accesscheck_arap_memory_5_free_completed=1;accesscheck_arap_memory_3_free_completed=1;accesscheck_arap_memory_2_free_completed=1;'
    'accesscheck_arap_memory_1_free_completed=1;accesscheck_arap_memory_0_free_completed=1;accesscheck_arap_observation_completed=1;accesscheck_world_descriptor_valid=1;'
    'accesscheck_world_decision_valid=1;accesscheck_world_api_called=1;accesscheck_world_api_success=1;accesscheck_world_access_status_raw=0;'
    'accesscheck_world_granted_access_raw=0;accesscheck_world_privilege_count_raw=0;accesscheck_world_privilege_header_valid=1;accesscheck_world_error=5;'
    'accesscheck_world_error_available=1;accesscheck_world_sd_revision=1;accesscheck_world_sd_control=4;accesscheck_world_acl_bytes=28;'
    'accesscheck_world_ace_count=1;accesscheck_world_ace_0_type=0;accesscheck_world_ace_0_flags=0;accesscheck_world_ace_0_bytes=20;'
    'accesscheck_world_ace_0_mask=3;accesscheck_world_sacl_present=0;accesscheck_world_dacl_present=1;accesscheck_world_desired_access_before_mapping=33554432;'
    'accesscheck_world_desired_access_after_mapping=33554432;accesscheck_world_mapping_read=0;accesscheck_world_mapping_write=0;accesscheck_world_mapping_execute=0;'
    'accesscheck_world_mapping_all=0;accesscheck_world_privilege_allocation_bytes=20;accesscheck_world_privilege_initial_count=2779096485;accesscheck_world_privilege_returned_bytes=20;'
    'accesscheck_world_privilege_control_raw=0;accesscheck_world_privilege_entry_span_bytes=8;accesscheck_world_interpreted_granted_access=0;accesscheck_world_memory_7_free_completed=1;'
    'accesscheck_world_memory_6_free_completed=1;accesscheck_world_memory_5_free_completed=1;accesscheck_world_memory_2_free_completed=1;accesscheck_world_memory_1_free_completed=1;'
    'accesscheck_world_memory_0_free_completed=1;accesscheck_world_observation_completed=1;duplicate_close_error=0;token_close_error=0;'
    'exact_process_stop_confirmed=1;pilot_process_outputs_owned=1;pilot_copied_bytes_verified=1;'
)
_AUTHORITY_IDENTITIES = {
    'fixture_source_sha256': '45216b87a18180c292ca6f490e0f7163c914958f07155269eabea9db5d807527',
    'stdin_writer': '1:1:1',
    'stdin': '1:1:1',
    'stdout': '1:1:2',
    'stderr': '1:1:3',
    'appcontainer_sid': 'S-1-15-2-1-2-3-4-5-6-7',
    'integrity_sid': 'S-1-16-4096',
    'native_appcontainer_ntstatus_hex': '00000000',
    'native_lpac_ntstatus_hex': 'C0000003',
    'duplicate_appcontainer_sid': 'S-1-15-2-1-2-3-4-5-6-7',
    'duplicate_integrity_sid': 'S-1-16-4096',
    'accesscheck_mixed_interpreted_decision': 'allowed',
    'accesscheck_mixed_descriptor_identity': 'absolute-v1;owner=S-1-5-18;group=S-1-5-18;no-SACL;mixed',
    'accesscheck_mixed_owner_sid': 'S-1-5-18',
    'accesscheck_mixed_group_sid': 'S-1-5-18',
    'accesscheck_mixed_ace_0_sid': 'S-1-1-0',
    'accesscheck_mixed_ace_1_sid': 'S-1-15-2-1',
    'accesscheck_mixed_ace_2_sid': 'S-1-15-2-2',
    'accesscheck_aap_interpreted_decision': 'denied',
    'accesscheck_aap_descriptor_identity': 'absolute-v1;owner=S-1-5-18;group=S-1-5-18;no-SACL;aap',
    'accesscheck_aap_owner_sid': 'S-1-5-18',
    'accesscheck_aap_group_sid': 'S-1-5-18',
    'accesscheck_aap_ace_0_sid': 'S-1-1-0',
    'accesscheck_aap_ace_1_sid': 'S-1-15-2-1',
    'accesscheck_arap_interpreted_decision': 'allowed',
    'accesscheck_arap_descriptor_identity': 'absolute-v1;owner=S-1-5-18;group=S-1-5-18;no-SACL;arap',
    'accesscheck_arap_owner_sid': 'S-1-5-18',
    'accesscheck_arap_group_sid': 'S-1-5-18',
    'accesscheck_arap_ace_0_sid': 'S-1-1-0',
    'accesscheck_arap_ace_1_sid': 'S-1-15-2-2',
    'accesscheck_world_interpreted_decision': 'denied',
    'accesscheck_world_descriptor_identity': 'absolute-v1;owner=S-1-5-18;group=S-1-5-18;no-SACL;world',
    'accesscheck_world_owner_sid': 'S-1-5-18',
    'accesscheck_world_group_sid': 'S-1-5-18',
    'accesscheck_world_ace_0_sid': 'S-1-1-0',
}


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def decode(data):
    return json.loads(data.decode('utf-8-sig'))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def reseal(context, members, prefix='evidence\\'):
    """Rebuild trusted synthetic hashes; deliberately exclude manifest's own entry."""
    manifest = 'evidence-sha256.txt'
    lines = [digest(data).upper() + ' ' + prefix + name.replace('/', '\\')
             for name, data in sorted(members.items()) if name != manifest]
    members[manifest] = ('\r\n'.join(lines) + '\r\n').encode('utf-8')
    context['member_sha256'] = {name: digest(data) for name, data in members.items()}
    return context, members


def direct():
    row = dict.fromkeys('Kind Stage Failure Executable CommandLine ExecutableSha256 ProfileSid StdinKind'.split())
    row.update(dict.fromkeys('CreateAttempted Created StdioValidated HostStdioClosed TokenVerified Assigned Resumed Drained CleanupConfirmed'.split(), False))
    row.update(dict.fromkeys('CreateError FailureCode Wait Exit CreationFlags HandleListCount'.split(), 0))
    row.update(Stage='setup', CreateError=-1, Wait=0xffffffff, Exit=0xffffffff, CreationFlags=0x08080404,
               StdinKind='broker_fresh_private_empty_regular_file', Numbers={}, Identities={})
    return row


def case_defaults(kind):
    fields = ('Fatal NoCaseResourcesAllocated AuthorityObserved OrdinarySignatureMatched OrdinaryRejected PreResumeReady '
              'IndividualResourceCleanupConfirmed CaptureIntegrityConfirmed ProfileDeleteApiConfirmed OwnedRootRemoved '
              'CleanupPreconditionsConfirmed CaseMarkerResolved ScopedLifecycleCleanupConfirmed OutsideUnchanged '
              'OutsideWriteAbsent OutsideReadObserved OutsideWriteObserved ScriptEntryObserved OutputOk MutationOk '
              'PositivePassed OfflineReferenceRouteValid NativeFiveAssertionsPassed NetworkDenialProven '
              'CmdExit23Observed CmdBatchExit23Observed CmdCwdObserved CmdReadObserved').split()
    row = dict.fromkeys(fields, False)
    row.update(Case=kind, Policy='accesscheck_signature_v1_ci', Status='pending', Failure=None,
               CanaryClassification='not_measured', ExitHex=None, KnownStartupStatus=None, Launcher=direct())
    return row


def writer(receipt, label, identity='7:0:700'):
    prefix = 'evidence_' + label
    values = dict(open_error=0, desired_access=0x40000000, handle_flags=0, file_type=1,
                  attributes=32, length=0, links=1, close_error=0, close_confirmed=1)
    receipt['Numbers'].update({prefix + '_' + k: v for k, v in values.items()})
    receipt['Identities'][prefix] = identity


def selected_parent(guards=1, closed=True):
    r = direct()
    values = ('security_size_error=122;security_read_error=0;security_free_confirmed=1;broker_owner_query_confirmed=1;'
              'broker_owner_token_desired_access=8;broker_owner_token_open_success=1;broker_owner_token_open_error=0;'
              'broker_owner_token_unowned_output=0;broker_owner_handle_query_success=1;broker_owner_handle_query_error=0;'
              'broker_owner_handle_flags=0;broker_owner_size_success=0;broker_owner_size_error=122;broker_owner_required_bytes=64;'
              'broker_owner_read_success=1;broker_owner_read_error=0;broker_owner_returned_bytes=64;broker_owner_data_free_confirmed=1;'
              'broker_owner_token_close_confirmed=1;broker_owner_token_close_error=0;broker_owned=1;security_control_flags=32772;'
              'dacl_ace_count=2;acl_observed_ace_count=2;acl_observation_completed=1;first_rejected_ace_index=-1')
    r['Numbers'].update({'selected_parent_' + k: int(v) for k, v in (x.split('=') for x in values.split(';'))})
    r['Identities'].update(selected_parent_owner_category='current_broker', selected_parent_first_rejected_reason='none')
    for index, category in enumerate(('current_broker', 'system')):
        label = 'selected_parent_ace_' + str(index)
        r['Numbers'].update({label + '_' + k: v for k, v in dict(native_type=0, flags=3, access_mask=0x1f01ff, qualifier=0, callback=0).items()})
        r['Identities'].update({label + '_type': 'CommonAce', label + '_sid_category': category})
    paths = ['C:\\', r'C:\Fixture', r'C:\Fixture\Local', PARENT]
    for index, path in enumerate(paths):
        label, identity = 'selected_pin_' + str(index), '7:0:' + str(index + 1)
        r['Identities'].update({label: identity, label + '_path': path, label + '_identity': identity, label + '_rechecked_identity': identity})
        r['Numbers'].update({label + '_open_error': 0, label + '_desired_access': 0x20081 if index == 3 else 0xa0,
                             label + '_handle_flags': 0, label + '_attributes': 16})
        if closed:
            r['Numbers'].update({label + '_close_error': 0, label + '_close_confirmed': 1})
    return dict(Policy='localappdata_temp_ci_v1', RequestedPath=PARENT, ResolvedPath=PARENT, Failure=None,
                Acquired=True, FinalScanConfirmed=closed, CloseAttempted=closed, CloseConfirmed=closed,
                PlannedHandles=4, AcquiredHandles=4, VerifiedGuards=guards, Metadata=r)


def environment(cwd, code):
    values = dict.fromkeys(('APPDATA', 'HOME', 'LOCALAPPDATA', 'TEMP', 'TMP', 'USERPROFILE'), cwd)
    values.update(GIT_CONFIG_GLOBAL=cwd + r'\empty.gitconfig', GIT_CONFIG_NOSYSTEM='1', GIT_TERMINAL_PROMPT='0',
                  npm_config_cache=cwd + r'\npm-cache', npm_config_globalconfig=cwd + r'\empty-global.npmrc',
                  npm_config_userconfig=cwd + r'\empty.npmrc', Path=code + r'\runtime;C:\Windows\System32;C:\Windows',
                  POWERSHELL_TELEMETRY_OPTOUT='1', POWERSHELL_UPDATECHECK='Off', PYTHONIOENCODING='utf-8',
                  PYTHONLEGACYWINDOWSSTDIO='0', PYTHONUTF8='1', SystemDrive='C:', SystemRoot=r'C:\Windows', windir=r'C:\Windows')
    return ('\n'.join(k + '=' + values[k] for k in sorted(values, key=str.casefold)) + '\n\n').encode('utf-8')


def raw_read(receipt, label, data, path, identity):
    receipt['Identities'].update({label: identity, label + '_path': path, label + '_sha256': digest(data)})
    values = dict(open_error=0, desired_access=0x80000000, handle_flags=0, advertised_bytes=len(data), bytes=len(data),
                  read_confirmed=1, close_confirmed=1, close_error=0)
    receipt['Numbers'].update({label + '_' + key: value for key, value in values.items()})


def journal(label, root, profile, nonce):
    return ('protocol=owned-pending-journal-v1\nstate=pending\nnonce=' + nonce + '\nlabel=' + label +
            '\nplanned_root=' + root + '\nplanned_profile=' + (profile or 'none') +
            '\npreconditions_record=preconditions-' + nonce + '.json\nresolution=completed filename commits the immutable nonce-bound preconditions record; pending is not completion\n').encode('utf-8')


def allocated_case(kind, index, members, cwd_output=None):
    row, nonce = case_defaults(kind), format(index + 1, '032x')
    r = row['Launcher']
    r['Numbers'] = {k: int(v) for k, v in (x.split('=') for x in _AUTHORITY.split(';') if x)}
    r['Identities'] = dict(_AUTHORITY_IDENTITIES)
    root, base = RUN_ROOT + '\\owned-' + nonce, 'pilot/' + kind + '/'
    cwd, code, evidence = root + '\\workspace', root + '\\code', EVIDENCE + '\\' + kind
    profile = 'ctm.fixture.pilot.' + nonce
    is_cmd = kind == 'cmd' or kind.startswith('cmd-')
    exe = code + ('\\cmd.exe' if is_cmd else '\\fixture.exe' if kind in CASES[:2] else '\\runtime\\' + kind + '.exe')
    command = '"' + exe + '" /d /q /c ' + {'cmd-cwd': 'cd', 'cmd-read-direct': 'type direct.cmd', 'cmd-exit23': 'exit 23'}.get(kind, 'direct.cmd')
    if not is_cmd:
        command = '"' + exe + '" sandbox "' + cwd + '" "' + root + '\\outside" 127.0.0.1:12345'
    if kind == 'node':
        read, write = ((root + '\\outside\\' + leaf).replace('\\', '\\\\') for leaf in ('canary.txt', 'probe-write.txt'))
        script = ("const fs=require('fs');fs.writeFileSync('script-entry.txt','runtime-entered');fs.writeFileSync('mutation.txt','runtime-ok');console.log(fs.readFileSync('mutation.txt','utf8'));" +
                  "let r='unexpected_success',w='unexpected_success';try{fs.readFileSync('" + read + "')}catch(e){r=e.code}" +
                  "try{fs.writeFileSync('" + write + "','runtime-escape')}catch(e){w=e.code}" +
                  "fs.writeFileSync('runtime-canary.txt','read='+r+'\\nwrite='+w+'\\n');if(r!=='EACCES'||w!=='EACCES')process.exitCode=2;")
        command = '"' + exe + '" -e "' + script + '"'
    if kind in ('powershell', 'pwsh'):
        mutation, read, write, receipt = cwd + r'\mutation.txt', root + r'\outside\canary.txt', root + r'\outside\probe-write.txt', cwd + r'\runtime-canary.txt'
        script = ("$ErrorActionPreference='Stop';[IO.File]::WriteAllText('" + cwd + "\\script-entry.txt','runtime-entered');[IO.File]::WriteAllText('" + mutation + "','runtime-ok');" +
                  "[Console]::WriteLine([IO.File]::ReadAllText('" + mutation + "'));$r=0;$w=0;$rt='success';$wt='success';" +
                  "try{[IO.File]::ReadAllText('" + read + "')|Out-Null}catch{$e=$_.Exception.GetBaseException();$r=$e.HResult;$rt=$e.GetType().FullName};" +
                  "try{[IO.File]::WriteAllText('" + write + "','runtime-escape')}catch{$e=$_.Exception.GetBaseException();$w=$e.HResult;$wt=$e.GetType().FullName};" +
                  "[IO.File]::WriteAllText('" + receipt + "',('read_type='+$rt+[char]10+'read_hresult='+$r+[char]10+'write_type='+$wt+[char]10+'write_hresult='+$w+[char]10));" +
                  "if($r -ne -2147024891 -or $w -ne -2147024891 -or $rt -ne 'System.UnauthorizedAccessException' -or $wt -ne 'System.UnauthorizedAccessException'){exit 2}")
        command = '"' + exe + '" -NoLogo -NoProfile -NonInteractive -Command "' + script + '"'
    r.update(Kind='cmd' if is_cmd else kind, Stage='target_observation_terminal', Executable=exe,
             CommandLine=command, ExecutableSha256=CMD_HASH if is_cmd else NATIVE_HASH,
             ProfileSid='S-1-15-2-1-2-3-4-5-6-' + str(index + 10), CreateAttempted=True, Created=True,
             CreateError=0, StdioValidated=True, HostStdioClosed=True, HandleListCount=3, Assigned=kind != 'ordinary',
             Resumed=kind != 'ordinary', Drained=True, Wait=0, Exit=0)
    n, ids = r['Numbers'], r['Identities']
    ids.update(appcontainer_sid=r['ProfileSid'], duplicate_appcontainer_sid=r['ProfileSid'], pilot_case_id=kind,
               pilot_profile_name=profile, pilot_owned_parent_path=RUN_ROOT, pilot_owned_root_path=root,
               pilot_owned_parent_identity='7:0:100', pilot_owned_root_identity='7:0:' + str(index + 200))
    ids['pilot_journal_' + kind + '_nonce'] = nonce
    n.update(delete_profile_hresult=0, pilot_owned_root_removed=1, pilot_scope_creation_confirmed=1,
             pilot_profile_owned=1, pilot_profile_checkpoint_completed=1,
             pilot_root_create_api_confirmed=1, pilot_create_root_error=0, resume_previous_count=1,
             exact_process_stop_confirmed=1, cleanup_final_process_wait=0, terminate_job_error=0,
             job_query_error=0, job_active_processes=0, individual_stop_drain_close_confirmed=1,
             thread_close_error=0, process_close_error=0, job_close_error=0, profile_sid_memory_freed=1, pilot_exit_query_success=1)
    n.update({label + '_close_confirmed': 1 for label in ('stdin_writer', 'stdin_writer_cleanup', 'stdin', 'stdout', 'stderr')})
    for key in ('IndividualResourceCleanupConfirmed', 'CaptureIntegrityConfirmed', 'ProfileDeleteApiConfirmed',
                'OwnedRootRemoved', 'CleanupPreconditionsConfirmed', 'OutsideUnchanged', 'OutsideWriteAbsent'):
        row[key] = True
    row.update(AuthorityObserved=kind != 'ordinary', PreResumeReady=kind != 'ordinary', ExitHex='00000000')
    if kind == 'ordinary':
        row.update(OrdinarySignatureMatched=True, OrdinaryRejected=True, Status='ordinary_signature_matched_and_lpac_rejected', ExitHex=None)
        n['configured_lpac_request'] = 0
        n.pop('setup_heap_2_completed')
        for key, value in dict(mixed_granted_access_raw=3, mixed_interpreted_granted_access=3, aap_access_status_raw=1,
                               aap_granted_access_raw=1, aap_interpreted_granted_access=1, aap_error_available=0, aap_error=-1).items():
            n['accesscheck_' + key] = value
        ids['accesscheck_aap_interpreted_decision'] = 'allowed'
    elif kind == 'reference':
        row.update(OfflineReferenceRouteValid=True, Status='winsock_initialization_failed_10107', ExitHex=None)
        r['Exit'] = 15107
        members[base + 'pre-network.txt'] = b'token=true\ninside=true\noutside_read=true\noutside_write=true\n'
        members[base + 'runtime-checks.txt'] = b''.join((k + '=0\n').encode() for k in
            ('protocol_catalog_open', 'protocol_catalog_close', 'namespace_catalog_open', 'namespace_catalog_close', 'provider_dll_open', 'winsock_dll_open'))
    else:
        row.update(Status='no_script_entry_evidence_inconclusive', CanaryClassification='cmd_errorlevel_is_not_raw_denial_evidence' if kind == 'cmd' else 'missing_or_other_runtime_error')
    members.update({base + 'stdout.txt': b'', base + 'stderr.txt': b'', base + 'canary.txt': b'synthetic-outside-canary',
                    base + 'environment.txt': environment(cwd, code)})
    copies = [(NATIVE_HASH, 'fixture.exe')] + ([(CMD_HASH, 'cmd.exe')] if is_cmd else
        [(NATIVE_HASH, 'runtime\\' + kind + '.exe')] if kind not in CASES[:2] else [])
    members[base + 'copy-source-destination-sha256.txt'] = ''.join(h + ' ' + h + ' ' + p + '\r\n' for h, p in copies).encode()
    members[base + 'private-code-sha256.txt'] = ''.join(h + ' ' + p + '\r\n' for h, p in copies).encode()
    if kind in ('cmd-exit23', 'cmd-batch-exit23'):
        row.update(Status='cmd_exit23_not_observed' if kind == 'cmd-exit23' else 'cmd_minimal_batch_exit23_not_observed',
                   CanaryClassification='sentinel_did_not_attempt_runtime_canary' if kind == 'cmd-exit23' else 'minimal_batch_did_not_attempt_runtime_canary')
    if kind.startswith('cmd-'):
        ids['pilot_original_cmd_sha256'] = CMD_HASH
        n['pilot_cmd_same_binary_verified'] = 1
    if kind in CASES[8:]:
        expected = (cwd + '\r\n').encode('ascii') if kind == 'cmd-cwd' else MINIMAL
        output = expected if cwd_output is None or kind != 'cmd-cwd' else cwd_output
        members[base + 'stdout.txt'] = output
        ids.update(pilot_cmd_observation_protocol='cmd-cwd-read-raw-v1', pilot_cmd_observation_case=kind,
                   pilot_cmd_observation_command=command, pilot_cmd_observation_cwd=cwd,
                   pilot_cmd_observation_stage='after_target_stop_and_job_drain', pilot_cmd_observation_expected_sha256=digest(expected))
        n.update(pilot_cmd_observation_raw_complete=1, pilot_cmd_observation_expected_supported=1,
                 pilot_cmd_observation_expected_bytes=len(expected), pilot_cmd_observation_stdout_matches=int(output == expected), pilot_cmd_observation_stderr_empty=1)
        for stream in ('stdout', 'stderr'):
            data = members[base + stream + '.txt']
            raw_read(r, 'pilot_cmd_' + stream + '_source', data, cwd + '\\' + stream + '.txt', ids[stream])
            raw_read(r, 'pilot_cmd_' + stream + '_evidence', data, evidence + '\\' + stream + '.txt', '7:0:' + str(400 + index * 2 + (stream == 'stderr')))
        row.update(CmdCwdObserved=kind == 'cmd-cwd' and output == expected, CmdReadObserved=kind == 'cmd-read-direct',
                   CanaryClassification=('cwd' if kind == 'cmd-cwd' else 'read') + '_observation_did_not_attempt_runtime_canary',
                   Status=('cmd_cwd' if kind == 'cmd-cwd' else 'cmd_read_direct') + ('_raw_observed' if output == expected else '_raw_not_observed'))
    if kind in ('cmd', 'cmd-batch-exit23', 'cmd-read-direct'):
        payload = MINIMAL
        if kind == 'cmd':
            payload = ('@echo off\r\necho runtime-entered>script-entry.txt\r\necho runtime-ok>mutation.txt\r\ntype mutation.txt\r\n' +
                       'type \"' + root + '\\outside\\canary.txt\" >outside-read.txt\r\necho read_errorlevel=%errorlevel%>runtime-canary.txt\r\n' +
                       'echo runtime-escape>\"' + root + '\\outside\\probe-write.txt\"\r\necho write_errorlevel=%errorlevel%>>runtime-canary.txt\r\nexit /b 0\r\n').encode('ascii')
        members[base + 'generated-direct.cmd.bin'] = payload
        ids['pilot_cmd_batch_stage'] = 'before_profile_and_process_creation'
        n.update(pilot_cmd_minimal_payload_verified=int(kind != 'cmd'), pilot_cmd_batch_capture_confirmed=1)
        raw_read(r, 'pilot_cmd_batch_source', payload, cwd + '\\direct.cmd', '7:0:' + str(500 + index))
        raw_read(r, 'pilot_cmd_batch_readback', payload, evidence + '\\generated-direct.cmd.bin', '7:0:' + str(600 + index))
        n.update(pilot_cmd_batch_destination_bytes=len(payload), pilot_cmd_batch_destination_write_confirmed=1,
                 pilot_cmd_batch_destination_close_confirmed=1, pilot_cmd_batch_destination_close_error=0)
        ids.update(pilot_cmd_batch_destination=ids['pilot_cmd_batch_readback'], pilot_cmd_batch_destination_path=evidence + '\\generated-direct.cmd.bin', pilot_cmd_batch_destination_sha256=digest(payload))
    for name in ('stdout.txt', 'stderr.txt', 'script-entry.txt', 'mutation.txt', 'runtime-canary.txt', 'outside-read.txt',
                 'pre-network.txt', 'runtime-checks.txt', 'receipt.txt', 'canary.txt', 'probe-write.txt',
                 'copy-source-destination-sha256.txt', 'private-code-sha256.txt', 'environment.txt'):
        label = 'capture_' + name
        n[label + '_open_error'] = 0 if base + name in members else 2
        if base + name in members:
            size = len(members[base + name])
            n.update({label + '_close_error': 0, label + '_advertised_bytes': size, label + '_copied_bytes': size})
            ids[label] = ids[name[:-4]] if name in ('stdout.txt', 'stderr.txt') else '7:0:' + str(800 + len(ids))
    for label in ('ownership_root', 'ownership_profile', 'ownership_process'):
        writer(r, label, '7:0:' + str(1300 + index * 3 + ('ownership_root', 'ownership_profile', 'ownership_process').index(label)))
    members[base + 'preconditions-' + nonce + '.json'] = encode(row)
    writer(r, 'journal_preconditions_' + nonce, '7:0:' + str(900 + index))
    n.update(journal_binding_verify_close_error=0, journal_binding_verify_close_confirmed=1)
    row.update(CaseMarkerResolved=True, ScopedLifecycleCleanupConfirmed=True)
    members[base + 'completed-' + nonce + '.txt'] = journal(kind, root, profile, nonce)
    members[base + 'case.json'] = encode(row)
    writer(r, 'case_receipt', '7:0:' + str(1000 + index))
    return row


def ownership_snapshots(row, members):
    """Model checkpoints before profile setup, after profile, and after CreateProcess."""
    source, base = row['Launcher'], 'pilot/' + row['Case'] + '/'
    snapshot = case_defaults(row['Case'])
    r = snapshot['Launcher']
    r['Kind'] = source['Kind']
    for key, value in source['Identities'].items():
        if key.startswith(('pilot_owned_', 'pilot_profile_', 'pilot_journal_')) or key == 'pilot_case_id':
            r['Identities'][key] = value
    for key in ('pilot_scope_creation_confirmed', 'pilot_root_create_api_confirmed', 'pilot_create_root_error'):
        r['Numbers'][key] = source['Numbers'][key]
    members[base + 'ownership-root.json'] = encode(snapshot)
    writer(r, 'ownership_root', source['Identities']['evidence_ownership_root'])
    for key in ('Executable', 'CommandLine', 'ExecutableSha256', 'ProfileSid'):
        r[key] = source[key]
    r['Numbers'].update(pilot_copied_bytes_verified=1, profile_create_hresult=0,
                        pilot_profile_owned=1, pilot_profile_checkpoint_completed=0)
    r['Identities']['fixture_source_sha256'] = NATIVE_HASH
    members[base + 'ownership-profile.json'] = encode(snapshot)
    writer(r, 'ownership_profile', source['Identities']['evidence_ownership_profile'])
    r['Numbers']['pilot_profile_checkpoint_completed'] = 1
    r.update(Stage='create_suspended', CreateAttempted=True, Created=True, CreateError=0,
             StdioValidated=True, HostStdioClosed=True, HandleListCount=3)
    for key, value in source['Numbers'].items():
        if key.startswith(('stdin', 'stdout', 'stderr', 'setup_')) or key == 'configured_lpac_request':
            r['Numbers'][key] = value
    r['Identities'].update({key: source['Identities'][key] for key in ('stdin_writer', 'stdin', 'stdout', 'stderr')})
    r['Numbers']['pilot_process_outputs_owned'] = 1
    members[base + 'ownership-process.json'] = encode(snapshot)


def completed_fixture(cwd_output=None, optional_missing=()):
    """Return a complete synthetic (trusted_context, raw_members) pair."""
    context = dict(repository='Eswink/coding-tools-mcp', workflow_path='.github/workflows/windows-lpac-runtime-diagnostic.yml',
                   artifact_name='windows-lpac-runtime-diagnostic', commit='1' * 40, tree='2' * 40, run_head_sha='1' * 40,
                   run_id=1001, job_id=1002, artifact_id=1003, run_attempt=1, artifact_size=123456,
                   artifact_sha256='3' * 64, artifact_crc_verified=True, manifest_verified=True,
                   member_set_complete=True, required_setup_and_capture_verified=True, job_terminal_state='failure')
    inventory = [dict(runtime=k, ready=k not in optional_missing, reason='synthetic unavailable' if k in optional_missing else None,
                      sha256=CMD_HASH if k == 'cmd' else NATIVE_HASH) for k in ('python', 'node', 'git', 'powershell', 'pwsh', 'npm', 'cmd')]
    for item in inventory:
        item.update(file_version='1.0.0.0', product_version='1.0.0.0', reparse_points=[])
        if item['runtime'] not in ('cmd', 'npm'):
            item.update(source_executable='C:\\synthetic-runtime\\' + item['runtime'] + '.exe', source_root=r'C:\synthetic-runtime', relative_executable=item['runtime'] + '.exe')
    members = {'source.txt': (context['commit'] + '\r\n' + context['tree'] + '\r\n').encode(),
               'fixture-binaries-sha256.txt': (NATIVE_HASH + ' windows_sandbox_fixture.exe\r\n' + '9' * 64 + ' windows_runtime_fixture.exe\r\n').encode(),
               'runtime/runtime-inventory.json': encode(inventory), 'runtime/runtime-copy-sha256.txt': (CMD_HASH + ' cmd.exe\r\n' + ''.join(NATIVE_HASH + ' ' + k + '\\' + k + '.exe\r\n' for k in ('node', 'powershell', 'pwsh'))).encode(),
               'runtime/runtime-matrix.json': encode([]), 'selected-parent-preflight.json': encode(selected_parent())}
    original_cases = ['python-budget', 'python-workspace', 'node-workspace', 'npm-cmd', 'git-local',
                      'cmd-workspace', 'powershell-workspace', 'pwsh-workspace']
    nested_names = original_cases + [name + suffix for suffix in ('-private-eof', '-private-eof-no-window') for name in original_cases[2:]]
    members['runtime/runtime-matrix.json'] = encode([dict(case=name, offline_passed=False, parent_fixture_canaries_passed=True,
        runtime=None, lifecycle=None, native_exit=None, native_failure='Win32Exception', numeric_diagnosis=['exit=15107'],
        native_classification='winsock_initialization_failed_10107', native_assertion_violation=False, network_denial_proven=False) for name in nested_names])
    for name, outside in [('control-receipt.txt', 'true'), ('mode-2-ordinary-appcontainer-receipt.txt', 'false')]:
        members['foundation/' + name] = ('token=true\ninside=true\noutside_read=' + outside + '\noutside_write=true\nnetwork=true\n').encode()
    members['pilot/preparation-premise.json'] = encode(dict(selected_parent_policy='localappdata_temp_ci_v1', selected_parent=PARENT,
        runner_temp_control=r'C:\runner-temp', policy='accesscheck_signature_v1_ci', foundation_valid=True, network_denial_proven=False,
        runtime_inventory=inventory, ready=[k for k in ('node', 'cmd', 'powershell', 'pwsh') if k not in optional_missing], native_fixture_sha256=NATIVE_HASH))
    run = dict.fromkeys(OLD_POSITIVES + ('AllCaseCleanupConfirmed', 'RunRootRemoved', 'CmdCwdRawObservationMatched', 'CmdReadRawObservationMatched'), False)
    run.update(Policy='accesscheck_signature_v1_ci', Phase='collecting', Failure=None,
               CleanupScope='ten required case outcomes, their actually created profile/private scopes and disposable run root and selected-parent metadata handles only; listener, preparation evidence, outer workflow capture/upload are separate outcomes',
               CompletionJournal='completed-' + RUN_NONCE + '.txt', JournalProtocol='completed filename is the final resolution receipt; preconditions alone are not completion',
               RequiredCaseCount=10, OriginalPilotRequiredCaseCount=6, AdditiveSentinelRequiredCaseCount=1, AdditiveBatchRequiredCaseCount=1,
               AdditiveCwdRequiredCaseCount=1, AdditiveReadRequiredCaseCount=1, OriginalNestedRequiredRows=20,
               NotCovered=['python', 'npm.cmd', 'git', 'nested_child_support', 'ConPTY', 'production_integration'],
               InitialSelectedParent=selected_parent(), SelectedParent=selected_parent(1, False), Broker=direct(), Cases=[])
    broker = run['Broker']
    broker['Identities'].update(same_run_native_fixture_sha256=NATIVE_HASH, pilot_journal_run_nonce=RUN_NONCE,
                                pilot_owned_root_identity='7:0:100', pilot_owned_parent_identity='7:0:4',
                                pilot_owned_root_path=RUN_ROOT, pilot_owned_parent_path=PARENT)
    broker['Numbers'].update(pilot_scope_creation_confirmed=1)
    for index, kind in enumerate(CASES):
        if kind in optional_missing or (kind.startswith('cmd-') and 'cmd' in optional_missing):
            row = case_defaults(kind)
            row.update(Status='preparation_failed', NoCaseResourcesAllocated=True)
        else:
            row = allocated_case(kind, index, members, cwd_output)
            ownership_snapshots(row, members)
        run['Cases'].append(row)
        run['CmdCwdRawObservationMatched'] = any(r['CmdCwdObserved'] for r in run['Cases'])
        run['CmdReadRawObservationMatched'] = any(r['CmdReadObserved'] for r in run['Cases'])
        run['SelectedParent']['VerifiedGuards'] += 4 if kind != 'ordinary' else 3
        members['pilot/matrix-' + str(index + 1).zfill(2) + '.json'] = encode(run)
        writer(broker, 'matrix_' + str(index + 1), '7:0:' + str(1100 + index))
        if kind == 'ordinary':
            run['OrdinaryControlPassed'] = True
        if kind == 'reference':
            run['ReferenceRoutePassed'] = True
    run.update(Phase='completion_preconditions_persisted', AllCaseCleanupConfirmed=True, RunRootRemoved=True)
    run['SelectedParent'] = selected_parent(42)
    broker['Numbers']['pilot_owned_root_removed'] = 1
    members['pilot/pilot-result.json'] = encode(run)
    writer(broker, 'final_result', '7:0:1200')
    members['pilot/preconditions-' + RUN_NONCE + '.json'] = encode(run)
    members['pilot/completed-' + RUN_NONCE + '.txt'] = journal('run', RUN_ROOT, None, RUN_NONCE)
    return reseal(context, members)
