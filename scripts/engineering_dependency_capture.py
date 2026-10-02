#!/usr/bin/env python3
"""Engineering capture integrity only; findings never grant security acceptance."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import tomllib

import exact_build_audit as exact
import release_dependency_contract as contract

BRANCH = 'ci/issue85-dependency-capture-20261001'
WORKFLOW = 'Eswink/coding-tools-mcp/.github/workflows/issue85-dependency-capture.yml@refs/heads/' + BRANCH
TARGET = 'x86_64-unknown-linux-gnu'
FLAGS = dict(engineering_only=True, release_approved=False, publish_approved=False, raw_zero_claim=False)
RECEIPT = 'engineering-receipt.json'


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def producer(sha, root=None):
    exact.need(os.environ.get('GITHUB_ACTIONS') == 'true', 'github_actions_required')
    workflow = WORKFLOW
    from rc_source_assembly import WORKFLOW as ASSEMBLY_WORKFLOW, verify_source
    if os.environ.get('GITHUB_WORKFLOW_REF') == ASSEMBLY_WORKFLOW:
        exact.need(root is not None, 'assembly_source_root_required')
        exact.need(os.environ.get('GITHUB_JOB') in {'capture', 'verify'}, 'wrong_assembly_capture_job')
        verify_source(root, sha)
        workflow = ASSEMBLY_WORKFLOW
    expected = dict(repository=contract.REPOSITORY, workflow_ref=workflow, sha=sha, job='capture')
    for key, env in (('repository', 'GITHUB_REPOSITORY'), ('workflow_ref', 'GITHUB_WORKFLOW_REF'), ('sha', 'GITHUB_SHA')):
        exact.need(os.environ.get(env) == expected[key], 'wrong_producer_' + key)
    for key, env in (('run_id', 'GITHUB_RUN_ID'), ('run_attempt', 'GITHUB_RUN_ATTEMPT')):
        value = os.environ.get(env, '')
        exact.need(re.fullmatch('[1-9][0-9]*', value), 'invalid_' + key)
        expected[key] = value
    return expected


def inventory(output):
    result = {}
    for path in sorted(output.rglob('*')):
        exact.need(not path.is_symlink(), 'linked_artifact')
        if path.is_file() and path != output / RECEIPT:
            result[path.relative_to(output).as_posix()] = exact.digest(exact.read(path))
        else:
            exact.need(path.is_dir() or path == output / RECEIPT, 'nonregular_artifact')
    return result


def command(root, output, records, name, argv):
    record = dict(command=argv, started_at=datetime.now(timezone.utc).isoformat())
    records[name] = record
    write_json(output / 'commands.json', records)
    try:
        code, stdout, stderr = exact.execute(argv, root)
        (output / (name + '.stdout')).write_bytes(stdout)
        (output / (name + '.stderr')).write_bytes(stderr)
        record['exit'] = code
        return code, stdout
    finally:
        record['completed_at'] = datetime.now(timezone.utc).isoformat()
        write_json(output / 'commands.json', records)


def raw_report(data, lock, code, snapshot):
    report = exact.decode(data)
    settings = report.get('settings', {})
    exact.need(settings == dict(target_arch=[], target_os=[], severity=None, ignore=[],
                               informational_warnings=['unmaintained', 'unsound', 'notice']), 'filtered_raw_audit')
    packages = lock.get('package', [])
    locked = {exact.key(package): package for package in packages}
    count = report.get('lockfile', {}).get('dependency-count')
    exact.need(locked and len(locked) == len(packages) and type(count) is int and count == len(locked), 'invalid_lock_count')
    database = report.get('database', {})
    count = database.get('advisory-count')
    exact.need(type(count) is int and 0 < count <= snapshot['file_count'], 'invalid_advisory_count')
    exact.need(database.get('last-commit') in (None, snapshot['commit']), 'wrong_report_database')
    vulnerabilities = report.get('vulnerabilities', {})
    findings = vulnerabilities.get('list')
    count = vulnerabilities.get('count')
    exact.need(type(findings) is list and type(count) is int and count == len(findings) and
               vulnerabilities.get('found') is bool(findings), 'invalid_finding_count')
    exact.need(type(code) is int and code == (1 if findings else 0), 'invalid_audit_exit')
    warnings = report.get('warnings')
    exact.need(type(warnings) is dict and set(warnings) <= {'unmaintained', 'unsound', 'notice', 'yanked'}, 'invalid_warnings')
    for kind, values in [('vulnerability', findings), *warnings.items()]:
        exact.need(type(values) is list, 'invalid_finding_list')
        for value in values:
            package = value.get('package', {})
            identity = exact.key(package)
            exact.need(identity in locked and package.get('checksum') == locked[identity].get('checksum'), 'unmapped_finding')
            advisory = value.get('advisory')
            if kind != 'vulnerability':
                exact.need(value.get('kind') == kind, 'wrong_warning_kind')
            if kind == 'yanked':
                exact.need(advisory is None, 'wrong_yanked_advisory')
            else:
                exact.need(type(advisory) is dict and advisory.get('package') == package['name'] and
                           re.fullmatch(r'RUSTSEC-[0-9]{4}-[0-9]{4}', str(advisory.get('id'))), 'invalid_advisory')
                exact.need(kind == 'vulnerability' or advisory.get('informational') == kind, 'wrong_warning_advisory')
    return dict(vulnerability_count=len(findings), warning_counts={key: len(value) for key, value in warnings.items()})


def verify(root, output, sha, version, trusted_digest):
    contract.hash_value(trusted_digest)
    data = exact.read(output / RECEIPT)
    exact.need(exact.digest(data) == trusted_digest, 'untrusted_receipt_digest')
    receipt = exact.decode(data)
    source = exact.source_identity(root, sha, version, TARGET)
    exact.need(type(receipt.get('schema')) is int and receipt['schema'] == 1, 'wrong_schema')
    exact.need(all(receipt.get(key) is value for key, value in FLAGS.items()), 'wrong_authority')
    exact.need(receipt.get('source') == source and receipt.get('producer') == producer(sha, root), 'wrong_source_or_producer')
    exact.need(receipt.get('files') == inventory(output), 'artifact_inventory_mismatch')
    required = {'commands.json', 'noncloud/raw-audit-capture.json'}
    required |= {name + suffix for name in ('cargo', 'rustc', 'audit-version', 'collector', 'gateway')
                 for suffix in ('.stdout', '.stderr')}
    required |= {'noncloud/rust-audit-' + name + suffix for name in ('desktop', 'local-agent', 'cloud-agent')
                 for suffix in ('.json', '.stderr')}
    required |= {'noncloud/desktop-glib/' + name for name in ('metadata.json', 'summary.json', 'upstream.crate')}
    required |= {'noncloud/desktop-glib/' + name + '-raw-audit' + suffix for name in ('product', 'upstream-identity')
                 for suffix in ('.json', '.stderr')}
    exact.need(set(receipt['files']) == required, 'incomplete_capture_streams')
    records = exact.decode(exact.read(output / 'commands.json'))
    exact.need(records == receipt['commands'] and set(records) == {'cargo', 'rustc', 'audit-version', 'collector', 'gateway'}, 'wrong_commands')
    for record in records.values():
        times = [datetime.fromisoformat(record[key]) for key in ('started_at', 'completed_at')]
        exact.need(all(value.tzinfo is not None for value in times) and times[0] <= times[1], 'invalid_command_times')
    for name in ('cargo', 'rustc', 'audit-version', 'collector'):
        exact.need(type(records[name].get('exit')) is int and records[name]['exit'] == 0, 'failed_' + name)
    for name in ('cargo', 'rustc'):
        text = exact.read(output / (name + '.stdout')).decode()
        exact.need(text == receipt['toolchain'][name] and re.match(r'^' + name + r' 1\.98\.1(?: |$)', text), 'wrong_toolchain')
    exact.need(exact.read(output / 'audit-version.stdout').decode().strip() == 'cargo-audit 0.22.2', 'wrong_audit_version')
    contract.hash_value(receipt['audit_binary_sha256'])
    snapshot = receipt['advisory_database']
    exact.need(snapshot.get('clean') is True and snapshot.get('origin', '').lower() == 'https://github.com/rustsec/advisory-db.git', 'wrong_database')
    for key, length in (('commit', 40), ('tree', 40), ('contents_sha256', 64)):
        exact.need(re.fullmatch('[0-9a-f]{' + str(length) + '}', str(snapshot.get(key))), 'wrong_database_identity')
    exact.need(type(snapshot.get('file_count')) is int and snapshot['file_count'] > 0, 'wrong_database_count')
    noncloud = output / 'noncloud'
    captured = exact.decode(exact.read(noncloud / 'raw-audit-capture.json'))
    expected = {**source, **producer(sha, root), 'source_root': receipt['source_root'], 'audit_version': 'cargo-audit 0.22.2',
                'audit_binary_sha256': receipt['audit_binary_sha256'], 'advisory_database': snapshot,
                'release_approved': False, 'publish_approved': False}
    exact.need(type(captured.get('schema')) is int and captured['schema'] == 1, 'wrong_capture_schema')
    exact.need(all(captured.get(key) == value for key, value in expected.items()), 'wrong_inner_capture_identity')
    exact.need(captured.get('release_approved') is False and captured.get('publish_approved') is False, 'wrong_inner_authority')
    exact.need(set(captured['reports']) == {'desktop', 'local-agent', 'cloud-agent'}, 'incomplete_noncloud_reports')
    audit_bin, database = receipt['audit_bin'], receipt['database_path']
    exact.need(set(receipt['locks']) == set(contract.LOCKS), 'wrong_lock_inventory')
    for name in ('cargo', 'rustc'):
        exact.need(records[name]['command'] == [name, '-Vv'], 'unexpected_toolchain_command')
    exact.need(records['audit-version']['command'] == [audit_bin, '--version'], 'unexpected_audit_version_command')
    source_root = Path(receipt['source_root'])
    expected_collector = [receipt['python_executable'], str(source_root / 'scripts/release_dependency_capture.py'),
                          '--root', str(source_root), '--output', receipt['capture_output'],
                          '--audit-bin', audit_bin, '--audit-db', database, '--expected-sha', sha, '--version', version]
    exact.need(records['collector']['command'] == expected_collector, 'unexpected_collector_command')
    results = {}
    for name, relative in contract.LOCKS.items():
        lock = tomllib.loads(exact.read(root / relative).decode())
        exact.need(receipt['locks'][name] == contract.hash_file(root / relative), 'lock_changed')
        if name == 'cloud-gateway':
            record = records['gateway']
            raw = exact.read(output / 'gateway.stdout')
        else:
            record = captured['reports'][name]
            raw = exact.read(noncloud / ('rust-audit-' + name + '.json'))
            exact.need(record['raw_sha256'] == exact.digest(raw) and record['lock_sha256'] == receipt['locks'][name], 'raw_report_changed')
        expected_command = [audit_bin, 'audit', '--no-fetch', '--db', database, '--json', '--file', relative]
        exact.need(record['command'] == expected_command, 'unexpected_audit_command')
        results[name] = raw_report(raw, lock, record['exit'], snapshot)
    desktop = exact.decode(exact.read(noncloud / 'rust-audit-desktop.json'))
    lock = tomllib.loads(exact.read(root / contract.LOCKS['desktop']).decode())
    proof = contract.desktop_source_proof(root, noncloud, captured, desktop, lock)
    exact.need(proof.get('required') is True and proof.get('source_backport_verified') is True, 'live_glib_proof_required')
    glib = exact.decode(exact.read(noncloud / 'desktop-glib/summary.json'))
    exact.need(glib.get('advisory_database') == snapshot and glib.get('audit_binary_sha256') == receipt['audit_binary_sha256'] and
               glib.get('audit_version') == 'cargo-audit 0.22.2' and glib.get('release_approved') is False and
               glib.get('raw_zero_claim') is False, 'wrong_glib_identity')
    exact.need(set(glib['audit_commands']) == {'product', 'upstream-identity'}, 'wrong_glib_commands')
    metadata_count = len(exact.decode(exact.read(noncloud / 'desktop-glib/metadata.json'))['packages'])
    exact.need(type(glib.get('metadata_package_count')) is int and glib['metadata_package_count'] == metadata_count,
               'wrong_glib_metadata_count')
    for key in ('upstream_archive_sha256', 'upstream_fix_commit', 'source_file_count', 'changed_files', 'patch_sha256', 'provenance_sha256'):
        exact.need(glib.get(key) == proof.get(key), 'wrong_glib_source_summary')
    exact.need(glib.get('source_backport_verified') is True and glib.get('product_lock_sha256') == receipt['locks']['desktop'],
               'wrong_glib_source_identity')
    for name, relative in (('product', 'src-tauri/Cargo.lock'), ('upstream-identity', 'patches/glib-0.18.5/upstream-identity.Cargo.lock')):
        record = glib['audit_commands'][name]
        raw = exact.read(noncloud / ('desktop-glib/' + name + '-raw-audit.json'))
        exact.need(record['report_sha256'] == exact.digest(raw) and record['command'] ==
                   [audit_bin, 'audit', '--no-fetch', '--db', database, '--file', relative, '--json'], 'wrong_glib_command')
        raw_report(raw, tomllib.loads(exact.read(root / relative).decode()), record['exit'], snapshot)
    return dict(schema=1, **FLAGS, pipeline_integrity='verified', security_acceptance='not_evaluated',
                source=source, producer=producer(sha, root), reports=results, receipt_sha256=trusted_digest,
                desktop_source_backport_verified=True, installed_desktop_bytes_verified=False)


def collect(root, output, audit_bin, database, sha, version):
    exact.need(not output.exists() and not output.is_relative_to(root), 'output_must_be_new_external')
    exact.need(not database.exists() and not database.is_relative_to(root), 'database_must_be_new_external')
    output.mkdir(parents=True)
    records = {}
    try:
        source = exact.source_identity(root, sha, version, TARGET)
        ci = producer(sha, root)
        exact.need(os.environ.get('GITHUB_JOB') == 'capture', 'wrong_capture_job')
        audit_hash = contract.hash_file(audit_bin)
        toolchain = {}
        for name in ('cargo', 'rustc'):
            code, data = command(root, output, records, name, [name, '-Vv'])
            exact.need(code == 0, 'toolchain_failed')
            toolchain[name] = data.decode()
        code, data = command(root, output, records, 'audit-version', [str(audit_bin), '--version'])
        exact.need(code == 0 and data.decode().strip() == 'cargo-audit 0.22.2', 'wrong_audit_tool')
        argv = [sys.executable, str(root / 'scripts/release_dependency_capture.py'), '--root', str(root),
                '--output', str(output / 'noncloud'), '--audit-bin', str(audit_bin), '--audit-db', str(database),
                '--expected-sha', sha, '--version', version]
        collector_code, _ = command(root, output, records, 'collector', argv)
        snapshot = exact.database_identity(database)
        command(root, output, records, 'gateway', [str(audit_bin), 'audit', '--no-fetch', '--db', str(database),
                                                  '--json', '--file', contract.LOCKS['cloud-gateway']])
        exact.need(snapshot == exact.database_identity(database), 'database_changed')
        exact.need(source == exact.source_identity(root, sha, version, TARGET), 'source_changed')
        exact.need(audit_hash == contract.hash_file(audit_bin), 'audit_binary_changed')
        exact.need(collector_code == 0, 'collector_failed')
        receipt = dict(schema=1, **FLAGS, source=source, producer=ci, source_root=str(root),
                       audit_bin=str(audit_bin), database_path=str(database), audit_binary_sha256=audit_hash,
                       toolchain=toolchain, python_version=sys.version, python_executable=sys.executable,
                       capture_output=str(output / 'noncloud'), commands=records, advisory_database=snapshot,
                       locks={name: contract.hash_file(root / path) for name, path in contract.LOCKS.items()}, files=inventory(output))
        write_json(output / RECEIPT, receipt)
        digest = contract.hash_file(output / RECEIPT)
        return verify(root, output, sha, version, digest)
    except Exception as error:
        write_json(output / 'failure.json', dict(**FLAGS, pipeline_integrity='incomplete', error_type=type(error).__name__, reason=str(error)))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('collect', 'verify'))
    for name in ('root', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--expected-sha', required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--audit-bin', type=Path)
    parser.add_argument('--audit-db', type=Path)
    parser.add_argument('--expected-receipt-sha256')
    args = parser.parse_args()
    if args.mode == 'collect':
        exact.need(args.audit_bin and args.audit_db, 'audit_paths_required')
        result = collect(args.root.resolve(), args.output.resolve(), args.audit_bin.resolve(),
                         args.audit_db.resolve(), args.expected_sha, args.version)
    else:
        result = verify(args.root.resolve(), args.output.resolve(), args.expected_sha, args.version, args.expected_receipt_sha256)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
