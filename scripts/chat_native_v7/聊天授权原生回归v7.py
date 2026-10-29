"""Static and offline contracts for 聊天授权原生验收v7 (no GUI, no network)."""
from __future__ import annotations
import ast
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
ROOT = SCRIPTS.parent
SOURCE = (HERE / "聊天授权原生验收v7.py").read_text(encoding="utf-8")
spec = importlib.util.spec_from_file_location("chat_native_v7", HERE / "聊天授权原生验收v7.py")
v7 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v7)


class NativeV7Contracts(unittest.TestCase):
    def test_stage_names_match_gate_v18_exactly(self):
        gate = (SCRIPTS / "聊天授权证据门禁v18.py").read_text(encoding="utf-8")
        names = ast.literal_eval(re.search(r"TEST_NAMES\s*=\s*(\[.*?\]|\(.*?\))", gate, re.S).group(1))
        self.assertEqual(list(v7.STAGES), list(names))
        self.assertEqual(v7.EVIDENCE, "聊天授权原生结果v6.json")

    def test_decisions_only_use_global_dialog_native_clicks(self):
        self.assertNotIn("核对指纹并批准", SOURCE)
        self.assertNotIn("contains(@class,'exclusive')", SOURCE)
        self.assertNotIn('"action": "approve"', SOURCE)
        self.assertNotIn('"action": "deny"', SOURCE)
        self.assertNotIn('"action": "revoke"', SOURCE)
        self.assertNotIn('"action": "exclusive"', SOURCE)
        self.assertEqual(v7.APPROVE, {False: "批准此聊天", True: "批准并独占"})
        self.assertIn("aria-labelledby='global-approval-title'", v7.MODAL)

    def test_policy_switch_is_declared_as_local_ipc(self):
        self.assertIn('"session_policy_switch_source": "local-ipc-update_workspace"', SOURCE)
        self.assertIn('"permission_approval_source": "native-webdriver-clicks-global-dialog"', SOURCE)

    def test_both_linux_workflows_run_v7(self):
        for name in ("聊天授权安装包v10.yml", "聊天授权验证v1.yml"):
            text = (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
            self.assertIn("scripts/chat_native_v7/聊天授权原生验收v7.py", text)
            self.assertNotIn("scripts/聊天授权原生验收v6.py", text)

    def test_failed_run_still_writes_bounded_failure_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = {"passed": False, "tests": [], "failure_type": "AssertionError"}
            v7.finish_evidence(Path(tmp), evidence, None, True)
            saved = json.loads((Path(tmp) / v7.EVIDENCE).read_text(encoding="utf-8"))
            self.assertIs(saved["passed"], False)
            self.assertEqual(saved["failure_type"], "AssertionError")


if __name__ == "__main__":
    unittest.main()
