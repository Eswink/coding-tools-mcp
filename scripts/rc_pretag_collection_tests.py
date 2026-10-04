"""Hermetic current-byte composition, no-authority output and failure ownership."""
from contextlib import ExitStack, nullcontext
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import rc_artifact_consumer as consumer
import rc_consumer_io as private
from rc_consumer_io import ConsumerError, PrivateRoot
import rc_pretag_collect as collect
import rc_pretag_collection_result as result
from rc_pretag_types import ContractError
from rc_pretag_collect_fixtures import PreTagFixture, FINAL_BRANCH

NAME = 'rc-pretag-observation.json'
SECRET = 'SECRET-must-never-appear-in-a-report'
FLAGS = ('release_approved', 'publish_approved', 'security_approved',
         'published_candidate', 'finalized', 'snapshot_atomic')

class _BrokenStream:
    def __init__(self, stream, operation): self.stream, self.operation = stream, operation
    def __getattr__(self, name): return getattr(self.stream, name)
    def __enter__(self): return self
    def __exit__(self, *args):
        self.stream.close()
        if self.operation == 'close': raise OSError(SECRET)
    def write(self, data):
        if self.operation == 'write': self.stream.write(data[:1]); raise OSError(SECRET)
        return self.stream.write(data)
    def flush(self):
        if self.operation == 'flush': raise OSError(SECRET)
        return self.stream.flush()

