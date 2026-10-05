"""Explicit historical C source fixture setup; inert until a test requests it."""
import hashlib
from pathlib import Path
import stat
from tempfile import TemporaryDirectory
from unittest.mock import patch

NAMES = ('rc_consumer_io', 'rc_consumer_transport_worker', 'rc_consumer_transport')
FIXTURE = 'rc_consumer_c_93c2ad95_io.txt'
PINS = {
    'rc_consumer_io': (12953, '3856af4ab573a91838ca2e06bb224ac983c8200a29b34f8a6a6c2bc9619b8de9'),
    'rc_consumer_transport_worker': (6126, '0ef142614c4c465ac166e4c4ca796b94474c333ace9db39cdc64e3010946f52b'),
    'rc_consumer_transport': (10946, '2555906190830843de21c8e54d3fca3f2043bae3330a17109d72bdf7782ca703'),
}


def read_buffers(root):
    """Verify all fixed input buffers before any temporary source is written."""
    buffers = {}
    for name in NAMES:
        path = Path(root) / 'scripts' / (FIXTURE if name == NAMES[0] else name + '.py')
        size, digest = PINS[name]
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size != size:
            raise ValueError('historical_source_rejected')
        with path.open('rb') as source:
            data = source.read(size + 1)
        if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('historical_source_rejected')
        buffers[name] = data
    return buffers


def install_historical(test):
    """Own one verified source root, patching only this test's loaded harness."""
    buffers = read_buffers(test.h.ROOT)
    try:
        temporary = TemporaryDirectory(prefix='rc-historical-c-')
        test.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        scripts = root / 'scripts'
        scripts.mkdir()
        for name in NAMES:
            (scripts / (name + '.py')).write_bytes(buffers[name])
        original = test.h.ROOT
        test.addCleanup(setattr, test.h, 'ROOT', original)
        patcher = patch.object(test.h, 'ROOT', root)
        test.addCleanup(patcher.stop)
        patcher.start()
        return root
    except BaseException:
        test.doCleanups()
        raise
