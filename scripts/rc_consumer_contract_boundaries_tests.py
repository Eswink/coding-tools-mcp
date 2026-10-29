"""Additional complete-content trust and typed paired-audit boundaries."""
import copy
import tempfile
import unittest

import rc_consumer_contract_parity_tests as paired
from rc_consumer_fixtures import ConsumerFixture, write_json
from rc_consumer_io import json_file


class FullContentBoundaries(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.f = ConsumerFixture(self.temp.name)

    def test_cloud_active_filtered_unsound_and_incomplete_builds_fail(self):
        original = copy.deepcopy(self.f.f)
        mutations = [
            lambda f: f.audit['vulnerabilities']['list'][0].update(package=copy.deepcopy(f.lock['package'][1])),
            lambda f: f.audit['settings'].update(ignore=['RUSTSEC-2023-0071']),
            lambda f: f.audit['settings'].update(target_os=['linux']),
            lambda f: f.audit['settings'].update(severity='critical'),
            lambda f: f.audit['vulnerabilities'].update(count=True),
            lambda f: f.audit['database'].update(**{'advisory-count': False}),
            lambda f: f.audit['lockfile'].update(**{'dependency-count': 3.0}),
            lambda f: f.events.pop(0),
            lambda f: f.events[0].update(features=['unreviewed']),
            lambda f: f.envelope['build_command'].__setitem__(0, '/payload/execute-me'),
            lambda f: f.envelope['features'].update(default=1),
            lambda f: f.envelope['features'].update(all=0),
            lambda f: f.envelope.update(lock_sha256='0'*64),
            lambda f: f.envelope.update(manifest_sha256='0'*64),
            lambda f: f.envelope['advisory_database'].update(clean=False),
            lambda f: f.audit.update(warnings={'unsound': [dict(kind='unsound', package=f.lock['package'][1],
                advisory=dict(id='RUSTSEC-2024-0429', package='fixture-dep', informational='unsound'))]}),
        ]
        for mutate in mutations:
            self.f.f = copy.deepcopy(original)
            mutate(self.f.f)
            self.f.sign_cloud()
            self.f.refresh_inventory()
            with self.subTest(mutation=mutate), self.assertRaises((ValueError, TypeError, KeyError)):
                self.f.verify()

    def test_extra_root_payload_and_missing_required_family_fail(self):
        path = self.f.bundle / 'extra.exe'
        path.write_bytes(b'synthetic extra payload')
        path.chmod(0o600)
        with self.assertRaisesRegex(ValueError, 'unexpected_root_payload'):
            self.f.verify()
        path.unlink()
        assets = self.f.verify()['assets']
        for asset in assets:
            path = self.f.bundle / asset['name']
            data = path.read_bytes()
            path.unlink()
            with self.subTest(family=asset['family']), self.assertRaises((ValueError, OSError)):
                self.f.verify()
            path.write_bytes(data)
            path.chmod(0o600)

    def test_canonical_cloud_audit_copy_cannot_diverge_after_inventory_refresh(self):
        path = self.f.contracts / 'rust-audit-cloud-gateway.json'
        value = json_file(path)
        value['extra_canary'] = 'same meaning, different bytes'
        write_json(path, value)
        self.f.refresh_inventory()
        with self.assertRaisesRegex(ValueError, 'canonical_raw_cloud_audit_mismatch'):
            self.f.verify()


class PairedStrictCounts(unittest.TestCase):
    def setUp(self):
        self.f = paired.DesktopPairedProof()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def test_upstream_dependency_count_is_an_integer_not_bool_or_float(self):
        path = self.f.directory / 'desktop-glib/upstream-identity-raw-audit.json'
        original = json_file(path)
        for wrong in (True, 1.0):
            value = copy.deepcopy(original)
            value['lockfile']['dependency-count'] = wrong
            write_json(path, value)
            with self.subTest(value=wrong), self.assertRaises(ValueError):
                self.f.verify()


if __name__ == '__main__':
    unittest.main()
