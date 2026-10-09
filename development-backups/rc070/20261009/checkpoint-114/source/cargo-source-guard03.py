from pathlib import Path
import json,hashlib,stat,subprocess,sys,time,os
D=Path('/workspace/work/rc070/rsa-cargo-resolver-owned01');W=D/'f13-candidate';P=json.load(open(D/'STARTUP-PACKET01.json'));S=json.load(open(D/'SOURCE-PREPARATION-LEASES02.json'))
def sha(b):return hashlib.sha256(b).hexdigest()
def guard():
 errors=[];cancellations=[];expected={x['path']:x for x in S['baseline1840']};expected.update({x['path']:x for x in S['candidate193']});assert len(expected)==2033
 actual=set()
 for root,dirs,files in os.walk(W,followlinks=False):
  dirs[:]=[n for n in dirs if not (Path(root)==W and n=='.git')]
  for n in dirs:
   if (Path(root)/n).is_symlink():errors.append('SOURCE_DIR_SYMLINK:'+str((Path(root)/n).relative_to(W)))
  for n in files:actual.add((Path(root)/n).relative_to(W).as_posix())
 if actual!=set(expected):errors.append('SOURCE_NAMESPACE_DRIFT')
 for rel,x in expected.items():
  try:
   p=W/rel;s=p.lstat();mode=x.get('nativeMode',x.get('mode'));b=p.read_bytes()
   if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1 or stat.S_IMODE(s.st_mode)!=int(mode[-3:],8):errors.append('SOURCE_FILE_KIND_MODE:'+rel)
   if rel not in P['sourceAllowedMutation'] and (len(b)!=x['bytes'] or sha(b)!=x['sha256']):errors.append('SOURCE_BYTES:'+rel)
  except BaseException as e:
   if isinstance(e,Exception):errors.append('SOURCE_READ_FAILED:'+rel+':'+type(e).__name__)
   else:cancellations.append(e)
 for name,x in P['tools'].items():
  try:
   p=Path(x['path']);s=p.stat();b=p.read_bytes();m=x.get('mode',x.get('physicalMode'))
   if len(b)!=x['bytes'] or sha(b)!=x['sha256'] or stat.S_IMODE(s.st_mode)!=int(m,8) or any(getattr(s,k)!=x[key] for k,key in [('st_dev','dev'),('st_ino','inode'),('st_nlink','nlink'),('st_mtime_ns','mtimeNs'),('st_ctime_ns','ctimeNs')]):errors.append('RUNTIME_DRIFT:'+name)
  except BaseException as e:
   if isinstance(e,Exception):errors.append('RUNTIME_READ_FAILED:'+name+':'+type(e).__name__)
   else:cancellations.append(e)
 for p in P['configAbsences']:
  try:
   if os.path.lexists(p):errors.append('CONFIG_ABSENCE_CHANGED:'+p)
  except BaseException as e:
   if isinstance(e,Exception):errors.append('CONFIG_CHECK_FAILED:'+type(e).__name__)
   else:cancellations.append(e)
 try:
  if subprocess.check_output(['/usr/bin/git','rev-parse','HEAD'],cwd=W,timeout=2).decode().strip()!=P['head']:errors.append('HEAD_DRIFT')
 except BaseException as e:
  if isinstance(e,Exception):errors.append('HEAD_READ_FAILED:'+type(e).__name__)
  else:cancellations.append(e)
 if cancellations:
  if len(cancellations)==1:raise cancellations[0]
  raise BaseExceptionGroup('source guard original cancellations',cancellations)
 return errors
