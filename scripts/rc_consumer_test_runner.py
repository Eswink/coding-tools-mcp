"""Hosted fixture gate: exact official source data is mandatory, zero skips."""
import hashlib
import os
from pathlib import Path
import unittest

from rc_consumer_io import read_bytes
from verify_glib_backport import ARCHIVE_SHA


def main():
    filename = os.environ.get('RC_CONSUMER_TEST_GLIB_ARCHIVE', '')
    if not filename or hashlib.sha256(read_bytes(Path(filename), 1024**2)).hexdigest() != ARCHIVE_SHA:
        raise SystemExit('required checksum-pinned official source fixture unavailable')
    suite = unittest.defaultTestLoader.discover(str(Path(__file__).absolute().parent),
                                                pattern='rc_consumer*_tests.py')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    # Require full current coverage and no optional-source skips in hosted proof.
    return 0 if result.wasSuccessful() and not result.skipped and result.testsRun >= 159 else 1


if __name__ == '__main__':
    raise SystemExit(main())
