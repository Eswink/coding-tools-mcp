"""Launch only the exact fixture application with valid stdout/stderr handles."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def run(executable: Path, log: Path, result: Path) -> int:
    if sys.platform != "win32" or os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted" or os.environ.get("GITHUB_REPOSITORY") != "Eswink/coding-tools-mcp":
        raise RuntimeError("Windows hosted fixture only")
    executable = executable.resolve(strict=True)
    # Parent launcher already verified this wrapper's real medium token and
    # assigned it to a private kill-on-close job. The app inherits both.
    with log.open("wb") as stream:
        child = subprocess.Popen([str(executable)], cwd=executable.parent,
                                 stdout=stream, stderr=subprocess.STDOUT,
                                 stdin=subprocess.DEVNULL, close_fds=True)
        returncode = child.wait()
    proof = {"pid": child.pid, "exit_code": returncode,
             "exit_code_hex": f"0x{returncode & 0xffffffff:08x}", "stdio_redirected": True}
    result.write_text(json.dumps(proof, indent=2), encoding="utf-8")
    return returncode


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.executable, args.log, args.result))
