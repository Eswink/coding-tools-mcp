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
    root = dict(path='/tmp/.mount_fixture',identity=[2049,500]) if kind == 'appimage' else None
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
        env = {} if root is None else dict(APPDIR=root['path'],LD_LIBRARY_PATH=root['path']+'/usr/lib:'+root['path']+'/usr/lib/x86_64-linux-gnu',GIO_MODULE_DIR=root['path']+'/usr/lib/x86_64-linux-gnu/gio/modules',GIO_EXTRA_MODULES=root['path']+'/usr/lib/x86_64-linux-gnu/gio/modules')
        samples.append(dict(stage='fixture',before=copy.deepcopy(process),after=copy.deepcopy(process),raw_maps=raw,
                            observed=[dict(category='ELF',file=str(index))],executable=[str(index)],environment=env,package_root=root,monotonic=1,wall=1))
    # Startup anchor is the desktop; the synthetic driver is native-only.
    if phase.startswith('startup'):
        processes = processes[1:]; samples = samples[1:]; del files['0']
        processes[0].pop('ancestor'); processes[0]['parent'] = 1
        for process in processes[1:]: process['ancestor'] = [11,1100]; process['parent'] = 11
    receipt = dict(schema=runtime.SCHEMA,binding=binding,phase=phase,launch_environment={},anchor=processes[0],processes=processes,
                   files=files,samples=samples,errors=[],cleanup_completed=True,claims=dict(runtime.FALSE_CLAIMS),host=dict(uid=1000,architecture='x86_64',os_release='ID=ubuntu\nVERSION_ID=24.04\n'),
                   raw_bytes=sum(len(s['raw_maps'].encode()) for s in samples),hash_bytes=10*len(files))
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
        workflow = WORKFLOW.read_text()
        self.assertIn('for scenario in missing-bus unlocked-keyring split-session-bus safe-mode; do',workflow)
        self.assertIn('--case "$scenario" --seconds 20',workflow)
        self.assertLess(workflow.index('scripts/linux_startup_candidate.py'),workflow.index('sudo apt-get install -y webkit2gtk-driver'))
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
            receipt['raw_bytes'] = sum(len(s['raw_maps'].encode()) for s in receipt['samples'])
            del receipt['files'][missing]; receipt['hash_bytes'] -= 10
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                runtime.verify_receipt(receipt,binding,receipt['phase'])
        binding, receipt = receipt_fixture()
        receipt['processes'].append(dict(pid=99,start=999,ancestor=[receipt['anchor']['pid'],receipt['anchor']['start']]))
        with self.assertRaisesRegex(ValueError,'retained process identity was not sampled'):
            runtime.verify_receipt(receipt,binding,receipt['phase'])
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
        binding, receipt = receipt_fixture(); receipt['errors'] = ['inaccessible helper']
        with self.assertRaisesRegex(ValueError,'incomplete'): runtime.verify_receipt(receipt,binding,receipt['phase'])


if __name__ == '__main__': unittest.main(verbosity=2)
