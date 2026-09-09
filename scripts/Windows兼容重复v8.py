"""Bounded real Windows regression repetitions; any failed/empty run stops the gate."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time

COMPAT = "tools::exec::tests::windows_workspace_scripts_and_python_unicode_execute_successfully"
NEGATIVE = "tools::windows_regression_v8::windows_explicit_timeout_remains_enforced"
RETAINED = "tools::windows_regression_v8::windows_compatibility_follows_retained_session_once"


def validate_result(code: int, text: str) -> None:
    if code != 0 or len(re.findall(r"test result: ok\. 1 passed; 0 failed; 0 ignored;", text)) != 1:
        raise ValueError("Windows regression failed or did not execute exactly one test")


def run(output: Path) -> None:
    if os.name != "nt":
        raise RuntimeError("this proof requires native Windows")
    output.mkdir(parents=True, exist_ok=True)
    results = []
    report = {"passed": False, "source_sha": os.environ["GITHUB_SHA"],
              "run_id": os.environ["GITHUB_RUN_ID"], "results": results}
    try:
        with (output / "Windows兼容重复v8.log").open("w", encoding="utf-8") as log:
            for index, name in enumerate([COMPAT] * 20 + [NEGATIVE, RETAINED], start=1):
                started = time.monotonic()
                command = ["cargo", "test", "--locked", "--manifest-path", "src-tauri/Cargo.toml",
                           "--lib", name, "--", "--exact", "--nocapture"]
                result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        encoding="utf-8", errors="replace", timeout=180, check=False)
                log.write(f"\n=== iteration {index}: {name} ===\n{result.stdout}\n")
                log.flush()
                validate_result(result.returncode, result.stdout)
                results.append({"index": index, "test": name, "passed": True,
                                "elapsed_ms": round((time.monotonic() - started) * 1000)})
        report.update(passed=True, compatibility_repetitions=20, explicit_timeout_verified=True,
                      retained_session_verified=True)
    finally:
        (output / "Windows兼容结果v8.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": True, "runs": len(results)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output.resolve())
