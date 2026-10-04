"""Parent-owned deadline, integrity and terminal cleanup for artifact bytes."""
from __future__ import annotations
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import struct
import subprocess
import sys
import time

from rc_consumer_io import ConsumerError, need
import rc_consumer_transport_worker as wire

REPOSITORY, API = wire.REPOSITORY, wire.API
MAX_ZIP, READ_SIZE, READ_TIMEOUT = wire.MAX_ZIP, wire.READ_SIZE, wire.READ_TIMEOUT
TOTAL_TIMEOUT = 300
CLEANUP_TIMEOUT = 5.0
# Held until separately reviewed host admission; reject before any worker starts.
TRUSTED_STORAGE_HOSTS: frozenset[str] = frozenset()
WORKER = Path(__file__).resolve().with_name('rc_consumer_transport_worker.py')
NoRedirect = wire.NoRedirect
SAFE_ERRORS = wire.ERROR_CODES | frozenset({
    'transport_deadline_exceeded', 'download_digest_mismatch',
    'unsafe_private_io', 'invalid_private_mode', 'unsafe_path', 'unsafe_absolute_path',
    'private_root_closed', 'private_root_replaced', 'unsafe_private_directory',
    'unsafe_private_file', 'unknown_private_directory', 'private_directory_replaced',
})


def _safe_code(error):
    try:
        code = error.code
        if type(code) is str and code in SAFE_ERRORS:
            return code
    except BaseException:
        pass
    return 'artifact_transport_failed'


def storage_url(value):
    code = None
    try:
        return wire.storage_url(value, TRUSTED_STORAGE_HOSTS)
    except wire.WireError as error:
        code = error.code
    raise ConsumerError(code)


def remaining(deadline, clock):
    value = deadline - clock()
    need(value > 0, 'transport_deadline_exceeded')
    return min(READ_TIMEOUT, value)


class _Download:
    def __init__(self, deadline, clock):
        self.deadline, self.clock = deadline, clock
        self.process = None
        self.uncertain = False
        self.escalated = False
        self.disposed = False

    def start(self, opener):
        if opener is None:
            self.process = subprocess.Popen(
                [sys.executable, '-B', '-I', '-S', str(WORKER)], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, shell=False,
                close_fds=True, bufsize=0, env={'LC_ALL': 'C', 'LANG': 'C'})
        else:
            # Library-only test seam. The CLI cannot supply a fixture launcher.
            self.process = opener.start_worker()
        # Take ownership immediately, even if descriptor setup subsequently fails.
        remaining(self.deadline, self.clock)
        os.set_blocking(self.process.stdin.fileno(), False)
        os.set_blocking(self.process.stdout.fileno(), False)

    def exchange(self, raw, size, digest, destination):
        process = self.process
        outgoing = struct.pack('!I', len(raw)) + raw
        sent, total = 0, 0
        received = bytearray()
        hasher = hashlib.sha256()
        ready = done = eof = False
        with ExitStack() as files, selectors.DefaultSelector() as selector:
            output = None
            selector.register(process.stdout, selectors.EVENT_READ)
            while not eof:
                wait = remaining(self.deadline, self.clock)
                events = selector.select(wait)
                remaining(self.deadline, self.clock)
                for key, _ in events:
                    if key.fileobj is process.stdin:
                        try:
                            count = os.write(process.stdin.fileno(), outgoing[sent:])
                        except BlockingIOError:
                            continue
                        need(count > 0, 'invalid_transport_ipc')
                        sent += count
                        if sent == len(outgoing):
                            selector.unregister(process.stdin)
                    else:
                        try:
                            block = os.read(process.stdout.fileno(), wire.MAX_FRAME + 4 - len(received))
                        except BlockingIOError:
                            continue
                        if not block:
                            need(done and not received, 'artifact_transport_failed')
                            eof = True
                            break
                        received.extend(block)
                        while len(received) >= 4:
                            length = struct.unpack('!I', received[:4])[0]
                            need(0 < length <= wire.MAX_FRAME, 'invalid_transport_ipc')
                            if len(received) < length + 4:
                                break
                            frame = bytes(received[4:length + 4])
                            del received[:length + 4]
                            need(not done, 'invalid_transport_ipc')
                            if not ready:
                                need(frame == b'R', 'invalid_transport_ipc')
                                ready = True
                                selector.register(process.stdin, selectors.EVENT_WRITE)
                            else:
                                need(sent == len(outgoing), 'invalid_transport_ipc')
                                if frame[:1] == b'B':
                                    chunk = frame[1:]
                                    need(bool(chunk), 'invalid_transport_ipc')
                                    total += len(chunk)
                                    need(total <= size and total <= MAX_ZIP, 'download_size_mismatch')
                                    hasher.update(chunk)
                                    if output is None:
                                        output = files.enter_context(destination.open('artifact.zip', 'xb'))
                                    remaining(self.deadline, self.clock)
                                    need(output.write(chunk) == len(chunk), 'artifact_transport_failed')
                                    remaining(self.deadline, self.clock)
                                elif frame == b'D':
                                    done = True
                                elif frame[:1] == b'E':
                                    code = frame[1:].decode('ascii')
                                    need(code in wire.ERROR_CODES, 'invalid_transport_ipc')
                                    raise ConsumerError(code)
                                else:
                                    raise ConsumerError('invalid_transport_ipc')
            need(total == size, 'download_size_mismatch')
            need('sha256:' + hasher.hexdigest() == digest, 'download_digest_mismatch')
            # This wait is still inside the one operation deadline.
            need(process.wait(timeout=remaining(self.deadline, self.clock)) == 0,
                 'artifact_transport_failed')
            remaining(self.deadline, self.clock)
        # PrivateRoot.open flushes, fsyncs and closes on context exit.
        remaining(self.deadline, self.clock)

    def cleanup(self):
        if self.uncertain:
            return False
        if self.disposed:
            return True
        self.disposed = True
        deadline = time.monotonic() + CLEANUP_TIMEOUT
        process = self.process
        if process is None:
            return True
        failed = False
        for name in ('stdin', 'stdout'):
            stream = getattr(process, name)
            setattr(process, name, None)  # Never retry a possibly retired descriptor.
            if stream is not None:
                try:
                    stream.close()
                except BaseException:
                    failed = True
        try:
            alive = process.poll() is None
        except BaseException:
            alive, failed = True, True
        if alive:
            self.escalated = True
            try:
                process.terminate()
            except BaseException:
                failed = True
            try:
                process.wait(timeout=max(0, min(1.0, (deadline - time.monotonic()) / 2)))
            except BaseException:
                pass
            try:
                alive = process.poll() is None
            except BaseException:
                alive, failed = True, True
            if alive:
                try:
                    process.kill()
                except BaseException:
                    failed = True
        try:
            process.wait(timeout=max(0, deadline - time.monotonic()))
            need(process.poll() is not None and time.monotonic() <= deadline,
                 'transport_cleanup_uncertain')
        except BaseException:
            failed = True
        self.uncertain = failed
        if not failed:
            self.process = None
        return not failed


