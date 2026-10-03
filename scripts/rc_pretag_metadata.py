"""Bounded read-only metadata observations. Never grants release authority."""
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import re

from rc_pretag_types import REPOSITORY, REPOSITORY_ID, WORKFLOWS, encode, timestamp
from rc_pretag_evidence import INTEGRATION_JOBS, FINAL_JOBS
from rc_pretag_metadata_types import (MetadataRequest, MetadataRecord,
                                      MetadataObservation, MetadataReceipt, OBSERVATION_KEYS)
from rc_pretag_metadata_api import (MetadataGitHub, MetadataAPIError,
                                    CleanupUncertain, link_relations)

STATES = frozenset(('queued', 'requested', 'waiting', 'pending', 'in_progress', 'completed'))
CONCLUSIONS = frozenset(('success', 'failure', 'cancelled', 'skipped', 'timed_out',
                        'action_required', 'neutral', 'stale', 'startup_failure'))
REVIEWS = frozenset(('APPROVED', 'DISMISSED', 'CHANGES_REQUESTED', 'PENDING', 'COMMENTED'))
TERMINAL_ERRORS = frozenset(('request_limit', 'aggregate_limit', 'session_timeout',
    'request_timeout', 'worker_failed', 'worker_start_failed', 'invalid_ipc', 'adapter_closed',
    'close_failure', 'tls_failure', 'transport_failure', 'response_limit'))


class CollectionError(ValueError):
    """Internal fixed-code classification; API text is never an error message."""


def need(condition, code='invalid_metadata'):
    if not condition:
        raise CollectionError(code)


def positive(value):
    return type(value) is int and 0 < value < 2**63


def digest(operation, value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'),
                     ensure_ascii=False, allow_nan=False).encode('utf-8')
    return hashlib.sha256(b'rc-pretag-metadata-v1/compare/' + operation.encode('ascii')
                          + b'\0' + raw).hexdigest()


def sha(value):
    need(type(value) is str and re.fullmatch('[0-9a-f]{40}', value) is not None)
    return value


def bounded_text(value, limit=512):
    need(type(value) is str and len(value) <= limit)
    return value


def moment(value, optional=False):
    if optional and value is None:
        return None
    try:
        timestamp(value)
    except (ValueError, TypeError):
        raise CollectionError('invalid_metadata') from None
    return value


def repository(value):
    need(type(value) is dict and value.get('full_name') == REPOSITORY
         and type(value.get('id')) is int and value['id'] == REPOSITORY_ID,
         'repository_mismatch')


def state(value, choices):
    if value is None:
        return None, None
    bounded_text(value)
    return (value, None) if value in choices else ('unknown', digest('unknown-field', value))


def observation(key, values, records=(), reason='observed', status='observed'):
    return MetadataObservation(key=key, state=status, reason=reason, count=len(values),
        comparison_sha256=digest(key, {'state': status, 'reason': reason, 'complete': True,
                                      'records': values}), records=tuple(records))


