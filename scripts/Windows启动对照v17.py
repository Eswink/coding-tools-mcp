"""Run the medium-token GUI probe in the SAME shell scene as native acceptance.

Only disposable GitHub-hosted Windows runners for this repository are allowed.
It launches one owned probe, waits at most 15 seconds and closes its private job.
This verifies the launcher/desktop only; it does not approve a chat or pass E2E.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys

spec = importlib.util.spec_from_file_location("medium_smoke_v17", Path(__file__).with_name("Windows非提升进程v12.py"))
medium = importlib.util.module_from_spec(spec)
spec.loader.exec_module(medium)


def run(output: Path) -> None:
    if (sys.platform != "win32" or os.environ.get("GITHUB_ACTIONS") != "true"
        or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"
        or os.environ.get("GITHUB_REPOSITORY") != "Eswink/coding-tools-mcp"):
        raise RuntimeError("same-context probe requires this repository's disposable Windows runner")
    output.parent.mkdir(parents=True, exist_ok=True)
    evidence = {"passed": False, "source_sha": os.environ.get("GITHUB_SHA"),
        "launch_flags": medium.NATIVE_CREATION_FLAGS, "real_interactive_window_created": False,
        "scope": "owned medium-token Python and USER32 probe; not application acceptance"}
    process = None
    primary_failed = False
    try:
        process = medium.launch(Path(sys.executable), dict(os.environ),
            [str(Path(__file__).with_name("Windows桌面冒烟v15.py").resolve())])
        evidence["security"] = process.security
        medium.require_standard(process.security["child"])
        result = process.wait(15)
        evidence["exit_code"] = result
        evidence["exit_code_hex"] = f"0x{result & 0xffffffff:08x}"
        if result != 0:
            raise RuntimeError("owned same-context GUI probe exited: " + evidence["exit_code_hex"])
        evidence["real_interactive_window_created"] = True
        evidence["passed"] = True
    except BaseException as error:
        primary_failed = True
        evidence["failure_type"] = type(error).__name__
        raise
    finally:
        cleanup_error = None
        if process is not None:
            try:
                process.terminate_tree()
            except BaseException as error:
                cleanup_error = error
                evidence["passed"] = False
                evidence["cleanup_failure_type"] = type(error).__name__
        output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if cleanup_error is not None and not primary_failed:
            raise cleanup_error


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)
