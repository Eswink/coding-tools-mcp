#!/usr/bin/env python3
"""Fixed, bounded artifact reads for one internal request; no event acquisition."""
import os
import pathlib
import stat
import sys

if __name__ == '__main__' and (not sys.flags.isolated or len(sys.argv) != 1):
    raise SystemExit(2)

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BROKER = ROOT / 'tests' / 'windows-broker-direct'
# -I excludes environment, current-directory and user-site imports. Retain only
# interpreter-owned standard-library paths, then add the two reviewed roots.
STANDARD_PATHS = [path for path in sys.path if path and
                  pathlib.Path(path).is_relative_to(sys.base_prefix) and
                  not {'site-packages', 'dist-packages'} & set(pathlib.Path(path).parts)]
sys.path[:] = [str(HERE), str(BROKER)] + STANDARD_PATHS

import hashlib
import json
from applocker_observation_contract import (FIXED_MEMBERS, target_identity,
                                           validate_bracket, build_query)

EVIDENCE = ROOT / 'evidence'
LIMITS = {'invocation': 4096, 'ownership': 1048576, 'case': 1048576,
          'run': 2097152, 'payload': 9}


def read_fixed_member(member):
    """Reject aliases, special files, links, changes, and uncertain close."""
    if type(member) is not str or member not in FIXED_MEMBERS.values():
        raise ValueError('fixed member required')
    key = next(key for key, value in FIXED_MEMBERS.items() if value == member)
    limit = LIMITS[key]
    windows = sys.platform == 'win32'

    def member_identity(info):
        timestamp = info.st_ctime_ns
        if windows:
            timestamp = getattr(info, 'st_birthtime_ns', None)
            if type(timestamp) is not int or timestamp < 0:
                raise ValueError('member birthtime required')
        return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
                info.st_size, info.st_mtime_ns, timestamp)

    parts = member.split('/')
    paths = [EVIDENCE]
    for part in parts:
        paths.append(paths[-1] / part)
    before = [os.lstat(path) for path in paths]
    for index, info in enumerate(before):
        regular = stat.S_ISREG(info.st_mode) if index == len(paths) - 1 else stat.S_ISDIR(info.st_mode)
        if not regular or getattr(info, 'st_file_attributes', 0) & 0x400 or info.st_ino <= 0:
            raise ValueError('ordinary fixed member required')
    initial = before[-1]
    if initial.st_nlink != 1 or not 0 <= initial.st_size <= limit:
        raise ValueError('member links or size')
    identity = member_identity(initial)
    descriptor = None
    try:
        descriptor = os.open(paths[-1], os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0))
        opened = os.fstat(descriptor)
        actual = member_identity(opened)
        if actual != identity or getattr(opened, 'st_file_attributes', 0) & 0x400:
            raise ValueError('open identity changed')
        data = bytearray()
        complete = False
        for _ in range(limit // 65536 + 2):
            chunk = os.read(descriptor, min(65536, limit + 1 - len(data)))
            if not chunk:
                complete = True
                break
            data.extend(chunk)
            if len(data) > limit:
                raise ValueError('member too large')
        if not complete or len(data) != initial.st_size:
            raise ValueError('incomplete member')
        final = os.fstat(descriptor)
        actual = member_identity(final)
        # Windows path ctime is creation time; descriptor ctime is ChangeTime.
        if (actual != identity or getattr(final, 'st_file_attributes', 0) & 0x400 or
                (windows and final.st_ctime_ns != opened.st_ctime_ns)):
            raise ValueError('read identity changed')
        after = [os.lstat(path) for path in paths]
        for old, new in zip(before, after):
            if ((old.st_dev, old.st_ino, old.st_mode, old.st_nlink) !=
                    (new.st_dev, new.st_ino, new.st_mode, new.st_nlink) or
                    getattr(new, 'st_file_attributes', 0) & 0x400):
                raise ValueError('path identity changed')
        last = after[-1]
        if (member_identity(last)[4:] != identity[4:] or
                last.st_ctime_ns != initial.st_ctime_ns):
            raise ValueError('member content changed')
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return bytes(data)


def prepare_request():
    """Read exactly the five fixed members; return a canonical private request."""
    members = {key: read_fixed_member(member) for key, member in FIXED_MEMBERS.items()}
    bracket = validate_bracket(members['invocation'])
    identity = target_identity(members['ownership'], members['case'], members['run'], members['payload'])
    query = build_query(identity, bracket)
    request = dict(identity, Protocol='applocker-prepared-request-v1',
                   StartedUtc=bracket['StartedUtc'], EndedUtc=bracket['EndedUtc'],
                   InvocationSha256=hashlib.sha256(members['invocation']).hexdigest(),
                   Query=query, QuerySha256=hashlib.sha256(query.encode('utf-8')).hexdigest())
    encoded = (json.dumps(request, ensure_ascii=True, sort_keys=True,
                          separators=(',', ':'), allow_nan=False) + '\n').encode('ascii')
    if len(encoded) > 131072:
        raise ValueError('request too large')
    return encoded


def main():
    """No CLI or environment input and no diagnostic payload on either stream."""
    if not sys.flags.isolated or len(sys.argv) != 1:
        return 2
    try:
        result = prepare_request()
        sys.stdout.buffer.write(result)
        sys.stdout.buffer.flush()
    except Exception:
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
