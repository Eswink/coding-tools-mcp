"""Bounded allowlisted observations; never a transferable release capability."""
from dataclasses import asdict, dataclass
import asyncio
import hashlib
import json
import subprocess

import rc_artifact_consumer as consumer
from rc_consumer_io import ConsumerError, need
from rc_consumer_snapshot import TrustedProducer
from rc_pretag_types import encode as contract_encode
from rc_release_eligibility import evaluate

SUCCESS_LIMIT, FAILURE_LIMIT, PATH_LIMIT = 262144, 8192, 4096
NAME = 'rc-pretag-observation.json'
STAGE_CODES = dict(invocation='pretag_context_rejected', source='pretag_source_rejected',
    tag_visibility='pretag_tag_visibility_failed', selection='pretag_selection_rejected',
    artifact='pretag_artifact_rejected', transport='pretag_transport_failed',
    archive='pretag_archive_rejected', contracts='pretag_contract_rejected',
    freshness='pretag_freshness_rejected', output='pretag_output_failed',
    output_handoff='pretag_output_handoff_failed')
CODES = frozenset(STAGE_CODES.values()) | frozenset({'pretag_tag_collision',
    'pretag_tag_response_invalid', 'transport_deadline_exceeded', 'transport_cleanup_uncertain',
    'pretag_output_limit', 'pretag_cancelled', 'pretag_internal_error'})
FALSE_FLAGS = dict(release_approved=False, publish_approved=False, security_approved=False,
                   finalized=False, snapshot_atomic=False)


