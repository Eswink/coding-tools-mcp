"""Real source Git commands and owned child faults; synthetic evidence only."""
from contextlib import contextmanager
import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace
import socket
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

import exact_build_audit as exact
import rc_consumer_fixed_git as fixed
from rc_consumer_io import ConsumerError
from rc_consumer_git_test_support import Cancelled, fault_child, git, reaped, record_git, sentinel, source
import rc_version_gate as rc
import rc_consumer_io as safe
import reviewed_source_gate as reviewed
import reviewed_source_gate_tests as reviewed_cases
import source_provenance_gate as provenance
from source_provenance_gate_tests import repository


@contextmanager
def reviewed_fixture():
    fixture = reviewed_cases.ReviewedTests()
    fixture.setUp()
    try:
        # The legacy builder opts into autocrlf; remove that fixture-only setting.
        # Production support and whitelist stay unchanged.
        git(fixture.root, 'config', '--unset', 'core.autocrlf')
        yield fixture
    finally:
        fixture.doCleanups()


class SourceGitCases(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='source-git-case-')
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.root, self.sha = source(self.parent)
        self.oid = git(self.root, 'rev-parse', 'HEAD:tracked')
        self.tag = 'v1.2.3-rc.4'
        git(self.root, 'tag', self.tag)

    def reader(self, **controls):
        return fixed.Reader(self.root, **(controls or dict(check_active=lambda: None)))

    def test_nine_typed_operations_preserve_exact_native_outputs_and_launches(self):
        tree = git(self.root, 'rev-parse', 'HEAD^{tree}')
        with record_git() as seen, self.reader() as reader:
            self.assertEqual(reader.commit(), self.sha)
            self.assertTrue(reader.tracked_clean())
            self.assertEqual(reader.untracked(), b'')
            self.assertTrue(reader.ancestor(self.sha, self.sha))
            entry = reader.tree_entry(self.sha, 'tracked')
            self.assertEqual(entry, f'100644 blob {self.oid}\ttracked\0'.encode())
            self.assertEqual(reader.blob_bytes(self.oid), b'tracked\n')
            self.assertEqual(reader.changes(self.sha, self.sha), b'')
            self.assertEqual(reader.tag_oid(self.tag), self.sha)
            self.assertEqual(reader.tag_kind(self.tag), b'commit\n')
            self.assertEqual(reader.read('rev-parse', 'HEAD^{tree}'), tree)
        suffixes = [('rev-parse', '--verify', 'HEAD^{commit}'),
            ('ls-files', '--stage', '-z', '--no-recurse-submodules'),
            ('diff', '--quiet', '--no-ext-diff', '--no-textconv', 'HEAD', '--'),
            ('ls-files', '--others', '-z'), ('merge-base', '--is-ancestor', self.sha, self.sha),
            ('ls-tree', '-z', self.sha, '--', 'tracked'), ('cat-file', 'blob', self.oid),
            ('diff', '--name-status', '--no-renames', '--no-ext-diff', '--no-textconv', '-z', self.sha, self.sha),
            ('rev-parse', '--verify', 'refs/tags/' + self.tag), ('cat-file', '-t', 'refs/tags/' + self.tag),
            ('rev-parse', 'HEAD^{tree}')]
        self.assertEqual(len(seen.calls), 12)
        for (argv, options), suffix in zip(seen.calls[1:], suffixes):
            self.assertEqual(argv[-len(suffix):], suffix)
            self.assertEqual(argv[0], fixed.BINARY)
            self.assertEqual(options['env'], fixed.ENV)
            self.assertEqual((options['cwd'], options['shell'], options['close_fds']), ('/', False, True))
            self.assertEqual(len(options['pass_fds']), 2)
        reaped(self, seen.children)

    def test_dynamic_operands_reject_before_launch_without_new_command_authority(self):
        with self.reader() as reader:
            operations = [lambda value: reader.ancestor(value, self.sha),
                lambda value: reader.ancestor(self.sha, value), lambda value: reader.blob_bytes(value),
                lambda value: reader.changes(value, self.sha), lambda value: reader.tree_entry(value, 'tracked')]
            with patch.object(fixed.subprocess, 'Popen', side_effect=AssertionError('invalid operand launch')):
                for operation in operations:
                    for value in ('HEAD', '--help', 'A' * 40, '0' * 39, self.sha + '\n', None):
                        with self.subTest(value=value), self.assertRaisesRegex(ConsumerError, '^unsupported_git_operation$'):
                            operation(value)
                for path in ('', '/abs', '../up', 'a//b', 'a/./b', 'a\\b', 'a\0b', 'a\nb', 'x' * 4097, 'a/' * 64 + 'b'):
                    with self.subTest(path=path), self.assertRaisesRegex(ConsumerError, '^unsupported_git_operation$'):
                        reader.tree_entry(self.sha, path)
                for tag in ('v1.2.3', '--help', 'refs/tags/' + self.tag, 'v01.2.3-rc.4', 'v1.2.3-rc.4４', 'v' + '1' * 256 + '.2.3-rc.4', self.tag + '\n'):
                    for operation in (reader.tag_oid, reader.tag_kind):
                        with self.assertRaisesRegex(ConsumerError, '^unsupported_git_operation$'): operation(tag)
                with self.assertRaisesRegex(ConsumerError, '^unsupported_git_operation$'):
                    reader.read('merge-base', '--is-ancestor', self.sha, self.sha)

    def test_quiet_predicates_only_accept_empty_stdout_and_exit_zero_or_one(self):
        with self.reader() as reader:
            for kind in ('tracked', 'ancestor'):
                for code in (0, 1, 2, 128, -1):
                    script = f'raise SystemExit({code})'
                    with self.subTest(kind=kind, code=code), fault_child(script) as seen:
                        if code in (0, 1): self.assertIs(reader._run(kind, 0), code == 0)
                        else:
                            with self.assertRaisesRegex(exact.EvidenceError, '^git_identity_unavailable$'):
                                reader._run(kind, 0)
                        reaped(self, seen.children)
                with fault_child('import os; os.write(1,b"x")') as seen:
                    with self.assertRaisesRegex(ConsumerError, '^git_output_limit_exceeded$'):
                        reader._run(kind, 0)
                    reaped(self, seen.children)

    def test_commit_tag_tree_framing_and_fixed_caps_reject_malformed_output(self):
        with self.reader() as reader:
            rows = [(reader.commit, b'0' * 40), (lambda: reader.tag_oid(self.tag), b'0' * 40 + b'\r\n'),
                (lambda: reader.tag_kind(self.tag), b'commit'), (lambda: reader.tag_kind(self.tag), b'unknown\n'),
                (lambda: reader.tree_entry(self.sha, 'tracked'), b'two\0entries\0'),
                (reader.untracked, b'unterminated')]
            for operation, raw in rows:
                with self.subTest(raw=raw), fault_child(f'import os; os.write(1,{raw!r})') as seen:
                    with self.assertRaises((exact.EvidenceError, ConsumerError)): operation()
                    reaped(self, seen.children)
            rows = [('commit', 41), ('tag_oid', 41), ('tag_kind', 8), ('entry', fixed.MAX_PATH_BYTES + 128),
                    ('untracked', fixed.SOURCE_LIST_LIMIT), ('changes', fixed.SOURCE_LIST_LIMIT), ('blob', fixed.BLOB_LIMIT)]
            for kind, cap in rows:
                for extra in (0, 1):
                    script = f'import os\nleft={cap + extra}\nwhile left:\n n=os.write(1,b"x"*min(left,65536)); left-=n\n'
                    with self.subTest(kind=kind, extra=extra), fault_child(script) as seen:
                        if extra:
                            with self.assertRaisesRegex(ConsumerError, '^git_output_limit_exceeded$'): reader._run(kind, cap)
                        else: self.assertEqual(len(reader._run(kind, cap)), cap)
                        reaped(self, seen.children)

    def test_raw_blob_bytes_and_absent_tree_entry_are_not_decoded_or_stripped(self):
        data = b'\0\xff\r\n raw \n'
        (self.root / 'binary').write_bytes(data)
        git(self.root, 'add', 'binary')
        git(self.root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'binary')
        sha = git(self.root, 'rev-parse', 'HEAD')
        oid = git(self.root, 'rev-parse', 'HEAD:binary')
        with self.reader() as reader:
            self.assertEqual(reader.blob_bytes(oid), data)
            self.assertEqual(reader.tree_entry(sha, 'missing'), b'')
            self.assertEqual(reader.changes(self.sha, sha), b'A\0binary\0')
            self.assertFalse(reader.ancestor(sha, self.sha))

    def test_tracked_staged_untracked_and_ignored_dirtiness_keep_distinct_meaning(self):
        for staged in (False, True):
            (self.root / 'tracked').write_text('dirty')
            if staged: git(self.root, 'add', 'tracked')
            with self.reader() as reader: self.assertFalse(reader.tracked_clean())
            git(self.root, 'reset', '--hard', '-q', self.sha)
        (self.root / '.git/info/exclude').write_text('ignored\n')
        for name in ('untracked', 'ignored'):
            (self.root / name).write_text(name)
        with self.reader() as reader:
            self.assertTrue(reader.tracked_clean())
            self.assertEqual(set(reader.untracked().split(b'\0')[:-1]), {b'untracked', b'ignored'})

    def test_gitlink_and_nonzero_index_stages_precede_tracked_diff(self):
        for mode in ('gitlink', 'unmerged'):
            if mode == 'gitlink': git(self.root, 'update-index', '--add', '--cacheinfo', '160000,' + self.sha + ',sub')
            else: git(self.root, 'update-index', '--index-info', input=f'100644 {self.oid} 1\ttracked\n'.encode())
            with self.reader() as reader, record_git() as seen:
                with self.assertRaisesRegex(ConsumerError, '^unsupported_git_index$'): reader.tracked_clean()
                self.assertEqual(len(seen.calls), 1)
                self.assertNotIn('diff', seen.calls[0][0])
                reaped(self, seen.children)
            git(self.root, 'reset', '--hard', '-q', self.sha)

    def test_source_children_drop_inherited_environment_and_reject_helper_network_config(self):
        helper, marker = sentinel(self.parent)
        bad = dict(PATH=str(self.parent), GIT_DIR='/missing', GIT_WORK_TREE='/missing', LD_PRELOAD=str(helper),
            GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='core.fsmonitor', GIT_CONFIG_VALUE_0=str(helper),
            GIT_EXEC_PATH=str(self.parent), GIT_SSH_COMMAND=str(helper), GIT_ASKPASS=str(helper), GH_TOKEN='synthetic')
        with patch.dict(os.environ, bad, clear=True), record_git() as seen, self.reader() as reader:
            self.assertEqual(reader.commit(), self.sha)
            self.assertTrue(reader.tracked_clean())
            self.assertEqual(reader.blob_bytes(self.oid), b'tracked\n')
        self.assertTrue(all(options['env'] == fixed.ENV for _, options in seen.calls))
        reaped(self, seen.children)
        config = self.root / '.git/config'; original = config.read_bytes()
        with socket.socket() as server:
            server.bind(('127.0.0.1', 0)); server.listen(); server.settimeout(0.05)
            rows = [f'[diff "attack"]\ntextconv={helper}', f'[diff]\nexternal={helper}',
                f'[credential]\nhelper={helper}', f'[core]\nfsmonitor={helper}',
                f'[remote "origin"]\nurl=http://127.0.0.1:{server.getsockname()[1]}\npromisor=true',
                '[core]\nautocrlf=false']
            for tail in rows:
                config.write_bytes(original + ('\n' + tail + '\n').encode())
                with self.assertRaisesRegex(ConsumerError, '^unsupported_git_configuration$'):
                    with self.reader(): pass
            with self.assertRaises(TimeoutError): server.accept()
        self.assertFalse(marker.exists())

    def test_callback_only_source_commands_do_not_create_an_operation_clock(self):
        polls = []
        with patch.object(fixed.time, 'monotonic', side_effect=AssertionError('invented clock')):
            with self.reader(check_active=lambda: polls.append(True) and None) as reader:
                self.assertEqual(reader.commit(), self.sha)
                self.assertTrue(reader.tracked_clean())
                self.assertTrue(reader.ancestor(self.sha, self.sha))
                self.assertEqual(reader.blob_bytes(self.oid), b'tracked\n')
        self.assertTrue(polls)

    def test_each_source_operation_timeout_and_cancel_reaps_the_known_child(self):
        operations = [('commit', 41), ('tracked', 0), ('untracked', fixed.SOURCE_LIST_LIMIT), ('ancestor', 0),
            ('entry', fixed.MAX_PATH_BYTES + 128), ('blob', fixed.BLOB_LIMIT), ('changes', fixed.SOURCE_LIST_LIMIT),
            ('tag_oid', 41), ('tag_kind', 8)]
        for kind, cap in operations:
            for cancel in (False, True):
                with self.subTest(kind=kind, cancel=cancel), self.reader() as reader:
                    reader.deadline = time.monotonic() + 0.15
                    def active():
                        if cancel and reader.process is not None: raise Cancelled()
                    reader.check_active = active
                    with fault_child('import time; time.sleep(10)') as seen:
                        code = 'transport_cancelled' if cancel else 'transport_deadline_exceeded'
                        with self.assertRaisesRegex(ConsumerError, '^' + code + '$'): reader._run(kind, cap)
                        reaped(self, seen.children)

    def test_rc_default_and_controlled_outputs_match_and_invalid_versions_precede_controls(self):
        root = self.parent / 'versions'; root.mkdir(); sha = repository(root)
        expected = rc.verify_source(root, sha, '1.2.3-rc.4')
        git(root, 'config', '--unset', 'core.autocrlf')
        self.assertEqual(rc.verify_source(root, sha, '1.2.3-rc.4', check_active=lambda: None), expected)
        for boundary in ('tracked_clean', 'close'):
            for cancelled in (False, True):
                stopped, deadline = [], time.monotonic() + 60
                original = getattr(fixed.Reader, boundary)
                def completed(reader, *args):
                    result = original(reader, *args); stopped.append(True); return result
                def active():
                    if stopped and cancelled: raise Cancelled()
                timer = SimpleNamespace(monotonic=lambda: deadline + 1 if stopped else deadline - 1)
                with self.subTest(boundary=boundary, cancelled=cancelled), \
                     patch.object(fixed.Reader, boundary, completed), patch.object(safe, 'time', timer):
                    code = 'transport_cancelled' if cancelled else 'transport_deadline_exceeded'
                    with self.assertRaisesRegex(ConsumerError, '^' + code + '$'):
                        rc.verify_source(root, sha, check_active=active, deadline=None if cancelled else deadline)
                self.assertTrue(stopped)
        (root / 'src-tauri/tauri.conf.json').write_text('{"version":"9.9.9"}')
        with patch.object(fixed, 'Reader', side_effect=AssertionError('invalid version reader')):
            with self.assertRaisesRegex(ValueError, 'candidate versions'):
                rc.verify_source(root, sha, check_active=lambda: (_ for _ in ()).throw(Cancelled()))

    def test_rc_dirty_and_wrong_sha_diagnostics_precede_post_read_cancellation(self):
        root = self.parent / 'versions'; root.mkdir(); sha = repository(root)
        git(root, 'config', '--unset', 'core.autocrlf')
        for dirty in (False, True):
            if dirty: (root / 'package.json').write_text((root / 'package.json').read_text() + '\n')
            completed, original = [], fixed.Reader.tracked_clean
            def tracked(reader):
                value = original(reader); completed.append(True); return value
            def active():
                if completed: raise Cancelled()
            with patch.object(fixed.Reader, 'tracked_clean', tracked):
                expected = 'tracked source differs' if dirty else 'checkout does not match'
                with self.assertRaisesRegex(ValueError, expected): rc.verify_source(root, 'f' * 40, check_active=active)

    def test_stable_default_remains_legacy_and_controlled_stable_fails_closed(self):
        root = self.parent / 'stable'; root.mkdir(); sha = repository(root, '1.2.3')
        with patch.object(fixed, 'Reader', side_effect=AssertionError('stable reader')):
            self.assertEqual(provenance.verify(root, sha)['source_classification'], 'stable')
            with patch.object(provenance.stable, 'verify_source', side_effect=AssertionError('controlled stable fallback')):
                for options in (dict(check_active=lambda: None), dict(deadline=time.monotonic() + 1)):
                    with self.assertRaisesRegex(ValueError, 'controlled stable source is unsupported'):
                        provenance.verify(root, sha, **options)

    def test_frozen_manifest_outputs_match_with_one_shared_review_reader(self):
        with reviewed_fixture() as fixture:
            sha = fixture.freeze(); expected = fixture.verify(sha)
            with record_git() as seen:
                actual = reviewed.verify(fixture.root, sha, baseline=fixture.base, check_active=lambda: None)
            self.assertEqual(actual, expected)
            # 4 provenance children + config/ancestor/manifest(3)/diff/tree + ten per-entry children.
            self.assertEqual(len(seen.calls), 21)
            self.assertEqual(sum('config' in argv for argv, _ in seen.calls), 2)
            reaped(self, seen.children)
            for boundary in ('last_read', 'close'):
                for cancelled in (False, True):
                    last, stopped, deadline = [], [], time.monotonic() + 60
                    read, close = fixed.Reader.read, fixed.Reader.close
                    def completed(reader, *args):
                        result = read(reader, *args)
                        if args == ('rev-parse', 'HEAD^{tree}'):
                            last.append(reader)
                            if boundary == 'last_read': stopped.append(True)
                        return result
                    def closed(reader):
                        close(reader)
                        if last and reader is last[-1] and boundary == 'close': stopped.append(True)
                    def active():
                        if stopped and cancelled: raise Cancelled()
                    timer = SimpleNamespace(monotonic=lambda: deadline + 1 if stopped else deadline - 1)
                    with self.subTest(boundary=boundary, cancelled=cancelled), patch.object(fixed.Reader, 'read', completed), \
                         patch.object(fixed.Reader, 'close', closed), patch.object(safe, 'time', timer):
                        code = 'transport_cancelled' if cancelled else 'transport_deadline_exceeded'
                        with self.assertRaisesRegex(ConsumerError, '^' + code + '$'):
                            reviewed.verify(fixture.root, sha, baseline=fixture.base, check_active=active,
                                            deadline=None if cancelled else deadline)
                    self.assertEqual(len(last), 1)
                    self.assertTrue(stopped)

    def test_reviewed_ancestry_failure_precedes_late_cancellation(self):
        with reviewed_fixture() as fixture:
            sha = fixture.freeze(); original, done = fixed.Reader.ancestor, []
            def ancestor(reader, baseline, source):
                value = original(reader, baseline, source); done.append(True); return value
            def active():
                if done: raise Cancelled()
            tree = git(fixture.root, 'rev-parse', 'HEAD^{tree}')
            unrelated = git(fixture.root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                            'commit-tree', tree, input=b'Unrelated synthetic root\n')
            with patch.object(fixed.Reader, 'ancestor', ancestor), self.assertRaises(subprocess.CalledProcessError) as failure:
                reviewed.verify(fixture.root, sha, baseline=unrelated, check_active=active)
            self.assertEqual(failure.exception.returncode, 1)
            self.assertEqual(done, [True])

    def test_reviewed_manifest_mutations_retain_closed_semantic_failures(self):
        with reviewed_fixture() as fixture:
            changes = [lambda m: m.update(schema=True), lambda m: m.update(base_commit='0' * 40),
                lambda m: m.update(version='1.2.3-rc.5'), lambda m: m.update(review_reference=''),
                lambda m: m['entries'][0]['after'].update(sha256='0' * 64),
                lambda m: m['entries'][0].update(status='M'), lambda m: m['entries'][0]['after'].update(mode='100755'),
                lambda m: m['entries'][1]['before'].update(blob_sha='0' * 40),
                lambda m: m.update(entries=m['entries'][:1]), lambda m: m.update(entries=m['entries'] * 2),
                lambda m: m.update(entries=list(reversed(m['entries']))),
                lambda m: m['entries'][0].update(path=reviewed.MANIFEST)]
            for mutate in changes:
                value = copy.deepcopy(fixture.manifest); mutate(value)
                with self.subTest(value=value), self.assertRaises(ValueError):
                    reviewed.verify(fixture.root, fixture.freeze(value), baseline=fixture.base, check_active=lambda: None)


    def test_missing_manifest_candidate_symlink_and_bad_manifest_json_fail_closed(self):
        with reviewed_fixture() as fixture:
            source_sha = git(fixture.root, 'rev-parse', 'HEAD')
            with self.assertRaisesRegex(ValueError, 'BLOCKED'):
                reviewed.verify(fixture.root, source_sha, baseline=fixture.base, check_active=lambda: None)
            fixture.freeze()
            path = fixture.root / reviewed.MANIFEST
            for raw in ('{"schema":1,"schema":1}', '{"schema":NaN}', '{}', 'not-json'):
                path.write_text(raw)
                git(fixture.root, 'add', '.')
                git(fixture.root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'bad manifest')
                with self.assertRaises(ValueError):
                    reviewed.verify(fixture.root, git(fixture.root, 'rev-parse', 'HEAD'), baseline=fixture.base,
                                    check_active=lambda: None)
        with reviewed_fixture() as fixture:
            path = fixture.root / 'modified.txt'; path.unlink(); path.symlink_to('target')
            with self.assertRaisesRegex(ValueError, 'candidate symlinks'):
                reviewed.verify(fixture.root, fixture.freeze(), baseline=fixture.base, check_active=lambda: None)

    def test_completed_manifest_failure_precedes_next_budget_callback(self):
        with reviewed_fixture() as fixture:
            source_sha = fixture.freeze(dict(fixture.manifest, schema=True))
            oid = git(fixture.root, 'rev-parse', 'HEAD:' + reviewed.MANIFEST)
            original, reads = fixed.Reader.blob_bytes, []
            def blob(reader, identity):
                data = original(reader, identity)
                if identity == oid: reads.append(True)
                return data
            def active():
                if len(reads) == 2: raise Cancelled()
            with patch.object(fixed.Reader, 'blob_bytes', blob):
                with self.assertRaisesRegex(ValueError, 'manifest schema'):
                    reviewed.verify(fixture.root, source_sha, baseline=fixture.base, check_active=active)
            self.assertEqual(reads, [True, True])

    def test_malformed_diff_framing_status_and_tree_descriptor_do_not_gain_success(self):
        with reviewed_fixture() as fixture:
            sha = fixture.freeze()
            original = fixed.Reader._run
            for kind, raw, message in (('changes', b'M\0one', 'Git diff framing'),
                    ('changes', b'R\0modified.txt\0', 'unsupported source status'),
                    ('entry', b'040000 tree ' + b'0' * 40 + b'\t' + reviewed.MANIFEST.encode() + b'\0', 'Git blob'),
                    ('entry', b'100600 blob ' + b'0' * 40 + b'\t' + reviewed.MANIFEST.encode() + b'\0', 'file mode')):
                def run(reader, operation, cap, *operands):
                    if operation != kind: return original(reader, operation, cap, *operands)
                    with fault_child(f'import os; os.write(1,{raw!r})') as seen:
                        result = original(reader, operation, cap, *operands)
                        reaped(self, seen.children)
                        return result
                with self.subTest(kind=kind, raw=raw), patch.object(fixed.Reader, '_run', run):
                    with self.assertRaisesRegex(ValueError, message):
                        reviewed.verify(fixture.root, sha, baseline=fixture.base, check_active=lambda: None)


if __name__ == '__main__':
    unittest.main()
