"""Publish a new prerelease only after every exact-source installed package gate."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
from exclusive_release_evidence import verify_all, require
from 发布版本校验v4 import verify_source
import 发布资产v8 as transport
from 聊天授权发布v26 import archive_evidence, anonymous_downloads, release_guide, text

REPO = 'Eswink/coding-tools-mcp'
REF = 'refs/heads/release/exclusive-v0.4.0'


class AnchoredGitHub(transport.GitHub):
    def __init__(self, token: str, source: str):
        super().__init__(token); self.source = source

    def request(self, method, path, data=None, allow_missing=False, upload=None):
        if method != 'GET':
            current = super().request('GET', '/git/ref/heads/main')
            require(current.get('object', {}).get('sha') == self.source, 'main moved before publication')
        if method == 'POST' and path == '/releases':
            data = {**data, 'name': data['tag_name'] + ' — 独占会话与 OAuth 刷新 · Windows / Ubuntu'}
        return super().request(method, path, data, allow_missing=allow_missing, upload=upload)


def compose(root: Path, repo: Path, output: Path, *, source: str, tree: str, version: str, run_id: str, ref: str):
    require(ref == REF and version == '0.4.0', 'unapproved release ref/version')
    files, summary, folders = verify_all(root, repo, source=source, tree=tree, version=version, run_id=run_id)
    output.mkdir(parents=True, exist_ok=True)
    manifest = output / f'Exclusive-release-summary_v{version}.json'
    manifest.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    guide = release_guide(repo, version)
    notes = output / f'Verification_v{version}.md'
    notes.write_text(f'# v{version} 独占会话与刷新凭据 · 双平台预发布\n\n源码 `{source}`；Actions `{run_id}`。\n\n'
        'Windows NSIS 与 Ubuntu 22.04/24.04 × DEB/AppImage 的实际安装及十二阶段原生审批/本地 HTTP 验收通过。\n\n'
        '**会话元数据和凭据均为隔离测试夹具，不代表真实 ChatGPT 账号端到端验收。OS 通知横幅可见性仍需在本机核验。**\n\n'
        + text(guide), encoding='utf-8')
    bundle = output / f'Exclusive-session-evidence_v{version}.zip'
    archive_evidence(root, bundle, folders, [manifest, notes])
    files += [(bundle, bundle.name, 'application/zip'), (manifest, manifest.name, 'application/json'),
              (notes, notes.name, 'text/markdown; charset=utf-8')]
    assets = []
    for path, name, mime in files:
        assets.append({'path': path, 'name': name, 'label': name, 'size': path.stat().st_size,
                       'digest': 'sha256:' + transport.digest(path), 'content_type': mime})
    sums = output / f'SHA256SUMS_v{version}.txt'
    sums.write_text(''.join(item['digest'][7:] + '  ' + item['name'] + '\n' for item in assets), encoding='utf-8')
    assets.append({'path': sums, 'name': sums.name, 'label': sums.name, 'size': sums.stat().st_size,
                   'digest': 'sha256:' + transport.digest(sums), 'content_type': 'text/plain; charset=utf-8'})
    transport.verify_assets(assets, [], complete=False)
    return assets, summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('evidence', 'output'): p.add_argument('--' + key, type=Path, required=True)
    for key in ('source', 'run-id'): p.add_argument('--' + key, required=True)
    p.add_argument('--publish', action='store_true'); args = p.parse_args()
    require(os.environ.get('GITHUB_REPOSITORY') == REPO and os.environ.get('GITHUB_ACTIONS') == 'true'
        and args.source == os.environ.get('GITHUB_SHA') and args.run_id == os.environ.get('GITHUB_RUN_ID'), 'exact hosted run required')
    repo = Path(__file__).resolve().parents[1]
    version = verify_source(repo, expected_sha=args.source)['version']
    tree = subprocess.check_output(['git', 'rev-parse', 'HEAD^{tree}'], cwd=repo, text=True).strip()
    assets, summary = compose(args.evidence.resolve(), repo, args.output.resolve(), source=args.source, tree=tree,
        version=version, run_id=args.run_id, ref=os.environ.get('GITHUB_REF', ''))
    if not args.publish:
        print(json.dumps(summary, ensure_ascii=False)); return
    api = AnchoredGitHub(os.environ.get('GH_TOKEN', ''), args.source)
    notes = next(item['path'] for item in assets if item['name'].endswith('.md')).read_text(encoding='utf-8')
    receipt = transport.publish(api, assets, args.source, version, notes)
    receipt.update(verification_scope=summary, anonymous_downloads=anonymous_downloads(assets, version))
    require(api.request('GET', '/git/ref/heads/main')['object']['sha'] == args.source, 'main moved after publication')
    (args.output / 'exclusive-publication-receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'publication_verified': True, 'source': args.source, 'tag': receipt['tag'],
                     'native_combinations': 5, 'real_chatgpt_verified': False}, ensure_ascii=False))


if __name__ == '__main__': main()
