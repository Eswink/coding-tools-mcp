"""Unverified publication observations only; no collector or executable authority."""
from dataclasses import dataclass

from rc_pretag_types import (POLICY_REVISION, SourceIdentity, choice, encode, parse_json,
                            positive, require, sequence, sha, text)
from rc_pretag_evidence import PayloadObservation, payload_names

SCHEMA = 1
DOMAIN = b'rc-publication-contract/v1:recipe\n'
BLOCKERS = ('authenticating_admission_unimplemented', 'consumer_handoff_unimplemented',
            'no_create_guarantee_unproven', 'live_visibility_freshness_unproven',
            'cross_journal_replay_unproven')
FAMILIES = ('nsis', 'deb', 'appimage', 'cloud', 'provenance', 'checksums')
MEDIA = ('application/vnd.microsoft.portable-executable', 'application/vnd.debian.binary-package',
         'application/octet-stream', 'application/gzip', 'application/json', 'text/plain')
REASONS = ('visibility_unproven', 'inventory_incomplete', 'target_inaccessible', 'lookup_unknown',
           'multiple_releases', 'release_mismatch', 'target_unresolved', 'asset_incomplete',
           'asset_conflict', 'asset_extra', 'asset_duplicate', 'published_partial',
           'journal_order', 'journal_target', 'journal_replay', 'checkpoint_required',
           'checkpoint_conflict', 'response_conflict', 'operation_after_stop',
           'uncertain_outcome', 'failed_attempt', 'initial_inventory_unknown',
           'unaccounted_asset', 'published_observation', 'incomplete_journal')
CLASSIFICATIONS = ('absent_reported', 'draft_empty_reported', 'draft_partial_reported',
                   'draft_complete_reported', 'published_complete_reported', 'collision',
                   'unknown', 'journal_consistent', 'journal_stopped', 'journal_conflict')


def optional_id(value):
    if value is not None:
        positive(value)


def optional_digest(value):
    if value is not None:
        sha(value, 64)


def filename(value):
    text(value, r'[A-Za-z0-9][A-Za-z0-9_.-]*', 'invalid_asset_name', 128)


def boundary(value):
    require(value.schema == SCHEMA and type(value.schema) is int, 'invalid_publication_schema')
    require(value.evidence_authentication == 'unverified'
            and value.execution_enabled is False and value.release_approved is False
            and value.publish_approved is False and value.snapshot_atomic is False,
            'publication_authority_forbidden')
    require(type(value.blockers) is tuple and value.blockers == BLOCKERS, 'missing_publication_blocker')


def fresh(value, cls):
    """Only reviewed exact classes reach the existing annotation-based codec."""
    require(any(cls is allowed for allowed in REVIEWED_RECORDS), 'invalid_publication_record')
    require(type(value) is cls, 'invalid_publication_record')
    return parse_json(cls, encode(value))


@dataclass(frozen=True)
class AssetSpec:
    name: str
    family: str
    media_type: str
    size: int
    sha256: str

    def __post_init__(self):
        choice(self.family, FAMILIES)
        filename(self.name)
        sha(self.sha256, 64)
        require(self.media_type == MEDIA[FAMILIES.index(self.family)], 'invalid_asset_media')
        if self.family in FAMILIES[:4]:
            PayloadObservation(self.name, self.family, self.size, self.sha256)
        else:
            positive(self.size)
            require(self.size <= (256 * 1024 if self.family == 'provenance' else 8192),
                    'evidence_asset_limit')


