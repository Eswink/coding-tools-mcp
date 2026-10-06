"""Install the reviewed AppImage launcher/runtime files and verify the final package.

This integration is pinned to the reviewed Tauri CLI. A changed bundler must be
reviewed again, not silently fall back to the generic environment-mutating AppRun.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import tempfile

CLI_VERSION = "2.11.4"
LAUNCHER = "scripts/AppImage启动入口v3.sh"
GRAPHICS_RUNTIME = (
    "libEGL.so.1",
    "libGLESv2.so.2",
    "libGL.so.1",
    "libGLX.so.0",
    "libGLdispatch.so.0",
)
RUNTIME_STAGE = Path("src-tauri/appimage-runtime")
RUNTIME_DEST = Path("usr/lib/x86_64-linux-gnu")


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require_amd64_elf(path: Path, label: str) -> None:
    with path.open("rb") as stream:
        header = stream.read(20)
    if len(header) < 20 or header[:6] != b"\x7fELF\x02\x01" or header[18:20] != b"\x3e\x00":
        raise RuntimeError(f"{label} is not a Linux amd64 ELF")


def resolve_runtime_library(name: str) -> Path:
    output = subprocess.check_output(["ldconfig", "-p"], text=True, timeout=30)
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped.startswith(name + " ") or "=>" not in stripped:
            continue
        if "x86-64" not in stripped and "x86_64" not in stripped:
            continue
        path = Path(stripped.rsplit("=>", 1)[1].strip())
        try:
            resolved = path.resolve(strict=True)
        except OSError:
            continue
        if not resolved.is_file() or resolved.is_symlink():
            continue
        require_amd64_elf(resolved, name)
        return resolved
    raise RuntimeError(f"required AppImage graphics runtime library not found: {name}")


def stage_graphics_runtime(root: Path) -> dict[str, dict[str, object]]:
    stage = root / RUNTIME_STAGE
    if stage.is_symlink():
        raise RuntimeError("AppImage runtime staging directory must not be a symlink")
    stage.mkdir(parents=True, exist_ok=True)
    result: dict[str, dict[str, object]] = {}
    for name in GRAPHICS_RUNTIME:
        source = resolve_runtime_library(name)
        destination = stage / name
        if destination.is_symlink():
            raise RuntimeError(f"AppImage runtime staging entry must not be a symlink: {name}")
        destination.unlink(missing_ok=True)
        shutil.copyfile(source, destination)
        os.chmod(destination, 0o644)
        require_amd64_elf(destination, name)
        result[name] = {"source": str(source), "sha256": digest(destination), "size": destination.stat().st_size}
    return result


def install(root: Path) -> Path:
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise RuntimeError("this AppImage launcher integration is Linux amd64 only")
    target = os.environ.get("TAURI_ENV_TARGET_TRIPLE", "x86_64-unknown-linux-gnu")
    if target != "x86_64-unknown-linux-gnu":
        raise RuntimeError("unsupported AppImage target")
    lock = json.loads((root / "package-lock.json").read_text(encoding="utf-8"))
    if lock["packages"]["node_modules/@tauri-apps/cli"]["version"] != CLI_VERSION:
        raise RuntimeError("Tauri CLI changed; review the AppRun integration before bundling")

    stage_graphics_runtime(root)

    metadata = json.loads(subprocess.check_output([
        "cargo", "metadata", "--offline", "--no-deps", "--format-version", "1",
        "--manifest-path", str(root / "src-tauri/Cargo.toml")], cwd=root / "src-tauri", text=True, timeout=60))
    target_dir = Path(metadata["target_directory"])
    if not target_dir.is_absolute():
        raise RuntimeError("cargo target directory must be absolute")
    tools = target_dir / ".tauri"
    if tools.is_symlink():
        raise RuntimeError("project tools directory must not be a symlink")
    tools.mkdir(parents=True, exist_ok=True)
    destination = tools / "AppRun-x86_64"
    if destination.is_symlink():
        raise RuntimeError("AppRun tools entry must not be a symlink")
    source = root / LAUNCHER
    fd, temporary = tempfile.mkstemp(prefix=".apprun-v3-", dir=tools)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(source.read_bytes())
            stream.flush()
            os.fchmod(stream.fileno(), 0o755)
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
    if digest(source) != digest(destination):
        raise RuntimeError("launcher staging digest mismatch")
    return destination


def verify_helpers(appdir: Path) -> dict:
    """Require the exact bundled GTK helper layout consumed by release WebKit."""
    result = {}
    prefix = Path("usr/lib/x86_64-linux-gnu/webkit2gtk-4.1")
    for name in ("WebKitNetworkProcess", "WebKitWebProcess", "injected-bundle/libwebkit2gtkinjectedbundle.so"):
        path = appdir / prefix / name
        if not path.is_file() or not path.resolve().is_relative_to(appdir.resolve()):
            raise RuntimeError(f"bundled WebKit helper missing or escaped: {name}")
        require_amd64_elf(path, name)
        if not name.endswith(".so") and not os.access(path, os.X_OK):
            raise RuntimeError(f"bundled WebKit helper is not executable: {name}")
        result[(prefix / name).as_posix()] = {"sha256": digest(path), "size": path.stat().st_size}
    return result


def verify_gio_module(appdir: Path) -> dict:
    path = appdir / "usr/lib/x86_64-linux-gnu/gio/modules/libgiognutls.so"
    if not path.is_file() or not path.resolve().is_relative_to(appdir.resolve()):
        raise RuntimeError("bundled GIO TLS module is missing or escaped")
    require_amd64_elf(path, "bundled GIO TLS module")
    return {"sha256": digest(path), "size": path.stat().st_size}


def verify_graphics_runtime(appdir: Path) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    root = appdir.resolve()
    for name in GRAPHICS_RUNTIME:
        path = appdir / RUNTIME_DEST / name
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root):
            raise RuntimeError(f"bundled AppImage graphics runtime missing or escaped: {name}")
        require_amd64_elf(path, name)
        result[name] = {"sha256": digest(path), "size": path.stat().st_size}
    return result


def setup_python_library(record: dict | None) -> str | None:
    """Validate a retained setup-python loader record without filesystem access."""
    if record is None:
        return None
    if type(record) is not dict or set(record) != {'schema', 'version', 'executable', 'library_path', 'library_directory'}:
        raise ValueError('invalid_setup_python_loader_record')
    version, executable, directory = (record[key] for key in ('version', 'executable', 'library_directory'))
    if (record['schema'] != 'setup-python-loader-v1' or type(version) is not str or
            not re.fullmatch(r'3\.12\.(?:0|[1-9][0-9]*)', version) or
            type(executable) is not dict or set(executable) != {'path', 'sha256', 'size'} or
            type(directory) is not dict or set(directory) != {'device', 'inode', 'mode', 'uid'}):
        raise ValueError('invalid_setup_python_loader_identity')
    installation = '/opt/hostedtoolcache/Python/' + version + '/x64'
    if (executable['path'] != installation + '/bin/python3.12' or record['library_path'] != installation + '/lib' or
            type(executable['size']) is not int or not 0 < executable['size'] <= 32 * 1024**2 or
            type(executable['sha256']) is not str or not re.fullmatch('[0-9a-f]{64}', executable['sha256'])):
        raise ValueError('invalid_setup_python_loader_path_or_bytes')
    for key, maximum in (('device', 2**64-1), ('inode', 2**64-1), ('mode', 0xffff), ('uid', 2**32-1)):
        if type(directory[key]) is not int or not 0 <= directory[key] <= maximum:
            raise ValueError('invalid_setup_python_library_metadata')
    if not directory['inode'] or not stat.S_ISDIR(directory['mode']) or directory['mode'] & 0o7022:
        raise ValueError('unsafe_setup_python_library_directory')
    return record['library_path']


def elf_inventory(appdir: Path, retained: Path | None = None) -> dict:
    """Bound the actual extracted tree and retain independent protected bytes."""
    import desktop_glib_build_contract as c
    from appimage_relro_contract import PROTECTED
    records, entries, total, seen = {}, 0, 0, set()
    root = appdir.resolve(strict=True)
    for base, directories, files in os.walk(root, followlinks=False):
        for name in sorted(directories + files):
            path = Path(base) / name
            relative = path.relative_to(root).as_posix()
            c.need(relative not in seen, 'duplicate_appimage_member')
            seen.add(relative)
            info = path.lstat()
            entries += 1
            c.need(entries <= 8192 and len(relative.encode()) <= 1024, 'appimage_inventory_limit')
            if stat.S_ISLNK(info.st_mode):
                target = os.readlink(path)
                c.need(not Path(target).is_absolute() and path.resolve(strict=True).is_relative_to(root),
                       'appimage_alias_escape')
                records[relative] = dict(kind='symlink', target=target, mode=stat.S_IMODE(info.st_mode))
                continue
            if stat.S_ISDIR(info.st_mode):
                continue
            c.need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, 'appimage_special_or_linked_member')
            total += info.st_size
            c.need(info.st_size <= c.MAX_BINARY and total <= 512 * 1024**2, 'appimage_member_byte_limit')
            with c.regular_descriptor(path, c.MAX_BINARY) as (fd, _):
                is_elf = os.read(fd, 4) == b'\x7fELF'
            if is_elf:
                records[relative] = dict(kind='file', mode=stat.S_IMODE(info.st_mode), nlink=1,
                                         **c.file_record(path))
                if retained is not None and relative in PROTECTED:
                    destination = retained / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    c.copy_regular(path, destination)
    c.need(records and len(records) <= 4096, 'empty_or_oversized_elf_inventory')
    return records


def verify(root: Path, image: Path, output: Path, source_sha: str | None = None,
           evidence_root: Path | None = None) -> dict:
    source = root / LAUNCHER
    with tempfile.TemporaryDirectory(prefix="apprun-proof-v3-") as scratch:
        # Inspect bytes only; this does not launch the GUI or alter its environment.
        env = dict(os.environ)
        env.pop("APPIMAGE_EXTRACT_AND_RUN", None)
        subprocess.run([str(image.resolve()), "--appimage-extract"], cwd=scratch, env=env,
                       stdout=subprocess.DEVNULL, check=True, timeout=90)
        appdir = Path(scratch) / "squashfs-root"
        outer, inner = appdir / "AppRun", appdir / "AppRun.wrapped"
        if inner.is_symlink() or not inner.is_file() or digest(inner) != digest(source):
            raise RuntimeError("final AppImage does not contain the reviewed launcher")
        wrapper = outer.read_text(encoding="utf-8")
        if "linuxdeploy-plugin-gtk.sh" not in wrapper or "AppRun.wrapped" not in wrapper:
            raise RuntimeError("expected GTK wrapper missing; review bundler changes")
        if not os.access(inner, os.X_OK):
            raise RuntimeError("packaged launcher lost executable permission")
        result = {"passed": True, "source_sha": source_sha if source_sha is not None else os.environ["GITHUB_SHA"],
                  "cli_version": CLI_VERSION, "launcher_sha256": digest(inner),
                  "appimage_sha256": digest(image), "gtk_hook_retained": True,
                  "webkit_helpers": verify_helpers(appdir), "gui_cwd": "APPDIR/usr",
                  "gio_tls_module": verify_gio_module(appdir),
                  "graphics_runtime": verify_graphics_runtime(appdir),
                  "scope": "final package entry/runtime bytes; native host Python is a separate GUI gate"}
        if evidence_root is not None:
            import desktop_glib_build_contract as c
            result['members'] = elf_inventory(appdir, evidence_root / 'appimage-members')
            c.copy_regular(appdir / 'usr/bin/coding-tools-mcp-desktop', evidence_root / 'appimage-desktop.elf')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--source")
    parser.add_argument("--evidence-root", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.verify:
        if not args.output:
            parser.error("--verify requires --output")
        print(json.dumps(verify(root, args.verify, args.output, args.source, args.evidence_root), ensure_ascii=False))
    else:
        path = install(root)
        print(json.dumps({"launcher": str(path), "sha256": digest(path)}, ensure_ascii=False))
