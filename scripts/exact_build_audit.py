#!/usr/bin/env python3
"""Exact Rust-build applicability evidence, never a replacement raw-lock audit.

Only the four gateway binaries are supported. Independent verification requires an
externally trusted envelope digest. Package-set disagreement is a blocker.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys

MANIFEST = "services/cloud-gateway/Cargo.toml"
LOCK = "services/cloud-gateway/Cargo.lock"
ROOT_NAME = "coding-tools-cloud-gateway"
BINS = {"coding-tools-gateway", "coding-tools-agent", "coding-tools-control-gateway", "coding-tools-mcp-gateway"}
STREAMS = {"metadata.json", "selected-tree.txt", "conservative-tree.txt", "build.jsonl", "raw-audit.json"}
MAX_BYTES = 64 * 1024 * 1024


class EvidenceError(ValueError):
    pass


def need(condition, code):
    if not condition:
        raise EvidenceError(code)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    need(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_BYTES, "invalid_evidence_file")
    return path.read_bytes()


def decode(data):
    def pairs(items):
        result = {}
        for k, v in items:
            need(k not in result, "duplicate_json_key")
            result[k] = v
        return result
    def finite_float(value):
        number = float(value)
        need(math.isfinite(number), "nonfinite_json_number")
        return number
    try:
        return json.loads(data, object_pairs_hook=pairs, parse_float=finite_float, parse_constant=lambda value: (_ for _ in ()).throw(EvidenceError("nonfinite_json_number")))
    except (ValueError, UnicodeError) as exc:
        raise EvidenceError("invalid_json") from exc


def normalized(path):
    return str(path).replace("\\", "/").rstrip("/")


def key(package):
    need(isinstance(package.get("name"), str) and isinstance(package.get("version"), str), "invalid_package_identity")
    source = package.get("source")
    need(source is None or isinstance(source, str), "invalid_package_source")
    return package["name"], package["version"], source


def package_maps(metadata, lock):
    packages = metadata.get("packages", [])
    need(packages and isinstance(packages, list), "missing_metadata_packages")
    by_id = {p["id"]: p for p in packages}
    need(len(by_id) == len(packages), "duplicate_package_id")
    by_display = {}
    for pid, p in by_id.items():
        need(isinstance(pid, str), "invalid_package_id")
        by_display.setdefault((p["name"], p["version"]), []).append(pid)
    locked = {key(p): p for p in lock.get("package", [])}
    need(len(locked) == len(lock.get("package", [])) and locked, "invalid_lock_packages")
    return by_id, by_display, locked


def tree_packages(text, by_display):
    result = {}
    for line in text.splitlines():
        need(bool(line.strip()), "empty_tree_line")
        if line.endswith(" (*)"):
            line = line[:-4]
        display, separator, features = line.partition("\t")
        match = re.match(r"^(\S+) v(\S+)(?:\s.*)?$", display)
        need(separator and match, "invalid_tree_line")
        ids = by_display.get((match.group(1), match.group(2)), [])
        need(len(ids) == 1, "ambiguous_or_unmapped_tree_package")
        values = set(features.split(",")) if features else set()
        need(all(re.fullmatch(r"[A-Za-z0-9_+./-]+", f) for f in values), "invalid_tree_feature")
        result.setdefault(ids[0], set()).update(values)
    need(len(result) > 1, "incomplete_selected_tree")
    return result


def unit(target):
    return target.get("name"), tuple(target.get("kind", []))


def verify_records(envelope, metadata, selected_text, conservative_text, build_text, audit, lock, expected):
    """Pure invariant checker; file hashes and actual source are checked by verify()."""
    need(type(envelope.get("schema")) is int and envelope["schema"] == 1, "unsupported_envelope")
    for field in ("sha", "tree", "lock_sha256", "manifest_sha256", "product_version", "target"):
        need(envelope.get(field) == expected.get(field), "wrong_" + field)
    ci = envelope.get("ci", {})
    need(ci.get("provider") in ("local", "github-actions"), "missing_build_provenance")
    if ci["provider"] == "github-actions":
        need(ci.get("sha") == envelope.get("sha"), "wrong_ci_source")
        need(ci.get("repository") == "Eswink/coding-tools-mcp", "wrong_ci_repository")
        need(ci.get("workflow_ref", "").startswith("Eswink/coding-tools-mcp/.github/workflows/"), "wrong_ci_workflow_repository")
        need(re.fullmatch(r"[1-9][0-9]*", str(ci.get("run_id"))) and re.fullmatch(r"[1-9][0-9]*", str(ci.get("run_attempt"))), "invalid_ci_run")
        need(all(isinstance(ci.get(k), str) and ci[k] for k in ("repository", "workflow_ref", "job", "runner_os")), "incomplete_ci_provenance")
    need(envelope.get("build_exit") == 0 and type(envelope.get("build_exit")) is int, "failed_build_process")
    need(envelope.get("features") == {"default": True, "all": False, "selected": []}, "unexpected_build_features")
    need(envelope.get("build_command") == build_command(envelope["target"]), "unexpected_build_command")
    need(envelope.get("verifier_sha256") == digest(Path(__file__).read_bytes()), "wrong_verifier_revision")
    need(envelope.get("audit_version", "").strip() == "cargo-audit 0.22.2", "unexpected_audit_version")
    need(re.fullmatch(r"[0-9a-f]{64}", envelope.get("audit_binary_sha256", "")), "missing_audit_binary_identity")
    need(all(envelope.get("toolchain", {}).get(k) for k in ("cargo", "rustc")), "missing_toolchain")
    for tool in ("cargo", "rustc"):
        need(re.match(r"^" + tool + r" [0-9]+\.[0-9]+\.[0-9]+(?: |$)", envelope["toolchain"][tool]), "unexpected_unstable_toolchain")
        if ci["provider"] == "github-actions":
            need(re.match(r"^" + tool + r" 1\.98\.1(?: |$)", envelope["toolchain"][tool]), "wrong_product_toolchain")
    by_id, by_display, locked = package_maps(metadata, lock)
    root = metadata.get("resolve", {}).get("root")
    need(root in by_id and by_id[root]["name"] == ROOT_NAME and by_id[root].get("source") is None, "wrong_root_package")
    need(normalized(by_id[root]["manifest_path"]) == normalized(envelope["source_root"]) + "/" + MANIFEST, "wrong_root_manifest")
    root_targets = {t["name"] for t in by_id[root]["targets"] if t["kind"] == ["bin"]}
    need(root_targets == BINS, "unexpected_manifest_bins")
    selected = tree_packages(selected_text, by_display)
    conservative = tree_packages(conservative_text, by_display)
    need(root in selected and set(selected) <= set(conservative), "inconsistent_conservative_tree")
    for pid in selected:
        need(key(by_id[pid]) in locked, "selected_package_not_locked")
        if by_id[pid].get("source") is None:
            need(normalized(by_id[pid]["manifest_path"]).startswith(normalized(envelope["source_root"]) + "/"), "external_local_dependency")
    needed_units = set()
    declared_units = {}
    for pid in selected:
        for t in by_id[pid]["targets"]:
            kinds = t["kind"]
            if "test" in kinds or "example" in kinds or "bench" in kinds:
                continue
            if "bin" in kinds and pid != root:
                continue
            needed_units.add((pid, unit(t)))
            declared_units[(pid, unit(t))] = t
    artifacts, features, units, roots = [], {}, set(), {}
    finished = False
    for line in build_text.splitlines():
        need(line.strip(), "empty_build_event")
        event = decode(line)
        need(isinstance(event, dict), "invalid_build_event")
        reason = event.get("reason")
        need(not finished, "event_after_build_finished")
        if reason == "build-finished":
            need(event.get("success") is True, "failed_build_finished")
            finished = True
        elif reason == "compiler-artifact":
            pid = event.get("package_id")
            need(pid in selected, "extra_or_unmapped_artifact_package")
            need(type(event.get("fresh")) is bool, "missing_fresh_status")
            target = event.get("target", {})
            u = (pid, unit(target))
            need(u in needed_units, "unexpected_compilation_unit")
            need(normalized(event.get("manifest_path", "")) == normalized(by_id[pid]["manifest_path"]), "artifact_manifest_mismatch")
            need(normalized(target.get("src_path", "")) == normalized(declared_units[u].get("src_path", "missing")), "artifact_source_mismatch")
            need(event.get("profile", {}).get("test") is False, "test_artifact_in_release")
            need(isinstance(event.get("features"), list) and all(isinstance(f, str) for f in event["features"]), "invalid_artifact_features")
            features.setdefault(pid, set()).update(event["features"])
            units.add(u)
            artifacts.append(event)
            if pid == root and target.get("kind") == ["bin"]:
                name = target["name"]
                need(name not in roots and name in BINS, "duplicate_or_extra_root")
                profile = event["profile"]
                need(profile.get("debug_assertions") is False and profile.get("opt_level") in ("1", "2", "3", "s", "z"), "nonrelease_root_profile")
                executable = event.get("executable")
                suffix = ".exe" if "windows" in envelope["target"] else ""
                need(isinstance(executable, str) and normalized(executable).endswith("/" + name + suffix), "wrong_root_executable")
                need(executable in event.get("filenames", []), "root_file_not_emitted")
                roots[name] = executable
        elif reason == "compiler-message":
            need(event.get("message", {}).get("level") != "error", "compiler_error_event")
        elif reason == "build-script-executed":
            need(event.get("package_id") in selected, "unknown_build_script")
        else:
            raise EvidenceError("unknown_build_event")
    need(finished, "missing_build_finished")
    need(set(features) == set(selected), "missing_dependency_artifact")
    need(units == needed_units, "missing_compilation_unit")
    need(features == selected, "selected_artifact_feature_mismatch")
    need(set(roots) == BINS, "missing_root_binary")
    settings = audit.get("settings", {})
    need("severity" in settings and settings.get("ignore") == [] and settings.get("target_arch") == [] and settings.get("target_os") == [] and settings.get("severity") is None, "filtered_raw_audit")
    need(set(settings.get("informational_warnings", [])) == {"unmaintained", "unsound", "notice"}, "suppressed_audit_warnings")
    database = audit.get("database", {})
    snapshot = envelope.get("advisory_database", {})
    need(snapshot.get("clean") is True and snapshot.get("origin", "").lower() == "https://github.com/rustsec/advisory-db.git", "untrusted_advisory_snapshot")
    for field, length in (("commit", 40), ("tree", 40), ("contents_sha256", 64)):
        need(re.fullmatch(r"[0-9a-f]{" + str(length) + "}", str(snapshot.get(field))), "invalid_advisory_snapshot")
    need(snapshot["commit"] == envelope.get("advisory_db_commit"), "wrong_advisory_database")
    acquisition = envelope.get("advisory_acquisition", {})
    need(acquisition.get("method") in ("fresh_official_clone", "existing_local_snapshot"), "missing_advisory_acquisition")
    times = []
    for field in ("started_at", "completed_at"):
        value = acquisition.get(field, "")
        need(isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z", value), "invalid_advisory_acquisition_time")
        times.append(datetime.fromisoformat(value.replace("Z", "+00:00")))
    need(times[0] <= times[1], "reversed_advisory_acquisition_time")
    if acquisition["method"] == "fresh_official_clone":
        need(acquisition.get("command") == ["git", "clone", "--depth", "1", "https://github.com/RustSec/advisory-db.git"], "wrong_advisory_acquisition_command")
        need(type(acquisition.get("exit")) is int and acquisition["exit"] == 0, "failed_advisory_acquisition")
    else:
        need(ci["provider"] == "local" and acquisition.get("command") == [], "nonfresh_product_advisory_snapshot")
    # cargo-audit --no-fetch legitimately leaves these raw Git telemetry fields null.
    # Do not fabricate them: bind actual clean database bytes independently instead.
    need(database.get("last-commit") in (None, snapshot["commit"]), "wrong_advisory_database")
    need(type(database.get("advisory-count")) is int and database["advisory-count"] > 0, "empty_advisory_database")
    need(type(snapshot.get("file_count")) is int and snapshot["file_count"] >= database["advisory-count"], "incomplete_advisory_snapshot")
    need(audit.get("lockfile", {}).get("dependency-count") == len(locked), "incomplete_lock_audit")
    vulnerabilities = audit.get("vulnerabilities", {})
    findings = vulnerabilities.get("list")
    need(isinstance(findings, list) and type(vulnerabilities.get("count")) is int and vulnerabilities["count"] == len(findings), "invalid_raw_finding_count")
    need(vulnerabilities.get("found") is bool(findings), "invalid_raw_found_status")
    need(type(envelope.get("audit_exit")) is int and envelope.get("audit_exit") == (1 if findings else 0), "invalid_raw_audit_exit")
    selected_keys = {key(by_id[p]) for p in selected}
    conservative_keys = {key(by_id[p]) for p in conservative}
    classified = []
    for finding in findings:
        p = finding.get("package", {})
        identity = key(p)
        need(identity in locked and p.get("checksum") == locked[identity].get("checksum"), "unmapped_raw_finding")
        need(identity not in selected_keys, "active_vulnerable_package")
        need(identity not in conservative_keys, "vulnerability_in_conservative_graph")
        advisory = finding.get("advisory", {}).get("id")
        need(isinstance(advisory, str) and advisory.startswith("RUSTSEC-"), "invalid_advisory_id")
        classified.append({"id": advisory, "package": p["name"], "version": p["version"], "source": p.get("source"), "classification": "absent_from_verified_build_and_conservative_graph"})
    need(isinstance(audit.get("warnings"), dict), "missing_raw_warnings")
    return {"schema": 1, "ci": ci, "advisory_database": snapshot, "advisory_acquisition": acquisition, "exact_build_audit": "passed", "raw_lock_audit": "findings_present" if findings else "no_vulnerabilities_found", "raw_vulnerability_count": len(findings), "active_vulnerability_count": 0, "selected_package_count": len(selected), "compiler_artifact_events": len(artifacts), "classified_raw_findings": classified, "raw_warnings": audit["warnings"], "executables": roots, "scope": "exact_Cargo_Rust_build_only_not_release_authorization"}


def build_command(target):
    return ["cargo", "build", "--release", "--locked", "--bins", "--manifest-path", MANIFEST, "--target", target, "--message-format=json"]


def execute(command, root, env=None):
    p = subprocess.run(command, cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return p.returncode, p.stdout, p.stderr


def git(root, *args):
    code, out, _ = execute(["git", *args], root)
    need(code == 0, "git_identity_unavailable")
    return out.decode().strip()


def source_identity(root, sha, version, target):
    need(re.fullmatch(r"[0-9a-f]{40}", sha), "invalid_expected_sha")
    need(git(root, "rev-parse", "HEAD") == sha, "wrong_checkout_sha")
    need(not git(root, "status", "--porcelain", "--untracked-files=all"), "unclean_source")
    product = decode(read(root / "package.json"))
    need(product.get("version") == version, "wrong_product_version")
    need(target in ("x86_64-unknown-linux-gnu", "x86_64-pc-windows-msvc"), "unsupported_shipping_target")
    return {"sha": sha, "tree": git(root, "rev-parse", "HEAD^{tree}"), "manifest_sha256": digest(read(root / MANIFEST)), "lock_sha256": digest(read(root / LOCK)), "product_version": version, "target": target}


def database_identity(root):
    need(not git(root, "status", "--porcelain", "--untracked-files=all"), "unclean_advisory_database")
    origin = git(root, "remote", "get-url", "origin")
    need(origin.lower() == "https://github.com/rustsec/advisory-db.git", "untrusted_advisory_origin")
    tracked = set(git(root, "ls-files").splitlines())
    files = set()
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if relative.parts[0] == ".git":
            continue
        need(not path.is_symlink(), "symlink_advisory_file")
        if path.is_file():
            files.add(relative.as_posix())
    need(files == tracked, "untracked_or_missing_advisory_files")
    h = hashlib.sha256()
    for relative in sorted(files):
        h.update(relative.encode() + b"\0" + digest(read(root / relative)).encode() + b"\n")
    return {"commit": git(root, "rev-parse", "HEAD"), "tree": git(root, "rev-parse", "HEAD^{tree}"), "contents_sha256": h.hexdigest(), "origin": origin, "clean": True, "file_count": len(files)}


def verify(root, evidence, sha, version, target, trusted_digest, binary_dir=None):
    import tomllib
    expected = source_identity(root, sha, version, target)
    envelope_bytes = read(evidence / "envelope.json")
    need(digest(envelope_bytes) == trusted_digest, "untrusted_envelope_digest")
    envelope = decode(envelope_bytes)
    need(set(envelope.get("streams", {})) == STREAMS, "incomplete_stream_inventory")
    streams = {}
    for name in sorted(STREAMS):
        raw = read(evidence / name)
        need(digest(raw) == envelope["streams"][name], "evidence_stream_tampered")
        streams[name] = raw
    lock = tomllib.loads(read(root / LOCK).decode())
    metadata = decode(streams["metadata.json"])
    by_id, by_display, _ = package_maps(metadata, lock)
    selected = tree_packages(streams["selected-tree.txt"].decode(), by_display)
    tracked = set(git(root, "ls-files").splitlines())
    for pid in selected:
        package = by_id[pid]
        if package.get("source") is not None:
            continue
        paths = [package["manifest_path"]] + [t["src_path"] for t in package["targets"] if not set(t["kind"]) & {"test", "example", "bench"}]
        prefix = normalized(envelope["source_root"]) + "/"
        for path in paths:
            path = normalized(path)
            need(path.startswith(prefix) and path[len(prefix):] in tracked, "local_source_not_in_commit")
    result = verify_records(envelope, decode(streams["metadata.json"]), streams["selected-tree.txt"].decode(), streams["conservative-tree.txt"].decode(), streams["build.jsonl"].decode(), decode(streams["raw-audit.json"]), lock, expected)
    need(set(envelope.get("binary_sha256", {})) == BINS, "incomplete_binary_inventory")
    for name, filename in result["executables"].items():
        path = binary_dir / Path(normalized(filename)).name if binary_dir else Path(filename)
        need(path.is_file() and not path.is_symlink(), "missing_binary")
        h = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                h.update(block)
        need(h.hexdigest() == envelope["binary_sha256"][name], "binary_hash_mismatch")
    return {**result, **expected, "envelope_sha256": trusted_digest, "binary_sha256": envelope["binary_sha256"]}


def collect(root, output, sha, version, target, audit_bin, audit_db, clone_advisory_db=False):
    import tomllib
    expected = source_identity(root, sha, version, target)
    need(not output.exists() and not output.is_relative_to(root), "output_must_be_new_and_outside_source")
    need(not any(os.environ.get(k) for k in ("RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER", "RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS")), "unreviewed_compiler_environment")
    ci = {"provider": "local"}
    if os.environ.get("GITHUB_ACTIONS") == "true":
        need(os.environ.get("GITHUB_SHA") == sha, "wrong_ci_source")
        ci = {"provider": "github-actions", **{key: os.environ.get(env, "") for key, env in (("sha", "GITHUB_SHA"), ("run_id", "GITHUB_RUN_ID"), ("run_attempt", "GITHUB_RUN_ATTEMPT"), ("repository", "GITHUB_REPOSITORY"), ("workflow_ref", "GITHUB_WORKFLOW_REF"), ("job", "GITHUB_JOB"), ("runner_os", "RUNNER_OS"))}}
    need(ci["provider"] == "local" or clone_advisory_db, "fresh_product_advisory_clone_required")
    need(ci["provider"] == "local" or ci["repository"] == "Eswink/coding-tools-mcp", "wrong_ci_repository")
    output.mkdir(parents=True)
    def capture(name, command, allowed=(0,)):
        code, out, err = execute(command, root)
        (output / name).write_bytes(out)
        (output / (name + ".stderr")).write_bytes(err)
        need(code in allowed, "command_failed_" + name)
        return code, out
    audit_version_code, audit_version, _ = execute([str(audit_bin), "--version"], root)
    need(audit_version_code == 0 and audit_version.decode().strip() == "cargo-audit 0.22.2", "unexpected_audit_version")
    with audit_bin.open("rb") as tool:
        audit_binary_hash = hashlib.file_digest(tool, "sha256").hexdigest()
    toolchain = {}
    for name, args in (("cargo", ["cargo", "-Vv"]), ("rustc", ["rustc", "-Vv"])):
        _, out = capture(name + "-version.txt", args)
        toolchain[name] = out.decode()
    if ci["provider"] == "github-actions":
        for tool in ("cargo", "rustc"):
            need(re.match(r"^" + tool + r" 1\.98\.1(?: |$)", toolchain[tool]), "wrong_product_toolchain")
    now = lambda: datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
    acquisition = {"method": "existing_local_snapshot", "command": [], "started_at": now()}
    if clone_advisory_db:
        need(not audit_db.exists() and not audit_db.is_relative_to(root), "advisory_clone_path_must_be_new_and_outside_source")
        command = ["git", "clone", "--depth", "1", "https://github.com/RustSec/advisory-db.git"]
        clone_code, _, _ = execute(command + [str(audit_db)], root)
        need(clone_code == 0, "failed_advisory_acquisition")
        acquisition.update(method="fresh_official_clone", command=command, exit=clone_code)
    acquisition["completed_at"] = now()
    acquired_snapshot = database_identity(audit_db)
    _, meta = capture("metadata.json", ["cargo", "metadata", "--locked", "--format-version", "1", "--manifest-path", MANIFEST])
    base = ["cargo", "tree", "--locked", "--manifest-path", MANIFEST, "--prefix", "none", "--charset", "ascii", "--format", "{p}\t{f}"]
    capture("selected-tree.txt", base + ["--target", target, "--edges", "normal,build"])
    capture("conservative-tree.txt", base + ["--target", "all", "--all-features", "--edges", "normal,build,dev"])
    code, build = capture("build.jsonl", build_command(target))
    database_snapshot = database_identity(audit_db)
    need(database_snapshot == acquired_snapshot, "advisory_database_changed_after_acquisition")
    db_commit = database_snapshot["commit"]
    audit_code, raw_audit = capture("raw-audit.json", [str(audit_bin), "audit", "--db", str(audit_db), "--no-fetch", "--json", "--file", LOCK], (0, 1))
    need(database_snapshot == database_identity(audit_db), "advisory_database_changed")
    need(expected == source_identity(root, sha, version, target), "source_changed_during_build")
    envelope = {"schema": 1, "ci": ci, "verifier_sha256": digest(Path(__file__).read_bytes()), "audit_version": audit_version.decode().strip(), "audit_binary_sha256": audit_binary_hash, **expected, "source_root": str(root), "toolchain": toolchain, "features": {"default": True, "all": False, "selected": []}, "build_command": build_command(target), "build_exit": code, "audit_exit": audit_code, "advisory_db_commit": db_commit, "advisory_database": database_snapshot, "advisory_acquisition": acquisition, "streams": {name: digest(read(output / name)) for name in STREAMS}}
    checked = verify_records(envelope, decode(meta), read(output / "selected-tree.txt").decode(), read(output / "conservative-tree.txt").decode(), build.decode(), decode(raw_audit), tomllib.loads(read(root / LOCK).decode()), expected)
    envelope["binary_sha256"] = {}
    for name, filename in checked["executables"].items():
        with Path(filename).open("rb") as binary:
            envelope["binary_sha256"][name] = hashlib.file_digest(binary, "sha256").hexdigest()
    raw = json.dumps(envelope, sort_keys=True, indent=2).encode() + b"\n"
    (output / "envelope.json").write_bytes(raw)
    summary = verify(root, output, sha, version, target, digest(raw))
    (output / "summary.json").write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n")
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("collect", "verify"))
    for name in ("root", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--expected-sha", required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--target", required=True)
    p.add_argument("--audit-bin", type=Path)
    p.add_argument("--audit-db", type=Path)
    p.add_argument("--clone-advisory-db", action="store_true", help="Acquire a new official advisory snapshot; required for GitHub product evidence")
    p.add_argument("--expected-envelope-sha256")
    p.add_argument("--binary-dir", type=Path)
    a = p.parse_args()
    try:
        if a.mode == "collect":
            need(a.audit_bin and a.audit_db, "audit_tool_and_database_required")
            result = collect(a.root.resolve(), a.output.resolve(), a.expected_sha, a.version, a.target, a.audit_bin.resolve(), a.audit_db.resolve(), a.clone_advisory_db)
        else:
            need(a.expected_envelope_sha256, "external_envelope_digest_required")
            result = verify(a.root.resolve(), a.output.resolve(), a.expected_sha, a.version, a.target, a.expected_envelope_sha256, a.binary_dir.resolve() if a.binary_dir else None)
        print(json.dumps(result, sort_keys=True))
    except (EvidenceError, OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        print(json.dumps({"exact_build_audit": "blocked", "reason": str(error) if isinstance(error, EvidenceError) else "invalid_or_unavailable_evidence"}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
