"""Allowlisted browser-harness diagnostics. Never export exception text or payloads."""
import contextlib

SAFE_CHECKS = frozenset({
    'body_limit',
    'browser_begin',
    'browser_context',
    'browser_cookie_flags',
    'browser_csrf',
    'browser_deny',
    'browser_expired',
    'browser_httponly',
    'browser_launch',
    'browser_login',
    'browser_post_origin',
    'browser_origin_only_referrer',
    'browser_callback_no_referrer',
    'browser_pkce_exchange',
    'browser_response_headers',
    'browser_rotation',
    'cli_check-config',
    'cli_migrate',
    'cli_provision-owner',
    'cli_register-client',
    'cli_rotate-owner',
    'cli_serve',
    'connection_cap',
    'cookie_cleared',
    'credential_not_logged',
    'cross_site',
    'db_outage_live',
    'db_outage_ready',
    'db_recovery_ready',
    'disposable_postgres_createdb',
    'disposable_postgres_initdb',
    'disposable_postgres_pg_ctl',
    'disposable_postgres_psql',
    'existing_process_survives',
    'foreign_host',
    'graceful_stop',
    'health',
    'login_not_consent',
    'no_remote_admin',
    'old_browser_replay',
    'rate_limit',
    'rate_recovery',
    'registered_cross_origin_callback',
    'restart_refresh',
    'rotation_invalidates_flow',
    'rotation_revokes_families',
    'run_disposable_database_as_nonroot',
    'service_ready',
    'service_ready_line',
    'service_start_deadline',
    'service_stop_deadline',
    'slow_header_deadline',
    'test_tls_certificate',
})


def failure_report(exc):
    # Playwright exceptions may contain credential-bearing URLs or HTML.
    blocked = "ERR_BLOCKED_BY_ADMINISTRATOR" in str(exc)
    code = exc.args[0] if type(exc) is RuntimeError and len(exc.args) == 1 else None
    known = isinstance(code, str) and code in SAFE_CHECKS
    return {"suite": "service_process_and_chromium", "result": "BLOCKED" if blocked else "FAIL",
            "class": type(exc).__name__,
            "reason": "browser_navigation_blocked_by_container_policy" if blocked
                      else code if known else "acceptance_error",
            "browser_gate_passed": False}


@contextlib.contextmanager
def browser_phase(name):
    """Mark an allowlisted browser lifecycle phase.

    Playwright TargetClosedError may embed credential-bearing URLs. Convert it
    into RuntimeError(name) so failure_report can export only the SAFE_CHECKS
    token. Other exceptions propagate unchanged. ``browser_begin`` remains the
    first-navigation assertion name; use ``browser_launch`` / ``browser_context``
    for earlier phases — do not overload begin for launch/context.
    """
    if name not in SAFE_CHECKS:
        raise ValueError(name)
    try:
        yield name
    except Exception as exc:
        if type(exc).__name__ == "TargetClosedError":
            raise RuntimeError(name) from None
        raise
