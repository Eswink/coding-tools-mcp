"""Strict same-run dual-platform pre-release; never waive an installed platform."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import 发布资产v8 as transport
from 聊天授权发布v26 import (text, identity, frontend_summary, archive_evidence,
    release_guide, anonymous_downloads)
from exclusive_native_gate import load, require, verify, SCENARIO
from exclusive_packages import verify_record
from 发布版本校验v4 import verify_source

REPO = 'Eswink/coding-tools-mcp'
REF = 'refs/heads/release/exclusive-v0.4.0'
MANIFEST = 'exclusive-package.json'
HEX = re.compile(r'[0-9a-f]{64}')


def rust_summary(log: str) -> int:
    rows = re.findall(r'^test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored; (\d+) measured; (\d+) filtered out;', log, re.M)
    require(rows and all(all(int(v) == 0 for v in row[1:]) for row in rows), 'missing/full Rust suite or failure/ignore/filter')
    total = sum(int(row[0]) for row in rows)
    successes = re.findall(r'^test \S+ \.\.\. ok$', log, re.M)
    require(total >= 400 and len(successes) == total, 'incomplete Rust result lines')
    require('test result: FAILED' not in log and re.search(r'^error(?:\[E\d+\])?:', log, re.M) is None, 'Rust failure')
    return total


def source_proof(root: Path, checkout: Path, source: str, tree: str) -> dict:
    exported = root / 'exclusive-source'
    require(text(exported / 'source.txt').strip() == source and text(exported / 'tree.txt').strip() == tree,
            'source export identity mismatch')
    result = {}
    for system in ('windows-latest', 'ubuntu-latest'):
        folder = root / ('exclusive-regression-' + system)
        require(text(folder / 'source.txt').strip() == source, 'source regression identity mismatch')
        total = rust_summary(text(folder / 'rust-tests.txt'))
        for name in ('rust-check.txt', 'production-warnings.txt'):
            log = text(folder / name)
            require('Finished' in log and re.search(r'^error(?:\[E\d+\])?:', log, re.M) is None, 'failed production compile')
        require('svelte-check found 0 errors and 0 warnings' in text(folder / 'frontend-check.txt'), 'frontend type/warning failure')
        require('built in' in text(folder / 'frontend-build.txt'), 'frontend production build incomplete')
        front = frontend_summary(text(folder / 'frontend-tests.txt'))
        require(front >= 139, 'new approval regressions missing')
        result[system] = {'rust_passed': total, 'frontend_passed': front, 'failed': 0, 'ignored_or_skipped': 0}
    browser = root / 'exclusive-browser'
    doc = load(browser / 'exclusive-evidence/browser-results.json')
    require(doc.get('status') == 'passed' and doc.get('passed') == 12 and doc.get('failure') is None
            and doc.get('page_errors') == [] and doc.get('native_notifications_verified') is False, 'browser scenario failed or mislabeled')
    rows = doc.get('tests', [])
    require(type(rows) is list and len(rows) == 12 and len({r.get('test') for r in rows}) == 12
            and all(r.get('status') == 'passed' for r in rows), 'twelve unique browser cases required')
    expected_sources = {name: hashlib.sha256((checkout / path).read_bytes()).hexdigest() for name, path in (
        ('chat-authorization', 'src/lib/chat-authorization.ts'), ('remote-session-policy', 'src/lib/remote-session-policy.ts'),
        ('ChatAuthorizationHost', 'src/lib/components/ChatAuthorizationHost.svelte'),
        ('RemoteSessionSettings', 'src/lib/components/RemoteSessionSettings.svelte'))}
    require(load(browser / 'exclusive-ui/source-manifest.json').get('sources') == expected_sources, 'browser production source mismatch')
    readiness = load(browser / 'exclusive-evidence/readiness-results.json')
    require(readiness.get('status') == 'passed' and [t.get('callback') for t in readiness.get('tests', [])]
            == ['releaseConfirm', 'releaseSave'] and all(t.get('candidate') == 'readiness is side-effect-free; explicit decision required'
            for t in readiness['tests']), 'readiness regression missing')
    before = root / 'exclusive-failure-first'
    require(text(before / 'baseline-sha.txt').strip() == 'a0551c447712104e2c2cb253d3d8a5a966518580', 'wrong failure-first baseline')
    failed = text(before / 'failure-first.txt')
    require('occupied workspace must not create B pending' in failed and '1 failed' in failed and 'error[E' not in failed,
            'baseline must fail the targeted assertion, not compilation')
    return {'platforms': result, 'browser_cases': 12, 'readiness_cases': 2, 'baseline_assertion_reproduced': True}


def installed_proof(folder: Path, source: str, run_id: str, version: str, kind: str, digest: str) -> dict:
    value = load(folder / 'exclusive-native.json')
    proof = verify(value, source=source, run_id=run_id, version=version, kind=kind, binary_sha256=digest)
    require(value.get('os_toast_visibility_verified') is False, 'OS toast visibility not established by this fixture')
    return {'kind': kind, 'passed': proof['passed'], 'native_stages': proof['native_stages'],
            'binary_sha256': digest, 'real_chatgpt_verified': False, 'os_toast_visibility_verified': False}


def windows_account(folder: Path, source: str, run_id: str, digest: str) -> None:
    doc = load(folder / '标准用户隔离结果v22.json')
    require(doc.get('source_sha') == source and doc.get('run_id') == run_id, 'standard-user proof identity mismatch')
    for key in ('passed', 'genuine_standard_account', 'account_deleted', 'profile_deleted', 'owned_processes_closed', 'credentials_scan_completed'):
        require(doc.get(key) is True, 'standard-user isolation incomplete: ' + key)
    require(doc.get('credentials_found') is False and doc.get('sandbox_disabled') is False and doc.get('native_exit_code') == 0,
            'standard-user credentials/sandbox/exit failure')
    actual = doc.get('actual_logon', {})
    require(actual.get('actual_child_identity_verified') is True and actual.get('token', {}).get('elevated') is False
            and actual.get('token', {}).get('integrity_rid') == 8192 and actual.get('restricted') is False
            and actual.get('manual_desktop_acl') is False and actual.get('launch_api') == 'CreateProcessWithLogonW'
            and actual.get('account_sid_sha256') == doc.get('account_sid_sha256')
            and HEX.fullmatch(doc.get('account_sid_sha256', '')), 'not genuine medium-integrity standard-user execution')
    payload = load(folder / '安装载荷核验v7.json')
    require(payload.get('passed') is True and payload.get('installed_sha256') == payload.get('expected_installed_sha256') == digest,
            'NSIS installed payload proof mismatch')


def compose(root: Path, output: Path, checkout: Path, *, source: str, tree: str, version: str, run_id: str, ref: str):
    require(ref == REF and version == '0.4.0', 'unapproved version or release branch')
    require(re.fullmatch(r'[0-9a-f]{40}', source) and re.fullmatch(r'[0-9a-f]{40}', tree)
            and re.fullmatch(r'[1-9][0-9]*', run_id), 'invalid release identity')
    checks = source_proof(root, checkout, source, tree)
    ubuntu, windows = root / 'exclusive-ubuntu-packages', root / 'exclusive-windows-package'
    linux, win = load(ubuntu / MANIFEST), load(windows / MANIFEST)
    for doc in (linux, win): identity(doc, source, tree, version, run_id)
    require(linux.get('build_kind') == 'release-packaged' and set(linux.get('packages', {})) == {'deb', 'appimage'}, 'both Linux packages required')
    files, folders, matrix = [], [ubuntu, windows], []
    for kind, ext in (('deb', '.deb'), ('appimage', '.AppImage')):
        entry = linux['packages'][kind]
        require(entry.get('architecture') == 'amd64' and HEX.fullmatch(entry.get('payload_sha256', '')), 'invalid Linux payload')
        file = verify_record(ubuntu, entry['artifact'])
        require(file.name == f'MCP_{version}_amd64{ext}', 'wrong Linux package name/version')
        files.append(file)
        for system in ('ubuntu-22.04', 'ubuntu-24.04'):
            folder = root / f'exclusive-installed-{system}-{kind}'
            installed = load(folder / MANIFEST); identity(installed, source, tree, version, run_id)
            wanted = entry['artifact']['sha256'] if kind == 'appimage' else entry['payload_sha256']
            require(installed.get('kind') == kind and installed.get('package') == entry['artifact']
                    and installed.get('payload_sha256') == entry['payload_sha256']
                    and installed.get('native_executable_sha256') == wanted, 'installed Linux bytes differ')
            matrix.append({'system': system, **installed_proof(folder, source, run_id, version, kind, wanted)})
            folders.append(folder)
    digest = win.get('payload_sha256', '')
    require(win.get('scenario') == SCENARIO and win.get('kind') == 'nsis' and HEX.fullmatch(digest)
            and win.get('native_executable_sha256') == digest, 'wrong Windows scenario or payload')
    for key in ('silent_install', 'exact_nsis_payload_verified', 'real_native_approval', 'synthetic_conversation_metadata'):
        require(win.get(key) is True, 'Windows acceptance cannot be deferred: ' + key)
    require(win.get('real_chatgpt_verified') is False and type(win.get('signed')) is bool, 'unproven Windows observation')
    installer = verify_record(windows, win['package'])
    require(installer.name == f'MCP_{version}_x64-setup.exe', 'wrong Windows installer name/version')
    windows_account(windows, source, run_id, digest)
    matrix.append({'system': 'windows-x64', **installed_proof(windows, source, run_id, version, 'nsis', digest)})
    files.insert(0, installer)
    summary = {'source_sha': source, 'source_tree': tree, 'version': version, 'run_id': run_id,
        'automated_release_gates_passed': True, 'prerelease': True, 'validation': checks, 'installed_matrix': matrix,
        'windows_signed': win['signed'], 'real_chatgpt_verified': False, 'os_toast_visibility_verified': False,
        'scope': 'same-source automated Windows/Ubuntu release; real ChatGPT and OS toast observations remain manual'}
    output.mkdir(parents=True, exist_ok=False)
    delivered = []
    for file in files:
        target = output / file.name; shutil.copyfile(file, target); delivered.append(target)
    guide = output / f'Verification_v{version}.md'
    guide.write_text(text(release_guide(checkout, version)) + '\n\n## 本次构建身份\n\n' +
        f'源码：`{source}`\n\n文件树：`{tree}`\n\n工作流：`{run_id}`\n', encoding='utf-8')
    report = output / f'Release-scope_v{version}.json'
    report.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    folders += [root / 'exclusive-browser', root / 'exclusive-failure-first']
    folders += [root / ('exclusive-regression-' + system) for system in ('windows-latest', 'ubuntu-latest')]
    archive = output / f'Exclusive-evidence_v{version}.zip'
    archive_evidence(root, archive, folders, [report, guide])
    delivered += [archive, guide, report]
    def asset(path):
        return {'path': path, 'name': path.name, 'label': path.name, 'size': path.stat().st_size,
                'digest': 'sha256:' + transport.digest(path), 'content_type': 'application/octet-stream'}
    assets = [asset(path) for path in delivered]
    sums = output / f'SHA256SUMS_v{version}.txt'
    sums.write_text(''.join(a['digest'][7:] + '  ' + a['name'] + '\n' for a in assets), encoding='utf-8')
    assets.append(asset(sums)); transport.verify_assets(assets, [], complete=False)
    return assets, summary


class AnchoredGitHub(transport.GitHub):
    def __init__(self, token: str, source: str):
        super().__init__(token); self.source = source

    def request(self, method, path, data=None, allow_missing=False, upload=None):
        if method != 'GET':
            require(super().request('GET', '/git/ref/heads/main').get('object', {}).get('sha') == self.source,
                    'main moved; refusing release mutation')
        if method == 'POST' and path == '/releases':
            data = {**data, 'name': data['tag_name'] + ' — 独占会话与可配置刷新 · Windows/Ubuntu预发布'}
        return super().request(method, path, data, allow_missing=allow_missing, upload=upload)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('evidence', 'output'): parser.add_argument('--' + name, type=Path, required=True)
    for name in ('source', 'run-id'): parser.add_argument('--' + name, required=True)
    parser.add_argument('--publish', action='store_true'); args = parser.parse_args()
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('GITHUB_REPOSITORY') == REPO
            and os.environ.get('GITHUB_SHA') == args.source and os.environ.get('GITHUB_RUN_ID') == args.run_id,
            'exact hosted workflow identity required')
    checkout = Path(__file__).resolve().parents[1]
    version = verify_source(checkout, expected_sha=args.source)['version']
    tree = subprocess.check_output(['git', 'rev-parse', 'HEAD^{tree}'], cwd=checkout, text=True).strip()
    assets, summary = compose(args.evidence.resolve(), args.output.resolve(), checkout, source=args.source,
        tree=tree, version=version, run_id=args.run_id, ref=os.environ.get('GITHUB_REF', ''))
    if not args.publish: print(json.dumps(summary, ensure_ascii=False)); return
    api = AnchoredGitHub(os.environ.get('GH_TOKEN', ''), args.source)
    notes = text(args.output / f'Verification_v{version}.md')
    receipt = transport.publish(api, assets, args.source, version, notes)
    receipt.update(verification_scope=summary, anonymous_downloads=anonymous_downloads(assets, version))
    require(api.request('GET', '/git/ref/heads/main')['object']['sha'] == args.source, 'main moved after publication')
    (args.output / 'publication-receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'publication_verified': True, 'source': args.source, 'tag': receipt['tag'], 'prerelease': True}))


if __name__ == '__main__': main()
