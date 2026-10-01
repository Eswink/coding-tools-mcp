"""Single-attempt, exact-owned-plan withdrawal after terminal failures.

Private directories have no concurrent writers. These checks do not provide an
atomic defense against another malicious process with this invocation's UID.
"""
import hashlib
import os
import stat

from rc_consumer_io import CHUNK, DIR_FLAGS, JSON_LIMIT, ConsumerError, need

PENDING = 'rc-asset-plan.pending'
SUCCESS = 'rc-asset-plan.json'


def identity(info):
    return (info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode), info.st_nlink)


class FinalizationFailure(ConsumerError):
    def __init__(self, original, outcome):
        self.outcome = outcome
        self.plan_absent_confirmed = outcome in {'withdrawn', 'absent'}
        self.original_error_code = original.code if isinstance(original, ConsumerError) else 'operation_failed'
        code = {'withdrawn': 'plan_withdrawn_after_failure', 'absent': 'plan_absent_after_failure',
                'uncertain': 'uncertain_plan_outcome'}[outcome]
        super().__init__(code)


class PlanCommit:
    """Capture authority from invocation-created identities, never current data."""
    def __init__(self, root, expected):
        need(type(expected) is bytes and 0 < len(expected) <= JSON_LIMIT, 'invalid_pending_plan')
        need(set(root.files()) == {'RC_PROVENANCE.json', PENDING}, 'invalid_receipt_inventory')
        self.path = root.path
        self.directory_identity = identity(os.fstat(root.fd))[:4]
        need(self.directory_identity[2:] == (os.geteuid(), 0o700), 'invalid_receipt_root')
        # root.open binds to PrivateRoot's inode recorded at exclusive creation.
        with root.open(PENDING) as stream:
            info = os.fstat(stream.fileno())
            self.file_identity = identity(info)
            need(self.file_identity[2:] == (os.geteuid(), 0o600, 1)
                 and info.st_size == len(expected) and stream.read(len(expected) + 1) == expected,
                 'pending_plan_changed')
        self.expected = expected
        self.digest = hashlib.sha256(expected).hexdigest()
        self.started = False

    def commit(self, root):
        need(not self.started and root.path == self.path, 'invalid_commit_state')
        need(set(root.files()) == {'RC_PROVENANCE.json', PENDING}, 'invalid_receipt_inventory')
        need(identity(os.fstat(root.fd))[:4] == self.directory_identity, 'receipt_root_changed')
        with root.open(PENDING) as stream:
            info = os.fstat(stream.fileno())
            need(identity(info) == self.file_identity and info.st_size == len(self.expected)
                 and stream.read(len(self.expected) + 1) == self.expected, 'pending_plan_changed')
        # Any subsequent failure triggers exactly one verified withdrawal, even
        # if rename completed but an error prevented confirmation to the caller.
        self.started = True
        os.rename(PENDING, SUCCESS, src_dir_fd=root.fd, dst_dir_fd=root.fd)

    def _open_root(self):
        fd = os.open('/', DIR_FLAGS)
        try:
            for part in self.path.parts[1:]:
                child = os.open(part, DIR_FLAGS, dir_fd=fd)
                previous, fd = fd, child
                os.close(previous)  # Ownership cleared; never retry this fd.
            need(identity(os.fstat(fd))[:4] == self.directory_identity, 'withdrawal_root_changed')
            result, fd = fd, None
            return result
        finally:
            if fd is not None:
                owned, fd = fd, None
                os.close(owned)

    def withdraw(self):
        """One exact-name attempt, no fallback, recursive cleanup or replay."""
        directory, file = self._open_root(), None
        try:
            try:
                file = os.open(SUCCESS, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                               dir_fd=directory)
            except FileNotFoundError:
                return 'absent'
            info = os.fstat(file)
            need(stat.S_ISREG(info.st_mode) and identity(info) == self.file_identity
                 and info.st_size == len(self.expected), 'withdrawal_plan_changed')
            data = bytearray()
            while len(data) <= len(self.expected):
                block = os.read(file, min(CHUNK, len(self.expected) + 1 - len(data)))
                if not block:
                    break
                data.extend(block)
            need(bytes(data) == self.expected and hashlib.sha256(data).hexdigest() == self.digest,
                 'withdrawal_plan_changed')
            owned, file = file, None
            os.close(owned)  # A close failure occurs before any removal attempt.
            need(identity(os.stat(SUCCESS, dir_fd=directory, follow_symlinks=False)) == self.file_identity,
                 'withdrawal_plan_changed')
            os.unlink(SUCCESS, dir_fd=directory)
            try:
                os.stat(SUCCESS, dir_fd=directory, follow_symlinks=False)
            except FileNotFoundError:
                return 'withdrawn'
            raise ConsumerError('withdrawal_absence_unconfirmed')
        finally:
            try:
                if file is not None:
                    owned, file = file, None
                    os.close(owned)
            finally:
                owned, directory = directory, None
                os.close(owned)
