"""Source-ordered late-failure assertions invoked by the existing unittest method."""
from cmd_observation_fixtures import OLD_POSITIVES, RUN_NONCE, completed_fixture, decode, case_defaults
from cmd_observation_failure_fixtures import late_failure


def assert_late_failures_keep_raw_and_old_results(test):
    case_categories = (
        'case_profile_delete_false case_profile_delete_throw case_root_remove_false case_root_remove_throw '
        'case_bind_serialize case_bind_create case_bind_write case_bind_flush case_bind_close '
        'case_verify_pending case_binding_content case_binding_identity case_binding_read case_binding_close case_rename '
        'case_receipt_serialize case_receipt_create case_receipt_write case_receipt_flush case_receipt_close_false case_receipt_close_throw'
    ).split()
    matrix_categories = 'matrix_serialize matrix_create matrix_write matrix_flush matrix_close_false matrix_close_throw'.split()
    run_categories = (
        'run_root_false run_root_throw final_guard final_identity_scan selected_pin_close_false selected_pin_close_throw selected_pin_uncertain '
        'final_result_serialize final_result_create final_result_write final_result_flush final_result_close_false final_result_close_throw '
        'run_bind_serialize run_bind_create run_bind_write run_bind_flush run_bind_close '
        'run_verify_pending run_binding_content run_binding_identity run_binding_read run_binding_close run_resolve_rename'
    ).split()
    test.assertEqual((len(case_categories), len(matrix_categories), len(run_categories)), (21, 6, 24))
    variants = [(category, target, 10) for target in ('cmd-read-direct', 'cmd-relative-batch-exit23') for category in case_categories]
    variants += [(category, 'cmd-read-direct', position) for position in (10, 11) for category in matrix_categories]
    variants += [(category, 'cmd-read-direct', 10) for category in run_categories]
    test.assertEqual(len(variants), 78)
    relative = 'cmd-relative-batch-exit23'
    for category, target, position in variants:
        with test.subTest(category=category, target=target, matrix_position=position):
            context, members = completed_fixture()
            matrices = {index: members['pilot/matrix-' + str(index).zfill(2) + '.json'] for index in range(1, 12)}
            preconditions = 'pilot/preconditions-' + RUN_NONCE + '.json'
            bound = members[preconditions]
            baseline = late_failure(members, category, target=target, matrix_position=position)
            test.assertIn('pilot/cleanup-uncertain.txt', members)
            test.assertNotIn('pilot/completed-' + RUN_NONCE + '.txt', members)
            if category in ('run_verify_pending', 'run_bind_close', 'run_bind_flush'):
                test.assertEqual(members[preconditions], bound)
            elif category == 'run_bind_write':
                test.assertEqual(members[preconditions], b'{"Policy":')
            elif category in ('run_bind_serialize', 'run_bind_create'):
                test.assertNotIn(preconditions, members)
            result = test.evaluate(context, members)
            test.assert_rejected(result)
            failure = decode(members['pilot/pilot-failure.json'])
            if category == 'run_bind_close':
                test.assertEqual(failure['Broker']['Numbers']['evidence_journal_preconditions_' + RUN_NONCE + '_close_confirmed'], 0)
            test.assertEqual({key: failure[key] for key in OLD_POSITIVES}, baseline)
            test.assertTrue(failure['CmdCwdRawObservationMatched'])
            test.assertTrue(failure['CmdReadRawObservationMatched'])
            blocked = category.startswith('case_') and target == 'cmd-read-direct' or category.startswith('matrix_') and position == 10
            test.assertEqual(failure['CmdRelativeBatchRawObservationMatched'], not blocked)
            test.assertFalse(result['RunCompletionValidated'])
            if not category.startswith('matrix_'):
                test.assertTrue(result['CmdCwdRawObservationMatched'])
                test.assertTrue(result['CmdReadRawObservationMatched'])
                test.assertEqual(result['CmdRelativeBatchRawObservationMatched'], not blocked)
            if blocked:
                expected = case_defaults(relative)
                expected.update(Fatal=True, NoCaseResourcesAllocated=True, Status=(
                    'blocked_prior_control_or_recovery' if category.startswith('case_') else 'blocked_run_failure_no_subject_created'))
                test.assertEqual(failure['Cases'][10], expected)
                test.assertFalse(any(name.startswith('pilot/' + relative + '/') for name in members))
                test.assertFalse(result['CmdRelativeBatchRawObservationMatched'])
            if category.startswith('matrix_'):
                for index in range(position, 12):
                    test.assertNotIn('pilot/matrix-' + str(index).zfill(2) + '.json', members)
                    prefix = 'evidence_matrix_' + str(index).zfill(2)
                    test.assertFalse(any(key.startswith(prefix + '_') for key in failure['Broker']['Numbers']))
                    test.assertNotIn(prefix, failure['Broker']['Identities'])
                unchanged = position - 1
            elif category.startswith('case_'):
                unchanged = 9 if target == 'cmd-read-direct' else 10
                test.assertEqual(decode(members['pilot/matrix-11.json'])['Cases'], failure['Cases'])
            else:
                unchanged = 11
            for index in range(1, unchanged + 1):
                test.assertEqual(members['pilot/matrix-' + str(index).zfill(2) + '.json'], matrices[index])
            reached_cases = 10 if blocked else 11
            after_scan = category.startswith(('final_result_', 'run_bind', 'run_verify', 'run_resolve', 'selected_pin_'))
            guards = 4 * reached_cases + (2 if after_scan else 0 if category.startswith(('case_', 'matrix_')) else 1)
            test.assertEqual(failure['SelectedParent']['VerifiedGuards'], guards)
    contradictions = [(category, 'cmd-read-direct') for category in (
        'case_root_remove_false', 'case_receipt_close_false', 'selected_pin_close_throw', 'run_binding_close')]
    contradictions += [(category, relative) for category in ('case_root_remove_false', 'case_receipt_close_false')]
    test.assertEqual(len(contradictions), 6)
    for category, target in contradictions:
        with test.subTest(contradiction=category, target=target):
            context, members = completed_fixture()
            late_failure(members, category, contradiction=True, target=target)
            result = test.evaluate(context, members)
            test.assert_rejected(result, 'commit')
            test.assertEqual(result['CwdStatus'], 'inconsistent')
            test.assertEqual(result['RelativeBatchStatus'], 'inconsistent')
