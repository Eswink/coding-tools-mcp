"""Hermetic transport tests; example.invalid is never contacted."""
import base64
from email.message import Message
import json
import os
import subprocess
import sys
import weakref
import hashlib
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import urllib.error

from rc_consumer_io import ConsumerError, PrivateRoot
import rc_consumer_transport as transport

HOST = 'fixture.example.invalid'
URL = 'https://' + HOST + '/data?signature=PRIVATE'
# Isolate fixture disposal from finalization tests' production os.unlink spies.
_FIXTURE_UNLINK, _FIXTURE_RMDIR = os.unlink, os.rmdir


def _remove_fixture(directory):
    for name in ('fixture.json', 'observed.json', 'observed.pending'):
        try:
            _FIXTURE_UNLINK(directory / name)
        except FileNotFoundError:
            pass
    _FIXTURE_RMDIR(directory)


class Response:
    def __init__(self, code, body=b'', headers=()):
        self.code = code
        self.body = io.BytesIO(body)
        self.headers = Message()
        for key, value in headers:
            self.headers[key] = value
        self._closed = False
        self._observer = None
        self.failure = None

    def read1(self, size):
        return self.body.read(size)

    @property
    def closed(self):
        observer = self._observer() if self._observer else None
        return self._closed or bool(observer and self._index in observer.observations().get('closed', []))

    def close(self):
        self._closed = True


