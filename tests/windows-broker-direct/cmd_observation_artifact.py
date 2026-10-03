"""Bounded external acceptance over already authenticated artifact members.

No archive acquisition, extraction, filesystem, process, token, or network access.
The caller owns archive CRC/source/run authentication; JSON cannot provide it.
"""
import copy
import json
import re

from cmd_observation_contracts import (ArtifactError, CASES, POLICY, SHA, NONCE, require, exact,
    digest, direct_schema, case_schema, no_allocation, writer, without_writer,
    authority_facts, capture_files, raw_observation, owned_path, file_identity, case_provenance, selected_acl)
from cmd_observation_cases import OBSERVATIONS

BOM_WRAPPERS = {'source.txt', 'fixture-binaries-sha256.txt', 'evidence-sha256.txt',
                'pilot/preparation-premise.json', 'runtime/runtime-inventory.json', 'runtime/runtime-copy-sha256.txt'}
RUN_BOOLS = ('OrdinaryControlPassed ReferenceRoutePassed AllFourOfflineCasesPassed AllCaseCleanupConfirmed '
             'RunRootRemoved CmdSentinelObservationPassed CmdBatchObservationPassed NetworkDenialProven '
             'CmdCwdRawObservationMatched CmdReadRawObservationMatched CmdRelativeBatchRawObservationMatched').split()
RUN_COUNTS = dict(RequiredCaseCount=11, OriginalPilotRequiredCaseCount=6, AdditiveSentinelRequiredCaseCount=1,
                  AdditiveBatchRequiredCaseCount=1, AdditiveCwdRequiredCaseCount=1, AdditiveReadRequiredCaseCount=1,
                  AdditiveRelativeBatchRequiredCaseCount=1, OriginalNestedRequiredRows=20)
RUN_STRINGS = 'Policy Phase Failure CleanupScope CompletionJournal JournalProtocol'.split()
JOURNAL_PROTOCOL = 'completed filename is the final resolution receipt; preconditions alone are not completion'
REASON_CODES = {'identity', 'provenance', 'missing', 'parse', 'stage', 'commit', 'cleanup',
                'raw_mismatch', 'unsupported_encoding', 'producer_acceptance_leak'}


def canonical(name):
    require(type(name) is str and 0 < len(name) <= 32700, 'provenance')
    require(not name.startswith('/') and not any(c in name for c in '\\:\0\r\n'), 'provenance')
    require(all(ord(c) >= 32 for c in name), 'provenance')
    require(all(p not in ('', '.', '..') and not p.endswith(('.', ' ')) for p in name.split('/')), 'provenance')
    return name


def text_member(members, name):
    require(name in members, 'missing', name, status='incomplete')
    value = members[name]
    if name in BOM_WRAPPERS and value.startswith(b'\xef\xbb\xbf'):
        value = value[3:]
    try:
        text = value.decode('utf-8', errors='strict')
    except UnicodeError:
        raise ArtifactError('parse', name, status='incomplete')
    require(not text.startswith('\ufeff'), 'parse', name, status='incomplete')
    return text


def json_member(members, name):
    require(name in members, 'missing', name, status='incomplete')
    require(len(members[name]) <= 4 * 1024 * 1024, 'parse', name, status='incomplete')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'parse', name)
            result[key] = value
        return result
    def invalid(_):
        raise ArtifactError('parse', name)
    try:
        value = json.loads(text_member(members, name), object_pairs_hook=pairs, parse_constant=invalid)
    except (ValueError, RecursionError) as error:
        if isinstance(error, ArtifactError):
            raise
        raise ArtifactError('parse', name, status='incomplete')
    pending = [(value, 0)]
    while pending:
        current, depth = pending.pop()
        require(depth <= 32, 'parse', name, status='incomplete')
        if type(current) is dict:
            for key, item in current.items():
                require('ObservationPassed' not in key or key in ('CmdSentinelObservationPassed', 'CmdBatchObservationPassed'),
                        'producer_acceptance_leak', name)
                pending.append((item, depth + 1))
        elif type(current) is list:
            require(len(current) <= 4096, 'parse', name, status='incomplete')
            pending.extend((item, depth + 1) for item in current)
    return value


