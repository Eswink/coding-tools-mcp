#!/usr/bin/env python3
"""Single evidence gate for installed_desktop_bytes_verified (engineering-only).

Carrier: one controlled-root unpack of the authenticated desktop.deb data.tar
(the bytes `dpkg-deb -x` would lay down), verified in place with no-follow reads.
No subprocess, no maintainer scripts, no dpkg database, no real machine.
"""
from __future__ import annotations
import hashlib
import os
import re
import stat

from exact_build_audit import digest, need
import desktop_glib_deb as deb

CARRIER = 'controlled-root-unpack-v1'
MAX_FILE = deb.MAX_ELF
LIMITATIONS = (
    'controlled-root unpack of DEB data.tar only (dpkg-deb -x equivalent); not a dpkg install',
    'maintainer scripts not run; no dpkg database, triggers, alternatives or postinst effects',
    'not a real machine or OS install; no runtime, native linker or system libglib acceptance',
    'no security, release or publish approval; engineering_only evidence',
)
SUMMARY_KEYS = {'carrier', 'installed_path', 'package_sha256', 'payload_sha256', 'installed_sha256',
                'installed_size', 'file_digests', 'symlinks_followed', 'maintainer_scripts_run',
                'dpkg_install', 'real_machine', 'limitations'}
HEX64 = re.compile('[0-9a-f]{64}')


def _mode(name):
    return 0o755 if name in deb.DATA_DIRS or name == deb.BINARY else 0o644


def _open_dir(parent, name):
    return os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)


def _root_fd(root):
    root = os.path.abspath(os.fspath(root))
    need(all(p not in ('.', '..') for p in root.split('/')), 'unsafe_installed_root')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in [p for p in root.split('/') if p]:
            child = _open_dir(fd, part)
            os.close(fd)
            fd = child
    except OSError:
        os.close(fd)
        need(False, 'unsafe_installed_root')
    info = os.fstat(fd)
    need(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid(), 'unsafe_installed_root')
    return fd


def _expected(package, version):
    files, dirs, _ = deb.deb_data(package, version)
    need(set(files) == deb.DATA_FILES and dirs <= deb.DATA_DIRS, 'unexpected_installed_inventory')
    return files


def unpack_controlled_root(package: bytes, version: str, root) -> None:
    """Lay down the reviewed DEB data files under an empty owned root (no dpkg, no scripts)."""
    files = _expected(package, version)
    fd = _root_fd(root)
    try:
        need(not os.listdir(fd), 'installed_root_not_empty')
        for name in sorted(deb.DATA_DIRS, key=lambda n: (n.count('/'), n)):
            *parents, leaf = name.split('/')
            cur = _walk_to(fd, parents)
            try: os.mkdir(leaf, 0o755, dir_fd=cur)
            finally: os.close(cur)
        for name, body in sorted(files.items()):
            *parents, leaf = name.split('/')
            cur = _walk_to(fd, parents)
            try:
                out = os.open(leaf, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=cur)
            finally: os.close(cur)
            try:
                view = memoryview(body)
                while view:
                    n = os.write(out, view)
                    need(n > 0, 'installed_write_failed')
                    view = view[n:]
                os.fchmod(out, _mode(name))
                os.fsync(out)
            finally: os.close(out)
    finally:
        os.close(fd)


def _walk_to(fd, parts):
    cur = os.dup(fd)
    for part in parts:
        child = _open_dir(cur, part)
        os.close(cur)
        cur = child
    return cur


def _census(fd, prefix=''):
    """No-follow inventory: every entry must be a reviewed dir or single-link regular file."""
    found = {}
    for name in sorted(os.listdir(fd)):
        rel = prefix + name
        need(len(found) < deb.MAX_ENTRIES and len(rel.encode()) <= deb.MAX_PATH, 'installed_resource_limit')
        info = os.stat(name, dir_fd=fd, follow_symlinks=False)
        need(not stat.S_ISLNK(info.st_mode), 'installed_symlink')
        if stat.S_ISDIR(info.st_mode):
            need(rel in deb.DATA_DIRS, 'unexpected_installed_path')
            child = _open_dir(fd, name)
            try: found.update(_census(child, rel + '/'))
            finally: os.close(child)
            found[rel] = ('dir', info)
        else:
            need(stat.S_ISREG(info.st_mode), 'installed_special_file')
            need(rel in deb.DATA_FILES, 'unexpected_installed_path')
            need(info.st_nlink == 1, 'installed_hardlink')
            found[rel] = ('file', info)
    return found


