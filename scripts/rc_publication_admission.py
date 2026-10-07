"""Fixed read-only integration/FINAL metadata; publication remains blocked."""
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import re
import time

import rc_consumer_snapshot as snapshot
from rc_consumer_io import need
import rc_publication_contract as core
from rc_publication_stage import Selection, _bind
from rc_release_policy import GATE_IDS, GATES

gate = snapshot.gate


class _Interrupted(Exception):
    """Carry only owned cancellation/deadline through old ValueError sanitizers."""
    def __init__(self, code):
        need(code in ('cancelled', 'timeout'), 'invalid_interruption')
        self.code = code
        super().__init__(code)


class _Reads:
    def __init__(self, api, active, deadline):
        self.api, self.active, self.deadline = api, active, deadline

    def check(self):
        try:
            self.active()
        except Exception as error:
            if getattr(error, 'code', None) in ('cancelled', 'timeout'):
                raise _Interrupted(error.code) from None
            raise
        if time.monotonic() >= self.deadline:
            raise _Interrupted('timeout')

    def get(self, path):
        import rc_publication_github as wire
        self.check()
        try:
            value = wire.GitHub.get(self.api, path, deadline=self.deadline, check_active=self.active)
        except wire.WireFailure as error:
            if error.code in ('cancelled', 'timeout'):
                raise _Interrupted(error.code) from None
            raise
        self.check()
        return value


@dataclass(frozen=True)
class _AdmissionReport:
    subject: core.PublicationSubject
    integration_evidence_sha256: str
    status = 'blocked'
    release_approved = publish_approved = snapshot_atomic = False
    draft_visibility = 'unknown'
    evidence_authentication = 'partial'

    def __post_init__(self):
        need(type(self.subject) is core.PublicationSubject, 'invalid_admission_subject')
        need(self.integration_evidence_sha256 == self.subject.gate_evidence[
            GATE_IDS.index('full_integration')], 'integration_digest_mismatch')

    @property
    def rows(self):
        return tuple((*row, 'passed' if row[0] == 'full_integration' else 'unknown')
                     for row in core._admission(self.subject))


@dataclass(frozen=True)
class _PackagingReport(_AdmissionReport):
    final_evidence_sha256: str

    def __post_init__(self):
        super().__post_init__()
        need(self.final_evidence_sha256 == self.subject.gate_evidence[
            GATE_IDS.index('final_packaging')], 'final_digest_mismatch')

    @property
    def rows(self):
        return tuple((*row, 'passed' if row[0] in ('full_integration', 'final_packaging') else 'unknown')
                     for row in core._admission(self.subject))


def _source(api, subject, *, final=False):
    source, invocation = subject.source, subject.runs[0 if final else 1]
    role = 'final' if final else 'integration'
    repository = api.get('/')
    snapshot._repository(repository, source.repository_id)
    value = api.get('/git/ref/' + invocation.ref[5:])
    need(type(value) is dict and value.get('ref') == invocation.ref
         and type(value.get('object')) is dict and value['object'].get('type') == 'commit'
         and value['object'].get('sha') == source.source_sha, role + '_ref_mismatch')
    ref = dict(ref=value['ref'], object=dict(type='commit', sha=source.source_sha))
    commit = api.get('/git/commits/' + source.source_sha)
    need(type(commit) is dict and commit.get('sha') == source.source_sha
         and type(commit.get('tree')) is dict and commit['tree'].get('sha') == source.source_tree,
         role + '_source_mismatch')
    tree_sha, trees = source.source_tree, []
    for name, mode, kind in (('.github', '040000', 'tree'), ('workflows', '040000', 'tree'),
                             (('final-rc-packages.yml' if final else 'dot-rc-integration.yml'), '100644', 'blob')):
        tree = api.get('/git/trees/' + tree_sha)
        need(type(tree) is dict and tree.get('sha') == tree_sha and tree.get('truncated') is False
             and type(tree.get('tree')) is list, role + '_tree_invalid')
        rows, names = tree['tree'], set()
        for row in rows:
            path = row.get('path') if type(row) is dict else None
            need(type(path) is str and 0 < len(path) <= 256 and '/' not in path
                 and path not in ('.', '..') and path not in names, role + '_tree_invalid')
            names.add(path)
        matches = [row for row in rows if row['path'] == name]
        need(len(matches) == 1 and matches[0].get('mode') == mode
             and matches[0].get('type') == kind, role + '_workflow_mismatch')
        sha = matches[0].get('sha')
        need(type(sha) is str and re.fullmatch('[a-f0-9]{40}', sha), role + '_tree_invalid')
        trees.append(tree_sha)
        tree_sha = sha
    need(tree_sha == invocation.workflow_blob, role + '_workflow_mismatch')
    return dict(repository=dict(id=source.repository_id, full_name=source.repository), ref=ref,
                commit=dict(sha=source.source_sha, tree=source.source_tree), trees=trees,
                workflow=dict(path=invocation.workflow_path, mode='100644', sha=tree_sha))


