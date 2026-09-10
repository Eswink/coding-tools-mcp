"""CI-only, same-user LUA/medium process in an owned kill-on-close job.

Never enables SANDBOX_INERT, changes accounts/policies, or patches application bytes.
"""
from __future__ import annotations
import ctypes as c
from ctypes import wintypes as w
import os
from pathlib import Path
import subprocess
import sys


def environment_block(env: dict[str, str]) -> str:
    for key, value in env.items():
        if not isinstance(key, str) or not key or '=' in key or '\0' in key or not isinstance(value, str) or '\0' in value:
            raise ValueError('invalid child environment')
    return '\0'.join(f'{k}={env[k]}' for k in sorted(env, key=str.upper)) + '\0\0'


def require_standard(state: dict) -> None:
    if state.get('elevated') is not False or type(state.get('integrity_rid')) is not int or not 4096 <= state['integrity_rid'] <= 8192:
        raise RuntimeError(f'non-elevated medium-or-lower token required: {state}')


class Startup(c.Structure):
    _fields_ = [('cb', w.DWORD), ('reserved', w.LPWSTR), ('desktop', w.LPWSTR), ('title', w.LPWSTR),
        ('x', w.DWORD), ('y', w.DWORD), ('width', w.DWORD), ('height', w.DWORD),
        ('chars_x', w.DWORD), ('chars_y', w.DWORD), ('fill', w.DWORD), ('flags', w.DWORD),
        ('show', w.WORD), ('reserved_size', w.WORD), ('reserved_ptr', c.c_void_p),
        ('stdin', w.HANDLE), ('stdout', w.HANDLE), ('stderr', w.HANDLE)]
class ProcessInfo(c.Structure):
    _fields_ = [('process', w.HANDLE), ('thread', w.HANDLE), ('pid', w.DWORD), ('tid', w.DWORD)]
class Label(c.Structure):
    _fields_ = [('sid', c.c_void_p), ('attributes', w.DWORD)]
class BasicLimits(c.Structure):
    _fields_ = [('process_time', c.c_longlong), ('job_time', c.c_longlong), ('flags', w.DWORD),
        ('min_working', c.c_size_t), ('max_working', c.c_size_t), ('active_processes', w.DWORD),
        ('affinity', c.c_size_t), ('priority', w.DWORD), ('scheduling', w.DWORD)]
class Limits(c.Structure):
    _fields_ = [('basic', BasicLimits), ('io', c.c_ulonglong * 6), ('process_memory', c.c_size_t),
        ('job_memory', c.c_size_t), ('peak_process', c.c_size_t), ('peak_job', c.c_size_t)]


class Api:
    def __init__(self):
        if sys.platform != 'win32':
            raise RuntimeError('Windows native API required')
        if c.sizeof(c.c_void_p) != 8 or c.sizeof(Startup) != 104 or c.sizeof(ProcessInfo) != 24 or c.sizeof(Limits) != 144:
            raise RuntimeError('unexpected Windows x64 ABI layout')
        self.kernel = c.WinDLL('kernel32', use_last_error=True)
        self.adv = c.WinDLL('advapi32', use_last_error=True)
        def bind(dll, name, result, args):
            function = getattr(dll, name); function.restype = result; function.argtypes = args
            setattr(self, name, function)
        ptr = c.c_void_p
        bind(self.kernel, 'GetCurrentProcess', w.HANDLE, [])
        bind(self.kernel, 'CloseHandle', w.BOOL, [w.HANDLE])
        bind(self.kernel, 'LocalFree', ptr, [ptr])
        bind(self.kernel, 'GetExitCodeProcess', w.BOOL, [w.HANDLE, c.POINTER(w.DWORD)])
        bind(self.kernel, 'WaitForSingleObject', w.DWORD, [w.HANDLE, w.DWORD])
        bind(self.kernel, 'TerminateProcess', w.BOOL, [w.HANDLE, w.UINT])
        bind(self.kernel, 'ResumeThread', w.DWORD, [w.HANDLE])
        bind(self.kernel, 'CreateJobObjectW', w.HANDLE, [ptr, w.LPCWSTR])
        bind(self.kernel, 'SetInformationJobObject', w.BOOL, [w.HANDLE, c.c_int, ptr, w.DWORD])
        bind(self.kernel, 'AssignProcessToJobObject', w.BOOL, [w.HANDLE, w.HANDLE])
        bind(self.adv, 'OpenProcessToken', w.BOOL, [w.HANDLE, w.DWORD, c.POINTER(w.HANDLE)])
        bind(self.adv, 'GetTokenInformation', w.BOOL, [w.HANDLE, c.c_int, ptr, w.DWORD, c.POINTER(w.DWORD)])
        bind(self.adv, 'SetTokenInformation', w.BOOL, [w.HANDLE, c.c_int, ptr, w.DWORD])
        bind(self.adv, 'CreateRestrictedToken', w.BOOL, [w.HANDLE, w.DWORD, w.DWORD, ptr, w.DWORD, ptr, w.DWORD, ptr, c.POINTER(w.HANDLE)])
        bind(self.adv, 'ConvertStringSidToSidW', w.BOOL, [w.LPCWSTR, c.POINTER(ptr)])
        bind(self.adv, 'GetLengthSid', w.DWORD, [ptr])
        bind(self.adv, 'GetSidSubAuthorityCount', c.POINTER(w.BYTE), [ptr])
        bind(self.adv, 'GetSidSubAuthority', c.POINTER(w.DWORD), [ptr, w.DWORD])
        bind(self.adv, 'CreateProcessAsUserW', w.BOOL, [w.HANDLE, w.LPCWSTR, w.LPWSTR, ptr, ptr,
            w.BOOL, w.DWORD, ptr, w.LPCWSTR, c.POINTER(Startup), c.POINTER(ProcessInfo)])

    def check(self, ok):
        if not ok: raise c.WinError(c.get_last_error())
        return ok

    def token_state(self, token) -> dict:
        needed, elevated = w.DWORD(), w.DWORD()
        self.check(self.GetTokenInformation(token, 20, c.byref(elevated), c.sizeof(elevated), c.byref(needed)))
        self.GetTokenInformation(token, 25, None, 0, c.byref(needed))
        if not 0 < needed.value <= 65536: raise RuntimeError('unexpected token label size')
        buffer = c.create_string_buffer(needed.value)
        self.check(self.GetTokenInformation(token, 25, buffer, needed, c.byref(needed)))
        sid = c.cast(buffer, c.POINTER(Label)).contents.sid
        count = self.GetSidSubAuthorityCount(sid).contents.value
        if not 1 <= count <= 15: raise RuntimeError('invalid integrity SID')
        rid = self.GetSidSubAuthority(sid, count - 1).contents.value
        return {'elevated': bool(elevated.value), 'integrity_rid': int(rid)}


