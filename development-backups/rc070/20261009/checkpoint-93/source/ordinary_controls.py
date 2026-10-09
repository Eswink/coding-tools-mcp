"""Stage I defaults to AST/pure parser controls. No bridge import at top level.

Only --owned-case C01 may run a native support case, AFTER separate Stage II
root authorization. Remaining fourteen-case inventory is honest NOTRUN or
IMPLEMENTATION_PENDING; it cannot be promoted from static controls.
"""
import argparse
import ast
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
SOURCES = ("syscall_x86_64.h", "birth_entry.S", "birth_module.c",
           "root_entry.S", "root_collector.c", "owner_adapter.py",
           "ordinary_controls.py", "build_source_owner.py")
CASES = {
    "C01": "sealed no-LAUNCH actual native support/terminal/IO",
    "C02": "ordinary labeled preallocation refusal, zero child",
    "C03": "post-created result failure retains original escrow",
    "C04": "actual pre-BOOT/no-LAUNCH abort, not command success",
    "C05": "shared .2 fixture readiness (telemetry pending)",
    "C06": "actual partial LAUNCH cancellation (fixture seam pending)",
    "C07": "genuine native exec errno",
    "C08": "already-dispatched builtin closure, no command status",
    "C09": "actual fork/doublefork/setsid adoption",
    "C10": "held child signal terminal (telemetry pending)",
    "C11": "actual combined overlimit output UNKNOWN",
    "C12": "missing EOF/once-close UNKNOWN",
    "C13": "primary and multiple original cancellation objects",
    "C14": "actual source/seal/foreignhandle mismatch (fixture seam pending)",
}


def run_static_controls():
    results = []
    trees = {}
    for name in SOURCES:
        raw = (HERE / name).read_text()
        if name.endswith(".py"):
            trees[name] = ast.parse(raw, filename=name)
        results.append({"case": "source_present:" + name, "pass": bool(raw)})
    # Compile ONLY extracted effect-free functions, not any module/import.
    adapter = trees["owner_adapter.py"]
    names = {"parse_protocol", "raise_preserved"}
    pure = ast.Module(body=[node for node in adapter.body
                           if isinstance(node, ast.FunctionDef) and node.name in names],
                      type_ignores=[])
    namespace = {}
    exec(compile(pure, "sealed_adapter_pure_functions", "exec"), namespace)
    parse = namespace["parse_protocol"]
    for frames in [(b"B\nE\n",), (b"B", b"\nE", b"\n"), (b"", b"B\n", b"E\n")]:
        phase = 0
        for raw in frames:
            phase = parse(raw, phase)
        results.append({"case": "actual_pure_split_parser", "pass": phase == 4})
    for frames in [(b"E\n",), (b"B\nX\n",), (b"B\nE\nB",), (b"B\n\n",)]:
        try:
            phase = 0
            for raw in frames:
                phase = parse(raw, phase)
        except ValueError:
            refused = True
        else:
            refused = False
        results.append({"case": "actual_pure_protocol_refusal", "pass": refused})
    primary, cancel1, cancel2 = SystemExit(1), KeyboardInterrupt(), SystemExit(9)
    preserved = False
    try:
        namespace["raise_preserved"](primary, [cancel1, cancel2])
    except BaseExceptionGroup as group:
        preserved = (len(group.exceptions) == 3 and
                     all(a is b for a, b in zip(group.exceptions, (primary, cancel1, cancel2))))
    results.append({"case": "actual_primary_multi_cancel_objects", "pass": preserved})
    module_top_bridge_import = any(
        isinstance(node, (ast.Import, ast.ImportFrom)) and
        any(alias.name == "_rc_native_birth" for alias in node.names)
        for node in adapter.body)
    results.append({"case": "no_top_level_bridge_import", "pass": not module_top_bridge_import})
    birth = (HERE / "birth_module.c").read_text()
    results.extend([
        {"case": "opaque_constructor_denied_source", "pass": ".tp_new=deny_new" in birth and "Py_TPFLAGS_BASETYPE" not in birth},
        {"case": "prelinked_escrow_before_first_resource_source", "pass": birth.index("registry=r") < birth.index("RC_NR_MEMFD_CREATE")},
        {"case": "native_launched_sticky_before_write_source", "pass": birth.index("r->launch_attempted=1") < birth.index("long got=rc_sc3(RC_NR_WRITE")},
    ])
    return {"profile": "static_ast_and_pure_functions_only", "original_sut": 0,
            "native_kernel_calls": 0, "bridge_imports": 0,
            "compiled": False, "results": results,
            "passed": all(row["pass"] for row in results),
            "ordinary_native_inventory": {key: "NOTRUN" for key in CASES}}


def ordinary_case(case):
    if case != "C01":
        return {"case": case, "status": "IMPLEMENTATION_PENDING", "actual_native_run": 0}
    # Stage II only. Importing this script or --static does NOT reach here.
    from owner_adapter import NativeOwnerAdapter
    owner = None
    primary = None
    try:
        owner = NativeOwnerAdapter()
        owner.start()  # No LAUNCH bytes whatsoever for support admission.
    except BaseException as error:
        primary = error
    if owner is not None:
        status = owner.stop(primary) if primary is None else owner.abort_no_launch(primary)
        return {"case": case, "status": "LOCAL_NATIVE_CLOSED", "local": status,
                "original_sut": 0, "command_result": "NOTESTABLISHED"}
    if isinstance(primary, OSError) and primary.errno in (1, 38, 95):
        return {"case": case, "status": "BLOCKED_UNSUPPORTED", "errno": primary.errno,
                "actual_native_run": "factory_attempt_only", "fallback": False}
    if primary is not None:
        raise primary
    raise RuntimeError("missing_actual_owner")


def run_owned_controls(case):
    if case not in CASES:
        raise ValueError("finite_case_only")
    return ordinary_case(case)


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--static", action="store_true")
    group.add_argument("--owned-case", choices=tuple(CASES))
    args = parser.parse_args()
    result = run_owned_controls(args.owned_case) if args.owned_case else run_static_controls()
    print(json.dumps(result, sort_keys=True))
    return 0 if (result.get("passed", False) or
                 result.get("status") == "LOCAL_NATIVE_CLOSED") else 1


if __name__ == "__main__":
    raise SystemExit(main())
