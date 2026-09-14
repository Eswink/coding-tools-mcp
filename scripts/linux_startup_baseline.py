"""Observe exact released GUI bytes in a disposable, non-root X11 session.

No release writes, user configuration, credentials, or sandbox overrides. This is
an environment reproduction, not proof of the operator's unknown crash cause.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--expected-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--case', choices=['missing-bus', 'unlocked-keyring'], required=True)
    parser.add_argument('--kind', choices=['deb', 'appimage'], required=True)
    args = parser.parse_args()
    assert os.getuid() != 0, 'do not run GUI as root'
    assert os.environ.get('DISPLAY'), 'isolated Xvfb required'
    assert os.environ.get('DBUS_SESSION_BUS_ADDRESS'), 'isolated bus required'
    assert hashlib.sha256(args.package.read_bytes()).hexdigest() == args.expected_sha256
    app = args.app.resolve(strict=True)
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    # Do not pass CI tokens or arbitrary inherited environment into the GUI.
    env = {k: os.environ[k] for k in ['PATH', 'DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS',
           'HOME', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_STATE_HOME', 'XDG_CACHE_HOME',
           'XDG_RUNTIME_DIR'] if k in os.environ}
    env.update(LANG='C.UTF-8', LC_ALL='C.UTF-8', XDG_CURRENT_DESKTOP='GNOME', XDG_SESSION_TYPE='x11',
               RUST_BACKTRACE='1')
    assert Path(env['HOME'], '.linux-startup-disposable').is_file(), 'disposable home required'
    if args.case == 'missing-bus':
        env['DBUS_SESSION_BUS_ADDRESS'] = 'unix:path=' + str(Path(env['XDG_RUNTIME_DIR'], 'absent-bus'))
    else:
        # Fixture key only, never a real account's keyring or a production secret.
        subprocess.run(['gnome-keyring-daemon', '--unlock', '--components=secrets'],
                       input=b'linux-startup-test-only', env=env, check=True, timeout=20,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(['gdbus', 'call', '--session', '--dest', 'org.freedesktop.DBus', '--object-path',
                        '/org/freedesktop/DBus', '--method', 'org.freedesktop.DBus.GetNameOwner',
                        'org.freedesktop.secrets'], env=env, check=True, timeout=15,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if args.kind == 'appimage':
        env['APPIMAGE_EXTRACT_AND_RUN'] = '1'
    start = time.monotonic()
    # stderr is bounded on collection, and generated only under this synthetic home.
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen([str(app)], cwd=env['HOME'], env=env, start_new_session=True,
                                   stdout=stdout, stderr=stderr)
        observations = []; natural_returncode = None
        try:
            while time.monotonic() - start < 60:
                natural_returncode = process.poll()
                if natural_returncode is not None:
                    break
                tree = subprocess.run(['xwininfo', '-root', '-tree'], env=env, capture_output=True,
                                      text=True, timeout=5)
                observations.append('Coding Tools MCP' in tree.stdout)
                time.sleep(1)
        finally:
            was_alive = process.poll() is None
            try: os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError: pass
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=5)
            # Kill remaining processes only in the group we created, never by name.
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
        stderr.seek(0); error = stderr.read(65536).decode('utf-8', errors='replace')
        stdout.seek(0); out = stdout.read(8192).decode('utf-8', errors='replace')
    (output / 'stderr.txt').write_text(error, encoding='utf-8')
    (output / 'stdout.txt').write_text(out, encoding='utf-8')
    config = Path(env['XDG_CONFIG_HOME']) / 'coding-tools-mcp-desktop/data/profiles.json'
    result = {
        'case': args.case, 'kind': args.kind, 'package_sha256': args.expected_sha256,
        'product_source': '63261e0c9ae4b0c6befdbe5ae8caff7f5d32c076',
        'test_source': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID'),
        'os_release': Path('/etc/os-release').read_text(), 'uid': os.getuid(),
        'display': 'Xvfb X11; not operator desktop or Wayland',
        'renderer_overrides': [], 'appimage_mode': 'extract-and-run' if args.kind == 'appimage' else None,
        'elapsed_seconds': round(time.monotonic() - start, 3), 'natural_exit_code': natural_returncode,
        'alive_before_test_cleanup': was_alive, 'window_observed': any(observations),
        'last_window_observed': bool(observations and observations[-1]),
        'app_state_panic': 'failed to load app state' in error,
        'config_created': config.exists(),
        'scope': 'controlled environment reproduction; operator-machine cause remains unconfirmed',
    }
    expected = (not was_alive and result['app_state_panic']) if args.case == 'missing-bus' else (
        was_alive and result['last_window_observed'] and not result['app_state_panic'])
    result['expected_baseline_behavior_observed'] = expected
    (output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))
    if not expected:
        raise SystemExit('Baseline differs from hypothesis; inspect retained evidence, do not loosen assertion')


if __name__ == '__main__':
    main()
