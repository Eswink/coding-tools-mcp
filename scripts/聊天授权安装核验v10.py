"""Verify release package bytes and installed payloads; never grants or publishes."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from 发布版本校验v4 import verify_source

BINARY = "coding-tools-mcp-desktop"
MANIFEST = "聊天授权安装来源v10.json"
SHA = re.compile(r"[0-9a-f]{64}")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def record(path: Path) -> dict:
    require(path.is_file() and not path.is_symlink(), "artifact must be a regular file")
    require(path.stat().st_size > 0, "empty artifact")
    return {"name": path.name, "size": path.stat().st_size, "sha256": digest(path)}


def verify_record(directory: Path, item: dict) -> Path:
    name = item.get("name")
    require(isinstance(name, str) and name not in ("", ".", "..") and
            "/" not in name and "\\" not in name and Path(name).name == name, "unsafe artifact name")
    require(type(item.get("size")) is int and item["size"] > 0, "invalid artifact size")
    require(isinstance(item.get("sha256"), str) and bool(SHA.fullmatch(item["sha256"])), "invalid SHA-256")
    path = directory / name
    require(record(path) == item, "artifact bytes differ from manifest")
    return path


def command(*args: str) -> str:
    return subprocess.check_output(args, text=True, encoding="utf-8", errors="strict",
                                   stderr=subprocess.STDOUT, timeout=120).strip()


def elf(path: Path) -> None:
    with path.open("rb") as stream:
        header = stream.read(20)
    require(len(header) == 20 and header[:6] == b"\x7fELF\x02\x01" and header[18:20] == b"\x3e\x00",
            "expected Linux x86_64 ELF")


def inspect_linux(package: Path, kind: str, version: str) -> dict:
    require(kind in ("deb", "appimage"), "unknown Linux package kind")
    with tempfile.TemporaryDirectory(prefix="chat-package-v10-") as tmp:
        if kind == "deb":
            require(command("dpkg-deb", "-f", str(package), "Version") == version, "DEB version mismatch")
            require(command("dpkg-deb", "-f", str(package), "Architecture") == "amd64", "DEB architecture mismatch")
            command("dpkg-deb", "-x", str(package), tmp)
            root = Path(tmp)
        else:
            elf(package)
            env = os.environ.copy()
            env.pop("APPIMAGE_EXTRACT_AND_RUN", None)
            subprocess.run([str(package.resolve()), "--appimage-extract"], cwd=tmp, env=env,
                           stdout=subprocess.DEVNULL, check=True, timeout=120)
            root = Path(tmp) / "squashfs-root"
        executable = root / "usr/bin" / BINARY
        require(executable.is_file() and executable.resolve().is_relative_to(root.resolve()), "payload missing or escaped")
        elf(executable)
        return {"payload_sha256": digest(executable), "architecture": "amd64",
                "package_id": command("dpkg-deb", "-f", str(package), "Package") if kind == "deb" else None}


def identity(source: str, root: Path) -> dict:
    proof = verify_source(root, expected_sha=source)
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    require(bool(run_id) and run_id.isdecimal() and os.environ.get("GITHUB_SHA") == source, "exact CI source/run required")
    return {"source_sha": source, "source_tree": command("git", "-C", str(root), "rev-parse", "HEAD^{tree}"),
            "version": proof["version"], "run_id": run_id}


def prepare(root: Path, output: Path, source: str) -> dict:
    data = identity(source, root)
    output.mkdir(parents=True, exist_ok=False)
    packages = {}
    for kind, suffix in (("deb", ".deb"), ("appimage", ".AppImage")):
        choices = list((root / "src-tauri/target/release/bundle" / kind).glob("*" + suffix))
        require(len(choices) == 1, "exactly one package per format required")
        target = output / f"科研工具MCP_聊天授权候选_v{data['version']}_Ubuntu_amd64{suffix}"
        shutil.copyfile(choices[0], target)
        if kind == "appimage":
            target.chmod(0o755)
        packages[kind] = {"artifact": record(target), **inspect_linux(target, kind, data["version"])}
    data.update(passed=True, packages=packages, build_kind="release-packaged")
    (output / MANIFEST).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def load_manifest(directory: Path, root: Path, source: str) -> dict:
    path = directory / MANIFEST
    require(path.is_file() and not path.is_symlink() and path.stat().st_size < 65536, "invalid package manifest")
    data = json.loads(path.read_text(encoding="utf-8"))
    expected = identity(source, root)
    require(all(data.get(k) == v for k, v in expected.items()), "package source/run/version/tree mismatch")
    require(data.get("passed") is True and data.get("build_kind") == "release-packaged", "not a verified release build")
    require(set(data.get("packages", {})) == {"deb", "appimage"}, "both package kinds required")
    for entry in data["packages"].values():
        verify_record(directory, entry["artifact"])
        require(bool(SHA.fullmatch(entry.get("payload_sha256", ""))), "missing payload digest")
    return data


def installed(directory: Path, root: Path, source: str, kind: str, output: Path) -> dict:
    require(os.geteuid() != 0, "installed GUI acceptance must not run as root")
    data = load_manifest(directory, root, source)
    entry = data["packages"][kind]
    package = verify_record(directory, entry["artifact"])
    require(inspect_linux(package, kind, data["version"]) == {k: entry[k] for k in ("payload_sha256", "architecture", "package_id")},
            "packaged payload changed")
    if kind == "deb":
        binary = Path("/usr/bin") / BINARY
        require(command("dpkg-query", "-W", "-f=${Version}", entry["package_id"]) == data["version"], "installed DEB version mismatch")
        require(digest(binary) == entry["payload_sha256"], "installed executable differs from DEB")
        elf(binary)
        files = [Path(p) for p in command("dpkg-query", "-L", entry["package_id"]).splitlines()]
        desktops = [p for p in files if p.suffix == ".desktop" and p.is_file()]
        icons = [p for p in files if "/icons/" in str(p) and p.suffix in (".png", ".svg") and p.is_file()]
        require(len(desktops) == 1 and bool(icons), "desktop entry and icons required")
        command("desktop-file-validate", str(desktops[0]))
        desktop = desktops[0].read_text(encoding="utf-8")
        require(f"Exec={BINARY}" in desktop or f"Exec=/usr/bin/{BINARY}" in desktop, "wrong desktop target")
        require("not found" not in command("ldd", str(binary)), "unresolved runtime library")
    else:
        binary = package
    result = {k: data[k] for k in ("source_sha", "source_tree", "version", "run_id")}
    result.update(passed=True, kind=kind, package=entry["artifact"], payload_sha256=entry["payload_sha256"],
                  native_executable_sha256=digest(binary), executable=str(binary.resolve()),
                  scope="release package and installed bytes; GUI is a separate gate")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
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
        parser.error("installed requires kind") if not args.kind else None
        value = installed(args.directory.resolve(), root, args.source, args.kind, args.output.resolve())
    print(json.dumps(value, ensure_ascii=False))
