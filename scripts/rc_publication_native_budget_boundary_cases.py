"""Actual native caller budgets and the optional consumer error bridge."""
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

import rc_consumer_io as safe
import rc_publication_artifact_admission as artifacts
import rc_publication_contract as core
import rc_publication_github as wire
import rc_publication_request as owned
from rc_publication_native_stage_composition_cases import NativeStageCompositionCases


class NativeBudgetBoundaryCases(unittest.TestCase):
    native_preparation = NativeStageCompositionCases.native_preparation
    blocked = NativeStageCompositionCases.blocked

    def test_actual_entered_invalid_caller_shape_is_rejected_without_callback_or_get(self):
        with self.native_preparation() as (session, tls, _):
            reached, called = [], []
            def observe(selection, api, *, deadline, check_active):
                owner, before = artifacts._OWNERS[api], len(tls.requests)
                def caller():
                    called.append(True)
                for invalid in (float('nan'), float('inf'), float('-inf'), True, '60', {}):
                    with self.subTest(deadline_type=type(invalid).__name__), self.assertRaisesRegex(
                            safe.ConsumerError, '^invalid_transport_deadline$'):
                        owner._controls(invalid, caller)
                for invalid in (True, 'callable', {}, object()):
                    with self.subTest(callback_type=type(invalid).__name__), self.assertRaisesRegex(
                            safe.ConsumerError, '^artifact_transport_failed$'):
                        owner._controls(deadline, invalid)
                self.assertEqual(called, [])
                self.assertEqual(len(tls.requests), before)
                reached.append(True)
                raise wire.WireFailure('fence_blocked', 'none')
            with patch.object(wire, '_authenticate', side_effect=observe):
                self.blocked(session)
            self.assertEqual(reached, [True])

    def test_actual_entered_generic_caller_exception_is_sanitized(self):
        with self.native_preparation() as (session, tls, _):
            errors = []
            def observe(selection, api, *, deadline, check_active):
                owner, before = artifacts._OWNERS[api], len(tls.requests)
                def caller():
                    raise RuntimeError('PRIVATE_CALLBACK_SENTINEL')
                try:
                    owner._controls(deadline, caller)
                except BaseException as error:
                    errors.append(error)
                self.assertEqual(len(tls.requests), before)
                raise wire.WireFailure('fence_blocked', 'none')
            with patch.object(wire, '_authenticate', side_effect=observe):
                self.blocked(session)
            self.assertEqual(len(errors), 1)
            self.assertIs(type(errors[0]), safe.ConsumerError)
            self.assertEqual(str(errors[0]), 'artifact_transport_failed')

    def test_actual_entered_second_budget_poll_preserves_non_none_error_identity(self):
        with self.native_preparation() as (session, tls, _):
            reached = []
            def observe(selection, api, *, deadline, check_active):
                owner, before = artifacts._OWNERS[api], len(tls.requests)
                armed, calls = [None], []
                issued, first = session._read_scope, session._read_scope._deadline
                self.assertIs(type(issued), owned._ReadScope)
                issued._check(api)
                def caller():
                    calls.append(True)
                    if armed[0] is not None:
                        raise armed[0]
                end, active = owner._controls(deadline, caller)
                self.assertTrue(calls)
                self.assertLessEqual(end, first)
                for code, effect in (('cancelled', 'unknown'), ('timeout', 'confirmed')):
                    error = wire.WireFailure(code, effect, release_id=100)
                    armed[0] = error
                    previous = len(calls)
                    try:
                        received = None
                        try:
                            safe._check_budget(end, active)
                        except BaseException as caught:
                            received = caught
                        with self.subTest(effect=effect):
                            self.assertIs(type(received), wire.WireFailure)
                            self.assertIs(received, error)
                            self.assertEqual(received.release_id, 100 if effect == 'confirmed' else None)
                            self.assertEqual(len(calls), previous + 1)
                            self.assertIs(session._read_scope, issued)
                            self.assertEqual(issued._deadline, first)
                    finally:
                        armed[0] = None
                self.assertEqual(len(tls.requests), before)
                reached.append(True)
                raise wire.WireFailure('fence_blocked', 'none')
            with patch.object(wire, '_authenticate', side_effect=observe):
                self.blocked(session)
            self.assertEqual(reached, [True])

    def test_actual_entered_later_none_or_generic_caller_keeps_fixed_code_and_owner_priority(self):
        with self.native_preparation() as (session, tls, _):
            reached = []
            def observe(selection, api, *, deadline, check_active):
                owner, before = artifacts._OWNERS[api], len(tls.requests)
                issued, first, calls, armed = session._read_scope, session._read_scope._deadline, [], [None]
                self.assertIs(type(issued), owned._ReadScope)
                issued._check(api)
                def caller():
                    calls.append(True)
                    if armed[0] is not None:
                        raise armed[0]
                end, active = owner._controls(deadline, caller)
                self.assertTrue(calls)
                self.assertLessEqual(end, first)
                variants = ((wire.WireFailure('cancelled', 'none'), 'transport_cancelled'),
                    (wire.WireFailure('timeout', 'none'), 'transport_deadline_exceeded'),
                    (wire.WireFailure('adapter_error', 'none'), 'artifact_transport_failed'),
                    (RuntimeError('PRIVATE_CALLBACK_SENTINEL'), 'artifact_transport_failed'))
                for error, expected in variants:
                    previous, armed[0] = len(calls), error
                    with self.subTest(expected=expected), self.assertRaises(safe.ConsumerError) as caught:
                        safe._check_budget(end, active)
                    self.assertIs(type(caught.exception), safe.ConsumerError)
                    self.assertEqual(caught.exception.code, expected)
                    self.assertEqual(len(calls), previous + 1)
                    self.assertIs(session._read_scope, issued)
                    self.assertEqual(issued._deadline, first)
                    armed[0] = None
                previous = len(calls)
                session.cancel()
                armed[0] = RuntimeError('PRIVATE_CALLBACK_SENTINEL')
                with self.assertRaisesRegex(safe.ConsumerError, '^transport_cancelled$'):
                    safe._check_budget(end, active)
                self.assertEqual(len(calls), previous)
                self.assertIs(session._read_scope, issued)
                self.assertEqual(issued._deadline, first)
                with self.assertRaisesRegex(safe.ConsumerError, '^transport_cancelled$'):
                    owner._controls(0, caller)
                self.assertEqual(len(calls), previous)
                self.assertEqual(len(tls.requests), before)
                self.assertIsNone(owner._report)
                reached.append(True)
                raise wire.WireFailure('cancelled', 'none')
            with patch.object(wire, '_authenticate', side_effect=observe):
                self.blocked(session, 'cancelled')
            self.assertEqual(reached, [True])


