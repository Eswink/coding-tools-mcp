"""Deterministic local fault proxy for ChatGPT MCP host-behavior experiments.

This is an isolated test harness. It never writes application configuration and it
never logs request headers or request bodies. OAuth endpoints always pass through;
allowlisted modes only alter /mcp behavior.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import threading
from urllib.parse import urlsplit

MAX_BODY_BYTES = 2 * 1024 * 1024
UPSTREAM_TIMEOUT_SECONDS = 15
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}
MODES = ("pass", "mcp-503", "workspace-offline", "reset-mcp")
AUTH_TOOLS = {"auth_status", "request_chat_authorization"}


@dataclass(frozen=True)
class Upstream:
    scheme: str
    host: str
    port: int
    base_path: str

    @classmethod
    def parse(cls, value: str) -> "Upstream":
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("upstream scheme must be http or https")
        if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("upstream must be an origin or path without credentials/query/fragment")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        return cls(parsed.scheme, parsed.hostname, port, parsed.path.rstrip("/"))

    def target(self, path: str) -> str:
        if not path.startswith("/"):
            raise ValueError("request path must be absolute")
        return f"{self.base_path}{path}" or "/"


class EvidenceWriter:
    def __init__(self, path: Path | None):
        self.path = path
        self._lock = threading.Lock()

    def write(self, **fields: object) -> None:
        if self.path is None:
            return
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **fields,
        }
        payload = json.dumps(record, ensure_ascii=False, sort_keys=True)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(payload + "\n")


@dataclass(frozen=True)
class ProxyConfig:
    upstream: Upstream
    mode: str
    evidence: EvidenceWriter


class ConnectorFaultProxy(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], config: ProxyConfig):
        super().__init__(address, ConnectorFaultHandler)
        self.config = config


class ConnectorFaultHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "ConnectorFaultProxy/1"
    sys_version = ""

    @property
    def config(self) -> ProxyConfig:
        return self.server.config  # type: ignore[attr-defined]

    def log_message(self, _format: str, *_args: object) -> None:
        # Avoid default request logging in case future URLs contain sensitive query data.
        return

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        self._handle()

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        self._handle()

    def _handle(self) -> None:
        body = self._read_body()
        if body is None:
            return
        path_only = self.path.split("?", 1)[0]
        if path_only == "/mcp":
            if self.config.mode == "mcp-503":
                self._mcp_503(body)
                return
            if self.config.mode == "reset-mcp":
                self._reset_mcp(body)
                return
            if self.config.mode == "workspace-offline" and self.command == "POST":
                intercepted = self._workspace_offline(body)
                if intercepted:
                    return
        self._proxy(body)

    def _read_body(self) -> bytes | None:
        transfer_encoding = self.headers.get("Transfer-Encoding", "").strip().lower()
        if transfer_encoding:
            if transfer_encoding != "chunked":
                self._send_json(400, {"error": "unsupported_transfer_encoding"})
                return None
            return self._read_chunked_body()
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            return b""
        try:
            length = int(raw_length)
        except ValueError:
            self._send_json(400, {"error": "invalid_content_length"})
            return None
        if length < 0 or length > MAX_BODY_BYTES:
            self._send_json(413, {"error": "request_body_too_large"})
            return None
        return self.rfile.read(length)

    def _read_chunked_body(self) -> bytes | None:
        chunks: list[bytes] = []
        total = 0
        while True:
            line = self.rfile.readline(128)
            if not line or len(line) >= 128 or not line.endswith(b"\r\n"):
                self._send_json(400, {"error": "invalid_chunked_body"})
                return None
            size_text = line[:-2].split(b";", 1)[0].strip()
            try:
                size = int(size_text, 16)
            except ValueError:
                self._send_json(400, {"error": "invalid_chunked_body"})
                return None
            if size < 0 or total + size > MAX_BODY_BYTES:
                self._send_json(413, {"error": "request_body_too_large"})
                return None
            if size == 0:
                # Consume trailers without retaining or logging them.
                while True:
                    trailer = self.rfile.readline(8192)
                    if trailer in {b"\r\n", b""}:
                        break
                    if len(trailer) >= 8192:
                        self._send_json(400, {"error": "invalid_chunked_body"})
                        return None
                break
            chunk = self.rfile.read(size)
            if len(chunk) != size or self.rfile.read(2) != b"\r\n":
                self._send_json(400, {"error": "invalid_chunked_body"})
                return None
            chunks.append(chunk)
            total += size
        return b"".join(chunks)

    def _mcp_503(self, body: bytes) -> None:
        self.config.evidence.write(
            mode=self.config.mode,
            method=self.command,
            path="/mcp",
            outcome="injected_http_503",
            body_bytes=len(body),
        )
        self._send_json(
            503,
            {
                "error": "connector_test_unavailable",
                "retryable": True,
                "test_harness": True,
            },
        )

    def _reset_mcp(self, body: bytes) -> None:
        self.config.evidence.write(
            mode=self.config.mode,
            method=self.command,
            path="/mcp",
            outcome="injected_connection_reset",
            body_bytes=len(body),
        )
        try:
            self.connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.connection.close()
        self.close_connection = True

    def _workspace_offline(self, body: bytes) -> bool:
        try:
            request = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False
        if not isinstance(request, dict) or request.get("method") != "tools/call":
            return False
        params = request.get("params")
        name = params.get("name") if isinstance(params, dict) else None
        if not isinstance(name, str) or name in AUTH_TOOLS:
            return False
        request_id = request.get("id")
        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": "Workspace execution is intentionally offline.",
                    }
                ],
                "structuredContent": {
                    "ok": False,
                    "code": "WORKSPACE_OFFLINE",
                    "retryable": False,
                    "user_action_required": False,
                },
                "isError": True,
            },
        }
        self.config.evidence.write(
            mode=self.config.mode,
            method=self.command,
            path="/mcp",
            outcome="injected_workspace_offline",
            tool=name,
            body_bytes=len(body),
        )
        self._send_json(200, response)
        return True

    def _proxy(self, body: bytes) -> None:
        upstream = self.config.upstream
        connection_type = http.client.HTTPSConnection if upstream.scheme == "https" else http.client.HTTPConnection
        connection = connection_type(upstream.host, upstream.port, timeout=UPSTREAM_TIMEOUT_SECONDS)
        headers = {
            name: value
            for name, value in self.headers.items()
            if name.lower() not in HOP_BY_HOP_HEADERS and name.lower() not in {"host", "content-length"}
        }
        if body:
            headers["Content-Length"] = str(len(body))
        target = upstream.target(self.path)
        try:
            connection.request(self.command, target, body=body or None, headers=headers)
            response = connection.getresponse()
            payload = response.read(MAX_BODY_BYTES + 1)
            if len(payload) > MAX_BODY_BYTES:
                self.config.evidence.write(
                    mode=self.config.mode,
                    method=self.command,
                    path=self.path.split("?", 1)[0],
                    outcome="upstream_response_too_large",
                    upstream_status=response.status,
                    body_bytes=len(body),
                )
                self._send_json(502, {"error": "upstream_response_too_large"})
                return
            forwarded_headers = [
                (name, value)
                for name, value in response.getheaders()
                if name.lower() not in HOP_BY_HOP_HEADERS and name.lower() != "content-length"
            ]
            self.send_response(response.status, response.reason)
            for name, value in forwarded_headers:
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if payload:
                self.wfile.write(payload)
            self.config.evidence.write(
                mode=self.config.mode,
                method=self.command,
                path=self.path.split("?", 1)[0],
                outcome="proxied",
                upstream_status=response.status,
                body_bytes=len(body),
                response_bytes=len(payload),
            )
        except (OSError, http.client.HTTPException) as error:
            self.config.evidence.write(
                mode=self.config.mode,
                method=self.command,
                path=self.path.split("?", 1)[0],
                outcome="upstream_error",
                error_type=type(error).__name__,
                body_bytes=len(body),
            )
            self._send_json(502, {"error": "upstream_unavailable", "test_harness": True})
        finally:
            connection.close()

    def _send_json(self, status: int, payload: object) -> None:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def build_server(host: str, port: int, upstream: str, mode: str, evidence: Path | None) -> ConnectorFaultProxy:
    if mode not in MODES:
        raise ValueError(f"mode must be one of: {', '.join(MODES)}")
    config = ProxyConfig(Upstream.parse(upstream), mode, EvidenceWriter(evidence))
    return ConnectorFaultProxy((host, port), config)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, required=True)
    parser.add_argument("--upstream", required=True, help="Local MCP origin, for example http://127.0.0.1:28766")
    parser.add_argument("--mode", choices=MODES, required=True)
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    if not (1 <= args.listen_port <= 65535):
        parser.error("--listen-port must be between 1 and 65535")
    try:
        server = build_server(args.listen_host, args.listen_port, args.upstream, args.mode, args.evidence)
    except ValueError as error:
        parser.error(str(error))
    host, port = server.server_address[:2]
    print(json.dumps({
        "ready": True,
        "listen": f"http://{host}:{port}",
        "mode": args.mode,
        "upstream": f"{server.config.upstream.scheme}://{server.config.upstream.host}:{server.config.upstream.port}{server.config.upstream.base_path}",
        "evidence": str(args.evidence) if args.evidence else None,
        "secrets_logged": False,
    }, ensure_ascii=False), flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
