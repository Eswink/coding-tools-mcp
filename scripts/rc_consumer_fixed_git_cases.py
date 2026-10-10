"""real native Git policy cases; synthetic source data only."""
import os
from pathlib import Path
import socket
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import exact_build_audit as exact
import rc_consumer_fixed_git as fixed
from rc_consumer_io import ConsumerError
from rc_consumer_fixtures import ConsumerFixture
from rc_consumer_git_test_support import git, source, sentinel, verify_fixture, record_git, reaped, TARGET


class FixedGitCases(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='fixed-git-case-')
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.root, self.sha = source(self.parent)
        self.config = self.root / '.git/config'
        self.original = self.config.read_bytes()
        self.helper, self.marker = sentinel(self.parent)

    def identity(self, **kwargs):
        return exact.source_identity(self.root, self.sha, '1.2.3-rc.4', TARGET,
                                     check_active=lambda: None, **kwargs)

    def rejected(self, tail, code='unsupported_git_configuration'):
        self.config.write_bytes(self.original + tail)
        with record_git() as seen, self.assertRaisesRegex(ConsumerError, '^' + code + '$'):
            self.identity()
        self.assertFalse(self.marker.exists())
        self.assertLessEqual(len(seen.calls), 1)
        reaped(self, seen.children) if seen.children else None
        self.config.write_bytes(self.original)

    def test_real_six_commands_exact_order_and_fixed_child_launch(self):
        other = self.parent / 'bundle-fixture'; other.mkdir()
        f = ConsumerFixture(other)
        with record_git() as seen:
            actual = verify_fixture(f, check_active=lambda: None)
        self.assertEqual(actual['sha'], f.sha)
        suffixes = [('config', '--null', '--no-includes'), ('rev-parse', 'HEAD'),
            ('ls-files', '--stage', '-z', '--no-recurse-submodules'),
            ('status', '--porcelain', '--untracked-files=all'), ('rev-parse', 'HEAD^{tree}'), ('ls-files',)]
        self.assertEqual(len(seen.calls), 6)
        for (argv, kwargs), suffix in zip(seen.calls, suffixes):
            self.assertEqual(argv[0], '/usr/bin/git')
            self.assertTrue(all(option in argv for option in fixed.PREFIX))
            self.assertIn(suffix[0], argv)
            index = argv.index(suffix[0])
            self.assertEqual(argv[index:index + len(suffix)], suffix)
            self.assertEqual(kwargs['env'], fixed.ENV)
            self.assertEqual((kwargs['cwd'], kwargs['bufsize'], kwargs['shell']), ('/', 0, False))
        self.assertNotIn('--git-dir=', ' '.join(seen.calls[0][0]))
        self.assertEqual(len(seen.calls[0][1]['pass_fds']), 1)
        reaped(self, seen.children)

    def test_legacy_default_execute_shape_and_no_clock(self):
        original, calls = exact.execute, []
        def execute(command, root, env=None):
            calls.append((command, root, env))
            return original(command, root, env)
        with patch.object(exact, 'execute', side_effect=execute), \
             patch.object(fixed, 'Reader', side_effect=AssertionError('default must not activate')), \
             patch.object(fixed.time, 'monotonic', side_effect=AssertionError('no default clock')):
            value = exact.source_identity(self.root, self.sha, '1.2.3-rc.4', TARGET)
        self.assertEqual(value['sha'], self.sha)
        self.assertEqual([row[0] for row in calls], [['git', 'rev-parse', 'HEAD'],
            ['git', 'status', '--porcelain', '--untracked-files=all'], ['git', 'rev-parse', 'HEAD^{tree}']])
        self.assertTrue(all(row[2] is None for row in calls))

    def test_dirty_tracked_staged_untracked_and_ignored_semantics(self):
        path = self.root / 'tracked'
        for staged in (False, True):
            path.write_text('dirty\n')
            if staged: git(self.root, 'add', 'tracked')
            with self.assertRaisesRegex(exact.EvidenceError, '^unclean_source$'): self.identity()
            git(self.root, 'reset', '--hard', '-q', self.sha)
        untracked = self.root / 'untracked'; untracked.write_text('untracked')
        with self.assertRaisesRegex(exact.EvidenceError, '^unclean_source$'): self.identity()
        untracked.unlink()
        (self.root / '.git/info/exclude').write_text('ignored\n')
        (self.root / 'ignored').write_text('ignored')
        self.assertEqual(self.identity()['sha'], self.sha)
        self.assertEqual(exact.source_identity(self.root, self.sha, '1.2.3-rc.4', TARGET)['sha'], self.sha)

    def test_wrong_head_precedes_index_and_status_but_follows_config(self):
        git(self.root, 'update-index', '--add', '--cacheinfo', '160000,' + self.sha + ',sub')
        with record_git() as seen, self.assertRaisesRegex(exact.EvidenceError, '^wrong_checkout_sha$'):
            exact.source_identity(self.root, 'f' * 40, '1.2.3-rc.4', TARGET, check_active=lambda: None)
        self.assertEqual(len(seen.calls), 2)
        self.config.write_bytes(self.original + b'\n[include]\npath=/does/not/exist\n')
        with self.assertRaisesRegex(ConsumerError, '^unsupported_git_configuration$'):
            exact.source_identity(self.root, 'f' * 40, '1.2.3-rc.4', TARGET, check_active=lambda: None)

    def test_unknown_duplicate_and_native_multiline_config_fail_closed(self):
        for tail in (b'\n[core]\nunknown=yes\n', b'\n[core]\nbare=false\n',
                     b'\n[user]\nname="ok\\ncore.bare\\ntrue"\n', b'\n[user]\nname\n'):
            with self.subTest(tail=tail): self.rejected(tail)
        self.config.write_bytes(self.original + b'\n[user]\nname="Fixture # quoted"\nemail=fixture@example.invalid\n')
        self.assertEqual(self.identity()['sha'], self.sha)

    def test_include_filter_fsmonitor_pager_and_hook_sentinels_never_execute(self):
        h = str(self.helper).encode()
        included = self.parent / 'included'
        included.write_bytes(b'[core]\nfsmonitor=' + h + b'\n')
        cases = [b'[include]\npath=' + str(included).encode(),
            b'[includeIf "gitdir:*"]\npath=' + str(included).encode(),
            b'[filter "attack"]\nclean=' + h, b'[filter "attack"]\nprocess=' + h,
            b'[core]\nfsmonitor=' + h, b'[core]\nhooksPath=' + h,
            b'[core]\npager=' + h, b'[pager]\nstatus=' + h,
            b'[diff "attack"]\ntextconv=' + h]
        (self.root / '.git/info/attributes').write_text('tracked filter=attack diff=attack\n')
        for tail in cases:
            with self.subTest(tail=tail): self.rejected(b'\n' + tail + b'\n')

    def test_credentials_remapping_submodules_and_extensions_are_rejected(self):
        h = str(self.helper).encode()
        for tail in (b'[credential]\nhelper=' + h, b'[core]\naskPass=' + h,
            b'[core]\nsshCommand=' + h, b'[url "ext::' + h + b'"]\ninsteadOf=https://',
            b'[submodule "sub"]\nupdate=!' + h, b'[submodule]\nrecurse=true',
            b'[extensions]\nobjectformat=sha256', b'[extensions]\nworktreeconfig=true',
            b'[extensions]\nrefstorage=reftable', b'[core]\nworktree=/tmp/other',
            b'[core]\nattributesFile=/tmp/other', b'[core]\nexcludesFile=/tmp/other',
            b'[core]\nsparseCheckout=true', b'[alias]\nstatus=!' + h):
            with self.subTest(tail=tail): self.rejected(b'\n' + tail + b'\n')

    def test_inherited_git_loader_path_and_credential_environment_is_absent(self):
        bad = {'PATH': str(self.parent), 'GIT_EXEC_PATH': str(self.parent), 'GIT_PAGER': str(self.helper),
            'PAGER': str(self.helper), 'GIT_ASKPASS': str(self.helper), 'SSH_ASKPASS': str(self.helper),
            'GIT_SSH_COMMAND': str(self.helper), 'LD_PRELOAD': str(self.helper),
            'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'core.fsmonitor',
            'GIT_CONFIG_VALUE_0': str(self.helper), 'GIT_INDEX_FILE': '/missing',
            'GIT_OBJECT_DIRECTORY': '/missing', 'GIT_ALTERNATE_OBJECT_DIRECTORIES': '/missing',
            'GIT_DIR': '/missing', 'GIT_WORK_TREE': '/missing', 'GH_TOKEN': 'synthetic-only'}
        (self.parent / 'git').symlink_to(self.helper)
        with patch.dict(os.environ, bad, clear=True), record_git() as seen:
            self.identity()
        self.assertTrue(seen.calls)
        self.assertTrue(all(kwargs['env'] == fixed.ENV for _, kwargs in seen.calls))
        self.assertFalse(self.marker.exists())
        reaped(self, seen.children)

    def test_gitlink_and_nonzero_stages_reject_before_status(self):
        sub = self.root / 'sub'; sub.mkdir()
        git(sub, 'init', '-q')
        (sub / '.git/config').write_bytes(b'[core]\nrepositoryformatversion=0\nbare=false\nfsmonitor=' + str(self.helper).encode() + b'\n')
        git(self.root, 'update-index', '--add', '--cacheinfo', '160000,' + self.sha + ',sub')
        with record_git() as seen, self.assertRaisesRegex(ConsumerError, '^unsupported_git_index$'): self.identity()
        self.assertEqual(len(seen.calls), 3)
        self.assertFalse(self.marker.exists())
        git(self.root, 'reset', '--hard', '-q', self.sha)
        blob = git(self.root, 'rev-parse', 'HEAD:tracked')
        git(self.root, 'update-index', '--index-info', input=f'100644 {blob} 1\ttracked\n'.encode())
        with record_git() as seen, self.assertRaisesRegex(ConsumerError, '^unsupported_git_index$'): self.identity()
        self.assertEqual(len(seen.calls), 3)

    def test_promisor_missing_objects_and_denied_protocol_never_connect(self):
        with socket.socket() as server:
            server.bind(('127.0.0.1', 0)); server.listen(); server.settimeout(0.05)
            url = f'http://127.0.0.1:{server.getsockname()[1]}/objects'.encode()
            for tail in (b'[remote "origin"]\nurl=' + url + b'\npromisor=true\n',
                         b'[extensions]\npartialClone=origin\n'):
                self.rejected(b'\n' + tail)
            marker = self.root / '.git/objects/pack' / ('pack-' + '0' * 40 + '.promisor')
            marker.write_bytes(b'')
            with self.assertRaisesRegex(ConsumerError, '^unsupported_git_metadata$'): self.identity()
            marker.unlink()
            self.config.write_bytes(self.original + b'\n[remote "origin"]\nurl=' + url + b'\n')
            commit = self.root / '.git/objects' / self.sha[:2] / self.sha[2:]
            commit.unlink()
            with self.assertRaisesRegex(exact.EvidenceError, '^git_identity_unavailable$'): self.identity()
            with self.assertRaises(TimeoutError): server.accept()
        self.assertFalse(self.marker.exists())

    def test_alternates_grafts_indirection_symlinks_and_unknown_metadata_reject(self):
        original, root_info = os.fstat, os.stat('/')
        def nonroot(fd):
            info = original(fd)
            if (info.st_dev, info.st_ino) == (root_info.st_dev, root_info.st_ino):
                fields = {name: getattr(info, name) for name in dir(info) if name.startswith('st_')}
                return SimpleNamespace(**(fields | {'st_uid': 1}))
            return info
        with patch.object(fixed.os, 'fstat', side_effect=nonroot), record_git() as seen:
            with self.assertRaisesRegex(ConsumerError, '^unsupported_git_metadata$'): self.identity()
        self.assertEqual(seen.calls, [])
        for name in ('objects/unknown-root-file', 'objects/info/alternates', 'objects/info/http-alternates', 'info/grafts',
                     'commondir', 'config.worktree', 'sharedindex.' + '0' * 40):
            path = self.root / '.git' / name
            path.write_text('/outside\n')
            with self.subTest(name=name), record_git() as seen, self.assertRaisesRegex(ConsumerError, '^unsupported_git_metadata$'):
                self.identity()
            self.assertEqual(seen.calls, [])
            path.unlink()
        path = self.root / '.git/objects/info/linked'; path.symlink_to(self.parent)
        with self.assertRaisesRegex(ConsumerError, '^unsupported_git_metadata$'): self.identity()
        path.unlink()
        actual = self.root / '.git'; moved = self.parent / 'git-real'; actual.rename(moved)
        actual.write_text('gitdir: ' + str(moved) + '\n')
        with self.assertRaises((ConsumerError, OSError)): self.identity()

    def test_replace_refs_ignored_and_config_size_limits_are_inclusive(self):
        baseline = self.identity()['tree']
        git(self.root, 'replace', self.sha, self.sha)
        self.assertEqual(self.identity()['tree'], baseline)
        self.config.write_bytes(self.original + b'\n#' + b'x' * (fixed.CONFIG_LIMIT - len(self.original) - 2))
        self.assertEqual(self.config.stat().st_size, fixed.CONFIG_LIMIT)
        self.assertEqual(self.identity()['tree'], baseline)
        self.config.write_bytes(self.config.read_bytes() + b'x')
        with self.assertRaisesRegex(ConsumerError, '^unsupported_git_metadata$'): self.identity()
