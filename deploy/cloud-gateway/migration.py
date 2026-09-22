#!/usr/bin/env python3
"""Render a deterministic, review-only public-origin/OAuth migration package.

This module never contacts Docker, Nginx, DNS, SSH, the VPS, OAuth clients, or
any database. It accepts public topology identifiers only; secret material is
not part of its input schema.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit
import uuid

SCHEMA = "coding-tools-origin-migration/v1"
MANIFEST_SCHEMA = "coding-tools-review-artifact-manifest/v1"
DEFAULT_ORIGIN = "https://research-system.eswlnk.com"
DEFAULT_PREFIX = "/coding-tools"
DEFAULT_UPSTREAM_PORT = 28880
MAX_PREFIX_BYTES = 128
MAX_ORIGIN_BYTES = 512

DOMAIN_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
PREFIX_RE = re.compile(r"/[a-z0-9-]+(?:/[a-z0-9-]+)*")
ENGINE_RE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")


class MigrationError(ValueError):
    pass


def _canonical_domain(host: str) -> str:
    if (
        not host
        or not host.isascii()
        or host != host.lower()
        or len(host) > 253
        or host.endswith(".")
    ):
        raise MigrationError("invalid canonical DNS host")
    labels = host.split(".")
    if len(labels) < 2 or any(not DOMAIN_LABEL.fullmatch(label) for label in labels):
        raise MigrationError("invalid canonical DNS host")
    return host


def canonical_origin(value: str) -> dict:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > MAX_ORIGIN_BYTES:
        raise MigrationError("invalid public origin")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise MigrationError("public origin must be a canonical HTTPS origin")

    # This planner intentionally supports DNS origins only. IPv6 literals and
    # IP addresses are outside the reviewed production topology.
    host = _canonical_domain(parsed.hostname or "")
    try:
        port = parsed.port
    except ValueError as exc:
        raise MigrationError("invalid public origin port") from exc

    raw_netloc = parsed.netloc
    if raw_netloc.startswith("[") or raw_netloc.count(":") > 1:
        raise MigrationError("IP literals are not accepted as public origins")
    explicit_port = None
    if ":" in raw_netloc:
        raw_host, raw_port = raw_netloc.rsplit(":", 1)
        if raw_host != host or not raw_port.isdigit() or (len(raw_port) > 1 and raw_port.startswith("0")):
            raise MigrationError("non-canonical public origin port")
        explicit_port = int(raw_port)

    effective_port = 443 if port is None else port
    if not 1 <= effective_port <= 65535:
        raise MigrationError("invalid public origin port")
    if explicit_port is not None and explicit_port != effective_port:
        raise MigrationError("invalid public origin port")

    serialized = f"https://{host}" if effective_port == 443 else f"https://{host}:{effective_port}"
    return {
        "scheme": "https",
        "host": host,
        "effective_port": effective_port,
        "origin": serialized,
    }


def canonical_prefix(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value.isascii()
        or len(value.encode("ascii", "strict")) > MAX_PREFIX_BYTES
        or not PREFIX_RE.fullmatch(value)
        or "//" in value
        or value.endswith("/")
    ):
        raise MigrationError("invalid canonical public prefix")
    return value


def canonical_connector(value: str) -> str:
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError, TypeError) as exc:
        raise MigrationError("connector must be a canonical UUID") from exc
    if not parsed.int or str(parsed) != value:
        raise MigrationError("connector must be a nonzero canonical UUID")
    return value


def public_identity(origin: str, prefix: str, connector: str) -> dict:
    base = canonical_origin(origin)
    prefix = canonical_prefix(prefix)
    connector = canonical_connector(connector)
    resource_path = f"{prefix}/mcp/{connector}"
    issuer_path = f"{prefix}/oauth"
    return {
        **base,
        "prefix": prefix,
        "connector": connector,
        "resource_path": resource_path,
        "resource": base["origin"] + resource_path,
        "issuer_path": issuer_path,
        "issuer": base["origin"] + issuer_path,
    }


def _engine_at_least_28(value) -> bool:
    if not isinstance(value, str) or not ENGINE_RE.fullmatch(value):
        return False
    return tuple(map(int, value.split("."))) >= (28, 0, 0)


def required_evidence(inventory: dict | None) -> list[dict]:
    data = dict(inventory or {})
    supported_host = bool(data.get("os_security_support_verified"))
    if data.get("os_id") == "centos-stream" and str(data.get("os_version", "")) == "8":
        supported_host = False

    checks = [
        ("supported_host", supported_host, "production host receives supported security updates"),
        (
            "docker_engine_isolation",
            _engine_at_least_28(data.get("docker_engine_version"))
            and data.get("external_port_isolation_verified") is True,
            "Docker Engine and external reachability prove loopback-only publishing",
        ),
        (
            "upstream_port_available",
            data.get("upstream_port_available") is True,
            "planned loopback upstream port is free on the real host",
        ),
        (
            "prefix_routes_available",
            data.get("prefix_routes_available") is True,
            "existing TLS vhost has no conflicting migration paths",
        ),
        ("tls_verified", data.get("tls_verified") is True, "public TLS identity is verified"),
        (
            "waf_protocol_verified",
            data.get("waf_protocol_verified") is True,
            "Baota/WAF preserves reviewed MCP/OAuth/upgrade semantics",
        ),
        ("candidate_readiness", False, "candidate gateway package reports ready behind loopback"),
        ("current_route_backup_receipt", False, "existing vhost/routing config backup digest is recorded"),
        (
            "oauth_refresh_agent_offline",
            False,
            "real-host OAuth refresh succeeds while local Agent is offline",
        ),
        (
            "mcp_offline_contract",
            False,
            "real-host catalog remains stable and owner call returns typed workspace-offline",
        ),
        ("rollback_rehearsal", False, "routing-only rollback was rehearsed without identity rollback"),
        ("real_chatgpt_acceptance", False, "real ChatGPT reconnect behavior has been observed"),
    ]
    return [
        {"id": key, "status": "satisfied" if ok else "missing", "description": description}
        for key, ok, description in checks
    ]


def migration_plan(
    *,
    current_origin: str,
    target_origin: str,
    connector: str,
    target_connector: str | None = None,
    current_prefix: str = DEFAULT_PREFIX,
    target_prefix: str | None = None,
    upstream_port: int = DEFAULT_UPSTREAM_PORT,
    inventory: dict | None = None,
) -> dict:
    if type(upstream_port) is not int or not 1024 <= upstream_port <= 65535:
        raise MigrationError("invalid unprivileged loopback upstream port")

    target_connector = connector if target_connector is None else target_connector
    target_prefix = current_prefix if target_prefix is None else target_prefix
    current = public_identity(current_origin, current_prefix, connector)
    target = public_identity(target_origin, target_prefix, target_connector)

    identity_fields = ("scheme", "host", "effective_port", "resource_path", "issuer_path", "connector")
    stable_identity = all(current[field] == target[field] for field in identity_fields)
    mode = "STABLE_ORIGIN_ROUTE_SWAP" if stable_identity else "EXPLICIT_RECONNECT_REAUTH_REQUIRED"
    evidence = required_evidence(inventory)

    plan = {
        "schema": SCHEMA,
        "review_only": True,
        "changes_applied": False,
        "release_allowed": False,
        "mode": mode,
        "current": current,
        "target": target,
        "loopback_upstream": {"host": "127.0.0.1", "port": upstream_port},
        "oauth_continuity": {
            "eligible": stable_identity,
            "identity_database": "preserve_current_monotonic_state",
            "credential_material": "never_export_or_copy",
            "required_action": (
                "preserve_existing_identity_state"
                if stable_identity
                else "explicit_connector_reconnect_and_reauthentication"
            ),
        },
        "required_evidence": evidence,
        "phases": [
            {
                "name": "preflight",
                "mutation": False,
                "requires": [
                    "supported_host",
                    "docker_engine_isolation",
                    "upstream_port_available",
                    "prefix_routes_available",
                    "tls_verified",
                    "waf_protocol_verified",
                    "current_route_backup_receipt",
                ],
                "actions": [
                    "review_current_public_identity",
                    "review_candidate_identity",
                    "validate_candidate_compose_and_nginx_offline",
                    "record_existing_route_backup_digest",
                ],
            },
            {
                "name": "stage",
                "mutation": False,
                "requires": ["candidate_readiness"],
                "actions": [
                    "start_candidate_only_after_separate_deployment_authorization",
                    "verify_candidate_loopback_readiness",
                    "keep_previous_route_available",
                ],
            },
            {
                "name": "cutover",
                "mutation": True,
                "requires": [
                    "candidate_readiness",
                    "current_route_backup_receipt",
                    "tls_verified",
                    "waf_protocol_verified",
                ],
                "actions": [
                    "stop_new_mutating_admissions_at_old_route",
                    "switch_only_reviewed_mcp_oauth_route_selection",
                    "retain_previous_route_for_bounded_rollback",
                ],
            },
            {
                "name": "verify",
                "mutation": False,
                "requires": [
                    "oauth_refresh_agent_offline",
                    "mcp_offline_contract",
                    "real_chatgpt_acceptance",
                ],
                "actions": [
                    "verify_oauth_continuity_or_explicit_reauthentication",
                    "verify_stable_catalog_and_offline_error",
                    "verify_real_chatgpt_connector_behavior",
                ],
            },
            {
                "name": "rollback",
                "mutation": True,
                "requires": ["current_route_backup_receipt", "rollback_rehearsal"],
                "actions": [
                    "stop_new_candidate_mutating_admissions",
                    "restore_previous_route_selection_only",
                    "preserve_current_identity_and_request_ledger_state",
                    "reconcile_unknown_outcomes_without_replay",
                ],
            },
        ],
        "rollback": {
            "routing_only": True,
            "restore_identity_database": False,
            "restore_oauth_state": False,
            "restore_revocation_epochs": False,
            "restore_consumed_authorization_state": False,
            "replay_unknown_requests": False,
            "preserve_current_identity_database": True,
            "preserve_revocations": True,
            "preserve_request_ledger_uncertainty": True,
            "keep_previous_route_until_host_acceptance": True,
        },
        "forbidden_operations": [
            "automatic_dns_change",
            "automatic_nginx_reload",
            "automatic_waf_change",
            "automatic_firewall_change",
            "automatic_docker_start",
            "automatic_database_restore",
            "automatic_oauth_credential_export",
            "automatic_connector_reauthentication",
            "automatic_unknown_request_replay",
        ],
    }

    if not stable_identity:
        plan["oauth_continuity"]["eligible"] = False
    return plan


def artifact_manifest(artifacts: dict[str, bytes]) -> dict:
    files = []
    for name in sorted(artifacts):
        path = Path(name)
        if (
            path.is_absolute()
            or ".." in path.parts
            or len(path.parts) != 1
            or name == "artifact-manifest.review.json"
        ):
            raise MigrationError("invalid review artifact name")
        payload = artifacts[name]
        if not isinstance(payload, bytes):
            raise MigrationError("review artifact must be bytes")
        files.append(
            {
                "path": name,
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    return {
        "schema": MANIFEST_SCHEMA,
        "algorithm": "sha256",
        "manifest_self_hashed": False,
        "files": files,
    }


def verify_artifact_manifest(directory: Path, manifest: dict) -> None:
    if manifest.get("schema") != MANIFEST_SCHEMA or manifest.get("algorithm") != "sha256":
        raise MigrationError("invalid artifact manifest schema")
    files = manifest.get("files")
    if not isinstance(files, list) or files != sorted(files, key=lambda item: item.get("path", "")):
        raise MigrationError("artifact manifest is not sorted")
    root = directory.resolve(strict=True)
    seen = set()
    for entry in files:
        if set(entry) != {"path", "bytes", "sha256"}:
            raise MigrationError("invalid artifact manifest entry")
        name = entry["path"]
        if not isinstance(name, str) or name in seen:
            raise MigrationError("invalid artifact manifest path")
        seen.add(name)
        path = Path(name)
        if path.is_absolute() or ".." in path.parts or len(path.parts) != 1:
            raise MigrationError("invalid artifact manifest path")
        item = (root / path).resolve(strict=True)
        if item.parent != root or item.is_symlink() or not item.is_file():
            raise MigrationError("invalid artifact manifest target")
        payload = item.read_bytes()
        if len(payload) != entry["bytes"] or hashlib.sha256(payload).hexdigest() != entry["sha256"]:
            raise MigrationError("artifact digest mismatch")


def _json_bytes(value: dict) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def render_review_package(
    *,
    output: Path,
    current_origin: str,
    target_origin: str,
    connector: str,
    target_connector: str | None,
    current_prefix: str,
    target_prefix: str | None,
    upstream_port: int,
    inventory: dict | None,
) -> dict:
    plan = migration_plan(
        current_origin=current_origin,
        target_origin=target_origin,
        connector=connector,
        target_connector=target_connector,
        current_prefix=current_prefix,
        target_prefix=target_prefix,
        upstream_port=upstream_port,
        inventory=inventory,
    )
    artifacts = {
        "migration-plan.review.json": _json_bytes(plan),
        "MIGRATION_NOT_APPLIED.txt": (
            b"Review-only migration package. No DNS, Nginx, WAF, Docker, database, OAuth, "
            b"Connector, or VPS changes were applied.\n"
        ),
    }
    manifest = artifact_manifest(artifacts)

    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    try:
        for name, payload in artifacts.items():
            fd = os.open(output / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
        payload = _json_bytes(manifest)
        fd = os.open(
            output / "artifact-manifest.review.json",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
        verify_artifact_manifest(output, manifest)
    except Exception:
        # A partial review directory is safer left visible than silently retried
        # or overwritten. The caller must inspect/remove it explicitly.
        raise
    return plan


def _load_inventory(path: Path | None) -> dict:
    if path is None:
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise MigrationError("inventory must be a JSON object")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-origin", default=DEFAULT_ORIGIN)
    parser.add_argument("--target-origin", default=DEFAULT_ORIGIN)
    parser.add_argument("--connector-id", required=True)
    parser.add_argument("--target-connector-id")
    parser.add_argument("--current-prefix", default=DEFAULT_PREFIX)
    parser.add_argument("--target-prefix")
    parser.add_argument("--upstream-port", type=int, default=DEFAULT_UPSTREAM_PORT)
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    plan = render_review_package(
        output=args.output,
        current_origin=args.current_origin,
        target_origin=args.target_origin,
        connector=args.connector_id,
        target_connector=args.target_connector_id,
        current_prefix=args.current_prefix,
        target_prefix=args.target_prefix,
        upstream_port=args.upstream_port,
        inventory=_load_inventory(args.inventory),
    )
    print(
        json.dumps(
            {
                "rendered": True,
                "applied": False,
                "release_allowed": False,
                "mode": plan["mode"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
