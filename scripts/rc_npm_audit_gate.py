"""Decide the RC frontend npm audit gate from raw `npm audit --json` reports.

Production dependencies (`npm audit --omit=dev --json`) have zero tolerance.
The full report must be zero, except for one exact, time-boxed, dev-only
exemption: deepmerge GHSA-gcqx-w48m-w2h4 (no patched release exists) and the
three direct dev packages whose `via` chain resolves only to that advisory.
Any other advisory, package, severity or count fails, and the exemption is
void after EXEMPTION_EXPIRES.

The packaging gate judges expiry by the current UTC date and writes a capture
record (CAPTURE_NAME, next to the full report) holding the capture time, the
full report digest and exit code, and the production report and exit code.
Evidence verifiers call check_recorded(), which judges expiry by that recorded
capture time and never reads the clock. A recorded zero report needs no capture
record, so historical rc.1/rc.2 zero evidence keeps its verdict.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
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
CAPTURE_NAME = 'npm-audit-capture.json'
CAPTURE_SCHEMA = 'rc-npm-audit-capture-v1'
CAPTURE_KEYS = frozenset({'schema', 'captured_at', 'full_report', 'full_sha256', 'full_exit_code',
                          'prod_report', 'prod_exit_code'})


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


def check_findings(report: object, on_date: date) -> dict:
    """Judge a non-zero full report against the exact exemption as of on_date."""
    value = counts(report)
    require(value['total'] > 0, 'npm audit findings expected')
    require(type(on_date) is date, 'npm audit exemption date required')
    require(on_date <= EXEMPTION_EXPIRES, f'npm audit exemption {EXEMPT_ADVISORY} expired after {EXEMPTION_EXPIRES}')
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


def check_full(report: object, exit_code: int, today: date) -> dict:
    value = counts(report)
    if value['total'] == 0:
        require(exit_code == 0, f'npm audit exit code {exit_code} with zero findings')
        return dict(total=0, exempted=[])
    require(exit_code == 1, f'unexpected npm audit exit code {exit_code}')
    return check_findings(report, today)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: object) -> datetime:
    require(type(value) is str and len(value) == 20 and value.endswith('Z'), 'invalid npm audit capture time')
    try:
        parsed = datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
    except ValueError as error:
        raise GateError('invalid npm audit capture time') from error
    return parsed


def capture_record(full_bytes: bytes, full_exit_code: int, prod_report: object, prod_exit_code: int,
                   captured_at: datetime) -> dict:
    require(type(captured_at) is datetime and captured_at.utcoffset() is not None, 'aware capture time required')
    stamp = captured_at.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    return dict(schema=CAPTURE_SCHEMA, captured_at=stamp, full_report='npm-audit.json',
                full_sha256=hashlib.sha256(full_bytes).hexdigest(), full_exit_code=full_exit_code,
                prod_report=prod_report, prod_exit_code=prod_exit_code)


def _recorded_zero(report: object) -> bool:
    if type(report) is not dict or 'error' in report or type(report.get('metadata')) is not dict:
        return False
    value = report['metadata'].get('vulnerabilities')
    return (type(value) is dict and 'total' in value and set(value) <= set(SEVERITIES) | {'total'}
            and all(type(v) is int and v == 0 for v in value.values()))


def check_recorded(report: object, report_bytes: bytes, capture: object) -> dict:
    """Verify recorded evidence; expiry is judged by the recorded capture time, never the clock.

    capture is the parsed CAPTURE_NAME record, or None when the evidence has none. Without a
    record only an all-zero report passes (the historical rc.1/rc.2 rule, unchanged)."""
    if capture is None:
        require(_recorded_zero(report), 'npm audit missing or vulnerable')
        return dict(total=0, exempted=[], captured_at=None)
    require(type(capture) is dict and set(capture) == CAPTURE_KEYS and capture.get('schema') == CAPTURE_SCHEMA
            and capture.get('full_report') == 'npm-audit.json', 'npm audit capture record invalid')
    require(type(report_bytes) is bytes and capture['full_sha256'] == hashlib.sha256(report_bytes).hexdigest(),
            'npm audit capture record does not bind the recorded report')
    require(type(capture['full_exit_code']) is int and type(capture['prod_exit_code']) is int,
            'npm audit capture exit codes invalid')
    captured = _timestamp(capture['captured_at'])
    check_prod(capture['prod_report'], capture['prod_exit_code'])
    result = check_full(report, capture['full_exit_code'], captured.date())
    return dict(result, captured_at=capture['captured_at'])


def read_bytes(path: Path) -> bytes:
    require(path.is_file() and not path.is_symlink(), f'missing npm audit report: {path}')
    require(path.stat().st_size <= MAX_REPORT_BYTES, f'npm audit report too large: {path}')
    return path.read_bytes()


def read(path: Path) -> object:
    return json.loads(read_bytes(path).decode('utf-8'))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--full', type=Path, required=True)
    parser.add_argument('--full-exit-code', type=int, required=True)
    parser.add_argument('--prod', type=Path, required=True)
    parser.add_argument('--prod-exit-code', type=int, required=True)
    args = parser.parse_args(argv)
    now = utc_now()
    today = now.date()
    try:
        prod = read(args.prod)
        full_bytes = read_bytes(args.full)
        full = json.loads(full_bytes.decode('utf-8'))
        result = dict(prod=check_prod(prod, args.prod_exit_code),
                      full=check_full(full, args.full_exit_code, today),
                      date=today.isoformat(), passed=True)
        record = capture_record(full_bytes, args.full_exit_code, prod, args.prod_exit_code, now)
        capture = args.full.with_name(CAPTURE_NAME)
        require(not capture.exists(), f'npm audit capture record already exists: {capture}')
        capture.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        result['captured_at'] = record['captured_at']
    except (GateError, ValueError) as error:
        print(json.dumps(dict(passed=False, error=str(error))), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