def trust_members(context, members):
    require(type(context) is dict and type(members) is dict, 'provenance')
    exact(context, {'repository': 'Eswink/coding-tools-mcp',
                    'workflow_path': '.github/workflows/windows-lpac-runtime-diagnostic.yml',
                    'artifact_name': 'windows-lpac-runtime-diagnostic', 'artifact_crc_verified': True,
                    'manifest_verified': True, 'member_set_complete': True,
                    'required_setup_and_capture_verified': True}, 'provenance')
    for key in ('commit', 'tree', 'run_head_sha'):
        require(type(context.get(key)) is str and re.fullmatch(r'[0-9a-f]{40}', context[key]), 'identity')
    require(context['run_head_sha'] == context['commit'], 'identity')
    for key in ('run_id', 'job_id', 'artifact_id', 'run_attempt', 'artifact_size'):
        require(type(context.get(key)) is int and 0 < context[key] < 2**63, 'provenance')
    require(type(context.get('artifact_sha256')) is str and SHA.fullmatch(context['artifact_sha256']), 'provenance')
    require(context.get('job_terminal_state') in ('success', 'failure'), 'stage', status='incomplete')
    require(0 < len(members) <= 4096, 'provenance', status='incomplete')
    require(type(context.get('member_sha256')) is dict and set(context['member_sha256']) == set(members), 'provenance')
    seen, total = set(), 0
    for name, data in members.items():
        canonical(name)
        require(name.casefold() not in seen and type(data) is bytes, 'provenance', name)
        seen.add(name.casefold())
        total += len(data)
        require(total <= 128 * 1024 * 1024, 'provenance', name, status='incomplete')
        require(context['member_sha256'][name] == digest(data), 'provenance', name)
    manifest = {}
    for line in text_member(members, 'evidence-sha256.txt').splitlines():
        match = re.fullmatch(r'([0-9A-Fa-f]{64}) (evidence[/\\].+)', line)
        require(match is not None, 'provenance', 'evidence-sha256.txt')
        path = match[2]
        require(not ('/' in path and '\\' in path), 'provenance', 'evidence-sha256.txt')
        name = canonical(path[len('evidence/'):].replace('\\', '/'))
        require(name not in manifest and name.casefold() not in {n.casefold() for n in manifest}, 'provenance', name)
        manifest[name] = match[1].lower()
    require(set(manifest) == set(members) - {'evidence-sha256.txt'}, 'provenance', 'evidence-sha256.txt')
    require(all(manifest[name] == digest(members[name]) for name in manifest), 'provenance', 'evidence-sha256.txt')
    require(text_member(members, 'source.txt').splitlines() == [context['commit'], context['tree']], 'identity', 'source.txt')
    for name in BOM_WRAPPERS & set(members):
        text_member(members, name)


def run_schema(run):
    fields = RUN_BOOLS + RUN_STRINGS + list(RUN_COUNTS) + ['NotCovered', 'InitialSelectedParent', 'SelectedParent', 'Broker', 'Cases']
    require(type(run) is dict and set(run) == set(fields), 'parse')
    exact(run, RUN_COUNTS)
    exact(run, {'Policy': POLICY, 'JournalProtocol': JOURNAL_PROTOCOL, 'NetworkDenialProven': False})
    for key in RUN_BOOLS:
        require(type(run[key]) is bool, 'parse')
    for key in RUN_STRINGS:
        require(run[key] is None or type(run[key]) is str, 'parse')
    require(run['NotCovered'] == ['python', 'npm.cmd', 'git', 'nested_child_support', 'ConPTY', 'production_integration'])
    require(type(run['Cases']) is list and len(run['Cases']) <= 11, 'parse')
    require([row.get('Case') for row in run['Cases'] if type(row) is dict] == list(CASES[:len(run['Cases'])]))
    for row in run['Cases']:
        case_schema(row)
    direct_schema(run['Broker'])


