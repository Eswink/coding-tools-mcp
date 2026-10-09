"""New ordinary controls. Never runs GNU configure/build/install or Git build.

Synthetic archive/MO/status and mocked ldd controls check denial/parser branches;
they are not genuine msgfmt or compiler/runtime admission evidence.
"""
import sys
sys.dont_write_bytecode = True
import ast
import hashlib
import io
import json
import lzma
import os
from pathlib import Path
import struct
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import owned_gettext_prepare as m


class GettextPreparationControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ordinary-', dir=m.OWNED_ROOT)
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_real_current_GPG_authentication_no_source_execution(self):
        compressed = m.verify_gettext_source(m.OWNED_ROOT/'gettext-1.0.tar.xz',
            m.OWNED_ROOT/'gettext-1.0.tar.xz.sig', m.OWNED_ROOT/'official-gnu-keyring.gpg', self.root/'auth')
        self.assertEqual(hashlib.sha256(compressed).hexdigest(),m.SOURCE_SHA)
        receipt=json.loads((self.root/'auth/source-identity.json').read_text())
        self.assertFalse(receipt['SOURCE_EXECUTION']);self.assertFalse(receipt['OWNED_INSTALL'])
        self.assertFalse(receipt['HOST_INSTALL']);self.assertEqual(receipt['SUT_runs'],0)

    def test_expired_real_status_exit_zero_rejected(self):
        for path in ('developer-signature.status','developer-signature02.status'):
            raw=(m.OWNED_ROOT/path).read_bytes()
            with self.assertRaises(ValueError):m.validate_gettext_signature_status(0,raw)

    def test_current_signer_wrong_exit_unknown_bad_missing_duplicate_refused(self):
        raw=(m.OWNED_ROOT/'current-developer-signature.status').read_bytes()
        m.validate_gettext_signature_status(0,raw)
        vectors=[(1,raw),(0,raw+b'[GNUPG:] KEYEXPIRED 1\n'),(0,raw+b'[GNUPG:] NEW_UNKNOWN 1\n'),
                 (0,raw.replace(m.SIGNER.encode(),b'0'*40)),(0,b''),(0,raw+raw)]
        for code,status in vectors:
            with self.subTest(status=status[-70:]):
                with self.assertRaises(ValueError):m.validate_gettext_signature_status(code,status)

    def test_archive_signature_key_byte_changes_refused_before_GPG(self):
        inputs=[m.OWNED_ROOT/'gettext-1.0.tar.xz',m.OWNED_ROOT/'gettext-1.0.tar.xz.sig',m.OWNED_ROOT/'official-gnu-keyring.gpg']
        for i in range(3):
            altered=self.root/f'altered-{i}';raw=inputs[i].read_bytes();altered.write_bytes(bytes([raw[0]^1])+raw[1:])
            vector=list(inputs);vector[i]=altered
            with patch.object(m.subprocess,'run',side_effect=AssertionError('GPG must not start')):
                with self.assertRaises(ValueError):m.verify_gettext_source(*vector,self.root/f'bad-{i}')

    def test_existing_destination_canary_unchanged(self):
        target=self.root/'exists';target.mkdir();canary=target/'canary';canary.write_bytes(b'preserve')
        with self.assertRaises(FileExistsError):m.prepare_owned_gettext(None,None,None,target)
        self.assertEqual(canary.read_bytes(),b'preserve')

    def test_foreign_or_symlink_parent_refused(self):
        link=self.root/'link';link.symlink_to('/tmp',target_is_directory=True)
        with self.assertRaises(ValueError):m.prepare_owned_gettext(None,None,None,link/'deny')
        with self.assertRaises(ValueError):m.prepare_owned_gettext(None,None,None,Path('/tmp/deny'))

    def test_real_archive_exact_vector_no_extraction_or_execution(self):
        compressed=(m.OWNED_ROOT/'gettext-1.0.tar.xz').read_bytes()
        members=m.inspect_gettext_archive(compressed)
        self.assertEqual((len(members),sum(x.isfile() for x in members),sum(x.isdir() for x in members)),(9346,9038,308))
        self.assertEqual(sum(x.size for x in members if x.isfile()),247291870)

    def test_real_owned_extraction_default_never_executes_GNU_and_preserves_identity(self):
        target=self.root/'prepared'
        result=m.prepare_owned_gettext(m.OWNED_ROOT/'gettext-1.0.tar.xz',
            m.OWNED_ROOT/'gettext-1.0.tar.xz.sig',m.OWNED_ROOT/'official-gnu-keyring.gpg',target)
        self.assertEqual(result['status'],'PREPARED_NOT_EXECUTED')
        self.assertEqual(result['original_source_entries'],9346)
        self.assertFalse(result['SOURCE_EXECUTION']);self.assertFalse(result['OWNED_INSTALL'])
        self.assertFalse(result['HOST_INSTALL']);self.assertFalse(result['phases'])
        self.assertTrue(result['original_source_unchanged']);self.assertTrue(result['runtime_unchanged'])
        self.assertFalse((target/'owned-prefix').exists())
        with tarfile.open(m.OWNED_ROOT/'gettext-1.0.tar.xz',mode='r:xz') as tar:
            for name in ['gettext-1.0/configure','gettext-1.0/README','gettext-1.0/gettext-tools']:
                member=tar.getmember(name);info=(target/'source'/name).stat()
                self.assertEqual(info.st_mode&0o777,member.mode)
                self.assertEqual(int(info.st_mtime),int(member.mtime))

    def test_unsafe_archive_paths_links_modes_duplicates_sizes_refused(self):
        vectors=[('gettext-1.0/../escape',tarfile.REGTYPE,0o644,0),
                 ('gettext-1.0/link',tarfile.SYMTYPE,0o644,0),
                 ('gettext-1.0/device',tarfile.CHRTYPE,0o644,0),
                 ('gettext-1.0/setuid',tarfile.REGTYPE,0o4644,0),
                 ('/gettext-1.0/absolute',tarfile.REGTYPE,0o644,0),
                 ('gettext-1.0/./dot',tarfile.REGTYPE,0o644,0),
                 ('gettext-1.0/huge',tarfile.REGTYPE,0o644,41*1024*1024)]
        for name,kind,mode,size in vectors:
            stream=io.BytesIO()
            with tarfile.open(fileobj=stream,mode='w') as tar:
                item=tarfile.TarInfo(name);item.type=kind;item.mode=mode;item.size=size
                tar.addfile(item,io.BytesIO(b'\0'*size) if size else None)
            with self.assertRaises(ValueError):m.inspect_gettext_archive(lzma.compress(stream.getvalue()),exact=False)
        stream=io.BytesIO()
        with tarfile.open(fileobj=stream,mode='w') as tar:
            for _ in range(2):tar.addfile(tarfile.TarInfo('gettext-1.0/duplicate'))
        with self.assertRaises(ValueError):m.inspect_gettext_archive(lzma.compress(stream.getvalue()),exact=False)

    def test_expansion_bound_precedes_member_discovery(self):
        with patch.object(m.lzma,'open') as opened, patch.object(m.tarfile,'open',side_effect=AssertionError('no discovery')):
            opened.return_value.__enter__.return_value.read.return_value=b'x'*(256*1024*1024+1)
            with self.assertRaises(ValueError):m.inspect_gettext_archive(b'synthetic')
            opened.return_value.__enter__.return_value.read.assert_called_once_with(256*1024*1024+1)

    def test_native_wrapper_missing_and_symlink_refused(self):
        wrapper=self.root/'wrapper';wrapper.write_bytes(b'#!/bin/sh\nexit 0\n');wrapper.chmod(0o700)
        link=self.root/'link';link.symlink_to('/usr/bin/git')
        for path in (wrapper,link,self.root/'missing'):
            with self.assertRaises((OSError,ValueError)):m.snapshot_owned_tool(path,native=True)

    def test_real_access_time_change_does_not_conceal_content_or_identity_drift(self):
        path=self.root/'ordinary-data';path.write_bytes(b'exact original bytes')
        os.utime(path,ns=(1_000_000_000,1_000_000_000))
        before=path.stat();first=m.snapshot_owned_tool(path);after=path.stat()
        self.assertGreater(after.st_atime_ns,before.st_atime_ns)
        self.assertEqual(first,m.snapshot_owned_tool(path))
        path.write_bytes(b'changed bytes')
        self.assertNotEqual(first,m.snapshot_owned_tool(path))

    def test_unknown_missing_foreign_dependency_mock_denials(self):
        # Real ELF is read, but ldd text deliberately mocked: branch controls only.
        for text in (b'libmissing.so => not found\n',b'unknown\n',b'/etc/passwd (0x1234)\n',b''):
            result=subprocess.CompletedProcess([],0,text,b'')
            with patch.object(m.subprocess,'run',return_value=result):
                with self.assertRaises(ValueError):m.inspect_msgfmt_dependencies('/usr/bin/git',self.root,{'PATH':'/usr/bin:/bin'})

    def test_independent_MO_parser_little_big_endian_and_bounds(self):
        for endian in ('<','>'):
            key=b'hello';value='bonjour é'.encode();raw=struct.pack(endian+'7I',0x950412de,0,1,28,36,0,0)
            raw+=struct.pack(endian+'2I',len(key),44)+struct.pack(endian+'2I',len(value),50)+key+b'\0'+value+b'\0'
            path=self.root/'synthetic.mo';path.write_bytes(raw)
            self.assertEqual(m.read_message_catalog(path),{'hello':'bonjour é'})
            path.write_bytes(raw[:-1])
            with self.assertRaises(ValueError):m.read_message_catalog(path)

    def test_owned_process_actual_success_failure_and_timeout(self):
        env={'PATH':'/usr/bin:/bin','HOME':str(self.root),'LANG':'C','LC_ALL':'C','TZ':'UTC'}
        for i,(source,seconds,passed,reason) in enumerate([('print("ordinary")',2,True,None),
                ('raise SystemExit(7)',2,False,None),('import time; time.sleep(30)',0.15,False,'TIMEOUT'),
                ('import os,time; os.close(1); os.close(2); time.sleep(30)',0.15,False,'TIMEOUT')]):
            result=m.run_owned_gettext_phase(['/usr/bin/python3','-c',source],self.root,env,self.root/f'process-{i}.log',seconds)
            self.assertEqual(result['passed'],passed);self.assertEqual(result['reason'],reason)
            self.assertLess(result['seconds'],5)

    def test_owned_process_actual_log_limit_and_fresh_log_canary(self):
        env={'PATH':'/usr/bin:/bin','HOME':str(self.root),'LANG':'C','LC_ALL':'C','TZ':'UTC'}
        vector=['/usr/bin/python3','-c','import sys;sys.stdout.write("x"*3000000)']
        path=self.root/'overflow.log';result=m.run_owned_gettext_phase(vector,self.root,env,path,2)
        self.assertEqual(result['reason'],'LOG_LIMIT');self.assertFalse(result['passed']);self.assertLessEqual(path.stat().st_size,2*1024*1024)
        canary=self.root/'existing.log';canary.write_bytes(b'preserve')
        with self.assertRaises(FileExistsError):m.run_owned_gettext_phase(vector,self.root,env,canary,2)
        self.assertEqual(canary.read_bytes(),b'preserve')

    def test_default_source_vectors_and_execute_false_AST(self):
        source=Path(m.__file__).read_text();tree=ast.parse(source)
        fn=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='prepare_owned_gettext')
        self.assertFalse(ast.literal_eval(fn.args.defaults[0]))
        self.assertIn("['./configure','--prefix='+str(prefix)],120",source)
        self.assertIn("['/usr/bin/make','-j2','all'],480",source)
        self.assertIn("['/usr/bin/make','install'],60",source)
        self.assertNotIn('--disable-',source);self.assertNotIn('NO_GETTEXT',source)
        self.assertNotIn('sudo',source);self.assertNotIn('/usr/local/bin/git',source)
        self.assertIn("'TMPDIR':str(temporary)",source)

    def test_actual_readonly_tool_runtime_lease(self):
        before={p:m.snapshot_owned_tool(p) for p in m.TOOLS}
        after={p:m.snapshot_owned_tool(p) for p in m.TOOLS}
        self.assertEqual(before,after)


if __name__ == '__main__':
    unittest.main(verbosity=2)
