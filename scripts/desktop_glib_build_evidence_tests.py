#!/usr/bin/env python3
import argparse
import copy
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import desktop_glib_build_contract as c
import desktop_glib_build_evidence as producer
import verify_glib_backport_tests as source_tests

ROOT = Path(__file__).resolve().parents[1]


def fixture():
    source, target = '/trusted/source', '/owned/target'
    packages = []
    for name, version, manifest, src, kind in (
        (c.BINARY, '0.6.0-rc.4', 'src-tauri/Cargo.toml', 'src-tauri/src/main.rs', 'bin'),
        ('glib', '0.18.5', 'vendor/glib-0.18.5/Cargo.toml', 'vendor/glib-0.18.5/src/lib.rs', 'lib'),
        ('dependency', '1.0.0', 'dependency/Cargo.toml', 'dependency/src/lib.rs', 'lib')):
        packages.append({'id': name, 'name': name, 'version': version,
            'source': None if name != 'dependency' else c.glib.REGISTRY,
            'manifest_path': source + '/' + manifest,
            'targets': [{'name': name.replace('-', '_') if kind == 'lib' else name,
                         'kind': [kind], 'src_path': source + '/' + src}]})
    metadata = {'packages': packages, 'resolve': {'root': c.BINARY, 'nodes': [
        {'id': c.BINARY, 'deps': [{'pkg': 'glib', 'dep_kinds': [{'kind': None}]}]},
        {'id': 'glib', 'deps': [{'pkg': 'dependency', 'dep_kinds': [{'kind': None}]}]},
        {'id': 'dependency', 'deps': []}]}}
    events = []
    for p in packages:
        name = p['name']
        filename = (target + '/' + c.TARGET + '/release/' + c.BINARY if name == c.BINARY else
                    target + '/' + c.TARGET + '/release/deps/lib' + name + '-abc.rlib')
        events.append({'reason': 'compiler-artifact', 'package_id': p['id'], 'manifest_path': p['manifest_path'],
            'target': p['targets'][0], 'features': [], 'fresh': False,
            'profile': {'test': False, 'opt_level': '3', 'debug_assertions': False, 'debuginfo': 0},
            'filenames': [filename], 'executable': filename if name == c.BINARY else None})
    events.append({'reason': 'build-finished', 'success': True})
    tree = ''.join(p['name'] + ' v' + p['version'] + '\t\n' for p in packages)
    return metadata, tree, events, source, target


def check_events(f):
    metadata, tree, events, source, target = f
    data = b''.join(json.dumps(event).encode() + b'\n' for event in events)
    return c.verify_compiler_events(metadata, tree, data, source, target)