class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.f = PreTagFixture(self.temp.name)

    def invoke(self, opener=None):
        with self.f.reviewed():
            return collect.collect(self.f.root, self.f.env, self.f.api,
                                   opener=opener or self.f.opener())

    def test_real_current_pipeline_yields_only_bounded_blocked_observation(self):
        value = self.invoke()
        encoded = result.encode(value); document = json.loads(encoded)
        self.assertTrue(document['artifact']['artifact_bytes_verified'])
        self.assertEqual(document['source']['source_sha'], self.f.sha)
        self.assertEqual(len(document['assets']), 4)
        self.assertEqual(len(document['installed_platforms']), 5)
        self.assertEqual(document['audits']['cloud']['raw_vulnerability_count'], 1)
        for field in FLAGS:
            self.assertIs(document[field], False)
        self.assertEqual(document['release_blockers'], list(consumer.contracts.BLOCKERS))
        for forbidden in (self.temp.name, self.f.api.token, 'signature=', 'installed_path', 'C:\\private'):
            self.assertNotIn(forbidden, encoded.decode())
        self.assertEqual(self.f.control.read_bytes(), b'')
        self.assertFalse(list(self.f.runner_temp.rglob(NAME)))
        self.assertFalse(list(self.f.runner_temp.rglob('rc-asset-plan*')))

    def test_shared_pipeline_failure_edges_stop_in_exact_order(self):
        edges = [(consumer.transport, 'download_artifact_zip'),
                 (consumer.snapshot, 'revalidate_download'),
                 (consumer.archive, 'extract_bounded_zip'),
                 (consumer.archive, 'verify_checksum_inventory'),
                 (consumer.archive, 'extract_bounded_cloud_tar'),
                 (consumer.contracts, 'verify_consumed_bundle')]
        from rc_consumer_plan_tests import PlanTests
        post = PlanTests(); post.setUp(); self.addCleanup(post.doCleanups)
        names = [name for _, name in edges] + ['download.files', 'bundle.files', 'cloud.files']
        for phase, invoke in (('pretag', self.invoke), ('posttag', post.invoke)):
            for stop in range(len(names) + 1):
                seen, membership, original_files = [], [], PrivateRoot.files
                with self.subTest(phase=phase, edge=stop), ExitStack() as stack:
                    for index, (module, name) in enumerate(edges):
                        original = getattr(module, name)
                        def call(*args, _i=index, _name=name, _original=original, **kwargs):
                            seen.append(_name)
                            if _i == stop: raise ConsumerError('synthetic_edge_failure')
                            return _original(*args, **kwargs)
                        stack.enter_context(patch.object(module, name, side_effect=call))
                    def files(root):
                        if names[5] in seen and len(membership) < 3:
                            index = 6 + len(membership); membership.append(index); seen.append(names[index])
                            if index == stop: raise ConsumerError('synthetic_membership_failure')
                        return original_files(root)
                    stack.enter_context(patch.object(PrivateRoot, 'files', files))
                    with self.assertRaises((result.Failure, ConsumerError)) if stop < len(names) else nullcontext():
                        invoke()
                self.assertEqual(seen, names[:stop + 1])
                self.assertEqual(self.f.control.read_bytes(), b'')

    def test_corrupt_actual_zip_stops_before_parser(self):
        changed = bytes([self.f.data[0] ^ 1]) + self.f.data[1:]
        with patch.object(consumer.archive, 'extract_bounded_zip') as parse:
            with self.assertRaises(result.Failure):
                self.invoke(self.f.opener(changed))
            parse.assert_not_called()

    def test_post_content_fences_reject_mutation_without_reselection(self):
        def change(f, kind):
            api = f.api
            if kind == 'source': (f.root / 'package.json').write_text('{}')
            elif kind == 'ref': api.data['/git/ref/heads/' + FINAL_BRANCH]['object']['sha'] = 'b' * 40
            elif kind == 'run': api.data[api.own_run_path()]['status'] = 'completed'
            elif kind == 'job': api.data[api.own_jobs_path()]['jobs'][0]['id'] += 1
            elif kind == 'attempt': api.data[api.own_run_path()]['run_attempt'] += 1
            elif kind == 'artifact': api.data['/actions/artifacts/13']['digest'] = 'sha256:' + 'c' * 64
            elif kind == 'tag': api.tag_response = dict(ref='refs/tags/v' + f.version,
                                                        object=dict(type='commit', sha=f.sha))
            else:
                page = api.data[f'/actions/workflows/11/runs?head_sha={f.sha}&per_page=100&page=1']
                page['workflow_runs'].insert(0, dict(page['workflow_runs'][0], id=124, conclusion='failure'))
                page['total_count'] = 2
        for kind in ('source', 'ref', 'run', 'job', 'attempt', 'artifact', 'tag', 'newest'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as base:
                fixture = PreTagFixture(base)
                original = consumer._verify_bundle_bytes
                def mutate(*args, **kwargs):
                    value = original(*args, **kwargs); change(fixture, kind); return value
                with fixture.reviewed(), patch.object(consumer, '_verify_bundle_bytes', side_effect=mutate):
                    with self.assertRaises(result.Failure):
                        collect.collect(fixture.root, fixture.env, fixture.api, opener=fixture.opener())
                self.assertEqual(fixture.control.read_bytes(), b'')
                self.assertFalse(list(fixture.runner_temp.rglob(NAME)))

    def test_all_payload_descriptors_close_before_result_factory(self):
        roots, original, factory = [], private.PrivateRoot, result._collect
        events, summarize, revalidate = [], result._summarize, collect.admission.revalidate
        def fresh(*args, **kwargs):
            root = original(*args, **kwargs); roots.append(root); return root
        def mint(*args, **kwargs):
            self.assertEqual(len(roots), 3)
            self.assertTrue(all(root.fd is None for root in roots))
            return factory(*args, **kwargs)
        with patch.object(private, 'PrivateRoot', side_effect=fresh), \
             patch.object(result, '_collect', side_effect=mint), \
             patch.object(result, '_summarize', side_effect=lambda *a: (events.append('summary'), summarize(*a))[1]), \
             patch.object(collect.admission, 'revalidate', side_effect=lambda *a: (events.append('fence'), revalidate(*a))[1]):
            self.invoke()
        self.assertEqual(events, ['summary', 'fence'])

class FailureTests(unittest.TestCase):
    def test_closed_failure_schema_and_sticky_cleanup_uncertainty(self):
        failure = result.Failure('transport', ConsumerError('transport_cleanup_uncertain'))
        for stage in (*result.STAGE_CODES, 'UNTRUSTED-' + SECRET):
            failure.record(stage, ConsumerError(SECRET.lower()))
            failure.record(stage, OSError(SECRET))
        value = json.loads(failure.encode())
        self.assertEqual(set(value), {'schema', 'passed', 'stage', 'error_code',
            'secondary_error_codes', 'terminal_state', 'cleanup_confirmed', *result.FALSE_FLAGS})
        self.assertEqual((value['stage'], value['error_code'], value['terminal_state']),
                         ('transport', 'transport_cleanup_uncertain', 'unknown'))
        self.assertLessEqual(len(set(value['secondary_error_codes'])), 4)
        self.assertTrue(set(value['secondary_error_codes']) <= result.CODES)
        self.assertNotIn(SECRET, failure.encode().decode())
        for key in ('passed', 'cleanup_confirmed', *result.FALSE_FLAGS):
            self.assertIs(value[key], False)

    def test_interrupt_timeout_and_unknown_codes_never_claim_cleanup(self):
        import asyncio
        for error in (KeyboardInterrupt(SECRET), SystemExit(SECRET), asyncio.CancelledError(),
                      TimeoutError(SECRET), ConsumerError('attacker_chosen_code')):
            value = json.loads(result.Failure('transport', error).encode())
            self.assertNotIn(SECRET, json.dumps(value))
            self.assertIn(value['error_code'], result.CODES)
            self.assertIs(value['cleanup_confirmed'], False)
            if not isinstance(error, ConsumerError):
                self.assertEqual(value['terminal_state'], 'unknown')

    def test_exact_success_and_failure_caps_include_newline(self):
        for cap in (result.SUCCESS_LIMIT, result.FAILURE_LIMIT):
            value = {'x': 'x' * (cap - len(result._bytes({'x': ''}, cap)))}
            self.assertEqual(len(result._bytes(value, cap)), cap)
            value['x'] += 'x'
            with self.assertRaisesRegex(ConsumerError, 'pretag_output_limit'):
                result._bytes(value, cap)
        for value in (float('nan'), float('inf'), float('-inf')):
            with self.assertRaises(ValueError): result._bytes({'x': value}, result.SUCCESS_LIMIT)

    def test_saved_receipt_plan_or_success_dictionary_cannot_be_encoded(self):
        import rc_pretag_fixtures as legacy
        for value in (legacy.receipt(True), {'schema': 'rc-asset-plan', 'passed': True},
                      {'artifact_bytes_verified': True}, b'{"passed":true}\n'):
            with self.subTest(kind=type(value).__name__), self.assertRaises(ConsumerError):
                result.encode(value)
        with self.assertRaises(ConsumerError): result.CollectedPreTagEvidence()

class OutputLifecycleTests(unittest.TestCase):
    setUp = CollectionTests.setUp
    invoke = CollectionTests.invoke

    def test_private_single_file_closed_before_handoff(self):
        evidence = self.invoke()
        path = collect.emit(evidence, self.f.root, self.f.env)
        self.assertEqual(path.name, NAME)
        self.assertEqual({p.name for p in path.parent.iterdir()}, {NAME})
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(path.read_bytes(), result.encode(evidence))
        self.assertFalse(path.is_relative_to(self.f.root))

    def test_mutated_raw_and_non_record_output_are_rejected(self):
        value = self.invoke()
        object.__setattr__(value, '_raw', b'{"passed":true}\n')
        for item in (value, {'passed': True}, None):
            with self.assertRaises((result.Failure, ConsumerError)):
                collect.emit(item, self.f.root, self.f.env)
        self.assertEqual(self.f.control.read_bytes(), b'')

    def test_numeric_boolean_nonfinite_and_content_authority_rejected(self):
        admitted, _, selection, _, producer = self.f.capture()
        content = self.f.f.verify()
        for path in (('assets', 0, 'size'), ('installed_platforms', 0, 'native_stages'),
                     ('audits', 'cloud', 'active_vulnerability_count')):
            for invalid in (True, False, 0.0, float('inf'), float('nan'), -1):
                value = copy.deepcopy(content); target = value
                for key in path[:-1]: target = target[key]
                target[path[-1]] = invalid
                with self.subTest(path=path, invalid=invalid), self.assertRaises(ConsumerError):
                    result._summarize(admitted, selection, producer, value)
        with self.assertRaises(ConsumerError): result._summarize(admitted, selection, {}, content)
        object.__setattr__(admitted.source, 'repository_id', True)
        with self.assertRaises(ContractError): result._summarize(admitted, selection, producer, content)

    def test_freeform_fields_never_cross_allowlist(self):
        admitted, _, selection, _, producer = self.f.capture()
        content = self.f.f.verify()
        content['debug'] = content['assets'][0]['source_path'] = SECRET
        content['audits']['cloud']['stderr'] = SECRET
        self.assertNotIn(SECRET.encode(), result.encode(result._collect(result._summarize(admitted, selection, producer, content))))

    def test_report_write_flush_fsync_close_readback_and_root_close_fail(self):
        value, fdopen, close = self.invoke(), os.fdopen, PrivateRoot.close
        for operation in ('write', 'flush', 'fsync', 'close', 'readback', 'root_close'):
            with self.subTest(operation=operation), ExitStack() as stack:
                if operation in ('write', 'flush', 'close'):
                    stack.enter_context(patch.object(os, 'fdopen', side_effect=lambda fd, mode:
                        _BrokenStream(fdopen(fd, mode), operation) if mode == 'xb' else fdopen(fd, mode)))
                elif operation == 'fsync': stack.enter_context(patch.object(os, 'fsync', side_effect=OSError(SECRET)))
                elif operation == 'readback': stack.enter_context(patch.object(PrivateRoot, 'read', return_value=b'bad'))
                else:
                    def fail(root): close(root); raise OSError(SECRET)
                    stack.enter_context(patch.object(PrivateRoot, 'close', fail))
                with self.assertRaises(result.Failure): collect.emit(value, self.f.root, self.f.env)
            self.assertEqual(self.f.control.read_bytes(), b'')
        self.assertTrue(list(self.f.runner_temp.rglob(NAME)))  # Residue is not success/deletion.

    def test_report_mode_hardlink_inode_and_root_replacement_reject(self):
        value, files = self.invoke(), PrivateRoot.files
        for kind in ('mode', 'hardlink', 'inode', 'root'):
            def attack(root):
                path = root.path / NAME
                if kind == 'mode': path.chmod(0o644)
                elif kind == 'hardlink': os.link(path, root.path / 'extra')
                elif kind == 'inode': path.unlink(); path.write_bytes(b'replaced'); path.chmod(0o600)
                else: root.path.rename(str(root.path) + '-old'); root.path.mkdir(mode=0o700)
                return files(root)
            with self.subTest(kind=kind), patch.object(PrivateRoot, 'files', attack):
                with self.assertRaises(result.Failure): collect.emit(value, self.f.root, self.f.env)
            self.assertEqual(self.f.control.read_bytes(), b'')

    def test_report_exclusive_nofollow_and_owner_reject(self):
        value, initialize, fstat = self.invoke(), PrivateRoot.__init__, os.fstat
        for kind in ('existing', 'symlink', 'owner'):
            def create(root, *args, **kwargs):
                initialize(root, *args, **kwargs)
                if kind == 'existing': (root.path / NAME).touch(mode=0o600)
                elif kind == 'symlink': (root.path / NAME).symlink_to(self.f.control)
            def identity(fd):
                info = fstat(fd)
                if kind == 'owner' and os.readlink('/proc/self/fd/' + str(fd)).endswith(NAME):
                    fields = list(info); fields[4] += 1; return os.stat_result(fields)
                return info
            with self.subTest(kind=kind), patch.object(PrivateRoot, '__init__', create), patch.object(os, 'fstat', identity):
                with self.assertRaises(result.Failure): collect.emit(value, self.f.root, self.f.env)
            self.assertEqual(self.f.control.read_bytes(), b'')

    def test_anchored_handoff_rejects_symlink_hardlink_outside_missing(self):
        path = collect.emit(self.invoke(), self.f.root, self.f.env)
        self.f.control.write_bytes(b'')
        for kind in ('symlink', 'hardlink', 'outside', 'missing'):
            target = self.f.runner_temp / kind
            if kind == 'symlink': target.symlink_to(self.f.control)
            elif kind == 'hardlink': os.link(self.f.control, target)
            elif kind == 'outside': target = Path(self.temp.name) / kind; target.touch()
            with self.subTest(kind=kind), self.assertRaises((ConsumerError, OSError)):
                collect._handoff(path, str(self.f.runner_temp), dict(self.f.env, GITHUB_OUTPUT=str(target)))
            if kind == 'hardlink': target.unlink()
        self.assertEqual(self.f.control.read_bytes(), b'')

    def test_handoff_write_flush_fsync_close_failure_is_terminal(self):
        path, fdopen = collect.emit(self.invoke(), self.f.root, self.f.env), os.fdopen
        for operation in ('write', 'flush', 'fsync', 'close'):
            self.f.control.write_bytes(b'')
            with self.subTest(operation=operation), ExitStack() as stack:
                if operation == 'fsync': stack.enter_context(patch.object(os, 'fsync', side_effect=OSError(SECRET)))
                else: stack.enter_context(patch.object(os, 'fdopen', side_effect=lambda fd, mode:
                        _BrokenStream(fdopen(fd, mode), operation)))
                with self.assertRaises(OSError): collect._handoff(path, str(self.f.runner_temp), self.f.env)

    def test_handoff_consumes_close_authority_once_and_bounds_full_line(self):
        path, calls, failing_fd = Path('/tmp/report/' + NAME), [], 10
        def close(fd):
            calls.append(fd)
            if fd == failing_fd: raise OSError(SECRET)
        with patch.object(private, '_directory', return_value=10), patch.object(os, 'open', return_value=20), \
             patch.object(os, 'close', side_effect=close), self.assertRaises(OSError):
            collect._handoff(path, '/tmp', {'GITHUB_OUTPUT': '/tmp/sub/control'})
        self.assertEqual(calls, [10, 20])
        calls.clear()
        failing_fd = 20
        with patch.object(private, '_directory', return_value=10), patch.object(os, 'open', return_value=20), \
             patch.object(os, 'fdopen', side_effect=OSError(SECRET)), \
             patch.object(os, 'close', side_effect=close), self.assertRaises(OSError):
            collect._handoff(path, '/tmp', {'GITHUB_OUTPUT': '/tmp/control'})
        self.assertEqual(calls, [20, 10])
        oversized = Path('/tmp/' + 'x' * (result.PATH_LIMIT - len('/tmp//') - len(NAME)) + '/' + NAME)
        with patch.object(private, '_directory') as opened, self.assertRaises(ConsumerError):
            collect._handoff(oversized, '/tmp', {'GITHUB_OUTPUT': '/tmp/control'})
        opened.assert_not_called()

    def test_cli_token_popped_before_every_git_and_child_and_released(self):
        import subprocess
        original, launch, seen = collect.collect, subprocess.Popen, []
        def guard(*args, **kwargs):
            self.assertNotIn('GH_TOKEN', os.environ)
            self.assertNotIn('GH_TOKEN', kwargs.get('env') or os.environ)
            self.assertNotIn(SECRET, repr(args)); seen.append(args)
            return launch(*args, **kwargs)
        with self.f.reviewed(), patch.dict(os.environ, dict(self.f.env, GH_TOKEN=SECRET), clear=True), \
             patch.object(collect, 'ROOT', self.f.root), patch.object(collect.sys, 'argv', ['collect']), \
             patch.object(collect.snapshot, 'GitHub', return_value=self.f.api), \
             patch.object(collect, 'collect', side_effect=lambda *a, **k: original(*a, opener=self.f.opener())), \
             patch.object(subprocess, 'Popen', side_effect=guard):
            self.assertEqual(collect.main(), 0)
        self.assertTrue(seen); self.assertEqual(self.f.api.token, '')
        self.assertNotIn(SECRET, self.f.control.read_text())

    def test_cleanup_uncertainty_survives_later_close_and_report_errors(self):
        close = PrivateRoot.close
        def fail(root): close(root); raise OSError(SECRET)
        with patch.object(consumer.transport, 'download_artifact_zip', side_effect=ConsumerError('transport_cleanup_uncertain')), \
             patch.object(PrivateRoot, 'close', fail), self.assertRaises(result.Failure) as caught:
            self.invoke()
        with patch.dict(os.environ, self.f.env, clear=True), patch.object(collect.sys, 'argv', ['collect']), \
             patch.object(collect.sys, 'stdout', _BrokenStream(io.StringIO(), 'write')), \
             patch.object(collect.snapshot, 'GitHub', return_value=self.f.api), \
             patch.object(collect, 'collect', side_effect=caught.exception):
            self.assertEqual(collect.main(), 1)
        self.assertEqual(json.loads(caught.exception.encode())['error_code'], 'transport_cleanup_uncertain')
        self.assertEqual(self.f.control.read_bytes(), b'')

    def test_cli_failures_and_cancellation_emit_only_sanitized_nonzero(self):
        for error in (KeyboardInterrupt(SECRET), TimeoutError(SECRET), ConsumerError(SECRET.lower())):
            output = io.StringIO()
            with patch.dict(os.environ, dict(self.f.env, GH_TOKEN=SECRET), clear=True), \
                 patch.object(collect.sys, 'argv', ['collect']), patch.object(collect.sys, 'stdout', output), \
                 patch.object(collect.snapshot, 'GitHub', return_value=self.f.api), \
                 patch.object(collect, 'collect', side_effect=error), patch.object(collect, 'emit') as emit:
                self.assertEqual(collect.main(), 1); emit.assert_not_called()
            self.assertNotIn(SECRET, output.getvalue())
            self.assertLessEqual(len(output.getvalue().encode()), result.FAILURE_LIMIT)
            self.assertIs(json.loads(output.getvalue())['passed'], False)
            self.assertEqual(self.f.api.token, '')

if __name__ == '__main__':
    unittest.main()
