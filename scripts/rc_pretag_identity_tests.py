"""Strict identity/schema attacks; no real evidence collection is exercised."""
from dataclasses import asdict, FrozenInstanceError, replace
import json
import unittest

from rc_pretag_types import (ContractError, InvocationIdentity, MAX_JSON_BYTES, PreTagCandidate,
    REPOSITORY, SourceIdentity, decode, encode, parse_json)
from rc_pretag_evidence import PreTagEvidenceReceipt
from rc_pretag_fixtures import SOURCE, candidate, invocation, receipt, selected


class PreTagIdentityTests(unittest.TestCase):
    def reject_replace(self, item, **changes):
        with self.assertRaises(ContractError):
            replace(item, **changes)

    def test_candidate_and_empty_full_receipts_roundtrip(self):
        for item in (candidate(), receipt(), receipt(True)):
            self.assertEqual(parse_json(type(item), encode(item)), item)

    def test_immutable_nested_records(self):
        for item, field in ((candidate(), 'source'), (SOURCE, 'source_sha')):
            with self.assertRaises(FrozenInstanceError):
                setattr(item, field, None)
        self.assertIsInstance(receipt(True).payloads, tuple)

    def test_source_exact_repository_and_numeric_types(self):
        for field, values in {'repository': ('owner/foreign', '', None),
                              'repository_id': (True, 1360355522.0, '1360355522', 0, -1, 99)}.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    self.reject_replace(SOURCE, **{field: value})

    def test_sha_tree_canonical_lowercase_and_length(self):
        for field in ('source_sha', 'source_tree'):
            for value in ('A' * 40, 'a' * 39, 'g' * 40, True, None):
                self.reject_replace(SOURCE, **{field: value})

    def test_only_canonical_numbered_rc_versions(self):
        for value in ('1.2.3', '01.2.3-rc.1', '1.02.3-rc.1', '1.2.03-rc.1',
                      '1.2.3-rc.01', 'v1.2.3-rc.1', '1.2.3-beta.1',
                      '1.2.3-rc.1+build', '1.2.3-rc.1\n', None, True):
            self.reject_replace(SOURCE, version=value)

    def test_all_invocation_integer_fields_reject_boolean_float_string(self):
        for field in ('run_id', 'run_attempt', 'workflow_id'):
            for value in (True, False, 1.0, '1', 0, -1, 2**63):
                self.reject_replace(invocation(), **{field: value})

    def test_missing_spoofed_or_foreign_workflow_identity(self):
        item = invocation()
        for field, value in (('event', 'workflow_dispatch'), ('workflow_sha', 'f' * 40),
                ('workflow_path', '.github/workflows/rc-artifact-consumer.yml'),
                ('workflow_ref', 'foreign/' + item.workflow_ref), ('workflow_blob', None),
                ('ref', 'refs/tags/v' + SOURCE.version), ('ref', 'refs/heads/main')):
            self.reject_replace(item, **{field: value})

    def test_pretag_branch_binds_version_nonce_and_actual_shape(self):
        for ref in ('refs/heads/release/rc-pretag-9.9.9-rc.1-fixture1',
                    'refs/heads/release/rc-pretag-' + SOURCE.version + '-short',
                    'refs/heads/release/rc-pretag-' + SOURCE.version + '-a..b1234',
                    'refs/heads/release/rc-pretag-' + SOURCE.version + '-fixture1/child'):
            self.reject_replace(invocation(), ref=ref, workflow_ref=REPOSITORY + '/' +
                                invocation().workflow_path + '@' + ref)

    def test_consumer_and_integration_attempt3_remain_supported(self):
        self.assertEqual(invocation('consumer', 3).run_attempt, 3)
        self.assertEqual(selected('integration', 3).current_attempt, 3)
        self.assertEqual(receipt(True).consumer.run_attempt, 3)

    def test_final_attempt1_and_push_candidate_only(self):
        for attempt in (2, 3):
            with self.assertRaises(ContractError):
                invocation('final', attempt)
        self.reject_replace(invocation('final'), event='workflow_dispatch')
        ref = 'refs/heads/release/dot-rc-reconciliation-fixture'
        self.reject_replace(invocation('final'), ref=ref, workflow_ref=REPOSITORY + '/' +
                            invocation('final').workflow_path + '@' + ref)

    def test_consumer_push_is_not_dispatch(self):
        self.reject_replace(invocation('consumer'), event='push')

    def test_candidate_does_not_accept_tag_objects_or_bypass_modes(self):
        for field, value in (('tag_state', 'present'), ('local_tag_observation', 'present'),
                            ('prospective_tag', 'v0.6.0'), ('evidence_authentication', 'authenticated')):
            self.reject_replace(candidate(), **{field: value})
        for key in ('tag_object_sha', 'allow_missing_tag', 'skip_tag', 'approved', 'release_approved'):
            value = json.loads(encode(candidate()))
            value[key] = True
            with self.assertRaises(ContractError):
                decode(PreTagCandidate, value)

    def test_remote_absence_needs_observed_visibility_but_stays_unverified(self):
        for visibility in ('unknown', 'denied'):
            self.reject_replace(candidate(), remote_tag_observation='absent', tag_visibility=visibility)
        observed = replace(candidate(), remote_tag_observation='absent', tag_visibility='observed')
        self.assertEqual(observed.evidence_authentication, 'unverified')

    def test_clean_six_versions_gateway_and_manifest_fields(self):
        for changes in ({'clean_source_observation': 1}, {'clean_source_observation': False},
                        {'desktop_versions': (SOURCE.version,) * 5},
                        {'desktop_versions': ('9.9.9-rc.1',) * 6}, {'gateway_version': '0.1.0'},
                        {'reviewed_manifest_blob': ''}, {'reviewed_manifest_sha256': 'f' * 63},
                        {'policy_revision': 'unknown'}):
            self.reject_replace(candidate(), **changes)

    def test_candidate_invocation_source_tree_version_binding(self):
        for field, value in (('source_sha', 'f' * 40), ('source_tree', 'f' * 40), ('version', '2.0.0-rc.1')):
            other = replace(SOURCE, **{field: value})
            self.reject_replace(candidate(), invocation=invocation(source=other))

    def test_every_candidate_field_required_no_extra_keys(self):
        original = json.loads(encode(candidate()))
        for key in original:
            value = dict(original)
            del value[key]
            with self.subTest(key=key), self.assertRaises(ContractError):
                decode(PreTagCandidate, value)

    def test_json_duplicate_keys_nonfinite_and_malformed_utf8(self):
        for raw in (b'{"schema":1,"schema":1}', b'{"x":NaN}', b'{"x":Infinity}', b'\xff', b'[]'):
            with self.assertRaises(ContractError):
                parse_json(PreTagEvidenceReceipt, raw)

    def test_bounded_json_bytes_depth_arrays_strings(self):
        for raw in (b' ' * (MAX_JSON_BYTES + 1), b'[' * 100 + b']' * 100,
                    json.dumps({'x': ['a'] * 129}).encode(), json.dumps({'x': 'a' * 513}).encode()):
            with self.assertRaises(ContractError):
                parse_json(PreTagEvidenceReceipt, raw)

    def test_nested_unknown_fields_and_non_integer_schema(self):
        for path in ('candidate', 'eligibility'):
            value = json.loads(encode(receipt()))
            value[path]['authenticated'] = True
            with self.assertRaises(ContractError):
                decode(PreTagEvidenceReceipt, value)
        self.reject_replace(receipt(), schema=True)

    def test_receipt_cannot_claim_collection_success_or_finalization(self):
        for field, value in (('evidence_collection_status', 'succeeded'), ('finalized', True),
                            ('release_approved', True), ('publish_approved', True),
                            ('snapshot_atomic', True), ('draft_visibility', 'proven'),
                            ('release_collision_state', 'absent')):
            self.reject_replace(receipt(), **{field: value})

    def test_receipt_selected_source_and_role_bound(self):
        other = replace(SOURCE, source_tree='f' * 40)
        self.reject_replace(receipt(True), consumer=invocation('consumer', 3, other))
        self.reject_replace(receipt(True), consumer=invocation())
        self.reject_replace(receipt(True), integration=selected('final'))

    def test_selected_runs_current_attempt_newest_job_inventory(self):
        item = selected('integration', 3)
        for changes in ({'current_attempt': 1}, {'newest_run_id': 99},
                        {'lists_complete_observation': False}, {'jobs': item.jobs[:-1]},
                        {'jobs': item.jobs[:-1] + (item.jobs[0],)}):
            self.reject_replace(item, **changes)
        self.reject_replace(selected(), jobs=selected().jobs[:-1])

    def test_every_selected_job_source_attempt_id_and_time_binding(self):
        item = selected('integration', 3)
        for field, value in (('run_id', 999), ('run_attempt', 1), ('source_sha', 'f' * 40),
                            ('completed_at', '2026-10-01T01:00:00Z')):
            bad = replace(item.jobs[0], **{field: value})
            self.reject_replace(item, jobs=(bad,) + item.jobs[1:])
        for field, value in (('job_id', True), ('status', 'queued'), ('conclusion', 'skipped'),
                            ('name', 'renamed'), ('started_at', '2026-13-01T00:00:00Z')):
            self.reject_replace(item.jobs[0], **{field: value})

    def test_artifact_source_current_attempt_job_and_outer_digest_binding(self):
        item = receipt(True)
        for field, value in (('run_id', 123), ('job_id', 999),
                            ('created_at', '2026-10-01T00:00:00Z'),
                            ('source', replace(SOURCE, source_tree='f' * 40))):
            bad = replace(item.artifact, **{field: value})
            self.reject_replace(item, artifact=bad)
        for field, value in (('run_attempt', 2), ('size', True), ('expired', True),
                            ('api_sha256', 'f' * 64), ('authentication', 'verified')):
            self.reject_replace(item.artifact, **{field: value})

    def test_exact_four_payload_inventory_and_no_paths(self):
        item = receipt(True)
        self.reject_replace(item, payloads=item.payloads[:-1])
        self.reject_replace(item, payloads=item.payloads[:-1] + (item.payloads[0],))
        for name in ('../payload', '/tmp/token', 'https://example.com/a', 'old-version.exe'):
            payload = replace(item.payloads[0], name=name)
            self.reject_replace(item, payloads=(payload,) + item.payloads[1:])
        self.reject_replace(item, artifact=None)

    def test_structural_original_text_and_false_flags_preserved(self):
        item = receipt(True)
        self.assertTrue(item.structural.passed)
        self.assertEqual(parse_json(PreTagEvidenceReceipt, encode(item)).structural, item.structural)
        self.assertEqual(item.eligibility.status, 'blocked')
        for blockers in ((), ('resolved',), item.structural.release_blockers + ('new blocker',)):
            self.reject_replace(item.structural, release_blockers=blockers)
        self.reject_replace(item.structural, release_approved=True)
        self.reject_replace(item, structural=replace(item.structural, run_id=999))

    def test_raw_audit_findings_retained_and_counts_strict(self):
        item = receipt(True)
        self.assertEqual(item.audits[0].raw_vulnerability_count, 1)
        self.assertEqual(item.audits[0].active_vulnerability_count, 0)
        for value in (True, -1, 1.0, 1000001):
            self.reject_replace(item.audits[0], raw_vulnerability_count=value)
        self.reject_replace(item, audits=item.audits[:-1] + (item.audits[0],))



