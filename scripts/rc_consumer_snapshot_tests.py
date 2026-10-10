"""Hermetic authenticated-route snapshot negatives; no live token/artifact."""
from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError
import io
import json
import os
import unittest
from unittest.mock import patch

import rc_consumer_snapshot as snapshot
from rc_consumer_snapshot_fixtures import API, SOURCE, VERSION, candidate, expectations


class SnapshotTests(unittest.TestCase):
    def test_complete_first_attempt_and_immutable_producer(self):
        api = API()
        selected = api.selection()
        artifact = snapshot.authenticate_bundle_metadata(api, selected, 600)
        producer = snapshot.derive_final_producer(candidate(), selected, artifact)
        self.assertEqual(len(selected['integration']['jobs']), 7)
        self.assertEqual(len(selected['final_packaging']['jobs']), 13)
        self.assertEqual(producer.version, VERSION)
        self.assertEqual(producer.run_attempt, 1)
        self.assertEqual(producer.repository_id, 1234)
        self.assertEqual(producer.artifact_sha256, 'b' * 64)
        with self.assertRaises(FrozenInstanceError):
            producer.run_id = 9
        self.assertFalse(any('status=success' in call or 'filter=latest' in call for call in api.calls))
        self.assertIn('/actions/runs/102/attempts/1/jobs?per_page=100&page=1', api.calls)
        self.assertIn('/actions/runs/101/attempts/2/jobs?per_page=100&page=1', api.calls)

    def test_expected_ids_reject_bool_float_zero_and_strings(self):
        for key in expectations().keys() - {'rc_version', 'release_tag', 'source_sha'}:
            for value in (True, False, 0, -1, 1.0, float('nan'), '102', None):
                expected = dict(expectations(), **{key: value})
                with self.subTest(key=key, value=value), self.assertRaises(snapshot.ConsumerError):
                    snapshot.select_source_runs(API(), candidate(), expected)

    def test_expected_identity_and_input_field_mutations(self):
        for change in (dict(source_sha='A' * 40), dict(rc_version='1.2.3'),
                       dict(release_tag='v1.2.3-rc.5'), dict(bypass=True), dict(final_run_id=999)):
            with self.subTest(change=change), self.assertRaises(snapshot.ConsumerError):
                snapshot.select_source_runs(API(), candidate(), dict(expectations(), **change))

    def test_latest_failure_pending_cancelled_never_falls_back(self):
        for status, conclusion in [('completed', 'failure'), ('queued', None),
                                   ('in_progress', None), ('completed', 'cancelled')]:
            api = API()
            newer = dict(api.data['/actions/runs/102'], id=999, status=status, conclusion=conclusion)
            api.data['/actions/runs/999'] = newer
            api.data[api.runs_path(12)]['workflow_runs'].append(newer)
            api.data[api.runs_path(12)]['total_count'] = 2
            with self.subTest(status=status, conclusion=conclusion), self.assertRaises(snapshot.ConsumerError):
                api.selection()
            self.assertNotIn('/actions/runs/102', api.calls)

    def test_all_final_reruns_including_retained_deleted_desktop_rejected(self):
        # Desktop receipts lack attempts. A deleted newer desktop artifact can
        # expose old bytes: even perfect current jobs/outer metadata cannot help.
        for attempt in (2, 9):
            api = API()
            run = api.data['/actions/runs/102']; run['run_attempt'] = attempt
            old_jobs = api.data.pop(api.jobs_path(102))
            for job in old_jobs['jobs']: job['run_attempt'] = attempt
            api.data[api.jobs_path(102, attempt)] = old_jobs
            api.data[api.artifacts_path()]['artifacts'].append(dict(
                id=599, name='rc-linux-packages', workflow_run=dict(id=102), expired=False))
            with self.assertRaisesRegex(snapshot.ConsumerError, '^unsupported_rerun_provenance$'):
                api.selection()
            with self.assertRaisesRegex(snapshot.ConsumerError, '^unsupported_rerun_provenance$'):
                snapshot.select_source_runs(api, candidate(), dict(expectations(), final_run_attempt=attempt))

    def test_repository_names_and_numeric_identity_all_bind(self):
        for route in ('/', '/actions/runs/101', '/actions/runs/102'):
            for identity in ('repository', 'head_repository') if route != '/' else ('',):
                for field, value in (('id', 999), ('id', True), ('id', 1234.0), ('full_name', 'other/repo')):
                    api = API(); target = api.data[route]
                    if identity: target = target[identity]
                    target[field] = value
                    with self.subTest(route=route, identity=identity, field=field), self.assertRaises(snapshot.ConsumerError):
                        api.selection()

    def test_run_workflow_source_event_branch_and_type_mutations(self):
        changes = [('head_sha', 'd' * 40), ('path', snapshot.gate.final.WORKFLOW),
                   ('workflow_id', 11), ('workflow_id', 12.0), ('id', True), ('run_number', 9.0),
                   ('event', 'workflow_dispatch'), ('head_branch', 'main'),
                   ('head_branch', 'release/full-rc-candidate-'),
                   ('head_branch', 'release/full-rc-candidate-../bad'),
                   ('head_branch', 'release/full-rc-candidate-bad\n')]
        for field, value in changes:
            api = API(); api.data['/actions/runs/102'][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(snapshot.ConsumerError):
                api.selection()

    def test_workflow_lookup_must_be_exact(self):
        for field, value in (('id', False), ('id', 12.0), ('path', '.github/workflows/other.yml')):
            api = API(); api.data['/actions/workflows/final-rc-packages.yml'][field] = value
            with self.subTest(field=field), self.assertRaises(snapshot.ConsumerError): api.selection()

    def test_missing_duplicate_extra_and_renamed_jobs(self):
        for change in ('missing', 'duplicate_id', 'duplicate_name', 'extra', 'rename'):
            api = API(); payload = api.data[api.jobs_path(102)]; jobs = payload['jobs']
            if change == 'missing': jobs.pop()
            elif change == 'duplicate_id': jobs[1]['id'] = jobs[0]['id']
            elif change == 'duplicate_name': jobs[1]['name'] = jobs[0]['name']
            elif change == 'extra': jobs.append(dict(jobs[0], id=999999, name='unexpected'))
            else: jobs[0]['name'] = 'wrong display name'
            payload['total_count'] = len(jobs)
            with self.subTest(change=change), self.assertRaises(snapshot.ConsumerError): api.selection()

    def test_job_ids_attempt_status_source_and_timestamps(self):
        changes = [('id', True), ('id', 999.0), ('run_id', 101), ('run_attempt', 2),
                   ('run_attempt', 1.0), ('head_sha', 'd' * 40), ('status', 'in_progress'),
                   ('conclusion', 'skipped'), ('started_at', None),
                   ('started_at', '2026-09-30T10:10:00Z'),
                   ('completed_at', '2026-09-30T10:00:00Z'),
                   ('completed_at', '2026-09-30T10:11:00Z')]
        for field, value in changes:
            api = API(); api.data[api.jobs_path(102)]['jobs'][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(snapshot.ConsumerError): api.selection()

    def test_run_timestamp_missing_wrong_order_or_malformed(self):
        for field, value in [('created_at', None), ('created_at', '2026-09-30T10:01:00Z'),
                             ('run_started_at', '2026-09-30T10:11:00Z'),
                             ('updated_at', '2026-02-30T10:11:00Z')]:
            api = API(); api.data['/actions/runs/102'][field] = value
            with self.subTest(field=field), self.assertRaises(snapshot.ConsumerError): api.selection()

    def test_event_and_branch_change_inside_old_helper_rejected(self):
        for field, value in [('event', 'workflow_dispatch'), ('head_branch', 'release/full-rc-candidate-raced'),
                             ('created_at', '2026-09-30T09:58:00Z')]:
            api = API(); original = api.get
            def racing(path):
                record = original(path)
                if path == '/actions/runs/102': record[field] = value
                return record
            api.get = racing
            with self.subTest(field=field), self.assertRaises(snapshot.ConsumerError): api.selection()

    def test_pagination_overbound_short_count_duplicate_search_cap(self):
        for change in ('overbound', 'short', 'bool_count', 'duplicate', 'cap'):
            api = API(); page = api.data[api.runs_path(12)]
            if change == 'overbound': page['total_count'] = 1001
            elif change == 'short': page['total_count'] = 2
            elif change == 'bool_count': page['total_count'] = True
            elif change == 'duplicate':
                page['workflow_runs'] *= 2; page['total_count'] = 2
            else:
                original = page['workflow_runs'][0]
                for number in range(1, 11):
                    route = api.runs_path(12).replace('&page=1', '&page=' + str(number))
                    api.data[route] = dict(total_count=1000, workflow_runs=[dict(original, id=1000 + i)
                        for i in range((number - 1) * 100, number * 100)])
            with self.subTest(change=change), self.assertRaises(snapshot.ConsumerError): api.selection()

    def test_artifact_digest_size_expiry_name_and_time_mutations(self):
        changes = [('digest', None), ('digest', 'SHA256:' + 'b' * 64), ('digest', 'sha256:' + 'B' * 64),
                   ('digest', 'sha256:' + 'b' * 63), ('id', True), ('id', 601), ('name', 'different'),
                   ('size_in_bytes', 0), ('size_in_bytes', True), ('size_in_bytes', 1000.0),
                   ('size_in_bytes', snapshot.MAX_ARTIFACT_BYTES + 1), ('expired', True),
                   ('expired', 0), ('expires_at', '2020-01-01T00:00:00Z'),
                   ('created_at', '2026-09-30T10:00:30Z'), ('created_at', '2026-09-30T10:10:00Z'),
                   ('updated_at', '2026-09-30T10:08:00Z')]
        for field, value in changes:
            api = API(); api.artifact()[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(snapshot.ConsumerError): api.metadata()

    def test_artifact_direct_and_list_metadata_must_agree(self):
        for field, value in [('digest', 'sha256:' + 'c' * 64), ('size_in_bytes', 1001),
                             ('updated_at', '2026-09-30T10:09:02Z'), ('expires_at', '2099-11-30T10:09:00Z')]:
            api = API(); api.data['/actions/artifacts/600'][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(snapshot.ConsumerError, 'artifact_snapshot_changed'):
                api.metadata()

    def test_artifact_owner_run_source_repository_and_branch(self):
        for field, value in [('id', 101), ('id', 102.0), ('head_sha', 'd' * 40),
                             ('repository_id', 999), ('repository_id', True), ('head_repository_id', 1234.0),
                             ('head_branch', 'release/full-rc-candidate-other')]:
            api = API(); api.artifact()['workflow_run'][field] = value
            with self.subTest(field=field), self.assertRaises(snapshot.ConsumerError): api.metadata()

    def test_artifact_inventory_missing_duplicate_or_racing(self):
        for count in (0, 2):
            api = API(); page = api.data[api.artifacts_path()]
            page['artifacts'] = [dict(api.artifact(), id=600+i) for i in range(count)]
            page['total_count'] = count
            with self.subTest(count=count), self.assertRaises(snapshot.ConsumerError): api.metadata()
        api = API(); original = api.get
        def racing(path):
            record = original(path)
            if path == api.artifacts_path() and api.calls.count(path) == 2:
                record['artifacts'][0]['digest'] = 'sha256:' + 'c' * 64
            return record
        api.get = racing
        with self.assertRaises(snapshot.ConsumerError): api.metadata()

    def test_download_fence_deleted_changed_rerun_or_failed(self):
        for kind in ('delete', 'digest', 'rerun', 'failed'):
            api = API(); selected = api.selection(); artifact = snapshot.authenticate_bundle_metadata(api, selected, 600)
            if kind == 'delete': api.data['/actions/artifacts/600'] = {}
            elif kind == 'digest': api.data['/actions/artifacts/600']['digest'] = 'sha256:' + 'c' * 64
            elif kind == 'rerun': api.data['/actions/runs/102']['run_attempt'] = 2
            else: api.data['/actions/runs/102']['conclusion'] = 'failure'
            with self.subTest(kind=kind), self.assertRaises(snapshot.ConsumerError):
                snapshot.revalidate_download(api, selected, artifact)

    def test_api_fixed_origin_method_and_auth_headers(self):
        requests = []
        class Opener:
            def open(self, request, timeout):
                requests.append((request, timeout))
                return io.BytesIO(json.dumps(dict(id=1234, full_name=snapshot.REPOSITORY)).encode())
        original = dict(os.environ)
        with patch.object(snapshot.gate.urllib.request, 'build_opener', return_value=Opener()):
            self.assertEqual(snapshot.GitHub('synthetic-token').get('/')['id'], 1234)
        request, timeout = requests[0]
        self.assertEqual(request.full_url, 'https://api.github.com/repos/' + snapshot.REPOSITORY)
        self.assertEqual(request.get_method(), 'GET')
        self.assertEqual(request.get_header('Authorization'), 'Bearer synthetic-token')
        self.assertEqual(request.get_header('X-github-api-version'), '2022-11-28')
        self.assertEqual(timeout, 30)
        self.assertEqual(dict(os.environ), original)

    def test_api_rejects_bad_paths_nonfinite_duplicate_and_raw_errors(self):
        api = snapshot.GitHub('synthetic-token')
        for path in ('//evil.invalid', '/?x=secret#fragment', '/../../', 'https://evil.invalid'):
            with self.subTest(path=path), self.assertRaises(snapshot.ConsumerError): api.get(path)
        for raw in (b'{"id":1,"id":2}', b'{"value":1e999}', b'{"value":NaN}'):
            class Opener:
                def open(self, request, timeout): return io.BytesIO(raw)
            with patch.object(snapshot.gate.urllib.request, 'build_opener', return_value=Opener()):
                with self.assertRaises(snapshot.ConsumerError): api.get('/')
        with patch.object(snapshot.gate.GitHub, 'get', side_effect=OSError('secret signed URL')):
            with self.assertRaisesRegex(snapshot.ConsumerError, '^invalid_snapshot$'): api.get('/actions/runs/123')


if __name__ == '__main__':
    unittest.main()
