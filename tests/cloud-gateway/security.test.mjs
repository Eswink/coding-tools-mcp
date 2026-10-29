import assert from 'node:assert/strict';
import test from 'node:test';
import http from 'node:http';
import { startLab } from '../../prototypes/cloud-gateway/gateway.mjs';
import { fixture, message, post, request, probe } from './helpers.mjs';

for (const host of ['0.0.0.0', '::', '192.168.0.1', 'localhost']) {
  test(`public/nonliteral bind ${host} is unavailable even with opt-in`, async () => {
    await assert.rejects(startLab({ lab: true, host, bearerToken: 'a'.repeat(64) }), /loopback/);
  });
}

test('start requires explicit lab mode and strong synthetic token', async () => {
  await assert.rejects(startLab({ bearerToken: 'a'.repeat(64) }), /Explicit/);
  for (const bearerToken of [undefined, '', 'weak', 'secret\n'.repeat(8), ' '.repeat(32)]) {
    await assert.rejects(startLab({ lab: true, bearerToken }), /synthetic bearer token/);
  }
});

test('real auth rejection is not converted to WORKSPACE_OFFLINE', async t => {
  const lab = await fixture(t);
  for (const options of [{ omit: ['Authorization'] }, { headers: { Authorization: `Bearer ${'b'.repeat(64)}` } }]) {
    const r = await post(lab, probe(), options);
    assert.equal(r.status, 401);
    assert.match(r.headers['www-authenticate'], /Bearer/);
    assert.ok(!r.text.includes('WORKSPACE_OFFLINE'));
  }
  assert.equal(lab.state.statsForTest().dispatches, 0);
});

test('Host/Origin are local exact origins; forwarded headers never confer trust', async t => {
  const lab = await fixture(t);
  for (const headers of [
    { Host: 'foreign.example:80' }, { Host: '127.0.0.1:1' },
    { Origin: 'https://foreign.example' }, { Origin: 'null' },
    { Origin: new URL(lab.endpoint).origin + '/' }, { Origin: 'not an origin' },
    { Origin: 'https://foreign.example', 'X-Forwarded-Host': new URL(lab.endpoint).host },
    { Host: 'foreign.example', 'X-Forwarded-Host': new URL(lab.endpoint).host },
  ]) {
    const r = await post(lab, probe(), { headers });
    assert.equal(r.status, 403);
    assert.equal(r.headers['www-authenticate'], undefined);
  }
  assert.equal((await post(lab, message('tools/list'), { headers: { Origin: new URL(lab.endpoint).origin } })).status, 200);
});

test('duplicate security and mirrored headers fail closed', async t => {
  const lab = await fixture(t);
  for (const duplicate of ['Host', 'Origin', 'Authorization', 'Mcp-Method', 'Mcp-Name', 'MCP-Protocol-Version']) {
    const rawHeaders = [
      'Host', new URL(lab.endpoint).host, 'Origin', new URL(lab.endpoint).origin,
      'Authorization', `Bearer ${lab.token}`, 'Content-Type', 'application/json',
      'Accept', 'application/json, text/event-stream', 'MCP-Protocol-Version', '2026-07-28',
      'Mcp-Method', 'tools/call', 'Mcp-Name', 'workspace_probe', duplicate, 'invalid-duplicate',
    ];
    const r = await request(lab.endpoint, { method: 'POST', headers: rawHeaders }, JSON.stringify(probe()));
    assert.ok([400, 403].includes(r.status));
    assert.equal(r.headers['www-authenticate'], undefined);
  }
  assert.equal(lab.state.statsForTest().dispatches, 0);
});

test('no remote administration or arbitrary upstream route', async t => {
  const lab = await fixture(t);
  for (const path of ['/admin/approve', '/agent/connect', '/mcp?upstream=http://127.0.0.1', 'http://foreign.example/mcp']) {
    const r = await post(lab, message('tools/list'), { path });
    assert.equal(r.status, 404);
  }
});

test('bounded payload and unsupported content/Accept reject generically', async t => {
  const lab = await fixture(t);
  for (const headers of [{ 'Content-Type': 'text/plain' }, { 'Content-Encoding': 'gzip' }]) {
    assert.equal((await post(lab, probe(), { headers })).status, 415);
  }
  for (const accept of ['application/json', 'text/event-stream', 'application/json;q=0, text/event-stream']) {
    assert.equal((await post(lab, probe(), { headers: { Accept: accept } })).status, 406);
  }
  const oversized = 'secret-canary'.repeat(6000);
  for (const headers of [{ 'Content-Length': String(Buffer.byteLength(oversized)) }, { 'Transfer-Encoding': 'chunked' }]) {
    const r = await post(lab, probe(), { raw: oversized, headers });
    assert.equal(r.status, 413);
    assert.ok(!r.text.includes('secret-canary'));
  }
});

test('incomplete body hits explicit total deadline and listener remains usable', async t => {
  const lab = await fixture(t, { readTimeoutMs: 80 });
  const status = await new Promise((resolve, reject) => {
    const req = http.request(lab.endpoint, { method: 'POST', headers: {
      Authorization: `Bearer ${lab.token}`, 'Content-Type': 'application/json',
      Accept: 'application/json, text/event-stream', 'Content-Length': '2000',
    } }, res => { res.resume(); res.on('end', () => resolve(res.statusCode)); });
    req.on('error', reject);
    req.setTimeout(3000, () => req.destroy(new Error('Test exceeded deadline')));
    req.write('{'); // Deliberately never finish body.
  });
  assert.equal(status, 408);
  assert.equal((await post(lab, message('tools/list'))).status, 200);
});

test('concurrent offline calls stay bounded and do not enter the executor', async t => {
  const lab = await fixture(t);
  const responses = await Promise.all(Array.from({ length: 16 }, () => post(lab, probe())));
  for (const r of responses) {
    assert.equal(r.status, 200);
    assert.equal(r.body.result.structuredContent.error.code, 'WORKSPACE_OFFLINE');
    assert.equal(r.headers['cache-control'], 'no-store');
  }
  assert.equal(lab.state.statsForTest().dispatches, 0);
});
