#!/usr/bin/env python3
"""Adversarial source/identity checks. Supply the official archive with --archive."""
import argparse
import copy
import json
from pathlib import Path
import shutil
import tempfile
import tomllib
import unittest

import verify_glib_backport as gate

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = None


class BackportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="glib-backport-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "root"
        self.root.mkdir()
        for folder in (gate.VENDOR, gate.PROVENANCE):
            shutil.copytree(ROOT / folder, self.root / folder)
        for name, relative in gate.LOCALS.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if name != "glib":
                shutil.copyfile(ROOT / relative, path)
        self.env = {"CARGO_HOME": str(Path(self.temp.name) / "cargo")}
        self.manifests = gate.verify_configuration(self.root, self.env)
        packages = [{"id": name, "name": name, "version": self.manifests[name]["package"]["version"],
                     "source": None, "manifest_path": str(self.root / relative)} for name, relative in gate.LOCALS.items()]
        packages.append({"id": "registry-package", "name": "registry-package", "version": "1.0.0", "source": gate.REGISTRY})
        self.metadata = {"packages": packages, "resolve": {"root": "coding-tools-mcp-desktop",
                         "nodes": [{"id": p["id"], "deps": []} for p in packages]}}
        self.lock = {"version": 3, "package": [{k: p[k] for k in ("name", "version", "source")} for p in packages]}
        self.lock["package"][-1]["checksum"] = "a" * 64
        self.upstream_lock = tomllib.loads((self.root / gate.PROVENANCE / "upstream-identity.Cargo.lock").read_text())

    def source(self):
        return gate.verify_source(self.root, ARCHIVE)

    def configuration(self):
        return gate.verify_configuration(self.root, self.env)

    def metadata_check(self):
        return gate.verify_metadata(self.root, self.metadata, self.lock, self.manifests)

    def reject(self, callback, code):
        with self.assertRaisesRegex(gate.VerificationError, code):
            callback()

    def append_manifest(self, text):
        path = self.root / "src-tauri/Cargo.toml"
        path.write_text(path.read_text() + text)

    def report(self, lock):
        return {"settings": {"target_arch": [], "target_os": [], "severity": None, "ignore": [],
                             "informational_warnings": ["unmaintained", "unsound", "notice"]},
                "lockfile": {"dependency-count": len(lock["package"])}, "database": {"advisory-count": 1277},
                "vulnerabilities": {"found": False, "count": 0, "list": []}, "warnings": {}}

    def audits(self):
        product = self.report(self.lock)
        product["warnings"]["unmaintained"] = [{"package": self.lock["package"][-1],
                                                "advisory": {"id": "RUSTSEC-2024-0001", "package": "registry-package"}}]
        upstream = self.report(self.upstream_lock)
        upstream["warnings"]["unsound"] = [{"package": self.upstream_lock["package"][0],
                                             "advisory": {"id": gate.ADVISORY, "package": "glib"}}]
        return copy.deepcopy(product), copy.deepcopy(upstream)

    def audit_check(self, product, upstream):
        return gate.verify_audits(product, upstream, self.lock, self.upstream_lock)

    def test_exact_official_source_and_patch(self):
        self.assertEqual(self.source()["source_file_count"], 121)
        self.assertEqual(self.source()["changed_files"], ["src/variant_iter.rs"])

    def test_source_mutations(self):
        for name, action in (
            ("extra", lambda: (self.root / gate.VENDOR / "extra.rs").write_text("extra")),
            ("missing", lambda: (self.root / gate.VENDOR / "src/lib.rs").unlink()),
            ("modified", lambda: (self.root / gate.VENDOR / "src/lib.rs").write_text("bad")),
            ("license", lambda: (self.root / gate.VENDOR / "LICENSE").write_text("changed")),
        ):
            with self.subTest(name=name):
                action()
                self.reject(self.source, "vendor_source_mismatch")
                shutil.rmtree(self.root / gate.VENDOR)
                shutil.copytree(ROOT / gate.VENDOR, self.root / gate.VENDOR)

    def test_source_links(self):
        path = self.root / gate.VENDOR / "linked"
        for target in (self.root / gate.VENDOR / "LICENSE", self.root / gate.VENDOR / "src"):
            with self.subTest(target=target):
                path.symlink_to(target)
                self.reject(self.source, "linked_source")
                path.unlink()

    def test_unpatched_source_rejected(self):
        original = gate.upstream_files(ARCHIVE)
        (self.root / gate.VENDOR / "src/variant_iter.rs").write_bytes(original["src/variant_iter.rs"])
        self.reject(self.source, "vendor_source_mismatch")

    def test_inventory_cannot_bless_modified_source(self):
        path = self.root / gate.VENDOR / "src/lib.rs"
        path.write_bytes(path.read_bytes() + b"\n// extra source\n")
        p = self.root / gate.PROVENANCE / "provenance.json"
        data = json.loads(p.read_text())
        data["patched_files"]["src/lib.rs"] = gate.sha(path.read_bytes())
        p.write_text(json.dumps(data))
        self.reject(self.source, "vendor_source_mismatch")

    def test_provenance_mutations(self):
        path = self.root / gate.PROVENANCE / "provenance.json"
        original = path.read_text()
        for key, value in (("schema", True), ("archive_url", "https://example.org"), ("upstream_fix_commit", "a" * 40),
                           ("archive_sha256", "0" * 64), ("license_sha256", "0" * 64), ("upstream_files", {}), ("patched_files", {})):
            with self.subTest(key=key):
                data = json.loads(original)
                data[key] = value
                path.write_text(json.dumps(data))
                self.reject(self.source, "wrong_provenance")

    def test_patch_mutation(self):
        (self.root / gate.PROVENANCE / "RUSTSEC-2024-0429.patch").write_text("bad patch")
        self.reject(self.source, "wrong_backport_patch")

    def test_archive_mutation(self):
        path = Path(self.temp.name) / "bad.crate"
        path.write_bytes(ARCHIVE.read_bytes() + b"bad")
        self.reject(lambda: gate.verify_source(self.root, path), "wrong_official_archive")

    def test_upstream_identity_mutations(self):
        path = self.root / gate.PROVENANCE / "upstream-identity.Cargo.lock"
        original = path.read_text()
        for before, after in (("0.18.5", "0.20.0"), (gate.REGISTRY, "registry+https://example.org/index"),
                              (gate.ARCHIVE_SHA, "0" * 64)):
            with self.subTest(before=before):
                path.write_text(original.replace(before, after))
                self.reject(self.source, "wrong_upstream_identity")

    def test_expected_configuration(self):
        self.assertEqual(set(self.configuration()), set(gate.LOCALS))

    def test_extra_patch_and_replace(self):
        self.append_manifest('\n[patch."https://example.org/index"]\nextra = { git = "https://example.org/repo" }\n')
        self.reject(self.configuration, "unreviewed_manifest_remap")
        shutil.copyfile(ROOT / "src-tauri/Cargo.toml", self.root / "src-tauri/Cargo.toml")
        self.append_manifest('\n[replace]\n"extra:1.0.0" = { path = "../extra" }\n')
        self.reject(self.configuration, "unreviewed_manifest_remap")

    def test_extra_dependency_remaps(self):
        for source in ('path = "../fake"', 'git = "https://example.org/repo"', 'registry = "alternate"',
                       'registry-index = "https://example.org/index"'):
            with self.subTest(source=source):
                self.append_manifest('\n[target.\'cfg(any())\'.dependencies.unreviewed]\nversion = "1"\n' + source + '\n')
                self.reject(self.configuration, "unreviewed_dependency_remap")
                shutil.copyfile(ROOT / "src-tauri/Cargo.toml", self.root / "src-tauri/Cargo.toml")

    def test_approved_path_cannot_be_retargeted(self):
        path = self.root / "src-tauri/Cargo.toml"
        path.write_text(path.read_text().replace('../services/cloud-agent', '../other-agent'))
        self.reject(self.configuration, "unreviewed_dependency_remap")

    def test_transitive_manifest_remap(self):
        path = self.root / "services/cloud-agent/Cargo.toml"
        path.write_text(path.read_text() + '\n[patch.crates-io]\nother = { path = "../../other" }\n')
        self.reject(self.configuration, "unreviewed_manifest_remap")

    def test_cargo_config_locations(self):
        for base in (self.root / "src-tauri/.cargo", self.root / ".cargo", self.root.parent / ".cargo", Path(self.env["CARGO_HOME"])):
            for name in ("config", "config.toml"):
                with self.subTest(base=base, name=name):
                    base.mkdir(parents=True, exist_ok=True)
                    path = base / name
                    path.write_text('[source.crates-io]\nreplace-with="other"\n')
                    self.reject(self.configuration, "unreviewed_cargo_configuration")
                    path.unlink()

    def test_cargo_source_environment(self):
        for key in ("CARGO_SOURCE_CRATES_IO_REPLACE_WITH", "CARGO_REGISTRY_DEFAULT", "CARGO_REGISTRIES_OTHER_INDEX",
                    "CARGO_PATCH_CRATES_IO_EXTRA_PATH", "CARGO_REPLACE_EXTRA", "CARGO_ALIAS_METADATA"):
            with self.subTest(key=key):
                self.env[key] = "other"
                self.reject(self.configuration, "source_override_environment")
                del self.env[key]

    def test_expected_metadata(self):
        self.assertEqual(self.metadata_check(), 5)

    def test_path_git_and_registry_remapped_metadata(self):
        for source in (None, "git+https://example.org/repo#" + "a" * 40, "registry+https://example.org/index"):
            with self.subTest(source=source):
                self.metadata["packages"][-1]["source"] = source
                self.lock["package"][-1]["source"] = source
                self.reject(self.metadata_check, "unreviewed_local_package|unreviewed_registry_or_git_source")

    def test_approved_package_wrong_path(self):
        self.metadata["packages"][3]["manifest_path"] = str(self.root / "other-glib/Cargo.toml")
        self.reject(self.metadata_check, "unreviewed_local_manifest")

    def test_local_package_wrong_version(self):
        self.metadata["packages"][3]["version"] = "0.20.0"
        self.lock["package"][3]["version"] = "0.20.0"
        self.reject(self.metadata_check, "wrong_local_version")

    def test_duplicate_package_id(self):
        self.metadata["packages"].append(self.metadata["packages"][0])
        self.reject(self.metadata_check, "duplicate_package_id")

    def test_missing_lock_or_graph_package(self):
        self.lock["package"].pop()
        self.reject(self.metadata_check, "metadata_lock_disagreement")

    def test_missing_resolved_node(self):
        self.metadata["resolve"]["nodes"].pop()
        self.reject(self.metadata_check, "incomplete_resolved_graph")

    def test_unknown_resolved_dependency(self):
        self.metadata["resolve"]["nodes"][0]["deps"] = [{"pkg": "unmapped"}]
        self.reject(self.metadata_check, "unmapped_resolved_dependency")

    def test_both_reports_keep_findings(self):
        product, upstream = self.audits()
        result = self.audit_check(product, upstream)
        self.assertFalse(result["release_approved"])
        self.assertFalse(result["raw_zero_claim"])
        self.assertEqual(result["product_warnings"], product["warnings"])
        self.assertEqual(result["upstream_identity_warnings"], upstream["warnings"])

    def test_missing_unsound_advisory(self):
        product, upstream = self.audits()
        upstream["warnings"] = {}
        self.reject(lambda: self.audit_check(product, upstream), "missing_upstream_unsound_advisory")

    def test_filtered_reports(self):
        for which in (0, 1):
            for key, value in (("ignore", [gate.ADVISORY]), ("severity", "high"), ("target_os", ["windows"]),
                               ("informational_warnings", ["unmaintained"])):
                with self.subTest(which=which, key=key):
                    reports = self.audits()
                    reports[which]["settings"][key] = value
                    self.reject(lambda: self.audit_check(*reports), "filtered_audit")

    def test_wrong_audit_counts(self):
        product, upstream = self.audits()
        product["vulnerabilities"]["count"] = True
        self.reject(lambda: self.audit_check(product, upstream), "wrong_audit_counts")

    def test_wrong_audit_package_identity(self):
        product, upstream = self.audits()
        upstream["warnings"]["unsound"][0]["package"]["checksum"] = "0" * 64
        self.reject(lambda: self.audit_check(product, upstream), "unmapped_audit_identity")

    def test_new_upstream_advisory_is_unreviewed(self):
        product, upstream = self.audits()
        finding = copy.deepcopy(upstream["warnings"]["unsound"][0])
        finding["advisory"]["id"] = "RUSTSEC-2026-0001"
        upstream["vulnerabilities"] = {"found": True, "count": 1, "list": [finding]}
        self.reject(lambda: self.audit_check(product, upstream), "unreviewed_upstream_advisory")

    def test_other_product_vulnerability_remains_visible(self):
        product, upstream = self.audits()
        finding = product["warnings"]["unmaintained"][0]
        product["vulnerabilities"] = {"found": True, "count": 1, "list": [finding]}
        self.assertEqual(self.audit_check(product, upstream)["product_vulnerabilities"], [finding])

    def test_duplicate_json_key(self):
        self.reject(lambda: gate.decode('{"schema":1,"schema":1}'), "duplicate_json_key")

    def test_workspace_dependency_remap(self):
        self.append_manifest('\n[workspace.dependencies.unreviewed]\ngit="https://example.org/repo"\n')
        self.reject(self.configuration, "unreviewed_dependency_remap")

    def test_workspace_member_extra_local_package(self):
        extra = {"id": "unexpected", "name": "unexpected", "version": "1.0.0", "source": None,
                 "manifest_path": str(self.root / "unexpected/Cargo.toml")}
        self.metadata["packages"].append(extra)
        self.metadata["resolve"]["nodes"].append({"id": "unexpected", "deps": []})
        self.lock["package"].append({k: extra[k] for k in ("name", "version", "source")})
        self.reject(self.metadata_check, "unreviewed_local_package")

    def test_source_parent_symlinks(self):
        for name in ("vendor", "patches"):
            with self.subTest(name=name):
                path = self.root / name
                moved = self.root / (name + "-moved")
                path.rename(moved)
                path.symlink_to(moved, target_is_directory=True)
                self.reject(self.source, "linked_source_parent")
                path.unlink()
                moved.rename(path)

    def test_relative_cargo_home_config(self):
        self.env["CARGO_HOME"] = "relative-cargo-home"
        path = self.root / "relative-cargo-home/config.toml"
        path.parent.mkdir()
        path.write_text('[paths]\n')
        self.reject(self.configuration, "unreviewed_cargo_configuration")

    def test_glib_patch_cannot_carry_registry_or_git_override(self):
        path = self.root / "src-tauri/Cargo.toml"
        text = path.read_text()
        path.write_text(text.replace('{ path = "../vendor/glib-0.18.5" }', '{ path = "../vendor/glib-0.18.5", git = "https://example.org/repo" }'))
        self.reject(self.configuration, "unreviewed_manifest_remap")

    def test_metadata_missing_expected_glib(self):
        self.metadata["packages"] = [p for p in self.metadata["packages"] if p["name"] != "glib"]
        self.lock["package"] = [p for p in self.lock["package"] if p["name"] != "glib"]
        self.reject(self.metadata_check, "missing_expected_local_package")

    def test_upstream_advisory_wrong_id(self):
        product, upstream = self.audits()
        upstream["warnings"]["unsound"][0]["advisory"]["id"] = "RUSTSEC-2024-0000"
        self.reject(lambda: self.audit_check(product, upstream), "missing_upstream_unsound_advisory")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--archive", type=Path, required=True)
    args, remaining = parser.parse_known_args()
    ARCHIVE = args.archive.resolve()
    gate.upstream_files(ARCHIVE)
    unittest.main(argv=[__file__, *remaining])
