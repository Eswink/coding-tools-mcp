"""Private process-local request ownership; not a GitHub authorization grant.

Fixed trusted source and no same-UID writer are prerequisites. Python reflection
or replacing trusted modules is not an external-input security boundary.
"""
from copy import deepcopy
import hashlib
import math
import os
import threading
import time
from types import MethodType

from rc_consumer_io import CHUNK
import rc_publication_contract as core

_ISSUER = object()


def _need(ok, code='invalid_request'):
    import rc_publication_github as wire
    if not ok:
        raise wire.WireFailure(code, 'none')


class _Opaque:
    __slots__ = ()

    def __setattr__(self, name, value):
        raise AttributeError('owned request is read-only')

    def __repr__(self):
        return '<owned publication request>'

    def __reduce_ex__(self, protocol):
        raise TypeError('owned request is not serializable')

    def __copy__(self):
        raise TypeError('owned request is not transferable')

    def __deepcopy__(self, memo):
        raise TypeError('owned request is not transferable')


class _CredentialOwner(_Opaque):
    __slots__ = ('_token', '_selection', '_client', '_session_owner')

    def __init__(self, issuer, token, selection, client):
        from rc_publication_stage import Selection
        _need(issuer is _ISSUER)
        _need(type(token) is str and 0 < len(token) <= 8192
              and all(33 <= ord(c) < 127 for c in token))
        _need(type(selection.subject) is core.PublicationSubject)
        selected = Selection(deepcopy(selection.subject), selection.consumer_artifact_id,
                             selection.consumer_artifact_size, selection.consumer_artifact_sha256)
        for name, value in (('_token', token), ('_selection', selected),
                            ('_client', client), ('_session_owner', None)):
            object.__setattr__(self, name, value)


def _credential(token, selection, client):
    import rc_publication_github as wire
    _need(type(client) is wire.GitHub)
    return _CredentialOwner(_ISSUER, token, selection, client)


class _SessionOwner(_Opaque):
    __slots__ = ('_session', '_client', '_credential', '_pid')

    def __init__(self, issuer, session, client):
        import rc_publication_executor as executor
        import rc_publication_github as wire
        _need(issuer is _ISSUER and type(session) is executor.PublisherSession
              and type(client) is wire.GitHub and session._api is client
              and session._selection is client.selection
              and client._credential._session_owner is None)
        for name, value in (('_session', session), ('_client', client),
                            ('_credential', client._credential), ('_pid', os.getpid())):
            object.__setattr__(self, name, value)
        object.__setattr__(client._credential, '_session_owner', self)


def _session_owner(session, client):
    return _SessionOwner(_ISSUER, session, client)


class _ReadScope(_Opaque):
    """Native prepare/operation lifetime; never an authorization capability."""
    __slots__ = ('_owner', '_op', '_deadline', '_thread', '_pid', '_retired')

    def __init__(self, issuer, owner, op):
        _need(issuer is _ISSUER and type(owner) is _SessionOwner)
        session = owner._session
        _need(owner._pid == os.getpid() and session._lock.locked()
              and (op is None or type(op) is core.Operation)
              and type(session._deadline) in (int, float) and math.isfinite(session._deadline))
        for name, value in (('_owner', owner), ('_op', op), ('_deadline', session._deadline),
                            ('_thread', threading.get_ident()), ('_pid', os.getpid()),
                            ('_retired', False)):
            object.__setattr__(self, name, value)

    def _check(self, client):
        import rc_publication_executor as executor
        owner, session = self._owner, self._owner._session
        _need(not self._retired and self._pid == owner._pid == os.getpid()
              and self._thread == threading.get_ident(), 'invalid_event')
        _need(session._owner is owner and session._api is owner._client is client
              and not client._closed and client._credential is owner._credential
              and owner._credential._session_owner is owner
              and session._selection is client.selection is owner._credential._selection,
              'invalid_event')
        _need(session._lock.locked() and session._read_scope is self, 'invalid_event')
        if self._op is None:
            _need(session._transition is None and session._inflight is None, 'invalid_event')
        else:
            _need(session._inflight is self._op and session._transition is not None
                  and session._transition.action is self._op
                  and session._transition.state.pending is self._op, 'invalid_event')
        executor.PublisherSession._check_active(session)
        _need(type(session._deadline) in (int, float) and math.isfinite(session._deadline)
              and time.monotonic() < min(self._deadline, session._deadline), 'timeout')


