"""Install the reviewed AppImage launcher/runtime files and verify the final package.

This integration is pinned to the reviewed Tauri CLI. A changed bundler must be
reviewed again, not silently fall back to the generic environment-mutating AppRun.
"""
from __future__ import annotations
import argparse
import hashlib
import math
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


def _projection_need(condition, message):
    if not condition:
        raise ValueError(message)


def setup_python_omitted(omission: dict) -> bool:
    _projection_need(type(omission) is dict and set(omission) == {'schema', 'input',
        'original_ld_library_path', 'child_ld_library_path', 'loading_authorized'}, 'invalid_loader_omission')
    _projection_need(omission['schema'] == 'setup-python-omission-v1' and
        omission['child_ld_library_path'] is None and omission['loading_authorized'] is False, 'invalid_omission_authority')
    record, expected = omission['input'], None
    if record is not None:
        try:
            expected = setup_python_library(record)
        except ValueError as error:
            _projection_need(str(error) == 'unsafe_setup_python_library_directory' and
                record['library_directory']['mode'] == 0o40777 and record['library_directory']['inode'] > 0,
                'unrecognized_omitted_loader_identity')
            expected = record['library_path']
    _projection_need(omission['original_ld_library_path'] == expected, 'omitted_loader_value_mismatch')
    return True


def omit_setup_python_input(projection: dict, omission: dict) -> dict:
    setup_python_omitted(omission)
    allowed = set(('LD_LIBRARY_PATH LD_PRELOAD LD_AUDIT LD_DEBUG LD_BIND_NOW GIO_EXTRA_MODULES GIO_MODULE_DIR '
        'GIO_USE_TLS GIO_USE_VFS GTK_PATH GTK_MODULES GDK_BACKEND APPIMAGE APPDIR APPIMAGE_EXTRACT_AND_RUN').split())
    _projection_need(type(projection) is dict and set(projection) <= allowed and all(type(v) is str and
        len(v.encode()) <= 4096 for v in projection.values()) and len(json.dumps(projection).encode()) <= 16384,
        'invalid_harness_environment_projection')
    original = omission['original_ld_library_path']
    _projection_need(projection.get('LD_LIBRARY_PATH') == original and
        ('LD_LIBRARY_PATH' in projection) == (original is not None), 'loader_omission_presence_or_value_mismatch')
    result = dict(projection)
    result.pop('LD_LIBRARY_PATH', None)
    return result


def validate_runtime_environment(launch, observed, package_root, python_loader=None, python_loader_omission=None):
    for key in ('LD_PRELOAD', 'LD_AUDIT', 'LD_DEBUG', 'GTK_MODULES', 'GIO_USE_TLS', 'GIO_USE_VFS'):
        _projection_need(not launch.get(key) and not observed.get(key), 'loader override present')
    _projection_need(not launch.get('GTK_PATH'), 'inherited GTK override present')
    expected = {key: launch.get(key, '') for key in ('LD_LIBRARY_PATH', 'GIO_MODULE_DIR', 'GIO_EXTRA_MODULES', 'GTK_PATH')}
    if package_root:
        root = package_root['path']
        _projection_need(package_root.get('kind') == 'appimage' and observed.get('APPDIR') == root, 'unbound AppImage projection')
        expected['GTK_PATH'] = root + '//usr/lib/gtk-3.0'
        expected['LD_LIBRARY_PATH'] = root + '/usr/lib:' + root + '/usr/lib/x86_64-linux-gnu'
        expected['GIO_MODULE_DIR'] = expected['GIO_EXTRA_MODULES'] = root + '/usr/lib/x86_64-linux-gnu/gio/modules'
    _projection_need(all(observed.get(key, '') == value for key, value in expected.items()), 'loader environment disagreement')
    _projection_need(python_loader is None and setup_python_omitted(python_loader_omission) and
        not any(launch.get(k) for k in ('LD_LIBRARY_PATH', 'GIO_MODULE_DIR', 'GIO_EXTRA_MODULES')),
        'inherited loader override present')