class Collector:
    def __init__(self, request, api):
        self.request, self.api = request, api
        self.stopped = False
        self.items = {}
        self.source_key = 'repository'

    def get(self, operation, **args):
        if self.stopped:
            raise CollectionError('prerequisite_unavailable')
        try:
            return self.api.get(operation, **args)
        except CleanupUncertain:
            raise
        except MetadataAPIError as exc:
            if exc.code in TERMINAL_ERRORS:
                self.stopped = True
            raise CollectionError(exc.code) from None

    def attempt(self, key, action):
        try:
            result = action()
            if isinstance(result, MetadataObservation):
                self.items[key] = result
            return result
        except CleanupUncertain:
            raise
        except MetadataAPIError as exc:
            code = exc.code
        except CollectionError as exc:
            code = str(exc)
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
            code = 'invalid_metadata'
        status = ('missing' if code in ('no_exact_source_run', 'workflow_missing') else
                  'prerequisite_unavailable' if code == 'prerequisite_unavailable' else
                  'inaccessible' if code in ('unauthorized', 'forbidden', 'not_found_or_not_visible',
                      'rate_limited', 'server_error', 'transport_failure', 'tls_failure') else 'invalid')
        self.items[key] = MetadataObservation(key=key, state=status, reason=code, count=0,
                                             comparison_sha256=None, records=())
        return None

    def counted(self, operation, key, **args):
        records, seen, total = [], set(), None
        for page in range(1, 11):
            reply = self.get(operation, **args, page=page)
            value = reply.value
            need(type(value) is dict, 'invalid_response_shape')
            count, batch = value.get('total_count'), value.get(key)
            need(type(count) is int and 0 <= count <= 1000, 'pagination_limit')
            need(total is None or count == total, 'pagination_changed')
            total = count
            need(type(batch) is list and len(batch) <= 100, 'incomplete_pagination')
            for item in batch:
                need(type(item) is dict and positive(item.get('id')))
                need(item['id'] not in seen, 'duplicate_record')
                seen.add(item['id']); records.append(item)
            need(len(records) <= total, 'incomplete_pagination')
            relations = link_relations(operation, dict(args, page=page), reply.link)
            need('last' not in relations or relations['last'] == max(1, (total + 99) // 100),
                 'incomplete_pagination')
            if len(records) == total:
                need('next' not in relations and relations.get('last', page) == page,
                     'incomplete_pagination')
                need(operation != 'runs' or total < 1000, 'pagination_limit')
                return records
            need(len(batch) == 100, 'incomplete_pagination')
        raise CollectionError('pagination_limit')

    def array(self, operation, identity):
        records, seen, last = [], set(), None
        for page in range(1, 11):
            reply = self.get(operation, page=page)
            batch = reply.value
            need(type(batch) is list and len(batch) <= 100, 'invalid_response_shape')
            relations = link_relations(operation, {'page': page}, reply.link)
            if 'last' in relations:
                need(last is None or last == relations['last'], 'pagination_changed')
                last = relations['last']
            need(last is None or page <= last or page == last + 1 and not batch,
                 'incomplete_pagination')
            need('next' not in relations or last is None or relations['next'] <= last, 'invalid_link')
            for item in batch:
                need(type(item) is dict)
                key = item.get(identity)
                need(positive(key) if identity == 'id' else
                     type(key) is str and re.fullmatch('[0-9a-f]{40}', key) is not None)
                need(key not in seen, 'duplicate_record')
                seen.add(key); records.append(item)
            need(len(records) < 1000, 'pagination_limit')
            if len(batch) < 100:
                need('next' not in relations and (last is None or last == page
                     or not batch and last == page - 1), 'incomplete_pagination')
                return records
            need('next' not in relations or relations['next'] == page + 1, 'invalid_link')
        raise CollectionError('pagination_limit')

    def source(self):
        source, ref = self.request.source, self.request.source_ref
        self.source_key = 'repository'
        value = self.get('repository').value
        repository(value)
        self.items['repository'] = observation('repository', [{'id': REPOSITORY_ID,
            'full_name': REPOSITORY}], [MetadataRecord(resource='repository', record_id=str(REPOSITORY_ID),
                                                   repository_id=REPOSITORY_ID)])
        self.source_key = 'ref'
        value = self.get('ref', branch=ref).value
        need(type(value) is dict and value.get('ref') == ref and
             type(value.get('object')) is dict and value['object'].get('type') == 'commit'
             and value['object'].get('sha') == source.source_sha, 'source_mismatch')
        self.items['ref'] = observation('ref', [{'ref': ref, 'sha': source.source_sha}],
            [MetadataRecord(resource='ref', record_id=source.source_sha, source_sha=source.source_sha, ref=ref)])
        self.source_key = 'commit'
        value = self.get('commit', sha=source.source_sha).value
        need(type(value) is dict and value.get('sha') == source.source_sha
             and type(value.get('tree')) is dict and value['tree'].get('sha') == source.source_tree,
             'source_mismatch')
        self.items['commit'] = observation('commit', [{'sha': source.source_sha, 'tree': source.source_tree}],
            [MetadataRecord(resource='commit', record_id=source.source_sha,
                            source_sha=source.source_sha, source_tree=source.source_tree)])
        self.source_key = 'trees'
        current, evidence, records = source.source_tree, [], []
        leaves = None
        for label, child in (('root', '.github'), ('.github', 'workflows'), ('workflows', None)):
            value = self.get('tree', sha=current).value
            need(type(value) is dict and value.get('sha') == current
                 and value.get('truncated') is False, 'tree_mismatch')
            entries = value.get('tree')
            need(type(entries) is list and len(entries) <= 1000)
            normalized = []
            for item in entries:
                need(type(item) is dict)
                name = bounded_text(item.get('path'))
                need(name and '/' not in name and not any(ord(c) < 32 for c in name))
                need(item.get('mode') in ('040000', '100644', '100755', '120000', '160000'))
                need(item.get('type') in ('tree', 'blob', 'commit'))
                normalized.append(dict(path=name, mode=item['mode'], type=item['type'], sha=sha(item.get('sha'))))
            need(len({x['path'] for x in normalized}) == len(normalized), 'duplicate_record')
            normalized.sort(key=lambda x: x['path'])
            evidence.append({'sha': current, 'entries': normalized})
            records.append(MetadataRecord(resource='tree', record_id=label, source_tree=current,
                                          detail_sha256=digest('tree', normalized)))
            if child:
                matches = [x for x in normalized if x['path'] == child]
                need(len(matches) == 1 and matches[0]['type'] == 'tree'
                     and matches[0]['mode'] == '040000', 'tree_mismatch')
                current = matches[0]['sha']
            else:
                leaves = {x['path']: x for x in normalized}
        self.items['trees'] = observation('trees', evidence, records)
        return leaves

    def workflow(self, role, leaves):
        need(leaves is not None, 'prerequisite_unavailable')
        name = WORKFLOWS[role].split('/')[-1]
        leaf = leaves.get(name)
        need(leaf is not None, 'workflow_missing')
        need(leaf['type'] == 'blob' and leaf['mode'] == '100644', 'workflow_mismatch')
        value = self.get('workflow', role=role).value
        need(type(value) is dict and positive(value.get('id'))
             and value.get('path') == WORKFLOWS[role], 'workflow_mismatch')
        lifecycle, unknown = state(value.get('state'),
            ('active', 'disabled_manually', 'disabled_inactivity', 'deleted'))
        need(lifecycle is not None)
        facts = dict(id=value['id'], path=WORKFLOWS[role], blob=leaf['sha'],
                     state=lifecycle, unknown_state=unknown)
        return observation(role + '_workflow', [facts], [MetadataRecord(resource='workflow',
            record_id=str(value['id']), workflow_id=value['id'], workflow_blob=leaf['sha'], name=WORKFLOWS[role],
            state=lifecycle, detail_sha256=digest('workflow', facts))])

    def run(self, raw, role, workflow_id):
        need(type(raw) is dict)
        repository(raw.get('repository')); repository(raw.get('head_repository'))
        for key in ('id', 'run_attempt', 'run_number', 'workflow_id'):
            need(positive(raw.get(key)))
        need(raw['workflow_id'] == workflow_id and raw.get('path') == WORKFLOWS[role], 'workflow_mismatch')
        need(raw.get('head_sha') == self.request.source.source_sha, 'source_mismatch')
        lifecycle, unknown = state(raw.get('status'), STATES)
        conclusion, unknown_conclusion = state(raw.get('conclusion'), CONCLUSIONS)
        need(lifecycle is not None)
        created, updated = moment(raw.get('created_at')), moment(raw.get('updated_at'))
        started = moment(raw.get('run_started_at'), True)
        need(created <= updated and (started is None or created <= started <= updated))
        need(lifecycle != 'completed' or (started is not None and conclusion is not None))
        event, branch = bounded_text(raw.get('event')), bounded_text(raw.get('head_branch'))
        return dict(id=raw['id'], run_attempt=raw['run_attempt'], run_number=raw['run_number'],
            workflow_id=workflow_id, source_sha=raw['head_sha'], status=lifecycle, conclusion=conclusion,
            created_at=created, updated_at=updated, started_at=started,
            event=event if event in ('push', 'pull_request', 'workflow_dispatch') else 'unknown',
            event_digest=digest('event', event), branch_digest=digest('branch', branch),
            expected_branch=branch == self.request.source_ref.removeprefix('refs/heads/'),
            final_branch=re.fullmatch(r'release/full-rc-candidate-[A-Za-z0-9][A-Za-z0-9._-]*', branch) is not None,
            unknown_status=unknown, unknown_conclusion=unknown_conclusion)

    def runs(self, role, workflow):
        need(workflow is not None, 'prerequisite_unavailable')
        workflow_id = workflow.records[0].workflow_id
        values = self.counted('runs', 'workflow_runs', workflow_id=workflow_id,
                              sha=self.request.source.source_sha)
        normalized = sorted((self.run(v, role, workflow_id) for v in values), key=lambda x: x['id'])
        need(len({v['run_number'] for v in normalized}) == len(normalized), 'duplicate_record')
        numbered = sorted(normalized, key=lambda x: x['run_number'])
        need(all(a['created_at'] <= b['created_at'] for a, b in zip(numbered, numbered[1:])))
        self.items[role + '_runs'] = observation(role + '_runs', normalized)
        need(numbered, 'no_exact_source_run')
        selected = numbered[-1]
        direct = self.run(self.get('run', run_id=selected['id']).value, role, workflow_id)
        need(selected == direct, 'snapshot_changed')
        reason = ('unsupported_attempt' if role == 'final' and direct['run_attempt'] != 1 else
                  'unsupported_run' if (role == 'final' and
                   (direct['event'] != 'push' or not direct['final_branch'])) or
                   not direct['expected_branch'] or direct['event'] == 'unknown' or
                   direct['status'] == 'unknown' or direct['conclusion'] == 'unknown' else 'observed')
        record = MetadataRecord(resource='run', record_id=str(direct['id']), repository_id=REPOSITORY_ID,
            source_sha=direct['source_sha'], run_id=direct['id'], run_attempt=direct['run_attempt'],
            run_number=direct['run_number'], workflow_id=workflow_id, state=direct['status'],
            conclusion=direct['conclusion'], event=direct['event'], created_at=direct['created_at'],
            updated_at=direct['updated_at'], started_at=direct['started_at'],
            ref=self.request.source_ref if direct['expected_branch'] else None, detail_sha256=digest('run', direct))
        self.items[role + '_run'] = observation(role + '_run', [direct], [record], reason,
                                               'observed' if reason == 'observed' else 'unsupported')
        return direct

    def jobs(self, role, run):
        need(run is not None, 'prerequisite_unavailable')
        values = self.counted('jobs', 'jobs', run_id=run['id'], attempt=run['run_attempt'])
        expected, normalized, records = (FINAL_JOBS if role == 'final' else INTEGRATION_JOBS), [], []
        for item in sorted(values, key=lambda x: x['id']):
            need(item.get('run_id') == run['id'] and type(item.get('run_id')) is int
                 and positive(item.get('run_attempt')) and item['run_attempt'] == run['run_attempt']
                 and item.get('head_sha') == run['source_sha'], 'source_mismatch')
            name = bounded_text(item.get('name'))
            status, unknown = state(item.get('status'), STATES)
            conclusion, unknown_conclusion = state(item.get('conclusion'), CONCLUSIONS)
            need(status is not None)
            start, end = moment(item.get('started_at'), True), moment(item.get('completed_at'), True)
            need(end is None or start is not None and start <= end)
            need(start is None or run['started_at'] is not None and run['started_at'] <= start <= run['updated_at'])
            need(end is None or end <= run['updated_at'])
            need(status != 'completed' or start is not None and end is not None and conclusion is not None)
            value = dict(id=item['id'], run_id=run['id'], run_attempt=run['run_attempt'],
                source_sha=run['source_sha'], name=name if name in expected else None,
                name_digest=digest('job-name', name), status=status, conclusion=conclusion,
                unknown_status=unknown, unknown_conclusion=unknown_conclusion, started_at=start, completed_at=end)
            normalized.append(value)
            records.append(MetadataRecord(resource='job', record_id=str(item['id']),
                source_sha=run['source_sha'], run_id=run['id'], run_attempt=run['run_attempt'],
                name=value['name'], state=status, conclusion=conclusion, started_at=start,
                completed_at=end, detail_sha256=digest('job', value)))
        current = self.run(self.get('run', run_id=run['id']).value, role, run['workflow_id'])
        need(current == run, 'snapshot_changed')
        names = [x['name'] for x in normalized]
        complete = len(names) == len(expected) and set(names) == expected and len(set(names)) == len(names)
        need(len(records) <= 128, 'output_limit')
        unknown = any(x['status'] == 'unknown' or x['conclusion'] == 'unknown' for x in normalized)
        reason = 'unknown_state' if unknown else 'observed' if complete else 'jobs_incomplete'
        return observation(role + '_jobs', normalized, records, reason,
                           'observed' if complete and not unknown else 'unsupported')

    def pull(self):
        raw = self.get('pr').value
        need(type(raw) is dict and raw.get('number') == 36 and type(raw.get('number')) is int)
        need(positive(raw.get('id')) and type(raw.get('merged')) is bool)
        repository(raw.get('head', {}).get('repo')); repository(raw.get('base', {}).get('repo'))
        count = raw.get('commits')
        need(type(count) is int and 0 <= count < 2**31)
        value = dict(id=raw['id'], number=36, head_sha=sha(raw['head'].get('sha')),
            base_sha=sha(raw['base'].get('sha')), merge_sha=None if raw.get('merge_commit_sha') is None
            else sha(raw['merge_commit_sha']), merged=raw['merged'], commits=count,
            state=bounded_text(raw.get('state')), updated_at=moment(raw.get('updated_at')))
        self.items['pr'] = observation('pr', [value], [MetadataRecord(resource='pr', record_id=str(raw['id']),
            head_sha=value['head_sha'], base_sha=value['base_sha'], merge_sha=value['merge_sha'],
            merged=value['merged'], commit_count=count, updated_at=value['updated_at'], detail_sha256=digest('pr', value))])
        return value

    def reviews(self, pull):
        need(pull is not None, 'prerequisite_unavailable')
        values = self.array('reviews', 'id')
        need(len(values) <= 128, 'review_cap')
        normalized, records = [], []
        for item in sorted(values, key=lambda x: x['id']):
            need(type(item.get('user')) is dict and positive(item['user'].get('id')))
            review_state, unknown = state(item.get('state'), REVIEWS)
            need(review_state is not None)
            commit = None if item.get('commit_id') is None else sha(item['commit_id'])
            submitted = moment(item.get('submitted_at'), True)
            need(review_state in ('PENDING', 'unknown') or submitted is not None and commit is not None)
            value = dict(id=item['id'], reviewer_id=item['user']['id'], reviewed_sha=commit,
                state=review_state, unknown_state=unknown, submitted_at=submitted,
                current_source=commit == self.request.source.source_sha, current_head=commit == pull['head_sha'])
            normalized.append(value)
            records.append(MetadataRecord(resource='review', record_id=str(item['id']),
                reviewer_id=value['reviewer_id'], reviewed_sha=commit, state=review_state,
                submitted_at=submitted, detail_sha256=digest('review', value)))
        return observation('reviews', normalized, records)

    def commits(self, pull):
        need(pull is not None, 'prerequisite_unavailable')
        need(pull['commits'] < 250, 'commit_cap')
        values = self.array('commits', 'sha')
        need(len(values) == pull['commits'] and len(values) < 250, 'incomplete_pagination')
        normalized = sorted(x['sha'] for x in values)
        return observation('commits', normalized)

    def collect_pass(self):
        self.items = {}
        self.source_key = 'repository'
        leaves = None
        try:
            leaves = self.source()
        except CleanupUncertain:
            raise
        except CollectionError as exc:
            self.attempt(self.source_key, lambda: (_ for _ in ()).throw(exc))
        except (ValueError, TypeError, KeyError, AttributeError):
            self.attempt(self.source_key, lambda: (_ for _ in ()).throw(CollectionError('invalid_metadata')))
        if leaves is not None:
            entry = leaves.get(WORKFLOWS['pretag'].split('/')[-1])
            self.attempt('pretag_workflow', lambda: observation('pretag_workflow', [entry])
                if entry and entry['type'] == 'blob' and entry['mode'] == '100644' else
                (_ for _ in ()).throw(CollectionError('workflow_missing' if entry is None else 'workflow_mismatch')))
        else:
            self.attempt('pretag_workflow', lambda: (_ for _ in ()).throw(CollectionError('prerequisite_unavailable')))
        for role in ('integration', 'final'):
            workflow = self.attempt(role + '_workflow', lambda: self.workflow(role, leaves))
            run = self.attempt(role + '_run', lambda: self.runs(role, workflow))
            self.attempt(role + '_jobs', lambda: self.jobs(role, run))
        pull = self.attempt('pr', self.pull)
        self.attempt('reviews', lambda: self.reviews(pull))
        self.attempt('commits', lambda: self.commits(pull))
        for key in OBSERVATION_KEYS[:-1]:
            if key not in self.items:
                self.items[key] = MetadataObservation(key=key, state='prerequisite_unavailable',
                    reason='prerequisite_unavailable', count=0)
        return tuple(self.items[k] for k in sorted(self.items))


def collect_metadata(request, api):
    need(type(request) is MetadataRequest, 'invalid_metadata')
    MetadataRequest(request.source, request.source_ref)
    begin = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    collector = Collector(request, api)
    try:
        first, second = collector.collect_pass(), collector.collect_pass()
    finally:
        api.close()  # Unproved cleanup propagates: never emit a completed receipt.
    changed = first != second
    observations = first
    if changed:
        observations += (MetadataObservation(key='collection', state='changed',
            reason='snapshot_changed', count=sum(a != b for a, b in zip(first, second))),)
    complete = not changed and all(x.state in ('observed', 'missing', 'unsupported') for x in observations)
    result = MetadataReceipt(request=request, observations=observations,
        revalidation_sha256=None if changed else digest('revalidation',
            [{'key': x.key, 'state': x.state, 'digest': x.comparison_sha256} for x in second]),
        revalidation_observations=tuple(replace(row, records=()) for row in second),
        started_at=begin, ended_at=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        request_count=api.request_count, response_bytes=api.response_bytes,
        channel='fixed_origin_tls_bearer_request' if type(api) is MetadataGitHub else 'synthetic',
        collection_status='observed_complete' if complete else 'blocked')
    encode(result)
    return result
