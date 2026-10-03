"""Pure synthetic artifact acceptance tests, not actual Windows fault injection."""
from copy import deepcopy
import unittest

from cmd_observation_artifact import evaluate_cmd_observation_artifact as evaluate
from cmd_observation_fixtures import (CASES, OLD_POSITIVES, RUN_NONCE, MINIMAL,
    completed_fixture, decode, encode, digest, reseal)
from cmd_observation_failure_fixtures import late_failure, unicode_fixture


REASON_CODES = {'identity', 'provenance', 'missing', 'parse', 'stage', 'commit', 'cleanup',
                'raw_mismatch', 'unsupported_encoding', 'producer_acceptance_leak'}


def put(mapping, key, value):
    mapping[key] = value


def mutate_json(members, name, operation):
    value = decode(members[name])
    operation(value)
    members[name] = encode(value)


def mutate_case(members, kind, operation):
    """Apply a semantic change to every snapshot that actually includes this row."""
    for name in tuple(members):
        if not name.startswith('pilot/') or not name.endswith('.json') or '/ownership-' in name:
            continue
        value = decode(members[name])
        if type(value) is dict and value.get('Case') == kind:
            operation(value)
        elif type(value) is dict and 'Cases' in value:
            for row in value['Cases']:
                if row['Case'] == kind:
                    operation(row)
        members[name] = encode(value)


def mutate_run(members, operation):
    for name in tuple(members):
        if name.startswith('pilot/') and name.endswith('.json'):
            value = decode(members[name])
            if type(value) is dict and 'Cases' in value:
                operation(value)
                members[name] = encode(value)


def raw_output(members, kind, stdout=None, stderr=None):
    base = 'pilot/' + kind + '/'
    for stream, value in [('stdout', stdout), ('stderr', stderr)]:
        if value is None:
            continue
        members[base + stream + '.txt'] = value
        def update(row, stream=stream, data=value):
            n, ids = row['Launcher']['Numbers'], row['Launcher']['Identities']
            for suffix in ('source', 'evidence'):
                label = 'pilot_cmd_' + stream + '_' + suffix
                n[label + '_advertised_bytes'] = n[label + '_bytes'] = len(data)
                ids[label + '_sha256'] = digest(data)
            n['capture_' + stream + '.txt_advertised_bytes'] = len(data)
            n['capture_' + stream + '.txt_copied_bytes'] = len(data)
        mutate_case(members, kind, update)
    def classify(row):
        n, ids = row['Launcher']['Numbers'], row['Launcher']['Identities']
        expected = (ids['pilot_cmd_observation_cwd'] + '\r\n').encode('ascii') if kind == 'cmd-cwd' else MINIMAL
        matched = members[base + 'stdout.txt'] == expected and not members[base + 'stderr.txt']
        n['pilot_cmd_observation_stdout_matches'] = int(members[base + 'stdout.txt'] == expected)
        n['pilot_cmd_observation_stderr_empty'] = int(not members[base + 'stderr.txt'])
        row['CmdCwdObserved' if kind == 'cmd-cwd' else 'CmdReadObserved'] = matched
        row['Status'] = ('cmd_cwd' if kind == 'cmd-cwd' else 'cmd_read_direct') + ('_raw_observed' if matched else '_raw_not_observed')
    mutate_case(members, kind, classify)
    def aggregate(run):
        slot = 8 if kind == 'cmd-cwd' else 9
        run['CmdCwdRawObservationMatched' if slot == 8 else 'CmdReadRawObservationMatched'] = (
            len(run['Cases']) > slot and run['Cases'][slot]['CmdCwdObserved' if slot == 8 else 'CmdReadObserved'])
    mutate_run(members, aggregate)


