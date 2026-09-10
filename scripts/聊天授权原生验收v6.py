"""Real WebKit/WebView2 GUI + local OAuth HTTP; host conversation IDs are synthetic.

Approvals, denial, revocation and exclusivity use native WebDriver clicks. Only
fixture setup and trusted local task cleanup use IPC. No public tunnel, mock IPC,
real account credentials or sandbox-disable flags are involved.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request

spec = importlib.util.spec_from_file_location("native_gui_v1", Path(__file__).with_name("Ubuntu原生验收v1.py"))
gui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gui)
adapter_spec = importlib.util.spec_from_file_location("native_adapter_v8", Path(__file__).with_name("跨平台原生驱动v8.py"))
adapter = importlib.util.module_from_spec(adapter_spec)
adapter_spec.loader.exec_module(adapter)
SCOPES = ["workspace.read", "files.read", "files.write", "exec.run", "task.read",
          "task.manage", "history.read", "history.write", "harness.write"]
NAME = "聊天授权原生验收v6"
ELEMENT = "element-6066-11e4-a52e-4f735466cecf"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never follow the synthetic OAuth callback to ChatGPT.


HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())


def exchange(url: str, data: dict | None = None, *, token: str | None = None, form: bool = False):
    headers = {"Accept": "application/json"}
    raw = None
    if data is not None:
        raw = urllib.parse.urlencode(data).encode() if form else json.dumps(data).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded" if form else "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=raw, headers=headers)
    try:
        response = HTTP.open(req, timeout=20)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        payload = response.read(1024 * 1024 + 1)
        if len(payload) > 1024 * 1024:
            raise AssertionError("oversized native HTTP response")
        return response.code, response.headers, payload


def oauth_token(base: str, client_id: str, password: str, callback: str, private_path: str) -> str:
    status, _, raw = exchange(base + "/.well-known/oauth-protected-resource")
    assert status == 200
    resource = json.loads(raw)["resource"]
    assert resource == base
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    common = {"client_id": client_id, "redirect_uri": callback, "code_challenge": challenge,
              "code_challenge_method": "S256", "resource": resource, "scope": "mcp", "state": "native-fixture-v6"}
    status, _, raw = exchange(base + "/oauth/authorize?" + urllib.parse.urlencode({**common, "response_type": "code"}))
    assert status == 200 and private_path.encode() not in raw and password.encode() not in raw
    status, headers, _ = exchange(base + "/oauth/authorize", {**common, "password": password}, form=True)
    assert status == 303
    target = urllib.parse.urlsplit(headers["Location"])
    expected = urllib.parse.urlsplit(callback)
    assert (target.scheme, target.netloc, target.path) == (expected.scheme, expected.netloc, expected.path)
    params = urllib.parse.parse_qs(target.query)
    assert params["state"] == [common["state"]]
    status, headers, raw = exchange(base + "/oauth/token", {"grant_type": "authorization_code",
        "code": params["code"][0], "code_verifier": verifier, "client_id": client_id,
        "redirect_uri": callback, "resource": resource}, form=True)
    assert status == 200 and headers["Cache-Control"] == "no-store"
    token = json.loads(raw)["access_token"]
    assert isinstance(token, str) and token
    return token


def rpc(base: str, token: str, chat: str | None, name: str, arguments: dict) -> dict:
    params = {"name": name, "arguments": arguments}
    if chat is not None:
        params["_meta"] = {"openai/session": chat}
    status, _, raw = exchange(base + "/mcp", {"jsonrpc": "2.0", "id": 1,
        "method": "tools/call", "params": params}, token=token)
    assert status == 200, "authenticated MCP transport failed"
    value = json.loads(raw).get("result", {}).get("structuredContent")
    assert isinstance(value, dict), "missing structured tool response"
    return value


def click(session, xpath: str) -> None:
    element = gui.wait_for(lambda: session.call("element", {"using": "xpath", "value": xpath}))
    session.call(f"element/{element[ELEMENT]}/click", {})  # A mutation is never retried.


def visit(session, profile: dict) -> None:
    session.click_text(NAME)
    gui.wait_for(lambda: session.call("url"), lambda url:
        urllib.parse.urlsplit(url).path.rstrip("/") == "/workspace/" + profile["id"])
    gui.wait_for(session.body, lambda text: "ChatGPT 聊天授权" in text and "暂无请求" in text)


def request_grant(session, base, token, chat, scopes, *, approve=True):
    first = rpc(base, token, chat, "request_chat_authorization", {"scopes": scopes})
    assert first["ok"] is True
    grant = first["authorization"]
    assert grant["status"] == "pending"
    repeated = rpc(base, token, chat, "request_chat_authorization", {"scopes": scopes})
    assert repeated["authorization"] == grant, "retry changed pending approval"
    fingerprint = grant["fingerprint"]
    assert len(fingerprint) == 16 and all(c in "0123456789abcdef" for c in fingerprint)
    button = "核对指纹并批准" if approve else "拒绝"
    click(session, f"//section[@aria-labelledby='chat-authorization-heading']//article[.//code[text()='{fingerprint}']]//button[normalize-space(.)='{button}']")
    expected = "active" if approve else "denied"
    gui.wait_for(lambda: rpc(base, token, chat, "auth_status", {}),
                 lambda value: value.get("authorization", {}).get("status") == expected)
    return grant


def denied(value: dict, private_path: str) -> None:
    assert value.get("ok") is False and value.get("error", {}).get("code") == "CHAT_AUTHORIZATION_REQUIRED"
    text = json.dumps(value, ensure_ascii=False)
    assert private_path not in text and "chat-A-only-v6" not in text


def finish_evidence(output: Path, evidence: dict, session, primary_failed: bool) -> None:
    """Cleanup failure must neither erase earlier evidence nor produce PASS."""
    cleanup_error = None
    if session:
        try:
            session.close()
            evidence["cleanup_completed"] = True
        except BaseException as error:
            cleanup_error = error
            evidence["passed"] = False
            evidence["cleanup_failed"] = True
            evidence["cleanup_failure_type"] = type(error).__name__
    # Preserve the first failure and always persist bounded, secret-free metadata.
    (output / "聊天授权原生结果v6.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": evidence["passed"], "tests": len(evidence["tests"])}))
    if cleanup_error is not None and not primary_failed:
        raise cleanup_error


def run(args) -> None:
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    evidence = {"passed": False, "source_sha": args.source, "run_id": os.environ.get("GITHUB_RUN_ID"),
        "platform": platform.platform(),
        "binary_sha256": None, "build_kind": "debug-static-assets" if args.kind == "native" else "release-installed",
        "package_kind": args.kind,
        "real_native_webview": False, "real_oauth_http": False, "real_local_ipc": False,
        "cleanup_failed": False, "cleanup_completed": False,
        "synthetic_conversation_metadata": True, "real_chatgpt_verified": False,
        "sandbox_disabled": False, "tests": []}
    session = None
    profile = None
    primary_failed = False
    def passed(name):
        evidence["tests"].append({"name": name, "passed": True})
        print("PASS " + name, flush=True)
    try:
        evidence["binary_sha256"] = hashlib.sha256(args.executable.read_bytes()).hexdigest()
        home = adapter.fixture_root(args)
        session = adapter.session(args.executable.resolve(), args.driver.resolve(), output, 1)
        evidence["real_native_webview"] = True
        evidence["version"] = session.invoke("plugin:app|version")
        evidence["real_local_ipc"] = True
        expected_version = json.loads((Path(__file__).resolve().parents[1] / "package.json").read_text(encoding="utf-8"))["version"]
        assert evidence["version"] == expected_version, "native binary version differs from source"
        assert session.invoke("list_workspaces") == [], "refusing a nonempty application profile"
        root = home / "聊天授权工作区v6"
        root.mkdir()
        (root / "只读样本v6.txt").write_text("chat-file-canary-v6", encoding="utf-8")
        profile = session.invoke("create_workspace", {"path": str(root), "name": NAME})
        profile["tunnel"].update(type="none", public_url="")
        profile["auth"].update(type="oauth", oauth_client_id="native-chat-client-v6", use_shared_secrets=False,
                               oauth_redirect_uri="https://chatgpt.com/connector/oauth/native-fixture-v6")
        profile["runtime"].update(local_port=gui.port(), tool_profile="full")
        profile["actions"].update(tunnel_type="none", public_url="", auth_type="none", local_port=gui.port())
        assert profile["actions"]["local_port"] != profile["runtime"]["local_port"]
        session.invoke("update_workspace", {"profile": profile})
        password = secrets.token_urlsafe(32)
        for key, value in [("oauth_password", password), ("oauth_token_secret", secrets.token_urlsafe(48))]:
            session.invoke("set_workspace_secret", {"id": profile["id"], "key": key, "value": value})
        session.call("refresh", {})
        visit(session, profile)
        session.screenshot(output / "审批前窗口v6.png")
        passed("真实窗口、工作区与本机安全配置")
        session.invoke("start_runtime", {"id": profile["id"]})
        base = "http://127.0.0.1:" + str(profile["runtime"]["local_port"])
        status, headers, _ = exchange(base + "/mcp", {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert status == 401 and "resource_metadata" in headers["WWW-Authenticate"]
        token = oauth_token(base, profile["auth"]["oauth_client_id"], password,
                            profile["auth"]["oauth_redirect_uri"], str(root))
        evidence["real_oauth_http"] = True
        passed("真实OAuth发现、PKCE授权码交换与401挑战")
        a, b, c = ["synthetic-native-" + secrets.token_hex(16) for _ in range(3)]
        for chat, arguments in [(a, {}), (b, {"authorized": True, "_meta": {"openai/session": a}}), (None, {})]:
            denied(rpc(base, token, chat, "server_info", arguments), str(root))
        assert rpc(base, token, a, "auth_status", {})["authorization"]["status"] == "unauthorized"
        passed("未审批、缺会话与模型伪造参数全部拒绝")
        request_grant(session, base, token, a, SCOPES)
        assert rpc(base, token, a, "server_info", {})["ok"] is True
        denied(rpc(base, token, b, "server_info", {}), str(root))
        sample = rpc(base, token, a, "read_file", {"path": "只读样本v6.txt"})
        assert sample["ok"] is True and "chat-file-canary-v6" in json.dumps(sample)
        session.screenshot(output / "批准会话Av6.png")
        passed("原生点击批准A、A读文件且B仍拒绝")
        request_grant(session, base, token, b, SCOPES)
        python = "python" if sys.platform == "win32" else "python3"
        job_a = rpc(base, token, a, "start_exec_task", {"cmd": python + " -c \"import time; print('chat-A-only-v6', flush=True); time.sleep(60)\"",
                                                       "request_id": "shared-native-id-v6", "timeout_ms": 120000})
        assert job_a["ok"] is True
        job_id = job_a["job_id"]
        assert rpc(base, token, b, "list_exec_tasks", {})["jobs"] == []
        for name in ["get_exec_task", "cancel_exec_task"]:
            rejected = rpc(base, token, b, name, {"job_id": job_id})
            assert rejected["ok"] is False and "chat-A-only-v6" not in json.dumps(rejected)
        job_b = rpc(base, token, b, "start_exec_task", {"cmd": python + " -c \"print('chat-B-only-v6')\"", "request_id": "shared-native-id-v6"})
        assert job_b["ok"] is True and job_b["job_id"] != job_id
        finished = gui.wait_for(lambda: rpc(base, token, b, "get_exec_task", {"job_id": job_b["job_id"]}), lambda value: value.get("terminal") is True)
        assert finished["status"] == "succeeded"
        local = session.invoke("control_exec_tasks", {"id": profile["id"], "channel": "mcp", "action": "cancel", "args": {"job_id": job_id}})
        assert local["ok"] is True
        stopped = gui.wait_for(lambda: rpc(base, token, a, "get_exec_task", {"job_id": job_id}), lambda value: value.get("terminal") is True)
        assert stopped["status"] == "cancelled"
        passed("双会话真实异步进程、幂等隔离与本机取消")
        click(session, "//section[@aria-labelledby='chat-authorization-heading']//button[normalize-space(.)='撤销全部']")
        for chat in [a, b]:
            gui.wait_for(lambda chat=chat: rpc(base, token, chat, "auth_status", {}), lambda value: value["authorization"]["status"] == "revoked")
            denied(rpc(base, token, chat, "server_info", {}), str(root))
        request_grant(session, base, token, b, ["workspace.read", "files.read"])
        denied(rpc(base, token, b, "exec_command", {"cmd": python + " -c \"print('must-not-execute')\""}), str(root))
        denied(rpc(base, token, b, "request_permissions", {"mode": "dangerous", "confirm": True}), str(root))
        passed("真实撤销全部、只读授权与禁止自提权")
        click(session, "//section[@aria-labelledby='chat-authorization-heading']//label[contains(@class,'exclusive')]//input")
        denied(rpc(base, token, b, "server_info", {}), str(root))
        request_grant(session, base, token, a, ["workspace.read"])
        request_grant(session, base, token, b, ["workspace.read"])
        denied(rpc(base, token, a, "server_info", {}), str(root))
        assert rpc(base, token, b, "server_info", {})["ok"] is True
        request_grant(session, base, token, c, ["workspace.read"], approve=False)
        denied(rpc(base, token, c, "server_info", {}), str(root))
        session.screenshot(output / "独占与拒绝v6.png")
        passed("原生独占切换、单一获准聊天与拒绝请求")
        session.invoke("stop_runtime", {"id": profile["id"]})
        session.close()
        session = adapter.session(args.executable.resolve(), args.driver.resolve(), output, 2)
        assert len(session.invoke("list_workspaces")) == 1
        session.invoke("start_runtime", {"id": profile["id"]})
        assert rpc(base, token, b, "auth_status", {})["authorization"]["status"] == "unauthorized"
        denied(rpc(base, token, b, "server_info", {}), str(root))
        session.screenshot(output / "进程重启后v6.png")
        passed("真实进程重启保留OAuth凭据但不恢复聊天授权")
        assert len(evidence["tests"]) == 8
        evidence["passed"] = True
    except BaseException as error:
        primary_failed = True
        evidence["failure_type"] = type(error).__name__
        if isinstance(error, adapter.NativeHostExited):
            evidence["host_exit_code"] = error.exit_code
            evidence["failure_stage"] = "owned-python-host"
        # Do not persist exception payloads that may contain credentials or tool data.
        raise
    finally:
        finish_evidence(output, evidence, session, primary_failed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--driver", type=Path, required=True)
    parser.add_argument("--kind", choices=["native", "deb", "appimage", "nsis"], required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fixture-root", type=Path)
    run(parser.parse_args())
