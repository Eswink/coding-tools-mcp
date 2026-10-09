"""Finite ordinary CI process/IO adapter; never a VM or publication capability.

SOURCE DRAFT: the Win64 API branches require current native ordinary controls.
No import runs a native API. Original v12 source is loaded only after a hash check.
"""
from __future__ import annotations

import ctypes as c
from ctypes import wintypes as w
from dataclasses import dataclass, field
import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

V12_SHA = "5f46773d1b67d931532144cb077d8d792a9a3f0e3cc0feb3daa91280ec8bfe9f"
QUARANTINE = []
PENDING, INCOMPLETE, ABORTED, BROKEN, CONNECTED = 997, 996, 995, 109, 535


@dataclass
class NativeOperation:
    handle: str
    event: str
    kind: str
    overlapped: object
    buffer: object = None
    submitted: int = 0
    state: str = "NOT_ISSUED"
    transferred: int = 0
    error: int | None = None


@dataclass
class NativeFrame:
    api: object
    original: object
    handles: dict = field(default_factory=dict)
    operations: list = field(default_factory=list)
    strong: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    observations: list = field(default_factory=list)
    unknown_acquisitions: list = field(default_factory=list)
    process_info: object = None
    process_known: bool = False
    forced: bool = False
    canceled: bool = False
    job_empty: bool = False
    exit_code: int | None = None
    attribute_state: str = "NONE"
    attribute_storage: object = None


def load_original_native_api(manager):
    if sys.platform != "win32":
        raise RuntimeError("actual Windows native API required; no POSIX substitute")
    path = Path(manager) / "scripts" / "Windows非提升进程v12.py"
    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != V12_SHA:
        raise ValueError("immutable original v12 source mismatch")
    spec = importlib.util.spec_from_file_location("_nt_ci_v12_" + uuid.uuid4().hex, path)
    original = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(original)
    api = original.Api()  # Original x64 ABI checks and DLL bindings, not launch().
    return original, extend_required_native_bindings(api)


def extend_required_native_bindings(api):
    ptr, dwordp = c.c_void_p, c.POINTER(w.DWORD)
    signatures = {
        "InitializeProcThreadAttributeList": (w.BOOL, [ptr, w.DWORD, w.DWORD, c.POINTER(c.c_size_t)]),
        "UpdateProcThreadAttribute": (w.BOOL, [ptr, w.DWORD, c.c_size_t, ptr, c.c_size_t, ptr, ptr]),
        "DeleteProcThreadAttributeList": (None, [ptr]),
        "IsProcessInJob": (w.BOOL, [w.HANDLE, w.HANDLE, c.POINTER(w.BOOL)]),
        "QueryInformationJobObject": (w.BOOL, [w.HANDLE, c.c_int, ptr, w.DWORD, dwordp]),
        "TerminateJobObject": (w.BOOL, [w.HANDLE, w.UINT]),
        "CreateNamedPipeW": (w.HANDLE, [w.LPCWSTR, w.DWORD, w.DWORD, w.DWORD, w.DWORD, w.DWORD, w.DWORD, ptr]),
        "ConnectNamedPipe": (w.BOOL, [w.HANDLE, ptr]),
        "CreateFileW": (w.HANDLE, [w.LPCWSTR, w.DWORD, w.DWORD, ptr, w.DWORD, w.DWORD, w.HANDLE]),
        "CreateEventW": (w.HANDLE, [ptr, w.BOOL, w.BOOL, w.LPCWSTR]),
        "ResetEvent": (w.BOOL, [w.HANDLE]),
        "ReadFile": (w.BOOL, [w.HANDLE, ptr, w.DWORD, ptr, ptr]),
        "WriteFile": (w.BOOL, [w.HANDLE, ptr, w.DWORD, ptr, ptr]),
        "GetOverlappedResult": (w.BOOL, [w.HANDLE, ptr, dwordp, w.BOOL]),
        "CancelIoEx": (w.BOOL, [w.HANDLE, ptr]),
        "GetHandleInformation": (w.BOOL, [w.HANDLE, dwordp]),
        "SetHandleInformation": (w.BOOL, [w.HANDLE, w.DWORD, w.DWORD]),
    }
    for name, (result, args) in signatures.items():
        fn = getattr(api.kernel, name)
        fn.restype, fn.argtypes = result, args
        setattr(api, name, fn)
    return api


