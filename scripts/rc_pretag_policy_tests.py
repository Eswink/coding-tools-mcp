"""Missing and forged evidence can never make this schema phase eligible."""
import ast
from dataclasses import replace
from pathlib import Path
import re
import unittest

import final_rc_evidence
import rc_consumer_contracts
import release_tag_gate
from rc_pretag_types import ContractError, PERMISSIONS, decode, encode
from rc_pretag_evidence import BLOCKERS, FINAL_JOBS, INTEGRATION_JOBS
from rc_pretag_fixtures import SOURCE, candidate, invocation, passing_claim, passing_claims, receipt, review
from rc_release_eligibility import GateObservation, ReleaseEligibility, evaluate
from rc_release_policy import (CURRENT_ISSUE_IDS, CURRENT_LEDGER_SOURCE_SHA, DEFERRED_ROWS,
                               GATES, GATE_IDS, LATER_PHASE_ROWS, OPTIONAL_OBSERVATIONS)

ROOT = Path(__file__).resolve().parents[1]


class PreTagPolicyTests(unittest.TestCase):
    def test_empty_inventory_blocks_every_required_row(self):
        value = evaluate(candidate(), ())
        self.assertEqual(tuple(row.gate_id for row in value.rows), GATE_IDS)
        self.assertTrue(all(row.status == 'unknown' and row.reason == 'missing_evidence' for row in value.rows))

    def test_all_passing_caller_claims_never_authenticate_or_approve(self):
        value = evaluate(candidate(), passing_claims())
        self.assertEqual(value.status, 'blocked')
        self.assertFalse(value.release_approved)
        self.assertFalse(value.publish_approved)
        self.assertTrue(all(row.reported_status == 'passed' and row.status == 'unknown' for row in value.rows))
        self.assertEqual(value.evidence_authentication, 'unverified')

    def test_each_required_row_missing_blocks_explicitly(self):
        for gate in GATES:
            with self.subTest(gate=gate.gate_id):
                value = evaluate(candidate(), tuple(o for o in passing_claims() if o.gate_id != gate.gate_id))
                row = next(r for r in value.rows if r.gate_id == gate.gate_id)
                self.assertEqual(row.reason, 'missing_evidence')
                self.assertEqual(value.status, 'blocked')

    def test_each_failed_unknown_and_skipped_row_blocks(self):
        for gate in GATES:
            for status in ('failed', 'unknown', 'skipped'):
                with self.subTest(gate=gate.gate_id, status=status):
                    value = evaluate(candidate(), (replace(passing_claim(gate), reported_status=status),))
                    row = next(r for r in value.rows if r.gate_id == gate.gate_id)
                    self.assertEqual(row.reason, 'reported_' + status)
                    self.assertEqual(value.status, 'blocked')

    def test_every_gate_wrong_source_and_tree_fails(self):
        for gate in GATES:
            for field in ('source_sha', 'source_tree'):
                other = replace(SOURCE, **{field: 'f' * 40})
                value = evaluate(candidate(), (replace(passing_claim(gate), source=other),))
                row = next(r for r in value.rows if r.gate_id == gate.gate_id)
                self.assertEqual((row.status, row.reason), ('failed', 'source_mismatch'))

    def test_each_gate_missing_permission_or_visibility_blocks(self):
        for gate in GATES:
            for changes, reason in (({'permissions_observed': ()}, 'permission_unproven'),
                                    ({'visibility': 'denied'}, 'visibility_unproven'),
                                    ({'visibility': 'unknown'}, 'visibility_unproven'),
                                    ({'evidence_sha256': None}, 'evidence_digest_missing')):
                value = evaluate(candidate(), (replace(passing_claim(gate), **changes),))
                row = next(r for r in value.rows if r.gate_id == gate.gate_id)
                self.assertEqual(row.reason, reason)

    def test_draft_visibility_and_review_do_not_follow_scope_label(self):
        value = evaluate(candidate(), passing_claims())
        by_id = {r.gate_id: r for r in value.rows}
        self.assertEqual(by_id['draft_visibility'].reason, 'authenticating_producer_unimplemented')
        self.assertEqual(by_id['final_independent_review'].reason, 'review_provenance_unproven')
        self.assertEqual(by_id['postmerge_integration_invocation'].status, 'unknown')
        self.assertEqual(by_id['snapshot_root_authority'].status, 'unknown')

    def test_unknown_gate_and_duplicate_row_rejected(self):
        row = passing_claim(GATES[0])
        with self.assertRaises(ContractError):
            replace(row, gate_id='extra_approved_gate')
        with self.assertRaises(ContractError):
            evaluate(candidate(), (row, row))

    def test_review_freeform_approval_string_is_not_a_receipt(self):
        row = next(o for o in passing_claims() if o.gate_id == 'final_independent_review')
        with self.assertRaises(ContractError):
            replace(row, review='approved by maintainer')
        value = evaluate(candidate(), (replace(row, review=review()),))
        self.assertEqual(next(r for r in value.rows if r.gate_id == row.gate_id).reason,
                         'review_provenance_unproven')

    def test_stale_review_head_or_postmerge_new_sha_fails(self):
        row = next(o for o in passing_claims() if o.gate_id == 'final_independent_review')
        for field in ('reviewed_sha', 'pr_head_sha', 'main_source_sha'):
            value = evaluate(candidate(), (replace(row, review=replace(review(), **{field: 'f' * 40})),))
            result = next(r for r in value.rows if r.gate_id == row.gate_id)
            self.assertEqual((result.status, result.reason), ('failed', 'review_source_mismatch'))

    def test_run_current_attempt_binding_and_positive_consumer_attempt3(self):
        row = passing_claim(GATES[0])
        for role in ('integration', 'consumer'):
            current = invocation(role, 3)
            old = invocation(role, 1)
            value = evaluate(candidate(), (replace(row, invocation=old),), (current,))
            self.assertEqual(value.rows[0].reason, 'selected_attempt_mismatch')
            value = evaluate(candidate(), (replace(row, invocation=current),), (current,))
            self.assertEqual(value.rows[0].reason, 'authenticating_producer_unimplemented')
            self.assertEqual(value.status, 'blocked')
        value = evaluate(candidate(), (replace(row, invocation=invocation('final')),))
        self.assertEqual(value.rows[0].reason, 'selected_run_missing')

    def test_pretag_invocation_and_selected_source_binding(self):
        row = passing_claim(GATES[0])
        value = evaluate(candidate(), (replace(row, invocation=replace(invocation(), run_id=999)),))
        self.assertEqual(value.rows[0].reason, 'selected_attempt_mismatch')
        other = replace(SOURCE, source_sha='f' * 40)
        with self.assertRaises(ContractError):
            evaluate(candidate(), (), (invocation('consumer', 3, other),))

    def test_no_forged_eligibility_approval_status_or_inventory(self):
        value = evaluate(candidate(), passing_claims())
        for changes in ({'status': 'eligible'}, {'release_approved': True}, {'publish_approved': True},
                        {'rows': value.rows[:-1]}, {'evidence_authentication': 'verified'}):
            with self.assertRaises(ContractError):
                replace(value, **changes)
        with self.assertRaises(ContractError):
            replace(value.rows[0], status='passed')
        with self.assertRaises(ContractError):
            replace(receipt(True), eligibility=evaluate(candidate(), ()))

    def test_complete_ledger_mapping_including_later_and_deferred(self):
        ledger = (ROOT / 'docs/releases/next-rc-ledger.md').read_text().split('## Source register')[0]
        expected = set()
        for line in ledger.splitlines():
            if line.startswith('| ') and not line.startswith('| Issue'):
                cell = line.split('|')[1]
                expected.update(re.findall(r'(?<![A-Za-z0-9])#[0-9]+|LEDGER-[A-Z0-9-]+', cell))
        covered = {row for gate in GATES for row in gate.ledger_rows}
        covered.update(row[0] for row in LATER_PHASE_ROWS + DEFERRED_ROWS)
        # The consumer baseline predates #88; also require the independently reviewed canonical ledger.
        expected.update(CURRENT_ISSUE_IDS)
        self.assertEqual(expected, covered)
        self.assertEqual({row for row in covered if row.startswith('#')}, CURRENT_ISSUE_IDS)
        self.assertEqual(len(CURRENT_ISSUE_IDS), 21)
        self.assertEqual(DEFERRED_ROWS[0][1], 'deferred')
        self.assertEqual(LATER_PHASE_ROWS[0][1], 'blocked')
        self.assertNotIn('tag_protection', GATE_IDS)
        self.assertEqual(set(OPTIONAL_OBSERVATIONS), {'tag_protection', 'platform_release_immutability'})

    def test_policy_rows_have_full_permission_identity_freshness_map(self):
        for gate in GATES:
            self.assertTrue(gate.scope and gate.endpoints and gate.artifact_contract)
            self.assertTrue(gate.visibility and gate.identity_binding and gate.completeness)
            self.assertTrue(gate.failure_semantics and gate.freshness)
            self.assertEqual(gate.verifier, 'unimplemented')
            self.assertLessEqual(set(gate.permissions), set(PERMISSIONS))
            self.assertTrue(all(path.startswith('GET /repos/Eswink/coding-tools-mcp') for path in gate.endpoints))
        for key in ('windows_execution', 'windows_denial', 'windows_cancel', 'windows_pty',
                    'windows_hooks', 'windows_snapshot', 'windows_warnings', 'snapshot_root_authority',
                    'ubuntu22_isolation', 'ubuntu24_isolation', 'installed_five_rows',
                    'raw_cloud_audit', 'raw_noncloud_audits', 'full_integration', 'final_packaging'):
            self.assertIn(key, GATE_IDS)

    def test_copied_fixed_inventories_match_unchanged_producer_contracts(self):
        self.assertEqual(FINAL_JOBS, release_tag_gate.FINAL_JOBS)
        self.assertEqual(INTEGRATION_JOBS, final_rc_evidence.REQUIRED_JOBS)
        self.assertEqual(BLOCKERS, rc_consumer_contracts.BLOCKERS)

    def test_runtime_contract_modules_have_no_io_or_execution_entrypoint(self):
        for name in ('rc_pretag_types', 'rc_pretag_evidence', 'rc_release_policy', 'rc_release_eligibility'):
            source = (ROOT / 'scripts' / (name + '.py')).read_text()
            self.assertLess(len(source.splitlines()), 500)
            parsed = ast.parse(source)
            imports = {node.module for node in ast.walk(parsed) if isinstance(node, ast.ImportFrom)}
            imports.update(alias.name for node in ast.walk(parsed) if isinstance(node, ast.Import) for alias in node.names)
            self.assertFalse(imports & {'os', 'subprocess', 'urllib', 'requests', 'pathlib', 'socket'})
            for node in ast.walk(parsed):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, ('open', 'exec', 'eval', '__import__'))
            self.assertNotIn('__main__', source)

    def test_fixture_workflow_least_privilege_fixed_actions_and_no_live_collector(self):
        source = (ROOT / '.github/workflows/rc-pretag-contract-checks.yml').read_text()
        self.assertIn('contents: read', source)
        self.assertNotIn(': write', source)
        self.assertIn('ubuntu-24.04', source)
        self.assertIn("python-version: '3.12'", source)
        self.assertIn('persist-credentials: false', source)
        for action in re.findall(r'uses: (\S+)', source):
            self.assertRegex(action, r'^[A-Za-z0-9_/-]+@[0-9a-f]{40}$')
        for forbidden in ('secrets.', 'github.token', 'GH_TOKEN', 'workflow_dispatch:',
                          'pull_request_target', 'upload-artifact', 'rc-pretag-evidence.yml'):
            self.assertNotIn(forbidden, source)



