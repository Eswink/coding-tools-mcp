"""Verify the OS-created child token, not an unrelated preflight logon token.

CI account fixture only. No token modification, desktop ACL mutation or credentials
in evidence. The suspended child is already in its owned job before these checks.
"""
from __future__ import annotations
import ctypes as c
from ctypes import wintypes as w
import hashlib
import re

ACCOUNT_SID = re.compile(r'S-1-5-21-(?:[0-9]+-){3}[0-9]+')

class TokenUser(c.Structure):
    _fields_ = [('sid', c.c_void_p), ('attributes', w.DWORD)]


def token_sid(api, token) -> str:
    needed = w.DWORD()
    api.GetTokenInformation(token, 1, None, 0, c.byref(needed))
    if not c.sizeof(TokenUser) <= needed.value <= 65536:
        raise RuntimeError('invalid child token user record size')
    data = c.create_string_buffer(needed.value)
    api.check(api.GetTokenInformation(token, 1, data, needed.value, c.byref(needed)))
    pointer = c.cast(data, c.POINTER(TokenUser)).contents.sid
    if not pointer:
        raise RuntimeError('missing child token user SID')
    return api.sid_text(pointer)


def token_session(api, token) -> int:
    session, needed = w.DWORD(), w.DWORD()
    api.check(api.GetTokenInformation(token, 12, c.byref(session), c.sizeof(session), c.byref(needed)))
    if needed.value != c.sizeof(session):
        raise RuntimeError('invalid token session record')
    return int(session.value)


def validate_identity(expected: str, actual: str, state: dict, restricted: bool,
                      parent_session: int, child_session: int) -> dict:
    if not ACCOUNT_SID.fullmatch(expected) or actual != expected:
        raise RuntimeError('native process is not the owned standard account')
    if (state.get('elevated') is not False or type(state.get('integrity_rid')) is not int
        or state['integrity_rid'] != 8192 or restricted is not False):
        raise RuntimeError('native child must be an ordinary medium standard-user token')
    if (type(parent_session) is not int or type(child_session) is not int
        or parent_session <= 0 or child_session != parent_session):
        raise RuntimeError('native child is not in the caller interactive session')
    return {'actual_child_identity_verified': True,
        'account_sid_sha256': hashlib.sha256(actual.encode()).hexdigest(),
        'token': state, 'restricted': restricted, 'session_id': child_session,
        'launch_api': 'CreateProcessWithLogonW', 'manual_desktop_acl': False}


def verify_child(api, medium, process, expected_sid: str) -> tuple[dict, str]:
    parent, child = w.HANDLE(), w.HANDLE()
    try:
        api.check(api.OpenProcessToken(api.GetCurrentProcess(), 0x0008, c.byref(parent)))
        api.check(api.OpenProcessToken(process, 0x0008, c.byref(child)))
        proof = validate_identity(expected_sid, token_sid(api, child), api.token_state(child),
            medium.token_has_restrictions(api, child), token_session(api, parent), token_session(api, child))
        size = w.DWORD(32768); profile = c.create_unicode_buffer(size.value)
        api.check(api.GetUserProfileDirectoryW(child, profile, c.byref(size)))
        return proof, profile.value
    finally:
        failures = []
        for handle in (child, parent):
            if handle:
                try:
                    api.check(api.CloseHandle(handle))
                except OSError as error:
                    failures.append(error)
        if failures:
            raise RuntimeError('child identity verification handle cleanup failed') from failures[0]
