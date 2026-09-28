#!/usr/bin/env python3
"""Deterministic issue work packets, not an autonomous coding worker.

No network, shell execution, issue-body instructions, secrets or write token.
Verification reads immutable Git blobs and current source bytes; GitHub run IDs
are references for independent CI verification, not self-authenticating proof.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

REPO = "Eswink/coding-tools-mcp"
BRANCH = "feat/cloud-gateway-agent-runtime"
LANES = {"protocol", "identity", "agent-client", "request-admission", "tool-runtime", "packaging", "release-review", "delivery"}
STATES = {"planned", "in_progress", "verified", "blocked", "deferred"}
SHA = re.compile(r"[0-9a-f]{40}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
ID = re.compile(r"[a-z][a-z0-9-]{1,63}\Z")
GATES = {"security-review", "supported-host", "windows-installed", "ubuntu-installed", "real-chatgpt", "reproducible-packages"}


class InvalidManifest(ValueError):
    pass


def require(test, code):
    if not test:
        raise InvalidManifest(code)


def shape(obj, required, optional=()):
    require(type(obj) is dict and set(required) <= set(obj) <= set(required) | set(optional), "invalid_shape")


def safe_path(value):
    require(type(value) is str and 0 < len(value) <= 240 and not any(c in value for c in "\\\x00:\n\r"), "invalid_path")
    p = PurePosixPath(value)
    require(not p.is_absolute() and str(p) == value and all(c not in ("", ".", "..", ".git") for c in value.split("/")), "invalid_path")
    return p


def overlap(left, right):
    a, b = safe_path(left).parts, safe_path(right).parts
    return a[:len(b)] == b or b[:len(a)] == a


def validate(doc):
    shape(doc, ["version", "repository", "integration_branch", "tasks", "release_gates"])
    require(doc["version"] == 1 and type(doc["version"]) is int and doc["repository"] == REPO and doc["integration_branch"] == BRANCH, "wrong_project")
    require(type(doc["tasks"]) is list and 1 <= len(doc["tasks"]) <= 64, "task_count")
    tasks = {}
    issues = set()
    for task in doc["tasks"]:
        shape(task, ["id", "issue", "title", "lane", "state", "priority", "depends_on", "paths", "release_required"], ["evidence", "reason"])
        key = task["id"]
        require(type(key) is str and ID.fullmatch(key) and key not in tasks, "duplicate_or_invalid_id")
        number = task["issue"]
        require(number is None or (type(number) is int and 1 <= number < 1000000 and number not in issues), "duplicate_or_invalid_issue")
        if number is not None:
            issues.add(number)
        require(type(task["title"]) is str and 1 <= len(task["title"]) <= 180 and not any(ord(c) < 32 for c in task["title"]), "invalid_title")
        require(type(task["lane"]) is str and task["lane"] in LANES and type(task["state"]) is str and task["state"] in STATES, "invalid_status_or_lane")
        require(type(task["priority"]) is int and 0 <= task["priority"] <= 100, "invalid_priority")
        require(type(task["release_required"]) is bool, "invalid_release_flag")
        require(type(task["paths"]) is list and 1 <= len(task["paths"]) <= 16, "invalid_paths")
        for path in task["paths"]:
            safe_path(path)
        deps = task["depends_on"]
        require(type(deps) is list and all(type(x) is str for x in deps) and len(set(deps)) == len(deps), "invalid_dependencies")
        if task["state"] in ("blocked", "deferred"):
            require(type(task.get("reason")) is str and 1 <= len(task["reason"]) <= 240, "missing_block_reason")
        if task["state"] == "verified":
            evidence = task.get("evidence")
            shape(evidence, ["revision", "run_id", "files"])
            require(type(evidence["revision"]) is str and SHA.fullmatch(evidence["revision"]), "invalid_evidence_revision")
            require(type(evidence["run_id"]) is int and evidence["run_id"] > 0, "invalid_run")
            require(type(evidence["files"]) is dict and 1 <= len(evidence["files"]) <= 256, "invalid_evidence_files")
            for path, digest in evidence["files"].items():
                safe_path(path)
                require(any(overlap(path, prefix) for prefix in task["paths"]), "evidence_outside_scope")
                require(type(digest) is str and DIGEST.fullmatch(digest), "invalid_evidence_digest")
        tasks[key] = task
    visiting, visited = set(), set()

    def visit(key):
        require(key in tasks, "missing_dependency")
        require(key not in visiting, "dependency_cycle")
        if key in visited:
            return
        visiting.add(key)
        for dep in tasks[key]["depends_on"]:
            visit(dep)
        visiting.remove(key)
        visited.add(key)
    for key in tasks:
        visit(key)
    gates = doc["release_gates"]
    require(type(gates) is dict and set(gates) == GATES, "missing_release_gate")
    for status in gates.values():
        require(type(status) is str and status in {"pending", "pass", "blocked", "deferred"}, "invalid_gate_state")
    return tasks


def git(root, *args):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, timeout=15)
    require(result.returncode == 0, "git_evidence_unavailable")
    return result.stdout


def verify_sources(root, evidence):
    try:
        git(root, "cat-file", "-e", evidence["revision"] + "^{commit}")
        for path, digest in evidence["files"].items():
            item = root / path
            require(item.is_file() and not item.is_symlink() and root in item.resolve().parents, "evidence_path_unavailable")
            require(item.stat().st_size <= 2 * 1024 * 1024, "evidence_too_large")
            require(hashlib.sha256(item.read_bytes()).hexdigest() == digest, "evidence_current_source_changed")
            size = int(git(root, "cat-file", "-s", evidence["revision"] + ":" + path))
            require(0 <= size <= 2 * 1024 * 1024, "evidence_blob_too_large")
            blob = git(root, "show", evidence["revision"] + ":" + path)
            require(hashlib.sha256(blob).hexdigest() == digest, "evidence_commit_mismatch")
        return True
    except (InvalidManifest, OSError, ValueError, subprocess.SubprocessError):
        return False


def plan(doc, root, limit=3, source_check=verify_sources):
    require(type(limit) is int and 1 <= limit <= 8, "invalid_limit")
    tasks = validate(doc)
    root = Path(root).resolve()
    statuses = {k: v["state"] for k, v in tasks.items()}
    for key, task in tasks.items():
        if task["state"] == "verified" and not source_check(root, task["evidence"]):
            statuses[key] = "stale_evidence"
    # A component cannot be verified if its engineering prerequisite is no longer verified.
    for _ in range(len(tasks)):
        changed = False
        for key, task in tasks.items():
            if statuses[key] == "verified" and any(statuses[d] != "verified" for d in task["depends_on"]):
                statuses[key] = "stale_dependency"
                changed = True
        if not changed:
            break
    occupied = [p for t in tasks.values() if t["state"] == "in_progress" for p in t["paths"]]
    active_lanes = {t["lane"] for t in tasks.values() if t["state"] == "in_progress"}
    # Two active writers to overlapping paths are a stop condition, not an invitation to race.
    active = [t for t in tasks.values() if t["state"] == "in_progress"]
    for i, task in enumerate(active):
        for other in active[i+1:]:
            require(task["lane"] != other["lane"] and not any(overlap(a, b) for a in task["paths"] for b in other["paths"]), "active_resource_conflict")
    packets, blocked = [], []
    for task in sorted(tasks.values(), key=lambda t: (t["priority"], t["id"])):
        if statuses[task["id"]] == "verified":
            continue
        deps = [d for d in task["depends_on"] if statuses[d] != "verified"]
        reason = None
        if statuses[task["id"]] != "planned":
            reason = statuses[task["id"]]
        elif deps:
            reason = "dependencies"
        elif task["lane"] in active_lanes or any(overlap(a, b) for a in task["paths"] for b in occupied):
            reason = "resource_busy"
        elif len(packets) >= limit:
            reason = "batch_limit"
        if reason:
            blocked.append({"id": task["id"], "reason": reason, "dependencies": deps})
            continue
        packet = {key: task[key] for key in ("id", "issue", "title", "lane", "paths", "depends_on")}
        packet.update({"action": "create_issue" if task["issue"] is None else "queue_issue",
                       "execution_started": False, "authority": "engineering_only"})
        packets.append(packet)
        occupied.extend(task["paths"])
        active_lanes.add(task["lane"])
    release_blockers = [k for k, t in tasks.items() if t["release_required"] and statuses[k] != "verified"]
    release_blockers += ["gate:" + k for k, state in doc["release_gates"].items() if state != "pass"]
    # This program is not the authorized release publisher and cannot certify external evidence.
    return {"version": 1, "repository": REPO, "branch": BRANCH, "packets": packets,
            "blocked": blocked, "states": statuses, "release_blockers": sorted(release_blockers),
            "release_allowed": False, "release_eligible_for_review": not release_blockers,
            "execution_adapter": "not_attached", "external_ci_attestation": "requires_independent_check"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--require-release-ready", action="store_true")
    args = parser.parse_args()
    require(args.manifest.stat().st_size <= 262144, "manifest_too_large")
    doc = json.loads(args.manifest.read_text(encoding="utf-8"))
    report = plan(doc, args.repo_root, args.limit)
    report["revision"] = git(args.repo_root, "rev-parse", "HEAD").decode().strip()
    require(SHA.fullmatch(report["revision"]), "invalid_source_revision")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Never truncate an existing receipt or follow an output symlink.
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({"packets": len(report["packets"]), "blocked": len(report["blocked"]),
                      "release_eligible_for_review": report["release_eligible_for_review"]}))
    if args.require_release_ready and not report["release_eligible_for_review"]:
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (InvalidManifest, OSError, ValueError, subprocess.SubprocessError) as exc:
        print(json.dumps({"error": "delivery_manifest_rejected", "class": type(exc).__name__}), file=sys.stderr)
        sys.exit(1)
