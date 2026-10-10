"""Output failure, exact inventory and field-by-field sanitization contracts."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import rc_artifact_consumer as consumer
from rc_consumer_fixtures import ConsumerFixture
from rc_consumer_io import ConsumerError, PrivateRoot
from rc_consumer_finalize import PlanCommit
import rc_consumer_plan_tests as fixtures
import rc_consumer_snapshot as snapshot


class OutputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.f = ConsumerFixture(self.temp.name)
        self.content = self.f.verify()
        self.api = fixtures.API(self.f, fixtures.zip_bytes(self.f.bundle))
        selected = snapshot.select_source_runs(self.api, self.api.candidate, self.api.expected)
        metadata = snapshot.authenticate_bundle_metadata(self.api, selected, 13)
        self.observation = dict(candidate=self.api.candidate, selection=selected, artifact=metadata,
            producer=snapshot.derive_final_producer(self.api.candidate, selected, metadata))
        self.output = PrivateRoot(self.temp.name, source_root=self.f.root)
        self.receipts = PrivateRoot(self.temp.name, source_root=self.f.root)
        self.addCleanup(self.output.close)
        self.addCleanup(self.receipts.close)

    def plan(self, content=None):
        return consumer.make_asset_plan(self.observation, content or self.content,
            SimpleNamespace(path=self.f.bundle), self.output, self.receipts)

    def test_arbitrary_receipt_text_never_reaches_output(self):
        text = 'PRIVATE://signed.example.invalid/secret?token=SECRET'
        self.content['untrusted_raw_text'] = text
        self.content['audits']['cloud']['debug'] = text
        self.content['assets'][0]['source_path'] = text
        self.content['installed_platforms'][0]['stderr'] = text
        result = self.plan()
        self.assertNotIn(text, json.dumps(result))
        self.assertNotIn(text.encode(), (self.output.path / 'RC_PROVENANCE.json').read_bytes())

    def test_false_approval_flags_are_literal_booleans(self):
        for name in ('release_approved', 'publish_approved', 'raw_zero_claim'):
            for value in (0, '', None, True):
                changed = copy.deepcopy(self.content)
                changed[name] = value
                with self.subTest(name=name, value=value), PrivateRoot(self.temp.name, source_root=self.f.root) as output:
                    with self.assertRaises(ConsumerError):
                        consumer.write_sanitized_provenance(self.observation, changed, output)
                    self.assertFalse((output.path / 'RC_PROVENANCE.json').exists())

    def test_summary_numbers_cannot_be_booleans_or_nonfinite(self):
        for value in (False, 0.0, float('nan'), float('inf')):
            changed = copy.deepcopy(self.content)
            changed['audits']['cloud']['active_vulnerability_count'] = value
            with self.subTest(value=value), PrivateRoot(self.temp.name, source_root=self.f.root) as output:
                with self.assertRaises(ConsumerError):
                    consumer.write_sanitized_provenance(self.observation, changed, output)

    def test_installed_matrix_and_signing_boundaries(self):
        changes = []
        value = copy.deepcopy(self.content); value['installed_platforms'].pop(); changes.append(value)
        value = copy.deepcopy(self.content); value['installed_platforms'][0]['real_chatgpt_verified'] = True; changes.append(value)
        value = copy.deepcopy(self.content); value['signing']['windows_payload_signature_observed'] = 1; changes.append(value)
        value = copy.deepcopy(self.content); value['release_blockers'] = []; changes.append(value)
        for value in changes:
            with self.subTest(value=value), PrivateRoot(self.temp.name, source_root=self.f.root) as output:
                with self.assertRaises(ConsumerError):
                    consumer.write_sanitized_provenance(self.observation, value, output)

    def test_failure_flushing_pending_plan_leaves_no_success_plan(self):
        original = self.receipts.write
        def fail(name, data):
            result = original(name, data)
            if name == 'rc-asset-plan.pending':
                raise OSError('synthetic flush failure')
            return result
        with patch.object(self.receipts, 'write', side_effect=fail), self.assertRaises(OSError):
            self.plan()
        self.assertFalse((self.receipts.path / 'rc-asset-plan.json').exists())

    def test_failure_of_atomic_commit_leaves_no_success_plan(self):
        plan = self.plan()
        guard = PlanCommit(self.receipts, consumer.encode(plan))
        with patch.object(consumer.os, 'rename', side_effect=OSError('synthetic rename failure')):
            with self.assertRaises(OSError):
                consumer.commit_success_plan(self.receipts, guard)
        self.assertFalse((self.receipts.path / 'rc-asset-plan.json').exists())

    def test_preexisting_output_file_and_extra_asset_fail(self):
        self.output.write(self.content['assets'][0]['name'], b'preexisting')
        with self.assertRaises(ConsumerError):
            self.plan()
        self.assertFalse((self.receipts.path / 'rc-asset-plan.json').exists())
        self.content['assets'].append(dict(name='extra.exe', size=1, family='nsis'))
        with self.assertRaises(ConsumerError):
            self.plan()

    def test_cli_has_no_offline_trust_digest_host_or_publish_option(self):
        source = (Path(__file__).parent / 'rc_artifact_consumer.py').read_text()
        for option in ('--offline', '--snapshot', '--digest', '--host', '--publish', '--force', '--ignore'):
            self.assertNotIn(option, source)
        for value in ('0', '-1', '01', '1.0', 'true', '1\n'):
            with self.assertRaises(Exception):
                consumer.decimal(value)


if __name__ == '__main__':
    unittest.main()
