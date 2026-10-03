"""Hermetic metadata receipt and collector contracts; no network or credentials."""
from dataclasses import asdict, replace
import json
import unittest

from rc_pretag_types import ContractError, MAX_JSON_BYTES, decode, encode, parse_json
from rc_release_policy import GATE_IDS
from rc_pretag_metadata_fixtures import (BEGIN, END, REQUEST, SOURCE, TREE_SHAS,
    FixtureAPI, FixtureResponse, commits, jobs, receipt, reviews, run)
from rc_pretag_metadata_types import (ENGINEERING_REF, MetadataError, MetadataObservation,
                                    MetadataReceipt, MetadataRecord, MetadataRequest)


class MetadataTypeTests(unittest.TestCase):
    def test_roundtrip_is_unverified_and_blocked(self):
        item = receipt()
        self.assertEqual(item, parse_json(MetadataReceipt, encode(item)))
        self.assertEqual(item.evidence_authentication, 'unverified')
        self.assertEqual(item.eligibility_status, 'blocked')
        self.assertEqual(item.policy_gates, GATE_IDS)
        self.assertEqual(item.principal_permissions, 'unproven')

    def test_all_false_guards_reject_true_and_nonbool(self):
        for key in ('artifact_bytes_verified', 'finalized', 'release_approved',
                    'publish_approved', 'snapshot_atomic'):
            for value in (True, 0, 1, None, 'false'):
                with self.subTest(key=key, value=value), self.assertRaises(ContractError):
                    replace(receipt(), **{key: value})

    def test_authority_strings_cannot_change(self):
        for key in ('schema', 'evidence_authentication', 'eligibility_status',
                    'blocker', 'principal_permissions'):
            with self.subTest(key=key), self.assertRaises(ContractError):
                replace(receipt(), **{key: 'approved'})

    def test_every_policy_row_is_mandatory_and_ordered(self):
        for gates in (GATE_IDS[:-1], tuple(reversed(GATE_IDS)), GATE_IDS + ('extra',), list(GATE_IDS)):
            with self.subTest(gates=gates), self.assertRaises(ContractError):
                replace(receipt(), policy_gates=gates)

    def test_strict_json_rejects_missing_extra_duplicate(self):
        value = asdict(receipt())
        value.pop('snapshot_atomic')
        with self.assertRaises(ContractError):
            parse_json(MetadataReceipt, json.dumps(value).encode())
        value = asdict(receipt())
        value['producer'] = 'trusted'
        with self.assertRaises(ContractError):
            parse_json(MetadataReceipt, json.dumps(value).encode())
        raw = encode(receipt()).replace(b'"schema":', b'"schema":"x","schema":')
        with self.assertRaisesRegex(ContractError, 'duplicate_json_key'):
            parse_json(MetadataReceipt, raw)

    def test_nonfinite_oversized_and_invalid_utf8(self):
        for raw in (b'{"x":NaN}', b'{"x":Infinity}', b'\xff', b' ' * (MAX_JSON_BYTES + 1)):
            with self.subTest(raw=raw[:20]), self.assertRaises(ContractError):
                parse_json(MetadataReceipt, raw)

    def test_request_accepts_only_narrow_branch_grammar(self):
        self.assertEqual(MetadataRequest(SOURCE, ENGINEERING_REF).source_ref, ENGINEERING_REF)
        MetadataRequest(SOURCE, 'refs/heads/release/full-rc-candidate-test_1.2')
        for value in ('refs/heads/main', 'refs/tags/v1.2.3-rc.7', ENGINEERING_REF + '/',
                      ENGINEERING_REF + '\n', ENGINEERING_REF + '%2f',
                      'refs/heads/release/full-rc-candidate-x..y',
                      'refs/heads/release/full-rc-candidate-x.',
                      'refs/heads/release/full-rc-candidate-' + 'a' * 81):
            with self.subTest(value=value), self.assertRaises(ContractError):
                MetadataRequest(SOURCE, value)

    def test_source_type_is_exact_and_version_is_an_expectation(self):
        with self.assertRaises(ContractError):
            MetadataRequest(asdict(SOURCE), ENGINEERING_REF)
        other = MetadataRequest(replace(SOURCE, version='8.9.10-rc.11'), ENGINEERING_REF)
        self.assertEqual(other.source.version, '8.9.10-rc.11')
        self.assertFalse(hasattr(other, 'version_verified'))

    def test_ids_counts_booleans_and_out_of_range_rejected(self):
        for key in ('repository_id', 'workflow_id', 'run_id', 'run_attempt', 'run_number', 'reviewer_id'):
            for value in (True, False, 0, -1, 2**63, '1'):
                with self.subTest(key=key, value=value), self.assertRaises(ContractError):
                    MetadataRecord('run', '1', **{key: value})
        for key, value in (('commit_count', True), ('merged', 1), ('record_id', True),
                           ('record_id', '01'), ('record_id', str(2**63))):
            with self.subTest(key=key), self.assertRaises(ContractError):
                MetadataRecord(**({'resource': 'run', 'record_id': '1'} | {key: value}))

    def test_remote_text_never_allowed_in_record_fields(self):
        for key in ('resource', 'record_id', 'name', 'state', 'conclusion', 'event', 'ref'):
            with self.subTest(key=key), self.assertRaises(ContractError):
                MetadataRecord(**({'resource': 'run', 'record_id': '1'} | {key: 'secret\nSENTINEL'}))

    def test_unknown_state_requires_only_hash(self):
        with self.assertRaises(ContractError):
            MetadataRecord('run', '1', state='unknown')
        item = MetadataRecord('run', '1', state='unknown', detail_sha256='f' * 64)
        self.assertEqual(item.state, 'unknown')
        self.assertNotIn(b'SENTINEL', encode(item))

    def test_negative_and_pending_states_are_representable(self):
        for state, conclusion in (('queued', None), ('in_progress', None),
                                  ('completed', 'failure'), ('completed', 'cancelled'),
                                  ('completed', 'skipped')):
            item = MetadataRecord('run', '1', state=state, conclusion=conclusion)
            self.assertEqual(item, parse_json(MetadataRecord, encode(item)))

    def test_timestamps_validate_order_and_calendar(self):
        for changes in ({'started_at': END, 'completed_at': BEGIN},
                        {'created_at': END, 'updated_at': BEGIN},
                        {'submitted_at': '2026-02-30T00:00:00Z'},
                        {'started_at': '2026-10-01T00:00:00+00:00'}):
            with self.subTest(changes=changes), self.assertRaises(ContractError):
                MetadataRecord('run', '1', **changes)

    def test_observation_inventory_limits_and_duplicate_id(self):
        item = MetadataRecord('run', '1')
        for count, values in ((True, ()), (-1, ()), (1001, ()),
                              (0, (item,)), (2, (item, item))):
            with self.subTest(count=count), self.assertRaises(ContractError):
                MetadataObservation('integration_runs', 'observed', 'observed', count, 'f' * 64, values)

    def test_observation_requires_known_key_reason_and_digest(self):
        for changes in ({'key': 'artifacts'}, {'state': 'passed'}, {'reason': 'raw_remote_text'},
                        {'comparison_sha256': None}):
            with self.subTest(changes=changes), self.assertRaises(ContractError):
                replace(receipt().observations[0], **changes)

    def test_collection_counters_channel_and_times_are_bounded(self):
        for changes in ({'request_count': True}, {'request_count': 129}, {'response_bytes': -1},
                        {'response_bytes': 16 * 1024**2 + 1}, {'channel': 'authenticated'},
                        {'started_at': END, 'ended_at': BEGIN},
                        {'collection_status': 'observed_complete'},
                        {'observations': receipt().observations * 2}):
            with self.subTest(changes=changes), self.assertRaises(ContractError):
                replace(receipt(), **changes)

    def test_frozen_dataclasses_and_nested_codec_validation(self):
        item = receipt()
        with self.assertRaises(AttributeError):
            item.release_approved = True
        object.__setattr__(item, 'release_approved', True)
        with self.assertRaises(ContractError):
            encode(item)

    def test_error_never_echoes_unknown_input(self):
        self.assertEqual(str(MetadataError('observed')), 'observed')
        self.assertEqual(str(MetadataError('TOKEN_SENTINEL')), 'invalid_metadata')
        self.assertEqual(str(MetadataError({'error': 'SENTINEL'})), 'invalid_metadata')

    def test_nested_missing_extra_and_wrong_source_type(self):
        for change in ('missing', 'extra', 'wrong_type'):
            value = json.loads(encode(receipt()))
            if change == 'missing':
                del value['request']['source']['source_tree']
            elif change == 'extra':
                value['request']['source']['version_verified'] = True
            else:
                value['request']['source']['repository_id'] = True
            with self.subTest(change=change), self.assertRaises(ContractError):
                parse_json(MetadataReceipt, json.dumps(value).encode())

    def test_json_depth_array_and_string_boundaries(self):
        for value in ({'x': 'a' * 513}, {'x': [None] * 129}, {'x': {str(i): i for i in range(129)}}):
            with self.subTest(kind=type(value['x'])), self.assertRaises(ContractError):
                parse_json(MetadataReceipt, json.dumps(value).encode())
        value = None
        for _ in range(18):
            value = [value]
        with self.assertRaisesRegex(ContractError, 'json_depth_limit'):
            parse_json(MetadataReceipt, json.dumps(value).encode())

    def test_hash_lengths_case_and_types(self):
        for key in ('source_sha', 'source_tree', 'workflow_blob', 'reviewed_sha', 'head_sha',
                    'base_sha', 'merge_sha', 'detail_sha256'):
            for value in ('A' * 40, 'a' * 39, True, 123):
                with self.subTest(key=key, value=value), self.assertRaises(ContractError):
                    MetadataRecord('run', '1', **{key: value})

    def test_every_review_state_remains_unverified(self):
        for state in ('APPROVED', 'DISMISSED', 'CHANGES_REQUESTED', 'PENDING', 'COMMENTED'):
            row = MetadataRecord('review', '7', reviewer_id=70, state=state,
                                 reviewed_sha=SOURCE.source_sha, submitted_at=END)
            observation = MetadataObservation('reviews', 'observed', 'observed', 1, 'f' * 64, (row,))
            item = replace(receipt(), observations=(observation,))
            self.assertEqual(item.evidence_authentication, 'unverified')
            self.assertFalse(item.release_approved)

    def test_incomplete_observation_can_preserve_safe_facts(self):
        prior = receipt().observations[0]
        for state in ('missing', 'inaccessible', 'invalid', 'unsupported', 'changed',
                      'prerequisite_unavailable'):
            row = replace(prior, state=state, reason='snapshot_changed')
            self.assertEqual(row.records, prior.records)
            self.assertEqual(parse_json(MetadataObservation, encode(row)), row)

    def test_empty_or_large_inventory_counts_are_not_fake_rows(self):
        empty = MetadataObservation('integration_runs', 'missing', 'no_exact_source_run', 0, 'f' * 64)
        inventory = MetadataObservation('integration_runs', 'observed', 'observed', 999, 'a' * 64)
        self.assertEqual(empty.records, ())
        self.assertEqual(inventory.records, ())
        self.assertEqual(inventory.count, 999)


