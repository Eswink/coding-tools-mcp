"""Pinned AppImage inputs for engineering builds; this does not approve a release."""
from __future__ import annotations
import argparse
import functools
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import stat
import subprocess
import tempfile
import time
from urllib.parse import urlsplit

TOOLS = (
    {"name": "linuxdeploy-x86_64.AppImage", "size": 13264064,
     "sha256": "e762bea85c8eb0d4b3508d46e5c1f037f717d0f9303ae3b4aafc8b04991fa1ef",
     "url": "https://github.com/tauri-apps/binary-releases/releases/download/linuxdeploy/linuxdeploy-x86_64.AppImage",
     "asset_id": 182515537, "provenance": "first-observed; upstream API digest null",
     "cache_name": "linuxdeploy-x86_64.AppImage"},
    {"name": "linuxdeploy-plugin-appimage-x86_64.AppImage", "size": 16488952,
     "sha256": "49d6a17160675a6bd1781699aae6bdf7692d98552e02a3671d2183d10547842e",
     "url": "https://github.com/linuxdeploy/linuxdeploy-plugin-appimage/releases/download/continuous/linuxdeploy-plugin-appimage-x86_64.AppImage",
     "asset_id": 602435573, "provenance": "upstream API SHA256",
     "cache_name": "linuxdeploy-plugin-appimage.AppImage"},
    {"name": "runtime-x86_64", "size": 944632,
     "sha256": "156f4bdbde9c52d01814600013e0a273f0118dc2de98975f3c8c63427ec79074",
     "url": "https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-x86_64",
     "asset_id": 596078161, "provenance": "upstream API SHA256", "cache_name": None},
    {"name": "linuxdeploy-plugin-gtk.sh", "size": 14622,
     "sha256": "7804c9eef13e59bf2783aad9882ef9db8f3f3f9e8d631874b1d348d550a3693f",
     "url": "https://raw.githubusercontent.com/tauri-apps/linuxdeploy-plugin-gtk/dda522bce37387f1b853d9095713bfaa924c8423/linuxdeploy-plugin-gtk.sh",
     "commit": "dda522bce37387f1b853d9095713bfaa924c8423", "provenance": "observed immutable-commit bytes",
     "cache_name": "linuxdeploy-plugin-gtk.sh"},
    {"name": "linuxdeploy-plugin-gstreamer.sh", "size": 4857,
     "sha256": "c107b49d84edbffc6ab226ed1007e0626a4f7aa2c3a36b7782bef62351d49e94",
     "url": "https://raw.githubusercontent.com/tauri-apps/linuxdeploy-plugin-gstreamer/2a2e67491c32995a3f279ad0ecbe77abd512b42a/linuxdeploy-plugin-gstreamer.sh",
     "commit": "2a2e67491c32995a3f279ad0ecbe77abd512b42a", "provenance": "observed immutable-commit bytes",
     "cache_name": "linuxdeploy-plugin-gstreamer.sh"},
)
NORMALIZED_SHA256 = "20eebde3c18ae2e44279bd624fc72482503aece216d5d77f10932235342f71c1"
LAUNCHER = "scripts/AppImage启动入口v3.sh"
LAUNCHER_SIZE = 1319
LAUNCHER_SHA256 = "726a50e47cdbc011f6eef6bcf655e1e2eec236f6750cadaff170a8f74c202c2c"
CURL_ENV = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"}
FINAL_HOSTS = {"github.com", "raw.githubusercontent.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def safe_path(value):
    path = Path(value).absolute()
    require(".." not in path.parts, "parent traversal is not permitted")
    for parent in reversed((path, *path.parents)):
        if parent.exists() or parent.is_symlink():
            require(not parent.is_symlink(), f"linked path: {parent}")
            if parent != path:
                require(parent.is_dir(), f"non-directory parent: {parent}")
    return path


def regular(path):
    path = safe_path(path)
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.geteuid(),
            f"expected owned single-link regular file: {path}")
    return info


def checked_file(path, size, digest, mode=None):
    info = regular(path)
    require(info.st_size == size, f"incorrect length: {path}")
    require(mode is None or stat.S_IMODE(info.st_mode) == mode, f"incorrect mode: {path}")
    data = path.read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    require(actual == digest, f"incorrect SHA256: {path}")
    return {"path": str(path), "size": len(data), "sha256": actual, "mode": oct(stat.S_IMODE(info.st_mode))}


