"""Adapter contract tests, not claims of native GUI execution."""
import importlib.util
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("adapter_test_v8", Path(__file__).with_name("跨平台原生驱动v8.py"))
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)

class AdapterTests(unittest.TestCase):
    def test_windows_capabilities_target_real_application(self):
        path = Path("C:/fixture/app.exe")
        cap = adapter.windows_capabilities(path)["capabilities"]["alwaysMatch"]
        self.assertEqual(cap["browserName"], "webview2")
        self.assertEqual(cap["ms:edgeOptions"]["binary"], str(path))
        self.assertEqual(cap["ms:edgeOptions"]["args"], [])
        self.assertNotIn("acceptInsecureCerts", cap)

    def test_windows_refuses_user_machine_and_outside_fixture(self):
        with patch.object(adapter.sys, "platform", "win32"), patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError): adapter.fixture_root(SimpleNamespace())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "fixture"; root.mkdir()
            env = {"GITHUB_ACTIONS":"true", "RUNNER_ENVIRONMENT":"github-hosted",
                   "GITHUB_REPOSITORY":"Eswink/coding-tools-mcp", "RUNNER_TEMP":tmp}
            with patch.object(adapter.sys, "platform", "win32"), patch.dict(os.environ, env, clear=True):
                with self.assertRaises(RuntimeError): adapter.fixture_root(SimpleNamespace(fixture_root=root))
                (root / ".chat-native-fixture-v8").touch()
                self.assertEqual(adapter.fixture_root(SimpleNamespace(fixture_root=root)), root.resolve())
                with self.assertRaises(RuntimeError): adapter.fixture_root(SimpleNamespace(fixture_root=Path(tmp)))
                with self.assertRaises(RuntimeError): adapter.fixture_root(SimpleNamespace(fixture_root=Path(tmp).parent))

    def test_backend_selection_is_platform_bound(self):
        with patch.object(adapter.sys, "platform", "win32"), patch.object(adapter, "WindowsNativeSession", return_value="native-windows") as win:
            self.assertEqual(adapter.session("app", "driver", "out", 1), "native-windows")
            win.assert_called_once_with("app", "driver", "out", 1)
        with patch.object(adapter.sys, "platform", "linux"), patch.object(adapter.gui, "NativeSession", return_value="native-linux") as lin:
            self.assertEqual(adapter.session("app", "driver", "out", 1), "native-linux")
            lin.assert_called_once_with("app", "driver", "out", 1)

if __name__ == "__main__": unittest.main()
