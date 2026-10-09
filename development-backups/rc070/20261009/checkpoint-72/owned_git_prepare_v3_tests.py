"""Ordinary owned controls only. Never execute original Git make/install.

Current genuine msgfmt may be read/leased; no downloaded ELF invocation here.
Mock source authenticity/build/install responses are explicitly ordinary fixtures.
"""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
import tempfile
import types
import unittest
from unittest.mock import patch
sys.dont_write_bytecode=True
import owned_git_prepare_v3 as g

ACTUAL_MSGFMT=Path('/workspace/work/rc070/publisher-debian-msgfmt-research/actual-owned-debian-msgfmt01/preparation-result.json')
ORIGINAL_MAKEFILE=Path('/workspace/work/rc070/publisher-supplementary-git-research/official-tar-Makefile')

class OwnedGitV3Controls(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=g.OWNED_ROOT,prefix='ordinary-git-v3-');self.root=Path(self.tmp.name)
 def tearDown(self):self.tmp.cleanup()
 def fixture_tar(self,rows=None):
  rows=rows if rows is not None else [('git-2.55.0/Makefile','file',ORIGINAL_MAKEFILE.read_bytes()),('git-2.55.0/README','file',b'ordinary fixture, not signedGit')]
  out=io.BytesIO()
  with tarfile.open(fileobj=out,mode='w:') as tar:
   for name,kind,payload in rows:
    member=tarfile.TarInfo(name);member.mode=0o644
    if kind=='file':member.size=len(payload);tar.addfile(member,io.BytesIO(payload))
    elif kind=='link':member.type=tarfile.SYMTYPE;member.linkname=payload;tar.addfile(member)
    elif kind=='hard':member.type=tarfile.LNKTYPE;member.linkname=payload;tar.addfile(member)
  return out.getvalue()
 def source_guard(self):
  m=g.load_reviewed_git_dependencies();return {name:m.snapshot_debian_tool(g.OWNED_ROOT/name) for name in g.SOURCE5}
 def fake_tools(self,evidence):
  return {'passed':True,'runtime':{},'build_env':{'PATH':str(g.TOOLCHAIN)+':/usr/bin:/bin','RUSTC':str(g.TOOLCHAIN/'rustc'),'HOME':str(self.root),'CARGO_HOME':str(self.root),'LANG':'C','LC_ALL':'C','TZ':'UTC'}}
 def fake_phase(self,vector,*args,**kwargs):
  return {'command':vector,'exit':2,'reason':None,'passed':False,'seconds':0,'log_bytes':0,'log_sha256':hashlib.sha256(b'').hexdigest()}
 def test_frozen_adapter_real_hash_and_no_pycache(self):
  self.assertEqual(hashlib.sha256(g.DEB_SOURCE.read_bytes()).hexdigest(),g.DEB_SHA)
  module=g.load_reviewed_git_dependencies();self.assertEqual(module.__name__,'exact_reviewed_debian_v3_adapter')
  self.assertEqual(module._OwnedDebianFile.__init__.__code__.co_filename,str(g.DEB_SOURCE))
 def test_adapter_bootstrap_read_primary_close_cancel_sameobjects(self):
  source=self.root/'adapter';source.write_bytes(b'x');actual_close=os.close;primary=KeyboardInterrupt('READ_CANCEL');cleanup=SystemExit('CLOSE_CANCEL');attempts=[]
  def closed(fd):attempts.append(fd);actual_close(fd);raise cleanup
  with patch.object(g,'DEB_SOURCE',source),patch.object(g.os,'read',side_effect=primary),patch.object(g.os,'close',side_effect=closed):
   try:g.load_reviewed_git_dependencies()
   except BaseException as error:self.assertIsInstance(error,BaseExceptionGroup);self.assertIs(error.exceptions[0],primary);self.assertIs(error.exceptions[1],cleanup)
   else:self.fail('Bootstrap original/cancel objects lost')
  self.assertEqual(len(attempts),1)
 def test_adapter_hash_drift_refused(self):
  source=self.root/'wrong';source.write_bytes(b'notreviewedcode')
  with patch.object(g,'DEB_SOURCE',source):
   with self.assertRaises(ValueError):g.load_reviewed_git_dependencies()
 def test_original_archive_inputs_pin_before_gpg_or_extract(self):
  source=self.root/'archive';source.write_bytes(b'bad')
  with patch.object(g.subprocess,'run') as run:
   with self.assertRaises(ValueError):g.verify_git_source(source,source,source,self.root/'auth')
   run.assert_not_called()
 def test_synthetic_source_extraction_bytes_and_manifest(self):
  source=g.extract_owned_git_source(self.fixture_tar(),self.root/'extract')
  self.assertEqual((source/'Makefile').read_bytes(),ORIGINAL_MAKEFILE.read_bytes())
  snapshot=g.snapshot_original_git_source(source);self.assertEqual(set(snapshot),{'Makefile','README'});self.assertTrue((source.parent/'SOURCE-MANIFEST.json').is_file())
 def test_source_escape_duplicate_hardlink_underlink_denied(self):
  cases=[[('../escape','file',b'x')],[('git-2.55.0/a','file',b'x'),('git-2.55.0/a','file',b'y')],[('git-2.55.0/a','hard','b')],[('git-2.55.0/a','link','../../outside')],[('git-2.55.0/a','link','b'),('git-2.55.0/a/child','file',b'x')]]
  for i,rows in enumerate(cases):
   with self.assertRaises(ValueError):g.extract_owned_git_source(self.fixture_tar(rows),self.root/f'bad-{i}')
 def test_existing_source_canary_and_member_cap_denied(self):
  target=self.root/'existing';target.mkdir();canary=target/'keep';canary.write_bytes(b'keep')
  with self.assertRaises(FileExistsError):g.extract_owned_git_source(self.fixture_tar(),target)
  self.assertEqual(canary.read_bytes(),b'keep')
  with patch.object(g,'MAX_TAR',1):
   with self.assertRaises(ValueError):g.extract_owned_git_source(self.fixture_tar(),self.root/'bound')
 def test_original_source_mutation_detected(self):
  source=g.extract_owned_git_source(self.fixture_tar(),self.root/'s');old=g.snapshot_original_git_source(source);(source/'README').write_bytes(b'changed')
  self.assertNotEqual(g.snapshot_original_git_source(source,old),old)
 def test_current_real_msgfmt_readonly_checked_vector(self):
  actual=g.validate_msgfmt_assignment(ACTUAL_MSGFMT)
  self.assertTrue(actual['assignment'].endswith(' --check'));self.assertEqual(shlex.split(actual['assignment'][7:]),[*actual['vector'],'--check']);self.assertGreater(len(actual['leases']),4)
  self.assertNotIn('LD_LIBRARY_PATH',actual['assignment']);self.assertNotIn('NO_GETTEXT',actual['assignment'])
 def test_missing_or_FALSE_msgfmt_result_denied_without_native(self):
  m=g.load_reviewed_git_dependencies();tmp=tempfile.TemporaryDirectory(dir=m.ROOT,prefix='ordinary-git-msgfmt-negative-')
  try:
   path=Path(tmp.name)/'result.json'
   for change in ({'status':'FAIL'},{'OWNED_EXTRACTION':False},{'original_runtime_unchanged':False},{'native_final_unchanged':False}):
    current=copy.deepcopy(json.loads(ACTUAL_MSGFMT.read_text()));current.update(change);path.write_text(json.dumps(current))
    with patch.object(g.subprocess,'Popen') as popen:
     with self.assertRaises(ValueError):g.validate_msgfmt_assignment(path)
     popen.assert_not_called()
  finally:tmp.cleanup()
 def test_unsafe_MSGFMT_make_expansion_denied(self):
  # Source logic has a real make-dollar guard; test actual source AST/byte clause
  # with an otherwise complete actual receipt and a changed literal loader value.
  m=g.load_reviewed_git_dependencies();tmp=tempfile.TemporaryDirectory(dir=m.ROOT,prefix='ordinary-msgfmt-argv-')
  try:
   path=Path(tmp.name)/'result.json';current=copy.deepcopy(json.loads(ACTUAL_MSGFMT.read_text()));current['phases'][0]['command'][0]='$($(shell false))';path.write_text(json.dumps(current))
   with self.assertRaises(ValueError):g.validate_msgfmt_assignment(path)
  finally:tmp.cleanup()
 def test_actual_owned_shell_program_args_keeps_original_check(self):
  # Actual /bin/sh + existing Python; not downloaded msgfmt/Git, no Makefile run.
  vector=['/usr/bin/python3','-c','import json,sys;print(json.dumps(sys.argv[1:]))','--check']
  command=shlex.join(vector)+' -o ordinary.mo ordinary.po'
  result=subprocess.run(['/bin/sh','-c',command],cwd=self.root,env={'PATH':'/usr/bin:/bin'},capture_output=True,timeout=5)
  self.assertEqual(result.returncode,0);self.assertEqual(json.loads(result.stdout),['--check','-o','ordinary.mo','ordinary.po'])
 def test_prefix_existing_symlink_host_and_make_dollar_denied(self):
  existing=self.root/'old';existing.mkdir();(existing/'keep').write_bytes(b'keep');link=self.root/'link';link.symlink_to(existing)
  for path in (existing,link,Path('/usr/local'),self.root/'$(shell false)',self.root/'space prefix'):
   with self.assertRaises(ValueError):g.validate_owned_install_prefix(path)
  self.assertEqual((existing/'keep').read_bytes(),b'keep');self.assertEqual(g.validate_owned_install_prefix(self.root/'new'),self.root/'new')
 def test_installed_hardlink_topology_unique_payload_and_outside_denied(self):
  prefix=self.root/'prefix';prefix.mkdir();file=prefix/'git';file.write_bytes(b'ownedfixture');os.link(file,prefix/'git-init')
  manifest=g.snapshot_original_git_source(prefix,installed=True);self.assertEqual(len(manifest),2);self.assertEqual(manifest['git']['link_count'],2)
  os.link(file,self.root/'external-link')
  with self.assertRaises(ValueError):g.snapshot_original_git_source(prefix,installed=True)
 def test_installed_namespace_added_or_escaped_link_denied(self):
  prefix=self.root/'p';prefix.mkdir();(prefix/'a').write_bytes(b'a');old=g.snapshot_original_git_source(prefix,installed=True);(prefix/'b').write_bytes(b'b')
  self.assertNotEqual(g.snapshot_original_git_source(prefix,installed=True),old);(prefix/'outside').symlink_to(self.root)
  with self.assertRaises(ValueError):g.snapshot_original_git_source(prefix,installed=True)
 def test_executeFalse_auth_fixture_no_build_install_or_msgfmt(self):
  with patch.object(g,'verify_git_source',return_value=self.fixture_tar()) as auth,patch.object(g,'run_owned_git_phase') as phase,patch.object(g,'validate_msgfmt_assignment') as msg:
   result=g.prepare_owned_git_v3('ordinary-a','ordinary-s','ordinary-k',self.root/'default',ACTUAL_MSGFMT)
   auth.assert_called_once();phase.assert_not_called();msg.assert_not_called()
  self.assertEqual(result['INSTALL'],'NOTRUN');self.assertEqual(result['build_runs'],0);self.assertEqual(result['SUT_runs'],0)
 def test_root_current_source_five_lease_required(self):
  with patch.object(g,'verify_git_source',return_value=self.fixture_tar()),patch.object(g,'run_owned_git_phase') as phase:
   with self.assertRaises(ValueError):g.prepare_owned_git_v3('a','s','k',self.root/'missing-source-lease',ACTUAL_MSGFMT,execute=True)
   phase.assert_not_called()
 def test_original_fullbuild480MSGFMTcheck_failure_install0(self):
  with patch.object(g,'verify_git_source',return_value=self.fixture_tar()),patch.object(g,'verify_native_build_toolchain',side_effect=self.fake_tools),patch.object(g,'run_owned_git_phase',side_effect=self.fake_phase) as phase:
   with self.assertRaises(ValueError):g.prepare_owned_git_v3('a','s','k',self.root/'failed-build',ACTUAL_MSGFMT,execute=True,current_source5=self.source_guard())
   self.assertEqual(phase.call_count,1);vector=phase.call_args.args[0]
   self.assertEqual(vector[:6],['/usr/bin/timeout','--signal=TERM','--kill-after=2s','480s','/usr/bin/make','-j2']);self.assertEqual(vector[-1],'all');self.assertTrue(vector[-2].startswith('MSGFMT='));self.assertTrue(vector[-2].endswith('--check'))
  result=json.loads((self.root/'failed-build/actual-build-install-result.json').read_text());self.assertEqual(result['INSTALL'],'NOTRUN');self.assertEqual(result['install_runs'],0);self.assertFalse(result['RC_qualification'])
 def test_partial_owned_install_honest_attempt_failed_notPASS(self):
  def phase(vector,*args,**kwargs):
   result=self.fake_phase(vector,*args,**kwargs)
   if vector[-1]=='all':
    result.update(exit=0,passed=True);artifact=Path(args[0])/'git';artifact.write_bytes(b'\x7fELF\x02\x01'+b'\x00'*12+b'\x3e\x00'+b'ordinary-header-only-not-executed');artifact.chmod(0o755)
   else:
    prefix=Path(next(x[7:] for x in vector if x.startswith('prefix=')));prefix.mkdir();(prefix/'partial').write_bytes(b'controlled owned fixture not installGit')
   return result
  with patch.object(g,'verify_git_source',return_value=self.fixture_tar()),patch.object(g,'verify_native_build_toolchain',side_effect=self.fake_tools),patch.object(g,'run_owned_git_phase',side_effect=phase) as run:
   with self.assertRaises(ValueError):g.prepare_owned_git_v3('a','s','k',self.root/'failed-install',ACTUAL_MSGFMT,execute=True,current_source5=self.source_guard())
   self.assertEqual(run.call_count,2);self.assertEqual(run.call_args.args[0][3],'60s');self.assertEqual(run.call_args.args[0][-1],'install')
  result=json.loads((self.root/'failed-install/actual-build-install-result.json').read_text());self.assertEqual(result['INSTALL'],'ATTEMPTED_OR_FAILED');self.assertTrue(result['TOOL_INSTALL_ATTEMPTED']);self.assertEqual(result['PRODUCT_INSTALL'],'NOTRUN');self.assertEqual(result['status'],'FAIL')
 def test_primary_cancel_and_final_guard_same_objects(self):
  primary=KeyboardInterrupt('REAL_ORDINARY_PRIMARY');cleanup=SystemExit('CONTROLLED_FINAL')
  actual=g.snapshot_original_git_source
  def snapshot(source,*args,**kwargs):
   if args and kwargs=={}:raise cleanup
   return actual(source,*args,**kwargs)
  with patch.object(g,'verify_git_source',return_value=self.fixture_tar()),patch.object(g,'validate_msgfmt_assignment',side_effect=primary),patch.object(g,'snapshot_original_git_source',side_effect=snapshot):
   try:g.prepare_owned_git_v3('a','s','k',self.root/'cancel-final',ACTUAL_MSGFMT,execute=True,current_source5=self.source_guard())
   except BaseException as error:self.assertIsInstance(error,BaseExceptionGroup);self.assertIs(error.exceptions[0],primary);self.assertIs(error.exceptions[1],cleanup)
   else:self.fail('Primary and final cancellation lost')
 def test_real_owned_child_exit_timeout_and_log_cap(self):
  env={'PATH':'/usr/bin:/bin'}
  ok=g.run_owned_git_phase(['/usr/bin/python3','-c','print("ordinary")'],self.root,env,self.root/'exit.log',2);self.assertTrue(ok['passed'])
  timed=g.run_owned_git_phase(['/usr/bin/python3','-c','import time;time.sleep(5)'],self.root,env,self.root/'timeout.log',.1);self.assertEqual(timed['reason'],'TIMEOUT')
  cap=g.run_owned_git_phase(['/usr/bin/python3','-c','import os;os.write(1,b"x"*(3*1024*1024))'],self.root,env,self.root/'cap.log',2);self.assertEqual(cap['reason'],'LOG_LIMIT');self.assertLessEqual(cap['log_bytes'],2*1024*1024)
 def test_managed_log_close_cancel_preserves_original(self):
  primary=KeyboardInterrupt('PHASE_CANCEL');cleanup=SystemExit('READER_CLOSE');selector=g.selectors.DefaultSelector();original=selector.close
  def close():original();raise cleanup
  with patch.object(g.selectors,'DefaultSelector',return_value=selector),patch.object(selector,'select',side_effect=primary),patch.object(selector,'close',side_effect=close):
   try:g.run_owned_git_phase(['/usr/bin/python3','-c','import time;time.sleep(5)'],self.root,{'PATH':'/usr/bin:/bin'},self.root/'cancel.log',2)
   except BaseException as error:self.assertIsInstance(error,BaseExceptionGroup);self.assertIs(error.exceptions[0],primary);self.assertIs(error.exceptions[1],cleanup)
   else:self.fail('Phase cancel/cleanup objects lost')
 def test_phase_source_guard_and_LD_env_denied_before_process(self):
  with patch.object(g.subprocess,'Popen') as popen:
   with self.assertRaises(ValueError):g.run_owned_git_phase(['/usr/bin/python3'],self.root,{'LD_LIBRARY_PATH':'bad'},self.root/'ld.log',2)
   bad=self.source_guard();bad[g.SOURCE5[0]]=dict(bad[g.SOURCE5[0]],sha256='0'*64)
   with self.assertRaises(ValueError):g.run_owned_git_phase(['/usr/bin/python3'],self.root,{},self.root/'source.log',2,source_guard=bad)
   popen.assert_not_called()

 def test_negative_PO_boolean_is_not_actual_integer_exit(self):
  m=g.load_reviewed_git_dependencies();tmp=tempfile.TemporaryDirectory(dir=m.ROOT,prefix='ordinary-negative-bool-')
  try:
   path=Path(tmp.name)/'result.json';current=copy.deepcopy(json.loads(ACTUAL_MSGFMT.read_text()));current['phases'][2]['exit']=True;path.write_text(json.dumps(current))
   with self.assertRaisesRegex(ValueError,'Exact GNU version/positive/negative'):g.validate_msgfmt_assignment(path)
  finally:tmp.cleanup()
 def test_inventory_expected_path_escape_denied(self):
  source=g.extract_owned_git_source(self.fixture_tar(),self.root/'safe')
  for name in ('../outside','/etc/passwd','a/../README'):
   with self.assertRaises(ValueError):g.snapshot_original_git_source(source,{name:{}})
 def test_source_mutation_after_controlled_build_stops_install_and_finaldeny(self):
  def phase(vector,source,*args,**kwargs):
   (Path(source)/'README').write_bytes(b'changed owned ordinary source')
   result=self.fake_phase(vector,source,*args,**kwargs);result.update(exit=0,passed=True);return result
  with patch.object(g,'verify_git_source',return_value=self.fixture_tar()),patch.object(g,'verify_native_build_toolchain',side_effect=self.fake_tools),patch.object(g,'run_owned_git_phase',side_effect=phase) as run:
   with self.assertRaises(BaseExceptionGroup):g.prepare_owned_git_v3('a','s','k',self.root/'source-mutation',ACTUAL_MSGFMT,execute=True,current_source5=self.source_guard())
   self.assertEqual(run.call_count,1)
  result=json.loads((self.root/'source-mutation/actual-build-install-result.json').read_text());self.assertEqual(result['INSTALL'],'NOTRUN');self.assertFalse(result['source_runtime_msgfmt_prefix_final_unchanged'])
 def test_mock_full_flow_INSTALL_true_only_after_correspondence_and_probes(self):
  # Header-only ELF DATA and mocked command exits/stdout: no actual ELF/run/install.
  fixture=b'\x7fELF\x02\x01'+b'\x00'*12+b'\x3e\x00'+b'ordinary-header-only-never-executed'
  def phase(vector,cwd,env,log,seconds,**kwargs):
   result=self.fake_phase(vector,cwd,env,log,seconds,**kwargs);result.update(exit=0,passed=True)
   if vector[-1]=='all':
    binary=Path(cwd)/'git';binary.write_bytes(fixture);binary.chmod(0o755)
   elif vector[-1]=='install':
    prefix=Path(next(x[7:] for x in vector if x.startswith('prefix=')));(prefix/'bin').mkdir(parents=True);(prefix/'bin/git').write_bytes(fixture);(prefix/'bin/git').chmod(0o755)
    (prefix/'libexec/git-core').mkdir(parents=True);os.link(prefix/'bin/git',prefix/'libexec/git-core/git-init');(prefix/'share/git-core/templates').mkdir(parents=True);(prefix/'share/locale').mkdir()
   else:
    prefix=Path(vector[0]).parents[1]
    value={'installed-0.log':b'git version 2.55.0\n','installed-1.log':(str(prefix/'libexec/git-core')+'\n').encode(),'installed-2.log':b'controlled mocked init\n','installed-3.log':b'e69de29bb2d1d6434b8b29ae775ad8c2e48c5391\n'}[Path(log).name]
    Path(log).write_bytes(value)
   return result
  with patch.object(g,'verify_git_source',return_value=self.fixture_tar()),patch.object(g,'verify_native_build_toolchain',side_effect=self.fake_tools),patch.object(g,'run_owned_git_phase',side_effect=phase) as run:
   result=g.prepare_owned_git_v3('a','s','k',self.root/'mock-only-full',ACTUAL_MSGFMT,execute=True,current_source5=self.source_guard())
   self.assertEqual(run.call_count,6)
  self.assertIs(result['INSTALL'],True);self.assertEqual(result['built_binary']['sha256'],result['installed_binary']['sha256']);self.assertEqual(result['PRODUCT_INSTALL'],'NOTRUN');self.assertEqual(result['SUT_runs'],0);self.assertFalse(result['RC_qualification'])
 def test_installed_payload_capacity_distinct_from_source_64MiB(self):
  self.assertEqual(g.MAX_TAR,64*1024*1024);self.assertEqual(g.MAX_INSTALL,256*1024*1024)
  prefix=self.root/'capacity';prefix.mkdir();(prefix/'body').write_bytes(b'1234')
  with patch.object(g,'MAX_INSTALL',3):
   with self.assertRaises(ValueError):g.snapshot_original_git_source(prefix,installed=True)

 def test_real_toolchain_cannot_shadow_original_systemGit_role(self):
  # Own DATA collision fixture; never create a shim in actual/shared toolchain.
  directory=self.root/'controlled-tc';directory.mkdir();(directory/'git').write_bytes(b'CONTROL_ONLY_NOT_EXECUTABLE')
  with patch.object(g,'TOOLCHAIN',directory),patch.object(g.subprocess,'run') as run:
   with self.assertRaisesRegex(ValueError,'shadows original'):g.verify_native_build_toolchain(self.root/'tool-env')
   run.assert_not_called()

if __name__=='__main__':unittest.main(verbosity=2)