def _read_scope(owner, op):
    scope = _ReadScope(_ISSUER, owner, op)
    session = owner._session
    _need(session._read_scope is None, 'invalid_event')
    session._read_scope = scope
    try:
        scope._check(owner._client)
    except BaseException:
        session._read_scope = None
        object.__setattr__(scope, '_retired', True)
        raise
    return scope


def _read_controls(client, deadline, caller):
    """Capture the native controller internally; caller controls only strengthen."""
    import rc_publication_github as wire
    _need(type(client) is wire.GitHub and not client._closed and callable(caller))
    credential = client._credential
    _need(type(credential) is _CredentialOwner and credential._client is client)
    deadline = time.monotonic() + wire.DEADLINE if deadline is None else deadline
    _need(type(deadline) in (int, float) and math.isfinite(deadline))
    owner, scope = credential._session_owner, None
    if owner is not None:
        _need(type(owner) is _SessionOwner and owner._client is client
              and owner._credential is credential)
        scope = owner._session._read_scope
        _need(type(scope) is _ReadScope and scope._owner is owner, 'invalid_event')
        scope._check(client)
        deadline = min(deadline, scope._deadline, owner._session._deadline)
    def active():
        _need(not client._closed and client._credential is credential
              and client.selection is credential._selection, 'cancelled')
        if scope is not None:
            scope._check(client)
        _need(time.monotonic() < deadline, 'timeout')
        caller()
        if scope is not None:
            scope._check(client)
        _need(time.monotonic() < deadline, 'timeout')
    active()
    return deadline, active, scope


class _OperationScope(_Opaque):
    __slots__ = ('_owner', '_op', '_deadline', '_thread', '_snapshot', '_used', '_retired')

    def __init__(self, issuer, owner, op):
        _need(issuer is _ISSUER and type(owner) is _SessionOwner)
        session = owner._session
        _need(type(op) is core.Operation and op.kind in core.MUTATIONS
              and type(session._deadline) in (int, float) and math.isfinite(session._deadline))
        for name, value in (('_owner', owner), ('_op', op), ('_deadline', session._deadline),
                            ('_thread', threading.get_ident()), ('_snapshot', None),
                            ('_used', False), ('_retired', False)):
            object.__setattr__(self, name, value)

    def _check(self, client, op, *, consumed=False):
        import rc_publication_executor as executor
        owner, session = self._owner, self._owner._session
        _need(not self._retired and self._thread == threading.get_ident())
        _need(owner._pid == os.getpid(), 'invalid_event')
        _need(session._owner is owner and session._api is owner._client is client
              and not client._closed and client._credential is owner._credential
              and owner._credential._session_owner is owner
              and session._selection is client.selection is owner._credential._selection)
        _need(session._lock.locked() and session._request_scope is self
              and session._inflight is op is self._op
              and session._transition is not None
              and session._transition.action is op and session._transition.state.pending is op,
              'invalid_event')
        executor.PublisherSession._check_active(session)
        _need(type(session._deadline) in (int, float) and math.isfinite(session._deadline)
              and time.monotonic() < min(self._deadline, session._deadline), 'timeout')
        _need(self._used is consumed and (op.operation_id in session._attempted) is consumed,
              'invalid_event')

    def _consume(self, snapshot):
        import rc_publication_executor as executor
        _need(self._snapshot is snapshot and type(snapshot) is _RequestSnapshot)
        self._check(snapshot._client, snapshot._op)
        executor.PublisherSession._before_write(self._owner._session)
        object.__setattr__(self, '_used', True)


def _operation_scope(owner, op):
    scope = _OperationScope(_ISSUER, owner, op)
    session = owner._session
    _need(session._request_scope is None, 'invalid_event')
    session._request_scope = scope
    try:
        scope._check(owner._client, op)
    except BaseException:
        session._request_scope = None
        object.__setattr__(scope, '_retired', True)
        raise
    return scope


def _retire(scope):
    if type(scope) in (_OperationScope, _ReadScope):
        object.__setattr__(scope, '_retired', True)


