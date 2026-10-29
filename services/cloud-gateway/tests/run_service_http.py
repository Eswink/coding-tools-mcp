#!/usr/bin/env python3
"""Independent binary/HTTP/PostgreSQL tests. NOT a browser or ChatGPT test.

Only fresh private databases and loopback listeners are used. No input DSN and no
production fallback. Credential-bearing response data stays in test memory.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import socket
import time
from urllib.parse import parse_qs, urlencode, urlsplit

from service_test_support import disposable_fixture, private_json, require

CASES = []
STAGE = "initialization"


def passed(name):
    CASES.append(name)


def main():
    global STAGE
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pg-bin", required=True, type=Path)
    p.add_argument("--binary", required=True, type=Path)
    p.add_argument("--pg-lib", type=Path)
    a = p.parse_args()
    with disposable_fixture(a.pg_bin.resolve(strict=True), a.binary.resolve(strict=True), a.pg_lib) as f:
        f.setup_config("https://gateway.example.invalid", "https://client.example.invalid/callback")
        cfg = f.config_data
        f.invoke("check-config")
        f.invoke("serve", expected=False)
        passed("config_check_without_database_schema")
        f.invoke("migrate"); f.invoke("migrate")
        passed("explicit_idempotent_migration")
        f.invoke("serve", expected=False)
        f.invoke("provision-owner", packet=dict(f.packet, password=f.password))
        f.invoke("provision-owner", packet=dict(f.packet, password=f.password), expected=False)
        passed("missing_owner_rejected_and_duplicate_provisioning_rejected")
        f.invoke("serve", expected=False)
        f.invoke("register-client"); f.invoke("register-client", expected=False)
        passed("missing_client_rejected_and_duplicate_registration_rejected")
        f.invoke("serve", packet=dict(f.packet, password=f.password), expected=False)
        passed("serving_credentials_cannot_contain_owner_password")
        wrong = dict(f.packet, identity_key=base64.urlsafe_b64encode(b"X" * 32).decode().rstrip("="))
        f.invoke("serve", packet=wrong, expected=False)
        passed("changed_key_rejected")
        for key, value in [("owner_subject", "00000000-0000-0000-0000-000000000099"),
                           ("origin", "https://wrong.example.invalid"), ("client_authentication", "confidential"),
                           ("redirect_uri", "https://wrong.example.invalid/cb")]:
            c = private_json(f.root / "mismatch.json", dict(cfg, **{key: value}))
            f.invoke("serve", config=c, expected=False)
        passed("configured_owner_issuer_client_callback_mismatches_rejected")
        f.sql("INSERT INTO _sqlx_migrations(version,description,success,checksum,execution_time) VALUES(999,'future',true,'x',0)")
        f.invoke("serve", expected=False)
        f.sql("DELETE FROM _sqlx_migrations WHERE version=999")
        passed("future_schema_ledger_rejected_without_rollback")
        f.start(files=True)
        live, ready = "/coding-tools/health/live", "/coding-tools/health/ready"
        require(f.http("GET", live)[0] == 200 and f.http("GET", ready)[0] == 200, "health")
        passed("real_process_protected_file_start_and_health")
        c = private_json(f.root / "clash.json", dict(cfg, bind=f"127.0.0.1:{f.upstream}"))
        f.invoke("serve", config=c, expected=False)
        require(f.http("GET", ready)[0] == 200, "existing_listener")
        passed("listener_conflict_does_not_stop_original")
        require(f.http("GET", live, headers={"Host": "foreign.invalid"})[0] == 403, "foreign_host")
        passed("foreign_host_rejected")
        STAGE = "foreign_origin_health_boundary"
        require(f.http("GET", live, headers={"Origin": "https://foreign.invalid"})[0] == 403, "foreign_origin")
        passed("foreign_origin_rejected_on_health_and_identity_surface")
        STAGE = "body_limit"
        require(f.http("POST", "/coding-tools/oauth/token", b"a" * 9000,
                       {"Content-Type": "application/x-www-form-urlencoded"})[0] == 413, "body_limit")
        passed("request_body_limit_enforced_on_actual_tcp")
        for route in ["/coding-tools/admin", "/coding-tools/oauth/provision", "/coding-tools/exec"]:
            require(f.http("POST", route)[0] == 404, "no_http_admin_or_exec")
        passed("no_remote_admin_or_cloud_execution_route")
        origin = cfg["origin"]
        resource = origin + "/coding-tools/mcp/" + cfg["connector"]
        verifier = "a" * 43
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        auth_path = "/coding-tools/oauth/authorize?" + urlencode({"response_type": "code", "client_id": cfg["client_id"],
            "redirect_uri": cfg["redirect_uri"], "resource": resource, "scope": "mcp", "state": "test-state",
            "code_challenge": challenge, "code_challenge_method": "S256"})

        def request_page(path, data=None, cookie=None):
            h = {"Origin": origin}
            if data is not None: h["Content-Type"] = "application/x-www-form-urlencoded"
            if cookie: h["Cookie"] = cookie
            status, headers, body = f.http("POST" if data is not None else "GET", path,
                                           urlencode(data) if data is not None else None, h)
            require(status == 200, "http_flow_page")
            cookie = headers["set-cookie"].split(";", 1)[0]
            csrf = re.search(rb'name=csrf value="([A-Za-z0-9_-]+)"', body).group(1).decode()
            return cookie, csrf

        def begin_login(password=None):
            cookie, csrf = request_page(auth_path)
            return request_page("/coding-tools/oauth/login", {"csrf": csrf, "password": password or f.password}, cookie)

        STAGE = "http_login_consent"
        first_cookie, first_csrf = request_page(auth_path)
        cookie, csrf = request_page("/coding-tools/oauth/login", {"csrf": first_csrf, "password": f.password}, first_cookie)
        require(first_cookie != cookie and first_csrf != csrf, "rotation")
        require(f.sql("SELECT count(*) FROM ctm_codes") == "0", "login_is_not_consent")
        passed("real_http_login_cookie_csrf_rotation_no_implicit_consent")
        h = {"Origin": origin, "Content-Type": "application/x-www-form-urlencoded", "Cookie": first_cookie}
        require(f.http("POST", "/coding-tools/oauth/consent", urlencode({"csrf": first_csrf, "decision": "allow"}), h)[0] == 400,
                "old_cookie_replay")
        passed("rotated_session_replay_rejected")
        h["Cookie"] = cookie
        status, headers, _ = f.http("POST", "/coding-tools/oauth/consent", urlencode({"csrf": csrf, "decision": "allow"}), h)
        require(status == 303 and headers["location"].startswith(cfg["redirect_uri"] + "?"), "explicit_consent")
        callback = parse_qs(urlsplit(headers["location"]).query)
        require(callback.get("state") == ["test-state"], "callback_state")
        passed("explicit_http_consent_exact_callback")
        status, _, _ = f.http("POST", "/coding-tools/oauth/consent", urlencode({"csrf": csrf, "decision": "allow"}), h)
        require(status == 400 and f.sql("SELECT count(*) FROM ctm_codes") == "1", "one_time_consent")
        passed("one_time_consent_replay_rejected")
        token_form = {"grant_type": "authorization_code", "client_id": cfg["client_id"], "code": callback["code"][0],
                      "redirect_uri": cfg["redirect_uri"], "code_verifier": verifier, "resource": resource}
        token_headers = {"Content-Type": "application/x-www-form-urlencoded"}
        status, _, body = f.http("POST", "/coding-tools/oauth/token", urlencode(token_form), token_headers)
        require(status == 200, "pkce_exchange")
        tokens = json.loads(body)
        passed("actual_http_pkce_exchange_without_agent")
        f.stop(); f.start()
        status, _, body = f.http("POST", "/coding-tools/oauth/token", urlencode({"grant_type": "refresh_token",
            "client_id": cfg["client_id"], "refresh_token": tokens["refresh_token"], "resource": resource}), token_headers)
        require(status == 200 and json.loads(body)["access_token"] != tokens["access_token"], "restart_refresh")
        passed("process_restart_preserves_refresh_authority_without_agent")
        cookie, csrf = begin_login()
        f.stop(); f.start()
        h["Cookie"] = cookie
        status, _, _ = f.http("POST", "/coding-tools/oauth/consent", urlencode({"csrf": csrf, "decision": "deny"}), h)
        require(status == 303 and f.sql("SELECT count(*) FROM ctm_codes") == "1", "restart_flow_deny")
        passed("process_restart_preserves_browser_flow_and_deny_semantics")
        cookie, csrf = begin_login()
        f.sql("UPDATE ctm_browser_flows SET expires_at=0")
        h["Cookie"] = cookie
        require(f.http("POST", "/coding-tools/oauth/consent", urlencode({"csrf": csrf, "decision": "allow"}), h)[0] == 400,
                "flow_expiry")
        passed("expired_authorization_not_resurrected")
        cookie, csrf = begin_login()
        f.invoke("rotate-owner", packet=dict(f.packet, password=f.password + "-new"),
                 extra=("--expected-epoch", "999"), expected=False)
        f.invoke("rotate-owner", packet=dict(f.packet, password=f.password + "-new"), extra=("--expected-epoch", "1"))
        h["Cookie"] = cookie
        require(f.http("POST", "/coding-tools/oauth/consent", urlencode({"csrf": csrf, "decision": "allow"}), h)[0] == 400,
                "rotated_flow")
        require(f.sql("SELECT count(*) FROM ctm_families WHERE NOT revoked") == "0", "rotated_tokens")
        passed("compare_and_swap_rotation_revokes_flows_and_tokens")
        begin_login(f.password + "-new")
        passed("new_password_works_without_process_restart")
        STAGE = "readiness_failure"
        f.sql("UPDATE ctm_clients SET disabled=true")
        require(f.http("GET", ready)[0] == 503 and f.http("GET", live)[0] == 200, "disabled_readiness")
        f.sql("UPDATE ctm_clients SET disabled=false")
        passed("disabled_registration_clears_readiness_only")
        f.pg_stop()
        require(f.http("GET", live)[0] == 200 and f.http("GET", ready)[0] == 503, "database_outage")
        f.pg_start()
        require(f.http("GET", ready)[0] == 200, "database_recovery")
        passed("real_database_stop_restart_distinguishes_live_ready")
        STAGE = "ingress_limits"
        time.sleep(1.1)
        statuses = [f.http("GET", live)[0] for _ in range(160)]
        require(429 in statuses and set(statuses) <= {200, 429}, "rate_limit")
        time.sleep(1.1)
        require(f.http("GET", live)[0] == 200, "rate_recovery")
        passed("request_rate_budget_and_recovery")
        sockets = []
        try:
            for _ in range(64): sockets.append(socket.create_connection(("127.0.0.1", f.upstream), timeout=2))
            time.sleep(.15)
            with socket.create_connection(("127.0.0.1", f.upstream), timeout=2) as extra:
                extra.settimeout(2)
                require(extra.recv(1) == b"", "connection_limit")
            passed("actual_tcp_connection_limit")
        finally:
            for s in sockets: s.close()
        time.sleep(.2)
        with socket.create_connection(("127.0.0.1", f.upstream), timeout=2) as slow:
            slow.sendall(b"GET /coding-tools/health/live HTTP/1.1\r\nHost:")
            slow.settimeout(8)
            start = time.monotonic()
            data = slow.recv(4096)
            require(time.monotonic() - start < 8 and (not data or b"408" in data), "header_deadline")
        passed("slow_header_deadline")
        f.stop()
        passed("bounded_sigterm_shutdown")
    print(json.dumps({"suite": "standalone_process_http", "result": "PASS", "passed": len(CASES), "cases": CASES,
                      "browser_tested": False, "agent_connected": False, "production_touched": False}))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"suite": "standalone_process_http", "result": "FAIL", "stage": STAGE,
                          "class": type(exc).__name__, "completed_cases": CASES}))
        raise SystemExit(1) from None
