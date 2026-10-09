"""Known-executable ordinary loader facts; never native/publication authority.

No query runs at import. Admission is deliberately narrow: the sealed 3.12
outer, its fixed loader, no non-main RPATH/RUNPATH, no alternate hwcap or
unbounded candidate context. Future query execution needs separate root review.
"""
import errno
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import struct
import subprocess
import time
import types

HERE = Path(__file__).resolve().parent
SOURCE = Path('/workspace/work/rc070/startup-native-birth-spec-next/external/rc_native_startup_owner')
BUILDER = SOURCE / 'build_source_owner.py'
BUILDER_SHA = '877d975b2221e24ecf2d86eddd13499c10b70bc8994b1bc0f6d0cea926e78dab'
OUTER = Path('/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python3.12')
OUTER_SHA = 'fa67443527ed9647f760d807e2a38f26340757123e643c4639cf273ed15d5ea7'
LOADER_LITERAL = Path('/lib64/ld-linux-x86-64.so.2')
LOADER = Path('/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2')
LOADER_SHA = '438c546d8e8cc48496bf3a95f753051afd9db66a629a74e31a9ded71586b56e0'
ENV = {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'TZ': 'UTC'}
DEFAULTS = tuple(map(Path, ('/lib/x86_64-linux-gnu', '/usr/lib/x86_64-linux-gnu', '/lib', '/usr/lib')))
LOG_LIMIT, JOB_SECONDS = 2 * 1024 * 1024, 120.0
_BUILDER = None
_ADMISSIONS = {}
_JOB_HOLDERS = []
_BOOTSTRAP_HOLDERS = []


class QueryAdmission:
    """No public constructor, numeric owner input, mutable state or subclass."""
    __slots__ = ()

    def __new__(cls, *args, **kwargs):
        raise TypeError('ordinary_admission_has_no_public_constructor')