class CompilerContractTests(unittest.TestCase):
    def reject(self, change):
        f = fixture()
        change(f)
        with self.assertRaises((ValueError, KeyError, TypeError)):
            check_events(f)

    def test_complete_required_units_pass(self):
        self.assertEqual(set(check_events(fixture())), {'root', 'glib'})

    def test_missing_glib_or_root_or_dependency(self):
        for index in range(3):
            with self.subTest(index=index): self.reject(lambda f: f[2].pop(index))

    def test_duplicate_glib_and_root(self):
        for index in (0, 1):
            with self.subTest(index=index): self.reject(lambda f: f[2].insert(0, copy.deepcopy(f[2][index])))

    def test_missing_failed_or_duplicate_terminal_event(self):
        self.reject(lambda f: f[2].pop())
        self.reject(lambda f: f[2][-1].update(success=False))
        self.reject(lambda f: f[2].append({'reason': 'build-finished', 'success': True}))

    def test_event_after_finish_rejects(self):
        self.reject(lambda f: f[2].append(copy.deepcopy(f[2][1])))

    def test_compiler_error_or_unknown_event(self):
        self.reject(lambda f: f[2].insert(0, {'reason': 'compiler-message', 'package_id': 'glib',
                                          'message': {'level': 'error'}}))
        self.reject(lambda f: f[2].insert(0, {'reason': 'unreviewed'}))

    def test_registry_glib_or_wrong_manifest(self):
        self.reject(lambda f: f[0]['packages'][1].update(source=c.glib.REGISTRY))
        self.reject(lambda f: f[0]['packages'][1].update(manifest_path='/registry/glib/Cargo.toml'))

    def test_glib_dev_or_build_only_dependency_rejects(self):
        for kind in ('dev', 'build'):
            with self.subTest(kind=kind):
                self.reject(lambda f: f[0]['resolve']['nodes'][0]['deps'][0]['dep_kinds'][0].update(kind=kind))

    def test_wrong_manifest_and_compiler_source(self):
        self.reject(lambda f: f[2][1].update(manifest_path='/wrong/Cargo.toml'))
        self.reject(lambda f: f[2][1].update(target={**f[2][1]['target'], 'src_path': '/standalone/lib.rs'}))

    def test_test_stale_and_wrong_release_profile(self):
        for key, value in (('test', True), ('debug_assertions', True), ('opt_level', '0')):
            with self.subTest(key=key): self.reject(lambda f: f[2][1]['profile'].update({key: value}))
        self.reject(lambda f: f[2][1].update(fresh=True))
        self.reject(lambda f: f[2][0].update(fresh=None))

    def test_wrong_feature_selection(self):
        self.reject(lambda f: f[2][1].update(features=['unselected']))
        self.reject(lambda f: f[2][1].update(features=['duplicate', 'duplicate']))

    def test_wrong_target_and_escaped_output(self):
        self.reject(lambda f: f[2][1].update(filenames=['/owned/target/release/libglib.rlib']))
        self.reject(lambda f: f[2][1].update(filenames=[f[4] + '/' + c.TARGET + '/release/../libglib.rlib']))
        self.reject(lambda f: f[2][0].update(executable='/other/product'))

    def test_glib_must_emit_one_rlib(self):
        self.reject(lambda f: f[2][1].update(filenames=[f[4] + '/' + c.TARGET + '/release/glib.rmeta']))
        self.reject(lambda f: f[2][1]['filenames'].append(f[4] + '/' + c.TARGET + '/release/libglib-two.rlib'))

    def test_duplicate_json_and_truncated_stream(self):
        f = fixture()
        for stream in (b'{"reason":"x","reason":"y"}\n', b'{"reason":'):
            with self.subTest(stream=stream), self.assertRaises(ValueError):
                c.verify_compiler_events(f[0], f[1], stream, f[3], f[4])

    def test_boolean_and_float_status_cannot_claim_success(self):
        for value in (1, 1.0, 'true'):
            with self.subTest(value=value): self.reject(lambda f: f[2][-1].update(success=value))


class JsonAndOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / 'bytes'
        self.path.write_bytes(b'original')

    def test_no_follow_normal_read_and_independent_copy(self):
        self.assertEqual(c.read_regular(self.path), b'original')
        copy = self.root / 'copy'
        self.assertEqual(c.copy_regular(self.path, copy), c.file_record(self.path))
        self.assertEqual(copy.stat().st_nlink, 1)
        self.assertNotEqual(copy.stat().st_ino, self.path.stat().st_ino)

    def test_linked_file_and_linked_parent_reject(self):
        linked = self.root / 'linked'
        linked.symlink_to(self.path)
        with self.assertRaises(OSError): c.read_regular(linked)
        folder = self.root / 'folder'
        folder.mkdir()
        (folder / 'data').write_bytes(b'x')
        (self.root / 'alias').symlink_to(folder, target_is_directory=True)
        with self.assertRaises(OSError): c.read_regular(self.root / 'alias/data')

    def test_evidence_hardlink_rejected_target_alias_allowed(self):
        os.link(self.path, self.root / 'second')
        with self.assertRaises(ValueError): c.read_regular(self.path)
        self.assertEqual(c.stable_file(self.path, self.root, 100, allow_hardlinks=True)['size'], 8)

    def test_hardlink_outside_target_rejects(self):
        target = self.root / 'target'
        target.mkdir()
        inside = target / 'inside'
        os.link(self.path, inside)
        with self.assertRaisesRegex(ValueError, 'outside_target'):
            c.stable_file(inside, target, 100, allow_hardlinks=True)

    def test_copy_refuses_existing_destination(self):
        with self.assertRaises(FileExistsError): c.copy_regular(self.path, self.path)

    def test_descriptor_mutation_rejects(self):
        with self.assertRaisesRegex(ValueError, 'changed_during_read'):
            with c.regular_descriptor(self.path): self.path.write_bytes(b'changed!')

    def test_file_size_and_root_boundaries(self):
        with self.assertRaises(ValueError): c.read_regular(self.path, 2)
        with self.assertRaises(ValueError): c.stable_file(self.path, self.root / 'elsewhere', 100)

    def test_json_nesting_duplicate_keys_and_nonfinite_reject(self):
        for raw in (b'[' * 65 + b'0' + b']' * 65, b'{"a":1,"a":2}', b'{"a":NaN}', b'1e9999'):
            with self.subTest(raw=raw), self.assertRaises(ValueError): c.decode(raw)
        self.assertEqual(c.decode(b'{"quoted":"[[[\\\""}'), {'quoted': '[[["'})

    def test_exclusive_json_and_inventory_links(self):
        c.write_json(self.root / 'record.json', {'valid': True})
        with self.assertRaises(FileExistsError): c.write_json(self.root / 'record.json', {})
        (self.root / 'link').symlink_to(self.path)
        with self.assertRaises(OSError): c.evidence_inventory(self.root)


class ProducerBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_capture_preserves_both_large_streams_and_exit(self):
        command = [sys.executable, '-c', 'import os;os.write(1,b"A"*200000);os.write(2,b"B"*200000);raise SystemExit(7)']
        code = producer.capture(command, self.root, dict(os.environ), self.root/'out', self.root/'err', timeout=10)
        self.assertEqual(code, 7)
        self.assertEqual((self.root/'out').read_bytes(), b'A' * 200000)
        self.assertEqual((self.root/'err').read_bytes(), b'B' * 200000)

    def test_capture_preserves_signal_status(self):
        code = producer.capture([sys.executable, '-c', 'import os,signal;os.kill(os.getpid(),signal.SIGTERM)'],
            self.root, dict(os.environ), self.root/'out', self.root/'err', timeout=10)
        self.assertEqual(code, -signal.SIGTERM)

    def test_capture_timeout_is_failure(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            producer.capture([sys.executable, '-c', 'import time;time.sleep(5)'], self.root,
                dict(os.environ), self.root/'out', self.root/'err', timeout=0.05)
        self.assertFalse((self.root / 'envelope.json').exists())

    def test_capture_limit_is_failure(self):
        with mock.patch.object(producer, 'MAX_LOG', 100), self.assertRaises(ValueError):
            producer.capture([sys.executable, '-c', 'print("x"*1000)'], self.root,
                dict(os.environ), self.root/'out', self.root/'err', timeout=10)

    def test_fresh_directory_must_be_new(self):
        producer.new_directory(self.root / 'fresh')
        with self.assertRaises(FileExistsError): producer.new_directory(self.root / 'fresh')

    def test_inherited_overrides_reject(self):
        forbidden = ('RUSTC', 'RUSTFLAGS', 'RUSTC_WRAPPER', 'RUSTC_WORKSPACE_WRAPPER', 'RUSTC_BOOTSTRAP',
            'CARGO_TARGET_DIR', 'CARGO_BUILD_BUILD_DIR', 'CARGO_BUILD_TARGET_DIR', 'CARGO_BUILD_TARGET',
            'CARGO_ENCODED_RUSTFLAGS', 'CARGO_PROFILE_RELEASE_DEBUG', 'CARGO_SOURCE_CRATES_IO_REPLACE_WITH',
            'CARGO_ALIAS_BUILD', 'CARGO_CONFIG_GLOBAL', 'MAKEFLAGS', 'CARGO_MAKEFLAGS')
        for key in forbidden:
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'inherited_build_override'):
                producer.build_environment(self.root, self.root/'target', {key: 'bad'})

    def test_environment_is_allowlisted_and_config_checked(self):
        with mock.patch.object(producer.glib, 'verify_configuration') as check:
            env = producer.build_environment(self.root, self.root/'target',
                {'PATH': '/tools', 'HOME': '/home/user', 'TOP_SECRET': 'never-copy', 'GIT_DIR': '/wrong'})
            self.assertNotIn('TOP_SECRET', env)
            self.assertNotIn('GIT_DIR', env)
            self.assertEqual(env['CARGO_PROFILE_RELEASE_DEBUG'], '0')
            check.assert_called_once_with(self.root, env)

    def test_existing_cargo_config_names_reject(self):
        fixture_ = source_tests.BackportTests()
        fixture_.setUp()
        self.addCleanup(fixture_.doCleanups)
        directory = fixture_.root / 'src-tauri/.cargo'
        directory.mkdir()
        for name in ('config', 'config.toml'):
            path = directory / name
            path.write_text('[build]\njobs=1\n')
            with self.subTest(name=name), self.assertRaises(ValueError):
                producer.build_environment(fixture_.root, self.root/'target', fixture_.env)
            path.unlink()

    def test_producer_identity_exact_workflow_and_run(self):
        sha = '1' * 40
        workflow = c.REPOSITORY + '/.github/workflows/' + c.WORKFLOW + '@refs/heads/ci/issue85-desktop-glib-deb-test'
        result = c.producer_identity(sha, '123', '1', workflow)
        self.assertEqual(result['source_sha'], sha)
        self.assertEqual(result['job'], 'build')
        for args in (('bad', '123', '1', workflow), (sha, '0', '1', workflow),
                     (sha, '123', True, workflow), (sha, '123', '1', workflow.replace(c.WORKFLOW, 'final-rc-packages.yml'))):
            with self.subTest(args=args), self.assertRaises(ValueError): c.producer_identity(*args)

    def test_runner_requires_expected_argv_before_launch(self):
        config = {'source_root': str(self.root), 'target_dir': str(self.root/'target')}
        with mock.patch.object(producer, 'load_runner_config', return_value=config), self.assertRaises(ValueError):
            producer.cargo_runner(['test', '--release'])

    def test_trusted_digest_and_source_are_not_loaded_from_receipt(self):
        with mock.patch.object(c, 'source_identity', return_value={}), self.assertRaises(ValueError):
            c.verify(self.root, self.root, '1'*40, {}, '')
        (self.root/'envelope.json').write_bytes(b'{}')
        with mock.patch.object(c, 'source_identity', return_value={}), self.assertRaises(ValueError):
            c.verify(self.root, self.root, '1'*40, {}, 'f'*64)

    def test_false_flags_are_explicit(self):
        self.assertIs(c.FLAGS['engineering_only'], True)
        for name in ('installed_desktop_bytes_verified', 'security_approved', 'release_approved',
                     'publish_approved', 'raw_zero_claim'):
            self.assertIs(c.FLAGS[name], False)

    def test_workflow_isolated_and_pinned(self):
        text = (ROOT / '.github/workflows' / c.WORKFLOW).read_text()
        self.assertIn("branches: ['ci/issue85-desktop-glib-deb-*']", text)
        for denied in ('workflow_dispatch:', 'pull_request:', 'workflow_run:', 'contents: write',
                       'secrets.', 'gh release', 'git tag', 'final-rc-packages.yml'):
            self.assertNotIn(denied, text)
        self.assertEqual(text.count("python-version: '3.12'"), 2)
        self.assertIn('artifact-ids: ${{ needs.build.outputs.artifact_id }}', text)
        self.assertIn('artifact_digest: ${{ steps.upload.outputs.artifact-digest }}', text)
        for line in text.splitlines():
            if 'uses:' in line:
                self.assertRegex(line, r'@[0-9a-f]{40}$')


class EnvelopeBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'source'
        self.root.mkdir()
        self.evidence = Path(self.temp.name) / 'evidence'
        self.evidence.mkdir()
        self.sha = '1' * 40
        self.source = dict(source_sha=self.sha, source_tree='2'*40, version='0.6.0-rc.4', target=c.TARGET, source_inputs={})
        self.identity = c.producer_identity(self.sha, '123', '1', c.REPOSITORY + '/.github/workflows/' +
            c.WORKFLOW + '@refs/heads/ci/issue85-desktop-glib-deb-fixture')
        self.events = check_events(fixture())
        for name in c.FILES:
            path = self.evidence / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'{}')
        (self.evidence/'traces').mkdir()
        self.paths = ['src-tauri/src/main.rs', 'vendor/glib-0.18.5/src/lib.rs']
        for n, path in enumerate(self.paths):
            target = self.root/path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b'trusted-source')
            c.write_json(self.evidence/'traces'/('rustc-' + str(n)*32 + '.json'),
                         {'id': str(n)*32, 'source': {'path': '/trusted/source/' + path}})
        runner = '/trusted/source/scripts/desktop_glib_build_evidence.py'
        env = dict(PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', CARGO_TERM_COLOR='never', CARGO_INCREMENTAL='0',
            CARGO_BUILD_JOBS='2', CARGO_PROFILE_RELEASE_DEBUG='0', CARGO_TARGET_DIR='/owned/target', TZ='UTC',
            RUSTC='/real/rustc', RUSTC_WRAPPER=runner)
        self.envelope = dict(schema=1, **self.source, **c.FLAGS, producer=self.identity, source_root='/trusted/source',
            target_dir='/owned/target', files=c.evidence_inventory(self.evidence), cargo_exit=0, tauri_exit=0,
            cargo_arguments=c.cargo_arguments(), tools={name: {'path': '/real/'+name, 'version': name+' 1.98.1',
                'sha256': 'a'*64} for name in ('cargo','rustc')}, build_environment=env,
            advisory_database={'clean':True,'origin':'https://github.com/RustSec/advisory-db.git','commit':'b'*40,
                'tree':'c'*40,'contents_sha256':'d'*64}, advisory_acquisition={'method':'fresh_official_clone',
                'exit':0,'started_ns':1,'finished_ns':2}, tauri_command=['npm','run','tauri','--','build','--config',
                'src-tauri/Ubuntu桌面v1.json','--bundles','deb','--target',c.TARGET,'--runner',runner,'--','--locked','--message-format=json'])
        self.envelope['tools'].update(tauri={'version':'tauri-cli 2.11.4'}, python={'version':'Python 3.12.9'})
        self.envelope['metadata_command'] = ['/real/cargo','metadata','--locked','--format-version','1',
            '--manifest-path','src-tauri/Cargo.toml','--features','tauri/custom-protocol']
        self.envelope['selected_tree_command'] = ['/real/cargo','tree','--locked','--manifest-path',
            'src-tauri/Cargo.toml','--prefix','none','--format','{p}\t{f}','--target',c.TARGET,
            '--edges','normal,build','--features','tauri/custom-protocol']
        ev = '/owned/evidence'
        self.envelope.update(evidence_root=ev, audit_binary='/real/audit', audit_db='/owned/db')
        self.envelope['tools']['python']['path'] = '/real/python'
        self.envelope['commands'] = {'source-audit': {'exit': 0, 'argv': ['/real/python',
            'scripts/verify_glib_backport.py', '--root', '/trusted/source', '--archive', ev+'/upstream.crate',
            '--audit-bin', '/real/audit', '--audit-db', '/owned/db', '--output', ev+'/source-audit']}}
        config = dict(source_sha=self.sha, source_root='/trusted/source', target_dir='/owned/target',
            evidence_root=ev, evidence_dir=ev+'/traces', real_cargo='/real/cargo', real_cargo_sha256='a'*64,
            real_rustc='/real/rustc', real_rustc_sha256='a'*64)
        receipts = {'runner-config.json': config, 'runner-start.json': {'arguments': c.cargo_arguments(),
            'cwd': '/trusted/source/src-tauri'}, 'cargo-exit.json': {'exit': 0}, 'compiler-copies.json': {
            'events': self.events, 'copies': {'desktop': c.file_record(self.evidence/'desktop.elf'),
                                            'glib': c.file_record(self.evidence/'glib.rlib')}}}
        for name, value in receipts.items(): (self.evidence/name).write_text(json.dumps(value))
        self.envelope['files'] = c.evidence_inventory(self.evidence)

    def run_verifier(self, mutation=None):
        e = copy.deepcopy(self.envelope)
        if mutation: mutation(e)
        path = self.evidence/'envelope.json'
        path.write_text(json.dumps(e))
        with ExitStack() as stack:
            for target, value in (('desktop_glib_build_contract.source_identity', self.source),
                ('desktop_glib_build_contract.verify_paired_source', {}),
                ('desktop_glib_build_contract.verify_compiler_events', self.events),
                ('desktop_glib_build_contract.git', '\n'.join(self.paths)),
                ('desktop_glib_link.verify_link_trace', {'compiler_input_provenance_verified':True}),
                ('desktop_glib_deb.verify_deb', {'marker_offset':100})):
                stack.enter_context(mock.patch(target, return_value=value))
            return c.verify(self.root, self.evidence, self.sha, self.identity, hashlib.sha256(path.read_bytes()).hexdigest())

    def test_contradictory_runner_receipts_reject(self):
        for name in ('runner-config.json', 'runner-start.json', 'cargo-exit.json', 'compiler-copies.json'):
            path = self.evidence/name
            original = path.read_bytes()
            try:
                before, after = {'runner-config.json': (b'1'*40, b'f'*40),
                    'runner-start.json': (b'"build"', b'"test"'), 'cargo-exit.json': (b': 0', b': false'),
                    'compiler-copies.json': (c.file_record(self.evidence/'glib.rlib')['sha256'].encode(), b'0'*64)}[name]
                path.write_bytes(original.replace(before, after))
                self.envelope['files'] = c.evidence_inventory(self.evidence)
                with self.subTest(name=name), self.assertRaises((ValueError, KeyError, TypeError)):
                    self.run_verifier()
            finally:
                path.write_bytes(original)
                self.envelope['files'] = c.evidence_inventory(self.evidence)

    def test_admitted_envelope_keeps_global_flags_false(self):
        result = self.run_verifier()
        self.assertTrue(result['desktop_compiler_input_to_deb_binding_verified'])
        for key, value in c.FLAGS.items(): self.assertIs(result[key], value)

    def test_source_producer_exit_tool_and_scope_mutations_reject(self):
        mutations = [lambda e:e.update(source_sha='f'*40), lambda e:e.update(source_tree='e'*40),
            lambda e:e['producer'].update(run_id='124'), lambda e:e['producer'].update(run_attempt='2'),
            lambda e:e.update(cargo_exit=True), lambda e:e.update(tauri_exit=1),
            lambda e:e['tools']['rustc'].update(version='rustc 1.97.0'),
            lambda e:e['tools']['tauri'].update(version='tauri-cli 2.11.5'),
            lambda e:e['tools']['python'].update(version='Python 3.10.0'),
            lambda e:e.update(installed_desktop_bytes_verified=True), lambda e:e.update(release_approved=0),
            lambda e:e['cargo_arguments'].append('--features=other'), lambda e:e['tauri_command'].append('--debug'),
            lambda e:e['build_environment'].update(RUSTFLAGS='override'),
            lambda e:e['advisory_database'].update(clean=1), lambda e:e['advisory_acquisition'].update(exit=True),
            lambda e:e['files'].pop('build.jsonl'), lambda e:e['commands']['source-audit'].update(exit=True),
            lambda e:e['commands']['source-audit']['argv'].append('--unexpected')]
        for mutation in mutations:
            with self.subTest(mutation=mutation), self.assertRaises((ValueError,KeyError,TypeError)):
                self.run_verifier(mutation)


