"""Verify the source-built Linux GUI degrades safely when desktop services are unavailable.

The fixture owns its HOME, D-Bus and keyring. It never touches operator credentials,
never disables a sandbox, and never treats Xvfb as a real Wayland desktop.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import tempfile
import time


def start_keyring(env: dict[str, str], output: Path) -> None:
    with (output / 'fixture-keyring.txt').open('wb') as log:
        subprocess.run(['gnome-keyring-daemon', '--unlock', '--components=secrets'],
                       input=b'linux-startup-test-only', env=env, check=True, timeout=20,
                       stdout=log, stderr=log)
        subprocess.run(['gnome-keyring-daemon', '--start', '--components=secrets'],
                       env=env, check=True, timeout=20, stdout=log, stderr=log)
        subprocess.run(['gdbus', 'call', '--session', '--dest', 'org.freedesktop.secrets',
                        '--object-path', '/org/freedesktop/secrets', '--method',
                        'org.freedesktop.DBus.Peer.Ping'], env=env, check=True, timeout=20,
                       stdout=log, stderr=log)



def name_has_owner(env: dict[str, str]) -> bool:
    result = subprocess.run(
        ['gdbus', 'call', '--session', '--dest', 'org.freedesktop.DBus',
         '--object-path', '/org/freedesktop/DBus', '--method',
         'org.freedesktop.DBus.NameHasOwner', 'org.freedesktop.secrets'],
        env=env, check=True, timeout=10, capture_output=True, text=True,
    )
    return result.stdout.strip() == '(true,)'


def start_runtime_user_bus(env: dict[str, str], output: Path) -> tuple[subprocess.Popen[str], str]:
    bus_path = Path(env['XDG_RUNTIME_DIR']) / 'bus'
    if bus_path.exists():
        raise RuntimeError('split-session fixture requires an unused runtime-user bus socket')
    log = (output / 'split-runtime-bus.txt').open('w', encoding='utf-8')
    process = subprocess.Popen(
        ['dbus-daemon', '--session', '--nofork', f'--address=unix:path={bus_path}',
         '--print-address=1'],
        env=env, stdout=subprocess.PIPE, stderr=log, text=True, start_new_session=True,
    )
    log.close()
    assert process.stdout is not None
    readable, _, _ = select.select([process.stdout], [], [], 5)
    if not readable:
        process.terminate()
        process.wait(timeout=5)
        raise RuntimeError('runtime-user fixture bus did not publish its address')
    announced = process.stdout.readline().strip()
    if not announced.startswith('unix:path='):
        process.terminate()
        process.wait(timeout=5)
        raise RuntimeError('runtime-user fixture bus returned an unexpected address form')
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not bus_path.is_socket():
        if process.poll() is not None:
            raise RuntimeError('runtime-user fixture bus exited before creating its socket')
        time.sleep(0.05)
    if not bus_path.is_socket():
        process.terminate()
        process.wait(timeout=5)
        raise RuntimeError('runtime-user fixture bus socket was not created')
    # The product intentionally reconstructs exactly this canonical address from
    # XDG_RUNTIME_DIR; the daemon's optional guid is not required for connection.
    return process, f'unix:path={bus_path}'


def stop_fixture_process(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--case', choices=['missing-bus', 'unlocked-keyring', 'split-session-bus', 'safe-mode', 'diagnose-startup', 'diagnose-no-bus'], required=True)
    parser.add_argument('--seconds', type=int, default=30)
    args = parser.parse_args()
    assert os.getuid() != 0, 'startup test must run as the ordinary runner user'
    if args.case not in ('diagnose-startup', 'diagnose-no-bus'):
        assert os.environ.get('DISPLAY'), 'isolated Xvfb required'
    assert os.environ.get('DBUS_SESSION_BUS_ADDRESS'), 'isolated session bus required'
    app = args.app.resolve(strict=True)
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    env = {key: os.environ[key] for key in [
        'PATH', 'DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS', 'HOME',
        'XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_STATE_HOME', 'XDG_CACHE_HOME',
        'XDG_RUNTIME_DIR'] if key in os.environ}
    env.update(LANG='C.UTF-8', LC_ALL='C.UTF-8', XDG_CURRENT_DESKTOP='GNOME',
               XDG_SESSION_TYPE='x11', RUST_BACKTRACE='1')
    if args.case in ('diagnose-startup', 'diagnose-no-bus'):
        env.pop('DISPLAY', None)
        env.pop('WAYLAND_DISPLAY', None)
    assert Path(env['HOME'], '.linux-startup-disposable').is_file(), 'disposable home required'
    runtime_bus_process: subprocess.Popen[str] | None = None
    split_fixture = None
    if args.case == 'missing-bus':
        env['DBUS_SESSION_BUS_ADDRESS'] = 'unix:path=' + str(Path(env['XDG_RUNTIME_DIR'], 'absent-bus'))
    elif args.case == 'diagnose-no-bus':
        env.pop('DBUS_SESSION_BUS_ADDRESS', None)
    elif args.case == 'split-session-bus':
        inherited_address = env['DBUS_SESSION_BUS_ADDRESS']
        runtime_bus_process, runtime_address = start_runtime_user_bus(env, output)
        runtime_env = env.copy()
        runtime_env['DBUS_SESSION_BUS_ADDRESS'] = runtime_address
        start_keyring(runtime_env, output)
        inherited_owned = name_has_owner(env)
        runtime_owned = name_has_owner(runtime_env)
        if inherited_address == runtime_address or inherited_owned or not runtime_owned:
            stop_fixture_process(runtime_bus_process)
            raise RuntimeError('split-session fixture did not establish isolated bus ownership')
        split_fixture = {
            'inherited_secret_service_owned': inherited_owned,
            'runtime_user_bus_secret_service_owned': runtime_owned,
            'addresses_differ': inherited_address != runtime_address,
        }
        (output / 'split-fixture.json').write_text(
            json.dumps(split_fixture, indent=2) + '\n', encoding='utf-8')
    else:
        start_keyring(env, output)

    app_command = [str(app)]
    if args.case == 'safe-mode':
        app_command.append('--safe-mode')
    elif args.case in ('diagnose-startup', 'diagnose-no-bus'):
        app_command.append('--diagnose-startup')

    start = time.monotonic()
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(app_command, cwd=env['HOME'], env=env, start_new_session=True,
                                   stdout=stdout, stderr=stderr)
        observations: list[bool] = []
        natural_returncode = None
        try:
            while time.monotonic() - start < args.seconds:
                natural_returncode = process.poll()
                if natural_returncode is not None:
                    break
                if args.case not in ('diagnose-startup', 'diagnose-no-bus'):
                    tree = subprocess.run(['xwininfo', '-root', '-tree'], env=env, capture_output=True,
                                          text=True, timeout=5)
                    observations.append('Coding Tools MCP' in tree.stdout)
                time.sleep(0.25 if args.case in ('diagnose-startup', 'diagnose-no-bus') else 1)
        finally:
            was_alive = process.poll() is None
            try: os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError: pass
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=5)
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
        stderr.seek(0); error = stderr.read(65536).decode('utf-8', errors='replace')
        stdout.seek(0); out = stdout.read(8192).decode('utf-8', errors='replace')

    stop_fixture_process(runtime_bus_process)
    (output / 'stderr.txt').write_text(error, encoding='utf-8')
    (output / 'stdout.txt').write_text(out, encoding='utf-8')
    config = Path(env['XDG_CONFIG_HOME']) / 'coding-tools-mcp-desktop/data/profiles.json'
    bootstrap = Path(env['XDG_STATE_HOME']) / 'coding-tools-mcp/bootstrap.log'
    bootstrap_text = bootstrap.read_text(encoding='utf-8') if bootstrap.is_file() else ''
    (output / 'bootstrap.log').write_text(bootstrap_text, encoding='utf-8')
    phases = [line.removeprefix('phase=') for line in bootstrap_text.splitlines() if line.startswith('phase=')]
    startup_diagnostics = None
    for line in out.splitlines():
        if line.startswith('startup-diagnostics='):
            startup_diagnostics = json.loads(line.removeprefix('startup-diagnostics='))
            break

    common = was_alive and bool(observations and observations[-1]) and 'panic' not in phases \
        and 'setup-complete' in phases and 'failed to load app state' not in error
    if args.case == 'missing-bus':
        expected = common and not config.exists() and 'app-state-locked' in phases \
            and 'background-deferred' in phases and 'background-ready' not in phases
    elif args.case in ('unlocked-keyring', 'split-session-bus'):
        expected = common and config.exists() and 'app-state-ready' in phases \
            and 'background-ready' in phases
    elif args.case == 'safe-mode':
        expected = common and config.exists() and 'app-state-ready' in phases \
            and 'tray-skipped-safe-mode' in phases and 'background-skipped-safe-mode' in phases \
            and 'tray-ready' not in phases and 'background-ready' not in phases \
            and startup_diagnostics is None
    else:
        expected_bus = args.case == 'diagnose-startup'
        expected_store = 'available' if expected_bus else 'session_bus_missing'
        expected = natural_returncode == 0 and not was_alive and not observations and not config.exists() \
            and 'panic' not in phases and 'app-state-ready' not in phases \
            and 'app-state-locked' not in phases and 'diagnostics-complete' in phases \
            and 'tauri-setup' not in phases and 'setup-complete' not in phases \
            and isinstance(startup_diagnostics, dict) \
            and startup_diagnostics.get('safeMode') is True \
            and startup_diagnostics.get('diagnoseStartup') is True \
            and startup_diagnostics.get('trayAvailable') is False \
            and startup_diagnostics.get('notificationPluginEnabled') is False \
            and startup_diagnostics.get('sessionBusConfigured') is expected_bus \
            and startup_diagnostics.get('displayBackend') == 'headless' \
            and startup_diagnostics.get('credentialStoreState') == expected_store \
            and startup_diagnostics.get('startupFailureReason') is None \
            and startup_diagnostics.get('configurationState') == 'not_loaded'
    result = {
        'case': args.case,
        'source': os.environ.get('GITHUB_SHA'),
        'run_id': os.environ.get('GITHUB_RUN_ID'),
        'uid': os.getuid(),
        'display': 'headless CLI diagnostic' if args.case in ('diagnose-startup', 'diagnose-no-bus') else 'Xvfb X11; not operator desktop or Wayland',
        'elapsed_seconds': round(time.monotonic() - start, 3),
        'natural_exit_code': natural_returncode,
        'alive_before_test_cleanup': was_alive,
        'window_observed': any(observations),
        'last_window_observed': bool(observations and observations[-1]),
        'config_created': config.exists(),
        'bootstrap_phases': phases,
        'app_state_panic': 'failed to load app state' in error,
        'startup_diagnostics': startup_diagnostics,
        'split_session_fixture': split_fixture,
        'expected_candidate_behavior_observed': expected,
    }
    (output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))
    if not expected:
        raise SystemExit('Candidate startup contract failed; inspect evidence, do not loosen assertion')


if __name__ == '__main__':
    main()
