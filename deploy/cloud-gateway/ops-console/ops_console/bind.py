"""Loopback bind enforcement (T-OPS-01 / FR-BIND-*)."""
from __future__ import annotations

import ipaddress
import re
from typing import Tuple

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "[::1]"})
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18765


class BindError(ValueError):
    def __init__(self, code: str = "bind_must_be_loopback"):
        super().__init__(code)
        self.code = code


def parse_bind(value: str) -> Tuple[str, int]:
    """Parse host:port; raise BindError if host is not loopback."""
    if not isinstance(value, str) or not value.strip():
        raise BindError("bind_must_be_loopback")
    value = value.strip()
    # IPv6 bracket form [::1]:port
    m = re.fullmatch(r"\[([^\]]+)\]:(\d{1,5})", value)
    if m:
        host, port_s = m.group(1), m.group(2)
    else:
        if value.count(":") != 1:
            # bare host without port, or malformed
            if value in ("0.0.0.0", "::", "[::]"):
                raise BindError("bind_must_be_loopback")
            raise BindError("bind_must_be_loopback")
        host, port_s = value.rsplit(":", 1)
    try:
        port = int(port_s)
    except ValueError as exc:
        raise BindError("bind_must_be_loopback") from exc
    if not (1 <= port <= 65535):
        raise BindError("bind_must_be_loopback")
    return normalize_loopback_host(host), port


def normalize_loopback_host(host: str) -> str:
    host = host.strip().lower()
    if host in ("localhost",):
        return "127.0.0.1"
    if host in ("::1", "[::1]"):
        return "::1"
    if host in ("0.0.0.0", "::", "[::]"):
        raise BindError("bind_must_be_loopback")
    try:
        addr = ipaddress.ip_address(host)
    except ValueError as exc:
        raise BindError("bind_must_be_loopback") from exc
    if not addr.is_loopback:
        raise BindError("bind_must_be_loopback")
    # Prefer canonical IPv4 string for 127.0.0.1
    if addr.version == 4:
        return str(addr)
    return "::1"


def assert_loopback_bind(host: str, port: int | None = None) -> Tuple[str, int]:
    """Validate host (and optional port); return (host, port)."""
    if host in ("0.0.0.0", "::", "[::]"):
        raise BindError("bind_must_be_loopback")
    host_n = normalize_loopback_host(host)
    p = DEFAULT_PORT if port is None else int(port)
    if not (1 <= p <= 65535):
        raise BindError("bind_must_be_loopback")
    return host_n, p


def is_loopback_bind_string(value: str) -> bool:
    """True if value looks like loopback host:port (gateway config bind)."""
    try:
        parse_bind(value)
        return True
    except BindError:
        return False
