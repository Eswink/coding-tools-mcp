"""Genuine local native scopes with modeled predecessors; grants no authority."""
from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import SimpleNamespace, MethodType
from unittest.mock import patch

import rc_publication_artifact_admission as artifacts
from rc_publication_artifact_admission_cases import ArtifactTLS
import rc_publication_contract as core
import rc_publication_executor as executor
import rc_publication_github as wire
from rc_publication_https_fixture import authorities, gates
import rc_publication_request as owned
from rc_publication_stage_cases import publisher_fixture, artifact_worker


@contextmanager
def _native_session(case, *, clock=None, after_enter=None):
    """Observe unchanged real issuers; no handwritten scope or session fields."""
    with publisher_fixture() as fixture, ArtifactTLS(fixture) as tls, \
            patch.object(wire, '_connect', side_effect=tls.connect), \
            authorities(), artifact_worker(fixture, tls), ExitStack() as stack:
        session = executor.PublisherSession(fixture.root, fixture.selection, 'fixture-token',
                                           temporary_parent=fixture.parent)
        trace = SimpleNamespace(entered=[], controls=[], executions=[], before_execute=None)
        enter, controls, execute = artifacts._ArtifactOwner.enter, owned._read_controls, executor.PublisherSession._execute
        def entered(owner, *args, **kwargs):
            value = enter(owner, *args, **kwargs)
            if owner.api is session._api:
                raw, scope = kwargs['check_active'], session._read_scope
                case.assertIs(type(raw), MethodType)
                case.assertIs(raw.__self__, session)
                case.assertIs(raw.__func__, executor.PublisherSession._check_active)
                case.assertIs(owner._owner_active, raw)
                case.assertIs(owner._session, session)
                case.assertIs(owner.selection, session._api.selection)
                case.assertIs(artifacts._OWNERS.get(owner.api), owner)
                case.assertIs(scope._owner, session._owner)
                case.assertFalse(scope._retired)
                trace.entered.append((owner, raw, scope, tuple(owner.stage._handles)))
                if after_enter is not None:
                    after_enter(owner, session, tls, trace)
            return value
        def controlled(api, *args, **kwargs):
            result = controls(api, *args, **kwargs)
            if api is session._api:
                trace.controls.append(result)
            return result
        def executing(current, op):
            if current is session:
                trace.executions.append((op, current._read_scope, current._request_scope))
                if trace.before_execute is not None:
                    trace.before_execute(current, op)
            return execute(current, op)
        def current_phase(selection, api, *, deadline, check_active):
            owner = artifacts._OWNERS.get(api)
            if owner is not None:
                case.assertIs(owner, session._artifact_owner)
                case.assertIs(owner.stage, session._stage)
                case.assertIs(owner.selection, api.selection)
                case.assertTrue(owner.entered and not owner.closed)
                failure = None
                try:
                    owner._capture(deadline=deadline, check_active=check_active)
                except artifacts.ConsumerError as error:
                    if error.code not in ('transport_cancelled', 'transport_deadline_exceeded', 'artifact_transport_failed'):
                        raise
                    failure = artifacts._wire_failure(error)
                if failure is not None:
                    raise failure from None
            return gates(selection, api, deadline=deadline, check_active=check_active)
        if clock is not None:
            stack.enter_context(patch.object(executor, 'time', clock))
        stack.enter_context(patch.object(artifacts._ArtifactOwner, 'enter', entered))
        stack.enter_context(patch.object(owned, '_read_controls', controlled))
        stack.enter_context(patch.object(executor.PublisherSession, '_execute', executing))
        stack.enter_context(patch.object(wire, '_authenticate', side_effect=current_phase))
        failures, trace.cleanup_checks = [], []
        try:
            yield session, tls, fixture, trace
        except BaseException as error:
            failures.append(error)
        try:
            session.close()
        except BaseException as error:
            failures.append(error)
        checks = [('retired_client', lambda: case.assertIsNone(session._api))]
        for owner, _, previous, handles in trace.entered:
            checks.extend([('retired_owner', lambda o=owner, p=previous: case.assertTrue(o.closed and p._retired)),
                           ('owner_registry', lambda o=owner: case.assertNotIn(o.api, artifacts._OWNERS)),
                           ('closed_handles', lambda h=handles: case.assertTrue(all(x.closed for x in h)))])
        checks.extend([('retired_scopes', lambda: case.assertTrue(all(read._retired and (scope is None or scope._retired)
                       for _, read, scope in trace.executions))),
                       ('removed_output', lambda: case.assertEqual(list(Path(fixture.parent).glob('rc-publisher-*')), [])),
                       ('tls_errors', lambda: case.assertEqual(tls.errors, []))])
        for name, check in checks:
            try:
                check()
                trace.cleanup_checks.append((name, True))
            except BaseException as error:
                trace.cleanup_checks.append((name, False))
                failures.append(error)
        if len(failures) == 1:
            raise failures[0]
        if failures:
            raise BaseExceptionGroup('Native fixture body, close and cleanup failures', failures)


