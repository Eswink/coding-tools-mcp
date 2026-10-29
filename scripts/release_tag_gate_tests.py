"""Real temporary Git tags and synthetic read-only API snapshots; no release actions."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import release_tag_gate as gate
from source_provenance_gate_tests import command, commit, repository

SOURCE = 'a' * 40
VERSION = '1.2.3-rc.4'
TAG = 'v' + VERSION
ROOT = Path(__file__).resolve().parents[1]


class API:
    def __init__(self, source=SOURCE, tag_object=None):
        self.calls = []
        self.data = {}
        self.source = source
        self.tag_object = tag_object or source
        for workflow_id, run_id, workflow, names in (
                (11, 101, gate.final.WORKFLOW, gate.final.REQUIRED_JOBS),
                (12, 102, gate.FINAL_WORKFLOW, gate.FINAL_JOBS)):
            info = dict(id=workflow_id, path=workflow)
            run = dict(id=run_id, run_attempt=2, run_number=9, workflow_id=workflow_id,
                       path=workflow, head_sha=source, status='completed', conclusion='success',
                       repository=dict(full_name=gate.REPOSITORY),
                       head_repository=dict(full_name=gate.REPOSITORY),
                       run_started_at='2026-09-30T10:00:00Z', updated_at='2026-09-30T10:10:00Z')
            jobs = [dict(id=run_id * 100 + i, name=name, run_id=run_id, run_attempt=2,
                         head_sha=source, status='completed', conclusion='success')
                    for i, name in enumerate(sorted(names), 1)]
            self.data['/actions/workflows/' + Path(workflow).name] = info
            self.data[self.runs_path(workflow_id)] = dict(total_count=1, workflow_runs=[run])
            self.data[f'/actions/runs/{run_id}'] = run
            self.data[self.jobs_path(run_id)] = dict(total_count=len(jobs), jobs=jobs)
        self.data['/actions/runs/102/artifacts?per_page=100&page=1'] = dict(total_count=1, artifacts=[dict(
            id=600, name='rc-structural-bundle', size_in_bytes=1000, expired=False,
            created_at='2026-09-30T10:09:00Z', expires_at='2099-10-30T10:09:00Z',
            workflow_run=dict(id=102, head_sha=source), digest='sha256:' + 'b' * 64)])
        self.data['/git/ref/tags/' + TAG] = dict(ref='refs/tags/' + TAG,
                                               object=dict(sha=self.tag_object, type='commit'))

    def runs_path(self, workflow_id):
        return f'/actions/workflows/{workflow_id}/runs?head_sha={self.source}&per_page=100&page=1'

    def jobs_path(self, run_id):
        return f'/actions/runs/{run_id}/attempts/2/jobs?per_page=100&page=1'

    def get(self, suffix):
        self.calls.append(suffix)
        if suffix not in self.data:
            raise AssertionError('Unexpected API request: ' + suffix)
        return copy.deepcopy(self.data[suffix])

    def final(self):
        return gate.successful_run(self, gate.FINAL_WORKFLOW, self.source, gate.FINAL_JOBS)


class TagTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        repository(self.root)
        for folder in ('cloud-gateway', 'cloud-agent', 'local-agent'):
            base = self.root / 'services' / folder
            base.mkdir(parents=True)
            version = VERSION if folder == 'cloud-gateway' else '0.1.0'
            name = 'coding-tools-' + folder
            (base / 'Cargo.toml').write_text(f'[package]\nname="{name}"\nversion="{version}"\n')
            (base / 'Cargo.lock').write_text(f'[[package]]\nname="{name}"\nversion="{version}"\n')
        self.baseline = commit(self.root)
        path = self.root / gate.reviewed.MANIFEST
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(dict(schema=1, base_commit=self.baseline, version=VERSION,
                                       review_reference='Synthetic unit fixture only', entries=[])))
        self.source = commit(self.root)
        command(self.root, 'tag', TAG)
        self.env = dict(GITHUB_EVENT_NAME='push', GITHUB_REPOSITORY=gate.REPOSITORY,
                        GITHUB_REF='refs/tags/' + TAG, GITHUB_SHA=self.source)
        self.api = API(self.source)
        self.original_review = gate.reviewed.verify

    def verify(self, api=None):
        with patch.object(gate.reviewed, 'verify',
                          side_effect=lambda root, source: self.original_review(root, source, baseline=self.baseline)):
            return gate.verify(self.root, TAG, self.env, api or self.api)

    def test_complete_rc_snapshot_is_evidence_not_release_or_byte_approval(self):
        value = self.verify()
        self.assertTrue(value['passed'])
        self.assertFalse(value['release_approved'])
        self.assertFalse(value['publish_approved'])
        self.assertFalse(value['final_bundle']['artifact_bytes_verified'])
        self.assertEqual(len(value['final_packaging']['jobs']), 13)
        self.assertEqual(len(value['integration']['jobs']), 7)
        self.assertEqual(self.api.calls.count('/git/ref/tags/' + TAG), 2)
        self.assertFalse(any('status=success' in call or '/jobs?filter=' in call for call in self.api.calls))

    def test_lightweight_and_annotated_tags_peel_actual_source(self):
        self.assertEqual(gate.route(self.root, TAG, self.env)['source_sha'], self.source)
        command(self.root, 'tag', '-d', TAG)
        command(self.root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                'tag', '-a', TAG, '-m', 'Synthetic annotated fixture')
        obj = command(self.root, 'rev-parse', 'refs/tags/' + TAG)
        self.assertNotEqual(obj, self.source)
        self.assertEqual(gate.route(self.root, TAG, self.env)['tag_object_sha'], obj)
        self.api.data['/git/ref/tags/' + TAG]['object'] = dict(type='tag', sha=obj)
        self.api.data['/git/tags/' + obj] = dict(sha=obj, object=dict(type='commit', sha=self.source))
        self.assertTrue(self.verify()['passed'])

    def test_manual_rc_rejected_even_with_publish_true(self):
        for publish in ('false', 'true'):
            with self.assertRaisesRegex(ValueError, 'manual RC'):
                gate.route(self.root, TAG, dict(self.env, GITHUB_EVENT_NAME='workflow_dispatch', INPUT_PUBLISH=publish))

    def test_invalid_tag_syntax_and_missing_tag_rejected(self):
        for tag in ('1.2.3-rc.4', 'v01.2.3-rc.4', 'v1.2.3-rc.04', 'v1.2.3-beta.1',
                    'v1.2.3-rc.4\n', 'v1.2.3+build', 'v1.2.3-rc.5'):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                gate.route(self.root, tag, dict(self.env, GITHUB_REF='refs/tags/' + tag))

    def test_wrong_repository_ref_event_source_and_checkout_rejected(self):
        for key, value in [('GITHUB_REPOSITORY', 'other/repo'), ('GITHUB_REF', 'refs/heads/main'),
                           ('GITHUB_EVENT_NAME', 'pull_request'), ('GITHUB_SHA', SOURCE)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                gate.route(self.root, TAG, dict(self.env, **{key: value}))
        command(self.root, 'checkout', '--detach', self.baseline)
        with self.assertRaises(ValueError): gate.route(self.root, TAG, self.env)

    def test_dirty_source_and_mixed_six_versions_rejected(self):
        path = self.root / 'package.json'
        original = path.read_text()
        path.write_text(original + '\n')
        with self.assertRaisesRegex(ValueError, 'tracked source'): gate.route(self.root, TAG, self.env)
        path.write_text(original.replace(VERSION, '1.2.3-rc.5'))
        with self.assertRaisesRegex(ValueError, 'differ'): gate.route(self.root, TAG, self.env)

    def test_gateway_product_version_mismatch_blocks_before_api(self):
        for name in ('Cargo.toml', 'Cargo.lock'):
            path = self.root / 'services/cloud-gateway' / name
            path.write_text(path.read_text().replace(VERSION, '0.1.0'))
        self.source = commit(self.root)
        command(self.root, 'tag', '-f', TAG)
        self.env['GITHUB_SHA'] = self.source
        with self.assertRaisesRegex(ValueError, 'gateway product version'): self.verify()
        self.assertEqual(self.api.calls, [])

    def test_frozen_reviewed_manifest_required_and_not_regenerated(self):
        (self.root / gate.reviewed.MANIFEST).unlink()
        self.source = commit(self.root)
        command(self.root, 'tag', '-f', TAG)
        self.env['GITHUB_SHA'] = self.source
        with self.assertRaisesRegex(ValueError, 'frozen source manifest'): self.verify()
        self.assertEqual(self.api.calls, [])

    def test_frozen_manifest_rejects_unreviewed_source_change(self):
        (self.root / 'extra.txt').write_text('unreviewed')
        self.source = commit(self.root)
        command(self.root, 'tag', '-f', TAG)
        self.env['GITHUB_SHA'] = self.source
        with self.assertRaisesRegex(ValueError, 'frozen reviewed source differs'): self.verify()

    def test_moved_live_tag_initial_and_final_check_fail(self):
        self.api.data['/git/ref/tags/' + TAG]['object']['sha'] = SOURCE
        with self.assertRaisesRegex(ValueError, 'live tag moved'): self.verify()
        self.api.data['/git/ref/tags/' + TAG]['object']['sha'] = self.source
        original = self.api.get
        def moving(path):
            value = original(path)
            if path == '/git/ref/tags/' + TAG and self.api.calls.count(path) == 2:
                value['object']['sha'] = SOURCE
            return value
        self.api.get = moving
        with self.assertRaisesRegex(ValueError, 'live tag moved'): self.verify()

    def test_new_run_appearing_during_snapshot_rejected(self):
        original = self.api.get
        path = self.api.runs_path(11)
        def racing(suffix):
            value = original(suffix)
            if suffix == path and self.api.calls.count(path) == 2:
                value['workflow_runs'].append(dict(value['workflow_runs'][0], id=999, status='queued', conclusion=None))
                value['total_count'] = 2
            return value
        self.api.get = racing
        with self.assertRaisesRegex(ValueError, 'run changed'): self.verify()

    def test_each_of_six_rc_version_fields_is_mandatory(self):
        mutations = [
            ('package.json', lambda value: value.update(version='1.2.3-rc.5')),
            ('package-lock.json', lambda value: value.update(version='1.2.3-rc.5')),
            ('package-lock.json', lambda value: value['packages'][''].update(version='1.2.3-rc.5')),
            ('src-tauri/tauri.conf.json', lambda value: value.update(version='1.2.3-rc.5')),
        ]
        for name, mutate in mutations:
            path = self.root / name; original = path.read_text(); value = json.loads(original)
            mutate(value); path.write_text(json.dumps(value))
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'differ'):
                gate.route(self.root, TAG, self.env)
            path.write_text(original)
        for name in ('src-tauri/Cargo.toml', 'src-tauri/Cargo.lock'):
            path = self.root / name; original = path.read_text()
            path.write_text(original.replace(VERSION, '1.2.3-rc.5'))
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'differ'):
                gate.route(self.root, TAG, self.env)
            path.write_text(original)

    def test_local_tag_movement_and_tag_version_mismatch_rejected(self):
        command(self.root, 'tag', '-f', TAG, self.baseline)
        with self.assertRaisesRegex(ValueError, 'event source'): gate.route(self.root, TAG, self.env)
        command(self.root, 'tag', 'v1.2.3-rc.5', self.source)
        with self.assertRaisesRegex(ValueError, 'expected version'):
            gate.route(self.root, 'v1.2.3-rc.5', dict(self.env, GITHUB_REF='refs/tags/v1.2.3-rc.5'))

    def test_annotation_object_is_not_accepted_as_event_commit(self):
        command(self.root, 'tag', '-d', TAG)
        command(self.root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                'tag', '-a', TAG, '-m', 'Synthetic annotated fixture')
        annotation = command(self.root, 'rev-parse', 'refs/tags/' + TAG)
        with self.assertRaisesRegex(ValueError, 'event source'):
            gate.route(self.root, TAG, dict(self.env, GITHUB_SHA=annotation))

    def test_stable_tags_still_use_original_resolver_and_manual_semantics(self):
        command(self.root, 'tag', 'v1.2.3', self.baseline)
        for event in ('push', 'workflow_dispatch'):
            value = gate.route(self.root, 'v1.2.3', dict(self.env, GITHUB_EVENT_NAME=event))
            self.assertEqual(value, dict(channel='stable', release_tag='v1.2.3', source_sha=self.baseline))
        with self.assertRaises(ValueError): gate.stable.resolve_tag(self.root, TAG)
        with self.assertRaises(ValueError): gate.stable.verify_source(self.root, expected_sha=self.source)


class APITests(unittest.TestCase):
    def setUp(self):
        self.api = API()

    def test_exact_final_and_integration_inventories_pass(self):
        self.assertEqual(len(self.api.final()['jobs']), 13)
        result = gate.successful_run(self.api, gate.final.WORKFLOW, SOURCE, gate.final.REQUIRED_JOBS)
        self.assertEqual(len(result['jobs']), 7)

    def test_newer_failed_pending_cancelled_run_never_falls_back(self):
        for status, conclusion in [('completed', 'failure'), ('in_progress', None),
                                   ('queued', None), ('completed', 'cancelled')]:
            api = API()
            run = dict(api.data['/actions/runs/102'], id=999, status=status, conclusion=conclusion)
            api.data['/actions/runs/999'] = run
            api.data[api.runs_path(12)]['workflow_runs'].append(run)
            api.data[api.runs_path(12)]['total_count'] = 2
            with self.subTest(status=status, conclusion=conclusion), self.assertRaisesRegex(ValueError, 'newest'):
                api.final()

    def test_run_identity_rejects_wrong_repo_source_workflow_and_bad_ids(self):
        changes = [dict(head_sha='b' * 40), dict(path='.github/workflows/windows-rc-packages.yml'),
                   dict(repository=dict(full_name='other/repo')), dict(head_repository=dict(full_name='other/repo')),
                   dict(workflow_id=99), dict(id=0), dict(id=True), dict(run_attempt=0),
                   dict(run_attempt=True), dict(run_number=0)]
        for change in changes:
            api = API()
            api.data[api.runs_path(12)]['workflow_runs'][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError): api.final()

    def test_workflow_lookup_identity_rejected(self):
        for change in (dict(id=True), dict(path=gate.final.WORKFLOW)):
            api = API()
            api.data['/actions/workflows/final-rc-packages.yml'].update(change)
            with self.assertRaises(ValueError): api.final()

    def test_missing_extra_duplicate_named_or_duplicate_id_jobs_rejected(self):
        for mutate in (lambda jobs: jobs.pop(),
                       lambda jobs: jobs.append(dict(jobs[0], id=99999, name='extra')),
                       lambda jobs: jobs[1].update(name=jobs[0]['name']),
                       lambda jobs: jobs[1].update(id=jobs[0]['id'])):
            api = API(); batch = api.data[api.jobs_path(102)]
            mutate(batch['jobs']); batch['total_count'] = len(batch['jobs'])
            with self.assertRaises(ValueError): api.final()

    def test_integration_exact_set_wraps_existing_subset_helper(self):
        extra = dict(self.api.data[self.api.jobs_path(101)]['jobs'][0], id=99999, name='unexpected extra')
        self.api.data[self.api.jobs_path(101)]['jobs'].append(extra)
        self.api.data[self.api.jobs_path(101)]['total_count'] += 1
        with self.assertRaisesRegex(ValueError, 'inventory'):
            gate.successful_run(self.api, gate.final.WORKFLOW, SOURCE, gate.final.REQUIRED_JOBS)

    def test_skipped_failed_foreign_source_run_attempt_and_bad_job_id_rejected(self):
        changes = [dict(conclusion='skipped'), dict(conclusion='failure'), dict(status='queued'),
                   dict(head_sha='b' * 40), dict(run_id=999), dict(run_attempt=1),
                   dict(run_attempt=True), dict(id=0), dict(id=True)]
        for change in changes:
            api = API(); api.data[api.jobs_path(102)]['jobs'][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError): api.final()

    def test_jobs_fetched_from_selected_attempt_and_rerun_race_rejected(self):
        original = self.api.get
        def racing(path):
            value = original(path)
            if path == '/actions/runs/102' and self.api.calls.count(path) > 1:
                value['run_attempt'] += 1
            return value
        self.api.get = racing
        with self.assertRaisesRegex(ValueError, 'run changed'): self.api.final()
        self.assertIn(self.api.jobs_path(102), self.api.calls)

    def test_status_and_update_races_rejected(self):
        for change in (dict(status='in_progress', conclusion=None), dict(updated_at='2026-09-30T11:10:00Z')):
            api = API(); original = api.get
            def racing(path):
                value = original(path)
                if path == '/actions/runs/102' and api.calls.count(path) > 1: value.update(change)
                return value
            api.get = racing
            with self.assertRaisesRegex(ValueError, 'run changed'): api.final()

    def test_full_pagination_and_deterministic_newest_across_pages(self):
        run = self.api.data['/actions/runs/102']
        first = [dict(run, id=index) for index in range(1, 101)]
        self.api.data[self.api.runs_path(12)] = dict(total_count=101, workflow_runs=first)
        self.api.data[self.api.runs_path(12).replace('&page=1', '&page=2')] = dict(total_count=101, workflow_runs=[run])
        self.assertEqual(self.api.final()['run']['id'], 102)

    def test_pagination_count_truncation_duplicate_and_bound_fail_closed(self):
        for batch in (dict(total_count=2, workflow_runs=[]), dict(total_count=1001, workflow_runs=[]),
                      dict(total_count=True, workflow_runs=[]), dict(total_count=0, workflow_runs=[dict(id=1)]),
                      dict(total_count=2, workflow_runs=[dict(id=1), dict(id=1)])):
            self.api.data['/list?per_page=100&page=1'] = batch
            with self.assertRaises(ValueError): gate.paginate(self.api, '/list', 'workflow_runs')
        self.api.data['/list?per_page=100&page=1'] = dict(total_count=101, workflow_runs=[dict(id=i) for i in range(1, 101)])
        self.api.data['/list?per_page=100&page=2'] = dict(total_count=102, workflow_runs=[dict(id=101)])
        with self.assertRaisesRegex(ValueError, 'count changed'): gate.paginate(self.api, '/list', 'workflow_runs')
        self.api.data['/list?per_page=100&page=2'] = dict(total_count=101, workflow_runs=[dict(id=1)])
        with self.assertRaisesRegex(ValueError, 'duplicate'): gate.paginate(self.api, '/list', 'workflow_runs')

    def test_final_bundle_metadata_rejects_missing_duplicate_expired_old_and_foreign(self):
        path = '/actions/runs/102/artifacts?per_page=100&page=1'
        for change in (dict(name='engineering-only'), dict(expired=True), dict(size_in_bytes=0),
                       dict(size_in_bytes=True), dict(workflow_run=dict(id=101, head_sha=SOURCE)),
                       dict(workflow_run=dict(id=102, head_sha='b' * 40)),
                       dict(created_at='2026-09-30T09:59:00Z'), dict(expires_at='2020-01-01T00:00:00Z'),
                       dict(digest='bad')):
            api = API(); api.data[path]['artifacts'][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                gate.bundle_metadata(api, api.data['/actions/runs/102'])
        self.api.data[path]['artifacts'].append(dict(self.api.data[path]['artifacts'][0], id=601))
        self.api.data[path]['total_count'] = 2
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            gate.bundle_metadata(self.api, self.api.data['/actions/runs/102'])

    def test_optional_api_digest_does_not_claim_byte_verification(self):
        del self.api.data['/actions/runs/102/artifacts?per_page=100&page=1']['artifacts'][0]['digest']
        value = gate.bundle_metadata(self.api, self.api.data['/actions/runs/102'])
        self.assertFalse(value['digest_available'])
        self.assertFalse(value['artifact_bytes_verified'])

    def test_missing_observed_job_attempt_field_fails_closed(self):
        for job in self.api.data[self.api.jobs_path(102)]['jobs']:
            del job['run_attempt']
        with self.assertRaisesRegex(ValueError, 'job/attempt'):
            self.api.final()
        self.assertIn(self.api.jobs_path(102), self.api.calls)

    def test_latest_run_rejects_api_search_at_1000_result_cap(self):
        run = self.api.data['/actions/runs/102']
        for page in range(1, 11):
            records = [dict(run, id=value) for value in range((page - 1) * 100 + 1, page * 100 + 1)]
            path = self.api.runs_path(12).replace('&page=1', '&page=' + str(page))
            self.api.data[path] = dict(total_count=1000, workflow_runs=records)
        with self.assertRaisesRegex(ValueError, 'search cap'):
            gate.latest_run(self.api, dict(id=12, path=gate.FINAL_WORKFLOW), SOURCE)

    def test_initial_run_attempt_changed_since_listing_rejected(self):
        self.api.data['/actions/runs/102'] = dict(self.api.data['/actions/runs/102'], run_attempt=3)
        with self.assertRaisesRegex(ValueError, 'run changed'): self.api.final()

    def test_multihop_annotated_tag_and_depth_bound(self):
        self.api.data['/git/ref/tags/' + TAG]['object'] = dict(type='tag', sha=SOURCE)
        self.api.data['/git/tags/' + SOURCE] = dict(sha=SOURCE, object=dict(type='tag', sha='b' * 40))
        self.api.data['/git/tags/' + 'b' * 40] = dict(sha='b' * 40, object=dict(type='commit', sha='c' * 40))
        gate.live_tag(self.api, TAG, SOURCE, 'c' * 40)
        for index in range(11):
            sha = f'{index + 1:040x}'; next_sha = f'{index + 2:040x}'
            self.api.data['/git/tags/' + sha] = dict(sha=sha, object=dict(type='tag', sha=next_sha))
        self.api.data['/git/ref/tags/' + TAG]['object'] = dict(type='tag', sha=f'{1:040x}')
        with self.assertRaisesRegex(ValueError, 'depth exceeded'):
            gate.live_tag(self.api, TAG, f'{1:040x}', SOURCE)

    def test_http_json_rejects_duplicate_nonfinite_oversized_and_redirected_responses(self):
        import io
        from urllib.error import HTTPError
        for raw in (b'{"id":1,"id":2}', b'{"id":NaN}', b'[]', b' ' * (gate.MAX_RESPONSE_BYTES + 1)):
            with patch.object(gate.urllib.request, 'build_opener') as opener:
                opener.return_value.open.return_value = io.BytesIO(raw)
                with self.assertRaises(ValueError): gate.GitHub('synthetic').get('/actions/runs/1')
        with patch.object(gate.urllib.request, 'build_opener') as opener:
            opener.return_value.open.side_effect = HTTPError('https://api.github.com', 404, 'missing', {}, None)
            with self.assertRaises(HTTPError): gate.GitHub('synthetic').get('/actions/runs/1')
        with patch.object(gate.urllib.request, 'build_opener') as opener:
            opener.return_value.open.return_value = io.BytesIO(b'{}')
            gate.GitHub('synthetic').get('/actions/runs/1')
            redirect = opener.call_args.args[0]()
            with self.assertRaisesRegex(ValueError, 'redirect'):
                redirect.redirect_request(None, None, 302, '', {}, 'https://other.invalid')

    def test_tag_invalid_type_source_ref_and_annotation_cycle_rejected(self):
        for change in (dict(type='tree', sha=SOURCE), dict(type='commit', sha='b' * 40)):
            api = API(); api.data['/git/ref/tags/' + TAG]['object'] = change
            with self.assertRaises(ValueError): gate.live_tag(api, TAG, change['sha'], SOURCE)
        self.api.data['/git/ref/tags/' + TAG]['object']['type'] = 'tag'
        self.api.data['/git/tags/' + SOURCE] = dict(sha=SOURCE, object=dict(type='tag', sha=SOURCE))
        with self.assertRaisesRegex(ValueError, 'cyclic'): gate.live_tag(self.api, TAG, SOURCE, SOURCE)


class WorkflowTests(unittest.TestCase):
    def test_rc_route_is_read_only_and_stable_build_publish_are_explicitly_guarded(self):
        workflow = (ROOT / '.github/workflows/release.yml').read_text()
        self.assertIn("tags: ['v*']", workflow)
        self.assertIn('python scripts/release_tag_gate.py route --tag', workflow)
        self.assertIn("build-windows:\n    if: needs.prepare.outputs.channel == 'stable'", workflow)
        self.assertIn("if: ${{ needs.prepare.outputs.channel == 'stable' && github.event_name == 'workflow_dispatch' && inputs.publish }}", workflow)
        rc_job = workflow.split('  rc-tag-evidence:', 1)[1].split('  build-windows:', 1)[0]
        self.assertIn("github.event_name == 'push'", rc_job)
        self.assertIn('contents: read\n      actions: read', rc_job)
        self.assertIn('persist-credentials: false', rc_job)
        self.assertIn('python scripts/release_tag_gate.py verify', rc_job)
        for forbidden in ('contents: write', 'download-artifact', 'action-gh-release', 'final_rc_evidence.py',
                          'release_dependency_contract.py', 'workflow_dispatch', 'gh release', 'npm ', 'cargo '):
            self.assertNotIn(forbidden, rc_job)

    def test_exact_final_names_derive_from_current_workflow_sources(self):
        final = (ROOT / gate.FINAL_WORKFLOW).read_text()
        cloud = (ROOT / '.github/workflows/full-rc-cloud-binaries.yml').read_text()
        topology = (ROOT / '.github/workflows/issue40-container-topology.yml').read_text()
        names = set()
        for line in final.splitlines():
            if line.startswith('    name: ') and '${{' not in line and 'Same-source nonproduction' not in line:
                names.add(line.removeprefix('    name: '))
        self.assertIn('  cloud:\n', final)
        self.assertIn('  build:\n', cloud); self.assertIn('  process:\n', cloud)
        names.update({'cloud / build', 'cloud / process'})
        for line in cloud.splitlines():
            if line.startswith('    name: '): names.add('cloud / ' + line.removeprefix('    name: '))
        self.assertIn('    name: Same-source nonproduction topology acceptance', final)
        self.assertIn('  topology:\n', topology)
        names.add('Same-source nonproduction topology acceptance / topology')
        self.assertIn('kind: [deb, appimage]', final)
        self.assertIn('os: [ubuntu-22.04, ubuntu-24.04]', final)
        names.update(f'Installed {os} ({kind})' for os in ('ubuntu-22.04', 'ubuntu-24.04') for kind in ('deb', 'appimage'))
        self.assertEqual(names, gate.FINAL_JOBS)
        self.assertEqual(len(names), 13)

    def test_both_os_provenance_runs_new_negatives_with_narrow_paths(self):
        workflow = (ROOT / '.github/workflows/发布来源验证v4.yml').read_text()
        self.assertIn('os: [ubuntu-latest, windows-latest]', workflow)
        self.assertEqual(workflow.count("- 'scripts/release_tag_gate*.py'"), 2)
        self.assertIn('reviewed_source_gate_tests release_tag_gate_tests; do', workflow)
        self.assertIn("'ci/rc-tag-evidence-*'", workflow)
        self.assertNotIn('tags-ignore', workflow)


if __name__ == '__main__':
    unittest.main()