def _evidence(api, subject, *, final=False):
    index, role = (0, 'final') if final else (1, 'integration')
    invocation, source = subject.runs[index], subject.source
    workflow, jobs = (gate.FINAL_WORKFLOW, gate.FINAL_JOBS) if final else (gate.final.WORKFLOW, gate.final.REQUIRED_JOBS)
    evidence = gate.successful_run(api, workflow, source.source_sha, jobs)
    need(evidence['workflow'].get('state') == 'active', role + '_workflow_inactive')
    strict = snapshot._strict_run(evidence, source.repository_id, source.source_sha,
                                  invocation.run_id, invocation.run_attempt, final=final)
    _bind(strict, invocation, subject.job_ids[index])
    exact = api.get(f'/actions/runs/{invocation.run_id}/attempts/{invocation.run_attempt}')
    need(snapshot._run(exact, source.repository_id) == strict['run'], role + '_attempt_changed')
    return strict


def authenticate_integration(api, selection, *, check_active, deadline):
    """Fresh owned GETs only; this result cannot be imported as publication authority."""
    import rc_publication_github as wire
    need(type(api) is wire.GitHub and api.selection is selection, 'invalid_admission_transport')
    need(type(selection) is Selection, 'invalid_publication_selection')
    selection.__post_init__()
    subject, invocation = selection.subject, selection.subject.runs[1]
    need(invocation.event in ('push', 'workflow_dispatch')
         and invocation.ref.startswith(('refs/heads/', 'refs/tags/'))
         and (invocation.event != 'push' or invocation.ref.startswith('refs/heads/')), 'unsupported_integration_ref')
    need(next(g.verifier for g in GATES if g.gate_id == 'full_integration')
         == 'github_full_integration_v1', 'integration_policy_mismatch')
    need(type(deadline) in (int, float) and math.isfinite(deadline), 'invalid_admission_deadline')
    reads = _Reads(api, check_active, min(deadline, time.monotonic() + wire.DEADLINE))
    reads.check()
    source = _source(reads, subject)
    observed = snapshot._ObservedAPI(reads, subject.source.repository_id)
    evidence = _evidence(observed, subject)
    need(_evidence(observed, subject) == evidence, 'integration_evidence_changed')
    latest = gate.latest_run(observed, evidence['workflow'], subject.source.source_sha)
    need(snapshot._run(latest, subject.source.repository_id) == evidence['run'], 'integration_run_changed')
    current = observed.get(f'/actions/runs/{invocation.run_id}')
    need(snapshot._run(current, subject.source.repository_id) == evidence['run'], 'integration_run_changed')
    need(_source(reads, subject) == source, 'integration_source_changed')
    digest = _digest(subject, source, evidence)
    reads.check()
    return _AdmissionReport(subject, digest)


def _digest(subject, source, evidence, *, final=False):
    invocation = subject.runs[0 if final else 1]
    record = dict(evidence, run=dict(evidence['run']))
    for key in ('repository', 'head_repository'):
        record['run'][key] = {name: evidence['run'][key][name] for name in ('id', 'full_name')}
    canonical = dict(schema='rc-final-packaging-v1' if final else 'rc-full-integration-v1',
        gate_id='final_packaging' if final else 'full_integration',
        source=asdict(subject.source), invocation=asdict(invocation), source_observation=source, evidence=record)
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=True, allow_nan=False).encode('utf-8')).hexdigest()


def authenticate_packaging(api, selection, *, check_active, deadline):
    """Observe the two fixed roles under one deadline; all remaining gates stay unknown."""
    import rc_publication_github as wire
    need(type(api) is wire.GitHub and api.selection is selection, 'invalid_admission_transport')
    need(type(selection) is Selection, 'invalid_publication_selection')
    selection.__post_init__()
    subject = selection.subject
    invocation, final = subject.runs[1], subject.runs[0]
    need(invocation.event in ('push', 'workflow_dispatch')
         and invocation.ref.startswith(('refs/heads/', 'refs/tags/'))
         and (invocation.event != 'push' or invocation.ref.startswith('refs/heads/')), 'unsupported_integration_ref')
    need(final.event == 'push' and final.run_attempt == 1 and final.ref.startswith('refs/heads/')
         and snapshot.CANDIDATE_BRANCH.fullmatch(final.ref[11:]) is not None, 'unsupported_final_producer')
    for key, verifier in (('full_integration', 'github_full_integration_v1'),
                          ('final_packaging', 'github_final_packaging_v1')):
        need(next(g.verifier for g in GATES if g.gate_id == key) == verifier, 'packaging_policy_mismatch')
    need(type(deadline) in (int, float) and math.isfinite(deadline), 'invalid_admission_deadline')
    reads = _Reads(api, check_active, min(deadline, time.monotonic() + wire.DEADLINE))
    reads.check()
    sources = tuple(_source(reads, subject, final=role) for role in (False, True))
    observed = snapshot._ObservedAPI(reads, subject.source.repository_id)
    evidence = tuple(_evidence(observed, subject, final=role) for role in (False, True))
    for role, expected in zip((False, True), evidence):
        need(_evidence(observed, subject, final=role) == expected, 'packaging_evidence_changed')
    for expected in evidence:
        latest = gate.latest_run(observed, expected['workflow'], subject.source.source_sha)
        need(snapshot._run(latest, subject.source.repository_id) == expected['run'], 'packaging_run_changed')
        current = observed.get(f"/actions/runs/{expected['run']['id']}")
        need(snapshot._run(current, subject.source.repository_id) == expected['run'], 'packaging_run_changed')
    for role, expected in zip((False, True), sources):
        need(_source(reads, subject, final=role) == expected, 'packaging_source_changed')
    digests = tuple(_digest(subject, source, record, final=role)
                    for role, source, record in zip((False, True), sources, evidence))
    report = _PackagingReport(subject, *digests)
    reads.check()
    return report
