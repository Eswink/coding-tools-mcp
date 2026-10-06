"""Actual archive payload, package identity and retained member boundaries."""
import copy
import hashlib
import importlib
import inspect
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import desktop_glib_build_contract as c
import desktop_glib_deb as deb
import desktop_glib_deb_tests as fixtures
import linux_package_provenance_contract as contract
import rc_packages

entry = importlib.import_module('AppImage入口配置v3')
ROOT = Path(__file__).resolve().parents[1]


def fixture_identity():
    source='1'*40
    producer=contract.producer_identity(source, '123', '2', c.REPOSITORY +
        '/.github/workflows/linux-rc-packages.yml@refs/heads/ci/preliminary-packages-test')
    e=dict(source_sha=source, source_tree='2'*40, version=fixtures.VERSION, producer=producer, profile=contract.PROFILE)
    packages={kind:dict(artifact=dict(name=f'MCP_{fixtures.VERSION}_amd64'+suffix,sha256='3'*64,size=10),
        package_version=rc_packages.debian_version(fixtures.VERSION) if kind=='deb' else fixtures.VERSION,
        payload_sha256='4'*64, architecture='amd64',package_id='coding-tools-mcp' if kind=='deb' else None)
        for kind,suffix in (('deb','.deb'),('appimage','.AppImage'))}
    manifest=dict(source_sha=source, source_tree=e['source_tree'],version=e['version'],run_id='123',passed=True,
                  build_kind='release-candidate',packages=packages)
    inputs=dict(schema='linux-provenance-inputs-v1',**e,packages=copy.deepcopy(packages),**contract.SCOPE,
        members={deb.BINARY:dict(kind='file',sha256='4'*64,size=10,mode=0o755,nlink=1)},
        package_references={'prebundle':dict(sha256='5'*64,size=10),
            'final_deb':dict(sha256='3'*64,size=10,payload_sha256='4'*64)},guard_final=dict(sha256='6'*64,size=1))
    return e,manifest,inputs


class PackageBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.e,self.manifest,self.inputs=fixture_identity()

    def write_debs(self, changed=None):
        compiled=fixtures.elf()
        raw=self.root/'desktop.deb';raw.write_bytes(fixtures.package())
        (self.root/'desktop.elf').write_bytes(compiled)
        final=self.root/'final.deb'
        rc_packages.repack_deb(raw,final,fixtures.VERSION)
        if changed is not None:
            stage=self.root/'altered';subprocess.run(['/usr/bin/dpkg-deb','--raw-extract',str(final),str(stage)],check=True,capture_output=True)
            changed(stage)
            final.unlink()
            subprocess.run(['/usr/bin/dpkg-deb','--build','--root-owner-group',str(stage),str(final)],check=True,capture_output=True)
        _,receipt=contract.final_deb_payload(final,rc_packages.debian_version(fixtures.VERSION))
        c.write_json(self.root/'final-deb-parser.json',receipt)
        return compiled,raw,final

    def test_raw_tauri_deb_uses_unchanged_marker_verifier(self):
        compiled,raw,_=self.write_debs()
        refs,proof=contract.package_bindings(self.root,fixtures.VERSION)
        self.assertEqual(proof,deb.verify_deb(compiled,raw.read_bytes(),fixtures.VERSION))
        self.assertEqual(refs['raw_deb']['payload_sha256'],hashlib.sha256(fixtures.transformed(compiled)).hexdigest())
        altered=bytearray(compiled);altered[-1]^=1;(self.root/'desktop.elf').write_bytes(altered)
        with self.assertRaises(ValueError):contract.package_bindings(self.root,fixtures.VERSION)

    def test_repacked_rc_deb_requires_same_payload_and_correct_version(self):
        self.write_debs(lambda root:(root/deb.BINARY).write_bytes(fixtures.transformed(fixtures.elf())+b'changed'))
        with self.assertRaisesRegex(ValueError,'repacked_deb_payload_changed'):
            contract.package_bindings(self.root,fixtures.VERSION)
        with self.assertRaises(ValueError):contract.final_deb_payload(self.root/'final.deb',fixtures.VERSION)

    def test_bundle_directory_must_match_authenticated_target_triple(self):
        target=self.root/'target';bundle=target/c.TARGET/'release/bundle';bundle.mkdir(parents=True)
        contract.check_bundle_directory(bundle,target)
        for wrong in (target/'release/bundle',target/'aarch64-unknown-linux-gnu/release/bundle',bundle/'../bundle'):
            with self.assertRaises(ValueError):contract.check_bundle_directory(wrong,target)
        bundle.rmdir();bundle.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(OSError):contract.check_bundle_directory(bundle,target)

    def test_final_package_identity_rejects_name_version_source_or_hash_substitution(self):
        contract.verify_package_identity(self.manifest,self.inputs,self.e)
        for mutation in (lambda m:m.update(source_sha='f'*40),lambda m:m.update(source_tree='e'*40),
            lambda m:m.update(version='0.6.0'),lambda m:m['packages']['deb']['artifact'].update(name='../other.deb'),
            lambda m:m['packages']['deb']['artifact'].update(sha256='bad'),
            lambda m:m['packages']['deb'].update(package_version=fixtures.VERSION),
            lambda m:m['packages']['deb'].update(package_id='different'),lambda m:m.update(run_id='124')):
            m=copy.deepcopy(self.manifest);mutation(m)
            with self.assertRaises(ValueError):contract.verify_package_identity(m,self.inputs,self.e)

    def test_appimage_inventory_records_all_regular_elf_members_and_aliases(self):
        folder=self.root/'appdir';(folder/'usr/bin').mkdir(parents=True);(folder/'usr/lib').mkdir()
        (folder/deb.BINARY).write_bytes(fixtures.elf());(folder/deb.BINARY).chmod(0o755)
        (folder/'usr/lib/ordinary.so').write_bytes(b'\x7fELF'+b'a'*32)
        (folder/'usr/lib/ordinary-alias.so').symlink_to('ordinary.so')
        (folder/'readme').write_text('not ELF')
        inventory=entry.elf_inventory(folder,self.root/'retained')
        self.assertEqual(set(inventory),{deb.BINARY,'usr/lib/ordinary.so','usr/lib/ordinary-alias.so'})
        self.assertEqual(inventory['usr/lib/ordinary-alias.so']['target'],'ordinary.so')
        self.assertEqual((self.root/'retained'/deb.BINARY).read_bytes(),fixtures.elf())
        self.assertEqual(inventory[deb.BINARY]['sha256'],hashlib.sha256(fixtures.elf()).hexdigest())

    def test_appimage_inventory_rejects_escape_special_duplicate_and_overflow_entries(self):
        folder=self.root/'appdir';folder.mkdir();(folder/'inside').write_bytes(b'\x7fELF1234')
        (folder/'escape').symlink_to(self.root/'outside');(self.root/'outside').write_text('x')
        with self.assertRaises(ValueError):entry.elf_inventory(folder)
        (folder/'escape').unlink();os.mkfifo(folder/'fifo')
        with self.assertRaises(ValueError):entry.elf_inventory(folder)
        (folder/'fifo').unlink();os.link(folder/'inside',folder/'alias')
        with self.assertRaises(ValueError):entry.elf_inventory(folder)
        (folder/'alias').unlink()
        with mock.patch.object(entry.os,'walk',return_value=[(str(folder),[],['inside','inside'])]),self.assertRaises(ValueError):
            entry.elf_inventory(folder)
        with mock.patch.object(c,'MAX_BINARY',4),self.assertRaises(ValueError):entry.elf_inventory(folder)

    def test_final_main_and_four_family_bytes_match_guard_receipt(self):
        import appimage_relro_contract_tests as guard_fixtures
        fixture=guard_fixtures.RelroContractTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        folder=self.root/'appimage-relro';folder.mkdir()
        for name,data in fixture.evidence.items():(folder/name).write_bytes(data)
        (self.root/'desktop.elf').write_bytes(fixture.compiled)
        (self.root/'compiler-copies.json').write_bytes(fixture.records['compiler_copies_bytes'])
        (self.root/'build.jsonl').write_bytes(fixture.records['build_jsonl_bytes'])
        for stream,data in fixture.logs.items():(self.root/('tauri.'+stream)).write_bytes(data)
        for kind in ('appdir','appimage'):
            records={}
            for name,item in fixture.inventory.items():
                path=self.root/(kind+'-members')/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(item['data'])
                records[name]={k:v for k,v in item.items() if k!='data'}
            c.write_json(self.root/(kind+'-entry.json'),{'members':records})
        c.write_json(self.root/'package-manifest.json',{'packages':{'appimage':{'artifact':dict(size=1000,sha256='1'*64)}}})
        config=fixture.config
        e=dict(source_sha=config['source_sha'],source_tree=config['source_tree'],producer=config['producer'],
            source_root=config['source_root'],target_dir=config['target_root'],evidence_root=config['evidence_root'],
            engineering_source_inputs={'scripts/appimage_relro_guard.py':{'sha256':config['guard_sha256']}},
            tools={'guard_python':dict(path=config['python_path'],sha256=config['python_sha256'],
                version=config['python_version'],size=100,mode=0o755,uid=0)})
        with mock.patch('appimage_relro_tool.verify_tool_receipt',return_value={'original':{'target':config['original_patchelf_path']}}):
            result=contract.guard_replay(self.root,e,fixture.refs)
            self.assertTrue(result['protected_bytes_preserved']);self.assertEqual(len(result['image']),9)
            for name,item in fixture.inventory.items():
                path=self.root/'appimage-members'/name;path.write_bytes(item['data']+b'changed')
                with self.subTest(member=name),self.assertRaises(ValueError):contract.guard_replay(self.root,e,fixture.refs)
                path.write_bytes(item['data'])

    def test_missing_or_sticky_failed_relro_final_blocks_package_proof(self):
        folder=self.root/'appimage-relro';folder.mkdir()
        (folder/'config.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'failed_or_unexpected_guard_state'):
            contract.guard_replay(self.root,self.e,{})
        for name in contract.GUARD_FILES:(folder/name).touch(exist_ok=True)
        (folder/'failed.json').write_text('{"failed":true}')
        with self.assertRaisesRegex(ValueError,'failed_or_unexpected_guard_state'):
            contract.guard_replay(self.root,self.e,{})

    def test_compiler_envelope_package_manifest_and_artifact_attempt_are_bound(self):
        for kind in ('deb','appimage'):
            path=self.root/self.manifest['packages'][kind]['artifact']['name'];path.write_bytes(kind.encode())
            self.manifest['packages'][kind]['artifact'].update(c.file_record(path))
        self.inputs['packages']=self.manifest['packages']
        c.write_json(self.root/'exclusive-package.json',self.manifest);c.write_json(self.root/'provenance-inputs.json',self.inputs)
        self.e.update(package_manifest=c.file_record(self.root/'exclusive-package.json'),
            provenance_inputs=c.file_record(self.root/'provenance-inputs.json'))
        c.write_json(self.root/'compiler-envelope.json',self.e)
        digest=c.file_record(self.root/'compiler-envelope.json')['sha256']
        def verify(producer=None,hash_value=digest,artifact='42'):
            return contract.installed_binding(self.root,self.e['source_sha'],producer or self.e['producer'],hash_value,
                contract.PROFILE,artifact,'a'*64,'appimage','ubuntu-24.04')
        binding=verify();self.assertEqual(binding['run_attempt'],'2');self.assertEqual(binding['artifact_id'],'42')
        from linux_package_provenance_tests import loader_record, omission_record
        current = loader_record(); current['version']='3.12.15'
        current['library_path']=current['library_path'].replace('3.12.14','3.12.15')
        current['executable']['path']=current['executable']['path'].replace('3.12.14','3.12.15')
        current['library_directory']['mode']=0o40777
        with mock.patch.object(contract,'capture_setup_python_loader',return_value=omission_record(current)) as captured:
            projected=verify();self.assertIsNone(projected['python_loader'])
            self.assertEqual(projected['python_loader_omission'],omission_record(current))
            captured.assert_called_once_with(os.environ,omission=True)
        import linux_package_provenance as producer
        from AppImage入口配置v3 import validate_harness_projection
        binding['python_loader_omission']=omission_record(current)
        binding_file=self.root/'provenance-binding.json';binding_file.write_text(json.dumps(binding))
        command=['--binding',str(binding_file),'--phase','native','--original-ld-state','present',
            '--original-ld-value',current['library_path'],'--output',str(self.root/'native-launch-projection.json')]
        environment=dict(GITHUB_SHA=binding['source_sha'],GITHUB_RUN_ID=binding['run_id'],GITHUB_RUN_ATTEMPT=binding['run_attempt'],
            GITHUB_WORKFLOW_REF=binding['workflow'],PACKAGE_KIND=binding['kind'])
        with mock.patch.dict(os.environ,environment,clear=True), \
             mock.patch.object(producer.platform,'freedesktop_os_release',return_value={'VERSION_ID':'24.04'}), \
             mock.patch.object(contract,'capture_setup_python_loader',return_value=omission_record(current)):
            producer.project_harness_input(command)
            proof=contract.read_json(self.root/'native-launch-projection.json')
            self.assertEqual(proof['original'],{'LD_LIBRARY_PATH':current['library_path']})
            self.assertEqual(proof['projected'],{})
            self.assertEqual(validate_harness_projection(proof,binding,'native-1',{},{}),{})
            for field,value in (('schema','wrong'),('phase','startup-safe-mode'),('binding_sha256','f'*64)):
                changed=dict(proof,**{field:value})
                with self.assertRaises(ValueError):validate_harness_projection(changed,binding,'native-1',{}, {})
            with self.assertRaises(ValueError):validate_harness_projection(proof,binding,'native-1',{'LD_LIBRARY_PATH':current['library_path']},{})
            self.assertFalse((self.root/'unrequested-output.json').exists())
            invalid=dict(binding,schema='wrong');binding_file.write_text(json.dumps(invalid))
            with self.assertRaisesRegex(ValueError,'wrong_harness_binding_context'):producer.project_harness_input(command)
            binding_file.write_text(json.dumps(binding))
            unknown=list(command);unknown[unknown.index('--original-ld-value')+1]=current['library_path']+':/extra'
            with self.assertRaises(ValueError):producer.project_harness_input(unknown)
            with mock.patch.dict(os.environ,{'LD_LIBRARY_PATH':current['library_path']}),self.assertRaises(ValueError):
                producer.project_harness_input(command)
            with mock.patch.dict(os.environ,{'LD_PRELOAD':'/unapproved.so'}),self.assertRaises(ValueError):
                producer.project_harness_input(command)
        wrong=copy.deepcopy(self.e['producer']);wrong['run_attempt']='1'
        for kwargs in ({'producer':wrong},{'hash_value':'f'*64},{'artifact':'0'}):
            with self.assertRaises(ValueError):verify(**kwargs)
        (self.root/self.manifest['packages']['appimage']['artifact']['name']).write_bytes(b'changed')
        with self.assertRaises(ValueError):verify()

    def test_original_package_entry_helper_and_launcher_checks_remain_required(self):
        image=self.root/'image';image.write_bytes(b'image');output=self.root/'proof.json'
        def extracted(args,**kwargs):
            folder=Path(kwargs['cwd'])/'squashfs-root';folder.mkdir()
            (folder/'AppRun').write_text('linuxdeploy-plugin-gtk.sh AppRun.wrapped')
            source=ROOT/entry.LAUNCHER;(folder/'AppRun.wrapped').write_bytes(source.read_bytes());(folder/'AppRun.wrapped').chmod(0o755)
        with mock.patch.object(entry.subprocess,'run',side_effect=extracted), \
             mock.patch.object(entry,'verify_helpers',side_effect=RuntimeError('helper absent')):
            with self.assertRaisesRegex(RuntimeError,'helper absent'):entry.verify(ROOT,image,output,'1'*40,self.root)
        self.assertFalse(output.exists())
        for helper in ('verify_helpers(appdir)','verify_gio_module(appdir)','verify_graphics_runtime(appdir)'):
            self.assertIn(helper,inspect.getsource(entry.verify))

    def test_scope_cannot_expand_to_other_dsos_linker_security_or_release(self):
        for key in contract.SCOPE:
            inputs=copy.deepcopy(self.inputs);inputs[key]=True
            with self.assertRaises(ValueError):contract.verify_package_identity(self.manifest,inputs,self.e)
        self.assertFalse(contract.SCOPE['independent_all_query_attempts_verified'])

    def test_successful_ldd_is_retained_but_cannot_supply_observed_mappings(self):
        text=inspect.getsource(rc_packages.installed)
        self.assertIn('"ldd", str(binary)',text)
        binding=contract.installed_binding
        self.assertNotIn('ldd',inspect.getsource(binding))
        self.assertNotIn('observed',self.inputs)
        self.assertFalse(self.inputs['full_dependency_closure_verified'])


if __name__ == '__main__':
    unittest.main()
