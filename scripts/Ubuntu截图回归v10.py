"""Read-only screenshot transport recovery tests; fixtures are not native GUI evidence."""
from __future__ import annotations
import base64
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from http.client import RemoteDisconnected
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, call, patch
import Ubuntu原生验收v1 as native


class ScreenshotTransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="截图回归v10-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "截图v10.png"
        self.png = b"\x89PNG\r\n\x1a\n" + b"fixture-not-native-evidence" * 250
        self.encoded = base64.b64encode(self.png).decode("ascii")
        self.session = native.NativeSession.__new__(native.NativeSession)
        self.session.call = Mock(return_value=self.encoded)
        self.pause = patch.object(native.time, "sleep").start()
        self.addCleanup(patch.stopall)

    def test_success_reads_one_screenshot(self):
        self.session.screenshot(self.path)
        self.assertEqual(self.path.read_bytes(), self.png)
        self.session.call.assert_called_once_with("screenshot")
        self.pause.assert_not_called()

    def test_disconnected_read_recovers_without_post(self):
        self.session.call.side_effect = [RemoteDisconnected("closed"), self.encoded]
        self.session.screenshot(self.path)
        self.assertEqual(self.path.read_bytes(), self.png)
        self.assertEqual(self.session.call.call_args_list, [call("screenshot")] * 2)
        self.pause.assert_called_once_with(0.25)

    def test_two_resets_recover_on_final_read(self):
        self.session.call.side_effect = [ConnectionResetError("reset"), RemoteDisconnected("closed"), self.encoded]
        self.session.screenshot(self.path)
        self.assertEqual(self.path.read_bytes(), self.png)
        self.assertEqual(self.session.call.call_args_list, [call("screenshot")] * 3)
        self.assertEqual(self.pause.call_args_list, [call(0.25), call(0.5)])

    def test_persistent_failure_is_bounded_and_does_not_write(self):
        self.session.call.side_effect = RemoteDisconnected("always closed")
        with self.assertRaises(RemoteDisconnected):
            self.session.screenshot(self.path)
        self.assertEqual(self.session.call.call_count, 3)
        self.assertEqual(self.pause.call_count, 2)
        self.assertFalse(self.path.exists())

    def test_http_error_is_not_retried(self):
        self.session.call.side_effect = RuntimeError("HTTP 500: failed")
        with self.assertRaises(RuntimeError):
            self.session.screenshot(self.path)
        self.session.call.assert_called_once_with("screenshot")
        self.pause.assert_not_called()

    def test_read_timeout_is_not_retried(self):
        self.session.call.side_effect = TimeoutError("read timeout")
        with self.assertRaises(TimeoutError):
            self.session.screenshot(self.path)
        self.assertEqual(self.session.call.call_count, 1)
        self.pause.assert_not_called()

    def test_invalid_base64_is_not_retried(self):
        self.session.call.return_value = "not base64!"
        with self.assertRaises(ValueError):
            self.session.screenshot(self.path)
        self.assertEqual(self.session.call.call_count, 1)
        self.assertFalse(self.path.exists())

    def test_invalid_png_is_not_retried(self):
        self.session.call.return_value = base64.b64encode(b"not PNG" * 1000).decode()
        with self.assertRaises(AssertionError):
            self.session.screenshot(self.path)
        self.assertEqual(self.session.call.call_count, 1)
        self.assertFalse(self.path.exists())

    def test_short_png_is_not_retried(self):
        self.session.call.return_value = base64.b64encode(b"\x89PNG\r\n\x1a\n").decode()
        with self.assertRaises(AssertionError):
            self.session.screenshot(self.path)
        self.assertEqual(self.session.call.call_count, 1)
        self.assertFalse(self.path.exists())

    def test_real_http_disconnect_recovers_same_native_session(self):
        seen = []
        encoded = self.encoded
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append((self.command, self.path))
                if len(seen) == 1:
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.connection.close()
                    return
                data = json.dumps({"value": encoded}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            def log_message(self, *_args):
                pass
        server = HTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            session = native.NativeSession.__new__(native.NativeSession)
            session.base = f"http://127.0.0.1:{server.server_port}"
            session.session = "same-fixture"
            session.screenshot(self.path)
            self.assertEqual(self.path.read_bytes(), self.png)
            self.assertEqual(seen, [("GET", "/session/same-fixture/screenshot")] * 2)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=3)
            self.assertFalse(worker.is_alive())

    def test_post_ipc_and_click_are_never_replayed(self):
        session = native.NativeSession.__new__(native.NativeSession)
        session.base, session.session = "http://127.0.0.1:12345", "fixture"
        for endpoint, payload in [("execute/async", {"script": "fixture", "args": []}),
                                  ("element/fixture/click", {})]:
            with self.subTest(endpoint=endpoint), patch.object(native, "request", side_effect=RemoteDisconnected("closed")) as request:
                with self.assertRaises(RemoteDisconnected):
                    session.call(endpoint, payload)
                request.assert_called_once()
        self.pause.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