def selected_parent(receipt, complete=True):
    require(type(receipt) is dict, 'parse')
    require(set(receipt) == set('Policy RequestedPath ResolvedPath Failure Acquired FinalScanConfirmed CloseAttempted CloseConfirmed PlannedHandles AcquiredHandles VerifiedGuards Metadata'.split()), 'parse')
    for key in ('Acquired', 'FinalScanConfirmed', 'CloseAttempted', 'CloseConfirmed'):
        require(type(receipt[key]) is bool, 'parse')
    for key in ('PlannedHandles', 'AcquiredHandles', 'VerifiedGuards'):
        require(type(receipt[key]) is int, 'parse')
    exact(receipt, {'Policy': 'localappdata_temp_ci_v1', 'Failure': None, 'Acquired': True}, 'cleanup')
    path = owned_path(receipt.get('ResolvedPath'))
    require(path == receipt.get('RequestedPath') and path.endswith('\\Temp'), 'identity')
    parts, paths = path[3:].split('\\'), [path[:3]]
    for part in parts:
        paths.append(paths[-1] + ('' if paths[-1].endswith('\\') else '\\') + part)
    require(len(paths) <= 32 and receipt.get('PlannedHandles') == len(paths)
            and receipt.get('AcquiredHandles') == len(paths), 'cleanup')
    require(type(receipt.get('VerifiedGuards')) is int and receipt['VerifiedGuards'] > 0, 'cleanup')
    if complete:
        exact(receipt, {'FinalScanConfirmed': True, 'CloseAttempted': True, 'CloseConfirmed': True}, 'cleanup')
    else:
        exact(receipt, {'FinalScanConfirmed': False, 'CloseAttempted': False, 'CloseConfirmed': False}, 'stage')
    direct_schema(receipt['Metadata'])
    selected_acl(receipt['Metadata'])
    n, i = receipt['Metadata']['Numbers'], receipt['Metadata']['Identities']
    pins = [i.get('selected_pin_' + str(index) + '_identity') for index in range(len(paths))]
    require(len(set(pins)) == len(paths), 'identity')
    require(all(type(pin) is str and pin.split(':')[0] == pins[0].split(':')[0] for pin in pins), 'identity')
    for index, item in enumerate(paths):
        label = 'selected_pin_' + str(index)
        identity = i.get(label + '_identity')
        file_identity(identity)
        exact(i, {label + '_path': item, label + '_rechecked_identity': identity})
        exact(n, {label + '_open_error': 0, label + '_handle_flags': 0,
                  label + '_desired_access': 0x20081 if index == len(paths) - 1 else 0xa0}, 'cleanup')
        require(n.get(label + '_attributes', 0) & 0x410 == 0x10, 'cleanup')
        if complete:
            exact(n, {label + '_close_error': 0, label + '_close_confirmed': 1}, 'cleanup')
    exact(n, {'selected_parent_broker_owned': 1, 'selected_parent_acl_observation_completed': 1,
              'selected_parent_broker_owner_query_confirmed': 1, 'selected_parent_security_free_confirmed': 1,
              'selected_parent_broker_owner_data_free_confirmed': 1,
              'selected_parent_broker_owner_token_close_confirmed': 1,
              'selected_parent_broker_owner_token_close_error': 0}, 'cleanup')
    require(not any(k.endswith(('_exception', '_failure')) for k in i), 'cleanup')
    require(all(v == 1 for k, v in n.items() if k.endswith(('_close_confirmed', '_free_confirmed'))), 'cleanup')


