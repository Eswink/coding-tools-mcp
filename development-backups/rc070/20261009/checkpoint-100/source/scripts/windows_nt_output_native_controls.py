"""Current-source genuine Windows ordinary controls, NEVER Go/VM owner grants.

This module is NOTRUN. Expected protected/unknown fault frames are retained until
this exact disposable control process exits; no close retry or flag clearing.
"""
from __future__ import annotations
import ctypes as c
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import sys
import tempfile
import time

import windows_nt_output_native_job as job


def native_has_unexpected_cancel(error, expected=None):
    if isinstance(error,BaseExceptionGroup):
        return any(native_has_unexpected_cancel(child,expected) for child in error.exceptions)
    return isinstance(error,(KeyboardInterrupt,SystemExit)) and error is not expected


def native_control_entry():
    if sys.platform != "win32" or sys.version_info[:2] != (3,12):
        raise RuntimeError("actual frozen Windows Python3.12 required; no skip/mock")
    if (os.environ.get("GITHUB_ACTIONS"),os.environ.get("GITHUB_REPOSITORY"),
        os.environ.get("RUNNER_ENVIRONMENT")) != ("true","Eswink/coding-tools-mcp","github-hosted"):
        raise RuntimeError("disposable CI purpose context required; context is not authority")
    if sys.argv[1:] != ["--all"]: raise ValueError("fixed ordinary entry required")
    manager = Path(__file__).resolve().parent.parent
    output = Path(tempfile.mkdtemp(prefix="nt-ordinary-controls-"))
    overall = time.monotonic()+120; records = []
    env = dict(os.environ);env["PYTHONDONTWRITEBYTECODE"]="1"
    for name,body,input_data,want_out,want_err in [
        ("creation-job-list-two-channels", "import sys;sys.stdout.buffer.write(b'owned-out');sys.stderr.buffer.write(b'owned-err')",None,b"owned-out",b"owned-err"),
        ("delayed-pending-read-eof", "import sys,time;time.sleep(.2);sys.stdout.buffer.write(b'delayed')",None,b"delayed",b""),
        ("binary-overlapped-stdin-eof", "import sys;data=sys.stdin.buffer.read();sys.stdout.buffer.write(data);sys.stderr.buffer.write(b'eof')",b"a\0b"*43691,b"a\0b"*43691,b"eof")]:
        value=job.native_collect_stage(manager,sys.executable,["-B","-c",body],env,manager,
            min(overall,time.monotonic()+15),output/name,input_data=input_data,overall_deadline=overall)
        if value["stdout"] != want_out or value["stderr"] != want_err or value["actual_root_exit"] != 0 or not value["kernel_job_empty"] or not value["self_handles_closed"]:
            raise AssertionError("actual named ordinary native vector rejects")
        records.append({"name":name,"action":"pass","scope":"actual-current-Windows-API"})
    # Actual pending operation: CancelIoEx result is not accepted as completion.
    original,api=job.load_original_native_api(manager);frame=job.NativeFrame(api,original)
    job.native_issue_connect(frame,"cancel_read")
    operation=job.native_issue_read(frame,"cancel_read")
    if operation.state != "PENDING": raise AssertionError("ordinary actual pending read not observed")
    frame.canceled=True;job.native_cancel_retire(frame,min(overall,time.monotonic()+2))
    if operation.state != "TERMINAL" or operation.error != job.ABORTED or frame.errors:
        job.QUARANTINE.append(frame);raise AssertionError("actual cancellation completion unresolved")
    for name in list(frame.handles):job.native_checked_close(frame,name)
    records.append({"name":"pending-read-cancel-completed-still-denied","action":"pass","scope":"actual-current-Windows-negative"})
    # A real protected live handle, not an invalidated numeric handle.
    protected=job.NativeFrame(api,original)
    raw=job.retain_native_result(protected,"protected_event",lambda:api.CreateEventW(None,True,False,None))
    api.check(api.SetHandleInformation(raw,2,2));flags=w.DWORD()
    api.check(api.GetHandleInformation(raw,c.byref(flags)))
    if flags.value & 2 != 2:raise AssertionError("actual protect flag not set")
    try:job.native_checked_close(protected,"protected_event")
    except OSError:
        if protected.handles["protected_event"]["state"] != "UNKNOWN":raise AssertionError("failed close holder lost")
    else:raise AssertionError("unexpected protected close success")
    api.check(api.GetHandleInformation(raw,c.byref(flags)))
    if flags.value & 2 != 2:raise AssertionError("protected unknown holder no longer live")
    job.QUARANTINE.append(protected)  # Never clear, retry or delete before exact process exit.
    records.append({"name":"real-protected-close-unknown-retained","action":"pass","scope":"actual-current-Windows-negative;notproductioncloseproof"})
    # Root exit0 with a live inherited-Job descendant cannot admit success.
    before=len(job.QUARANTINE)
    descendant="import subprocess,sys;subprocess.Popen([sys.executable,'-B','-c','import time;time.sleep(60)'],close_fds=False)"
    try:
        job.native_collect_stage(manager,sys.executable,["-B","-c",descendant],env,manager,
            min(overall,time.monotonic()+2),output/"descendant-held-writer",overall_deadline=overall)
    except BaseException as error:
        if native_has_unexpected_cancel(error):raise
        if len(job.QUARANTINE)<=before or not job.QUARANTINE[-1].forced or not job.QUARANTINE[-1].job_empty:
            raise AssertionError("real descendant forced closure not observed")
    else:raise AssertionError("live descendant/root-only outcome admitted")
    records.append({"name":"actual-descendant-held-writer-rejected","action":"pass","scope":"actual-current-Windows-negative"})
    # Real creation followed by an ordinary delegate fault; never natural FFI proof.
    original_loader=job.load_original_native_api
    original2,api2=original_loader(manager);real_create=api2.CreateProcessW
    marker=KeyboardInterrupt("ordinary-after-real-create-marker")
    api2.CreateProcessW=lambda *a:(real_create(*a),(_ for _ in ()).throw(marker))[0]
    job.load_original_native_api=lambda _: (original2,api2)
    errors=[];before=len(job.QUARANTINE)
    try:
        job.native_collect_stage(manager,sys.executable,["-B","-c","raise AssertionError('must remain suspended')"],
            env,manager,min(overall,time.monotonic()+2),output/"after-real-create-fault",overall_deadline=overall)
    except BaseException as actual:
        if native_has_unexpected_cancel(actual,marker):raise
        if actual is not marker and not (isinstance(actual,BaseExceptionGroup) and marker in actual.exceptions):
            errors.append(actual)
        if len(job.QUARANTINE)<=before or not job.QUARANTINE[-1].unknown_acquisitions or not job.QUARANTINE[-1].job_empty:
            errors.append(AssertionError("creation no-return strong UNKNOWN frame missing"))
    else:errors.append(AssertionError("creation delegate cancellation swallowed"))
    finally:
        try:job.load_original_native_api=original_loader
        except BaseException as error:errors.append(error)
        job.raise_preserved_native_errors(errors)
    records.append({"name":"real-created-job-contained-delegate-cancel-denied","action":"pass","scope":"actualnativewithordinarydelegatefault;notnaturalFFIreproduction"})
    for name,body,combined in [
        ("actual-channel-cap-before-next-read-denied","import sys;sys.stdout.buffer.write(b'x'*3145728)",4194304),
        ("actual-shared-remaining-cap-denied","import sys;sys.stdout.buffer.write(b'x'*1024)",32)]:
        before=len(job.QUARANTINE)
        try:
            job.native_collect_stage(manager,sys.executable,["-B","-c",body],env,manager,
                min(overall,time.monotonic()+15),output/name,overall_deadline=overall,raw_total_cap=combined)
        except BaseException as actual:
            if native_has_unexpected_cancel(actual):raise
            errors=list(actual.exceptions) if isinstance(actual,BaseExceptionGroup) else [actual]
            if not any("raw capacity exhausted" in str(e) for e in errors):raise
            if len(job.QUARANTINE)<=before:raise AssertionError("actual denied byte frame not retained")
            retained=job.QUARANTINE[-1]
            if not retained.process_known or not retained.job_empty:
                raise AssertionError("actual budget child/Job retirement not observed")
            saved=[p.stat().st_size for p in (output/name).glob("*.raw")]
            if any(n>2097152 for n in saved) or sum(saved)>combined:
                raise AssertionError("actual saved failure raw exceeded fixed cap")
        else:raise AssertionError("actual incomplete-at-cap stage admitted")
        records.append({"name":name,"action":"pass","scope":"actual-current-Windows-budget-negative;notEOFsuccess"})
    if time.monotonic()>=overall:raise TimeoutError("native ordinary120s deadline")
    print(json.dumps({"records":records,"count":len(records),"native_authority":False,
        "expected_fault_frames":"held until this exact control process exit","original_Go_methods":0},sort_keys=True))
    return records


if __name__=="__main__":
    native_control_entry()
