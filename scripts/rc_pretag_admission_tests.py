"""Real-source pre-tag admission and fail-closed live-identity fixtures only."""
import copy
from dataclasses import FrozenInstanceError
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

import rc_consumer_snapshot as snapshot
from rc_consumer_snapshot_fixtures import environment as post_environment
from rc_consumer_io import ConsumerError
import rc_pretag_admission as admission
from rc_pretag_collect_fixtures import (
    PreTagFixture, PreTagAPI, WORKFLOW, OWN_JOB, OWN_RUN, OWN_ATTEMPT, FINAL_BRANCH)
import rc_pretag_types as types
from source_provenance_gate_tests import command, commit


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.f = PreTagFixture(self.temp.name)

    def reject(self):
        with self.assertRaises(ConsumerError):
            self.f.admit()

    def recommit(self):
        self.f.sha = self.f.source = commit(self.f.root)
        self.f.tree = command(self.f.root, 'rev-parse', 'HEAD^{tree}')
        self.f.env.update(GITHUB_SHA=self.f.sha, GITHUB_WORKFLOW_SHA=self.f.sha)
        self.f.api = PreTagAPI(self.f, self.f.data)

    def test_real_clean_six_slot_reviewed_source_without_tag(self):
        before = dict(os.environ)
        admitted = self.f.admit()
        self.assertEqual(admitted.source.source_sha, self.f.sha)
        self.assertEqual(admitted.source.source_tree, self.f.tree)
        self.assertEqual(admitted.candidate.desktop_versions, (self.f.version,) * 6)
        self.assertEqual(admitted.candidate.gateway_version, self.f.version)
        self.assertEqual(admitted.invocation.role, 'pretag')
        self.assertEqual(admitted.job_id, OWN_JOB)
        self.assertEqual(admitted.candidate.remote_tag_observation, 'unknown')
        self.assertEqual(admitted.candidate.local_tag_observation, 'absent')
        self.assertEqual(command(self.f.root, 'tag', '--list'), '')
        self.assertEqual(dict(os.environ), before)
        self.assertTrue(all(body.closed for body in self.f.api.tag_bodies))
        with self.assertRaises(FrozenInstanceError):
            admitted.job_id = 7

    def test_absent_tag_still_rejected_by_unchanged_posttag_consumer(self):
        env = post_environment(self.f.sha)
        env['GITHUB_REPOSITORY_ID'] = str(types.REPOSITORY_ID)
        with self.f.reviewed(), self.assertRaises(ConsumerError):
            snapshot.resolve_candidate(self.f.root, self.f.api.expected, env, self.f.api)
        self.assertEqual(command(self.f.root, 'tag', '--list'), '')

    def test_existing_lightweight_tag_passes_posttag_and_blocks_pretag(self):
        tag = 'v' + self.f.version
        command(self.f.root, 'tag', tag)
        self.f.api.data['/git/ref/tags/' + tag] = dict(ref='refs/tags/' + tag,
                                                     object=dict(type='commit', sha=self.f.sha))
        env = post_environment(self.f.sha)
        env['GITHUB_REPOSITORY_ID'] = str(types.REPOSITORY_ID)
        with self.f.reviewed():
            value = snapshot.resolve_candidate(self.f.root, self.f.api.expected, env, self.f.api)
        self.assertEqual(value['tag_object_sha'], self.f.sha)
        self.reject()
        self.assertEqual(command(self.f.root, 'rev-parse', tag), self.f.sha)

    def test_annotated_and_foreign_local_tags_reject_without_repair(self):
        tag = 'v' + self.f.version
        command(self.f.root, '-c', 'user.name=Fixture', '-c', 'user.email=f@example.invalid',
                'tag', '-a', tag, '-m', 'Synthetic annotation')
        self.reject()
        command(self.f.root, 'tag', '-d', tag)
        command(self.f.root, 'tag', tag, self.f.baseline)
        self.reject()
        self.assertEqual(command(self.f.root, 'rev-parse', tag), self.f.baseline)

    def test_all_invocation_environment_fields_are_mandatory(self):
        for field in self.f.env.keys() - {'RUNNER_TEMP', 'GITHUB_OUTPUT'}:
            value = self.f.env.pop(field)
            with self.subTest(field=field):
                self.reject()
            self.f.env[field] = value

    def test_environment_identity_types_and_event_are_not_coerced(self):
        changes = [('GITHUB_ACTIONS', 'True'), ('RUNNER_OS', 'Windows'), ('GITHUB_JOB', 'other'),
            ('GITHUB_EVENT_NAME', 'workflow_dispatch'), ('GITHUB_REPOSITORY', 'other/repo'),
            ('GITHUB_SHA', 'a' * 40), ('GITHUB_WORKFLOW_SHA', 'b' * 40),
            ('GITHUB_WORKFLOW_REF', types.REPOSITORY + '/other.yml@' + self.f.ref)]
        changes += [(key, value) for key in ('GITHUB_REPOSITORY_ID', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT')
                    for value in ('0', '01', '1.0', True, 1, None, '-1', '1\n', str(2**63))]
        for field, value in changes:
            old = self.f.env[field]
            self.f.env[field] = value
            with self.subTest(field=field, value=value):
                self.reject()
            self.f.env[field] = old

    def test_actual_ref_requires_exact_version_and_alphanumeric_nonce(self):
        for ref in ('refs/heads/main', self.f.ref + '\n', self.f.ref[:-2],
                    self.f.ref.replace('Fixture01', 'bad_nonce'),
                    self.f.ref.replace(self.f.version, '0.6.2-rc.2'),
                    self.f.ref.replace(self.f.version, '0.6.2'),
                    self.f.ref.replace('Fixture01', 'a' * 65)):
            env = dict(self.f.env, GITHUB_REF=ref,
                       GITHUB_WORKFLOW_REF=types.REPOSITORY + '/' + WORKFLOW + '@' + ref)
            with self.subTest(ref=ref), self.assertRaises(ConsumerError), self.f.reviewed():
                admission.admit(self.f.root, env, self.f.api)

    def test_all_six_version_slots_reject_independently(self):
        fields = [('package.json', ('version',)), ('package-lock.json', ('version',)),
                  ('package-lock.json', ('packages', '', 'version')),
                  ('src-tauri/tauri.conf.json', ('version',))]
        for name, keys in fields:
            path = self.f.root / name
            raw = path.read_bytes(); value = json.loads(raw); target = value
            for key in keys[:-1]: target = target[key]
            target[keys[-1]] = '9.9.9-rc.9'; path.write_text(json.dumps(value))
            with self.subTest(name=name, keys=keys): self.reject()
            path.write_bytes(raw)
        for name in ('src-tauri/Cargo.toml', 'src-tauri/Cargo.lock'):
            path = self.f.root / name; raw = path.read_bytes()
            path.write_bytes(raw.replace(self.f.version.encode(), b'9.9.9-rc.9'))
            with self.subTest(name=name): self.reject()
            path.write_bytes(raw)

    def test_gateway_alignment_rejects_committed_wrong_version(self):
        for name in ('Cargo.toml', 'Cargo.lock'):
            path = self.f.root / 'services/cloud-gateway' / name
            path.write_text(path.read_text().replace(self.f.version, '0.1.0'))
        self.recommit(); self.reject()
        self.assertFalse(self.f.api.calls)

    def test_tracked_untracked_and_ignored_source_reject_before_api(self):
        path = self.f.root / 'package.json'; raw = path.read_bytes()
        path.write_bytes(raw + b'\n'); self.reject(); path.write_bytes(raw)
        path = self.f.root / 'unexpected'; path.write_text('not committed')
        self.reject(); path.unlink()
        (self.f.root / '.git/info/exclude').write_text('ignored\n')
        (self.f.root / 'ignored').write_text('also rejected')
        self.reject()
        self.assertFalse(self.f.api.calls)

    def test_missing_reviewed_manifest_is_not_generated(self):
        path = self.f.root / snapshot.gate.reviewed.MANIFEST
        path.unlink(); self.recommit(); self.reject()
        self.assertFalse(path.exists())
        self.assertFalse(self.f.api.calls)

    def test_unreviewed_commit_is_not_covered_by_frozen_manifest(self):
        (self.f.root / 'unreviewed-source').write_text('outside frozen entries')
        self.recommit(); self.reject()
        self.assertFalse(self.f.api.calls)

    def test_manifest_schema_and_version_are_real_gate_checks(self):
        path = self.f.root / snapshot.gate.reviewed.MANIFEST
        value = json.loads(path.read_text()); value['schema'] = True
        path.write_text(json.dumps(value)); self.recommit(); self.reject()
        value['schema'], value['version'] = 1, '9.9.9-rc.1'
        path.write_text(json.dumps(value)); self.recommit(); self.reject()

    def test_workflow_missing_or_symlink_is_not_committed_regular_identity(self):
        path = self.f.root / WORKFLOW
        path.unlink(); self.recommit(); self.reject()
        path.symlink_to('../../package.json'); self.recommit(); self.reject()
        self.assertFalse(self.f.api.calls)

    def test_head_mismatch_rejects_before_live_reads(self):
        command(self.f.root, 'checkout', '--detach', self.f.baseline)
        self.reject(); self.assertFalse(self.f.api.calls)

    def test_repository_ref_commit_tree_and_workflow_live_identity(self):
        routes = [('/', 'id', True), ('/', 'id', 7), ('/', 'full_name', 'other/repo'),
            ('/git/commits/' + self.f.sha, 'sha', 'a' * 40),
            ('/git/commits/' + self.f.sha, 'tree', dict(sha='b' * 40)),
            ('/actions/workflows/rc-pretag-evidence.yml', 'id', 20.0),
            ('/actions/workflows/rc-pretag-evidence.yml', 'path', '.github/workflows/other.yml'),
            ('/actions/workflows/rc-pretag-evidence.yml', 'state', 'disabled_manually')]
        branch = '/git/ref/heads/' + self.f.ref.removeprefix('refs/heads/')
        routes += [(branch, 'ref', 'refs/heads/other'), (branch, 'object', dict(type='tag', sha=self.f.sha)),
                   (branch, 'object', dict(type='commit', sha='a' * 40))]
        for route, key, value in routes:
            original = copy.deepcopy(self.f.api.data[route]); self.f.api.data[route][key] = value
            with self.subTest(route=route, key=key): self.reject()
            self.f.api.data[route] = original

    def test_current_and_exact_attempt_runs_must_be_live_and_matching(self):
        changes = [('id', OWN_RUN + 1), ('run_attempt', OWN_ATTEMPT + 1), ('run_number', True),
            ('workflow_id', 21), ('head_sha', 'b' * 40), ('event', 'workflow_dispatch'),
            ('head_branch', FINAL_BRANCH), ('path', '.github/workflows/other.yml'),
            ('repository', dict(id=7, full_name=types.REPOSITORY)),
            ('head_repository', dict(id=types.REPOSITORY_ID, full_name='other/repo')),
            ('status', 'queued'), ('status', 'completed'), ('status', 'waiting'),
            ('conclusion', 'cancelled'), ('conclusion', 'success'), ('conclusion', 'skipped')]
        for route in (self.f.api.own_run_path(), self.f.api.own_attempt_path()):
            for key, value in changes:
                original = copy.deepcopy(self.f.api.data[route]); self.f.api.data[route][key] = value
                with self.subTest(route=route, key=key, value=value): self.reject()
                self.f.api.data[route] = original

    def test_active_job_requires_exact_unique_identity_attempt_and_status(self):
        route = self.f.api.own_jobs_path(); original = copy.deepcopy(self.f.api.data[route])
        changes = [('id', True), ('id', 9001.0), ('id', 0), ('run_id', 901),
            ('run_attempt', 4), ('run_attempt', 3.0), ('head_sha', 'a' * 40), ('name', 'wrong'),
            ('status', 'queued'), ('status', 'completed'), ('conclusion', 'skipped'),
            ('conclusion', 'cancelled'), ('conclusion', 'success'), ('started_at', None),
            ('completed_at', '2026-10-01T00:04:00Z')]
        for key, value in changes:
            self.f.api.data[route] = copy.deepcopy(original)
            self.f.api.data[route]['jobs'][0][key] = value
            with self.subTest(key=key, value=value): self.reject()
        for jobs in ([], original['jobs'] * 2, original['jobs'] + [dict(original['jobs'][0], id=99)]):
            self.f.api.data[route] = dict(total_count=len(jobs), jobs=jobs); self.reject()

    def test_own_updated_at_is_not_frozen_like_completed_producer(self):
        captured = self.f.capture()
        for route in (self.f.api.own_run_path(), self.f.api.own_attempt_path()):
            self.f.api.data[route]['updated_at'] = '2026-10-01T00:05:00Z'
        self.f.revalidate(captured)

    def test_typed_403_404_remain_unknown_only_after_close(self):
        for status in (403, 404):
            self.f.api.tag_status = status
            result = self.f.admit()
            self.assertEqual(result.candidate.remote_tag_observation, 'unknown')
            self.assertIn(result.candidate.tag_visibility, ('unknown', 'denied'))
            self.assertTrue(self.f.api.tag_bodies[-1].closed)

    def test_known_remote_tag_collision_and_malformed_200_reject(self):
        for value in ({}, [], dict(ref='refs/tags/wrong', object=dict(type='commit', sha=self.f.sha)),
            dict(ref='refs/tags/v' + self.f.version, object=dict(type='commit', sha='broken')),
            dict(ref='refs/tags/v' + self.f.version, object=dict(type='commit', sha=self.f.sha)),
            dict(ref='refs/tags/v' + self.f.version, object=dict(type='tag', sha='a' * 40))):
            self.f.api.tag_response = value
            with self.subTest(value=value): self.reject()

    def test_non403404_and_untyped_tag_failures_are_terminal(self):
        for status in (301, 302, 401, 408, 429, 500, 503):
            self.f.api.tag_status = status
            with self.subTest(status=status): self.reject()
        for error in (TimeoutError('secret'), OSError('secret'), ValueError('secret'),
                      ConsumerError('invalid_snapshot')):
            self.f.api.tag_error = error
            with self.subTest(error=type(error).__name__): self.reject()

    def test_known_visibility_error_close_failure_is_terminal(self):
        class FailingClose(io.BytesIO):
            def close(self):
                super().close()
                raise OSError('secret close error')
        for status in (403, 404):
            self.f.api.tag_error = urllib.error.HTTPError('https://api.github.com/synthetic', status,
                                                          'secret', {}, FailingClose())
            self.reject()

    def test_tag_cancellation_cannot_become_unknown_visibility(self):
        for error in (KeyboardInterrupt(), SystemExit(1)):
            self.f.api.tag_error = error
            with self.assertRaises(type(error)): self.f.admit()

    def test_runtime_is_exact_linux_cpython312(self):
        for module, name, value in ((admission.sys, 'platform', 'win32'),
                (admission.sys, 'version_info', (3, 11)),
                (admission.platform, 'python_implementation', lambda: 'PyPy')):
            with patch.object(module, name, value): self.reject()

    def test_local_tag_command_failure_cannot_be_missing(self):
        original = admission.subprocess.run
        def failing(*args, **kwargs):
            argv = args[0]
            if 'show-ref' in argv or ('rev-parse' in argv and any(str(x).startswith('refs/tags/') for x in argv)):
                return subprocess.CompletedProcess(argv, 128, stdout='', stderr='synthetic')
            return original(*args, **kwargs)
        with patch.object(admission.subprocess, 'run', side_effect=failing): self.reject()

    def test_shared_selector_direct_inputs_reject_before_network(self):
        with self.assertRaisesRegex(ConsumerError, 'invalid_expectations'): snapshot.select_source_runs(self.f.api, None, {})
        with self.assertRaisesRegex(ConsumerError, 'invalid_expectations'): snapshot.resolve_candidate(self.f.root, {}, {}, self.f.api)
        expected = self.f.api.expected
        for key in expected.keys() - {'rc_version', 'release_tag', 'source_sha'}:
            for value in (True, False, 0, -1, 1.0, '1', None):
                with self.subTest(key=key, value=value), self.assertRaises(ConsumerError):
                    snapshot._select_source_runs_for_identity(self.f.api, self.f.sha,
                        types.REPOSITORY_ID, dict(expected, **{key: value}))
        for source, repo in [('a' * 40, types.REPOSITORY_ID), (self.f.sha, True),
                             (self.f.sha, 1.0), (self.f.sha, 0)]:
            with self.assertRaises(ConsumerError):
                snapshot._select_source_runs_for_identity(self.f.api, source, repo, expected)
        self.assertFalse(self.f.api.calls)

    def test_j_supported_integration_branch_can_differ_from_final(self):
        self.f.api.data['/actions/runs/456']['head_branch'] = 'integration-fixture'
        captured = self.f.capture(); self.f.revalidate(captured)
        self.assertNotEqual(captured[2]['integration']['run']['head_branch'], FINAL_BRANCH)

    def test_fixed_admission_and_final_branch_change_reject_freshness(self):
        captured = self.f.capture()
        route = '/git/ref/heads/' + FINAL_BRANCH
        self.f.api.data[route]['object']['sha'] = 'a' * 40
        with self.assertRaises(ConsumerError): self.f.revalidate(captured)
        self.f.api.data[route]['object']['sha'] = self.f.sha
        self.f.api.data[self.f.api.own_jobs_path()]['jobs'][0]['id'] += 1
        with self.assertRaises(ConsumerError): self.f.revalidate(captured)

    def test_final_source_fence_rechecks_after_artifact_metadata(self):
        captured = self.f.capture(); original = self.f.api.get
        def racing(path):
            value = original(path)
            if path == '/actions/artifacts/13':
                (self.f.root / 'appeared-during-fence').write_text('synthetic race')
            return value
        self.f.api.get = racing
        with self.assertRaises(ConsumerError): self.f.revalidate(captured)

    def test_frozen_own_run_and_attempt_are_not_replaced_during_fence(self):
        captured = self.f.capture()
        routes = (self.f.api.own_run_path(), self.f.api.own_attempt_path())
        original = {route: copy.deepcopy(self.f.api.data[route]) for route in routes}
        for key, value in (('run_number', 31), ('created_at', '2026-09-30T23:59:59Z'),
                           ('run_attempt', 4), ('conclusion', 'cancelled')):
            for route in routes: self.f.api.data[route][key] = value
            with self.subTest(key=key), self.assertRaises(ConsumerError): self.f.revalidate(captured)
            for route in routes: self.f.api.data[route] = copy.deepcopy(original[route])

    def test_discovery_values_cannot_replace_strict_fixed_selection(self):
        admitted = self.f.admit(); expected = admission.discover(self.f.api, admitted)
        route = f'/actions/workflows/11/runs?head_sha={self.f.sha}&per_page=100&page=1'
        newer = dict(self.f.api.data['/actions/runs/123'], id=124, conclusion='failure')
        self.f.api.data[route] = dict(total_count=2, workflow_runs=[newer, self.f.api.data['/actions/runs/123']])
        self.f.api.data['/actions/runs/124'] = newer
        with self.assertRaises(ConsumerError):
            snapshot._select_source_runs_for_identity(self.f.api, self.f.sha, types.REPOSITORY_ID, expected)

    def test_visibility_change_cannot_promote_unknown_to_absence(self):
        captured = self.f.capture(); self.f.api.tag_status = 403
        with self.assertRaises(ConsumerError): self.f.revalidate(captured)
        self.assertEqual(captured[0].candidate.remote_tag_observation, 'unknown')


if __name__ == '__main__':
    unittest.main()
