"""Blocked-only eligibility aggregation of unverified, caller-supplied reports.

A reported passing row is retained but cannot authenticate itself. No trusted
producer or approval adapter is implemented by this contract-only increment.
"""
from dataclasses import dataclass

from rc_pretag_types import (InvocationIdentity, PERMISSIONS, POLICY_REVISION, PreTagCandidate,
                            SourceIdentity, choice, positive, require, sequence, sha)
from rc_release_policy import GATES, GATE_IDS

REASONS = ('review_dismissed', 'review_changes_requested', 'review_pending', 'review_state_unknown',
           'missing_evidence', 'source_mismatch', 'reported_failed', 'reported_skipped',
           'reported_unknown', 'permission_unproven', 'visibility_unproven',
           'evidence_digest_missing', 'review_provenance_unproven', 'review_source_mismatch',
           'selected_run_missing', 'selected_attempt_mismatch', 'authenticating_producer_unimplemented')


@dataclass(frozen=True)
class ReviewObservation:
    reviewer_id: int
    review_id: int
    reviewed_sha: str
    pr_head_sha: str
    main_source_sha: str
    receipt_sha256: str
    state: str
    provenance: str

    def __post_init__(self):
        positive(self.reviewer_id)
        positive(self.review_id)
        for value in (self.reviewed_sha, self.pr_head_sha, self.main_source_sha):
            sha(value)
        sha(self.receipt_sha256, 64)
        choice(self.state, ('approved', 'dismissed', 'changes_requested', 'pending', 'unknown'))
        choice(self.provenance, ('unverified',))


@dataclass(frozen=True)
class GateObservation:
    gate_id: str
    reported_status: str
    source: SourceIdentity
    evidence_sha256: str | None
    permissions_observed: tuple[str, ...]
    visibility: str
    invocation: InvocationIdentity | None
    review: ReviewObservation | None

    def __post_init__(self):
        choice(self.gate_id, GATE_IDS, 'unknown_gate')
        choice(self.reported_status, ('passed', 'failed', 'unknown', 'skipped'))
        require(type(self.source) is SourceIdentity, 'invalid_gate_source')
        if self.evidence_sha256 is not None:
            sha(self.evidence_sha256, 64)
        sequence(self.permissions_observed, str, 3)
        require(len(set(self.permissions_observed)) == len(self.permissions_observed)
                and all(p in PERMISSIONS for p in self.permissions_observed), 'invalid_permissions')
        choice(self.visibility, ('observed', 'unknown', 'denied'))
        require(self.invocation is None or type(self.invocation) is InvocationIdentity,
                'invalid_gate_invocation')
        require(self.review is None or type(self.review) is ReviewObservation, 'invalid_review')


@dataclass(frozen=True)
class GateResult:
    gate_id: str
    reported_status: str
    status: str
    reason: str

    def __post_init__(self):
        choice(self.gate_id, GATE_IDS, 'unknown_gate')
        choice(self.reported_status, ('passed', 'failed', 'unknown', 'skipped', 'missing'))
        choice(self.status, ('failed', 'unknown'))
        choice(self.reason, REASONS)


@dataclass(frozen=True)
class ReleaseEligibility:
    source: SourceIdentity
    policy_revision: str
    status: str
    rows: tuple[GateResult, ...]
    release_approved: bool = False
    publish_approved: bool = False
    snapshot_atomic: bool = False
    evidence_authentication: str = 'unverified'

    def __post_init__(self):
        require(type(self.source) is SourceIdentity, 'invalid_eligibility_source')
        require(self.policy_revision == POLICY_REVISION, 'unsupported_policy_revision')
        choice(self.status, ('blocked',))
        sequence(self.rows, GateResult, 128)
        require(tuple(row.gate_id for row in self.rows) == GATE_IDS, 'incomplete_eligibility_inventory')
        require(self.release_approved is False and self.publish_approved is False
                and self.snapshot_atomic is False, 'approval_forbidden')
        choice(self.evidence_authentication, ('unverified',))


def evaluate(candidate: PreTagCandidate, observations: tuple[GateObservation, ...],
             selected: tuple[InvocationIdentity, ...] = ()) -> ReleaseEligibility:
    require(type(candidate) is PreTagCandidate, 'invalid_candidate')
    sequence(observations, GateObservation, len(GATES))
    require(len({o.gate_id for o in observations}) == len(observations), 'duplicate_gate')
    sequence(selected, InvocationIdentity, 3)
    require(all(run.role in ('integration', 'final', 'consumer') for run in selected)
            and len({run.role for run in selected}) == len(selected), 'invalid_selected_runs')
    require(all(run.source == candidate.source for run in selected), 'selected_source_mismatch')
    by_id = {o.gate_id: o for o in observations}
    runs = {run.role: run for run in selected}
    results = []
    for gate in GATES:
        row = by_id.get(gate.gate_id)
        reported, status, reason = 'missing', 'unknown', 'missing_evidence'
        if row is not None:
            reported = row.reported_status
            if row.source != candidate.source or (row.invocation is not None
                                                 and row.invocation.source != candidate.source):
                status, reason = 'failed', 'source_mismatch'
            elif row.review is not None and any(value != candidate.source.source_sha for value in (
                    row.review.reviewed_sha, row.review.pr_head_sha, row.review.main_source_sha)):
                status, reason = 'failed', 'review_source_mismatch'
            elif row.review is not None and row.review.state in ('dismissed', 'changes_requested'):
                status, reason = 'failed', 'review_' + row.review.state
            elif reported in ('failed', 'skipped'):
                status, reason = 'failed', 'reported_' + reported
            elif reported == 'unknown':
                reason = 'reported_unknown'
            elif not set(gate.permissions) <= set(row.permissions_observed):
                reason = 'permission_unproven'
            elif row.visibility != 'observed':
                reason = 'visibility_unproven'
            elif row.evidence_sha256 is None:
                reason = 'evidence_digest_missing'
            elif row.review is not None and row.review.state in ('pending', 'unknown'):
                reason = 'review_pending' if row.review.state == 'pending' else 'review_state_unknown'
            elif row.invocation is not None and row.invocation.role != 'pretag':
                expected = runs.get(row.invocation.role)
                if expected is None:
                    reason = 'selected_run_missing'
                elif row.invocation != expected:
                    status, reason = 'failed', 'selected_attempt_mismatch'
                else:
                    reason = 'authenticating_producer_unimplemented'
            elif row.invocation is not None and row.invocation != candidate.invocation:
                status, reason = 'failed', 'selected_attempt_mismatch'
            elif gate.gate_id in ('main_integration', 'final_independent_review'):
                reason = 'review_provenance_unproven'
            else:
                reason = 'authenticating_producer_unimplemented'
        results.append(GateResult(gate.gate_id, reported, status, reason))
    return ReleaseEligibility(candidate.source, POLICY_REVISION, 'blocked', tuple(results))
