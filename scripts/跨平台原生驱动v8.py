"""Native WebView2 adapter; never substitutes browser mocks or permission IPC."""
from __future__ import annotations
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import time

spec = importlib.util.spec_from_file_location("ubuntu_native_driver_v8", Path(__file__).with_name("Ubuntu原生验收v1.py"))
gui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gui)


def windows_capabilities(debug_port: int) -> dict:
    # Microsoft WebView2 attach mode: never ask EdgeDriver to launch another app.
    if type(debug_port) is not int or not 1 <= debug_port <= 65535:
        raise ValueError("invalid loopback debugging port")
    return {"capabilities": {"alwaysMatch": {"browserName": "webview2",
        "ms:edgeOptions": {"debuggerAddress": f"127.0.0.1:{debug_port}"}}}}


def webview_environment(debug_port: int) -> dict:
    windows_capabilities(debug_port)  # Validate before constructing arguments.
    env = os.environ.copy()
    # Per-child only; do not change the registry, global environment or sandbox.
    env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = (
        f"--remote-debugging-port={debug_port} --remote-debugging-address=127.0.0.1")
    return env


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


class WindowsNativeSession(gui.NativeSession):
    def __init__(self, executable: Path, driver: Path, output: Path, attempt: int):
        self.session = ""
        self.process = None
        self.app_process = None
        self.executable, self.driver = executable, driver
        self.log = (output / f"Windows原生驱动v8-{attempt}.log").open("wb")
        number, debug_port = gui.port(), gui.port()
        while debug_port == number:
            debug_port = gui.port()
        self.base = f"http://127.0.0.1:{number}"
        self.debug_base = f"http://127.0.0.1:{debug_port}"
        try:
            self.app_process = subprocess.Popen([str(executable)],
                env=webview_environment(debug_port), stdout=self.log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            gui.wait_for(lambda: self.debug_status(), timeout=60)
            self.process = subprocess.Popen([str(driver), f"--port={number}", "--allowed-ips=127.0.0.1"],
                stdout=self.log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            gui.wait_for(lambda: gui.request(self.base + "/status", timeout=3), timeout=15)
            result = gui.request(self.base + "/session", windows_capabilities(debug_port), timeout=90)
            self.session = result["value"]["sessionId"]
            self.call("timeouts", {"script": 30000, "pageLoad": 60000, "implicit": 0})
            gui.wait_for(lambda: self.execute("return !!window.__TAURI_INTERNALS__?.invoke"))
        except BaseException:
            self.close()
            raise

    def debug_status(self):
        if self.app_process.poll() is not None:
            raise RuntimeError("native application exited before WebView2 became ready")
        value = gui.request(self.debug_base + "/json/version", timeout=3)
        if not isinstance(value, dict) or not value.get("webSocketDebuggerUrl"):
            raise RuntimeError("native WebView2 debugging endpoint is not ready")
        return value

    def stop_owned_process(self, process):
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


def session(executable: Path, driver: Path, output: Path, attempt: int):
    factory = WindowsNativeSession if sys.platform == "win32" else gui.NativeSession
    return factory(executable, driver, output, attempt)
