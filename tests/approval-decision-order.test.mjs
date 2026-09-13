/** Run the actual production decision function with synthetic IPC and UI state.
 * These are function-level regressions, not Svelte DOM/native-window acceptance.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const sourceRoot = process.env.APPROVAL_SOURCE_ROOT || root;
const host = readFileSync(path.join(sourceRoot, 'src/lib/components/ChatAuthorizationHost.svelte'), 'utf8');
const script = host.match(/<script[^>]*>([\s\S]*?)<\/script>/)?.[1];
assert.ok(script, 'production host script is required');
const ast = ts.createSourceFile('host.ts', script, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
const decision = ast.statements.find(node => ts.isFunctionDeclaration(node) && node.name?.text === 'decide');
assert.ok(decision?.body, 'production decide function is required');
const transpile = source => ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const exports = {};
new Function('exports', transpile(readFileSync(path.join(root, 'src/lib/chat-authorization.ts'), 'utf8')))(exports);

const row = () => ({ workspaceId: 'fixture-workspace', grant: { id: 'fixture-request',
  fingerprint: 'fixture-fingerprint', status: 'pending', scopes: ['files.read', 'exec.run'],
  created_at: 1, expires_at: 100, idle_expires_at: 100 } });
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function harness(options = {}) {
  const gate = deferred();
  const create = new Function('canApprove', 'initial', 'gate', `
    let selected = initial.selected === undefined ? initial.row : initial.selected;
    let selectedScopes = initial.scopes ?? ['files.read'];
    let verified = initial.verified ?? true;
    let now = initial.now ?? 10;
    let busy = false, disposed = false, error = '';
    const calls = [], events = [];
    const invoke = (name, args) => { calls.push({name, args}); events.push({name:'invoke', busy}); return gate.promise; };
    const dismiss = () => { events.push({name:'dismiss', busy}); selected = null; verified = false; };
    const refresh = async () => { events.push({name:'refresh', busy}); };
    ${transpile(decision.getText(ast))}
    return { decide, calls, events, dispose: () => { disposed = true; },
      inspect: () => ({ selected, selectedScopes, verified, busy, error }) };
  `);
  return { gate, ui: create(exports.canApprove, { row: row(), ...options }, gate) };
}

test('approval completion releases busy before refreshing the next inbox candidate', async () => {
  const { ui, gate } = harness();
  const work = ui.decide(true);
  assert.equal(ui.inspect().busy, true);
  assert.equal(ui.events.some(e => e.name === 'refresh'), false);
  gate.resolve({});
  await work;
  assert.deepEqual(ui.events, [{name:'invoke', busy:true}, {name:'dismiss', busy:true}, {name:'refresh', busy:false}]);
  assert.equal(ui.inspect().verified, false);
  assert.equal(ui.inspect().busy, false);
});

test('repeated approval clicks produce only one privileged IPC decision', async () => {
  const { ui, gate } = harness();
  const work = ui.decide(true);
  await ui.decide(true);
  assert.equal(ui.calls.length, 1);
  gate.resolve({});
  await work;
});

test('decision targets the selected workspace and only the confirmed scope subset', async () => {
  const { ui, gate } = harness();
  const work = ui.decide(true);
  assert.deepEqual(ui.calls, [{name:'chat_authorization_control', args:{id:'fixture-workspace',
    action:'approve', requestId:'fixture-request', scopes:['files.read'], exclusive:null}}]);
  gate.resolve({});
  await work;
});

test('failed decision leaves the candidate visible and never runs success refresh', async () => {
  const { ui, gate } = harness();
  const work = ui.decide(true);
  gate.reject(new Error('synthetic IPC failure'));
  await work;
  assert.equal(ui.inspect().error, 'Error: synthetic IPC failure');
  assert.equal(ui.inspect().selected.grant.id, 'fixture-request');
  assert.equal(ui.inspect().busy, false);
  assert.deepEqual(ui.events, [{name:'invoke', busy:true}]);
});

test('disposal while the decision is pending suppresses later UI effects', async () => {
  const { ui, gate } = harness();
  const work = ui.decide(true);
  ui.dispose();
  gate.resolve({});
  await work;
  assert.deepEqual(ui.events, [{name:'invoke', busy:true}]);
});

test('no selected candidate cannot invoke a privileged decision', async () => {
  const { ui } = harness({selected:null});
  await ui.decide(true);
  assert.equal(ui.calls.length, 0);
});

test('unconfirmed, empty, expanded or expired permissions are not approved', async () => {
  for (const options of [{verified:false}, {scopes:[]}, {scopes:['harness.write']}, {now:100}]) {
    const { ui } = harness(options);
    await ui.decide(true);
    assert.equal(ui.calls.length, 0, JSON.stringify(options));
    assert.equal(ui.inspect().busy, false);
  }
});

test('local rejection does not require fingerprint confirmation or send approval scopes', async () => {
  const { ui, gate } = harness({verified:false, scopes:[]});
  const work = ui.decide(false);
  assert.equal(ui.calls[0].args.action, 'deny');
  assert.equal(ui.calls[0].args.scopes, null);
  gate.resolve({});
  await work;
  assert.equal(ui.events.at(-1).busy, false);
});
