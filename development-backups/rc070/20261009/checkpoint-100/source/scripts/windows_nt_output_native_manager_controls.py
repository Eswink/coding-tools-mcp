"""Ordinary synthetic parser/binding/error controls; ZERO native API credit."""
from __future__ import annotations
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import zipfile
from types import SimpleNamespace

import windows_nt_output_native_ci as ci
import windows_nt_output_native_job as job


def manager_control_entry():
    manager = Path(__file__).resolve().parent.parent
    lease = ci.load_native_lease(manager/"scripts/windows_nt_output_native_inputs.json")
    entry = lease["selected_entry"]; top = entry["top_level_names"]; subs = entry["required_subtests"]
    events = [{"Action":"start","Package":"ordinary.fixture"}]
    for name in top:
        events.append({"Action":"run","Package":"ordinary.fixture","Test":name})
        for sub in subs:
            if sub.split("/",1)[0] == name:
                events.extend([{"Action":"run","Package":"ordinary.fixture","Test":sub},
                    {"Action":"pass","Package":"ordinary.fixture","Test":sub}])
        events.append({"Action":"pass","Package":"ordinary.fixture","Test":name})
    events.append({"Action":"pass","Package":"ordinary.fixture"})
    raw = b"".join((json.dumps(e)+"\n").encode() for e in events)
    result = ci.parse_native_vector(raw,entry,"ordinary.fixture")
    assert len(result["success_names"]) == 25 and result["native_authority"] is False
    controls = ["synthetic-complete-vector-not-native"]
    cases = {
        "missing-method": [e for e in events if e.get("Test") != top[-1]],
        "duplicate-run": [*events[:-1],{"Action":"run","Package":"ordinary.fixture","Test":top[0]},events[-1]],
        "duplicate-terminal": [*events[:-1],{"Action":"pass","Package":"ordinary.fixture","Test":top[0]},events[-1]],
        "skip": [{**e,"Action":"skip"} if e.get("Test")==top[-1] and e["Action"]=="pass" else e for e in events],
        "foreign-package": [{**e,"Package":"foreign"} if i==2 else e for i,e in enumerate(events)],
        "package-only": [events[0],events[-1]],
    }
    for name, vector in cases.items():
        body = b"".join((json.dumps(e)+"\n").encode() for e in vector)
        try: ci.parse_native_vector(body,entry,"ordinary.fixture")
        except ValueError: controls.append(name)
        else: raise AssertionError("negative vector admitted: "+name)
    for name, body in [("invalid-utf8",b"\xff"),("malformed-json",b"{\n"),("zero-selection",b"")]:
        try: ci.parse_native_vector(body,entry,"ordinary.fixture")
        except ValueError: controls.append(name)
        else: raise AssertionError("negative byte vector admitted")
    original_path = manager/"scripts/windows_foundation_source_guard.py"
    assert hashlib.sha256(original_path.read_bytes()).hexdigest() == lease["source_guard_sha256"]
    spec = importlib.util.spec_from_file_location("_ordinary_exact_guard",original_path)
    guard = importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
    original = guard.run_git
    for primary in (ValueError("ordinary-delegate-marker"),KeyboardInterrupt("ordinary-cancel-marker"),SystemExit("ordinary-exit-marker")):
        try:
            with ci.bind_source_git_delegate(guard,lambda *a,**k: (_ for _ in ()).throw(primary)) as binding:
                assert binding["original_run_git"] == "RETAINED_NOT_EXECUTED"
                guard.tree_rows(Path("ordinary-unused-path"),"ordinary-unused-tree")
        except BaseException as error:
            assert error is primary
        else: raise AssertionError("delegate failure swallowed")
        assert guard.run_git is original and guard._nt_bound is False
        controls.append("binding-restored-"+type(primary).__name__)
    primary, cancel, cleanup = ValueError("primary"),KeyboardInterrupt("cancel"),OSError("cleanup")
    try: job.raise_preserved_native_errors([primary,cancel,cleanup])
    except BaseExceptionGroup as group:
        assert group.exceptions == (primary,cancel,cleanup)
    else: raise AssertionError("simultaneous cancellation/error objects lost")
    controls.append("exact-primary-cancel-cleanup-group")
    single = SystemExit("single-original-object")
    try: job.raise_preserved_native_errors([single])
    except BaseException as actual: assert actual is single
    else: raise AssertionError("single original cancellation swallowed")
    controls.append("single-exact-object")
    # Failure-first cases were admitted by the frozen initial source (JSON29).
    for name,body in [
        ("duplicate-json-key",raw.replace(b'"Action": "start"',b'"Action": "fail", "Action": "start"',1)),
        ("false-Test-type",raw.replace(b'"Action": "start"',b'"Action": "start", "Test": false',1)),
        ("early-package-terminal",b"".join((json.dumps(e)+"\n").encode() for e in [events[0],events[-1],*events[1:-1]])),
        ("named-output-before-run",b"".join((json.dumps(e)+"\n").encode() for e in [events[0],
            {"Action":"output","Package":"ordinary.fixture","Test":top[0],"Output":"premature"},*events[1:]])),
        ("nonfinite-Elapsed",raw.replace(b'"Action": "start"',b'"Action": "start", "Elapsed": NaN',1)),
        ("boolean-Elapsed",raw.replace(b'"Action": "start"',b'"Action": "start", "Elapsed": true',1)),
        ("unknown-field",raw.replace(b'"Action": "start"',b'"Action": "start", "Unsupported": 1',1))]:
        try:ci.parse_native_vector(body,entry,"ordinary.fixture")
        except ValueError:controls.append(name)
        else:raise AssertionError("strict malformed vector admitted: "+name)
    temporary=Path(tempfile.mkdtemp(prefix="ordinary-nt-manager-parser-"))
    # Actual owned POSIX files exercise metadata/FD guards only, not WinAPI.
    runtime=temporary/"runtime";runtime.mkdir();(runtime/"owned").write_bytes(b"ordinary-owned")
    before=ci.snapshot_runtime_tree(runtime,time.monotonic()+10)
    assert ci.snapshot_runtime_tree(runtime,time.monotonic()+10,before)==before
    controls.append("owned-local-runtime-file-fence")
    (runtime/"owned").write_bytes(b"different-owned")
    try:ci.snapshot_runtime_tree(runtime,time.monotonic()+10,before)
    except ValueError:controls.append("local-runtime-change-denied")
    else:raise AssertionError("runtime drift accepted")
    os.link(runtime/"owned",runtime/"hardlink")
    try:ci.snapshot_runtime_tree(runtime,time.monotonic()+10)
    except ValueError:controls.append("local-runtime-hardlink-denied")
    else:raise AssertionError("runtime hardlink accepted")
    # Synthetic collector substitutes only an ordinary delegate; no Git or Win
    # process is launched. It writes real owned raw files for counter checks.
    original_collector=job.native_collect_stage
    actual_git=Path(shutil.which("git")); calls=[]
    fake=lambda *a,**kw:(Path(a[6]).mkdir(parents=True,exist_ok=False),
        (Path(a[6])/"stdout.raw").write_bytes(b""),(Path(a[6])/"stderr.raw").write_bytes(b"unsupported ordinary option"),
        calls.append(kw),{"stdout":b"","stderr":b"unsupported ordinary option","actual_root_exit":129})[-1]
    job.native_collect_stage=fake
    try:
        counter={"calls":0,"raw_bytes":0,"overall_deadline":time.monotonic()+10}
        try:ci.bounded_run_git_delegate(manager,temporary/"raw",actual_git,counter["overall_deadline"],counter,temporary,"status")
        except RuntimeError as error:assert str(error)=="git status failed: unsupported ordinary option"
        else:raise AssertionError("native Git nonzero semantics admitted")
        assert counter["raw_bytes"]==len(b"unsupported ordinary option") and calls[-1]["require_zero"] is False
        controls.append("ordinary-nonzero-Git-prefix-and-saved-counter")
        counter["calls"]=320; previous=len(calls)
        try:ci.bounded_run_git_delegate(manager,temporary/"raw",actual_git,counter["overall_deadline"],counter,temporary,"status")
        except RuntimeError:pass
        else:raise AssertionError("321st helper admitted")
        assert len(calls)==previous;controls.append("helper321-predelegate-denied")
        marker=KeyboardInterrupt("ordinary-collector-cancel")
        job.native_collect_stage=lambda *a,**k:(_ for _ in ()).throw(marker)
        counter={"calls":0,"raw_bytes":0,"overall_deadline":time.monotonic()+10}
        try:ci.bounded_run_git_delegate(manager,temporary/"cancelraw",actual_git,counter["overall_deadline"],counter,temporary,"status")
        except BaseException as actual:assert actual is marker
        else:raise AssertionError("collector cancel swallowed")
        controls.append("ordinary-Git-cancel-exact-object")
        # Saved failure bytes count toward the aggregate cap; both the exact
        # original cancellation and new counter rejection remain observable.
        job.native_collect_stage=lambda *a,**k:(Path(a[6]).mkdir(parents=True,exist_ok=False),
            (Path(a[6])/"stdout.raw").write_bytes(b"xx"),(_ for _ in ()).throw(marker))[-1]
        counter={"calls":0,"raw_bytes":16777215,"overall_deadline":time.monotonic()+10}
        try:ci.bounded_run_git_delegate(manager,temporary/"overflowraw",actual_git,counter["overall_deadline"],counter,temporary,"status")
        except BaseExceptionGroup as group:
            assert group.exceptions[0] is marker and isinstance(group.exceptions[1],RuntimeError)
        else:raise AssertionError("failure raw overflow/cancel not jointly preserved")
        assert counter["raw_bytes"]==16777217
        controls.append("saved-failure-byte-overflow-preserves-cancel")
    finally:job.native_collect_stage=original_collector
    assert job.native_collect_stage is original_collector
    # Last-error/filename callbacks are synthetic parser controls, not DLL calls.
    old_set=getattr(ci.ctypes,"set_last_error",None);old_get=getattr(ci.ctypes,"get_last_error",None)
    last={"error":0};ci.ctypes.set_last_error=lambda n:last.__setitem__("error",n)
    ci.ctypes.get_last_error=lambda:last["error"]
    try:
        fake_api=SimpleNamespace(GetModuleFileNameW=lambda h,b,n:(setattr(b,"value","/ordinary/loaded.dll"),len("/ordinary/loaded.dll"))[1])
        assert ci.module_filename_from_api(fake_api,123)=="/ordinary/loaded.dll"
        controls.append("synthetic-module-filename-length")
        fake_api.GetModuleFileNameW=lambda h,b,n:(last.__setitem__("error",122),n)[1]
        try:ci.module_filename_from_api(fake_api,123)
        except ValueError:controls.append("synthetic-module-truncation-denied")
        else:raise AssertionError("truncated module path admitted")
        fake_api.GetModuleFileNameW=lambda h,b,n:0
        try:ci.module_filename_from_api(fake_api,123)
        except OSError:controls.append("synthetic-module-zero-denied")
        else:raise AssertionError("module failure admitted")
    finally:
        for name,original_value in (("set_last_error",old_set),("get_last_error",old_get)):
            if original_value is None:delattr(ci.ctypes,name)
            else:setattr(ci.ctypes,name,original_value)
    discovery=("\n".join(top)+"\nok ordinary.fixture 0.01s\n").encode()
    assert ci.parse_native_discovery(discovery,entry)["actual_discovered_top_names"]==top
    controls.append("synthetic-discovery-exact-top-vector")
    try:ci.parse_native_discovery(discovery+top[0].encode()+b"\n",entry)
    except ValueError:controls.append("synthetic-discovery-duplicate-denied")
    else:raise AssertionError("extra actual discovered test admitted")
    original_loader=job.load_original_native_api;native_calls=[]
    job.load_original_native_api=lambda *a:native_calls.append(a)
    try:
        try:ci.execute_native_manager(manager,lease,temporary/"must-not-create")
        except RuntimeError:pass
        else:raise AssertionError("disabled source launched manager")
        assert not native_calls and not (temporary/"must-not-create").exists()
        controls.append("disabled-manager-preIO-no-native")
    finally:job.load_original_native_api=original_loader
    budget=job.NativeRawBudget(4194304)
    requested=budget.reserve("stdout");assert requested==65536
    try:budget.complete("stdout",requested+1)
    except RuntimeError:pass
    else:raise AssertionError("reservation over-transfer admitted")
    assert budget.saved["stdout"]==0 and budget.reserved["stdout"]==requested
    controls.append("ordinary-over-transfer-keeps-reservation")
    try:budget.reserve("stdout")
    except RuntimeError:controls.append("ordinary-UNKNOWN-reservation-not-reissued")
    else:raise AssertionError("unresolved read reissued")
    budget.complete("stdout",17);assert budget.saved["stdout"]==17 and budget.reserved["stdout"]==0
    controls.append("ordinary-actual-count-unused-reservation-released")
    full=job.NativeRawBudget(4194304)
    for _ in range(32):full.complete("stdout",full.reserve("stdout"))
    try:full.reserve("stdout")
    except RuntimeError:controls.append("ordinary-full-channel-noEOF-no-probe")
    else:raise AssertionError("extra read at full channel admitted")
    shared=job.NativeRawBudget(32);assert shared.reserve("stdout")==32
    try:shared.reserve("stderr")
    except RuntimeError:controls.append("ordinary-pending-shared-cap-not-double-reserved")
    else:raise AssertionError("shared pending cap oversubscribed")
    receipt=temporary/"exclusive-receipt.json";ci.write_native_receipt(receipt,{"owned":True})
    old=receipt.read_bytes()
    try:ci.write_native_receipt(receipt,{"overwrite":True})
    except FileExistsError:pass
    else:raise AssertionError("existing receipt overwritten")
    assert receipt.read_bytes()==old;controls.append("owned-exclusive-receipt-no-overwrite")
    original_open=Path.open;attempts=[]
    real_output=original_open(temporary/"receipt-backing","w",encoding="utf8")
    primary=ValueError("ordinary-receipt-write");cancel=SystemExit("ordinary-receipt-close")
    holder=SimpleNamespace(write=lambda data:(_ for _ in ()).throw(primary),
        close=lambda:(attempts.append("receipt"),real_output.close(),(_ for _ in ()).throw(cancel))[-1])
    Path.open=lambda *a,**k:holder
    try:
        try:ci.write_native_receipt(temporary/"uncertain-receipt",{"owned":True})
        except BaseExceptionGroup as group:assert group.exceptions==(primary,cancel)
        else:raise AssertionError("receipt primary/closecancel lost")
    finally:Path.open=original_open
    assert attempts==["receipt"] and holder in ci.RESOURCE_QUARANTINE
    controls.append("ordinary-receipt-closeUNKNOWN-holder-exactcancel")
    actual_lstat=Path.lstat;runtime_info=actual_lstat(runtime)
    Path.lstat=lambda p,*a,**k:SimpleNamespace(st_mode=runtime_info.st_mode,st_file_attributes=0x400) if p==runtime else actual_lstat(p,*a,**k)
    try:
        try:ci.snapshot_runtime_tree(runtime,time.monotonic()+5)
        except ValueError:controls.append("synthetic-root-reparse-pre-read-denied")
        else:raise AssertionError("root reparse metadata admitted")
    finally:Path.lstat=actual_lstat
    archive_path=temporary/"owned-ordinary.zip"
    with zipfile.ZipFile(archive_path,"x") as archive:archive.writestr("owned.dat",b"ordinary-member")
    with zipfile.ZipFile(archive_path) as archive:
        result=ci.extract_owned_member(archive,archive.getinfo("owned.dat"),temporary/"owned-member",time.monotonic()+5)
        assert result["bytes"]==len(b"ordinary-member") and (temporary/"owned-member").read_bytes()==b"ordinary-member"
        controls.append("actual-owned-ZIP-member-not-officialGo")
        info=archive.getinfo("owned.dat");info.file_size+=1
        try:ci.extract_owned_member(archive,info,temporary/"bad-metadata-member",time.monotonic()+5)
        except ValueError:controls.append("owned-ZIP-actual-size-metadata-mismatch-denied")
        else:raise AssertionError("ZIP metadata mismatch admitted")
    try:ci.extract_verified_go_zip(archive_path,temporary/"must-not-extract",time.monotonic()+5)
    except ValueError:controls.append("ordinary-ZIP-cannot-be-official-Go")
    else:raise AssertionError("ordinary archive accepted as pinned official Go")
    assert not (temporary/"must-not-extract").exists()
    real_member=original_open(temporary/"owned-member","rb");real_output=original_open(temporary/"member-backing","wb")
    primary=ValueError("ordinary-member-read");output_cancel=SystemExit("ordinary-member-outputclose");member_cancel=KeyboardInterrupt("ordinary-member-close")
    attempts=[]
    member=SimpleNamespace(read=lambda size:(_ for _ in ()).throw(primary),
        close=lambda:(attempts.append("member"),real_member.close(),(_ for _ in ()).throw(member_cancel))[-1])
    output=SimpleNamespace(write=lambda data:real_output.write(data),
        close=lambda:(attempts.append("output"),real_output.close(),(_ for _ in ()).throw(output_cancel))[-1])
    Path.open=lambda *a,**k:output
    try:
        try:ci.extract_owned_member(SimpleNamespace(open=lambda *a:member),
            SimpleNamespace(file_size=5,filename="ordinary"),temporary/"member-fault",time.monotonic()+5)
        except BaseExceptionGroup as group:assert group.exceptions==(primary,output_cancel,member_cancel)
        else:raise AssertionError("member/output independent close cancellation lost")
    finally:Path.open=original_open
    assert attempts==["output","member"] and member in ci.RESOURCE_QUARANTINE and output in ci.RESOURCE_QUARANTINE
    controls.append("ordinary-member-and-output-closeUNKNOWN-independent-exactobjects")
    # Negative-only binding fixture. This sparse owned file has the pinned
    # length, but NOT the official digest. The mocked snapshot never supplies
    # official-Go evidence; constructor/read/close must fail before extraction.
    malformed=temporary/"owned-sparse-malformed.zip"
    with original_open(malformed,"xb") as sparse:sparse.truncate(87295983)
    file_info=malformed.stat();old_snapshot=ci.snapshot_runtime_file
    fixture_identity={"bytes":file_info.st_size,
        "sha256":"40b16bc8f00540a2cb02dff4de72b73e966fdd8d65f95e33d8e4080b48a2459a",
        "device":file_info.st_dev,"file_id":file_info.st_ino,"links":file_info.st_nlink}
    ci.snapshot_runtime_file=lambda *a:fixture_identity
    actual_input=original_open(malformed,"rb");attempts=[]
    primary=ValueError("ordinary-actual-ZipFile-constructor-read")
    cancel=KeyboardInterrupt("ordinary-owned-archive-input-close")
    archive_holder=SimpleNamespace(fileno=actual_input.fileno,seek=actual_input.seek,tell=actual_input.tell,
        read=lambda *a:(_ for _ in ()).throw(primary),
        close=lambda:(attempts.append("archive_input"),actual_input.close(),(_ for _ in ()).throw(cancel))[-1])
    Path.open=lambda *a,**k:archive_holder
    try:
        try:ci.extract_verified_go_zip(malformed,temporary/"must-not-extract-ctor",time.monotonic()+5)
        except BaseExceptionGroup as group:assert group.exceptions==(primary,cancel)
        else:raise AssertionError("actual ZipFile constructor primary/inputclose cancellation lost")
    finally:Path.open=original_open;ci.snapshot_runtime_file=old_snapshot
    assert attempts==["archive_input"] and actual_input.closed and archive_holder in ci.RESOURCE_QUARANTINE
    assert not (temporary/"must-not-extract-ctor").exists()
    controls.append("negative-only-identity-binding-actual-ZipFile-constructor-primary-inputcloseUNKNOWN")
    # The real malformed ZIP error also propagates with a normally closed
    # caller-owned input. No synthetic constructor or Windows call is involved.
    ci.snapshot_runtime_file=lambda *a:fixture_identity
    try:
        try:ci.extract_verified_go_zip(malformed,temporary/"must-not-extract-badzip",time.monotonic()+5)
        except zipfile.BadZipFile:controls.append("negative-only-identity-binding-real-BadZipFile-no-extraction")
        else:raise AssertionError("actual malformed owned ZIP admitted")
    finally:ci.snapshot_runtime_file=old_snapshot
    assert not (temporary/"must-not-extract-badzip").exists()
    # Both returned-ZIP close and its independent owned-input close are tried
    # once even if each reports cancellation. The ZIP factory here is an
    # explicitly synthetic cleanup-boundary fixture, not constructor evidence.
    actual_input=original_open(malformed,"rb");actual_zip=zipfile.ZipFile(archive_path)
    primary=ValueError("ordinary-returned-ZIP-inventory")
    zip_cancel=SystemExit("ordinary-returned-ZIP-close");input_cancel=KeyboardInterrupt("ordinary-second-input-close")
    attempts=[];old_zip_factory=zipfile.ZipFile
    zip_holder=SimpleNamespace(infolist=lambda:(_ for _ in ()).throw(primary),
        close=lambda:(attempts.append("zip"),actual_zip.close(),(_ for _ in ()).throw(zip_cancel))[-1])
    input_holder=SimpleNamespace(fileno=actual_input.fileno,
        close=lambda:(attempts.append("input"),actual_input.close(),(_ for _ in ()).throw(input_cancel))[-1])
    ci.snapshot_runtime_file=lambda *a:fixture_identity;Path.open=lambda *a,**k:input_holder
    zipfile.ZipFile=lambda actual_input:zip_holder
    try:
        try:ci.extract_verified_go_zip(malformed,temporary/"must-not-extract-close",time.monotonic()+5)
        except BaseExceptionGroup as group:assert group.exceptions==(primary,zip_cancel,input_cancel)
        else:raise AssertionError("ZIP/input independent cancellation objects lost")
    finally:zipfile.ZipFile=old_zip_factory;Path.open=original_open;ci.snapshot_runtime_file=old_snapshot
    assert attempts==["zip","input"] and actual_input.closed and actual_zip.fp is None
    assert zip_holder in ci.RESOURCE_QUARANTINE and input_holder in ci.RESOURCE_QUARANTINE
    controls.append("synthetic-ZIP-and-owned-input-onceclose-exact-three-object-group")
    import windows_nt_output_native_controls as native
    owned=KeyboardInterrupt("owned-expected-marker");unexpected=SystemExit("real-unexpected-cancel")
    assert not native.native_has_unexpected_cancel(BaseExceptionGroup("owned",[owned,OSError("ordinary-cleanup")]),owned)
    assert native.native_has_unexpected_cancel(BaseExceptionGroup("nested",[owned,BaseExceptionGroup("nestedcancel",[unexpected])]),owned)
    controls.append("ordinary-nested-unexpected-cancel-never-accepted")
    value = {"scope":"ORDINARY_SYNTHETIC_PARSER_BINDING_ONLY","controls":controls,
        "count":len(controls),"actual_native_api_calls":0,"actual_go_processes":0,
        "actual_original_native_methods":0,"native_authority":False}
    print(json.dumps(value,sort_keys=True))
    return value


if __name__ == "__main__":
    manager_control_entry()
