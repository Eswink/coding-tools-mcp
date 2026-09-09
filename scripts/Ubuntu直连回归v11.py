"""Native WebDriver transport contract; local HTTP fixtures are not GUI evidence."""
from __future__ import annotations
import json
from http.client import RemoteDisconnected
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import Ubuntu原生验收v1 as native


class DirectDriverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="原生直连v11-")
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)
        self.app = self.output / "中文应用 AppImage"
        self.driver = self.output / "tauri-driver"
        self.calls = []
        self.process = Mock()

    def answer(self, url, data=None, method=None, timeout=60):
        self.calls.append((url, data, method))
        if url.endswith("/status"):
            return {"value": {"ready": True}}
        if url.endswith("/session"):
            return {"value": {"sessionId": "same-native-session"}}
        if url.endswith("/execute/sync"):
            return {"value": True}
        return {"value": None}

    def start(self):
        with patch.object(native, "port", side_effect=[41230, 41231]), \
             patch.object(native.subprocess, "Popen", return_value=self.process) as spawn, \
             patch.object(native, "request", side_effect=self.answer):
            session = native.NativeSession(self.app, self.driver, self.output, 1)
        self.addCleanup(session.log.close)
        return session, spawn

    def test_all_http_requests_use_native_port(self):
        session, _ = self.start()
        self.assertEqual(session.base, "http://127.0.0.1:41231")
        self.assertTrue(self.calls)
        self.assertTrue(all(row[0].startswith(session.base + "/") for row in self.calls))
        self.assertNotIn(":41230/", " ".join(row[0] for row in self.calls))

    def test_native_capabilities_match_pinned_tauri_mapping(self):
        self.start()
        data = next(row[1] for row in self.calls if row[0].endswith("/session"))
        self.assertEqual(data, {"capabilities": {"alwaysMatch": {
            "browserName": "wry", "webkitgtk:browserOptions": {"binary": str(self.app), "args": []}}}})

    def test_tauri_driver_still_manages_native_process_group(self):
        _, spawn = self.start()
        self.assertEqual(spawn.call_args.args[0], [str(self.driver), "--port", "41230",
                        "--native-port", "41231", "--native-host", "127.0.0.1"])
        self.assertIs(spawn.call_args.kwargs["start_new_session"], True)
        self.assertNotIn("env", spawn.call_args.kwargs)  # host Python environment is inherited unchanged

    def test_session_is_created_once_and_not_refreshed(self):
        self.start()
        self.assertEqual(sum(row[0].endswith("/session") for row in self.calls), 1)
        self.assertFalse(any("refresh" in row[0] for row in self.calls))

    def test_native_post_connection_reset_is_not_replayed(self):
        session = native.NativeSession.__new__(native.NativeSession)
        session.base = "http://127.0.0.1:41231"
        session.session = "same-native-session"
        with patch.object(native, "request", side_effect=RemoteDisconnected("fixture")) as request:
            with self.assertRaises(RemoteDisconnected):
                session.call("element/item/click", {})
            request.assert_called_once_with(session.base + "/session/same-native-session/element/item/click", {}, None)

    def test_real_native_http_is_used_without_a_proxy_server(self):
        calls = []
        class Handler(BaseHTTPRequestHandler):
            def send(self, value):
                data = json.dumps({"value": value}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(data)
            def do_GET(self):
                calls.append((self.command, self.path, None))
                self.send({"ready": True})
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                calls.append((self.command, self.path, body))
                if self.path == "/session":
                    self.send({"sessionId": "fixture-native"})
                elif self.path.endswith("execute/sync"):
                    self.send(True)
                else:
                    self.send(None)
            def log_message(self, *_args):
                pass
        server = HTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        # No proxy listens at port zero. The real HTTP server is only on native_port.
        def immediate(operation, predicate=bool, timeout=30):
            value = operation()
            if not predicate(value):
                raise AssertionError("fixture not ready")
            return value
        try:
            with patch.object(native, "port", side_effect=[0, server.server_port]), \
                 patch.object(native.subprocess, "Popen", return_value=self.process), \
                 patch.object(native, "wait_for", side_effect=immediate), \
                 patch.object(native.NativeSession, "close"):
                session = native.NativeSession(self.app, self.driver, self.output, 1)
                self.addCleanup(session.log.close)
            self.assertEqual(session.session, "fixture-native")
            self.assertEqual([row[1] for row in calls], ["/status", "/session",
                             "/session/fixture-native/timeouts", "/session/fixture-native/execute/sync"])
            self.assertEqual(calls[1][2]["capabilities"]["alwaysMatch"]["webkitgtk:browserOptions"],
                             {"binary": str(self.app), "args": []})
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=3)
            self.assertFalse(worker.is_alive())


if __name__ == "__main__":
    unittest.main(verbosity=2)
