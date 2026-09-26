#!/usr/bin/env python3
"""Real WSS/gateway/Agent subprocess regression. Disposable DB and keys; no VPS.
Certificates are short-lived fixture material. No verification bypass or redirects.
"""
import argparse
import json
import queue
import select
import socket
import socketserver
import ssl
import subprocess
import threading
import time
from pathlib import Path
from service_test_support import disposable_fixture, private_json, require

CASES = []
STAGE = "setup"


def passed(name):
    CASES.append(name)


class Process:
    def __init__(self, args, packet, env, secrets):
        self.lines = queue.Queue()
        self.output = bytearray()
        self.secrets = secrets
        self.p = subprocess.Popen(list(map(str, args)), stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        self.p.stdin.write(json.dumps(packet).encode())
        self.p.stdin.close()
        self.threads = []
        for stream in (self.p.stdout, self.p.stderr):
            t = threading.Thread(target=self.read, args=(stream,), daemon=True)
            t.start()
            self.threads.append(t)

    def read(self, stream):
        for line in iter(stream.readline, b""):
            self.output.extend(line)
            try:
                self.lines.put(json.loads(line))
            except (ValueError, UnicodeError):
                self.lines.put({"unparsed": True})

    def event(self, name, timeout=12):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                x = self.lines.get(timeout=min(.2, end-time.monotonic()))
            except queue.Empty:
                if self.p.poll() is not None:
                    break
                continue
            if "error" in x:
                raise RuntimeError("child_error_" + str(x["error"]))
            if x.get("event") == name or x.get("status") == name:
                return x
        raise RuntimeError("missing_" + name)

    def stop(self, kill=False, success=True):
        if self.p.poll() is None:
            self.p.kill() if kill else self.p.terminate()
        try:
            self.p.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.p.kill()
            self.p.wait(timeout=3)
            raise RuntimeError("subprocess_shutdown_deadline") from None
        for t in self.threads:
            t.join(timeout=2)
        for secret in self.secrets:
            require(secret.encode() not in self.output, "no_secret_logs")
        if success and not kill:
            require(self.p.returncode == 0, "clean_subprocess_exit")


class Relay:
    """TLS byte relay, preserving actual Upgrade and long-lived duplex sockets."""
    def __init__(self, root):
        def openssl(*args):
            result = subprocess.run(["openssl", *map(str, args)], capture_output=True, timeout=20)
            require(result.returncode == 0, "isolated_tls_fixture")
        ca, cakey = root / "ca.pem", root / "ca.key"
        self.der = root / "ca.der"
        leaf, key, csr = root / "leaf.pem", root / "leaf.key", root / "leaf.csr"
        openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1", "-subj", "/CN=AgentTestCA",
                "-addext", "basicConstraints=critical,CA:TRUE", "-keyout", cakey, "-out", ca)
        openssl("req", "-new", "-newkey", "rsa:2048", "-nodes", "-subj", "/CN=localhost", "-keyout", key, "-out", csr)
        ext = root / "leaf.ext"
        ext.write_text("subjectAltName=DNS:localhost\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n")
        openssl("x509", "-req", "-in", csr, "-CA", ca, "-CAkey", cakey, "-CAcreateserial", "-days", "1", "-extfile", ext, "-out", leaf)
        openssl("x509", "-in", ca, "-outform", "DER", "-out", self.der)
        for p in (cakey, key, self.der):
            p.chmod(0o600)
        expired = root / "expired.pem"
        (root / "ca-index").write_text("")
        (root / "ca-serial").write_text("01\n")
        conf = root / "ca.cnf"
        conf.write_text(f"[ca]\ndefault_ca=testca\n[testca]\ndatabase={root}/ca-index\nnew_certs_dir={root}\nserial={root}/ca-serial\nprivate_key={cakey}\ncertificate={ca}\ndefault_md=sha256\npolicy=policy\n[policy]\ncommonName=supplied\n")
        openssl("ca", "-batch", "-notext", "-config", conf, "-in", csr, "-startdate", "20200101000000Z", "-enddate", "20200102000000Z", "-extfile", ext, "-out", expired)
        self.expired_leaf, self.leaf, self.key = expired, leaf, key
        self.ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.ctx.load_cert_chain(leaf, key)
        self.upstream = 0
        self.mode = "proxy"
        self.requests = 0
        self.stopping = threading.Event()
        owner = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                try:
                    self.request.settimeout(3)
                    with owner.ctx.wrap_socket(self.request, server_side=True) as downstream:
                        if owner.mode == "redirect":
                            downstream.recv(16384)
                            owner.requests += 1
                            downstream.sendall(b"HTTP/1.1 302 Found\r\nLocation: https://foreign.invalid/agent\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                            return
                        with socket.create_connection(("127.0.0.1", owner.upstream), timeout=3) as upstream:
                            downstream.settimeout(3)
                            upstream.settimeout(3)
                            while not owner.stopping.is_set():
                                readable, _, _ = select.select([downstream, upstream], [], [], .2)
                                if downstream.pending() and downstream not in readable:
                                    readable.append(downstream)
                                for source in readable:
                                    data = source.recv(16384)
                                    if not data:
                                        return
                                    (upstream if source is downstream else downstream).sendall(data)
                except (OSError, ssl.SSLError):
                    return

        class Server(socketserver.ThreadingTCPServer):
            daemon_threads = True
            allow_reuse_address = False
        self.server = Server(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.stopping.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)


def wait_db(f, query, expected, seconds=5):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if f.sql(query) == str(expected):
            return
        time.sleep(.1)
    raise RuntimeError("database_condition")


def main():
    global STAGE
    p = argparse.ArgumentParser()
    p.add_argument("--pg-bin", type=Path, required=True)
    p.add_argument("--pg-lib", type=Path)
    p.add_argument("--bin-dir", type=Path, required=True)
    a = p.parse_args()
    rootbin = a.bin_dir.resolve()
    with disposable_fixture(a.pg_bin.resolve(), rootbin / "coding-tools-gateway", a.pg_lib) as f:
        relay = Relay(f.root)
        children = []
        secrets = [f.password, f.packet["identity_key"], f.packet["database_url"]]
        agentbin = rootbin / "coding-tools-agent"
        controlbin = rootbin / "coding-tools-control-gateway"
        cfgpath = f.root / "agent.json"
        device = None

        def process(binary, command, path, packet, extra=()):
            flag = "--key-stdin" if binary == agentbin else "--secrets-stdin"
            obj = Process([binary, command, "--config", path, flag, *extra], packet, f.env, secrets)
            children.append(obj)
            return obj

        def once(binary, command, path, packet, extra=(), success=True):
            obj = process(binary, command, path, packet, extra)
            obj.p.wait(timeout=12)
            obj.stop(success=success)
            require((obj.p.returncode == 0) == success, "expected_cli_status")
            return obj

        def gateway():
            obj = process(controlbin, "serve", f.config, f.packet)
            e = obj.event("ready")
            require(e["mode"] == "identity_with_agent_control", "opt_in_service_mode")
            relay.upstream = f.upstream = int(e["listen"].rsplit(":", 1)[1])
            return obj

        def enroll():
            r = subprocess.run([str(rootbin / "examples" / "agent_fixture")],
                               input=json.dumps({"config": f.config_data, "secrets": f.packet}).encode(),
                               capture_output=True, timeout=12, env=f.env)
            require(r.returncode == 0, "actual_device_enrollment")
            obj = json.loads(r.stdout)
            secrets.append(obj["pkcs8"])
            return obj

        try:
            origin = f"https://localhost:{relay.port}"
            f.setup_config(origin, origin + "/callback")
            f.invoke("migrate")
            f.invoke("provision-owner", packet={**f.packet, "password": f.password})
            f.invoke("register-client")
            device = enroll()
            once(controlbin, "serve", f.config, f.packet, success=False)
            passed("missing_selected_device_fails_before_serve")
            once(controlbin, "select-device", f.config, f.packet, ["--device", device["device"]])
            config = {"origin": origin, "prefix": "/coding-tools", "connector": f.config_data["connector"],
                      "device": device["device"], "device_epoch": device["device_epoch"], "authority_epoch": 1,
                      "public_key": device["public_key"], "revision_file": str(f.root / "revision.bin"),
                      "ca_der_file": str(relay.der), "run_seconds": 100}
            private_json(cfgpath, config)
            packet = {"pkcs8": device["pkcs8"]}
            once(agentbin, "run", cfgpath, packet, success=False)
            passed("journal_requires_explicit_initialization")
            once(agentbin, "init-state", cfgpath, packet)
            once(agentbin, "init-state", cfgpath, packet, success=False)
            passed("journal_initialization_no_overwrite")
            # Default identity service does not expose channel route.
            f.start()
            require(f.http("GET", "/coding-tools/agent")[0] == 404, "identity_only_not_mounted")
            f.stop()
            passed("default_identity_service_unchanged")
            STAGE = "actual_wss_connection"
            server = gateway()
            agent = process(agentbin, "run", cfgpath, packet)
            agent.event("agent_connected")
            rev = agent.event("agent_recovery_projected")["revision"]
            passed("real_enrolled_device_tls_process_roundtrip")
            require(rev == 1 and f.sql("SELECT connected FROM ctm_agent_channel") == "t", "connected_presence")
            state = json.loads(f.sql("SELECT state_text FROM ctm_grant_projection"))
            require(state["phase"] == "recovery_required" and state["execution"] == "offline" and state["grant"] is None,
                    "recovery_only_no_grants")
            passed("signed_projection_cannot_mint_execution_authority")
            once(agentbin, "run", cfgpath, packet, success=False)
            passed("concurrent_agent_process_journal_lock")
            # Long enough to cross the old HTTP ten-second deadline.
            time.sleep(10.5)
            require(agent.p.poll() is None and f.sql("SELECT last_seq FROM ctm_agent_channel") == "4", "separate_ws_lifetime")
            require(f.sql("SELECT revision FROM ctm_grant_projection") == "1", "heartbeat_not_snapshot")
            passed("upgraded_socket_survives_http_deadline")
            passed("heartbeat_does_not_renew_signed_state")
            require(agent.event("agent_recovery_projected", 10)["revision"] == 2, "fresh_snapshot")
            passed("independent_lease_bounded_snapshot_refresh")
            require(f.sql("SELECT (snapshot_until <= lease_until) FROM ctm_grant_projection JOIN ctm_agent_channel USING(connector)") == "t", "lease_ceiling")
            passed("snapshot_freshness_bounded_by_channel_lease")
            # Failed second server bind must not fence the running controller.
            boot = f.sql("SELECT gateway_boot FROM ctm_agent_channel")
            same = private_json(f.root / "same-port.json", {**f.config_data, "bind": f"127.0.0.1:{f.upstream}"})
            once(controlbin, "serve", same, f.packet, success=False)
            require(f.sql("SELECT gateway_boot FROM ctm_agent_channel") == boot, "failed_bind_preserves_boot")
            passed("failed_bind_does_not_fence_active_agent")
            STAGE = "trusted_selection_conflict"
            other = enroll()
            once(controlbin, "select-device", f.config, f.packet, ["--device", other["device"]], success=False)
            require(f.sql("SELECT gateway_boot FROM ctm_agent_channel") == f.sql("SELECT gateway_boot FROM ctm_grant_projection"), "rejected_selection_must_not_fence")
            once(controlbin, "select-device", f.config, f.packet, ["--device", device["device"]])
            require(f.sql("SELECT gateway_boot FROM ctm_grant_projection") == boot, "idempotent_selection_must_not_fence")
            passed("rejected_or_idempotent_selection_preserves_active_controller")
            STAGE = "graceful_client_restart"
            agent.stop()
            wait_db(f, "SELECT connected FROM ctm_agent_channel", "f")
            passed("client_sigterm_disconnects_without_replay")
            agent = process(agentbin, "run", cfgpath, packet)
            agent.event("agent_connected")
            require(agent.event("agent_recovery_projected")["revision"] == 3, "durable_revision_restart")
            passed("journal_persists_revision_across_processes")
            STAGE = "server_restart"
            server.stop()
            require(f.sql("SELECT connected FROM ctm_agent_channel") == "f", "server_shutdown_fences_presence")
            passed("service_drains_upgraded_sockets_and_presence")
            server = gateway()
            agent.event("agent_reconnecting", 12)
            agent.event("agent_connected", 12)
            require(agent.event("agent_recovery_projected")["revision"] == 4, "restart_reconciles")
            require(f.sql("SELECT gateway_boot FROM ctm_agent_channel") != boot, "new_controller_boot")
            passed("server_restart_reconnects_with_fresh_boot")
            agent.stop(kill=True)
            wait_db(f, "SELECT connected FROM ctm_agent_channel", "f")
            agent = process(agentbin, "run", cfgpath, packet)
            agent.event("agent_connected")
            require(agent.event("agent_recovery_projected")["revision"] == 5, "crash_lock_released")
            passed("agent_crash_releases_os_lock")
            agent.stop()
            # TLS failures must terminate promptly; they cannot retry until run_seconds expires.
            STAGE = "tls_identity_failure"
            for name, patch in [("untrusted_ca", {"ca_der_file": None}),
                                ("wrong_certificate_name", {"origin": f"https://127.0.0.1:{relay.port}"})]:
                altered = {**config, **patch, "revision_file": str(f.root / (name + ".bin"))}
                path = private_json(f.root / (name + ".json"), altered)
                once(agentbin, "init-state", path, packet)
                bad = process(agentbin, "run", path, packet)
                bad.p.wait(timeout=6)
                bad.stop(success=False)
                require(bad.p.returncode != 0 and b"agent_reconnecting" not in bad.output, name + "_terminal")
                passed(name + "_rejected_before_proof")
            relay.ctx.load_cert_chain(relay.expired_leaf, relay.key)
            bad = process(agentbin, "run", cfgpath, packet)
            bad.p.wait(timeout=6)
            bad.stop(success=False)
            require(bad.p.returncode != 0 and b"agent_reconnecting" not in bad.output, "expired_certificate_terminal")
            passed("expired_certificate_rejected_before_proof")
            relay.ctx.load_cert_chain(relay.leaf, relay.key)
            STAGE = "redirect"
            relay.mode = "redirect"
            bad = process(agentbin, "run", cfgpath, packet)
            bad.p.wait(timeout=6)
            bad.stop(success=False)
            require(bad.p.returncode != 0 and relay.requests == 1 and b"agent_reconnecting" not in bad.output, "redirect_terminal")
            passed("redirect_not_followed_or_retried")
            relay.mode = "proxy"
            STAGE = "revocation"
            agent = process(agentbin, "run", cfgpath, packet)
            agent.event("agent_connected")
            agent.event("agent_recovery_projected")
            f.sql("UPDATE ctm_devices SET revoked=true,epoch=epoch+1")
            agent.p.wait(timeout=22)
            agent.stop(success=False)
            require(agent.p.returncode != 0 and agent.output.count(b"agent_reconnecting") <= 1, "revocation_terminal")
            passed("revoked_device_not_retried_indefinitely")
            once(controlbin, "serve", f.config, f.packet, success=False)
            passed("revoked_selection_blocks_new_service")
            server.stop()
            passed("all_process_logs_redacted")
            print(json.dumps({"suite": "agent_process_wss", "result": "PASS", "passed": len(CASES),
                              "cases": CASES, "physical_host": False, "workspace_execution": False}))
        finally:
            for child in reversed(children):
                if child.p.poll() is None:
                    child.stop(success=False)
            relay.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"suite": "agent_process_wss", "result": "FAIL", "stage": STAGE,
                          "class": type(exc).__name__, "case": str(exc) if isinstance(exc, RuntimeError) else "bounded_test_failure",
                          "completed_cases": CASES}))
        raise SystemExit(1) from None
