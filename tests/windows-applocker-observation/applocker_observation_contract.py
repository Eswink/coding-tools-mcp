"""Pure, bounded correlation of supplied AppLocker observation bytes.

This module acquires nothing. The caller authenticates the whole artifact; raw
JSON cannot grant provenance, pilot completion, or an accepted security result.
"""
import datetime
import json
import math
import re
import xml.etree.ElementTree as ET

from cmd_observation_artifact import evaluate_cmd_observation_artifact, run_schema
from cmd_observation_contracts import (
    ArtifactError, MINIMAL, NONCE, POLICY, SHA, case_schema, digest, exact,
    file_identity, owned_path, raw_read, require, without_writer, writer,
)

CASE = 'cmd-relative-batch-exit23'
CHANNEL = 'Microsoft-Windows-AppLocker/MSI and Script'
PROVIDER = 'Microsoft-Windows-AppLocker'
FIXED_MEMBERS = {
    'invocation': 'applocker-observation/invocation.json',
    'ownership': 'pilot/' + CASE + '/ownership-process.json',
    'case': 'pilot/' + CASE + '/case.json',
    'run': 'pilot/pilot-result.json',
    'payload': 'pilot/' + CASE + '/generated-direct.cmd.bin',
}
RAW_MEMBER = 'applocker-observation/observation.json'
RUN_MAX_BYTES = 2097152
BRACKET_KEYS = {'Protocol', 'StartedUtc', 'EndedUtc', 'ElapsedMilliseconds'}
HASH_KEYS = ('OwnershipSha256', 'CaseSha256', 'RunSha256', 'InvocationSha256', 'QuerySha256')
IDENTITY_KEYS = {'TargetPid', 'TargetPath', *HASH_KEYS[:3]}
RAW_KEYS = {'Protocol', 'Case', 'Status', 'Reason', 'Decision', *HASH_KEYS}
RAW_REASONS = {
    'setup_unavailable', 'bracket_invalid', 'identity_unavailable',
    'identity_inconsistent', 'request_invalid', 'channel_unavailable',
    'access_denied', 'query_unsupported', 'read_failed', 'read_timeout',
    'record_invalid', 'no_matching_record', 'multiple_records',
    'close_uncertain', 'evidence_write_failed',
}
ASCII_LOWER = str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')


def strict_json(data, max_bytes=1048576, expected_keys=None):
    """Parse strict UTF8 JSON with bounded containers and unambiguous keys."""
    require(type(data) is bytes and type(max_bytes) is int
            and 0 < max_bytes <= RUN_MAX_BYTES and 0 < len(data) <= max_bytes, 'parse')
    require(not data.startswith(b'\xef\xbb\xbf'), 'parse')

    def pairs(items):
        result, seen = {}, set()
        for key, value in items:
            folded = key.translate(ASCII_LOWER)
            require(folded not in seen, 'parse')
            seen.add(folded)
            result[key] = value
        return result

    try:
        value = json.loads(data.decode('utf-8', errors='strict'), object_pairs_hook=pairs,
                           parse_constant=lambda _: require(False, 'parse'))
    except (ValueError, UnicodeError, RecursionError):
        raise ArtifactError('parse') from None
    pending = [(value, 0)]
    while pending:
        current, depth = pending.pop()
        require(depth <= 32, 'parse')
        if type(current) is dict:
            pending.extend((key, depth + 1) for key in current)
            pending.extend((item, depth + 1) for item in current.values())
        elif type(current) is list:
            require(len(current) <= 4096, 'parse')
            pending.extend((item, depth + 1) for item in current)
        elif type(current) is float:
            require(math.isfinite(current), 'parse')
        elif type(current) is str:
            require(not any(0xd800 <= ord(c) <= 0xdfff for c in current), 'parse')
    if expected_keys is not None:
        require(type(value) is dict and set(value) == set(expected_keys), 'parse')
    return value


