"""Run exact, isolated MCP host acceptance tests without confusing red with green.

The Rust probe is outside Cargo's automatic test discovery. It is copied into a
throwaway checkout's auth test module, never into committed production sources.
Only an exact one-test assertion failure with its expected gap marker is a red
witness. Compilation, timeout, no-match, ignored, or setup errors are not proof.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
CONTROL = [
    "control_unapproved_chat_cannot_spawn",
    "control_approved_workspace_script_executes",
    "control_pause_and_revoke_block_new_children",
    "control_foreign_chat_cannot_use_approved_workspace",
]
GAPS = {
    "acceptance_omitted_policy_never_spawns_unsandboxed": "SANDBOX_GAP_OMITTED_POLICY",
    "acceptance_workspace_read_cannot_escape": "SANDBOX_GAP_FS_READ",
    "acceptance_symlink_cannot_escape": "SANDBOX_GAP_SYMLINK",
    "acceptance_workspace_write_cannot_escape": "SANDBOX_GAP_FS_WRITE",
    "acceptance_safe_mode_denies_loopback_network": "SANDBOX_GAP_NETWORK",
    "acceptance_model_cannot_disable_sandbox": "SANDBOX_GAP_MODEL_SWITCH",
    "acceptance_tty_flag_cannot_bypass_isolation": "SANDBOX_GAP_TTY",
}
SUMMARY = re.compile(r"test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) ignored;")


def classify(returncode: int, text: str, marker: str | None) -> str:
    summaries = SUMMARY.findall(text)
    if returncode == 0 and summaries == [("ok", "1", "0", "0")]:
        return "pass"
    if (returncode == 101 and marker and marker in text
            and "PROBE_SETUP:" not in text
            and summaries == [("FAILED", "0", "1", "0")]):
        return "gap_confirmed"
    return "invalid_evidence"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expect-gap", action="store_true",
                        help="Diagnose the pinned pre-integration baseline; never a safety PASS")
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    out = args.evidence.resolve()
    out.mkdir(parents=True, exist_ok=True)
    auth = ROOT / "src-tauri/src/auth/mod.rs"
    target = auth.with_name("sandbox_dispatch_probe.rs")
    original = auth.read_bytes()
    if target.exists() or b"sandbox_dispatch_probe" in original:
        raise SystemExit("Refusing to overwrite an existing probe module")
    source = ROOT / "tests/cloud-gateway/ubuntu_sandbox_dispatch.rs"
    receipt = {"mode": "diagnostic" if args.expect_gap else "acceptance",
               "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
               "tree": subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True).strip(),
               "probe_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "tests": {}}
    target.write_bytes(source.read_bytes())
    auth.write_bytes(original + b'\n#[cfg(all(test, target_os = "linux"))]\nmod sandbox_dispatch_probe;\n')
    env = {**os.environ, "CARGO_TERM_COLOR": "never", "RUST_BACKTRACE": "0"}
    try:
        # Compile once: cargo failure is never an accepted red regression.
        compile_cmd = ["cargo", "test", "--locked", "--manifest-path", "src-tauri/Cargo.toml", "--lib", "--no-run"]
        with (out / "compile.txt").open("w") as log:
            built = subprocess.run(compile_cmd, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=1800)
        receipt["compile_exit"] = built.returncode
        if built.returncode != 0:
            receipt["error"] = "probe compilation failed"
        else:
            for test in CONTROL + list(GAPS):
                cmd = ["cargo", "test", "--locked", "--manifest-path", "src-tauri/Cargo.toml", "--lib",
                       f"auth::sandbox_dispatch_probe::{test}", "--", "--exact", "--nocapture"]
                try:
                    run = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=40)
                    text, code = run.stdout + run.stderr, run.returncode
                except subprocess.TimeoutExpired:
                    text, code = "PROBE_SETUP: per-test deadline exceeded\n", 124
                (out / (test + ".txt")).write_text(text, encoding="utf-8")
                status = classify(code, text, GAPS.get(test))
                receipt["tests"][test] = {"exit_code": code, "status": status}
                print(f"{test}: {status}", flush=True)
    finally:
        auth.write_bytes(original)
        target.unlink()
        receipt["production_source_restored"] = auth.read_bytes() == original
        controls_ok = all(receipt["tests"].get(t, {}).get("status") == "pass" for t in CONTROL)
        gaps_confirmed = all(receipt["tests"].get(t, {}).get("status") == "gap_confirmed" for t in GAPS)
        receipt["controls_passed"] = controls_ok
        receipt["acceptance_passed"] = controls_ok and all(
            receipt["tests"].get(t, {}).get("status") == "pass" for t in GAPS)
        receipt["diagnostic_complete"] = controls_ok and gaps_confirmed
        (out / "result.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        (out / "sha256.json").write_text(json.dumps({
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in out.iterdir() if p.is_file() and p.name != "sha256.json"
        }, indent=2), encoding="utf-8")
    return 0 if receipt["diagnostic_complete" if args.expect_gap else "acceptance_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
