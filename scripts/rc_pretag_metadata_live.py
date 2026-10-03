"""Exact-source read-only diagnostic; a passing diagnostic grants no authority."""
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from rc_pretag_metadata import collect_metadata
from rc_pretag_metadata_api import CleanupUncertain, MetadataGitHub
from rc_pretag_metadata_source import SourceVerification, verify_source
from rc_pretag_metadata_types import ENGINEERING_REF, MetadataReceipt, MetadataRequest, OBSERVATION_KEYS
from rc_pretag_types import REPOSITORY, REPOSITORY_ID, SourceIdentity, encode, parse_json

WORKFLOW = '.github/workflows/rc-pretag-metadata-checks.yml'
EXPECTED_VERSION = '0.6.0-rc.4'  # Explicit unchanged-baseline expectation, not acceptance.
FALSE_FLAGS = ('published_candidate', 'release_approved', 'publish_approved',
               'security_approved', 'snapshot_atomic')


def require(condition):
    if not condition:
        raise ValueError('diagnostic_rejected')


def context():
    expected = {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': REPOSITORY,
        'GITHUB_REPOSITORY_ID': str(REPOSITORY_ID), 'GITHUB_EVENT_NAME': 'push',
        'GITHUB_REF': ENGINEERING_REF, 'GITHUB_JOB': 'metadata',
        'GITHUB_WORKFLOW_REF': REPOSITORY + '/' + WORKFLOW + '@' + ENGINEERING_REF,
        'RC_EXPECTED_VERSION': EXPECTED_VERSION}
    require(all(os.environ.get(key) == value for key, value in expected.items()))
    sha = os.environ.get('GITHUB_SHA', '')
    require(re.fullmatch('[0-9a-f]{40}', sha) is not None)
    require(os.environ.get('GITHUB_WORKFLOW_SHA') == sha)
    ids = [os.environ.get(key, '') for key in ('GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT')]
    require(all(re.fullmatch('[1-9][0-9]{0,18}', value) and int(value) < 2**63 for value in ids))
    return dict(source_sha=sha, workflow_code_sha=sha, workflow_path=WORKFLOW,
        run_id=int(ids[0]), run_attempt=int(ids[1]), job_name=os.environ['GITHUB_JOB'],
        numeric_job_id=None, job_id_binding='external_review_required',
        expected_version=EXPECTED_VERSION, version_verified=False)


def source(root, sha):
    proof = verify_source(root, sha)  # Live evidence must never use staged mode.
    require(type(proof) is SourceVerification and proof.mode == 'committed')
    require(proof.source_sha == sha and proof.source_verified is True)
    require(all(getattr(proof, key) is False for key in FALSE_FLAGS))
    return proof


def quality(receipt, request):
    require(type(receipt) is MetadataReceipt)
    receipt = parse_json(MetadataReceipt, encode(receipt))  # Revalidate every false guard.
    require(receipt.request == request and receipt.channel == 'fixed_origin_tls_bearer_request')
    require(receipt.revalidation_sha256 is not None and receipt.collection_status == 'blocked')
    first = {row.key: row for row in receipt.observations}
    require(set(first) == set(OBSERVATION_KEYS) - {'collection'})
    require(tuple(asdict(row) | {'records': ()} for row in receipt.observations)
            == tuple(asdict(row) for row in receipt.revalidation_observations))
    negative = {'pretag_workflow': ('missing', 'workflow_missing')}
    for role in ('integration', 'final'):
        negative[role + '_run'] = ('missing', 'no_exact_source_run')
        negative[role + '_jobs'] = ('prerequisite_unavailable', 'prerequisite_unavailable')
        require(first[role + '_runs'].count == 0)
    for key, row in first.items():
        if key in negative:
            require((row.state, row.reason) == negative[key] and row.count == 0 and not row.records)
        else:
            require((row.state, row.reason) == ('observed', 'observed') and row.comparison_sha256)
        require(all('unknown' not in (r.name, r.state, r.conclusion, r.event) for r in row.records))
    return encode(receipt)


def directory(path):
    require(path.is_absolute() and '..' not in path.parts)
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def identity(info):
    return (info.st_dev, info.st_ino, info.st_uid, info.st_mode, info.st_size, info.st_mtime_ns)


