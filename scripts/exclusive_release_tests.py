"""Synthetic release-gate unit tests, never evidence of installed execution."""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import exclusive_release as release
import exclusive_release_evidence as evidence
from exclusive_native_contract_tests import record as native_record
from 发布资产v8 import GitHub

SOURCE, TREE, VERSION, RUN = 'a'*40, 'b'*40, '0.4.0', '123'
REPO = Path(__file__).resolve().parents[1]


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')


def fixture(root):
    base = dict(source_sha=SOURCE, source_tree=TREE, version=VERSION, run_id=RUN, passed=True)
    source = root / 'exclusive-source'; source.mkdir()
    (source/'source.txt').write_text(SOURCE); (source/'tree.txt').write_text(TREE)
    for system, count in [('windows-latest', 428), ('ubuntu-latest', 417)]:
        folder = root / f'exclusive-regression-{system}'; folder.mkdir()
        (folder/'source.txt').write_text(SOURCE)
        (folder/'rust-tests.txt').write_text(''.join(f'test synthetic::{n} ... ok\n' for n in range(count)) +
            f'test result: ok. {count} passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 1s\n')
        for name in ['rust-check.txt','production-warnings.txt']: (folder/name).write_text('Finished dev profile\n')
        (folder/'frontend-check.txt').write_text('svelte-check found 0 errors and 0 warnings\n')
        (folder/'frontend-build.txt').write_text('built in 1s\n')
        (folder/'frontend-tests.txt').write_text('TAP version 13\n' + ''.join(f'ok {n} - synthetic {n}\n' for n in range(1,140)) +
            '1..139\n# tests 139\n# suites 0\n# pass 139\n# fail 0\n# cancelled 0\n# skipped 0\n# todo 0\n# duration_ms 1.0\n')
    contracts=root/'exclusive-release-contracts'; contracts.mkdir(); (contracts/'source.txt').write_text(SOURCE)
    for file,count in [('native-contracts.txt',14),('release-contracts.txt',18),('asset-transport-contracts.txt',20)]:
        (contracts/file).write_text(f'Ran {count} tests in 1.0s\n\nOK\n')
    base_dir = root/'exclusive-failure-first'; base_dir.mkdir()
    (base_dir/'baseline-sha.txt').write_text('a0551c447712104e2c2cb253d3d8a5a966518580')
    (base_dir/'failure-first.txt').write_text('UNIT ONLY: occupied workspace must not create B pending; 1 failed\n')
    names = [n.args[0].value for n in ast.walk(ast.parse((REPO/'tests/exclusive-ui-browser.py').read_text()))
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id=='done']
    write(root/'exclusive-browser/exclusive-evidence/browser-results.json', dict(status='passed', passed=12, failure=None,
        page_errors=[], native_notifications_verified=False, tests=[dict(test=n,status='passed') for n in names]))
    paths = {'chat-authorization':'src/lib/chat-authorization.ts', 'remote-session-policy':'src/lib/remote-session-policy.ts',
             'ChatAuthorizationHost':'src/lib/components/ChatAuthorizationHost.svelte', 'RemoteSessionSettings':'src/lib/components/RemoteSessionSettings.svelte'}
    write(root/'exclusive-browser/exclusive-ui/source-manifest.json', {'sources': {k:hashlib.sha256((REPO/p).read_bytes()).hexdigest() for k,p in paths.items()}})
    write(root/'exclusive-browser/exclusive-evidence/readiness-results.json', {'status':'passed', 'tests':[
        {'callback':n,'baseline':'side effect and timeout reproduced','candidate':'readiness is side-effect-free; explicit decision required'} for n in ('releaseConfirm','releaseSave')]})
    def package(folder,name):
        folder.mkdir(parents=True, exist_ok=True); file=folder/name; file.write_bytes(('SYNTHETIC UNIT FIXTURE '+name).encode())
        return dict(name=name,size=file.stat().st_size,sha256=hashlib.sha256(file.read_bytes()).hexdigest())
    def native(folder,kind,digest):
        doc = native_record(); doc.update(package_kind=kind,binary_sha256=digest)
        write(folder/evidence.NATIVE,doc)
    packages={}
    for kind,ext in [('deb','.deb'),('appimage','.AppImage')]:
        item=package(root/'exclusive-ubuntu-packages',f'MCP_{VERSION}_amd64{ext}')
        packages[kind]=dict(artifact=item,payload_sha256='c'*64,architecture='amd64')
        for system in ['ubuntu-22.04','ubuntu-24.04']:
            folder=root/f'exclusive-installed-{system}-{kind}'; digest=item['sha256'] if kind=='appimage' else 'c'*64
            write(folder/evidence.MANIFEST,dict(base,kind=kind,package=item,payload_sha256='c'*64,native_executable_sha256=digest))
            native(folder,kind,digest)
    write(root/'exclusive-ubuntu-packages'/evidence.MANIFEST,dict(base,build_kind='release-packaged',packages=packages))
    folder=root/'exclusive-windows-package'
    item=package(folder,f'MCP_{VERSION}_x64-setup.exe')
    write(folder/evidence.MANIFEST,dict(base,scenario='exclusive-refresh-v1',kind='nsis',package=item,payload_sha256='d'*64,
        native_executable_sha256='d'*64,silent_install=True,exact_nsis_payload_verified=True,real_native_approval=True,real_chatgpt_verified=False,signed=False))
    native(folder,'nsis','d'*64)


