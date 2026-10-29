"""Local invitation/connection artifact listing (requirements §5). No DB."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

INVITE_RE = re.compile(r"^invitation.*\.json$", re.IGNORECASE)
CONN_RE = re.compile(r"^connection.*\.json$", re.IGNORECASE)
UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
SECRETISH = frozenset({"token", "secret", "client_secret", "password", "identity_key", "database_url", "pkcs8"})


def _mtime_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().isoformat(timespec="seconds")


def _kind(name: str) -> str:
    if INVITE_RE.match(name):
        return "invitation"
    if CONN_RE.match(name):
        return "connection"
    return "unknown"


def _safe_device_uuid(path: Path) -> Optional[str]:
    """Best-effort non-secret device UUID from local JSON; never return tokens."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    for key in ("device_uuid", "device_id", "device"):
        if key in SECRETISH:
            continue
        val = data.get(key)
        if isinstance(val, str) and UUID_RE.match(val):
            return val
        if isinstance(val, dict):
            nested = val.get("uuid") or val.get("id")
            if isinstance(nested, str) and UUID_RE.match(nested):
                return nested
    return None


def list_local_devices(workspace_root: Path, artifacts_rel: str = "devices") -> Dict[str, Any]:
    root = workspace_root / artifacts_rel
    if not root.exists() or not root.is_dir():
        return {"ok": True, "items": [], "created": False}
    items: List[Dict[str, Any]] = []
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return {"ok": True, "items": [], "created": True}
    for name in names:
        if not (INVITE_RE.match(name) or CONN_RE.match(name)):
            continue
        path = root / name
        try:
            st = os.lstat(path)
        except OSError:
            continue
        if os.path.islink(path):
            continue
        import stat as statmod
        if not statmod.S_ISREG(st.st_mode):
            continue
        items.append({
            "basename": name,
            "kind": _kind(name),
            "mtime": _mtime_iso(st.st_mtime),
            "size": st.st_size,
            "device_uuid": _safe_device_uuid(path),
        })
    return {"ok": True, "items": items, "created": True}
