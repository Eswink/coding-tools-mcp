"""New preparation-only entry. Original Publisher85/300 remain blocked.

Workflow redirects all stdout/stderr before this interpreter starts. No raw
console output is used, no production/provider/tag/release code is executed.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import time

import rc_disposable_git_prepare as prepare
import rc_disposable_git_role_install as role
import rc_disposable_public_projection as public
import rc_native_probe_restore as original_restore

BRANCH = 'ci/rc070-publisher-genuine-tool-prep-20261009'
INPUTS = (
    ('archive', 'git-2.55.0.tar.xz', 8177180, prepare.SOURCE_SHA,
     'https://www.kernel.org/pub/software/scm/git/git-2.55.0.tar.xz'),
    ('signature', 'git-2.55.0.tar.sign', 566, prepare.SIGN_SHA,
     'https://www.kernel.org/pub/software/scm/git/git-2.55.0.tar.sign'),
    ('key', 'junio-full-public-key.asc', 68820, prepare.KEY_SHA,
     'https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x96E07AF25771955980DAD10020D04E5A713660A7'))
MAX_REQUEST = 8192
MAX_ROLE_RESULT = 4096
_SUT_RUNS = 0


def run_disposable_publisher_probe(*args, **kwargs):
    # A separate source/authorization contract is required for private durable
    # raw persistence and original85→all8raw receipt_gate→300. No fallback to
    # old main, historical receipts, public projection or fixture grants.
    raise ValueError('Private durable original evidence is unavailable; SUT0')


def _fetch_inputs(context):
    root = Path(context['root']) / 'rc070-official-inputs'
    root.mkdir(mode=0o700)
    paths = {}
    for name, filename, size, digest, url in INPUTS:
        path = root / filename
        if os.path.lexists(path):
            raise ValueError('Fresh official input path required')
        prepare._capture(['/usr/bin/curl', '--fail', '--silent', '--show-error',
                          '--proto', '=https', '--max-redirs', '0', '--connect-timeout', '10',
                          '--max-time', '30', '--max-filesize', str(size),
                          '--output', str(path), url])
        data = context['dependency'].owned_debian_file_io(path, read_limit=size+1)
        info = path.lstat()
        if (len(data) != size or hashlib.sha256(data).hexdigest() != digest
                or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != os.geteuid()):
            raise ValueError('Downloaded official input mismatch')
        paths[name] = path
    return paths


def _fixed_role_program(management):
    path = Path(management) / 'scripts/rc_disposable_git_role_install.py'
    raw = original_restore.read_regular(path)
    expected = original_restore.git(management, 'show', 'HEAD:scripts/rc_disposable_git_role_install.py')
    if raw != expected or len(raw) > 65536:
        raise ValueError('Actual reviewed inline installer source mismatch')
    trailer = '''
import sys
os.umask(0o022)
def _pairs(rows):
    result = {}
    for key, value in rows:
        if key in result:
            raise ValueError('Duplicate typed key')
        result[key] = value
    return result
try:
    if len(sys.argv) != 2 or len(sys.argv[1].encode('utf-8')) > 8192:
        raise ValueError('Bounded typed input required')
    request = json.loads(sys.argv[1], object_pairs_hook=_pairs,
                         parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite input')))
    result = install_disposable_git_role(request)
    if UNKNOWN:
        raise ValueError('UNKNOWN actual holders remain')
    encoded = json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False)
    if len(encoded.encode('ascii')) > 4096:
        raise ValueError('Bounded helper result required')
    print(encoded)
except BaseException:
    print('{"status":"FAIL_SINGLE_ROLE"}')
    sys.exit(1)
'''
    return raw.decode('utf-8') + trailer


def _role_callbacks(management, context):
    state = {'created': False, 'closed': False, 'probe_passed': False,
             'source_sha256': None, 'actual_role': None, 'deadline': None}

    def before(prefix, installed, built, deadline):
        remaining = deadline - time.monotonic()
        if not 0 < remaining <= 30:
            raise TimeoutError('Shared original installed-probe deadline')
        state['deadline'] = deadline
        if os.path.lexists(role.TARGET):
            raise ValueError('Single role no-clobber requires preabsence')
        source = Path(prefix) / 'bin/git'
        fd = role.HeldFD()
        parent = role.HeldFD()
        primary, request, errors = None, None, []
        try:
            fd.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
            parent.open('/usr/local/bin', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
            source_identity = role.file_identity(fd.fd)
            digest = role.digest_fd(fd.fd, source_identity[6])
            if digest != built['sha256'] or installed['bin/git']['sha256'] != digest:
                raise ValueError('Role source is not this genuine fullinstall')
            request = dict(schema='rc070-single-git-role-1', runner_temp=context['root'],
                           source_relative=str(source.relative_to(context['root'])),
                           source_identity=source_identity, source_bytes=source_identity[6],
                           source_sha256=digest, target_parent=role.parent_identity(parent.fd),
                           caller_uid=os.geteuid())
        except BaseException as error:
            primary = error
        finally:
            for holder in (parent, fd):
                try:
                    holder.close()
                except BaseException as error:
                    errors.append(error)
        if errors:
            raise BaseExceptionGroup('Role input primary and independent closes',
                                     ([primary] if primary is not None else []) + errors)
        if primary is not None:
            raise primary
        data = json.dumps(role.validate_role_install_request(request), separators=(',', ':'))
        if len(data.encode('utf-8')) > MAX_REQUEST:
            raise ValueError('Role typed request bound')
        program = _fixed_role_program(management)
        if os.access('/usr/local/bin', os.W_OK):
            command = ['/usr/bin/python3', '-I', '-S', '-c', program, data]
        else:
            # No sudo shell, mutable runner script, chmod/chown or dependency install.
            # Actual noninteractive sudo availability is required, never simulated.
            command = ['/usr/bin/sudo', '-n', '--', '/usr/bin/python3', '-I', '-S', '-c', program, data]
        phase, raw = prepare._capture(command, seconds=deadline-time.monotonic(), allow_nonzero=True)
        if len(raw) > MAX_ROLE_RESULT or phase['exit'] != 0:
            raise ValueError('Actual fixed role helper failed')
        result = public.parse_projection(raw)
        public.exact(result, ('status', 'bytes', 'sha256', 'close_state', 'publisher_authority'))
        if (result['status'] != 'CREATED_ROLE_ONLY' or result['close_state'] != 'CLOSED'
                or result['publisher_authority'] is not False or result['sha256'] != request['source_sha256']
                or result['bytes'] != request['source_bytes']):
            raise ValueError('Actual role creation and closure mismatch')
        state.update(created=True, closed=True, source_sha256=request['source_sha256'],
                     actual_role=context['dependency'].snapshot_debian_tool(role.TARGET, native=True))
        prepare.read_current_tool_lease(context)

    def after(prefix, deadline):
        remaining = deadline - time.monotonic()
        if deadline != state['deadline']:
            raise ValueError('Same original absolute shared deadline required')
        if not state['created'] or not state['closed'] or not 0 < remaining <= 30:
            raise ValueError('Current original role closure and shared budget required')
        raw = prepare._capture([role.TARGET, *prepare.PREFIX, '--version'], seconds=remaining)
        if raw != b'git version 2.55.0\n':
            raise ValueError('Actual extra role fullflags/version')
        current = context['dependency'].snapshot_debian_tool(role.TARGET, native=True)
        if current != state['actual_role'] or current['sha256'] != state['source_sha256']:
            raise ValueError('Actual installed role changed')
        prepare.read_current_tool_lease(context)
        state['completed_monotonic'] = time.monotonic()
        if state['completed_monotonic'] >= deadline:
            raise TimeoutError('Real role probe/close shared deadline exceeded')
        state['probe_passed'] = True
    context['role_pre'], context['role_post'] = before, after
    context['role_state'] = state


def _source_context(management, context):
    # Original restore is real nativefetch/gitshow, untouched source/AST. No SUT.
    for commit in (original_restore.BACKUP, original_restore.PARENT):
        prepare._capture(['/usr/bin/git', '-c', 'credential.helper=', '-c', 'core.hooksPath=/dev/null',
                          '-C', str(management), 'fetch', '--no-tags', 'origin', commit])
    old = os.umask(0o022)
    try:
        return original_restore.restore(management, Path(context['root']) / 'rc070-pure-source')
    finally:
        os.umask(old)


def _projections(management, context, source, prepared):
    profile = dict(status='NOT_RUN', loaded=0, executed=0, success=0, failures=0,
                   errors=0, skips=0, xfails=0, xpasses=0)
    result = prepared['result']
    state = context['role_state']
    if (not all(state.get(k) is True for k in ('created', 'closed', 'probe_passed'))
            or role.UNKNOWN or not result['source_runtime_msgfmt_prefix_final_unchanged']):
        raise ValueError('Setup PASS needs complete same-run double branch and closure')
    phases = result['phases']
    if len(phases) != 6 or any(p['exit'] != 0 or p['reason'] is not None for p in phases):
        raise ValueError('Exact ownedprefix original four native probes required')
    tools = context['dependency']
    owned = prepared['owned']
    gpg = json.loads(tools.owned_debian_file_io(owned / 'actual-build/source-auth/source-identity.json', decode=True))
    def row(p):
        return dict(status='PASS', exit_code=p['exit'], elapsed_ms=int(p['seconds'] * 1000))
    probe_seconds = state['completed_monotonic'] - (state['deadline'] - 30)
    if probe_seconds >= 30 or probe_seconds < 0:
        raise TimeoutError('Shared original probe30 exceeded')
    head = original_restore.git(management, 'rev-parse', 'HEAD').decode().strip()
    inventory = json.loads((Path(management) / 'scripts/rc_native_probe_inventory.json').read_bytes())
    inventory_hash = lambda key: hashlib.sha256(json.dumps(inventory[key], separators=(',', ':')).encode()).hexdigest()
    records = {
        public.FILES[0]: dict(schema=public.SCHEMA, scope='compatible-publisher-component-only', setup_status='PASS',
            profiles=dict(necessary85=profile, original300=dict(profile)), release_authorized=False,
            product_install_runs=0, projection_only=True, phases=dict(
                gpg=dict(status='PASS', exit_code=0, elapsed_ms=int(gpg['shared_gpg_seconds']*1000)),
                build=row(phases[0]), install=row(phases[1]),
                probe=dict(status='PASS', exit_code=0, elapsed_ms=int(probe_seconds*1000)))),
        public.FILES[1]: dict(schema=public.SCHEMA, repository='Eswink/coding-tools-mcp', management_commit=head,
            source_tree=source['tree'], backup_commit=source['backup'], pure_source_count=source['count'],
            runner_bytes=6259, runner_sha256=original_restore.RUNNER_SHA, fixture_sha256=original_restore.FIXTURE_SHA,
            inventory85_sha256=inventory_hash('necessary85'), inventory300_sha256=inventory_hash('original300')),
        public.FILES[2]: dict(schema=public.SCHEMA, git_version='2.55.0', image_platform='linux/amd64',
            runtime_kind='HOSTED_VM', image_provenance=dict(kind='HOSTED_VM', image_version=os.environ.get('ImageVersion'),
                container_manifest_digest=None, container_config_digest=None, provenance_verified=False),
            archive_sha256=prepare.SOURCE_SHA, signature_sha256=prepare.SIGN_SHA, key_sha256=prepare.KEY_SHA,
            tar_sha256=gpg['tar_sha256'], builder_source_sha256=prepare.V4_SHA,
            installed_binary_sha256=result['installed_binary']['sha256'],
            build_log_sha256=phases[0]['log_sha256'], install_log_sha256=phases[1]['log_sha256'],
            archive_bytes=8177180, signature_bytes=566, key_bytes=68820, tar_bytes=51916800,
            gpg_primary=gpg['primary_fingerprint'], gpg_subkey=gpg['subkey_fingerprint'],
            signature_valid=True, system_git_unchanged=True, prefix_preabsent=True, configs_count=2,
            gitk_upstream_fallback_observed=None),
        public.FILES[3]: dict(schema=public.SCHEMA, projection_only=True, original_raw_available_privately='UNAVAILABLE',
            profiles={name: dict(original_seal_sha256=None, files=[]) for name in ('necessary85', 'original300')})}
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--management', required=True)
    parser.add_argument('--runner-temp', required=True)
    parser.add_argument('--mode', choices=['preparation-only'], required=True)
    args = parser.parse_args()
    management = Path(args.management).resolve()
    if (os.environ.get('GITHUB_EVENT_NAME') != 'push'
            or os.environ.get('GITHUB_REPOSITORY') != 'Eswink/coding-tools-mcp'
            or os.environ.get('GITHUB_REF') != 'refs/heads/' + BRANCH
            or original_restore.git(management, 'rev-parse', 'HEAD').decode().strip() != os.environ.get('GITHUB_SHA')
            or original_restore.git(management, 'status', '--porcelain', '--untracked-files=all') != b''):
        raise ValueError('Real reviewed GitHub event/current native source required')
    context = prepare.preflight_disposable_realm(management, args.runner_temp)
    source = _source_context(management, context)
    inputs = _fetch_inputs(context)
    _role_callbacks(management, context)
    prepared = prepare.prepare_genuine_git(management, context, inputs)
    prepare.verify_genuine_install(prepared)
    if context['dependency'].snapshot_debian_tool(role.TARGET, native=True) != context['role_state']['actual_role']:
        raise ValueError('Final single role drift')
    prepare.read_current_tool_lease(context)
    records = _projections(management, context, source, prepared)
    public.project_public_evidence(records, Path(context['root']) / 'rc070-public-artifacts')
    # No original tests are executed or implicitly admitted by genuine tool PASS.
    if _SUT_RUNS != 0:
        raise ValueError('Unexpected Publisher test execution')
    print('PASS_GENUINE_TOOL_PREPARATION_ONLY_SUT0')
    return 0


if __name__ == '__main__':
    try:
        code = main()
    except BaseException:
        # This is a fixed private-captured status. Workflow never prints raw file.
        print('FAIL_OR_BLOCKED_GENUINE_TOOL_PREPARATION_SUT0')
        code = 1
    raise SystemExit(code)
