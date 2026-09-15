from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE_PATH = Path(__file__).with_name("rc_version_gate.py")
spec = importlib.util.spec_from_file_location("rc_version_gate", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(module)


class RcVersionGateTests(unittest.TestCase):
    def test_rc_regex_accepts_only_numbered_rc(self):
        self.assertTrue(module.RC_VERSION.fullmatch("0.6.0-rc.1"))
        for value in ["0.6.0", "0.6.0-beta.1", "0.6.0-rc", "01.6.0-rc.1"]:
            self.assertFalse(module.RC_VERSION.fullmatch(value), value)

    def test_project_versions_requires_all_six_fields(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "src-tauri").mkdir()
            version = "0.6.0-rc.1"
            (root / "package.json").write_text(json.dumps({"name": module.PACKAGE, "version": version}), encoding="utf-8")
            (root / "package-lock.json").write_text(json.dumps({
                "name": module.PACKAGE, "version": version,
                "packages": {"": {"name": module.PACKAGE, "version": version}},
            }), encoding="utf-8")
            (root / "src-tauri/Cargo.toml").write_text(
                f'[package]\nname = "{module.PACKAGE}"\nversion = "{version}"\n', encoding="utf-8")
            (root / "src-tauri/Cargo.lock").write_text(
                f'[[package]]\nname = "{module.PACKAGE}"\nversion = "{version}"\n', encoding="utf-8")
            (root / "src-tauri/tauri.conf.json").write_text(json.dumps({"version": version}), encoding="utf-8")
            actual, fields = module.project_versions(root)
            self.assertEqual(actual, version)
            self.assertEqual(len(fields), 6)
            changed = json.loads((root / "package-lock.json").read_text())
            changed["packages"][""]["version"] = "0.6.0-rc.2"
            (root / "package-lock.json").write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "differ"):
                module.project_versions(root)


if __name__ == "__main__":
    unittest.main()
