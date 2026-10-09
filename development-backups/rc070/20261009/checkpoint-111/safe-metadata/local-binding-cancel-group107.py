"""Owned POSIX fixed-input controls; zero native processes/API/Go, no restore positive."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"scripts"))
import windows_nt_output_native_ci as ci
manager=Path(__file__).resolve().parents[2]
backup=Path(sys.argv[1])
spec=importlib.util.spec_from_file_location("_fixed_original_local_guard94",manager/"scripts/windows_foundation_source_guard.py")
guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
m=guard.load_manifest(manager/"scripts/windows_foundation_source_manifest.json")
inputs={}
for row in m["exact73"]:
    data=(backup/(m["exact73_prefix"]+row["path"]+".source")).read_bytes()
    guard.check_blob(data,row)
    inputs[m["exact73_backup_commit"]+":"+m["exact73_prefix"]+row["path"]+".source"]=data
patch=(backup/m["full43_patch_path"]).read_bytes()
assert len(patch)==167168 and hashlib.sha256(patch).hexdigest()==guard.PATCH_SHA
inputs[m["full43_backup_commit"]+":"+m["full43_patch_path"]]=patch
root=Path(tempfile.mkdtemp(prefix="owned-original-local94-"))
calls=[]
def transparent_typed_native_replacement(repo,*args,**kwargs):
    calls.append((str(repo),args,kwargs))
    if args[0]=="fetch":return b""
    assert args[0]=="show" and not kwargs
    return inputs[args[1]]
original=guard.run_git
guard.run_git=transparent_typed_native_replacement
try:
    payload=root/"fixed-input"
    before=ci.stage_owned_original_payloads(guard,manager,payload,m,time.monotonic()+30)
finally:guard.run_git=original
expected=[("fetch","--no-tags",guard.REPOSITORY,c) for c in sorted({m["exact73_backup_commit"],m["full43_backup_commit"]})]
expected += [("show",m["exact73_backup_commit"]+":"+m["exact73_prefix"]+r["path"]+".source") for r in m["exact73"]]
expected += [("show",m["full43_backup_commit"]+":"+m["full43_patch_path"])]
assert [a for _,a,_ in calls]==expected and len(calls)==76
assert before["expected_file_roles"]==74 and before["expected_directory_roles"]==31 and before["actual_bytes"]==592919
assert ci.verify_owned_original_payloads(guard,payload,m,time.monotonic()+30)==before
import types
import windows_nt_output_native_controls as native
marker=KeyboardInterrupt("ordinary-actual-module-postassignment-cancel")
restore_cancel=SystemExit("ordinary-binding-restore-cancel")
assignments=[]
class ActualModuleAssignmentCancel(types.ModuleType):
    def __setattr__(self,name,value):
        types.ModuleType.__setattr__(self,name,value)
        if name=="run_git":
            assignments.append("restore" if value is original else "bind")
            if value is not original:raise marker
            if sys.argv[2]=="fixed-group":raise restore_cancel
oldclass=guard.__class__;guard.__class__=ActualModuleAssignmentCancel
oldspec=native.importlib.util.spec_from_file_location;oldmodule=native.importlib.util.module_from_spec;oldplatform=native.sys.platform
native.importlib.util.spec_from_file_location=lambda *a,**k:types.SimpleNamespace(loader=types.SimpleNamespace(exec_module=lambda module:None))
native.importlib.util.module_from_spec=lambda spec:guard
native.sys.platform="win32"  # Explicit ordinary typing substitution, no Windows API called.
try:
    try:native.native_original_local_payload_controls(manager,payload,root,m and time.monotonic()+30)
    except BaseExceptionGroup as actual:assert sys.argv[2]=="fixed-group" and actual.exceptions==(marker,restore_cancel)
    except BaseException as actual:assert actual is marker
    else:raise AssertionError("actual assignment cancellation swallowed")
    result={"scope":"ORDINARY_ACTUAL_MODULE_ASSIGNMENT_WITH_MOCKED_PLATFORM_AND_LOADER","bind_then_cancel":assignments==["bind"],"restored_exact_original":guard.run_git is original,"assignments":list(assignments),"actual_native_API_calls":0,"actual_native_Git_processes":0,"actual_Go_processes":0}
    if sys.argv[2]=="failure-first":assert result["bind_then_cancel"] and not result["restored_exact_original"]
    else:assert result["restored_exact_original"] and assignments==["bind","restore"]
finally:
    native.importlib.util.spec_from_file_location=oldspec;native.importlib.util.module_from_spec=oldmodule;native.sys.platform=oldplatform
    types.ModuleType.__setattr__(guard,"run_git",original);guard.__class__=oldclass
print(json.dumps(result,sort_keys=True))
