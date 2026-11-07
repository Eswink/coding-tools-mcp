#!/usr/bin/env python3
"""Installed-root gate: positive, malicious, missing and mis-bound evidence (synthetic DEB fixtures)."""
import copy
import os
import shutil
import subprocess
from pathlib import Path
import tempfile
import unittest

import desktop_glib_deb as deb
import desktop_glib_deb_tests as fx
import desktop_glib_installed as inst
from exact_build_audit import EvidenceError


class InstalledGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'installed'
        self.root.mkdir()
        self.package = fx.package(extra_dirs=tuple(sorted(deb.DATA_DIRS)))
        self.summary = deb.verify_deb(fx.elf(), self.package, fx.VERSION)

    def tearDown(self):
        self.tmp.cleanup()

    def verify(self, package=None, summary=None):
        return inst.verify_installed_root(self.root, package or self.package, fx.VERSION, summary or self.summary)

    def unpacked(self):
        inst.unpack_controlled_root(self.package, fx.VERSION, self.root)
        return self.root

    def reject(self, code, **kw):
        with self.assertRaisesRegex(EvidenceError, code):
            self.verify(**kw)

    def test_positive_controlled_root_binds_payload_and_keeps_approvals_false(self):
        self.unpacked()
        result = self.verify()
        self.assertIs(result['installed_desktop_bytes_verified'], True)
        s = result['installed_desktop_bytes']
        self.assertEqual(s['installed_sha256'], self.summary['payload_sha256'])
        self.assertEqual(s['package_sha256'], self.summary['package_sha256'])
        self.assertEqual(set(s['file_digests']), deb.DATA_FILES)
        for k in ('symlinks_followed', 'maintainer_scripts_run', 'dpkg_install', 'real_machine'):
            self.assertIs(s[k], False)
        self.assertTrue(any('not a dpkg install' in x for x in s['limitations']))
        self.assertTrue(any('maintainer scripts not run' in x for x in s['limitations']))
        self.assertTrue(any('not a real machine' in x for x in s['limitations']))
        for k in ('security_approved', 'release_approved', 'publish_approved'):
            self.assertNotIn(k, result)

    def test_flags_constant_never_true(self):
        import desktop_glib_build_contract as c
        self.assertIs(c.FLAGS['installed_desktop_bytes_verified'], False)
        self.assertIs(c.FLAGS['engineering_only'], True)
        self.assertIn('scripts/desktop_glib_installed.py', c.SOURCE_INPUTS)

    def test_missing_root_or_file_rejected(self):
        self.reject('missing_installed_path')
        self.unpacked()
        (self.root / deb.BINARY).unlink()
        self.reject('missing_installed_path')

    def test_payload_byte_mutation_rejected(self):
        self.unpacked()
        p = self.root / deb.BINARY
        data = bytearray(p.read_bytes()); data[-1] ^= 1
        p.write_bytes(bytes(data))
        self.reject('installed_bytes_mismatch')

    def test_icon_byte_mutation_rejected(self):
        self.unpacked()
        p = self.root / sorted(deb.DATA_FILES - {deb.BINARY})[0]
        p.write_bytes(p.read_bytes() + b'x')
        self.reject('installed_bytes_mismatch')

    def test_symlink_binary_not_followed(self):
        self.unpacked()
        p = self.root / deb.BINARY
        real = Path(self.tmp.name) / 'outside'
        real.write_bytes(p.read_bytes()); p.unlink(); p.symlink_to(real)
        self.reject('installed_symlink')

    def test_symlinked_directory_rejected(self):
        self.unpacked()
        d = self.root / 'usr/bin'
        moved = Path(self.tmp.name) / 'bin-outside'
        d.rename(moved); d.symlink_to(moved, target_is_directory=True)
        self.reject('installed_symlink')

    def test_symlinked_root_rejected(self):
        self.unpacked()
        link = Path(self.tmp.name) / 'link'
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(EvidenceError, 'unsafe_installed_root'):
            inst.verify_installed_root(link, self.package, fx.VERSION, self.summary)

    def test_hardlink_rejected(self):
        self.unpacked()
        os.link(self.root / deb.BINARY, Path(self.tmp.name) / 'alias')
        self.reject('installed_hardlink')

    def test_extra_and_escaping_paths_rejected(self):
        self.unpacked()
        (self.root / 'etc').mkdir()
        self.reject('unexpected_installed_path')
        (self.root / 'etc').rmdir()
        (self.root / 'usr/bin/extra').write_bytes(b'x')
        self.reject('unexpected_installed_path')

    def test_special_file_rejected(self):
        self.unpacked()
        os.mkfifo(self.root / 'usr/bin/fifo')
        self.reject('installed_special_file')

    def test_mode_mismatch_rejected(self):
        self.unpacked()
        os.chmod(self.root / deb.BINARY, 0o644)
        self.reject('installed_mode_mismatch')

    def test_wrong_deb_binding_rejected(self):
        self.unpacked()
        for change in (dict(package_sha256='0' * 64), dict(payload_sha256='0' * 64), dict(payload_path='usr/bin/x')):
            bad = {**self.summary, **change}
            with self.subTest(change=change):
                self.reject('installed_wrong_deb_binding', summary=bad)

    def test_other_package_rejected(self):
        self.unpacked()
        other = fx.package(extra_dirs=tuple(sorted(deb.DATA_DIRS)), payload=fx.transformed(fx.elf(offset=4500)))
        self.reject('installed_wrong_deb_binding', package=other)

    @unittest.skipUnless(shutil.which('dpkg-deb'), 'dpkg-deb unavailable')
    def test_independent_dpkg_deb_extract_matches_gate(self):
        deb_path = Path(self.tmp.name) / 'fixture.deb'
        deb_path.write_bytes(self.package)
        subprocess.run(['dpkg-deb', '-x', str(deb_path), str(self.root)], check=True, capture_output=True)
        result = self.verify()
        self.assertIs(result['installed_desktop_bytes_verified'], True)
        p = self.root / deb.BINARY
        data = bytearray(p.read_bytes()); data[100] ^= 1
        p.write_bytes(bytes(data))
        self.reject('installed_bytes_mismatch')

    def test_unpack_refuses_nonempty_root(self):
        (self.root / 'x').write_bytes(b'')
        with self.assertRaisesRegex(EvidenceError, 'installed_root_not_empty'):
            inst.unpack_controlled_root(self.package, fx.VERSION, self.root)

    def test_gate_rejects_forged_or_unbound_summaries(self):
        self.unpacked()
        good = self.verify()['installed_desktop_bytes']
        self.assertIs(inst.installed_gate(good, self.summary['package_sha256']), True)
        mutations = [lambda s: s.pop('file_digests'), lambda s: s.update(extra=1),
            lambda s: s.update(carrier='dpkg-install'), lambda s: s.update(installed_sha256='1' * 64),
            lambda s: s.update(payload_sha256='1' * 64), lambda s: s['file_digests'].pop(deb.BINARY),
            lambda s: s.update(maintainer_scripts_run=True), lambda s: s.update(real_machine=True),
            lambda s: s.update(dpkg_install=True), lambda s: s.update(symlinks_followed=True),
            lambda s: s.update(limitations=[]), lambda s: s.update(installed_size=0),
            lambda s: s.update(package_sha256='Z' * 64)]
        for m in mutations:
            bad = copy.deepcopy(good); m(bad)
            with self.subTest(m=m), self.assertRaises(EvidenceError):
                inst.installed_gate(bad)
        with self.assertRaisesRegex(EvidenceError, 'unbound_installed_summary'):
            inst.installed_gate(good, '2' * 64)
        with self.assertRaises(EvidenceError):
            inst.installed_gate(None)

    def test_claim_requires_summary_for_true_and_none_for_false(self):
        self.unpacked()
        good = self.verify()['installed_desktop_bytes']
        self.assertEqual(inst.claim({'installed_desktop_bytes_verified': False}), (False, None))
        flag, bound = inst.claim({'installed_desktop_bytes_verified': True, 'installed_desktop_bytes': good})
        self.assertIs(flag, True)
        self.assertEqual(bound['installed_sha256'], good['installed_sha256'])
        for proof, code in (({'installed_desktop_bytes_verified': True}, 'invalid_installed_summary'),
                ({'installed_desktop_bytes_verified': False, 'installed_desktop_bytes': good}, 'installed_summary_without_claim'),
                ({'installed_desktop_bytes_verified': 1, 'installed_desktop_bytes': good}, 'invalid_installed_claim'),
                ({}, 'invalid_installed_claim')):
            with self.subTest(proof=proof), self.assertRaisesRegex(EvidenceError, code):
                inst.claim(proof)


if __name__ == '__main__':
    unittest.main(verbosity=2)
