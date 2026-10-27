"""Real temporary Git source/tag fixtures and synthetic freshness fences only."""
from __future__ import annotations

import copy
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import rc_consumer_snapshot as snapshot
from rc_consumer_snapshot_fixtures import API, SOURCE, TAG, VERSION, environment, expectations, source_tree
from source_provenance_gate_tests import command, commit


class SourceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.baseline, self.source = source_tree(self.root)
        self.env = environment(self.source)
        self.expected = expectations(self.source)
        self.api = API(self.source)
        original = snapshot.gate.reviewed.verify
        verifier = patch.object(snapshot.gate.reviewed, 'verify', side_effect=lambda root, source:
                                original(root, source, baseline=self.baseline))
        verifier.start()
        self.addCleanup(verifier.stop)

    def resolve(self):
        return snapshot.resolve_candidate(self.root, self.expected, self.env, self.api)

    def capture(self):
        candidate = self.resolve()
        selection = snapshot.select_source_runs(self.api, candidate, self.expected)
        artifact = snapshot.authenticate_bundle_metadata(self.api, selection, self.expected['artifact_id'])
        producer = snapshot.derive_final_producer(candidate, selection, artifact)
        return dict(candidate=candidate, selection=selection, artifact=artifact, producer=producer)

    def test_source_versions_tree_consumer_and_no_environment_spoofing(self):
        original_environment = dict(os.environ)
        value = self.resolve()
        self.assertEqual(value['version'], VERSION)
        self.assertEqual(value['source_sha'], self.source)
        self.assertEqual(value['source_tree'], command(self.root, 'rev-parse', 'HEAD^{tree}'))
        self.assertEqual(len(value['source_proof']['versions']), 6)
        self.assertEqual(value['consumer']['run_id'], 900)
        self.assertEqual(value['consumer']['run_attempt'], 3)
        self.assertEqual(value['consumer']['source_sha'], self.source)
        self.assertFalse(value['reviewed_source']['publish_approved'])
        self.assertEqual(dict(os.environ), original_environment)

    def test_actual_consumer_environment_fields_are_mandatory(self):
        for field in list(self.env):
            value = self.env.pop(field)
            with self.subTest(field=field), self.assertRaises(snapshot.ConsumerError): self.resolve()
            self.env[field] = value

    def test_consumer_wrong_identity_and_malformed_numeric_fields(self):
        mutations = [('GITHUB_SHA', SOURCE), ('GITHUB_WORKFLOW_SHA', SOURCE),
                     ('GITHUB_REPOSITORY', 'other/repo'), ('GITHUB_EVENT_NAME', 'push'),
                     ('GITHUB_WORKFLOW_REF', snapshot.REPOSITORY + '/evil.yml@' + self.env['GITHUB_REF']),
                     ('GITHUB_REF', 'refs/heads/../../evil'), ('GITHUB_RUN_ID', '1.0'),
                     ('GITHUB_RUN_ATTEMPT', True), ('GITHUB_RUN_ID', '01'), ('GITHUB_REPOSITORY_ID', '0')]
        for field, new in mutations:
            old = self.env[field]; self.env[field] = new
            with self.subTest(field=field, new=new), self.assertRaises(snapshot.ConsumerError): self.resolve()
            self.env[field] = old

    def test_missing_and_moved_local_tag_never_created_or_repaired(self):
        command(self.root, 'tag', '-d', TAG)
        with self.assertRaises(snapshot.ConsumerError): self.resolve()
        self.assertEqual(command(self.root, 'tag', '--list'), '')
        command(self.root, 'tag', TAG, self.baseline)
        with self.assertRaisesRegex(snapshot.ConsumerError, 'lightweight_tag_required'): self.resolve()
        self.assertEqual(command(self.root, 'rev-parse', TAG), self.baseline)
        self.assertEqual(self.api.calls, [])

    def test_annotated_local_and_remote_tags_rejected(self):
        command(self.root, 'tag', '-d', TAG)
        command(self.root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                'tag', '-a', TAG, '-m', 'Synthetic annotation fixture')
        with self.assertRaisesRegex(snapshot.ConsumerError, 'lightweight_tag_required'): self.resolve()
        command(self.root, 'tag', '-d', TAG)
        command(self.root, 'tag', TAG)
        self.api.data['/git/ref/tags/' + TAG]['object']['type'] = 'tag'
        with self.assertRaisesRegex(snapshot.ConsumerError, 'lightweight_tag_required'): self.resolve()
        self.assertFalse(any('/git/tags/' in call for call in self.api.calls))

    def test_stable_malformed_mismatched_tag_and_version_rejected(self):
        for version, tag in [('1.2.3', 'v1.2.3'), (VERSION, 'v' + VERSION + '\n'),
                             (VERSION, 'v1.2.3-rc.5'), ('01.2.3-rc.4', TAG)]:
            old = self.expected
            self.expected = dict(old, rc_version=version, release_tag=tag)
            with self.subTest(version=version, tag=tag), self.assertRaises(snapshot.ConsumerError): self.resolve()
            self.expected = old

    def test_tracked_untracked_and_ignored_source_dirtiness(self):
        path = self.root / 'package.json'; original = path.read_bytes()
        path.write_bytes(original + b'\n')
        with self.assertRaises(snapshot.ConsumerError): self.resolve()
        path.write_bytes(original)
        path = self.root / 'untracked.txt'; path.write_text('untracked')
        with self.assertRaisesRegex(snapshot.ConsumerError, 'untracked_source'): self.resolve()
        path.unlink()
        (self.root / '.git/info/exclude').write_text('ignored.txt\n')
        (self.root / 'ignored.txt').write_text('ignored is still untracked')
        with self.assertRaisesRegex(snapshot.ConsumerError, 'untracked_source'): self.resolve()

    def test_all_six_versions_remain_source_checks(self):
        import json
        mutations = [('package.json', ('version',)), ('package-lock.json', ('version',)),
                     ('package-lock.json', ('packages', '', 'version')),
                     ('src-tauri/tauri.conf.json', ('version',))]
        for name, keys in mutations:
            path = self.root / name; raw = path.read_bytes(); value = json.loads(raw)
            parent = value
            for key in keys[:-1]: parent = parent[key]
            parent[keys[-1]] = '1.2.3-rc.5'; path.write_text(json.dumps(value))
            with self.subTest(name=name, keys=keys), self.assertRaises(snapshot.ConsumerError): self.resolve()
            path.write_bytes(raw)
        for name in ('src-tauri/Cargo.toml', 'src-tauri/Cargo.lock'):
            path = self.root / name; raw = path.read_text(); path.write_text(raw.replace(VERSION, '1.2.3-rc.5'))
            with self.subTest(name=name), self.assertRaises(snapshot.ConsumerError): self.resolve()
            path.write_text(raw)

    def test_missing_reviewed_manifest_and_wrong_gateway_fail_before_api(self):
        manifest = self.root / snapshot.gate.reviewed.MANIFEST
        saved = manifest.read_bytes(); manifest.unlink()
        with self.assertRaises(snapshot.ConsumerError): self.resolve()
        manifest.write_bytes(saved)
        for name in ('Cargo.toml', 'Cargo.lock'):
            path = self.root / 'services/cloud-gateway' / name
            path.write_text(path.read_text().replace(VERSION, '0.1.0'))
        self.source = commit(self.root)
        command(self.root, 'tag', '-f', TAG)
        self.expected['source_sha'] = self.source
        self.env.update(GITHUB_SHA=self.source, GITHUB_WORKFLOW_SHA=self.source)
        with self.assertRaises(snapshot.ConsumerError): self.resolve()
        self.assertEqual(self.api.calls, [])

    def test_missing_checked_out_workflow_is_not_dispatch_identity(self):
        (self.root / snapshot.CONSUMER_WORKFLOW).unlink()
        self.source = commit(self.root)
        command(self.root, 'tag', '-f', TAG)
        self.expected['source_sha'] = self.source
        self.env.update(GITHUB_SHA=self.source, GITHUB_WORKFLOW_SHA=self.source)
        with self.assertRaisesRegex(snapshot.ConsumerError, 'consumer_workflow_missing'): self.resolve()

    def test_valid_snapshot_revalidates_full_inventory_and_local_proof(self):
        captured = self.capture()
        counts = len(self.api.calls)
        snapshot.revalidate_download(self.api, captured['selection'], captured['artifact'])
        snapshot.revalidate_snapshot(self.api, self.root, self.expected, self.env, captured)
        later = self.api.calls[counts:]
        self.assertIn(self.api.jobs_path(101, 2), later)
        self.assertIn(self.api.jobs_path(102), later)
        self.assertIn(self.api.artifacts_path(), later)
        self.assertIn('/actions/artifacts/600', later)
        self.assertIn('/git/ref/tags/' + TAG, later)

    def test_freshness_rejects_run_job_artifact_tag_repository_changes(self):
        for kind in ('new_run', 'attempt', 'job_id', 'job_time', 'event', 'head_branch',
                     'artifact_digest', 'artifact_size', 'artifact_list', 'tag', 'repository'):
            self.api = API(self.source); captured = self.capture()
            if kind == 'new_run':
                newer = dict(self.api.data['/actions/runs/102'], id=999, status='queued', conclusion=None)
                self.api.data['/actions/runs/999'] = newer
                self.api.data[self.api.runs_path(12)] = dict(total_count=2, workflow_runs=[newer,
                    self.api.data['/actions/runs/102']])
            elif kind == 'attempt': self.api.data['/actions/runs/102']['run_attempt'] = 2
            elif kind == 'job_id': self.api.data[self.api.jobs_path(102)]['jobs'][0]['id'] += 50
            elif kind == 'job_time': self.api.data[self.api.jobs_path(102)]['jobs'][0]['started_at'] = '2026-09-30T10:02:00Z'
            elif kind == 'event': self.api.data['/actions/runs/102']['event'] = 'workflow_dispatch'
            elif kind == 'head_branch': self.api.data['/actions/runs/102']['head_branch'] += '-new'
            elif kind == 'artifact_digest': self.api.data['/actions/artifacts/600']['digest'] = 'sha256:' + 'c' * 64
            elif kind == 'artifact_size': self.api.data['/actions/artifacts/600']['size_in_bytes'] += 1
            elif kind == 'artifact_list': self.api.data[self.api.artifacts_path()] = dict(total_count=0, artifacts=[])
            elif kind == 'tag': self.api.data['/git/ref/tags/' + TAG]['object']['sha'] = SOURCE
            else: self.api.data['/']['id'] = 5678
            with self.subTest(kind=kind), self.assertRaises(snapshot.ConsumerError):
                snapshot.revalidate_snapshot(self.api, self.root, self.expected, self.env, captured)

    def test_final_live_tag_read_detects_last_window_change(self):
        captured = self.capture(); original = self.api.get
        old_count = self.api.calls.count('/git/ref/tags/' + TAG)
        def racing(path):
            value = original(path)
            if path == '/git/ref/tags/' + TAG and self.api.calls.count(path) == old_count + 3:
                value['object']['sha'] = SOURCE
            return value
        self.api.get = racing
        with self.assertRaises(snapshot.ConsumerError):
            snapshot.revalidate_snapshot(self.api, self.root, self.expected, self.env, captured)

    def test_source_changes_during_content_validation_rejected(self):
        captured = self.capture()
        (self.root / 'untracked-new').write_text('changed after download')
        with self.assertRaises(snapshot.ConsumerError):
            snapshot.revalidate_snapshot(self.api, self.root, self.expected, self.env, captured)

    def test_only_fixed_read_only_git_commands_run_for_source_validation(self):
        calls = []
        original = subprocess.run
        allowed = {'rev-parse', 'diff', 'ls-files', 'ls-tree', 'cat-file', 'merge-base'}
        def recording(args, *rest, **kwargs):
            calls.append(args)
            self.assertEqual(args[0], 'git')
            self.assertIn(args[1], allowed)
            self.assertNotIn('shell', kwargs)
            return original(args, *rest, **kwargs)
        with patch.object(subprocess, 'run', side_effect=recording): self.resolve()
        self.assertTrue(calls)
        self.assertEqual(command(self.root, 'status', '--porcelain'), '')


if __name__ == '__main__':
    unittest.main()
