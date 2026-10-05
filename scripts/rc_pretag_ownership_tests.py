"""Issue111: exact reviewed ownership source, finite topology and failure boundaries."""
import ast
from contextlib import ExitStack, contextmanager
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import rc_pretag_composition_tests as c
import rc_pretag_ownership_profile as o
import rc_pretag_collect as collect
import rc_pretag_collection_result as result
from rc_consumer_io_ownership_tests import load_current


class OwnershipCompositionTests(unittest.TestCase):
    def setUp(self):
        self.repo, _, self.commit, self.blob = self.enterContext(c._profile_fixture())
        self.good = c._entries(o.M, self.repo)
        for path in o.CAPS:
            self.good[path] = ('100644', 'blob', self.blob((c.ROOT / path).read_bytes()))
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
        self.assertEqual((len(c.ALLOWED), len(o.CAPS), len(c.ALLOWED | o.CAPS.keys())), (22, 12, 32))
        with self.assertRaises(o.TopologyError): self.selected(o.M)
        for path, pin in o.NEW_PINS.items(): self.assertEqual(o.pin((c.ROOT / path).read_bytes()), pin)

    def test_ownership_io_drift_and_reverted_handoff_reject(self):
        old = c._git('show', o.M + ':' + o.IO, root=self.repo)
        current = (c.ROOT / o.IO).read_bytes()
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
        data = {p: (c.ROOT / p).read_bytes() for p in o.CAPS}
        delta = o.budgets(self.pure, self.repo, c._git, data)
        self.assertLessEqual(delta, 2200)
        path = 'scripts/rc_pretag_ownership_tests.py'
        for count, widened in ((301, False), (len(data[path].splitlines()) + 2201 - delta, True)):
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


if __name__ == '__main__':
    unittest.main()
