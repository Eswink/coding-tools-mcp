"""Owned, exact selected consumer receipts and FINAL bytes; no publication authority."""
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import stat
import struct
import zlib
import zipfile

import rc_artifact_consumer as consumer
import rc_consumer_archive as archive
import rc_consumer_snapshot as snapshot
from rc_consumer_io import CHUNK, FILE_LIMIT, JSON_LIMIT, ConsumerError, PrivateRoot, json_file, need, open_file
from rc_publication_contract import Asset, AssetPlanView, PublicationSubject

RECEIPT_LIMIT = 64 * 1024**2
CONSUME_JOB = 'Read-only authenticated FINAL bytes and sanitized plan'
NAMES = {'RC_PROVENANCE.json', 'rc-asset-plan.json'}


@dataclass(frozen=True)
class Selection:
    subject: PublicationSubject
    consumer_artifact_id: int
    consumer_artifact_size: int
    consumer_artifact_sha256: str

    def __post_init__(self):
        need(type(self.subject) is PublicationSubject, 'invalid_publication_selection')
        self.subject.__post_init__()
        for run in self.subject.runs:
            run.__post_init__()
        self.subject.source.__post_init__()
        need(type(self.consumer_artifact_id) is int and 0 < self.consumer_artifact_id < 2**63
             and self.consumer_artifact_id != self.subject.artifact_id, 'invalid_receipt_id')
        need(type(self.consumer_artifact_size) is int and 0 < self.consumer_artifact_size <= RECEIPT_LIMIT,
             'invalid_receipt_size')
        need(type(self.consumer_artifact_sha256) is str
             and re.fullmatch('[0-9a-f]{64}', self.consumer_artifact_sha256), 'invalid_receipt_digest')


def _source(root, subject, api):
    gate, source = snapshot.gate, subject.source
    gate.rc.verify_source(root, expected_sha=source.source_sha, expected_version=source.version)
    need(not gate.reviewed.git(root, 'ls-files', '--others', '-z'), 'untracked_source')
    gate.cloud.versions(root, source.version)
    reviewed = gate.reviewed.verify(root, source.source_sha)
    need(reviewed['source_tree'] == source.source_tree, 'source_tree_mismatch')
    need(gate.reviewed.git(root, 'rev-parse', '--verify', 'refs/tags/' + subject.tag).decode().strip()
         == subject.tag_object_sha and gate.reviewed.git(root, 'cat-file', '-t', 'refs/tags/' + subject.tag)
         == b'commit\n', 'lightweight_tag_required')
    for invocation in subject.runs:
        blob = gate.reviewed.blob(root, source.source_sha, invocation.workflow_path)
        need(blob is not None and blob['mode'] == '100644' and blob['blob_sha'] == invocation.workflow_blob,
             'workflow_blob_mismatch')
    snapshot._live_tag(api, subject.tag, source.source_sha)


def _bind(evidence, invocation, ids):
    run = evidence['run']
    need((run['id'], run['run_attempt'], run['workflow_id'], run['path'], run['head_sha'], run['event'])
         == (invocation.run_id, invocation.run_attempt, invocation.workflow_id, invocation.workflow_path,
             invocation.source.source_sha, invocation.event), 'selected_run_mismatch')
    # This executor supports post-merge branch/tag runs; PR merge refs fail closed.
    need(invocation.ref == 'refs/heads/' + run['head_branch'] or
         invocation.ref == 'refs/tags/' + run['head_branch'], 'selected_ref_mismatch')
    need(tuple(sorted(j['id'] for j in evidence['jobs'])) == tuple(sorted(ids)), 'selected_jobs_mismatch')


