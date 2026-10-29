"""Synthetic data only. No fixture is an authenticated or finalized receipt."""
from dataclasses import replace

from rc_pretag_types import (InvocationIdentity, POLICY_REVISION, PreTagCandidate, REPOSITORY,
                            REPOSITORY_ID, SourceIdentity, WORKFLOWS)
from rc_pretag_evidence import (ArtifactObservation, AuditObservation, BLOCKERS, BUNDLE_JOB,
    FINAL_JOBS, INTEGRATION_JOBS, JobObservation, PayloadObservation, PreTagEvidenceReceipt,
    SelectedRunObservation, StructuralObservation, payload_names)
from rc_release_eligibility import GateObservation, ReviewObservation, evaluate
from rc_release_policy import GATES


SOURCE = SourceIdentity(REPOSITORY, REPOSITORY_ID, 'a' * 40, 'b' * 40, '1.2.3-rc.7')


def invocation(role='pretag', attempt=1, source=SOURCE):
    refs = {'pretag': 'refs/heads/release/rc-pretag-' + source.version + '-fixture1',
            'integration': 'refs/heads/release/dot-rc-reconciliation-fixture',
            'final': 'refs/heads/release/full-rc-candidate-fixture',
            'consumer': 'refs/heads/release/rc-consumer-fixture'}
    event = 'workflow_dispatch' if role == 'consumer' else 'push'
    ids = {'pretag': 400, 'integration': 100, 'final': 200, 'consumer': 300}
    return InvocationIdentity(role, source, ids[role], attempt, ids[role] + 1,
        WORKFLOWS[role], REPOSITORY + '/' + WORKFLOWS[role] + '@' + refs[role],
        source.source_sha, 'c' * 40, event, refs[role])


def candidate():
    return PreTagCandidate(SOURCE, invocation(), 'v' + SOURCE.version, 'absent', 'absent',
        'unknown', 'unknown', True, (SOURCE.version,) * 6, SOURCE.version,
        'd' * 40, 'e' * 64, POLICY_REVISION, 'unverified')


def selected(role='final', attempt=1):
    run = invocation(role, attempt)
    names = FINAL_JOBS if role == 'final' else INTEGRATION_JOBS
    jobs = tuple(JobObservation(1000 + i, name, run.run_id, attempt, SOURCE.source_sha,
        'completed', 'success', '2026-10-01T00:01:00Z', '2026-10-01T00:03:00Z')
        for i, name in enumerate(sorted(names)))
    return SelectedRunObservation(run, attempt, run.run_id, '2026-10-01T00:00:00Z',
        '2026-10-01T00:04:00Z', jobs, 'f' * 64, True)


def passing_claim(gate):
    return GateObservation(gate.gate_id, 'passed', SOURCE, '1' * 64, gate.permissions,
                           'observed', None, None)


def passing_claims():
    return tuple(passing_claim(gate) for gate in GATES)


def review():
    return ReviewObservation(77, 88, SOURCE.source_sha, SOURCE.source_sha,
                             SOURCE.source_sha, '2' * 64, 'approved', 'unverified')


def receipt(full=False):
    item = candidate()
    integration, final = (selected('integration', 3), selected()) if full else (None, None)
    consumer = invocation('consumer', 3) if full else None
    artifact, structural, payloads, audits = None, None, (), ()
    observations = passing_claims() if full else ()
    if full:
        job = next(job for job in final.jobs if job.name == BUNDLE_JOB)
        artifact = ArtifactObservation(SOURCE, final.invocation.run_id, 1, job.job_id, 1234,
            'rc-structural-bundle', 123456, '3' * 64, '3' * 64,
            '2026-10-01T00:02:00Z', False, 'unverified')
        structural = StructuralObservation(SOURCE, final.invocation.run_id, 1,
            '2026-10-01T00:03:00Z', '4' * 64, True, BLOCKERS, False, False)
        payloads = tuple(PayloadObservation(name, family, 42, '5' * 64)
                         for family, name in payload_names(SOURCE.version).items())
        audits = tuple(AuditObservation(scope, 1, 0, 2, 0, 0, 0)
                       for scope in ('cloud', 'desktop', 'cloud-agent', 'local-agent', 'npm'))
    identities = (integration.invocation, final.invocation, consumer) if full else ()
    return PreTagEvidenceReceipt(1, item, integration, final, consumer, artifact, payloads,
        structural, audits, observations, 'unknown', 'unknown', 'unverified', 'blocked',
        evaluate(item, observations, identities), False, False, False, False)
