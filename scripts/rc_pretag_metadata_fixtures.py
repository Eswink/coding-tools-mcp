"""Synthetic, credential-free metadata fixtures; never release evidence."""
from copy import deepcopy
from dataclasses import dataclass
import json

from rc_pretag_evidence import FINAL_JOBS, INTEGRATION_JOBS
from rc_pretag_types import REPOSITORY, REPOSITORY_ID, SourceIdentity, WORKFLOWS
from rc_pretag_metadata_types import (ENGINEERING_REF, MetadataObservation,
                                    MetadataReceipt, MetadataRecord, MetadataRequest)

SOURCE = SourceIdentity(REPOSITORY, REPOSITORY_ID, 'a' * 40, 'b' * 40, '1.2.3-rc.7')
REQUEST = MetadataRequest(SOURCE, 'refs/heads/release/full-rc-candidate-fixture')
BEGIN = '2026-10-01T00:00:00Z'
START = '2026-10-01T00:01:00Z'
END = '2026-10-01T00:04:00Z'
TREE_SHAS = (SOURCE.source_tree, 'c' * 40, 'd' * 40)
WORKFLOW_IDS = {'integration': 101, 'final': 201}
BLOBS = {'integration': 'e' * 40, 'final': 'f' * 40, 'pretag': '1' * 40}
RUN_IDS = {'integration': 100, 'final': 200}


def receipt():
    row = MetadataRecord('repository', str(REPOSITORY_ID), repository_id=REPOSITORY_ID)
    observation = MetadataObservation('repository', 'observed', 'observed', 1,
                                      '2' * 64, (row,))
    return MetadataReceipt(REQUEST, (observation,), None, BEGIN, END,
                           1, 100, 'synthetic', 'partial')


def repository():
    return {'id': REPOSITORY_ID, 'full_name': REPOSITORY}


def ref():
    return {'ref': REQUEST.source_ref, 'object': {'type': 'commit', 'sha': SOURCE.source_sha}}


def commit():
    return {'sha': SOURCE.source_sha, 'tree': {'sha': SOURCE.source_tree}}


def tree(index=0):
    if index < 2:
        entries = [{'path': ('.github', 'workflows')[index], 'mode': '040000',
                    'type': 'tree', 'sha': TREE_SHAS[index + 1]}]
    else:
        entries = [{'path': WORKFLOWS[role].rsplit('/', 1)[-1], 'mode': '100644',
                    'type': 'blob', 'sha': BLOBS[role]}
                   for role in ('integration', 'final', 'pretag')]
    return {'sha': TREE_SHAS[index], 'truncated': False, 'tree': entries}


def workflow(role='integration'):
    return {'id': WORKFLOW_IDS[role], 'path': WORKFLOWS[role], 'state': 'active'}


def run(role='integration', attempt=None, status='completed', conclusion='success'):
    attempt = (3 if role == 'integration' else 1) if attempt is None else attempt
    return {'id': RUN_IDS[role], 'workflow_id': WORKFLOW_IDS[role],
            'run_number': 12, 'run_attempt': attempt, 'head_sha': SOURCE.source_sha,
            'head_branch': REQUEST.source_ref.removeprefix('refs/heads/'),
            'repository': repository(), 'head_repository': repository(),
            'path': WORKFLOWS[role], 'event': 'push', 'status': status,
            'conclusion': conclusion, 'created_at': BEGIN,
            'run_started_at': START if status != 'queued' else None, 'updated_at': END}


def jobs(role='integration', attempt=None):
    attempt = (3 if role == 'integration' else 1) if attempt is None else attempt
    names = INTEGRATION_JOBS if role == 'integration' else FINAL_JOBS
    values = [{'id': (1000 if role == 'integration' else 2000) + index,
               'run_id': RUN_IDS[role], 'run_attempt': attempt, 'head_sha': SOURCE.source_sha,
               'name': name, 'status': 'completed', 'conclusion': 'success',
               'started_at': START, 'completed_at': END}
              for index, name in enumerate(sorted(names))]
    return {'total_count': len(values), 'jobs': values}


def pull_request():
    return {'number': 36, 'id': 360, 'state': 'open', 'merged': False, 'updated_at': END,
            'head': {'sha': SOURCE.source_sha, 'repo': repository()},
            'base': {'sha': '2' * 40, 'repo': repository()},
            'merge_commit_sha': '3' * 40, 'commits': 1}


def reviews():
    return [{'id': 700, 'user': {'id': 70}, 'state': 'APPROVED',
             'commit_id': SOURCE.source_sha, 'submitted_at': END}]


def commits():
    return [{'sha': SOURCE.source_sha}]


@dataclass(frozen=True)
class FixtureResponse:
    value: dict | list
    link: str | None = None
    byte_count: int = 100


class FixtureAPI:
    """In-memory endpoint transcript with optional response-transform callback.

    The hook receives operation, keyword arguments, occurrence, and a fresh value.
    It may return a replacement value/FixtureResponse or raise a fixed-code error.
    No URL, token, file, subprocess or network access exists in this fake.
    """

    channel = 'synthetic'

    def __init__(self, transform=None):
        self.transform = transform
        self.request_count = 0
        self.response_bytes = 0
        self.calls = []
        self.closed = False

    def get(self, operation, **kwargs):
        if self.closed:
            raise AssertionError('fixture_used_after_close')
        self.calls.append((operation, dict(kwargs)))
        self.request_count += 1
        occurrence = sum(op == operation and args == kwargs for op, args in self.calls)
        value = deepcopy(self._value(operation, kwargs))
        if self.transform is not None:
            value = self.transform(operation, dict(kwargs), occurrence, value)
        response = value if isinstance(value, FixtureResponse) else FixtureResponse(
            value, None, len(json.dumps(value, separators=(',', ':')).encode('utf-8')))
        self.response_bytes += response.byte_count
        return response

    def _value(self, operation, arguments):
        if operation == 'repository':
            return repository()
        if operation == 'ref':
            return ref()
        if operation == 'commit':
            return commit()
        if operation == 'tree':
            return tree(TREE_SHAS.index(arguments.get('sha')))
        if operation == 'workflow':
            return workflow(arguments.get('role'))
        role = 'integration' if arguments.get('workflow_id') == 101 or arguments.get('run_id') == 100 else 'final'
        if operation == 'runs':
            return {'total_count': 1, 'workflow_runs': [run(role)]}
        if operation == 'run':
            return run(role)
        if operation == 'jobs':
            return jobs(role)
        if operation == 'pr':
            return pull_request()
        if operation == 'reviews':
            return reviews() if arguments.get('page', 1) == 1 else []
        if operation == 'commits':
            return commits() if arguments.get('page', 1) == 1 else []
        raise AssertionError('unknown_fixture_operation')

    def close(self):
        self.closed = True
