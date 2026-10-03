"""Pure receipt facts for narrow cmd observations, not a Windows token verifier."""
import hashlib
import re

CASES = ('ordinary', 'reference', 'node', 'cmd', 'powershell', 'pwsh',
         'cmd-exit23', 'cmd-batch-exit23', 'cmd-cwd', 'cmd-read-direct')
POLICY = 'accesscheck_signature_v1_ci'
RAW_PROTOCOL = 'cmd-cwd-read-raw-v1'
MINIMAL = b'exit 23\r\n'
SHA = re.compile(r'[0-9a-f]{64}\Z')
NONCE = re.compile(r'[0-9a-f]{32}\Z')
DIRECT_STRINGS = 'Kind Stage Failure Executable CommandLine ExecutableSha256 ProfileSid StdinKind'.split()
DIRECT_BOOLS = 'CreateAttempted Created StdioValidated HostStdioClosed TokenVerified Assigned Resumed Drained CleanupConfirmed'.split()
DIRECT_INTS = 'CreateError FailureCode Wait Exit CreationFlags HandleListCount'.split()
CASE_STRINGS = 'Case Policy Status Failure CanaryClassification ExitHex KnownStartupStatus'.split()
CASE_BOOLS = ('Fatal NoCaseResourcesAllocated AuthorityObserved OrdinarySignatureMatched OrdinaryRejected PreResumeReady '
              'IndividualResourceCleanupConfirmed CaptureIntegrityConfirmed ProfileDeleteApiConfirmed OwnedRootRemoved '
              'CleanupPreconditionsConfirmed CaseMarkerResolved ScopedLifecycleCleanupConfirmed OutsideUnchanged '
              'OutsideWriteAbsent OutsideReadObserved OutsideWriteObserved ScriptEntryObserved OutputOk MutationOk '
              'PositivePassed OfflineReferenceRouteValid NativeFiveAssertionsPassed NetworkDenialProven '
              'CmdExit23Observed CmdBatchExit23Observed CmdCwdObserved CmdReadObserved').split()
UNRELATED = ('PositivePassed OfflineReferenceRouteValid NativeFiveAssertionsPassed NetworkDenialProven '
             'ScriptEntryObserved OutputOk MutationOk CmdExit23Observed CmdBatchExit23Observed').split()
CAPTURES = ('stdout.txt', 'stderr.txt', 'script-entry.txt', 'mutation.txt', 'runtime-canary.txt',
            'outside-read.txt', 'pre-network.txt', 'runtime-checks.txt', 'receipt.txt', 'canary.txt',
            'probe-write.txt', 'copy-source-destination-sha256.txt', 'private-code-sha256.txt', 'environment.txt')


class ArtifactError(ValueError):
    def __init__(self, code, member='', case='', status='inconsistent'):
        super().__init__(code)
        self.code, self.member, self.case, self.status = code, member, case, status


def require(condition, code='identity', member='', case='', status='inconsistent'):
    if not condition:
        raise ArtifactError(code, member, case, status)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def exact(values, expected, code='identity'):
    for key, value in expected.items():
        require(key in values, 'missing', status='incomplete')
        require(type(values[key]) is type(value) and values[key] == value, code)


def file_identity(value):
    require(type(value) is str and re.fullmatch(r'[0-9]{1,10}:[0-9]{1,10}:[0-9]{1,10}', value) is not None)
    parts = [int(x) for x in value.split(':')]
    require(all(x <= 0xffffffff for x in parts) and parts[1:] != [0, 0])
    require(value == ':'.join(str(x) for x in parts))


def owned_path(value):
    require(type(value) is str and 4 <= len(value) <= 32700)
    require(re.match(r'^[A-Za-z]:\\', value) is not None and value[-1] != '\\')
    require(not any(c in value[3:] for c in '/:"\'\0\r\n%!&|<>^?*'))
    for part in value[3:].split('\\'):
        require(part not in ('', '.', '..') and not part.endswith(('.', ' ')))
        require(len(part) <= 255 and all(ord(c) >= 32 and not 0xd800 <= ord(c) <= 0xdfff for c in part))
        require(not re.fullmatch(r'CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|(?:COM|LPT)[1-9¹²³]', part.split('.')[0].upper()))
    return value


