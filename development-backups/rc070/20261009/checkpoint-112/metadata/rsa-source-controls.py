"""Ordinary TOML/source model only. No Cargo, issuer, build or native execution."""
from pathlib import Path
import tomllib,json,hashlib,copy,unittest,sys,stat
W=Path('/workspace/work/rc070/independent-review-work'); C=W/'f13-rsa-candidate-source';R=Path('/workspace/work/rc070/windows-tools/cargo/registry/src/index.crates.io-1949cf8c6b5b557f')
SELECTION=('runtime-tokio-rustls','postgres','migrate','macros','uuid')
def admit_postgres_source_request(features,default_features):
 if type(features) not in (list,tuple) or type(default_features) is not bool:raise ValueError('typed request required')
 if default_features or any(type(x) is not str for x in features) or len(features)!=len(set(features)):raise ValueError('invalid feature request')
 if set(features)!=set(SELECTION):raise ValueError('unsupported SOURCE_ONLY_POSTGRES feature selection')
 return {'state':'SOURCE_ONLY_NOT_WIRED','cargo_run_allowed':False,'issuer_authority':False}
def manifests(candidate):
 out={}
 for p in R.glob('sqlx*-0.8.6/Cargo.toml'):
  m=tomllib.loads(p.read_text());out[m['package']['name']]=m
 if candidate:
  for name in ('sqlx','sqlx-macros-core'):out[name]=tomllib.loads((C/'services/cloud-gateway/vendor'/name/'Cargo.toml').read_text())
 return out
def closure(ms,selection=SELECTION):
 """Fixed-point model of normal dependencies and features inside SQLx packages; external tokens remain symbolic, not Cargo proof."""
 selected={'sqlx':set(selection)};active={}; external=set();changed=True
 while changed:
  before=repr((sorted((p,sorted(v)) for p,v in selected.items()), sorted((p,sorted(v)) for p,v in active.items()), sorted(external)))
  for name,features in list(selected.items()):
   m=ms[name];deps=m.get('dependencies',{});enabled=active.setdefault(name,set())
   for dep,row in deps.items():
    if not row.get('optional',False):enabled.add(dep)
   for f in list(features):
    if f not in m.get('features',{}):
     suppressed={x[4:] for xs in m.get('features',{}).values() for x in xs if x.startswith('dep:')}
     if f in deps and deps[f].get('optional',False) and f not in suppressed:
      enabled.add(f);continue
     raise ValueError('undeclared '+name+'/'+f)
    for token in m['features'][f]:
     if token.startswith('dep:'):enabled.add(token[4:])
     elif '/' in token:
      dep,feat=token.split('/',1);weak=dep.endswith('?');dep=dep.rstrip('?')
      if not weak:enabled.add(dep)
      if not weak or dep in enabled:
       if dep in ms:selected.setdefault(dep,set()).add(feat)
       else:external.add((name,dep,feat))
     elif token in m.get('features',{}):features.add(token)
     elif token in deps:enabled.add(token)
     else:raise ValueError('undeclared token '+name+'/'+token)
   for dep in enabled:
    if dep not in deps:raise ValueError('missing dependency '+name+'/'+dep)
    row=deps[dep]
    if dep in ms:
     fs=selected.setdefault(dep,set());fs.update(row.get('features',[]))
     if row.get('default-features',True) and 'default' in ms[dep].get('features',{}):fs.add('default')
    else:external.update((name,dep,f) for f in row.get('features',[]))
  after=repr((sorted((p,sorted(v)) for p,v in selected.items()),sorted((p,sorted(v)) for p,v in active.items()),sorted(external)))
  changed=before!=after
 return {'features':{p:sorted(v) for p,v in sorted(selected.items())},'active_dependencies':{p:sorted(v) for p,v in sorted(active.items())},'external_symbolic_features':[list(x) for x in sorted(external)]}
def require_parity(ms):
 result=closure(ms)
 if result!=closure(manifests(False)):raise ValueError('current PostgreSQL closure changed')
 if 'sqlx-mysql' in result['features'] or any('sqlx-mysql' in ds for ds in result['active_dependencies'].values()):raise ValueError('mysql active')
 return result
