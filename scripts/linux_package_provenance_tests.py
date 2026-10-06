"""New engineering profile boundaries; historical test IDs remain separate."""
import copy
from contextlib import ExitStack, contextmanager
import hashlib
import inspect
import io
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
        producer=identity, originals_dir='/owned/originals', packages_root='/owned/packages', python_loader=None,
        python_loader_omission=omission_record(None), **contract.SCOPE)
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


def loader_record():
    base = '/opt/hostedtoolcache/Python/3.12.14/x64'
    return dict(schema='setup-python-loader-v1', version='3.12.14',
        executable=dict(path=base+'/bin/python3.12', sha256='a'*64, size=100), library_path=base+'/lib',
        library_directory=dict(device=1, inode=2, mode=0o40755, uid=0))


def omission_record(record):
    return dict(schema='setup-python-omission-v1', input=record,
        original_ld_library_path=record['library_path'] if record else None,
        child_ld_library_path=None, loading_authorized=False)


@contextmanager
def installed_python_fixture():
    """A synthetic installation adapter, with real descriptor reads and hashes."""
    record = loader_record(); executable = record['executable']['path']; library = record['library_path']
    with tempfile.TemporaryDirectory() as raw, ExitStack() as stack:
        root = Path(raw); binary = root/'python3.12'; binary.write_bytes(b'synthetic-selected-python')
        libs = root/'lib'; libs.mkdir(mode=0o755)
        original_stat, original_resolve = Path.stat, Path.resolve
        original_parent, original_record = c.parent_descriptor, c.file_record
        def mapped(path):
            return binary if str(path) == executable else libs if str(path) == library else path
        def parent(path):
            return original_parent(libs/Path(path).name if str(Path(path).parent) == library else path)
        stack.enter_context(mock.patch.object(contract.sys, 'version_info', (3,12,14)))
        stack.enter_context(mock.patch.object(contract.sys, 'executable', executable))
        stack.enter_context(mock.patch.object(contract.sys, 'prefix', library[:-4]))
        stack.enter_context(mock.patch.object(Path, 'resolve', lambda path,*a,**k:
            path if str(path) == executable else original_resolve(path,*a,**k)))
        stack.enter_context(mock.patch.object(Path, 'stat', lambda path,*a,**k: original_stat(mapped(path),*a,**k)))
        stack.enter_context(mock.patch.object(c, 'parent_descriptor', side_effect=parent))
        stack.enter_context(mock.patch.object(c, 'file_record', side_effect=lambda path,*a,**k: original_record(mapped(path),*a,**k)))
        yield {'LD_LIBRARY_PATH':library, 'pythonLocation':library[:-4]}, libs, binary


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
        e = copy.deepcopy(self.e); e['python_loader_omission'] = omission_record(loader_record())
        e['tools']['python'] = dict(e['python_loader_omission']['input']['executable'], version='Python 3.12.14')
        contract.verify_header(e, self.source, self.identity, contract.PROFILE)
        for key, value in (('sha256', 'b'*64), ('size', 101), ('version', 'Python 3.12.15')):
            changed = copy.deepcopy(e); changed['tools']['python'][key] = value
            with self.assertRaises(ValueError): contract.verify_header(changed,self.source,self.identity,contract.PROFILE)
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
        isolated = """import builtins, json, sys
sys.path.insert(0, sys.argv[1])
real_import = builtins.__import__
def without_unix(name, *args, **kwargs):
    if name.split('.')[0] in {'resource', 'fcntl', 'pwd', 'grp', 'termios', 'tty'}:
        raise ModuleNotFoundError('Windows-unavailable module: ' + name)
    return real_import(name, *args, **kwargs)
builtins.__import__ = without_unix
import linux_package_provenance_contract as contract
try:
    contract.parser_limits()
except RuntimeError as exc:
    assert str(exc) == 'Linux DEB parser resource limits are unavailable on this platform'
else:
    raise AssertionError('Missing platform limits must fail closed')
print(json.dumps(contract.tauri_command('/source')))
"""
        result = subprocess.run([sys.executable, '-B', '-c', isolated, str(ROOT/'scripts')],
            cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), command)

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
        with installed_python_fixture() as (original, library, executable):
            record = contract.capture_setup_python_loader(original)
            self.assertEqual(record['executable']['sha256'], hashlib.sha256(executable.read_bytes()).hexdigest())
            self.assertEqual(record['library_directory']['inode'], library.stat().st_ino)
            with mock.patch.object(c.glib, 'verify_configuration'):
                child = producer.engineering_environment(Path('/source'),Path('/target'),original)
            self.assertNotIn('LD_LIBRARY_PATH',child)
            self.assertNotIn('pythonLocation',child)
            for bad in (original['LD_LIBRARY_PATH']+':/extra', original['LD_LIBRARY_PATH']+'/',
                        original['LD_LIBRARY_PATH']+':', '', '/tmp/alias'):
                with self.assertRaises(ValueError): contract.capture_setup_python_loader(dict(original,LD_LIBRARY_PATH=bad))
            with self.assertRaises(ValueError): contract.capture_setup_python_loader(dict(original,pythonLocation='/other'))
            library.chmod(0o777)
            errors = io.StringIO()
            with mock.patch.object(contract.sys,'stderr',errors), self.assertRaisesRegex(ValueError,'^unsafe_setup_python_library_directory$'):
                contract.capture_setup_python_loader(dict(original,SECRET_TOKEN='must-not-be-logged'))
            self.assertLess(len(errors.getvalue().encode()),8192)
            diagnostic = json.loads(errors.getvalue().removeprefix('SETUP_PYTHON_LOADER_REJECTION:'))
            expected = library.stat()
            self.assertEqual({k:diagnostic['library_'+k] for k in ('mode','uid','gid','device','inode')},
                dict(mode=expected.st_mode,uid=expected.st_uid,gid=expected.st_gid,device=expected.st_dev,inode=expected.st_ino))
            self.assertEqual(diagnostic['requested_python'],contract.sys.executable)
            self.assertEqual(diagnostic['resolved_python'],record['executable']['path'])
            self.assertEqual(diagnostic['python_sha256'],record['executable']['sha256'])
            self.assertEqual(diagnostic['python_version'],'3.12.14')
            self.assertEqual(diagnostic['python_prefix'],original['pythonLocation'])
            self.assertNotIn('must-not-be-logged',errors.getvalue())
            omitted = contract.capture_setup_python_loader(original,omission=True)
            self.assertEqual(omitted,omission_record({**record,'library_directory':{**record['library_directory'],'mode':0o40777}}))
            self.assertIsNone(omitted['child_ld_library_path']); self.assertIs(omitted['loading_authorized'],False)
            from AppImage入口配置v3 import setup_python_omitted, omit_setup_python_input
            self.assertTrue(setup_python_omitted(omitted))
            supplied={'LD_LIBRARY_PATH':original['LD_LIBRARY_PATH'],'GDK_BACKEND':'x11'}
            self.assertEqual(omit_setup_python_input(supplied,omitted),{'GDK_BACKEND':'x11'})
            self.assertIn('LD_LIBRARY_PATH',supplied)
            with self.assertRaises(ValueError): contract.setup_python_library(omitted['input'])
            for bad in ('',original['LD_LIBRARY_PATH']+':/other','/other'):
                with self.assertRaises(ValueError): omit_setup_python_input({'LD_LIBRARY_PATH':bad},omitted)
            with self.assertRaises(ValueError): omit_setup_python_input({},omitted)
            for field,value in (('loading_authorized',True),('child_ld_library_path',original['LD_LIBRARY_PATH'])):
                with self.assertRaises(ValueError): setup_python_omitted(dict(omitted,**{field:value}))
            with mock.patch('builtins.print',side_effect=OSError('closed stream')), self.assertRaisesRegex(ValueError,'^unsafe_setup_python_library_directory$'):
                contract.capture_setup_python_loader(original)
            library.chmod(0o755)
            with mock.patch.object(contract.sys,'version_info',(3,12,15)), self.assertRaises(ValueError):
                contract.capture_setup_python_loader(original)
            with mock.patch.object(contract.sys,'prefix',original['pythonLocation']+'/alias'), self.assertRaises(ValueError):
                contract.capture_setup_python_loader(original)
            file_record = c.file_record
            def changed_directory(path,*args,**kwargs):
                result = file_record(path,*args,**kwargs); library.chmod(0o700); return result
            with mock.patch.object(c,'file_record',side_effect=changed_directory), self.assertRaisesRegex(ValueError,'changed_setup_python_identity'):
                contract.capture_setup_python_loader(original)
            library.chmod(0o755)
            def changed_executable(path,*args,**kwargs):
                result = file_record(path,*args,**kwargs); executable.write_bytes(b'changed-selected-python'); return result
            with mock.patch.object(c,'file_record',side_effect=changed_executable), self.assertRaisesRegex(ValueError,'changed_setup_python_identity'):
                contract.capture_setup_python_loader(original)
            real_fstat = os.fstat
            def wrong_owner(fd):
                fields = list(real_fstat(fd)); fields[4] = 123456; return os.stat_result(fields)
            with mock.patch.object(os,'fstat',side_effect=wrong_owner), self.assertRaisesRegex(ValueError,'unowned_setup_python_library'):
                contract.capture_setup_python_loader(original)
            saved = library.with_name('saved-lib'); library.rename(saved); library.symlink_to(saved,target_is_directory=True)
            with self.assertRaises(OSError): contract.capture_setup_python_loader(original)
        record = loader_record()
        for mutation in (lambda r:r.update(version='3.12.15'), lambda r:r.update(library_path=r['library_path']+':/tmp'),
            lambda r:r['executable'].update(sha256='invalid'), lambda r:r['executable'].update(path='/other/python3.12'),
            lambda r:r['library_directory'].update(mode=0o40777), lambda r:r['library_directory'].update(mode=0o100755),
            lambda r:r['library_directory'].update(inode=True), lambda r:r['library_directory'].update(uid=-1)):
            changed = copy.deepcopy(record); mutation(changed)
            with self.assertRaises(ValueError): contract.setup_python_library(changed)
        pure = """import builtins,json,sys
sys.path.insert(0,sys.argv[1])
real_import=builtins.__import__
def portable(name,*args,**kwargs):
    if name.split('.')[0] in {'tomllib','resource','fcntl','desktop_glib_build_contract','desktop_glib_deb'}:
        raise ModuleNotFoundError(name)
    return real_import(name,*args,**kwargs)
builtins.__import__=portable
from AppImage入口配置v3 import setup_python_library
print(setup_python_library(json.loads(sys.argv[2])))
"""
        isolated = subprocess.run([sys.executable,'-B','-c',pure,str(ROOT/'scripts'),json.dumps(record)],
            capture_output=True,text=True,timeout=30)
        self.assertEqual(isolated.returncode,0,isolated.stderr)
        self.assertEqual(isolated.stdout.strip(),record['library_path'])
        with mock.patch.object(c.glib, 'verify_configuration'):
            env = producer.engineering_environment(Path('/source'), Path('/target'),
                {'PATH':'/usr/bin:/bin', 'APPIMAGE_EXTRACT_AND_RUN':'1', 'SECRET_TOKEN':'not-forwarded'})
        self.assertNotIn('SECRET_TOKEN', env)
        self.assertNotIn('APPIMAGE_EXTRACT_AND_RUN', env)
        workflow = (ROOT/'.github/workflows/linux-rc-packages.yml').read_text()
        binding = 'python -B scripts/linux_package_binding_tests.py'
        self.assertEqual(workflow.count(binding),1)
        self.assertLess(workflow.index('uses: actions/setup-python@'),workflow.index(binding))
        self.assertLess(workflow.index(binding),workflow.index('uses: dtolnay/rust-toolchain@'))
        self.assertLess(workflow.index(binding),workflow.index('name: Install build dependencies'))
        self.assertIn('id: package_binding',workflow)
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
