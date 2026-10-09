"""Synthetic seven-job shapes over verified TLS; no hosted acceptance or authority."""
from collections import Counter
from copy import deepcopy
from dataclasses import asdict, FrozenInstanceError, replace
import hashlib
import io
import json
import tempfile
import time
import unittest
from unittest.mock import patch

import rc_publication_admission as admission
import rc_publication_contract as core
import rc_publication_executor as executor
import rc_publication_github as wire
from rc_consumer_io import ConsumerError
from rc_publication_https_fixture import HTTPSFixture
from rc_publication_stage import Selection
from rc_release_policy import GATE_IDS, GATES


def adopt_selection(fixture, selection):
    """Reseal trusted fixture data through a fresh actual credential client."""
    previous = getattr(fixture, 'api', None)
    if previous is not None:
        if type(previous) is not wire.GitHub:
            raise AssertionError('fixture reseal requires actual GitHub client')
        current = wire.GitHub('fixture-token', selection)
        previous.close()
        fixture.api = current
        selection = current.selection
    fixture.selection = selection
    fixture.subject = selection.subject


class IntegrationTLS(HTTPSFixture):
    """Exact API fixture, using only the existing verified loopback connection seam."""
    def __init__(self):
        super().__init__()
        self.counts, self.hook = Counter(), None
        s, i = self.subject.source, self.subject.runs[1]
        repo = dict(id=s.repository_id, full_name=s.repository)
        self.run = dict(id=i.run_id, run_attempt=i.run_attempt, run_number=17, workflow_id=i.workflow_id,
            path=i.workflow_path, head_sha=s.source_sha, status='completed', conclusion='success',
            run_started_at='2026-10-01T00:01:00Z', updated_at='2026-10-01T00:10:00Z',
            repository=deepcopy(repo), head_repository=deepcopy(repo), event=i.event,
            head_branch=i.ref[11:], created_at='2026-10-01T00:00:00Z')
        self.jobs = [dict(id=3201+n, run_id=i.run_id, run_attempt=i.run_attempt, name=name,
            head_sha=s.source_sha, status='completed', conclusion='success',
            started_at='2026-10-01T00:02:00Z', completed_at='2026-10-01T00:09:00Z')
            for n, name in enumerate(sorted(admission.gate.final.REQUIRED_JOBS))]
        self.workflow = '/actions/workflows/dot-rc-integration.yml'
        self.runs = f'/actions/workflows/{i.workflow_id}/runs?head_sha={s.source_sha}&per_page=100&page=1'
        self.current = f'/actions/runs/{i.run_id}'
        self.attempt = self.current + f'/attempts/{i.run_attempt}'
        self.job_path = self.attempt + '/jobs?per_page=100&page=1'
        self.sources = ['/', '/git/ref/' + i.ref[5:], '/git/commits/' + s.source_sha,
                        '/git/trees/' + s.source_tree, '/git/trees/' + 'd'*40, '/git/trees/' + 'e'*40]
        self.data = {'/': repo, self.sources[1]: dict(ref=i.ref, object=dict(type='commit', sha=s.source_sha)),
            self.sources[2]: dict(sha=s.source_sha, tree=dict(sha=s.source_tree)),
            self.workflow: dict(id=i.workflow_id, path=i.workflow_path, state='active'),
            self.runs: dict(total_count=1, workflow_runs=[self.run]), self.current: self.run,
            self.attempt: self.run, self.job_path: dict(total_count=7, jobs=self.jobs)}
        for path, name, child, mode, kind in zip(self.sources[3:], ('.github', 'workflows', 'dot-rc-integration.yml'),
                ('d'*40, 'e'*40, i.workflow_blob), ('040000', '040000', '100644'), ('tree', 'tree', 'blob')):
            self.data[path] = dict(sha=path.rsplit('/', 1)[1], truncated=False,
                                  tree=[dict(path=name, mode=mode, type=kind, sha=child)])
        self.subject = replace(self.subject, job_ids=(self.subject.job_ids[0],
            tuple(j['id'] for j in self.jobs), self.subject.job_ids[2]))
        self.seal()
        one = [self.workflow, self.runs, self.current, self.job_path, self.current, self.attempt]
        self.expected_paths = [wire.ROOT + ('' if p == '/' else p)
                               for p in self.sources + one*2 + [self.runs, self.current] + self.sources]
        self.route = self.integration_route
        from rc_publication_final_admission_cases import add_final
        add_final(self)

    def reference_digest(self):
        s, i = self.subject.source, self.subject.runs[1]
        observation = dict(repository=dict(id=s.repository_id, full_name=s.repository),
            ref=dict(ref=i.ref, object=dict(type='commit', sha=s.source_sha)),
            commit=dict(sha=s.source_sha, tree=s.source_tree), trees=[s.source_tree, 'd'*40, 'e'*40],
            workflow=dict(path=i.workflow_path, mode='100644', sha=i.workflow_blob))
        value = dict(schema='rc-full-integration-v1', gate_id='full_integration', source=asdict(s),
            invocation=asdict(i), source_observation=observation,
            evidence=dict(workflow=dict(id=i.workflow_id, path=i.workflow_path), run=deepcopy(self.run),
                          jobs=sorted(deepcopy(self.jobs), key=lambda j: j['id'])))
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                        ensure_ascii=True, allow_nan=False).encode()).hexdigest()

    def seal(self):
        digests = list(self.subject.gate_evidence)
        digests[GATE_IDS.index('full_integration')] = self.reference_digest()
        self.subject = replace(self.subject, gate_evidence=tuple(digests))
        adopt_selection(self, Selection(self.subject, 41, 1, '1'*64))

    def integration_route(self, method, path, headers, body):
        suffix = path.removeprefix(wire.ROOT) or '/'
        if method != 'GET' or suffix not in self.data:
            return None
        self.counts[suffix] += 1
        value = deepcopy(self.data[suffix])
        if self.hook:
            response = self.hook(suffix, self.counts[suffix], value)
            if response is not None:
                return response
        return self.response(value)

    def __enter__(self):
        super().__enter__()
        self.connection = patch.object(wire, '_connect', side_effect=self.connect)
        self.connection.start()
        self.api = wire.GitHub('fixture-token', self.selection)
        self.selection = self.api.selection
        self.subject = self.selection.subject
        return self

    def __exit__(self, *args):
        self.api.close()
        self.connection.stop()
        super().__exit__(*args)


