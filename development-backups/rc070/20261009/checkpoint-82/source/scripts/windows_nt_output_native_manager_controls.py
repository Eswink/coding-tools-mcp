"""Ordinary synthetic parser/binding/error controls; ZERO native API credit."""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

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
    value = {"scope":"ORDINARY_SYNTHETIC_PARSER_BINDING_ONLY","controls":controls,
        "count":len(controls),"actual_native_api_calls":0,"actual_go_processes":0,
        "actual_original_native_methods":0,"native_authority":False}
    print(json.dumps(value,sort_keys=True))
    return value


if __name__ == "__main__":
    manager_control_entry()