def retain_native_result(frame, name, acquisition):
    if name in frame.handles:
        raise ValueError("duplicate native holder")
    frame.unknown_acquisitions.append(name)
    value = acquisition()  # A no-return exception may follow a native side effect.
    if value is None or value == 0 or value == c.c_void_p(-1).value:
        frame.unknown_acquisitions.remove(name)
        raise c.WinError(c.get_last_error())
    frame.handles[name] = {"raw": int(value), "state": "LIVE"}
    frame.unknown_acquisitions.remove(name)
    return int(value)


def native_checked_close(frame, name):
    slot = frame.handles[name]
    if slot["state"] != "LIVE":
        raise RuntimeError("close requires actual live holder; never retry UNKNOWN")
    if any(o.state in ("CALLING", "PENDING", "UNKNOWN") and name in (o.handle, o.event)
           for o in frame.operations):
        raise RuntimeError("cannot close a holder referenced by unresolved native IO")
    slot["state"] = "CLOSING"
    try:
        if not frame.api.CloseHandle(slot["raw"]):
            raise c.WinError(c.get_last_error())
    except BaseException:
        slot["state"] = "UNKNOWN"
        raise
    slot["state"] = "CLOSED"


def native_issue_connect(frame, channel, outbound=False):
    api = frame.api
    name = r"\\.\pipe\coding-tools-native-ci-" + uuid.uuid4().hex
    # FIRST_PIPE_INSTANCE, OVERLAPPED, byte mode, REJECT_REMOTE_CLIENTS.
    server = retain_native_result(frame, channel, lambda: api.CreateNamedPipeW(
        name, (2 if outbound else 1) | 0x40000000 | 0x00080000,
        0x00000008, 1, 65536, 65536, 0, None))
    event = channel + "_event"
    retain_native_result(frame, event, lambda: api.CreateEventW(None, True, False, None))
    ovtype = type("_Overlapped", (c.Structure,), {"_fields_": [
        ("internal", c.c_size_t), ("internal_high", c.c_size_t),
        ("offset", w.DWORD), ("offset_high", w.DWORD), ("event", w.HANDLE)]})
    if c.sizeof(ovtype) != 32:
        raise RuntimeError("unexpected actual Win64 OVERLAPPED layout")
    ov = ovtype(); ov.event = frame.handles[event]["raw"]
    op = NativeOperation(channel, event, "CONNECT", ov)
    frame.operations.append(op)
    op.state = "CALLING"
    try:
        ok = api.ConnectNamedPipe(server, c.byref(ov))
        error = 0 if ok else c.get_last_error()
    except BaseException:
        op.state = "UNKNOWN"
        raise
    if ok or error == CONNECTED:
        op.state = "TERMINAL"
    elif error == PENDING:
        op.state = "PENDING"
    else:
        op.state = "TERMINAL"; op.error = error
        raise c.WinError(error)
    client = channel + "_client"
    retain_native_result(frame, client, lambda: api.CreateFileW(
        name, 0x80000000 if outbound else 0x40000000, 0, None, 3, 0x80, None))
    until = time.monotonic() + 2
    while op.state == "PENDING" and time.monotonic() < until:
        native_observe_completion(frame, op)
        if op.state == "PENDING": time.sleep(.002)
    if op.state != "TERMINAL" or op.error:
        raise RuntimeError("connection completion not known")
    return channel, client


