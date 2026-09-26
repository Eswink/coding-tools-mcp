import assert from 'node:assert/strict';
import test from 'node:test';
import { SyntheticWorkspace } from '../../prototypes/cloud-gateway/state.mjs';
import { fixture, message, post, probe } from './helpers.mjs';

const bodyData = response => response.body.result.structuredContent;
const authCall = (name, session = 'lab-owner', args = {}) =>
  message('tools/call', { name, arguments: args }, { session });

test('online -> offline -> online preserves catalog, listener and existing grant', async t => {
  const lab = await fixture(t);
  const catalog = await post(lab, message('tools/list'));
  const discovery = await post(lab, message('server/discover'));
  lab.state.setOnlineForTest(true);
  const online = await post(lab, probe());
  assert.equal(online.status, 200); assert.equal(bodyData(online).synthetic, true);
  assert.equal(online.body.result.isError, false);
  lab.state.setOnlineForTest(false);
  const offline = await post(lab, probe());
  assert.equal(offline.status, 200);
  assert.equal(offline.body.result.resultType, 'complete');
  assert.equal(offline.body.result.isError, true);
  assert.equal(bodyData(offline).error.code, 'WORKSPACE_OFFLINE');
  assert.equal(offline.headers['www-authenticate'], undefined);
  assert.ok(!offline.text.includes('mcp/www_authenticate'));
  assert.equal(bodyData(offline).error.retryable, false);
  assert.equal((await post(lab, message('tools/list'))).text, catalog.text);
  assert.equal((await post(lab, message('server/discover'))).text, discovery.text);
  assert.equal(bodyData(await post(lab, authCall('auth_status'))).authorization.status, 'active');
  lab.state.setOnlineForTest(true);
  assert.equal(bodyData(await post(lab, probe())).ok, true);
  assert.equal(lab.state.statsForTest().dispatches, 2);
});

test('foreign conversations get identical non-disclosing responses across presence changes', async t => {
  const lab = await fixture(t);
  for (const tool of ['workspace_probe', 'auth_status', 'request_chat_authorization']) {
    lab.state.setOnlineForTest(true);
    const before = await post(lab, authCall(tool, 'unapproved-chat'));
    lab.state.setOnlineForTest(false);
    const after = await post(lab, authCall(tool, 'unapproved-chat'));
    assert.equal(before.text, after.text);
    assert.equal(bodyData(after).error.code, 'EXCLUSIVE_CHAT_LOCKED');
    for (const secret of ['lab-owner', 'fingerprint', 'expires', 'workspace_id', 'path', 'task_id', 'online', 'offline']) {
      assert.ok(!after.text.includes(secret), secret);
    }
  }
  assert.deepEqual(lab.state.statsForTest(), { dispatches: 0, pendingAllocations: 0 });
});

test('offline unapproved requests allocate no pending; online request reserves once', async t => {
  const state = new SyntheticWorkspace();
  const lab = await fixture(t, { state });
  for (let i = 0; i < 25; i++) {
    const r = await post(lab, authCall('request_chat_authorization', 'new-chat'));
    assert.equal(bodyData(r).error.code, 'CHAT_AUTHORIZATION_UNAVAILABLE');
    assert.equal(r.headers['www-authenticate'], undefined);
  }
  assert.equal(state.statsForTest().pendingAllocations, 0);
  assert.equal(bodyData(await post(lab, probe('new-chat'))).error.code, 'CHAT_AUTHORIZATION_REQUIRED');
  state.setOnlineForTest(true);
  assert.equal(bodyData(await post(lab, authCall('request_chat_authorization', 'new-chat'))).authorization.status, 'pending');
  state.setOnlineForTest(false);
  assert.equal(bodyData(await post(lab, authCall('request_chat_authorization', 'new-chat'))).authorization.status, 'pending');
  assert.equal(state.statsForTest().pendingAllocations, 1);
  assert.equal(bodyData(await post(lab, authCall('request_chat_authorization', 'another-chat'))).error.code, 'EXCLUSIVE_CHAT_LOCKED');
});

test('missing, oversized, invalid context cannot disclose availability', async t => {
  const lab = await fixture(t);
  for (const session of [undefined, null, '', 'a\nsecret', 'x'.repeat(257), 1]) {
    const body = probe(); body.params._meta['openai/session'] = session;
    const r = await post(lab, body);
    assert.equal(bodyData(r).error.code, 'CHAT_CONTEXT_REQUIRED');
    assert.equal(r.headers['www-authenticate'], undefined);
  }
});

test('recovery, scope, expiry and revocation outrank availability', async t => {
  let now = 100;
  const state = new SyntheticWorkspace({ clock: () => now });
  const lab = await fixture(t, { state });
  state.approveForTest('lab-owner', { scopes: [] });
  assert.equal(bodyData(await post(lab, probe())).error.code, 'CHAT_SCOPE_REQUIRED');
  state.setRecoveryForTest(true);
  assert.equal(bodyData(await post(lab, probe())).error.code, 'CHAT_RECOVERY_REQUIRED');
  state.setRecoveryForTest(false);
  state.approveForTest('lab-owner', { ttlMs: 10 });
  now += 11;
  assert.equal(bodyData(await post(lab, probe())).error.code, 'CHAT_AUTHORIZATION_REQUIRED');
  state.setOnlineForTest(true);
  assert.equal(bodyData(await post(lab, probe())).error.code, 'CHAT_AUTHORIZATION_REQUIRED');
  state.approveForTest('lab-owner');
  state.revokeForTest('lab-owner');
  assert.equal(bodyData(await post(lab, probe())).error.code, 'CHAT_AUTHORIZATION_REQUIRED');
  assert.equal(state.statsForTest().dispatches, 0);
});

test('unknown outcome is distinct from known offline and is not silently retried', async t => {
  const lab = await fixture(t);
  lab.state.setOnlineForTest(true);
  lab.state.setUnknownOutcomeForTest(true);
  const r = await post(lab, probe());
  assert.equal(r.status, 200);
  assert.equal(bodyData(r).error.code, 'EXECUTION_OUTCOME_UNKNOWN');
  assert.equal(r.body.result.isError, true);
  assert.equal(r.headers['www-authenticate'], undefined);
  assert.equal(lab.state.statsForTest().dispatches, 1);
  lab.state.setOnlineForTest(false);
  assert.equal(bodyData(await post(lab, probe())).error.code, 'WORKSPACE_OFFLINE');
  assert.equal(lab.state.statsForTest().dispatches, 1);
  // This tests classification/one dispatch, NOT distributed exactly-once execution.
});

test('schema-invalid tool arguments fail without allocation or dispatch', async t => {
  const lab = await fixture(t);
  lab.state.setOnlineForTest(true);
  for (const args of [null, [], 5, { path: '/etc/passwd' }, { scopes: ['exec.run'] }]) {
    const r = await post(lab, authCall('workspace_probe', 'lab-owner', args));
    assert.equal(bodyData(r).error.code, 'INVALID_ARGUMENTS');
  }
  for (const args of [{ scopes: [] }, { scopes: ['exec.run'] }, { approve: true }]) {
    const r = await post(lab, authCall('request_chat_authorization', 'lab-owner', args));
    assert.equal(bodyData(r).error.code, 'INVALID_ARGUMENTS');
  }
  assert.equal(lab.state.statsForTest().dispatches, 0);
});
