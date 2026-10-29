"""Real archive observation delegates; no test discovery or payload execution."""
from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
from unittest.mock import patch
import tarfile
import zipfile

import rc_consumer_archive as archive
import rc_consumer_io as safe


class Budget:
    def __init__(self, cancelled=True):
        self.cancelled, self.stopped, self.polls = cancelled, False, 0
        self.deadline = None if cancelled else 101
        self.controls = dict(deadline=self.deadline, check_active=self.active)

    def active(self):
        self.polls += 1
        if self.cancelled and self.stopped:
            raise safe.ConsumerError('cancelled')

    def now(self):
        return 101 if self.stopped else 100

    @contextmanager
    def after_entry(self):
        checked = archive._check_budget
        def check(deadline, active):
            checked(deadline, active)
            self.stopped = True
        with patch.object(archive, '_check_budget', check):
            yield

    @property
    def code(self):
        return 'transport_cancelled' if self.cancelled else 'transport_deadline_exceeded'


class Observed:
    """Delegate all real stream/decoder work; report only completed operations."""
    def __init__(self, target, trace, kind, key='', owner=None):
        self.target, self.trace, self.kind, self.key, self.owner = target, trace, kind, key, owner
        if kind == 'decoder':
            self.owner = self
        else:
            trace.streams.append(target)

    def __getattr__(self, name):
        return getattr(self.target, name)

    def event(self, operation, result, size=None):
        self.trace.event(self.kind + '.' + operation, self.key, result, size, self.owner)
        return result

    def read(self, size=-1):
        return self.event('read', self.target.read(size), size)

    def write(self, data):
        return self.event('write', self.target.write(data), len(data))

    def decompress(self, data, size):
        return self.event('decompress', self.target.decompress(data, size), size)

    def __enter__(self):
        self.target.__enter__()
        self.event('enter', None)
        return self

    def __exit__(self, *error):
        result = self.target.__exit__(*error)
        self.event('close', None)
        return result


class Trace:
    def __init__(self, hook=lambda event: None, budget=None):
        self.budget = budget
        self.hook, self.events, self.streams, self.controls = hook, [], [], []
        self.phase, self.padding, self.failures = '', False, []

    def event(self, kind, key='', result=None, size=None, owner=None):
        event = SimpleNamespace(kind=kind, key=key, result=result, size=size, owner=owner,
                                phase=self.phase)
        self.events.append(event)
        self.hook(event)
        return result

    def count(self, kind):
        return sum(event.kind == kind for event in self.events)

    def wrap(self, function, label):
        def wrapped(*args, **kwargs):
            if (label == 'zip_archive_close' and args[0].fp is None) or \
                    (label == 'tar_archive_close' and args[0].closed):
                return function(*args, **kwargs)
            self.controls.append((label, kwargs.copy()))
            previous, self.phase = self.phase, label
            self.event(label + '.entry', owner=args)
            try:
                result = function(*args, **kwargs)
                return self.event(label + '.return', result=result, owner=args)
            finally:
                self.phase = previous
        return wrapped

    @contextmanager
    def trace_calls(self):
        original_file, original_root = safe.open_file, safe.PrivateRoot.open
        original_zip, original_tar = zipfile.ZipFile.open, tarfile.TarFile.extractfile
        original_decode, original_iter = archive.zlib.decompressobj, tarfile.TarFile.__iter__
        original_at, original_stream, original_need = archive._at, tarfile._Stream.read, archive.need
        with ExitStack() as stack:
            def install(owner, name, replacement, **kwargs):
                stack.enter_context(patch.object(owner, name, replacement, **kwargs))

            @contextmanager
            def file_open(path):
                kind = 'hash' if self.phase == 'hash_file' else 'raw'
                try:
                    with original_file(path) as stream:
                        yield Observed(stream, self, kind, str(path))
                finally:
                    if 'stream' in locals() and stream.closed:
                        self.event(kind + '.close', str(path))

            @contextmanager
            def root_open(root, name, mode='rb'):
                kind = 'output' if mode == 'xb' else 'binary'
                try:
                    with original_root(root, name, mode) as stream:
                        self.event(kind + '.acquire', name)
                        yield Observed(stream, self, kind, name)
                finally:
                    if 'stream' in locals() and stream.closed:
                        self.event(kind + '.close', name)

            def zip_open(owner, member, *args, **kwargs):
                result = original_zip(owner, member, *args, **kwargs)
                self.event('zip.acquire', member.filename, owner=member)
                return Observed(result, self, 'zip', member.filename, member)

            def tar_open(owner, member):
                result = original_tar(owner, member)
                if result is None:
                    return result
                self.event('tar.acquire', member.name, owner=member)
                return Observed(result, self, 'tar', member.name, member)

            def decode(bits, *args, **kwargs):
                kind = 'gzip' if bits > 0 else 'deflate' if self.phase == '_deflate_integrity' else 'zipdecoder'
                result = original_decode(bits, *args, **kwargs)
                return Observed(result, self, 'decoder', kind, result)

            def iterate(owner):
                for member in original_iter(owner):
                    self.event('tar.member', member.name, owner=member)
                    yield member
                self.padding = True
                self.event('tar.end')

            def at(stream, offset, length):
                result = original_at(stream, offset, length)
                self.event('record', self.phase, result, length)
                return result

            def stream_read(owner, size):
                result = original_stream(owner, size)
                if self.padding:
                    self.event('padding.read', result=result, size=size)
                return result

            def diagnosed(condition, code):
                if not condition:
                    self.failures.append((code, self.budget.polls if self.budget else None))
                return original_need(condition, code)

            install(archive, 'need', diagnosed)
            install(safe, 'open_file', file_open)
            install(archive, 'open_file', file_open)
            install(safe.PrivateRoot, 'open', root_open)
            install(zipfile.ZipFile, 'open', zip_open)
            install(tarfile.TarFile, 'extractfile', tar_open)
            install(tarfile.TarFile, '__iter__', iterate)
            install(tarfile._Stream, 'read', stream_read)
            install(archive.zlib, 'decompressobj', decode)
            install(archive, '_at', at)
            for label in ('_directory_guard', '_local_records', '_deflate_integrity',
                          'extract_bounded_zip', 'extract_bounded_cloud_tar', 'json_file', 'hash_file'):
                install(archive, label, self.wrap(getattr(archive, label), label))
            for owner, label, name in ((safe.PrivateRoot, 'inventory', 'files'),
                    (safe.PrivateRoot, 'mkdir', 'mkdir'), (zipfile.ZipFile, 'zip_archive', '__init__'),
                    (zipfile.ZipFile, 'zip_archive_close', 'close'), (tarfile.TarFile, 'tar_archive_close', 'close'),
                    (archive._GzipReader, 'gzip_reader', '__init__')):
                install(owner, name, self.wrap(getattr(owner, name), label))
            install(archive, 'sorted', self.wrap(sorted, 'sort'), create=True)
            yield self