mode=sys.argv[1];marker=Path(P['onceMarker']);out={'mode':mode,'errors':guard(),'currentMonotonic':time.monotonic(),'sourceFiles':2033,'nativeOwnerGranted':False,'qualifiedRC':False}
logs=[]
if mode=='after-1':
 import tomllib
 try:
  rel=P['sourceAllowedMutation'][0];old=tomllib.loads(subprocess.check_output(['/usr/bin/git','show','HEAD:'+rel],cwd=W,timeout=2).decode());new=tomllib.loads((W/rel).read_text())
  oldrows=old['package'];newrows=new['package'];original={(x['name'],x['version']):x for x in oldrows};changed=[];unexpected=[]
  for x in newrows:
   key=(x['name'],x['version']);prev=original.get(key)
   if prev is None:unexpected.append({'kind':'new_or_upgrade','row':x});continue
   if x!=prev:changed.append({'before':prev,'after':x})
   if x['name'] not in ('sqlx','sqlx-macros-core') and any(x.get(k)!=prev.get(k) for k in ('source','checksum')):unexpected.append({'kind':'source_or_checksum','row':x})
   if x['name'] in ('sqlx','sqlx-macros-core') and (x['version']!='0.8.6' or x.get('source') is not None or x.get('checksum') is not None):unexpected.append({'kind':'patch_not_owned_path','row':x})
  if any(x['name'] in ('rsa','sqlx-mysql') for x in newrows):out['errors'].append('RSA_OR_MYSQL_REMAINS')
  if unexpected:out['errors'].append('UNADMITTED_LOCK_GRAPH_CHANGE')
  diff={'oldCount':len(oldrows),'newCount':len(newrows),'removed':[x for x in oldrows if (x['name'],x['version']) not in {(y['name'],y['version']) for y in newrows}],'changed':changed,'unexpected':unexpected,'wholeNewGraph':newrows,'ObservedLockAfterCargoAttempt':True}
  p=D/'ACTUAL-CARGO-GENERATED-LOCK-DIFF01.json'
  with p.open('x') as f:json.dump(diff,f,indent=2)
  p.chmod(0o600)
 except Exception as e:out['errors'].append('LOCK_GRAPH_READ_FAILED:'+type(e).__name__)
for p in sorted((D/'raw').iterdir()):
 st=p.lstat()
 if not stat.S_ISREG(st.st_mode) or st.st_nlink!=1:out['errors'].append('RAW_FILE_KIND');continue
 b=p.read_bytes();logs.append({'file':p.name,'bytes':len(b),'sha256':sha(b)})
out['raw']=logs;out['rawTotal']=sum(x['bytes'] for x in logs)
if out['rawTotal']>P['rawTotalMaxBytes']:out['errors'].append('RAW_TOTAL_LIMIT')
if marker.exists():
 started=json.load(open(marker));out['startedMonotonic']=started['startedMonotonic'];out['elapsedSeconds']=time.monotonic()-out['startedMonotonic']
 if out['elapsedSeconds']>120:out['errors'].append('TOTAL_DEADLINE')
if mode=='begin':
 # Before the sole attempt the original lock is still byte exact.
 rel=P['sourceAllowedMutation'][0];x=next(x for x in S['baseline1840'] if x['path']==rel)
 if sha((W/rel).read_bytes())!=x['sha256']:out['errors'].append('INITIAL_LOCK_DRIFT')
 if marker.exists() or Path(P['exactEnvironment']['CARGO_TARGET_DIR']).exists() or logs:out['errors'].append('INITIAL_SLOT_NOT_EMPTY')
 if not out['errors']:
  started={'startedMonotonic':time.monotonic(),'packetSHA256':sha((D/'STARTUP-PACKET01.json').read_bytes()),'sourceLeaseSHA256':sha((D/'SOURCE-PREPARATION-LEASES02.json').read_bytes()),'soleAttempt':True,'qualification':'CARGO_RESOLUTION_ONLY_NO_NATIVE_OWNER'}
  with marker.open('x') as f:json.dump(started,f)
  marker.chmod(0o600);out['startedMonotonic']=started['startedMonotonic'];out['elapsedSeconds']=time.monotonic()-started['startedMonotonic']
p=D/('GUARD-'+mode+'-'+str(time.monotonic_ns())+'.json');p.write_text(json.dumps(out,indent=2)+'\n');p.chmod(0o600);print(json.dumps(out));sys.exit(1 if out['errors'] else 0)