class _RequestSnapshot(_Opaque):
    __slots__ = ('_client', '_credential', '_scope', '_op', '_method', '_host', '_path',
                 '_header', '_body', '_stream', '_asset', '_identity', '_deadline', '_read_scope')

    def __init__(self, issuer, client, scope, op, method, host, path, body, stream,
                 asset, anonymous, binary, deadline, before_write):
        import rc_publication_executor as executor
        import rc_publication_github as wire
        _need(issuer is _ISSUER and type(client) is wire.GitHub and not client._closed)
        _need(type(body) is bytes and type(deadline) in (int, float) and math.isfinite(deadline))
        _need(type(anonymous) is bool and type(binary) is bool
              and host in (wire.API, wire.UPLOAD, wire.STORAGE) and type(path) is str
              and path.startswith('/') and all(33 <= ord(c) < 127 for c in path))
        wire.GitHub._closed_request(client, method, host, path, body, stream, asset, op)
        credential, identity, read_scope = client._credential, None, None
        _need(type(credential) is _CredentialOwner and credential._client is client)
        if op is not None:
            _need(type(scope) is _OperationScope and not anonymous and not binary)
            scope._check(client, op)
            _need(scope._snapshot is None, 'invalid_event')
            session = scope._owner._session
            _need(type(before_write) is MethodType and before_write.__self__ is session
                  and before_write.__func__ is executor.PublisherSession._before_write)
            deadline = min(deadline, scope._deadline, session._deadline)
            if stream is not None:
                from rc_publication_stage import StagedAssets
                stage, ordinal = session._stage, op.asset_ordinal
                _need(type(stage) is StagedAssets and stage._entered and not stage._closed
                      and stage._selection == client.selection
                      and type(ordinal) is int and 0 <= ordinal < len(stage._handles)
                      and stream is stage._handles[ordinal] and asset == stage.plan.assets[ordinal]
                      and not stream.closed and stream.tell() == 0)
                if stage._api is not client:
                    from rc_publication_artifact_admission import _ArtifactOwner, _StageAPI, _OWNERS
                    owner = session._artifact_owner
                    _need(type(owner) is _ArtifactOwner and _OWNERS.get(client) is owner
                          and owner.entered and not owner.closed and owner.stage is stage
                          and owner.api is client and owner.selection is client.selection
                          and owner._session is session
                          and type(stage._api) is _StageAPI and stage._api is owner.adapter
                          and not owner.adapter.closed and owner.adapter.api is client
                          and owner.adapter.selection is client.selection)
                stage._check_handle(ordinal)
                info = os.fstat(stream.fileno())
                identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        else:
            _need(scope is None)
            deadline, _, read_scope = _read_controls(client, deadline, lambda: None)
        headers = {'Host': host, 'Connection': 'close', 'Accept':
                   'application/octet-stream' if binary else 'application/vnd.github+json',
                   'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'bounded-rc-publisher'}
        if not anonymous and host != wire.STORAGE:
            headers['Authorization'] = 'Bearer ' + credential._token
        if method != 'GET':
            headers.update({'Content-Length': str(asset.size if stream is not None else len(body)),
                            'Content-Type': asset.media_type if stream is not None else 'application/json'})
        header = (method + ' ' + path + ' HTTP/1.1\r\n' + ''.join(
            key + ': ' + value + '\r\n' for key, value in headers.items()) + '\r\n').encode('ascii')
        values = (client, credential, scope, op, method, host, path, header, body,
                  stream, asset, identity, deadline, read_scope)
        for name, value in zip(self.__slots__, values):
            object.__setattr__(self, name, value)
        if scope is not None:
            object.__setattr__(scope, '_snapshot', self)

    def _check(self, client, *, consumed=False):
        _need(client is self._client and not client._closed
              and client._credential is self._credential
              and client.selection is self._credential._selection, 'cancelled')
        if self._read_scope is not None:
            self._read_scope._check(client)
        _need(time.monotonic() < self._deadline, 'timeout')
        if self._scope is not None:
            _need(self._scope._snapshot is self)
            self._scope._check(client, self._op, consumed=consumed)

    def _prepare_stream(self, active):
        if self._stream is None:
            return
        stream, asset, scope = self._stream, self._asset, self._scope
        stage = scope._owner._session._stage
        stage._check_handle(self._op.asset_ordinal)
        info = os.fstat(stream.fileno())
        current = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        _need(current == self._identity and stream.tell() == 0)
        digest, total = hashlib.sha256(), 0
        while total < asset.size:
            active()
            chunk = stream.read(min(CHUNK, asset.size - total))
            _need(type(chunk) is bytes and 0 < len(chunk) <= asset.size - total)
            digest.update(chunk)
            total += len(chunk)
        active()
        _need(stream.read(1) == b'' and digest.hexdigest() == asset.sha256)
        stage._check_handle(self._op.asset_ordinal)
        info = os.fstat(stream.fileno())
        _need((info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns) == self._identity)
        stream.seek(0)
        active()


def _snapshot(client, scope, op, method, host, path, body, stream, asset,
              anonymous, binary, deadline, before_write):
    return _RequestSnapshot(_ISSUER, client, scope, op, method, host, path, body,
                            stream, asset, anonymous, binary, deadline, before_write)
