"""Read-only, exact-source first-attempt FINAL provenance snapshots.

Inputs are expectations, never authorities. Only live authenticated API reads and
the clean reviewed checkout construct TrustedProducer. No archive code runs here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import subprocess

import release_tag_gate as gate
from rc_consumer_io import ConsumerError, need

REPOSITORY = gate.REPOSITORY
CONSUMER_WORKFLOW = '.github/workflows/rc-artifact-consumer.yml'
BUNDLE_JOB = 'Collect exact-source packaging evidence (release remains blocked)'
CANDIDATE_BRANCH = re.compile(r'release/full-rc-candidate-[A-Za-z0-9][A-Za-z0-9._-]*')
SHA256 = re.compile(r'sha256:([0-9a-f]{64})')
MAX_ARTIFACT_BYTES = 2 * 1024**3
RUN_FIELDS = (*gate.SNAPSHOT_FIELDS, 'event', 'head_branch', 'created_at')
JOB_FIELDS = ('id', 'run_id', 'run_attempt', 'name', 'head_sha', 'status',
              'conclusion', 'started_at', 'completed_at')
ARTIFACT_FIELDS = ('id', 'name', 'size_in_bytes', 'digest', 'expired', 'created_at',
                   'updated_at', 'expires_at', 'workflow_run')
EXPECTATIONS = {'rc_version', 'release_tag', 'source_sha', 'final_run_id',
                'final_run_attempt', 'integration_run_id', 'integration_run_attempt', 'artifact_id'}


@dataclass(frozen=True)
class TrustedProducer:
    repository: str
    repository_id: int
    source_sha: str
    source_tree: str
    version: str
    run_id: int
    run_attempt: int
    workflow_ref: str
    workflow_id: int
    bundle_job_id: int
    bundle_job_started_at: str
    bundle_job_completed_at: str
    artifact_id: int
    artifact_sha256: str
    artifact_size: int


def _finite(value, depth=0):
    need(depth <= 64, 'api_structure_limit')
    if isinstance(value, float):
        need(math.isfinite(value), 'nonfinite_api_number')
    elif isinstance(value, dict):
        for item in value.values():
            _finite(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _finite(item, depth + 1)


def _call(function, *args, **kwargs):
    """Do not allow helper/API errors or arbitrary raw bodies into output."""
    try:
        return function(*args, **kwargs)
    except ConsumerError:
        raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError,
            OverflowError, RecursionError, subprocess.SubprocessError):
        raise ConsumerError('invalid_snapshot') from None


class GitHub(gate.GitHub):
    """Unchanged fixed-origin GET transport, with bounded sanitized failures."""
    def get(self, suffix):
        need(type(suffix) is str and re.fullmatch(r'/[A-Za-z0-9_./?=&-]*', suffix)
             is not None and '..' not in suffix and not suffix.startswith('//'), 'invalid_api_path')
        value = _call(_repository_metadata, self.token) if suffix == '/' else _call(super().get, suffix)
        _finite(value)
        return value


def _repository_metadata(token):
    # The old helper requires a slash-prefixed suffix; the repository endpoint
    # has no trailing slash. Retain its exact token/origin/redirect/size policy.
    class NoRedirect(gate.urllib.request.HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, msg, headers, newurl):
            raise ConsumerError('unexpected_api_redirect')
    request = gate.urllib.request.Request('https://api.github.com/repos/' + REPOSITORY,
        headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
                 'X-GitHub-Api-Version': '2022-11-28'}, method='GET')
    with gate.urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
        raw = response.read(gate.MAX_RESPONSE_BYTES + 1)
    need(len(raw) <= gate.MAX_RESPONSE_BYTES, 'api_response_limit')
    value = json.loads(raw, object_pairs_hook=gate.reviewed.unique,
                       parse_constant=lambda _: (_ for _ in ()).throw(ConsumerError('nonfinite_api_number')))
    need(type(value) is dict, 'invalid_api_object')
    return value


def _time(value):
    return _call(gate.timestamp, value)


def _decimal(value):
    need(type(value) is str and re.fullmatch(r'[1-9][0-9]{0,19}', value) is not None,
         'invalid_consumer_identity')
    return int(value)


def _inputs(expectations):
    need(type(expectations) is dict and set(expectations) == EXPECTATIONS, 'invalid_expectations')
    for key in EXPECTATIONS - {'rc_version', 'release_tag', 'source_sha'}:
        need(gate.positive(expectations[key]), 'invalid_expected_id')
    need(expectations['final_run_attempt'] == 1, 'unsupported_rerun_provenance')
    version, source = expectations['rc_version'], expectations['source_sha']
    need(type(version) is str and gate.rc.RC_VERSION.fullmatch(version) is not None,
         'invalid_rc_version')
    need(type(source) is str and gate.rc.SHA.fullmatch(source) is not None, 'invalid_source_sha')
    need(expectations['release_tag'] == 'v' + version, 'invalid_release_tag')


def _live_tag(api, tag, source):
    # The old helper permits annotations; this new boundary deliberately does not.
    value = _call(api.get, '/git/ref/tags/' + tag)
    need(type(value) is dict and value.get('ref') == 'refs/tags/' + tag
         and type(value.get('object')) is dict and value['object'].get('type') == 'commit'
         and value['object'].get('sha') == source, 'lightweight_tag_required')
    _call(gate.live_tag, api, tag, source, source)


def resolve_candidate(root: Path, expectations: dict, environment: dict, api) -> dict:
    _inputs(expectations)
    source, version, tag = (expectations[k] for k in ('source_sha', 'rc_version', 'release_tag'))
    ref = environment.get('GITHUB_REF', '')
    need(type(ref) is str and re.fullmatch(r'refs/(heads|tags)/[A-Za-z0-9][A-Za-z0-9/._-]*', ref)
         is not None and '..' not in ref and not ref.endswith('/'), 'invalid_consumer_ref')
    workflow_ref = REPOSITORY + '/' + CONSUMER_WORKFLOW + '@' + ref
    need(environment.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'
         and environment.get('GITHUB_REPOSITORY') == REPOSITORY
         and environment.get('GITHUB_SHA') == source
         and environment.get('GITHUB_WORKFLOW_SHA') == source
         and environment.get('GITHUB_WORKFLOW_REF') == workflow_ref, 'invalid_consumer_identity')
    consumer = dict(repository=REPOSITORY, repository_id=_decimal(environment.get('GITHUB_REPOSITORY_ID')),
                    run_id=_decimal(environment.get('GITHUB_RUN_ID')),
                    run_attempt=_decimal(environment.get('GITHUB_RUN_ATTEMPT')),
                    workflow_ref=workflow_ref, source_sha=source, event='workflow_dispatch')
    proof = _call(gate.rc.verify_source, root, expected_sha=source, expected_version=version)
    need(not _call(gate.reviewed.git, root, 'ls-files', '--others', '-z'), 'untracked_source')
    workflow = _call(gate.reviewed.blob, root, source, CONSUMER_WORKFLOW)
    need(workflow is not None and workflow['mode'] == '100644', 'consumer_workflow_missing')
    local_tag = _call(gate.reviewed.git, root, 'rev-parse', '--verify', 'refs/tags/' + tag).decode().strip()
    kind = _call(gate.reviewed.git, root, 'cat-file', '-t', 'refs/tags/' + tag).decode().strip()
    need(local_tag == source and kind == 'commit', 'lightweight_tag_required')
    components = _call(gate.cloud.versions, root, version)
    reviewed = _call(gate.reviewed.verify, root, source)
    tree = _call(gate.reviewed.git, root, 'rev-parse', '--verify', 'HEAD^{tree}').decode().strip()
    need(gate.rc.SHA.fullmatch(tree) is not None and reviewed.get('source_tree') == tree,
         'invalid_source_tree')
    _live_tag(api, tag, source)
    return dict(source_sha=source, source_tree=tree, version=version, release_tag=tag,
                tag_object_sha=local_tag, consumer=consumer, source_proof=proof,
                component_versions=components, reviewed_source=reviewed)


def _repository(value, expected_id=None):
    need(type(value) is dict and value.get('full_name') == REPOSITORY
         and gate.positive(value.get('id')), 'repository_identity_mismatch')
    need(expected_id is None or value['id'] == expected_id, 'repository_identity_mismatch')
    return value['id']


def _run(value, repository_id):
    need(type(value) is dict, 'invalid_run')
    for key in ('id', 'run_attempt', 'run_number', 'workflow_id'):
        need(gate.positive(value.get(key)), 'invalid_run_id')
    _repository(value.get('repository'), repository_id)
    _repository(value.get('head_repository'), repository_id)
    need(type(value.get('event')) is str and type(value.get('head_branch')) is str, 'invalid_run_context')
    need(_time(value.get('created_at')) <= _time(value.get('run_started_at'))
         <= _time(value.get('updated_at')), 'invalid_run_time')
    return {key: value.get(key) for key in RUN_FIELDS}


class _ObservedAPI:
    """Compare extra immutable fields across *every* old-helper API read."""
    def __init__(self, api, repository_id):
        self.api, self.repository_id, self.runs = api, repository_id, {}

    def get(self, path):
        value = _call(self.api.get, path)
        need(type(value) is dict, 'invalid_api_object')
        _finite(value)
        runs = value.get('workflow_runs', []) if '/runs?' in path else []
        if re.fullmatch(r'/actions/runs/[1-9][0-9]*', path):
            runs = [value]
            # successful_run fetches the selected ID after complete pagination,
            # before its success check. Historical, unselected reruns are fine.
            if value.get('path') == gate.FINAL_WORKFLOW:
                need(type(value.get('run_attempt')) is int and value['run_attempt'] == 1,
                     'unsupported_rerun_provenance')
        need(type(runs) is list, 'invalid_run_list')
        for run in runs:
            record = _run(run, self.repository_id)
            old = self.runs.setdefault(run['id'], record)
            if record['path'] == gate.FINAL_WORKFLOW and old['run_attempt'] == 1:
                need(record['run_attempt'] == 1, 'unsupported_rerun_provenance')
            need(old == record, 'run_snapshot_changed')
        return value


def _strict_run(evidence, repository_id, source, expected_id, expected_attempt, final=False):
    run = evidence['run']
    record = _run(run, repository_id)
    need(run['id'] == expected_id and run['run_attempt'] == expected_attempt, 'selected_run_mismatch')
    if final:
        need(run['run_attempt'] == 1, 'unsupported_rerun_provenance')
        need(run.get('event') == 'push' and CANDIDATE_BRANCH.fullmatch(run.get('head_branch', ''))
             is not None, 'unsupported_final_producer')
    jobs = []
    for job in evidence['jobs']:
        need(gate.positive(job.get('id')), 'invalid_job_id')
        start, end = _time(job.get('started_at')), _time(job.get('completed_at'))
        need(_time(run['run_started_at']) <= start <= end <= _time(run['updated_at']),
             'attempt_binding_unproven')
        jobs.append({key: job.get(key) for key in JOB_FIELDS})
    # Keep only authenticated fields needed by data validators and final fences.
    workflow = {key: evidence['workflow'][key] for key in ('id', 'path')}
    return dict(run=record, workflow=workflow, jobs=sorted(jobs, key=lambda j: j['id']))


def select_source_runs(api, candidate: dict, expectations: dict) -> dict:
    _inputs(expectations)
    need(candidate['source_sha'] == expectations['source_sha'], 'candidate_source_mismatch')
    repository = _call(api.get, '/')
    repository_id = _repository(repository, candidate['consumer']['repository_id'])
    observed = _ObservedAPI(api, repository_id)
    source = candidate['source_sha']
    result = dict(repository_id=repository_id)
    for key, prefix, path, names in (
            ('integration', 'integration', gate.final.WORKFLOW, gate.final.REQUIRED_JOBS),
            ('final_packaging', 'final', gate.FINAL_WORKFLOW, gate.FINAL_JOBS)):
        evidence = _call(gate.successful_run, observed, path, source, names)
        result[key] = _strict_run(evidence, repository_id, source, expectations[prefix + '_run_id'],
                                  expectations[prefix + '_run_attempt'], final=prefix == 'final')
        latest = _call(gate.latest_run, observed, evidence['workflow'], source)
        if prefix == 'final':
            need(latest['run_attempt'] == 1, 'unsupported_rerun_provenance')
        need(_run(latest, repository_id) == result[key]['run'], 'run_snapshot_changed')
    return result


def _artifact(value, selection, expected_id):
    need(type(value) is dict and gate.positive(value.get('id')) and value['id'] == expected_id
         and value.get('name') == 'rc-structural-bundle', 'artifact_identity_mismatch')
    run = selection['final_packaging']['run']
    owner = value.get('workflow_run')
    need(type(owner) is dict and type(owner.get('id')) is int and owner['id'] == run['id']
         and owner.get('head_sha') == run['head_sha'] and owner.get('head_branch') == run['head_branch'],
         'artifact_run_mismatch')
    for key in ('repository_id', 'head_repository_id'):
        need(type(owner.get(key)) is int and owner[key] == selection['repository_id'],
             'artifact_repository_mismatch')
    need(value.get('expired') is False and gate.positive(value.get('size_in_bytes'))
         and value['size_in_bytes'] <= MAX_ARTIFACT_BYTES, 'invalid_artifact_size_or_expiry')
    digest = value.get('digest')
    need(type(digest) is str and SHA256.fullmatch(digest) is not None, 'artifact_digest_required')
    jobs = [job for job in selection['final_packaging']['jobs'] if job['name'] == BUNDLE_JOB]
    need(len(jobs) == 1, 'attempt_binding_unproven')
    job = jobs[0]
    created, updated, expires = (_time(value.get(key)) for key in ('created_at', 'updated_at', 'expires_at'))
    need(_time(job['started_at']) <= created <= _time(job['completed_at']) and updated >= created,
         'attempt_binding_unproven')
    need(expires > datetime.now(timezone.utc) and expires > updated, 'artifact_expired')
    record = {key: value.get(key) for key in ARTIFACT_FIELDS}
    record['workflow_run'] = {key: owner.get(key) for key in
                              ('id', 'repository_id', 'head_repository_id', 'head_sha', 'head_branch')}
    return record


def authenticate_bundle_metadata(api, selection: dict, artifact_id: int) -> dict:
    need(gate.positive(artifact_id), 'invalid_expected_id')
    run = selection['final_packaging']['run']
    need(run['run_attempt'] == 1, 'unsupported_rerun_provenance')
    # Preserve the old baseline while independently retaining all strict fields.
    baseline = _call(gate.bundle_metadata, api, run)
    artifacts = _call(gate.paginate, api, f"/actions/runs/{run['id']}/artifacts", 'artifacts')
    matches = [a for a in artifacts if a.get('name') == 'rc-structural-bundle']
    need(len(matches) == 1, 'artifact_inventory_mismatch')
    listed = _artifact(matches[0], selection, artifact_id)
    need(all(baseline[key] == listed[key] for key in
             ('id', 'name', 'size_in_bytes', 'digest', 'created_at', 'expires_at')), 'artifact_snapshot_changed')
    direct = _artifact(_call(api.get, f'/actions/artifacts/{artifact_id}'), selection, artifact_id)
    need(listed == direct, 'artifact_snapshot_changed')
    return direct


def derive_final_producer(candidate: dict, selection: dict, artifact: dict) -> TrustedProducer:
    run = selection['final_packaging']['run']
    need(run['run_attempt'] == 1, 'unsupported_rerun_provenance')
    need(run['event'] == 'push' and CANDIDATE_BRANCH.fullmatch(run['head_branch']) is not None,
         'unsupported_final_producer')
    job = next(j for j in selection['final_packaging']['jobs'] if j['name'] == BUNDLE_JOB)
    return TrustedProducer(REPOSITORY, selection['repository_id'], candidate['source_sha'],
                           candidate['source_tree'], candidate['version'], run['id'], run['run_attempt'],
                           REPOSITORY + '/' + gate.FINAL_WORKFLOW + '@refs/heads/' + run['head_branch'],
                           run['workflow_id'], job['id'], job['started_at'], job['completed_at'],
                           artifact['id'], artifact['digest'][7:], artifact['size_in_bytes'])


def revalidate_download(api, selection: dict, artifact: dict) -> None:
    run = selection['final_packaging']['run']
    current = _call(api.get, f"/actions/runs/{run['id']}")
    need(current.get('run_attempt') == 1 and type(current.get('run_attempt')) is int,
         'unsupported_rerun_provenance')
    need(_run(current, selection['repository_id']) == run, 'run_snapshot_changed')
    current_artifact = _artifact(_call(api.get, f"/actions/artifacts/{artifact['id']}"),
                                 selection, artifact['id'])
    need(current_artifact == artifact, 'artifact_snapshot_changed')


def revalidate_snapshot(api, root: Path, expectations: dict, environment: dict, snapshot: dict) -> None:
    candidate = resolve_candidate(root, expectations, environment, api)
    need(candidate == snapshot['candidate'], 'candidate_snapshot_changed')
    selection = select_source_runs(api, candidate, expectations)
    need(selection == snapshot['selection'], 'selection_snapshot_changed')
    artifact = authenticate_bundle_metadata(api, selection, expectations['artifact_id'])
    need(artifact == snapshot['artifact'], 'artifact_snapshot_changed')
    need(derive_final_producer(candidate, selection, artifact) == snapshot['producer'],
         'producer_snapshot_changed')
    need(resolve_candidate(root, expectations, environment, api) == candidate,
         'candidate_snapshot_changed')
