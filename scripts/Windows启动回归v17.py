"""Unit tests for a CI-only launcher experiment, not Windows acceptance."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch


def load(filename, name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


medium = load("Windows非提升进程v12.py", "flags_v17")


class LaunchFlagsTests(unittest.TestCase):
    def test_detached_console_preserves_suspend_unicode_and_owned_group(self):
        self.assertEqual(medium.NATIVE_CREATION_FLAGS, 0x4 | 0x8 | 0x200 | 0x400)
        for forbidden in (0x10, 0x08000000, 0x01000000, 0x02000000):
            self.assertEqual(medium.NATIVE_CREATION_FLAGS & forbidden, 0)


class SameContextSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.smoke = load("Windows启动对照v17.py", "smoke_v17")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name) / "启动对照v17.json"
        self.process = Mock()
        self.process.wait.return_value = 0
        self.process.security = {"parent": {"elevated": True, "integrity_rid": 12288},
            "child": {"elevated": False, "integrity_rid": 8192}, "owned_job": True}
        self.stack = []
        for context in (patch.object(self.smoke.sys, "platform", "win32"),
                        patch.dict(os.environ, {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted",
                            "GITHUB_REPOSITORY": "Eswink/coding-tools-mcp", "GITHUB_SHA": "b" * 40}),
                        patch.object(self.smoke.medium, "launch", return_value=self.process)):
            self.stack.append(context.start())
            self.addCleanup(context.stop)

    def data(self): return json.loads(self.output.read_text(encoding="utf-8"))

    def test_success_requires_medium_token_and_zero_exit(self):
        self.smoke.run(self.output)
        self.assertIs(self.data()["passed"], True)
        self.assertIs(self.data()["real_interactive_window_created"], True)
        self.process.wait.assert_called_once_with(15)
        self.process.terminate_tree.assert_called_once()

    def test_native_exit_is_exact_and_never_counted_as_pass(self):
        self.process.wait.return_value = 0xc0000142
        with self.assertRaisesRegex(RuntimeError, "0xc0000142"): self.smoke.run(self.output)
        self.assertEqual(self.data()["exit_code"], 0xc0000142)
        self.assertIs(self.data()["passed"], False)
        self.assertIs(self.data()["real_interactive_window_created"], False)
        self.process.terminate_tree.assert_called_once()

    def test_cleanup_error_cannot_overwrite_primary_exit(self):
        self.process.wait.return_value = 0xc0000142
        self.process.terminate_tree.side_effect = OSError("cleanup-canary")
        with self.assertRaisesRegex(RuntimeError, "0xc0000142"): self.smoke.run(self.output)
        self.assertIs(self.data()["passed"], False)
        self.assertEqual(self.data()["cleanup_failure_type"], "OSError")
        self.assertNotIn("cleanup-canary", self.output.read_text(encoding="utf-8"))

    def test_cleanup_error_after_success_still_fails(self):
        self.process.terminate_tree.side_effect = OSError("cleanup-canary")
        with self.assertRaises(OSError): self.smoke.run(self.output)
        self.assertIs(self.data()["passed"], False)

    def test_elevated_child_is_rejected(self):
        self.process.security["child"]["elevated"] = True
        with self.assertRaises(RuntimeError): self.smoke.run(self.output)
        self.assertIs(self.data()["passed"], False)
        self.process.terminate_tree.assert_called_once()

    def test_not_for_user_machines(self):
        with patch.dict(os.environ, {"RUNNER_ENVIRONMENT": "self-hosted"}):
            with self.assertRaises(RuntimeError): self.smoke.run(self.output)
        self.stack[-1].assert_not_called()
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
