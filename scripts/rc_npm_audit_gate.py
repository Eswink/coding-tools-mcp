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

C13c: live gate runs always verify the vendored deepmerge mitigation first
(verify_vendored_mitigation, pinned hashes below). When it holds, the full report
must be zero (npm 11 skips file: links) or exactly the four GHSA-gcqx lows (npm 10
still reports them); both judge identically and expire only at MITIGATION_REVIEW_BY.
Such runs write capture v2. C13d: a v1 capture record now only verifies an all-zero
full report (total>0 under v1 is refused, closing the back-dated unpinned path); the
no-capture all-zero rule is unchanged and the v1 schema itself is kept.

C41: the two dates are separate. EXEMPTION_EXPIRES (2026-11-30) only bounds the v1 judge
(check_findings, no vendored mitigation). The live gate (--verify-only, --no-capture, and the
capture-v2 packaging run) goes through verify_vendored_mitigation/check_mitigated and is bounded
only by MITIGATION_REVIEW_BY (2027-02-28), so 2026-12-01 does not stop CI.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

SEVERITIES = ('info', 'low', 'moderate', 'high', 'critical')
EXEMPT_ADVISORY = 'https://github.com/advisories/GHSA-gcqx-w48m-w2h4'
EXEMPT_PACKAGE = 'deepmerge'
EXEMPT_SEVERITY = 'low'
EXEMPT_CHAIN = frozenset({'@sveltejs/vite-plugin-svelte', '@sveltejs/kit', '@sveltejs/adapter-static'})
# v1 judge only (check_findings); the live mitigated gate uses MITIGATION_REVIEW_BY below.
EXEMPTION_EXPIRES = date(2026, 11, 30)  # last valid day (UTC); void from 2026-12-01
MAX_REPORT_BYTES = 16 * 1024 * 1024
CAPTURE_NAME = 'npm-audit-capture.json'
CAPTURE_SCHEMA = 'rc-npm-audit-capture-v1'
CAPTURE_KEYS = frozenset({'schema', 'captured_at', 'full_report', 'full_sha256', 'full_exit_code',
                          'prod_report', 'prod_exit_code'})

# --- C13c vendored-deepmerge mitigation (capture v2) ---
# Pinned expected digests. Changing anything under vendor-js/deepmerge or the two lock entries
# requires changing these constants in the same reviewed diff.
VENDOR_DIR = 'vendor-js/deepmerge'
VENDOR_VERSION = '4.3.1+ctm.1'
EXEMPT_RANGE = '>=4.2.0 <=4.3.1'
EXEMPT_NODES = frozenset({'node_modules/deepmerge', VENDOR_DIR})
LOCK_KEYS = ('node_modules/deepmerge', VENDOR_DIR)
VENDOR_TREE_SHA256 = '45d3fcc3da266fc07070e1b21be854c63f170f46da3ef18557637302823eefe3'
VENDOR_CJS_SHA256 = '8f4fbffea4088b18687f80ef0e6c7ad429b1ab682ef3d48c9680ebc43255cc60'
VENDOR_PROVENANCE_SHA256 = 'fa505cac73fcbfc89abb7015bb143b00f3c4b0a166328ba9516a6900ae2c3a54'
LOCK_ENTRY_SHA256 = '06bbdc82bf517ac57b14c9c20477a619fc3a6df440eea1574c0494be80242435'
# Last valid day (UTC) for the mitigation path, judged live and by capture time. Renewing it
# REQUIRES re-checking provenance.json removal_condition: GHSA-gcqx-w48m-w2h4 withdrawn_at, and
# whether upstream shipped a fixed deepmerge accepted by @sveltejs/vite-plugin-svelte (the gate
# cannot see either offline; this date is the only backstop).
MITIGATION_REVIEW_BY = date(2027, 2, 28)
CAPTURE_SCHEMA_V2 = 'rc-npm-audit-capture-v2'
MITIGATION_KEYS = frozenset({'vendor_version', 'tree_sha256', 'cjs_sha256', 'provenance_sha256',
                             'lock_entry_sha256'})
CAPTURE_KEYS_V2 = CAPTURE_KEYS | {'mitigation', 'npm_version', 'node_version'}
PINNED_MITIGATION = dict(vendor_version=VENDOR_VERSION, tree_sha256=VENDOR_TREE_SHA256,
                         cjs_sha256=VENDOR_CJS_SHA256, provenance_sha256=VENDOR_PROVENANCE_SHA256,
                         lock_entry_sha256=LOCK_ENTRY_SHA256)