@dataclass(frozen=True)
class PublicationRecipe:
    source: SourceIdentity
    release_tag: str
    assets: tuple[AssetSpec, ...]
    notes_sha256: str
    consumer_plan_sha256: str
    schema: int = SCHEMA
    policy_revision: str = POLICY_REVISION
    evidence_authentication: str = 'unverified'
    execution_enabled: bool = False
    release_approved: bool = False
    publish_approved: bool = False
    snapshot_atomic: bool = False
    blockers: tuple[str, ...] = BLOCKERS

    def __post_init__(self):
        boundary(self)
        require(type(self.source) is SourceIdentity, 'invalid_recipe_source')
        require(self.policy_revision == POLICY_REVISION, 'invalid_publication_policy')
        require(self.release_tag == 'v' + self.source.version, 'invalid_recipe_tag')
        sequence(self.assets, AssetSpec, 6)
        expected = payload_names(self.source.version)
        names = tuple(expected[f] for f in FAMILIES[:4]) + (
            'RC_PROVENANCE.json', f'SHA256SUMS_{self.source.version}.txt')
        require(tuple(a.family for a in self.assets) == FAMILIES
                and tuple(a.name for a in self.assets) == names, 'invalid_recipe_inventory')
        sha(self.notes_sha256, 64)
        sha(self.consumer_plan_sha256, 64)


@dataclass(frozen=True)
class AssetObservation:
    asset_id: int
    name: str
    state: str
    media_type: str | None
    size: int | None
    sha256: str | None

    def __post_init__(self):
        positive(self.asset_id)
        filename(self.name)
        choice(self.state, ('uploaded', 'starter', 'unknown'))
        if self.media_type is not None:
            text(self.media_type, r'[a-z0-9][a-z0-9+./; =_-]*', 'invalid_observed_media', 128)
        if self.size is not None:
            require(type(self.size) is int and 0 <= self.size <= 2 * 1024**3, 'invalid_observed_size')
        optional_digest(self.sha256)


@dataclass(frozen=True)
class ReleaseObservation:
    source: SourceIdentity
    release_id: int
    tag: str
    reported_target_commitish: str | None
    draft: bool
    prerelease: bool
    notes_sha256: str
    assets: tuple[AssetObservation, ...]

    def __post_init__(self):
        require(type(self.source) is SourceIdentity, 'invalid_release_source')
        positive(self.release_id)
        filename(self.tag)
        if self.reported_target_commitish is not None:
            sha(self.reported_target_commitish)
        require(type(self.draft) is bool and type(self.prerelease) is bool, 'invalid_release_flags')
        sha(self.notes_sha256, 64)
        sequence(self.assets, AssetObservation, 16)


@dataclass(frozen=True)
class InventoryCheckpoint:
    source: SourceIdentity
    tag: str
    expected_release_id: int | None
    visibility: str
    completeness: str
    lookup: str
    releases: tuple[ReleaseObservation, ...]

    def __post_init__(self):
        require(type(self.source) is SourceIdentity, 'invalid_checkpoint_source')
        filename(self.tag)
        optional_id(self.expected_release_id)
        choice(self.visibility, ('reported_visible', 'denied', 'unknown'))
        choice(self.completeness, ('complete', 'incomplete', 'unknown'))
        choice(self.lookup, ('found', 'absent', 'inaccessible', 'unknown'))
        sequence(self.releases, ReleaseObservation, 2)
        require(bool(self.releases) == (self.lookup == 'found'), 'contradictory_inventory_lookup')


@dataclass(frozen=True)
class AttemptObservation:
    operation: str
    release_id: int | None
    asset_name: str | None
    outcome: str
    requested_draft: bool | None
    requested_prerelease: bool | None
    requested_make_latest: str | None
    response_release: ReleaseObservation | None
    response_asset: AssetObservation | None

    def __post_init__(self):
        choice(self.operation, ('create_draft', 'upload_asset', 'publish'))
        choice(self.outcome, ('prepared_only', 'response_success', 'response_failure', 'outcome_unknown'))
        optional_id(self.release_id)
        require((self.release_id is None) == (self.operation == 'create_draft'), 'invalid_attempt_target')
        if self.operation == 'upload_asset':
            filename(self.asset_name)
            require(self.requested_draft is None and self.requested_prerelease is None
                    and self.requested_make_latest is None and self.response_release is None,
                    'invalid_upload_intent')
        else:
            require(self.asset_name is None and self.response_asset is None
                    and self.requested_draft is (self.operation == 'create_draft')
                    and self.requested_prerelease is True and self.requested_make_latest == 'false',
                    'invalid_release_intent')
        require(self.response_release is None or type(self.response_release) is ReleaseObservation,
                'invalid_release_response')
        require(self.response_asset is None or type(self.response_asset) is AssetObservation,
                'invalid_asset_response')
        response = self.response_asset if self.operation == 'upload_asset' else self.response_release
        if self.outcome == 'response_success':
            require(response is not None, 'missing_success_response')
        if self.outcome == 'prepared_only':
            require(response is None, 'prepared_response_present')


