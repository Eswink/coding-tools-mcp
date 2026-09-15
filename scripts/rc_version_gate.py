"""Validate an exact-source release-candidate version without weakening stable release gates."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tomllib

PACKAGE = "coding-tools-mcp-desktop"
RC_VERSION = re.compile(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)-rc\.(?:0|[1-9]\d*)")
SHA = re.compile(r"[0-9a-f]{40}")
MAX_CONFIG_BYTES = 10 * 1024 * 1024


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load(root: Path, name: str) -> dict:
    path = root / name
    require(path.is_file() and not path.is_symlink(), f"missing config: {name}")
    require(path.stat().st_size <= MAX_CONFIG_BYTES, f"config too large: {name}")
    raw = path.read_bytes().decode("utf-8")
    return tomllib.loads(raw) if name.endswith((".toml", ".lock")) else json.loads(raw)


def project_versions(root: Path) -> tuple[str, dict[str, str]]:
    package = load(root, "package.json")
    package_lock = load(root, "package-lock.json")
    cargo = load(root, "src-tauri/Cargo.toml")
    cargo_lock = load(root, "src-tauri/Cargo.lock")
    tauri = load(root, "src-tauri/tauri.conf.json")

    packages = [entry for entry in cargo_lock["package"] if entry.get("name") == PACKAGE]
    require(len(packages) == 1, "Cargo.lock must contain exactly one project package")
    identities = [
        package.get("name"),
        package_lock.get("name"),
        package_lock.get("packages", {}).get("", {}).get("name"),
        cargo.get("package", {}).get("name"),
    ]
    require(all(name == PACKAGE for name in identities), "project package identity mismatch")

    versions = {
        "package.json": package.get("version"),
        "package-lock.json:version": package_lock.get("version"),
        "package-lock.json:packages.root": package_lock.get("packages", {}).get("", {}).get("version"),
        "Cargo.toml:package": cargo.get("package", {}).get("version"),
        "Cargo.lock:project": packages[0].get("version"),
        "tauri.conf.json": tauri.get("version"),
    }
    require(all(isinstance(value, str) and RC_VERSION.fullmatch(value) for value in versions.values()),
            "candidate versions must all use major.minor.patch-rc.N")
    require(len(set(versions.values())) == 1, "candidate version fields differ")
    version = next(iter(versions.values()))
    return version, versions


def git_commit(root: Path) -> str:
    result = subprocess.run(["git", "rev-parse", "--verify", "HEAD^{commit}"], cwd=root,
                            text=True, capture_output=True, timeout=20, check=False)
    value = result.stdout.strip()
    require(result.returncode == 0 and bool(SHA.fullmatch(value)), "unable to resolve exact source commit")
    return value


def verify_source(root: Path, expected_sha: str | None = None,
                  expected_version: str | None = None) -> dict:
    version, versions = project_versions(root)
    if expected_version is not None:
        require(bool(RC_VERSION.fullmatch(expected_version)), "expected version is not an rc version")
        require(version == expected_version, "candidate version does not match expected version")
    head = git_commit(root)
    clean = subprocess.run(["git", "diff", "--quiet", "HEAD", "--"], cwd=root,
                           capture_output=True, timeout=20, check=False)
    require(clean.returncode == 0, "tracked source differs from the candidate commit")
    if expected_sha is not None:
        require(bool(SHA.fullmatch(expected_sha)) and head == expected_sha,
                "checkout does not match expected source SHA")
    return {
        "scope": "release-candidate-version-and-source",
        "passed": True,
        "version": version,
        "source_sha": head,
        "versions": versions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--expect-sha")
    parser.add_argument("--expect-version")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        root = args.root.resolve(strict=True)
        report = verify_source(root, args.expect_sha, args.expect_version)
        text = json.dumps(report, ensure_ascii=False, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text + "\n", encoding="utf-8")
        print(text)
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        print(json.dumps({"passed": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
