"""Finite data-only AppImage preservation proof; no tool execution or release approval."""
import collections
import contextlib
import os
from pathlib import Path
import posixpath
import re
import stat
import struct

import desktop_glib_build_contract as base
import desktop_glib_deb as deb

need, digest, decode = base.need, base.exact.digest, base.decode
PROFILE, MAIN, MAX_ELF = 'linux-engineering-packages-v1', deb.BINARY, 256 * 1024**2
TOOL_SIZE, TOOL_SHA256 = 1029016, 'c15c1282d9dadcaaf5e492c0ee5f929d34453f8af759cc4aadad03b5b65df879'
OUTER_SIZE, OUTER_OFFSET = 13264064, 193728
OUTER_SHA256 = 'e762bea85c8eb0d4b3508d46e5c1f037f717d0f9303ae3b4aafc8b04991fa1ef'
APP = b'__TAURI_BUNDLE_TYPE_VAR_APP'
FAMILIES = {
    'glib': (1281808, '86acf2c843bcfaf5e8c24ab959737960c797da53b41658dc8ec6f257c786048c'),
    'gio': (1932688, 'b63a477916c1f95de4b2c80bb4f5940a59ebc5860793d93b271448e90edbfe52'),
    'gobject': (387464, '05a94d6be0a50dba15a579f3ad1f5c6ec12c8d303f3b715a665fd27824ca523e'),
    'gmodule': (22736, '1019fc28ced6829f22b446a091ecb5b76b9fa3b3c458bc6ea936c1d328302cb5')}
PROTECTED = {MAIN: dict(family='main', size=None, sha256=None, mode=0o755, rpath='$ORIGIN/../lib')}
for _family, (_size, _hash) in FAMILIES.items():
    for _suffix in (('0',) if _family in ('glib', 'gmodule') else ('', '0', '0.7200.4')):
        PROTECTED['usr/lib/lib' + _family + '-2.0.so' + ('.' + _suffix if _suffix else '')] = dict(
            family=_family, size=_size, sha256=_hash, mode=0o644, rpath='$ORIGIN')
CAPS = dict(config=32768, binding=32768, state=16384, failure=4096, final=1048576,
    event=32768, journal=33554432, calls=4096, argv_count=64, argv_bytes=16384,
    path=4096, elf=MAX_ELF, hashed=17179869184, duration=900, lock=30, child=30, stream=1048576)
CONFIG_KEYS = set(('schema profile source_sha source_tree producer source_root target_root evidence_root '
    'appdir_root compiler_binding_path desktop_elf_path original_patchelf_path original_patchelf_size '
    'original_patchelf_sha256 guard_path guard_sha256 guard_mode python_path python_sha256 '
    'python_version protected caps').split())
BINDING_KEYS = set(('schema profile source_sha source_tree producer target_root compiler_copies_sha256 '
    'build_jsonl_sha256 prebundle event_executable').split())
RECORD_KEYS = set('target size sha256 mode uid device inode nlink mtime_ns ctime_ns'.split())
FILES = {'config.json', 'parser-tool.json', 'original-patchelf', 'compiler-binding.json',
         'lock', 'state.json', 'operations.jsonl', 'final.json'}
FALSE_FLAGS = dict.fromkeys(('independent_all_query_attempts_verified all_bundled_dsos_relro_preserved '
    'full_dependency_closure_verified native_linker_consumption_verified retained_glib_code_verified '
    'security_approved release_approved publish_approved').split(), False)


def keys(value, expected, code):
    need(type(value) is dict and set(value) == set(expected), code)


def identity(value, limit=MAX_ELF):
    keys(value, {'sha256', 'size'}, 'invalid_byte_record')
    need(type(value['size']) is int and 0 <= value['size'] <= limit and
         type(value['sha256']) is str and re.fullmatch('[0-9a-f]{64}', value['sha256']), 'invalid_byte_identity')
    return value


def byte_record(data):
    need(type(data) is bytes, 'immutable_bytes_required')
    return dict(size=len(data), sha256=digest(data))


def canonical(path):
    value = os.fspath(path)
    need(type(value) is str and value.startswith('/') and 1 < len(value.encode()) <= CAPS['path'] and
         all(p not in ('', '.', '..') for p in value.split('/')[1:]) and '\\' not in value and
         all(ord(c) >= 32 and ord(c) != 127 for c in value), 'noncanonical_path')
    return value


