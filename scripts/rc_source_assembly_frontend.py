#!/usr/bin/env python3
"""Fail-closed PR94 browser/frontend acceptance for the reviewed RC assembly.

The assembly source guard owns ancestry and integration scope. This verifier
retains the concrete frontend assertions and binds them to its source receipt.
Real browsers with synthetic IPC are not native or release acceptance.
"""
import argparse
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess

from exact_build_audit import EvidenceError, decode, need, read

REPOSITORY = "Eswink/coding-tools-mcp"
REF = "refs/heads/ci/rc-source-assembly-v2-20261001"
WORKFLOW = REPOSITORY + "/.github/workflows/rc-source-assembly.yml@" + REF
STEPS = "checkout source node python versions install dependency check build regression audit playwright browser_dependencies sandbox cloud ui hooks snapshots".split()
SANDBOX = ('import json,os; from playwright.sync_api import sync_playwright; '
           'p=sync_playwright().start(); b=p.chromium.launch(headless=True, '
           'chromium_sandbox=True, executable_path=os.environ["CHROMIUM_PATH"]); '
           'print(json.dumps({"chromium_sandbox":True,"browser_version":b.version,'
           '"native_verified":False})); b.close(); p.stop()')
COMMANDS = {
    "versions": ["bash", "-euo", "pipefail", "-c", "node --version; npm --version; python --version; npm config get registry; npm config get omit"],
    "npm-ci": ["npm", "ci"],
    "npm-ls-devalue": ["npm", "ls", "devalue", "--json"],
    "frontend-check": ["npm", "run", "check"],
    "frontend-build": ["npm", "run", "build"],
    "frontend-full": ["node", "scripts/前端完整回归v4.mjs"],
    "npm-audit": ["npm", "audit", "--json"],
    "playwright-install": ["python", "-m", "pip", "install", "playwright==1.58.0"],
    "browser-dependencies": ["python", "-m", "playwright", "install", "--with-deps", "chromium"],
    "sandbox-preflight": ["python", "-c", SANDBOX],
    "cloud-browser": ["python", "tests/cloud-connection-browser.py"],
    "ui-browser": ["python", "tests/ui-refactor-browser.py"],
    "hooks-browser": ["python", "tests/policy-hooks-browser.py"],
    "snapshots-browser": ["python", "tests/workspace-snapshots-browser.py"],
}
INPUT_ROOTS = ["src", "tests", "package.json", "package-lock.json", "pnpm-lock.yaml",
               "pnpm-workspace.yaml", "vite.config.js", "svelte.config.js", "tsconfig.json",
               "src-tauri/tauri.conf.json", "scripts/前端完整回归v4.mjs",
               ".github/workflows/issue84-frontend-acceptance.yml",
               ".github/workflows/rc-source-assembly.yml"]
REQUIRED_INPUTS = {
    "package.json", "package-lock.json", "pnpm-lock.yaml", "pnpm-workspace.yaml",
    "vite.config.js", "svelte.config.js", "tsconfig.json", "src-tauri/tauri.conf.json",
    "scripts/前端完整回归v4.mjs", "tests/devalue-security.test.mjs",
    "tests/fixtures/ui-refactor-ipc.js", "tests/ui_refactor_states.py",
    "tests/browser_viewport_evidence.py", "tests/cloud-connection-browser.py",
    "tests/ui-refactor-browser.py", "tests/policy-hooks-browser.py", "tests/workspace-snapshots-browser.py",
}
CLOUD_STATES = {"unconfigured", "configured", "starting", "connected", "pending_approval",
                "approved", "paused", "draining", "recovery"}
UI_STATES = {"empty-workspace", "empty-frp", "empty-software", "long-workspace",
             "partial-secret-failure", "task-empty-and-error", "approval-minimum-dark", "system-theme-live"}
