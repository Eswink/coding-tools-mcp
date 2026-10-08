"""Real filesystem ownership cases; proposed code, never executed in design."""
from contextlib import contextmanager
import gc
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import rc_consumer_io as safe
import rc_publication_retirement as retirement


class StageRetirementCases(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.source = self.parent / 'source'
        self.source.mkdir()
        self.owners = []
        self.addCleanup(self.release)

    def release(self):
        for owner in self.owners:
            try:
                if owner.root is not None:
                    owner.root.close()
            finally:
                owner.release()

    def owner(self):
        result = retirement.StageRootOwner()
        self.owners.append(result)
        return result

    def root(self, owner=None):
        owner = owner or self.owner()
        root = safe.PrivateRoot(self.parent, 'stage-test-', source_root=self.source, _stage_owner=owner)
        return root, owner

    def retire(self, *owners, retain=False):
        for owner in owners:
            if owner.root is not None:
                owner.root.close()
        retirement.retire_staged(owners, retain=retain)

    def failed(self, action):
        with self.assertRaisesRegex(safe.ConsumerError, '^stage_retirement_failed$'):
            action()

    def released(self, owner):
        self.assertIsNone(owner.root_fd)
        self.assertIsNone(owner.parent_fd)
        self.assertIsNone(owner.root.fd)

    def test_default_private_root_close_retains_outputs(self):
        root = safe.PrivateRoot(self.parent, source_root=self.source)
        self.addCleanup(root.close)
        path = root.write('nested/kept', b'consumer output')
        root.close(); root.close()
        self.assertEqual(path.read_bytes(), b'consumer output')
        self.assertIsNone(root.fd)
        self.assertIsNone(root._stage_owner)

    def test_stage_root_removes_only_registered_tree(self):
        root, owner = self.root()
        root.mkdir('empty/deep')
        root.write('nested/data', b'owned')
        root.write('top', b'owned too')
        self.retire(owner)
        self.assertFalse(root.path.exists())
        self.assertTrue(self.source.is_dir())
        self.released(owner)

    def test_parent_siblings_and_foreign_prefixes_survive(self):
        foreign = self.parent / 'stage-test-foreign'
        foreign.mkdir(mode=0o700)
        sentinel = foreign / 'data'; sentinel.write_bytes(b'foreign')
        root, owner = self.root(); root.write('data', b'owned')
        self.retire(owner)
        self.assertEqual(sentinel.read_bytes(), b'foreign')
        self.assertTrue(self.parent.exists())
        self.assertFalse(root.path.exists())

    def test_retained_parent_and_root_descriptors_are_authority(self):
        root, owner = self.root(); root.write('data', b'owned')
        original = root.path
        displaced = original.with_name('displaced')
        original.rename(displaced)
        original.mkdir(mode=0o700)
        sentinel = original / 'foreign'; sentinel.write_bytes(b'keep')
        self.failed(lambda: self.retire(owner))
        self.assertEqual(sentinel.read_bytes(), b'keep')
        self.assertEqual((displaced / 'data').read_bytes(), b'owned')
        self.released(owner)

    def test_root_constructor_is_registered_before_completion(self):
        owner = self.owner()
        registered = retirement.StageRootOwner.directory
        def after(record, *args):
            registered(record, *args)
            self.assertIs(record, owner)
            self.assertIsNotNone(record.root)
            self.assertIsNone(record.root.fd)
            self.assertIsNotNone(record.root_fd)
            raise RuntimeError('after authenticated construction')
        with patch.object(retirement.StageRootOwner, 'directory', after):
            with self.assertRaisesRegex(RuntimeError, 'after authenticated'):
                self.root(owner)
        path = owner.root.path
        retirement.retire_staged([owner])
        self.assertFalse(path.exists())
        self.released(owner)

    def test_constructor_precreation_failures_close_acquired_descriptors(self):
        owner = self.owner()
        with self.assertRaises(safe.ConsumerError):
            safe.PrivateRoot(self.source, source_root=self.source, _stage_owner=owner)
        retirement.retire_staged([owner])
        self.assertEqual(list(self.parent.iterdir()), [self.source])
        self.released(owner)

    def test_mkdir_success_open_failure_retains_unauthenticated_root(self):
        owner, opened = self.owner(), os.open
        def fail(name, *args, **kwargs):
            if isinstance(name, str) and name.startswith('stage-test-'):
                raise OSError('after mkdir before root open')
            return opened(name, *args, **kwargs)
        with patch.object(safe.os, 'open', side_effect=fail), self.assertRaises(safe.ConsumerError):
            self.root(owner)
        path = self.parent / owner.name
        self.failed(lambda: retirement.retire_staged([owner]))
        self.assertTrue(path.is_dir())
        self.released(owner)

    def test_root_identity_failure_retains_and_closes_once(self):
        owner = self.owner()
        with patch.object(safe.PrivateRoot, '_identity', side_effect=safe.ConsumerError('unsafe_private_directory')):
            with self.assertRaisesRegex(safe.ConsumerError, '^unsafe_private_directory$'):
                self.root(owner)
        self.failed(lambda: retirement.retire_staged([owner]))
        self.assertTrue((self.parent / owner.name).is_dir())
        self.released(owner)

    def test_root_registration_precedes_parent_close_failure(self):
        owner, close, observed = self.owner(), os.close, []
        def fail(fd):
            info = os.fstat(fd)
            target = owner.root_fd is not None and (info.st_dev, info.st_ino) == owner.parent_identity
            close(fd)
            if target and not observed:
                observed.append(fd)
                self.assertIn('', owner.entries)
                raise OSError('after actual parent close')
        with patch.object(safe.os, 'close', side_effect=fail), self.assertRaises(safe.ConsumerError):
            self.root(owner)
        self.assertEqual(len(observed), 1)
        self.failed(lambda: retirement.retire_staged([owner]))
        self.assertTrue(owner.root.path.exists())
        self.released(owner)

    def test_created_directory_is_registered_before_parent_close(self):
        root, owner = self.root(); close, seen = os.close, []
        def fail(fd):
            close(fd)
            if 'nested' in owner.entries and not seen:
                seen.append(fd)
                self.assertEqual(root._dirs['nested'], owner.entries['nested'][1])
                raise OSError('after real traversal close')
        with patch.object(safe.os, 'close', side_effect=fail), self.assertRaises(safe.ConsumerError):
            root.mkdir('nested')
        self.assertEqual(len(seen), 1)
        self.failed(lambda: self.retire(owner))
        self.assertTrue((root.path / 'nested').is_dir())

    def test_directory_partial_setup_retains_unknown_child(self):
        root, owner = self.root(); opened = os.open
        def fail(name, *args, **kwargs):
            if name == 'partial':
                raise OSError('created directory cannot be opened')
            return opened(name, *args, **kwargs)
        with patch.object(safe.os, 'open', side_effect=fail), self.assertRaises(safe.ConsumerError):
            root.mkdir('partial')
        self.assertIn('partial', owner.pending)
        self.failed(lambda: self.retire(owner))
        self.assertTrue((root.path / 'partial').is_dir())

    def test_exclusive_file_registration_precedes_parent_close_and_fdopen(self):
        for fault in ('parent_close', 'fdopen'):
            root, owner = self.root(); close, seen = os.close, []
            def parent_close(fd):
                close(fd)
                if 'created' in owner.entries and not seen:
                    seen.append(fd)
                    raise OSError('after actual file parent close')
            def fdopen(*args, **kwargs):
                self.assertIn('created', owner.entries)
                raise OSError('fdopen failure after registration')
            with patch.object(safe.os, 'close', side_effect=parent_close) if fault == 'parent_close' else patch.object(safe.os, 'fdopen', side_effect=fdopen):
                with self.assertRaises(safe.ConsumerError): root.write('created', b'data')
            self.assertIn('created', owner.entries)
            self.assertFalse(owner.active)
            if fault == 'parent_close':
                self.failed(lambda: self.retire(owner))
                self.assertTrue((root.path / 'created').exists())
            else:
                self.retire(owner)
                self.assertFalse(root.path.exists())

        root, owner = self.root(); opened, observed = os.fdopen, []
        def partial(fd, mode, **kwargs):
            self.assertEqual(kwargs, {'closefd': False})
            stream = opened(fd, mode, **kwargs)
            stream.close()
            observed.append(os.fstat(fd))
            raise RuntimeError('after non-owning stream setup')
        with patch.object(safe.os, 'fdopen', side_effect=partial):
            with self.assertRaisesRegex(RuntimeError, 'non-owning'): root.write('partial', b'data')
        self.assertEqual(len(observed), 1)
        self.assertFalse(owner.active)
        self.retire(owner)
        self.assertFalse(root.path.exists())

    def test_partial_file_write_with_certain_close_can_retire(self):
        root, owner = self.root()
        with patch.object(owner, 'stream', side_effect=RuntimeError('context setup')), \
                patch.object(owner, 'close_stream', wraps=owner.close_stream) as closed:
            with self.assertRaisesRegex(RuntimeError, 'context setup'): root.write('empty', b'data')
        closed.assert_called_once()
        self.assertTrue(closed.call_args.args[0].closed)
        self.assertFalse(owner.active)
        with self.assertRaisesRegex(RuntimeError, 'body failure'):
            with root.open('partial', 'xb') as stream:
                stream.write(b'part')
                raise RuntimeError('body failure')
        self.assertFalse(owner.active)
        self.assertFalse(owner.uncertain)
        self.retire(owner)
        self.assertFalse(root.path.exists())

    def test_file_setup_or_close_uncertainty_retains_once(self):
        root, owner = self.root(); fdopen = os.fdopen; calls = []
        def failing_close(*args, **kwargs):
            stream = fdopen(*args, **kwargs)
            close = stream.close
            def failed():
                calls.append(stream.fileno())
                close()
                raise OSError('after actual stream close')
            stream.close = failed
            return stream
        with patch.object(safe.os, 'fdopen', side_effect=failing_close):
            with self.assertRaises(safe.ConsumerError): root.write('data', b'part')
        self.failed(lambda: self.retire(owner))
        self.assertEqual(len(calls), 1)
        self.assertTrue((root.path / 'data').exists())
        self.failed(lambda: retirement.retire_staged([owner]))
        self.assertEqual(len(calls), 1)
        root, owner = self.root()
        context = root.open('held', 'xb')
        stream = context.__enter__()
        try:
            self.failed(lambda: self.retire(owner))
            self.assertTrue((root.path / 'held').exists())
            self.assertTrue(owner.active)
        finally:
            context.__exit__(None, None, None)
        self.assertTrue(stream.closed)
        self.failed(lambda: retirement.retire_staged([owner]))
        self.assertTrue((root.path / 'held').exists())

        for fault in ('before_close', 'raw_write'):
            root, owner = self.root(); captured, numbers, attempts = [], [], []
            def opened(*args, **kwargs):
                stream = fdopen(*args, **kwargs)
                captured.append(stream); numbers.append(stream.fileno())
                def failed(*unused):
                    attempts.append(fault)
                    raise OSError('controlled ' + fault)
                if fault == 'before_close': stream.close = failed
                else: stream.raw.write = failed
                return stream
            with patch.object(safe.os, 'fdopen', side_effect=opened):
                with self.assertRaises(safe.ConsumerError):
                    with root.open('buffered', 'xb') as stream:
                        stream.write(b'pending buffered bytes')
                        raise RuntimeError('body failure skips success flush')
            self.assertTrue(captured[0].closed and captured[0].raw.closed)
            self.assertEqual(attempts, [fault])
            self.assertFalse(owner.active or owner.unclosed)
            self.assertTrue(owner.uncertain)
            sentinel = self.parent / ('sentinel-' + root.path.name)
            sentinel.write_bytes(b'untouched')
            foreign = os.open(sentinel, os.O_RDWR)
            number = numbers[0]
            if foreign != number:
                os.dup2(foreign, number); os.close(foreign)
            try:
                with self.assertRaises(ValueError): captured[0].flush()
                del stream
                captured.clear(); gc.collect()
                self.assertEqual(sentinel.read_bytes(), b'untouched')
                self.assertEqual(attempts, [fault])
                os.fstat(number)
                self.failed(lambda: self.retire(owner))
                self.assertTrue((root.path / 'buffered').exists())
            finally:
                os.close(number)

    def test_duplicate_name_and_identity_registration_rejects(self):
        root, owner = self.root(); root.write('data', b'first')
        with self.assertRaisesRegex(safe.ConsumerError, '^stage_entry_reused$'):
            root.write('data', b'second')
        self.assertEqual(root.read('data'), b'first')
        owner.reserve('alias', 'file')
        with root.open('data') as stream:
            with self.assertRaises(safe.ConsumerError):
                owner.record('alias', 'file', stream.fileno(), root.fd, 'data')
        self.failed(lambda: self.retire(owner))
        self.assertEqual((root.path / 'data').read_bytes(), b'first')

    def test_unknown_file_directory_and_special_entry_prevent_all_removal(self):
        for kind in ('file', 'directory', 'fifo'):
            first, one = self.root(); first.write('owned', b'keep')
            second, two = self.root(); second.write('owned', b'keep')
            unknown = second.path / 'unknown'
            if kind == 'file': unknown.write_bytes(b'foreign')
            elif kind == 'directory': unknown.mkdir()
            else: os.mkfifo(unknown)
            with patch.object(retirement.os, 'unlink', side_effect=AssertionError('destruction before all preflights')):
                self.failed(lambda: self.retire(one, two))
            self.assertEqual((first.path / 'owned').read_bytes(), b'keep')
            self.assertTrue(unknown.exists())

    def test_missing_file_and_empty_directory_membership_rejects(self):
        for kind in ('file', 'directory'):
            root, owner = self.root()
            path = root.write('gone', b'data') if kind == 'file' else root.path / 'gone'
            if kind == 'directory': root.mkdir('gone'); path.rmdir()
            else: path.unlink()
            self.failed(lambda: self.retire(owner))
            self.assertTrue(root.path.exists())

    def test_file_directory_and_root_replacements_survive(self):
        for kind in ('file', 'directory'):
            root, owner = self.root()
            root.write('nested/data', b'owned')
            path = root.path / ('nested/data' if kind == 'file' else 'nested')
            moved = self.parent / ('moved-' + root.path.name)
            path.rename(moved)
            if kind == 'file': path.write_bytes(b'foreign'); path.chmod(0o600)
            else: path.mkdir(mode=0o700)
            self.failed(lambda: self.retire(owner))
            self.assertTrue(path.exists())
            self.assertTrue(moved.exists())

    def test_symlink_and_hardlink_aliases_survive(self):
        for kind in ('symlink', 'hardlink'):
            root, owner = self.root(); path = root.write('data', b'owned')
            outside = self.parent / ('outside-' + root.path.name)
            if kind == 'symlink':
                path.rename(outside); path.symlink_to(outside)
            else: os.link(path, outside)
            self.failed(lambda: self.retire(owner))
            self.assertEqual(outside.read_bytes(), b'owned')
            self.assertTrue(path.is_symlink() if kind == 'symlink' else path.exists())

    def test_owner_mode_and_type_drift_prevent_removal(self):
        root, owner = self.root(); path = root.write('data', b'owned')
        path.chmod(0o640)
        self.failed(lambda: self.retire(owner))
        self.assertEqual(path.read_bytes(), b'owned')
        self.released(owner)
        root, owner = self.root(); root.write('data', b'owned')
        original_stat = os.stat
        def changed_uid(path, *args, **kwargs):
            info = original_stat(path, *args, **kwargs)
            if path == 'data':
                row = list(info); row[4] += 1  # Model only the UID field; no chown authority.
                return os.stat_result(row)
            return info
        with patch.object(retirement.os, 'stat', side_effect=changed_uid):
            self.failed(lambda: self.retire(owner))
        self.assertEqual((root.path / 'data').read_bytes(), b'owned')
        for operation in ('root', 'mkdir', 'files'):
            root, owner = self.root(); root.write('data', b'owned')
            close, count = os.close, []
            identity = root._dirs['']
            def after_close(fd):
                info = os.fstat(fd)
                target = root._dirs.get('nested') if operation == 'mkdir' else identity
                matches = (info.st_dev, info.st_ino) == target
                close(fd)
                if matches:
                    count.append(fd)
                    if len(count) == (2 if operation == 'files' else 1):
                        raise OSError('after actual temporary directory close')
            if operation == 'root': root._dirs[''] = (-1, -1)
            try:
                with patch.object(safe.os, 'close', side_effect=after_close):
                    with self.assertRaises((OSError, safe.ConsumerError)):
                        root._root() if operation == 'root' else root.mkdir('nested') if operation == 'mkdir' else root.files()
            finally:
                root._dirs[''] = identity
            self.assertTrue(owner.uncertain)
            self.failed(lambda: self.retire(owner))
            self.assertTrue(root.path.exists())

    def test_unlink_failure_stops_and_never_retries(self):
        root, owner = self.root(); root.write('a', b'a'); root.write('b', b'b')
        unlink, attempts = os.unlink, []
        def lost_reply(name, *, dir_fd):
            attempts.append(name); unlink(name, dir_fd=dir_fd)
            raise OSError('after actual unlink')
        with patch.object(retirement.os, 'unlink', side_effect=lost_reply):
            self.failed(lambda: self.retire(owner))
            self.failed(lambda: retirement.retire_staged([owner]))
        self.assertEqual(attempts, ['a'])
        self.assertFalse((root.path / 'a').exists())
        self.assertEqual((root.path / 'b').read_bytes(), b'b')

    def test_bottom_up_rmdir_failure_stops_and_never_retries(self):
        root, owner = self.root(); root.mkdir('a/b')
        rmdir, attempts = os.rmdir, []
        def lost_reply(name, *, dir_fd):
            attempts.append(name); rmdir(name, dir_fd=dir_fd)
            raise OSError('after actual rmdir')
        with patch.object(retirement.os, 'rmdir', side_effect=lost_reply):
            self.failed(lambda: self.retire(owner))
            self.failed(lambda: retirement.retire_staged([owner]))
        self.assertEqual(attempts, ['b'])
        self.assertTrue((root.path / 'a').is_dir())
        self.released(owner)

    def test_retirement_descriptor_failures_still_close_other_owners_once(self):
        roots = [self.root() for _ in range(2)]
        for root, _ in roots: root.close()
        owned = {fd for _, owner in roots for fd in (owner.root_fd, owner.parent_fd)}
        target, close, attempts, reused = next(iter(owned)), os.close, [], []
        def fail(fd):
            attempts.append(fd); close(fd)
            if fd == target and not reused:
                foreign = os.open('/dev/null', os.O_RDONLY)
                if foreign != target:
                    os.dup2(foreign, target)
                    close(foreign)
                reused.append(target)
                raise OSError('after actual retained close')
        try:
            with patch.object(retirement.os, 'close', side_effect=fail):
                self.failed(lambda: retirement.retire_staged([owner for _, owner in roots], retain=True))
            self.assertEqual(set(attempts), owned)
            self.assertEqual(len(attempts), len(owned))
            self.assertEqual(reused, [target])
            os.fstat(reused[0])
            for _, owner in roots: self.released(owner)
        finally:
            for fd in reused: close(fd)

    def test_repeated_close_and_partial_retirement_never_delete_again(self):
        root, owner = self.root(); root.write('data', b'owned')
        self.retire(owner)
        foreign = root.path; foreign.mkdir(mode=0o700)
        (foreign / 'new').write_bytes(b'new owner')
        with patch.object(retirement.os, 'unlink', side_effect=AssertionError('repeat removal')):
            self.failed(lambda: retirement.retire_staged([owner]))
        self.assertEqual((foreign / 'new').read_bytes(), b'new owner')
        self.released(owner)
