"""Synthetic exact-scope/lineage adversaries; no live API or repository writes.

Only TemporaryDirectory Git fixtures are mutated. Real checkout tests are read-only
and do not claim that an incomplete working increment is a passing candidate.
"""
from dataclasses import asdict, replace
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import rc_pretag_metadata_source as source


def blob(data):
    return source.object_hash(b'blob', data)


def entry(path, data=b'unchanged\n', mode='100644'):
    return source.Entry(path, mode, blob(data))


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.base = (entry('baseline/a'), entry('baseline/b'), entry('root.txt'),
                     entry(source.GUARD_PATH))
        self.added = tuple(entry(path, path.encode()) for path in source.ADDITIONS)
        self.guard = source.Entry(source.GUARD_PATH, '100644', source.GUARD_BLOB)
        self.candidate = self.base[:-1] + (self.guard,) + self.added
        self.options = dict(expected_base_tree=source.tree_hash(self.base),
            expected_candidate_tree=source.tree_hash(self.candidate), expected_base_count=4)

    def check(self, candidate=None, base=None, **options):
        return source.validate_inventory(self.base if base is None else base,
            self.candidate if candidate is None else candidate, **(self.options | options))

    def rejected(self, candidate=None, base=None, **options):
        with self.assertRaises(source.SourceVerificationError):
            self.check(candidate, base, **options)

    def test_positive_exact_paths_blobs_modes(self):
        self.assertEqual(self.check(), source.ADDITIONS)
        self.assertEqual(len(source.ADDITIONS), 16)
        self.assertEqual(sum(p.endswith('.py') for p in source.ADDITIONS), 12)

    def test_all_1628_predecessors_are_checked(self):
        base = tuple(entry('baseline/%04d' % i) for i in range(1627)) + (self.base[-1],)
        candidate = base[:-1] + (self.guard,) + self.added
        options = dict(expected_base_tree=source.tree_hash(base),
            expected_candidate_tree=source.tree_hash(candidate), expected_base_count=1628)
        self.assertEqual(self.check(candidate, base, **options), source.ADDITIONS)
        for i in range(1628):
            with self.subTest(index=i):
                changed = candidate[:i] + (replace(candidate[i], oid='f' * 40),) + candidate[i+1:]
                self.rejected(changed, base, **options)

    def test_each_missing_and_substituted_addition_fails(self):
        for i, item in enumerate(self.added, len(self.base)):
            with self.subTest(path=item.path):
                self.rejected(self.candidate[:i] + self.candidate[i+1:])
                self.rejected(self.candidate[:i] + (replace(item, path='substituted.py'),)
                              + self.candidate[i+1:])

    def test_each_addition_changed_content_fails_expected_tree(self):
        for i, item in enumerate(self.added, len(self.base)):
            with self.subTest(path=item.path):
                self.rejected(self.candidate[:i] + (replace(item, oid='f' * 40),)
                              + self.candidate[i+1:])

    def test_each_predecessor_missing_substituted_or_changed_fails(self):
        for i, item in enumerate(self.base):
            for replacement in ((), (replace(item, path='different'),),
                                (replace(item, oid='e' * 40),)):
                with self.subTest(path=item.path, replacement=replacement):
                    self.rejected(self.candidate[:i] + replacement + self.candidate[i+1:])

    def test_every_path_rejects_mode_substitutions(self):
        for i, item in enumerate(self.candidate):
            for mode in ('100755', '120000', '160000', '040000', '100664', 100644):
                with self.subTest(path=item.path, mode=mode):
                    self.rejected(self.candidate[:i] + (replace(item, mode=mode),)
                                  + self.candidate[i+1:])

    def test_guard_is_one_exact_required_replacement(self):
        self.assertEqual(source.GUARD_PATH, 'scripts/rc_publication_boundary_tests.py')
        self.assertEqual(source.GUARD_BLOB, '85627ca59cc6b7d700af30867c1e7aa0c8fb547f')
        for guard in (self.base[-1], replace(self.guard, oid='e' * 40)):
            self.rejected(self.base[:-1] + (guard,) + self.added)
        no_guard = self.base[:-1]
        self.rejected(no_guard + self.added, no_guard, expected_base_count=3,
                      expected_base_tree=source.tree_hash(no_guard),
                      expected_candidate_tree=source.tree_hash(no_guard + self.added))

    def test_extra_duplicate_and_conflicting_paths_fail(self):
        for item in (entry('arbitrary-extra'), self.candidate[0],
                     replace(self.candidate[0], oid='a' * 40), entry('baseline/a/child')):
            self.rejected(self.candidate + (item,))

    def test_strict_paths_and_hashes(self):
        for path in ('', '/root', '../x', 'a/../b', './a', 'a//b', 'a/', 'a\\b',
                     'a\tb', 'a\nb', '.git/config', 'a/.GIT/x', 'a\0b', 'a' * 513, '\ud800'):
            with self.subTest(path=path):
                self.rejected((replace(self.candidate[0], path=path),) + self.candidate[1:])
        for oid in ('A' * 40, 'g' * 40, 'a' * 39, 'a' * 41, True, None):
            self.rejected((replace(self.candidate[0], oid=oid),) + self.candidate[1:])

    def test_base_and_candidate_tree_and_count_are_exact(self):
        for options in ({'expected_base_tree': 'a' * 40},
                        {'expected_candidate_tree': 'a' * 40},
                        {'expected_base_count': 2}, {'expected_base_count': True}):
            self.rejected(**options)
        self.rejected(base=(replace(self.base[0], oid='a' * 40),) + self.base[1:])

    def test_addition_must_be_absent_from_base_and_unique(self):
        self.rejected(expected_additions=source.ADDITIONS + (source.ADDITIONS[0],))
        self.rejected(expected_additions=source.ADDITIONS + ('root.txt',))

    def test_count_only_same_size_inventory_is_rejected(self):
        self.rejected(tuple(entry('unrelated/%02d' % i) for i in range(len(self.candidate))))

    def test_parser_rejects_malformed_duplicate_nonblob_and_unmerged(self):
        good = b'100644 blob ' + b'a' * 40 + b'\ta\0'
        self.assertEqual(source.parse_inventory(good), (source.Entry('a', '100644', 'a'*40),))
        for raw in (b'', b'\0', good[:-1], good + good, good.replace(b'blob', b'tree'),
                    good.replace(b'\ta', b'\t\xff'), good.replace(b'blob ', b'blob  ')):
            with self.assertRaises(source.SourceVerificationError):
                source.parse_inventory(raw)
        for stage in (b'1', b'2', b'3', b'00'):
            with self.assertRaises(source.SourceVerificationError):
                source.parse_inventory(b'100644 ' + b'a'*40 + b' ' + stage + b'\ta\0', index=True)

    def test_parser_and_inventory_bounds(self):
        with self.assertRaises(source.SourceVerificationError):
            source.parse_inventory(b'x' * (source.MAX_OUTPUT + 1))
        with self.assertRaises(source.SourceVerificationError):
            source.inventory([entry(str(i)) for i in range(source.MAX_ENTRIES + 1)])


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='metadata-source-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = {'PATH': '/usr/bin:/bin', 'HOME': str(self.root), 'LC_ALL': 'C',
            'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
            'GIT_AUTHOR_NAME': 'Fixture', 'GIT_AUTHOR_EMAIL': 'fixture@example.invalid',
            'GIT_COMMITTER_NAME': 'Fixture', 'GIT_COMMITTER_EMAIL': 'fixture@example.invalid'}
        self.git('init', '-q')
        self.write('baseline/a', b'a\n')
        self.write('root.txt', b'root\n')
        self.write(source.GUARD_PATH, b'synthetic old guard\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'Synthetic baseline')
        self.base = self.git('rev-parse', 'HEAD').decode().strip()
        self.base_tree = self.git('rev-parse', 'HEAD^{tree}').decode().strip()
        for path in source.ADDITIONS:
            self.write(path, path.encode() + b'\n')
        self.write(source.GUARD_PATH, b'synthetic approved guard\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'Synthetic published parent')
        self.parent = self.git('rev-parse', 'HEAD').decode().strip()
        self.parent_tree = self.git('rev-parse', 'HEAD^{tree}').decode().strip()
        self.pins = mock.patch.multiple(source, BASE_SHA=self.base, BASE_TREE=self.base_tree,
            BASE_COUNT=3, GUARD_BLOB=blob(b'synthetic approved guard\n'),
            PARENT_SHA=self.parent, PARENT_TREE=self.parent_tree)
        self.pins.start()
        self.addCleanup(self.pins.stop)
        self.write('scripts/rc_pretag_metadata_live.py', b'synthetic diagnostic correction\n')
        self.git('add', '.')
        self.prospective = self.git('write-tree').decode().strip()  # Test fixture only.
        self.git('commit', '-qm', 'Synthetic candidate')
        self.candidate = self.git('rev-parse', 'HEAD').decode().strip()

    def git(self, *args):
        return subprocess.check_output(['/usr/bin/git', *args], cwd=self.root,
            env=self.env, stderr=subprocess.DEVNULL, timeout=5)

    def write(self, path, data):
        file = self.root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(data)

    def verify(self, **kwargs):
        return source.verify_source(self.root, self.candidate, **kwargs)

    def test_positive_committed_exact_one_parent(self):
        result = self.verify(expected_tree=self.prospective)
        self.assertEqual((result.mode, result.source_sha, result.source_tree),
                         ('committed', self.candidate, self.prospective))
        self.assertEqual((result.parent_sha, result.parent_tree), (self.parent, self.parent_tree))
        self.assertEqual((result.baseline_sha, result.baseline_tree), (self.base, self.base_tree))
        self.assertEqual(result.predecessor_count, 3)
        self.assertEqual(result.unchanged_predecessor_count, 2)
        self.assertEqual(result.guard_path, source.GUARD_PATH)
        self.assertEqual(result.guard_blob, source.GUARD_BLOB)
        for key in ('release_approved', 'publish_approved', 'security_approved',
                    'snapshot_atomic', 'published_candidate'):
            self.assertIs(asdict(result)[key], False)
        with self.assertRaises(ValueError):
            replace(result, release_approved=True)

    def test_positive_staged_is_only_prospective(self):
        self.git('reset', '--soft', self.parent)
        result = source.verify_source(self.root, self.parent, staged=True,
                                      expected_tree=self.prospective)
        self.assertEqual(result.mode, 'prospective_index')
        self.assertEqual(result.source_sha, self.parent)
        self.assertFalse(result.published_candidate)
        self.assertEqual(self.git('rev-parse', 'HEAD').decode().strip(), self.parent)

    def test_production_gate_does_not_mutate_index_objects_or_files(self):
        def snapshot():
            return {str(p.relative_to(self.root)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in self.root.rglob('*') if p.is_file()}
        before = snapshot()
        self.verify()
        self.assertEqual(before, snapshot())

    def test_git_tree_calculation_matches_actual_git(self):
        entries = source.parse_inventory(self.git('ls-tree', '-rz', self.candidate))
        self.assertEqual(source.tree_hash(entries), self.prospective)

    def test_wrong_expected_source_tree_and_staged_head(self):
        for call in (lambda: source.verify_source(self.root, self.base),
                     lambda: self.verify(expected_tree='a' * 40),
                     lambda: self.verify(staged=True)):
            with self.assertRaises(source.SourceVerificationError):
                call()

    def test_wrong_pinned_base_sha_or_tree(self):
        for changes in ({'BASE_SHA': 'a' * 40}, {'BASE_TREE': 'a' * 40},
                        {'PARENT_SHA': 'a' * 40}, {'PARENT_TREE': 'a' * 40}):
            with mock.patch.multiple(source, **changes):
                with self.assertRaises(source.SourceVerificationError):
                    self.verify()

    def test_published_parent_requires_exact_sole_baseline_parent(self):
        for parents in ((), (self.candidate,), (self.base, self.candidate)):
            arguments = [item for parent in parents for item in ('-p', parent)]
            sha = self.git('commit-tree', self.parent_tree, *arguments,
                           '-m', 'Synthetic wrong published lineage').decode().strip()
            with mock.patch.object(source, 'PARENT_SHA', sha), self.assertRaisesRegex(
                    source.SourceVerificationError, 'published_parent_lineage_mismatch'):
                self.verify()

    def test_candidate_cannot_skip_published_parent_or_stage_on_baseline(self):
        sha = self.git('commit-tree', self.prospective, '-p', self.base,
                       '-m', 'Synthetic skipped published parent').decode().strip()
        self.git('reset', '--hard', sha)
        with self.assertRaisesRegex(source.SourceVerificationError, 'candidate_parent_mismatch'):
            source.verify_source(self.root, sha)
        self.git('reset', '--soft', self.base)
        with self.assertRaisesRegex(source.SourceVerificationError, 'staged_head_mismatch'):
            source.verify_source(self.root, self.base, staged=True)

    def test_candidate_cannot_use_same_tree_alternate_published_commit(self):
        alternate = self.git('commit-tree', self.parent_tree, '-p', self.base,
                             '-m', 'Synthetic alternate parent identity').decode().strip()
        sha = self.git('commit-tree', self.prospective, '-p', alternate,
                       '-m', 'Synthetic candidate on alternate parent').decode().strip()
        self.git('reset', '--hard', sha)
        with self.assertRaisesRegex(source.SourceVerificationError, 'candidate_parent_mismatch'):
            source.verify_source(self.root, sha)

    def test_dirty_bytes_in_every_predecessor_and_addition(self):
        for path in ('baseline/a', 'root.txt', source.GUARD_PATH, *source.ADDITIONS):
            file = self.root / path
            original = file.read_bytes()
            try:
                file.write_bytes(original + b'dirty')
                with self.subTest(path=path), self.assertRaisesRegex(
                        source.SourceVerificationError, 'working_bytes_mismatch'):
                    self.verify()
            finally:
                file.write_bytes(original)

    def test_dirty_mode_in_every_predecessor_and_addition(self):
        for path in ('baseline/a', 'root.txt', source.GUARD_PATH, *source.ADDITIONS):
            file = self.root / path
            try:
                file.chmod(0o755)
                with self.subTest(path=path), self.assertRaisesRegex(
                        source.SourceVerificationError, 'working_mode_mismatch'):
                    self.verify()
            finally:
                file.chmod(0o644)

    def test_symlink_file_and_ancestor_are_rejected(self):
        file = self.root / 'root.txt'
        file.unlink()
        file.symlink_to('baseline/a')
        with self.assertRaises(source.SourceVerificationError):
            self.verify()
        file.unlink()
        self.write('root.txt', b'root\n')
        folder = self.root / 'baseline'
        folder.rename(self.root / 'moved-baseline')
        folder.symlink_to('moved-baseline', target_is_directory=True)
        with self.assertRaises(source.SourceVerificationError):
            self.verify()

    def test_fifo_and_directory_are_rejected_without_blocking(self):
        file = self.root / 'root.txt'
        file.unlink()
        os.mkfifo(file)
        with self.assertRaises(source.SourceVerificationError):
            self.verify()
        file.unlink()
        file.mkdir()
        with self.assertRaises(source.SourceVerificationError):
            self.verify()

    def test_deleted_working_file_and_oversized_file_fail(self):
        file = self.root / 'root.txt'
        file.unlink()
        with self.assertRaises(source.SourceVerificationError):
            self.verify()
        file.write_bytes(b'x' * (source.MAX_FILE + 1))
        with self.assertRaisesRegex(source.SourceVerificationError, 'working_file_limit'):
            self.verify()

    def test_dirty_index_is_rejected(self):
        self.write('root.txt', b'changed\n')
        self.git('add', 'root.txt')
        self.write('root.txt', b'root\n')
        with self.assertRaisesRegex(source.SourceVerificationError, 'index_mismatch'):
            self.verify()

    def test_extra_path_committed_or_missing_staged_is_rejected(self):
        self.write('unexpected.py', b'extra\n')
        self.git('add', '.')
        self.git('commit', '--amend', '--no-edit', '-q')
        sha = self.git('rev-parse', 'HEAD').decode().strip()
        with self.assertRaisesRegex(source.SourceVerificationError, 'candidate_paths_mismatch'):
            source.verify_source(self.root, sha)
        self.git('reset', '--hard', self.candidate)
        self.git('reset', '--soft', self.parent)
        self.git('rm', '--cached', source.ADDITIONS[0])
        with self.assertRaisesRegex(source.SourceVerificationError, 'candidate_paths_mismatch'):
            source.verify_source(self.root, self.parent, staged=True)

    def test_same_tree_extra_parent_fails(self):
        sha = self.git('commit-tree', self.prospective, '-p', self.parent,
                       '-p', self.candidate, '-m', 'Synthetic multiparent').decode().strip()
        self.git('reset', '--hard', sha)
        with self.assertRaisesRegex(source.SourceVerificationError, 'candidate_parent_mismatch'):
            source.verify_source(self.root, sha)

    def test_intermediate_change_then_revert_same_tree_fails(self):
        self.write('root.txt', b'intermediate edit\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'Synthetic intermediate edit')
        self.write('root.txt', b'root\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'Synthetic revert')
        sha = self.git('rev-parse', 'HEAD').decode().strip()
        self.assertEqual(self.git('rev-parse', 'HEAD^{tree}').decode().strip(), self.prospective)
        with self.assertRaisesRegex(source.SourceVerificationError, 'candidate_parent_mismatch'):
            source.verify_source(self.root, sha)

    def test_replace_ref_cannot_hide_intermediate_history(self):
        self.git('commit', '--allow-empty', '-qm', 'Synthetic extra history')
        sha = self.git('rev-parse', 'HEAD').decode().strip()
        self.git('replace', sha, self.candidate)
        with self.assertRaisesRegex(source.SourceVerificationError, 'candidate_parent_mismatch'):
            source.verify_source(self.root, sha)

    def test_noncontiguous_parent_headers_cannot_forge_lineage(self):
        author = b'author Fixture <fixture@example.invalid> 1000000000 +0000\n'
        committer = author.replace(b'author ', b'committer ')
        parent = b'parent ' + self.parent.encode() + b'\n'
        for headers in (author + parent + committer, author + committer + parent,
                        author + committer + b'encoding UTF-8\n' + parent):
            raw = b'tree ' + self.prospective.encode() + b'\n' + headers + b'\nSynthetic\n'
            sha = subprocess.check_output(['/usr/bin/git', 'hash-object', '--literally',
                '-t', 'commit', '-w', '--stdin'], input=raw, cwd=self.root,
                env=self.env, stderr=subprocess.DEVNULL, timeout=5).decode().strip()
            self.assertEqual(self.git('rev-list', '--parents', '--no-walk', sha).strip(), sha.encode())
            self.git('update-ref', 'HEAD', sha)
            with self.assertRaisesRegex(source.SourceVerificationError, 'invalid_commit_header_order'):
                source.verify_source(self.root, sha)


class GitBoundsTests(unittest.TestCase):
    def test_fixed_allowlist_and_sha_prevent_command_injection(self):
        reader = source.GitReader('.')
        for operation, oid in (('fetch', None), ('commit', '--all'),
                               ('tree', 'HEAD'), ('head', 'a'*40)):
            with self.assertRaises(source.SourceVerificationError):
                reader.read(operation, oid)

    def test_command_limit_and_overall_timeout(self):
        reader = source.GitReader('.')
        reader.commands = source.MAX_COMMANDS
        with self.assertRaisesRegex(source.SourceVerificationError, 'git_command_limit'):
            reader.read('head')
        reader.deadline = 0
        with self.assertRaisesRegex(source.SourceVerificationError, 'source_timeout'):
            reader.remaining()

    def test_bounded_real_subprocess_output_and_time(self):
        original = subprocess.Popen
        for program, code in (("import os; os.write(1,b'x'*2000000)", 'git_output_limit'),
                              ('import time; time.sleep(10)', 'git_timeout')):
            processes = []
            def launch(argv, **kwargs):
                self.assertEqual(argv[0], '/usr/bin/git')
                self.assertFalse(kwargs['shell'])
                self.assertNotIn('GITHUB_TOKEN', kwargs['env'])
                process = original([sys.executable, '-I', '-S', '-c', program], **kwargs)
                processes.append(process)
                return process
            with mock.patch.object(source.subprocess, 'Popen', side_effect=launch), \
                 mock.patch.object(source, 'COMMAND_SECONDS', 0.2):
                with self.assertRaisesRegex(source.SourceVerificationError, code):
                    source.GitReader('.').read('head')
            self.assertTrue(all(p.poll() is not None for p in processes))

    def test_commit_hash_and_parent_parser(self):
        raw = b'tree ' + b'a'*40 + b'\nparent ' + b'b'*40 + b'\n\nprivate message\n'
        sha = source.object_hash(b'commit', raw)
        self.assertEqual(source.parse_commit(raw, sha), ('a'*40, ('b'*40,)))
        for data in (raw + b'x', b'x'*65537):
            with self.assertRaises(source.SourceVerificationError):
                source.parse_commit(data, sha)

    def test_cleanup_error_is_fixed_and_never_emits_source_proof(self):
        process = mock.Mock()
        process.poll.return_value = None
        process.stdout.fileno.return_value = -1
        process.kill.side_effect = OSError('private path or context')
        with mock.patch.object(source.subprocess, 'Popen', return_value=process), \
             self.assertRaisesRegex(source.SourceVerificationError, '^git_cleanup_uncertain$'):
            source.GitReader('.').read('head')

    def test_new_files_stay_below_500_lines(self):
        for name in ('rc_pretag_metadata_source.py', 'rc_pretag_metadata_source_tests.py'):
            self.assertLess(len(Path(__file__).with_name(name).read_text().splitlines()), 500)

class FailureSummaryBoundsTests(unittest.TestCase):
    def test_exact_17_plus_16_rows_fit_and_overflow_is_rejected(self):
        import json
        import rc_pretag_metadata_live as live
        from rc_pretag_metadata_fixtures import REQUEST, FixtureAPI
        from rc_pretag_metadata_types import MetadataObservation
        receipt = live.collect_metadata(REQUEST, FixtureAPI())
        changed = MetadataObservation('collection', 'changed', 'snapshot_changed', 1)
        receipt = replace(receipt, collection_status='blocked', observations=receipt.observations + (changed,))
        summary = live.failure_summary(receipt)
        self.assertEqual((len(summary['pass_a']), len(summary['pass_b'])), (17, 16))
        self.assertEqual(summary['pass_a'][-1], dict(key='collection', state='changed', reason='snapshot_changed'))
        error = dict(status='failed', code='collection_failed', stage='quality', observations=summary,
            release_approved=False, publish_approved=False, evidence_authentication='unverified')
        self.assertLessEqual(len(json.dumps(error, sort_keys=True).encode()), live.ERROR_BYTES)
        for field, values in (('observations', receipt.observations + (changed,)),
                ('revalidation_observations', receipt.revalidation_observations + (changed,))):
            forged = replace(receipt)
            object.__setattr__(forged, field, values)
            with self.subTest(field=field), self.assertRaises(ValueError):
                live.failure_summary(forged)

        oversized = replace(receipt.observations[0].records[0])
        for name in ('record_id', 'source_sha', 'name', 'state'):
            object.__setattr__(oversized, name, 'x' * 512)
        for field, value in (('records', (asdict(receipt.observations[0].records[0]),)),
                ('key', type('StringSubclass', (str,), {})('commit')), ('count', 2**63),
                ('key', 'x' * 513), ('records', tuple(range(129))), ('records', (receipt,)),
                ('records', (oversized,) * 128)):
            forged = replace(receipt)
            row = replace(receipt.observations[0])
            object.__setattr__(row, field, value)
            object.__setattr__(forged, 'observations', (row,) + receipt.observations[1:])
            with mock.patch.object(live, 'encode', side_effect=AssertionError('serialization reached')):
                with self.subTest(field=field), self.assertRaises(ValueError):
                    live.failure_summary(forged)

    def test_error_byte_cap_is_exact_and_never_truncates_or_overwrites(self):
        import rc_pretag_metadata_live as live
        self.assertEqual(live.ERROR_BYTES, 8192)
        with tempfile.TemporaryDirectory() as folder:
            fd = live.directory(Path(folder))
            try:
                raw = b'x' * live.ERROR_BYTES
                live.write(fd, 'error.json', raw, live.ERROR_BYTES)
                with self.assertRaises(ValueError):
                    live.write(fd, 'error.json', raw + b'x', live.ERROR_BYTES)
                self.assertEqual((Path(folder) / 'error.json').read_bytes(), raw)
                with self.assertRaises(FileExistsError):
                    live.write(fd, 'error.json', b'{}', live.ERROR_BYTES)
            finally:
                os.close(fd)


if __name__ == '__main__':
    unittest.main()
