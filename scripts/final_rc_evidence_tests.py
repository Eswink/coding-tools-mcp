"""Synthetic contract tests, never native execution evidence."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import final_rc_evidence as gate
import exclusive_native_gate as native

SOURCE = 'a' * 40
EXPECTED = dict(source_sha=SOURCE, source_tree='b' * 40, version='1.2.3-rc.4', run_id='123')


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def native_receipt(kind, digest):
    return dict(scenario=native.SCENARIO, source_sha=SOURCE, run_id='123', version='1.2.3-rc.4',
                package_kind=kind, binary_sha256=digest, build_kind='release-installed', passed=True,
                real_native_webview=True, real_oauth_http=True, real_local_ipc=True,
                cleanup_completed=True, export_secret_scan_completed=True, sandbox_disabled=False,
                cleanup_failed=False, real_chatgpt_verified=False, export_secrets_found=False,
                synthetic_conversation_metadata=True, tests=[dict(name=n, passed=True) for n in native.TEST_NAMES],
                foreign_request_count=100, pending_elapsed_seconds=90,
                permission_approval_source='native-webdriver-clicks')


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'artifacts'
        self.root.mkdir()
        self.out = Path(self.temp.name) / 'bundle'

    def run_data(self):
        run = dict(id=456, head_sha=SOURCE, repository=dict(full_name=gate.REPOSITORY),
                   path=gate.WORKFLOW, status='completed', conclusion='success')
        jobs = [dict(id=i+1, name=name, run_id=456, head_sha=SOURCE, status='completed', conclusion='success')
                for i, name in enumerate(sorted(gate.REQUIRED_JOBS))]
        return run, jobs

    def fixture(self):
        contracts = self.root / 'rc-package-contracts'
        write(contracts / 'identity.json', dict(EXPECTED, passed=True))
        write(contracts / 'integration.json', gate.integration(*self.run_data(), SOURCE, '456'))
        write(contracts / 'npm-audit.json', dict(metadata=dict(vulnerabilities=dict(total=0))))
        for name in gate.LOCKS:
            write(contracts / f'rust-audit-{name}.json', dict(database=dict(commit='c'*40),
                  lockfile=dict(dependency_count=100), vulnerabilities=dict(found=False, count=0)))
        packages = {}
        for kind in ('deb', 'appimage', 'nsis'):
            folder = self.root / ('rc-windows-package' if kind == 'nsis' else 'rc-linux-packages')
            folder.mkdir(exist_ok=True)
            data = ('synthetic-' + kind).encode()
            digest = hashlib.sha256(data).hexdigest()
            name = 'fixture.' + kind
            (folder / name).write_bytes(data)
            record = dict(name=name, size=len(data), sha256=digest)
            if kind == 'nsis':
                write(folder / 'rc-windows-package.json', dict(EXPECTED, passed=True, kind=kind,
                      release_candidate=True, silent_install=True, exact_nsis_payload_verified=True,
                      native_executable_sha256=digest, package=record))
                write(folder / 'exclusive-native.json', native_receipt(kind, digest))
            else:
                packages[kind] = dict(artifact=record, payload_sha256=digest)
                for os_name in ('ubuntu-22.04', 'ubuntu-24.04'):
                    installed = self.root / f'rc-linux-installed-{os_name}-{kind}'
                    write(installed / 'installed-platform.json', dict(id='ubuntu', version_id=os_name.removeprefix('ubuntu-')))
                    write(installed / 'rc-package.json', dict(EXPECTED, passed=True, kind=kind,
                          package=record, payload_sha256=digest, native_executable_sha256=digest))
                    write(installed / 'exclusive-native.json', native_receipt(kind, digest))
        write(self.root / 'rc-linux-packages/build-platform.json', dict(id='ubuntu', version_id='22.04'))
        write(self.root / 'rc-linux-packages/exclusive-package.json',
              dict(EXPECTED, passed=True, build_kind='release-candidate', packages=packages))

    def test_push_context_is_closed_branch_and_repository_allowlist(self):
        environment = dict(GITHUB_EVENT_NAME='push', GITHUB_REPOSITORY=gate.REPOSITORY,
                           GITHUB_REF='refs/heads/release/full-rc-candidate-1.2.3-rc.4')
        self.assertTrue(gate.push_context(environment))
        for key, value in [('GITHUB_EVENT_NAME', 'workflow_dispatch'),
                           ('GITHUB_REPOSITORY', 'other/repo'), ('GITHUB_REF', 'refs/heads/main'),
                           ('GITHUB_REF', 'refs/heads/release/full-rc-candidate-'),
                           ('GITHUB_REF', 'refs/tags/release/full-rc-candidate-x')]:
            self.assertFalse(gate.push_context(dict(environment, **{key: value})))

    def test_selects_unique_latest_successful_exact_source_run(self):
        run, _ = self.run_data()
        newer = dict(run, id=500)
        self.assertEqual(gate.select_run([newer, run, dict(run, id=600, head_sha='d'*40)], SOURCE), '500')
        self.assertEqual(gate.select_run([run, dict(newer, conclusion='failure')], SOURCE), '456')

    def test_empty_duplicate_or_wrong_source_run_list_rejected(self):
        run, _ = self.run_data()
        for runs in ([], [run, run], [dict(run, head_sha='d'*40)], [dict(run, path='old.yml')],
                     [dict(run, status='in_progress')], [dict(run, conclusion='failure')]):
            with self.assertRaises(ValueError): gate.select_run(runs, SOURCE)

    def test_dispatch_cannot_implicitly_select_a_run(self):
        with patch.dict(gate.os.environ, {'GITHUB_EVENT_NAME': 'workflow_dispatch',
                        'GITHUB_REPOSITORY': gate.REPOSITORY, 'GH_TOKEN': 'synthetic'}, clear=True):
            with self.assertRaises(ValueError): gate.fetch_integration('', SOURCE)

    def test_integration_exact_success(self):
        self.assertTrue(gate.integration(*self.run_data(), SOURCE, '456')['passed'])

    def test_integration_rejects_wrong_source_status_repository_or_path(self):
        for key, value in [('head_sha', 'd'*40), ('status', 'in_progress'), ('conclusion', 'failure'),
                           ('path', 'legacy.yml'), ('repository', dict(full_name='other/repo'))]:
            run, jobs = self.run_data(); run[key] = value
            with self.assertRaises(ValueError): gate.integration(run, jobs, SOURCE, '456')

    def test_integration_rejects_missing_failed_skipped_or_foreign_jobs(self):
        run, jobs = self.run_data()
        for altered in [jobs[:-1], jobs + [jobs[0]]]:
            with self.assertRaises(ValueError): gate.integration(run, altered, SOURCE, '456')
        for key, value in [('conclusion', 'failure'), ('conclusion', 'skipped'), ('head_sha', 'd'*40)]:
            altered = copy.deepcopy(jobs); altered[0][key] = value
            with self.assertRaises(ValueError): gate.integration(run, altered, SOURCE, '456')

    def test_bundle_checksums_and_release_remains_blocked(self):
        self.fixture(); result = gate.bundle(self.root, self.out, EXPECTED)
        self.assertFalse(result['publish_approved']); self.assertTrue(result['release_blockers'])
        for line in (self.out / 'SHA256SUMS.txt').read_text().splitlines():
            digest, name = line.split('  ', 1)
            self.assertEqual(hashlib.sha256((self.out / name).read_bytes()).hexdigest(), digest)

    def test_bundle_rejects_missing_platform(self):
        self.fixture()
        (self.root / 'rc-linux-installed-ubuntu-22.04-deb/rc-package.json').unlink()
        with self.assertRaises(ValueError): gate.bundle(self.root, self.out, EXPECTED)

    def test_bundle_rejects_corrupted_package(self):
        self.fixture(); (self.root / 'rc-linux-packages/fixture.deb').write_bytes(b'changed')
        with self.assertRaises(ValueError): gate.bundle(self.root, self.out, EXPECTED)

    def test_bundle_rejects_wrong_version_or_run(self):
        self.fixture()
        for key, value in [('version', '1.2.3-rc.9'), ('run_id', '999')]:
            with self.assertRaises(ValueError): gate.bundle(self.root, self.out, dict(EXPECTED, **{key:value}))

    def test_missing_or_vulnerable_audit_rejected(self):
        self.fixture(); folder = self.root / 'rc-package-contracts'
        write(folder / 'rust-audit-cloud-agent.json', dict(vulnerabilities=dict(found=True, count=1)))
        with self.assertRaises(ValueError): gate.audits(folder)
        (folder / 'rust-audit-cloud-agent.json').unlink()
        with self.assertRaises(ValueError): gate.audits(folder)

    def test_security_assertion_cannot_be_relabeled_as_packaging(self):
        self.fixture(); path = self.root / 'rc-windows-package/exclusive-native.json'
        value = gate.read_json(path); value['sandbox_disabled'] = True; write(path, value)
        with self.assertRaises(ValueError): gate.bundle(self.root, self.out, EXPECTED)

    def test_json_duplicate_and_nonfinite_rejected(self):
        p = self.root / 'bad.json'
        for raw in ('{"passed":false,"passed":true}', '{"count":NaN}'):
            p.write_text(raw)
            with self.assertRaises(ValueError): gate.read_json(p)

    def test_wrong_linux_build_platform_rejected(self):
        self.fixture()
        write(self.root / 'rc-linux-packages/build-platform.json', dict(id='ubuntu', version_id='24.04'))
        with self.assertRaises(ValueError): gate.bundle(self.root, self.out, EXPECTED)

    def test_symlink_evidence_rejected(self):
        self.fixture()
        try: (self.root / 'linked').symlink_to(self.root / 'rc-package-contracts/identity.json')
        except OSError: self.skipTest('symlink fixture unavailable')
        with self.assertRaises(ValueError): gate.bundle(self.root, self.out, EXPECTED)


if __name__ == '__main__':
    unittest.main()