def journal(members, prefix, label, receipt, root, profile):
    nonce = receipt['Identities'].get('pilot_journal_' + label + '_nonce')
    require(type(nonce) is str and NONCE.fullmatch(nonce), 'commit')
    completed, pre = prefix + 'completed-' + nonce + '.txt', prefix + 'preconditions-' + nonce + '.json'
    expected = ('protocol=owned-pending-journal-v1\nstate=pending\nnonce=' + nonce + '\nlabel=' + label +
                '\nplanned_root=' + root + '\nplanned_profile=' + profile + '\npreconditions_record=' +
                pre.rsplit('/', 1)[-1] + '\nresolution=completed filename commits the immutable nonce-bound preconditions record; pending is not completion\n')
    require(completed in members, 'commit', completed, label, 'incomplete')
    require(text_member(members, completed) == expected, 'commit', completed, label)
    for name in members:
        if name.startswith(prefix) and '/' not in name[len(prefix):]:
            if name[len(prefix):].startswith(('completed-', 'preconditions-', 'cleanup-uncertain')):
                require(name in (completed, pre), 'commit', name, label)
    require(len(members[completed]) <= 4 * 1024 * 1024, 'parse', completed, label, 'incomplete')
    return json_member(members, pre), nonce


def committed_case(row, members, run_root, inventory, run_identity):
    kind, r = row['Case'], row['Launcher']
    if row['NoCaseResourcesAllocated']:
        no_allocation(row, inventory, members)
        return
    exact(row, {'Fatal': False, 'Failure': None, 'IndividualResourceCleanupConfirmed': True,
                'CaptureIntegrityConfirmed': True, 'ProfileDeleteApiConfirmed': True, 'OwnedRootRemoved': True,
                'CleanupPreconditionsConfirmed': True, 'CaseMarkerResolved': True, 'ScopedLifecycleCleanupConfirmed': True}, 'cleanup')
    exact(r, {'Failure': None, 'Drained': True, 'CleanupConfirmed': False})
    n, i = r['Numbers'], r['Identities']
    root = owned_path(i.get('pilot_owned_root_path'))
    require(root.rsplit('\\', 1)[0] == run_root and re.fullmatch(r'owned-[0-9a-f]{32}', root.rsplit('\\', 1)[1]))
    profile = i.get('pilot_profile_name')
    require(type(profile) is str and re.fullmatch(r'ctm\.fixture\.pilot\.[0-9a-f]{32}', profile))
    exact(i, {'pilot_case_id': kind, 'pilot_owned_parent_path': run_root})
    file_identity(i.get('pilot_owned_root_identity'))
    require(i.get('pilot_owned_parent_identity') == run_identity and i['pilot_owned_root_identity'] != run_identity, 'identity')
    require(i['pilot_owned_root_identity'].split(':')[0] == run_identity.split(':')[0], 'identity')
    exact(n, {'delete_profile_hresult': 0, 'pilot_owned_root_removed': 1, 'pilot_scope_creation_confirmed': 1,
              'individual_stop_drain_close_confirmed': 1, 'exact_process_stop_confirmed': 1}, 'cleanup')
    capture_files(row, members)
    authority_facts(row, kind == 'ordinary')
    if kind == 'reference':
        exact(row, {'OfflineReferenceRouteValid': True, 'NetworkDenialProven': False}, 'stage')
        exact(r, {'Wait': 0}, 'stage')
        base = 'pilot/reference/'
        expected = ['token=true', 'inside=true', 'outside_read=true', 'outside_write=true']
        require(sorted(text_member(members, base + 'pre-network.txt').splitlines()) == sorted(expected), 'provenance')
        checks = text_member(members, base + 'runtime-checks.txt').splitlines()
        keys = ('protocol_catalog_open', 'protocol_catalog_close', 'namespace_catalog_open', 'namespace_catalog_close', 'provider_dll_open', 'winsock_dll_open')
        require(len(checks) == 6 and {line.split('=')[0] for line in checks} == set(keys)
                and all(re.fullmatch(r'[a-z_]+=-?[0-9]+', line) for line in checks), 'provenance')
        if r['Exit'] == 15107:
            require(base + 'receipt.txt' not in members and not row['NativeFiveAssertionsPassed'], 'stage')
        else:
            require(r['Exit'] == 0 and row['NativeFiveAssertionsPassed'], 'stage')
            require(sorted(text_member(members, base + 'receipt.txt').splitlines()) == sorted(expected + ['network=true']), 'provenance')
    prefix = 'pilot/' + kind + '/'
    pre, nonce = journal(members, prefix, kind, r, root, profile)
    stored = json_member(members, prefix + 'case.json')
    case_schema(pre)
    case_schema(stored)
    writer(r, 'case_receipt')
    projected = copy.deepcopy(row)
    projected['Launcher'] = without_writer(r, ['case_receipt'])
    require(stored == projected, 'stage', prefix + 'case.json', kind)
    writer(stored['Launcher'], 'journal_preconditions_' + nonce)
    projected = copy.deepcopy(stored)
    projected['CaseMarkerResolved'] = projected['ScopedLifecycleCleanupConfirmed'] = False
    projected['Launcher'] = without_writer(projected['Launcher'], ['journal_preconditions_' + nonce])
    for suffix in ('close_error', 'close_confirmed'):
        exact(stored['Launcher']['Numbers'], {'journal_binding_verify_' + suffix: 0 if suffix == 'close_error' else 1}, 'commit')
        projected['Launcher']['Numbers'].pop('journal_binding_verify_' + suffix)
    require(pre == projected, 'stage', prefix + 'preconditions-' + nonce + '.json', kind)
    for name in ('ownership-root.json', 'ownership-profile.json', 'ownership-process.json'):
        snapshot = json_member(members, prefix + name)
        case_schema(snapshot)
        require(all(snapshot[observation['row_flag']] is False for observation in OBSERVATIONS), 'stage')
        require(snapshot['Case'] == kind and snapshot['Launcher']['Identities'].get('pilot_case_id') == kind, 'identity')
        require(snapshot['Launcher']['Identities'].get('pilot_profile_name') == profile, 'identity')
        observed = snapshot['Launcher']
        writer(r, name[:-5].replace('-', '_'))
        for key, value in observed['Identities'].items():
            require(i.get(key) == value, 'stage', prefix + name)
        for key, value in observed['Numbers'].items():
            if key != 'pilot_profile_checkpoint_completed':
                require(n.get(key) == value, 'stage', prefix + name)
        for key in ('pilot_owned_parent_path', 'pilot_owned_root_path', 'pilot_owned_root_identity'):
            require(observed['Identities'].get(key) == i.get(key), 'identity')
        if name != 'ownership-root.json':
            for key in ('Executable', 'CommandLine', 'ExecutableSha256', 'ProfileSid'):
                require(observed[key] == r[key], 'stage')
        if name == 'ownership-process.json':
            exact(observed, {'CreateAttempted': True, 'Created': True, 'Assigned': False, 'Resumed': False,
                             'StdioValidated': True, 'HostStdioClosed': True}, 'stage')


