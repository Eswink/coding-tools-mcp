"""existing real bundle/stage fixtures; synthetic release authority only."""
from contextlib import ExitStack, contextmanager
import hashlib
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import exact_build_audit as exact
import rc_artifact_consumer as consumer
import rc_consumer_contracts as contracts
import rc_consumer_fixed_git as fixed
from rc_consumer_io import ConsumerError
from rc_consumer_fixtures import ConsumerFixture
from rc_consumer_git_test_support import Cancelled, fault_child, reaped, record_git, verify_fixture, TARGET
import release_dependency_contract as dependency
import rc_publication_executor as executor
import rc_publication_executor_cases as old
import rc_publication_github as wire
import rc_publication_stage as stage
import rc_publication_staging_budget_cases as previous
from rc_publication_stage_cases import publisher_fixture, artifact_worker


class GitBudgetWiringCases(unittest.TestCase):
    session = previous.StagingBudgetCases.session
    recording = previous.StagingBudgetCases.recording
    failed_run = previous.StagingBudgetCases.failed_run

    @contextmanager
    def bundle(self):
        with tempfile.TemporaryDirectory(prefix='git-bundle-case-') as parent:
            yield ConsumerFixture(parent)

    @contextmanager
    def chain(self):
        seen = []
        def capture(obj, name):
            original = getattr(obj, name)
            def call(*args, **kwargs):
                seen.append((name, kwargs.copy()))
                return original(*args, **kwargs)
            return call
        with ExitStack() as stack:
            for obj, name in ((consumer, '_verify_bundle_bytes'), (contracts, 'verify_consumed_bundle'),
                    (contracts, 'verify_consumed_cloud'), (dependency, 'verify_build'), (exact, 'verify'),
                    (fixed.Reader, '__init__')):
                stack.enter_context(patch.object(obj, name, capture(obj, name)))
            yield seen

    def snapshot(self, roots):
        return tuple((root.path, tuple(sorted((p.relative_to(root.path).as_posix(),
            hashlib.sha256(p.read_bytes()).hexdigest()) for p in root.path.rglob('*') if p.is_file()))) for root in roots)

    def test_existing_bundle_fixture_matches_legacy_with_real_six_git_reads(self):
        with self.bundle() as f:
            expected = f.verify()
            with record_git() as seen:
                actual = contracts.verify_consumed_bundle(f.root, f.bundle, f.unpacked, f.producer,
                    f.integration, check_active=lambda: None)
            self.assertEqual(actual, expected)
            self.assertEqual(len(seen.calls), 6)
            reaped(self, seen.children)

    def test_same_deadline_and_callback_identities_cross_every_runtime_boundary(self):
        with publisher_fixture() as fixture, artifact_worker(fixture):
            deadline, callback = time.monotonic() + 60, lambda: None
            with self.chain() as seen, record_git() as children:
                owner = stage.stage_selected(fixture.root, fixture.selection, fixture.api,
                    temporary_parent=fixture.parent, deadline=deadline, check_active=callback)
                try:
                    owner.__enter__()
                    self.assertEqual(owner.plan.assets, fixture.plan.assets)
                    self.assertEqual(owner.plan_bytes, fixture.plan_bytes)
                    self.assertEqual(owner.provenance_bytes, fixture.provenance_bytes)
                finally:
                    owner.close()
            self.assertEqual([name for name, _ in seen], ['_verify_bundle_bytes', 'verify_consumed_bundle',
                'verify_consumed_cloud', 'verify_build', 'verify', '__init__'])
            for _, kwargs in seen:
                self.assertIs(kwargs['deadline'], deadline)
                self.assertIs(kwargs['check_active'], callback)
            self.assertEqual(len(children.calls), 6)
            reaped(self, children.children)
            self.assertTrue(all(not root.path.exists() for root in owner._roots))

    def test_omitted_controls_keep_every_old_downstream_keyword_shape(self):
        with publisher_fixture() as fixture, artifact_worker(fixture), self.chain() as seen, \
             patch.object(fixed.Reader, '__enter__', side_effect=AssertionError('legacy reader launch')):
            owner = stage.stage_selected(fixture.root, fixture.selection, fixture.api,
                                         temporary_parent=fixture.parent)
            try:
                owner.__enter__()
                self.assertEqual(owner.plan.assets, fixture.plan.assets)
            finally:
                owner.close()
        self.assertEqual([name for name, _ in seen], ['_verify_bundle_bytes', 'verify_consumed_bundle',
            'verify_consumed_cloud', 'verify_build', 'verify'])
        self.assertTrue(all('deadline' not in kwargs and 'check_active' not in kwargs for _, kwargs in seen))

    def test_one_deadline_spans_config_head_index_status_tree_and_files(self):
        with self.bundle() as f:
            original, entered, clock = fixed.Reader._run, [], [100.0]
            def run(reader, kind, cap):
                entered.append((kind, reader.deadline))
                clock[0] += 0.2
                return original(reader, kind, cap)
            with patch.object(fixed.Reader, '_run', run), \
                 patch.object(fixed.time, 'monotonic', side_effect=lambda: clock[0]), record_git() as seen:
                with self.assertRaisesRegex(ConsumerError, '^transport_deadline_exceeded$'):
                    verify_fixture(f, deadline=101.1, check_active=lambda: None)
            self.assertEqual([kind for kind, _ in entered], ['config', 'head', 'index', 'status', 'tree', 'files'])
            self.assertEqual({deadline for _, deadline in entered}, {101.1})
            self.assertEqual(len(seen.calls), 5)
            reaped(self, seen.children)

    def test_callback_only_complete_bundle_uses_no_operation_clock(self):
        with self.bundle() as f:
            calls = []
            with record_git() as seen, patch.object(fixed.time, 'monotonic', side_effect=AssertionError('invented clock')):
                actual = verify_fixture(f, check_active=lambda: calls.append(True) and None)
            self.assertEqual(actual['sha'], f.sha)
            self.assertEqual(len(seen.calls), 6)
            self.assertTrue(calls)
            reaped(self, seen.children)

    def test_native_config_failure_precedes_post_success_callback(self):
        with self.bundle() as f:
            path = f.root / '.git/config'
            path.write_bytes(path.read_bytes() + b'\n[core]\nfsmonitor=/must/not/run\n')
            validator, completed = fixed._config, []
            def validate(raw):
                completed.append(True)
                return validator(raw)
            def active():
                if completed: raise Cancelled()
            with patch.object(fixed, '_config', validate):
                with self.assertRaisesRegex(ConsumerError, '^unsupported_git_configuration$'):
                    verify_fixture(f, check_active=active)

    def test_wrong_head_diagnostic_precedes_callback_after_real_head_read(self):
        with self.bundle() as f:
            original, head = fixed.Reader.read, []
            def read(reader, *args):
                value = original(reader, *args)
                if args == ('rev-parse', 'HEAD'): head.append(True)
                return value
            def active():
                if head: raise Cancelled()
            with patch.object(fixed.Reader, 'read', read):
                with self.assertRaisesRegex(exact.EvidenceError, '^wrong_checkout_sha$'):
                    exact.source_identity(f.root, 'f' * 40, f.version, TARGET, check_active=active)

    def test_dirty_status_diagnostic_precedes_callback_after_real_status_read(self):
        with self.bundle() as f:
            (f.root / 'new-untracked').write_text('dirty')
            original, status = fixed.Reader.read, []
            def read(reader, *args):
                value = original(reader, *args)
                if args[0] == 'status': status.append(True)
                return value
            def active():
                if status: raise Cancelled()
            with patch.object(fixed.Reader, 'read', read):
                with self.assertRaisesRegex(exact.EvidenceError, '^unclean_source$'):
                    verify_fixture(f, check_active=active)

    def test_existing_evidence_errors_and_late_ls_files_order_remain(self):
        with self.bundle() as f, record_git() as seen:
            with self.assertRaisesRegex(exact.EvidenceError, '^untrusted_envelope_digest$'):
                exact.verify(f.root, f.exact, f.sha, f.version, TARGET, '0' * 64,
                             f.unpacked / 'bin', check_active=lambda: None)
            self.assertEqual(len(seen.calls), 5)
            self.assertEqual(seen.calls[-1][0][-2:], ('rev-parse', 'HEAD^{tree}'))
            reaped(self, seen.children)

    def test_real_git_child_cancellation_retires_stage_after_confirmed_reap(self):
        with self.session() as (session, tls, fixture, seen):
            def cancel(process):
                session.cancel()
                return process
            with fault_child('import time; time.sleep(10)', wrap=cancel) as children:
                self.failed_run(session, 'cancelled')
                reaped(self, children.children)
            self.assertEqual(session.outcome, 'blocked_no_effect')
            self.assertIsNone(session.transition)
            self.assertFalse(session._cleanup_failed)
            self.assertEqual(old.ExecutorCases.mutations(tls), [])
            self.assertEqual(len(seen.stage._roots), 6)
            self.assertTrue(all(not root.path.exists() for root in seen.stage._roots))
            self.assertTrue(all(child.poll() is not None for child in seen.children))

    def test_real_git_child_timeout_retires_stage_and_keeps_existing_error_mapping(self):
        with self.session(seconds=3) as (session, tls, fixture, seen):
            with fault_child('import time; time.sleep(10)') as children:
                self.failed_run(session, 'timeout')
                reaped(self, children.children)
            self.assertEqual(len(children.children), 1)
            self.assertEqual(session.outcome, 'blocked_no_effect')
            self.assertIsNone(session.transition)
            self.assertFalse(session._cleanup_failed)
            self.assertEqual(old.ExecutorCases.mutations(tls), [])
            self.assertTrue(all(not root.path.exists() for root in seen.stage._roots))
            self.assertEqual(seen.stage_errors[-1].code, 'transport_deadline_exceeded')

    def test_git_cleanup_uncertainty_is_sticky_and_retains_known_stage_bytes(self):
        with self.session() as (session, tls, fixture, seen):
            snapshots, wrappers = [], []
            class CloseFailure:
                def __init__(self, stream): self.stream, self.calls = stream, 0
                def __getattr__(self, name): return getattr(self.stream, name)
                def close(self):
                    self.calls += 1
                    self.stream.close()
                    raise OSError('after real Git pipe close')
            def cancel(process):
                snapshots.append(self.snapshot(seen.stage._roots))
                wrapper = CloseFailure(process.stdout)
                process.stdout = wrapper
                wrappers.append(wrapper)
                session.cancel()
                return wrapper
            with fault_child('import time; time.sleep(10)', wrap=cancel) as children:
                self.failed_run(session, 'adapter_error')
                reaped(self, children.children)
            self.assertEqual(session.outcome, 'blocked_no_effect')
            self.assertIsNone(session.transition)
            self.assertTrue(session._cleanup_failed)
            self.assertTrue(seen.stage._cleanup_failed)
            self.assertEqual(seen.stage_errors[-1].code, 'transport_cleanup_uncertain')
            self.assertEqual(old.ExecutorCases.mutations(tls), [])
            self.assertEqual(self.snapshot(seen.stage._roots), snapshots[0])
            self.assertTrue(all(root.path.exists() and root.fd is None for root in seen.stage._roots))
            seen.stage.close()
            with self.assertRaises(wire.WireFailure): session.close()
            self.assertEqual(self.snapshot(seen.stage._roots), snapshots[0])
            self.assertEqual([wrapper.calls for wrapper in wrappers], [1])
