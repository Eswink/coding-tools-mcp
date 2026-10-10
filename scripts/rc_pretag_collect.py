"""One live-only, nonpublishing pretag collection. No receipt or output-path CLI."""
import hashlib
import os
from pathlib import Path
import stat
import sys

# The isolated CLI imports only this exact checkout's sibling modules.
sys.path.insert(0, str(Path(__file__).absolute().parent))
import rc_artifact_consumer as consumer
import rc_consumer_io as private_io
from rc_consumer_io import need
import rc_consumer_snapshot as snapshot
import rc_pretag_admission as admission
import rc_pretag_collection_result as result

ROOT = Path(__file__).absolute().parents[1]


def _temporary(root, environment):
    value = environment.get('RUNNER_TEMP')
    need(type(value) is str and value.startswith('/') and value == os.path.normpath(value)
         and not any(ord(c) < 32 for c in value) and len(value.encode('utf-8')) <= result.PATH_LIMIT
         and os.path.commonpath((str(root.absolute()), value)) != str(root.absolute()), 'pretag_output_failed')
    fd = private_io._directory(value)
    try:
        need(os.fstat(fd).st_uid == os.geteuid() and os.path.realpath(value) == value, 'pretag_output_failed')
    finally:
        os.close(fd)
    return value


def _byte_stage(error):
    files, trace = set(), error.__traceback__
    while trace is not None:
        files.add(trace.tb_frame.f_code.co_filename)
        trace = trace.tb_next
    if consumer.contracts.__file__ in files: return 'contracts'
    if consumer.archive.__file__ in files: return 'archive'
    if snapshot.__file__ in files: return 'artifact'
    return 'transport'


def collect(root, environment, api, *, opener=None):
    """Only this live path constructs an in-process result; no imported authority."""
    roots, failure, stage = [], None, 'invocation'
    try:
        admitted = admission.admit(root, environment, api)
        stage = 'selection'
        expectations = admission.discover(api, admitted)
        selection = snapshot._select_source_runs_for_identity(api, admitted.source.source_sha,
                                                              admitted.source.repository_id, expectations)
        admission.branch(api, 'refs/heads/' + selection['final_packaging']['run']['head_branch'],
                         admitted.source.source_sha)
        stage = 'artifact'
        metadata = snapshot.authenticate_bundle_metadata(api, selection, expectations['artifact_id'])
        producer = snapshot.derive_final_producer(admission.projection(admitted), selection, metadata)
        stage = 'output'
        parent = _temporary(root, environment)
        for prefix in ('rc-pretag-download-', 'rc-pretag-bundle-', 'rc-pretag-cloud-'):
            roots.append(private_io.PrivateRoot(parent, prefix, source_root=root))
        stage = 'transport'
        try:
            content = consumer._verify_bundle_bytes(root, api, selection, metadata, producer, *roots, opener=opener)
        except BaseException as error:
            stage = _byte_stage(error)
            raise
        stage = 'output'
        prepared = result._summarize(admitted, selection, producer, content)
    except BaseException as error:
        failure = result.Failure(stage, error)
    finally:
        # Close once, without retry, retaining stronger transport uncertainty.
        for owned in reversed(roots):
            try:
                owned.close()
            except BaseException as error:
                if failure is None: failure = result.Failure('output', error)
                else: failure.record('output', error)
    if failure is not None:
        raise failure from None
    try:
        admission.revalidate(api, root, environment, admitted, expectations, selection, metadata, producer)
    except BaseException as error:
        raise result.Failure('freshness', error) from None
    try:
        return result._collect(prepared)
    except BaseException as error:
        raise result.Failure('output', error) from None


def _handoff(path, parent, environment):
    value = str(path)
    need(path.name == result.NAME and path.is_absolute() and os.path.commonpath((parent, value)) == parent
         and not any(ord(c) < 32 for c in value) and len(value.encode('utf-8')) <= result.PATH_LIMIT,
         'pretag_output_handoff_failed')
    control = environment.get('GITHUB_OUTPUT')
    need(type(control) is str and control.startswith('/') and control == os.path.normpath(control)
         and len(control.encode('utf-8')) <= result.PATH_LIMIT and not any(ord(c) < 32 for c in control)
         and os.path.commonpath((parent, control)) == parent and control != value,
         'pretag_output_handoff_failed')
    line = ('receipt_path=' + value + '\n').encode('utf-8')
    need(len(line) <= result.PATH_LIMIT, 'pretag_output_handoff_failed')
    parent_fd, fd = private_io._directory(parent), None
    try:
        parts = Path(control).relative_to(parent).parts
        need(bool(parts), 'pretag_output_handoff_failed')
        for part in parts[:-1]:
            child = os.open(part, private_io.DIR_FLAGS, dir_fd=parent_fd)
            previous, parent_fd = parent_fd, child
            os.close(previous)
        fd = os.open(parts[-1], os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                     dir_fd=parent_fd)
        info = os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid() and info.st_nlink == 1,
             'pretag_output_handoff_failed')
        stream = os.fdopen(fd, 'ab'); fd = None
        with stream:
            need(stream.write(line) == len(line), 'pretag_output_handoff_failed')
            stream.flush(); os.fsync(stream.fileno())
    finally:
        owned, fd = fd, None
        try:
            if owned is not None:
                os.close(owned)
        finally:
            owned, parent_fd = parent_fd, None
            if owned is not None:
                os.close(owned)


def emit(record, root, environment):
    owned, failure, stage = None, None, 'output'
    try:
        data = result.encode(record)
        parent = _temporary(root, environment)
        owned = private_io.PrivateRoot(parent, 'rc-pretag-observation-', source_root=root)
        with owned.open(result.NAME, 'xb') as stream:
            need(stream.write(data) == len(data), 'pretag_output_failed')
        need(owned.files() == (result.NAME,), 'pretag_output_failed')
        readback = owned.read(result.NAME, result.SUCCESS_LIMIT)
        need(readback == data and hashlib.sha256(readback).digest() == hashlib.sha256(data).digest(),
             'pretag_output_failed')
        path = owned.path / result.NAME
    except BaseException as error:
        failure = result.Failure(stage, error)
    finally:
        if owned is not None:
            try: owned.close()
            except BaseException as error:
                if failure is None: failure = result.Failure('output', error)
                else: failure.record('output', error)
    if failure is not None: raise failure from None
    try: _handoff(path, parent, environment)
    except BaseException as error: raise result.Failure('output_handoff', error) from None
    return path


def main():
    token = os.environ.pop('GH_TOKEN', '')
    api, failure = None, None
    try:
        need(len(sys.argv) == 1, 'pretag_context_rejected')
        api = snapshot.GitHub(token)
        observation = collect(ROOT, os.environ, api, opener=None)
        api.token = ''; token = ''
        emit(observation, ROOT, os.environ)
    except BaseException as error:
        failure = error if isinstance(error, result.Failure) else result.Failure('invocation', error)
    finally:
        if api is not None: api.token = ''
        token = ''
    if failure is None: return 0
    try:
        data = failure.encode().decode('utf-8')
        need(sys.stdout.write(data) == len(data), 'pretag_output_failed')
        sys.stdout.flush()
    except BaseException as error:
        failure.record('output', error)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
