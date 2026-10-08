"""Explicit stage-only creation ownership; callers forbid concurrent writers."""
from contextlib import contextmanager
import io
import os
import stat

from rc_consumer_io import ConsumerError, DIR_FLAGS, need, safe_relative


class StageRootOwner:
    """One constructor's private artifacts; never authority over discovered names."""
    def __init__(self):
        need(all(fn in os.supports_dir_fd for fn in (os.open, os.stat, os.unlink, os.rmdir))
             and os.stat in os.supports_follow_symlinks and os.scandir in os.supports_fd,
             'stage_retirement_unavailable')
        self.root = self.parent_fd = self.root_fd = self.name = None
        self.parent_identity = None
        self.entries, self.pending, self.active = {}, {}, set()
        self.unclosed = {}
        self.registered = self.uncertain = self.retired = False

    def attach(self, root):
        need(self.root is None and not self.retired, 'stage_owner_reused')
        self.root = root

    def parent(self, fd, name):
        need(self.parent_fd is None and self.name is None, 'stage_owner_reused')
        self.parent_fd = os.dup(fd)
        info = os.fstat(self.parent_fd)
        need(stat.S_ISDIR(info.st_mode), 'stage_retirement_failed')
        self.parent_identity, self.name = (info.st_dev, info.st_ino), name
        self.reserve('', 'directory')

    def reserve(self, relative, kind):
        need(not self.retired and relative not in self.entries and relative not in self.pending,
             'stage_entry_reused')
        if relative:
            safe_relative(relative)
        self.pending[relative] = kind

    @staticmethod
    def identity(info, kind):
        directory = kind == 'directory'
        need((stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
             and info.st_uid == os.geteuid()
             and stat.S_IMODE(info.st_mode) == (0o700 if directory else 0o600)
             and (directory or info.st_nlink == 1),
             'unsafe_private_directory' if directory else 'unsafe_private_file')
        return info.st_dev, info.st_ino

    def record(self, relative, kind, fd, parent, name):
        need(self.pending.get(relative) == kind, 'stage_entry_unowned')
        opened = self.identity(os.fstat(fd), kind)
        bound = self.identity(os.stat(name, dir_fd=parent, follow_symlinks=False), kind)
        need(opened == bound and all(row[1] != opened for row in self.entries.values()),
             'stage_retirement_failed')
        self.entries[relative] = kind, opened
        del self.pending[relative]

    def directory(self, relative, fd, parent, name):
        self.record(relative, 'directory', fd, parent, name)
        if not relative:
            self.root_fd = os.dup(fd)

    def file(self, relative, fd, parent, name, mode):
        self.active.add(fd)
        if mode == 'xb':
            self.record(relative, 'file', fd, parent, name)

    def close_fd(self, fd):
        self.active.discard(fd)
        try:
            os.close(fd)
        except BaseException:
            self.uncertain = True
            raise

    def close_stream(self, stream, fd):
        self.unclosed[fd] = stream
        try:
            need(type(stream) in (io.BufferedReader, io.BufferedWriter), 'stage_stream_uncertain')
            raw = stream.raw
            need(type(raw) is io.FileIO and raw.closefd is False
                 and (raw.closed or raw.fileno() == fd), 'stage_stream_uncertain')
            forced = False
            try:
                stream.close()
            finally:
                try:
                    if not raw.closed:
                        forced = self.uncertain = True
                        io.FileIO.close(raw)
                finally:
                    if raw.closed and stream.closed:
                        self.unclosed.pop(fd)
                        self.close_fd(fd)
                    else:
                        self.uncertain = True
            need(not forced, 'stage_stream_uncertain')
        except BaseException:
            self.uncertain = True
            raise

    @contextmanager
    def stream(self, stream, fd):
        try:
            need(fd in self.active and not self.retired, 'stage_owner_reused')
            yield stream
        finally:
            self.close_stream(stream, fd)

    def check(self, relative, info):
        row = self.entries.get(relative)
        need(row is not None and self.identity(info, row[0]) == row[1],
             'stage_retirement_failed')

    @contextmanager
    def directory_fd(self, relative):
        fd = os.dup(self.root_fd)
        try:
            self.check('', os.fstat(fd))
            walked = []
            for name in relative.split('/') if relative else ():
                walked.append(name)
                path = '/'.join(walked)
                need(self.entries.get(path, (None,))[0] == 'directory', 'stage_retirement_failed')
                self.check(path, os.stat(name, dir_fd=fd, follow_symlinks=False))
                child = os.open(name, DIR_FLAGS, dir_fd=fd)
                try:
                    self.check(path, os.fstat(child))
                except BaseException:
                    closing, child = child, None
                    self.close_fd(closing)
                    raise
                previous, fd = fd, child
                self.close_fd(previous)
            yield fd
        finally:
            closing, fd = fd, None
            self.close_fd(closing)

    def preflight(self):
        need(not self.uncertain and not self.pending and not self.active and not self.unclosed,
             'stage_retirement_failed')
        if self.parent_fd is None:
            need(not self.entries and self.root_fd is None, 'stage_retirement_failed')
            return
        need(self.root_fd is not None and self.root.fd is None, 'stage_retirement_failed')
        parent = os.fstat(self.parent_fd)
        need(stat.S_ISDIR(parent.st_mode)
             and (parent.st_dev, parent.st_ino) == self.parent_identity, 'stage_retirement_failed')
        self.check('', os.fstat(self.root_fd))
        self.check('', os.stat(self.name, dir_fd=self.parent_fd, follow_symlinks=False))
        directories = {path: row[1] for path, row in self.entries.items() if row[0] == 'directory'}
        files = {path: row[1] for path, row in self.entries.items() if row[0] == 'file'}
        need(directories == self.root._dirs and files == self.root._files, 'stage_retirement_failed')
        children = {path: {} for path in directories}
        for path in self.entries:
            if path:
                parent, _, name = path.rpartition('/')
                need(parent in children, 'stage_retirement_failed')
                children[parent][name] = path
        for relative, expected in children.items():
            with self.directory_fd(relative) as fd:
                found = set()
                with os.scandir(fd) as iterator:
                    for entry in iterator:
                        need(entry.name in expected and entry.name not in found, 'stage_retirement_failed')
                        self.check(expected[entry.name], os.stat(entry.name, dir_fd=fd, follow_symlinks=False))
                        found.add(entry.name)
                need(found == expected.keys(), 'stage_retirement_failed')

    def remove(self):
        if self.root_fd is None:
            return
        files = sorted(path for path, row in self.entries.items() if row[0] == 'file')
        directories = sorted((path for path, row in self.entries.items() if path and row[0] == 'directory'),
                             key=lambda path: (path.count('/'), path), reverse=True)
        for relative in (*files, *directories):
            parent, _, name = relative.rpartition('/')
            with self.directory_fd(parent) as fd:
                self.check(relative, os.stat(name, dir_fd=fd, follow_symlinks=False))
                action = os.unlink if self.entries[relative][0] == 'file' else os.rmdir
                action(name, dir_fd=fd)
        self.check('', os.fstat(self.root_fd))
        self.check('', os.stat(self.name, dir_fd=self.parent_fd, follow_symlinks=False))
        os.rmdir(self.name, dir_fd=self.parent_fd)

    def release(self):
        error = None
        for name in ('root_fd', 'parent_fd'):
            fd = getattr(self, name)
            setattr(self, name, None)
            if fd is not None:
                try:
                    self.close_fd(fd)
                except BaseException as failure:
                    error = failure
        if error is not None:
            raise error


def retire_staged(owners, *, retain=False):
    """Preflight all stage roots; one destructive pass; release every retained FD."""
    error = None
    try:
        need(all(type(owner) is StageRootOwner and not owner.retired for owner in owners),
             'stage_owner_reused')
        for owner in owners:
            owner.retired = True
        for owner in owners:
            if not owner.registered and owner.root is not None and owner.root.fd is not None:
                try:
                    owner.root.close()
                except BaseException as failure:
                    owner.uncertain, error = True, failure
        if error is not None:
            raise error
        if not retain:
            for owner in owners:
                owner.preflight()
            identities = [row[1] for owner in owners for row in owner.entries.values()]
            need(len(identities) == len(set(identities)), 'stage_retirement_failed')
            for owner in reversed(owners):
                owner.remove()
    except BaseException as failure:
        error = failure
    finally:
        for owner in reversed(owners):
            if type(owner) is not StageRootOwner:
                continue
            try:
                owner.release()
            except BaseException as failure:
                error = failure
    if error is not None:
        if isinstance(error, (OSError, ConsumerError)):
            raise ConsumerError('stage_retirement_failed') from None
        raise error
