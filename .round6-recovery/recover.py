"""Exact reviewed source transfer. Never writes a branch ref or executes source with a write token."""
import base64, hashlib, json, lzma, os, subprocess, sys, urllib.request
from pathlib import Path
BASE='ac816e0962a8211b071f63380777b7cef1124f87'
TREE='a8d88b79944f812c0bd0712ee62d96c4bb508ca7'
DIGEST='bfe6d1f4489aaa5a0c5283cf0b6cf58d5a437ce9a475fd7e950782444b86d99d'
REPO='Eswink/coding-tools-mcp'
ALLOWED=('services/cloud-gateway/','docs/specs/cloud-gateway-agent-runtime/','.github/workflows/cloud-gateway-channel.yml')
PROTECTED=('src','src-tauri','AGENTS.md','CLAUDE.md','package.json','package-lock.json','.agents','.claude')
def git(*args):
    return subprocess.check_output(['git',*args],text=True).strip()
def reconstruct(directory):
    assert git('rev-parse','HEAD')==BASE
    assert not git('status','--porcelain','--untracked-files=no')
    raw=b''.join((directory/f'part-{n}.bin').read_bytes() for n in range(4))
    assert len(raw)==22800 and hashlib.sha256(raw).hexdigest()==DIGEST
    patch=lzma.decompress(raw)
    assert len(patch)<1000000
    subprocess.run(['git','apply','--index','--whitespace=error-all','-'],input=patch,check=True)
    paths=git('diff','--cached','--name-only').splitlines()
    assert len(paths)==20 and all(p.startswith(ALLOWED) and '..' not in p.split('/') for p in paths)
    assert not git('diff','--cached','--diff-filter=D','--name-only')
    assert git('write-tree')==TREE
    env=dict(os.environ,GIT_AUTHOR_NAME='Source verification',GIT_AUTHOR_EMAIL='noreply@openai.com',GIT_COMMITTER_NAME='Source verification',GIT_COMMITTER_EMAIL='noreply@openai.com')
    made=subprocess.check_output(['git','commit-tree',TREE,'-p',BASE],input=b'Verified isolated round-6 source\n',env=env).decode().strip()
    subprocess.run(['git','checkout','--detach',made],check=True)
    for p in PROTECTED: assert git('rev-parse',BASE+':'+p)==git('rev-parse','HEAD:'+p),p
    print(json.dumps({'source_tree':TREE,'base':BASE,'protected_paths':'PASS'}))
def import_blobs(directory):
    assert git('rev-parse','HEAD^{tree}')==TREE
    token=os.environ['GH_TOKEN']
    def api(method,path,data=None):
        req=urllib.request.Request('https://api.github.com/repos/'+REPO+'/'+path,data=json.dumps(data).encode() if data is not None else None,headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','Content-Type':'application/json'},method=method)
        with urllib.request.urlopen(req,timeout=40) as response: return json.load(response)
    assert api('GET','git/ref/heads/feat/cloud-gateway-agent-runtime')['object']['sha']==BASE,'Remote changed: stop'
    paths=git('diff','--name-only',BASE,'HEAD').splitlines()
    assert len(paths)==20 and all(p.startswith(ALLOWED) for p in paths)
    entries=[]
    for path in paths:
        mode,kind,sha=git('ls-tree','HEAD','--',path).split('\t')[0].split()
        assert kind=='blob' and mode in ('100644','100755')
        data=subprocess.check_output(['git','cat-file','blob',sha])
        result=api('POST','git/blobs',{'content':base64.b64encode(data).decode(),'encoding':'base64'})
        assert result['sha']==sha,'Hash mismatch'
        entries.append(dict(path=path,mode=mode,type=kind,sha=sha))
    directory.mkdir(exist_ok=True)
    report=dict(base=BASE,source_tree=TREE,ref_modified=False,entries=entries)
    (directory/'import.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({'blobs_verified':len(entries),'source_tree':TREE,'ref_modified':False}))
if __name__=='__main__':
    mode=sys.argv[1];directory=Path(sys.argv[2])
    if mode=='reconstruct':reconstruct(directory)
    elif mode=='import':import_blobs(directory)
    else:raise SystemExit('Unsupported mode')
