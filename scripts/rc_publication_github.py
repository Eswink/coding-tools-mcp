"""Closed HTTPS publisher boundary; production authority remains unavailable."""
from __future__ import annotations
from dataclasses import dataclass
from functools import wraps
import hashlib
import json
import re
import socket
import ssl
import time
from urllib.parse import urlsplit, quote

import rc_publication_contract as core
from rc_consumer_io import CHUNK, FILE_LIMIT
from rc_consumer_wire_failure import _publication_failure
from rc_pretag_types import REPOSITORY
import rc_publication_admission as admission
import rc_publication_request as owned

API, UPLOAD, STORAGE = 'api.github.com', 'uploads.github.com', 'release-assets.githubusercontent.com'
ROOT = '/repos/' + REPOSITORY
METADATA, HEADERS, PAGES, TIMEOUT, DEADLINE = 2 * 1024**2, 32768, 100, 15, 300


class WireFailure(ValueError):
    def __init__(self, code, effect, release_id=None, asset=None):
        self.code = code if type(code) is str and code in core.CODES else 'adapter_error'
        self.effect = effect if type(effect) is str and effect in ('none', 'unknown', 'confirmed') else 'none'
        self.release_id = release_id if (self.effect == 'confirmed' and type(release_id) is int
                                        and 0 < release_id < 2**63) else None
        self.asset = asset if self.effect == 'confirmed' and type(asset) is core.RemoteAsset else None
        super().__init__(self.code)


def _need(ok, code='verification_failed'):
    if not ok:
        raise WireFailure(code, 'none')


def _safe(method):
    @wraps(method)
    def call(*args, **kwargs):
        failure = None
        try:
            return method(*args, **kwargs)
        except BaseException as error:
            failure = (WireFailure(error.code, error.effect, error.release_id, error.asset)
                       if isinstance(error, WireFailure) else WireFailure('adapter_error', 'none'))
        raise failure
    return call


def _prepare_admission(selection, api, *, check_active, deadline):
    """Authenticate metadata for local staging; never grant mutation permission."""
    import rc_publication_artifact_admission as artifacts
    return artifacts.prepare_admission(selection, api, check_active=check_active, deadline=deadline)


def _authenticate(selection, api, *, check_active, deadline):
    try:
        import rc_publication_artifact_admission as artifacts
        report = artifacts.authenticate_artifacts(api, selection,
            check_active=check_active, deadline=deadline)
    except WireFailure:
        raise
    except Exception as error:
        raise artifacts._wire_failure(error) from None
    _need(all(row[3] == 'passed' for row in report.rows) and report.draft_visibility == 'proven', 'fence_blocked')
    return report.rows, report.draft_visibility


def _remote_constraint(subject):
    raise WireFailure('fence_blocked', 'none')


def _authorize(op, subject, *, request, scope):
    raise WireFailure('denied', 'none')


@dataclass(frozen=True)
class _LatestAbsent:
    repository: str
    source_sha: str


def _authenticated_latest_absence(selection):
    raise WireFailure('fence_blocked', 'none')


def _connect(host, timeout):
    context = ssl.create_default_context()
    raw = socket.create_connection((host, 443), timeout=timeout)
    try:
        return context.wrap_socket(raw, server_hostname=host)
    except BaseException:
        raw.close()
        raise


def _positive(value):
    _need(type(value) is int and 0 < value < 2**63, 'identity_mismatch')
    return value


def _json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            _need(key not in result)
            result[key] = value
        return result
    def bound(value, depth=0):
        _need(depth <= 32)
        if type(value) in (dict, list):
            _need(len(value) <= 10000)
            for child in value.values() if type(value) is dict else value:
                bound(child, depth + 1)
        elif type(value) is float:
            _need(False)
    value = json.loads(raw.decode('utf-8'), object_pairs_hook=unique,
                       parse_constant=lambda _: _need(False))
    _need(type(value) in (dict, list))
    bound(value)
    return value


