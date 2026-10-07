"""Twelve real TLS protocol cases, with adversarial subcases; never live traffic."""
from dataclasses import replace
import hashlib
import io
import json
import socket
import ssl
import time
import unittest
from unittest.mock import patch

import rc_publication_contract as core
import rc_publication_github as wire
from rc_publication_https_fixture import HTTPSFixture, authorities, gates, stable_identity


class GitHubCases(unittest.TestCase):
    def setUp(self):
        self.fixture = HTTPSFixture().__enter__()
        self.addCleanup(self.fixture.close)
        self.connection = patch.object(wire, '_connect', side_effect=self.fixture.connect)
        self.connection.start()
        self.addCleanup(self.connection.stop)
        self.api = wire.GitHub('fixture-private-token', self.fixture.selection)
        self.addCleanup(self.api.close)
        self.transition = core.start(self.fixture.subject, self.fixture.plan)
        self.trace, self.attempts = [], []

    def step(self):
        state, op = self.transition.state, self.transition.action
        self.trace.append(op.kind)
        fields = {}
        if op.kind in ('ObserveFence', 'ObserveDraft', 'VerifyPublished'):
            rows, visibility = gates(self.fixture.selection)
            fields['observation'] = self.api.observe(state, staged=state.plan.assets, gates=rows,
                                                      draft_visibility=visibility)
        elif op.kind in ('CreateDraft', 'PublishPrerelease'):
            method = self.api.create_draft if op.kind == 'CreateDraft' else self.api.publish_prerelease
            fields['release_id'] = method(op, before_write=lambda: self.attempts.append(op.operation_id),
                                          check_active=lambda: None)
        elif op.kind == 'UploadAsset':
            fields['asset'] = self.api.upload_asset(op, io.BytesIO(self.fixture.payloads[op.asset.name]),
                before_write=lambda: self.attempts.append(op.operation_id), check_active=lambda: None)
            fields['release_id'] = op.release_id
        else:
            fields.update(asset=self.api.verify_asset(op), release_id=op.release_id)
        result = core.OperationResult(core.RESULT_KINDS[core.OPERATION_KINDS.index(op.kind)],
            op.operation_id, op.subject_digest, op.kind, 'confirmed' if op.kind in core.MUTATIONS else 'none', **fields)
        self.transition = core.advance(state, result)
        return self.transition

    def until(self, kind, ordinal=None):
        while self.transition.action is not None:
            action = self.transition.action
            if type(action) is core.AwaitPublishRequest:
                if kind == 'AwaitPublishRequest':
                    return action
                self.transition = core.request_publish(self.transition.state,
                    core.PublicationRequest('request', 'fixture-owner', action.release_id, action.subject_digest))
                continue
            if action.kind == kind and (ordinal is None or action.asset_ordinal == ordinal):
                return action
            self.step()
        self.fail('unexpected terminal outcome: ' + str(self.transition.state.outcome))

    def error(self, function, effect='none'):
        with self.assertRaises(wire.WireFailure) as caught:
            function()
        self.assertEqual(caught.exception.effect, effect)
        self.assertIn(caught.exception.code, core.CODES)
        self.assertNotIn('fixture-private-token', str(caught.exception))
        self.assertIsNone(caught.exception.__context__)
        return caught.exception

    def mutate(self, op):
        if op.kind == 'CreateDraft':
            return self.api.create_draft(op, before_write=lambda: None, check_active=lambda: None)
        if op.kind == 'PublishPrerelease':
            return self.api.publish_prerelease(op, before_write=lambda: None, check_active=lambda: None)
        return self.api.upload_asset(op, io.BytesIO(self.fixture.payloads[op.asset.name]),
                                     before_write=lambda: None, check_active=lambda: None)

    def test_closed_methods_paths_headers_and_bodies(self):
        with authorities():
            create = self.until('CreateDraft')
            self.until('VerifyPublished')
            publish = [r for r in self.fixture.requests if r[0] == 'PATCH'][0]
        created = [r for r in self.fixture.requests if r[0] == 'POST' and r[1] == wire.ROOT + '/releases'][0]
        self.assertEqual(json.loads(created[3]), {'tag_name': self.fixture.subject.tag, 'draft': True,
            'prerelease': True, 'make_latest': 'false', 'generate_release_notes': False})
        self.assertEqual(json.loads(publish[3]), {'draft': False, 'prerelease': True, 'make_latest': 'false'})
        self.assertEqual(publish[1], wire.ROOT + '/releases/100')
        for method, path, headers, body in self.fixture.requests:
            self.assertIn(method, ('GET', 'POST', 'PATCH'))
            self.assertEqual(headers['x-github-api-version'], '2022-11-28')
            self.assertEqual(headers['authorization'], 'Bearer fixture-private-token')
            self.assertNotIn('cookie', headers)
            self.assertTrue(path.startswith(wire.ROOT + '/'))
        for suffix in ('https://evil.invalid', '//evil', '/a/../b', '/x\r\nX:bad', '/%2fsecret'):
            self.error(lambda: self.api.get(suffix))
        # Even direct permissive callbacks cannot bypass each fixed unavailable source.
        upload = core.Operation('UploadAsset', 5, create.subject_digest, 100,
                                asset_ordinal=0, asset=self.fixture.plan.assets[0])
        publish_op = core.Operation('PublishPrerelease', 24, create.subject_digest, 100,
                                   request_id='request', draft=False, prerelease=True)
        before = len(self.fixture.requests)
        for method in ('POST', 'PATCH', 'DELETE', 'PUT'):
            self.error(lambda: self.api._request(method, wire.API, wire.ROOT + '/releases', body=b'{}'))
        with authorities():
            self.error(lambda: self.api._request('POST', wire.API, wire.ROOT + '/releases',
                                                body=b'{}', op=create))
            self.error(lambda: self.api._request('PATCH', wire.UPLOAD, wire.ROOT + '/releases/100',
                                                body=b'{}', op=publish_op))
        with authorities():
            for change in ({'name': 'foreign.bin'}, {'family': 'foreign'}, {'media_type': 'text/plain'},
                           {'size': wire.FILE_LIMIT + 1}):
                bad = replace(upload, asset=replace(upload.asset, **change))
                self.error(lambda: self.api._request('POST', wire.UPLOAD, wire.ROOT +
                    '/releases/100/assets?name=' + bad.asset.name, stream=io.BytesIO(b'x'), asset=bad.asset, op=bad))
        with authorities(), patch.object(wire, '_authorize', side_effect=lambda *_: time.sleep(0.25)) as late:
            body = json.dumps({'tag_name': self.fixture.subject.tag, 'draft': True, 'prerelease': True,
                'make_latest': 'false', 'generate_release_notes': False}, separators=(',', ':'), sort_keys=True).encode()
            self.error(lambda: self.api._request('POST', wire.API, wire.ROOT + '/releases', body=body,
                op=create, deadline=time.monotonic() + 0.2))
            late.assert_called_once()
        self.assertEqual(len(self.fixture.requests), before)
        for op in (create, upload, publish_op):
            for passed in range(3):
                with self.subTest(kind=op.kind, passed=passed):
                    start = len(self.fixture.requests)
                    with patch.object(wire, '_authenticate', side_effect=gates if passed else
                                      lambda *args, **kwargs: (_ for _ in ()).throw(wire.WireFailure('fence_blocked', 'none'))):
                        with patch.object(wire, '_remote_constraint', side_effect=None if passed > 1 else
                                          lambda _: (_ for _ in ()).throw(wire.WireFailure('fence_blocked', 'none'))):
                            self.error(lambda: self.mutate(op))
                    self.assertEqual(len(self.fixture.requests), start)

    def test_complete_bounded_pagination_and_collision_rejection(self):
        path = wire.ROOT + '/releases?per_page=100&page='
        rows = [dict(self.fixture.stable, id=1000 + i, tag_name='v' + str(i)) for i in range(100)]
        self.fixture.routes['GET', path + '1'] = self.fixture.response(rows)
        self.fixture.routes['GET', path + '2'] = self.fixture.response([])
        observed = self.api.observe(self.transition.state, staged=self.fixture.plan.assets,
                                   gates=gates(self.fixture.selection)[0], draft_visibility='unknown')
        self.assertEqual(observed.draft_visibility, 'unknown')
        self.assertTrue(any(r[1] == path + '2' for r in self.fixture.requests))
        for bad in ([rows[0]], [dict(rows[0], id=9999)], [{'id': True, 'tag_name': 'x'}], {}, rows + [rows[0]]):
            self.fixture.routes['GET', path + '2'] = self.fixture.response(bad)
            self.error(lambda: self.api.observe(self.transition.state, staged=self.fixture.plan.assets,
                gates=gates(self.fixture.selection)[0], draft_visibility='proven'))
        self.fixture.routes.clear()
        def endless(method, target, headers, body):
            if target.startswith(path):
                page = int(target.rsplit('=', 1)[1])
                return self.fixture.response([dict(self.fixture.stable, id=page * 100 + i,
                    tag_name=f'v{page}-{i}') for i in range(100)])
        self.fixture.route = endless
        before = len(self.fixture.requests)
        self.error(lambda: self.api.observe(self.transition.state, staged=self.fixture.plan.assets,
            gates=gates(self.fixture.selection)[0], draft_visibility='proven'))
        self.assertEqual(sum(r[1].startswith(path) for r in self.fixture.requests[before:]), 100)

    def test_json_types_duplicates_limits_and_status_failures(self):
        target = wire.ROOT + '/fixture'
        bodies = (b'{"id":1,"id":2}', b'NaN', b'[] trailing', b'1', b'{"x":Infinity}',
                  b'{"x":1.5}', b'[' * 40 + b'0' + b']' * 40, b' ' * (wire.METADATA + 1))
        for body in bodies:
            with self.subTest(length=len(body)):
                self.fixture.routes['GET', target] = (200, {}, body)
                self.error(lambda: self.api.get('/fixture'))
        for status in (301, 302, 401, 403, 404, 429, 500, 502):
            self.fixture.routes['GET', target] = (status, {'Location': 'https://api.github.com'}, b'{}')
            self.error(lambda: self.api.get('/fixture'))
        for raw in (b'HTTP/1.1 200 X\r\nX: ' + b'a' * 32768 + b'\r\n\r\n',
                    b'HTTP/1.1 200 X\r\nContent-Length: 2\r\nContent-Length: 2\r\n\r\n{}',
                    b'HTTP/1.1 200 X\r\nContent-Length: 2\r\nTransfer-Encoding: chunked\r\n\r\n{}'):
            self.fixture.routes['GET', target] = {'raw': raw}
            self.error(lambda: self.api.get('/fixture'))
        self.fixture.routes['GET', target] = {'raw': b'HTTP/1.1 200 X\r\nTransfer-Encoding: chunked\r\n\r\n2\r\n{}\r\n0\r\n\r\n'}
        self.assertEqual(self.api.get('/fixture'), {})

    def test_six_ordered_descriptor_uploads_match_wire_bytes(self):
        with authorities():
            self.until('AwaitPublishRequest')
        uploads = [r for r in self.fixture.requests if r[0] == 'POST' and '/assets?' in r[1]]
        self.assertEqual(len(uploads), 6)
        for request, asset in zip(uploads, self.fixture.plan.assets):
            _, path, headers, body = request
            self.assertTrue(path.endswith('?name=' + asset.name))
            self.assertEqual(headers['host'], wire.UPLOAD)
            self.assertEqual(int(headers['content-length']), asset.size)
            self.assertEqual(headers['content-type'], asset.media_type)
            self.assertEqual(hashlib.sha256(body).hexdigest(), asset.sha256)
            self.assertEqual(body, self.fixture.payloads[asset.name])
        self.assertEqual(self.attempts, [2, 5, 8, 11, 14, 17, 20])
        self.assertEqual(len(self.trace), 22)

    def test_direct_binary_download_rehashes_exact_bytes(self):
        with authorities():
            op = self.until('VerifyAsset')
        remote = self.api.verify_asset(op)
        self.assertTrue(remote.matches_bytes())
        target = wire.ROOT + '/releases/assets/' + str(op.asset_id)
        row, original = self.fixture.assets[op.asset_id]
        for content in (original[:-1], original + b'X', b'X' * len(original)):
            self.fixture.assets[op.asset_id] = (row, content)
            self.error(lambda: self.api.verify_asset(op))
        self.fixture.assets[op.asset_id] = (dict(row, digest='sha256:' + '0' * 64), original)
        self.error(lambda: self.api.verify_asset(op))
        self.assertTrue(any(r[1] == target and r[2]['accept'] == 'application/octet-stream'
                            for r in self.fixture.requests))

    def test_single_storage_redirect_strips_credentials(self):
        with authorities():
            op = self.until('VerifyAsset')
        self.fixture.redirects[op.asset_id] = f'https://{wire.STORAGE}/asset/{op.asset_id}?sig=fixture-secret'
        self.assertTrue(self.api.verify_asset(op).matches_bytes())
        hops = self.fixture.requests[-2:]
        self.assertIn('authorization', hops[0][2])
        self.assertEqual(hops[1][2]['host'], wire.STORAGE)
        self.assertNotIn('authorization', hops[1][2])
        self.assertNotIn('cookie', hops[1][2])

    def test_unsafe_redirect_chain_hosts_and_ports_reject(self):
        with authorities():
            op = self.until('VerifyAsset')
        for location in ('http://' + wire.STORAGE + '/asset/200', 'https://evil.invalid/asset/200',
                         'https://' + wire.STORAGE + ':444/asset/200',
                         'https://user:password@' + wire.STORAGE + '/asset/200',
                         'https://' + wire.STORAGE + '/asset/200#fragment',
                         'https://' + wire.STORAGE + '//asset/200'):
            self.fixture.redirects[op.asset_id] = location
            before = len(self.fixture.requests)
            failure = self.error(lambda: self.api.verify_asset(op))
            self.assertEqual(len(self.fixture.requests) - before, 2)
            self.assertNotIn(location, str(failure))
        self.fixture.redirects[op.asset_id] = 'https://' + wire.STORAGE + '/asset/200'
        self.fixture.routes['GET', '/asset/200'] = (302, {'Location': 'https://' + wire.STORAGE + '/again'}, b'')
        self.error(lambda: self.api.verify_asset(op))
        self.assertFalse(any(r[1] == '/again' for r in self.fixture.requests))

    def test_upload_502_starter_is_uncertain_without_retry(self):
        with authorities():
            op = self.until('UploadAsset')
            target = wire.ROOT + '/releases/100/assets?name=' + op.asset.name
            self.fixture.routes['POST', target] = (502, {}, b'{"state":"starter"}')
            failure = self.error(lambda: self.mutate(op), 'unknown')
        self.assertIsNone(failure.asset)
        self.assertEqual(sum(r[0] == 'POST' and r[1] == target for r in self.fixture.requests), 1)
        stopped = core.advance(self.transition.state, core.OperationResult('OperationUncertain',
            op.operation_id, op.subject_digest, op.kind, failure.effect, code=failure.code))
        self.assertEqual(stopped.state.outcome, 'uncertain_remote_effect')
        self.assertEqual(core.advance(stopped.state, None), stopped)

    def test_disconnect_timeout_and_truncated_mutation_responses(self):
        with authorities():
            op = self.until('CreateDraft')
            target = wire.ROOT + '/releases'
            for response in ({}, {'raw': b'HTTP/1.1 201 X\r\nContent-Length: 100\r\n\r\n{}'},
                             {'raw': b'HTTP/1.1 201 X\r\nTransfer-Encoding: chunked\r\n\r\na\r\n{}'}):
                self.fixture.routes['POST', target] = response
                self.error(lambda: self.mutate(op), 'unknown')
            self.fixture.routes['POST', target] = {'delay': 0.2}
            def fast_timeout(host, timeout):
                sock = self.fixture.connect(host, timeout)
                original = sock.settimeout
                sock.settimeout = lambda value: original(min(value, 0.03))
                return sock
            with patch.object(wire, '_connect', side_effect=fast_timeout):
                self.assertEqual(self.error(lambda: self.mutate(op), 'unknown').code, 'timeout')
            self.fixture.routes.clear()
            def cleanup_fails(host, timeout):
                sock = self.fixture.connect(host, timeout)
                original = sock.close
                def close():
                    original()
                    raise OSError('fixture-private-token')
                sock.close = close
                return sock
            with patch.object(wire, '_connect', side_effect=cleanup_fails):
                failure = self.error(lambda: self.mutate(op), 'confirmed')
                self.assertEqual(failure.release_id, 100)
            with patch.object(wire, '_connect', side_effect=OSError('fixture-private-token')):
                self.error(lambda: self.mutate(op))

    def test_mismatched_success_retains_uncertain_effect(self):
        with authorities():
            op = self.until('CreateDraft')
            valid = {'id': 100, 'tag_name': self.fixture.subject.tag, 'draft': True, 'prerelease': True}
            for changes in ({'id': True}, {'id': 0}, {'tag_name': 'v0.0.0'}, {'draft': False}, {'prerelease': 1}):
                self.fixture.routes['POST', wire.ROOT + '/releases'] = self.fixture.response(dict(valid, **changes), 201)
                self.error(lambda: self.mutate(op), 'unknown')
            self.fixture.routes.clear()
            op = self.until('UploadAsset')
            for payload in (b'wrong', self.fixture.payloads[op.asset.name] + b'X'):
                self.error(lambda: self.api.upload_asset(op, io.BytesIO(payload), before_write=lambda: None,
                                                          check_active=lambda: None), 'unknown')
            target = wire.ROOT + '/releases/100/assets?name=' + op.asset.name
            row = {'id': 200, 'name': op.asset.name, 'content_type': op.asset.media_type, 'size': op.asset.size,
                   'digest': 'sha256:' + op.asset.sha256, 'state': 'uploaded'}
            for changes in ({'name': 'wrong'}, {'size': True}, {'digest': 'sha256:' + '0' * 64}, {'state': 'starter'}):
                self.fixture.routes['POST', target] = self.fixture.response(dict(row, **changes), 201)
                self.error(lambda: self.mutate(op), 'unknown')

    def test_anonymous_verification_and_latest_drift(self):
        with authorities():
            self.until('VerifyPublished')
            for ident in self.fixture.assets:
                self.fixture.redirects[ident] = f'https://{wire.STORAGE}/asset/{ident}'
            before = len(self.fixture.requests)
            self.step()
            self.assertEqual(self.transition.state.outcome, 'modeled_verified')
            self.assertEqual(len(self.trace), 25)
            self.assertTrue(all('authorization' not in r[2] for r in self.fixture.requests[before:]))
            original = self.api._latest(True, __import__('time').monotonic() + 30)
            self.fixture.latest.update(name='incidental', body='incidental', download_count=999)
            self.assertEqual(self.api._latest(True, __import__('time').monotonic() + 30), original)
            self.fixture.latest['target_commitish'] = 'changed'
            self.assertNotEqual(self.api._latest(True, __import__('time').monotonic() + 30), original)
            self.fixture.latest['id'] = 99
            self.error(lambda: self.api._latest(True, __import__('time').monotonic() + 30))
            subject = replace(self.fixture.subject, stable_latest_identity=stable_identity(False))
            self.fixture.selection.subject = subject
            self.fixture.latest = None
            deadline = __import__('time').monotonic() + 30
            self.error(lambda: self.api._latest(True, deadline))
            with patch.object(wire, '_authenticated_latest_absence', return_value=True):
                self.error(lambda: self.api._latest(True, deadline))
            with patch.object(wire, '_authenticated_latest_absence',
                              return_value=wire._LatestAbsent(wire.REPOSITORY, subject.source.source_sha)):
                before = len(self.fixture.requests)
                self.assertEqual(self.api._latest(True, deadline), subject.stable_latest_identity)
                self.assertTrue(all('authorization' not in r[2] for r in self.fixture.requests[before:]))
                with patch.object(wire, '_authenticate', return_value=((), 'denied')):
                    self.error(lambda: self.api._latest(True, deadline))

    def test_tls_validation_and_error_redaction(self):
        def untrusted(host, timeout):
            raw = socket.create_connection(('127.0.0.1', self.fixture.port), timeout)
            try:
                return ssl.create_default_context().wrap_socket(raw, server_hostname=host)
            except BaseException:
                raw.close()
                raise
        def wrong_hostname(host, timeout):
            return self.fixture.connect('unlisted.invalid', timeout)
        for factory in (untrusted, wrong_hostname):
            with patch.object(wire, '_connect', side_effect=factory):
                self.error(lambda: self.api.get('/releases/latest'))
        self.assertEqual(self.fixture.requests, [])
        with authorities():
            op = self.until('CreateDraft')
            for kind in (401, 403, 404, 409, 422, 502):
                self.fixture.routes['POST', wire.ROOT + '/releases'] = (kind, {},
                    b'fixture-private-token https://secret.invalid/?sig=private')
                failure = self.error(lambda: self.mutate(op), 'unknown')
                self.assertEqual(vars(failure), {'code': 'verification_failed', 'effect': 'unknown',
                                                 'release_id': None, 'asset': None})
        self.assertEqual(self.fixture.errors, [])


if __name__ == '__main__':
    unittest.main()
