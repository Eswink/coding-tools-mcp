#!/usr/bin/env python3
"""Gateway Ops Console HTTP server (S2) — loopback only, stdlib.

Loopback operator console ≠ public HTTP administrator surface.
Usage:
  python3 server.py --workspace-root /abs/path [--bind 127.0.0.1:18765]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from ops_console.bind import (  # noqa: E402
    DEFAULT_HOST,
    DEFAULT_PORT,
    BindError,
    assert_loopback_bind,
    parse_bind,
)
from ops_console import cli_wrap, config_api, devices, kit_preview  # noqa: E402
from ops_console.paths import PathError, ensure_workspace_root  # noqa: E402

STATIC_DIR = HERE / "static"
CSRF_HEADER = "X-Ops-Console"
CSRF_VALUE = "1"


class AppState:
    def __init__(self, workspace_root: Path, bind_host: str, bind_port: int, gateway_bin: Optional[str]):
        self.workspace_root = workspace_root
        self.bind_host = bind_host
        self.bind_port = bind_port
        self.gateway_bin = gateway_bin


STATE: Optional[AppState] = None


def json_bytes(obj: Any, status: int = 200) -> Tuple[int, bytes, str]:
    return status, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8"


def err(code: str, status: int = 400) -> Tuple[int, bytes, str]:
    return json_bytes({"ok": False, "error": code}, status=status)


class OpsHandler(BaseHTTPRequestHandler):
    server_version = "GatewayOpsConsole/0.1-s2"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _read_json(self) -> Any:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            return None
        if length > 1_000_000:
            raise ValueError("body_too_large")
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def _csrf_ok(self) -> bool:
        return self.headers.get(CSRF_HEADER) == CSRF_VALUE

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        # Remind clients this is loopback ops, not public admin
        self.send_header("X-Ops-Console-Surface", "loopback-only")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        try:
            self._dispatch_get()
        except Exception as exc:  # noqa: BLE001
            self._handle_exc(exc)

    def do_PUT(self) -> None:  # noqa: N802
        try:
            self._dispatch_write("PUT")
        except Exception as exc:  # noqa: BLE001
            self._handle_exc(exc)

    def do_POST(self) -> None:  # noqa: N802
        try:
            self._dispatch_write("POST")
        except Exception as exc:  # noqa: BLE001
            self._handle_exc(exc)

    def _handle_exc(self, exc: BaseException) -> None:
        if isinstance(exc, (BindError, PathError, config_api.ConfigError, kit_preview.KitPreviewError, cli_wrap.CliError)):
            code = getattr(exc, "code", str(exc))
            status, body, ctype = err(code, 400)
            self._send(status, body, ctype)
            return
        if isinstance(exc, json.JSONDecodeError):
            status, body, ctype = err("invalid_json", 400)
            self._send(status, body, ctype)
            return
        traceback.print_exc()
        status, body, ctype = err("internal_error", 500)
        self._send(status, body, ctype)

    def _dispatch_get(self) -> None:
        assert STATE is not None
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            return self._serve_static("index.html", "text/html; charset=utf-8")
        if path.startswith("/assets/"):
            name = path[len("/assets/"):]
            if ".." in name or name.startswith("/"):
                status, body, ctype = err("path_escape_denied", 400)
                return self._send(status, body, ctype)
            # map /assets/x -> static/x
            ctype = "application/octet-stream"
            if name.endswith(".js"):
                ctype = "application/javascript; charset=utf-8"
            elif name.endswith(".css"):
                ctype = "text/css; charset=utf-8"
            return self._serve_static(name, ctype)

        if path == "/api/v1/health":
            status, body, ctype = json_bytes({
                "ok": True,
                "service": "gateway-ops-console",
                "bind": f"{STATE.bind_host}:{STATE.bind_port}",
                "note": "loopback operator console ≠ public admin",
            })
            return self._send(status, body, ctype)

        if path == "/api/v1/config":
            rel = (qs.get("path") or ["config.json"])[0]
            payload = config_api.read_config(STATE.workspace_root, rel)
            status, body, ctype = json_bytes(payload)
            return self._send(status, body, ctype)

        if path == "/api/v1/devices/local":
            payload = devices.list_local_devices(STATE.workspace_root)
            status, body, ctype = json_bytes(payload)
            return self._send(status, body, ctype)

        if path == "/api/v1/gateway-listen":
            # Optional: read config bind and TCP-connect loopback only
            listening = False
            bind_s = None
            reason = None
            try:
                cfg = config_api.read_config(STATE.workspace_root, "config.json")
                bind_s = cfg["data"].get("bind")
                if not bind_s:
                    reason = "config_missing_bind"
                else:
                    host, port = parse_bind(str(bind_s))
                    import socket
                    with socket.socket(socket.AF_INET if ":" not in host or host.count(":") == 1 and "." in host else socket.AF_INET6) as sock:
                        sock.settimeout(0.3)
                        listening = sock.connect_ex((host if host != "::1" else "127.0.0.1", port)) == 0
            except PathError as pe:
                if pe.code == "path_not_found":
                    reason = "config_missing"
                else:
                    raise
            except BindError:
                status, body, ctype = err("target_must_be_loopback", 400)
                return self._send(status, body, ctype)
            status, body, ctype = json_bytes({
                "ok": True,
                "listening": listening,
                "bind": bind_s,
                **({"reason": reason} if reason else {}),
            })
            return self._send(status, body, ctype)

        # Denied surfaces
        if path.startswith("/api/v1/devices/db") or path.startswith("/api/v1/devices/") and path != "/api/v1/devices/local":
            status, body, ctype = err("db_device_list_not_in_v1", 404)
            return self._send(status, body, ctype)

        status, body, ctype = err("not_found", 404)
        self._send(status, body, ctype)

    def _dispatch_write(self, method: str) -> None:
        assert STATE is not None
        if not self._csrf_ok():
            status, body, ctype = err("ops_csrf_guard", 403)
            return self._send(status, body, ctype)
        ctype_hdr = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype_hdr and ctype_hdr != "application/json":
            status, body, ctype = err("ops_csrf_guard", 403)
            return self._send(status, body, ctype)

        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        body_obj = self._read_json()

        if method == "PUT" and path == "/api/v1/config":
            rel = (qs.get("path") or ["config.json"])[0]
            if not isinstance(body_obj, dict) or "data" not in body_obj:
                status, body, ctype = err("invalid_json", 400)
                return self._send(status, body, ctype)
            payload = config_api.write_config(STATE.workspace_root, rel, body_obj["data"])
            status, body, ctype = json_bytes(payload)
            return self._send(status, body, ctype)

        if method == "POST" and path == "/api/v1/kit/preview":
            if not isinstance(body_obj, dict):
                status, body, ctype = err("invalid_json", 400)
                return self._send(status, body, ctype)
            action = body_obj.get("action") or "plan"
            if action == "plan":
                payload = kit_preview.run_kit_plan()
            elif action == "render_diff":
                opts = body_obj.get("options") or {}
                payload = kit_preview.run_kit_render_diff(
                    STATE.workspace_root,
                    private_root_rel=body_obj.get("private_root_rel") or ".",
                    domain=str(opts.get("domain") or "gateway.example.invalid"),
                    connector=str(opts.get("connector") or "00000000-0000-0000-0000-000000000001"),
                    port=int(opts.get("port") or 28880),
                )
            else:
                status, body, ctype = err("kit:unknown_action", 400)
                return self._send(status, body, ctype)
            status, body, ctype = json_bytes(payload)
            return self._send(status, body, ctype)

        if method == "POST" and path == "/api/v1/cli/check-config":
            if not isinstance(body_obj, dict):
                status, body, ctype = err("invalid_json", 400)
                return self._send(status, body, ctype)
            payload = cli_wrap.check_config(
                STATE.workspace_root,
                body_obj.get("config_rel") or "config.json",
                gateway_bin=STATE.gateway_bin,
            )
            status, body, ctype = json_bytes(payload)
            return self._send(status, body, ctype)

        if method == "POST" and path == "/api/v1/cli/register-client":
            if not isinstance(body_obj, dict):
                status, body, ctype = err("invalid_json", 400)
                return self._send(status, body, ctype)
            if not body_obj.get("secrets_file_rel"):
                status, body, ctype = err("secrets_file_required", 400)
                return self._send(status, body, ctype)
            payload = cli_wrap.register_client(
                STATE.workspace_root,
                body_obj.get("config_rel") or "config.json",
                body_obj["secrets_file_rel"],
                gateway_bin=STATE.gateway_bin,
            )
            status, body, ctype = json_bytes(payload)
            return self._send(status, body, ctype)

        if method == "POST" and path == "/api/v1/cli/invite-device":
            if not isinstance(body_obj, dict):
                status, body, ctype = err("invalid_json", 400)
                return self._send(status, body, ctype)
            if not body_obj.get("secrets_file_rel"):
                status, body, ctype = err("secrets_file_required", 400)
                return self._send(status, body, ctype)
            payload = cli_wrap.invite_device(
                STATE.workspace_root,
                body_obj.get("config_rel") or "config.json",
                body_obj["secrets_file_rel"],
                body_obj.get("output_rel") or "devices/invitation.json",
                gateway_bin=STATE.gateway_bin,
            )
            status, body, ctype = json_bytes(payload)
            return self._send(status, body, ctype)

        # Denied CLI / capabilities
        denied_map = {
            "/api/v1/cli/migrate": "cli_not_enabled_in_v1",
            "/api/v1/cli/provision-owner": "cli_not_enabled_in_v1",
            "/api/v1/cli/rotate-owner": "cli_not_enabled_in_v1",
            "/api/v1/cli/serve": "cli_not_enabled_in_v1",
            "/api/v1/cli/redeem-device": "cli_not_enabled_in_v1",
            "/api/v1/cli/revoke-device": "cli_not_enabled_in_v1",
            "/api/v1/cli/select-device": "cli_not_enabled_in_v1",
            "/api/v1/admin": "capability_denied",
            "/api/v1/oauth/code": "capability_denied",
            "/api/v1/dcr": "capability_denied",
            "/api/v1/exec": "command_not_allowed",
        }
        if path in denied_map:
            status, body, ctype = err(denied_map[path], 404)
            return self._send(status, body, ctype)

        status, body, ctype = err("not_found", 404)
        self._send(status, body, ctype)

    def _serve_static(self, name: str, content_type: str) -> None:
        path = (STATIC_DIR / name).resolve()
        try:
            path.relative_to(STATIC_DIR.resolve())
        except ValueError:
            status, body, ctype = err("path_escape_denied", 400)
            return self._send(status, body, ctype)
        if not path.is_file():
            status, body, ctype = err("not_found", 404)
            return self._send(status, body, ctype)
        data = path.read_bytes()
        self._send(200, data, content_type)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--workspace-root", required=True, help="Absolute private workspace root")
    p.add_argument("--bind", default=f"{DEFAULT_HOST}:{DEFAULT_PORT}",
                   help="Must be loopback host:port (default 127.0.0.1:18765)")
    p.add_argument("--gateway-bin", default=None, help="Path to coding-tools-gateway binary")
    return p


def main(argv: Optional[list] = None) -> int:
    global STATE
    args = build_arg_parser().parse_args(argv)
    try:
        host, port = parse_bind(args.bind)
        host, port = assert_loopback_bind(host, port)
    except BindError as exc:
        print(json.dumps({"ok": False, "error": exc.code}), file=sys.stderr)
        return 2
    try:
        root = ensure_workspace_root(args.workspace_root)
    except PathError as exc:
        print(json.dumps({"ok": False, "error": exc.code}), file=sys.stderr)
        return 2

    STATE = AppState(root, host, port, args.gateway_bin)
    # Force address family for 127.0.0.1
    server = ThreadingHTTPServer((host, port), OpsHandler)
    print(json.dumps({
        "ok": True,
        "service": "gateway-ops-console",
        "bind": f"{host}:{port}",
        "workspace_root": str(root),
        "note": "loopback operator console ≠ public admin",
    }), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