class ConsumerBudgetBridgeCases(unittest.TestCase):
    def test_consumer_without_publication_module_keeps_standalone_sanitization(self):
        source = str(Path(safe.__file__).parent)
        code = '''import sys, time
sys.path.insert(0, sys.argv[1])
import rc_consumer_io as safe
assert 'rc_publication_github' not in sys.modules
def caller():
    raise RuntimeError('PRIVATE_CALLBACK_SENTINEL')
try:
    safe._check_budget(time.monotonic()+10, caller)
except safe.ConsumerError as error:
    assert type(error) is safe.ConsumerError and str(error) == 'artifact_transport_failed'
else:
    raise AssertionError('missing standalone rejection')
assert 'rc_publication_github' not in sys.modules
'''
        completed = subprocess.run([sys.executable, '-B', '-c', code, source],
            capture_output=True, text=True, timeout=10)
        self.assertEqual((completed.returncode, completed.stdout, completed.stderr), (0, '', ''))

    def test_exact_non_none_wire_failure_preserves_identity_release_and_asset(self):
        asset = core.RemoteAsset(200, core.Asset('payload.zip', 'synthetic',
                                               'application/zip', 1, '1'*64))
        for code, effect in (('cancelled', 'unknown'), ('timeout', 'confirmed')):
            with self.subTest(effect=effect):
                error = wire.WireFailure(code, effect, release_id=100, asset=asset)
                def caller():
                    raise error
                with self.assertRaises(wire.WireFailure) as caught:
                    safe._check_budget(time.monotonic()+10, caller)
                self.assertIs(caught.exception, error)
                self.assertIs(caught.exception.asset, asset if effect == 'confirmed' else None)
                self.assertEqual(caught.exception.release_id, 100 if effect == 'confirmed' else None)

    def test_none_wire_failures_keep_original_fixed_consumer_codes(self):
        for code, expected in (('cancelled', 'transport_cancelled'),
                ('timeout', 'transport_deadline_exceeded'), ('adapter_error', 'artifact_transport_failed')):
            with self.subTest(code=code):
                error = wire.WireFailure(code, 'none')
                def caller():
                    raise error
                with self.assertRaises(safe.ConsumerError) as caught:
                    safe._check_budget(time.monotonic()+10, caller)
                self.assertIs(type(caught.exception), safe.ConsumerError)
                self.assertEqual(caught.exception.code, expected)

    def test_subclass_or_duck_effect_cannot_claim_wire_failure_passthrough(self):
        queried = []
        class Derived(wire.WireFailure):
            pass
        class Duck(RuntimeError):
            code = 'adapter_error'
            @property
            def effect(self):
                queried.append(True)
                raise RuntimeError('PRIVATE_EFFECT_SENTINEL')
        for error in (Derived('adapter_error', 'unknown'), Duck('PRIVATE_CALLBACK_SENTINEL')):
            def caller():
                raise error
            with self.assertRaisesRegex(safe.ConsumerError, '^artifact_transport_failed$'):
                safe._check_budget(time.monotonic()+10, caller)
        self.assertEqual(queried, [])
