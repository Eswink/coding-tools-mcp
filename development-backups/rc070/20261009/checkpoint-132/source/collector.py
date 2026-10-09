"""Source-only bounded ordinary dual-stream capture; no native-family authority.

Root must independently seal the exact compiler/runtime/config/source closure
and review a fresh startup before using this module. No commands run at import.
A successful ordinary child capture is never a publisher/install/VM grant.
"""
import hashlib
import math
import os
from pathlib import Path
import selectors
import signal
import stat
import subprocess
import time

MAX_BYTES = 2 * 1024 * 1024
MAX_SECONDS = 480.0
TERM_SECONDS = 2.0
KILL_SECONDS = 2.0
_ATTEMPTS = []  # UNKNOWN records retain actual resources and exception objects.


class LogLimitExceeded(RuntimeError):
    pass


class WholeDeadlineExceeded(TimeoutError):
    pass


def _resource(record, name, close):
    item = {'name': name, 'object': None, 'attempted': False,
            'close_attempted': False, 'state': 'PREALLOCATED', 'close': close,
            'errors': []}
    record['resources'].append(item)  # before any effectful creator
    return item


def _create_resource(item, creator):
    item['attempted'] = True
    try:
        item['object'] = creator()
        item['state'] = 'OWNED'
        return item['object']
    except BaseException as error:
        item['state'] = 'UNKNOWN'
        item['errors'].append(error)
        raise


def close_resources(record):
    """Attempt every independent actual close; never retry unknown closes."""
    errors = []
    for item in reversed(record['resources']):
        if item['close_attempted']:
            continue
        if item['object'] is None:
            if not item['attempted']:
                item['state'] = 'NOT_CREATED'
            # A creator that raised after an effect has no reconstructed return.
            continue
        item['close_attempted'] = True
        try:
            item['close'](item['object'])
            item['state'] = 'CLOSED'
            item['object'] = None  # only after actual successful close
        except BaseException as error:
            item['state'] = 'UNKNOWN'
            item['errors'].append(error)
            errors.append(error)
    return errors


def _bind_pipe(item, process, name):
    item['attempted'] = True
    try:
        item['object'] = getattr(process, name)
        if item['object'] is None:
            raise RuntimeError('true_created_PIPE_return_missing')
        item['state'] = 'OWNED_TRUE_RETURN'
    except BaseException as error:
        item['state'] = 'UNKNOWN'
        item['errors'].append(error)
        raise


def capture_pending_pipes(record):
    """Recover only actual pipe objects still held by the true Popen return.

    This is a repeated observation, never a retry of an ambiguous close and
    never reconstruction from integer FDs. A failing item cannot skip the other.
    """
    errors = []
    process = record['child']['object']
    if process is None:
        return errors
    for name, item in record.get('pipes', {}).items():
        if item['object'] is None and not item['close_attempted']:
            try:
                _bind_pipe(item, process, name)
            except BaseException as error:
                errors.append(error)
    return errors


def _remaining(deadline, maximum):
    value = deadline - time.monotonic()
    if value <= 0:
        raise WholeDeadlineExceeded('whole_deadline_exhausted_during_owned_cleanup')
    return min(maximum, value)


def retire_owned_child(record, deadline):
    """Independent wait even after poll/signal cancellation; ordinary child only.

    Signals use only the live unreaped true Popen return, not external PID input.
    No post-reap integer group signal and no native descendant closure claim.
    """
    child = record['child']
    process = child['object']
    if process is None:
        return []
    errors, alive = [], None
    try:
        alive = process.poll() is None
    except BaseException as error:
        errors.append(error)
    if alive is True:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            record['term_attempted'] = True
        except ProcessLookupError:
            record['term_attempted'] = True
        except BaseException as error:
            errors.append(error)
    elif alive is False:
        record['created_group_descendants'] = 'UNKNOWN_NO_POST_REAP_INTEGER_SIGNAL'
    # Poll/signal exceptions must not skip the independent true-child wait.
    timed_out, first_wait_failed = False, False
    try:
        process.wait(timeout=_remaining(deadline, TERM_SECONDS))
    except subprocess.TimeoutExpired:
        timed_out = True  # actual wait timeout leaves the original unreaped
    except BaseException as error:
        first_wait_failed = True
        errors.append(error)
    if timed_out or first_wait_failed:
        can_signal = timed_out
        if not can_signal:
            try:
                can_signal = process.poll() is None
            except BaseException as error:
                errors.append(error)
        if can_signal:
            try:
                os.killpg(process.pid, signal.SIGKILL)
                record['kill_attempted'] = True
            except ProcessLookupError:
                record['kill_attempted'] = True
            except BaseException as error:
                errors.append(error)
        # This second wait is independent of the second poll/signal outcome.
        try:
            process.wait(timeout=_remaining(deadline, KILL_SECONDS))
        except BaseException as error:
            errors.append(error)
    try:
        code = process.poll()
        record['observed_returncode'] = code
        if code is None:
            raise RuntimeError('actual_created_child_retirement_UNKNOWN')
        child['state'] = 'UNKNOWN' if errors else 'REAPED_ORDINARY_CHILD_ONLY'
    except BaseException as error:
        errors.append(error)
        child['state'] = 'UNKNOWN'
    child['errors'].extend(errors)
    return errors


