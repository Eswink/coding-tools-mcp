"""Unit tests of acceptance contracts, not evidence of native application execution."""
from __future__ import annotations
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from exclusive_native_gate import SCENARIO, TEST_NAMES, load, verify
from native_scenario import script_name
from exclusive_native_dialog_tests import NativeDialogRace

SOURCE, RUN, VERSION, DIGEST = 'a' * 40, '123', '0.4.0', 'b' * 64


def record():
    return {'scenario': SCENARIO, 'source_sha': SOURCE, 'run_id': RUN, 'version': VERSION,
        'package_kind': 'nsis', 'binary_sha256': DIGEST, 'build_kind': 'release-installed',
        'passed': True, 'real_native_webview': True, 'real_oauth_http': True, 'real_local_ipc': True,
        'cleanup_completed': True, 'export_secret_scan_completed': True,
        'sandbox_disabled': False, 'cleanup_failed': False, 'real_chatgpt_verified': False,
        'export_secrets_found': False, 'synthetic_conversation_metadata': True,
        'foreign_request_count': 100, 'pending_elapsed_seconds': 90.5,
        'permission_approval_source': 'native-webdriver-clicks',
        'tests': [{'name': name, 'passed': True} for name in TEST_NAMES]}


def check(value, **changes):
    fields = dict(source=SOURCE, run_id=RUN, version=VERSION, kind='nsis', binary_sha256=DIGEST)
    fields.update(changes)
    return verify(value, **fields)


class NativeContracts(unittest.TestCase):
    def test_complete_record_does_not_authorize_publication(self):
        result = check(record())
        self.assertTrue(result['passed'])
        self.assertFalse(result['publish_approved'])

    def test_identity_mismatch_rejected(self):
        for field, value in [('source', 'c' * 40), ('run_id', '124'), ('version', '0.4.1'),
                             ('kind', 'deb'), ('binary_sha256', 'c' * 64)]:
            with self.subTest(field=field), self.assertRaises(ValueError): check(record(), **{field: value})

    def test_old_or_incomplete_scenario_cannot_be_promoted(self):
        for kind in ('legacy', '', None):
            value = record(); value['scenario'] = kind
            with self.assertRaises(ValueError): check(value)
        value = record(); value['tests'] = value['tests'][:8]
        with self.assertRaises(ValueError): check(value)

    def test_duplicate_reordered_and_failed_stages_rejected(self):
        for mode in ('duplicate', 'reorder', 'failed'):
            value = record()
            if mode == 'duplicate': value['tests'][1] = copy.deepcopy(value['tests'][0])
            elif mode == 'reorder': value['tests'].reverse()
            else: value['tests'][0]['passed'] = False
            with self.subTest(mode=mode), self.assertRaises(ValueError): check(value)

    def test_failure_metadata_and_unverified_boundaries_rejected(self):
        for key in ('cleanup_completed', 'real_native_webview', 'real_oauth_http',
                    'export_secret_scan_completed', 'passed'):
            value = record(); value[key] = False
            with self.subTest(key=key), self.assertRaises(ValueError): check(value)
        for key in ('sandbox_disabled', 'real_chatgpt_verified', 'export_secrets_found'):
            value = record(); value[key] = True
            with self.subTest(key=key), self.assertRaises(ValueError): check(value)
        value = record(); value['failure_type'] = 'AssertionError'
        with self.assertRaises(ValueError): check(value)

    def test_no_simulated_approval_or_deadline(self):
        for key, bad in [('permission_approval_source', 'mock-ipc'), ('pending_elapsed_seconds', 89.9), ('foreign_request_count', 99)]:
            value = record(); value[key] = bad
            with self.subTest(key=key), self.assertRaises(ValueError): check(value)

    def test_json_duplicate_and_nonfinite_fields_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'fixture.json'
            for raw in ('{"passed":true,"passed":false}', '{"value":NaN}'):
                path.write_text(raw)
                with self.assertRaises(ValueError): load(path)

    def test_scenario_selector_is_a_closed_allowlist(self):
        self.assertEqual(script_name('legacy'), '聊天授权原生验收v6.py')
        self.assertEqual(script_name('exclusive'), 'exclusive_native_acceptance.py')
        for value in ('../escape.py', '/tmp/exclusive_native_acceptance.py', 'exclusive;cmd', None, 1):
            with self.subTest(value=value), self.assertRaises(ValueError): script_name(value)

    def test_windows_bootstrap_preserves_source_hash_and_logon_gates(self):
        source = Path(__file__).with_name('Windows标准用户验收v22.py').read_text()
        for text in ("script_name(args.get('scenario', 'legacy'))", "'scenario':args.scenario",
                     "verify_sources(root / 'source', data['source_hashes'])", 'use_normal_user_process',
                     'owned_account(name, sid, marker, actual)', "if password.encode() in raw"):
            self.assertIn(text, source)


if __name__ == '__main__': unittest.main(verbosity=2)
