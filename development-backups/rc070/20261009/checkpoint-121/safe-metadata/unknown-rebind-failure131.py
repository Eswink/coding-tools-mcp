"""UNKNOWN sameguard rebind failure-first, actual ModuleType faults, zero native."""
import importlib.util,json,sys,types
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"scripts"))
import windows_nt_output_native_ci as ci
root=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location("_real_original_guard",root/"scripts/windows_foundation_source_guard.py")
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
original=g.run_git;attempts=[];calls=[];armed=[True]
replacement=lambda *a,**k:(calls.append((a,k)),b"owned ordinary")[1]
primary=ValueError("ordinary-primary-before-unknown");cleanup=SystemExit("ordinary-restore-once-unknown")
class ActualModule(types.ModuleType):
    def __setattr__(self,name,value):
        types.ModuleType.__setattr__(self,name,value)
        if name in ("run_git","_nt_bound"):attempts.append(name)
        if name=="run_git" and value is original and armed[0]:
            armed[0]=False;raise cleanup
g.__class__=ActualModule
try:
    with ci.bind_source_git_delegate(g,replacement):raise primary
except BaseExceptionGroup as error:assert error.exceptions==(primary,cleanup)
else:raise AssertionError("unknown control not reached")
assert g._nt_bound is False and g.run_git is original
assert any(isinstance(f,dict) and f.get("guard") is g and f["state"]=="UNKNOWN" for f in ci.RESOURCE_QUARANTINE)
previous=len(attempts);entered=False
try:
    with ci.bind_source_git_delegate(g,replacement):
        entered=True;g.run_git("ordinary-not-a-repo","ordinary-no-native")
except RuntimeError as error:assert sys.argv[1]=="fixed" and "uncertain" in str(error)
else:assert sys.argv[1]=="failure-first"
result={"scope":"ORDINARY_ACTUAL_UNKNOWN_BINDING_FRAME_NOT_NATIVEHANDLE","entered_after_UNKNOWN":entered,"delegate_calls_after_UNKNOWN":len(calls),"new_binding_assignments_after_UNKNOWN":len(attempts)-previous,"actual_guard_frame_strong_retained":True,"actual_Windows_API":0,"actual_native_processes":0,"actual_Go":0}
if sys.argv[1]=="failure-first":assert entered and len(calls)==1
else:assert not entered and not calls and len(attempts)==previous
print(json.dumps(result,sort_keys=True))