def provenance(run, members):
    premise = json_member(members, 'pilot/preparation-premise.json')
    exact(premise, {'policy': POLICY, 'foundation_valid': True, 'network_denial_proven': False,
                    'selected_parent_policy': 'localappdata_temp_ci_v1'}, 'provenance')
    inventory = json_member(members, 'runtime/runtime-inventory.json')
    require(type(inventory) is list and len(inventory) == 7, 'provenance')
    ready = {}
    for item in inventory:
        require(type(item) is dict and item.get('runtime') in ('python', 'node', 'git', 'powershell', 'pwsh', 'npm', 'cmd'), 'parse')
        require(item['runtime'] not in ready and type(item.get('ready')) is bool, 'parse')
        ready[item['runtime']] = item['ready']
    require(premise.get('runtime_inventory') == inventory and premise.get('ready') == [k for k in ('node', 'cmd', 'powershell', 'pwsh') if ready[k]], 'provenance')
    require(premise.get('selected_parent') == run['SelectedParent']['ResolvedPath'], 'identity')
    native = run['Broker']['Identities'].get('same_run_native_fixture_sha256')
    require(type(native) is str and SHA.fullmatch(native) and premise.get('native_fixture_sha256') == native, 'provenance')
    binaries = text_member(members, 'fixture-binaries-sha256.txt').splitlines()
    require(sum(line.lower() == native + ' windows_sandbox_fixture.exe' for line in binaries) == 1, 'provenance')
    for name, outside in [('control-receipt.txt', 'true'), ('mode-2-ordinary-appcontainer-receipt.txt', 'false')]:
        lines = text_member(members, 'foundation/' + name).splitlines()
        require(sorted(lines) == sorted(['token=true', 'inside=true', 'outside_read=' + outside, 'outside_write=true', 'network=true']), 'provenance')
    require('runtime/runtime-matrix.json' in members, 'missing', 'runtime/runtime-matrix.json', status='incomplete')
    # Legacy matrix bytes are hash-verified but deliberately opaque. Their keys
    # cannot supply prerequisite/accepted truth; only parsed contributing receipts can.
    runtime_hashes = {}
    for line in text_member(members, 'runtime/runtime-copy-sha256.txt').splitlines():
        match = re.fullmatch(r'([0-9A-Fa-f]{64}) (.+)', line)
        require(match is not None and match[2].casefold() not in {k.casefold() for k in runtime_hashes}, 'provenance')
        runtime_hashes[match[2]] = match[1].lower()
    windows = set()
    for row in run['Cases']:
        if not row['NoCaseResourcesAllocated']:
            windows.add(case_provenance(row, members, native, runtime_hashes, {item['runtime']: item for item in inventory}))
    require(len(windows) == 1, 'provenance')
    return ready