def _pending_fence(case, kind, production_authenticate):
    """Reach the actual target, then restore the unchanged production gate."""
    with _native_session(case) as (session, tls, fixture, trace):
        native_execute = executor.PublisherSession._execute
        captured = []
        def target(current, op):
            if current is not session or op.kind != kind:
                return native_execute(current, op)
            before, scope, read = len(tls.requests), current._request_scope, current._read_scope
            case.assertEqual(captured, [])
            predecessors = [row for row in tls.requests if row[0] in ('POST', 'PATCH', 'DELETE')]
            def authenticate(selection, api, **kwargs):
                snapshot = scope._snapshot
                owner = artifacts._OWNERS.get(api)
                case.assertIs(api, session._api)
                case.assertIs(selection, api.selection)
                case.assertIs(owner, session._artifact_owner)
                case.assertIs(owner._session, session)
                case.assertIs(scope._owner, session._owner)
                case.assertIs(scope._owner._credential, api._credential)
                case.assertIs(snapshot._client, api)
                case.assertIs(snapshot._credential, api._credential)
                case.assertIs(snapshot._scope, scope)
                case.assertIsNone(snapshot._read_scope)
                case.assertIs(read._owner, session._owner)
                case.assertFalse(read._retired)
                case.assertIs(snapshot._op, op)
                case.assertIs(session._transition.action, op)
                case.assertIs(session._transition.state.pending, op)
                case.assertIs(session._inflight, op)
                case.assertFalse(scope._used)
                case.assertNotIn(op.operation_id, session._attempted)
                case.assertEqual(snapshot._deadline, min(scope._deadline, read._deadline, session._deadline))
                case.assertEqual(snapshot._method, 'PATCH' if kind == 'PublishPrerelease' else 'POST')
                case.assertTrue(snapshot._header.startswith((snapshot._method+' '+snapshot._path+' HTTP/1.1\r\n').encode()))
                return production_authenticate(selection, api, **kwargs)
            with patch.object(wire, '_authenticate', side_effect=authenticate), patch.object(wire, '_authorize') as authorize:
                with case.assertRaises(wire.WireFailure) as error:
                    native_execute(current, op)
                case.assertEqual((error.exception.code, error.exception.effect), ('fence_blocked', 'none'))
                authorize.assert_not_called()
            rows = tls.requests[before:]
            subject = session._selection.subject
            trees = [subject.source.source_tree]
            for name in ('.github', 'workflows'):
                trees.append(next(r['sha'] for r in fixture.api.data['/git/trees/'+trees[-1]]['tree'] if r['path']==name))
            sources, evidence, closing = [], [], []
            for index in (1, 0):
                run = subject.runs[index]
                source = ['/', '/git/ref/'+run.ref[5:], '/git/commits/'+subject.source.source_sha]
                source += ['/git/trees/'+sha for sha in trees]
                prefix = '/actions/runs/'+str(run.run_id)
                runs = '/actions/workflows/'+str(run.workflow_id)+'/runs?head_sha='+subject.source.source_sha+'&per_page=100&page=1'
                phase = ['/actions/workflows/'+Path(run.workflow_path).name, runs, prefix,
                         prefix+'/attempts/'+str(run.run_attempt)+'/jobs?per_page=100&page=1', prefix,
                         prefix+'/attempts/'+str(run.run_attempt)]
                sources.extend(source); evidence.extend(phase); closing.extend((runs, prefix))
            expected = [wire.ROOT+(p if p!='/' else '') for p in sources+evidence+evidence+closing+sources]
            case.assertEqual(len(expected), 52)
            case.assertEqual([r[1] for r in rows[:52]], expected)
            case.assertTrue(all(r[0]=='GET' and not r[3] for r in rows))
            report = session._artifact_owner._report
            case.assertEqual([r[0] for r in report.rows if r[3]=='passed'],
                             ['raw_cloud_audit', 'raw_noncloud_audits', 'full_integration', 'final_packaging', 'bundle_bytes'])
            case.assertEqual(sum(r[3]=='unknown' for r in report.rows), 58)
            case.assertEqual((report.status, report.draft_visibility), ('blocked', 'unknown'))
            case.assertFalse(report.release_approved or report.publish_approved or report.snapshot_atomic)
            case.assertFalse(scope._used)
            case.assertNotIn(op.operation_id, session._attempted)
            case.assertEqual([r for r in tls.requests if r[0] in ('POST','PATCH','DELETE')], predecessors)
            captured.append((scope, read, len(predecessors)))
            raise error.exception
        with patch.object(executor.PublisherSession, '_execute', target):
            result = session.run_until_pause()
            if kind == 'PublishPrerelease':
                case.assertIsInstance(result.action, core.AwaitPublishRequest)
                pause = result.action
                result = session.request_publish(core.PublicationRequest('publish-once', 'owner-request-reference',
                                                  pause.release_id, pause.subject_digest))
        case.assertEqual(len(captured), 1)
        scope, read, count = captured[0]
        case.assertTrue(scope._retired and read._retired)
        case.assertEqual(count, {'CreateDraft':0, 'UploadAsset':1, 'PublishPrerelease':7}[kind])
        case.assertEqual(result.state.code, 'fence_blocked')
        case.assertEqual(result.state.outcome, 'blocked_no_effect' if kind=='CreateDraft' else 'partial_draft')


