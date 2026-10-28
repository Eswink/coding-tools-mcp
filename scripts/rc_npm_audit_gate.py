"""Decide the RC frontend npm audit gate from raw `npm audit --json` reports.

Production dependencies (`npm audit --omit=dev --json`) have zero tolerance.
The full report must be zero, except for one exact, time-boxed, dev-only
exemption: deepmerge GHSA-gcqx-w48m-w2h4 (no patched release exists) and the
three direct dev packages whose `via` chain resolves only to that advisory.
Any other advisory, package, severity or count fails, and the exemption is
void after EXEMPTION_EXPIRES.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys

SEVERITIES = ('info', 'low', 'moderate', 'high', 'critical')
EXEMPT_ADVISORY = 'https://github.com/advisories/GHSA-gcqx-w48m-w2h4'
EXEMPT_PACKAGE = 'deepmerge'
EXEMPT_SEVERITY = 'low'
EXEMPT_CHAIN = frozenset({'@sveltejs/vite-plugin-svelte', '@sveltejs/kit', '@sveltejs/adapter-static'})
EXEMPTION_EXPIRES = date(2026, 11, 30)  # last valid day (UTC); void from 2026-12-01
MAX_REPORT_BYTES = 16 * 1024 * 1024


class GateError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise GateError(message)


def counts(report: object) -> dict:
    require(type(report) is dict and 'error' not in report, 'npm audit report missing or errored')
    require(report.get('auditReportVersion') == 2, 'unsupported npm audit report version')
    value = report.get('metadata', {}).get('vulnerabilities') if type(report.get('metadata')) is dict else None
    require(type(value) is dict and set(value) == set(SEVERITIES) | {'total'}, 'invalid npm audit counts')
    require(all(type(v) is int and v >= 0 for v in value.values()), 'invalid npm audit counts')
    require(sum(value[s] for s in SEVERITIES) == value['total'], 'inconsistent npm audit counts')
    require(type(report.get('vulnerabilities')) is dict and len(report['vulnerabilities']) == value['total'],
            'npm audit vulnerability entries do not match counts')
    return value


def check_prod(report: object, exit_code: int) -> dict:
    value = counts(report)
    require(value['total'] == 0 and exit_code == 0, f'production npm audit is not zero: {value}')
    return dict(total=0)


def _advisory(entry: object) -> bool:
    return (type(entry) is dict and entry.get('url') == EXEMPT_ADVISORY
            and entry.get('name') == EXEMPT_PACKAGE and entry.get('dependency') == EXEMPT_PACKAGE
            and entry.get('severity') == EXEMPT_SEVERITY)


def check_full(report: object, exit_code: int, today: date) -> dict:
    value = counts(report)
    if value['total'] == 0:
        require(exit_code == 0, f'npm audit exit code {exit_code} with zero findings')
        return dict(total=0, exempted=[])
    require(today <= EXEMPTION_EXPIRES, f'npm audit exemption {EXEMPT_ADVISORY} expired after {EXEMPTION_EXPIRES}')
    require(exit_code == 1, f'unexpected npm audit exit code {exit_code}')
    allowed = EXEMPT_CHAIN | {EXEMPT_PACKAGE}
    found = report['vulnerabilities']
    require(set(found) == allowed, f'npm audit packages outside the exemption: {sorted(set(found) ^ allowed)}')
    require(value == dict(info=0, low=len(allowed), moderate=0, high=0, critical=0, total=len(allowed)),
            f'npm audit counts outside the exemption: {value}')
    for name, entry in found.items():
        require(type(entry) is dict and entry.get('name') == name, f'malformed npm audit entry: {name}')
        require(entry.get('severity') == EXEMPT_SEVERITY, f'npm audit severity outside the exemption: {name}')
        via = entry.get('via')
        require(type(via) is list and via, f'npm audit entry without via: {name}')
        if name == EXEMPT_PACKAGE:
            require(all(_advisory(item) for item in via), f'npm audit advisory outside the exemption: {name}')
        else:
            require(all(type(item) is str and item in allowed and item != name for item in via),
                    f'npm audit via chain outside the exemption: {name}')
    for name in EXEMPT_CHAIN:  # every chain entry must resolve, acyclically, to the advisory package
        seen, frontier = set(), {name}
        while frontier:
            current = frontier.pop()
            require(current not in seen, f'npm audit via cycle: {name}')
            seen.add(current)
            if current != EXEMPT_PACKAGE:
                frontier |= set(found[current]['via'])
        require(EXEMPT_PACKAGE in seen, f'npm audit via chain does not reach {EXEMPT_PACKAGE}: {name}')
    return dict(total=value['total'], exempted=sorted(found), advisory=EXEMPT_ADVISORY,
                expires=EXEMPTION_EXPIRES.isoformat())


def read(path: Path) -> object:
    require(path.is_file() and not path.is_symlink(), f'missing npm audit report: {path}')
    require(path.stat().st_size <= MAX_REPORT_BYTES, f'npm audit report too large: {path}')
    return json.loads(path.read_bytes().decode('utf-8'))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--full', type=Path, required=True)
    parser.add_argument('--full-exit-code', type=int, required=True)
    parser.add_argument('--prod', type=Path, required=True)
    parser.add_argument('--prod-exit-code', type=int, required=True)
    args = parser.parse_args(argv)
    today = datetime.now(timezone.utc).date()
    try:
        result = dict(prod=check_prod(read(args.prod), args.prod_exit_code),
                      full=check_full(read(args.full), args.full_exit_code, today),
                      date=today.isoformat(), passed=True)
    except (GateError, ValueError) as error:
        print(json.dumps(dict(passed=False, error=str(error))), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