class _Reader:
    def __init__(self, sock, deadline, active):
        self.sock, self.deadline, self.active = sock, deadline, active
        self.buffer = bytearray()
    def check(self):
        self.active()
        left = self.deadline - time.monotonic()
        _need(left > 0, 'timeout')
        self.sock.settimeout(min(TIMEOUT, left))
    def take(self, size):
        while len(self.buffer) < size:
            # Poll cancellation while waiting for bytes, retaining the old
            # per-recv TIMEOUT as an absolute idle bound across retries.
            idle_deadline = time.monotonic() + TIMEOUT
            while True:
                self.check()
                left = min(self.deadline, idle_deadline) - time.monotonic()
                _need(left > 0, 'timeout')
                self.sock.settimeout(min(0.1, left))
                try:
                    data = self.sock.recv(min(CHUNK, size - len(self.buffer)))
                except TimeoutError:
                    continue
                break
            _need(data)
            self.buffer.extend(data)
        result = bytes(self.buffer[:size])
        del self.buffer[:size]
        return result
    def line(self, limit):
        result = bytearray()
        while not result.endswith(b'\r\n'):
            _need(len(result) < limit)
            result.extend(self.take(1))
        return bytes(result)
    def response(self, limit, binary=False):
        first = self.line(HEADERS)
        _need(re.fullmatch(rb'HTTP/1\.[01] [1-5][0-9]{2} [^\r\n]*\r\n', first) is not None)
        status, used, headers = int(first[9:12]), len(first), {}
        while True:
            line = self.line(HEADERS - used)
            used += len(line)
            if line == b'\r\n':
                break
            _need(b':' in line and line[:1] not in b' \t')
            key, value = line[:-2].split(b':', 1)
            _need(re.fullmatch(rb'[A-Za-z0-9-]+', key) is not None)
            name, value = key.decode('ascii').lower(), value.strip().decode('ascii')
            _need(name not in headers and all(32 <= ord(c) < 127 for c in value))
            headers[name] = value
        _need(headers.get('content-encoding', 'identity') == 'identity')
        _need(not ('content-length' in headers and 'transfer-encoding' in headers))
        raw, digest, total = bytearray(), hashlib.sha256(), 0
        def consume(size):
            nonlocal total
            _need(0 <= size <= limit - total)
            while size:
                chunk = self.take(min(CHUNK, size))
                digest.update(chunk)
                if not binary:
                    raw.extend(chunk)
                total += len(chunk)
                size -= len(chunk)
        if 'transfer-encoding' in headers:
            _need(headers['transfer-encoding'].lower() == 'chunked')
            while True:
                line = self.line(128)
                _need(re.fullmatch(rb'[0-9a-fA-F]{1,16}\r\n', line) is not None)
                size = int(line[:-2], 16)
                if not size:
                    _need(self.take(2) == b'\r\n')
                    break
                consume(size)
                _need(self.take(2) == b'\r\n')
        else:
            length = headers.get('content-length', '')
            _need(re.fullmatch(r'[0-9]{1,12}', length) is not None)
            consume(int(length))
        self.check()
        return status, headers, (total, digest.hexdigest()) if binary else bytes(raw)


