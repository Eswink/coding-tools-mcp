"""Actual held-native metadata effects and bounded synthetic error output."""
from pathlib import Path
import json
import subprocess
import sys
import time
import traceback
import unittest
from unittest.mock import patch

import rc_consumer_io as safe
import rc_consumer_snapshot as snapshot
import rc_publication_admission as metadata
import rc_publication_artifact_admission as artifacts
import rc_publication_contract as core
import rc_publication_github as wire
import rc_publication_request as owned
from rc_publication_native_stage_composition_cases import NativeStageCompositionCases

MARKER = 'SYNTHETIC_PRIVATE_EFFECT_MARKER'


def receipt():
    return core.RemoteAsset(200, core.Asset('payload.zip', 'synthetic',
        'application/zip', 1, '1' * 64))


class MetadataEffectCases(unittest.TestCase):
    native_preparation = NativeStageCompositionCases.native_preparation
    blocked = NativeStageCompositionCases.blocked

    def controls(self, session, api, deadline, caller):
        owner, scope = artifacts._OWNERS[api], session._read_scope
        self.assertIs(owner, session._artifact_owner)
        self.assertIs(owner.stage, session._stage)
        self.assertIs(owner.selection, api.selection)
        self.assertIs(owner._session, session)
        self.assertIs(type(scope), owned._ReadScope)
        scope._check(api)
        first = scope._deadline
        end, active = owner._controls(deadline, caller)
        self.assertLessEqual(end, min(first, session._deadline, deadline))
        return owner, scope, first, end, active

    def test_actual_first_prepare_poll_preserves_original_non_none_and_suppressed_context(self):
        rows = []
        with self.native_preparation() as (session, tls, _):
            def observe(selection, api, *, deadline, check_active):
                for code, effect, hidden in (('cancelled', 'unknown', False),
                        ('timeout', 'confirmed', False), ('timeout', 'confirmed', True)):
                    armed, calls = [None], []
                    def caller():
                        calls.append(True)
                        if armed[0] is not None:
                            raise armed[0]
                    owner, scope, first, end, active = self.controls(session, api, deadline, caller)
                    error = wire.WireFailure(code, effect, release_id=100, asset=receipt())
                    if hidden:
                        error.__context__ = RuntimeError(MARKER)
                        error.__suppress_context__ = True
                    before, count, armed[0] = len(tls.requests), len(calls), error
                    received = None
                    try:
                        artifacts.prepare_admission(selection, api, deadline=end, check_active=active)
                    except BaseException as caught:
                        received = caught
                    rows.append((received, error, hidden))
                    self.assertEqual(len(calls), count + 1)
                    self.assertEqual(len(tls.requests), before)
                    self.assertIs(session._read_scope, scope)
                    self.assertEqual(scope._deadline, first)
                    self.assertIsNone(owner._report)
                raise wire.WireFailure('fence_blocked', 'none')
            with patch.object(wire, '_authenticate', side_effect=observe):
                self.blocked(session)
        self.assertEqual(len(rows), 3)
        for received, error, hidden in rows:
            with self.subTest(effect=error.effect, hidden=hidden):
                self.assertIs(received, error)
                self.assertEqual((received.code, received.effect, received.release_id, received.asset),
                    (error.code, error.effect, error.release_id, error.asset))
                self.assertNotIn(MARKER, ''.join(traceback.format_exception(received)))

    def postdecode(self, target):
        rows = []
        with self.native_preparation() as (session, tls, _):
            def observe(selection, api, *, deadline, check_active):
                for code, effect in (('cancelled', 'unknown'), ('timeout', 'confirmed')):
                    armed, calls, paths, exposed, sources, current = [None], [], [], [], [], [None]
                    def caller():
                        calls.append(True)
                        if armed[0] is not None:
                            raise armed[0]
                    owner, scope, first, end, active = self.controls(session, api, deadline, caller)
                    error = wire.WireFailure(code, effect, release_id=100, asset=receipt())
                    original_json, original_get, original_source = wire._json, wire.GitHub.get, metadata._source
                    def decoded(raw):
                        value = original_json(raw)
                        if current[0] == target:
                            armed[0] = error
                        return value
                    def canonical(client, path, **kwargs):
                        paths.append(path)
                        current[0] = path
                        try:
                            return original_get(client, path, **kwargs)
                        except wire.WireFailure as caught:
                            exposed.append(caught)
                            raise
                        finally:
                            current[0] = None
                    def validated_source(*args, **kwargs):
                        value = original_source(*args, **kwargs)
                        sources.append(value)
                        return value
                    before, received = len(tls.requests), None
                    with patch.object(wire, '_json', side_effect=decoded), patch.object(
                            wire.GitHub, 'get', new=canonical), patch.object(
                            metadata, '_source', side_effect=validated_source):
                        try:
                            artifacts.prepare_admission(selection, api, deadline=end, check_active=active)
                        except BaseException as caught:
                            received = caught
                    expected = []
                    for source in sources:
                        expected.extend(('/', '/git/ref/' + source['ref']['ref'][5:],
                            '/git/commits/' + source['commit']['sha']))
                        expected.extend('/git/trees/' + sha for sha in source['trees'])
                    expected.append(target)
                    self.assertEqual(paths, expected)
                    self.assertEqual(len(sources), 0 if target == '/' else 2)
                    self.assertEqual(len(tls.requests) - before, len(expected))
                    self.assertEqual(len(exposed), 1)
                    self.assertIs(armed[0], error)
                    self.assertIs(session._read_scope, scope)
                    self.assertEqual(scope._deadline, first)
                    self.assertIsNone(owner._report)
                    rows.append((received, exposed[0], error))
                raise wire.WireFailure('fence_blocked', 'none')
            with patch.object(wire, '_authenticate', side_effect=observe):
                self.blocked(session)
        for received, exposed, error in rows:
            with self.subTest(effect=error.effect):
                self.assertIs(received, exposed)
                self.assertIs(type(received), wire.WireFailure)
                self.assertEqual((received.code, received.effect, received.release_id, received.asset),
                    (error.code, error.effect, error.release_id, error.asset))
        self.assertEqual(len(rows), 2)

    def test_actual_root_get_preserves_public_canonical_non_none_error(self):
        self.postdecode('/')

    def test_actual_observed_workflow_get_preserves_public_canonical_non_none_error(self):
        self.postdecode('/actions/workflows/dot-rc-integration.yml')

    def test_actual_modified_error_fields_are_safe_and_never_infer_none(self):
        rows = []
        variants = ('code', 'args', 'notes', 'cause', 'context', 'effect', 'release_id', 'asset', 'none_effect')
        with self.native_preparation() as (session, tls, _):
            def observe(selection, api, *, deadline, check_active):
                for field in variants:
                    error = wire.WireFailure('timeout', 'confirmed', release_id=100, asset=receipt())
                    if field == 'code': error.code = MARKER
                    elif field == 'args': error.args = (MARKER,)
                    elif field == 'notes': error.add_note(MARKER)
                    elif field == 'cause': error.__cause__ = RuntimeError(MARKER)
                    elif field == 'context':
                        error.__context__ = RuntimeError(MARKER)
                        error.__suppress_context__ = False
                    elif field == 'effect': error.effect = MARKER
                    elif field == 'release_id': error.release_id = MARKER
                    elif field == 'asset': error.asset = MARKER
                    elif field == 'none_effect': error.effect = 'none'
                    calls = []
                    def caller():
                        calls.append(True)
                        raise error
                    before, scope = len(tls.requests), session._read_scope
                    first, received = scope._deadline, None
                    try:
                        artifacts._OWNERS[api]._controls(deadline, caller)
                    except BaseException as caught:
                        received = caught
                    self.assertEqual(calls, [True])
                    self.assertEqual(len(tls.requests), before)
                    self.assertIs(session._read_scope, scope)
                    self.assertEqual(scope._deadline, first)
                    self.assertIsNone(artifacts._OWNERS[api]._report)
                    output = ''.join(traceback.format_exception(received))
                    print(json.dumps(dict(scope='actual-held-amended-wire-output', field=field,
                        error_type=type(received).__name__, string_has_marker=MARKER in str(received),
                        trace_has_marker=MARKER in output, callback_calls=len(calls), new_gets=0)))
                    rows.append((field, received, error))
                raise wire.WireFailure('fence_blocked', 'none')
            with patch.object(wire, '_authenticate', side_effect=observe):
                self.blocked(session)
        for field, received, original in rows:
            with self.subTest(field=field):
                self.assertIs(type(received), wire.WireFailure)
                self.assertIsNot(received, original)
                expected = 'unknown' if field in ('effect', 'release_id', 'asset', 'none_effect') else 'confirmed'
                self.assertEqual(received.effect, expected)
                self.assertEqual(received.code, 'adapter_error' if field == 'code' else 'timeout')
                self.assertEqual(received.release_id, 100 if expected == 'confirmed' else None)
                self.assertIs(received.asset, original.asset if expected == 'confirmed' else None)
                self.assertNotIn(MARKER, str(received))
                self.assertNotIn(MARKER, ''.join(traceback.format_exception(received)))

    def test_actual_none_generic_and_later_native_cancel_keep_fixed_priority(self):
        rows = []
        with self.native_preparation() as (session, tls, _):
            def observe(selection, api, *, deadline, check_active):
                armed, calls = [None], []
                def caller():
                    calls.append(True)
                    if armed[0] is not None:
                        raise armed[0]
                owner, scope, first, end, active = self.controls(session, api, deadline, caller)
                variants = ((wire.WireFailure('cancelled', 'none'), 'cancelled'),
                    (wire.WireFailure('timeout', 'none'), 'timeout'),
                    (wire.WireFailure('adapter_error', 'none'), 'adapter_error'),
                    (RuntimeError(MARKER), 'adapter_error'))
                for error, expected in variants:
                    armed[0], count, before = error, len(calls), len(tls.requests)
                    received = None
                    try:
                        artifacts.prepare_admission(selection, api, deadline=end, check_active=active)
                    except BaseException as caught:
                        received = caught
                    rows.append((received, expected))
                    self.assertEqual(len(calls), count + 1)
                    self.assertEqual(len(tls.requests), before)
                armed[0] = wire.WireFailure('timeout', 'unknown')
                count, before = len(calls), len(tls.requests)
                session.cancel()
                with self.assertRaises(wire.WireFailure) as caught:
                    artifacts.prepare_admission(selection, api, deadline=end, check_active=active)
                rows.append((caught.exception, 'cancelled'))
                self.assertEqual(len(calls), count)
                self.assertEqual(len(tls.requests), before)
                self.assertIs(session._read_scope, scope)
                self.assertEqual(scope._deadline, first)
                self.assertIsNone(owner._report)
                raise wire.WireFailure('cancelled', 'none')
            with patch.object(wire, '_authenticate', side_effect=observe):
                self.blocked(session, 'cancelled')
        for error, code in rows:
            self.assertIs(type(error), wire.WireFailure)
            self.assertEqual((error.code, error.effect, error.release_id, error.asset), (code, 'none', None, None))
            self.assertNotIn(MARKER, ''.join(traceback.format_exception(error)))