def write(fd, name, value, limit=16384):
    require(name in ('source.json', 'scope.json', 'metadata.json', 'error.json', 'completion.pending.json'))
    raw = value if type(value) is bytes else json.dumps(value, sort_keys=True, allow_nan=False).encode()
    require(len(raw) <= limit)
    handle = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
    with os.fdopen(handle, 'wb') as stream:
        created = os.fstat(stream.fileno())
        require(stat.S_ISREG(created.st_mode) and created.st_uid == os.geteuid()
                and created.st_nlink == 1 and created.st_size == 0)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
        owned = identity(os.fstat(stream.fileno()))
    # Returning is possible only after successful flush, fsync, and close.
    return dict(name=name, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()), owned


def verify_file(fd, record, owned, links=1):
    require(links == 1 or links == 2 and record['name'] in ('completion.pending.json', 'completion.json'))
    handle = os.open(record['name'], os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=fd)
    with os.fdopen(handle, 'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and identity(before) == owned and before.st_nlink == links)
        raw = stream.read(record['bytes'] + 1)
        after = os.fstat(stream.fileno())
    current = os.stat(record['name'], dir_fd=fd, follow_symlinks=False)
    require(identity(after) == identity(current) == owned and after.st_nlink == current.st_nlink == links)
    require(len(raw) == record['bytes'] and hashlib.sha256(raw).hexdigest() == record['sha256'])


def complete(fd, payloads):
    names = {'source.json', 'scope.json', 'metadata.json'}
    require({record['name'] for record, _ in payloads} == names and len(payloads) == 3)
    require(set(os.listdir(fd)) == names)
    for record, owned in payloads:
        verify_file(fd, record, owned)
    manifest = dict(schema='rc-pretag-metadata-completion-v1', files=[row for row, _ in payloads],
        evidence_authentication='unverified', release_approved=False, publish_approved=False,
        snapshot_atomic=False, collect_step_success_required=True)
    pending, owned = write(fd, 'completion.pending.json', manifest)
    verify_file(fd, pending, owned)
    require(set(os.listdir(fd)) == names | {'completion.pending.json'})
    os.link('completion.pending.json', 'completion.json', src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
    # The closed pending inode is never changed or retried after this no-overwrite link.
    os.fsync(fd)
    for name in ('completion.pending.json', 'completion.json'):
        verify_file(fd, pending | {'name': name}, owned, links=2)
    for record, owner in payloads:
        verify_file(fd, record, owner)
    require(set(os.listdir(fd)) == names | {'completion.pending.json', 'completion.json'})


def main():
    token = os.environ.pop('GITHUB_TOKEN', '')  # Before any Git or worker child.
    fd = None
    code = 'output_failed'
    try:
        parent = directory(Path(os.environ['RC_DIAGNOSTIC_DIR']))
        try:
            os.mkdir('live', mode=0o700, dir_fd=parent)
            fd = os.open('live', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        finally:
            os.close(parent)
        code = 'invalid_context'
        invocation = context()
        root = Path(__file__).absolute().parent.parent
        code = 'source_verification_failed'
        before = source(root, invocation['source_sha'])
        request = MetadataRequest(SourceIdentity(REPOSITORY, REPOSITORY_ID,
            before.source_sha, before.source_tree, EXPECTED_VERSION), ENGINEERING_REF)
        code = 'collection_failed'
        api = MetadataGitHub(token)
        token = ''
        receipt = collect_metadata(request, api)
        raw = quality(receipt, request)
        code = 'source_revalidation_failed'
        require(source(root, before.source_sha) == before)
        code = 'output_failed'
        payloads = [write(fd, 'source.json', asdict(before)),
            write(fd, 'scope.json', invocation | dict(status='collected', evidence_authentication='unverified',
                release_approved=False, publish_approved=False, snapshot_atomic=False)),
            write(fd, 'metadata.json', raw, 256 * 1024)]
        complete(fd, payloads)
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        if isinstance(exc, CleanupUncertain):
            code = 'cleanup_uncertain'
        if fd is not None:
            try:
                write(fd, 'error.json', dict(status='failed', code=code, release_approved=False,
                    publish_approved=False, evidence_authentication='unverified'), 1024)
            except (OSError, ValueError):
                pass  # A failed diagnostic never overwrites another file to retain an error.
        return 1
    finally:
        token = ''
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                return 1


if __name__ == '__main__':
    raise SystemExit(main())
