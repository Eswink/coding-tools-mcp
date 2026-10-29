"""Real WebKit/WebView2 GUI + local OAuth HTTP; host conversation IDs are synthetic.

v7 of the eight-stage chat-authorization acceptance. The frozen v6 script clicks
inline panel buttons that the global approval dialog
(`//dialog[@aria-labelledby='global-approval-title']`) now covers, and expects the
old "last approval wins" exclusivity. v7 keeps v6's stages, evidence file and
gate (聊天授权证据门禁v18) but decides every request in that dialog with native
WebDriver clicks: open the candidate, tick the verification box, then
"批准此聊天" (shared policy), "批准并独占" (exclusive policy) or "拒绝".

The concurrent A/B stages need a shared workspace, so fixture setup saves
`session_policy.exclusive = false` through the same local `update_workspace`
IPC the "远程会话安全" save button uses (its confirm box is an OS dialog that
WebDriver cannot drive). Stage 7 saves `exclusive = true` the same way; the
switch is recorded in the evidence as local IPC, never as a click. No approval,
denial or revocation is made through IPC. No public tunnel, mock IPC, real
account credentials or sandbox-disable flags are involved.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import secrets
import subprocess
import sys
import time
import urllib.parse

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
_spec = importlib.util.spec_from_file_location("chat_native_v6_frozen", SCRIPTS / "聊天授权原生验收v6.py")
v6 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(v6)
gui, adapter, exchange, rpc, oauth_token = v6.gui, v6.adapter, v6.exchange, v6.rpc, v6.oauth_token
SCOPES = v6.SCOPES
ELEMENT = v6.ELEMENT
NAME = "聊天授权原生验收v7"
EVIDENCE = "聊天授权原生结果v6.json"  # Consumed unchanged by 证据门禁v18 and 发布v26.
MODAL = "//dialog[@aria-labelledby='global-approval-title']"
PANEL = "//section[@aria-labelledby='chat-authorization-heading']"
STAGES = (
    "真实窗口、工作区与本机安全配置",
    "真实OAuth发现、PKCE授权码交换与401挑战",
    "未审批、缺会话与模型伪造参数全部拒绝",
    "原生点击批准A、A读文件且B仍拒绝",
    "双会话真实异步进程、幂等隔离与本机取消",
    "真实撤销全部、只读授权与禁止自提权",
    "原生独占切换、单一获准聊天与拒绝请求",
    "真实进程重启保留OAuth凭据但不恢复聊天授权",
)
APPROVE = {False: "批准此聊天", True: "批准并独占"}
SECRET_SERVICE_HINT = "系统 Secret Service 暂不可用"
KEYRING_FIXTURE_PASSWORD = b"isolated-ubuntu-native-v1"


def reunlock_ci_keyring() -> None:
    """Re-unlock the CI gnome-keyring once; never touches a user desktop session."""
    if sys.platform == "win32":
        return
    subprocess.run(["gnome-keyring-daemon", "--unlock", "--components=secrets"],
        input=KEYRING_FIXTURE_PASSWORD, check=False, capture_output=True, timeout=15)


def click(session, xpath: str) -> None:
    v6.click(session, xpath)  # One native click; a mutation is never retried.


def status(session, profile):
    return session.invoke("chat_authorization_control", {"id": profile["id"], "action": "status",
        "requestId": None, "scopes": None, "exclusive": None})


def inbox(session):
    return session.invoke("chat_authorization_inbox")


def modal_open(session) -> bool:
    return session.execute("return !!document.querySelector('dialog[aria-labelledby=global-approval-title][open]')") is True


def dialog_shows(session, fingerprint: str) -> bool:
    return session.execute("""
        const dialog = document.querySelector('dialog[aria-labelledby=global-approval-title][open]');
        return !!dialog && dialog.querySelector('code')?.textContent === arguments[0];
    """, fingerprint) is True


def open_dialog(session, fingerprint: str) -> None:
    """Show exactly this candidate in the global dialog.

    A foreground invalidation may open the dialog on its own between our
    observation and the inbox click; WebKit then reports the covered inbox
    button as not interactable. Only that narrow result is accepted, and only
    when a readback proves the expected dialog is already open.
    """
    if not dialog_shows(session, fingerprint):
        try:
            click(session, "//button[contains(@class,'approval-inbox')]")
        except RuntimeError as error:
            code = None
            if str(error).startswith("HTTP 400: "):
                try:
                    code = json.loads(str(error)[len("HTTP 400: "):]).get("value", {}).get("error")
                except (ValueError, AttributeError):
                    pass
            if code not in ("element not interactable", "element click intercepted") or not dialog_shows(session, fingerprint):
                raise
    gui.wait_for(lambda: dialog_shows(session, fingerprint))


def request(base, token, chat, scopes) -> dict:
    first = rpc(base, token, chat, "request_chat_authorization", {"scopes": scopes})
    assert first["ok"] is True
    grant = first["authorization"]
    assert grant["status"] == "pending"
    repeated = rpc(base, token, chat, "request_chat_authorization", {"scopes": scopes})
    assert repeated["authorization"] == grant, "retry changed pending approval"
    fingerprint = grant["fingerprint"]
    assert len(fingerprint) == 16 and all(c in "0123456789abcdef" for c in fingerprint)
    return grant


def decide_in_dialog(session, base, token, chat, grant, *, approve=True, exclusive=False):
    gui.wait_for(lambda: inbox(session), lambda value:
        any(row.get("grant", {}).get("id") == grant["id"] for row in value["pending"]))
    open_dialog(session, grant["fingerprint"])
    assert session.execute("return document.querySelector('.approval-dialog .verify input').checked") is False
    assert session.execute("return document.querySelector('.approval-dialog footer .tx-btn-primary').disabled") is True
    label = session.execute("return document.querySelector('.approval-dialog footer .tx-btn-primary').textContent.trim()")
    assert label == APPROVE[exclusive], "dialog policy differs from the saved workspace policy"
    if approve:
        click(session, MODAL + "//label[contains(@class,'verify')]//input")
        click(session, MODAL + f"//button[normalize-space(.)='{APPROVE[exclusive]}']")
    else:
        click(session, MODAL + "//button[normalize-space(.)='拒绝']")
    expected = "active" if approve else "denied"
    recovered = False

    def auth_or_recover():
        nonlocal recovered
        if approve and not recovered and SECRET_SERVICE_HINT in (session.body() or ""):
            # One controlled recovery click after the CI keyring re-unlock; never a blind replay.
            reunlock_ci_keyring()
            time.sleep(0.5)
            click(session, MODAL + f"//button[normalize-space(.)='{APPROVE[exclusive]}']")
            recovered = True
        return rpc(base, token, chat, "auth_status", {})

    value = gui.wait_for(auth_or_recover,
        lambda value: value.get("authorization", {}).get("status") == expected)
    gui.wait_for(lambda: not modal_open(session))
    return value["authorization"]


def request_grant(session, base, token, chat, scopes, *, approve=True, exclusive=False):
    grant = request(base, token, chat, scopes)
    decide_in_dialog(session, base, token, chat, grant, approve=approve, exclusive=exclusive)
    return grant


def revoke_all(session, profile) -> None:
    """One native click on the panel's 撤销全部 once its handler is ready."""
    assert not modal_open(session)
    def enabled_button():
        element = session.call("element", {"using": "xpath", "value": PANEL + "//button[normalize-space(.)='撤销全部']"})
        element_id = element[ELEMENT]
        return element_id if session.call(f"element/{element_id}/enabled") is True else None
    element_id = gui.wait_for(enabled_button)
    session.call(f"element/{element_id}/click", {})  # Never retry a mutation.
    gui.wait_for(lambda: status(session, profile), lambda value:
        not any(row.get("status") in ("pending", "active") for row in value["records"]))


