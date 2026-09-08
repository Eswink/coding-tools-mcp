"""验证安装证据后幂等发布；本地文件保留中文名，传输名唯一且仅含ASCII。"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request
import zipfile

REPO = 'Eswink/coding-tools-mcp'
API = f'https://api.github.com/repos/{REPO}'
UPLOAD = f'https://uploads.github.com/repos/{REPO}'
VERSION = re.compile(r'(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)')
SHA = re.compile(r'[a-f0-9]{40}')
DIGEST = re.compile(r'[a-f0-9]{64}')


class ReleaseError(ValueError):
    """A failed gate must leave a draft, never a partial public release."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReleaseError(message)


def digest(file: Path) -> str:
    with file.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load(file: Path) -> dict:
    require(file.is_file() and not file.is_symlink(), f'缺少普通证据文件: {file.name}')
    require(file.stat().st_size <= 1024 * 1024, '证据JSON超出体积限制')
    data = json.loads(file.read_text(encoding='utf-8-sig'))
    require(isinstance(data, dict), '证据必须是JSON对象')
    return data


def prepare_assets(root: Path, source: str, version: str) -> list[dict]:
    require(bool(SHA.fullmatch(source)) and bool(VERSION.fullmatch(version)), '源码SHA或版本无效')
    provenance = load(root / '发布来源v7.json')
    smoke = load(root / '安装冒烟结果v7.json')
    payload = load(root / '安装载荷核验v7.json')
    require(all(doc.get('source_sha') == source for doc in (provenance, smoke, payload)), '证据源码SHA不一致')
    require(provenance.get('version') == smoke.get('version') == version, '安装版本与发布版本不一致')
    require(provenance.get('passed') is True and payload.get('passed') is True, '来源或载荷校验未通过')
    require(smoke.get('platform') == 'windows-x64', '安装平台不匹配')
    require(all(smoke.get(key) is True for key in (
        'silent_install', 'native_window_created', 'sustained_process', 'exact_nsis_payload_verified'
    )), '安装或窗口启动证据未通过')
    installed = smoke.get('installed_binary_sha256', '')
    require(bool(DIGEST.fullmatch(installed)), '安装载荷摘要缺失')
    require(installed == payload.get('installed_sha256') == payload.get('expected_installed_sha256'), '安装载荷摘要不一致')
    items = provenance.get('artifacts')
    require(isinstance(items, list) and len(items) == 1, '必须恰好包含一个安装包')
    item = items[0]
    expected_name = f'科研工具MCP_{version}_x64-setup.exe'
    require(item.get('name') == expected_name, '安装包名称不匹配或包含越界路径')
    binary = root / expected_name
    require(binary.is_file() and not binary.is_symlink(), '安装包不存在或不是普通文件')
    require(binary.stat().st_size == item.get('bytes') and binary.stat().st_size > 0, '安装包大小不一致')
    require(digest(binary) == item.get('sha256'), '安装包摘要不一致')
    # Preserve all original Chinese evidence names inside one ZIP; otherwise
    # GitHub may normalize distinct names into the same v7.json asset name.
    evidence = root / '发布验证证据v8.zip'
    entries = [root / name for name in ('发布来源v7.json', '安装冒烟结果v7.json', '安装载荷核验v7.json', '本地验收说明v7.md')]
    require(all(p.is_file() and not p.is_symlink() for p in entries), '发布说明或证据缺失')
    with zipfile.ZipFile(evidence, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for file in entries:
            info = zipfile.ZipInfo(file.name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, file.read_bytes())
    def asset(path: Path, name: str, mime: str) -> dict:
        return {'path': path, 'name': name, 'label': path.name, 'size': path.stat().st_size,
                'digest': 'sha256:' + digest(path), 'content_type': mime}
    assets = [asset(binary, f'MCP_{version}_x64-setup.exe', 'application/vnd.microsoft.portable-executable'),
              asset(evidence, 'release-evidence_v8.zip', 'application/zip')]
    sums = root / '安装包校验和v8.txt'
    sums.write_text(''.join(a['digest'][7:] + '  ' + a['name'] + '\n' for a in assets), encoding='utf-8')
    assets.append(asset(sums, 'SHA256SUMS_v8.txt', 'text/plain; charset=utf-8'))
    return assets


def verify_assets(expected: list[dict], actual: list[dict], complete: bool) -> set[str]:
    names = [a['name'] for a in expected]
    require(len(set(names)) == len(names), '预期附件重名')
    require(all(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]+', n) for n in names), '传输附件名必须为安全ASCII')
    available = {}
    for asset in actual:
        name = asset.get('name')
        require(name in names and name not in available, '远端附件包含未知文件或规范化重名')
        available[name] = asset
    for want in expected:
        got = available.get(want['name'])
        if got is not None:
            require(got.get('state') == 'uploaded' and got.get('size') == want['size']
                    and got.get('digest') == want['digest'], '远端同名附件内容不同，拒绝覆盖')
    if complete:
        require(set(available) == set(names), '远端附件不完整')
    return set(available)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ReleaseError('拒绝携带认证信息重定向')


class GitHub:
    def __init__(self, token: str):
        require(bool(token), '缺少GitHub发布凭据')
        self.headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json',
                        'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'coding-tools-release-v8'}
        self.opener = urllib.request.build_opener(NoRedirect())

    def request(self, method: str, path: str, data=None, allow_missing=False, upload=None):
        require(path.startswith('/'), '无效API路径')
        headers = dict(self.headers)
        url = API + path
        body = None
        if upload is not None:
            url = UPLOAD + path
            headers['Content-Type'] = upload['content_type']
            body = upload['path'].read_bytes()
            require('sha256:' + hashlib.sha256(body).hexdigest() == upload['digest'], '上传前文件发生变化')
        elif data is not None:
            headers['Content-Type'] = 'application/json'
            body = json.dumps(data).encode('utf-8')
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=120) as response:
                raw = response.read(8 * 1024 * 1024)
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as error:
            if error.code == 404 and allow_missing and method == 'GET':
                return None
            # Never print headers, credentials, or signed redirect URLs.
            raise ReleaseError(f'GitHub {method} 请求失败: HTTP {error.code}') from None


def publish(api, assets: list[dict], source: str, version: str, notes: str) -> dict:
    tag = 'v' + version
    ref = api.request('GET', '/git/ref/tags/' + tag, allow_missing=True)
    if ref is not None:
        require(ref.get('object', {}).get('type') == 'commit'
                and ref['object'].get('sha') == source, '已有标签指向其他源码，拒绝覆盖')
    # Include drafts and paginate, without assuming the newest release is ours.
    matches = []
    for page in range(1, 101):
        rows = api.request('GET', f'/releases?per_page=100&page={page}')
        matches.extend(row for row in rows if row.get('tag_name') == tag)
        if len(rows) < 100:
            break
    else:
        raise ReleaseError('Release列表超限，拒绝未确认的创建')
    require(len(matches) <= 1, '存在多个同标签Release')
    if matches:
        release = matches[0]
        require(release.get('target_commitish') == source and release.get('prerelease') is True,
                '已有Release来源或类型不匹配')
    else:
        release = api.request('POST', '/releases', {
            'tag_name': tag, 'target_commitish': source, 'name': tag + ' — 固定公网入口本地验收版',
            'body': notes, 'draft': True, 'prerelease': True, 'make_latest': 'false'})
    rid = release['id']
    def remote_assets():
        # Only three assets are allowed; a full page is itself an invalid state.
        return api.request('GET', f'/releases/{rid}/assets?per_page=100')
    present = verify_assets(assets, remote_assets(), complete=not release['draft'])
    if release['draft']:
        for asset in assets:
            if asset['name'] not in present:
                query = urllib.parse.urlencode({'name': asset['name'], 'label': asset['label']})
                uploaded = api.request('POST', f'/releases/{rid}/assets?{query}', upload=asset)
                verify_assets([asset], [uploaded], complete=True)
        verify_assets(assets, remote_assets(), complete=True)
        # Race check before the public transition. Never move an existing ref.
        ref = api.request('GET', '/git/ref/tags/' + tag, allow_missing=True)
        require(ref is None or (ref.get('object', {}).get('type') == 'commit' and ref['object']['sha'] == source),
                '发布期间标签发生并发变化')
        release = api.request('PATCH', f'/releases/{rid}', {
            'draft': False, 'prerelease': True, 'make_latest': 'false', 'body': notes})
    require(release.get('draft') is False and release.get('prerelease') is True, 'Release未发布为验收版')
    ref = api.request('GET', '/git/ref/tags/' + tag)
    require(ref['object']['type'] == 'commit' and ref['object']['sha'] == source, '最终标签源码不一致')
    verify_assets(assets, remote_assets(), complete=True)
    return {'passed': True, 'tag': tag, 'source_sha': source, 'release_id': rid,
            'url': release['html_url'], 'prerelease': True,
            'assets': [{k: v for k, v in a.items() if k != 'path'} for a in assets]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    try:
        assets = prepare_assets(args.root, args.source, args.version)
        if not args.publish:
            print(json.dumps({'verified': True, 'published': False, 'assets': [a['name'] for a in assets]}))
            return 0
        notes = (args.root / '本地验收说明v7.md').read_text(encoding='utf-8')
        result = publish(GitHub(os.environ.get('GH_TOKEN', '')), assets, args.source, args.version, notes)
        (args.root / '发布完成记录v8.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError, urllib.error.URLError) as error:
        # HTTPError is sanitized inside the client; no request credentials printed.
        print(json.dumps({'passed': False, 'error': str(error)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
