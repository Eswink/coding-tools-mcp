"""Real Git fixtures and explicitly owned pipe fault children."""
from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

import exact_build_audit as exact
import rc_consumer_fixed_git as fixed
from rc_consumer_fixtures import ConsumerFixture

TARGET = 'x86_64-unknown-linux-gnu'


def git(root, *args, input=None):
    return subprocess.run([fixed.BINARY, '--no-pager', '-C', str(root), *args],
        input=input, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=dict(fixed.ENV), check=True).stdout.decode().strip()


def source(parent):
    root = parent / 'source'
    root.mkdir()
    git(root, 'init', '-q', '--initial-branch=main')
    (root / 'package.json').write_text('{"version":"1.2.3-rc.4"}')
    (root / exact.MANIFEST).parent.mkdir(parents=True)
    (root / exact.MANIFEST).write_text('[package]\nname="fixture"\nversion="1.2.3-rc.4"\n')
    (root / exact.LOCK).write_text('version=4\n')
    (root / 'tracked').write_text('tracked\n')
    git(root, 'add', '.')
    git(root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
        'commit', '-qm', 'Synthetic fixture')
    return root, git(root, 'rev-parse', 'HEAD')


def verify_fixture(fixture, **budget):
    f = fixture
    return exact.verify(f.root, f.exact, f.sha, f.version, TARGET,
                        exact.digest((f.exact / 'envelope.json').read_bytes()), f.unpacked / 'bin', **budget)


def sentinel(parent):
    marker = parent / 'helper-executed'
    path = parent / 'helper'
    path.write_text('#!/bin/sh\nprintf executed >> "' + str(marker) + '"\nexit 91\n')
    path.chmod(0o700)
    return path, marker


@contextmanager
def record_git():
    original, calls, children = subprocess.Popen, [], []
    def launch(argv, *args, **kwargs):
        process = original(argv, *args, **kwargs)
        if argv[0] == fixed.BINARY:
            calls.append((tuple(argv), kwargs.copy()))
            children.append(process)
        return process
    with patch.object(fixed.subprocess, 'Popen', side_effect=launch):
        yield SimpleNamespace(calls=calls, children=children)


@contextmanager
def fault_child(script, *, wrap=None):
    """Substitute only Popen, only for a fixed-Git launch, with a real owned child."""
    original, children, wrappers = subprocess.Popen, [], []
    def launch(argv, *args, **kwargs):
        if argv[0] != fixed.BINARY:
            return original(argv, *args, **kwargs)
        process = original([sys.executable, '-I', '-S', '-u', '-c', script],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            bufsize=0, close_fds=True, env={'LC_ALL': 'C', 'LANG': 'C'})
        children.append(process)
        if wrap is not None:
            wrappers.append(wrap(process))
        return process
    try:
        with patch.object(fixed.subprocess, 'Popen', side_effect=launch):
            yield SimpleNamespace(children=children, wrappers=wrappers)
    finally:
        # Test cleanup follows evidence checks; never report this as runtime cleanup.
        for process in children:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=3)


def reaped(test, children):
    test.assertTrue(children)
    for child in children:
        test.assertIsNotNone(child.returncode)
        test.assertIsNotNone(child.poll())
        with test.assertRaises(ChildProcessError):
            os.waitpid(child.pid, os.WNOHANG)


class Cancelled(Exception):
    code = 'cancelled'


@contextmanager
def observe_pipe(reader):
    original, reads = os.read, []
    def read(fd, amount):
        data = original(fd, amount)
        process = reader.process
        if process is not None and process.stdout is not None and fd == process.stdout.fileno():
            reads.append((data, process.poll() is None))
        return data
    with patch.object(fixed.os, 'read', side_effect=read):
        yield reads
