"""Named offline publication decision tests; no fixture is release authority."""
import ast
from dataclasses import FrozenInstanceError, asdict, replace
import hashlib
import inspect
import json
import unittest
from unittest.mock import patch

import rc_publication_contract as p
from rc_consumer_contracts import BLOCKERS
from rc_pretag_types import InvocationIdentity, REPOSITORY, REPOSITORY_ID, SourceIdentity, WORKFLOWS


def fixture():
    source = SourceIdentity(REPOSITORY, REPOSITORY_ID, 'a' * 40, 'b' * 40, '0.7.0-rc.1')
    runs = []
    for index, role in enumerate(('final', 'integration', 'consumer')):
        ref = 'refs/heads/release/full-rc-candidate-fixture'
        runs.append(InvocationIdentity(role, source, 10 + index, 1, 20 + index, WORKFLOWS[role],
            REPOSITORY + '/' + WORKFLOWS[role] + '@' + ref, source.source_sha, 'c' * 40,
            'push' if role != 'consumer' else 'workflow_dispatch', ref))
    fixed = (*p.payloads(source.version), ('RC_PROVENANCE.json', 'provenance', 'application/json'),
             (f'SHA256SUMS_{source.version}.txt', 'checksums', 'text/plain'))
    plan = p.AssetPlanView(tuple(p.Asset(name, family, media, i + 1, str(i + 1) * 64)
                               for i, (name, family, media) in enumerate(fixed)))
    subject = p.PublicationSubject(source, 'v' + source.version, source.source_sha, tuple(runs),
        ((31,), (32,), (33,)), 40, 100, 'd' * 64, 'e' * 64, ('f' * 64,) * len(p.GATE_IDS), (50, 50, '0' * 64))
    return subject, plan


def observation(state, public=False):
    assets = tuple(p.RemoteAsset(identity, asset, asset.size, asset.sha256, public)
                   for identity, asset in zip(state.asset_ids, state.plan.assets))
    return p.Observation(state.subject, state.plan.assets,
        tuple((*row, 'passed') for row in p._admission(state.subject)), 'commit', state.subject.tag_object_sha,
        () if state.release_id is None else (state.release_id,), 'proven', True, state.release_id,
        assets, not public, True, state.subject.stable_latest_identity)


def successful_result(transition):
    state, op = transition.state, transition.action
    values = {}
    if op.kind in ('ObserveFence', 'ObserveDraft', 'VerifyPublished'):
        values['observation'] = observation(state, op.kind == 'VerifyPublished')
    elif op.kind in ('CreateDraft', 'PublishPrerelease'):
        values['release_id'] = state.release_id or 100
    else:
        verified = op.kind == 'VerifyAsset'
        values.update(release_id=state.release_id, asset=p.RemoteAsset(op.asset_id if verified else
            200 + op.asset_ordinal, op.asset, op.asset.size if verified else None,
            op.asset.sha256 if verified else None))
    return p.OperationResult(p.RESULT_KINDS[p.OPERATION_KINDS.index(op.kind)], op.operation_id,
        op.subject_digest, op.kind, 'confirmed' if op.kind in p.MUTATIONS else 'none', **values)


def succeed(transition):
    return p.advance(transition.state, successful_result(transition))


def trace():
    transitions = [p.start(*fixture())]
    while transitions[-1].action is not None:
        current = transitions[-1]
        if type(current.action) is p.AwaitPublishRequest:
            request = p.PublicationRequest('request-1', 'external-owner-decision', current.state.release_id,
                                           current.action.subject_digest)
            transitions.append(p.request_publish(current.state, request))
        else:
            transitions.append(succeed(current))
    return transitions


