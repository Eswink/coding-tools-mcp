"""Independent metadata contracts and bounded, test-only failure diagnostics."""
import io
import sys
import types
from contextlib import contextmanager
from unittest import mock

__all__ = ['check_metadata_snapshots', 'capture_fixed_stats']
_FIELDS = ('st_dev', 'st_ino', 'st_mode', 'st_nlink', 'st_size',
           'st_mtime_ns', 'st_ctime_ns', 'st_birthtime_ns',
           'st_file_attributes', 'st_reparse_tag')
_MISSING = object()


@contextmanager
def capture_fixed_stats(driver, member_key, size):
    """Forward existing calls; on failure emit only bounded numeric metadata."""
    records, total, seen = [], 0, 0
    phases = {'lstat': 0, 'fstat': 0}
    enabled = (type(member_key) is str and member_key in
               ('invocation', 'ownership', 'case', 'run', 'payload') and
               type(size) is int and 0 <= size <= 2097153)

    def forwarding(operation, original):
        def forward(*args, **kwargs):
            nonlocal total, seen
            info = original(*args, **kwargs)
            phases[operation] += 1
            seen += 1
            if enabled and seen <= 10:
                try:
                    fields = []
                    for field in _FIELDS:
                        value = getattr(info, field, None)
                        if type(value) is int and value.bit_length() <= 4096:
                            fields.append(field + '=' + str(value))
                    line = (f'member={member_key} size={size} '
                            f'phase={operation}{phases[operation]} ' + ' '.join(fields) + '\n')
                    length = len(line.encode('ascii'))
                    if total + length <= 16384:
                        records.append(line)
                        total += length
                except BaseException:
                    pass  # Diagnostics must never change the original operation.
            return info
        return forward

    with mock.patch.object(driver.os, 'lstat', forwarding('lstat', driver.os.lstat)), \
            mock.patch.object(driver.os, 'fstat', forwarding('fstat', driver.os.fstat)):
        try:
            yield
        except BaseException:
            try:
                sys.stderr.write(''.join(records))
            except BaseException:
                pass
            raise


def _snapshots(platform):
    members = []
    for index in range(4):
        values = dict(st_dev=7, st_ino=11, st_mode=0o100600, st_nlink=1,
                      st_size=9, st_mtime_ns=300, st_ctime_ns=100,
                      st_file_attributes=0, st_reparse_tag=0)
        if platform == 'win32':
            values['st_birthtime_ns'] = 100
            if index in (1, 2):
                values['st_ctime_ns'] = 200
        members.append(types.SimpleNamespace(**values))
    return members


def _check_case(test, driver, platform, stage=None, field=None, value=None):
    members = _snapshots(platform)
    if field is not None:
        if value is _MISSING:
            delattr(members[stage], field)
        else:
            setattr(members[stage], field, value)
    ancestors = [types.SimpleNamespace(st_dev=7, st_ino=inode, st_mode=0o40700,
                                     st_nlink=1, st_file_attributes=0)
                 for inode in (21, 22, 23)]
    member = 'pilot/cmd-relative-batch-exit23/generated-direct.cmd.bin'
    paths = [driver.EVIDENCE]
    for part in member.split('/'):
        paths.append(paths[-1] / part)
    with test.variant(platform=platform, stage=stage, field=field,
                      value='missing' if value is _MISSING else value), \
            mock.patch.object(driver.sys, 'platform', platform), \
            mock.patch.object(driver.os, 'lstat', side_effect=ancestors + [members[0]] + ancestors + [members[3]]) as lstat, \
            mock.patch.object(driver.os, 'open', return_value=41) as opened, \
            mock.patch.object(driver.os, 'fstat', side_effect=[members[1], members[2]]) as fstat, \
            mock.patch.object(driver.os, 'read', side_effect=[b'exit 23\r\n', b'']) as read, \
            mock.patch.object(driver.os, 'close') as close:
        if field is None:
            test.assertEqual(driver.read_fixed_member(member), b'exit 23\r\n')
        else:
            with test.assertRaises(ValueError):
                driver.read_fixed_member(member)
        expected_open = int(stage != 0)
        expected_stats = 0 if stage == 0 else 1 if stage == 1 else 2
        expected_paths = paths if stage in (0, 1, 2) else paths + paths
        test.assertEqual(lstat.call_args_list, [mock.call(path) for path in expected_paths])
        test.assertEqual(opened.call_count, expected_open)
        test.assertEqual(fstat.call_args_list, [mock.call(41)] * expected_stats)
        test.assertEqual(read.call_args_list, [] if stage in (0, 1) else
                         [mock.call(41, 10), mock.call(41, 1)])
        test.assertEqual(close.call_args_list, [mock.call(41)] * expected_open)


