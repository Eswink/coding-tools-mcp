#!/usr/bin/env python3
"""S2 acceptance tests for gateway ops console (stdlib unittest)."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ops_console.bind import BindError, assert_loopback_bind, parse_bind  # noqa: E402
from ops_console import config_api, devices  # noqa: E402
from ops_console.paths import PathError, ensure_workspace_root  # noqa: E402
from ops_console.secrets_filter import strip_secrets  # noqa: E402


class BindTests(unittest.TestCase):
    def test_loopback_ok(self):
        h, p = parse_bind("127.0.0.1:18765")
        self.assertEqual(h, "127.0.0.1")
        self.assertEqual(p, 18765)

    def test_reject_0_0_0_0(self):
        with self.assertRaises(BindError) as cm:
            parse_bind("0.0.0.0:18765")
        self.assertEqual(cm.exception.code, "bind_must_be_loopback")

    def test_reject_public(self):
        with self.assertRaises(BindError):
            assert_loopback_bind("8.8.8.8", 80)

    def test_server_startup_non_loopback_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [sys.executable, str(ROOT / "server.py"),
                 "--workspace-root", tmp,
                 "--bind", "0.0.0.0:18765"],
                capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(proc.returncode, 2)
            self.assertIn("bind_must_be_loopback", proc.stderr)


class ConfigSecretsTests(unittest.TestCase):
    def test_strip_secrets(self):
        data, stripped = strip_secrets({
            "origin": "https://x.example",
            "database_url": "postgresql://secret",
            "identity_key": "x" * 43,
        })
        self.assertEqual(data.get("origin"), "https://x.example")
        self.assertNotIn("database_url", data)
        self.assertNotIn("identity_key", data)
        self.assertIn("database_url", stripped)

    def test_put_rejects_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = ensure_workspace_root(tmp)
            with self.assertRaises(config_api.ConfigError) as cm:
                config_api.write_config(root, "config.json", {
                    "origin": "https://gateway.example.invalid",
                    "prefix": "/coding-tools",
                    "connector": "00000000-0000-0000-0000-000000000001",
                    "owner_subject": "00000000-0000-0000-0000-000000000002",
                    "client_id": "c1",
                    "redirect_uri": "https://client.example.invalid/cb",
                    "client_authentication": "public",
                    "bind": "127.0.0.1:28880",
                    "database_url": "postgresql://nope",
                })
            self.assertEqual(cm.exception.code, "secrets_not_allowed_in_config_api")

    def test_get_put_public_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = ensure_workspace_root(tmp)
            payload = {
                "origin": "https://gateway.example.invalid",
                "prefix": "/coding-tools",
                "connector": "00000000-0000-0000-0000-000000000001",
                "owner_subject": "00000000-0000-0000-0000-000000000002",
                "client_id": "c1",
                "redirect_uri": "https://client.example.invalid/cb",
                "client_authentication": "public",
                "bind": "127.0.0.1:28880",
            }
            w = config_api.write_config(root, "config.json", payload)
            self.assertTrue(w["ok"])
            # Plant a secret on disk and ensure GET strips it
            on_disk = json.loads((root / "config.json").read_text())
            on_disk["database_url"] = "postgresql://hidden"
            (root / "config.json").write_text(json.dumps(on_disk))
            g = config_api.read_config(root, "config.json")
            self.assertTrue(g["ok"])
            self.assertNotIn("database_url", g["data"])
            self.assertIn("database_url", g["stripped_secret_keys"])

    def test_put_rejects_non_loopback_bind(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = ensure_workspace_root(tmp)
            with self.assertRaises(config_api.ConfigError) as cm:
                config_api.write_config(root, "config.json", {
                    "origin": "https://gateway.example.invalid",
                    "prefix": "/coding-tools",
                    "connector": "00000000-0000-0000-0000-000000000001",
                    "owner_subject": "00000000-0000-0000-0000-000000000002",
                    "client_id": "c1",
                    "redirect_uri": "https://client.example.invalid/cb",
                    "client_authentication": "public",
                    "bind": "0.0.0.0:28880",
                })
            self.assertEqual(cm.exception.code, "config_bind_must_be_loopback")


class DevicesTests(unittest.TestCase):
    def test_empty_dir_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = ensure_workspace_root(tmp)
            out = devices.list_local_devices(root)
            self.assertTrue(out["ok"])
            self.assertEqual(out["items"], [])

    def test_missing_devices_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = ensure_workspace_root(tmp)
            out = devices.list_local_devices(root, "devices")
            self.assertEqual(out["items"], [])


class UiHtmlTests(unittest.TestCase):
    def test_html_has_checkbox_and_select(self):
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        self.assertIn('data-ui="enum-select"', html)
        self.assertIn("<select", html)
        self.assertIn('id="f-client_authentication"', html)
        self.assertIn('type="checkbox"', html)
        self.assertIn('data-ui="checkbox-switch"', html)
        self.assertIn("本机回环控制台 ≠ 公网 admin", html)


class HttpLiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        # pick free port
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            cls.port = s.getsockname()[1]
        cls.proc = subprocess.Popen(
            [sys.executable, str(ROOT / "server.py"),
             "--workspace-root", str(cls.root),
             "--bind", f"127.0.0.1:{cls.port}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        # wait for listen
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                c = HTTPConnection("127.0.0.1", cls.port, timeout=0.3)
                c.request("GET", "/api/v1/health")
                r = c.getresponse()
                if r.status == 200:
                    c.close()
                    break
                c.close()
            except OSError:
                time.sleep(0.05)
        else:
            cls.proc.kill()
            raise RuntimeError("server did not start: " + (cls.proc.stderr.read() if cls.proc.stderr else ""))

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        try:
            cls.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            cls.proc.kill()
        cls.tmp.cleanup()

    def _conn(self):
        return HTTPConnection("127.0.0.1", self.port, timeout=2)

    def test_health_200(self):
        c = self._conn()
        c.request("GET", "/api/v1/health")
        r = c.getresponse()
        body = json.loads(r.read().decode())
        self.assertEqual(r.status, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["service"], "gateway-ops-console")
        c.close()

    def test_devices_empty(self):
        c = self._conn()
        c.request("GET", "/api/v1/devices/local")
        r = c.getresponse()
        body = json.loads(r.read().decode())
        self.assertEqual(r.status, 200)
        self.assertEqual(body["items"], [])
        c.close()

    def test_config_put_get(self):
        payload = {
            "data": {
                "origin": "https://gateway.example.invalid",
                "prefix": "/coding-tools",
                "connector": "00000000-0000-0000-0000-000000000001",
                "owner_subject": "00000000-0000-0000-0000-000000000002",
                "client_id": "c1",
                "redirect_uri": "https://client.example.invalid/cb",
                "client_authentication": "public",
                "bind": "127.0.0.1:28880",
            }
        }
        c = self._conn()
        body = json.dumps(payload).encode()
        c.request("PUT", "/api/v1/config?path=config.json", body=body, headers={
            "Content-Type": "application/json",
            "X-Ops-Console": "1",
            "Content-Length": str(len(body)),
        })
        r = c.getresponse()
        put_body = json.loads(r.read().decode())
        self.assertEqual(r.status, 200, put_body)
        self.assertTrue(put_body["ok"])
        c.close()

        c = self._conn()
        c.request("GET", "/api/v1/config?path=config.json")
        r = c.getresponse()
        get_body = json.loads(r.read().decode())
        self.assertTrue(get_body["ok"])
        self.assertEqual(get_body["data"]["client_id"], "c1")
        self.assertNotIn("database_url", get_body["data"])
        c.close()

    def test_csrf_guard(self):
        c = self._conn()
        body = json.dumps({"data": {"origin": "https://x.invalid"}}).encode()
        c.request("PUT", "/api/v1/config?path=config.json", body=body, headers={
            "Content-Type": "application/json",
            "Content-Length": str(len(body)),
        })
        r = c.getresponse()
        data = json.loads(r.read().decode())
        self.assertEqual(r.status, 403)
        self.assertEqual(data["error"], "ops_csrf_guard")
        c.close()

    def test_index_html_served(self):
        c = self._conn()
        c.request("GET", "/")
        r = c.getresponse()
        html = r.read().decode()
        self.assertEqual(r.status, 200)
        self.assertIn("checkbox", html)
        self.assertIn("<select", html)
        c.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