def validate_harness_projection(proof, binding, phase, harness, launch):
    _projection_need(type(proof) is dict and set(proof) == {'schema', 'phase', 'binding_sha256', 'omission',
        'original', 'projected'}, 'invalid_harness_projection')
    group = 'native' if phase in ('native-1', 'native-2', 'native') else phase
    _projection_need(group in ('native', 'startup-missing-bus', 'startup-unlocked-keyring',
        'startup-split-session-bus', 'startup-safe-mode'), 'invalid_harness_phase')
    digest = hashlib.sha256(json.dumps(binding, sort_keys=True, ensure_ascii=True,
        separators=(',', ':'), allow_nan=False).encode('ascii')).hexdigest()
    _projection_need(binding.get('schema') == 'linux-installed-binding-v1' and proof['schema'] == 'linux-harness-projection-v1' and
        proof['phase'] == group and proof['binding_sha256'] == digest and
        proof['omission'] == binding['python_loader_omission'], 'harness_projection_binding_mismatch')
    _projection_need(omit_setup_python_input(proof['original'], proof['omission']) == proof['projected'] == harness and
        'LD_LIBRARY_PATH' not in harness, 'harness_projection_changed')
    validate_runtime_environment(harness, harness, None, binding['python_loader'], binding['python_loader_omission'])
    validate_runtime_environment(launch, launch, None, binding['python_loader'], binding['python_loader_omission'])
    return proof['projected']


def elf_inventory(appdir: Path, retained: Path | None = None) -> dict:
    """Bound the actual extracted tree and retain independent protected bytes."""
    import desktop_glib_build_contract as c
    from appimage_relro_contract import PROTECTED, verify_media_member
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
                resolved = path.resolve(strict=True)
                c.need(not Path(target).is_absolute() and resolved.is_relative_to(root),
                       'appimage_alias_escape')
                record = dict(kind='symlink', target=target, mode=stat.S_IMODE(info.st_mode))
                verify_media_member(relative, record)
                verify_media_member(os.path.normpath(os.path.join(os.path.dirname(relative), target)), record)
                verify_media_member(resolved.relative_to(root).as_posix(), record)
                records[relative] = record
                continue
            if stat.S_ISDIR(info.st_mode):
                verify_media_member(relative, dict(kind='directory'))
                continue
            c.need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, 'appimage_special_or_linked_member')
            total += info.st_size
            c.need(info.st_size <= c.MAX_BINARY and total <= 512 * 1024**2, 'appimage_member_byte_limit')
            with c.regular_descriptor(path, c.MAX_BINARY) as (fd, _):
                is_elf = os.read(fd, 4) == b'\x7fELF'
            record = (dict(kind='file', mode=stat.S_IMODE(info.st_mode), nlink=1, **c.file_record(path))
                      if is_elf else dict(kind='nonelf'))
            verify_media_member(relative, record)
            if is_elf:
                records[relative] = record
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




# Pure sampled-runtime replay, shared with the ordinary-user observer.
SCHEMA = 'linux-runtime-provenance-v1'
MAIN = 'usr/bin/coding-tools-mcp-desktop'
BINDING_KEYS = ('schema', 'profile', 'source_sha', 'source_tree', 'run_id', 'run_attempt',
                'workflow', 'os', 'kind', 'package', 'envelope_sha256', 'artifact_id', 'artifact_digest', 'members',
                'python_loader', 'python_loader_omission')
LIMITS = dict(processes=128, files=512, maps=1048576, rows=8192, path=4096,
              file_bytes=256*1024**2, hash_bytes=8*1024**3, raw_bytes=128*1024**2,
              evidence_bytes=256*1024**2, seconds=900)
FALSE_CLAIMS = dict(atomic_snapshot=False, complete_lifetime_closure=False,
                   tls_runtime_closure=False, official_archive_byte_origin=False,
                   native_linker_consumption_verified=False, retained_glib_code_verified=False,
                   security_approved=False, publish_approved=False)
def require(condition, message):
    if not condition: raise ValueError(message)
def same_process(first, last):
    return all(first[key] == last[key] for key in ('pid', 'start', 'executable'))