def _write_all(fd, data, digest, record, name):
    offset = 0
    while offset < len(data):
        count = os.write(fd, memoryview(data)[offset:])
        if type(count) is not int or not 0 < count <= len(data) - offset:
            raise RuntimeError('raw_writer_invalid_or_zero_write')
        digest.update(data[offset:offset + count])
        record['streams'][name]['bytes_written'] += count
        offset += count


def _validate_inputs(argv, cwd, env, executable_sha256, seconds, byte_limit):
    if type(argv) not in (tuple, list) or not argv or any(type(x) is not str or '\x00' in x for x in argv):
        raise ValueError('exact_nonempty_string_argv_required')
    executable = Path(argv[0])
    if not executable.is_absolute() or executable.resolve(strict=True) != executable:
        raise ValueError('literal_canonical_absolute_executable_required_no_PATH_lookup')
    if type(executable_sha256) is not str or len(executable_sha256) != 64:
        raise ValueError('root_sealed_executable_sha256_required')
    cwd = Path(cwd)
    if not cwd.is_absolute() or cwd.resolve(strict=True) != cwd or not cwd.is_dir():
        raise ValueError('literal_canonical_absolute_cwd_required')
    if type(env) is not dict or any(type(k) is not str or type(v) is not str or not k or '=' in k or '\x00' in k + v for k, v in env.items()):
        raise ValueError('exact_replaced_string_environment_required')
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 4 < seconds <= MAX_SECONDS:
        raise ValueError('whole_budget_gt4_and_at_most480_required')
    if type(byte_limit) is not int or not 0 < byte_limit <= MAX_BYTES:
        raise ValueError('combined_byte_cap_at_most2MiB_required')
    return tuple(argv), str(cwd), dict(env)


def _seal_executable(record, path, expected):
    item = _resource(record, 'sealed_executable_read', os.close)
    fd = _create_resource(item, lambda: os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC))
    before = os.fstat(fd)
    if not stat.S_ISREG(before.st_mode) or not before.st_mode & 0o111 or before.st_size > 256 * 1024 * 1024:
        raise ValueError('bounded_actual_executable_required')
    digest, total = hashlib.sha256(), 0
    while data := os.read(fd, 65536):
        total += len(data)
        if total > 256 * 1024 * 1024:
            raise RuntimeError('executable_read_bound')
        digest.update(data)
    after = os.fstat(fd)
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise RuntimeError('executable_changed_during_actual_read')
    if total != before.st_size or digest.hexdigest() != expected:
        raise RuntimeError('root_sealed_executable_bytes_changed')


