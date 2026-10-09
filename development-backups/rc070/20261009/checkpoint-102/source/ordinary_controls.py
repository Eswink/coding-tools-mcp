"""Stage I defaults to AST/pure parser controls. No bridge import at top level.

Only --owned-case C01 may run a native support case, AFTER separate Stage II
root authorization. Remaining fourteen-case inventory is honest NOTRUN or
IMPLEMENTATION_PENDING; it cannot be promoted from static controls.
"""
import argparse
import ast
import json
import pathlib
import hashlib
import importlib.util

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


class ForwardFile:
    """Ordinary test adapter: every effect delegates to its actual opened file."""
    def __init__(self, actual, read_error=None, write_error=None, close_error=None):
        self.actual = actual
        self.read_error, self.write_error, self.close_error = read_error, write_error, close_error
        self.close_calls = 0

    def __getattr__(self, name):
        return getattr(self.actual, name)

    def read(self, *args):
        result = self.actual.read(*args)
        if self.read_error is not None:
            error, self.read_error = self.read_error, None
            raise error
        return result

    def write(self, *args):
        result = self.actual.write(*args)
        if self.write_error is not None:
            error, self.write_error = self.write_error, None
            raise error
        return result

    def close(self):
        self.close_calls += 1
        result = self.actual.close()  # genuine close ALWAYS precedes injected observation
        if self.close_error is not None:
            error, self.close_error = self.close_error, None
            raise error
        return result


class ForwardSelector:
    def __init__(self, actual, close_error):
        self.actual, self.close_error = actual, close_error
        self.close_calls = 0

    def __getattr__(self, name):
        return getattr(self.actual, name)

    def close(self):
        self.close_calls += 1
        result = self.actual.close()
        if self.close_error is not None:
            error, self.close_error = self.close_error, None
            raise error
        return result


def contains_original(error, original):
    if error is original:
        return True
    return isinstance(error, BaseExceptionGroup) and any(
        contains_original(member, original) for member in error.exceptions)


def capture_patches(patches, action):
    """Capture before install; each restore attempts independently, preserving errors."""
    captured = [(obj, name, getattr(obj, name), replacement)
                for obj, name, replacement in patches]
    attempts, errors, primary, result = [], [], None, None
    try:
        for obj, name, original, replacement in captured:
            attempts.append((obj, name, original))  # before potentially failing setter
            setattr(obj, name, replacement)
            if getattr(obj, name) is not replacement:
                raise RuntimeError("ordinary_hook_install_unknown")
        result = action()
    except BaseException as error:
        primary = error
    finally:
        for obj, name, original in reversed(attempts):
            try:
                setattr(obj, name, original)
                if getattr(obj, name) is not original:
                    raise RuntimeError("ordinary_hook_restore_unknown")
            except BaseException as error:
                errors.append(error)
    if errors:
        causes = ([primary] if primary is not None else []) + errors
        primary = causes[0] if len(causes) == 1 else BaseExceptionGroup(
            "ordinary_control_primary_and_restore", causes)
    return primary, result, errors


