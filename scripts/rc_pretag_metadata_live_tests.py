"""Synthetic provider/adapter/workflow mocks only; never live acceptance evidence."""
from contextlib import ExitStack
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import rc_pretag_metadata_live as live
import rc_pretag_metadata_source as source
from rc_pretag_metadata_fixtures import FixtureAPI, REQUEST

ROOT = Path(__file__).absolute().parent.parent
WORKFLOW = ROOT / live.WORKFLOW


def provider(folder):
    return dict(GITHUB_ACTIONS='true', GITHUB_REPOSITORY='Eswink/coding-tools-mcp',
        GITHUB_REPOSITORY_ID='1360355522', GITHUB_EVENT_NAME='push',
        GITHUB_REF=live.ENGINEERING_REF, GITHUB_JOB='metadata', GITHUB_SHA='a' * 40,
        GITHUB_WORKFLOW_SHA='a' * 40, GITHUB_RUN_ID='1', GITHUB_RUN_ATTEMPT='2',
        GITHUB_WORKFLOW_REF='Eswink/coding-tools-mcp/' + live.WORKFLOW + '@' + live.ENGINEERING_REF,
        RC_EXPECTED_VERSION=live.EXPECTED_VERSION, RC_DIAGNOSTIC_DIR=folder,
        GITHUB_TOKEN='synthetic-token-not-a-credential')


def proof():
    return source.SourceVerification('committed', 'a' * 40, 'b' * 40, source.BASE_SHA,
        source.BASE_TREE, 1628, 1627, source.GUARD_PATH, source.GUARD_BLOB, source.ADDITIONS, 1)


def negative(operation, arguments, occurrence, value):
    if operation == 'runs':
        return {'total_count': 0, 'workflow_runs': []}
    if operation == 'tree' and arguments['sha'] == 'd' * 40:
        value['tree'] = [row for row in value['tree'] if row['sha'] != '1' * 40]
    return value


def accepted(status, files):
    """Synthetic external acceptance probe; file presence alone is never enough."""
    names = {'source.json', 'scope.json', 'metadata.json'}
    if status != 0 or set(files) != names | {'completion.json'}:
        return False
    manifest = json.loads(files['completion.json'])
    rows = manifest['files']
    return len(rows) == 3 and {row['name'] for row in rows} == names and all(
        len(files[row['name']]) == row['bytes']
        and hashlib.sha256(files[row['name']]).hexdigest() == row['sha256'] for row in rows)


class LiveDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.synthetic = live.collect_metadata(REQUEST, FixtureAPI(negative))
        self.request = live.MetadataRequest(replace(REQUEST.source,
            version=live.EXPECTED_VERSION), live.ENGINEERING_REF)
        # Explicit trusted-output mock, not a claim that FixtureAPI used real TLS.
        self.trusted_output_mock = replace(self.synthetic, request=self.request,
            channel='fixed_origin_tls_bearer_request')

    def invoke(self, *, environment=None, before=None, after=None, receipt=None,
               failure=None, writer=None, closer=None):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            env = provider(folder) | (environment or {})
            stack.enter_context(mock.patch.dict(os.environ, env, clear=True))
            proofs = iter((before or proof(), after or proof()))
            def verify(*args, **kwargs):
                self.assertNotIn('GITHUB_TOKEN', os.environ)
                self.assertEqual(kwargs, {})
                return next(proofs)
            gate = stack.enter_context(mock.patch.object(live, 'verify_source', side_effect=verify))
            adapter = stack.enter_context(mock.patch.object(live, 'MetadataGitHub'))
            collector = stack.enter_context(mock.patch.object(live, 'collect_metadata',
                return_value=receipt or self.trusted_output_mock, side_effect=failure))
            if writer:
                stack.enter_context(mock.patch.object(live, 'write', side_effect=writer))
            if closer:
                stack.enter_context(mock.patch.object(live.os, 'close', side_effect=closer))
            status = live.main()
            stack.close()
            output = Path(folder) / 'live'
            files = {p.name: p.read_bytes() for p in output.iterdir()} if output.exists() else {}
            return status, files, gate, adapter, collector

    def test_success_is_blocked_metadata_with_actual_provider_identity(self):
        status, files, gate, adapter, collector = self.invoke()
        self.assertEqual(status, 0)
        self.assertEqual(set(files), {'metadata.json', 'source.json', 'scope.json',
            'completion.pending.json', 'completion.json'})
        self.assertEqual(gate.call_count, 2)
        adapter.assert_called_once_with('synthetic-token-not-a-credential')
        self.assertEqual(collector.call_args.args[0], self.request)
        scope = json.loads(files['scope.json'])
        self.assertEqual((scope['run_id'], scope['run_attempt'], scope['job_name']), (1, 2, 'metadata'))
        self.assertIsNone(scope['numeric_job_id'])
        self.assertFalse(scope['version_verified'])
        metadata = json.loads(files['metadata.json'])
        self.assertEqual((metadata['collection_status'], metadata['eligibility_status']), ('blocked', 'blocked'))
        self.assertNotIn(b'synthetic-token', b''.join(files.values()))

    def test_each_context_field_rejects_missing_and_malformed_values_before_children(self):
        for key in provider('/tmp'):
            if key in ('RC_DIAGNOSTIC_DIR', 'GITHUB_TOKEN'):
                continue
            for value in ('', 'invalid'):
                with self.subTest(field=key, value=value):
                    status, files, gate, adapter, collector = self.invoke(environment={key: value})
                    self.assertEqual(status, 1)
                    self.assertEqual(json.loads(files['error.json'])['code'], 'invalid_context')
                    gate.assert_not_called()
                    adapter.assert_not_called()
                    collector.assert_not_called()

    def test_context_numeric_bounds_and_workflow_code_are_exact(self):
        for key in ('GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'):
            for value in ('0', '-1', '01', str(2**63), '1\n'):
                with mock.patch.dict(os.environ, provider('/tmp') | {key: value}, clear=True):
                    with self.assertRaises(ValueError):
                        live.context()
        with mock.patch.dict(os.environ, provider('/tmp') | {'GITHUB_WORKFLOW_SHA': 'b' * 40}, clear=True):
            with self.assertRaises(ValueError):
                live.context()

    def test_synthetic_adapter_channel_is_never_promoted(self):
        self.assertEqual(self.synthetic.channel, 'synthetic')
        status, files, _, _, _ = self.invoke(receipt=replace(self.synthetic, request=self.request))
        self.assertEqual(status, 1)
        self.assertEqual(set(files), {'error.json'})

    def test_only_complete_repeated_empty_negative_profile_is_accepted(self):
        for key, state, reason in (('repository', 'inaccessible', 'forbidden'),
                ('reviews', 'invalid', 'incomplete_pagination'), ('final_runs', 'changed', 'snapshot_changed'),
                ('pretag_workflow', 'missing', 'not_found_or_not_visible'),
                ('integration_jobs', 'prerequisite_unavailable', 'forbidden')):
            rows = tuple(replace(row, state=state, reason=reason) if row.key == key else row
                         for row in self.trusted_output_mock.observations)
            bad = replace(self.trusted_output_mock, observations=rows,
                revalidation_observations=tuple(replace(row, records=()) for row in rows))
            with self.subTest(key=key), self.assertRaises(ValueError):
                live.quality(bad, self.request)

    def test_nonempty_inventory_or_changed_second_pass_never_becomes_diagnostic_success(self):
        rows = tuple(replace(row, count=1) if row.key == 'final_runs' else row
                     for row in self.trusted_output_mock.observations)
        for second in (self.trusted_output_mock.revalidation_observations,
                       tuple(replace(row, records=()) for row in rows)):
            with self.assertRaises(ValueError):
                live.quality(replace(self.trusted_output_mock, observations=rows,
                    revalidation_observations=second), self.request)
        with self.assertRaises(ValueError):
            live.quality(replace(self.trusted_output_mock, revalidation_sha256=None), self.request)

    def test_false_authority_guards_are_revalidated(self):
        for field in ('release_approved', 'publish_approved', 'finalized', 'artifact_bytes_verified', 'snapshot_atomic'):
            forged = replace(self.trusted_output_mock)
            object.__setattr__(forged, field, True)
            with self.assertRaises(ValueError):
                live.quality(forged, self.request)

    def test_committed_source_and_all_false_source_guards_are_required(self):
        candidates = [replace(proof(), mode='prospective_index'), replace(proof(), source_sha='c' * 40)]
        for field in live.FALSE_FLAGS:
            forged = proof()
            object.__setattr__(forged, field, True)
            candidates.append(forged)
        for candidate in candidates:
            status, files, _, adapter, _ = self.invoke(before=candidate)
            self.assertEqual(status, 1)
            self.assertEqual(set(files), {'error.json'})
            adapter.assert_not_called()

    def test_post_collection_source_change_rejects_all_metadata_outputs(self):
        status, files, gate, _, _ = self.invoke(after=replace(proof(), source_tree='c' * 40))
        self.assertEqual((status, gate.call_count), (1, 2))
        self.assertEqual(set(files), {'error.json'})
        self.assertEqual(json.loads(files['error.json'])['code'], 'source_revalidation_failed')

    def test_cleanup_uncertain_and_private_exceptions_produce_only_fixed_error(self):
        for error, code in ((live.CleanupUncertain(), 'cleanup_uncertain'),
                            (ValueError('private arbitrary remote prose'), 'collection_failed')):
            status, files, _, _, _ = self.invoke(failure=error)
            self.assertEqual(status, 1)
            self.assertEqual(set(files), {'error.json'})
            self.assertEqual(json.loads(files['error.json'])['code'], code)
            self.assertNotIn(b'private', files['error.json'])

    def test_collision_preserves_other_file_and_fails_without_deleting_it(self):
        original = live.write
        def collision(fd, name, value, limit=16384):
            if name == 'source.json':
                original(fd, name, b'collision-marker')
            return original(fd, name, value, limit)
        status, files, _, _, _ = self.invoke(writer=collision)
        self.assertEqual(status, 1)
        self.assertEqual(files['source.json'], b'collision-marker')
        self.assertNotIn('metadata.json', files)
        self.assertEqual(json.loads(files['error.json'])['code'], 'output_failed')

    def test_error_write_failure_and_final_fd_close_failure_return_failure(self):
        def no_write(*args, **kwargs):
            raise OSError('private filesystem detail')
        status, files, _, _, _ = self.invoke(failure=live.CleanupUncertain(), writer=no_write)
        self.assertEqual((status, files), (1, {}))
        original = os.close
        # The final close is the first close after completed metadata output.
        ready = [False]
        writer = live.write
        def remember(fd, name, value, limit=16384):
            result = writer(fd, name, value, limit)
            ready[0] |= name == 'completion.pending.json'
            return result
        def fail_final(fd):
            original(fd)
            if ready[0]:
                raise OSError('private close detail')
        status, files, _, _, _ = self.invoke(writer=remember, closer=fail_final)
        self.assertEqual(status, 1)
        artifact = {name: raw for name, raw in files.items() if name != 'completion.pending.json'}
        self.assertFalse(accepted(status, artifact))

    def test_output_caps_no_overwrite_and_symlinks(self):
        with tempfile.TemporaryDirectory() as folder:
            fd = live.directory(Path(folder))
            try:
                live.write(fd, 'error.json', {'status': 'synthetic'})
                with self.assertRaises(FileExistsError):
                    live.write(fd, 'error.json', {})
                for name, size, limit in (('source.json', 16385, 16384), ('metadata.json', 262145, 262144)):
                    with self.assertRaises(ValueError):
                        live.write(fd, name, b'x' * size, limit)
                (Path(folder) / 'linked').symlink_to(folder)
                with self.assertRaises(OSError):
                    live.directory(Path(folder) / 'linked')
                (Path(folder) / 'scope.json').symlink_to(Path(folder) / 'error.json')
                with self.assertRaises(FileExistsError):
                    live.write(fd, 'scope.json', {})
            finally:
                os.close(fd)

    def test_existing_invocation_directory_is_never_reused(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'live').mkdir()
            marker = Path(folder) / 'live/metadata.json'
            marker.write_bytes(b'collision-marker')
            with mock.patch.dict(os.environ, provider(folder), clear=True), mock.patch.object(live, 'MetadataGitHub') as adapter:
                self.assertEqual(live.main(), 1)
                adapter.assert_not_called()
            self.assertEqual(marker.read_bytes(), b'collision-marker')

    def test_manifest_has_exact_payload_byte_hashes_and_requires_successful_step(self):
        status, files, _, _, _ = self.invoke()
        artifact = {name: raw for name, raw in files.items() if name != 'completion.pending.json'}
        self.assertTrue(accepted(status, artifact))
        self.assertFalse(accepted(1, artifact))
        self.assertEqual(files['completion.pending.json'], files['completion.json'])
        for name in ('source.json', 'scope.json', 'metadata.json'):
            self.assertFalse(accepted(0, artifact | {name: artifact[name] + b' '}))
            self.assertFalse(accepted(0, {key: value for key, value in artifact.items() if key != name}))
        self.assertFalse(accepted(0, artifact | {'unexpected.json': b'{}'}))

    def test_late_payload_or_manifest_write_failure_never_creates_completion(self):
        original = live.write
        for target in ('source.json', 'scope.json', 'metadata.json', 'completion.pending.json'):
            def late(fd, name, value, limit=16384):
                result = original(fd, name, value, limit)
                if name == target:
                    raise OSError('synthetic late flush or close failure')
                return result
            status, files, _, _, _ = self.invoke(writer=late)
            self.assertEqual(status, 1)
            self.assertIn(target, files)  # No deletion or repair of uncertain residue.
            self.assertNotIn('completion.json', files)
            self.assertEqual(json.loads(files['error.json'])['code'], 'output_failed')

    def test_partial_manifest_fsync_failure_and_unconfirmed_file_close_fail(self):
        original = live.write
        def partial(fd, name, value, limit=16384):
            if name == 'completion.pending.json':
                original(fd, name, b'{')
                raise OSError('synthetic partial manifest')
            return original(fd, name, value, limit)
        status, files, _, _, _ = self.invoke(writer=partial)
        self.assertEqual((status, files['completion.pending.json']), (1, b'{'))
        self.assertNotIn('completion.json', files)
        with mock.patch.object(live.os, 'fsync', side_effect=OSError('synthetic fsync failure')):
            status, files, _, _, _ = self.invoke()
        self.assertEqual(status, 1)
        self.assertNotIn('completion.json', files)
        fdopen = os.fdopen
        class FailedClose:
            def __init__(self, *args, **kwargs):
                self.stream = fdopen(*args, **kwargs)
            def __enter__(self):
                return self.stream
            def __exit__(self, *args):
                self.stream.close()
                raise OSError('synthetic close uncertainty')
        with mock.patch.object(live.os, 'fdopen', side_effect=FailedClose):
            status, files, _, _, _ = self.invoke()
        self.assertEqual(status, 1)
        self.assertNotIn('completion.pending.json', files)
        self.assertNotIn('completion.json', files)

    def test_link_failure_and_existing_marker_never_overwrite_or_retry(self):
        original = os.link
        for collide in (False, True):
            def failed_link(src, dst, **options):
                if collide:
                    handle = os.open(dst, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=options['dst_dir_fd'])
                    with os.fdopen(handle, 'wb') as stream:
                        stream.write(b'collision-marker')
                    return original(src, dst, **options)
                raise OSError('synthetic hardlink failure')
            with mock.patch.object(live.os, 'link', side_effect=failed_link) as linking:
                status, files, _, _, _ = self.invoke()
            self.assertEqual(status, 1)
            self.assertEqual(linking.call_count, 1)
            self.assertIn('completion.pending.json', files)
            self.assertEqual(files.get('completion.json'), b'collision-marker' if collide else None)

    def test_payload_inode_replacement_hardlink_and_changed_bytes_are_rejected(self):
        complete = live.complete
        for change in ('replace', 'hardlink', 'bytes'):
            def tamper(fd, payloads):
                if change == 'hardlink':
                    os.link('source.json', 'alias.json', src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
                else:
                    if change == 'replace':
                        os.rename('source.json', 'original.json', src_dir_fd=fd, dst_dir_fd=fd)
                    flags = os.O_WRONLY | (os.O_CREAT | os.O_EXCL if change == 'replace' else 0)
                    with os.fdopen(os.open('source.json', flags, 0o600, dir_fd=fd), 'wb') as stream:
                        stream.write(b'changed')
                return complete(fd, payloads)
            with mock.patch.object(live, 'complete', side_effect=tamper):
                status, files, _, _, _ = self.invoke()
            self.assertEqual(status, 1)
            self.assertNotIn('completion.json', files)

    def test_only_known_pending_marker_pair_can_have_two_links(self):
        original = os.link
        def third_link(src, dst, **options):
            original(src, dst, **options)
            original(src, 'third.json', **options)
        with mock.patch.object(live.os, 'link', side_effect=third_link):
            status, files, _, _, _ = self.invoke()
        self.assertEqual(status, 1)
        self.assertIn('completion.json', files)  # Job failure excludes this residue from upload.
        self.assertIn('error.json', files)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text()

    def test_exact_push_branch_paths_and_no_other_entrypoints(self):
        self.assertIn("branches: ['feat/rc-pretag-metadata-1dfe']", self.text)
        paths = self.text.split('    paths:\n', 1)[1].split('\npermissions:', 1)[0]
        self.assertEqual({line.strip()[3:-1] for line in paths.splitlines()}, set(source.ADDITIONS) | {source.GUARD_PATH})
        for forbidden in ('workflow_dispatch:', 'pull_request:', 'pull_request_target:', 'tags:', '**', 'write-all'):
            self.assertNotIn(forbidden, self.text)

    def test_pins_permissions_token_scope_and_explicit_artifact_paths(self):
        self.assertEqual(self.text.count('GITHUB_TOKEN:'), 1)
        fixture, metadata = self.text.split('  metadata:\n', 1)
        self.assertNotIn('${{ github.token }}', fixture)
        self.assertIn('needs: fixtures', metadata)
        self.assertIn('permissions:\n      contents: read\n      actions: read\n      pull-requests: read', metadata)
        pins = ('actions/checkout@11d5960a326750d5838078e36cf38b85af677262',
            'actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065',
            'actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02')
        for pin in pins:
            self.assertEqual(self.text.count(pin), 3 if 'upload-artifact' in pin else 2)
        self.assertEqual(self.text.count('persist-credentials: false'), 2)
        self.assertEqual(self.text.count('retention-days: 7'), 3)
        self.assertEqual(self.text.count('if: always()'), 1)
        self.assertIn("if: ${{ always() && steps.collect.outcome == 'success' }}", self.text)
        self.assertIn("if: ${{ always() && steps.collect.outcome != 'success' }}", self.text)
        for forbidden in ('download-artifact', 'pip install', 'npm install', 'gh release', 'git tag', 'secrets.'):
            self.assertNotIn(forbidden, self.text)

    def test_failure_artifacts_exclude_all_payload_and_marker_residue(self):
        failure = self.text.split("if: ${{ always() && steps.collect.outcome != 'success' }}", 1)[1]
        paths = [line.strip() for line in failure.split('          path: |\n', 1)[1].splitlines()]
        self.assertEqual(paths, ['${{ env.RC_DIAGNOSTIC_DIR }}/bootstrap.json',
            '${{ env.RC_DIAGNOSTIC_DIR }}/live/error.json'])
        success = self.text.split("if: ${{ always() && steps.collect.outcome == 'success' }}", 1)[1]
        success = success.split('      - uses:', 1)[0]
        for name in ('source.json', 'scope.json', 'metadata.json', 'completion.json'):
            self.assertIn('/live/' + name, success)
        self.assertNotIn('completion.pending.json', success)
        self.assertNotIn('*', success)

    def test_fixture_acquisition_keeps_all_original_bounds_and_checksum(self):
        for bound in ("--proto '=https'", '--max-redirs 0', '--max-time 30', '--connect-timeout 10',
                      '--max-filesize 1048576', 'sha256sum --check --strict',
                      '233daaf6e83ae6a12a52055f568f9d7cf4671dabb78ff9560ab6da230ce00ee5'):
            self.assertIn(bound, self.text)

    def test_file_caps_and_live_has_no_subprocess_or_test_switch(self):
        self.assertLessEqual(len(self.text.splitlines()), 180)
        code = (ROOT / 'scripts/rc_pretag_metadata_live.py').read_text()
        self.assertLessEqual(len(code.splitlines()), 230)
        self.assertLess(len(Path(__file__).read_text().splitlines()), 500)
        for forbidden in ('subprocess', 'shell=True', 'TEST_MODE', 'RC_TEST', 'getpass', 'keyring'):
            self.assertNotIn(forbidden, code)

    def run_synthetic_groups(self, *, bad_group=None, field=None, source_changed=False):
        begin = self.text.index('          import importlib, json, os, sys, unittest\n')
        end = self.text.index('          PY\n', begin)
        code = '\n'.join(line[10:] for line in self.text[begin:end].splitlines())
        expected = [174, 53, 159, 135, 208]
        suites, results = [], []
        for index, count in enumerate(expected):
            loaded = count + (1 if index == bad_group and field == 'loaded' else 0)
            suites.append(mock.Mock(countTestCases=mock.Mock(return_value=loaded)))
            results.append(SimpleNamespace(testsRun=count, failures=['synthetic'] if index == bad_group and field == 'failures' else [],
                errors=['synthetic'] if index == bad_group and field == 'errors' else [],
                skipped=['synthetic'] if index == bad_group and field == 'skipped' else [],
                expectedFailures=['synthetic'] if index == bad_group and field == 'expectedFailures' else [],
                unexpectedSuccesses=['synthetic'] if index == bad_group and field == 'unexpectedSuccesses' else []))
        runner = mock.Mock(run=mock.Mock(side_effect=results))
        after = replace(proof(), source_tree='c' * 40) if source_changed else proof()
        with tempfile.TemporaryDirectory() as folder, \
             mock.patch.dict(os.environ, {'RC_DIAGNOSTIC_DIR': folder, 'GITHUB_SHA': 'a' * 40}, clear=True), \
             mock.patch.object(source, 'verify_source', side_effect=[proof(), after]), \
             mock.patch.object(unittest, 'TestSuite', side_effect=suites), \
             mock.patch.object(unittest, 'TextTestRunner', return_value=runner):
            namespace = {}
            with self.assertRaises(SystemExit) as stopped:
                exec(compile(code, '<synthetic-workflow-fixture-driver>', 'exec'), namespace)
            report = json.loads((Path(folder) / 'fixtures.json').read_text())
            return stopped.exception.code, report, namespace

    def test_executable_workflow_counts_all_five_real_groups(self):
        status, report, namespace = self.run_synthetic_groups()
        self.assertEqual(status, 0)
        self.assertEqual(report['status'], 'passed')
        self.assertEqual({key: value['executed'] for key, value in report['counts'].items()},
            dict(metadata=174, pretag=53, consumer=159, publication=135, original=208))
        self.assertEqual(len(namespace['groups']['original'][1]), 14)
        self.assertIn('exclusive_native_contract_tests', namespace['groups']['original'][1])
        self.assertIn('发布版本回归v4', namespace['groups']['original'][1])
        modules = namespace['groups']['metadata'][1]
        self.assertEqual(set(modules), {path.stem for path in ROOT.joinpath('scripts').glob('rc_pretag_metadata*_tests.py')})
        import importlib
        loaded = sum(unittest.defaultTestLoader.loadTestsFromModule(importlib.import_module(name)).countTestCases()
                     for name in modules)
        self.assertEqual(loaded, namespace['groups']['metadata'][0])

    def test_executable_workflow_rejects_any_count_failure_error_or_skip(self):
        for index in range(5):
            for field in ('loaded', 'failures', 'errors', 'skipped', 'expectedFailures', 'unexpectedSuccesses'):
                status, report, _ = self.run_synthetic_groups(bad_group=index, field=field)
                self.assertEqual((status, report['status']), (1, 'failed'))
                self.assertEqual(len(report['counts']), 5)

    def test_executable_workflow_rejects_post_test_source_change(self):
        status, report, _ = self.run_synthetic_groups(source_changed=True)
        self.assertEqual((status, report['status']), (1, 'failed'))


if __name__ == '__main__':
    unittest.main()
