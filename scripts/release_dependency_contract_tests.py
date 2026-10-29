#!/usr/bin/env python3
"""Synthetic mutation tests: no fixture here constitutes release evidence."""
import ast
import copy
import io
import json
import os
from pathlib import Path
import re
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import cloud_release_bundle as cloud
import exact_build_audit as exact
from exact_build_audit_tests import Fixture, DEP, RSA
import final_rc_evidence as final
import final_rc_evidence_tests as final_fixtures
import release_dependency_contract as gate


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def write_lock(path, lock):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = ['version = 4']
    for package in lock['package']:
        text.append('[[package]]')
        text += [key + ' = ' + json.dumps(value) for key, value in package.items()]
    path.write_text('\n'.join(text))


class BoundFixture:
    def __init__(self, directory):
        self.base = Path(directory)
        self.root = self.base / 'source'; self.root.mkdir()
        self.evidence = self.base / 'evidence'; self.evidence.mkdir()
        self.binaries = self.base / 'binaries'; self.binaries.mkdir()
        self.package = self.base / 'package'
        self.f = Fixture()
        self.producer = gate.producer(self.f.expected['sha'], '123', '1',
            gate.REPOSITORY + '/.github/workflows/final-rc-packages.yml@refs/heads/release/full-rc-candidate-fixture')
        self.f.envelope['ci'] = self.producer.copy()
        self.f.envelope['toolchain'] = {'cargo': 'cargo 1.98.1', 'rustc': 'rustc 1.98.1'}
        self.f.envelope['advisory_acquisition'].update(method='fresh_official_clone',
            command=['git', 'clone', '--depth', '1', 'https://github.com/RustSec/advisory-db.git'], exit=0)
        self.f.audit['warnings'] = {'yanked': [dict(kind='yanked', advisory=None,
                                                   package=copy.deepcopy(self.f.lock['package'][1]))]}
        self.f.envelope['binary_sha256'] = {}
        for name in exact.BINS:
            data = b'\x7fELF\x02\x01' + b'\0'*12 + b'\x3e\x00' + ('synthetic-' + name).encode()
            (self.binaries / name).write_bytes(data)
            self.f.envelope['binary_sha256'][name] = exact.digest(data)
        self.archive_identity = dict(source_sha=self.f.expected['sha'], source_tree=self.f.expected['tree'],
            run_id='123', product_version=self.f.expected['product_version'], target=self.f.expected['target'],
            component_versions={'coding-tools-cloud-gateway': self.f.expected['product_version']})
        docs = self.root / 'docs/releases'; docs.mkdir(parents=True)
        (docs / 'cloud-binary-install.md').write_text('Synthetic archive fixture only')
        self.sign()

    def sign(self):
        f = self.f
        write_lock(self.root / exact.LOCK, f.lock)
        streams = {'metadata.json': json.dumps(f.metadata), 'selected-tree.txt': f.selected,
                   'conservative-tree.txt': f.conservative,
                   'build.jsonl': '\n'.join(json.dumps(event) for event in f.events),
                   'raw-audit.json': json.dumps(f.audit)}
        for name, data in streams.items(): (self.evidence / name).write_text(data)
        f.envelope['streams'] = {name: gate.hash_file(self.evidence / name) for name in exact.STREAMS}
        write_json(self.evidence / 'envelope.json', f.envelope)
        self.envelope_digest = gate.hash_file(self.evidence / 'envelope.json')

    def build_archive(self):
        with patch.object(cloud.platform, 'freedesktop_os_release', return_value={'ID':'ubuntu','VERSION_ID':'22.04'}), \
             patch.object(cloud.platform, 'machine', return_value='x86_64'), \
             patch.object(cloud, 'probe', return_value={'synthetic': True}):
            cloud.build(self.root, self.binaries, self.package, self.archive_identity)
        self.archive_digest = gate.hash_file(self.package / 'cloud-linux-amd64.tar.gz')

    def verification(self, archive=False, **overrides):
        tracked = exact.MANIFEST + '\n' + '\n'.join(t['src_path'].removeprefix('/repo/')
            for t in self.f.metadata['packages'][0]['targets'])
        environment = dict(GITHUB_SHA=self.f.expected['sha'], GITHUB_RUN_ID='123',
            GITHUB_RUN_ATTEMPT='1', GITHUB_WORKFLOW_REF=self.producer['workflow_ref'])
        with patch.object(exact, 'source_identity', return_value=self.f.expected), \
             patch.object(exact, 'git', return_value=tracked), patch.dict(os.environ, environment), \
             patch.object(cloud, 'identity', return_value=self.archive_identity):
            values = dict(root=self.root, evidence=self.evidence, version=self.f.expected['product_version'],
                          sha=self.f.expected['sha'], target=self.f.expected['target'],
                          envelope_digest=self.envelope_digest, expected_producer=self.producer)
            if archive:
                values.update(directory=self.package, unpacked=self.base / 'unpacked',
                              archive_digest=self.archive_digest)
                values.update(overrides)
                return gate.verify_archive(**values)
            values.update(binaries=self.binaries)
            values.update(overrides)
            return gate.verify_build(**values)


class DependencyContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.bound = BoundFixture(self.temp.name)

    def test_real_checker_plus_archive_join_preserves_raw_bytes(self):
        b = self.bound; b.build_archive()
        before = (b.evidence / 'raw-audit.json').read_bytes()
        result = b.verification(archive=True)
        self.assertEqual(result['raw_vulnerability_count'], 1)
        self.assertEqual(result['active_vulnerability_count'], 0)
        self.assertEqual(result['classified_raw_findings'][0]['id'], 'RUSTSEC-2023-0071')
        self.assertEqual(result['raw_lock_audit'], 'findings_present')
        self.assertEqual(result['raw_warnings'], b.f.audit['warnings'])
        self.assertFalse(result['publish_approved']); self.assertFalse(result['release_approved'])
        self.assertEqual(result['artifact_kind'], 'release-cloud')
        self.assertEqual((b.evidence / 'raw-audit.json').read_bytes(), before)

    def test_missing_invalid_and_self_supplied_digest_fail(self):
        for value in (None, '', 'a'*63, 'A'*64, '0'*64):
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                self.bound.verification(envelope_digest=value)

    def test_exact_producer_fields_are_all_bound(self):
        b = self.bound
        changes = {'provider':'local', 'repository':'attacker/repo', 'sha':'9'*40, 'run_id':'999',
                   'run_attempt':'2', 'workflow_ref':gate.REPOSITORY + '/.github/workflows/issue85-exact-build-audit.yml@refs/heads/ci',
                   'job':'other', 'runner_os':'Windows'}
        for field, value in changes.items():
            with self.subTest(field=field):
                original = b.f.envelope['ci'][field]
                b.f.envelope['ci'][field] = value; b.sign()
                with self.assertRaises(ValueError): b.verification()
                b.f.envelope['ci'][field] = original
        b.sign()

    def test_missing_expected_producer_field_or_unreviewed_workflow_fails(self):
        for field in gate.PRODUCER_FIELDS:
            bad = self.bound.producer.copy(); bad.pop(field)
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.bound.verification(expected_producer=bad)
        with self.assertRaises(ValueError): gate.producer('1'*40, '1', '1',
            gate.REPOSITORY + '/.github/workflows/unreviewed.yml@refs/heads/main')
        for value in (True, 1, '0', '-1', '1\n'):
            with self.assertRaises(ValueError): gate.producer('1'*40, value, '1', self.bound.producer['workflow_ref'])

    def test_replayed_attempt_rejected_even_with_a_valid_envelope(self):
        b = self.bound; b.build_archive()
        older = b.producer.copy(); older['run_attempt'] = '2'
        b.f.envelope['ci'] = older; b.sign()
        with self.assertRaisesRegex(ValueError, 'current_producer'):
            b.verification(archive=True, expected_producer=older)

    def test_altered_stream_and_rehashed_envelope_fail_external_digest(self):
        b = self.bound; original = b.envelope_digest
        (b.evidence / 'raw-audit.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'stream_tampered'): b.verification()
        b.f.audit['vulnerabilities'] = {'found':False,'count':0,'list':[]}; b.sign()
        with self.assertRaisesRegex(ValueError, 'untrusted_envelope'):
            b.verification(envelope_digest=original)

    def test_missing_or_substituted_binary_is_rejected(self):
        victim = self.bound.binaries / sorted(exact.BINS)[0]; original = victim.read_bytes()
        victim.write_bytes(original + b'other build')
        with self.assertRaisesRegex(ValueError, 'binary_hash_mismatch'): self.bound.verification()
        victim.unlink()
        with self.assertRaisesRegex(ValueError, 'missing_binary'): self.bound.verification()

    def test_outer_receipt_rehash_cannot_replace_trusted_archive(self):
        b = self.bound; b.build_archive(); archive = b.package / 'cloud-linux-amd64.tar.gz'
        archive.write_bytes(archive.read_bytes() + b'changed')
        receipt = json.loads((b.package / 'archive-receipt.json').read_text())
        receipt['archive'].update(size=archive.stat().st_size,sha256=gate.hash_file(archive))
        write_json(b.package / 'archive-receipt.json', receipt)
        with self.assertRaisesRegex(ValueError, 'trusted producer digest'): b.verification(archive=True)
        self.assertFalse((b.base / 'unpacked').exists())

    def test_legacy_archive_cannot_bypass_envelope_binary_check(self):
        b = self.bound
        for path in b.binaries.iterdir(): path.write_bytes(path.read_bytes() + b'rebuilt')
        b.build_archive()
        with self.assertRaisesRegex(ValueError, 'binary_hash_mismatch'): b.verification(archive=True)

    def test_trusted_digest_rejects_before_legacy_unpack_on_adapter_and_cli_routes(self):
        b = self.bound; b.build_archive()
        with patch.object(cloud, 'unpack', wraps=cloud.unpack) as legacy:
            with self.assertRaisesRegex(ValueError, 'trusted producer digest'):
                b.verification(archive=True, archive_digest='0'*64)
            legacy.assert_not_called()
            args = ['cloud_release_bundle.py', 'unpack', '--version', b.f.expected['product_version'],
                    '--directory', str(b.package), '--output', str(b.base/'cli-unpacked')]
            for suffix in ([], ['--expected-archive-sha256', '0'*64]):
                with patch('sys.argv', args + suffix), \
                     patch.object(cloud, 'identity', return_value=b.archive_identity), \
                     self.assertRaisesRegex(ValueError, 'trusted producer'):
                    cloud.main()
                legacy.assert_not_called()
            self.assertFalse((b.base/'unpacked').exists())
            self.assertFalse((b.base/'cli-unpacked').exists())
            b.verification(archive=True)
            legacy.assert_called_once_with(b.package, b.base/'unpacked', b.archive_identity)

    def test_active_unknown_and_malformed_unsound_warnings_fail(self):
        b = self.bound
        warning = dict(kind='unsound', package=copy.deepcopy(b.f.lock['package'][1]),
                       advisory=dict(id='RUSTSEC-2024-0429',package='fixture-dep',informational='unsound'))
        for mutate in (lambda x:None, lambda x:x['advisory'].update(id='UNKNOWN'),
                       lambda x:x['package'].update(version='999'), lambda x:x.update(kind='notice')):
            item = copy.deepcopy(warning); mutate(item)
            b.f.audit['warnings'] = {'unsound':[item]}; b.sign()
            with self.assertRaises(ValueError): b.verification()
        for warnings in ({'unknown':[]}, {'yanked':{}}, {'yanked':[{'kind':'yanked'}]}, None):
            b.f.audit['warnings'] = warnings; b.sign()
            with self.assertRaises((ValueError, KeyError, TypeError)): b.verification()

    def test_maintenance_warning_is_mapped_and_disclosed(self):
        b = self.bound
        b.f.audit['warnings'] = {'unmaintained':[dict(kind='unmaintained',
            package=copy.deepcopy(b.f.lock['package'][1]),
            advisory=dict(id='RUSTSEC-2024-0001',package='fixture-dep',informational='unmaintained'))]}
        b.sign(); self.assertEqual(b.verification()['raw_warnings'], b.f.audit['warnings'])

    def test_active_and_conservative_only_vulnerabilities_still_fail(self):
        b = self.bound
        b.f.audit['vulnerabilities']['list'][0]['package'] = copy.deepcopy(b.f.lock['package'][1]); b.sign()
        with self.assertRaisesRegex(ValueError, 'active_vulnerable'): b.verification()
        b.f.audit['vulnerabilities']['list'][0]['package'] = copy.deepcopy(b.f.lock['package'][2])
        b.f.conservative += 'rsa v0.9.10\t\n'; b.sign()
        with self.assertRaisesRegex(ValueError, 'conservative_graph'): b.verification()

    def test_missing_units_features_filters_counts_and_lock_fail(self):
        b = self.bound
        for mutate in (lambda f:f.events.pop(0), lambda f:f.events[0].update(features=['extra']),
                       lambda f:f.audit['settings'].update(ignore=['RUSTSEC-2023-0071']),
                       lambda f:f.audit['vulnerabilities'].update(count=True),
                       lambda f:f.audit['vulnerabilities']['list'][0].update(
                           package=dict(f.audit['vulnerabilities']['list'][0]['package'], checksum='0'*64))):
            original = copy.deepcopy(b.f); mutate(b.f); b.sign()
            with self.assertRaises((ValueError, KeyError, TypeError)): b.verification()
            b.f = original

    def test_engineering_archive_is_separate_and_safe(self):
        b = self.bound; b.package.mkdir()
        archive = b.package / 'engineering-binaries.tar.gz'
        with tarfile.open(archive,'w:gz') as tar:
            for path in sorted(b.binaries.iterdir()): tar.add(path,arcname=path.name)
        b.archive_digest = gate.hash_file(archive)
        result = b.verification(archive=True, engineering=True)
        self.assertEqual(result['artifact_kind'],'engineering')
        self.assertFalse(result['release_approved'])

    def test_engineering_traversal_links_duplicates_and_missing_members_fail(self):
        b = self.bound; archive = b.base / 'engineering.tar.gz'
        for mode in ('traversal','link','duplicate','missing'):
            with tarfile.open(archive,'w:gz') as tar:
                names = sorted(exact.BINS)
                for index,name in enumerate(names[:-1] if mode=='missing' else names):
                    member = tarfile.TarInfo('../escape' if mode=='traversal' and index==0 else name)
                    member.size=1
                    if mode=='link' and index==0: member.type=tarfile.SYMTYPE;member.linkname='/tmp/escape'
                    tar.addfile(member,io.BytesIO(b'x'))
                if mode=='duplicate':tar.addfile(tarfile.TarInfo(names[0]))
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                gate.engineering_unpack(archive,b.base/'unsafe',gate.hash_file(archive))
            self.assertFalse((b.base/'unsafe').exists())

    def test_local_glib_requires_separate_source_verifier(self):
        lock = {'package':[{'name':'glib','version':'0.18.5'}]}
        with self.assertRaisesRegex(ValueError,'desktop_glib_source_verifier_required'):
            gate.desktop_source_proof(self.bound.root,self.bound.evidence,
                {'desktop_glib_source_proof_required':True},{},lock)
        with self.assertRaisesRegex(ValueError,'scope_mismatch'):
            gate.desktop_source_proof(self.bound.root,self.bound.evidence,
                {'desktop_glib_source_proof_required':False},{},lock)


class FinalContractJoin(unittest.TestCase):
    def setUp(self):
        self.fixture = final_fixtures.EvidenceTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.fixture.fixture();self.folder = self.fixture.root/'rc-package-contracts'
        self.cloud = self.fixture.root/'rc-cloud-linux-amd64';self.cloud.mkdir()
        (self.cloud/'cloud-linux-amd64.tar.gz').write_bytes(b'synthetic archive')
        self.report = {'cloud':dict(archive_size=17,archive_sha256=gate.hash_file(self.cloud/'cloud-linux-amd64.tar.gz'))}
        identity = final.read_json(self.folder/'identity.json')
        identity['evidence_inventory'] = final.evidence_inventory(self.folder)
        write_json(self.folder/'identity.json',identity)
        self.options=(self.fixture.root,self.cloud,self.fixture.root/'unpack',{},gate.hash_file(self.folder/'identity.json'))

    def test_bundle_recomputes_cloud_and_keeps_native_gates(self):
        with patch.object(final,'dependency_contract',return_value=self.report) as verify:
            result=final.bundle(self.fixture.root,self.fixture.out,final_fixtures.EXPECTED,dependency_options=self.options)
        verify.assert_called_once();self.assertFalse(result['publish_approved'])
        self.assertEqual((self.fixture.out/'cloud-linux-amd64.tar.gz').read_bytes(),b'synthetic archive')

    def test_inventory_or_contract_identity_mutation_is_rejected(self):
        for filename in ('npm-audit.json','identity.json'):
            path=self.folder/filename;before=path.read_bytes();path.write_bytes(before+b' ')
            with self.subTest(file=filename),patch.object(final,'dependency_contract') as verify,self.assertRaises(ValueError):
                final.bundle(self.fixture.root,self.fixture.out,final_fixtures.EXPECTED,dependency_options=self.options)
            verify.assert_not_called();path.write_bytes(before)

    def test_failed_cloud_contract_or_native_security_still_blocks(self):
        with patch.object(final,'dependency_contract',side_effect=ValueError('active vulnerability')),self.assertRaises(ValueError):
            final.bundle(self.fixture.root,self.fixture.out,final_fixtures.EXPECTED,dependency_options=self.options)
        path=self.fixture.root/'rc-windows-package/exclusive-native.json';value=final.read_json(path)
        value['sandbox_disabled']=True;write_json(path,value)
        with patch.object(final,'dependency_contract',return_value=self.report),self.assertRaises(ValueError):
            final.bundle(self.fixture.root,self.fixture.out,final_fixtures.EXPECTED,dependency_options=self.options)


class RawCaptureContracts(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'source';self.root.mkdir()
        self.directory=Path(self.temp.name)/'evidence';self.directory.mkdir()
        self.f=Fixture();self.lock=self.f.lock
        self.audit=copy.deepcopy(self.f.audit)
        self.audit.update(warnings={},vulnerabilities=dict(found=False,count=0,list=[]))
        self.expected=dict(source_sha='1'*40,source_tree='2'*40,version='0.6.2-rc.1',run_id='123')
        self.env=dict(GITHUB_RUN_ATTEMPT='1',GITHUB_WORKFLOW_REF=gate.REPOSITORY+
                      '/.github/workflows/final-rc-packages.yml@refs/heads/release/full-rc-candidate-fixture')
        self.capture=dict(schema=1,sha='1'*40,tree='2'*40,product_version='0.6.2-rc.1',run_id='123',
            run_attempt='1',repository=gate.REPOSITORY,workflow_ref=self.env['GITHUB_WORKFLOW_REF'],job='contracts',
            audit_version='cargo-audit 0.22.2',audit_binary_sha256='6'*64,source_root=str(self.root),
            advisory_database=self.f.envelope['advisory_database'],desktop_glib_source_proof_required=False,
            release_approved=False,publish_approved=False,reports={})
        for name in ('desktop','local-agent','cloud-agent'):
            write_lock(self.root/gate.LOCKS[name],self.lock)
            write_json(self.directory/f'rust-audit-{name}.json',self.audit)
            self.capture['reports'][name]=dict(command=['/verified/cargo-audit','audit','--no-fetch',
                '--db','/official/snapshot','--json','--file',gate.LOCKS[name]],exit=0,
                raw_sha256=gate.hash_file(self.directory/f'rust-audit-{name}.json'),
                lock_sha256=gate.hash_file(self.root/gate.LOCKS[name]))
        self.save()

    def save(self):write_json(self.directory/'raw-audit-capture.json',self.capture)

    def verify(self):
        with patch.dict(os.environ,self.env):return gate.verify_noncloud_audits(self.root,self.directory,self.expected)

    def test_complete_capture_passes_without_cloud_waiver(self):
        result=self.verify();self.assertEqual(set(result),{'desktop','local-agent','cloud-agent'})
        self.assertFalse(result['desktop']['desktop_source']['required'])

    def test_capture_producer_lock_report_exit_and_filters_fail(self):
        for field in ('sha','tree','product_version','run_id','run_attempt','repository','workflow_ref','job'):
            original=self.capture[field];self.capture[field]='wrong';self.save()
            with self.subTest(field=field),self.assertRaises(ValueError):self.verify()
            self.capture[field]=original
        self.save()
        for field,value in (('exit',1),('exit',False),('lock_sha256','0'*64),('raw_sha256','0'*64),
                            ('command',['cargo-audit','audit','--ignore','RUSTSEC-2024-0429'])):
            original=self.capture['reports']['desktop'][field]
            self.capture['reports']['desktop'][field]=value;self.save()
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):self.verify()
            self.capture['reports']['desktop'][field]=original

    def test_zero_count_and_warning_shape_are_strict(self):
        for mutate in (lambda a:a['vulnerabilities'].update(count=False),
                       lambda a:a['vulnerabilities'].update(found=True),
                       lambda a:a['vulnerabilities'].update(list=[{}]),
                       lambda a:a['database'].update(**{'advisory-count':False}),
                       lambda a:a['lockfile'].update(**{'dependency-count':True}),
                       lambda a:a['settings'].update(informational_warnings=['notice']),
                       lambda a:a.update(warnings={'unknown':[]})):
            audit=copy.deepcopy(self.audit);mutate(audit)
            with self.assertRaises(ValueError):gate.raw_audit(audit,self.lock,zero=True)

    def test_any_noncloud_vulnerability_remains_blocking(self):
        with self.assertRaisesRegex(ValueError,'active_or_unproven'):
            gate.raw_audit(self.f.audit,self.lock,zero=True)


class WorkflowContracts(unittest.TestCase):
    def setUp(self):
        self.root=Path(__file__).resolve().parents[1]
        self.final=(self.root/'.github/workflows/final-rc-packages.yml').read_text()
        self.cloud=(self.root/'.github/workflows/full-rc-cloud-binaries.yml').read_text()
        self.engineering=(self.root/'.github/workflows/issue85-exact-build-audit.yml').read_text()

    def test_same_commit_acyclic_prerequisites_and_native_gates(self):
        self.assertIn('uses: ./.github/workflows/full-rc-cloud-binaries.yml',self.final)
        body=self.final.split('jobs:\n',1)[1]
        pieces=re.split(r'^  ([A-Za-z0-9_-]+):\n',body,flags=re.M)
        jobs=dict(zip(pieces[1::2],pieces[2::2]));edges={}
        for job,text in jobs.items():
            match=re.search(r'^    needs: (.+)$',text,re.M)
            edges[job]=[v.strip() for v in match[1].strip('[]').split(',')] if match else []
        def visit(job,seen):
            self.assertNotIn(job,seen)
            for parent in edges[job]:self.assertIn(parent,jobs);visit(parent,seen|{job})
        for job in jobs:visit(job,set())
        self.assertEqual(edges['source'],[]);self.assertEqual(edges['cloud'],['source'])
        self.assertEqual(set(edges['contracts']),{'source','cloud'})
        for job in ('windows','linux-build'):self.assertEqual(edges[job],['contracts'])
        self.assertTrue({'contracts','cloud','windows','linux-build','linux-installed'}<=set(edges['bundle']))
        for command in ('rc_windows_install.ps1','rc_native_gate.py','linux_startup_candidate.py',
                        'rc_version_gate.py','final_rc_evidence.py integration'):
            self.assertIn(command,self.final)

    def test_trusted_outputs_reach_every_consumer(self):
        for name in ('archive_sha256','envelope_sha256','producer_run_id','producer_run_attempt',
                     'producer_workflow_ref','producer_job'):
            self.assertIn('needs.cloud.outputs.'+name,self.final)
            self.assertIn('needs.build.outputs.'+name,self.cloud)
        self.assertIn('needs.contracts.outputs.identity_sha256',self.final)
        self.assertEqual(self.cloud.count('python scripts/release_dependency_contract.py'),3)
        self.assertNotIn('agent_fixture',self.cloud);self.assertNotIn('cloud-test-fixture',self.cloud)
        self.assertNotIn('mkdir -p evidence',self.cloud)
        self.assertNotIn('continue-on-error:',self.cloud+self.final)
        self.assertNotIn('--ignore',self.cloud+self.final)

    def test_topology_is_same_source_mandatory_success_only_bundle_prerequisite(self):
        pieces=re.split(r'^  ([A-Za-z0-9_-]+):\n',self.final.split('jobs:\n',1)[1],flags=re.M)
        jobs=dict(zip(pieces[1::2],pieces[2::2]))
        self.assertRegex(jobs['topology'],r'(?m)^    needs: source$')
        self.assertRegex(jobs['topology'],r'(?m)^    uses: \./\.github/workflows/issue40-container-topology.yml$')
        needs=re.search(r'^    needs: \[(.+)\]$',jobs['bundle'],re.M)[1]
        self.assertIn('topology',[v.strip() for v in needs.split(',')])
        for name in ('topology','bundle'):
            self.assertNotRegex(jobs[name],r'(?m)^    (if|continue-on-error):')
        topology=(self.root/'.github/workflows/issue40-container-topology.yml').read_text()
        self.assertIn('  workflow_call:',topology)
        self.assertIn('test "$(git rev-parse HEAD)" = "$GITHUB_SHA"',topology)
        self.assertIn('python tests/cloud-gateway-deployment/run_container_topology.py',topology)
        self.assertNotIn('continue-on-error:',topology)

    def test_all_final_archive_call_routes_require_trusted_unpack(self):
        routes={}
        for module in (cloud,gate,final):
            tree=ast.parse(Path(module.__file__).read_text())
            routes[module.__name__]={node.name:{ast.unparse(call.func) for call in ast.walk(node)
                if isinstance(call,ast.Call)} for node in tree.body if isinstance(node,ast.FunctionDef)}
        archive=routes['cloud_release_bundle'];adapter=routes['release_dependency_contract']
        packaging=routes['final_rc_evidence']
        self.assertEqual([name for name,calls in archive.items() if 'unpack' in calls],['unpack_trusted'])
        self.assertIn('unpack_trusted',archive['main'])
        self.assertIn('cloud.unpack_trusted',adapter['verify_archive'])
        self.assertIn('dependency.verify_archive',packaging['dependency_contract'])
        self.assertIn('dependency_contract',packaging['main'])
        self.assertIn('dependency_contract',packaging['bundle'])
        self.assertIn('bundle',packaging['main'])
        for module in (adapter,packaging):
            self.assertFalse(any(call=='unpack' or call.endswith('.unpack')
                                 for calls in module.values() for call in calls))
        self.assertIn('final_rc_evidence.py dependencies',self.final)
        self.assertIn('final_rc_evidence.py bundle',self.final)
        self.assertEqual(self.cloud.count('python scripts/release_dependency_contract.py'),3)

    def test_engineering_proof_is_explicit_and_final_has_no_engineering_switch(self):
        self.assertIn('release_dependency_contract.py --engineering',self.engineering)
        self.assertIn('test "$PRODUCER_ATTEMPT" = "$GITHUB_RUN_ATTEMPT"',self.engineering)
        self.assertIn("'release_approved': False",self.engineering)
        self.assertNotIn('--engineering',self.final+self.cloud)
        self.assertIn('final_rc_evidence.py integration',self.cloud)
        self.assertIn('cloud_release_bundle.py versions',self.cloud)


if __name__ == '__main__':
    unittest.main()