def native_issue_read(frame, channel):
    api = frame.api
    previous = [o for o in frame.operations if o.handle == channel][-1]
    if previous.state != "TERMINAL":
        raise RuntimeError("prior operation has not completed")
    api.check(api.ResetEvent(frame.handles[previous.event]["raw"]))
    ov = type(previous.overlapped)(); ov.event = frame.handles[previous.event]["raw"]
    op = NativeOperation(channel, previous.event, "READ", ov, c.create_string_buffer(65536), 65536)
    frame.operations.append(op); op.state = "CALLING"
    try:
        ok = api.ReadFile(frame.handles[channel]["raw"], op.buffer, op.submitted, None, c.byref(ov))
        error = 0 if ok else c.get_last_error()
    except BaseException:
        op.state = "UNKNOWN"
        raise
    if not ok and error == BROKEN:
        op.state = "TERMINAL"; op.error = BROKEN
    elif ok or error == PENDING:
        op.state = "PENDING"; native_observe_completion(frame, op)
    else:
        op.state = "TERMINAL"; op.error = error
        raise c.WinError(error)
    return op


def native_issue_write(frame, channel, data):
    api = frame.api
    previous = [o for o in frame.operations if o.handle == channel][-1]
    if previous.state != "TERMINAL": raise RuntimeError("prior write/connect is unresolved")
    if not data or len(data) > 65536: raise ValueError("finite nonempty write chunk required")
    api.check(api.ResetEvent(frame.handles[previous.event]["raw"]))
    ov = type(previous.overlapped)(); ov.event = frame.handles[previous.event]["raw"]
    op = NativeOperation(channel, previous.event, "WRITE", ov, c.create_string_buffer(data), len(data))
    frame.operations.append(op); op.state = "CALLING"
    try:
        ok = api.WriteFile(frame.handles[channel]["raw"], op.buffer, len(data), None, c.byref(ov))
        error = 0 if ok else c.get_last_error()
    except BaseException:
        op.state = "UNKNOWN"
        raise
    if ok or error == PENDING:
        op.state = "PENDING"; native_observe_completion(frame, op)
    else:
        op.state = "TERMINAL"; op.error = error
        raise c.WinError(error)
    return op


def native_observe_completion(frame, op):
    if op.state not in ("PENDING", "UNKNOWN", "CALLING"):
        return op.state
    count = w.DWORD()
    try:
        ok = frame.api.GetOverlappedResult(frame.handles[op.handle]["raw"],
            c.byref(op.overlapped), c.byref(count), False)
        error = 0 if ok else c.get_last_error()
    except BaseException:
        op.state = "UNKNOWN"
        raise
    if not ok and error == INCOMPLETE:
        op.state = "PENDING"; return op.state
    if not ok and error not in (ABORTED, BROKEN):
        op.state = "UNKNOWN"; op.error = error
        raise c.WinError(error)
    if count.value > op.submitted and op.kind != "CONNECT":
        op.state = "UNKNOWN"
        raise RuntimeError("actual native byte count exceeds submitted buffer")
    op.state, op.transferred, op.error = "TERMINAL", int(count.value), error or None
    return op.state


def native_cancel_retire(frame, deadline):
    pending = [o for o in frame.operations if o.state in ("CALLING", "PENDING", "UNKNOWN")]
    for op in pending:
        try:
            ok = frame.api.CancelIoEx(frame.handles[op.handle]["raw"], c.byref(op.overlapped))
            frame.observations.append({"cancel_requested": bool(ok), "error": 0 if ok else c.get_last_error(), "kind": op.kind})
        except BaseException as error:
            frame.errors.append(error)
    while pending and time.monotonic() < deadline:
        for op in list(pending):
            try:
                native_observe_completion(frame, op)
                if op.state == "TERMINAL": pending.remove(op)
            except BaseException as error:
                frame.errors.append(error); pending.remove(op)  # Holder stays UNKNOWN, retained.
        if pending: time.sleep(.002)
    if pending or any(o.state in ("UNKNOWN", "CALLING", "PENDING") for o in frame.operations):
        frame.errors.append(RuntimeError("native IO completion remains UNKNOWN"))


