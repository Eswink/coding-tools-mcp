"""Ordinary owned controls only: no Debian ELF, installer, Git or CI execution."""
import hashlib
import io
import json
import lzma
import os
from pathlib import Path
import struct
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
import owned_debian_msgfmt_prepare as m


class DebianMsgfmtPreparationControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=m.ROOT, prefix='ordinary-debian-')
        self.root = Path(self.temp.name)
        self.record = {'Package':'gettext','Version':'0.21-12','Architecture':'amd64'}

    def tearDown(self):
        self.temp.cleanup()

    def signature(self):
        parts=[]
        for primary in sorted(m.ANCHORS):
            parts += ['[GNUPG:] NEWSIG', '[GNUPG:] GOODSIG '+primary[-16:]+' Official ordinary control',
                      '[GNUPG:] VALIDSIG '+primary+' 2026-07-11 1783765031 0 4 0 1 8 01 '+primary,
                      '[GNUPG:] TRUST_UNDEFINED 0 pgp']
        return ('\n'.join(parts)+'\n').encode()

    def tar_bytes(self, rows):
        out=io.BytesIO()
        with tarfile.open(fileobj=out, mode='w:') as tar:
            for name,kind,data in rows:
                info=tarfile.TarInfo(name);info.mode=0o755 if kind=='dir' else 0o644
                if kind=='file':info.size=len(data);tar.addfile(info,io.BytesIO(data))
                elif kind=='dir':info.type=tarfile.DIRTYPE;tar.addfile(info)
                elif kind=='link':info.type=tarfile.SYMTYPE;info.linkname=data;tar.addfile(info)
                elif kind=='hard':info.type=tarfile.LNKTYPE;info.linkname=data;tar.addfile(info)
                else:info.type=tarfile.FIFOTYPE;tar.addfile(info)
        return lzma.compress(out.getvalue())

    def deb(self, rows=None):
        rows=rows if rows is not None else [('./usr/', 'dir', b''),('./usr/bin/', 'dir',b''),('./usr/bin/msgfmt','file',b'ordinary non-executable DATA')]
        members=[('debian-binary',b'2.0\n'),('control.tar.xz',self.tar_bytes([('./control','file',b'Package: gettext\nVersion: 0.21-12\nArchitecture: amd64\n')])),('data.tar.xz',self.tar_bytes(rows))]
        raw=b'!<arch>\n'
        for name,data in members:
            header=(name+'/').ljust(16)+'0'.ljust(12)+'0'.ljust(6)+'0'.ljust(6)+'100644'.ljust(8)+str(len(data)).ljust(10)+'`\n'
            raw+=header.encode()+data+(b'\n' if len(data)%2 else b'')
        return raw,dict(self.record, Size=str(len(raw)), SHA256=hashlib.sha256(raw).hexdigest())

    def test_signature_two_exact_anchors(self):
        result=m.validate_debian_signature_status(0,self.signature())
        self.assertEqual(set(result['primaries']),m.ANCHORS)
        self.assertIn('TRUST_UNDEFINED',result['trust'])

    def test_signature_exit0_expired_revoked_unknown_deny(self):
        for tag in ('EXPKEYSIG','KEYEXPIRED','REVKEYSIG','BADSIG','NO_PUBKEY','FAILURE'):
            with self.subTest(tag=tag),self.assertRaises(ValueError):
                m.validate_debian_signature_status(0,self.signature()+('[GNUPG:] '+tag+' 0\n').encode())
        with self.assertRaises(ValueError):m.validate_debian_signature_status(1,self.signature())

    def test_signature_missing_or_mismatched_anchor(self):
        raw=self.signature()
        with self.assertRaises(ValueError):m.validate_debian_signature_status(0,raw.replace(sorted(m.ANCHORS)[0].encode(),b'0'*40))
        with self.assertRaises(ValueError):m.validate_debian_signature_status(0,raw.replace(b'GOODSIG ',b'GOODSIG 0'))

    def test_real_official_metadata_gpg_and_signed_records(self):
        p=m.ROOT/'official-metadata'
        before=m.snapshot_debian_tool('/usr/bin/gpg')
        raw,identity=m.verify_debian_metadata(p/'bookworm-InRelease',p/'bookworm-amd64-Packages.xz','/usr/share/keyrings/debian-archive-keyring.gpg',self.root/'actual-auth')
        self.assertFalse(identity['strict_freshness']);self.assertFalse(identity['anti_replay_proven'])
        self.assertIsNone(identity['valid_until'])
        rows=[m.select_debian_package(raw,n) for n in m.SELECTED]
        self.assertEqual(len(rows),8);self.assertLess(sum(int(r['Size']) for r in rows),32*1024*1024)
        self.assertEqual(rows[0]['SHA256'],'8c1f9d43575373ce311f51d00a13afbb4888d63aa559a93a3472f5d77513b60c')
        self.assertEqual(before,m.snapshot_debian_tool('/usr/bin/gpg'))

    def test_metadata_changed_actual_owned_input_deny(self):
        p=m.ROOT/'official-metadata';bad=self.root/'InRelease';bad.write_bytes((p/'bookworm-InRelease').read_bytes()+b'changed')
        with self.assertRaises(ValueError):m.verify_debian_metadata(bad,p/'bookworm-amd64-Packages.xz','/usr/share/keyrings/debian-archive-keyring.gpg',self.root/'auth')
        self.assertFalse((self.root/'auth').exists())

    def test_package_duplicate_arch_version_path_or_size_deny(self):
        fields='Package: gettext\nVersion: 0.21-12\nArchitecture: amd64\nFilename: pool/main/g/gettext/g.deb\nSize: 20\nSHA256: '+'a'*64+'\nDepends: libc6 (>= 2.34)\n'
        self.assertEqual(m.select_debian_package(fields.encode(),'gettext')['Version'],'0.21-12')
        cases=[fields+'\n'+fields,fields.replace('amd64','arm64'),fields.replace('0.21-12','0.20'),fields.replace('pool/main/','pool/main/../'),fields.replace('Size: 20','Size: -1'),fields+'Package: gettext\n']
        for raw in cases:
            with self.subTest(raw=raw[:70]),self.assertRaises(ValueError):m.select_debian_package(raw.encode(),'gettext')
        with self.assertRaises(ValueError):m.select_debian_package(fields.encode(),'libc6')

    def test_real_owned_ar_data_and_safe_library_link(self):
        rows=[('./usr/lib/', 'dir',b''),('./usr/lib/libordinary.so.1.0','file',b'pure owned library DATA'),('./usr/lib/libordinary.so.1','link','libordinary.so.1.0')]
        raw,record=self.deb(rows);entries=m.inspect_debian_ar(raw,record)
        totals={'bytes':0,'entries':0};manifest=m.extract_owned_debian_data(entries,self.root/'data',totals)
        self.assertEqual((self.root/'data/usr/lib/libordinary.so.1').read_bytes(),b'pure owned library DATA')
        self.assertEqual(manifest['usr/lib/libordinary.so.1']['link'],'libordinary.so.1.0')
        self.assertEqual(totals['bytes'],len(b'pure owned library DATA'))

    def test_ar_changed_truncated_duplicate_and_codec_deny(self):
        raw,record=self.deb()
        with self.assertRaises(ValueError):m.inspect_debian_ar(raw+b'x',record)
        for bad in (raw[:-1],raw.replace(b'data.tar.xz/',b'data.tar.gz/'),raw+raw[8:]):
            r=dict(record,Size=str(len(bad)),SHA256=hashlib.sha256(bad).hexdigest())
            with self.assertRaises(ValueError):m.inspect_debian_ar(bad,r)

    def test_data_path_links_special_and_duplicates_deny(self):
        cases=[[('../escape','file',b'x')],[('/absolute','file',b'x')],[('same','file',b'a'),('same','file',b'b')],
               [('hard','hard','x')],[('special','fifo',b'')],[('link','link','/tmp/absolute')],
               [('link','link','../../escape')],[('link','link','missing')],[('link','link','target'),('target','link','link')],
               [('link','link','target'),('link/child','file',b'x'),('target','file',b't')]]
        for i,rows in enumerate(cases):
            raw,record=self.deb(rows)
            with self.subTest(i=i),self.assertRaises(ValueError):m.extract_owned_debian_data(m.inspect_debian_ar(raw,record),self.root/f'data-{i}',{'bytes':0,'entries':0})
        self.assertFalse((m.ROOT/'escape').exists())

    def test_existing_owned_target_canary_and_aggregate_cap(self):
        raw,record=self.deb();entries=m.inspect_debian_ar(raw,record);target=self.root/'data';target.mkdir();(target/'canary').write_bytes(b'KEEP')
        with self.assertRaises(FileExistsError):m.extract_owned_debian_data(entries,target,{'bytes':0,'entries':0})
        self.assertEqual((target/'canary').read_bytes(),b'KEEP')
        for totals in ({'bytes':128*1024*1024,'entries':0},{'bytes':0,'entries':10000}):
            with self.assertRaises(ValueError):m.extract_owned_debian_data(entries,self.root/'oversize',totals)

    def test_actual_owned_ELF_wrapper_missing_and_path_drift(self):
        bad=self.root/'tool';bad.write_bytes(b'#!/bin/sh\nexit 0\n');bad.chmod(0o755)
        with self.assertRaises(ValueError):m.snapshot_debian_tool(bad,native=True)
        with self.assertRaises(FileNotFoundError):m.snapshot_debian_tool(self.root/'missing',native=True)
        original=m.snapshot_debian_tool(bad);bad.write_bytes(b'changed')
        self.assertNotEqual(original,m.snapshot_debian_tool(bad))
        actual=self.root/'ordinary-real-python';actual.write_bytes(Path('/usr/bin/python3').resolve().read_bytes());actual.chmod(0o755)
        self.assertTrue(m.snapshot_debian_tool(actual,native=True)['sha256'])
        link=self.root/'alias';link.symlink_to(actual)
        with self.assertRaises(ValueError):m.snapshot_debian_tool(link,native=True)

    def test_ordinary_owned_child_log_cap_timeout_and_exit(self):
        # Executes preexisting real Python, never a downloaded Debian executable.
        env={'PATH':'/usr/bin:/bin','HOME':str(self.root),'LANG':'C'}
        good=m.run_debian_phase(['/usr/bin/python3','-c','print("ordinary")'],self.root,env,self.root/'good.log',2)
        self.assertTrue(good['passed'])
        bad=m.run_debian_phase(['/usr/bin/python3','-c','raise SystemExit(7)'],self.root,env,self.root/'bad.log',2)
        self.assertEqual(bad['exit'],7)
        timeout=m.run_debian_phase(['/usr/bin/python3','-c','import time; time.sleep(3)'],self.root,env,self.root/'timeout.log',.1)
        self.assertEqual(timeout['reason'],'TIMEOUT')
        noisy=m.run_debian_phase(['/usr/bin/python3','-c','import os;os.write(1,b"x"*3000000)'],self.root,env,self.root/'noisy.log',2)
        self.assertEqual(noisy['reason'],'LOG_LIMIT');self.assertLessEqual(noisy['log_bytes'],2*1024*1024)

    def test_synthetic_MO_parser_is_ordinary_not_GNU(self):
        original=b'hello\0';translated='bonjour é'.encode()+b'\0';raw=struct.pack('<7I',0x950412de,0,1,28,36,0,0)+struct.pack('<2I',5,44)+struct.pack('<2I',len(translated)-1,44+len(original))+original+translated
        path=self.root/'mock.mo';path.write_bytes(raw);self.assertEqual(m.read_native_mo(path)['hello'],'bonjour é')
        for bad in (b'bad',raw[:30],raw[:-1]):
            path.write_bytes(bad)
            with self.assertRaises(ValueError):m.read_native_mo(path)

    def test_executeFalse_default_no_native_or_git_launch(self):
        # Auth/data are controlled owned fixtures; this does not authenticate a real .deb.
        packages={n:self.root/(n+'.deb') for n in m.SELECTED};raw,record=self.deb()
        for path in packages.values():path.write_bytes(raw)
        runtime={p:m.snapshot_debian_tool(p) for p in m.HOST_TOOLS}
        with patch.object(m,'verify_debian_metadata',return_value=(b'controlled',{'strict_freshness':False})),patch.object(m,'select_debian_package',return_value=record),patch.object(m,'verify_debian_runtime') as native:
            result=m.prepare_owned_debian_msgfmt(None,None,None,packages,self.root/'prepared')
            native.assert_not_called()
        self.assertEqual(result['status'],'PREPARED_NOT_EXECUTED');self.assertFalse(result['HOST_INSTALL']);self.assertTrue(result['OWNED_EXTRACTION'])
        self.assertEqual(result['SUT_runs'],0);self.assertEqual(result['GitV3_runs'],0)
        self.assertEqual(runtime,{p:m.snapshot_debian_tool(p) for p in m.HOST_TOOLS})

    def test_finite_eight_packages_and_no_unbounded_installer(self):
        with self.assertRaises(ValueError):m.prepare_owned_debian_msgfmt(None,None,None,{},self.root/'reject')
        self.assertFalse((self.root/'reject').exists())
        with self.assertRaises(ValueError):m.run_debian_phase(['/usr/bin/true'],self.root,{},self.root/'bad.log',31)

    def test_runtime_original_drift_before_native_vector_deny(self):
        # Genuine msgfmt launch remains mocked and not credited.
        binary=self.root/'ordinary';binary.write_bytes(Path('/usr/bin/python3').resolve().read_bytes());binary.chmod(0o755)
        env={'LD_LIBRARY_PATH':str(self.root)}
        with self.assertRaises(ValueError):m.verify_debian_runtime(binary,'/lib64/ld-linux-x86-64.so.2',[],self.root,env,{})
        self.assertFalse((self.root/'loader-list.log').exists())

    def test_primary_and_cancel_object_preserved_when_final_observation_fails(self):
        packages={n:self.root/(n+'.deb') for n in m.SELECTED}
        for path in packages.values():path.write_bytes(b'NOT_RUN')
        actual=m.snapshot_debian_tool
        for i,primary in enumerate((ValueError('ORIGINAL_PRIMARY'),KeyboardInterrupt('CONTROLLED_CANCEL'))):
            calls=0
            def leased(path,native=False):
                nonlocal calls
                calls+=1
                if calls>len(m.HOST_TOOLS):raise RuntimeError('FINAL_OBSERVATION_FAILURE')
                return actual(path,native)
            with patch.object(m,'snapshot_debian_tool',side_effect=leased),patch.object(m,'verify_debian_metadata',side_effect=primary):
                try:m.prepare_owned_debian_msgfmt(None,None,None,packages,self.root/f'failure-{i}')
                except BaseException as error:
                    self.assertIsInstance(error,BaseExceptionGroup)
                    self.assertIs(error.exceptions[0],primary)
                    self.assertEqual(str(error.exceptions[1]),'FINAL_OBSERVATION_FAILURE')
                else:self.fail('Original exception missing')

    def test_source_future_date_and_existing_auth_namespace_deny(self):
        p=m.ROOT/'official-metadata'
        with patch.object(m.time,'time',return_value=0),self.assertRaises(ValueError):
            m.verify_debian_metadata(p/'bookworm-InRelease',p/'bookworm-amd64-Packages.xz','/usr/share/keyrings/debian-archive-keyring.gpg',self.root/'future-auth')
        existing=self.root/'existing';existing.mkdir();canary=existing/'canary';canary.write_bytes(b'KEEP')
        with self.assertRaises(FileExistsError):m.verify_debian_metadata(p/'bookworm-InRelease',p/'bookworm-amd64-Packages.xz','/usr/share/keyrings/debian-archive-keyring.gpg',existing)
        self.assertEqual(canary.read_bytes(),b'KEEP')

    def test_control_record_identity_mismatch_and_expired_aggregate_deadline_deny(self):
        raw,record=self.deb()
        wrong=dict(record,Version='0.20')
        with self.assertRaises(ValueError):m.inspect_debian_ar(raw,wrong)
        entries=m.inspect_debian_ar(raw,record)
        with self.assertRaises(TimeoutError):m.extract_owned_debian_data(entries,self.root/'expired',{'bytes':0,'entries':0},deadline=0)

    def test_controlled_cancel_and_reader_close_keep_original_objects(self):
        # Real owned preexisting Python child; cancellation/reader-close signals
        # are controlled delegates, not proof of native IO cancellation closure.
        actual=m.selectors.DefaultSelector;cancel=KeyboardInterrupt('ORDINARY_CANCEL');close=RuntimeError('ORDINARY_READER_CLOSE')
        selector=actual()
        with patch.object(selector,'select',side_effect=cancel),patch.object(selector,'close',side_effect=close),patch.object(m.selectors,'DefaultSelector',return_value=selector):
            try:m.run_debian_phase(['/usr/bin/python3','-c','import time;time.sleep(3)'],self.root,{'PATH':'/usr/bin:/bin'},self.root/'cancel.log',2)
            except BaseExceptionGroup as error:
                self.assertIs(error.exceptions[0],cancel);self.assertIs(error.exceptions[1],close)
            else:self.fail('Original cancellation missing')
        selector.close()

    def test_owned_payload_drift_denied_before_first_native_delegate(self):
        # Actual owned file mutation and a controlled native delegate, never a
        # downloaded executable. Must fail before any target-loader invocation.
        packages={n:self.root/(n+'.deb') for n in m.SELECTED};raw,record=self.deb()
        for path in packages.values():path.write_bytes(raw)
        actual=m.extract_owned_debian_data
        def changed(entries,destination,totals,deadline=None):
            result=actual(entries,destination,totals,deadline)
            if Path(destination).name=='gettext':
                path=Path(destination)/'usr/bin/msgfmt';path.write_bytes(Path('/usr/bin/python3').resolve().read_bytes());path.chmod(0o755)
            return result
        with patch.object(m,'verify_debian_metadata',return_value=(b'controlled',{'strict_freshness':False})),patch.object(m,'select_debian_package',return_value=record),patch.object(m,'extract_owned_debian_data',side_effect=changed),patch.object(m,'verify_debian_runtime',side_effect=ValueError('CONTROLLED_NATIVE_DELEGATE')) as native:
            with self.assertRaises(BaseException):m.prepare_owned_debian_msgfmt(None,None,None,packages,self.root/'pre-native-drift',execute=True)
            native.assert_not_called()

    def test_real_existing_ELF_copy_ABI_dependency_allowlist_deny(self):
        # Existing host Python byte-copy only: real readelf and loader --list
        # inventory, no downloaded .deb, Python main, GNU msgfmt or Git run.
        binary=self.root/'owned-existing-python';binary.write_bytes(Path('/usr/bin/python3').resolve().read_bytes());binary.chmod(0o755)
        before=m.snapshot_debian_tool(binary,native=True)
        runtime={p:m.snapshot_debian_tool(p) for p in m.HOST_TOOLS};leases={}
        with self.assertRaisesRegex(ValueError,'pre-load identity allowlist'):
            m.verify_debian_runtime(binary,'/lib64/ld-linux-x86-64.so.2',[],self.root,{'PATH':'/usr/bin:/bin','HOME':str(self.root),'LC_ALL':'C'},runtime,leases)
        self.assertTrue((self.root/'loader-list.log').exists())
        self.assertTrue((self.root/'elf-2.log').exists())
        self.assertEqual(before,m.snapshot_debian_tool(binary,native=True))
        self.assertEqual(runtime,{p:m.snapshot_debian_tool(p) for p in m.HOST_TOOLS})
        self.assertIn('binary',leases);self.assertIn('loader',leases)

    def test_exact_observed_doc_DATA_link_only_no_missing_library_admission(self):
        row=('usr/share/doc/libgomp1','link','gcc-12-base');raw,record=self.deb([row])
        destination=self.root/'libgomp1';manifest=m.extract_owned_debian_data(m.inspect_debian_ar(raw,record),destination,{'bytes':0,'entries':0})
        link=destination/'usr/share/doc/libgomp1'
        self.assertTrue(link.is_symlink());self.assertFalse(link.exists());self.assertEqual(os.readlink(link),'gcc-12-base')
        self.assertTrue(manifest[row[0]]['documentation_DATA_only'])
        self.assertEqual(manifest[row[0]]['canonical_owned_target'],'usr/share/doc/gcc-12-base')
        cases=[('usr/lib/x86_64-linux-gnu/libgomp.so.1','link','gcc-12-base'),
               ('usr/share/doc/libgomp1','link','gcc-13-base'),('usr/share/doc/libgomp1','link','/usr/share/doc/gcc-12-base')]
        for i,bad in enumerate(cases):
            root=self.root/f'case-{i}';root.mkdir();raw,record=self.deb([bad])
            with self.assertRaises(ValueError):m.extract_owned_debian_data(m.inspect_debian_ar(raw,record),root/'libgomp1',{'bytes':0,'entries':0})
        raw,record=self.deb([row])
        with self.assertRaises(ValueError):m.extract_owned_debian_data(m.inspect_debian_ar(raw,record),self.root/'wrong-package',{'bytes':0,'entries':0})


if __name__ == '__main__':
    unittest.main(verbosity=2)