def direct_schema(row):
    require(type(row) is dict, 'parse')
    require(set(row) == set(DIRECT_STRINGS + DIRECT_BOOLS + DIRECT_INTS + ['Numbers', 'Identities']), 'parse')
    for key in DIRECT_STRINGS:
        require(row[key] is None or type(row[key]) is str, 'parse')
    for key in DIRECT_BOOLS:
        require(type(row[key]) is bool, 'parse')
    for key in DIRECT_INTS:
        require(type(row[key]) is int and -(2**31) <= row[key] <= 0xffffffff, 'parse')
    require(type(row['Numbers']) is dict and type(row['Identities']) is dict, 'parse')
    require(all(type(v) is int and -(2**63) <= v < 2**63 for v in row['Numbers'].values()), 'parse')
    require(all(type(v) is str for v in row['Identities'].values()), 'parse')


def case_schema(row):
    require(type(row) is dict and set(row) == set(CASE_STRINGS + CASE_BOOLS + ['Launcher']), 'parse')
    for key in CASE_STRINGS:
        require(row[key] is None or type(row[key]) is str, 'parse')
    for key in CASE_BOOLS:
        require(type(row[key]) is bool, 'parse')
    direct_schema(row['Launcher'])
    require(row['Case'] in CASES and row['Policy'] == POLICY)


def default_direct():
    result = dict.fromkeys(DIRECT_STRINGS)
    result.update(dict.fromkeys(DIRECT_BOOLS, False))
    result.update(dict.fromkeys(DIRECT_INTS, 0))
    result.update(Stage='setup', CreateError=-1, Wait=0xffffffff, Exit=0xffffffff,
                  CreationFlags=0x08080404, StdinKind='broker_fresh_private_empty_regular_file', Numbers={}, Identities={})
    return result


def no_allocation(row, inventory, members):
    case_schema(row)
    kind = row['Case']
    runtime = 'cmd' if kind.startswith('cmd-') else kind
    require(kind not in ('ordinary', 'reference') and inventory.get(runtime) is False, 'stage')
    exact(row, {'Status': 'preparation_failed', 'Failure': None, 'CanaryClassification': 'not_measured',
                'ExitHex': None, 'KnownStartupStatus': None})
    exact(row, {key: key == 'NoCaseResourcesAllocated' for key in CASE_BOOLS})
    require(row['Launcher'] == default_direct(), 'stage')
    require(not any(name.startswith('pilot/' + kind + '/') for name in members), 'stage')


def writer(receipt, label):
    n, i = receipt['Numbers'], receipt['Identities']
    prefix = 'evidence_' + label
    exact(n, {prefix + '_open_error': 0, prefix + '_desired_access': 0x40000000,
              prefix + '_handle_flags': 0, prefix + '_file_type': 1, prefix + '_length': 0,
              prefix + '_links': 1, prefix + '_close_error': 0, prefix + '_close_confirmed': 1}, 'commit')
    require(prefix + '_attributes' in n and n[prefix + '_attributes'] & 0x410 == 0, 'commit')
    file_identity(i.get(prefix))
    require(prefix + '_close_exception' not in i, 'commit')


def without_writer(receipt, labels):
    """Remove only the precise OpenPrivate/PilotCloseHandle fields for named writes."""
    result = dict(receipt, Numbers=dict(receipt['Numbers']), Identities=dict(receipt['Identities']))
    suffixes = ('open_error', 'desired_access', 'handle_flags', 'file_type', 'attributes',
                'length', 'links', 'close_error', 'close_confirmed')
    for label in labels:
        prefix = 'evidence_' + label
        for suffix in suffixes:
            result['Numbers'].pop(prefix + '_' + suffix, None)
        result['Identities'].pop(prefix, None)
    return result