def source_identity(root, source):
    """Use isolated Git metadata, actual objects/index, and independently hash tracked files."""
    root = safe_path(root)
    require(re.fullmatch(r"[0-9a-f]{40}", source) is not None, "source must be a full SHA")
    actual = safe_path(root / ".git")
    require(actual.is_dir(), "standalone actual .git directory required")
    for relative in ("commondir", "objects/info/alternates", "objects/info/http-alternates", "info/grafts"):
        require(not os.path.lexists(actual / relative), "alternate Git storage is forbidden")
    regular(actual / "HEAD")
    head = (actual / "HEAD").read_text().strip()
    if head.startswith("ref: "):
        ref = head[5:]
        require(re.fullmatch(r"refs/heads/[A-Za-z0-9_./-]+", ref) and ".." not in ref, "invalid HEAD ref")
        ref_path = safe_path(actual / ref)
        if ref_path.exists():
            regular(ref_path)
            head = ref_path.read_text().strip()
        else:
            packed = safe_path(actual / "packed-refs")
            regular(packed)
            matches = [line.split()[0] for line in packed.read_text().splitlines() if line.endswith(" " + ref)]
            require(len(matches) == 1, "HEAD ref is missing or ambiguous")
            head = matches[0]
    require(head == source, "actual HEAD differs from source")
    regular(actual / "index")
    objects = safe_path(actual / "objects")
    require(objects.is_dir(), "actual object database required")
    with tempfile.TemporaryDirectory(prefix="appimage-git-") as scratch:
        isolated = Path(scratch)
        (isolated / "objects").mkdir()
        (isolated / "refs").mkdir()
        (isolated / "HEAD").write_text(source + "\n")
        env = dict(CURL_ENV, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null",
                   GIT_CONFIG_SYSTEM="/dev/null", GIT_OBJECT_DIRECTORY=str(objects),
                   GIT_INDEX_FILE=str(actual / "index"), GIT_OPTIONAL_LOCKS="0")
        command = ["/usr/bin/git", "--no-replace-objects", f"--git-dir={isolated}", f"--work-tree={root}"]
        def git(*args):
            return subprocess.check_output(command + list(args), cwd=root, env=env, timeout=30)
        tree = git("rev-parse", source + "^{tree}").decode().strip()
        git("diff-index", "--cached", "--quiet", "--no-ext-diff", "--no-textconv", source, "--")
        for entry in git("ls-tree", "-rz", source).split(b"\0")[:-1]:
            metadata, name = entry.split(b"\t", 1)
            mode, kind, digest = metadata.decode().split()
            require(kind == "blob" and mode in ("100644", "100755"), "unsupported tracked source entry")
            path = root / os.fsdecode(name)
            info = regular(path)
            data = path.read_bytes()
            actual_digest = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
            require(actual_digest == digest and bool(info.st_mode & 0o111) == (mode == "100755"),
                    f"tracked worktree drift: {name!r}")
    return {"source_sha": source, "source_tree": tree, "source_root": str(root),
            "tracked_worktree_and_index_verified": True, "untracked_outputs_allowed": True}


def target_path(root, target_directory):
    target = safe_path(target_directory)
    result = subprocess.check_output([
        "cargo", "metadata", "--offline", "--no-deps", "--format-version", "1",
        "--manifest-path", str(root / "src-tauri/Cargo.toml")], cwd=root / "src-tauri", timeout=60)
    actual = Path(json.loads(result)["target_directory"])
    require(actual.is_absolute() and safe_path(actual) == target, "actual Cargo target directory mismatch")
    return target


def _file_limit(size):
    resource.setrlimit(resource.RLIMIT_FSIZE, (size, size))


def download(tool, directory, deadline):
    remaining = min(60, deadline - time.monotonic())
    require(remaining > 0, "aggregate acquisition deadline expired")
    destination = safe_path(directory / tool["name"])
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with tempfile.TemporaryFile() as status:
            command = ["/usr/bin/curl", "--disable", "--silent", "--fail", "--location",
                       "--proto", "=https", "--proto-redir", "=https", "--max-redirs", "3",
                       "--connect-timeout", "20", "--max-time", str(remaining),
                       "--max-filesize", str(tool["size"]), "--output", f"/proc/self/fd/{fd}",
                       "--write-out", "%{http_code}\n%{url_effective}\n", "--url", tool["url"]]
            subprocess.run(command, env=dict(CURL_ENV), pass_fds=(fd,), stdout=status,
                           stderr=subprocess.DEVNULL, timeout=remaining, check=True,
                           preexec_fn=functools.partial(_file_limit, tool["size"]))
            status.seek(0)
            result = status.read(4097)
        require(time.monotonic() <= deadline, "aggregate acquisition deadline expired")
        require(len(result) <= 4096, "oversized curl status")
        lines = result.decode("ascii").splitlines()
        require(len(lines) == 2 and lines[0] == "200", "download requires HTTP 200")
        final = urlsplit(lines[1])
        require(final.scheme == "https" and final.hostname in FINAL_HOSTS and final.port in (None, 443)
                and final.username is None and final.password is None, "unapproved final download URL")
        checked_file(destination, tool["size"], tool["sha256"], 0o600)
        os.fchmod(fd, 0o444)
    finally:
        os.close(fd)


