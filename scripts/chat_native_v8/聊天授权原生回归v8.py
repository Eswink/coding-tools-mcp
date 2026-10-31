"""Static and offline contracts for 聊天授权原生验收v8 (no GUI, no network)."""
from __future__ import annotations
import ast
import importlib.util
from pathlib import Path
import re
import unittest

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
ROOT = SCRIPTS.parent
SOURCE = (HERE / "聊天授权原生验收v8.py").read_text(encoding="utf-8")
spec = importlib.util.spec_from_file_location("chat_native_v8", HERE / "聊天授权原生验收v8.py")
v8 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v8)


def rust_scopes():
    text = (ROOT / "src-tauri/src/auth/聊天授权v1.rs").read_text(encoding="utf-8")
    body = re.search(r"pub const SCOPES: &\[&str\] = &\[(.*?)\];", text, re.S).group(1)
    return re.findall(r'"([a-z.]+)"', body)


class FakeSession:
    """Records the native clicks and answers the dialog probes."""
    def __init__(self, scopes):
        self.scopes, self.checked, self.clicks = scopes, False, []
    def execute(self, script, *args):
        if "approval-dialog .verify input" in script:
            return False
        if "footer .tx-btn-primary').disabled" in script:
            return True
        if "footer .tx-btn-primary').textContent" in script:
            return "批准此聊天"
        if "dialog[aria-labelledby=global-approval-title][open]')" in script and "querySelector('code')" in script:
            return True
        if "value=\"${arguments[0]}\"" in script:
            present = v8.SENSITIVE in self.scopes
            return [present, self.checked, self.checked]
        if "[open]')" in script:
            return False
        raise AssertionError(script)
    def body(self):
        return ""


class NativeV8Contracts(unittest.TestCase):
    def test_scopes_are_v6_plus_agents_manage_and_match_the_native_list(self):
        self.assertEqual(v8.SCOPES, [*v8.v6.SCOPES, "agents.manage"])
        self.assertEqual(len(v8.SCOPES), 10)
        self.assertEqual(v8.SCOPES, rust_scopes())
        labels = (ROOT / "src/lib/chat-authorization.ts").read_text(encoding="utf-8")
        for scope in v8.SCOPES:
            self.assertIn(f'"{scope}":', labels)
        self.assertIn(f'"agents.manage": "{v8.WARNING}"', labels)

    def test_v8_reuses_frozen_v7_stages_evidence_and_gate(self):
        gate = (SCRIPTS / "聊天授权证据门禁v18.py").read_text(encoding="utf-8")
        names = ast.literal_eval(re.search(r"TEST_NAMES\s*=\s*(\[.*?\]|\(.*?\))", gate, re.S).group(1))
        self.assertEqual(list(v8.STAGES), list(names))
        self.assertEqual(v8.EVIDENCE, "聊天授权原生结果v6.json")
        self.assertIs(v8.v7.decide_in_dialog, v8.decide_in_dialog)
        self.assertEqual(v8.v7.SCOPES, v8.SCOPES)
        self.assertEqual(v8.v7.NAME, "聊天授权原生验收v8")

    def test_decisions_stay_native_clicks_and_never_ipc(self):
        for banned in ('"action": "approve"', '"action": "deny"', '"action": "revoke"', "核对指纹并批准"):
            self.assertNotIn(banned, SOURCE)
        self.assertIn("@value='{SENSITIVE}'", SOURCE)

    def test_no_workflow_runs_v8_yet(self):
        for path in (ROOT / ".github/workflows").glob("*.yml"):
            self.assertNotIn("chat_native_v8", path.read_text(encoding="utf-8"), path.name)

    def _decide(self, scopes, approve=True, granted=None, grant_sensitive=True):
        grant = {"id": "g1", "fingerprint": "0123456789abcdef", "scopes": scopes}
        session = FakeSession(scopes)
        clicks = []
        state = {"status": "pending"}
        def click(_session, xpath):
            clicks.append(xpath)
            if xpath == v8.SENSITIVE_BOX:
                session.checked = True
            elif xpath.endswith("[normalize-space(.)='批准此聊天']"):
                state.update(status="active", scopes=granted if granted is not None
                             else [s for s in scopes if s != "agents.manage" or session.checked])
            elif xpath.endswith("[normalize-space(.)='拒绝']"):
                state.update(status="denied")
        def rpc(_base, _token, _chat, name, _args):
            assert name == "auth_status"
            return {"authorization": dict(state)}
        orig = (v8.v7.click, v8.v7.rpc, v8.rpc, v8.v7.inbox, v8.gui.wait_for)
        def wait_for(fetch, check=lambda v: v):
            value = fetch()
            assert check(value), value
            return value
        try:
            v8.v7.click = click
            v8.v7.rpc = v8.rpc = rpc
            v8.v7.inbox = lambda _s: {"pending": [{"grant": {"id": "g1"}}]}
            v8.gui.wait_for = wait_for
            v8.decide_in_dialog(session, "b", "t", "c", grant, approve=approve, grant_sensitive=grant_sensitive)
        finally:
            v8.v7.click, v8.v7.rpc, v8.rpc, v8.v7.inbox, v8.gui.wait_for = orig
        return clicks

    def test_requested_sensitive_scope_is_ticked_by_one_native_click_before_approval(self):
        clicks = self._decide(v8.SCOPES)
        self.assertEqual(clicks[0], v8.SENSITIVE_BOX)
        self.assertEqual(clicks.count(v8.SENSITIVE_BOX), 1)
        self.assertTrue(clicks[-1].endswith("[normalize-space(.)='批准此聊天']"))

    def test_unrequested_or_withheld_sensitive_scope_is_never_clicked(self):
        self.assertNotIn(v8.SENSITIVE_BOX, self._decide(["workspace.read"]))
        self.assertNotIn(v8.SENSITIVE_BOX, self._decide(v8.SCOPES, grant_sensitive=False))
        self.assertNotIn(v8.SENSITIVE_BOX, self._decide(v8.SCOPES, approve=False))

    def test_a_grant_that_differs_from_the_ticked_boxes_fails(self):
        with self.assertRaises(AssertionError):
            self._decide(v8.SCOPES, granted=v8.v6.SCOPES)


if __name__ == "__main__":
    unittest.main()
