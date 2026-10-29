"""Hermetic hostile content contracts. Synthetic positives are not acceptance."""
import ast
import copy
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import cloud_release_bundle as cloud
import exact_build_audit as exact
import final_rc_evidence as final
import rc_consumer_contracts as consumer
from rc_consumer_fixtures import ConsumerFixture, write_json
from rc_consumer_io import json_file
import release_dependency_contract as dependency


class ContentContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.f = ConsumerFixture(self.temp.name)

    def reject_json(self, path, mutations, *, inventory=False, pattern=None):
        original = json_file(path)
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                value = copy.deepcopy(original)
                mutate(value)
                write_json(path, value)
                if inventory:
                    self.f.refresh_inventory()
                with self.assertRaisesRegex((ValueError, TypeError, KeyError), pattern or '.'):
                    self.f.verify()
        write_json(path, original)
        if inventory:
            self.f.refresh_inventory()

    def test_full_positive_recomputes_without_payload_execution_or_environment_changes(self):
        before = dict(os.environ)
        run = subprocess.run
        observed = []
        def git_only(argv, **kwargs):
            allowed = [['git', 'rev-parse', 'HEAD'], ['git', 'rev-parse', 'HEAD^{tree}'],
                       ['git', 'status', '--porcelain', '--untracked-files=all'], ['git', 'ls-files']]
            self.assertIn(argv, allowed)
            self.assertEqual(kwargs['cwd'], self.f.root)
            observed.append(argv)
            return run(argv, **kwargs)
        with patch.object(subprocess, 'run', side_effect=git_only), \
             patch.object(dependency, 'current_producer', side_effect=AssertionError('producer environment')), \
             patch.object(dependency, 'verify_archive', side_effect=AssertionError('producer archive')), \
             patch.object(dependency, 'verify_noncloud_audits', side_effect=AssertionError('producer audits')), \
             patch.object(final, 'bundle', side_effect=AssertionError('producer bundle')), \
             patch.object(cloud, 'probe', side_effect=AssertionError('payload execution')):
            result = self.f.verify()
        self.assertTrue(observed)
        self.assertEqual(before, dict(os.environ))
        self.assertEqual([a['family'] for a in result['assets']], ['nsis', 'deb', 'appimage', 'cloud'])
        self.assertEqual(len(result['installed_platforms']), 5)
        self.assertEqual(result['audits']['cloud']['raw_vulnerability_count'], 1)
        self.assertEqual(result['audits']['cloud']['active_vulnerability_count'], 0)
        self.assertEqual(result['audits']['cloud']['warning_counts']['yanked'], 1)
        self.assertFalse(result['publish_approved'])
        self.assertFalse(result['release_approved'])
        self.assertFalse(result['raw_zero_claim'])
        self.assertFalse(result['signing']['windows_payload_signature_observed'])

    def test_packaging_identity_approvals_scope_blockers_and_schema(self):
        mutations = [lambda v, k=k: v.update({k: 'wrong'}) for k in
                     ('source_sha', 'source_tree', 'version', 'run_id')]
        mutations += [lambda v: v.update(passed=1), lambda v: v.update(release_approved=0),
                      lambda v: v.update(publish_approved=True), lambda v: v.update(scope='approved'),
                      lambda v: v.update(release_blockers=[]), lambda v: v.update(schema=True),
                      lambda v: v.update(schema=1.0), lambda v: v.update(schema=2)]
        self.reject_json(self.f.bundle / 'packaging-report.json', mutations)

    def test_trusted_context_cannot_be_invented_from_receipts(self):
        original = copy.deepcopy(self.f.producer)
        for field, value in [('run_attempt', 2), ('run_attempt', True), ('run_id', 123.0),
                             ('source_sha', '9'*40), ('source_tree', '9'*40), ('artifact_id', False),
                             ('workflow_ref', dependency.REPOSITORY + '/.github/workflows/full-rc-cloud-binaries.yml@refs/heads/main')]:
            with self.subTest(field=field, value=value):
                setattr(self.f.producer, field, value)
                with self.assertRaises(ValueError):
                    self.f.verify()
                self.f.producer = copy.deepcopy(original)

    def test_inventory_checks_all_contract_bytes_before_parsing_them(self):
        path = self.f.contracts / 'npm-audit.json'
        path.write_bytes(path.read_bytes() + b' ')
        with self.assertRaisesRegex(ValueError, 'contract_inventory_mismatch'):
            self.f.verify()

    def test_older_integration_and_wrong_job_ids_fail_in_both_receipts(self):
        for folder in (self.f.contracts, self.f.cloud):
            self.reject_json(folder / 'integration.json', [
                lambda v: v.update(integration_run_id='455'),
                lambda v: v.update(source_sha='9'*40),
                lambda v: v['jobs'][0].update(id=999),
                lambda v: v['jobs'][0].update(id=True),
                lambda v: v['jobs'][0].update(id=1.0),
                lambda v: v['jobs'][0].update(name='unknown'),
                lambda v: v['jobs'].pop(),
                lambda v: v['jobs'].append(v['jobs'][0]),
            ], inventory=folder == self.f.contracts,
                pattern='integration_receipt|stale_integration')

    def test_npm_total_boolean_float_error_and_nonzero_fail(self):
        self.reject_json(self.f.contracts / 'npm-audit.json', [
            lambda v, n=n: v['metadata']['vulnerabilities'].update(total=n)
            for n in (False, 0.0, '0', 1)] + [lambda v: v.update(error=None)],
            inventory=True, pattern='npm_zero')

    def test_linux_records_versions_architecture_and_generated_names(self):
        self.reject_json(self.f.bundle / 'evidence/rc-linux-packages/exclusive-package.json', [
            lambda v: v.update(build_kind='release-packaged'),
            lambda v: v['packages'].pop('deb'),
            lambda v: v['packages']['deb'].update(package_version=self.f.version),
            lambda v: v['packages']['appimage'].update(package_version='0.6.1'),
            lambda v: v['packages']['deb'].update(architecture='arm64'),
            lambda v: v['packages']['deb']['artifact'].update(name='old-version.deb'),
            lambda v: v['packages']['deb']['artifact'].update(size=True),
            lambda v: v['packages']['deb']['artifact'].update(size=30.0),
            lambda v: v['packages']['appimage'].update(payload_sha256='wrong'),
        ])

    def test_package_root_and_nested_copies_and_missing_families(self):
        for path in [self.f.bundle / a['name'] for a in self.f.verify()['assets']]:
            original = path.read_bytes()
            path.write_bytes(original + b'altered')
            with self.subTest(path=path.name), self.assertRaises(ValueError):
                self.f.verify()
            path.write_bytes(original)
        for name in ('rc-linux-packages', 'rc-windows-package'):
            folder = self.f.bundle / 'evidence' / name
            package = next(p for p in folder.iterdir() if p.name.startswith('MCP_'))
            original = package.read_bytes()
            package.write_bytes(original + b'changed')
            with self.assertRaises(ValueError):
                self.f.verify()
            package.write_bytes(original)

    def test_all_five_native_receipts_are_mandatory(self):
        for path in self.f.bundle.rglob('exclusive-native.json'):
            original = path.read_bytes()
            path.unlink()
            with self.subTest(path=path.parent.name), self.assertRaises((ValueError, OSError)):
                self.f.verify()
            path.write_bytes(original)
            path.chmod(0o600)

    def test_native_numeric_boundary_accepts_90_point_5_rejects_bool_nonfinite(self):
        path = self.f.bundle / 'evidence/rc-windows-package/exclusive-native.json'
        self.assertEqual(json_file(path)['pending_elapsed_seconds'], 90.5)
        self.f.verify()
        self.reject_json(path, [lambda v, n=n: v.update(pending_elapsed_seconds=n)
                               for n in (True, False, 89.999, '90', float('nan'), float('inf'))] +
                         [lambda v: v.update(foreign_request_count=100.0)])
        original = path.read_text()
        path.write_text(original.replace('90.5', '1e999'))
        with self.assertRaises(ValueError):
            self.f.verify()

    def test_native_twelve_stages_and_all_observation_boundaries(self):
        path = self.f.bundle / 'evidence/rc-linux-installed-ubuntu-24.04-appimage/exclusive-native.json'
        mutations = [lambda v, k=k: v.update({k: False}) for k in
            ('passed', 'real_native_webview', 'real_oauth_http', 'real_local_ipc', 'cleanup_completed',
             'export_secret_scan_completed', 'synthetic_conversation_metadata')]
        mutations += [lambda v, k=k: v.update({k: True}) for k in
            ('sandbox_disabled', 'cleanup_failed', 'real_chatgpt_verified', 'export_secrets_found')]
        mutations += [lambda v: v['tests'].pop(), lambda v: v['tests'].reverse(),
                      lambda v: v['tests'][0].update(passed=False),
                      lambda v: v.update(binary_sha256='a'*64),
                      lambda v: v.update(permission_approval_source='simulated')]
        self.reject_json(path, mutations)

    def test_appimage_native_hash_is_outer_installer_deb_hash_is_payload(self):
        for kind in ('deb', 'appimage'):
            folder = self.f.bundle / 'evidence' / f'rc-linux-installed-ubuntu-22.04-{kind}'
            self.reject_json(folder / 'rc-package.json', [
                lambda v, k=kind: v.update(native_executable_sha256=
                    v['payload_sha256'] if k == 'appimage' else v['package']['sha256'])],
                pattern='installed_linux_payload_mismatch')

    def test_windows_payload_native_consistency_and_honest_signing(self):
        folder = self.f.bundle / 'evidence/rc-windows-package'
        self.reject_json(folder / 'rc-windows-package.json', [
            lambda v: v.update(payload_sha256='b'*64), lambda v: v.update(signed='true'),
            lambda v: v.update(real_chatgpt_verified=True), lambda v: v.update(silent_install=False),
            lambda v: v.update(exact_nsis_payload_verified=False), lambda v: v.update(real_native_approval=False)])
        self.reject_json(folder / '安装载荷核验v7.json', [
            lambda v: v.update(installed_sha256='b'*64), lambda v: v.update(expected_installed_sha256='b'*64),
            lambda v: v.update(source_sha='9'*40), lambda v: v.update(marker_offset=True),
            lambda v: v['observed'].append(dict(v['observed'][0], path='other.exe')),
            lambda v: v['observed'][0].update(bytes=True), lambda v: v.update(cli_version='unreviewed')])

    def test_cloud_manifest_and_build_envelope_identities(self):
        self.reject_json(self.f.unpacked / 'manifest.json', [
            lambda v, k=k: v.update({k: 'wrong'}) for k in
            ('source_sha', 'source_tree', 'run_id', 'product_version', 'target', 'build_os')])
        self.reject_json(self.f.unpacked / 'manifest.json', [
            lambda v: v.update(schema=True), lambda v: v.update(schema=1.0),
            lambda v: v.update(publish_approved=0), lambda v: v['binaries'].pop(cloud.BINS[0]),
            lambda v: v['binaries'][cloud.BINS[0]].update(size=True),
            lambda v: v['binaries'][cloud.BINS[0]].update(size=1.0)])
        self.reject_json(self.f.exact / 'envelope.json', [
            lambda v: v['ci'].update(run_attempt='2'), lambda v: v['ci'].update(job='contracts'),
            lambda v: v['ci'].update(workflow_ref=dependency.REPOSITORY + '/.github/workflows/issue85-exact-build-audit.yml@refs/heads/ci')],
            pattern='cloud_build_producer')

    def test_cloud_binary_missing_modified_and_non_elf(self):
        victim = self.f.unpacked / 'bin' / cloud.BINS[0]
        original = victim.read_bytes()
        victim.write_bytes(b'not ELF' + original)
        with self.assertRaises(ValueError):
            self.f.verify()
        victim.unlink()
        with self.assertRaises((ValueError, OSError)):
            self.f.verify()

    def test_recomputed_dependency_report_cannot_be_replaced_by_success_string(self):
        self.reject_json(self.f.bundle / 'packaging-report.json', [
            lambda v: v.update(dependency_contract={}),
            lambda v: v['dependency_contract'].update(raw_zero_claim=True),
            lambda v: v['dependency_contract']['cloud'].update(raw_vulnerability_count=0),
            lambda v: v['dependency_contract'].update(release_approved=True)],
            pattern='recorded_dependency_contract')

    def test_untrusted_diagnostics_and_paths_do_not_enter_public_summary(self):
        folder = self.f.bundle / 'evidence/rc-windows-package'
        path = folder / 'exclusive-native.json'
        value = json_file(path)
        value.update(diagnostic='PRIVATE_CANARY', token='not-a-real-secret', path='/private/path')
        write_json(path, value)
        raw = json.dumps(self.f.verify())
        for text in ('PRIVATE_CANARY', 'not-a-real-secret', '/private/path', '/repo', 'C:\\private', 'executables'):
            self.assertNotIn(text, raw)

    def test_static_consumer_does_not_call_producer_or_environment_mutators(self):
        for path in (Path(consumer.__file__), Path(consumer.verify_consumed_noncloud_audits.__code__.co_filename)):
            tree = ast.parse(path.read_text())
            calls = [ast.unparse(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)]
            forbidden = ('current_producer', 'verify_archive', 'verify_noncloud_audits', 'extractall',
                         '.probe', '.inspect_linux', 'os.environ', 'subprocess', '.collect')
            self.assertFalse([call for call in calls if any(f in call for f in forbidden)])


if __name__ == '__main__':
    unittest.main()
