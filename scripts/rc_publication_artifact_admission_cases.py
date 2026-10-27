"""Verified TLS and real synthetic FINAL validators; no release approval."""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, FrozenInstanceError, replace
import hashlib
import io
import json
import os
from pathlib import Path
import time
import unittest
from unittest.mock import patch

import rc_artifact_consumer as consumer
from rc_consumer_fixtures import write_json
from rc_consumer_io import ConsumerError
from rc_consumer_plan_tests import zip_bytes
import rc_publication_admission as metadata
import rc_publication_artifact_admission as artifacts
import rc_publication_contract as core
import rc_publication_executor as executor
import rc_publication_github as wire
from rc_publication_https_fixture import HTTPSFixture
from rc_publication_stage_cases import publisher_fixture, artifact_route, artifact_worker, git
from rc_release_policy import GATE_IDS


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=True, allow_nan=False).encode('utf-8')).hexdigest()


def reference_artifacts(f):
    s, selected = f.selection.subject, f.selection
    binding = dict(source=asdict(s.source), tag=s.tag, tag_object_sha=s.tag_object_sha,
        runs=[asdict(r) for r in s.runs], job_ids=s.job_ids,
        final_artifact=dict(id=s.artifact_id, size=s.artifact_size, sha256=s.artifact_sha256),
        consumer_artifact=dict(id=selected.consumer_artifact_id, size=selected.consumer_artifact_size,
                               sha256=selected.consumer_artifact_sha256),
        plan_sha256=s.plan_sha256, provenance_sha256=hashlib.sha256(f.provenance_bytes).hexdigest(),
        assets=[asdict(a) for a in f.plan.assets])
    p = json.loads(f.provenance_bytes)
    return tuple(digest(dict(schema='rc-owned-final-artifact-v1', gate_id=key, binding=binding, evidence=value))
        for key, value in (('bundle_bytes', p), ('raw_cloud_audit', p['audits']['cloud']),
                           ('raw_noncloud_audits', p['audits']['noncloud'])))


def reseal_artifact_client(f, api, selection):
    """Replace only a transport client held by this trusted test fixture."""
    clients = f.fixture_clients
    if type(api) is not wire.GitHub or f.selection is not api.selection \
            or type(clients) is not list or not any(client is api for client in clients):
        raise AssertionError('artifact fixture reseal requires its actual client')
    current = wire.GitHub('fixture-token', selection)
    clients.append(current)
    api.close()
    f.selection = current.selection
    return current


class ArtifactTLS(HTTPSFixture):
    def __init__(self, f):
        s = f.selection.subject
        github = git(f.root, 'rev-parse', s.source.source_sha + ':.github')
        workflows = git(f.root, 'rev-parse', s.source.source_sha + ':.github/workflows')
        f.api.data['/git/commits/' + s.source.source_sha] = dict(sha=s.source.source_sha,
                                                             tree=dict(sha=s.source.source_tree))
        for tree in (s.source.source_tree, github, workflows):
            rows = []
            for line in git(f.root, 'ls-tree', tree).splitlines():
                info, name = line.split('\t')
                mode, kind, sha = info.split()
                rows.append(dict(path=name, mode=mode, type=kind, sha=sha))
            f.api.data['/git/trees/' + tree] = dict(sha=tree, truncated=False, tree=rows)
        values = list(s.gate_evidence)
        for index, key in ((0, 'final_packaging'), (1, 'full_integration')):
            invocation = s.runs[index]
            f.api.data['/git/ref/' + invocation.ref[5:]] = dict(ref=invocation.ref,
                object=dict(type='commit', sha=s.source.source_sha))
            workflow = f.api.data['/actions/workflows/' + Path(invocation.workflow_path).name]
            workflow['state'] = 'active'
            run = deepcopy(f.api.data[f'/actions/runs/{invocation.run_id}'])
            jobs = deepcopy(f.api.data[f'/actions/runs/{invocation.run_id}/attempts/{invocation.run_attempt}/jobs?per_page=100&page=1']['jobs'])
            observation = dict(repository=dict(id=s.source.repository_id, full_name=s.source.repository),
                ref=dict(ref=invocation.ref, object=dict(type='commit', sha=s.source.source_sha)),
                commit=dict(sha=s.source.source_sha, tree=s.source.source_tree),
                trees=[s.source.source_tree, github, workflows],
                workflow=dict(path=invocation.workflow_path, mode='100644', sha=invocation.workflow_blob))
            values[GATE_IDS.index(key)] = digest(dict(schema='rc-final-packaging-v1' if index == 0 else 'rc-full-integration-v1',
                gate_id=key, source=asdict(s.source), invocation=asdict(invocation), source_observation=observation,
                evidence=dict(workflow=dict(id=invocation.workflow_id, path=invocation.workflow_path),
                              run=run, jobs=sorted(jobs, key=lambda j: j['id']))))
        for key, value in zip(artifacts.ARTIFACT_GATES, reference_artifacts(f)):
            values[GATE_IDS.index(key)] = value
        f.selection = replace(f.selection, subject=replace(s, gate_evidence=tuple(values)))
        self.f = f
        super().__init__(subject=f.selection.subject, plan=f.plan, payloads=f.payloads)
        self.selection = f.selection
        self.route = lambda *args: artifact_route(f, *args)


