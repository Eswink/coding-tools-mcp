"""Real stage/worker/TLS lifecycle sketches; synthetic release authority only."""
from contextlib import contextmanager
import os
from unittest.mock import patch
import unittest

import rc_consumer_io as safe
import rc_publication_contract as core
import rc_publication_executor_cases as old
import rc_publication_github as wire
import rc_publication_retirement as retirement
import rc_publication_stage as stage
import rc_publication_staging_budget_cases as previous
from rc_publication_stage_cases import publisher_fixture, artifact_worker


class StageRetirementLifetimeCases(unittest.TestCase):
    session = previous.StagingBudgetCases.session
    children_exited = previous.StagingBudgetCases.children_exited
    bindings = previous.StagingBudgetCases.bindings
    activation_failed = previous.StagingBudgetCases.activation_failed
    failed_run = previous.StagingBudgetCases.failed_run
    blocked_download = previous.StagingBudgetCases.blocked_download
    request = staticmethod(old.ExecutorCases.request)
    mutations = staticmethod(old.ExecutorCases.mutations)

    @contextmanager
    def recording(self, **kwargs):
        with previous.StagingBudgetCases.recording(self, **kwargs) as seen:
            self.seen = seen
            yield seen

    @contextmanager
    def real_stage(self):
        with publisher_fixture() as fixture, artifact_worker(fixture):
            owner = stage.stage_selected(fixture.root, fixture.selection, fixture.api,
                                         temporary_parent=fixture.parent)
            try:
                owner.__enter__()
                yield owner, fixture
            finally:
                owner.close()

    @contextmanager
    def retirement_trace(self):
        original, events = stage.retire_staged, []
        def retiring(owners, **kwargs):
            paths = tuple(item.root.path for item in owners if item.root is not None and item.root.path)
            children = tuple(child.poll() for child in self.seen.children)
            try:
                return original(owners, **kwargs)
            finally:
                events.append(dict(retain=kwargs.get('retain'), children=children,
                                   existed=tuple(path.exists() for path in paths), paths=paths))
        with patch.object(stage, 'retire_staged', side_effect=retiring):
            yield events

    def test_real_stage_keeps_six_roots_and_handles_until_close(self):
        with self.real_stage() as (owner, fixture):
            self.assertEqual((len(owner._roots), len(owner._handles), len(owner._retirements)), (6, 6, 6))
            self.assertTrue(all(root.path.is_dir() for root in owner._roots))
            self.assertTrue(all(not handle.closed for handle in owner._handles))
            self.assertEqual(owner.plan.assets, fixture.plan.assets)
            self.assertEqual(owner.plan_bytes, fixture.plan_bytes)
            self.assertEqual(owner.provenance_bytes, fixture.provenance_bytes)
            paths = tuple(root.path for root in owner._roots)
            owner.close()
            self.assertTrue(all(not path.exists() for path in paths))
            self.assertTrue(fixture.source.bundle.exists())

    def test_real_success_closes_handles_before_retiring_all_six_roots(self):
        with self.real_stage() as (owner, _):
            unlink, events = os.unlink, []
            def removed(name, *, dir_fd):
                self.assertTrue(all(handle.closed for handle in owner._handles))
                self.assertTrue(all(root.fd is None for root in owner._roots))
                events.append(name)
                return unlink(name, dir_fd=dir_fd)
            with patch.object(retirement.os, 'unlink', side_effect=removed):
                owner.close(); owner.close()
            self.assertTrue(events)
            self.assertTrue(all(not root.path.exists() for root in owner._roots))
            self.assertTrue(all(item.root_fd is None and item.parent_fd is None for item in owner._retirements))

    def test_real_partial_activation_retires_only_certain_owned_entries(self):
        with publisher_fixture() as fixture:
            fixture.archives[13] = b'broken final archive'
            with artifact_worker(fixture):
                owner = stage.stage_selected(fixture.root, fixture.selection, fixture.api,
                                             temporary_parent=fixture.parent)
                with self.assertRaises(safe.ConsumerError): owner.__enter__()
                self.assertEqual(len(owner._roots), 6)
                self.assertTrue(all(not root.path.exists() for root in owner._roots))
                self.assertFalse(owner._cleanup_failed)
                self.assertTrue(all(item.root_fd is None and item.parent_fd is None for item in owner._retirements))

        with publisher_fixture() as fixture, artifact_worker(fixture):
            owner = stage.stage_selected(fixture.root, fixture.selection, fixture.api, temporary_parent=fixture.parent)
            opened, streams = safe.PrivateRoot.open, []
            @contextmanager
            def partial(root, name, mode='rb'):
                with opened(root, name, mode) as stream:
                    if mode == 'rb' and root is getattr(owner, '_output', None) and hasattr(owner, 'plan'):
                        streams.append(stream)
                        if len(streams) == 3: raise OSError('third retained handle')
                    yield stream
            with patch.object(safe.PrivateRoot, 'open', partial):
                with self.assertRaisesRegex(safe.ConsumerError, '^unsafe_private_io$'): owner.__enter__()
            self.assertEqual(len(streams), 3)
            self.assertTrue(all(stream.closed for stream in streams))
            self.assertTrue(all(not root.path.exists() for root in owner._roots))
            self.assertFalse(owner._cleanup_failed)

    def test_real_receipt_and_bundle_workers_exit_before_removal(self):
        with self.session() as (session, _, _, seen), self.retirement_trace() as events:
            session.run_until_pause()
            self.children_exited(seen, 2)
            session.close()
            self.assertEqual(len(events), 1)
            self.assertEqual(len(events[0]['children']), 2)
            self.assertTrue(all(code is not None for code in events[0]['children']))
            self.assertEqual(events[0]['existed'], (False,) * 6)

    def test_real_timeout_and_cancellation_retire_after_certain_worker_cleanup(self):
        for ident in (14, 13):
            for cancelled in (False, True):
                with self.retirement_trace() as events:
                    self.blocked_download(ident, cancelled)
                self.assertEqual(len(events), 1)
                self.assertFalse(events[0]['retain'])
                self.assertTrue(all(code is not None for code in events[0]['children']))
                self.assertEqual(events[0]['existed'], (False,) * 6)

    def test_transport_cleanup_uncertain_retains_every_stage_root(self):
        for ident in (14, 13):
            with self.retirement_trace() as events:
                self.blocked_download(ident, True, pipe=True)
            self.assertEqual(len(events), 1)
            self.assertTrue(events[0]['retain'])
            self.assertEqual(events[0]['existed'], (True,) * 6)
            self.assertTrue(all(code is not None for code in events[0]['children']))

    def test_retained_handle_close_failure_prevents_every_removal(self):
        with publisher_fixture() as fixture, artifact_worker(fixture):
            owner = stage.stage_selected(fixture.root, fixture.selection, fixture.api,
                                         temporary_parent=fixture.parent)
            opened, failed = safe.PrivateRoot.open, []
            @contextmanager
            def closing(root, name, mode='rb'):
                try:
                    with opened(root, name, mode) as stream:
                        yield stream
                finally:
                    if mode == 'rb' and stream in owner._handles and not failed:
                        self.assertTrue(stream.closed)
                        failed.append(stream)
                        raise OSError('after real retained stream closure')
            with patch.object(safe.PrivateRoot, 'open', closing):
                owner.__enter__()
                with self.assertRaisesRegex(safe.ConsumerError, '^unsafe_private_io$'): owner.close()
            self.assertEqual(len(failed), 1)
            self.assertTrue(owner._cleanup_failed)
            self.assertTrue(all(handle.closed for handle in owner._handles))
            self.assertTrue(all(root.path.exists() for root in owner._roots))
            owner.close()

    def test_ordinary_root_close_failure_prevents_every_removal(self):
        with self.real_stage() as (owner, _):
            close, attempts = safe.PrivateRoot.close, []
            def closing(root):
                close(root)
                if root in owner._roots:
                    attempts.append(root)
                    if len(attempts) == 1: raise OSError('after real root closure')
            with patch.object(safe.PrivateRoot, 'close', closing):
                with self.assertRaisesRegex(OSError, 'after real root'): owner.close()
                owner.close()
            self.assertEqual(attempts, list(reversed(owner._roots)))
            self.assertTrue(owner._cleanup_failed)
            self.assertTrue(all(root.path.exists() and root.fd is None for root in owner._roots))
        with self.real_stage() as (owner, _):
            owned = owner._output._stage_owner
            close = os.close
            def temporary(fd):
                info = os.fstat(fd)
                close(fd)
                if (info.st_dev, info.st_ino) == owned.entries[''][1]:
                    raise OSError('after real handle-check directory close')
            with patch.object(safe.os, 'close', side_effect=temporary):
                with self.assertRaisesRegex(OSError, 'handle-check'): owner.stream(0)
            self.assertTrue(owned.uncertain)
            with self.assertRaisesRegex(safe.ConsumerError, '^stage_retirement_failed$'): owner.close()
            self.assertTrue(all(root.path.exists() for root in owner._roots))

    def test_pause_close_and_cancel_remain_local_and_cannot_resume(self):
        for method in ('close', 'cancel'):
            with self.session() as (session, tls, _, seen):
                pause = session.run_until_pause()
                paths = tuple(root.path for root in seen.stage._roots)
                requests = len(tls.requests)
                getattr(session, method)()
                self.assertIs(session.transition, pause)
                self.assertEqual(len(tls.requests), requests)
                self.assertIsInstance(pause.action, core.AwaitPublishRequest)
                self.assertTrue(all(not path.exists() for path in paths))
                with self.assertRaises(wire.WireFailure): session.run_until_pause()
                self.assertEqual(len(self.mutations(tls)), 7)

    def test_activation_retirement_failure_remains_blocked_no_effect(self):
        with self.session() as (session, tls, fixture, seen):
            fixture.archives[13] = b'broken final archive'
            receipts = stage._receipts
            def foreign(path, destination, **kwargs):
                result = receipts(path, destination, **kwargs)
                (destination.path / 'foreign').write_bytes(b'not registered')
                return result
            with patch.object(stage, '_receipts', side_effect=foreign):
                self.failed_run(session, 'adapter_error')
            self.assertEqual(session.outcome, 'blocked_no_effect')
            self.assertIsNone(session.transition)
            self.assertTrue(session._cleanup_failed)
            self.assertEqual(self.mutations(tls), [])
            self.assertTrue(all(root.path.exists() for root in seen.stage._roots))

    def test_prior_draft_and_unknown_mutation_effects_survive_retirement_failure(self):
        with self.session() as (session, tls, _, seen):
            session.run_until_pause()
            ident = session.transition.state.release_id
            (seen.stage._output.path / 'foreign').write_bytes(b'foreign')
            result = session.request_publish(self.request(session))
            self.assertEqual(result.state.outcome, 'partial_draft')
            self.assertEqual(result.state.release_id, ident)
            self.assertTrue(session._cleanup_failed)
            self.assertEqual(len(self.mutations(tls)), 7)
            self.assertTrue(all(root.path.exists() for root in seen.stage._roots))
        with self.session() as (session, tls, _, seen):
            def lost(method, path, headers, body):
                tls._release(method, path, headers, body)
                (seen.stage._output.path / 'foreign').write_bytes(b'foreign')
                return {'raw': b'HTTP/1.1 201 Fixture\r\nContent-Length: 50\r\n\r\n{'}
            tls.routes['POST', wire.ROOT + '/releases'] = lost
            result = session.run_until_pause()
            self.assertEqual(result.state.outcome, 'uncertain_remote_effect')
            self.assertIsNone(result.state.release_id)
            self.assertTrue(session._cleanup_failed)
            self.assertEqual(len(self.mutations(tls)), 1)
            self.assertTrue(all(root.path.exists() for root in seen.stage._roots))

    def test_confirmed_publish_retirement_failure_remains_published_unverified(self):
        with self.session() as (session, tls, _, seen):
            session.run_until_pause()
            ident = session.transition.state.release_id
            unlink, attempts = os.unlink, []
            def failed(name, *, dir_fd):
                attempts.append(name)
                unlink(name, dir_fd=dir_fd)
                raise OSError('after real partial retirement')
            with patch.object(retirement.os, 'unlink', side_effect=failed):
                result = session.request_publish(self.request(session))
                with self.assertRaises(wire.WireFailure): session.close()
            self.assertEqual((result.state.code, result.state.outcome), ('adapter_error', 'published_unverified'))
            self.assertEqual(result.state.release_id, ident)
            self.assertEqual(len(attempts), 1)
            self.assertTrue(session._cleanup_failed)
            self.assertFalse(tls.release['draft'])
            self.assertEqual(len(self.mutations(tls)), 8)
            self.assertTrue(all(handle.closed for handle in seen.stage._handles))
