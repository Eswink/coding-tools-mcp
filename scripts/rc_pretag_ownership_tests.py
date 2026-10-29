"""Issue111: exact reviewed ownership source, finite topology and failure boundaries."""
import ast
from contextlib import ExitStack, contextmanager, nullcontext
import errno
import json
import os
import stat
import subprocess
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import rc_pretag_composition_tests as c
import rc_pretag_ownership_profile as o
import rc_pretag_collect as collect
import rc_pretag_collection_result as result
import rc_pretag_collect_fixtures as fixtures
from rc_consumer_io_ownership_tests import load_current
from rc_pretag_integration_admission_profile import normalize as integration_bytes


class OwnershipCompositionTests(unittest.TestCase):
    def setUp(self):
        self.repo, _, self.commit, self.blob = self.enterContext(c._profile_fixture())
        self.good = c._entries(o.M, self.repo)
        frozen = c._entries(c.publication.N, self.repo)
        for path in o.CAPS:
            self.good[path] = frozen[path] if path in (o.CHECKS, c.publication.OWNERSHIP_TESTS) else (
                '100644', 'blob', self.blob(integration_bytes(path, (c.ROOT / path).read_bytes())))
        self.pure = self.commit([o.M], self.good)

    def content(self, ref):
        return o.content(ref, self.repo, c._git, c._entries, c._feature_profile)

    def selected(self, ref):
        return o.selected_profile(ref, self.repo, c._git, c._entries, c._feature_profile,
                                  c.RELEASE, c.RELEASE_TREE, c.RELEASE_DOCS)

    def changed(self, path, data):
        return self.good | {path: ('100644', 'blob', self.blob(data))}

    def rejects(self, parents, expected):
        bad = self.commit(parents, expected)
        self.assertEqual(c._entries(bad, self.repo), expected)
        self.assertEqual(self.content(self.pure), self.good)
        if expected != self.good:
            o.release_content(bad, self.good, self.repo, c._git, c._entries,
                              c.RELEASE, c.RELEASE_TREE, c.RELEASE_DOCS)
        else:
            self.assertEqual(self.content(bad), expected)  # Content is independently valid.
        with self.assertRaises(o.TopologyError):
            o.topology(bad, self.repo, c._git, c.RELEASE)
        with patch.object(o, 'content', side_effect=AssertionError('content must not run')) as content:
            with self.assertRaises(o.TopologyError): self.selected(bad)
            content.assert_not_called()
        return bad

    def test_exact_m_ownership_overlay_accepts_only_reviewed_delta(self):
        self.assertEqual(c._git('rev-parse', o.M + '^{tree}', root=self.repo).decode().strip(), o.M_TREE)
        self.assertEqual(self.selected(self.pure), self.good)
        self.assertEqual((len(c.ALLOWED), len(o.CAPS), len(c.ALLOWED | o.CAPS.keys())), (22, 13, 32))
        with self.assertRaises(o.TopologyError): self.selected(o.M)
        for path, pin in o.NEW_PINS.items():
            data = integration_bytes(path, (c.ROOT / path).read_bytes())
            if path == o.CHECKS: data = c.publication.timeout_inverse(path, data)
            self.assertEqual(o.pin(data), pin)

    def test_ownership_io_drift_and_reverted_handoff_reject(self):
        old = c._git('show', o.M + ':' + o.IO, root=self.repo)
        current = integration_bytes(o.IO, (c.ROOT / o.IO).read_bytes())
        mutations = [old, current + b'\n', current.replace(b'CHUNK = 64', b'CHUNK = 63')]
        for name in ('_directory', '_parent', '__init__'):
            def method(data):
                module = ast.parse(data)
                scope = module if name == '_directory' else next(n for n in module.body if isinstance(n, ast.ClassDef) and n.name == 'PrivateRoot')
                return next(n for n in scope.body if isinstance(n, ast.FunctionDef) and n.name == name)
            source, target = method(old), method(current)
            lines = current.splitlines(keepends=True)
            lines[target.lineno - 1:target.end_lineno] = old.splitlines(keepends=True)[source.lineno - 1:source.end_lineno]
            mutations.append(b''.join(lines))
        for data in mutations:
            with self.subTest(pin=o.pin(data)), self.assertRaises(AssertionError):
                self.selected(self.commit([o.M], self.changed(o.IO, data)))
        self.assertEqual(set(c.NARROW), {'scripts/rc_consumer_snapshot.py', 'scripts/rc_artifact_consumer.py'})
        with patch.object(c, '_reconstruct_snapshot', wraps=c._reconstruct_snapshot) as snapshot, \
             patch.object(c, '_reconstruct_consumer', wraps=c._reconstruct_consumer) as consumer:
            self.content(self.pure)
            snapshot.assert_called_once(); consumer.assert_called_once()
        self.assertEqual(o.outside_io(old), o.outside_io(current))

    def test_proof_bodies_live_pins_and_fixture_identity_reject_drift(self):
        o.proof_contract((c.ROOT / o.PROOF).read_bytes())
        for path in (o.PROOF, o.FIXTURE, 'scripts/rc_consumer_proof_fixtures.py',
                     'scripts/rc_consumer_default_worker_proof.py', 'scripts/rc_consumer_transport.py',
                     'scripts/rc_consumer_transport_worker.py', '.github/workflows/rc-artifact-default-worker-proof.yml', c.LIVE):
            with self.subTest(path=path), self.assertRaises(AssertionError):
                self.selected(self.commit([o.M], self.changed(path, (c.ROOT / path).read_bytes() + b'\n')))
        altered = (c.ROOT / o.PROOF).read_bytes().replace(b'def test_01_', b'def test_changed_01_', 1)
        with self.assertRaises(AssertionError): o.proof_contract(altered)

    def test_overlay_modes_paths_deletions_and_extra_sources_reject(self):
        for path in (o.IO, o.FIXTURE, 'scripts/rc_pretag_ownership_profile.py', 'unreviewed-extra.py'):
            for entry in (None, ('100755', 'blob', self.blob(b'# changed\n')), ('120000', 'blob', self.blob(b'target'))):
                changed = dict(self.good)
                if entry is None: changed.pop(path, None)
                else: changed[path] = entry
                if changed == self.good: continue
                with self.subTest(path=path, entry=entry), self.assertRaises(AssertionError):
                    self.selected(self.commit([o.M], changed))

    def test_original_adopter_and_ownership_budgets_are_separate(self):
        self.assertEqual(c._feature_profile(o.M, self.repo), c._entries(o.M, self.repo))
        data = {p: c._git('cat-file', 'blob', self.good[p][2], root=self.repo) for p in o.CAPS}
        delta = o.budgets(self.pure, self.repo, c._git, data)
        self.assertLessEqual(delta, 2200)
        path = 'scripts/rc_pretag_ownership_tests.py'
        for count, widened in ((381, False), (len(data[path].splitlines()) + 2201 - delta, True)):
            changed = dict(data); changed[path] = data[path] + b'# budget boundary\n' * (count - len(data[path].splitlines()))
            ref = self.commit([o.M], self.changed(path, changed[path]))
            caps = {p: (10000, 10000) for p in o.CAPS} if widened else o.CAPS
            with patch.object(o, 'CAPS', caps), self.assertRaises(AssertionError):
                o.budgets(ref, self.repo, c._git, changed)
        self.assertEqual(c.BUDGET['scripts/rc_pretag_composition_tests.py'], 470)

    def test_pure_candidate_chain_anchors_at_m_with_fixed_limit(self):
        self.assertEqual(self.selected(self.pure), self.good)
        tip = self.pure
        for _ in range(15): tip = self.commit([tip], self.good)
        self.assertEqual(self.selected(tip), self.good)

    def test_exact_fix_merge_has_m_then_pure_candidate(self):
        self.assertEqual(self.selected(self.commit([o.M, self.pure], self.good)), self.good)
        drift = self.changed(o.IO, b'wrong tree\n')
        with self.assertRaises(AssertionError) as failed: self.selected(self.commit([o.M, self.pure], drift))
        self.assertNotIsInstance(failed.exception, o.TopologyError)

    def test_exact_release_overlay_has_r_then_validated_nonrelease(self):
        overlay = self.good | c.RELEASE_DOCS
        fix = self.commit([o.M, self.pure], self.good)
        for second in (self.pure, fix):
            self.assertEqual(self.selected(self.commit([c.RELEASE, second], overlay)), overlay)
        for path in c.RELEASE_DOCS:
            drift = overlay | {path: ('100644', 'blob', self.blob(b'document drift\n'))}
            with self.assertRaises(AssertionError) as failed: self.selected(self.commit([c.RELEASE, self.pure], drift))
            self.assertNotIsInstance(failed.exception, o.TopologyError)

    def test_invalid_pure_topologies_reject_with_valid_trees(self):
        foreign = self.commit([], self.good)
        lookalike = self.commit([], c._entries(o.M, self.repo))
        fix = self.commit([o.M, self.pure], self.good)
        nested = self.commit([foreign, self.pure], self.good)
        tip = self.pure
        for _ in range(15): tip = self.commit([tip], self.good)
        for parents in ([], [tip], [foreign], [lookalike], [nested], [fix]): self.rejects(parents, self.good)
        with self.assertRaises(o.TopologyError): o.topology('f' * 40, self.repo, c._git, c.RELEASE)

    def test_invalid_fix_merges_reject_with_valid_trees(self):
        foreign = self.commit([], self.good)
        fix = self.commit([o.M, self.pure], self.good)
        for parents in ([self.pure, o.M], [o.M, self.pure, foreign], [foreign, self.pure],
                        [o.M, fix], [o.M, o.M], [o.M, foreign]): self.rejects(parents, self.good)

    def test_invalid_release_overlays_reject_with_valid_trees(self):
        overlay = self.good | c.RELEASE_DOCS
        release = self.commit([c.RELEASE, self.pure], overlay)
        foreign = self.commit([], self.good)
        lookalike = self.commit([], c._entries(c.RELEASE, self.repo))
        fix = self.commit([o.M, self.pure], self.good)
        nested = self.commit([o.M, fix], self.good)
        for parents in ([self.pure, c.RELEASE], [c.RELEASE, self.pure, o.M], [lookalike, self.pure],
                        [c.RELEASE, release], [c.RELEASE, foreign], [c.RELEASE, nested]): self.rejects(parents, overlay)


