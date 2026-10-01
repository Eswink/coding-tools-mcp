"""Synthetic consumer fixtures, never release, native, or transport evidence."""
from __future__ import annotations

import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
from types import SimpleNamespace

import cloud_release_bundle as cloud
import exact_build_audit as exact
from exact_build_audit_tests import Fixture
import final_rc_evidence as final
from final_rc_evidence_tests import native_receipt
import rc_consumer_contracts as consumer
import release_dependency_contract as dependency


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(value), encoding='utf-8')
    path.chmod(0o600)


def write_lock(path, lock):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    lines = ['version = 4']
    for package in lock['package']:
        lines.append('[[package]]')
        lines.extend(key + ' = ' + json.dumps(value) for key, value in package.items() if value is not None)
    path.write_text('\n'.join(lines))


def private_tree(path):
    path.chmod(0o700)
    for child in path.rglob('*'):
        child.chmod(0o700 if child.is_dir() else 0o600)


class ConsumerFixture:
    """Real unchanged build verifier over a tiny, committed synthetic checkout."""
    def __init__(self, base):
        self.base = Path(base)
        self.root = self.base / 'source'
        self.bundle = self.base / 'bundle'
        self.unpacked = self.base / 'cloud-unpacked'
        for path in (self.root, self.bundle, self.unpacked):
            path.mkdir(mode=0o700)
        self.contracts = self.bundle / 'evidence/rc-package-contracts'
        self.cloud = self.bundle / 'evidence/rc-cloud-linux-amd64'
        self.exact = self.cloud / 'exact-build'
        for path in (self.contracts, self.exact, self.unpacked / 'bin'):
            path.mkdir(parents=True, mode=0o700)
        self.f = Fixture()
        self.version = self.f.expected['product_version']
        self.f.metadata['packages'][0]['version'] = self.version
        self.f.lock['package'][0]['version'] = self.version
        self.f.selected = self.f.selected.replace(' v0.1.0 ', ' v' + self.version + ' ')
        self.f.conservative = self.f.selected
        write_json(self.root / 'package.json', dict(version=self.version))
        write_json(self.root / 'package-lock.json', dict(packages={
            'node_modules/@tauri-apps/cli': dict(version='2.11.4')}))
        self.noncloud_locks = {}
        for component, name in (('cloud-gateway', 'coding-tools-cloud-gateway'),
                                ('cloud-agent', 'coding-tools-cloud-agent'),
                                ('local-agent', 'coding-tools-local-agent')):
            path = self.root / 'services' / component
            path.mkdir(parents=True, exist_ok=True)
            version = self.version if component == 'cloud-gateway' else '0.1.0'
            (path / 'Cargo.toml').write_text('[package]\nname = ' + json.dumps(name) +
                                           '\nversion = ' + json.dumps(version) + '\n')
            lock = self.f.lock if component == 'cloud-gateway' else {
                'package': [dict(name=name, version=version)]}
            write_lock(path / 'Cargo.lock', lock)
            if component != 'cloud-gateway':
                self.noncloud_locks[component] = lock
        self.noncloud_locks['desktop'] = {'package': [copy.deepcopy(self.f.lock['package'][1])]}
        write_lock(self.root / dependency.LOCKS['desktop'], self.noncloud_locks['desktop'])
        for target in self.f.metadata['packages'][0]['targets']:
            path = self.root / target['src_path'].removeprefix('/repo/')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('// Synthetic data-only source identity fixture\n')
        self.commit_source()
        self.producer = SimpleNamespace(repository=dependency.REPOSITORY, repository_id=10,
            source_sha=self.sha, source_tree=self.tree, version=self.version, run_id=123, run_attempt=1,
            workflow_ref=dependency.REPOSITORY + '/.github/workflows/final-rc-packages.yml@refs/heads/release/full-rc-candidate-fixture',
            workflow_id=11, bundle_job_id=12, bundle_job_started_at='2026-10-01T00:00:00Z',
            bundle_job_completed_at='2026-10-01T00:01:00Z', artifact_id=13, artifact_sha256='9'*64, artifact_size=1234)
        self.expected = dict(source_sha=self.sha, source_tree=self.tree, version=self.version, run_id='123')
        self.integration = dict(run=dict(id=456, run_attempt=2, head_sha=self.sha), jobs=[
            dict(id=i+1, name=name, run_id=456, run_attempt=2, head_sha=self.sha,
                 status='completed', conclusion='success') for i, name in enumerate(sorted(final.REQUIRED_JOBS))])
        self.integration_proof = dict(passed=True, source_sha=self.sha, integration_run_id='456',
            jobs=[dict(id=j['id'], name=j['name']) for j in self.integration['jobs']])
        write_json(self.contracts / 'integration.json', self.integration_proof)
        write_json(self.cloud / 'integration.json', self.integration_proof)
        self.build_cloud()
        self.build_noncloud()
        self.build_installers()
        self.refresh_reports()

    def commit_source(self):
        def git(*args):
            return subprocess.check_output(['git', '-C', str(self.root), *args], text=True).strip()
        git('init', '-q')
        git('add', '.')
        git('-c', 'user.name=Synthetic consumer fixture', '-c', 'user.email=fixture@example.invalid',
            'commit', '-qm', 'Synthetic fixture, not release evidence')
        self.sha = git('rev-parse', 'HEAD')
        self.tree = git('rev-parse', 'HEAD^{tree}')

    def build_cloud(self):
        self.f.envelope.update(sha=self.sha, tree=self.tree,
            manifest_sha256=dependency.hash_file(self.root / exact.MANIFEST),
            lock_sha256=dependency.hash_file(self.root / exact.LOCK),
            ci=dependency.producer(self.sha, '123', '1', self.producer.workflow_ref),
            toolchain=dict(cargo='cargo 1.98.1', rustc='rustc 1.98.1'))
        self.f.envelope['advisory_acquisition'].update(method='fresh_official_clone',
            command=['git', 'clone', '--depth', '1', 'https://github.com/RustSec/advisory-db.git'], exit=0)
        self.f.audit['warnings'] = {'yanked': [dict(kind='yanked', advisory=None,
            package=copy.deepcopy(self.f.lock['package'][1]))]}
        binaries = {}
        for name in sorted(cloud.BINS):
            data = b'\x7fELF\x02\x01' + b'\0'*12 + b'\x3e\0' + ('synthetic-' + name).encode()
            (self.unpacked / 'bin' / name).write_bytes(data)
            binaries[name] = dict(size=len(data), sha256=exact.digest(data))
        self.f.envelope['binary_sha256'] = {name: record['sha256'] for name, record in binaries.items()}
        expected = dict(source_sha=self.sha, source_tree=self.tree, run_id='123',
            product_version=self.version, component_versions=cloud.versions(self.root, self.version), target=cloud.TARGET)
        write_json(self.unpacked / 'manifest.json', dict(expected, schema=1, binaries=binaries,
            build_os='ubuntu-22.04', publish_approved=False, scope=consumer.CLOUD_SCOPE))
        (self.unpacked / 'README.md').write_text('Synthetic fixture only, do not run these bytes')
        archive = self.cloud / 'cloud-linux-amd64.tar.gz'
        with tarfile.open(archive, 'w:gz', format=tarfile.USTAR_FORMAT) as stream:
            for name in sorted(cloud.MEMBERS):
                data = (self.unpacked / name).read_bytes()
                member = tarfile.TarInfo(name)
                member.size = len(data)
                member.mode = 0o755 if name.startswith('bin/') else 0o644
                stream.addfile(member, io.BytesIO(data))
        shutil.copyfile(archive, self.bundle / archive.name)
        write_json(self.cloud / 'archive-receipt.json', dict(expected, passed=True, publish_approved=False,
            archive=dict(name=archive.name, size=archive.stat().st_size, sha256=dependency.hash_file(archive))))
        self.sign_cloud()

    def sign_cloud(self):
        streams = {'metadata.json': json.dumps(self.f.metadata), 'selected-tree.txt': self.f.selected,
            'conservative-tree.txt': self.f.conservative,
            'build.jsonl': '\n'.join(json.dumps(e) for e in self.f.events), 'raw-audit.json': json.dumps(self.f.audit)}
        for name, data in streams.items():
            (self.exact / name).write_text(data)
        self.f.envelope['streams'] = {name: dependency.hash_file(self.exact / name) for name in exact.STREAMS}
        write_json(self.exact / 'envelope.json', self.f.envelope)
        shutil.copyfile(self.exact / 'raw-audit.json', self.contracts / 'rust-audit-cloud-gateway.json')

    def build_noncloud(self):
        self.capture = dict(schema=1, sha=self.sha, tree=self.tree, product_version=self.version,
            run_id='123', run_attempt='1', repository=dependency.REPOSITORY, workflow_ref=self.producer.workflow_ref,
            job='contracts', audit_version='cargo-audit 0.22.2', audit_binary_sha256='6'*64,
            source_root='/repo', advisory_database=copy.deepcopy(self.f.envelope['advisory_database']),
            desktop_glib_source_proof_required=False, release_approved=False, publish_approved=False, reports={})
        for name, lock in self.noncloud_locks.items():
            audit = copy.deepcopy(self.f.audit)
            audit.update(warnings={}, vulnerabilities=dict(found=False, count=0, list=[]))
            audit['lockfile']['dependency-count'] = len(lock['package'])
            write_json(self.contracts / f'rust-audit-{name}.json', audit)
            self.capture['reports'][name] = dict(command=['/fixture/cargo-audit', 'audit', '--no-fetch',
                '--db', '/fixture/advisory-db', '--json', '--file', dependency.LOCKS[name]], exit=0,
                raw_sha256=dependency.hash_file(self.contracts / f'rust-audit-{name}.json'),
                lock_sha256=dependency.hash_file(self.root / dependency.LOCKS[name]))
        write_json(self.contracts / 'raw-audit-capture.json', self.capture)
        write_json(self.contracts / 'npm-audit.json', dict(metadata=dict(vulnerabilities=dict(total=0))))

    def build_installers(self):
        packages = {}
        for kind, suffix in (('deb', '_amd64.deb'), ('appimage', '_amd64.AppImage'), ('nsis', '_x64-setup.exe')):
            folder = self.bundle / 'evidence' / ('rc-windows-package' if kind == 'nsis' else 'rc-linux-packages')
            folder.mkdir(exist_ok=True)
            name = 'MCP_' + self.version + suffix
            data = ('synthetic installer bytes: ' + kind).encode()
            (folder / name).write_bytes(data)
            shutil.copyfile(folder / name, self.bundle / name)
            record = dict(name=name, size=len(data), sha256=exact.digest(data))
            payload = exact.digest(('synthetic installed payload: ' + kind).encode())
            binary = record['sha256'] if kind == 'appimage' else payload
            proof = native_receipt(kind, binary)
            proof.update(source_sha=self.sha, version=self.version, pending_elapsed_seconds=90.5)
            if kind == 'nsis':
                write_json(folder / 'rc-windows-package.json', dict(self.expected, passed=True, kind=kind,
                    scenario='exclusive-refresh-v1', release_candidate=True, silent_install=True,
                    exact_nsis_payload_verified=True, real_native_approval=True, signed=False,
                    publish_approved=False, real_chatgpt_verified=False, synthetic_conversation_metadata=True,
                    package=record, payload_sha256=payload, native_executable_sha256=payload))
                write_json(folder / 'exclusive-native.json', proof)
                write_json(folder / '安装载荷核验v7.json', dict(passed=True, source_sha=None, cli_version='2.11.4',
                    upstream_contract=consumer.PAYLOAD_CONTRACT, allowed_change='single UNK -> NSS bundle-type marker',
                    marker_offset=32, unbundled_sha256='a'*64, expected_installed_sha256=payload,
                    installed_sha256=payload, installed_path='C:\\private\\fixture.exe',
                    observed=[dict(path='fixture.exe', bytes=128, sha256=payload)]))
            else:
                version = consumer.debian_version(self.version) if kind == 'deb' else self.version
                packages[kind] = dict(artifact=record, package_version=version, payload_sha256=payload,
                    architecture='amd64', package_id='coding-tools-mcp' if kind == 'deb' else None)
                for platform in ('ubuntu-22.04', 'ubuntu-24.04'):
                    installed = self.bundle / 'evidence' / f'rc-linux-installed-{platform}-{kind}'
                    write_json(installed / 'installed-platform.json', dict(id='ubuntu', version_id=platform[7:]))
                    write_json(installed / 'rc-package.json', dict(self.expected, passed=True, kind=kind,
                        package=record, package_version=version, payload_sha256=payload, native_executable_sha256=binary))
                    write_json(installed / 'exclusive-native.json', proof)
        folder = self.bundle / 'evidence/rc-linux-packages'
        write_json(folder / 'build-platform.json', dict(id='ubuntu', version_id='22.04'))
        write_json(folder / 'exclusive-package.json', dict(self.expected, passed=True,
            build_kind='release-candidate', packages=packages))

    def refresh_inventory(self):
        identity = json.loads((self.contracts / 'identity.json').read_text())
        identity['evidence_inventory'] = final.evidence_inventory(self.contracts)
        write_json(self.contracts / 'identity.json', identity)
        self.checksums()

    def checksums(self):
        paths = sorted(p for p in self.bundle.rglob('*') if p.is_file() and p != self.bundle / 'SHA256SUMS.txt')
        (self.bundle / 'SHA256SUMS.txt').write_text(''.join(dependency.hash_file(p) + '  ' +
            p.relative_to(self.bundle).as_posix() + '\n' for p in paths))
        private_tree(self.bundle)
        private_tree(self.unpacked)

    def refresh_reports(self):
        private_tree(self.bundle)
        private_tree(self.unpacked)
        _, proof = consumer.verify_consumed_cloud(self.root, self.bundle, self.unpacked,
                                                self.producer, self.integration)
        noncloud = consumer.verify_consumed_noncloud_audits(self.root, self.contracts, self.producer)
        contract = dict(noncloud=noncloud, cloud=proof, raw_zero_claim=False,
                        release_approved=False, publish_approved=False, scope=consumer.DEPENDENCY_SCOPE)
        write_json(self.contracts / 'identity.json', dict(self.expected, passed=True, dependency_contract=contract,
            evidence_inventory=final.evidence_inventory(self.contracts)))
        write_json(self.bundle / 'packaging-report.json', dict(self.expected, passed=True, release_approved=False,
            publish_approved=False, scope=consumer.PACKAGE_SCOPE, release_blockers=list(consumer.BLOCKERS),
            dependency_contract=contract))
        self.checksums()

    def verify(self):
        return consumer.verify_consumed_bundle(self.root, self.bundle, self.unpacked,
                                               self.producer, self.integration)
