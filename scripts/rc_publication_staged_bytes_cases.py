"""Cooperative staged-byte controls over real IO; synthetic authority only."""
from contextlib import ExitStack, contextmanager
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

import rc_artifact_consumer as consumer
import rc_consumer_archive_budget_support as observation
import rc_consumer_archive_tests as fixtures
import rc_consumer_checksum_budget_cases as checksum
import rc_consumer_io as safe
import rc_publication_contract as core
import rc_publication_executor as executor
import rc_publication_executor_cases as old
import rc_publication_github as wire
import rc_publication_stage as stage
import rc_publication_staging_budget_cases as staging
from rc_publication_stage_cases import publisher_fixture, artifact_worker, set_receipts
from rc_publication_staged_bytes_support import boundary as run_boundary, failed_activation as run_failed_activation


class StagedBytesCases(unittest.TestCase):
    setUp = fixtures.ArchiveTests.setUp
    root = fixtures.ArchiveTests.root
    file = fixtures.ArchiveTests.file
    zip = fixtures.ArchiveTests.zip
    failure = checksum.ChecksumBudgetCases.failure
    padded_session = checksum.ChecksumBudgetCases.padded_session
    recording = staging.StagingBudgetCases.recording
    session = staging.StagingBudgetCases.session
    children_exited = staging.StagingBudgetCases.children_exited
    bindings = staging.StagingBudgetCases.bindings
    activation_failed = staging.StagingBudgetCases.activation_failed
    failed_run = staging.StagingBudgetCases.failed_run

    @contextmanager
    def trace_calls(self, hook=lambda event: None, budget=None):
        trace = observation.Trace(hook, budget)
        class WithSeek(observation.Observed):
            def seek(self, *args):
                return self.event('seek', self.target.seek(*args))
        with patch.object(observation, 'Observed', WithSeek), trace.trace_calls(), ExitStack() as stack:
            stack.enter_context(patch.object(stage, 'open_file', safe.open_file))
            for owner, name, label in ((stage, '_receipts', 'receipts'),
                    (safe.PrivateRoot, 'copy', 'copy'), (consumer, 'hash_file', 'output_hash'),
                    (stage.StagedAssets, 'revalidate', 'revalidate')):
                stack.enter_context(patch.object(owner, name, trace.wrap(getattr(owner, name), label)))
            yield trace

    @contextmanager
    def owned_stage(self):
        with publisher_fixture() as fixture:
            # Valid original JSON whitespace creates real multi-CHUNK retained bytes.
            fixture.provenance_bytes += b' \n' * safe.CHUNK
            fixture.payloads['RC_PROVENANCE.json'] = fixture.provenance_bytes
            checksum_name = next(name for name in fixture.payloads if name.startswith('SHA256SUMS_'))
            fixture.payloads[checksum_name] = ''.join(hashlib.sha256(fixture.payloads[name]).hexdigest() + '  ' + name + '\n'
                for name in sorted(fixture.payloads) if name != checksum_name).encode()
            rows = [dict(name=row.name, family=row.family, media_type=row.media_type,
                         size=len(fixture.payloads[row.name]), sha256=hashlib.sha256(fixture.payloads[row.name]).hexdigest())
                    for row in fixture.plan.assets]
            fixture.plan_bytes = consumer.encode(dict(json.loads(fixture.provenance_bytes), assets=rows))
            fixture.plan = core.AssetPlanView(tuple(core.Asset(**row) for row in rows))
            fixture.selection = replace(fixture.selection, subject=replace(fixture.selection.subject,
                plan_sha256=hashlib.sha256(fixture.plan_bytes).hexdigest()))
            set_receipts(fixture)
            with artifact_worker(fixture), self.trace_calls() as trace:
                with stage.stage_selected(fixture.root, fixture.selection, fixture.api,
                                          temporary_parent=fixture.parent) as owner:
                    yield owner, fixture, trace
            self.assertTrue(all(handle.closed for handle in owner._handles))
            self.assertTrue(all(root.fd is None for root in owner._roots))

    def receipts(self, entries=None, compression=zipfile.ZIP_DEFLATED):
        entries = entries or [(name, b'{"value":"' + b'x' * (safe.CHUNK + 7) + b'"}')
                              for name in sorted(stage.NAMES)]
        return self.zip([('rc-consumer-receipts-case/' + name, data) for name, data in entries], compression)

    def no_later_bytes(self, trace, offset):
        self.assertFalse([e.kind for e in trace.events[offset:]
                          if e.kind.endswith(('.read', '.write', '.decompress', '.acquire', '.member'))])

    boundary = run_boundary

    def test_default_receipts_copy_revalidation_preserve_bytes_and_no_clock(self):
        clock = SimpleNamespace(monotonic=lambda: self.fail('default read a clock'))
        path, destination, source = self.receipts(), self.root(), self.file(b'a' * (2 * safe.CHUNK + 3))
        with self.trace_calls() as trace, patch.object(safe, 'time', clock):
            stage._receipts(path, destination)
            copied = destination.copy('copy', source)
        self.assertEqual(copied.read_bytes(), source.read_bytes())
        self.assertEqual(set(destination.files()), stage.NAMES | {'copy'})
        self.assertTrue(all(not kwargs for label, kwargs in trace.controls
                            if label in {'receipts', 'copy', '_directory_guard', '_local_records', '_deflate_integrity'}))
        with self.owned_stage() as (owner, fixture, _), patch.object(safe, 'time', clock):
            self.assertEqual(owner.revalidate(), fixture.plan.assets)
            self.assertEqual((owner.plan_bytes, owner.provenance_bytes), (fixture.plan_bytes, fixture.provenance_bytes))
            self.assertTrue(all(handle.tell() == 0 for handle in owner._handles))

    def test_invalid_controls_fail_before_byte_io(self):
        root = self.root()
        for value, code in ((True, 'invalid_transport_deadline'), (float('nan'), 'invalid_transport_deadline'),
                            (float('inf'), 'invalid_transport_deadline'), (0, 'transport_deadline_exceeded')):
            for action in (lambda: stage._receipts('/absent', root, deadline=value),
                           lambda: root.copy('copy', '/absent', deadline=value)):
                with (patch.object(safe, 'open_file', side_effect=AssertionError('opened')),
                      patch.object(stage, 'open_file', side_effect=AssertionError('opened'))):
                    self.failure(action, code)
        with self.owned_stage() as (owner, _, _), patch.object(stage, '_observe', side_effect=AssertionError('observed')):
            self.failure(lambda: owner.revalidate(check_active=1), 'artifact_transport_failed')

    def test_original_budget_and_callback_failures_are_preserved(self):
        for callback, code in ((lambda: 1, 'artifact_transport_failed'),
                (lambda: (_ for _ in ()).throw(safe.ConsumerError('cancelled')), 'transport_cancelled'),
                (lambda: (_ for _ in ()).throw(safe.ConsumerError('timeout')), 'transport_deadline_exceeded'),
                (lambda: (_ for _ in ()).throw(RuntimeError('private')), 'artifact_transport_failed')):
            self.failure(lambda: self.root().copy('copy', '/absent', check_active=callback), code, clean=True)
            self.failure(lambda: stage._receipts('/absent', self.root(), check_active=callback), code, clean=True)
        for interrupt in (KeyboardInterrupt, SystemExit):
            with self.assertRaises(interrupt):
                self.root().copy('copy', '/absent', check_active=lambda: (_ for _ in ()).throw(interrupt('private')))
        path, destination, budget = self.receipts(), self.root(), observation.Budget(False)
        with self.trace_calls() as trace, patch.object(safe, 'time', SimpleNamespace(monotonic=budget.now)):
            stage._receipts(path, destination, **budget.controls)
        forwarded = [kw for name, kw in trace.controls if name in {'receipts', '_directory_guard', '_local_records', '_deflate_integrity'}]
        self.assertGreater(len(forwarded), 3)
        self.assertTrue(all(kw['deadline'] == 101 and kw['check_active'] is budget.controls['check_active'] for kw in forwarded))

    def test_receipt_directory_local_and_deflate_boundaries(self):
        for compression in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            boundaries = [('_directory_guard', 'record'), ('_local_records', 'record')]
            if compression == zipfile.ZIP_DEFLATED:
                boundaries.append(('_deflate_integrity', 'raw.read'))
            for phase, kind in boundaries:
                for cancelled in (False, True):
                    with self.subTest(compression=compression, phase=phase, cancelled=cancelled):
                        path, root = self.receipts(compression=compression), self.root()
                        self.boundary(lambda controls: stage._receipts(path, root, **controls),
                                      lambda event: event.phase == phase and event.kind == kind
                                      and (kind != 'record' or event.size == 0), cancelled)

    def test_receipt_member_read_write_and_close_boundaries(self):
        for kind in ('zip.read', 'output.write', 'zip.close', 'zip_archive_close.return', 'raw.close'):
            for cancelled in (False, True):
                path, root = self.receipts(), self.root()
                with self.subTest(kind=kind, cancelled=cancelled):
                    self.boundary(lambda controls: stage._receipts(path, root, **controls),
                                  lambda event: event.kind == kind, cancelled)

    def test_receipt_rejections_precede_success_polls(self):
        for entries, code in (([('rc-asset-plan.json', b'{}')], 'receipt_member_count'),
                ([('wrong', b'{}'), ('RC_PROVENANCE.json', b'{}')], 'receipt_layout'),
                ([('rc-asset-plan.json', b'x' * (safe.JSON_LIMIT + 1)), ('RC_PROVENANCE.json', b'{}')], 'receipt_member_limit')):
            self.failure(lambda: stage._receipts(self.receipts(entries), self.root(), check_active=lambda: None), code)
        path, root, budget = self.receipts(), self.root(), observation.Budget()
        def failed(member, size=-1):
            budget.stopped = True
            raise OSError('private read error')
        with patch.object(zipfile.ZipExtFile, 'read', failed):
            self.failure(lambda: stage._receipts(path, root, **budget.controls), 'unsafe_file_io')
        self.assertEqual(root.files(), ())
        for fault in ('crc', 'size', 'close'):
            for cancelled in (False, True):
                path = self.receipts(compression=zipfile.ZIP_STORED)
                if fault == 'crc':
                    data = bytearray(path.read_bytes())
                    for offset in (14, data.index(b'PK\x01\x02') + 16):
                        data[offset:offset + 4] = (int.from_bytes(data[offset:offset + 4], 'little') ^ 1).to_bytes(4, 'little')
                    path.write_bytes(data)
                root, budget, faults = self.root(), observation.Budget(cancelled), []
                read, close = zipfile.ZipExtFile.read, zipfile.ZipExtFile.close
                def collision():
                    budget.stopped = True
                    faults.append(budget.polls)
                def reading(member, size=-1):
                    try:
                        return read(member, size)
                    except zipfile.BadZipFile:
                        collision()
                        raise
                def closing(member):
                    was_open = not member.closed
                    result = close(member)
                    if fault == 'close' and was_open:
                        collision()
                        raise OSError('injected member close failure after real closure')
                    return result
                def hook(event):
                    if fault == 'size' and event.kind == 'zip.read' and not faults:
                        event.owner.file_size += 1
                        collision()
                with (self.trace_calls(hook, budget) as trace,
                      patch.object(safe, 'time', SimpleNamespace(monotonic=budget.now)),
                      patch.object(zipfile.ZipExtFile, 'read', reading),
                      patch.object(zipfile.ZipExtFile, 'close', closing)):
                    self.failure(lambda: stage._receipts(path, root, **budget.controls),
                                 {'size': 'receipt_member_size', 'crc': 'invalid_receipt_zip', 'close': 'unsafe_file_io'}[fault])
                self.assertEqual(faults, [budget.polls])
                self.assertTrue(all(stream.closed for stream in trace.streams))

    def test_copy_read_write_eof_and_close_boundaries(self):
        source = self.file(bytes(range(256)) * (safe.CHUNK // 64 + 1))
        for kind, eof in (('raw.read', False), ('raw.read', True), ('output.write', False), ('output.close', False), ('raw.close', False)):
            for cancelled in (False, True):
                root = self.root()
                with self.subTest(kind=kind, eof=eof, cancelled=cancelled):
                    self.boundary(lambda controls: root.copy('copy', source, **controls),
                        lambda event: event.phase == 'copy' and event.kind == kind and
                        (event.result == b'' if eof else event.result != b''), cancelled)
                self.assertIsNotNone(root.fd)

    def test_copy_limits_nofollow_and_failures_retire_once(self):
        source, root = self.file(b'x' * (safe.CHUNK + 1)), self.root()
        with patch.object(safe, 'FILE_LIMIT', safe.CHUNK):
            self.failure(lambda: root.copy('copy', source, check_active=lambda: None), 'private_copy_limit')
        link = source.with_name('symlink')
        link.symlink_to(source)
        self.failure(lambda: self.root().copy('link', link, check_active=lambda: None), 'unsafe_file_io')
        hard = source.with_name('hardlink')
        os.link(source, hard)
        self.failure(lambda: self.root().copy('hard', source, check_active=lambda: None), 'nonregular_file')
        root, original, streams, budget = self.root(), safe.PrivateRoot.open, [], observation.Budget()
        @contextmanager
        def bad_write(owner, name, mode='rb'):
            with original(owner, name, mode) as stream:
                streams.append(stream)
                def write(data):
                    budget.stopped = True
                    raise OSError('private write error')
                yield SimpleNamespace(write=write)
        with patch.object(safe.PrivateRoot, 'open', bad_write):
            self.failure(lambda: root.copy('failed', self.file(b'ok'), **budget.controls), 'unsafe_private_io')
        self.assertTrue(all(stream.closed for stream in streams))
        root.close()
        root.close()
        self.assertIsNone(root.fd)
        opened, streams, budget = safe.open_file, [], observation.Budget()
        @contextmanager
        def failed_retirement(path):
            with opened(path) as stream:
                streams.append(stream)
                yield stream
                budget.stopped = True
                raise OSError('injected source unwind failure')
        with patch.object(safe, 'open_file', failed_retirement):
            self.failure(lambda: self.root().copy('closed', self.file(b'copy'), **budget.controls), 'unsafe_file_io')
        self.assertTrue(all(stream.closed for stream in streams))

    def test_output_checksum_and_asset_hashes_share_controls(self):
        with self.padded_session() as (session, _, fixture, seen), self.trace_calls() as trace:
            session.run_until_pause()
            rows = [kwargs for phase, kwargs in trace.controls if phase == 'output_hash']
            self.assertEqual(len(rows), 11)
            deadline, callback = seen.downloads[0][1]['deadline'], seen.downloads[0][1]['check_active']
            self.assertTrue(all(row['deadline'] == deadline and row['check_active'] is callback for row in rows))
            self.bindings(seen.stage, fixture)
            self.assertEqual(seen.stage.provenance_bytes, fixture.provenance_bytes)
            self.children_exited(seen, 2)

    def test_revalidation_retains_handles_and_rewinds(self):
        with self.owned_stage() as (owner, fixture, trace):
            handles = tuple(owner._handles)
            self.assertGreater(next(row.size for row in owner.plan.assets if row.name == 'RC_PROVENANCE.json'), safe.CHUNK)
            trace.events.clear()
            opened = safe.open_file
            def reject_payload(path):
                self.assertNotEqual(Path(path).parent, owner._output.path)
                return opened(path)
            with patch.object(safe, 'open_file', reject_payload):
                self.assertEqual(owner.revalidate(check_active=lambda: None), fixture.plan.assets)
            self.assertEqual(tuple(owner._handles), handles)
            reads = [event for event in trace.events if event.kind == 'binary.read' and event.key == 'RC_PROVENANCE.json']
            self.assertGreater(len(reads), 2)
            self.assertTrue(all(event.size == safe.CHUNK for event in reads))
            self.assertTrue(all(handle.tell() == 0 for handle in handles))
            for index, handle in enumerate(handles):
                self.assertIs(owner.stream(index), handle)

    def test_revalidation_read_eof_and_seek_boundaries(self):
        with self.owned_stage() as (owner, _, trace):
            first_name = owner.plan.assets[0].name
            for kind, eof, occurrence in (('binary.read', False, 1), ('binary.read', True, 1),
                                           ('binary.seek', False, 1), ('binary.seek', False, 2)):
                for cancelled in (False, True):
                    budget, stopped, matches = observation.Budget(cancelled), [], []
                    def hook(event):
                        if (not stopped and event.kind == kind and event.key == first_name
                                and (event.result == b'' if eof else event.result != b'')):
                            matches.append(event)
                            if len(matches) == occurrence:
                                budget.stopped = True
                                stopped.append(len(trace.events))
                    trace.hook = hook
                    with patch.object(safe, 'time', SimpleNamespace(monotonic=budget.now)):
                        self.failure(lambda: owner.revalidate(**budget.controls), budget.code)
                    self.assertEqual(len(stopped), 1)
                    self.assertEqual(len(matches), occurrence)
                    self.no_later_bytes(trace, stopped[0])
                    self.assertTrue(all(not handle.closed for handle in owner._handles))
            trace.hook = lambda event: None
            owner.revalidate()
            self.assertTrue(all(handle.tell() == 0 for handle in owner._handles))

    def test_revalidation_drift_and_io_errors_precede_polls(self):
        with self.owned_stage() as (owner, fixture, trace):
            path = owner._output.path / owner.plan.assets[0].name
            original = path.read_bytes()
            path.write_bytes(bytes([original[0] ^ 1]) + original[1:])
            budget = observation.Budget()
            trace.hook = lambda event: setattr(budget, 'stopped', True) if event.kind == 'binary.read' and event.result == b'' else None
            self.failure(lambda: owner.revalidate(**budget.controls), 'staged_hash_changed')
            trace.hook = lambda event: None
            path.write_bytes(original + b'x')
            self.failure(lambda: owner.revalidate(check_active=lambda: None), 'staged_handle_changed')
            path.write_bytes(original)
            handle, wrapped = owner._handles[0], owner._handles[0].target
            def failed(*args):
                budget.stopped = True
                raise OSError('private retained IO failure')
            for operation in ('read', 'seek'):
                budget.stopped = False
                with patch.object(handle, operation, failed), self.assertRaisesRegex(OSError, 'private retained IO failure'):
                    owner.revalidate(**budget.controls)
            self.assertFalse(wrapped.closed)
            budget.stopped = False
            grown = []
            def growing(event):
                if event.key != owner.plan.assets[0].name:
                    return
                if event.kind == 'binary.seek' and not grown:
                    path.write_bytes(original + b'x')
                    grown.append(True)
                if event.kind == 'binary.read':
                    budget.stopped = True
            trace.hook = growing
            self.failure(lambda: owner.revalidate(**budget.controls), 'staged_size_changed')
            self.assertEqual(grown, [True])
            trace.hook = lambda event: None
            path.write_bytes(original)
            path.rename(Path(fixture.parent) / 'withdrawn-payload')
            budget.stopped, inventory_fault = False, []
            def inventory_changed(event):
                if event.kind == 'inventory.entry' and event.owner[0] is owner._output:
                    budget.stopped = True
                    inventory_fault.append(budget.polls)
            trace.hook = inventory_changed
            self.failure(lambda: owner.revalidate(**budget.controls), 'private_inventory_changed')
            self.assertEqual(inventory_fault, [budget.polls])

    def test_activation_shares_budget_across_owned_byte_phases(self):
        with self.padded_session() as (session, _, fixture, seen), self.trace_calls() as trace:
            activation = []
            def hook(event):
                if event.kind == 'revalidate.return' and session._inflight is None:
                    activation.extend(trace.controls)
            trace.hook = hook
            session.run_until_pause()
            pair = seen.downloads[0][1]
            labels = {'receipts', '_directory_guard', '_local_records', '_deflate_integrity', 'copy', 'output_hash', 'revalidate'}
            rows = [(label, kwargs) for label, kwargs in activation if label in labels]
            self.assertEqual({label for label, _ in rows}, labels)
            self.assertTrue(all(kw['deadline'] == pair['deadline'] and kw['check_active'] is pair['check_active'] for _, kw in rows))
            self.bindings(seen.stage, fixture)
            self.children_exited(seen, 2)
            self.assertEqual([ident for ident, _ in seen.downloads], [14, 13])
            self.assertEqual(len(seen.stage._roots), 6)

    failed_activation = run_failed_activation

    def test_activation_cancellation_and_timeout_stop_later_phases(self):
        for phase in ('receipts', 'copy', 'output_hash', 'revalidate'):
            for cancelled in (False, True):
                with self.subTest(phase=phase, cancelled=cancelled):
                    self.failed_activation(phase, cancelled)

    def test_activation_cleanup_failures_remain_sticky(self):
        for fault in ('root_failure', 'api_failure', 'handle_failure'):
            for cancelled in (False, True):
                with self.subTest(fault=fault, cancelled=cancelled):
                    self.failed_activation('revalidate', cancelled, **{fault: True})

    def test_later_revalidation_uses_current_operation_budget(self):
        with self.padded_session() as (session, tls, _, seen), self.trace_calls() as trace:
            session.run_until_pause()
            owner, handles = seen.stage, tuple(seen.stage._handles)
            activation_deadline = owner._deadline
            clock = SimpleNamespace(monotonic=lambda: activation_deadline + 10)
            trace.controls.clear()
            calls, authenticate = [], wire._authenticate
            def authenticated(*args, **kwargs):
                calls.append((session._inflight.kind, kwargs.copy()))
                return authenticate(*args, **kwargs)
            with patch.object(safe, 'time', clock), patch.object(executor, 'time', clock), patch.object(wire, '_authenticate', authenticated):
                result = session.request_publish(old.ExecutorCases.request(session))
            self.assertEqual(result.state.outcome, 'modeled_verified')
            rows = [kw for label, kw in trace.controls if label == 'revalidate']
            self.assertEqual([kind for kind, _ in calls], ['ObserveFence', 'PublishPrerelease', 'VerifyPublished'])
            authentication = [kwargs for kind, kwargs in calls if kind in ('ObserveFence', 'ObserveDraft', 'VerifyPublished')]
            self.assertEqual(len(rows), len(authentication))
            self.assertTrue(all(row['deadline'] == auth['deadline'] and row['check_active'] is auth['check_active']
                                for row, auth in zip(rows, authentication)))
            self.assertTrue(rows and all(kw['deadline'] > activation_deadline for kw in rows))
            self.assertTrue(all(kw['check_active'].__self__ is session for kw in rows))
            self.assertEqual(owner._deadline, activation_deadline)
            self.assertEqual(tuple(owner._handles), handles)
            self.assertTrue(all(handle.closed for handle in handles))
            self.assertEqual(len(old.ExecutorCases.mutations(tls)), 8)

    def test_later_revalidation_cancel_timeout_preserve_effects(self):
        for phase, count, outcome in (('ObserveFence', 0, 'blocked_no_effect'), ('ObserveDraft', 1, 'partial_draft'),
                                       ('ObserveDraft', 7, 'partial_draft'),
                                       ('VerifyPublished', 8, 'published_unverified')):
            for cancelled in (False, True):
                with self.padded_session() as (session, tls, _, seen), self.trace_calls() as trace:
                    if phase == 'VerifyPublished': session.run_until_pause()
                    stopped = []
                    def hook(event):
                        if (not stopped and session._inflight is not None and session._inflight.kind == phase
                                and len(old.ExecutorCases.mutations(tls)) == count
                                and event.phase == 'revalidate' and event.kind == 'binary.read'):
                            stopped.append(len(trace.events))
                            if cancelled: session.cancel()
                    trace.hook = hook
                    now = lambda: session._deadline if stopped and not cancelled else time.monotonic()
                    with patch.object(safe, 'time', SimpleNamespace(monotonic=now)), patch.object(executor, 'time', SimpleNamespace(monotonic=now)):
                        result = session.request_publish(old.ExecutorCases.request(session)) if phase == 'VerifyPublished' else session.run_until_pause()
                    self.assertEqual(len(stopped), 1)
                    self.no_later_bytes(trace, stopped[0])
                    self.assertEqual((result.state.code, result.state.outcome), ('cancelled' if cancelled else 'timeout', outcome))
                    self.assertEqual(len(old.ExecutorCases.mutations(tls)), count)
                    self.assertTrue(session._closed)
                    self.assertTrue(all(handle.closed for handle in seen.stage._handles))

    def test_later_revalidation_errors_do_not_gain_authority(self):
        for value in ('unrelated', [], object()):
            with self.padded_session() as (session, tls, _, seen):
                revalidate = stage.StagedAssets.revalidate
                def failed(owner, **kwargs):
                    if session._inflight is None: return revalidate(owner, **kwargs)
                    error = safe.ConsumerError('unrelated')
                    error.code = value
                    raise error
                with patch.object(stage.StagedAssets, 'revalidate', failed):
                    result = session.run_until_pause()
                self.assertEqual((result.state.code, result.state.outcome), ('adapter_error', 'blocked_no_effect'))
                self.assertEqual(old.ExecutorCases.mutations(tls), [])
                self.assertTrue(all(handle.closed for handle in seen.stage._handles))
        with self.padded_session() as (session, tls, _, seen):
            session.run_until_pause()
            owner = seen.stage
            close = owner.close
            def bad_close():
                close()
                raise OSError('injected retired owner close failure')
            with patch.object(owner, 'close', bad_close):
                result = session.request_publish(old.ExecutorCases.request(session))
            self.assertEqual((result.state.code, result.state.outcome), ('adapter_error', 'published_unverified'))
            self.assertTrue(session._cleanup_failed)
            self.assertEqual(len(old.ExecutorCases.mutations(tls)), 8)
            with self.assertRaises(wire.WireFailure) as failure: session.close()
            self.assertEqual((failure.exception.code, failure.exception.effect), ('adapter_error', 'none'))
        for phase, count, outcome in (('ObserveDraft', 1, 'partial_draft'), ('VerifyPublished', 8, 'published_unverified')):
            with self.padded_session() as (session, tls, _, seen), self.trace_calls() as trace:
                if phase == 'VerifyPublished': session.run_until_pause()
                stopped, retired = [], []
                def hook(event):
                    if (not stopped and session._inflight is not None and session._inflight.kind == phase
                            and event.phase == 'revalidate' and event.kind == 'binary.read'):
                        stopped.append(len(trace.events))
                trace.hook = hook
                close = stage.StagedAssets.close
                def failed_close(owner):
                    retired.append(owner)
                    close(owner)
                    raise OSError('injected retired stage close failure')
                now = lambda: session._deadline if stopped else time.monotonic()
                with (patch.object(stage.StagedAssets, 'close', failed_close),
                      patch.object(safe, 'time', SimpleNamespace(monotonic=now)),
                      patch.object(executor, 'time', SimpleNamespace(monotonic=now))):
                    result = session.request_publish(old.ExecutorCases.request(session)) if phase == 'VerifyPublished' else session.run_until_pause()
                self.assertEqual(len(stopped), 1)
                self.no_later_bytes(trace, stopped[0])
                self.assertEqual((result.state.code, result.state.outcome), ('timeout', outcome))
                self.assertEqual(len(old.ExecutorCases.mutations(tls)), count)
                self.assertEqual(retired, [seen.stage])
                self.assertTrue(session._cleanup_failed)
                self.assertTrue(all(handle.closed for handle in seen.stage._handles))
                with self.assertRaises(wire.WireFailure) as failure: session.close()
                self.assertEqual((failure.exception.code, failure.exception.effect), ('adapter_error', 'none'))


if __name__ == '__main__':
    unittest.main()