class SnapshotEffectBoundaryCases(unittest.TestCase):
    def test_actual_non_none_identity_and_other_snapshot_sanitizers(self):
        class Derived(wire.WireFailure): pass
        queried = []
        class Duck(ValueError):
            @property
            def effect(self):
                queried.append(True)
                raise RuntimeError(MARKER)
        for error in (wire.WireFailure('timeout', 'unknown'),
                wire.WireFailure('cancelled', 'confirmed', release_id=100, asset=receipt())):
            def failed(): raise error
            received = None
            try:
                snapshot._call(failed)
            except BaseException as caught:
                received = caught
            with self.subTest(effect=error.effect):
                self.assertIs(type(received), wire.WireFailure)
                self.assertIs(received, error)
        for error in (wire.WireFailure('timeout', 'none'), Derived('timeout', 'unknown'),
                Duck(MARKER), ValueError(MARKER), OSError(MARKER)):
            def failed(): raise error
            with self.subTest(type=type(error).__name__), self.assertRaisesRegex(
                    safe.ConsumerError, '^invalid_snapshot$'):
                snapshot._call(failed)
        self.assertEqual(queried, [])
        error = safe.ConsumerError('transport_cancelled')
        def failed(): raise error
        with self.assertRaises(safe.ConsumerError) as caught:
            snapshot._call(failed)
        self.assertIs(caught.exception, error)

    def test_standalone_snapshot_does_not_import_publication(self):
        code = '''import sys
sys.path.insert(0, sys.argv[1])
import rc_consumer_snapshot as snapshot
from rc_consumer_io import ConsumerError
assert 'rc_publication_github' not in sys.modules
def failed(): raise ValueError('SYNTHETIC_PRIVATE_EFFECT_MARKER')
try: snapshot._call(failed)
except ConsumerError as error:
    assert str(error) == 'invalid_snapshot'
else: raise AssertionError('missing rejection')
assert 'rc_publication_github' not in sys.modules
'''
        completed = subprocess.run([sys.executable, '-B', '-c', code, str(Path(snapshot.__file__).parent)],
            capture_output=True, text=True, timeout=10)
        self.assertEqual((completed.returncode, completed.stdout, completed.stderr), (0, '', ''))


