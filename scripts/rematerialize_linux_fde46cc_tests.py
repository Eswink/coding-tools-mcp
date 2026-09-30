"""Offline transfer contracts. No network, unpacking or executable launch."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import rematerialize_linux_fde46cc as transfer


class TransferTests(unittest.TestCase):
    def metadata(self):
        return dict(id=transfer.ARTIFACT_ID, name=transfer.ARTIFACT_NAME, expired=False,
                    size_in_bytes=transfer.ARCHIVE_SIZE, digest='sha256:' + transfer.ARCHIVE_SHA256,
                    workflow_run=dict(id=transfer.RUN_ID, head_sha=transfer.SOURCE_SHA,
                                      head_branch='ci/preliminary-packages-20260930',
                                      repository_id=transfer.REPOSITORY_ID,
                                      head_repository_id=transfer.REPOSITORY_ID))

    def fixture(self, directory):
        data=b'opaque original ZIP bytes; never extracted here'  # 47 bytes: five tiny parts
        self.assertEqual(len(data),47)
        self.addCleanup(patch.stopall)
        patch.object(transfer,'ARCHIVE_SIZE',len(data)).start()
        patch.object(transfer,'ARCHIVE_SHA256',hashlib.sha256(data).hexdigest()).start()
        patch.object(transfer,'CHUNK_BYTES',10).start()
        original=directory/'original.zip';original.write_bytes(data)
        parts=directory/'chunks'
        receipt=transfer.split_archive(original,parts,'a'*40,'123')
        return original,parts,receipt,data

    def test_production_constants_are_fixed_and_bounded(self):
        self.assertEqual(transfer.ARTIFACT_ID,11114636713)
        self.assertEqual(transfer.RUN_ID,36748964715)
        self.assertEqual(transfer.ARCHIVE_SIZE,97384787)
        self.assertEqual(transfer.ARCHIVE_SHA256,'e7d8c352ba7f384c8c5dce25b74620d43211508d4ce7dcf960dae4b53c7d720d')
        self.assertLess(transfer.CHUNK_BYTES,24*1024*1024)
        self.assertEqual((transfer.ARCHIVE_SIZE+transfer.CHUNK_BYTES-1)//transfer.CHUNK_BYTES,5)

    def test_exact_metadata_and_all_identity_mutations(self):
        transfer.validate_metadata(self.metadata())
        fields=[('id',1),('id',True),('name','foreign'),('expired',True),
                ('size_in_bytes',1),('digest','sha256:'+'0'*64)]
        for key,value in fields:
            item=self.metadata();item[key]=value
            with self.subTest(key=key),self.assertRaises(transfer.TransferError):transfer.validate_metadata(item)
        for key in ['id','head_sha','head_branch','repository_id','head_repository_id']:
            item=self.metadata();item['workflow_run'][key]='wrong'
            with self.subTest(key=key),self.assertRaises(transfer.TransferError):transfer.validate_metadata(item)

    def test_split_join_preserves_original_and_receipt_scope(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);original,parts,receipt,data=self.fixture(root)
            output=root/'reassembled.zip';transfer.join_archive(parts,output)
            self.assertEqual(output.read_bytes(),data);self.assertEqual(original.read_bytes(),data)
            self.assertEqual([p['size'] for p in receipt['chunks']],[10,10,10,10,7])
            self.assertFalse(receipt['release_approved']);self.assertFalse(receipt['extraction_performed'])
            self.assertFalse(receipt['binary_execution_performed'])

    def test_bad_original_size_digest_and_symlink_are_refused(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);original,_,_,data=self.fixture(root)
            for bad in [data+b'x',b'x'*len(data)]:
                original.write_bytes(bad)
                with self.assertRaises(transfer.TransferError):transfer.split_archive(original,root/'bad','a'*40,'123')
                self.assertFalse((root/'bad').exists())
            original.write_bytes(data);link=root/'link';link.symlink_to(original)
            with self.assertRaises(transfer.TransferError):transfer.validate_archive(link)

    def test_tampered_chunk_and_existing_output_are_refused(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);_,parts,_,data=self.fixture(root);output=root/'out'
            output.write_bytes(b'keep')
            with self.assertRaises(transfer.TransferError):transfer.join_archive(parts,output)
            self.assertEqual(output.read_bytes(),b'keep')
            part=parts/'original.zip.part-00';part.write_bytes(b'x'*10)
            with self.assertRaises(transfer.TransferError):transfer.join_archive(parts,root/'new')
            self.assertFalse((root/'new').exists())

    def test_wrong_source_scope_inventory_path_offsets_and_order_are_refused(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);_,parts,receipt,_=self.fixture(root);path=parts/'receipt.json'
            mutations=[]
            for field in ['source_sha','source_tree','sha256','artifact_id','run_id']:
                item=copy.deepcopy(receipt);item['original'][field]='wrong';mutations.append(item)
            item=copy.deepcopy(receipt);item['release_approved']=True;mutations.append(item)
            item=copy.deepcopy(receipt);item['chunks']=item['chunks'][:-1];mutations.append(item)
            for field,value in [('name','../escape'),('offset',1),('size',True),('sha256','0'*64)]:
                item=copy.deepcopy(receipt);item['chunks'][0][field]=value;mutations.append(item)
            item=copy.deepcopy(receipt);item['chunks'].reverse();mutations.append(item)
            for item in mutations:
                path.write_text(json.dumps(item))
                with self.assertRaises(transfer.TransferError):transfer.join_archive(parts,root/'out')
                self.assertFalse((root/'out').exists())

    def test_missing_extra_or_symlinked_parts_are_refused(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);original,parts,_,_=self.fixture(root);part=parts/'original.zip.part-00'
            part.rename(root/'saved')
            with self.assertRaises(transfer.TransferError):transfer.join_archive(parts,root/'out')
            part.symlink_to(root/'saved')
            with self.assertRaises(transfer.TransferError):transfer.join_archive(parts,root/'out')
            part.unlink();(root/'saved').rename(part);(parts/'extra').write_bytes(b'')
            with self.assertRaises(transfer.TransferError):transfer.join_archive(parts,root/'out')

    def test_nonhosted_fetch_stops_before_network(self):
        with patch.dict(transfer.os.environ,{},clear=True),patch.object(transfer,'github_read') as read:
            with self.assertRaises(transfer.TransferError):transfer.rematerialize_fixed_artifact(Path('/tmp/foreign'))
            read.assert_not_called()

    def test_github_failure_never_includes_credentials_or_redirect(self):
        with tempfile.TemporaryDirectory() as raw:
            failure=type('Failure',(),{'returncode':1,'stderr':b'private-token signed-url'})()
            with patch.object(transfer.subprocess,'run',return_value=failure):
                with self.assertRaises(transfer.TransferError) as error:transfer.github_read('/fixed',Path(raw)/'result')
            self.assertEqual(str(error.exception),'github_artifact_read_failed')

    def test_workflow_only_uploads_receipt_and_five_parts(self):
        root=Path(__file__).resolve().parents[1]
        text=(root/'.github/workflows/rematerialize-linux-fde46cc.yml').read_text()
        self.assertIn('contents: read',text);self.assertIn('actions: read',text)
        self.assertNotIn('inputs:',text);self.assertNotIn('write',text)
        self.assertEqual(text.count('actions/upload-artifact@'),6)
        self.assertEqual(text.count('compression-level: 0'),6)
        for index in range(5):self.assertIn(f'/chunks/original.zip.part-{index:02d}',text)
        self.assertNotIn('cargo ',text);self.assertNotIn('npm ',text)


if __name__=='__main__':unittest.main()
