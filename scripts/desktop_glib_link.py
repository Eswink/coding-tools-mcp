#!/usr/bin/env python3
"""Rustc observations and target compiler-input ancestry, never linker/code proof."""
from __future__ import annotations
import fcntl
import json
import os
from pathlib import Path
import re
import shlex
import signal
import stat
import subprocess
import time
import uuid

from exact_build_audit import EvidenceError, need

TARGET = 'x86_64-unknown-linux-gnu'
MAX_RECORD, MAX_TRACE, MAX_BINARY = 4 * 1024**2, 64 * 1024**2, 256 * 1024**2
ENVIRONMENT = frozenset(('CARGO_PKG_NAME', 'CARGO_PKG_VERSION', 'CARGO_CRATE_NAME',
    'CARGO_MANIFEST_DIR', 'CARGO_MAKEFLAGS', 'OUT_DIR', 'OPT_LEVEL', 'PROFILE',
    'DEBUG', 'NUM_JOBS', 'TARGET', 'HOST'))
LONG_VALUES = frozenset(('crate-name', 'crate-type', 'edition', 'emit', 'out-dir',
    'target', 'extern', 'cfg', 'check-cfg', 'error-format', 'json', 'cap-lints',
    'color', 'diagnostic-width', 'allow', 'warn', 'deny', 'forbid', 'force-warn'))
CODEGEN = frozenset(('opt-level', 'metadata', 'extra-filename', 'embed-bitcode',
    'debuginfo', 'debug-assertions', 'overflow-checks', 'strip', 'codegen-units',
    'lto', 'panic', 'target-cpu', 'target-feature', 'relocation-model',
    'force-frame-pointers', 'rpath', 'link-arg', 'symbol-mangling-version'))


def canonical(value, cwd='/'):
    need(isinstance(value, str) and value and '\x00' not in value, 'invalid_trace_path')
    need(len(os.fsencode(value)) <= 1024 and '..' not in Path(value).parts, 'unsafe_trace_path')
    return os.path.normpath(value if value.startswith('/') else os.path.join(cwd, value))


def inside(path, root):
    return Path(path).is_relative_to(root) and path != root


def valid_argv(argv):
    need(isinstance(argv, list) and 1 <= len(argv) <= 4096, 'invalid_rustc_argv')
    need(all(isinstance(a, str) and '\x00' not in a and len(os.fsencode(a)) <= 16384
             for a in argv), 'invalid_rustc_argument')
    need(sum(len(os.fsencode(a)) for a in argv) <= MAX_RECORD // 2, 'rustc_argv_limit')


def parse_externs(values, cwd):
    result, names = [], set()
    for value in values:
        name, sep, path = value.partition('=')
        need(sep and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name) and name not in names,
             'invalid_or_duplicate_extern')
        path = canonical(path, cwd)
        need(Path(path).suffix in ('.rmeta', '.rlib', '.so'), 'unknown_extern_shape')
        result.append({'name': name, 'path': path})
        names.add(name)
    return result


