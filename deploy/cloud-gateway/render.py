#!/usr/bin/env python3
"""Render review-only artifacts. Never contact Docker, Nginx, DNS or the VPS."""
import argparse
import json
import os
from pathlib import Path
import re
import uuid

DEFAULT_DOMAIN = "research-system.eswlnk.com"
PREFIX = "/coding-tools"
DEFAULT_PORT = 28880


def validate(domain: str, connector: str, port: int) -> str:
    labels = domain.split(".")
    if (not isinstance(domain, str) or not domain.isascii() or domain != domain.lower()
            or len(domain) > 253 or len(labels) < 2
            or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", x) for x in labels)
            or type(port) is not int or not 1024 <= port <= 65535):
        raise ValueError("invalid canonical DNS name or unprivileged loopback port")
    parsed = uuid.UUID(connector)
    if not parsed.int or str(parsed) != connector:
        raise ValueError("connector must be a nonzero canonical UUID")
    return str(parsed)


def nginx_locations(domain: str, connector: str, port: int) -> str:
    validate(domain, connector, port)
    resource = f"{PREFIX}/mcp/{connector}"
    routes = [
        (f"= /.well-known/oauth-protected-resource{resource}", False),
        (f"= /.well-known/oauth-authorization-server{PREFIX}/oauth", False),
        (f"{PREFIX}/", False),
        (f"= {PREFIX}/agent/connect", True),
    ]
    blocks = ["# REVIEW ONLY: no complete Gateway/Agent executable in round 2.",
              "# Merge locations into the EXISTING TLS vhost, never replace nginx.conf.",
              "# WAF, certificate, root site, firewall and DNS are not altered."]
    safe_host = re.escape(domain)
    for path, websocket in routes:
        lines = [f"location {path} {{",
                 f'    if ($http_host !~* "^{safe_host}(?::443)?$") {{ return 421; }}',
                 f"    proxy_pass http://127.0.0.1:{port};",  # no URI: retain prefix
                 "    proxy_http_version 1.1;",
                 f"    proxy_set_header Host {domain};",
                 '    proxy_set_header Forwarded "";',
                 '    proxy_set_header X-Forwarded-Host "";',
                 '    proxy_set_header X-Forwarded-For $remote_addr;',
                 '    proxy_set_header X-Forwarded-Proto https;',
                 '    proxy_set_header X-Real-IP $remote_addr;',
                 '    proxy_set_header Accept-Encoding "";',
                 '    proxy_buffering off;',
                 '    proxy_request_buffering off;',
                 '    proxy_cache off;',
                 '    proxy_intercept_errors off;',
                 '    proxy_redirect off;',
                 '    proxy_connect_timeout 3s;',
                 '    proxy_read_timeout 75s;',
                 '    proxy_send_timeout 30s;',
                 '    client_max_body_size 64k;',
                 '    client_body_timeout 10s;',
                 '    access_log off;']
        if websocket:
            lines += ['    # Future enrolled agent route only; not implemented by this library.',
                      '    proxy_set_header Upgrade $http_upgrade;',
                      '    proxy_set_header Connection "upgrade";']
        else:
            lines += ['    proxy_set_header Upgrade "";', '    proxy_set_header Connection "";']
        blocks.append("\n".join(lines + ["}"]))
    return "\n\n".join(blocks) + "\n"


