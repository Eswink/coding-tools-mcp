#!/usr/bin/env python3
"""Real binary + fresh PostgreSQL + Chromium acceptance, without an Agent or VPS.

Run as a non-root test user. Requires existing PostgreSQL16, built gateway binary,
OpenSSL, Playwright Python, and an explicit local Chromium binary. Creates/deletes
only a new private cluster and ephemeral loopback TLS proxy. No production input.
"""
import argparse
import hashlib
import base64
import json
from pathlib import Path
import socket
import time
from urllib.parse import urlencode

from service_test_support import disposable_fixture, private_json, require, tls_proxy


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pg-bin", required=True, type=Path)
    p.add_argument("--binary", required=True, type=Path)
    p.add_argument("--chromium", required=True, type=Path)
    p.add_argument("--pg-lib", type=Path)
    a = p.parse_args()
    cases = []

    def passed(name):
        cases.append(name)

    with disposable_fixture(a.pg_bin.resolve(strict=True), a.binary.resolve(strict=True), a.pg_lib) as f:
        with tls_proxy(f) as (origin, foreign):
            f.setup_config(origin, foreign + "/callback")
            cfg = f.config_data
            resource = origin + "/coding-tools/mcp/" + cfg["connector"]
            f.invoke("check-config")
            passed("read_only_config_check")
            f.invoke("serve", expected=False)
            passed("unmigrated_serve_rejected")
            f.invoke("migrate")
            f.invoke("migrate")
            passed("explicit_migration_is_idempotent")
            f.invoke("serve", expected=False)
            passed("missing_owner_serve_rejected")
            f.invoke("provision-owner", packet=dict(f.packet, password=f.password))
            f.invoke("provision-owner", packet=dict(f.packet, password=f.password), expected=False)
            passed("duplicate_owner_rejected")
            f.invoke("serve", expected=False)
            passed("missing_client_serve_rejected")
            f.invoke("register-client")
            f.invoke("register-client", expected=False)
            passed("duplicate_client_rejected")
            f.invoke("serve", packet=dict(f.packet, password=f.password), expected=False)
            passed("serving_password_packet_rejected")
            wrong = private_json(f.root / "wrong-config.json", dict(cfg, client_authentication="confidential"))
            f.invoke("serve", config=wrong, expected=False)
            passed("client_auth_mode_mismatch_rejected")
            altered = dict(f.packet, identity_key=base64.urlsafe_b64encode(b"X" * 32).decode().rstrip("="))
            f.invoke("serve", packet=altered, expected=False)
            passed("wrong_identity_key_rejected")
            f.start(files=True)
            passed("actual_process_starts_with_protected_file")
            live, ready = "/coding-tools/health/live", "/coding-tools/health/ready"
            require(f.http("GET", live)[0] == 200 and f.http("GET", ready)[0] == 200, "health")
            passed("live_and_ready")
            clash = private_json(f.root / "clash.json", dict(cfg, bind=f"127.0.0.1:{f.upstream}"))
            f.invoke("serve", config=clash, expected=False)
            require(f.http("GET", ready)[0] == 200, "existing_process_survives")
            passed("second_listener_cannot_replace_running_service")
            require(f.http("GET", live, headers={"Host": "foreign.invalid"})[0] == 403, "foreign_host")
            passed("foreign_host_rejected")
            require(f.http("POST", "/coding-tools/oauth/token", b"a" * 9000,
                           {"Content-Type": "application/x-www-form-urlencoded"})[0] == 413, "body_limit")
            passed("actual_http_body_limit")
            require(f.http("POST", "/coding-tools/admin/provision")[0] == 404, "no_remote_admin")
            passed("no_http_management_shortcut")

            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path=str(a.chromium.resolve(strict=True)),
                                                     headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
                context = browser.new_context(ignore_https_errors=True)
                context.route("**/*", lambda route: route.continue_()
                              if route.request.url.startswith((origin + "/", foreign + "/")) else route.abort())
                page = context.new_page()
                verifier = "a" * 43
                challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
                state = "isolated-browser-state"
                auth_url = origin + "/coding-tools/oauth/authorize?" + urlencode({
                    "response_type": "code", "client_id": cfg["client_id"], "redirect_uri": cfg["redirect_uri"],
                    "resource": resource, "scope": "mcp", "code_challenge": challenge,
                    "code_challenge_method": "S256", "state": state})

                def begin():
                    r = page.goto(auth_url)
                    require(r.status == 200, "browser_begin")
                    return r

                def login(password=None):
                    page.fill("input[name=password]", password or f.password)
                    with page.expect_request(lambda request: request.method == "POST"
                                             and request.url == origin + "/coding-tools/oauth/login") as posted:
                        with page.expect_navigation() as r:
                            page.click("button[type=submit]")
                    require(r.value.status == 200, "browser_login")
                    # Compare privately; export only the fixed case name, never headers/URLs.
                    require(posted.value.header_value("origin") == origin, "browser_post_origin")
                    require(posted.value.header_value("referer") == origin + "/", "browser_origin_only_referrer")

                r = begin()
                h = r.headers
                require(h.get("cache-control") == "no-store" and "default-src 'none'" in h.get("content-security-policy", "")
                        and h.get("referrer-policy") == "strict-origin", "browser_response_headers")
                cookies = [c for c in context.cookies(origin) if c["name"] == "__Host-ctm-browser"]
                require(len(cookies) == 1 and cookies[0]["secure"] and cookies[0]["httpOnly"]
                        and cookies[0]["sameSite"] == "Lax" and cookies[0]["path"] == "/", "browser_cookie_flags")
                require("__Host-ctm-browser" not in page.evaluate("document.cookie"), "browser_httponly")
                passed("chromium_secure_httponly_samesite_cookie_and_headers")
                old_cookie = cookies[0]["value"]
                old_csrf = page.input_value("input[name=csrf]")
                login()
                new_cookie = next(c["value"] for c in context.cookies(origin) if c["name"] == "__Host-ctm-browser")
                new_csrf = page.input_value("input[name=csrf]")
                require(old_cookie != new_cookie and old_csrf != new_csrf, "browser_rotation")
                require(f.sql("SELECT count(*) FROM ctm_codes") == "0", "login_not_consent")
                passed("chromium_login_rotates_cookie_csrf_without_issuing_code")
                status, _, _ = f.http("POST", "/coding-tools/oauth/consent",
                    urlencode({"csrf": old_csrf, "decision": "allow"}),
                    {"Origin": origin, "Content-Type": "application/x-www-form-urlencoded",
                     "Cookie": "__Host-ctm-browser=" + old_cookie, "Sec-Fetch-Site": "same-origin"})
                require(status == 400, "old_browser_replay")
                passed("rotated_cookie_cannot_be_replayed")
                with page.expect_request(lambda request: request.method == "POST"
                                         and request.url == origin + "/coding-tools/oauth/consent") as posted:
                    with page.expect_request(lambda request: request.url.startswith(foreign + "/callback?")) as callback:
                        with page.expect_navigation():
                            page.click("button[value=allow]")
                require(posted.value.header_value("origin") == origin, "browser_post_origin")
                require(posted.value.header_value("referer") == origin + "/", "browser_origin_only_referrer")
                require(callback.value.header_value("referer") is None, "browser_callback_no_referrer")
                passed("chromium_form_origin_without_path_query_referrer_and_referrer_free_callback")
                require(page.title() == "Test callback" and f.callbacks[-1].get("state") == [state]
                        and "code" in f.callbacks[-1], "registered_cross_origin_callback")
                require(not any(c["name"] == "__Host-ctm-browser" for c in context.cookies(origin)), "cookie_cleared")
                code = f.callbacks[-1]["code"][0]
                passed("chromium_explicit_consent_and_cross_origin_callback")
                token_form = {"grant_type": "authorization_code", "client_id": cfg["client_id"], "code": code,
                              "redirect_uri": cfg["redirect_uri"], "code_verifier": verifier, "resource": resource}
                status, _, body = f.http("POST", "/coding-tools/oauth/token", urlencode(token_form),
                                       {"Content-Type": "application/x-www-form-urlencoded"})
                require(status == 200, "browser_pkce_exchange")
                tokens = json.loads(body)
                passed("real_browser_code_pkce_exchange_without_agent")
                f.stop()
                f.start()
                status, _, body = f.http("POST", "/coding-tools/oauth/token", urlencode({
                    "grant_type": "refresh_token", "client_id": cfg["client_id"],
                    "refresh_token": tokens["refresh_token"], "resource": resource}),
                    {"Content-Type": "application/x-www-form-urlencoded"})
                require(status == 200 and json.loads(body)["access_token"] != tokens["access_token"], "restart_refresh")
                passed("separate_process_restart_refresh_without_agent")

                # Explicit denial is a browser flow, not an authentication failure.
                before = f.sql("SELECT count(*) FROM ctm_codes")
                begin(); login()
                with page.expect_navigation(): page.click("button[value=deny]")
                require(f.callbacks[-1].get("error") == ["access_denied"]
                        and f.sql("SELECT count(*) FROM ctm_codes") == before, "browser_deny")
                passed("chromium_denial_does_not_issue_code")

                begin(); login()
                page.locator("input[name=csrf]").evaluate("e => e.value = 'wrong-csrf'")
                with page.expect_navigation() as rejected: page.click("button[value=allow]")
                require(rejected.value.status == 400 and f.sql("SELECT count(*) FROM ctm_codes") == before, "browser_csrf")
                passed("chromium_same_origin_forged_csrf_rejected")

                begin(); login()
                csrf = page.input_value("input[name=csrf]")
                attack = context.new_page()
                attack.goto(foreign + "/attacker")
                with attack.expect_navigation() as rejected:
                    attack.evaluate("""([action, csrf]) => {
                        let f = document.createElement('form'); f.method='post'; f.action=action;
                        for (const [name,value] of [['csrf',csrf],['decision','allow']]) {
                            let i=document.createElement('input'); i.name=name; i.value=value; f.append(i);
                        } document.body.append(f); f.submit();
                    }""", [origin + "/coding-tools/oauth/consent", csrf])
                require(rejected.value.status in (400, 403) and f.sql("SELECT count(*) FROM ctm_codes") == before, "cross_site")
                attack.close()
                passed("chromium_cross_site_consent_rejected_even_with_known_csrf")

                # Controlled expiry injection only in this fresh disposable test database.
                f.sql("UPDATE ctm_browser_flows SET expires_at=0")
                with page.expect_navigation() as rejected: page.click("button[value=allow]")
                require(rejected.value.status == 400, "browser_expired")
                passed("chromium_expired_flow_rejected")
                begin(); login()
                new_password = f.password + "-rotated"
                f.invoke("rotate-owner", packet=dict(f.packet, password=new_password),
                         extra=("--expected-epoch", "999"), expected=False)
                passed("stale_rotation_epoch_rejected")
                f.invoke("rotate-owner", packet=dict(f.packet, password=new_password), extra=("--expected-epoch", "1"))
                with page.expect_navigation() as rejected: page.click("button[value=allow]")
                require(rejected.value.status == 400, "rotation_invalidates_flow")
                require(f.sql("SELECT count(*) FROM ctm_families WHERE NOT revoked") == "0", "rotation_revokes_families")
                passed("rotation_revokes_browser_and_oauth_authority")
                begin(); login(new_password)
                passed("chromium_rotated_password_works_without_service_restart")
                context.close(); browser.close()

            f.pg_stop()
            require(f.http("GET", live)[0] == 200, "db_outage_live")
            require(f.http("GET", ready)[0] == 503, "db_outage_ready")
            f.pg_start()
            require(f.http("GET", ready)[0] == 200, "db_recovery_ready")
            passed("live_ready_distinguish_real_database_outage_and_recovery")

            # Exhaust rate budget with small, content-free health calls.
            time.sleep(1.1)
            statuses = [f.http("GET", live)[0] for _ in range(160)]
            require(429 in statuses and set(statuses) <= {200, 429}, "rate_limit")
            time.sleep(1.1)
            require(f.http("GET", live)[0] == 200, "rate_recovery")
            passed("fixed_window_rate_budget_rejects_then_recovers")

            sockets = []
            try:
                for _ in range(64): sockets.append(socket.create_connection(("127.0.0.1", f.upstream), timeout=2))
                time.sleep(.15)
                with socket.create_connection(("127.0.0.1", f.upstream), timeout=2) as extra:
                    extra.settimeout(2)
                    require(extra.recv(1) == b"", "connection_cap")
                passed("connection_admission_cap")
            finally:
                for s in sockets: s.close()
            time.sleep(.2)
            with socket.create_connection(("127.0.0.1", f.upstream), timeout=2) as slow:
                slow.sendall(b"GET /coding-tools/health/live HTTP/1.1\r\nHost:")
                slow.settimeout(8)
                start = time.monotonic()
                data = slow.recv(4096)
                require(time.monotonic() - start < 8 and (not data or b"408" in data), "slow_header_deadline")
            passed("slow_header_connection_deadline")
            f.stop()
            passed("bounded_graceful_shutdown")
        print(json.dumps({"suite": "service_process_and_chromium", "passed": len(cases), "cases": cases,
                          "agent_connected": False, "production_touched": False,
                          "browser_os_sandbox_tested": False, "real_chatgpt_tested": False}))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Playwright exceptions may embed credential-bearing URLs. Never export them.
        blocked = "ERR_BLOCKED_BY_ADMINISTRATOR" in str(exc)
        print(json.dumps({"suite": "service_process_and_chromium",
                          "result": "BLOCKED" if blocked else "FAIL", "class": type(exc).__name__,
                          "reason": "browser_navigation_blocked_by_container_policy" if blocked else "acceptance_error",
                          "browser_gate_passed": False}))
        raise SystemExit(78 if blocked else 1) from None
