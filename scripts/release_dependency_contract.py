#!/usr/bin/env python3
"""Bind CI archive bytes to complete build evidence; never authorize a release.

Trust inputs must come from the reviewed producer's CI outputs, not downloaded
receipts. The engineering archive mode is deliberately ineligible for final RC.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import tarfile
import tomllib

import exact_build_audit as exact

REPOSITORY = 'Eswink/coding-tools-mcp'
WORKFLOWS = {'final-rc-packages.yml', 'full-rc-cloud-binaries.yml',
             'issue85-exact-build-audit.yml'}
PRODUCER_FIELDS = {'provider', 'repository', 'sha', 'run_id', 'run_attempt',
                   'workflow_ref', 'job', 'runner_os'}
LOCKS = {'desktop': 'src-tauri/Cargo.lock',
         'local-agent': 'services/local-agent/Cargo.lock',
         'cloud-agent': 'services/cloud-agent/Cargo.lock',
         'cloud-gateway': exact.LOCK}


def hash_file(path: Path) -> str:
    exact.need(path.is_file() and not path.is_symlink(), 'nonregular_evidence')
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def hash_value(value: str) -> None:
    exact.need(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value),
               'missing_or_invalid_trusted_digest')


def producer(sha: str, run_id: str, attempt: str, workflow_ref: str,
             job: str = 'build') -> dict:
    exact.need(isinstance(sha, str) and re.fullmatch('[0-9a-f]{40}', sha), 'invalid_producer_source')
    for value in (run_id, attempt):
        exact.need(isinstance(value, str) and re.fullmatch('[1-9][0-9]*', value), 'invalid_producer_run')
    prefix = REPOSITORY + '/.github/workflows/'
    exact.need(isinstance(workflow_ref, str) and workflow_ref.startswith(prefix), 'invalid_producer_workflow')
    filename, separator, ref = workflow_ref[len(prefix):].partition('@')
    exact.need(filename in WORKFLOWS and separator and
               re.fullmatch(r'refs/(heads|tags)/[A-Za-z0-9][A-Za-z0-9._/-]*', ref),
               'invalid_producer_workflow')
    exact.need(job == 'build', 'unexpected_producer_job')
    return dict(provider='github-actions', repository=REPOSITORY, sha=sha,
                run_id=run_id, run_attempt=attempt, workflow_ref=workflow_ref,
                job=job, runner_os='Linux')


def current_producer() -> dict:
    return producer(os.environ.get('GITHUB_SHA', ''), os.environ.get('GITHUB_RUN_ID', ''),
                    os.environ.get('GITHUB_RUN_ATTEMPT', ''), os.environ.get('GITHUB_WORKFLOW_REF', ''))


def warning_policy(audit: dict, lock: dict) -> dict:
    """Retain every warning; an unsound record is never a cloud absence waiver."""
    locked = {exact.key(p): p for p in lock.get('package', [])}
    exact.need(locked and len(locked) == len(lock.get('package', [])), 'invalid_warning_lock')
    warnings = audit.get('warnings')
    exact.need(type(warnings) is dict, 'missing_raw_warnings')
    for kind, records in warnings.items():
        exact.need(kind in {'unmaintained', 'unsound', 'notice', 'yanked'}, 'unknown_warning_kind')
        exact.need(type(records) is list, 'malformed_raw_warning')
        for record in records:
            exact.need(type(record) is dict and record.get('kind') == kind, 'warning_kind_mismatch')
            package = record.get('package', {})
            key = exact.key(package)
            exact.need(key in locked and package.get('checksum') == locked[key].get('checksum'),
                       'unmapped_raw_warning')
            advisory = record.get('advisory')
            if kind == 'yanked':
                exact.need(advisory is None, 'unknown_yanked_advisory')
            else:
                exact.need(type(advisory) is dict and
                           re.fullmatch(r'RUSTSEC-[0-9]{4}-[0-9]{4}', str(advisory.get('id'))) and
                           advisory.get('package') == package['name'] and
                           advisory.get('informational') == kind, 'unknown_warning_advisory')
            exact.need(kind != 'unsound', 'unresolved_unsound_warning')
    return warnings


def raw_audit(audit: dict, lock: dict, *, zero: bool) -> dict:
    """Validate actual cargo-audit shape, never bool/zero or list/count shortcuts."""
    settings = audit.get('settings', {})
    exact.need(settings.get('ignore') == [] and settings.get('target_arch') == [] and
               settings.get('target_os') == [] and 'severity' in settings and settings['severity'] is None,
               'filtered_raw_audit')
    exact.need(set(settings.get('informational_warnings', [])) == {'unmaintained', 'unsound', 'notice'},
               'suppressed_audit_warnings')
    db = audit.get('database', {})
    exact.need(type(db.get('advisory-count')) is int and db['advisory-count'] > 0, 'missing_audit_database')
    count = audit.get('lockfile', {}).get('dependency-count')
    exact.need(type(count) is int and count == len(lock.get('package', [])) and count > 0,
               'incomplete_raw_lock_audit')
    vulnerability = audit.get('vulnerabilities', {})
    findings = vulnerability.get('list')
    exact.need(type(findings) is list and type(vulnerability.get('count')) is int and
               vulnerability['count'] == len(findings) and vulnerability.get('found') is bool(findings),
               'invalid_raw_finding_count')
    exact.need(not zero or not findings, 'active_or_unproven_raw_vulnerability')
    return {'raw_lock_audit': 'findings_present' if findings else 'no_vulnerabilities_found',
            'raw_vulnerability_count': len(findings), 'raw_warnings': warning_policy(audit, lock)}


def verify_build(root: Path, evidence: Path, binaries: Path, version: str,
                 sha: str, target: str, envelope_digest: str, expected_producer: dict) -> dict:
    hash_value(envelope_digest)
    exact.need(set(expected_producer) == PRODUCER_FIELDS, 'incomplete_expected_producer')
    canonical = producer(sha, expected_producer['run_id'], expected_producer['run_attempt'],
                         expected_producer['workflow_ref'], expected_producer['job'])
    exact.need(canonical == expected_producer, 'invalid_expected_producer')
    result = exact.verify(root, evidence, sha, version, target, envelope_digest, binaries)
    exact.need(result['ci'] == expected_producer, 'wrong_exact_build_producer')
    audit_bytes = exact.read(evidence / 'raw-audit.json')
    lock = tomllib.loads(exact.read(root / exact.LOCK).decode())
    raw = raw_audit(exact.decode(audit_bytes), lock, zero=False)
    exact.need(result['raw_vulnerability_count'] == raw['raw_vulnerability_count'] and
               len(result['classified_raw_findings']) == raw['raw_vulnerability_count'],
               'unclassified_raw_finding')
    return {**result, **raw, 'raw_audit_sha256': exact.digest(audit_bytes),
            'release_approved': False, 'publish_approved': False}


def engineering_unpack(archive: Path, destination: Path, expected_digest: str) -> None:
    hash_value(expected_digest)
    exact.need(hash_file(archive) == expected_digest, 'untrusted_archive_digest')
    exact.need(not destination.exists(), 'unpack_target_must_be_new')
    with tarfile.open(archive, 'r:gz') as tar:
        members = tar.getmembers()
        exact.need(len(members) == 4 and {m.name for m in members} == exact.BINS,
                   'engineering_archive_member_mismatch')
        exact.need(all(m.isfile() and not m.issym() and not m.islnk() and
                       0 < m.size < 256 * 1024**2 for m in members), 'engineering_archive_member_type')
        destination.mkdir(parents=True)
        for member in members:
            data = tar.extractfile(member).read(member.size + 1)
            exact.need(len(data) == member.size, 'engineering_archive_truncated')
            (destination / member.name).write_bytes(data)


def verify_archive(root: Path, directory: Path, evidence: Path, unpacked: Path,
                   version: str, sha: str, target: str, archive_digest: str,
                   envelope_digest: str, expected_producer: dict, *, engineering=False) -> dict:
    hash_value(archive_digest)
    exact.need(not unpacked.resolve().is_relative_to(root.resolve()), 'unpack_must_be_outside_source')
    if engineering:
        archive = directory / 'engineering-binaries.tar.gz'
        engineering_unpack(archive, unpacked, archive_digest)
        binaries = unpacked
    else:
        # Local import avoids the existing final_rc_evidence/read_json import cycle.
        import cloud_release_bundle as cloud
        exact.need(expected_producer == current_producer(), 'wrong_current_producer_attempt_or_workflow')
        expected = cloud.identity(root, version)
        exact.need(expected['source_sha'] == sha and expected['run_id'] == expected_producer['run_id'],
                   'wrong_archive_producer_source_or_run')
        archive = directory / 'cloud-linux-amd64.tar.gz'
        cloud.unpack_trusted(directory, unpacked, expected, archive_digest)
        binaries = unpacked / 'bin'
    result = verify_build(root, evidence, binaries, version, sha, target,
                          envelope_digest, expected_producer)
    return {**result, 'archive_sha256': archive_digest, 'archive_size': archive.stat().st_size,
            'artifact_kind': 'engineering' if engineering else 'release-cloud',
            'archive_to_build_verified': True}


def desktop_source_proof(root: Path, directory: Path, capture: dict, product: dict, lock: dict) -> dict:
    local_glib = any(p['name'] == 'glib' and p.get('source') is None for p in lock['package'])
    exact.need(capture.get('desktop_glib_source_proof_required') is local_glib, 'desktop_source_proof_scope_mismatch')
    if not local_glib:
        return {'required': False, 'scope': 'registry_audit_only'}
    path = root / 'scripts/verify_glib_backport.py'
    exact.need(path.is_file() and not path.is_symlink(), 'desktop_glib_source_verifier_required')
    spec = importlib.util.spec_from_file_location('release_glib_source_verifier', path)
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    folder = directory / 'desktop-glib'
    source = verifier.verify_source(root, folder / 'upstream.crate')
    manifests = verifier.verify_configuration(root, os.environ)
    metadata = exact.decode(exact.read(folder / 'metadata.json'))
    verifier.verify_metadata(Path(capture['source_root']), metadata, lock, manifests)
    original = exact.decode(exact.read(folder / 'upstream-identity-raw-audit.json'))
    captured_product = exact.decode(exact.read(folder / 'product-raw-audit.json'))
    exact.need(captured_product == product, 'desktop_paired_product_audit_changed')
    upstream_lock = tomllib.loads(exact.read(root / verifier.PROVENANCE / 'upstream-identity.Cargo.lock').decode())
    paired = verifier.verify_audits(product, original, lock, upstream_lock)
    return {'required': True, **source, **paired, 'source_backport_verified': True,
            'installed_desktop_bytes_verified': False}


def verify_noncloud_audits(root: Path, directory: Path, expected: dict) -> dict:
    capture = exact.decode(exact.read(directory / 'raw-audit-capture.json'))
    exact.need(type(capture.get('schema')) is int and capture['schema'] == 1, 'wrong_capture_schema')
    required = dict(sha=expected['source_sha'], tree=expected['source_tree'],
                    product_version=expected['version'], run_id=expected['run_id'],
                    run_attempt=os.environ.get('GITHUB_RUN_ATTEMPT'), repository=REPOSITORY,
                    workflow_ref=os.environ.get('GITHUB_WORKFLOW_REF'), job='contracts',
                    audit_version='cargo-audit 0.22.2', release_approved=False, publish_approved=False)
    exact.need(all(capture.get(k) == v for k, v in required.items()), 'wrong_raw_audit_capture_producer')
    hash_value(capture.get('audit_binary_sha256'))
    snapshot = capture.get('advisory_database', {})
    exact.need(snapshot.get('clean') is True and snapshot.get('origin', '').lower() ==
               'https://github.com/rustsec/advisory-db.git', 'wrong_raw_advisory_snapshot')
    for key, length in (('commit', 40), ('tree', 40), ('contents_sha256', 64)):
        exact.need(re.fullmatch('[0-9a-f]{' + str(length) + '}', str(snapshot.get(key))), 'wrong_raw_advisory_snapshot')
    records = capture.get('reports', {})
    exact.need(set(records) == {'desktop', 'local-agent', 'cloud-agent'}, 'incomplete_noncloud_audits')
    results = {}
    for name, record in records.items():
        data = exact.read(directory / f'rust-audit-{name}.json')
        exact.need(exact.digest(data) == record.get('raw_sha256') and
                   hash_file(root / LOCKS[name]) == record.get('lock_sha256'), 'raw_lock_or_report_changed')
        command = record.get('command', [])
        exact.need(len(command) == 8 and command[1:4] == ['audit', '--no-fetch', '--db'] and
                   command[5:] == ['--json', '--file', LOCKS[name]], 'unexpected_raw_audit_command')
        audit = exact.decode(data)
        database = audit.get('database', {})
        exact.need(database.get('last-commit') in (None, snapshot['commit']) and
                   type(snapshot.get('file_count')) is int and
                   type(database.get('advisory-count')) is int and
                   snapshot['file_count'] >= database['advisory-count'], 'raw_advisory_snapshot_disagreement')
        lock = tomllib.loads(exact.read(root / LOCKS[name]).decode())
        result = raw_audit(audit, lock, zero=True)
        exact.need(type(record.get('exit')) is int and record['exit'] == 0, 'failed_zero_audit_command')
        if name == 'desktop':
            result['desktop_source'] = desktop_source_proof(root, directory, capture, audit, lock)
        results[name] = result
    return results


def add_trust_arguments(parser):
    parser.add_argument('--expected-archive-sha256', required=True)
    parser.add_argument('--expected-envelope-sha256', required=True)
    parser.add_argument('--producer-run-id', required=True)
    parser.add_argument('--producer-run-attempt', required=True)
    parser.add_argument('--producer-workflow-ref', required=True)
    parser.add_argument('--producer-job', required=True)


def trust_arguments(args, sha):
    expected = producer(sha, args.producer_run_id, args.producer_run_attempt,
                        args.producer_workflow_ref, args.producer_job)
    return dict(archive_digest=args.expected_archive_sha256,
                envelope_digest=args.expected_envelope_sha256, expected_producer=expected)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--directory', type=Path, required=True)
    p.add_argument('--evidence', type=Path, required=True)
    p.add_argument('--unpack', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--version', required=True)
    p.add_argument('--expected-sha', required=True)
    p.add_argument('--target', default='x86_64-unknown-linux-gnu')
    p.add_argument('--engineering', action='store_true')
    add_trust_arguments(p)
    a = p.parse_args()
    result = verify_archive(a.root.resolve(), a.directory.resolve(), a.evidence.resolve(),
                            a.unpack.resolve(), a.version, a.expected_sha, a.target,
                            **trust_arguments(a, a.expected_sha), engineering=a.engineering)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except (exact.EvidenceError, OSError, ValueError, KeyError, TypeError, AttributeError, tarfile.TarError) as exc:
        raise SystemExit('BLOCKED: ' + str(exc)) from None