def _observe(root, selected, api):
    s, gate = selected.subject, snapshot.gate
    _source(root, s, api)
    f, i, c = s.runs
    expected = dict(rc_version=s.source.version, release_tag=s.tag, source_sha=s.source.source_sha,
        final_run_id=f.run_id, final_run_attempt=f.run_attempt, integration_run_id=i.run_id,
        integration_run_attempt=i.run_attempt, artifact_id=s.artifact_id)
    runs = snapshot._select_source_runs_for_identity(api, s.source.source_sha, s.source.repository_id, expected)
    for name, invocation, ids in zip(('final_packaging', 'integration'), (f, i), s.job_ids):
        _bind(runs[name], invocation, ids)
    artifact = snapshot.authenticate_bundle_metadata(api, runs, s.artifact_id)
    need((artifact['size_in_bytes'], artifact['digest']) == (s.artifact_size, 'sha256:' + s.artifact_sha256),
         'selected_artifact_mismatch')
    workflow = api.get('/actions/workflows/' + Path(c.workflow_path).name)
    need(type(workflow) is dict and type(workflow.get('id')) is int
         and (workflow['id'], workflow.get('path')) == (c.workflow_id, c.workflow_path), 'consumer_workflow_mismatch')
    run = api.get(f'/actions/runs/{c.run_id}')
    gate.run_identity(run, workflow, s.source.source_sha)
    need(run.get('status') == 'completed' and run.get('conclusion') == 'success', 'consumer_not_successful')
    jobs = gate.paginate(api, f'/actions/runs/{c.run_id}/attempts/{c.run_attempt}/jobs', 'jobs')
    need(len(jobs) == 1 and jobs[0].get('name') == CONSUME_JOB, 'consumer_job_inventory')
    job = jobs[0]
    need(type(job.get('run_id')) is int and job['run_id'] == c.run_id
         and type(job.get('run_attempt')) is int and job['run_attempt'] == c.run_attempt
         and job.get('head_sha') == s.source.source_sha and job.get('status') == 'completed'
         and job.get('conclusion') == 'success', 'consumer_job_mismatch')
    consumed = snapshot._strict_run(dict(run=run, workflow=workflow, jobs=jobs), s.source.repository_id,
                                    s.source.source_sha, c.run_id, c.run_attempt)
    _bind(consumed, c, s.job_ids[2])
    for suffix in (f'/actions/runs/{c.run_id}/attempts/{c.run_attempt}', f'/actions/runs/{c.run_id}'):
        need(snapshot._run(api.get(suffix), s.source.repository_id) == consumed['run'], 'consumer_run_changed')
    name = f'rc-artifact-consumer-sanitized-{c.run_id}-{c.run_attempt}'
    matches = [a for a in gate.paginate(api, f'/actions/runs/{c.run_id}/artifacts', 'artifacts') if a.get('name') == name]
    need(len(matches) == 1, 'receipt_inventory_mismatch')
    raw = api.get(f'/actions/artifacts/{selected.consumer_artifact_id}')
    need(type(raw) is dict and raw == matches[0], 'receipt_metadata_changed')
    need(type(raw.get('id')) is int and raw['id'] == selected.consumer_artifact_id and raw.get('name') == name
         and type(raw.get('size_in_bytes')) is int and raw['size_in_bytes'] == selected.consumer_artifact_size
         and raw.get('digest') == 'sha256:' + selected.consumer_artifact_sha256 and raw.get('expired') is False,
         'receipt_artifact_mismatch')
    owner = dict(id=c.run_id, repository_id=s.source.repository_id, head_repository_id=s.source.repository_id,
                 head_sha=s.source.source_sha, head_branch=run['head_branch'])
    need(type(raw.get('workflow_run')) is dict and all(type(raw['workflow_run'].get(k)) is type(v)
         and raw['workflow_run'][k] == v for k, v in owner.items()), 'receipt_owner_mismatch')
    created, updated, expires = (snapshot._time(raw.get(k)) for k in ('created_at', 'updated_at', 'expires_at'))
    need(snapshot._time(job['started_at']) <= created <= updated <= snapshot._time(job['completed_at'])
         and expires > max(updated, datetime.now(timezone.utc)), 'receipt_time_mismatch')
    metadata = {k: raw[k] for k in snapshot.ARTIFACT_FIELDS}
    metadata['workflow_run'] = owner
    return runs, artifact, consumed, metadata