def _check_capture(test):
    info = _snapshots('win32')[0]
    private = '/private/path/SECRET_CONTENT'
    error = OSError(private)
    for failure in (False, True):
        with test.variant(capture='forwarding', failure=failure):
            operations = types.SimpleNamespace(lstat=mock.Mock(return_value=info),
                                               fstat=mock.Mock(return_value=info))
            fake = types.SimpleNamespace(os=operations)
            originals = (operations.lstat, operations.fstat)
            output = io.StringIO()
            try:
                with mock.patch.object(sys, 'stderr', output), capture_fixed_stats(fake, 'payload', 9):
                    for _ in range(7):
                        test.assertIs(fake.os.lstat(private, dir_fd=17), info)
                        test.assertIs(fake.os.fstat(19), info)
                    if failure:
                        raise error
            except OSError as caught:
                test.assertIs(caught, error)
            else:
                test.assertFalse(failure)
            test.assertIs(fake.os.lstat, originals[0])
            test.assertIs(fake.os.fstat, originals[1])
            test.assertEqual(originals[0].call_args_list, [mock.call(private, dir_fd=17)] * 7)
            test.assertEqual(originals[1].call_args_list, [mock.call(19)] * 7)
            lines = output.getvalue().splitlines()
            test.assertEqual(len(lines), 10 if failure else 0)
            test.assertNotIn(private, output.getvalue())
            test.assertNotIn('SECRET_CONTENT', output.getvalue())
            for line in lines:
                tokens = line.split()
                test.assertEqual(tokens[:2], ['member=payload', 'size=9'])
                test.assertRegex(tokens[2], r'^phase=(lstat|fstat)[1-5]$')
                for token in tokens[3:]:
                    name, number = token.split('=')
                    test.assertIn(name, _FIELDS)
                    test.assertEqual(str(int(number)), number)

    for mode in ('bytes', 'invalid_metadata', 'invalid_context', 'output_failure', 'operation_failure'):
        with test.variant(capture=mode):
            values = {name: 1 << 4095 for name in _FIELDS}
            if mode == 'invalid_metadata':
                values.update(st_dev=private, st_ino=1 << 5000, st_mode=True,
                              st_nlink=1.5, st_size=None)
            info = types.SimpleNamespace(**values, path=private, content=b'SECRET_CONTENT')
            operation = mock.Mock(return_value=info)
            fake = types.SimpleNamespace(os=types.SimpleNamespace(lstat=operation, fstat=operation))
            output = io.StringIO()
            sink = mock.Mock(side_effect=RuntimeError(private)) if mode == 'output_failure' else None
            if mode == 'operation_failure':
                operation.side_effect = error
            key, size = (private, True) if mode == 'invalid_context' else ('run', 2097153)
            with mock.patch.object(sys, 'stderr', output), \
                    mock.patch.object(output, 'write', sink or output.write), \
                    test.assertRaises(OSError) as caught:
                with capture_fixed_stats(fake, key, size):
                    for _ in range(20):
                        test.assertIs(fake.os.lstat(private), info)
                    raise error
            test.assertIs(caught.exception, error)
            test.assertEqual(operation.call_count, 1 if mode == 'operation_failure' else 20)
            text = output.getvalue()
            test.assertLessEqual(len(text.encode('ascii')), 16384)
            test.assertLessEqual(len(text.splitlines()), 10)
            test.assertNotIn(private, text)
            test.assertNotIn('SECRET_CONTENT', text)
            if mode == 'bytes':
                test.assertGreater(len(text), 0)
                test.assertLess(len(text.splitlines()), 10)
            if mode == 'invalid_metadata':
                for name in ('st_dev', 'st_ino', 'st_mode', 'st_nlink', 'st_size'):
                    test.assertNotIn(name + '=', text)
            if mode in ('invalid_context', 'output_failure', 'operation_failure'):
                test.assertEqual(text, '')


def check_metadata_snapshots(test, driver):
    """Exercise literal, independent expectations on both platform branches."""
    shared = (('st_dev', 8), ('st_ino', 12), ('st_mode', 0o100640),
              ('st_nlink', 2), ('st_size', 8), ('st_mtime_ns', 301))
    for platform in ('win32', 'linux'):
        _check_case(test, driver, platform)
        comparable = shared + (('st_birthtime_ns', 101),) if platform == 'win32' else shared + (('st_ctime_ns', 101),)
        for stage in (1, 2, 3):
            for field, value in comparable:
                _check_case(test, driver, platform, stage, field, value)
    for stage, value in ((2, 201), (3, 101)):
        _check_case(test, driver, 'win32', stage, 'st_ctime_ns', value)
    for stage in range(4):
        for value in (_MISSING, None, True, 100.0, '100', -1):
            _check_case(test, driver, 'win32', stage, 'st_birthtime_ns', value)
    _check_capture(test)
