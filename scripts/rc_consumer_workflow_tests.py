"""Static workflow authority and source noninterference contracts."""
import ast
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).absolute().parents[1]
PINNED = {
    'actions/checkout': '11d5960a326750d5838078e36cf38b85af677262',
    'actions/setup-python': 'a26af69be951a213d495a4c3e4e4022e16d87065',
    'actions/upload-artifact': 'ea165f8d65b6e75b540449e92b4886f43607fa02',
}


class WorkflowTests(unittest.TestCase):
    def files(self):
        return [ROOT / '.github/workflows' / name for name in
                ('rc-artifact-consumer.yml', 'rc-artifact-consumer-checks.yml')]

    def test_token_scope_actions_pinning_and_no_mutating_release_paths(self):
        for path in self.files():
            text = path.read_text()
            with self.subTest(path=path.name):
                self.assertIn('permissions:\n  contents: read\n  actions: read\n', text)
                self.assertNotRegex(text, r'\b(write|write-all|id-token|attestations|deployments|packages):')
                for action, sha in re.findall(r'uses: ([^@\s]+)@([^\s]+)', text):
                    self.assertIn(action, PINNED)
                    self.assertEqual(sha, PINNED[action])
                self.assertIn('runs-on: ubuntu-24.04', text)
                self.assertIn("python-version: '3.12'", text)
                self.assertIn('ref: ${{ github.sha }}', text)
                self.assertIn('fetch-depth: 0', text)
                self.assertIn('persist-credentials: false', text)
                self.assertIn("PYTHONDONTWRITEBYTECODE: '1'", text)
                self.assertNotRegex(text, r'(?m)^\s*(environment|secrets|cache):')
                self.assertNotIn('workflow_run:', text)
                self.assertNotIn('pull_request_target:', text)
                self.assertNotIn('/releases', text)
                self.assertNotIn('gh release', text)
                self.assertNotRegex(text, r'git (tag|push)')

    def test_consumer_manual_inputs_only_and_sanitized_upload(self):
        text = self.files()[0].read_text()
        self.assertIn('  workflow_dispatch:', text)
        self.assertNotIn('  push:', text)
        self.assertNotIn('  pull_request:', text)
        inputs = re.findall(r'^      ([a-z_]+):$', text, re.M)
        self.assertEqual(set(inputs), {'rc_version', 'release_tag', 'source_sha', 'final_run_id',
            'final_run_attempt', 'integration_run_id', 'integration_run_attempt', 'artifact_id'})
        self.assertIn('test "$GITHUB_SHA" = "$SOURCE_SHA"', text)
        self.assertIn('test "$GITHUB_WORKFLOW_SHA" = "$SOURCE_SHA"', text)
        self.assertIn('GH_TOKEN: ${{ github.token }}', text)
        upload = text.split('          path: |', 1)[1].split('          if-no-files-found:', 1)[0]
        self.assertEqual(upload.strip().splitlines(), [
            '${{ runner.temp }}/rc-consumer-receipts-*/RC_PROVENANCE.json',
            '            ${{ runner.temp }}/rc-consumer-receipts-*/rc-asset-plan.json'])
        self.assertNotIn('rc-consumer-assets', upload)
        self.assertNotIn('if: always()', text)

    def test_fixture_workflow_has_no_token_input_and_runs_old_suites(self):
        text = self.files()[1].read_text()
        self.assertNotIn('GH_TOKEN:', text)
        self.assertNotIn('inputs:', text)
        self.assertIn("python scripts/rc_consumer_test_runner.py", text)
        self.assertIn("RC_CONSUMER_TEST_GLIB_ARCHIVE:", text)
        self.assertIn("--max-time 30 --max-filesize 1048576", text)
        self.assertIn("233daaf6e83ae6a12a52055f568f9d7cf4671dabb78ff9560ab6da230ce00ee5", text)
        self.assertNotIn("continue-on-error", text)
        for name in ('release_tag_gate', 'rc_version_gate', 'reviewed_source_gate', 'cloud_release_bundle',
                     'final_rc_evidence', 'release_dependency_capture', 'release_dependency_contract',
                     'exact_build_audit', 'rc_packages', 'rc_windows_install_contract',
                     'exclusive_native_contract', 'exclusive_release', 'source_provenance_gate',
                     '发布版本回归v4.py'):
            self.assertIn(name, text)
        self.assertIn('  pull_request:', text)
        self.assertIn('    paths:', text)
        self.assertIn('feat/rc-final-artifact-consumer-*', text)

    def test_runner_temp_context_is_only_in_supported_step_env(self):
        text = self.files()[1].read_text()
        before_steps, steps = text.split('    steps:', 1)
        self.assertNotIn('runner.temp', before_steps)
        self.assertEqual(steps.count('          RC_CONSUMER_TEST_GLIB_ARCHIVE: ${{ runner.temp }}/glib-0.18.5.crate'), 2)

    def test_new_sources_have_no_payload_execution_or_environment_identity_writes(self):
        forbidden = {'extractall', 'current_producer', 'verify_archive', 'verify_noncloud_audits',
                     'collect', 'probe', 'inspect_linux', 'installed', 'prepare', 'fetch_integration'}
        paths = [ROOT / 'scripts/rc_artifact_consumer.py'] + [
            p for p in (ROOT / 'scripts').glob('rc_consumer_*.py')
            if not p.name.endswith(('_tests.py', '_fixtures.py')) and p.name != 'rc_consumer_fixtures.py']
        for path in paths:
            text = path.read_text()
            self.assertLessEqual(len(text.splitlines()), 500, path.name)
            tree = ast.parse(text)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    name = node.func.attr if isinstance(node.func, ast.Attribute) else ''
                    self.assertNotIn(name, forbidden, (path.name, node.lineno, name))
                if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    for target in targets:
                        self.assertNotIn('os.environ', ast.unparse(target), path.name)
            self.assertNotIn('sys.path', text)
            self.assertNotIn('shell=True', text)


if __name__ == '__main__':
    unittest.main()