class ArtifactAdmissionCases(unittest.TestCase):
    @contextmanager
    def fixture(self):
        with publisher_fixture() as f, ArtifactTLS(f) as tls, patch.object(wire, '_connect', side_effect=tls.connect), \
                artifact_worker(f, tls):
            api = wire.GitHub('fixture-token', f.selection)
            # f.api remains the BudgetAPI data model; transport identity is
            # owned by this unchanged actual client in the third tuple slot.
            f.selection = api.selection
            f.fixture_clients = [api]
            try:
                yield f, tls, api
            finally:
                for client in reversed(f.fixture_clients):
                    client.close()
            self.assertEqual(tls.errors, [])
            self.assertTrue(all(r[0] == 'GET' and not r[3] for r in tls.requests))

    @contextmanager
    def owner(self, f, api):
        owner = artifacts._ArtifactOwner(f.root, f.selection, api, temporary_parent=f.parent)
        try:
            owner.enter(deadline=time.monotonic()+60, check_active=lambda: None)
            yield owner
        finally:
            owner.close()
            owner.stage.close()

    def blocked(self, f, api, *, code='fence_blocked', active=lambda: None, deadline=None):
        with self.assertRaises(wire.WireFailure) as error:
            wire._authenticate(f.selection, api, deadline=time.monotonic()+60 if deadline is None else deadline,
                               check_active=active)
        self.assertEqual((error.exception.code, error.exception.effect), (code, 'none'))

    def test_real_preparation_stages_and_authenticates_exact_five_rows(self):
        with self.fixture() as (f, tls, api), self.owner(f, api) as owner:
            self.blocked(f, api)
            report = owner._report
            self.assertEqual([r[0] for r in report.rows if r[3] == 'passed'],
                ['raw_cloud_audit', 'raw_noncloud_audits', 'full_integration', 'final_packaging', 'bundle_bytes'])
            self.assertEqual(report.artifact_digests, reference_artifacts(f))
            self.assertEqual((report.status, report.draft_visibility, report.evidence_authentication),
                             ('blocked', 'unknown', 'partial'))
            self.assertFalse(report.release_approved or report.publish_approved or report.snapshot_atomic)
            with self.assertRaises(FrozenInstanceError): report.artifact_digests = ('0'*64,)*3
            self.assertTrue(any('/actions/artifacts/13/zip' in r[1] for r in tls.requests))

    def test_session_stages_before_full_gate_block_and_retires_all_owners(self):
        with self.fixture() as (f, tls, _):
            session = executor.PublisherSession(f.root, f.selection, 'fixture-token', temporary_parent=f.parent)
            captured, original = [], artifacts._ArtifactOwner.authenticate
            def observe(owner, *args, **kwargs):
                value = original(owner, *args, **kwargs)
                captured.append((owner, value, tuple(owner.stage._handles)))
                return value
            with patch.object(artifacts._ArtifactOwner, 'authenticate', observe), self.assertRaises(wire.WireFailure) as error:
                session.run_until_pause()
            self.assertEqual((error.exception.code, error.exception.effect, session.outcome),
                             ('fence_blocked', 'none', 'blocked_no_effect'))
            self.assertIsNone(session.transition)
            self.assertEqual(len(captured), 1)
            owner, _, handles = captured[0]
            self.assertTrue(owner.closed and all(h.closed for h in handles))
            self.assertNotIn(owner.api, artifacts._OWNERS)
            self.assertEqual(list(Path(f.parent).glob('rc-publisher-*')), [])
            session.close()

    def test_read_only_preparation_never_authenticates_artifact_rows(self):
        with self.fixture() as (f, tls, api):
            report = wire._prepare_admission(f.selection, api, deadline=time.monotonic()+60, check_active=lambda: None)
            self.assertEqual([r[0] for r in report.rows if r[3] == 'passed'], ['full_integration', 'final_packaging'])
            self.assertFalse(any(r[1].endswith('/zip') for r in tls.requests))
            self.blocked(f, api)

    def test_caller_report_owner_attribute_and_flags_cannot_import_authority(self):
        with self.fixture() as (f, _, api):
            forged = artifacts._ArtifactReport(metadata._PackagingReport(f.selection.subject,
                f.selection.subject.gate_evidence[GATE_IDS.index('full_integration')],
                f.selection.subject.gate_evidence[GATE_IDS.index('final_packaging')]), reference_artifacts(f))
            api._artifact_owner = forged
            self.blocked(f, api)
            with self.assertRaises(TypeError):
                artifacts._ArtifactOwner(f.root, f.selection, api, temporary_parent=f.parent, report=forged)
            with self.assertRaises(TypeError):
                wire._authenticate(f.selection, api, deadline=time.monotonic()+60, check_active=lambda: None, approved=True)

    def test_foreign_and_closed_owner_are_unavailable(self):
        with self.fixture() as (f, tls, api), self.owner(f, api) as owner:
            foreign = wire.GitHub('fixture-token', f.selection)
            try:
                before = len(tls.requests)
                self.blocked(f, foreign, code='verification_failed')
                self.assertEqual(len(tls.requests), before)
                with self.assertRaises(wire.WireFailure) as error:
                    wire._authenticate(foreign.selection, foreign, deadline=time.monotonic()+60, check_active=lambda: None)
                self.assertEqual((error.exception.code, error.exception.effect), ('fence_blocked', 'none'))
                self.assertEqual(len(tls.requests)-before, 52)
                self.assertNotIn(foreign, artifacts._OWNERS)
                self.assertIsNone(foreign._credential._session_owner)
                self.assertIs(artifacts._OWNERS.get(api), owner)
            finally: foreign.close()
            owner.close()
            self.blocked(f, api)
            with self.assertRaisesRegex(ConsumerError, '^artifact_owner_closed$'):
                owner.adapter.budget(time.monotonic()+60, lambda: None)
            with self.assertRaisesRegex(ConsumerError, '^artifact_owner_lifetime$'):
                owner.enter(deadline=time.monotonic()+60, check_active=lambda: None)

    def test_fixed_reads_ignore_get_override_and_reject_transport_shadows(self):
        with self.fixture() as (f, _, api):
            api.get = lambda *a, **kw: self.fail('instance GET invoked')
            with self.owner(f, api): self.blocked(f, api)
            for name in ('_metadata', '_request', '_closed_request'):
                setattr(api, name, lambda *a, **kw: self.fail('instance transport invoked'))
                try: self.blocked(f, api, code='verification_failed')
                finally: delattr(api, name)

    def test_metadata_failure_prevents_any_artifact_staging(self):
        with self.fixture() as (f, tls, api):
            f.api.data['/actions/runs/123']['conclusion'] = 'failure'
            owner = artifacts._ArtifactOwner(f.root, f.selection, api, temporary_parent=f.parent)
            try:
                with patch.object(consumer, '_verify_bundle_bytes', wraps=consumer._verify_bundle_bytes) as parsed:
                    with self.assertRaises(wire.WireFailure):
                        owner.enter(deadline=time.monotonic()+60, check_active=lambda: None)
                    parsed.assert_not_called()
                self.assertNotIn(api, artifacts._OWNERS)
                self.assertFalse(any(r[1].endswith('/zip') for r in tls.requests))
            finally: owner.close(); owner.stage.close()

    def test_all_three_frozen_artifact_digest_mismatches_block(self):
        for key in artifacts.ARTIFACT_GATES:
            with self.subTest(gate=key), self.fixture() as (f, _, api):
                values = list(f.selection.subject.gate_evidence); values[GATE_IDS.index(key)] = '0'*64
                api = reseal_artifact_client(f, api, replace(f.selection,
                    subject=replace(f.selection.subject, gate_evidence=tuple(values))))
                with self.owner(f, api) as owner:
                    self.blocked(f, api, code='verification_failed')
                    self.assertIsNone(owner._report)

    def test_original_plan_and_provenance_copies_cannot_drift(self):
        for field in ('plan_bytes', 'provenance_bytes'):
            with self.subTest(field=field), self.fixture() as (f, _, api), self.owner(f, api) as owner:
                original = getattr(owner.stage, field)
                setattr(owner.stage, field, original + b' ')
                self.blocked(f, api, code='verification_failed')
                self.assertIsNone(owner._report)

    def test_retained_asset_and_selected_metadata_drift_block(self):
        for mode in ('bytes', 'metadata'):
            with self.subTest(mode=mode), self.fixture() as (f, _, api), self.owner(f, api) as owner:
                if mode == 'bytes':
                    path = owner.stage._output.path / owner.stage.plan.assets[0].name
                    raw = path.read_bytes(); path.write_bytes(bytes([raw[0]^1])+raw[1:])
                else: f.api.data['/actions/artifacts/13']['expired'] = True
                self.blocked(f, api, code='verification_failed')
                self.assertIsNone(owner._report)

    def test_corrupt_final_archive_never_registers_owner(self):
        with self.fixture() as (f, _, api):
            f.archives[13] = f.archives[13][:-1] + b'X'
            owner = artifacts._ArtifactOwner(f.root, f.selection, api, temporary_parent=f.parent)
            try:
                with self.assertRaisesRegex(ConsumerError, '^download_digest_mismatch$'):
                    owner.enter(deadline=time.monotonic()+60, check_active=lambda: None)
                self.assertNotIn(api, artifacts._OWNERS)
            finally: owner.close(); owner.stage.close()

    def test_raw_npm_rustsec_glib_and_installed_contract_failures_stay_failures(self):
        expected = dict(npm=('invalid_npm_zero_audit', (1, 0, 0)),
            cloud_active=('active_vulnerable_package', (1, 0, 0)),
            noncloud_active=('active_or_unproven_raw_vulnerability', (1, 1, 0)),
            glib_scope=('desktop_source_proof_scope_mismatch', (1, 1, 0)),
            installed=('invalid_windows_acceptance_boundary', (1, 1, 1)))
        for mode, (code, counts) in expected.items():
            with self.subTest(mode=mode), self.fixture() as (f, _, api):
                contracts = f.source.contracts
                if mode == 'npm': write_json(contracts / 'npm-audit.json', dict(metadata=dict(vulnerabilities=dict(total=True))))
                elif mode == 'cloud_active':
                    raw = f.source.f.audit['vulnerabilities']['list'][0]
                    raw['package'] = deepcopy(f.source.f.lock['package'][1])
                    f.source.sign_cloud()
                elif mode == 'noncloud_active':
                    capture = json.loads((contracts / 'raw-audit-capture.json').read_text())
                    path = contracts / 'rust-audit-local-agent.json'
                    value = json.loads(path.read_text())
                    value['vulnerabilities'] = dict(found=True, count=1, list=[dict(advisory=dict(id='RUSTSEC-2099-9999'))])
                    write_json(path, value)
                    capture['reports']['local-agent']['raw_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
                    write_json(contracts / 'raw-audit-capture.json', capture)
                elif mode == 'glib_scope':
                    capture = json.loads((contracts / 'raw-audit-capture.json').read_text())
                    capture['desktop_glib_source_proof_required'] = True
                    write_json(contracts / 'raw-audit-capture.json', capture)
                    for name in ('metadata.json', 'upstream-identity-raw-audit.json', 'product-raw-audit.json'):
                        write_json(contracts / 'desktop-glib' / name, dict(lockfile={'dependency-count': 1}))
                else:
                    path = f.source.bundle / 'evidence/rc-windows-package/rc-windows-package.json'
                    value = json.loads(path.read_text()); value['silent_install'] = False; write_json(path, value)
                f.source.refresh_inventory()
                changed = zip_bytes(f.source.bundle); f.archives[13] = changed
                record = f.api.data['/actions/artifacts/13']
                record.update(size_in_bytes=len(changed), digest='sha256:'+hashlib.sha256(changed).hexdigest())
                api = reseal_artifact_client(f, api, replace(f.selection, subject=replace(f.selection.subject,
                    artifact_size=len(changed), artifact_sha256=hashlib.sha256(changed).hexdigest())))
                owner = artifacts._ArtifactOwner(f.root, f.selection, api, temporary_parent=f.parent)
                try:
                    with patch.object(consumer.contracts, 'verify_consumed_bundle', wraps=consumer.contracts.verify_consumed_bundle) as validator, \
                            patch.object(consumer.contracts, 'verify_consumed_cloud', wraps=consumer.contracts.verify_consumed_cloud) as cloud, \
                            patch.object(consumer.contracts, 'verify_consumed_noncloud_audits', wraps=consumer.contracts.verify_consumed_noncloud_audits) as noncloud, \
                            patch.object(consumer.contracts, 'verify_consumed_installers', wraps=consumer.contracts.verify_consumed_installers) as installers:
                        with self.assertRaisesRegex(ValueError, '^'+code+'$'):
                            owner.enter(deadline=time.monotonic()+60, check_active=lambda: None)
                        self.assertEqual(validator.call_count, 1)
                        self.assertEqual((cloud.call_count, noncloud.call_count, installers.call_count), counts)
                    self.assertNotIn(api, artifacts._OWNERS)
                finally: owner.close(); owner.stage.close()

    def test_raw_findings_producer_assertions_and_blockers_remain_visible(self):
        with self.fixture() as (f, _, api), self.owner(f, api) as owner:
            self.blocked(f, api)
            p = json.loads(owner.stage.provenance_bytes)
            self.assertEqual((p['audits']['cloud']['raw_vulnerability_count'], p['audits']['cloud']['active_vulnerability_count']), (1, 0))
            self.assertEqual(p['audits']['npm_vulnerability_count'], 0)
            self.assertFalse(p['audits']['raw_zero_claim'])
            self.assertEqual(len(p['installed_platforms']), 5)
            self.assertTrue(all(r['observations'] == 'authenticated_producer_assertions' for r in p['installed_platforms']))
            self.assertEqual(p['release_blockers'], list(consumer.contracts.BLOCKERS))
            for key in ('snapshot_root_authority', 'windows_isolation', 'installed_five_rows', 'npm_audit', 'rust_audit', 'structural_blocker_resolution'):
                self.assertEqual(next(r[3] for r in owner._report.rows if r[0] == key), 'unknown')

    def test_budget_controls_during_final_owned_read_preserve_codes(self):
        for cancelled in (False, True):
            with self.subTest(cancelled=cancelled), self.fixture() as (f, _, api), self.owner(f, api) as owner:
                stream = owner.stage._handles[4]
                original = stream.read
                revalidate, armed = artifacts.StagedAssets.revalidate, [False]
                controls = dict(deadline=time.monotonic()+60, active=lambda: None)
                def read(size):
                    data = original(size)
                    if armed[0]:
                        if cancelled: controls['active'] = lambda: (_ for _ in ()).throw(wire.WireFailure('cancelled', 'none'))
                        else: controls['deadline'] = 0
                    return data
                def validated(stage, **kwargs):
                    value = revalidate(stage, **kwargs)
                    armed[0] = True
                    return value
                def active():
                    controls['active']()
                    if controls['deadline'] == 0: raise wire.WireFailure('timeout', 'none')
                with patch.object(artifacts.StagedAssets, 'revalidate', validated), patch.object(stream, 'read', side_effect=read):
                    self.blocked(f, api, code='cancelled' if cancelled else 'timeout', active=active)
                self.assertTrue(armed[0])
                self.assertEqual(stream.tell(), 0)
                self.assertIsNone(owner._report)

    def test_new_reads_use_one_budget_and_expired_preparation_has_no_get(self):
        with self.fixture() as (f, tls, api):
            before = len(tls.requests)
            self.blocked(f, api, code='timeout', deadline=0)
            self.assertEqual(len(tls.requests), before)
            calls, original = [], wire.GitHub.get
            def recorded(current, path, **kwargs):
                calls.append(kwargs['deadline']); return original(current, path, **kwargs)
            end = time.monotonic()+60
            owner = artifacts._ArtifactOwner(f.root, f.selection, api, temporary_parent=f.parent)
            try:
                with patch.object(wire.GitHub, 'get', recorded):
                    owner.enter(deadline=end, check_active=lambda: None)
                    self.blocked(f, api, deadline=end)
                self.assertTrue(calls); self.assertEqual(set(calls), {end})
            finally: owner.close(); owner.stage.close()

    def test_remote_owner_and_latest_absence_constraints_remain_hard_rejects(self):
        from rc_publication_native_admission_fixture import _authorizer_denial
        production_authorize = wire._authorize
        with self.fixture() as (f, _, api), self.owner(f, api):
            for fn, args, code in ((wire._remote_constraint, (f.selection.subject,), 'fence_blocked'),
                    (wire._authenticated_latest_absence, (f.selection,), 'fence_blocked')):
                with self.assertRaises(wire.WireFailure) as error: fn(*args)
                self.assertEqual((error.exception.code, error.exception.effect), (code, 'none'))
        _authorizer_denial(self, production_authorize)

    def test_owned_direct_mutation_sinks_still_block_before_authorize_and_write(self):
        from rc_publication_native_admission_fixture import _pending_fence
        production_authenticate = wire._authenticate
        with self.fixture() as (f, tls, api), self.owner(f, api):
            operations = (core.Operation('CreateDraft', 2, 'a'*64, tag=f.selection.subject.tag, draft=True, prerelease=True),
                core.Operation('UploadAsset', 5, 'a'*64, release_id=100, asset_ordinal=0, asset=f.plan.assets[0]),
                core.Operation('PublishPrerelease', 24, 'a'*64, release_id=100, request_id='once', draft=False, prerelease=True))
            for op in operations:
                before = len(tls.requests)
                options = dict(before_write=lambda: self.fail('mutation write attempted'), check_active=lambda: None)
                with patch.object(wire, '_authorize') as authorize, self.assertRaises(wire.WireFailure) as error:
                    if op.kind == 'CreateDraft': api.create_draft(op, **options)
                    elif op.kind == 'UploadAsset': api.upload_asset(op, io.BytesIO(f.payloads[op.asset.name]), **options)
                    else: api.publish_prerelease(op, **options)
                self.assertEqual((error.exception.code, error.exception.effect), ('invalid_request', 'none'))
                authorize.assert_not_called()
                self.assertEqual(len(tls.requests), before)
        for kind in ('CreateDraft', 'UploadAsset', 'PublishPrerelease'):
            _pending_fence(self, kind, production_authenticate)

    def test_stage_adapter_real_tls_midread_cancel_and_timeout_preserve_codes(self):
        for cancelled in (False, True):
            with self.subTest(cancelled=cancelled), self.fixture() as (f, tls, api):
                adapter, interrupted, entered = artifacts._StageAPI(api, f.selection), [False], []
                def active():
                    if interrupted[0]: raise wire.WireFailure('cancelled', 'none')
                original = tls.route
                def route(method, path, headers, body):
                    if path == wire.ROOT:
                        entered.append(path)
                        if cancelled: interrupted[0] = True
                        else: time.sleep(0.3)
                    return original(method, path, headers, body)
                tls.route = route
                end = time.monotonic() + (60 if cancelled else 0.15)
                adapter.budget(end, active)
                start = time.monotonic()
                with self.assertRaisesRegex(ConsumerError, '^transport_'+('cancelled' if cancelled else 'deadline_exceeded')+'$'):
                    # Caller controls cannot extend a deadline or replace owned cancellation.
                    adapter.get('/', deadline=end+60, check_active=lambda: None)
                self.assertEqual(entered, [wire.ROOT])
                self.assertLess(time.monotonic()-start, 1)
                adapter.closed = True

    def test_entered_owner_cancel_and_expiry_cannot_be_replaced_by_caller(self):
        for cancelled in (True, False):
            with self.subTest(cancelled=cancelled), self.fixture() as (f, tls, api):
                interrupted, end = [False], time.monotonic()+60
                def active():
                    if interrupted[0]: raise wire.WireFailure('cancelled', 'none')
                owner = artifacts._ArtifactOwner(f.root, f.selection, api, temporary_parent=f.parent)
                try:
                    owner.enter(deadline=end, check_active=active)
                    before = len(tls.requests)
                    interrupted[0] = cancelled
                    clock = time.monotonic() if cancelled else end+1
                    with patch('rc_consumer_io.time.monotonic', return_value=clock):
                        for authenticate in (lambda: wire._authenticate(f.selection, api,
                                deadline=end+120, check_active=lambda: None),
                                lambda: artifacts.authenticate_artifacts(api, f.selection,
                                    deadline=end+120, check_active=lambda: None)):
                            with self.assertRaises((wire.WireFailure, ConsumerError)) as error:
                                authenticate()
                            self.assertEqual(error.exception.code,
                                ('cancelled' if cancelled else 'timeout') if isinstance(error.exception, wire.WireFailure)
                                else 'transport_'+('cancelled' if cancelled else 'deadline_exceeded'))
                    self.assertEqual(len(tls.requests), before)
                    self.assertIs(artifacts._OWNERS.get(api), owner)
                finally: owner.close(); owner.stage.close()

    def test_only_bound_session_scope_can_renew_owner_deadline(self):
        from types import SimpleNamespace
        from rc_publication_native_admission_fixture import _native_session
        end, next_phase = time.monotonic()+60, []
        clock = SimpleNamespace(monotonic=lambda: end+(120 if next_phase else 0)-executor.OPERATION_SECONDS)
        def entered(owner, session, tls, trace):
            self.assertIs(owner._session, session)
            scoped, _ = owner._controls(end+240, lambda: None)
            self.assertEqual(scoped, end)
            next_phase.append(True)
        with _native_session(self, clock=clock, after_enter=entered) as (session, tls, _, trace):
            def renewed(current, op):
                owner, _, previous, _ = trace.entered[0]
                self.assertTrue(previous._retired)
                self.assertIsNot(current._read_scope, previous)
                self.assertEqual(current._deadline, end+120)
                before = len(tls.requests)
                scoped, active = owner._controls(end+240, lambda: None)
                self.assertEqual(scoped, session._deadline); self.assertIsNone(active())
                self.assertIs(active, trace.controls[-1][1])
                scoped, active = owner._controls(end-1, lambda: None)
                self.assertEqual(scoped, end-1); self.assertIsNone(active())
                with self.assertRaisesRegex(ConsumerError, '^transport_deadline_exceeded$'):
                    owner._controls(0, lambda: None)
                self.assertEqual(len(tls.requests), before)
                session._cancelled.set()
                with self.assertRaisesRegex(ConsumerError, '^transport_cancelled$'):
                    owner.authenticate(deadline=end+240, check_active=lambda: None)
                self.assertEqual(len(tls.requests), before)
            trace.before_execute = renewed
            result = session.run_until_pause()
            self.assertEqual((result.state.code, result.state.outcome), ('cancelled', 'blocked_no_effect'))


if __name__ == '__main__':
    unittest.main()
