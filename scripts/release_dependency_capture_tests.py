#!/usr/bin/env python3
"""Mocked command-boundary capture tests, never hosted audit evidence."""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import release_dependency_capture as capture
from release_dependency_contract_tests import write_lock
from exact_build_audit_tests import Fixture


class CaptureContracts(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.root=self.base/'source';self.root.mkdir()
        self.output=self.base/'captured';self.database=self.base/'fresh-db'
        self.audit_bin=self.base/'cargo-audit';self.audit_bin.write_bytes(b'synthetic tool identity')
        self.f=Fixture();self.audit=copy.deepcopy(self.f.audit)
        self.audit.update(warnings={},vulnerabilities=dict(found=False,count=0,list=[]))
        for name in ('desktop','cloud-agent','local-agent'):write_lock(self.root/capture.LOCKS[name],self.f.lock)
        self.env=dict(GITHUB_RUN_ID='123',GITHUB_RUN_ATTEMPT='1',GITHUB_JOB='contracts',
            GITHUB_WORKFLOW_REF='Eswink/coding-tools-mcp/.github/workflows/final-rc-packages.yml@refs/heads/fixture',
            GITHUB_REPOSITORY='Eswink/coding-tools-mcp')

    def invoke(self, audit_exit=0, database_changed=False, clone_failure=False):
        def execute(command, root):
            if command[-1]=='--version':return 0,b'cargo-audit 0.22.2\n',b''
            return audit_exit,json.dumps(self.audit).encode(),b'raw stderr retained'
        snapshot=self.f.envelope['advisory_database']
        changed={**snapshot,'commit':'0'*40} if database_changed else snapshot
        with patch.dict(os.environ,self.env),patch.object(capture.exact,'source_identity',return_value=self.f.expected), \
             patch.object(capture.exact,'execute',side_effect=execute), \
             patch.object(capture.exact,'database_identity',side_effect=[snapshot,changed]), \
             patch.object(capture.subprocess,'run',side_effect=subprocess.CalledProcessError(1,['git']) if clone_failure else None) as clone:
            capture.capture(self.root,self.output,self.audit_bin,self.database,self.f.expected['sha'],self.f.expected['product_version'])
        return clone

    def test_three_original_reports_and_exact_commands_are_retained(self):
        clone=self.invoke()
        self.assertEqual(clone.call_args.args[0][:4],['git','clone','--depth','1'])
        self.assertEqual(clone.call_args.args[0][4],'https://github.com/RustSec/advisory-db.git')
        receipt=json.loads((self.output/'raw-audit-capture.json').read_text())
        self.assertEqual(set(receipt['reports']),{'desktop','local-agent','cloud-agent'})
        for name,record in receipt['reports'].items():
            self.assertEqual((self.output/f'rust-audit-{name}.json').read_bytes(),json.dumps(self.audit).encode())
            self.assertEqual((self.output/f'rust-audit-{name}.stderr').read_bytes(),b'raw stderr retained')
            self.assertEqual(record['command'][1:4],['audit','--no-fetch','--db'])
        self.assertFalse(receipt['release_approved']);self.assertFalse(receipt['publish_approved'])

    def test_raw_nonzero_finding_is_captured_without_a_false_security_verdict(self):
        self.audit=self.f.audit
        self.invoke(audit_exit=1)
        receipt=json.loads((self.output/'raw-audit-capture.json').read_text())
        self.assertEqual(receipt['reports']['desktop']['exit'],1)
        self.assertNotIn('passed',receipt)

    def test_audit_execution_error_preserves_raw_but_cannot_emit_receipt(self):
        with self.assertRaisesRegex(ValueError,'execution_failed'):self.invoke(audit_exit=2)
        self.assertTrue((self.output/'rust-audit-desktop.json').is_file())
        self.assertFalse((self.output/'raw-audit-capture.json').exists())

    def test_database_mutation_or_clone_failure_blocks(self):
        with self.assertRaisesRegex(ValueError,'database_changed'):self.invoke(database_changed=True)
        self.assertFalse((self.output/'raw-audit-capture.json').exists())

    def test_existing_database_cannot_replace_fresh_acquisition(self):
        self.database.mkdir()
        with self.assertRaisesRegex(ValueError,'database_must_be_new'):self.invoke()

    def test_path_glib_requires_its_separate_verifier(self):
        lock=copy.deepcopy(self.f.lock);lock['package'].append({'name':'glib','version':'0.18.5'})
        write_lock(self.root/capture.LOCKS['desktop'],lock)
        with self.assertRaisesRegex(ValueError,'desktop_glib_source_verifier_required'):self.invoke()


if __name__=='__main__':unittest.main()
