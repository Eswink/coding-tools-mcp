"""Synthetic frozen manifests in real temporary Git repositories only."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import reviewed_source_gate as gate
from source_provenance_gate_tests import repository, command, commit


def descriptor(data):
    if data is None:
        return None
    sha = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
    return dict(mode='100644', blob_sha=sha, sha256=hashlib.sha256(data).hexdigest())


class ReviewedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        repository(self.root)
        (self.root / 'modified.txt').write_bytes(b'before')
        (self.root / 'deleted.bin').write_bytes(b'gone\x00')
        self.base = commit(self.root)
        (self.root / 'modified.txt').write_bytes(b'after')
        (self.root / 'deleted.bin').unlink()
        (self.root / 'added.bin').write_bytes(b'new\x00')
        commit(self.root)
        self.manifest = dict(schema=1, base_commit=self.base, version='1.2.3-rc.4',
                             review_reference='Synthetic unit-test review, not external approval', entries=[
            dict(path='added.bin', status='A', before=None, after=descriptor(b'new\x00')),
            dict(path='deleted.bin', status='D', before=descriptor(b'gone\x00'), after=None),
            dict(path='modified.txt', status='M', before=descriptor(b'before'), after=descriptor(b'after'))])

    def freeze(self, value=None):
        path = self.root / gate.MANIFEST; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value if value is not None else self.manifest))
        return commit(self.root)

    def verify(self, source):
        return gate.verify(self.root, source, baseline=self.base)

    def test_exact_add_modify_delete_manifest_passes_without_approval(self):
        value = self.verify(self.freeze())
        self.assertEqual(value['entry_count'], 3)
        self.assertEqual(value['metadata_exclusion'], gate.MANIFEST)
        self.assertFalse(value['publish_approved'])
        self.assertEqual(value['manifest_blob']['blob_sha'], command(self.root, 'rev-parse', 'HEAD:' + gate.MANIFEST))

    def test_missing_or_untracked_manifest_fails_closed(self):
        source = command(self.root, 'rev-parse', 'HEAD')
        with self.assertRaisesRegex(ValueError, 'BLOCKED'): self.verify(source)
        path = self.root / gate.MANIFEST; path.parent.mkdir(parents=True); path.write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(ValueError, 'BLOCKED'): self.verify(source)

    def test_wrong_digest_status_mode_before_blob_rejected(self):
        mutations = [lambda m: m['entries'][0]['after'].update(sha256='0'*64),
                     lambda m: m['entries'][0].update(status='M'),
                     lambda m: m['entries'][0]['after'].update(mode='100755'),
                     lambda m: m['entries'][1]['before'].update(blob_sha='0'*40),
                     lambda m: m['entries'][2]['before'].update(sha256='0'*64)]
        for mutate in mutations:
            changed = copy.deepcopy(self.manifest); mutate(changed)
            with self.assertRaises(ValueError): self.verify(self.freeze(changed))

    def test_omitted_deleted_file_extra_path_and_self_hash_rejected(self):
        for entries in (self.manifest['entries'][:1], self.manifest['entries'] + [dict(
                path='surprise', status='A', before=None, after=descriptor(b'x'))],
                [dict(path=gate.MANIFEST, status='A', before=None, after=descriptor(b'x'))]):
            with self.assertRaises(ValueError): self.verify(self.freeze(dict(self.manifest, entries=entries)))

    def test_stale_manifest_cannot_cover_new_source(self):
        self.freeze(); (self.root / 'not-reviewed.txt').write_text('changed')
        with self.assertRaises(ValueError): self.verify(commit(self.root))

    def test_no_broad_metadata_directory_exclusion(self):
        self.freeze(); (self.root / 'docs/releases/unchecked.json').write_text('{}')
        with self.assertRaises(ValueError): self.verify(commit(self.root))

    def test_wrong_version_or_base_or_schema_rejected(self):
        for key, value in [('version', '1.2.3-rc.5'), ('base_commit', '0'*40), ('schema', True)]:
            with self.assertRaises(ValueError): self.verify(self.freeze(dict(self.manifest, **{key: value})))

    def test_duplicate_paths_and_unsorted_entries_rejected(self):
        for entries in (self.manifest['entries'] * 2, list(reversed(self.manifest['entries']))):
            with self.assertRaises(ValueError): self.verify(self.freeze(dict(self.manifest, entries=entries)))

    def test_duplicate_json_and_nonfinite_rejected(self):
        path = self.root / gate.MANIFEST; path.parent.mkdir(parents=True)
        for value in ('{"schema":1,"schema":1}', '{"schema":NaN}'):
            path.write_text(value)
            with self.assertRaises(ValueError): self.verify(commit(self.root))

    def test_same_content_mode_change_requires_review(self):
        self.freeze(); command(self.root, 'update-index', '--chmod=+x', 'modified.txt')
        command(self.root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                'commit', '-m', 'mode mutation')
        with self.assertRaises(ValueError): self.verify(command(self.root, 'rev-parse', 'HEAD'))


if __name__ == '__main__':
    unittest.main()
