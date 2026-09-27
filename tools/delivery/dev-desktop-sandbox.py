"""Temporary development driver; never a release asset or production entrypoint."""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import zipfile

ROOT = Path.cwd()
EVIDENCE = ROOT / "evidence"
PLAN_ID = "feature-ubuntu-desktop-sandbox-connect-the-s-5aa75bc66e"
BASE = "9b2639d47aaecc0a903124404c9c97cbf1f806d6"
AUTH = "src-tauri/src/auth/聊天授权v1.rs"
TEST = "src-tauri/src/auth/local_admission_deadline_tests.rs"
AUTH_BLOB = "388920919713c45cf3054d5226e1334a4b7b1fef"
HOOK = '\n#[cfg(test)]\n#[path = "local_admission_deadline_tests.rs"]\nmod local_admission_deadline_tests;\n'


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def download_artifact(artifact_id: int, expected_sha256: str) -> zipfile.ZipFile:
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    request = urllib.request.Request(
        f"https://api.github.com/repos/Eswink/coding-tools-mcp/actions/artifacts/{artifact_id}/zip",
        headers={"Authorization": "Bearer " + os.environ["GH_TOKEN"], "Accept": "application/vnd.github+json"},
    )
    try:
        urllib.request.build_opener(NoRedirect).open(request, timeout=60)
        raise RuntimeError("expected artifact redirect")
    except urllib.error.HTTPError as error:
        if error.code != 302:
            raise
        location = error.headers["Location"]
        if urllib.parse.urlsplit(location).scheme != "https":
            raise RuntimeError("insecure artifact redirect")
    # The GitHub credential is never forwarded to the signed storage URL.
    with urllib.request.urlopen(location, timeout=60) as response:
        data = response.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != expected_sha256:
        raise RuntimeError("artifact identity mismatch")
    return zipfile.ZipFile(io.BytesIO(data))


def prepare_plan() -> None:
    EVIDENCE.mkdir(exist_ok=True)
    with download_artifact(10926726056, "9c063b405d7fdfb02267f2717e276e6a7d86b73f3fc528404af7a7a0b258f066") as archive:
        record = json.loads(archive.read("resumed-checkpoint.json"))["structuredContent"]["record"]
    assert record["planId"] == PLAN_ID
    state_path = ROOT / ".mcp-probe-kit" / "plans" / (PLAN_ID + ".json")
    write_json(state_path, record)
    probe = os.environ["RUNNER_TEMP"] + "/probe/node_modules/.bin/mcp-probe-kit"

    def invoke(name: str, args: dict, label: str) -> dict:
        input_path = EVIDENCE / (label + "-input.json")
        write_json(input_path, args)
        run = subprocess.run([probe, "exec", name, "--input", str(input_path)], text=True,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90)
        (EVIDENCE / (label + ".json")).write_text(run.stdout, encoding="utf-8")
        (EVIDENCE / (label + ".stderr")).write_text(run.stderr, encoding="utf-8")
        result = json.loads(run.stdout)
        assert run.returncode == 0 and result.get("ok") is not False and result.get("isError") is not True, label
        details = result.get("structuredContent", {})
        print(json.dumps({"tool": name, "label": label, "passed": details.get("passed"),
                          "stored": details.get("stored"), "found": details.get("found")}))
        return result

    resumed = invoke("resume_plan", {"project_root": str(ROOT), "plan_id": PLAN_ID}, "resume")
    assert resumed["structuredContent"]["found"] is True
    context_paths = ["AGENTS.md", "docs/graph-insights/latest.md", "docs/graph-insights/latest.json"]
    assert all((ROOT / path).is_file() for path in context_paths)
    write_json(EVIDENCE / "context-hashes.json", {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in context_paths})
    common = {"project_root": str(ROOT), "plan_id": PLAN_ID, "status": "active"}
    invoke("plan_heartbeat", {**common, "current_step_id": "write-spec", "skipped_steps": [{
        "step_id": "context", "reason": "All three required context documents already exist and were read; fresh 18-symbol GitNexus evidence is retained in run36302640460."}]}, "context-checkpoint")
    spec = "docs/specs/ubuntu-desktop-sandbox-connect-the"
    assert all((ROOT / spec / leaf).is_file() for leaf in ["requirements.md", "design.md", "tasks.md"])
    invoke("plan_heartbeat", {**common, "completed_step_ids": ["write-spec"], "current_step_id": "check-spec", "evidence": [{
        "kind": "requirements", "summary": "FR-1..FR-6 and bounded desktop integration written", "reference": spec + "/requirements.md", "revision": os.environ["GITHUB_SHA"]}]}, "written-checkpoint")
    checked = invoke("check_spec", {"project_root": str(ROOT), "feature_name": "ubuntu-desktop-sandbox-connect-the", "docs_dir": "docs"}, "spec-check")
    assert checked["structuredContent"]["passed"] is True
    invoke("plan_heartbeat", {**common, "completed_step_ids": ["write-spec", "check-spec"], "current_step_id": "estimate", "evidence": [{
        "kind": "spec", "summary": "Written specification validated without errors", "reference": "evidence/spec-check.json", "revision": os.environ["GITHUB_SHA"]}]}, "spec-checkpoint")
    estimate_args = next(step["args"] for step in record["plan"]["steps"] if step["id"] == "estimate")
    invoke("estimate", estimate_args, "estimate-guidance")
    write_json(EVIDENCE / "risk-assessment.json", {
        "summary": "High-risk lifecycle integration; implement and verify in separately reviewable increments.",
        "storyPoints": 13, "confidence": "medium",
        "timeEstimates": {"optimistic": "not estimated", "normal": "not estimated", "pessimistic": "not estimated"},
        "breakdown": [],
        "risks": [
            {"risk": "Context constructor reaches 58 upstream symbols (CRITICAL)", "impact": "high", "mitigation": "Keep cfg-gated additions minimal and require both native full suites."},
            {"risk": "Expiry and cancellation across blocking locks and I/O", "impact": "high", "mitigation": "Old/fixed lock regressions, monotonic limits and owned supervisors."},
            {"risk": "Rust graph has ambiguous/missing receivers", "impact": "high", "mitigation": "Read actual callers and test the public dispatcher; no inference from zero graph edges."}
        ],
        "assumptions": ["Pinned Linux kernel rules remain unchanged", "No public authority mint", "Physical host acceptance remains pending", "Story points describe scope, not a future delivery-time promise"]
    })
    invoke("plan_heartbeat", {**common, "completed_step_ids": ["write-spec", "check-spec", "estimate"], "current_step_id": "implement", "evidence": [{
        "kind": "other", "step_id": "estimate", "summary": "Scope and high-risk call chains assessed; no delivery-time estimate", "reference": "evidence/risk-assessment.json", "revision": os.environ["GITHUB_SHA"]}]}, "implementation-checkpoint")
    (EVIDENCE / "plan-state.json").write_bytes(state_path.read_bytes())


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError("non-unique source anchor: " + old[:90])
    return text.replace(old, new, 1)


