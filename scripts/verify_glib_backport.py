#!/usr/bin/env python3
"""Verify one exact GLib source backport; never grants raw-zero/release approval.

Requires the separately downloaded, checksum-pinned official crate. Cargo metadata
is collected, not supplied by the caller. Optional audit capture keeps BOTH raw
product and upstream-identity reports; local path crates are not registry-audited.
"""
import argparse
import difflib
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import tomllib

ARCHIVE_SHA = "233daaf6e83ae6a12a52055f568f9d7cf4671dabb78ff9560ab6da230ce00ee5"
REGISTRY = "registry+https://github.com/rust-lang/crates.io-index"
VENDOR = "vendor/glib-0.18.5"
PROVENANCE = "patches/glib-0.18.5"
FIX = "b5a4071e439bef2b5eea76c3aa25e5ae84839e34"
ADVISORY = "RUSTSEC-2024-0429"
LOCALS = {
    "coding-tools-mcp-desktop": "src-tauri/Cargo.toml",
    "coding-tools-cloud-agent": "services/cloud-agent/Cargo.toml",
    "coding-tools-local-agent": "services/local-agent/Cargo.toml",
    "glib": VENDOR + "/Cargo.toml",
}
PATH_DEPS = {
    ("src-tauri/Cargo.toml", "dependencies", "coding-tools-cloud-agent"): {"path": "../services/cloud-agent"},
    ("src-tauri/Cargo.toml", "target", "cfg(target_os = \"linux\")", "dependencies", "coding-tools-local-agent"): {"path": "../services/local-agent"},
}


class VerificationError(ValueError):
    pass


def need(condition, code):
    if not condition:
        raise VerificationError(code)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    need(path.is_file() and not path.is_symlink(), "missing_or_linked_file:" + str(path))
    need(path.stat().st_size <= 64 * 1024 * 1024, "oversized_file")
    return path.read_bytes()


def decode(data):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, "duplicate_json_key")
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(VerificationError("nonfinite_json")))


def tree_files(directory):
    need(directory.is_dir() and not directory.is_symlink(), "missing_or_linked_directory")
    result = {}
    for base, dirs, files in os.walk(directory, followlinks=False):
        for name in dirs + files:
            path = Path(base) / name
            need(not path.is_symlink(), "linked_source")
        for name in files:
            path = Path(base) / name
            result[path.relative_to(directory).as_posix()] = read(path)
    return result


def upstream_files(archive):
    data = read(archive)
    need(sha(data) == ARCHIVE_SHA, "wrong_official_archive")
    result = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as stream:
        for member in stream:
            path = PurePosixPath(member.name)
            need(member.isfile() and path.parts[0] == "glib-0.18.5" and ".." not in path.parts,
                 "invalid_archive_member")
            name = path.relative_to("glib-0.18.5").as_posix()
            need(name not in result, "duplicate_archive_member")
            result[name] = stream.extractfile(member).read()
    need(len(result) == 121, "wrong_upstream_file_count")
    return result


def expected_patch(files):
    old = files["src/variant_iter.rs"]
    new = old
    for before, after in (
        (b"let p: *mut libc::c_char = std::ptr::null_mut();", b"let mut p: *mut libc::c_char = std::ptr::null_mut();"),
        (b"                &p,", b"                &mut p,"),
    ):
        need(new.count(before) == 1, "unexpected_upstream_context")
        new = new.replace(before, after)
    patch = "".join(difflib.unified_diff(old.decode().splitlines(True), new.decode().splitlines(True),
                   fromfile="a/src/variant_iter.rs", tofile="b/src/variant_iter.rs")).encode()
    return {**files, "src/variant_iter.rs": new}, patch


