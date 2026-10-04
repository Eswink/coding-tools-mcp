"""One fixed diagnostic; importing this module never starts or authenticates work."""
from datetime import datetime, timedelta, timezone
import hashlib
import http.client
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import selectors
import signal
import stat
import subprocess
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).absolute().parents[1]
C_COMMIT = '93c2ad95304668ecc112da0cb073e46fe177e4f7'
C_TREE = '2eb0f0b3809c98331f9db4ae56a137c8817b3489'
HASHES = {
    'rc_consumer_io': '3856af4ab573a91838ca2e06bb224ac983c8200a29b34f8a6a6c2bc9619b8de9',
    'rc_consumer_transport_worker': '0ef142614c4c465ac166e4c4ca796b94474c333ace9db39cdc64e3010946f52b',
    'rc_consumer_transport': '2555906190830843de21c8e54d3fca3f2043bae3330a17109d72bdf7782ca703',
}
ADDED = ('.github/workflows/rc-artifact-default-worker-proof.yml',
         'scripts/rc_consumer_default_worker_proof.py',
         'scripts/rc_consumer_default_worker_proof_tests.py')
REPOSITORY, REPOSITORY_ID = 'Eswink/coding-tools-mcp', 1360355522
REF = 'refs/heads/ci/rc-artifact-default-worker-proof-20261004'
WORKFLOW_REF = REPOSITORY + '/.github/workflows/rc-artifact-default-worker-proof.yml@' + REF
SOURCE_SHA = 'e2e011f7f2a3a1df838bbd588106205b999db610'
RUN_ID, ARTIFACT_ID, SIZE = 36796834637, 11134440327, 912
DIGEST = 'sha256:dcc70362712162e99d6884942f0720934bc16c7d6a817361ffbfd1602601fa60'
BRANCH = 'ci/rc-tag-evidence-e2e011-cumulative'
CREATED, EXPIRES = '2026-10-01T00:34:27Z', '2026-10-08T00:34:27Z'
REPO_FIELDS = (('id', REPOSITORY_ID), ('full_name', REPOSITORY))
RUN_FIELDS = (('id', RUN_ID), ('run_attempt', 1), ('workflow_id', 352786852),
    ('head_sha', SOURCE_SHA), ('event', 'push'), ('head_branch', BRANCH),
    ('path', '.github/workflows/发布来源验证v4.yml'), ('status', 'completed'),
    ('conclusion', 'success'), ('created_at', '2026-10-01T00:34:16Z'),
    ('run_started_at', '2026-10-01T00:34:16Z'), ('updated_at', '2026-10-01T00:35:27Z'))
ARTIFACT_FIELDS = (('id', ARTIFACT_ID), ('name', '发布来源证据v4-ubuntu-latest-36796834637'),
    ('size_in_bytes', SIZE), ('digest', DIGEST), ('expired', False),
    ('created_at', CREATED), ('updated_at', CREATED), ('expires_at', EXPIRES))
NESTED_FIELDS = (('id', RUN_ID), ('repository_id', REPOSITORY_ID),
    ('head_repository_id', REPOSITORY_ID), ('head_sha', SOURCE_SHA), ('head_branch', BRANCH))
BASE = '/repos/' + REPOSITORY
RUN_PATH = BASE + '/actions/runs/' + str(RUN_ID)
METADATA_PATHS = (BASE, RUN_PATH, RUN_PATH + '/artifacts?per_page=100&page=1',
                  BASE + '/actions/artifacts/' + str(ARTIFACT_ID))
HOSTS = frozenset({'productionresultssa5.blob.core.windows.net'})
SCOPE = 'fixed-default-worker-artifact-proof-only'
STAGES = frozenset({'preflight', 'metadata_a', 'private_root', 'transport', 'readback',
                   'metadata_b', 'readback_b', 'root_close', 'source_exit', 'report'})
