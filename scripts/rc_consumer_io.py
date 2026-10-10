"""Private, nofollow data I/O for the nonpublishing FINAL consumer (POSIX only)."""
from __future__ import annotations
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import stat
import time
import unicodedata

CHUNK = 64 * 1024
JSON_LIMIT = 16_000_000 - 1
FILE_LIMIT = 512 * 1024**2
PATH_LIMIT = 1024
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


class ConsumerError(ValueError):
    """Only fixed, bounded codes cross the public error boundary."""
    def __init__(self, code):
        self.code = code if type(code) is str and re.fullmatch(r'[a-z][a-z0-9_]{0,95}', code) else 'consumer_validation_failed'
        super().__init__(self.code)


def need(condition, code):
    if not condition:
        raise ConsumerError(code)


def safe_relative(name: str, *, directory=False) -> str:
    need(type(name) is str and bool(name), 'unsafe_path')
    try:
        encoded = name.encode('utf-8', errors='strict')
    except UnicodeError:
        raise ConsumerError('unsafe_path') from None
    need(len(encoded) <= PATH_LIMIT and not any(unicodedata.category(c).startswith('C') for c in name)
         and '\\' not in name and ':' not in name, 'unsafe_path')
    if directory and name.endswith('/'):
        name = name[:-1]
    need(bool(name) and all(p not in {'', '.', '..'} for p in name.split('/')), 'unsafe_path')
    return name


def _absolute(path) -> str:
    value = os.fspath(path)
    need(type(value) is str and value.startswith('/') and '\x00' not in value
         and all(p not in {'.', '..'} for p in value.split('/')), 'unsafe_absolute_path')
    return value.rstrip('/') or '/'


def _directory(path) -> int:
    """Walk from / using dirfds, never resolving any symlink component."""
    path = _absolute(path)
    fd = os.open('/', DIR_FLAGS)
    try:
        for part in path.split('/')[1:]:
            if not part:
                continue
            new = os.open(part, DIR_FLAGS, dir_fd=fd)
            previous, fd = fd, new
            os.close(previous)
        return fd
    except BaseException:
        closing, fd = fd, None
        os.close(closing)
        raise


@contextmanager
def open_file(path):
    """Open an existing regular, single-link file with every parent nofollow."""
    fd = None
    try:
        value = _absolute(path)
        parent, name = value.rsplit('/', 1)
        parent_fd = _directory(parent or '/')
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=parent_fd)
        finally:
            os.close(parent_fd)
        info = os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, 'nonregular_file')
        stream = os.fdopen(fd, 'rb')
        fd = None
        with stream:
            yield stream
    except OSError:
        raise ConsumerError('unsafe_file_io') from None
    finally:
        if fd is not None:
            os.close(fd)


def _check_budget(deadline, check_active):
    """Check caller-owned controls without renewing a budget or exposing errors."""
    if deadline is None and check_active is None:
        return
    need(deadline is None or type(deadline) is int or
         (type(deadline) is float and math.isfinite(deadline)), 'invalid_transport_deadline')
    need(check_active is None or callable(check_active), 'artifact_transport_failed')
    if deadline is not None:
        need(time.monotonic() < deadline, 'transport_deadline_exceeded')
    if check_active is None:
        return
    code, cancellation = None, None
    try:
        if check_active() is not None:
            code = 'artifact_transport_failed'
    except KeyboardInterrupt:
        cancellation = KeyboardInterrupt
    except SystemExit:
        cancellation = SystemExit
    except BaseException as error:
        code = 'artifact_transport_failed'
        try:
            value = error.code
            if type(value) is str:
                code = {'cancelled': 'transport_cancelled',
                        'timeout': 'transport_deadline_exceeded'}.get(value, code)
        except BaseException:
            pass
    if cancellation is SystemExit:
        raise SystemExit(1)
    if cancellation:
        raise KeyboardInterrupt()
    if code:
        raise ConsumerError(code)
    if deadline is not None:
        need(time.monotonic() < deadline, 'transport_deadline_exceeded')


def hash_file(path, *, deadline=None, check_active=None) -> str:
    _check_budget(deadline, check_active)
    with open_file(path) as stream:
        need(os.fstat(stream.fileno()).st_size <= FILE_LIMIT, 'file_size_limit')
        digest = hashlib.sha256()
        total = 0
        while True:
            _check_budget(deadline, check_active)
            data = stream.read(CHUNK)
            if data:
                total += len(data)
                need(total <= FILE_LIMIT, 'file_size_limit')
            _check_budget(deadline, check_active)
            if not data:
                break
            digest.update(data)
        result = digest.hexdigest()
    _check_budget(deadline, check_active)
    return result


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, 'duplicate_json_key')
        result[key] = value
    return result


def _finite(text):
    value = float(text)
    need(math.isfinite(value), 'nonfinite_json_number')
    return value


