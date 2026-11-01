"""Real WebKit/WebView2 GUI + local OAuth HTTP; host conversation IDs are synthetic.

v8 of the eight-stage chat-authorization acceptance (A1 C6, SPEC-A1 v5.4 §3.1).
v6 and v7 stay frozen; v8 loads its own copy of v7 and only changes:

* SCOPES = v6.SCOPES + ["agents.manage"] (all ten local scopes);
* every dialog decision first proves that the sensitive `agents.manage` box,
  when requested, is rendered checked with the warning
  「Windows 无沙箱，子代理命令以你的权限运行」 shown (A1 C7pre: O13 decided
  2026-10-31, checked by default; UI default only), and absent otherwise;
  when it is to be withheld from an approval, unticks it with one native
  WebDriver click and waits for the warning to disappear before the v7
  decision clicks (the grant still needs that explicit local approval);
* the approved grant is read back over the MCP `auth_status` call and must
  contain exactly the ticked scopes.

The stages, evidence file and gate (聊天授权证据门禁v18) are v7's, unchanged.
No workflow references v8 yet (no yaml change in A1 C6; wiring it in is a
separate GO). No approval, denial or revocation is made through IPC.
"""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
sys.path.insert(0, str(SCRIPTS))
_spec = importlib.util.spec_from_file_location("chat_native_v7_frozen_for_v8", SCRIPTS / "chat_native_v7" / "聊天授权原生验收v7.py")
v7 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(v7)
v6, gui, rpc = v7.v6, v7.gui, v7.rpc
SENSITIVE = "agents.manage"
WARNING = "Windows 无沙箱，子代理命令以你的权限运行"
SCOPES = [*v6.SCOPES, SENSITIVE]
NAME = "聊天授权原生验收v8"
STAGES, EVIDENCE, MODAL = v7.STAGES, v7.EVIDENCE, v7.MODAL
SENSITIVE_BOX = MODAL + f"//input[@type='checkbox' and @value='{SENSITIVE}']"
_v7_decide = v7.decide_in_dialog


def sensitive_state(session):
    """(rendered, checked, warning shown) for the sensitive box in the open dialog."""
    return tuple(session.execute("""
        const dialog = document.querySelector('dialog[aria-labelledby=global-approval-title][open]');
        const box = dialog?.querySelector(`input[type=checkbox][value="${arguments[0]}"]`);
        const warned = [...(dialog?.querySelectorAll('[role=alert]') ?? [])].some(e => e.textContent.trim() === arguments[1]);
        return [!!box, !!box?.checked, warned];
    """, SENSITIVE, WARNING))


def decide_in_dialog(session, base, token, chat, grant, *, approve=True, exclusive=False, grant_sensitive=True):
    gui.wait_for(lambda: v7.inbox(session), lambda value:
        any(row.get("grant", {}).get("id") == grant["id"] for row in value["pending"]))
    v7.open_dialog(session, grant["fingerprint"])
    requested = SENSITIVE in grant["scopes"]
    assert sensitive_state(session) == (requested, requested, requested), \
        "a requested sensitive scope must start checked with its warning (O13 default checked)"
    tick = approve and requested and grant_sensitive
    if approve and requested and not grant_sensitive:
        v7.click(session, SENSITIVE_BOX)  # One native click to withhold it; never retried.
        gui.wait_for(lambda: sensitive_state(session), lambda state: state == (True, False, False))
    _v7_decide(session, base, token, chat, grant, approve=approve, exclusive=exclusive)
    if approve:
        granted = rpc(base, token, chat, "auth_status", {})["authorization"]["scopes"]
        expected = sorted(s for s in grant["scopes"] if s != SENSITIVE or tick)
        assert sorted(granted) == expected, "approved scopes differ from the ticked boxes"


# The frozen v7 flow resolves these names in its own module globals.
v7.SCOPES = SCOPES
v7.NAME = NAME
v7.decide_in_dialog = decide_in_dialog
run, finish_evidence = v7.run, v7.finish_evidence

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--driver", type=Path, required=True)
    parser.add_argument("--kind", choices=["native", "deb", "appimage", "nsis"], required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fixture-root", type=Path)
    run(parser.parse_args())
