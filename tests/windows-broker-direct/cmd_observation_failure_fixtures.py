"""Pure source-ordered failed/unsupported variants of the synthetic fixture."""
from copy import deepcopy

from cmd_observation_fixtures import (OLD_POSITIVES, RUN_NONCE, completed_fixture,
    case_defaults, decode, encode, digest, reseal, writer)


def erase_writer(receipt, label):
    prefix = 'evidence_' + label
    receipt['Numbers'] = {key: value for key, value in receipt['Numbers'].items() if not key.startswith(prefix + '_')}
    receipt['Identities'].pop(prefix, None)


def late_failure(members, category, contradiction=False, target='cmd-read-direct', matrix_position=10):
    """Drop completed receipts impossible at the injected persistence/lifecycle stage."""
    if target not in ('cmd-read-direct', 'cmd-relative-batch-exit23') or type(matrix_position) is not int or matrix_position not in (10, 11):
        raise ValueError('finite late-failure target and matrix position required')
    run = decode(members['pilot/pilot-result.json'])
    baseline = {key: run[key] for key in OLD_POSITIVES}
    favorable = deepcopy(run)
    bound = members['pilot/preconditions-' + RUN_NONCE + '.json']
    run.update(Phase='failed_recovery_retained', Failure='IOException: synthetic ' + category)
    after_scan = category.startswith(('final_result_', 'run_bind', 'run_verify', 'run_resolve'))
    run['RunRootRemoved'] = not category.startswith(('case_', 'matrix_', 'run_root'))
    reached = 10 if category.startswith('case_') and target == 'cmd-read-direct' else matrix_position if category.startswith('matrix_') else 11
    guards = 4 * reached
    run['SelectedParent']['VerifiedGuards'] = guards + 2 if after_scan or category.startswith('selected_pin_') else guards if category.startswith(('case_', 'matrix_')) else guards + 1
    if category.startswith(('case_', 'matrix_')):
        run['Broker']['Numbers'].pop('pilot_owned_root_removed', None)
        run['AllCaseCleanupConfirmed'] = False
    if reached == 10:
        blocked = case_defaults('cmd-relative-batch-exit23')
        blocked.update(Fatal=True, NoCaseResourcesAllocated=True,
                       Status='blocked_prior_control_or_recovery' if category.startswith('case_') else 'blocked_run_failure_no_subject_created')
        run['Cases'][10] = blocked
        run['CmdRelativeBatchRawObservationMatched'] = False
        if not contradiction:
            for name in tuple(members):
                if name.startswith('pilot/cmd-relative-batch-exit23/'):
                    members.pop(name)
    run['SelectedParent']['FinalScanConfirmed'] = after_scan or category.startswith('selected_pin_')
    if category.startswith(('selected_pin_', 'final_guard', 'final_identity_scan')):
        run['SelectedParent']['Failure'] = 'IOException: synthetic selected-parent failure'
    if category.startswith('selected_pin_'):
        run['SelectedParent']['CloseConfirmed'] = False
        run['SelectedParent']['Metadata']['Numbers']['selected_pin_0_close_confirmed'] = 0
    if category.startswith('run_root'):
        run['Broker']['Numbers']['pilot_owned_root_removed'] = 0
    run_completed = 'pilot/completed-' + RUN_NONCE + '.txt'
    if not contradiction:
        members['pilot/cleanup-uncertain.txt'] = members.pop(run_completed)
    if category.startswith('case_'):
        kind, slot = target, 9 if target == 'cmd-read-direct' else 10
        row = run['Cases'][slot]
        nonce = row['Launcher']['Identities']['pilot_journal_' + kind + '_nonce']
        base = 'pilot/' + kind + '/'
        row.update(Fatal=True, Failure='IOException: synthetic ' + category,
                   Status='case_receipt_persistence_failed' if category.startswith('case_receipt') else 'evidence_or_scoped_cleanup_failed')
        if not category.startswith('case_receipt') and not contradiction:
            members[base + 'cleanup-uncertain.txt'] = members.pop(base + 'completed-' + nonce + '.txt')
            row.update(CaseMarkerResolved=False, ScopedLifecycleCleanupConfirmed=False)
        if category in ('case_profile_delete_false', 'case_profile_delete_throw', 'case_root_remove_false', 'case_root_remove_throw'):
            row.update(CleanupPreconditionsConfirmed=False)
            row['ProfileDeleteApiConfirmed' if 'profile' in category else 'OwnedRootRemoved'] = False
            row['Launcher']['Numbers']['delete_profile_hresult' if 'profile' in category else 'pilot_owned_root_removed'] = -1 if 'profile' in category else 0
            if 'profile' in category:
                row['OwnedRootRemoved'] = False
                row['Launcher']['Numbers'].pop('pilot_owned_root_removed', None)
        if not contradiction:
            if category.startswith('case_receipt'):
                if category.endswith(('serialize', 'create')):
                    members.pop(base + 'case.json')
                elif category.endswith(('write', 'flush')):
                    members[base + 'case.json'] = b'{"Case":'
                else:
                    row['Launcher']['Numbers']['evidence_case_receipt_close_confirmed'] = 0
            else:
                before_bind = category.startswith(('case_profile', 'case_root', 'case_bind_')) or category == 'case_verify_pending'
                if before_bind:
                    if category not in ('case_bind_write', 'case_bind_flush', 'case_bind_close'):
                        erase_writer(row['Launcher'], 'journal_preconditions_' + nonce)
                    if category == 'case_bind_close':
                        row['Launcher']['Numbers']['evidence_journal_preconditions_' + nonce + '_close_confirmed'] = 0
                    for suffix in ('close_error', 'close_confirmed'):
                        row['Launcher']['Numbers'].pop('journal_binding_verify_' + suffix, None)
                    if category == 'case_bind_write':
                        members[base + 'preconditions-' + nonce + '.json'] = b'{\"Case\":'
                    elif category not in ('case_bind_close', 'case_bind_flush'):
                        members.pop(base + 'preconditions-' + nonce + '.json')
                stored = deepcopy(row)
                erase_writer(stored['Launcher'], 'case_receipt')
                members[base + 'case.json'] = encode(stored)
        run['AllCaseCleanupConfirmed'] = False
        if not contradiction:
            matrix_name = 'pilot/matrix-' + str(slot + 1) + '.json'
            matrix = decode(members[matrix_name])
            matrix['Cases'][slot] = deepcopy(row)
            members[matrix_name] = encode(matrix)
            if slot == 9:
                matrix['Cases'].append(deepcopy(run['Cases'][10]))
                writer(matrix['Broker'], 'matrix_10', run['Broker']['Identities']['evidence_matrix_10'])
                members['pilot/matrix-11.json'] = encode(matrix)
    if not contradiction:
        members.pop('pilot/pilot-result.json')
        members.pop('pilot/preconditions-' + RUN_NONCE + '.json')
        if category.startswith('matrix_'):
            for position in range(matrix_position, 12):
                erase_writer(run['Broker'], 'matrix_' + str(position))
                members.pop('pilot/matrix-' + str(position) + '.json')
        elif category.startswith('final_result_') and category.endswith(('write', 'flush', 'close_false', 'close_throw')):
            members['pilot/pilot-result.json'] = encode(favorable) if 'close' in category else b'{"Policy":'
        elif category.startswith('run_') and not category.startswith('run_root'):
            # Favorable final-result bytes exist before Bind/Verify/Resolve errors.
            members['pilot/pilot-result.json'] = encode(favorable)
            if category.startswith('run_binding') or category in (
                    'run_verify_pending', 'run_resolve_rename', 'run_bind_flush', 'run_bind_close', 'run_bind_write'):
                members['pilot/preconditions-' + RUN_NONCE + '.json'] = bound
                run['Broker'] = deepcopy(decode(bound)['Broker'])
                writer(run['Broker'], 'journal_preconditions_' + RUN_NONCE)
                if category == 'run_bind_write':
                    members['pilot/preconditions-' + RUN_NONCE + '.json'] = b'{"Policy":'
                if category == 'run_bind_close':
                    label = 'evidence_journal_preconditions_' + RUN_NONCE
                    run['Broker']['Numbers'].update({label + '_close_confirmed': 0, label + '_close_error': 6})
    members['pilot/pilot-failure.json'] = encode(run)
    return baseline


