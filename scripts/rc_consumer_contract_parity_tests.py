"""Explicit-consumer parity with unchanged producer audit rejection contracts."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import rc_consumer_noncloud as consumer
from rc_consumer_fixtures import ConsumerFixture, write_json, write_lock
from rc_consumer_io import json_file
import release_dependency_contract as old
import release_dependency_contract_tests as producer_tests
import verify_glib_backport as glib
import verify_glib_backport_tests as source_tests


def producer_for(expected, workflow):
    return SimpleNamespace(repository=old.REPOSITORY, repository_id=1,
        source_sha=expected['source_sha'], source_tree=expected['source_tree'],
        version=expected['version'], run_id=int(expected['run_id']), run_attempt=1,
        workflow_ref=workflow, workflow_id=2, bundle_job_id=3, artifact_id=4,
        artifact_sha256='a'*64, artifact_size=100)


class ExistingCaptureNegatives(producer_tests.RawCaptureContracts):
    """Run each existing producer capture negative against the new entrypoint."""
    def verify(self):
        producer = producer_for(self.expected, self.env['GITHUB_WORKFLOW_REF'])
        return consumer.verify_consumed_noncloud_audits(self.root, self.directory, producer)


class ConsumerAuditNegatives(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.f = ConsumerFixture(self.temp.name)

    def verify(self):
        return consumer.verify_consumed_noncloud_audits(self.f.root, self.f.contracts, self.f.producer)

    def save_audit(self, value, name='desktop'):
        path = self.f.contracts / f'rust-audit-{name}.json'
        write_json(path, value)
        capture = json_file(self.f.contracts / 'raw-audit-capture.json')
        capture['reports'][name]['raw_sha256'] = old.hash_file(path)
        write_json(self.f.contracts / 'raw-audit-capture.json', capture)

    def test_old_and_new_same_negative_raw_audit_matrix(self):
        path = self.f.contracts / 'rust-audit-desktop.json'
        original = json_file(path)
        mutations = [lambda a: a['vulnerabilities'].update(count=False),
            lambda a: a['vulnerabilities'].update(count=0.0),
            lambda a: a['vulnerabilities'].update(found=True),
            lambda a: a['vulnerabilities'].update(list=[{}]),
            lambda a: a['database'].update(**{'advisory-count': False}),
            lambda a: a['lockfile'].update(**{'dependency-count': True}),
            lambda a: a['lockfile'].update(**{'dependency-count': 1.0}),
            lambda a: a['settings'].update(informational_warnings=['notice']),
            lambda a: a['settings'].update(ignore=['RUSTSEC-2024-0429']),
            lambda a: a['settings'].update(target_os=['linux']),
            lambda a: a['settings'].update(target_arch=['x86_64']),
            lambda a: a['settings'].update(severity='critical'),
            lambda a: a.update(warnings={'unknown': []}),
            lambda a: a.update(warnings={'yanked': {}}),
            lambda a: a.update(warnings=None),
            lambda a: a['database'].update(**{'last-commit': '0'*40})]
        env = dict(GITHUB_RUN_ATTEMPT='1', GITHUB_WORKFLOW_REF=self.f.producer.workflow_ref)
        for mutate in mutations:
            value = copy.deepcopy(original)
            mutate(value)
            self.save_audit(value)
            with self.subTest(mutation=mutate), self.assertRaises((ValueError, TypeError, KeyError)):
                self.verify()
            with patch.dict(os.environ, env), self.assertRaises((ValueError, TypeError, KeyError)):
                old.verify_noncloud_audits(self.f.root, self.f.contracts, self.f.expected)

    def test_any_noncloud_finding_blocks_and_mapped_warnings_are_retained(self):
        audit = json_file(self.f.contracts / 'rust-audit-desktop.json')
        package = copy.deepcopy(self.f.noncloud_locks['desktop']['package'][0])
        warning = dict(kind='unmaintained', package=package,
            advisory=dict(id='RUSTSEC-2024-0001', package=package['name'], informational='unmaintained'))
        audit['warnings'] = {'unmaintained': [warning]}
        self.save_audit(audit)
        self.assertEqual(self.verify()['desktop']['raw_warnings'], audit['warnings'])
        audit['vulnerabilities'] = dict(found=True, count=1, list=[dict(package=package,
            advisory=dict(id='RUSTSEC-2023-0071'))])
        self.save_audit(audit)
        with self.assertRaisesRegex(ValueError, 'active_or_unproven'):
            self.verify()

    def test_all_unsound_unknown_unmapped_warning_cases_fail(self):
        original = json_file(self.f.contracts / 'rust-audit-desktop.json')
        package = copy.deepcopy(self.f.noncloud_locks['desktop']['package'][0])
        warning = dict(kind='unsound', package=package,
            advisory=dict(id='RUSTSEC-2024-0429', package=package['name'], informational='unsound'))
        for mutate in (lambda w: None, lambda w: w['advisory'].update(id='UNKNOWN'),
                       lambda w: w['package'].update(version='999'),
                       lambda w: w.update(kind='notice'), lambda w: w['advisory'].update(informational='notice')):
            value = copy.deepcopy(original)
            bad = copy.deepcopy(warning)
            mutate(bad)
            value['warnings'] = {'unsound': [bad]}
            self.save_audit(value)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                self.verify()

    def test_capture_schema_digest_database_command_and_numeric_types(self):
        path = self.f.contracts / 'raw-audit-capture.json'
        original = json_file(path)
        mutations = [lambda v: v.update(schema=True), lambda v: v.update(schema=1.0),
            lambda v: v.update(audit_binary_sha256='bad'), lambda v: v.update(release_approved=0),
            lambda v: v.update(publish_approved=0), lambda v: v.update(audit_version='cargo-audit 0.1.0'),
            lambda v: v['advisory_database'].update(clean=False),
            lambda v: v['advisory_database'].update(origin='https://attacker.invalid/db'),
            lambda v: v['advisory_database'].update(commit='bad'),
            lambda v: v['advisory_database'].update(tree='bad'),
            lambda v: v['advisory_database'].update(contents_sha256='bad'),
            lambda v: v['advisory_database'].update(file_count=True),
            lambda v: v['advisory_database'].update(file_count=1.0),
            lambda v: v['advisory_database'].update(file_count=1),
            lambda v: v['reports'].pop('desktop'),
            lambda v: v['reports']['desktop'].update(command='not-a-command-list'),
            lambda v: v['reports']['desktop']['command'].__setitem__(0, {}),
            lambda v: v['reports']['desktop'].update(exit=False),
            lambda v: v['reports']['desktop'].update(exit=0.0)]
        for mutate in mutations:
            value = copy.deepcopy(original)
            mutate(value)
            write_json(path, value)
            with self.subTest(mutation=mutate), self.assertRaises((ValueError, TypeError, KeyError)):
                self.verify()

    def test_actual_consumer_environment_never_substitutes_producer_identity(self):
        with patch.dict(os.environ, dict(GITHUB_RUN_ID='999', GITHUB_RUN_ATTEMPT='999',
            GITHUB_WORKFLOW_REF='consumer/workflow', GITHUB_SHA='9'*40)):
            before = dict(os.environ)
            result = self.verify()
            self.assertEqual(dict(os.environ), before)
        self.assertEqual(set(result), {'desktop', 'local-agent', 'cloud-agent'})

    def test_local_desktop_proof_cannot_be_omitted_or_suppressed(self):
        lock = {'package': [dict(name='glib', version='0.18.5')]}
        write_lock(self.f.root / old.LOCKS['desktop'], lock)
        capture_path = self.f.contracts / 'raw-audit-capture.json'
        capture = json_file(capture_path)
        capture['reports']['desktop']['lock_sha256'] = old.hash_file(self.f.root / old.LOCKS['desktop'])
        write_json(capture_path, capture)
        with self.assertRaisesRegex(ValueError, 'scope_mismatch'):
            self.verify()
        capture['desktop_glib_source_proof_required'] = True
        write_json(capture_path, capture)
        with self.assertRaises((ValueError, OSError)):
            self.verify()


class DesktopPairedProof(unittest.TestCase):
    """Optional retained official-source proof; no download and no payload run."""
    def setUp(self):
        archive = os.environ.get('RC_CONSUMER_TEST_GLIB_ARCHIVE')
        if not archive:
            self.skipTest('Set RC_CONSUMER_TEST_GLIB_ARCHIVE for retained official source data test')
        self.archive = Path(archive)
        self.assertEqual(old.hash_file(self.archive), glib.ARCHIVE_SHA)
        self.fixture = source_tests.BackportTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        scripts = self.root / 'scripts'
        scripts.mkdir()
        shutil.copyfile(Path(glib.__file__), scripts / 'verify_glib_backport.py')
        self.directory = self.root.parent / 'audits'
        self.directory.mkdir()
        folder = self.directory / 'desktop-glib'
        folder.mkdir()
        shutil.copyfile(self.archive, folder / 'upstream.crate')
        write_json(folder / 'metadata.json', self.fixture.metadata)
        product, upstream = self.fixture.audits()
        for audit in (product, upstream):
            for kind, records in audit['warnings'].items():
                for record in records:
                    record['kind'] = kind
                    record['advisory']['informational'] = kind
        write_json(folder / 'product-raw-audit.json', product)
        write_json(folder / 'upstream-identity-raw-audit.json', upstream)
        expected = dict(source_sha='1'*40, source_tree='2'*40, version='0.6.2-rc.1', run_id='123')
        workflow = old.REPOSITORY + '/.github/workflows/final-rc-packages.yml@refs/heads/release/full-rc-candidate-fixture'
        self.producer = producer_for(expected, workflow)
        capture = dict(schema=1, sha=expected['source_sha'], tree=expected['source_tree'],
            product_version=expected['version'], run_id='123', run_attempt='1', repository=old.REPOSITORY,
            workflow_ref=workflow, job='contracts', audit_version='cargo-audit 0.22.2', audit_binary_sha256='a'*64,
            source_root=str(self.root), desktop_glib_source_proof_required=True,
            release_approved=False, publish_approved=False, reports={}, advisory_database=dict(clean=True,
                origin='https://github.com/RustSec/advisory-db.git', commit='3'*40, tree='4'*40,
                contents_sha256='5'*64, file_count=1300))
        for name in ('desktop', 'local-agent', 'cloud-agent'):
            lock = self.fixture.lock if name == 'desktop' else {'package': [self.fixture.lock['package'][-1]]}
            report = product if name == 'desktop' else self.fixture.report(lock)
            write_lock(self.root / old.LOCKS[name], lock)
            write_json(self.directory / f'rust-audit-{name}.json', report)
            capture['reports'][name] = dict(command=['/recorded/cargo-audit', 'audit', '--no-fetch', '--db',
                '/recorded/db', '--json', '--file', old.LOCKS[name]], exit=0,
                lock_sha256=old.hash_file(self.root / old.LOCKS[name]),
                raw_sha256=old.hash_file(self.directory / f'rust-audit-{name}.json'))
        write_json(self.directory / 'raw-audit-capture.json', capture)

    def verify(self):
        return consumer.verify_consumed_noncloud_audits(self.root, self.directory, self.producer)

    def test_real_official_source_and_paired_raw_advisory_survive_sanitization(self):
        before = dict(os.environ)
        spec = importlib.util.spec_from_file_location
        seen = []
        def checked_import(name, path):
            self.assertEqual(path, self.root / 'scripts/verify_glib_backport.py')
            seen.append(path)
            return spec(name, path)
        with patch.object(importlib.util, 'spec_from_file_location', side_effect=checked_import), \
             patch('subprocess.run', side_effect=AssertionError('no source or payload execution')):
            result = self.verify()
        self.assertEqual(before, dict(os.environ))
        self.assertTrue(seen)
        summary = consumer.audit_summary(result['desktop'])
        self.assertTrue(summary['desktop_source']['source_backport_verified'])
        self.assertEqual(summary['desktop_source']['upstream_identity_warning_counts']['unsound'], 1)
        self.assertFalse(summary['desktop_source']['installed_desktop_bytes_verified'])
        self.assertIn('RUSTSEC-2024-0429', json.dumps(result['desktop']))

    def test_actual_consumer_overrides_and_changed_upstream_proof_fail(self):
        with patch.dict(os.environ, {'CARGO_SOURCE_CRATES_IO_REPLACE_WITH': 'unreviewed'}):
            before = dict(os.environ)
            with self.assertRaisesRegex(ValueError, 'source_override_environment'):
                self.verify()
            self.assertEqual(before, dict(os.environ))
        path = self.directory / 'desktop-glib/upstream.crate'
        path.write_bytes(path.read_bytes() + b'changed')
        with self.assertRaisesRegex(ValueError, 'wrong_official_archive'):
            self.verify()

    def test_upstream_unsound_advisory_and_paired_product_cannot_be_removed(self):
        path = self.directory / 'desktop-glib/upstream-identity-raw-audit.json'
        original = json_file(path)
        value = copy.deepcopy(original)
        value['warnings'] = {}
        write_json(path, value)
        with self.assertRaisesRegex(ValueError, 'missing_upstream_unsound_advisory'):
            self.verify()
        write_json(path, original)
        path = self.directory / 'desktop-glib/product-raw-audit.json'
        value = json_file(path)
        value['warnings'] = {}
        write_json(path, value)
        with self.assertRaisesRegex(ValueError, 'paired_product_audit_changed'):
            self.verify()


if __name__ == '__main__':
    unittest.main()
