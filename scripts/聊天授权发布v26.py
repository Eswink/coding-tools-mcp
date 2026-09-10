"""Publish exact-source authorization candidates; deferred GUI checks are NOT PASS."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import urllib.error
import urllib.request
import zipfile

import 发布资产v8 as transport
import 聊天授权证据门禁v18 as native
from 聊天授权安装核验v10 import verify_record
from 发布版本校验v4 import verify_source

REPO = 'Eswink/coding-tools-mcp'
STRICT_REF = 'refs/heads/release/聊天授权v26'
LOCAL_REF = 'refs/heads/release/聊天授权本地验收v26'
MANIFEST = '聊天授权安装来源v10.json'
NATIVE = '聊天授权原生结果v6.json'
SUMMARY = '聊天授权交付范围v26.json'
HEX64 = re.compile(r'[0-9a-f]{64}')
require = native.require
load = native.load


def identity(doc: dict, source: str, tree: str, version: str, run_id: str) -> None:
    expected = {'source_sha': source, 'source_tree': tree, 'version': version, 'run_id': run_id}
    require(all(doc.get(k) == v for k, v in expected.items()), 'source/tree/version/run mismatch')
    require(doc.get('passed') is True, 'failed package record')


def text(path: Path, limit: int = 4 * 1024 * 1024) -> str:
    require(path.is_file() and not path.is_symlink(), 'missing regular text evidence: ' + path.name)
    raw = path.read_bytes()
    require(0 < len(raw) <= limit, 'empty or oversized text evidence')
    return raw.decode('utf-8-sig')


def baseline(root: Path, source: str) -> dict:
    result = {}
    for os_name in ('windows-latest', 'ubuntu-latest'):
        rust = root / f'聊天授权Rust-{os_name}-v4'
        front = root / f'聊天授权前端-{os_name}-v4'
        for folder in (rust, front):
            require(text(folder / '源码版本v4.txt').strip() == source, 'baseline source mismatch')
        log = text(rust / '完整回归v4.txt')
        rows = re.findall(r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored;', log)
        require(rows and all(int(f) == int(i) == 0 for _, f, i in rows), 'Rust failure/ignored/missing summary')
        total = sum(int(n) for n, _, _ in rows)
        require(total >= 320 and 'test result: FAILED' not in log, 'incomplete full Rust regression')
        for name in ('编译检查v4.txt', '生产零警告v5.txt'):
            compile_log = text(rust / name)
            require('Finished' in compile_log and not re.search(r'error(?:\[E\d+\])?:', compile_log), 'compile evidence failure')
        front_log = text(front / '前端回归v4.txt')
        require(re.search(r'# fail 0\b', front_log) is not None and not re.search(r'^not ok\b', front_log, re.M), 'frontend tests failed')
        result[os_name] = {'rust_passed': total, 'rust_failed': 0, 'rust_ignored': 0, 'frontend_passed': True}
    return result


def native_proof(directory: Path, source: str, run_id: str, version: str, kind: str, digest: str) -> dict:
    return native.verify(load(directory / NATIVE), source=source, run_id=run_id,
                         version=version, kind=kind, binary_sha256=digest)


def windows_proof(folder: Path, doc: dict, local: bool, source: str, run_id: str, version: str) -> dict:
    require(doc.get('kind') == 'nsis', 'wrong Windows package type')
    sha = doc.get('payload_sha256', '')
    require(isinstance(sha, str) and HEX64.fullmatch(sha) is not None and
            doc.get('native_executable_sha256') == sha, 'Windows installed payload mismatch')
    require(doc.get('silent_install') is True and doc.get('exact_nsis_payload_verified') is True, 'Windows installation cannot be waived')
    require(doc.get('real_chatgpt_verified') is False, 'unproven real ChatGPT assertion')
    if not local:
        require(doc.get('real_native_approval') is True, 'strict mode requires actual native approval')
        native_proof(folder, source, run_id, version, 'nsis', sha)
        return {'status': 'passed', 'stages': 8, 'real_chatgpt_verified': False}
    require(doc.get('real_native_approval') is False and doc.get('native_status') == 'pending_local_verification'
            and isinstance(doc.get('waiver'), str) and 'NOT PASS' in doc['waiver'], 'local deferral must be explicit, never PASS')
    require(not (folder / NATIVE).exists(), 'failed/native records cannot be silently waived into a local package')
    smoke = load(folder / '安装冒烟结果v7.json')
    payload = load(folder / '安装载荷核验v7.json')
    require(smoke.get('source_sha') == payload.get('source_sha') == source and smoke.get('version') == version,
            'Windows basic smoke source/version mismatch')
    require(smoke.get('platform') == 'windows-x64' and payload.get('passed') is True, 'Windows basic smoke failed')
    require(smoke.get('installed_binary_sha256') == payload.get('installed_sha256') ==
            payload.get('expected_installed_sha256') == sha, 'Windows basic smoke digest mismatch')
    for key in ('silent_install', 'exact_nsis_payload_verified', 'native_window_created', 'sustained_process'):
        require(doc.get(key) is True and smoke.get(key) is True, 'Windows basic smoke cannot be waived: ' + key)
    return {'status': 'pending_local_verification', 'stages': 0, 'basic_install_and_window_smoke': True,
            'waiver': doc['waiver'], 'real_chatgpt_verified': False}


def archive_evidence(root: Path, output: Path, folders: list[Path], extras: list[Path]) -> None:
    # No executable/runtime archive, configuration, credential store or user profile is exported.
    entries = {}
    for folder in folders:
        require(folder.is_dir() and not folder.is_symlink(), 'missing evidence directory')
        for file in sorted(folder.rglob('*')):
            require(not file.is_symlink(), 'symlink evidence prohibited')
            if not file.is_file() or file.suffix.lower() not in ('.json', '.txt', '.log', '.md', '.png'): continue
            require(file.stat().st_size <= 8 * 1024 * 1024, 'individual evidence too large')
            entries[file.relative_to(root).as_posix()] = file
    for file in extras: entries['交付说明/' + file.name] = file
    require(len(entries) < 1000 and sum(p.stat().st_size for p in entries.values()) < 80 * 1024 * 1024, 'evidence bounds exceeded')
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, file in sorted(entries.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            bundle.writestr(info, file.read_bytes())


def compose(root: Path, output: Path, *, source: str, tree: str, version: str, run_id: str,
            ref: str, guide: Path) -> tuple[list[dict], dict]:
    require(ref in (STRICT_REF, LOCAL_REF), 'unapproved release branch')
    require(re.fullmatch(r'[0-9a-f]{40}', source) is not None and re.fullmatch(r'[0-9a-f]{40}', tree) is not None, 'invalid Git identity')
    require(re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version) is not None and re.fullmatch(r'[1-9][0-9]*', run_id) is not None, 'invalid version/run')
    local = ref == LOCAL_REF
    checks = baseline(root, source)
    ubuntu = root / '聊天授权Ubuntu包v10'
    windows = root / '聊天授权Windows包v10'
    linux = load(ubuntu / MANIFEST); win = load(windows / MANIFEST)
    for doc in (linux, win): identity(doc, source, tree, version, run_id)
    require(linux.get('build_kind') == 'release-packaged' and set(linux.get('packages', {})) == {'deb', 'appimage'}, 'both Ubuntu packages required')
    files, folders, matrix = [], [ubuntu, windows], []
    for kind, ext in (('deb', '.deb'), ('appimage', '.AppImage')):
        entry = linux['packages'][kind]
        require(entry.get('architecture') == 'amd64' and HEX64.fullmatch(entry.get('payload_sha256', '')) is not None, 'invalid Linux payload')
        file = verify_record(ubuntu, entry['artifact'])
        files.append((file, f'MCP_{version}_amd64{ext}', 'application/octet-stream'))
        for system in ('ubuntu-22.04', 'ubuntu-24.04'):
            folder = root / f'聊天授权已安装-{system}-{kind}-v10'
            installed = load(folder / MANIFEST); identity(installed, source, tree, version, run_id)
            require(installed.get('kind') == kind and installed.get('package') == entry['artifact']
                    and installed.get('payload_sha256') == entry['payload_sha256'], 'installed Linux package mismatch')
            executable_sha = entry['artifact']['sha256'] if kind == 'appimage' else entry['payload_sha256']
            require(installed.get('native_executable_sha256') == executable_sha, 'Linux GUI executable digest mismatch')
            native_proof(folder, source, run_id, version, kind, executable_sha)
            matrix.append({'system': system, 'kind': kind, 'status': 'passed', 'stages': 8})
            folders.append(folder)
    file = verify_record(windows, win['package'])
    require(file.suffix == '.exe', 'expected Windows installer')
    files.append((file, f'MCP_{version}_x64-setup.exe', 'application/vnd.microsoft.portable-executable'))
    win_result = windows_proof(windows, win, local, source, run_id, version)
    summary = {'source_sha': source, 'source_tree': tree, 'version': version, 'run_id': run_id,
        'release_ref': ref, 'artifact_gates_passed': True, 'all_native_gui_verified': not local,
        'real_chatgpt_verified': False, 'native_metadata': 'synthetic, not authenticated ChatGPT provenance',
        'windows': win_result, 'ubuntu': matrix, 'baseline': checks,
        'windows_signed': win.get('signed') is True, 'prerelease': True,
        'scope': 'Installable candidate; real ChatGPT two-window acceptance remains local.'}
    output.mkdir(parents=True, exist_ok=True)
    summary_file = output / SUMMARY
    summary_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    scope = ('Windows 原生完整审批：**待用户本地核验，不是 PASS**。CI 仅完成真实安装、精确载荷、窗口创建与存活。'
             if local else 'Windows 原生完整审批：八阶段通过；会话元数据是测试夹具，不是真实 ChatGPT。')
    notes = output / f'聊天授权安装与核验v{version}.md'
    notes.write_text(f'# v{version} 聊天授权 · Ubuntu / Windows 预发布\n\n{scope}\n\n'
        f'源码：`{source}`；Actions：`{run_id}`。Ubuntu 22.04/24.04 × DEB/AppImage 四组合各八阶段通过。\n\n'
        '**真实 ChatGPT 双聊天与公网联调尚未验收；未签名包可能显示未知发布者。不是稳定版或全面安全认证。**\n\n'
        + text(guide), encoding='utf-8')
    folders.extend(root / f'聊天授权{area}-{system}-v4' for area in ('Rust', '前端') for system in ('windows-latest', 'ubuntu-latest'))
    bundle = output / f'聊天授权双平台验收证据v{version}.zip'
    archive_evidence(root, bundle, folders, [summary_file, notes])
    files.extend([(bundle, f'Chat-authorization-evidence_v{version}.zip', 'application/zip'),
                  (notes, f'Verification_v{version}.md', 'text/markdown; charset=utf-8')])
    assets = [{'path': p, 'name': name, 'label': p.name, 'size': p.stat().st_size,
               'digest': 'sha256:' + transport.digest(p), 'content_type': mime} for p, name, mime in files]
    sums = output / f'聊天授权校验和v{version}.txt'
    sums.write_text(''.join(a['digest'][7:] + '  ' + a['name'] + '\n' for a in assets), encoding='utf-8')
    assets.append({'path': sums, 'name': f'SHA256SUMS_v{version}.txt', 'label': sums.name,
        'size': sums.stat().st_size, 'digest': 'sha256:' + transport.digest(sums), 'content_type': 'text/plain; charset=utf-8'})
    transport.verify_assets(assets, [], complete=False)
    return assets, summary


class AnchoredGitHub(transport.GitHub):
    def __init__(self, token: str, source: str):
        super().__init__(token); self.source = source

    def request(self, method, path, data=None, allow_missing=False, upload=None):
        if method != 'GET':
            ref = super().request('GET', '/git/ref/heads/main')
            require(ref.get('object', {}).get('sha') == self.source, 'main moved; refusing publication mutation')
        if method == 'POST' and path == '/releases':
            data = {**data, 'name': data['tag_name'] + ' — 聊天授权 · Ubuntu与Windows验收版'}
        return super().request(method, path, data, allow_missing=allow_missing, upload=upload)


def anonymous_downloads(assets: list[dict], version: str) -> list[dict]:
    result = []
    for item in assets:
        url = f'https://github.com/{REPO}/releases/download/v{version}/{item["name"]}'
        request = urllib.request.Request(url, headers={'User-Agent': 'coding-tools-anonymous-verification-v26'})
        size, digest = 0, hashlib.sha256()
        with urllib.request.urlopen(request, timeout=120) as response:
            while chunk := response.read(1024 * 1024):
                size += len(chunk); require(size <= item['size'], 'public download exceeded expected size')
                digest.update(chunk)
        require(size == item['size'] and 'sha256:' + digest.hexdigest() == item['digest'], 'public attachment differs')
        result.append({'name': item['name'], 'size': size, 'sha256': digest.hexdigest(), 'anonymous_download_verified': True})
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    ref = os.environ.get('GITHUB_REF', '')
    require(os.environ.get('GITHUB_REPOSITORY') == REPO and os.environ.get('GITHUB_ACTIONS') == 'true'
            and args.source == os.environ.get('GITHUB_SHA') and args.run_id == os.environ.get('GITHUB_RUN_ID'), 'exact hosted CI source/run required')
    root = Path(__file__).resolve().parents[1]
    version = verify_source(root, expected_sha=args.source)['version']
    tree = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD^{tree}'], text=True).strip()
    guide = root / 'docs/releases' / f'聊天授权安装与本地核验v{version}.md'
    assets, summary = compose(args.evidence.resolve(), args.output.resolve(), source=args.source,
                              tree=tree, version=version, run_id=args.run_id, ref=ref, guide=guide)
    if not args.publish:
        print(json.dumps(summary, ensure_ascii=False)); return
    api = AnchoredGitHub(os.environ.get('GH_TOKEN', ''), args.source)
    notes = next(a['path'] for a in assets if a['name'].endswith('.md')).read_text(encoding='utf-8')
    receipt = transport.publish(api, assets, args.source, version, notes)
    receipt.update(verification_scope=summary, anonymous_downloads=anonymous_downloads(assets, version))
    require(api.request('GET', '/git/ref/heads/main')['object']['sha'] == args.source, 'main moved after publication')
    (args.output / '聊天授权公开回执v26.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'publication_verified': True, 'tag': receipt['tag'], 'source': args.source,
                      'windows_native_status': summary['windows']['status'], 'real_chatgpt_verified': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
