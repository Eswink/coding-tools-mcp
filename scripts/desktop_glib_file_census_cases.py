"""Deterministic filesystem cases used by existing compiler ownership test IDs."""
import errno
import os
from pathlib import Path
import tempfile
from unittest import mock

import desktop_glib_build_contract as c
import desktop_glib_file_census as census


def pair(root):
    root.mkdir()
    selected, alias = root / 'selected', root / 'alias'
    selected.write_bytes(b'stable')
    os.link(selected, alias)
    return selected, alias


def recovery_cases(case):
    for kind in ('file', 'directory', 'exhausted'):
        with case.subTest(census=kind), tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'target'
            selected, _ = pair(root)
            transient = root / 'temporary.rcgu.o'
            transient.mkdir() if kind == 'directory' else transient.write_bytes(b'object')
            expected, original = c.file_record(selected, single_link=False), os.walk
            attempts = []

            def walk(*args, **kwargs):
                attempts.append(1)
                if kind == 'exhausted':
                    yield str(root), [], ['missing']
                    return
                for base, dirs, files in original(*args, **kwargs):
                    if len(attempts) == 1 and Path(base) == root:
                        transient.rmdir() if kind == 'directory' else transient.unlink()
                    yield base, dirs, files

            with mock.patch.object(census.os, 'walk', walk):
                if kind == 'exhausted':
                    with case.assertRaises(FileNotFoundError):
                        c.stable_file(selected, root, allow_hardlinks=True)
                else:
                    case.assertEqual(c.stable_file(selected, root, allow_hardlinks=True), expected)
            case.assertEqual(len(attempts), 2)


def rejection_cases(case):
    for kind in ('unlink', 'relink', 'directory_escape', 'external', 'content'):
        with case.subTest(census=kind), tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'target'
            selected, alias = pair(root)
            transient = root / 'temporary.rcgu.o'
            transient.write_bytes(b'object')
            if kind == 'directory_escape':
                holder = root / 'holder'
                holder.mkdir()
                alias.rename(holder / 'alias')
            if kind == 'external':
                alias.rename(Path(temporary) / 'outside')
            original, attempts = os.walk, []

            def walk(*args, **kwargs):
                attempts.append(1)
                for base, dirs, files in original(*args, **kwargs):
                    if len(attempts) == 1 and Path(base) == root:
                        if kind in ('unlink', 'relink'):
                            alias.unlink()
                            if kind == 'relink':
                                os.link(selected, alias)
                        elif kind == 'directory_escape':
                            holder.rename(Path(temporary) / 'escaped')
                        elif kind == 'content':
                            selected.write_bytes(b'change')
                        transient.unlink()
                    yield base, dirs, files

            with mock.patch.object(census.os, 'walk', walk), case.assertRaises(ValueError):
                c.stable_file(selected, root, allow_hardlinks=True)
            case.assertEqual(len(attempts), 2 if kind in ('external', 'directory_escape') else 1)

    for origin in ('walk', 'stat'):
        for code in (errno.EACCES, errno.EIO, errno.ELOOP, errno.ENOTDIR):
            with case.subTest(origin=origin, errno=code), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / 'target'
                selected, _ = pair(root)

                def walk(*args, **kwargs):
                    if origin == 'walk':
                        kwargs['onerror'](OSError(code, 'injected census failure'))
                    return iter([(str(root), [], ['selected', 'alias'])])

                with mock.patch.object(census.os, 'walk', side_effect=walk) as calls:
                    with mock.patch.object(Path, 'stat', side_effect=OSError(code, 'injected stat failure')):
                        with case.assertRaises(OSError) as caught:
                            c.stable_file(selected, root, allow_hardlinks=True)
                    case.assertEqual(caught.exception.errno, code)
                    case.assertEqual(calls.call_count, 1)

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / 'target'
        selected, _ = pair(root)
        wrong_errno = FileNotFoundError(errno.EIO, 'not an ENOENT')
        with mock.patch.object(census.os, 'walk', side_effect=wrong_errno) as calls:
            with case.assertRaises(FileNotFoundError):
                c.stable_file(selected, root, allow_hardlinks=True)
            case.assertEqual(calls.call_count, 1)


def named_replacement_case(case):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        parent = root / 'original'
        selected, _ = pair(parent)
        anchored = c.file_identity(selected.stat())
        original_read, changed = os.read, []

        def read(fd, size):
            data = original_read(fd, size)
            if not data and not changed:
                parent.rename(root / 'moved')
                parent.mkdir()
                selected.write_bytes(b'stable')
                case.assertEqual(c.file_identity(os.fstat(fd)), anchored)
                changed.append(True)
            return data

        with mock.patch.object(c.os, 'read', read):
            with case.assertRaisesRegex(ValueError, 'named_target_changed_during_read'):
                c.stable_file(selected, root, allow_hardlinks=True)
        case.assertEqual(changed, [True])