CODES = frozenset({'preflight_rejected', 'source_rejected', 'identity_rejected',
    'runtime_rejected', 'metadata_rejected', 'expiry_rejected', 'file_rejected',
    'root_close_failed', 'signal_setup_failed', 'signal_cleanup_failed', 'overall_deadline', 'proof_failed', 'transport_cleanup_uncertain',
    'transport_cancelled', 'invalid_storage_redirect', 'unverified_storage_host',
    'unexpected_artifact_download_status', 'unexpected_storage_status',
    'encoded_storage_response', 'download_size_mismatch', 'invalid_transport_chunk',
    'artifact_transport_failed', 'invalid_transport_ipc', 'transport_deadline_exceeded',
    'download_digest_mismatch', 'unsafe_private_io', 'invalid_private_mode', 'unsafe_path',
    'unsafe_absolute_path', 'private_root_closed', 'private_root_replaced',
    'unsafe_private_directory', 'unsafe_private_file', 'unknown_private_directory',
    'private_directory_replaced', 'private_file_replaced', 'private_inventory_changed',
    'private_read_limit', 'unsafe_root_parent', 'root_inside_source'})
STATE = {'stage': 'preflight', 'expired': False, 'deadline': 0.0, 'cleanup': None}


class ProofError(ValueError):
    def __init__(self, code):
        self.code = code if type(code) is str and code in CODES else 'proof_failed'
        super().__init__('proof_rejected')


def require(condition, code='preflight_rejected'):
    if not condition:
        raise ProofError(code)


def deadline_check():
    require(not STATE['expired'] and time.monotonic() < STATE['deadline'], 'overall_deadline')


def alarm(_signum, _frame):
    STATE['expired'] = True
    raise ProofError('overall_deadline')


def runtime():
    require(len(sys.argv) == 1 and sys.implementation.name == 'cpython'
            and sys.version_info[:3] == (3, 12, 14) and platform.system() == 'Linux'
            and sys.flags.isolated == 1 and sys.flags.no_site == 1
            and sys.dont_write_bytecode, 'runtime_rejected')


def identity():
    expected = {'GITHUB_REPOSITORY': REPOSITORY, 'GITHUB_REPOSITORY_ID': str(REPOSITORY_ID),
        'GITHUB_EVENT_NAME': 'push', 'GITHUB_REF': REF, 'GITHUB_WORKFLOW_REF': WORKFLOW_REF,
        'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_WORKSPACE': str(ROOT)}
    values = {key: os.environ.get(key, '') for key in (*expected, 'GITHUB_SHA',
              'GITHUB_WORKFLOW_SHA', 'GITHUB_RUN_ID', 'RUNNER_TEMP')}
    require(all(values[key] == value for key, value in expected.items()), 'identity_rejected')
    require(re.fullmatch('[0-9a-f]{40}', values['GITHUB_SHA']) is not None
            and values['GITHUB_WORKFLOW_SHA'] == values['GITHUB_SHA'], 'identity_rejected')
    require(re.fullmatch('[1-9][0-9]{0,19}', values['GITHUB_RUN_ID']) is not None,
            'identity_rejected')
    require(0 < len(values['RUNNER_TEMP']) <= 4096 and values['RUNNER_TEMP'].startswith('/'),
            'identity_rejected')
    return values


def git(*args):
    # All callers provide fixed read-only arguments; cap reads, time and output.
    process = subprocess.Popen(['/usr/bin/git', '--no-optional-locks', '-c', 'core.fsmonitor=false',
        '-c', 'core.hooksPath=/dev/null', '-C', str(ROOT), *args], stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, shell=False, close_fds=True,
        env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C', 'GIT_CONFIG_NOSYSTEM': '1',
             'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_TERMINAL_PROMPT': '0'})
    data, end = bytearray(), time.monotonic() + 10
    try:
        os.set_blocking(process.stdout.fileno(), False)
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                left = end - time.monotonic()
                require(left > 0 and selector.select(left), 'source_rejected')
                chunk = os.read(process.stdout.fileno(), min(65536, 131073 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
                require(len(data) <= 131072, 'source_rejected')
        require(process.wait(timeout=max(0, end - time.monotonic())) == 0, 'source_rejected')
        return data.decode('utf-8', errors='strict').strip()
    finally:
        try:
            process.stdout.close()
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)


def source_bytes():
    require(ROOT == ROOT.resolve() and (ROOT / 'scripts').is_dir(), 'source_rejected')
    buffers = {}
    for name, digest in HASHES.items():
        path = ROOT / 'scripts' / (name + '.py')
        require(path == path.resolve(), 'source_rejected')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= 65536,
                    'source_rejected')
            data = stream.read(65537)
        require(len(data) <= 65536 and hashlib.sha256(data).hexdigest() == digest,
                'source_rejected')
        buffers[name] = data
    return buffers


