"""Owned, bounded preparation of the fixed inert pipe and loopback fixtures."""
import hashlib
import json
import os
import select
import stat
import time

# Unconfirmed fixture disposal retains its process, private directory and owner.
_UNCERTAIN = []
PREPARED_MODES = frozenset({'request_backpressure', 'local_headers', 'local_body',
                           'local_api_headers', 'local_api_status', 'local_storage_status'})


def publish_ready(config, raw):
    """The actual fixture child calls this only after successfully emitting R."""
    mode = json.loads(raw)['mode']
    assert type(mode) is str and mode in PREPARED_MODES
    value = dict(mode=mode, pid=os.getpid(),
                 config_sha256=hashlib.sha256(raw).hexdigest())
    data = json.dumps(value, sort_keys=True).encode()
    assert len(data) <= 1024
    pending = config.parent / 'observed.pending'
    with pending.open('xb') as stream:
        assert stream.write(data) == len(data)
    os.replace(pending, config.parent / 'observed.json')


def _retire_prepared(adapter):
    """Cleanup only this actual inert child; uncertainty never releases the owner."""
    process, end = adapter.process, time.monotonic() + .5
    if process is None:
        return False  # Call entry without an owned return is not definite no-child.
    try:
        if process.poll() is None:
            process.kill()
        left = end - time.monotonic()
        assert left > 0
        process.wait(timeout=left)
        assert process.poll() is not None
        for stream in (process.stdin, process.stdout, process.stderr):
            assert time.monotonic() < end
            if stream is not None:
                stream.close()
                assert stream.closed
        assert time.monotonic() < end
        return True
    except BaseException:
        return False


def backpressure_opener(*responses, mode='responses', port=None):
    """Preserve original Opener/test methods; disclose separate fixture readiness."""
    from rc_consumer_transport_tests import Opener
    adapter = Opener(*responses, mode=mode, port=port)
    if type(mode) is not str or mode not in PREPARED_MODES:
        return adapter
    adapter._remove.atexit = False
    end = time.monotonic() + .9
    try:
        process = adapter.start_worker()  # The original constructor and real Popen.
        config = adapter.directory / 'fixture.json'
        assert stat.S_ISREG(config.lstat().st_mode)
        with config.open('rb') as stream:
            raw = stream.read(8 * 1024**2 + 1)
        assert len(raw) <= 8 * 1024**2
        expected = dict(mode=mode, pid=process.pid,
                        config_sha256=hashlib.sha256(raw).hexdigest())
        witness = adapter.directory / 'observed.json'
        while True:
            now = time.monotonic()
            assert now < end and process.poll() is None, 'fixture readiness unavailable'
            if witness.exists():
                assert stat.S_ISREG(witness.lstat().st_mode)
                with witness.open('rb') as stream:
                    data = stream.read(1025)
                assert len(data) <= 1024
                value = json.loads(data)
                assert type(value) is dict and type(value.get('pid')) is int and value == expected
                if select.select([process.stdout], [], [], 0)[0]:
                    assert time.monotonic() < end and process.poll() is None
                    break  # Leave the actual R frame unread for the original exchange.
            time.sleep(min(.01, end - now))
        handed_off = False
        def handoff():
            nonlocal handed_off
            assert not handed_off and process.poll() is None, 'fixture child already handed off'
            handed_off = True
            return process
        adapter.start_worker = handoff
        adapter._fixture_ready = expected
        return adapter
    except BaseException:
        if not _retire_prepared(adapter):
            adapter._remove.detach()
            _UNCERTAIN.append(adapter)
        raise AssertionError('owned backpressure fixture preparation failed') from None