def _authorizer_denial(case, production_authorize):
    """Capture only the request and scope delivered by genuine native _request."""
    with _native_session(case) as (session, tls, _, trace):
        captured = []
        def authorize(op, subject, *, request, scope):
            case.assertEqual(captured, [])
            case.assertIs(op, session._transition.action)
            case.assertIs(op, session._transition.state.pending)
            case.assertIs(op, session._inflight)
            case.assertIs(subject, session._selection.subject)
            case.assertIs(scope, session._request_scope)
            case.assertIs(request, scope._snapshot)
            case.assertIs(request._scope, scope)
            case.assertIs(request._client, session._api)
            case.assertIs(request._credential, session._api._credential)
            case.assertIsNone(request._read_scope)
            case.assertIs(session._read_scope._owner, session._owner)
            case.assertFalse(session._read_scope._retired)
            case.assertIs(scope._owner, session._owner)
            case.assertFalse(scope._used)
            case.assertNotIn(op.operation_id, session._attempted)
            case.assertEqual((request._method, request._host, request._path),
                             ('POST', wire.API, wire.ROOT+'/releases'))
            case.assertEqual(request._deadline, min(scope._deadline, session._read_scope._deadline, session._deadline))
            captured.append((scope, session._read_scope, len(tls.requests)))
            return production_authorize(op, subject, request=request, scope=scope)
        with patch.object(wire, '_authorize', side_effect=authorize):
            result = session.run_until_pause()
        case.assertEqual((result.state.code, result.state.outcome), ('denied','blocked_no_effect'))
        case.assertEqual(len(captured), 1)
        scope, read, before = captured[0]
        case.assertTrue(scope._retired and read._retired)
        case.assertFalse(scope._used)
        case.assertEqual(len(tls.requests), before)
        case.assertEqual([r for r in tls.requests if r[0] in ('POST','PATCH','DELETE')], [])
