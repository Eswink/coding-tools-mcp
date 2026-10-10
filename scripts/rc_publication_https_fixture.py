"""Verified loopback TLS only; these fixtures grant no production authority."""
from contextlib import ExitStack, contextmanager
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import socket
import ssl
import subprocess
import tempfile
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import rc_publication_contract as core
import rc_publication_github as wire
from rc_pretag_publication_contract_tests import fixture as contract_fixture

STABLE = {'id': 50, 'tag_name': 'v0.5.0', 'target_commitish': 'main', 'draft': False,
          'prerelease': False, 'published_at': '2026-01-01T00:00:00Z'}
STABLE_TAG = {'type': 'commit', 'sha': '5' * 40}


def stable_identity(latest=True):
    projection = dict(STABLE, tag_ref=STABLE_TAG)
    value = {'stable': projection, 'latest': projection if latest else None}
    return (50, 50 if latest else 0, hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(',', ':')).encode()).hexdigest())


def gates(selection, *args, **kwargs):
    return tuple((*row, 'passed') for row in core._admission(selection.subject)), 'proven'


@contextmanager
def authorities():
    with ExitStack() as stack:
        stack.enter_context(patch.object(wire, '_authenticate', side_effect=gates))
        stack.enter_context(patch.object(wire, '_remote_constraint', return_value=None))
        stack.enter_context(patch.object(wire, '_authorize', return_value=None))
        yield