def save_policy(session, profile, *, exclusive: bool) -> None:
    """Fixture policy save through the same IPC as the settings save button."""
    profile["auth"]["session_policy"]["exclusive"] = exclusive
    session.invoke("update_workspace", {"profile": profile})
    saved = session.invoke("list_workspaces")
    assert [p["auth"]["session_policy"]["exclusive"] for p in saved if p["id"] == profile["id"]] == [exclusive]


def refused(value: dict, private_path: str, code: str = "CHAT_AUTHORIZATION_REQUIRED") -> None:
    assert value.get("ok") is False and value.get("error", {}).get("code") == code
    text = json.dumps(value, ensure_ascii=False)
    assert private_path not in text and "chat-A-only-v6" not in text


def run(args) -> None:
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    evidence = {"passed": False, "source_sha": args.source, "run_id": os.environ.get("GITHUB_RUN_ID"),
        "platform": platform.platform(), "acceptance_script": NAME,
        "binary_sha256": None, "build_kind": "debug-static-assets" if args.kind == "native" else "release-installed",
        "package_kind": args.kind,
        "real_native_webview": False, "real_oauth_http": False, "real_local_ipc": False,
        "cleanup_failed": False, "cleanup_completed": False,
        "synthetic_conversation_metadata": True, "real_chatgpt_verified": False,
        "sandbox_disabled": False, "permission_approval_source": "native-webdriver-clicks-global-dialog",
        "session_policy_switch_source": "local-ipc-update_workspace", "tests": []}
    session = None
    primary_failed = False
    def passed(index):
        assert index == len(evidence["tests"])
        evidence["tests"].append({"name": STAGES[index], "passed": True})
        print("PASS " + STAGES[index], flush=True)
    try:
        evidence["binary_sha256"] = hashlib.sha256(args.executable.read_bytes()).hexdigest()
        home = adapter.fixture_root(args)
        session = adapter.session(args.executable.resolve(), args.driver.resolve(), output, 1)
        evidence["real_native_webview"] = True
        evidence["version"] = session.invoke("plugin:app|version")
        evidence["real_local_ipc"] = True
        expected_version = json.loads((SCRIPTS.parent / "package.json").read_text(encoding="utf-8"))["version"]
        assert evidence["version"] == expected_version, "native binary version differs from source"
        assert session.invoke("list_workspaces") == [], "refusing a nonempty application profile"
        root = home / "聊天授权工作区v7"
        root.mkdir()
        (root / "只读样本v6.txt").write_text("chat-file-canary-v6", encoding="utf-8")
        profile = session.invoke("create_workspace", {"path": str(root), "name": NAME})
        assert profile["auth"]["session_policy"]["exclusive"] is True, "default must stay exclusive"
        profile["tunnel"].update(type="none", public_url="")
        profile["auth"].update(type="oauth", oauth_client_id="native-chat-client-v7", use_shared_secrets=False,
                               oauth_redirect_uri="https://chatgpt.com/connector/oauth/native-fixture-v7")
        profile["auth"]["session_policy"]["exclusive"] = False  # Shared: the A/B stages run concurrently.
        profile["runtime"].update(local_port=gui.port(), tool_profile="full")
        profile["actions"].update(tunnel_type="none", public_url="", auth_type="none", local_port=gui.port())
        assert profile["actions"]["local_port"] != profile["runtime"]["local_port"]
        session.invoke("update_workspace", {"profile": profile})
        password = secrets.token_urlsafe(32)
        client_secret = secrets.token_urlsafe(32)
        for key, value in [("oauth_password", password), ("oauth_client_secret", client_secret),
                           ("oauth_token_secret", secrets.token_urlsafe(48))]:
            session.invoke("set_workspace_secret", {"id": profile["id"], "key": key, "value": value})
        session.call("refresh", {})
        session.click_text(NAME)
        gui.wait_for(lambda: session.call("url"), lambda url:
            urllib.parse.urlsplit(url).path.rstrip("/") == "/workspace/" + profile["id"])
        gui.wait_for(session.body, lambda text: "ChatGPT 聊天授权" in text)
        assert session.execute("return document.querySelector('.remote-session-settings input[type=checkbox]').checked") is False
        session.screenshot(output / "审批前窗口v7.png")
        passed(0)
        session.invoke("start_runtime", {"id": profile["id"]})
        assert status(session, profile)["exclusive"] is False
        base = "http://127.0.0.1:" + str(profile["runtime"]["local_port"])
        code, headers, _ = exchange(base + "/mcp", {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert code == 401 and headers["Cache-Control"] == "no-store"
        assert headers["WWW-Authenticate"] == f'Bearer resource_metadata="{base}/.well-known/oauth-protected-resource/mcp", scope="mcp"'
        token = oauth_token(base, profile["auth"]["oauth_client_id"], password,
                            profile["auth"]["oauth_redirect_uri"], str(root), client_secret=client_secret)
        evidence["real_oauth_http"] = True
        passed(1)
        a, b, c = ["synthetic-native-" + secrets.token_hex(16) for _ in range(3)]
        for chat, arguments in [(a, {}), (b, {"authorized": True, "_meta": {"openai/session": a}}), (None, {})]:
            refused(rpc(base, token, chat, "server_info", arguments), str(root))
        assert rpc(base, token, a, "auth_status", {})["authorization"]["status"] == "unauthorized"
        passed(2)
        request_grant(session, base, token, a, SCOPES)
        assert rpc(base, token, a, "server_info", {})["ok"] is True
        refused(rpc(base, token, b, "server_info", {}), str(root))
        sample = rpc(base, token, a, "read_file", {"path": "只读样本v6.txt"})
        assert sample["ok"] is True and "chat-file-canary-v6" in json.dumps(sample)
        session.screenshot(output / "批准会话Av7.png")
        passed(3)
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
        passed(4)
        revoke_all(session, profile)
        for chat in [a, b]:
            gui.wait_for(lambda chat=chat: rpc(base, token, chat, "auth_status", {}), lambda value: value["authorization"]["status"] == "revoked")
            refused(rpc(base, token, chat, "server_info", {}), str(root))
        request_grant(session, base, token, b, ["workspace.read", "files.read"])
        refused(rpc(base, token, b, "exec_command", {"cmd": python + " -c \"print('must-not-execute')\""}), str(root))
        refused(rpc(base, token, b, "request_permissions", {"mode": "dangerous", "confirm": True}), str(root))
        passed(5)
        save_policy(session, profile, exclusive=True)
        gui.wait_for(lambda: status(session, profile), lambda value: value["exclusive"] is True)
        gui.wait_for(lambda: rpc(base, token, b, "server_info", {}), lambda value: value.get("ok") is False)
        refused(rpc(base, token, b, "server_info", {}), str(root))  # Saving a policy revokes every chat.
        request_grant(session, base, token, a, ["workspace.read"], exclusive=True)
        assert rpc(base, token, a, "server_info", {})["ok"] is True
        before = inbox(session)
        refused(rpc(base, token, b, "request_chat_authorization", {"scopes": ["workspace.read"]}), str(root), "EXCLUSIVE_CHAT_LOCKED")
        refused(rpc(base, token, b, "server_info", {}), str(root), "EXCLUSIVE_CHAT_LOCKED")
        assert inbox(session)["pending"] == [] and inbox(session)["revision"] == before["revision"]
        assert not modal_open(session)
        revoke_all(session, profile)
        request_grant(session, base, token, c, ["workspace.read"], approve=False, exclusive=True)
        refused(rpc(base, token, c, "server_info", {}), str(root))
        session.screenshot(output / "独占与拒绝v7.png")
        passed(6)
        session.invoke("stop_runtime", {"id": profile["id"]})
        session.close()
        session = adapter.session(args.executable.resolve(), args.driver.resolve(), output, 2)
        assert len(session.invoke("list_workspaces")) == 1
        session.invoke("start_runtime", {"id": profile["id"]})
        for chat in (a, b):
            assert rpc(base, token, chat, "auth_status", {})["authorization"]["status"] == "unauthorized"
            refused(rpc(base, token, chat, "server_info", {}), str(root))
        session.screenshot(output / "进程重启后v7.png")
        passed(7)
        assert len(evidence["tests"]) == len(STAGES) == 8
        evidence["passed"] = True
    except BaseException as error:
        primary_failed = True
        evidence["failure_type"] = type(error).__name__
        if isinstance(error, adapter.NativeHostExited):
            evidence["host_exit_code"] = error.exit_code
            evidence["failure_stage"] = "owned-python-host"
        if session:
            try: session.screenshot(output / "失败现场v7.png")
            except BaseException: pass
        # Do not persist exception payloads that may contain credentials or tool data.
        raise
    finally:
        finish_evidence(output, evidence, session, primary_failed)


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
    (output / EVIDENCE).write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": evidence["passed"], "tests": len(evidence["tests"]), "script": NAME}, ensure_ascii=False))
    if cleanup_error is not None and not primary_failed:
        raise cleanup_error


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--driver", type=Path, required=True)
    parser.add_argument("--kind", choices=["native", "deb", "appimage", "nsis"], required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fixture-root", type=Path)
    run(parser.parse_args())