def stdio_facts(r):
    exact(r, {'StdioValidated': True, 'HostStdioClosed': True, 'HandleListCount': 3,
              'StdinKind': 'broker_fresh_private_empty_regular_file'})
    n, i = r['Numbers'], r['Identities']
    identities = [i.get(label) for label in ('stdin', 'stdout', 'stderr')]
    for identity in identities:
        file_identity(identity)
    require(len(set(identities)) == 3 and i.get('stdin_writer') == identities[0])
    for label in ('stdin_writer', 'stdin', 'stdout', 'stderr'):
        exact(n, {label + '_open_error': 0, label + '_close_error': 0, label + '_file_type': 1,
                  label + '_length': 0, label + '_links': 1,
                  label + '_handle_flags': 0 if label == 'stdin_writer' else 1,
                  label + '_desired_access': 0x80000000 if label == 'stdin' else 0x40000000})
        require(label + '_attributes' in n and n[label + '_attributes'] & 0x410 == 0)
    for label in ('writer', 'stdin', 'stdout', 'stderr', 'attribute'):
        exact(n, {'setup_' + label + '_cleanup_completed': 1})
    for index in (0, 1, 3, 4):
        exact(n, {'setup_heap_' + str(index) + '_completed': 1})
    require(n.get('configured_lpac_request') in (0, 1))
    if n['configured_lpac_request'] == 1:
        exact(n, {'setup_heap_2_completed': 1})
    else:
        require('setup_heap_2_completed' not in n)


