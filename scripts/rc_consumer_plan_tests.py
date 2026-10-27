"""Synthetic API/byte/content integration and sanitized output, no live transport."""
from contextlib import ExitStack
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import rc_artifact_consumer as consumer
from rc_consumer_fixtures import ConsumerFixture
from rc_consumer_io import ConsumerError, PrivateRoot
import rc_consumer_snapshot as snapshot
from rc_consumer_transport_tests import HOST, URL, Opener, Response


class API:
    """Authenticated-API-shaped synthetic reads, never production trust input."""
    token = 'fixture-token'

    def __init__(self, fixture, data):
        self.calls = []
        f = fixture
        self.expected = dict(rc_version=f.version, release_tag='v' + f.version, source_sha=f.sha,
                             final_run_id=123, final_run_attempt=1, integration_run_id=456,
                             integration_run_attempt=2, artifact_id=13)
        repo = dict(id=10, full_name=snapshot.REPOSITORY)
        self.data = {'/': repo}
        for run_id, attempt, workflow_id, path, names in (
                (123, 1, 11, snapshot.gate.FINAL_WORKFLOW, snapshot.gate.FINAL_JOBS),
                (456, 2, 12, snapshot.gate.final.WORKFLOW, snapshot.gate.final.REQUIRED_JOBS)):
            run = dict(id=run_id, run_attempt=attempt, run_number=run_id, workflow_id=workflow_id,
                       path=path, head_sha=f.sha, status='completed', conclusion='success',
                       event='push', head_branch='release/full-rc-candidate-fixture',
                       repository=repo, head_repository=repo, created_at='2026-10-01T00:00:00Z',
                       run_started_at='2026-10-01T00:00:00Z', updated_at='2026-10-01T00:02:00Z')
            jobs = copy.deepcopy(f.integration['jobs']) if run_id == 456 else [
                dict(id=1000 + i, name=name, run_id=run_id, run_attempt=attempt, head_sha=f.sha,
                     status='completed', conclusion='success') for i, name in enumerate(sorted(names))]
            for job in jobs:
                job.update(started_at='2026-10-01T00:00:00Z', completed_at='2026-10-01T00:01:00Z')
            self.data['/actions/workflows/' + Path(path).name] = dict(id=workflow_id, path=path)
            self.data[f'/actions/workflows/{workflow_id}/runs?head_sha={f.sha}&per_page=100&page=1'] = {
                'total_count': 1, 'workflow_runs': [run]}
            self.data[f'/actions/runs/{run_id}'] = run
            self.data[f'/actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100&page=1'] = {
                'total_count': len(jobs), 'jobs': jobs}
        artifact = dict(id=13, name='rc-structural-bundle', size_in_bytes=len(data),
                        digest='sha256:' + hashlib.sha256(data).hexdigest(), expired=False,
                        created_at='2026-10-01T00:00:30Z', updated_at='2026-10-01T00:00:31Z',
                        expires_at='2099-01-01T00:00:00Z', workflow_run=dict(id=123,
                        repository_id=10, head_repository_id=10, head_sha=f.sha,
                        head_branch='release/full-rc-candidate-fixture'))
        self.data['/actions/artifacts/13'] = artifact
        self.data['/actions/runs/123/artifacts?per_page=100&page=1'] = {
            'total_count': 1, 'artifacts': [artifact]}
        self.data['/git/ref/tags/v' + f.version] = dict(ref='refs/tags/v' + f.version,
                                                      object=dict(type='commit', sha=f.sha))
        self.candidate = dict(source_sha=f.sha, source_tree=f.tree, version=f.version,
            release_tag='v' + f.version, tag_object_sha=f.sha, consumer=dict(repository_id=10,
            run_id=999, run_attempt=1, workflow_ref=snapshot.REPOSITORY + '/' +
            snapshot.CONSUMER_WORKFLOW + '@refs/heads/fixture'))

    def get(self, path):
        self.calls.append(path)
        return copy.deepcopy(self.data[path])


