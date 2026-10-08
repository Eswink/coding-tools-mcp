"""Six fixed Git reads under caller controls; Linux, no concurrent writers.

Controlled artifact validation retains the caller deadline and cancellation.
This is trusted-native Git containment, not a native-code sandbox.
"""
import hashlib
import os
from pathlib import Path
import re
import selectors
import stat
import subprocess
import time

from rc_consumer_io import ConsumerError, _check_budget, need

BINARY = '/usr/bin/git'
CONFIG_LIMIT = 64 * 1024
INDEX_LIMIT = 64 * 1024 * 1024
INDEX_OUTPUT_LIMIT = 16 * 1024 * 1024
STATUS_LIMIT = 16 * 1024 * 1024
FILES_LIMIT = 16 * 1024 * 1024
READ_SIZE = 64 * 1024
WAIT = 0.025
CLEANUP_SECONDS = 2.0
MAX_METADATA_ENTRIES = 262144
MAX_OPEN_FDS = 1024
MAX_PATH_BYTES = 4096
MAX_DEPTH = 64
ENV = dict(PATH='/usr/bin:/bin', LANG='C', LC_ALL='C',
           GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null',
           GIT_CONFIG_SYSTEM='/dev/null', GIT_NO_REPLACE_OBJECTS='1', GIT_ATTR_NOSYSTEM='1',
           GIT_OPTIONAL_LOCKS='0', GIT_TERMINAL_PROMPT='0',
           GIT_ALLOW_PROTOCOL='', GIT_PROTOCOL_FROM_USER='0',
           GIT_CEILING_DIRECTORIES='/', GIT_DISCOVERY_ACROSS_FILESYSTEM='0')
PREFIX = ('--no-pager', '--no-replace-objects', '--no-optional-locks', '--no-lazy-fetch')
OVERRIDES = ('-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false',
             '-c', 'core.untrackedCache=false', '-c', 'credential.helper=',
             '-c', 'protocol.allow=never')
OPERATIONS = {
    ('rev-parse', 'HEAD'): ('head', 41),
    ('status', '--porcelain', '--untracked-files=all'): ('status', STATUS_LIMIT),
    ('rev-parse', 'HEAD^{tree}'): ('tree', 41),
    ('ls-files',): ('files', FILES_LIMIT),
}
BOOL_KEYS = frozenset((b'core.filemode', b'core.ignorecase', b'core.symlinks',
                       b'core.logallrefupdates'))
ROOT_NAMES = frozenset(('HEAD', 'config', 'index', 'objects', 'refs', 'info', 'hooks',
    'logs', 'branches', 'description', 'packed-refs', 'shallow', 'FETCH_HEAD',
    'ORIG_HEAD', 'COMMIT_EDITMSG'))
DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
FILE = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK


def _identity(info):
    stable = info.st_dev, info.st_ino, info.st_mode, info.st_uid
    return stable if stat.S_ISDIR(info.st_mode) else (*stable, info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _git_available(condition):
    if not condition:
        from exact_build_audit import EvidenceError
        raise EvidenceError('git_identity_unavailable')


def _config(raw):
    need(not raw or raw.endswith(b'\0'), 'unsupported_git_configuration')
    values = {}
    for record in raw.split(b'\0')[:-1]:
        key, separator, value = record.partition(b'\n')
        need(separator and key not in values, 'unsupported_git_configuration')
        values[key] = value
        valid = key in BOOL_KEYS and value in (b'true', b'false')
        valid |= key == b'core.repositoryformatversion' and value == b'0'
        valid |= key == b'core.bare' and value == b'false'
        if key in (b'user.name', b'user.email', b'remote.origin.url'):
            valid |= 0 < len(value) <= 4096 and all(32 <= byte < 127 for byte in value)
        if key == b'remote.origin.fetch':
            valid |= value == b'+refs/heads/*:refs/remotes/origin/*'
        branch = re.fullmatch(rb'branch\.([A-Za-z0-9_-][A-Za-z0-9_./-]{0,127})\.(remote|merge)', key)
        if branch and b'..' not in branch[1] and b'//' not in branch[1]:
            valid |= branch[2] == b'remote' and value == b'origin'
            valid |= branch[2] == b'merge' and re.fullmatch(rb'refs/heads/[A-Za-z0-9_-][A-Za-z0-9_./-]{0,127}', value) is not None and b'..' not in value and b'//' not in value
        need(valid, 'unsupported_git_configuration')
    need(values.get(b'core.repositoryformatversion') == b'0' and values.get(b'core.bare') == b'false',
         'unsupported_git_configuration')


def _index(raw):
    need(not raw or raw.endswith(b'\0'), 'unsupported_git_index')
    for row in raw.split(b'\0')[:-1]:
        header, separator, name = row.partition(b'\t')
        match = re.fullmatch(rb'(100644|100755|120000) ([0-9a-f]{40}) 0', header)
        need(match and separator and name and len(name) <= MAX_PATH_BYTES and
             not name.startswith(b'/') and all(p not in (b'', b'.', b'..') for p in name.split(b'/')),
             'unsupported_git_index')


class Reader:
    """Internal owner. Callers cannot choose an executable, environment or policy."""
    def __init__(self, root, *, deadline=None, check_active=None):
        self.root = Path(root).absolute()
        self.deadline, self.check_active = deadline, check_active
        self.fds, self.bindings = [], []
        self.process = self.selector = None
        self.closed = self.uncertain = False
        self.entries = 0
        self.retained = []
        self.binary_digest = None

    def check(self):
        _check_budget(self.deadline, self.check_active)

    def _opened(self, name, flags, parent=None, *, owner=None, limit=None):
        need(len(self.fds) < MAX_OPEN_FDS, 'unsupported_git_metadata')
        fd = os.open(name, flags, dir_fd=parent)
        self.fds.append(fd)  # Ownership precedes every fallible check/callback.
        info = os.fstat(fd)
        need((owner is None or info.st_uid == owner) and not info.st_mode & 0o022,
             'unsupported_git_metadata')
        if flags == FILE:
            need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and
                 (limit is None or info.st_size <= limit), 'unsupported_git_metadata')
        self.bindings.append((parent, name, fd, _identity(info)))
        self.check()
        return fd

    def _path(self, path, *, trusted=False):
        text = os.fspath(path)
        need(text.startswith('/') and len(os.fsencode(text)) <= MAX_PATH_BYTES and
             all(p not in ('.', '..') for p in text.split('/')), 'unsupported_git_metadata')
        pieces = [p for p in text.split('/') if p]
        need(len(pieces) <= MAX_DEPTH, 'unsupported_git_metadata')
        fd = self._opened('/', DIR, owner=0 if trusted else None)
        for part in pieces:
            # /tmp may be writable; only root-owned binary parents must be immutable.
            if not trusted:
                need(len(self.fds) < MAX_OPEN_FDS, 'unsupported_git_metadata')
                child = os.open(part, DIR, dir_fd=fd)
                self.fds.append(child)
                info = os.fstat(child)
                self.bindings.append((fd, part, child, _identity(info)))
                fd = child
                self.check()
            else:
                fd = self._opened(part, DIR, fd, owner=0)
        return fd

    def _names(self, fd):
        result = []
        entries = os.scandir(fd)
        try:
            for entry in entries:
                self.entries += 1
                need(self.entries <= MAX_METADATA_ENTRIES and
                     len(os.fsencode(entry.name)) <= 255, 'unsupported_git_metadata')
                result.append(entry.name)
                self.check()
        finally:
            try:
                entries.close()
            except BaseException:
                self.retained.append(entries)
                self.uncertain = True
                raise ConsumerError('transport_cleanup_uncertain') from None
        return result

    def _scan(self, fd, relative, depth=0):
        need(depth <= MAX_DEPTH, 'unsupported_git_metadata')
        for name in self._names(fd):
            path = relative + '/' + name
            need(len(os.fsencode(path)) <= MAX_PATH_BYTES, 'unsupported_git_metadata')
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            need(info.st_uid == os.geteuid() and not info.st_mode & 0o022,
                 'unsupported_git_metadata')
            if stat.S_ISDIR(info.st_mode):
                if relative == 'objects':
                    need(name in ('info', 'pack') or re.fullmatch('[0-9a-f]{2}', name), 'unsupported_git_metadata')
                else:
                    need(relative.startswith(('refs', 'logs', 'hooks', 'branches')),
                         'unsupported_git_metadata')
                child = self._opened(name, DIR, fd, owner=os.geteuid())
                self._scan(child, path, depth + 1)
            else:
                need(relative != 'objects', 'unsupported_git_metadata')
                limit = 4096 if relative.startswith('refs') else 64 * 1024 * 1024
                if relative == 'objects/pack':
                    need(re.fullmatch(r'pack-[0-9a-f]{40}\.(pack|idx|rev|bitmap|keep)', name) or
                         name == 'multi-pack-index', 'unsupported_git_metadata')
                    limit = 1024 * 1024 * 1024 if name.endswith('.pack') else limit
                elif relative == 'objects/info':
                    need(name in ('packs', 'commit-graph'), 'unsupported_git_metadata')
                elif relative.startswith('objects/'):
                    need(re.fullmatch(r'objects/[0-9a-f]{2}/[0-9a-f]{38}', path), 'unsupported_git_metadata')
                elif relative == 'info':
                    need(name in ('exclude', 'attributes'), 'unsupported_git_metadata')
                need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= limit,
                     'unsupported_git_metadata')
                # Retain identities, not one descriptor for every object/loose ref.
                self.bindings.append((fd, name, None, _identity(info)))
                self.check()

    def _binary_hash(self):
        digest, offset = hashlib.sha256(), 0
        while True:
            block = os.pread(self.binary_fd, READ_SIZE, offset)
            if not block:
                return digest.digest()
            offset += len(block)
            need(offset <= 64 * 1024 * 1024, 'unsupported_git_binary')
            digest.update(block)
            self.check()

    def _recheck(self):
        for parent, name, fd, expected in self.bindings:
            need(_identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) == expected and
                 (fd is None or _identity(os.fstat(fd)) == expected), 'unsupported_git_metadata')
            self.check()

        need(self._binary_hash() == self.binary_digest, 'unsupported_git_binary')

    def __enter__(self):
        try:
            self.check()
            binary_parent = self._path('/usr/bin', trusted=True)
            self.binary_fd = self._opened('git', FILE, binary_parent, owner=0, limit=64 * 1024 * 1024)
            need(os.pread(self.binary_fd, 4, 0) == b'\x7fELF' and os.fstat(self.binary_fd).st_mode & 0o111,
                 'unsupported_git_binary')
            self.binary_digest = self._binary_hash()
            self.cwd_fd = self._path('/')
            need(not os.path.lexists('/.git'), 'unsupported_git_metadata')
            self.root_fd = self._path(self.root)
            need(os.fstat(self.root_fd).st_uid == os.geteuid() and not os.fstat(self.root_fd).st_mode & 0o022,
                 'unsupported_git_metadata')
            self.git_fd = self._opened('.git', DIR, self.root_fd, owner=os.geteuid())
            names = self._names(self.git_fd)
            need(set(names) <= ROOT_NAMES and {'HEAD', 'config', 'index', 'objects', 'refs'} <= set(names),
                 'unsupported_git_metadata')
            for name in names:
                if name in ('objects', 'refs', 'info', 'hooks', 'logs', 'branches'):
                    fd = self._opened(name, DIR, self.git_fd, owner=os.geteuid())
                    self._scan(fd, name)
                else:
                    cap = CONFIG_LIMIT if name == 'config' else INDEX_LIMIT if name == 'index' else 4096 if name == 'HEAD' else 4 * 1024 * 1024
                    fd = self._opened(name, FILE, self.git_fd, owner=os.geteuid(), limit=cap)
                    if name == 'config':
                        self.config_fd = fd
            _config(self._run('config', CONFIG_LIMIT))
            self.check()
            return self
        except BaseException:
            self.close()
            raise

    def _argv(self, kind):
        if kind == 'config':
            return [BINARY, *PREFIX, 'config', '--null', '--no-includes',
                    f'--file=/proc/self/fd/{self.config_fd}', '--list']
        command = {'head': ('rev-parse', 'HEAD'), 'tree': ('rev-parse', 'HEAD^{tree}'),
                   'index': ('ls-files', '--stage', '-z', '--no-recurse-submodules'),
                   'status': ('status', '--porcelain', '--untracked-files=all'), 'files': ('ls-files',)}[kind]
        return [BINARY, *PREFIX, f'--git-dir=/proc/self/fd/{self.git_fd}',
                f'--work-tree=/proc/self/fd/{self.root_fd}', *OVERRIDES, *command]

    def _run(self, kind, cap):
        need(not self.closed and not self.uncertain, 'transport_cleanup_uncertain')
        self._recheck()
        self.check()
        payload, eof, failed = bytearray(), False, None
        try:
            inherited = (self.config_fd,) if kind == 'config' else (self.root_fd, self.git_fd)
            self.process = subprocess.Popen(self._argv(kind), cwd='/', env=dict(ENV),
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                shell=False, close_fds=True, pass_fds=inherited, bufsize=0)
            self.check()
            os.set_blocking(self.process.stdout.fileno(), False)
            self.selector = selectors.DefaultSelector()
            self.selector.register(self.process.stdout, selectors.EVENT_READ)
            while True:
                if eof:
                    code = self.process.poll()
                    if code is not None:
                        _git_available(code == 0)
                        break
                self.check()
                events = self.selector.select(WAIT)
                for _, _ in events:
                    try:
                        block = os.read(self.process.stdout.fileno(), min(READ_SIZE, cap + 1 - len(payload)))
                    except BlockingIOError:
                        continue
                    if not block:
                        self.selector.unregister(self.process.stdout)
                        eof = True
                        break
                    payload.extend(block)
                    need(len(payload) <= cap, 'git_output_limit_exceeded')
                # EOF+nonzero exit is already a local failure before another poll.
                if eof and self.process.poll() is not None:
                    _git_available(self.process.returncode == 0)
                    break
                self.check()
        except BaseException as error:
            failed = error
        finally:
            self._dispose()
        if failed is not None:
            raise failed
        return bytes(payload)

    def read(self, *args):
        need(args in OPERATIONS, 'unsupported_git_operation')
        if args[0] == 'status':
            _index(self._run('index', INDEX_OUTPUT_LIMIT))
            self.check()
        kind, cap = OPERATIONS[args]
        raw = self._run(kind, cap)
        if kind in ('head', 'tree'):
            _git_available(re.fullmatch(rb'[0-9a-f]{40}\n', raw))
        return raw.decode().strip()

    def _dispose(self):
        failed = False
        selector, self.selector = self.selector, None
        if selector is not None:
            try:
                selector.close()
            except BaseException:
                self.retained.append(selector)
                failed = True
        process, self.process = self.process, None
        if process is not None:
            stream, process.stdout = process.stdout, None
            if stream is not None:
                try:
                    stream.close()  # bufsize=0: one owned, unbuffered FileIO close.
                except BaseException:
                    failed = True
                    self.retained.append(stream)
            try:
                alive = process.poll() is None
            except BaseException:
                alive, failed = True, True
            if alive:
                limit = time.monotonic() + CLEANUP_SECONDS
                try:
                    process.terminate()
                except BaseException:
                    failed = True
                try:
                    process.wait(timeout=min(0.25, max(0, limit - time.monotonic())))
                except subprocess.TimeoutExpired:
                    pass
                except BaseException:
                    failed = True
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
                    process.wait(timeout=max(0, limit - time.monotonic()))
                    need(process.returncode is not None and time.monotonic() <= limit,
                         'transport_cleanup_uncertain')
                except BaseException:
                    failed = True
            else:
                try:
                    process.wait(timeout=0)
                except BaseException:
                    failed = True
        if failed and process is not None:
            self.retained.append(process)
        self.uncertain |= failed
        need(not self.uncertain, 'transport_cleanup_uncertain')

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self._dispose()
        except BaseException:
            self.uncertain = True
        while self.fds:
            fd = self.fds.pop()
            try:
                os.close(fd)
            except BaseException:
                self.uncertain = True
        need(not self.uncertain, 'transport_cleanup_uncertain')

    def __exit__(self, *_):
        self.close()