class OwnershipFailureBoundaryTests(unittest.TestCase):
    SECRET = 'synthetic-private-path-token'

    @contextmanager
    def inert(self, io):
        source = SimpleNamespace(source_sha='a' * 40, repository_id=1)
        selection = {'final_packaging': {'run': {'head_branch': 'fixture'}}}
        with ExitStack() as stack:
            for module, name, value in ((collect.admission, 'admit', SimpleNamespace(source=source)),
                (collect.admission, 'discover', {'artifact_id': 1}), (collect.admission, 'branch', None),
                (collect.admission, 'projection', {}), (collect.snapshot, '_select_source_runs_for_identity', selection),
                (collect.snapshot, 'authenticate_bundle_metadata', {}), (collect.snapshot, 'derive_final_producer', object()),
                (collect.snapshot, 'resolve_candidate', {}), (collect.snapshot, 'select_source_runs', selection)):
                stack.enter_context(patch.object(module, name, return_value=value))
            stopped = [stack.enter_context(patch.object(module, name)) for module, name in
                ((collect.consumer, '_verify_bundle_bytes'), (result, '_summarize'), (result, '_collect'),
                 (collect.admission, 'revalidate'), (collect, '_handoff'), (io.PrivateRoot, '__enter__'), (io.PrivateRoot, 'open'))]
            stack.enter_context(patch.object(collect, 'private_io', io))
            stack.enter_context(patch.object(collect, 'os', io.os))
            yield stopped
            for action in stopped: action.assert_not_called()

    def bounded(self, failure, stage):
        data = json.loads(failure.encode())
        self.assertEqual(data['stage'], stage)
        self.assertFalse(data['passed']); self.assertFalse(data['cleanup_confirmed'])
        self.assertTrue(all(data[key] is False for key in result.FALSE_FLAGS))
        self.assertNotIn(self.SECRET, failure.encode().decode())
        self.assertLessEqual(len(failure.encode()), result.FAILURE_LIMIT)
        return data

    def test_actual_directory_fault_blocks_collection_observation(self):
        io = load_current(); io.os.close_faults[100] = (OSError(self.SECRET), True, True)
        with self.inert(io), self.assertRaises(result.Failure) as failed:
            collect.collect(Path('/source'), {'RUNNER_TEMP': '/owned'}, Mock())
        self.assertEqual(io.os.attempts, [100, 101])
        self.assertEqual(io.os.opens, 2); self.assertFalse(io.os.foreign_closed)
        self.bounded(failed.exception, 'output')

    def test_actual_handoff_walk_fault_preserves_uncertainty(self):
        io = load_current(); io.os.close_faults[100] = (OSError(self.SECRET), False, False)
        with patch.object(collect, 'private_io', io), patch.object(collect, 'os', io.os):
            with self.assertRaises(OSError) as failed:
                collect._handoff(Path('/owned') / result.NAME, '/owned', {'GITHUB_OUTPUT': '/owned/control'})
        self.assertEqual(io.os.attempts, [100, 101])
        self.assertEqual(io.os.opens, 2); self.assertFalse(io.os.foreign_closed)
        self.bounded(result.Failure('output_handoff', failed.exception), 'output_handoff')
        sticky = result.Failure('transport', collect.consumer.ConsumerError('transport_cleanup_uncertain'))
        sticky.record('output_handoff', failed.exception); sticky.record('output', OSError(self.SECRET))
        data = self.bounded(sticky, 'transport')
        self.assertEqual((data['error_code'], data['terminal_state']), ('transport_cleanup_uncertain', 'unknown'))
        self.assertIn('pretag_output_handoff_failed', data['secondary_error_codes'])

    def test_actual_constructor_fault_blocks_collect_and_emit(self):
        for caller in ('collect', 'emit', 'consumer'):
            for fault in ('identity', 'parent_close', 'root_cleanup'):
                io = load_current()
                if fault != 'parent_close': io.os.identity_faults[101] = io.ConsumerError('unsafe_private_directory')
                if fault == 'parent_close': io.os.close_faults[100] = (OSError(self.SECRET), True, True)
                if fault == 'root_cleanup': io.os.close_faults[101] = (OSError(self.SECRET), False, False)
                with self.subTest(caller=caller, fault=fault), self.inert(io), \
                     patch.object(collect, '_temporary', return_value='/'), patch.object(result, 'encode', return_value=b'{}'), \
                     patch.object(collect.consumer, 'PrivateRoot', io.PrivateRoot):
                    with self.assertRaises((result.Failure, io.ConsumerError)) as failed:
                        if caller == 'collect': collect.collect(Path('/source'), {}, Mock())
                        elif caller == 'emit': collect.emit(object(), Path('/source'), {})
                        else: collect.consumer.consume(Path('/source'), {'artifact_id': 1}, {}, Mock(), temporary_parent='/')
                self.assertEqual(io.os.attempts, [100, 101] if fault == 'parent_close' else [101, 100])
                self.assertEqual(io.os.opens, 2); self.assertFalse(io.os.foreign_closed)
                failure = failed.exception if isinstance(failed.exception, result.Failure) else result.Failure('output', failed.exception)
                self.bounded(failure, 'output')


