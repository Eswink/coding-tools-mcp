"""Contract tests for connector_fault_proxy.py; no real ChatGPT host is used."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
import sys

MODULE_PATH = Path(__file__).with_name("connector_fault_proxy.py")
spec = importlib.util.spec_from_file_location("connector_fault_proxy", MODULE_PATH)
assert spec and spec.loader
proxy = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = proxy
spec.loader.exec_module(proxy)


class UpstreamHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, _format, *_args):
        return

    def do_GET(self):  # noqa: N802
        self._reply({"path": self.path, "auth_present": bool(self.headers.get("Authorization"))})

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self._reply({
            "path": self.path,
            "auth_present": bool(self.headers.get("Authorization")),
            "body": json.loads(body or b"{}"),
        })

    def _reply(self, payload):
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class RunningServer:
    def __init__(self, server):
        self.server = server
        self.thread = threading.Thread(target=server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self.server

    def __exit__(self, *_exc):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


class FaultProxyContracts(unittest.TestCase):
    def setUp(self):
        self.upstream = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
        self.upstream_url = f"http://127.0.0.1:{self.upstream.server_port}"
        self.upstream_runner = RunningServer(self.upstream)
        self.upstream_runner.__enter__()
        self.tempdir = tempfile.TemporaryDirectory()
        self.evidence = Path(self.tempdir.name) / "evidence.jsonl"

    def tearDown(self):
        self.upstream_runner.__exit__(None, None, None)
        self.tempdir.cleanup()

    def start_proxy(self, mode):
        server = proxy.build_server("127.0.0.1", 0, self.upstream_url, mode, self.evidence)
        runner = RunningServer(server)
        runner.__enter__()
        self.addCleanup(runner.__exit__, None, None, None)
        return server

    def request(self, server, method, path, payload=None, token=None):
        body = None if payload is None else json.dumps(payload).encode()
        headers = {}
        if body is not None:
            headers["Content-Type"] = "application/json"
            headers["Content-Length"] = str(len(body))
        if token:
            headers["Authorization"] = f"Bearer {token}"
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
        finally:
            connection.close()

    def test_pass_mode_forwards_mcp_oauth_and_authorization_without_logging_secret(self):
        server = self.start_proxy("pass")
        secret = "test-secret-token-never-log"
        status, value = self.request(server, "GET", "/.well-known/oauth-authorization-server", token=secret)
        self.assertEqual(status, 200)
        self.assertTrue(value["auth_present"])
        status, value = self.request(server, "POST", "/mcp", {"jsonrpc": "2.0", "id": 1, "method": "ping"}, secret)
        self.assertEqual(status, 200)
        self.assertEqual(value["body"]["method"], "ping")
        evidence = self.evidence.read_text(encoding="utf-8")
        self.assertNotIn(secret, evidence)
        self.assertNotIn('"method": "ping"', evidence)

    def test_mcp_503_leaves_oauth_endpoint_reachable(self):
        server = self.start_proxy("mcp-503")
        status, value = self.request(server, "GET", "/mcp")
        self.assertEqual(status, 503)
        self.assertTrue(value["test_harness"])
        status, value = self.request(server, "GET", "/oauth/authorize?x=1")
        self.assertEqual(status, 200)
        self.assertEqual(value["path"], "/oauth/authorize?x=1")

    def test_workspace_offline_only_intercepts_business_tool_calls(self):
        server = self.start_proxy("workspace-offline")
        business = {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "read_file", "arguments": {"path": "x"}}}
        status, value = self.request(server, "POST", "/mcp", business)
        self.assertEqual(status, 200)
        self.assertTrue(value["result"]["isError"])
        self.assertEqual(value["result"]["structuredContent"]["code"], "WORKSPACE_OFFLINE")
        self.assertFalse(value["result"]["structuredContent"]["user_action_required"])

        auth = {"jsonrpc": "2.0", "id": 8, "method": "tools/call", "params": {"name": "auth_status", "arguments": {}}}
        status, value = self.request(server, "POST", "/mcp", auth)
        self.assertEqual(status, 200)
        self.assertEqual(value["body"]["params"]["name"], "auth_status")

        status, value = self.request(server, "POST", "/mcp", {"jsonrpc": "2.0", "id": 9, "method": "tools/list"})
        self.assertEqual(status, 200)
        self.assertEqual(value["body"]["method"], "tools/list")

    def test_workspace_offline_accepts_chunked_tool_call(self):
        server = self.start_proxy("workspace-offline")
        payload = json.dumps({
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {"name": "read_file", "arguments": {"path": "x"}},
        }).encode()
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        try:
            connection.request(
                "POST",
                "/mcp",
                body=[payload[:17], payload[17:]],
                headers={"Content-Type": "application/json"},
                encode_chunked=True,
            )
            response = connection.getresponse()
            value = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertEqual(value["result"]["structuredContent"]["code"], "WORKSPACE_OFFLINE")
        finally:
            connection.close()

    def test_reset_mcp_abruptly_closes_only_mcp_connection(self):
        server = self.start_proxy("reset-mcp")
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        try:
            connection.request("GET", "/mcp")
            with self.assertRaises((http.client.RemoteDisconnected, ConnectionResetError, OSError)):
                connection.getresponse()
        finally:
            connection.close()
        status, value = self.request(server, "GET", "/.well-known/oauth-protected-resource/mcp")
        self.assertEqual(status, 200)
        self.assertIn("oauth-protected-resource", value["path"])

    def test_upstream_parser_rejects_credentials_and_non_http_schemes(self):
        for value in ("file:///tmp/x", "http://user:pass@example.com", "http://example.com?a=1", "example.com"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                proxy.Upstream.parse(value)


if __name__ == "__main__":
    unittest.main(verbosity=2)
