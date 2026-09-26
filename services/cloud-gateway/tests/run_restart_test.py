#!/usr/bin/env python3
"""Start, restart and remove ONLY a fresh private PostgreSQL test cluster.

Requires PostgreSQL 16 binaries and the already-built restart_probe example.
Never accepts an existing cluster/DSN or touches system/production services.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile


def run(command, *, env, data=None):
    result = subprocess.run(command, env=env, input=data, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=45, check=False)
    if result.returncode:
        # Do not echo a credential-bearing stdin/stdout or a potentially sensitive error.
        raise RuntimeError(f"disposable test step {Path(command[0]).name} failed: {result.returncode}")
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pg-bin", type=Path, required=True)
    parser.add_argument("--probe", type=Path, required=True)
    args = parser.parse_args()
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        raise SystemExit("Run the disposable test as an unprivileged user, not root.")
    pg = args.pg_bin.resolve(strict=True)
    probe = args.probe.resolve(strict=True)
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        port = candidate.getsockname()[1]
    env = dict(os.environ)
    # Ignore any ambient remote/production connection choices.
    for key in list(env):
        if key.startswith("PG") or key in ("DATABASE_URL", "TEST_DATABASE_URL"):
            env.pop(key)
    with tempfile.TemporaryDirectory(prefix="ctm-restart-") as directory:
        root = Path(directory)
        cluster = root / "db"
        run([str(pg / "initdb"), "-D", str(cluster), "-A", "trust", "-U", "gateway_test",
             "--encoding=UTF8", "--no-locale"], env=env)
        start = [str(pg / "pg_ctl"), "-D", str(cluster), "-l", str(root / "postgres.log"),
                 "-o", f"-h 127.0.0.1 -p {port} -k {root}", "-w", "start"]
        stop = [str(pg / "pg_ctl"), "-D", str(cluster), "-m", "fast", "-w", "stop"]
        started = False
        try:
            run(start, env=env)
            started = True
            run([str(pg / "createdb"), "-h", "127.0.0.1", "-p", str(port), "-U", "gateway_test",
                 "coding_tools_identity_test"], env=env)
            child_env = dict(env, TEST_DATABASE_URL=f"postgresql://gateway_test@127.0.0.1:{port}/coding_tools_identity_test",
                             CTM_DISPOSABLE_TEST_PROBE="1")
            private_state = run([str(probe), "seed"], env=child_env)
            assert len(private_state) <= 4096
            run(stop, env=env)
            started = False
            run(start, env=env)
            started = True
            result = json.loads(run([str(probe), "verify"], env=child_env, data=private_state))
            del private_state
            assert result == {"restart_refresh": "PASS", "agent_connected": False}
            print(json.dumps({"test": "independent_process_and_postgres_restart", "result": "PASS",
                              "production_services_touched": False, "agent_required": False}))
        finally:
            if started:
                run(stop, env=env)


if __name__ == "__main__":
    main()
