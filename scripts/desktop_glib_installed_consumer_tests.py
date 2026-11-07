#!/usr/bin/env python3
"""Downstream consumers stay fail-closed on installed_desktop_bytes_verified=True (C24 S1b).

Neither consumer holds an authenticated DEB package_sha256, so True is confined to the GLib DEB lane
(desktop_glib_installed.verify_installed_root -> installed_gate bound to verify_deb package_sha256)."""
import copy
from pathlib import Path
import tempfile
import unittest

import desktop_glib_deb as deb
import desktop_glib_deb_tests as fx
import desktop_glib_installed as inst
import rc_artifact_consumer as artifact
import rc_consumer_noncloud as noncloud

KINDS = ('unmaintained', 'unsound', 'notice', 'yanked')


def good_summary():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / 'r'; root.mkdir()
        package = fx.package(extra_dirs=tuple(sorted(deb.DATA_DIRS)))
        inst.unpack_controlled_root(package, fx.VERSION, root)
        return inst.verify_installed_root(root, package, fx.VERSION, deb.verify_deb(fx.elf(), package, fx.VERSION))


def artifact_value(**proof):
    base = dict(required=True, source_backport_verified=True, installed_desktop_bytes_verified=False,
                upstream_identity_raw_vulnerability_count=1, upstream_identity_warning_counts={k: 0 for k in KINDS})
    base.update(proof)
    return dict(raw_vulnerability_count=0, active_vulnerability_count=0,
                warning_counts={k: 0 for k in KINDS}, desktop_source=base)


def noncloud_value(**proof):
    base = dict(required=True, source_backport_verified=True, raw_zero_claim=False, release_approved=False,
                installed_desktop_bytes_verified=False, upstream_identity_vulnerabilities=[{}],
                upstream_identity_warnings={'unsound': [{}]})
    base.update(proof)
    return dict(raw_vulnerability_count=0, raw_warnings={}, desktop_source=base)


class ConsumerInstalledClaims(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proof = good_summary()

    def cases(self):
        good = self.proof['installed_desktop_bytes']
        forged = copy.deepcopy(good); forged['installed_sha256'] = '1' * 64
        scripts = copy.deepcopy(good); scripts['maintainer_scripts_run'] = True
        return [dict(installed_desktop_bytes_verified=True),
                dict(installed_desktop_bytes_verified=True, installed_desktop_bytes=forged),
                dict(installed_desktop_bytes_verified=True, installed_desktop_bytes=scripts),
                dict(installed_desktop_bytes_verified=False, installed_desktop_bytes=good),
                dict(installed_desktop_bytes_verified='true', installed_desktop_bytes=good),
                dict(installed_desktop_bytes_verified=True, installed_desktop_bytes=good, required=False,
                     source_backport_verified=False)]

    def test_sealed_final_consumer_stays_fail_closed_on_true(self):
        # rc_artifact_consumer.py is sealed by the rc_pretag inverse-profile pin chain; C24 leaves it
        # unchanged, so any True claim is rejected there until a separately scoped sealed overlay.
        good = self.proof['installed_desktop_bytes']
        with self.assertRaisesRegex(ValueError, 'invalid_sanitized_desktop_proof'):
            artifact.audit(artifact_value(installed_desktop_bytes_verified=True, installed_desktop_bytes=good))

    def test_noncloud_registry_only_scope_without_flag_still_false(self):
        n = noncloud.audit_summary(dict(raw_vulnerability_count=0, raw_warnings={},
                                        desktop_source={'required': False, 'scope': 'registry_audit_only'}))
        self.assertIs(n['desktop_source']['installed_desktop_bytes_verified'], False)

    def test_false_path_unchanged(self):
        a = artifact.audit(artifact_value())['desktop_source']
        n = noncloud.audit_summary(noncloud_value())['desktop_source']
        for s in (a, n):
            self.assertIs(s['installed_desktop_bytes_verified'], False)
            self.assertNotIn('installed_desktop_bytes', s)

    def forged(self):
        # Grok C24 S1 HARD: self-consistent forgery (all sha fields one arbitrary hex, file_digests filled).
        f = copy.deepcopy(self.proof['installed_desktop_bytes']); fake = 'b' * 64
        f.update(package_sha256=fake, payload_sha256=fake, installed_sha256=fake)
        f['file_digests'] = {k: fake for k in f['file_digests']}
        return f

    def test_noncloud_rejects_true_even_with_genuine_bound_summary(self):
        good = self.proof['installed_desktop_bytes']
        for required in (True, False):
            with self.subTest(required=required), self.assertRaisesRegex(ValueError, 'invalid_desktop_proof_summary'):
                noncloud.audit_summary(noncloud_value(installed_desktop_bytes_verified=True,
                                                      installed_desktop_bytes=good, required=required))

    def test_noncloud_rejects_self_consistent_forgery(self):
        for flag in (True, False):
            with self.subTest(flag=flag), self.assertRaisesRegex(ValueError, 'invalid_desktop_proof_summary'):
                noncloud.audit_summary(noncloud_value(installed_desktop_bytes_verified=flag,
                                                      installed_desktop_bytes=self.forged()))
        with self.assertRaises((ValueError, KeyError)):
            artifact.audit(artifact_value(installed_desktop_bytes_verified=True, installed_desktop_bytes=self.forged()))

    def test_noncloud_not_required_true_rejected(self):
        with self.assertRaisesRegex(ValueError, 'invalid_desktop_proof_summary'):
            noncloud.audit_summary(dict(raw_vulnerability_count=0, raw_warnings={},
                                        desktop_source={'required': False, 'installed_desktop_bytes_verified': True}))

    def test_missing_forged_or_misbound_rejected(self):
        for proof in self.cases():
            with self.subTest(proof=sorted(proof)):
                if proof['installed_desktop_bytes_verified'] is not False:
                    with self.assertRaises((ValueError, KeyError)):
                        artifact.audit(artifact_value(**proof))
                with self.assertRaisesRegex(ValueError, 'invalid_desktop_proof_summary'):
                    noncloud.audit_summary(noncloud_value(**proof))

    def test_noncloud_never_carries_approval(self):
        for k in ('release_approved', 'security_approved', 'publish_approved'):
            with self.subTest(k=k), self.assertRaisesRegex(ValueError, 'invalid_desktop_proof_summary'):
                noncloud.audit_summary(noncloud_value(**{k: True}))

    def test_noncloud_does_not_import_installed_gate(self):
        # True must not be reachable from noncloud: no installed_gate/claim wiring without an authenticated sha.
        src = Path(noncloud.__file__).read_text()
        self.assertNotIn('import desktop_glib_installed', src)
        self.assertNotIn('from desktop_glib_installed', src)
        self.assertNotIn('installed_gate(', src)
        self.assertNotIn('claim(', src)


if __name__ == '__main__':
    unittest.main(verbosity=2)
