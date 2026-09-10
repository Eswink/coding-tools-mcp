"""Real medium-token desktop/USER32 smoke; exits nonzero rather than skipping."""
import ctypes as c
from ctypes import wintypes as w
import os
import sys


def run() -> None:
    if sys.platform != "win32" or os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted" or os.environ.get("GITHUB_REPOSITORY") != "Eswink/coding-tools-mcp":
        raise RuntimeError("disposable Windows runner required")
    user = c.WinDLL("user32", use_last_error=True)
    kernel = c.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentThreadId.restype = w.DWORD
    user.GetProcessWindowStation.restype = w.HANDLE
    user.GetThreadDesktop.argtypes = [w.DWORD]; user.GetThreadDesktop.restype = w.HANDLE
    user.GetUserObjectInformationW.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.POINTER(w.DWORD)]
    user.GetUserObjectInformationW.restype = w.BOOL
    for handle, expected in ((user.GetProcessWindowStation(), "winsta0"),
                             (user.GetThreadDesktop(kernel.GetCurrentThreadId()), "default")):
        text = c.create_unicode_buffer(256); size = w.DWORD()
        if not handle or not user.GetUserObjectInformationW(handle, 2, text, c.sizeof(text), c.byref(size)):
            raise c.WinError(c.get_last_error())
        if text.value.casefold() != expected:
            raise RuntimeError("unexpected desktop: " + text.value)
    user.CreateWindowExW.argtypes = [w.DWORD,w.LPCWSTR,w.LPCWSTR,w.DWORD,c.c_int,c.c_int,c.c_int,c.c_int,
                                     w.HWND,w.HMENU,w.HINSTANCE,c.c_void_p]
    user.CreateWindowExW.restype = w.HWND
    user.ShowWindow.argtypes = [w.HWND,c.c_int]; user.ShowWindow.restype = w.BOOL
    user.UpdateWindow.argtypes = [w.HWND]; user.UpdateWindow.restype = w.BOOL
    user.DestroyWindow.argtypes = [w.HWND]; user.DestroyWindow.restype = w.BOOL
    window = user.CreateWindowExW(0, "STATIC", "Native authorization desktop smoke", 0x00cf0000,
                                   20,20,300,120,None,None,None,None)
    if not window: raise c.WinError(c.get_last_error())
    try:
        user.ShowWindow(window, 1)
        if not user.UpdateWindow(window): raise c.WinError(c.get_last_error())
    finally:
        if not user.DestroyWindow(window): raise c.WinError(c.get_last_error())


if __name__ == "__main__": run()