class GitHub:
    def __init__(self, token: str, selection):
        self._closed = False
        self._credential = owned._credential(token, selection, self)

    @property
    def token(self):
        return '' if self._closed else self._credential._token

    @property
    def selection(self):
        return self._credential._selection

    def _request(self, method, host, path, *, body=b'', stream=None, asset=None,
                 op=None, scope=None, before_write=lambda: None, check_active=lambda: None,
                 anonymous=False, binary=False, limit=METADATA, deadline=None):
        sock = None
        possible, confirmed, result, failure = False, False, None, None
        deadline = time.monotonic() + DEADLINE if deadline is None else deadline
        try:
            _need(not self._closed, 'cancelled')
            if op is None:
                deadline, check_active, _ = owned._read_controls(self, deadline, check_active)
            check_active()
            _need(time.monotonic() < deadline, 'timeout')
            self._closed_request(method, host, path, body, stream, asset, op)
            _need(op is None or (not anonymous and not binary), 'invalid_request')
            _need(host in (API, UPLOAD, STORAGE) and path.startswith('/') and
                  all(33 <= ord(c) < 127 for c in path), 'invalid_request')
            snapshot = owned._snapshot(self, scope, op, method, host, path, body,
                stream, asset, anonymous, binary, deadline, before_write)
            deadline = snapshot._deadline
            def active():
                snapshot._check(self, consumed=possible)
                check_active()
                snapshot._check(self, consumed=possible)
            active()
            length = asset.size if stream is not None else len(snapshot._body)
            sock = _connect(host, min(TIMEOUT, max(0.001, deadline - time.monotonic())))
            _need(isinstance(sock, ssl.SSLSocket) and sock.context.check_hostname
                  and sock.context.verify_mode == ssl.CERT_REQUIRED and sock.server_hostname == host
                  and sock.getpeercert(), 'denied')
            reader = _Reader(sock, deadline, active)
            reader.check()
            if op is not None:
                _authenticate(self.selection, self, check_active=active, deadline=deadline)
                _remote_constraint(self.selection.subject)
                _authorize(op, self.selection.subject, request=snapshot, scope=scope)
                reader.check()
                snapshot._prepare_stream(active)
                snapshot._scope._consume(snapshot)
                possible = True
            sock.sendall(snapshot._header)
            if stream is None:
                if snapshot._body:
                    reader.check()
                    sock.sendall(snapshot._body)
            else:
                digest, total = hashlib.sha256(), 0
                while total < length:
                    reader.check()
                    chunk = stream.read(min(CHUNK, length - total))
                    _need(type(chunk) is bytes and 0 < len(chunk) <= length - total)
                    sock.sendall(chunk)
                    digest.update(chunk)
                    total += len(chunk)
                _need(stream.read(1) == b'' and digest.hexdigest() == asset.sha256)
            result = reader.response(limit, binary)
            if op is not None:
                result = self._mutation_result(op, result)
            else:
                active()
            confirmed = op is not None
        except BaseException as error:
            normalized = _publication_failure(error) if op is None else None
            if normalized is not None and normalized.effect != 'none':
                failure = normalized
            else:
                code = error.code if isinstance(error, WireFailure) else (
                    'timeout' if isinstance(error, TimeoutError) else 'adapter_error')
                failure = WireFailure(code, 'unknown' if possible else 'none')
        if sock is not None:
            try:
                sock.close()
            except BaseException:
                if failure is None:
                    failure = WireFailure('adapter_error', 'confirmed' if confirmed else 'none',
                        result if confirmed and type(result) is int else op.release_id if confirmed else None,
                        result if type(result) is core.RemoteAsset else None)
        if failure is None and op is None:
            try:
                active()
            except BaseException as error:
                normalized = _publication_failure(error)
                if normalized is not None and normalized.effect != 'none':
                    failure = normalized
                else:
                    failure = WireFailure(error.code if isinstance(error, WireFailure)
                                          else 'adapter_error', 'none')
        if failure is not None:
            raise failure
        return result

    def _closed_request(self, method, host, path, body, stream, asset, op):
        if op is None:
            _need(method == 'GET' and body == b'' and stream is None and asset is None, 'invalid_request')
            return
        _need(type(op) is core.Operation and op.kind in core.MUTATIONS, 'invalid_request')
        self._op(op, op.kind)
        if op.kind == 'UploadAsset':
            _need((method, host, path, body, asset) == ('POST', UPLOAD, ROOT + '/releases/' +
                  str(op.release_id) + '/assets?name=' + quote(op.asset.name, safe=''), b'', op.asset)
                  and stream is not None, 'invalid_request')
            return
        create = op.kind == 'CreateDraft'
        expected = ({'tag_name': self.selection.subject.tag, 'draft': True, 'prerelease': True,
                     'make_latest': 'false', 'generate_release_notes': False} if create else
                    {'draft': False, 'prerelease': True, 'make_latest': 'false'})
        _need((method, host, path, body) == ('POST' if create else 'PATCH', API,
              ROOT + '/releases' + ('' if create else '/' + str(op.release_id)),
              json.dumps(expected, separators=(',', ':'), sort_keys=True).encode())
              and stream is None and asset is None, 'invalid_request')

    def _metadata(self, suffix, anonymous=False, deadline=None, absent=False, check_active=lambda: None):
        deadline, check_active, _ = owned._read_controls(self, deadline, check_active)
        status, _, body = self._request('GET', API, ROOT + ('' if suffix == '/' else suffix),
                                       anonymous=anonymous, deadline=deadline, check_active=check_active)
        check_active()
        if status == 404 and absent:
            return None
        _need(status == 200)
        try:
            value = _json(body)
        except BaseException:
            pass
        else:
            check_active()
            return value
        raise WireFailure('verification_failed', 'none')

    @_safe
    def get(self, suffix, *, deadline=None, check_active=lambda: None):
        _need(type(suffix) is str and re.fullmatch(r'/[A-Za-z0-9_./?=&-]*', suffix)
              and '..' not in suffix and '//' not in suffix, 'invalid_request')
        deadline, check_active, _ = owned._read_controls(self, deadline, check_active)
        value = self._metadata(suffix, deadline=deadline, check_active=check_active)
        check_active()
        return value

    def _pages(self, suffix, anonymous, deadline, check_active=lambda: None):
        deadline, check_active, _ = owned._read_controls(self, deadline, check_active)
        rows, ids, names = [], set(), set()
        for page in range(1, PAGES + 1):
            batch = self._metadata(suffix + f'?per_page=100&page={page}', anonymous, deadline,
                                   check_active=check_active)
            _need(type(batch) is list and len(batch) <= 100)
            for row in batch:
                check_active()
                _need(type(row) is dict)
                ident = _positive(row.get('id'))
                name = row.get('name') if '/assets' in suffix else row.get('tag_name')
                _need(type(name) is str and bool(name) and ident not in ids and name not in names)
                ids.add(ident)
                names.add(name)
                rows.append(row)
            if len(batch) < 100:
                check_active()
                return rows
        raise WireFailure('verification_failed', 'none')

    def _tag(self, tag, anonymous, deadline, check_active=lambda: None):
        deadline, check_active, _ = owned._read_controls(self, deadline, check_active)
        _need(type(tag) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,159}', tag))
        value = self._metadata('/git/ref/tags/' + tag, anonymous, deadline, check_active=check_active)
        _need(type(value) is dict and value.get('ref') == 'refs/tags/' + tag)
        obj = value.get('object')
        _need(type(obj) is dict and obj.get('type') in ('commit', 'tag')
              and type(obj.get('sha')) is str and re.fullmatch('[a-f0-9]{40}', obj['sha']))
        check_active()
        return {'type': obj['type'], 'sha': obj['sha']}

    def _projection(self, row, anonymous, deadline, check_active=lambda: None):
        deadline, check_active, _ = owned._read_controls(self, deadline, check_active)
        _need(type(row) is dict)
        _positive(row.get('id'))
        _need(all(type(row.get(k)) is bool for k in ('draft', 'prerelease'))
              and all(type(row.get(k)) is str for k in ('tag_name', 'target_commitish', 'published_at'))
              and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ', row['published_at']))
        value = {k: row[k] for k in ('id', 'tag_name', 'target_commitish', 'draft', 'prerelease', 'published_at')}
        value['tag_ref'] = self._tag(row['tag_name'], anonymous, deadline, check_active)
        check_active()
        return value

    def _latest(self, anonymous, deadline, check_active=lambda: None):
        deadline, check_active, _ = owned._read_controls(self, deadline, check_active)
        expected = self.selection.subject.stable_latest_identity
        stable = self._metadata('/releases/' + str(_positive(expected[0])), anonymous, deadline,
                                check_active=check_active)
        _need(stable.get('id') == expected[0])
        latest = self._metadata('/releases/latest', anonymous, deadline, absent=True,
                                check_active=check_active)
        if latest is None:
            _need(expected[1] == 0)
            proof = _authenticated_latest_absence(self.selection)
            _need(type(proof) is _LatestAbsent and proof.repository == REPOSITORY
                  and proof.source_sha == self.selection.subject.source.source_sha)
            _, visibility = _authenticate(self.selection, self, check_active=check_active, deadline=deadline)
            _need(visibility == 'proven')
            projected = None
        else:
            _need(type(latest) is dict and latest.get('id') == expected[1])
            projected = self._projection(latest, anonymous, deadline, check_active)
        value = {'stable': self._projection(stable, anonymous, deadline, check_active), 'latest': projected}
        identity = (expected[0], 0 if latest is None else latest['id'],
                    hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest())
        check_active()
        return identity

    def _remote_asset(self, row, expected, expected_id=None):
        _need(type(row) is dict)
        ident = _positive(row.get('id'))
        _need(expected_id is None or ident == expected_id, 'identity_mismatch')
        _need(row.get('name') == expected.name and row.get('content_type') == expected.media_type
              and type(row.get('size')) is int and row['size'] == expected.size
              and row.get('digest') == 'sha256:' + expected.sha256 and row.get('state') == 'uploaded',
              'identity_mismatch')
        return core.RemoteAsset(ident, expected)

    def _download(self, remote, anonymous, deadline, check_active=lambda: None):
        deadline, check_active, _ = owned._read_controls(self, deadline, check_active)
        _need(remote.asset.size <= FILE_LIMIT)
        status, headers, measured = self._request('GET', API, ROOT + '/releases/assets/' + str(remote.asset_id),
            binary=True, anonymous=anonymous, limit=remote.asset.size, deadline=deadline,
            check_active=check_active)
        check_active()
        if status == 302:
            location = headers.get('location', '')
            _need(len(location) <= 8192 and all(33 <= ord(c) < 127 for c in location))
            try:
                url = urlsplit(location)
                valid = (url.scheme == 'https' and url.hostname == STORAGE and url.port in (None, 443)
                         and url.username is None and url.password is None and not url.fragment
                         and url.path.startswith('/') and not url.path.startswith('//'))
            except ValueError:
                valid = False
            _need(valid)
            status, _, measured = self._request('GET', STORAGE, url.path + ('?' + url.query if url.query else ''),
                binary=True, anonymous=True, limit=remote.asset.size, deadline=deadline,
                check_active=check_active)
            check_active()
        _need(status == 200 and measured == (remote.asset.size, remote.asset.sha256))
        return core.RemoteAsset(remote.asset_id, remote.asset, *measured, anonymous)

    def _op(self, op, kind):
        _need(type(op) is core.Operation and op.kind == kind, 'invalid_request')
        op.__post_init__()
        _need(op.tag is None or op.tag == self.selection.subject.tag, 'identity_mismatch')
        if kind == 'UploadAsset':
            fixed = (*core.payloads(self.selection.subject.source.version),
                     ('RC_PROVENANCE.json', 'provenance', 'application/json'),
                     ('SHA256SUMS_' + self.selection.subject.source.version + '.txt', 'checksums', 'text/plain'))
            _need(op.asset.size <= FILE_LIMIT and (op.asset.name, op.asset.family, op.asset.media_type)
                  == fixed[op.asset_ordinal], 'invalid_request')


    @_safe
    def create_draft(self, op, *, before_write, check_active, scope=None):
        self._op(op, 'CreateDraft')
        body = {'tag_name': self.selection.subject.tag, 'draft': True, 'prerelease': True,
                'make_latest': 'false', 'generate_release_notes': False}
        return self._mutation(op, 'POST', API, '/releases', body, before_write, check_active, scope)

    @_safe
    def publish_prerelease(self, op, *, before_write, check_active, scope=None):
        self._op(op, 'PublishPrerelease')
        return self._mutation(op, 'PATCH', API, '/releases/' + str(op.release_id),
                              {'draft': False, 'prerelease': True, 'make_latest': 'false'}, before_write, check_active, scope)

    def _mutation_result(self, op, response):
        status, _, raw = response
        _need(status == (200 if op.kind == 'PublishPrerelease' else 201))
        row = _json(raw)
        if op.kind == 'UploadAsset':
            remote = self._remote_asset(row, op.asset)
            _need(remote.asset_id not in op.expected_asset_ids, 'identity_mismatch')
            return remote
        _need(type(row) is dict and row.get('tag_name') == self.selection.subject.tag
              and row.get('draft') is op.draft and row.get('prerelease') is True)
        ident = _positive(row.get('id'))
        _need(op.release_id is None or ident == op.release_id, 'identity_mismatch')
        return ident

    def _mutation(self, op, method, host, suffix, body, before_write, check_active, scope=None):
        return self._request(method, host, ROOT + suffix,
            body=json.dumps(body, separators=(',', ':'), sort_keys=True).encode(), op=op,
            before_write=before_write, check_active=check_active, scope=scope)

    @_safe
    def upload_asset(self, op, stream, *, before_write, check_active, scope=None):
        self._op(op, 'UploadAsset')
        return self._request('POST', UPLOAD, ROOT + '/releases/' + str(op.release_id) + '/assets?name=' +
            quote(op.asset.name, safe=''), stream=stream, asset=op.asset, op=op,
            before_write=before_write, check_active=check_active, scope=scope)

    @_safe
    def verify_asset(self, op, *, deadline=None, check_active=lambda: None):
        self._op(op, 'VerifyAsset')
        deadline, check_active, _ = owned._read_controls(self, deadline, check_active)
        row = self._metadata('/releases/assets/' + str(op.asset_id), deadline=deadline,
                             check_active=check_active)
        remote = self._download(self._remote_asset(row, op.asset, op.asset_id), False, deadline, check_active)
        check_active()
        return remote

    @_safe
    def observe(self, state, *, staged, gates, draft_visibility, deadline=None, check_active=lambda: None):
        core._state(state)
        op, subject = state.pending, self.selection.subject
        _need(op is not None and op.kind in ('ObserveFence', 'ObserveDraft', 'VerifyPublished')
              and state.subject == subject, 'invalid_request')
        deadline, check_active, _ = owned._read_controls(self, deadline, check_active)
        public = op.kind == 'VerifyPublished'
        tag = self._tag(subject.tag, public, deadline, check_active)
        releases = self._pages('/releases', public, deadline, check_active)
        matching = tuple(r['id'] for r in releases if r['tag_name'] == subject.tag)
        assets, draft, prerelease = (), False, False
        if state.release_id is not None:
            row = self._metadata('/releases/' + str(state.release_id), public, deadline, check_active=check_active)
            _need(type(row) is dict and _positive(row.get('id')) == state.release_id and row.get('tag_name') == subject.tag
                  and type(row.get('draft')) is bool and type(row.get('prerelease')) is bool)
            draft, prerelease = row['draft'], row['prerelease']
            rows = self._pages('/releases/' + str(state.release_id) + '/assets', public, deadline, check_active)
            _need(len(rows) == len(state.asset_ids) and {r['id'] for r in rows} == set(state.asset_ids))
            by_id = {r['id']: r for r in rows}
            assets = tuple(self._remote_asset(by_id[ident], expected, ident)
                           for ident, expected in zip(state.asset_ids, state.plan.assets))
            if public or op.phase == 'before_publish':
                assets = tuple(self._download(a, public, deadline, check_active) for a in assets)
        observation = core.Observation(subject, staged, gates, tag['type'], tag['sha'], matching,
            draft_visibility, True, state.release_id, assets, draft, prerelease,
            self._latest(public, deadline, check_active))
        check_active()
        return observation

    def close(self):
        self._closed = True
