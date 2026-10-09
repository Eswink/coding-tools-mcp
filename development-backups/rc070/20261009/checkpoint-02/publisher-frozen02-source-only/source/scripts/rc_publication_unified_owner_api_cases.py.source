"""Actual entered owners and verified TLS across both adapters; no authority."""
from contextlib import contextmanager
from types import SimpleNamespace
import time
import unittest
from unittest.mock import patch

import rc_consumer_io as safe
import rc_publication_artifact_admission as artifacts
from rc_publication_artifact_admission_cases import ArtifactAdmissionCases
import rc_publication_contract as core
import rc_publication_executor as executor
import rc_publication_github as wire
import rc_publication_stage as stage


class UnifiedOwnerAPICases(unittest.TestCase):
    @contextmanager
    def fixture(self):
        # Reuse the real TLS/FINAL fixture without inheriting its20 test methods.
        with ArtifactAdmissionCases.fixture(self) as value:
            yield value

    @contextmanager
    def entered(self, f, api, active=lambda: None):
        owner = artifacts._ArtifactOwner(f.root, f.selection, api, temporary_parent=f.parent)
        end = time.monotonic() + 60
        try:
            owner.enter(deadline=end, check_active=active)
            self.assertIs(artifacts._OWNERS.get(api), owner)
            self.assertTrue(owner.entered)
            yield owner, end
        finally:
            owner.close()
            owner.stage.close()
            self.assertNotIn(api, artifacts._OWNERS)

    def failure(self, action, code):
        with self.assertRaises(safe.ConsumerError) as result:
            stage.snapshot._call(action)
        self.assertEqual(result.exception.code, code)
        self.assertEqual(str(result.exception), code)

    def real_get_observer(self, path, armed):
        original = wire.GitHub.get
        def observed(api, suffix, **kwargs):
            # The fixed original method still executes verified TLS and polls.
            value = original(api, suffix, **kwargs)
            if suffix == path:
                armed.append(True)
            return value
        return patch.object(wire.GitHub, 'get', observed)

    def test_real_two_adapter_observation_retains_one_owned_deadline(self):
        with self.fixture() as (f, tls, api), self.entered(f, api) as (owner, end):
            rows, original = [], wire.GitHub.get
            def observed(current, path, **kwargs):
                rows.append((path, kwargs['deadline'], kwargs['check_active']))
                return original(current, path, **kwargs)
            with patch.object(wire.GitHub, 'get', observed):
                actual = stage._observe(f.root, f.selection, owner.adapter,
                                        deadline=end+120, check_active=lambda: None)
            self.assertEqual(actual, owner.stage._observation)
            self.assertTrue(rows)
            self.assertEqual({r[1] for r in rows}, {end})
            self.assertEqual(sum('/git/ref/tags/' in r[0] for r in rows), 2)
            self.assertTrue(all(callable(r[2]) for r in rows))
            self.assertTrue(all(r[0] == 'GET' and r[3] == b'' for r in tls.requests))

    def test_exact_owned_identity_retains_callback_without_spoofed_scope_or_renewal(self):
        from rc_publication_native_admission_fixture import _native_session
        end = time.monotonic()+60
        clock = SimpleNamespace(monotonic=lambda: end-executor.OPERATION_SECONDS)
        def native_enter(owner, session, tls, trace):
            original = trace.entered[0][1]
            self.assertIs(owner._owner_active, original)
            self.assertIs(owner._session, session)
            before = len(tls.requests)
            scoped, active = owner._controls(end+120, original)
            self.assertEqual(scoped, end)
            self.assertIs(active, trace.controls[-1][1])
            self.assertIs(trace.controls[-1][2], session._read_scope)
            self.failure(lambda: owner._controls(0, original), 'transport_deadline_exceeded')
            scoped, later = owner._controls(end+120, lambda: None)
            self.assertEqual(scoped, end); self.assertIsNot(later, original)
            self.assertEqual(len(tls.requests), before)
            session._cancelled.set()
            self.failure(lambda: owner._controls(end+120, lambda: None), 'transport_cancelled')
            self.failure(lambda: owner.stage.revalidate(deadline=end+120,
                         check_active=lambda: None), 'transport_cancelled')
            self.assertEqual(len(tls.requests), before)
        with _native_session(self, clock=clock, after_enter=native_enter) as (session, _, _, _):
            with self.assertRaises(wire.WireFailure) as error:
                session.run_until_pause()
            self.assertEqual((error.exception.code, error.exception.effect), ('cancelled', 'none'))
        # Actual pause replaces the old handwritten session deadline=None.
        with _native_session(self) as (session, tls, _, trace):
            self.assertIsInstance(session.run_until_pause().action, core.AwaitPublishRequest)
            owner, original, previous, _ = trace.entered[0]
            self.assertTrue(previous._retired)
            self.assertIsNone(session._deadline)
            before = len(tls.requests)
            self.failure(lambda: owner._controls(previous._deadline+120, original), 'artifact_scope_unavailable')
            self.assertEqual(len(tls.requests), before)
        # Ordinary spoofed attributes belong only to a real standalone client.
        with self.fixture() as (f, tls, api), executor.PublisherSession(f.root,
                f.selection, 'fixture-token', temporary_parent=f.parent) as session:
            stopped = []
            def original():
                if stopped:
                    raise wire.WireFailure('cancelled', 'none')
            original.__self__, original.__func__ = session, executor.PublisherSession._check_active
            with self.entered(f, api, original) as (owner, end):
                self.assertIs(owner.stage._check_active, original)
                self.assertIsNone(owner._session)
                self.assertIsNone(api._credential._session_owner)
                before = len(tls.requests)
                scoped, active = owner._controls(end+120, original)
                self.assertEqual(scoped, end); self.assertIs(active, original)
                self.failure(lambda: owner._controls(0, original), 'transport_deadline_exceeded')
                scoped, later = owner._controls(end+120, lambda: None)
                self.assertEqual(scoped, end); self.assertIsNot(later, original)
                stopped.append(True)
                self.failure(lambda: owner._controls(end+120, lambda: None), 'transport_cancelled')
                self.failure(lambda: owner.stage.revalidate(deadline=end+120,
                             check_active=lambda: None), 'transport_cancelled')
                self.assertEqual(len(tls.requests), before)

    def test_none_owned_callback_keeps_callable_stage_controls_and_original_deadline(self):
        with self.fixture() as (f, tls, api), self.entered(f, api, None) as (owner, end):
            self.assertIsNone(owner._owner_active)
            self.assertIsNone(owner._session)
            self.assertTrue(callable(owner.stage._check_active))
            self.assertTrue(callable(owner.adapter.active))
            actual = stage._observe(f.root, f.selection, owner.adapter,
                                    deadline=end+120, check_active=lambda: None)
            self.assertEqual(actual, owner.stage._observation)
            scoped, active = owner._controls(end+120, None)
            self.assertEqual(scoped, end)
            self.assertTrue(callable(active))
            self.assertIsNone(active())
            with self.assertRaises(wire.WireFailure) as result:
                wire._authenticate(f.selection, api, deadline=end+120, check_active=None)
            self.assertEqual((result.exception.code, result.exception.effect), ('fence_blocked', 'none'))
            self.assertEqual(sum(row[3] == 'unknown' for row in owner._report.rows), 58)
            before = len(tls.requests)
            with patch.object(safe, 'time', SimpleNamespace(monotonic=lambda: end+1)):
                self.failure(lambda: owner.stage.revalidate(deadline=end+120,
                             check_active=lambda: None), 'transport_deadline_exceeded')
            self.assertEqual(len(tls.requests), before)
            self.assertTrue(all(row[0] == 'GET' and row[3] == b'' for row in tls.requests))

    def test_entered_owner_controls_survive_noop_revalidation_and_authentication(self):
        for cancel in (True, False):
            with self.subTest(cancel=cancel), self.fixture() as (f, tls, api):
                stopped = []
                def active():
                    if stopped:
                        raise wire.WireFailure('cancelled', 'none')
                with self.entered(f, api, active) as (owner, end):
                    before = len(tls.requests)
                    if cancel:
                        stopped.append(True)
                    clock = time.monotonic() if cancel else end+1
                    with patch.object(safe, 'time', SimpleNamespace(monotonic=lambda: clock)):
                        self.failure(lambda: owner.stage.revalidate(deadline=end+120,
                            check_active=lambda: None),
                            'transport_cancelled' if cancel else 'transport_deadline_exceeded')
                        with self.assertRaises(wire.WireFailure) as result:
                            wire._authenticate(f.selection, api, deadline=end+120,
                                               check_active=lambda: None)
                        self.assertEqual((result.exception.code, result.exception.effect),
                                         ('cancelled' if cancel else 'timeout', 'none'))
                    self.assertEqual(len(tls.requests), before)
                    self.assertIsNone(owner._report)

    def test_real_source_tag_read_preserves_entered_owner_cancellation(self):
        with self.fixture() as (f, tls, api):
            stopped = []
            def active():
                if stopped:
                    raise wire.WireFailure('cancelled', 'none')
            with self.entered(f, api, active) as (owner, end):
                route, target = tls.route, wire.ROOT+'/git/ref/tags/'+f.selection.subject.tag
                def cancel(method, path, headers, body):
                    if path == target:
                        stopped.append(True)
                    return route(method, path, headers, body)
                tls.route = cancel
                before = len(tls.requests)
                self.failure(lambda: owner.stage.revalidate(deadline=end+120,
                    check_active=lambda: None), 'transport_cancelled')
                self.assertEqual(stopped, [True])
                self.assertEqual([r[1] for r in tls.requests[before:]], [target])
                self.assertIsNone(owner._report)

    def test_real_shorter_api_deadline_cannot_be_renewed_by_owned_longer_scope(self):
        with self.fixture() as (f, tls, api), self.entered(f, api) as (owner, end):
            route, reached = tls.route, []
            def delayed(method, path, headers, body):
                if path == wire.ROOT:
                    reached.append(True)
                    time.sleep(0.3)
                return route(method, path, headers, body)
            tls.route = delayed
            before, start = len(tls.requests), time.monotonic()
            short = start+0.15
            self.failure(lambda: stage._APIReads(owner.adapter, short, lambda: None).get('/'),
                         'transport_deadline_exceeded')
            self.assertEqual(reached, [True])
            self.assertEqual(len(tls.requests)-before, 1)
            self.assertLess(time.monotonic()-start, 1)
            self.assertEqual(owner.adapter.deadline, end)

    def tls_callback_failure(self, reason):
        with self.fixture() as (f, tls, api):
            stopped = []
            def active():
                if stopped:
                    if reason == 'return':
                        return 1
                    raise reason('private-body-never-output')
            with self.entered(f, api, active) as (owner, end):
                route, reached = tls.route, []
                def interrupted(method, path, headers, body):
                    if path == wire.ROOT:
                        reached.append(True)
                        stopped.append(True)
                    return route(method, path, headers, body)
                tls.route = interrupted
                before = len(tls.requests)
                action = lambda: stage._APIReads(owner.adapter, end+120, lambda: None).get('/')
                if reason in (KeyboardInterrupt, SystemExit):
                    with self.assertRaises(reason) as result:
                        action()
                    self.assertEqual(result.exception.args, () if reason is KeyboardInterrupt else (1,))
                else:
                    self.failure(action, 'artifact_transport_failed')
                self.assertEqual(reached, [True])
                self.assertEqual(len(tls.requests)-before, 1)

    def test_real_owned_midread_callback_failure_retains_closed_code(self):
        for reason in (RuntimeError, 'return'):
            with self.subTest(reason=reason):
                self.tls_callback_failure(reason)

    def test_real_owned_midread_interruptions_have_sanitized_arguments(self):
        for reason in (KeyboardInterrupt, SystemExit):
            with self.subTest(reason=reason):
                self.tls_callback_failure(reason)

    def test_owned_local_interruption_never_reclassifies_uncertain_wire_effect(self):
        for effect in ('unknown', 'confirmed'):
            for reason in (RuntimeError, KeyboardInterrupt):
                with self.subTest(effect=effect, reason=reason), self.fixture() as (f, tls, api):
                    stopped = []
                    def active():
                        if stopped:
                            raise reason('private-body-never-output')
                    with self.entered(f, api, active) as (owner, end):
                        original, route = wire.GitHub.get, tls.route
                        asset = core.RemoteAsset(200, f.plan.assets[0])
                        failures = []
                        def uncertain(current, path, **kwargs):
                            try:
                                return original(current, path, **kwargs)
                            except wire.WireFailure as error:
                                self.assertEqual(error.effect, 'none')
                                changed = wire.WireFailure(error.code, effect, 100, asset)
                                failures.append(changed)
                                raise changed
                        def interrupt(method, path, headers, body):
                            if path == wire.ROOT:
                                stopped.append(True)
                            return route(method, path, headers, body)
                        tls.route = interrupt
                        before = len(tls.requests)
                        with patch.object(wire.GitHub, 'get', uncertain), self.assertRaises(wire.WireFailure) as result:
                            stage._APIReads(owner.adapter, end+120, lambda: None).get('/')
                        self.assertEqual(failures, [result.exception])
                        self.assertEqual(result.exception.effect, effect)
                        self.assertEqual(result.exception.release_id, 100 if effect == 'confirmed' else None)
                        self.assertIs(result.exception.asset, asset if effect == 'confirmed' else None)
                        self.assertEqual(result.exception.code, 'cancelled' if reason is KeyboardInterrupt else 'adapter_error')
                        self.assertEqual(len(tls.requests)-before, 1)

    def priority(self, *, receipt, bad, cancel):
        with self.fixture() as (f, tls, api):
            armed = []
            def active():
                if armed and cancel:
                    raise wire.WireFailure('cancelled', 'none')
            with self.entered(f, api, active) as (owner, end):
                target = '/actions/artifacts/14' if receipt else '/git/ref/tags/'+f.selection.subject.tag
                if bad:
                    if receipt:
                        f.api.data[target]['workflow_run']['repository_id'] = 1
                    else:
                        f.api.data[target]['object']['sha'] = '0'*40
                real_clock = time.monotonic
                timer = SimpleNamespace(monotonic=lambda: end+1 if armed and not cancel else real_clock())
                before = len(tls.requests)
                with self.real_get_observer(target, armed), patch.object(safe, 'time', timer):
                    action = (lambda: stage._observe(f.root, f.selection, owner.adapter,
                        deadline=end, check_active=active)) if receipt else (
                        lambda: stage._source(f.root, f.selection.subject, owner.adapter,
                            deadline=end, check_active=active))
                    code = ('receipt_owner_mismatch' if receipt else 'lightweight_tag_required') if bad else (
                        'transport_cancelled' if cancel else 'transport_deadline_exceeded')
                    self.failure(action, code)
                self.assertEqual(armed, [True])
                self.assertTrue(len(tls.requests) > before)
                self.assertEqual(tls.requests[-1][1], wire.ROOT+target)
                self.assertIsNone(owner._report)

    def test_bad_tag_metadata_precedes_cancel_first_observed_after_real_get_return(self):
        self.priority(receipt=False, bad=True, cancel=True)

    def test_bad_tag_metadata_precedes_expiry_first_observed_after_real_get_return(self):
        self.priority(receipt=False, bad=True, cancel=False)

    def test_bad_receipt_metadata_precedes_late_cancel_and_expiry(self):
        for cancel in (True, False):
            with self.subTest(cancel=cancel):
                self.priority(receipt=True, bad=True, cancel=cancel)

    def test_valid_tag_still_rejects_late_cancel_and_expiry_without_second_get(self):
        for cancel in (True, False):
            with self.subTest(cancel=cancel):
                self.priority(receipt=False, bad=False, cancel=cancel)

    def test_valid_last_receipt_still_checks_final_owned_fence(self):
        for cancel in (True, False):
            with self.subTest(cancel=cancel):
                self.priority(receipt=True, bad=False, cancel=cancel)

    def test_paused_bound_session_cannot_reauthenticate_with_caller_scope(self):
        from rc_publication_native_admission_fixture import _native_session
        end = time.monotonic()+60
        with _native_session(self) as (session, tls, _, trace):
            result = session.run_until_pause()
            self.assertIsInstance(result.action, core.AwaitPublishRequest)
            owner, _, previous, _ = trace.entered[0]
            self.assertIs(owner._session, session)
            self.assertIsNone(session._deadline)
            self.assertIsNone(session._read_scope)
            self.assertTrue(previous._retired)
            end = previous._deadline
            self.assertGreater(end+120, previous._deadline)
            before = len(tls.requests)
            with self.assertRaisesRegex(safe.ConsumerError, '^artifact_scope_unavailable$'):
                artifacts.authenticate_artifacts(session._api, session._api.selection,
                    deadline=end+120, check_active=lambda: None)
            self.assertEqual(len(tls.requests), before)
            self.assertIsNone(owner._report)


if __name__ == '__main__':
    unittest.main()
