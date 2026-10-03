"""Data-only, negative-capable metadata receipts with no release authority.

Source versions are expectations. A receipt is not authenticated evidence even
when its requests used TLS and a bearer header. The old codecs stay unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from rc_pretag_types import (ContractError, REPOSITORY_ID, SourceIdentity, WORKFLOWS,
                            choice, decode, encode, parse_json, positive, require,
                            sequence, sha, text, timestamp)
from rc_pretag_evidence import FINAL_JOBS, INTEGRATION_JOBS
from rc_release_policy import GATE_IDS

SCHEMA = 'rc-pretag-metadata-v1'
ENGINEERING_REF = 'refs/heads/feat/rc-pretag-metadata-1dfe'
SOURCE_REF_PATTERN = (r'refs/heads/(?:feat/rc-pretag-metadata-1dfe|'
                      r'release/full-rc-candidate-[A-Za-z0-9][A-Za-z0-9._-]{0,79})')
OBSERVATION_KEYS = (
    'repository', 'ref', 'commit', 'trees', 'pretag_workflow',
    'integration_workflow', 'final_workflow', 'integration_runs', 'final_runs',
    'integration_run', 'final_run', 'integration_jobs', 'final_jobs',
    'pr', 'reviews', 'commits', 'collection',
)
OBSERVATION_STATES = ('observed', 'missing', 'inaccessible', 'invalid',
                      'unsupported', 'changed', 'prerequisite_unavailable')
REASON_CODES = frozenset((
    'observed', 'no_exact_source_run', 'prerequisite_unavailable',
    'source_mismatch', 'repository_mismatch', 'workflow_mismatch', 'tree_mismatch',
    'workflow_missing', 'invalid_metadata', 'incomplete_pagination',
    'duplicate_record', 'pagination_changed', 'pagination_limit',
    'unsupported_run', 'unsupported_attempt', 'jobs_incomplete', 'review_cap',
    'commit_cap', 'review_source_mismatch', 'snapshot_changed',
    'revalidation_unavailable', 'output_limit', 'unknown_state',
    'invalid_request', 'invalid_operation', 'invalid_token', 'invalid_json',
    'invalid_response', 'invalid_link', 'response_limit', 'aggregate_limit',
    'request_limit', 'request_timeout', 'collection_timeout', 'tls_failure',
    'network_failure', 'close_failure', 'unauthorized', 'forbidden',
    'not_found_or_not_visible', 'rate_limited', 'server_error',
    'unexpected_status', 'redirect_rejected', 'worker_failure',
    'worker_protocol_error', 'worker_teardown_unproven', 'unsupported_platform',
    'invalid_arguments', 'session_timeout', 'duplicate_json_key', 'nonfinite_json',
    'json_depth_limit', 'json_object_limit', 'json_array_limit', 'json_string_limit',
    'json_integer_limit', 'invalid_response_shape', 'invalid_headers',
    'transport_failure', 'worker_start_failed', 'worker_failed', 'invalid_ipc',
    'adapter_closed', 'concurrent_request', 'cleanup_uncertain',
))
RESOURCE_KINDS = ('repository', 'ref', 'commit', 'tree', 'workflow', 'run',
                  'job', 'pr', 'review', 'pr_commit')
FIXED_LABELS = ('source', 'root', '.github', 'workflows', 'pretag',
                'integration', 'final', 'unknown')
SAFE_NAMES = frozenset(FIXED_LABELS) | frozenset(WORKFLOWS.values()) | frozenset(
    path.rsplit('/', 1)[-1] for path in WORKFLOWS.values()) | FINAL_JOBS | INTEGRATION_JOBS
RECORD_STATES = frozenset((
    'observed', 'missing', 'unknown', 'queued', 'requested', 'waiting', 'pending',
    'in_progress', 'completed', 'active', 'disabled_manually',
    'disabled_inactivity', 'deleted', 'open', 'closed', 'approved', 'commented',
    'changes_requested', 'dismissed', 'APPROVED', 'COMMENTED',
    'CHANGES_REQUESTED', 'DISMISSED', 'PENDING',
))
CONCLUSIONS = ('success', 'failure', 'cancelled', 'skipped', 'timed_out',
               'neutral', 'action_required', 'stale', 'startup_failure', 'unknown')
EVENTS = ('push', 'pull_request', 'workflow_dispatch', 'unknown')


class MetadataError(ContractError):
    """A fixed code only; caller or remote text must never escape via errors."""

    def __init__(self, code='invalid_metadata'):
        self.code = code if type(code) is str and code in REASON_CODES else 'invalid_metadata'
        super().__init__(self.code)


def source_ref(value):
    text(value, SOURCE_REF_PATTERN, 'invalid_source_ref', 128)
    require('..' not in value and not value.endswith(('.', '/'))
            and '//' not in value, 'invalid_source_ref')


@dataclass(frozen=True)
class MetadataRequest:
    source: SourceIdentity
    source_ref: str

    def __post_init__(self):
        require(type(self.source) is SourceIdentity, 'invalid_source_identity')
        # Revalidate nested identities, including ones mutated outside dataclass APIs.
        SourceIdentity(**vars(self.source))
        source_ref(self.source_ref)


@dataclass(frozen=True)
class MetadataRecord:
    resource: str
    record_id: str
    repository_id: int | None = None
    source_sha: str | None = None
    source_tree: str | None = None
    workflow_id: int | None = None
    workflow_blob: str | None = None
    run_id: int | None = None
    run_attempt: int | None = None
    run_number: int | None = None
    name: str | None = None
    state: str | None = None
    conclusion: str | None = None
    event: str | None = None
    ref: str | None = None
    created_at: str | None = None
    started_at: str | None = None
    updated_at: str | None = None
    completed_at: str | None = None
    reviewer_id: int | None = None
    reviewed_sha: str | None = None
    submitted_at: str | None = None
    merged: bool | None = None
    head_sha: str | None = None
    base_sha: str | None = None
    merge_sha: str | None = None
    commit_count: int | None = None
    detail_sha256: str | None = None

    def __post_init__(self):
        choice(self.resource, RESOURCE_KINDS)
        require(type(self.record_id) is str and len(self.record_id) <= 40,
                'invalid_record_id')
        if self.record_id not in FIXED_LABELS:
            require(re.fullmatch(r'(?:[1-9][0-9]{0,18}|[0-9a-f]{40})', self.record_id)
                    is not None, 'invalid_record_id')
            if self.record_id.isdigit() and len(self.record_id) < 40:
                positive(int(self.record_id))
        for value in (self.repository_id, self.workflow_id, self.run_id,
                      self.run_attempt, self.run_number, self.reviewer_id):
            if value is not None:
                positive(value)
        if self.repository_id is not None:
            require(self.repository_id == REPOSITORY_ID, 'wrong_repository_id')
        for value in (self.source_sha, self.source_tree, self.workflow_blob,
                      self.reviewed_sha, self.head_sha, self.base_sha, self.merge_sha):
            if value is not None:
                sha(value)
        if self.detail_sha256 is not None:
            sha(self.detail_sha256, 64)
        if self.name is not None:
            choice(self.name, SAFE_NAMES, 'unknown_name')
        if self.state is not None:
            choice(self.state, RECORD_STATES)
        if self.conclusion is not None:
            choice(self.conclusion, CONCLUSIONS)
        if self.event is not None:
            choice(self.event, EVENTS)
        if 'unknown' in (self.name, self.state, self.conclusion, self.event):
            require(self.detail_sha256 is not None, 'missing_unknown_digest')
        if self.ref is not None:
            text(self.ref, r'refs/(?:heads/[A-Za-z0-9][A-Za-z0-9/._-]*|'
                 r'pull/[1-9][0-9]{0,18}/merge)', 'invalid_ref', 128)
            require('..' not in self.ref and '//' not in self.ref
                    and not self.ref.endswith(('/', '.')), 'invalid_ref')
        for value in (self.created_at, self.started_at, self.updated_at,
                      self.completed_at, self.submitted_at):
            if value is not None:
                timestamp(value)
        for left, right in ((self.created_at, self.updated_at),
                            (self.started_at, self.completed_at)):
            require(left is None or right is None or timestamp(left) <= timestamp(right),
                    'invalid_metadata_times')
        require(self.merged is None or type(self.merged) is bool, 'invalid_merged')
        require(self.commit_count is None or (type(self.commit_count) is int
                and 0 <= self.commit_count < 2**63), 'invalid_commit_count')


@dataclass(frozen=True)
class MetadataObservation:
    key: str
    state: str
    reason: str
    count: int
    comparison_sha256: str | None = None
    records: tuple[MetadataRecord, ...] = ()

    def __post_init__(self):
        choice(self.key, OBSERVATION_KEYS)
        choice(self.state, OBSERVATION_STATES)
        choice(self.reason, REASON_CODES)
        require(type(self.count) is int and 0 <= self.count <= 1000, 'invalid_count')
        sequence(self.records, MetadataRecord, 128)
        require(self.count >= len(self.records), 'invalid_count')
        require(len({(r.resource, r.record_id) for r in self.records}) == len(self.records),
                'duplicate_record')
        if self.comparison_sha256 is not None:
            sha(self.comparison_sha256, 64)
        require(self.state != 'observed' or self.comparison_sha256 is not None,
                'missing_comparison_digest')


@dataclass(frozen=True)
class MetadataReceipt:
    request: MetadataRequest
    observations: tuple[MetadataObservation, ...]
    revalidation_sha256: str | None
    started_at: str
    ended_at: str
    request_count: int
    response_bytes: int
    channel: str
    collection_status: str
    schema: str = SCHEMA
    evidence_authentication: str = 'unverified'
    eligibility_status: str = 'blocked'
    blocker: str = 'authenticating_producer_unimplemented'
    artifact_bytes_verified: bool = False
    finalized: bool = False
    release_approved: bool = False
    publish_approved: bool = False
    snapshot_atomic: bool = False
    principal_permissions: str = 'unproven'
    policy_gates: tuple[str, ...] = GATE_IDS
    revalidation_observations: tuple[MetadataObservation, ...] = ()

    def __post_init__(self):
        require(type(self.request) is MetadataRequest, 'invalid_metadata_request')
        sequence(self.observations, MetadataObservation, len(OBSERVATION_KEYS))
        require(len({row.key for row in self.observations}) == len(self.observations),
                'duplicate_observation')
        sequence(self.revalidation_observations, MetadataObservation, len(OBSERVATION_KEYS) - 1)
        require(len({row.key for row in self.revalidation_observations})
                == len(self.revalidation_observations), 'duplicate_observation')
        require(all(not row.records and row.key != 'collection'
                    for row in self.revalidation_observations), 'invalid_revalidation_summary')
        if self.revalidation_observations:
            require({row.key for row in self.revalidation_observations}
                    == set(OBSERVATION_KEYS) - {'collection'}, 'incomplete_revalidation_summary')
        if self.revalidation_sha256 is not None:
            sha(self.revalidation_sha256, 64)
        begin, end = timestamp(self.started_at), timestamp(self.ended_at)
        require(begin <= end, 'invalid_receipt_times')
        require(type(self.request_count) is int and 0 <= self.request_count <= 128,
                'invalid_request_count')
        require(type(self.response_bytes) is int and 0 <= self.response_bytes <= 16 * 1024**2,
                'invalid_response_bytes')
        choice(self.channel, ('synthetic', 'fixed_origin_tls_bearer_request'))
        choice(self.collection_status, ('observed_complete', 'partial', 'blocked'))
        identity = lambda row: (row.key, row.state, row.reason, row.count, row.comparison_sha256)
        require(self.collection_status != 'observed_complete' or (
            tuple(map(identity, self.observations))
            == tuple(map(identity, self.revalidation_observations))
            and self.revalidation_sha256 is not None
            and {row.key for row in self.observations} >= set(OBSERVATION_KEYS) - {'collection'}
            and all(row.state in ('observed', 'missing', 'unsupported')
                    for row in self.observations)), 'incomplete_metadata_receipt')
        for value, expected in ((self.schema, SCHEMA), (self.evidence_authentication, 'unverified'),
                (self.eligibility_status, 'blocked'),
                (self.blocker, 'authenticating_producer_unimplemented'),
                (self.principal_permissions, 'unproven')):
            require(type(value) is str and value == expected, 'metadata_authority_forbidden')
        for value in (self.artifact_bytes_verified, self.finalized, self.release_approved,
                      self.publish_approved, self.snapshot_atomic):
            require(value is False, 'metadata_authority_forbidden')
        sequence(self.policy_gates, str, len(GATE_IDS))
        require(self.policy_gates == GATE_IDS, 'incomplete_policy_gates')
