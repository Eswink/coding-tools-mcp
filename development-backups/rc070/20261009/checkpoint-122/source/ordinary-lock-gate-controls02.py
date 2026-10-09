from pathlib import Path
import ast,copy,json,tomllib,hashlib,subprocess
D=Path('/workspace/work/rc070/rsa-cargo-resolver-owned02')
raw=(D/'cargo-source-guard01.py').read_bytes()
tree=ast.parse(raw)
nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='validate_lock_graph']
assert len(nodes)==1
namespace={}
exec(compile(ast.Module(body=nodes,type_ignores=[]),str(D/'cargo-source-guard01.py'), 'exec'),namespace)
check=namespace['validate_lock_graph']
old=tomllib.loads(subprocess.check_output(['/usr/bin/git','show','HEAD:services/cloud-gateway/Cargo.lock'],cwd=D/'f13-candidate',timeout=2).decode())['package']
actual_initial=tomllib.loads((D/'f13-candidate/services/cloud-gateway/Cargo.lock').read_text())['package']
assert len(old)==230 and len(actual_initial)==216
# Synthetic IN-MEMORY data control only. Never write this vector to a lock file.
positive=copy.deepcopy(actual_initial)
original_bitflags=next(x for x in old if x['name']=='bitflags')
for i,row in enumerate(positive):
 if row['name']=='bitflags':
  positive[i]=copy.deepcopy(original_bitflags)
  positive[i].pop('dependencies',None)
assert not check(old,positive)['unexpected']
results=[{'name':'synthetic_in_memory_permitted_graph','pass':True}]
def negative(name,mutate):
 rows=copy.deepcopy(positive);mutate(rows);errors=check(old,rows)['unexpected'];assert errors,name
 results.append({'name':name,'pass':True,'actualRejectKinds':sorted({x['kind'] for x in errors})})
def row(rows,name):return next(x for x in rows if x['name']==name)
negative('actual_unadmitted_initial_upgrade',lambda rows:rows.__setitem__(slice(None),copy.deepcopy(actual_initial)))
negative('unrelated_original_package_removed',lambda rows:rows.remove(row(rows,'bytes')))
negative('new_unrelated_package_added',lambda rows:rows.append({'name':'unrelated-owned-invention','version':'1.0.0'}))
negative('duplicate_identity',lambda rows:rows.__setitem__(0,copy.deepcopy(rows[1])))
negative('original_checksum_changed',lambda rows:row(rows,'bytes').__setitem__('checksum','0'*64))
negative('original_source_changed',lambda rows:row(rows,'bytes').__setitem__('source','registry+https://invalid.example/index'))
negative('original_version_changed',lambda rows:row(rows,'bytes').__setitem__('version','99.0.0'))
negative('unrelated_field_added',lambda rows:row(rows,'bytes').__setitem__('arbitrary_field',True))
negative('dependency_added',lambda rows:row(rows,'sqlx-macros-core')['dependencies'].append('rsa'))
negative('unrelated_dependency_removed',lambda rows:row(rows,'sqlx-macros-core')['dependencies'].remove('tokio'))
negative('dependency_reordered',lambda rows:row(rows,'sqlx-macros-core')['dependencies'].reverse())
negative('dependency_duplicated',lambda rows:row(rows,'sqlx-macros-core')['dependencies'].append('tokio'))
negative('lingering_RSA',lambda rows:rows.append(copy.deepcopy(next(x for x in old if x['name']=='rsa'))))
negative('lingering_MySQL',lambda rows:rows.append(copy.deepcopy(next(x for x in old if x['name']=='sqlx-mysql'))))
negative('owned_patch_source_lost',lambda rows:row(rows,'sqlx').__setitem__('source',next(x['source'] for x in old if x['name']=='sqlx')))
negative('owned_patch_checksum_lost',lambda rows:row(rows,'sqlx-macros-core').__setitem__('checksum',next(x['checksum'] for x in old if x['name']=='sqlx-macros-core')))
negative('malformed_dependency_type',lambda rows:row(rows,'sqlx')['dependencies'].__setitem__(0,7))
# Exact source and initial-lock predicate AST controls; no guard/native entry runs.
guardnode=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='guard')
sourcecheck=next(n for n in guardnode.body if isinstance(n,ast.If) and 'SOURCE_LEASE_DRIFT' in ast.dump(n))
packet=json.loads((D/'STARTUP-PACKET01.json').read_text())
env={'D':D,'P':copy.deepcopy(packet),'sha':lambda b:hashlib.sha256(b).hexdigest()}
expr=compile(ast.Expression(sourcecheck.test),'exact-source-lease-predicate','eval')
assert eval(expr,env) is False
env['P']['sourcePreparationSHA']='0'*64
assert eval(expr,env) is True
results.append({'name':'exact_AST_initial_source_lease_mismatch','pass':True})
begin=next(n for n in tree.body if isinstance(n,ast.If) and isinstance(n.test,ast.Compare) and isinstance(n.test.left,ast.Name) and n.test.left.id=='mode' and isinstance(n.test.comparators[0],ast.Constant) and n.test.comparators[0].value=='begin')
lockcheck=next(n for n in begin.body if isinstance(n,ast.If) and 'INITIAL_LOCK_DRIFT' in ast.dump(n))
env={'W':D/'f13-candidate','rel':'services/cloud-gateway/Cargo.lock','x':copy.deepcopy(packet['initialLockLease']),'sha':lambda b:hashlib.sha256(b).hexdigest()}
expr=compile(ast.Expression(lockcheck.test),'exact-initial-lock-predicate','eval')
assert eval(expr,env) is False
env['x']['sha256']='0'*64
assert eval(expr,env) is True
results.append({'name':'exact_AST_initial_lock_SHA_mismatch','pass':True})
env['x']=copy.deepcopy(packet['initialLockLease']);env['x']['bytes']+=1
assert eval(expr,env) is True
results.append({'name':'exact_AST_initial_lock_byte_count_mismatch','pass':True})
result={'scope':'ORDINARY_DATA_ONLY_EXACT_FUNCTION_AST_NOT_WHOLE_GUARD_OR_CARGO','sourceSHA256':hashlib.sha256(raw).hexdigest(),'functionASTSHA256':hashlib.sha256(ast.dump(nodes[0],include_attributes=False).encode()).hexdigest(),'syntheticPositiveNotActualRepairedCargoLock':True,'namedControls':results,'controls':len(results),'CargoExecutions':0,'sourceLockWritten':False,'RCQualification':False}
print(json.dumps(result,indent=2))