@dataclass(frozen=True)
class JournalEntry:
    sequence: int
    kind: str
    attempt: AttemptObservation | None
    checkpoint: InventoryCheckpoint | None

    def __post_init__(self):
        positive(self.sequence)
        choice(self.kind, ('attempt', 'checkpoint'))
        require((self.kind == 'attempt' and type(self.attempt) is AttemptObservation
                 and self.checkpoint is None) or
                (self.kind == 'checkpoint' and type(self.checkpoint) is InventoryCheckpoint
                 and self.attempt is None), 'invalid_journal_entry')


@dataclass(frozen=True)
class JournalObservation:
    source: SourceIdentity
    recipe: PublicationRecipe
    recipe_fingerprint: str
    transaction_digest: str
    entries: tuple[JournalEntry, ...]
    schema: int = SCHEMA
    evidence_authentication: str = 'unverified'
    execution_enabled: bool = False
    release_approved: bool = False
    publish_approved: bool = False
    snapshot_atomic: bool = False
    blockers: tuple[str, ...] = BLOCKERS

    def __post_init__(self):
        boundary(self)
        require(type(self.source) is SourceIdentity and type(self.recipe) is PublicationRecipe
                and self.source == self.recipe.source, 'invalid_journal_source')
        sha(self.recipe_fingerprint, 64)
        sha(self.transaction_digest, 64)
        sequence(self.entries, JournalEntry, 32)
        require(bool(self.entries), 'empty_journal')


@dataclass(frozen=True)
class ObservationReport:
    classification: str
    reasons: tuple[str, ...]
    published_observed: bool = False
    uncertainty_observed: bool = False
    failed_observed: bool = False
    release_id: int | None = None
    accounted_asset_ids: tuple[int, ...] = ()
    observed_release_ids: tuple[int, ...] = ()
    observed_asset_ids: tuple[int, ...] = ()
    schema: int = SCHEMA
    evidence_authentication: str = 'unverified'
    execution_enabled: bool = False
    release_approved: bool = False
    publish_approved: bool = False
    snapshot_atomic: bool = False
    blockers: tuple[str, ...] = BLOCKERS

    def __post_init__(self):
        boundary(self)
        choice(self.classification, CLASSIFICATIONS)
        sequence(self.reasons, str, len(REASONS))
        require(len(set(self.reasons)) == len(self.reasons)
                and all(reason in REASONS for reason in self.reasons), 'invalid_report_reasons')
        for flag in (self.published_observed, self.uncertainty_observed, self.failed_observed):
            require(type(flag) is bool, 'invalid_observation_flag')
        optional_id(self.release_id)
        for values, bound in ((self.accounted_asset_ids, 6), (self.observed_release_ids, 64),
                              (self.observed_asset_ids, 128)):
            sequence(values, int, bound)
            require(len(set(values)) == len(values), 'duplicate_report_id')
            for value in values:
                positive(value)


REVIEWED_RECORDS = (AssetSpec, PublicationRecipe, AssetObservation, ReleaseObservation,
                    InventoryCheckpoint, AttemptObservation, JournalEntry,
                    JournalObservation, ObservationReport)