UI_SCENARIOS = {
    "real settings and sidebar theme controls share persisted state",
    "global profile editing preserves blank-token keep semantics and route identity",
    "all shared credentials masked, no plaintext synthetic secret rendered",
    "manual keyboard tab activation and actual log component render the typed result",
    "health starts unchecked and failed requests never render a passing state",
    "cancel keeps actual unsaved config; explicit confirmation alone switches service",
    "successful actual form save clears navigation warning without granting permissions",
    "reverted input is clean and does not produce a stale leave confirmation",
    "software table exposes only supported installation facts, not invented versions",
    "unchanged global approval host works across routes and requires fingerprint/scope subset",
}
HOOK_SCENARIOS = {
    "exact escaped preview and checkbox, cancellation consumes token",
    "exact digest submitted only after explicit review",
    "uncertain mutation stays locked through read-only refresh",
    "disable retains recovery lock",
}


def safe_path(base, relative):
    need(isinstance(relative, str) and relative and "\\" not in relative, "invalid evidence path")
    parts = PurePosixPath(relative).parts
    need(not PurePosixPath(relative).is_absolute() and all(p not in (".", "..") for p in parts)
         and str(PurePosixPath(relative)) == relative, "noncanonical evidence path")
    path = base
    for part in parts:
        path = path / part
        need(not path.is_symlink(), "symlink evidence path: " + relative)
    need(path.resolve().is_relative_to(base.resolve()), "escaped evidence path")
    return path


def raw(base, relative):
    return read(safe_path(base, relative))


def document(base, relative):
    return decode(raw(base, relative))


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def rows(report, key, size, label):
    value = report.get(key)
    need(type(value) is list and len(value) == size, f"{label}: expected {size} {key}")
    return value


def image(evidence, relative):
    need(raw(evidence, relative).startswith(b"\x89PNG\r\n\x1a\n"), "missing PNG: " + relative)


def utc_time(value):
    need(isinstance(value, str) and re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)", value), "invalid command UTC timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    need(parsed.utcoffset() == timedelta(0), "non-UTC command timestamp")
    return parsed


def commands(evidence):
    outcomes = document(evidence, "step-outcomes.json")
    for name in STEPS:
        need(outcomes.get(name, {}).get("outcome") == "success", "failed/skipped step: " + name)
    for name, expected in COMMANDS.items():
        prefix = "commands/" + name + "/"
        receipt = document(evidence, prefix + "command.json")
        need(receipt.get("command") == expected, "unexpected command argv: " + name)
        need(type(receipt.get("exit")) is int and receipt["exit"] == 0, "nonzero command exit: " + name)
        need(raw(evidence, prefix + "exit-code.txt").decode().strip() == "0", "command exit disagreement: " + name)
        need(utc_time(receipt.get("started_at")) <= utc_time(receipt.get("completed_at")), "reversed command timestamps: " + name)
        stdout = raw(evidence, prefix + "stdout.txt")
        if name == "ui-browser" and not stdout.strip():
            # The unchanged UI runner writes files without printing on success.
            # Quiet output is valid only with its full UI/report/source proof.
            ui(evidence, document(evidence, "source.json")["inputs"])
        else:
            need(stdout.strip(), "empty command stdout: " + name)
        raw(evidence, prefix + "stderr.txt")  # Empty stderr is valid, missing stderr is not.