def authority_facts(row, ordinary=False):
    """Check published measured truth; never query, duplicate, or adopt a token."""
    r, n, i = row['Launcher'], row['Launcher']['Numbers'], row['Launcher']['Identities']
    exact(r, {'CreateAttempted': True, 'Created': True, 'CreateError': 0, 'TokenVerified': False,
              'CreationFlags': 0x08080404, 'CleanupConfirmed': False})
    require(type(r['ProfileSid']) is str and re.fullmatch(r'S-1-15-2-(?:[0-9]+-)*[0-9]+', r['ProfileSid']))
    exact(i, {'appcontainer_sid': r['ProfileSid'], 'duplicate_appcontainer_sid': r['ProfileSid'],
              'integrity_sid': 'S-1-16-4096', 'duplicate_integrity_sid': 'S-1-16-4096',
              'native_appcontainer_ntstatus_hex': '00000000', 'native_lpac_ntstatus_hex': 'C0000003'})
    exact(n, {'profile_create_hresult': 0, 'pilot_process_outputs_owned': 1, 'pilot_copied_bytes_verified': 1,
              'source_token_requested_access': 10, 'source_token_open_error': 0, 'source_restricted_properties_verified': 1,
              'source_type_value': 1, 'appcontainer_value': 1, 'capabilities_value': 0, 'token_close_error': 0,
              'duplicate_ownership_confirmed': 1, 'duplicate_valid': 1, 'duplicate_api_success': 1, 'duplicate_error': 0,
              'duplicate_desired_access': 8, 'duplicate_attributes_null': 1, 'duplicate_requested_level': 1,
              'duplicate_requested_type': 2, 'duplicate_handle_flags_success': 1, 'duplicate_handle_flags_error': 0,
              'duplicate_handle_flags': 0, 'duplicate_type_value': 2, 'duplicate_level_value': 1,
              'duplicate_appcontainer_value': 1, 'duplicate_capabilities_value': 0, 'duplicate_close_error': 0,
              'accesscheck_observer_completed': 1, 'accesscheck_observer_cleanup_confirmed': 1, 'accesscheck_call_attempts': 4})
    exact(n, dict(zip(('lpac_size_call_success lpac_size_error lpac_required_bytes lpac_sizing_expected_insufficient_buffer '
                       'lpac_fixed_buffer_bytes lpac_fixed_initial_value lpac_fixed_query_success lpac_fixed_query_error '
                       'lpac_fixed_returned_bytes lpac_fixed_raw_value lpac_fixed_value_valid lpac_observation_success '
                       'native_queries_observation_only').split(), (0, 87, 0, 0, 4, -1515870811, 0, 87, 0, -1515870811, 0, 0, 1))))
    native_keys = ('call_completed class buffer_bytes initial_value initial_returned_bytes ntstatus_signed ntstatus_unsigned '
                   'returned_bytes raw_value buffer_unchanged return_length_unchanged complete_dword_observed').split()
    for label, values in [('native_appcontainer', (1, 29, 4, -1515870811, 3735928559, 0, 0, 4, 1, 0, 0, 1)),
                          ('native_lpac', (1, 46, 4, -1515870811, 3735928559, -1073741821, 3221225475,
                                           3735928559, -1515870811, 1, 1, 0))]:
        exact(n, {label + '_' + key: value for key, value in zip(native_keys, values)})
    for label in ('source_type', 'appcontainer', 'capabilities', 'appcontainer_sid', 'integrity_sid',
                  'duplicate_type', 'duplicate_level', 'duplicate_appcontainer', 'duplicate_capabilities',
                  'duplicate_appcontainer_sid', 'duplicate_integrity_sid'):
        exact(n, {label + '_size_error': 122, label + '_query_error': 0})
        require(4 <= n.get(label + '_returned_bytes', 0) <= n.get(label + '_required_bytes', 0) <= 65536)
        if label.startswith('duplicate_'):
            exact(n, {label + '_valid': 1, label + '_size_call_success': 0,
                      label + '_query_success': 1, label + '_free_completed': 1})
        else:
            exact(n, {label + '_observation_success': 1})
        if label in ('source_type', 'appcontainer', 'duplicate_type', 'duplicate_level', 'duplicate_appcontainer'):
            exact(n, {label + '_required_bytes': 4, label + '_returned_bytes': 4})
        if label.endswith('_sid'):
            returned, offset, length = (n.get(label + suffix, -1) for suffix in ('_returned_bytes', '_sid_offset', '_sid_bytes'))
            require((16 if 'integrity' in label else 8) <= offset <= returned and
                    8 <= length <= 68 and (length - 8) % 4 == 0 and length <= returned - offset)
            require('integrity' not in label or length == 12)
    allowed_access = {'accesscheck_observer_completed', 'accesscheck_observer_cleanup_confirmed', 'accesscheck_call_attempts'}
    for label, mask in [('mixed', 3 if ordinary else 2), ('aap', 1 if ordinary else 0), ('arap', 2), ('world', 0)]:
        prefix = 'accesscheck_' + label
        exact(n, {prefix + '_descriptor_valid': 1, prefix + '_decision_valid': 1,
                  prefix + '_api_called': 1, prefix + '_api_success': 1,
                  prefix + '_access_status_raw': int(mask != 0), prefix + '_granted_access_raw': mask,
                  prefix + '_interpreted_granted_access': mask, prefix + '_observation_completed': 1,
                  prefix + '_error_available': int(mask == 0), prefix + '_error': 5 if mask == 0 else -1})
        exact(i, {prefix + '_interpreted_decision': 'allowed' if mask else 'denied',
                  prefix + '_descriptor_identity': 'absolute-v1;owner=S-1-5-18;group=S-1-5-18;no-SACL;' + label,
                  prefix + '_owner_sid': 'S-1-5-18', prefix + '_group_sid': 'S-1-5-18'})
        fixed = dict(privilege_count_raw=0, privilege_header_valid=1, privilege_allocation_bytes=20,
                     privilege_initial_count=2779096485, privilege_entry_span_bytes=8, sd_revision=1,
                     sd_control=4, sacl_present=0, dacl_present=1, desired_access_before_mapping=33554432,
                     desired_access_after_mapping=33554432, mapping_read=0, mapping_write=0, mapping_execute=0, mapping_all=0)
        exact(n, {prefix + '_' + key: value for key, value in fixed.items()})
        require(8 <= n.get(prefix + '_privilege_returned_bytes', -1) <= 20)
        sids = ['S-1-1-0'] + ([] if label == 'world' else ['S-1-15-2-' + ('2' if label == 'arap' else '1')])
        if label == 'mixed':
            sids.append('S-1-15-2-2')
        masks = {'mixed': [3, 1, 2], 'aap': [1, 1], 'arap': [2, 2], 'world': [3]}[label]
        exact(n, {prefix + '_ace_count': len(sids), prefix + '_acl_bytes': 8 + 20 + 24 * (len(sids) - 1)})
        for index, sid in enumerate(sids):
            ace = prefix + '_ace_' + str(index)
            exact(n, {ace + '_type': 0, ace + '_flags': 0, ace + '_bytes': 20 if index == 0 else 24, ace + '_mask': masks[index]})
            exact(i, {ace + '_sid': sid})
            allowed_access.update(ace + '_' + field for field in ('type', 'flags', 'bytes', 'mask', 'sid'))
        for slot in [0, 1, 5, 6, 7] + list(range(2, 2 + len(sids))):
            exact(n, {prefix + '_memory_' + str(slot) + '_free_completed': 1})
            allowed_access.add(prefix + '_memory_' + str(slot) + '_free_completed')
        fields = ('descriptor_valid decision_valid api_called api_success access_status_raw granted_access_raw '
                  'interpreted_granted_access observation_completed error_available error interpreted_decision '
                  'descriptor_identity owner_sid group_sid privilege_returned_bytes privilege_control_raw ace_count acl_bytes').split()
        allowed_access.update(prefix + '_' + field for field in fields + list(fixed))
    for key in set(n) | set(i):
        require(not key.startswith('accesscheck_') or key in allowed_access)
    for key in i:
        require(not key.endswith('_observation_failure'))
        if key.endswith('_exception'):
            require(not key.startswith(('source_', 'appcontainer', 'capabilities', 'integrity_', 'duplicate_',
                                        'accesscheck_', 'lpac_', 'native_', 'setup_', 'pilot_source_close')))
    stdio_facts(r)
    if ordinary:
        exact(row, {'OrdinarySignatureMatched': True, 'OrdinaryRejected': True, 'AuthorityObserved': False, 'PreResumeReady': False})
        exact(r, {'Assigned': False, 'Resumed': False})
    else:
        exact(row, {'AuthorityObserved': True, 'PreResumeReady': True})
        exact(r, {'Assigned': True, 'Resumed': True})


