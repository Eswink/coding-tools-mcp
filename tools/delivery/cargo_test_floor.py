"""Fail-closed check of captured `cargo test` output without pinning exact counts.

Exact `N passed` greps broke whenever a suite legitimately grew (and differ per
OS because of cfg-gated tests). This keeps what they guarded:
  * at least one libtest summary was produced (the selected tests really ran);
  * every summary is `ok` with 0 failed and 0 ignored;
  * the passed total is at least the reviewed floor, so a filter that silently
    selects nothing, or a suite that loses tests, still fails.
`cargo test` failures already fail the step through `set -o pipefail`.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SUMMARY = re.compile(
    r'test result: (?P<status>ok|FAILED)\. (?P<passed>\d+) passed; '
    r'(?P<failed>\d+) failed; (?P<ignored>\d+) ignored;'
)


def check(text: str, minimum: int) -> tuple[bool, str]:
    rows = [m.groupdict() for m in SUMMARY.finditer(text)]
    if not rows:
        return False, 'no libtest summary found'
    passed = sum(int(r['passed']) for r in rows)
    bad = [r for r in rows if r['status'] != 'ok' or r['failed'] != '0' or r['ignored'] != '0']
    if bad:
        return False, f'non-clean summaries: {bad}'
    if passed < minimum:
        return False, f'{passed} passed < reviewed floor {minimum}'
    return True, f'{passed} passed >= floor {minimum}; {len(rows)} summaries; 0 failed; 0 ignored'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('log', type=Path)
    parser.add_argument('--min', type=int, required=True, dest='minimum')
    args = parser.parse_args(argv)
    if args.minimum < 1:
        parser.error('--min must be >= 1')
    ok, detail = check(args.log.read_text(encoding='utf-8', errors='replace'), args.minimum)
    print(f'{args.log}: {detail}')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
