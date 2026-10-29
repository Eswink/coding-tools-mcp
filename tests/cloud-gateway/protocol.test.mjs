import assert from 'node:assert/strict';
import test from 'node:test';
import { MODERN, LEGACY, VERSIONS, INFO_META, VERSION_META, CAPABILITIES_META,
  parseMessage, decodeName, validateVersion } from '../../prototypes/cloud-gateway/protocol.mjs';
import { fixture, message, post, request, probe } from './helpers.mjs';

test('modern discovery uses versioned complete result and separate server metadata', async t => {
  const lab = await fixture(t);
  const r = await post(lab, message('server/discover'));
  assert.equal(r.status, 200);
  assert.equal(r.body.result.resultType, 'complete');
  assert.deepEqual(r.body.result.supportedVersions, VERSIONS);
  assert.match(r.body.result._meta[INFO_META].name, /lab/);
  assert.equal(r.body.result.serverInfo, undefined);
  assert.equal(r.body.result.protocolVersion, undefined);
  assert.equal(r.headers['mcp-session-id'], undefined);
});

for (const version of LEGACY) {
  test(`legacy ${version} handshake and tool errors do not use modern fields`, async t => {
    const lab = await fixture(t);
    const initialize = message('initialize', { protocolVersion: version, capabilities: {},
      clientInfo: { name: 'lab-client', version: '1' } }, { version });
    const init = await post(lab, initialize, { version, omit: ['MCP-Protocol-Version'] });
    assert.equal(init.status, 200);
    assert.equal(init.body.result.protocolVersion, version);
    assert.equal(init.body.result.resultType, undefined);
    const ready = message('notifications/initialized', {}, { version });
    delete ready.id;
    const notification = await post(lab, ready, { version });
    assert.equal(notification.status, 202);
    assert.equal(notification.text, '');
    const r = await post(lab, message('tools/call', { name: 'workspace_probe' }, { version }), { version });
    assert.equal(r.status, 200);
    assert.equal(r.body.result.isError, true);
    assert.equal(r.body.result.resultType, undefined);
  });
}

test('unknown modern version returns typed version error with supported set', async t => {
  const lab = await fixture(t);
  const r = await post(lab, message('server/discover'), { version: '2099-01-01' });
  assert.equal(r.status, 400);
  assert.equal(r.body.error.code, -32022);
  assert.deepEqual(r.body.error.data.supported, VERSIONS);
  assert.equal(r.body.error.data.requested, '2099-01-01');
});

test('modern missing/mismatching protocol, method and name headers fail closed', async t => {
  const lab = await fixture(t);
  for (const options of [
    { omit: ['MCP-Protocol-Version'] }, { omit: ['Mcp-Method'] }, { omit: ['Mcp-Name'] },
    { headers: { 'Mcp-Method': 'tools/list' } }, { headers: { 'Mcp-Name': 'auth_status' } },
  ]) {
    const r = await post(lab, probe(), options);
    assert.equal(r.status, 400);
    assert.equal(r.body.error.code, -32020);
  }
  const body = probe(); body.params._meta[VERSION_META] = LEGACY[0];
  assert.equal((await post(lab, body)).body.error.code, -32020);
  assert.equal(lab.state.statsForTest().dispatches, 0);
});

test('per-request capabilities are required, not inherited from discovery', async t => {
  const lab = await fixture(t);
  await post(lab, message('server/discover'));
  const body = probe(); delete body.params._meta[CAPABILITIES_META];
  const r = await post(lab, body);
  assert.equal(r.status, 400); assert.equal(r.body.error.code, -32602);
});

test('no legacy downgrade for modern metadata', async t => {
  const lab = await fixture(t);
  const r = await post(lab, probe(), { version: LEGACY[0] });
  assert.equal(r.status, 400); assert.equal(r.body.error.code, -32020);
});

test('Base64 name is decoded before comparison, invalid UTF-8 is rejected', async t => {
  const lab = await fixture(t);
  const encoded = '=?base64?' + Buffer.from('workspace_probe').toString('base64') + '?=';
  assert.equal((await post(lab, probe(), { headers: { 'Mcp-Name': encoded } })).status, 200);
  assert.equal(decodeName('=?base64?' + Buffer.from('工具').toString('base64') + '?='), '工具');
  const body = message('tools/call', { name: '工具' });
  assert.equal(validateVersion(body, { 'mcp-protocol-version': MODERN, 'mcp-method': 'tools/call',
    'mcp-name': '=?base64?' + Buffer.from('工具').toString('base64') + '?=' }), MODERN);
  for (const name of ['=?base64?%%%?=', '=?base64?/w==?=', '=?base64?Zh==?=']) {
    const r = await post(lab, probe(), { headers: { 'Mcp-Name': name } });
    assert.equal(r.status, 400); assert.equal(r.body.error.code, -32020);
  }
});

test('unknown RPC is a protocol error, not a fabricated tool result', async t => {
  const lab = await fixture(t);
  for (const method of ['not/a/method', 'initialize', 'ping']) {
    const r = await post(lab, message(method));
    assert.equal(r.status, 404); assert.equal(r.body.error.code, -32601);
  }
  const r = await post(lab, message('tools/call', { name: 'exec_command' }));
  assert.equal(r.status, 400); assert.equal(r.body.error.code, -32602);
});

test('GET/DELETE/OPTIONS do not advertise sessions or browser CORS', async t => {
  const lab = await fixture(t);
  for (const method of ['GET', 'DELETE', 'OPTIONS']) {
    const r = await request(lab.endpoint, { method });
    assert.equal(r.status, 405); assert.equal(r.headers.allow, 'POST');
    assert.equal(r.headers['access-control-allow-origin'], undefined);
  }
  const r = await post(lab, message('tools/list'), {
    headers: { 'Mcp-Session-Id': 'not-authority', 'Last-Event-ID': 'ignored' },
  });
  assert.equal(r.status, 200); assert.equal(r.headers['mcp-session-id'], undefined);
});

test('invalid JSON and shapes reject without invoking a fixture', async t => {
  const lab = await fixture(t);
  for (const raw of ['{', 'null', '[]', '1', '{"jsonrpc":"2.0","method":"tools/list","id":null}',
    '{"jsonrpc":"2.0","method":"tools/list","id":true}',
    '{"jsonrpc":"2.0","method":"tools/list","id":1,"params":[]}']) {
    const r = await post(lab, message('tools/list'), { raw });
    assert.equal(r.status, 400);
    assert.ok([-32700, -32600].includes(r.body.error.code));
  }
  assert.throws(() => parseMessage(Buffer.from([0xff])), /Invalid JSON/);
  assert.equal(lab.state.statsForTest().dispatches, 0);
});