class PreTagRefinementTests(unittest.TestCase):
    def test_rc_zero_matches_existing_canonical_version_contract(self):
        self.assertIsNotNone(release_tag_gate.rc.RC_VERSION.fullmatch('1.2.3-rc.0'))
        self.assertEqual(replace(SOURCE, version='1.2.3-rc.0').version, '1.2.3-rc.0')

    def test_stale_review_source_cannot_hide_behind_matching_invocation(self):
        row = next(o for o in passing_claims() if o.gate_id == 'final_independent_review')
        current = invocation('consumer', 3)
        claim = replace(row, invocation=current, review=replace(review(), reviewed_sha='f' * 40))
        result = evaluate(candidate(), (claim,), (current,))
        finding = next(r for r in result.rows if r.gate_id == row.gate_id)
        self.assertEqual((finding.status, finding.reason), ('failed', 'review_source_mismatch'))
        self.assertFalse(result.publish_approved)

    def test_tag_absence_map_names_exact_read_and_explicit_blocked_receipt(self):
        gate = next(g for g in GATES if g.gate_id == 'tag_absence')
        self.assertIn('GET /repos/Eswink/coding-tools-mcp/git/ref/tags/{strict_tag}', gate.endpoints)
        self.assertEqual(receipt(True).eligibility_status, 'blocked')
        with self.assertRaises(ContractError):
            replace(receipt(True), eligibility_status='eligible')