class FixtureMetadataTests(unittest.TestCase):
    from rc_pretag_collection_tests import fixture_git_test_setup as setUp

    def test_metadata_snapshot_and_disappearance_boundaries(self):
        target = self.root / '.git/objects/maintenance.lock'
        original_stat, original_symlink = Path.stat, Path.is_symlink
        observed = self.metadata_observations = []
        lookups = self.metadata_lookups = []
        self.metadata_removals = 0
        def observe(path, *args, **kwargs):
            if path == target:
                lookups.append(kwargs.get('follow_symlinks', True))
            info = original_stat(path, *args, **kwargs)
            if path == target:
                self.assertTrue(stat.S_ISREG(info.st_mode))
                observed.append(info)
                target.unlink()
                self.metadata_removals += 1
            return info
        def symlink(path):
            # Keep the old preliminary link check real; delete at its is_file observation.
            if path == target:
                return stat.S_ISLNK(original_stat(path, follow_symlinks=False).st_mode)
            return original_symlink(path)
        target.write_bytes(b'owned lock')
        before = len(self.children)
        with self.subTest(boundary='after-observation'):
            try:
                with patch.object(Path, 'stat', observe), patch.object(Path, 'is_symlink', symlink):
                    fixtures.command(self.root, 'status', '--porcelain')
            finally:
                self.assertEqual(self.metadata_removals, 1)
                self.assertEqual(len(observed), 1)
                self.assertFalse(target.exists())
            self.assertEqual(lookups, [False])  # The real lstat snapshot is the only entry lookup.
            self.assertEqual(len(self.children), before + 1)
        for number in (errno.ENOENT, errno.EACCES, errno.EIO):
            with self.subTest(errno=number):
                target.write_bytes(b'owned lock')
                def fail(path):
                    if path == target:
                        if number == errno.ENOENT:
                            target.unlink()
                            return original_stat(path, follow_symlinks=False)
                        raise OSError(number, 'owned metadata lookup')
                    return original_stat(path, follow_symlinks=False)
                before = len(self.children)
                try:
                    with patch.object(Path, 'lstat', fail), self.assertRaises(OSError) as raised:
                        fixtures.command(self.root, 'status', '--porcelain')
                    self.assertEqual(raised.exception.errno, number)
                finally:
                    target.unlink(missing_ok=True)
                    self.assertEqual(len(self.children), before)

    def test_metadata_links_and_owned_identity_remain_rejected(self):
        from rc_pretag_admission_tests import FixtureGitIsolationTests
        FixtureGitIsolationTests.test_fixture_git_context_escapes_reject_before_launch(self)
        target, referent = self.root / '.git/owned-entry', self.root / 'referent'
        referent.write_bytes(b'owned data')
        original_lstat = Path.lstat
        for kind in ('symlink', 'dangling', 'hardlink', 'file', 'directory'):
            if kind == 'symlink': target.symlink_to(referent)
            elif kind == 'dangling': target.symlink_to(self.root / 'missing')
            elif kind == 'hardlink': os.link(referent, target)
            elif kind == 'file': target.write_bytes(b'owned data')
            else: target.mkdir()
            lookups, before = [], len(self.children)
            def observe(path):
                if path == target: lookups.append(path)
                return original_lstat(path)
            rejected = kind in ('symlink', 'dangling', 'hardlink')
            with self.subTest(kind=kind), patch.object(Path, 'lstat', observe):
                with self.assertRaises(ValueError) if rejected else nullcontext():
                    fixtures.command(self.root, 'status', '--porcelain')
            self.assertEqual(lookups, [target])
            self.assertEqual(len(self.children), before + (not rejected))
            if kind == 'directory': target.rmdir()
            else: target.unlink()
        owner = Path(self.temp.name)
        temporary, device, inode = self.guard.roots[owner]
        before = len(self.children)
        with patch.dict(self.guard.roots, {owner: (temporary, device, inode + 1)}):
            with self.assertRaises(ValueError): fixtures.command(self.root, 'status')
        self.assertEqual(len(self.children), before)

    def test_automatic_maintenance_controls_are_fixed_child_only(self):
        config = self.root / '.git/config'
        config_before, process_before = config.read_bytes(), dict(os.environ)
        hostile = fixtures.fixture_git_hostile(self.root) | dict(GIT_CONFIG_COUNT='2',
            GIT_CONFIG_KEY_0='maintenance.auto', GIT_CONFIG_VALUE_0='true',
            GIT_CONFIG_KEY_1='gc.auto', GIT_CONFIG_VALUE_1='1',
            GIT_CONFIG_PARAMETERS="'maintenance.auto=true' 'gc.auto=1'", FIXTURE_MARKER='kept')
        user = ['-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid']
        argv = ['git', *user, 'status', '--porcelain']
        argv_before = list(argv)
        with patch.dict(os.environ, hostile):
            inherited = dict(os.environ)
            fixtures.commit(self.root)
            for supplied in (None, dict(hostile), {}):
                supplied_before = None if supplied is None else dict(supplied)
                for launch in (subprocess.run, subprocess.check_output, subprocess.check_call, subprocess.call):
                    value = launch(argv, cwd=self.root, env=supplied, stderr=subprocess.PIPE)
                    self.assertIn(getattr(value, 'returncode', value), (0, b''))
                    self.assertEqual(self.children[-1][1]['env'], fixtures.git_environment(supplied))
                with subprocess.Popen(argv, cwd=self.root, env=supplied, stdout=subprocess.PIPE) as child:
                    self.assertEqual(child.communicate()[0], b'')
                    self.assertEqual(child.returncode, 0)
                self.assertEqual(supplied, supplied_before)
            self.assertEqual(dict(os.environ), inherited)
        self.assertEqual(dict(os.environ), process_before)
        self.assertEqual(argv, argv_before)
        fixed = ['-c', 'core.hooksPath=' + os.devnull, '-c', 'core.fsmonitor=false',
                 '-c', 'maintenance.auto=false', '-c', 'gc.auto=0']
        self.assertEqual(self.children[0][0], [self.guard.executable, *fixed, 'init', '-q'])
        for args, options in self.children:
            accepted = user if args[1:5] == user else []
            prefix = [self.guard.executable, *accepted, *fixed]
            self.assertEqual(args[:len(prefix)], prefix)
            self.assertIn(args[len(prefix)], ('init', 'add', 'commit', 'rev-parse', 'status'))
            self.assertEqual((args.count('maintenance.auto=false'), args.count('gc.auto=0')), (1, 1))
        before = len(self.children)
        for option in ('maintenance.auto=true', 'maintenance.auto=false', 'gc.auto=1', 'gc.auto=0'):
            with self.subTest(option=option), self.assertRaises(ValueError):
                fixtures.command(self.root, '-c', option, 'status')
        self.assertEqual(len(self.children), before)
        self.assertEqual(config.read_bytes(), config_before)


if __name__ == '__main__':
    unittest.main()
