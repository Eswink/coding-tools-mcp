#!/usr/bin/env python3
"""Exact nine-file preservation guard for the pinned engineering AppImage build."""
from __future__ import annotations
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import selectors
import re
import signal
import stat
import subprocess
import sys
import time

import appimage_relro_contract as c
import desktop_glib_build_contract as io
from desktop_glib_link import propagate_exit
from exact_build_audit import EvidenceError

FAILURE = 'APPIMAGE_RELRO_GUARD_FAILURE:'
BOOT_HASH_BYTES = 10*c.CAPS['config']  # Three config and at most seven binding hashes; prepaid before entry.


def classify_original_argv(argv):
    """patchelf 0.8 stops at the first non-option, ignoring subsequent tokens."""
    c.need(type(argv) is list and len(argv) <= c.CAPS['argv_count'] and
           all(type(a) is str and '\0' not in a for a in argv) and
           sum(len(a.encode()) for a in argv) <= c.CAPS['argv_bytes'], 'argv_limit')
    values = {'--set-interpreter', '--interpreter', '--set-rpath', '--remove-needed'}
    queries = {'--print-interpreter', '--print-rpath'}
    flags = {'--shrink-rpath', '--force-rpath', '--debug'}
    i, mutation, query, setter, rpath = 0, False, False, False, None
    while i < len(argv):
        arg = argv[i]
        if arg in ('--help', '--version'):
            return {'operation': arg[2:], 'target': None, 'mutation': False, 'setter': False, 'rpath': None}
        if arg in values:
            if i + 1 == len(argv):
                return {'operation': 'invalid', 'target': None, 'mutation': True, 'setter': False, 'rpath': rpath}
            mutation, setter = True, setter or arg == '--set-rpath'
            if arg == '--set-rpath': rpath = argv[i+1]
            i += 2
        elif arg in queries:
            query = True
            i += 1
        elif arg in flags:
            mutation = mutation or arg == '--shrink-rpath'
            i += 1
        else:
            return {'operation': 'set-rpath' if setter else 'mutation' if mutation else 'query' if query else 'read',
                    'target': arg, 'mutation': mutation, 'setter': setter, 'rpath': rpath}
    return {'operation': 'invalid', 'target': None, 'mutation': mutation, 'setter': setter, 'rpath': rpath}


def bounded_child(executable_fd, args, *, cwd=None, env=None, timeout=30,
                  stdout_limit=1024**2, stderr_limit=1024**2, limits=False, forward=False, extra_fds=(), stdout_fd=None):
    """Capture both streams concurrently, terminating only our child on failure."""
    def constrain():
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
        resource.setrlimit(resource.RLIMIT_AS, (256 * 1024**2,) * 2)
        resource.setrlimit(resource.RLIMIT_FSIZE, (max(stdout_limit, stderr_limit),) * 2)
    child, streams = None, [bytearray(), bytearray()]
    deadline = time.monotonic() + timeout
    try:
        child = subprocess.Popen(args, executable=f'/proc/self/fd/{executable_fd}', pass_fds=(executable_fd, *extra_fds),
            cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            preexec_fn=constrain if limits else None)
        with selectors.DefaultSelector() as selected:
            for index, stream in enumerate((child.stdout, child.stderr)):
                os.set_blocking(stream.fileno(), False)
                selected.register(stream, selectors.EVENT_READ, index)
            while selected.get_map():
                c.need(time.monotonic() < deadline, 'child_timeout')
                for key, _ in selected.select(min(.1, max(0, deadline-time.monotonic()))):
                    block = os.read(key.fileobj.fileno(), 65536)
                    if not block:
                        selected.unregister(key.fileobj)
                        continue
                    index = key.data
                    c.need(len(streams[index]) + len(block) <= (stdout_limit, stderr_limit)[index], 'child_stream_limit')
                    streams[index].extend(block)
                    if index == 0 and stdout_fd is not None:
                        c.need(os.write(stdout_fd, block) == len(block), 'short_parser_write')
                    if forward:
                        output = (sys.stdout.buffer, sys.stderr.buffer)[index]
                        output.write(block)
                        output.flush()
            code = child.wait(timeout=max(.001, deadline-time.monotonic()))
        return code, bytes(streams[0]), bytes(streams[1])
    except subprocess.TimeoutExpired as exc:
        raise EvidenceError('child_timeout') from exc
    finally:
        if child is not None:
            if child.poll() is None:
                child.kill()
            child.wait()
            for stream in (child.stdout, child.stderr):
                if stream: stream.close()


