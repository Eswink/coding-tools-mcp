"""Owned test-only TLS relay and finite certificates; no production TLS bypass."""
import json, os, select, socket, socketserver, ssl, subprocess, sys, threading, time
from pathlib import Path


def openssl(*args):
    p = subprocess.run(["openssl", *map(str, args)], capture_output=True, timeout=15)
    if p.returncode:
        raise RuntimeError("test certificate generation failed")
    return p.stdout


def certificates(root, hostname="localhost", mode="valid"):
    """Keep the unchanged relay's localhost default; mutations affect one cause."""
    if hostname not in ("localhost", "gateway.example.invalid") or mode not in (
            "valid", "untrusted_ca", "wrong_hostname", "expired"):
        raise ValueError("fixed certificate identity and mode required")
    root = Path(root).resolve(strict=True)
    ca, cakey, leaf, key, csr = [root / x for x in (
        "ca.pem", "ca.key", "leaf.pem", "leaf.key", "leaf.csr")]
    openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
            "-subj", "/CN=HostAgentFixtureCA", "-addext", "basicConstraints=critical,CA:TRUE",
            "-keyout", cakey, "-out", ca)
    openssl("req", "-new", "-newkey", "rsa:2048", "-nodes", "-subj", "/CN=" + hostname,
            "-keyout", key, "-out", csr)
    san = "wrong.example.invalid" if mode == "wrong_hostname" else hostname
    extensions = ("subjectAltName=DNS:" + san + "\nbasicConstraints=critical,CA:FALSE\n"
                  "keyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n")
    ext = root / "leaf.ext"
    ext.write_text(extensions)
    if mode == "expired":
        (root / "index").write_text("")
        (root / "serial").write_text("01\n")
        conf = root / "ca.conf"
        conf.write_text(f"[ca]\ndefault_ca=local\n[local]\ndatabase={root}/index\n"
                        f"serial={root}/serial\nnew_certs_dir={root}\ncertificate={ca}\n"
                        f"private_key={cakey}\ndefault_md=sha256\npolicy=subject\n"
                        "[subject]\ncommonName=supplied\n")
        openssl("ca", "-batch", "-notext", "-config", conf, "-in", csr, "-out", leaf,
                "-extfile", ext, "-startdate", "20000101000000Z", "-enddate", "20010101000000Z")
    else:
        openssl("x509", "-req", "-in", csr, "-CA", ca, "-CAkey", cakey,
                "-CAcreateserial", "-days", "1", "-extfile", ext, "-out", leaf)
    trusted = ca
    if mode == "untrusted_ca":
        trusted = root / "unrelated.pem"
        openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                "-subj", "/CN=UnrelatedFixtureCA", "-addext", "basicConstraints=critical,CA:TRUE",
                "-keyout", root / "unrelated.key", "-out", trusted)
    openssl("x509", "-in", trusted, "-outform", "DER", "-out", root / "ca.der")
    for path in root.iterdir():
        if path.is_file():
            path.chmod(0o600)
    return leaf, key


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            if getattr(self.server, "refuse", False):
                try:
                    self.request.close()
                except OSError:
                    pass
                return
            self.request.settimeout(4)
            with ctx.wrap_socket(self.request, server_side=True) as downstream:
                with socket.create_connection(("127.0.0.1", self.server.upstream), timeout=4) as upstream:
                    with self.server.lock:
                        self.server.active.append((downstream, upstream))
                    try:
                        while True:
                            ready, _, _ = select.select([downstream, upstream], [], [], .2)
                            if downstream.pending() and downstream not in ready:
                                ready.append(downstream)
                            for source in ready:
                                # hold_up only freezes connections snapped at hold
                                # time (Agent WSS). Later HTTP tools/call must still
                                # reach the gateway so (d) can observe UNKNOWN.
                                if (source is downstream and self.server.hold_up.is_set()
                                        and id(downstream) in self.server.held):
                                    continue
                                data = source.recv(16384)
                                if not data:
                                    return
                                (upstream if source is downstream else downstream).sendall(data)
                    finally:
                        with self.server.lock:
                            pair = (downstream, upstream)
                            if pair in self.server.active:
                                self.server.active.remove(pair)
        except (OSError, ssl.SSLError):
            pass


class Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = False


def _close_pairs(pairs):
    for down, up in pairs:
        for sock in (down, up):
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass


def apply_op(server, op):
    if op == "drop":
        # Bare drop (no prior hold): defer closes briefly so the control HTTP
        # ack (relayed on an active handler) can flush — preserves (b1)/(c).
        # Held drop: close snapped Agent sockets WHILE hold_up stays set so a
        # buffered Agent reply cannot flush to the gateway (S2-4 (d)).
        with server.lock:
            held = set(server.held)
            if held:
                victims = [(d, u) for d, u in server.active if id(d) in held]
                server.active = [(d, u) for d, u in server.active if id(d) not in held]
                server.held = set()
            else:
                victims = list(server.active)
                server.active.clear()
        if held:
            _close_pairs(victims)
            server.hold_up.clear()
        else:
            server.hold_up.clear()

            def _deferred():
                time.sleep(0.05)
                _close_pairs(victims)

            threading.Thread(target=_deferred, daemon=True).start()
        print(json.dumps({"event": "op_applied", "op": "drop", "held_drop": bool(held)}),
              file=sys.stderr, flush=True)
    elif op == "refuse":
        server.refuse = True
        print(json.dumps({"event": "op_applied", "op": "refuse"}), file=sys.stderr, flush=True)
    elif op == "hold_up":
        with server.lock:
            server.held = {id(down) for down, _ in server.active}
            n = len(server.held)
        server.hold_up.set()
        print(json.dumps({"event": "op_applied", "op": "hold_up", "held": n}),
              file=sys.stderr, flush=True)
    elif op == "release":
        server.hold_up.clear()
        with server.lock:
            server.held = set()
        server.refuse = False
        print(json.dumps({"event": "op_applied", "op": "release"}), file=sys.stderr, flush=True)
    else:
        print(json.dumps({"event": "op_ignored", "op": op}), file=sys.stderr, flush=True)


def control_loop(server, stdin):
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            cmd = json.loads(line)
        except json.JSONDecodeError:
            print(json.dumps({"event": "op_ignored", "reason": "json"}), file=sys.stderr, flush=True)
            continue
        if not isinstance(cmd, dict):
            continue
        op = cmd.get("op")
        if isinstance(op, str):
            apply_op(server, op)


def main():
    global ctx
    leaf, key = certificates(Path(sys.argv[1]))
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(leaf, key)
    server = Server(("127.0.0.1", 0), Handler)
    server.hold_up = threading.Event()
    server.refuse = False
    server.active = []
    server.held = set()
    server.lock = threading.Lock()
    print(json.dumps({"port": server.server_address[1]}), flush=True)
    upstream = json.loads(sys.stdin.readline())
    assert type(upstream) is int and 1 <= upstream <= 65535
    server.upstream = upstream
    threading.Thread(target=control_loop, args=(server, sys.stdin), daemon=True).start()
    server.serve_forever()


if __name__ == "__main__":
    main()
