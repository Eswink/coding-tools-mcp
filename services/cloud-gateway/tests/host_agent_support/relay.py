"""Owned test-only TLS relay and finite certificates; no production TLS bypass."""
import json, os, select, socket, socketserver, ssl, subprocess, sys
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
            self.request.settimeout(4)
            with ctx.wrap_socket(self.request, server_side=True) as downstream:
                with socket.create_connection(("127.0.0.1", self.server.upstream), timeout=4) as upstream:
                    while True:
                        ready, _, _ = select.select([downstream, upstream], [], [], .2)
                        if downstream.pending() and downstream not in ready:
                            ready.append(downstream)
                        for source in ready:
                            data = source.recv(16384)
                            if not data:
                                return
                            (upstream if source is downstream else downstream).sendall(data)
        except (OSError, ssl.SSLError):
            pass


class Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = False


def main():
    global ctx
    leaf, key = certificates(Path(sys.argv[1]))
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(leaf, key)
    server = Server(("127.0.0.1", 0), Handler)
    print(json.dumps({"port": server.server_address[1]}), flush=True)
    upstream = json.loads(sys.stdin.readline())
    assert type(upstream) is int and 1 <= upstream <= 65535
    server.upstream = upstream
    server.serve_forever()


if __name__ == "__main__":
    main()
