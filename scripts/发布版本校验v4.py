"""只读检查项目版本、标签源码与安装包摘要；不构建、不发布、不修改版本。"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tomllib

PACKAGE = "coding-tools-mcp-desktop"
VERSION = re.compile(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)")
SHA = re.compile(r"[0-9a-f]{40}")
MAX_CONFIG_BYTES = 10 * 1024 * 1024


def project_versions(root: Path) -> tuple[str, dict[str, str]]:
    """Parse the actual JSON/TOML structures, not incidental dependency versions."""
    def load(name: str) -> dict:
        file = root / name
        if file.stat().st_size > MAX_CONFIG_BYTES:
            raise ValueError(f"配置体积异常: {name}")
        raw = file.read_bytes()
        return tomllib.loads(raw.decode("utf-8")) if name.endswith((".toml", ".lock")) else json.loads(raw)

    package = load("package.json")
    lock = load("package-lock.json")
    cargo = load("src-tauri/Cargo.toml")
    cargo_lock = load("src-tauri/Cargo.lock")
    tauri = load("src-tauri/tauri.conf.json")
    packages = [p for p in cargo_lock["package"] if p.get("name") == PACKAGE]
    if len(packages) != 1:
        raise ValueError("Cargo.lock 必须恰好包含一个项目包")
    identities = [package["name"], lock["name"], lock["packages"][""]["name"], cargo["package"]["name"]]
    if any(name != PACKAGE for name in identities):
        raise ValueError("项目包名不一致")
    versions = {
        "package.json": package["version"],
        "package-lock.json:version": lock["version"],
        "package-lock.json:packages.root": lock["packages"][""]["version"],
        "Cargo.toml:package": cargo["package"]["version"],
        "Cargo.lock:project": packages[0]["version"],
        "tauri.conf.json": tauri["version"],
    }
    if any(not isinstance(value, str) or not VERSION.fullmatch(value) for value in versions.values()):
        raise ValueError("项目版本必须为无前导零的 major.minor.patch")
    if len(set(versions.values())) != 1:
        raise ValueError("六处项目版本不一致")
    return package["version"], versions


def git_commit(root: Path, ref: str) -> str:
    result = subprocess.run(["git", "rev-parse", "--verify", f"{ref}^{{commit}}"], cwd=root,
                            text=True, capture_output=True, timeout=20, check=False)
    value = result.stdout.strip()
    if result.returncode or not SHA.fullmatch(value):
        raise ValueError("无法解析有效的源码commit；需要完整仓库及目标tag")
    return value


def resolve_tag(root: Path, tag: str) -> str:
    if not isinstance(tag, str) or not tag.startswith("v") or not VERSION.fullmatch(tag[1:]):
        raise ValueError("发布标签必须为 v<major.minor.patch>")
    return git_commit(root, f"refs/tags/{tag}")


def verify_source(root: Path, tag: str | None = None, expected_sha: str | None = None) -> dict:
    version, versions = project_versions(root)
    head = git_commit(root, "HEAD")
    clean = subprocess.run(["git", "diff", "--quiet", "HEAD", "--"], cwd=root,
                           capture_output=True, timeout=20, check=False)
    if clean.returncode:
        raise ValueError("已跟踪源码存在未提交修改，不能声称安装包来自该commit")
    if expected_sha is not None and (not SHA.fullmatch(expected_sha) or head != expected_sha):
        raise ValueError("实际checkout与指定源码SHA不一致")
    if tag is not None:
        target = resolve_tag(root, tag)
        if target != head:
            raise ValueError("标签对应源码不是当前checkout，禁止错标安装包")
        if tag != f"v{version}":
            raise ValueError("发布标签版本与项目版本不一致")
    return {"scope": "version-and-source-only", "passed": True, "version": version,
            "source_sha": head, "tag": tag, "versions": versions}


def collect_artifacts(directory: Path, version: str, suffix: str) -> list[dict]:
    if suffix not in (".exe", ".dmg") or not VERSION.fullmatch(version):
        raise ValueError("不支持的安装包类型或版本")
    files = sorted(directory.glob(f"*{suffix}"))
    if not files:
        raise ValueError("安装包目录为空")
    boundary = re.compile(r"(?:^|[_-])" + re.escape(version) + r"(?=[_.-]|$)")
    entries = []
    for file in files:
        if file.is_symlink() or not file.is_file() or not file.stat().st_size or not boundary.search(file.name):
            raise ValueError("安装包必须是非空普通文件，且名称明确包含当前版本；旧包不得混入")
        hasher = hashlib.sha256()
        with file.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(block)
        entries.append({"name": file.name, "bytes": file.stat().st_size, "sha256": hasher.hexdigest()})
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--tag")
    parser.add_argument("--expect-sha")
    parser.add_argument("--resolve-only", action="store_true")
    parser.add_argument("--github-output", action="store_true")
    parser.add_argument("--artifacts", type=Path)
    parser.add_argument("--suffix", choices=[".exe", ".dmg"], default=".exe")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        root = args.root.resolve(strict=True)
        if args.resolve_only:
            if args.tag is None or args.artifacts is not None or args.expect_sha is not None:
                raise ValueError("resolve-only只接受tag，不执行版本/安装包验证")
            sha = resolve_tag(root, args.tag)
            report = {"scope": "tag-resolution-only", "source_sha": sha, "tag": args.tag}
            if args.github_output:
                with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as stream:
                    stream.write(f"source_sha={sha}\nrelease_tag={args.tag}\n")
        else:
            if args.github_output:
                raise ValueError("github-output仅适用于resolve-only")
            report = verify_source(root, args.tag, args.expect_sha)
            if args.artifacts is not None:
                report["artifacts"] = collect_artifacts(root / args.artifacts, report["version"], args.suffix)
        output = json.dumps(report, ensure_ascii=False, indent=2)
        if args.output:
            args.output.write_text(output + "\n", encoding="utf-8")
        print(output)
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(json.dumps({"passed": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
