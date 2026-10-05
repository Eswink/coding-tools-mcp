"""Pure inert decisions: modeled records never grant publication authority.
The executor owns fresh admission/owner-authorization/revocation per mutation,
at-most-once dispatch and byte handles; fences are non-atomic and raw-plan binding external.
"""
from dataclasses import asdict, dataclass, field, fields, replace
import hashlib
import json

from rc_artifact_consumer import payloads
from rc_pretag_types import (ContractError, InvocationIdentity, SourceIdentity, choice,
                             positive, require, sequence, sha, text)
from rc_release_policy import GATE_IDS

OPERATION_KINDS = ('ObserveFence', 'CreateDraft', 'ObserveDraft', 'UploadAsset',
                   'VerifyAsset', 'PublishPrerelease', 'VerifyPublished')
RESULT_KINDS = ('FenceObserved', 'DraftCreated', 'DraftObserved', 'AssetUploaded',
                'AssetVerified', 'PrereleasePublished', 'PublishedVerified',
                'OperationFailed', 'OperationUncertain')
MUTATIONS = ('CreateDraft', 'UploadAsset', 'PublishPrerelease')
CODES = ('ok', 'cancelled', 'denied', 'timeout', 'adapter_error', 'invalid_event',
         'fence_blocked', 'identity_mismatch', 'verification_failed', 'invalid_request')
POST_TAG_CHECKS = ('consumer', 'live_tag', 'staged_bytes', 'release_inventory', 'latest_identity')


