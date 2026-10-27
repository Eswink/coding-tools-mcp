"""Config GET/PUT under workspace_root (FR-CFG-*)."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Tuple

from .bind import is_loopback_bind_string
from .paths import PathError, resolve_rel
from .secrets_filter import (
    PUBLIC_CONFIG_KEYS,
    reject_secret_keys_in_body,
    strip_secrets,
)


class ConfigError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def read_config(workspace_root: Path, rel: str = "config.json") -> Dict[str, Any]:
    path = resolve_rel(workspace_root, rel, must_exist=True)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigError("config_unreadable_json") from exc
    if not isinstance(raw, dict):
        raise ConfigError("config_not_object")
    data, stripped = strip_secrets(raw)
    return {
        "ok": True,
        "path": rel,
        "data": data,
        "stripped_secret_keys": stripped,
    }


def validate_public_config(data: Dict[str, Any]) -> None:
    if not isinstance(data, dict):
        raise ConfigError("config_not_object")
    forbidden = reject_secret_keys_in_body(data)
    if forbidden:
        raise ConfigError("secrets_not_allowed_in_config_api")
    # Allow subset or exact public keys; reject unknown non-public
    unknown = [k for k in data if k not in PUBLIC_CONFIG_KEYS]
    if unknown:
        raise ConfigError("config_unknown_keys")
    bind = data.get("bind")
    if bind is not None and not is_loopback_bind_string(str(bind)):
        raise ConfigError("config_bind_must_be_loopback")
    origin = data.get("origin")
    if origin is not None:
        if not isinstance(origin, str) or not re.fullmatch(r"https://[a-z0-9.-]+", origin):
            raise ConfigError("config_origin_not_https_host")
    prefix = data.get("prefix")
    if prefix is not None and prefix != "/coding-tools":
        raise ConfigError("config_prefix_mismatch")
    auth = data.get("client_authentication")
    if auth is not None and auth not in ("public", "confidential"):
        raise ConfigError("config_client_authentication_invalid")


def write_config(workspace_root: Path, rel: str, data: Dict[str, Any]) -> Dict[str, Any]:
    validate_public_config(data)
    # Ensure parent exists under root
    path = resolve_rel(workspace_root, rel, must_exist=False)
    parent = path.parent
    if not parent.exists():
        # Only create if parent is still under workspace_root and is not root itself needing mkdir chain within root
        try:
            parent.relative_to(workspace_root)
        except ValueError as exc:
            raise ConfigError("path_escape_denied") from exc
        parent.mkdir(parents=True, exist_ok=True)
        os.chmod(parent, 0o700)
    # If existing file has secret keys, preserve them on disk but never accept new ones from API
    existing: Dict[str, Any] = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(existing, dict):
                existing = {}
        except (OSError, ValueError):
            existing = {}
    from .secrets_filter import SECRET_KEYS
    merged = dict(data)
    for key, value in existing.items():
        if key in SECRET_KEYS and key not in merged:
            merged[key] = value  # preserve on disk only; never returned
    text = json.dumps({k: merged[k] for k in sorted(merged)}, indent=2) + "\n"
    # Write via temp + replace
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, text.encode("utf-8"))
    finally:
        os.close(fd)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    os.chmod(path, 0o600)
    return {"ok": True, "path": rel, "bytes": len(text.encode("utf-8"))}