def _read_file(fd, rel):
    *parents, leaf = rel.split('/')
    cur = _walk_to(fd, parents)
    try: f = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=cur)
    finally: os.close(cur)
    try:
        before = os.fstat(f)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size <= MAX_FILE,
             'installed_file_changed')
        chunks, size = [], 0
        while chunk := os.read(f, 1024**2):
            size += len(chunk)
            need(size <= MAX_FILE, 'installed_resource_limit')
            chunks.append(chunk)
        after = os.fstat(f)
        need(size == before.st_size and (before.st_ino, before.st_mtime_ns, before.st_size) ==
             (after.st_ino, after.st_mtime_ns, after.st_size), 'installed_file_changed')
        return b''.join(chunks), before
    finally: os.close(f)


def verify_installed_root(root, package: bytes, version: str, deb_summary: dict) -> dict:
    """Byte-exact DEB payload == controlled installed root, bound to the verified DEB summary."""
    need(type(deb_summary) is dict and deb_summary.get('payload_path') == deb.BINARY and
         deb_summary.get('package_sha256') == digest(package), 'installed_wrong_deb_binding')
    files = _expected(package, version)
    need(digest(files[deb.BINARY]) == deb_summary.get('payload_sha256'), 'installed_wrong_deb_binding')
    fd = _root_fd(root)
    try:
        found = _census(fd)
        need({k for k, v in found.items() if v[0] == 'file'} == deb.DATA_FILES, 'missing_installed_path')
        digests = {}
        for rel in sorted(deb.DATA_FILES):
            body, info = _read_file(fd, rel)
            need(body == files[rel], 'installed_bytes_mismatch')
            need(stat.S_IMODE(info.st_mode) == _mode(rel), 'installed_mode_mismatch')
            digests[rel] = hashlib.sha256(body).hexdigest()
        need(_census(fd).keys() == found.keys(), 'installed_root_changed')
    finally:
        os.close(fd)
    deb.elf_layout(files[deb.BINARY])
    summary = dict(carrier=CARRIER, installed_path=deb.BINARY, package_sha256=deb_summary['package_sha256'],
                   payload_sha256=deb_summary['payload_sha256'], installed_sha256=digests[deb.BINARY],
                   installed_size=len(files[deb.BINARY]), file_digests=digests, symlinks_followed=False,
                   maintainer_scripts_run=False, dpkg_install=False, real_machine=False,
                   limitations=list(LIMITATIONS))
    return dict(installed_desktop_bytes_verified=installed_gate(summary, deb_summary['package_sha256']),
                installed_desktop_bytes=summary)


def installed_gate(summary, package_sha256) -> bool:
    """The only producer of installed_desktop_bytes_verified=True; raises on any unbound summary.

    package_sha256 is mandatory and must come from the caller's own authenticated DEB verification
    (verify_deb); a summary is never self-authenticating, so a self-consistent forgery is rejected."""
    need(type(package_sha256) is str and HEX64.fullmatch(package_sha256) is not None, 'unbound_installed_summary')
    need(type(summary) is dict and set(summary) == SUMMARY_KEYS, 'invalid_installed_summary')
    need(summary['carrier'] == CARRIER and summary['installed_path'] == deb.BINARY and
         summary['limitations'] == list(LIMITATIONS) and
         all(summary[k] is False for k in ('symlinks_followed', 'maintainer_scripts_run', 'dpkg_install',
                                           'real_machine')), 'invalid_installed_summary')
    hashes = summary['file_digests']
    need(type(hashes) is dict and set(hashes) == deb.DATA_FILES and
         all(type(v) is str and HEX64.fullmatch(v) for v in hashes.values()) and
         all(type(summary[k]) is str and HEX64.fullmatch(summary[k])
             for k in ('package_sha256', 'payload_sha256', 'installed_sha256')), 'invalid_installed_summary')
    need(summary['installed_sha256'] == summary['payload_sha256'] == hashes[deb.BINARY] and
         type(summary['installed_size']) is int and 64 <= summary['installed_size'] <= MAX_FILE,
         'unbound_installed_summary')
    need(summary['package_sha256'] == package_sha256, 'unbound_installed_summary')
    return True


def claim(proof: dict, package_sha256):
    """Consumer view: (flag, summary-or-None). True only via installed_gate bound to an authenticated
    package_sha256 supplied by the caller (GLib DEB lane); consumers without one must stay fail-closed."""
    flag, summary = proof.get('installed_desktop_bytes_verified'), proof.get('installed_desktop_bytes')
    if flag is False:
        need(summary is None, 'installed_summary_without_claim')
        return False, None
    need(flag is True, 'invalid_installed_claim')
    return installed_gate(summary, package_sha256), {k: summary[k] for k in (
        'carrier', 'installed_path', 'package_sha256', 'payload_sha256', 'installed_sha256')}
