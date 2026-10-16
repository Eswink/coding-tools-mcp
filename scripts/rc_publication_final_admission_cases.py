"""Synthetic thirteen-job TLS metadata, never real FINAL or publication authority."""
from copy import deepcopy
from dataclasses import asdict, FrozenInstanceError, replace
import hashlib
import io
import json
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import rc_publication_admission as admission
from rc_publication_admission_cases import IntegrationTLS, adopt_selection
import rc_publication_contract as core
import rc_publication_executor as executor
import rc_publication_github as wire
from rc_consumer_io import ConsumerError
from rc_publication_stage import Selection
from rc_release_policy import GATE_IDS


def final_digest(f):
    s, invocation = f.subject.source, f.subject.runs[0]
    run = deepcopy(f.final_run)
    for key in ('repository', 'head_repository'):
        run[key] = {name: run[key][name] for name in ('id', 'full_name')}
    observation = dict(repository=dict(id=s.repository_id, full_name=s.repository),
        ref=dict(ref=invocation.ref, object=dict(type='commit', sha=s.source_sha)),
        commit=dict(sha=s.source_sha, tree=s.source_tree), trees=[s.source_tree, 'd'*40, 'e'*40],
        workflow=dict(path=invocation.workflow_path, mode='100644', sha=invocation.workflow_blob))
    canonical = dict(schema='rc-final-packaging-v1', gate_id='final_packaging', source=asdict(s),
        invocation=asdict(invocation), source_observation=observation,
        evidence=dict(workflow=dict(id=invocation.workflow_id, path=invocation.workflow_path),
                      run=run, jobs=sorted(deepcopy(f.final_jobs), key=lambda j: j['id'])))
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def seal_final(f):
    digests = list(f.subject.gate_evidence)
    digests[GATE_IDS.index('final_packaging')] = final_digest(f)
    f.subject = replace(f.subject, gate_evidence=tuple(digests))
    adopt_selection(f, Selection(f.subject, 41, 1, '1'*64))


def add_final(f):
    """Extend initialized integration data; preserve its receipt, trace and digest."""
    s, invocation = f.subject.source, f.subject.runs[0]
    f.final_run = dict(deepcopy(f.run), id=invocation.run_id, workflow_id=invocation.workflow_id,
        path=invocation.workflow_path, event=invocation.event, head_branch=invocation.ref[11:])
    f.final_jobs = [dict(deepcopy(f.jobs[0]), id=3101+n, run_id=invocation.run_id, name=name)
                    for n, name in enumerate(sorted(admission.gate.FINAL_JOBS))]
    f.final_workflow = '/actions/workflows/final-rc-packages.yml'
    f.final_runs = f'/actions/workflows/{invocation.workflow_id}/runs?head_sha={s.source_sha}&per_page=100&page=1'
    f.final_current = f'/actions/runs/{invocation.run_id}'
    f.final_attempt = f.final_current + '/attempts/1'
    f.final_job_path = f.final_attempt + '/jobs?per_page=100&page=1'
    f.final_sources = [f.sources[0], '/git/ref/' + invocation.ref[5:], *f.sources[2:]]
    f.data.update({f.final_sources[1]: dict(ref=invocation.ref, object=dict(type='commit', sha=s.source_sha)),
        f.final_workflow: dict(id=invocation.workflow_id, path=invocation.workflow_path, state='active'),
        f.final_runs: dict(total_count=1, workflow_runs=[f.final_run]), f.final_current: f.final_run,
        f.final_attempt: f.final_run, f.final_job_path: dict(total_count=13, jobs=f.final_jobs)})
    f.data[f.sources[-1]]['tree'].append(dict(path='final-rc-packages.yml', mode='100644',
                                            type='blob', sha=invocation.workflow_blob))
    f.subject = replace(f.subject, job_ids=(tuple(j['id'] for j in f.final_jobs), *f.subject.job_ids[1:]))
    seal_final(f)
    integration = [f.workflow, f.runs, f.current, f.job_path, f.current, f.attempt]
    final = [f.final_workflow, f.final_runs, f.final_current, f.final_job_path, f.final_current, f.final_attempt]
    f.packaging_paths = [wire.ROOT + ('' if p == '/' else p) for p in
        f.sources + f.final_sources + (integration + final)*2 +
        [f.runs, f.current, f.final_runs, f.final_current] + f.sources + f.final_sources]


