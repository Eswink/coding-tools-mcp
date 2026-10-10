"""Synthetic snapshot fixtures only. Never a producer or release acceptance proof."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import rc_consumer_snapshot as snapshot
from source_provenance_gate_tests import command, commit, repository

SOURCE = 'a' * 40
VERSION = '1.2.3-rc.4'
TAG = 'v' + VERSION
REPOSITORY_ID = 1234


def expectations(source=SOURCE):
    return dict(rc_version=VERSION, release_tag=TAG, source_sha=source,
                final_run_id=102, final_run_attempt=1, integration_run_id=101,
                integration_run_attempt=2, artifact_id=600)


def environment(source=SOURCE):
    ref = 'refs/heads/release/full-rc-candidate-fixture'
    return dict(GITHUB_EVENT_NAME='workflow_dispatch', GITHUB_REPOSITORY=snapshot.REPOSITORY,
                GITHUB_REPOSITORY_ID=str(REPOSITORY_ID), GITHUB_SHA=source, GITHUB_WORKFLOW_SHA=source,
                GITHUB_WORKFLOW_REF=snapshot.REPOSITORY + '/' + snapshot.CONSUMER_WORKFLOW + '@' + ref,
                GITHUB_REF=ref, GITHUB_RUN_ID='900', GITHUB_RUN_ATTEMPT='3')


def candidate(source=SOURCE):
    return dict(source_sha=source, source_tree='c' * 40, version=VERSION,
                consumer=dict(repository_id=REPOSITORY_ID))


def source_tree(root):
    repository(root)
    for folder in ('cloud-gateway', 'cloud-agent', 'local-agent'):
        base = root / 'services' / folder
        base.mkdir(parents=True)
        version = VERSION if folder == 'cloud-gateway' else '0.1.0'
        name = 'coding-tools-' + folder
        (base / 'Cargo.toml').write_text(f'[package]\nname="{name}"\nversion="{version}"\n')
        (base / 'Cargo.lock').write_text(f'[[package]]\nname="{name}"\nversion="{version}"\n')
    path = root / snapshot.CONSUMER_WORKFLOW
    path.parent.mkdir(parents=True)
    path.write_text('name: Synthetic consumer fixture\non: workflow_dispatch\n')
    baseline = commit(root)
    path = root / snapshot.gate.reviewed.MANIFEST
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(dict(schema=1, base_commit=baseline, version=VERSION,
                                   review_reference='Synthetic consumer unit fixture only', entries=[])))
    source = commit(root)
    command(root, 'tag', TAG)
    return baseline, source


class API:
    """Exact-route, deep-copy read transport; mutation belongs only in tests."""
    def __init__(self, source=SOURCE):
        self.calls, self.data, self.source = [], {}, source
        self.data['/'] = dict(id=REPOSITORY_ID, full_name=snapshot.REPOSITORY)
        self.data['/git/ref/tags/' + TAG] = dict(ref='refs/tags/' + TAG,
                                               object=dict(sha=source, type='commit'))
        for workflow_id, run_id, attempt, path, names in (
                (11, 101, 2, snapshot.gate.final.WORKFLOW, snapshot.gate.final.REQUIRED_JOBS),
                (12, 102, 1, snapshot.gate.FINAL_WORKFLOW, snapshot.gate.FINAL_JOBS)):
            repo = dict(id=REPOSITORY_ID, full_name=snapshot.REPOSITORY)
            run = dict(id=run_id, run_attempt=attempt, run_number=9, workflow_id=workflow_id,
                       path=path, head_sha=source, status='completed', conclusion='success',
                       repository=copy.deepcopy(repo), head_repository=copy.deepcopy(repo),
                       created_at='2026-09-30T09:59:00Z', run_started_at='2026-09-30T10:00:00Z',
                       updated_at='2026-09-30T10:10:00Z', event='push',
                       head_branch='release/full-rc-candidate-fixture')
            self.data['/actions/workflows/' + Path(path).name] = dict(id=workflow_id, path=path)
            self.data[self.runs_path(workflow_id)] = dict(total_count=1, workflow_runs=[run])
            self.data[f'/actions/runs/{run_id}'] = run
            jobs = [dict(id=run_id * 100 + i, name=name, run_id=run_id, run_attempt=attempt,
                         head_sha=source, status='completed', conclusion='success',
                         started_at='2026-09-30T10:01:00Z', completed_at='2026-09-30T10:09:59Z')
                    for i, name in enumerate(sorted(names), 1)]
            self.data[self.jobs_path(run_id, attempt)] = dict(total_count=len(jobs), jobs=jobs)
        artifact = dict(id=600, name='rc-structural-bundle', size_in_bytes=1000, expired=False,
                        created_at='2026-09-30T10:09:00Z', updated_at='2026-09-30T10:09:01Z',
                        expires_at='2099-10-30T10:09:00Z', digest='sha256:' + 'b' * 64,
                        workflow_run=dict(id=102, head_sha=source, repository_id=REPOSITORY_ID,
                                          head_repository_id=REPOSITORY_ID,
                                          head_branch='release/full-rc-candidate-fixture'))
        self.data[self.artifacts_path()] = dict(total_count=1, artifacts=[artifact])
        self.data['/actions/artifacts/600'] = copy.deepcopy(artifact)

    def get(self, path):
        self.calls.append(path)
        if path not in self.data:
            raise AssertionError('Unexpected synthetic API request: ' + path)
        return copy.deepcopy(self.data[path])

    def runs_path(self, workflow_id):
        return f'/actions/workflows/{workflow_id}/runs?head_sha={self.source}&per_page=100&page=1'

    @staticmethod
    def jobs_path(run_id, attempt=1):
        return f'/actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100&page=1'

    @staticmethod
    def artifacts_path():
        return '/actions/runs/102/artifacts?per_page=100&page=1'

    def artifact(self):
        return self.data[self.artifacts_path()]['artifacts'][0]

    def selection(self):
        return snapshot.select_source_runs(self, candidate(self.source), expectations(self.source))

    def metadata(self):
        return snapshot.authenticate_bundle_metadata(self, self.selection(), 600)
