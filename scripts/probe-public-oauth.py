"""Bounded, credential-free observation of the explicitly reported public origin."""
from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path
import socket
import ssl
import urllib.error
import urllib.request

ORIGIN = "https://research-system.eswlnk.com"
LIMIT = 64 * 1024
PATHS = (
    ("GET", "/"),
    ("GET", "/mcp"),
    ("GET", "/.well-known/oauth-authorization-server"),
    ("GET", "/.well-known/oauth-protected-resource/mcp"),
    ("GET", "/.well-known/oauth-protected-resource"),
    ("POST", "/mcp"),
)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def observe(opener, method: str, path: str) -> dict:
    row = {"method": method, "path": path, "verified": False}
    body = None if method == "GET" else json.dumps({
        "jsonrpc": "2.0", "id": "public-oauth-probe", "method": "initialize", "params": {}
    }).encode()
    request = urllib.request.Request(ORIGIN + path, data=body, method=method, headers={
        "Accept": "application/json", "Content-Type": "application/json",
        "User-Agent": "coding-tools-mcp-public-diagnostic/1", "Cache-Control": "no-cache",
    })
    try:
        try:
            response = opener.open(request, timeout=8)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            status = response.code
            row["status"] = status
            mime = response.headers.get_content_type().lower()
            row["media_type"] = mime if mime in (
                "application/json", "text/html", "text/plain", "application/problem+json"
            ) else "other"
            server = response.headers.get("Server", "").lower()
            row["server_family"] = next((v for v in ("cloudflare", "nginx", "caddy", "frp") if v in server), "other")
            raw = response.read(LIMIT + 1)
            row["bytes_observed"] = len(raw)
            row["body_sha256"] = hashlib.sha256(raw).hexdigest()
            if len(raw) > LIMIT:
                row["classification"] = "response_too_large"
                return row
            try:
                value = json.loads(raw)
            except (ValueError, UnicodeError):
                value = None
            is_json = isinstance(value, dict) and mime in ("application/json", "application/problem+json")
            row["classification"] = "json_object" if is_json else "non_json_response"
            if 300 <= status < 400:
                row["classification"] = "redirect_rejected"
            if method == "POST":
                challenge = response.headers.get_all("WWW-Authenticate") or []
                expected = f'Bearer resource_metadata="{ORIGIN}/.well-known/oauth-protected-resource/mcp", scope="mcp"'
                row["challenge_present"] = bool(challenge)
                row["verified"] = status == 401 and challenge == [expected]
            elif is_json and status == 200:
                if path == "/mcp":
                    row["verified"] = value.get("name") == "coding-tools-mcp" and value.get("version") == "0.3.2"
                elif path == "/.well-known/oauth-authorization-server":
                    row["verified"] = (value.get("issuer") == ORIGIN
                        and value.get("authorization_endpoint") == ORIGIN + "/oauth/authorize"
                        and value.get("token_endpoint") == ORIGIN + "/oauth/token"
                        and "S256" in value.get("code_challenge_methods_supported", []))
                elif path.startswith("/.well-known/oauth-protected-resource"):
                    row["verified"] = (value.get("resource") == ORIGIN + "/mcp"
                        and value.get("authorization_servers") == [ORIGIN])
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
        row["classification"] = "network_or_response_error"
        row["error_type"] = type(error).__name__
    return row


def main() -> int:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    rows = [observe(opener, method, path) for method, path in PATHS]
    required = [r for r in rows if r["path"].startswith("/.well-known/") or r["method"] == "POST"]
    report = {"origin": ORIGIN, "observed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "credentials_sent": False, "redirects_followed": False,
        "public_oauth_ready": all(r["verified"] for r in required), "requests": rows}
    target = Path("evidence/public-oauth.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(target.read_text(encoding="utf-8"))
    return 0 if report["public_oauth_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