def source_snapshot(values):
    head = git('rev-parse', 'HEAD')
    require(head == values['GITHUB_SHA'], 'source_rejected')
    require(git('rev-list', '--parents', '-n', '1', 'HEAD') == head + ' ' + C_COMMIT,
            'source_rejected')
    require(git('rev-parse', 'HEAD^1^{tree}') == C_TREE, 'source_rejected')
    tree = git('rev-parse', 'HEAD^{tree}')
    require(re.fullmatch('[0-9a-f]{40}', tree) is not None, 'source_rejected')
    delta = git('diff-tree', '--no-commit-id', '--no-renames', '--raw', '-r', C_COMMIT, 'HEAD')
    rows = delta.splitlines()
    require(len(rows) == 3, 'source_rejected')
    for row, path in zip(rows, ADDED):
        require(re.fullmatch(':000000 100644 0{40} [0-9a-f]{40} A\t' + re.escape(path), row)
                is not None, 'source_rejected')
    require(git('status', '--porcelain=v1', '--untracked-files=all', '--ignored=matching') == '',
            'source_rejected')
    return {'c_commit': C_COMMIT, 'c_tree': C_TREE, 'h_commit': head, 'h_tree': tree,
            'module_sha256': dict(HASHES)}, source_bytes()


def load_production(buffers):
    require(tuple(buffers) == tuple(HASHES) and not any(n in sys.modules for n in HASHES),
            'source_rejected')
    modules = []
    for name, digest in HASHES.items():
        data, path = buffers[name], str(ROOT / 'scripts' / (name + '.py'))
        require(type(data) is bytes and hashlib.sha256(data).hexdigest() == digest, 'source_rejected')
        spec = importlib.util.spec_from_file_location(name, path)
        require(spec is not None and spec.name == name and spec.origin == path
                and type(spec.loader) is importlib.machinery.SourceFileLoader
                and spec.loader.path == path, 'source_rejected')
        module = importlib.util.module_from_spec(spec)
        require(module.__file__ == path and module.__spec__ is spec
                and module.__loader__ is spec.loader, 'source_rejected')
        sys.modules[name] = module
        # Execute only these hash-verified buffers. Never ask a loader to execute code.
        exec(compile(data, path, 'exec', dont_inherit=True), module.__dict__)
        modules.append(module)
    io, wire, transport = modules
    require(wire.TRUSTED_STORAGE_HOSTS == transport.TRUSTED_STORAGE_HOSTS == HOSTS
            and transport.TOTAL_TIMEOUT == 300 and transport.CLEANUP_TIMEOUT == 5
            and wire.READ_TIMEOUT == 15
            and transport.WORKER == ROOT / 'scripts/rc_consumer_transport_worker.py', 'source_rejected')
    return io, wire, transport


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, 'metadata_rejected')
        result[key] = value
    return result


def integer(raw):
    require(len(raw) <= 20, 'metadata_rejected')
    value = int(raw)
    require(-(2**63) <= value < 2**63, 'metadata_rejected')
    return value


def noninteger(_raw):
    raise ProofError('metadata_rejected')