def validate_completion(run, members, parsed):
    run_schema(run)
    exact(run, {'Phase': 'completion_preconditions_persisted', 'Failure': None, 'OrdinaryControlPassed': True,
                'ReferenceRoutePassed': True, 'AllCaseCleanupConfirmed': True, 'RunRootRemoved': True}, 'commit')
    require(len(run['Cases']) == 11, 'missing', status='incomplete')
    matrices = {'pilot/matrix-' + str(n).zfill(2) + '.json' for n in range(1, 12)}
    require({name for name in members if name.startswith('pilot/matrix-')} == matrices, 'stage')
    require('pilot/pilot-failure.json' not in members and not any(n.startswith('pilot/') and n.endswith('/cleanup-uncertain.txt') for n in members), 'commit')
    for receipt in (run['InitialSelectedParent'], run['SelectedParent'], json_member(members, 'selected-parent-preflight.json')):
        selected_parent(receipt)
        require(receipt['ResolvedPath'] == run['SelectedParent']['ResolvedPath'], 'identity')
    broker, root = run['Broker'], owned_path(run['Broker']['Identities'].get('pilot_owned_root_path'))
    run_identity = broker['Identities'].get('pilot_owned_root_identity')
    file_identity(run_identity)
    endpoint = run['SelectedParent']['Metadata']['Identities']['selected_pin_' + str(run['SelectedParent']['PlannedHandles'] - 1) + '_identity']
    require(broker['Identities'].get('pilot_owned_parent_identity') == endpoint and run_identity != endpoint
            and run_identity.split(':')[0] == endpoint.split(':')[0], 'identity')
    require(root.rsplit('\\', 1)[0] == run['SelectedParent']['ResolvedPath'] and re.fullmatch(r'ctm-direct-pilot-[0-9a-f]{32}', root.rsplit('\\', 1)[1]))
    exact(broker['Numbers'], {'pilot_owned_root_removed': 1, 'pilot_scope_creation_confirmed': 1}, 'cleanup')
    pre, nonce = journal(members, 'pilot/', 'run', broker, root, 'none')
    require(run['CompletionJournal'] == 'completed-' + nonce + '.txt', 'commit')
    run_schema(pre)
    writer(pre['Broker'], 'final_result')
    projected = copy.deepcopy(pre)
    projected['Broker'] = without_writer(pre['Broker'], ['final_result'])
    require(projected == run, 'stage', 'pilot/pilot-result.json')
    inventory = provenance(run, members)
    profiles, roots = set(), set()
    for row in run['Cases']:
        committed_case(row, members, root, inventory, run_identity)
        if not row['NoCaseResourcesAllocated']:
            identity = row['Launcher']['Identities']
            profile, case_root = identity['pilot_profile_name'], identity['pilot_owned_root_path']
            require(profile not in profiles and case_root not in roots)
            profiles.add(profile)
            roots.add(case_root)
    old_six = all(not row['NoCaseResourcesAllocated'] and not row['Fatal'] and row['ScopedLifecycleCleanupConfirmed']
                  and (row['OrdinarySignatureMatched'] and row['OrdinaryRejected'] if index == 0 else
                       row['OfflineReferenceRouteValid'] if index == 1 else row['PositivePassed'])
                  for index, row in enumerate(run['Cases'][:6]))
    require(run['AllFourOfflineCasesPassed'] == old_six, 'stage')
    for slot, aggregate, flag in [(6, 'CmdSentinelObservationPassed', 'CmdExit23Observed'), (7, 'CmdBatchObservationPassed', 'CmdBatchExit23Observed')]:
        row = run['Cases'][slot]
        require(run[aggregate] == (row[flag] and not row['NoCaseResourcesAllocated'] and not row['Fatal'] and row['ScopedLifecycleCleanupConfirmed']), 'stage')
    for count in range(1, 12):
        name = 'pilot/matrix-' + str(count).zfill(2) + '.json'
        matrix = parsed.get(name)
        require(matrix is not None, 'missing', name, status='incomplete')
        run_schema(matrix)
        exact(matrix, {'Phase': 'collecting', 'Failure': None, 'AllCaseCleanupConfirmed': False, 'RunRootRemoved': False,
                       'OrdinaryControlPassed': count > 1, 'ReferenceRoutePassed': count > 2}, 'stage')
        require(matrix['Cases'] == run['Cases'][:count], 'stage', name)
        require(matrix['InitialSelectedParent'] == run['InitialSelectedParent'], 'stage', name)
        selected_parent(matrix['SelectedParent'], False)
        for key in ('Policy', 'CleanupScope', 'CompletionJournal', 'JournalProtocol', 'NotCovered'):
            require(matrix[key] == run[key], 'stage', name)
        for key, value in matrix['Broker']['Identities'].items():
            require(run['Broker']['Identities'].get(key) == value, 'stage', name)
        for key, value in matrix['Broker']['Numbers'].items():
            require(run['Broker']['Numbers'].get(key) == value, 'stage', name)
        for earlier in range(1, count):
            writer(matrix['Broker'], 'matrix_' + str(earlier))
        require('evidence_matrix_' + str(count) not in matrix['Broker']['Identities'], 'stage', name)
        writer(run['Broker'], 'matrix_' + str(count))
        for observation in OBSERVATIONS:
            key, slot = observation['run_flag'], observation['slot']
            require(matrix[key] == (run[key] if count > slot else False), 'stage', name)
        for key, count_needed in [('AllFourOfflineCasesPassed', 6), ('CmdSentinelObservationPassed', 7), ('CmdBatchObservationPassed', 8)]:
            require(matrix[key] == (run[key] if count >= count_needed else False), 'stage', name)
    return True


