"""Truthful pretag push admission; no receipt, version or manifest override."""
from dataclasses import dataclass
from pathlib import Path
import platform
import re
import subprocess
import sys
from urllib.error import HTTPError

import rc_consumer_snapshot as snapshot
from rc_consumer_io import ConsumerError, need
from rc_pretag_types import (SourceIdentity, InvocationIdentity, PreTagCandidate,
                            REPOSITORY, REPOSITORY_ID, POLICY_REVISION, RC)

gate = snapshot.gate
WORKFLOW = '.github/workflows/rc-pretag-evidence.yml'
JOB, JOB_NAME = 'collect', 'Collect pre-tag FINAL evidence (release remains blocked)'
REF = re.compile(r'refs/heads/release/rc-pretag-(' + RC + r')-[A-Za-z0-9]{8,64}')


@dataclass(frozen=True)
class Admitted:
    candidate: PreTagCandidate
    job_id: int
    run_number: int
    run_started_at: str
    run_created_at: str
    job_started_at: str

    @property
    def source(self):
        return self.candidate.source

    @property
    def invocation(self):
        return self.candidate.invocation


def tag_visibility(api, version):
    """Only the unchanged fixed-origin base GET retains typed HTTP errors."""
    need(type(version) is str and gate.rc.RC_VERSION.fullmatch(version), 'pretag_context_rejected')
    tag = 'v' + version
    try:
        value = gate.GitHub.get(api, '/git/ref/tags/' + tag)
    except HTTPError as error:
        code = error.code
        try:
            error.close()
        except Exception:
            raise ConsumerError('pretag_tag_visibility_failed') from None
        need(type(code) is int and code in (403, 404), 'pretag_tag_visibility_failed')
        return 'denied' if code == 403 else 'unknown'
    except Exception:
        raise ConsumerError('pretag_tag_visibility_failed') from None
    obj = value.get('object') if type(value) is dict else None
    need(type(value) is dict and value.get('ref') == 'refs/tags/' + tag
         and type(obj) is dict and obj.get('type') in ('commit', 'tag')
         and type(obj.get('sha')) is str and gate.rc.SHA.fullmatch(obj['sha']),
         'pretag_tag_response_invalid')
    raise ConsumerError('pretag_tag_collision')


def branch(api, ref, source):
    need(type(ref) is str and ref.startswith('refs/heads/') and '..' not in ref,
         'pretag_context_rejected')
    value = snapshot._call(api.get, '/git/ref/' + ref[5:])
    need(type(value) is dict and value.get('ref') == ref
         and type(value.get('object')) is dict and value['object'].get('type') == 'commit'
         and value['object'].get('sha') == source, 'pretag_source_rejected')


def _active_run(value, identity):
    record = snapshot._run(value, identity.source.repository_id)
    need(value['id'] == identity.run_id and value['run_attempt'] == identity.run_attempt
         and value['workflow_id'] == identity.workflow_id and value['head_sha'] == identity.source.source_sha
         and value['path'] == WORKFLOW and value['event'] == 'push'
         and value['head_branch'] == identity.ref.removeprefix('refs/heads/')
         and value['status'] == 'in_progress' and value['conclusion'] is None,
         'pretag_context_rejected')
    # updated_at is checked by _run, but it can legitimately advance while active.
    return tuple(value.get(k) for k in ('id', 'run_attempt', 'run_number', 'workflow_id',
                 'head_sha', 'path', 'event', 'head_branch', 'created_at', 'run_started_at'))


