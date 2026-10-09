"""Genuine preparation adapter; no compiler/install/build/probe on import.

Copies exact reviewed V4/resource sources into a new owned root and adapts only
runtime/path/msgfmt predicates. Original snapshot and owned-phase functions
are retained byte-for-byte; this adapter is explicitly a new execution scope.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import time
import lzma

from rc_disposable_git_role_install import HeldFD

_CAPTURE = None
_CAPTURE_SEQUENCE = 0
import types

V4_SHA = 'a21b053058b1365d5b547c4983a3338ba8f3b4b844d16fc795bcd0c31a1bbe48'
DEB_SHA = '382f47e98cb5e782e4080f781ba930a42a265a5d83250507199045b1d28ba0aa'
SOURCE_SHA = '457fdb04dc8728e007d4688695e6912e6f680727920f2a40bf11eacc17505357'
SIGN_SHA = '8673501946204c38ebfed09603c1f3a041ed8d12b31f0aa06a474d41e359e254'
KEY_SHA = 'fd2809d850e844b614ac60f13ded554c55d9052e5c799a5814abcba2a68a063c'
PREFIX = ('--no-pager', '--no-replace-objects', '--no-optional-locks', '--no-lazy-fetch',
          '-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false',
          '-c', 'core.untrackedCache=false', '-c', 'credential.helper=',
          '-c', 'protocol.allow=never')
SOURCE_NAMES = ('owned_git_prepare_v4.py', 'rc_disposable_git_prepare.py',
                *(f'docs/specs/issue88-disposable-publisher-git-role/{name}.md'
                  for name in ('requirements', 'design', 'tasks')))
HOST = ('/usr/bin/git', '/usr/bin/cc', '/usr/bin/c++', '/usr/bin/make', '/usr/bin/gpg',
        '/usr/bin/python3', '/usr/bin/openssl', '/usr/bin/timeout', '/usr/bin/curl',
        '/usr/bin/msgfmt', '/usr/bin/ar', '/usr/bin/ranlib', '/usr/bin/readelf',
        '/usr/bin/ldd', '/usr/bin/nm', '/usr/bin/strip', '/bin/sh')
ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C', 'TZ': 'UTC',
       'PYTHONDONTWRITEBYTECODE': '1', 'GIT_CONFIG_NOSYSTEM': '1',
       'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_NO_REPLACE_OBJECTS': '1',
       'GIT_TERMINAL_PROMPT': '0'}


def _module(raw, name, filename):
    m = types.ModuleType(name)
    m.__file__ = str(filename)
    exec(compile(raw, str(filename), 'exec'), m.__dict__)
    return m


def _read_exact(path, digest):
    holder = HeldFD()
    primary, data = None, bytearray()
    try:
        holder.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        fd = holder.fd
        s = os.fstat(fd)
        if not stat.S_ISREG(s.st_mode) or s.st_size > 65536:
            raise ValueError('Bounded regular source required')
        while len(data) <= 65536:
            row = os.read(fd, min(65536, 65537 - len(data)))
            if not row:
                break
            data.extend(row)
        if len(data) != s.st_size or hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('Frozen source bytes mismatch')
    except BaseException as error:
        primary = error
    errors = []
    try:
        holder.close()
    except BaseException as error:
        # Actual UNKNOWN holder retains its returned FD; no reuse/retry.
        errors.append(error)
    if errors:
        raise BaseExceptionGroup('Source primary and close failures',
                                 ([primary] if primary is not None else []) + errors)
    if primary is not None:
        raise primary
    return bytes(data)


def _initialize_capture(management, root):
    global _CAPTURE
    vendor = Path(management) / 'scripts/rc_disposable_vendor'
    resource = _module(_read_exact(vendor / 'owned_debian_msgfmt_prepare.py', DEB_SHA),
                       'bounded_capture_resource', vendor / 'owned_debian_msgfmt_prepare.py')
    resource.ROOT = root
    kernel = _module(_read_exact(vendor / 'owned_git_prepare_v4.py', V4_SHA),
                     'exact_bounded_capture_kernel', vendor / 'owned_git_prepare_v4.py')
    kernel.OWNED_ROOT = root
    kernel.load_reviewed_git_dependencies = lambda: resource
    directory = root / 'rc070-private-capture'
    directory.mkdir(mode=0o700)
    _CAPTURE = {'kernel': kernel, 'resource': resource, 'root': root,
                'directory': directory, 'phases': [], 'unknown_streams': []}


def _run_dual_capture(vector, root, env, seconds):
    """New dual-stream collector; vendor collector and its AST stay exact.

    Combined live reads cap 2MiB; overflow keeps bounded prefix and FAIL.
    Only the created Popen is cleaned; no process identity authorizes publisher.
    """
    import selectors
    import signal
    started = time.monotonic()
    process, selector, primary, errors = None, None, None, []
    streams = {'stdout': bytearray(), 'stderr': bytearray()}
    reason = None
    selector = selectors.DefaultSelector()
    try:
        process = subprocess.Popen(vector, cwd=root, env=env, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True, close_fds=True)
        for name in streams:
            selector.register(getattr(process, name), selectors.EVENT_READ, name)
        while selector.get_map():
            remaining = seconds - (time.monotonic() - started)
            if remaining <= 0:
                reason = 'TIMEOUT'
                break
            for key, _ in selector.select(min(.05, remaining)):
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                available = 2*1024*1024 - sum(len(v) for v in streams.values())
                streams[key.data].extend(chunk[:available])
                if len(chunk) > available:
                    reason = 'LOG_LIMIT'
                    break
            if reason is not None:
                break
        if reason is None:
            remaining = seconds - (time.monotonic() - started)
            if remaining <= 0:
                reason = 'TIMEOUT'
            else:
                try:
                    process.wait(timeout=remaining)
                except subprocess.TimeoutExpired:
                    reason = 'TIMEOUT'
    except BaseException as error:
        primary = error
    finally:
        cleanup_deadline = time.monotonic() + 4
        def cleanup_remaining(maximum):
            remaining = cleanup_deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Original shared cleanup4 deadline exhausted')
            return min(maximum, remaining)
        if process is not None:
            try:
                if process.poll() is None or reason is not None or primary is not None:
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    try:
                        process.wait(timeout=cleanup_remaining(2))
                    except subprocess.TimeoutExpired:
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        process.wait(timeout=cleanup_remaining(2))
            except BaseException as error:
                errors.append(error)
            # Independent final created-group retirement attempt remains even
            # when parent wait/poll raises or the parent has exited first.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except BaseException as error:
                errors.append(error)
            # Native reap is independently attempted after the final KILL,
            # including first-poll cancellation. It shares, never adds to,
            # the original absolute2+2 cleanup deadline.
            try:
                process.wait(timeout=cleanup_remaining(4))
            except BaseException as error:
                errors.append(error)
            for name in streams:
                pipe = getattr(process, name)
                if pipe is not None:
                    try:
                        pipe.close()
                    except BaseException as error:
                        # Retain the actual object; UNKNOWN closure is no PASS.
                        _CAPTURE['unknown_streams'].append(pipe)
                        errors.append(error)
        try:
            selector.close()
        except BaseException as error:
            errors.append(error)
    if errors:
        raise BaseExceptionGroup('Capture primary and independent cleanup failures',
                                 ([primary] if primary is not None else []) + errors)
    if primary is not None:
        raise primary
    raw = {name: bytes(value) for name, value in streams.items()}
    return {'exit': process.returncode, 'reason': reason,
            'seconds': time.monotonic()-started,
            'log_bytes': sum(map(len, raw.values())),
            'stdout_sha256': hashlib.sha256(raw['stdout']).hexdigest(),
            'stderr_sha256': hashlib.sha256(raw['stderr']).hexdigest()}, raw


def _capture(vector, *, seconds=30, env=ENV, allow_nonzero=False):
    global _CAPTURE_SEQUENCE
    if _CAPTURE is None or not 0 < seconds <= 480:
        raise ValueError('Current bounded capture initialization required')
    _CAPTURE_SEQUENCE += 1
    phase, streams = _run_dual_capture(vector, _CAPTURE['root'], env, seconds)
    _CAPTURE['phases'].append(phase)
    for name, raw in streams.items():
        log = _CAPTURE['directory'] / ('phase-%04d.%s.log' % (_CAPTURE_SEQUENCE, name))
        _CAPTURE['resource'].owned_debian_file_io(log, data=raw)
    if phase['reason'] is not None or (phase['exit'] != 0 and not allow_nonzero):
        raise ValueError('Bounded native phase failed')
    return (phase, streams['stdout']) if allow_nonzero else streams['stdout']


def preflight_disposable_realm(management, runner_temp):
    if sys.version_info[:2] != (3, 12) or sys.platform != 'linux' or os.geteuid() == 0:
        raise ValueError('Fresh ordinary hosted Python3.12 required')
    root = Path(runner_temp)
    if (root.resolve() != root or not root.is_dir() or root.stat().st_uid != os.geteuid()
            or root.stat().st_mode & 0o022):
        raise ValueError('Literal owned runner temp required')
    if os.path.lexists('/usr/local/bin/git'):
        raise ValueError('Existing additional role cannot be overwritten')
    _initialize_capture(management, root)
    source = Path(management) / 'scripts/rc_disposable_vendor'
    dependency = _module(_read_exact(source / 'owned_debian_msgfmt_prepare.py', DEB_SHA),
                         'exact_disposable_resource_adapter', source / 'owned_debian_msgfmt_prepare.py')
    roles = {name: dependency.snapshot_debian_tool(name) for name in HOST}
    if _capture(['/usr/bin/git', *PREFIX, '--version']).startswith(b'git version ') is False:
        raise ValueError('SystemGit complete original flags required')
    if not _capture(['/usr/bin/msgfmt', '--version']).startswith(b'msgfmt (GNU gettext-tools) '):
        raise ValueError('Genuine existing GNU msgfmt required')
    # Ask an already installed rustup only for the current tool path, never install/update.
    rustup = Path.home() / '.cargo/bin/rustup'
    rustup_role = dependency.snapshot_debian_tool(rustup, native=True)
    rustc = Path(_capture([str(rustup), 'which', 'rustc']).decode('ascii').strip())
    cargo = Path(_capture([str(rustup), 'which', 'cargo']).decode('ascii').strip())
    if (not rustc.is_absolute() or rustc.resolve() != rustc or cargo.resolve() != cargo
            or rustc.parent != cargo.parent):
        raise ValueError('Existing genuine compiler directory required')
    compiler_native = {str(p): dependency.snapshot_debian_tool(p, native=True)
                      for p in (rustc, cargo)}
    compiler_roles = {str(p): dependency.snapshot_debian_tool(p) for p in (rustc, cargo)}
    versions = {}
    for name, path in [('rustc', rustc), ('cargo', cargo)]:
        raw = _capture([str(path), '--version'])
        match = re.fullmatch(name.encode() + rb' ([0-9]+)\.([0-9]+)\.([0-9]+) [^\r\n]+\n', raw)
        if match is None:
            raise ValueError('Exact actual compiler version required')
        versions[name] = tuple(int(x) for x in match.groups())
    # Actual signed Makefile decides its compiler requirement during fullmake;
    # do not remove Rust targets or claim a local1.98.1 predicate was executed.
    return {'root': str(root), 'roles': roles, 'compiler_roles': compiler_roles,
            'compiler_native': compiler_native, 'toolchain': str(rustc.parent), 'versions': versions,
            'rustup_role': rustup_role, 'dependency': dependency}


def read_current_tool_lease(context):
    m = context['dependency']
    result = {name: m.snapshot_debian_tool(name) for name in context['roles']}
    if result != context['roles']:
        raise ValueError('Original hosted role drift')
    compiler = {name: m.snapshot_debian_tool(name)
                for name in context['compiler_roles']}
    if compiler != context['compiler_roles']:
        raise ValueError('Actual compiler drift')
    if m.snapshot_debian_tool(context['rustup_role']['path'], native=True) != context['rustup_role']:
        raise ValueError('Actual rustup drift')
    return result


def _configure_v4(management, owned, context):
    vendor = Path(management) / 'scripts/rc_disposable_vendor'
    raw = _read_exact(vendor / 'owned_git_prepare_v4.py', V4_SHA)
    dependency = context['dependency']
    m = _module(raw, 'exact_v4_with_disclosed_hosted_predicates', owned / SOURCE_NAMES[0])
    m.OWNED_ROOT = owned
    m.SOURCE5 = SOURCE_NAMES  # disclosed accurate CI source-lease role adaptation
    m.DEB_SOURCE = owned / 'owned_debian_msgfmt_prepare.py'
    m.TOOLCHAIN = Path(context['toolchain'])
    dependency.ROOT = owned
    dependency.HOST_TOOLS = tuple(context['roles'])
    # Exact function source/AST is preserved; explicit dependency/path/runtime
    # predicates below are new adapter bindings, never an identical localV4run.
    m.load_reviewed_git_dependencies = lambda: dependency

    def verify_hosted_build_toolchain(evidence):
        evidence = Path(evidence)
        evidence.mkdir(mode=0o700)
        home, cargo_home = evidence / 'build-home', evidence / 'cargo-home'
        home.mkdir(mode=0o700)
        cargo_home.mkdir(mode=0o700)
        if any((m.TOOLCHAIN / Path(role).name).exists() for role in context['roles']):
            raise ValueError('Compiler directory shadows original role')
        read_current_tool_lease(context)
        env = {'PATH': str(m.TOOLCHAIN) + ':/usr/bin:/bin', 'RUSTC': str(m.TOOLCHAIN / 'rustc'),
               'CARGO_HOME': str(cargo_home), 'HOME': str(home), 'LANG': 'C',
               'LC_ALL': 'C', 'TZ': 'UTC'}
        return {'passed': True, 'runtime': dict(context['compiler_roles']),
                'build_env': env, 'versions': dict(context['versions']),
                'INSTALL': False, 'SUT_runs': 0}

    def validate_hosted_msgfmt(receipt):
        data = json.loads(dependency.owned_debian_file_io(receipt, read_limit=65536, decode=True))
        if data != context['msgfmt_predicate']:
            raise ValueError('Actual nativeGNU predicate drift')
        read_current_tool_lease(context)
        base = ['/lib64/ld-linux-x86-64.so.2', '--library-path',
                '/lib/x86_64-linux-gnu:/usr/lib/x86_64-linux-gnu', '/usr/bin/msgfmt']
        return {'config_bytes': m.serialize_msgfmt_config(base).decode('ascii'),
                'vector': base, 'leases': [context['roles']['/usr/bin/msgfmt']],
                'receipt_lease': dependency.snapshot_debian_tool(receipt),
                'receipt_path': str(receipt)}

    m.verify_native_build_toolchain = verify_hosted_build_toolchain
    m.validate_msgfmt_assignment = validate_hosted_msgfmt
    m.verify_git_source = lambda archive, signature, key, evidence: _verify_signed_source(
        m, dependency, archive, signature, key, evidence)
    # Original vendor raw source is exact. This one candidate function has a
    # disclosed AST delta: role-pre/post callbacks share the existing probe30
    # start, with no change to snapshot_original_git_source/run_owned_git_phase.
    tree = ast.parse(raw)
    candidate = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                     and n.name == 'prepare_owned_git_v4')
    candidate = ast.fix_missing_locations(candidate)
    original_ast_sha = hashlib.sha256(ast.dump(candidate, include_attributes=False).encode()).hexdigest()
    class RoleCalls(ast.NodeTransformer):
        def visit_Assign(self, node):
            if any(isinstance(t, ast.Name) and t.id == 'commands' for t in node.targets):
                call = ast.parse('_role_pre(prefix, installed, build_binary, started+30)').body[0]
                return [call, node]
            if any(isinstance(t, ast.Name) and t.id == 'version' for t in node.targets):
                call = ast.parse('_role_post(prefix, started+30)').body[0]
                return [call, node]
            return node
    adapted = ast.fix_missing_locations(ast.Module(body=[RoleCalls().visit(candidate)], type_ignores=[]))
    m._role_pre = context['role_pre']
    m._role_post = context['role_post']
    exec(compile(adapted, str(owned / 'CI-ADAPTED-PREPARE-AST.py'), 'exec'), m.__dict__)
    context['prepare_ast_original_sha256'] = original_ast_sha
    context['prepare_ast_adapted_sha256'] = hashlib.sha256(ast.dump(adapted.body[0], include_attributes=False).encode()).hexdigest()
    return m, raw


def _verify_signed_source(m, dependency, archive, signature, key, evidence):
    """New bounded GPG scope; exact input pins and actual original signature."""
    payloads = []
    for path, size, digest in [(archive, 8177180, SOURCE_SHA),
                               (signature, 566, SIGN_SHA), (key, 68820, KEY_SHA)]:
        raw = dependency.owned_debian_file_io(path, read_limit=size+1)
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError('Exact official source/sign/key pins required')
        payloads.append(raw)
    evidence = Path(evidence)
    evidence.mkdir(mode=0o700)
    home = evidence / 'public-key-home'
    home.mkdir(mode=0o700)
    decoder = lzma.LZMADecompressor(memlimit=128*1024*1024)
    tar = decoder.decompress(payloads[0], max_length=m.MAX_TAR+1)
    if (len(tar) != 51916800 or not decoder.eof or decoder.unused_data
            or hashlib.sha256(tar).hexdigest() != '28d94a29be1ca2669cf05e0220ac7a07742f50b417484bf4bad56595edb8d160'):
        raise ValueError('Original complete tar identity')
    tar_path = evidence / 'git-2.55.0.tar'
    dependency.owned_debian_file_io(tar_path, data=tar)
    keyring = home / 'pinned-public-key.gpg'
    status = evidence / 'developer.status'
    before = dependency.snapshot_debian_tool('/usr/bin/gpg')
    start = time.monotonic()
    _capture(['/usr/bin/gpg', '--homedir', str(home), '--batch', '--no-options',
              '--no-autostart', '--output', str(keyring), '--dearmor', str(key)],
             seconds=30-(time.monotonic()-start))
    if os.path.lexists(status):
        raise ValueError('Fresh private signature status required')
    _capture(['/usr/bin/gpg', '--homedir', str(home), '--batch', '--no-options',
              '--no-autostart', '--no-auto-key-retrieve', '--no-default-keyring',
              '--keyring', str(keyring), '--status-file', str(status),
              '--verify', str(signature), str(tar_path)],
             seconds=30-(time.monotonic()-start))
    raw_status = dependency.owned_debian_file_io(status, read_limit=2*1024*1024+1)
    rows = [line.split() for line in raw_status.decode('ascii').splitlines()]
    valid = [r for r in rows if len(r) >= 12 and r[:2] == ['[GNUPG:]', 'VALIDSIG']]
    bad = {'BADSIG', 'ERRSIG', 'EXPKEYSIG', 'EXPSIG', 'REVKEYSIG', 'KEYEXPIRED',
           'SIGEXPIRED', 'NO_PUBKEY', 'FAILURE'}
    if (len(valid) != 1 or valid[0][2] != m.SUBKEY or valid[0][-1] != m.PRIMARY
            or any(len(r) > 1 and r[1] in bad for r in rows)
            or dependency.snapshot_debian_tool('/usr/bin/gpg') != before
            or dependency.owned_debian_file_io(tar_path, read_limit=m.MAX_TAR+1) != tar):
        raise ValueError('Current pinned original signature or input drift')
    dependency.owned_debian_file_io(evidence / 'source-identity.json', data=json.dumps({
        'source_sha256': SOURCE_SHA, 'tar_sha256': hashlib.sha256(tar).hexdigest(),
        'primary_fingerprint': m.PRIMARY, 'subkey_fingerprint': m.SUBKEY,
        'gpg_exit': 0, 'shared_gpg_seconds': time.monotonic()-start,
        'INSTALL': False, 'SUT_runs': 0, 'publisher_authority': False}))
    return tar


def _prepare_genuine_git_delegate(management, context, inputs):
    """Real phases only when explicitly called by root-reviewed prep entry."""
    root = Path(context['root'])
    owned = root / 'rc070-genuine-git'
    owned.mkdir(mode=0o700)
    m, raw = _configure_v4(management, owned, context)
    context['prefix_snapshot_module'] = m
    dependency = context['dependency']
    dependency.owned_debian_file_io(owned / SOURCE_NAMES[0], data=raw)
    dependency.owned_debian_file_io(owned / 'owned_debian_msgfmt_prepare.py',
                                  data=_read_exact(Path(management) / 'scripts/rc_disposable_vendor/owned_debian_msgfmt_prepare.py', DEB_SHA))
    # Accurate new adapter/docs roles, explicitly configured in SOURCE5; protected
    # function AST is exact, its module-global source role contract is adapted.
    current_paths = [Path(management) / 'scripts/rc_disposable_git_prepare.py',
                     *(Path(management) / f'docs/specs/issue88-disposable-publisher-git-role/{n}.md'
                       for n in ('requirements', 'design', 'tasks'))]
    for name, path in zip(SOURCE_NAMES[1:], current_paths):
        target = owned / name
        target.parent.mkdir(parents=True, exist_ok=True)
        dependency.owned_debian_file_io(target, data=path.read_bytes())
    # Native genuineGNU version + positive + malformed negative control. All
    # outputs are private captured, no invoking a fallback or fixture grant.
    base = ['/lib64/ld-linux-x86-64.so.2', '--library-path',
            '/lib/x86_64-linux-gnu:/usr/lib/x86_64-linux-gnu', '/usr/bin/msgfmt']
    negative = owned / 'malformed-core.po'
    dependency.owned_debian_file_io(negative, data='msgid "broken\nmsgstr "x"\n')
    positive = owned / 'valid-core.po'
    dependency.owned_debian_file_io(positive, data='msgid ""\nmsgstr "Content-Type: text/plain; charset=UTF-8\\n"\n\nmsgid "a"\nmsgstr "b"\n')
    stdout = _capture([*base, '--version'])
    if not stdout.startswith(b'msgfmt (GNU gettext-tools) '):
        raise ValueError('Actual GNU loader version required')
    _capture([*base, '--check', '-o', str(owned / 'positive.mo'), str(positive)])
    bad, bad_raw = _capture([*base, '--check', '-o', str(owned / 'negative.mo'), str(negative)],
                            allow_nonzero=True)
    if bad['exit'] == 0:
        raise ValueError('Original malformedGNU check must reject')
    context['msgfmt_predicate'] = {'status': 'ACTUAL_EXISTING_GNU_COMPONENT_ONLY',
                                  'version_sha256': hashlib.sha256(stdout).hexdigest(),
                                  'malformed_exit': bad['exit'],
                                  'no_package_or_host_install': True}
    predicate = owned / 'native-msgfmt-predicate.json'
    dependency.owned_debian_file_io(predicate, data=json.dumps(context['msgfmt_predicate']))
    current = {name: dependency.snapshot_debian_tool(owned / name) for name in SOURCE_NAMES}
    read_current_tool_lease(context)
    result = m.prepare_owned_git_v4(inputs['archive'], inputs['signature'], inputs['key'],
                                    owned / 'actual-build', predicate, execute=True,
                                    current_source5=current)
    read_current_tool_lease(context)
    return {'result': result, 'owned': owned, 'module': m, 'context': context}


def verify_genuine_install(prepared):
    m, result = prepared['module'], prepared['result']
    if (result.get('status') != 'PASS_OWNED_GIT_BUILD_INSTALL_ONLY'
            or result.get('INSTALL') is not True or result.get('build_runs') != 1
            or result.get('install_runs') != 1 or not result.get('source_runtime_msgfmt_prefix_final_unchanged')):
        raise ValueError('Current complete genuine preparation required')
    prefix = prepared['owned'] / 'actual-build/owned-prefix'
    current = m.snapshot_original_git_source(prefix, installed=True)
    if current != result['installed_manifest']:
        raise ValueError('Complete genuine installednamespace drift')
    read_current_tool_lease(prepared['context'])
    return prefix / 'bin/git'


def prepare_genuine_git(management, context, inputs):
    primary, result, errors = None, None, []
    try:
        result = _prepare_genuine_git_delegate(management, context, inputs)
    except BaseException as error:
        primary = error
    m = context['dependency']
    for path, original in [*context['roles'].items(), *context['compiler_roles'].items()]:
        try:
            if m.snapshot_debian_tool(path) != original:
                raise ValueError('Final original runtime drift')
        except BaseException as error:
            errors.append(error)
    try:
        if m.snapshot_debian_tool(context['rustup_role']['path'], native=True) != context['rustup_role']:
            raise ValueError('Final rustup drift')
    except BaseException as error:
        errors.append(error)
    if errors:
        raise BaseExceptionGroup('Preparation primary and all final role failures',
                                 ([primary] if primary is not None else []) + errors)
    if primary is not None:
        raise primary
    return result