def verify_source(root, archive):
    original = upstream_files(archive)
    expected, patch = expected_patch(original)
    need(not (root / "vendor").is_symlink() and not (root / "patches").is_symlink(), "linked_source_parent")
    need(tree_files(root / VENDOR) == expected, "vendor_source_mismatch")
    evidence = root / PROVENANCE
    need(not evidence.is_symlink(), "linked_provenance")
    need(read(evidence / "RUSTSEC-2024-0429.patch") == patch, "wrong_backport_patch")
    provenance = decode(read(evidence / "provenance.json"))
    expected_provenance = {
        "schema": 1, "name": "glib", "version": "0.18.5",
        "archive_url": "https://static.crates.io/crates/glib/glib-0.18.5.crate",
        "archive_sha256": ARCHIVE_SHA,
        "crate_source_commit": "42b9caf98e03ded086362d9653ca58fe94dc8658",
        "upstream_fix_commit": FIX,
        "upstream_fix_url": "https://github.com/gtk-rs/gtk-rs-core/commit/" + FIX,
        "advisory": ADVISORY, "license": "MIT", "license_sha256": sha(original["LICENSE"]),
        "patch_sha256": sha(patch),
        "upstream_files": {name: sha(data) for name, data in original.items()},
        "patched_files": {name: sha(data) for name, data in expected.items()},
    }
    need(type(provenance.get("schema")) is int and provenance == expected_provenance, "wrong_provenance")
    identity = tomllib.loads(read(evidence / "upstream-identity.Cargo.lock").decode())
    need(identity == {"version": 3, "package": [{"name": "glib", "version": "0.18.5", "source": REGISTRY,
                                                "checksum": ARCHIVE_SHA}]}, "wrong_upstream_identity")
    return {"upstream_archive_sha256": ARCHIVE_SHA, "upstream_fix_commit": FIX,
            "source_file_count": len(original), "changed_files": ["src/variant_iter.rs"],
            "patch_sha256": sha(patch), "provenance_sha256": sha(read(evidence / "provenance.json"))}


def verify_configuration(root, environment):
    """Reject overrides before fixed-command Cargo invocation; no config whitelist."""
    start = root / "src-tauri"
    locations = [start, *start.parents]
    home = Path(environment.get("CARGO_HOME", str(Path.home() / ".cargo")))
    if not home.is_absolute():
        home = root / home  # Cargo is invoked with cwd=root, independently of this process cwd.
    candidates = [base / ".cargo" / name for base in locations for name in ("config", "config.toml")]
    candidates += [home / name for name in ("config", "config.toml")]
    for path in candidates:
        need(not path.exists() and not path.is_symlink(), "unreviewed_cargo_configuration:" + str(path))
    for key in environment:
        need(not key.startswith(("CARGO_SOURCE_", "CARGO_REGISTRY_", "CARGO_REGISTRIES_", "CARGO_PATCH_",
                                 "CARGO_REPLACE_", "CARGO_ALIAS_")), "source_override_environment:" + key)
    manifests = {}
    for name, relative in LOCALS.items():
        path = root / relative
        need(not any(p.is_symlink() for p in [path, *path.parents] if p != root.parent), "linked_local_manifest")
        manifest = tomllib.loads(read(path).decode())
        need(manifest.get("package", {}).get("name") == name, "wrong_local_package")
        expected = {"crates-io": {"glib": {"path": "../vendor/glib-0.18.5"}}} if relative == "src-tauri/Cargo.toml" else None
        need(manifest.get("patch") == expected and "replace" not in manifest, "unreviewed_manifest_remap")
        def walk(value, trail):
            if not isinstance(value, dict):
                return
            for key, child in value.items():
                if key in ("dependencies", "dev-dependencies", "build-dependencies"):
                    for dep, spec in child.items():
                        if isinstance(spec, dict) and any(k in spec for k in ("path", "git", "registry", "registry-index")):
                            need(PATH_DEPS.get((relative, *trail, key, dep)) == spec, "unreviewed_dependency_remap")
                walk(child, (*trail, key))
        walk(manifest, ())
        manifests[name] = manifest
    return manifests