def patched_auth(original: str) -> str:
    start = original.index("    pub(crate) fn commit_local_admission(")
    end = original.index("    fn permit_locked(", start)
    block = original[start:end]
    check = '        if ticket.expired() {\n            return Err("LOCAL_ADMISSION_EXPIRED");\n        }\n'
    block = replace_once(block, '        if state.revision != ticket.authority_revision {',
                         '        // Waiting for the authorization mutex consumes the ticket lifetime.\n' + check + '        if state.revision != ticket.authority_revision {')
    anchor = '        let execution = gate.try_admit_generation(ticket.execution_generation)?;\n'
    block = replace_once(block, anchor, anchor + '        // The execution gate may also have blocked while the ticket expired.\n' + check)
    block = replace_once(block, '        Ok(LocalAdmissionPermit::new(chat, execution))',
                         '        // Durable fence I/O is part of admission, not an extension of its TTL.\n' + check + '        Ok(LocalAdmissionPermit::new(chat, execution))')
    return original[:start] + block + original[end:] + HOOK


def run_logged(label: str, args: list[str], timeout: int = 1800) -> tuple[int, str]:
    EVIDENCE.mkdir(exist_ok=True)
    path = EVIDENCE / (label + ".log")
    with path.open("w", encoding="utf-8") as output:
        result = subprocess.run(args, stdout=output, stderr=subprocess.STDOUT, timeout=timeout)
    text = path.read_text(encoding="utf-8", errors="replace")
    print(f"=== {label}: exit={result.returncode} ===\n" + text[-5000:])
    write_json(EVIDENCE / (label + "-command.json"), {"args": args, "exit_code": result.returncode})
    return result.returncode, text