def normalized(data):
    require(data[8:11] == b"AI\x02", "unexpected linuxdeploy marker")
    result = data[:8] + b"\0\0\0" + data[11:]
    require(hashlib.sha256(result).hexdigest() == NORMALIZED_SHA256, "normalized linuxdeploy pin mismatch")
    return result


def inspect_tools(root, target, directory, phase):
    tools = target / ".tauri"
    for path in (directory, tools):
        safe_path(path)
        info = path.stat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid(), "owned tool directories required")
    require({p.name for p in directory.iterdir()} == {t["name"] for t in TOOLS}, "original inventory mismatch")
    names = {t["cache_name"] for t in TOOLS if t["cache_name"]}
    if phase == "after":
        names.add("AppRun-x86_64")
    require({p.name for p in tools.iterdir()} == names, "cache inventory or AppRun phase mismatch")
    originals, cache = {}, {}
    for tool in TOOLS:
        originals[tool["name"]] = checked_file(directory / tool["name"], tool["size"], tool["sha256"], 0o444)
        if tool["cache_name"]:
            digest = NORMALIZED_SHA256 if tool["name"] == "linuxdeploy-x86_64.AppImage" else tool["sha256"]
            cache[tool["cache_name"]] = checked_file(tools / tool["cache_name"], tool["size"], digest, 0o755)
    checked_file(root / LAUNCHER, LAUNCHER_SIZE, LAUNCHER_SHA256)
    if phase == "after":
        cache["AppRun-x86_64"] = checked_file(tools / "AppRun-x86_64", LAUNCHER_SIZE, LAUNCHER_SHA256, 0o755)
    runtime = str(directory / "runtime-x86_64")
    if phase != "prepare":
        require(os.environ.get("LDAI_RUNTIME_FILE") == runtime, "LDAI_RUNTIME_FILE must equal verified local runtime")
    return {"originals": originals, "cache": cache, "runtime_file": runtime}


def receipt(identity, observed, phase, target, output):
    value = dict(identity, **observed, schema="pinned-appimage-tools-v1", phase=phase,
                 target_directory=str(target), pins=TOOLS, passed=True, engineering_only=True,
                 security_approved=False, release_approved=False, publish_approved=False,
                 limits="No reproducible-source equivalence or hostile same-user atomic isolation claim")
    path = safe_path(output)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(json.dumps(value, indent=2) + "\n")
    return value


def paths(root, target_directory, directory, output):
    root, directory, output = map(safe_path, (root, directory, output))
    target = target_path(root, target_directory)
    require(not os.path.lexists(output), "receipt output already exists")
    require(directory != target / ".tauri" and not directory.is_relative_to(target / ".tauri")
            and not (target / ".tauri").is_relative_to(directory), "original/cache directories overlap")
    require(not output.is_relative_to(directory) and not output.is_relative_to(target / ".tauri"),
            "receipt must be separate from tool directories")
    return root, target, directory, output


def prepare(root, target_directory, directory, source, output):
    identity = source_identity(root, source)
    root, target, directory, output = paths(root, target_directory, directory, output)
    tools = safe_path(target / ".tauri")
    require(not os.path.lexists(directory) and not os.path.lexists(tools), "fresh original and cache directories required")
    directory.mkdir(mode=0o700)
    target.mkdir(parents=True, exist_ok=True)
    tools.mkdir(mode=0o700)
    deadline = time.monotonic() + 300
    for tool in TOOLS:
        download(tool, directory, deadline)
    # No executable copy is created until every original has passed its pin.
    for tool in TOOLS:
        if tool["cache_name"]:
            data = (directory / tool["name"]).read_bytes()
            if tool["name"] == "linuxdeploy-x86_64.AppImage":
                data = normalized(data)
            path = tools / tool["cache_name"]
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                os.fchmod(stream.fileno(), 0o755)
    observed = inspect_tools(root, target, directory, "prepare")
    require(source_identity(root, source) == identity, "source changed during preparation")
    return receipt(identity, observed, "prepare", target, output)


def verify(root, target_directory, directory, source, phase, output):
    require(phase in ("before", "after"), "unknown verification phase")
    identity = source_identity(root, source)
    root, target, directory, output = paths(root, target_directory, directory, output)
    observed = inspect_tools(root, target, directory, phase)
    require(source_identity(root, source) == identity, "source changed during verification")
    return receipt(identity, observed, phase, target, output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "verify"):
        child = commands.add_parser(name)
        for option in ("root", "target-directory", "directory", "output"):
            child.add_argument("--" + option, type=Path, required=True)
        child.add_argument("--source", required=True)
        if name == "verify":
            child.add_argument("--phase", choices=("before", "after"), required=True)
    args = vars(parser.parse_args())
    action = args.pop("command")
    print(json.dumps((prepare if action == "prepare" else verify)(**args)))


if __name__ == "__main__":
    main()
