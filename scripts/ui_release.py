"""UI v0.5.0 same-source release, composing rather than replacing security gates."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from exclusive_release import (REPO, MANIFEST, HEX, SCENARIO, transport, text, identity, source_proof,
    windows_account, verify_record, archive_evidence, release_guide, anonymous_downloads, verify_source, load, require)
from ui_refactor_native_gate import verify as native_verify
from ui_release_evidence import verify as route_verify

REF = 'refs/heads/release/ui-v0.5.0'


def installed_proof(folder, source, run_id, version, kind, digest):
    value = load(folder / 'exclusive-native.json')
    proof = native_verify(value, directory=folder, source=source, run_id=run_id, version=version, kind=kind, binary_sha256=digest)
    require(value.get('os_toast_visibility_verified') is False, 'OS toast visibility not established')
    return {'kind': kind, 'passed': proof['passed'], 'native_stages': proof['native_stages'],
            'ui_screens': proof['ui_screens'], 'binary_sha256': digest,
            'real_chatgpt_verified': False, 'os_toast_visibility_verified': False}


def compose(root: Path, output: Path, checkout: Path, *, source: str, tree: str, version: str, run_id: str, ref: str):
    require(ref == REF and version == '0.5.0', 'unapproved version or release branch')
    require(re.fullmatch(r'[0-9a-f]{40}', source) and re.fullmatch(r'[0-9a-f]{40}', tree)
            and re.fullmatch(r'[1-9][0-9]*', run_id), 'invalid release identity')
    checks = source_proof(root, checkout, source, tree)
    require(all(p['frontend_passed'] >= 180 for p in checks['platforms'].values()), 'UI frontend regressions missing')
    checks['ui_routes'] = route_verify(root / 'ui-refactor-pages-candidate', checkout, source=source, tree=tree, run_id=run_id)
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
        'scope': 'UI refactor automated Windows/Ubuntu release; host account, OS toast and subjective visual approval are not inferred'}
    output.mkdir(parents=True, exist_ok=False)
    delivered = []
    for file in files:
        target = output / file.name; shutil.copyfile(file, target); delivered.append(target)
    guide = output / f'Verification_v{version}.md'
    guide.write_text(text(release_guide(checkout, version)) + '\n\n## 本次构建身份\n\n' +
        f'源码：`{source}`\n\n文件树：`{tree}`\n\n工作流：`{run_id}`\n', encoding='utf-8')
    report = output / f'Release-scope_v{version}.json'
    report.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    folders += [root / 'exclusive-browser', root / 'exclusive-failure-first', root / 'ui-refactor-pages-candidate']
    folders += [root / ('exclusive-regression-' + system) for system in ('windows-latest', 'ubuntu-latest')]
    archive = output / f'UI-evidence_v{version}.zip'
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
            data = {**data, 'name': data['tag_name'] + ' — 新版桌面控制台 UI · Windows/Ubuntu预发布'}
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