def real_mutations(directory, version, output=None):
    from desktop_glib_deb import deb_payload, verify_deb, verify_marker_transform
    compiled = c.read_regular(directory/'desktop.elf', c.MAX_BINARY)
    package = c.read_regular(directory/'desktop.deb', c.MAX_BINARY)
    result = verify_deb(compiled, package, version)
    payload, _ = deb_payload(package, version)
    changed_elf = bytearray(compiled)
    changed_elf[-1] ^= 1
    changed_payload = bytearray(payload)
    changed_payload[-1] ^= 1
    changed_package = bytearray(package)
    changed_package[0] ^= 1
    controls = [('actual_emitted_elf_nonmarker_mutation', lambda: verify_deb(bytes(changed_elf), package, version)),
        ('actual_deb_payload_nonmarker_mutation', lambda: verify_marker_transform(compiled, bytes(changed_payload))),
        ('actual_deb_archive_mutation', lambda: verify_deb(compiled, bytes(changed_package), version))]
    names = []
    for name, callback in controls:
        try: callback()
        except c.exact.EvidenceError: names.append(name)
        else: raise AssertionError('real mutation unexpectedly accepted: ' + name)
    report = {'passed': True, 'scope': 'data-only mutations of authenticated actual build bytes',
        'controls': names, 'count': len(names), 'prebundle_sha256': result['prebundle_sha256'],
        'package_sha256': result['package_sha256'], **c.FLAGS}
    if output: c.write_json(output, report)
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--real-evidence', type=Path)
    parser.add_argument('--real-version')
    parser.add_argument('--real-output', type=Path)
    args, rest = parser.parse_known_args()
    if args.real_evidence:
        parser.error('--real-version is required') if not args.real_version else None
        real_mutations(args.real_evidence, args.real_version, args.real_output)
    else:
        unittest.main(argv=[sys.argv[0], *rest], verbosity=2)
