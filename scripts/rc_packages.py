"""Prepare and verify exact-source Linux RC packages without using stable-release gates."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from exclusive_packages import (
    BINARY,
    MANIFEST,
    SHA,
    command,
    digest,
    elf,
    inspect_linux,
    record,
    require,
    verify_record,
)
from rc_version_gate import verify_source

RC_VERSION = re.compile(r"((?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*))-rc\.((?:0|[1-9]\d*))")


def debian_version(app_version: str) -> str:
    """Map app SemVer RC syntax to Debian's pre-release ordering syntax."""
    match = RC_VERSION.fullmatch(app_version)
    require(match is not None, "candidate app version must be major.minor.patch-rc.N")
    return f"{match.group(1)}~rc{match.group(2)}"


def repack_deb(source: Path, target: Path, app_version: str) -> str:
    """Rebuild only DEB metadata so future stable x.y.z sorts above x.y.z~rcN."""
    require(source.is_file() and not source.is_symlink(), "candidate DEB source must be a regular file")
    package_version = debian_version(app_version)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="coding-tools-rc-deb-") as raw:
        root = Path(raw)
        subprocess.run(["dpkg-deb", "--raw-extract", str(source), str(root)],
                       check=True, timeout=120, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        control = root / "DEBIAN/control"
        require(control.is_file() and not control.is_symlink() and control.stat().st_size < 1024 * 1024,
                "candidate DEB control file missing or invalid")
        text = control.read_text(encoding="utf-8")
        matches = list(re.finditer(r"(?m)^Version:\s*(\S+)\s*$", text))
        require(len(matches) == 1 and matches[0].group(1) == app_version,
                "Tauri candidate DEB version does not match app version before RC rewrite")
        start, end = matches[0].span()
        control.write_text(text[:start] + f"Version: {package_version}" + text[end:], encoding="utf-8")
        subprocess.run(["dpkg-deb", "--build", "--root-owner-group", str(root), str(target)],
                       check=True, timeout=120, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    require(command("dpkg-deb", "-f", str(target), "Version") == package_version,
            "rebuilt candidate DEB version mismatch")
    return package_version


def identity(source: str, root: Path) -> dict:
    proof = verify_source(root, expected_sha=source)
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    require(bool(run_id) and run_id.isdecimal() and os.environ.get("GITHUB_SHA") == source,
            "exact CI source/run required")
    return {
        "source_sha": source,
        "source_tree": command("git", "-C", str(root), "rev-parse", "HEAD^{tree}"),
        "version": proof["version"],
        "run_id": run_id,
    }


def prepare(root: Path, output: Path, source: str) -> dict:
    data = identity(source, root)
    output.mkdir(parents=True, exist_ok=False)
    packages = {}
    for kind, suffix in (("deb", ".deb"), ("appimage", ".AppImage")):
        choices = list((root / "src-tauri/target/release/bundle" / kind).glob("*" + suffix))
        require(len(choices) == 1, "exactly one candidate package per format required")
        target = output / f"MCP_{data['version']}_amd64{suffix}"
        if kind == "deb":
            package_version = repack_deb(choices[0], target, data["version"])
        else:
            shutil.copyfile(choices[0], target)
            target.chmod(0o755)
            package_version = data["version"]
        packages[kind] = {
            "artifact": record(target),
            "package_version": package_version,
            **inspect_linux(target, kind, package_version),
        }
    data.update(passed=True, packages=packages, build_kind="release-candidate")
    (output / MANIFEST).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


def load_manifest(directory: Path, root: Path, source: str) -> dict:
    path = directory / MANIFEST
    require(path.is_file() and not path.is_symlink() and path.stat().st_size < 65536,
            "invalid candidate package manifest")
    data = json.loads(path.read_text(encoding="utf-8"))
    expected = identity(source, root)
    require(all(data.get(key) == value for key, value in expected.items()),
            "candidate package source/run/version/tree mismatch")
    require(data.get("passed") is True and data.get("build_kind") == "release-candidate",
            "not a verified release-candidate build")
    require(set(data.get("packages", {})) == {"deb", "appimage"}, "both Linux candidate formats required")
    for kind, entry in data["packages"].items():
        verify_record(directory, entry["artifact"])
        require(bool(SHA.fullmatch(entry.get("payload_sha256", ""))), "missing candidate payload digest")
        expected_package_version = debian_version(data["version"]) if kind == "deb" else data["version"]
        require(entry.get("package_version") == expected_package_version,
                "candidate package-manager version mismatch")
    return data


def installed(directory: Path, root: Path, source: str, kind: str, output: Path) -> dict:
    require(os.geteuid() != 0, "installed GUI acceptance must not run as root")
    data = load_manifest(directory, root, source)
    entry = data["packages"][kind]
    package = verify_record(directory, entry["artifact"])
    package_version = entry["package_version"]
    actual = inspect_linux(package, kind, package_version)
    require(actual == {key: entry[key] for key in ("payload_sha256", "architecture", "package_id")},
            "candidate packaged payload changed")
    if kind == "deb":
        binary = Path("/usr/bin") / BINARY
        require(command("dpkg-query", "-W", "-f=${Version}", entry["package_id"]) == package_version,
                "installed candidate DEB package-manager version mismatch")
        require(digest(binary) == entry["payload_sha256"], "installed candidate executable differs from DEB")
        elf(binary)
        files = [Path(value) for value in command("dpkg-query", "-L", entry["package_id"]).splitlines()]
        desktops = [value for value in files if value.suffix == ".desktop" and value.is_file()]
        icons = [value for value in files if "/icons/" in str(value) and value.suffix in (".png", ".svg") and value.is_file()]
        require(len(desktops) == 1 and bool(icons), "candidate desktop entry and icons required")
        command("desktop-file-validate", str(desktops[0]))
        desktop = desktops[0].read_text(encoding="utf-8")
        require(f"Exec={BINARY}" in desktop or f"Exec=/usr/bin/{BINARY}" in desktop,
                "candidate desktop entry targets wrong executable")
        require("not found" not in command("ldd", str(binary)), "candidate DEB has unresolved runtime library")
    else:
        binary = package
    result = {key: data[key] for key in ("source_sha", "source_tree", "version", "run_id")}
    result.update(
        passed=True,
        kind=kind,
        package=entry["artifact"],
        package_version=package_version,
        payload_sha256=entry["payload_sha256"],
        native_executable_sha256=digest(binary),
        executable=str(binary.resolve()),
        scope="release-candidate package and installed bytes; GUI/security are separate gates",
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "installed"])
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--kind", choices=["deb", "appimage"])
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.mode == "prepare":
        value = prepare(args.directory.resolve(), args.output.resolve(), args.source)
    else:
        if not args.kind:
            parser.error("installed requires --kind")
        value = installed(args.directory.resolve(), root, args.source, args.kind, args.output.resolve())
    print(json.dumps(value, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
