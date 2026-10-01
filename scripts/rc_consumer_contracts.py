"""Authenticate data contracts inside an already API-digest-verified FINAL ZIP.

Only reviewed source helpers and fixed Git reads may run. No installer or cloud
binary is executed. Installed/native observations remain producer assertions,
not independently repeated acceptance or protection against a malicious producer.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import re

import cloud_release_bundle as cloud
import final_rc_evidence as final
import rc_native_gate as native
from rc_packages import debian_version
import release_dependency_contract as dependency
from rc_consumer_io import assert_private_tree, hash_file, json_file, need, read_bytes, read_prefix
from rc_consumer_noncloud import (approval_flags, audit_summary, digest_value, positive,
                                 producer_identity, schema, verify_consumed_noncloud_audits)

BLOCKERS = ('Windows production isolation security profile remains unresolved',
            'Full original release ledger and external release approval remain required')
PACKAGE_SCOPE = 'Exact package bytes and installed acceptance only'
DEPENDENCY_SCOPE = 'Exact cloud archive and per-lock dependency evidence; native/security gates remain separate'
CLOUD_SCOPE = 'Standalone cloud release binaries; no embedded configuration or credentials'
PAYLOAD_CONTRACT = ('https://github.com/tauri-apps/tauri/blob/tauri-cli-v2.11.4/'
                    'crates/tauri-bundler/src/bundle.rs')
MEDIA_TYPES = {'nsis': 'application/vnd.microsoft.portable-executable',
               'deb': 'application/vnd.debian.binary-package',
               'appimage': 'application/octet-stream', 'cloud': 'application/gzip'}


def identity(value, expected):
    schema(value)
    approval_flags(value)
    need(all(value.get(k) == v for k, v in expected.items()), 'content_identity_mismatch')
    need(value.get('passed') is True, 'content_not_passed')


def asset_record(directory, record, name, kind):
    need(type(record) is dict and set(record) == {'name', 'size', 'sha256'} and
         record.get('name') == name and positive(record.get('size')), 'invalid_package_record')
    digest = digest_value(record.get('sha256'))
    path = directory / name
    need(path.stat().st_size == record['size'] and hash_file(path) == digest, 'package_bytes_mismatch')
    return dict(name=name, family=kind, media_type=MEDIA_TYPES[kind], size=record['size'], sha256=digest)


def integration_receipt(path, producer, snapshot):
    value = json_file(path)
    schema(value)
    approval_flags(value)
    run, jobs = snapshot['run'], snapshot['jobs']
    need(positive(run.get('id')) and positive(run.get('run_attempt')) and
         run.get('head_sha') == producer.source_sha and type(jobs) is list and
         len(jobs) == len(final.REQUIRED_JOBS), 'invalid_integration_snapshot')
    selected = []
    for job in jobs:
        need(type(job) is dict and positive(job.get('id')) and
             type(job.get('name')) is str and job['name'] in final.REQUIRED_JOBS and
             type(job.get('run_id')) is int and job['run_id'] == run['id'] and
             type(job.get('run_attempt')) is int and job['run_attempt'] == run['run_attempt'] and
             job.get('head_sha') == producer.source_sha and job.get('status') == 'completed' and
             job.get('conclusion') == 'success', 'invalid_integration_snapshot')
        selected.append((job['id'], job['name']))
    need(len({j[0] for j in selected}) == len(jobs) and
         {j[1] for j in selected} == final.REQUIRED_JOBS, 'invalid_integration_snapshot')
    need(value.get('passed') is True and value.get('source_sha') == producer.source_sha and
         value.get('integration_run_id') == str(run['id']), 'stale_integration_receipt')
    recorded = value.get('jobs')
    need(type(recorded) is list and len(recorded) == len(jobs), 'integration_receipt_job_mismatch')
    need(all(type(j) is dict and set(j) == {'id', 'name'} and positive(j.get('id')) and
             type(j.get('name')) is str for j in recorded), 'integration_receipt_job_mismatch')
    need(sorted((j['id'], j['name']) for j in recorded) == sorted(selected),
         'integration_receipt_job_mismatch')


def verify_consumed_cloud(root, bundle_dir, cloud_dir, producer, integration_snapshot):
    expected = producer_identity(producer)
    nested = bundle_dir / 'evidence/rc-cloud-linux-amd64'
    versions = cloud.versions(root, producer.version)
    archive_identity = dict(source_sha=producer.source_sha, source_tree=producer.source_tree,
                            run_id=str(producer.run_id), product_version=producer.version,
                            component_versions=versions, target=cloud.TARGET)
    receipt = json_file(nested / 'archive-receipt.json')
    identity(receipt, archive_identity)
    need(receipt.get('publish_approved') is False, 'invalid_cloud_approval')
    name = 'cloud-linux-amd64.tar.gz'
    asset = asset_record(nested, receipt.get('archive'), name, 'cloud')
    need(asset_record(bundle_dir, receipt['archive'], name, 'cloud') == asset,
         'cloud_root_copy_mismatch')
    manifest = json_file(cloud_dir / 'manifest.json')
    schema(manifest, required=True)
    approval_flags(manifest)
    need(all(manifest.get(k) == v for k, v in archive_identity.items()) and
         manifest.get('build_os') == 'ubuntu-22.04' and manifest.get('publish_approved') is False and
         manifest.get('scope') == CLOUD_SCOPE, 'cloud_manifest_identity_mismatch')
    binaries = manifest.get('binaries')
    need(type(binaries) is dict and set(binaries) == set(cloud.BINS), 'cloud_binary_inventory_mismatch')
    for name in cloud.BINS:
        item = binaries[name]
        need(type(item) is dict and positive(item.get('size')), 'invalid_cloud_binary_record')
        digest_value(item.get('sha256'))
        path = cloud_dir / 'bin' / name
        need(path.stat().st_size == item['size'] and hash_file(path) == item['sha256'],
             'cloud_binary_bytes_mismatch')
        header = read_prefix(path, 20)
        need(len(header) == 20 and header[:6] == b'\x7fELF\x02\x01' and header[18:20] == b'\x3e\x00',
             'invalid_cloud_elf')
    integration_receipt(nested / 'integration.json', producer, integration_snapshot)
    evidence = nested / 'exact-build'
    # The digest is computed from bytes transitively authenticated by the API ZIP
    # digest. It is not an independently fetched producer job-output digest.
    envelope = json_file(evidence / 'envelope.json')
    schema(envelope, required=True)
    approval_flags(envelope)
    features = envelope.get('features')
    need(type(features) is dict and features.get('default') is True and features.get('all') is False,
         'invalid_cloud_feature_booleans')
    canonical = dependency.producer(producer.source_sha, str(producer.run_id),
                                    str(producer.run_attempt), producer.workflow_ref)
    need(envelope.get('ci') == canonical, 'wrong_cloud_build_producer')
    proof = dependency.verify_build(root, evidence, cloud_dir / 'bin', producer.version,
                                    producer.source_sha, cloud.TARGET, hash_file(evidence / 'envelope.json'),
                                    canonical)
    need(proof['tree'] == expected['source_tree'] and proof['binary_sha256'] ==
         {name: binaries[name]['sha256'] for name in cloud.BINS}, 'cloud_build_manifest_mismatch')
    return asset, dict(proof, archive_sha256=asset['sha256'], archive_size=asset['size'],
                       artifact_kind='release-cloud', archive_to_build_verified=True)


def native_receipt(path, producer, kind, digest):
    value = json_file(path)
    schema(value)
    approval_flags(value)
    duration = value.get('pending_elapsed_seconds')
    need(type(value.get('foreign_request_count')) is int and value['foreign_request_count'] == 100,
         'invalid_native_foreign_request_count')
    need(type(duration) in (int, float) and (type(duration) is int or math.isfinite(duration)) and duration >= 90,
         'invalid_native_duration')
    native.verify(value, source=producer.source_sha, run_id=str(producer.run_id),
                  version=producer.version, kind=kind, binary_sha256=digest)
    return dict(native_stages=12, real_chatgpt_verified=False, synthetic_conversation_metadata=True,
                installed_observations='authenticated_producer_assertions')


def windows_payload(path, producer, digest):
    value = json_file(path)
    schema(value)
    approval_flags(value)
    need(value.get('passed') is True and value.get('source_sha') in (None, producer.source_sha) and
         value.get('cli_version') == '2.11.4' and value.get('upstream_contract') == PAYLOAD_CONTRACT and
         value.get('allowed_change') == 'single UNK -> NSS bundle-type marker' and
         value.get('expected_installed_sha256') == digest and value.get('installed_sha256') == digest and
         'error' not in value, 'windows_payload_assertion_mismatch')
    digest_value(value.get('unbundled_sha256'))
    offset = value.get('marker_offset')
    need(type(offset) is int and 2 <= offset < 128 * 1024**2 and
         value['unbundled_sha256'] != digest, 'invalid_windows_payload_transform')
    observed = value.get('observed')
    need(type(observed) is list and 1 <= len(observed) <= 64, 'invalid_windows_payload_observations')
    paths, matches = set(), 0
    for item in observed:
        need(type(item) is dict and type(item.get('path')) is str and 0 < len(item['path']) <= 1024 and
             item['path'] not in paths and positive(item.get('bytes')) and item['bytes'] <= 128 * 1024**2,
             'invalid_windows_payload_observations')
        paths.add(item['path'])
        digest_value(item.get('sha256'))
        if item['sha256'] == digest:
            need(offset + len(b'__TAURI_BUNDLE_TYPE_VAR_NSS') <= item['bytes'],
                 'windows_payload_marker_out_of_bounds')
        matches += item['sha256'] == digest
    need(matches == 1, 'windows_payload_not_unique')


def verify_consumed_installers(bundle_dir, producer):
    expected = producer_identity(producer)
    evidence = bundle_dir / 'evidence'
    linux = evidence / 'rc-linux-packages'
    manifest = json_file(linux / 'exclusive-package.json')
    identity(manifest, expected)
    need(json_file(linux / 'build-platform.json') == {'id': 'ubuntu', 'version_id': '22.04'},
         'wrong_linux_build_platform')
    packages = manifest.get('packages')
    need(manifest.get('build_kind') == 'release-candidate' and type(packages) is dict and
         set(packages) == {'deb', 'appimage'}, 'invalid_linux_package_manifest')
    assets, installed = [], []
    for kind, suffix in (('deb', '.deb'), ('appimage', '.AppImage')):
        entry = packages[kind]
        need(type(entry) is dict and entry.get('architecture') == 'amd64', 'wrong_linux_architecture')
        payload = digest_value(entry.get('payload_sha256'))
        version = debian_version(producer.version) if kind == 'deb' else producer.version
        need(entry.get('package_version') == version, 'wrong_linux_package_version')
        if kind == 'deb':
            need(type(entry.get('package_id')) is str and
                 re.fullmatch('[a-z0-9][a-z0-9+.-]+', entry['package_id']), 'invalid_debian_package_id')
        else:
            need(entry.get('package_id') is None, 'invalid_appimage_package_id')
        name = f'MCP_{producer.version}_amd64{suffix}'
        asset = asset_record(linux, entry.get('artifact'), name, kind)
        need(asset_record(bundle_dir, entry['artifact'], name, kind) == asset, 'linux_root_copy_mismatch')
        assets.append(asset)
        for os_name in ('ubuntu-22.04', 'ubuntu-24.04'):
            folder = evidence / f'rc-linux-installed-{os_name}-{kind}'
            need(json_file(folder / 'installed-platform.json') ==
                 {'id': 'ubuntu', 'version_id': os_name.removeprefix('ubuntu-')}, 'wrong_installed_platform')
            value = json_file(folder / 'rc-package.json')
            identity(value, expected)
            binary = payload if kind == 'deb' else asset['sha256']
            need(value.get('kind') == kind and value.get('package') == entry['artifact'] and
                 type(value['package'].get('size')) is int and value.get('package_version') == version and
                 value.get('payload_sha256') == payload and value.get('native_executable_sha256') == binary,
                 'installed_linux_payload_mismatch')
            observations = native_receipt(folder / 'exclusive-native.json', producer, kind, binary)
            installed.append(dict(platform=os_name, kind=kind, **observations))
    windows = evidence / 'rc-windows-package'
    value = json_file(windows / 'rc-windows-package.json')
    identity(value, expected)
    need(value.get('kind') == 'nsis' and value.get('scenario') == 'exclusive-refresh-v1' and
         all(value.get(k) is True for k in ('release_candidate', 'silent_install', 'exact_nsis_payload_verified',
             'real_native_approval', 'synthetic_conversation_metadata')) and
         value.get('real_chatgpt_verified') is False and value.get('publish_approved') is False and
         type(value.get('signed')) is bool, 'invalid_windows_acceptance_boundary')
    payload = digest_value(value.get('payload_sha256'))
    need(value.get('native_executable_sha256') == payload, 'windows_native_payload_mismatch')
    name = f'MCP_{producer.version}_x64-setup.exe'
    asset = asset_record(windows, value.get('package'), name, 'nsis')
    need(asset_record(bundle_dir, value['package'], name, 'nsis') == asset, 'windows_root_copy_mismatch')
    windows_payload(windows / '安装载荷核验v7.json', producer, payload)
    observations = native_receipt(windows / 'exclusive-native.json', producer, 'nsis', payload)
    installed.append(dict(platform='windows-2025', kind='nsis', **observations))
    return [asset, *assets], installed, dict(windows_payload_signature_observed=value['signed'])


def verify_consumed_bundle(root, bundle_dir, cloud_dir, producer, integration_snapshot):
    """Return only fixed, typed public summaries after recomputing all contracts."""
    expected = producer_identity(producer)
    need(not bundle_dir.resolve().is_relative_to(root.resolve()) and
         not cloud_dir.resolve().is_relative_to(root.resolve()), 'content_must_be_outside_source')
    files = assert_private_tree(bundle_dir)
    assert_private_tree(cloud_dir)
    report = json_file(bundle_dir / 'packaging-report.json')
    identity(report, expected)
    approval_flags(report, required=True)
    need(report.get('scope') == PACKAGE_SCOPE and report.get('release_blockers') == list(BLOCKERS),
         'invalid_packaging_scope_or_blockers')
    contracts = bundle_dir / 'evidence/rc-package-contracts'
    contract_identity = json_file(contracts / 'identity.json')
    identity(contract_identity, expected)
    need(contract_identity.get('evidence_inventory') == final.evidence_inventory(contracts),
         'contract_inventory_mismatch')
    integration_receipt(contracts / 'integration.json', producer, integration_snapshot)
    cloud_asset, cloud_proof = verify_consumed_cloud(root, bundle_dir, cloud_dir, producer, integration_snapshot)
    need(read_bytes(contracts / 'rust-audit-cloud-gateway.json') ==
         read_bytes(bundle_dir / 'evidence/rc-cloud-linux-amd64/exact-build/raw-audit.json'),
         'canonical_raw_cloud_audit_mismatch')
    npm = json_file(contracts / 'npm-audit.json')
    counts = npm.get('metadata', {}).get('vulnerabilities')
    need('error' not in npm and type(counts) is dict and 'total' in counts and
         set(counts) <= {'total', 'info', 'low', 'moderate', 'high', 'critical'} and
         all(type(count) is int and count == 0 for count in counts.values()), 'invalid_npm_zero_audit')
    noncloud = verify_consumed_noncloud_audits(root, contracts, producer)
    computed = dict(noncloud=noncloud, cloud=cloud_proof, raw_zero_claim=False,
                    release_approved=False, publish_approved=False, scope=DEPENDENCY_SCOPE)
    # JSON type distinctions matter: Python considers False == 0 == 0.0.
    canonical = json.dumps(computed, sort_keys=True, allow_nan=False)
    need(json.dumps(report.get('dependency_contract'), sort_keys=True, allow_nan=False) == canonical and
         json.dumps(contract_identity.get('dependency_contract'), sort_keys=True, allow_nan=False) == canonical,
         'recorded_dependency_contract_mismatch')
    assets, installed, signing = verify_consumed_installers(bundle_dir, producer)
    assets.append(cloud_asset)
    expected_root = {a['name'] for a in assets} | {'packaging-report.json', 'SHA256SUMS.txt'}
    need({name for name in files if '/' not in name} == expected_root, 'unexpected_root_payload')
    return dict(assets=assets, installed_platforms=installed,
                audits=dict(cloud=audit_summary(cloud_proof),
                            noncloud={name: audit_summary(value) for name, value in sorted(noncloud.items())},
                            npm_vulnerability_count=0, raw_zero_claim=False),
                signing=signing, release_blockers=list(BLOCKERS), raw_zero_claim=False,
                release_approved=False, publish_approved=False)
