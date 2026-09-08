"""版本递增必须精确限定在项目包，不能改动依赖版本。"""
import json
from pathlib import Path
import tempfile
import tomllib
import unittest
from 版本递增v7 import FILES, PACKAGE, plan
from 发布版本校验v4 import project_versions


class VersionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'src-tauri').mkdir()
        for name, value in {
            'package.json': {'name': PACKAGE, 'version': '0.2.1', 'dependencies': {'example': '0.2.1'}},
            'package-lock.json': {'name': PACKAGE, 'version': '0.2.1', 'packages': {
                '': {'name': PACKAGE, 'version': '0.2.1'}, 'node_modules/example': {'version': '0.2.1'}}},
            'src-tauri/tauri.conf.json': {'version': '0.2.1', 'productName': 'Coding Tools MCP'},
        }.items():
            (self.root / name).write_text(json.dumps(value), encoding='utf-8')
        (self.root / 'src-tauri/Cargo.toml').write_text(
            '[package]\nname = "' + PACKAGE + '"\nversion = "0.2.1"\n[dependencies]\nexample = "0.2.1"\n')
        (self.root / 'src-tauri/Cargo.lock').write_text(
            'version = 4\n[[package]]\nname = "' + PACKAGE + '"\nversion = "0.2.1"\n'
            '[[package]]\nname = "example"\nversion = "0.2.1"\n')

    def original(self):
        return {name: (self.root / name).read_bytes() for name in FILES}

    def test_plan_is_read_only(self):
        before = self.original()
        self.assertEqual(set(plan(self.root, '0.2.1', '0.2.2')), set(FILES))
        self.assertEqual(before, self.original())

    def test_only_project_versions_change(self):
        for name, raw in plan(self.root, '0.2.1', '0.2.2').items():
            (self.root / name).write_bytes(raw)
        self.assertEqual(project_versions(self.root)[0], '0.2.2')
        self.assertEqual(json.loads((self.root / 'package.json').read_text())['dependencies']['example'], '0.2.1')
        self.assertEqual(json.loads((self.root / 'package-lock.json').read_text())['packages']['node_modules/example']['version'], '0.2.1')
        self.assertEqual(tomllib.loads((self.root / 'src-tauri/Cargo.toml').read_text())['dependencies']['example'], '0.2.1')
        self.assertEqual(tomllib.loads((self.root / 'src-tauri/Cargo.lock').read_text())['package'][1]['version'], '0.2.1')
        self.assertEqual(plan(self.root, '0.2.1', '0.2.2'), {})

    def test_wrong_base_is_rejected_without_writes(self):
        before = self.original()
        with self.assertRaises(ValueError): plan(self.root, '0.1.0', '0.2.2')
        self.assertEqual(before, self.original())

    def test_downgrade_and_equal_are_rejected(self):
        for version in ['0.2.0', '0.2.1']:
            with self.assertRaises(ValueError): plan(self.root, '0.2.1', version)

    def test_invalid_versions_are_rejected(self):
        for version in ['v0.2.2', '00.2.2', '0.2.2-rc.1', '0.2.2\n', '0.2.2; echo bad']:
            with self.assertRaises(ValueError): plan(self.root, '0.2.1', version)

    def test_existing_drift_is_rejected(self):
        (self.root / 'src-tauri/tauri.conf.json').write_text('{"version":"0.1.0"}')
        before = self.original()
        with self.assertRaises(ValueError): plan(self.root, '0.2.1', '0.2.2')
        self.assertEqual(before, self.original())


if __name__ == '__main__':
    unittest.main()
