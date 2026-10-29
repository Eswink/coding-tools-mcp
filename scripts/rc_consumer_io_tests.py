"""Hermetic synthetic attacks on consumer private I/O; no artifact execution."""
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import rc_consumer_io as safe


class PrivateIOTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.source = self.parent / 'checkout'
        self.source.mkdir()
        (self.source / 'unchanged').write_bytes(b'source')
        self.root = safe.PrivateRoot(self.parent, 'test-', source_root=self.source)
        self.addCleanup(self.root.close)

    def test_positive_private_modes_read_copy_inventory(self):
        path = self.root.write('evidence/one', b'one')
        self.assertEqual(self.root.read('evidence/one'), b'one')
        self.assertEqual(safe.hash_file(path), hashlib.sha256(b'one').hexdigest())
        self.root.copy('two', path)
        self.assertEqual(self.root.files(), ('evidence/one', 'two'))
        self.assertEqual(safe.assert_private_tree(self.root.path), self.root.files())
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.root.path.stat().st_mode & 0o777, 0o700)
        self.assertEqual(safe.read_prefix(path, 2), b'on')
        self.assertEqual(safe.read_bytes(path, 3), b'one')

    def test_invalid_relative_paths(self):
        for value in ('/abs', '../up', 'a/../up', './x', 'a//b', 'a/', 'C:x', '\\server',
                      'a\\b', 'nul\x00x', 'a\nb', 'a\x7fb', '\ud800', '\u202ex', 'x' * 1025):
            with self.subTest(value=repr(value)), self.assertRaises(safe.ConsumerError):
                self.root.write(value, b'blocked')
        self.assertEqual((self.source / 'unchanged').read_bytes(), b'source')
        self.assertEqual(sorted(p.name for p in self.source.iterdir()), ['unchanged'])

    def test_source_root_and_ancestor_symlink_rejected(self):
        with self.assertRaises(safe.ConsumerError):
            safe.PrivateRoot(self.source, source_root=self.source)
        child = self.source / 'child'
        child.mkdir()
        with self.assertRaises(safe.ConsumerError):
            safe.PrivateRoot(child, source_root=self.source)
        alias = self.parent / 'alias'
        alias.symlink_to(self.parent, target_is_directory=True)
        with self.assertRaises(safe.ConsumerError):
            safe.PrivateRoot(alias, source_root=self.source)
        self.root.write('a/file', b'private')
        with self.assertRaises(safe.ConsumerError):
            safe.read_bytes(alias / self.root.path.name / 'a/file')

    def test_final_symlink_and_hardlink_rejected(self):
        (self.root.path / 'link').symlink_to(self.source / 'unchanged')
        with self.assertRaises(safe.ConsumerError):
            self.root.write('link', b'changed')
        with self.assertRaises(safe.ConsumerError):
            safe.hash_file(self.root.path / 'link')
        path = self.root.write('normal', b'private')
        os.link(path, self.parent / 'hardlink')
        with self.assertRaises(safe.ConsumerError):
            self.root.read('normal')
        with self.assertRaises(safe.ConsumerError):
            safe.hash_file(path)
        self.assertEqual((self.source / 'unchanged').read_bytes(), b'source')

    def test_parent_replacement_before_open_rejected(self):
        self.root.write('evidence/one', b'one')
        original = self.root.path / 'evidence'
        original.rename(self.root.path / 'held')
        original.symlink_to(self.source, target_is_directory=True)
        for action in (lambda: self.root.write('evidence/unchanged', b'changed'),
                       lambda: self.root.read('evidence/one'), lambda: self.root.files()):
            with self.assertRaises(safe.ConsumerError):
                action()
        self.assertEqual((self.source / 'unchanged').read_bytes(), b'source')

    def test_open_parent_race_remains_anchored(self):
        self.root.mkdir('evidence')
        original_open = os.open
        switched = False
        def raced_open(name, flags, *args, **kwargs):
            nonlocal switched
            if name == 'safe' and not switched:
                switched = True
                (self.root.path / 'evidence').rename(self.root.path / 'held')
                (self.root.path / 'evidence').symlink_to(self.source, target_is_directory=True)
            return original_open(name, flags, *args, **kwargs)
        with patch.object(safe.os, 'open', side_effect=raced_open):
            self.root.write('evidence/safe', b'anchored')
        self.assertTrue(switched)
        self.assertFalse((self.source / 'safe').exists())
        self.assertEqual((self.root.path / 'held/safe').read_bytes(), b'anchored')
        with self.assertRaises(safe.ConsumerError):
            self.root.files()

    def test_root_replacement_and_injected_file_fail(self):
        old = self.root.path
        old.rename(self.parent / 'held-root')
        old.mkdir(mode=0o700)
        with self.assertRaises(safe.ConsumerError):
            self.root.write('no', b'no')
        other = safe.PrivateRoot(self.parent, 'other-', source_root=self.source)
        self.addCleanup(other.close)
        (other.path / 'injected').write_bytes(b'injected')
        with self.assertRaises(safe.ConsumerError):
            other.files()

    def test_preexisting_private_entry_and_mode_change_fail(self):
        self.root.write('one', b'first')
        with self.assertRaises(safe.ConsumerError):
            self.root.write('one', b'second')
        self.assertEqual(self.root.read('one'), b'first')
        (self.root.path / 'one').chmod(0o700)
        with self.assertRaises(safe.ConsumerError):
            self.root.read('one')
        with self.assertRaises(safe.ConsumerError):
            safe.assert_private_tree(self.root.path)

    def test_bounded_reads_and_fixed_error_codes(self):
        path = self.root.write('bytes', b'12345')
        for action in (lambda: self.root.read('bytes', 4), lambda: safe.read_bytes(path, 4),
                       lambda: safe.read_prefix(path, -1)):
            with self.assertRaises(safe.ConsumerError):
                action()
        self.assertEqual(str(safe.ConsumerError('https://secret?token')), 'consumer_validation_failed')
        self.assertEqual(safe.ConsumerError('safe_code').code, 'safe_code')

    def test_json_duplicates_nonfinite_overflow_and_syntax(self):
        values = (b'{"x":1,"x":2}', b'{"x":{"y":1,"y":2}}', b'{"x":NaN}', b'{"x":Infinity}',
                  b'{"x":-Infinity}', b'{"x":1e999}', b'{"x":-1e999}', b'[]', b'{', b'\xff')
        for index, value in enumerate(values):
            path = self.root.write(str(index), value)
            with self.subTest(value=value), self.assertRaises(safe.ConsumerError):
                safe.json_file(path)
        path = self.root.write('fraction', b'{"pending_elapsed_seconds":90.5,"id":1}')
        self.assertEqual(safe.json_file(path)['pending_elapsed_seconds'], 90.5)
        with patch.object(safe, 'JSON_LIMIT', 4), self.assertRaises(safe.ConsumerError):
            safe.json_file(path)


if __name__ == '__main__':
    unittest.main()