def admit(root, environment, api):
    need(sys.platform == 'linux' and platform.python_implementation() == 'CPython'
         and sys.version_info[:2] == (3, 12) and environment.get('RUNNER_OS') == 'Linux'
         and environment.get('GITHUB_ACTIONS') == 'true' and environment.get('GITHUB_JOB') == JOB,
         'pretag_context_rejected')
    ref = environment.get('GITHUB_REF', '')
    match = REF.fullmatch(ref) if type(ref) is str else None
    need(match is not None, 'pretag_context_rejected')
    version, source = match[1], environment.get('GITHUB_SHA')
    need(type(source) is str and gate.rc.SHA.fullmatch(source)
         and environment.get('GITHUB_EVENT_NAME') == 'push'
         and environment.get('GITHUB_REPOSITORY') == REPOSITORY
         and environment.get('GITHUB_WORKFLOW_SHA') == source
         and environment.get('GITHUB_WORKFLOW_REF') == REPOSITORY + '/' + WORKFLOW + '@' + ref,
         'pretag_context_rejected')
    repository_id, run_id, attempt = (snapshot._decimal(environment.get(k)) for k in
        ('GITHUB_REPOSITORY_ID', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
    need(repository_id == REPOSITORY_ID and 0 < run_id < 2**63 and 0 < attempt < 2**63,
         'pretag_context_rejected')
    try:
        proof = gate.rc.verify_source(root, expected_sha=source, expected_version=version)
        need(not gate.reviewed.git(root, 'ls-files', '--others', '-z'), 'pretag_source_rejected')
        workflow_blob = gate.reviewed.blob(root, source, WORKFLOW)
        need(workflow_blob is not None and workflow_blob['mode'] == '100644', 'pretag_source_rejected')
        tag = subprocess.run(['git', 'show-ref', '--verify', '--quiet', 'refs/tags/v' + version],
                             cwd=root, timeout=30, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        need(tag.returncode != 0, 'pretag_tag_collision')
        need(tag.returncode == 1, 'pretag_source_rejected')
        components = gate.cloud.versions(root, version)
        reviewed = gate.reviewed.verify(root, source)
        tree = gate.reviewed.git(root, 'rev-parse', '--verify', 'HEAD^{tree}').decode().strip()
        need(reviewed['source_tree'] == tree, 'pretag_source_rejected')
        source_identity = SourceIdentity(REPOSITORY, repository_id, source, tree, version)
    except ConsumerError:
        raise
    except Exception:
        raise ConsumerError('pretag_source_rejected') from None
    snapshot._repository(snapshot._call(api.get, '/'), repository_id)
    branch(api, ref, source)
    commit = snapshot._call(api.get, '/git/commits/' + source)
    need(type(commit) is dict and commit.get('sha') == source
         and type(commit.get('tree')) is dict and commit['tree'].get('sha') == tree,
         'pretag_source_rejected')
    workflow = snapshot._call(api.get, '/actions/workflows/' + Path(WORKFLOW).name)
    need(type(workflow) is dict and gate.positive(workflow.get('id'))
         and workflow['id'] < 2**63 and workflow.get('path') == WORKFLOW and workflow.get('state') == 'active',
         'pretag_context_rejected')
    identity = InvocationIdentity('pretag', source_identity, run_id, attempt, workflow['id'], WORKFLOW,
        environment['GITHUB_WORKFLOW_REF'], source, workflow_blob['blob_sha'], 'push', ref)
    run = snapshot._call(api.get, f'/actions/runs/{run_id}')
    fixed = _active_run(run, identity)
    exact = snapshot._call(api.get, f'/actions/runs/{run_id}/attempts/{attempt}')
    need(_active_run(exact, identity) == fixed, 'pretag_context_rejected')
    jobs = snapshot._call(gate.paginate, api, f'/actions/runs/{run_id}/attempts/{attempt}/jobs', 'jobs')
    need(len(jobs) == 1, 'pretag_context_rejected')
    job = jobs[0]
    need(gate.positive(job.get('id')) and job.get('name') == JOB_NAME
         and type(job.get('run_id')) is int and job['run_id'] == run_id
         and type(job.get('run_attempt')) is int and job['run_attempt'] == attempt
         and job.get('head_sha') == source and job.get('status') == 'in_progress'
         and job.get('conclusion') is None and job.get('completed_at') is None
         and snapshot._time(job.get('started_at')) >= snapshot._time(run['run_started_at']),
         'pretag_context_rejected')
    need(_active_run(snapshot._call(api.get, f'/actions/runs/{run_id}'), identity) == fixed,
         'pretag_context_rejected')
    visibility = tag_visibility(api, version)
    candidate = PreTagCandidate(source_identity, identity, 'v' + version, 'absent', 'absent',
        'unknown', visibility, True, tuple(proof['versions'].values()), components['coding-tools-cloud-gateway'],
        reviewed['manifest_blob']['blob_sha'], reviewed['manifest_blob']['sha256'], POLICY_REVISION, 'unverified')
    return Admitted(candidate, job['id'], run['run_number'], run['run_started_at'], run['created_at'], job['started_at'])


def discover(api, admitted):
    """Discovery returns expectations only; the strict shared selector follows."""
    source = admitted.source
    runs = [snapshot._call(gate.successful_run, api, path, source.source_sha, names) for path, names in
            ((gate.final.WORKFLOW, gate.final.REQUIRED_JOBS), (gate.FINAL_WORKFLOW, gate.FINAL_JOBS))]
    artifact = snapshot._call(gate.bundle_metadata, api, runs[1]['run'])
    return dict(rc_version=source.version, release_tag='v' + source.version, source_sha=source.source_sha,
        integration_run_id=runs[0]['run']['id'], integration_run_attempt=runs[0]['run']['run_attempt'],
        final_run_id=runs[1]['run']['id'], final_run_attempt=runs[1]['run']['run_attempt'], artifact_id=artifact['id'])


def projection(admitted):
    return dict(source_sha=admitted.source.source_sha, source_tree=admitted.source.source_tree,
                version=admitted.source.version)


def revalidate(api, root, environment, admitted, expectations, selection, metadata, producer):
    need(admit(root, environment, api) == admitted, 'pretag_freshness_rejected')
    current = snapshot._select_source_runs_for_identity(api, admitted.source.source_sha,
                                                       admitted.source.repository_id, expectations)
    need(current == selection, 'pretag_freshness_rejected')
    artifact = snapshot.authenticate_bundle_metadata(api, current, expectations['artifact_id'])
    need(artifact == metadata and snapshot.derive_final_producer(projection(admitted), current, artifact)
         == producer, 'pretag_freshness_rejected')
    branch(api, 'refs/heads/' + current['final_packaging']['run']['head_branch'], admitted.source.source_sha)
    need(admit(root, environment, api) == admitted, 'pretag_freshness_rejected')