def run_builder_owned_controls(out):
    """Explicit Stage I ordinary compiler/file cases; separate root scope approval.

    Never compiles a ROOT or bridge and never calls native birth. The only real
    process argv is official fixed GCC --version or -M on our own empty unit.
    Hooks forward real operations before labeled after-operation exceptions.
    """
    if not out.is_absolute() or out.exists():
        raise ValueError("exclusive_absent_ordinary_output_required")
    out.mkdir(mode=0o700)
    spec = importlib.util.spec_from_file_location("ordinary_stagei_builder", HERE / "build_source_owner.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)  # effect-free Python builder, NEVER native bridge
    source_before = {name: builder.file_identity(HERE / name) for name in SOURCES}
    gcc_before = builder.file_identity(builder.GCC)
    if gcc_before["sha256"] != "a23ecab8ff08f09ad8c80602c2c5df7f49e09c25905cb8975902e101bf72635f":
        raise RuntimeError("fixed_actual_gcc_identity_mismatch")
    actual_popen = builder.subprocess.Popen
    actual_selector = builder.selectors.DefaultSelector
    actual_open = pathlib.Path.open
    actual_stat = builder.os.fstat
    actual_read = builder.os.read
    created, forwarded_files, selectors, results = [], [], [], []
    state = {"jobs": [], "log_bytes": 0}

    def real_creator(*args, **kwargs):
        actual = actual_popen(*args, **kwargs)
        created.append(actual)  # same actual Popen object; no PID reconstruction
        return actual

    primary = SystemExit(31)
    def broken_selector():
        raise primary
    error, _, restores = capture_patches(
        [(builder.subprocess, "Popen", real_creator),
         (builder.selectors, "DefaultSelector", broken_selector)],
        lambda: builder.run_job([str(builder.GCC), "--version"], out, state, "K01"))
    proc = created[-1]
    results.append({"case": "K01_post_created_selector_primary", "pass":
                    contains_original(error, primary) and not restores and
                    proc.returncode is not None and proc.stdout.closed and proc.stderr.closed,
                    "actual_created": True, "actual_returncode": proc.returncode})

    cancel = KeyboardInterrupt()
    def closing_selector():
        wrapper = ForwardSelector(actual_selector(), cancel)
        selectors.append(wrapper)
        return wrapper
    error, _, restores = capture_patches(
        [(builder.subprocess, "Popen", real_creator),
         (builder.selectors, "DefaultSelector", closing_selector)],
        lambda: builder.run_job([str(builder.GCC), "--version"], out, state, "K02"))
    selected = selectors[-1]
    held = [item for item in builder._FILE_HOLDERS if item["object"] is selected]
    proc = created[-1]
    results.append({"case": "K02_first_close_cancel_remaining_pipes", "pass":
                    contains_original(error, cancel) and not restores and selected.close_calls == 1
                    and len(held) == 1 and held[0]["state"] == "UNKNOWN"
                    and proc.stdout.closed and proc.stderr.closed and proc.returncode is not None,
                    "retained_actual_unknown_selector": bool(held)})

    target, reader_error, writer_error, closer_error = None, None, None, None
    def target_open(path, *args, **kwargs):
        actual = actual_open(path, *args, **kwargs)
        if pathlib.Path(path) == target:
            wrapper = ForwardFile(actual, reader_error, writer_error, closer_error)
            forwarded_files.append(wrapper)
            return wrapper
        return actual

    target = out / "K03-negative-json.json"
    writer_error, closer_error = SystemExit(32), KeyboardInterrupt()
    error, _, restores = capture_patches([(pathlib.Path, "open", target_open)],
                                         lambda: builder.save_json(target, {"ordinary": True}))
    wrapper = forwarded_files[-1]
    held = [item for item in builder._FILE_HOLDERS if item["object"] is wrapper]
    results.append({"case": "K03_actual_write_primary_close_cancel", "pass":
                    contains_original(error, writer_error) and contains_original(error, closer_error)
                    and not restores and wrapper.actual.closed and wrapper.close_calls == 1
                    and len(held) == 1 and held[0]["state"] == "UNKNOWN"})

    target = out / "K04-actual-metadata.bin"
    with builder.OwnedFile(target, "xb") as stream:
        stream.write(b"ordinary_metadata_input")
    reader_error, writer_error, closer_error = None, None, SystemExit(34)
    primary = KeyboardInterrupt()
    fail_stat = [True]
    def inject_stat(fd):
        result = actual_stat(fd)
        if fail_stat[0]:
            fail_stat[0] = False
            raise primary
        return result
    error, _, restores = capture_patches([(pathlib.Path, "open", target_open),
                                          (builder.os, "fstat", inject_stat)],
                                         lambda: builder.file_identity(target))
    wrapper = forwarded_files[-1]
    held = [item for item in builder._FILE_HOLDERS if item["object"] is wrapper]
    results.append({"case": "K04_true_fstat_primary_close_cancel", "pass":
                    contains_original(error, primary) and contains_original(error, closer_error)
                    and not restores and wrapper.actual.closed and wrapper.close_calls == 1
                    and len(held) == 1 and held[0]["state"] == "UNKNOWN"})

    inert = out / "K05-inert-payload.bin"
    with builder.OwnedFile(inert, "xb") as stream:
        stream.write(b"ordinary_inert_bytes_not_ELF_not_executed")
    image_out = out / "K05-image"
    image_out.mkdir(mode=0o700)
    target = image_out / "root_image.inc"
    reader_error, writer_error, closer_error = None, SystemExit(35), KeyboardInterrupt()
    error, _, restores = capture_patches([(pathlib.Path, "open", target_open)],
                                         lambda: builder.embed_root(inert, image_out))
    wrapper = forwarded_files[-1]
    held = [item for item in builder._FILE_HOLDERS if item["object"] is wrapper]
    results.append({"case": "K05_inert_embedding_write_close_cancel", "pass":
                    contains_original(error, writer_error) and contains_original(error, closer_error)
                    and not restores and wrapper.actual.closed and wrapper.close_calls == 1
                    and len(held) == 1 and held[0]["state"] == "UNKNOWN",
                    "root_execution": False, "input_is_not_native_image": True})

    empty = out / "K06-empty.c"
    with builder.OwnedFile(empty, "x", encoding="ascii") as stream:
        stream.write("/* ordinary empty unit: no ROOT/bridge code */\n")
    target = out / "K06.d"
    reader_error, writer_error, closer_error = KeyboardInterrupt(), None, SystemExit(36)
    error, _, restores = capture_patches([(pathlib.Path, "open", target_open)],
        lambda: builder.header_dependencies(empty, ["-std=c11"], out, state, "K06"))
    wrapper = forwarded_files[-1]
    held = [item for item in builder._FILE_HOLDERS if item["object"] is wrapper]
    results.append({"case": "K06_actual_empty_header_read_close_cancel", "pass":
                    contains_original(error, reader_error) and contains_original(error, closer_error)
                    and not restores and wrapper.actual.closed and wrapper.close_calls == 1
                    and len(held) == 1 and held[0]["state"] == "UNKNOWN"})

    primary, selector_cancel, stdout_cancel, stderr_cancel = SystemExit(37), KeyboardInterrupt(), SystemExit(38), BaseException("ordinary_cancel")
    def multi_creator(*args, **kwargs):
        actual = real_creator(*args, **kwargs)
        actual.stdout = ForwardFile(actual.stdout, close_error=stdout_cancel)
        actual.stderr = ForwardFile(actual.stderr, close_error=stderr_cancel)
        return actual
    cancel = selector_cancel
    first_read = [True]
    observed_bytes = [0]
    def panic_read(fd, size):
        actual = actual_read(fd, size)
        if actual and first_read[0]:
            first_read[0] = False
            observed_bytes[0] += len(actual)  # explicit observation loss: no original journal claim
            raise primary
        return actual
    error, _, restores = capture_patches(
        [(builder.subprocess, "Popen", multi_creator),
         (builder.selectors, "DefaultSelector", closing_selector),
         (builder.os, "read", panic_read)],
        lambda: builder.run_job([str(builder.GCC), "--version"], out, state, "K07"))
    proc = created[-1]
    selected = selectors[-1]
    refs = [item for item in builder._FILE_HOLDERS
            if item["object"] is selected or item["object"] is proc.stdout or item["object"] is proc.stderr]
    results.append({"case": "K07_actual_primary_all_close_cancel_objects", "pass":
                    all(contains_original(error, item) for item in
                        (primary, selector_cancel, stdout_cancel, stderr_cancel)) and not restores
                    and selected.close_calls == 1 and proc.stdout.close_calls == 1 and proc.stderr.close_calls == 1
                    and proc.stdout.actual.closed and proc.stderr.actual.closed and proc.returncode is not None
                    and len(refs) == 3 and all(item["state"] == "UNKNOWN" for item in refs),
                    "discarded_after_real_read_observation_bytes": observed_bytes[0],
                    "no_complete_compiler_stdout_claim": True})

    source_after = {name: builder.file_identity(HERE / name) for name in SOURCES}
    gcc_after = builder.file_identity(builder.GCC)
    unchanged = source_before == source_after and gcc_before == gcc_after
    summary = {"profile": "ordinary_builder_owned_resources_only", "results": results,
               "passed": all(item["pass"] for item in results) and unchanged,
               "actual_created_GCC_processes": len(created),
               "actual_job_records": state["jobs"], "source_and_GCC_before_after_exact": unchanged,
               "combined_log_bytes": state["log_bytes"], "job_limit_seconds": 120,
               "retained_unknown_file_objects": len(builder._FILE_HOLDERS),
               "retained_compiler_holders": len(builder._COMPILER_HOLDERS),
               "bridge_imports": 0, "native_birth_factory": 0, "ROOTexec": 0,
               "originalSUT": 0, "native14": "NOTRUN", "family_qualification": False}
    builder.save_json(out / "ORDINARY-BUILDER-RESULT.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--static", action="store_true")
    group.add_argument("--owned-case", choices=tuple(CASES))
    group.add_argument("--builder-owned", action="store_true")
    parser.add_argument("--out", type=pathlib.Path)
    args = parser.parse_args()
    if args.builder_owned:
        if args.out is None:
            parser.error("--builder-owned requires an absent absolute --out")
        result = run_builder_owned_controls(args.out)
    else:
        result = run_owned_controls(args.owned_case) if args.owned_case else run_static_controls()
    print(json.dumps(result, sort_keys=True))
    return 0 if (result.get("passed", False) or
                 result.get("status") == "LOCAL_NATIVE_CLOSED") else 1


if __name__ == "__main__":
    raise SystemExit(main())
