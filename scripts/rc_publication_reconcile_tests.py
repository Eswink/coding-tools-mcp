"""Synthetic journal consistency, never an executed end-to-end publication claim."""
from copy import deepcopy
from dataclasses import asdict, replace
import unittest

from rc_pretag_types import ContractError, encode, parse_json
from rc_publication_fixtures import (assert_unverified, synthetic_asset, synthetic_assets,
    synthetic_attempt, synthetic_checkpoint, synthetic_entries, synthetic_full_trace,
    synthetic_journal, synthetic_recipe, synthetic_release)
from rc_publication_reconcile import reconcile
from rc_publication_types import JournalObservation


def synthetic_trace(journal):
    return [entry.attempt if entry.kind == 'attempt' else entry.checkpoint
            for entry in journal.entries]


def synthetic_draft_checkpoint(count=0):
    return synthetic_checkpoint(synthetic_release(synthetic_assets(count)), expected_release_id=700)


class PublicationReconcileTests(unittest.TestCase):
    def check(self, journal, classification, reason=None):
        report = reconcile(journal)
        assert_unverified(self, report)
        self.assertEqual(report.classification, classification)
        if reason is not None:
            self.assertIn(reason, report.reasons)
        self.assertNotIn('next_action', asdict(report))
        return report

    def test_full_synthetic_create_upload_checkpoint_publish_trace(self):
        journal = synthetic_full_trace()
        report = self.check(journal, 'journal_consistent')
        self.assertEqual(len(journal.entries), 17)
        self.assertEqual(report.release_id, 700)
        self.assertEqual(report.accounted_asset_ids, tuple(range(1001, 1007)))
        self.assertEqual(report.observed_asset_ids, report.accounted_asset_ids)
        self.assertEqual(report.observed_release_ids, (700,))
        self.assertIs(report.published_observed, True)
        self.assertIs(report.uncertainty_observed, False)
        self.assertIs(report.failed_observed, False)

    def test_initial_partial_draft_all_sizes_can_form_consistent_synthetic_trace(self):
        for count in range(7):
            with self.subTest(initial_assets=count):
                report = self.check(synthetic_full_trace(initial_count=count), 'journal_consistent')
                self.assertEqual(report.accounted_asset_ids, tuple(range(1001, 1007)))
                self.assertIs(report.published_observed, True)

    def test_partial_trace_ending_at_checkpoint_is_consistent_but_unverified(self):
        for count in range(7):
            report = self.check(synthetic_journal(synthetic_draft_checkpoint(count)), 'journal_consistent')
            self.assertEqual(report.accounted_asset_ids, tuple(range(1001, 1001 + count)))
            self.assertIs(report.published_observed, False)

    def test_absent_only_trace_has_no_target_or_accounted_assets(self):
        report = self.check(synthetic_journal(), 'journal_consistent')
        self.assertIsNone(report.release_id)
        self.assertEqual(report.accounted_asset_ids, ())

    def test_initial_published_inventory_permits_read_only_observation(self):
        public = synthetic_release(synthetic_assets(), draft=False)
        report = self.check(synthetic_journal(synthetic_checkpoint(public)), 'journal_consistent')
        self.assertIs(report.published_observed, True)
        self.assertEqual(report.accounted_asset_ids, ())
        self.assertEqual(report.observed_asset_ids, tuple(range(1001, 1007)))

    def test_repeated_identical_published_reads_do_not_claim_ownership_or_conflict(self):
        public = synthetic_release(synthetic_assets(), draft=False)
        checkpoint = synthetic_checkpoint(public, expected_release_id=700)
        report = self.check(synthetic_journal(checkpoint, checkpoint), 'journal_consistent')
        self.assertIs(report.published_observed, True)
        self.assertEqual(report.accounted_asset_ids, ())
        self.assertEqual(report.observed_asset_ids, tuple(range(1001, 1007)))

    def test_every_success_requires_a_fresh_post_success_checkpoint(self):
        trace = synthetic_trace(synthetic_full_trace())
        for end in (2, 4, 6, 8, 10, 12, 14, 16):
            report = self.check(synthetic_journal(*trace[:end]), 'journal_stopped', 'checkpoint_required')
            self.assertIn('incomplete_journal', report.reasons)
            self.assertIs(report.failed_observed, False)

    def test_following_attempt_before_success_checkpoint_is_conflict(self):
        trace = synthetic_trace(synthetic_full_trace())
        for index in (2, 4, 6, 8, 10, 12, 14):
            modified = trace[:index] + trace[index + 1:]
            self.check(synthetic_journal(*modified), 'journal_conflict', 'checkpoint_required')

    def test_first_entry_must_be_checkpoint(self):
        self.check(synthetic_journal(synthetic_attempt()), 'journal_conflict', 'checkpoint_required')

    def test_contiguous_sequence_no_gap_duplicate_or_reorder(self):
        journal = synthetic_full_trace()
        for entries in ((replace(journal.entries[0], sequence=2),) + journal.entries[1:],
                journal.entries[:2] + (replace(journal.entries[2], sequence=2),) + journal.entries[3:],
                (journal.entries[1], journal.entries[0]) + journal.entries[2:]):
            self.check(replace(journal, entries=entries), 'journal_conflict', 'journal_order')

    def test_create_requires_reported_absence_and_cannot_replace_draft(self):
        for count in (0, 2, 6):
            self.check(synthetic_journal(synthetic_draft_checkpoint(count), synthetic_attempt()),
                       'journal_conflict', 'journal_target')

    def test_upload_without_established_release_cannot_proceed(self):
        self.check(synthetic_journal(synthetic_checkpoint(), synthetic_attempt('upload_asset')),
                   'journal_conflict', 'journal_target')

    def test_initial_unknown_cannot_be_cleared_by_later_reported_absence(self):
        trace = (synthetic_checkpoint(lookup='unknown'), synthetic_checkpoint(), synthetic_attempt())
        report = self.check(synthetic_journal(*trace), 'journal_conflict', 'operation_after_stop')
        self.assertIn('initial_inventory_unknown', report.reasons)
        self.assertEqual(report.accounted_asset_ids, ())

    def test_initial_collision_cannot_be_cleared_by_matching_checkpoint(self):
        wrong = replace(synthetic_release(), notes_sha256='f' * 64)
        trace = (synthetic_checkpoint(wrong), synthetic_draft_checkpoint(), synthetic_attempt('upload_asset'))
        self.check(synthetic_journal(*trace), 'journal_conflict', 'operation_after_stop')

    def test_second_create_is_not_a_retry(self):
        trace = synthetic_trace(synthetic_full_trace())[:3] + [synthetic_attempt()]
        self.check(synthetic_journal(*trace), 'journal_conflict', 'journal_replay')

    def test_second_upload_for_same_asset_is_not_a_retry(self):
        trace = synthetic_trace(synthetic_full_trace())[:5] + [synthetic_attempt('upload_asset')]
        self.check(synthetic_journal(*trace), 'journal_conflict', 'journal_replay')

    def test_second_publish_and_upload_after_publication_are_forbidden(self):
        trace = synthetic_trace(synthetic_full_trace())
        for operation in ('create_draft', 'upload_asset', 'publish'):
            self.check(synthetic_journal(*trace, synthetic_attempt(operation)),
                       'journal_conflict', 'operation_after_stop')

    def test_any_operation_after_prepared_unknown_or_failure_is_forbidden(self):
        for operation in ('create_draft', 'upload_asset', 'publish'):
            initial = (synthetic_checkpoint() if operation == 'create_draft' else
                       synthetic_draft_checkpoint(6 if operation == 'publish' else 0))
            for outcome in ('prepared_only', 'outcome_unknown', 'response_failure'):
                for following in ('create_draft', 'upload_asset', 'publish'):
                    trace = (initial, synthetic_attempt(operation, outcome), synthetic_attempt(following))
                    with self.subTest(operation=operation, outcome=outcome, following=following):
                        report = self.check(synthetic_journal(*trace), 'journal_conflict', 'operation_after_stop')
                        self.assertIs(report.failed_observed, outcome == 'response_failure')
                        self.assertIs(report.uncertainty_observed, outcome != 'response_failure')

    def test_prepared_or_unknown_latch_survives_matching_read(self):
        for outcome in ('prepared_only', 'outcome_unknown'):
            trace = (synthetic_draft_checkpoint(), synthetic_attempt('upload_asset', outcome),
                     synthetic_draft_checkpoint())
            report = self.check(synthetic_journal(*trace), 'journal_stopped', 'uncertain_outcome')
            self.assertIs(report.uncertainty_observed, True)
            self.assertEqual(report.accounted_asset_ids, ())

    def test_failure_latch_survives_matching_read_without_asserting_absence(self):
        trace = (synthetic_draft_checkpoint(), synthetic_attempt('upload_asset', 'response_failure'),
                 synthetic_draft_checkpoint())
        report = self.check(synthetic_journal(*trace), 'journal_stopped', 'failed_attempt')
        self.assertIs(report.failed_observed, True)
        self.assertEqual(report.accounted_asset_ids, ())

    def test_unknown_create_retains_new_release_and_asset_ids_without_accounting(self):
        assets = tuple(replace(asset, asset_id=2001 + i) for i, asset in enumerate(synthetic_assets()))
        later = synthetic_checkpoint(synthetic_release(assets, release_id=777), expected_release_id=777)
        report = self.check(synthetic_journal(synthetic_checkpoint(),
            synthetic_attempt('create_draft', 'outcome_unknown'), later), 'journal_stopped', 'uncertain_outcome')
        self.assertIsNone(report.release_id)
        self.assertEqual(report.observed_release_ids, (777,))
        self.assertEqual(report.observed_asset_ids, tuple(range(2001, 2007)))
        self.assertEqual(report.accounted_asset_ids, ())
        self.assertIs(report.uncertainty_observed, True)

    def test_unknown_upload_later_new_id_is_observed_not_successfully_accounted(self):
        later_asset = synthetic_asset(2, asset_id=3003)
        later = synthetic_checkpoint(synthetic_release(synthetic_assets(2) + (later_asset,)),
                                     expected_release_id=700)
        report = self.check(synthetic_journal(synthetic_draft_checkpoint(2),
            synthetic_attempt('upload_asset', 'outcome_unknown', index=2), later),
            'journal_stopped', 'uncertain_outcome')
        self.assertEqual(report.accounted_asset_ids, (1001, 1002))
        self.assertEqual(report.observed_asset_ids, (1001, 1002, 3003))
        self.assertIs(report.uncertainty_observed, True)

    def test_failed_upload_cannot_be_laundered_through_complete_later_inventory(self):
        trace = (synthetic_draft_checkpoint(5),
                 synthetic_attempt('upload_asset', 'response_failure', index=5),
                 synthetic_draft_checkpoint(6))
        report = self.check(synthetic_journal(*trace), 'journal_stopped', 'failed_attempt')
        self.assertEqual(report.accounted_asset_ids, tuple(range(1001, 1006)))
        self.assertIn(1006, report.observed_asset_ids)
        self.check(synthetic_journal(*trace, synthetic_attempt('publish')),
                   'journal_conflict', 'operation_after_stop')

    def test_uncertain_response_identity_retained_without_success_ownership(self):
        release = synthetic_release(release_id=777)
        report = self.check(synthetic_journal(synthetic_checkpoint(),
            synthetic_attempt('create_draft', 'outcome_unknown', response=release)), 'journal_stopped')
        self.assertEqual(report.observed_release_ids, (777,))
        self.assertIsNone(report.release_id)
        self.assertEqual(report.accounted_asset_ids, ())
        report = self.check(synthetic_journal(synthetic_draft_checkpoint(),
            synthetic_attempt('upload_asset', 'response_failure', response=synthetic_asset(asset_id=999))),
            'journal_stopped')
        self.assertIn(999, report.observed_asset_ids)
        self.assertEqual(report.accounted_asset_ids, ())

    def test_unexplained_new_asset_after_success_cannot_complete_journal(self):
        trace = synthetic_trace(synthetic_full_trace())[:4]
        self.check(synthetic_journal(*trace, synthetic_draft_checkpoint(2)),
                   'journal_conflict', 'unaccounted_asset')

    def test_disappeared_or_replaced_accounted_asset_is_conflict(self):
        initial = synthetic_draft_checkpoint(2)
        changed = (synthetic_assets(1), (replace(synthetic_asset(), asset_id=999), synthetic_asset(1)))
        for assets in changed:
            later = synthetic_checkpoint(synthetic_release(assets), expected_release_id=700)
            self.check(synthetic_journal(initial, later), 'journal_conflict', 'unaccounted_asset')

    def test_accounted_asset_mutation_never_matches_a_fresh_checkpoint(self):
        for field, value in (('media_type', 'text/plain'), ('size', 1), ('sha256', 'f' * 64),
                             ('state', 'starter'), ('name', 'renamed.exe')):
            asset = replace(synthetic_asset(), **{field: value})
            later = synthetic_checkpoint(synthetic_release((asset,)), expected_release_id=700)
            self.check(synthetic_journal(synthetic_draft_checkpoint(1), later),
                       'journal_conflict', 'checkpoint_conflict')

    def test_same_accounted_inventory_in_different_row_order_is_consistent(self):
        later = synthetic_checkpoint(synthetic_release(synthetic_assets(3)[::-1]), expected_release_id=700)
        report = self.check(synthetic_journal(synthetic_draft_checkpoint(3), later), 'journal_consistent')
        self.assertEqual(report.accounted_asset_ids, (1001, 1002, 1003))

    def test_continuation_checkpoint_requires_unchanged_explicit_release_target(self):
        for target in (None, 701):
            checkpoint = replace(synthetic_draft_checkpoint(), expected_release_id=target)
            self.check(synthetic_journal(synthetic_draft_checkpoint(), checkpoint), 'journal_conflict')
        replacement = synthetic_checkpoint(synthetic_release(release_id=701), expected_release_id=701)
        self.check(synthetic_journal(synthetic_draft_checkpoint(), replacement), 'journal_conflict', 'journal_target')

    def test_attempt_cannot_substitute_another_release_id(self):
        for operation in ('upload_asset', 'publish'):
            initial = synthetic_draft_checkpoint(6 if operation == 'publish' else 0)
            self.check(synthetic_journal(initial, synthetic_attempt(operation, release_id=701)),
                       'journal_conflict', 'journal_target')

    def test_successful_upload_response_requires_exact_asset_identity(self):
        for field, value in (('name', synthetic_asset(1).name), ('media_type', None),
                ('media_type', 'text/plain'), ('size', None), ('size', 0),
                ('sha256', None), ('sha256', 'f' * 64), ('state', 'starter')):
            response = replace(synthetic_asset(), **{field: value})
            self.check(synthetic_journal(synthetic_draft_checkpoint(),
                synthetic_attempt('upload_asset', response=response)), 'journal_conflict', 'response_conflict')

    def test_successful_upload_cannot_reuse_an_accounted_id(self):
        response = synthetic_asset(1, asset_id=1001)
        self.check(synthetic_journal(synthetic_draft_checkpoint(1),
            synthetic_attempt('upload_asset', index=1, response=response)), 'journal_conflict', 'response_conflict')

    def test_upload_of_unlisted_asset_is_rejected(self):
        attempt = replace(synthetic_attempt('upload_asset'), asset_name='unlisted.txt')
        self.check(synthetic_journal(synthetic_draft_checkpoint(), attempt), 'journal_conflict', 'response_conflict')

    def test_create_response_must_be_exact_empty_draft_for_recipe(self):
        original = synthetic_release()
        for changes in ({'draft': False}, {'prerelease': False}, {'notes_sha256': 'f' * 64},
                {'tag': 'v1.2.3-rc.8'}, {'reported_target_commitish': None},
                {'reported_target_commitish': 'f' * 40}, {'assets': synthetic_assets(1)},
                {'source': replace(original.source, source_tree='f' * 40)}):
            self.check(synthetic_journal(synthetic_checkpoint(),
                synthetic_attempt(response=replace(original, **changes))), 'journal_conflict', 'response_conflict')

    def test_publish_requires_complete_checkpoint_with_six_accounted_assets(self):
        for count in range(6):
            self.check(synthetic_journal(synthetic_draft_checkpoint(count), synthetic_attempt('publish')),
                       'journal_conflict', 'checkpoint_required')

    def test_publish_response_cannot_substitute_release_or_asset_ids(self):
        public = synthetic_release(synthetic_assets(), draft=False)
        for change in ({'release_id': 701}, {'draft': True}, {'assets': synthetic_assets(5)},
                {'assets': (synthetic_asset(asset_id=2001),) + synthetic_assets()[1:]},
                {'assets': synthetic_assets() + (synthetic_asset(),)}, {'prerelease': False}):
            self.check(synthetic_journal(synthetic_draft_checkpoint(6),
                synthetic_attempt('publish', response=replace(public, **change))),
                'journal_conflict', 'response_conflict')

    def test_published_observation_survives_inaccessible_unknown_or_denied_reads(self):
        public = synthetic_checkpoint(synthetic_release(synthetic_assets(), draft=False))
        for later in (synthetic_checkpoint(lookup='inaccessible'), synthetic_checkpoint(lookup='unknown'),
                      synthetic_checkpoint(visibility='denied')):
            report = self.check(synthetic_journal(public, later), 'journal_stopped')
            self.assertIs(report.published_observed, True)

    def test_publish_success_and_failure_facts_remain_independent(self):
        trace = synthetic_trace(synthetic_full_trace())
        later = synthetic_attempt('publish', 'response_failure')
        report = self.check(synthetic_journal(*trace, later), 'journal_conflict', 'operation_after_stop')
        self.assertIs(report.published_observed, True)
        self.assertIs(report.failed_observed, True)

    def test_uncertainty_and_publication_survive_later_failed_reads(self):
        trace = (synthetic_draft_checkpoint(6), synthetic_attempt('publish', 'outcome_unknown'),
                 synthetic_checkpoint(synthetic_release(synthetic_assets(), draft=False), expected_release_id=700),
                 synthetic_checkpoint(lookup='inaccessible'))
        report = self.check(synthetic_journal(*trace), 'journal_stopped', 'uncertain_outcome')
        self.assertIs(report.uncertainty_observed, True)
        self.assertIs(report.published_observed, True)
        self.assertIs(report.failed_observed, False)

    def test_failure_is_not_cleared_by_a_later_published_inventory(self):
        trace = (synthetic_draft_checkpoint(6), synthetic_attempt('publish', 'response_failure'),
                 synthetic_checkpoint(synthetic_release(synthetic_assets(), draft=False), expected_release_id=700))
        report = self.check(synthetic_journal(*trace), 'journal_stopped', 'failed_attempt')
        self.assertIs(report.failed_observed, True)
        self.assertIs(report.published_observed, True)

    def test_recipe_fingerprint_cannot_be_replaced_or_left_stale_after_tampering(self):
        journal = synthetic_full_trace()
        with self.assertRaisesRegex(ContractError, 'journal_recipe_mismatch'):
            reconcile(replace(journal, recipe_fingerprint='0' * 64))
        recipe = replace(journal.recipe, notes_sha256='f' * 64)
        with self.assertRaisesRegex(ContractError, 'journal_recipe_mismatch'):
            reconcile(replace(journal, recipe=recipe))

    def test_new_transaction_digest_does_not_remove_stop_or_replay_blocker(self):
        trace = (synthetic_checkpoint(), synthetic_attempt('create_draft', 'outcome_unknown'))
        for digest in ('1' * 64, '2' * 64):
            report = self.check(synthetic_journal(*trace, transaction_digest=digest), 'journal_stopped')
            self.assertIs(report.uncertainty_observed, True)
            self.assertIn('cross_journal_replay_unproven', report.blockers)

    def test_successful_trace_has_no_verified_final_public_or_executable_state(self):
        report = self.check(synthetic_full_trace(), 'journal_consistent')
        for key in ('next_action', 'request', 'executor', 'authority_token', 'ready', 'eligible',
                    'public_verified', 'finalized', 'owned'):
            self.assertNotIn(key, asdict(report))
        self.assertEqual(parse_json(type(report), encode(report)), report)

    def test_journal_entrypoint_deeply_revalidates_nested_and_boundary_tampering(self):
        for field, value in (('execution_enabled', True), ('release_approved', True),
                ('publish_approved', True), ('snapshot_atomic', True), ('blockers', ()),
                ('evidence_authentication', 'authenticated')):
            journal = synthetic_full_trace()
            object.__setattr__(journal, field, value)
            with self.assertRaises(ContractError):
                reconcile(journal)
        journal = synthetic_full_trace()
        object.__setattr__(journal.entries[3].attempt.response_asset, 'size', True)
        with self.assertRaises(ContractError):
            reconcile(journal)
        journal = synthetic_full_trace()
        object.__setattr__(journal.recipe.source, 'source_tree', 'X' * 40)
        with self.assertRaises(ContractError):
            reconcile(journal)

    def test_journal_entrypoint_rejects_subclasses_and_untyped_input(self):
        class JournalSubclass(JournalObservation):
            pass
        journal = synthetic_journal()
        subclass = JournalSubclass(**{field: getattr(journal, field) for field in journal.__dataclass_fields__})
        for value in (subclass, {}, None):
            with self.assertRaises(ContractError):
                reconcile(value)

    def test_published_then_draft_is_conflict_without_erasing_publication(self):
        public = synthetic_checkpoint(synthetic_release(synthetic_assets(), draft=False),
                                      expected_release_id=700)
        for prefix in ([public], synthetic_trace(synthetic_full_trace())):
            with self.subTest(initial_only=len(prefix) == 1):
                report = self.check(synthetic_journal(*prefix, synthetic_draft_checkpoint(6)),
                                    'journal_conflict', 'checkpoint_conflict')
                self.assertIs(report.published_observed, True)

    def test_aggregate_observed_asset_id_bound_rejects_instead_of_truncating(self):
        checkpoints = [synthetic_checkpoint(lookup='unknown')]
        for index in range(9):
            assets = tuple(replace(synthetic_asset(), asset_id=2000 + 16 * index + j,
                                   name=f'synthetic-extra-{index}-{j}.txt') for j in range(16))
            checkpoints.append(synthetic_checkpoint(synthetic_release(assets, release_id=700 + index)))
        report = self.check(synthetic_journal(*checkpoints[:9]), 'journal_stopped')
        self.assertEqual(len(report.observed_asset_ids), 128)
        self.assertEqual(report.accounted_asset_ids, ())
        with self.assertRaises(ContractError):
            reconcile(synthetic_journal(*checkpoints))

    def test_maximum_bounded_release_ids_are_all_retained_without_truncation(self):
        checkpoints = []
        for index in range(32):
            checkpoint = synthetic_checkpoint(synthetic_release(release_id=700 + 2 * index))
            checkpoints.append(replace(checkpoint, releases=checkpoint.releases + (
                synthetic_release(release_id=701 + 2 * index),)))
        report = self.check(synthetic_journal(*checkpoints), 'journal_conflict', 'multiple_releases')
        self.assertEqual(report.observed_release_ids, tuple(range(700, 764)))
        self.assertEqual(report.accounted_asset_ids, ())

    def test_initial_public_baseline_cannot_be_replaced_by_new_asset_ids(self):
        public = synthetic_release(synthetic_assets(), draft=False)
        replacement = replace(public, assets=(synthetic_asset(asset_id=2001),) + public.assets[1:])
        report = self.check(synthetic_journal(
            synthetic_checkpoint(public, expected_release_id=700),
            synthetic_checkpoint(replacement, expected_release_id=700)), 'journal_conflict')
        self.assertIs(report.published_observed, True)
        self.assertEqual(report.accounted_asset_ids, ())
        self.assertEqual(report.observed_asset_ids, tuple(range(1001, 1007)) + (2001,))

    def test_initial_absence_cannot_account_for_unexplained_later_draft(self):
        report = self.check(synthetic_journal(synthetic_checkpoint(), synthetic_draft_checkpoint(6)),
                            'journal_conflict', 'journal_target')
        self.assertEqual(report.accounted_asset_ids, ())
        self.assertIsNone(report.release_id)

    def test_foreign_source_in_continuation_checkpoint_is_a_conflict(self):
        checkpoint = synthetic_draft_checkpoint(1)
        for field, value in (('source_sha', 'f' * 40), ('source_tree', 'f' * 40),
                             ('version', '1.2.3-rc.8')):
            foreign = replace(checkpoint, source=replace(checkpoint.source, **{field: value}))
            self.check(synthetic_journal(checkpoint, foreign), 'journal_conflict', 'checkpoint_conflict')

    def test_unknown_publish_then_public_then_draft_keeps_uncertainty_and_publication(self):
        trace = (synthetic_draft_checkpoint(6), synthetic_attempt('publish', 'outcome_unknown'),
                 synthetic_checkpoint(synthetic_release(synthetic_assets(), draft=False), expected_release_id=700),
                 synthetic_draft_checkpoint(6))
        report = reconcile(synthetic_journal(*trace))
        assert_unverified(self, report)
        self.assertIn(report.classification, ('journal_stopped', 'journal_conflict'))
        self.assertIs(report.uncertainty_observed, True)
        self.assertIs(report.published_observed, True)


if __name__ == '__main__':
    unittest.main()