def compose_blueprint(domain: str, connector: str, port: int) -> dict:
    validate(domain, connector, port)
    return {
        "name": "coding-tools-gateway",
        "x-delivery-state": "NOT_DEPLOYABLE_IDENTITY_LIBRARY_ONLY",
        "services": {
            "gateway": {
                "profiles": ["integration-pending"],
                "image": "${GATEWAY_IMAGE:?audited digest-pinned gateway image required}",
                "platform": "linux/amd64", "user": "65532:65532", "read_only": True,
                "cap_drop": ["ALL"], "security_opt": ["no-new-privileges:true"],
                "pids_limit": 128, "mem_limit": "512m", "cpus": "1.0",
                "restart": "unless-stopped",
                "ports": [{"target": 8080, "published": str(port), "host_ip": "127.0.0.1", "protocol": "tcp"}],
                "environment": {
                    "PUBLIC_ORIGIN": f"https://{domain}", "PUBLIC_PREFIX": PREFIX,
                    "CONNECTOR_ID": connector, "LISTEN_ADDR": "0.0.0.0:8080",
                    "DATABASE_URL_FILE": "/run/secrets/gateway_database_url",
                    "IDENTITY_KEY_FILE": "/run/secrets/gateway_identity_key",
                },
                "secrets": ["gateway_database_url", "gateway_identity_key"],
                "tmpfs": ["/tmp:rw,noexec,nosuid,size=16m"],
                "networks": ["edge", "database"],
                "depends_on": {"postgres": {"condition": "service_healthy"}},
                "logging": {"driver": "local", "options": {"max-size": "10m", "max-file": "3"}},
            },
            "postgres": {
                "profiles": ["integration-pending"],
                "image": "${POSTGRES_IMAGE:?tested PostgreSQL 16 digest-pinned image required}",
                "platform": "linux/amd64", "restart": "unless-stopped",
                "read_only": True, "cap_drop": ["ALL"],
                "cap_add": ["CHOWN", "DAC_OVERRIDE", "SETGID", "SETUID"],
                "security_opt": ["no-new-privileges:true"], "pids_limit": 128,
                "mem_limit": "768m", "cpus": "1.0",
                "environment": {"POSTGRES_DB": "coding_tools_gateway", "POSTGRES_USER": "gateway_bootstrap",
                                "POSTGRES_PASSWORD_FILE": "/run/secrets/postgres_password"},
                "secrets": ["postgres_password"],
                "volumes": ["postgres_data:/var/lib/postgresql/data"],
                "tmpfs": ["/tmp:rw,noexec,nosuid,size=16m", "/var/run/postgresql:rw,nosuid,size=16m"],
                "networks": ["database"],
                "command": ["postgres", "-c", "log_statement=none", "-c", "log_min_error_statement=panic",
                            "-c", "log_parameter_max_length=0", "-c", "log_parameter_max_length_on_error=0"],
                "healthcheck": {"test": ["CMD", "pg_isready", "-U", "gateway_bootstrap", "-d", "coding_tools_gateway"],
                                "interval": "10s", "timeout": "3s", "retries": 5},
            },
        },
        "networks": {"edge": {}, "database": {"internal": True}},
        "volumes": {"postgres_data": {}},
        "secrets": {name: {"file": "${" + env + ":?external protected secret file required}"}
                    for name, env in [("gateway_database_url", "GATEWAY_DATABASE_URL_FILE"),
                                      ("gateway_identity_key", "GATEWAY_IDENTITY_KEY_FILE"),
                                      ("postgres_password", "POSTGRES_PASSWORD_FILE")]},
    }


def assess_inventory(data: dict) -> dict:
    """Evaluate supplied facts only. Missing facts never become passing evidence."""
    blockers = ["GATEWAY_APPLICATION_INTEGRATION_PENDING", "REAL_HOST_ACCEPTANCE_PENDING"]
    os_name, version = data.get("os_id"), str(data.get("os_version", ""))
    if os_name == "centos-stream" and version == "8":
        blockers.append("HOST_OS_EOL_CENTOS_STREAM_8")
    elif data.get("os_security_support_verified") is not True:
        blockers.append("HOST_SECURITY_SUPPORT_UNVERIFIED")
    engine = str(data.get("docker_engine_version", ""))
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", engine):
        blockers.append("DOCKER_ENGINE_VERSION_UNVERIFIED")
    elif tuple(map(int, engine.split("."))) < (28, 0, 0):
        blockers.append("DOCKER_LOOPBACK_PUBLISH_L2_RISK")
    for field, code in [("upstream_port_available", "UPSTREAM_PORT_UNVERIFIED"),
                        ("prefix_routes_available", "ROUTE_COLLISION_UNVERIFIED"),
                        ("tls_verified", "TLS_UNVERIFIED"),
                        ("waf_protocol_verified", "WAF_PROTOCOL_UNVERIFIED"),
                        ("external_port_isolation_verified", "PORT_ISOLATION_UNVERIFIED")]:
        if data.get(field) is not True:
            blockers.append(code)
    return {"status": "BLOCKED_FOR_PRODUCTION", "blockers": blockers,
            "facts_are_user_reported": True, "changes_applied": False,
            "compose_version_is_not_engine_version": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", default=DEFAULT_DOMAIN)
    parser.add_argument("--connector-id", required=True)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    validate(args.domain, args.connector_id, args.port)
    nginx = nginx_locations(args.domain, args.connector_id, args.port)
    compose = compose_blueprint(args.domain, args.connector_id, args.port)
    # Only create a fresh output directory. No force, overwrite or privileged operation.
    args.output.mkdir(mode=0o700, parents=False, exist_ok=False)
    for name, text in [("nginx-locations.review.conf", nginx),
                       ("compose.blueprint.json", json.dumps(compose, indent=2) + "\n"),
                       ("NOT_DEPLOYABLE.txt", "Round 2 contains a library, not a public Gateway. Do not apply these review artifacts.\n")]:
        fd = os.open(args.output / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
    print(json.dumps({"rendered": True, "applied": False, "deployable": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