def unicode_fixture():
    """Consistent non-ASCII ancestor, with cmd ASCII batch fallback retained."""
    context, members = completed_fixture(cwd_output=b'?\r\n')
    for name, data in tuple(members.items()):
        replacement = b'Fixt?re' if name.endswith('generated-direct.cmd.bin') else 'Fixtüre'.encode('utf-8')
        members[name] = data.replace(b'Fixture', replacement)
    for name in tuple(members):
        if not name.startswith('pilot/') or not name.endswith('.json'):
            continue
        value = decode(members[name])
        rows = value.get('Cases', [value] if 'Case' in value else [])
        for row in rows:
            kind, receipt = row['Case'], row['Launcher']
            numbers, identities = receipt['Numbers'], receipt['Identities']
            base = 'pilot/' + kind + '/'
            if 'capture_environment.txt_advertised_bytes' in numbers:
                size = len(members[base + 'environment.txt'])
                numbers.update({'capture_environment.txt_advertised_bytes': size, 'capture_environment.txt_copied_bytes': size})
            if kind == 'cmd' and 'pilot_cmd_batch_capture_confirmed' in numbers:
                data = members[base + 'generated-direct.cmd.bin']
                for label in ('pilot_cmd_batch_source', 'pilot_cmd_batch_readback'):
                    numbers[label + '_advertised_bytes'] = numbers[label + '_bytes'] = len(data)
                    identities[label + '_sha256'] = digest(data)
                numbers['pilot_cmd_batch_destination_bytes'] = len(data)
                identities['pilot_cmd_batch_destination_sha256'] = digest(data)
            if kind == 'cmd-cwd' and 'pilot_cmd_observation_raw_complete' in numbers:
                numbers.update(pilot_cmd_observation_expected_supported=0, pilot_cmd_observation_expected_bytes=-1,
                               pilot_cmd_observation_stdout_matches=0)
                identities.pop('pilot_cmd_observation_expected_sha256')
                row.update(Status='cmd_cwd_expected_encoding_unsupported', CmdCwdObserved=False)
        members[name] = encode(value)
    return reseal(context, members)