def encoded(value, limit):
    data = (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False) + '\n').encode()
    c.need(len(data) <= limit, 'receipt_limit')
    return data


def owned_fd(path, flags, mode=0o600):
    with io.parent_descriptor(path) as (parent, name):
        fd = os.open(name, flags | os.O_NOFOLLOW | os.O_NONBLOCK, mode, dir_fd=parent)
        try:
            info = os.fstat(fd)
            c.need(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid() and info.st_nlink == 1
                   and stat.S_IMODE(info.st_mode) == mode, 'unsafe_state_file')
            named = os.stat(name, dir_fd=parent, follow_symlinks=False)
            c.need(io.file_identity(info) == io.file_identity(named), 'state_name_changed')
            return fd
        except BaseException:
            os.close(fd)
            raise


def write_all(fd, data):
    # A short write is evidence failure, never silently accepted as complete.
    c.need(os.write(fd, data) == len(data), 'short_receipt_write')
    os.fsync(fd)


def append_event(root, value):
    data = encoded(value, c.CAPS['event'])
    fd = owned_fd(root / 'operations.jsonl', os.O_WRONLY | os.O_APPEND)
    try:
        c.need(os.fstat(fd).st_size + len(data) <= c.CAPS['journal'], 'journal_limit')
        write_all(fd, data)
    finally:
        os.close(fd)


