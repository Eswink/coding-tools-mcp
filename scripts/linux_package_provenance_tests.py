"""New engineering profile boundaries; historical test IDs remain separate."""
import copy
from contextlib import ExitStack
import hashlib
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import desktop_glib_build_contract as c
import desktop_glib_build_evidence as old
import desktop_glib_build_evidence_tests as fixtures
import linux_package_provenance as producer
import linux_package_provenance_contract as contract

ROOT = Path(__file__).resolve().parents[1]


def engineering_fixture(test):
    fixture = fixtures.EnvelopeBoundaryTests()
    fixture.setUp()
    test.addCleanup(fixture.doCleanups)
    e = fixture.envelope
    source = dict(fixture.source, engineering_source_inputs={})
    identity = contract.producer_identity(fixture.sha, '123', '1', c.REPOSITORY +
        '/.github/workflows/linux-rc-packages.yml@refs/heads/ci/preliminary-packages-fixture')
    e.update(source, schema='linux-package-provenance-v1', profile=contract.PROFILE,
        producer=identity, originals_dir='/owned/originals', packages_root='/owned/packages', **contract.SCOPE)
    e['tauri_command'] = contract.tauri_command(e['source_root'])
    e['files']['appimage-relro/config.json'] = {'sha256': 'e'*64, 'size': 100}
    e['build_environment'].update(APPIMAGE_EXTRACT_AND_RUN='1',
        LDAI_RUNTIME_FILE='/owned/originals/runtime-x86_64',
        PATCHELF='/trusted/source/scripts/appimage_relro_guard.py',
        APPIMAGE_RELRO_CONFIG='/owned/evidence/appimage-relro/config.json', APPIMAGE_RELRO_CONFIG_SHA256='e'*64)
    config = json.loads((fixture.evidence / 'runner-config.json').read_text())
    config['profile'] = contract.PROFILE
    (fixture.evidence / 'runner-config.json').write_text(json.dumps(config))
    return fixture, source, identity, e


class CompilerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.f, self.source, self.identity, self.e = engineering_fixture(self)

    def check(self, change=None, profile=contract.PROFILE):
        e = copy.deepcopy(self.e)
        if change:
            change(e)
        contract.verify_header(e, self.source, self.identity, profile)

    def test_engineering_profile_requires_exact_workflow_source_and_attempt(self):
        self.check()
        for change in (lambda e:e.update(source_sha='3'*40), lambda e:e.update(source_tree='3'*40),
            lambda e:e['producer'].update(run_attempt='2'), lambda e:e['producer'].update(workflow_sha='2'*40),
            lambda e:e['producer'].update(job='installed'), lambda e:e['producer'].update(run_id='124')):
            with self.subTest(change=change), self.assertRaises(ValueError): self.check(change)
        for workflow in ('main', 'ci/issue85-desktop-glib-deb-fixture', 'ci/preliminary-packages-../x'):
            with self.assertRaises(ValueError): contract.producer_identity('1'*40, '1', '1',
                c.REPOSITORY + '/.github/workflows/linux-rc-packages.yml@refs/heads/' + workflow)

    def test_cross_profile_and_self_selected_profile_reject(self):
        for profile in (None, '', 'issue85', 1):
            with self.subTest(profile=profile), self.assertRaises(ValueError): self.check(profile=profile)
        with self.assertRaises(ValueError): self.check(lambda e:e.update(profile='issue85'))
        historical = c.producer_identity('1'*40, '123', '1', c.REPOSITORY +
            '/.github/workflows/' + c.WORKFLOW + '@refs/heads/ci/issue85-desktop-glib-deb-fixture')
        with self.assertRaises(ValueError): contract.verify_header(self.e, self.source, historical, contract.PROFILE)

    def test_historical_profile_keeps_exact_producer_command_and_flags(self):
        fixture = fixtures.EnvelopeBoundaryTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        result = fixture.run_verifier()
        self.assertEqual(result['producer']['workflow_ref'].split('/.github/workflows/')[1].split('@')[0], c.WORKFLOW)
        for key, expected in c.FLAGS.items(): self.assertIs(result[key], expected)
        self.assertEqual(fixture.envelope['tauri_command'][4:6], ['build', '--config'])
        self.assertEqual(fixture.envelope['tauri_command'][8], 'deb')

    def test_single_tauri_invocation_uses_existing_runner_and_wrapper(self):
        command = contract.tauri_command('/source')
        self.assertEqual(command.count('build'), 1)
        self.assertEqual(command[4:6], ['--verbose', 'build'])
        self.assertEqual(command[command.index('--bundles')+1], 'deb,appimage')
        self.assertEqual(command[-3:], ['--', '--locked', '--message-format=json'])
        for change in (lambda e:e['tauri_command'].remove('--verbose'),
            lambda e:e['tauri_command'].append('--debug'), lambda e:e['cargo_arguments'].append('--workspace')):
            with self.assertRaises(ValueError): self.check(change)
        self.assertIn('old.capture(build,', inspect.getsource(producer.collect))
        self.assertEqual(inspect.getsource(producer.collect).count('old.capture(build,'), 1)

    def test_metadata_runner_hook_and_package_paths_share_one_target(self):
        self.check()
        for key in ('metadata_command', 'selected_tree_command'):
            with self.assertRaises(ValueError): self.check(lambda e:e[key].append('--target=wrong'))
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / 'target'
            bundle = target / c.TARGET / 'release/bundle'
            bundle.mkdir(parents=True)
            contract.check_bundle_directory(bundle, target)
            with self.assertRaises(ValueError): contract.check_bundle_directory(target / 'release/bundle', target)
        config = json.loads((self.f.evidence/'runner-config.json').read_text())
        self.assertEqual(config['target_dir'], self.e['target_dir'])
        c.verify_runner_receipts(self.f.evidence, self.e, self.f.events,
            c.file_record(self.f.evidence/'desktop.elf'), c.file_record(self.f.evidence/'glib.rlib'), contract.PROFILE)

    def test_target_evidence_packages_and_originals_are_fresh_disjoint_owned(self):
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            root = base/'source'; root.mkdir()
            values = [base/n for n in ('evidence', 'target', 'originals', 'packages')]
            producer.owned_directories(root, *values)
            self.assertEqual((values[0].stat().st_mode & 0o777), 0o700)
            with self.assertRaises(ValueError): producer.owned_directories(root, *values)
            for index in range(4):
                changed = [base/('fresh'+str(n)) for n in range(4)]
                changed[index] = root/'inside'
                with self.assertRaises(ValueError): producer.owned_directories(root, *changed)

    def test_engineering_environment_rejects_inherited_build_and_guard_overrides(self):
        keys = ('RUSTFLAGS', 'CARGO_TARGET_DIR', 'CARGO_PROFILE_RELEASE_LTO', 'PATCHELF',
            'PATCHELF_DEBUG', 'APPIMAGE_RELRO_CONFIG', 'APPIMAGE_RELRO_ANY', 'LD_PRELOAD',
            'LD_LIBRARY_PATH', 'LDAI_RUNTIME_FILE', 'NO_STRIP', 'APPIMAGE_EXTRACT_AND_RUN', 'TAURI_CONFIG')
        for key in keys:
            with self.subTest(key=key), mock.patch.object(c.glib, 'verify_configuration'), self.assertRaises(ValueError):
                producer.engineering_environment(Path('/source'), Path('/target'), {key:'unexpected'})

    def test_only_fixed_appimage_and_relro_environment_is_forwarded(self):
        with mock.patch.object(c.glib, 'verify_configuration'):
            env = producer.engineering_environment(Path('/source'), Path('/target'),
                {'PATH':'/usr/bin:/bin', 'APPIMAGE_EXTRACT_AND_RUN':'1', 'SECRET_TOKEN':'not-forwarded'})
        self.assertNotIn('SECRET_TOKEN', env)
        self.assertNotIn('APPIMAGE_EXTRACT_AND_RUN', env)
        for key in ('PATCHELF', 'APPIMAGE_RELRO_CONFIG', 'LDAI_RUNTIME_FILE', 'RUSTC_WRAPPER'):
            with self.assertRaises(ValueError): self.check(lambda e:e['build_environment'].update({key:'/wrong'}))
        with self.assertRaises(ValueError): self.check(lambda e:e['build_environment'].update(LD_LIBRARY_PATH='/x'))

    def test_compiler_binding_is_written_before_runner_returns(self):
        import appimage_relro_tool
        metadata, tree, events, source, target = fixtures.fixture()
        evidence = self.f.evidence
        config = dict(source_root=source, target_dir=target, evidence_root=str(evidence), profile=contract.PROFILE,
            real_cargo='/real/cargo', real_cargo_sha256='a'*64)
        (evidence/'metadata.json').write_text(json.dumps(metadata)); (evidence/'selected-tree.txt').write_text(tree)
        (evidence/'build.jsonl').write_bytes(b''.join(json.dumps(e).encode()+b'\n' for e in events))
        for name in ('runner-start.json', 'cargo-exit.json', 'compiler-copies.json'): (evidence/name).unlink()
        observed = []
        def bound(path, records):
            self.assertEqual(c.decode(c.read_regular(evidence/'cargo-exit.json')), {'exit':0})
            self.assertEqual(c.decode(c.read_regular(evidence/'compiler-copies.json')), records)
            observed.append('bound')
        with mock.patch.object(old, 'load_runner_config', return_value=config), mock.patch.object(Path, 'cwd', return_value=Path(source)/'src-tauri'), \
             mock.patch.object(old, 'capture', return_value=0), mock.patch.object(c, 'stable_file'), \
             mock.patch.object(c, 'file_record', return_value={'sha256':'a'*64,'size':1}), \
             mock.patch.object(c, 'copy_regular', return_value={'sha256':'b'*64,'size':1}), \
             mock.patch.object(appimage_relro_tool, 'bind_compiler', side_effect=bound):
            self.assertEqual(old.cargo_runner(c.cargo_arguments()), 0)
        self.assertEqual(observed, ['bound'])

    def test_compiler_binding_matches_copies_events_and_source(self):
        root_record, glib_record = (c.file_record(self.f.evidence/name) for name in ('desktop.elf', 'glib.rlib'))
        c.verify_runner_receipts(self.f.evidence, self.e, self.f.events, root_record, glib_record, contract.PROFILE)
        for change in (lambda e:e.update(source_sha='a'*40), lambda e:e.update(target_dir='/elsewhere'),
                       lambda e:e['tools']['rustc'].update(sha256='b'*64)):
            e = copy.deepcopy(self.e); change(e)
            with self.assertRaises(ValueError):
                c.verify_runner_receipts(self.f.evidence, e, self.f.events, root_record, glib_record, contract.PROFILE)

    def test_cached_missing_or_mismatched_compiler_outputs_reject(self):
        for mutation in (lambda f:f[2][0].update(fresh=True), lambda f:f[2].pop(1),
            lambda f:f[2][0].update(executable='/wrong'), lambda f:f[2][-1].update(success=False)):
            fixture = fixtures.fixture(); mutation(fixture)
            with self.assertRaises(ValueError): fixtures.check_events(fixture)

    def test_postbundle_target_must_match_retained_prebundle_bytes(self):
        with tempfile.TemporaryDirectory() as raw:
            base=Path(raw); target=base/'target'; evidence=base/'evidence'; evidence.mkdir()
            binary=target/c.TARGET/'release'/c.BINARY; binary.parent.mkdir(parents=True)
            binary.write_bytes(b'actual compiler bytes'); (evidence/'desktop.elf').write_bytes(binary.read_bytes())
            producer.check_restored_target(target, evidence)
            binary.write_bytes(b'changed by bundle')
            with self.assertRaises(ValueError): producer.check_restored_target(target, evidence)

    def test_pinned_tools_and_guard_run_in_fixed_prepare_build_finalize_order(self):
        text=inspect.getsource(producer.collect)
        steps=['appimage_tools.prepare(', 'prepare_session(', "'before',", 'old.capture(build,', 'seal_session(',
               "'after',", 'entry.verify(', 'rc_packages.prepare(', 'contract.guard_replay(', "'envelope.json', envelope)"]
        offsets=[text.index(step) for step in steps]
        self.assertEqual(offsets, sorted(offsets))
        self.assertNotIn('npm run tauri -- build', (ROOT/'.github/workflows/linux-rc-packages.yml').read_text())

    def test_failed_compiler_bundle_or_guard_cannot_emit_success(self):
        for key, bad in (('cargo_exit', 1), ('cargo_exit', False), ('tauri_exit', -9), ('tauri_exit', True)):
            with self.assertRaises(ValueError): self.check(lambda e:e.update({key:bad}))
        import appimage_relro_guard
        with tempfile.TemporaryDirectory() as raw:
            path=Path(raw); (path/'failed.json').write_text('{}')
            with self.assertRaises((ValueError, KeyError, OSError)):
                appimage_relro_guard.seal_session({'evidence_root':str(path.parent), 'profile':'wrong'})

    def test_paired_unfiltered_source_audits_remain_required(self):
        with mock.patch.object(c, 'verify_paired_source', side_effect=ValueError('raw paired audit absent')) as audited:
            with self.assertRaisesRegex(ValueError, 'raw paired audit absent'):
                c.verify_compiler_payload(self.f.root,self.f.evidence,self.f.sha,self.source,self.e,contract.PROFILE)
        audited.assert_called_once()
        for change in (lambda e:e['advisory_database'].update(clean=False),
                       lambda e:e['advisory_acquisition'].update(exit=1)):
            with self.assertRaises(ValueError): self.check(change)

    def test_evidence_inventory_rejects_missing_extra_changed_or_linked_files(self):
        import appimage_relro_contract as guard
        with tempfile.TemporaryDirectory() as raw:
            directory=Path(raw)
            names=c.FILES | contract.EXTRA_FILES | {'appimage-relro/'+n for n in contract.GUARD_FILES}
            names|={prefix+'/'+name for prefix in ('appdir-members','appimage-members') for name in guard.PROTECTED}
            for name in names:
                path=directory/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(b'x')
            inventory=c.evidence_inventory(directory); contract.verify_inventory(directory,inventory)
            chosen=directory/'build.jsonl'; chosen.write_bytes(b'changed')
            with self.assertRaises(ValueError): contract.verify_inventory(directory,inventory)
            chosen.write_bytes(b'x'); chosen.unlink(); chosen.symlink_to(directory/'desktop.elf')
            with self.assertRaises((ValueError,OSError)): contract.verify_inventory(directory,inventory)
            chosen.unlink(); chosen.write_bytes(b'x'); (directory/'unexpected').write_bytes(b'x')
            with self.assertRaises(ValueError): contract.verify_inventory(directory,c.evidence_inventory(directory))
            (directory/'unexpected').unlink(); chosen.unlink()
            with self.assertRaises(ValueError): contract.verify_inventory(directory,c.evidence_inventory(directory))

    def test_expected_envelope_digest_is_external_to_evidence(self):
        path=self.f.evidence/'envelope.json'; path.write_text(json.dumps(self.e))
        for digest in (None, '', '0'*64):
            with self.assertRaises(ValueError): contract.verify(self.f.root,self.f.evidence,self.f.sha,
                self.identity,digest,contract.PROFILE)
        self.e['trusted_digest']='0'*64; path.write_text(json.dumps(self.e))
        with self.assertRaises(ValueError): contract.verify(self.f.root,self.f.evidence,self.f.sha,
            self.identity,'0'*64,contract.PROFILE)

    def test_data_only_replay_never_executes_recorded_paths(self):
        self.e['tools']['cargo']['path']='/malicious/executable'
        self.e['metadata_command'][0]='/malicious/executable'; self.e['selected_tree_command'][0]='/malicious/executable'
        with mock.patch.object(subprocess,'run',side_effect=AssertionError('must not execute recorded command')):
            self.check()
        text=inspect.getsource(contract.final_deb_payload)
        self.assertIn("Path('/usr/bin/dpkg-deb')", text)
        self.assertNotIn("e['tools']",text)

    def test_untracked_build_evidence_does_not_weaken_source_cleanliness(self):
        text=inspect.getsource(c.source_identity)
        self.assertIn("'--untracked-files=all'",text)
        with mock.patch.object(c,'source_identity',side_effect=ValueError('unclean_source')):
            with self.assertRaisesRegex(ValueError,'unclean_source'): contract.source_identity(self.f.root,self.f.sha)
        workflow=(ROOT/'.github/workflows/linux-rc-packages.yml').read_text()
        self.assertNotIn('mkdir -p evidence',workflow)
        self.assertNotIn('$GITHUB_WORKSPACE/evidence',workflow)

    def test_cancellation_stream_or_close_failure_remains_failed(self):
        with tempfile.TemporaryDirectory() as raw:
            base=Path(raw)
            with self.assertRaises(subprocess.TimeoutExpired):
                old.capture([sys.executable,'-c','import time; time.sleep(10)'],base,dict(os.environ),
                    base/'out',base/'err',timeout=.05)
            with mock.patch.object(old,'MAX_LOG',16), self.assertRaises(ValueError):
                old.capture([sys.executable,'-c','print("x"*10000)'],base,dict(os.environ),base/'out2',base/'err2')


if __name__ == '__main__':
    unittest.main()