def _read_bootstrap_bytes():
    if len(_BOOTSTRAP_HOLDERS) >= 4096:
        raise RuntimeError('bootstrap_unknown_holder_bound')
    holder = {'object': None, 'state': 'PREALLOCATED', 'close_attempted': False,
              'factory_attempted': False, 'errors': []}
    _BOOTSTRAP_HOLDERS.append(holder)  # before the actual file creator
    primary, failures, data = None, [], None
    try:
        holder['factory_attempted'] = True
        holder['object'] = open(BUILDER, 'rb')
        holder['state'] = 'OWNED'
        before = os.fstat(holder['object'].fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > 1024 * 1024:
            raise RuntimeError('bootstrap_source_not_bounded_regular_file')
        data = holder['object'].read(1024 * 1024 + 1)
        after = os.fstat(holder['object'].fileno())
        if len(data) > 1024 * 1024 or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise RuntimeError('bootstrap_source_changed_during_actual_read')
    except BaseException as error:
        primary = error
        holder['errors'].append(error)
        holder['state'] = 'UNKNOWN'
    finally:
        if holder['object'] is not None:
            holder['close_attempted'] = True
            try:
                holder['object'].close()
                holder['state'] = 'CLOSED'
                for index, item in enumerate(_BOOTSTRAP_HOLDERS):
                    if item is holder:
                        del _BOOTSTRAP_HOLDERS[index]
                        break
                holder['object'] = None  # only after actual successful close
            except BaseException as error:
                holder['state'] = 'UNKNOWN'
                holder['errors'].append(error)
                failures.append(error)
        else:
            holder['state'] = 'UNKNOWN' if holder['factory_attempted'] else 'CLOSED'
    errors = ([primary] if primary is not None else []) + failures
    if errors:
        if len(errors) == 1:
            raise errors[0]
        raise BaseExceptionGroup('bootstrap_source_primary_and_close_failures', errors)
    return data


def load_builder_readonly():
    global _BUILDER
    if _BUILDER is None:
        data = _read_bootstrap_bytes()
        if hashlib.sha256(data).hexdigest() != BUILDER_SHA:
            raise RuntimeError('fixed_builder_source_changed_before_execution')
        # Execute those exact verified bytes, never a second unchecked file read.
        # No main/compile/bridge/factory entry is invoked by this helper import.
        module = types.ModuleType('rc_fixed877_ordinary_file_helpers')
        module.__file__ = str(BUILDER)
        exec(compile(data, str(BUILDER), 'exec'), module.__dict__)
        if module.file_identity(BUILDER)['sha256'] != BUILDER_SHA:
            raise RuntimeError('fixed_builder_source_changed')
        _BUILDER = module
    return _BUILDER


def expand_search_paths(paths, origin):
    result = []
    for entry in paths:
        text = entry.replace('${ORIGIN}', str(origin)).replace('$ORIGIN', str(origin))
        if not text or '$' in text or not text.startswith('/') or '\x00' in text or ':' in text:
            raise RuntimeError('unsupported_dynamic_search_token_or_relative_component')
        result.append(str(Path(os.path.normpath(text))))
    return result


def validate_elf_policy(info):
    if info.get('kind') not in (2, 3):
        raise RuntimeError('nonruntime_ELF_kind')
    callbacks = {0x6ffffefa, 0x6ffffefb, 0x6ffffefc, 0x7ffffffd, 0x7fffffff}
    for tag, value in info['dynamic']:
        if tag in callbacks:
            raise RuntimeError('callback_or_external_configuration_dynamic_tag')
        # Explicit finite flags: NOW/ORIGIN/SYMBOLIC/BIND_NOW/STATIC_TLS;
        # FLAGS_1 NOW/NODELETE/ORIGIN/PIE only. No speculative flags.
        if tag == 30 and value & ~0x1f:
            raise RuntimeError('unsupported_DT_FLAGS')
        if tag == 0x6ffffffb and value & ~(0x1 | 0x8 | 0x80 | 0x08000000):
            raise RuntimeError('unsupported_DT_FLAGS_1')
    for name in info['needed']:
        if not re.fullmatch(r'[A-Za-z0-9_.+\-]+', name) or name in ('.', '..'):
            raise RuntimeError('unsupported_DT_NEEDED_name')
    expand_search_paths(info['rpath'], '/ordinary-origin-shape-only')
    expand_search_paths(info['runpath'], '/ordinary-origin-shape-only')
    return {'callbacks_rejected': True, 'role': 'ordinary_candidate_policy_only'}


def read_elf_policy(builder, path):
    data = builder.read_bytes_owned(path)
    parsed = builder.elf_dependencies(path)
    if hashlib.sha256(data).hexdigest() != parsed['parsed_bytes_sha256']:
        raise RuntimeError('ELF_changed_between_two_actual_reads')
    header = struct.unpack_from('<HHIQQQIHHHHHH', data, 16)
    dynamic = []
    for index in range(header[9]):
        program = struct.unpack_from('<IIQQQQQQ', data, header[4] + index * header[8])
        if program[0] == 2:
            if program[2] + program[5] > len(data) or program[5] % 16:
                raise RuntimeError('dynamic_policy_table_bounds')
            terminated = False
            for offset in range(program[2], program[2] + program[5], 16):
                tag, value = struct.unpack_from('<qQ', data, offset)
                if not tag:
                    terminated = True
                    break
                dynamic.append((tag, value))
            if not terminated:
                raise RuntimeError('dynamic_policy_table_not_terminated')
    info = {'kind': parsed['type'], 'interpreter': parsed['interpreter'],
            'needed': parsed['needed'], 'rpath': parsed['rpath'], 'runpath': parsed['runpath'],
            'dynamic': dynamic, 'bytes_sha256': parsed['parsed_bytes_sha256']}
    validate_elf_policy(info)
    return info


def check_global_policy(policy):
    if policy['env'] != {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'TZ': 'UTC'}:
        raise RuntimeError('loader_query_requires_exact_replaced_environment')
    if policy['inherited_unsafe'] or policy['secure'] is not False:
        raise RuntimeError('unsafe_or_unknown_loader_execution_context')
    if policy['preload_absent'] is not True or policy['capability_absent'] is not True:
        raise RuntimeError('preload_or_capability_unknown')
    return {'scope': 'ordinary_policy_only', 'qualifies_native': False}


def query_environment_policy(builder):
    # Auxiliary-vector bytes are private, discarded immediately; only AT_SECURE
    # is retained. This future admission read is NOT invoked by data controls.
    raw = builder.read_bytes_owned('/proc/self/auxv', 16384)
    if len(raw) % 16:
        raise RuntimeError('unsupported_auxiliary_vector_layout')
    secure_values = [value for tag, value in struct.iter_unpack('<QQ', raw) if tag == 23]
    if secure_values != [0] or os.getuid() != os.geteuid() or os.getgid() != os.getegid():
        raise RuntimeError('secure_execution_not_proven_false')
    unsafe = sorted(name for name in os.environ if name.startswith('LD_') or name == 'GLIBC_TUNABLES')
    policy = {'env': dict(ENV), 'inherited_unsafe': unsafe, 'secure': False,
              'preload_absent': not os.path.lexists('/etc/ld.so.preload'), 'capability_absent': True}
    check_global_policy(policy)
    return policy


def path_fact(path):
    path = Path(path).absolute()
    try:
        info = path.lstat()
    except FileNotFoundError:
        return {'path': str(path), 'exists': False}
    result = {'path': str(path), 'exists': True, 'dev': info.st_dev, 'ino': info.st_ino,
              'mode': info.st_mode, 'nlink': info.st_nlink, 'mtime_ns': info.st_mtime_ns,
              'ctime_ns': info.st_ctime_ns}
    if path.is_symlink():
        result['link'] = os.readlink(path)
        result['resolved'] = str(path.resolve(strict=True))
    if path.is_dir():
        actual = path.stat()
        if actual.st_uid != 0 or actual.st_mode & 0o022:
            raise RuntimeError('unsafe_native_search_directory')
        names = sorted(os.listdir(path))  # no exposed iterator/FD to retire
        if len(names) > 4096:
            raise RuntimeError('native_directory_entry_bound')
        result['entries'] = names
        result['actual'] = [actual.st_dev, actual.st_ino, actual.st_mode, actual.st_mtime_ns, actual.st_ctime_ns]
    return result


def snapshot_search_facts(paths):
    paths = sorted(set(map(str, paths)))
    if len(paths) > 4096:
        raise RuntimeError('search_fact_bound')
    return {path: path_fact(path) for path in paths}


def collect_candidates(builder):
    outer = read_elf_policy(builder, OUTER)
    if outer['interpreter'] != str(LOADER_LITERAL) or outer['runpath']:
        raise RuntimeError('unsupported_first_outer_interpreter_or_RUNPATH')
    inherited = list(map(Path, expand_search_paths(outer['rpath'], OUTER.parent)))
    roots = inherited + list(DEFAULTS)
    cache = builder.cache_entries()
    aliases = {str(OUTER): str(OUTER), str(LOADER): str(LOADER), str(LOADER_LITERAL): str(LOADER)}
    infos, pending = {str(OUTER): outer}, [OUTER, LOADER]
    facts = set(map(str, roots)) | {'/etc/ld.so.preload', '/etc/ld.so.cache', '/etc/ld.so.conf', '/etc/ld.so.conf.d'}
    seen_names = set()
    while pending:
        path = pending.pop()
        canonical = str(path.resolve(strict=True))
        if canonical not in infos:
            infos[canonical] = read_elf_policy(builder, path)
        info = infos[canonical]
        if canonical != str(OUTER) and (info['rpath'] or info['runpath'] or info['interpreter']):
            raise RuntimeError('nonmain_loader_ancestry_or_search_context_unbounded')
        for name in info['needed']:
            if name in seen_names:
                continue
            seen_names.add(name)
            if len(seen_names) > 128 or len(infos) > 128:
                raise RuntimeError('candidate_closure_bound')
            candidates = [root / name for root in roots]
            for cached, hwcap in cache.get(name, []):
                if hwcap:
                    raise RuntimeError('cached_hardware_variant_unbounded')
                candidates.append(cached)
            existing = set()
            for root in roots:
                # Hwcaps selection and legacy platform paths are rejected if
                # any potentially selected variant for a needed name exists.
                hwroot = root / 'glibc-hwcaps'
                facts.add(str(hwroot))
                if hwroot.exists():
                    for leaf in os.listdir(hwroot):
                        candidate = hwroot / leaf / name
                        facts.update((str(hwroot / leaf), str(candidate)))
                        if candidate.exists():
                            raise RuntimeError('hardware_directory_variant_unbounded')
                for leaf in ('tls', 'haswell', 'x86_64'):
                    candidate = root / leaf / name
                    facts.update((str(root / leaf), str(candidate)))
                    if candidate.exists():
                        raise RuntimeError('legacy_platform_variant_unbounded')
            for candidate in candidates:
                facts.add(str(candidate))
                facts.add(str(candidate.parent))
                if not os.path.lexists(candidate):
                    continue
                canonical_candidate = str(candidate.resolve(strict=True))
                if not candidate.is_file():
                    raise RuntimeError('nonregular_declared_candidate')
                aliases[str(candidate)] = canonical_candidate
                aliases[canonical_candidate] = canonical_candidate
                existing.add(canonical_candidate)
                if canonical_candidate not in infos:
                    infos[canonical_candidate] = read_elf_policy(builder, candidate)
                    pending.append(candidate)
            if not existing:
                raise RuntimeError('missing_all_declared_dependency_candidates:' + name)
    return {'candidate_info': infos, 'candidate_aliases': aliases,
            'allowed_paths': sorted(infos), 'fact_paths': sorted(facts),
            'scope': 'known_outer_only_no_plugin_host', 'plugin_context': 'BLOCKED_UNKNOWN'}


def capture_native_context(builder):
    policy = query_environment_policy(builder)
    candidates = collect_candidates(builder)
    files = set(candidates['allowed_paths']) | {str(LOADER_LITERAL), '/etc/ld.so.cache'}
    for path in ('/etc/ld.so.conf',):
        if os.path.lexists(path):
            files.add(path)
    confdir = Path('/etc/ld.so.conf.d')
    if confdir.exists():
        for name in os.listdir(confdir):
            item = confdir / name
            if not item.is_file():
                raise RuntimeError('unsupported_loader_config_entry')
            files.add(str(item))
    source_files = [SOURCE / name for name in builder.SOURCE_NAMES] + [HERE / 'loader_query_context.py', HERE / 'loader_query_controls.py']
    files.update(map(str, source_files))
    for path in candidates['allowed_paths']:
        info = Path(path).stat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & (0o6000 | 0o022):
            raise RuntimeError('unsafe_loader_or_candidate_file_mode')
        try:
            cap = os.getxattr(path, 'security.capability')
        except OSError as error:
            if error.errno != errno.ENODATA:
                raise RuntimeError('candidate_capability_unknown') from error
        else:
            if cap:
                raise RuntimeError('candidate_capability_present')
    sealed = builder.snapshot(files)
    if sealed[str(OUTER)]['sha256'] != OUTER_SHA or sealed[str(LOADER)]['sha256'] != LOADER_SHA:
        raise RuntimeError('fixed_outer_or_loader_identity_changed')
    if sealed[str(LOADER_LITERAL)]['resolved'] != str(LOADER) or sealed[str(LOADER_LITERAL)]['sha256'] != LOADER_SHA:
        raise RuntimeError('literal_interpreter_alias_not_bound_to_fixed_loader')
    if sealed[str(BUILDER)]['sha256'] != BUILDER_SHA:
        raise RuntimeError('fixed_builder_changed')
    for path in source_files:
        if stat.S_IMODE(path.stat().st_mode) != 0o644 or path.stat().st_nlink != 1:
            raise RuntimeError('source_physical_mode_or_link_count_changed')
    return {'policy': policy, 'candidates': candidates, 'files': sealed,
            'search_facts': snapshot_search_facts(candidates['fact_paths']),
            'argv': [str(LOADER), '--list', str(OUTER)], 'env': dict(ENV),
            'source_build_identity_proof': False, 'qualifies_native': False}


def validate_query_admission():
    builder = load_builder_readonly()
    before = capture_native_context(builder)
    after = capture_native_context(builder)
    if before != after:
        raise RuntimeError('context_changed_during_readonly_admission')
    if len(_ADMISSIONS) >= 8:
        raise RuntimeError('ordinary_admission_registry_bound')
    admission = object.__new__(QueryAdmission)
    _ADMISSIONS[admission] = {'builder': builder, 'context': before}
    return admission


def authentic_state(admission):
    if type(admission) is not QueryAdmission or admission not in _ADMISSIONS:
        raise TypeError('not_internally_registered_ordinary_query_admission')
    return _ADMISSIONS[admission]


def _parse_listing_data(stdout, state):
    if not isinstance(stdout, bytes) or len(stdout) > LOG_LIMIT:
        raise RuntimeError('bounded_raw_loader_stdout_required')
    aliases, infos = state['candidate_aliases'], state['candidate_info']
    allowed, loader = set(state['allowed_paths']), state['loader']
    roles, selected, names, vdso = [], set(), set(), False
    declared = {name for info in infos.values() for name in info['needed']}
    for line in stdout.decode('utf-8', errors='strict').splitlines():
        line = line.strip()
        if re.fullmatch(r'linux-vdso\.so\.1 \(0x[0-9a-f]+\)', line):
            if vdso:
                raise RuntimeError('duplicate_virtual_vdso_role')
            vdso = True
            roles.append({'kind': 'vdso', 'name': 'linux-vdso.so.1', 'path': None})
            continue
        dependency = re.fullmatch(r'([A-Za-z0-9_.+\-]+) => (/[^\s]+) \(0x[0-9a-f]+\)', line)
        own_loader = re.fullmatch(r'(/[^\s]+) \(0x[0-9a-f]+\)', line)
        if dependency:
            name, alias = dependency.groups()
            if name not in declared or name in names:
                raise RuntimeError('unknown_or_duplicate_dependency_role')
            kind = 'dependency'
            names.add(name)
        elif own_loader:
            alias, name, kind = own_loader.group(1), 'fixed_loader', 'loader'
        else:
            raise RuntimeError('unsupported_or_not_found_loader_output')
        canonical = aliases.get(alias)
        if canonical not in allowed or canonical in selected:
            raise RuntimeError('unsealed_or_duplicate_loader_path')
        if (kind == 'loader') != (canonical == loader):
            raise RuntimeError('mismatched_loader_output_role')
        if kind == 'loader' and Path(alias).name in declared:
            names.add(Path(alias).name)
        if kind == 'dependency' and Path(alias).name != name:
            raise RuntimeError('dependency_loaded_alias_does_not_match_needed_name')
        selected.add(canonical)
        roles.append({'kind': kind, 'name': name, 'path': canonical})
    if loader not in selected or not vdso:
        raise RuntimeError('missing_loader_or_virtual_role')
    required = set(infos[state['target']]['needed'])
    for path in selected:
        required.update(infos[path]['needed'])
    if names != required:
        raise RuntimeError('missing_or_extraneous_required_dependency_role')
    return {'roles': roles, 'selected_paths': sorted(selected), 'qualifies_native': False}


def parse_loader_list(stdout, admission):
    state = authentic_state(admission)
    context = state['context']
    candidates = context['candidates']
    return _parse_listing_data(stdout, dict(candidates, target=str(OUTER), loader=str(LOADER)))


def parse_loader_listing(stdout, admission):
    return parse_loader_list(stdout, admission)


def verify_after(admission):
    state = authentic_state(admission)
    current = capture_native_context(state['builder'])
    if current != state['context']:
        raise RuntimeError('actual_native_input_or_search_policy_fence_changed')
    return {'actual_full_fences_equal': True, 'qualifies_native': False}


def query_loader_context(admission, out_dir):
    return ordinary_job(admission, out_dir)


def _finish_after_fences(admission, record, start, failures):
    """Independent afterfence and total-deadline attempts; preserve each object.

    This helper does not release a process holder or qualify any native family.
    Data controls may replace its observers with explicit pure mocks.
    """
    try:
        record['after_fences'] = verify_after(admission)
    except BaseException as error:
        failures.append(error)
    try:
        record['elapsed_seconds'] = time.monotonic() - start
        if record['elapsed_seconds'] >= JOB_SECONDS:
            raise RuntimeError('query_total_deadline_exhausted_after_retirement_and_fences')
    except BaseException as error:
        failures.append(error)


def ordinary_job(admission, out_dir):
    """Future-only actual ordinary query; separate root startup permission required."""
    start = time.monotonic()  # shared120 starts before admission/fences/creation
    registered = authentic_state(admission)
    verify_after(admission)  # all native/search/callback policy BEFORE creator
    if registered.get('attempted', False):
        raise RuntimeError('ordinary_admission_single_attempt_only')
    registered['attempted'] = True  # sticky before any creation attempt
    argv = [str(LOADER), '--list', str(OUTER)]
    context = registered['context']
    if context['argv'] != argv or context['env'] != {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'TZ': 'UTC'}:
        raise RuntimeError('ordinary_admission_vector_or_environment_changed')
    if ENV != {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'TZ': 'UTC'}:
        raise RuntimeError('query_environment_literal_changed')
    out = Path(out_dir).absolute()
    if out.is_symlink() or not out.is_dir() or out.resolve(strict=True) != out:
        raise RuntimeError('exclusive_query_output_real_directory_required')
    if stat.S_IMODE(out.stat().st_mode) != 0o700 or os.listdir(out):
        raise RuntimeError('exclusive_empty0700_query_output_required')
    builder = registered['builder']
    new_holder, close_resource = builder.new_holder, builder.close_resource
    OwnedFile, file_identity = builder.OwnedFile, builder.file_identity
    _FILE_HOLDERS = builder._FILE_HOLDERS
    state, label = {'jobs': [], 'log_bytes': 0}, 'ordinary-loader-list'
    record = {'argv': list(map(str, argv)), 'label': label, 'limit_seconds': JOB_SECONDS}
    state['jobs'].append(record)
    # All reachability/storage exists before Popen or selector creates anything.
    holder = new_holder(_JOB_HOLDERS, 'actual-loader_query-process')
    resources = {name: new_holder(_FILE_HOLDERS, 'loader_query-' + name)
                 for name in ('stdout', 'stderr', 'selector')}
    holder['resources'] = resources
    outputs = {'stdout': bytearray(), 'stderr': bytearray()}
    process, streams, primary = None, None, None
    failures, interrupted, kill_sent = [], False, False
    try:
        if time.monotonic() - start >= JOB_SECONDS:
            raise RuntimeError('query_shared_deadline_exhausted_before_creator')
        holder['factory_attempted'] = True
        # FIRST actual Popen-return store is inside this protected region.
        holder['object'] = subprocess.Popen(
            record['argv'], cwd=out, env=ENV, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=True, close_fds=True)
        holder['state'] = 'OWNED'
        process = holder['object']
        # The retained Popen itself already strongly owns both actual pipes.
        for name in ('stdout', 'stderr'):
            resources[name]['factory_attempted'] = True
            resources[name]['object'] = getattr(process, name)
            resources[name]['state'] = 'OWNED'
        record['actual_created_loader_query_pid'] = process.pid  # diagnostic, no grant
        resources['selector']['factory_attempted'] = True
        resources['selector']['object'] = selectors.DefaultSelector()
        resources['selector']['state'] = 'OWNED'
        streams = resources['selector']['object']
        for name in outputs:
            stream = resources[name]['object']
            os.set_blocking(stream.fileno(), False)
            streams.register(stream, selectors.EVENT_READ, name)
        while streams.get_map() or process.poll() is None:
            elapsed = time.monotonic() - start
            if elapsed >= JOB_SECONDS - 4 and not interrupted:
                interrupted = True
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            if elapsed >= JOB_SECONDS - 2 and not kill_sent:
                kill_sent = True
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if elapsed >= JOB_SECONDS:
                raise RuntimeError('loader_query_job_terminal_or_EOF_UNKNOWN')
            for key, _ in streams.select(min(0.1, JOB_SECONDS - elapsed)):
                data = os.read(key.fileobj.fileno(), 65536)
                if not data:
                    streams.unregister(key.fileobj)
                    continue
                available = LOG_LIMIT - state['log_bytes']
                outputs[key.data].extend(data[:available])
                state['log_bytes'] += min(len(data), available)
                if len(data) > available:
                    record['log_overlimit'] = True
                    record['unpreserved_bytes_after_limit'] = record.get('unpreserved_bytes_after_limit', 0) + len(data) - available
                    interrupted = True
                    if not kill_sent:
                        kill_sent = True
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
        record['exit'] = process.wait(timeout=max(0.001, JOB_SECONDS - (time.monotonic() - start)))
        record['pipe_eof'] = True
        if interrupted or record['exit'] != 0:
            raise RuntimeError('loader_query_or_inspection_job_failed: ' + label)
    except BaseException as error:
        primary = error
        holder['state'] = 'UNKNOWN'
        holder['errors'].append(error)
        # Use the true retained return, even if a later observation/selector failed.
        process = holder['object']
        if process is not None:
            try:
                if process.poll() is None:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            except BaseException as cleanup_error:
                failures.append(cleanup_error)
            try:
                remaining = JOB_SECONDS - (time.monotonic() - start)
                if remaining <= 0:
                    raise RuntimeError('loader_query_terminal_UNKNOWN_at_fixed_deadline')
                process.wait(timeout=remaining)
            except BaseException as cleanup_error:
                failures.append(cleanup_error)
        streams = resources['selector']['object']
        if streams is not None:
            try:
                while streams.get_map():
                    remaining = JOB_SECONDS - (time.monotonic() - start)
                    if remaining <= 0:
                        raise RuntimeError('loader_query_pipe_EOF_UNKNOWN_at_fixed_deadline')
                    for key, _ in streams.select(min(0.1, remaining)):
                        data = os.read(key.fileobj.fileno(), 65536)
                        if not data:
                            streams.unregister(key.fileobj)
                            continue
                        available = LOG_LIMIT - state['log_bytes']
                        outputs[key.data].extend(data[:available])
                        state['log_bytes'] += min(len(data), available)
                        if len(data) > available:
                            record['unpreserved_bytes_after_limit'] = record.get('unpreserved_bytes_after_limit', 0) + len(data) - available
                record['pipe_eof'] = True
            except BaseException as cleanup_error:
                failures.append(cleanup_error)
    finally:
        try:
            record['elapsed_seconds'] = time.monotonic() - start
            if holder['object'] is not None:
                record['observed_returncode'] = holder['object'].poll()
        except BaseException as cleanup_error:
            failures.append(cleanup_error)
        for name, data in outputs.items():
            path = out / (label + '.' + name)
            try:
                with OwnedFile(path, 'xb') as stream:
                    stream.write(data)
            except BaseException as cleanup_error:
                failures.append(cleanup_error)
            try:
                record[name] = file_identity(path)
            except BaseException as cleanup_error:
                failures.append(cleanup_error)
        # No failing item may skip another actual owned close. UNKNOWN holders
        # remain linked with actual objects; no integer-FD retry or reconstruction.
        for name in ('selector', 'stdout', 'stderr'):
            try:
                failures.extend(close_resource(resources[name]))
            except BaseException as cleanup_error:
                failures.append(cleanup_error)
        try:
            record['resource_states'] = {name: item['state'] for name, item in resources.items()}
        except BaseException as cleanup_error:
            failures.append(cleanup_error)
        # Failure/cancellation never skips the actual new afterfence attempt;
        # any failure joins all original primary/cleanup objects below.
        try:
            _finish_after_fences(admission, record, start, failures)
        except BaseException as cleanup_error:
            failures.append(cleanup_error)
    errors = ([primary] if primary is not None else []) + failures
    if errors:
        holder['state'] = 'UNKNOWN'
        holder['errors'].extend(failures)
        try:
            record['loader_query_holder_state'] = 'UNKNOWN_RETAINED'
            record['primary_and_cleanup_error_types'] = [type(error).__name__ for error in errors]
            record['terminal_and_EOF_is_not_native_family_qualification'] = True
        except BaseException as observation_error:
            errors.append(observation_error)
            holder['errors'].append(observation_error)
        if len(errors) == 1:
            raise errors[0]
        raise BaseExceptionGroup('loader_query_primary_and_independent_cleanup_failures', errors)
    try:
        raw_result = {name: bytes(data) for name, data in outputs.items()}
        if raw_result['stderr']:
            raise RuntimeError('unexpected_loader_query_stderr')
        factual = parse_loader_list(raw_result['stdout'], admission)
        after_fences = record['after_fences']
        result = {'ordinary_facts': factual, 'job_record': record, 'fences_after': after_fences,
                  'qualifies_native': False, 'original_sut': 'NOTRUN', 'compiler': 'NOTRUN'}
        record['elapsed_seconds'] = time.monotonic() - start
        if record['elapsed_seconds'] >= JOB_SECONDS:
            raise RuntimeError('query_total_deadline_exhausted_before_result_release')
        record['loader_query_holder_state'] = 'RELEASED'
        holder['state'] = 'RELEASED'
        for index, item in enumerate(_JOB_HOLDERS):
            if item is holder:
                del _JOB_HOLDERS[index]
                break
        holder['object'] = None  # only verified terminal, EOF and successful closes
        return result
    except BaseException as observation_error:
        holder['state'] = 'UNKNOWN'
        holder['errors'].append(observation_error)
        if not any(item is holder for item in _JOB_HOLDERS):
            _JOB_HOLDERS.append(holder)
        raise
