"""Exact test-source inventory for the v23 Windows standard-user acceptance.

v22 copied every non-recursive ``scripts/*.py`` plus ``package.json`` and only
required ``1 <= len(inventory) <= 300``. That numeric cap had zero margin at
0.7.0 (299 + package.json). v23 replaces the cap with an exact, checked-in
manifest: the sorted relative names, their count and the SHA-256 of the
canonical name list. Any extra, missing or renamed file fails closed.

Content integrity is still enforced per run: the controller hashes every copied
file and the standard-user child re-verifies those hashes before and after the
native acceptance (same as v22). The manifest pins *membership*, not bytes, so a
script edit does not need a manifest re-pin while an added/removed file does.

Pure stdlib, no Windows APIs: importable and testable on Linux.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

SCHEMA = 'coding-tools-windows-standard-source-manifest-v23'
MANIFEST_NAME = '标准用户源清单v23.json'
SUBDIR = 'windows_standard_v23'
PACKAGE = 'package.json'
# Only these suffixes are collected from the v23 subdirectory itself.
SUBDIR_SUFFIXES = ('.py', '.json')
MAX_ENTRIES = 4096


def names_digest(names: list[str]) -> str:
    return hashlib.sha256(('\n'.join(names) + '\n').encode('utf-8')).hexdigest()


def _regular(path: Path) -> Path:
    if path.is_symlink() or not path.is_file():
        raise ValueError('test source must be a regular, non-symlink file: ' + path.name)
    return path


def collect(scripts: Path) -> dict[str, Path]:
    """Return {relative name: absolute path} for the exact copy set.

    Membership rule (deterministic, mirrors v22 plus the v23 subdirectory):
      * every regular ``scripts/*.py`` (non-recursive, as v22);
      * every regular ``scripts/windows_standard_v23/*.py|*.json`` (non-recursive);
      * the repository ``package.json``.
    Directories such as ``__pycache__`` are never collected.
    """
    scripts = scripts.resolve()
    found: dict[str, Path] = {}
    for path in scripts.glob('*.py'):
        found['scripts/' + path.name] = _regular(path)
    sub = scripts / SUBDIR
    if sub.is_symlink() or not sub.is_dir():
        raise ValueError('v23 subdirectory missing or not a real directory')
    for path in sub.iterdir():
        if path.is_dir() and not path.is_symlink():
            continue
        if path.suffix in SUBDIR_SUFFIXES:
            found[f'scripts/{SUBDIR}/{path.name}'] = _regular(path)
    found[PACKAGE] = _regular(scripts.parent / PACKAGE)
    return dict(sorted(found.items()))


def build(names) -> dict:
    names = sorted(names)
    return {'schema': SCHEMA, 'count': len(names), 'names_sha256': names_digest(names), 'entries': names}


def load(path: Path) -> dict:
    data = json.loads(_regular(path).read_text(encoding='utf-8'))
    validate(data)
    return data


def validate(data) -> None:
    if not isinstance(data, dict) or set(data) != {'schema', 'count', 'names_sha256', 'entries'}:
        raise ValueError('invalid v23 source manifest shape')
    entries = data['entries']
    if (data['schema'] != SCHEMA or not isinstance(entries, list) or not entries
            or len(entries) > MAX_ENTRIES or not all(isinstance(n, str) and n for n in entries)):
        raise ValueError('invalid v23 source manifest entries')
    if entries != sorted(entries) or len(set(entries)) != len(entries):
        raise ValueError('v23 source manifest must be sorted and unique')
    for name in entries:
        parts = name.split('/')
        if name != PACKAGE and not (
                (len(parts) == 2 and parts[0] == 'scripts' and parts[1].endswith('.py'))
                or (len(parts) == 3 and parts[:2] == ['scripts', SUBDIR] and parts[2].endswith(SUBDIR_SUFFIXES))):
            raise ValueError('v23 source manifest entry outside the allowed layout: ' + name)
        if any(p in ('', '.', '..') or '\\' in p or ':' in p for p in parts):
            raise ValueError('v23 source manifest entry is not a plain relative name')
    if PACKAGE not in entries or f'scripts/{SUBDIR}/{MANIFEST_NAME}' not in entries:
        raise ValueError('v23 source manifest must list package.json and itself')
    if type(data['count']) is not int or data['count'] != len(entries):
        raise ValueError('v23 source manifest count mismatch')
    if data['names_sha256'] != names_digest(entries):
        raise ValueError('v23 source manifest digest mismatch')


def compare(manifest: dict, actual) -> dict:
    expected, actual = set(manifest['entries']), set(actual)
    return {'extra': sorted(actual - expected), 'missing': sorted(expected - actual)}


def require_exact(manifest: dict, actual) -> None:
    diff = compare(manifest, actual)
    if diff['extra'] or diff['missing']:
        raise ValueError('test-source inventory differs from the v23 manifest: '
            f"extra={diff['extra'][:5]} missing={diff['missing'][:5]} "
            f"(+{len(diff['extra'])}/-{len(diff['missing'])})")


def git_names(root: Path) -> list[str]:
    """Tracked membership as git sees it (core.quotepath=off keeps CJK names readable)."""
    raw = subprocess.check_output(['git', '-c', 'core.quotepath=off', 'ls-files', '-z', '--', 'scripts', PACKAGE], cwd=root)
    names = []
    for name in raw.decode('utf-8').split('\0'):
        parts = name.split('/')
        if name == PACKAGE or (len(parts) == 2 and parts[0] == 'scripts' and parts[1].endswith('.py')) or (
                len(parts) == 3 and parts[:2] == ['scripts', SUBDIR] and parts[2].endswith(SUBDIR_SUFFIXES)):
            names.append(name)
    return sorted(names)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('command', choices=('check', 'write', 'git-check'))
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args(argv)
    scripts = args.root.resolve() / 'scripts'
    path = scripts / SUBDIR / MANIFEST_NAME
    if args.command == 'write':
        names = list(collect(scripts))
        if f'scripts/{SUBDIR}/{MANIFEST_NAME}' not in names:
            names.append(f'scripts/{SUBDIR}/{MANIFEST_NAME}')
        data = build(names)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        print(json.dumps({'written': str(path.relative_to(args.root.resolve())), 'count': data['count'],
                          'names_sha256': data['names_sha256']}, ensure_ascii=False))
        return 0
    manifest = load(path)
    actual = git_names(args.root.resolve()) if args.command == 'git-check' else list(collect(scripts))
    diff = compare(manifest, actual)
    top = sum(1 for n in manifest['entries'] if n.count('/') == 1 and n.startswith('scripts/'))
    ok = not diff['extra'] and not diff['missing']
    print(json.dumps({'mode': args.command, 'passed': ok, 'count': manifest['count'], 'top_level_py': top,
                      'names_sha256': manifest['names_sha256'], **diff}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
