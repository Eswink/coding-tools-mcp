"""RC input validation must remain distinct from stable publication approval."""
import importlib
import json
from pathlib import Path
import tempfile
import unittest

preflight = importlib.import_module("release_preflight")


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "src-tauri").mkdir()
        (self.root / "docs/releases").mkdir(parents=True)

    def fixture(self, version="0.6.1-rc.2"):
        name = "coding-tools-mcp-desktop"
        (self.root / "package.json").write_text(json.dumps({"name": name, "version": version}))
        (self.root / "package-lock.json").write_text(json.dumps({
            "name": name, "version": version, "packages": {"": {"name": name, "version": version}}
        }))
        (self.root / "src-tauri/Cargo.toml").write_text(f'[package]\nname="{name}"\nversion="{version}"\n')
        (self.root / "src-tauri/Cargo.lock").write_text(f'[[package]]\nname="{name}"\nversion="{version}"\n')
        (self.root / "src-tauri/tauri.conf.json").write_text(json.dumps({"version": version}))
        guide = self.root / f"docs/releases/verification-v{version}.md"
        guide.write_text(f"# {version}\nSynthetic input fixture, not acceptance evidence.\n")
        return guide

    def test_auto_selects_rc_without_claiming_release_or_source_verified(self):
        self.fixture()
        result = preflight.verify_inputs(self.root)
        self.assertEqual(result["channel"], "rc")
        self.assertEqual(result["version_fields"], 6)
        self.assertEqual(result["scope"], "release-inputs-only")
        self.assertFalse(result["source_verified"])

    def test_explicit_stable_still_rejects_rc(self):
        self.fixture()
        with self.assertRaises(ValueError):
            preflight.verify_inputs(self.root, channel="stable")

    def test_explicit_rc_rejects_stable(self):
        self.fixture("0.6.1")
        with self.assertRaises(ValueError):
            preflight.verify_inputs(self.root, channel="rc")

    def test_rc_rejects_version_drift(self):
        self.fixture()
        (self.root / "src-tauri/tauri.conf.json").write_text('{"version":"0.6.1-rc.3"}')
        with self.assertRaises(ValueError):
            preflight.verify_inputs(self.root)

    def test_rc_rejects_missing_empty_and_symlink_guide(self):
        guide = self.fixture()
        guide.unlink()
        with self.assertRaises(ValueError):
            preflight.verify_inputs(self.root)
        guide.write_text(" \n")
        with self.assertRaises(ValueError):
            preflight.verify_inputs(self.root)
        guide.unlink()
        target = self.root / "other.md"
        target.write_text("Other guide")
        guide.symlink_to(target)
        with self.assertRaises(ValueError):
            preflight.verify_inputs(self.root)

    def test_rc_rejects_guide_directory_escape(self):
        guide = self.fixture()
        guide.unlink()
        releases = self.root / "docs/releases"
        releases.rmdir()
        with tempfile.TemporaryDirectory() as raw:
            outside = Path(raw)
            (outside / guide.name).write_text("External guide")
            releases.symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                preflight.verify_inputs(self.root)

    def test_source_identity_cannot_be_claimed_without_git_candidate(self):
        self.fixture()
        with self.assertRaises(ValueError):
            preflight.verify_inputs(self.root, expected_sha="a" * 40)


if __name__ == "__main__":
    unittest.main()
