"""Current-source genuine Windows ordinary controls, NEVER Go/VM owner grants.

This module is NOTRUN. Expected protected/unknown fault frames are retained until
this exact disposable control process exits; no close retry or flag clearing.
"""
from __future__ import annotations
import ctypes as c
from ctypes import wintypes as w
import json
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import time

import windows_nt_output_native_job as job
import windows_nt_output_native_ci as ci


def native_has_unexpected_cancel(error, expected=None):
    if isinstance(error,BaseExceptionGroup):
        return any(native_has_unexpected_cancel(child,expected) for child in error.exceptions)
    return isinstance(error,(KeyboardInterrupt,SystemExit)) and error is not expected


def native_original_local_payload_controls(manager, payload, output, deadline):
    """Actual Windows fixed-input negative branches; no source native Git call."""
    if sys.platform!="win32":raise RuntimeError("real current Windows owned-input controls required")
    lease=ci.load_native_lease(manager/"scripts/windows_nt_output_native_inputs.json")
    guard_path=manager/"scripts/windows_foundation_source_guard.py"
    if ci.hashlib.sha256(guard_path.read_bytes()).hexdigest()!=lease["source_guard_sha256"]:
        raise ValueError("original local negative guard source changed")
    spec=importlib.util.spec_from_file_location("_current_original_local_negative",guard_path)
    guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
    manifest=guard.load_manifest(manager/"scripts/windows_foundation_source_manifest.json")
    before=ci.verify_owned_original_payloads(guard,payload,manifest,deadline)
    records=[];calls=[]
    original_binding=guard.run_git
    guard.run_git=lambda *a,**k:(calls.append((a,k)),(_ for _ in ()).throw(AssertionError("negative unexpectedly reached native Git")))[-1]
    errors=[]
    try:
        for name in ("original-local-bad-source-preclone-rejected",
                "original-local-bad-patch-preclone-rejected",
                "original-local-existing-destination-preclone-rejected"):
            root=output/name;root.mkdir(mode=0o700,exist_ok=False)
            dirs=before["directories"]
            for relative in sorted((p for p in dirs if p!="."),key=lambda p:(len(Path(p).parts),p)):
                (root/relative).mkdir(mode=0o700,exist_ok=False)
            for row in before["files"]:
                data=ci.read_owned_bounded_file(payload/row["path"],deadline,167168,return_data=True)["data"]
                ci.write_owned_original_payload(root/row["path"],data,deadline)
            if ci.verify_owned_original_payloads(guard,root,manifest,deadline)["actual_bytes"]!=592919:
                raise AssertionError("negative fixed input copy changed")
            destination=output/(name+"-sut")
            if name=="original-local-existing-destination-preclone-rejected":
                destination.mkdir(mode=0o700,exist_ok=False)
            else:
                relative=("source/"+manifest["exact73"][0]["path"]
                    if name=="original-local-bad-source-preclone-rejected" else "FULL43-FROM-EXACT73.patch")
                path=root/relative
                errors2=[];stream=None;frame={"path":str(path),"state":"MUTATION_OPEN_CALLING","resource":None}
                try:
                    if time.monotonic()>=deadline:raise TimeoutError("negative mutation open deadline")
                    stream=path.open("r+b",buffering=0);frame["resource"]=stream
                    if time.monotonic()>=deadline:raise TimeoutError("negative mutation read deadline")
                    first=stream.read(1)
                    if time.monotonic()>=deadline:raise TimeoutError("negative mutation read returned late")
                    if len(first)!=1:raise AssertionError("fixed negative canary is empty")
                    stream.seek(0)
                    if time.monotonic()>=deadline:raise TimeoutError("negative mutation write deadline")
                    written=stream.write(bytes([first[0]^1]))
                    if time.monotonic()>=deadline:raise TimeoutError("negative mutation write returned late")
                    if type(written) is not int or written!=1:raise AssertionError("negative mutation unknown write")
                except BaseException as error:errors2.append(error)
                finally:
                    if stream is not None:
                        try:stream.close()
                        except BaseException as error:errors2.append(error)
                    if time.monotonic()>=deadline:errors2.append(TimeoutError("negative mutation close deadline"))
                    if errors2:ci.RESOURCE_QUARANTINE.append(frame)
                    job.raise_preserved_native_errors(errors2)
            previous=len(calls)
            try:guard.restore_source(manager,destination,manifest,local_payload=root)
            except ValueError:pass
            else:raise AssertionError("original local fixed negative admitted")
            if len(calls)!=previous:raise AssertionError("original negative reached native source process")
            records.append({"name":name,"action":"pass","scope":"actual-Windows-original-local-negative;zero-native-Git"})
        if ci.verify_owned_original_payloads(guard,payload,manifest,deadline)!=before:
            raise AssertionError("canonical original input changed during negatives")
    except BaseException as error:errors.append(error)
    finally:
        try:
            guard.run_git=original_binding
            if guard.run_git is not original_binding:raise AssertionError("exact original binding not restored")
        except BaseException as error:errors.append(error)
        job.raise_preserved_native_errors(errors)
    return records


def native_control_entry():
    if sys.platform != "win32" or sys.version_info[:2] != (3,12):
        raise RuntimeError("actual frozen Windows Python3.12 required; no skip/mock")
    if (os.environ.get("GITHUB_ACTIONS"),os.environ.get("GITHUB_REPOSITORY"),
        os.environ.get("RUNNER_ENVIRONMENT")) != ("true","Eswink/coding-tools-mcp","github-hosted"):
        raise RuntimeError("disposable CI purpose context required; context is not authority")
    if len(sys.argv)!=4 or sys.argv[1:3]!=["--all","--original-local-payload"]:
        raise ValueError("fixed ordinary entry with prepared input required")
    payload=Path(sys.argv[3])
    manager = Path(__file__).resolve().parent.parent
    output = Path(tempfile.mkdtemp(prefix="nt-ordinary-controls-"))
    overall = time.monotonic()+120; records = []
    records.extend(native_original_local_payload_controls(manager,payload,output,overall))
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
