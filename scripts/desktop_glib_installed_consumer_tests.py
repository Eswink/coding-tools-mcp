#!/usr/bin/env python3
"""Downstream consumers accept installed_desktop_bytes_verified=True only with a bound gate summary."""
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

    def test_bound_true_accepted_and_sanitized(self):
        good = self.proof['installed_desktop_bytes']
        n = noncloud.audit_summary(noncloud_value(installed_desktop_bytes_verified=True,
                                                  installed_desktop_bytes=good))['desktop_source']
        for s in (n,):
            self.assertIs(s['installed_desktop_bytes_verified'], True)
            self.assertEqual(s['installed_desktop_bytes']['installed_sha256'], good['payload_sha256'])
            self.assertNotIn('file_digests', s['installed_desktop_bytes'])

    def test_missing_forged_or_misbound_rejected(self):
        for proof in self.cases():
            with self.subTest(proof=sorted(proof)):
                if proof['installed_desktop_bytes_verified'] is not False:
                    with self.assertRaises((ValueError, KeyError)):
                        artifact.audit(artifact_value(**proof))
                with self.assertRaisesRegex(ValueError, 'invalid_desktop_proof_summary'):
                    noncloud.audit_summary(noncloud_value(**proof))

    def test_noncloud_true_never_carries_approval(self):
        good = self.proof['installed_desktop_bytes']
        for k in ('release_approved', 'security_approved', 'publish_approved'):
            with self.subTest(k=k), self.assertRaisesRegex(ValueError, 'invalid_desktop_proof_summary'):
                noncloud.audit_summary(noncloud_value(installed_desktop_bytes_verified=True,
                                                      installed_desktop_bytes=good, **{k: True}))


if __name__ == '__main__':
    unittest.main(verbosity=2)
