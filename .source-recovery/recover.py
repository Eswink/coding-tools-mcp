#!/usr/bin/env python3
"""One-shot reviewed blob import; tree/commit/ref writes require native connector."""
import argparse,base64,hashlib,json,lzma,os,subprocess,urllib.request
from pathlib import Path
BASE='ba9c379f08da37f2a05bb96c377a95f432da969e'
TARGET='5b55ba5eaaaea11d8c2322bbaa5980980cc8ad48'
TREE='92ea0acab1281db6feb85f02c14290235eabff3e'
DIGEST='536c414e8466f8acd21f4dd03f2bfe2f99c09b2eccb01a885f19e26c66b1c282'
REPO='Eswink/coding-tools-mcp'
ALLOWED=('services/cloud-gateway/','deploy/cloud-gateway/','tests/cloud-gateway-deployment/','docs/specs/cloud-gateway-agent-runtime/','.github/workflows/cloud-gateway-')
PROTECTED=('src','src-tauri','AGENTS.md','CLAUDE.md','package.json','package-lock.json','.agents','.claude')
def git(*args,input=None):
 return subprocess.check_output(['git',*args],input=input).decode().strip()
def payload(directory):
 raw=b''.join((directory/f'part-{n:02}.bin').read_bytes() for n in range(12))
 assert len(raw)==68520 and hashlib.sha256(raw).hexdigest()==DIGEST,'payload mismatch'
 obj=json.loads(lzma.decompress(raw))
 assert obj['base']==BASE and obj['target']==TARGET and len(obj['commits'])==2
 return obj

def reconstruct(data):
 assert git('rev-parse','HEAD')==BASE,'base mismatch'
 assert not git('status','--porcelain','--untracked-files=no'),'dirty tracked checkout'
 parent=BASE
 for c in data['commits']:
  assert c['parent']==parent
  subprocess.run(['git','apply','--index','--whitespace=error-all','-'],input=c['patch'].encode(),check=True)
  paths=git('diff','--cached','--name-only').splitlines()
  assert paths and all(p.startswith(ALLOWED) and '..' not in p.split('/') for p in paths),paths
  assert not git('diff','--cached','--diff-filter=D','--name-only'),'deletion forbidden'
  tree=git('write-tree');assert tree==c['tree'],'source tree mismatch'
  env=dict(os.environ)
  for typ in ('author','committer'):
   for key,value in c[typ].items():env['GIT_'+typ.upper()+'_'+key.upper()]=value
  made=subprocess.check_output(['git','commit-tree',tree,'-p',parent],input=c['message'].encode(),env=env).decode().strip()
  assert made==c['sha'],'commit identity mismatch'
  subprocess.run(['git','checkout','--detach',made],check=True)
  parent=made
 assert parent==TARGET and git('rev-parse','HEAD^{tree}')==TREE
 for p in PROTECTED:assert git('rev-parse',BASE+':'+p)==git('rev-parse',TARGET+':'+p),p
 print(json.dumps({'reconstructed_commit':TARGET,'tree':TREE,'protected_paths':'PASS'}))

def publish_objects(data,output):
 # The earlier tree POST returned 403. Do not enlarge token permissions or
 # bypass workflow restrictions: export blobs only, then use the explicitly
 # authorized native connector for reviewed tree/commit/ref operations.
 token=os.environ['GH_TOKEN']
 def api(method,path,body=None):
  assert (method,path) in [('GET','git/ref/heads/feat/cloud-gateway-agent-runtime'),('POST','git/blobs')]
  request=urllib.request.Request('https://api.github.com/repos/'+REPO+'/'+path,
   data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None,
   headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','Content-Type':'application/json'},method=method)
  with urllib.request.urlopen(request,timeout=40) as response:return json.load(response)
 assert git('rev-parse','HEAD')==TARGET
 assert api('GET','git/ref/heads/feat/cloud-gateway-agent-runtime')['object']['sha']==BASE,'remote changed; stop'
 results=[];seen=set()
 for c in data['commits']:
  entries=[]
  paths=git('diff','--name-only',c['parent'],c['sha']).splitlines()
  assert all(p.startswith(ALLOWED) for p in paths)
  for path in paths:
   mode,kind,sha=git('ls-tree',c['sha'],'--',path).split('\t')[0].split()
   assert mode in ('100644','100755') and kind=='blob'
   if sha not in seen:
    raw=subprocess.check_output(['git','cat-file','blob',sha])
    result=api('POST','git/blobs',{'content':base64.b64encode(raw).decode(),'encoding':'base64'})
    assert result['sha']==sha,'blob mismatch';seen.add(sha)
   entries.append({'path':path,'mode':mode,'type':'blob','sha':sha})
  results.append({'local':c['sha'],'parent':c['parent'],'tree':c['tree'],'base_tree':git('rev-parse',c['parent']+'^{tree}'),'entries':entries})
 report={'base':BASE,'local_target':TARGET,'tree':TREE,'payload_sha256':DIGEST,'blobs_verified':len(seen),'ref_modified':False,'trees_or_commits_created':False,'commits':results}
 output.write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='commits'}))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['reconstruct','import']);p.add_argument('directory',type=Path);p.add_argument('--output',type=Path,default=Path('import-result.json'));a=p.parse_args()
 data=payload(a.directory)
 if a.mode=='reconstruct':reconstruct(data)
 else:publish_objects(data,a.output)
