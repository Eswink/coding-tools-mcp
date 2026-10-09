"""Narrow role-file primitive. No sudo or system write occurs on import.

The controller launches fixed sealed source via Python -I -S -c, never a
mutable runner script under sudo. Ordinary controls use owned directory FDs.
UNKNOWN close holders retain actual objects; no retry or unlink is permitted.
"""
import hashlib
import json
import os
import stat

MAX_ELF = 64 * 1024 * 1024
UNKNOWN = []
TARGET = '/usr/local/bin/git'


class HeldFD:
    def __init__(self, fd):
        self.fd = fd
        self.state = 'OPEN'
        self.unknown_fd = None

    def close(self):
        if self.state != 'OPEN':
            raise ValueError('Close already attempted')
        fd = self.fd
        self.fd = None
        self.unknown_fd = fd
        self.state = 'UNKNOWN'
        UNKNOWN.append(self)
        os.close(fd)
        self.state = 'CLOSED'
        self.unknown_fd = None
        UNKNOWN.remove(self)


def parent_identity(fd):
    s = os.fstat(fd)
    if not stat.S_ISDIR(s.st_mode):
        raise ValueError('Directory FD required')
    return [s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_nlink]


def file_identity(fd):
    s = os.fstat(fd)
    if not stat.S_ISREG(s.st_mode):
        raise ValueError('Regular source required')
    return [s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid,
            s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns]


def digest_fd(fd, expected_bytes):
    if type(expected_bytes) is not int or not 0 < expected_bytes <= MAX_ELF:
        raise ValueError('Native binary byte bound')
    os.lseek(fd, 0, os.SEEK_SET)
    h = hashlib.sha256()
    total = 0
    magic = b''
    while total <= expected_bytes:
        chunk = os.read(fd, min(65536, expected_bytes + 1 - total))
        if not chunk:
            break
        if not magic:
            magic = chunk[:4]
        total += len(chunk)
        h.update(chunk)
    if total != expected_bytes or magic != b'\x7fELF':
        raise ValueError('Exact native ELF payload required')
    return h.hexdigest()


def copy_elf_role_at(source_fd, parent_fd, expected_parent, expected_source,
                     expected_bytes, expected_sha, expected_uid):
    """Copy to new literal leaf git; caller owns and later closes the input FDs.

    Input FD provenance and permissions are checked by the fixed installer.
    Primitive controls cannot establish signed-source/build provenance alone.
    """
    if parent_identity(parent_fd) != expected_parent:
        raise ValueError('Parent identity mismatch')
    if file_identity(source_fd) != expected_source:
        raise ValueError('Source identity mismatch')
    if digest_fd(source_fd, expected_bytes) != expected_sha:
        raise ValueError('Source digest mismatch')
    target = None
    primary = None
    result = None
    try:
        target = HeldFD(os.open('git', os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW |
                                os.O_RDWR | os.O_CLOEXEC, 0o755, dir_fd=parent_fd))
        os.lseek(source_fd, 0, os.SEEK_SET)
        total = 0
        while total < expected_bytes:
            chunk = os.read(source_fd, min(65536, expected_bytes - total))
            if not chunk:
                raise ValueError('Source shortened')
            view = memoryview(chunk)
            while view:
                n = os.write(target.fd, view)
                if type(n) is not int or not 0 < n <= len(view):
                    raise ValueError('Incomplete native write')
                view = view[n:]
            total += len(chunk)
        os.fsync(target.fd)
        s = os.fstat(target.fd)
        if (not stat.S_ISREG(s.st_mode) or stat.S_IMODE(s.st_mode) != 0o755
                or s.st_nlink != 1 or s.st_uid != expected_uid
                or s.st_size != expected_bytes):
            raise ValueError('New role native policy mismatch')
        if digest_fd(target.fd, expected_bytes) != expected_sha:
            raise ValueError('Copied ELF digest mismatch')
        if (file_identity(source_fd) != expected_source
                or digest_fd(source_fd, expected_bytes) != expected_sha
                or parent_identity(parent_fd) != expected_parent):
            raise ValueError('Source or parent changed')
        os.fsync(parent_fd)
        result = {'status': 'CREATED_ROLE_ONLY', 'bytes': expected_bytes,
                  'sha256': expected_sha, 'close_state': 'PENDING',
                  'publisher_authority': False}
    except BaseException as error:
        primary = error
    errors = []
    if target is not None:
        try:
            target.close()
        except BaseException as error:
            errors.append(error)
    try:
        if parent_identity(parent_fd) != expected_parent:
            raise ValueError('Final parent changed')
    except BaseException as error:
        errors.append(error)
    if errors:
        raise BaseExceptionGroup('Role primary and cleanup failures',
                                 ([primary] if primary is not None else []) + errors)
    if primary is not None:
        raise primary
    result['close_state'] = 'CLOSED'
    return result