def download_artifact_zip(api, artifact, destination, *, opener=None, clock=time.monotonic):
    """One supervised download; test-only opener launch adapters never bypass IPC.

    Synchronous OS launch/file I/O cannot be interrupted; late completion fails.
    """
    ident, size, digest = (artifact.get(k) for k in ('id', 'size_in_bytes', 'digest'))
    need(type(ident) is int and ident > 0 and type(size) is int and 0 < size <= MAX_ZIP,
         'invalid_download_metadata')
    need(type(digest) is str and re.fullmatch(r'sha256:[0-9a-f]{64}', digest) is not None,
         'invalid_download_metadata')
    need(type(api.token) is str and bool(api.token), 'missing_actions_read_token')
    need(bool(TRUSTED_STORAGE_HOSTS), 'storage_transport_unverified')
    owner = _Download(clock() + TOTAL_TIMEOUT, clock)
    code, cancellation = None, None
    try:
        need(len(api.token) <= wire.MAX_REQUEST, 'invalid_transport_ipc')
        raw = json.dumps({'id': ident, 'size': size, 'token': api.token},
                         ensure_ascii=True, separators=(',', ':')).encode('ascii')
        need(len(raw) <= wire.MAX_REQUEST, 'invalid_transport_ipc')
        owner.start(opener)
        owner.exchange(raw, size, digest, destination)
    except ConsumerError as error:
        code = _safe_code(error)
    except (KeyboardInterrupt, SystemExit) as error:
        cancellation = type(error)
    except BaseException:
        code = 'artifact_transport_failed'
    # Do not carry raw exception objects/contexts into the public error boundary.
    if not owner.cleanup():
        failure = ConsumerError('transport_cleanup_uncertain')
        failure.original_error_code = code or ('transport_cancelled' if cancellation else 'artifact_transport_failed')
        raise failure
    if cancellation is SystemExit:
        raise SystemExit(1)  # Cancellation must not turn the CLI exit status into success.
    if cancellation:
        raise cancellation()
    if code:
        raise ConsumerError(code)
    need(not owner.escalated, 'artifact_transport_failed')
    return destination.path / 'artifact.zip'
