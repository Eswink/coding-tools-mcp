"""Cooperative archive boundaries over real parsers, files and TLS workers."""
from decimal import Decimal
import gzip
import hashlib
import json
import random
import struct
import tarfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

import rc_artifact_consumer as consumer
import rc_consumer_archive as archive
import rc_consumer_archive_tests as fixtures
import rc_consumer_checksum_budget_cases as checksum
import rc_consumer_io as safe
import rc_consumer_snapshot as snapshot
import rc_publication_executor as executor
import rc_publication_stage as stage
import rc_publication_staging_budget_cases as staging


from rc_consumer_archive_budget_support import Budget, Trace


class ArchiveBudgetCases(unittest.TestCase):
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

    def cloud(self, *, large=False, bad_elf=False, bad_digest=False, padding=True):
        elf = b'\x7fELF\x02\x01' + b'\0' * 12 + b'\x3e\0'
        elf += random.Random(88).randbytes(3 * safe.CHUNK) if large else b'synthetic; never execute'
        if bad_elf:
            elf = b'X' + elf[1:]
        manifest = {'binaries': {name: {'size': len(elf), 'sha256': hashlib.sha256(elf).hexdigest()}
                                 for name in archive.BINS}}
        if bad_digest:
            manifest['binaries'][archive.BINS[0]]['sha256'] = '0' * 64
        entries = [(name, elf if name.startswith('bin/') else json.dumps(manifest).encode()
                    if name == 'manifest.json' else b'synthetic documentation')
                   for name in sorted(archive.CLOUD_MEMBERS)]
        raw, _ = fixtures.synthetic_tar(entries)
        if not padding:
            end = sum(512 + (len(data) + 511) // 512 * 512 for _, data in entries)
            raw = raw[:end + 512]
        return self.file(gzip.compress(raw)), manifest, dict(entries)

    def extract(self, kind, path, root, **controls):
        if kind == 'zip':
            return archive.extract_bounded_zip(path, root, {'payload.exe'}, **controls)
        return archive.extract_bounded_cloud_tar(path, root, **controls)

    def stop_at(self, kind, path, selected, *, occurrence=1, cancelled=True, expected=None, change=None):
        budget, root, matches, trigger = Budget(cancelled), self.root(), [], []
        fd = root.fd
        def hook(event):
            if selected(event):
                matches.append(event)
                if len(matches) == occurrence:
                    if change:
                        change(event)
                    budget.stopped = True
                    trigger.append(len(trace.events))
        trace = Trace(hook, budget)
        with trace.installed(), patch.object(safe, 'time', SimpleNamespace(monotonic=budget.now)):
            self.failure(lambda: self.extract(kind, path, root, **budget.controls), expected or budget.code)
        self.assertEqual(len(matches), occurrence)
        self.assertEqual(len(trigger), 1)
        forbidden = ('.read', '.write', '.decompress', '.acquire', '.entry', '.member')
        self.assertFalse([e.kind for e in trace.events[trigger[0]:]
                          if e.kind.endswith(forbidden) and '_close.' not in e.kind], trace.events[trigger[0]:])
        self.assertTrue(all(stream.closed for stream in trace.streams))
        self.assertEqual(root.fd, fd)
        if expected:
            self.assertEqual(trace.failures[-1], (expected, budget.polls))
        return trace, root, budget

    def test_default_archive_results_and_omitted_controls(self):
        clock = SimpleNamespace(monotonic=lambda: self.fail('omitted controls read clock'))
        for compression, zip64 in ((zipfile.ZIP_STORED, False), (zipfile.ZIP_DEFLATED, False),
                                   (zipfile.ZIP_DEFLATED, True)):
            entries = [('payload.exe', b'payload'), ('evidence/a', b'evidence')]
            path, root, trace = self.zip(entries, compression, zip64), self.root(), Trace()
            with trace.installed(), patch.object(safe, 'time', clock):
                self.assertEqual(archive.inspect_zip_directory(path)['count'], 2)
                self.assertEqual(self.extract('zip', path, root), ('evidence/a', 'payload.exe'))
            self.assertEqual({name: root.read(name) for name, _ in entries}, dict(entries))
            self.assertTrue(all((root.path / name).stat().st_mode & 0o777 == 0o600 for name in root.files()))
            self.assertTrue(all(not kwargs for label, kwargs in trace.controls
                                if label.startswith('_') or label == 'extract_bounded_zip'))
        path, expected, entries = self.cloud()
        root, trace = self.root(), Trace()
        with trace.installed(), patch.object(safe, 'time', clock):
            self.assertEqual(self.extract('tar', path, root), expected)
        self.assertEqual({name: root.read(name) for name in root.files()}, entries)
        self.assertTrue(all((root.path / name).stat().st_mode & 0o777 == 0o600 for name in root.files()))
        self.assertEqual([kwargs for label, kwargs in trace.controls if label == 'hash_file'], [{}] * 4)
        receipt = self.zip([('rc-consumer-receipts-case/' + name, b'{}') for name in sorted(stage.NAMES)])
        trace = Trace()
        with trace.installed(), patch.object(safe, 'time', clock):
            destination = self.root()
            stage._receipts(receipt, destination)
            self.assertEqual(set(destination.files()), stage.NAMES)
        self.assertTrue(all(not kwargs for label, kwargs in trace.controls if label.startswith('_')))

    def test_invalid_controls_stop_before_parser_io(self):
        invalid = (True, False, Decimal('1'), type('Integer', (int,), {})(2), type('Float', (float,), {})(2),
                   'private', object(), float('nan'), float('inf'), float('-inf'))
        root = self.root()
        with patch.object(safe.PrivateRoot, 'files', side_effect=AssertionError('destination inspected')), \
             patch.object(archive, 'open_file', side_effect=AssertionError('file acquired')), \
             patch.object(archive.os, 'fstat', side_effect=AssertionError('raw inspected')):
            for kind in ('zip', 'tar', 'gzip'):
                action = lambda controls: archive._GzipReader(object(), **controls) if kind == 'gzip' else \
                    self.extract(kind, '/absent', root, **controls)
                for deadline in invalid:
                    self.failure(lambda: action(dict(deadline=deadline)), 'invalid_transport_deadline')
                for active in (False, 0, object()):
                    self.failure(lambda: action(dict(check_active=active)), 'artifact_transport_failed')

    def test_original_deadline_and_sanitized_callback_errors(self):
        callback, deadline = lambda: None, 10**10000
        path, expected, _ = self.cloud()
        trace = Trace()
        with trace.installed():
            self.assertEqual(self.extract('tar', path, self.root(), deadline=deadline, check_active=callback), expected)
        forwarded = [kwargs for label, kwargs in trace.controls if label in
                     {'extract_bounded_cloud_tar', 'gzip_reader', 'hash_file'}]
        self.assertEqual(len(forwarded), 6)
        self.assertTrue(all(kwargs['deadline'] is deadline and kwargs['check_active'] is callback for kwargs in forwarded))
        path = self.zip([('payload.exe', b'data')])
        trace = Trace()
        with trace.installed():
            self.extract('zip', path, self.root(), deadline=deadline, check_active=callback)
        self.assertTrue(all(kwargs['deadline'] is deadline and kwargs['check_active'] is callback
                            for label, kwargs in trace.controls if label.startswith('_')))
        class Hostile(BaseException):
            @property
            def code(self):
                raise SystemExit('private')
        for kind in ('zip', 'tar'):
            source = path if kind == 'zip' else self.cloud()[0]
            for code, expected_code in (('cancelled', 'transport_cancelled'), ('timeout', 'transport_deadline_exceeded'),
                                        ('unknown', 'artifact_transport_failed'), ([], 'artifact_transport_failed')):
                def active():
                    error = safe.ConsumerError('private')
                    error.code = code
                    raise error
                self.failure(lambda: snapshot._call(self.extract, kind, source, self.root(), check_active=active),
                             expected_code, clean=True)
            def hostile():
                raise Hostile('private')
            self.failure(lambda: self.extract(kind, source, self.root(), check_active=hostile),
                         'artifact_transport_failed', clean=True)
            for value in (False, 0, 'private'):
                self.failure(lambda: self.extract(kind, source, self.root(), check_active=lambda: value),
                             'artifact_transport_failed', clean=True)
            for exception, args in ((KeyboardInterrupt, ()), (SystemExit, (1,))):
                def active():
                    raise exception('private')
                with self.assertRaises(exception) as caught:
                    self.extract(kind, source, self.root(), check_active=active)
                self.assertEqual(caught.exception.args, args)
                self.assertIsNone(caught.exception.__context__)
                self.assertIsNone(caught.exception.__cause__)
            with patch.object(safe, 'time', SimpleNamespace(monotonic=lambda: 101)):
                self.failure(lambda: self.extract(kind, source, self.root(), deadline=101), 'transport_deadline_exceeded')
            with patch.object(safe, 'time', SimpleNamespace(monotonic=lambda: self.fail('callback-only clock'))):
                self.extract(kind, source, self.root(), check_active=callback)

    def test_directory_and_local_record_checkpoints(self):
        path = self.zip([('payload.exe', b'one'), ('evidence/a', b'two'), ('evidence/b', b'three')])
        for phase in ('_directory_guard', '_local_records'):
            trace, root, _ = self.stop_at('zip', path, lambda e: e.kind == 'record' and e.key == phase
                                         and e.size == 0, occurrence=2)
            self.assertEqual(root.files(), ())
            self.assertEqual(trace.count('zip.acquire'), 0)
            if phase == '_directory_guard':
                self.assertEqual(trace.count('zip_archive.entry'), 0)
        for boundary in ('sort.return', 'inventory.return', 'zip_archive.return'):
            self.stop_at('zip', path, lambda e: e.kind == boundary)
        self.stop_at('zip', path, lambda e: e.kind == 'record' and e.key == '_directory_guard' and e.size == 4)
        raw = bytearray(path.read_bytes())
        struct.pack_into('<HH', raw, len(raw) - 14, 2, 2)
        trace, _, budget = self.stop_at('zip', self.file(raw), lambda e: e.kind == 'record'
            and e.key == '_directory_guard' and e.size == 0, occurrence=2, expected='zip_directory_count')

    def test_real_deflate_input_output_and_stored_boundaries(self):
        for payload, boundary in ((random.Random(88).randbytes(4 * safe.CHUNK), 'raw.read'),
                                  (bytes(range(256)) * 900, 'decoder.decompress')):
            path = self.zip([('payload.exe', payload)])
            for cancelled in (False, True):
                trace, root, _ = self.stop_at('zip', path, lambda e: e.kind == boundary and
                    (e.phase == '_deflate_integrity' and e.size == safe.CHUNK
                     if boundary == 'raw.read' else e.key == 'deflate'),
                    occurrence=2, cancelled=cancelled)
                self.assertEqual(root.files(), ())
                self.assertEqual(trace.count('zip.acquire'), 0)
                if boundary == 'decoder.decompress':
                    self.assertEqual([len(e.result) for e in trace.events if e.kind == boundary], [safe.CHUNK] * 2)
        path = self.zip([('payload.exe', b'stored')], zipfile.ZIP_STORED)
        budget = Budget()
        original = archive.need
        def checked(condition, code):
            original(condition, code)
            if code == 'zip_stored_size':
                budget.stopped = True
        with patch.object(archive, 'need', checked), patch.object(zipfile.ZipFile, 'open',
                side_effect=AssertionError('extraction reached')):
            self.failure(lambda: self.extract('zip', path, self.root(), **budget.controls), budget.code)

        path = self.zip([('payload.exe', b'terminal deflate fixture')])
        for fault, code in (('eof', 'zip_deflate_eof'), ('size', 'zip_deflate_eof'), ('hidden', 'zip_hidden_data')):
            with zipfile.ZipFile(path) as source:
                info = source.infolist()[0]
            if fault == 'size':
                info.file_size += 1
            else:
                info.compress_size += -1 if fault == 'eof' else 1
            budget = Budget()
            def terminal(event):
                if event.kind == 'decoder.decompress' and event.key == 'deflate':
                    budget.stopped = True
            trace = Trace(terminal, budget)
            with path.open('rb') as raw, trace.installed():
                self.failure(lambda: archive._deflate_integrity(raw, info, **budget.controls), code)
            self.assertEqual(trace.count('decoder.decompress'), 1)
            self.assertEqual(trace.failures[-1], (code, budget.polls))

    def test_zip_read_write_directory_and_eof_boundaries(self):
        path = self.zip([('payload.exe', random.Random(88).randbytes(3 * safe.CHUNK)), ('evidence/next', b'later')])
        for event, occurrence in (('zip.read', 2), ('output.write', 1)):
            trace, root, _ = self.stop_at('zip', path, lambda e: e.kind == event, occurrence=occurrence)
            self.assertEqual(root.files(), ('payload.exe',))
            self.assertEqual((root.path / 'payload.exe').stat().st_size, safe.CHUNK)
            self.assertEqual(trace.count('zip.acquire'), 1)
        self.stop_at('zip', path, lambda e: e.kind == 'zip.read' and not e.result)
        self.stop_at('zip', path, lambda e: e.kind == 'zip.read' and not e.result,
                     expected='zip_member_size', change=lambda e: setattr(e.owner, 'file_size', e.owner.file_size + 1))
        directory = self.zip([('evidence/', b''), ('payload.exe', b'later')])
        for boundary in ('zip.read', 'mkdir.return'):
            trace, root, _ = self.stop_at('zip', directory, lambda e: e.kind == boundary)
            self.assertEqual(trace.count('output.write'), 0)
            self.assertEqual(root.files(), ())

    def test_gzip_raw_decompress_trailer_and_empty_reads(self):
        payload = random.Random(88).randbytes(4 * safe.CHUNK)
        for boundary, count in (('raw.read', 2), ('decoder.decompress', 2), ('raw.read', 1)):
            budget, trace = Budget(boundary != 'decoder.decompress'), Trace()
            matches = []
            def hook(event):
                selected = event.kind == boundary and (event.size == 1 if count == 1 else event.size != 1)
                if selected:
                    matches.append(event)
                    if len(matches) == count:
                        budget.stopped = True
            trace.hook = hook
            with trace.installed(), patch.object(safe, 'time', SimpleNamespace(monotonic=budget.now)), \
                 safe.open_file(self.file(gzip.compress(payload))) as raw:
                reader = archive._GzipReader(raw, **budget.controls)
                accepted = []
                def drain():
                    while data := reader.read(safe.CHUNK):
                        accepted.append(data)
                self.failure(drain, budget.code)
                self.assertEqual(len(matches), count)
                self.assertLess(sum(map(len, accepted)), len(payload))
            self.assertTrue(all(stream.closed for stream in trace.streams))
        for finished in (False, True):
            budget = Budget(not finished)
            with patch.object(safe, 'time', SimpleNamespace(monotonic=budget.now)), \
                 self.file(gzip.compress(b'data')).open('rb') as raw:
                reader = archive._GzipReader(raw, **budget.controls)
                if finished:
                    self.assertEqual(reader.read(safe.CHUNK), b'data')
                    self.assertTrue(reader.finished)
                position = raw.tell()
                with budget.after_entry(), patch.object(raw, 'read', wraps=raw.read) as reads:
                    self.failure(lambda: reader.read(1 if finished else 0), budget.code)
                    reads.assert_not_called()
                self.assertEqual(raw.tell(), position)

        for fault, payload in (('unused', b'data'), ('pending', random.Random(88).randbytes(safe.CHUNK + 1))):
            budget = Budget()
            def trailing(event):
                if event.kind == 'decoder.decompress' and event.owner.eof:
                    if fault == 'pending':
                        event.owner.unconsumed_tail = b'x'  # Inject inconsistent state after real decompression.
                    else:
                        self.assertTrue(event.owner.unused_data)
                    budget.stopped = True
            trace = Trace(trailing, budget)
            path = self.file(gzip.compress(payload) + (b'trailing' if fault == 'unused' else b''))
            with trace.installed(), safe.open_file(path) as raw:
                reader = archive._GzipReader(raw, **budget.controls)
                def drain():
                    while reader.read(safe.CHUNK):
                        pass
                self.failure(drain, 'gzip_trailing_data')
            self.assertTrue(budget.stopped)
            self.assertEqual(trace.failures[-1], ('gzip_trailing_data', budget.polls))

    def test_tar_member_payload_and_padding_boundaries(self):
        path, _, _ = self.cloud(large=True)
        for event, occurrence in (('tar.read', 2), ('output.write', 2), ('tar.member', 3),
                                   ('padding.read', 1), ('tar.acquire', 1)):
            trace, root, _ = self.stop_at('tar', path, lambda e: e.kind == event
                and (e.key.startswith('bin/') and bool(e.result) if event == 'tar.read' else True),
                                         occurrence=occurrence, cancelled=event != 'output.write')
            if event == 'tar.acquire':
                self.assertEqual(trace.count('output.acquire'), 0)
                self.assertEqual(trace.count('tar.enter'), 1)
                self.assertEqual(trace.count('tar.close'), 1)
                self.assertEqual(root.files(), ())
        self.stop_at('tar', path, lambda e: e.kind == 'tar.read' and not e.result,
                     expected='tar_member_size', change=lambda e: setattr(e.owner, 'size', e.owner.size + 1))
        self.stop_at('tar', path, lambda e: e.kind == 'padding.read' and not e.result)
        self.stop_at('tar', self.cloud(padding=False)[0], lambda e: e.kind == 'padding.read' and not e.result,
                     expected='tar_incomplete_padding')

    def test_cloud_manifest_header_and_hash_boundaries(self):
        path, expected, _ = self.cloud(large=True)
        for selected, count in ((lambda e: e.kind == 'json_file.return', 1),
                (lambda e: e.kind == 'binary.read' and e.size == 20, 1),
                (lambda e: e.kind == 'hash.read', 2), (lambda e: e.kind == 'hash_file.return', 4)):
            trace, root, _ = self.stop_at('tar', path, selected, occurrence=count, cancelled=count != 2)
            self.assertEqual(json.loads(root.read('manifest.json')), expected)
            self.assertEqual(trace.count('hash_file.entry'), 4 if count == 4 else 1 if count == 2 else 0)
        for close_fails in (False, True):
            bad, _, _ = self.cloud(bad_elf=True)
            budget, polls = Budget(), []
            def hook(event):
                if event.kind == 'binary.read' and event.size == 20:
                    budget.stopped = True
                if event.kind == 'binary.close' and budget.stopped and close_fails:
                    polls.append(budget.polls)
                    raise OSError('injected close failure')
            trace = Trace(hook, budget)
            with trace.installed():
                self.failure(lambda: self.extract('tar', bad, self.root(), **budget.controls),
                             'invalid_cloud_archive' if close_fails else 'cloud_binary_elf')
            self.assertEqual(trace.count('hash_file.entry'), 0)
            if not close_fails:
                self.assertEqual(trace.failures[-1], ('cloud_binary_elf', budget.polls))
            if close_fails:
                self.assertEqual(polls, [budget.polls])

    def test_late_close_inventory_and_io_failure_precedence(self):
        for kind in ('zip', 'tar'):
            path = self.zip([('payload.exe', b'data')]) if kind == 'zip' else self.cloud()[0]
            boundaries = ('output.close', kind + '.close', 'raw.close',
                          'zip_archive_close.return' if kind == 'zip' else 'tar_archive_close.return',
                          'inventory.return')
            for boundary in boundaries:
                self.stop_at(kind, path, lambda e: e.kind == boundary,
                             occurrence=2 if boundary == 'inventory.return' else 1)
            for boundary in (kind + '.read', 'output.write', 'output.close', 'inventory.return'):
                codes = []
                for controlled in (False, True):
                    budget, polls = Budget(), []
                    def hook(event):
                        if event.kind == boundary:
                            budget.stopped = True
                            polls.append(budget.polls)
                            raise OSError('injected I/O failure, not an observed OS failure')
                    with Trace(hook).installed():
                        with self.assertRaises((safe.ConsumerError, OSError)) as caught:
                            self.extract(kind, path, self.root(), **(budget.controls if controlled else {}))
                    codes.append(getattr(caught.exception, 'code', type(caught.exception)))
                    self.assertEqual(polls, [budget.polls])
                self.assertEqual(codes[0], codes[1])

    def test_existing_archive_rejections_with_active_controls(self):
        stored = self.zip([('payload.exe', b'payload')], zipfile.ZIP_STORED).read_bytes()
        crc = bytearray(stored)
        crc[30 + len('payload.exe')] ^= 1
        zip_cases = [(self.file(crc), 'invalid_zip'), (self.file(b'prefix' + stored), 'zip_directory_limit'),
                     (self.zip([('../unsafe', b'x')]), 'unsafe_path'),
                     (self.zip([('payload.exe', b'a' * (16 * safe.CHUNK))]), 'zip_expansion_limit')]
        raw, _ = fixtures.synthetic_tar()
        info = tarfile.TarInfo('manifest.json')
        info.type, info.size = tarfile.XHDTYPE, 2**40
        tar_cases = [(self.file(gzip.compress(info.tobuf())), 'tar_extension_or_special'),
                     (self.file(gzip.compress(raw)[:-8]), 'truncated_gzip'),
                     (self.file(gzip.compress(raw) + gzip.compress(b'next')), 'gzip_trailing_data'),
                     (self.file(gzip.compress(raw + b'x')), 'tar_trailing_data'),
                     (self.cloud(bad_elf=True)[0], 'cloud_binary_elf'),
                     (self.cloud(bad_digest=True)[0], 'cloud_binary_digest')]
        oversized = bytearray(stored)
        central = oversized.index(b'PK\x01\x02')
        struct.pack_into('<I', oversized, central + 24, safe.FILE_LIMIT + 1)
        zip_cases.append((self.file(oversized), 'zip_expansion_limit'))
        count = bytearray(stored)
        struct.pack_into('<HH', count, len(count) - 14, archive.ENTRY_LIMIT + 1, archive.ENTRY_LIMIT + 1)
        zip_cases.append((self.file(count), 'zip_directory_limit'))
        special = tarfile.TarInfo('manifest.json')
        special.type = tarfile.SYMTYPE
        tar_cases.append((self.file(gzip.compress(special.tobuf())), 'tar_extension_or_special'))
        for kind, cases in (('zip', zip_cases), ('tar', tar_cases)):
            for path, code in cases:
                for controls in ({}, {'check_active': lambda: None}):
                    self.failure(lambda: self.extract(kind, path, self.root(), **controls), code)

    def test_two_downloads_share_controls_through_real_archives(self):
        with self.padded_session() as (session, _, fixture, seen), Trace().installed() as trace:
            clock = time.monotonic
            remaining = []
            checked = safe._check_budget
            def check(deadline, active):
                if deadline is not None:
                    remaining.append(deadline - clock())
                return checked(deadline, active)
            with patch.object(archive, '_check_budget', check):
                session.run_until_pause()
            handles = self.bindings(seen.stage, fixture)
            self.children_exited(seen, 2)
            self.assertEqual([ident for ident, _ in seen.downloads], [14, 13])
            deadline = seen.downloads[0][1]['deadline']
            callback = seen.downloads[0][1]['check_active']
            self.assertEqual(seen.downloads[1][1]['deadline'], deadline)
            self.assertIs(seen.downloads[1][1]['check_active'], callback)
            labels = {'extract_bounded_zip', 'extract_bounded_cloud_tar', 'gzip_reader', 'hash_file'}
            forwarded = [kwargs for label, kwargs in trace.controls if label in labels and kwargs]
            self.assertTrue(all(kwargs['deadline'] == deadline and kwargs['check_active'] is callback
                                for kwargs in forwarded))
            self.assertGreater(len(forwarded), 6)
            self.assertGreater(remaining[0], remaining[-1])
            session.close()
            self.assertEqual(len(seen.roots), 6)
            self.assertTrue(all(handle.closed for handle in handles))

    def archive_failure(self, cancelled, boundary, **faults):
        with self.padded_session(**faults) as (session, tls, _, seen):
            stopped, trigger = [], []
            def now():
                return session._deadline if stopped and not cancelled else time.monotonic()
            def hook(event):
                if stopped:
                    return
                selected = {'entry': event.kind == 'extract_bounded_zip.entry',
                    'zip': event.kind == 'zip.read' and event.key == 'packaging-report.json' and bool(event.result),
                    'zip_eof': event.kind == 'zip.read' and event.key == 'packaging-report.json' and not event.result,
                    'tar': event.kind == 'tar.read', 'gzip': event.kind == 'decoder.decompress' and event.key == 'gzip',
                    'hash': event.kind == 'hash.read' and '/bin/' in event.key, 'return': event.kind == 'hash_file.return'
                    and event.owner[0].name == archive.BINS[-1]}[boundary]
                if selected:
                    trigger.append(event)
                    if boundary != 'zip' or len(trigger) == 2:
                        self.children_exited(seen, 2)
                        stopped.append(len(trace.events))
                        if cancelled:
                            session.cancel()
            trace = Trace(hook)
            code = 'adapter_error' if faults else 'cancelled' if cancelled else 'timeout'
            with trace.installed(), patch.object(safe, 'time', SimpleNamespace(monotonic=now)), \
                 patch.object(executor, 'time', SimpleNamespace(monotonic=now)), \
                 patch.object(consumer.contracts, 'verify_consumed_bundle',
                              wraps=consumer.contracts.verify_consumed_bundle) as contracts:
                self.failed_run(session, code)
            self.assertTrue(stopped)
            self.assertEqual(len(seen.stage._roots), 6)
            self.assertTrue(all(stream.closed for stream in trace.streams))
            contracts.assert_not_called()
            self.assertFalse([e.kind for e in trace.events[stopped[0]:]
                              if e.kind.endswith(('.read', '.write', '.decompress', '.member', '.acquire', '.entry'))
                              and '_close.' not in e.kind])
            self.activation_failed(session, tls, seen, code, 2, sticky=bool(faults))

    def test_archive_cancellation_reaps_both_children(self):
        for boundary in ('zip', 'tar', 'gzip', 'hash'):
            with self.subTest(boundary=boundary):
                self.archive_failure(True, boundary)

    def test_archive_timeout_reaps_both_children(self):
        for boundary in ('entry', 'zip', 'zip_eof', 'tar', 'return'):
            with self.subTest(boundary=boundary):
                self.archive_failure(False, boundary)

    def test_archive_cleanup_failures_remain_sticky(self):
        for cancelled in (False, True):
            for fault in ('root_failure', 'api_failure'):
                with self.subTest(cancelled=cancelled, fault=fault):
                    self.archive_failure(cancelled, 'zip' if cancelled else 'hash', **{fault: True})


if __name__ == '__main__':
    unittest.main()