def capture_files(row, members):
    r, case = row['Launcher'], row['Case']
    n, i = r['Numbers'], r['Identities']
    required = {'stdout.txt', 'stderr.txt', 'canary.txt', 'copy-source-destination-sha256.txt',
                'private-code-sha256.txt', 'environment.txt'}
    for name in CAPTURES:
        prefix, member = 'capture_' + name, 'pilot/' + case + '/' + name
        require(prefix + '_open_error' in n, 'missing', member, case, 'incomplete')
        if n[prefix + '_open_error'] == 2:
            require(name not in required and member not in members, 'provenance', member, case)
            continue
        exact(n, {prefix + '_open_error': 0, prefix + '_close_error': 0}, 'provenance')
        require(member in members, 'missing', member, case, 'incomplete')
        size = len(members[member])
        require(size <= 1048576, 'parse', member, case, 'incomplete')
        exact(n, {prefix + '_advertised_bytes': size, prefix + '_copied_bytes': size}, 'provenance')
        file_identity(i.get(prefix))
        if name in ('stdout.txt', 'stderr.txt'):
            require(i[prefix] == i[name[:-4]], 'identity', member, case)
    require(members['pilot/' + case + '/canary.txt'] == b'synthetic-outside-canary', 'raw_mismatch')
    require('pilot/' + case + '/probe-write.txt' not in members, 'raw_mismatch')


def raw_read(n, i, label, data, path, identity=None):
    exact(i, {label + '_path': path, label + '_sha256': digest(data)}, 'raw_mismatch')
    file_identity(i.get(label))
    if identity is not None:
        require(i[label] == identity)
    exact(n, {label + '_open_error': 0, label + '_desired_access': 0x80000000,
              label + '_handle_flags': 0, label + '_advertised_bytes': len(data), label + '_bytes': len(data),
              label + '_read_confirmed': 1, label + '_close_confirmed': 1, label + '_close_error': 0}, 'raw_mismatch')
    require(label + '_close_exception' not in i, 'raw_mismatch')


