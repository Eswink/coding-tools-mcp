"""Evidence regressions with fault injection; not native GUI acceptance."""
from __future__ import annotations
import contextlib
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


auth = load("auth_evidence_v16", "聊天授权原生验收v6.py")
adapter = auth.adapter


class Clock:
    def __init__(self): self.elapsed = 0.0
    def now(self): return self.elapsed
    def sleep(self, seconds): self.elapsed += seconds


class EvidenceTests(unittest.TestCase):
    def arguments(self, root):
        executable = root / "test-only.exe"
        executable.write_bytes(b"unit fixture, not an executable")
        return SimpleNamespace(executable=executable, driver=root / "driver.exe",
            output=root / "evidence", kind="native", source="a" * 40)

    def test_startup_failure_does_not_claim_ipc_oauth_or_gui_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.arguments(Path(tmp))
            with patch.object(adapter, "fixture_root", side_effect=RuntimeError("fixture unavailable")):
                with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError):
                    auth.run(args)
            data = json.loads((args.output / "聊天授权原生结果v6.json").read_text(encoding="utf-8"))
            self.assertFalse(data["passed"])
            self.assertEqual(data["tests"], [])
            for field in ("real_native_webview", "real_oauth_http", "real_local_ipc"):
                with self.subTest(field=field): self.assertIs(data[field], False)

    def test_cleanup_error_preserves_primary_failure_and_writes_evidence(self):
        class PrimaryFailure(RuntimeError): pass
        class CleanupFailure(RuntimeError): pass
        with tempfile.TemporaryDirectory() as tmp:
            args = self.arguments(Path(tmp))
            native = Mock()
            native.invoke.side_effect = PrimaryFailure("do not persist credential-canary")
            native.close.side_effect = CleanupFailure("cleanup-canary")
            with patch.object(adapter, "fixture_root", return_value=Path(tmp)), \
                 patch.object(adapter, "session", return_value=native):
                with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(PrimaryFailure):
                    auth.run(args)
            text = (args.output / "聊天授权原生结果v6.json").read_text(encoding="utf-8")
            data = json.loads(text)
            self.assertFalse(data["passed"])
            self.assertEqual(data["failure_type"], "PrimaryFailure")
            self.assertEqual(data["cleanup_failure_type"], "CleanupFailure")
            self.assertIs(data["cleanup_failed"], True)
            self.assertNotIn("credential-canary", text)
            self.assertNotIn("cleanup-canary", text)
            native.close.assert_called_once()

    def test_missing_binary_still_writes_failed_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.arguments(Path(tmp))
            args.executable.unlink()
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(FileNotFoundError):
                auth.run(args)
            data = json.loads((args.output / "聊天授权原生结果v6.json").read_text(encoding="utf-8"))
            self.assertIs(data["passed"], False)
            self.assertIs(data["binary_sha256"], None)
            self.assertEqual(data["failure_type"], "FileNotFoundError")

    def test_cleanup_failure_cannot_leave_a_success_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = {"passed": True, "tests": [{"passed": True}] * 8}
            session = Mock()
            session.close.side_effect = RuntimeError("cleanup credential-canary")
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError):
                auth.finish_evidence(Path(tmp), data, session, primary_failed=False)
            text = (Path(tmp) / "聊天授权原生结果v6.json").read_text(encoding="utf-8")
            self.assertIs(json.loads(text)["passed"], False)
            self.assertNotIn("credential-canary", text)

    def test_successful_cleanup_is_required_and_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = {"passed": True, "tests": [{"passed": True}] * 8}
            session = Mock()
            with contextlib.redirect_stdout(io.StringIO()):
                auth.finish_evidence(Path(tmp), data, session, primary_failed=False)
            saved = json.loads((Path(tmp) / "聊天授权原生结果v6.json").read_text(encoding="utf-8"))
            self.assertIs(saved["passed"], True)
            self.assertIs(saved["cleanup_completed"], True)
            session.close.assert_called_once()

    def test_host_exit_code_saved_without_claiming_product_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self.arguments(Path(tmp))
            with patch.object(adapter, "fixture_root", return_value=Path(tmp)), \
                 patch.object(adapter, "session", side_effect=adapter.NativeHostExited(0xc0000142)):
                with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(adapter.NativeHostExited):
                    auth.run(args)
            data = json.loads((args.output / "聊天授权原生结果v6.json").read_text(encoding="utf-8"))
            self.assertEqual(data["host_exit_code"], 0xc0000142)
            self.assertEqual(data["failure_stage"], "owned-python-host")
            self.assertIs(data["real_native_webview"], False)


class ReadinessTests(unittest.TestCase):
    def session(self):
        native = object.__new__(adapter.WindowsNativeSession)
        native.app_process = Mock()
        native.app_process.poll.return_value = None
        native.debug_base = "http://127.0.0.1:12345"
        return native

    def test_known_dead_host_is_not_retried_for_sixty_seconds(self):
        native, clock = self.session(), Clock()
        native.app_process.poll.return_value = 0xc0000142
        with patch.object(adapter.time, "monotonic", clock.now), \
             patch.object(adapter.time, "sleep", clock.sleep), \
             patch.object(adapter.gui, "request") as request:
            with self.assertRaisesRegex(RuntimeError, "0xc0000142"):
                native.wait_for_debug(timeout=60)
        self.assertEqual(clock.elapsed, 0)
        request.assert_not_called()

    def test_transient_connection_is_polled_without_restarting_app(self):
        native, clock = self.session(), Clock()
        ready = {"webSocketDebuggerUrl": "ws://127.0.0.1:12345/devtools/browser/test"}
        with patch.object(adapter.time, "monotonic", clock.now), \
             patch.object(adapter.time, "sleep", clock.sleep), \
             patch.object(adapter.gui, "request", side_effect=[ConnectionRefusedError(), ready]) as request:
            self.assertEqual(native.wait_for_debug(timeout=5), ready)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(clock.elapsed, 0.25)

    def test_protocol_error_is_not_retried_as_transient_failure(self):
        native, clock = self.session(), Clock()
        with patch.object(adapter.time, "monotonic", clock.now), \
             patch.object(adapter.time, "sleep", clock.sleep), \
             patch.object(adapter.gui, "request", return_value={}) as request:
            with self.assertRaises(RuntimeError): native.wait_for_debug(timeout=5)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(clock.elapsed, 0)

    def test_not_ready_has_a_finite_deadline(self):
        native, clock = self.session(), Clock()
        with patch.object(adapter.time, "monotonic", clock.now), \
             patch.object(adapter.time, "sleep", clock.sleep), \
             patch.object(adapter.gui, "request", side_effect=ConnectionRefusedError()):
            with self.assertRaises(TimeoutError): native.wait_for_debug(timeout=1)
        self.assertEqual(clock.elapsed, 1)

    def test_invalid_deadlines_rejected(self):
        native = self.session()
        for value in (0, -1, True, "60", float("nan"), float("inf"), 301):
            with self.subTest(timeout=value), self.assertRaises(ValueError):
                native.wait_for_debug(timeout=value)


if __name__ == "__main__":
    unittest.main()
