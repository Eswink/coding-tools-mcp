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
        cap = adapter.windows_capabilities(19222)["capabilities"]["alwaysMatch"]
        self.assertEqual(cap["browserName"], "webview2")
        self.assertEqual(cap["ms:edgeOptions"], {"debuggerAddress": "127.0.0.1:19222"})
        self.assertNotIn("acceptInsecureCerts", cap)
        for invalid in (0, -1, 65536, True, "9222", "remote-host:9222"):
            with self.assertRaises(ValueError): adapter.windows_capabilities(invalid)

    def test_debugging_is_child_local_and_never_disables_sandbox(self):
        original = {"PATH":"canary-path", "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS":"old-flags"}
        with patch.dict(os.environ, original, clear=True):
            child = adapter.webview_environment(19222, Path(tempfile.gettempdir()).resolve())
            self.assertEqual(dict(os.environ), original)
            self.assertEqual(child["PATH"], "canary-path")
            self.assertEqual(child["WEBVIEW2_USER_DATA_FOLDER"], str(Path(tempfile.gettempdir()).resolve()))
            self.assertEqual(child["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"],
                             "--remote-debugging-port=19222")
            with self.assertRaises(ValueError): adapter.webview_environment(19222, Path("relative"))

    def test_close_stops_both_owned_processes_even_when_app_cleanup_fails(self):
        from unittest.mock import Mock
        session = adapter.WindowsNativeSession.__new__(adapter.WindowsNativeSession)
        session.log = Mock(closed=False)
        session.session = ""
        session.browser_profile = None
        session.app_process, session.process = Mock(), Mock()
        session.stop_owned_process = Mock(side_effect=[RuntimeError("fixture cleanup failure"), None])
        with self.assertRaises(RuntimeError): session.close()
        self.assertEqual(session.stop_owned_process.call_args_list[0].args, (session.app_process,))
        self.assertEqual(session.stop_owned_process.call_args_list[1].args, (session.process,))
        session.log.close.assert_called_once()

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

    def test_debug_listener_requires_owned_loopback_endpoint(self):
        snapshot = {"processes": [{"id": 12}], "listeners": [{"process": 12, "port": 19222, "address": "127.0.0.1"}]}
        adapter.verify_debug_listener(snapshot, 19222)
        for changes in [{"address": "0.0.0.0"}, {"address": "::"}, {"process": 99}, {"port": 19223}]:
            wrong = {**snapshot, "listeners": [{**snapshot["listeners"][0], **changes}]}
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                adapter.verify_debug_listener(wrong, 19222)
        with self.assertRaises(ValueError): adapter.verify_debug_listener({}, 19222)

    def test_backend_selection_is_platform_bound(self):
        with patch.object(adapter.sys, "platform", "win32"), patch.object(adapter, "WindowsNativeSession", return_value="native-windows") as win:
            self.assertEqual(adapter.session("app", "driver", "out", 1), "native-windows")
            win.assert_called_once_with("app", "driver", "out", 1)
        with patch.object(adapter.sys, "platform", "linux"), patch.object(adapter.gui, "NativeSession", return_value="native-linux") as lin:
            self.assertEqual(adapter.session("app", "driver", "out", 1), "native-linux")
            lin.assert_called_once_with("app", "driver", "out", 1)

if __name__ == "__main__": unittest.main()