def raw_observation(row, members, original_hash):
    """No late Fatal/cleanup/run-success gate: raw facts survive later failure."""
    case_schema(row)
    case, r = row['Case'], row['Launcher']
    require(case in CASES[8:] and not row['NoCaseResourcesAllocated'])
    n, i = r['Numbers'], r['Identities']
    cwd = owned_path(i.get('pilot_cmd_observation_cwd'))
    root = cwd.rsplit('\\', 1)[0]
    require(cwd == root + '\\workspace' and re.fullmatch(r'owned-[0-9a-f]{32}', root.rsplit('\\', 1)[-1]))
    exe = root + '\\code\\cmd.exe'
    command = '"' + exe + '" /d /q /c ' + ('cd' if case == 'cmd-cwd' else 'type direct.cmd')
    require(type(original_hash) is str and SHA.fullmatch(original_hash))
    exact(r, {'Kind': 'cmd', 'Stage': 'target_observation_terminal', 'Executable': exe, 'CommandLine': command, 'ExecutableSha256': original_hash})
    exact(i, {'pilot_case_id': case, 'pilot_cmd_observation_case': case, 'pilot_cmd_observation_protocol': RAW_PROTOCOL,
              'pilot_cmd_observation_command': command, 'pilot_original_cmd_sha256': original_hash,
              'pilot_cmd_observation_stage': 'after_target_stop_and_job_drain'})
    exact(n, {'pilot_cmd_same_binary_verified': 1, 'resume_previous_count': 1,
              'exact_process_stop_confirmed': 1, 'cleanup_final_process_wait': 0, 'terminate_job_error': 0,
              'job_query_error': 0, 'job_active_processes': 0, 'individual_stop_drain_close_confirmed': 1,
              'thread_close_error': 0, 'process_close_error': 0, 'job_close_error': 0,
              'profile_sid_memory_freed': 1, 'pilot_cmd_observation_raw_complete': 1})
    exact(row, {'OutsideUnchanged': True, 'OutsideWriteAbsent': True, 'OutsideReadObserved': False,
                'OutsideWriteObserved': False, 'IndividualResourceCleanupConfirmed': True, 'CaptureIntegrityConfirmed': True})
    exact(row, dict.fromkeys(UNRELATED, False))
    exact(r, {'Drained': True})
    require(r['Wait'] in (0, 258), 'stage')
    if r['Wait'] == 0:
        exact(n, {'pilot_exit_query_success': 1}, 'stage')
    else:
        require('pilot_exit_query_success' not in n and r['Exit'] == 0xffffffff, 'stage')
    authority_facts(row)
    capture_files(row, members)
    base = 'pilot/' + case + '/'
    stdout, stderr = members[base + 'stdout.txt'], members[base + 'stderr.txt']
    evidence = i.get('pilot_cmd_stdout_evidence_path', '').rsplit('\\', 1)[0]
    owned_path(evidence)
    require(evidence.endswith('\\pilot\\' + case))
    for stream, data in [('stdout', stdout), ('stderr', stderr)]:
        require(len(data) <= 1048576, 'parse', base + stream + '.txt', case, 'incomplete')
        raw_read(n, i, 'pilot_cmd_' + stream + '_source', data, cwd + '\\' + stream + '.txt', i.get(stream))
        raw_read(n, i, 'pilot_cmd_' + stream + '_evidence', data, evidence + '\\' + stream + '.txt')
    require(len({i['pilot_cmd_' + stream + '_' + part] for stream in ('stdout', 'stderr') for part in ('source', 'evidence')}) == 4)
    numeric = {'expected_supported', 'expected_bytes', 'raw_complete', 'stdout_matches', 'stderr_empty'}
    identities = {'protocol', 'case', 'command', 'cwd', 'stage', 'expected_sha256'}
    require(all(not key.startswith('pilot_cmd_observation_') or key[len('pilot_cmd_observation_'):] in numeric for key in n))
    require(all(not key.startswith('pilot_cmd_observation_') or key[len('pilot_cmd_observation_'):] in identities for key in i))
    labels = ['pilot_cmd_' + stream + '_' + part for stream in ('stdout', 'stderr') for part in ('source', 'evidence')]
    for values, suffixes in [(n, ('_open_error', '_desired_access', '_handle_flags', '_advertised_bytes', '_bytes',
                                 '_read_confirmed', '_close_confirmed', '_close_error')), (i, ('', '_path', '_sha256'))]:
        allowed = {label + suffix for label in labels for suffix in suffixes}
        require(all(not key.startswith(('pilot_cmd_stdout_', 'pilot_cmd_stderr_')) or key in allowed for key in values))
    expected = MINIMAL if case == 'cmd-read-direct' else (cwd + '\r\n').encode('ascii') if cwd.isascii() else None
    exact(n, {'pilot_cmd_observation_expected_supported': int(expected is not None),
              'pilot_cmd_observation_expected_bytes': -1 if expected is None else len(expected),
              'pilot_cmd_observation_stdout_matches': int(expected is not None and stdout == expected),
              'pilot_cmd_observation_stderr_empty': int(not stderr)}, 'raw_mismatch')
    if expected is None:
        require('pilot_cmd_observation_expected_sha256' not in i, 'unsupported_encoding')
    else:
        exact(i, {'pilot_cmd_observation_expected_sha256': digest(expected)}, 'raw_mismatch')
    if case == 'cmd-read-direct':
        require(members.get(base + 'generated-direct.cmd.bin') == MINIMAL, 'raw_mismatch')
        exact(i, {'pilot_cmd_batch_stage': 'before_profile_and_process_creation'})
        exact(n, {'pilot_cmd_minimal_payload_verified': 1, 'pilot_cmd_batch_capture_confirmed': 1})
        for part in ('source', 'readback'):
            path = cwd + '\\direct.cmd' if part == 'source' else evidence + '\\generated-direct.cmd.bin'
            raw_read(n, i, 'pilot_cmd_batch_' + part, MINIMAL, path)
        exact(n, {'pilot_cmd_batch_destination_bytes': 9, 'pilot_cmd_batch_destination_write_confirmed': 1,
                  'pilot_cmd_batch_destination_close_confirmed': 1, 'pilot_cmd_batch_destination_close_error': 0})
        exact(i, {'pilot_cmd_batch_destination_path': evidence + '\\generated-direct.cmd.bin',
                  'pilot_cmd_batch_destination_sha256': digest(MINIMAL),
                  'pilot_cmd_batch_destination': i['pilot_cmd_batch_readback']})
        require(i['pilot_cmd_batch_source'] != i['pilot_cmd_batch_destination'])
    return expected is not None and stdout == expected and not stderr and r['Wait'] == 0 and r['Exit'] == 0, expected is None


