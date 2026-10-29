#!/usr/bin/env python3
"""Run scan fault injection against owned, disposable real D-Bus/keyring processes.

No existing desktop service or credential is touched. The fixture intentionally
has no D-Bus activation directories, so disconnect cannot silently auto-restart
the service. Child tests rendezvous using bounded, non-secret marker files.
"""
import os
from pathlib import Path
import re
import select
import subprocess
import sys
import tempfile
import time


def stop(child):
    if child is not None and child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=10)


def call(env, method, *args):
    return subprocess.check_output(
        ["gdbus", "call", "--session", "--dest", "org.freedesktop.secrets",
         "--object-path", "/org/freedesktop/secrets", "--method", method, *args],
        env=env, stderr=subprocess.DEVNULL, text=True, timeout=5,
    )


def start_keyring(env, log):
    child = subprocess.Popen(
        ["gnome-keyring-daemon", "--foreground", "--unlock", "--components=secrets"],
        stdin=subprocess.PIPE, stdout=log, stderr=log, env=env,
    )
    child.stdin.write(b"disposable-scan-fixture-only")
    child.stdin.close()
    until = time.monotonic() + 15
    while time.monotonic() < until:
        if child.poll() is not None:
            raise RuntimeError("fixture keyring daemon exited during startup")
        try:
            result = call(env, "org.freedesktop.Secret.Service.ReadAlias", "default")
            match = re.search(r"'(/org/freedesktop/secrets/collection/[^']+)'", result)
            if match:
                return child, match.group(1)
        except (subprocess.SubprocessError, OSError):
            pass
        time.sleep(0.05)
    stop(child)
    raise RuntimeError("fixture Secret Service did not become ready")


def main(command):
    if not command:
        raise SystemExit("usage: native_scan_keyring_fixture.py COMMAND [ARGS...]")
    daemon = keyring = test = None
    with tempfile.TemporaryDirectory(prefix="native-scan-fault-") as temporary:
        root = Path(temporary)
        env = os.environ.copy()
        env.setdefault("CARGO_HOME", str(Path.home() / ".cargo"))
        env.setdefault("RUSTUP_HOME", str(Path.home() / ".rustup"))
        # Never inherit a real desktop control socket or bus address.
        for name in ("DBUS_SESSION_BUS_ADDRESS", "GNOME_KEYRING_CONTROL", "SSH_AUTH_SOCK"):
            env.pop(name, None)
        for name, directory in (("HOME", "home"), ("XDG_RUNTIME_DIR", "runtime"),
                                ("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"),
                                ("XDG_CACHE_HOME", "cache"), ("XDG_STATE_HOME", "state")):
            path = root / directory
            path.mkdir(mode=0o700)
            env[name] = str(path)
        env["CTM_NATIVE_SCAN_FIXTURE"] = str(root)
        config = root / "bus.conf"
        config.write_text(f'''<busconfig>
<type>session</type><listen>unix:tmpdir={root / "runtime"}</listen><auth>EXTERNAL</auth>
<policy context="default"><allow send_destination="*"/><allow receive_sender="*"/><allow own="*"/></policy>
</busconfig>''', encoding="utf-8")
        with (root / "daemon.log").open("wb") as log:
            try:
                daemon = subprocess.Popen(
                    ["dbus-daemon", "--nofork", "--config-file", str(config), "--print-address=1"],
                    stdout=subprocess.PIPE, stderr=log, text=True, env=env,
                )
                if not select.select([daemon.stdout], [], [], 10)[0]:
                    raise RuntimeError("fixture D-Bus startup timed out")
                address = daemon.stdout.readline().strip()
                if not address.startswith("unix:"):
                    raise RuntimeError("fixture D-Bus did not return a private socket")
                env["DBUS_SESSION_BUS_ADDRESS"] = address
                keyring, collection = start_keyring(env, log)
                test = subprocess.Popen(command, env=env)
                for stage in ("lock", "disconnect", "restart", "bus-disconnect"):
                    until = time.monotonic() + 30
                    while not (root / f"ready-{stage}").exists():
                        if test.poll() is not None:
                            raise RuntimeError(f"native test exited before {stage}: {test.returncode}")
                        if time.monotonic() > until:
                            raise RuntimeError(f"native test rendezvous timed out: {stage}")
                        time.sleep(0.01)
                    if stage == "lock":
                        call(env, "org.freedesktop.Secret.Service.Lock", f"[objectpath '{collection}']")
                    elif stage == "disconnect":
                        stop(keyring)
                        keyring = None
                    elif stage == "restart":
                        keyring, _ = start_keyring(env, log)
                    else:
                        stop(daemon)
                        daemon = None
                    (root / f"go-{stage}").write_text("go", encoding="utf-8")
                result = test.wait(timeout=30)
                if result:
                    raise RuntimeError(f"native fault test failed: {result}")
                print("PASS: isolated real Secret Service lock, duplicate, disconnect, restart and bus loss")
            finally:
                stop(test)
                stop(keyring)
                stop(daemon)


if __name__ == "__main__":
    main(sys.argv[1:])
