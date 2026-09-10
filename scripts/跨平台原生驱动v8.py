"""Native WebView2 adapter; never substitutes browser mocks or permission IPC."""
from __future__ import annotations
import importlib.util
import json
import re
import math
import os
from pathlib import Path
import subprocess
import shutil
import tempfile
import sys
import time
import urllib.error

spec = importlib.util.spec_from_file_location("ubuntu_native_driver_v8", Path(__file__).with_name("Ubuntu原生验收v1.py"))
gui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gui)
medium_spec = importlib.util.spec_from_file_location("medium_native_v12", Path(__file__).with_name("Windows非提升进程v12.py"))
medium = importlib.util.module_from_spec(medium_spec)
medium_spec.loader.exec_module(medium)


def windows_capabilities(debug_port: int) -> dict:
    # Microsoft WebView2 attach mode: never ask EdgeDriver to launch another app.
    if type(debug_port) is not int or not 1 <= debug_port <= 65535:
        raise ValueError("invalid loopback debugging port")
    return {"capabilities": {"alwaysMatch": {"browserName": "webview2",
        "ms:edgeOptions": {"debuggerAddress": f"127.0.0.1:{debug_port}"}}}}


def webview_environment(debug_port: int, user_data: Path) -> dict:
    windows_capabilities(debug_port)  # Validate before constructing arguments.
    if not user_data.is_absolute():
        raise ValueError("browser fixture path must be absolute")
    if any(char in str(user_data) for char in ('"', "\r", "\n", "\0")):
        raise ValueError("invalid browser fixture path")
    env = os.environ.copy()
    # Per-child only; do not change the registry, global environment or sandbox.
    env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = (
        f'--remote-debugging-port={debug_port} --enable-logging --v=1 '
        f'--log-file="{user_data / "浏览器启动v20.log"}"')
    env["WEBVIEW2_USER_DATA_FOLDER"] = str(user_data)
    return env



def collect_startup_log(profile: Path | None, output: Path) -> None:
    """Capture bounded startup errors ONLY before a WebDriver session exists.

    Raw browser logs stay in the disposable profile and are deleted with it.
    No network log, registry dump, account credentials or OAuth traffic is saved.
    """
    path = profile / "浏览器启动v20.log" if profile else None
    record = {"phase": "before_oauth", "file_found": False, "truncated": False, "messages": []}
    if path is not None and path.is_file():
        with path.open("rb") as stream:
            raw = stream.read(128 * 1024 + 1)
        record["file_found"] = True
        record["truncated"] = len(raw) > 128 * 1024
        for line in raw[:128 * 1024].decode("utf-8", errors="replace").splitlines():
            if not re.search(r"(?:ERROR|FATAL|WARNING|sandbox|[Pp]ermission|[Aa]ccess.denied)", line):
                continue
            line = re.sub(r"(?i)(?:https?|wss?)://[^\s]+", "<url>", line)
            line = re.sub(r"(?i)(?:[a-z]:\\)[^\r\n]*", "<local-path>", line)
            line = re.sub(r"(?i)(token|password|authorization|secret|cookie)\s*[:=]\s*[^\s,;]+", r"\1=<redacted>", line)
            record["messages"].append(line[:1200])
            if len(record["messages"]) == 40:
                record["truncated"] = True
                break
    output.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

def native_process_snapshot(root_pid: int) -> dict:
    if type(root_pid) is not int or root_pid <= 0:
        raise ValueError("invalid owned process id")
    # Only this Popen process and descendants are returned. No full environment,
    # command line, unrelated processes, registry values or browser data is logged.
    script = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$rows = @(Get-CimInstance Win32_Process)
