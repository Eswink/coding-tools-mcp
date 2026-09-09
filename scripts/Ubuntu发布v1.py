"""Fail-closed Ubuntu release: validated main SHA, sequential immutable assets, public re-download."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from Ubuntu安装验收v1 import VERSION, MANIFEST, verify_manifest, digest, require

REPOSITORY = "Eswink/coding-tools-mcp"
API = f"https://api.github.com/repos/{REPOSITORY}"
TAG = f"v{VERSION}"
REF = "refs/heads/release/Ubuntu桌面v1"


def validate_reports(evidence: Path, source: str) -> list[dict]:
    reports = []
    for system in ["ubuntu-22.04", "ubuntu-24.04"]:
        for kind in ["deb", "appimage"]:
            path = evidence / f"Ubuntu原生验收v1-{system}" / kind / "原生验收结果v1.json"
            result = json.loads(path.read_text(encoding="utf-8"))
            require(result.get("passed") is True and result.get("source_sha") == source, f"unverified native report: {path}")
            require(result.get("version") == VERSION and result.get("format") == kind, "native format/version mismatch")
            require(result.get("real_native_webview") is True and result.get("mock_transport") is False,
                    "native transport must not be mocked")
            require(result.get("host_python_environment_preserved") is True,
                    "host Python environment was not validated")
            require(result.get("sandbox_disabled") is False and len(result["tests"]) == 8,
                    "incomplete native acceptance or sandbox bypass")
            require(all(item.get("passed") is True for item in result["tests"]), "native subtest failed")
            reports.append(result)
        installed = evidence / f"Ubuntu原生验收v1-{system}" / "安装载荷结果v1.json"
        result = json.loads(installed.read_text(encoding="utf-8"))
        require(result.get("passed") is True and result.get("source_sha") == source and result.get("version") == VERSION,
                "installed-payload proof mismatch")
    for system in ["ubuntu-24.04", "windows-latest"]:
        report = evidence / f"Ubuntu基线v1-{system}" / "基线结果v1.json"
        data = json.loads(report.read_text(encoding="utf-8"))
        require(data.get("passed") is True and data.get("source_sha") == source, "baseline proof mismatch")
    return reports


def write_evidence_entry(archive: zipfile.ZipFile, path: Path, name: str) -> None:
    require(path.stat().st_size < 25_000_000, "unexpectedly large evidence file")
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, path.read_bytes(), compresslevel=9)


def compose(packages: Path, evidence: Path, output: Path, source: str, root: Path) -> list[Path]:
    require(re.fullmatch(r"[0-9a-f]{40}", source) is not None, "a full source SHA is required")
    manifest = verify_manifest(packages, source)
    validate_reports(evidence, source)
    output.mkdir(parents=True, exist_ok=True)
    assets = []
    for kind, extension in [("deb", "deb"), ("appimage", "AppImage")]:
        path = output / f"MCP_{VERSION}_amd64.{extension}"
        shutil.copyfile(packages / manifest["packages"][kind]["name"], path)
        assets.append(path)
    archive = output / f"Ubuntu-evidence_v{VERSION}.zip"
    # Enumerate known evidence names, not arbitrary JSON/log files from every artifact.
    # acceptance and publish download different artifact sets; that must not alter bytes.
    allowed = ["Ubuntu构建证据v1/打包v1.log", "Ubuntu构建证据v1/入口校验v3.json"]
    for system in ("ubuntu-24.04", "windows-latest"):
        for name in ("基线结果v1.json", "全目标检查v1.log", "完整Rust回归v1.log",
                     "生产零警告v1.log", "原生密钥v1.log", "npm审计v1.json", "重启重复回归v2.log"):
            allowed.append(f"Ubuntu基线v1-{system}/{name}")
    for name in ("面板交互结果v3.json", "面板交互截图v3.png"):
        allowed.append(f"Ubuntu基线v1-ubuntu-24.04/浏览器面板v1/{name}")
    for system in ("ubuntu-22.04", "ubuntu-24.04"):
        prefix = f"Ubuntu原生验收v1-{system}"
        allowed.append(f"{prefix}/安装载荷结果v1.json")
        for kind in ("deb", "appimage"):
            for name in ("原生验收结果v1.json", "首次启动v1.png", "异步任务面板v1.png",
                         "重启恢复v1.png", "原生驱动v1-1.log", "原生驱动v1-2.log",
                         "Portal接口v2.txt", "图形会话v2.log"):
                allowed.append(f"{prefix}/{kind}/{name}")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as target:
        for name in sorted(allowed):
            path = evidence / name
            if path.is_file():
                require(not path.is_symlink() and path.resolve().is_relative_to(evidence.resolve()),
                        "evidence must not escape its artifact directory")
                write_evidence_entry(target, path, "验收证据/" + name)
        write_evidence_entry(target, packages / MANIFEST, MANIFEST)
        write_evidence_entry(target, root / f"docs/releases/Ubuntu安装说明v{VERSION}.md", f"Ubuntu安装说明v{VERSION}.md")
    assets.append(archive)
    checksums = output / f"SHA256SUMS_v{VERSION}.txt"
    checksums.write_text("".join(f"{digest(path)}  {path.name}\n" for path in assets), encoding="utf-8")
    assets.append(checksums)
    return assets


class Github:
    def __init__(self, token: str):
        require(bool(token), "missing release token")
        self.token = token

    def call(self, path: str, data: dict | None = None, method: str = "GET"):
        raw = None if data is None else json.dumps(data, ensure_ascii=False).encode()
        req = urllib.request.Request(API + path, data=raw, method=method, headers={
            "Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code == 404 and method == "GET":
                return None
            raise RuntimeError(f"GitHub {method} {path} returned {exc.code}") from exc

    def main_is(self, source: str) -> None:
        data = self.call("/git/ref/heads/main")
        require(data is not None and data["object"]["sha"] == source, "main moved; refusing publication")

    def tag_is(self, source: str, required: bool = False) -> None:
        data = self.call(f"/git/ref/tags/{TAG}")
        require(data is not None or not required, "published tag missing")
        if data:
            # This pipeline creates lightweight tags; unexpected annotated tags fail closed.
            require(data["object"]["type"] == "commit" and data["object"]["sha"] == source, "tag source mismatch")

    def upload(self, release_id: int, path: Path) -> dict:
        name = urllib.parse.urlencode({"name": path.name})
        url = f"https://uploads.github.com/repos/{REPOSITORY}/releases/{release_id}/assets?{name}"
        req = urllib.request.Request(url, data=path.read_bytes(), method="POST", headers={
            "Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
            "Content-Type": "application/octet-stream", "X-GitHub-Api-Version": "2022-11-28"})
        with urllib.request.urlopen(req, timeout=240) as response:
            return json.load(response)


def check_asset(item: dict, path: Path) -> None:
    require(item["name"] == path.name and item["state"] == "uploaded", "asset name/state mismatch")
    require(item["size"] == path.stat().st_size and item.get("digest") == "sha256:" + digest(path), "asset digest mismatch; refusing replacement")


def publish(assets: list[Path], source: str, root: Path, output: Path) -> dict:
    require(os.environ.get("GITHUB_REPOSITORY") == REPOSITORY, "unexpected repository")
    require(os.environ.get("GITHUB_REF") == REF and os.environ.get("GITHUB_SHA") == source, "only the explicit merged-source release branch may publish")
    client = Github(os.environ.get("GH_TOKEN", ""))
    client.main_is(source)
    client.tag_is(source)
    release = client.call(f"/releases/tags/{TAG}")
    body = (root / f"docs/releases/Ubuntu安装说明v{VERSION}.md").read_text(encoding="utf-8")
    body += f"\n\n构建源码：{source}\n工作流：https://github.com/{REPOSITORY}/actions/runs/{os.environ['GITHUB_RUN_ID']}\n"
    if release is None:
        release = client.call("/releases", {"tag_name": TAG, "target_commitish": source,
            "name": f"{TAG} — Ubuntu图形桌面验收版", "body": body, "draft": True, "prerelease": True}, "POST")
    require(release["target_commitish"] == source and release["prerelease"] is True, "release source/status mismatch")
    release_id = release["id"]
    existing = {item["name"]: item for item in client.call(f"/releases/{release_id}/assets?per_page=100")}
    expected = {path.name for path in assets}
    require(set(existing) <= expected, "unexpected assets; refusing to modify the release")
    for path in assets:
        item = existing.get(path.name)
        if item is None:
            require(release["draft"] is True, "cannot add missing assets to an already public release")
            item = client.upload(release_id, path)
        check_asset(item, path)
    live = client.call(f"/releases/{release_id}/assets?per_page=100")
    require({item["name"] for item in live} == expected, "public asset set incomplete")
    for item in live:
        check_asset(item, next(path for path in assets if path.name == item["name"]))
    client.main_is(source)
    client.tag_is(source)
    if release["draft"]:
        release = client.call(f"/releases/{release_id}", {"draft": False, "prerelease": True, "make_latest": "false"}, "PATCH")
    require(release["draft"] is False, "release is not public")
    client.tag_is(source, required=True)
    receipts = []
    for item in live:
        expected_url = f"https://github.com/{REPOSITORY}/releases/download/{TAG}/{item['name']}"
        require(item["browser_download_url"] == expected_url, "unexpected public download URL")
        hasher, size = hashlib.sha256(), 0
        # Deliberately no Authorization header. Redirected public release assets need no token.
        with urllib.request.urlopen(expected_url, timeout=180) as response:
            for chunk in iter(lambda: response.read(1024 * 1024), b""):
                size += len(chunk)
                hasher.update(chunk)
        require(size == item["size"] and "sha256:" + hasher.hexdigest() == item["digest"], "anonymous public download mismatch")
        receipts.append({"name": item["name"], "size": size, "sha256": hasher.hexdigest(), "anonymous_download_verified": True})
    receipt = {"passed": True, "source_sha": source, "version": VERSION, "release_id": release_id,
               "url": release["html_url"], "draft": False, "prerelease": True, "assets": receipts}
    (output / "公开下载回执v1.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False))
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packages", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    assets = compose(args.packages.resolve(), args.evidence.resolve(), args.output.resolve(), args.source, root)
    if args.publish:
        publish(assets, args.source, root, args.output.resolve())
    else:
        print(json.dumps({"validated": True, "published": False, "assets": [path.name for path in assets]}))
