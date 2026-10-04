"""Run six authenticated HTTP cases and one direct dispatcher case on Linux.

A successful compilation and exactly one passing test per invocation are required.
This temporarily injects test-only Rust, restores source on ordinary failures, and
never treats a diagnostic red witness as passing acceptance. No real credentials.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
CASES = (
    "authenticated_environment_and_child_boundary_are_truthful",
    "authenticated_child_environment_stdin_and_temp_are_confined",
    "authenticated_zero_yield_input_completes_without_replay",
    "authenticated_dangerous_mode_still_denies_network",
    "approved_primary_missing_policy_fails_closed_without_hooks",
    "authenticated_timeout_stops_sandboxed_process_tree",
    "authenticated_kill_session_stops_sandboxed_process_tree",
)
CASE_PATHS = {name: "auth::sandbox_lifecycle_probe::"
              + ("deadline::" if name in CASES[-2:] else "") + name for name in CASES}
PAYLOADS = {
    "sandbox_lifecycle_probe.rs": "tests/cloud-gateway/linux_sandbox_lifecycle.rs",
    "linux_sandbox_lifecycle_support.rs": "tests/cloud-gateway/linux_sandbox_lifecycle_support.rs",
    "linux_sandbox_deadline.rs": "tests/cloud-gateway/linux_sandbox_deadline.rs",
}
GOLDEN = {
    "tests/cloud-gateway/ubuntu_sandbox_dispatch.rs":
        "aed13ff4af30cbb0dbf693ad250991e375f61f005106295528fa16af2d6ab032",
    "tests/cloud-gateway/sandbox-dispatch/run_probe.py":
        "6d6288fb2a5f119f734a268a80e540f0b75faefa85df7a32ebe7b47417f54b22",
}
SPEC = importlib.util.spec_from_file_location(
    "unchanged_sandbox_dispatch", ROOT / "tests/cloud-gateway/sandbox-dispatch/run_probe.py")
golden = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(golden)
INJECTION = b'\n#[cfg(all(test, target_os = "linux", target_arch = "x86_64"))]\nmod sandbox_lifecycle_probe;\n'
TOTAL_TIMEOUT = 75 * 60


def hashes(root: Path) -> dict:
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in GOLDEN}


def run_owned(cmd: list, *, cwd: Path, env: dict, timeout: float,
              stdout=None) -> tuple:
    """Own the Cargo/test process group and bound kill/reap as well as execution."""
    try:
        child = subprocess.Popen(cmd, cwd=cwd, env=env, start_new_session=True,
                                 stdout=stdout if stdout is not None else subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True)
    except OSError as error:
        return 127, f"PROBE_SETUP: could not execute command: {error}\n"
    try:
        output, _ = child.communicate(timeout=timeout)
        return child.returncode, output or ""
    except subprocess.TimeoutExpired as error:
        partial = error.output or ""
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", errors="replace")
        cleanup = ""
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError as failure:
            cleanup = f"; group termination uncertain: {failure}"
        try:
            output, _ = child.communicate(timeout=5)
            partial = output or partial
        except subprocess.TimeoutExpired:
            # A descendant may hold a pipe after the test process has died.
            # Never wait indefinitely for it; the fixture itself also self-exits.
            if child.stdout is not None:
                child.stdout.close()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cleanup += "; process reap unconfirmed"
        return 124, partial + f"\nPROBE_SETUP: command deadline exceeded{cleanup}\n"


def run_case(root: Path, name: str, env: dict, deadline: float) -> tuple:
    cmd = ["cargo", "test", "--locked", "--manifest-path", "src-tauri/Cargo.toml",
           "--lib", CASE_PATHS[name],
           "--", "--exact", "--nocapture", "--test-threads=1"]
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return 124, "PROBE_SETUP: total runner deadline exceeded\n"
    return run_owned(cmd, cwd=root, env=env, timeout=min(40, remaining))


def write_receipt(out: Path, receipt: dict) -> None:
    (out / "result.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    (out / "sha256.json").write_text(json.dumps({
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in out.iterdir() if p.is_file() and p.name != "sha256.json"
    }, indent=2) + "\n", encoding="utf-8")


def run_probe(root: Path, out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    receipt = {"mode": "acceptance",
               "scope": "synthetic-authenticated Linux A/D/deadline HTTP and E direct dispatcher",
               "platform": platform.platform(), "tests": {}, "acceptance_passed": False,
               "compile_exit": None, "production_source_restored": False}
    auth = root / "src-tauri/src/auth/mod.rs"
    targets = [auth.with_name(name) for name in PAYLOADS]
    original = None
    injected = []
    auth_touched = False
    deadline = time.monotonic() + TOTAL_TIMEOUT
    try:
        if platform.system() != "Linux" or platform.machine() != "x86_64":
            raise RuntimeError("requires native Linux x86_64, not a skipped acceptance")
        receipt["head"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True, timeout=10).strip()
        receipt["tree"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD^{tree}"], cwd=root, text=True, timeout=10).strip()
        receipt["golden_sha256"] = hashes(root)
        if receipt["golden_sha256"] != GOLDEN:
            raise RuntimeError("original golden probe bytes changed")
        original = auth.read_bytes()
        if (any(target.exists() for target in targets) or b"sandbox_lifecycle_probe" in original
                or auth.with_name("sandbox_dispatch_probe.rs").exists()
                or b"mod sandbox_dispatch_probe" in original):
            raise RuntimeError("refusing preexisting or concurrent probe injection")
        payloads = {name: (root / source).read_bytes() for name, source in PAYLOADS.items()}
        receipt["payload_sha256"] = {
            PAYLOADS[name]: hashlib.sha256(payload).hexdigest()
            for name, payload in payloads.items()
        }
        receipt["probe_sha256"] = receipt["payload_sha256"][PAYLOADS["sandbox_lifecycle_probe.rs"]]
        for name, payload in payloads.items():
            target = auth.with_name(name)
            with target.open("xb") as stream:
                injected.append(target)  # Own even a partially written payload.
                stream.write(payload)
        auth_touched = True  # A partial registration write still needs restoration.
        auth.write_bytes(original + INJECTION)
        env = {**os.environ, "CARGO_TERM_COLOR": "never", "RUST_BACKTRACE": "0",
               "PATH": "/usr/bin:/bin:" + os.environ.get("PATH", ""),
               "CTM_LIFECYCLE_HOST_ONLY": "synthetic-host-value"}
        compile_cmd = ["cargo", "test", "--locked", "--manifest-path", "src-tauri/Cargo.toml",
                       "--lib", "--no-run"]
        with (out / "compile.txt").open("w", encoding="utf-8") as log:
            code, text = run_owned(compile_cmd, cwd=root, env=env, stdout=log,
                                   timeout=min(1800, deadline - time.monotonic()))
            log.write(text)
        receipt["compile_exit"] = code
        if code != 0:
            raise RuntimeError("probe compilation failed")
        for name in CASES:
            code, text = run_case(root, name, env, deadline)
            (out / (name + ".txt")).write_text(text, encoding="utf-8")
            status = golden.classify(code, text, None)
            # Even an apparent success cannot hide a fixture/setup warning.
            if "PROBE_SETUP:" in text:
                status = "invalid_evidence"
            receipt["tests"][name] = {"exit_code": code, "status": status,
                                      "test_filter": CASE_PATHS[name]}
            print(f"{name}: {status}", flush=True)
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        receipt["error"] = f"PROBE_SETUP: {error}"
    finally:
        cleanup_errors = []
        if auth_touched:
            try:
                auth.write_bytes(original)
            except OSError as error:
                cleanup_errors.append(f"source restoration failed: {error}")
        for target in injected:
            try:
                target.unlink()
            except OSError as error:
                cleanup_errors.append(f"injected module removal failed: {target.name}: {error}")
        if original is not None:
            try:
                receipt["production_source_restored"] = (
                    auth.read_bytes() == original and all(not target.exists() for target in injected))
            except OSError as error:
                cleanup_errors.append(f"source restoration check failed: {error}")
        if cleanup_errors:
            receipt["cleanup_errors"] = cleanup_errors
            receipt["production_source_restored"] = False
        try:
            receipt["golden_unchanged"] = hashes(root) == GOLDEN
        except OSError as error:
            receipt["golden_unchanged"] = False
            receipt["error"] = f"PROBE_SETUP: golden source unavailable: {error}"
        receipt["acceptance_passed"] = (
            receipt["compile_exit"] == 0
            and "error" not in receipt
            and receipt["production_source_restored"]
            and all(not target.exists() for target in targets)
            and receipt["golden_unchanged"]
            and set(receipt["tests"]) == set(CASES)
            and all(receipt["tests"][name]["status"] == "pass" for name in CASES)
        )
        write_receipt(out, receipt)
    return 0 if receipt["acceptance_passed"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    return run_probe(ROOT, args.evidence.resolve())


if __name__ == "__main__":
    sys.exit(main())
