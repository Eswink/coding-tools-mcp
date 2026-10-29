"""Real temporary Git source classification fixtures; no release operations."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import source_provenance_gate as gate


def command(root, *args):
    return subprocess.check_output(['git', *args], cwd=root, stderr=subprocess.PIPE).decode().strip()


def commit(root):
    command(root, 'add', '.')
    command(root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
            'commit', '-m', 'synthetic fixture', '--allow-empty')
    return command(root, 'rev-parse', 'HEAD')


def repository(root, version='1.2.3-rc.4'):
    (root / 'src-tauri').mkdir()
    name = 'coding-tools-mcp-desktop'
    (root / 'package.json').write_text(json.dumps(dict(name=name, version=version)))
    (root / 'package-lock.json').write_text(json.dumps(dict(name=name, version=version,
                                      packages={'': dict(name=name, version=version)})))
    (root / 'src-tauri/tauri.conf.json').write_text(json.dumps(dict(version=version)))
    (root / 'src-tauri/Cargo.toml').write_text(f'[package]\nname="{name}"\nversion="{version}"\n')
    (root / 'src-tauri/Cargo.lock').write_text(f'version=4\n[[package]]\nname="{name}"\nversion="{version}"\n')
    command(root, 'init')
    command(root, 'config', 'core.autocrlf', 'false')
    return commit(root)


class ProvenanceTests(unittest.TestCase):
    def test_fullmatch_classification(self):
        self.assertEqual(gate.classify('1.2.3'), 'stable')
        self.assertEqual(gate.classify('1.2.3-rc.4'), 'release-candidate')
        for value in ('01.2.3', '1.2.3-beta.4', '1.2.3-rc.04', '1.2.3+meta', '1.2.3\n', '', None):
            with self.assertRaises(ValueError): gate.classify(value)

    def test_real_stable_and_rc_sources_retain_all_six_checks(self):
        for version in ('1.2.3', '1.2.3-rc.4'):
            with tempfile.TemporaryDirectory() as raw:
                root = Path(raw); source = repository(root, version)
                value = gate.verify(root, source)
                self.assertEqual(len(value['versions']), 6)
                self.assertFalse(value['publish_approved'])
                with self.assertRaises(ValueError): gate.verify(root, '0'*40)
                path = root / 'src-tauri/tauri.conf.json'
                path.write_text('{"version":"8.8.8"}')
                with self.assertRaises(ValueError): gate.verify(root, source)

    def test_dirty_same_version_source_is_not_provenance(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); source = repository(root)
            path = root / 'package.json'; path.write_text(path.read_text() + '\n')
            with self.assertRaises(ValueError): gate.verify(root, source)

    def test_stable_verifier_still_rejects_rc(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); source = repository(root)
            with self.assertRaises(ValueError): gate.stable.verify_source(root, expected_sha=source)


if __name__ == '__main__':
    unittest.main()
