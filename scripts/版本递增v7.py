"""仅递增本项目六处版本；默认只检查，--apply 才写入，不提交、不发布。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import tempfile
from 发布版本校验v4 import PACKAGE, VERSION, project_versions

FILES = ('package.json', 'package-lock.json', 'src-tauri/Cargo.toml',
         'src-tauri/Cargo.lock', 'src-tauri/tauri.conf.json')


def plan(root: Path, previous: str, version: str) -> dict[str, bytes]:
    if not VERSION.fullmatch(previous) or not VERSION.fullmatch(version):
        raise ValueError('版本必须是 major.minor.patch')
    if tuple(map(int, version.split('.'))) <= tuple(map(int, previous.split('.'))):
        raise ValueError('新版本必须严格大于旧版本')
    actual, _ = project_versions(root)
    if actual == version:
        return {}
    if actual != previous:
        raise ValueError('当前版本不是预期基线，拒绝覆盖')
    originals = {name: (root / name).read_bytes() for name in FILES}
    updates = {}
    for name, raw in originals.items():
        text = raw.decode('utf-8')
        if name.endswith('.json'):
            data = json.loads(text)
            data['version'] = version
            if name == 'package-lock.json':
                data['packages']['']['version'] = version
            text = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
        else:
            prefix = (r'(^\[\[package\]\]\s*\nname = "' + re.escape(PACKAGE) + r'"\s*\nversion = ")'
                      if name.endswith('.lock') else r'(^\[package\]\r?\n(?:(?!^\[).)*?^version = ")')
            pattern = prefix + re.escape(previous) + r'(")'
            text, count = re.subn(pattern, lambda m: m[1] + version + m[2], text, flags=re.M | re.S)
            if count != 1:
                raise ValueError('项目版本字段不是唯一匹配: ' + name)
        updates[name] = text.encode('utf-8')
    # Re-parse all proposed files before touching the real checkout.
    with tempfile.TemporaryDirectory(prefix='version-review-') as folder:
        target = Path(folder)
        for name, raw in updates.items():
            (target / name).parent.mkdir(parents=True, exist_ok=True)
            (target / name).write_bytes(raw)
        if project_versions(target)[0] != version:
            raise ValueError('候选六处版本不一致')
    return updates


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--from-version', required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        updates = plan(args.root, args.from_version, args.version)
        if args.apply:
            for name, raw in updates.items():
                (args.root / name).write_bytes(raw)
        print(json.dumps({'version': args.version, 'changed_files': list(updates),
                          'applied': args.apply, 'already_current': not updates}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({'passed': False, 'error': str(error)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
