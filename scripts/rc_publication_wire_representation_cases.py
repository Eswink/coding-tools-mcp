"""Actual held-native canonical-current error shape, never receipt authority."""
import unittest
import traceback
from unittest.mock import patch

import rc_publication_artifact_admission as artifacts
import rc_publication_github as wire
from rc_publication_metadata_effect_cases import MetadataEffectCases, MARKER, receipt
from rc_publication_native_stage_composition_cases import NativeStageCompositionCases


class WireRepresentationCases(unittest.TestCase):
    native_preparation = NativeStageCompositionCases.native_preparation
    blocked = NativeStageCompositionCases.blocked

    def test_actual_display_only_none_damage_and_invalid_none_are_distinct(self):
        from rc_consumer_io import ConsumerError
        rows = []
        with self.native_preparation() as (session, tls, _):
            def observe(selection, api, *, deadline, check_active):
                for field in ('args', 'notes', 'cause', 'context', 'code', 'effect', 'receipt'):
                    for code in ('cancelled', 'timeout', 'adapter_error'):
                        error = wire.WireFailure(code, 'none')
                        if field == 'args': error.args = (MARKER,)
                        elif field == 'notes': error.add_note(MARKER)
                        elif field == 'cause': error.__cause__ = RuntimeError(MARKER)
                        elif field == 'context':
                            error.__context__ = RuntimeError(MARKER)
                            error.__suppress_context__ = False
                        elif field == 'code': error.code = MARKER
                        elif field == 'effect': error.effect = MARKER
                        elif field == 'receipt': error.release_id = 100
                        before, calls, received = len(tls.requests), [], None
                        def caller():
                            calls.append(True)
                            raise error
                        try:
                            artifacts._OWNERS[api]._controls(deadline, caller)
                        except BaseException as caught:
                            received = caught
                        self.assertEqual(calls, [True])
                        self.assertEqual(len(tls.requests), before)
                        self.assertIsNone(artifacts._OWNERS[api]._report)
                        rows.append((field, code, received))
                raise wire.WireFailure('fence_blocked', 'none')
            with patch.object(wire, '_authenticate', side_effect=observe):
                self.blocked(session)
        self.assertEqual(len(rows), 21)
        for field, code, received in rows:
            with self.subTest(field=field, code=code):
                if field in ('code', 'effect', 'receipt'):
                    self.assertIs(type(received), wire.WireFailure)
                    self.assertEqual((received.effect, received.release_id, received.asset), ('unknown', None, None))
                    self.assertEqual(received.code, 'adapter_error' if field == 'code' else code)
                else:
                    self.assertIs(type(received), ConsumerError)
                    self.assertEqual(received.code, {'cancelled': 'transport_cancelled',
                        'timeout': 'transport_deadline_exceeded'}.get(code, 'artifact_transport_failed'))
                self.assertNotIn(MARKER, str(received))
                self.assertNotIn(MARKER, ''.join(traceback.format_exception(received)))

    def test_actual_optional_confirmed_and_nested_receipt_validation_without_hooks(self):
        hooks, rows = [], []
        class Trap:
            def __eq__(self, other):
                hooks.append('equality')
                raise RuntimeError(MARKER)
            def __repr__(self):
                hooks.append('repr')
                raise RuntimeError(MARKER)
        valid = [wire.WireFailure('timeout', 'confirmed', ident, asset)
            for ident, asset in ((None, None), (100, None), (None, receipt()), (100, receipt()))]
        empty_notes = wire.WireFailure('timeout', 'confirmed')
        empty_notes.__notes__ = []
        valid.append(empty_notes)
        shadow = receipt()
        object.__setattr__(shadow, '__post_init__', lambda: hooks.append('remote-shadow'))
        object.__setattr__(shadow.asset, '__post_init__', lambda: hooks.append('asset-shadow'))
        valid.append(wire.WireFailure('timeout', 'confirmed', asset=shadow))
        bad = []
        for ident in (True, 0, 2**63):
            error = wire.WireFailure('timeout', 'confirmed', asset=receipt())
            error.release_id = ident
            bad.append(error)
        nested = receipt()
        object.__setattr__(nested.asset, 'sha256', MARKER)
        bad.append(wire.WireFailure('timeout', 'confirmed', asset=nested))
        trap = wire.WireFailure('timeout', 'confirmed', release_id=100, asset=receipt())
        trap.args = (Trap(),)
        with self.native_preparation() as (session, tls, _):
            def observe(selection, api, *, deadline, check_active):
                for error, kind in [(e, 'valid') for e in valid] + [(e, 'bad-receipt') for e in bad] + [(trap, 'dirty-args')]:
                    calls, received, before = [], None, len(tls.requests)
                    def caller():
                        calls.append(True)
                        raise error
                    scope, first = session._read_scope, session._read_scope._deadline
                    try:
                        artifacts._OWNERS[api]._controls(deadline, caller)
                    except BaseException as caught:
                        received = caught
                    self.assertEqual(calls, [True])
                    self.assertEqual(len(tls.requests), before)
                    self.assertIs(session._read_scope, scope)
                    self.assertEqual(scope._deadline, first)
                    self.assertIsNone(artifacts._OWNERS[api]._report)
                    rows.append((error, kind, received))
                raise wire.WireFailure('fence_blocked', 'none')
            with patch.object(wire, '_authenticate', side_effect=observe):
                self.blocked(session)
        self.assertEqual(hooks, [])
        self.assertEqual(len(rows), 11)
        for error, kind, received in rows:
            with self.subTest(kind=kind):
                self.assertIs(type(received), wire.WireFailure)
                if kind == 'valid':
                    self.assertIs(received, error)
                elif kind == 'bad-receipt':
                    self.assertIsNot(received, error)
                    self.assertEqual((received.effect, received.release_id, received.asset), ('unknown', None, None))
                else:
                    self.assertTrue(received is not error)
                    self.assertEqual((received.code, received.effect, received.release_id), ('timeout', 'confirmed', 100))
                    self.assertIs(received.asset, error.asset)
                    self.assertEqual(received.args, ('timeout',))
        self.assertEqual(hooks, [])