def _bytes(value, limit):
    raw = (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')
    need(len(raw) <= limit, 'pretag_output_limit')
    return raw


class Failure(Exception):
    """Fixed output vocabulary; later failures never mask uncertain teardown."""
    def __init__(self, stage, error):
        self.stage, self.code, self.secondary = 'invocation', 'pretag_internal_error', []
        self.unknown = False
        self.record(stage, error, initial=True)
        super().__init__(self.code)

    def record(self, stage, error, initial=False):
        context = error
        for _ in range(16):
            self.unknown |= isinstance(context, (TimeoutError, subprocess.TimeoutExpired))
            context = getattr(context, '__cause__', None) or getattr(context, '__context__', None)
            if context is None: break
        if isinstance(error, Failure):
            codes, stage = [error.code, *error.secondary], error.stage
            self.unknown |= error.unknown
        else:
            stage = stage if stage in STAGE_CODES else 'invocation'
            code = getattr(error, 'code', None)
            code = code if type(code) is str and code in CODES else STAGE_CODES[stage]
            if isinstance(error, (KeyboardInterrupt, SystemExit, asyncio.CancelledError)):
                code = 'pretag_cancelled'
            self.unknown |= isinstance(error, TimeoutError) or code in (
                'pretag_cancelled', 'transport_deadline_exceeded', 'transport_cleanup_uncertain')
            codes = [code]
            if code in STAGE_CODES.values(): stage = next(k for k, v in STAGE_CODES.items() if v == code)
            if code in ('pretag_tag_collision', 'pretag_tag_response_invalid'): stage = 'tag_visibility'
        for code in codes:
            if code == 'transport_cleanup_uncertain':
                prior = self.code
                self.stage, self.code, self.unknown = 'transport', code, True
                if not initial and prior != code and prior not in self.secondary:
                    self.secondary.append(prior)
            elif initial and self.code != 'transport_cleanup_uncertain':
                self.stage, self.code = stage, code
                initial = False
            elif code != self.code and code not in self.secondary:
                self.secondary.append(code)
        self.secondary = self.secondary[:4]

    def encode(self):
        return _bytes(dict(schema='rc-pretag-failure-v1', passed=False, stage=self.stage,
            error_code=self.code, secondary_error_codes=self.secondary,
            terminal_state='unknown' if self.unknown else 'failed', cleanup_confirmed=False,
            **FALSE_FLAGS), FAILURE_LIMIT)


@dataclass(frozen=True, init=False)
class CollectedPreTagEvidence:
    """No decoder/import path. Not isolation against arbitrary Python execution."""
    _raw: bytes
    _digest: str

    def __init__(self):
        raise ConsumerError('pretag_context_rejected')


@dataclass(frozen=True)
class _PreparedObservation:
    value: dict


def _summarize(admitted, selection, producer, content):
    from rc_pretag_admission import Admitted
    need(type(admitted) is Admitted and type(producer) is TrustedProducer, 'pretag_context_rejected')
    contract_encode(admitted.candidate)  # Revalidate nested immutable schema, even if force-mutated.
    consumer.contracts.producer_identity(producer)
    need((producer.source_sha, producer.source_tree, producer.version, producer.repository_id) ==
         (admitted.source.source_sha, admitted.source.source_tree, admitted.source.version,
          admitted.source.repository_id), 'pretag_source_rejected')
    need(content['release_approved'] is False and content['publish_approved'] is False
         and content['raw_zero_claim'] is False, 'pretag_contract_rejected')
    rows = content['installed_platforms']
    need(type(rows) is list and len(rows) == 5 and {(r['platform'], r['kind']) for r in rows}
         == consumer.PLATFORMS, 'pretag_contract_rejected')
    installed = []
    for row in sorted(rows, key=lambda r: (r['platform'], r['kind'])):
        need(type(row['native_stages']) is int and row['native_stages'] == 12
             and row['real_chatgpt_verified'] is False and row['synthetic_conversation_metadata'] is True,
             'pretag_contract_rejected')
        installed.append(dict(platform=row['platform'], kind=row['kind'], native_stages=12,
            real_chatgpt_verified=False, synthetic_conversation_metadata=True,
            observations='authenticated_producer_assertions'))
    records = content['assets']
    fixed = consumer.payloads(producer.version)
    need(type(records) is list and len(records) == 4 and {a['name'] for a in records}
         == {r[0] for r in fixed}, 'pretag_contract_rejected')
    assets = []
    for name, family, media in fixed:
        record = next(a for a in records if a['name'] == name)
        need(record['family'] == family and record['media_type'] == media
             and type(record['size']) is int and 0 < record['size'] <= consumer.snapshot.MAX_ARTIFACT_BYTES,
             'pretag_contract_rejected')
        consumer.contracts.digest_value(record['sha256'])
        assets.append(dict(name=name, family=family, media_type=media, size=record['size'], sha256=record['sha256']))
    audits = content['audits']
    need(audits['raw_zero_claim'] is False and type(audits['npm_vulnerability_count']) is int
         and audits['npm_vulnerability_count'] == 0 and set(audits['noncloud']) ==
         {'desktop', 'cloud-agent', 'local-agent'}, 'pretag_contract_rejected')
    signing = content['signing']['windows_payload_signature_observed']
    need(type(signing) is bool and content['release_blockers'] == list(consumer.contracts.BLOCKERS),
         'pretag_contract_rejected')
    integration = selection['integration']
    need(integration['run']['head_sha'] == producer.source_sha and selection['repository_id']
         == producer.repository_id, 'pretag_selection_rejected')
    policy = evaluate(admitted.candidate, ())
    value = dict(schema='rc-pretag-observation-v1', scope='authenticated-pretag-final-bytes-only', passed=True,
        **FALSE_FLAGS, published_candidate=False, publication_atomic=False, eligibility='blocked',
        source=asdict(admitted.source), invocation=asdict(admitted.invocation),
        active_job=dict(id=admitted.job_id, name='Collect pre-tag FINAL evidence (release remains blocked)',
                        run_id=admitted.invocation.run_id, run_attempt=admitted.invocation.run_attempt),
        producer=asdict(producer), integration=dict(run_id=integration['run']['id'],
            run_attempt=integration['run']['run_attempt'], job_ids=[j['id'] for j in integration['jobs']]),
        artifact=dict(id=producer.artifact_id, sha256=producer.artifact_sha256, size=producer.artifact_size,
                      artifact_bytes_verified=True), assets=assets, installed_platforms=installed,
        audits=dict(cloud=consumer.audit(audits['cloud']),
            noncloud={n: consumer.audit(audits['noncloud'][n]) for n in sorted(audits['noncloud'])},
            npm_vulnerability_count=0, raw_zero_claim=False),
        signing=dict(windows_payload_signature_observed=signing, consumer_signing_verified=False),
        local_tag_absent=True, remote_tag_observation='unknown', remote_tag_visibility=admitted.candidate.tag_visibility,
        legacy_unimplemented_eligibility_policy=dict(status=policy.status, rows=[asdict(r) for r in policy.rows]),
        release_blockers=list(consumer.contracts.BLOCKERS), limitations=[
            'Read-only bounded observation; no release, publication, security or independent review approval',
            'Remote tag absence and draft visibility remain unknown; local absence is not global absence',
            'Installed/native outcomes are authenticated producer assertions, not independent execution',
            'Private descriptor close is not deletion; runner-lifetime payload residue may remain',
            'No whole-CLI deadline or synchronous OS preemption guarantee; platform timeout is outer control',
            'Canceled/failed collection, upload, job or run cannot authenticate a retained observation',
            'No atomic snapshot, reproducibility, signing, Windows isolation or real ChatGPT acceptance'])
    return _PreparedObservation(value)


def _collect(prepared):
    need(type(prepared) is _PreparedObservation, 'pretag_context_rejected')
    raw = _bytes(prepared.value, SUCCESS_LIMIT)
    record = object.__new__(CollectedPreTagEvidence)
    object.__setattr__(record, '_raw', raw)
    object.__setattr__(record, '_digest', hashlib.sha256(raw).hexdigest())
    return record


def encode(record):
    need(type(record) is CollectedPreTagEvidence and type(record._raw) is bytes
         and len(record._raw) <= SUCCESS_LIMIT and type(record._digest) is str
         and hashlib.sha256(record._raw).hexdigest() == record._digest, 'pretag_output_failed')
    return record._raw
