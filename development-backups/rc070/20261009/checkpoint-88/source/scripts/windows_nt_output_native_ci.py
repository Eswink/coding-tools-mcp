"""Source-only draft of fixed NT ordinary-controls management.

Execution activation remains disabled. Native results are evidence, never grants.
Original guard AST is retained; its run_git is explicitly rebound, not executed.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import ctypes
import importlib.util
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import time
import urllib.request
import zipfile

import windows_nt_output_native_job as job

RESOURCE_QUARANTINE = []
NATIVE_SOURCE_ACTIVATED = False  # A separate reviewed meaningful head must change this.


def load_native_lease(path):
    data = strict_native_json(Path(path).read_text(encoding="utf-8"))
    source, go, budgets = data["native_source"], data["go"], data["budgets"]
    if data["schema"] != 1 or data["repository"] != "Eswink/coding-tools-mcp":
        raise ValueError("wrong fixed native lease")
    expected = ("19bb292004e0fd4ed02374b35bcd2f22469779f0", 1953,
        "d86ece313011780ae408092bc2d1e37b05373e75", 1954,
        "8625c6117b3840db9f67565cac1bc3ef1fff4464", 13563,
        "048c82289482e11ece77c8dd6c74f9df33ad897785a140cb0fe0692ad5c38200")
    actual = tuple(source[k] for k in ("pure_original_tree", "pure_original_count",
        "prospective_native_sut_tree", "prospective_native_sut_count", "overlay_source_commit",
        "overlay_bytes", "overlay_sha256"))
    if actual != expected or go != {"version": "go1.24.13",
            "url": "https://go.dev/dl/go1.24.13.windows-amd64.zip", "bytes": 87295983,
            "sha256": "40b16bc8f00540a2cb02dff4de72b73e966fdd8d65f95e33d8e4080b48a2459a"}:
        raise ValueError("source/runtime lease drift")
    if any(type(v) is not int or v <= 0 for v in budgets.values()):
        raise ValueError("typed finite budgets required")
    if budgets != {"overall_seconds":2700,"source_seconds":300,"acquisition_seconds":300,
            "extraction_seconds":120,"compile_seconds":600,"ordinary_native_seconds":120,
            "discovery_seconds":60,"go_native_seconds":600,"go_test_timeout_seconds":540,
            "after_seconds":60,"grace_seconds":7,"force_seconds":2,"io_close_seconds":2,
            "root_stage_count":20,"git_helper_count":320,"git_combined_raw_bytes":16777216,
            "per_channel_bytes":2097152}:
        raise ValueError("fixed caps differ")
    entry = data["selected_entry"]
    names, subs = entry["top_level_names"], entry["required_subtests"]
    if len(names) != 21 or len(set(names)) != 21 or len(subs) != 4 or len(set(subs)) != 4:
        raise ValueError("fixed named native selection differs")
    if any(not n.startswith("TestGuestNative") for n in names):
        raise ValueError("non-native selected method")
    return data


def snapshot_runtime_file(path, deadline, single_link=True):
    path = Path(path)
    errors = []; stream = None; result = None
    try:
        before = path.lstat()
        if (not stat.S_ISREG(before.st_mode) or path.is_symlink() or
                getattr(before,"st_file_attributes",0)&0x400 or
                (single_link and before.st_nlink != 1)):
            raise ValueError("runtime file type/link/reparse rejected")
        stream = path.open("rb"); opened = os.fstat(stream.fileno())
        identity = (before.st_dev,before.st_ino,before.st_size,before.st_nlink)
        if identity != (opened.st_dev,opened.st_ino,opened.st_size,opened.st_nlink):
            raise ValueError("runtime path differs from actual opened FD")
        count = 0; digest = hashlib.sha256()
        while True:
            if time.monotonic() >= deadline: raise TimeoutError("runtime fence deadline")
            chunk = stream.read(65536)
            if not chunk: break
            count += len(chunk); digest.update(chunk)
        after_fd = os.fstat(stream.fileno()); after_path = path.lstat()
        if count != before.st_size or any(identity != (v.st_dev,v.st_ino,v.st_size,v.st_nlink)
                or v.st_mtime_ns != before.st_mtime_ns for v in (after_fd,after_path)):
            raise ValueError("runtime file changed while reading actual FD")
        result = {"path":str(path),"bytes":count,"sha256":digest.hexdigest(),
            "device":opened.st_dev,"file_id":opened.st_ino,"links":opened.st_nlink,
            "mode":stat.S_IMODE(opened.st_mode),"native_authority":False}
    except BaseException as error: errors.append(error)
    finally:
        if stream is not None:
            try: stream.close()
            except BaseException as error: RESOURCE_QUARANTINE.append(stream); errors.append(error)
        job.raise_preserved_native_errors(errors)
    return result


def snapshot_runtime_tree(root, deadline, expected=None):
    root = Path(root)
    if root.is_symlink() or not root.is_dir(): raise ValueError("runtime root not a real directory")
    rows = []
    for path in sorted(root.rglob("*")):
        if time.monotonic() >= deadline: raise TimeoutError("complete runtime fence deadline")
        info = path.lstat()
        if path.is_symlink() or getattr(info,"st_file_attributes",0)&0x400:
            raise ValueError("runtime directory reparse denied")
        if stat.S_ISDIR(info.st_mode): continue
        row = snapshot_runtime_file(path,deadline)
        row["path"] = path.relative_to(root).as_posix(); rows.append(row)
    if not rows or (expected is not None and rows != expected):
        raise ValueError("complete runtime tree empty or changed")
    return rows


def module_filename_from_api(api, module_handle):
    # The actual already-loaded WinDLL handle is an observation, never a grant.
    if type(module_handle) is not int or module_handle <= 0:
        raise ValueError("actual existing module handle required")
    for capacity in (256,512,1024,2048,4096,8192,16384,32768):
        buffer = ctypes.create_unicode_buffer(capacity)
        ctypes.set_last_error(0)
        length = api.GetModuleFileNameW(module_handle,buffer,capacity)
        error = ctypes.get_last_error()
        if type(length) is not int or length <= 0:
            raise OSError(error,"GetModuleFileNameW failed")
        if length >= capacity or error == 122: continue
        if error or length != len(buffer.value) or not Path(buffer.value).is_absolute():
            raise ValueError("module path error/truncation/nonabsolute observation")
        return buffer.value
    raise ValueError("bounded module path buffer exhausted")


def loaded_native_dll_snapshot(manager, deadline, expected=None):
    _, api = job.load_original_native_api(manager)
    rows = []
    for name,dll in (("kernel32",api.kernel),("advapi32",api.adv)):
        actual = snapshot_runtime_file(module_filename_from_api(api,dll._handle),deadline,
            single_link=False)  # System DLLs may have WinSxS hardlinks; not owned files.
        actual["loaded_api_module"] = name; rows.append(actual)
    if expected is not None and rows != expected: raise ValueError("loaded API DLL identity changed")
    return {"observed_loaded_api_dlls":rows,"other_loaded_modules":"UNVERIFIED",
        "transitive_system_dependencies":"UNVERIFIED","full_OS_verified":False,
        "native_authority":False}


def parse_ordinary_native_records(raw):
    names = ["creation-job-list-two-channels","delayed-pending-read-eof",
        "binary-overlapped-stdin-eof","pending-read-cancel-completed-still-denied",
        "real-protected-close-unknown-retained","actual-descendant-held-writer-rejected",
        "real-created-job-contained-delegate-cancel-denied"]
    lines = raw.decode("utf-8","strict").splitlines()
    if len(lines) != 1: raise ValueError("ordinary native receipt is not one complete record")
    value = strict_native_json(lines[0]); rows = value.get("records")
    if (type(value.get("count")) is not int or value["count"] != len(names)
            or value.get("native_authority") is not False or type(value.get("original_Go_methods")) is not int
            or value["original_Go_methods"] != 0
            or type(rows) is not list or [r.get("name") for r in rows] != names
            or any(r.get("action") != "pass" for r in rows)):
        raise ValueError("current exact ordinary native vector missing/rejected")
    return value


def parse_native_discovery(raw, entry):
    lines = raw.decode("utf-8","strict").splitlines()
    names = [line for line in lines if line.startswith("Test")]
    if names != entry["top_level_names"] or len(lines) != len(names)+1:
        raise ValueError("actual Go discovery differs from fixed source selection")
    if not re.fullmatch(r"ok\s+\S+\s+\S+",lines[-1]):
        raise ValueError("missing actual Go discovery package terminal")
    return {"actual_discovered_top_names":names,"subtests":"NOT_DISCOVERED_BY_GO_LIST",
        "raw_sha256":hashlib.sha256(raw).hexdigest(),"native_authority":False}


def restore_augmented_source(guard, manager, destination, manifest, lease):
    original = guard.restore_source(manager,destination,manifest)
    source = lease["native_source"]
    guard.run_git(manager,"fetch","--no-tags",guard.REPOSITORY,source["overlay_source_commit"])
    data = guard.run_git(manager,"show",source["overlay_source_commit"]+":"+source["overlay_backup_path"])
    row = {"path":source["overlay_sut_path"],"bytes":source["overlay_bytes"],
        "sha256":source["overlay_sha256"],"blob":source["overlay_blob"]}
    guard.check_blob(data,row)
    blob = guard.run_git(destination,"hash-object","-w","--stdin",data=data).decode().strip()
    if blob != row["blob"]: raise ValueError("actual native overlay blob differs")
    guard.run_git(destination,"update-index","--add","--cacheinfo",
        source["overlay_mode"]+","+blob+","+row["path"],index=True)
    guard.run_git(destination,"checkout-index","--all","--force",index=True)
    return {"original_1953_restoration":original,
        "augmented":verify_augmented_source(guard,destination,manifest,lease)}


def verify_management_native(guard, manager, lease, expected=None):
    # The future root-reviewed actual head is observed here; context is not a grant.
    head = guard.run_git(manager,"rev-parse","HEAD").decode().strip()
    if not re.fullmatch("[0-9a-f]{40}",head) or head != os.environ.get("GITHUB_SHA"):
        raise ValueError("actual manager head differs from reviewed CI context")
    original = guard.verify_manager(manager)
    rows = []
    paths = [*lease["management_source_paths"],"scripts/Windows非提升进程v12.py"]
    for path in sorted(paths):
        raw = guard.run_git(manager,"ls-tree","-z",head,"--",path)
        entries = [v for v in raw.split(b"\0") if v]
        if len(entries) != 1: raise ValueError("actual manager source absent from immutable head")
        header,name = entries[0].split(b"\t",1); mode,kind,blob = header.decode().split()
        if mode != "100644" or kind != "blob" or name.decode() != path:
            raise ValueError("manager actual native mode/blob/type differs")
        data = guard.run_git(manager,"show",head+":"+path)
        row = {"path":path,"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest(),"blob":blob,"mode":mode}
        guard.check_blob((manager/path).read_bytes(),row); rows.append(row)
    result = {"original_seven":original,"new_six_and_v12":rows,"actual_head":head}
    if expected is not None and result != expected: raise ValueError("management source/ref changed")
    return result


def verify_augmented_source(guard, repository, manifest, lease):
    source = lease["native_source"]
    row = {"path": source["overlay_sut_path"], "mode": source["overlay_mode"],
        "blob": source["overlay_blob"], "bytes": source["overlay_bytes"], "sha256": source["overlay_sha256"]}
    rows = sorted([*manifest["whole_source"], row], key=lambda r: r["path"])
    if len({r["path"] for r in rows}) != 1954:
        raise ValueError("duplicate/missing candidate source")
    if guard.run_git(repository, "rev-parse", "HEAD").decode().strip() != guard.BASE:
        raise ValueError("SUT base mismatch")
    tree = guard.run_git(repository, "write-tree", index=True).decode().strip()
    if tree != source["prospective_native_sut_tree"]:
        raise ValueError("actual native candidate index mismatch")
    if guard.tree_rows(repository, tree) != [{k: r[k] for k in ("path", "mode", "blob")} for r in rows]:
        raise ValueError("actual native candidate tree rows differ")
    identities = []
    for row in rows:
        path = repository / guard.safe_path(row["path"])
        for parent in [path, *path.parents]:
            if parent == repository.parent: break
            info = parent.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError("source reparse/symlink denied")
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("source nonregular/hardlinked file denied")
        guard.check_blob(path.read_bytes(), row)
        identities.append({"path": row["path"], "mode": row["mode"], "sha256": row["sha256"],
            "device": info.st_dev, "file_id": info.st_ino, "links": info.st_nlink, "bytes": info.st_size})
    if any(guard.run_git(repository, "ls-files", "--others", "--exclude-standard", "-z", index=True).split(b"\0")):
        raise ValueError("unexpected physical source")
    if (repository / "src-tauri/src/tools/cloud_host/windows_workspace/stage.rs").exists():
        raise ValueError("blocked Stage11 present")
    return {"tree": tree, "paths": identities, "native_authority": False,
        "snapshot_assumption": "trusted disposable host; not atomic filesystem ownership grant"}


def verify_go_runtime(root, expected=None):
    root = Path(root)
    rows = []
    for path in sorted(root.rglob("*")):
        info = path.lstat()
        if path.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("runtime reparse/symlink denied")
        if path.is_dir(): continue
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("runtime nonregular/hardlink denied")
        b = path.read_bytes()
        rows.append({"path": path.relative_to(root).as_posix(), "bytes": len(b),
            "sha256": hashlib.sha256(b).hexdigest(), "device": info.st_dev,
            "file_id": info.st_ino, "links": info.st_nlink})
    if not rows: raise ValueError("empty runtime inventory")
    if expected is not None and rows != expected: raise ValueError("complete runtime drift")
    return rows


def acquire_fixed_go_zip(lease, destination, deadline):
    if Path(destination).exists(): raise ValueError("fresh archive path required")
    errors = []; response = stream = None; count = 0; digest = hashlib.sha256()
    try:
        response = urllib.request.urlopen(lease["go"]["url"], timeout=min(30, max(.001, deadline-time.monotonic())))
        if response.geturl() not in (lease["go"]["url"], "https://dl.google.com/go/go1.24.13.windows-amd64.zip"):
            raise ValueError("unexpected archive redirect")
        stream = Path(destination).open("xb")
        while True:
            if time.monotonic() >= deadline: raise TimeoutError("fixed acquisition deadline")
            chunk = response.read(65536)
            if not chunk: break
            count += len(chunk)
            if count > lease["go"]["bytes"]: raise ValueError("archive body exceeds exact size")
            stream.write(chunk); digest.update(chunk)
        if count != lease["go"]["bytes"] or digest.hexdigest() != lease["go"]["sha256"]:
            raise ValueError("official archive size/digest mismatch")
    except BaseException as error: errors.append(error)
    finally:
        for resource in (stream, response):
            if resource is None: continue
            try: resource.close()
            except BaseException as error:
                RESOURCE_QUARANTINE.append(resource); errors.append(error)
        job.raise_preserved_native_errors(errors)
    return {"bytes": count, "sha256": digest.hexdigest()}


def extract_verified_go_zip(archive, destination, deadline):
    destination = Path(destination)
    if destination.exists(): raise ValueError("fresh runtime extraction required")
    errors = []; z = None; inventory = []; folded = set()
    try:
        z = zipfile.ZipFile(archive)
        for entry in z.infolist():
            name = entry.filename.rstrip("/"); p = PurePosixPath(name)
            if not name or "\\" in name or p.is_absolute() or str(p) != name:
                raise ValueError("unsafe archive path")
            if any(part in (".", "..") or ":" in part or part.rstrip(" .") != part or
                   part.split(".")[0].casefold() in ("con", "prn", "aux", "nul", *("com"+str(i) for i in range(1,10)), *("lpt"+str(i) for i in range(1,10)))
                   for part in p.parts): raise ValueError("Windows archive alias/traversal")
            folded_name = name.casefold()
            if folded_name in folded: raise ValueError("archive case collision")
            folded.add(folded_name)
            mode = entry.external_attr >> 16
            if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
                raise ValueError("archive link/nonregular entry")
        destination.mkdir()
        for entry in z.infolist():
            if time.monotonic() >= deadline: raise TimeoutError("fixed extraction deadline")
            path = destination / entry.filename
            if entry.is_dir(): path.mkdir(parents=True, exist_ok=True); continue
            path.parent.mkdir(parents=True, exist_ok=True)
            data = z.read(entry)
            if len(data) != entry.file_size: raise ValueError("archive decompressed byte mismatch")
            path.write_bytes(data)
            inventory.append({"path": entry.filename, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        actual = verify_go_runtime(destination)
        if [{k:r[k] for k in ("path","bytes","sha256")} for r in actual] != sorted(inventory, key=lambda r:r["path"]):
            raise ValueError("complete extracted runtime differs from verified ZIP")
    except BaseException as error: errors.append(error)
    finally:
        if z is not None:
            try: z.close()
            except BaseException as error: RESOURCE_QUARANTINE.append(z); errors.append(error)
        job.raise_preserved_native_errors(errors)
    return actual


def bounded_run_git_delegate(manager, output, git_executable, deadline, counter, repo,
                             *args, index=False, data=None):
    counter["calls"] += 1
    if counter["calls"] > 320: raise RuntimeError("native Git helper count exceeded")
    if shutil.which("git") != str(git_executable): raise ValueError("fenced original Git resolver changed")
    env = dict(os.environ)
    for key in list(env):
        if key.startswith("GIT_"): env.pop(key)
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_NO_REPLACE_OBJECTS="1")
    if index: env["GIT_INDEX_FILE"] = str(repo / ".git" / "foundation-candidate.index")
    raw_path = output / ("git-%03d" % counter["calls"])
    errors = []; actual = None
    try:
        actual = job.native_collect_stage(manager, git_executable,
            ["-c","core.autocrlf=false","-c","core.hooksPath="+os.devnull,"-C",str(repo),*args],
            env, repo, deadline, raw_path, input_data=data, require_zero=False,
            overall_deadline=counter["overall_deadline"])
    except BaseException as error: errors.append(error)
    finally:
        try:
            counter["raw_bytes"] += sum(p.stat().st_size for p in
                (raw_path/"stdout.raw",raw_path/"stderr.raw") if p.exists())
            if counter["raw_bytes"] > 16777216:
                raise RuntimeError("combined source helper raw overflow")
        except BaseException as error: errors.append(error)
        job.raise_preserved_native_errors(errors)
    if actual["actual_root_exit"]:
        raise RuntimeError("git "+args[0]+" failed: "+actual["stderr"].decode("utf-8","replace")[:4096])
    return actual["stdout"]


def strict_native_json(text):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result: raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    def constant(value):
        raise ValueError("nonfinite JSON number: "+value)
    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


@contextmanager
def bind_source_git_delegate(guard, delegate):
    if getattr(guard, "_nt_bound", False): raise ValueError("unexpected/concurrent original binding")
    original = guard.run_git; errors = []
    guard._nt_bound = True
    try:
        guard.run_git = delegate
        yield {"original_run_git": "RETAINED_NOT_EXECUTED", "higher_ast": "ORIGINAL_WITH_NEW_DELEGATE_BINDING"}
    except BaseException as error: errors.append(error)
    finally:
        try:
            guard.run_git = original; guard._nt_bound = False
            if guard.run_git is not original: raise RuntimeError("original function object not restored")
        except BaseException as error: errors.append(error)
        job.raise_preserved_native_errors(errors)


def parse_native_vector(raw, entry, package=None):
    top, subs = entry["top_level_names"], entry["required_subtests"]
    selected = set(top) | set(subs); run = []; passed = []; failures = []; skips = []; terminal = []
    package_start = package_pass = 0
    for line in raw.decode("utf-8","strict").splitlines():
        if not line: raise ValueError("empty Go JSON record")
        event = strict_native_json(line)
        if not isinstance(event,dict) or type(event.get("Action")) is not str: raise ValueError("malformed Go event")
        if set(event) - {"Time","Action","Package","Test","Elapsed","Output"}:
            raise ValueError("unknown Go event field")
        if any(type(event[k]) is not str for k in ("Time","Package","Test","Output") if k in event):
            raise ValueError("untyped Go string field")
        if "Elapsed" in event and (type(event["Elapsed"]) not in (int,float) or
                not math.isfinite(event["Elapsed"]) or event["Elapsed"] < 0):
            raise ValueError("invalid Go elapsed field")
        if package is None: package = event.get("Package")
        if not package or event.get("Package") != package: raise ValueError("foreign/unknown Go package")
        action, name = event["Action"], event.get("Test")
        if package_pass: raise ValueError("event after package terminal")
        if not name:
            if action == "start":
                if package_start or run: raise ValueError("duplicate/late package start")
                package_start += 1
            elif action == "pass":
                if package_start != 1 or set(terminal) != selected or failures or skips:
                    raise ValueError("early package success")
                package_pass += 1
            elif action == "fail": failures.append("PACKAGE")
            elif action != "output": raise ValueError("unexpected package action")
            continue
        if package_start != 1: raise ValueError("named event before package start")
        if name not in selected: raise ValueError("unexpected actual named Go test")
        if action == "run":
            if name in run: raise ValueError("duplicate actual run")
            if "/" in name and (name.split("/",1)[0] not in run or name.split("/",1)[0] in terminal):
                raise ValueError("subtest outside actual live parent")
            run.append(name)
        elif action in ("pass","fail","skip"):
            if name not in run or name in terminal: raise ValueError("missing/duplicate actual terminal")
            terminal.append(name)
            {"pass":passed,"fail":failures,"skip":skips}[action].append(name)
            if "/" not in name and any(s.startswith(name+"/") and s not in terminal for s in subs):
                raise ValueError("parent terminal before required subtest")
        elif action == "output":
            if name not in run or name in terminal: raise ValueError("output outside actual named execution")
        else: raise ValueError("unexpected named test action")
    if package_start != 1 or package_pass != 1 or failures or skips or set(run) != selected or set(passed) != selected:
        raise ValueError("current exact native Go vector incomplete/rejected")
    return {"package":package,"loaded_names":sorted(selected),"executed_names":run,"success_names":passed,
        "failures":failures,"skips":skips,"raw_sha256":hashlib.sha256(raw).hexdigest(),"native_authority":False}


def invoke_native_controls(manager, runtime_python, env, deadline, output):
    if sys.platform != "win32": raise RuntimeError("ordinary native controls require real Windows")
    # Fixed current-source controls must be implemented/frozen before activation.
    return job.native_collect_stage(manager, runtime_python,
        ["-B",str(manager/"scripts/windows_nt_output_native_controls.py"),"--all"],
        env,manager,deadline,output)


def write_native_receipt(path, value):
    if Path(path).exists(): raise ValueError("terminal receipt already exists")
    Path(path).write_text(json.dumps(value,sort_keys=True,indent=2)+"\n",encoding="utf-8")


def execute_native_manager(manager, lease, output):
    # This composed entry is source-only until three distinct activation guards
    # are reviewed. It does not create any VM/RunBinding/issuer capability.
    if not NATIVE_SOURCE_ACTIVATED or lease["native_activation"] != "ROOT_REVIEWED_ACTIVATION":
        raise RuntimeError("native source activation DISABLED")
    if sys.platform != "win32" or sys.version_info[:2] != (3,12) or not sys.dont_write_bytecode:
        raise RuntimeError("exact actual Windows Python3.12 -B required")
    if (os.environ.get("GITHUB_ACTIONS"),os.environ.get("GITHUB_REPOSITORY"),
            os.environ.get("RUNNER_ENVIRONMENT")) != ("true","Eswink/coding-tools-mcp","github-hosted"):
        raise RuntimeError("disposable named CI purpose context required; context is not authority")
    manager,output = Path(manager),Path(output)
    output.mkdir(parents=False,exist_ok=False)
    budgets = lease["budgets"]; overall = time.monotonic()+budgets["overall_seconds"]
    errors=[]; report={"passed":False,"scope":"CURRENT_ORDINARY_NT_API_CONTROL_ONLY",
        "native_authority":False,"VM_boot_owner":"NOT_PROVEN","RC_qualification":False,
        "all_descendant_exit_codes":"UNKNOWN","other_OS_dependencies":"UNVERIFIED"}
    counter={"calls":0,"raw_bytes":0,"overall_deadline":overall}; stages=[]
    git_name = shutil.which("git")
    if not git_name: raise RuntimeError("actual original native Git unavailable")
    git = Path(git_name).resolve(strict=True)
    guard_path = manager/"scripts/windows_foundation_source_guard.py"
    manifest_path = manager/"scripts/windows_foundation_source_manifest.json"
    for path,key in ((guard_path,"source_guard_sha256"),(manifest_path,"source_manifest_sha256")):
        if hashlib.sha256(path.read_bytes()).hexdigest() != lease[key]:
            raise ValueError("immutable original guard/manifest bytes changed")
    spec=importlib.util.spec_from_file_location("_current_immutable_nt_source_guard",guard_path)
    guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
    manifest=guard.load_manifest(manifest_path)
    original_binding=guard.run_git
    source=output/"pure-sut"; archive=output/"official-go.zip"; go_root=output/"official-go"
    env=dict(os.environ);env.update(lease["selected_entry"]["environment"])
    env.update(PYTHONDONTWRITEBYTECODE="1",GOCACHE=str(output/"go-cache"),
        GOTMPDIR=str(output/"go-tmp"))
    Path(env["GOTMPDIR"]).mkdir()
    source_before=management_before=python_before=git_before=dll_before=go_before=None
    phase_deadline=min(overall,time.monotonic()+budgets["source_seconds"])
    delegate=lambda repo,*args,**kw:bounded_run_git_delegate(manager,output/"git-raw",git,
        phase_deadline,counter,repo,*args,**kw)
    try:
        python_before=snapshot_runtime_tree(Path(sys.base_prefix),phase_deadline)
        git_before=snapshot_runtime_tree(git.parent.parent,phase_deadline)
        report["python_actual_executable"]=snapshot_runtime_file(Path(sys.executable),phase_deadline)
        report["git_actual_executable"]=snapshot_runtime_file(git,phase_deadline)
        dll_before=loaded_native_dll_snapshot(manager,phase_deadline)
        with bind_source_git_delegate(guard,delegate):
            management_before=verify_management_native(guard,manager,lease)
            report["restore"]=restore_augmented_source(guard,manager,source,manifest,lease)
            source_before=report["restore"]["augmented"]
        acquisition_deadline=min(overall,time.monotonic()+budgets["acquisition_seconds"])
        report["archive"]=acquire_fixed_go_zip(lease,archive,acquisition_deadline)
        extraction_deadline=min(overall,time.monotonic()+budgets["extraction_seconds"])
        # Check the same fixed archived bytes again before extraction.
        archive_identity=snapshot_runtime_file(archive,extraction_deadline)
        if (archive_identity["bytes"],archive_identity["sha256"]) != (lease["go"]["bytes"],lease["go"]["sha256"]):
            raise ValueError("archive changed between acquisition and extraction")
        report["go_extraction"]=extract_verified_go_zip(archive,go_root,extraction_deadline)
        go_before=snapshot_runtime_tree(go_root,extraction_deadline)
        go=go_root/"go/bin/go.exe"
        if not go.is_file(): raise ValueError("verified official Go executable absent")
        cwd=source/lease["selected_entry"]["cwd"]
        # Each root stage is counted independently from bounded source helpers.
        stages.append("ordinary-native")
        ordinary=job.native_collect_stage(manager,Path(sys.executable),
            ["-B",str(manager/"scripts/windows_nt_output_native_controls.py"),"--all"],
            env,manager,min(overall,time.monotonic()+budgets["ordinary_native_seconds"]),
            output/"ordinary-native",overall_deadline=overall)
        report["ordinary_native"]=parse_ordinary_native_records(ordinary["stdout"])
        stages.append("go-compile")
        compiled=job.native_collect_stage(manager,go,["test","-c","-tags=guest","-o",str(output/"selected-native.exe"),"."],
            env,cwd,min(overall,time.monotonic()+budgets["compile_seconds"]),
            output/"go-compile",overall_deadline=overall)
        report["compiled_executable"]=snapshot_runtime_file(output/"selected-native.exe",overall)
        stages.append("go-discovery")
        discovery=job.native_collect_stage(manager,go,["test","-list",lease["selected_entry"]["run_regex"],"-tags=guest","."],
            env,cwd,min(overall,time.monotonic()+budgets["discovery_seconds"]),
            output/"go-discovery",overall_deadline=overall)
        report["discovery"]=parse_native_discovery(discovery["stdout"],lease["selected_entry"])
        stages.append("go-native-named")
        native=job.native_collect_stage(manager,go,["test","-json","-count=1","-tags=guest",
            "-timeout="+str(budgets["go_test_timeout_seconds"])+"s","-run",lease["selected_entry"]["run_regex"],"."],
            env,cwd,min(overall,time.monotonic()+budgets["go_native_seconds"]),
            output/"go-native-named",overall_deadline=overall)
        report["native_named"]=parse_native_vector(native["stdout"],lease["selected_entry"])
        report["managed_root_stages"]=stages
        if len(stages)>budgets["root_stage_count"]: raise RuntimeError("managed root stage budget exceeded")
    except BaseException as error: errors.append(error)
    finally:
        phase_deadline=min(overall,time.monotonic()+budgets["after_seconds"])
        # Every available source/runtime after-fence is attempted independently,
        # even if a primary/observer cancellation already exists.
        for name,before,check in [
            ("source",source_before,lambda:verify_augmented_source(guard,source,manifest,lease)),
            ("management",management_before,lambda:verify_management_native(guard,manager,lease,management_before)),
            ("python",python_before,lambda:snapshot_runtime_tree(Path(sys.base_prefix),phase_deadline,python_before)),
            ("git",git_before,lambda:snapshot_runtime_tree(git.parent.parent,phase_deadline,git_before)),
            ("loaded_api_dlls",dll_before,lambda:loaded_native_dll_snapshot(manager,phase_deadline,dll_before["observed_loaded_api_dlls"])),
            ("go",go_before,lambda:snapshot_runtime_tree(go_root,phase_deadline,go_before))]:
            if before is None:
                report[name+"_after"]="NOT_ADMITTED";continue
            try:
                if name in ("source","management"):
                    with bind_source_git_delegate(guard,delegate): actual=check()
                else: actual=check()
                if actual != before: raise ValueError(name+" actual after-fence differs")
                report[name+"_after"]="EXACT"
            except BaseException as error: errors.append(error);report[name+"_after"]="FAIL_OR_UNKNOWN"
        try:
            if guard.run_git is not original_binding: raise RuntimeError("original delegate binding not restored")
            if time.monotonic() >= overall: raise TimeoutError("overall2700s deadline")
            if any(report.get(n+"_after")!="EXACT" for n in ("source","management","python","git","loaded_api_dlls","go")):
                raise RuntimeError("complete after-admission unavailable")
        except BaseException as error: errors.append(error)
        report["source_git_counter"]={"calls":counter["calls"],"saved_raw_bytes":counter["raw_bytes"]}
        report["passed"]=not errors and "native_named" in report
        report["error_types"]=[type(e).__name__ for e in errors]
        try: write_native_receipt(output/"ACTUAL-NATIVE-OUTER-RECEIPT.json",report)
        except BaseException as error: errors.append(error)
        job.raise_preserved_native_errors(errors)
    return report


def native_ci_main():
    lease = load_native_lease(Path(__file__).with_name("windows_nt_output_native_inputs.json"))
    # Fail-only default until source/control/fixed-ref/activation startup review.
    if not NATIVE_SOURCE_ACTIVATED or lease["native_activation"] != "ROOT_REVIEWED_ACTIVATION":
        raise RuntimeError("native CI activation DISABLED; no native methods launched")
    manager=Path(__file__).resolve().parent.parent
    temporary=os.environ.get("RUNNER_TEMP")
    if not temporary: raise RuntimeError("actual disposable runner temporary directory unavailable")
    result=execute_native_manager(manager,lease,Path(temporary)/"windows-nt-output-native")
    print(json.dumps({"scope":result["scope"],"passed":result["passed"],"native_authority":False},sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(native_ci_main())