def _receipts(path, destination):
    try:
        with open_file(path) as stream:
            need(os.fstat(stream.fileno()).st_size <= RECEIPT_LIMIT, 'receipt_zip_limit')
            directory = archive._directory_guard(stream)
            need(directory['count'] in (2, 3), 'receipt_member_count')
            with zipfile.ZipFile(stream) as source:
                infos, names, prefix, files = source.infolist(), archive._Names(), None, set()
                need(len(infos) == directory['count'] and source.start_dir == directory['offset'], 'zip_directory_count')
                for info in infos:
                    name = names.add(info.orig_filename, info.is_dir())
                    parts = name.split('/')
                    need(re.fullmatch(r'rc-consumer-receipts-[A-Za-z0-9_-]{1,64}', parts[0])
                         and (prefix is None or prefix == parts[0]), 'receipt_prefix')
                    prefix = parts[0]
                    need((info.is_dir() and len(parts) == 1 and info.file_size == 0) or
                         (not info.is_dir() and len(parts) == 2 and parts[1] in NAMES), 'receipt_layout')
                    kind = stat.S_IFMT(info.external_attr >> 16)
                    need(kind in ({0, stat.S_IFDIR} if info.is_dir() else {0, stat.S_IFREG})
                         and not (info.external_attr & 0xffff & ~0x37)
                         and (not info.external_attr & 0x10 or info.is_dir()), 'zip_special_member')
                    need(info.flag_bits & ~0x80e == 0 and info.compress_type in (0, 8)
                         and info.extract_version <= 45 and info.volume == 0
                         and 0 <= info.file_size <= JSON_LIMIT and 0 <= info.compress_size <= RECEIPT_LIMIT
                         and info.file_size <= max(1, info.compress_size) * archive.RATIO_LIMIT, 'receipt_member_limit')
                    if not info.is_dir():
                        files.add(parts[1])
                need(files == NAMES, 'receipt_inventory_mismatch')
                archive._local_records(stream, infos, directory['offset'])
                for info in infos:
                    archive._deflate_integrity(stream, info)
                    with source.open(info) as member:
                        data = member.read(JSON_LIMIT + 1)
                        need(len(data) == info.file_size, 'receipt_member_size')
                        if not info.is_dir():
                            destination.write(info.filename.split('/')[1], data)
    except (OSError, zipfile.BadZipFile, NotImplementedError, UnicodeError, zlib.error, struct.error):
        raise ConsumerError('invalid_receipt_zip') from None


def _provenance(s, observation, content, value):
    runs, artifact, consumed, _ = observation
    f, i, c = s.runs
    producer = snapshot.derive_final_producer(dict(source_sha=s.source.source_sha,
        source_tree=s.source.source_tree, version=s.source.version), runs, artifact)
    moment = snapshot._time(value.get('verified_at'))
    job = consumed['jobs'][0]
    need(snapshot._time(job['started_at']) <= moment <= snapshot._time(job['completed_at']), 'receipt_clock_mismatch')
    expected = dict(schema=1, passed=True, scope=consumer.SCOPE, snapshot_atomic=False,
        release_approved=False, publish_approved=False,
        source=dict(sha=s.source.source_sha, tree=s.source.source_tree, version=s.source.version,
                    release_tag=s.tag, tag_object_sha=s.tag_object_sha),
        repository=dict(full_name=s.source.repository, id=s.source.repository_id),
        producer=dict(run_id=f.run_id, run_attempt=f.run_attempt, workflow_ref=f.workflow_ref,
            workflow_id=f.workflow_id, bundle_job_id=producer.bundle_job_id,
            bundle_job_started_at=producer.bundle_job_started_at, bundle_job_completed_at=producer.bundle_job_completed_at),
        integration=dict(run_id=i.run_id, run_attempt=i.run_attempt),
        artifact=dict(id=s.artifact_id, sha256=s.artifact_sha256, size=s.artifact_size, artifact_bytes_verified=True),
        consumer=dict(run_id=c.run_id, run_attempt=c.run_attempt, workflow_ref=c.workflow_ref, source_sha=s.source.source_sha),
        verified_at=value['verified_at'], installed_platforms=[dict(platform=r['platform'], kind=r['kind'],
            native_stages=12, real_chatgpt_verified=False, synthetic_conversation_metadata=True,
            observations='authenticated_producer_assertions') for r in sorted(content['installed_platforms'],
                key=lambda r: (r['platform'], r['kind']))],
        audits=dict(cloud=consumer.audit(content['audits']['cloud']),
            noncloud={k: consumer.audit(v) for k, v in content['audits']['noncloud'].items()},
            npm_vulnerability_count=0, raw_zero_claim=False),
        signing=dict(windows_payload_signature_observed=content['signing']['windows_payload_signature_observed'],
                     consumer_signing_verified=False), release_blockers=list(consumer.contracts.BLOCKERS),
        limitations=list(consumer.LIMITATIONS))
    need(consumer.encode(value) == consumer.encode(expected), 'provenance_binding_mismatch')
    return producer