def zip_bytes(directory):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(directory.rglob('*')):
            if path.is_file():
                archive.write(path, path.relative_to(directory).as_posix())
    return stream.getvalue()


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.f = ConsumerFixture(self.temp.name)
        self.data = zip_bytes(self.f.bundle)
        self.api = API(self.f, self.data)

    def invoke(self, data=None):
        body = self.data if data is None else data
        opener = Opener(Response(302, headers=[('Location', URL)]), Response(200, body))
        # Source resolution has an independent real-Git suite. This combined
        # fixture patches only that source boundary, never snapshot/API/content
        # validators, extraction, hashes, or the final freshness implementation.
        with patch.object(snapshot, 'resolve_candidate', return_value=self.api.candidate), \
             patch.object(consumer.transport, 'TRUSTED_STORAGE_HOSTS', frozenset({HOST})):
            return consumer.consume(self.f.root, self.api.expected, dict(os.environ), self.api,
                                     temporary_parent=self.temp.name, opener=opener)

    def plans(self):
        return list(Path(self.temp.name).glob('rc-consumer-receipts-*/rc-asset-plan.json'))

    def test_full_data_sequence_exact_assets_and_no_environment_changes(self):
        environment = dict(os.environ)
        result = self.invoke()
        self.assertEqual(dict(os.environ), environment)
        plan, directory = result['plan'], result['asset_directory']
        expected = {name for name, _, _ in consumer.payloads(self.f.version)} | {
            'RC_PROVENANCE.json', f'SHA256SUMS_{self.f.version}.txt'}
        self.assertEqual({p.name for p in directory.iterdir()}, expected)
        self.assertEqual({r['name'] for r in plan['assets']}, expected)
        for item in plan['assets']:
            data = (directory / item['name']).read_bytes()
            self.assertEqual(len(data), item['size'])
            self.assertEqual(hashlib.sha256(data).hexdigest(), item['sha256'])
            self.assertEqual((directory / item['name']).stat().st_mode & 0o777, 0o600)
        checksums = (directory / f'SHA256SUMS_{self.f.version}.txt').read_text().splitlines()
        self.assertEqual({line[66:] for line in checksums}, expected - {f'SHA256SUMS_{self.f.version}.txt'})
        self.assertFalse(plan['release_approved'])
        self.assertFalse(plan['publish_approved'])
        self.assertFalse(plan['snapshot_atomic'])
        self.assertEqual(plan['scope'], consumer.SCOPE)
        self.assertEqual(len(plan['installed_platforms']), 5)
        self.assertEqual(plan['audits']['cloud']['raw_vulnerability_count'], 1)
        self.assertEqual(plan['audits']['cloud']['active_vulnerability_count'], 0)
        self.assertEqual(plan['audits']['cloud']['warning_counts']['yanked'], 1)
        self.assertEqual({p.name for p in result['receipt_directory'].iterdir()},
                         {'RC_PROVENANCE.json', 'rc-asset-plan.json'})
        encoded = json.dumps(plan)
        for secret in (self.temp.name, 'C:\\private', 'signature=', self.api.token, '/fixture/', '/repo', 'installed_path'):
            self.assertNotIn(secret, encoded)
        self.assertGreaterEqual(self.api.calls.count('/actions/artifacts/13'), 3)

    def test_wrong_outer_digest_prevents_all_archive_parsers(self):
        corrupt = bytes([self.data[0] ^ 1]) + self.data[1:]
        with patch.object(consumer.archive, 'extract_bounded_zip') as parser:
            with self.assertRaisesRegex(ConsumerError, 'download_digest_mismatch'):
                self.invoke(corrupt)
            parser.assert_not_called()
        self.assertEqual(self.plans(), [])

    def test_self_updated_internal_checksums_do_not_override_api_digest(self):
        installer = next(self.f.bundle.glob('*.exe'))
        installer.write_bytes(b'changed malicious installer')
        self.f.checksums()
        rewritten = zip_bytes(self.f.bundle)
        self.api.data['/actions/artifacts/13']['size_in_bytes'] = len(rewritten)
        with patch.object(consumer.archive, 'extract_bounded_zip') as parser:
            with self.assertRaisesRegex(ConsumerError, 'download_digest_mismatch'):
                self.invoke(rewritten)
            parser.assert_not_called()
        self.assertEqual(self.plans(), [])

    def test_deletion_after_download_prevents_parsing(self):
        original = consumer.transport.download_artifact_zip
        def download(*args, **kwargs):
            result = original(*args, **kwargs)
            self.api.data['/actions/artifacts/13'] = {}
            return result
        with patch.object(consumer.transport, 'download_artifact_zip', side_effect=download), \
             patch.object(consumer.archive, 'extract_bounded_zip') as parser:
            with self.assertRaises(ConsumerError):
                self.invoke()
            parser.assert_not_called()
        self.assertEqual(self.plans(), [])

    def test_final_rerun_after_content_prevents_any_success_output(self):
        original = consumer.contracts.verify_consumed_bundle
        def content(*args):
            value = original(*args)
            self.api.data['/actions/runs/123']['run_attempt'] = 2
            return value
        with patch.object(consumer.contracts, 'verify_consumed_bundle', side_effect=content):
            with self.assertRaisesRegex(ConsumerError, 'unsupported_rerun_provenance'):
                self.invoke()
        self.assertEqual(self.plans(), [])
        self.assertTrue(list(Path(self.temp.name).glob('rc-consumer-assets-*')))
        self.assertTrue(list(Path(self.temp.name).glob('rc-consumer-receipts-*/rc-asset-plan.pending')))
        self.assertFalse(list(Path(self.temp.name).glob('rc-consumer-receipts-*/rc-asset-plan.json')))

    def test_payloads_never_executed_and_source_unchanged(self):
        original_run = consumer.snapshot.subprocess.run
        original_check = consumer.snapshot.subprocess.check_output
        seen = []
        def guard(function):
            def call(args, *rest, **kwargs):
                self.assertEqual(args[0], 'git')
                seen.append(args)
                return function(args, *rest, **kwargs)
            return call
        before = {str(p.relative_to(self.f.root)): p.read_bytes()
                  for p in self.f.root.rglob('*') if p.is_file()}
        with patch.object(consumer.snapshot.subprocess, 'run', side_effect=guard(original_run)), \
             patch.object(consumer.snapshot.subprocess, 'check_output', side_effect=guard(original_check)):
            self.invoke()
        after = {str(p.relative_to(self.f.root)): p.read_bytes()
                 for p in self.f.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        self.assertTrue(seen)


if __name__ == '__main__':
    unittest.main()
