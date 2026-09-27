"""Isolated native validation; only verified unreferenced blobs can be imported."""
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

BASE = "9b2639d47aaecc0a903124404c9c97cbf1f806d6"
PROBE_REF = "f3a213b1bf0633e5cab2d58370a87aec07c5f011"
PATCH_SHA = "d4e5ce17dbbddd76db29f625bce7dedb2b439b414b82ded15964630a90d3fb9c"
PATHS = [
    ".github/workflows/cloud-gateway-desktop-sandbox.yml",
    ".github/workflows/cloud-gateway-lab.yml",
    "docs/specs/desktop-sandbox-prerelease/design.md",
    "docs/specs/desktop-sandbox-prerelease/requirements.md",
    "docs/specs/desktop-sandbox-prerelease/tasks.md",
    "services/local-agent/src/sandbox/mod.rs",
    "src-tauri/Cargo.lock", "src-tauri/Cargo.toml",
    "src-tauri/src/auth/local_admission_expiry_tests.rs",
    "src-tauri/src/auth/聊天授权v1.rs",
    "src-tauri/src/tools/context.rs", "src-tauri/src/tools/dispatch.rs",
    "src-tauri/src/tools/exec.rs", "src-tauri/src/tools/linux_sandbox.rs",
    "src-tauri/src/tools/linux_sandbox_tests.rs", "src-tauri/src/tools/mod.rs",
    "src-tauri/src/tools/session.rs", "tests/cloud-gateway/scope-guard.test.mjs",
]
GOLDEN = {
    "tests/cloud-gateway/ubuntu_sandbox_dispatch.rs": "5284c554f92064fc41d46af6b1e4c4b0fd135ff1",
    "tests/cloud-gateway/sandbox-dispatch/run_probe.py": "1fdb18eae060c7a9c9903f86f5687e272f9ca1d0",
    "tests/cloud-gateway/sandbox-dispatch/test_run_probe.py": "6d27b6475c86babc3a9b94abf8a416706d05cd88",
}
ALL = sorted(PATHS + list(GOLDEN))


def git(*args, raw=False):
    value = subprocess.check_output(["git", *args])
    return value if raw else value.decode("utf-8").strip()


def blob_hash(data):
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def prepare(root):
    encoded = b"".join((root / f"part-{n:02d}.txt").read_bytes() for n in range(12))
    assert len(encoded) == 22924 and hashlib.sha256(encoded).hexdigest() == PATCH_SHA
    patch = gzip.decompress(base64.b64decode(encoded, validate=True))
    assert len(patch) == 50912
    patch_file = root / "candidate.patch"
    patch_file.write_bytes(patch)
    subprocess.run(["git", "checkout", "--detach", "--force", BASE], check=True)
    names = git("apply", "--numstat", "-z", str(patch_file), raw=True).split(b"\0")
    paths = [line.split(b"\t", 2)[2].decode("utf-8") for line in names if line]
    assert sorted(paths) == sorted(PATHS), paths
    subprocess.run(["git", "apply", "--check", "--index", str(patch_file)], check=True)
    subprocess.run(["git", "apply", "--index", str(patch_file)], check=True)
    for path, expected in GOLDEN.items():
        data = git("show", f"{PROBE_REF}:{path}", raw=True)
        assert blob_hash(data) == expected
        target = Path(path)
        assert not target.exists()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    subprocess.run(["cargo", "fmt", "--manifest-path", "services/local-agent/Cargo.toml"], check=True)
    subprocess.run(["rustfmt", "--edition", "2021",
                    "src-tauri/src/auth/local_admission_expiry_tests.rs",
                    "src-tauri/src/tools/linux_sandbox.rs",
                    "src-tauri/src/tools/linux_sandbox_tests.rs"], check=True)
    (root / "rustfmt.patch").write_bytes(git("diff", raw=True))
    subprocess.run(["git", "add", "--", *ALL], check=True)
    assert git("diff", "--name-only") == "", "unexpected formatter changes"
    actual = git("diff", "--cached", "--name-only", "-z", raw=True).decode().split("\0")
    assert sorted(p for p in actual if p) == ALL
    env = dict(os.environ, GIT_AUTHOR_NAME="Candidate validation", GIT_AUTHOR_EMAIL="validation@invalid.example",
               GIT_COMMITTER_NAME="Candidate validation", GIT_COMMITTER_EMAIL="validation@invalid.example",
               GIT_AUTHOR_DATE="2026-09-27T00:00:00+0000", GIT_COMMITTER_DATE="2026-09-27T00:00:00+0000")
    subprocess.run(["git", "-c", "commit.gpgsign=false", "commit", "--no-verify", "-m",
                    "candidate: mandatory Linux desktop sandbox"], env=env, check=True)
    print("CANDIDATE=" + git("rev-parse", "HEAD"))
    print("CANDIDATE_TREE=" + git("rev-parse", "HEAD^{tree}"))


def snapshot(root):
    subprocess.run(["git", "diff", "--exit-code", "HEAD", "--"], check=True)
    manifest = {"base": BASE, "commit": git("rev-parse", "HEAD"),
                "tree": git("rev-parse", "HEAD^{tree}"), "files": {}}
    for path in ALL:
        data = Path(path).read_bytes()
        blob = git("rev-parse", f"HEAD:{path}")
        assert blob_hash(data) == blob
        target = root / "source" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        manifest["files"][path] = {"blob": blob, "sha256": hashlib.sha256(data).hexdigest()}
    root.mkdir(parents=True, exist_ok=True)
    (root / "candidate.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    subprocess.run(["git", "bundle", "create", str(root / "source.bundle"), "HEAD"], check=True)


def import_blobs(root):
    a, b = root / "native-ubuntu-24.04", root / "native-windows-2025"
    manifests = [json.loads((p / "candidate.json").read_text(encoding="utf-8")) for p in (a, b)]
    assert manifests[0] == manifests[1], "platform source mismatch"
    manifest = manifests[0]
    assert manifest["base"] == BASE and sorted(manifest["files"]) == ALL
    assert os.environ["GITHUB_REPOSITORY"] == "Eswink/coding-tools-mcp"
    out = {}
    for path, entry in manifest["files"].items():
        data = (a / "source" / path).read_bytes()
        assert data == (b / "source" / path).read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]
        assert blob_hash(data) == entry["blob"]
        body = json.dumps({"content": base64.b64encode(data).decode(), "encoding": "base64"}).encode()
        request = urllib.request.Request(
            "https://api.github.com/repos/Eswink/coding-tools-mcp/git/blobs", data=body,
            headers={"Authorization": "Bearer " + os.environ["GH_TOKEN"],
                     "Accept": "application/vnd.github+json", "Content-Type": "application/json",
                     "X-GitHub-Api-Version": "2022-11-28"}, method="POST")
        with urllib.request.urlopen(request, timeout=60) as response:
            sha = json.load(response)["sha"]
        assert sha == entry["blob"]
        out[path] = sha
    print("VERIFIED_BLOBS=" + json.dumps(out, sort_keys=True))
    print("VERIFIED_TREE=" + manifest["tree"])
    # No ref, commit, release, tag, issue or deployment write is performed here.


if __name__ == "__main__":
    {"prepare": prepare, "snapshot": snapshot, "import": import_blobs}[sys.argv[1]](Path(sys.argv[2]).resolve())
