"""Deterministic navigation-race tests, not native acceptance evidence."""
from __future__ import annotations
import json
import unittest
from unittest.mock import Mock, patch
import exclusive_native_acceptance as native

FINGERPRINT = '0123456789abcdef'


def driver_error(code):
    return RuntimeError('HTTP 400: ' + json.dumps({'value': {'error': code}}))


class NativeDialogRace(unittest.TestCase):
    def invoke(self, states, error=None):
        session = Mock()
        session.execute.side_effect = states
        with patch.object(native.legacy, 'click', side_effect=error) as click, \
             patch.object(native.gui, 'wait_for', side_effect=lambda f: self.assertTrue(f())):
            native.open_candidate_dialog(session, FINGERPRINT)
        self.assertTrue(all(c.args[-1] == FINGERPRINT for c in session.execute.call_args_list))
        self.assertLessEqual(click.call_count, 1, 'a click must not be replayed')
        return click.call_count

    def test_already_open_never_clicks_behind_modal(self):
        self.assertEqual(self.invoke([True, True]), 0)

    def test_background_candidate_uses_one_native_inbox_click(self):
        self.assertEqual(self.invoke([False, True]), 1)

    def test_webkit_autopen_race_requires_exact_modal_readback(self):
        self.assertEqual(self.invoke([False, True, True], driver_error('element not interactable')), 1)

    def test_webview_intercept_race_requires_exact_modal_readback(self):
        self.assertEqual(self.invoke([False, True, True], driver_error('element click intercepted')), 1)

    def test_obscured_inbox_without_target_modal_is_not_a_pass(self):
        for code in ('element not interactable', 'element click intercepted'):
            with self.subTest(code=code), self.assertRaises(RuntimeError):
                self.invoke([False, False], driver_error(code))

    def test_other_driver_and_transport_errors_are_never_suppressed(self):
        for error in (driver_error('stale element reference'), driver_error('invalid session id'),
                      RuntimeError('connection reset'), RuntimeError('HTTP 400: not-json')):
            with self.subTest(error=error), self.assertRaises(RuntimeError):
                self.invoke([False, True], error)

    def test_truthy_non_boolean_does_not_prove_a_matching_modal(self):
        with self.assertRaises(RuntimeError):
            self.invoke([None, 'yes'], driver_error('element not interactable'))

    def test_revocation_waits_for_authoritative_completion(self):
        session = Mock(); profile = {'id': 'synthetic-profile'}
        seen = []
        def observe(fetch, predicate):
            first = fetch(); seen.append(predicate(first))
            second = fetch(); seen.append(predicate(second))
            self.assertEqual(seen, [False, True])
        with patch.object(native, 'visit'), patch.object(native.legacy, 'click') as click, \
             patch.object(native, 'status', side_effect=[{'records':[{'status':'active'}]}, {'records':[{'status':'revoked'}]}]), \
             patch.object(native.gui, 'wait_for', side_effect=observe):
            native.revoke(session, profile)
        self.assertEqual(click.call_count, 1)
        session.invoke.assert_not_called()

    def test_revocation_does_not_claim_that_draining_work_has_ended(self):
        session = Mock(); profile = {'id': 'synthetic-profile'}
        snapshot = {'records':[{'status':'revoked'}], 'lease_state':'draining'}
        with patch.object(native, 'visit'), patch.object(native.legacy, 'click'), \
             patch.object(native, 'status', return_value=snapshot), \
             patch.object(native.gui, 'wait_for', side_effect=lambda fetch, predicate: self.assertTrue(predicate(fetch()))):
            native.revoke(session, profile)
        session.invoke.assert_not_called()

    def test_source_routes_both_entrypoints_through_readback(self):
        from pathlib import Path
        source = Path(native.__file__).read_text()
        self.assertIn("open_candidate_dialog(session, grant['fingerprint'])", source)
        self.assertIn("open_candidate_dialog(session, pending['authorization']['fingerprint'])", source)
        import inspect
        self.assertNotIn('session.invoke', inspect.getsource(native.open_candidate_dialog))


if __name__ == '__main__':
    unittest.main(verbosity=2)
