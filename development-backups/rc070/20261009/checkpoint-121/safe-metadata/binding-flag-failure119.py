"""Actual ModuleType binding failure-first, zero native APIs/processes/Go."""
import importlib.util,json,sys,types
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"scripts"))
import windows_nt_output_native_ci as ci
root=Path(__file__).resolve().parents[2]
results=[]
for kind in ("flag-effect-cancel","restore-error-clear-not-attempted"):
    spec=importlib.util.spec_from_file_location("_real_frozen_source_guard",root/"scripts/windows_foundation_source_guard.py")
    guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
    original=guard.run_git;delegate=lambda *a,**k:b""
    marker=KeyboardInterrupt("ordinary-owned-boundflag-effect-cancel")
    primary=ValueError("ordinary-delegate-primary")
    cleanup=SystemExit("ordinary-first-binding-restore-cancel")
    assignments=[]
    class ActualGuardModule(types.ModuleType):
        def __setattr__(self,name,value):
            types.ModuleType.__setattr__(self,name,value)
            if name in ("run_git","_nt_bound"):
                assignments.append([name,"original" if value is original else value if type(value) is bool else "delegate"])
                if name=="_nt_bound" and value is True and kind=="flag-effect-cancel":raise marker
                if name=="run_git" and value is original and kind=="restore-error-clear-not-attempted":raise cleanup
    guard.__class__=ActualGuardModule
    try:
        with ci.bind_source_git_delegate(guard,delegate):
            if kind=="restore-error-clear-not-attempted":raise primary
    except BaseExceptionGroup as error:assert kind=="restore-error-clear-not-attempted" and error.exceptions==(primary,cleanup)
    except BaseException as error:assert kind=="flag-effect-cancel" and error is marker
    else:raise AssertionError("actual binding cancellation swallowed")
    bound=guard._nt_bound
    if sys.argv[1]=="failure-first":assert bound is True and not any(n=="_nt_bound" and v is False for n,v in assignments)
    else:assert bound is False and guard.run_git is original and assignments[-1]==["_nt_bound",False]
    results.append({"kind":kind,"assignments":assignments,"actual_known_original_binding":guard.run_git is original,"bound_after":bound,"exact_original_exception_objects_asserted":True})
print(json.dumps({"scope":"ORDINARY_ACTUAL_MODULE_BINDING_ONLY","results":results,"actual_Win_API":0,"actual_native_processes":0,"actual_Go":0},sort_keys=True))