def _path_fds(path, resources):
    if type(path) is not str or not path.startswith('/') or '\x00' in path:
        raise ValueError('Literal absolute directory required')
    parts = path.split('/')[1:]
    if any(not x or x in ('.', '..') for x in parts):
        raise ValueError('Canonical path required')
    fd = HeldFD(os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW |
                        os.O_CLOEXEC))
    resources.append(fd)
    for part in parts:
        fd = HeldFD(os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW |
                            os.O_CLOEXEC, dir_fd=fd.fd))
        resources.append(fd)
    return fd


def validate_role_install_request(request):
    keys = {'schema', 'runner_temp', 'source_relative', 'source_identity',
            'source_bytes', 'source_sha256', 'target_parent', 'caller_uid'}
    if type(request) is not dict or set(request) != keys:
        raise ValueError('Exact request schema required')
    if request['schema'] != 'rc070-single-git-role-1':
        raise ValueError('Role schema mismatch')
    root, relative = request['runner_temp'], request['source_relative']
    if (type(root) is not str or not root.startswith('/') or root in ('/', '/usr', '/usr/local')
            or type(relative) is not str or relative.startswith('/')
            or any(x in ('', '.', '..') for x in relative.split('/'))
            or not relative.endswith('/owned-prefix/bin/git')):
        raise ValueError('Owned source path policy')
    if (type(request['caller_uid']) is not int or request['caller_uid'] <= 0
            or type(request['source_bytes']) is not int
            or not 0 < request['source_bytes'] <= MAX_ELF
            or type(request['source_sha256']) is not str
            or len(request['source_sha256']) != 64
            or any(c not in '0123456789abcdef' for c in request['source_sha256'])):
        raise ValueError('Typed role request required')
    for key, size in [('source_identity', 9), ('target_parent', 6)]:
        if (type(request[key]) is not list or len(request[key]) != size
                or any(type(x) is not int for x in request[key])):
            raise ValueError('Native identity vector mismatch')
    return request


def install_disposable_git_role(request):
    """Fixed target, one fresh ELF only; privileged invocation must be reviewed."""
    r = validate_role_install_request(request)
    resources, primary, result = [], None, None
    try:
        if os.geteuid() == 0:
            if os.environ.get('SUDO_UID') != str(r['caller_uid']):
                raise ValueError('Actual sudo caller mismatch')
        elif os.geteuid() != r['caller_uid']:
            raise ValueError('Actual caller mismatch')
        root = _path_fds(r['runner_temp'], resources)
        root_info = os.fstat(root.fd)
        if root_info.st_uid != r['caller_uid'] or root_info.st_mode & 0o022:
            raise ValueError('Owned private temp root required')
        parent_relative, leaf = r['source_relative'].rsplit('/', 1)
        current = root
        for component in parent_relative.split('/'):
            current = HeldFD(os.open(component, os.O_RDONLY | os.O_DIRECTORY |
                                    os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=current.fd))
            resources.append(current)
            if os.fstat(current.fd).st_uid != r['caller_uid']:
                raise ValueError('Foreign owned prefix component')
        source = HeldFD(os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                dir_fd=current.fd))
        resources.append(source)
        if (file_identity(source.fd) != r['source_identity']
                or os.fstat(source.fd).st_uid != r['caller_uid']):
            raise ValueError('Genuine current source FD mismatch')
        target = _path_fds('/usr/local/bin', resources)
        for lease in resources[-4:]:
            info = os.fstat(lease.fd)
            if info.st_uid != 0 or info.st_mode & 0o022:
                raise ValueError('Root directory policy mismatch')
        result = copy_elf_role_at(source.fd, target.fd, r['target_parent'],
                                  r['source_identity'], r['source_bytes'],
                                  r['source_sha256'], os.geteuid())
    except BaseException as error:
        primary = error
    errors = []
    for resource in reversed(resources):
        try:
            resource.close()
        except BaseException as error:
            errors.append(error)
    if errors:
        raise BaseExceptionGroup('Installer primary and cleanup failures',
                                 ([primary] if primary is not None else []) + errors)
    if primary is not None:
        raise primary
    return result
