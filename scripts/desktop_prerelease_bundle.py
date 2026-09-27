"""Assemble one scoped desktop prerelease from exact-source installed CI evidence.

This does not approve the full cloud-gateway roadmap, create tags, or publish.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import zipfile

import rc_native_gate
from exclusive_packages import record, verify_record, require
from rc_version_gate import verify_source

VERSION = "0.6.1-rc.1"
PROBE_SHA = "aed13ff4af30cbb0dbf693ad250991e375f61f005106295528fa16af2d6ab032"
SUMMARY = re.compile(r"test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) ignored;")
RUSTSEC_ACTION_SHA = "69366f33c96575abad1ee0dba8212993eecbe998"
PROBES = {
    "control_unapproved_chat_cannot_spawn", "control_approved_workspace_script_executes",
    "control_pause_and_revoke_block_new_children", "control_foreign_chat_cannot_use_approved_workspace",
    "acceptance_omitted_policy_never_spawns_unsandboxed", "acceptance_workspace_read_cannot_escape",
    "acceptance_symlink_cannot_escape", "acceptance_workspace_write_cannot_escape",
    "acceptance_safe_mode_denies_loopback_network", "acceptance_model_cannot_disable_sandbox",
    "acceptance_tty_flag_cannot_bypass_isolation",
}
STARTUP = ("missing-bus", "unlocked-keyring", "split-session-bus", "safe-mode")


def load(path: Path) -> dict:
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 5_000_000,
            f"missing/invalid evidence: {path.name}")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result
    def invalid(value):
        raise ValueError("non-finite JSON number: " + value)
    def finite(value):
        number = float(value)
        require(math.isfinite(number), "non-finite JSON number")
        return number
    value = json.loads(path.read_text(encoding="utf-8-sig"),
                       object_pairs_hook=unique, parse_constant=invalid, parse_float=finite)
    require(type(value) is dict, "evidence must be an object")
    return value


def identity(value: dict, source: str, tree: str, run_id: str) -> None:
    for key, expected in (("source_sha", source), ("source_tree", tree),
                          ("version", VERSION), ("run_id", run_id)):
        require(value.get(key) == expected, "identity mismatch: " + key)
    require(value.get("passed") is True, "evidence did not pass")


def log_tests(path: Path, minimum: int) -> int:
    require(path.is_file() and not path.is_symlink() and path.stat().st_size < 20_000_000,
            "missing test log")
    matches = SUMMARY.findall(path.read_text(encoding="utf-8"))
    require(bool(matches), "no executed tests")
    require(all(ok == "ok" and failed == "0" and ignored == "0"
                for ok, passed, failed, ignored in matches), "failed or ignored tests")
    count = sum(int(passed) for ok, passed, failed, ignored in matches)
    require(count >= minimum, "insufficient executed tests")
    return count


def verify_hashes(directory: Path) -> None:
    manifest = load(directory / "sha256.json")
    require(bool(manifest), "empty evidence digest manifest")
    for name, expected in manifest.items():
        require(type(name) is str and "\\" not in name and not Path(name).is_absolute()
                and ".." not in Path(name).parts, "unsafe evidence path")
        path = directory / name
        require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(directory.resolve()), "invalid evidence file")
        require(hashlib.sha256(path.read_bytes()).hexdigest() == expected,
                "evidence digest mismatch: " + name)


def native(directory: Path, source: str, tree: str, run_id: str, linux: bool) -> dict:
    verify_hashes(directory)
    value = load(directory / "results.json")
    require(value.get("source_sha") == source and value.get("run_id") == run_id,
            "native source/run mismatch")
    require(value.get("platform") == ("Linux" if linux else "Windows"), "native platform mismatch")
    require((directory / "commit.txt").read_text().strip() == source, "native checkout mismatch")
    require((directory / "tree.txt").read_text().strip() == tree, "native tree mismatch")
    expected = {key: "success" for key in ("CHECK", "DESKTOP", "RUNTIME", "FORMAT")}
    expected.update(PROBE="success" if linux else "skipped",
                    GIT_BOUNDARY="success" if linux else "skipped")
    require(value.get("outcomes") == expected, "incomplete native acceptance")
    counts = {"desktop": log_tests(directory / "desktop.txt", 495 if linux else 488),
              "runtime": log_tests(directory / "runtime.txt", 134 if linux else 91)}
    if linux:
        counts["git_boundary_included_in_desktop"] = log_tests(directory / "git-boundary.txt", 6)
        probe = load(directory / "mcp-probe/result.json")
        require(probe.get("mode") == "acceptance" and probe.get("head") == source
                and probe.get("tree") == tree and probe.get("compile_exit") == 0
                and probe.get("probe_sha256") == PROBE_SHA, "wrong containment probe")
        require(all(probe.get(k) is True for k in (
            "production_source_restored", "controls_passed", "acceptance_passed")),
            "containment not accepted")
        tests = probe.get("tests")
        require(type(tests) is dict and set(tests) == PROBES, "missing original containment probes")
        require(all(t == {"exit_code": 0, "status": "pass"} for t in tests.values()), "probe failed")
        for name in PROBES:
            require(log_tests(directory / "mcp-probe" / (name + ".txt"), 1) == 1,
                    "probe must execute exactly once")
        counts["mcp_containment"] = len(PROBES)
    return counts


def validate(root: Path, artifacts: Path, source: str, tree: str, run_id: str) -> tuple[dict, list[Path]]:
    require(re.fullmatch(r"[0-9a-f]{40}", source) is not None, "invalid source")
    require(re.fullmatch(r"[0-9a-f]{40}", tree) is not None, "invalid tree")
    require(re.fullmatch(r"[1-9][0-9]*", run_id) is not None, "invalid run")
    scope = load(root / f"docs/releases/desktop-v{VERSION}/scope.json")
    require(scope.get("version") == VERSION and scope.get("profile") == "desktop-local-validation"
            and scope.get("full_cloud_gateway_release") is False, "incorrect release scope")
    counts = {}
    for platform, linux in (("ubuntu-24.04", True), ("windows-2025", False)):
        counts[platform] = native(artifacts / f"desktop-native-{platform}-{run_id}",
                                 source, tree, run_id, linux)
    contracts = artifacts / "desktop-package-contracts"
    for name in ("npm-audit.json", "rust-audit-desktop.json", "rust-audit-runtime.json"):
        audit = load(contracts / name)
        if name.startswith("npm"):
            count = audit.get("metadata", {}).get("vulnerabilities", {}).get("total")
            require(type(count) is int and count == 0,
                    "npm vulnerabilities or incomplete audit")
        else:
            count = audit.get("vulnerabilities", {}).get("count")
            require(type(count) is int and count == 0
                    and audit["vulnerabilities"].get("found") is False, "Rust vulnerabilities/incomplete audit")
            expected_dir = "src-tauri" if name == "rust-audit-desktop.json" else "services/local-agent"
            require(audit.get("tool") == "rustsec/audit-check"
                    and audit.get("action_sha") == RUSTSEC_ACTION_SHA
                    and audit.get("working_directory") == expected_dir,
                    "Rust audit provenance mismatch")
    contract_id = load(contracts / "identity.json")
    identity(contract_id, source, tree, run_id)

    win_dir = artifacts / "desktop-windows-package"
    win = load(win_dir / "rc-windows-package.json")
    identity(win, source, tree, run_id)
    require(win.get("kind") == "nsis" and all(win.get(key) is True for key in (
        "silent_install", "exact_nsis_payload_verified", "real_native_approval")),
        "Windows installed package not verified")
    win_path = verify_record(win_dir, win["package"])
    require(win_path.name == f"MCP_{VERSION}_x64-setup.exe", "wrong Windows asset")
    require(win.get("native_executable_sha256") == win.get("payload_sha256"), "Windows payload differs")
    stages = {"nsis": rc_native_gate.verify(load(win_dir / "exclusive-native.json"),
        source=source, run_id=run_id, version=VERSION, kind="nsis",
        binary_sha256=win["payload_sha256"])["native_stages"]}

    linux_dir = artifacts / "desktop-linux-packages"
    linux_manifest = load(linux_dir / "exclusive-package.json")
    identity(linux_manifest, source, tree, run_id)
    require(linux_manifest.get("build_kind") == "release-candidate"
            and set(linux_manifest.get("packages", {})) == {"deb", "appimage"}, "missing Linux formats")
    paths = [win_path]
    for kind, suffix in (("deb", ".deb"), ("appimage", ".AppImage")):
        entry = linux_manifest["packages"][kind]
        path = verify_record(linux_dir, entry["artifact"])
        require(path.name == f"MCP_{VERSION}_amd64{suffix}", "wrong Linux asset")
        directory = artifacts / f"desktop-linux-installed-{kind}"
        installed = load(directory / "rc-package.json")
        identity(installed, source, tree, run_id)
        require(installed.get("kind") == kind and installed.get("package") == entry["artifact"]
                and installed.get("payload_sha256") == entry.get("payload_sha256"), "installed bytes differ")
        expected_binary = entry["payload_sha256"] if kind == "deb" else entry["artifact"]["sha256"]
        require(installed.get("native_executable_sha256") == expected_binary, "native binary differs")
        stages[kind] = rc_native_gate.verify(load(directory / "exclusive-native.json"),
            source=source, run_id=run_id, version=VERSION, kind=kind,
            binary_sha256=expected_binary)["native_stages"]
        for case in STARTUP:
            startup = load(directory / f"startup-{case}/result.json")
            require(startup.get("source") == source and startup.get("run_id") == run_id
                    and startup.get("case") == case and type(startup.get("uid")) is int
                    and startup["uid"] > 0 and startup.get("expected_candidate_behavior_observed") is True,
                    "missing unprivileged raw-startup observation")
        paths.append(path)
    report = {"passed": True, "source_sha": source, "source_tree": tree,
              "version": VERSION, "run_id": run_id, "channel": "prerelease",
              "scope": scope, "native_test_counts": counts, "installed_native_stages": stages,
              "windows_authenticode_signed": win.get("signed") is True,
              "independent_rebuild_reproducibility": "not_claimed",
              "real_workstation_and_chatgpt": "deferred_to_owner",
              "assets": [record(path) for path in paths]}
    return report, paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("artifacts", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    verify_source(root, expected_sha=args.source, expected_version=VERSION)
    tree = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD^{tree}"],
                                   text=True).strip()
    output = args.output.resolve()
    require(not output.exists() and not output.is_relative_to(root), "use a new external output directory")
    report, paths = validate(root, args.artifacts.resolve(), args.source, tree, args.run_id)
    output.mkdir(parents=True)
    for path in paths:
        shutil.copyfile(path, output / path.name)
    doc = root / f"docs/releases/desktop-v{VERSION}"
    for name in ("LOCAL-TEST.zh-CN.md", "scope.json"):
        shutil.copyfile(doc / name, output / name)
    (output / "BUILDINFO.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    with zipfile.ZipFile(output / "VALIDATION-EVIDENCE.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(args.artifacts.rglob("*")):
            if path.is_file() and not path.is_symlink() and (
                path.suffix in {".json", ".txt", ".log", ".tap", ".png"} or path.name == "source.bundle"
            ):
                archive.write(path, path.relative_to(args.artifacts).as_posix())
    checks = [f"{record(p)['sha256']}  {p.name}\n" for p in sorted(output.iterdir()) if p.is_file()]
    (output / "SHA256SUMS.txt").write_text("".join(checks))
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
