"""Route source-only validation without changing stable publication rules."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import rc_version_gate as rc
import 发布版本校验v4 as stable


def classify(version: str) -> str:
    if isinstance(version, str) and stable.VERSION.fullmatch(version):
        return 'stable'
    if isinstance(version, str) and rc.RC_VERSION.fullmatch(version):
        return 'release-candidate'
    raise ValueError('source version must be strict stable or numbered release candidate')


def verify(root: Path, source: str, *, deadline=None, check_active=None) -> dict:
    version = rc.load(root, 'package.json').get('version')
    kind = classify(version)
    budget = {} if deadline is None and check_active is None else dict(deadline=deadline, check_active=check_active)
    rc.require(not budget or kind == 'release-candidate', 'controlled stable source is unsupported')
    result = (stable.verify_source(root, expected_sha=source) if kind == 'stable'
              else rc.verify_source(root, expected_sha=source, expected_version=version, **budget))
    return {**result, 'source_classification': kind, 'publish_approved': False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--expect-sha', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    value = verify(args.root.resolve(), args.expect_sha)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(value, ensure_ascii=False))


if __name__ == '__main__':
    main()
