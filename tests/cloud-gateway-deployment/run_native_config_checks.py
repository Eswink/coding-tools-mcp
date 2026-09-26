#!/usr/bin/env python3
"""Validate blueprints with actual Compose/Nginx in a private temporary test setup.

Only `compose config` is executed, never `up`. Nginx is a newly spawned process
on an ephemeral loopback port, not the host's installed/production service.
"""
import argparse
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("render", ROOT / "deploy/cloud-gateway/render.py")
render = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render)
CONNECTOR = "00000000-0000-0000-0000-000000000001"


class Upstream(BaseHTTPRequestHandler):
    def do_GET(self):
        response = json.dumps({"path": self.path, "host": self.headers.get("Host"),
                               "forwarded": self.headers.get("Forwarded"),
                               "xfh": self.headers.get("X-Forwarded-Host"),
                               "connection": self.headers.get("Connection"),
                               "upgrade": self.headers.get("Upgrade")}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, *_):
        pass


def request(port, path, **headers):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        conn.request("GET", path, headers={"Host": render.DEFAULT_DOMAIN, **headers})
        result = conn.getresponse()
        return result.status, result.read()
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose", type=Path, required=True)
    parser.add_argument("--nginx", type=Path, required=True)
    args = parser.parse_args()
    compose, nginx = str(args.compose.resolve(strict=True)), str(args.nginx.resolve(strict=True))
    with tempfile.TemporaryDirectory(prefix="ctm-config-") as directory:
        root = Path(directory)
        env = dict(os.environ)
        # No real registry assets or credentials are read or downloaded.
        env.update(GATEWAY_IMAGE="example.invalid/gateway@sha256:" + "0" * 64,
                   POSTGRES_IMAGE="example.invalid/postgres@sha256:" + "1" * 64)
        for key in ["GATEWAY_DATABASE_URL_FILE", "GATEWAY_IDENTITY_KEY_FILE", "POSTGRES_PASSWORD_FILE"]:
            path = root / key.lower()
            path.write_text("disposable-config-test-not-a-credential", encoding="utf-8")
            path.chmod(0o600)
            env[key] = str(path)
        config = root / "compose.blueprint.json"
        config.write_text(json.dumps(render.compose_blueprint(render.DEFAULT_DOMAIN, CONNECTOR, 28880)))
        completed = subprocess.run([compose, "-f", str(config), "--profile", "integration-pending",
                                    "config", "--format", "json"], env=env, capture_output=True,
                                   text=True, timeout=15, check=True)
        normalized = json.loads(completed.stdout)
        assert normalized["services"]["gateway"]["ports"][0]["host_ip"] == "127.0.0.1"
        assert "ports" not in normalized["services"]["postgres"]
        server = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        with socket.socket() as candidate:
            candidate.bind(("127.0.0.1", 0))
            port = candidate.getsockname()[1]
        locations = render.nginx_locations(render.DEFAULT_DOMAIN, CONNECTOR, server.server_port)
        conf = root / "nginx.conf"
        conf.write_text(f"""worker_processes 1;
error_log {root}/error.log error;
pid {root}/nginx.pid;
events {{ worker_connections 64; }}
http {{
    access_log off;
    client_body_temp_path {root}/body;
    proxy_temp_path {root}/proxy;
    fastcgi_temp_path {root}/fastcgi;
    uwsgi_temp_path {root}/uwsgi;
    scgi_temp_path {root}/scgi;
    server {{
        listen 127.0.0.1:{port};
        server_name {render.DEFAULT_DOMAIN};
        location = / {{ return 200 'existing-site'; }}
        {locations}
    }}
}}
""")
        process = None
        try:
            subprocess.run([nginx, "-t", "-p", str(root), "-c", str(conf)], env=env,
                           capture_output=True, timeout=10, check=True)
            process = subprocess.Popen([nginx, "-p", str(root), "-c", str(conf), "-g",
                                        "daemon off; master_process off;"], env=env,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(40):
                if process.poll() is not None:
                    raise RuntimeError("private Nginx test exited before readiness")
                try:
                    status, body = request(port, "/")
                    break
                except OSError:
                    time.sleep(0.05)
            else:
                raise RuntimeError("private Nginx readiness deadline")
            assert (status, body) == (200, b"existing-site")
            for path in ["/coding-tools/oauth/token",
                         "/.well-known/oauth-authorization-server/coding-tools/oauth",
                         "/.well-known/oauth-protected-resource/coding-tools/mcp/" + CONNECTOR]:
                status, body = request(port, path, Forwarded="host=foreign.invalid",
                                       **{"X-Forwarded-Host": "foreign.invalid"})
                data = json.loads(body)
                assert status == 200 and data["path"] == path
                assert data["host"] == render.DEFAULT_DOMAIN
                assert data["xfh"] is None and data["forwarded"] is None
            assert request(port, "/coding-tools/oauth/token", Host="foreign.invalid")[0] == 421
            # Header forwarding test only: this is NOT an authenticated WSS integration test.
            status, body = request(port, "/coding-tools/agent/connect", Upgrade="websocket", Connection="Upgrade")
            assert status == 200 and json.loads(body)["upgrade"] == "websocket"
            assert json.loads(body)["connection"].lower() == "upgrade"
        finally:
            if process is not None:
                process.terminate()
                process.wait(timeout=10)
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
    print(json.dumps({"compose_config": "PASS", "nginx_syntax": "PASS",
                      "nginx_loopback_http_routes": "PASS", "docker_daemon_used": False,
                      "vps_or_baota_waf_tested": False}))


if __name__ == "__main__":
    main()
