"""Parent-owned bounded supervisor for the single fixed-origin metadata worker.

The constructor accepts an existing token in memory. There is no environment
credential reader, arbitrary URL interface, retry, host option or injected
production transport. Call close before constructing a completed receipt.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import selectors
import struct
import subprocess
import sys
import threading
import time

from rc_pretag_metadata_worker import (
    ERROR_CODES, MAX_BODY, MAX_FRAME, MAX_REQUEST, MetadataAPIError,
    link_relations, parse_json, require, route, valid_token,
)

MAX_REQUESTS = 128
MAX_BYTES = 16 * MAX_BODY
REQUEST_SECONDS = 10.0
SESSION_SECONDS = 120.0
TEARDOWN_SECONDS = 5.0
WORKER_PATH = Path(__file__).resolve().with_name('rc_pretag_metadata_worker.py')


class CleanupUncertain(MetadataAPIError):
    """Fatal: a caller must not emit a completed receipt after this exception."""

    def __init__(self):
        super().__init__('cleanup_uncertain')


@dataclass(frozen=True)
class ApiResponse:
    value: dict | list
    link: str | None
    byte_count: int


class MetadataGitHub:
    """Serial supervised GETs. Library import and construction do not network."""

    def __init__(self, token):
        valid_token(token)
        require(sys.platform == 'linux' and sys.version_info[:2] == (3, 12)
                and hasattr(os, 'set_blocking'), 'unsupported_platform')
        self._token = token
        self._started = time.monotonic()
        self._process = None
        self._closed = False
        self._cleanup_uncertain = False
        self._request_count = 0
        self._response_bytes = 0
        self._lock = threading.Lock()

    @property
    def channel(self):
        return 'fixed_origin_tls_bearer_request'

    @property
    def request_count(self):
        return self._request_count

    @property
    def response_bytes(self):
        return self._response_bytes

    def _remaining(self, deadline):
        now = time.monotonic()
        require(now < self._started + SESSION_SECONDS, 'session_timeout')
        require(now < deadline, 'request_timeout')
        return min(deadline, self._started + SESSION_SECONDS) - now

    def _start(self):
        if self._process is not None:
            return
        try:
            self._process = subprocess.Popen(
                [sys.executable, '-I', '-S', str(WORKER_PATH)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                shell=False, close_fds=True, bufsize=0, env={'LC_ALL': 'C', 'LANG': 'C'},
            )
            os.set_blocking(self._process.stdin.fileno(), False)
            os.set_blocking(self._process.stdout.fileno(), False)
        except Exception:
            raise MetadataAPIError('worker_start_failed') from None

    def _exchange(self, raw, deadline):
        process = self._process
        outgoing = struct.pack('!I', len(raw)) + raw
        received = bytearray()
        sent = 0
        size = None
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            selector.register(process.stdin, selectors.EVENT_WRITE)
            while True:
                remaining = self._remaining(deadline)
                require(process.poll() is None, 'worker_failed')
                events = selector.select(remaining)
                if not events:
                    self._remaining(deadline)
                    continue
                for key, _ in events:
                    if key.fileobj is process.stdin:
                        try:
                            count = os.write(process.stdin.fileno(), outgoing[sent:])
                        except BlockingIOError:
                            continue
                        require(count > 0, 'invalid_ipc')
                        sent += count
                        if sent == len(outgoing):
                            selector.unregister(process.stdin)
                    else:
                        try:
                            chunk = os.read(process.stdout.fileno(), 65536)
                        except BlockingIOError:
                            continue
                        require(bool(chunk), 'worker_failed')
                        received.extend(chunk)
                        require(sent == len(outgoing), 'invalid_ipc')
                        if size is None and len(received) >= 4:
                            size = struct.unpack('!I', received[:4])[0]
                            require(0 < size <= MAX_FRAME, 'invalid_ipc')
                        if size is not None:
                            require(len(received) <= size + 4, 'invalid_ipc')
                            if len(received) == size + 4:
                                self._remaining(deadline)
                                return bytes(received[4:])

    def _reject_unsolicited(self):
        if self._process is None:
            return
        require(self._process.poll() is None, 'worker_failed')
        try:
            chunk = os.read(self._process.stdout.fileno(), 1)
        except BlockingIOError:
            return
        require(False, 'invalid_ipc' if chunk else 'worker_failed')

    def _decode(self, raw, operation, arguments):
        try:
            frame = parse_json(raw, response=False)
        except MetadataAPIError:
            raise MetadataAPIError('invalid_ipc') from None
        base = {'id', 'operation', 'byte_count'}
        require(type(frame) is dict and set(frame) in (base | {'code'}, base | {'value', 'link'}),
                'invalid_ipc')
        require(type(frame['id']) is int and frame['id'] == self._request_count
                and frame['operation'] == operation, 'invalid_ipc')
        count = frame['byte_count']
        require(type(count) is int and 0 <= count <= MAX_BODY, 'invalid_ipc')
        self._response_bytes += count
        require(self._response_bytes <= MAX_BYTES, 'aggregate_limit')
        if 'code' in frame:
            require(type(frame['code']) is str and frame['code'] in ERROR_CODES, 'invalid_ipc')
            raise MetadataAPIError(frame['code'])
        require(count <= MAX_BODY, 'response_limit')
        expected = list if operation in {'reviews', 'commits'} else dict
        require(type(frame['value']) is expected, 'invalid_ipc')
        # Independently apply raw-body limits to data crossing the private pipe.
        try:
            value = parse_json(json.dumps(frame['value'], ensure_ascii=False,
                                          separators=(',', ':'), allow_nan=False).encode('utf-8'))
            link_relations(operation, arguments, frame['link'])
        except (MetadataAPIError, ValueError, UnicodeError):
            raise MetadataAPIError('invalid_ipc') from None
        return ApiResponse(value, frame['link'], count)

    def get(self, operation, **arguments):
        route(operation, arguments)
        require(self._lock.acquire(blocking=False), 'concurrent_request')
        try:
            require(not self._cleanup_uncertain, 'cleanup_uncertain')
            require(not self._closed, 'adapter_closed')
            self._remaining(time.monotonic() + REQUEST_SECONDS)
            require(self._request_count < MAX_REQUESTS, 'request_limit')
            # Reserve a complete worst-case response before any further GET.
            require(self._response_bytes <= MAX_BYTES - MAX_BODY, 'aggregate_limit')
            deadline = min(time.monotonic() + REQUEST_SECONDS,
                           self._started + SESSION_SECONDS)
            self._reject_unsolicited()
            self._request_count += 1
            raw = json.dumps({'id': self._request_count, 'operation': operation,
                              'args': arguments, 'token': self._token},
                             ensure_ascii=False, separators=(',', ':')).encode('utf-8')
            require(len(raw) <= MAX_REQUEST, 'invalid_ipc')
            self._start()
            frame = self._exchange(raw, deadline)
            response = self._decode(frame, operation, arguments)
            self._remaining(deadline)
            self._reject_unsolicited()
            return response
        except MetadataAPIError as exc:
            # HTTP/JSON failures have closed their connection before the reply.
            recoverable = {
                'unauthorized', 'forbidden', 'not_found_or_not_visible', 'rate_limited',
                'server_error', 'unexpected_status', 'redirect_rejected', 'invalid_json',
                'duplicate_json_key', 'nonfinite_json', 'json_depth_limit',
                'json_object_limit', 'json_array_limit', 'json_string_limit',
                'json_integer_limit', 'invalid_response_shape', 'invalid_headers', 'invalid_link',
            }
            if exc.code not in recoverable:
                self._cleanup()
            raise
        except BaseException as exc:
            self._cleanup()
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            raise MetadataAPIError('worker_failed') from None
        finally:
            self._lock.release()

    def _cleanup(self):
        if self._cleanup_uncertain:
            raise CleanupUncertain()
        self._closed = True
        self._token = None
        process = self._process
        if process is None:
            return
        deadline = min(time.monotonic() + TEARDOWN_SECONDS,
                       self._started + SESSION_SECONDS + TEARDOWN_SECONDS)
        failed = False
        for pipe in (process.stdin, process.stdout):
            try:
                pipe.close()
            except BaseException:
                failed = True
        try:
            if process.poll() is None:
                try:
                    process.terminate()
                    process.wait(timeout=max(0, min(1.0, deadline - time.monotonic())))
                except BaseException:
                    # Even a failed terminate must not prevent a kill/reap attempt.
                    pass
                if process.poll() is None:
                    process.kill()
            process.wait(timeout=max(0, deadline - time.monotonic()))
            require(process.poll() is not None and time.monotonic() <= deadline,
                    'cleanup_uncertain')
        except BaseException:
            failed = True
        if failed:
            self._cleanup_uncertain = True
            raise CleanupUncertain() from None
        self._process = None

    def close(self):
        require(self._lock.acquire(blocking=False), 'concurrent_request')
        try:
            self._cleanup()
        finally:
            self._lock.release()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