def rustc_outputs(args, cwd, target_dir, environment=None):
    """Parse the pinned Linux naming subset; unknown syntax cannot establish proof."""
    valid_argv(args)
    if any(a in ('-vV', '-V', '--version', '--help', '-h', '--print') or
           a.startswith('--print=') for a in args):
        return {'role': 'query', 'unit': None, 'externs': [], 'outputs': []}
    from desktop_glib_probes import classify_probe
    probe = classify_probe(args, cwd, target_dir, environment or {})
    if probe is not None:
        return dict(role='probe', unit=probe, externs=[], outputs=[])
    values, codes, sources, i = {}, {}, [], 0
    while i < len(args):
        arg = args[i]
        if arg.startswith('--'):
            key, sep, value = arg[2:].partition('=')
            need(key in LONG_VALUES, 'unsupported_rustc_option:' + key)
            if not sep:
                i += 1
                need(i < len(args), 'missing_rustc_option_value')
                value = args[i]
            values.setdefault(key, []).append(value)
        elif arg.startswith(('-C', '-L', '-l', '-A', '-W', '-D', '-F')):
            key, value = arg[:2], arg[2:]
            if not value:
                i += 1
                need(i < len(args), 'missing_rustc_short_value')
                value = args[i]
            if key == '-C':
                name, sep, setting = value.partition('=')
                if name == 'prefer-dynamic':
                    need(not sep and arg == '-C', 'unsupported_prefer_dynamic_value')
                    setting = 'yes'
                else:
                    need(sep and name in CODEGEN, 'unsupported_codegen_option:' + name)
                need(name == 'link-arg' or name not in codes, 'duplicate_codegen_option')
                if name == 'link-arg':
                    need(not re.search(r'(^|[,\s])(-o|--output|@|--out-implib)', setting),
                         'linker_output_override')
                codes[name] = setting
        else:
            need(not arg.startswith(('-', '@')), 'unsupported_rustc_argument')
            sources.append(arg)
        i += 1
    for key in ('crate-name', 'edition', 'emit', 'out-dir', 'target'):
        need(len(values.get(key, [])) <= 1, 'duplicate_rustc_option')
    need(len(sources) == 1 and all(k in values for k in ('crate-name', 'emit', 'out-dir')),
         'incomplete_rustc_unit')
    name = values['crate-name'][0]
    need(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name), 'invalid_crate_name')
    types = sorted(set(t for v in values.get('crate-type', ['bin']) for t in v.split(',')))
    need(set(types) <= {'lib', 'rlib', 'bin', 'staticlib', 'cdylib', 'dylib', 'proc-macro'},
         'unsupported_crate_type')
    emits = sorted(values['emit'][0].split(','))
    need(len(emits) == len(set(emits)) and set(emits) <= {'dep-info', 'metadata', 'link'},
         'unsupported_emit_shape')
    extra = codes.get('extra-filename', '')
    need(re.fullmatch(r'(?:-[A-Za-z0-9_]+)?', extra), 'invalid_extra_filename')
    target = values.get('target', [None])[0]
    need(target in (None, TARGET), 'unsupported_rustc_target')
    role = 'target' if target else 'host'
    need('prefer-dynamic' not in codes or (role == 'host' and types == ['proc-macro'] and
         'link' in emits), 'unsupported_prefer_dynamic_unit')
    out = canonical(values['out-dir'][0], cwd)
    need(inside(out, target_dir), 'output_outside_fresh_target')
    need('prefer-dynamic' not in codes or out == str(Path(target_dir) / 'release/deps'),
         'wrong_prefer_dynamic_profile')
    if role == 'target':
        need(out == str(Path(target_dir) / TARGET / 'release/deps'), 'wrong_target_profile')
    else:
        need(inside(out, str(Path(target_dir) / 'release')), 'wrong_host_profile')
    externs = values.get('extern', [])
    bare = [v for v in externs if '=' not in v]
    # Pinned Cargo797e8a9 compiler/mod.rs:1852-1855 adds this sysroot import.
    need(not bare or (role == 'host' and types == ['proc-macro'] and bare == ['proc_macro']),
         'unsupported_bare_extern')
    unit = dict(crate_name=name, crate_types=types, emits=emits, extra_filename=extra,
                sysroot_externs=bare,
                target=target, out_dir=out, source=canonical(sources[0], cwd),
                opt_level=codes.get('opt-level', '0'), debuginfo=codes.get('debuginfo', '0'))
    outputs = {}
    if 'metadata' in emits:
        outputs['lib' + name + extra + '.rmeta'] = 'metadata'
    if 'link' in emits:
        for kind in types:
            filename = name + extra if kind == 'bin' else 'lib' + name + extra + {
                'lib': '.rlib', 'rlib': '.rlib', 'staticlib': '.a', 'cdylib': '.so',
                'dylib': '.so', 'proc-macro': '.so'}[kind]
            need(filename not in outputs or outputs[filename] == 'link', 'output_kind_collision')
            outputs[filename] = 'link'
    return dict(role=role, unit=unit, externs=parse_externs([v for v in externs if '=' in v], cwd),
                outputs=[{'path': str(Path(out) / n), 'kind': k} for n, k in sorted(outputs.items())])


