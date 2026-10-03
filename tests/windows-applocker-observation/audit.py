#!/usr/bin/env python3
"""Thirty-two portable contracts; all decisions here are explicitly synthetic."""
import ast
import io
import json
import os
import pathlib
import re
import runpy
import stat
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BROKER = ROOT / 'tests/windows-broker-direct'
sys.path[:0] = [str(HERE), str(BROKER)]
import applocker_observation_contract as contract
import prepare_query as driver
from cmd_observation_contracts import ArtifactError
from cmd_observation_artifact import evaluate_cmd_observation_artifact as old_evaluate
from cmd_observation_fixtures import reseal
from cmd_observation_failure_fixtures import late_failure

from contract_fixtures import (
    encode, digest, fixture, identity, inspect_query, inspect_pure_source,
    inspect_reader_source, CASE, BASE, START, END, PATH, CHANNEL,
    PREDICATES, SELECTOR, QUERY, BRACKET,
)
from driver_contract_tests import check_metadata_snapshots, capture_fixed_stats

COUNTS = {}


class AppLockerAudit(unittest.TestCase):
    def setUp(self):
        self.context, self.members = fixture()
        self.raw = json.loads(self.members[contract.RAW_MEMBER])

    def variant(self, **values):
        COUNTS[self._testMethodName] = COUNTS.get(self._testMethodName, 0) + 1
        return self.subTest(**values)

    def reject_identity(self, member, section, key, values):
        for value in values:
            changed = dict(self.members)
            row = json.loads(changed[member])
            target = row['Cases'][10] if member == 'pilot/pilot-result.json' else row
            for part in section:
                target = target[part]
            target[key] = value
            changed[member] = encode(row)
            with self.variant(member=member, key=key, value=value), self.assertRaises(ArtifactError):
                identity(changed)

    def raw_check(self, value):
        return contract.validate_raw_receipt(encode(value), identity(self.members), BRACKET,
                                             self.members['applocker-observation/invocation.json'])

    def test_json_valid_and_object_local_keys(self):
        self.assertEqual(contract.strict_json(b'{"a":{"Key":1},"b":{"Key":2}}'), {'a': {'Key': 1}, 'b': {'Key': 2}})
        self.assertEqual(contract.strict_json(b'{"A":1}', expected_keys={'A'}), {'A': 1})

    def test_json_duplicate_and_ascii_collision(self):
        for data in (b'{"a":1,"a":2}', b'{"Key":1,"KEY":2}', b'{"a":{"X":1,"x":2}}'):
            with self.variant(data=data), self.assertRaises(ArtifactError): contract.strict_json(data)

    def test_json_encoding_bom_truncation(self):
        for data in (b'\xef\xbb\xbf{}', b'\xff', b'{', b'{}x', b'{"s":"\\ud800"}', b''):
            with self.variant(data=data), self.assertRaises(ArtifactError): contract.strict_json(data)

    def test_json_size_depth_array_limits(self):
        for data in (b' ' * 1048577, b'[' * 34 + b'0' + b']' * 34, encode([0] * 4097)):
            with self.variant(size=len(data)), self.assertRaises(ArtifactError): contract.strict_json(data)
        self.assertEqual(len(contract.strict_json(encode([0] * 4096))), 4096)

    def test_json_nonfinite_and_input_types(self):
        for data in (b'NaN', b'Infinity', b'-Infinity', b'1e999', '{}', None, bytearray(b'{}')):
            with self.variant(data=repr(data)), self.assertRaises(ArtifactError): contract.strict_json(data)

    def test_json_unknown_and_accepted_fields(self):
        for key in ('Unknown', 'Accepted', 'NetworkDenialProven', 'CmdRelativeBatchObservationPassed'):
            with self.variant(key=key), self.assertRaises(ArtifactError): contract.validate_bracket(encode(dict(BRACKET, **{key: True})))
            with self.variant(raw_key=key), self.assertRaises(ArtifactError): self.raw_check(dict(self.raw, **{key: True}))

    def test_time_exact_hundred_nanosecond_precision(self):
        self.assertEqual(contract.utc_ticks('2026-10-03T07:00:00.0000001Z') - contract.utc_ticks(START), 1)
        self.assertEqual(contract.utc_ticks(END) - contract.utc_ticks(START), 10000000)

    def test_time_endpoint_decisions_and_one_tick_outside(self):
        for stamp in (START, END):
            with self.variant(stamp=stamp): self.raw_check(dict(self.raw, Decision=dict(EventId=8007, Utc=stamp)))
        for stamp in ('2026-10-03T06:59:59.9999999Z', '2026-10-03T07:00:01.0000001Z'):
            with self.variant(stamp=stamp), self.assertRaises(ArtifactError):
                self.raw_check(dict(self.raw, Decision=dict(EventId=8007, Utc=stamp)))

    def test_time_calendar_timezone_and_precision_rejected(self):
        for stamp in ('2026-02-29T07:00:00.0000000Z', START[:-1], START[:-1] + '+00:00',
                      START.replace('.0000000', '.000000'), START.replace('07:00:00', '24:00:00'),
                      START.replace('2026', '0000'), START.replace('00.000', '60.000')):
            with self.variant(stamp=stamp), self.assertRaises(ArtifactError): contract.utc_ticks(stamp)

    def test_time_rollback_overflow_and_duration_types(self):
        for elapsed in (-1, 900001, True, 1.5, '1000', 2**63):
            with self.variant(elapsed=elapsed), self.assertRaises(ArtifactError):
                contract.validate_bracket(encode(dict(BRACKET, ElapsedMilliseconds=elapsed)))
        with self.assertRaises(ArtifactError): contract.validate_bracket(encode(dict(BRACKET, StartedUtc=END, EndedUtc=START)))

    def test_time_maximum_and_clock_discrepancy(self):
        contract.validate_bracket(encode(dict(BRACKET, EndedUtc='2026-10-03T07:15:00.0000000Z', ElapsedMilliseconds=900000)))
        contract.validate_bracket(encode(dict(BRACKET, ElapsedMilliseconds=3000)))
        for fields in (dict(ElapsedMilliseconds=3001), dict(EndedUtc='2026-10-03T07:15:00.0000001Z', ElapsedMilliseconds=900000)):
            with self.variant(fields=fields), self.assertRaises(ArtifactError): contract.validate_bracket(encode(dict(BRACKET, **fields)))

    def test_identity_literal_pid_path_payload_and_hashes(self):
        actual = identity(self.members)
        self.assertEqual((actual['TargetPid'], actual['TargetPath']), (4242, PATH))
        self.assertEqual(self.members[BASE + 'generated-direct.cmd.bin'], bytes.fromhex('657869742032330d0a'))
        self.assertEqual(digest(self.members[BASE + 'generated-direct.cmd.bin']), 'cab50bf1c23956b80d898c7af8f1c1e853e5bba6b14b8a2fbe4981d382fb7e8a')
        self.assertEqual(actual['RunSha256'], digest(self.members['pilot/pilot-result.json']))
        profile = json.loads(self.members[BASE + 'ownership-profile.json'])['Launcher']
        self.assertFalse(profile['Created'] or 'pilot_created_pid' in profile['Numbers'])
        self.assertEqual(profile['Numbers']['pilot_cmd_batch_capture_confirmed'], 1)

    def test_identity_pid_and_creation_flags(self):
        self.reject_identity(BASE + 'ownership-process.json', ['Launcher', 'Numbers'], 'pilot_created_pid', [0, -1, True, 1.5, '4242', 2147483648])
        for key, value in [('Created', False), ('CreateAttempted', False), ('Assigned', True), ('Resumed', True), ('HostStdioClosed', False)]:
            self.reject_identity(BASE + 'ownership-process.json', ['Launcher'], key, [value])
        self.reject_identity(BASE + 'ownership-process.json', ['Launcher'], 'ProfileSid', [None, '', 'S-1-5-18', 's-1-15-2-1'])
        for key in ('Created', 'CreateAttempted', 'Assigned', 'Resumed', 'StdioValidated', 'HostStdioClosed'):
            self.reject_identity(BASE + 'case.json', ['Launcher'], key, [False])

    def test_identity_case_slot_command_binary_and_nonce(self):
        self.reject_identity(BASE + 'ownership-process.json', [], 'Case', ['cmd', 'cmd-read-direct'])
        self.reject_identity('pilot/pilot-result.json', ['Launcher'], 'CommandLine', ['cmd /c direct.cmd'])
        self.reject_identity(BASE + 'case.json', ['Launcher'], 'ExecutableSha256', ['0' * 64])
        for key in ('pilot_journal_' + CASE + '_nonce', 'pilot_profile_name', 'pilot_case_id'):
            self.reject_identity(BASE + 'ownership-process.json', ['Launcher', 'Identities'], key, ['wrong'])
        changed = dict(self.members); run = json.loads(changed['pilot/pilot-result.json']); run['Cases'][9:11] = run['Cases'][9:11][::-1]
        changed['pilot/pilot-result.json'] = encode(run)
        with self.assertRaises(ArtifactError): identity(changed)

    def test_identity_capture_payload_close_and_disagreement(self):
        for key in ('pilot_cmd_batch_capture_confirmed', 'pilot_cmd_batch_source_read_confirmed',
                    'pilot_cmd_batch_readback_close_confirmed', 'pilot_cmd_batch_destination_write_confirmed'):
            self.reject_identity(BASE + 'ownership-process.json', ['Launcher', 'Numbers'], key, [0])
        self.reject_identity(BASE + 'case.json', ['Launcher', 'Numbers'], 'pilot_created_pid', [4243])
        for payload in (b'exit 23\n', b'exit 24\r\n', b'exit 23\r\nx', b''):
            changed = dict(self.members, **{BASE + 'generated-direct.cmd.bin': payload})
            with self.variant(payload=payload), self.assertRaises(ArtifactError): identity(changed)

    def test_identity_path_spelling_cwd_and_alias_traps(self):
        for key in ('pilot_owned_root_path', 'pilot_owned_parent_path', 'pilot_cmd_observation_cwd', 'pilot_cmd_batch_source_path'):
            original = json.loads(self.members[BASE + 'ownership-process.json'])['Launcher']['Identities'][key]
            self.reject_identity(BASE + 'ownership-process.json', ['Launcher', 'Identities'], key,
                                 [original.lower(), original + '\\..', original.replace('Fixture', 'Fixtüre'), original.replace('Fixture', 'Fixtu\u0308re')])

    def test_query_literal_nine_comparisons_and_structure(self):
        actual = contract.build_query(identity(self.members), BRACKET)
        inspect_query(actual)
        self.assertEqual(actual, QUERY)
        root = ET.fromstring(actual)
        self.assertEqual(([n.tag for n in root.iter()], root[0][0].text), (['QueryList', 'Query', 'Select'], SELECTOR))
        self.assertEqual(len(re.findall(r'(?:>=|<=|(?<![<>])=)', SELECTOR)), 9)

    def test_query_independent_predicate_mutations(self):
        actual = contract.build_query(identity(self.members), BRACKET)
        for predicate in PREDICATES:
            with self.variant(predicate=predicate), self.assertRaises(AssertionError):
                inspect_query(actual.replace(escape(predicate), 'true()'))

    def test_query_wrong_nested_logger_extra_selector(self):
        for before, after in [('UserData[RuleAndFileData', 'EventData[Data'), ('TargetProcessId', 'Execution/@ProcessID'),
                              ('FilePath=', 'contains(FilePath,'), ('</Query>', '<Select>*</Select></Query>')]:
            with self.variant(before=before), self.assertRaises(AssertionError): inspect_query(QUERY.replace(before, after))

    def test_query_metacharacters_unicode_and_no_normalization(self):
        original = identity(self.members)
        for bad in ("'", '"', '&', '<', '%', '*', '?', '\ud800', '\ufffe', '\uffff'):
            with self.variant(bad=repr(bad)), self.assertRaises(ArtifactError):
                contract.build_query(dict(original, TargetPath=PATH.replace('Fixture', 'Fix' + bad)), BRACKET)
        for value in ('Fixtüre', 'Fixtu\u0308re', 'fixture'):
            with self.variant(value=value):
                path = PATH.replace('Fixture', value)
                self.assertIn("FilePath='" + path + "'", ET.fromstring(contract.build_query(dict(original, TargetPath=path), BRACKET))[0][0].text)

    def test_summary_synthetic_positive_and_old_results_opaque(self):
        expected_old = old_evaluate(self.context, self.members)
        self.assertTrue(expected_old['RunCompletionValidated'])
        for event in (8005, 8006, 8007):
            with self.variant(event=event):
                self.raw['Decision']['EventId'] = event
                self.members[contract.RAW_MEMBER] = encode(self.raw); reseal(self.context, self.members)
                self.assertEqual(contract.evaluate_applocker_observation(self.context, self.members),
                                 dict(status='matched_record', reason=None, decision=self.raw['Decision']))
        for value in (None, b'{malformed', b'{"NetworkDenialProven":true}'):
            with self.variant(sibling=value):
                if value is None: self.members.pop(contract.RAW_MEMBER, None)
                else: self.members[contract.RAW_MEMBER] = value
                reseal(self.context, self.members)
                self.assertEqual(old_evaluate(self.context, self.members), expected_old)

    def test_summary_finite_reasons_and_invalid_decisions(self):
        for reason in sorted(contract.RAW_REASONS):
            with self.variant(reason=reason): self.raw_check(dict(self.raw, Status='inconclusive', Reason=reason, Decision=None))
        for changes in (dict(Reason='raw exception'), dict(Status='accepted'), dict(Decision=None),
                        dict(Decision=dict(EventId=True, Utc=START)), dict(Decision=dict(EventId=8008, Utc=START)),
                        dict(Decision=dict(EventId=8007, Utc=START, Path=PATH))):
            with self.variant(changes=changes), self.assertRaises(ArtifactError): self.raw_check(dict(self.raw, **changes))

    def test_summary_input_query_digests_and_missing_proof(self):
        for key in ('OwnershipSha256', 'CaseSha256', 'RunSha256', 'InvocationSha256', 'QuerySha256'):
            for value in (None, '0' * 64, 'A' * 64):
                with self.variant(key=key, value=value), self.assertRaises(ArtifactError): self.raw_check(dict(self.raw, **{key: value}))
        for member in ('applocker-observation/invocation.json', contract.RAW_MEMBER, BASE + 'ownership-process.json'):
            changed = dict(self.members); changed.pop(member); context, changed = reseal(dict(self.context), changed)
            with self.variant(member=member): self.assertEqual(contract.evaluate_applocker_observation(context, changed)['status'], 'inconclusive')
        pending = 'applocker-observation/observation-pending.json'
        variants = [(stage, False, pending) for stage in ('flush_failure', 'close_failure', 'rename_failure')]
        variants += [('final_and_pending', True, pending), ('missing_final', False, None),
                     ('extra_file', True, 'applocker-observation/extra.json'),
                     ('case_alias', False, 'applocker-observation/Observation.json'),
                     ('prefix_alias', False, 'AppLocker-Observation/observation.json'),
                     ('pending_alias', True, 'applocker-observation/Observation-Pending.json'),
                     ('nested_alias', True, 'applocker-observation/nested/observation.json')]
        raw_bytes = self.members[contract.RAW_MEMBER]
        self.assertEqual(self.raw_check(json.loads(raw_bytes))['Status'], 'raw_matched')
        original = old_evaluate(self.context, self.members)
        for stage, keep_final, extra in variants:
            changed = dict(self.members)
            if not keep_final:
                changed.pop(contract.RAW_MEMBER)
            if extra is not None:
                changed[extra] = raw_bytes
            context, changed = reseal(dict(self.context), changed)
            with self.variant(persistence_stage=stage):
                self.assertEqual(old_evaluate(context, changed), original)
                self.assertEqual(contract.evaluate_applocker_observation(context, changed),
                                 dict(status='inconclusive', reason='evidence_write_failed', decision=None))

    def test_summary_caller_trust_cannot_come_from_rehashed_json(self):
        for key in ('artifact_crc_verified', 'manifest_verified', 'member_set_complete', 'required_setup_and_capture_verified',
                    'run_id', 'job_id', 'run_attempt', 'artifact_id', 'commit', 'tree', 'run_head_sha'):
            context = dict(self.context); context[key] = False
            with self.variant(key=key): self.assertEqual(contract.evaluate_applocker_observation(context, self.members)['status'], 'inconclusive')
        self.members['source.txt'] = b'0' * 40 + b'\n' + b'2' * 40 + b'\n'; reseal(self.context, self.members)
        self.assertEqual(contract.evaluate_applocker_observation(self.context, self.members)['status'], 'inconclusive')

    def test_summary_all_late_and_contradictory_failures(self):
        cases = ('case_profile_delete_false case_profile_delete_throw case_root_remove_false case_root_remove_throw '
                 'case_bind_serialize case_bind_create case_bind_write case_bind_flush case_bind_close case_verify_pending '
                 'case_binding_content case_binding_identity case_binding_read case_binding_close case_rename '
                 'case_receipt_serialize case_receipt_create case_receipt_write case_receipt_flush case_receipt_close_false case_receipt_close_throw').split()
        matrices = 'matrix_serialize matrix_create matrix_write matrix_flush matrix_close_false matrix_close_throw'.split()
        runs = ('run_root_false run_root_throw final_guard final_identity_scan selected_pin_close_false selected_pin_close_throw selected_pin_uncertain '
                'final_result_serialize final_result_create final_result_write final_result_flush final_result_close_false final_result_close_throw '
                'run_bind_serialize run_bind_create run_bind_write run_bind_flush run_bind_close run_verify_pending '
                'run_binding_content run_binding_identity run_binding_read run_binding_close run_resolve_rename').split()
        variants = [(kind, target, 10, False) for target in ('cmd-read-direct', CASE) for kind in cases]
        variants += [(kind, 'cmd-read-direct', position, False) for position in (10, 11) for kind in matrices]
        variants += [(kind, 'cmd-read-direct', 10, False) for kind in runs]
        self.assertEqual(len(variants), 78)
        variants += [(kind, 'cmd-read-direct', 10, True) for kind in ('case_root_remove_false', 'case_receipt_close_false', 'selected_pin_close_throw', 'run_binding_close')]
        variants += [(kind, CASE, 10, True) for kind in ('case_root_remove_false', 'case_receipt_close_false')]
        for kind, target, position, contradiction in variants:
            context, members = fixture(); late_failure(members, kind, contradiction, target, position); reseal(context, members)
            with self.variant(kind=kind, target=target, position=position, contradiction=contradiction):
                self.assertFalse(old_evaluate(context, members)['RunCompletionValidated'])
                with mock.patch.object(contract, 'target_identity', side_effect=AssertionError('completion must gate identity')):
                    self.assertEqual(contract.evaluate_applocker_observation(context, members)['status'], 'inconclusive')
        self.assertEqual(len(variants), 84)

    def test_driver_fixed_five_reads_and_canonical_output(self):
        with mock.patch.object(driver, 'read_fixed_member', side_effect=lambda name: self.members[name]) as read:
            request = driver.prepare_request()
        self.assertEqual([call.args[0] for call in read.call_args_list], list(contract.FIXED_MEMBERS.values()))
        value = json.loads(request)
        self.assertEqual((value['TargetPid'], value['TargetPath'], value['Query']), (4242, PATH, QUERY))
        self.assertEqual(request, (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':')) + '\n').encode())
        self.assertLessEqual(len(request), 131072)

    def test_driver_regular_size_links_reparse_and_arbitrary_path(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(driver, 'EVIDENCE', pathlib.Path(temp)):
            path = pathlib.Path(temp) / contract.FIXED_MEMBERS['payload']; path.parent.mkdir(parents=True); path.write_bytes(b'exit 23\r\n')
            with capture_fixed_stats(driver, 'payload', 9):
                self.assertEqual(driver.read_fixed_member(contract.FIXED_MEMBERS['payload']), b'exit 23\r\n')
            for name in ('../source.txt', str(path), 'pilot/other/case.json'):
                with self.variant(name=name), self.assertRaises(ValueError): driver.read_fixed_member(name)
            for mode in ('oversize', 'hardlink', 'symlink', 'reparse', 'directory'):
                with self.variant(mode=mode):
                    data = path.read_bytes(); backup = path.with_name('backup')
                    if mode == 'oversize': path.write_bytes(b'x' * 10)
                    elif mode == 'hardlink': os.link(path, backup)
                    elif mode == 'directory': path.unlink(); path.mkdir()
                    info = path.lstat(); proxy = types.SimpleNamespace(**{key: getattr(info, key) for key in dir(info) if key.startswith('st_')})
                    if mode == 'symlink': proxy.st_mode = stat.S_IFLNK | 0o777
                    else: proxy.st_file_attributes = 0x400
                    real_lstat = os.lstat
                    patch = mock.patch.object(driver.os, 'lstat', side_effect=lambda item: proxy if item == path else real_lstat(item)) if mode in ('reparse', 'symlink') else mock.patch.object(driver, 'LIMITS', driver.LIMITS)
                    with patch, self.assertRaises((ValueError, OSError)): driver.read_fixed_member(contract.FIXED_MEMBERS['payload'])
                    if mode == 'directory': path.rmdir()
                    else: path.unlink()
                    if backup.exists(): backup.unlink()
                    path.write_bytes(data)
            for key, limit in [('run', 2097152), ('case', 1048576), ('ownership', 1048576), ('invocation', 4096)]:
                path = pathlib.Path(temp) / contract.FIXED_MEMBERS[key]; path.parent.mkdir(parents=True, exist_ok=True)
                self.assertEqual(driver.LIMITS[key], limit)
                for size in (limit, limit + 1):
                    with self.variant(member=key, size=size), capture_fixed_stats(driver, key, size):
                        data = b'x' * size; path.write_bytes(data)
                        if size == limit: self.assertEqual(driver.read_fixed_member(contract.FIXED_MEMBERS[key]), data)
                        else:
                            with self.assertRaises(ValueError): driver.read_fixed_member(contract.FIXED_MEMBERS[key])

    def test_driver_identity_race_read_and_close_uncertainty(self):
        real_close = os.close
        def close_uncertain(descriptor):
            real_close(descriptor)
            raise OSError('synthetic close uncertainty after test descriptor closed')
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(driver, 'EVIDENCE', pathlib.Path(temp)):
            path = pathlib.Path(temp) / contract.FIXED_MEMBERS['payload']; path.parent.mkdir(parents=True); path.write_bytes(b'exit 23\r\n')
            for failure in ('open_identity', 'read_identity', 'path_identity', 'ancestor_identity', 'short_read', 'read', 'close'):
                with self.variant(failure=failure):
                    info = path.stat(); bad = types.SimpleNamespace(**{key: getattr(info, key) for key in dir(info) if key.startswith('st_')}); bad.st_ino += 1
                    if failure in ('open_identity', 'read_identity'):
                        patch = mock.patch.object(driver.os, 'fstat', side_effect=[bad] if failure == 'open_identity' else [info, bad])
                    elif failure in ('path_identity', 'ancestor_identity'):
                        before = [item.lstat() for item in [pathlib.Path(temp), path.parent.parent, path.parent, path]]
                        after = list(before); after[-1 if failure == 'path_identity' else 0] = bad
                        patch = mock.patch.object(driver.os, 'lstat', side_effect=before + after)
                    elif failure == 'short_read': patch = mock.patch.object(driver.os, 'read', side_effect=[b'exit', b''])
                    else: patch = mock.patch.object(driver.os, failure, side_effect=close_uncertain if failure == 'close' else OSError('synthetic'))
                    with patch as operation, self.assertRaises((ValueError, OSError)): driver.read_fixed_member(contract.FIXED_MEMBERS['payload'])
        check_metadata_snapshots(self, driver)

    def test_driver_cli_import_shadowing_and_fail_closed_main(self):
        with tempfile.TemporaryDirectory() as temp:
            marker = pathlib.Path(temp) / 'executed'
            (pathlib.Path(temp) / 'applocker_observation_contract.py').write_text('open(' + repr(str(marker)) + ',"w").write("bad")')
            for arguments in ([], ['arbitrary']):
                with self.variant(arguments=arguments):
                    result = subprocess.run([sys.executable, '-I', str(HERE / 'prepare_query.py'), *arguments], cwd=temp,
                                            env=dict(os.environ, PYTHONPATH=temp), capture_output=True, timeout=10)
                    self.assertEqual((result.returncode, result.stdout, result.stderr), (2, b'', b''))
                    self.assertFalse(marker.exists())
        with mock.patch.object(driver.sys, 'flags', types.SimpleNamespace(isolated=1)), mock.patch.object(driver.sys, 'argv', ['fixed']), mock.patch.object(driver, 'prepare_request', side_effect=ValueError):
            self.assertEqual(driver.main(), 2)
        output = io.BytesIO()
        with mock.patch.object(driver.sys, 'flags', types.SimpleNamespace(isolated=1)), mock.patch.object(driver.sys, 'argv', ['fixed']), mock.patch.object(driver.sys, 'stdout', types.SimpleNamespace(buffer=output)), mock.patch.object(driver, 'prepare_request', return_value=b'{}\n'):
            self.assertEqual(driver.main(), 0)
        self.assertEqual(output.getvalue(), b'{}\n')

    def test_source_inventory_caps_and_pure_driver_functions(self):
        caps = {'observe.ps1': 450, 'contract-tests.ps1': 480, 'applocker_observation_contract.py': 450,
                'prepare_query.py': 200, 'audit.py': 480, 'contract_fixtures.py': 220, 'driver_contract_tests.py': 240}
        self.assertEqual({path.name for path in HERE.iterdir() if path.is_file()}, set(caps))
        for name, cap in caps.items():
            with self.variant(name=name): self.assertLessEqual(len((HERE / name).read_text().splitlines()), cap)
        for name, count in [('applocker_observation_contract.py', 7), ('prepare_query.py', 3), ('contract_fixtures.py', 7)]:
            tree = ast.parse((HERE / name).read_text()); self.assertEqual(sum(isinstance(node, ast.FunctionDef) for node in tree.body), count)
        helpers = {'encode', 'digest', 'fixture', 'identity', 'inspect_query', 'inspect_pure_source', 'inspect_reader_source'}
        support = ast.parse((HERE / 'contract_fixtures.py').read_text())
        audit = ast.parse((HERE / 'audit.py').read_text())
        self.assertEqual({node.name for node in support.body if isinstance(node, ast.FunctionDef)}, helpers)
        exported = next(ast.literal_eval(node.value) for node in support.body if isinstance(node, ast.Assign)
                        and any(isinstance(target, ast.Name) and target.id == '__all__' for target in node.targets))
        imported = {alias.name for node in ast.walk(audit) if isinstance(node, ast.ImportFrom)
                    and node.module == 'contract_fixtures' for alias in node.names}
        self.assertEqual(imported, set(exported))
        callers = {node.func.id for node in ast.walk(audit) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
        self.assertEqual(callers & helpers, helpers)
        test_helpers = {'check_metadata_snapshots', 'capture_fixed_stats'}
        helper_tree = ast.parse((HERE / 'driver_contract_tests.py').read_text(encoding='utf-8'))
        exported = next(ast.literal_eval(node.value) for node in helper_tree.body if isinstance(node, ast.Assign)
                        and any(isinstance(target, ast.Name) and target.id == '__all__' for target in node.targets))
        self.assertEqual(set(exported), test_helpers)
        self.assertEqual(callers & test_helpers, test_helpers)
        for name in ('applocker_observation_contract.py', 'prepare_query.py'):
            runtime = ast.parse((HERE / name).read_text())
            imports = {node.module for node in ast.walk(runtime) if isinstance(node, ast.ImportFrom)}
            imports.update(alias.name for node in ast.walk(runtime) if isinstance(node, ast.Import) for alias in node.names)
            self.assertNotIn('contract_fixtures', imports)
            self.assertNotIn('driver_contract_tests', imports)
        source = (HERE / 'applocker_observation_contract.py').read_text()
        inspect_pure_source(source)
        for forbidden in ('os', 'http.client'):
            with self.variant(import_name=forbidden), self.assertRaises(AssertionError): inspect_pure_source(source + '\nimport ' + forbidden)
        self.assertNotRegex(source, r'\b(?:open|exec|eval|__import__)\s*\(|\b(?:subprocess|socket|requests|pathlib|ctypes)\b')
        self.assertNotRegex((HERE / 'prepare_query.py').read_text(), r'\b(?:subprocess|socket|requests|ctypes|glob|rglob|walk)\b')

    def test_source_workflow_query_and_resource_mutations(self):
        workflow = (ROOT / '.github/workflows/windows-lpac-runtime-diagnostic.yml').read_text()
        pilot = '& tests/windows-broker-direct/run-pilot.ps1 -Fixture tests/windows-lpac-runtime/target/debug/windows_sandbox_fixture.exe -Payload "$env:RUNNER_TEMP/lpac-runtime-payload" -Evidence evidence/pilot -Foundation evidence/foundation'
        self.assertEqual(workflow.count(pilot), 1)
        outer = workflow.split('# APPLOCKER_OUTER_BEGIN')[1].split('# APPLOCKER_OUTER_END')[0]
        self.assertRegex(outer, r'try \{\s*' + re.escape(pilot) + r'\s*\} finally \{')
        self.assertNotRegex(outer, r'\b(?:return|exit|continue-on-error)\b')
        self.assertIn('APPLOCKER_PYTHON: ${{ steps.python.outputs.python-path }}', workflow)
        self.assertIn('python tests/windows-applocker-observation/audit.py', workflow)
        synthetic = (HERE / 'contract-tests.ps1').read_text()
        for token in ('APPLOCKER_OUTER_BEGIN', 'APPLOCKER_OUTER_END', '[scriptblock]::Create($wrapper)', 'Invoke-SyntheticPilot', 'Invoke-SyntheticLoad'):
            self.assertIn(token, synthetic)
        source = (HERE / 'observe.ps1').read_text()
        inspect_reader_source(source)
        selector = re.search(r'\$expected = "([^\n]+)"', source).group(1)
        predicates = [part.replace(START, '$($request.StartedUtc)').replace(END, '$($request.EndedUtc)').replace('4242', '$($request.TargetPid)').replace(PATH, '$($request.TargetPath)') for part in PREDICATES]
        mutations = [(selector, selector.replace(predicate, 'true()')) for predicate in predicates]
        mutations += [('$query.TolerateQueryErrors = $false', '$query.TolerateQueryErrors = $true'), ('$reader.BatchSize = 1', '$reader.BatchSize = 64')]
        mutations += [('ReadEvent([TimeSpan]::FromMilliseconds(2000))', 'ReadEvent([TimeSpan]::FromMilliseconds(3000))'),
                      ('$query.ChildNodes.Count -ne 1', '$query.ChildNodes.Count -ne 2'),
                      ('[string]::Equals($select.InnerText, $expected, [StringComparison]::Ordinal)',
                       '[string]::Equals($select.InnerText, $expected, [StringComparison]::InvariantCulture)')]
        mutations += [("'observation-pending.json'", "'observation-temp.json'"),
                      ('$stream.Flush($true)', '$stream.Flush($false)'), ('$stream.Dispose()', ''),
                      ('$stream.Flush($true)', '$stream.Flush($true)\n[IO.File]::Move($writePath, $finalPath)'),
                      ('[IO.File]::Move($writePath, $finalPath)', '[IO.File]::Move($writePath, $finalPath, $true)')]
        for before, after in mutations:
            with self.variant(mutation=after), self.assertRaises(AssertionError): inspect_reader_source(source.replace(before, after))
        self.assertNotRegex(source, r'Get-WinEvent|FormatDescription|\.ToXml\(|DllImport|Register-ObjectEvent|OpenProcess')

    def test_source_immutable_bytes_and_retained_330_identities(self):
        paths = sorted((path for path in BROKER.iterdir() if path.suffix in ('.cs', '.ps1', '.py')),
                       key=lambda path: path.name.encode('utf-8'))
        names = [path.name for path in paths]
        for flavor in (pathlib.PurePosixPath, pathlib.PureWindowsPath):
            with self.variant(path_flavor=flavor.__name__):
                self.assertEqual([path.name for path in sorted(map(flavor, reversed(names)),
                                 key=lambda path: path.name.encode('utf-8'))], names)
        windows_order = sorted(paths, key=lambda path: pathlib.PureWindowsPath(path.name))
        self.assertNotEqual([path.name for path in windows_order], names)
        wrong_order = b''.join(path.name.encode() + b'\0' + path.read_bytes() + b'\0' for path in windows_order)
        self.assertEqual(digest(wrong_order), '63118873e3239342d68542f0b775734567f3a597be9b2b5c937d2bd4bb159dab')
        immutable = b''.join(path.name.encode() + b'\0' + path.read_bytes() + b'\0' for path in paths)
        self.assertEqual((len(paths), digest(immutable)), (44, '1509f8ae681e529a732bc90d1c3e24e76ad8680ef1dd027751a6e174f10d2083'))
        entries = ['tests/windows-lpac-runtime/audit.py'] + ['tests/windows-broker-direct/' + name for name in
                   ('audit.py', 'qualification-audit.py', 'pilot-audit.py', 'parent-candidate-audit.py', 'selected-parent-audit.py', 'cmd-sentinel-audit.py', 'cmd-observations-audit.py')]
        identities = []
        for entry in entries:
            suite = unittest.defaultTestLoader.loadTestsFromModule(types.SimpleNamespace(**runpy.run_path(str(ROOT / entry))))
            stack = list(suite)
            while stack:
                item = stack.pop()
                if isinstance(item, unittest.TestSuite): stack.extend(item)
                else: identities.append(entry + ':' + item.id())
        self.assertEqual((len(identities), digest('\n'.join(sorted(identities)).encode())),
                         (330, '25223b547713c85dde0b05cc251d77a93cf0dc1dafb1b8ec28b72024a2c96686'))


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(AppLockerAudit)
    print('Discovered unittest methods:', suite.countTestCases())
    if suite.countTestCases() != 32: raise SystemExit('expected exactly 32 new methods')
    outcome = unittest.TextTestRunner(verbosity=2).run(suite)
    print('Executed unittest methods:', outcome.testsRun, '; expanded parameter variants:', sum(COUNTS.values()))
    print('Synthetic/source contracts only; no Windows event acquisition')
    raise SystemExit(not outcome.wasSuccessful())
