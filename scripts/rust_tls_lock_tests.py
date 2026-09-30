"""Prevent the known Rustls encryption-level regression in shipped lockfiles.

This bounded advisory regression complements, never replaces, current RustSec
audits and real TLS/WSS behavior tests.
"""
from pathlib import Path
import re
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
LOCKS = ('src-tauri', 'services/cloud-agent', 'services/cloud-gateway', 'services/local-agent')


def check_lock(text: str) -> int:
    packages = tomllib.loads(text)['package']
    found = 0
    for package in packages:
        if package['name'] != 'rustls':
            continue
        found += 1
        version = package['version']
        if not re.fullmatch(r'\d+\.\d+\.\d+', version):
            raise ValueError('Rustls prerelease requires a separate advisory review')
        numbers = tuple(map(int, version.split('.')))
        if (0, 23, 13) <= numbers < (0, 23, 45):
            raise ValueError('RUSTSEC-2026-0285: vulnerable Rustls lock entry')
    return found


class RustlsLockRegression(unittest.TestCase):
    def fixture(self, version: str) -> str:
        return f'[[package]]\nname="rustls"\nversion="{version}"\n'

    def test_all_affected_boundaries_are_rejected(self):
        for version in ('0.23.13', '0.23.41', '0.23.44'):
            with self.subTest(version=version), self.assertRaises(ValueError):
                check_lock(self.fixture(version))

    def test_patched_and_advisory_unaffected_ranges(self):
        for version in ('0.23.12', '0.23.45', '0.23.46'):
            self.assertEqual(check_lock(self.fixture(version)), 1)

    def test_duplicates_cannot_hide_a_vulnerable_version(self):
        with self.assertRaises(ValueError):
            check_lock(self.fixture('0.23.45') + self.fixture('0.23.41'))

    def test_prerelease_is_not_silently_treated_as_patched(self):
        with self.assertRaises(ValueError):
            check_lock(self.fixture('0.23.45-rc.1'))

    def test_actual_all_production_lockfiles(self):
        for directory in LOCKS:
            with self.subTest(directory=directory):
                count = check_lock((ROOT / directory / 'Cargo.lock').read_text())
                if directory != 'services/local-agent':
                    self.assertGreater(count, 0, 'expected TLS dependency disappeared')


if __name__ == '__main__':
    unittest.main()