class MetadataCollectorTests(unittest.TestCase):
    def collect(self, transform=None):
        from rc_pretag_metadata import collect_metadata
        api = FixtureAPI(transform)
        result = collect_metadata(REQUEST, api)
        self.assertTrue(api.closed)
        self.assertEqual(result.evidence_authentication, 'unverified')
        self.assertFalse(result.release_approved)
        self.assertFalse(result.finalized)
        self.assertEqual(result.policy_gates, GATE_IDS)
        return result, {row.key: row for row in result.observations}, api

    def changed_response(self, operation, change, key=None, target=None):
        def transform(op, args, occurrence, value):
            if op == operation and (key is None or args.get(key) == target):
                change(value)
            return value
        return transform

    def test_complete_metadata_is_still_blocked_release(self):
        result, rows, api = self.collect()
        self.assertEqual(result.collection_status, 'observed_complete')
        self.assertEqual(result.channel, 'synthetic')
        self.assertEqual(rows['integration_jobs'].count, 7)
        self.assertEqual(rows['final_jobs'].count, 13)
        self.assertEqual(rows['integration_run'].records[0].run_attempt, 3)
        self.assertEqual(result.eligibility_status, 'blocked')
        self.assertEqual(result, parse_json(MetadataReceipt, encode(result)))
        self.assertEqual(sum(op == 'repository' for op, _ in api.calls), 2)

    def test_source_repository_ref_commit_and_tree_mismatch(self):
        cases = [('repository', lambda v: v.update(id=1)),
                 ('repository', lambda v: v.update(full_name='Other/repo')),
                 ('ref', lambda v: v['object'].update(type='tag')),
                 ('ref', lambda v: v['object'].update(sha='1' * 40)),
                 ('ref', lambda v: v.update(ref='refs/heads/main')),
                 ('commit', lambda v: v.update(sha='1' * 40)),
                 ('commit', lambda v: v['tree'].update(sha='1' * 40)),
                 ('tree', lambda v: v.update(sha='1' * 40)),
                 ('tree', lambda v: v.update(truncated=True))]
        for op, change in cases:
            with self.subTest(op=op):
                result, rows, api = self.collect(self.changed_response(op, change))
                self.assertEqual(result.collection_status, 'blocked')
                self.assertEqual(rows['integration_workflow'].reason, 'prerequisite_unavailable')
                self.assertTrue(any(name == 'pr' for name, _ in api.calls))

    def test_tree_duplicate_names_symlinks_and_bad_parent_mode(self):
        for sha, change in ((TREE_SHAS[0], lambda v: v['tree'].append(dict(v['tree'][0]))),
                           (TREE_SHAS[0], lambda v: v['tree'][0].update(mode='100644')),
                           (TREE_SHAS[2], lambda v: v['tree'][0].update(mode='120000'))):
            with self.subTest(sha=sha):
                result, _, _ = self.collect(self.changed_response('tree', change, 'sha', sha))
                self.assertEqual(result.collection_status, 'blocked')

    def test_missing_pretag_file_is_truthful(self):
        _, rows, _ = self.collect(self.changed_response('tree', lambda v: v['tree'].pop(), 'sha', TREE_SHAS[2]))
        self.assertEqual(rows['pretag_workflow'].reason, 'workflow_missing')
        self.assertEqual(rows['pretag_workflow'].records, ())

    def test_workflow_path_and_id_are_strict(self):
        for change in (lambda v: v.update(id=True), lambda v: v.update(path='evil.yml')):
            with self.subTest(change=change):
                _, rows, _ = self.collect(self.changed_response('workflow', change, 'role', 'integration'))
                self.assertEqual(rows['integration_workflow'].reason, 'workflow_mismatch')

    def test_no_source_run_never_fabricates_a_run(self):
        _, rows, api = self.collect(self.changed_response('runs',
            lambda v: v.update(total_count=0, workflow_runs=[]), 'workflow_id', 201))
        self.assertEqual(rows['final_run'].reason, 'no_exact_source_run')
        self.assertEqual(rows['final_run'].records, ())
        self.assertFalse(any(op == 'jobs' and args['run_id'] == 200 for op, args in api.calls))

    def test_newest_pending_is_not_replaced_with_older_success(self):
        def transform(op, args, n, value):
            if op == 'runs' and args['workflow_id'] == 101:
                old = run(); old.update(id=90, run_number=11)
                pending = run(status='queued', conclusion=None)
                value.update(total_count=2, workflow_runs=[old, pending])
            if op == 'run' and args['run_id'] == 100:
                return run(status='queued', conclusion=None)
            return value
        _, rows, _ = self.collect(transform)
        self.assertEqual(rows['integration_run'].records[0].state, 'queued')
        self.assertEqual(rows['integration_run'].records[0].run_id, 100)

    def test_unknown_newest_event_is_not_filtered(self):
        def transform(op, args, n, value):
            if op == 'runs' and args['workflow_id'] == 101:
                value['workflow_runs'][0]['event'] = 'TOKEN_SENTINEL'
            if op == 'run' and args['run_id'] == 100:
                value['event'] = 'TOKEN_SENTINEL'
            return value
        result, rows, _ = self.collect(transform)
        self.assertEqual(rows['integration_run'].reason, 'unsupported_run')
        self.assertNotIn(b'TOKEN_SENTINEL', encode(result))

    def test_duplicate_run_numbers_and_time_order_are_invalid(self):
        for duplicate in (True, False):
            def change(value):
                extra = run(); extra.update(id=90, run_number=12 if duplicate else 13,
                                            created_at='2026-09-30T23:59:59Z')
                value.update(total_count=2, workflow_runs=[run(), extra])
            with self.subTest(duplicate=duplicate):
                _, rows, _ = self.collect(self.changed_response('runs', change, 'workflow_id', 101))
                self.assertEqual(rows['integration_run'].state, 'invalid')

    def test_list_and_direct_attempt_disagreement_blocks(self):
        _, rows, _ = self.collect(self.changed_response('run', lambda v: v.update(run_attempt=4), 'run_id', 100))
        self.assertEqual(rows['integration_run'].reason, 'snapshot_changed')

    def test_final_attempt_two_is_observed_as_unsupported(self):
        def transform(op, args, n, value):
            if op == 'runs' and args['workflow_id'] == 201:
                value['workflow_runs'][0]['run_attempt'] = 2
            if op == 'run' and args['run_id'] == 200:
                value['run_attempt'] = 2
            if op == 'jobs' and args['run_id'] == 200:
                return jobs('final', 2)
            return value
        _, rows, api = self.collect(transform)
        self.assertEqual(rows['final_run'].reason, 'unsupported_attempt')
        self.assertEqual(rows['final_run'].records[0].run_attempt, 2)
        self.assertTrue(any(op == 'jobs' and args.get('attempt') == 2 for op, args in api.calls))

    def test_run_missing_attempt_wrong_repo_source_or_path(self):
        changes = (lambda v: v.pop('run_attempt'), lambda v: v.update(head_sha='1' * 40),
                   lambda v: v['head_repository'].update(id=1),
                   lambda v: v.update(path=v['path'] + '@refs/heads/main'))
        for change in changes:
            with self.subTest(change=change):
                _, rows, _ = self.collect(self.changed_response('run', change, 'run_id', 100))
                self.assertEqual(rows['integration_run'].state, 'invalid')

    def test_job_identity_must_be_explicit(self):
        for field in ('head_sha', 'run_id', 'run_attempt'):
            with self.subTest(field=field):
                _, rows, _ = self.collect(self.changed_response('jobs',
                    lambda v: v['jobs'][0].pop(field), 'run_id', 100))
                self.assertEqual(rows['integration_jobs'].reason, 'source_mismatch')

    def test_missing_duplicate_and_unknown_job_names(self):
        for change in (lambda v: v.update(total_count=6, jobs=v['jobs'][:-1]),
                       lambda v: v['jobs'][0].update(name=v['jobs'][1]['name']),
                       lambda v: v['jobs'][0].update(name='PRIVATE_JOB_SENTINEL')):
            result, rows, _ = self.collect(self.changed_response('jobs', change, 'run_id', 100))
            self.assertEqual(rows['integration_jobs'].reason, 'jobs_incomplete')
            self.assertNotIn(b'PRIVATE_JOB_SENTINEL', encode(result))

    def test_failed_skipped_inprogress_jobs_are_preserved(self):
        for status, conclusion, end in (('completed', 'failure', END), ('completed', 'skipped', END),
                                        ('in_progress', None, None)):
            _, rows, _ = self.collect(self.changed_response('jobs', lambda v: v['jobs'][0].update(
                status=status, conclusion=conclusion, completed_at=end), 'run_id', 100))
            self.assertEqual(rows['integration_jobs'].records[0].state, status)
            self.assertEqual(rows['integration_jobs'].records[0].conclusion, conclusion)

    def test_counted_pages_shape_count_and_duplicates(self):
        for change in (lambda v: v.update(total_count=True), lambda v: v.update(total_count=1000),
                       lambda v: v.update(total_count=2),
                       lambda v: v.update(total_count=2, workflow_runs=v['workflow_runs'] * 2)):
            _, rows, _ = self.collect(self.changed_response('runs', change, 'workflow_id', 101))
            self.assertEqual(rows['integration_run'].state, 'invalid')

    def test_review_states_stale_commit_and_author_association_stay_facts(self):
        for state in ('DISMISSED', 'CHANGES_REQUESTED', 'PENDING', 'COMMENTED', 'APPROVED'):
            _, rows, _ = self.collect(self.changed_response('reviews', lambda v: v[0].update(
                state=state, commit_id='1' * 40, author_association='OWNER')))
            self.assertEqual(rows['reviews'].records[0].state, state)
            self.assertEqual(rows['reviews'].records[0].reviewed_sha, '1' * 40)

    def test_multiple_reviews_by_same_user_are_not_collapsed(self):
        def change(value):
            value.append(dict(value[0], id=701, state='CHANGES_REQUESTED'))
        _, rows, _ = self.collect(self.changed_response('reviews', change))
        self.assertEqual(rows['reviews'].count, 2)
        self.assertEqual(len(rows['reviews'].records), 2)

    def test_review_and_commit_duplicate_ids_rejected(self):
        for op in ('reviews', 'commits'):
            _, rows, _ = self.collect(self.changed_response(op, lambda v: v.append(dict(v[0]))))
            self.assertEqual(rows[op].reason, 'duplicate_record')

    def test_bare_arrays_do_not_accept_counted_envelopes(self):
        for op in ('reviews', 'commits'):
            def transform(name, args, n, value):
                return {'total_count': 1, 'items': value} if name == op else value
            _, rows, _ = self.collect(transform)
            self.assertEqual(rows[op].reason, 'invalid_response_shape')

    def test_commit_cap_and_count_mismatch(self):
        for count in (0, 2, 250, 251):
            _, rows, _ = self.collect(self.changed_response('pr', lambda v: v.update(commits=count)))
            self.assertIn(rows['commits'].reason, ('commit_cap', 'incomplete_pagination'))

    def test_unmerged_merge_sha_is_only_metadata(self):
        _, rows, _ = self.collect()
        self.assertFalse(rows['pr'].records[0].merged)
        self.assertEqual(rows['pr'].records[0].merge_sha, '3' * 40)

    def test_second_pass_mutations_retain_first_facts_and_block(self):
        for operation in ('ref', 'reviews', 'jobs', 'pr'):
            def transform(op, args, n, value):
                if op == operation and n == 2:
                    if op == 'ref': value['object']['sha'] = '1' * 40
                    if op == 'reviews': value[0]['state'] = 'DISMISSED'
                    if op == 'jobs': value['jobs'][0]['conclusion'] = 'failure'
                    if op == 'pr': value['merged'] = True
                return value
            result, rows, api = self.collect(transform)
            self.assertEqual(result.collection_status, 'blocked')
            self.assertIsNone(result.revalidation_sha256)
            self.assertTrue(any(row.reason == 'snapshot_changed' for row in rows.values()))
            self.assertEqual(sum(op == 'repository' for op, _ in api.calls), 2)

    def test_order_only_review_change_is_stable_but_unknown_value_change_is_not(self):
        def transform(op, args, n, value):
            if op == 'reviews':
                value.append(dict(value[0], id=701))
                if n == 2: value.reverse()
            return value
        result, _, _ = self.collect(transform)
        self.assertEqual(result.collection_status, 'observed_complete')
        def unknown(op, args, n, value):
            if op == 'reviews': value[0]['state'] = 'SECRET_' + str(n)
            return value
        result, _, _ = self.collect(unknown)
        self.assertEqual(result.collection_status, 'blocked')
        self.assertNotIn(b'SECRET_', encode(result))

    def test_permission_errors_are_not_absence_or_public_fallback(self):
        from rc_pretag_metadata_api import MetadataAPIError
        for code in ('unauthorized', 'forbidden', 'not_found_or_not_visible', 'rate_limited'):
            def transform(op, args, n, value):
                if op == 'reviews': raise MetadataAPIError(code)
                return value
            result, rows, api = self.collect(transform)
            self.assertEqual(result.collection_status, 'blocked')
            self.assertEqual(rows['reviews'].state, 'inaccessible')
            self.assertEqual(rows['reviews'].reason, code)
            self.assertEqual(sum(op == 'reviews' for op, _ in api.calls), 2)

    def test_review_129_and_1000_boundaries_do_not_truncate(self):
        for count, reason in ((129, 'review_cap'), (1000, 'pagination_limit')):
            def transform(op, args, n, value):
                if op == 'reviews':
                    start = (args['page'] - 1) * 100
                    return [dict(reviews()[0], id=1000 + i) for i in range(start, min(start + 100, count))]
                return value
            _, rows, api = self.collect(transform)
            self.assertEqual(rows['reviews'].reason, reason)
            self.assertEqual(rows['reviews'].records, ())
            self.assertTrue(all(args['page'] <= 10 for op, args in api.calls if op == 'reviews'))

    def test_full_array_without_link_requires_empty_terminal_page(self):
        def transform(op, args, n, value):
            if op == 'reviews':
                return [dict(reviews()[0], id=1000 + i) for i in range(100)] if args['page'] == 1 else []
            return value
        _, rows, api = self.collect(transform)
        self.assertEqual(rows['reviews'].count, 100)
        self.assertEqual(sum(op == 'reviews' and args['page'] == 2 for op, args in api.calls), 2)

    def test_249_commit_inventory_interior_mutation_is_detected(self):
        for mutate in (False, True):
            def transform(op, args, n, value):
                if op == 'pr': value['commits'] = 249
                if op == 'commits':
                    start = (args['page'] - 1) * 100
                    return [{'sha': format(i + (1000 if mutate and n == 2 and i == 170 else 1), '040x')}
                            for i in range(start, min(start + 100, 249))]
                return value
            result, rows, _ = self.collect(transform)
            self.assertEqual(rows['commits'].count, 249)
            self.assertEqual(rows['commits'].records, ())
            self.assertEqual(result.collection_status, 'blocked' if mutate else 'observed_complete')


if __name__ == '__main__':
    unittest.main()