def source(root, evidence):
    report = document(evidence, "source.json")
    head, tree = git(root, "rev-parse", "HEAD"), git(root, "rev-parse", "HEAD^{tree}")
    need(report.get("source_sha") == report.get("workflow_sha") == head == os.environ.get("GITHUB_SHA"), "source/workflow SHA mismatch")
    need(report.get("source_tree") == tree, "source tree mismatch")
    for key, expected in (("repository", REPOSITORY), ("ref", REF), ("workflow_ref", WORKFLOW)):
        need(report.get(key) == expected, "wrong source " + key)
    for key, env in (("repository", "GITHUB_REPOSITORY"), ("ref", "GITHUB_REF"),
                     ("workflow_ref", "GITHUB_WORKFLOW_REF"), ("workflow_sha", "GITHUB_WORKFLOW_SHA"),
                     ("run_id", "GITHUB_RUN_ID"), ("run_attempt", "GITHUB_RUN_ATTEMPT")):
        need(report.get(key) == os.environ.get(env), "source context mismatch: " + key)
    for key in ("run_id", "run_attempt"):
        need(isinstance(report.get(key), str) and re.fullmatch(r"[1-9][0-9]*", report[key]), "invalid source " + key)
    need(report.get("engineering_only") is True, "engineering scope missing")
    for flag in ("release_approved", "publish_approved", "native_verified", "real_chatgpt_verified"):
        need(report.get(flag) is False, "engineering scope mismatch: " + flag)
    inputs = report.get("inputs")
    need(type(inputs) is dict and REQUIRED_INPUTS <= inputs.keys(), "input manifest incomplete")
    tracked = set(filter(None, git(root, "ls-files", "-z", "--", *INPUT_ROOTS).split("\0")))
    need(tracked <= inputs.keys(), "tracked frontend input manifest incomplete")
    for name, item in inputs.items():
        need(type(item) is dict and sha256(raw(root, name)) == item.get("sha256"), "input changed: " + name)
        need(git(root, "rev-parse", "HEAD:" + name) == item.get("git_blob"), "input blob mismatch: " + name)
    clean = subprocess.run(["git", "-C", str(root), "diff", "--exit-code", "HEAD", "--"], capture_output=True)
    safe_path(evidence, "tracked-clean.txt").write_bytes(clean.stdout + clean.stderr)
    need(clean.returncode == 0, "tracked source changed during execution")
    return report


def build(root, evidence):
    manifest = {p.relative_to(root).as_posix(): sha256(raw(root, p.relative_to(root).as_posix()))
                for p in sorted((root / "build").rglob("*")) if p.is_file()}
    need("build/index.html" in manifest and len(manifest) > 1, "built output missing")
    path = safe_path(evidence, "build-manifest.json")
    if path.exists():
        need(document(evidence, "build-manifest.json") == manifest, "built output hashes changed")
    else:
        path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def audit(evidence):
    data = raw(evidence, "npm-audit.json")
    need(data == raw(evidence, "commands/npm-audit/stdout.txt"), "audit JSON was modified")
    need(raw(evidence, "npm-audit.stderr.txt") == raw(evidence, "commands/npm-audit/stderr.txt"), "audit stderr was modified")
    report = decode(data)
    need("error" not in report and report.get("vulnerabilities") == {}, "audit error or vulnerability entries")
    counts = report.get("metadata", {}).get("vulnerabilities", {})
    need(all(type(counts.get(k)) is int and counts[k] == 0
             for k in ("info", "low", "moderate", "high", "critical", "total")), "audit counts missing/nonzero/invalid")
    total = report.get("metadata", {}).get("dependencies", {}).get("total")
    need(type(total) is int and total > 0, "empty audit dependency scope")
    dependency = document(evidence, "commands/npm-ls-devalue/stdout.txt")
    need(type(dependency) is dict and bool(dependency.get("dependencies")), "empty dependency tree")


def regression(evidence):
    full = re.sub(r"\x1b\[[0-9;]*m", "", raw(evidence, "commands/frontend-full/stdout.txt").decode())
    for key, value in (("tests", 233), ("pass", 233), ("fail", 0), ("cancelled", 0), ("skipped", 0), ("todo", 0)):
        need(re.findall(r"^(?:#|ℹ) " + key + r" (\d+)\s*$", full, re.M) == [str(value)], "frontend count mismatch: " + key)
    for name in ("both lockfiles select the same verified devalue package and integrity",
                 "serialized Set rejects an out-of-bounds reference", "supported serialization still round-trips shared values"):
        need(name in full, "missing devalue regression: " + name)


def browser_provenance(evidence):
    sandbox = document(evidence, "commands/sandbox-preflight/stdout.txt")
    need(sandbox.get("chromium_sandbox") is True and sandbox.get("native_verified") is False
         and isinstance(sandbox.get("browser_version"), str) and sandbox["browser_version"], "sandbox preflight absent/invalid")
    for name in ("chrome-version.txt", "chrome-sha256.txt", "playwright-version.txt"):
        need(raw(evidence, name).strip(), "missing browser provenance: " + name)
    need(re.fullmatch(rb"[0-9a-f]{64}  /opt/google/chrome/chrome\n?", raw(evidence, "chrome-sha256.txt")), "invalid Chrome binary hash provenance")
    need(re.search(r"^Version: 1\.58\.0$", raw(evidence, "playwright-version.txt").decode(), re.M), "wrong Playwright version")
    need(sandbox["browser_version"] in raw(evidence, "chrome-version.txt").decode(), "Chrome/preflight version mismatch")


