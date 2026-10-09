"""Ordinary source-input controls; no CI identity, installer, SUT or host writes."""
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
import owned_git_prepare as original

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
        changed=self.root/'source.tar.xz';changed.write_bytes((ROOT/'git-2.55.0.tar.xz').read_bytes()[:-1]+b'X');evidence=self.root/'auth'
        with self.assertRaisesRegex(ValueError,'bytes differ'):original.verify_git_source(changed,ROOT/'git-2.55.0.tar.sign',ROOT/'junio-ubuntu-public-key.asc',evidence)
        self.assertFalse(evidence.exists())
    def test_bad_key_rejected_before_evidence(self):
        changed=self.root/'public-key.asc';changed.write_bytes(b'not a signing key');evidence=self.root/'auth'
        with self.assertRaisesRegex(ValueError,'bytes differ'):original.verify_git_source(ROOT/'git-2.55.0.tar.xz',ROOT/'git-2.55.0.tar.sign',changed,evidence)
        self.assertFalse(evidence.exists())
    def test_actual_official_signature_and_all_source_entries(self):
        verified=original.verify_git_source(ROOT/'git-2.55.0.tar.xz',ROOT/'git-2.55.0.tar.sign',ROOT/'junio-ubuntu-public-key.asc',self.root/'auth')
        source=original.extract_owned_git_source(verified,self.root/'destination')
        self.assertEqual((source/'INSTALL').read_bytes(),(ROOT/'official-tar-INSTALL').read_bytes())
        self.assertEqual(len([p for p in source.rglob('*') if p.is_file() and not p.is_symlink()]),4764)
        self.assertEqual(len([p for p in source.rglob('*') if p.is_symlink()]),3)
        self.assertFalse((source/'git').exists())
if __name__=='__main__':unittest.main(verbosity=2)
