"""Read-only exact-source gates for the exclusive-refresh prerelease.

Legacy evidence can be loaded for parser reuse, but eight-stage/multi-owner
acceptance or a deferred Windows GUI test never satisfies this release contract.
"""
from __future__ import annotations
import ast
import hashlib
from pathlib import Path
import re
from exclusive_native_gate import load, require, verify as native_verify, TEST_NAMES
from exclusive_packages import verify_record
from 聊天授权发布v26 import text, frontend_summary, identity

MANIFEST = 'exclusive-package.json'
NATIVE = 'exclusive-native.json'


def full_regression(folder: Path, source: str, minimum: int) -> dict:
    require(text(folder / 'source.txt').strip() == source, 'regression source mismatch')
    log = text(folder / 'rust-tests.txt')
    rows = re.findall(r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored; (\d+) measured; (\d+) filtered out;', log)
    require(rows and all(all(int(v) == 0 for v in row[1:]) for row in rows), 'incomplete/filtered Rust suite')
    require('test result: FAILED' not in log and not re.search(r'^test .* \.\.\. (?:FAILED|ignored)', log, re.M), 'Rust failure or ignored test')
    count = sum(int(row[0]) for row in rows)
    require(count >= minimum, 'Rust suite unexpectedly reduced')
    require(len(re.findall(r'^test .* \.\.\. ok\s*$', log, re.M)) == count, 'truncated Rust result lines')
    for name in ('rust-check.txt', 'production-warnings.txt'):
        value = text(folder / name)
        require('Finished' in value and not re.search(r'error(?:\[E\d+\])?:', value), 'Rust compilation failed')
    checked = text(folder / 'frontend-check.txt')
    require('svelte-check found 0 errors and 0 warnings' in checked, 'frontend type/warning check failed')
    build = text(folder / 'frontend-build.txt')
    require('built in' in build and not re.search(r'error during build|Build failed', build, re.I), 'production frontend build failed')
    count_front = frontend_summary(text(folder / 'frontend-tests.txt'))
    require(count_front >= 139, 'frontend suite unexpectedly reduced')
    return {'rust_passed': count, 'rust_failed': 0, 'rust_ignored': 0, 'frontend_passed': count_front}


def browser_proof(folder: Path, repo: Path) -> dict:
    proof = load(folder / 'exclusive-evidence/browser-results.json')
    expected = [node.args[0].value for node in ast.walk(ast.parse((repo / 'tests/exclusive-ui-browser.py').read_text()))
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'done'
                and node.args and isinstance(node.args[0], ast.Constant)]
    require(len(expected) == len(set(expected)) == 12, 'unexpected browser scenario contract')
    require(proof.get('status') == 'passed' and proof.get('passed') == 12 and proof.get('failure') is None
            and proof.get('page_errors') == [] and proof.get('native_notifications_verified') is False, 'browser regression incomplete')
    require(proof.get('tests') == [{'test': name, 'status': 'passed'} for name in expected], 'browser cases missing or replaced')
    manifest = load(folder / 'exclusive-ui/source-manifest.json')
    sources = {'chat-authorization': 'src/lib/chat-authorization.ts',
               'remote-session-policy': 'src/lib/remote-session-policy.ts',
               'ChatAuthorizationHost': 'src/lib/components/ChatAuthorizationHost.svelte',
               'RemoteSessionSettings': 'src/lib/components/RemoteSessionSettings.svelte'}
    actual = {key: hashlib.sha256((repo / path).read_bytes()).hexdigest() for key, path in sources.items()}
    require(manifest.get('sources') == actual, 'browser components do not match release source')
    readiness = load(folder / 'exclusive-evidence/readiness-results.json')
    require(readiness.get('status') == 'passed' and readiness.get('tests') == [
        {'callback': name, 'baseline': 'side effect and timeout reproduced',
         'candidate': 'readiness is side-effect-free; explicit decision required'}
        for name in ('releaseConfirm', 'releaseSave')], 'readiness regression failed')
    return {'passed': 12, 'readiness_passed': 2, 'mock_ipc': True, 'native_notifications_verified': False}


def verify_all(root: Path, repo: Path, *, source: str, tree: str, version: str, run_id: str) -> tuple[list[tuple], dict, list[Path]]:
    require(re.fullmatch(r'[0-9a-f]{40}', source) and re.fullmatch(r'[0-9a-f]{40}', tree), 'invalid Git identity')
    require(re.fullmatch(r'[1-9][0-9]*', run_id) and re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version), 'invalid version/run')
    require(text(root / 'exclusive-source/source.txt').strip() == source and text(root / 'exclusive-source/tree.txt').strip() == tree,
            'exported source identity mismatch')
    regression = {system: full_regression(root / f'exclusive-regression-{system}', source, minimum)
                  for system, minimum in [('windows-latest', 428), ('ubuntu-latest', 417)]}
    contracts = root / 'exclusive-release-contracts'
    require(text(contracts / 'source.txt').strip() == source, 'release contract source mismatch')
    for file, minimum in [('native-contracts.txt', 14), ('release-contracts.txt', 18), ('asset-transport-contracts.txt', 20)]:
        content = text(contracts / file)
        matches = re.findall(r'^Ran (\d+) tests? in ', content, re.M)
        require(len(matches) == 1 and int(matches[0]) >= minimum and re.search(r'^OK$', content, re.M)
                and 'FAILED' not in content and 'skipped=' not in content, 'release rejection contracts failed')
    browser = browser_proof(root / 'exclusive-browser', repo)
    base = root / 'exclusive-failure-first'
    require(text(base / 'baseline-sha.txt').strip() == 'a0551c447712104e2c2cb253d3d8a5a966518580', 'wrong failure-first source')
    baseline = text(base / 'failure-first.txt')
    require('occupied workspace must not create B pending' in baseline and '1 failed' in baseline and 'error[E' not in baseline,
            'failure-first proof is not the intended assertion')
    linux_dir, win_dir = root / 'exclusive-ubuntu-packages', root / 'exclusive-windows-package'
    linux, win = load(linux_dir / MANIFEST), load(win_dir / MANIFEST)
    for doc in (linux, win): identity(doc, source, tree, version, run_id)
    require(linux.get('build_kind') == 'release-packaged' and set(linux.get('packages', {})) == {'deb', 'appimage'}, 'missing Ubuntu formats')
    files, matrix = [], []
    folders = [linux_dir, win_dir, base, root / 'exclusive-browser', contracts]
    folders += [root / f'exclusive-regression-{s}' for s in regression]
    for kind, ext in [('deb', '.deb'), ('appimage', '.AppImage')]:
        entry = linux['packages'][kind]
        require(entry.get('architecture') == 'amd64' and re.fullmatch(r'[0-9a-f]{64}', entry.get('payload_sha256', '')), 'invalid Linux payload')
        file = verify_record(linux_dir, entry['artifact'])
        require(file.name == f'MCP_{version}_amd64{ext}', 'Linux artifact name/version mismatch')
        files.append((file, file.name, 'application/octet-stream'))
        for system in ['ubuntu-22.04', 'ubuntu-24.04']:
            folder = root / f'exclusive-installed-{system}-{kind}'
            installed = load(folder / MANIFEST); identity(installed, source, tree, version, run_id)
            require(installed.get('kind') == kind and installed.get('package') == entry['artifact']
                    and installed.get('payload_sha256') == entry['payload_sha256'], 'installed Linux package mismatch')
            executable_sha = entry['artifact']['sha256'] if kind == 'appimage' else entry['payload_sha256']
            require(installed.get('native_executable_sha256') == executable_sha, 'wrong installed executable bytes')
            native_verify(load(folder / NATIVE), source=source, run_id=run_id, version=version, kind=kind, binary_sha256=executable_sha)
            matrix.append({'system': system, 'kind': kind, 'passed': True, 'native_stages': len(TEST_NAMES)})
            folders.append(folder)
    require(win.get('scenario') == 'exclusive-refresh-v1' and win.get('kind') == 'nsis', 'legacy Windows artifact')
    for flag in ['silent_install', 'exact_nsis_payload_verified', 'real_native_approval']:
        require(win.get(flag) is True, 'Windows installation or approval missing: ' + flag)
    require(win.get('real_chatgpt_verified') is False, 'real ChatGPT cannot be inferred from test metadata')
    binary_sha = win.get('payload_sha256', '')
    require(re.fullmatch(r'[0-9a-f]{64}', binary_sha) and win.get('native_executable_sha256') == binary_sha, 'wrong Windows executable')
    native_verify(load(win_dir / NATIVE), source=source, run_id=run_id, version=version, kind='nsis', binary_sha256=binary_sha)
    file = verify_record(win_dir, win['package'])
    require(file.name == f'MCP_{version}_x64-setup.exe', 'wrong Windows installer name')
    files.append((file, file.name, 'application/vnd.microsoft.portable-executable'))
    summary = {'source_sha': source, 'source_tree': tree, 'version': version, 'run_id': run_id,
        'artifact_gates_passed': True, 'prerelease': True, 'all_native_gui_verified': True,
        'windows': {'passed': True, 'native_stages': len(TEST_NAMES), 'signed': win.get('signed') is True},
        'ubuntu': matrix, 'regression': regression, 'browser': browser,
        'real_chatgpt_verified': False, 'os_toast_visibility_verified': False,
        'scope': 'Installed native modal/IPC and local OAuth HTTP with synthetic conversation metadata. Not an OS toast or real ChatGPT certification.'}
    return files, summary, folders
