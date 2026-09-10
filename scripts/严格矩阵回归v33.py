"""Prevent a green recovery pipeline that silently skips the full native matrix."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


def source(name):
    return (ROOT / '.github/workflows' / name).read_text(encoding='utf-8')


def job(text, name):
    match = re.search(r'^  ' + re.escape(name) + r':\n(.*?)(?=^  [A-Za-z][\w-]*:|\Z)', text, re.M | re.S)
    if not match:
        raise AssertionError('required job not found: ' + name)
    return match.group(1)


class StrictMatrixContracts(unittest.TestCase):
    def test_recovery_calls_both_full_workflows_without_waiver(self):
        text = source('Windows原生恢复v27.yml')
        for name, workflow in (('validate', '聊天授权验证v1.yml'), ('packages', '聊天授权安装包v10.yml')):
            section = job(text, name)
            self.assertIn('needs: contracts', section)
            self.assertIn('uses: ./.github/workflows/' + workflow, section)
            self.assertRegex(section, r'windows_local:\s+false\b')
            self.assertNotIn('continue-on-error', section)
            self.assertNotIn('if:', section)

    def test_exact_fix_branch_allowed_not_wildcard_or_all_branches(self):
        section = job(source('聊天授权验证v1.yml'), 'source')
        condition = next(line for line in section.splitlines() if line.strip().startswith('if:'))
        self.assertIn("github.repository == 'Eswink/coding-tools-mcp'", condition)
        self.assertIn("github.ref == 'refs/heads/fix/windows-native-v27'", condition)
        self.assertNotIn('startsWith', condition)
        self.assertNotIn('contains(', condition)

    def test_current_source_identity_and_read_only_permissions_preserved(self):
        text = source('Windows原生恢复v27.yml')
        self.assertIn('contents: read', text)
        self.assertNotIn('contents: write', text)
        self.assertIn('git rev-parse HEAD', text)
        self.assertIn('git archive --format=zip', text)
        self.assertIn('python scripts/严格矩阵回归v33.py', text)
        self.assertNotIn('continue-on-error', text)

    def test_validation_keeps_native_gate_and_deferral_ref_restriction(self):
        text = source('聊天授权验证v1.yml')
        section = job(text, 'windows-native')
        self.assertIn('!inputs.windows_local', section)
        self.assertIn('聊天授权Windows原生v8.yml', section)
        self.assertIn("test \"$WINDOWS_LOCAL\" != true || test \"$GITHUB_REF\" = 'refs/heads/release/聊天授权本地验收v26'", text)


if __name__ == '__main__':
    unittest.main()
