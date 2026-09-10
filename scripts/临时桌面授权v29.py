"""CI-only desktop access for one newly created logon session, never a user group.

Window-station/desktop ACL entries are added without inheritance or ACL/owner
write rights. Existing ACEs are preserved; cleanup removes only the exact ACEs
created here. Product tokens, registry policies and sandbox settings are untouched.
"""
from __future__ import annotations
import ctypes as c
from ctypes import wintypes as w
import hashlib
import os
import re
import struct
import sys

LOGON_SID = re.compile(r'S-1-5-5-[0-9]+-[0-9]+')
WINDOW_RIGHTS = 0x00020337  # READ_CONTROL + GUI data/atoms/clipboard; no EXIT/CREATE_DESKTOP.
DESKTOP_RIGHTS = 0x000201c7  # READ_CONTROL + window/menu/read/write/enum/switch; no hooks/journals.


def acl_entries(raw: bytes) -> list[bytes]:
    if len(raw) < 8:
        raise ValueError('truncated ACL')
    revision, _, size, count, _ = struct.unpack_from('<BBHHH', raw)
    if revision not in (2, 4) or not 8 <= size <= len(raw) <= 65535:
        raise ValueError('invalid ACL header')
    result, position = [], 8
    for _ in range(count):
        if position + 4 > size:
            raise ValueError('truncated ACE header')
        length = struct.unpack_from('<H', raw, position + 2)[0]
        if length < 4 or length % 4 or position + length > size:
            raise ValueError('invalid ACE length')
        result.append(raw[position:position + length]); position += length
    return result


def pack_acl(original: bytes, entries: list[bytes]) -> bytes:
    size = 8 + sum(map(len, entries))
    if size > 65535 or len(entries) > 65535:
        raise ValueError('ACL size limit')
    output = struct.pack('<BBHHH', original[0], 0, size, len(entries), 0) + b''.join(entries)
    acl_entries(output)
    return output


def logon_ace(sid: bytes, rights: int) -> bytes:
    # SID revision, subauthority count, NT authority, first subauthority 5.
    if (len(sid) != 20 or sid[:8] != bytes([1, 3, 0, 0, 0, 0, 0, 5])
        or struct.unpack_from('<I', sid, 8)[0] != 5
        or rights not in (WINDOW_RIGHTS, DESKTOP_RIGHTS)):
        raise ValueError('only bounded logon-session GUI rights are allowed')
    return struct.pack('<BBHI', 0, 0, 8 + len(sid), rights) + sid


def add_owned_ace(raw: bytes, ace: bytes) -> bytes:
    entries = acl_entries(raw)
    if any(entry[8:] == ace[8:] for entry in entries if len(entry) >= 8):
        raise ValueError('new logon SID unexpectedly already present')
    index = next((i for i, value in enumerate(entries) if value[1] & 0x10), len(entries))
    entries.insert(index, ace)
    return pack_acl(raw, entries)


def remove_owned_ace(raw: bytes, ace: bytes) -> bytes:
    entries = acl_entries(raw)
    if entries.count(ace) != 1:
        raise RuntimeError('owned desktop ACE missing or duplicated')
    entries.remove(ace)
    return pack_acl(raw, entries)


class Group(c.Structure):
    _fields_ = [('sid', c.c_void_p), ('attributes', w.DWORD)]


class Groups(c.Structure):
    _fields_ = [('count', w.DWORD), ('groups', Group * 1)]


class Mapping(c.Structure):
    _fields_ = [('read', w.DWORD), ('write', w.DWORD), ('execute', w.DWORD), ('all', w.DWORD)]


def object_mapping(rights: int) -> Mapping:
    # Win32 object-specific generic mappings are NOT the requested access mask.
    # These describe existing ACE interpretation; they do not grant permissions.
    if type(rights) is not int:
        raise ValueError('unknown GUI object mapping')
    if rights == WINDOW_RIGHTS:
        return Mapping(0x20303, 0x2001c, 0x20060, 0xf037f)
    if rights == DESKTOP_RIGHTS:
        return Mapping(0x20041, 0x200be, 0x20100, 0xf01ff)
    raise ValueError('unknown GUI object mapping')


