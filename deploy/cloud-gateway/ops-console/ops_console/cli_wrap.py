"""Allowlisted coding-tools-gateway CLI wrappers (FR-CLI-*)."""
from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .paths import PathError, resolve_rel

ALLOWED_COMMANDS = frozenset({"check-config", "register-client", "invite-device"})
SECRET_ARGV_PATTERNS = re.compile(r"(password|secret|token|database_url|identity_key)=", re.I)


class CliError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def find_gateway_bin(explicit: Optional[str] = None) -> Path:
    if explicit:
        p = Path(explicit)
        if p.is_file() and os.access(p, os.X_OK):
            return p
        raise CliError("gateway_bin_missing")
    env = os.environ.get("CODING_TOOLS_GATEWAY_BIN")
    if env:
        p = Path(env)
        if p.is_file() and os.access(p, os.X_OK):
            return p
    # search PATH
    for folder in os.environ.get("PATH", "").split(os.pathsep):
        cand = Path(folder) / "coding-tools-gateway"
        if cand.is_file() and os.access(cand, os.X_OK):
            return cand
    # known workspace build artifacts (dev only)
    for cand in (
        Path("/workspace/target-s1-gw/debug/coding-tools-gateway"),
        Path("/workspace/verify-s1-target-gw/debug/coding-tools-gateway"),
    ):
        if cand.is_file() and os.access(cand, os.X_OK):
            return cand
    raise CliError("gateway_bin_missing")


def _validate_secrets_file(workspace_root: Path, rel: str) -> Path:
    path = resolve_rel(workspace_root, rel, must_exist=True)
    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode):
        raise CliError("secrets_file_symlink_denied")
    if not stat.S_ISREG(st.st_mode):
        raise CliError("secrets_file_not_regular")
    mode = stat.S_IMODE(st.st_mode)
    # Must not be group/world readable or writable: prefer 0600/0400
    if mode & 0o077:
        raise CliError("secrets_file_mode_not_private")
    if st.st_nlink != 1:
        raise CliError("secrets_file_hardlinked")
    return path


def _run(argv: Sequence[str], timeout: int = 60) -> Dict[str, Any]:
    # Guard: never put secrets in argv beyond --secrets-file PATH
    joined = " ".join(argv)
    if SECRET_ARGV_PATTERNS.search(joined):
        raise CliError("secrets_in_argv_denied")
    proc = subprocess.run(list(argv), capture_output=True, text=True, timeout=timeout, check=False)
    # Filter stdout/stderr: drop lines that look like secrets
    def filter_text(text: str) -> str:
        lines = []
        for line in (text or "").splitlines():
            low = line.lower()
            if any(k in low for k in ("database_url", "identity_key", "client_secret", "password=", "token")):
                lines.append("[redacted]")
            else:
                lines.append(line[:500])
        return "\n".join(lines)[:4000]

    return {
        "exit_code": proc.returncode,
        "stdout_preview": filter_text(proc.stdout),
        "stderr_preview": filter_text(proc.stderr),
    }


def check_config(workspace_root: Path, config_rel: str, gateway_bin: Optional[str] = None) -> Dict[str, Any]:
    bin_path = find_gateway_bin(gateway_bin)
    cfg = resolve_rel(workspace_root, config_rel, must_exist=True)
    result = _run([str(bin_path), "check-config", "--config", str(cfg)])
    ok = result["exit_code"] == 0
    return {
        "ok": ok,
        "exit_code": result["exit_code"],
        "result_class": "ok" if ok else "check_config_failed",
        "stdout_preview": result["stdout_preview"],
        "stderr_preview": result["stderr_preview"],
    }


def register_client(
    workspace_root: Path,
    config_rel: str,
    secrets_file_rel: str,
    gateway_bin: Optional[str] = None,
) -> Dict[str, Any]:
    bin_path = find_gateway_bin(gateway_bin)
    cfg = resolve_rel(workspace_root, config_rel, must_exist=True)
    secrets = _validate_secrets_file(workspace_root, secrets_file_rel)
    result = _run([
        str(bin_path), "register-client",
        "--config", str(cfg),
        "--secrets-file", str(secrets),
    ])
    # Never echo secrets; only exit metadata
    return {
        "ok": result["exit_code"] == 0,
        "exit_code": result["exit_code"],
        "result_class": "ok" if result["exit_code"] == 0 else "register_client_failed",
    }


def _require_invite_output_rel(output_rel: str) -> str:
    """S3: invite output_rel must be under devices/ (normalized); reject abs/escape/empty."""
    if not isinstance(output_rel, str) or not output_rel.strip():
        raise PathError("output_rel_must_be_under_devices")
    # Normalize separators for prefix / escape checks; keep logical relative form.
    norm = output_rel.replace("\\", "/").strip()
    if os.path.isabs(output_rel) or os.path.isabs(norm):
        raise PathError("output_rel_must_be_under_devices")
    if norm.startswith("/") or (len(norm) >= 2 and norm[1] == ":"):
        raise PathError("output_rel_must_be_under_devices")
    if not norm.startswith("devices/"):
        raise PathError("output_rel_must_be_under_devices")
    rest = norm[len("devices/") :]
    if not rest or rest.endswith("/"):
        raise PathError("output_rel_must_be_under_devices")
    parts = Path(norm).parts
    if any(p == ".." for p in parts):
        raise PathError("output_rel_must_be_under_devices")
    return norm


def invite_device(
    workspace_root: Path,
    config_rel: str,
    secrets_file_rel: str,
    output_rel: str,
    gateway_bin: Optional[str] = None,
) -> Dict[str, Any]:
    # Validate output_rel before bin/config so bad paths fail fast with a fixed code.
    output_rel = _require_invite_output_rel(output_rel)
    bin_path = find_gateway_bin(gateway_bin)
    cfg = resolve_rel(workspace_root, config_rel, must_exist=True)
    secrets = _validate_secrets_file(workspace_root, secrets_file_rel)
    out = resolve_rel(workspace_root, output_rel, must_exist=False)
    out.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(out.parent, 0o700)
    result = _run([
        str(bin_path), "invite-device",
        "--config", str(cfg),
        "--secrets-file", str(secrets),
        "--output-file", str(out),
    ])
    meta: Dict[str, Any] = {
        "ok": result["exit_code"] == 0,
        "exit_code": result["exit_code"],
        "output_basename": out.name,
    }
    if out.exists():
        try:
            os.chmod(out, 0o600)
            st = out.stat()
            from datetime import datetime, timezone
            meta["mtime"] = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).astimezone().isoformat(timespec="seconds")
        except OSError:
            pass
    return meta
