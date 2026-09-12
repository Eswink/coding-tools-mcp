/** Actual TS unit tests and Svelte compiler/AST contracts, not native UI evidence. */
import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { compile, parse } from 'svelte/compiler';
import ts from 'typescript';

const read = (name) => readFileSync(new URL('../' + name, import.meta.url), 'utf8');
function loadTs(name, dependencies = {}) {
  const source = read(name);
  const result = ts.transpileModule(source, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
    reportDiagnostics: true,
  });
  assert.equal((result.diagnostics ?? []).length, 0);
  const exports = {};
  new Function('require', 'exports', result.outputText)((name) => {
    assert.ok(name in dependencies, `unexpected dependency: ${name}`);
    return dependencies[name];
  }, exports);
  return exports;
}
function deferred() {
  let resolve, reject;
  const promise = new Promise((a, b) => { resolve = a; reject = b; });
  return { promise, resolve, reject };
}
function secretsApi(invoke) {
  let current;
  const states = [];
  const api = loadTs('src/lib/api/secrets.ts', {
    '@tauri-apps/api/core': { invoke },
    'svelte/store': { writable(initial) {
      current = initial;
      return { update(fn) { current = fn(current); states.push(current); } };
    } },
  });
  return { api, states, snapshot: () => current };
}

test('request tickets reject stale results after navigation or a newer request', async () => {
  const { latestRequest } = loadTs('src/lib/runtime/latest-request.ts');
  const requests = latestRequest();
  const old = requests.begin();
  const next = requests.begin();
  assert.equal(requests.current(old), false);
  assert.equal(requests.current(next), true);
  requests.invalidate();
  assert.equal(requests.current(next), false);
  let published = '';
  const delay = deferred();
  const ticket = requests.begin();
  const task = delay.promise.then((value) => { if (requests.current(ticket)) published = value; });
  requests.invalidate();
  delay.resolve('old-workspace-secret');
  await task;
  assert.equal(published, '');
});

test('credential reads do not invalidate or share credential bytes', async () => {
  const h = secretsApi(async () => 'private-fixture');
  assert.equal(await h.api.getSecret('fixture', 'oauth_client_secret'), 'private-fixture');
  assert.deepEqual(h.snapshot(), { revision: 0, pending: 0 });
  assert.deepEqual(h.states, []);
});

test('writes invalidate before and after success without placing secrets in state', async () => {
  const call = deferred();
  const h = secretsApi(() => call.promise);
  const result = h.api.setSecret('fixture', 'oauth_client_secret', 'canary-secret');
  assert.deepEqual(h.snapshot(), { revision: 1, pending: 1 });
  call.resolve(); await result;
  assert.deepEqual(h.snapshot(), { revision: 2, pending: 0 });
  assert.ok(!JSON.stringify(h.states).includes('canary-secret'));
});

test('restart failure still invalidates and preserves the original rejection', async () => {
  const failure = new Error('saved but application failed');
  const h = secretsApi(async () => { throw failure; });
  await assert.rejects(h.api.regenerateSharedSecret('oauth_password'), (error) => error === failure);
  assert.deepEqual(h.snapshot(), { revision: 2, pending: 0 });
});

test('overlapping workspace/shared updates do not clear the pending fence early', async () => {
  const calls = [deferred(), deferred()]; let index = 0;
  const h = secretsApi(() => calls[index++].promise);
  const a = h.api.setSharedSecret('oauth_client_id', 'fixture');
  const b = h.api.regenerateWorkspaceSecret('fixture', 'oauth_password');
  assert.equal(h.snapshot().pending, 2);
  calls[0].resolve(); await a;
  assert.equal(h.snapshot().pending, 1);
  calls[1].resolve('new-fixture');
  assert.equal(await b, 'new-fixture');
  assert.deepEqual(h.snapshot(), { revision: 4, pending: 0 });
});

const files = ['HealthPanel', 'CopyFieldRow', 'SecretInput', 'GptQuickCopy'];
test('modified credential and health Svelte components compile without warnings', () => {
  for (const file of files) {
    const result = compile(read(`src/lib/components/${file}.svelte`), { generate: 'client' });
    assert.deepEqual(result.warnings, [], file);
  }
});

test('every quick-copy credential is explicitly masked, while public IDs remain readable', () => {
  const source = read('src/lib/components/GptQuickCopy.svelte');
  const ast = parse(source, { modern: true });
  const rows = [];
  const visit = (node) => {
    if (!node || typeof node !== 'object') return;
    if (node.type === 'Component' && node.name === 'CopyFieldRow') rows.push(node);
    for (const value of Object.values(node)) {
      if (Array.isArray(value)) value.forEach(visit);
      else if (value && typeof value === 'object') visit(value);
    }
  };
  visit(ast.fragment);
  let masked = 0;
  for (const row of rows) {
    const label = row.attributes.find((attribute) => attribute.name === 'label')?.value?.[0]?.data;
    const secret = row.attributes.find((attribute) => attribute.name === 'secret');
    if (['OAuth Client Secret', '授权口令', 'Bearer Token', 'API Key（Bearer）'].includes(label)) {
      assert.equal(secret?.value, true, label); masked++;
    } else assert.equal(secret, undefined, label);
  }
  assert.equal(masked, 5);
  assert.match(source, /\$credentialState\.pending > 0/);
  assert.doesNotMatch(source, /secrets\.oauth_client_id \?\? auth\.oauth_client_id/);
});

test('secret defaults, stale health results and skipped checks cannot display false success', () => {
  for (const file of ['CopyFieldRow', 'SecretInput']) {
    const source = read(`src/lib/components/${file}.svelte`);
    assert.match(source, /visible = \$state\(false\)/);
    assert.doesNotMatch(source, /visible = \$state\(true\)/);
  }
  const health = read('src/lib/components/HealthPanel.svelte');
  assert.match(health, /requests\.current\(ticket\) && id === workspaceId/);
  assert.match(health, /item\.skipped \? "未执行" : item\.ok \? "通过" : "失败"/);
  assert.doesNotMatch(health, /error = String\(err\)/);
});
