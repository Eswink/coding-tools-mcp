"""Capture the standard-user bootstrap before importing the native test harness.

No credential is accepted. The controller owns the source/manifest (read-only to
this user); the log is under the writable, disposable fixture state directory.
"""
from __future__ import annotations
import faulthandler
import os
from pathlib import Path
import runpy
import sys


def main() -> None:
    if sys.platform != 'win32' or len(sys.argv) != 2:
        raise RuntimeError('Windows fixture manifest required')
    manifest = Path(sys.argv[1]).resolve(strict=True)
    root = manifest.parent
    if not (root / '.standard-account-fixture-v22').is_file():
        raise RuntimeError('missing owned fixture marker')
    state = root / 'state'
    with (state / '标准宿主引导v27.log').open('w', encoding='utf-8', buffering=1) as stream:
        sys.stdout = sys.stderr = stream
        print('bootstrap_entered pid=' + str(os.getpid()), flush=True)
        # Stack frames only, not locals; the timer is cancelled before OAuth.
        faulthandler.enable(file=stream)
        faulthandler.dump_traceback_later(45, file=stream)
        target = root / 'source' / 'scripts' / 'Windows标准用户验收v22.py'
        sys.argv = [str(target), '--child-manifest', str(manifest)]
        try:
            runpy.run_path(str(target), run_name='__main__')
        except BaseException as error:
            print('bootstrap_exit_type=' + type(error).__name__, flush=True)
            raise
        finally:
            faulthandler.cancel_dump_traceback_later()


if __name__ == '__main__':
    main()