class OwnedProcess:
    def __init__(self, api: Api, info: ProcessInfo, job, security: dict):
        self.api, self.handle, self.job = api, info.process, job
        self.pid, self.security, self.returncode = int(info.pid), security, None

    def poll(self):
        if not self.handle: return self.returncode
        status = self.api.WaitForSingleObject(self.handle, 0)
        if status == 258: return None
        if status != 0: raise c.WinError(c.get_last_error())
        code = w.DWORD(); self.api.check(self.api.GetExitCodeProcess(self.handle, c.byref(code)))
        self.returncode = int(code.value)
        return self.returncode

    def wait(self, timeout=10):
        if not self.handle: return self.returncode
        status = self.api.WaitForSingleObject(self.handle, max(0, min(int(timeout * 1000), 0xfffffffe)))
        if status == 258: raise subprocess.TimeoutExpired('owned-native-app', timeout)
        if status != 0: raise c.WinError(c.get_last_error())
        return self.poll()

    def terminate_tree(self):
        # Closing this unnamed job terminates its descendants even if root exited.
        if self.job:
            self.api.check(self.api.CloseHandle(self.job)); self.job = None
        try:
            self.wait(10)
        finally:
            if self.handle:
                self.api.CloseHandle(self.handle); self.handle = None


def launch(executable: Path, env: dict[str, str], arguments: list[str] | None = None) -> OwnedProcess:
    if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted' or os.environ.get('GITHUB_REPOSITORY') != 'Eswink/coding-tools-mcp':
        raise RuntimeError('only disposable hosted CI may launch this fixture')
    executable = executable.resolve(strict=True)
    block = c.create_unicode_buffer(environment_block(env))
    argv = [str(executable), *(arguments or [])]
    if any('\0' in part for part in argv): raise ValueError('invalid command argument')
    line = c.create_unicode_buffer(subprocess.list2cmdline(argv))
    api = Api(); original, restricted, child_token = w.HANDLE(), w.HANDLE(), w.HANDLE()
    sid, job, info = c.c_void_p(), None, ProcessInfo()
    transferred = False
    try:
        api.check(api.OpenProcessToken(api.GetCurrentProcess(), 0x0001 | 0x0002 | 0x0008 | 0x0080, c.byref(original)))
        parent_state = api.token_state(original)
        # DISABLE_MAX_PRIVILEGE | LUA_TOKEN. SANDBOX_INERT is deliberately absent.
        api.check(api.CreateRestrictedToken(original, 0x1 | 0x4, 0, None, 0, None, 0, None, c.byref(restricted)))
        api.check(api.ConvertStringSidToSidW('S-1-16-8192', c.byref(sid)))
        label = Label(sid, 0x20)
        api.check(api.SetTokenInformation(restricted, 25, c.byref(label), c.sizeof(label) + api.GetLengthSid(sid)))
        required = api.token_state(restricted); require_standard(required)
        job = api.check(api.CreateJobObjectW(None, None))
        limits = Limits(); limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        api.check(api.SetInformationJobObject(job, 9, c.byref(limits), c.sizeof(limits)))
        startup = Startup(); startup.cb = c.sizeof(startup)
        # Suspended until owned-job assignment and actual child-token validation.
        api.check(api.CreateProcessAsUserW(restricted, str(executable), line, None, None, False,
            0x4 | 0x200 | 0x400 | 0x08000000, block, str(executable.parent), c.byref(startup), c.byref(info)))
        api.check(api.AssignProcessToJobObject(job, info.process))
        api.check(api.OpenProcessToken(info.process, 0x0008, c.byref(child_token)))
        actual = api.token_state(child_token); require_standard(actual)
        if api.ResumeThread(info.thread) == 0xffffffff: raise c.WinError(c.get_last_error())
        process = OwnedProcess(api, info, job, {'parent': parent_state, 'child': actual, 'owned_job': True})
        transferred = True
        return process
    finally:
        if not transferred:
            if job: api.CloseHandle(job)
            if info.process:
                api.TerminateProcess(info.process, 1); api.WaitForSingleObject(info.process, 10000); api.CloseHandle(info.process)
        if info.thread: api.CloseHandle(info.thread)
        for handle in (child_token, restricted, original):
            if handle: api.CloseHandle(handle)
        if sid: api.LocalFree(sid)
