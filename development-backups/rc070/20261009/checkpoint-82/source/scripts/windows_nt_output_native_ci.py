"""Source-only draft of fixed NT ordinary-controls management.

Execution activation remains disabled. Native results are evidence, never grants.
Original guard AST is retained; its run_git is explicitly rebound, not executed.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import importlib.util
import json
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


def load_native_lease(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
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
    if (budgets["overall_seconds"], budgets["git_helper_count"],
        budgets["git_combined_raw_bytes"], budgets["per_channel_bytes"]) != (2700, 320, 16777216, 2097152):
        raise ValueError("fixed caps differ")
    entry = data["selected_entry"]
    names, subs = entry["top_level_names"], entry["required_subtests"]
    if len(names) != 21 or len(set(names)) != 21 or len(subs) != 4 or len(set(subs)) != 4:
        raise ValueError("fixed named native selection differs")
    if any(not n.startswith("TestGuestNative") for n in names):
        raise ValueError("non-native selected method")
    return data


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
    actual = job.native_collect_stage(manager, git_executable,
        ["-c","core.autocrlf=false","-c","core.hooksPath="+os.devnull,"-C",str(repo),*args],
        env, repo, deadline, output / ("git-%03d" % counter["calls"]), input_data=data)
    counter["raw_bytes"] += len(actual["stdout"])+len(actual["stderr"])
    if counter["raw_bytes"] > 16777216: raise RuntimeError("combined source helper raw overflow")
    if actual["actual_root_exit"]:
        raise RuntimeError("git "+args[0]+" failed: "+actual["stderr"].decode("utf-8","replace")[:4096])
    return actual["stdout"]


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
        event = json.loads(line)
        if not isinstance(event,dict) or not isinstance(event.get("Action"),str): raise ValueError("malformed Go event")
        if package is None: package = event.get("Package")
        if not package or event.get("Package") != package: raise ValueError("foreign/unknown Go package")
        action, name = event["Action"], event.get("Test")
        if not name:
            if action == "start": package_start += 1
            elif action == "pass": package_pass += 1
            elif action == "fail": failures.append("PACKAGE")
            elif action != "output": raise ValueError("unexpected package action")
            continue
        if name not in selected: raise ValueError("unexpected actual named Go test")
        if action == "run":
            if name in run: raise ValueError("duplicate actual run")
            run.append(name)
        elif action in ("pass","fail","skip"):
            if name not in run or name in terminal: raise ValueError("missing/duplicate actual terminal")
            terminal.append(name)
            {"pass":passed,"fail":failures,"skip":skips}[action].append(name)
        elif action != "output": raise ValueError("unexpected named test action")
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


def native_ci_main():
    lease = load_native_lease(Path(__file__).with_name("windows_nt_output_native_inputs.json"))
    # Fail-only default until source/control/fixed-ref/activation startup review.
    if lease["native_activation"] != "ROOT_REVIEWED_ACTIVATION":
        raise RuntimeError("native CI activation DISABLED: incomplete source draft; no native methods launched")
    raise RuntimeError("composed orchestration not frozen; launch forbidden")


if __name__ == "__main__":
    native_ci_main()
