"""Strict native-candidate evidence validation. This does not authorize a release.

A synthetic conversation matrix never proves real ChatGPT client provenance.
The caller must separately enforce both-platform builds, public-client testing,
review, exact main/tag identity and post-publication attachment verification.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re

TEST_NAMES = (
    "真实窗口、工作区与本机安全配置",
    "真实OAuth发现、PKCE授权码交换与401挑战",
    "未审批、缺会话与模型伪造参数全部拒绝",
    "原生点击批准A、A读文件且B仍拒绝",
    "双会话真实异步进程、幂等隔离与本机取消",
    "真实撤销全部、只读授权与禁止自提权",
    "原生独占切换、单一获准聊天与拒绝请求",
    "真实进程重启保留OAuth凭据但不恢复聊天授权",
)
LIMIT = 128 * 1024


def require(condition: bool, message: str) -> None:
    if not condition: raise ValueError(message)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON field")
        result[key] = value
    return result


def reject_constant(_value):
    raise ValueError("non-finite JSON number")


def load(path: Path) -> dict:
    require(path.is_file() and not path.is_symlink(), "evidence must be a regular file")
    with path.open("rb") as stream:
        raw = stream.read(LIMIT + 1)
    require(0 < len(raw) <= LIMIT, "evidence exceeds size limit or is empty")
    value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique_object, parse_constant=reject_constant)
    require(type(value) is dict, "evidence must be an object")
    return value


def verify(value: dict, *, source: str, run_id: str, version: str, kind: str, binary_sha256: str) -> dict:
    require(type(value) is dict, "evidence must be an object")
    require(isinstance(source, str) and re.fullmatch(r"[0-9a-f]{40}", source) is not None, "invalid source SHA")
    require(isinstance(run_id, str) and re.fullmatch(r"[1-9][0-9]*", run_id) is not None, "invalid run id")
    require(isinstance(version, str) and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) is not None, "invalid version")
    require(isinstance(binary_sha256, str) and re.fullmatch(r"[0-9a-f]{64}", binary_sha256) is not None, "invalid binary digest")
    require(kind in ("native", "deb", "appimage", "nsis"), "unknown package kind")
    expected = {"source_sha": source, "run_id": run_id, "version": version,
        "package_kind": kind, "binary_sha256": binary_sha256,
        "build_kind": "debug-static-assets" if kind == "native" else "release-installed"}
    require(all(value.get(key) == item for key, item in expected.items()), "source/run/version/kind/binary mismatch")
    for key in ("passed", "real_native_webview", "real_oauth_http", "real_local_ipc", "cleanup_completed"):
        require(value.get(key) is True, "required native observation was not completed: " + key)
    for key in ("sandbox_disabled", "cleanup_failed", "real_chatgpt_verified"):
        require(value.get(key) is False, "invalid native fixture boundary: " + key)
    require(value.get("synthetic_conversation_metadata") is True, "fixture metadata must not be mislabeled as real ChatGPT")
    require(not any(k in value for k in ("failure_type", "cleanup_failure_type", "host_exit_code")), "failure metadata cannot be promoted to PASS")
    tests = value.get("tests")
    require(type(tests) is list and len(tests) == len(TEST_NAMES), "eight native stages are required")
    require(all(type(test) is dict and test.get("passed") is True for test in tests), "a native stage did not pass")
    require([test.get("name") for test in tests] == list(TEST_NAMES), "native stages are missing, duplicated or reordered")
    return {"passed": True, **expected, "verified_native_stages": len(tests),
        "scope": "native candidate evidence only", "publish_approved": False,
        "real_chatgpt_verified": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--kind", choices=("native", "deb", "appimage", "nsis"), required=True)
    args = parser.parse_args()
    with args.binary.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    proof = verify(load(args.input), source=args.source, run_id=args.run_id,
        version=args.version, kind=args.kind, binary_sha256=digest)
    print(json.dumps(proof, ensure_ascii=False))


if __name__ == "__main__":
    main()
