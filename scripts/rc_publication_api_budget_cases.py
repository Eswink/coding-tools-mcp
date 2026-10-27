"""Stage API controls over synthetic metadata and real loopback TLS; no authority."""
import json
import ssl
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from rc_consumer_git_test_support import Cancelled
import rc_consumer_io as safe
import rc_publication_github as wire
import rc_publication_stage as stage
from rc_publication_https_fixture import HTTPSFixture
from rc_publication_stage_cases import publisher_fixture


class TrickleTLS(HTTPSFixture):
    """Same verified loopback TLS ownership, with a slow header or body."""
    def __init__(self):
        super().__init__()
        self.mode = 'header'
        self.connected = False

    def _handle(self, raw):
        try:
            with self.context.wrap_socket(raw, server_side=True) as sock:
                sock.settimeout(2)
                data = bytearray()
                while b'\r\n\r\n' not in data:
                    block = sock.recv(1)
                    if not block or len(data) > 65536:
                        return
                    data.extend(block)
                lines = bytes(data).split(b'\r\n\r\n', 1)[0].decode('ascii').split('\r\n')
                method, path, _ = lines[0].split(' ')
                headers = dict((k.lower(), v.strip()) for k, v in
                               (line.split(':', 1) for line in lines[1:]))
                self.requests.append((method, path, headers, b''))
                self.connected = True
                body = json.dumps({'padding': 'x' * 2048}).encode()
                header = ('HTTP/1.1 200 Fixture\r\nContent-Length: ' + str(len(body)) + '\r\n\r\n').encode()
                if self.mode == 'header':
                    for byte in header:
                        sock.sendall(bytes([byte]))
                        time.sleep(0.012)
                    sock.sendall(body)
                else:
                    sock.sendall(header)
                    for offset in range(0, len(body), 128):
                        sock.sendall(body[offset:offset + 128])
                        time.sleep(0.025)
        except (OSError, ValueError, ssl.SSLError):
            pass
        except BaseException as error:
            self.errors.append(type(error).__name__)
        finally:
            raw.close()


