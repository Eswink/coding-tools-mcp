"""Regression checks for exact JSON types at every retained summary boundary."""
import copy
import tempfile
import unittest

from rc_consumer_fixtures import ConsumerFixture, write_json
from rc_consumer_io import json_file


class NumericContentContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.f = ConsumerFixture(self.temp.name)

    def test_retained_dependency_summary_zero_cannot_be_boolean_or_float(self):
        for path in (self.f.bundle / 'packaging-report.json', self.f.contracts / 'identity.json'):
            original = json_file(path)
            for wrong in (False, 0.0):
                value = copy.deepcopy(original)
                value['dependency_contract']['cloud']['active_vulnerability_count'] = wrong
                write_json(path, value)
                with self.subTest(path=path.name, value=wrong), self.assertRaisesRegex(
                        ValueError, 'recorded_dependency_contract_mismatch'):
                    self.f.verify()
            write_json(path, original)

    def test_retained_dependency_summary_approval_false_cannot_be_integer_zero(self):
        path = self.f.bundle / 'packaging-report.json'
        value = json_file(path)
        value['dependency_contract']['release_approved'] = 0
        write_json(path, value)
        with self.assertRaisesRegex(ValueError, 'recorded_dependency_contract_mismatch'):
            self.f.verify()

    def test_windows_marker_offset_must_fit_observed_installed_payload(self):
        path = self.f.bundle / 'evidence/rc-windows-package/安装载荷核验v7.json'
        value = json_file(path)
        value['marker_offset'] = value['observed'][0]['bytes']
        write_json(path, value)
        with self.assertRaisesRegex(ValueError, 'windows_payload'):
            self.f.verify()

    def test_exact_envelope_cannot_assert_approval(self):
        path = self.f.exact / 'envelope.json'
        value = json_file(path)
        value['release_approved'] = True
        write_json(path, value)
        with self.assertRaisesRegex(ValueError, 'approval'):
            self.f.verify()

    def test_large_integral_duration_stays_finite_without_float_overflow(self):
        path = self.f.bundle / 'evidence/rc-windows-package/exclusive-native.json'
        value = json_file(path)
        value['pending_elapsed_seconds'] = 10**400
        write_json(path, value)
        self.assertFalse(self.f.verify()['release_approved'])


if __name__ == '__main__':
    unittest.main()
