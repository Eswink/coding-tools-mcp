#!/usr/bin/env python3
"""Synthetic boundary contracts only; live Cargo/GLib proof requires hosted CI."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import engineering_dependency_capture as gate
from release_dependency_contract_tests import write_lock


class EngineeringCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'source'
        self.root.mkdir()
        self.output = self.base / 'capture'
        self.database = self.base / 'database'
        self.audit = self.base / 'cargo-audit'
        self.audit.write_bytes(b'synthetic audit identity')
        self.source = dict(sha='a' * 40, tree='b' * 40, product_version='0.7.0-rc.1',
                           target=gate.TARGET, manifest_sha256='c' * 64, lock_sha256='d' * 64)
        self.snapshot = dict(commit='e' * 40, tree='f' * 40, contents_sha256='a' * 64,
                             origin='https://github.com/RustSec/advisory-db.git', clean=True, file_count=50)
        self.package = dict(name='example', version='1.0.0', source='registry+https://github.com/rust-lang/crates.io-index', checksum='1' * 64)
        self.locks = {name: dict(version=3, package=[copy.deepcopy(self.package)]) for name in gate.contract.LOCKS}
        self.locks['desktop']['package'].append(dict(name='glib', version='0.18.5'))
        for name, path in gate.contract.LOCKS.items():
            write_lock(self.root / path, self.locks[name])
        self.upstream_lock = dict(version=3, package=[dict(self.package, name='glib', version='0.18.5')])
        write_lock(self.root / 'patches/glib-0.18.5/upstream-identity.Cargo.lock', self.upstream_lock)
        self.env = dict(GITHUB_ACTIONS='true', GITHUB_REPOSITORY=gate.contract.REPOSITORY,
                        GITHUB_WORKFLOW_REF=gate.WORKFLOW, GITHUB_SHA=self.source['sha'], GITHUB_JOB='capture',
                        GITHUB_RUN_ID='123', GITHUB_RUN_ATTEMPT='1')
        self.collector_exit = 0
        self.gateway_exit = 0
        self.gateway_report = self.report(self.locks['cloud-gateway'])
        self.proof = dict(required=True, source_backport_verified=True)
        self.stack = []
        for context in (patch.dict(os.environ, self.env),
                        patch.object(gate.exact, 'source_identity', return_value=self.source),
                        patch.object(gate.exact, 'database_identity', return_value=self.snapshot),
                        patch.object(gate.contract, 'desktop_source_proof', return_value=self.proof),
                        patch.object(gate.exact, 'execute', side_effect=self.execute)):
            self.stack.append(context.start())
            self.addCleanup(context.stop)

    def report(self, lock):
        return dict(settings=dict(target_arch=[], target_os=[], severity=None, ignore=[],
                                  informational_warnings=['unmaintained', 'unsound', 'notice']),
                    database={'advisory-count': 10, 'last-commit': None},
                    lockfile={'dependency-count': len(lock['package'])},
                    vulnerabilities=dict(found=False, count=0, list=[]), warnings={})

    def finding(self, package=None, kind=None):
        package = copy.deepcopy(package or self.package)
        value = dict(package=package, advisory=dict(id='RUSTSEC-2024-0429', package=package['name'], informational=kind))
        if kind:
            value['kind'] = kind
        return value

    def noncloud(self):
        folder = self.output / 'noncloud'
        folder.mkdir()
        self.database.mkdir()
        reports = {}
        for name in ('desktop', 'local-agent', 'cloud-agent'):
            raw = json.dumps(self.report(self.locks[name])).encode()
            (folder / ('rust-audit-' + name + '.json')).write_bytes(raw)
            (folder / ('rust-audit-' + name + '.stderr')).write_bytes(b'untouched stderr')
            reports[name] = dict(command=[str(self.audit), 'audit', '--no-fetch', '--db', str(self.database),
                                         '--json', '--file', gate.contract.LOCKS[name]], exit=0,
                                 raw_sha256=gate.exact.digest(raw), lock_sha256=gate.contract.hash_file(self.root / gate.contract.LOCKS[name]))
        captured = dict(schema=1, **{**self.source, **gate.producer(self.source['sha'])}, source_root=str(self.root),
                        audit_version='cargo-audit 0.22.2', audit_binary_sha256=gate.contract.hash_file(self.audit),
                        advisory_database=self.snapshot, reports=reports, desktop_glib_source_proof_required=True,
                        release_approved=False, publish_approved=False)
        gate.write_json(folder / 'raw-audit-capture.json', captured)
        glib_folder = folder / 'desktop-glib'
        glib_folder.mkdir()
        gate.write_json(glib_folder / 'metadata.json', {'packages': [self.package]})
        (glib_folder / 'upstream.crate').write_bytes(b'archive bytes are mocked in these unit tests')
        glib = dict(advisory_database=self.snapshot, audit_binary_sha256=gate.contract.hash_file(self.audit),
                    audit_version='cargo-audit 0.22.2', release_approved=False, raw_zero_claim=False, audit_commands={},
                    source_backport_verified=True, metadata_package_count=1, product_lock_sha256=gate.contract.hash_file(self.root / 'src-tauri/Cargo.lock'))
        for name, path in (('product', 'src-tauri/Cargo.lock'), ('upstream-identity', 'patches/glib-0.18.5/upstream-identity.Cargo.lock')):
            report = self.report(self.locks['desktop'] if name == 'product' else self.upstream_lock)
            if name == 'upstream-identity':
                report['warnings']['unsound'] = [self.finding(self.upstream_lock['package'][0], 'unsound')]
            raw = json.dumps(report).encode()
            (glib_folder / (name + '-raw-audit.json')).write_bytes(raw)
            (glib_folder / (name + '-raw-audit.stderr')).write_bytes(b'raw warning stderr')
            glib['audit_commands'][name] = dict(command=[str(self.audit), 'audit', '--no-fetch', '--db', str(self.database),
                                                       '--file', path, '--json'], exit=0, report_sha256=gate.exact.digest(raw))
        gate.write_json(glib_folder / 'summary.json', glib)

    def execute(self, argv, root):
        if argv[0] in ('cargo', 'rustc'):
            return 0, (argv[0] + ' 1.98.1 (fixture)\n').encode(), b''
        if argv[-1] == '--version':
            return 0, b'cargo-audit 0.22.2\n', b''
        if argv[1].endswith('release_dependency_capture.py'):
            self.noncloud()
            return self.collector_exit, b'collector stdout', b'collector stderr'
        return self.gateway_exit, json.dumps(self.gateway_report).encode(), b'gateway raw stderr'

    def collect(self):
        return gate.collect(self.root, self.output, self.audit, self.database, self.source['sha'], self.source['product_version'])

    def verify(self, digest=None):
        return gate.verify(self.root, self.output, self.source['sha'], self.source['product_version'],
                           digest or gate.contract.hash_file(self.output / gate.RECEIPT))

    def refresh_manifest(self, change=None):
        path = self.output / gate.RECEIPT
        receipt = gate.exact.decode(path.read_bytes())
        if change:
            change(receipt)
        receipt['files'] = gate.inventory(self.output)
        gate.write_json(path, receipt)

    def test_complete_capture_retains_four_reports_and_no_authority(self):
        result = self.collect()
        self.assertEqual(set(result['reports']), set(gate.contract.LOCKS))
        self.assertEqual(result['pipeline_integrity'], 'verified')
        self.assertEqual(result['security_acceptance'], 'not_evaluated')
        for key, value in gate.FLAGS.items():
            self.assertIs(result[key], value)
        self.assertEqual((self.output / 'gateway.stderr').read_bytes(), b'gateway raw stderr')
        self.assertEqual(self.verify()['receipt_sha256'], result['receipt_sha256'])
        self.assertTrue(self.stack[3].called)

    def test_legitimate_finding_exit_one_remains_visible(self):
        self.gateway_report['vulnerabilities'] = dict(found=True, count=1, list=[self.finding()])
        self.gateway_exit = 1
        result = self.collect()
        self.assertEqual(result['reports']['cloud-gateway']['vulnerability_count'], 1)
        self.assertFalse(result['raw_zero_claim'])
        self.assertEqual(json.loads((self.output / 'gateway.stdout').read_bytes()), self.gateway_report)

    def test_exit_mismatch_invalid_counts_and_tool_errors_rejected(self):
        for code, count, found, values in ((0, 1, True, [self.finding()]), (1, 0, False, []),
                                         (2, 0, False, []), (0, True, False, []), (1, 2, True, [self.finding()])):
            with self.subTest(code=code, count=count):
                report = self.report(self.locks['cloud-gateway'])
                report['vulnerabilities'] = dict(count=count, found=found, list=values)
                with self.assertRaises(ValueError):
                    gate.raw_report(json.dumps(report).encode(), self.locks['cloud-gateway'], code, self.snapshot)

    def test_warning_identity_and_yanked_are_preserved_without_waiver(self):
        for kind in ('unsound', 'unmaintained', 'notice', 'yanked'):
            report = self.report(self.locks['cloud-gateway'])
            warning = self.finding(kind=kind)
            if kind == 'yanked':
                warning['advisory'] = None
            report['warnings'][kind] = [warning]
            result = gate.raw_report(json.dumps(report).encode(), self.locks['cloud-gateway'], 0, self.snapshot)
            self.assertEqual(result['warning_counts'][kind], 1)
            warning['package']['checksum'] = '2' * 64
            with self.assertRaisesRegex(ValueError, 'unmapped_finding'):
                gate.raw_report(json.dumps(report).encode(), self.locks['cloud-gateway'], 0, self.snapshot)

    def test_collector_failure_retains_diagnostics_and_does_not_emit_receipt(self):
        self.collector_exit = 7
        with self.assertRaisesRegex(ValueError, 'collector_failed'):
            self.collect()
        self.assertEqual(json.loads((self.output / 'commands.json').read_text())['collector']['exit'], 7)
        self.assertEqual((self.output / 'collector.stderr').read_bytes(), b'collector stderr')
        self.assertTrue((self.output / 'failure.json').is_file())
        self.assertFalse((self.output / gate.RECEIPT).exists())

    def test_database_drift_blocks_and_preserves_gateway_raw(self):
        self.stack[2].side_effect = [self.snapshot, {**self.snapshot, 'commit': '0' * 40}]
        with self.assertRaisesRegex(ValueError, 'database_changed'):
            self.collect()
        self.assertTrue((self.output / 'gateway.stdout').exists())

    def test_source_drift_blocks(self):
        self.stack[1].side_effect = [self.source, {**self.source, 'tree': '0' * 40}]
        with self.assertRaisesRegex(ValueError, 'source_changed'):
            self.collect()

    def test_invalid_json_keeps_original_tool_output_and_fails(self):
        original = self.execute
        self.stack[4].side_effect = lambda argv, root: (2, b'not JSON', b'network failed') if '--json' in argv else original(argv, root)
        with self.assertRaises(ValueError):
            self.collect()
        self.assertEqual((self.output / 'gateway.stdout').read_bytes(), b'not JSON')
        self.assertEqual(json.loads((self.output / 'commands.json').read_text())['gateway']['exit'], 2)

    def test_file_tamper_and_recomputed_inner_hash_reject_original_trust(self):
        result = self.collect()
        path = self.output / 'gateway.stdout'
        path.write_bytes(path.read_bytes() + b' ')
        with self.assertRaisesRegex(ValueError, 'artifact_inventory_mismatch'):
            self.verify(result['receipt_sha256'])
        self.refresh_manifest()
        with self.assertRaisesRegex(ValueError, 'untrusted_receipt_digest'):
            self.verify(result['receipt_sha256'])

    def test_extra_missing_and_linked_files_rejected(self):
        self.collect()
        extra = self.output / 'extra'
        extra.write_text('extra')
        with self.assertRaisesRegex(ValueError, 'artifact_inventory_mismatch'):
            self.verify()
        extra.unlink()
        extra.symlink_to(self.audit)
        with self.assertRaisesRegex(ValueError, 'linked_artifact'):
            self.verify()
        extra.unlink()
        (self.output / 'gateway.stderr').unlink()
        with self.assertRaisesRegex(ValueError, 'artifact_inventory_mismatch'):
            self.verify()

    def test_changed_attempt_and_claimed_release_authority_fail(self):
        self.collect()
        with patch.dict(os.environ, GITHUB_RUN_ATTEMPT='2'):
            with self.assertRaisesRegex(ValueError, 'wrong_source_or_producer'):
                self.verify()
        self.refresh_manifest(lambda receipt: receipt.update(release_approved=True))
        with self.assertRaisesRegex(ValueError, 'wrong_authority'):
            self.verify()

    def test_inner_database_tool_and_glib_exits_are_checked(self):
        self.collect()
        path = self.output / 'noncloud/desktop-glib/summary.json'
        glib = json.loads(path.read_text())
        glib['audit_commands']['upstream-identity']['exit'] = 1
        gate.write_json(path, glib)
        self.refresh_manifest()
        with self.assertRaisesRegex(ValueError, 'invalid_audit_exit'):
            self.verify()

    def test_cross_receipt_identities_and_tool_mutation_fail(self):
        self.collect()
        path = self.output / 'noncloud/raw-audit-capture.json'
        original = path.read_bytes()
        for key, value in (('audit_binary_sha256', '0' * 64), ('tree', '0' * 40),
                           ('advisory_database', {**self.snapshot, 'commit': '0' * 40}), ('publish_approved', 0)):
            with self.subTest(field=key):
                captured = json.loads(original)
                captured[key] = value
                gate.write_json(path, captured)
                self.refresh_manifest()
                with self.assertRaises(ValueError):
                    self.verify()
                path.write_bytes(original)
        self.refresh_manifest(lambda receipt: receipt['locks'].update(desktop='0' * 64))
        with self.assertRaisesRegex(ValueError, 'lock_changed'):
            self.verify()

    def test_missing_stream_cannot_be_blessed_by_rehashing(self):
        self.collect()
        (self.output / 'collector.stderr').unlink()
        self.refresh_manifest()
        with self.assertRaisesRegex(ValueError, 'incomplete_capture_streams'):
            self.verify()

    def test_audit_binary_drift_is_retained_as_failure(self):
        original = self.execute
        def mutate(argv, root):
            result = original(argv, root)
            if '--json' in argv:
                self.audit.write_bytes(b'changed tool')
            return result
        self.stack[4].side_effect = mutate
        with self.assertRaisesRegex(ValueError, 'audit_binary_changed'):
            self.collect()
        self.assertTrue((self.output / 'failure.json').is_file())

    def test_workflow_is_exact_branch_read_only_and_digest_is_external(self):
        text = (Path(__file__).resolve().parents[1] / '.github/workflows/issue85-dependency-capture.yml').read_text()
        self.assertIn("branches: ['" + gate.BRANCH + "']", text)
        self.assertEqual(text.count("github.repository == 'Eswink/coding-tools-mcp'"), 2)
        self.assertIn('contents: read', text)
        self.assertIn('needs.capture.outputs.receipt_sha256', text)
        for forbidden in ('workflow_dispatch', 'secrets.', 'contents: write', 'cargo build', 'final-rc-packages'):
            self.assertNotIn(forbidden, text)


if __name__ == '__main__':
    unittest.main()
