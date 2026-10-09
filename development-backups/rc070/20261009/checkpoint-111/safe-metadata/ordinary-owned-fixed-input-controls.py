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
controls=["actual-owned-POSIX-fixed74-layout-bytes-modes-and76-mocked-native-vectors"]
all_dirs=before["directories"]
for name in ("source","patch","destination"):
    duplicate=root/(name+"-negative");duplicate.mkdir(mode=0o700)
    for rel in sorted((p for p in all_dirs if p!="."),key=lambda p:(len(Path(p).parts),p)):(duplicate/rel).mkdir(mode=0o700)
    for row in before["files"]:
        data=ci.read_owned_bounded_file(payload/row["path"],time.monotonic()+30,167168,return_data=True)["data"]
        ci.write_owned_original_payload(duplicate/row["path"],data,time.monotonic()+30)
    assert ci.verify_owned_original_payloads(guard,duplicate,m,time.monotonic()+30)["actual_bytes"]==592919
    destination=root/(name+"-sut")
    if name=="destination":destination.mkdir(mode=0o700)
    else:
        bad=duplicate/("source/"+m["exact73"][0]["path"] if name=="source" else "FULL43-FROM-EXACT73.patch")
        data=bad.read_bytes();bad.write_bytes(bytes([data[0]^1])+data[1:])
    forbidden=[]
    guard.run_git=lambda *a,**k:(forbidden.append((a,k)),(_ for _ in ()).throw(AssertionError("negative reached native process")))[-1]
    try:
        try:guard.restore_source(manager,destination,m,local_payload=duplicate)
        except ValueError as error:
            if name=="source":assert "source SHA/size" in str(error)
            elif name=="patch":assert "patch SHA/size" in str(error)
            else:assert "destination already exists" in str(error)
        else:raise AssertionError("original fixed negative admitted")
    finally:guard.run_git=original
    assert not forbidden
    if name!="destination":assert not destination.exists()
    controls.append("actual-POSIX-original-local-"+name+"-preclone-rejection-zero-native")
assert ci.verify_owned_original_payloads(guard,payload,m,time.monotonic()+30)==before
extra=payload/"extra";ci.write_owned_original_payload(extra,b"extra",time.monotonic()+5)
try:ci.verify_owned_original_payloads(guard,payload,m,time.monotonic()+30)
except ValueError as error:assert "extra payload file" in str(error)
else:raise AssertionError("extra payload admitted")
extra.unlink();controls.append("actual-owned-input-extra-file-rejected-not-original-positive")
print(json.dumps({"controls":controls,"count":len(controls),"scope":"OWNED_POSIX_FIXED_INPUT_AND_MOCKED_NATIVE_ARGV_ONLY","actual_native_processes":0,"actual_Windows_API_calls":0,"actual_Go_processes":0,"original_local_positive":"NOTRUN","actual_official_Go_ZIP":"NOTRUN","source_roles":74,"directory_roles":31,"payload_bytes":592919,"all_four_fixture_bytes":2371676,"mocked_stage_requests":len(calls)},sort_keys=True))