class APIBudgetCases(unittest.TestCase):
    def failure(self, action, code):
        with self.assertRaises(safe.ConsumerError) as result:
            stage.snapshot._call(action)
        self.assertEqual(result.exception.code, code)
        return result.exception

    def test_default_observation_keeps_empty_api_kwargs_and_no_new_clock(self):
        with publisher_fixture() as fixture:
            rows, get = [], fixture.api.get
            def observed(path, **kwargs):
                rows.append((path, kwargs))
                return get(path)
            timer = SimpleNamespace(monotonic=lambda: self.fail('default operation clock'))
            with patch.object(fixture.api, 'get', observed), patch.object(safe, 'time', timer), \
                 patch.object(stage, '_APIReads', side_effect=AssertionError('default wrapper')):
                value = stage._observe(fixture.root, fixture.selection, fixture.api)
            self.assertEqual(len(value), 4)
            self.assertTrue(rows)
            self.assertTrue(all(not kwargs for _, kwargs in rows))

    def test_all_source_and_observation_metadata_reads_keep_original_deadline(self):
        with publisher_fixture() as fixture:
            expected = stage._observe(fixture.root, fixture.selection, fixture.api)
            polls, rows, get = [], [], fixture.api.get
            callback = lambda: polls.append(True) and None
            deadline = time.monotonic() + 60
            def observed(path, **kwargs):
                rows.append((path, kwargs.copy()))
                return get(path, **kwargs)
            with patch.object(fixture.api, 'get', observed):
                actual = stage._observe(fixture.root, fixture.selection, fixture.api,
                                        deadline=deadline, check_active=callback)
            self.assertEqual(actual, expected)
            self.assertEqual(sum('/git/ref/tags/' in path for path, _ in rows), 2)
            self.assertEqual(rows[-1][0], '/actions/artifacts/14')
            self.assertTrue(all(kwargs['deadline'] is deadline and callable(kwargs['check_active'])
                                for _, kwargs in rows))
            self.assertTrue(polls)

    def test_invalid_or_expired_controls_prevent_api_calls(self):
        for value, code in ((True, 'invalid_transport_deadline'), (float('nan'), 'invalid_transport_deadline'),
                            (float('inf'), 'invalid_transport_deadline'), (0, 'transport_deadline_exceeded')):
            api = SimpleNamespace(get=lambda *args, **kwargs: self.fail('API called'))
            self.failure(lambda: stage._APIReads(api, value, None).get('/fixture'), code)

    def test_only_exact_no_effect_wire_interruptions_are_promoted(self):
        for code, effect in (('timeout', 'none'), ('cancelled', 'none'), ('verification_failed', 'none'),
                            ('timeout', 'unknown'), ('cancelled', 'confirmed')):
            observed = []
            def failed(*args, **kwargs):
                error = wire.WireFailure(code, effect)
                observed.append(error)
                raise error
            api = SimpleNamespace(get=failed)
            expected = {'timeout': 'transport_deadline_exceeded', 'cancelled': 'transport_cancelled'}[code] \
                if effect == 'none' and code in ('timeout', 'cancelled') else 'invalid_snapshot'
            with self.subTest(code=code, effect=effect):
                if effect == 'none':
                    self.failure(lambda: stage._APIReads(api, time.monotonic() + 60, None).get('/fixture'), expected)
                else:
                    with self.assertRaises(wire.WireFailure) as caught:
                        stage._APIReads(api, time.monotonic() + 60, None).get('/fixture')
                    self.assertEqual(len(observed), 1)
                    self.assertIs(caught.exception, observed[0])
                    self.assertEqual((caught.exception.code, caught.exception.effect,
                        caught.exception.release_id, caught.exception.asset), (code, effect, None, None))

    def test_callback_bridge_does_not_override_unknown_wire_effect(self):
        stopped, observed = [], []
        def active():
            if stopped:
                raise Cancelled()
        def failed(path, **kwargs):
            stopped.append(True)
            try:
                kwargs['check_active']()
            except wire.WireFailure:
                error = wire.WireFailure('cancelled', 'unknown')
                observed.append(error)
                raise error from None
        reads = stage._APIReads(SimpleNamespace(get=failed), time.monotonic() + 60, active)
        with self.assertRaises(wire.WireFailure) as caught:
            reads.get('/fixture')
        self.assertEqual(stopped, [True])
        self.assertEqual(len(observed), 1)
        self.assertIs(caught.exception, observed[0])
        self.assertEqual((caught.exception.code, caught.exception.effect,
            caught.exception.release_id, caught.exception.asset), ('cancelled', 'unknown', None, None))

    def test_full_pagination_uses_one_original_deadline(self):
        rows, clock = [], [100.0]
        def get(path, **kwargs):
            rows.append((path, kwargs.copy()))
            clock[0] += 0.4
            page = 1 if path.endswith('page=1') else 2
            values = [{'id': i} for i in range(1, 101)] if page == 1 else [{'id': 101}]
            return {'total_count': 101, 'jobs': values}
        deadline = 101.0
        reads = stage._APIReads(SimpleNamespace(get=get), deadline, None)
        with patch.object(safe, 'time', SimpleNamespace(monotonic=lambda: clock[0])):
            values = stage.snapshot.gate.paginate(reads, '/actions/runs/1/jobs', 'jobs')
            safe._check_budget(deadline, None)
        self.assertEqual([row['id'] for row in values], list(range(1, 102)))
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(options['deadline'] is deadline for _, options in rows))

    def test_pagination_deadline_stops_before_next_page_without_partial_success(self):
        rows, clock = [], [100.0]
        def get(path, **kwargs):
            rows.append(path)
            clock[0] = 102.0
            return {'total_count': 101, 'jobs': [{'id': i} for i in range(1, 101)]}
        reads = stage._APIReads(SimpleNamespace(get=get), 101.0, None)
        with patch.object(safe, 'time', SimpleNamespace(monotonic=lambda: clock[0])):
            self.failure(lambda: stage.snapshot.gate.paginate(reads, '/actions/runs/1/jobs', 'jobs'),
                         'transport_deadline_exceeded')
        self.assertEqual(len(rows), 1)

    def test_returned_bad_tag_precedes_late_cancellation(self):
        with publisher_fixture() as fixture:
            stopped, get = [], fixture.api.get
            def observed(path, **kwargs):
                value = get(path, **kwargs)
                if path.startswith('/git/ref/tags/'):
                    stopped.append(True)
                    value['object']['sha'] = '0' * 40
                return value
            def active():
                if stopped:
                    raise Cancelled()
            with patch.object(fixture.api, 'get', observed):
                self.failure(lambda: stage._source(fixture.root, fixture.selection.subject,
                    fixture.api, check_active=active), 'lightweight_tag_required')

    def test_source_success_checks_after_second_tag_read(self):
        for cancelled in (False, True):
            with self.subTest(cancelled=cancelled), publisher_fixture() as fixture:
                tags, get, deadline = [], fixture.api.get, time.monotonic() + 60
                def observed(path, **kwargs):
                    value = get(path, **kwargs)
                    if path.startswith('/git/ref/tags/'):
                        tags.append(path)
                    return value
                def active():
                    if len(tags) == 2 and cancelled:
                        raise Cancelled()
                timer = SimpleNamespace(monotonic=lambda: deadline + 1 if len(tags) == 2 else deadline - 1)
                with patch.object(fixture.api, 'get', observed), patch.object(safe, 'time', timer):
                    self.failure(lambda: stage._source(fixture.root, fixture.selection.subject, fixture.api,
                        deadline=None if cancelled else deadline, check_active=active),
                        'transport_cancelled' if cancelled else 'transport_deadline_exceeded')
                self.assertEqual(len(tags), 2)

    def test_last_receipt_semantic_failure_precedes_late_cancellation(self):
        with publisher_fixture() as fixture:
            stopped, get = [], fixture.api.get
            fixture.api.data['/actions/artifacts/14']['workflow_run']['repository_id'] = 1
            def observed(path, **kwargs):
                value = get(path, **kwargs)
                if path == '/actions/artifacts/14':
                    stopped.append(True)
                return value
            def active():
                if stopped:
                    raise Cancelled()
            with patch.object(fixture.api, 'get', observed):
                self.failure(lambda: stage._observe(fixture.root, fixture.selection, fixture.api,
                    check_active=active), 'receipt_owner_mismatch')

    def test_observation_success_checks_after_receipt_semantics(self):
        for cancelled in (False, True):
            with self.subTest(cancelled=cancelled), publisher_fixture() as fixture:
                stopped, get, deadline = [], fixture.api.get, time.monotonic() + 60
                def observed(path, **kwargs):
                    value = get(path, **kwargs)
                    if path == '/actions/artifacts/14':
                        stopped.append(True)
                    return value
                def active():
                    if stopped and cancelled:
                        raise Cancelled()
                timer = SimpleNamespace(monotonic=lambda: deadline + 1 if stopped else deadline - 1)
                with patch.object(fixture.api, 'get', observed), patch.object(safe, 'time', timer):
                    self.failure(lambda: stage._observe(fixture.root, fixture.selection, fixture.api,
                        deadline=None if cancelled else deadline, check_active=active),
                        'transport_cancelled' if cancelled else 'transport_deadline_exceeded')
                self.assertEqual(stopped, [True])

    def tls_read(self, mode, *, interrupted=None):
        with TrickleTLS() as tls:
            tls.mode = mode
            api = wire.GitHub('fixture-token', tls.selection)
            started, readers, received = time.monotonic(), [], []
            initialize, take = wire._Reader.__init__, wire._Reader.take
            def initialized(reader, *args):
                initialize(reader, *args)
                readers.append(reader)
            def observed(reader, size):
                value = take(reader, size)
                received.append(len(value))
                return value
            def progress():
                return bool(received) if mode == 'header' else any(reader.buffer for reader in readers)
            def active():
                if tls.connected and progress() and interrupted is not None:
                    if interrupted == 'return':
                        return 1
                    raise interrupted('private-raw-reason')
            deadline = started + (0.15 if interrupted is None else 3)
            with patch.object(wire, '_connect', side_effect=tls.connect), \
                 patch.object(wire._Reader, '__init__', initialized), patch.object(wire._Reader, 'take', observed):
                if interrupted in (KeyboardInterrupt, SystemExit):
                    with self.assertRaises(interrupted) as result:
                        stage._APIReads(api, deadline, active).get('/fixture')
                    self.assertEqual(result.exception.args, () if interrupted is KeyboardInterrupt else (1,))
                else:
                    code = ('transport_deadline_exceeded' if interrupted is None else
                            'artifact_transport_failed' if interrupted in ('return', RuntimeError) else 'transport_cancelled')
                    self.failure(lambda: stage._APIReads(api, deadline, active).get('/fixture'), code)
            elapsed = time.monotonic() - started
            self.assertLess(elapsed, 1)
            self.assertEqual(len(tls.requests), 1)
            self.assertEqual(tls.errors, [])
            self.assertEqual(tls.requests[0][0], 'GET')
            self.assertEqual(tls.requests[0][3], b'')
            self.assertTrue(progress())
            print('STAGE_API_TLS ' + json.dumps(dict(mode=mode, elapsed_seconds=elapsed,
                interruption='deadline' if interrupted is None else str(interrupted), scope='loopback-only',
                completed_take_bytes=sum(received), partial_body_bytes=sum(len(reader.buffer) for reader in readers))), flush=True)

    def test_real_tls_trickle_headers_use_original_deadline(self):
        self.tls_read('header')

    def test_real_tls_trickle_body_uses_original_deadline(self):
        self.tls_read('body')

    def test_real_tls_generic_cancellation_is_not_invalid_snapshot(self):
        for mode in ('header', 'body'):
            with self.subTest(mode=mode):
                self.tls_read(mode, interrupted=Cancelled)

    def test_real_tls_callback_failures_preserve_optional_control_contract(self):
        for reason in ('return', RuntimeError):
            with self.subTest(reason=reason):
                self.tls_read('body', interrupted=reason)

    def test_real_tls_interrupt_types_have_sanitized_arguments(self):
        for reason in (KeyboardInterrupt, SystemExit):
            with self.subTest(reason=reason):
                self.tls_read('header', interrupted=reason)


if __name__ == '__main__':
    unittest.main()