def utc_ticks(value):
    """Canonical UTC ticks since year 1, preserving the seventh decimal digit."""
    require(type(value) is str and re.fullmatch(
        r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{7}Z', value), 'parse')
    try:
        stamp = datetime.datetime(int(value[:4]), int(value[5:7]), int(value[8:10]),
                                  int(value[11:13]), int(value[14:16]), int(value[17:19]))
    except ValueError:
        raise ArtifactError('parse') from None
    seconds = ((stamp.toordinal() - 1) * 86400 + stamp.hour * 3600
               + stamp.minute * 60 + stamp.second)
    return seconds * 10000000 + int(value[20:27])


def validate_bracket(data):
    """Validate the invocation interval; it is not a process lifetime window."""
    bracket = strict_json(data, 4096, BRACKET_KEYS) if type(data) is bytes else data
    require(type(bracket) is dict and set(bracket) == BRACKET_KEYS, 'parse')
    exact(bracket, {'Protocol': 'applocker-invocation-bracket-v1'})
    start, end = utc_ticks(bracket['StartedUtc']), utc_ticks(bracket['EndedUtc'])
    elapsed = bracket['ElapsedMilliseconds']
    require(type(elapsed) is int and 0 <= elapsed <= 900000, 'parse')
    require(0 <= end - start <= 900000 * 10000, 'identity')
    require(abs(end - start - elapsed * 10000) <= 2000 * 10000, 'identity')
    return dict(bracket)


def target_identity(ownership_bytes, case_bytes, run_bytes, payload_bytes):
    """Bind only the fixed slot10 owned process, command, path and payload."""
    ownership = strict_json(ownership_bytes)
    terminal = strict_json(case_bytes)
    run = strict_json(run_bytes, RUN_MAX_BYTES)
    case_schema(ownership)
    case_schema(terminal)
    run_schema(run)
    require(len(run['Cases']) == 11, 'identity')
    final = run['Cases'][10]
    require(type(payload_bytes) is bytes and payload_bytes == MINIMAL, 'identity')
    for row in (ownership, terminal, final):
        exact(row, {'Case': CASE, 'Policy': POLICY, 'NoCaseResourcesAllocated': False})
    created, ended = ownership['Launcher'], terminal['Launcher']
    exact(created, {'Kind': 'cmd', 'Stage': 'create_suspended', 'CreateAttempted': True,
                    'Created': True, 'CreateError': 0, 'StdioValidated': True,
                    'HostStdioClosed': True, 'Assigned': False, 'Resumed': False,
                    'Failure': None})
    exact(ended, {'Kind': 'cmd', 'Stage': 'target_observation_terminal',
                  'CreateAttempted': True, 'Created': True, 'CreateError': 0,
                  'StdioValidated': True, 'HostStdioClosed': True,
                  'Assigned': True, 'Resumed': True})
    require(type(created['ProfileSid']) is str
            and re.fullmatch(r'S-1-15-2-(?:[0-9]+-)*[0-9]+', created['ProfileSid']), 'identity')
    numbers, identities = created['Numbers'], created['Identities']
    exact(numbers, {'pilot_process_outputs_owned': 1})
    pid = numbers.get('pilot_created_pid')
    require(type(pid) is int and 0 < pid <= 2147483647, 'identity')
    parent = owned_path(identities.get('pilot_owned_parent_path'))
    root = owned_path(identities.get('pilot_owned_root_path'))
    require(re.fullmatch(r'ctm-direct-pilot-[0-9a-f]{32}', parent.rsplit('\\', 1)[-1]))
    require(root.rsplit('\\', 1)[0] == parent
            and re.fullmatch(r'owned-[0-9a-f]{32}', root.rsplit('\\', 1)[-1]))
    cwd, executable = root + '\\workspace', root + '\\code\\cmd.exe'
    path, command = cwd + '\\direct.cmd', '"' + executable + '" /d /q /c .\\direct.cmd'
    original_hash = run['Cases'][3]['Launcher']['ExecutableSha256']
    require(type(original_hash) is str and SHA.fullmatch(original_hash), 'identity')
    nonce = identities.get('pilot_journal_' + CASE + '_nonce')
    require(type(nonce) is str and NONCE.fullmatch(nonce), 'identity')
    profile = identities.get('pilot_profile_name')
    require(type(profile) is str and re.fullmatch(r'ctm\.fixture\.pilot\.[0-9a-f]{32}', profile))
    exact(identities, {'pilot_case_id': CASE, 'pilot_cmd_observation_case': CASE,
                      'pilot_cmd_observation_protocol': 'cmd-relative-batch-raw-v1',
                      'pilot_cmd_observation_command': command, 'pilot_cmd_observation_cwd': cwd,
                      'pilot_cmd_batch_stage': 'before_profile_and_process_creation'})
    for key in ('pilot_owned_parent_identity', 'pilot_owned_root_identity'):
        file_identity(identities.get(key))
    require(identities['pilot_owned_parent_identity'] != identities['pilot_owned_root_identity'])
    require(identities['pilot_owned_parent_identity'].split(':')[0]
            == identities['pilot_owned_root_identity'].split(':')[0])
    exact(run['Broker']['Identities'], {'pilot_owned_root_path': parent,
                                      'pilot_owned_root_identity': identities['pilot_owned_parent_identity']})
    destination = owned_path(identities.get('pilot_cmd_batch_destination_path'))
    require(destination.endswith('\\pilot\\' + CASE + '\\generated-direct.cmd.bin'))
    raw_read(numbers, identities, 'pilot_cmd_batch_source', MINIMAL, path)
    raw_read(numbers, identities, 'pilot_cmd_batch_readback', MINIMAL, destination)
    exact(numbers, {'pilot_cmd_minimal_payload_verified': 1, 'pilot_cmd_batch_capture_confirmed': 1,
                    'pilot_cmd_batch_destination_open_error': 0,
                    'pilot_cmd_batch_destination_desired_access': 0x40000000,
                    'pilot_cmd_batch_destination_handle_flags': 0,
                    'pilot_cmd_batch_destination_file_type': 1, 'pilot_cmd_batch_destination_links': 1,
                    'pilot_cmd_batch_destination_length': 0, 'pilot_cmd_batch_destination_bytes': 9,
                    'pilot_cmd_batch_destination_write_confirmed': 1,
                    'pilot_cmd_batch_destination_close_confirmed': 1,
                    'pilot_cmd_batch_destination_close_error': 0})
    require('pilot_cmd_batch_destination_attributes' in numbers
            and numbers['pilot_cmd_batch_destination_attributes'] & 0x410 == 0)
    exact(identities, {'pilot_cmd_batch_destination_sha256': digest(MINIMAL),
                      'pilot_cmd_batch_destination': identities['pilot_cmd_batch_readback']})
    require(identities['pilot_cmd_batch_source'] != identities['pilot_cmd_batch_destination'])
    require('pilot_cmd_batch_destination_close_exception' not in identities)
    for receipt in (created, ended, final['Launcher']):
        exact(receipt, {'Executable': executable, 'CommandLine': command,
                        'ExecutableSha256': original_hash, 'ProfileSid': created['ProfileSid']})
        exact(receipt['Identities'], identities)
        exact(receipt['Numbers'], numbers)
    exact(ended['Identities'], {'pilot_original_cmd_sha256': original_hash,
                               'pilot_cmd_observation_stage': 'after_target_stop_and_job_drain'})
    # The final writer's receipt is the sole change after case.json was persisted.
    writer(final['Launcher'], 'case_receipt')
    projected = dict(final, Launcher=without_writer(final['Launcher'], ['case_receipt']))
    require(projected == terminal, 'identity')
    return {'TargetPid': pid, 'TargetPath': path, 'OwnershipSha256': digest(ownership_bytes),
            'CaseSha256': digest(case_bytes), 'RunSha256': digest(run_bytes)}


def build_query(identity, bracket):
    """Build one fixed service-side selector; no alternate literals or aliases."""
    require(type(identity) is dict and set(identity) == IDENTITY_KEYS, 'parse')
    pid, path = identity['TargetPid'], owned_path(identity['TargetPath'])
    require(type(pid) is int and 0 < pid <= 2147483647, 'identity')
    require(not any(ord(char) in (0xfffe, 0xffff) for char in path), 'parse')
    require(re.search(r'\\ctm-direct-pilot-[0-9a-f]{32}\\owned-[0-9a-f]{32}'
                      r'\\workspace\\direct\.cmd\Z', path), 'identity')
    for key in HASH_KEYS[:3]:
        require(type(identity[key]) is str and SHA.fullmatch(identity[key]), 'parse')
    # owned_path rejects quote/metacharacter/invalid Unicode input without rewrite.
    bracket = validate_bracket(bracket)
    selector = ("*[System[Provider[@Name='Microsoft-Windows-AppLocker'] and "
                "(EventID=8005 or EventID=8006 or EventID=8007) and "
                "TimeCreated[@SystemTime>='" + bracket['StartedUtc'] + "' and @SystemTime<='"
                + bracket['EndedUtc'] + "']] and UserData[RuleAndFileData[PolicyName='SCRIPT' "
                "and TargetProcessId=" + str(pid) + " and FilePath='" + path + "']]]")
    query_list = ET.Element('QueryList')
    query = ET.SubElement(query_list, 'Query', {'Id': '0', 'Path': CHANNEL})
    ET.SubElement(query, 'Select', {'Path': CHANNEL}).text = selector
    result = ET.tostring(query_list, encoding='unicode', short_empty_elements=False)
    require(len(result.encode('utf-8')) <= 128 * 1024, 'parse')
    return result


def validate_raw_receipt(raw_bytes, identity, bracket, invocation_bytes):
    """Recompute every correlation hash; producer output cannot grant trust."""
    raw = strict_json(raw_bytes, 16384, RAW_KEYS)
    exact(raw, {'Protocol': 'applocker-script-observation-raw-v1', 'Case': CASE})
    require(type(raw['Status']) is str and raw['Status'] in ('raw_matched', 'inconclusive'), 'parse')
    require(bracket == validate_bracket(invocation_bytes), 'identity')
    query = build_query(identity, bracket)
    expected = {key: identity[key] for key in HASH_KEYS[:3]}
    expected.update(InvocationSha256=digest(invocation_bytes), QuerySha256=digest(query.encode('utf-8')))
    for key in HASH_KEYS:
        value = raw[key]
        require(value is None or type(value) is str and SHA.fullmatch(value), 'parse')
        require(value is None or value == expected[key], 'identity')
    if raw['Status'] == 'inconclusive':
        require(type(raw['Reason']) is str and raw['Reason'] in RAW_REASONS
                and raw['Decision'] is None, 'parse')
        return raw
    require(raw['Reason'] is None and all(raw[key] is not None for key in HASH_KEYS), 'parse')
    decision = raw['Decision']
    require(type(decision) is dict and set(decision) == {'EventId', 'Utc'}, 'parse')
    require(type(decision['EventId']) is int and decision['EventId'] in (8005, 8006, 8007), 'parse')
    ticks = utc_ticks(decision['Utc'])
    require(utc_ticks(bracket['StartedUtc']) <= ticks <= utc_ticks(bracket['EndedUtc']), 'identity')
    return raw


def evaluate_applocker_observation(trusted_context, members):
    """Reviewed PID/path/time correlation only, after unchanged full completion."""
    result = {'status': 'inconclusive', 'reason': 'run_completion_unvalidated', 'decision': None}
    try:
        original = evaluate_cmd_observation_artifact(trusted_context, members)
        if original.get('RunCompletionValidated') is not True:
            return result
        result['reason'] = 'bracket_invalid'
        invocation = members[FIXED_MEMBERS['invocation']]
        bracket = validate_bracket(invocation)
        result['reason'] = 'evidence_write_failed'
        sibling_members = {name for name in members
                           if name.split('/', 1)[0].casefold() == 'applocker-observation'}
        require(sibling_members == {FIXED_MEMBERS['invocation'], RAW_MEMBER}, 'commit')
        result['reason'] = 'identity_inconsistent'
        identity = target_identity(*(members[FIXED_MEMBERS[key]]
                                     for key in ('ownership', 'case', 'run', 'payload')))
        result['reason'] = 'record_invalid'
        raw = validate_raw_receipt(members[RAW_MEMBER], identity, bracket, invocation)
        if raw['Status'] == 'raw_matched':
            return {'status': 'matched_record', 'reason': None, 'decision': dict(raw['Decision'])}
        result['reason'] = raw['Reason']
    except (ArtifactError, KeyError, TypeError, IndexError, ValueError, UnicodeError, OverflowError, RecursionError):
        pass
    return result