class PreTagReviewCorrectionTests(unittest.TestCase):
    def test_issue88_is_explicit_later_scope_without_circular_pretag_run(self):
        self.assertEqual(CURRENT_LEDGER_SOURCE_SHA, 'e2e011f7f2a3a1df838bbd588106205b999db610')
        self.assertIn('#88', CURRENT_ISSUE_IDS)
        row = next(row for row in LATER_PHASE_ROWS if row[0] == '#88')
        self.assertEqual(row[1], 'blocked')
        self.assertIn('no circular pre-tag dependency', row[2])
        self.assertFalse(any('#88' in gate.ledger_rows for gate in GATES))
        self.assertEqual(evaluate(candidate(), ()).status, 'blocked')

    def test_negative_and_pending_review_claims_retain_explicit_outcomes(self):
        row = next(o for o in passing_claims() if o.gate_id == 'final_independent_review')
        current = invocation('consumer', 3)
        for state, status, reason in (('dismissed', 'failed', 'review_dismissed'),
                ('changes_requested', 'failed', 'review_changes_requested'),
                ('pending', 'unknown', 'review_pending'), ('unknown', 'unknown', 'review_state_unknown')):
            claim = replace(row, review=replace(review(), state=state), invocation=current)
            result = evaluate(candidate(), (claim,), (current,))
            finding = next(r for r in result.rows if r.gate_id == row.gate_id)
            self.assertEqual((finding.status, finding.reason), (status, reason))
            self.assertEqual(result.status, 'blocked')
            self.assertFalse(result.release_approved)
            self.assertFalse(result.publish_approved)

    def test_hosted_floor_matches_all_current_reviewed_fixtures(self):
        workflow = (ROOT / '.github/workflows/rc-pretag-contract-checks.yml').read_text()
        floor = int(re.search(r'result.testsRun >= ([0-9]+)', workflow).group(1))
        self.assertGreaterEqual(floor, 53)

if __name__ == '__main__':
    unittest.main(verbosity=2)