def create_job_bound_suspended(frame, executable, argv, env, cwd, input_data):
    api, original = frame.api, frame.original
    job = retain_native_result(frame, "job", lambda: api.CreateJobObjectW(None, None))
    limits = original.Limits(); limits.basic.flags = 0x2000
    frame.strong.append(limits)
    api.check(api.SetInformationJobObject(job, 9, c.byref(limits), c.sizeof(limits)))
    native_issue_connect(frame, "stdout"); native_issue_connect(frame, "stderr")
    if input_data is None:
        retain_native_result(frame, "stdin_client", lambda: api.CreateFileW("NUL", 0x80000000, 3, None, 3, 0x80, None))
    else:
        if not isinstance(input_data, bytes) or len(input_data) > 2097152:
            raise ValueError("bounded immutable input bytes required")
        frame.strong.append(input_data); native_issue_connect(frame, "stdin", outbound=True)
    children = [frame.handles[n]["raw"] for n in ("stdin_client", "stdout_client", "stderr_client")]
    if len(set(children)) != 3: raise RuntimeError("IO handles are not distinct")
    for name, slot in frame.handles.items():
        desired = 1 if name in ("stdin_client", "stdout_client", "stderr_client") else 0
        api.check(api.SetHandleInformation(slot["raw"], 1, desired))
        flags = w.DWORD(); api.check(api.GetHandleInformation(slot["raw"], c.byref(flags)))
        if flags.value & 1 != desired: raise RuntimeError("actual inheritance flags mismatch")
    size = c.c_size_t()
    ok = api.InitializeProcThreadAttributeList(None, 2, 0, c.byref(size))
    if ok or c.get_last_error() != 122 or not 0 < size.value <= 65536:
        raise RuntimeError("unexpected attribute allocation query")
    attributes = c.create_string_buffer(size.value); frame.strong.append(attributes)
    frame.attribute_storage = attributes
    frame.attribute_state = "CALLING"
    api.check(api.InitializeProcThreadAttributeList(attributes, 2, 0, c.byref(size)))
    frame.attribute_state = "LIVE"
    handlelist, joblist = (w.HANDLE * 3)(*children), (w.HANDLE * 1)(job)
    frame.strong.extend([handlelist, joblist])
    api.check(api.UpdateProcThreadAttribute(attributes, 0, 0x20002, handlelist, c.sizeof(handlelist), None, None))
    api.check(api.UpdateProcThreadAttribute(attributes, 0, 0x2000d, joblist, c.sizeof(joblist), None, None))
    extype = type("_StartupEx", (c.Structure,), {"_fields_": [("base", original.Startup), ("attributes", c.c_void_p)]})
    if c.sizeof(extype) != 112: raise RuntimeError("unexpected actual STARTUPINFOEX size")
    startup = extype(); startup.base.cb = c.sizeof(startup); startup.base.flags = 0x100
    startup.base.stdin, startup.base.stdout, startup.base.stderr = children
    startup.attributes = c.addressof(attributes)
    info = original.ProcessInfo(); frame.process_info = info
    block = c.create_unicode_buffer(original.environment_block(env))
    command = c.create_unicode_buffer(subprocess.list2cmdline([str(executable), *argv]))
    frame.strong.extend([startup, info, block, command])
    frame.unknown_acquisitions.append("CreateProcessW_return")
    ok = api.CreateProcessW(str(executable), command, None, None, True,
        original.NATIVE_CREATION_FLAGS | 0x80000, block, str(cwd),
        c.cast(c.byref(startup), c.POINTER(original.Startup)), c.byref(info))
    if not ok:
        frame.unknown_acquisitions.remove("CreateProcessW_return")
        if info.process or info.thread:
            frame.unknown_acquisitions.append("unexpected_failure_ProcessInfo")
        raise c.WinError(c.get_last_error())
    if not info.process or not info.thread: raise RuntimeError("successful creation lacks actual handles")
    frame.handles["process"] = {"raw": int(info.process), "state": "LIVE"}
    frame.handles["thread"] = {"raw": int(info.thread), "state": "LIVE"}
    frame.process_known = True; frame.unknown_acquisitions.remove("CreateProcessW_return")
    member = w.BOOL(); api.check(api.IsProcessInJob(info.process, job, c.byref(member)))
    if not member.value: raise RuntimeError("actual child is not in creation-time Job")
    for name in ("stdin_client", "stdout_client", "stderr_client"):
        native_checked_close(frame, name)
    if api.ResumeThread(info.thread) != 1:
        raise RuntimeError("unexpected actual suspend count")
    native_checked_close(frame, "thread")
    return frame


