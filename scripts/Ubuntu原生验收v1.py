"""Exercise an installed Tauri GUI through native WebKit WebDriver and real IPC/HTTP.

Run under an isolated ordinary-user HOME, D-Bus/Secret Service and Xvfb session.
No browser mocks, injected Tauri plugin, sandbox bypass, or public tunnel is used.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request

VERSION = "0.2.5"
HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def request(url: str, data: dict | None = None, method: str | None = None, timeout: int = 60) -> dict:
    raw = None if data is None else json.dumps(data, ensure_ascii=False).encode()
    req = urllib.request.Request(url, data=raw, method=method,
                                 headers={"Content-Type": "application/json", "Accept": "application/json"})
    try:
        with HTTP.open(req, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}: {exc.read(4096).decode(errors='replace')}") from exc


def wait_for(operation, predicate=bool, timeout: int = 30):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            last = operation()
            if predicate(last):
                return last
        except (OSError, RuntimeError) as exc:
            last = str(exc)
        time.sleep(0.25)
    raise AssertionError(f"condition not met within {timeout}s: {str(last)[:1500]}")


def port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class NativeSession:
    def __init__(self, executable: Path, driver: Path, output: Path, attempt: int):
        self.session = ""
        self.process = None
        self.log = (output / f"原生驱动v1-{attempt}.log").open("wb")
        number, native = port(), port()
        while native == number:
            native = port()
        self.base = f"http://127.0.0.1:{number}"
        self.executable, self.driver = executable, driver
        try:
            self.process = subprocess.Popen([str(driver), "--port", str(number), "--native-port", str(native),
                                             "--native-host", "127.0.0.1"], stdout=self.log, stderr=subprocess.STDOUT,
                                            start_new_session=True)
            wait_for(lambda: request(self.base + "/status", timeout=3), timeout=15)
            result = request(self.base + "/session", {"capabilities": {"alwaysMatch": {
                "browserName": "wry", "tauri:options": {"application": str(executable)}}}}, timeout=90)
            self.session = result["value"]["sessionId"]
            self.call("timeouts", {"script": 30000, "pageLoad": 60000, "implicit": 0})
            wait_for(lambda: self.execute("return !!window.__TAURI_INTERNALS__?.invoke"))
        except BaseException:
            self.close()
            raise

    def call(self, path: str, data: dict | None = None, method: str | None = None):
        result = request(f"{self.base}/session/{self.session}/{path}", data, method)
        value = result.get("value")
        if isinstance(value, dict) and value.get("error"):
            raise RuntimeError(str(value))
        return value

    def execute(self, script: str, *args):
        return self.call("execute/sync", {"script": script, "args": list(args)})

    def invoke(self, command: str, arguments: dict | None = None):
        value = self.call("execute/async", {"script": """
            const done=arguments[arguments.length-1];
            window.__TAURI_INTERNALS__.invoke(arguments[0],arguments[1])
              .then(value=>done({ok:true,value}),error=>done({ok:false,error:String(error)}));
        """, "args": [command, arguments or {}]})
        if not value or not value["ok"]:
            raise RuntimeError(f"real IPC {command}: {value}")
        return value.get("value")

    def body(self) -> str:
        return self.execute("return document.body.innerText")

    def click_text(self, text: str) -> None:
        # Native WebDriver click; do not substitute a browser mock or rewrite UI state.
        element = wait_for(lambda: self.call("element", {"using": "xpath", "value":
            f"//button[normalize-space(.)='{text}']"}))
        element_id = element["element-6066-11e4-a52e-4f735466cecf"]
        self.call(f"element/{element_id}/click", {})

    def screenshot(self, path: Path) -> None:
        raw = base64.b64decode(self.call("screenshot"), validate=True)
        if not raw.startswith(b"\x89PNG\r\n\x1a\n") or len(raw) < 5000:
            raise AssertionError("native screenshot is missing or invalid")
        path.write_bytes(raw)

    def close(self) -> None:
        try:
            if self.session and self.process and self.process.poll() is None:
                try:
                    self.execute("setTimeout(()=>window.__TAURI_INTERNALS__.invoke('quit_app'),50);return true")
                    time.sleep(0.4)
                except (OSError, RuntimeError):
                    pass  # A closed native window may already have ended the session.
                try:
                    request(f"{self.base}/session/{self.session}", method="DELETE", timeout=5)
                except (OSError, RuntimeError):
                    pass
        finally:
            self.session = ""
            if self.process and self.process.poll() is None:
                # This process group was created by this test, never a disk-restored PID.
                os.killpg(self.process.pid, signal.SIGTERM)
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(self.process.pid, signal.SIGKILL)
                    self.process.wait(timeout=5)
            self.log.close()


def tool(profile: dict, channel: str, name: str, args: dict) -> dict:
    if channel == "mcp":
        url = f"http://127.0.0.1:{profile['runtime']['local_port']}/mcp"
        value = request(url, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                              "params": {"name": name, "arguments": args}}, timeout=10)
        result = value.get("result", {}).get("structuredContent")
    else:
        url = f"http://127.0.0.1:{profile['actions']['local_port']}/actions/{name}"
        value = request(url, args, timeout=10)
        result = value.get("structured_content")
    if not isinstance(result, dict) or result.get("ok") is False:
        raise AssertionError(f"real {channel} {name} failed: {value}")
    return result


def run(args) -> None:
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    evidence = {"passed": False, "version": VERSION, "source_sha": args.source, "format": args.kind,
                "platform": platform.platform(), "executable": str(args.executable.resolve()),
                "real_native_webview": True, "mock_transport": False, "sandbox_disabled": False,
                "appimage_mode": "extract-and-run" if args.kind == "appimage" else None,
                "tests": []}
    session = None
    profile = None
    def passed(name):
        evidence["tests"].append({"name": name, "passed": True})
    try:
        if os.geteuid() == 0 or not os.environ.get("DISPLAY") or not os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
            raise RuntimeError("ordinary user, display and isolated D-Bus are required")
        if os.environ.get("WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS"):
            raise RuntimeError("sandbox bypass is prohibited")
        home = Path.home().resolve()
        if not (home / ".ubuntu-ci-fixture-v1").is_file():
            raise RuntimeError("refusing to modify a non-fixture user profile")
        session = NativeSession(args.executable.resolve(), args.driver.resolve(), output, 1)
        assert session.invoke("plugin:app|version") == VERSION
        wait_for(session.body, lambda text: "添加你的第一个工作区" in text and VERSION in text)
        session.screenshot(output / "首次启动v1.png")
        passed("安装后的真实窗口、首页与前后端版本")
        root = home / "工作区验收v1"
        root.mkdir()
        profile = session.invoke("create_workspace", {"path": str(root), "name": "Ubuntu桌面验收v1"})
        profile["tunnel"]["type"] = "none"
        profile["tunnel"]["public_url"] = ""
        profile["auth"]["type"] = "noauth"
        profile["actions"]["tunnel_type"] = "none"
        profile["actions"]["auth_type"] = "none"
        profile["actions"]["public_url"] = ""
        session.invoke("update_workspace", {"profile": profile})
        assert len(session.invoke("list_workspaces")) == 1
        session.call("refresh", {})
        wait_for(session.body, lambda text: "Ubuntu桌面验收v1" in text and "异步任务" in text)
        passed("真实IPC创建工作区与刷新后路由恢复")
        jobs = {}
        for channel, start in [("mcp", "start_runtime"), ("actions", "start_actions_runtime")]:
            session.invoke(start, {"id": profile["id"]})
            expected = f"Ubuntu {channel} 中文验收v1"
            params = {"cmd": f"python3 -c \"print('{expected}')\"", "request_id": f"Ubuntu-{channel}-v1", "timeout_ms": 30000}
            accepted = tool(profile, channel, "start_exec_task", params)
            job = accepted["job_id"]
            repeated = tool(profile, channel, "start_exec_task", params)
            assert repeated["job_id"] == job and repeated["deduplicated"] is True
            final = wait_for(lambda: tool(profile, channel, "get_exec_task", {"job_id": job}), lambda x: x["terminal"])
            assert final["status"] == "succeeded" and final["result"]["exit_code"] == 0, final
            assert expected in base64.b64decode(final["stdout"]["data_base64"]).decode("utf-8"), final
            assert final.get("restart_recoverable") is True and not final.get("persistence_failed"), final
            jobs[channel] = job
            passed(f"真实{channel} HTTP异步执行、幂等和中文输出")
        assert jobs["mcp"] != jobs["actions"]
        session.click_text("异步任务")
        wait_for(session.body, lambda text: "Ubuntu mcp 中文验收v1" in text and "退出码：0" in text)
        session.screenshot(output / "异步任务面板v1.png")
        passed("生产Svelte任务面板通过真实IPC显示原生命令结果")
        params = {"cmd": "python3 -c \"import time; print('started',flush=True); time.sleep(20)\"",
                  "request_id": "Ubuntu-cancel-v1", "timeout_ms": 30000}
        cancelling = tool(profile, "mcp", "start_exec_task", params)["job_id"]
        wait_for(lambda: tool(profile, "mcp", "get_exec_task", {"job_id": cancelling}),
                 lambda x: "started" in base64.b64decode(x["stdout"]["data_base64"]).decode(errors="replace"))
        tool(profile, "mcp", "cancel_exec_task", {"job_id": cancelling})
        final = wait_for(lambda: tool(profile, "mcp", "get_exec_task", {"job_id": cancelling}), lambda x: x["terminal"])
        assert final["status"] == "cancelled" and not final["result"].get("process_may_be_running"), final
        passed("已实际运行的异步进程取消并终结")
        for stop in ["stop_runtime", "stop_actions_runtime"]:
            session.invoke(stop, {"id": profile["id"]})
        session.close()
        session = None
        config = Path(os.environ["XDG_CONFIG_HOME"]) / "coding-tools-mcp-desktop/data/profiles.json"
        raw = config.read_text(encoding="utf-8")
        envelope = json.loads(raw)
        assert envelope["format"] == "coding-tools-mcp.encrypted" and envelope["algorithm"] == "AES-256-GCM"
        assert "Ubuntu桌面验收v1" not in raw and str(root) not in raw
        assert config.stat().st_mode & 0o077 == 0
        evidence["encrypted_config_sha256"] = hashlib.sha256(config.read_bytes()).hexdigest()
        passed("配置确实加密落盘且仅当前用户可读写")
        session = NativeSession(args.executable.resolve(), args.driver.resolve(), output, 2)
        restored = session.invoke("list_workspaces")
        assert len(restored) == 1 and restored[0]["id"] == profile["id"]
        for channel, job in jobs.items():
            record = session.invoke("control_exec_tasks", {"id": profile["id"], "channel": channel,
                                                           "action": "get", "args": {"job_id": job}})
            assert record["status"] == "succeeded" and record["job_id"] == job, record
        wait_for(session.body, lambda text: "Ubuntu桌面验收v1" in text)
        session.screenshot(output / "重启恢复v1.png")
        passed("原生应用重启后通过系统密钥恢复工作区与双通道任务记录")
        evidence["passed"] = len(evidence["tests"]) == 8
    except BaseException as exc:
        evidence["error"] = f"{type(exc).__name__}: {exc}"
        if session:
            try:
                session.screenshot(output / "失败现场v1.png")
            except Exception:
                pass
        raise
    finally:
        if session:
            session.close()
        (output / "原生验收结果v1.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"passed": evidence["passed"], "tests": len(evidence["tests"]), "format": args.kind}, ensure_ascii=False))
    if not evidence["passed"]:
        raise AssertionError("incomplete native acceptance")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--driver", type=Path, required=True)
    parser.add_argument("--kind", choices=["deb", "appimage"], required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