def _digest(value, plan):
    return hashlib.sha256(json.dumps((asdict(value), asdict(plan)), sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _ids(values, limit=6):
    sequence(values, int, limit)
    for value in values:
        positive(value)
    require(len(set(values)) == len(values), 'duplicate_identity')


def _latest(value):
    require(type(value) is tuple and len(value) == 3, 'invalid_latest_identity')
    for identity in value[:2]:
        require(type(identity) is int and 0 <= identity < 2**63, 'invalid_latest_id')
    sha(value[2], 64)


@dataclass(frozen=True)
class Asset:
    name: str
    family: str
    media_type: str
    size: int
    sha256: str

    def __post_init__(self):
        text(self.name, r'[A-Za-z0-9][A-Za-z0-9_.-]*', 'invalid_asset_name', 160)
        text(self.family, r'[a-z]+', 'invalid_asset_family', 16)
        text(self.media_type, r'[a-z0-9.+/-]+', 'invalid_media_type', 80)
        require(type(self.size) is int and 0 < self.size <= 2**40, 'invalid_asset_size')
        sha(self.sha256, 64)


@dataclass(frozen=True)
class AssetPlanView:
    assets: tuple[Asset, ...]

    def __post_init__(self):
        sequence(self.assets, Asset, 6)
        require(len(self.assets) == 6, 'invalid_asset_inventory')


@dataclass(frozen=True)
class PublicationSubject:
    source: SourceIdentity
    tag: str
    tag_object_sha: str
    runs: tuple[InvocationIdentity, ...]
    job_ids: tuple[tuple[int, ...], ...]
    artifact_id: int
    artifact_size: int
    artifact_sha256: str
    plan_sha256: str
    gate_evidence: tuple[str, ...]
    stable_latest_identity: tuple[int, int, str]

    def __post_init__(self):
        require(type(self.source) is SourceIdentity, 'invalid_source')
        require(type(self.tag) is str and self.tag == 'v' + self.source.version, 'invalid_tag')
        sha(self.tag_object_sha)
        require(self.tag_object_sha == self.source.source_sha, 'lightweight_tag_required')
        sequence(self.runs, InvocationIdentity, 3)
        require(tuple(r.role for r in self.runs) == ('final', 'integration', 'consumer')
                and all(r.source == self.source for r in self.runs), 'invalid_frozen_runs')
        require(type(self.job_ids) is tuple and len(self.job_ids) == 3 and all(self.job_ids), 'invalid_job_inventory')
        for ids in self.job_ids:
            _ids(ids, 64)
        positive(self.artifact_id)
        require(type(self.artifact_size) is int and 0 < self.artifact_size <= 2**40, 'invalid_artifact_size')
        require(type(self.gate_evidence) is tuple and len(self.gate_evidence) == len(GATE_IDS), 'incomplete_gate_bindings')
        for digest in (self.artifact_sha256, self.plan_sha256, *self.gate_evidence):
            sha(digest, 64)
        _latest(self.stable_latest_identity)


@dataclass(frozen=True)
class PublicationRequest:
    request_id: str
    reference: str
    release_id: int
    subject_digest: str

    def __post_init__(self):
        text(self.request_id, r'[A-Za-z0-9_-]+', 'invalid_request_id', 80)
        text(self.reference, r'[A-Za-z0-9_-]+', 'invalid_request_reference', 128)
        positive(self.release_id)
        sha(self.subject_digest, 64)


@dataclass(frozen=True)
class RemoteAsset:
    asset_id: int
    asset: Asset
    downloaded_size: int | None = None
    downloaded_sha256: str | None = None
    anonymous: bool = False

    def __post_init__(self):
        positive(self.asset_id)
        require(type(self.asset) is Asset and type(self.anonymous) is bool, 'invalid_remote_asset')
        require((self.downloaded_size is None) == (self.downloaded_sha256 is None), 'incomplete_download')
        if self.downloaded_size is not None:
            require(type(self.downloaded_size) is int and 0 <= self.downloaded_size <= 2**40,
                    'invalid_download_size')
            sha(self.downloaded_sha256, 64)

    def matches_bytes(self):
        return (self.downloaded_size, self.downloaded_sha256) == (self.asset.size, self.asset.sha256)


@dataclass(frozen=True)
class Observation:
    subject: PublicationSubject
    staged: tuple[Asset, ...]
    gates: tuple[tuple[str, str, str, str], ...]
    tag_kind: str
    tag_object_sha: str | None
    release_ids: tuple[int, ...]
    draft_visibility: str
    inventory_complete: bool
    release_id: int | None
    assets: tuple[RemoteAsset, ...]
    draft: bool
    prerelease: bool
    stable_latest_identity: tuple[int, int, str]

    def __post_init__(self):
        require(type(self.subject) is PublicationSubject, 'invalid_observed_subject')
        sequence(self.staged, Asset, 6)
        sequence(self.gates, tuple, len(GATE_IDS))
        for row in self.gates:
            require(len(row) == 4, 'invalid_gate_row')
            choice(row[0], GATE_IDS)
            choice(row[1], ('historical_pretag', 'current_admission'))
            sha(row[2], 64)
            choice(row[3], ('passed', 'failed', 'skipped', 'unknown', 'stale'))
        choice(self.tag_kind, ('commit', 'tag', 'absent', 'unknown'))
        if self.tag_object_sha is not None:
            sha(self.tag_object_sha)
        _ids(self.release_ids, 64)
        choice(self.draft_visibility, ('proven', 'unknown', 'denied'))
        if self.release_id is not None:
            positive(self.release_id)
        sequence(self.assets, RemoteAsset, 6)
        require(all(type(v) is bool for v in (self.inventory_complete, self.draft, self.prerelease)),
                'invalid_observation_flag')
        _latest(self.stable_latest_identity)


@dataclass(frozen=True)
class Operation:
    kind: str
    operation_id: int
    subject_digest: str
    release_id: int | None = None
    expected_asset_ids: tuple[int, ...] = ()
    phase: str | None = None
    asset_ordinal: int | None = None
    asset: Asset | None = None
    asset_id: int | None = None
    request_id: str | None = None
    tag: str | None = None
    draft: bool | None = None
    prerelease: bool | None = None
    latest_policy: str = 'preserve'
    admission: tuple[tuple[str, str, str], ...] = ()
    post_tag_checks: tuple[str, ...] = ()
    stable_latest_identity: tuple[int, int, str] | None = None

    def __post_init__(self):
        choice(self.kind, OPERATION_KINDS)
        require(type(self.operation_id) is int and 1 <= self.operation_id <= 25, 'operation_limit')
        sha(self.subject_digest, 64)
        _ids(self.expected_asset_ids)
        for identity in (self.release_id, self.asset_id):
            if identity is not None:
                positive(identity)
        require(self.latest_policy == 'preserve', 'latest_change_forbidden')
        initial = self.kind == 'CreateDraft' or (self.kind == 'ObserveFence' and self.phase == 'before_draft')
        require((self.release_id is None) is initial and (not initial or not self.expected_asset_ids),
                'invalid_operation_target')
        shape = dict(ObserveFence=('phase', 'admission', 'post_tag_checks'),
            CreateDraft=('tag', 'draft', 'prerelease'), ObserveDraft=(),
            UploadAsset=('asset_ordinal', 'asset'), VerifyAsset=('asset_id', 'asset'),
            PublishPrerelease=('request_id', 'draft', 'prerelease'), VerifyPublished=('stable_latest_identity',))
        optional = ('request_id',) if self.kind == 'ObserveFence' and self.phase == 'before_publish' else ()
        active = tuple(f.name for f in fields(self)[5:] if getattr(self, f.name) != f.default and f.name != 'latest_policy')
        require(set(active) == set(shape[self.kind] + optional), 'invalid_operation_shape')
        if self.phase is not None:
            choice(self.phase, ('before_draft', 'before_upload', 'before_publish'))
            require(self.post_tag_checks == POST_TAG_CHECKS and type(self.admission) is tuple
                    and len(self.admission) == len(GATE_IDS), 'invalid_admission')
            for index, row in enumerate(self.admission):
                require(type(row) is tuple and len(row) == 3 and row[:2] ==
                    (GATE_IDS[index], 'historical_pretag' if GATE_IDS[index] == 'tag_absence' else 'current_admission'), 'invalid_admission')
                sha(row[2], 64)
        if self.asset is not None:
            require(type(self.asset) is Asset, 'invalid_operation_asset')
        if self.asset_ordinal is not None:
            require(type(self.asset_ordinal) is int and 0 <= self.asset_ordinal < 6, 'invalid_ordinal')
        if self.request_id is not None:
            text(self.request_id, r'[A-Za-z0-9_-]+', 'invalid_request_id', 80)
        if self.tag is not None:
            text(self.tag, r'v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)-rc\.(?:0|[1-9][0-9]*)', 'invalid_tag', 81)
        if self.draft is not None:
            require(self.draft is (self.kind == 'CreateDraft') and self.prerelease is True, 'invalid_release_mode')
        if self.stable_latest_identity is not None:
            _latest(self.stable_latest_identity)


@dataclass(frozen=True)
class OperationResult:
    kind: str
    operation_id: int
    subject_digest: str
    expected_kind: str
    effect: str
    observation: Observation | None = None
    release_id: int | None = None
    asset: RemoteAsset | None = None
    code: str = 'ok'

    def __post_init__(self):
        choice(self.kind, RESULT_KINDS)
        require(type(self.operation_id) is int and 1 <= self.operation_id <= 25, 'operation_limit')
        sha(self.subject_digest, 64)
        choice(self.expected_kind, OPERATION_KINDS)
        choice(self.effect, ('none', 'confirmed', 'unknown'))
        choice(self.code, CODES)
        require(self.observation is None or type(self.observation) is Observation, 'invalid_observation')
        require(self.asset is None or type(self.asset) is RemoteAsset, 'invalid_asset_result')
        if self.release_id is not None:
            positive(self.release_id)
        if self.kind in ('OperationFailed', 'OperationUncertain'):
            require((self.effect == 'unknown') is (self.kind == 'OperationUncertain')
                    and self.code != 'ok' and self.observation is None, 'invalid_failure_result')
            require(self.effect == 'confirmed' or (self.release_id is None and self.asset is None),
                    'contradictory_failure_payload')
            require(self.asset is None or self.expected_kind == 'UploadAsset', 'invalid_failure_payload')
        else:
            require(self.kind == RESULT_KINDS[OPERATION_KINDS.index(self.expected_kind)]
                    and self.code == 'ok' and self.effect ==
                    ('confirmed' if self.expected_kind in MUTATIONS else 'none'), 'invalid_success_result')
        require(self.expected_kind in MUTATIONS or self.effect != 'confirmed', 'read_cannot_mutate')


@dataclass(frozen=True)
class PublicationState:
    subject: PublicationSubject
    plan: AssetPlanView
    pending: Operation | None = None
    intent_count: int = 0
    release_id: int | None = None
    asset_ids: tuple[int, ...] = ()
    request: PublicationRequest | None = None
    mutated: bool = False
    published: bool = False
    outcome: str | None = None
    code: str = 'ok'


@dataclass(frozen=True)
class AwaitPublishRequest:
    release_id: int
    subject_digest: str


@dataclass(frozen=True)
class Transition:
    state: PublicationState
    action: Operation | AwaitPublishRequest | None
    release_approved: bool = field(default=False, init=False)
    publish_approved: bool = field(default=False, init=False)
    snapshot_atomic: bool = field(default=False, init=False)
    live_publication_verified: bool = field(default=False, init=False)


def _state(state):
    require(type(state) is PublicationState and type(state.subject) is PublicationSubject
            and type(state.plan) is AssetPlanView and type(state.intent_count) is int
            and 1 <= state.intent_count <= 25, 'invalid_state')
    _ids(state.asset_ids)
    require(type(state.mutated) is bool and type(state.published) is bool, 'invalid_state')
    if state.release_id is not None:
        positive(state.release_id)
    require(state.request is None or type(state.request) is PublicationRequest, 'invalid_state')
    choice(state.code, CODES)
    if state.outcome is not None:
        choice(state.outcome, ('blocked_no_effect', 'partial_draft', 'uncertain_remote_effect',
                               'published_unverified', 'modeled_verified'))
        require(state.pending is None, 'invalid_terminal_state')
        return
    op = state.pending
    if op is None:
        require(state.intent_count == 22 and len(state.asset_ids) == 6 and state.release_id is not None
                and state.mutated and not state.published and state.request is None, 'invalid_waiting_state')
        return
    kinds = ('ObserveFence', 'CreateDraft', 'ObserveDraft') + ('ObserveFence', 'UploadAsset', 'VerifyAsset') * 6 + (
        'ObserveDraft', 'ObserveFence', 'PublishPrerelease', 'VerifyPublished')
    require(type(op) is Operation and op.operation_id == state.intent_count and op.kind == kinds[state.intent_count - 1]
            and op.subject_digest == _digest(state.subject, state.plan) and op.release_id == state.release_id
            and op.expected_asset_ids == state.asset_ids, 'invalid_pending_state')
    count = min(6, max(0, (state.intent_count - 3) // 3))
    require(len(state.asset_ids) == count and state.published is (state.intent_count == 25)
            and state.mutated is (state.intent_count >= 3), 'invalid_state_phase')
    require((state.request is not None) is (state.intent_count >= 23) and (state.request is None or
            (state.request.release_id == state.release_id and state.request.subject_digest == op.subject_digest)), 'invalid_request_phase')
    if op.kind == 'ObserveFence':
        require(op.phase == ('before_draft' if state.intent_count == 1 else 'before_publish' if state.intent_count == 23 else 'before_upload')
                and op.admission == _admission(state.subject), 'invalid_fence_phase')
    actual = (op.tag, op.asset_ordinal, op.asset, op.asset_id, op.request_id, op.stable_latest_identity)
    expected = (state.subject.tag, count, state.plan.assets[min(count - (op.kind == 'VerifyAsset'), 5)],
                state.asset_ids[-1] if state.asset_ids else None,
                state.request.request_id if state.request else None, state.subject.stable_latest_identity)
    require(all(value is None or value == expected[index] for index, value in enumerate(actual)),
            'operation_state_mismatch')


def _admission(subject):
    return tuple((gate, 'historical_pretag' if gate == 'tag_absence' else 'current_admission', digest)
                 for gate, digest in zip(GATE_IDS, subject.gate_evidence))


def _emit(state, kind, **fields):
    op = Operation(kind, state.intent_count + 1, _digest(state.subject, state.plan), state.release_id,
                   state.asset_ids, **fields)
    return Transition(replace(state, pending=op, intent_count=op.operation_id), op)


def _fence(state, phase):
    return _emit(state, 'ObserveFence', phase=phase, admission=_admission(state.subject),
                 post_tag_checks=POST_TAG_CHECKS, request_id=state.request.request_id if state.request else None)


def _stop(state, code, uncertain=False):
    outcome = ('uncertain_remote_effect' if uncertain or state.outcome == 'uncertain_remote_effect' else
               'published_unverified' if state.published else 'partial_draft' if state.mutated else 'blocked_no_effect')
    return Transition(replace(state, pending=None, outcome=outcome, code=code), None)


def _inventory(state, observation, public=False):
    require(type(observation) is Observation and observation.subject == state.subject
            and observation.inventory_complete and observation.draft_visibility == 'proven'
            and observation.tag_kind == 'commit' and observation.tag_object_sha == state.subject.tag_object_sha
            and observation.stable_latest_identity == state.subject.stable_latest_identity,
            'identity_mismatch')
    require(observation.release_ids == (() if state.release_id is None else (state.release_id,))
            and observation.release_id == state.release_id, 'identity_mismatch')
    expected = tuple(zip(state.asset_ids, state.plan.assets))
    require(tuple((a.asset_id, a.asset) for a in observation.assets) == expected, 'identity_mismatch')
    if state.release_id is not None:
        require(observation.draft is (not public) and observation.prerelease is True, 'identity_mismatch')
    if public:
        require(all(a.matches_bytes() and a.anonymous for a in observation.assets), 'verification_failed')


def start(subject: PublicationSubject, plan: AssetPlanView) -> Transition:
    require(type(subject) is PublicationSubject and type(plan) is AssetPlanView, 'invalid_start')
    fixed = (*payloads(subject.source.version), ('RC_PROVENANCE.json', 'provenance', 'application/json'),
             (f'SHA256SUMS_{subject.source.version}.txt', 'checksums', 'text/plain'))
    require(tuple((a.name, a.family, a.media_type) for a in plan.assets) == fixed, 'invalid_asset_inventory')
    return _fence(PublicationState(subject, plan), 'before_draft')


def advance(state: PublicationState, result: OperationResult) -> Transition:
    _state(state)
    if state.outcome is not None:
        return Transition(state, None)
    op = state.pending
    if op is None:
        return _stop(state, 'invalid_event')
    if (type(result) is not OperationResult or result.operation_id != op.operation_id
            or result.subject_digest != op.subject_digest or result.expected_kind != op.kind):
        return _stop(state, 'invalid_event', op.kind in MUTATIONS)
    if result.effect == 'unknown':
        return _stop(state, result.code, op.kind in MUTATIONS)
    if result.effect == 'confirmed':
        state = replace(state, mutated=True, published=state.published or op.kind == 'PublishPrerelease')
        if op.kind == 'CreateDraft' and result.release_id is not None:
            state = replace(state, release_id=result.release_id)
        if op.kind == 'UploadAsset' and result.asset is not None and result.asset.asset_id not in state.asset_ids:
            state = replace(state, asset_ids=state.asset_ids + (result.asset.asset_id,))
    if result.kind == 'OperationFailed':
        return _stop(state, result.code)
    try:
        observation = result.observation
        if op.kind in ('ObserveFence', 'ObserveDraft', 'VerifyPublished'):
            require(result.release_id is None and result.asset is None, 'invalid_event')
            _inventory(state, observation, op.kind == 'VerifyPublished')
        elif op.kind in ('CreateDraft', 'PublishPrerelease'):
            require(result.observation is None and result.asset is None and result.release_id is not None
                    and result.release_id == state.release_id, 'identity_mismatch')
        else:
            require(result.observation is None and result.release_id == state.release_id
                    and result.asset is not None and result.asset.asset == op.asset
                    and result.asset.asset_id == (state.asset_ids[-1] if op.kind == 'UploadAsset' else op.asset_id),
                    'identity_mismatch')
        if op.kind == 'ObserveFence':
            require(observation.staged == state.plan.assets
                    and observation.gates == tuple((*row, 'passed') for row in op.admission), 'fence_blocked')
            if op.phase == 'before_draft':
                return _emit(state, 'CreateDraft', tag=state.subject.tag, draft=True, prerelease=True)
            if op.phase == 'before_publish':
                require(all(a.matches_bytes() for a in observation.assets), 'verification_failed')
                return _emit(state, 'PublishPrerelease', request_id=state.request.request_id, draft=False, prerelease=True)
            return _emit(state, 'UploadAsset', asset_ordinal=len(state.asset_ids), asset=state.plan.assets[len(state.asset_ids)])
        if op.kind == 'CreateDraft':
            return _emit(state, 'ObserveDraft')
        if op.kind == 'ObserveDraft':
            if len(state.asset_ids) == 6:
                return Transition(replace(state, pending=None), AwaitPublishRequest(state.release_id, _digest(state.subject, state.plan)))
            return _fence(state, 'before_upload')
        if op.kind == 'UploadAsset':
            require(len(state.asset_ids) == op.asset_ordinal + 1, 'identity_mismatch')
            return _emit(state, 'VerifyAsset', asset_id=result.asset.asset_id, asset=op.asset)
        if op.kind == 'VerifyAsset':
            require(result.asset.matches_bytes(), 'verification_failed')
            return _emit(state, 'ObserveDraft') if len(state.asset_ids) == 6 else _fence(state, 'before_upload')
        if op.kind == 'PublishPrerelease':
            return _emit(state, 'VerifyPublished', stable_latest_identity=state.subject.stable_latest_identity)
        return Transition(replace(state, pending=None, outcome='modeled_verified'), None)
    except ContractError as error:
        return _stop(state, str(error))


def request_publish(state: PublicationState, request: PublicationRequest) -> Transition:
    _state(state)
    if state.outcome is not None:
        return Transition(state, None)
    if (state.pending is not None or state.request is not None or len(state.asset_ids) != 6
            or type(request) is not PublicationRequest or request.release_id != state.release_id
            or request.subject_digest != _digest(state.subject, state.plan)):
        return _stop(state, 'invalid_request', state.pending is not None and state.pending.kind in MUTATIONS)
    return _fence(replace(state, request=request), 'before_publish')