def raise_preserved_native_errors(errors):
    if len(errors) == 1: raise errors[0]
    if errors: raise BaseExceptionGroup("native stage and independent retirement failures", errors)


def native_collect_stage(manager, executable, argv, env, cwd, deadline, raw_directory,
                         input_data=None, channel_cap=2097152, overall_deadline=None):
    if type(channel_cap) is not int or channel_cap != 2097152:
        raise ValueError("fixed channel cap required")
    raw_directory = Path(raw_directory)
    if overall_deadline is None:
        overall_deadline = deadline  # Fail-only conservative bound for a bare caller.
    if deadline > overall_deadline:
        raise ValueError("stage extends overall deadline")
    raw_directory.mkdir(parents=True, exist_ok=False)
    original, api = load_original_native_api(manager)
    frame = NativeFrame(api, original)
    # The complete accounting value is retained, not a PID or receipt assertion.
    acctype = type("_JobAccounting", (c.Structure,), {"_fields_": [
        ("times", c.c_longlong * 4), ("faults", w.DWORD), ("total", w.DWORD),
        ("active", w.DWORD), ("terminated", w.DWORD)]})
    if c.sizeof(acctype) != 48: raise RuntimeError("unexpected Job accounting ABI")
    streams = {}; raw = {"stdout": bytearray(), "stderr": bytearray()}
    current = {}; eof = set(); offset = 0; write = None
    try:
        for name in raw:
            streams[name] = (raw_directory / (name + ".raw")).open("xb")
            frame.strong.append(streams[name])
        create_job_bound_suspended(frame, executable, argv, env, cwd, input_data)
        for name in raw: current[name] = native_issue_read(frame, name)
        while time.monotonic() < deadline:
            for name, op in list(current.items()):
                native_observe_completion(frame, op)
                if op.state != "TERMINAL": continue
                if op.error == BROKEN:
                    eof.add(name); del current[name]; continue
                if op.error: raise c.WinError(op.error)
                data = op.buffer.raw[:op.transferred]
                if len(raw[name]) + len(data) > channel_cap:
                    streams[name].write(data); streams[name].flush()
                    raise RuntimeError("actual raw channel overflow; saved bytes are failure evidence")
                raw[name].extend(data); streams[name].write(data); streams[name].flush()
                if not data: raise RuntimeError("zero read without actual EOF")
                current[name] = native_issue_read(frame, name)
            if input_data is not None and frame.handles["stdin"]["state"] == "LIVE":
                if write is not None:
                    native_observe_completion(frame, write)
                    if write.state == "TERMINAL":
                        if write.error or not write.transferred: raise RuntimeError("stdin write failed/no progress")
                        offset += write.transferred; write = None
                if write is None:
                    if offset == len(input_data): native_checked_close(frame, "stdin")
                    else: write = native_issue_write(frame, "stdin", input_data[offset:offset + 65536])
            wait_status = api.WaitForSingleObject(frame.handles["process"]["raw"], 0)
            if wait_status not in (0, 258):
                raise c.WinError(c.get_last_error())
            if wait_status == 0:
                code = w.DWORD(); api.check(api.GetExitCodeProcess(frame.handles["process"]["raw"], c.byref(code)))
                frame.exit_code = int(code.value)
                accounting = acctype(); api.check(api.QueryInformationJobObject(
                    frame.handles["job"]["raw"], 1, c.byref(accounting), c.sizeof(accounting), None))
                frame.job_empty = accounting.active == 0
                observation = {"root_exit": frame.exit_code, "job_active": int(accounting.active),
                    "job_terminated": int(accounting.terminated), "all_descendant_exit_codes": "UNKNOWN"}
                if not frame.observations or frame.observations[-1] != observation:
                    if len(frame.observations) >= 4096:
                        raise RuntimeError("finite kernel observation budget exceeded")
                    frame.observations.append(observation)
                if accounting.terminated: frame.forced = True
                if frame.job_empty and eof == set(raw): break
            time.sleep(.002)
        else: raise TimeoutError("native stage deadline reached")
        if frame.exit_code != 0 or frame.forced or frame.canceled:
            raise RuntimeError("native root outcome rejects success")
    except BaseException as error:
        frame.errors.append(error)
        if isinstance(error, (KeyboardInterrupt, SystemExit)): frame.canceled = True
    finally:
        # Each independently safe attempt proceeds even if an earlier one fails.
        if "job" in frame.handles and not frame.job_empty:
            grace = min(overall_deadline, time.monotonic() + 7)
            while time.monotonic() < grace:
                try:
                    accounting = acctype(); api.check(api.QueryInformationJobObject(
                        frame.handles["job"]["raw"], 1, c.byref(accounting), c.sizeof(accounting), None))
                    frame.job_empty = accounting.active == 0
                    if frame.job_empty: break
                except BaseException as error: frame.errors.append(error); break
                time.sleep(.01)
            if not frame.job_empty:
                frame.forced = True
                try: api.check(api.TerminateJobObject(frame.handles["job"]["raw"], 1))
                except BaseException as error: frame.errors.append(error)
                until = min(overall_deadline, time.monotonic() + 2)
                while time.monotonic() < until:
                    try:
                        accounting = acctype(); api.check(api.QueryInformationJobObject(
                            frame.handles["job"]["raw"], 1, c.byref(accounting), c.sizeof(accounting), None))
                        frame.job_empty = accounting.active == 0
                        if frame.job_empty: break
                    except BaseException as error: frame.errors.append(error); break
                    time.sleep(.01)
                frame.errors.append(RuntimeError("forced or UNKNOWN Job retirement rejects success"))
        try: native_cancel_retire(frame, min(overall_deadline, time.monotonic() + 2))
        except BaseException as error: frame.errors.append(error)
        if frame.attribute_state == "LIVE":
            try:
                api.DeleteProcThreadAttributeList(frame.attribute_storage)
                frame.attribute_state = "CLOSED"
            except BaseException as error:
                frame.attribute_state = "UNKNOWN"; frame.errors.append(error)
        for name, slot in list(frame.handles.items()):
            if slot["state"] != "LIVE": continue
            if name == "job" and not frame.job_empty: continue
            try: native_checked_close(frame, name)
            except BaseException as error: frame.errors.append(error)
        for stream in streams.values():
            try: stream.close()
            except BaseException as error: frame.errors.append(error)
        uncertain = (frame.unknown_acquisitions or frame.attribute_state not in ("NONE", "CLOSED")
            or any(v["state"] != "CLOSED" for v in frame.handles.values())
            or any(o.state != "TERMINAL" for o in frame.operations))
        if uncertain:
            QUARANTINE.append(frame)
            frame.errors.append(RuntimeError("whole native frame quarantined; self IO/handles UNKNOWN"))
        if frame.errors:
            QUARANTINE.append(frame)
        raise_preserved_native_errors(frame.errors)
    return {"stdout": bytes(raw["stdout"]), "stderr": bytes(raw["stderr"]),
        "actual_root_exit": frame.exit_code, "kernel_job_empty": frame.job_empty,
        "self_handles_closed": not uncertain, "forced": frame.forced,
        "all_descendant_exit_codes": "UNKNOWN", "native_authority": False,
        "observations": frame.observations}