def parse_maps(raw):
    require(len(raw) <= LIMITS['maps'] and raw.endswith(b'\n'), 'truncated or oversized maps')
    rows, end = [], 0
    for line in raw.decode('utf-8', 'strict').splitlines():
        match = re.fullmatch(r'([0-9a-f]+)-([0-9a-f]+) ([r-][w-][x-][ps]) ([0-9a-f]+) ([0-9a-f]+):([0-9a-f]+) ([0-9]+)(?: +(.*))?', line)
        require(match is not None, 'invalid maps row')
        a, b, perms, offset, major, minor, inode, path = match.groups(); path = path or ''
        a, b = int(a, 16), int(b, 16)
        require(end <= a < b and len(path.encode()) <= LIMITS['path'], 'overlap or path limit')
        end = b
        shared = perms in ('r--s', 'rw-s') and int(major, 16) == 0 and int(minor, 16) == 1 and path in ('/SYSV00000000 (deleted)', '/memfd:WebKitSharedMemory (deleted)')
        category = ('shared-memory' if shared else 'deleted' if path.endswith(' (deleted)') else 'ambiguous' if '\\' in path else
                    'kernel' if path.startswith('[') else 'anonymous' if not path else 'file')
        require(category != 'file' or (path.startswith('/') and int(inode) > 0), 'invalid file mapping')
        rows.append(dict(start=a, end=b, permissions=perms, offset=int(offset, 16),
                         device=[int(major, 16), int(minor, 16)], inode=int(inode), path=path, category=category))
        require(len(rows) <= LIMITS['rows'], 'maps row limit')
    require(rows, 'empty maps')
    return rows
def package_origin(path, identity, binding, package_root=None):
    equivalent = sorted(m['path'] for m in binding['members']
                        if identity['sha256'] == m['sha256'] and identity['size'] == m['size'])
    member = path.lstrip('/') if binding['kind'] == 'deb' else None
    if binding['kind'] == 'appimage' and package_root and path.startswith(package_root['path'] + '/'):
        member = path[len(package_root['path']) + 1:]
        require(identity['identity'][0] == package_root['identity'][0], 'package root device mismatch')
    expected = [m for m in binding['members'] if m['path'] == member]
    if expected:
        require(member in equivalent, 'package member bytes mismatch')
        return dict(kind='package', members=[member], equivalent_members=equivalent)
    if {k: identity[k] for k in ('sha256', 'size')} == binding['package']:
        return dict(kind='outer-package', members=[], equivalent_members=equivalent)
    return dict(kind='system', members=[], equivalent_members=equivalent)