class StagedAssets:
    def __init__(self, root, selection, api, temporary_parent):
        need(type(selection) is Selection, 'invalid_publication_selection')
        self._selection = deepcopy(selection)
        self._selection.__post_init__()
        self.subject, self._root, self._api = self._selection.subject, Path(root), api
        self._parent, self._stack, self._roots, self._handles = temporary_parent, ExitStack(), [], []
        self._entered = self._closed = False

    def __enter__(self):
        need(not self._entered and not self._closed, 'stage_lifetime')
        self._entered = True
        try:
            self._observation = snapshot._call(_observe, self._root, self._selection, self._api)
            def fresh():
                root = self._stack.enter_context(PrivateRoot(self._parent, 'rc-publisher-', source_root=self._root))
                self._roots.append(root)
                return root
            receipt_download, receipts, download, bundle, cloud, self._output = (fresh() for _ in range(6))
            path = consumer.transport.download_artifact_zip(self._api, self._observation[3], receipt_download)
            snapshot._call(_receipts, path, receipts)
            self.plan_bytes, self.provenance_bytes = (receipts.read(name) for name in ('rc-asset-plan.json', 'RC_PROVENANCE.json'))
            need(hashlib.sha256(self.plan_bytes).hexdigest() == self.subject.plan_sha256, 'original_plan_digest_mismatch')
            plan, provenance = (json_file(receipts.path / name) for name in ('rc-asset-plan.json', 'RC_PROVENANCE.json'))
            runs, metadata, _, _ = self._observation
            producer = snapshot.derive_final_producer(dict(source_sha=self.subject.source.source_sha,
                source_tree=self.subject.source.source_tree, version=self.subject.source.version), runs, metadata)
            content = consumer._verify_bundle_bytes(self._root, self._api, runs, metadata, producer, download, bundle, cloud)
            snapshot._call(_provenance, self.subject, self._observation, content, provenance)
            fixed = (*consumer.payloads(producer.version), ('RC_PROVENANCE.json', 'provenance', 'application/json'),
                     (f'SHA256SUMS_{producer.version}.txt', 'checksums', 'text/plain'))
            for name, _, _ in fixed[:4]:
                self._output.copy(name, bundle.path / name)
            self._output.write('RC_PROVENANCE.json', self.provenance_bytes)
            checksums = ''.join(f'{consumer.hash_file(self._output.path / name)}  {name}\n' for name in sorted(self._output.files()))
            self._output.write(fixed[-1][0], checksums.encode())
            rows = [dict(name=n, family=f, media_type=m, size=(self._output.path / n).stat().st_size,
                         sha256=consumer.hash_file(self._output.path / n)) for n, f, m in fixed]
            need(consumer.encode(plan) == consumer.encode(dict(provenance, assets=rows)), 'original_plan_binding_mismatch')
            self.plan = AssetPlanView(tuple(Asset(**row) for row in rows))
            self._handles = [self._stack.enter_context(self._output.open(row.name)) for row in self.plan.assets]
            self._identities = tuple((os.fstat(h.fileno()).st_dev, os.fstat(h.fileno()).st_ino) for h in self._handles)
            self.revalidate()
            return self
        except BaseException:
            self.close()
            raise

    def revalidate(self):
        need(self._entered and not self._closed, 'stage_lifetime')
        need(snapshot._call(_observe, self._root, self._selection, self._api) == self._observation, 'selection_changed')
        for root in self._roots:
            root.files()
        need(set(self._output.files()) == {a.name for a in self.plan.assets}, 'staged_inventory_changed')
        for index, (handle, row) in enumerate(zip(self._handles, self.plan.assets)):
            self._check_handle(index)
            handle.seek(0)
            digest, total = hashlib.sha256(), 0
            while data := handle.read(CHUNK):
                total += len(data)
                need(total <= row.size, 'staged_size_changed')
                digest.update(data)
            need(total == row.size and digest.hexdigest() == row.sha256, 'staged_hash_changed')
            handle.seek(0)
        return self.plan.assets

    def _check_handle(self, ordinal):
        root_fd = self._output._root()
        try:
            row, handle = self.plan.assets[ordinal], self._handles[ordinal]
            info, path = os.fstat(handle.fileno()), os.stat(row.name, dir_fd=root_fd, follow_symlinks=False)
            need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size == row.size <= FILE_LIMIT
                 and info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o600
                 and (info.st_dev, info.st_ino) == self._identities[ordinal] == (path.st_dev, path.st_ino), 'staged_handle_changed')
        finally:
            os.close(root_fd)

    def stream(self, ordinal):
        need(type(ordinal) is int and 0 <= ordinal < 6 and self._entered and not self._closed, 'invalid_stage_stream')
        handle = self._handles[ordinal]
        need(not handle.closed, 'staged_handle_changed')
        self._check_handle(ordinal)
        handle.seek(0)
        return handle

    def close(self):
        if not self._closed:
            self._closed = True
            self._stack.close()

    def __exit__(self, *_):
        self.close()


def stage_selected(root, selection, api, *, temporary_parent):
    return StagedAssets(root, selection, api, temporary_parent)
