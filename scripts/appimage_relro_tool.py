"""Stage the authenticated embedded patchelf and bind one completed compiler run."""
from __future__ import annotations
import base64
import hashlib
import os
from pathlib import Path
import platform
import re
import stat
import sys

import appimage_relro_contract as c
import desktop_glib_build_contract as io
from appimage_relro_guard import BOOT_HASH_BYTES, bounded_child, encoded, owned_fd, original_descriptor, write_all

PARSER = '/usr/bin/unsquashfs'
OPTIONS = ('-cat', '-o', '-llnumeric', '-strict-errors', '-no-wildcards', '-processors', '-data-queue', '-frag-queue')
FAMILIES = ('glib', 'gio', 'gobject', 'gmodule')


def exact_bytes(data, size, sha256):
    c.need(type(data) is bytes and len(data) == size and hashlib.sha256(data).hexdigest() == sha256,
           'pinned_bytes_mismatch')


def listing_member(raw):
    """Validate the complete fixed archive listing, without extracting any paths."""
    c.need(len(raw) <= 1024**2, 'listing_limit')
    entries = {}
    for line in raw.decode('utf-8', errors='strict').splitlines():
        match = re.fullmatch(r'([dl-][rwxstST-]{9})\s+([0-9]+)/([0-9]+)\s+([0-9]+)\s+[0-9-]+\s+[0-9:]+\s+(squashfs-root(?:/.*)?)', line)
        c.need(match is not None, 'invalid_parser_listing')
        mode, uid, gid, size, text = match.groups()
        path, sep, link = text.partition(' -> ')
        c.need(all(ord(ch) >= 32 and ord(ch) != 127 for ch in text) and '\\' not in path and
               all(part not in ('', '.', '..') for part in path.split('/')), 'unsafe_archive_path')
        c.need(path not in entries and (mode[0] == 'l') == bool(sep), 'duplicate_or_conflicting_archive_path')
        c.need(not any(ch in mode for ch in 'sStT'), 'unsafe_archive_mode')
        entries[path] = {'kind': mode[0], 'mode': mode, 'size': int(size)}
    for path in entries:
        c.need(all(entries.get(str(parent), {}).get('kind') == 'd'
                   for parent in Path(path).parents if str(parent) != '.'), 'invalid_archive_ancestor')
    for path in ('squashfs-root', 'squashfs-root/usr', 'squashfs-root/usr/bin'):
        c.need(entries.get(path, {}).get('kind') == 'd', 'invalid_tool_ancestor')
    entry = entries.get('squashfs-root/usr/bin/patchelf')
    c.need(entry is not None and entry['kind'] == '-' and entry['mode'] == '-rwxr-xr-x'
           and entry['size'] == c.TOOL_SIZE, 'invalid_original_member')
    return {'entries': len(entries), 'member': 'usr/bin/patchelf', **entry}


def parser_identity():
    data, record = c.observe(PARSER, owned=False)
    c.need(record['uid'] == 0 and record['mode'] & 0o022 == 0 and record['mode'] & 0o111,
           'unsafe_parser_identity')
    os_release = platform.freedesktop_os_release()
    c.need(os_release.get('ID') == 'ubuntu' and os_release.get('VERSION_ID') == '22.04', 'wrong_parser_os')
    with io.regular_descriptor('/usr/bin/dpkg-query') as (fd, _):
        code, out, err = bounded_child(fd, ['/usr/bin/dpkg-query', '-S', PARSER], stdout_limit=65536, stderr_limit=65536)
        c.need(code == 0 and out == b'squashfs-tools: /usr/bin/unsquashfs\n' and not err, 'wrong_parser_package')
        code, version, err = bounded_child(fd, ['/usr/bin/dpkg-query', '-W', '-f=${Status}\t${Version}\n', 'squashfs-tools'], stdout_limit=65536, stderr_limit=65536)
        c.need(code == 0 and version.startswith(b'install ok installed\t') and len(version.splitlines()) == 1 and not err,
               'parser_package_not_installed')
    with io.regular_descriptor(PARSER) as (fd, _):
        code, out, err = bounded_child(fd, [PARSER, '-help'], stdout_limit=1024**2, stderr_limit=65536)
    help_bytes = out+err
    c.need(code in (0, 1) and all(option.encode() in help_bytes for option in OPTIONS), 'parser_missing_capability')
    return {'executable': record, 'os': {'id': os_release['ID'], 'version': os_release['VERSION_ID']},
            'package': version.decode().strip(), 'help_sha256': hashlib.sha256(help_bytes).hexdigest(), 'options': list(OPTIONS)}