def verify_receipt(receipt, binding, phase):
    require(receipt['schema'] == SCHEMA and receipt['phase'] == phase, 'receipt schema/phase mismatch')
    require(receipt['binding'] == {key: binding[key] for key in BINDING_KEYS}, 'runtime binding mismatch')
    require(receipt['claims'] == FALSE_CLAIMS, 'unsupported runtime claim')
    require(not receipt['errors'] and receipt['cleanup_completed'] is True, 'incomplete runtime observations')
    validate_harness_projection(receipt['projection'], binding, 'native' if phase in ('native-1', 'native-2') else phase, receipt['harness_environment'], receipt['launch_environment'])
    require(receipt['anchor'] and 0 < len(receipt['processes']) <= LIMITS['processes'], 'missing anchor')
    require(receipt['host']['uid'] > 0 and receipt['host']['architecture'] == 'x86_64', 'host identity mismatch')
    identities = {(p['pid'], p['start']): p for p in receipt['processes']}; anchor = (receipt['anchor']['pid'], receipt['anchor']['start'])
    require(anchor in identities and len({p['pid'] for p in receipt['processes']}) == len(identities) == len(receipt['processes']), 'anchor identity missing')
    for key, process in identities.items():
        seen = set()
        while key != anchor:
            require(key not in seen, 'ancestry cycle'); seen.add(key)
            key = tuple(process.get('ancestor', [])); require(key in identities, 'unbound ancestry'); process = identities[key]
    ready = 'native-ready' if phase.startswith('native') else 'first-window'; requests = receipt['requests']
    require(receipt['ready'] == ready and 0 < len(requests) <= 64 and requests[-1]['stage'] == 'before-cleanup' and any(q['stage'] == ready for q in requests), 'missing readiness/final checkpoint')
    times = [q['monotonic'] for q in requests]; cut = receipt['ready_at']; events = receipt['discovery']
    require(all(type(t) in (int, float) and math.isfinite(t) and t > 0 for t in times + [cut]) and times == sorted(times) and next(q['monotonic'] for q in requests if q['stage'] == ready) <= cut <= times[-1] + 8, 'invalid epoch times')
    require(0 < len(events) <= LIMITS['rows'] and all(type(e['monotonic']) in (int, float) and math.isfinite(e['monotonic']) and 0 < e['monotonic'] <= times[-1] + 8 for e in events), 'invalid discovery times')
    require([e['monotonic'] for e in events] == sorted(e['monotonic'] for e in events), 'unordered discovery')
    required = set(map(tuple, receipt['required'])); bootstrap = {(p['pid'], p['start']) for p in receipt['bootstrap']}
    require(required == {(e['pid'], e['start']) for e in events if e['monotonic'] >= cut} and receipt['bootstrap'] == [e for e in events if e['monotonic'] < cut], 'unbound process epoch')
    require(anchor in required and required <= set(identities) and bootstrap <= set(identities) and required | bootstrap == set(identities), 'unaccounted process epoch')
    require(0 < len(receipt['files']) <= LIMITS['files'], 'missing file observations')
    release = dict(line.split('=',1) for line in receipt['host']['os_release'].splitlines() if '=' in line)
    require(release.get('ID','').strip(chr(34)) == 'ubuntu' and release.get('VERSION_ID','').strip(chr(34)) == binding['os'].removeprefix('ubuntu-'), 'OS identity mismatch')
    roles, observed_members, raw_bytes, used, sampled, pending = set(), set(), 0, set(), set(), set()
    reads = receipt['hash_reads']; require(all(type(r['bytes']) is int and 0 <= r['bytes'] <= LIMITS['file_bytes'] and type(r['complete']) is bool for r in reads), 'invalid hash read charge')
    require(type(receipt['hash_bytes']) is int and sum(r['bytes'] for r in reads) == receipt['hash_bytes'] <= LIMITS['hash_bytes'], 'hash budget mismatch')
    hashes = {(tuple(r['identity']), r['sha256']) for r in reads if r['complete'] is True and r['bytes'] == r['identity'][2]}
    for value in receipt['files'].values():
        require(0 < value['size'] <= LIMITS['file_bytes'] and re.fullmatch('[0-9a-f]{64}', value['sha256']) and (tuple(value['identity']), value['sha256']) in hashes, 'invalid file identity')
    for sample in receipt['samples']:
        pid = sample['pid']; token = (pid, sample['stage']); complete = sample['status'] == 'complete'
        require(type(sample['monotonic']) in (int, float) and min(e['monotonic'] for e in events if e['pid'] == pid and e['monotonic'] >= cut) <= sample['monotonic'] <= times[-1] + 8 and (not sample['package_root'] or binding['kind'] == 'appimage'), 'sample outside stable epoch')
        if sample['status'] == 'unknown' and sample.get('reason') == 'exited-after-observation':
            require(any(p == pid for p, _ in sampled) and not sample['raw_maps'] and not sample['raw_after'] and not sample['observed'] and sample['before'] is None and sample['after'] is None, 'unobserved process exit'); continue
        require(sample['status'] in ('retry', 'complete') and sample['attempt'] in (0, 1), 'unresolved mapping attempt')
        require((sample['attempt'] == 1) == (token in pending), 'unbound mapping retry')
        if complete: pending.discard(token)
        else:
            require(sample['attempt'] == 0 and sample['reason'] in ('process executable changed during sample', 'mapping changed during hash'), 'invalid mapping retry'); pending.add(token)
        require(sample['before'] and sample['before']['pid'] == pid and (pid, sample['before']['start']) in required, 'unknown sampled process')
        rows = parse_maps(sample['raw_maps'].encode()); after_rows = parse_maps(sample['raw_after'].encode()); raw_bytes += len(sample['raw_maps'].encode()) + len(sample['raw_after'].encode())
        require(len(rows) == len(sample['observed']), 'mapping result count')
        require(all(sample['before'][k] == sample['after'][k] for k in ('pid', 'start')), 'PID reused')
        stable = same_process(sample['before'], sample['after']); maps_stable = all(row in after_rows for row in rows if row['category'] == 'file')
        if stable: validate_runtime_environment(receipt['launch_environment'], sample['environment'], sample['package_root'], binding['python_loader'], binding['python_loader_omission'])
        if not complete: require((sample['reason'] == 'process executable changed during sample' and not stable) or (sample['reason'] == 'mapping changed during hash' and stable and not maps_stable), 'unproved mapping churn')
        if complete:
            require(same_process(sample['before'], sample['after']) and all(row in after_rows for row in rows if row['category'] == 'file'), 'unstable process observation')
            require(not sample['package_root'] or binding['kind'] == 'appimage', 'unbound package root')
            validate_runtime_environment(receipt['launch_environment'], sample['environment'], sample['package_root'], binding['python_loader'], binding['python_loader_omission'])
            sampled.add((pid, sample['before']['start']))
        executable_files = set()
        for row, item in zip(rows, sample['observed']):
            if not complete and item['category'] == 'unresolved':
                require(item.get('reason') in ('FileNotFoundError', 'ProcessLookupError'), 'fatal backing failure hidden by retry'); continue
            require(item['category'] in ('ELF', 'non-ELF', 'anonymous', 'kernel', 'shared-memory'), 'unresolved mapping')
            require((row['category'] == 'file') == (item['category'] in ('ELF', 'non-ELF')) and (row['category'] == 'file' or row['category'] == item['category']), 'mapping category mismatch')
            if item['category'] == 'shared-memory': require(row['category'] == 'shared-memory' and item.get('bytes_verified') is False, 'shared memory byte claim')
            if item['category'] == 'non-ELF':
                dev, ino, *_ = item['identity']; require(row['device'] == [os.major(dev), os.minor(dev)] and row['inode'] == ino, 'non-ELF backing identity')
            if item['category'] != 'ELF': continue
            used.add(item['file']); value = receipt['files'][item['file']]; dev, ino, size, _, _ = value['identity']
            require(row['device'] == [os.major(dev), os.minor(dev)] and row['inode'] == ino and value['size'] == size and row['path'] == value['path'], 'backing identity mismatch')
            origin = package_origin(row['path'], value, binding, sample['package_root'])
            if value['origin']['kind'] == 'owned-driver': require((pid, sample['before']['start']) == anchor and phase.startswith('native'), 'unowned driver')
            else: require(value['origin'] == origin, 'origin mismatch')
            if value['origin']['kind'] == 'system': require(value['owner']['phase'] == phase and value['owner']['versions'] and value['owner']['official_archive_byte_origin'] is False, 'system owner phase mismatch')
            if complete: observed_members.update(origin['members'])
            if ino == sample['before']['executable'][1] and dev == sample['before']['executable'][0]: executable_files.add(item['file'])
        if not complete: continue
        require(set(sample['executable']) == executable_files and executable_files, 'executable mapping mismatch')
        for key in executable_files:
            value = receipt['files'][key]
            if MAIN in value['origin']['members']: roles.add('desktop')
            if value['origin']['kind'] == 'owned-driver': roles.add('driver')
            if value['origin']['kind'] in ('system', 'package') and Path(value['path']).name in ('WebKitWebProcess', 'WebKitNetworkProcess'): roles.add(Path(value['path']).name)
    require(not pending and sampled == required, 'retained process identity was not sampled')
    require(used == set(receipt['files']), 'unreferenced file observation')
    require(raw_bytes == receipt['raw_bytes'] and raw_bytes <= LIMITS['raw_bytes'], 'raw evidence budget mismatch')
    require({'desktop', 'WebKitWebProcess', 'WebKitNetworkProcess'} <= roles, 'missing desktop/helper observation')
    require(not phase.startswith('native') or 'driver' in roles, 'missing native anchor observation')
    observed_versions = {(s['pid'], s['before']['start'], tuple(s['before']['executable'])) for s in receipt['samples'] if s['status'] == 'complete'}
    return dict(phase=phase, sampled_backing_files_verified=True, observed_members=sorted(observed_members),
        bootstrap_unobserved_processes=len(bootstrap - sampled), shared_memory_bytes_verified=False,
        sampled_scope='stable-readiness-epoch', retained_incomplete_attempts=sum(q['status'] != 'complete' for q in receipt['samples']),
        bootstrap_unobserved_versions=sum((p['pid'], p['start'], tuple(p['executable'])) not in observed_versions for p in receipt['bootstrap']),
        tls='observed' if any(Path(receipt['files'][k]['path']).name == 'libgiognutls.so' for q in receipt['samples'] if q['status'] == 'complete' for k in [i['file'] for i in q['observed'] if i['category'] == 'ELF']) else 'not_observed', **FALSE_CLAIMS)

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
