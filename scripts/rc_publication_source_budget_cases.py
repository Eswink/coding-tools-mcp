"""Bounded Stage source observation; real Git/TLS with synthetic authority."""
from contextlib import ExitStack, contextmanager
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import rc_artifact_consumer as consumer
import rc_consumer_fixed_git as fixed
import rc_consumer_io as safe
from rc_consumer_git_test_support import Cancelled, fault_child, git, reaped, record_git
import rc_publication_executor as executor
import rc_publication_executor_cases as old
import rc_publication_github as wire
import rc_publication_stage as stage
import rc_publication_staging_budget_cases as previous
from rc_publication_stage_cases import publisher_fixture, artifact_worker


class SourceBudgetCases(unittest.TestCase):
    session = previous.StagingBudgetCases.session
    recording = previous.StagingBudgetCases.recording
    failed_run = previous.StagingBudgetCases.failed_run

    @contextmanager
    def calls(self):
        rows, initialize = [], fixed.Reader.__init__
        def captured(reader, *args, **kwargs):
            rows.append((reader, kwargs.copy()))
            return initialize(reader, *args, **kwargs)
        with patch.object(fixed.Reader, '__init__', captured):
            yield rows

    def timing(self, label, started, finished, deadline, fixture, owners, children):
        metadata = list((fixture.root / '.git').rglob('*'))
        receipt = dict(scope='synthetic-native-source-budget', phase=label,
            elapsed_seconds=finished - started, remaining_seconds=deadline - finished,
            deadline=deadline, source_sha=fixture.selection.subject.source.source_sha,
            git_binary_bytes=Path(fixed.BINARY).stat().st_size,
            metadata_entries=len(metadata), metadata_files=sum(path.is_file() for path in metadata),
            metadata_directories=sum(path.is_dir() for path in metadata), git_children=len(children.calls),
            owners=[dict(bindings=len(reader.bindings), scanned_entries=reader.entries,
                owned_descriptors=sum(fd is not None for _, _, fd, _ in reader.bindings),
                closed=reader.closed, uncertain=reader.uncertain) for reader, _ in owners])
        print('SOURCE_BUDGET_TIMING ' + json.dumps(receipt, sort_keys=True), flush=True)
        return receipt

    @contextmanager
    def source_fault(self, script, *, wrap=None, when=lambda: True):
        original, fired = stage._source, []
        children = SimpleNamespace(children=[], wrappers=[])
        def source(*args, **kwargs):
            if fired or not when(): return original(*args, **kwargs)
            fired.append(True)
            with fault_child(script, wrap=wrap) as seen:
                try:
                    return original(*args, **kwargs)
                finally:
                    children.children.extend(seen.children)
                    children.wrappers.extend(seen.wrappers)
                    reaped(self, seen.children)
        with patch.object(stage, '_source', source):
            yield children

    def snapshot(self, roots):
        return tuple((root.path, tuple(sorted((path.relative_to(root.path).as_posix(),
            hashlib.sha256(path.read_bytes()).hexdigest()) for path in root.path.rglob('*') if path.is_file())))
            for root in roots)

    def test_default_source_has_empty_downstream_kwargs_and_no_reader_or_clock(self):
        with publisher_fixture() as fixture:
            rows = []
            gate = stage.snapshot.gate
            def capture(owner, name):
                original = getattr(owner, name)
                def call(*args, **kwargs):
                    rows.append((name, kwargs.copy()))
                    return original(*args, **kwargs)
                return call
            with ExitStack() as stack:
                for owner, name in ((stage, '_source'), (gate.rc, 'verify_source'), (gate.reviewed, 'verify')):
                    stack.enter_context(patch.object(owner, name, capture(owner, name)))
                stack.enter_context(patch.object(fixed, 'Reader', side_effect=AssertionError('default Reader')))
                stack.enter_context(patch.object(safe, 'time', SimpleNamespace(monotonic=lambda: self.fail('default clock'))))
                value = stage._observe(fixture.root, fixture.selection, fixture.api)
            self.assertEqual(len(value), 4)
            self.assertEqual([name for name, _ in rows], ['_source', 'verify_source', 'verify', 'verify_source'])
            self.assertTrue(all('deadline' not in kwargs and 'check_active' not in kwargs for _, kwargs in rows))

    def test_full_source_observation_has_four_owners_and_exact_87_children(self):
        with publisher_fixture() as fixture:
            expected = stage._observe(fixture.root, fixture.selection, fixture.api)
            started, callback = time.monotonic(), lambda: None
            deadline = started + 60
            with self.calls() as owners, record_git() as children:
                try:
                    actual = stage._observe(fixture.root, fixture.selection, fixture.api,
                                            deadline=deadline, check_active=callback)
                finally:
                    timing = self.timing('source-observation-60s', started, time.monotonic(), deadline,
                                         fixture, owners, children)
            self.assertGreater(timing['remaining_seconds'], 0)
            self.assertEqual(actual, expected)
            self.assertEqual(len(owners), 4)
            self.assertEqual(len(children.calls), 87)
            self.assertTrue(all(options['deadline'] is deadline and options['check_active'] is callback
                                for _, options in owners))
            self.assertTrue(all(reader.closed and not reader.uncertain and not reader.fds for reader, _ in owners))
            self.assertEqual(sum('config' in argv for argv, _ in children.calls), 4)
            reaped(self, children.children)

    def test_activation_reuses_original_pair_for_both_source_passes_and_bundle(self):
        with publisher_fixture() as fixture, artifact_worker(fixture):
            started, callback = time.monotonic(), lambda: None
            deadline, finished = started + 60, None
            with self.calls() as owners, record_git() as children:
                try:
                    with stage.stage_selected(fixture.root, fixture.selection, fixture.api,
                            temporary_parent=fixture.parent, deadline=deadline, check_active=callback) as owner:
                        finished = time.monotonic()
                        self.assertEqual(owner.plan.assets, fixture.plan.assets)
                        self.assertEqual((owner.plan_bytes, owner.provenance_bytes), (fixture.plan_bytes, fixture.provenance_bytes))
                finally:
                    timing = self.timing('stage-activation-60s', started, time.monotonic() if finished is None else finished,
                                         deadline, fixture, owners, children)
            self.assertGreater(timing['remaining_seconds'], 0)
            self.assertEqual(len(owners), 9)
            self.assertEqual(len(children.calls), 180)
            self.assertTrue(all(options['deadline'] is deadline and options['check_active'] is callback
                                for _, options in owners))
            self.assertTrue(all(not root.path.exists() for root in owner._roots))
            reaped(self, children.children)

    def test_one_absolute_deadline_spans_source_readers_without_renewal(self):
        with publisher_fixture() as fixture:
            original, rows, clock = fixed.Reader._run, [], [100.0]
            def run(reader, kind, cap, *operands):
                rows.append((kind, reader.deadline)); clock[0] += 0.2
                return original(reader, kind, cap, *operands)
            timer = SimpleNamespace(monotonic=lambda: clock[0])
            with patch.object(fixed.Reader, '_run', run), patch.object(fixed, 'time', timer), \
                 patch.object(safe, 'time', timer), record_git() as children:
                with self.assertRaisesRegex(safe.ConsumerError, '^transport_deadline_exceeded$'):
                    stage._source(fixture.root, fixture.selection.subject, fixture.api,
                                  deadline=101.1, check_active=lambda: None)
            self.assertEqual([kind for kind, _ in rows], ['config', 'commit', 'index', 'tracked', 'config', 'untracked'])
            self.assertEqual({deadline for _, deadline in rows}, {101.1})
            self.assertEqual(len(children.calls), 5)
            reaped(self, children.children)

    def test_callback_only_full_source_does_not_read_an_operation_clock(self):
        with publisher_fixture() as fixture:
            polls = []
            timer = SimpleNamespace(monotonic=lambda: self.fail('callback-only clock'))
            with patch.object(fixed, 'time', timer), patch.object(safe, 'time', timer), record_git() as seen:
                stage._source(fixture.root, fixture.selection.subject, fixture.api,
                              check_active=lambda: polls.append(True) and None)
            self.assertEqual(len(seen.calls), 87)
            self.assertTrue(polls)
            reaped(self, seen.children)
            for boundary in ('last_blob', 'close'):
                for cancelled in (False, True):
                    reviewed_done, last, stopped = [], [], []
                    deadline = time.monotonic() + 60
                    gate = stage.snapshot.gate.reviewed
                    verify, blob, close = gate.verify, gate._blob, fixed.Reader.close
                    def verified(*args, **kwargs):
                        value = verify(*args, **kwargs); reviewed_done.append(True); return value
                    def completed(*args):
                        value = blob(*args)
                        if reviewed_done and args[2] == fixture.selection.subject.runs[-1].workflow_path:
                            last.append(args[3])
                            if boundary == 'last_blob': stopped.append(True)
                        return value
                    def closed(reader):
                        close(reader)
                        if last and reader is last[-1] and boundary == 'close': stopped.append(True)
                    def active():
                        if stopped and cancelled: raise Cancelled()
                    timer = SimpleNamespace(monotonic=lambda: deadline + 1 if stopped else deadline - 1)
                    with self.subTest(boundary=boundary, cancelled=cancelled), patch.object(gate, 'verify', verified), \
                         patch.object(gate, '_blob', completed), patch.object(fixed.Reader, 'close', closed), \
                         patch.object(safe, 'time', timer), patch.object(fixture.api, 'get') as api:
                        code = 'transport_cancelled' if cancelled else 'transport_deadline_exceeded'
                        with self.assertRaisesRegex(safe.ConsumerError, '^' + code + '$'):
                            stage._source(fixture.root, fixture.selection.subject, fixture.api, check_active=active,
                                          deadline=None if cancelled else deadline)
                        api.assert_not_called()
                    self.assertEqual(len(last), 1)
                    self.assertTrue(last[0].closed)
                    self.assertTrue(stopped)

    def test_invalid_or_expired_controls_create_no_child_or_private_root(self):
        with publisher_fixture() as fixture:
            for deadline, code in ((True, 'invalid_transport_deadline'), (float('nan'), 'invalid_transport_deadline'),
                                   (float('inf'), 'invalid_transport_deadline'), (0, 'transport_deadline_exceeded')):
                owner = stage.stage_selected(fixture.root, fixture.selection, fixture.api,
                    temporary_parent=fixture.parent, deadline=deadline)
                with patch.object(fixed.subprocess, 'Popen', side_effect=AssertionError('early child')):
                    with self.assertRaisesRegex(safe.ConsumerError, '^' + code + '$'): owner.__enter__()
                self.assertEqual(owner._roots, [])
                self.assertTrue(owner._closed)

    def test_initial_source_timeout_reaps_before_any_private_stage_root(self):
        with self.session(seconds=3) as (session, tls, _, seen):
            with self.source_fault('import time; time.sleep(10)') as children:
                self.failed_run(session, 'timeout')
                reaped(self, children.children)
            self.assertEqual(len(children.children), 1)
            self.assertEqual(seen.stage._roots, [])
            self.assertEqual(seen.downloads, [])
            self.assertEqual(old.ExecutorCases.mutations(tls), [])
            self.assertEqual(session.outcome, 'blocked_no_effect')
            self.assertFalse(session._cleanup_failed)

    def test_initial_source_cancellation_owns_and_reaps_child_before_cleanup(self):
        with self.session() as (session, tls, _, seen):
            def cancel(process):
                session.cancel()
                return process
            with self.source_fault('import time; time.sleep(10)', wrap=cancel) as children:
                self.failed_run(session, 'cancelled')
                reaped(self, children.children)
            self.assertEqual(seen.stage._roots, [])
            self.assertEqual(seen.downloads, [])
            self.assertEqual(old.ExecutorCases.mutations(tls), [])
            self.assertFalse(session._cleanup_failed)

    def test_revalidation_uses_fresh_current_pair_after_activation_has_expired(self):
        with publisher_fixture() as fixture, artifact_worker(fixture):
            activation_deadline, stopped = time.monotonic() + 60, []
            def activation_callback():
                if stopped: raise Cancelled()
            with stage.stage_selected(fixture.root, fixture.selection, fixture.api, temporary_parent=fixture.parent,
                    deadline=activation_deadline, check_active=activation_callback) as owner:
                stopped.append(True)
                timer = SimpleNamespace(monotonic=lambda: activation_deadline + 1)
                current_deadline, current_callback = activation_deadline + 60, lambda: None
                with self.calls() as owners, patch.object(fixed, 'time', timer), patch.object(safe, 'time', timer):
                    self.assertEqual(owner.revalidate(deadline=current_deadline, check_active=current_callback), fixture.plan.assets)
                self.assertEqual(len(owners), 4)
                self.assertTrue(all(options['deadline'] is current_deadline and options['check_active'] is current_callback
                                    for _, options in owners))
                self.assertIs(owner._deadline, activation_deadline)
                self.assertIs(owner._check_active, activation_callback)
        with self.session() as (session, tls, fixture, _):
            chosen, execute = [], executor.PublisherSession._execute
            self.assertEqual(executor.OPERATION_SECONDS, 30)
            def selected(current, operation):
                self.assertEqual(operation.kind, 'ObserveFence')
                started, deadline = time.monotonic(), current._deadline
                with self.calls() as owners, record_git() as children:
                    try:
                        result = execute(current, operation)
                    finally:
                        timing = self.timing('session-observe-fence-30s', started, time.monotonic(), deadline,
                                             fixture, owners, children)
                self.assertGreater(timing['remaining_seconds'], 0)
                self.assertLessEqual(deadline - started, 30)
                self.assertEqual((len(owners), len(children.calls)), (4, 87))
                self.assertTrue(all(options['deadline'] is deadline for _, options in owners))
                reaped(self, children.children)
                chosen.append(timing)
                current.cancel()  # End this measurement before the first modeled mutation.
                return result
            with patch.object(executor.PublisherSession, '_execute', selected):
                result = session.run_until_pause()
            self.assertEqual(len(chosen), 1)
            self.assertEqual(result.state.code, 'cancelled')
            self.assertEqual(old.ExecutorCases.mutations(tls), [])

    def test_local_untracked_tree_tag_and_workflow_failures_precede_late_cancellation(self):
        for boundary, code in (('untracked', 'untracked_source'), ('verify', 'source_tree_mismatch'),
                               ('tag_oid', 'lightweight_tag_required'), ('_blob', 'workflow_blob_mismatch')):
            with self.subTest(boundary=boundary), publisher_fixture() as fixture:
                subject, done = fixture.selection.subject, []
                if boundary == 'untracked': (fixture.root / 'untracked').write_text('dirty')
                elif boundary == 'verify':
                    changed = replace(subject.source, source_tree='0' * 40)
                    subject = replace(subject, source=changed, runs=tuple(replace(run, source=changed) for run in subject.runs))
                elif boundary == 'tag_oid': git(fixture.root, 'tag', '-f', subject.tag, stage.snapshot.gate.reviewed.BASE)
                else: subject = replace(subject, runs=(replace(subject.runs[0], workflow_blob='0' * 40), *subject.runs[1:]))
                target = fixed.Reader if boundary in ('untracked', 'tag_oid') else stage.snapshot.gate.reviewed
                original = getattr(target, boundary)
                review_complete, verify = [], stage.snapshot.gate.reviewed.verify
                def verified(*args, **kwargs):
                    value = verify(*args, **kwargs); review_complete.append(True); return value
                def captured(*args, **kwargs):
                    value = original(*args, **kwargs)
                    # _blob is also used during manifest verification; only stop at selected workflow.
                    if boundary != '_blob' or review_complete and args[2] == subject.runs[0].workflow_path: done.append(True)
                    return value
                def active():
                    if done: raise Cancelled()
                with ExitStack() as stack:
                    stack.enter_context(patch.object(target, boundary, captured))
                    if boundary == '_blob': stack.enter_context(patch.object(stage.snapshot.gate.reviewed, 'verify', verified))
                    with self.assertRaisesRegex(safe.ConsumerError, '^' + code + '$'):
                        stage._source(fixture.root, subject, fixture.api, check_active=active)
                self.assertEqual(done, [True])

    def test_ignored_untracked_file_is_rejected_before_reviewed_manifest_reader(self):
        with publisher_fixture() as fixture:
            (fixture.root / '.git/info/exclude').write_text('ignored\n')
            (fixture.root / 'ignored').write_text('untracked despite exclusion')
            with patch.object(stage.snapshot.gate.reviewed, 'verify', side_effect=AssertionError('reached manifest')):
                with self.assertRaisesRegex(safe.ConsumerError, '^untracked_source$'):
                    stage._source(fixture.root, fixture.selection.subject, fixture.api, check_active=lambda: None)

    def test_later_source_cancel_and_timeout_preserve_existing_mutation_effects(self):
        for phase, count, outcome in (('ObserveFence', 0, 'blocked_no_effect'), ('ObserveDraft', 1, 'partial_draft'),
                                       ('ObserveDraft', 7, 'partial_draft'), ('VerifyPublished', 8, 'published_unverified')):
            for cancelled in (False, True):
                with self.subTest(phase=phase, count=count, cancelled=cancelled), self.session() as (session, tls, _, seen):
                    if phase == 'VerifyPublished': session.run_until_pause()
                    def when():
                        return (session._inflight is not None and session._inflight.kind == phase
                                and len(old.ExecutorCases.mutations(tls)) == count)
                    def stop(process):
                        if cancelled: session.cancel()
                        else: session._deadline = time.monotonic()
                        return process
                    with self.source_fault('import time; time.sleep(10)', wrap=stop, when=when) as children:
                        result = (session.request_publish(old.ExecutorCases.request(session)) if phase == 'VerifyPublished'
                                  else session.run_until_pause())
                        reaped(self, children.children)
                    self.assertEqual((result.state.code, result.state.outcome), ('cancelled' if cancelled else 'timeout', outcome))
                    self.assertEqual(len(old.ExecutorCases.mutations(tls)), count)
                    self.assertTrue(session._closed)
                    self.assertTrue(all(handle.closed for handle in seen.stage._handles))
                    self.assertTrue(all(not root.path.exists() for root in seen.stage._roots))

    def test_source_cleanup_uncertainty_retains_bytes_and_is_sticky_after_prior_effect(self):
        for phase, count, outcome in (('ObserveDraft', 1, 'partial_draft'), ('VerifyPublished', 8, 'published_unverified')):
            with self.subTest(phase=phase), self.session() as (session, tls, _, seen):
                if phase == 'VerifyPublished': session.run_until_pause()
                snapshots, wrappers = [], []
                class CloseFailure:
                    def __init__(self, stream): self.stream, self.calls = stream, 0
                    def __getattr__(self, name): return getattr(self.stream, name)
                    def close(self):
                        self.calls += 1
                        self.stream.close()
                        raise OSError('after real source pipe close')
                def stop(process):
                    snapshots.append(self.snapshot(seen.stage._roots))
                    wrapper = CloseFailure(process.stdout); process.stdout = wrapper; wrappers.append(wrapper)
                    session.cancel()
                    return wrapper
                def when():
                    return (session._inflight is not None and session._inflight.kind == phase
                            and len(old.ExecutorCases.mutations(tls)) == count)
                with self.source_fault('import time; time.sleep(10)', wrap=stop, when=when) as children:
                    result = (session.request_publish(old.ExecutorCases.request(session)) if phase == 'VerifyPublished'
                              else session.run_until_pause())
                    reaped(self, children.children)
                self.assertEqual((result.state.code, result.state.outcome), ('adapter_error', outcome))
                self.assertEqual(len(old.ExecutorCases.mutations(tls)), count)
                self.assertTrue(session._cleanup_failed)
                self.assertTrue(seen.stage._cleanup_failed)
                self.assertEqual(self.snapshot(seen.stage._roots), snapshots[0])
                self.assertTrue(all(root.path.exists() and root.fd is None for root in seen.stage._roots))
                self.assertTrue(all(handle.closed for handle in seen.stage._handles))
                seen.stage.close()
                with self.assertRaises(wire.WireFailure): session.close()
                self.assertEqual(self.snapshot(seen.stage._roots), snapshots[0])
                self.assertEqual([wrapper.calls for wrapper in wrappers], [1])


if __name__ == '__main__':
    unittest.main()