def case_provenance(row, members, native, runtime_hashes, inventory):
    """Bind every allocated private copy and the unchanged environment template."""
    r, case = row['Launcher'], row['Case']
    base, i = 'pilot/' + case + '/', r['Identities']
    root = owned_path(i.get('pilot_owned_root_path'))
    cwd, code = root + '\\workspace', root + '\\code'
    def hashes(name, copied=False):
        data = members[base + name].decode('utf-8', errors='strict')
        require(not data.startswith('\ufeff'), 'parse', base + name)
        result = {}
        for line in data.splitlines():
            pattern = r'([0-9a-f]{64}) ([0-9a-f]{64}) (.+)' if copied else r'([0-9a-f]{64}) (.+)'
            match = re.fullmatch(pattern, line)
            require(match is not None, 'provenance', base + name)
            hash_value, relative = match[1], match[3] if copied else match[2]
            require(not copied or match[1] == match[2], 'provenance', base + name)
            require(relative.casefold() not in {p.casefold() for p in result}, 'provenance', base + name)
            owned_path(code + '\\' + relative)
            result[relative] = hash_value
        return result
    copies = hashes('copy-source-destination-sha256.txt', True)
    require(copies == hashes('private-code-sha256.txt'), 'provenance', base)
    require(copies.get('fixture.exe') == native and i.get('fixture_source_sha256') == native, 'provenance', base)
    runtime = 'cmd' if case.startswith('cmd') else case
    for relative, hash_value in copies.items():
        if relative == 'fixture.exe':
            continue
        payload_name = 'cmd.exe' if runtime == 'cmd' and relative == 'cmd.exe' else runtime + '\\' + relative[len('runtime\\'):]
        require(runtime not in ('ordinary', 'reference') and (relative == 'cmd.exe' or relative.startswith('runtime\\')), 'provenance', base)
        require(runtime_hashes.get(payload_name) == hash_value, 'provenance', base)
    if runtime in ('ordinary', 'reference', 'cmd'):
        require(set(copies) == ({'fixture.exe', 'cmd.exe'} if runtime == 'cmd' else {'fixture.exe'}), 'provenance', base)
    require(type(r['Executable']) is str and r['Executable'].startswith(code + '\\') and copies.get(r['Executable'][len(code) + 1:]) == r['ExecutableSha256'], 'provenance', base)
    if runtime not in ('ordinary', 'reference'):
        runtime_hash = inventory[runtime].get('sha256')
        require(type(runtime_hash) is str and inventory[runtime]['ready'] is True and runtime_hash.lower() == r['ExecutableSha256'], 'provenance', base)
    environment = members[base + 'environment.txt'].decode('utf-8', errors='strict')
    pairs = [line.split('=', 1) for line in environment.splitlines() if line]
    require(all(len(pair) == 2 for pair in pairs) and len(dict(pairs)) == len(pairs), 'provenance', base + 'environment.txt')
    values = dict(pairs)
    windows = owned_path(values.get('SystemRoot'))
    expected = dict.fromkeys(['APPDATA', 'HOME', 'LOCALAPPDATA', 'TEMP', 'TMP', 'USERPROFILE'], cwd)
    expected.update(GIT_CONFIG_GLOBAL=cwd + '\\empty.gitconfig', GIT_CONFIG_NOSYSTEM='1', GIT_TERMINAL_PROMPT='0',
                    npm_config_cache=cwd + '\\npm-cache', npm_config_globalconfig=cwd + '\\empty-global.npmrc',
                    npm_config_userconfig=cwd + '\\empty.npmrc', Path=code + '\\runtime;' + windows + '\\System32;' + windows,
                    POWERSHELL_TELEMETRY_OPTOUT='1', POWERSHELL_UPDATECHECK='Off', PYTHONIOENCODING='utf-8',
                    PYTHONLEGACYWINDOWSSTDIO='0', PYTHONUTF8='1', SystemDrive=windows[:2], SystemRoot=windows, windir=windows)
    require(environment == ''.join(k + '=' + expected[k] + '\n' for k in sorted(expected, key=str.casefold)) + '\n', 'provenance', base + 'environment.txt')
    return windows