def require_delta(original,candidate):
 for name in ('sqlx','sqlx-macros-core'):
  expected=copy.deepcopy(original[name]);del expected['dependencies']['sqlx-mysql']
  for f,items in expected['features'].items():expected['features'][f]=[x for x in items if x!='sqlx-mysql' and not x.startswith('sqlx-mysql?/')]
  if candidate[name]!=expected:raise ValueError('unexpected manifest delta')
 for name in original:
  if name not in ('sqlx','sqlx-macros-core') and candidate[name]!=original[name]:raise ValueError('third manifest delta')
class Controls(unittest.TestCase):
 def test_current_postgres_parity(self):require_parity(manifests(True))
 def test_exact_two_manifest_semantics(self):require_delta(manifests(False),manifests(True))
 def test_optional_mysql_removed(self):
  for name in ('sqlx','sqlx-macros-core'):self.assertNotIn('sqlx-mysql',manifests(True)[name]['dependencies'])
 def test_all_weak_references_removed(self):
  for name in ('sqlx','sqlx-macros-core'):
   self.assertFalse(any('sqlx-mysql' in x for xs in manifests(True)[name]['features'].values() for x in xs))
 def test_third_mysql_feature_target_declared(self):
  ms=manifests(True);self.assertEqual(ms['sqlx-macros']['features']['mysql'],['sqlx-macros-core/mysql']);self.assertIn('mysql',ms['sqlx-macros-core']['features'])
 def test_original_postgres_request_not_authority(self):self.assertEqual(admit_postgres_source_request(list(SELECTION),False)['cargo_run_allowed'],False)
 def test_mysql_rejected(self):
  with self.assertRaises(ValueError):admit_postgres_source_request([*SELECTION,'mysql'],False)
 def test_all_databases_rejected(self):
  with self.assertRaises(ValueError):admit_postgres_source_request(['all-databases'],False)
 def test_default_features_rejected(self):
  with self.assertRaises(ValueError):admit_postgres_source_request(list(SELECTION),True)
 def test_duplicate_features_rejected(self):
  with self.assertRaises(ValueError):admit_postgres_source_request([*SELECTION,'uuid'],False)
 def test_untyped_default_rejected(self):
  with self.assertRaises(ValueError):admit_postgres_source_request(list(SELECTION),0)
 def test_bad_postgres_dependency_rejected(self):
  ms=manifests(True);del ms['sqlx']['dependencies']['sqlx-postgres']
  with self.assertRaises(ValueError):require_parity(ms)
 def test_lost_migrate_forward_rejected(self):
  ms=manifests(True);ms['sqlx']['features']['migrate']=[]
  with self.assertRaises(ValueError):require_parity(ms)
 def test_third_manifest_change_rejected(self):
  ms=manifests(True);ms['sqlx-macros']['features']['mysql']=[]
  with self.assertRaises(ValueError):require_delta(manifests(False),ms)
 def test_compat_feature_mutation_rejected(self):
  ms=manifests(True);ms['sqlx-macros-core']['features']['mysql']=['migrate']
  with self.assertRaises(ValueError):require_delta(manifests(False),ms)
 def test_all_original_source_parity(self):
  original=json.loads((W/'F13-RSA-OFFICIAL193-BEFORE01.json').read_text())
  for r in original['files']:
   p=C/r['path'];s=p.lstat();self.assertEqual(s.st_nlink,1);self.assertEqual(stat.S_IMODE(s.st_mode),0o755 if r['mode']=='100755' else 0o644)
   if not r['path'].endswith('/Cargo.toml'):self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),r['sha256'])
if __name__=='__main__':
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(Controls);r=unittest.TextTestRunner(verbosity=2).run(suite)
 report={'loaded':suite.countTestCases(),'executed':r.testsRun,'success':r.wasSuccessful(),'failures':len(r.failures),'errors':len(r.errors),'closure':require_parity(manifests(True)),'model_boundary':'ordinary TOML fixedpoint normalSQLx dependencies; symbolic outsideSQLx; NOT Cargo','cargo': 'NOTRUN','state':'SOURCE_ONLY_NOT_WIRED','original_RSA_audit':'FAIL_UNCHANGED'}
 with (W/'F13-RSA-ORDINARY-CONTROLS02.json').open('x') as f:json.dump(report,f,indent=2);f.write('\n')
 sys.exit(0 if r.wasSuccessful() else 1)
