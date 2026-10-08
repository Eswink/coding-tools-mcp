"""Validate authenticated FINAL bytes and stage an explicitly nonpublishing plan."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile

import rc_consumer_archive as archive
import rc_consumer_contracts as contracts
from rc_consumer_finalize import FinalizationFailure, PlanCommit
from rc_consumer_io import ConsumerError, PrivateRoot, hash_file, need
import rc_consumer_snapshot as snapshot
import rc_consumer_transport as transport

SCOPE = 'authenticated-final-artifact-validation-only'
LIMITATIONS = (
    'Bounded authenticated CI observation; snapshot_atomic=false',
    'Outer API ZIP digest authenticates internal evidence transitively, not independent job signatures',
    'Installer bytes are rehashed; installed and native results are authenticated producer assertions',
    'No independent reproducibility, signing, Windows isolation or real ChatGPT acceptance is established',
    'Actual consumer environment checks do not attest the historical producer environment',
    'A future publisher must revalidate live evidence and exact staged bytes; this plan grants no authority',
    'Private staging assumes no concurrent writers with this invocation UID',
    'Failure withdraws only the owned success plan when confirmed; uncertain withdrawal fails without replay',
)
WARNING_KINDS = ('unmaintained', 'unsound', 'notice', 'yanked')
PLATFORMS = {('windows-2025', 'nsis'), ('ubuntu-22.04', 'deb'), ('ubuntu-24.04', 'deb'),
             ('ubuntu-22.04', 'appimage'), ('ubuntu-24.04', 'appimage')}


def payloads(version):
    need(type(version) is str and snapshot.gate.rc.RC_VERSION.fullmatch(version), 'invalid_rc_version')
    return ((f'MCP_{version}_x64-setup.exe', 'nsis', contracts.MEDIA_TYPES['nsis']),
            (f'MCP_{version}_amd64.deb', 'deb', contracts.MEDIA_TYPES['deb']),
            (f'MCP_{version}_amd64.AppImage', 'appimage', contracts.MEDIA_TYPES['appimage']),
            ('cloud-linux-amd64.tar.gz', 'cloud', contracts.MEDIA_TYPES['cloud']))


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8')


def count(value):
    need(type(value) is int and value >= 0, 'invalid_sanitized_count')
    return value


def warnings(value):
    need(type(value) is dict and set(value) == set(WARNING_KINDS), 'invalid_sanitized_warnings')
    return {kind: count(value[kind]) for kind in WARNING_KINDS}


def audit(value):
    result = {key: count(value[key]) for key in ('raw_vulnerability_count', 'active_vulnerability_count')}
    need(result['active_vulnerability_count'] == 0, 'active_vulnerability_remains')
    result['warning_counts'] = warnings(value['warning_counts'])
    if 'desktop_source' in value:
        proof = value['desktop_source']
        needed = proof['required']
        need(type(needed) is bool and proof['source_backport_verified'] is needed
             and proof['installed_desktop_bytes_verified'] is False, 'invalid_sanitized_desktop_proof')
        result['desktop_source'] = dict(required=needed, source_backport_verified=needed,
                                        installed_desktop_bytes_verified=False)
        if needed:
            result['desktop_source'].update(
                upstream_identity_raw_vulnerability_count=count(proof['upstream_identity_raw_vulnerability_count']),
                upstream_identity_warning_counts=warnings(proof['upstream_identity_warning_counts']))
    return result


def write_sanitized_provenance(snapshot_value, content, output):
    """Construct allowlisted fields; never copy freeform receipt strings/logs."""
    producer, candidate = snapshot_value['producer'], snapshot_value['candidate']
    contracts.producer_identity(producer)
    need(content['release_approved'] is False and content['publish_approved'] is False
         and content['raw_zero_claim'] is False, 'invalid_content_boundary')
    installed = content['installed_platforms']
    need(type(installed) is list and len(installed) == 5
         and {(row['platform'], row['kind']) for row in installed} == PLATFORMS, 'invalid_installed_matrix')
    matrix = []
    for row in sorted(installed, key=lambda item: (item['platform'], item['kind'])):
        need(type(row['native_stages']) is int and row['native_stages'] == 12
             and row['real_chatgpt_verified'] is False and row['synthetic_conversation_metadata'] is True,
             'invalid_installed_boundary')
        matrix.append(dict(platform=row['platform'], kind=row['kind'], native_stages=12,
                           real_chatgpt_verified=False, synthetic_conversation_metadata=True,
                           observations='authenticated_producer_assertions'))
    audits = content['audits']
    need(audits['raw_zero_claim'] is False and audits['npm_vulnerability_count'] == 0
         and type(audits['npm_vulnerability_count']) is int
         and set(audits['noncloud']) == {'desktop', 'cloud-agent', 'local-agent'}, 'invalid_audit_boundary')
    signing = content['signing']['windows_payload_signature_observed']
    need(type(signing) is bool and content['release_blockers'] == list(contracts.BLOCKERS),
         'invalid_signing_or_blocker_boundary')
    consumer = candidate['consumer']
    integration = snapshot_value['selection']['integration']['run']
    value = dict(schema=1, passed=True, scope=SCOPE, snapshot_atomic=False,
        release_approved=False, publish_approved=False,
        source=dict(sha=producer.source_sha, tree=producer.source_tree, version=producer.version,
                    release_tag=candidate['release_tag'], tag_object_sha=candidate['tag_object_sha']),
        repository=dict(full_name=producer.repository, id=producer.repository_id),
        producer=dict(run_id=producer.run_id, run_attempt=producer.run_attempt,
                      workflow_ref=producer.workflow_ref, workflow_id=producer.workflow_id,
                      bundle_job_id=producer.bundle_job_id,
                      bundle_job_started_at=producer.bundle_job_started_at,
                      bundle_job_completed_at=producer.bundle_job_completed_at),
        integration=dict(run_id=integration['id'], run_attempt=integration['run_attempt']),
        artifact=dict(id=producer.artifact_id, sha256=producer.artifact_sha256, size=producer.artifact_size,
                      artifact_bytes_verified=True),
        consumer=dict(run_id=consumer['run_id'], run_attempt=consumer['run_attempt'],
                      workflow_ref=consumer['workflow_ref'], source_sha=producer.source_sha),
        verified_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z'),
        installed_platforms=matrix,
        audits=dict(cloud=audit(audits['cloud']),
                    noncloud={name: audit(audits['noncloud'][name]) for name in sorted(audits['noncloud'])},
                    npm_vulnerability_count=0, raw_zero_claim=False),
        signing=dict(windows_payload_signature_observed=signing, consumer_signing_verified=False),
        release_blockers=list(contracts.BLOCKERS), limitations=list(LIMITATIONS))
    output.write('RC_PROVENANCE.json', encode(value))
    return value


def commit_success_plan(receipts, guard):
    """Final anchored rename; the outer failure boundary owns withdrawal."""
    guard.commit(receipts)


def make_asset_plan(snapshot_value, content, bundle, output, receipts):
    """Stage six fixed assets and a pending plan, never a success filename."""
    version = snapshot_value['producer'].version
    fixed = payloads(version)
    records = content['assets']
    need(type(records) is list and len(records) == 4
         and {item['name'] for item in records} == {item[0] for item in fixed}, 'invalid_asset_inventory')
    recorded = {item['name']: item for item in records}
    for name, family, media_type in fixed:
        item = recorded[name]
        need(item['family'] == family and item['media_type'] == media_type
             and type(item['size']) is int and item['size'] > 0, 'invalid_asset_record')
        output.copy(name, bundle.path / name)
        need((output.path / name).stat().st_size == item['size'] and hash_file(output.path / name) == item['sha256'],
             'staged_payload_changed')
    provenance = write_sanitized_provenance(snapshot_value, content, output)
    checksum_name = f'SHA256SUMS_{version}.txt'
    names = [name for name, _, _ in fixed] + ['RC_PROVENANCE.json']
    checksums = ''.join(f'{hash_file(output.path / name)}  {name}\n' for name in sorted(names))
    output.write(checksum_name, checksums.encode('utf-8'))
    final = (*fixed, ('RC_PROVENANCE.json', 'provenance', 'application/json'),
             (checksum_name, 'checksums', 'text/plain'))
    need(set(output.files()) == {item[0] for item in final}, 'invalid_staged_asset_inventory')
    assets = [dict(name=name, family=family, media_type=media_type,
                   size=(output.path / name).stat().st_size, sha256=hash_file(output.path / name))
              for name, family, media_type in final]
    plan = dict(provenance, assets=assets)
    # Only the sanitized copies are eligible for Actions upload. The payload
    # output is local and distinct from this receipt-only directory.
    receipts.copy('RC_PROVENANCE.json', output.path / 'RC_PROVENANCE.json')
    receipts.write('rc-asset-plan.pending', encode(plan))
    return plan


def _verify_bundle_bytes(root, api, selection, metadata, producer, download, bundle, cloud, *,
                         opener=None, deadline=None, check_active=None):
    budget = {} if deadline is None and check_active is None else dict(deadline=deadline, check_active=check_active)
    path = transport.download_artifact_zip(api, metadata, download, opener=opener, **budget)
    snapshot.revalidate_download(api, selection, metadata)
    archive.extract_bounded_zip(path, bundle, [name for name, _, _ in payloads(producer.version)], **budget)
    archive.verify_checksum_inventory(bundle, **budget)
    archive.extract_bounded_cloud_tar(bundle.path / 'cloud-linux-amd64.tar.gz', cloud, **budget)
    content = contracts.verify_consumed_bundle(root, bundle.path, cloud.path, producer, selection['integration'])
    download.files(); bundle.files(); cloud.files()
    return content


def consume(root, expectations, environment, api, *, temporary_parent=None, opener=None):
    """Live-authenticated production sequence. No offline snapshot CLI exists."""
    candidate = snapshot.resolve_candidate(root, expectations, environment, api)
    selection = snapshot.select_source_runs(api, candidate, expectations)
    metadata = snapshot.authenticate_bundle_metadata(api, selection, expectations['artifact_id'])
    producer = snapshot.derive_final_producer(candidate, selection, metadata)
    observation = dict(candidate=candidate, selection=selection, artifact=metadata, producer=producer)
    parent = temporary_parent or tempfile.gettempdir()
    guard = None
    try:
        with ExitStack() as final_roots:
            with ExitStack() as temporary_roots:
                def fresh(prefix):
                    return temporary_roots.enter_context(PrivateRoot(parent, prefix, source_root=root))
                download, bundle, cloud = (fresh(prefix) for prefix in
                    ('rc-consumer-download-', 'rc-consumer-bundle-', 'rc-consumer-cloud-'))
                content = _verify_bundle_bytes(root, api, selection, metadata, producer,
                                               download, bundle, cloud, opener=opener)
                output = fresh('rc-consumer-assets-')
                receipts = final_roots.enter_context(PrivateRoot(parent, 'rc-consumer-receipts-', source_root=root))
                plan = make_asset_plan(observation, content, bundle, output, receipts)
                guard = PlanCommit(receipts, encode(plan))
                result = dict(plan=plan, asset_directory=output.path, receipt_directory=receipts.path)
            # Large copies/hash/fsync and nonessential descriptor cleanup have
            # finished. Reobserve all live identities immediately before commit.
            snapshot.revalidate_snapshot(api, root, expectations, environment, observation)
            commit_success_plan(receipts, guard)
        return result
    except Exception as original:
        if guard is not None and guard.started:
            try:
                outcome = guard.withdraw()
            except Exception as withdrawal_error:
                failure = FinalizationFailure(original, 'uncertain')
                failure.withdrawal_error = withdrawal_error
                raise failure from original
            raise FinalizationFailure(original, outcome) from original
        raise


def decimal(value):
    if not re.fullmatch(r'[1-9][0-9]{0,19}', value):
        raise argparse.ArgumentTypeError('positive canonical decimal required')
    return int(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ('rc_version', 'release_tag', 'source_sha'):
        parser.add_argument('--' + field.replace('_', '-'), required=True)
    for field in ('final_run_id', 'final_run_attempt', 'integration_run_id', 'integration_run_attempt', 'artifact_id'):
        parser.add_argument('--' + field.replace('_', '-'), required=True, type=decimal)
    args = parser.parse_args()
    try:
        result = consume(Path(__file__).absolute().parents[1], vars(args), os.environ,
                         snapshot.GitHub(os.environ.get('GH_TOKEN', '')),
                         temporary_parent=os.environ.get('RUNNER_TEMP', tempfile.gettempdir()))
        return 0
    except Exception as error:
        code = error.code if isinstance(error, ConsumerError) else 'consumer_validation_failed'
        report = dict(passed=False, stage='consumer', error_code=code,
                      release_approved=False, publish_approved=False)
        if isinstance(error, FinalizationFailure):
            report.update(stage='finalization', plan_outcome=error.outcome,
                          plan_absent_confirmed=error.plan_absent_confirmed,
                          original_error_code=error.original_error_code)
        print(json.dumps(report))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