def cloud(evidence):
    report = document(evidence, "cloud-ui/report.json")
    states = rows(report, "states", 9, "cloud")
    need(set(states) == CLOUD_STATES, "cloud states mismatch")
    for flag in ("ok", "global_drain_warning_outside_workspace", "confirmation_cancelled_without_submit", "explicit_normal_start_without_initialization"):
        need(report.get(flag) is True, "cloud missing assertion: " + flag)
    need(report.get("errors") == [] and report.get("native_verified") is False
         and report.get("real_host_verified") is False, "cloud error/scope mismatch")
    for name in states + ["connected-390", "connected-1280", "global-drain-warning"]:
        image(evidence, "cloud-ui/" + name + ".png")


def ui(evidence, inputs):
    report = document(evidence, "existing-ui/result.json")
    need(report.get("ok") is True and report.get("mode") == "candidate" and report.get("browser_errors") == [], "UI result incomplete")
    need(report.get("native_verified") is False and report.get("real_chatgpt_verified") is False, "UI scope mismatch")
    screens = rows(report, "screens", 40, "UI")
    expected = {(p, w, h, t) for p in ("workspace-overview", "general-settings", "credentials-and-keys", "frp-configuration", "software-management")
                for w, h in ((1586, 992), (1280, 800), (960, 640), (1920, 1080)) for t in ("light", "dark")}
    need({(x["page"], x["width"], x["height"], x["theme"]) for x in screens} == expected, "UI screen coverage mismatch")
    for row in screens:
        need(row.get("overflow") == [], "UI overflow")
        need(row["file"] == f'{row["page"]}-{row["width"]}x{row["height"]}-{row["theme"]}.png', "UI screenshot filename mismatch")
        image(evidence, "existing-ui/" + row["file"])
    scenarios = rows(report, "scenarios", 10, "UI")
    need({row["name"] for row in scenarios} == UI_SCENARIOS and all(row.get("ok") is True for row in scenarios), "UI scenario failed/missing")
    states = rows(report, "state_scenarios", 8, "UI")
    need(document(evidence, "existing-ui/state-results.json") == states, "UI state reports differ")
    need({row["name"] for row in states} == UI_STATES, "UI state coverage mismatch")
    for row in states:
        need(row.get("ok") is True and row.get("native_verified") is False, "UI state failed/scope mismatch")
        need(row["file"] == "state-" + row["name"] + ".png", "UI state filename mismatch")
        image(evidence, "existing-ui/" + row["file"])
    manifest = document(evidence, "existing-ui/source-manifest.json")
    need(manifest.get("files") == {p: v["sha256"] for p, v in inputs.items() if p.startswith("src/")}, "UI source manifest mismatch")
    need(manifest.get("fixture_sha256") == inputs["tests/fixtures/ui-refactor-ipc.js"]["sha256"], "UI fixture mismatch")