def metadata_get(path, token):
    require(path in METADATA_PATHS, 'metadata_rejected')
    deadline_check()
    connection = http.client.HTTPSConnection('api.github.com', port=443, timeout=10)
    response = None
    try:
        connection.request('GET', path, headers={'Authorization': 'Bearer ' + token,
            'Accept': 'application/vnd.github+json', 'Accept-Encoding': 'identity',
            'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'rc-default-worker-proof'})
        response = connection.getresponse()
        headers = response.getheaders()
        # Post-stdlib-parsing aggregate limit, not a preallocation header bound.
        require(sum(len(k) + len(v) + 4 for k, v in headers) <= 16384, 'metadata_rejected')
        headers = [(k.lower(), v) for k, v in headers]
        require(type(response.status) is int and response.status == 200
                and not any(k in {'location', 'link'} for k, _ in headers), 'metadata_rejected')
        types = [v for k, v in headers if k == 'content-type']
        require(len(types) == 1 and types[0].split(';')[0].strip() == 'application/json', 'metadata_rejected')
        enc = [v for k, v in headers if k == 'content-encoding']
        require(not enc or enc == ['identity'], 'metadata_rejected')
        lengths = [v for k, v in headers if k == 'content-length']
        require(len(lengths) <= 1, 'metadata_rejected')
        if lengths:
            require(re.fullmatch('[0-9]{1,6}', lengths[0]) is not None
                    and int(lengths[0]) <= 131072
                    and not any(k == 'transfer-encoding' for k, _ in headers), 'metadata_rejected')
        raw = response.read(131073)
        require(len(raw) <= 131072 and (not lengths or int(lengths[0]) == len(raw)), 'metadata_rejected')
        result = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_int=integer,
                            parse_float=noninteger, parse_constant=noninteger)
        require(type(result) is dict, 'metadata_rejected')
        return result
    finally:
        try:
            if response is not None:
                response.close()
        finally:
            connection.close()


def selected(record, fields):
    require(type(record) is dict, 'metadata_rejected')
    values = []
    for key, expected in fields:
        value = record.get(key)
        require(type(value) is type(expected) and value == expected, 'metadata_rejected')
        values.append(value)
    return tuple(values)


def artifact_tuple(record):
    return selected(record, ARTIFACT_FIELDS) + (selected(record.get('workflow_run'), NESTED_FIELDS),)


def expiry(phase):
    require(phase in ('a', 'b'), 'expiry_rejected')
    expires = datetime.fromisoformat(EXPIRES.replace('Z', '+00:00'))
    now = datetime.now(timezone.utc)
    require(now + timedelta(seconds=430 if phase == 'a' else 0) < expires, 'expiry_rejected')


def metadata(token, phase):
    repo = selected(metadata_get(METADATA_PATHS[0], token), REPO_FIELDS)
    run = metadata_get(METADATA_PATHS[1], token)
    run_tuple = selected(run, RUN_FIELDS) + tuple(selected(run.get(k), REPO_FIELDS)
                                                for k in ('repository', 'head_repository'))
    listing = metadata_get(METADATA_PATHS[2], token)
    total, items = listing.get('total_count'), listing.get('artifacts')
    require(type(total) is int and total == 2 and type(items) is list and len(items) == total,
            'metadata_rejected')
    ids, target = [], None
    for item in items:
        require(type(item) is dict and type(item.get('id')) is int and 0 < item['id'] < 2**63,
                'metadata_rejected')
        ids.append(item['id'])
        if item['id'] == ARTIFACT_ID:
            target = artifact_tuple(item)
    require(tuple(sorted(ids)) == (11133683955, ARTIFACT_ID), 'metadata_rejected')
    direct = artifact_tuple(metadata_get(METADATA_PATHS[3], token))
    require(target == direct and RUN_FIELDS[9][1] <= CREATED <= RUN_FIELDS[11][1], 'metadata_rejected')
    expiry(phase)
    deadline_check()
    return (repo, run_tuple, direct, (total, tuple(sorted(ids)))), {
        'id': ARTIFACT_ID, 'size_in_bytes': SIZE, 'digest': DIGEST}


def readback(root, path):
    require(path == root.path / 'artifact.zip' and root.files() == ('artifact.zip',), 'file_rejected')
    data = root.read('artifact.zip', limit=SIZE)
    require(len(data) == SIZE and 'sha256:' + hashlib.sha256(data).hexdigest() == DIGEST, 'file_rejected')
    return {'size_in_bytes': len(data), 'digest': 'sha256:' + hashlib.sha256(data).hexdigest()}


def error_code(error):
    try:
        value = error.code
        if type(value) is str and value in CODES:
            return value
    except BaseException:
        pass
    return 'proof_failed'


def run_proof(token):
    runtime()
    values = identity()
    require(type(token) is str and 0 < len(token) <= 16384, 'preflight_rejected')
    binding, buffers = source_snapshot(values)
    io, _wire, transport = load_production(buffers)
    STATE['stage'] = 'metadata_a'
    before, artifact = metadata(token, 'a')
    STATE['stage'] = 'private_root'
    root = io.PrivateRoot(values['RUNNER_TEMP'], prefix='rc-default-worker-proof-', source_root=ROOT)
    try:
        with root:
            STATE['stage'] = 'transport'
            try:
                path = transport.download_artifact_zip(SimpleNamespace(token=token), artifact, root, opener=None)
            except BaseException as error:
                if error_code(error) == 'transport_cleanup_uncertain':
                    STATE['cleanup'] = 'artifact_transport_failed'
                    original = getattr(error, 'original_error_code', None)
                    if type(original) is str and original in transport.SAFE_ERRORS | {'transport_cancelled'}:
                        STATE['cleanup'] = original
                raise
            deadline_check()
            STATE['stage'] = 'readback'
            observed = readback(root, path)
            STATE['stage'] = 'metadata_b'
            after, _ = metadata(token, 'b')
            require(before == after, 'metadata_rejected')
            STATE['stage'] = 'readback_b'
            require(readback(root, path) == observed, 'file_rejected')
            STATE['stage'] = 'root_close'
    except BaseException:
        if STATE['stage'] == 'root_close':
            raise ProofError('root_close_failed') from None
        raise
    STATE['stage'] = 'source_exit'
    final, final_buffers = source_snapshot(values)
    require(final == binding and final_buffers == buffers, 'source_rejected')
    expiry('b')
    deadline_check()
    STATE['stage'] = 'report'
    return {'schema': 'rc-default-worker-proof-v1', 'scope': SCOPE, 'passed': True,
        'source': binding, 'run_id': int(values['GITHUB_RUN_ID']), 'run_attempt': 1,
        'workflow_ref': WORKFLOW_REF, 'runtime': {'implementation': 'cpython',
        'python': platform.python_version(), 'system': platform.system()},
        'producer_run_id': RUN_ID, 'artifact_id': ARTIFACT_ID, 'observed_owned_file': observed,
        'production_default_call_returned': True, 'independent_owned_file_readback': True,
        'metadata_a_b_equal': True, 'private_root_closed': True, 'source_unchanged': True,
        'source_enforced_success_contract': {'evidence_basis': 'reviewed_unchanged_default_path',
        'api_status': 302, 'storage_status': 200, 'storage_host': next(iter(HOSTS)),
        'worker_exit_code': 0, 'done_eof_normal_reap_and_certain_completion': True},
        'independent_worker_network_telemetry': False, 'snapshot_atomic': False,
        'release_approved': False, 'publish_approved': False, 'final_bundle_validated': False}


def failure(error):
    code = error_code(error)
    if STATE['cleanup'] is not None:
        code = 'transport_cleanup_uncertain'
    elif STATE['expired'] or time.monotonic() >= STATE['deadline']:
        code = 'overall_deadline'
    stage = STATE['stage'] if STATE['stage'] in STAGES else 'preflight'
    report = {'schema': 'rc-default-worker-proof-v1', 'scope': SCOPE, 'passed': False,
        'stage': stage, 'code': code, 'release_approved': False, 'publish_approved': False,
        'final_bundle_validated': False, 'snapshot_atomic': False}
    if code == 'transport_cleanup_uncertain':
        report['original_error_code'] = STATE['cleanup'] or 'artifact_transport_failed'
    return report


def main():
    previous, rc = None, 1
    STATE.update(stage='preflight', expired=False, deadline=time.monotonic() + 420, cleanup=None)
    try:
        token = os.environ.pop('GH_TOKEN', '')
        try:
            previous = signal.signal(signal.SIGALRM, alarm)
            signal.setitimer(signal.ITIMER_REAL, max(0.001, STATE['deadline'] - time.monotonic()))
        except BaseException:
            raise ProofError('signal_setup_failed') from None
        report = run_proof(token)
        deadline_check()
        rc = 0
    except BaseException as error:
        report = failure(error)
    finally:
        cleanup_failed = False
        try:
            signal.setitimer(signal.ITIMER_REAL, 0)
        except BaseException:
            cleanup_failed = True
        try:
            if previous is not None:
                signal.signal(signal.SIGALRM, previous)
        except BaseException:
            cleanup_failed = True
        if cleanup_failed:
            report, rc = failure(ProofError('signal_cleanup_failed')), 1
    try:
        if rc == 0:
            deadline_check()
        output = json.dumps(report, sort_keys=True, ensure_ascii=True)
        if rc == 0:
            deadline_check()
    except BaseException as error:
        output, rc = json.dumps(failure(error), sort_keys=True, ensure_ascii=True), 1
    try:
        print(output)
    except BaseException:
        return 1
    return rc


if __name__ == '__main__':
    # Last boundary also covers interruption during failure formatting itself.
    try:
        exit_code = main()
    except BaseException:
        try:
            print('{"schema":"rc-default-worker-proof-v1","scope":"fixed-default-worker-artifact-proof-only",'
                  '"passed":false,"stage":"preflight","code":"proof_failed","snapshot_atomic":false,'
                  '"release_approved":false,"publish_approved":false,"final_bundle_validated":false}')
        except BaseException:
            pass
        exit_code = 1
    sys.exit(exit_code)
