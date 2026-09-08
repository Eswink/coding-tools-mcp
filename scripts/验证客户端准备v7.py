"""下载指定官方FRPC发行版并核对发行方SHA256；只为无公网连接的配置测试准备客户端。"""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import urllib.request
import zipfile

ROOT = 'https://github.com/fatedier/frp/releases/download/v0.61.2/'
ASSET = 'frp_0.61.2_windows_amd64.zip'


def fetch(name: str, limit: int) -> bytes:
    with urllib.request.urlopen(ROOT + name, timeout=90) as response:
        if not response.url.startswith('https://'):
            raise ValueError('拒绝非HTTPS下载')
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('下载超过体积上限')
    return data


def main() -> None:
    checksums = fetch('frp_sha256_checksums.txt', 65536).decode('utf-8')
    matching = [line.split()[0] for line in checksums.splitlines()
                if len(line.split()) == 2 and line.split()[1].lstrip('*') == ASSET]
    if len(matching) != 1 or not re.fullmatch(r'[0-9a-f]{64}', matching[0]):
        raise ValueError('发行方摘要必须唯一且合法')
    raw = fetch(ASSET, 32 * 1024 * 1024)
    if hashlib.sha256(raw).hexdigest() != matching[0]:
        raise ValueError('FRPC发行包摘要不符')
    target = Path(os.environ['RUNNER_TEMP']) / '验证客户端v7'
    target.mkdir(exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        member = archive.getinfo('frp_0.61.2_windows_amd64/frpc.exe')
        if member.file_size > 64 * 1024 * 1024:
            raise ValueError('FRPC文件过大')
        binary = archive.read(member)
    if not binary.startswith(b'MZ'):
        raise ValueError('FRPC不是PE文件')
    path = target / 'frpc.exe'
    path.write_bytes(binary)
    with Path(os.environ['GITHUB_ENV']).open('a', encoding='utf-8') as output:
        output.write('FRPC_TEST_BINARY=' + str(path) + '\n')
    report = {'upstream': ROOT + ASSET, 'archive_sha256': matching[0],
              'binary_sha256': hashlib.sha256(binary).hexdigest(), 'version': '0.61.2'}
    (target / '客户端来源v7.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
