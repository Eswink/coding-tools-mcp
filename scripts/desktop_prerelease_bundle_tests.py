"""Failure-first contracts for the desktop-only package evidence gate."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import desktop_prerelease_bundle as gate
import exclusive_native_gate as stable

SOURCE, TREE, RUN = "a" * 40, "b" * 40, "123"
BINARY = "c" * 64


class BundleContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        self.artifacts = Path(self.temp.name) / "artifacts"
        self.ident = dict(source_sha=SOURCE, source_tree=TREE, run_id=RUN,
                          version=gate.VERSION, passed=True)
        self.write(self.root / f"docs/releases/desktop-v{gate.VERSION}/scope.json", {
            "version": gate.VERSION, "profile": "desktop-local-validation",
            "full_cloud_gateway_release": False,
        })
        for platform, linux in (("ubuntu-24.04", True), ("windows-2025", False)):
            d = self.artifacts / f"desktop-native-{platform}-{RUN}"
            self.write(d / "commit.txt", SOURCE, raw=True)
            self.write(d / "tree.txt", TREE, raw=True)
            outcomes = {k: "success" for k in ("CHECK", "DESKTOP", "RUNTIME", "FORMAT")}
            outcomes.update(PROBE="success" if linux else "skipped",
                            GIT_BOUNDARY="success" if linux else "skipped")
            self.write(d / "results.json", dict(source_sha=SOURCE, run_id=RUN,
                        platform="Linux" if linux else "Windows", outcomes=outcomes))
            self.write(d / "desktop.txt", self.summary(495 if linux else 488), raw=True)
            self.write(d / "runtime.txt", self.summary(134 if linux else 91), raw=True)
            if linux:
                self.write(d / "git-boundary.txt", self.summary(6), raw=True)
                self.write(d / "mcp-probe/result.json", dict(
                    mode="acceptance", head=SOURCE, tree=TREE, compile_exit=0,
                    probe_sha256=gate.PROBE_SHA, production_source_restored=True,
                    controls_passed=True, acceptance_passed=True,
                    tests={name: {"exit_code": 0, "status": "pass"} for name in gate.PROBES}))
                for name in gate.PROBES:
                    self.write(d / f"mcp-probe/{name}.txt", self.summary(1), raw=True)
            self.rehash(d)
        contracts = self.artifacts / "desktop-package-contracts"
        self.write(contracts / "identity.json", self.ident)
        self.write(contracts / "npm-audit.json", {"metadata": {"vulnerabilities": {"total": 0}}})
        for name, directory in (("desktop", "src-tauri"), ("runtime", "services/local-agent")):
            self.write(contracts / f"rust-audit-{name}.json", {
                "tool": "rustsec/audit-check", "action_sha": gate.RUSTSEC_ACTION_SHA,
                "working_directory": directory,
                "vulnerabilities": {"count": 0, "found": False},
            })
        win_dir = self.artifacts / "desktop-windows-package"
        win_file = win_dir / f"MCP_{gate.VERSION}_x64-setup.exe"
        self.write(win_file, "synthetic binary fixture", raw=True)
        self.write(win_dir / "rc-windows-package.json", {
            **self.ident, "kind": "nsis", "silent_install": True,
            "exact_nsis_payload_verified": True, "real_native_approval": True,
            "package": gate.record(win_file), "payload_sha256": BINARY,
            "native_executable_sha256": BINARY, "signed": False})
        self.write(win_dir / "exclusive-native.json", self.native_proof("nsis", BINARY))
        packages = {}
        for kind, suffix in (("deb", ".deb"), ("appimage", ".AppImage")):
            path = self.artifacts / "desktop-linux-packages" / f"MCP_{gate.VERSION}_amd64{suffix}"
            self.write(path, "synthetic " + kind, raw=True)
            item = gate.record(path)
            packages[kind] = {"artifact": item, "payload_sha256": BINARY}
            digest = BINARY if kind == "deb" else item["sha256"]
            directory = self.artifacts / f"desktop-linux-installed-{kind}"
            self.write(directory / "rc-package.json", {
                **self.ident, "kind": kind, "package": item, "payload_sha256": BINARY,
                "native_executable_sha256": digest})
            self.write(directory / "exclusive-native.json", self.native_proof(kind, digest))
            for case in gate.STARTUP:
                self.write(directory / f"startup-{case}/result.json", dict(
                    source=SOURCE, run_id=RUN, case=case, uid=1001,
                    expected_candidate_behavior_observed=True))
        self.write(self.artifacts / "desktop-linux-packages/exclusive-package.json", {
            **self.ident, "build_kind": "release-candidate", "packages": packages})

    @staticmethod
    def summary(count):
        return f"test result: ok. {count} passed; 0 failed; 0 ignored;\n"

    @staticmethod
    def native_proof(kind, digest):
        value = dict(scenario=stable.SCENARIO, source_sha=SOURCE, run_id=RUN,
                     version=gate.VERSION, package_kind=kind, binary_sha256=digest,
                     build_kind="release-installed", foreign_request_count=100,
                     pending_elapsed_seconds=90, permission_approval_source="native-webdriver-clicks",
                     synthetic_conversation_metadata=True,
                     tests=[{"name": name, "passed": True} for name in stable.TEST_NAMES])
        value.update({key: True for key in ("passed", "real_native_webview", "real_oauth_http",
                     "real_local_ipc", "cleanup_completed", "export_secret_scan_completed")})
        value.update({key: False for key in ("sandbox_disabled", "cleanup_failed",
                     "real_chatgpt_verified", "export_secrets_found")})
        return value

    @staticmethod
    def write(path, value, raw=False):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value if raw else json.dumps(value), encoding="utf-8")

    def rehash(self, d):
        self.write(d / "sha256.json", {p.relative_to(d).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in d.rglob("*") if p.is_file() and p.name != "sha256.json"})

    def check(self):
        return gate.validate(self.root, self.artifacts, SOURCE, TREE, RUN)

    def mutate(self, relative, key, value):
        path = self.artifacts / relative
        data = json.loads(path.read_text())
        data[key] = value
        self.write(path, data)

    def test_complete_synthetic_evidence_fixture_is_consistent(self):
        report, files = self.check()
        self.assertEqual(len(files), 3)
        self.assertFalse(report["scope"]["full_cloud_gateway_release"])
        self.assertFalse(report["windows_authenticode_signed"])
        self.assertEqual(report["installed_native_stages"], {"nsis": 12, "deb": 12, "appimage": 12})

    def test_changed_installer_is_rejected(self):
        path = self.artifacts / "desktop-windows-package" / f"MCP_{gate.VERSION}_x64-setup.exe"
        path.write_bytes(b"changed")
        with self.assertRaises(ValueError): self.check()

    def test_wrong_source_tree_run_or_version_is_rejected(self):
        path = self.artifacts / "desktop-windows-package/rc-windows-package.json"
        original = gate.load(path)
        for key in ("source_sha", "source_tree", "run_id", "version"):
            with self.subTest(key=key):
                self.write(path, {**original, key: "wrong"})
                with self.assertRaises(ValueError): self.check()
        self.write(path, original)

    def test_mismatched_installed_payload_is_rejected(self):
        self.mutate("desktop-linux-installed-deb/rc-package.json", "payload_sha256", "d" * 64)
        with self.assertRaises(ValueError): self.check()

    def test_old_or_failed_or_zero_test_logs_are_rejected(self):
        d = self.artifacts / f"desktop-native-ubuntu-24.04-{RUN}"
        for text in (self.summary(0), self.summary(494),
                     "test result: FAILED. 495 passed; 1 failed; 0 ignored;\n",
                     "test result: ok. 495 passed; 0 failed; 1 ignored;\n"):
            self.write(d / "desktop.txt", text, raw=True)
            self.rehash(d)
            with self.assertRaises(ValueError): self.check()

    def test_mutated_evidence_without_hash_update_is_rejected(self):
        d = self.artifacts / f"desktop-native-ubuntu-24.04-{RUN}"
        self.write(d / "runtime.txt", self.summary(134) + "tampered", raw=True)
        with self.assertRaises(ValueError): self.check()

    def test_skipped_linux_kernel_probes_are_rejected(self):
        d = self.artifacts / f"desktop-native-ubuntu-24.04-{RUN}"
        data = gate.load(d / "results.json")
        data["outcomes"]["PROBE"] = "skipped"
        self.write(d / "results.json", data)
        self.rehash(d)
        with self.assertRaises(ValueError): self.check()

    def test_original_probe_names_and_mode_are_mandatory(self):
        d = self.artifacts / f"desktop-native-ubuntu-24.04-{RUN}"
        path = d / "mcp-probe/result.json"
        data = gate.load(path)
        for key, val in (("mode", "diagnostic"), ("probe_sha256", "e" * 64), ("tests", {})):
            changed = copy.deepcopy(data); changed[key] = val
            self.write(path, changed); self.rehash(d)
            with self.assertRaises(ValueError): self.check()

    def test_native_gui_cannot_be_replaced_with_mock_approval(self):
        self.mutate("desktop-windows-package/exclusive-native.json",
                    "permission_approval_source", "fixture")
        with self.assertRaises(ValueError): self.check()

    def test_physical_chatgpt_pass_cannot_be_invented(self):
        self.mutate("desktop-windows-package/exclusive-native.json", "real_chatgpt_verified", True)
        with self.assertRaises(ValueError): self.check()

    def test_unresolved_dependency_vulnerabilities_are_rejected(self):
        self.write(self.artifacts / "desktop-package-contracts/npm-audit.json",
                   {"metadata": {"vulnerabilities": {"total": 1}}})
        with self.assertRaises(ValueError): self.check()

    def test_boolean_is_not_a_vulnerability_count(self):
        self.write(self.artifacts / "desktop-package-contracts/npm-audit.json",
                   {"metadata": {"vulnerabilities": {"total": False}}})
        with self.assertRaises(ValueError): self.check()


    def test_rust_audit_receipt_provenance_is_mandatory(self):
        path = self.artifacts / "desktop-package-contracts/rust-audit-desktop.json"
        original = gate.load(path)
        for key, value in (("tool", "fixture"), ("action_sha", "0" * 40),
                           ("working_directory", "src-tauri-copy")):
            with self.subTest(key=key):
                self.write(path, {**original, key: value})
                with self.assertRaises(ValueError):
                    self.check()
        self.write(path, original)

    def test_root_startup_observation_is_rejected(self):
        self.mutate("desktop-linux-installed-deb/startup-missing-bus/result.json", "uid", 0)
        with self.assertRaises(ValueError): self.check()

    def test_traversal_in_hash_manifest_is_rejected(self):
        d = self.artifacts / f"desktop-native-ubuntu-24.04-{RUN}"
        self.write(d / "sha256.json", {"../escape": "a" * 64})
        with self.assertRaises(ValueError): self.check()

    def test_duplicate_and_nonfinite_json_are_rejected(self):
        path = self.root / "bad.json"
        for text in ('{"passed":false,"passed":true}', '{"x":NaN}', '{"x":1e9999}', "[]"):
            self.write(path, text, raw=True)
            with self.assertRaises(ValueError): gate.load(path)


if __name__ == "__main__":
    unittest.main()
