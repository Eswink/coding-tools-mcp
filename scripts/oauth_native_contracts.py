"""Fail closed when the OAuth repair branch cannot reach strict native gates."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


def workflow(name):
    return (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")


def job(text, name):
    match = re.search(r"^  " + re.escape(name) + r":\n(.*?)(?=^  [A-Za-z][\w-]*:|\Z)", text, re.M | re.S)
    if not match:
        raise AssertionError("missing required job: " + name)
    return match.group(1)


class OAuthNativeContracts(unittest.TestCase):
    def test_repair_branch_reaches_reusable_validation_source(self):
        source = job(workflow("聊天授权验证v1.yml"), "source")
        condition = next(line for line in source.splitlines() if line.strip().startswith("if:"))
        self.assertIn("github.repository == 'Eswink/coding-tools-mcp'", condition)
        self.assertIn("github.ref == 'refs/heads/fix/oauth-discovery-runtime'", condition)
        self.assertNotIn("startsWith", condition)
        self.assertNotIn("contains(", condition)

    def test_both_strict_workflows_are_mandatory(self):
        source = workflow("oauth-native-acceptance.yml")
        for name, called in (("validate", "聊天授权验证v1.yml"), ("packages", "聊天授权安装包v10.yml")):
            section = job(source, name)
            self.assertIn("needs: contracts", section)
            self.assertIn("uses: ./.github/workflows/" + called, section)
            self.assertRegex(section, r"windows_local:\s+false\b")
            self.assertNotIn("if:", section)
            self.assertNotIn("continue-on-error", section)

    def test_entry_is_read_only_exact_source_and_version_checked(self):
        source = workflow("oauth-native-acceptance.yml")
        self.assertIn("branches: ['fix/oauth-discovery-runtime']", source)
        self.assertIn("contents: read", source)
        self.assertNotIn("contents: write", source)
        self.assertNotIn("continue-on-error", source)
        self.assertIn("ref: ${{ github.sha }}", source)
        self.assertIn('test "$(git rev-parse HEAD)" = "$GITHUB_SHA"', source)
        self.assertIn('python scripts/发布版本校验v4.py --expect-sha "$GITHUB_SHA"', source)
        self.assertIn('assert receipt["version"] == "0.3.2"', source)
        self.assertIn("sha256sum evidence/source.zip", source)
        for command in ("oauth_native_contracts.py", "授权辅助回归v23.py", "聊天授权发布回归v26.py"):
            self.assertIn("python scripts/" + command, source)

    def test_installed_matrix_is_four_linux_combinations_and_real_nsis(self):
        source = workflow("聊天授权安装包v10.yml")
        section = job(source, "linux-native")
        self.assertIn("os: [ubuntu-22.04, ubuntu-24.04]", section)
        self.assertIn("kind: [deb, appimage]", section)
        self.assertIn("聊天授权证据门禁v18.py", section)
        self.assertIn("聊天授权原生验收v6.py", section)
        windows = job(source, "windows")
        self.assertIn("聊天授权Windows安装v10.ps1", windows)
        self.assertIn("!inputs.windows_local", windows)
        self.assertNotIn("continue-on-error", windows)

    def test_legacy_windows_waiver_remains_restricted_to_its_old_branch(self):
        source = workflow("聊天授权验证v1.yml")
        self.assertIn("test \"$WINDOWS_LOCAL\" != true || test \"$GITHUB_REF\" = 'refs/heads/release/聊天授权本地验收v26'", source)
        self.assertIn("!inputs.windows_local", job(source, "windows-native"))
        self.assertNotIn("windows_local: true", workflow("oauth-native-acceptance.yml"))


if __name__ == "__main__":
    unittest.main()
