"""Hermetic transport tests; example.invalid is never contacted."""
from email.message import Message
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


class Response:
    def __init__(self, code, body=b'', headers=()):
        self.code = code
        self.body = io.BytesIO(body)
        self.headers = Message()
        for key, value in headers:
            self.headers[key] = value
        self.closed = False

    def read1(self, size):
        return self.body.read(size)

    def close(self):
        self.closed = True


class Opener:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


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
        response.read1 = lambda _: (_ for _ in ()).throw(TimeoutError(URL))
        with self.assertRaisesRegex(ConsumerError, '^artifact_transport_failed$'):
            self.run_download(Opener(self.redirect(), response))

    def test_default_opener_rejects_redirects(self):
        handler = transport.NoRedirect()
        self.assertIsNone(handler.redirect_request(None, None, 302, '', Message(), URL))


if __name__ == '__main__':
    unittest.main()
