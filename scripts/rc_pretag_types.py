"""Strict data-only pre-tag identities. Parsing does not authenticate evidence.

There is deliberately no environment, Git, network, collector or CLI entrypoint.
These immutable records describe observations; they cannot grant release rights.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields, is_dataclass
from datetime import datetime
import json
import re
import types
from typing import get_args, get_origin, get_type_hints

REPOSITORY = 'Eswink/coding-tools-mcp'
REPOSITORY_ID = 1360355522
POLICY_REVISION = 'rc-pretag-contract-v1'
RC = r'(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)-rc\.(?:0|[1-9][0-9]*)'
WORKFLOWS = {
    'pretag': '.github/workflows/rc-pretag-evidence.yml',
    'integration': '.github/workflows/dot-rc-integration.yml',
    'final': '.github/workflows/final-rc-packages.yml',
    'consumer': '.github/workflows/rc-artifact-consumer.yml',
}
PERMISSIONS = ('contents:read', 'actions:read', 'pull-requests:read')
MAX_JSON_BYTES = 256 * 1024


class ContractError(ValueError):
    """Fixed-code error; never echo caller-supplied strings."""


def require(condition, code):
    if not condition:
        raise ContractError(code)


def text(value, pattern, code, limit=256):
    require(type(value) is str and len(value) <= limit
            and re.fullmatch(pattern, value) is not None, code)


def positive(value):
    require(type(value) is int and 0 < value < 2**63, 'invalid_positive_integer')


def sha(value, length=40):
    text(value, '[0-9a-f]{' + str(length) + '}', 'invalid_digest', length)


def choice(value, choices, code='invalid_enum'):
    require(type(value) is str and value in choices, code)


def sequence(value, cls, limit):
    require(type(value) is tuple and len(value) <= limit
            and all(type(item) is cls for item in value), 'invalid_sequence')


def timestamp(value):
    text(value, r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', 'invalid_timestamp', 20)
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise ContractError('invalid_timestamp') from None


def decode(cls, value):
    """Exact dataclass schema, with no coercion or extension fields."""
    require(type(value) is dict and set(value) == {f.name for f in fields(cls)},
            'invalid_record_fields')
    hints = get_type_hints(cls)

    def convert(kind, item):
        origin, args = get_origin(kind), get_args(kind)
        if origin is types.UnionType:
            require(len(args) == 2 and type(None) in args, 'invalid_schema_union')
            return None if item is None else convert(next(a for a in args if a is not type(None)), item)
        if origin is tuple:
            require(type(item) is list and len(item) <= 128, 'invalid_array')
            return tuple(convert(args[0], child) for child in item)
        if is_dataclass(kind):
            return decode(kind, item)
        require(type(item) is kind, 'invalid_field_type')
        return item

    return cls(**{name: convert(hints[name], item) for name, item in value.items()})


def parse_json(cls, raw):
    require(type(raw) is bytes and len(raw) <= MAX_JSON_BYTES, 'invalid_json_size')

    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'duplicate_json_key')
            result[key] = value
        return result

    def finite(_):
        raise ContractError('nonfinite_json')

    def bounded(value, depth=0):
        require(depth <= 16, 'json_depth_limit')
        if type(value) is dict:
            require(len(value) <= 128, 'json_object_limit')
            for item in value.values():
                bounded(item, depth + 1)
        elif type(value) is list:
            require(len(value) <= 128, 'json_array_limit')
            for item in value:
                bounded(item, depth + 1)
        elif type(value) is str:
            require(len(value) <= 512, 'json_string_limit')

    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=unique, parse_constant=finite)
        bounded(value)
        return decode(cls, value)
    except ContractError:
        raise
    except (UnicodeError, ValueError, RecursionError, OverflowError):
        raise ContractError('invalid_json') from None


def encode(record):
    """Re-decode serialized fields to enforce constructor and nested invariants."""
    raw = (json.dumps(asdict(record), sort_keys=True, separators=(',', ':'),
                      allow_nan=False) + '\n').encode('utf-8')
    parse_json(type(record), raw)
    return raw


@dataclass(frozen=True)
class SourceIdentity:
    repository: str
    repository_id: int
    source_sha: str
    source_tree: str
    version: str

    def __post_init__(self):
        require(type(self.repository) is str and self.repository == REPOSITORY,
                'wrong_repository')
        positive(self.repository_id)
        require(self.repository_id == REPOSITORY_ID, 'wrong_repository_id')
        sha(self.source_sha)
        sha(self.source_tree)
        text(self.version, RC, 'invalid_rc_version', 80)


@dataclass(frozen=True)
class InvocationIdentity:
    role: str
    source: SourceIdentity
    run_id: int
    run_attempt: int
    workflow_id: int
    workflow_path: str
    workflow_ref: str
    workflow_sha: str
    workflow_blob: str
    event: str
    ref: str

    def __post_init__(self):
        require(type(self.source) is SourceIdentity, 'invalid_source_identity')
        choice(self.role, WORKFLOWS)
        for value in (self.run_id, self.run_attempt, self.workflow_id):
            positive(value)
        sha(self.workflow_sha)
        sha(self.workflow_blob)
        require(self.workflow_sha == self.source.source_sha, 'workflow_source_mismatch')
        require(self.workflow_path == WORKFLOWS[self.role], 'wrong_workflow')
        if self.role == 'integration' and self.event == 'pull_request':
            text(self.ref, r'refs/pull/[1-9][0-9]{0,18}/merge', 'invalid_integration_pr_ref')
            positive(int(self.ref.split('/')[2]))
        else:
            text(self.ref, r'refs/(?:heads|tags)/[A-Za-z0-9][A-Za-z0-9/._-]*', 'invalid_ref')
        require('..' not in self.ref and not self.ref.endswith(('/', '.'))
                and '//' not in self.ref, 'invalid_ref')
        require(self.workflow_ref == REPOSITORY + '/' + self.workflow_path + '@' + self.ref,
                'workflow_ref_mismatch')
        if self.role == 'pretag':
            require(self.event == 'push', 'pretag_push_required')
            pattern = 'refs/heads/release/rc-pretag-' + re.escape(self.source.version)
            text(self.ref, pattern + r'-[A-Za-z0-9]{8,64}', 'invalid_pretag_ref')
        elif self.role == 'final':
            require(self.event == 'push' and self.run_attempt == 1, 'final_attempt1_push_required')
            text(self.ref, r'refs/heads/release/full-rc-candidate-[A-Za-z0-9][A-Za-z0-9._-]*',
                 'invalid_final_ref')
        elif self.role == 'consumer':
            require(self.event == 'workflow_dispatch', 'consumer_dispatch_required')
        else:
            choice(self.event, ('push', 'pull_request', 'workflow_dispatch'))
            require(self.event != 'push' or self.ref.startswith('refs/heads/'),
                    'integration_push_branch_required')


@dataclass(frozen=True)
class PreTagCandidate:
    source: SourceIdentity
    invocation: InvocationIdentity
    prospective_tag: str
    tag_state: str
    local_tag_observation: str
    remote_tag_observation: str
    tag_visibility: str
    clean_source_observation: bool
    desktop_versions: tuple[str, ...]
    gateway_version: str
    reviewed_manifest_blob: str
    reviewed_manifest_sha256: str
    policy_revision: str
    evidence_authentication: str

    def __post_init__(self):
        require(type(self.source) is SourceIdentity and type(self.invocation) is InvocationIdentity,
                'invalid_candidate_identity')
        require(self.invocation.role == 'pretag' and self.invocation.source == self.source,
                'candidate_invocation_mismatch')
        require(self.prospective_tag == 'v' + self.source.version, 'wrong_prospective_tag')
        choice(self.tag_state, ('absent',))
        choice(self.local_tag_observation, ('absent',))
        choice(self.remote_tag_observation, ('absent', 'unknown'))
        choice(self.tag_visibility, ('observed', 'unknown', 'denied'))
        require(self.remote_tag_observation != 'absent' or self.tag_visibility == 'observed',
                'tag_absence_visibility_unproven')
        require(self.clean_source_observation is True, 'unclean_source_observation')
        sequence(self.desktop_versions, str, 6)
        require(len(self.desktop_versions) == 6 and
                all(v == self.source.version for v in self.desktop_versions)
                and self.gateway_version == self.source.version, 'version_observation_mismatch')
        sha(self.reviewed_manifest_blob)
        sha(self.reviewed_manifest_sha256, 64)
        require(self.policy_revision == POLICY_REVISION, 'unsupported_policy_revision')
        choice(self.evidence_authentication, ('unverified',))
