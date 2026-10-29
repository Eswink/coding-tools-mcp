#!/usr/bin/env python3
"""Fail-closed verifier contracts. Synthetic events are never release evidence."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import exact_build_audit as gate

ROOT = "path+file:///repo/services/cloud-gateway#coding-tools-cloud-gateway@0.1.0"
DEP = "registry+https://github.com/rust-lang/crates.io-index#fixture-dep@1.0.0"
RSA = "registry+https://github.com/rust-lang/crates.io-index#rsa@0.9.10"
REGISTRY = "registry+https://github.com/rust-lang/crates.io-index"


def target(name, kind):
    return {"name": name, "kind": [kind], "src_path": "/repo/services/cloud-gateway/src/" + name + ".rs"}


def artifact(pid, t, features=(), fresh=True):
    name, kind = t["name"], t["kind"]
    exe = "/build/x86_64-unknown-linux-gnu/release/" + name if kind == ["bin"] else None
    return {"reason": "compiler-artifact", "package_id": pid, "manifest_path": "/repo/" + gate.MANIFEST if pid == ROOT else ("/registry/fixture-dep/Cargo.toml" if pid == DEP else "/registry/rsa/Cargo.toml"), "target": copy.deepcopy(t), "features": list(features),
            "fresh": fresh, "profile": {"test": False, "debug_assertions": False, "opt_level": "3"},
            "executable": exe, "filenames": [exe] if exe else ["/build/lib" + name + ".rlib"]}


class Fixture:
    def __init__(self):
        self.expected = {"sha": "1" * 40, "tree": "2" * 40, "lock_sha256": "3" * 64,
                         "manifest_sha256": "4" * 64, "product_version": "0.6.2-rc.1", "target": "x86_64-unknown-linux-gnu"}
        self.envelope = {"schema": 1, "ci": {"provider": "local"}, **self.expected, "source_root": "/repo", "build_exit": 0,
                         "advisory_acquisition": {"method": "existing_local_snapshot", "command": [], "started_at": "2026-09-30T12:00:00.000000Z", "completed_at": "2026-09-30T12:00:00.000001Z"},
                         "audit_exit": 1, "advisory_db_commit": "5" * 40,
                         "advisory_database": {"commit": "5" * 40, "tree": "7" * 40, "contents_sha256": "8" * 64, "clean": True, "file_count": 1300, "origin": "https://github.com/RustSec/advisory-db.git"},
                         "features": {"default": True, "all": False, "selected": []},
                         "toolchain": {"cargo": "cargo 1.91.0", "rustc": "rustc 1.91.0"},
                         "build_command": gate.build_command(self.expected["target"]),
                         "audit_version": "cargo-audit 0.22.2", "audit_binary_sha256": "6" * 64,
                         "verifier_sha256": gate.digest(Path(gate.__file__).read_bytes())}
        root = {"id": ROOT, "name": gate.ROOT_NAME, "version": "0.1.0", "source": None,
                "manifest_path": "/repo/" + gate.MANIFEST, "targets": [target(n, "bin") for n in sorted(gate.BINS)] + [target("coding_tools_cloud_gateway", "lib")]}
        dep = {"id": DEP, "name": "fixture-dep", "version": "1.0.0", "source": REGISTRY,
               "manifest_path": "/registry/fixture-dep/Cargo.toml", "targets": [target("fixture_dep", "lib"), target("build-script-build", "custom-build")]}
        rsa = {"id": RSA, "name": "rsa", "version": "0.9.10", "source": REGISTRY,
               "manifest_path": "/registry/rsa/Cargo.toml", "targets": [target("rsa", "lib")]}
        self.metadata = {"resolve": {"root": ROOT}, "packages": [root, dep, rsa]}
        self.lock = {"package": [{"name": p["name"], "version": p["version"], **({"source": p["source"], "checksum": "a" * 64} if p["source"] else {})} for p in (root, dep, rsa)]}
        self.selected = "coding-tools-cloud-gateway v0.1.0 (/repo/services/cloud-gateway)\t\nfixture-dep v1.0.0\tdefault\n"
        self.conservative = self.selected
        self.events = [artifact(ROOT, t) for t in root["targets"]] + [artifact(DEP, t, ["default"]) for t in dep["targets"]] + [{"reason": "build-finished", "success": True}]
        self.audit = {"database": {"last-commit": "5" * 40, "advisory-count": 1277},
                      "lockfile": {"dependency-count": 3}, "warnings": {"unmaintained": [{"package": "canary"}]},
                      "settings": {"ignore": [], "target_arch": [], "target_os": [], "severity": None,
                                   "informational_warnings": ["unmaintained", "unsound", "notice"]},
                      "vulnerabilities": {"found": True, "count": 1, "list": [{"package": self.lock["package"][2], "advisory": {"id": "RUSTSEC-2023-0071"}}]}}

    def run(self):
        return gate.verify_records(self.envelope, self.metadata, self.selected, self.conservative,
                                   "\n".join(json.dumps(e) for e in self.events), self.audit, self.lock, self.expected)


class Contracts(unittest.TestCase):
    def rejected(self, mutate):
        f = Fixture()
        mutate(f)
        with self.assertRaises((gate.EvidenceError, KeyError, TypeError)):
            f.run()

    def test_nonstandard_json_numbers_and_boolean_schema_fail(self):
        for value in ("NaN", "Infinity", "-Infinity", "1e999"):
            with self.subTest(value=value), self.assertRaises(gate.EvidenceError):
                gate.decode('{"ignored":' + value + '}')
        for value in (True, 1.0, "1", None):
            self.rejected(lambda f, value=value: f.envelope.update(schema=value))

    def test_github_product_producer_binding(self):
        f = Fixture()
        f.envelope["ci"] = {"provider": "github-actions", "sha": f.expected["sha"], "repository": "Eswink/coding-tools-mcp", "workflow_ref": "Eswink/coding-tools-mcp/.github/workflows/audit.yml@refs/heads/ci", "run_id": "123", "run_attempt": "1", "job": "build", "runner_os": "Linux"}
        f.envelope["toolchain"] = {"rustc": "rustc 1.98.1 (hash date)", "cargo": "cargo 1.98.1 (hash date)"}
        f.envelope["advisory_acquisition"].update(method="fresh_official_clone", command=["git", "clone", "--depth", "1", "https://github.com/RustSec/advisory-db.git"], exit=0)
        f.run()
        for field, value in (("repository", "attacker/coding-tools-mcp"), ("repository", "Eswink/coding-tools-mcp-fork"), ("workflow_ref", "attacker/repo/.github/workflows/audit.yml@refs/heads/main")):
            bad = copy.deepcopy(f)
            bad.envelope["ci"][field] = value
            with self.assertRaises(gate.EvidenceError):
                bad.run()
        for tool in ("rustc", "cargo"):
            for version in ("1.98.0", "1.98.10", "1.98.1-nightly"):
                bad = copy.deepcopy(f)
                bad.envelope["toolchain"][tool] = tool + " " + version
                with self.assertRaises(gate.EvidenceError):
                    bad.run()
        bad = copy.deepcopy(f)
        bad.envelope["advisory_acquisition"].update(method="existing_local_snapshot", command=[])
        with self.assertRaises(gate.EvidenceError):
            bad.run()

    def test_advisory_acquisition_provenance_failures(self):
        self.rejected(lambda f: f.envelope.pop("advisory_acquisition"))
        self.rejected(lambda f: f.envelope["advisory_acquisition"].update(started_at="unknown"))
        self.rejected(lambda f: f.envelope["advisory_acquisition"].update(completed_at="2020-01-01T00:00:00.000000Z"))
        self.rejected(lambda f: f.envelope["advisory_acquisition"].update(method="fresh_official_clone", command=["untrusted"], exit=0))
        self.rejected(lambda f: f.envelope["advisory_acquisition"].update(method="fresh_official_clone", command=["git", "clone", "--depth", "1", "https://github.com/RustSec/advisory-db.git"], exit=True))

    def test_unused_raw_finding_is_preserved_and_fresh_units_are_included(self):
        r = Fixture().run()
        self.assertEqual(r["raw_vulnerability_count"], 1)
        self.assertEqual(r["active_vulnerability_count"], 0)
        self.assertEqual(r["raw_lock_audit"], "findings_present")
        self.assertIn("unmaintained", r["raw_warnings"])
        self.assertEqual(r["selected_package_count"], 2)
        self.assertEqual(r["compiler_artifact_events"], 7)

    def test_removing_dependency_with_roots_and_success_kept_fails(self):
        self.rejected(lambda f: setattr(f, "events", [e for e in f.events if e.get("package_id") != DEP]))

    def test_removing_one_build_script_unit_while_package_stays_fails(self):
        self.rejected(lambda f: setattr(f, "events", [e for e in f.events if e.get("target", {}).get("kind") != ["custom-build"]]))

    def test_missing_root_and_extra_root_fail(self):
        self.rejected(lambda f: f.events.pop(0))
        self.rejected(lambda f: f.events.insert(0, artifact(ROOT, target("unexpected", "bin"))))

    def test_failed_missing_duplicate_or_nonterminal_finish_fail(self):
        self.rejected(lambda f: f.events[-1].update(success=False))
        self.rejected(lambda f: f.events.pop())
        self.rejected(lambda f: f.events.append({"reason": "build-finished", "success": True}))
        self.rejected(lambda f: f.envelope.update(build_exit=101))

    def test_wrong_expected_sha_tree_lock_manifest_target_version_fail(self):
        for field in Fixture().expected:
            with self.subTest(field=field):
                self.rejected(lambda f, field=field: f.expected.update({field: "wrong"}))

    def test_wrong_build_command_features_or_toolchain_fail(self):
        self.rejected(lambda f: f.envelope["build_command"].remove("--locked"))
        self.rejected(lambda f: f.envelope["features"].update(all=True))
        self.rejected(lambda f: f.envelope["toolchain"].update(rustc="rustc nightly"))
        self.rejected(lambda f: f.envelope.update(audit_version="cargo-audit 0.1.0"))
        self.rejected(lambda f: f.envelope.update(verifier_sha256="0" * 64))

    def test_compiler_paths_and_ci_provenance_are_bound(self):
        self.rejected(lambda f: f.events[0].update(manifest_path="/foreign/Cargo.toml"))
        self.rejected(lambda f: f.events[0]["target"].update(src_path="/foreign/main.rs"))
        self.rejected(lambda f: f.envelope.update(ci={"provider": "github-actions", "sha": "wrong"}))
        self.rejected(lambda f: f.envelope.pop("ci"))

    def test_unmapped_version_source_and_extra_artifact_fail(self):
        self.rejected(lambda f: f.events[0].update(package_id="unmapped"))
        self.rejected(lambda f: f.lock["package"][1].update(version="2.0.0"))
        self.rejected(lambda f: f.lock["package"][1].update(source="registry+https://foreign.invalid"))
        self.rejected(lambda f: f.events.insert(0, artifact(RSA, target("rsa", "lib"))))

    def test_omitted_tree_and_ambiguous_metadata_fail(self):
        self.rejected(lambda f: setattr(f, "selected", f.selected.splitlines()[0] + "\n"))
        self.rejected(lambda f: f.metadata["packages"].append({**f.metadata["packages"][1], "id": "other", "source": "other"}))

    def test_active_rsa_and_any_other_advisory_fail(self):
        def active(f):
            f.selected += "rsa v0.9.10\t\n"
            f.conservative = f.selected
            f.events.insert(-1, artifact(RSA, target("rsa", "lib")))
        self.rejected(active)
        def other(f):
            f.audit["vulnerabilities"]["list"][0] = {"package": f.lock["package"][1], "advisory": {"id": "RUSTSEC-2099-9999"}}
        self.rejected(other)

    def test_conservative_graph_finding_cannot_be_dismissed(self):
        self.rejected(lambda f: setattr(f, "conservative", f.conservative + "rsa v0.9.10\t\n"))

    def test_artifact_feature_difference_test_profile_and_missing_fresh_fail(self):
        self.rejected(lambda f: f.events[0].update(features=["unexpected"]))
        self.rejected(lambda f: f.events[0]["profile"].update(test=True))
        self.rejected(lambda f: f.events[0]["profile"].update(opt_level="0"))
        self.rejected(lambda f: f.events[0].pop("fresh"))

    def test_filtered_or_suppressed_raw_audit_fails(self):
        self.rejected(lambda f: f.audit["settings"].update(ignore=["RUSTSEC-2023-0071"]))
        self.rejected(lambda f: f.audit["settings"].update(target_os=["linux"]))
        self.rejected(lambda f: f.audit["settings"].update(severity="critical"))
        self.rejected(lambda f: f.audit["settings"].update(informational_warnings=[]))

    def test_raw_finding_count_exit_database_checksum_tampering_fails(self):
        self.rejected(lambda f: f.audit["vulnerabilities"].update(count=0))
        self.rejected(lambda f: f.envelope.update(audit_exit=0))
        self.rejected(lambda f: f.audit["database"].update({"last-commit": "0" * 40}))
        self.rejected(lambda f: f.audit["lockfile"].update({"dependency-count": 1}))
        def checksum(f):
            f.audit = copy.deepcopy(f.audit)
            f.audit["vulnerabilities"]["list"][0]["package"]["checksum"] = "b" * 64
        self.rejected(checksum)

    def test_no_fetch_null_git_telemetry_needs_independent_snapshot(self):
        f = Fixture()
        f.audit["database"]["last-commit"] = None
        f.audit["database"]["last-updated"] = None
        self.assertEqual(f.run()["raw_vulnerability_count"], 1)
        self.rejected(lambda f: f.envelope.pop("advisory_database"))
        self.rejected(lambda f: f.envelope["advisory_database"].update(contents_sha256=""))
        self.rejected(lambda f: f.envelope["advisory_database"].update(file_count=1))
        self.rejected(lambda f: f.envelope["advisory_database"].update(clean=False))

    def test_malformed_duplicate_json_is_rejected(self):
        for raw in ('{"reason":"build-finished","reason":"compiler-artifact"}', '{', 'null'):
            with self.subTest(raw=raw):
                with self.assertRaises((gate.EvidenceError, AttributeError)):
                    event = gate.decode(raw)
                    if not isinstance(event, dict):
                        raise gate.EvidenceError("invalid_event")

    def test_extracted_four_binary_hashes_and_missing_or_modified_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            f = Fixture()
            streams = {"metadata.json": json.dumps(f.metadata), "selected-tree.txt": f.selected,
                       "conservative-tree.txt": f.conservative, "build.jsonl": "\n".join(json.dumps(e) for e in f.events),
                       "raw-audit.json": json.dumps(f.audit)}
            for name, contents in streams.items():
                (root / name).write_text(contents)
            lock_lines = ["version = 4"]
            for p in f.lock["package"]:
                lock_lines.append("[[package]]")
                lock_lines.extend(k + " = " + json.dumps(v) for k, v in p.items())
            (root / gate.LOCK).parent.mkdir(parents=True)
            (root / gate.LOCK).write_text("\n".join(lock_lines))
            binaries = root / "extracted" / "bin"
            binaries.mkdir(parents=True)
            hashes = {}
            for name in gate.BINS:
                data = ("synthetic-binary-" + name).encode()
                (binaries / name).write_bytes(data)
                hashes[name] = gate.digest(data)
            envelope = {**f.envelope, "streams": {n: gate.digest((root / n).read_bytes()) for n in gate.STREAMS}, "binary_sha256": hashes}
            raw = json.dumps(envelope).encode()
            (root / "envelope.json").write_bytes(raw)
            def verify():
                return gate.verify(root, root, f.expected["sha"], f.expected["product_version"], f.expected["target"], gate.digest(raw), binaries)
            tracked = gate.MANIFEST + "\n" + "\n".join(t["src_path"].removeprefix("/repo/") for t in f.metadata["packages"][0]["targets"])
            with patch.object(gate, "source_identity", return_value=f.expected), patch.object(gate, "git", return_value=tracked):
                self.assertEqual(verify()["raw_lock_audit"], "findings_present")
                victim = binaries / sorted(gate.BINS)[0]
                before = victim.read_bytes()
                victim.write_bytes(before + b"tamper")
                with self.assertRaisesRegex(gate.EvidenceError, "binary_hash_mismatch"):
                    verify()
                victim.unlink()
                with self.assertRaisesRegex(gate.EvidenceError, "missing_binary"):
                    verify()
                victim.write_bytes(before)
                changed = copy.deepcopy(f.audit)
                changed["vulnerabilities"] = {"found": False, "count": 0, "list": []}
                (root / "raw-audit.json").write_text(json.dumps(changed))
                with self.assertRaisesRegex(gate.EvidenceError, "evidence_stream_tampered"):
                    verify()
                envelope["streams"]["raw-audit.json"] = gate.digest((root / "raw-audit.json").read_bytes())
                (root / "envelope.json").write_text(json.dumps(envelope))
                with self.assertRaisesRegex(gate.EvidenceError, "untrusted_envelope_digest"):
                    verify()

    def test_external_digest_and_stream_hashes_reject_modified_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            f = Fixture()
            envelope = {**f.envelope, "streams": {n: "0" * 64 for n in gate.STREAMS}}
            raw = json.dumps(envelope).encode()
            (root / "envelope.json").write_bytes(raw)
            with patch.object(gate, "source_identity", return_value=f.expected):
                with self.assertRaisesRegex(gate.EvidenceError, "untrusted_envelope_digest"):
                    gate.verify(root, root, f.expected["sha"], f.expected["product_version"], f.expected["target"], "f" * 64)
                for name in gate.STREAMS:
                    (root / name).write_text("tampered")
                with self.assertRaisesRegex(gate.EvidenceError, "evidence_stream_tampered"):
                    gate.verify(root, root, f.expected["sha"], f.expected["product_version"], f.expected["target"], gate.digest(raw))


if __name__ == "__main__":
    unittest.main()
