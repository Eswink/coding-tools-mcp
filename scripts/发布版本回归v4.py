"""发布来源门的结构、负例与真实临时Git仓库回归；不触发任何Release。"""
from pathlib import Path
import json
import subprocess
import tempfile
import unittest

from 发布版本校验v4 import collect_artifacts, git_commit, project_versions, resolve_tag, verify_source


class ReleaseGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="发布版本回归v4-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "src-tauri").mkdir()
        self.write_json("package.json", {"name": "coding-tools-mcp-desktop", "version": "0.2.2"})
        self.write_json("package-lock.json", {"name": "coding-tools-mcp-desktop", "version": "0.2.2", "packages": {"": {"name": "coding-tools-mcp-desktop", "version": "0.2.2"}}})
        self.write_json("src-tauri/tauri.conf.json", {"version": "0.2.2"})
        (self.root / "src-tauri/Cargo.toml").write_text('[package]\nname="coding-tools-mcp-desktop"\nversion="0.2.2"\n[dependencies]\nother="0.2.1"\n')
        (self.root / "src-tauri/Cargo.lock").write_text('version=4\n[[package]]\nname="other"\nversion="0.2.1"\n[[package]]\nname="coding-tools-mcp-desktop"\nversion="0.2.2"\n')

    def write_json(self, file, value):
        (self.root / file).write_text(json.dumps(value), encoding="utf-8")

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)

    def repository(self):
        self.git("init")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "add", ".")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "fixture")
        self.git("tag", "v0.2.2")

    def test_six_versions_match_without_changing_dependencies(self):
        version, fields = project_versions(self.root)
        self.assertEqual(version, "0.2.2")
        self.assertEqual(len(fields), 6)
        self.assertIn('other="0.2.1"', (self.root / "src-tauri/Cargo.toml").read_text())

    def test_each_version_field_mismatch_is_rejected(self):
        for file in ["package.json", "package-lock.json", "src-tauri/tauri.conf.json", "src-tauri/Cargo.toml", "src-tauri/Cargo.lock"]:
            with self.subTest(file=file):
                p = self.root / file
                old = p.read_text()
                p.write_text(old.replace("0.2.2", "0.2.3", 1))
                with self.assertRaises(ValueError): project_versions(self.root)
                p.write_text(old)

    def test_lock_root_package_mismatch_is_rejected(self):
        file = self.root / "package-lock.json"
        obj = json.loads(file.read_text()); obj["packages"][""]["version"] = "0.2.1"
        self.write_json("package-lock.json", obj)
        with self.assertRaises(ValueError): project_versions(self.root)

    def test_duplicate_cargo_project_is_rejected(self):
        file = self.root / "src-tauri/Cargo.lock"
        file.write_text(file.read_text() + '\n[[package]]\nname="coding-tools-mcp-desktop"\nversion="0.2.2"\n')
        with self.assertRaises(ValueError): project_versions(self.root)

    def test_missing_and_malformed_inputs_fail(self):
        (self.root / "package.json").write_text("not-json")
        with self.assertRaises(ValueError): project_versions(self.root)
        (self.root / "package.json").unlink()
        with self.assertRaises(OSError): project_versions(self.root)

    def test_exact_tag_checkout_passes(self):
        self.repository()
        sha = resolve_tag(self.root, "v0.2.2")
        self.assertEqual(verify_source(self.root, "v0.2.2", sha)["source_sha"], sha)

    def test_tag_on_old_commit_is_rejected_even_if_versions_match(self):
        self.repository()
        (self.root / "修改v4.txt").write_text("different code")
        self.git("add", ".")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "different")
        with self.assertRaisesRegex(ValueError, "当前checkout"): verify_source(self.root, "v0.2.2")

    def test_wrong_expected_sha_is_rejected(self):
        self.repository()
        with self.assertRaisesRegex(ValueError, "SHA"): verify_source(self.root, expected_sha="0" * 40)

    def test_tag_version_mismatch_is_rejected(self):
        self.repository(); self.git("tag", "v0.2.3")
        with self.assertRaisesRegex(ValueError, "版本"): verify_source(self.root, "v0.2.3")

    def test_invalid_and_missing_tags_are_rejected(self):
        for tag in ["--help", "v0.2.2\nsource_sha=evil", "v01.2.2", "main", "v0.2.2;true"]:
            with self.subTest(tag=tag), self.assertRaises(ValueError): resolve_tag(self.root, tag)
        self.repository()
        with self.assertRaises(ValueError): resolve_tag(self.root, "v9.9.9")

    def test_installer_manifest_and_old_files(self):
        directory = self.root / "产物"; directory.mkdir()
        with self.assertRaises(ValueError): collect_artifacts(directory, "0.2.2", ".exe")
        file = directory / "App_0.2.2_x64-setup.exe"; file.write_bytes(b"test fixture, not a real installer")
        entries = collect_artifacts(directory, "0.2.2", ".exe")
        self.assertEqual(len(entries), 1); self.assertEqual(len(entries[0]["sha256"]), 64)
        (directory / "App_0.2.21_x64-setup.exe").write_bytes(b"old")
        with self.assertRaises(ValueError): collect_artifacts(directory, "0.2.2", ".exe")

    def test_dirty_tracked_source_cannot_claim_tag_provenance(self):
        self.repository()
        file = self.root / "src-tauri/Cargo.toml"
        file.write_text(file.read_text() + "\n# modified after checkout\n")
        with self.assertRaisesRegex(ValueError, "修改"):
            verify_source(self.root, "v0.2.2")

    def test_annotated_tag_is_peeled_to_commit(self):
        self.repository()
        self.git("tag", "-d", "v0.2.2")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "tag", "-a", "v0.2.2", "-m", "annotated")
        self.assertEqual(resolve_tag(self.root, "v0.2.2"), git_commit(self.root, "HEAD"))
        self.assertTrue(verify_source(self.root, "v0.2.2")["passed"])

    def test_empty_installer_is_rejected(self):
        file = self.root / "App_0.2.2_x64.dmg"; file.touch()
        with self.assertRaises(ValueError): collect_artifacts(self.root, "0.2.2", ".dmg")


if __name__ == "__main__":
    unittest.main(verbosity=2)