def viewports(root, evidence, directory, report, stem, height, controls):
    config = document(root, "src-tauri/tauri.conf.json")["app"]["windows"][0]
    minimum = {"source": "src-tauri/tauri.conf.json", "min_width": config["minWidth"], "min_height": config["minHeight"]}
    need(report.get("native_window_contract") == minimum and report.get("mobile_visual_acceptance") is False, directory + ": native viewport scope mismatch")
    records = rows(report, "viewport_evidence", 3, directory)
    need({(row["width"], row["height"]) for row in records} == {(w, height) for w in (390, minimum["min_width"], 1280)}, directory + ": viewport coverage mismatch")
    for viewport in records:
        width = viewport["width"]
        classification = ("supported_native_window" if width >= minimum["min_width"] and height >= minimum["min_height"]
                          else "diagnostic_outside_native_window_contract")
        need(viewport.get("classification") == classification, directory + ": viewport classification mismatch")
        checkpoints = rows(viewport, "checkpoints", 3, directory)
        need([row.get("control") for row in checkpoints] == controls, directory + ": control coverage mismatch")
        for index, checkpoint in enumerate(checkpoints):
            filename = f"{stem}-{width}.png" if index == 2 else f"{stem}-{width}-{controls[index]}.png"
            need(checkpoint.get("image") == filename and checkpoint.get("image_scope") == "visible_viewport", directory + ": checkpoint image mismatch")
            need(checkpoint.get("minimum_intersection_ratio") == 0.98 and type(checkpoint.get("enabled")) is bool
                 and checkpoint.get("actionability_checked_without_click") is checkpoint["enabled"], directory + ": checkpoint visibility/actionability mismatch")
            image(evidence, directory + "/" + filename)


def hooks_snapshots(root, evidence):
    hooks = document(evidence, "hooks-ui/report.json")
    need(hooks.get("ok") is True and hooks.get("errors") == [] and hooks.get("native_verified") is False, "Hooks result/scope mismatch")
    need(set(rows(hooks, "scenarios", 4, "Hooks")) == HOOK_SCENARIOS, "Hooks scenario coverage mismatch")
    snapshots = document(evidence, "snapshot-ui/report.json")
    for flag in ("ok", "owner_cancel_preserved", "plan_bound_restore", "no_auto_capture"):
        need(snapshots.get(flag) is True, "snapshot missing assertion: " + flag)
    need(snapshots.get("errors") == [] and snapshots.get("native_verified") is False
         and snapshots.get("real_host_verified") is False, "snapshot error/scope mismatch")
    viewports(root, evidence, "hooks-ui", hooks, "preview", 1000, ["manifest", "review", "approval"])
    viewports(root, evidence, "snapshot-ui", snapshots, "restore-plan", 900, ["workspace", "plan", "restore"])


def verify(root, evidence):
    """Return an engineering-only summary; malformed/missing evidence never passes."""
    root, evidence = Path(root).resolve(), Path(evidence).resolve()
    failures, report = [], {}
    try:
        report = source(root, evidence)
    except Exception as error:
        failures.append(f"source: {type(error).__name__}: {error}")
    checks = [("commands", lambda: commands(evidence)), ("build", lambda: build(root, evidence)),
              ("audit", lambda: audit(evidence)), ("regression", lambda: regression(evidence)),
              ("browser provenance", lambda: browser_provenance(evidence)), ("cloud", lambda: cloud(evidence)),
              ("UI", lambda: ui(evidence, report.get("inputs", {}))),
              ("Hooks/snapshots", lambda: hooks_snapshots(root, evidence))]
    for label, check in checks:
        try:
            check()
        except Exception as error:
            failures.append(f"{label}: {type(error).__name__}: {error}")
    return {"source_sha": report.get("source_sha", os.environ.get("GITHUB_SHA")),
            "source_tree": report.get("source_tree"), "passed": not failures, "failures": failures,
            "scope": "RC source assembly frontend engineering only; real browser, synthetic IPC",
            "engineering_only": True, "release_approved": False, "publish_approved": False,
            "native_verified": False, "real_chatgpt_verified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    args.evidence.mkdir(parents=True, exist_ok=True)
    context_error = None
    if "STEP_OUTCOMES" in os.environ:
        try:
            outcomes = decode(os.environ["STEP_OUTCOMES"].encode())
            need(type(outcomes) is dict, "invalid step outcome object")
            safe_path(args.evidence, "step-outcomes.json").write_text(json.dumps(outcomes) + "\n", encoding="utf-8")
        except (OSError, ValueError) as error:
            context_error = "step outcomes: " + str(error)
    summary = verify(args.root, args.evidence)
    if context_error is not None:
        summary["passed"] = False
        summary["failures"].append(context_error)
    payload = json.dumps(summary, indent=2) + "\n"
    safe_path(args.evidence, "acceptance-summary.json").write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