def verify_deadline() -> None:
    EVIDENCE.mkdir(exist_ok=True)
    original_bytes = subprocess.check_output(["git", "show", BASE + ":" + AUTH])
    assert blob_sha(original_bytes) == AUTH_BLOB
    assert (ROOT / AUTH).read_bytes() == original_bytes, "development source has unexpected concurrent edits"
    original = original_bytes.decode("utf-8")
    subprocess.run(["rustfmt", "--edition", "2021", TEST], check=True)
    (ROOT / AUTH).write_text(original + HOOK, encoding="utf-8", newline="\n")
    write_json(EVIDENCE / "old-source.json", {"production_base": BASE, "production_blob": AUTH_BLOB,
        "test_hook_blob": blob_sha((ROOT / AUTH).read_bytes()), "test_blob": blob_sha((ROOT / TEST).read_bytes())})
    command = ["cargo", "test", "--locked", "--manifest-path", "src-tauri/Cargo.toml", "--lib", "local_admission_deadline_tests", "--", "--test-threads=1"]
    status, text = run_logged("old-code-regression", command)
    assert status != 0 and "1 passed; 2 failed; 0 ignored" in text, "old-code reproduction did not fail in exactly the expected tests"
    for name in ["ticket_expiring_while_authorization_lock_is_held_is_rejected", "ticket_expiring_while_execution_gate_is_held_is_rejected"]:
        assert name + " ... FAILED" in text, name
    (ROOT / AUTH).write_text(patched_auth(original), encoding="utf-8", newline="\n")
    status, text = run_logged("fixed-code-regression", command)
    assert status == 0 and "3 passed; 0 failed; 0 ignored" in text
    for label, args in [
        ("desktop-all-targets", ["cargo", "check", "--locked", "--all-targets", "--manifest-path", "src-tauri/Cargo.toml"]),
        ("desktop-full-suite", ["cargo", "test", "--locked", "--manifest-path", "src-tauri/Cargo.toml"]),
        ("desktop-strict-library", ["cargo", "rustc", "--locked", "--lib", "--manifest-path", "src-tauri/Cargo.toml", "--", "-D", "warnings"]),
    ]:
        assert run_logged(label, args)[0] == 0, label
    subprocess.run(["git", "diff", "--check"], check=True)
    manifest = {}
    for path in [AUTH, TEST]:
        data = (ROOT / path).read_bytes()
        destination = EVIDENCE / "source" / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        manifest[path] = {"blob": blob_sha(data), "sha256": hashlib.sha256(data).hexdigest()}
    write_json(EVIDENCE / "source-manifest.json", {"workflow_sha": os.environ["GITHUB_SHA"], "base_sha": BASE,
        "classification": "generated-development-variant-not-a-final-commit", "files": manifest})
    (EVIDENCE / "source.diff").write_bytes(subprocess.check_output(["git", "diff", "--", AUTH, TEST]))
    print("DEADLINE_SOURCE_MANIFEST=" + json.dumps(manifest, sort_keys=True))


def export_blobs() -> None:
    roots = [Path(os.environ["RUNNER_TEMP"]) / "native" / name for name in ["ubuntu-24.04", "windows-2025"]]
    manifests = [json.loads((root / "source-manifest.json").read_text(encoding="utf-8")) for root in roots]
    assert manifests[0]["files"] == manifests[1]["files"], "native tested source bytes differ"
    assert set(manifests[0]["files"]) == {AUTH, TEST}
    result = {}
    for path, identity in manifests[0]["files"].items():
        data = (roots[0] / "source" / path).read_bytes()
        assert blob_sha(data) == identity["blob"] and hashlib.sha256(data).hexdigest() == identity["sha256"]
        request = urllib.request.Request(
            "https://api.github.com/repos/Eswink/coding-tools-mcp/git/blobs",
            data=json.dumps({"content": base64.b64encode(data).decode(), "encoding": "base64"}).encode(),
            headers={"Authorization": "Bearer " + os.environ["GH_TOKEN"], "Accept": "application/vnd.github+json", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            sha = json.load(response)["sha"]
        assert sha == identity["blob"]
        result[path] = sha
    write_json(EVIDENCE / "exported-blobs.json", result)
    print("TESTED_DEADLINE_BLOBS=" + json.dumps(result, sort_keys=True))


def hash_evidence() -> None:
    EVIDENCE.mkdir(exist_ok=True)
    write_json(EVIDENCE / "hashes.json", {
        p.relative_to(EVIDENCE).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in EVIDENCE.rglob("*") if p.is_file() and p.name != "hashes.json"
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["plan", "deadline", "blobs", "hash"])
    args = parser.parse_args()
    {"plan": prepare_plan, "deadline": verify_deadline, "blobs": export_blobs, "hash": hash_evidence}[args.action]()
