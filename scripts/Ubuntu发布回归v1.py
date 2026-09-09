"""Offline fail-closed regression for Ubuntu package and release gates."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from Ubuntu安装验收v1 import VERSION, MANIFEST, verify_manifest, digest, elf_x64
from Ubuntu发布v1 import validate_reports, compose, check_asset, Github, publish, REF, REPOSITORY

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "a" * 40


class UbuntuReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.packages, self.evidence, self.output = [self.root / name for name in ("packages", "evidence", "output")]
        self.packages.mkdir()
        items = {}
        for kind in ("deb", "appimage"):
            path = self.packages / (kind + ".fixture")
            path.write_bytes((kind * 30).encode())
            items[kind] = {"name": path.name, "size": path.stat().st_size, "sha256": digest(path)}
        self.manifest = {"source_sha": SOURCE, "version": VERSION, "packages": items}
        self.write_manifest()
        for system in ("ubuntu-22.04", "ubuntu-24.04"):
            for kind in ("deb", "appimage"):
                path = self.report(system, kind)
                path.parent.mkdir(parents=True)
                path.write_text(json.dumps({"passed": True, "source_sha": SOURCE, "version": VERSION,
                    "format": kind, "real_native_webview": True, "mock_transport": False, "sandbox_disabled": False, "host_python_environment_preserved": True,
                    "tests": [{"name": f"case-{i}", "passed": True} for i in range(8)]}))
            (path.parent.parent / "安装载荷结果v1.json").write_text(json.dumps({"passed": True, "source_sha": SOURCE, "version": VERSION}))
        for system in ("ubuntu-24.04", "windows-latest"):
            path = self.evidence / f"Ubuntu基线v1-{system}" / "基线结果v1.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"passed": True, "source_sha": SOURCE}))

    def write_manifest(self):
        (self.packages / MANIFEST).write_text(json.dumps(self.manifest))

    def report(self, system="ubuntu-22.04", kind="deb"):
        return self.evidence / f"Ubuntu原生验收v1-{system}" / kind / "原生验收结果v1.json"

    def mutate(self, key, value):
        path = self.report()
        report = json.loads(path.read_text())
        report[key] = value
        path.write_text(json.dumps(report))

    def test_valid_package_digests(self):
        self.assertEqual(verify_manifest(self.packages, SOURCE), self.manifest)

    def test_corrupt_package_rejected(self):
        (self.packages / "deb.fixture").write_bytes(b"corrupt")
        with self.assertRaises(ValueError):
            verify_manifest(self.packages, SOURCE)

    def test_wrong_sha_rejected(self):
        with self.assertRaises(ValueError):
            verify_manifest(self.packages, "b" * 40)

    def test_missing_format_rejected(self):
        del self.manifest["packages"]["appimage"]
        self.write_manifest()
        with self.assertRaises(ValueError):
            verify_manifest(self.packages, SOURCE)

    def test_path_traversal_rejected(self):
        self.manifest["packages"]["deb"]["name"] = "../secret"
        self.write_manifest()
        with self.assertRaises(ValueError):
            verify_manifest(self.packages, SOURCE)

    def test_all_four_native_reports_required(self):
        self.assertEqual(len(validate_reports(self.evidence, SOURCE)), 4)
        self.report("ubuntu-24.04", "appimage").unlink()
        with self.assertRaises(FileNotFoundError):
            validate_reports(self.evidence, SOURCE)

    def test_failed_native_result_blocks(self):
        self.mutate("passed", False)
        with self.assertRaises(ValueError):
            validate_reports(self.evidence, SOURCE)

    def test_mismatched_native_source_blocks(self):
        self.mutate("source_sha", "b" * 40)
        with self.assertRaises(ValueError):
            validate_reports(self.evidence, SOURCE)

    def test_mock_transport_does_not_count_as_native(self):
        self.mutate("mock_transport", True)
        with self.assertRaises(ValueError):
            validate_reports(self.evidence, SOURCE)

    def test_sandbox_bypass_blocks(self):
        self.mutate("sandbox_disabled", True)
        with self.assertRaises(ValueError):
            validate_reports(self.evidence, SOURCE)

    def test_incomplete_tests_block(self):
        self.mutate("tests", [{"passed": True}])
        with self.assertRaises(ValueError):
            validate_reports(self.evidence, SOURCE)

    def test_failed_subtest_blocks(self):
        self.mutate("tests", [{"passed": False}] * 8)
        with self.assertRaises(ValueError):
            validate_reports(self.evidence, SOURCE)

    def test_baseline_missing_blocks(self):
        (self.evidence / "Ubuntu基线v1-windows-latest/基线结果v1.json").unlink()
        with self.assertRaises(FileNotFoundError):
            validate_reports(self.evidence, SOURCE)

    def test_asset_digest_mismatch_refuses_replacement(self):
        path = self.packages / "deb.fixture"
        record = {"name": path.name, "state": "uploaded", "size": path.stat().st_size, "digest": "sha256:" + digest(path)}
        check_asset(record, path)
        record["digest"] = "sha256:" + "0" * 64
        with self.assertRaises(ValueError):
            check_asset(record, path)

    def test_wrong_main_blocks(self):
        client = Github("fixture-only")
        with patch.object(client, "call", return_value={"object": {"sha": "b" * 40}}):
            with self.assertRaises(ValueError):
                client.main_is(SOURCE)

    def test_wrong_tag_blocks(self):
        client = Github("fixture-only")
        with patch.object(client, "call", return_value={"object": {"sha": SOURCE, "type": "tag"}}):
            with self.assertRaises(ValueError):
                client.tag_is(SOURCE)

    def test_nonrelease_branch_never_calls_api(self):
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": REPOSITORY, "GITHUB_REF": "refs/heads/main", "GITHUB_SHA": SOURCE}):
            with patch("Ubuntu发布v1.Github") as api:
                with self.assertRaises(ValueError):
                    publish([], SOURCE, ROOT, self.output)
                api.assert_not_called()

    def test_offline_composition_and_checksums(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")):
            assets = compose(self.packages, self.evidence, self.output, SOURCE, ROOT)
        self.assertEqual(len(assets), 4)
        checksum = assets[-1].read_text()
        for path in assets[:-1]:
            self.assertIn(digest(path) + "  " + path.name, checksum)

    def test_elf_architecture_guard(self):
        path = self.root / "elf"
        header = bytearray(20)
        header[:6] = b"\x7fELF\x02\x01"
        header[18:20] = b"\x3e\x00"
        path.write_bytes(header)
        self.assertTrue(elf_x64(path))
        header[18:20] = b"\xb7\x00"  # ARM64 is intentionally not this release target.
        path.write_bytes(header)
        self.assertFalse(elf_x64(path))

    def test_workflow_requires_all_gates_and_minimum_permissions(self):
        workflow = (ROOT / ".github/workflows/Ubuntu桌面构建v1.yml").read_text(encoding="utf-8")
        self.assertIn("runs-on: ubuntu-22.04", workflow)
        self.assertIn("os: [ubuntu-22.04, ubuntu-24.04]", workflow)
        self.assertIn("needs: [validate, build, native, acceptance]", workflow)
        self.assertEqual(workflow.count("contents: write"), 1)
        self.assertNotIn("contents: write", workflow.split("  publish:")[0])
        self.assertIn(REF, workflow)
        self.assertNotIn("continue-on-error: true", workflow)
        self.assertNotIn("--disable-sandbox", workflow)
        self.assertNotIn("WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS", workflow)

    def test_linux_overlay_preserves_shared_product_identity(self):
        config = json.loads((ROOT / "src-tauri/Ubuntu桌面v1.json").read_text())
        self.assertNotIn("productName", config)
        self.assertNotIn("identifier", config)
        self.assertEqual(config["bundle"]["targets"], ["deb", "appimage"])
        self.assertIn("gnome-keyring", config["bundle"]["linux"]["deb"]["depends"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
