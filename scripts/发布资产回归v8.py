"""发布门负例、续传和只读幂等回归；所有API测试使用内存替身。"""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from 发布资产v8 import ReleaseError, prepare_assets, publish, verify_assets

SOURCE = 'a' * 40
VERSION = '0.2.3'


class FakeAPI:
    def __init__(self):
        self.release = None
        self.assets = []
        self.ref = None
        self.writes = []
        self.fail_upload = False
        self.race_ref = False

    def request(self, method, path, data=None, allow_missing=False, upload=None):
        if method == 'GET':
            if path.startswith('/git/ref/'):
                return self.ref
            if path.startswith('/releases?'):
                return [copy.deepcopy(self.release)] if self.release else []
            if '/assets?' in path:
                return copy.deepcopy(self.assets)
        self.writes.append((method, path))
        if path == '/releases':
            self.release = {'id': 1, 'html_url': 'https://github.com/example/release', **data}
            return copy.deepcopy(self.release)
        if upload:
            if self.fail_upload:
                raise ReleaseError('simulated network failure')
            asset = {k: upload[k] for k in ('name', 'size', 'digest')}
            asset['state'] = 'uploaded'
            self.assets.append(asset)
            if self.race_ref:
                self.ref = {'object': {'type': 'commit', 'sha': 'b' * 40}}
            return asset
        if method == 'PATCH':
            self.release.update(data)
            self.ref = {'object': {'type': 'commit', 'sha': self.release['target_commitish']}}
            return copy.deepcopy(self.release)
        raise AssertionError((method, path))


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        self.addCleanup(self.dir.cleanup)
        self.binary = self.root / f'科研工具MCP_{VERSION}_x64-setup.exe'
        self.binary.write_bytes(b'MZ-test-installer')
        import hashlib
        payload_hash = 'c' * 64
        self.source = {'source_sha': SOURCE, 'version': VERSION, 'passed': True, 'artifacts': [
            {'name': self.binary.name, 'bytes': self.binary.stat().st_size,
             'sha256': hashlib.sha256(self.binary.read_bytes()).hexdigest()}]}
        self.smoke = {'source_sha': SOURCE, 'version': VERSION, 'platform': 'windows-x64',
                      'silent_install': True, 'native_window_created': True,
                      'sustained_process': True, 'exact_nsis_payload_verified': True,
                      'installed_binary_sha256': payload_hash}
        self.payload = {'passed': True, 'source_sha': SOURCE, 'installed_sha256': payload_hash,
                        'expected_installed_sha256': payload_hash}
        self.write()
        (self.root / '本地验收说明v7.md').write_text('本地验收说明', encoding='utf-8')

    def write(self):
        for name, value in [('发布来源v7.json', self.source), ('安装冒烟结果v7.json', self.smoke),
                            ('安装载荷核验v7.json', self.payload)]:
            (self.root / name).write_text(json.dumps(value), encoding='utf-8')

    def assets(self):
        return prepare_assets(self.root, SOURCE, VERSION)

    def test_transport_names_are_distinct_ascii_with_chinese_labels(self):
        assets = self.assets()
        self.assertEqual(len({a['name'] for a in assets}), 3)
        self.assertTrue(all(a['name'].isascii() and not a['label'].isascii() for a in assets))

    def test_evidence_archive_is_deterministic(self):
        first = self.assets()
        second = self.assets()
        self.assertEqual([a['digest'] for a in first], [a['digest'] for a in second])

    def test_changed_installer_fails(self):
        self.binary.write_bytes(b'tampered')
        with self.assertRaises(ReleaseError): self.assets()

    def test_wrong_sha_fails(self):
        self.payload['source_sha'] = 'b' * 40; self.write()
        with self.assertRaises(ReleaseError): self.assets()

    def test_wrong_version_fails(self):
        self.smoke['version'] = '0.2.2'; self.write()
        with self.assertRaises(ReleaseError): self.assets()

    def test_false_install_fails(self):
        self.smoke['silent_install'] = False; self.write()
        with self.assertRaises(ReleaseError): self.assets()

    def test_string_true_is_not_success(self):
        self.smoke['native_window_created'] = 'true'; self.write()
        with self.assertRaises(ReleaseError): self.assets()

    def test_path_traversal_is_rejected(self):
        self.source['artifacts'][0]['name'] = '../secret.exe'; self.write()
        with self.assertRaises(ReleaseError): self.assets()

    def test_missing_payload_digest_is_rejected(self):
        self.smoke['installed_binary_sha256'] = ''; self.write()
        with self.assertRaises(ReleaseError): self.assets()

    def test_missing_notes_fails(self):
        (self.root / '本地验收说明v7.md').unlink()
        with self.assertRaises(ReleaseError): self.assets()

    def test_publish_then_repeat_performs_no_writes(self):
        api = FakeAPI(); assets = self.assets()
        self.assertTrue(publish(api, assets, SOURCE, VERSION, 'notes')['passed'])
        previous = len(api.writes)
        self.assertTrue(publish(api, assets, SOURCE, VERSION, 'notes')['passed'])
        self.assertEqual(len(api.writes), previous)

    def test_failed_upload_keeps_draft_and_resume_succeeds(self):
        api = FakeAPI(); api.fail_upload = True; assets = self.assets()
        with self.assertRaises(ReleaseError): publish(api, assets, SOURCE, VERSION, 'notes')
        self.assertTrue(api.release['draft'])
        self.assertIsNone(api.ref)
        api.fail_upload = False
        self.assertTrue(publish(api, assets, SOURCE, VERSION, 'notes')['passed'])
        self.assertEqual(sum(path == '/releases' for _, path in api.writes), 1)

    def test_other_source_draft_is_untouched(self):
        api = FakeAPI()
        api.release = {'id': 1, 'tag_name': 'v' + VERSION, 'target_commitish': 'b' * 40,
                       'draft': True, 'prerelease': True}
        with self.assertRaises(ReleaseError): publish(api, self.assets(), SOURCE, VERSION, 'notes')
        self.assertEqual(api.writes, [])

    def test_tag_race_prevents_public_transition(self):
        api = FakeAPI(); api.race_ref = True
        with self.assertRaises(ReleaseError): publish(api, self.assets(), SOURCE, VERSION, 'notes')
        self.assertTrue(api.release['draft'])
        self.assertFalse(any(method == 'PATCH' for method, _ in api.writes))

    def test_wrong_existing_tag_is_untouched(self):
        api = FakeAPI(); api.ref = {'object': {'type': 'commit', 'sha': 'b' * 40}}
        with self.assertRaises(ReleaseError): publish(api, self.assets(), SOURCE, VERSION, 'notes')
        self.assertEqual(api.writes, [])

    def test_remote_mismatch_is_not_overwritten(self):
        assets = self.assets(); actual = [{'name': assets[0]['name'], 'size': assets[0]['size'],
                                        'digest': 'sha256:' + '0'*64, 'state': 'uploaded'}]
        with self.assertRaises(ReleaseError): verify_assets(assets, actual, complete=False)

    def test_normalized_unknown_remote_name_is_rejected(self):
        with self.assertRaises(ReleaseError): verify_assets(self.assets(), [{'name': 'v7.json'}], complete=False)

    def test_incomplete_remote_is_rejected(self):
        with self.assertRaises(ReleaseError): verify_assets(self.assets(), [], complete=True)

    def test_duplicate_expected_name_is_rejected(self):
        assets = self.assets(); assets[1]['name'] = assets[0]['name']
        with self.assertRaises(ReleaseError): verify_assets(assets, [], complete=False)

    def test_partial_upload_resume_does_not_replace_verified_asset(self):
        api = FakeAPI(); assets = self.assets()
        api.release = {'id': 1, 'tag_name': 'v' + VERSION, 'target_commitish': SOURCE,
                       'draft': True, 'prerelease': True, 'html_url': 'https://example.invalid'}
        api.assets = [{k: assets[0][k] for k in ('name', 'size', 'digest')} | {'state': 'uploaded'}]
        self.assertTrue(publish(api, assets, SOURCE, VERSION, 'notes')['passed'])
        self.assertEqual(sum('/assets?' in path for _, path in api.writes), 2)


if __name__ == '__main__':
    unittest.main()