class FinalAdmissionCases(unittest.TestCase):
    def observe(self, f, active=lambda: None, deadline=None):
        return admission.authenticate_packaging(f.api, f.selection, check_active=active,
            deadline=time.monotonic()+30 if deadline is None else deadline)

    def blocked(self, f, code='verification_failed', active=lambda: None, deadline=None):
        with self.assertRaises(wire.WireFailure) as error:
            wire._authenticate(f.selection, f.api, check_active=active,
                deadline=time.monotonic()+30 if deadline is None else deadline)
        self.assertEqual((error.exception.code, error.exception.effect), (code, 'none'))
        self.assertTrue(all(r[0] == 'GET' and not r[3] for r in f.requests))
        self.assertEqual(f.errors, [])

    def reject(self, change, endpoint=None):
        with IntegrationTLS() as f:
            change(f)
            self.blocked(f)
            if endpoint is not None:
                self.assertGreater(f.counts[getattr(f, endpoint)], 0)

    def test_exact_thirteen_jobs_returns_two_gate_blocked_report(self):
        with IntegrationTLS() as f:
            report = self.observe(f)
            self.assertEqual(len(f.final_jobs), 13)
            self.assertEqual(report.integration_evidence_sha256, f.reference_digest())
            self.assertEqual(report.final_evidence_sha256, final_digest(f))
            self.assertEqual((report.status, report.evidence_authentication, report.draft_visibility),
                             ('blocked', 'partial', 'unknown'))
            self.assertFalse(report.release_approved or report.publish_approved or report.snapshot_atomic)
            self.assertEqual(tuple(r[0] for r in report.rows), GATE_IDS)
            self.assertEqual([r[0] for r in report.rows if r[3] == 'passed'], ['full_integration', 'final_packaging'])
            self.assertTrue(all(r[3] == 'unknown' for r in report.rows if r[0] not in ('full_integration', 'final_packaging')))
            self.assertEqual([r[1] for r in f.requests], f.packaging_paths)
            self.assertEqual(len(f.requests), 52)
            self.assertTrue(all(r[2]['authorization'] == 'Bearer fixture-token' for r in f.requests))
            with self.assertRaises(FrozenInstanceError): report.final_evidence_sha256 = '0'*64

    def test_both_canonical_digests_and_incidental_metadata(self):
        with IntegrationTLS() as f:
            f.jobs.reverse(); f.final_jobs.reverse()
            f.data['/']['description'] = 'incidental'
            for run in (f.run, f.final_run): run['repository']['description'] = 'incidental'
            report = self.observe(f)
            self.assertEqual(report.integration_evidence_sha256, f.subject.gate_evidence[GATE_IDS.index('full_integration')])
            self.assertEqual(report.final_evidence_sha256, final_digest(f))
        for key in ('full_integration', 'final_packaging'):
            def change(f):
                values = list(f.subject.gate_evidence); values[GATE_IDS.index(key)] = '0'*64
                adopt_selection(f, replace(f.selection, subject=replace(f.subject, gate_evidence=tuple(values))))
            self.reject(change, 'final_attempt')

    def test_repository_source_and_selected_ref_identities_reject(self):
        for target, field, value in (('repository', 'id', True), ('head_repository', 'id', 999),
                ('repository', 'full_name', 'foreign/repo'), ('head_repository', 'full_name', 'foreign/repo')):
            self.reject(lambda f: f.final_run[target].update({field: value}), 'final_runs')
        for target, field, value in ((0, 'id', 999), (1, 'ref', 'refs/heads/foreign'),
                                    (2, 'sha', 'f'*40), (2, 'tree', {'sha': 'f'*40})):
            self.reject(lambda f: f.data[f.final_sources[target]].update({field: value}))
        self.reject(lambda f: f.data[f.final_sources[1]]['object'].update(type='tag'))

    def test_final_candidate_push_first_attempt_required(self):
        for field, value in (('event', 'workflow_dispatch'), ('event', 'pull_request'), ('run_attempt', 2),
                ('head_branch', 'main'), ('head_branch', 'release/full-rc-candidate-'), ('head_branch', 'v0.7.0-rc.1')):
            self.reject(lambda f: f.final_run.update({field: value}), 'final_runs')
        with IntegrationTLS() as f:
            for field, value in (('event', 'workflow_dispatch'), ('run_attempt', 2), ('ref', 'refs/heads/main')):
                with self.assertRaises(ValueError): replace(f.subject.runs[0], **{field: value})

    def test_fixed_active_final_workflow_blob_and_path_required(self):
        for field, value in (('id', 999), ('path', '.github/workflows/foreign.yml'), ('state', 'disabled_manually')):
            self.reject(lambda f: f.data[f.final_workflow].update({field: value}), 'final_workflow')
        for field, value in (('mode', '100755'), ('type', 'tree'), ('path', 'wrong.yml'), ('sha', 'f'*40)):
            self.reject(lambda f: f.data[f.sources[-1]]['tree'][1].update({field: value}))
        self.reject(lambda f: f.data[f.sources[-1]]['tree'].pop())
        self.reject(lambda f: f.data[f.sources[-1]].update(truncated=True))

    def test_exact_selected_final_run_attempt_job_ids_required(self):
        for field, value in (('id', 999), ('run_attempt', 2), ('workflow_id', 999), ('head_sha', 'f'*40)):
            self.reject(lambda f: f.final_run.update({field: value}), 'final_runs')
        self.reject(lambda f: f.final_jobs[0].update(id=999), 'final_job_path')

    def test_thirteen_job_inventory_status_and_times_reject(self):
        for field, value in (('name', 'foreign'), ('status', 'queued'), ('conclusion', 'skipped'),
                ('run_id', 999), ('run_attempt', 2), ('head_sha', 'f'*40),
                ('started_at', '2026-10-01T00:00:00Z'), ('completed_at', '2026-10-01T00:11:00Z')):
            self.reject(lambda f: f.final_jobs[0].update({field: value}), 'final_job_path')
        self.reject(lambda f: f.final_jobs[0].update(name=f.final_jobs[1]['name']), 'final_job_path')
        self.reject(lambda f: f.final_jobs[0].update(id=f.final_jobs[1]['id']), 'final_job_path')
        self.reject(lambda f: f.final_jobs.pop(), 'final_job_path')
        self.reject(lambda f: f.final_jobs.append(dict(f.final_jobs[0], id=999)), 'final_job_path')

    def test_newer_unsuccessful_final_never_falls_back(self):
        for status, conclusion in (('queued', None), ('in_progress', None), ('completed', 'failure'),
                                   ('completed', 'cancelled'), ('completed', 'skipped')):
            def change(f):
                newer = dict(f.final_run, id=99, status=status, conclusion=conclusion)
                f.data[f.final_runs] = dict(total_count=2, workflow_runs=[f.final_run, newer])
                f.data['/actions/runs/99'] = newer
            self.reject(change, 'final_runs')

    def test_complete_paginated_final_selection(self):
        with IntegrationTLS() as f:
            invocation = replace(f.subject.runs[0], run_id=1001)
            f.subject = replace(f.subject, runs=(invocation, *f.subject.runs[1:]))
            f.final_run['id'] = 1001
            for job in f.final_jobs: job['run_id'] = 1001
            for field, suffix in (('final_current', ''), ('final_attempt', '/attempts/1'),
                                 ('final_job_path', '/attempts/1/jobs?per_page=100&page=1')):
                old, new = getattr(f, field), '/actions/runs/1001'+suffix
                f.data[new] = f.data.pop(old); setattr(f, field, new)
            f.data[f.final_runs] = dict(total_count=101, workflow_runs=[dict(f.final_run, id=n) for n in range(101, 201)])
            f.data[f.final_runs[:-1]+'2'] = dict(total_count=101, workflow_runs=[f.final_run])
            seal_final(f)
            self.observe(f)
            self.assertEqual(f.counts[f.final_runs[:-1]+'2'], 3)

    def test_malformed_duplicate_truncated_and_capped_lists_reject(self):
        for count, rows in ((2, 1), (0, 1), (True, 1), (1001, 1), (2, 2)):
            self.reject(lambda f: f.data.update({f.final_runs: dict(total_count=count, workflow_runs=[f.final_run]*rows)}), 'final_runs')
        def capped(f):
            for page in range(1, 11):
                f.data[f.final_runs[:-1]+str(page)] = dict(total_count=1000,
                    workflow_runs=[dict(f.final_run, id=100+(page-1)*100+n) for n in range(100)])
        self.reject(capped, 'final_runs')
        def drift(f):
            f.data[f.final_runs] = dict(total_count=101, workflow_runs=[dict(f.final_run, id=n) for n in range(101, 201)])
            f.data[f.final_runs[:-1]+'2'] = dict(total_count=102, workflow_runs=[f.final_run])
        self.reject(drift, 'final_runs')

    def test_current_and_attempt_drift_reject(self):
        for target in ('final_current', 'final_attempt'):
            for occurrence in ((2, 5) if target == 'final_current' else (2,)):
                for field, value in (('run_attempt', 2), ('event', 'workflow_dispatch'), ('updated_at', '2026-10-01T00:11:00Z')):
                    def change(f):
                        f.hook = lambda p, n, row: row.update({field: value}) if p == getattr(f, target) and n == occurrence else None
                    self.reject(change, target)

    def test_final_job_fields_drift_reject(self):
        for field, value in (('id', 999), ('name', 'foreign'), ('conclusion', 'failure'),
                             ('completed_at', '2026-10-01T00:08:00Z')):
            def change(f):
                f.hook = lambda p, n, row: row['jobs'][0].update({field: value}) if p == f.final_job_path and n == 2 else None
            self.reject(change, 'final_job_path')

    def test_final_source_ref_workflow_reobserve_drift_reject(self):
        for index in range(6):
            for occurrence in (3, 4):
                def change(f):
                    def hook(path, count, row):
                        if path == f.final_sources[index] and count == occurrence:
                            if index == 0: row['id'] = 999
                            elif index == 1: row['object']['sha'] = 'f'*40
                            else: row['sha'] = 'f'*40
                    f.hook = hook
                self.reject(change)
        self.reject(lambda f: setattr(f, 'hook', lambda p, n, r: r.update(state='disabled_manually')
            if p == f.final_workflow and n == 2 else None), 'final_workflow')

    def test_late_newer_final_blocks_each_closing_pass(self):
        for occurrence in (2, 3):
            def change(f):
                f.data['/actions/runs/999'] = dict(f.final_run, id=999, conclusion='failure')
                f.hook = lambda p, n, row: row.update(total_count=2, workflow_runs=[f.final_run,
                    f.data['/actions/runs/999']]) if p == f.final_runs and n == occurrence else None
            self.reject(change, 'final_runs')

    def test_integration_changes_during_final_are_rejected(self):
        for occurrence in (1, 2):
            with IntegrationTLS() as f:
                f.hook = lambda p, n, row: f.run.update(conclusion='failure') if p == f.final_job_path and n == occurrence else None
                self.blocked(f)
                self.assertEqual(f.counts[f.runs], occurrence+1)

    def test_final_metadata_denial_absence_redirect_and_nonjson_reject(self):
        for endpoint in ('final_workflow', 'final_runs', 'final_current', 'final_attempt', 'final_job_path'):
            for status in (401, 403, 404, 302, 500):
                self.reject(lambda f: f.routes.update({('GET', wire.ROOT+getattr(f, endpoint)):
                    (status, {'Location': 'https://foreign.invalid/private'}, b'secret-token')}))
        self.reject(lambda f: f.routes.update({('GET', wire.ROOT+f.final_workflow): (200, {}, b'<html>private</html>')}))

    def test_final_metadata_duplicate_and_bounds_reject(self):
        for raw in (b'{"id":1,"id":2}', b'{"value":NaN}', b'['*40+b']'*40, b' '*(wire.METADATA+1)):
            self.reject(lambda f: f.routes.update({('GET', wire.ROOT+f.final_workflow): (200, {}, raw)}))

    def test_cancellation_entering_and_during_final_returns_no_report(self):
        for endpoint in ('source', 'final_workflow', 'final_job_path'):
            with IntegrationTLS() as f:
                cancelled = []
                f.hook = lambda p, n, row: cancelled.append(True) if p == (f.sources[-1] if endpoint == 'source' else getattr(f, endpoint)) else None
                def active():
                    if cancelled: raise wire.WireFailure('cancelled', 'none')
                self.blocked(f, 'cancelled', active)
                self.assertEqual(len(f.requests), {'source': 6, 'final_workflow': 19, 'final_job_path': 22}[endpoint])

    def test_caller_deadline_covers_both_gates(self):
        with IntegrationTLS() as f:
            start, elapsed = time.monotonic(), [0]
            f.hook = lambda p, n, row: elapsed.__setitem__(0, elapsed[0]+1)
            with patch.object(admission, 'time', SimpleNamespace(monotonic=lambda: start+elapsed[0])):
                self.blocked(f, 'timeout', deadline=start+24)
            self.assertEqual(len(f.requests), 24)
            self.assertEqual(f.counts[f.final_attempt], 1)
        for deadline in (0, float('nan'), float('inf'), True):
            with IntegrationTLS() as f:
                self.blocked(f, 'timeout' if deadline == 0 else 'verification_failed', deadline=deadline)
                self.assertEqual(f.requests, [])

    def test_internal_deadline_is_clamped_once(self):
        with IntegrationTLS() as f:
            start, elapsed, deadlines = time.monotonic(), [0], []
            original = wire.GitHub.get
            def recorded(api, path, **options):
                deadlines.append(options['deadline'])
                return original(api, path, **options)
            f.hook = lambda p, n, row: elapsed.__setitem__(0, elapsed[0]+6)
            with patch.object(admission, 'time', SimpleNamespace(monotonic=lambda: start+elapsed[0])), patch.object(wire.GitHub, 'get', recorded):
                self.blocked(f, 'timeout', deadline=start+1000)
            self.assertEqual(len(f.requests), 50)
            self.assertEqual(set(deadlines), {start+300})
            self.assertEqual(f.counts[f.final_runs], 3)

    def test_entry_and_direct_sinks_remain_effect_free(self):
        from rc_publication_native_admission_fixture import _pending_fence
        production_authenticate = wire._authenticate
        import rc_publication_artifact_admission as artifacts
        with IntegrationTLS() as f, tempfile.TemporaryDirectory() as root, patch.object(artifacts, 'stage_selected',
                side_effect=wire.WireFailure('fence_blocked', 'none')) as stage:
            with executor.PublisherSession(root, f.selection, 'fixture-token', temporary_parent=root) as session:
                with self.assertRaises(wire.WireFailure) as error: session.run_until_pause()
                self.assertEqual((error.exception.code, session.outcome), ('fence_blocked', 'blocked_no_effect'))
                self.assertIsNone(session.transition); stage.assert_called_once()
            self.assertEqual([r[1] for r in f.requests], f.packaging_paths)
            operations = (core.Operation('CreateDraft', 2, 'a'*64, tag=f.subject.tag, draft=True, prerelease=True),
                core.Operation('UploadAsset', 5, 'a'*64, release_id=100, asset_ordinal=0, asset=f.plan.assets[0]),
                core.Operation('PublishPrerelease', 24, 'a'*64, release_id=100, request_id='once', draft=False, prerelease=True))
            for operation in operations:
                before = len(f.requests)
                with patch.object(wire, '_authorize') as authorize, self.assertRaises(wire.WireFailure) as error:
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

    def test_legacy_integration_negative_endpoints_are_reached(self):
        for endpoint in ('workflow', 'runs', 'current', 'attempt', 'job_path'):
            with IntegrationTLS() as f:
                mutated = []
                def hook(path, count, row):
                    if path == getattr(f, endpoint):
                        mutated.append(path)
                        return 403, {}, b'private integration denial'
                f.hook = hook
                self.blocked(f)
                self.assertEqual(mutated, [getattr(f, endpoint)])
                self.assertEqual(f.counts[f.final_sources[-1]], 2)
                self.assertEqual(f.counts[f.final_workflow], 0)
        for endpoint in ('workflow', 'runs', 'current', 'attempt', 'job_path'):
            with IntegrationTLS() as f:
                consumed = []
                def hook(path, count, row):
                    if path == getattr(f, endpoint) and count == 2:
                        consumed.append(path)
                        return 403, {}, b'late integration denial'
                f.hook = hook
                self.blocked(f)
                self.assertEqual(consumed, [getattr(f, endpoint)])

    def test_fresh_reobservation_and_caller_claims_confer_no_authority(self):
        import rc_publication_artifact_admission as artifacts
        from rc_pretag_fixtures import candidate, passing_claims
        from rc_release_eligibility import evaluate
        result = evaluate(candidate(), passing_claims())
        self.assertEqual((result.status, result.evidence_authentication), ('blocked', 'unverified'))
        self.assertTrue(all(r.status != 'passed' for r in result.rows))
        with IntegrationTLS() as f:
            f.api.get = lambda *a, **k: self.fail('caller GET invoked')
            report = self.observe(f)
            self.assertEqual(f.counts[f.final_runs], 3)
            f.final_run['conclusion'] = 'failure'
            self.blocked(f)
            self.assertEqual(f.counts[f.final_runs], 4)
            self.assertFalse(hasattr(f.api, '_admission'))
            options = dict(check_active=lambda: None, deadline=time.monotonic()+30)
            for extra in ({'approved': True}, {'roles': ('final_packaging',)}, {'report': report}):
                with self.assertRaises(TypeError): admission.authenticate_packaging(f.api, f.selection, **extra, **options)
            class Foreign(wire.GitHub): pass
            canonical, owners = f.api.selection, tuple(artifacts._OWNERS)
            before_foreign = len(f.requests)
            with self.assertRaises(wire.WireFailure) as error:
                admission.authenticate_packaging(Foreign('fixture-token', f.selection), f.selection, **options)
            self.assertIs(type(error.exception), wire.WireFailure)
            self.assertEqual((error.exception.code, error.exception.effect), ('invalid_request', 'none'))
            self.assertEqual(len(f.requests), before_foreign)
            self.assertIsNone(f.api._credential._session_owner)
            self.assertEqual(tuple(artifacts._OWNERS), owners)
            before = len(f.requests)
            f.selection = report
            self.blocked(f)
            self.assertEqual(len(f.requests), before)
            self.assertIs(f.api.selection, canonical)
            self.assertEqual(tuple(artifacts._OWNERS), owners)

    def test_distinct_supported_integration_ref_and_final_branch(self):
        for ref, event in (('refs/heads/ci/integration', 'push'), ('refs/tags/v0.7.0-rc.1', 'workflow_dispatch')):
            with IntegrationTLS() as f:
                invocation = replace(f.subject.runs[1], ref=ref, event=event,
                    workflow_ref=wire.REPOSITORY+'/'+f.subject.runs[1].workflow_path+'@'+ref)
                f.subject = replace(f.subject, runs=(f.subject.runs[0], invocation, f.subject.runs[2]))
                f.run.update(event=event, head_branch=ref.split('/', 2)[2])
                f.sources[1] = '/git/ref/'+ref[5:]
                f.data[f.sources[1]] = dict(ref=ref, object=dict(type='commit', sha=f.subject.source.source_sha))
                f.seal()
                report = self.observe(f)
                self.assertEqual(report.integration_evidence_sha256, f.reference_digest())
                self.assertEqual(report.final_evidence_sha256, final_digest(f))
                self.assertEqual(f.counts[f.sources[1]], 2)
                self.assertEqual(f.counts[f.final_sources[1]], 2)


if __name__ == '__main__':
    unittest.main()
