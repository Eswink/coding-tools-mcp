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
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    primary, data = None, bytearray()
    try:
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
        os.close(fd)
    except BaseException as error:
        # No reuse/retry, and private actual holder remains in the raised group.
        errors.append(error)
    if errors:
        raise BaseExceptionGroup('Source primary and close failures',
                                 ([primary] if primary is not None else []) + errors)
    if primary is not None:
        raise primary
    return bytes(data)


def _capture(vector, *, seconds=30, env=ENV):
    phase = subprocess.run(vector, env=env, capture_output=True, timeout=seconds)
    if len(phase.stdout) + len(phase.stderr) > 2 * 1024 * 1024:
        raise ValueError('Phase output cap')
    if phase.returncode != 0:
        raise ValueError('Required native role phase failed')
    return phase.stdout


def preflight_disposable_realm(management, runner_temp):
    if sys.version_info[:2] != (3, 12) or sys.platform != 'linux' or os.geteuid() == 0:
        raise ValueError('Fresh ordinary hosted Python3.12 required')
    root = Path(runner_temp)
    if (root.resolve() != root or not root.is_dir() or root.stat().st_uid != os.geteuid()
            or root.stat().st_mode & 0o022):
        raise ValueError('Literal owned runner temp required')
    if os.path.lexists('/usr/local/bin/git'):
        raise ValueError('Existing additional role cannot be overwritten')
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
    return m, raw


def prepare_genuine_git(management, context, inputs):
    """Real phases only when explicitly called by root-reviewed prep entry."""
    root = Path(context['root'])
    owned = root / 'rc070-genuine-git'
    owned.mkdir(mode=0o700)
    m, raw = _configure_v4(management, owned, context)
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
    bad = subprocess.run([*base, '--check', '-o', str(owned / 'negative.mo'), str(negative)],
                         env=ENV, capture_output=True, timeout=30)
    if bad.returncode == 0 or len(bad.stdout) + len(bad.stderr) > 2 * 1024 * 1024:
        raise ValueError('Original malformedGNU check must reject')
    context['msgfmt_predicate'] = {'status': 'ACTUAL_EXISTING_GNU_COMPONENT_ONLY',
                                  'version_sha256': hashlib.sha256(stdout).hexdigest(),
                                  'malformed_exit': bad.returncode,
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