def jobserver_fds(environment):
    """Preserve Cargo's supported pipe/FIFO jobserver without creating descriptors."""
    from desktop_glib_build_contract import parent_descriptor
    declared = []
    for token in shlex.split(environment.get('CARGO_MAKEFLAGS', '')):
        if re.fullmatch(r'-j\d*', token):
            continue
        match = re.fullmatch(r'--jobserver-(auth|fds)=(.+)', token)
        need(match is not None, 'unsupported_jobserver_flags')
        need(match.group(1) != 'fds' or not match.group(2).startswith('fifo:'),
             'unsupported_legacy_fifo_jobserver')
        declared.append(match.group(2))
    if not declared:
        return ()
    need(len(set(declared)) == 1, 'conflicting_jobserver_declarations')
    value = declared[0]
    if value.startswith('fifo:'):
        path = canonical(value[5:])
        need(value[5:] == path, 'noncanonical_jobserver_fifo')
        with parent_descriptor(path) as (fd, name):
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
        need(stat.S_ISFIFO(info.st_mode) and info.st_uid == os.getuid(), 'invalid_jobserver_fifo')
        return ()
    need(re.fullmatch(r'\d+,\d+', value), 'unsupported_jobserver_auth')
    read_fd, write_fd = map(int, value.split(','))
    need(3 <= read_fd < 2**20 and 3 <= write_fd < 2**20 and read_fd != write_fd,
         'invalid_jobserver_descriptors')
    read_info, write_info = os.fstat(read_fd), os.fstat(write_fd)
    need(stat.S_ISFIFO(read_info.st_mode) and stat.S_ISFIFO(write_info.st_mode) and
         (read_info.st_dev, read_info.st_ino) == (write_info.st_dev, write_info.st_ino),
         'invalid_jobserver_pipe')
    need(fcntl.fcntl(read_fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY and
         fcntl.fcntl(write_fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_WRONLY,
         'wrong_jobserver_pipe_direction')
    return read_fd, write_fd


def propagate_exit(code):
    if code < 0:
        if -code not in (signal.SIGKILL, signal.SIGSTOP):
            signal.signal(-code, signal.SIG_DFL)
        signal.pthread_sigmask(signal.SIG_UNBLOCK, {-code})
        os.kill(os.getpid(), -code)
    raise SystemExit(code)


def capture_rustc(argv, config):
    """Inherit live stdio, record bounded data, and return the actual child's status."""
    from desktop_glib_build_contract import file_record, stable_file, write_json
    from desktop_glib_probes import capture_probe_parent
    valid_argv(argv)
    compiler = canonical(config['real_rustc'])
    need(argv[0] == compiler and os.path.realpath(compiler) == compiler, 'alternate_rustc')
    identity = file_record(compiler, MAX_BINARY, single_link=False)
    need(identity['sha256'] == config['real_rustc_sha256'], 'changed_real_rustc')
    cwd, started = os.getcwd(), time.time_ns()
    record = dict(schema=2, id=uuid.uuid4().hex, argv=argv, cwd=cwd,
        compiler={'path': compiler, 'sha256': identity['sha256']},
        source_sha=config['source_sha'], source_root=config['source_root'],
        target_dir=config['target_dir'], environment={k: v for k, v in os.environ.items()
            if k in ENVIRONMENT}, started_ns=started, finished_ns=None, returncode=None,
        role='invalid', unit=None, source=None, externs=[], outputs=[], error=None, parent=None)
    def snapshot(path, target=False):
        return stable_file(path, config['target_dir'] if target else '/',
                           MAX_BINARY, allow_hardlinks=target)
    try:
        parsed = rustc_outputs(argv[1:], cwd, config['target_dir'], record['environment'])
        record.update(role=parsed['role'], unit=parsed['unit'])
        if parsed['role'] == 'probe':
            record['parent'] = capture_probe_parent(config['target_dir'], parsed['unit']['out_dir'])
        if parsed['unit'] and parsed['unit']['source'] is not None:
            path = parsed['unit']['source']
            record['source'] = {'path': path, 'before': snapshot(path), 'after': None}
            for ext in parsed['externs']:
                record['externs'].append(dict(ext, before=snapshot(ext['path'], True), after=None))
    except (EvidenceError, OSError, ValueError) as exc:
        record['error'] = str(exc)
    try:
        fds = jobserver_fds(os.environ)
        env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        # No PIPE, shell, decoding, buffering, or handling of live metadata messages.
        process = subprocess.Popen(argv, cwd=cwd, env=env, pass_fds=fds)
        record['returncode'] = process.wait()
        if not record['error'] and record['source']:
            record['source']['after'] = snapshot(record['source']['path'])
            for ext in record['externs']:
                ext['after'] = snapshot(ext['path'], True)
            if record['returncode'] == 0:
                record['outputs'] = [dict(o, **snapshot(o['path'], True)) for o in parsed['outputs']]
        if not record['error'] and record['role'] == 'probe':
            record['parent'] = capture_probe_parent(config['target_dir'],
                parsed['unit']['out_dir'], record['parent'])
        need(file_record(compiler, MAX_BINARY, single_link=False) == identity, 'compiler_changed')
    except (EvidenceError, OSError, ValueError) as exc:
        record['error'] = str(exc)
    finally:
        record['finished_ns'] = time.time_ns()
        need(len(json.dumps(record).encode()) <= MAX_RECORD, 'rustc_record_limit')
        write_json(Path(config['evidence_dir']) / ('rustc-' + record['id'] + '.json'), record)
    need(record['returncode'] is not None, 'rustc_not_executed:' + str(record['error']))
    return record['returncode']


def hash_record(value, limit=MAX_BINARY):
    need(isinstance(value, dict) and set(value) == {'sha256', 'size'}, 'invalid_artifact_identity')
    need(isinstance(value['sha256'], str) and re.fullmatch(r'[0-9a-f]{64}', value['sha256']),
         'invalid_artifact_hash')
    need(type(value['size']) is int and 0 <= value['size'] <= limit, 'invalid_artifact_size')


def bounded_data(value):
    pending, count = [(value, 0)], 0
    while pending:
        item, depth = pending.pop()
        count += 1
        need(depth <= 64 and count <= MAX_RECORD, 'trace_nesting_or_item_limit')
        need(item is None or type(item) in (dict, list, str, int), 'invalid_trace_json_type')
        if isinstance(item, dict):
            need(all(isinstance(k, str) for k in item), 'invalid_trace_json_key')
            pending.extend((v, depth + 1) for v in item.values())
        elif isinstance(item, list):
            pending.extend((v, depth + 1) for v in item)


def verify_link_trace(records, expected):
    """Data-only reconciliation after Cargo ends; producer exit ordering is irrelevant."""
    need(isinstance(records, list) and 1 <= len(records) <= 8192, 'invalid_trace_count')
    owners, units, edges, total = {}, {}, {}, 0
    keys = {'schema', 'id', 'argv', 'cwd', 'compiler', 'source_sha', 'source_root', 'target_dir',
            'environment', 'started_ns', 'finished_ns', 'returncode', 'role', 'unit', 'source',
            'externs', 'outputs', 'error', 'parent'}
    for rec in records:
        need(isinstance(rec, dict) and set(rec) == keys, 'invalid_trace_schema')
        bounded_data(rec)
        length = len(json.dumps(rec, allow_nan=False).encode())
        total += length
        need(length <= MAX_RECORD and total <= MAX_TRACE, 'trace_resource_limit')
        need(type(rec['schema']) is int and rec['schema'] == 2, 'invalid_trace_version')
        ident = rec['id']
        need(isinstance(ident, str) and re.fullmatch(r'[0-9a-f]{32}', ident) and ident not in units,
             'duplicate_or_invalid_invocation')
        need(type(rec['returncode']) is int and
             rec['returncode'] in ((0, 1) if rec['role'] == 'probe' else (0,)) and rec['error'] is None,
             'failed_or_incomplete_rustc')
        need(all(type(rec[k]) is int and 0 <= rec[k] < 2**63 for k in ('started_ns', 'finished_ns'))
             and rec['finished_ns'] >= rec['started_ns'], 'invalid_trace_timestamps')
        for field in ('source_sha', 'source_root', 'target_dir'):
            need(rec[field] == expected[field], 'wrong_trace_' + field)
        need(rec['compiler'] == {'path': expected['real_rustc'],
                                 'sha256': expected['real_rustc_sha256']}, 'wrong_trace_compiler')
        valid_argv(rec['argv'])
        need(rec['argv'][0] == expected['real_rustc'], 'wrong_trace_compiler_argv')
        need(rec['cwd'] == canonical(rec['cwd']), 'noncanonical_trace_cwd')
        env = rec['environment']
        need(isinstance(env, dict) and set(env) <= ENVIRONMENT and all(isinstance(v, str) and
             len(os.fsencode(v)) <= 16384 for v in env.values()), 'invalid_trace_environment')
        parsed = rustc_outputs(rec['argv'][1:], rec['cwd'], expected['target_dir'], env)
        need(rec['role'] == parsed['role'] and rec['unit'] == parsed['unit'], 'changed_trace_unit')
        need(isinstance(rec['externs'], list) and isinstance(rec['outputs'], list), 'invalid_trace_lists')
        units[ident], edges[ident] = rec, set()
        if rec['role'] == 'probe':
            need(rec['externs'] == rec['outputs'] == [], 'probe_has_proof_artifacts')
            continue
        need(rec['parent'] is None, 'unexpected_compiler_parent')
        if rec['role'] == 'query':
            need(rec['source'] is None and not rec['externs'] and not rec['outputs'], 'query_has_outputs')
            continue
        source = rec['source']
        need(isinstance(source, dict) and set(source) == {'path', 'before', 'after'} and
             source['path'] == parsed['unit']['source'], 'wrong_trace_source')
        need(all(isinstance(e, dict) and set(e) == {'name', 'path', 'before', 'after'}
                 for e in rec['externs']), 'invalid_extern_record')
        need(all(isinstance(o, dict) and set(o) == {'path', 'kind', 'sha256', 'size'}
                 for o in rec['outputs']), 'invalid_output_record')
        for before_after in (source, *rec['externs']):
            hash_record(before_after['before'])
            hash_record(before_after['after'])
            need(before_after['before'] == before_after['after'], 'compiler_input_changed')
        if inside(source['path'], expected['source_root']):
            need(source['before']['sha256'] == expected['local_source_hashes'].get(source['path']),
                 'untrusted_local_source')
        need([{k: e[k] for k in ('name', 'path')} for e in rec['externs']] == parsed['externs'],
             'changed_trace_externs')
        need(all(set(e) == {'name', 'path', 'before', 'after'} for e in rec['externs']), 'invalid_extern_record')
        need([{k: o[k] for k in ('path', 'kind')} for o in rec['outputs']] == parsed['outputs'],
             'changed_trace_outputs')
        for output in rec['outputs']:
            need(set(output) == {'path', 'kind', 'sha256', 'size'}, 'invalid_output_record')
            hash_record({k: output[k] for k in ('sha256', 'size')},
                        128 * 1024**2 if parsed['unit']['crate_name'] == 'glib' else MAX_BINARY)
            need(output['path'] not in owners, 'duplicate_output_owner')
            owners[output['path']] = (ident, output)
    for ident, rec in units.items():
        for ext in rec['externs']:
            need(ext['path'] in owners, 'unmatched_extern_producer')
            owner, output = owners[ext['path']]
            producer = units[owner]
            need(ext['before'] == {k: output[k] for k in ('sha256', 'size')}, 'extern_hash_mismatch')
            need('link' in producer['unit']['emits'], 'check_only_producer')
            if producer['role'] != rec['role']:
                need(rec['role'] == 'target' and producer['role'] == 'host' and
                     producer['unit']['crate_types'] == ['proc-macro'] and ext['path'].endswith('.so'),
                     'cross_target_compiler_edge')
            edges[ident].add(owner)
    from desktop_glib_probes import verify_probe_trace
    for rec in records:
        if rec['role'] == 'probe':
            verify_probe_trace(rec, expected, units, owners)
    # Kahn elimination rejects all cycles without unbounded recursive traversal.
    remaining = {k: set(v) for k, v in edges.items()}
    while remaining:
        leaves = {k for k, v in remaining.items() if not v}
        need(leaves, 'cyclic_compiler_inputs')
        remaining = {k: v - leaves for k, v in remaining.items() if k not in leaves}
    selected = {}
    for label, crate, kinds in (('glib', 'glib', {'lib', 'rlib'}),
                                ('root', 'coding_tools_mcp_desktop', {'bin'})):
        candidates = [r for r in records if r['role'] == 'target' and
            r['unit']['source'] == expected[label + '_source'] and r['unit']['crate_name'] == crate]
        need(len(candidates) == 1, 'missing_or_duplicate_' + label + '_unit')
        rec = candidates[0]
        need(set(rec['unit']['crate_types']) <= kinds and 'link' in rec['unit']['emits'] and
             rec['unit']['opt_level'] == '3' and rec['unit']['debuginfo'] == '0', 'wrong_proof_unit_profile')
        need(rec['source']['before']['sha256'] == expected[label + '_source_sha256'], 'wrong_proof_source')
        selected[label] = rec
    glib = selected['glib']
    rlib = expected['glib_rlib']
    need(owners.get(rlib['path'], (None,))[0] == glib['id'], 'wrong_glib_archive_owner')
    need(all(owners[rlib['path']][1][k] == rlib[k] for k in ('sha256', 'size')) and
         rlib['path'].endswith('.rlib'),
         'wrong_glib_archive_hash')
    need(any(o['kind'] == 'metadata' and o['path'].endswith('.rmeta') for o in glib['outputs']),
         'missing_glib_metadata_cooutput')
    root_outputs = [o for o in selected['root']['outputs'] if o['kind'] == 'link']
    need(len(root_outputs) == 1 and all(root_outputs[0][k] == expected['root_executable'][k]
         for k in ('sha256', 'size'))
         and inside(expected['root_executable']['path'], expected['target_dir']), 'wrong_root_executable')
    ancestry, pending = set(), [selected['root']['id']]
    while pending:
        current = pending.pop()
        if current not in ancestry:
            ancestry.add(current)
            pending.extend(p for p in edges[current] if units[p]['role'] == 'target')
    need(glib['id'] in ancestry, 'glib_not_on_target_compiler_input_ancestry')
    return {'compiler_input_provenance_verified': True, 'glib_invocation': glib['id'],
            'root_invocation': selected['root']['id'], 'target_ancestry_units': len(ancestry),
            'diagnostic_probes': sum(r['role'] == 'probe' for r in records),
            'diagnostic_probe_failures': sum(r['role'] == 'probe' and r['returncode'] == 1 for r in records),
            'native_linker_consumption_verified': False, 'retained_glib_code_verified': False}
