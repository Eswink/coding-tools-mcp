"""Publish one source-bound Ubuntu/Windows release only after both native gates."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import zipfile
import urllib.request

import Ubuntu发布v1 as ubuntu
import 发布资产v8 as windows
from Ubuntu安装验收v1 import VERSION, MANIFEST, require, digest
from 发布版本校验v4 import project_versions
from Windows兼容重复v8 import COMPAT, NEGATIVE, RETAINED

REPOSITORY = windows.REPO
REF = "refs/heads/release/双平台v8"
CANDIDATE = "双平台候选清单v8.json"


def validate_repeat(evidence: Path, source: str, run_id: str) -> dict:
    data = windows.load(evidence / "Ubuntu基线v1-windows-latest/Windows兼容结果v8.json")
    require(data.get("passed") is True and data.get("source_sha") == source and str(data.get("run_id")) == run_id,
            "Windows repetition source/run mismatch")
    require(data.get("compatibility_repetitions") == 20 and data.get("explicit_timeout_verified") is True
            and data.get("retained_session_verified") is True, "incomplete Windows regression proof")
    rows = data.get("results", [])
    require(len(rows) == 22 and [row.get("test") for row in rows] == [COMPAT] * 20 + [NEGATIVE, RETAINED]
            and all(row.get("passed") is True for row in rows), "failed/missing Windows repetition")
    return data


def inventory(assets: list[dict], source: str, run_id: str) -> dict:
    return {"source_sha": source, "version": VERSION, "run_id": run_id,
            "assets": [{k: item[k] for k in ("name", "size", "digest")} for item in assets]}


def compose(evidence: Path, output: Path, source: str, run_id: str, root: Path) -> list[dict]:
    require(project_versions(root)[0] == VERSION, "project version differs from packaging version")
    require(bool(run_id) and run_id.isdecimal(), "exact workflow run required")
    packages = evidence / "Ubuntu安装包v1"
    manifest = windows.load(packages / MANIFEST)
    require(str(manifest.get("run_id")) == run_id, "Ubuntu packages came from a different run")
    validate_repeat(evidence, source, run_id)
    # Both existing validators execute before any release API calls.
    ubuntu_assets = ubuntu.compose(packages, evidence, output / "Ubuntu证据", source, root)
    windows_root = evidence / "Windows本地验收安装包v8"
    identity = windows.load(windows_root / "双平台构建身份v8.json")
    require(identity == {"source_sha": source, "run_id": run_id, "version": VERSION}, "Windows build identity mismatch")
    windows_assets = windows.prepare_assets(windows_root, source, VERSION)
    with zipfile.ZipFile(windows_assets[1]["path"], "a") as archive:
        for path in [windows_root / "双平台构建身份v8.json",
                     evidence / "Ubuntu基线v1-windows-latest/Windows兼容结果v8.json",
                     evidence / "Ubuntu基线v1-windows-latest/Windows兼容重复v8.log"]:
            require(path.is_file() and not path.is_symlink(), "missing Windows repetition evidence")
            ubuntu.write_evidence_entry(archive, path, path.name)
    selected = [(path, path.name, "application/octet-stream") for path in ubuntu_assets[:-1]]
    selected += [(item["path"], item["name"] if index == 0 else f"Windows-evidence_v{VERSION}.zip", item["content_type"])
                 for index, item in enumerate(windows_assets[:2])]
    output.mkdir(parents=True, exist_ok=True)
    result = []
    for original, name, mime in selected:
        target = output / name
        shutil.copyfile(original, target)
        result.append({"path": target, "name": name, "label": original.name, "content_type": mime,
                       "size": target.stat().st_size, "digest": "sha256:" + digest(target)})
    sums = output / f"SHA256SUMS_v{VERSION}.txt"
    sums.write_text("".join(f"{item['digest'][7:]}  {item['name']}\n" for item in result), encoding="utf-8")
    result.append({"path": sums, "name": sums.name, "label": f"双平台校验和v{VERSION}.txt",
                   "content_type": "text/plain; charset=utf-8", "size": sums.stat().st_size, "digest": "sha256:" + digest(sums)})
    require(len(result) == 6 and len({item["name"] for item in result}) == 6, "both platforms and all six assets required")
    (output / CANDIDATE).write_text(json.dumps(inventory(result, source, run_id), ensure_ascii=False, indent=2), encoding="utf-8")
    return result


class AnchoredGitHub(windows.GitHub):
    def __init__(self, token: str, source: str):
        super().__init__(token)
        self.source = source

    def request(self, method: str, path: str, data=None, allow_missing=False, upload=None):
        if method != "GET":
            main = super().request("GET", "/git/ref/heads/main")
            require(main.get("object", {}).get("sha") == self.source, "main moved; no release writes allowed")
        if method == "POST" and path == "/releases":
            data = {**data, "name": f"v{VERSION} — Ubuntu与Windows图形桌面版"}
        return super().request(method, path, data=data, allow_missing=allow_missing, upload=upload)


def check_public_downloads(assets: list[dict], version: str) -> list[dict]:
    receipts = []
    for item in assets:
        require(item["name"].isascii() and "/" not in item["name"] and "\\" not in item["name"], "invalid download name")
        url = f"https://github.com/{REPOSITORY}/releases/download/v{version}/{item['name']}"
        hasher, count = hashlib.sha256(), 0
        # This request has no Authorization header and never reuses the authenticated opener.
        with urllib.request.urlopen(url, timeout=180) as response:
            for chunk in iter(lambda: response.read(1024 * 1024), b""):
                count += len(chunk)
                require(count <= item["size"], "public download exceeded expected size")
                hasher.update(chunk)
        require(count == item["size"] and "sha256:" + hasher.hexdigest() == item["digest"], "public download digest mismatch")
        receipts.append({"name": item["name"], "size": count, "sha256": hasher.hexdigest(), "anonymous_download_verified": True})
    return receipts


def publish(assets: list[dict], evidence: Path, output: Path, source: str, run_id: str, root: Path) -> dict:
    require(os.environ.get("GITHUB_REPOSITORY") == REPOSITORY and os.environ.get("GITHUB_REF") == REF
            and os.environ.get("GITHUB_SHA") == source and os.environ.get("GITHUB_RUN_ID") == run_id,
            "only exact merged-source release workflow may publish")
    candidate = windows.load(evidence / "双平台候选发布v8" / CANDIDATE)
    require(candidate == inventory(assets, source, run_id), "candidate asset set changed after acceptance")
    notes = (root / f"docs/releases/双平台安装说明v{VERSION}.md").read_text(encoding="utf-8")
    notes += f"\n\n构建源码：{source}\n构建与验收：https://github.com/{REPOSITORY}/actions/runs/{run_id}\n"
    api = AnchoredGitHub(os.environ.get("GH_TOKEN", ""), source)
    main = api.request("GET", "/git/ref/heads/main")
    require(main.get("object", {}).get("sha") == source, "main moved before publication")
    result = windows.publish(api, assets, source, VERSION, notes)
    receipt = {**result, "run_id": run_id, "version": VERSION, "draft": False,
               "assets": check_public_downloads(assets, VERSION)}
    (output / "双平台公开回执v8.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    assets = compose(args.evidence.resolve(), args.output.resolve(), args.source, args.run_id, root)
    if args.publish:
        print(json.dumps(publish(assets, args.evidence.resolve(), args.output.resolve(), args.source, args.run_id, root), ensure_ascii=False))
    else:
        print(json.dumps({"validated": True, "published": False, "assets": [item["name"] for item in assets]}))
