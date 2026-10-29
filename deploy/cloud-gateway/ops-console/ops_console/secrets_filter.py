"""Secret key stripping for config API responses (T-OPS-02 / FR-CFG-4)."""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

SECRET_KEYS = frozenset({
    "database_url",
    "identity_key",
    "password",
    "client_secret",
    "token",
    "pkcs8",
    "secrets",
    "secret",
})

PUBLIC_CONFIG_KEYS = frozenset({
    "origin",
    "prefix",
    "connector",
    "owner_subject",
    "client_id",
    "redirect_uri",
    "client_authentication",
    "bind",
})

# Boolean-ish / enum fields for FR-UI
BOOL_FIELDS: Dict[str, type] = {}  # config has no native bools yet; UI may add toggles for future flags
ENUM_FIELDS = {
    "client_authentication": ("public", "confidential"),
}


def strip_secrets(data: Any) -> Tuple[Any, List[str]]:
    """Return (sanitized_copy, stripped_key_names). Never returns secret values."""
    stripped: List[str] = []
    if not isinstance(data, dict):
        return data, stripped
    out: Dict[str, Any] = {}
    for key, value in data.items():
        if key in SECRET_KEYS or str(key).lower() in SECRET_KEYS:
            stripped.append(str(key))
            continue
        if isinstance(value, dict):
            nested, nested_stripped = strip_secrets(value)
            out[key] = nested
            stripped.extend(f"{key}.{s}" for s in nested_stripped)
        else:
            out[key] = value
    return out, stripped


def reject_secret_keys_in_body(data: Any) -> List[str]:
    """Return list of forbidden keys present (for PUT rejection)."""
    if not isinstance(data, dict):
        return []
    found = []
    for key in data:
        if key in SECRET_KEYS or str(key).lower() in SECRET_KEYS:
            found.append(str(key))
    return found
