"""Exercise the actual CI path checks without calling any Windows account API."""
import importlib.util
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('standard_paths_v23', Path(__file__).with_name('Windows标准用户验收v22.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class ReachedNativeApi(Exception):
    pass

class StandardAccountPaths(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.repo, self.temporary = self.root / 'repo', self.root / 'temp'
        self.repo.mkdir(); self.temporary.mkdir()
        self.executable = self.repo / 'app.exe'; self.executable.touch()
        self.driver = self.temporary / 'driver.exe'; self.driver.touch()
        self.source = 'a' * 40
        self.env = {'GITHUB_ACTIONS': 'true', 'RUNNER_ENVIRONMENT': 'github-hosted',
            'GITHUB_REPOSITORY': 'Eswink/coding-tools-mcp', 'GITHUB_SHA': self.source,
            'GITHUB_RUN_ID': '123', 'GITHUB_WORKSPACE': str(self.repo), 'RUNNER_TEMP': str(self.temporary)}

    def invoke(self, output, *, source=None, executable=None):
        args = SimpleNamespace(output=output, source=self.source if source is None else source,
            executable=self.executable if executable is None else executable, driver=self.driver, kind='nsis')
        with patch.dict(os.environ, self.env, clear=True), patch.object(m.sys, 'platform', 'win32'), \
             patch.object(m, 'AccountApi', side_effect=ReachedNativeApi) as api:
            try:
                m.run(args)
            finally:
                self.api_called = api.called

    def test_repository_evidence_is_accepted(self):
        with self.assertRaises(ReachedNativeApi): self.invoke(self.repo / 'evidence')
        self.assertTrue(self.api_called)

    def test_nsis_temporary_evidence_is_accepted(self):
        with self.assertRaises(ReachedNativeApi): self.invoke(self.temporary / 'packages' / 'evidence')
        self.assertTrue(self.api_called)

    def test_exact_allowed_roots_are_not_evidence_directories(self):
        for root in (self.repo, self.temporary):
            with self.subTest(root=root), self.assertRaises(ValueError): self.invoke(root)
            self.assertFalse(self.api_called)

    def test_sibling_output_is_rejected_before_api(self):
        with self.assertRaises(ValueError): self.invoke(self.root / 'outside')
        self.assertFalse(self.api_called)
        self.assertFalse((self.root / 'outside').exists())

    def test_path_traversal_is_rejected(self):
        with self.assertRaises(ValueError): self.invoke(self.repo / '..' / 'outside')
        self.assertFalse(self.api_called)

    def test_foreign_executable_is_rejected(self):
        app = self.root / 'outside.exe'; app.touch()
        with self.assertRaises(ValueError): self.invoke(self.repo / 'evidence', executable=app)
        self.assertFalse(self.api_called)

    def test_source_mismatch_or_malformed_fails_before_api(self):
        for value in ('b' * 40, 'a' * 39, 'A' * 40, '../../main'):
            with self.subTest(value=value), self.assertRaises(ValueError): self.invoke(self.repo / 'evidence', source=value)
            self.assertFalse(self.api_called)

    def test_original_binary_is_unchanged(self):
        self.executable.write_bytes(b'byte-exact-fixture')
        with self.assertRaises(ReachedNativeApi): self.invoke(self.temporary / 'evidence')
        self.assertEqual(self.executable.read_bytes(), b'byte-exact-fixture')

if __name__ == '__main__': unittest.main()