class ArtifactAcceptanceTests(unittest.TestCase):
    def assert_contract(self, result):
        self.assertEqual(result['protocol'], 'cmd-cwd-read-acceptance-v1')
        for key in ('CmdCwdObservationPassed', 'CmdReadObservationPassed', 'RunCompletionValidated',
                    'CmdCwdRawObservationMatched', 'CmdReadRawObservationMatched'):
            self.assertIs(type(result[key]), bool)
        for key in ('CwdStatus', 'ReadStatus'):
            self.assertIn(result[key], ('accepted', 'not_matched', 'incomplete', 'inconsistent'))
        self.assertLessEqual(len(result['Reasons']), 64)
        for reason in result['Reasons']:
            self.assertEqual(set(reason), {'code', 'case', 'member'})
            self.assertIn(reason['code'], REASON_CODES)

    def evaluate(self, context, members, seal=True):
        if seal:
            reseal(context, members)
        result = evaluate(context, members)
        self.assert_contract(result)
        return result

    def assert_rejected(self, result, code=None):
        self.assertFalse(result['CmdCwdObservationPassed'])
        self.assertFalse(result['CmdReadObservationPassed'])
        if code:
            self.assertIn(code, [reason['code'] for reason in result['Reasons']])

    def test_completed_stage_aware_fixture_and_unchanged_input(self):
        context, members = completed_fixture()
        before = deepcopy((context, members))
        result = self.evaluate(context, members, False)
        self.assertTrue(result['RunCompletionValidated'])
        self.assertTrue(result['CmdCwdObservationPassed'])
        self.assertTrue(result['CmdReadObservationPassed'])
        self.assertEqual(result['Reasons'], [])
        self.assertEqual((context, members), before)
        self.assertIn(b'state=pending\n', members['pilot/completed-' + RUN_NONCE + '.txt'])
        for count in (1, 2):
            matrix = decode(members['pilot/matrix-0' + str(count) + '.json'])
            self.assertEqual(matrix['OrdinaryControlPassed'], count > 1)
            self.assertFalse(matrix['ReferenceRoutePassed'])
        for key in OLD_POSITIVES[2:]:
            self.assertFalse(decode(members['pilot/pilot-result.json'])[key])

    def test_complete_optional_no_allocation_rows(self):
        for missing in (('node',), ('powershell',), ('pwsh',), ('node', 'powershell', 'pwsh'), ('cmd',)):
            with self.subTest(missing=missing):
                context, members = completed_fixture(optional_missing=missing)
                result = self.evaluate(context, members)
                self.assertEqual(result['CmdCwdObservationPassed'], 'cmd' not in missing)
                self.assertEqual(result['CmdReadObservationPassed'], 'cmd' not in missing)
                self.assertTrue(result['RunCompletionValidated'])

    def test_non_ascii_cwd_is_unsupported_without_blocking_type(self):
        context, members = unicode_fixture()
        result = self.evaluate(context, members)
        self.assertFalse(result['CmdCwdObservationPassed'])
        self.assertTrue(result['CmdReadObservationPassed'])
        self.assertTrue(result['RunCompletionValidated'])
        self.assertIn('unsupported_encoding', [reason['code'] for reason in result['Reasons']])

    def test_clean_cwd_mismatch_does_not_block_type(self):
        for output in (b'', b'C:\\wrong\r\n', b'\xef\xbb\xbfC:\\wrong\r\n', b'wrong\n', b'wrong\r', b'wrong\r\nextra', b'\0'):
            with self.subTest(output=output):
                context, members = completed_fixture(cwd_output=output)
                result = self.evaluate(context, members)
                self.assertFalse(result['CmdCwdObservationPassed'])
                self.assertEqual(result['CwdStatus'], 'not_matched')
                self.assertTrue(result['CmdReadObservationPassed'])
                self.assertTrue(result['RunCompletionValidated'])

    def test_each_minimal_payload_byte_and_framing_mismatch(self):
        values = [MINIMAL[:i] + bytes([MINIMAL[i] ^ 1]) + MINIMAL[i + 1:] for i in range(len(MINIMAL))]
        values += [MINIMAL + b'\0', MINIMAL[:-1], b'\xef\xbb\xbf' + MINIMAL, b'', b'exit 23\n']
        for value in values:
            with self.subTest(value=value):
                context, members = completed_fixture()
                raw_output(members, 'cmd-read-direct', stdout=value)
                result = self.evaluate(context, members)
                self.assertEqual(result['ReadStatus'], 'not_matched')
                self.assertTrue(result['CmdCwdObservationPassed'])
                self.assertFalse(result['CmdReadObservationPassed'])

    def test_stderr_nonempty_is_independent_mismatch(self):
        for kind, tag, other in [('cmd-cwd', 'Cwd', 'Read'), ('cmd-read-direct', 'Read', 'Cwd')]:
            context, members = completed_fixture()
            raw_output(members, kind, stderr=b'error\r\n')
            result = self.evaluate(context, members)
            self.assertEqual(result[tag + 'Status'], 'not_matched')
            self.assertTrue(result['Cmd' + other + 'ObservationPassed'])

    def test_trusted_identity_and_provenance_fields_fail_closed(self):
        changes = dict(repository='other/repo', workflow_path='other.yml', artifact_name='other',
                       commit='4' * 40, tree='4' * 40, run_head_sha='4' * 40, run_id=True,
                       job_id=0, artifact_id=-1, run_attempt='1', artifact_size=0, artifact_sha256='G' * 64,
                       artifact_crc_verified=False, manifest_verified=1, member_set_complete=False,
                       required_setup_and_capture_verified=False, job_terminal_state='cancelled')
        for key, value in changes.items():
            with self.subTest(key=key):
                context, members = completed_fixture()
                context[key] = value
                self.assert_rejected(self.evaluate(context, members, False))
        for terminal in ('success', 'failure'):
            context, members = completed_fixture()
            context['job_terminal_state'] = terminal
            self.assertTrue(self.evaluate(context, members)['CmdReadObservationPassed'])

    def test_missing_corrupt_or_truncated_required_members(self):
        paths = ('source.txt', 'foundation/control-receipt.txt', 'selected-parent-preflight.json',
                 'pilot/pilot-result.json', 'pilot/matrix-01.json', 'pilot/matrix-10.json',
                 'pilot/cmd-cwd/case.json', 'pilot/cmd-cwd/stdout.txt', 'pilot/cmd-read-direct/generated-direct.cmd.bin',
                 'pilot/preconditions-' + RUN_NONCE + '.json', 'pilot/completed-' + RUN_NONCE + '.txt')
        for path in paths:
            for mode in ('missing', 'truncated'):
                with self.subTest(path=path, mode=mode):
                    context, members = completed_fixture()
                    if mode == 'missing':
                        members.pop(path)
                    else:
                        members[path] = members[path][:len(members[path]) // 2]
                    self.assert_rejected(self.evaluate(context, members))

    def test_strict_json_types_duplicates_nonfinite_and_acceptance_leaks(self):
        path = 'pilot/cmd-cwd/case.json'
        for payload in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b'[]', b'null', b'{', b'\xff'):
            with self.subTest(payload=payload):
                context, members = completed_fixture()
                members[path] = payload
                self.assert_rejected(self.evaluate(context, members), 'parse')
        for name in ('CmdCwdObservationPassed', 'CmdReadObservationPassed', 'NestedObservationPassed'):
            context, members = completed_fixture()
            mutate_json(members, path, lambda row: row.update({name: True}))
            self.assert_rejected(self.evaluate(context, members), 'producer_acceptance_leak')
        for field, value in [('Fatal', 0), ('AuthorityObserved', 'true'), ('Unexpected', False)]:
            context, members = completed_fixture()
            mutate_json(members, path, lambda row: row.update({field: value}))
            self.assert_rejected(self.evaluate(context, members), 'parse')

    def test_bom_allowlist_and_non_utf8(self):
        wrappers = ('source.txt', 'fixture-binaries-sha256.txt', 'pilot/preparation-premise.json',
                    'runtime/runtime-inventory.json', 'runtime/runtime-copy-sha256.txt')
        for path in wrappers:
            context, members = completed_fixture()
            members[path] = b'\xef\xbb\xbf' + members[path]
            self.assertTrue(self.evaluate(context, members)['CmdCwdObservationPassed'])
        for path in wrappers + ('selected-parent-preflight.json', 'pilot/cmd-cwd/case.json'):
            context, members = completed_fixture()
            members[path] = b'\xff\xfe' + members[path]
            self.assert_rejected(self.evaluate(context, members))
        context, members = completed_fixture()
        members['selected-parent-preflight.json'] = b'\xef\xbb\xbf' + members['selected-parent-preflight.json']
        self.assert_rejected(self.evaluate(context, members), 'parse')

    def test_member_paths_hashes_manifest_self_and_aliases(self):
        for name in ('/absolute', '../escape', 'pilot/../escape', 'pilot\\case', 'C:/escape', 'pilot//case', 'pilot/case.', 'SOURCE.TXT'):
            context, members = completed_fixture()
            members[name] = b'x'
            self.assert_rejected(self.evaluate(context, members), 'provenance')
        for mode in ('hash', 'unlisted', 'manifest_self', 'duplicate', 'wrong_prefix', 'mixed_prefix'):
            with self.subTest(mode=mode):
                context, members = completed_fixture()
                manifest = 'evidence-sha256.txt'
                if mode == 'hash':
                    context['member_sha256']['source.txt'] = '0' * 64
                elif mode == 'unlisted':
                    members['unlisted.bin'] = b'x'
                    context['member_sha256']['unlisted.bin'] = digest(b'x')
                else:
                    line = members[manifest].splitlines()[0] + b'\r\n'
                    if mode == 'manifest_self':
                        members[manifest] += (digest(members[manifest]) + ' evidence\\evidence-sha256.txt\r\n').encode()
                    elif mode == 'duplicate':
                        members[manifest] += line
                    else:
                        members[manifest] = members[manifest].replace(b'evidence\\', b'outer\\' if mode == 'wrong_prefix' else b'evidence/extra\\', 1)
                    context['member_sha256'][manifest] = digest(members[manifest])
                self.assert_rejected(self.evaluate(context, members, False), 'provenance')

    def test_journal_binding_order_and_conflicts(self):
        path = 'pilot/completed-' + RUN_NONCE + '.txt'
        mutations = [(b'state=pending', b'state=completed'), (b'label=run', b'label=cmd-cwd'),
                     (RUN_NONCE.encode(), b'a' * 32), (b'planned_profile=none', b'planned_profile=other')]
        for before, after in mutations:
            context, members = completed_fixture()
            members[path] = members[path].replace(before, after)
            self.assert_rejected(self.evaluate(context, members), 'commit')
        for extra in (b'\n', b'nonce=' + RUN_NONCE.encode() + b'\n'):
            context, members = completed_fixture()
            members[path] += extra
            self.assert_rejected(self.evaluate(context, members), 'commit')
        for name in ('pilot/cleanup-uncertain.txt', 'pilot/completed-' + 'a' * 32 + '.txt'):
            context, members = completed_fixture()
            members[name] = members[path]
            self.assert_rejected(self.evaluate(context, members), 'commit')
        context, members = completed_fixture()
        mutate_json(members, 'pilot/matrix-01.json', lambda run: run.update(OrdinaryControlPassed=True))
        self.assert_rejected(self.evaluate(context, members), 'stage')

    def test_authority_stdio_raw_and_cleanup_mutations(self):
        changes = [('AuthorityObserved', False), ('PreResumeReady', False), ('OutsideUnchanged', False),
                   ('OutsideWriteAbsent', False), ('NetworkDenialProven', True), ('CmdExit23Observed', True)]
        launcher = [('TokenVerified', True), ('Created', False), ('CreateError', 5), ('Assigned', False),
                    ('Resumed', False), ('HandleListCount', 4), ('StdioValidated', False), ('HostStdioClosed', False),
                    ('ExecutableSha256', '5' * 64), ('CommandLine', 'cmd /c type other.cmd'), ('Kind', 'powershell')]
        numbers = [('lpac_size_error', 0), ('native_lpac_ntstatus_signed', 0), ('accesscheck_mixed_granted_access_raw', 3),
                   ('duplicate_requested_level', 2), ('stdout_handle_flags', 0), ('stdout_desired_access', 0x80000000),
                   ('pilot_cmd_stdout_source_close_confirmed', 0), ('pilot_cmd_stdout_evidence_bytes', 1),
                   ('pilot_cmd_observation_raw_complete', 0), ('delete_profile_hresult', 5)]
        for area, entries in [(None, changes), ('Launcher', launcher), ('Numbers', numbers)]:
            for key, value in entries:
                with self.subTest(area=area, key=key):
                    context, members = completed_fixture()
                    def mutation(row):
                        target = row if area is None else row['Launcher'] if area == 'Launcher' else row['Launcher']['Numbers']
                        target[key] = value
                    mutate_case(members, 'cmd-cwd', mutation)
                    result = self.evaluate(context, members)
                    self.assertFalse(result['CmdCwdObservationPassed'])

    def test_noallocation_cannot_rewrite_allocated_evidence(self):
        for kind in ('ordinary', 'reference', 'cmd-cwd', 'cmd-read-direct', 'node'):
            context, members = completed_fixture()
            mutate_case(members, kind, lambda row: row.update(NoCaseResourcesAllocated=True))
            self.assert_rejected(self.evaluate(context, members))

    def test_late_failures_keep_raw_and_old_results_without_acceptance(self):
        categories = ('case_profile_delete_false case_profile_delete_throw case_root_remove_false case_root_remove_throw '
                      'case_bind_serialize case_bind_create case_bind_write case_bind_flush case_bind_close '
                      'case_verify_pending case_binding_content case_binding_identity case_binding_read case_binding_close case_rename '
                      'case_receipt_serialize case_receipt_create case_receipt_write case_receipt_flush case_receipt_close_false case_receipt_close_throw '
                      'matrix_serialize matrix_create matrix_write matrix_flush matrix_close_false matrix_close_throw '
                      'run_root_false run_root_throw final_guard final_identity_scan selected_pin_close_false selected_pin_close_throw selected_pin_uncertain '
                      'final_result_serialize final_result_create final_result_write final_result_flush final_result_close_false final_result_close_throw '
                      'run_bind_serialize run_bind_create run_bind_write run_bind_flush run_bind_close '
                      'run_verify_pending run_binding_content run_binding_identity run_binding_read run_binding_close run_resolve_rename').split()
        for category in categories:
            with self.subTest(category=category):
                context, members = completed_fixture()
                preconditions = 'pilot/preconditions-' + RUN_NONCE + '.json'
                bound = members[preconditions]
                baseline = late_failure(members, category)
                self.assertIn('pilot/cleanup-uncertain.txt', members)
                self.assertNotIn('pilot/completed-' + RUN_NONCE + '.txt', members)
                if category in ('run_verify_pending', 'run_bind_close', 'run_bind_flush'):
                    self.assertEqual(members[preconditions], bound)
                elif category == 'run_bind_write':
                    self.assertEqual(members[preconditions], b'{"Policy":')
                elif category in ('run_bind_serialize', 'run_bind_create'):
                    self.assertNotIn(preconditions, members)
                result = self.evaluate(context, members)
                self.assert_rejected(result)
                failure = decode(members['pilot/pilot-failure.json'])
                if category == 'run_bind_close':
                    self.assertEqual(failure['Broker']['Numbers']['evidence_journal_preconditions_' + RUN_NONCE + '_close_confirmed'], 0)
                self.assertEqual({key: failure[key] for key in OLD_POSITIVES}, baseline)
                self.assertTrue(failure['CmdCwdRawObservationMatched'])
                self.assertTrue(failure['CmdReadRawObservationMatched'])
                self.assertFalse(result['RunCompletionValidated'])
                if not category.startswith('matrix_'):
                    self.assertTrue(result['CmdCwdRawObservationMatched'])
                    self.assertTrue(result['CmdReadRawObservationMatched'])
        for category in ('case_root_remove_false', 'case_receipt_close_false', 'selected_pin_close_throw', 'run_binding_close'):
            context, members = completed_fixture()
            late_failure(members, category, contradiction=True)
            result = self.evaluate(context, members)
            self.assert_rejected(result, 'commit')
            self.assertEqual(result['CwdStatus'], 'inconsistent')


    def test_size_depth_array_and_member_bounds(self):
        for kind in ('json_size', 'raw_size', 'depth', 'array', 'count', 'total'):
            with self.subTest(kind=kind):
                context, members = completed_fixture()
                if kind == 'json_size':
                    members['pilot/cmd-cwd/case.json'] = b' ' * (4 * 1024 * 1024 + 1)
                elif kind == 'raw_size':
                    raw_output(members, 'cmd-cwd', stdout=b'x' * (1024 * 1024 + 1))
                elif kind == 'depth':
                    members['pilot/extra.json'] = b'[' * 34 + b'0' + b']' * 34
                elif kind == 'array':
                    members['pilot/extra.json'] = encode([0] * 4097)
                elif kind == 'count':
                    members.update({f'extra/{i}': b'' for i in range(4097)})
                else:
                    members['large-opaque.bin'] = b'x' * (128 * 1024 * 1024)
                result = self.evaluate(context, members)
                self.assert_rejected(result)
                self.assertEqual(result['CwdStatus'], 'incomplete')

    def test_manifest_bom_slash_paths_and_raw_bytes_not_normalized(self):
        for prefix in ('evidence/', 'evidence\\'):
            context, members = completed_fixture()
            reseal(context, members, prefix)
            if prefix == 'evidence/':
                members['evidence-sha256.txt'] = members['evidence-sha256.txt'].replace(b'\\', b'/')
            members['evidence-sha256.txt'] = b'\xef\xbb\xbf' + members['evidence-sha256.txt']
            context['member_sha256']['evidence-sha256.txt'] = digest(members['evidence-sha256.txt'])
            self.assertTrue(self.evaluate(context, members, False)['CmdReadObservationPassed'])
        context, members = completed_fixture()
        value = members['pilot/cmd-cwd/stdout.txt']
        for changed in (value.lower(), value[:-2] + b'\n', value[:-1], value + b'\r\n'):
            context, members = completed_fixture()
            raw_output(members, 'cmd-cwd', stdout=changed)
            self.assertEqual(self.evaluate(context, members)['CwdStatus'], 'not_matched')

    def test_clean_nonzero_exit_and_timeout_remain_independent(self):
        for wait, exit_code in ((0, 1), (0, 23), (258, 0xffffffff)):
            context, members = completed_fixture()
            def change(row):
                row['Launcher'].update(Wait=wait, Exit=exit_code)
                if wait == 258:
                    row['Launcher']['Numbers'].pop('pilot_exit_query_success')
                row.update(CmdCwdObserved=False, ExitHex=format(exit_code, '08X'),
                           Status='deadline_exceeded' if wait == 258 else 'cmd_cwd_raw_not_observed')
            mutate_case(members, 'cmd-cwd', change)
            mutate_run(members, lambda run: run.update(CmdCwdRawObservationMatched=False))
            result = self.evaluate(context, members)
            self.assertEqual(result['CwdStatus'], 'not_matched')
            self.assertTrue(result['CmdReadObservationPassed'])

    def test_old_aggregates_cannot_claim_unsupported_success(self):
        for key in OLD_POSITIVES[2:]:
            context, members = completed_fixture()
            mutate_run(members, lambda run: run.update({key: True}))
            self.assert_rejected(self.evaluate(context, members))

    def test_required_identity_and_batch_proofs(self):
        values = {'pilot_owned_parent_identity': '7:0:999', 'pilot_owned_root_identity': '1:0:0',
                  'pilot_cmd_observation_protocol': 'unknown', 'pilot_cmd_observation_cwd': 'relative',
                  'pilot_cmd_observation_stage': 'before_resume', 'pilot_original_cmd_sha256': '0' * 64,
                  'pilot_cmd_stdout_source': '9' * 4301 + ':0:1', 'pilot_cmd_stdout_evidence': '1:0:0',
                  'pilot_cmd_batch_stage': 'after_create', 'pilot_cmd_batch_source_sha256': '0' * 64,
                  'pilot_cmd_batch_readback_path': 'C:\\wrong', 'pilot_cmd_batch_destination': '1:0:0'}
        for key, value in values.items():
            context, members = completed_fixture()
            mutate_case(members, 'cmd-read-direct', lambda row: put(row['Launcher']['Identities'], key, value))
            self.assertFalse(self.evaluate(context, members)['CmdReadObservationPassed'])
        for key in ('pilot_cmd_stdout_source_read_confirmed', 'pilot_exit_query_success',
                    'source_type_returned_bytes', 'accesscheck_mixed_ace_0_mask', 'pilot_cmd_batch_destination_write_confirmed'):
            context, members = completed_fixture()
            mutate_case(members, 'cmd-read-direct', lambda row: row['Launcher']['Numbers'].pop(key))
            self.assertFalse(self.evaluate(context, members)['CmdReadObservationPassed'])

    def test_each_missing_matrix_position_blocks_acceptance(self):
        for count in range(1, 11):
            context, members = completed_fixture()
            original = decode(members['pilot/pilot-result.json'])
            late_failure(members, 'matrix_write')
            for index in range(count, 11):
                members.pop('pilot/matrix-' + str(index).zfill(2) + '.json', None)
            result = self.evaluate(context, members)
            self.assert_rejected(result)
            failure = decode(members['pilot/pilot-failure.json'])
            self.assertEqual([failure[k] for k in OLD_POSITIVES], [original[k] for k in OLD_POSITIVES])

    def test_opaque_legacy_claims_cannot_supply_acceptance(self):
        context, members = completed_fixture()
        rows = decode(members['runtime/runtime-matrix.json'])
        rows[0].update(CmdCwdObservationPassed=True, CmdReadObservationPassed=True)
        members['runtime/runtime-matrix.json'] = encode(rows)
        self.assertTrue(self.evaluate(context, members)['CmdCwdObservationPassed'])
        members.pop('pilot/cmd-cwd/case.json')
        self.assert_rejected(self.evaluate(context, members))

    def test_source_descriptor_and_selected_pin_integrity(self):
        for field, value in [('accesscheck_mixed_ace_1_mask', 2), ('accesscheck_mixed_mapping_all', 1),
                             ('accesscheck_mixed_memory_0_free_completed', 0), ('duplicate_appcontainer_sid_sid_offset', 0),
                             ('source_type_required_bytes', True), ('accesscheck_world_unknown', 0)]:
            context, members = completed_fixture()
            mutate_case(members, 'cmd-cwd', lambda row: put(row['Launcher']['Numbers'], field, value))
            self.assertFalse(self.evaluate(context, members)['CmdCwdObservationPassed'])
        for field, value in [('selected_pin_0_close_confirmed', 0), ('selected_pin_3_handle_flags', 1),
                             ('selected_parent_broker_owner_token_close_confirmed', 0), ('selected_parent_ace_0_native_type', 99)]:
            context, members = completed_fixture()
            mutate_run(members, lambda run: put(run['SelectedParent']['Metadata']['Numbers'], field, value))
            self.assert_rejected(self.evaluate(context, members))


if __name__ == '__main__':
    unittest.main()