class AdmissionCases(unittest.TestCase):
    def observe(self, f, active=lambda: None, deadline=None):
        return admission.authenticate_integration(f.api, f.selection, check_active=active,
            deadline=time.monotonic()+30 if deadline is None else deadline)

    def blocked(self, f, code='fence_blocked', active=lambda: None, deadline=None):
        with self.assertRaises(wire.WireFailure) as caught:
            wire._authenticate(f.selection, f.api, check_active=active,
                deadline=time.monotonic()+30 if deadline is None else deadline)
        self.assertEqual((caught.exception.code, caught.exception.effect), (code, 'none'))
        self.assertTrue(all(row[0] == 'GET' and row[3] == b'' for row in f.requests))

    def rejection(self, change):
        with IntegrationTLS() as f:
            change(f)
            self.blocked(f, 'verification_failed')
            self.assertEqual(f.errors, [])

    def test_exact_seven_jobs_returns_blocked_partial_evidence(self):
        with IntegrationTLS() as f:
            result = self.observe(f)
            self.assertEqual(result.integration_evidence_sha256, f.reference_digest())
            self.assertEqual(result.status, 'blocked')
            self.assertEqual(result.evidence_authentication, 'partial')
            self.assertEqual(result.draft_visibility, 'unknown')
            self.assertFalse(result.release_approved or result.publish_approved or result.snapshot_atomic)
            self.assertEqual(tuple(r[0] for r in result.rows), GATE_IDS)
            self.assertEqual([r[0] for r in result.rows if r[3] == 'passed'], ['full_integration'])
            self.assertEqual([r[1] for r in f.requests], f.expected_paths)
            self.assertTrue(all(r[2]['authorization'] == 'Bearer fixture-token' for r in f.requests))
            with self.assertRaises(FrozenInstanceError): result.status = 'eligible'
            self.assertTrue(all(r[3] == 'unknown' for r in result.rows if r[0] != 'full_integration'))

    def test_gate_digest_canonical_order_and_binding(self):
        with IntegrationTLS() as f:
            f.jobs.reverse()
            f.run['repository']['description'] = 'incidental metadata'
            self.assertEqual(self.observe(f).integration_evidence_sha256, f.subject.gate_evidence[GATE_IDS.index('full_integration')])
            adopt_selection(f, replace(f.selection,
                subject=replace(f.subject, gate_evidence=('0'*64,)*len(GATE_IDS))))
            self.blocked(f, 'verification_failed')

    def test_frozen_source_tree_and_repository_identity_rejected(self):
        for target, field, value in (('/', 'id', True), ('/', 'full_name', 'foreign/repo'),
                ('commit', 'sha', 'f'*40), ('commit', 'tree', {'sha': 'f'*40}),
                ('run', 'repository', {'id': 9, 'full_name': wire.REPOSITORY}),
                ('run', 'head_repository', {'id': 9, 'full_name': wire.REPOSITORY})):
            with self.subTest(target=target, field=field):
                self.rejection(lambda f: (f.run if target == 'run' else f.data[f.sources[2] if target == 'commit' else target]).update({field: value}))

    def test_workflow_path_id_blob_mode_and_tree_completeness_rejected(self):
        for field, value in (('id', 999), ('path', '.github/workflows/fixture.yml'), ('state', 'disabled_manually')):
            self.rejection(lambda f: f.data[f.workflow].update({field: value}))
        for field, value in (('mode', '100755'), ('type', 'tree'), ('path', 'wrong.yml'), ('sha', 'f'*40)):
            self.rejection(lambda f: f.data[f.sources[-1]]['tree'][0].update({field: value}))
        self.rejection(lambda f: f.data[f.sources[3]].update(truncated=True))
        self.rejection(lambda f: f.data[f.sources[3]]['tree'].append(deepcopy(f.data[f.sources[3]]['tree'][0])))
        # Recorded postmerge hermetic identities are negative projections, never raw-response replay or integration proof.
        for run_id, path in ((37618132128, 'rc-pretag-evidence-checks.yml'),
                             (37618132066, 'rc-artifact-consumer-checks.yml')):
            self.rejection(lambda f: f.run.update(id=run_id, path='.github/workflows/'+path,
                head_sha='c2b5afb2c46318e2c54283f8442d5996e55f0a73', run_attempt=1))

    def test_event_ref_and_pr_merge_selection_rejected(self):
        for field, value in (('event', 'pull_request'), ('head_branch', 'foreign')):
            self.rejection(lambda f: f.run.update({field: value}))
        self.rejection(lambda f: f.data[f.sources[1]]['object'].update(type='tag'))
        with IntegrationTLS() as f:
            i = replace(f.subject.runs[1], event='pull_request', ref='refs/pull/123/merge',
                workflow_ref=wire.REPOSITORY+'/'+f.subject.runs[1].workflow_path+'@refs/pull/123/merge')
            adopt_selection(f, replace(f.selection,
                subject=replace(f.subject, runs=(f.subject.runs[0], i, f.subject.runs[2]))))
            self.blocked(f, 'verification_failed'); self.assertEqual(f.requests, [])
            with self.assertRaises(ValueError):
                replace(i, event='push', ref='refs/tags/v0.7.0-rc.1',
                    workflow_ref=wire.REPOSITORY+'/'+i.workflow_path+'@refs/tags/v0.7.0-rc.1')

    def test_exact_run_attempt_and_selected_job_ids_rejected(self):
        for field, value in (('id', 999), ('run_attempt', 2), ('workflow_id', 999), ('head_sha', 'f'*40)):
            self.rejection(lambda f: f.run.update({field: value}))
        self.rejection(lambda f: f.jobs[0].update(id=999))

    def test_exact_seven_job_names_status_and_times_rejected(self):
        for field, value in (('name', 'hermetic fixture'), ('status', 'queued'), ('conclusion', 'skipped'),
                ('run_id', 999), ('run_attempt', 2), ('head_sha', 'f'*40),
                ('started_at', '2026-10-01T00:00:00Z'), ('completed_at', '2026-10-01T00:11:00Z')):
            self.rejection(lambda f: f.jobs[0].update({field: value}))
        self.rejection(lambda f: f.jobs[0].update(name=f.jobs[1]['name']))
        self.rejection(lambda f: f.jobs[0].update(id=f.jobs[1]['id']))
        self.rejection(lambda f: f.jobs.pop())
        self.rejection(lambda f: f.jobs.append(dict(f.jobs[0], id=999)))

    def test_newer_unsuccessful_run_never_falls_back(self):
        for status, conclusion in (('queued', None), ('in_progress', None), ('completed', 'failure'),
                                   ('completed', 'cancelled'), ('completed', 'skipped')):
            def change(f):
                newer = dict(f.run, id=99, status=status, conclusion=conclusion)
                f.data[f.runs] = dict(total_count=2, workflow_runs=[f.run, newer])
                f.data['/actions/runs/99'] = newer
            self.rejection(change)

    def test_paginated_newest_run_selection_has_exact_inventory(self):
        with IntegrationTLS() as f:
            i = replace(f.subject.runs[1], run_id=1001)
            f.subject = replace(f.subject, runs=(f.subject.runs[0], i, f.subject.runs[2]))
            f.run['id'] = 1001
            for j in f.jobs: j['run_id'] = 1001
            for old, new in ((f.current, '/actions/runs/1001'), (f.attempt, '/actions/runs/1001/attempts/1'),
                             (f.job_path, '/actions/runs/1001/attempts/1/jobs?per_page=100&page=1')):
                f.data[new] = f.data.pop(old)
            f.data[f.runs] = dict(total_count=101, workflow_runs=[dict(f.run, id=n) for n in range(1, 101)])
            f.data[f.runs[:-1]+'2'] = dict(total_count=101, workflow_runs=[f.run])
            f.seal()
            self.observe(f)
            self.assertEqual(f.counts[f.runs[:-1]+'2'], 3)

    def test_pagination_counts_duplicates_truncation_and_cap_rejected(self):
        for count, rows in ((2, 1), (0, 1), (True, 1), (1001, 1), (2, 2)):
            self.rejection(lambda f: f.data.update({f.runs: dict(total_count=count, workflow_runs=[f.run]*rows)}))
        def capped(f):
            for page in range(1, 11):
                f.data[f.runs[:-1]+str(page)] = dict(total_count=1000,
                    workflow_runs=[dict(f.run, id=(page-1)*100+n+1) for n in range(100)])
        self.rejection(capped)
        def drift(f):
            f.data[f.runs] = dict(total_count=101, workflow_runs=[dict(f.run, id=n) for n in range(1, 101)])
            f.data[f.runs[:-1]+'2'] = dict(total_count=102, workflow_runs=[dict(f.run, id=101)])
        self.rejection(drift)

    def test_run_attempt_and_current_snapshot_drift_rejected(self):
        for target in ('current', 'attempt'):
            for field, value in (('run_attempt', 2), ('event', 'workflow_dispatch'), ('updated_at', '2026-10-01T00:11:00Z')):
                def change(f):
                    def hook(path, count, row):
                        if path == getattr(f, target) and count == (2 if target == 'current' else 1): row[field] = value
                    f.hook = hook
                self.rejection(change)

    def test_job_inventory_and_fields_drift_rejected(self):
        for field, value in (('id', 999), ('name', 'foreign'), ('conclusion', 'failure'),
                             ('completed_at', '2026-10-01T00:08:00Z')):
            def change(f):
                def hook(path, count, row):
                    if path == f.job_path and count == 2: row['jobs'][0][field] = value
                f.hook = hook
            self.rejection(change)

    def test_workflow_ref_source_tree_reobserve_drift_rejected(self):
        for index in range(6):
            def change(f):
                def hook(path, count, row):
                    if path == f.sources[index] and count == 2:
                        if index == 0: row['id'] = 999
                        elif index == 1: row['object']['sha'] = 'f'*40
                        else: row['sha'] = 'f'*40
                f.hook = hook
            self.rejection(change)
        self.rejection(lambda f: setattr(f, 'hook', lambda p, n, r: r.update(state='disabled_manually')
            if p == f.workflow and n == 2 else None))

    def test_late_newer_run_blocks_frozen_selection(self):
        for occurrence in (2, 3):
            def change(f):
                def hook(path, count, row):
                    if path == f.runs and count == occurrence:
                        row.update(total_count=2, workflow_runs=[f.run, dict(f.run, id=999, conclusion='failure')])
                f.hook = hook
                f.data['/actions/runs/999'] = dict(f.run, id=999, conclusion='failure')
            self.rejection(change)

    def test_metadata_denial_absence_redirect_and_nonjson_rejected(self):
        for status in (401, 403, 404, 302, 500):
            with IntegrationTLS() as f:
                f.routes['GET', wire.ROOT] = status, {'Location': 'https://foreign.invalid/private'}, b'secret-token'
                self.blocked(f, 'verification_failed'); self.assertEqual(len(f.requests), 1)
        self.rejection(lambda f: f.routes.update({('GET', wire.ROOT): (200, {}, b'<html>private</html>')}))

    def test_metadata_parser_limits_and_duplicate_fields_rejected(self):
        for raw in (b'{"id":1,"id":2}', b'{"value":NaN}', b'['*40+b']'*40, b' '* (wire.METADATA+1)):
            self.rejection(lambda f: f.routes.update({('GET', wire.ROOT): (200, {}, raw)}))

    def test_cancelled_before_connect_sends_no_request(self):
        with IntegrationTLS() as f, patch.object(wire, '_connect') as connect:
            def cancelled(): raise wire.WireFailure('cancelled', 'none')
            self.blocked(f, 'cancelled', cancelled)
            connect.assert_not_called(); self.assertEqual(f.requests, [])

    def test_cancelled_during_reads_returns_no_partial_result(self):
        with IntegrationTLS() as f:
            cancelled = []
            f.hook = lambda p, n, r: cancelled.append(True) if p == f.job_path else None
            def active():
                if cancelled: raise wire.WireFailure('cancelled', 'none')
            self.blocked(f, 'cancelled', active)
            self.assertEqual(f.counts[f.job_path], 1)

    def test_one_absolute_deadline_covers_all_reads(self):
        with IntegrationTLS() as f:
            def delayed(path, count, row):
                raw = json.dumps(row).encode()
                return dict(delay=0.015, raw=b'HTTP/1.1 200 OK\r\nContent-Length: '+str(len(raw)).encode()+b'\r\n\r\n'+raw)
            f.hook = delayed
            start = time.monotonic()
            self.blocked(f, 'timeout', deadline=start+0.12)
            self.assertLess(time.monotonic()-start, 0.5)
            self.assertGreaterEqual(len(f.requests), 2); self.assertLess(len(f.requests), len(f.expected_paths))
        for deadline in (0, float('nan'), float('inf'), True):
            with IntegrationTLS() as f:
                self.blocked(f, 'timeout' if deadline == 0 else 'verification_failed', deadline=deadline)
                self.assertEqual(f.requests, [])

    def test_repeat_invocation_reobserves_without_cached_authority(self):
        with IntegrationTLS() as f:
            self.observe(f); self.assertEqual(f.counts[f.runs], 3)
            f.run['conclusion'] = 'failure'
            self.blocked(f, 'verification_failed')
            self.assertEqual(f.counts[f.runs], 4)
            self.assertFalse(hasattr(f.api, '_admission'))

    def test_authenticate_real_reads_and_blocks_remaining_gates(self):
        with IntegrationTLS() as f:
            self.blocked(f)
            self.assertEqual([r[1] for r in f.requests], f.packaging_paths)
            self.assertEqual([g.gate_id for g in GATES if g.verifier != 'unimplemented'],
                             ['raw_cloud_audit', 'raw_noncloud_audits', 'full_integration', 'final_packaging', 'bundle_bytes'])
            with self.assertRaises(wire.WireFailure): wire._remote_constraint(f.subject)
            with self.assertRaises(wire.WireFailure): wire._authenticated_latest_absence(f.selection)

    def test_public_entry_authenticates_then_blocks_before_staging(self):
        import rc_publication_artifact_admission as artifacts
        with IntegrationTLS() as f, tempfile.TemporaryDirectory() as root, patch.object(artifacts, 'stage_selected',
                side_effect=wire.WireFailure('fence_blocked', 'none')) as stage:
            with executor.PublisherSession(root, f.selection, 'fixture-token', temporary_parent=root) as session:
                with self.assertRaises(wire.WireFailure) as error: session.run_until_pause()
                self.assertEqual((error.exception.code, session.outcome), ('fence_blocked', 'blocked_no_effect'))
                self.assertIsNone(session.transition); stage.assert_called_once()
            self.assertEqual([r[1] for r in f.requests], f.packaging_paths)
            self.assertTrue(all(r[0] == 'GET' and not r[3] for r in f.requests))

    def test_all_direct_mutation_sinks_authenticate_and_send_no_mutation(self):
        from rc_publication_native_admission_fixture import _pending_fence
        production_authenticate = wire._authenticate
        with IntegrationTLS() as f:
            create = core.Operation('CreateDraft', 2, 'a'*64, tag=f.subject.tag, draft=True, prerelease=True)
            upload = core.Operation('UploadAsset', 5, 'a'*64, release_id=100, asset_ordinal=0, asset=f.plan.assets[0])
            publish = core.Operation('PublishPrerelease', 24, 'a'*64, release_id=100, request_id='once', draft=False, prerelease=True)
            for operation in (create, upload, publish):
                before = len(f.requests)
                with patch.object(wire, '_authorize') as authorize:
                    with self.assertRaises(wire.WireFailure) as error:
                        options = dict(before_write=lambda: self.fail('mutation attempted'), check_active=lambda: None)
                        if operation.kind == 'CreateDraft': f.api.create_draft(operation, **options)
                        elif operation.kind == 'UploadAsset': f.api.upload_asset(operation, io.BytesIO(f.payloads[operation.asset.name]), **options)
                        else: f.api.publish_prerelease(operation, **options)
                    self.assertEqual((error.exception.code, error.exception.effect), ('invalid_request', 'none'))
                    authorize.assert_not_called()
                self.assertEqual([r[1] for r in f.requests[before:]], [])
                self.assertTrue(all(r[0] == 'GET' and not r[3] for r in f.requests))
        for kind in ('CreateDraft', 'UploadAsset', 'PublishPrerelease'):
            _pending_fence(self, kind, production_authenticate)

    def test_caller_claims_and_reports_cannot_bypass_fixed_authentication(self):
        import rc_publication_artifact_admission as artifacts
        from rc_pretag_fixtures import candidate, passing_claims
        from rc_release_eligibility import evaluate
        result = evaluate(candidate(), passing_claims())
        self.assertEqual((result.status, result.evidence_authentication), ('blocked', 'unverified'))
        self.assertTrue(all(r.status != 'passed' for r in result.rows))
        with IntegrationTLS() as f:
            f.api.get = lambda *args, **kwargs: self.fail('caller GET invoked')
            self.blocked(f)
            self.assertEqual([r[1] for r in f.requests], f.packaging_paths)
            class Foreign(wire.GitHub): pass
            canonical, owners = f.api.selection, tuple(artifacts._OWNERS)
            before_foreign = len(f.requests)
            with self.assertRaises(wire.WireFailure) as error:
                admission.authenticate_integration(Foreign('fixture-token', f.selection), f.selection,
                    check_active=lambda: None, deadline=time.monotonic()+30)
            self.assertIs(type(error.exception), wire.WireFailure)
            self.assertEqual((error.exception.code, error.exception.effect), ('invalid_request', 'none'))
            self.assertEqual(len(f.requests), before_foreign)
            self.assertIsNone(f.api._credential._session_owner)
            self.assertEqual(tuple(artifacts._OWNERS), owners)
            before = len(f.requests)
            options = dict(check_active=lambda: None, deadline=time.monotonic()+30)
            with self.assertRaises(TypeError): admission.authenticate_integration(f.api, f.selection, approved=True, **options)
            with self.assertRaises(TypeError): wire._authenticate(f.selection, f.api, approved=True, **options)
            forged = admission._AdmissionReport(f.subject, f.subject.gate_evidence[GATE_IDS.index('full_integration')])
            f.selection = forged
            self.blocked(f, 'verification_failed')
            self.assertEqual(len(f.requests), before)
            self.assertIs(f.api.selection, canonical)
            self.assertEqual(tuple(artifacts._OWNERS), owners)


if __name__ == '__main__':
    unittest.main()
