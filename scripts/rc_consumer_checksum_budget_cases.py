"""Cooperative checksum controls over real files and workers; synthetic authority only."""
from contextlib import contextmanager
from decimal import Decimal
import hashlib
from pathlib import Path
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import rc_artifact_consumer as consumer
import rc_consumer_archive as archive
import rc_consumer_archive_tests as archive_fixtures
import rc_consumer_io as safe
import rc_publication_executor as executor
import rc_publication_stage as stage
import rc_publication_staging_budget_cases as staging
from rc_publication_stage_cases import SourceFixture, publisher_fixture, artifact_worker


class ChecksumBudgetCases(unittest.TestCase):
    # Reuse fixture methods, never inherit or rediscover old test methods.
    setUp = archive_fixtures.ArchiveTests.setUp
    root = archive_fixtures.ArchiveTests.root
    recording = staging.StagingBudgetCases.recording
    session = staging.StagingBudgetCases.session
    children_exited = staging.StagingBudgetCases.children_exited
    bindings = staging.StagingBudgetCases.bindings
    activation_failed = staging.StagingBudgetCases.activation_failed
    failed_run = staging.StagingBudgetCases.failed_run

    def inventory_root(self, entries=None, text=None):
        entries = entries or {'a': bytes(range(256)) * 800, 'b': b'second'}
        root = self.root()
        for name, data in entries.items():
            root.write(name, data)
        if text is None:
            text = ''.join(hashlib.sha256(data).hexdigest() + '  ' + name + '\n'
                           for name, data in entries.items())
        root.write('SHA256SUMS.txt', text.encode())
        return root, entries

    def failure(self, action, code, *, clean=False):
        with self.assertRaises(safe.ConsumerError) as caught:
            action()
        error = caught.exception
        self.assertEqual((error.code, error.args), (code, (code,)))
        if clean:
            self.assertIsNone(error.__context__)
            self.assertIsNone(error.__cause__)
        return error

    @contextmanager
    def reads(self, select=lambda path: True, hook=lambda *_: None, closed=lambda *_: None):
        opened, calls, streams = safe.open_file, [], []

        @contextmanager
        def observed(path):
            with opened(path) as stream:
                streams.append(stream)
                if not select(Path(path)):
                    yield stream
                else:
                    def read(size):
                        data = stream.read(size)
                        calls.append((Path(path), size, len(data)))
                        hook(Path(path), data, calls)
                        return data
                    yield SimpleNamespace(read=read, fileno=stream.fileno)
            closed(Path(path))

        with patch.object(safe, 'open_file', observed):
            yield calls, streams

    @contextmanager
    def padded_session(self, **faults):
        refresh = SourceFixture.refresh_reports

        def padded(fixture):
            refresh(fixture)
            path = fixture.bundle / 'packaging-report.json'
            path.write_bytes(path.read_bytes() + b' \n' * (2 * safe.CHUNK))
            fixture.checksums()

        with patch.object(SourceFixture, 'refresh_reports', padded), self.session(**faults) as value:
            yield value

    def test_default_hash_inventory_and_bundle_call_shapes(self):
        root, entries = self.inventory_root()
        no_clock = SimpleNamespace(monotonic=lambda: self.fail('default checksum read clock'))
        hashed, verify = archive.hash_file, archive.verify_checksum_inventory
        calls, inventories = [], []

        def hash_observed(path, **kwargs):
            calls.append(kwargs.copy())
            return hashed(path, **kwargs)

        def inventory_observed(owner, **kwargs):
            inventories.append(kwargs.copy())
            return verify(owner, **kwargs)

        with patch.object(safe, 'time', no_clock), patch.object(archive, 'hash_file', hash_observed):
            self.assertEqual(verify(root), {n: hashlib.sha256(d).hexdigest() for n, d in entries.items()})
            self.assertEqual(calls, [{}] * len(entries))
        with publisher_fixture() as fixture, artifact_worker(fixture), self.recording() as seen:
            owner = stage.stage_selected(fixture.root, fixture.selection, fixture.api, temporary_parent=fixture.parent)
            try:
                with patch.object(safe, 'time', no_clock), patch.object(archive, 'verify_checksum_inventory', inventory_observed):
                    owner.__enter__()
                self.assertEqual(inventories, [{}])
                self.assertEqual(seen.downloads, [(14, {}), (13, {'opener': None})])
                self.children_exited(seen, 2)
            finally:
                owner.close()

    def test_invalid_controls_reject_before_io(self):
        class Integer(int): pass
        class Float(float): pass
        invalid = (True, False, Integer(2), Float(2), Decimal('2'), 'PRIVATE', object(),
                   float('nan'), float('inf'), float('-inf'))
        for function, operand in ((safe.hash_file, '/absent'),
                (archive.verify_checksum_inventory, SimpleNamespace(files=lambda: self.fail('root reached')))):
            for value in invalid:
                with self.subTest(function=function.__name__, kind=type(value).__name__):
                    self.failure(lambda: function(operand, deadline=value), 'invalid_transport_deadline', clean=True)
            for callback in (False, 0, object()):
                self.failure(lambda: function(operand, check_active=callback), 'artifact_transport_failed', clean=True)

    def test_deadline_boundaries_huge_values_and_callback_only(self):
        root, entries = self.inventory_root({'a': b'payload'})
        now = [100]
        with patch.object(safe, 'time', SimpleNamespace(monotonic=lambda: now[0])):
            for value in (0, 99, 100, -10**10000):
                self.failure(lambda: safe.hash_file(root.path / 'a', deadline=value), 'transport_deadline_exceeded')
            for value in (101, 101.5, 10**10000):
                self.assertEqual(safe.hash_file(root.path / 'a', deadline=value), hashlib.sha256(entries['a']).hexdigest())
            def late(): now[0] = 101
            self.failure(lambda: safe.hash_file(root.path / 'a', deadline=101, check_active=late), 'transport_deadline_exceeded')
        with patch.object(safe, 'time', SimpleNamespace(monotonic=lambda: self.fail('callback-only clock'))):
            self.assertEqual(set(archive.verify_checksum_inventory(root, check_active=lambda: None)), {'a'})

    def test_callback_errors_and_interrupts_are_sanitized(self):
        class CodeError(BaseException):
            def __init__(self, code): super().__init__('PRIVATE'); self.code = code
        class String(str): pass
        class Hostile(BaseException):
            @property
            def code(self): raise SystemExit('PRIVATE')
        errors = [(CodeError(code), expected) for code, expected in (
            ('cancelled', 'transport_cancelled'), ('timeout', 'transport_deadline_exceeded'),
            ('unknown', 'artifact_transport_failed'), ([], 'artifact_transport_failed'),
            (String('cancelled'), 'artifact_transport_failed'))]
        errors += [(Hostile('PRIVATE'), 'artifact_transport_failed'), (BaseException('PRIVATE'), 'artifact_transport_failed')]
        for error, code in errors:
            def callback(): raise error
            self.failure(lambda: safe.hash_file('/absent', check_active=callback), code, clean=True)
        for value in (False, 0, 'PRIVATE', object()):
            self.failure(lambda: safe.hash_file('/absent', check_active=lambda: value), 'artifact_transport_failed', clean=True)
        for kind, args in ((KeyboardInterrupt, ()), (SystemExit, (1,))):
            def callback(): raise kind('PRIVATE')
            with self.assertRaises(kind) as caught:
                safe.hash_file('/absent', check_active=callback)
            self.assertEqual(caught.exception.args, args)
            self.assertIsNone(caught.exception.__context__)
            self.assertIsNone(caught.exception.__cause__)

    def test_real_multichunk_hash_stops_on_cancel_or_expiry(self):
        root, entries = self.inventory_root()
        identity = root.fd
        for cancelled in (False, True):
            now, stopped = [100], [False]
            def hook(path, data, calls):
                if len(calls) == 2:
                    stopped[0], now[0] = True, 101
            def active():
                if cancelled and stopped[0]: raise safe.ConsumerError('cancelled')
            with self.reads(hook=hook) as (calls, streams), patch.object(safe, 'time', SimpleNamespace(monotonic=lambda: now[0])):
                self.failure(lambda: safe.hash_file(root.path / 'a', deadline=None if cancelled else 101,
                    check_active=active), 'transport_cancelled' if cancelled else 'transport_deadline_exceeded')
            self.assertEqual([row[2] for row in calls], [safe.CHUNK, safe.CHUNK])
            self.assertTrue(all(stream.closed for stream in streams))
            self.assertEqual(root.fd, identity)
            self.assertGreater(len(entries['a']), 3 * safe.CHUNK)

    def test_late_eof_and_close_cannot_return_digest(self):
        root, _ = self.inventory_root({'a': b'data'})
        for boundary in ('eof', 'close'):
            for cancelled in (False, True):
                stopped = [False]
                def hook(path, data, calls):
                    if boundary == 'eof' and not data: stopped[0] = True
                def closed(path):
                    if boundary == 'close': stopped[0] = True
                def active():
                    if cancelled and stopped[0]: raise safe.ConsumerError('cancelled')
                with self.reads(hook=hook, closed=closed) as (calls, streams), \
                     patch.object(safe, 'time', SimpleNamespace(monotonic=lambda: 101 if stopped[0] else 100)):
                    self.failure(lambda: safe.hash_file(root.path / 'a', deadline=None if cancelled else 101,
                        check_active=active), 'transport_cancelled' if cancelled else 'transport_deadline_exceeded')
                self.assertEqual([row[2] for row in calls], [4, 0])
                self.assertTrue(all(stream.closed for stream in streams))

    def test_inventory_rows_share_original_controls(self):
        root, entries = self.inventory_root()
        original, hashed, parsed = safe._check_budget, archive.hash_file, archive.re.fullmatch
        seen, rows, controls = [], [], []
        callback = lambda: None
        def check(deadline, active):
            seen.append((deadline, active)); return original(deadline, active)
        def hash_observed(path, **kwargs):
            controls.append(kwargs.copy()); return hashed(path, **kwargs)
        def parse(pattern, line, *args):
            if pattern == r'([0-9a-f]{64})  (.+)': rows.append((line, len(seen)))
            return parsed(pattern, line, *args)
        with patch.object(safe, '_check_budget', check), patch.object(archive, '_check_budget', check), \
             patch.object(archive, 'hash_file', hash_observed), patch.object(archive.re, 'fullmatch', parse):
            result = archive.verify_checksum_inventory(root, deadline=10**10000, check_active=callback)
        self.assertEqual(set(result), set(entries))
        self.assertEqual(len(rows), 2)
        self.assertLess(rows[0][1], rows[1][1])
        self.assertTrue(all(value == 10**10000 and active is callback for value, active in seen))
        self.assertEqual(controls, [dict(deadline=10**10000, check_active=callback)] * 2)
        for cancelled in (False, True):
            count = [0]
            def parse_stopped(pattern, line, *args):
                if pattern == r'([0-9a-f]{64})  (.+)': count[0] += 1
                return parsed(pattern, line, *args)
            def active():
                if cancelled and count[0]: raise safe.ConsumerError('cancelled')
            with patch.object(archive.re, 'fullmatch', parse_stopped), \
                 patch.object(safe, 'time', SimpleNamespace(monotonic=lambda: 101 if count[0] else 100)), \
                 patch.object(archive, 'hash_file', side_effect=AssertionError('hash after row stop')):
                self.failure(lambda: archive.verify_checksum_inventory(root, deadline=None if cancelled else 101,
                    check_active=active), 'transport_cancelled' if cancelled else 'transport_deadline_exceeded')
            self.assertEqual(count[0], 1)

    def test_checksum_errors_and_root_ownership_are_preserved(self):
        digest = hashlib.sha256(b'payload').hexdigest()
        for text, code in (('invalid\n', 'invalid_checksum_inventory'),
                (digest + '  absent\n', 'checksum_coverage'), ('0' * 64 + '  a\n', 'checksum_mismatch')):
            for controls in ({}, {'check_active': lambda: None}):
                root, _ = self.inventory_root({'a': b'payload'}, text)
                fd = root.fd
                self.failure(lambda: archive.verify_checksum_inventory(root, **controls), code)
                self.assertEqual(root.fd, fd)
                self.assertEqual(root.files(), ('SHA256SUMS.txt', 'a'))
        root, _ = self.inventory_root({'a': b'payload'})
        with patch.object(safe, 'FILE_LIMIT', 1):
            self.failure(lambda: safe.hash_file(root.path / 'a', check_active=lambda: None), 'file_size_limit')
        def bad_read(*_): raise OSError('PRIVATE')
        with self.reads(hook=bad_read):
            self.failure(lambda: safe.hash_file(root.path / 'a', check_active=lambda: None), 'unsafe_file_io')
        opened = safe.open_file
        @contextmanager
        def bad_close(path):
            with opened(path) as stream: yield stream
            raise safe.ConsumerError('unsafe_file_io')
        with patch.object(safe, 'open_file', bad_close):
            self.failure(lambda: safe.hash_file(root.path / 'a', check_active=lambda: None), 'unsafe_file_io')
        for boundary in ('read', 'close'):
            for cancelled in (False, True):
                stopped, polls, failed_at = [False], [0], []
                def active():
                    polls[0] += 1
                    if stopped[0]: raise safe.ConsumerError('cancelled')
                def failed_io(*_):
                    stopped[0] = True
                    failed_at.append(polls[0])
                    raise OSError('PRIVATE')
                @contextmanager
                def closing(path):
                    with opened(path) as stream:
                        yield stream
                        stream.close()
                        failed_io()
                fault = self.reads(hook=failed_io) if boundary == 'read' else patch.object(safe, 'open_file', closing)
                with fault, patch.object(safe, 'time', SimpleNamespace(monotonic=lambda: 101 if stopped[0] else 100)):
                    self.failure(lambda: safe.hash_file(root.path / 'a', deadline=None if cancelled else 101,
                        check_active=active), 'unsafe_file_io')
                self.assertEqual(failed_at, [polls[0]])  # No poll after established I/O failure.

    def test_two_downloads_share_controls_through_real_checksum(self):
        with self.padded_session() as (session, _, fixture, seen):
            verify, hashed = archive.verify_checksum_inventory, archive.hash_file
            controls, hashes, entered, in_inventory = [], [], [], [False]
            def checked(root, **kwargs):
                self.children_exited(seen, 2)
                controls.append(kwargs.copy()); entered.append(time.monotonic())
                in_inventory[0] = True
                try:
                    return verify(root, **kwargs)
                finally:
                    in_inventory[0] = False
            def hash_observed(path, **kwargs):
                if in_inventory[0]: hashes.append(kwargs.copy())
                return hashed(path, **kwargs)
            with patch.object(archive, 'verify_checksum_inventory', checked), patch.object(archive, 'hash_file', hash_observed):
                session.run_until_pause()
            self.assertEqual([ident for ident, _ in seen.downloads], [14, 13])
            self.assertEqual(len(controls), 1)
            first = seen.downloads[0][1]
            self.assertEqual(controls[0]['deadline'], seen.auth[0]['deadline'])
            self.assertIs(controls[0]['check_active'], first['check_active'])
            self.assertTrue(hashes and all(row['deadline'] == controls[0]['deadline']
                and row['check_active'] is controls[0]['check_active'] for row in hashes))
            self.assertLess(controls[0]['deadline'] - entered[0], 30)
            self.assertGreater(controls[0]['deadline'] - entered[0], 0)
            handles = self.bindings(seen.stage, fixture)
            self.children_exited(seen, 2)
            session.close()
            self.assertTrue(all(handle.closed for handle in handles))

    def checksum_failure(self, cancelled, boundary='chunk', **faults):
        with self.padded_session(**faults) as (session, tls, _, seen):
            stopped, calls = [False], []
            def now(): return session._deadline if stopped[0] and not cancelled else time.monotonic()
            def stop():
                self.children_exited(seen, 2)
                stopped[0] = True
                if cancelled: session.cancel()
            def selected(path):
                return seen.stage is not None and path == seen.stage._roots[3].path / 'packaging-report.json'
            def read(path, data, observed):
                if (boundary == 'chunk' and len(observed) == 2) or (boundary == 'eof' and not data): stop()
            verify = archive.verify_checksum_inventory
            def entered(root, **kwargs):
                if boundary == 'entry': stop()
                return verify(root, **kwargs)
            sticky = bool(faults)
            code = 'adapter_error' if sticky else 'cancelled' if cancelled else 'timeout'
            with patch.object(safe, 'time', SimpleNamespace(monotonic=now), create=True), \
                 patch.object(executor, 'time', SimpleNamespace(monotonic=now)), \
                 self.reads(select=selected, hook=read) as (calls, streams), \
                 patch.object(archive, 'verify_checksum_inventory', entered), \
                 patch.object(archive, 'extract_bounded_cloud_tar', wraps=archive.extract_bounded_cloud_tar) as cloud:
                self.failed_run(session, code)
            self.assertTrue(stopped[0])
            cloud.assert_not_called()
            self.assertEqual(len(calls), 0 if boundary == 'entry' else 2 if boundary == 'chunk' else 6)
            if boundary == 'chunk': self.assertEqual([row[2] for row in calls], [safe.CHUNK] * 2)
            if boundary == 'eof': self.assertEqual(calls[-1][2], 0)
            self.assertTrue(all(stream.closed for stream in streams))
            self.activation_failed(session, tls, seen, code, 2, sticky=sticky)

    def test_checksum_cancellation_reaps_both_children(self):
        for boundary in ('chunk', 'eof'):
            with self.subTest(boundary=boundary): self.checksum_failure(True, boundary)

    def test_checksum_timeout_reaps_both_children(self):
        for boundary in ('entry', 'chunk', 'eof'):
            with self.subTest(boundary=boundary): self.checksum_failure(False, boundary)

    def test_checksum_cleanup_failures_remain_sticky(self):
        for cancelled in (False, True):
            for fault in ('root_failure', 'api_failure'):
                with self.subTest(cancelled=cancelled, fault=fault):
                    self.checksum_failure(cancelled, **{fault: True})


if __name__ == '__main__':
    unittest.main()
