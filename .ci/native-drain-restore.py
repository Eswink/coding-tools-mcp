import base64,hashlib,json,lzma,os,pathlib,subprocess
base='2c5d133eaa75d7fc084b8122350d7768ce5b2382'
expected='d61d5c21e2c5e7cb4dea0c401b72653f694a9bbd'
p=pathlib.Path('evidence');p.mkdir(exist_ok=True)
encoded=''.join(pathlib.Path(f'.ci/issue81-drain-part{i:02d}.txt').read_text(encoding='utf-8') for i in range(15))
assert len(encoded)==122624
patch=lzma.decompress(base64.b64decode(encoded,validate=True))
assert len(patch)==517365 and hashlib.sha256(patch).hexdigest()=='fbc4362f60aede50eb9418ed65134383fdd4b092689aaf71f6bca16481b5d4e3'
(p/'input.patch').write_bytes(patch)
rows=subprocess.check_output(['git','apply','--numstat','-z',str(p/'input.patch')]).split(b'\0')
paths=[row.split(b'\t',2)[2].decode('utf-8') for row in rows if row]
assert len(paths)==95 and len(set(paths))==95
assert all(not pathlib.PurePosixPath(v).is_absolute() and '..' not in pathlib.PurePosixPath(v).parts and v.startswith(('services/','src-tauri/','tools/','docs/','.github/workflows/','tests/delivery/')) for v in paths)
subprocess.run(['git','apply','--check',str(p/'input.patch')],check=True)
subprocess.run(['git','apply',str(p/'input.patch')],check=True)
env={**os.environ,'GIT_INDEX_FILE':str((p/'candidate.index').resolve())}
subprocess.run(['git','read-tree',base],env=env,check=True)
subprocess.run(['git','add','--',*paths],env=env,check=True)
tree=subprocess.check_output(['git','write-tree'],env=env,text=True).strip()
assert tree==expected,(tree,expected)
# A local validation-only commit makes source-sensitive tests inspect
# the compiled product tree. This never creates or moves remote refs.
env.update(GIT_AUTHOR_NAME='CI source verifier',GIT_AUTHOR_EMAIL='ci@users.noreply.github.com',GIT_COMMITTER_NAME='CI source verifier',GIT_COMMITTER_EMAIL='ci@users.noreply.github.com',GIT_AUTHOR_DATE='2026-09-30T00:00:00+00:00',GIT_COMMITTER_DATE='2026-09-30T00:00:00+00:00')
commit=subprocess.check_output(['git','commit-tree',tree,'-p',base,'-m','Synthetic validation checkout for Issue81 native drain; product tree only'],env=env,text=True).strip()
subprocess.run(['git','reset','--hard',commit],check=True)
(p/'candidate.index').unlink(missing_ok=True)
files={}
for path in paths:
    data=pathlib.Path(path).read_bytes()
    mode=subprocess.check_output(['git','ls-files','--stage','--',path],text=True).split()[0]
    files[path]={'sha256':hashlib.sha256(data).hexdigest(),'git_blob':hashlib.sha1(f'blob {len(data)}\0'.encode()+data).hexdigest(),'mode':mode}
    target=p/'source'/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
(p/'source.json').write_text(json.dumps({'baseline':base,'candidate_tree':tree,'validation_commit':commit,'workflow_sha':os.environ['GITHUB_SHA'],'local_source_commit':'97472a4cb4c5597f11af89ab08051d3ca59399b8','files':files},indent=2),encoding='utf-8')
print('VERIFIED_PRODUCT_TREE='+tree)
