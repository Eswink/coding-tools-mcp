"""Data-only noncloud verification against authenticated FINAL producer identity.

No environment identity is substituted. The unchanged desktop source verifier
also checks the real consumer configuration; that is not a historical producer
environment attestation. Detailed findings remain in private evidence only.
"""
from __future__ import annotations

from pathlib import Path
import re
import tomllib

import release_dependency_contract as dependency
from rc_consumer_io import hash_file, json_file, need, read_bytes

WARNING_KINDS = ('unmaintained', 'unsound', 'notice', 'yanked')
REPOSITORY = 'Eswink/coding-tools-mcp'
FINAL_REF = (re.escape(REPOSITORY) + r'/\.github/workflows/final-rc-packages\.yml'
             r'@refs/heads/release/full-rc-candidate-[A-Za-z0-9][A-Za-z0-9._-]*')
RC = r'(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)-rc\.(?:0|[1-9][0-9]*)'


def positive(value):
    return type(value) is int and value > 0


def digest_value(value):
    need(type(value) is str and re.fullmatch(r'[0-9a-f]{64}', value), 'invalid_content_digest')
    return value


def producer_identity(producer):
    """Validate context shape, never derive authority from artifact JSON."""
    need(producer.repository == REPOSITORY, 'wrong_trusted_repository')
    for field in ('repository_id', 'run_id', 'run_attempt', 'workflow_id',
                  'bundle_job_id', 'artifact_id', 'artifact_size'):
        need(positive(getattr(producer, field)), 'invalid_trusted_numeric_identity')
    need(producer.run_attempt == 1, 'unsupported_rerun_provenance')
    for field in ('source_sha', 'source_tree'):
        value = getattr(producer, field)
        need(type(value) is str and re.fullmatch('[0-9a-f]{40}', value), 'invalid_trusted_source')
    need(type(producer.version) is str and re.fullmatch(RC, producer.version), 'invalid_trusted_version')
    need(type(producer.workflow_ref) is str and re.fullmatch(FINAL_REF, producer.workflow_ref),
         'unsupported_final_producer')
    digest_value(producer.artifact_sha256)
    return dict(source_sha=producer.source_sha, source_tree=producer.source_tree,
                version=producer.version, run_id=str(producer.run_id))


def approval_flags(value, *, required=False):
    for key in ('release_approved', 'publish_approved'):
        need((key not in value and not required) or value.get(key) is False,
             'invalid_approval_boundary')


def schema(value, *, required=False):
    need(('schema' not in value and not required) or
         (type(value.get('schema')) is int and value['schema'] == 1), 'unsupported_content_schema')


