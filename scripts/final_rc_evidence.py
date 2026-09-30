"""Collect exact-source packaging evidence; never authorize a release."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import urllib.request

from rc_version_gate import verify_source, require
from rc_native_gate import verify as verify_native
from exclusive_native_gate import legacy
import release_dependency_contract as dependency

REPOSITORY = 'Eswink/coding-tools-mcp'
WORKFLOW = '.github/workflows/dot-rc-integration.yml'
REQUIRED_JOBS = {'native (ubuntu-22.04)', 'native (ubuntu-24.04)',
                 'native (windows-2025)', 'real-transport (ubuntu-22.04)',
                 'real-transport (ubuntu-24.04)', 'browser', 'oauth-process-browser'}
LOCKS = ('desktop', 'local-agent', 'cloud-agent', 'cloud-gateway')


def read_json(path: Path) -> dict:
    require(path.is_file() and not path.is_symlink() and path.stat().st_size < 16_000_000,
            f'invalid evidence file: {path.name}')
    value = json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=legacy.unique_object,
                       parse_constant=legacy.reject_constant)
    require(type(value) is dict, 'evidence must be an object')
    return value


def integration(run: dict, jobs: list, source: str, run_id: str) -> dict:
    require(run.get('id') == int(run_id) and run.get('head_sha') == source,
            'integration run/source mismatch')
    require(run.get('repository', {}).get('full_name') == REPOSITORY,
            'integration repository mismatch')
    require(run.get('path') == WORKFLOW and run.get('status') == 'completed'
            and run.get('conclusion') == 'success', 'integration has not passed')
    require(type(jobs) is list and jobs and len({j.get('id') for j in jobs}) == len(jobs),
            'invalid integration job list')
    require(REQUIRED_JOBS <= {j.get('name') for j in jobs}, 'missing full integration job')
    require(all(j.get('run_id') == int(run_id) and j.get('head_sha') == source
                and j.get('status') == 'completed' and j.get('conclusion') == 'success'
                for j in jobs), 'failed skipped or foreign integration job')
    return {'passed': True, 'source_sha': source, 'integration_run_id': run_id,
            'jobs': [{'id': j['id'], 'name': j['name']} for j in jobs]}


def push_context(environment: dict) -> bool:
    return (environment.get('GITHUB_EVENT_NAME') == 'push'
            and environment.get('GITHUB_REPOSITORY') == REPOSITORY
            and re.fullmatch(r'refs/heads/release/full-rc-candidate-[A-Za-z0-9][A-Za-z0-9._-]*',
                             environment.get('GITHUB_REF', '')) is not None)


def select_run(runs: list, source: str) -> str:
    require(type(runs) is list and runs, 'no successful exact-source integration run')
    require(len({run.get('id') for run in runs}) == len(runs), 'ambiguous duplicate integration runs')
    eligible = [run for run in runs if run.get('head_sha') == source
                and run.get('path') == WORKFLOW and run.get('status') == 'completed'
                and run.get('conclusion') == 'success'
                and run.get('repository', {}).get('full_name') == REPOSITORY]
    require(eligible and all(type(run.get('id')) is int and run['id'] > 0 for run in eligible),
            'no valid exact-source successful integration run')
    # GitHub run IDs provide deterministic ordering; attempts are checked again
    # through the latest-attempt jobs endpoint before any package can build.
    return str(max(run['id'] for run in eligible))


def fetch_integration(run_id: str, source: str) -> dict:
    require(not run_id or re.fullmatch(r'[1-9][0-9]*', run_id) is not None, 'invalid integration run ID')
    require(re.fullmatch(r'[0-9a-f]{40}', source) is not None, 'invalid integration source')
    require(bool(run_id) or push_context(os.environ), 'dispatch requires an explicit integration run')
    require(os.environ.get('GITHUB_REPOSITORY') == REPOSITORY, 'wrong repository')
    token = os.environ.get('GH_TOKEN', '')
    require(bool(token), 'read-only Actions token required')
    def get(suffix):
        request = urllib.request.Request('https://api.github.com/repos/' + REPOSITORY + suffix,
            headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
                     'X-GitHub-Api-Version': '2022-11-28'})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    if not run_id:
        runs = []
        for page in range(1, 21):
            batch = get('/actions/workflows/dot-rc-integration.yml/runs'
                        f'?head_sha={source}&status=success&per_page=100&page={page}')['workflow_runs']
            runs.extend(batch)
            if len(batch) < 100:
                break
        else:
            raise ValueError('integration run pagination exceeded bound')
        run_id = select_run(runs, source)
    run = get('/actions/runs/' + run_id)
    jobs = []
    for page in range(1, 21):
        batch = get(f'/actions/runs/{run_id}/jobs?filter=latest&per_page=100&page={page}')['jobs']
        jobs.extend(batch)
        if len(batch) < 100:
            break
    else:
        raise ValueError('integration job pagination exceeded bound')
    return integration(run, jobs, source, run_id)


def audits(directory: Path) -> None:
    npm = read_json(directory / 'npm-audit.json')
    require('error' not in npm and npm.get('metadata', {}).get('vulnerabilities', {}).get('total') == 0,
            'npm audit missing or vulnerable')
    for name in LOCKS:
        value = read_json(directory / f'rust-audit-{name}.json')
        vulnerability = value.get('vulnerabilities', {})
        require(vulnerability.get('found') is False and vulnerability.get('count') == 0,
                'RustSec findings or missing result: ' + name)
        require(value.get('database') and value.get('lockfile'), 'RustSec provenance missing: ' + name)


def identity(value: dict, expected: dict) -> None:
    require(all(value.get(k) == v for k, v in expected.items()), 'evidence source/run/tree/version mismatch')
    require(value.get('passed') is True, 'evidence did not pass')


def copy_package(directory: Path, record: dict, output: Path) -> None:
    name = record.get('name', '')
    require(type(name) is str and name and Path(name).name == name and '/' not in name and '\\' not in name,
            'invalid package filename')
    path = directory / name
    require(path.is_file() and not path.is_symlink(), 'missing package')
    require(path.stat().st_size == record.get('size') and
            hashlib.sha256(path.read_bytes()).hexdigest() == record.get('sha256'), 'package digest mismatch')
    require(not (output / name).exists(), 'duplicate package destination')
    shutil.copyfile(path, output / name)


def evidence_inventory(directory: Path) -> dict:
    require(directory.is_dir() and not directory.is_symlink(), 'invalid evidence directory')
    require(not any(p.is_symlink() for p in directory.rglob('*')), 'symlink in evidence inventory')
    return {p.relative_to(directory).as_posix(): dependency.hash_file(p)
            for p in sorted(directory.rglob('*')) if p.is_file() and p != directory / 'identity.json'}


def dependency_contract(directory: Path, cloud: Path, unpacked: Path, root: Path,
                        expected: dict, trust: dict) -> dict:
    proof = dependency.verify_archive(root, cloud, cloud / 'exact-build', unpacked,
                                      expected['version'], expected['source_sha'],
                                      'x86_64-unknown-linux-gnu', **trust)
    require(proof['artifact_kind'] == 'release-cloud' and proof['archive_to_build_verified'] is True,
            'engineering evidence cannot satisfy final dependency contract')
    require((directory / 'rust-audit-cloud-gateway.json').read_bytes() ==
            (cloud / 'exact-build/raw-audit.json').read_bytes(), 'canonical raw cloud audit mismatch')
    npm = read_json(directory / 'npm-audit.json')
    total = npm.get('metadata', {}).get('vulnerabilities', {}).get('total')
    require('error' not in npm and type(total) is int and total == 0, 'npm audit missing or vulnerable')
    noncloud = dependency.verify_noncloud_audits(root, directory, expected)
    return dict(noncloud=noncloud, cloud=proof, raw_zero_claim=False,
                release_approved=False, publish_approved=False,
                scope='Exact cloud archive and per-lock dependency evidence; native/security gates remain separate')


def bundle(artifacts: Path, output: Path, expected: dict, *, dependency_options=None) -> dict:
    require(not output.exists(), 'bundle output must be new')
    contracts = artifacts / 'rc-package-contracts'
    contract_identity = read_json(contracts / 'identity.json')
    identity(contract_identity, expected)
    dependency_report = None
    if dependency_options is None:
        # Legacy structural helper remains raw-zero. Final CLI always supplies
        # the authenticated cloud contract; there is no CLI fallback/ignore flag.
        audits(contracts)
    else:
        root, cloud, unpacked, trust, contracts_digest = dependency_options
        dependency.hash_value(contracts_digest)
        require(dependency.hash_file(contracts / 'identity.json') == contracts_digest,
                'untrusted dependency contract identity')
        require(contract_identity.get('evidence_inventory') == evidence_inventory(contracts),
                'raw audit/source proof evidence changed')
        dependency_report = dependency_contract(contracts, cloud, unpacked, root, expected, trust)
    prior = read_json(contracts / 'integration.json')
    require(prior.get('passed') is True and prior.get('source_sha') == expected['source_sha'],
            'missing exact integration receipt')
    linux = artifacts / 'rc-linux-packages'
    manifest = read_json(linux / 'exclusive-package.json')
    identity(manifest, expected)
    require(read_json(linux / 'build-platform.json') == {'id': 'ubuntu', 'version_id': '22.04'},
            'Linux packages must be built on Ubuntu22.04')
    require(manifest.get('build_kind') == 'release-candidate' and
            set(manifest.get('packages', {})) == {'deb', 'appimage'}, 'both Linux packages required')
    windows = artifacts / 'rc-windows-package'
    win = read_json(windows / 'rc-windows-package.json')
    identity(win, expected)
    require(win.get('kind') == 'nsis' and win.get('release_candidate') is True and
            win.get('silent_install') is True and win.get('exact_nsis_payload_verified') is True,
            'Windows installed payload evidence missing')
    verify_native(read_json(windows / 'exclusive-native.json'), source=expected['source_sha'],
                  run_id=expected['run_id'], version=expected['version'], kind='nsis',
                  binary_sha256=win['native_executable_sha256'])
    for os_name in ('ubuntu-22.04', 'ubuntu-24.04'):
        for kind in ('deb', 'appimage'):
            folder = artifacts / f'rc-linux-installed-{os_name}-{kind}'
            require(read_json(folder / 'installed-platform.json') ==
                    {'id': 'ubuntu', 'version_id': os_name.removeprefix('ubuntu-')},
                    'installed platform mismatch')
            installed = read_json(folder / 'rc-package.json')
            identity(installed, expected)
            require(installed.get('kind') == kind and installed.get('package') == manifest['packages'][kind]['artifact']
                    and installed.get('payload_sha256') == manifest['packages'][kind]['payload_sha256'],
                    'installed Linux payload mismatch')
            verify_native(read_json(folder / 'exclusive-native.json'), source=expected['source_sha'],
                          run_id=expected['run_id'], version=expected['version'], kind=kind,
                          binary_sha256=installed['native_executable_sha256'])
    require(not any(p.is_symlink() for p in artifacts.rglob('*')), 'symlink in evidence input')
    output.mkdir(parents=True)
    for entry in manifest['packages'].values():
        copy_package(linux, entry['artifact'], output)
    copy_package(windows, win['package'], output)
    if dependency_report is not None:
        cloud = dependency_options[1]
        copy_package(cloud, dict(name='cloud-linux-amd64.tar.gz',
                     size=dependency_report['cloud']['archive_size'],
                     sha256=dependency_report['cloud']['archive_sha256']), output)
    shutil.copytree(artifacts, output / 'evidence')
    report = {**expected, 'passed': True, 'publish_approved': False,
              'scope': 'Exact package bytes and installed acceptance only',
              'release_blockers': ['Windows production isolation security profile remains unresolved',
                                   'Full original release ledger and external release approval remain required']}
    if dependency_report is not None:
        report.update(dependency_contract=dependency_report, release_approved=False)
    (output / 'packaging-report.json').write_text(json.dumps(report, indent=2) + '\n')
    paths = sorted(p for p in output.rglob('*') if p.is_file())
    require(not any(p.is_symlink() for p in output.rglob('*')), 'symlink in evidence')
    (output / 'SHA256SUMS.txt').write_text(''.join(
        hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.relative_to(output).as_posix() + '\n'
        for p in paths))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('integration', 'audits', 'dependencies', 'bundle'))
    parser.add_argument('--version', default='')
    parser.add_argument('--github-output', action='store_true')
    parser.add_argument('--integration-run')
    parser.add_argument('--directory', type=Path, default=Path('evidence'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cloud-directory', type=Path)
    parser.add_argument('--unpack-directory', type=Path)
    parser.add_argument('--expected-contracts-sha256')
    for name in ('expected-archive-sha256', 'expected-envelope-sha256', 'producer-run-id',
                 'producer-run-attempt', 'producer-workflow-ref', 'producer-job'):
        parser.add_argument('--' + name)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    require(bool(args.version) or (args.mode == 'integration' and push_context(os.environ)),
            'explicit version required outside the owner-created candidate push')
    proof = verify_source(root, expected_sha=os.environ['GITHUB_SHA'], expected_version=args.version or None)
    expected = {'source_sha': proof['source_sha'], 'version': proof['version'],
                'source_tree': subprocess.check_output(['git', 'rev-parse', 'HEAD^{tree}'], text=True).strip(),
                'run_id': os.environ['GITHUB_RUN_ID']}
    if args.mode == 'integration':
        value = fetch_integration(args.integration_run or '', expected['source_sha'])
    elif args.mode == 'audits':
        audits(args.directory)
        value = {**expected, 'passed': True}
    elif args.mode == 'dependencies':
        require(args.cloud_directory is not None and args.unpack_directory is not None,
                'cloud archive and fresh external unpack directory required')
        trust = dependency.trust_arguments(args, expected['source_sha'])
        report = dependency_contract(args.directory, args.cloud_directory, args.unpack_directory,
                                     root, expected, trust)
        value = {**expected, 'passed': True, 'dependency_contract': report,
                 'evidence_inventory': evidence_inventory(args.directory)}
    else:
        require(args.cloud_directory is not None and args.unpack_directory is not None,
                'cloud archive and fresh external unpack directory required')
        trust = dependency.trust_arguments(args, expected['source_sha'])
        bundle(args.directory, args.output, expected, dependency_options=(root, args.cloud_directory,
               args.unpack_directory, trust, args.expected_contracts_sha256))
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    if args.github_output:
        require(args.mode == 'integration', 'outputs supported only after source/integration validation')
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as stream:
            stream.write('version=' + proof['version'] + '\n')
            stream.write('integration_run_id=' + value['integration_run_id'] + '\n')
        with open(os.environ['GITHUB_ENV'], 'a', encoding='utf-8') as stream:
            stream.write('VERSION=' + proof['version'] + '\n')


if __name__ == '__main__':
    main()
