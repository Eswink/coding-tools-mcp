"""NSIS标记核验的正反例；任意其他字节变更必须拒绝。"""
import json
from pathlib import Path
import tempfile
import unittest
from 安装载荷校验v7 import CLI_VERSION, ORIGINAL, NSIS, expected_payload, inspect


class PayloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.installed = self.root / '中文 安装 [目录]'
        self.installed.mkdir()
        self.built = self.root / 'built.exe'
        self.original = b'MZ' + bytes(range(256)) + ORIGINAL + b'unchanged suffix'
        self.expected, self.offset = expected_payload(self.original)
        self.built.write_bytes(self.original)
        self.lock = self.root / 'package-lock.json'
        self.lock.write_text(json.dumps({'packages': {'node_modules/@tauri-apps/cli': {'version': CLI_VERSION}}}))

    def run_inspect(self, data):
        (self.installed / 'application.exe').write_bytes(data)
        return inspect(self.built, self.installed, self.lock)

    def test_exact_nsis_payload_is_accepted(self):
        result = self.run_inspect(self.expected)
        self.assertTrue(result['passed'])
        self.assertEqual(result['marker_offset'], self.offset)
        self.assertNotEqual(result['unbundled_sha256'], result['installed_sha256'])
        self.assertEqual(self.built.read_bytes(), self.original)

    def test_unpatched_original_is_rejected(self):
        self.assertFalse(self.run_inspect(self.original)['passed'])

    def test_arbitrary_prefix_suffix_changes_are_rejected(self):
        for index in [2, 5, len(self.expected) - 1]:
            data = bytearray(self.expected)
            data[index] ^= 1
            self.assertFalse(self.run_inspect(bytes(data))['passed'])

    def test_different_bundle_type_is_rejected(self):
        self.assertFalse(self.run_inspect(self.expected.replace(NSIS, b'__TAURI_BUNDLE_TYPE_VAR_MSI'))['passed'])

    def test_duplicate_matching_files_are_rejected(self):
        (self.installed / 'duplicate.exe').write_bytes(self.expected)
        self.assertFalse(self.run_inspect(self.expected)['passed'])

    def test_uninstaller_does_not_match_application(self):
        (self.installed / 'uninstall.exe').write_bytes(b'MZuninstaller')
        result = self.run_inspect(self.expected)
        self.assertTrue(result['passed'])
        self.assertEqual(len(result['observed']), 2)

    def test_missing_and_duplicate_markers_rejected(self):
        for data in [b'MZno marker', self.original + ORIGINAL]:
            with self.assertRaises(ValueError): expected_payload(data)

    def test_cli_upgrade_requires_review(self):
        self.lock.write_text(json.dumps({'packages': {'node_modules/@tauri-apps/cli': {'version': '9.0.0'}}}))
        with self.assertRaises(ValueError): self.run_inspect(self.expected)

    def test_empty_install_directory_is_rejected(self):
        self.assertFalse(inspect(self.built, self.installed, self.lock)['passed'])

    def test_wrong_pe_prefix_is_rejected(self):
        with self.assertRaises(ValueError): expected_payload(b'notpe' + ORIGINAL)


if __name__ == '__main__':
    unittest.main()
