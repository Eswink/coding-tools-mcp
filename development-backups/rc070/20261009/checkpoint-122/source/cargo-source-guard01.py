from pathlib import Path
import json,hashlib,stat,subprocess,sys,time,os
D=Path('/workspace/work/rc070/rsa-cargo-resolver-owned02');W=D/'f13-candidate';P=json.load(open(D/'STARTUP-PACKET01.json'));S=json.load(open(D/'SOURCE-PREPARATION-LEASES02.json'))
def sha(b):return hashlib.sha256(b).hexdigest()
def validate_lock_graph(oldrows,newrows):
 from collections import Counter
 removed_names={'const-oid','der','lazy_static','libm','num-bigint-dig','num-integer','num-iter','pem-rfc7468','pkcs1','pkcs8','rsa','signature','spki','sqlx-mysql'}
 allowed_edges={('sqlx','sqlx-mysql'),('sqlx-macros-core','sqlx-mysql'),('digest','const-oid'),('num-traits','libm'),('bitflags','serde')}
 problems=[];changed=[]
 def valid(rows):
  return isinstance(rows,list) and all(isinstance(x,dict) and isinstance(x.get('name'),str) and isinstance(x.get('version'),str) and isinstance(x.get('dependencies',[]),list) and all(isinstance(d,str) for d in x.get('dependencies',[])) for x in rows)
 if not valid(oldrows) or not valid(newrows):return {'unexpected':[{'kind':'malformed_package_rows'}]}
 original={(x['name'],x['version']):x for x in oldrows};current={(x['name'],x['version']):x for x in newrows}
 if len(oldrows)!=230 or len(newrows)!=216:problems.append({'kind':'exact_package_count'})
 if len(original)!=len(oldrows) or len(current)!=len(newrows):problems.append({'kind':'duplicate_identity'})
 expected_removed={k for k in original if k[0] in removed_names}
 if len(expected_removed)!=14 or {k[0] for k in expected_removed}!=removed_names or set(original)-set(current)!=expected_removed:problems.append({'kind':'unadmitted_removed_identity'})
 for x in newrows:
  key=(x['name'],x['version']);prev=original.get(key)
  if prev is None:problems.append({'kind':'new_or_upgrade','row':x});continue
  if x!=prev:changed.append({'before':prev,'after':x})
  before={k:v for k,v in prev.items() if k!='dependencies'};after={k:v for k,v in x.items() if k!='dependencies'}
  if x['name'] in ('sqlx','sqlx-macros-core'):
   if x['version']!='0.8.6' or x.get('source') is not None or x.get('checksum') is not None:problems.append({'kind':'patch_not_owned_path','row':x})
   for k in ('source','checksum'):before.pop(k,None);after.pop(k,None)
  if before!=after:problems.append({'kind':'unadmitted_package_fields','row':x})
  od=prev.get('dependencies',[]);nd=x.get('dependencies',[]);adds=Counter(nd)-Counter(od);drops=Counter(od)-Counter(nd)
  if adds:problems.append({'kind':'dependency_added','package':key,'dependencies':list(adds.elements())})
  if any((x['name'],d.split(' ')[0]) not in allowed_edges for d in drops):problems.append({'kind':'dependency_removed','package':key,'dependencies':list(drops.elements())})
  remaining=list(od)
  for d in drops.elements():remaining.remove(d)
  if remaining!=nd:problems.append({'kind':'dependency_order_or_multiplicity','package':key})
 if any(k[0] in ('rsa','sqlx-mysql') for k in current):problems.append({'kind':'RSA_OR_MYSQL_REMAINS'})
 if ('bitflags','2.9.4') not in current or ('bitflags','2.13.0') in current:problems.append({'kind':'BITFLAGS_EXACT_VERSION'})
 if any((name,'0.8.6') not in current for name in ('sqlx','sqlx-macros-core')):problems.append({'kind':'MISSING_OWNED_PATCH'})
 return {'oldCount':len(oldrows),'newCount':len(newrows),'removed':[x for x in oldrows if (x['name'],x['version']) not in current],'changed':changed,'unexpected':problems,'wholeNewGraph':newrows,'ObservedLockAfterCargoAttempt':True}
def guard():
 errors=[];cancellations=[];expected={x['path']:x for x in S['baseline1840']};expected.update({x['path']:x for x in S['candidate193']});assert len(expected)==2033
 if sha((D/'SOURCE-PREPARATION-LEASES02.json').read_bytes())!=P['sourcePreparationSHA']:errors.append('SOURCE_LEASE_DRIFT')
 for rel,x in P['executorSourceLeases'].items():
  p=D/rel;s=p.lstat();b=p.read_bytes()
  if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1 or stat.S_IMODE(s.st_mode)!=int(x['mode'],8) or len(b)!=x['bytes'] or sha(b)!=x['sha256']:errors.append('EXECUTOR_SOURCE_DRIFT:'+rel)
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
  diff=validate_lock_graph(old['package'],new['package'])
  lockbytes=(W/rel).read_bytes();diff['actualNewLockBytes']=len(lockbytes);diff['actualNewLockSHA256']=sha(lockbytes)
  if diff['unexpected']:out['errors'].append('UNADMITTED_LOCK_GRAPH_CHANGE')
  p=D/'ACTUAL-CARGO-GENERATED-LOCK-DIFF01.json'
  with p.open('x') as f:json.dump(diff,f,indent=2)
  p.chmod(0o600)
 except Exception as e:out['errors'].append('LOCK_GRAPH_READ_FAILED:'+type(e).__name__)
sealed=D/'ACTUAL-CARGO-GENERATED-LOCK-DIFF01.json'
if sealed.exists() and mode!='after-1':
 try:
  x=json.loads(sealed.read_text());b=(W/P['sourceAllowedMutation'][0]).read_bytes()
  if len(b)!=x['actualNewLockBytes'] or sha(b)!=x['actualNewLockSHA256']:out['errors'].append('POST_UPDATE_LOCK_CHANGED')
 except Exception as e:out['errors'].append('POST_UPDATE_LOCK_CHECK_FAILED:'+type(e).__name__)
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
 # Before this distinct attempt the prior genuine generated lock is exact, not the original native comparator.
 rel=P['sourceAllowedMutation'][0];x=P['initialLockLease']
 if len((W/rel).read_bytes())!=x['bytes'] or sha((W/rel).read_bytes())!=x['sha256']:out['errors'].append('INITIAL_LOCK_DRIFT')
 if marker.exists() or Path(P['exactEnvironment']['CARGO_TARGET_DIR']).exists() or logs:out['errors'].append('INITIAL_SLOT_NOT_EMPTY')
 if not out['errors']:
  started={'startedMonotonic':time.monotonic(),'packetSHA256':sha((D/'STARTUP-PACKET01.json').read_bytes()),'sourceLeaseSHA256':sha((D/'SOURCE-PREPARATION-LEASES02.json').read_bytes()),'soleAttempt':True,'qualification':'CARGO_RESOLUTION_ONLY_NO_NATIVE_OWNER'}
  with marker.open('x') as f:json.dump(started,f)
  marker.chmod(0o600);out['startedMonotonic']=started['startedMonotonic'];out['elapsedSeconds']=time.monotonic()-started['startedMonotonic']
p=D/('GUARD-'+mode+'-'+str(time.monotonic_ns())+'.json');p.write_text(json.dumps(out,indent=2)+'\n');p.chmod(0o600);print(json.dumps(out));sys.exit(1 if out['errors'] else 0)
