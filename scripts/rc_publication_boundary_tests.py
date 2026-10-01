"""Pure-runtime and isolated diagnostic-workflow boundaries; synthetic only."""
import ast
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import unittest
from unittest.mock import patch

ROOT = Path(__file__).absolute().parents[1]
WORKFLOW = ROOT / '.github/workflows/rc-publication-contract-checks.yml'
BASE = '70aa9e3644fc50861992717c6c879d8c7261539f'
RUNTIME = {'rc_publication_types', 'rc_publication_contract', 'rc_publication_reconcile'}
PREDECESSORS = {'rc_pretag_types', 'rc_pretag_evidence', 'rc_release_eligibility', 'rc_release_policy'}
PURE_STDLIB = {'__future__', 'dataclasses', 'datetime', 'hashlib', 'json', 're', 'types', 'typing'}


def inline_block(label):
    source = WORKFLOW.read_text()
    return textwrap.dedent(source.split('# BEGIN ' + label + '\n', 1)[1].split('# END ' + label, 1)[0])


def inline_namespace(label):
    namespace = {'__name__': 'synthetic_workflow_test'}
    exec(compile(inline_block(label), '<inline-workflow-fixture>', 'exec'), namespace)
    return namespace


def imports(tree):
    result = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                raise AssertionError('relative import outside reviewed runtime graph')
            result.add(node.module)
            if any(alias.name == '*' for alias in node.names):
                raise AssertionError('wildcard import outside reviewed runtime graph')
    return result


