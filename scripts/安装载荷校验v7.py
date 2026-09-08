"""逐字节核对已安装NSIS程序，仅允许锁定Tauri定义的唯一包类型标记替换。"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

ORIGINAL = b'__TAURI_BUNDLE_TYPE_VAR_UNK'
NSIS = b'__TAURI_BUNDLE_TYPE_VAR_NSS'
MAX_BYTES = 128 * 1024 * 1024
CLI_VERSION = '2.11.4'
UPSTREAM = 'https://github.com/tauri-apps/tauri/blob/tauri-cli-v2.11.4/crates/tauri-bundler/src/bundle.rs'


def expected_payload(original: bytes) -> tuple[bytes, int]:
    if not original.startswith(b'MZ') or len(original) > MAX_BYTES:
        raise ValueError('构建程序格式或体积异常')
    if original.count(ORIGINAL) != 1:
        raise ValueError('构建程序必须包含且仅包含一个Tauri原始包类型标记')
    offset = original.index(ORIGINAL)
    return original[:offset] + NSIS + original[offset + len(ORIGINAL):], offset


def bounded_read(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError('载荷文件不是受支持的常规文件')
    with path.open('rb') as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError('载荷文件读取超过上限')
    return data


def inspect(built: Path, installed_dir: Path, lockfile: Path) -> dict:
    lock = json.loads(lockfile.read_text(encoding='utf-8'))
    if lock['packages']['node_modules/@tauri-apps/cli']['version'] != CLI_VERSION:
        raise ValueError('CLI版本变更，必须重新审查对应的打包变换')
    original = bounded_read(built)
    expected, offset = expected_payload(original)
    report = {'passed': False, 'source_sha': os.environ.get('SOURCE_SHA'),
              'cli_version': CLI_VERSION, 'upstream_contract': UPSTREAM,
              'marker_offset': offset, 'allowed_change': 'single UNK -> NSS bundle-type marker',
              'unbundled_sha256': hashlib.sha256(original).hexdigest(),
              'expected_installed_sha256': hashlib.sha256(expected).hexdigest(), 'observed': []}
    root = installed_dir.resolve(strict=True)
    candidates = sorted(root.rglob('*.exe'))
    if len(candidates) > 64:
        raise ValueError('安装目录包含异常数量的可执行文件')
    matches = []
    for path in candidates:
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('安装目录存在外部重定向')
        data = bounded_read(path)
        report['observed'].append({'path': path.relative_to(root).as_posix(),
                                   'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
        # Exact bytes, not approximate similarity, PE metadata, or version alone.
        if data == expected:
            matches.append(path)
    if len(matches) == 1:
        report.update(passed=True, installed_path=str(matches[0]),
                      installed_sha256=hashlib.sha256(expected).hexdigest())
    else:
        report['error'] = '已安装程序与精确NSIS预期载荷不符或不唯一'
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--built', type=Path, required=True)
    parser.add_argument('--installed-dir', type=Path, required=True)
    parser.add_argument('--lockfile', type=Path, default=Path('package-lock.json'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = inspect(args.built, args.installed_dir, args.lockfile)
    except (OSError, ValueError, KeyError, TypeError) as error:
        result = {'passed': False, 'error': str(error), 'source_sha': os.environ.get('SOURCE_SHA')}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