def _evaluate(trusted_context, members):
    """Return reviewer-only acceptance. Every missing/invalid gate defaults false."""
    context = trusted_context if type(trusted_context) is dict else {}
    result = {'protocol': 'cmd-cwd-read-relative-batch-acceptance-v1', 'RunCompletionValidated': False, 'Reasons': []}
    for observation in OBSERVATIONS:
        result.update({observation['accepted_field']: False, observation['run_flag']: False,
                       observation['status_key']: 'incomplete'})
    for output, key in [('source_commit', 'commit'), ('source_tree', 'tree'), ('run_id', 'run_id'),
                        ('job_id', 'job_id'), ('run_attempt', 'run_attempt'), ('artifact_id', 'artifact_id')]:
        result[output] = context.get(key)
    def record(error, case='', member=''):
        require(error.code in REASON_CODES)
        reason = dict(code=error.code, case=error.case or case, member=error.member or member)
        if reason not in result['Reasons'] and len(result['Reasons']) < 64:
            result['Reasons'].append(reason)
    try:
        trust_members(context, members)
    except ArtifactError as error:
        record(error)
        for observation in OBSERVATIONS:
            result[observation['status_key']] = error.status
        return result
    parsed, parse_errors = {}, []
    for name in members:
        if name.startswith('pilot/') and name.endswith('.json') or name == 'selected-parent-preflight.json':
            try:
                parsed[name] = json_member(members, name)
            except ArtifactError as error:
                parse_errors.append(error)
                record(error)
    candidate = parsed.get('pilot/pilot-result.json')
    if candidate is None:
        candidate = next((parsed['pilot/matrix-' + str(n).zfill(2) + '.json'] for n in range(11, 0, -1)
                          if 'pilot/matrix-' + str(n).zfill(2) + '.json' in parsed), None)
    try:
        require(candidate is not None, 'missing', 'pilot/pilot-result.json', status='incomplete')
        run_schema(candidate)
    except ArtifactError as error:
        record(error)
        for observation in OBSERVATIONS:
            result[observation['status_key']] = error.status
        return result
    raw_errors, unsupported = {}, {}
    original_hash = candidate['Cases'][3]['Launcher']['ExecutableSha256'] if len(candidate['Cases']) > 3 else None
    for observation in OBSERVATIONS:
        slot, tag, flag = observation['slot'], observation['tag'], observation['row_flag']
        kind, run_flag, status_key = observation['kind'], observation['run_flag'], observation['status_key']
        try:
            require(len(candidate['Cases']) > slot, 'missing', case=kind, status='incomplete')
            row = candidate['Cases'][slot]
            matched, unsupported[tag] = (False, False) if row['NoCaseResourcesAllocated'] else raw_observation(row, members, original_hash)
            result[run_flag] = matched
            require(row[flag] == matched and candidate[run_flag] == matched, 'raw_mismatch')
            require(all(row[other['row_flag']] is False for other in OBSERVATIONS if other['kind'] != kind), 'raw_mismatch')
            if not row['Fatal'] and not row['NoCaseResourcesAllocated']:
                expected_status = observation['matched_status']
                if not matched:
                    expected_status = 'cmd_cwd_expected_encoding_unsupported' if unsupported[tag] else observation['unmatched_status']
                require(row['Status'] == ('deadline_exceeded' if row['Launcher']['Wait'] == 258 else expected_status), 'stage')
                require(row['CanaryClassification'] == observation['canary'], 'stage')
            result[status_key] = 'not_matched'
            if not matched:
                record(ArtifactError('unsupported_encoding' if unsupported[tag] else 'raw_mismatch'), kind)
        except ArtifactError as error:
            raw_errors[tag] = error
            record(error, kind)
            result[status_key] = error.status
    try:
        require(not parse_errors, 'parse', status='incomplete')
        require(not raw_errors, 'raw_mismatch', status='incomplete' if any(e.status == 'incomplete' for e in raw_errors.values()) else 'inconsistent')
        require('pilot/pilot-result.json' in parsed, 'missing', 'pilot/pilot-result.json', status='incomplete')
        result['RunCompletionValidated'] = validate_completion(candidate, members, parsed)
    except ArtifactError as error:
        record(error)
        for observation in OBSERVATIONS:
            result[observation['status_key']] = error.status
        return result
    for observation in OBSERVATIONS:
        if observation['tag'] not in raw_errors and result[observation['run_flag']]:
            result[observation['accepted_field']] = True
            result[observation['status_key']] = 'accepted'
    return result


def evaluate_cmd_observation_artifact(trusted_context, members):
    """Malformed shapes always yield a bounded result, never partial acceptance."""
    try:
        return _evaluate(trusted_context, members)
    except (KeyError, TypeError, IndexError, UnicodeError, OverflowError):
        result = _evaluate({}, {})
        result['Reasons'] = [dict(code='parse', case='', member='')]
        for observation in OBSERVATIONS:
            result[observation['status_key']] = 'incomplete'
        return result
