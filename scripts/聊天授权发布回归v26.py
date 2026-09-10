"""Negative release-gate tests using explicit synthetic fixtures, never CI proof."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import 聊天授权发布v26 as m

SOURCE, TREE, VERSION, RUN = 'a' * 40, 'b' * 40, '0.3.0', '12345'


def write_json(file, value):
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')


def fixture(root, local=False):
    base = dict(passed=True, source_sha=SOURCE, source_tree=TREE, version=VERSION, run_id=RUN)
    for system in ('windows-latest', 'ubuntu-latest'):
        for area in ('Rust', '前端'):
            folder = root / f'聊天授权{area}-{system}-v4'; folder.mkdir(parents=True)
            (folder / '源码版本v4.txt').write_text(SOURCE, encoding='utf-8')
        folder = root / f'聊天授权Rust-{system}-v4'
        (folder / '完整回归v4.txt').write_text('test result: ok. 350 passed; 0 failed; 0 ignored; 0 measured;\n', encoding='utf-8')
        for name in ('编译检查v4.txt', '生产零警告v5.txt'):
            (folder / name).write_text('Finished `dev` profile', encoding='utf-8')
        (root / f'聊天授权前端-{system}-v4/前端回归v4.txt').write_text('# tests 30\n# fail 0\n', encoding='utf-8')
    def package(folder, name):
        folder.mkdir(parents=True, exist_ok=True)
        file = folder / name; file.write_bytes(('FAKE UNIT FIXTURE ' + name).encode())
        return dict(name=name, size=file.stat().st_size, sha256=hashlib.sha256(file.read_bytes()).hexdigest())
    def native(folder, kind, sha):
        value = dict(passed=True, source_sha=SOURCE, run_id=RUN, version=VERSION, package_kind=kind,
            binary_sha256=sha, build_kind='release-installed', real_native_webview=True,
            real_oauth_http=True, real_local_ipc=True, cleanup_completed=True, sandbox_disabled=False,
            cleanup_failed=False, real_chatgpt_verified=False, synthetic_conversation_metadata=True,
            tests=[dict(name=n, passed=True) for n in m.native.TEST_NAMES])
        write_json(folder / m.NATIVE, value)
    packages = {}
    for kind, ext in (('deb', '.deb'), ('appimage', '.AppImage')):
        item = package(root / '聊天授权Ubuntu包v10', '候选' + ext)
        packages[kind] = dict(artifact=item, payload_sha256='c' * 64, architecture='amd64', package_id='example' if kind == 'deb' else None)
        for system in ('ubuntu-22.04', 'ubuntu-24.04'):
            folder = root / f'聊天授权已安装-{system}-{kind}-v10'
            sha = item['sha256'] if kind == 'appimage' else 'c' * 64
            write_json(folder / m.MANIFEST, dict(base, kind=kind, package=item, payload_sha256='c' * 64, native_executable_sha256=sha))
            native(folder, kind, sha)
    write_json(root / '聊天授权Ubuntu包v10' / m.MANIFEST, dict(base, packages=packages, build_kind='release-packaged'))
    folder = root / '聊天授权Windows包v10'
    win = dict(base, kind='nsis', package=package(folder, '候选.exe'), payload_sha256='d' * 64,
        native_executable_sha256='d' * 64, silent_install=True, exact_nsis_payload_verified=True,
        signed=False, real_chatgpt_verified=False, real_native_approval=not local)
    if local:
        win.update(native_status='pending_local_verification', waiver='user-authorized NOT PASS', native_window_created=True, sustained_process=True)
        write_json(folder / '安装冒烟结果v7.json', dict(base, platform='windows-x64', installed_binary_sha256='d'*64,
            silent_install=True, exact_nsis_payload_verified=True, native_window_created=True, sustained_process=True))
        write_json(folder / '安装载荷核验v7.json', dict(base, installed_sha256='d'*64, expected_installed_sha256='d'*64))
    else: native(folder, 'nsis', 'd'*64)
    write_json(folder / m.MANIFEST, win)
    guide = root / '指南.md'; guide.write_text('UNIT TEST fixture only.', encoding='utf-8')
    return guide


class ReleaseGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'collected'; self.root.mkdir()
        self.out = Path(self.temp.name) / 'output'
        self.guide = fixture(self.root)

    def tearDown(self): self.temp.cleanup()
    def compose(self, ref=m.STRICT_REF):
        return m.compose(self.root, self.out, source=SOURCE, tree=TREE, version=VERSION,
                         run_id=RUN, ref=ref, guide=self.guide)
    def change(self, relative, fn):
        file = self.root / relative; data = m.load(file); fn(data); write_json(file, data)

    def test_complete_strict_candidate_retains_unverified_chatgpt(self):
        assets, summary = self.compose()
        self.assertEqual(len(assets), 6)
        self.assertTrue(summary['all_native_gui_verified'])
        self.assertFalse(summary['real_chatgpt_verified'])
        self.assertEqual(summary['windows']['stages'], 8)

    def test_explicit_local_mode_is_not_full_pass(self):
        shutil = m.shutil; shutil.rmtree(self.root); self.root.mkdir(); self.guide = fixture(self.root, local=True)
        _, summary = self.compose(m.LOCAL_REF)
        self.assertFalse(summary['all_native_gui_verified'])
        self.assertEqual(summary['windows']['status'], 'pending_local_verification')
        self.assertEqual(summary['windows']['stages'], 0)
        with self.assertRaises(ValueError): self.compose()

    def test_feature_branch_cannot_publish(self):
        with self.assertRaises(ValueError): self.compose('refs/heads/feat/chat-authorization-v1')

    def test_native_failure_cannot_be_promoted(self):
        self.change('聊天授权Windows包v10/' + m.NATIVE, lambda x: x.update(passed=False, tests=[]))
        with self.assertRaises(ValueError): self.compose()
        with self.assertRaises(ValueError): self.compose(m.LOCAL_REF)

    def test_all_four_linux_combinations_are_mandatory(self):
        (self.root / '聊天授权已安装-ubuntu-24.04-appimage-v10' / m.NATIVE).unlink()
        with self.assertRaises(ValueError): self.compose()

    def test_install_digest_cannot_be_waived(self):
        self.change('聊天授权Windows包v10/' + m.MANIFEST, lambda x: x.update(native_executable_sha256='e'*64))
        with self.assertRaises(ValueError): self.compose()

    def test_changed_package_bytes_are_rejected(self):
        (self.root / '聊天授权Windows包v10/候选.exe').write_bytes(b'tampered')
        with self.assertRaises(ValueError): self.compose()

    def test_cross_run_manifest_rejected(self):
        self.change('聊天授权Ubuntu包v10/' + m.MANIFEST, lambda x: x.update(run_id='12346'))
        with self.assertRaises(ValueError): self.compose()

    def test_cross_tree_manifest_rejected(self):
        self.change('聊天授权Windows包v10/' + m.MANIFEST, lambda x: x.update(source_tree='f'*40))
        with self.assertRaises(ValueError): self.compose()

    def test_baseline_failures_block_all_modes(self):
        (self.root / '聊天授权Rust-windows-latest-v4/完整回归v4.txt').write_text('test result: ok. 350 passed; 1 failed; 0 ignored;', encoding='utf-8')
        for ref in (m.STRICT_REF, m.LOCAL_REF):
            with self.assertRaises(ValueError): self.compose(ref)

    def test_ignored_rust_and_incomplete_suites_rejected(self):
        file = self.root / '聊天授权Rust-ubuntu-latest-v4/完整回归v4.txt'
        for raw in ('test result: ok. 350 passed; 0 failed; 1 ignored;', 'test result: ok. 3 passed; 0 failed; 0 ignored;'):
            file.write_text(raw, encoding='utf-8')
            with self.assertRaises(ValueError): self.compose()

    def test_changed_frontend_source_is_rejected(self):
        (self.root / '聊天授权前端-windows-latest-v4/源码版本v4.txt').write_text('f'*40, encoding='utf-8')
        with self.assertRaises(ValueError): self.compose()

    def test_duplicate_json_and_native_stages_rejected(self):
        self.change('聊天授权已安装-ubuntu-22.04-deb-v10/' + m.NATIVE, lambda x: x['tests'].__setitem__(1, x['tests'][0]))
        with self.assertRaises(ValueError): self.compose()
        file = self.root / '聊天授权Ubuntu包v10' / m.MANIFEST
        file.write_text('{"passed":false,"passed":true}', encoding='utf-8')
        with self.assertRaises(ValueError): m.load(file)

    def test_native_metadata_must_remain_synthetic(self):
        self.change('聊天授权Windows包v10/' + m.NATIVE, lambda x: x.update(real_chatgpt_verified=True))
        with self.assertRaises(ValueError): self.compose()

    def test_evidence_zip_is_deterministic_and_not_executable_bundle(self):
        assets, _ = self.compose(); first = [(x['name'],x['digest']) for x in assets]
        assets, _ = self.compose(); self.assertEqual(first, [(x['name'],x['digest']) for x in assets])
        with m.zipfile.ZipFile(assets[3]['path']) as archive:
            self.assertTrue(all(not n.endswith(('.exe','.AppImage','.deb')) for n in archive.namelist()))

    def test_local_smoke_failure_is_not_waived(self):
        m.shutil.rmtree(self.root); self.root.mkdir(); self.guide = fixture(self.root, local=True)
        self.change('聊天授权Windows包v10/安装冒烟结果v7.json', lambda x: x.update(native_window_created=False))
        with self.assertRaises(ValueError): self.compose(m.LOCAL_REF)

    def test_no_mutation_when_main_has_moved(self):
        api = m.AnchoredGitHub('unit-fake-token', SOURCE)
        with patch.object(m.transport.GitHub, 'request', return_value={'object': {'sha':'f'*40}}) as request:
            with self.assertRaises(ValueError): api.request('POST', '/releases', data={'tag_name':'v0.3.0'})
            request.assert_called_once_with('GET', '/git/ref/heads/main')

    def test_anonymous_download_never_has_authorization_header(self):
        import io
        payload = b'unit-only'; item = dict(name='unit.txt', size=len(payload), digest='sha256:'+hashlib.sha256(payload).hexdigest())
        with patch.object(m.urllib.request, 'urlopen', return_value=io.BytesIO(payload)) as request:
            self.assertTrue(m.anonymous_downloads([item], VERSION)[0]['anonymous_download_verified'])
            self.assertNotIn('Authorization', dict(request.call_args.args[0].header_items()))

    def test_workflow_defaults_and_local_waiver_are_explicit(self):
        workflow = Path(__file__).resolve().parents[1] / '.github/workflows'
        publication = (workflow/'聊天授权发布v26.yml').read_text(encoding='utf-8')
        self.assertIn('needs: [prepare, validate, packages]', publication)
        self.assertIn('contents: write', publication)
        self.assertIn('refs/heads/main', publication)
        for name in ('聊天授权验证v1.yml','聊天授权安装包v10.yml'):
            value = (workflow/name).read_text(encoding='utf-8')
            self.assertIn('windows_local:', value)
            self.assertIn('default: false', value)
            self.assertNotIn('continue-on-error: true', value)
            self.assertNotIn('contents: write', value)


if __name__ == '__main__': unittest.main()
