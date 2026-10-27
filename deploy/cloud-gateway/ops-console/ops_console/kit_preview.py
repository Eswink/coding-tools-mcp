"""Read-only kit.py plan / render_diff wrapper (FR-KIT-*)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional


class KitPreviewError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def default_kit_py() -> Path:
    # ops-console lives at deploy/cloud-gateway/ops-console/
    here = Path(__file__).resolve().parent.parent
    return here.parent / "kit" / "kit.py"


def run_kit_plan(kit_py: Optional[Path] = None) -> Dict[str, Any]:
    kit = Path(kit_py) if kit_py else default_kit_py()
    if not kit.is_file():
        raise KitPreviewError("kit:kit_py_missing")
    proc = subprocess.run(
        [sys.executable, str(kit), "plan"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        env={**os.environ, "PYTHONPATH": str(kit.parent.parent)},
    )
    if proc.returncode != 0:
        code = _extract_kit_error(proc.stdout) or "kit:plan_failed"
        raise KitPreviewError(code)
    try:
        payload = json.loads(proc.stdout)
    except ValueError as exc:
        raise KitPreviewError("kit:plan_unreadable") from exc
    # Summarize without dumping huge blobs
    steps = payload.get("steps") if isinstance(payload, dict) else None
    summary_lines: List[str] = []
    if isinstance(steps, list):
        for step in steps:
            if isinstance(step, dict):
                summary_lines.append(f"- {step.get('id')}: {step.get('action')}")
    diff = "\n".join(summary_lines)
    return {"ok": True, "action": "plan", "diff": diff, "codes": [], "raw_keys": list(payload) if isinstance(payload, dict) else []}


def run_kit_render_diff(
    workspace_root: Path,
    *,
    private_root_rel: str = ".",
    domain: str = "gateway.example.invalid",
    connector: str = "00000000-0000-0000-0000-000000000001",
    port: int = 28880,
    gateway_image: str = "coding-tools-gateway:local",
    ingress_image: str = "coding-tools-ingress:local",
    postgres_image: str = "postgres:16-alpine",
    kit_py: Optional[Path] = None,
) -> Dict[str, Any]:
    """Render into a temp dir and return a text summary (filenames + sha), not secrets."""
    kit = Path(kit_py) if kit_py else default_kit_py()
    if not kit.is_file():
        raise KitPreviewError("kit:kit_py_missing")
    private_root = (workspace_root / private_root_rel).resolve()
    try:
        private_root.relative_to(workspace_root.resolve())
    except ValueError as exc:
        raise KitPreviewError("kit:private_root_escape") from exc
    with tempfile.TemporaryDirectory(prefix="ops-console-kit-") as tmp:
        out = Path(tmp) / "render-out"
        # kit.py requires output path to not exist and be absolute
        cmd = [
            sys.executable, str(kit), "render",
            "--private-root", str(private_root),
            "--output", str(out),
            "--domain", domain,
            "--connector", connector,
            "--gateway-image", gateway_image,
            "--ingress-image", ingress_image,
            "--postgres-image", postgres_image,
            "--port", str(port),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
        if proc.returncode != 0:
            code = _extract_kit_error(proc.stdout) or _extract_kit_error(proc.stderr) or "kit:render_failed"
            # Still allow plan-only style soft failure for incomplete private roots
            raise KitPreviewError(code if code.startswith("kit:") else f"kit:{code}")
        lines = ["# render output summary"]
        if out.is_dir():
            for name in sorted(os.listdir(out)):
                p = out / name
                if p.is_file():
                    lines.append(f"{name}  bytes={p.stat().st_size}")
        # Include stdout JSON keys only
        try:
            payload = json.loads(proc.stdout)
            if isinstance(payload, dict) and "files" in payload:
                for fname, digest in sorted(payload["files"].items()):
                    lines.append(f"sha256 {fname}={digest}")
        except ValueError:
            pass
        return {"ok": True, "action": "render_diff", "diff": "\n".join(lines), "codes": []}


def _extract_kit_error(text: str) -> Optional[str]:
    if not text:
        return None
    try:
        data = json.loads(text.strip().splitlines()[-1])
        if isinstance(data, dict) and isinstance(data.get("error"), str):
            err = data["error"]
            return err if err.startswith("kit:") else f"kit:{err}"
    except (ValueError, IndexError):
        pass
    return None