def collect_build_streams(argv, cwd, env, executable_sha256, output_dir,
                          before_fence, after_fence, *, seconds=MAX_SECONDS,
                          byte_limit=MAX_BYTES):
    """One ordinary capture, root-only future compiler call after startup review.

    Return is ordinary capture only. Caller receipt writing and its post-writer
    clock must still fit the same deadline; success here is not final build
    qualification. Unknown/cancel paths retain objects in _ATTEMPTS.
    """
    start = time.monotonic()
    if len(_ATTEMPTS) >= 256:
        raise RuntimeError('retained_attempt_bound')
    record = {'start': start, 'resources': [], 'child': {'object': None,
              'state': 'PREALLOCATED', 'attempted': False, 'errors': []},
              'streams': {n: {'bytes_written': 0, 'eof': False} for n in ('stdout', 'stderr')},
              'errors': [], 'partial': True, 'ordinary_capture_pass': False,
              'qualifies_native_family': False, 'receipt_requires_same_deadline': True,
              'term_attempted': False, 'kill_attempted': False}
    _ATTEMPTS.append(record)
    primary, failures = None, []
    deadline = start + (float(seconds) if type(seconds) in (int, float) and math.isfinite(seconds) else 0)
    record['deadline'] = deadline
    selector = None
    process = None
    try:
        argv, cwd, env = _validate_inputs(argv, cwd, env, executable_sha256, seconds, byte_limit)
        if not callable(before_fence) or not callable(after_fence):
            raise TypeError('mandatory_source_runtime_before_after_fences_required')
        _seal_executable(record, argv[0], executable_sha256)
        before_fence()
        if time.monotonic() >= deadline - TERM_SECONDS - KILL_SECONDS:
            raise WholeDeadlineExceeded('before_fence_consumed_running_budget')
        out = Path(output_dir)
        if not out.is_absolute() or out.resolve(strict=True) != out:
            raise ValueError('literal_canonical_precreated_output_directory_required')
        directory = _resource(record, 'output_directory', os.close)
        dirfd = _create_resource(directory, lambda: os.open(out, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC))
        pinned = os.fstat(dirfd)
        if pinned.st_uid != os.getuid() or stat.S_IMODE(pinned.st_mode) != 0o700 or os.listdir(dirfd):
            raise RuntimeError('precreated_empty_owned0700_directory_required')
        record['output_directory_identity'] = (pinned.st_dev, pinned.st_ino)
        logs, digests = {}, {}
        for name in ('stdout', 'stderr'):
            item = _resource(record, 'raw_' + name, os.close)
            logs[name] = _create_resource(item, lambda name=name: os.open(name + '.raw', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=dirfd))
            actual = os.fstat(logs[name])
            if not stat.S_ISREG(actual.st_mode) or stat.S_IMODE(actual.st_mode) != 0o600 or actual.st_nlink != 1:
                raise RuntimeError('exclusive_raw_regular0600_required')
            digests[name] = hashlib.sha256()
        reader = _resource(record, 'selector', lambda x: x.close())
        selector = _create_resource(reader, selectors.DefaultSelector)
        # Both holders are linked BEFORE Popen. Allocation failure is 0creator.
        record['pipes'] = {}
        for name in ('stdout', 'stderr'):
            record['pipes'][name] = _resource(record, name + '_pipe', lambda x: x.close())
        child = record['child']
        child['attempted'] = True
        try:
            child['object'] = subprocess.Popen(argv, cwd=cwd, env=env,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                start_new_session=True, close_fds=True)
            child['state'] = 'OWNED_TRUE_RETURN'
        except BaseException as error:
            child['state'] = 'UNKNOWN'
            child['errors'].append(error)
            raise
        process = child['object']
        pipes = record['pipes']
        for name, item in pipes.items():
            _bind_pipe(item, process, name)
        for name, item in pipes.items():
            os.set_blocking(item['object'].fileno(), False)
            selector.register(item['object'], selectors.EVENT_READ, name)
        total = 0
        run_deadline = deadline - TERM_SECONDS - KILL_SECONDS
        while selector.get_map():
            remaining = run_deadline - time.monotonic()
            if remaining <= 0:
                raise WholeDeadlineExceeded('running_budget_exhausted_cleanup_reserved')
            for key, _ in selector.select(min(0.05, remaining)):
                capacity = byte_limit - total
                data = os.read(key.fileobj.fileno(), min(65536, capacity + 1))
                if not data:
                    selector.unregister(key.fileobj)
                    record['streams'][key.data]['eof'] = True
                    continue
                retained = data[:capacity]
                total += len(retained)
                _write_all(logs[key.data], retained, digests[key.data], record, key.data)
                if len(data) > capacity:
                    record['log_overflow'] = True
                    record['observed_overflow_bytes'] = len(data) - capacity
                    record['unobserved_remaining_output'] = 'UNKNOWN_PARTIAL'
                    raise LogLimitExceeded('aggregate_raw_log_limit_partial_prefix_FAIL')
        remaining = run_deadline - time.monotonic()
        if remaining <= 0:
            raise WholeDeadlineExceeded('no_remaining_running_budget_for_wait')
        code = process.wait(timeout=remaining)
        record['observed_returncode'] = code
        record['child']['state'] = 'REAPED_ORDINARY_CHILD_ONLY'
        record['partial'] = False
        for name, fd in logs.items():
            current = os.fstat(fd)
            if current.st_size != record['streams'][name]['bytes_written'] or current.st_nlink != 1:
                raise RuntimeError('actual_raw_writer_byte_identity_mismatch')
            record['streams'][name]['sha256'] = digests[name].hexdigest()
        current_directory = os.stat(out, follow_symlinks=False)
        if (current_directory.st_dev, current_directory.st_ino) != record['output_directory_identity']:
            raise RuntimeError('output_directory_path_identity_changed')
        if code != 0:
            raise subprocess.CalledProcessError(code, argv)
    except BaseException as error:
        primary = error
        record['errors'].append(error)
    finally:
        # Independent cleanup, all closes, after fence and clock attempts.
        if primary is not None:
            try:
                failures.extend(retire_owned_child(record, deadline))
            except BaseException as error:
                failures.append(error)
        try:
            failures.extend(capture_pending_pipes(record))
        except BaseException as error:
            failures.append(error)
        try:
            failures.extend(close_resources(record))
        except BaseException as error:
            failures.append(error)
        try:
            if not callable(after_fence):
                raise TypeError('mandatory_after_fence_not_callable')
            after_fence()
            record['after_fence_pass'] = True
        except BaseException as error:
            failures.append(error)
        try:
            record['elapsed_seconds'] = time.monotonic() - start
            if time.monotonic() >= deadline:
                raise WholeDeadlineExceeded('whole_deadline_exhausted_after_cleanup_fences')
        except BaseException as error:
            failures.append(error)
        record['errors'].extend(failures)
    unknown = any(x['state'] == 'UNKNOWN' for x in record['resources']) or record['child']['state'] == 'UNKNOWN'
    if unknown and primary is None and not failures:
        failures.append(RuntimeError('retained_UNKNOWN_resource_cannot_pass'))
        record['errors'].extend(failures)
    errors = ([primary] if primary is not None else []) + failures
    if errors:
        if len(errors) == 1:
            raise errors[0]
        raise BaseExceptionGroup('ordinary_capture_primary_and_independent_cleanup_failures', errors)
    record['ordinary_capture_pass'] = True
    return record