class RuntimeBoundaryTests(unittest.TestCase):
    def test_transitive_imports_stay_in_reviewed_pure_graph(self):
        seen, pending = set(), list(RUNTIME)
        while pending:
            name = pending.pop()
            if name in seen:
                continue
            seen.add(name)
            tree = ast.parse((ROOT / 'scripts' / (name + '.py')).read_text())
            for imported in imports(tree):
                self.assertIn(imported, PURE_STDLIB | RUNTIME | PREDECESSORS, (name, imported))
                if imported not in PURE_STDLIB:
                    pending.append(imported)
        self.assertEqual(seen, RUNTIME | PREDECESSORS)

    def test_runtime_has_no_dynamic_execution_io_or_main(self):
        forbidden = {'open', 'exec', 'eval', 'compile', '__import__', 'breakpoint', 'input', 'print',
            'getattr', 'setattr', 'globals', 'locals', 'vars', 'getenv', 'getcwd', 'chdir', 'read_text',
            'read_bytes', 'write_text', 'write_bytes', 'unlink', 'mkdir', 'system', 'popen', 'request',
            'urlopen', 'socket', 'connect', 'import_module', 'spec_from_file_location'}
        # Predecessor strict codecs intentionally use get_type_hints on their own schemas.
        for name in RUNTIME | PREDECESSORS:
            source = (ROOT / 'scripts' / (name + '.py')).read_text()
            self.assertNotIn('__main__', source, name)
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    called = node.func.id if isinstance(node.func, ast.Name) else \
                        node.func.attr if isinstance(node.func, ast.Attribute) else None
                    self.assertNotIn(called, forbidden, (name, getattr(node, 'lineno', None)))
                if isinstance(node, (ast.AsyncFunctionDef, ast.Await, ast.Yield, ast.YieldFrom)):
                    self.fail('runtime execution boundary: ' + name)

    def test_new_modules_are_bounded_and_have_only_declarative_top_level(self):
        for path in sorted((ROOT / 'scripts').glob('rc_publication_*.py')):
            self.assertLessEqual(len(path.read_text().splitlines()), 500, path.name)
        for name in RUNTIME:
            for node in ast.parse((ROOT / 'scripts' / (name + '.py')).read_text()).body:
                self.assertTrue(isinstance(node, (ast.Import, ast.ImportFrom, ast.Assign,
                    ast.AnnAssign, ast.FunctionDef, ast.ClassDef)) or isinstance(node, ast.Expr)
                    and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str),
                    (name, node.lineno))

    def test_public_api_has_no_transport_or_verifier_injection(self):
        forbidden = {'url', 'token', 'transport', 'adapter', 'verifier', 'callback', 'executor',
                     'request', 'client', 'authenticated', 'trusted'}
        for name in RUNTIME:
            tree = ast.parse((ROOT / 'scripts' / (name + '.py')).read_text())
            for node in tree.body:
                if isinstance(node, ast.FunctionDef) and not node.name.startswith('_'):
                    args = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
                    self.assertTrue(forbidden.isdisjoint(arg.arg for arg in args), (name, node.name))
                    self.assertIsNone(node.args.kwarg, (name, node.name))
                    self.assertIsNone(node.args.vararg, (name, node.name))

    def test_caller_selected_class_never_reaches_annotation_evaluation(self):
        import rc_publication_types as publication
        from rc_pretag_types import ContractError

        @dataclass(frozen=True)
        class ForeignRecord:
            number: int

        with patch('rc_pretag_types.get_type_hints', side_effect=AssertionError('unreviewed annotation evaluated')) as hints:
            with self.assertRaises(ContractError):
                publication.fresh(ForeignRecord(1), ForeignRecord)
            hints.assert_not_called()

    def test_all_predecessor_tracked_content_and_modes_are_unchanged(self):
        runner = inline_namespace('RC_GROUP_RUNNER')
        command = ['git', 'diff', '--exit-code', BASE, '--', '.', *[':(exclude)' + name for name in runner['NEW']]]
        result = subprocess.run(command, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        self.assertEqual(result.returncode, 0, 'predecessor tracked blob/mode changed or source unavailable')


class WorkflowBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.source = WORKFLOW.read_text()

    def test_exact_isolated_push_trigger_and_paths(self):
        trigger = self.source.split('\npermissions:', 1)[0]
        self.assertIn("branches: ['feat/rc-publication-contract-70aa']", trigger)
        self.assertEqual(re.findall(r"      - '([^']+)'", trigger), ['scripts/rc_publication_*.py',
            'docs/specs/issue-88-additive/**', '.github/workflows/rc-publication-contract-checks.yml'])
        self.assertNotRegex(trigger, r'pull_request|workflow_dispatch|workflow_call|workflow_run|release:|tags:')

    def test_read_only_permissions_and_exact_pinned_actions(self):
        self.assertIn('permissions:\n  contents: read\n', self.source)
        self.assertNotRegex(self.source, r'(?m)^\s*(actions|id-token|packages|attestations|deployments):')
        self.assertNotRegex(self.source, r'\b(write|write-all):|GH_TOKEN|GITHUB_TOKEN|secrets\.')
        self.assertEqual(re.findall(r'uses: ([^\s]+)', self.source), [
            'actions/checkout@11d5960a326750d5838078e36cf38b85af677262',
            'actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065',
            'actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02'])
        for literal in ('ref: ${{ github.sha }}', 'persist-credentials: false', 'fetch-depth: 0',
                        'runs-on: ubuntu-24.04', "python-version: '3.12'", 'timeout-minutes: 15'):
            self.assertIn(literal, self.source)
        self.assertNotIn('runner.temp', self.source.split('    steps:', 1)[0])

    def test_no_release_tag_dispatch_payload_or_environment_dump(self):
        self.assertNotRegex(self.source, r'gh (release|api|workflow)|git (tag|push)|/releases|/dispatches')
        self.assertNotRegex(self.source, r'printenv|env\s*>|dict\(os.environ\)|os.environ.items|extractall')
        self.assertNotIn('continue-on-error', self.source)
        self.assertNotIn('|| true', self.source)

    def test_upload_always_exact_diagnostics_and_retention(self):
        collector = inline_namespace('RC_DIAGNOSTIC_COLLECTOR')
        upload = self.source.split('      - name: Retain diagnostic evidence', 1)[1]
        self.assertIn('if: always()', upload)
        self.assertIn('retention-days: 7', upload)
        self.assertIn('if-no-files-found: error', upload)
        self.assertIn('name: rc-publication-diagnostics-${{ github.run_id }}-${{ github.run_attempt }}', upload)
        paths = upload.split('          path: |\n', 1)[1].splitlines()
        self.assertEqual({line.strip().split('/upload/')[1] for line in paths},
                         set(collector['ALLOWLIST']) | {'collector.json'})
        for line in paths:
            self.assertNotIn('*', line)
            self.assertIn('${{ runner.temp }}/rc-publication-${{ github.run_id }}-${{ github.run_attempt }}/upload/', line)
        collect_step = self.source.split('      - name: Collect explicit bounded diagnostics', 1)[1].split('      - name:', 1)[0]
        self.assertIn('if: always()', collect_step)

    def test_exact_counts_and_original_imported_test_selection(self):
        runner = inline_namespace('RC_GROUP_RUNNER')
        self.assertEqual(runner['EXPECTED'], {'new': None, 'pretag': 53, 'consumer': 159, 'original': 208})
        self.assertEqual(runner['ORIGINAL'], ('release_tag_gate', 'rc_version_gate', 'reviewed_source_gate',
            'cloud_release_bundle', 'final_rc_evidence', 'release_dependency_capture', 'release_dependency_contract',
            'exact_build_audit', 'rc_packages', 'rc_windows_install_contract', 'exclusive_native_contract',
            'exclusive_release', 'source_provenance_gate'))
        self.assertIn("['发布版本回归v4']", self.source)
        self.assertIn('loaded == result.testsRun', runner['SUITE'])
        self.assertIn('loaded == expected', runner['SUITE'])
        self.assertIn('not result.skipped', runner['SUITE'])
        self.assertIn('loaded > 0', runner['SUITE'])

    def test_original_loaded_cases_include_native_imports_and_version(self):
        import importlib
        runner = inline_namespace('RC_GROUP_RUNNER')
        loader = unittest.TestLoader()
        counts = [loader.loadTestsFromModule(importlib.import_module(name + '_tests')).countTestCases()
                  for name in runner['ORIGINAL']]
        version = loader.loadTestsFromModule(importlib.import_module('发布版本回归v4')).countTestCases()
        imported = sum(loader.loadTestsFromModule(importlib.import_module(name)).countTestCases()
            for name in ('exclusive_native_dialog_tests', 'exclusive_native_revoke_tests'))
        self.assertEqual((sum(counts) - imported, imported, version), (178, 16, 14))
        self.assertEqual(sum(counts) + version, 208)

    def test_fixed_fixture_source_and_missing_fixture_only_blocks_consumer(self):
        self.assertIn('https://static.crates.io/crates/glib/glib-0.18.5.crate', self.source)
        self.assertIn('233daaf6e83ae6a12a52055f568f9d7cf4671dabb78ff9560ab6da230ce00ee5', self.source)
        self.assertIn('--max-time 30 --max-filesize 1048576', self.source)
        self.assertIn("(label == 'consumer' and not fixture)", self.source)
        self.assertIn('passed.append(run_group(root, label))', self.source)
        self.assertIn("actual_head=git('rev-parse', 'HEAD')", self.source)
        self.assertIn("expected_tree=git('rev-parse', expected + '^{tree}')", self.source)


class DiagnosticCollectorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.raw, self.destination = self.root / 'raw', self.root / 'upload'
        self.raw.mkdir()
        self.collector = inline_namespace('RC_DIAGNOSTIC_COLLECTOR')
        self.steps = {name: 'success' for name in ('initialize', 'checkout', 'python', 'fixture', 'gate')}
        for name, expected in self.collector['EXPECTED'].items():
            self.write(name, dict(status='passed', original_exit=0, expected=expected, loaded=expected or 12,
                executed=expected or 12, skipped=0, errors=0, failures=0, log_truncated=False))
            (self.raw / (name + '.log')).write_text('synthetic unittest diagnostic\n')
        self.write('source', dict(status='passed', expected_sha='a' * 40, actual_head='a' * 40,
            actual_tree='b' * 40, expected_tree='b' * 40, predecessor_unchanged=True, exact_additions=True))
        for name in ('fixture', 'tools', 'checks'):
            self.write(name, {'status': 'passed'})

    def write(self, name, value):
        (self.raw / (name + '.json')).write_text(json.dumps(value) + '\n')

    def mutate(self, name, **changes):
        value = json.loads((self.raw / (name + '.json')).read_text())
        value.update(changes)
        self.write(name, value)

    def collect(self):
        status = self.collector['collect'](self.raw, self.destination, self.steps)
        report = json.loads((self.destination / 'collector.json').read_text())
        self.assertLessEqual(sum(path.stat().st_size for path in self.destination.iterdir()), self.collector['TOTAL_CAP'])
        self.assertTrue(all(path.is_file() and not path.is_symlink() for path in self.destination.iterdir()))
        self.assertFalse(report['execution_enabled'])
        self.assertFalse(report['publish_approved'])
        self.assertFalse(report['release_approved'])
        self.assertFalse(report['snapshot_atomic'])
        self.assertEqual(report['evidence_authentication'], 'unverified')
        return status, report

    def test_success_has_exact_regular_allowlist_and_false_authority(self):
        status, report = self.collect()
        self.assertEqual(status, 0)
        self.assertEqual(report['issues'], [])
        self.assertEqual({path.name for path in self.destination.iterdir()}, set(self.collector['ALLOWLIST']) | {'collector.json'})

    def test_group_failure_retains_original_exit_and_other_group_counts(self):
        self.mutate('pretag', status='failed', original_exit=17, failures=1)
        status, report = self.collect()
        self.assertEqual(status, 1)
        self.assertIn('group_failed_or_not_run:pretag', report['issues'])
        self.assertEqual(json.loads((self.destination / 'pretag.json').read_text())['original_exit'], 17)
        self.assertEqual(json.loads((self.destination / 'original.json').read_text())['executed'], 208)

    def test_wrong_count_zero_new_and_skips_cannot_pass(self):
        self.mutate('pretag', loaded=52, executed=52)
        self.mutate('new', loaded=0, executed=0)
        self.mutate('original', skipped=1)
        status, report = self.collect()
        self.assertEqual(status, 1)
        for name in ('new', 'pretag', 'original'):
            self.assertIn('group_failed_or_not_run:' + name, report['issues'])

    def test_boolean_counts_and_exit_are_not_numeric_proof(self):
        self.mutate('new', loaded=True, executed=True)
        self.mutate('pretag', original_exit=False)
        self.assertEqual(self.collect()[0], 1)

    def test_missing_fixture_retains_consumer_not_run(self):
        self.mutate('fixture', status='failed')
        self.mutate('consumer', status='not_run', original_exit=None, loaded=None, executed=None,
                    reason='required_fixture_unavailable')
        self.steps['fixture'] = 'failure'
        status, report = self.collect()
        self.assertEqual(status, 1)
        self.assertIn('fixture_failed_or_unavailable', report['issues'])
        self.assertEqual(json.loads((self.destination / 'original.json').read_text())['status'], 'passed')
        self.assertEqual(json.loads((self.destination / 'consumer.json').read_text())['status'], 'not_run')

    def test_missing_source_has_no_base_fallback(self):
        (self.raw / 'source.json').unlink()
        status, report = self.collect()
        self.assertEqual(status, 1)
        self.assertIn('source_not_bound', report['issues'])
        self.assertNotIn(BASE, (self.destination / 'collector.json').read_text())

    def test_wrong_source_tree_or_head_is_not_bound(self):
        self.mutate('source', actual_head='c' * 40, actual_tree='d' * 40)
        self.assertIn('source_not_bound', self.collect()[1]['issues'])

    def test_truncation_is_bounded_and_fails_without_masking_exit(self):
        (self.raw / 'new.log').write_bytes(b'x' * (self.collector['PER_FILE_CAP'] + 1))
        self.mutate('new', status='failed', original_exit=9)
        status, report = self.collect()
        self.assertEqual(status, 1)
        self.assertIn('oversize_or_truncated', report['issues'])
        self.assertEqual((self.destination / 'new.log').stat().st_size, self.collector['PER_FILE_CAP'])
        self.assertEqual(json.loads((self.destination / 'new.json').read_text())['original_exit'], 9)

    def test_runner_reported_log_truncation_also_fails(self):
        self.mutate('new', log_truncated=True)
        self.assertEqual(self.collect()[0], 1)

    def test_aggregate_cap_includes_collector_receipt(self):
        for name in self.collector['ALLOWLIST']:
            (self.raw / name).write_bytes(b'x' * self.collector['PER_FILE_CAP'])
        status, report = self.collect()
        self.assertEqual(status, 1)
        self.assertIn('oversize_or_truncated', report['issues'])

    def test_unexpected_file_is_rejected_without_retention(self):
        (self.raw / 'unapproved-payload.zip').write_bytes(b'do not retain')
        status, report = self.collect()
        self.assertEqual(status, 1)
        self.assertIn('unexpected_file', report['issues'])
        self.assertFalse((self.destination / 'unapproved-payload.zip').exists())

    def test_symlink_is_rejected_without_following(self):
        outside = self.root / 'private.txt'
        outside.write_text('synthetic forbidden sentinel')
        (self.raw / 'new.log').unlink()
        (self.raw / 'new.log').symlink_to(outside)
        status, report = self.collect()
        self.assertEqual(status, 1)
        self.assertFalse((self.destination / 'new.log').exists())
        self.assertNotIn('synthetic forbidden sentinel', (self.destination / 'collector.json').read_text())

    def test_missing_raw_directory_retains_failure_receipt(self):
        self.raw = self.root / 'absent'
        status, report = self.collect()
        self.assertEqual(status, 1)
        self.assertIn('missing_or_linked_raw_directory', report['issues'])

    def test_nonobject_json_retains_failure_instead_of_crashing_collector(self):
        (self.raw / 'new.json').write_text('[]\n')
        status, report = self.collect()
        self.assertEqual(status, 1)
        self.assertIn('missing_linked_or_invalid_file', report['issues'])

    def test_raw_directory_symlink_is_never_followed(self):
        alternate = self.root / 'other'
        self.raw.rename(alternate)
        self.raw.symlink_to(alternate, target_is_directory=True)
        status, report = self.collect()
        self.assertEqual(status, 1)
        self.assertIn('missing_or_linked_raw_directory', report['issues'])
        self.assertEqual({path.name for path in self.destination.iterdir()}, {'collector.json'})

    def test_linked_evidence_parent_is_rejected_before_writing(self):
        parent_link = self.root / 'linked'
        parent_link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'unsafe_evidence_directory'):
            self.collector['collect'](parent_link / 'raw', parent_link / 'upload', self.steps)
        self.assertFalse(self.destination.exists())

    def test_checkout_setup_and_cancelled_steps_cannot_be_hidden(self):
        self.steps.update(checkout='failure', python='skipped', gate='cancelled')
        status, report = self.collect()
        self.assertEqual(status, 1)
        self.assertEqual(report['steps']['gate'], 'cancelled')
        self.assertIn('workflow_step_failed_or_not_run', report['issues'])
        self.assertIn('runner loss', report['limitation'])

    def test_existing_destination_is_never_reused(self):
        self.destination.mkdir()
        with self.assertRaises(FileExistsError):
            self.collector['collect'](self.raw, self.destination, self.steps)


if __name__ == '__main__':
    unittest.main()