def observe(path, *, owned=True, mode=None, limit=MAX_ELF, hash_data=True):
    path = canonical(path)
    with base.parent_descriptor(path) as (parent, name):
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            before = os.fstat(fd)
            need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 <= before.st_size <= limit,
                 'invalid_observed_file')
            need((not owned or before.st_uid == os.geteuid()) and not before.st_mode & 0o6022 and
                 (mode is None or stat.S_IMODE(before.st_mode) == mode), 'wrong_observed_owner_or_mode')
            chunks, size = [], 0
            while chunk := os.read(fd, min(1024**2, limit + 1 - size)):
                chunks.append(chunk); size += len(chunk)
                need(size <= limit, 'observation_limit')
            after = os.fstat(fd)
            named = os.stat(name, dir_fd=parent, follow_symlinks=False)
            need(base.file_identity(before) == base.file_identity(after) == base.file_identity(named) and
                 before.st_mode == after.st_mode == named.st_mode and before.st_uid == after.st_uid == named.st_uid
                 and size == before.st_size, 'observed_file_changed')
            with base.parent_descriptor(path) as (again, leaf):
                need(base.file_identity(os.stat(leaf, dir_fd=again, follow_symlinks=False)) ==
                     base.file_identity(before), 'observed_named_path_changed')
            data = b''.join(chunks)
            return data, dict(target=path, size=len(data), sha256=digest(data) if hash_data else None, mode=stat.S_IMODE(before.st_mode),
                uid=before.st_uid, device=before.st_dev, inode=before.st_ino, nlink=before.st_nlink,
                mtime_ns=before.st_mtime_ns, ctime_ns=before.st_ctime_ns)
        finally:
            os.close(fd)


def validate_config(c):
    keys(c, CONFIG_KEYS, 'invalid_relro_config_fields')
    need(c['schema'] == 'appimage-relro-config-v1' and c['profile'] == PROFILE and
         c['protected'] == PROTECTED and c['caps'] == CAPS and all(type(v) is int for v in c['caps'].values()),
         'invalid_relro_config_contract')
    for field in ('source_sha', 'source_tree'):
        need(type(c[field]) is str and re.fullmatch('[0-9a-f]{40}', c[field]), 'invalid_config_source')
    p = c['producer']
    keys(p, 'provider repository source_sha workflow_sha run_id run_attempt workflow_ref job runner_os platform'.split(),
         'invalid_config_producer')
    need(p['provider'] == 'github-actions' and p['repository'] == base.REPOSITORY and
         p['source_sha'] == p['workflow_sha'] == c['source_sha'] and p['job'] == 'build' and
         p['runner_os'] == 'Linux' and p['platform'] == {'id': 'ubuntu', 'version_id': '22.04'} and
         all(type(p[k]) is str and re.fullmatch('[1-9][0-9]*', p[k]) for k in ('run_id', 'run_attempt')) and
         type(p['workflow_ref']) is str and re.fullmatch(re.escape(base.REPOSITORY + '/.github/workflows/linux-rc-packages.yml@refs/heads/') +
             r'(fix/linux-startup-platform|ci/preliminary-packages-[A-Za-z0-9._-]+)', p['workflow_ref']), 'wrong_config_producer')
    for field in [k for k in c if k.endswith(('_root', '_path'))]: canonical(c[field])
    roots = [Path(c[k]) for k in ('source_root', 'target_root', 'evidence_root')]
    need(not any(a.is_relative_to(b) for i, a in enumerate(roots) for j, b in enumerate(roots) if i != j),
         'overlapping_relro_roots')
    r = c['evidence_root'] + '/appimage-relro'
    need(c['appdir_root'] == c['target_root'] + '/' + base.TARGET + '/release/bundle/appimage/Coding Tools MCP.AppDir' and
         c['compiler_binding_path'] == r + '/compiler-binding.json' and c['desktop_elf_path'] == c['evidence_root'] + '/desktop.elf'
         and c['original_patchelf_path'] == r + '/original-patchelf' and
         c['guard_path'] == c['source_root'] + '/scripts/appimage_relro_guard.py', 'wrong_derived_config_path')
    need(type(c['original_patchelf_size']) is int and c['original_patchelf_size'] == TOOL_SIZE and
         c['original_patchelf_sha256'] == TOOL_SHA256 and type(c['guard_mode']) is int and c['guard_mode'] == 0o755 and
         all(type(c[k]) is str and re.fullmatch('[0-9a-f]{64}', c[k]) for k in ('guard_sha256', 'python_sha256')) and
         type(c['python_version']) is str and re.fullmatch(r'Python 3\.12\.[0-9]+', c['python_version']), 'wrong_config_tool')
    return c