class StageCaptureDiagnosticCases(unittest.TestCase):
    def test_original_later_effect_cases_capture_actual_fixed_consumer_cause(self):
        from rc_publication_source_budget_cases import SourceBudgetCases
        original, recorded = artifacts._ArtifactOwner._capture, []
        def observed(owner, **kwargs):
            try:
                return original(owner, **kwargs)
            except safe.ConsumerError as error:
                session, scope = owner._session, owner._session._read_scope
                self.assertIs(owner, session._artifact_owner)
                self.assertIs(scope._owner, session._owner)
                self.assertIs(owner.api, session._api)
                self.assertIs(owner.selection, session._api.selection)
                self.assertIs(type(scope), owned._ReadScope)
                converted = artifacts._wire_failure(error)
                recorded.append(dict(phase=session._inflight.kind, original_type=type(error).__name__,
                    original_code=error.code, converted_code=converted.code, converted_effect=converted.effect,
                    first_deadline=scope._deadline, current_deadline=session._deadline))
                raise
        case = SourceBudgetCases('test_later_source_cancel_and_timeout_preserve_existing_mutation_effects')
        result = unittest.TestResult()
        with patch.object(artifacts._ArtifactOwner, '_capture', new=observed):
            case.run(result)
        print(json.dumps(dict(scope='unchanged-original-method-corrected-fixture-diagnostic',
            original_id=case.id(), original_failures=len(result.failures), original_errors=len(result.errors),
            original_tests_run=result.testsRun, actual_capture_errors=recorded), sort_keys=True))
        self.assertEqual(result.testsRun, 1)
        self.assertEqual((len(result.failures), len(result.errors)), (0, 0))
        self.assertEqual(len(recorded), 8)
        self.assertEqual(sum(row['original_code'] == 'transport_cancelled' for row in recorded), 4)
        self.assertEqual(sum(row['original_code'] == 'transport_deadline_exceeded' for row in recorded), 4)
        for row in recorded:
            self.assertEqual(row['converted_effect'], 'none')
            self.assertEqual(row['converted_code'],
                'cancelled' if row['original_code'] == 'transport_cancelled' else 'timeout')