def selected_acl(receipt):
    n, i, p = receipt['Numbers'], receipt['Identities'], 'selected_parent_'
    facts = dict(security_size_error=122, security_read_error=0, broker_owner_token_desired_access=8,
                 broker_owner_token_open_success=1, broker_owner_token_open_error=0,
                 broker_owner_token_unowned_output=0, broker_owner_handle_query_success=1,
                 broker_owner_handle_query_error=0, broker_owner_handle_flags=0, broker_owner_size_success=0,
                 broker_owner_size_error=122, broker_owner_read_success=1, broker_owner_read_error=0)
    exact(n, {p + k: v for k, v in facts.items()}, 'cleanup')
    require(24 <= n.get(p + 'broker_owner_returned_bytes', 0) <= n.get(p + 'broker_owner_required_bytes', 0) <= 65536, 'cleanup')
    count = n.get(p + 'dacl_ace_count', -2)
    require(0 <= count <= 16384 and n.get(p + 'acl_observed_ace_count') == count, 'cleanup')
    require(0 <= n.get(p + 'security_control_flags', -1) <= 65535 and n[p + 'security_control_flags'] & 4, 'cleanup')
    require(i.get(p + 'owner_category') in ('current_broker', 'system', 'administrators'), 'cleanup')
    exact(i, {p + 'first_rejected_reason': 'none'}, 'cleanup')
    exact(n, {p + 'first_rejected_ace_index': -1}, 'cleanup')
    for index in range(count):
        ace = p + 'ace_' + str(index)
        shape = i.get(ace + '_type')
        require(shape == 'CommonAce', 'cleanup')
        require(0 <= n.get(ace + '_native_type', -1) <= 255 and 0 <= n.get(ace + '_flags', -1) <= 255, 'cleanup')
        if shape != 'CustomAce':
            require(0 <= n.get(ace + '_access_mask', -1) <= 0xffffffff, 'cleanup')
            require(i.get(ace + '_sid_category') in ('current_broker', 'system', 'administrators', 'creator_owner', 'other'), 'cleanup')
        if shape == 'CommonAce':
            require(n.get(ace + '_qualifier') in (0, 1) and n.get(ace + '_callback') == 0, 'cleanup')
            require(n[ace + '_native_type'] == n[ace + '_qualifier'], 'cleanup')
            if n[ace + '_qualifier'] == 0:
                mask = n[ace + '_access_mask']
                require(mask & ~0xf01f01ff == 0, 'cleanup')
                require(mask & 0x500d0156 == 0 or i[ace + '_sid_category'] in ('current_broker', 'system', 'administrators'), 'cleanup')