def json_file(path) -> dict:
    with open_file(path) as stream:
        need(os.fstat(stream.fileno()).st_size <= JSON_LIMIT, 'json_size_limit')
        data = stream.read(JSON_LIMIT + 1)
    need(len(data) <= JSON_LIMIT, 'json_size_limit')
    try:
        value = json.loads(data.decode('utf-8-sig'), object_pairs_hook=_pairs,
                           parse_float=_finite, parse_constant=lambda _: need(False, 'nonfinite_json_number'))
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as error:
        if isinstance(error, ConsumerError):
            raise
        raise ConsumerError('invalid_json') from None
    need(type(value) is dict, 'json_object_required')
    return value


class PrivateRoot:
    """New owner-only root; dirfds and inode checks reject replacements/races.

    Payloads stay 0600. The path is exposed solely for unchanged reviewed helpers;
    callers must not run concurrent writers or delegate this private directory.
    """
    def __init__(self, parent, prefix='rc-consumer-', *, source_root=None, _stage_owner=None):
        self.fd = None
        self.path = None
        self._dirs = {}
        self._files = {}
        self._stage_owner = owner = _stage_owner
        if owner is not None:
            from rc_publication_retirement import StageRootOwner
            need(type(owner) is StageRootOwner, 'invalid_stage_owner')
            owner.attach(self)
        close = self._retirement_close
        parent = _absolute(parent)
        source = _absolute(source_root or Path(__file__).absolute().parents[1])
        need(os.path.commonpath((source, parent)) != source, 'root_inside_source')
        need(type(prefix) is str and re.fullmatch(r'[A-Za-z0-9_-]{1,64}', prefix), 'invalid_root_prefix')
        parent_fd = root_fd = None
        try:
            try:
                parent_fd = _directory(parent)
                # Nofollow traversal makes lexical and actual ancestry identical.
                need(os.path.realpath(parent) == parent, 'unsafe_root_parent')
                name = prefix + secrets.token_hex(16)
                if owner is not None:
                    owner.parent(parent_fd, name)
                os.mkdir(name, 0o700, dir_fd=parent_fd)
                root_fd = os.open(name, DIR_FLAGS, dir_fd=parent_fd)
                self.path = Path(parent) / name
                self._dirs[''] = self._identity(root_fd)
                if owner is not None:
                    owner.directory('', root_fd, parent_fd, name)
                closing, parent_fd = parent_fd, None
                close(closing)
                self.fd, root_fd = root_fd, None
            finally:
                try:
                    if root_fd is not None:
                        closing, root_fd = root_fd, None
                        close(closing)
                finally:
                    if parent_fd is not None:
                        closing, parent_fd = parent_fd, None
                        close(closing)
        except OSError:
            if owner is not None:
                owner.uncertain = True
            raise ConsumerError('unsafe_root_parent') from None

    @staticmethod
    def _identity(fd):
        info = os.fstat(fd)
        need(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
             and stat.S_IMODE(info.st_mode) == 0o700, 'unsafe_private_directory')
        return info.st_dev, info.st_ino

    def _root(self):
        need(self.fd is not None, 'private_root_closed')
        fd = None
        try:
            fd = _directory(self.path)
            need(self._identity(fd) == self._dirs[''], 'private_root_replaced')
            return fd
        except BaseException:
            if fd is not None:
                self._retirement_close(fd)
            elif getattr(self, '_stage_owner', None) is not None:
                self._stage_owner.uncertain = True
            raise

    def _parent(self, name, create=False):
        owner = getattr(self, '_stage_owner', None)
        close = self._retirement_close
        parts = safe_relative(name).split('/')
        fd = self._root()
        walked = []
        try:
            for part in parts[:-1]:
                walked.append(part)
                relative = '/'.join(walked)
                if relative not in self._dirs:
                    need(create, 'unknown_private_directory')
                    if owner is not None:
                        owner.reserve(relative, 'directory')
                    os.mkdir(part, 0o700, dir_fd=fd)
                    child = os.open(part, DIR_FLAGS, dir_fd=fd)
                    try:
                        self._dirs[relative] = self._identity(child)
                        if owner is not None:
                            owner.directory(relative, child, fd, part)
                    except BaseException:
                        closing, child = child, None
                        close(closing)
                        raise
                else:
                    child = os.open(part, DIR_FLAGS, dir_fd=fd)
                    try:
                        need(self._identity(child) == self._dirs[relative], 'private_directory_replaced')
                    except BaseException:
                        closing, child = child, None
                        close(closing)
                        raise
                previous, fd = fd, child
                close(previous)
            return fd, parts[-1]
        except BaseException:
            closing, fd = fd, None
            close(closing)
            raise

    def mkdir(self, relative):
        try:
            fd, _ = self._parent(safe_relative(relative) + '/unused', create=True)
            self._retirement_close(fd)
        except OSError:
            raise ConsumerError('unsafe_private_io') from None

    @contextmanager
    def open(self, relative, mode='rb'):
        need(mode in {'rb', 'xb'}, 'invalid_private_mode')
        owner = getattr(self, '_stage_owner', None)
        close = self._retirement_close
        fd = None
        try:
            parent, name = self._parent(relative, create=mode == 'xb')
            try:
                flags = os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
                flags |= os.O_WRONLY | os.O_CREAT | os.O_EXCL if mode == 'xb' else os.O_RDONLY
                if owner is not None and mode == 'xb':
                    owner.reserve(relative, 'file')
                fd = os.open(name, flags, 0o600, dir_fd=parent)
                if owner is not None:
                    owner.file(relative, fd, parent, name, mode)
            finally:
                close(parent)
            info = os.fstat(fd)
            need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.geteuid()
                 and stat.S_IMODE(info.st_mode) == 0o600, 'unsafe_private_file')
            identity = info.st_dev, info.st_ino
            if mode == 'xb':
                self._files[relative] = identity
            else:
                need(self._files.get(relative) == identity, 'private_file_replaced')
            stream = os.fdopen(fd, mode) if owner is None else os.fdopen(fd, mode, closefd=False)
            owned, fd = fd, None
            context = stream
            if owner is not None:
                try:
                    context = owner.stream(stream, owned)
                except BaseException:
                    owner.close_stream(stream, owned)
                    raise
            with context:
                yield stream
                if mode == 'xb':
                    stream.flush()
                    os.fsync(stream.fileno())
        except OSError:
            raise ConsumerError('unsafe_private_io') from None
        finally:
            if fd is not None:
                close(fd)

    def read(self, relative, limit=JSON_LIMIT):
        need(type(limit) is int and 0 <= limit <= FILE_LIMIT, 'invalid_read_limit')
        with self.open(relative) as stream:
            need(os.fstat(stream.fileno()).st_size <= limit, 'private_read_limit')
            data = stream.read(limit + 1)
        need(len(data) <= limit, 'private_read_limit')
        return data

    def write(self, relative, data):
        need(type(data) is bytes and len(data) <= FILE_LIMIT, 'private_write_limit')
        with self.open(relative, 'xb') as stream:
            stream.write(data)
        return self.path / relative

    def copy(self, relative, source_path, *, deadline=None, check_active=None):
        _check_budget(deadline, check_active)
        total = 0
        with open_file(source_path) as source, self.open(relative, 'xb') as target:
            while True:
                _check_budget(deadline, check_active)
                data = source.read(CHUNK)
                if data:
                    total += len(data)
                    need(total <= FILE_LIMIT, 'private_copy_limit')
                _check_budget(deadline, check_active)
                if not data:
                    break
                target.write(data)
                _check_budget(deadline, check_active)
        _check_budget(deadline, check_active)
        return self.path / relative

    def files(self):
        """Check complete on-disk membership, including injected extra files."""
        found = set()
        def visit(fd, prefix):
            for name in os.listdir(fd):
                relative = prefix + name
                safe_relative(relative)
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    child = os.open(name, DIR_FLAGS, dir_fd=fd)
                    try:
                        need(self._identity(child) == self._dirs.get(relative), 'private_directory_replaced')
                        visit(child, relative + '/')
                    finally:
                        self._retirement_close(child)
                else:
                    with self.open(relative):
                        found.add(relative)
        try:
            fd = self._root()
            try:
                visit(fd, '')
            finally:
                self._retirement_close(fd)
            need(found == set(self._files), 'private_inventory_changed')
            return tuple(sorted(found))
        except OSError:
            raise ConsumerError('unsafe_private_io') from None

    def _retirement_close(self, fd):
        owner = getattr(self, '_stage_owner', None)
        return os.close(fd) if owner is None else owner.close_fd(fd)

    def close(self):
        owned, self.fd = self.fd, None
        if owned is not None:
            os.close(owned)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def read_bytes(path, limit=JSON_LIMIT):
    need(type(limit) is int and 0 <= limit <= FILE_LIMIT, 'invalid_read_limit')
    with open_file(path) as stream:
        need(os.fstat(stream.fileno()).st_size <= limit, 'file_size_limit')
        data = stream.read(limit + 1)
    need(len(data) <= limit, 'file_size_limit')
    return data


def read_prefix(path, n=20):
    need(type(n) is int and 0 <= n <= CHUNK, 'invalid_read_limit')
    with open_file(path) as stream:
        return stream.read(n)


def assert_private_tree(directory):
    """Audit paths before invoking unchanged data-only checkout validators."""
    found = []
    def visit(fd, prefix):
        PrivateRoot._identity(fd)
        for name in os.listdir(fd):
            relative = prefix + name
            safe_relative(relative)
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            need(info.st_uid == os.geteuid(), 'unsafe_private_file')
            if stat.S_ISDIR(info.st_mode):
                child = os.open(name, DIR_FLAGS, dir_fd=fd)
                try:
                    visit(child, relative + '/')
                finally:
                    os.close(child)
            else:
                need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                     and stat.S_IMODE(info.st_mode) == 0o600, 'unsafe_private_file')
                found.append(relative)
    try:
        fd = _directory(directory)
        try:
            visit(fd, '')
        finally:
            os.close(fd)
    except OSError:
        raise ConsumerError('unsafe_private_io') from None
    return tuple(sorted(found))
