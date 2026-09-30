"""Owned test-only TLS byte relay; no production endpoint or certificate bypass."""
import json, os, select, socket, socketserver, ssl, subprocess, sys, threading
from pathlib import Path

root = Path(sys.argv[1])
def openssl(*args):
    p = subprocess.run(["openssl", *map(str, args)], capture_output=True, timeout=15)
    if p.returncode:
        raise RuntimeError("test certificate generation failed")
ca, cakey, leaf, key, csr = [root / x for x in ("ca.pem", "ca.key", "leaf.pem", "leaf.key", "leaf.csr")]
openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1", "-subj", "/CN=HostAgentFixtureCA",
        "-addext", "basicConstraints=critical,CA:TRUE", "-keyout", cakey, "-out", ca)
openssl("req", "-new", "-newkey", "rsa:2048", "-nodes", "-subj", "/CN=localhost", "-keyout", key, "-out", csr)
ext = root / "leaf.ext"
ext.write_text("subjectAltName=DNS:localhost\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n")
openssl("x509", "-req", "-in", csr, "-CA", ca, "-CAkey", cakey, "-CAcreateserial", "-days", "1", "-extfile", ext, "-out", leaf)
openssl("x509", "-in", ca, "-outform", "DER", "-out", root / "ca.der")
for p in (cakey, key, root / "ca.der"):
    p.chmod(0o600)
ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ctx.load_cert_chain(leaf, key)
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
server = Server(("127.0.0.1", 0), Handler)
print(json.dumps({"port": server.server_address[1]}), flush=True)
upstream = json.loads(sys.stdin.readline())
assert type(upstream) is int and 1 <= upstream <= 65535
server.upstream = upstream
server.serve_forever()