REMOVAL_HINT = 'notice: npm audit shows zero with npm<11; removal_condition may already be met (recheck GHSA withdrawn_at)'


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
            # C13d: exactly one advisory; no dedupe before the check.
            require(len(via) == 1 and _advisory(via[0]), f'npm audit advisory outside the exemption: {name}')
        else:
            require(all(type(item) is str and item in allowed and item != name for item in via),
                    f'npm audit via chain outside the exemption: {name}')
            require(entry.get('nodes') == [f'node_modules/{name}'],
                    f'npm audit chain nodes outside the exemption: {name}')
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


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode('utf-8')


def _regular(path: Path, label: str) -> bytes:
    require(not path.is_symlink() and path.is_file(), f'vendored deepmerge {label} missing or not a regular file')
    return path.read_bytes()


def _load(path: Path, label: str) -> object:
    try:
        return json.loads(_regular(path, label).decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GateError(f'vendored deepmerge {label} is not valid JSON') from error


def verify_vendored_mitigation(repo: Path) -> dict:
    """Fail-closed proof that deepmerge resolves to the pinned vendored copy. Returns the mitigation record."""
    repo = Path(repo)
    pkg = _load(repo / 'package.json', 'package.json')
    require(type(pkg) is dict, 'package.json invalid')
    dev = pkg.get('devDependencies')
    over = pkg.get('overrides')
    require(type(dev) is dict and dev.get('deepmerge') == 'file:' + VENDOR_DIR,
            'deepmerge devDependency is not the vendored file: link')
    require(type(over) is dict and over.get('deepmerge') == '$deepmerge', 'deepmerge override missing')
    for field in ('dependencies', 'optionalDependencies', 'peerDependencies', 'bundleDependencies', 'bundledDependencies'):
        value = pkg.get(field)
        require(value is None or 'deepmerge' not in value, f'deepmerge must be dev-only, found in {field}')
    lock = _load(repo / 'package-lock.json', 'package-lock.json')
    require(type(lock) is dict and lock.get('lockfileVersion') == 3 and type(lock.get('packages')) is dict,
            'package-lock.json invalid')
    packages = lock['packages']
    require(packages.get('node_modules/deepmerge') == {'resolved': VENDOR_DIR, 'link': True},
            'lock node_modules/deepmerge is not the vendored link')
    vendor_entry = packages.get(VENDOR_DIR)
    require(type(vendor_entry) is dict and vendor_entry.get('version') == VENDOR_VERSION
            and vendor_entry.get('dev') is True, 'lock vendored deepmerge entry is not dev-only 4.3.1+ctm.1')
    for key in ('optional', 'peer', 'devOptional'):
        require(key not in vendor_entry, f'lock vendored deepmerge entry carries {key}')
    for key, value in packages.items():
        if key in LOCK_KEYS:
            continue
        resolved = value.get('resolved', '') if type(value) is dict else ''
        require(not key.endswith('/deepmerge') and key != 'deepmerge'
                and not (type(value) is dict and value.get('name') == 'deepmerge')
                and not (type(resolved) is str and 'deepmerge-' in resolved),
                f'lock carries another deepmerge copy or alias: {key}')
    lock_sha = _sha256(_canonical({key: packages[key] for key in LOCK_KEYS}))
    require(lock_sha == LOCK_ENTRY_SHA256, 'lock deepmerge entries differ from the pinned digest')
    vendor = repo / VENDOR_DIR
    require(vendor.is_dir() and not vendor.is_symlink(), 'vendored deepmerge directory missing')
    tree = {}
    for path in sorted(vendor.rglob('*')):
        rel = path.relative_to(vendor).as_posix()
        if path.is_dir() and not path.is_symlink():
            continue
        tree[rel] = _sha256(_regular(path, rel))
    provenance_bytes = _regular(vendor / 'provenance.json', 'provenance.json')
    require(_sha256(provenance_bytes) == VENDOR_PROVENANCE_SHA256, 'provenance.json differs from the pinned digest')
    provenance = json.loads(provenance_bytes.decode('utf-8'))
    require(provenance.get('version') == VENDOR_VERSION and provenance.get('advisory') == 'GHSA-gcqx-w48m-w2h4',
            'provenance.json identity mismatch')
    listed = provenance.get('vendored_files')
    require(type(listed) is dict and set(tree) == set(listed) | {'provenance.json', 'PATCHES.md'},
            f'vendored deepmerge file set differs from provenance: {sorted(set(tree) ^ (set(listed or {}) | {"provenance.json", "PATCHES.md"}))}')
    for rel, digest in listed.items():
        require(tree[rel] == digest, f'vendored deepmerge file differs from provenance: {rel}')
    require(tree.get('dist/cjs.js') == VENDOR_CJS_SHA256, 'dist/cjs.js differs from the pinned digest')
    vendored_pkg = json.loads((vendor / 'package.json').read_bytes().decode('utf-8'))
    require(vendored_pkg.get('version') == VENDOR_VERSION, 'vendored deepmerge package.json version mismatch')
    tree_sha = _sha256(_canonical(tree))
    require(tree_sha == VENDOR_TREE_SHA256, 'vendored deepmerge tree differs from the pinned digest')
    installed = repo / 'node_modules' / 'deepmerge'
    if os.path.lexists(installed):
        require(installed.is_symlink() and installed.resolve() == vendor.resolve(),
                'node_modules/deepmerge is not a symlink to the vendored copy')
    return dict(vendor_version=VENDOR_VERSION, tree_sha256=tree_sha, cjs_sha256=tree['dist/cjs.js'],
                provenance_sha256=_sha256(provenance_bytes), lock_entry_sha256=lock_sha)


def check_mitigation_record(mitigation: object) -> None:
    require(type(mitigation) is dict and set(mitigation) == MITIGATION_KEYS, 'npm audit mitigation record invalid')
    require(mitigation == PINNED_MITIGATION, 'npm audit mitigation record differs from the pinned digests')


def check_mitigated(report: object, exit_code: int, on_date: date) -> dict:
    """Full report judged under a verified vendored mitigation: zero, or exactly the four GHSA-gcqx lows."""
    value = counts(report)
    require(type(on_date) is date, 'npm audit mitigation date required')
    require(on_date <= MITIGATION_REVIEW_BY,
            f'npm audit deepmerge mitigation review overdue after {MITIGATION_REVIEW_BY}; recheck removal_condition')
    if value['total'] == 0:
        require(exit_code == 0, f'npm audit exit code {exit_code} with zero findings')
        return dict(total=0, exempted=[], mitigated=True, review_by=MITIGATION_REVIEW_BY.isoformat())
    require(exit_code == 1, f'unexpected npm audit exit code {exit_code}')
    allowed = EXEMPT_CHAIN | {EXEMPT_PACKAGE}
    found = report['vulnerabilities']
    require(value == dict(info=0, low=4, moderate=0, high=0, critical=0, total=4) and set(found) == allowed,
            f'npm audit findings outside the mitigation: {value} {sorted(found)}')
    entry = found[EXEMPT_PACKAGE]
    require(type(entry) is dict and entry.get('name') == EXEMPT_PACKAGE and entry.get('severity') == EXEMPT_SEVERITY,
            'npm audit deepmerge entry outside the mitigation')
    nodes = entry.get('nodes')
    require(type(nodes) is list and set(nodes) == EXEMPT_NODES and len(nodes) == len(EXEMPT_NODES),
            f'npm audit deepmerge nodes are not the vendored link: {nodes}')
    via = entry.get('via')
    # C13d: exactly one advisory entry, judged as-is (no dedupe before the check).
    require(type(via) is list and len(via) == 1 and _advisory(via[0]) and via[0].get('range') == EXEMPT_RANGE,
            'npm audit deepmerge advisory outside the mitigation')
    for name in EXEMPT_CHAIN:
        chain = found[name]
        require(type(chain) is dict and chain.get('name') == name and chain.get('severity') == EXEMPT_SEVERITY,
                f'npm audit chain entry outside the mitigation: {name}')
        # C13d: chain nodes must be exactly the one top-level install, as a list.
        require(chain.get('nodes') == [f'node_modules/{name}'],
                f'npm audit chain nodes outside the mitigation: {name}')
        require(type(chain.get('via')) is list and chain['via']
                and all(type(item) is str and item in allowed and item != name for item in chain['via']),
                f'npm audit via chain outside the mitigation: {name}')
    for name in EXEMPT_CHAIN:
        seen, frontier = set(), {name}
        while frontier:
            current = frontier.pop()
            require(current not in seen, f'npm audit via cycle: {name}')
            seen.add(current)
            if current != EXEMPT_PACKAGE:
                frontier |= set(found[current]['via'])
        require(EXEMPT_PACKAGE in seen, f'npm audit via chain does not reach {EXEMPT_PACKAGE}: {name}')
    return dict(total=4, exempted=sorted(found), advisory=EXEMPT_ADVISORY, mitigated=True,
                review_by=MITIGATION_REVIEW_BY.isoformat())


def _tool_version(value: object, label: str) -> str:
    require(type(value) is str and 0 < len(value) <= 64 and value.strip() == value and value,
            f'npm audit capture {label} missing')
    return value


def capture_record_v2(full_bytes: bytes, full_exit_code: int, prod_report: object, prod_exit_code: int,
                      captured_at: datetime, mitigation: dict, npm_version: str, node_version: str) -> dict:
    record = capture_record(full_bytes, full_exit_code, prod_report, prod_exit_code, captured_at)
    check_mitigation_record(mitigation)
    record.update(schema=CAPTURE_SCHEMA_V2, mitigation=dict(mitigation),
                  npm_version=_tool_version(npm_version, 'npm_version'),
                  node_version=_tool_version(node_version, 'node_version'))
    return record


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
    if type(capture) is dict and capture.get('schema') == CAPTURE_SCHEMA_V2:
        return _check_recorded_v2(report, report_bytes, capture)
    require(type(capture) is dict and set(capture) == CAPTURE_KEYS and capture.get('schema') == CAPTURE_SCHEMA
            and capture.get('full_report') == 'npm-audit.json', 'npm audit capture record invalid')
    require(type(report_bytes) is bytes and capture['full_sha256'] == hashlib.sha256(report_bytes).hexdigest(),
            'npm audit capture record does not bind the recorded report')
    require(type(capture['full_exit_code']) is int and type(capture['prod_exit_code']) is int,
            'npm audit capture exit codes invalid')
    captured = _timestamp(capture['captured_at'])
    check_prod(capture['prod_report'], capture['prod_exit_code'])
    # C13d: v1 carries no mitigation pin, so it may only vouch for a zero full report.
    require(counts(report)['total'] == 0, 'npm audit v1 capture with findings refused; capture v2 required')
    result = check_full(report, capture['full_exit_code'], captured.date())
    return dict(result, captured_at=capture['captured_at'])


def _check_recorded_v2(report: object, report_bytes: bytes, capture: dict) -> dict:
    require(set(capture) == CAPTURE_KEYS_V2 and capture.get('full_report') == 'npm-audit.json',
            'npm audit capture record invalid')
    require(type(report_bytes) is bytes and capture['full_sha256'] == hashlib.sha256(report_bytes).hexdigest(),
            'npm audit capture record does not bind the recorded report')
    require(type(capture['full_exit_code']) is int and type(capture['prod_exit_code']) is int,
            'npm audit capture exit codes invalid')
    _tool_version(capture['npm_version'], 'npm_version')
    _tool_version(capture['node_version'], 'node_version')
    check_mitigation_record(capture['mitigation'])
    captured = _timestamp(capture['captured_at'])
    check_prod(capture['prod_report'], capture['prod_exit_code'])
    result = check_mitigated(report, capture['full_exit_code'], captured.date())
    return dict(result, captured_at=capture['captured_at'])


def read_bytes(path: Path) -> bytes:
    require(path.is_file() and not path.is_symlink(), f'missing npm audit report: {path}')
    require(path.stat().st_size <= MAX_REPORT_BYTES, f'npm audit report too large: {path}')
    return path.read_bytes()


def read(path: Path) -> object:
    return json.loads(read_bytes(path).decode('utf-8'))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    parser.add_argument('--verify-only', action='store_true', help='only verify the vendored mitigation')
    parser.add_argument('--no-capture', action='store_true', help='judge without writing the capture record')
    parser.add_argument('--full', type=Path)
    parser.add_argument('--full-exit-code', type=int)
    parser.add_argument('--prod', type=Path)
    parser.add_argument('--prod-exit-code', type=int)
    parser.add_argument('--npm-version')
    parser.add_argument('--node-version')
    args = parser.parse_args(argv)
    now = utc_now()
    today = now.date()
    try:
        mitigation = verify_vendored_mitigation(args.repo)  # M7: always first, even for a zero report
        if args.verify_only:
            require(today <= MITIGATION_REVIEW_BY,
                    f'npm audit deepmerge mitigation review overdue after {MITIGATION_REVIEW_BY}; recheck removal_condition')
            print(json.dumps(dict(passed=True, verify_only=True, mitigation=mitigation,
                                  review_by=MITIGATION_REVIEW_BY.isoformat()), sort_keys=True))
            return 0
        require(None not in (args.full, args.full_exit_code, args.prod, args.prod_exit_code),
                '--full/--full-exit-code/--prod/--prod-exit-code required')
        npm_version = _tool_version(args.npm_version, 'npm_version')
        node_version = _tool_version(args.node_version, 'node_version')
        prod = read(args.prod)
        full_bytes = read_bytes(args.full)
        full = json.loads(full_bytes.decode('utf-8'))
        result = dict(prod=check_prod(prod, args.prod_exit_code),
                      full=check_mitigated(full, args.full_exit_code, today),
                      date=today.isoformat(), passed=True, npm_version=npm_version, node_version=node_version)
        major = npm_version.split('.')[0]
        if result['full']['total'] == 0 and major.isdigit() and int(major) < 11:  # non-blocking
            print(REMOVAL_HINT, file=sys.stderr)
        if not args.no_capture:
            record = capture_record_v2(full_bytes, args.full_exit_code, prod, args.prod_exit_code, now,
                                       mitigation, npm_version, node_version)
            capture = args.full.with_name(CAPTURE_NAME)
            require(not capture.exists(), f'npm audit capture record already exists: {capture}')
            capture.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n', encoding='utf-8')
            result['captured_at'] = record['captured_at']
    except (GateError, ValueError, OSError) as error:
        print(json.dumps(dict(passed=False, error=str(error))), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