class HTTPSFixture:
    def __init__(self, subject=None, plan=None, payloads=None):
        original, original_plan = contract_fixture()
        self.payloads = payloads or {a.name: (f'payload-{i}-'.encode() * (i + 1))
                                    for i, a in enumerate(original_plan.assets)}
        self.plan = plan or core.AssetPlanView(tuple(replace(a, size=len(self.payloads[a.name]),
            sha256=hashlib.sha256(self.payloads[a.name]).hexdigest()) for a in original_plan.assets))
        self.subject = subject or replace(original, stable_latest_identity=stable_identity())
        self.selection = SimpleNamespace(subject=self.subject, consumer_artifact_id=41,
                                         consumer_artifact_size=1, consumer_artifact_sha256='1' * 64)
        self.requests, self.routes, self.route, self.errors = [], {}, None, []
        self.assets, self.release, self.redirects = {}, None, {}
        self.latest = dict(STABLE)
        self.stable = dict(STABLE)
        self._stop, self._threads = threading.Event(), []

    def __enter__(self):
        self._temporary = tempfile.TemporaryDirectory(prefix='publisher-tls-')
        self.root = Path(self._temporary.name)
        self.ca, self.certificate, self.key = (self.root / n for n in ('ca.pem', 'server.pem', 'server.key'))
        commands = [
            ['req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', str(self.root / 'ca.key'),
             '-out', str(self.ca), '-days', '1', '-subj', '/CN=Publisher Test CA'],
            ['req', '-new', '-newkey', 'rsa:2048', '-nodes', '-keyout', str(self.key),
             '-out', str(self.root / 'server.csr'), '-subj', '/CN=api.github.com'],
            ['x509', '-req', '-in', str(self.root / 'server.csr'), '-CA', str(self.ca), '-CAkey',
             str(self.root / 'ca.key'), '-CAcreateserial', '-out', str(self.certificate), '-days', '1',
             '-extfile', str(self.root / 'extensions')]]
        (self.root / 'extensions').write_text('subjectAltName=DNS:api.github.com,DNS:uploads.github.com,'
            'DNS:release-assets.githubusercontent.com,DNS:productionresultssa5.blob.core.windows.net\n')
        for command in commands:
            done = subprocess.run(['/usr/bin/openssl', *command], stdout=subprocess.DEVNULL,
                                  stderr=subprocess.PIPE, timeout=15)
            if done.returncode:
                cause = RuntimeError('openssl stderr: ' + done.stderr.decode('utf-8', 'replace')[-2000:])
                raise subprocess.CalledProcessError(done.returncode, done.args, stderr=done.stderr) from cause
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.context.load_cert_chain(self.certificate, self.key)
        self.listener = socket.socket()
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen(100)
        self.listener.settimeout(0.1)
        self.port = self.listener.getsockname()[1]
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()
        return self

    def connect(self, host, timeout):
        context = ssl.create_default_context(cafile=str(self.ca))
        raw = socket.create_connection(('127.0.0.1', self.port), timeout)
        try:
            return context.wrap_socket(raw, server_hostname=host)
        except BaseException:
            raw.close()
            raise

    def _serve(self):
        while not self._stop.is_set():
            try:
                raw, _ = self.listener.accept()
            except (TimeoutError, OSError):
                continue
            thread = threading.Thread(target=self._handle, args=(raw,), daemon=True)
            self._threads.append(thread)
            thread.start()

    def _handle(self, raw):
        try:
            with self.context.wrap_socket(raw, server_side=True) as sock:
                sock.settimeout(2)
                data = bytearray()
                while b'\r\n\r\n' not in data:
                    block = sock.recv(1)
                    if not block:
                        return
                    data.extend(block)
                    if len(data) > 65536:
                        return
                header, body = bytes(data).split(b'\r\n\r\n', 1)
                lines = header.decode('ascii').split('\r\n')
                method, path, _ = lines[0].split(' ')
                headers = dict((k.lower(), v.strip()) for k, v in (line.split(':', 1) for line in lines[1:]))
                index = len(self.requests)
                self.requests.append((method, path, headers, body))
                size = int(headers.get('content-length', 0))
                while len(body) < size:
                    chunk = sock.recv(min(65536, size - len(body)))
                    if not chunk:
                        return
                    body += chunk
                self.requests[index] = (method, path, headers, body)
                response = self.routes.get((method, path))
                if callable(response):
                    response = response(method, path, headers, body)
                if response is None and self.route is not None:
                    response = self.route(method, path, headers, body)
                if response is None:
                    response = self._release(method, path, headers, body)
                if type(response) is dict:
                    if response.get('delay'):
                        time.sleep(response['delay'])
                    if response.get('raw'):
                        sock.sendall(response['raw'])
                    return
                status, extra, content = response
                extra = {'Content-Length': str(len(content)), 'Connection': 'close', **extra}
                sock.sendall((f'HTTP/1.1 {status} Fixture\r\n' + ''.join(
                    k + ': ' + str(v) + '\r\n' for k, v in extra.items()) + '\r\n').encode() + content)
        except (OSError, ValueError, ssl.SSLError):
            pass
        except BaseException as error:
            self.errors.append(type(error).__name__)
        finally:
            raw.close()

    @staticmethod
    def response(value, status=200):
        return status, {'Content-Type': 'application/json'}, json.dumps(value).encode()

    def _release(self, method, path, headers, body):
        parsed, prefix = urlsplit(path), wire.ROOT
        suffix, query = parsed.path.removeprefix(prefix), parse_qs(parsed.query)
        if method == 'GET' and suffix.startswith('/git/ref/tags/'):
            tag = suffix.removeprefix('/git/ref/tags/')
            return self.response({'ref': 'refs/tags/' + tag, 'object': STABLE_TAG if tag == STABLE['tag_name']
                                  else {'type': 'commit', 'sha': self.subject.tag_object_sha}})
        if method == 'GET' and suffix in ('/releases/50', '/releases/latest'):
            row = self.stable if suffix.endswith('/50') else self.latest
            return self.response(row if row else {'message': 'Not Found'}, 200 if row else 404)
        if method == 'GET' and suffix == '/releases':
            return self.response(([self.stable] + ([self.release] if self.release else []))
                                 if query.get('page') == ['1'] else [])
        if method == 'POST' and suffix == '/releases':
            value = json.loads(body)
            self.release = dict(value, id=100, target_commitish=self.subject.source.source_sha,
                                published_at=None, assets=[])
            return self.response(self.release, 201)
        if suffix == '/releases/100':
            if method == 'PATCH':
                self.release.update(json.loads(body))
                self.release['published_at'] = '2026-10-07T00:00:00Z'
            return self.response(self.release)
        if suffix == '/releases/100/assets':
            if method == 'POST':
                name, ident = query['name'][0], 200 + len(self.assets)
                row = {'id': ident, 'name': name, 'content_type': headers['content-type'],
                       'size': len(body), 'digest': 'sha256:' + hashlib.sha256(body).hexdigest(), 'state': 'uploaded'}
                self.assets[ident] = (row, body)
                return self.response(row, 201)
            return self.response([a[0] for a in self.assets.values()] if query.get('page') == ['1'] else [])
        if suffix.startswith('/releases/assets/'):
            ident = int(suffix.rsplit('/', 1)[1])
            row, content = self.assets[ident]
            if headers.get('accept') != 'application/octet-stream':
                return self.response(row)
            if ident in self.redirects:
                return 302, {'Location': self.redirects[ident]}, b''
            return 200, {}, content
        if headers.get('host') == wire.STORAGE and parsed.path.startswith('/asset/'):
            return 200, {}, self.assets[int(parsed.path.rsplit('/', 1)[1])][1]
        return self.response({'message': 'Not Found'}, 404)

    def close(self):
        self._stop.set()
        self.listener.close()
        self.thread.join(3)
        for thread in self._threads:
            thread.join(3)
        self._temporary.cleanup()

    def __exit__(self, *args):
        self.close()
