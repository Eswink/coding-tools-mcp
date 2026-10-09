"""Stage I build/byte-inspection only. Never runs ROOT or imports the bridge.

Default --describe starts no subprocess. --compile is a distinct authorized
compiler operation; its artifacts are PRIVATE and excluded from source backup.
Build identity is not kernel support, lifecycle success, or release qualification.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import selectors
import shlex
import signal
import struct
import subprocess
import sys
import time

GCC = Path('/usr/bin/x86_64-linux-gnu-gcc-14')
READELF = Path('/usr/bin/x86_64-linux-gnu-readelf')
OBJDUMP = Path('/usr/bin/x86_64-linux-gnu-objdump')
OUTER = Path('/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python3.12')
INCLUDE = OUTER.parent.parent / 'include/python3.12'
GCC_LIB = Path('/usr/lib/gcc/x86_64-linux-gnu/14')
TOOLS = (GCC, Path('/usr/libexec/gcc/x86_64-linux-gnu/14/cc1'),
         Path('/usr/libexec/gcc/x86_64-linux-gnu/14/collect2'),
         Path('/usr/bin/x86_64-linux-gnu-as'), Path('/usr/bin/as'),
         Path('/usr/bin/x86_64-linux-gnu-ld.bfd'), Path('/usr/bin/ld'),
         READELF, OBJDUMP, OUTER)
SOURCE_NAMES = ('syscall_x86_64.h', 'birth_entry.S', 'birth_module.c',
                'root_entry.S', 'root_collector.c', 'owner_adapter.py',
                'ordinary_controls.py', 'build_source_owner.py')
LIB_DIRS = (Path('/lib/x86_64-linux-gnu'), Path('/usr/lib/x86_64-linux-gnu'),
            Path('/lib'), Path('/usr/lib'), GCC_LIB)
ENV = {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'TZ': 'UTC'}
LOG_LIMIT = 2 * 1024 * 1024
JOB_SECONDS = 120.0  # includes bounded termination/drain, never restarted
FILE_LIMIT = 128 * 1024 * 1024
INPUT_FILES = 4096
INPUT_BYTES = 512 * 1024 * 1024


def save_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def file_identity(path, remaining=FILE_LIMIT):
    path = Path(path).absolute()
    link = path.lstat()
    actual = path.resolve(strict=True)
    with actual.open('rb') as stream:
        before = os.fstat(stream.fileno())
        limit = min(FILE_LIMIT, remaining)
        if before.st_size > limit or not actual.is_file():
            raise RuntimeError('unbounded_or_nonregular_input: ' + str(path))
        data = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    if len(data) > limit or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise RuntimeError('input_changed_while_reading: ' + str(path))
    return {'path': str(path), 'resolved': str(actual), 'bytes': len(data),
            'sha256': hashlib.sha256(data).hexdigest(), 'dev': before.st_dev,
            'ino': before.st_ino, 'mode': before.st_mode, 'nlink': before.st_nlink,
            'mtime_ns': before.st_mtime_ns, 'link_dev': link.st_dev,
            'link_ino': link.st_ino, 'link_mode': link.st_mode,
            'link_target': os.readlink(path) if path.is_symlink() else None}


def snapshot(paths):
    paths = sorted(set(map(str, paths)))
    if len(paths) > INPUT_FILES:
        raise RuntimeError('input_file_bound_exceeded')
    result, total = {}, 0
    for path in paths:
        identity = file_identity(path, INPUT_BYTES - total)
        total += identity['bytes']
        result[str(Path(path).absolute())] = identity
    return result


def check_unchanged(before):
    after = snapshot(before)
    differences = [name for name in before if before[name] != after[name]]
    if differences:
        raise RuntimeError('frozen_input_changed: ' + repr(differences))
    return after


def elf_dependencies(path):
    data = Path(path).read_bytes()
    if len(data) > FILE_LIMIT or data[:6] != b'\x7fELF\x02\x01':
        raise RuntimeError('requires_bounded_ELF64_little_endian: ' + str(path))
    header = struct.unpack_from('<HHIQQQIHHHHHH', data, 16)
    kind, machine, _, entry, phoff, shoff, _, _, phsize, phnum, shsize, shnum, names = header
    if machine != 62 or phsize != 56 or (shnum and shsize != 64):
        raise RuntimeError('unsupported_ELF_ABI: ' + str(path))
    programs = [struct.unpack_from('<IIQQQQQQ', data, phoff + i * phsize) for i in range(phnum)]
    loads = [p for p in programs if p[0] == 1]
    interpreter = None
    dynamic = []
    for program in programs:
        if program[2] + program[5] > len(data):
            raise RuntimeError('ELF_segment_out_of_bounds')
        if program[0] == 3:
            interpreter = data[program[2]:program[2] + program[5]].rstrip(b'\0').decode()
        if program[0] == 2:
            for offset in range(program[2], program[2] + program[5], 16):
                tag, value = struct.unpack_from('<qQ', data, offset)
                if tag == 0:
                    break
                dynamic.append((tag, value))
    straddr = next((value for tag, value in dynamic if tag == 5), None)
    strsize = next((value for tag, value in dynamic if tag == 10), 0)
    strings = b''
    if straddr is not None:
        segment = next((p for p in loads if p[3] <= straddr < p[3] + p[5]), None)
        if segment is None:
            raise RuntimeError('dynamic_strings_not_file_backed')
        offset = segment[2] + straddr - segment[3]
        strings = data[offset:offset + strsize]
    needed, runpath, rpath = [], [], []
    for tag, value in dynamic:
        if tag not in (1, 15, 29):
            continue
        end = strings.find(b'\0', value)
        if end < 0:
            raise RuntimeError('unterminated_ELF_string')
        text = strings[value:end].decode()
        if tag == 1:
            needed.append(text)
        elif tag == 29:
            runpath.extend(text.split(':'))
        else:
            rpath.extend(text.split(':'))
    sections = [struct.unpack_from('<IIQQQQIIQQ', data, shoff + i * shsize) for i in range(shnum)]
    section_strings = b''
    if sections:
        section_strings = data[sections[names][4]:sections[names][4] + sections[names][5]]
    named_sections, symbols = {}, []
    for section in sections:
        end = section_strings.find(b'\0', section[0])
        name = section_strings[section[0]:end].decode() if end >= 0 else ''
        named_sections[name] = section[5]
        if section[1] not in (2, 11):
            continue
        string_section = sections[section[6]]
        table = data[string_section[4]:string_section[4] + string_section[5]]
        if section[9] != 24:
            raise RuntimeError('unexpected_ELF_symbol_size')
        for offset in range(section[4], section[4] + section[5], 24):
            name_offset, _, _, index, value, size = struct.unpack_from('<IBBHQQ', data, offset)
            end = table.find(b'\0', name_offset)
            name = table[name_offset:end].decode() if end >= 0 else ''
            if name:
                symbols.append({'name': name, 'section': index, 'value': value, 'size': size})
    return {'type': kind, 'entry': entry, 'interpreter': interpreter, 'needed': needed,
            'runpath': runpath, 'rpath': rpath, 'loads': loads,
            'sections': named_sections, 'symbols': symbols}


def cache_entries():
    data = Path('/etc/ld.so.cache').read_bytes()
    if len(data) > 4 * 1024 * 1024 or not data.startswith(b'glibc-ld.so.cache1.1'):
        raise RuntimeError('unsupported_loader_cache_format')
    count = struct.unpack_from('<I', data, 20)[0]
    if count > 65536 or 48 + count * 24 > len(data):
        raise RuntimeError('unbounded_loader_cache')
    result = {}
    for i in range(count):
        flags, key, value, _, hwcap = struct.unpack_from('<iIIIQ', data, 48 + i * 24)
        if flags & 0xff00 != 0x0300:
            continue  # not x86-64 libc6
        key_end, value_end = data.find(b'\0', key), data.find(b'\0', value)
        if key_end < 0 or value_end < 0:
            raise RuntimeError('invalid_loader_cache_string')
        result.setdefault(data[key:key_end].decode(), []).append(
            (Path(data[value:value_end].decode()), hwcap))
    return result


def resolve_needed(name, origin, runpath, cache):
    if '/' in name:
        if not name.startswith('/'):
            raise RuntimeError('relative_needed_path_is_unsupported')
        return Path(name).resolve(strict=True)
    directories = []
    for directory in runpath:
        directory = directory.replace('${ORIGIN}', str(origin)).replace('$ORIGIN', str(origin))
        if not directory or '$' in directory or not directory.startswith('/'):
            raise RuntimeError('unresolved_dynamic_search_path')
        directories.append(Path(directory))
    # Refuse unresolved alternate hardware implementations, rather than guess CPU capabilities.
    for directory in directories + list(LIB_DIRS):
        hw = directory / 'glibc-hwcaps'
        if hw.is_dir() and any((child / name).is_file() for child in hw.iterdir()):
            raise RuntimeError('unresolved_hardware_library_variant: ' + name)
    for directory in directories:
        candidate = directory / name
        if candidate.is_file():
            return candidate.resolve(strict=True)
    cached = cache.get(name, [])
    if any(hwcap and path.exists() for path, hwcap in cached):
        raise RuntimeError('unresolved_cached_hardware_variant: ' + name)
    matches = {path.resolve(strict=True) for path, hwcap in cached if not hwcap and path.is_file()}
    if not matches:
        matches = {(directory / name).resolve(strict=True) for directory in LIB_DIRS
                   if (directory / name).is_file()}
    if len(matches) != 1:
        raise RuntimeError('ambiguous_or_missing_dynamic_dependency: ' + name)
    return next(iter(matches))


def tool_closure():
    cache = cache_entries()
    pending, paths = list(TOOLS), set()
    support = [p for p in Path('/usr/libexec/gcc/x86_64-linux-gnu/14').rglob('*') if p.is_file()]
    support += [p for p in GCC_LIB.rglob('*') if p.is_file()]
    support += [Path('/usr/x86_64-linux-gnu/bin') / name for name in ('as', 'ld')]
    for path in support:
        with path.open('rb') as stream:
            if stream.read(4) == b'\x7fELF':
                pending.append(path)
    while pending:
        path = Path(pending.pop()).absolute()
        if path in paths:
            continue
        if len(paths) >= INPUT_FILES:
            raise RuntimeError('dynamic_tool_closure_file_bound_exceeded')
        paths.add(path)
        info = elf_dependencies(path)
        if info['rpath']:
            raise RuntimeError('DT_RPATH_inheritance_not_implemented: ' + str(path))
        if info['interpreter']:
            pending.append(Path(info['interpreter']))
        pending.extend(resolve_needed(name, path.resolve().parent, info['runpath'], cache)
                       for name in info['needed'])
    paths.update((Path('/etc/ld.so.cache'), Path('/etc/ld.so.conf')))
    paths.update(p for p in Path('/etc/ld.so.conf.d').glob('*') if p.is_file())
    # Compiler/linker defaults and implicit archives/CRT are frozen before -M or compilation.
    paths.update(support)
    paths.update(p for p in INCLUDE.rglob('*') if p.is_file())
    paths.update(Path('/usr/lib/x86_64-linux-gnu') / name for name in
                 ('crti.o', 'crtn.o', 'libc.so', 'libc_nonshared.a'))
    return paths


def run_job(argv, out, state, label):
    if Path(argv[0]) not in (GCC, READELF, OBJDUMP):
        raise RuntimeError('compiler_or_byte_inspector_only')
    start = time.monotonic()
    record = {'argv': list(map(str, argv)), 'label': label, 'limit_seconds': JOB_SECONDS}
    state['jobs'].append(record)
    process = subprocess.Popen(record['argv'], cwd=out, env=ENV, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=True, close_fds=True)
    record['actual_created_compiler_pid'] = process.pid  # diagnostic only, never owner grant
    streams = selectors.DefaultSelector()
    outputs, interrupted, kill_sent = {'stdout': bytearray(), 'stderr': bytearray()}, False, False
    primary, failures = None, []
    try:
        for name in outputs:
            stream = getattr(process, name)
            os.set_blocking(stream.fileno(), False)
            streams.register(stream, selectors.EVENT_READ, name)
        while streams.get_map() or process.poll() is None:
            elapsed = time.monotonic() - start
            if elapsed >= JOB_SECONDS - 2 and not interrupted:
                interrupted = True
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            if elapsed >= JOB_SECONDS - 1 and not kill_sent:
                kill_sent = True
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if elapsed >= JOB_SECONDS:
                raise RuntimeError('compiler_job_terminal_or_EOF_unknown')
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
            raise RuntimeError('compiler_or_inspection_job_failed: ' + label)
    except BaseException as error:
        primary = error
        # Stop this actual compiler session, not the proposed ROOT/collector.
        # Cancellation cannot introduce a fresh cleanup deadline.
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
                raise RuntimeError('compiler_terminal_UNKNOWN_at_fixed_deadline')
            process.wait(timeout=remaining)
        except BaseException as cleanup_error:
            failures.append(cleanup_error)
        try:
            while streams.get_map():
                remaining = JOB_SECONDS - (time.monotonic() - start)
                if remaining <= 0:
                    raise RuntimeError('compiler_pipe_EOF_UNKNOWN_at_fixed_deadline')
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
            record['observed_returncode'] = process.poll()
        except BaseException as cleanup_error:
            failures.append(cleanup_error)
        for name, data in outputs.items():
            stream = None
            path = out / (label + '.' + name)
            try:
                stream = path.open('xb')
            except BaseException as cleanup_error:
                failures.append(cleanup_error)
            if stream is not None:
                try:
                    stream.write(data)
                except BaseException as cleanup_error:
                    failures.append(cleanup_error)
                try:
                    stream.close()
                except BaseException as cleanup_error:
                    failures.append(cleanup_error)
            try:
                record[name] = file_identity(path)
            except BaseException as cleanup_error:
                failures.append(cleanup_error)
        for resource in (streams, process.stdout, process.stderr):
            try:
                resource.close()
            except BaseException as cleanup_error:
                failures.append(cleanup_error)
    errors = ([primary] if primary is not None else []) + failures
    if errors:
        record['primary_and_cleanup_error_types'] = [type(error).__name__ for error in errors]
        record['compiler_terminal_and_EOF_is_not_native_family_qualification'] = True
        if len(errors) == 1:
            raise errors[0]
        raise BaseExceptionGroup('compiler_primary_and_independent_cleanup_failures', errors)
    return {name: bytes(data) for name, data in outputs.items()}


def validate_diagnostic(outputs, frozen, selected):
    invocations = []
    for line in outputs['stderr'].decode('utf-8', 'strict').splitlines():
        if line.startswith('COLLECT_LTO_WRAPPER='):
            path = Path(line.partition('=')[2]).resolve(strict=True)
            if not any(item['resolved'] == str(path) for item in frozen.values()):
                raise RuntimeError('LTO_wrapper_not_frozen_before_diagnostic')
        tokens = shlex.split(line)
        if not tokens or tokens[0].startswith('-'):
            continue
        first = tokens[0]
        if not first.startswith('/') and first not in ('as', 'ld'):
            continue
        path = Path(first) if first.startswith('/') else Path('/usr/bin') / first
        if path.name not in ('cc1', 'as', 'x86_64-linux-gnu-as', 'collect2', 'ld', 'x86_64-linux-gnu-ld'):
            raise RuntimeError('unexpected_actual_compiler_child: ' + str(path))
        actual = path.resolve(strict=True)
        if actual not in selected.values() or not any(item['resolved'] == str(actual) for item in frozen.values()):
            raise RuntimeError('compiler_child_not_selected_and_frozen: ' + str(path))
        for i, token in enumerate(tokens[:-1]):
            if token == '-plugin':
                plugin = Path(tokens[i + 1]).resolve(strict=True)
                if not any(item['resolved'] == str(plugin) for item in frozen.values()):
                    raise RuntimeError('actual_link_plugin_not_frozen')
        invocations.append(tokens)
    if not invocations:
        raise RuntimeError('actual_compiler_diagnostic_has_no_child_invocations')
    return invocations


def header_dependencies(source, flags, out, state, label):
    path = out / (label + '.d')
    run_job([str(GCC), *flags, '-M', '-MT', 'frozen', '-MF', str(path), str(source)],
            out, state, label)
    text = path.read_text().replace('\\\n', ' ')
    target, separator, names = text.partition(':')
    if target.strip() != 'frozen' or not separator:
        raise RuntimeError('invalid_actual_M_dependencies')
    return {Path(name).resolve(strict=True) for name in shlex.split(names)}


def embed_root(root, out):
    data = root.read_bytes()
    if not data or len(data) > 128 * 1024:
        raise RuntimeError('root_image_size_refused')
    path = out / 'root_image.inc'
    with path.open('x', encoding='ascii') as stream:
        stream.write('/* GENERATED LOCAL BUILD INPUT. Not a source backup. */\n')
        stream.write('#define RC_ROOT_IMAGE_LENGTH ' + str(len(data)) + 'UL\n')
        stream.write('static const unsigned char rc_root_image[] = {\n')
        for i in range(0, len(data), 16):
            stream.write(','.join('0x%02x' % byte for byte in data[i:i + 16]) + ',\n')
        stream.write('};\n')
    return {'ROOT': file_identity(root), 'include': file_identity(path)}


def inspect_binary(binary, out, state, label, root_bytes=None):
    run_job([str(READELF), '-W', '-a', str(binary)], out, state, label + '-readelf-full')
    run_job([str(OBJDUMP), '-d', '-r', '-w', '-C', str(binary)], out, state, label + '-objdump-full')
    info = elf_dependencies(binary)
    if root_bytes is None:
        forbidden = ('.init', '.fini', '.init_array', '.fini_array', '.preinit_array', '.plt', '.got.plt')
        if info['type'] != 2 or info['interpreter'] or info['needed'] or any(
                info['sections'].get(name, 0) for name in forbidden) or any(
                symbol['section'] == 0 for symbol in info['symbols']):
            raise RuntimeError('root_has_unapproved_runtime_entry_or_imports')
    else:
        symbols = [s for s in info['symbols'] if s['name'] == 'rc_root_image']
        if len(symbols) != 1 or symbols[0]['size'] != len(root_bytes):
            raise RuntimeError('embedded_root_symbol_not_exact')
        symbol = symbols[0]
        load = next((p for p in info['loads'] if p[3] <= symbol['value'] and
                     symbol['value'] + symbol['size'] <= p[3] + p[5]), None)
        if load is None:
            raise RuntimeError('embedded_root_not_file_backed')
        offset = load[2] + symbol['value'] - load[3]
        embedded = binary.read_bytes()[offset:offset + symbol['size']]
        if embedded != root_bytes:
            raise RuntimeError('actual_embedded_root_bytes_differ')
        info['actual_embedded_root_sha256'] = hashlib.sha256(embedded).hexdigest()
    return {'file': file_identity(binary), 'elf': info}


def link_inputs(map_path, out, frozen):
    records = {}
    for line in map_path.read_text().splitlines():
        if not line.startswith('LOAD '):
            continue
        path = Path(line[5:].strip())
        if not path.is_absolute():
            path = out / path
        path = path.resolve(strict=True)
        if not path.is_relative_to(out) and str(path) not in frozen:
            # Aliases must resolve to one input already captured BEFORE this build.
            if not any(item['resolved'] == str(path) for item in frozen.values()):
                raise RuntimeError('actual_link_input_not_frozen_before_build: ' + str(path))
        records[str(path)] = file_identity(path)
    if not records:
        raise RuntimeError('empty_actual_link_map')
    return records


def describe():
    return {'scope': 'Stage I compiler/byte inspection only; no ROOTexec or bridge import',
            'default': 'describe; zero subprocesses', 'explicit_compile': '--compile --out ABSENT_DIR',
            'gcc': str(GCC), 'outer': str(OUTER), 'outer_header': str(INCLUDE),
            'job_seconds_including_cleanup': JOB_SECONDS, 'combined_log_bytes': LOG_LIMIT,
            'input_files_bound': INPUT_FILES, 'combined_input_bytes_bound': INPUT_BYTES,
            'root_image_bytes_bound': 128 * 1024,
            'source_files': SOURCE_NAMES, 'controls': 'NOTRUN',
            'gaps': ['machine-code/source entry review remains independent',
                     'no kernel ABI/support/adoption/closure proof',
                     'unresolved DT_RPATH/hardware library resolution blocks compilation',
                     'source hashes before/after do not exclude privileged mid-build injection']}


def compile_candidate(src, out):
    if Path(sys.executable).resolve() != OUTER.resolve() or sys.version_info[:3] != (3, 12, 14):
        raise RuntimeError('requires_exact_frozen_outer_Python3.12.14')
    if file_identity(OUTER)['sha256'] != 'fa67443527ed9647f760d807e2a38f26340757123e643c4639cf273ed15d5ea7':
        raise RuntimeError('outer_binary_identity_changed')
    if file_identity(GCC)['sha256'] != 'a23ecab8ff08f09ad8c80602c2c5df7f49e09c25905cb8975902e101bf72635f':
        raise RuntimeError('fixed_gcc14_identity_changed')
    if not out.is_absolute() or out.exists() or out.is_relative_to(src):
        raise RuntimeError('exclusive_absent_build_directory_required_outside_source')
    out.mkdir(mode=0o700)
    state = {**describe(), 'status': 'BUILDING', 'jobs': [], 'log_bytes': 0,
             'source': snapshot(src / name for name in SOURCE_NAMES)}
    frozen = {}
    primary, failures = None, []
    try:
        frozen = snapshot(tool_closure() | {src / name for name in SOURCE_NAMES})
        save_json(out / 'INPUTS-INITIAL.json', frozen)
        selected = {}
        for name in ('cc1', 'as', 'collect2', 'ld'):
            response = run_job([str(GCC), '-print-prog-name=' + name], out, state, 'selected-' + name)
            text = response['stdout'].decode('utf-8', 'strict').strip()
            path = Path(text) if text.startswith('/') else Path('/usr/bin') / text
            actual = path.resolve(strict=True)
            if not any(item['resolved'] == str(actual) for item in frozen.values()):
                raise RuntimeError('actual_selected_compiler_tool_not_frozen: ' + name)
            selected[name] = actual
        state['selected_compiler_tools'] = {name: str(path) for name, path in selected.items()}
        check_unchanged(frozen)
        root_flags = ['-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-ffreestanding',
                      '-fno-builtin', '-fno-stack-protector', '-fno-asynchronous-unwind-tables']
        root = out / 'ROOT.elf'
        root_argv = [str(GCC), *root_flags, '-save-temps=obj', '-nostdlib', '-static', '-no-pie',
                     '-Wl,-e,_start,--build-id=none,-Map,' + str(out / 'ROOT.map'),
                     str(src / 'root_entry.S'), str(src / 'root_collector.c'), '-o', str(root)]
        root_deps = set()
        for name in ('root_entry.S', 'root_collector.c'):
            root_deps.update(header_dependencies(src / name, root_flags, out, state, 'M-' + name))
        check_unchanged(frozen)
        frozen = snapshot(set(frozen) | root_deps)
        save_json(out / 'INPUTS-ROOT-BEFORE.json', frozen)
        diagnostic = run_job([*root_argv[:1], '-###', *root_argv[1:]], out, state, 'ROOT-compiler-diagnostic')
        state['root_actual_compiler_invocations'] = validate_diagnostic(diagnostic, frozen, selected)
        check_unchanged(frozen)
        run_job(root_argv, out, state, 'ROOT-build')
        check_unchanged(frozen)
        state['root'] = inspect_binary(root, out, state, 'ROOT')
        state['root_link_inputs'] = link_inputs(out / 'ROOT.map', out, frozen)
        state['embedding'] = embed_root(root, out)
        root_bytes = root.read_bytes()
        bridge_flags = ['-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                        '-fno-stack-protector', '-fno-builtin', '-I' + str(INCLUDE), '-I' + str(out)]
        state['bridges'] = {}
        for variant in ('baseline', 'ordinary-faults'):
            directory = out / variant
            directory.mkdir(mode=0o700)
            flags = bridge_flags + (['-DRC_ORDINARY_FAULTS'] if variant == 'ordinary-faults' else [])
            deps = set()
            for name in ('birth_module.c', 'birth_entry.S'):
                deps.update(header_dependencies(src / name, flags, directory, state, 'M-' + name))
            check_unchanged(frozen)
            frozen = snapshot(set(frozen) | deps)
            save_json(directory / 'INPUTS-BRIDGE-BEFORE.json', frozen)
            binary = directory / '_rc_native_birth.cpython-312-x86_64-linux-gnu.so'
            argv = [str(GCC), *flags, '-save-temps=obj', str(src / 'birth_module.c'),
                    str(src / 'birth_entry.S'), '-Wl,-z,relro,-z,now,--build-id=none,-Map,' +
                    str(directory / 'BRIDGE.map'), '-o', str(binary)]
            diagnostic = run_job([argv[0], '-###', *argv[1:]], directory, state, 'BRIDGE-compiler-diagnostic')
            state[variant + '_actual_compiler_invocations'] = validate_diagnostic(diagnostic, frozen, selected)
            check_unchanged(frozen)
            run_job(argv, directory, state, 'BRIDGE-build')
            check_unchanged(frozen)
            state['bridges'][variant] = inspect_binary(binary, directory, state, 'BRIDGE', root_bytes)
            state['bridges'][variant]['actual_link_inputs'] = link_inputs(directory / 'BRIDGE.map', directory, frozen)
        state['inputs_after'] = check_unchanged(frozen)
        state['generated_artifacts'] = snapshot(p for p in out.rglob('*') if p.is_file())
        state['status'] = 'BUILD_AND_BYTE_INSPECTION_ONLY'
    except BaseException as error:
        primary = error
        state['status'] = 'FAIL'
        state['error_type'] = type(error).__name__
        state['error'] = str(error)
    finally:
        state['controls'] = 'NOTRUN'
        state['originalSUT'] = 'NOTRUN'
        state['root_execution'] = 'NOTRUN'
        state['bridge_import'] = 'NOTRUN'
        try:
            state['inputs_after_terminal_or_failure'] = snapshot(frozen)
            state['actual_input_changes'] = [name for name in frozen if
                frozen[name] != state['inputs_after_terminal_or_failure'][name]]
            if state['actual_input_changes']:
                state['status'] = 'FAIL'
                failures.append(RuntimeError('actual_build_input_changed'))
        except BaseException as identity_error:
            state['status'] = 'FAIL'
            state['after_identity_error'] = type(identity_error).__name__ + ': ' + str(identity_error)
            failures.append(identity_error)
        try:
            save_json(out / 'BUILD-RESULT.json', state)
        except BaseException as receipt_error:
            failures.append(receipt_error)
    errors = ([primary] if primary is not None else []) + failures
    if errors:
        if len(errors) == 1:
            raise errors[0]
        raise BaseExceptionGroup('build_primary_and_identity_receipt_failures', errors)
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--describe', action='store_true')
    group.add_argument('--compile', action='store_true')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    if not args.compile:
        print(json.dumps(describe(), indent=2))
        return 0
    if args.out is None:
        parser.error('--compile requires --out with an absent absolute directory')
    state = compile_candidate(Path(__file__).resolve().parent, args.out)
    print(json.dumps({'status': state['status'], 'controls': 'NOTRUN', 'out': str(args.out)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