def read_config(path, expected_hash=None, *, defer_hash=False):
    raw, _ = observe(path, mode=0o400, limit=CAPS['config'], hash_data=not defer_hash)
    need(defer_hash or expected_hash is None or digest(raw) == expected_hash, 'changed_relro_config')
    c = validate_config(decode(raw, CAPS['config']))
    need(canonical(path) == c['evidence_root'] + '/appimage-relro/config.json', 'wrong_config_location')
    with base.parent_descriptor(path) as (parent, _):
        info = os.fstat(parent)
        need(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700, 'unsafe_private_state_directory')
        with base.parent_descriptor(str(Path(path).parent)) as (ancestor, name):
            named = os.stat(name, dir_fd=ancestor, follow_symlinks=False)
            need((base.file_identity(info), info.st_uid, info.st_mode) ==
                 (base.file_identity(named), named.st_uid, named.st_mode), 'private_state_directory_changed')
    return c


def read_binding(config, compiler_records=None):
    c = validate_config(config)
    raw = (observe(c['compiler_binding_path'], mode=0o600, limit=CAPS['binding'])[0] if compiler_records is None
           else compiler_records['relro_evidence']['compiler-binding.json'])
    b = decode(raw, CAPS['binding']); keys(b, BINDING_KEYS, 'invalid_compiler_binding_fields')
    need(b['schema'] == 'appimage-relro-compiler-v1' and all(b[k] == c[k] for k in
         ('profile', 'source_sha', 'source_tree', 'producer', 'target_root')), 'wrong_compiler_binding_context')
    identity(b['prebundle'])
    need(b['event_executable'] == c['target_root'] + '/' + base.TARGET + '/release/' + base.BINARY and
         all(type(b[k]) is str and re.fullmatch('[0-9a-f]{64}', b[k]) for k in
             ('compiler_copies_sha256', 'build_jsonl_sha256')), 'wrong_compiler_binding_identity')
    if compiler_records is not None:
        r = compiler_records
        need(decode(r['compiler_copies_bytes']) == {'events': r['events'], 'copies': r['copies']} and
             b['compiler_copies_sha256'] == digest(r['compiler_copies_bytes']) and b['build_jsonl_sha256'] == digest(r['build_jsonl_bytes'])
             and b['prebundle'] == r['copies']['desktop'] == byte_record(r['compiled']) and
             b['event_executable'] == r['events']['root']['executable'], 'compiler_binding_evidence_mismatch')
        lines = r['build_jsonl_bytes'].splitlines()
        need(lines and decode(lines[-1]) == {'reason': 'build-finished', 'success': True} and
             sum(decode(line) == r['events']['root'] for line in lines) == 1, 'unverified_compiler_finish')
    return b


def verify_app_marker(compiled, payload):
    need(type(compiled) is bytes and type(payload) is bytes and compiled.count(deb.UNK) == 1 and
         compiled.count(APP) == 0 and payload.count(APP) == 1 and payload.count(deb.UNK) == 0, 'invalid_app_marker')
    pos = compiled.index(deb.UNK)
    expected = compiled[:pos] + APP + compiled[pos + len(APP):]
    view = compiled[:pos] + deb.DEB + compiled[pos + len(APP):]
    result = deb.verify_marker_transform(compiled, view)
    need(payload == expected, 'unexpected_app_payload_change')
    return {**result, 'payload_sha256': digest(payload), 'payload_size': len(payload)}


