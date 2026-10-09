"""Ordinary source-input controls; no CI identity, installer, SUT or host writes."""
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
import owned_git_prepare_v2 as original

ROOT=original.OWNED_ROOT
class OwnedSourceControls(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='ordinary-source-',dir=ROOT)
        self.root=Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()
    def archive(self, entries):
        buffer=io.BytesIO()
        with tarfile.open(fileobj=buffer,mode='w') as archive:
            for name,kind,data in entries:
                item=tarfile.TarInfo(name)
                if kind=='file':
                    item.size=len(data);item.mode=0o644;archive.addfile(item,io.BytesIO(data))
                elif kind=='symlink':
                    item.type=tarfile.SYMTYPE;item.linkname=data;archive.addfile(item)
                elif kind=='hardlink':
                    item.type=tarfile.LNKTYPE;item.linkname=data;archive.addfile(item)
                elif kind=='device':
                    item.type=tarfile.CHRTYPE;archive.addfile(item)
        return buffer.getvalue()
    def reject(self,entries,expected):
        dest=self.root/'destination'
        with self.assertRaisesRegex(ValueError,expected): original.extract_owned_git_source(self.archive(entries),dest)
        self.assertFalse(dest.exists())
    def test_traversal_rejected_before_destination(self):self.reject([('git-2.55.0/../../foreign','file',b'bad')],'escapes')
    def test_absolute_path_rejected(self):self.reject([('/git-2.55.0/foreign','file',b'bad')],'escapes')
    def test_wrong_prefix_rejected(self):self.reject([('git-foreign/a','file',b'bad')],'wrong prefix')
    def test_duplicate_rejected(self):self.reject([('git-2.55.0/a','file',b'1'),('git-2.55.0/a','file',b'2')],'duplicates')
    def test_escaping_relative_link_rejected(self):self.reject([('git-2.55.0/a','symlink','../../foreign')],'symlink escapes')
    def test_absolute_link_rejected(self):self.reject([('git-2.55.0/a','symlink','/foreign')],'symlink escapes')
    def test_member_under_link_rejected(self):self.reject([('git-2.55.0/a','symlink','d'),('git-2.55.0/a/child','file',b'x')],'under symlink')
    def test_hardlink_rejected(self):self.reject([('git-2.55.0/a','hardlink','git-2.55.0/b')],'hard-linked')
    def test_device_rejected(self):self.reject([('git-2.55.0/a','device','')],'special')
    def test_existing_destination_preserved(self):
        dest=self.root/'destination';dest.mkdir();(dest/'canary').write_bytes(b'original')
        with self.assertRaisesRegex(ValueError,'fresh owned'):original.extract_owned_git_source(self.archive([('git-2.55.0/a','file',b'x')]),dest)
        self.assertEqual((dest/'canary').read_bytes(),b'original')
    def test_ordinary_confined_link_and_detached_bytes(self):
        source=original.extract_owned_git_source(self.archive([('git-2.55.0/d/data','file',b'original'),('git-2.55.0/link','symlink','d/data')]),self.root/'destination')
        self.assertEqual((source/'link').read_bytes(),b'original');self.assertTrue((source/'link').resolve().is_relative_to(source));self.assertEqual((source/'d/data').stat().st_mode&0o777,0o644)
    def test_bad_source_rejected_before_evidence(self):
        changed=self.root/'source.tar.xz';changed.write_bytes((ROOT.parent/'git-2.55.0.tar.xz').read_bytes()[:-1]+b'X');evidence=self.root/'auth'
        with self.assertRaisesRegex(ValueError,'bytes differ'):original.verify_git_source(changed,ROOT.parent/'git-2.55.0.tar.sign',ROOT.parent/'junio-ubuntu-public-key.asc',evidence)
        self.assertFalse(evidence.exists())
    def test_bad_key_rejected_before_evidence(self):
        changed=self.root/'public-key.asc';changed.write_bytes(b'not a signing key');evidence=self.root/'auth'
        with self.assertRaisesRegex(ValueError,'bytes differ'):original.verify_git_source(ROOT.parent/'git-2.55.0.tar.xz',ROOT.parent/'git-2.55.0.tar.sign',changed,evidence)
        self.assertFalse(evidence.exists())
    def test_actual_official_signature_and_all_source_entries(self):
        verified=original.verify_git_source(ROOT.parent/'git-2.55.0.tar.xz',ROOT.parent/'git-2.55.0.tar.sign',ROOT.parent/'junio-ubuntu-public-key.asc',self.root/'auth')
        source=original.extract_owned_git_source(verified,self.root/'destination')
        self.assertEqual((source/'INSTALL').read_bytes(),(ROOT.parent/'official-tar-INSTALL').read_bytes())
        self.assertEqual(len([p for p in source.rglob('*') if p.is_file() and not p.is_symlink()]),4764)
        self.assertEqual(len([p for p in source.rglob('*') if p.is_symlink()]),3)
        self.assertFalse((source/'git').exists())

class GenuineToolchainControls(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='ordinary-tool-',dir=ROOT);self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def test_missing_cargo_blocks_zero_build(self):
        r=original.verify_native_build_toolchain(self.root/'missing',cargo_path=original.TOOLCHAIN/'missing-cargo')
        self.assertFalse(r['passed']);self.assertEqual(r['build_runs'],0);self.assertIn('FileNotFoundError',r['blocked_reason']);self.assertFalse((self.root/'missing'/'actual-build.log').exists())
    def test_bad_cargo_hash_blocks_before_versions(self):
        r=original.verify_native_build_toolchain(self.root/'bad-cargo',cargo_sha='0'*64)
        self.assertFalse(r['passed']);self.assertEqual(r['build_runs'],0);self.assertEqual(r['versions'],[]);self.assertIn('Cargo exact hash mismatch',r['blocked_reason'])
    def test_bad_rustc_hash_blocks_before_versions(self):
        r=original.verify_native_build_toolchain(self.root/'bad-rustc',rustc_sha='0'*64)
        self.assertFalse(r['passed']);self.assertEqual(r['build_runs'],0);self.assertEqual(r['versions'],[]);self.assertIn('Rustc exact hash mismatch',r['blocked_reason'])
    def test_nonapproved_payload_directory_blocks(self):
        r=original.verify_native_build_toolchain(self.root/'foreign',cargo_path=Path('/usr/bin/git'))
        self.assertFalse(r['passed']);self.assertEqual(r['build_runs'],0);self.assertIn('unapproved toolchain path',r['blocked_reason'])
    def test_actual_payload_versions_runtime_and_scoped_env(self):
        r=original.verify_native_build_toolchain(self.root/'real')
        self.assertTrue(r['passed'],r.get('blocked_reason'));self.assertEqual(r['runtime_before'],r['runtime_after']);self.assertEqual(r['build_runs'],0)
        self.assertEqual(r['build_env']['PATH'],str(original.TOOLCHAIN)+':/usr/bin:/bin');self.assertEqual(r['build_env']['RUSTC'],str(original.TOOLCHAIN/'rustc'))
        self.assertEqual(set(r['build_env']),{'PATH','RUSTC','CARGO_HOME','HOME','LANG','LC_ALL','TZ'});self.assertTrue(all(v['exit_code']==0 for v in r['versions']))
        self.assertTrue(Path(r['build_env']['CARGO_HOME']).is_relative_to(ROOT));self.assertEqual(len(r['runtime_before']),9)
if __name__=='__main__':unittest.main(verbosity=2)
