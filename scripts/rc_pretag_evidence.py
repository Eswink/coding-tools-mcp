"""Unverified pre-tag receipt schema, not an actual evidence finalizer.

The future collector must independently authenticate API identity and ZIP bytes,
resolve visibility/review/engineering gates, and repeat fresh admission fences.
This module cannot perform those operations or mint successful live evidence.
"""
from dataclasses import dataclass

from rc_pretag_types import (InvocationIdentity, PreTagCandidate, SourceIdentity, choice,
                            positive, require, sequence, sha, timestamp)
from rc_release_eligibility import GateObservation, ReleaseEligibility, evaluate

INTEGRATION_JOBS = frozenset(('native (ubuntu-22.04)', 'native (ubuntu-24.04)',
    'native (windows-2025)', 'real-transport (ubuntu-22.04)', 'real-transport (ubuntu-24.04)',
    'browser', 'oauth-process-browser'))
FINAL_JOBS = frozenset((
    'Exact approved source and integration prerequisite', 'cloud / build', 'cloud / process',
    'cloud / Non-root image build and protected-file fixture (no deployment)',
    'Same-source nonproduction topology acceptance / topology',
    'Version, packaging and authenticated dependency contracts',
    'Build and install exact Windows NSIS (isolation unresolved)',
    'Build exact Ubuntu22 DEB and AppImage', 'Installed ubuntu-22.04 (deb)',
    'Installed ubuntu-24.04 (deb)', 'Installed ubuntu-22.04 (appimage)',
    'Installed ubuntu-24.04 (appimage)', 'Collect exact-source packaging evidence (release remains blocked)'))
BLOCKERS = ('Windows production isolation security profile remains unresolved',
            'Full original release ledger and external release approval remain required')
BUNDLE_JOB = 'Collect exact-source packaging evidence (release remains blocked)'


@dataclass(frozen=True)
class JobObservation:
    job_id: int
    name: str
    run_id: int
    run_attempt: int
    source_sha: str
    status: str
    conclusion: str
    started_at: str
    completed_at: str

    def __post_init__(self):
        for value in (self.job_id, self.run_id, self.run_attempt):
            positive(value)
        choice(self.name, INTEGRATION_JOBS | FINAL_JOBS, 'unknown_job')
        sha(self.source_sha)
        choice(self.status, ('completed',))
        choice(self.conclusion, ('success',))
        require(timestamp(self.started_at) <= timestamp(self.completed_at), 'invalid_job_times')


@dataclass(frozen=True)
class SelectedRunObservation:
    invocation: InvocationIdentity
    current_attempt: int
    newest_run_id: int
    run_started_at: str
    updated_at: str
    jobs: tuple[JobObservation, ...]
    jobs_response_sha256: str
    lists_complete_observation: bool

    def __post_init__(self):
        require(type(self.invocation) is InvocationIdentity
                and self.invocation.role in ('final', 'integration'), 'invalid_selected_run')
        positive(self.current_attempt)
        positive(self.newest_run_id)
        run = self.invocation
        require(self.current_attempt == run.run_attempt and self.newest_run_id == run.run_id,
                'not_newest_current_attempt')
        begin, end = timestamp(self.run_started_at), timestamp(self.updated_at)
        require(begin <= end, 'invalid_run_times')
        sequence(self.jobs, JobObservation, 13)
        names = FINAL_JOBS if run.role == 'final' else INTEGRATION_JOBS
        require(len(self.jobs) == len(names) and {j.name for j in self.jobs} == names
                and len({j.job_id for j in self.jobs}) == len(self.jobs), 'invalid_job_inventory')
        for job in self.jobs:
            require(job.run_id == run.run_id and job.run_attempt == run.run_attempt
                    and job.source_sha == run.source.source_sha, 'job_attempt_source_mismatch')
            require(begin <= timestamp(job.started_at) <= timestamp(job.completed_at) <= end,
                    'job_time_binding_unproven')
        sha(self.jobs_response_sha256, 64)
        require(self.lists_complete_observation is True, 'incomplete_run_observation')


@dataclass(frozen=True)
class ArtifactObservation:
    source: SourceIdentity
    run_id: int
    run_attempt: int
    job_id: int
    artifact_id: int
    name: str
    size: int
    api_sha256: str
    downloaded_sha256: str
    created_at: str
    expired: bool
    authentication: str

    def __post_init__(self):
        require(type(self.source) is SourceIdentity, 'invalid_artifact_source')
        for value in (self.run_id, self.run_attempt, self.job_id, self.artifact_id, self.size):
            positive(value)
        require(self.run_attempt == 1 and self.size <= 2 * 1024**3, 'invalid_final_artifact')
        choice(self.name, ('rc-structural-bundle',))
        sha(self.api_sha256, 64)
        sha(self.downloaded_sha256, 64)
        require(self.api_sha256 == self.downloaded_sha256, 'artifact_digest_mismatch')
        timestamp(self.created_at)
        require(self.expired is False, 'expired_artifact')
        choice(self.authentication, ('unverified',))


@dataclass(frozen=True)
class PayloadObservation:
    name: str
    family: str
    size: int
    sha256: str

    def __post_init__(self):
        choice(self.family, ('nsis', 'deb', 'appimage', 'cloud'))
        require(type(self.name) is str and 0 < len(self.name) <= 128, 'invalid_payload_name')
        positive(self.size)
        require(self.size <= 2 * 1024**3, 'payload_size_limit')
        sha(self.sha256, 64)