def dynamic_relro(data):
    need(type(data) is bytes and 64 <= len(data) <= MAX_ELF and data[:7] == b'\x7fELF\x02\x01\x01' and
         data[7] in (0, 3) and not any(data[8:16]), 'invalid_dynamic_elf')
    kind, machine, version, _, phoff, _, flags, ehsize, phsize, phnum = struct.unpack_from('<HHIQQQIHHH', data, 16)
    need(kind in (2, 3) and machine == 62 and version == 1 and flags == 0 and ehsize == 64 and
         phsize == 56 and 0 < phnum <= 128 and phoff >= 64, 'invalid_dynamic_headers')
    deb.checked_range(phoff, phsize * phnum, len(data), 'truncated_dynamic_headers')
    headers = [struct.unpack_from('<IIQQQQQQ', data, phoff + n * 56) for n in range(phnum)]
    for typ, perms, off, addr, phys, filesz, memsz, align in headers:
        deb.checked_range(off, filesz, len(data), 'dynamic_file_overflow')
        deb.checked_range(addr, memsz, deb.U64, 'dynamic_address_overflow')
        deb.checked_range(phys, memsz, deb.U64, 'dynamic_physical_overflow')
        need(filesz <= memsz and perms & ~7 == 0 and (align <= 1 or align & (align - 1) == 0 and
             off % align == addr % align), 'invalid_dynamic_segment')
    loads = [p for p in headers if p[0] == 1]
    dyn, rel, stack = ([p for p in headers if p[0] == t] for t in (2, 0x6474e552, 0x6474e551))
    need(len(dyn) == len(rel) == len(stack) == 1, 'ambiguous_dynamic_relro_stack')
    d, r = dyn[0], rel[0]
    need(0 < d[5] == d[6] <= 4096 * 16 and d[5] % 16 == 0 and r[6] > 0, 'invalid_dynamic_table')
    maps = [p for p in loads if p[2] <= d[2] and d[2] + d[5] <= p[2] + p[5] and
            p[3] + d[2] - p[2] == d[3] and d[3] + d[6] <= p[3] + p[6]]
    need(len(maps) == 1 and maps[0][1] & 4, 'contradictory_dynamic_mapping')
    effective = (r[3] // 4096 * 4096, (r[3] + r[6]) // 4096 * 4096)
    need(effective[0] <= d[3] < d[3] + d[6] <= effective[1] and
         maps[0][3] <= r[3] and r[3] + r[6] <= maps[0][3] + maps[0][6] and r[5] > 0 and
         r[3] - maps[0][3] == r[2] - maps[0][2] and
         maps[0][2] <= r[2] < r[2] + r[5] <= maps[0][2] + maps[0][5], 'dynamic_outside_effective_relro')
    for p in loads:
        if p is maps[0] or not p[1] & 2: continue
        file_pages, virtual_pages = deb.mapped_pages((p[2], p[2] + p[5])), deb.mapped_pages((p[3], p[3] + p[6]))
        file_overlap = (max(file_pages[0], d[2]), min(file_pages[1], d[2] + d[5]))
        alias = tuple(virtual_pages[0] + boundary - file_pages[0] for boundary in file_overlap)
        virtual = (max(virtual_pages[0], d[3]), min(virtual_pages[1], d[3] + d[6]))
        need(not (file_overlap[0] < file_overlap[1] and not effective[0] <= alias[0] < alias[1] <= effective[1]) and
             not virtual[0] < virtual[1], 'writable_dynamic_alias')
    entries = [struct.unpack_from('<qQ', data, off) for off in range(d[2], d[2] + d[5], 16)]
    need(any(t == 0 for t, v in entries), 'unterminated_dynamic_table')
    end = next(i for i, item in enumerate(entries) if item[0] == 0)
    need(all(t == 0 for t, v in entries[end:]), 'contradictory_dynamic_tail')
    entries = entries[:end]
    need(all(sum(t == tag for t, v in entries) <= 1 for tag in (24, 30, 0x6ffffffb)), 'duplicate_dynamic_flags')
    need(not any(t in (15, 29) for t, v in entries), 'protected_rpath_present')
    now = any(t == 24 or t == 30 and v & 8 or t == 0x6ffffffb and v & 1 for t, v in entries)
    nx = not stack[0][1] & 1
    pie = kind == 3 and any(t == 0x6ffffffb and v & 0x8000000 for t, v in entries)
    need(now and nx, 'missing_bind_now_or_nx')
    return dict(dynamic=dict(offset=d[2], address=d[3], filesz=d[5], memsz=d[6]),
        declared_relro=dict(start=r[3], end=r[3] + r[6]), effective_relro=dict(start=effective[0], end=effective[1]),
        bind_now=bool(now), nx=bool(nx), pie=bool(pie))


def protected_bytes(relative, data, compiled):
    need(relative in PROTECTED, 'unknown_protected_destination')
    expected = PROTECTED[relative]
    if relative == MAIN: verify_app_marker(compiled, data)
    else: need(byte_record(data) == {k: expected[k] for k in ('sha256', 'size')}, 'wrong_protected_bytes')
    layout = dynamic_relro(data)
    if relative == MAIN:
        need(layout['pie'] and dynamic_relro(compiled) == layout, 'main_layout_or_pie_changed')
    return layout


@contextlib.contextmanager
def owned_appdir_parents(config, path, mutation=False):
    root = config['target_root']; held = []
    def stamp(s, mutable=False):
        identity = (s.st_dev, s.st_ino, s.st_nlink) if mutable else base.file_identity(s)
        return identity, s.st_uid, s.st_mode
    with base.parent_descriptor(root + '/parent-check') as (anchor, _):
        try:
            fd = anchor
            for component in [None, *Path(path).relative_to(root).parts[:-1]]:
                parent = fd
                if component is not None: fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                info = os.fstat(fd); held.append((fd, parent, component, info))
                need(info.st_uid == os.geteuid() and not info.st_mode & 0o6022, 'unsafe_appdir_parent')
            yield
            for fd, parent, component, before in held:
                after = os.fstat(fd)
                named = os.stat(component, dir_fd=parent, follow_symlinks=False) if component else after
                mutable = mutation and fd == held[-1][0]
                need(all(stamp(s, mutable) == stamp(before, mutable) for s in (after, named)), 'appdir_parent_changed')
            with base.parent_descriptor(root) as (parent, name):
                named = os.stat(name, dir_fd=parent, follow_symlinks=False); before = held[0][3]
                need(stamp(named) == stamp(before), 'appdir_anchor_changed')
        finally:
            for fd, _, component, _ in reversed(held):
                if component is not None: os.close(fd)


def protected_record(config, path, compiled=None):
    path = canonical(path); prefix = config['appdir_root'] + '/'
    need(path.startswith(prefix) and path[len(prefix):] in PROTECTED, 'outside_protected_destinations')
    relative = path[len(prefix):]
    if relative == MAIN:
        binding = read_binding(config)
        if compiled is None: compiled = observe(config['desktop_elf_path'], mode=0o600, limit=binding['prebundle']['size'])[0]
        need(byte_record(compiled) == binding['prebundle'], 'changed_retained_compiler')
    with owned_appdir_parents(config, path):
        data, record = observe(path, mode=PROTECTED[relative]['mode'], limit=binding['prebundle']['size'] if relative == MAIN else PROTECTED[relative]['size'])
        protected_bytes(relative, data, compiled)
        return {**record, 'target': relative}

def operation_record(r):
    keys(r, RECORD_KEYS | ({'aliases', 'resolved'} if type(r) is dict and 'aliases' in r else set()), 'invalid_operation_file_fields')
    identity({k: r[k] for k in ('sha256', 'size')})
    need(type(r['target']) is str and 0 < len(r['target'].encode()) <= CAPS['path'] and
         all(type(r[k]) is int and r[k] >= 0 for k in RECORD_KEYS - {'target', 'sha256'}) and
         r['nlink'] == 1 and r['mode'] <= 0o777 and not r['mode'] & 0o22, 'invalid_operation_file')
    if 'aliases' in r:
        canonical(r['resolved'])
        need(type(r['aliases']) is list and 0 < len(r['aliases']) <= 8, 'invalid_query_aliases')
        for item in r['aliases']:
            keys(item, 'path target device inode mtime_ns ctime_ns'.split(), 'invalid_query_alias_fields')
            canonical(item['path'])
            need(type(item['target']) is str and 0 < len(item['target'].encode()) <= CAPS['path'] and
                 '\\' not in item['target'] and all(ord(ch) >= 32 and ord(ch) != 127 for ch in item['target']) and
                 all(type(item[k]) is int and item[k] >= 0 for k in ('device', 'inode', 'mtime_ns', 'ctime_ns')), 'invalid_query_alias')


def diagnostics(config, logs, setters):
    keys(logs, {'stdout', 'stderr'}, 'missing_build_log_stream')
    attempts, canonicals = [], []
    for data in logs.values():
        need(type(data) is bytes and len(data) <= 64 * 1024**2 and b'\0' not in data, 'invalid_build_log')
        text = re.sub(r'\x1b\[[0-9;]*m', '', data.decode('utf-8', errors='strict'))
        need('\x1b' not in text, 'unreviewed_log_escape')
        for line in text.splitlines():
            need(not any(s in line for s in ('APPIMAGE_RELRO_GUARD_FAILURE:', 'Call to patchelf failed:',
                'Failed to set rpath in ELF file:', 'Could not find patchelf', 'Failed to execute patchelf',
                'Failed to run patchelf', 'Strip call failed:')), 'visible_linuxdeploy_failure')
            for selector in ('Using patchelf:', 'Using patchelf specified in $PATCHELF:'):
                if selector in line:
                    need(line.split(selector, 1)[1].strip().strip('"') == config['guard_path'], 'wrong_visible_selector')
            if 'Setting rpath in ELF file' in line:
                suffix = line.split('Setting rpath in ELF file', 1)[1].strip()
                match = re.fullmatch(r'(?:"([^"]+)"|(.+?)) to (.*)', suffix)
                need(match is not None, 'malformed_setter_diagnostic')
                path, value = match[1] or match[2], match[3].strip()
                attempts.append((canonical(path), value))
            if 'Calling patchelf on canonical path' in line:
                suffix = line.split('Calling patchelf on canonical path', 1)[1].strip()
                match = re.fullmatch(r'(/.+?) instead of original path (/.*)', suffix)
                need(match is not None, 'malformed_canonical_diagnostic')
                canonicals.append((canonical(match[1]), canonical(match[2])))
    available = collections.Counter(p for p, _ in attempts)
    resolved = {}
    for actual, original in canonicals:
        need(available[original] > 0 and resolved.get(original, actual) == actual, 'canonical_diagnostic_mismatch')
        available[original] -= 1; resolved[original] = actual
    attempts = [(resolved.get(path, path), value) for path, value in attempts]
    need(collections.Counter(attempts) == collections.Counter(setters), 'setter_diagnostic_bijection')


def replay_operations(config, raw_journal, logs):
    from appimage_relro_guard import classify_original_argv
    validate_config(config)
    need(type(raw_journal) is bytes and 0 < len(raw_journal) <= CAPS['journal'] and
         raw_journal.endswith(b'\n'), 'invalid_operation_journal')
    lines = raw_journal.splitlines()
    need(len(lines) % 2 == 0 and 0 < len(lines) <= CAPS['calls'] * 2, 'pending_or_excess_operations')
    rows = [decode(line, CAPS['event']) for line in lines]
    begin_keys = set(('schema event sequence config_sha256 compiler_binding_sha256 pid start_time argv cwd '
                      'operation target decision before original_tool monotonic_ns').split())
    end_keys = set('schema event sequence config_sha256 result after stdout stderr error monotonic_ns'.split())
    coverage, setters, last_time, duration, hashed, bindings, configs = set(), [], 0, 0, 0, set(), set()
    for index in range(0, len(rows), 2):
        b, e = rows[index:index + 2]
        keys(b, begin_keys, 'invalid_operation_begin_fields')
        keys(e, end_keys | ({'exit'} if 'exit' in e else {'signal'}), 'invalid_operation_end_fields')
        need(b['schema'] == e['schema'] == 'appimage-relro-operation-v1' and b['event'] == 'begin' and
             e['event'] == 'end' and type(b['sequence']) is int and type(e['sequence']) is int and
             b['sequence'] == e['sequence'] == index // 2 + 1, 'operation_sequence_mismatch')
        need(type(b['pid']) is int and b['pid'] > 0 and type(b['start_time']) is str and
             re.fullmatch('[0-9]+', b['start_time']), 'invalid_operation_process')
        canonical(b['cwd'])
        need(all(type(v) is int for v in (b['monotonic_ns'], e['monotonic_ns'])) and
             last_time <= b['monotonic_ns'] <= e['monotonic_ns'], 'operation_time_mismatch')
        last_time = e['monotonic_ns']; duration += e['monotonic_ns'] - b['monotonic_ns']
        need(type(e.get('exit')) is int and e['exit'] == 0 and e['error'] is None and
             b['decision'] in ('preserve', 'delegate') and e['result'] ==
             ('preserved' if b['decision'] == 'preserve' else 'delegated'), 'recorded_operation_failure')
        for field in ('config_sha256', 'compiler_binding_sha256'):
            need(type(b[field]) is str and re.fullmatch('[0-9a-f]{64}', b[field]), 'invalid_operation_binding')
        need(e['config_sha256'] == b['config_sha256'], 'operation_config_mismatch')
        configs.add(b['config_sha256']); bindings.add(b['compiler_binding_sha256'])
        parsed = classify_original_argv(b['argv'])
        need(parsed['operation'] == b['operation'] and b['operation'] != 'invalid', 'operation_argv_mismatch')
        operand = parsed['target']
        absolute = None if operand is None else canonical(operand if operand.startswith('/') else b['cwd'] + '/' + operand)
        prefix = config['appdir_root'] + '/'
        target = absolute[len(prefix):] if absolute and absolute.startswith(prefix) else absolute
        need(target == b['target'], 'operation_target_mismatch')
        for record in (b['before'], e['after']):
            if record is not None:
                operation_record(record); hashed += record['size']
                need(record['target'] == (target if target in PROTECTED else absolute), 'file_target_mismatch')
                need('aliases' not in record or b['decision'] == 'delegate' and not parsed['mutation'] and
                     target not in PROTECTED, 'unreviewed_query_alias')
        need((b['before'] is None) == (operand is None) and (e['after'] is None) == (operand is None), 'missing_file_observation')
        if parsed['setter']:
            need(type(parsed['rpath']) is str, 'missing_setter_value')
            setters.append((absolute, parsed['rpath']))
        if b['decision'] == 'preserve':
            need(target in PROTECTED and b['argv'] == ['--set-rpath', PROTECTED[target]['rpath'], absolute] and
                 b['before'] == e['after'] and b['original_tool'] is None and
                 e['stdout'] is None and e['stderr'] is None, 'invalid_preservation_record')
            coverage.add(target)
        else:
            operation_record(b['original_tool'])
            need('aliases' not in b['original_tool'] and b['original_tool']['target'] == config['original_patchelf_path'] and
                 b['original_tool']['size'] == TOOL_SIZE and b['original_tool']['sha256'] == TOOL_SHA256 and
                 b['original_tool']['mode'] == 0o500, 'wrong_delegated_tool')
            for stream in ('stdout', 'stderr'): identity(e[stream], CAPS['stream'])
            need(not parsed['mutation'] or target not in PROTECTED and absolute.startswith(prefix), 'delegated_protected_mutation')
            if not parsed['mutation']: need(b['before'] == e['after'], 'recorded_query_mutation')
    need(len(configs) == len(bindings) == 1 and coverage == set(PROTECTED) and duration <= CAPS['duration'] * 10**9
         and hashed <= CAPS['hashed'], 'incomplete_or_excess_operation_coverage')
    diagnostics(config, logs, setters)
    return dict(calls=len(rows) // 2, config_sha256=configs.pop(), compiler_binding_sha256=bindings.pop(),
        journal_sha256=digest(raw_journal), journal_bytes=len(raw_journal), total_observed_bytes=hashed,
        duration_ns=duration, protected_count=len(coverage), independent_all_query_attempts_verified=False)


def verify_final(config, compiler_records, appdir_records, image_records, appimage_record, logs, package_references):
    from appimage_relro_tool import verify_tool_receipt
    c, evidence = validate_config(config), compiler_records['relro_evidence']
    need(type(evidence) is dict and set(evidence) in (FILES, FILES - {'final.json'}), 'wrong_relro_receipt_inventory')
    limits = {'config.json': CAPS['config'], 'compiler-binding.json': CAPS['binding'], 'parser-tool.json': 65536,
              'original-patchelf': TOOL_SIZE, 'lock': 0, 'state.json': CAPS['state'],
              'operations.jsonl': CAPS['journal'], 'final.json': CAPS['final']}
    need(all(type(v) is bytes and len(v) <= limits[k] for k, v in evidence.items()), 'relro_receipt_limit')
    need(decode(evidence['config.json'], CAPS['config']) == c, 'final_config_mismatch')
    need(byte_record(evidence['original-patchelf']) == dict(size=TOOL_SIZE, sha256=TOOL_SHA256), 'final_tool_mismatch')
    tool = verify_tool_receipt(evidence['parser-tool.json'])
    need(tool['original']['target'] == c['original_patchelf_path'], 'wrong_staged_tool_location')
    binding = read_binding(c, compiler_records)
    replay = replay_operations(c, evidence['operations.jsonl'], logs)
    need(replay['config_sha256'] == digest(evidence['config.json']) and
         replay['compiler_binding_sha256'] == digest(evidence['compiler-binding.json']), 'replayed_binding_mismatch')
    state = decode(evidence['state.json'], CAPS['state'])
    keys(state, 'schema config_sha256 phase next_sequence completed_calls total_hashed_bytes journal_bytes'.split(), 'invalid_final_state')
    need(state['schema'] == 'appimage-relro-state-v1' and state['phase'] == 'sealed' and
         state['config_sha256'] == replay['config_sha256'] and all(type(state[k]) is int for k in
         ('next_sequence', 'completed_calls', 'total_hashed_bytes', 'journal_bytes')) and
         state['next_sequence'] == replay['calls'] + 1 and state['completed_calls'] == replay['calls'] and
         state['journal_bytes'] == replay['journal_bytes'] and
         replay['total_observed_bytes'] <= state['total_hashed_bytes'] <= CAPS['hashed'], 'unsealed_or_contradictory_state')
    inventories = []
    for records in (appdir_records, image_records):
        need(type(records) is dict and set(PROTECTED) <= set(records) and len(records) <= 8192, 'missing_protected_inventory')
        checked = {}
        for path, record in records.items():
            canonical('/' + path)
            need(type(record) is dict, 'invalid_inventory_record')
            family = any(Path(path).name.startswith('lib' + f + '-2.0.so') for f in FAMILIES)
            need(not family or path in PROTECTED, 'extra_protected_family_member')
            need(not any(s in path.lower() for s in ('gstreamer', 'gst-plugin-scanner', 'gst-ptp-helper')),
                 'unreviewed_media_inventory')
            seen, destination = set(), path
            while records.get(destination, {}).get('kind') == 'symlink':
                need(destination not in seen and len(seen) < 8, 'cyclic_or_excess_inventory_links')
                seen.add(destination); link = records[destination].get('target')
                need(type(link) is str and 0 < len(link.encode()) <= CAPS['path'] and '\\' not in link and
                     all(ord(ch) >= 32 and ord(ch) != 127 for ch in link), 'invalid_inventory_link')
                destination = posixpath.normpath(posixpath.join(posixpath.dirname(destination), link))
                need(destination.lstrip('/') not in PROTECTED, 'linked_protected_alias')
            if path not in PROTECTED: continue
            need(record.get('kind') == 'file' and type(record.get('mode')) is int and
                 record['mode'] == PROTECTED[path]['mode'] and type(record.get('nlink')) is int and record['nlink'] == 1,
                 'linked_or_wrong_mode_protected_member')
            data = record['data']; actual = byte_record(data)
            need(actual == {k: record[k] for k in ('size', 'sha256')}, 'changed_final_member_record')
            checked[path] = dict(**actual, mode=record['mode'], kind='file', nlink=1,
                dynamic_relro=protected_bytes(path, data, compiler_records['compiled']))
        inventories.append(checked)
    need(inventories[0] == inventories[1], 'appdir_image_bytes_differ')
    for line in evidence['operations.jsonl'].splitlines():
        event = decode(line, CAPS['event']); record = event.get('before', event.get('after'))
        if record is not None and record['target'] in PROTECTED:
            need(all(record[k] == inventories[0][record['target']][k] for k in ('size', 'sha256', 'mode', 'nlink')),
                 'operation_final_identity_mismatch')
    identity(appimage_record)
    keys(package_references, {'prebundle', 'raw_deb', 'final_deb'}, 'invalid_package_references')
    need(package_references['prebundle'] == binding['prebundle'], 'prebundle_reference_mismatch')
    compiled = compiler_records['compiled']; offset = compiled.index(deb.UNK)
    deb_hash = digest(compiled[:offset] + deb.DEB + compiled[offset + len(deb.UNK):])
    for key in ('raw_deb', 'final_deb'):
        item = package_references[key]; keys(item, {'size', 'sha256', 'payload_sha256'}, 'invalid_deb_reference')
        identity({k: item[k] for k in ('size', 'sha256')})
        need(item['payload_sha256'] == deb_hash, 'deb_payload_reference_mismatch')
    result = dict(schema='appimage-relro-final-v1', profile=PROFILE, source_sha=c['source_sha'],
        source_tree=c['source_tree'], producer=c['producer'], **replay, tool_sha256=TOOL_SHA256,
        parser_tool_sha256=digest(evidence['parser-tool.json']), appdir= inventories[0], image=inventories[1],
        appimage=appimage_record, packages=package_references, failure=False, protected_input_identity_verified=True,
        protected_bytes_preserved=True, protected_dynamic_relro_verified=True)
    result.update(FALSE_FLAGS)
    if 'final.json' in evidence: need(decode(evidence['final.json'], CAPS['final']) == result, 'untrusted_final_claims')
    return result
