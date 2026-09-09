"""合并发布配置与六处版本回归；不构建、不发布、不访问网络。"""
import copy
import json
from pathlib import Path
import tempfile
import tomllib
import unittest
from 版本递增v7 import plan, FILES
from 发布版本校验v4 import project_versions, PACKAGE

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / '.github/workflows/合并验收发布v9.yml').read_text(encoding='utf-8')
PREP = (ROOT / '.github/workflows/版本准备v9.yml').read_text(encoding='utf-8')

def next_fixture_version():
    current, _ = project_versions(ROOT)
    major, minor, patch = map(int, current.split('.'))
    return current, f'{major}.{minor}.{patch + 1}'


class MergedReleaseTests(unittest.TestCase):
    def test_six_versions_and_idempotent_plan(self):
        current, candidate = next_fixture_version()
        updates = plan(ROOT, current, candidate)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            for name in FILES:
                output = target / name
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(updates.get(name, (ROOT/name).read_bytes()))
            version, fields = project_versions(target)
            self.assertEqual(version, candidate)
            self.assertEqual(len(fields), 6)
            self.assertEqual(plan(target, current, candidate), {})

    def test_dependency_graph_unchanged(self):
        current, candidate = next_fixture_version()
        updates = plan(ROOT, current, candidate)
        for name in ('package-lock.json', 'src-tauri/Cargo.lock'):
            parse = tomllib.loads if name.endswith('.lock') else json.loads
            before = parse((ROOT/name).read_text(encoding='utf-8'))
            after = parse(updates.get(name, (ROOT/name).read_bytes()).decode())
            if name.endswith('.lock'):
                for data in (before, after):
                    for package in data['package']:
                        if package['name'] == PACKAGE:
                            package.pop('version')
            else:
                for data in (before, after):
                    data.pop('version')
                    data['packages'][''].pop('version')
            self.assertEqual(before, after)

    def test_release_ref_is_explicit(self):
        self.assertIn("branches: ['release/合并验收v9']", WORKFLOW)
        self.assertIn("github.ref == 'refs/heads/release/合并验收v9'", WORKFLOW)
        self.assertNotIn('pull_request:', WORKFLOW)

    def test_prepare_and_publish_check_main_sha(self):
        self.assertEqual(WORKFLOW.count("git ls-remote origin 'refs/heads/main'"), 2)
        self.assertNotIn('refs/heads/feat/', WORKFLOW)
        self.assertIn('--expect-sha "$GITHUB_SHA"', WORKFLOW)

    def test_version_is_explicit(self):
        self.assertIn("== '0.2.4'", WORKFLOW)
        self.assertIn('--version 0.2.4 --publish', WORKFLOW)
        self.assertNotIn('--version 0.2.3', WORKFLOW)

    def test_full_validation_precedes_build_and_publish(self):
        self.assertIn('os: [ubuntu-latest, windows-latest]', WORKFLOW)
        self.assertIn('needs: [prepare, validate]', WORKFLOW)
        self.assertIn('needs: [prepare, validate, windows]', WORKFLOW)
        self.assertIn('cargo test --locked --manifest-path src-tauri/Cargo.toml', WORKFLOW)
        self.assertIn('-- -D warnings', WORKFLOW)
        self.assertIn("['total'] == 0", WORKFLOW)

    def test_complete_native_keyring_group(self):
        self.assertEqual(WORKFLOW.count('data::secure_file::native_tests'), 2)
        self.assertNotIn('native_keychain_cross_process_file_roundtrip --', WORKFLOW)

    def test_real_panel_and_log_tests(self):
        self.assertIn('node --test tests/任务日志回归v2.test.mjs', WORKFLOW)
        self.assertIn('python tests/任务面板浏览器回归v3.py', WORKFLOW)
        self.assertIn('playwright==1.57.0', WORKFLOW)

    def test_install_and_public_download_gates(self):
        self.assertIn('安装包冒烟v7.ps1', WORKFLOW)
        self.assertIn('sha256:', WORKFLOW)
        self.assertIn('公开Release附件独立下载核验:', WORKFLOW)
        self.assertIn('len(raw) == item[', WORKFLOW)

    def test_only_publish_has_write_permission(self):
        self.assertEqual(WORKFLOW.count('contents: write'), 1)
        self.assertNotIn('contents: write', WORKFLOW.split('  publish:')[0])
        self.assertNotIn('macos-latest', WORKFLOW)

    def test_version_bot_is_confined_to_candidate_branch(self):
        self.assertIn("github.ref == 'refs/heads/release/准备v0.2.4'", PREP)
        self.assertIn('git push origin HEAD:refs/heads/release/准备v0.2.4', PREP)
        self.assertIn('assert changed <= allowed', PREP)
        self.assertNotIn('git push origin HEAD:refs/heads/main', PREP)
        for name in FILES:
            self.assertIn(name, PREP)

    def test_notes_do_not_claim_native_e2e_or_day_long_stress(self):
        notes = (ROOT/'docs/发布说明v0.2.4.md').read_text(encoding='utf-8')
        self.assertIn('预发布', notes)
        self.assertIn('不等同真实桌面端到端', notes)
        self.assertIn('不代表已经持续运行24小时', notes)

if __name__ == '__main__':
    unittest.main(verbosity=2)