def package_key(package):
    return package["name"], package["version"], package.get("source")


def verify_metadata(root, metadata, lock, manifests):
    packages = metadata.get("packages", [])
    need(isinstance(packages, list) and packages, "missing_metadata_packages")
    by_id = {p["id"]: p for p in packages}
    need(len(by_id) == len(packages), "duplicate_package_id")
    locked = {package_key(p): p for p in lock.get("package", [])}
    need(len(locked) == len(lock.get("package", [])), "duplicate_lock_identity")
    need({package_key(p) for p in packages} == set(locked) and len(packages) == len(locked), "metadata_lock_disagreement")
    locals_seen = set()
    for package in packages:
        source = package.get("source")
        if source is None:
            name = package["name"]
            need(name in LOCALS and name not in locals_seen, "unreviewed_local_package")
            need(package["manifest_path"] == str(root / LOCALS[name]), "unreviewed_local_manifest")
            need(package["version"] == manifests[name]["package"]["version"], "wrong_local_version")
            need("checksum" not in locked[package_key(package)], "local_registry_checksum")
            locals_seen.add(name)
        else:
            need(source == REGISTRY, "unreviewed_registry_or_git_source")
            need(re.fullmatch(r"[0-9a-f]{64}", locked[package_key(package)].get("checksum", "")), "missing_registry_checksum")
    need(locals_seen == set(LOCALS), "missing_expected_local_package")
    resolve = metadata.get("resolve", {})
    root_id = resolve.get("root")
    need(root_id in by_id and by_id[root_id]["name"] == "coding-tools-mcp-desktop", "wrong_metadata_root")
    nodes = resolve.get("nodes", [])
    need(len(nodes) == len(by_id) and {n["id"] for n in nodes} == set(by_id), "incomplete_resolved_graph")
    need(all(d["pkg"] in by_id for n in nodes for d in n.get("deps", [])), "unmapped_resolved_dependency")
    return len(packages)


def verify_audit(report, lock):
    settings = report.get("settings", {})
    need(settings == {"target_arch": [], "target_os": [], "severity": None, "ignore": [],
                      "informational_warnings": ["unmaintained", "unsound", "notice"]}, "filtered_audit")
    locked = {package_key(p): p for p in lock["package"]}
    need(report.get("lockfile", {}).get("dependency-count") == len(locked), "wrong_audit_package_count")
    need(type(report.get("database", {}).get("advisory-count")) is int and report["database"]["advisory-count"] > 0,
         "empty_advisory_database")
    vulnerabilities = report.get("vulnerabilities", {})
    findings = vulnerabilities.get("list")
    need(isinstance(findings, list) and type(vulnerabilities.get("count")) is int and
         vulnerabilities["count"] == len(findings) and vulnerabilities.get("found") is bool(findings), "wrong_audit_counts")
    warnings = report.get("warnings")
    need(isinstance(warnings, dict) and set(warnings) <= {"unmaintained", "unsound", "notice"}, "invalid_audit_warnings")
    for category, values in [("vulnerability", findings), *warnings.items()]:
        need(isinstance(values, list), "invalid_audit_findings")
        for value in values:
            package = value["package"]
            identity = package_key(package)
            need(identity in locked and package.get("checksum") == locked[identity].get("checksum"), "unmapped_audit_identity")
            need(value["advisory"]["package"] == package["name"] and value["advisory"]["id"].startswith("RUSTSEC-"), "invalid_advisory")
    return findings, warnings