class Opener:
    """Inert child fixture; telemetry is separate from the production byte IPC."""
    def __init__(self, *responses, mode='responses', port=None):
        self.responses = list(responses)
        self.mode, self.port = mode, port
        self.directory = Path(tempfile.mkdtemp(prefix='transport-fixture-'))
        self._remove = weakref.finalize(self, _remove_fixture, self.directory)
        self.process = None
        for index, response in enumerate(self.responses):
            if isinstance(response, Response):
                response._observer, response._index = weakref.ref(self), index

    def __del__(self):
        process = getattr(self, 'process', None)
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=1)
        if hasattr(self, '_remove'):
            self._remove()

    def observations(self):
        path = self.directory / 'observed.json'
        if not path.exists():
            return {}
        with path.open('rb') as stream:
            raw = stream.read(131073)
        assert len(raw) <= 131072
        return json.loads(raw)

    @property
    def requests(self):
        import urllib.request
        return [(urllib.request.Request(row['url'], headers=dict(row['headers']),
                    method=row['method']), row['timeout'])
                for row in self.observations().get('requests', [])]

    def start_worker(self):
        rows = []
        for response in self.responses:
            if isinstance(response, urllib.error.HTTPError):
                rows.append(dict(code=response.code, headers=list(response.headers.items()),
                                 http_error=True, body=''))
            elif isinstance(response, Response):
                rows.append(dict(code=response.code, headers=list(response.headers.items()),
                    body=base64.b64encode(response.body.getvalue()).decode(), failure=response.failure))
            else:
                rows.append(dict(failure='open'))
        raw = json.dumps(dict(responses=rows, mode=self.mode, port=self.port)).encode()
        assert len(raw) <= 8 * 1024**2
        config = self.directory / 'fixture.json'
        config.write_bytes(raw)
        self.process = subprocess.Popen([sys.executable, '-B', '-I', '-S',
            str(Path(__file__).with_name('rc_consumer_transport_supervisor_tests.py')),
            '--worker-fixture', str(config)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, shell=False, close_fds=True, bufsize=0,
            env={'LC_ALL': 'C', 'LANG': 'C'})
        return self.process


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = PrivateRoot(self.temp.name, source_root=Path('/not-the-fixture'))
        self.addCleanup(self.root.close)
        self.data = b'authenticated synthetic archive bytes'
        self.artifact = dict(id=42, size_in_bytes=len(self.data),
                             digest='sha256:' + hashlib.sha256(self.data).hexdigest())
        self.api = SimpleNamespace(token='TOKEN-MUST-NOT-LEAVE-API')
        self.hosts = patch.object(transport, 'TRUSTED_STORAGE_HOSTS', frozenset({HOST}))
        self.hosts.start()
        self.addCleanup(self.hosts.stop)

    def run_download(self, opener, **kwargs):
        return transport.download_artifact_zip(self.api, self.artifact, self.root,
                                               opener=opener, **kwargs)

    def redirect(self, url=URL, code=302):
        return Response(code, headers=[('Location', url)])

    def test_authenticated_two_request_download(self):
        first = self.redirect()
        second = Response(200, self.data, [('Content-Length', str(len(self.data)))])
        opener = Opener(first, second)
        path = self.run_download(opener)
        self.assertEqual(path.read_bytes(), self.data)
        self.assertTrue(first.closed and second.closed)
        api, storage = [r for r, _ in opener.requests]
        self.assertEqual(api.full_url, transport.API + '/repos/Eswink/coding-tools-mcp/actions/artifacts/42/zip')
        self.assertEqual(api.get_header('Authorization'), 'Bearer ' + self.api.token)
        self.assertEqual(storage.full_url, URL)
        self.assertEqual(storage.header_items(), [('Accept', 'application/zip')])
        self.assertEqual([r.get_method() for r, _ in opener.requests], ['GET', 'GET'])
        self.assertTrue(all(0 < timeout <= transport.READ_TIMEOUT for _, timeout in opener.requests))

    def test_empty_production_host_contract_blocks_before_network(self):
        opener = Opener()
        with patch.object(transport, 'TRUSTED_STORAGE_HOSTS', frozenset()):
            with self.assertRaisesRegex(ConsumerError, '^storage_transport_unverified$'):
                self.run_download(opener)
        self.assertFalse(opener.requests)

    def test_redirect_destinations_fail_closed(self):
        urls = ['http://' + HOST + '/a', 'https://evil.invalid/a', 'https://127.0.0.1/a',
                'https://[::1]/a', 'https://u:p@' + HOST + '/a', 'https://' + HOST + ':444/a',
                'https://' + HOST + '/a#x', 'https://' + HOST + './a', 'https://é.invalid/a',
                'https://' + HOST + '\n/a', 'https://bad..host/a', 'https://' + HOST]
        for url in urls:
            with self.subTest(url=url):
                opener = Opener(self.redirect(url))
                with self.assertRaises(ConsumerError):
                    self.run_download(opener)
                self.assertEqual(len(opener.requests), 1)
                self.assertEqual(self.root.files(), ())

    def test_duplicate_or_missing_location_and_other_status(self):
        responses = [Response(302), Response(302, headers=[('Location', URL), ('Location', URL)]),
                     self.redirect(code=301), self.redirect(code=307), Response(200, self.data)]
        for response in responses:
            with self.subTest(status=response.code, headers=len(response.headers)):
                opener = Opener(response)
                with self.assertRaises(ConsumerError):
                    self.run_download(opener)
                self.assertEqual(len(opener.requests), 1)

    def test_http_error_302_is_expected_without_body_read(self):
        error = urllib.error.HTTPError('https://api.github.com/fixed', 302, 'Found',
                                      self.redirect().headers, io.BytesIO(b'NEVER-READ'))
        opener = Opener(error, Response(200, self.data))
        self.assertEqual(self.run_download(opener).read_bytes(), self.data)

    def test_second_redirect_and_raw_exception_are_sanitized(self):
        for response in (self.redirect('https://attacker.invalid/path?SECRET'),
                         urllib.error.HTTPError(URL, 302, 'SECRET', Message(), io.BytesIO())):
            with self.subTest(type=type(response).__name__):
                with self.assertRaises(ConsumerError) as caught:
                    self.run_download(Opener(self.redirect(), response))
                self.assertNotIn('PRIVATE', str(caught.exception))
                self.assertNotIn('SECRET', str(caught.exception))
                self.assertNotIn(HOST, str(caught.exception))

    def test_wrong_digest_fails(self):
        self.artifact['digest'] = 'sha256:' + '0' * 64
        with self.assertRaisesRegex(ConsumerError, 'download_digest_mismatch'):
            self.run_download(Opener(self.redirect(), Response(200, self.data)))

    def test_truncated_oversized_and_changed_length_fail(self):
        for body, headers in [(self.data[:-1], []), (self.data + b'x', []),
                              (self.data, [('Content-Length', '1')]),
                              (self.data, [('Content-Length', str(len(self.data))), ('Content-Length', '1')]),
                              (self.data, [('Content-Encoding', 'gzip')])]:
            with self.subTest(length=len(body), headers=headers):
                with PrivateRoot(self.temp.name, source_root=Path('/source')) as root:
                    with self.assertRaises(ConsumerError):
                        transport.download_artifact_zip(self.api, self.artifact, root,
                            opener=Opener(self.redirect(), Response(200, body, headers)))

    def test_metadata_types_are_not_coerced(self):
        for key, value in [('id', True), ('id', 1.0), ('size_in_bytes', False),
                           ('size_in_bytes', 1.0), ('size_in_bytes', transport.MAX_ZIP + 1),
                           ('digest', None), ('digest', 'sha256:' + 'A' * 64)]:
            with self.subTest(key=key, value=value):
                artifact = dict(self.artifact, **{key: value})
                opener = Opener()
                with self.assertRaises(ConsumerError):
                    transport.download_artifact_zip(self.api, artifact, self.root, opener=opener)
                self.assertFalse(opener.requests)

    def test_total_deadline_checked_during_streaming(self):
        times = iter([0, 0, 0, transport.TOTAL_TIMEOUT + 1])
        with self.assertRaisesRegex(ConsumerError, 'transport_deadline_exceeded'):
            self.run_download(Opener(self.redirect(), Response(200, self.data)), clock=lambda: next(times))

    def test_stream_error_has_fixed_code(self):
        response = Response(200)
        response.failure = 'read'
        with self.assertRaisesRegex(ConsumerError, '^artifact_transport_failed$'):
            self.run_download(Opener(self.redirect(), response))

    def test_default_opener_rejects_redirects(self):
        handler = transport.NoRedirect()
        self.assertIsNone(handler.redirect_request(None, None, 302, '', Message(), URL))


class CompiledStoragePolicyTests(unittest.TestCase):
    """Unpatched source defaults; fake responses do not establish live TLS."""
    def test_compiled_defaults_are_exact_reviewed_singleton(self):
        expected = frozenset({'productionresultssa5.blob.core.windows.net'})
        self.assertEqual(transport.TRUSTED_STORAGE_HOSTS, expected)
        self.assertEqual(transport.wire.TRUSTED_STORAGE_HOSTS, expected)
        self.assertIs(type(transport.TRUSTED_STORAGE_HOSTS), frozenset)
        self.assertIs(type(transport.wire.TRUSTED_STORAGE_HOSTS), frozenset)

    def test_both_defaults_accept_only_reviewed_host_urls(self):
        for authority in ('productionresultssa5.blob.core.windows.net',
                          'productionresultssa5.blob.core.windows.net:443'):
            with self.subTest(authority=authority):
                url = 'https://' + authority + '/data?signature=SYNTHETIC'
                self.assertEqual(transport.storage_url(url), url)
                self.assertEqual(transport.wire.storage_url(
                    url, transport.wire.TRUSTED_STORAGE_HOSTS), url)

    def test_both_defaults_reject_adversarial_destinations(self):
        host = 'productionresultssa5.blob.core.windows.net'
        urls = ['https://productionresultssa50.blob.core.windows.net/a',
                'https://productionresultssa5.blob.core.windows.net.evil.invalid/a',
                'https://sub.' + host + '/a', 'https://other.blob.core.windows.net/a',
                'https://productionresultssа5.blob.core.windows.net/a',
                'https://127.0.0.1/a', 'https://[::1]/a',
                'https://u:p@' + host + '/a', 'https://' + host + '@evil.invalid/a',
                'https://' + host + ':444/a', 'https://' + host + '/a#fragment',
                'http://' + host + '/a', 'https://' + host + './a']
        for url in urls:
            with self.subTest(url=url):
                with self.assertRaises(ConsumerError):
                    transport.storage_url(url)
                with self.assertRaises(transport.wire.WireError):
                    transport.wire.storage_url(url, transport.wire.TRUSTED_STORAGE_HOSTS)

    def test_default_worker_synthetic_two_hop_preserves_headers_and_closes(self):
        url = 'https://productionresultssa5.blob.core.windows.net/data?signature=SYNTHETIC'
        first = Response(302, headers=[('Location', url)])
        second = Response(200, b'fixture', [('Content-Length', '7')])
        responses, requests, frames = iter((first, second)), [], []
        opener = SimpleNamespace(open=lambda request, timeout:
            (requests.append((request, timeout)), next(responses))[1])
        transport.wire.download(dict(id=42, size=7, token='SYNTHETIC-API-ONLY'),
                                frames.append, opener=opener)
        self.assertEqual(frames, [b'Bfixture', b'D'])
        self.assertTrue(first.closed and second.closed)
        self.assertEqual(len(requests), 2)
        api, storage = [request for request, _ in requests]
        self.assertEqual(api.full_url, transport.API +
                         '/repos/Eswink/coding-tools-mcp/actions/artifacts/42/zip')
        self.assertEqual(api.get_header('Authorization'), 'Bearer SYNTHETIC-API-ONLY')
        self.assertEqual(storage.full_url, url)
        self.assertEqual(storage.header_items(), [('Accept', 'application/zip')])
        self.assertEqual([request.get_method() for request, _ in requests], ['GET', 'GET'])

    def test_default_worker_rejects_untrusted_host_before_storage_request(self):
        for host in ('productionresultssa50.blob.core.windows.net',
                     'productionresultssa5.blob.core.windows.net.evil.invalid',
                     'sub.productionresultssa5.blob.core.windows.net'):
            with self.subTest(host=host):
                first = Response(302, headers=[('Location', 'https://' + host + '/data')])
                requests, frames = [], []
                opener = SimpleNamespace(open=lambda request, timeout:
                    (requests.append(request), first)[1])
                with self.assertRaisesRegex(transport.wire.WireError, '^unverified_storage_host$'):
                    transport.wire.download(dict(id=42, size=7, token='SYNTHETIC'),
                                            frames.append, opener=opener)
                self.assertEqual(len(requests), 1)
                self.assertEqual(frames, [])
                self.assertTrue(first.closed)

    def test_default_worker_rejects_second_redirect_without_done(self):
        url = 'https://productionresultssa5.blob.core.windows.net/data?signature=SYNTHETIC'
        for destination in (url, 'https://evil.invalid/data'):
            with self.subTest(destination=destination):
                first = Response(302, headers=[('Location', url)])
                second = Response(302, headers=[('Location', destination)])
                responses, requests, frames = iter((first, second)), [], []
                opener = SimpleNamespace(open=lambda request, timeout:
                    (requests.append(request), next(responses))[1])
                with self.assertRaisesRegex(transport.wire.WireError, '^unexpected_storage_status$'):
                    transport.wire.download(dict(id=42, size=7, token='SYNTHETIC'),
                                            frames.append, opener=opener)
                self.assertEqual(len(requests), 2)
                self.assertEqual(frames, [])
                self.assertTrue(first.closed and second.closed)


if __name__ == '__main__':
    unittest.main()
