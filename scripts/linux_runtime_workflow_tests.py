"""Installed matrix preservation and data-only receipt rejection controls."""
import ast
import copy
import inspect
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import linux_runtime_provenance as runtime
import linux_runtime_provenance_tests as fixtures
import exclusive_native_acceptance as native

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/linux-rc-packages.yml'


def launch_projection(binding, phase, harness=None):
    harness = {} if harness is None else harness
    original = dict(harness); omission = binding['python_loader_omission']
    if omission['input'] is not None: original['LD_LIBRARY_PATH'] = omission['original_ld_library_path']
    digest = fixtures.hashlib.sha256(json.dumps(binding,sort_keys=True,ensure_ascii=True,separators=(',',':'),allow_nan=False).encode('ascii')).hexdigest()
    return dict(schema='linux-harness-projection-v1',phase='native' if phase in ('native-1','native-2') else phase,
                binding_sha256=digest,omission=omission,original=original,projected=harness)


def receipt_fixture(phase='startup-missing-bus', kind='deb'):
    binding = fixtures.binding([dict(path=runtime.MAIN,sha256='1'*64,size=10)], kind=kind)
    processes, files, samples = [], {}, []
    root = dict(path='/tmp/.mount_fixture',identity=[2049,500],kind='appimage') if kind == 'appimage' else None
    paths = ['/usr/bin/tauri-driver','/'+runtime.MAIN,'/usr/lib/WebKitWebProcess','/usr/lib/WebKitNetworkProcess']
    for index, path in enumerate(paths):
        if index == 1 and root: path = root['path'] + path
        inode, pid = index + 1000, index + 10
        value = dict(identity=[2049,inode,10,1,1],sha256=str(index)*64,size=10,path=path)
        value['origin'] = runtime.package_origin(path,value,binding,root)
        if index == 0: value['origin'] = dict(kind='owned-driver',members=[],equivalent_members=[])
        if index >= 2: value['owner'] = dict(phase=phase,ownership='webkit: '+path,versions='webkit\t1\tamd64\twebkit\t1',official_archive_byte_origin=False)
        process = dict(pid=pid,start=pid*100,parent=1 if index==0 else 10,executable=value['identity'],executable_path=path)
        if index: process['ancestor'] = [10,1000]
        processes.append(process); files[str(index)] = value
        raw = f'1000-2000 r-xp 0 {os.major(2049):02x}:{os.minor(2049):02x} {inode} {path}\n'
        env = {} if root is None else dict(APPDIR=root['path'],GTK_PATH=root['path']+'//usr/lib/gtk-3.0',LD_LIBRARY_PATH=root['path']+'/usr/lib:'+root['path']+'/usr/lib/x86_64-linux-gnu',GIO_MODULE_DIR=root['path']+'/usr/lib/x86_64-linux-gnu/gio/modules',GIO_EXTRA_MODULES=root['path']+'/usr/lib/x86_64-linux-gnu/gio/modules')
        samples.append(dict(stage='fixture',before=copy.deepcopy(process),after=copy.deepcopy(process),raw_maps=raw,
                            observed=[dict(category='ELF',file=str(index))],executable=[str(index)],environment=env,package_root=root,monotonic=1.2,wall=1,
                            status='complete',attempt=0,raw_after=raw,pid=pid))
    # Startup anchor is the desktop; the synthetic driver is native-only.
    if phase.startswith('startup'):
        processes = processes[1:]; samples = samples[1:]; del files['0']
        processes[0].pop('ancestor'); processes[0]['parent'] = 1
        for process in processes[1:]: process['ancestor'] = [11,1100]; process['parent'] = 11
        for sample,process in zip(samples,processes): sample.update(before=copy.deepcopy(process),after=copy.deepcopy(process))
    receipt = dict(schema=runtime.SCHEMA,binding=binding,phase=phase,launch_environment={},anchor=processes[0],processes=processes,
                   files=files,samples=samples,errors=[],cleanup_completed=True,claims=dict(runtime.FALSE_CLAIMS),host=dict(uid=1000,architecture='x86_64',os_release='ID=ubuntu\nVERSION_ID=24.04\n'),
                   raw_bytes=sum(len(s[k].encode()) for s in samples for k in ('raw_maps','raw_after')),hash_bytes=10*len(files),
                   ready='native-ready' if phase.startswith('native') else 'first-window',required=[[p['pid'],p['start']] for p in processes],
                   bootstrap=[],ready_at=1.0,discovery=[dict(p,monotonic=1.1) for p in processes],requests=[dict(stage='native-ready' if phase.startswith('native') else 'first-window',monotonic=1.0),dict(stage='before-cleanup',monotonic=2)],
                   progress=dict(stage='fixture',pid=None,operation='idle'),hash_reads=[dict(identity=v['identity'],bytes=v['size'],complete=True,sha256=v['sha256']) for v in files.values()])
    receipt.update(projection=launch_projection(binding,phase),harness_environment={})
    return binding, receipt