class PublicationContractTests(unittest.TestCase):
    def setUp(self):
        self.subject, self.plan = fixture()
        self.steps = trace()

    def at(self, kind, index=0):
        return [t for t in self.steps if type(t.action) is p.Operation and t.action.kind == kind][index]

    def bad_observation(self, transition, **changes):
        result = successful_result(transition)
        return p.advance(transition.state, replace(result, observation=replace(result.observation, **changes)))

    def failure(self, transition, effect='none', code='denied', **fields):
        op = transition.action
        result = p.OperationResult('OperationUncertain' if effect == 'unknown' else 'OperationFailed',
            op.operation_id, op.subject_digest, op.kind, effect, code=code, **fields)
        return p.advance(transition.state, result)

    def assertStopped(self, transition, outcome=None):
        self.assertIsNone(transition.action)
        self.assertNotEqual(transition.state.outcome, 'modeled_verified')
        if outcome is not None:
            self.assertEqual(transition.state.outcome, outcome)
        self.assertFalse(any(getattr(transition, name) for name in
            ('release_approved', 'publish_approved', 'snapshot_atomic', 'live_publication_verified')))

    def test_exact_six_asset_plan_uses_consumer_payload_contract(self):
        with patch.object(p, 'payloads', wraps=p.payloads) as seam:
            transition = p.start(self.subject, self.plan)
        seam.assert_called_once_with('0.7.0-rc.1')
        self.assertEqual(len(transition.state.plan.assets), 6)
        self.assertEqual(tuple((a.name, a.family, a.media_type) for a in self.plan.assets[:4]),
                         p.payloads(self.subject.source.version))
        self.assertEqual(self.plan.assets[-2].name, 'RC_PROVENANCE.json')
        changed = replace(self.plan, assets=(replace(self.plan.assets[0], size=99), *self.plan.assets[1:]))
        other = p.start(self.subject, changed)
        self.assertNotEqual(other.action.subject_digest, transition.action.subject_digest)
        self.assertStopped(p.advance(other.state, successful_result(transition)))

    def test_canonical_rc_subject_and_exact_tag_binding(self):
        for version in ('0.7.0', '0.7.0-rc.01', 'v0.7.0-rc.1', '00.7.0-rc.1', '0.7.0-beta.1'):
            with self.subTest(version=version), self.assertRaises(p.ContractError):
                replace(self.subject.source, version=version)
        for fields in ({'tag': 'v0.7.0-rc.2'}, {'tag_object_sha': 'c' * 40}):
            with self.assertRaises(p.ContractError):
                replace(self.subject, **fields)
        self.assertEqual(self.subject.source.version, '0.7.0-rc.1')

    def test_subject_numeric_digest_and_size_bounds(self):
        for field in ('artifact_id', 'artifact_size'):
            for value in (True, 0, -1, 2**63, '1'):
                with self.subTest(field=field, value=value), self.assertRaises(p.ContractError):
                    replace(self.subject, **{field: value})
        for digest in ('g' * 64, '0' * 63, '0' * 65, '', True):
            with self.assertRaises(p.ContractError):
                replace(self.subject, plan_sha256=digest)
        for value in (True, 0, -1, 2**40 + 1):
            with self.assertRaises(p.ContractError):
                replace(self.plan.assets[0], size=value)
        with self.assertRaises(p.ContractError):
            replace(self.subject, job_ids=((True,), (32,), (33,)))

    def test_missing_extra_duplicate_or_path_asset_rejected(self):
        for assets in (self.plan.assets[:-1], self.plan.assets + self.plan.assets[:1]):
            with self.assertRaises(p.ContractError):
                p.AssetPlanView(assets)
        for assets in ((self.plan.assets[0],) * 6, tuple(reversed(self.plan.assets))):
            with self.assertRaises(p.ContractError):
                p.start(self.subject, p.AssetPlanView(assets))
        for name in ('../asset', '/asset', 'a\\b', 'x' * 161):
            with self.assertRaises(p.ContractError):
                replace(self.plan.assets[0], name=name)

    def test_original_false_flags_and_blockers_preserved(self):
        original = dict(source=asdict(self.subject.source), producer=asdict(self.subject.runs[0]),
            assets=[asdict(a) for a in self.plan.assets], release_approved=False, publish_approved=False,
            snapshot_atomic=False, release_blockers=list(BLOCKERS), limitations=['fixture-boundary'])
        before = json.dumps(original, sort_keys=True)
        projected = p.AssetPlanView(tuple(p.Asset(**row) for row in original['assets']))
        p.start(self.subject, projected)
        self.assertEqual(json.dumps(original, sort_keys=True), before)
        self.assertEqual(original['release_blockers'], list(BLOCKERS))
        self.assertIs(original['release_approved'], False)
        with self.assertRaises(FrozenInstanceError):
            projected.assets = ()

    def test_serialized_plan_is_never_authorization(self):
        for value in (asdict(self.plan), json.dumps(asdict(self.plan)), {'authorized': True}):
            with self.assertRaises(p.ContractError):
                p.start(self.subject, value)
        self.assertFalse(hasattr(p, 'decode'))
        self.assertFalse(hasattr(p, 'parse_json'))
        for transition in self.steps:
            self.assertIs(transition.release_approved, False)
            self.assertIs(transition.publish_approved, False)

    def test_module_has_no_io_entrypoint_or_executable_adapter(self):
        tree = ast.parse(inspect.getsource(p))
        imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        imports |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        self.assertEqual(imports, {'dataclasses', 'hashlib', 'json', 'rc_artifact_consumer',
                                  'rc_pretag_types', 'rc_release_policy'})
        calls = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
        self.assertFalse(calls & {'open', 'eval', 'exec', '__import__', 'print', 'input'})
        self.assertNotIn('__main__', inspect.getsource(p))
        self.assertEqual({n.name for n in tree.body if isinstance(n, ast.FunctionDef) and not n.name.startswith('_')},
                         {'start', 'advance', 'request_publish'})

    def test_missing_failed_unknown_or_stale_fence_blocks(self):
        transition = self.at('ObserveFence')
        rows = observation(transition.state).gates
        for gate_index in range(len(p.GATE_IDS)):
            for status in ('failed', 'skipped', 'unknown', 'stale'):
                changed = list(rows)
                changed[gate_index] = (*rows[gate_index][:3], status)
                self.assertStopped(self.bad_observation(transition, gates=tuple(changed)), 'blocked_no_effect')
        self.assertStopped(self.bad_observation(transition, gates=rows[:-1]))
        self.assertStopped(self.bad_observation(transition, gates=rows[:-1] + rows[:1]))

    def test_historical_pretag_absence_and_current_tag_are_distinct(self):
        transition = self.at('ObserveFence')
        rows = observation(transition.state).gates
        index = p.GATE_IDS.index('tag_absence')
        self.assertEqual(rows[index][1], 'historical_pretag')
        self.assertEqual(observation(transition.state).tag_kind, 'commit')
        changed = list(rows)
        changed[index] = (rows[index][0], 'current_admission', *rows[index][2:])
        self.assertStopped(self.bad_observation(transition, gates=tuple(changed)))
        self.assertEqual(succeed(transition).action.kind, 'CreateDraft')

    def test_absent_annotated_moved_or_foreign_tag_blocks(self):
        transition = self.at('ObserveFence')
        for kind in ('absent', 'tag', 'unknown'):
            self.assertStopped(self.bad_observation(transition, tag_kind=kind))
        for digest in (None, 'c' * 40):
            self.assertStopped(self.bad_observation(transition, tag_object_sha=digest))
        with self.assertRaises(p.ContractError):
            replace(self.subject.source, repository='foreign/repository')

    def test_collision_or_unproven_draft_visibility_blocks(self):
        transition = self.at('ObserveFence')
        for changes in ({'release_ids': (100,)}, {'draft_visibility': 'unknown'},
                        {'draft_visibility': 'denied'}, {'inventory_complete': False}):
            self.assertStopped(self.bad_observation(transition, **changes), 'blocked_no_effect')
        draft = self.at('ObserveDraft')
        self.assertStopped(self.bad_observation(draft, release_ids=(100, 101)), 'partial_draft')

    def test_draft_intent_preserves_prerelease_and_latest(self):
        op = self.at('CreateDraft').action
        self.assertEqual((op.tag, op.draft, op.prerelease, op.latest_policy),
                         (self.subject.tag, True, True, 'preserve'))
        self.assertIsNone(op.release_id)
        self.assertEqual(op.expected_asset_ids, ())
        self.assertEqual(op.subject_digest, p._digest(self.subject, self.plan))
        for fields in ({'kind': 'DeleteRelease'}, {'release_id': 100}, {'expected_asset_ids': (200,)},
                       {'operation_id': True}, {'operation_id': 26}, {'draft': False},
                       {'prerelease': False}, {'latest_policy': 'replace'}, {'request_id': 'surprise'}):
            with self.subTest(fields=fields), self.assertRaises(p.ContractError):
                replace(op, **fields)
        for kind in ('ObserveDraft', 'UploadAsset', 'VerifyAsset', 'PublishPrerelease', 'VerifyPublished'):
            with self.assertRaises(p.ContractError):
                replace(self.at(kind).action, release_id=None)

    def test_draft_response_and_inventory_identity_must_match(self):
        transition = self.at('CreateDraft')
        result = successful_result(transition)
        self.assertStopped(p.advance(transition.state, replace(result, release_id=None)), 'partial_draft')
        draft = self.at('ObserveDraft')
        for changes in ({'release_id': 101}, {'draft': False}, {'prerelease': False},
                        {'assets': (p.RemoteAsset(200, self.plan.assets[0]),)}):
            self.assertStopped(self.bad_observation(draft, **changes), 'partial_draft')

    def test_six_uploads_are_ordered_and_nonoverwriting(self):
        uploads = [self.at('UploadAsset', i) for i in range(6)]
        self.assertEqual([t.action.asset_ordinal for t in uploads], list(range(6)))
        self.assertEqual(tuple(t.action.asset for t in uploads), self.plan.assets)
        for ordinal, transition in enumerate(uploads):
            self.assertEqual(transition.action.expected_asset_ids, tuple(range(200, 200 + ordinal)))
            self.assertEqual(succeed(transition).action.kind, 'VerifyAsset')
        second = uploads[1]
        result = successful_result(second)
        self.assertStopped(p.advance(second.state, replace(result, asset=replace(result.asset, asset_id=200))))
        self.assertFalse(set(p.OPERATION_KINDS) & {'DeleteAsset', 'OverwriteAsset', 'DeleteRelease', 'CreateTag'})

    def test_every_upload_requires_fresh_subject_and_byte_fence(self):
        fences = [t for t in self.steps if type(t.action) is p.Operation and t.action.phase == 'before_upload']
        self.assertEqual(len(fences), 6)
        for transition in fences:
            self.assertEqual(succeed(transition).action.kind, 'UploadAsset')
            self.assertStopped(self.bad_observation(transition, staged=tuple(reversed(self.plan.assets))))
            changed = replace(self.subject, artifact_id=41)
            self.assertStopped(self.bad_observation(transition, subject=changed))
            self.assertEqual(transition.action.post_tag_checks, p.POST_TAG_CHECKS)
            self.assertEqual(tuple(row[0] for row in transition.action.admission), p.GATE_IDS)

    def test_upload_response_cannot_replace_expected_asset_identity(self):
        for index in range(6):
            transition = self.at('UploadAsset', index)
            result = successful_result(transition)
            for fields in ({'name': 'different.bin'}, {'sha256': '0' * 64}, {'size': 99}):
                asset = replace(result.asset, asset=replace(result.asset.asset, **fields))
                self.assertStopped(p.advance(transition.state, replace(result, asset=asset)), 'partial_draft')
            self.assertStopped(p.advance(transition.state, replace(result, release_id=101)), 'partial_draft')

    def test_downloaded_size_and_hash_must_match_each_asset(self):
        for index in range(6):
            transition = self.at('VerifyAsset', index)
            result = successful_result(transition)
            for fields in ({'downloaded_size': 0}, {'downloaded_sha256': '0' * 64}, {'asset_id': 999}):
                self.assertStopped(p.advance(transition.state,
                    replace(result, asset=replace(result.asset, **fields))), 'partial_draft')
        transition = self.at('VerifyAsset')
        premature = p.PublicationRequest('early', 'external', 100, transition.action.subject_digest)
        self.assertStopped(p.request_publish(transition.state, premature))

    def test_exact_final_draft_inventory_required(self):
        transition = self.at('ObserveDraft', 1)
        assets = observation(transition.state).assets
        for changed in (assets[:-1], tuple(reversed(assets)), assets[:-1] + assets[:1]):
            self.assertStopped(self.bad_observation(transition, assets=changed), 'partial_draft')
        self.assertIsInstance(succeed(transition).action, p.AwaitPublishRequest)

    def test_publish_wait_has_no_automatic_effect(self):
        waiting = next(t for t in self.steps if type(t.action) is p.AwaitPublishRequest)
        self.assertIsNone(waiting.state.pending)
        self.assertEqual(waiting.state.intent_count, 22)
        self.assertIsNone(waiting.state.request)
        self.assertFalse(waiting.state.published)
        self.assertStopped(p.advance(waiting.state, successful_result(self.at('ObserveDraft', 1))))

    def test_publish_request_binds_subject_and_draft_but_grants_no_authority(self):
        waiting = next(t for t in self.steps if type(t.action) is p.AwaitPublishRequest)
        request = p.PublicationRequest('publish', 'external-owner-reference', 100, waiting.action.subject_digest)
        for fields in ({'release_id': 101}, {'subject_digest': '0' * 64}):
            self.assertStopped(p.request_publish(waiting.state, replace(request, **fields)), 'partial_draft')
        transition = p.request_publish(waiting.state, request)
        self.assertEqual(transition.action.kind, 'ObserveFence')
        self.assertIs(transition.publish_approved, False)
        self.assertStopped(p.request_publish(transition.state, request))
        with self.assertRaises(p.ContractError):
            replace(request, reference='https://credentials.example/token')

    def test_publish_requires_new_final_fence(self):
        transition = self.at('ObserveFence', 7)
        self.assertEqual(transition.action.phase, 'before_publish')
        self.assertEqual(len(transition.action.expected_asset_ids), 6)
        self.assertEqual(transition.action.request_id, transition.state.request.request_id)
        for fields in ({'staged': ()}, {'gates': ()}, {'subject': replace(self.subject, artifact_id=99)}):
            self.assertStopped(self.bad_observation(transition, **fields), 'partial_draft')
        self.assertEqual(succeed(transition).action.kind, 'PublishPrerelease')
        observed = observation(transition.state)
        for index in range(6):
            for fields in ({'downloaded_size': None, 'downloaded_sha256': None},
                           {'downloaded_size': 0}, {'downloaded_sha256': '0' * 64}):
                assets = list(observed.assets)
                assets[index] = replace(assets[index], **fields)
                self.assertStopped(self.bad_observation(transition, assets=tuple(assets)), 'partial_draft')

    def test_publish_intent_cannot_promote_stable_or_latest(self):
        op = self.at('PublishPrerelease').action
        self.assertEqual((op.release_id, op.draft, op.prerelease, op.latest_policy), (100, False, True, 'preserve'))
        self.assertEqual(op.request_id, 'request-1')
        self.assertEqual(op.expected_asset_ids, tuple(range(200, 206)))
        self.assertNotIn('PromoteStable', p.OPERATION_KINDS)

    def test_public_metadata_and_anonymous_six_hashes_required(self):
        transition = self.at('VerifyPublished')
        original = observation(transition.state, True)
        for fields in ({'draft': True}, {'prerelease': False}, {'assets': original.assets[:-1]}):
            self.assertStopped(self.bad_observation(transition, **fields), 'published_unverified')
        for index in range(6):
            for fields in ({'anonymous': False}, {'downloaded_size': 0}, {'downloaded_sha256': '0' * 64}):
                assets = list(original.assets)
                assets[index] = replace(assets[index], **fields)
                self.assertStopped(self.bad_observation(transition, assets=tuple(assets)), 'published_unverified')
        self.assertEqual(succeed(transition).state.outcome, 'modeled_verified')

    def test_stable_latest_drift_fails_verification(self):
        for transition in [t for t in self.steps if type(t.action) is p.Operation and
                           t.action.kind in ('ObserveFence', 'ObserveDraft', 'VerifyPublished')]:
            self.assertStopped(self.bad_observation(transition, stable_latest_identity=(50, 51, '0' * 64)))
        self.assertStopped(self.bad_observation(self.at('VerifyPublished'),
            stable_latest_identity=(50, 50, '1' * 64)), 'published_unverified')

    def test_duplicate_stale_out_of_order_and_wrong_kind_results_reject(self):
        for transition in [t for t in self.steps if type(t.action) is p.Operation]:
            result = successful_result(transition)
            for fields in ({'operation_id': 25 if result.operation_id != 25 else 1}, {'subject_digest': '0' * 64}):
                self.assertStopped(p.advance(transition.state, replace(result, **fields)))
            other = self.at('CreateDraft') if transition.action.kind != 'CreateDraft' else self.at('ObserveFence')
            self.assertStopped(p.advance(transition.state, successful_result(other)))
        first = self.at('ObserveFence')
        self.assertStopped(p.advance(succeed(first).state, successful_result(first)), 'uncertain_remote_effect')
        for transition in (first, self.at('UploadAsset'), self.at('VerifyAsset'), self.at('PublishPrerelease')):
            for fields in ({'intent_count': True}, {'intent_count': 0}, {'intent_count': 26},
                           {'intent_count': 2**63}, {'asset_ids': (True,)}, {'asset_ids': [200]},
                           {'pending': 'invalid'}, {'request': 'invalid'}, {'mutated': 1}):
                with self.subTest(fields=fields), self.assertRaises(p.ContractError):
                    p.advance(replace(transition.state, **fields), successful_result(transition))
        waiting = next(t for t in self.steps if type(t.action) is p.AwaitPublishRequest)
        request = p.PublicationRequest('late', 'external', 100, waiting.action.subject_digest)
        for fields in ({'intent_count': 21}, {'asset_ids': (200,)}, {'published': True}):
            with self.assertRaises(p.ContractError):
                p.request_publish(replace(waiting.state, **fields), request)
        fence = self.at('ObserveFence', 1)
        wrong = replace(fence.action, phase='before_publish', request_id='unexpected')
        with self.assertRaises(p.ContractError):
            p.advance(replace(fence.state, pending=wrong), successful_result(fence))
        cases = [('CreateDraft', {'tag': 'v0.7.0-rc.2'}), ('UploadAsset', {'asset_ordinal': 1}),
                 ('UploadAsset', {'asset': replace(self.plan.assets[0], size=99)}),
                 ('VerifyAsset', {'asset_id': 999}), ('VerifyAsset', {'asset': self.plan.assets[1]}),
                 ('PublishPrerelease', {'request_id': 'other-request'}),
                 ('VerifyPublished', {'stable_latest_identity': (50, 51, '0' * 64)})]
        for kind, fields in cases:
            transition = self.at(kind)
            wrong = replace(transition.action, **fields)
            with self.subTest(kind=kind, fields=fields), self.assertRaises(p.ContractError):
                p.advance(replace(transition.state, pending=wrong), successful_result(transition))
        admission = list(first.action.admission)
        admission[0] = (*admission[0][:2], '0' * 64)
        wrong = replace(first.action, admission=tuple(admission))
        with self.assertRaises(p.ContractError):
            p.advance(replace(first.state, pending=wrong), successful_result(first))

    def test_confirmed_no_effect_and_partial_draft_are_distinct(self):
        self.assertStopped(self.failure(self.at('CreateDraft')), 'blocked_no_effect')
        confirmed = self.failure(self.at('CreateDraft'), 'confirmed', release_id=100)
        self.assertStopped(confirmed, 'partial_draft')
        self.assertEqual(confirmed.state.release_id, 100)
        for index in range(6):
            stopped = self.failure(self.at('UploadAsset', index))
            self.assertStopped(stopped, 'partial_draft')
            self.assertEqual(stopped.state.asset_ids, tuple(range(200, 200 + index)))

    def test_uncertain_mutation_is_sticky_and_never_retried(self):
        mutations = [t for t in self.steps if type(t.action) is p.Operation and t.action.kind in p.MUTATIONS]
        self.assertEqual(len(mutations), 8)
        for transition in mutations:
            uncertain = self.failure(transition, 'unknown', 'timeout')
            self.assertStopped(uncertain, 'uncertain_remote_effect')
            for later in self.steps:
                if type(later.action) is p.Operation:
                    self.assertEqual(p.advance(uncertain.state, successful_result(later)), uncertain)
            request = p.PublicationRequest('late', 'external', 100, transition.action.subject_digest)
            self.assertEqual(p.request_publish(uncertain.state, request), uncertain)

    def test_cancellation_and_adapter_errors_are_sanitized(self):
        for kind in p.MUTATIONS:
            transition = self.at(kind)
            for code in ('cancelled', 'adapter_error', 'denied'):
                before = self.failure(transition, code=code)
                self.assertStopped(before, 'blocked_no_effect' if kind == 'CreateDraft' else 'partial_draft')
                self.assertStopped(self.failure(transition, 'unknown', code), 'uncertain_remote_effect')
            with self.assertRaises(p.ContractError):
                self.failure(transition, code='secret https://signed-url.example/token')
            result = successful_result(transition)
            with self.assertRaises(p.ContractError):
                replace(result, kind='OperationFailed', effect='unknown', code='timeout')
            for fields in ({'effect': 'none'}, {'operation_id': True}, {'operation_id': 26},
                           {'observation': {}}, {'asset': []}, {'release_id': True}):
                with self.assertRaises(p.ContractError):
                    replace(result, **fields)
        read = self.at('ObserveFence')
        self.assertStopped(p.advance(read.state, replace(successful_result(read), observation=None)))
        upload = self.at('UploadAsset')
        self.assertStopped(p.advance(upload.state, replace(successful_result(upload), asset=None)), 'partial_draft')
        for transition in (self.at('CreateDraft'), read, upload):
            op = transition.action
            for effect in ('none', 'unknown'):
                for payload in ({'release_id': 100}, {'asset': p.RemoteAsset(200, self.plan.assets[0])}):
                    with self.assertRaises(p.ContractError):
                        self.failure(transition, effect, 'cancelled', **payload)
        confirmed = self.failure(upload, 'confirmed', 'adapter_error', release_id=100,
                                 asset=p.RemoteAsset(200, self.plan.assets[0]))
        self.assertStopped(confirmed, 'partial_draft')
        self.assertEqual(confirmed.state.asset_ids, (200,))

    def test_published_unverified_is_not_no_effect_or_success(self):
        transition = self.at('VerifyPublished')
        for effect in ('none', 'unknown'):
            stopped = self.failure(transition, effect, 'timeout')
            self.assertStopped(stopped, 'published_unverified')
            self.assertTrue(stopped.state.published)
            self.assertEqual(stopped.state.release_id, 100)
            self.assertEqual(stopped.state.asset_ids, tuple(range(200, 206)))
        published = self.failure(self.at('PublishPrerelease'), 'confirmed', release_id=100)
        self.assertStopped(published, 'published_unverified')

    def test_complete_model_trace_is_bounded_and_never_real_approval(self):
        operations = [t.action for t in self.steps if type(t.action) is p.Operation]
        self.assertEqual(len(operations), 25)
        self.assertEqual([op.operation_id for op in operations], list(range(1, 26)))
        self.assertEqual([op.kind for op in operations], ['ObserveFence', 'CreateDraft', 'ObserveDraft'] +
            ['ObserveFence', 'UploadAsset', 'VerifyAsset'] * 6 +
            ['ObserveDraft', 'ObserveFence', 'PublishPrerelease', 'VerifyPublished'])
        terminal = self.steps[-1]
        self.assertEqual(terminal.state.outcome, 'modeled_verified')
        self.assertIsNone(terminal.action)
        self.assertEqual(terminal.state.intent_count, 25)
        for transition in self.steps:
            for field in ('release_approved', 'publish_approved', 'snapshot_atomic', 'live_publication_verified'):
                self.assertIs(getattr(transition, field), False)
        self.assertEqual(p.start(self.subject, self.plan), self.steps[0])
        self.assertEqual(p.advance(terminal.state, successful_result(self.at('VerifyPublished'))), terminal)


if __name__ == '__main__':
    unittest.main()
