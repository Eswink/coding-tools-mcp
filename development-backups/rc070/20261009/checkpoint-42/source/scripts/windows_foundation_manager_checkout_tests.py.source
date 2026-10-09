#!/usr/bin/env python3
"""Real owned native Git checkout controls; no Run-SourceCompile/native owner/CI."""
import ast
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import windows_foundation_source_guard as guard

MANAGER_PATHS = (
    '.github/workflows/windows-foundation-source-compile.yml',
    'scripts/windows_foundation_source_compile.ps1',
    'scripts/windows_foundation_source_guard.py',
    'scripts/windows_foundation_source_manifest.json',
    'docs/specs/windows-foundation-source-compile/requirements.md',
    'docs/specs/windows-foundation-source-compile/design.md',
    'docs/specs/windows-foundation-source-compile/tasks.md',
)
UNLEASED = 'docs/specs/windows-foundation-source-compile/ordinary-not-manager.md'
NESTED = 'nested/.github/workflows/windows-foundation-source-compile.yml'


class ManagerRawCheckoutControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ordinary-fixed-manager-checkout-')
        self.work = Path(self.temp.name)
        self.old_sha = os.environ.get('GITHUB_SHA')

    def tearDown(self):
        if self.old_sha is None:
            os.environ.pop('GITHUB_SHA', None)
        else:
            os.environ['GITHUB_SHA'] = self.old_sha
        self.temp.cleanup()

    def git(self, repo, *args, autocrlf='false'):
        return subprocess.check_output(['git', '-c', 'core.hooksPath=' + os.devnull,
            '-c', 'core.autocrlf=' + autocrlf, '-C', str(repo), *args], stderr=subprocess.DEVNULL)

    def clone_fixture(self, attributes, autocrlf):
        # Literal public manager source bytes; no private host/runtime/env files or fake authorizers.
        seed = self.work / 'seed'; seed.mkdir()
        for name in MANAGER_PATHS:
            dest = seed / name; dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes((SCRIPTS.parent / name).read_bytes()); dest.chmod(0o644)
        for name in (UNLEASED, NESTED):
            dest = seed / name; dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b'ordinary unleased source\nsecond line\n')
        if attributes:
            (seed / '.gitattributes').write_bytes((SCRIPTS.parent / '.gitattributes').read_bytes())
        self.git(seed, 'init', '-q'); self.git(seed, 'add', '--', '.')
        self.git(seed, '-c', 'user.name=Owned ordinary source', '-c', 'user.email=ordinary@invalid',
            'commit', '-qm', 'Owned public source checkout control; not candidate or CI')
        checkout = self.work / 'checkout'
        self.git(seed, 'clone', '--no-hardlinks', str(seed), str(checkout), autocrlf=autocrlf)
        os.environ['GITHUB_SHA'] = self.git(checkout, 'rev-parse', 'HEAD').decode().strip()
        return seed, checkout

    def assert_raw_manager(self, checkout):
        for name in MANAGER_PATHS:
            expected = self.git(checkout, 'show', 'HEAD:' + name)
            actual = (checkout / name).read_bytes()
            self.assertTrue(actual == expected, 'Fixed manager path differs from raw HEAD blob: ' + name)
            actual_oid = self.git(checkout, 'hash-object', '--no-filters', '--', name).decode().strip()
            expected_oid = self.git(checkout, 'rev-parse', 'HEAD:' + name).decode().strip()
            self.assertEqual(actual_oid, expected_oid)
        result = guard.verify_manager(checkout)
        self.assertEqual(result['manager_files'], 7)
        self.assertFalse(result['native_authority'])
        self.assertEqual(result['native_positive'], 'NOTRUN')

    def test_rules_are_exact_seven_literal_paths(self):
        lines = [line.split() for line in (SCRIPTS.parent / '.gitattributes').read_text().splitlines()
            if line.strip() and not line.startswith('#')]
        self.assertEqual(len(lines), 7)
        self.assertEqual({line[0] for line in lines}, set(MANAGER_PATHS))
        self.assertTrue(all(len(line) == 2 and line[1] == '-text' for line in lines))
        self.assertTrue(all(not any(char in line[0] for char in '*?[') for line in lines))

    def test_without_attributes_true_checkout_reproduces_original_raw_rejection(self):
        seed, checkout = self.clone_fixture(False, 'true')
        for name in MANAGER_PATHS:
            expected = self.git(seed, 'show', 'HEAD:' + name)
            actual = (checkout / name).read_bytes()
            self.assertTrue(actual == expected.replace(b'\n', b'\r\n'))
            self.assertFalse(actual == expected)
        with self.assertRaisesRegex(ValueError, 'blob mismatch'):
            guard.verify_manager(checkout)

    def test_attributes_true_checkout_preserves_raw_seven_and_original_admission(self):
        _, checkout = self.clone_fixture(True, 'true')
        self.assert_raw_manager(checkout)
        response = self.git(checkout, 'check-attr', '-z', 'text', '--', *MANAGER_PATHS).split(b'\0')
        self.assertEqual(response[:-1:3], [name.encode() for name in MANAGER_PATHS])
        self.assertEqual(response[2:-1:3], [b'unset'] * 7)

    def test_attributes_false_checkout_preserves_raw_seven_and_original_admission(self):
        _, checkout = self.clone_fixture(True, 'false')
        self.assert_raw_manager(checkout)

    def test_unmatched_same_directory_text_still_converts_under_true(self):
        seed, checkout = self.clone_fixture(True, 'true')
        self.assert_raw_manager(checkout)
        expected = self.git(seed, 'show', 'HEAD:' + UNLEASED)
        self.assertEqual((checkout / UNLEASED).read_bytes(), expected.replace(b'\n', b'\r\n'))
        self.assertEqual(self.git(checkout, 'check-attr', '-z', 'text', '--', UNLEASED).split(b'\0')[2], b'unspecified')

    def test_nested_same_name_is_not_accidentally_covered(self):
        seed, checkout = self.clone_fixture(True, 'true')
        self.assert_raw_manager(checkout)
        expected = self.git(seed, 'show', 'HEAD:' + NESTED)
        self.assertEqual((checkout / NESTED).read_bytes(), expected.replace(b'\n', b'\r\n'))
        self.assertEqual(self.git(checkout, 'check-attr', '-z', 'text', '--', NESTED).split(b'\0')[2], b'unspecified')

    def test_actual_mutation_retains_original_strict_rejection(self):
        _, checkout = self.clone_fixture(True, 'true')
        self.assert_raw_manager(checkout)
        path = checkout / MANAGER_PATHS[0]; path.write_bytes(path.read_bytes() + b'ordinary mutation\n')
        with self.assertRaisesRegex(ValueError, 'blob mismatch'):
            guard.verify_manager(checkout)

    def test_complete_original_guard_bytes_and_verify_manager_ast_remain_exact(self):
        data = (SCRIPTS / 'windows_foundation_source_guard.py').read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), '71aaba07443ba0ace608f8a73e0996df839f6c189e866ee949eb4dd21e4a4073')
        node = next(node for node in ast.parse(data).body if isinstance(node, ast.FunctionDef) and node.name == 'verify_manager')
        actual = hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()
        self.assertEqual(actual, '183f30416658ab6cc9edad3cbcb58a66b69a799858052f9d7b31138309362198')


if __name__ == '__main__':
    unittest.main(verbosity=2)