class PreTagReviewIdentityTests(unittest.TestCase):
    def test_actual_integration_pr_ref_and_event_shapes_are_bound(self):
        item = invocation('integration', 3)
        ref = 'refs/pull/36/merge'
        valid = replace(item, event='pull_request', ref=ref,
                        workflow_ref=REPOSITORY + '/' + item.workflow_path + '@' + ref)
        self.assertEqual(parse_json(InvocationIdentity, encode(valid)), valid)
        self.assertEqual(valid.run_attempt, 3)
        with self.assertRaises(ContractError):
            replace(item, event='pull_request')
        for bad_ref in ('refs/pull/0/merge', 'refs/pull/036/merge', 'refs/pull/-1/merge',
                        'refs/pull/36/head', 'refs/heads/main', 'refs/tags/v1.2.3-rc.7'):
            with self.assertRaises(ContractError):
                replace(valid, ref=bad_ref,
                        workflow_ref=REPOSITORY + '/' + item.workflow_path + '@' + bad_ref)
        for bad_event in ('push', 'workflow_dispatch'):
            with self.assertRaises(ContractError):
                replace(valid, event=bad_event)
        tag_ref = 'refs/tags/v1.2.3-rc.7'
        with self.assertRaises(ContractError):
            replace(item, ref=tag_ref, workflow_ref=REPOSITORY + '/' + item.workflow_path + '@' + tag_ref)
        self.assertEqual(replace(item, event='workflow_dispatch').run_attempt, 3)
        with self.assertRaises(ContractError):
            replace(valid, workflow_ref=item.workflow_ref)

    def test_overlong_json_integer_has_fixed_error_without_raw_parser_text(self):
        with self.assertRaisesRegex(ContractError, '^invalid_json$'):
            parse_json(PreTagCandidate, b'{"value":' + b'9' * 5000 + b'}')
        with self.assertRaisesRegex(ContractError, '^duplicate_json_key$'):
            parse_json(PreTagCandidate, b'{"x":1,"x":2}')

if __name__ == '__main__':
    unittest.main(verbosity=2)