class DesktopAccess:
    def __init__(self, api, token):
        if (sys.platform != 'win32' or os.environ.get('GITHUB_ACTIONS') != 'true'
            or os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted'
            or os.environ.get('GITHUB_REPOSITORY') != 'Eswink/coding-tools-mcp'):
            raise RuntimeError('desktop fixture restricted to this disposable hosted runner')
        self.api, self.token, self.resources, self.applied = api, token, [], []
        self.proof = {'target': r'WinSta0\Default', 'checks': [], 'owned_aces_removed': False}
        self.user = c.WinDLL('user32', use_last_error=True)
        def bind(dll, name, result, args):
            fn = getattr(dll, name); fn.restype, fn.argtypes = result, args
            setattr(self, name, fn)
        ptr = c.c_void_p
        bind(self.user, 'GetProcessWindowStation', w.HANDLE, [])
        bind(self.user, 'GetUserObjectInformationW', w.BOOL, [w.HANDLE, c.c_int, ptr, w.DWORD, c.POINTER(w.DWORD)])
        bind(self.user, 'OpenWindowStationW', w.HANDLE, [w.LPCWSTR, w.BOOL, w.DWORD])
        bind(self.user, 'OpenDesktopW', w.HANDLE, [w.LPCWSTR, w.DWORD, w.BOOL, w.DWORD])
        bind(self.user, 'CloseDesktop', w.BOOL, [w.HANDLE])
        bind(self.user, 'CloseWindowStation', w.BOOL, [w.HANDLE])
        bind(api.adv, 'GetSecurityInfo', w.DWORD, [w.HANDLE, c.c_int, w.DWORD, c.POINTER(ptr), c.POINTER(ptr), c.POINTER(ptr), c.POINTER(ptr), c.POINTER(ptr)])
        bind(api.adv, 'SetSecurityInfo', w.DWORD, [w.HANDLE, c.c_int, w.DWORD, ptr, ptr, ptr, ptr])
        bind(api.adv, 'DuplicateToken', w.BOOL, [w.HANDLE, c.c_int, c.POINTER(w.HANDLE)])
        bind(api.adv, 'AccessCheck', w.BOOL, [ptr, w.HANDLE, w.DWORD, c.POINTER(Mapping), ptr, c.POINTER(w.DWORD), c.POINTER(w.DWORD), c.POINTER(w.BOOL)])

    @staticmethod
    def code(value, name):
        if value:
            raise OSError(value, name + ' failed')

    def snapshot(self, handle, rights) -> tuple[bytes, bool]:
        sd, acl = c.c_void_p(), c.c_void_p()
        impersonation = w.HANDLE()
        try:
            # Owner/group are needed by AccessCheck; only DACL is ever changed.
            self.code(self.GetSecurityInfo(handle, 7, 1 | 2 | 4, None, None, c.byref(acl), None, c.byref(sd)), 'GetSecurityInfo')
            if not acl:
                raise RuntimeError('null desktop ACL is not supported')
            size = struct.unpack_from('<H', c.string_at(acl, 8), 2)[0]
            if not 8 <= size <= 65535:
                raise RuntimeError('invalid desktop ACL size')
            raw = c.string_at(acl, size); acl_entries(raw)
            self.api.check(self.DuplicateToken(self.token, 2, c.byref(impersonation)))
            privileges = c.create_string_buffer(4096)
            length, granted, status = w.DWORD(4096), w.DWORD(), w.BOOL()
            mapping = object_mapping(rights)
            self.api.check(self.AccessCheck(sd, impersonation, rights, c.byref(mapping),
                privileges, c.byref(length), c.byref(granted), c.byref(status)))
            return raw, bool(status.value)
        finally:
            if impersonation: self.api.CloseHandle(impersonation)
            if sd: self.api.LocalFree(sd)

    def replace_acl(self, handle, raw):
        acl_entries(raw)
        buffer = c.create_string_buffer(raw)
        self.code(self.SetSecurityInfo(handle, 7, 4, None, None, buffer, None), 'SetSecurityInfo')

    def apply(self):
        needed, current = w.DWORD(), self.api.check(self.GetProcessWindowStation())
        name = c.create_unicode_buffer(512)
        self.api.check(self.GetUserObjectInformationW(current, 2, name, c.sizeof(name), c.byref(needed)))
        self.proof['parent_station'] = name.value
        if name.value.casefold() != 'winsta0':
            raise RuntimeError('the hosted native test requires the interactive WinSta0 station')
        needed = w.DWORD()
        self.api.GetTokenInformation(self.token, 28, None, 0, c.byref(needed))
        if not c.sizeof(Groups) <= needed.value <= 65536:
            raise RuntimeError('invalid logon SID record size')
        buffer = c.create_string_buffer(needed.value)
        self.api.check(self.api.GetTokenInformation(self.token, 28, buffer, needed, c.byref(needed)))
        groups = c.cast(buffer, c.POINTER(Groups)).contents
        if groups.count != 1 or groups.groups[0].attributes & 0xc0000000 != 0xc0000000:
            raise RuntimeError('expected one Windows logon-session SID')
        pointer = groups.groups[0].sid
        if not LOGON_SID.fullmatch(self.api.sid_text(pointer)):
            raise RuntimeError('invalid ephemeral logon-session SID')
        sid = c.string_at(pointer, self.api.GetLengthSid(pointer))
        self.proof['logon_sid_sha256'] = hashlib.sha256(sid).hexdigest()
        station = self.api.check(self.OpenWindowStationW('WinSta0', False, 0x60000 | 0x337))
        self.resources.append((station, self.CloseWindowStation))
        desktop = self.api.check(self.OpenDesktopW('Default', 0, False, 0x60000 | 0x1c7))
        self.resources.append((desktop, self.CloseDesktop))
        for label, handle, rights in (('station', station, WINDOW_RIGHTS), ('desktop', desktop, DESKTOP_RIGHTS)):
            raw, before = self.snapshot(handle, rights)
            ace = logon_ace(sid, rights)
            updated = add_owned_ace(raw, ace)
            self.replace_acl(handle, updated)
            self.applied.append((label, handle, rights, ace))
            actual, after = self.snapshot(handle, rights)
            record = {'object': label, 'access_before': before, 'access_after': after,
                'rights': rights, 'original_acl_sha256': hashlib.sha256(raw).hexdigest()}
            self.proof['checks'].append(record)
            if acl_entries(actual) != acl_entries(updated) or not after:
                raise RuntimeError('desktop ACL readback or effective access validation failed')
        return self.proof

    def close(self):
        failures = []
        for label, handle, rights, ace in reversed(self.applied):
            try:
                current, _ = self.snapshot(handle, rights)
                restored = remove_owned_ace(current, ace)
                self.replace_acl(handle, restored)
                actual, _ = self.snapshot(handle, rights)
                if acl_entries(actual) != acl_entries(restored):
                    raise RuntimeError('desktop ACL removal readback mismatch')
            except BaseException as error:
                failures.append(label + ':' + type(error).__name__)
        for handle, close in reversed(self.resources):
            try: self.api.check(close(handle))
            except BaseException as error: failures.append(type(error).__name__)
        self.applied.clear(); self.resources.clear()
        self.proof['owned_aces_removed'] = not failures
        if failures:
            raise RuntimeError('owned desktop access cleanup failed: ' + ','.join(failures))
