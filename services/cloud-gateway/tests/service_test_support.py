"""Disposable process/TLS fixtures. Never accepts a production DSN or existing cluster."""
import base64
from contextlib import contextmanager
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import select
import socket
import ssl
import subprocess
import tempfile
import threading
from urllib.parse import parse_qs, urlsplit
import uuid


def require(value, name):
    if not value:
        raise RuntimeError(name)  # Fixed case name, never request bodies/URLs/credentials.


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def private_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")
    path.chmod(0o600)
    return path


class Fixture:
    def __init__(self, root, pg, binary, pg_lib=None):
        self.root, self.pg, self.binary = root, pg, binary
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith("PG") and k not in ("DATABASE_URL", "TEST_DATABASE_URL")}
        self.pg_env = dict(self.env)
        if pg_lib:
            self.pg_env["LD_LIBRARY_PATH"] = str(pg_lib)
        self.port = free_port()
        self.cluster = root / "cluster"
        self.running = False
        self.process = None
        self.process_logs = []
        self.callbacks = []
        self.upstream = 0
        self.password = secrets.token_urlsafe(32)
        self.packet = {"database_url": f"postgresql://gateway_test@127.0.0.1:{self.port}/coding_tools_identity_test",
                       "identity_key": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")}
        self.config = root / "config.json"
        self.secret_file = private_json(root / "service-secrets.json", self.packet)
        self.config_data = None

    def pg_command(self, name, *args):
        r = subprocess.run([str(self.pg / name), *map(str, args)], env=self.pg_env,
                           capture_output=True, timeout=30, check=False)
        require(r.returncode == 0, "disposable_postgres_" + name)
        return r.stdout

    def init(self):
        self.pg_command("initdb", "-D", self.cluster, "-A", "trust", "-U", "gateway_test",
                        "--encoding=UTF8", "--no-locale")
        self.pg_start()
        self.pg_command("createdb", "-h", "127.0.0.1", "-p", self.port,
                        "-U", "gateway_test", "coding_tools_identity_test")

    def pg_start(self):
        self.pg_command("pg_ctl", "-D", self.cluster, "-l", self.root / "postgres.log",
                        "-o", f"-h 127.0.0.1 -p {self.port} -k {self.root}", "-w", "start")
        self.running = True

    def pg_stop(self):
        self.pg_command("pg_ctl", "-D", self.cluster, "-m", "fast", "-w", "stop")
        self.running = False

    def sql(self, query):
        return self.pg_command("psql", "-h", "127.0.0.1", "-p", self.port, "-U", "gateway_test",
                               "-d", "coding_tools_identity_test", "-At", "-v", "ON_ERROR_STOP=1",
                               "-c", query).decode().strip()

    def setup_config(self, origin, callback):
        self.config_data = {"origin": origin, "prefix": "/coding-tools", "connector": str(uuid.uuid4()),
                            "owner_subject": str(uuid.uuid4()), "client_id": "browser-test",
                            "redirect_uri": callback, "client_authentication": "public", "bind": "127.0.0.1:0"}
        private_json(self.config, self.config_data)

    def invoke(self, command, *, packet=None, expected=True, config=None, extra=()):
        args = [str(self.binary), command, "--config", str(config or self.config)]
        if command != "check-config":
            args.append("--secrets-stdin")
        r = subprocess.run([*args, *extra], input=json.dumps(packet or self.packet).encode(),
                           env=self.env, capture_output=True, timeout=15)
        require((r.returncode == 0) == expected, "cli_" + command)
        self.check_logs(r.stdout + r.stderr)
        return json.loads((r.stdout if expected else r.stderr).decode())

    def check_logs(self, output):
        for raw in (self.password, self.packet["identity_key"], self.packet["database_url"]):
            require(raw.encode() not in output, "credential_not_logged")

    def start(self, *, files=False):
        args = [str(self.binary), "serve", "--config", str(self.config)]
        args += ["--secrets-file", str(self.secret_file)] if files else ["--secrets-stdin"]
        p = subprocess.Popen(args, env=self.env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.process = p
        if not files:
            p.stdin.write(json.dumps(self.packet).encode())
        p.stdin.close()
        readable, _, _ = select.select([p.stdout], [], [], 12)
        require(readable, "service_start_deadline")
        line = p.stdout.readline()
        require(line, "service_ready_line")
        result = json.loads(line)
        require(result["status"] == "ready" and result["mode"] == "identity_only", "service_ready")
        self.upstream = int(result["listen"].rsplit(":", 1)[1])
        self.check_logs(line)

    def stop(self):
        if self.process:
            p, self.process = self.process, None
            p.terminate()
            try:
                p.wait(timeout=12)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait(timeout=5)
                raise RuntimeError("service_stop_deadline")
            output = p.stdout.read() + p.stderr.read()
            self.check_logs(output)
            require(p.returncode == 0 and b'"stopped"' in output, "graceful_stop")

    def http(self, method, path, data=None, headers=None):
        h = {"Host": urlsplit(self.config_data["origin"]).netloc}
        h.update(headers or {})
        c = http.client.HTTPConnection("127.0.0.1", self.upstream, timeout=8)
        try:
            c.request(method, path, body=data, headers=h)
            r = c.getresponse()
            return r.status, dict(r.getheaders()), r.read()
        finally:
            c.close()


@contextmanager
def disposable_fixture(pg, binary, pg_lib=None):
    require(not hasattr(os, "geteuid") or os.geteuid() != 0, "run_disposable_database_as_nonroot")
    with tempfile.TemporaryDirectory(prefix="ctm-service-") as directory:
        f = Fixture(Path(directory).resolve(), pg, binary, pg_lib)
        try:
            f.init()
            yield f
        finally:
            try:
                f.stop()
            finally:
                if f.running:
                    f.pg_stop()


@contextmanager
def tls_proxy(f):
    """Only ephemeral loopback origins; forwards no traffic to the user's domain."""
    cert, key = f.root / "cert.pem", f.root / "key.pem"
    result = subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                             "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1",
                             "-keyout", str(key), "-out", str(cert)], capture_output=True, timeout=20)
    require(result.returncode == 0, "test_tls_certificate")
    key.chmod(0o600)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def route(self):
            parsed = urlsplit(self.path)
            if parsed.path == "/callback":
                f.callbacks.append(parse_qs(parsed.query))
                body = b"<!doctype html><title>Test callback</title><p>Callback captured in test memory.</p>"
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Content-Type", "text/html")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return
            if parsed.path == "/attacker":
                body = b"<!doctype html><title>Test attacker</title><body>Cross-origin fixture</body>"
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(body)
                return
            h = {k: v for k, v in self.headers.items() if k.lower() not in ("connection", "host", "transfer-encoding")}
            h["Host"] = urlsplit(f.config_data["origin"]).netloc
            data = self.rfile.read(int(self.headers.get("Content-Length", "0"))) if self.command == "POST" else None
            conn = http.client.HTTPConnection("127.0.0.1", f.upstream, timeout=10)
            try:
                conn.request(self.command, self.path, data, h)
                r = conn.getresponse()
                body = r.read()
                self.send_response(r.status)
                for k, v in r.getheaders():
                    if k.lower() not in ("connection", "transfer-encoding", "content-length", "server", "date"):
                        self.send_header(k, v)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            finally:
                conn.close()
        do_GET = route
        do_POST = route

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert, key)
    server.socket = ctx.wrap_socket(server.socket, server_side=True)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"https://127.0.0.1:{port}", f"https://localhost:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
