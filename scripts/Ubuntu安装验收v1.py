"""Ubuntu package provenance and installed-payload checks; no GUI mocks or publishing."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
from 发布版本校验v4 import project_versions

VERSION = "0.2.6"
BINARY = "coding-tools-mcp-desktop"
MANIFEST = "Ubuntu构建来源v1.json"


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def command(*args: str) -> str:
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=90).strip()


def elf_x64(path: Path) -> bool:
    with path.open("rb") as stream:
        header = stream.read(20)
    return len(header) == 20 and header[:6] == b"\x7fELF\x02\x01" and header[18:20] == b"\x3e\x00"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verify_manifest(directory: Path, source: str) -> dict:
    data = json.loads((directory / MANIFEST).read_text(encoding="utf-8"))
    require(data["source_sha"] == source and data["version"] == VERSION, "source/version mismatch")
    require(set(data["packages"]) == {"deb", "appimage"}, "both package formats are required")
    for kind, item in data["packages"].items():
        name = item["name"]
        require(Path(name).name == name and "/" not in name, "unsafe artifact name")
        path = directory / name
        require(path.is_file() and not path.is_symlink(), f"missing {kind}")
        require(path.stat().st_size == item["size"] and digest(path) == item["sha256"], f"{kind} digest mismatch")
    return data


def prepare(root: Path, output: Path) -> None:
    version, fields = project_versions(root)
    require(version == VERSION and len(fields) == 6, "six project versions must match")
    source = command("git", "-C", str(root), "rev-parse", "HEAD")
    require(source == os.environ["GITHUB_SHA"], "build must use the triggering source SHA")
    require(not command("git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"), "tracked source changed")
    output.mkdir(parents=True, exist_ok=True)
    packages = {}
    for kind, pattern, extension in [("deb", "deb/*.deb", "deb"), ("appimage", "appimage/*.AppImage", "AppImage")]:
        matches = list((root / "src-tauri/target/release/bundle").glob(pattern))
        require(len(matches) == 1, f"expected exactly one {kind} package: {matches}")
        target = output / f"科研工具MCP_v{VERSION}_Ubuntu_amd64.{extension}"
        shutil.copy2(matches[0], target)
        if kind == "appimage":
            target.chmod(0o755)
        packages[kind] = {"name": target.name, "size": target.stat().st_size, "sha256": digest(target)}
    deb = output / packages["deb"]["name"]
    require(command("dpkg-deb", "-f", str(deb), "Version") == VERSION, "DEB internal version mismatch")
    require(command("dpkg-deb", "-f", str(deb), "Architecture") == "amd64", "wrong DEB architecture")
    with tempfile.TemporaryDirectory(prefix="ubuntu-payload-") as scratch:
        command("dpkg-deb", "-x", str(deb), scratch)
        binary = Path(scratch) / "usr/bin" / BINARY
        require(elf_x64(binary), "DEB payload is not ELF x86_64")
        payload_sha = digest(binary)
    record = {"version": version, "source_sha": source,
              "source_tree": command("git", "-C", str(root), "rev-parse", "HEAD^{tree}"),
              "run_id": os.environ["GITHUB_RUN_ID"], "build_os": platform.platform(),
              "glibc": list(platform.libc_ver()), "versions": fields, "packages": packages,
              "deb_package": command("dpkg-deb", "-f", str(deb), "Package"),
              "deb_payload_sha256": payload_sha, "payload_scope": "packaged DEB binary; may differ from unbundled binary due to Tauri bundle marker"}
    (output / MANIFEST).write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    verify_manifest(output, source)
    print(json.dumps({"source_sha": source, "version": version, "packages": packages}, ensure_ascii=False))


def installed(directory: Path, source: str, output: Path) -> None:
    data = verify_manifest(directory, source)
    require(os.geteuid() != 0, "native acceptance must run as an ordinary user")
    package = data["deb_package"]
    require(command("dpkg-query", "-W", "-f=${Version}", package) == VERSION, "installed version mismatch")
    binary = Path("/usr/bin") / BINARY
    require(elf_x64(binary) and digest(binary) == data["deb_payload_sha256"], "installed binary differs from DEB payload")
    entries = [Path(x) for x in command("dpkg-query", "-L", package).splitlines()]
    desktops = [x for x in entries if x.suffix == ".desktop" and x.is_file()]
    icons = [x for x in entries if "/icons/" in str(x) and x.suffix in (".png", ".svg")]
    require(len(desktops) == 1 and bool(icons), "desktop entry or icons missing")
    command("desktop-file-validate", str(desktops[0]))
    desktop = desktops[0].read_text(encoding="utf-8")
    require(f"Exec={BINARY}" in desktop or f"Exec=/usr/bin/{BINARY}" in desktop, "desktop Exec mismatch")
    linked = command("ldd", str(binary))
    require("not found" not in linked, "installed runtime library missing")
    result = {"passed": True, "source_sha": source, "version": VERSION, "platform": platform.platform(),
              "installed_binary_sha256": digest(binary), "package": package,
              "desktop_entry": str(desktops[0]), "icon_count": len(icons), "runtime_dependencies_resolved": True}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "installed"])
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", default=os.environ.get("GITHUB_SHA", ""))
    args = parser.parse_args()
    if args.mode == "prepare":
        prepare(args.directory.resolve(), args.output.resolve())
    else:
        installed(args.directory.resolve(), args.source, args.output.resolve())


if __name__ == "__main__":
    main()
