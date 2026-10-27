"""Bounded complete hardlink census anchored to one open compiler-input inode."""
from __future__ import annotations
import errno
import os
from pathlib import Path

from exact_build_audit import need


def file_identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns, info.st_nlink)


def raise_walk_error(error):
    raise error


def verify_alias_census(fd, before, root):
    """Retry only an incomplete ENOENT census; never accept partial alias counts."""
    anchored = file_identity(before)
    for attempt in range(2):
        need(file_identity(os.fstat(fd)) == anchored, 'file_changed_during_read')
        aliases = 0
        try:
            for base, dirs, files in os.walk(root, followlinks=False, onerror=raise_walk_error):
                need(all(not (Path(base) / name).is_symlink() for name in dirs),
                     'linked_target_directory')
                for name in files:
                    item = (Path(base) / name).stat(follow_symlinks=False)
                    if (item.st_dev, item.st_ino) == (before.st_dev, before.st_ino):
                        aliases += 1
        except FileNotFoundError as exc:
            need(file_identity(os.fstat(fd)) == anchored, 'file_changed_during_read')
            if exc.errno != errno.ENOENT or attempt == 1:
                raise
            continue
        need(file_identity(os.fstat(fd)) == anchored, 'file_changed_during_read')
        need(aliases == before.st_nlink, 'hardlink_alias_outside_target')
        return