def payload_names(version):
    return {'nsis': f'MCP_{version}_x64-setup.exe', 'deb': f'MCP_{version}_amd64.deb',
            'appimage': f'MCP_{version}_amd64.AppImage', 'cloud': 'cloud-linux-amd64.tar.gz'}


@dataclass(frozen=True)
class StructuralObservation:
    source: SourceIdentity
    run_id: int
    run_attempt: int
    observed_at: str
    record_sha256: str
    passed: bool
    release_blockers: tuple[str, ...]
    release_approved: bool
    publish_approved: bool

    def __post_init__(self):
        require(type(self.source) is SourceIdentity, 'invalid_structural_source')
        positive(self.run_id)
        positive(self.run_attempt)
        require(self.run_attempt == 1, 'invalid_structural_attempt')
        timestamp(self.observed_at)
        sha(self.record_sha256, 64)
        require(type(self.passed) is bool, 'invalid_structural_passed')
        sequence(self.release_blockers, str, 2)
        require(self.release_blockers == BLOCKERS, 'unknown_or_changed_structural_blockers')
        require(self.release_approved is False and self.publish_approved is False, 'approval_forbidden')


@dataclass(frozen=True)
class AuditObservation:
    scope: str
    raw_vulnerability_count: int
    active_vulnerability_count: int
    unmaintained: int
    unsound: int
    notice: int
    yanked: int

    def __post_init__(self):
        choice(self.scope, ('cloud', 'desktop', 'local-agent', 'cloud-agent', 'npm'))
        for value in (self.raw_vulnerability_count, self.active_vulnerability_count,
                      self.unmaintained, self.unsound, self.notice, self.yanked):
            require(type(value) is int and 0 <= value <= 1000000, 'invalid_audit_count')
        require(self.active_vulnerability_count <= self.raw_vulnerability_count, 'invalid_audit_counts')


@dataclass(frozen=True)
class PreTagEvidenceReceipt:
    schema: int
    candidate: PreTagCandidate
    integration: SelectedRunObservation | None
    final: SelectedRunObservation | None
    consumer: InvocationIdentity | None
    artifact: ArtifactObservation | None
    payloads: tuple[PayloadObservation, ...]
    structural: StructuralObservation | None
    audits: tuple[AuditObservation, ...]
    observations: tuple[GateObservation, ...]
    release_collision_state: str
    draft_visibility: str
    evidence_collection_status: str
    eligibility_status: str
    eligibility: ReleaseEligibility
    finalized: bool
    release_approved: bool
    publish_approved: bool
    snapshot_atomic: bool

    def __post_init__(self):
        require(type(self.schema) is int and self.schema == 1, 'invalid_receipt_schema')
        require(type(self.candidate) is PreTagCandidate, 'invalid_candidate')
        source = self.candidate.source
        selected = []
        for role, run in (('integration', self.integration), ('final', self.final)):
            if run is not None:
                require(type(run) is SelectedRunObservation and run.invocation.role == role
                        and run.invocation.source == source, 'receipt_run_source_mismatch')
                selected.append(run.invocation)
        if self.consumer is not None:
            require(type(self.consumer) is InvocationIdentity and self.consumer.role == 'consumer'
                    and self.consumer.source == source, 'receipt_consumer_mismatch')
            selected.append(self.consumer)
        sequence(self.payloads, PayloadObservation, 4)
        sequence(self.audits, AuditObservation, 5)
        require(len({audit.scope for audit in self.audits}) == len(self.audits), 'duplicate_audit_scope')
        if self.artifact is None:
            require(not self.payloads and self.structural is None and not self.audits,
                    'unbound_bundle_observations')
        else:
            require(type(self.artifact) is ArtifactObservation and self.final is not None
                    and self.artifact.source == source, 'receipt_artifact_source_mismatch')
            final = self.final.invocation
            require(self.artifact.run_id == final.run_id
                    and self.artifact.run_attempt == final.run_attempt, 'artifact_attempt_mismatch')
            job = next(j for j in self.final.jobs if j.name == BUNDLE_JOB)
            require(self.artifact.job_id == job.job_id and timestamp(job.started_at)
                    <= timestamp(self.artifact.created_at) <= timestamp(job.completed_at),
                    'artifact_job_binding_unproven')
            expected = payload_names(source.version)
            require(len(self.payloads) == 4 and {p.family for p in self.payloads} == set(expected)
                    and all(p.name == expected[p.family] for p in self.payloads), 'invalid_payload_inventory')
        if self.structural is not None:
            require(type(self.structural) is StructuralObservation
                    and self.structural.source == source and self.artifact is not None
                    and self.structural.run_id == self.artifact.run_id
                    and self.structural.run_attempt == self.artifact.run_attempt, 'structural_source_mismatch')
        choice(self.release_collision_state, ('unknown', 'no_visible_collision', 'collision'))
        choice(self.draft_visibility, ('unknown', 'denied', 'reported_visible'))
        choice(self.evidence_collection_status, ('unverified',))
        choice(self.eligibility_status, ('blocked',))
        require(type(self.eligibility) is ReleaseEligibility and self.eligibility == evaluate(
            self.candidate, self.observations, tuple(selected)), 'eligibility_result_mismatch')
        require(self.finalized is False and self.release_approved is False
                and self.publish_approved is False and self.snapshot_atomic is False, 'approval_forbidden')