class Gates(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)/'collected'; self.root.mkdir(); fixture(self.root)
    def tearDown(self): self.tmp.cleanup()
    def verify(self,**change):
        fields=dict(source=SOURCE,tree=TREE,version=VERSION,run_id=RUN); fields.update(change)
        return evidence.verify_all(self.root,REPO,**fields)
    def change(self,path,fn):
        file=self.root/path; value=evidence.load(file); fn(value); write(file,value)
    def test_complete_unit_matrix_retains_unverified_boundaries(self):
        files,summary,_=self.verify(); self.assertEqual(len(files),3); self.assertTrue(summary['artifact_gates_passed'])
        self.assertEqual(len(summary['ubuntu']),4); self.assertFalse(summary['real_chatgpt_verified']); self.assertFalse(summary['os_toast_visibility_verified'])
        self.assertEqual(summary['windows']['native_stages'],12)
    def test_wrong_source_tree_run_and_version(self):
        for key,value in [('source','f'*40),('tree','f'*40),('run_id','124'),('version','0.4.1')]:
            with self.subTest(key=key),self.assertRaises(ValueError): self.verify(**{key:value})
    def test_missing_linux_combination(self):
        (self.root/'exclusive-installed-ubuntu-24.04-appimage'/evidence.NATIVE).unlink()
        with self.assertRaises(ValueError): self.verify()
    def test_windows_deferral_rejected(self):
        self.change('exclusive-windows-package/'+evidence.MANIFEST,lambda d:d.update(real_native_approval=False))
        with self.assertRaises(ValueError): self.verify()
    def test_cross_run_install_and_wrong_bytes(self):
        self.change('exclusive-installed-ubuntu-22.04-deb/'+evidence.MANIFEST,lambda d:d.update(run_id='124'))
        with self.assertRaises(ValueError): self.verify()
    def test_wrong_package_bytes(self):
        (self.root/f'exclusive-windows-package/MCP_{VERSION}_x64-setup.exe').write_bytes(b'tampered')
        with self.assertRaises(ValueError): self.verify()
    def test_old_native_scenario_and_failure(self):
        self.change('exclusive-windows-package/'+evidence.NATIVE,lambda d:d.update(scenario='legacy'))
        with self.assertRaises(ValueError): self.verify()
    def test_no_fake_native_approval(self):
        self.change('exclusive-windows-package/'+evidence.NATIVE,lambda d:d.update(permission_approval_source='mock-ipc'))
        with self.assertRaises(ValueError): self.verify()
    def test_no_ignored_or_filtered_rust(self):
        path=self.root/'exclusive-regression-windows-latest/rust-tests.txt'; original=path.read_text()
        for old,new in [('0 ignored','1 ignored'),('0 filtered out','1 filtered out'),('0 failed','1 failed')]:
            path.write_text(original.replace(old,new))
            with self.subTest(field=old),self.assertRaises(ValueError): self.verify()
    def test_truncated_rust_results_rejected(self):
        path=self.root/'exclusive-regression-windows-latest/rust-tests.txt'; path.write_text(path.read_text().replace('test synthetic::0 ... ok\n',''))
        with self.assertRaises(ValueError): self.verify()
    def test_frontend_failure_rejected(self):
        path=self.root/'exclusive-regression-ubuntu-latest/frontend-tests.txt';path.write_text(path.read_text().replace('# fail 0','# fail 1'))
        with self.assertRaises(ValueError): self.verify()
    def test_browser_failure_or_stale_component_rejected(self):
        self.change('exclusive-browser/exclusive-ui/source-manifest.json',lambda d:d['sources'].update(ChatAuthorizationHost='e'*64))
        with self.assertRaises(ValueError): self.verify()
    def test_browser_missing_case_rejected(self):
        self.change('exclusive-browser/exclusive-evidence/browser-results.json',lambda d:d['tests'].pop())
        with self.assertRaises(ValueError): self.verify()
    def test_readiness_requires_both_explicit_decisions(self):
        self.change('exclusive-browser/exclusive-evidence/readiness-results.json',lambda d:d['tests'].pop())
        with self.assertRaises(ValueError): self.verify()
    def test_stale_legacy_baseline_not_confused_with_passing_candidate(self):
        (self.root/'exclusive-failure-first/failure-first.txt').write_text('compiler error[E1]; 1 failed')
        with self.assertRaises(ValueError): self.verify()
    def test_no_publication_on_unapproved_ref(self):
        with self.assertRaises(ValueError): release.compose(self.root,REPO,Path(self.tmp.name)/'out',source=SOURCE,tree=TREE,version=VERSION,run_id=RUN,ref='refs/heads/main')
    def test_no_mutation_if_main_moved(self):
        api=release.AnchoredGitHub('synthetic-test-token',SOURCE)
        with patch.object(GitHub,'request',return_value={'object':{'sha':'f'*40}}) as call:
            with self.assertRaises(ValueError):api.request('POST','/releases',data={'tag_name':'v0.4.0'})
            call.assert_called_once_with('GET','/git/ref/heads/main')
    def test_compose_exports_seven_unique_ascii_assets(self):
        assets,summary=release.compose(self.root,REPO,Path(self.tmp.name)/'out',source=SOURCE,tree=TREE,version=VERSION,run_id=RUN,ref=release.REF)
        self.assertEqual(len(assets),7); self.assertEqual(len({a['name'] for a in assets}),7)
        self.assertTrue(all(a['name'].isascii() for a in assets)); self.assertTrue(summary['prerelease'])


if __name__=='__main__':unittest.main(verbosity=2)