$ids = [System.Collections.Generic.HashSet[int]]::new()
$null = $ids.Add(__ROOT_PID__)
for ($i = 0; $i -lt 8; $i++) {
    foreach ($row in $rows) {
        if ($ids.Contains([int]$row.ParentProcessId)) { $null = $ids.Add([int]$row.ProcessId) }
    }
}
if ($ids.Count -gt 128) { throw 'unexpected owned process count' }
$owned = @($rows | Where-Object { $ids.Contains([int]$_.ProcessId) } | ForEach-Object {
    [ordered]@{ id=[int]$_.ProcessId; parent=[int]$_.ParentProcessId; name=$_.Name;
        debug_flags=@([regex]::Matches($_.CommandLine, '--remote-debugging-[^\s"]+') | ForEach-Object { $_.Value });
        user_data_flag_present=($_.CommandLine -match '--user-data-dir=') }
})
$listeners = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $ids.Contains([int]$_.OwningProcess) } | ForEach-Object {
    [ordered]@{ address=$_.LocalAddress; port=[int]$_.LocalPort; process=[int]$_.OwningProcess }
})
[ordered]@{root=__ROOT_PID__; processes=$owned; listeners=$listeners} | ConvertTo-Json -Depth 6 -Compress
""".replace("__ROOT_PID__", str(root_pid))
    result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, encoding="utf-8", check=True, timeout=20,
        creationflags=subprocess.CREATE_NO_WINDOW)
    return json.loads(result.stdout)


def verify_debug_listener(snapshot: dict, debug_port: int) -> None:
    rows = snapshot.get("listeners", [])
    own = {p["id"] for p in snapshot.get("processes", [])}
    selected = [row for row in rows if row.get("port") == debug_port]
    if not selected or any(row.get("address") not in ("127.0.0.1", "::1") or row.get("process") not in own for row in selected):
        raise ValueError("native debug listener must belong to this app and bind loopback only")


def fixture_root(args) -> Path:
    if sys.platform == "win32":
        flags = os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "")
        if "--no-sandbox" in flags or "--disable-setuid-sandbox" in flags:
            raise RuntimeError("sandbox bypass prohibited")
        if (os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"
            or os.environ.get("GITHUB_REPOSITORY") != "Eswink/coding-tools-mcp"):
            raise RuntimeError("Windows native acceptance requires a disposable hosted runner")
        temporary = Path(os.environ["RUNNER_TEMP"]).resolve()
        root = Path(args.fixture_root).resolve() if getattr(args, "fixture_root", None) else None
        if root is None or root == temporary or temporary not in root.parents:
            raise RuntimeError("fixture root must be below RUNNER_TEMP")
        if not (root / ".chat-native-fixture-v8").is_file():
            raise RuntimeError("refusing non-fixture Windows profile")
        return root
    if sys.platform != "linux" or os.geteuid() == 0 or not os.environ.get("DISPLAY") or not os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
        raise RuntimeError("isolated ordinary-user Linux GUI required")
    if os.environ.get("WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS"):
        raise RuntimeError("sandbox bypass prohibited")
    root = Path.home()
    if not (root / ".ubuntu-ci-fixture-v1").is_file():
        raise RuntimeError("refusing non-fixture Linux profile")
    return root


class NativeHostExited(RuntimeError):
    """The owned Python wrapper exited; this does not establish a product crash."""
    def __init__(self, exit_code: int):
        self.exit_code = exit_code
        super().__init__(f"owned Python host exited before WebView2 became ready: "
                         f"code={exit_code}, hex=0x{exit_code & 0xffffffff:08x}")


class WindowsNativeSession(gui.NativeSession):
    def __init__(self, executable: Path, driver: Path, output: Path, attempt: int):
        self.session = ""
        self.process = None
        self.app_process = None
        self.browser_profile = None
        self.executable, self.driver = executable, driver
        self.log = (output / f"Windows原生驱动v8-{attempt}.log").open("wb")
        number, debug_port = gui.port(), gui.port()
        while debug_port == number:
            debug_port = gui.port()
        self.base = f"http://127.0.0.1:{number}"
        self.debug_base = f"http://127.0.0.1:{debug_port}"
        try:
            self.browser_profile = Path(tempfile.mkdtemp(prefix="chat-webview-v10-", dir=os.environ["RUNNER_TEMP"]))
            self.app_process = medium.launch(Path(sys.executable), webview_environment(debug_port, self.browser_profile), [
                str(Path(__file__).with_name("Windows原生宿主v13.py").resolve()),
                "--executable", str(executable),
                "--log", str((output / f"Windows应用输出v13-{attempt}.log").resolve()),
                "--result", str((output / f"Windows应用退出v13-{attempt}.json").resolve())])
            (output / f"Windows权限级别v12-{attempt}.json").write_text(
                json.dumps(self.app_process.security, indent=2), encoding="utf-8")
            self.wait_for_debug(timeout=60)
            startup = native_process_snapshot(self.app_process.pid)
            verify_debug_listener(startup, debug_port)
            (output / f"Windows启动诊断v10-{attempt}.json").write_text(
                json.dumps(startup, indent=2), encoding="utf-8")
            self.process = subprocess.Popen([str(driver), f"--port={number}", "--allowed-ips=127.0.0.1"],
                stdout=self.log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            gui.wait_for(lambda: gui.request(self.base + "/status", timeout=3), timeout=15)
            result = gui.request(self.base + "/session", windows_capabilities(debug_port), timeout=90)
            self.session = result["value"]["sessionId"]
            self.call("timeouts", {"script": 30000, "pageLoad": 60000, "implicit": 0})
            gui.wait_for(lambda: self.execute("return !!window.__TAURI_INTERNALS__?.invoke"))
        except BaseException:
            if not self.session:
                try:
                    collect_startup_log(self.browser_profile, output / f"Windows浏览器启动v20-{attempt}.json")
                except (OSError, ValueError):
                    pass  # Diagnostics never replaces the original failure.
            if self.app_process and self.app_process.poll() is None:
                try:
                    snapshot = native_process_snapshot(self.app_process.pid)
                    (output / f"Windows启动诊断v10-{attempt}.json").write_text(
                        json.dumps(snapshot, indent=2), encoding="utf-8")
                except (OSError, ValueError, subprocess.SubprocessError):
                    pass  # Diagnostics never replaces the original test failure.
            try:
                self.close()
            except (OSError, RuntimeError, subprocess.SubprocessError) as cleanup_error:
                print(f"native cleanup also failed: {type(cleanup_error).__name__}", file=sys.stderr)
            raise

    def wait_for_debug(self, timeout=60):
        """Retry only read-only connection readiness, never a known process exit."""
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 300:
            raise ValueError("native startup budget must be finite and within 300 seconds")
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("owned native host did not expose its loopback WebView2 endpoint")
            try:
                return self.debug_status(timeout=min(3, remaining))
            except (ConnectionError, TimeoutError, urllib.error.URLError):
                # Process-exit and protocol errors remain fatal. No app/tool replay.
                time.sleep(min(0.25, max(0, deadline - time.monotonic())))

    def debug_status(self, timeout=3):
        exit_code = self.app_process.poll()
        if exit_code is not None:
            raise NativeHostExited(exit_code)
        value = gui.request(self.debug_base + "/json/version", timeout=timeout)
        if not isinstance(value, dict) or not value.get("webSocketDebuggerUrl"):
            raise RuntimeError("native WebView2 debugging endpoint is not ready")
        return value

    def stop_owned_process(self, process):
        if isinstance(process, medium.OwnedProcess):
            process.terminate_tree()
            return
        if process and process.poll() is None:
            # Popen handles created by this adapter only; never a name-wide kill.
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=self.log, stderr=subprocess.STDOUT, timeout=15, check=False)
            process.wait(timeout=10)

    def close(self):
        if self.log.closed:
            return
        try:
            if self.session and self.process and self.process.poll() is None:
                try:
                    self.execute("setTimeout(()=>window.__TAURI_INTERNALS__.invoke('quit_app'),50);return true")
                    time.sleep(0.4)
                except (OSError, RuntimeError):
                    pass
                try:
                    gui.request(f"{self.base}/session/{self.session}", method="DELETE", timeout=5)
                except (OSError, RuntimeError):
                    pass
        finally:
            self.session = ""
            try:
                self.stop_owned_process(self.app_process)
            finally:
                try:
                    self.stop_owned_process(self.process)
                finally:
                    self.log.close()
                    if self.browser_profile is not None:
                        deadline = time.monotonic() + 10
                        while True:
                            try:
                                shutil.rmtree(self.browser_profile)
                                break
                            except PermissionError:
                                if time.monotonic() >= deadline: raise
                                time.sleep(0.25)
                        self.browser_profile = None


def session(executable: Path, driver: Path, output: Path, attempt: int):
    factory = WindowsNativeSession if sys.platform == "win32" else gui.NativeSession
    return factory(executable, driver, output, attempt)