def verify_consumed_noncloud_audits(root: Path, directory: Path, producer) -> dict:
    """Mirror every producer check, with explicit authenticated run/attempt/ref."""
    expected = producer_identity(producer)
    capture = json_file(directory / 'raw-audit-capture.json')
    schema(capture, required=True)
    approval_flags(capture, required=True)
    required = dict(sha=expected['source_sha'], tree=expected['source_tree'],
                    product_version=expected['version'], run_id=expected['run_id'],
                    run_attempt=str(producer.run_attempt), repository=REPOSITORY,
                    workflow_ref=producer.workflow_ref, job='contracts', audit_version='cargo-audit 0.22.2')
    need(all(capture.get(k) == v for k, v in required.items()), 'wrong_raw_audit_capture_producer')
    digest_value(capture.get('audit_binary_sha256'))
    snapshot = capture.get('advisory_database')
    need(type(snapshot) is dict and snapshot.get('clean') is True and
         type(snapshot.get('origin')) is str and snapshot['origin'].lower() ==
         'https://github.com/rustsec/advisory-db.git', 'wrong_raw_advisory_snapshot')
    for key, length in (('commit', 40), ('tree', 40), ('contents_sha256', 64)):
        need(type(snapshot.get(key)) is str and re.fullmatch('[0-9a-f]{' + str(length) + '}',
             snapshot[key]), 'wrong_raw_advisory_snapshot')
    need(positive(snapshot.get('file_count')), 'wrong_raw_advisory_snapshot')
    records = capture.get('reports')
    need(type(records) is dict and set(records) == {'desktop', 'local-agent', 'cloud-agent'},
         'incomplete_noncloud_audits')
    results = {}
    for name, record in records.items():
        need(type(record) is dict, 'invalid_raw_audit_record')
        path = directory / f'rust-audit-{name}.json'
        need(hash_file(path) == record.get('raw_sha256') and
             hash_file(root / dependency.LOCKS[name]) == record.get('lock_sha256'), 'raw_lock_or_report_changed')
        command = record.get('command')
        need(type(command) is list and len(command) == 8 and
             all(type(part) is str and part for part in command) and
             command[1:4] == ['audit', '--no-fetch', '--db'] and
             command[5:] == ['--json', '--file', dependency.LOCKS[name]], 'unexpected_raw_audit_command')
        audit = json_file(path)
        database = audit.get('database', {})
        need(type(database) is dict and database.get('last-commit') in (None, snapshot['commit']) and
             type(database.get('advisory-count')) is int and
             snapshot['file_count'] >= database['advisory-count'], 'raw_advisory_snapshot_disagreement')
        lock = tomllib.loads(read_bytes(root / dependency.LOCKS[name], 64 * 1024**2).decode())
        result = dependency.raw_audit(audit, lock, zero=True)
        need(type(record.get('exit')) is int and record['exit'] == 0, 'failed_zero_audit_command')
        if name == 'desktop':
            if capture.get('desktop_glib_source_proof_required') is True:
                # Reject duplicate/nonfinite (including overflow) data before the
                # unchanged reviewed source verifier's additional parsing.
                for filename in ('metadata.json', 'upstream-identity-raw-audit.json', 'product-raw-audit.json'):
                    document = json_file(directory / 'desktop-glib' / filename)
                    if filename != 'metadata.json':
                        count = document.get('lockfile', {}).get('dependency-count')
                        need(type(count) is int and count > 0, 'invalid_paired_audit_dependency_count')
            result['desktop_source'] = dependency.desktop_source_proof(root, directory, capture, audit, lock)
        results[name] = result
    return results


def warning_counts(warnings):
    need(type(warnings) is dict and set(warnings) <= set(WARNING_KINDS), 'invalid_warning_summary')
    need(all(type(v) is list for v in warnings.values()), 'invalid_warning_summary')
    return {kind: len(warnings.get(kind, [])) for kind in WARNING_KINDS}


def audit_summary(value):
    count = value.get('raw_vulnerability_count')
    active = value.get('active_vulnerability_count', count)
    need(type(count) is int and count >= 0 and type(active) is int and active == 0,
         'invalid_audit_summary')
    result = dict(raw_vulnerability_count=count, active_vulnerability_count=active,
                  warning_counts=warning_counts(value['raw_warnings']))
    if 'desktop_source' in value:
        proof = value['desktop_source']
        required = proof.get('required')
        need(type(required) is bool, 'invalid_desktop_proof_summary')
        summary = dict(required=required, source_backport_verified=required,
                       installed_desktop_bytes_verified=False)
        if required:
            need(proof.get('source_backport_verified') is True and proof.get('raw_zero_claim') is False and
                 proof.get('release_approved') is False and proof.get('installed_desktop_bytes_verified') is False,
                 'invalid_desktop_proof_summary')
            findings = proof.get('upstream_identity_vulnerabilities')
            need(type(findings) is list, 'invalid_desktop_proof_summary')
            summary.update(upstream_identity_raw_vulnerability_count=len(findings),
                           upstream_identity_warning_counts=warning_counts(proof['upstream_identity_warnings']))
        result['desktop_source'] = summary
    return result
