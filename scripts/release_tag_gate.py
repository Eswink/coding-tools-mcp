"""Route release tags; RC tags only inspect existing exact-source CI evidence.

This is a bounded API snapshot, not artifact-byte verification or release approval.
The final reusable job names are derived from committed workflow source; a real
completed final DAG must confirm their GitHub display names before release use.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import urllib.request

import cloud_release_bundle as cloud
import final_rc_evidence as final
import rc_version_gate as rc
import reviewed_source_gate as reviewed
from source_provenance_gate import classify
import 发布版本校验v4 as stable

REPOSITORY = final.REPOSITORY
FINAL_WORKFLOW = '.github/workflows/final-rc-packages.yml'
FINAL_JOBS = frozenset({
    'Exact approved source and integration prerequisite',
    'cloud / build',
    'cloud / process',
    'cloud / Non-root image build and protected-file fixture (no deployment)',
    'Same-source nonproduction topology acceptance / topology',
    'Version, packaging and authenticated dependency contracts',
    'Build and install exact Windows NSIS (isolation unresolved)',
    'Build exact Ubuntu22 DEB and AppImage',
    'Installed ubuntu-22.04 (deb)',
    'Installed ubuntu-24.04 (deb)',
    'Installed ubuntu-22.04 (appimage)',
    'Installed ubuntu-24.04 (appimage)',
    'Collect exact-source packaging evidence (release remains blocked)',
})
MAX_PAGES = 10
PAGE_SIZE = 100
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
SNAPSHOT_FIELDS = ('id', 'run_attempt', 'run_number', 'workflow_id', 'path', 'head_sha',
                   'status', 'conclusion', 'run_started_at', 'updated_at',
                   'repository', 'head_repository')
require = rc.require


def positive(value) -> bool:
    return type(value) is int and value > 0


def route(root: Path, tag: str, environment: dict) -> dict:
    require(type(tag) is str and tag.startswith('v'), 'release tag must start with v')
    channel = classify(tag[1:])
    require(environment.get('GITHUB_EVENT_NAME') in ('push', 'workflow_dispatch'),
            'unsupported release event')
    if channel == 'stable':
        # Keep the legacy stable tag parser and its manual checkout semantics.
        source = stable.resolve_tag(root, tag)
        return dict(channel=channel, source_sha=source, release_tag=tag)
    require(environment.get('GITHUB_EVENT_NAME') == 'push',
            'manual RC validation/publication is forbidden, including publish=true')
    require(environment.get('GITHUB_REPOSITORY') == REPOSITORY
            and environment.get('GITHUB_REF') == 'refs/tags/' + tag, 'wrong RC tag push context')
    source = stable.git_commit(root, 'refs/tags/' + tag)
    require(environment.get('GITHUB_SHA') == source, 'RC tag/event source mismatch')
    proof = rc.verify_source(root, expected_sha=source, expected_version=tag[1:])
    object_sha = reviewed.git(root, 'rev-parse', '--verify', 'refs/tags/' + tag).decode().strip()
    require(rc.SHA.fullmatch(object_sha) is not None, 'invalid local tag object')
    return dict(channel=channel, source_sha=proof['source_sha'], release_tag=tag,
                tag_object_sha=object_sha, version=proof['version'],
                release_approved=False, publish_approved=False)


def timestamp(value: str) -> datetime:
    require(type(value) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', value) is not None,
            'invalid API timestamp')
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


class GitHub:
    """Only fixed-origin GETs; never follow an API redirect with the token."""
    def __init__(self, token: str):
        require(bool(token), 'read-only Actions token required')
        self.token = token

    def get(self, suffix: str) -> dict:
        require(suffix.startswith('/') and not suffix.startswith('//'), 'invalid API path')
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, request, fp, code, msg, headers, newurl):
                raise ValueError('unexpected GitHub API redirect')
        request = urllib.request.Request('https://api.github.com/repos/' + REPOSITORY + suffix,
            headers={'Authorization': 'Bearer ' + self.token, 'Accept': 'application/vnd.github+json',
                     'X-GitHub-Api-Version': '2022-11-28'}, method='GET')
        with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        require(len(raw) <= MAX_RESPONSE_BYTES, 'API response exceeds bound')
        value = json.loads(raw, object_pairs_hook=reviewed.unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite API value')))
        require(type(value) is dict, 'API response must be an object')
        return value


def paginate(api, path: str, key: str) -> list:
    """Exhaust the declared result set, refusing truncation, duplicates or races."""
    records, seen, total = [], set(), None
    separator = '&' if '?' in path else '?'
    for page in range(1, MAX_PAGES + 1):
        value = api.get(f'{path}{separator}per_page={PAGE_SIZE}&page={page}')
        count, batch = value.get('total_count'), value.get(key)
        require(type(count) is int and 0 <= count <= MAX_PAGES * PAGE_SIZE,
                'invalid or over-bound pagination count')
        require(total is None or total == count, 'pagination count changed')
        total = count
        require(type(batch) is list and len(batch) <= PAGE_SIZE, 'invalid pagination batch')
        for record in batch:
            require(type(record) is dict and positive(record.get('id')), 'invalid API record ID')
            require(record['id'] not in seen, 'duplicate API record')
            seen.add(record['id'])
            records.append(record)
        require(len(records) <= total, 'pagination count overflow')
        if len(records) == total:
            return records
        require(len(batch) == PAGE_SIZE, 'incomplete pagination result')
    raise ValueError('pagination exceeded bound')


def run_identity(run: dict, workflow: dict, source: str) -> None:
    require(type(run) is dict and positive(run.get('id')) and positive(run.get('run_attempt'))
            and positive(run.get('run_number')), 'invalid run ID/attempt/number')
    require(run.get('head_sha') == source and run.get('path') == workflow['path']
            and type(run.get('workflow_id')) is int and run['workflow_id'] == workflow['id'],
            'wrong run source/workflow')
    require(run.get('repository', {}).get('full_name') == REPOSITORY
            and run.get('head_repository', {}).get('full_name') == REPOSITORY, 'wrong run repository')
    timestamp(run.get('run_started_at'))
    require(timestamp(run.get('updated_at')) >= timestamp(run['run_started_at']), 'invalid run time order')


def latest_run(api, workflow: dict, source: str) -> dict:
    # No status=success filter: a newer failed/pending exact-source run blocks.
    runs = paginate(api, f"/actions/workflows/{workflow['id']}/runs?head_sha={source}", 'workflow_runs')
    # Filtered Actions searches have a documented 1000-result cap. At that
    # boundary we cannot establish completeness, even if total_count is capped.
    require(len(runs) < 1000, 'workflow run search cap reached; completeness unproven')
    require(bool(runs), 'no exact-source workflow run')
    for run in runs:
        run_identity(run, workflow, source)
    return max(runs, key=lambda run: run['id'])


def same_snapshot(before: dict, after: dict) -> None:
    require(all(before.get(field) == after.get(field) for field in SNAPSHOT_FIELDS),
            'run changed during evidence snapshot')


def successful_run(api, workflow_path: str, source: str, expected_jobs: frozenset | set) -> dict:
    workflow = api.get('/actions/workflows/' + Path(workflow_path).name)
    require(positive(workflow.get('id')) and workflow.get('path') == workflow_path,
            'workflow identity mismatch')
    selected = latest_run(api, workflow, source)
    run = api.get(f"/actions/runs/{selected['id']}")
    run_identity(run, workflow, source)
    same_snapshot(selected, run)
    require(run.get('status') == 'completed' and run.get('conclusion') == 'success',
            'newest exact-source run has not succeeded')
    jobs = paginate(api, f"/actions/runs/{run['id']}/attempts/{run['run_attempt']}/jobs", 'jobs')
    names = [job.get('name') for job in jobs]
    require(all(type(name) is str for name in names) and len(names) == len(expected_jobs)
            and len(set(names)) == len(names) and set(names) == expected_jobs,
            'job inventory is not the exact required set')
    # The actual repository attempt endpoint returns run_attempt on every job.
    # Require that observed contract in addition to the attempt-specific URL.
    for job in jobs:
        require(type(job.get('run_id')) is int and job['run_id'] == run['id']
                and positive(job.get('run_attempt')) and job['run_attempt'] == run['run_attempt']
                and job.get('head_sha') == source and job.get('status') == 'completed'
                and job.get('conclusion') == 'success', 'failed skipped or foreign job/attempt')
    if workflow_path == final.WORKFLOW:
        # Additional strict checks surround the existing compatible subset helper.
        final.integration(run, jobs, source, str(run['id']))
    same_snapshot(run, api.get(f"/actions/runs/{run['id']}"))
    return dict(run=run, workflow=workflow, jobs=jobs)


def bundle_metadata(api, run: dict) -> dict:
    artifacts = paginate(api, f"/actions/runs/{run['id']}/artifacts", 'artifacts')
    matches = [artifact for artifact in artifacts if artifact.get('name') == 'rc-structural-bundle']
    require(len(matches) == 1, 'expected exactly one final structural bundle artifact')
    artifact = matches[0]
    owner = artifact.get('workflow_run', {})
    require(type(owner.get('id')) is int and owner['id'] == run['id']
            and owner.get('head_sha') == run['head_sha'], 'foreign final bundle artifact')
    require(artifact.get('expired') is False and positive(artifact.get('size_in_bytes')),
            'missing expired or empty final bundle artifact')
    created = timestamp(artifact.get('created_at'))
    require(timestamp(run['run_started_at']) <= created <= timestamp(run['updated_at']),
            'final bundle predates selected run attempt or postdates completion')
    require(timestamp(artifact.get('expires_at')) > datetime.now(created.tzinfo), 'final bundle expired')
    digest = artifact.get('digest')
    require(digest is None or (type(digest) is str and re.fullmatch(r'sha256:[0-9a-f]{64}', digest)),
            'invalid final bundle metadata digest')
    return dict(id=artifact['id'], name=artifact['name'], size_in_bytes=artifact['size_in_bytes'],
                digest=digest, created_at=artifact['created_at'], expires_at=artifact['expires_at'],
                artifact_bytes_verified=False, digest_available=digest is not None)


def live_tag(api, tag: str, expected_object: str, expected_source: str) -> None:
    ref = api.get('/git/ref/tags/' + tag)
    require(ref.get('ref') == 'refs/tags/' + tag, 'live tag ref mismatch')
    obj = ref.get('object', {})
    require(obj.get('sha') == expected_object, 'live tag moved')
    seen = set()
    for _ in range(10):
        sha, kind = obj.get('sha'), obj.get('type')
        require(type(sha) is str and rc.SHA.fullmatch(sha) is not None and sha not in seen,
                'invalid or cyclic live tag object')
        seen.add(sha)
        if kind == 'commit':
            require(sha == expected_source, 'live tag/source mismatch')
            return
        require(kind == 'tag', 'live tag does not resolve to a commit')
        annotation = api.get('/git/tags/' + sha)
        require(annotation.get('sha') == sha, 'annotated tag object mismatch')
        obj = annotation.get('object', {})
    raise ValueError('annotated tag depth exceeded bound')


def verify(root: Path, tag: str, environment: dict, api) -> dict:
    resolved = route(root, tag, environment)
    require(resolved['channel'] == 'release-candidate', 'RC evidence gate requires an RC push')
    source = resolved['source_sha']
    components = cloud.versions(root, resolved['version'])
    manifest = reviewed.verify(root, source)
    live_tag(api, tag, resolved['tag_object_sha'], source)
    integration = successful_run(api, final.WORKFLOW, source, final.REQUIRED_JOBS)
    packaging = successful_run(api, FINAL_WORKFLOW, source, FINAL_JOBS)
    artifact = bundle_metadata(api, packaging['run'])
    # Re-list all statuses and re-read selected attempts to detect observed
    # changes. These checks are bounded observations, not an atomic API snapshot.
    for evidence in (integration, packaging):
        same_snapshot(evidence['run'], latest_run(api, evidence['workflow'], source))
        same_snapshot(evidence['run'], api.get(f"/actions/runs/{evidence['run']['id']}"))
    live_tag(api, tag, resolved['tag_object_sha'], source)
    require(route(root, tag, environment) == resolved, 'local tag/source changed')
    return dict(resolved, passed=True, scope='existing exact-source CI metadata only',
                component_versions=components, reviewed_source=manifest,
                integration=integration, final_packaging=packaging, final_bundle=artifact,
                release_approved=False, publish_approved=False,
                limitations=['Artifact bytes are not downloaded or executed',
                             'This bounded snapshot is not release/security approval'])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('route', 'verify'))
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--tag', required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--github-output', action='store_true')
    args = parser.parse_args()
    require(not args.github_output or args.command == 'route', 'outputs are only for routing')
    value = (route(args.root.resolve(), args.tag, os.environ) if args.command == 'route' else
             verify(args.root.resolve(), args.tag, os.environ, GitHub(os.environ.get('GH_TOKEN', ''))))
    if args.github_output:
        with Path(os.environ['GITHUB_OUTPUT']).open('a', encoding='utf-8') as output:
            for key in ('channel', 'source_sha', 'release_tag'):
                output.write(f'{key}={value[key]}\n')
    encoded = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding='utf-8')
    print(encoded, end='')


if __name__ == '__main__':
    main()
