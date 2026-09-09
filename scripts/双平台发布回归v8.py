"""Offline negative tests. These fixtures are not native installation evidence."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
import zipfile

import Ubuntu发布回归v1 as linux_fixture
import 发布资产回归v8 as windows_fixture
import 双平台发布v8 as dual
from Windows兼容重复v8 import validate_result, COMPAT, NEGATIVE, RETAINED

SOURCE = linux_fixture.SOURCE
RUN_ID = "12345"
ROOT = Path(__file__).resolve().parents[1]


class DualReleaseTests(unittest.TestCase):
    def setUp(self):
        self.linux = linux_fixture.UbuntuReleaseTests()
        self.linux.setUp()
        self.addCleanup(self.linux.doCleanups)
        self.windows = windows_fixture.PublishTests()
        with patch.object(windows_fixture, "VERSION", dual.VERSION):
            self.windows.setUp()
        self.addCleanup(self.windows.doCleanups)
        self.evidence = self.linux.evidence
        shutil.copytree(self.linux.packages, self.evidence / "Ubuntu安装包v1")
        self.windows_root = self.evidence / "Windows本地验收安装包v8"
        shutil.copytree(self.windows.root, self.windows_root)
        self.output = self.linux.root / "dual-output"
        self.manifest = self.evidence / "Ubuntu安装包v1" / dual.MANIFEST
        self.update(self.manifest, run_id=RUN_ID)
        self.identity = self.windows_root / "双平台构建身份v8.json"
        self.identity.write_text(json.dumps({"source_sha": SOURCE, "run_id": RUN_ID, "version": dual.VERSION}), encoding="utf-8")
        self.repeat = self.evidence / "Ubuntu基线v1-windows-latest/Windows兼容结果v8.json"
        self.repeat.write_text(json.dumps({"passed": True, "source_sha": SOURCE, "run_id": RUN_ID,
            "compatibility_repetitions": 20, "explicit_timeout_verified": True, "retained_session_verified": True,
            "results": [{"test": name, "passed": True} for name in [COMPAT]*20+[NEGATIVE, RETAINED]]}), encoding="utf-8")
        self.repeat.with_name("Windows兼容重复v8.log").write_text("fixture, not native evidence", encoding="utf-8")

    def update(self, path, **values):
        data = json.loads(path.read_text(encoding="utf-8"))
        data.update(values)
        path.write_text(json.dumps(data), encoding="utf-8")

    def assets(self):
        return dual.compose(self.evidence, self.output, SOURCE, RUN_ID, ROOT)

    def test_six_assets_include_both_platforms_and_complete_checksums(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("offline composition must not access network")):
            assets = self.assets()
        self.assertEqual(len(assets), 6)
        names = {item["name"] for item in assets}
        for suffix in (".deb", ".AppImage", ".exe"):
            self.assertEqual(sum(name.endswith(suffix) for name in names), 1)
        sums = assets[-1]["path"].read_text(encoding="utf-8")
        for item in assets[:-1]: self.assertIn(item["digest"][7:] + "  " + item["name"], sums)
        with zipfile.ZipFile(self.output / f"Windows-evidence_v{dual.VERSION}.zip") as archive:
            self.assertIn("Windows兼容结果v8.json", archive.namelist())

    def test_repeated_composition_is_byte_stable(self):
        a = [(v["name"],v["digest"]) for v in self.assets()]
        b = [(v["name"],v["digest"]) for v in self.assets()]
        self.assertEqual(a, b)

    def test_missing_windows_installer_blocks(self):
        next(self.windows_root.glob("*.exe")).unlink()
        with self.assertRaises(ValueError): self.assets()

    def test_windows_gui_failure_blocks(self):
        self.update(self.windows_root / "安装冒烟结果v7.json", native_window_created=False)
        with self.assertRaises(ValueError): self.assets()

    def test_ubuntu_native_failure_blocks(self):
        self.linux.mutate("passed", False)
        with self.assertRaises(ValueError): self.assets()

    def test_ubuntu_run_mismatch_blocks(self):
        self.update(self.manifest, run_id="999")
        with self.assertRaises(ValueError): self.assets()

    def test_windows_run_mismatch_blocks(self):
        self.update(self.identity, run_id="999")
        with self.assertRaises(ValueError): self.assets()

    def test_windows_version_mismatch_blocks(self):
        self.update(self.identity, version="0.0.0")
        with self.assertRaises(ValueError): self.assets()

    def test_missing_repetition_proof_blocks(self):
        self.repeat.unlink()
        with self.assertRaises(ValueError): self.assets()

    def test_missing_timeout_negative_blocks(self):
        self.update(self.repeat, explicit_timeout_verified=False)
        with self.assertRaises(ValueError): self.assets()

    def test_empty_or_false_repetition_blocks(self):
        self.update(self.repeat, results=[])
        with self.assertRaises(ValueError): self.assets()

    def test_wrong_repetition_case_blocks(self):
        data=json.loads(self.repeat.read_text()); data['results'][0]['test']='unrelated'
        self.repeat.write_text(json.dumps(data))
        with self.assertRaises(ValueError): self.assets()

    def test_fake_green_zero_tests_is_rejected(self):
        with self.assertRaises(ValueError): validate_result(0,"test result: ok. 0 passed; 0 failed; 0 ignored;")

    def test_nonzero_exit_is_not_a_pass(self):
        with self.assertRaises(ValueError): validate_result(101,"test result: ok. 1 passed; 0 failed; 0 ignored;")

    def test_exact_single_real_test_result_is_accepted(self):
        validate_result(0,"test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 253 filtered out;")

    def test_nonrelease_context_never_creates_api(self):
        assets=self.assets()
        with patch.dict(os.environ, {'GITHUB_REF':'refs/heads/main','GITHUB_REPOSITORY':dual.REPOSITORY,'GITHUB_SHA':SOURCE,'GITHUB_RUN_ID':RUN_ID}), patch.object(dual,'AnchoredGitHub') as client:
            with self.assertRaises(ValueError): dual.publish(assets,self.evidence,self.output,SOURCE,RUN_ID,ROOT)
            client.assert_not_called()

    def test_candidate_changed_after_acceptance_blocks_api(self):
        assets=self.assets(); target=self.evidence/'双平台候选发布v8'; target.mkdir()
        value=dual.inventory(assets,SOURCE,RUN_ID); value['assets'][0]['digest']='sha256:'+'0'*64
        (target/dual.CANDIDATE).write_text(json.dumps(value))
        with patch.dict(os.environ, {'GITHUB_REF':dual.REF,'GITHUB_REPOSITORY':dual.REPOSITORY,'GITHUB_SHA':SOURCE,'GITHUB_RUN_ID':RUN_ID}), patch.object(dual,'AnchoredGitHub') as client:
            with self.assertRaises(ValueError): dual.publish(assets,self.evidence,self.output,SOURCE,RUN_ID,ROOT)
            client.assert_not_called()

    def test_main_drift_prevents_authenticated_write(self):
        api=dual.AnchoredGitHub('fixture-only',SOURCE)
        with patch.object(dual.windows.GitHub,'request',return_value={'object':{'sha':'b'*40}}) as transport:
            with self.assertRaises(ValueError): api.request('PATCH','/releases/1',{'draft':False})
            self.assertEqual(transport.call_count,1)
            self.assertEqual(transport.call_args.args[:2],('GET','/git/ref/heads/main'))

    def test_public_download_is_anonymous_and_verified(self):
        raw=b'fixture package'; asset={'name':'MCP.exe','size':len(raw),'digest':'sha256:'+hashlib.sha256(raw).hexdigest()}
        with patch('urllib.request.urlopen',return_value=io.BytesIO(raw)) as request:
            result=dual.check_public_downloads([asset],dual.VERSION)
        self.assertIsInstance(request.call_args.args[0],str)
        self.assertTrue(result[0]['anonymous_download_verified'])

    def test_tampered_public_download_is_rejected(self):
        asset={'name':'MCP.exe','size':3,'digest':'sha256:'+'0'*64}
        with patch('urllib.request.urlopen',return_value=io.BytesIO(b'bad')):
            with self.assertRaises(ValueError): dual.check_public_downloads([asset],dual.VERSION)

    def test_oversized_public_download_is_rejected(self):
        asset={'name':'MCP.exe','size':1,'digest':'sha256:'+'0'*64}
        with patch('urllib.request.urlopen',return_value=io.BytesIO(b'large')):
            with self.assertRaises(ValueError): dual.check_public_downloads([asset],dual.VERSION)

    def test_workflow_permissions_and_all_gates(self):
        text=(ROOT/'.github/workflows/双平台桌面发布v8.yml').read_text(encoding='utf-8')
        self.assertIn('needs: [ubuntu, windows, acceptance]',text)
        self.assertEqual(text.count('contents: write'),1)
        self.assertIn(dual.REF,text)
        self.assertNotIn('continue-on-error',text)
        reusable=(ROOT/'.github/workflows/双平台Ubuntu验收v8.yml').read_text(encoding='utf-8')
        self.assertIn('workflow_call:',reusable)
        self.assertNotIn('contents: write',reusable)
        self.assertIn('Windows兼容重复v8.py',reusable)


if __name__ == '__main__':
    unittest.main(verbosity=2)