def verify_audits(product, upstream, product_lock, upstream_lock):
    findings, warnings = verify_audit(product, product_lock)
    upstream_findings, upstream_warnings = verify_audit(upstream, upstream_lock)
    retained = upstream_warnings.get("unsound", [])
    need(len(retained) == 1 and retained[0]["advisory"]["id"] == ADVISORY, "missing_upstream_unsound_advisory")
    need(not upstream_findings and set(upstream_warnings) == {"unsound"}, "unreviewed_upstream_advisory")
    return {"product_vulnerabilities": findings, "product_warnings": warnings,
            "upstream_identity_vulnerabilities": upstream_findings, "upstream_identity_warnings": upstream_warnings,
            "raw_zero_claim": False, "release_approved": False,
            "scope": "exact_source_backport_only; upstream_registry_unsound_advisory_retained"}


def run(command, root):
    result = subprocess.run(command, cwd=root, capture_output=True, check=False)
    return result.returncode, result.stdout, result.stderr


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--audit-bin", type=Path)
    parser.add_argument("--audit-db", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    need(all((args.audit_bin, args.audit_db, args.output)) or not any((args.audit_bin, args.audit_db, args.output)),
         "audit_capture_requires_binary_database_output")
    if args.audit_bin:
        args.audit_bin = args.audit_bin.resolve(strict=True)
    manifests = verify_configuration(root, os.environ)
    summary = verify_source(root, args.archive)
    lock_bytes = read(root / "src-tauri/Cargo.lock")
    lock = tomllib.loads(lock_bytes.decode())
    code, data, error = run(["cargo", "metadata", "--locked", "--format-version", "1", "--manifest-path", "src-tauri/Cargo.toml"], root)
    need(code == 0, "cargo_metadata_failed:" + error.decode(errors="replace"))
    summary["metadata_package_count"] = verify_metadata(root, decode(data), lock, manifests)
    summary["product_lock_sha256"] = sha(lock_bytes)
    summary["source_backport_verified"] = True
    summary["release_approved"] = False
    summary["raw_zero_claim"] = False
    if args.output:
        output = args.output.resolve()
        need(not output.exists() and not output.is_relative_to(root), "output_must_be_new_and_external")
        output.mkdir(parents=True)
        (output / "metadata.json").write_bytes(data)
        from exact_build_audit import database_identity
        database = database_identity(args.audit_db.resolve())
        code, version, _ = run([str(args.audit_bin), "--version"], root)
        need(code == 0 and version.decode().strip() == "cargo-audit 0.22.2", "wrong_audit_version")
        reports = {}
        exits = {}
        for name, relative in (("product", "src-tauri/Cargo.lock"), ("upstream-identity", PROVENANCE + "/upstream-identity.Cargo.lock")):
            command = [str(args.audit_bin), "audit", "--no-fetch", "--db", str(args.audit_db.resolve()), "--file", relative, "--json"]
            code, data, error = run(command, root)
            (output / (name + "-raw-audit.json")).write_bytes(data)
            (output / (name + "-raw-audit.stderr")).write_bytes(error)
            report = decode(data)
            need(type(code) is int and code == (1 if report.get("vulnerabilities", {}).get("found") else 0), "unexpected_audit_exit")
            reports[name] = report
            exits[name] = {"command": command, "exit": code, "report_sha256": sha(data)}
        upstream_lock = tomllib.loads(read(root / PROVENANCE / "upstream-identity.Cargo.lock").decode())
        summary.update(verify_audits(reports["product"], reports["upstream-identity"], lock, upstream_lock))
        need(database == database_identity(args.audit_db.resolve()), "advisory_database_changed")
        need(summary["product_lock_sha256"] == sha(read(root / "src-tauri/Cargo.lock")), "product_lock_changed")
        need(manifests == verify_configuration(root, os.environ), "local_manifests_changed")
        need(verify_source(root, args.archive)["provenance_sha256"] == summary["provenance_sha256"], "source_changed")
        summary.update({"audit_commands": exits, "advisory_database": database, "audit_version": version.decode().strip(),
                        "audit_binary_sha256": sha(read(args.audit_bin))})
        (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (VerificationError, ValueError, KeyError, TypeError, OSError, tarfile.TarError) as exc:
        raise SystemExit("FAIL: " + str(exc))
