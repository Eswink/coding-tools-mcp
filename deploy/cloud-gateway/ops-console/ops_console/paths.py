"""Workspace-root path safety (T-OPS-03 / FR-CFG-2)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Union

PathLike = Union[str, Path]


class PathError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def ensure_workspace_root(root: PathLike) -> Path:
    root = Path(root)
    if not root.is_absolute():
        raise PathError("workspace_root_must_be_absolute")
    if any(part == ".." for part in root.parts):
        raise PathError("workspace_root_must_be_absolute")
    # Resolve without following final component if missing: resolve parent
    try:
        resolved = root.resolve(strict=False)
    except OSError as exc:
        raise PathError("workspace_root_unresolvable") from exc
    if not resolved.is_dir():
        raise PathError("workspace_root_must_be_directory")
    return resolved


def resolve_rel(workspace_root: Path, rel: str, *, must_exist: bool = False) -> Path:
    """Resolve a relative path under workspace_root; reject escapes/symlinks out."""
    if not isinstance(rel, str) or not rel:
        raise PathError("path_must_be_relative")
    if os.path.isabs(rel):
        raise PathError("path_must_be_relative")
    # Reject backslash-absolute and Windows drive forms early
    if rel.startswith(("/", "\\")) or (len(rel) >= 2 and rel[1] == ":"):
        raise PathError("path_must_be_relative")
    parts = Path(rel).parts
    if any(p == ".." for p in parts):
        raise PathError("path_escape_denied")
    candidate = (workspace_root / rel)
    # Walk components with NOFOLLOW to detect symlink escape
    cur = workspace_root
    for part in Path(rel).parts:
        nxt = cur / part
        if os.path.lexists(nxt):
            st = os.lstat(nxt)
            if os.path.islink(nxt):
                target = Path(os.path.realpath(nxt))
                try:
                    target.relative_to(workspace_root)
                except ValueError as exc:
                    raise PathError("path_symlink_denied") from exc
            cur = Path(os.path.realpath(nxt)) if not os.path.islink(nxt) else Path(os.path.realpath(nxt))
            try:
                cur.relative_to(workspace_root)
            except ValueError as exc:
                raise PathError("path_symlink_denied") from exc
        else:
            # Intermediate missing: only OK if not must_exist and this is last or parents will be created by caller
            cur = nxt
            try:
                # Ensure logical path still under root
                cur.resolve(strict=False).relative_to(workspace_root)
            except ValueError as exc:
                raise PathError("path_escape_denied") from exc
    final = (workspace_root / rel)
    try:
        final_resolved = final.resolve(strict=False)
        final_resolved.relative_to(workspace_root)
    except ValueError as exc:
        raise PathError("path_escape_denied") from exc
    if must_exist:
        if not os.path.lexists(final):
            raise PathError("path_not_found")
        if os.path.islink(final):
            target = Path(os.path.realpath(final))
            try:
                target.relative_to(workspace_root)
            except ValueError as exc:
                raise PathError("path_symlink_denied") from exc
        if not final.is_file() or final.is_symlink():
            # After realpath check: must be regular file
            st = os.lstat(final)
            import stat as statmod
            if statmod.S_ISLNK(st.st_mode):
                raise PathError("path_symlink_denied")
            if not statmod.S_ISREG(st.st_mode):
                raise PathError("path_not_regular_file")
    return final