class InstalledWorkflowTests(unittest.TestCase):
    def test_exact_four_os_kind_rows_and_existing_job_conditions_remain(self):
        workflow = WORKFLOW.read_text()
        self.assertIn('os: [ubuntu-22.04, ubuntu-24.04]',workflow)
        self.assertIn('kind: [deb, appimage]',workflow)
        self.assertIn("if: always() && needs.build.outputs.packages_ready == 'true'",workflow)
        self.assertIn("if: always() && steps.prerequisites.outcome == 'success'",workflow)
        self.assertIn('cargo test --no-fail-fast --manifest-path src-tauri/Cargo.toml --locked',workflow)
        self.assertIn('fail-fast: false',workflow)
        self.assertIn('python -B scripts/rc_pretag_linux_package_cases.py',workflow)
        lines = workflow.splitlines()
        for index, line in enumerate(lines):
            indent = len(line) - len(line.lstrip())
            if line.strip() == 'env:' and indent <= 4:
                block = []
                for following in lines[index+1:]:
                    if following.strip() and len(following)-len(following.lstrip()) <= indent: break
                    block.append(following)
                self.assertNotIn('runner.temp', '\n'.join(block))
        for job in workflow.split('    steps:\n')[1:]:
            self.assertTrue(job.startswith('      - name: Set external evidence paths\n'))
            initialization = job.split('      - uses:',1)[0]
            self.assertIn('EVIDENCE_DIRECTORY=%s/linux-rc-evidence',initialization)
            self.assertIn('"$RUNNER_TEMP" >> "$GITHUB_ENV"',initialization)
            self.assertLess(job.index('GITHUB_ENV'),job.index('"$EVIDENCE_DIRECTORY"'))
        installed = workflow.split('  installed:',1)[1].split('      - uses:',1)[0]
        self.assertIn('LINUX_PACKAGE_PROVENANCE_BINDING=%s/linux-rc-evidence/provenance-binding.json',installed)
        rows = {(os_name,kind) for os_name in ('ubuntu-22.04','ubuntu-24.04') for kind in ('deb','appimage')}
        self.assertEqual(len(rows),4)

    def test_all_four_startup_cases_keep_twenty_seconds_before_driver_install(self):
        workflow = WORKFLOW.read_text().split('\n  installed:',1)[1]
        self.assertIn('for scenario in missing-bus unlocked-keyring split-session-bus safe-mode; do',workflow)
        self.assertIn('--case "$scenario" --seconds 20',workflow)
        self.assertLess(workflow.index('scripts/linux_startup_candidate.py'),workflow.index('sudo apt-get install -y webkit2gtk-driver'))
        prerequisites = 'sudo apt-get install -y xvfb xauth x11-utils fonts-noto-cjk desktop-file-utils gnome-keyring dbus-x11 xdg-desktop-portal xdg-desktop-portal-gtk libayatana-appindicator3-1 libsecret-1-0 libxdo3 libfuse2 libegl-mesa0'
        self.assertEqual(workflow.count(prerequisites),1)
        self.assertLess(workflow.index(prerequisites),workflow.index('scripts/linux_startup_candidate.py'))
        self.assertEqual(workflow.count('sudo apt-get install -y webkit2gtk-driver'),1)
        self.assertIn("failed to load app state|panic",workflow)
        self.assertIn('touch "$HOME/.linux-startup-disposable"',workflow)
        self.assertIn('xvfb-run -a',workflow); self.assertIn('dbus-run-session',workflow)
        source = inspect.getsource(fixtures.startup.main)
        self.assertLess(source.index('observer = runtime.configured'),source.index('start_runtime_user_bus(env, output)'))
        self.assertEqual(workflow.count('unset LD_LIBRARY_PATH'),2)
        self.assertEqual(workflow.count('project-harness-input --binding'),2)

    def test_all_twelve_native_stages_restart_and_real_deadline_remain(self):
        source = inspect.getsource(native.run); tree = ast.parse(source)
        passed = [n.args[0].value for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='passed']
        self.assertEqual(passed,list(range(12))); self.assertEqual(len(native.TEST_NAMES),12)
        self.assertIn('range(100)',source); self.assertIn('90.2 - (time.monotonic() - start)',source)
        self.assertIn('session.close(); session = None',source)
        self.assertEqual(source.count('session = adapter.session('),2)
        for name in ('native-session-settings.png','native-approval-modal.png','native-background-inbox.png','native-restart-without-grant.png'):
            self.assertIn(name,source)
        self.assertIn('scan_export(output, sensitive)',source)
        self.assertIn("permission_approval_source': 'native-webdriver-clicks'",source)
        fixtures.shared.check_final_epoch(self,receipt_fixture)


    def test_runtime_package_source_attempt_os_kind_and_envelope_mismatches_reject(self):
        binding, receipt = receipt_fixture(); runtime.verify_receipt(receipt,binding,receipt['phase'])
        for key in ('source_sha','source_tree','run_id','run_attempt','os','kind','package','envelope_sha256','artifact_id','artifact_digest'):
            changed = copy.deepcopy(receipt); changed['binding'][key] = 'wrong'
            with self.subTest(key=key), self.assertRaisesRegex(ValueError,'binding mismatch'):
                runtime.verify_receipt(changed,binding,receipt['phase'])
        for key in runtime.FALSE_CLAIMS:
            changed = copy.deepcopy(receipt); changed['claims'][key] = True
            with self.subTest(claim=key), self.assertRaises(ValueError): runtime.verify_receipt(changed,binding,receipt['phase'])

    def test_missing_primary_or_helper_observation_is_not_an_empty_success(self):
        for missing in ('1','2','3'):
            binding, receipt = receipt_fixture()
            receipt['samples'] = [s for s in receipt['samples'] if missing not in s['executable']]
            receipt['raw_bytes'] = sum(len(s[k].encode()) for s in receipt['samples'] for k in ('raw_maps','raw_after'))
            del receipt['files'][missing]; receipt['hash_bytes'] -= 10
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                runtime.verify_receipt(receipt,binding,receipt['phase'])
        binding, receipt = receipt_fixture()
        receipt['processes'].append(dict(pid=99,start=999,ancestor=[receipt['anchor']['pid'],receipt['anchor']['start']]))
        receipt['required'].append([99,999]); receipt['discovery'].append(dict(receipt['processes'][-1],monotonic=1.1))
        with self.assertRaisesRegex(ValueError,'(retained|required|epoch).*not sampled'):
            runtime.verify_receipt(receipt,binding,receipt['phase'])
        for phase,missing in (('startup-missing-bus','1'),('startup-missing-bus','2'),('startup-missing-bus','3'),('native-1','0')):
            binding, receipt = receipt_fixture(phase); missed = next(s['before'] for s in receipt['samples'] if missing in s['executable'])
            receipt['bootstrap'].append(dict(missed,monotonic=.5)); receipt['required'].remove([missed['pid'],missed['start']])
            next(p for p in receipt['discovery'] if p['pid']==missed['pid'])['monotonic'] = .5; receipt['discovery'].sort(key=lambda e:e['monotonic'])
            receipt['samples'] = [s for s in receipt['samples'] if missing not in s['executable']]; del receipt['files'][missing]
            receipt['hash_reads'] = [r for r in receipt['hash_reads'] if r['identity'] != missed['executable']]
            receipt['raw_bytes'] = sum(len(s[k].encode()) for s in receipt['samples'] for k in ('raw_maps','raw_after')); receipt['hash_bytes'] -= 10
            with self.subTest(bootstrap_cannot_waive=missing),self.assertRaisesRegex(ValueError,'unaccounted process epoch|missing .*observation'):
                runtime.verify_receipt(receipt,binding,phase)
        binding, receipt = receipt_fixture(); bootstrap = dict(pid=99,start=999,parent=receipt['anchor']['pid'],ancestor=[receipt['anchor']['pid'],receipt['anchor']['start']],executable=[2049,999,10,1,1],executable_path='/bin/bash')
        receipt['processes'].append(bootstrap); receipt['bootstrap'].append(dict(bootstrap,monotonic=.5)); receipt['discovery'].append(dict(bootstrap,monotonic=.5)); receipt['discovery'].sort(key=lambda e:e['monotonic'])
        self.assertTrue(runtime.verify_receipt(receipt,binding,receipt['phase'])['sampled_backing_files_verified'])
        self.assertFalse(runtime.verify_receipt(receipt,binding,receipt['phase'])['complete_lifetime_closure'])
        initial = copy.deepcopy(receipt['anchor']); initial['executable'] = [2049,77,20,1,1]; initial['executable_path'] = '/tmp/product.AppImage'
        receipt['anchor'] = initial; receipt['processes'][0] = initial; receipt['bootstrap'].append(dict(initial,monotonic=.5)); receipt['discovery'].append(dict(initial,monotonic=.5)); receipt['discovery'].sort(key=lambda e:e['monotonic'])
        self.assertTrue(runtime.verify_receipt(receipt,binding,receipt['phase'])['sampled_backing_files_verified'])
        self.assertNotEqual(receipt['bootstrap'][-1]['executable'],receipt['samples'][0]['before']['executable'])
        result = runtime.verify_receipt(receipt,binding,receipt['phase'])
        self.assertEqual(result['bootstrap_unobserved_versions'],2); self.assertEqual(result['bootstrap_unobserved_processes'],1)

        for change in (lambda r:r.update(ready=None),lambda r:r['required'].append([99,999]),lambda r:r.update(samples=[])):
            changed = copy.deepcopy(receipt); change(changed)
            with self.assertRaises(ValueError): runtime.verify_receipt(changed,binding,receipt['phase'])
        binding, receipt = receipt_fixture(kind='appimage')
        self.assertTrue(runtime.verify_receipt(receipt,binding,receipt['phase'])['sampled_backing_files_verified'])
        changed = copy.deepcopy(receipt); changed['samples'][0]['environment']['GIO_MODULE_DIR'] = '/host/modules'
        with self.assertRaisesRegex(ValueError,'environment disagreement'): runtime.verify_receipt(changed,binding,receipt['phase'])
        changed = copy.deepcopy(receipt); changed['samples'][0]['environment']['LD_PRELOAD'] = '/unknown.so'
        with self.assertRaisesRegex(ValueError,'loader override'): runtime.verify_receipt(changed,binding,receipt['phase'])
        loader = fixtures.python_loader(); loader['library_directory']['mode'] = 0o40777
        binding['python_loader_omission'].update(input=loader,original_ld_library_path=loader['library_path'])
        receipt['projection'] = launch_projection(binding,receipt['phase'],{'GDK_BACKEND':'x11'})
        receipt['harness_environment'] = {'GDK_BACKEND':'x11'}
        entry = fixtures.inspect.getmodule(runtime.validate_environment)
        with self.assertRaises(ValueError): entry.setup_python_library(loader)
        with patch.object(runtime.os,'stat',side_effect=AssertionError('replay must not stat producer paths')):
            self.assertTrue(runtime.verify_receipt(receipt,binding,receipt['phase'])['sampled_backing_files_verified'])
        for field, value in (('binding_sha256','0'*64),('phase','native'),('projected',{'LD_LIBRARY_PATH':loader['library_path']})):
            changed = copy.deepcopy(receipt); changed['projection'][field] = value
            with self.subTest(projection=field), self.assertRaises(ValueError): runtime.verify_receipt(changed,binding,receipt['phase'])
        for place in ('launch_environment','harness_environment'):
            changed = copy.deepcopy(receipt); changed[place]['LD_LIBRARY_PATH'] = loader['library_path']
            with self.subTest(reappearance=place), self.assertRaises(ValueError): runtime.verify_receipt(changed,binding,receipt['phase'])
        changed = copy.deepcopy(receipt); changed['samples'][0]['environment']['LD_LIBRARY_PATH'] += ':'+loader['library_path']
        with self.assertRaises(ValueError): runtime.verify_receipt(changed,binding,receipt['phase'])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'binding.json'; path.write_text(json.dumps(binding))
            proof = path.with_name(receipt['phase']+'-launch-projection.json'); proof.write_text(json.dumps(receipt['projection']))
            with patch.dict(os.environ,{'LINUX_PACKAGE_PROVENANCE_BINDING':str(path),'GDK_BACKEND':'x11'},clear=True):
                observer = runtime.configured(Path(directory)/'receipt.json',receipt['phase'],{})
                self.assertEqual(observer.launch_environment,{}); self.assertEqual(observer.projection,receipt['projection'])
                with fixtures.subprocess.Popen(['/usr/bin/sleep','30']) as child:
                    observer.attach(child); observer.checkpoint('before-cleanup')
                    child.terminate(); child.wait(timeout=5); observer.finish(True)
                captured = json.loads((Path(directory)/'receipt.json').read_text())
                self.assertEqual(captured['projection'],receipt['projection'])
                self.assertEqual(captured['harness_environment'],{'GDK_BACKEND':'x11'})
                with patch.dict(os.environ,{'LD_LIBRARY_PATH':loader['library_path']}), self.assertRaises(ValueError): runtime.configured(Path(directory)/'bad.json',receipt['phase'],{})
                proof.unlink()
                with self.assertRaises(FileNotFoundError): runtime.configured(Path(directory)/'missing.json',receipt['phase'],{})



    def test_each_matrix_artifact_is_required_without_cross_row_substitution(self):
        workflow = WORKFLOW.read_text()
        self.assertIn('artifact-ids: ${{ needs.build.outputs.package_artifact_id }}',workflow)
        downloads = workflow.split('- uses: actions/download-artifact@v4')[1:]
        self.assertEqual(len(downloads),3)
        for download in downloads:
            self.assertIn('merge-multiple: true',download.split('      - ',1)[0])
        self.assertIn('linux-rc-installed-${{ matrix.os }}-${{ matrix.kind }}-${{ github.sha }}',workflow)
        self.assertIn('--run-attempt "$GITHUB_RUN_ATTEMPT"',workflow)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            phases = ['startup-'+case for case in ('missing-bus','unlocked-keyring','split-session-bus','safe-mode')] + ['native-1','native-2']
            for phase in phases:
                binding, receipt = receipt_fixture(phase)
                path = root/phase/'runtime-provenance.json' if phase.startswith('startup') else root/('runtime-provenance-'+phase[-1]+'.json')
                path.parent.mkdir(exist_ok=True); path.write_text(json.dumps(receipt))
            expected = {key:binding[key] for key in ('source_sha','run_id','run_attempt','os','kind')}
            result = runtime.verify_directory(binding,root,expected); self.assertEqual(len(result['sessions']),6)
            with self.assertRaises(ValueError): runtime.verify_directory(binding,root,{**expected,'os':'ubuntu-22.04'})
            (root/'runtime-provenance-2.json').unlink()
            with self.assertRaises(FileNotFoundError): runtime.verify_directory(binding,root,expected)

    def test_independent_replay_occurs_after_existing_native_behavior(self):
        workflow = WORKFLOW.read_text()
        native_gate = workflow.index('scripts/rc_native_gate.py')
        runtime_gate = workflow.index('scripts/linux_runtime_provenance.py verify')
        replay = workflow.index('scripts/desktop_glib_build_evidence.py verify-linux')
        self.assertLess(native_gate,runtime_gate); self.assertLess(runtime_gate,replay)
        self.assertIn("if: matrix.os == 'ubuntu-24.04' && matrix.kind == 'deb'",workflow)
        self.assertIn('artifact-ids: ${{ needs.build.outputs.evidence_artifact_id }}',workflow)
        self.assertIn('--expected-envelope-sha256',workflow)

    def test_failure_evidence_uploads_without_publication_or_security_approval(self):
        workflow = WORKFLOW.read_text(); last_upload = workflow[workflow.rindex('- uses: actions/upload-artifact@v4'):]
        self.assertIn('if: always()',last_upload); self.assertIn('if-no-files-found: error',last_upload)
        self.assertIn('contents: read',workflow); self.assertNotIn('contents: write',workflow)
        self.assertNotIn('gh release',workflow); self.assertNotIn('no-sandbox',workflow)
        self.assertFalse(any(runtime.FALSE_CLAIMS.values()))
        with patch.object(runtime,'process_identity',side_effect=AssertionError('data-only verifier must not inspect producer proc')):
            binding, receipt = receipt_fixture(); runtime.verify_receipt(receipt,binding,receipt['phase'])
        binding, receipt = receipt_fixture()
        for name in ('/SYSV00000000 (deleted)','/memfd:WebKitSharedMemory (deleted)'):
            changed = copy.deepcopy(receipt); sample = changed['samples'][0]
            raw = f'2000-3000 rw-s 0 00:01 999 {name}\n'
            sample['raw_maps'] += raw; sample['raw_after'] += raw
            sample['observed'].append(dict(category='shared-memory',bytes_verified=False)); changed['raw_bytes'] += 2*len(raw.encode())
            self.assertTrue(runtime.verify_receipt(changed,binding,changed['phase'])['sampled_backing_files_verified'])
            for old,new in (('rw-s','r-xs'),('rw-s','rw-p'),('00:01','00:02'),(name,'/other (deleted)')):
                forged = copy.deepcopy(changed)
                for key in ('raw_maps','raw_after'): forged['samples'][0][key] = forged['samples'][0][key].replace(old,new)
                forged['raw_bytes'] = sum(len(s[k].encode()) for s in forged['samples'] for k in ('raw_maps','raw_after'))
                with self.subTest(shared_memory_forgery=new),self.assertRaises(ValueError): runtime.verify_receipt(forged,binding,forged['phase'])
            changed['samples'][0]['observed'][-1]['bytes_verified'] = True
            with self.assertRaises(ValueError): runtime.verify_receipt(changed,binding,changed['phase'])
        retried = copy.deepcopy(receipt); failed = copy.deepcopy(retried['samples'][0])
        failed.update(status='retry',reason='mapping changed during hash',raw_after='1000-2000 rw-p 0 00:00 0\n',executable=[])
        retried['samples'][0]['attempt'] = 1; retried['samples'].insert(0,failed)
        retried['raw_bytes'] = sum(len(s[k].encode()) for s in retried['samples'] for k in ('raw_maps','raw_after'))
        self.assertTrue(runtime.verify_receipt(retried,binding,retried['phase'])['sampled_backing_files_verified'])
        for mutate in (lambda r:r['samples'].pop(1),lambda r:r['samples'][0].update(reason='permission denied'),lambda r:r['samples'][1].update(attempt=0),
            lambda r:r['samples'][0].update(reason='process executable changed during sample'),
            *[lambda r,k=k:r['samples'][0].update(reason='process executable changed during sample',after=dict(r['samples'][0]['after'],**{k:999},executable=[2049,999,10,1,1])) for k in ('pid','start')],
            lambda r:r['samples'][0]['observed'][0].update(category='unresolved',reason='hash read limit')):
            exhausted = copy.deepcopy(retried); mutate(exhausted)
            with self.assertRaises(ValueError): runtime.verify_receipt(exhausted,binding,exhausted['phase'])
        exited = copy.deepcopy(receipt); exited['samples'].append(dict(exited['samples'][0],status='unknown',reason='exited-after-observation',before=None,after=None,raw_maps='',raw_after='',observed=[],executable=[],monotonic=1.5))
        self.assertTrue(runtime.verify_receipt(exited,binding,exited['phase'])['sampled_backing_files_verified'])
        for field,value in (('raw_after','1000-2000 rw-p 0 00:00 0\n'),('observed',[dict(category='kernel')]),('monotonic',.5)):
            changed = copy.deepcopy(exited); changed['samples'][-1][field] = value
            with self.assertRaises(ValueError): runtime.verify_receipt(changed,binding,changed['phase'])
        for mutate in (lambda r:r['requests'].reverse(),lambda r:r['requests'][0].update(monotonic=float('nan')),
            lambda r:r['requests'][-1].update(monotonic=0),lambda r:r['discovery'][0].update(monotonic=1.3),lambda r:r['discovery'][-1].update(monotonic=1.3),lambda r:r['samples'][0].update(monotonic=.5),
            lambda r:(r['required'].remove([12,1200]),r['bootstrap'].append(dict(r['discovery'][1]))),
            *[lambda r,v=v:(r['hash_reads'].append(dict(identity=r['files']['1']['identity'],bytes=v,complete=False,sha256=None)),r.update(hash_bytes=r['hash_bytes']+v)) for v in (-1,True)],
            lambda r:r.update(raw_bytes=r['raw_bytes']-1),lambda r:r.update(hash_bytes=r['hash_bytes']-1),
            lambda r:r['hash_reads'][0].update(complete=False),lambda r:r['hash_reads'][0].update(sha256='f'*64),
            lambda r:r['samples'][0].update(status='unknown'),lambda r:r['samples'][0].update(attempt=2),
            lambda r:r['files'].update(unreferenced=copy.deepcopy(r['files']['1']))):
            changed = copy.deepcopy(receipt); mutate(changed)
            with self.assertRaises(ValueError): runtime.verify_receipt(changed,binding,changed['phase'])
        binding, receipt = receipt_fixture(); receipt['errors'] = ['inaccessible helper']
        with self.assertRaisesRegex(ValueError,'incomplete'): runtime.verify_receipt(receipt,binding,receipt['phase'])


if __name__ == '__main__': unittest.main(verbosity=2)
