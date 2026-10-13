"""Owned FINAL byte/audit evidence; unknown release gates remain blocked.

Trusted fixed Python source and no concurrent same-UID writer are prerequisites.
No caller report, external stage or verified flag can be imported as authority.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
from weakref import WeakKeyDictionary
from types import MethodType

import rc_artifact_consumer as consumer
from rc_consumer_io import CHUNK, JSON_LIMIT, ConsumerError, _check_budget, need
from rc_consumer_wire_failure import _publication_failure
import rc_publication_admission as metadata
import rc_publication_contract as core
from rc_publication_stage import Selection, StagedAssets, stage_selected
from rc_release_policy import GATE_IDS, GATES

ARTIFACT_GATES = ('bundle_bytes', 'raw_cloud_audit', 'raw_noncloud_audits')
_OWNERS = WeakKeyDictionary()


def _fixed_connection(api, selection):
    import rc_publication_github as wire
    need(type(api) is wire.GitHub and type(selection) is Selection
         and api.selection is selection and not api._closed, 'invalid_artifact_transport')
    # A get shadow is ignored by the unbound call. Its downstream method shadows
    # must not be able to replace the fixed verified HTTPS implementation.
    need(not any(name in api.__dict__ for name in ('_metadata', '_request', '_closed_request')),
         'invalid_artifact_transport')
    selection.__post_init__()


class _StageAPI:
    """Fixed concrete reads, retaining the current owned operation budget."""
    def __init__(self, api, selection):
        _fixed_connection(api, selection)
        self.api, self.selection = api, selection
        self.deadline = self.active = None
        self.closed = False

    @property
    def token(self):
        _fixed_connection(self.api, self.selection)
        need(not self.closed, 'artifact_owner_closed')
        return self.api.token

    def budget(self, deadline, active):
        need(not self.closed, 'artifact_owner_closed')
        _check_budget(deadline, active)
        self.deadline, self.active = deadline, active

    def get(self, path, *, deadline=None, check_active=None):
        import rc_publication_github as wire
        _fixed_connection(self.api, self.selection)
        need(not self.closed and self.deadline is not None, 'artifact_owner_closed')
        end = self.deadline if deadline is None else min(self.deadline, deadline)
        owned_active = self.active
        def active():
            # A supplied callback may strengthen, never replace, owner controls.
            if owned_active is not None:
                need(owned_active() is None, 'artifact_transport_failed')
            if check_active is not None and check_active is not owned_active:
                return check_active()
        _check_budget(end, active)
        interrupted = None
        def poll():
            nonlocal interrupted
            try:
                _check_budget(end, active)
            except ConsumerError as error:
                interrupted = error.code
                raise wire.WireFailure({'transport_deadline_exceeded': 'timeout',
                    'transport_cancelled': 'cancelled'}.get(error.code, 'adapter_error'), 'none') from None
            except (KeyboardInterrupt, SystemExit) as error:
                interrupted = type(error)
                raise wire.WireFailure('cancelled', 'none') from None
        try:
            value = wire.GitHub.get(self.api, path, deadline=end, check_active=poll)
        except wire.WireFailure as error:
            if error.effect != 'none':
                raise
            if interrupted is KeyboardInterrupt:
                raise KeyboardInterrupt() from None
            if interrupted is SystemExit:
                raise SystemExit(1) from None
            if type(interrupted) is str:
                raise ConsumerError(interrupted) from None
            if error.code in ('cancelled', 'timeout'):
                raise ConsumerError('transport_cancelled' if error.code == 'cancelled'
                                    else 'transport_deadline_exceeded') from None
            raise
        # Fixed GitHub.get polls after decoding; Stage validates returned
        # metadata before its enclosing fence, preserving semantic precedence.
        return value


def _evidence_digests(selection, assets, provenance, provenance_sha256, *, deadline, check_active):
    """Pure frozen expectations; this function alone authenticates nothing."""
    _check_budget(deadline, check_active)
    subject = selection.subject
    binding = dict(source=asdict(subject.source), tag=subject.tag, tag_object_sha=subject.tag_object_sha,
        runs=[asdict(run) for run in subject.runs], job_ids=subject.job_ids,
        final_artifact=dict(id=subject.artifact_id, size=subject.artifact_size, sha256=subject.artifact_sha256),
        consumer_artifact=dict(id=selection.consumer_artifact_id, size=selection.consumer_artifact_size,
                               sha256=selection.consumer_artifact_sha256),
        plan_sha256=subject.plan_sha256, provenance_sha256=provenance_sha256,
        assets=[asdict(asset) for asset in assets])
    values = (provenance, provenance['audits']['cloud'], provenance['audits']['noncloud'])
    result = []
    for gate_id, evidence in zip(ARTIFACT_GATES, values):
        _check_budget(deadline, check_active)
        record = dict(schema='rc-owned-final-artifact-v1', gate_id=gate_id, binding=binding, evidence=evidence)
        encoded = json.dumps(record, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=True, allow_nan=False).encode('utf-8')
        _check_budget(deadline, check_active)
        result.append(hashlib.sha256(encoded).hexdigest())
        _check_budget(deadline, check_active)
    return tuple(result)


@dataclass(frozen=True)
class _ArtifactReport:
    packaging: metadata._PackagingReport
    artifact_digests: tuple[str, ...]
    status = 'blocked'
    release_approved = publish_approved = snapshot_atomic = False
    draft_visibility = 'unknown'
    evidence_authentication = 'partial'

    def __post_init__(self):
        need(type(self.packaging) is metadata._PackagingReport, 'invalid_artifact_metadata')
        need(type(self.artifact_digests) is tuple and len(self.artifact_digests) == 3,
             'invalid_artifact_evidence')
        for key, digest in zip(ARTIFACT_GATES, self.artifact_digests):
            need(digest == self.packaging.subject.gate_evidence[GATE_IDS.index(key)],
                 'artifact_evidence_digest_mismatch')

    @property
    def rows(self):
        passed = ('full_integration', 'final_packaging', *ARTIFACT_GATES)
        return tuple((*row, 'passed' if row[0] in passed else 'unknown')
                     for row in core._admission(self.packaging.subject))


class _ArtifactOwner:
    """Created by a session; register only after real staging succeeds."""
    def __init__(self, root, selection, api, *, temporary_parent):
        _fixed_connection(api, selection)
        need(api not in _OWNERS, 'artifact_owner_exists')
        self.api, self.selection = api, selection
        self.adapter = _StageAPI(api, selection)
        self.stage = stage_selected(root, selection, self.adapter, temporary_parent=temporary_parent)
        self.closed = self.entered = False
        self._digests = self._report = None
        self._owner_deadline = self._owner_active = self._session = None

    def _controls(self, deadline, check_active):
        """Keep lifetime cancellation; only the bound session renews its scope."""
        end, owned_active = self._owner_deadline, self._owner_active
        need(end is not None, 'invalid_artifact_budget')
        if self._session is not None:
            import rc_publication_executor as executor
            session = self._session
            need(type(session) is executor.PublisherSession and session._artifact_owner is self
                 and session._api is self.api and session._selection is self.selection,
                 'invalid_artifact_session')
            end = session._deadline
            need(end is not None, 'artifact_scope_unavailable')
        native = self.api._credential._session_owner is not None
        # Standalone reads retain their original lifetime-first ordering. A
        # native client must check its actual controller before any caller hook.
        if not native:
            _check_budget(end, owned_active)
            _check_budget(deadline, check_active)
            end = end if deadline is None else min(end, deadline)
        if not native and owned_active is not None and check_active is owned_active:
            _check_budget(end, owned_active)
            return end, owned_active
        def active():
            if native:
                import rc_publication_github as wire
                try:
                    _check_budget(None, owned_active)
                    _check_budget(deadline, check_active if check_active is not owned_active else None)
                except ConsumerError as error:
                    if error.code == 'invalid_transport_deadline':
                        raise
                    # Keep the established callback vocabulary on later
                    # enclosing budget polls, without double-normalizing a
                    # ConsumerError. Non-none wire failures never enter here.
                    raise wire.WireFailure({'transport_cancelled': 'cancelled',
                        'transport_deadline_exceeded': 'timeout'}.get(error.code, 'adapter_error'), 'none') from None
                return
            if owned_active is not None:
                need(owned_active() is None, 'artifact_transport_failed')
            if check_active is not None and check_active is not owned_active:
                need(check_active() is None, 'artifact_transport_failed')
        if native:
            import rc_publication_request as owned
            import rc_publication_github as wire
            # Capture only the actual held-loop controller. Its first deadline
            # also bounds retained bytes after the last concrete HTTP GET.
            try:
                end, active, _ = owned._read_controls(self.api, end, active)
            except wire.WireFailure as error:
                if error.effect == 'none' and error.code in ('cancelled', 'timeout', 'adapter_error'):
                    raise ConsumerError({'cancelled': 'transport_cancelled',
                        'timeout': 'transport_deadline_exceeded'}.get(error.code, 'artifact_transport_failed')) from None
                raise
            end = end if deadline is None else min(end, deadline)
        _check_budget(end, active)
        return end, active

    def enter(self, *, deadline, check_active):
        import rc_publication_github as wire
        import rc_publication_executor as executor
        need(not self.closed and not self.entered and self.api not in _OWNERS, 'artifact_owner_lifetime')
        if self.api._credential._session_owner is None:
            _check_budget(deadline, check_active)
        self._owner_deadline, self._owner_active = deadline, check_active
        candidate = check_active.__self__ if type(check_active) is MethodType else None
        if (type(candidate) is executor.PublisherSession
                and check_active.__func__ is executor.PublisherSession._check_active
                and candidate._artifact_owner is self and candidate._api is self.api
                and candidate._selection is self.selection):
            self._session = candidate
        deadline, check_active = self._controls(deadline, check_active)
        wire._prepare_admission(self.selection, self.api, deadline=deadline, check_active=check_active)
        self.adapter.budget(deadline, check_active)
        self.stage._deadline, self.stage._check_active = deadline, check_active
        self.stage.__enter__()
        self.entered = True
        self._digests = self._capture(deadline=deadline, check_active=check_active)
        _check_budget(deadline, check_active)
        _OWNERS[self.api] = self

    def _capture(self, *, deadline, check_active):
        import rc_publication_github as wire
        deadline, check_active = self._controls(deadline, check_active)
        _fixed_connection(self.api, self.selection)
        need(not self.closed and self.entered and type(self.stage) is StagedAssets
             and self.stage._api is self.adapter and self.stage._selection == self.selection
             and self.stage.subject == self.selection.subject, 'invalid_artifact_owner')
        self.adapter.budget(deadline, check_active)
        assets = StagedAssets.revalidate(self.stage, deadline=deadline, check_active=check_active)
        fixed = (*consumer.payloads(self.selection.subject.source.version),
            ('RC_PROVENANCE.json', 'provenance', 'application/json'),
            ('SHA256SUMS_' + self.selection.subject.source.version + '.txt', 'checksums', 'text/plain'))
        need(tuple((a.name, a.family, a.media_type) for a in assets) == fixed, 'artifact_plan_changed')
        stream, raw, digest = StagedAssets.stream(self.stage, 4), bytearray(), hashlib.sha256()
        try:
            while True:
                _check_budget(deadline, check_active)
                chunk = stream.read(CHUNK)
                _check_budget(deadline, check_active)
                if not chunk:
                    break
                raw.extend(chunk)
                need(len(raw) <= JSON_LIMIT and len(raw) <= assets[4].size, 'artifact_provenance_limit')
                digest.update(chunk)
            need((len(raw), digest.hexdigest()) == (assets[4].size, assets[4].sha256),
                 'artifact_provenance_changed')
        finally:
            stream.seek(0)
        _check_budget(deadline, check_active)
        provenance = wire._json(bytes(raw))
        _check_budget(deadline, check_active)
        need(type(provenance) is dict and bytes(raw) == self.stage.provenance_bytes,
             'artifact_provenance_changed')
        need(hashlib.sha256(self.stage.plan_bytes).hexdigest() == self.selection.subject.plan_sha256,
             'artifact_plan_changed')
        _check_budget(deadline, check_active)
        plan = wire._json(self.stage.plan_bytes)
        _check_budget(deadline, check_active)
        expected = dict(provenance, assets=[asdict(asset) for asset in assets])
        need(consumer.encode(plan) == consumer.encode(expected), 'artifact_plan_changed')
        _check_budget(deadline, check_active)
        return _evidence_digests(self.selection, assets, provenance, digest.hexdigest(),
                                 deadline=deadline, check_active=check_active)

    def authenticate(self, *, deadline, check_active):
        need(_OWNERS.get(self.api) is self and not self.closed and self.entered,
             'artifact_owner_unavailable')
        deadline, check_active = self._controls(deadline, check_active)
        report = prepare_admission(self.selection, self.api, deadline=deadline, check_active=check_active)
        digests = self._capture(deadline=deadline, check_active=check_active)
        need(digests == self._digests, 'artifact_evidence_changed')
        for key, verifier in zip(ARTIFACT_GATES, ('github_final_bundle_bytes_v1',
                'github_final_raw_cloud_audit_v1', 'github_final_raw_noncloud_audits_v1')):
            need(next(g.verifier for g in GATES if g.gate_id == key) == verifier, 'artifact_policy_mismatch')
        result = _ArtifactReport(report, digests)
        _check_budget(deadline, check_active)
        self._report = result
        return result

    def close(self):
        self.closed = self.adapter.closed = True
        if _OWNERS.get(self.api) is self:
            del _OWNERS[self.api]


def authenticate_artifacts(api, selection, *, deadline, check_active):
    """No owner/record import: lookup only an actually staged in-process owner."""
    _fixed_connection(api, selection)
    owner = _OWNERS.get(api)
    if owner is None:
        import rc_publication_github as wire
        prepare_admission(selection, api, deadline=deadline, check_active=check_active)
        raise wire.WireFailure('fence_blocked', 'none')
    need(type(owner) is _ArtifactOwner and owner.api is api and owner.selection is selection,
         'invalid_artifact_owner')
    return owner.authenticate(deadline=deadline, check_active=check_active)


def _wire_failure(error):
    import rc_publication_github as wire
    normalized = _publication_failure(error)
    if normalized is not None and normalized.effect != 'none':
        return normalized
    if isinstance(error, (metadata._Interrupted, wire.WireFailure)):
        return wire.WireFailure(error.code, 'none')
    if isinstance(error, ConsumerError):
        return wire.WireFailure({'transport_deadline_exceeded': 'timeout',
            'transport_cancelled': 'cancelled'}.get(error.code, 'verification_failed'), 'none')
    return wire.WireFailure('verification_failed', 'none')


def prepare_admission(selection, api, *, check_active, deadline):
    """Fixed metadata prerequisite; returned inert data grants no write authority."""
    import rc_publication_github as wire
    try:
        _fixed_connection(api, selection)
        report = metadata.authenticate_packaging(api, selection, check_active=check_active, deadline=deadline)
        wire._need(type(report) is metadata._PackagingReport and report.subject == selection.subject)
        wire._need([row[0] for row in report.rows if row[3] == 'passed'] == ['full_integration', 'final_packaging'])
        return report
    except Exception as error:
        failure = _wire_failure(error)
    raise failure from None
