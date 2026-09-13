"""Synthetic publisher-contract tests, never native or installer acceptance evidence."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import exclusive_release as release
from exclusive_native_contract_tests import record as native_record
from exclusive_native_gate import TEST_NAMES

SOURCE, TREE, VERSION, RUN = 'a' * 40, 'c' * 40, '0.4.0', '123'


def put(root, name, value):
    path = root / name; path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, (dict, list)): value = json.dumps(value)
    path.write_text(value, encoding='utf-8'); return path


def artifact(root, name):
    # Deliberately NOT an executable; unit fixtures never run or publish.
    path = put(root, name, 'synthetic package bytes: ' + name)
    return {'name': name, 'size': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def native(root, kind, digest):
    value = native_record()
    value.update(package_kind=kind, binary_sha256=digest, os_toast_visibility_verified=False)
    put(root, 'exclusive-native.json', value)


def fixture(root, checkout):
    base = {'source_sha': SOURCE, 'source_tree': TREE, 'version': VERSION, 'run_id': RUN, 'passed': True}
    put(root, 'exclusive-source/source.txt', SOURCE); put(root, 'exclusive-source/tree.txt', TREE)
    rust = '\n'.join(f'test case_{n} ... ok' for n in range(400)) + '\ntest result: ok. 400 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 1s\n'
    tap = 'TAP version 13\n' + '\n'.join(f'ok {n} - test {n}' for n in range(1,140))
    tap += '\n1..139\n# tests 139\n# suites 0\n# pass 139\n# fail 0\n# cancelled 0\n# skipped 0\n# todo 0\n# duration_ms 1\n'
    for system in ('windows-latest', 'ubuntu-latest'):
        folder = root / ('exclusive-regression-' + system)
        for name, value in {'source.txt': SOURCE, 'rust-tests.txt': rust, 'rust-check.txt': 'Finished',
            'production-warnings.txt': 'Finished', 'frontend-check.txt': 'svelte-check found 0 errors and 0 warnings',
            'frontend-build.txt': 'built in 1s', 'frontend-tests.txt': tap}.items(): put(folder, name, value)
    sources = {}
    for name, path in (('chat-authorization', 'src/lib/chat-authorization.ts'),
        ('remote-session-policy', 'src/lib/remote-session-policy.ts'),
        ('ChatAuthorizationHost', 'src/lib/components/ChatAuthorizationHost.svelte'),
        ('RemoteSessionSettings', 'src/lib/components/RemoteSessionSettings.svelte')):
        file = put(checkout, path, 'synthetic source ' + name); sources[name] = hashlib.sha256(file.read_bytes()).hexdigest()
    folder = root / 'exclusive-browser'
    put(folder, 'exclusive-ui/source-manifest.json', {'sources': sources})
    put(folder, 'exclusive-evidence/browser-results.json', {'status':'passed', 'passed':12, 'failure':None,
        'page_errors':[], 'native_notifications_verified':False,
        'tests':[{'test':str(n), 'status':'passed'} for n in range(12)]})
    put(folder, 'exclusive-evidence/readiness-results.json', {'status':'passed', 'tests':[
        {'callback':name, 'candidate':'readiness is side-effect-free; explicit decision required'}
        for name in ('releaseConfirm','releaseSave')]})
    put(root, 'exclusive-failure-first/baseline-sha.txt', 'a0551c447712104e2c2cb253d3d8a5a966518580')
    put(root, 'exclusive-failure-first/failure-first.txt', 'occupied workspace must not create B pending; 1 failed')
    put(checkout, 'docs/releases/verification-v0.4.0.md', '# Synthetic unit-test guide\nNOT a release.\n')
    ubuntu = root / 'exclusive-ubuntu-packages'; packages = {}
    for kind, ext in (('deb','.deb'),('appimage','.AppImage')):
        item = artifact(ubuntu, f'MCP_{VERSION}_amd64{ext}')
        packages[kind] = {'architecture':'amd64','payload_sha256':'b'*64,'artifact':item}
        digest = item['sha256'] if kind == 'appimage' else 'b'*64
        for system in ('ubuntu-22.04','ubuntu-24.04'):
            folder = root / f'exclusive-installed-{system}-{kind}'
            put(folder, release.MANIFEST, {**base, 'kind':kind, 'package':item, 'payload_sha256':'b'*64,
                'native_executable_sha256':digest})
            native(folder, kind, digest)
    put(ubuntu, release.MANIFEST, {**base,'build_kind':'release-packaged','packages':packages})
    folder = root / 'exclusive-windows-package'
    item = artifact(folder, f'MCP_{VERSION}_x64-setup.exe')
    put(folder, release.MANIFEST, {**base,'scenario':release.SCENARIO,'kind':'nsis','package':item,
        'payload_sha256':'b'*64,'native_executable_sha256':'b'*64,'silent_install':True,
        'exact_nsis_payload_verified':True,'real_native_approval':True,'signed':False,
        'synthetic_conversation_metadata':True,'real_chatgpt_verified':False})
    native(folder,'nsis','b'*64)
    put(folder,'标准用户隔离结果v22.json', {**base,'genuine_standard_account':True, 'account_deleted':True,
        'profile_deleted':True,'owned_processes_closed':True,'credentials_scan_completed':True,
        'credentials_found':False,'sandbox_disabled':False,'native_exit_code':0,'account_sid_sha256':'d'*64,
        'actual_logon':{'actual_child_identity_verified':True,'account_sid_sha256':'d'*64,
            'token':{'elevated':False,'integrity_rid':8192},'restricted':False,'manual_desktop_acl':False,
            'launch_api':'CreateProcessWithLogonW'}})
    put(folder,'安装载荷核验v7.json', {'passed':True,'installed_sha256':'b'*64,'expected_installed_sha256':'b'*64})


class ReleaseContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.evidence=self.root/'evidence'; self.checkout=self.root/'checkout'
        fixture(self.evidence,self.checkout)

    def compose(self, **fields):
        args = dict(source=SOURCE, tree=TREE, version=VERSION, run_id=RUN, ref=release.REF); args.update(fields)
        return release.compose(self.evidence,self.root/'delivery',self.checkout,**args)

    def change(self, path, mutate):
        file=self.evidence/path; value=json.loads(file.read_text()); mutate(value); file.write_text(json.dumps(value))

    def test_all_five_installed_cases_produce_seven_unique_assets(self):
        assets, summary=self.compose()
        self.assertEqual(len(assets),7);self.assertEqual(len({a['name'] for a in assets}),7)
        self.assertEqual(len(summary['installed_matrix']),5)
        self.assertTrue(all(row['native_stages']==12 for row in summary['installed_matrix']))
        self.assertTrue(summary['prerelease']);self.assertFalse(summary['real_chatgpt_verified'])
        self.assertFalse(summary['os_toast_visibility_verified'])
        for item in assets:self.assertEqual(item['digest'],'sha256:'+release.transport.digest(item['path']))

    def test_wrong_identity_and_non_release_ref_rejected(self):
        for key,value in [('source','e'*40),('tree','f'*40),('run_id','124'),('version','0.3.2'),('ref','refs/heads/main')]:
            with self.subTest(key=key),self.assertRaises(ValueError):self.compose(**{key:value})

    def test_missing_installed_combination_rejected(self):
        (self.evidence/'exclusive-installed-ubuntu-24.04-appimage/exclusive-native.json').unlink()
        with self.assertRaises(ValueError):self.compose()

    def test_native_evidence_cannot_be_waived_or_faked(self):
        path='exclusive-windows-package/exclusive-native.json'; original=(self.evidence/path).read_text()
        for key,value in [('passed',False),('real_chatgpt_verified',True),('os_toast_visibility_verified',True),
                          ('pending_elapsed_seconds',1),('permission_approval_source','ipc'),('tests',[])]:
            self.change(path,lambda doc:doc.update({key:value}))
            with self.subTest(key=key),self.assertRaises(ValueError):self.compose()
            (self.evidence/path).write_text(original)

    def test_refresh_scenario_does_not_accept_legacy_eight_stages(self):
        self.change('exclusive-windows-package/exclusive-native.json',lambda doc:doc.update(tests=doc['tests'][:8]))
        with self.assertRaises(ValueError):self.compose()

    def test_changed_package_bytes_rejected(self):
        (self.evidence/'exclusive-ubuntu-packages/MCP_0.4.0_amd64.deb').write_bytes(b'tampered')
        with self.assertRaises(ValueError):self.compose()

    def test_package_path_traversal_and_bool_size_rejected(self):
        path='exclusive-windows-package/exclusive-package.json'; original=(self.evidence/path).read_text()
        for field,value in [('name','../escape.exe'),('name','MCP_0.3.2_x64-setup.exe'),('size',True)]:
            self.change(path,lambda doc:doc['package'].update({field:value}))
            with self.subTest(field=field),self.assertRaises(ValueError):self.compose()
            (self.evidence/path).write_text(original)

    def test_elevated_windows_execution_rejected(self):
        self.change('exclusive-windows-package/标准用户隔离结果v22.json',lambda doc:doc['actual_logon']['token'].update(elevated=True))
        with self.assertRaises(ValueError):self.compose()

    def test_linux_inner_payload_is_not_appimage_executable_digest(self):
        self.change('exclusive-installed-ubuntu-22.04-appimage/exclusive-package.json',lambda doc:doc.update(native_executable_sha256='b'*64))
        with self.assertRaises(ValueError):self.compose()

    def test_other_run_installed_evidence_rejected(self):
        self.change('exclusive-installed-ubuntu-22.04-deb/exclusive-native.json',lambda doc:doc.update(run_id='124'))
        with self.assertRaises(ValueError):self.compose()

    def test_component_hashes_anchor_browser_checks_to_checkout(self):
        (self.checkout/'src/lib/components/ChatAuthorizationHost.svelte').write_text('changed')
        with self.assertRaises(ValueError):self.compose()

    def test_browser_missing_or_failed_scenarios_rejected(self):
        self.change('exclusive-browser/exclusive-evidence/browser-results.json',lambda doc:doc['tests'].pop())
        with self.assertRaises(ValueError):self.compose()

    def test_rust_truncated_filtered_ignored_or_error_logs_rejected(self):
        path=self.evidence/'exclusive-regression-windows-latest/rust-tests.txt';original=path.read_text()
        for value in [original.split('\n',1)[1], original.replace('0 filtered','1 filtered'),
                      original.replace('0 ignored','1 ignored'), original+'\nerror: failure\n']:
            path.write_text(value)
            with self.subTest(value=value[-70:]),self.assertRaises(ValueError):self.compose()
        path.write_text(original)

    def test_frontend_skip_rejected(self):
        path=self.evidence/'exclusive-regression-windows-latest/frontend-tests.txt'
        path.write_text(path.read_text().replace('# skipped 0','# skipped 1'))
        with self.assertRaises(ValueError):self.compose()

    def test_symlink_package_rejected(self):
        path=self.evidence/'exclusive-ubuntu-packages/MCP_0.4.0_amd64.deb'
        target=self.root/'other.deb';path.rename(target);path.symlink_to(target)
        with self.assertRaises(ValueError):self.compose()

    def test_existing_output_not_silently_overwritten(self):
        (self.root/'delivery').mkdir()
        with self.assertRaises(FileExistsError):self.compose()

    def test_main_moves_before_any_mutation_blocks_publication(self):
        api=release.AnchoredGitHub('synthetic-unused-credential',SOURCE)
        with patch.object(release.transport.GitHub,'request',return_value={'object':{'sha':'e'*40}}) as call:
            with self.assertRaises(ValueError):api.request('POST','/releases',{})
            self.assertEqual(call.call_count,1);self.assertEqual(call.call_args.args,('GET','/git/ref/heads/main'))


if __name__=='__main__':unittest.main(verbosity=2)