def parser_call(parser_fd, archive_fd, mode, output_fd=None):
    args = [PARSER, mode, '-o', str(c.OUTER_OFFSET), '-strict-errors', '-no-wildcards',
            '-processors', '1', '-data-queue', '4', '-frag-queue', '4', f'/proc/self/fd/{archive_fd}']
    if mode == '-cat': args.append('usr/bin/patchelf')
    code, out, err = bounded_child(parser_fd, args, env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'},
        stdout_limit=c.TOOL_SIZE if mode == '-cat' else 1024**2, stderr_limit=65536, limits=True, extra_fds=(archive_fd,), stdout_fd=output_fd)
    c.need(code == 0 and not err, 'parser_failed')
    return out


def stage_file(path, data, staged=False):
    fd = owned_fd(path, os.O_RDONLY if staged else os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    try:
        if not staged: write_all(fd, data)
        exact_bytes(data, c.TOOL_SIZE, c.TOOL_SHA256)
        _, record = c.observe(path, mode=0o600)
        c.need(record['sha256'] == c.TOOL_SHA256 and record['size'] == c.TOOL_SIZE, 'staged_tool_changed')
        os.fchmod(fd, 0o500)
        os.fsync(fd)
    finally:
        os.close(fd)


def tool_probes(config):
    root = Path(config['original_patchelf_path']).parent
    probe = root/'probe'
    with io.parent_descriptor(probe) as (parent, name): os.mkdir(name, 0o700, dir_fd=parent)
    host, host_record = c.observe('/usr/bin/true', owned=False)
    paths = [probe/'readonly', probe/'mutation']
    for path in paths:
        fd = owned_fd(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        try: write_all(fd, host)
        finally: os.close(fd)
    results = []
    calls = [(['--version'], None), (['--print-rpath', str(paths[0])], paths[0]),
             (['--set-rpath', '$ORIGIN', str(paths[1])], paths[1]), (['--print-rpath', str(paths[1])], paths[1])]
    for index, (argv, path) in enumerate(calls):
        before = c.observe(path)[1] if path else None
        fd, tool_before = original_descriptor(config)
        try: code, out, err = bounded_child(fd, [config['original_patchelf_path'], *argv], stdout_limit=16384, stderr_limit=16384)
        finally: os.close(fd)
        c.need(c.observe(config['original_patchelf_path'], mode=0o500)[1] == tool_before, 'probe_tool_changed')
        after = c.observe(path)[1] if path else None
        c.need(code == 0 and not err, 'original_probe_failed')
        c.need(index != 0 or out == b'patchelf 0.8\n', 'wrong_original_version')
        c.need(index not in (1, 3) or before == after, 'probe_query_changed_input')
        c.need(index != 2 or before['sha256'] != after['sha256'], 'probe_mutation_missing')
        c.need(index != 3 or out == b'$ORIGIN\n', 'probe_rpath_mismatch')
        results.append({'argv': argv, 'exit': code, 'stdout': base64.b64encode(out).decode(),
                        'stderr': base64.b64encode(err).decode(), 'before': before, 'after': after})
    c.need({p.name for p in probe.iterdir()} == {'readonly', 'mutation'}, 'unexpected_probe_file')
    for path in paths:
        c.observe(path, mode=0o600)
        path.unlink()
    probe.rmdir()
    return {'host_copy': host_record, 'calls': results}


def stage_original(config_inputs):
    config = config_inputs['config']
    original = Path(config_inputs['originals_dir'])/'linuxdeploy-x86_64.AppImage'
    parser = parser_identity()
    with io.regular_descriptor(original, c.OUTER_SIZE) as (archive_fd, archive_info):
        outer, observed = c.observe(original, mode=0o444)
        exact_bytes(outer, c.OUTER_SIZE, c.OUTER_SHA256)
        c.need((archive_info.st_dev, archive_info.st_ino) == (observed['device'], observed['inode']), 'archive_replaced')
        with io.regular_descriptor(PARSER) as (parser_fd, parser_info):
            c.need(c.observe(PARSER, owned=False)[1] == parser['executable'], 'parser_changed')
            c.need((parser_info.st_dev, parser_info.st_ino) == (parser['executable']['device'], parser['executable']['inode']), 'parser_replaced')
            listing = listing_member(parser_call(parser_fd, archive_fd, '-llnumeric'))
            destination = owned_fd(Path(config['original_patchelf_path']), os.O_WRONLY | os.O_CREAT | os.O_EXCL)
            try:
                data = parser_call(parser_fd, archive_fd, '-cat', destination)
                os.fsync(destination)
            finally: os.close(destination)
            exact_bytes(data, c.TOOL_SIZE, c.TOOL_SHA256)
            c.need(c.observe(PARSER, owned=False)[1] == parser['executable'], 'parser_changed')
        c.need(c.observe(original, mode=0o444)[1] == observed and io.file_identity(archive_info) == io.file_identity(os.fstat(archive_fd)), 'archive_replaced')
    stage_file(Path(config['original_patchelf_path']), data, staged=True)
    probes = tool_probes(config)
    receipt = {'schema': 'appimage-relro-tool-v1', 'outer': observed, 'offset': c.OUTER_OFFSET,
               'parser': parser, 'listing': listing, 'original': c.observe(config['original_patchelf_path'], mode=0o500)[1], 'probes': probes}
    c.need(len(encoded(receipt, 65536)) <= 65536, 'tool_receipt_limit')
    io.write_json(Path(config['original_patchelf_path']).parent/'parser-tool.json', receipt)
    return receipt


def host_alias_record(item):
    c.keys(item, {'path', 'target', 'device', 'inode'}, 'invalid_alias_record')
    c.need(type(item['path']) is str, 'invalid_alias_path')
    c.canonical(item['path'])
    target = item['target']
    c.need(Path(item['path']).parent == Path('/usr/lib/x86_64-linux-gnu') and type(target) is str and
           0 < len(target.encode()) <= c.CAPS['path'] and target not in ('.', '..') and
           '/' not in target and '\\' not in target and all(ord(ch) >= 32 and ord(ch) != 127 for ch in target),
           'escaping_host_alias')
    c.need(type(item['device']) is int and 0 <= item['device'] <= (1 << 64) - 1 and
           type(item['inode']) is int and 0 < item['inode'] <= (1 << 64) - 1, 'invalid_alias_file_identity')


def host_glib_inputs():
    base, originals, aliases = Path('/usr/lib/x86_64-linux-gnu'), {}, {}
    for family in FAMILIES:
        path = base/f'lib{family}-2.0.so.0.7200.4'
        data, record = c.observe(path, owned=False, mode=0o644)
        pin = next(value for value in c.PROTECTED.values() if value['family'] == family)
        exact_bytes(data, pin['size'], pin['sha256'])
        originals[family] = record
        for suffix in ('.so', '.so.0'):
            alias = base/f'lib{family}-2.0{suffix}'
            chain, visited = [], set()
            while alias != path:
                c.need(str(alias) not in visited and len(chain) < 8 and alias.parent == base, 'unsafe_host_alias')
                visited.add(str(alias))
                info = alias.lstat()
                c.need(stat.S_ISLNK(info.st_mode) and info.st_uid == 0, 'invalid_host_alias')
                target = os.readlink(alias)
                c.need(io.file_identity(info) == io.file_identity(alias.lstat()), 'host_alias_changed')
                item = {'path': str(alias), 'target': target, 'device': info.st_dev, 'inode': info.st_ino}
                host_alias_record(item)
                chain.append(item)
                alias = base/target
            aliases[f'{family}{suffix}'] = chain
    return {'originals': originals, 'aliases': aliases}


def prepare_session(source_binding, target, evidence, tools, python):
    target, evidence = Path(c.canonical(str(target))), Path(c.canonical(str(evidence)))
    source = Path(c.canonical(source_binding['source_root']))
    originals = Path(c.canonical(tools['originals_dir']))
    roots = (source, target, evidence, originals)
    c.need(all(a != b and not a.is_relative_to(b) and not b.is_relative_to(a)
               for i, a in enumerate(roots) for b in roots[i+1:]), 'overlapping_session_paths')
    for path in (target, evidence):
        with io.parent_descriptor(path/'anchor') as (fd, _):
            info = os.fstat(fd)
            c.need(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700, 'unowned_session_root')
    root = evidence/'appimage-relro'
    with io.parent_descriptor(root) as (parent, name): os.mkdir(name, 0o700, dir_fd=parent)
    guard = source/'scripts/appimage_relro_guard.py'
    _, guard_record = c.observe(guard, mode=0o755)
    from linux_package_provenance_contract import guard_python_identity
    guard_python_identity(python)
    _, interpreter = c.observe(python['path'], owned=False, mode=0o755)
    c.need(source_binding['profile'] == c.PROFILE and interpreter['uid'] == 0 and
           all(interpreter[k] == python[k] for k in ('size', 'sha256')), 'python_identity_changed')
    config = {key: source_binding[key] for key in ('profile', 'source_sha', 'source_tree', 'producer', 'source_root')}
    config.update(schema='appimage-relro-config-v1', target_root=str(target), evidence_root=str(evidence),
        appdir_root=str(target/'x86_64-unknown-linux-gnu/release/bundle/appimage/Coding Tools MCP.AppDir'),
        compiler_binding_path=str(root/'compiler-binding.json'), desktop_elf_path=str(evidence/'desktop.elf'),
        original_patchelf_path=str(root/'original-patchelf'), original_patchelf_size=c.TOOL_SIZE,
        original_patchelf_sha256=c.TOOL_SHA256, guard_path=str(guard), guard_sha256=guard_record['sha256'],
        guard_mode=0o755, python_path=python['path'], python_sha256=python['sha256'], python_version=python['version'],
        protected=c.PROTECTED, caps=c.CAPS)
    c.validate_config(config)
    encoded(config, c.CAPS['config'])
    inputs = host_glib_inputs()
    stage_original({'config': config, 'originals_dir': str(originals)})
    # Host provenance is bounded in the existing single tool receipt, not a new path.
    receipt = io.decode(io.read_regular(root/'parser-tool.json', 65536))
    receipt['host_glib'] = inputs
    data = encoded(receipt, 65536)
    fd = owned_fd(root/'parser-tool.json', os.O_WRONLY)
    try:
        os.ftruncate(fd, 0)
        write_all(fd, data)
    finally: os.close(fd)
    io.write_json(root/'config.json', config)
    fd = owned_fd(root/'config.json', os.O_RDONLY)
    try: os.fchmod(fd, 0o400)
    finally: os.close(fd)
    config_hash = io.file_record(root/'config.json')['sha256']
    for name in ('lock', 'operations.jsonl'):
        fd = owned_fd(root/name, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        os.close(fd)
    io.write_json(root/'state.json', {'schema': 'appimage-relro-state-v1', 'config_sha256': config_hash,
        'phase': 'prepared', 'next_sequence': 1, 'completed_calls': 0, 'total_hashed_bytes': BOOT_HASH_BYTES, 'journal_bytes': 0})
    return config


def bind_compiler(config, compiler_records):
    if not isinstance(config, dict): config = c.read_config(config)
    c.validate_config(config)
    evidence = Path(config['evidence_root'])
    c.need(io.decode(io.read_regular(evidence/'cargo-exit.json')) == {'exit': 0}, 'compiler_not_finished')
    copies_raw = io.read_regular(evidence/'compiler-copies.json')
    c.need(io.decode(copies_raw) == compiler_records and set(compiler_records) == {'events', 'copies'}, 'compiler_copies_mismatch')
    build_raw = io.read_regular(evidence/'build.jsonl')
    events = io.verify_compiler_events(io.decode(io.read_regular(evidence/'metadata.json')),
        io.read_regular(evidence/'selected-tree.txt').decode(), build_raw, config['source_root'], config['target_root'])
    c.need(events == compiler_records['events'], 'compiler_event_mismatch')
    executable = events['root']['executable']
    prebundle = io.file_record(evidence/'desktop.elf')
    c.need(prebundle == compiler_records['copies']['desktop'] and io.file_record(executable, single_link=False) == prebundle,
           'compiler_copy_changed')
    binding = {key: config[key] for key in ('profile', 'source_sha', 'source_tree', 'producer', 'target_root')}
    binding.update(schema='appimage-relro-compiler-v1', compiler_copies_sha256=hashlib.sha256(copies_raw).hexdigest(),
        build_jsonl_sha256=hashlib.sha256(build_raw).hexdigest(), prebundle=prebundle, event_executable=executable)
    encoded(binding, c.CAPS['binding'])
    io.write_json(Path(config['compiler_binding_path']), binding)
    return binding


def verify_tool_receipt(raw):
    """Replay bounded staging/probe evidence; never execute an evidence-selected tool."""
    value = io.decode(raw, 65536)
    c.keys(value, {'schema','outer','offset','parser','listing','original','probes','host_glib'}, 'invalid_tool_receipt')
    c.need(value['schema'] == 'appimage-relro-tool-v1' and value['offset'] == c.OUTER_OFFSET, 'wrong_tool_schema')
    for record, size, sha256, mode in ((value['outer'],c.OUTER_SIZE,c.OUTER_SHA256,0o444),
                                      (value['original'],c.TOOL_SIZE,c.TOOL_SHA256,0o500)):
        c.keys(record, c.RECORD_KEYS, 'invalid_tool_record'); c.operation_record(record)
        c.need(record['size'] == size and record['sha256'] == sha256 and record['mode'] == mode
               and record['nlink'] == 1, 'wrong_tool_pin')
    parser = value['parser']
    c.keys(parser['executable'], c.RECORD_KEYS, 'invalid_parser_file'); c.operation_record(parser['executable'])
    c.keys(parser, {'executable','os','package','help_sha256','options'}, 'invalid_parser_receipt')
    c.need(parser['executable']['target'] == PARSER and parser['executable']['uid'] == 0 and
           parser['executable']['mode'] & 0o022 == 0 and parser['executable']['mode'] & 0o111 and
           parser['os'] == {'id':'ubuntu','version':'22.04'} and
           re.fullmatch(r'install ok installed\t[^\s]+', parser['package']) and
           parser['options'] == list(OPTIONS) and re.fullmatch('[0-9a-f]{64}', parser['help_sha256']), 'wrong_parser_receipt')
    listing = value['listing']
    c.keys(listing, {'entries','member','kind','mode','size'}, 'wrong_listing_receipt')
    c.need(type(listing['entries']) is int and 4 <= listing['entries'] <= 10000 and
           listing['member'] == 'usr/bin/patchelf' and listing['kind'] == '-' and listing['mode'] == '-rwxr-xr-x'
           and listing['size'] == c.TOOL_SIZE, 'wrong_listed_tool')
    probes = value['probes']
    c.keys(probes, {'host_copy','calls'}, 'invalid_probes')
    c.keys(probes['host_copy'], c.RECORD_KEYS, 'invalid_probe_host'); c.operation_record(probes['host_copy'])
    c.need(probes['host_copy']['target'] == '/usr/bin/true' and len(probes['calls']) == 4, 'wrong_probe_input')
    root = str(Path(value['original']['target']).parent/'probe')
    expected = [['--version'], ['--print-rpath',root+'/readonly'],
                ['--set-rpath','$ORIGIN',root+'/mutation'], ['--print-rpath',root+'/mutation']]
    for i, call in enumerate(probes['calls']):
        c.keys(call, {'argv','exit','stdout','stderr','before','after'}, 'invalid_probe_record')
        c.need(call['argv'] == expected[i] and type(call['exit']) is int and call['exit'] == 0, 'failed_probe')
        try:
            out = base64.b64decode(call['stdout'], validate=True)
            err = base64.b64decode(call['stderr'], validate=True)
        except (ValueError, TypeError) as exc: raise io.exact.EvidenceError('invalid_probe_stream') from exc
        c.need(len(out) <= 16384 and not err, 'wrong_probe_stream')
        if i == 0:
            c.need(out == b'patchelf 0.8\n' and call['before'] is call['after'] is None, 'wrong_version_probe')
        else:
            for record in (call['before'], call['after']):
                c.keys(record, c.RECORD_KEYS, 'invalid_probe_identity'); c.operation_record(record)
            c.need(call['before']['target'] == call['after']['target'] == expected[i][-1], 'wrong_probe_path')
            if i in (1,3): c.need(call['before'] == call['after'], 'probe_query_mutated')
            if i in (1,2): c.need({k:call['before'][k] for k in ('size','sha256')} ==
                                 {k:probes['host_copy'][k] for k in ('size','sha256')}, 'wrong_probe_copy')
            if i == 2: c.need(call['before']['sha256'] != call['after']['sha256'], 'missing_probe_mutation')
            if i == 3: c.need(out == b'$ORIGIN\n' and call['before'] == probes['calls'][2]['after'], 'wrong_probe_rpath')
    host = value['host_glib']
    c.keys(host, {'originals','aliases'}, 'invalid_host_glib')
    c.need(set(host['originals']) == set(FAMILIES) and set(host['aliases']) ==
           {family+suffix for family in FAMILIES for suffix in ('.so','.so.0')}, 'wrong_host_glib_inventory')
    for family, record in host['originals'].items():
        pin = next(v for v in c.PROTECTED.values() if v['family'] == family)
        c.keys(record, c.RECORD_KEYS, 'invalid_host_file'); c.operation_record(record)
        c.need(record['target'] == '/usr/lib/x86_64-linux-gnu/lib'+family+'-2.0.so.0.7200.4' and
               record['size'] == pin['size'] and record['sha256'] == pin['sha256'] and record['mode'] == 0o644 and record['uid'] == 0,
               'wrong_signed_host_glib')
    for name, chain in host['aliases'].items():
        c.need(type(chain) is list and 1 <= len(chain) <= 8, 'invalid_alias_chain')
        family, suffix = name.split('.so',1)
        expected_path = '/usr/lib/x86_64-linux-gnu/lib'+family+'-2.0.so'+suffix
        visited = set()
        for item in chain:
            host_alias_record(item)
            c.need(item['path'] == expected_path and expected_path not in visited and
                   expected_path != host['originals'][family]['target'], 'wrong_alias_chain')
            visited.add(expected_path)
            expected_path = '/usr/lib/x86_64-linux-gnu/'+item['target']
            c.need(expected_path not in visited, 'cyclic_host_alias')
        c.need(expected_path == host['originals'][family]['target'], 'wrong_alias_destination')
    return value