def replace_state(root, state):
    data = encoded(state, c.CAPS['state'])
    temporary = root / ('state.' + str(os.getpid()) + '.tmp')
    fd = owned_fd(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    try:
        write_all(fd, data)
        old = owned_fd(root / 'state.json', os.O_RDONLY)
        os.close(old)
        with io.parent_descriptor(temporary) as (parent, name):
            os.replace(name, 'state.json', src_dir_fd=parent, dst_dir_fd=parent)
            os.fsync(parent)
    finally:
        os.close(fd)


def latch_failure(root, sequence, code, state=None):
    value = {'schema': 'appimage-relro-failure-v1', 'sequence': sequence, 'error': code[:96]}
    try:
        fd = owned_fd(root / 'failed.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError:
        c.observe(root / 'failed.json', mode=0o600, limit=c.CAPS['failure'])
    else:
        try: write_all(fd, encoded(value, c.CAPS['failure']))
        finally: os.close(fd)
    if state is not None:
        state['phase'] = 'failed'
        replace_state(root, state)


def session_state(root, config_hash):
    raw, _ = c.observe(root / 'state.json', mode=0o600, limit=c.CAPS['state'], hash_data=False)
    state = io.decode(raw)
    c.need(set(state) == {'schema', 'config_sha256', 'phase', 'next_sequence', 'completed_calls',
                         'total_hashed_bytes', 'journal_bytes'}, 'invalid_state_keys')
    c.need(state['schema'] == 'appimage-relro-state-v1' and state['config_sha256'] == config_hash
           and state['phase'] in ('prepared', 'active'), 'invalid_state_phase')
    for key in ('next_sequence', 'completed_calls', 'total_hashed_bytes', 'journal_bytes'):
        c.need(type(state[key]) is int and state[key] >= 0, 'invalid_state_counter')
    raw, _ = c.observe(root / 'operations.jsonl', mode=0o600, limit=c.CAPS['journal'], hash_data=False)
    c.need(len(raw) == state['journal_bytes'] and (not raw or raw.endswith(b'\n')), 'journal_state_mismatch')
    rows = [io.decode(line, c.CAPS['event']) for line in raw.splitlines()]
    c.need(len(rows) == state['completed_calls'] * 2 and state['next_sequence'] == state['completed_calls']+1,
           'pending_or_missing_operation')
    for i, row in enumerate(rows):
        c.need(row.get('sequence') == i//2+1 and row.get('event') == ('begin', 'end')[i%2]
               and row.get('config_sha256') == config_hash, 'reordered_operation')
        if i % 2:
            c.need(row.get('exit') == 0 and row.get('error') is None, 'prior_operation_failed')
    duration = sum(rows[i+1]['monotonic_ns']-rows[i]['monotonic_ns'] for i in range(0, len(rows), 2))
    c.need(0 <= duration < c.CAPS['duration']*10**9 and state['completed_calls'] < c.CAPS['calls']
           and state['total_hashed_bytes'] < c.CAPS['hashed'], 'session_limit')
    return state, duration


def original_descriptor(config):
    path = Path(config['original_patchelf_path'])
    fd = owned_fd(path, os.O_RDONLY, 0o500)
    try:
        data, record = c.observe(path, mode=0o500, limit=c.TOOL_SIZE)
        c.need(record['size'] == c.TOOL_SIZE and record['sha256'] == c.TOOL_SHA256 and
               (os.fstat(fd).st_dev, os.fstat(fd).st_ino) == (record['device'], record['inode']), 'original_tool_changed')
        return fd, record
    except BaseException:
        os.close(fd)
        raise


def delegate_original(config, argv, target_record):
    fd, tool = original_descriptor(config)
    try:
        result = bounded_child(fd, [config['original_patchelf_path'], *argv], forward=True)
        _, after = c.observe(config['original_patchelf_path'], mode=0o500, limit=c.TOOL_SIZE)
        c.need(tool == after and io.file_identity(os.fstat(fd)) ==
               (after['device'], after['inode'], after['size'], after['mtime_ns'], after['ctime_ns'], after['nlink']),
               'original_tool_changed')
        return result
    finally:
        os.close(fd)


def query_observation(config, path, charge):
    original, pending, aliases, snapshots = path, Path(path).parts[1:], [], []
    current = Path('/')
    while pending:
        component, *pending = pending
        current = current/component
        info = current.lstat()
        if stat.S_ISLNK(info.st_mode):
            c.need(len(aliases) < 8, 'query_alias_limit')
            target = os.readlink(current)
            c.need(target and len(target.encode()) <= c.CAPS['path'] and '\\' not in target and
                   all(ord(ch) >= 32 and ord(ch) != 127 for ch in target), 'invalid_query_alias')
            aliases.append(dict(path=str(current), target=target, device=info.st_dev, inode=info.st_ino,
                                mtime_ns=info.st_mtime_ns, ctime_ns=info.st_ctime_ns))
            snapshots.append((current, io.file_identity(info), target))
            resolved = Path(os.path.abspath(current.parent/target))
            pending = [*resolved.parts[1:], *pending]
            current = Path('/')
    resolved = c.canonical(str(current))
    relative = str(current.relative_to(config['appdir_root'])) if current.is_relative_to(config['appdir_root']) else None
    record = target_record(config, resolved, relative, charge, owned=False)
    for alias, identity, target in snapshots:
        c.need(io.file_identity(alias.lstat()) == identity and os.readlink(alias) == target, 'query_alias_changed')
    return {**record, 'target': original, **({'resolved': resolved, 'aliases': aliases} if aliases else {})}


def target_record(config, path, relative, charge, owned=True):
    if relative in c.PROTECTED:
        size = c.read_binding(config)['prebundle']['size'] if relative == c.MAIN else c.PROTECTED[relative]['size']
        charge(size*(8 if relative == c.MAIN else 2))
        return c.protected_record(config, path)
    size = os.stat(path, follow_symlinks=False).st_size
    c.need(0 <= size <= c.CAPS['elf'], 'target_size_limit')
    charge(size)
    return c.observe(path, owned=owned, limit=size)[1]


def target_observation(config, parsed, charge=lambda amount: None):
    target = parsed['target']
    if target is None:
        return None, None, None
    absolute = c.canonical(target if os.path.isabs(target) else str(Path.cwd() / target))
    root = Path(config['appdir_root'])
    relative = str(Path(absolute).relative_to(root)) if Path(absolute).is_relative_to(root) else None
    protected = relative in c.PROTECTED
    if protected:
        c.need(not os.path.lexists(absolute+'_patchelf_tmp'), 'existing_patchelf_tmp')
        c.need(target == absolute, 'protected_noncanonical_operand')
        return absolute, relative, target_record(config, absolute, relative, charge)
    c.need(not (relative is not None or parsed['mutation']) or not any(Path(absolute).name.startswith('lib'+family+'-2.0.so')
                   for family in ('glib', 'gio', 'gobject', 'gmodule')), 'extra_protected_family')
    if parsed['mutation']:
        c.need(relative is not None and relative != '.', 'mutation_outside_appdir')
    try:
        record = target_record(config, absolute, relative, charge) if parsed['mutation'] else query_observation(config, absolute, charge)
    except FileNotFoundError:
        if parsed['mutation']: raise
        record = None
    if parsed['mutation']:
        c.need(not os.path.lexists(absolute+'_patchelf_tmp'), 'existing_patchelf_tmp')
        for name in c.PROTECTED:
            path = root / name
            if os.path.lexists(path):
                info = os.stat(path, follow_symlinks=False)
                c.need((info.st_dev, info.st_ino) != (record['device'], record['inode']), 'protected_inode_alias')
    return absolute, relative or absolute, record


def finish_call(root, begin, state, after, code, stdout, stderr, error, duration):
    end = {'schema': 'appimage-relro-operation-v1', 'event': 'end', 'sequence': begin['sequence'],
        'config_sha256': begin['config_sha256'], 'result': 'rejected' if error else
        'preserved' if begin['decision'] == 'preserve' else 'delegated',
        'after': after, 'stdout': None if stdout is None else {'size': len(stdout), 'sha256': hashlib.sha256(stdout).hexdigest()},
        'stderr': None if stderr is None else {'size': len(stderr), 'sha256': hashlib.sha256(stderr).hexdigest()}, 'error': error, 'monotonic_ns': time.monotonic_ns()}
    end['exit' if code >= 0 else 'signal'] = code if code >= 0 else -code
    c.need(duration + end['monotonic_ns']-begin['monotonic_ns'] <= c.CAPS['duration']*10**9, 'session_duration_limit')
    append_event(root, end)
    state.update(next_sequence=begin['sequence']+1, completed_calls=begin['sequence'],
                 journal_bytes=(root/'operations.jsonl').stat().st_size,
                 phase='failed' if error else 'active')
    replace_state(root, state)


def guard_call(config, argv, verify_entry=False):
    root = Path(config['compiler_binding_path']).parent
    with io.parent_descriptor(root/'lock') as (parent, _):
        info = os.fstat(parent)
        c.need(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700, 'unsafe_session_directory')
    config_raw, _ = c.observe(root/'config.json', mode=0o400, limit=c.CAPS['config'], hash_data=False)
    c.need(io.decode(config_raw) == config, 'config_object_mismatch')
    lock = owned_fd(root/'lock', os.O_RDONLY)
    state, begin, sequence, begin_written, authenticated = None, None, 0, False, not verify_entry
    try:
        deadline = time.monotonic()+c.CAPS['lock']
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                c.need(time.monotonic() < deadline, 'lock_timeout')
                time.sleep(.02)
        config_hash = hashlib.sha256(config_raw).hexdigest()
        c.need(not verify_entry or config_hash == os.environ.get('APPIMAGE_RELRO_CONFIG_SHA256'), 'changed_relro_config')
        authenticated = True
        c.need(io.file_identity(os.fstat(lock)) == io.file_identity(os.stat(root/'lock', follow_symlinks=False)), 'lock_replaced')
        c.need(not os.path.lexists(root/'failed.json'), 'sticky_failure')
        state, duration = session_state(root, config_hash)
        def charge(amount):
            c.need(state['total_hashed_bytes'] + amount <= c.CAPS['hashed'], 'hash_budget_exhausted')
            state['total_hashed_bytes'] += amount
            replace_state(root, state)
        c.need(state['total_hashed_bytes'] >= BOOT_HASH_BYTES, 'missing_startup_reserve')
        charge(BOOT_HASH_BYTES + 2*c.CAPS['stream'])
        if verify_entry:
            for key, mode in (('python', None), ('guard', 0o755)):
                path = config[key+'_path']; size = os.stat(path).st_size
                c.need(0 <= size <= c.CAPS['elf'], 'entry_size_limit')
                charge(size)
                c.need(c.observe(path, owned=key == 'guard', mode=mode, limit=size)[1]['sha256'] == config[key+'_sha256'], 'entry_identity_changed')
        sequence = state['next_sequence']
        c.read_binding(config)
        binding, _ = c.observe(config['compiler_binding_path'], mode=0o600, limit=c.CAPS['binding'])
        parsed = classify_original_argv(argv)
        begin = {'schema': 'appimage-relro-operation-v1', 'event': 'begin', 'sequence': sequence,
            'config_sha256': config_hash, 'compiler_binding_sha256': hashlib.sha256(binding).hexdigest(),
            'pid': os.getpid(), 'start_time': Path('/proc/self/stat').read_text().rsplit(')', 1)[1].split()[19],
            'argv': argv, 'cwd': str(Path.cwd()), 'operation': parsed['operation'], 'target': parsed['target'],
            'decision': 'reject', 'before': None, 'original_tool': None, 'monotonic_ns': time.monotonic_ns()}
        operand = parsed['target']
        path = str(Path.cwd()/operand) if operand and not os.path.isabs(operand) else operand
        mutable = path not in {config['appdir_root']+'/'+name for name in c.PROTECTED}
        parents = c.owned_appdir_parents(config, path, mutation=mutable) if parsed['mutation'] and path else contextlib.nullcontext()
        with parents:
            absolute, relative, before = target_observation(config, parsed, charge)
            begin.update(target=relative, before=before)
            protected = relative in c.PROTECTED
            if protected and parsed['mutation']:
                c.need(argv == ['--set-rpath', c.PROTECTED[relative]['rpath'], absolute], 'unsupported_protected_mutation')
                decision = 'preserve'
            else:
                decision = 'delegate'
                charge(3*c.TOOL_SIZE)
                tool_fd, tool_record = original_descriptor(config)
                os.close(tool_fd)
                begin['original_tool'] = tool_record
            begin['decision'] = decision
            append_event(root, begin)
            begin_written = True
            if decision == 'preserve':
                after, code, out, err = target_record(config, absolute, relative, charge), 0, None, None
                c.need(before == after, 'protected_changed')
            else:
                code, out, err = delegate_original(config, argv, before)
                after = None if absolute is None or before is None and code else target_record(config, absolute, relative, charge) if protected or parsed['mutation'] else query_observation(config, absolute, charge)
                if not parsed['mutation']:
                    c.need(after == before, 'query_changed_input')
                elif absolute:
                    c.need(not os.path.lexists(absolute+'_patchelf_tmp'), 'leftover_patchelf_tmp')
        error = 'original_nonzero' if code else None
        if error: latch_failure(root, sequence, error, state)
        finish_call(root, begin, state, after, code, out, err, error, duration)
        return code
    except BaseException as exc:
        code = str(exc) if isinstance(exc, EvidenceError) else 'guard_exception'
        code = code[:96] if code and all(ch.isalnum() or ch in '_:-' for ch in code) else 'guard_exception'
        try:
            if authenticated: latch_failure(root, sequence, code, state)
            if begin is not None:
                if not begin_written: append_event(root, begin)
                finish_call(root, begin, state, None, 125, None, None, code, duration)
        except BaseException: pass
        print(FAILURE+code, file=sys.stderr)
        return 125
    finally:
        os.close(lock)


def seal_session(config):
    root = Path(config['compiler_binding_path']).parent
    lock = owned_fd(root/'lock', os.O_RDONLY)
    try:
        deadline = time.monotonic()+c.CAPS['lock']
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                c.need(time.monotonic() < deadline, 'lock_timeout')
                time.sleep(.02)
        c.need(not os.path.lexists(root/'failed.json'), 'sticky_failure')
        config_hash = c.observe(root/'config.json', mode=0o400)[1]['sha256']
        state, _ = session_state(root, config_hash)
        state['phase'] = 'sealed'
        replace_state(root, state)
        return state
    finally:
        os.close(lock)


def main(argv=None):
    def interrupted(signum, frame):
        raise EvidenceError('guard_interrupted')
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP): signal.signal(sig, interrupted)
    try:
        c.need(re.fullmatch('[0-9a-f]{64}', os.environ.get('APPIMAGE_RELRO_CONFIG_SHA256', '')), 'missing_config_hash')
        c.need(not os.path.lexists(Path(os.environ.get('APPIMAGE_RELRO_CONFIG', '')).parent/'failed.json'), 'sticky_failure')
        config = c.read_config(os.environ.get('APPIMAGE_RELRO_CONFIG', ''), defer_hash=True)
        c.need(str(Path(sys.executable).resolve()) == config['python_path'] and
               sys.version.split()[0] == config['python_version'].removeprefix('Python ') and
               str(Path(__file__).resolve()) == config['guard_path'], 'guard_entry_changed')
        code = guard_call(config, list(sys.argv[1:] if argv is None else argv), verify_entry=True)
    except BaseException as exc:
        print(FAILURE+'entry_verification_failed', file=sys.stderr)
        code = 125
    propagate_exit(code)


if __name__ == '__main__':
    main()
