from pathlib import Path
import hashlib,json,types,tempfile,os,stat
D=Path('/workspace/work/rc070/rsa-gateway-build-owned04');p=D/'build-root-once04.py';b=p.read_bytes();assert hashlib.sha256(b).hexdigest()=='d95985a9d56d8d6dc00855fd2d4a6ea9fa654fb52cba3e7ede253b368d6cf374';m=types.ModuleType('actual_wrapper04_ordinary');m.__file__=str(p);exec(compile(b,str(p),'exec'),m.__dict__)
results=[]
def good(name,fn):fn();results.append({'name':name,'result':'PASS'})
def bad(name,fn):
 try:fn()
 except Exception:results.append({'name':name,'result':'PASS_REJECTED'})
 else:raise AssertionError('unexpected_acceptance:'+name)
def row(p):
 s=p.lstat();v={'path':str(p),'kind':'symlink' if p.is_symlink() else 'regular','mode':f'{stat.S_IMODE(s.st_mode):04o}','dev':s.st_dev,'inode':s.st_ino,'nlink':s.st_nlink,'mtimeNs':s.st_mtime_ns,'ctimeNs':s.st_ctime_ns}
 if p.is_symlink():v.update(linkTarget=os.readlink(p),resolved=str(p.resolve(strict=True)))
 else:v.update(bytes=s.st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
 return v
with tempfile.TemporaryDirectory(prefix='input-controls04-',dir=D) as td:
 t=Path(td);f=t/'source';f.write_bytes(b'exact-source-input');f.chmod(0o600);r=row(f);good('actual_regular_identity',lambda:m.check_row(r));f.write_bytes(b'different-source');bad('byte_or_physical_mutation',lambda:m.check_row(r));r=row(f);f.chmod(0o644);bad('mode_mutation',lambda:m.check_row(r));r=row(f);os.link(f,t/'hardlink');bad('nlink_mutation',lambda:m.check_row(r));a=t/'alias';a.symlink_to('source');r=row(a);good('exact_symlink_identity',lambda:m.check_row(r));a.unlink();a.symlink_to('hardlink');bad('literal_link_mutation',lambda:m.check_row(r))
 j=t/'report.json';j.write_text('{"value": 1}');good('strict_complete_json',lambda:m.read_json(j));j.write_text('{"value":1,"value":2}');bad('duplicate_json_key',lambda:m.read_json(j));j.write_text('{"value":NaN}');bad('nan_json',lambda:m.read_json(j));j.write_text('{"value":1e999}');bad('overflow_nonfinite_json',lambda:m.read_json(j))
r={'scope':'ORDINARY_ACTUAL_HELPER_TEMP_INPUT_AND_SCHEMA_ONLY','rootHelperSHA256':hashlib.sha256(b).hexdigest(),'controls':results,'actualPassed':len(results),'compilerExecutions':0,'CargoExecutions':0,'buildFinishedProof':False};out=D/'ORDINARY-INPUT-CONTROLS04.safe.json'
with out.open('x') as f:json.dump(r,f,indent=2);f.write('\n')
out.chmod(0o600);print(json.dumps(r))
