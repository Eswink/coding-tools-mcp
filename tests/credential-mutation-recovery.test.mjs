/** Executes unchanged production function bodies with controlled IPC promises.
 * These are behavioral boundary tests, not DOM, native, or public-deployment evidence.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';

const read = (p) => readFileSync(new URL('../' + p, import.meta.url), 'utf8');
function functions(file, state) {
  const source = read(file).split('<script lang="ts">')[1].split('</script>')[0];
  const ast = ts.createSourceFile(file + '.ts', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
  const nodes = ast.statements.filter(ts.isFunctionDeclaration);
  const code = nodes.map((node) => node.getText(ast).replace(/^export /, '')).join('\n');
  const js = ts.transpileModule(code, { compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.None,
  } }).outputText;
  return new Function('state', `with (state) { ${js}; return {${nodes.map((n) => n.name.text).join(',')}}; }`)(state);
}
function module(file) {
  const exports = {};
  const js = ts.transpileModule(read(file), { compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS,
  } }).outputText;
  new Function('exports', 'require', js)(exports, (key) => {
    assert.equal(key, 'svelte/store'); return { writable: () => ({ update() {} }) };
  });
  return exports;
}
const { latestRequest } = module('src/lib/runtime/latest-request.ts');
const { applyAndRefresh } = module('src/lib/runtime/configuration.ts');
function deferred() {
  let resolve, reject;
  const promise = new Promise((a, b) => { resolve = a; reject = b; });
  return { promise, resolve, reject };
}
const failure = new Error('fixture: persisted, then restart failed');
function mcp(overrides = {}) {
  const state = {
    workspaceId: 'A', disposed: false, draft: { type: 'oauth', use_shared_secrets: false, oauth_client_id: 'private-draft' },
    auth: { type: 'oauth', oauth_client_id: 'saved-id' }, dirty: true,
    secrets: { oauth_client_secret: 'old' }, loadedSharedOauthClientId: '',
    saving: false, regenerating: null, loadingSecrets: false, secretsError: '', suppressSecretsReload: false,
    secretRequests: latestRequest(), operationRequests: latestRequest(), applyAndRefresh,
    getWorkspaceSecret: async () => 'canonical', getSharedSecret: async () => 'shared-canonical',
    regenerateWorkspaceSecret: async () => { throw failure; }, regenerateSharedSecret: async () => { throw failure; },
    onSaveProfile: async () => { throw failure; }, messages: [],
    ...overrides,
  };
  state.message = async (text) => { state.messages.push(text); };
  return { state, ...functions('src/lib/components/AuthConfigForm.svelte', state) };
}
function actions(overrides = {}) {
  const state = {
    workspaceId: 'A', disposed: false, draftUseShared: false, dirty: true,
    draftAuthType: 'oauth', draftOauthClientId: 'id', draftOauthScopes: '',
    credentialsBusy: false, saving: false, secretsError: '', suppressSecretsReload: false,
    apiKey: 'old', loadedApiKey: 'old', oauthClientSecret: 'old', loadedOauthClientSecret: 'old',
    oauthPassword: 'old', loadedOauthPassword: 'old', oauthTokenSecret: 'old', loadedOauthTokenSecret: 'old',
    loadingKey: false, loadingOAuthSecret: false, loadingOAuthPassword: false, loadingOAuthTokenSecret: false,
    regenerating: false, regeneratingOAuthSecret: false, regeneratingOAuthPassword: false, regeneratingOAuthTokenSecret: false,
    secretRequests: latestRequest(), operationRequests: latestRequest(), applyAndRefresh,
    getSecret: async () => 'canonical', getSharedSecret: async () => 'shared-canonical',
    regenerateSecret: async () => { throw failure; }, regenerateSharedSecret: async () => { throw failure; },
    onSave: async () => { throw failure; }, messages: [], ...overrides,
  };
  state.message = async (text) => { state.messages.push(text); };
  return { state, ...functions('src/lib/components/ActionsAuthForm.svelte', state) };
}

for (const shared of [false, true]) {
  test(`MCP rotation failure reads persisted truth (shared=${shared})`, async () => {
    const h = mcp(); h.state.draft.use_shared_secrets = shared;
    await h.regenerate('oauth_client_secret');
    assert.equal(h.state.secrets.oauth_client_secret, shared ? 'shared-canonical' : 'canonical');
    assert.match(h.state.messages[0], /persisted, then restart failed/);
    assert.equal(h.state.regenerating, null);
  });
  test(`Actions rotation failure reads persisted truth (shared=${shared})`, async () => {
    const h = actions({ draftUseShared: shared });
    await h.regenerateCredential('secret', 'actions_oauth_client_secret', 'actions_oauth_client_secret');
    assert.equal(h.state.oauthClientSecret, shared ? 'shared-canonical' : 'canonical');
    assert.match(h.state.messages[0], /persisted, then restart failed/);
  });
}
test('MCP failed save also refreshes credentials', async () => {
  const h = mcp(); await h.save();
  assert.equal(h.state.secrets.oauth_client_secret, 'canonical');
  assert.equal(h.state.saving, false);
});
test('Actions failed save also refreshes credentials', async () => {
  const h = actions(); await h.save();
  assert.equal(h.state.oauthClientSecret, 'canonical');
  assert.equal(h.state.saving, false);
});
test('failed canonical reads clear all MCP credentials and block further mutation', async () => {
  const h = mcp({ getWorkspaceSecret: async () => { throw new Error('read failed'); } });
  await h.regenerate('oauth_client_secret');
  assert.deepEqual(h.state.secrets, {}); assert.ok(h.state.secretsError);
  assert.match(h.state.messages[0], /persisted, then restart failed/);
});
test('failed canonical reads clear all Actions credentials', async () => {
  const h = actions({ getSecret: async () => { throw new Error('read failed'); } });
  await h.regenerateCredential('secret', 'actions_oauth_client_secret', 'actions_oauth_client_secret');
  assert.equal(h.state.oauthClientSecret, ''); assert.equal(h.state.apiKey, '');
  assert.ok(h.state.secretsError);
});
test('pending MCP rotation cannot expose the old value', async () => {
  const wait = deferred(); const h = mcp({ regenerateWorkspaceSecret: () => wait.promise });
  const operation = h.regenerate('oauth_client_secret');
  assert.equal(h.state.secrets.oauth_client_secret ?? '', '');
  wait.resolve('canonical'); await operation;
});
test('late mutation recovery cannot fetch or publish into another workspace', async () => {
  const wait = deferred(); let reads = 0;
  const h = mcp({ regenerateWorkspaceSecret: () => wait.promise, getWorkspaceSecret: async () => { reads++; return 'canonical'; } });
  const operation = h.regenerate('oauth_client_secret');
  h.state.workspaceId = 'B'; h.state.secrets = { oauth_client_secret: 'B-only' };
  wait.reject(failure); await operation;
  assert.equal(reads, 0); assert.equal(h.state.secrets.oauth_client_secret, 'B-only');
  assert.deepEqual(h.state.messages, []);
});
test('credential refresh preserves an edited private MCP client ID', async () => {
  const wait = deferred(); const h = mcp({ getWorkspaceSecret: () => wait.promise });
  const operation = h.loadSecrets('A', 'oauth', false);
  h.state.draft.oauth_client_id = 'new-unsaved-id'; wait.resolve('canonical'); await operation;
  assert.equal(h.state.draft.oauth_client_id, 'new-unsaved-id');
});
test('shared identity readback never replaces the private MCP client ID draft', async () => {
  const h = mcp(); h.state.draft.use_shared_secrets = true;
  await h.loadSecrets('A', 'oauth', true);
  assert.equal(h.state.loadedSharedOauthClientId, 'shared-canonical');
  assert.equal(h.state.draft.oauth_client_id, 'private-draft');
});

function sharedKeys(overrides = {}) {
  const state = {
    disposed: false, secrets: { bearer_token: 'old', oauth_password: 'unsaved-other' },
    originals: { bearer_token: 'old', oauth_password: 'saved-other' }, loadErrors: {},
    saving: false, loading: false, regenerating: null, dirty: true, hasLoadErrors: false,
    ALL_KEYS: [{key:'bearer_token'}, {key:'oauth_password'}],
    loadRequests: latestRequest(), mutationRequests: latestRequest(), applyAndRefresh,
    regenerateSharedSecret: async () => { throw failure; }, setSharedSecret: async () => { throw failure; },
    getSharedSecret: async () => 'canonical', messages: [], ...overrides,
  };
  state.message = async (text) => { state.messages.push(text); };
  return { state, ...functions('src/routes/settings/keys/+page.svelte', state) };
}
test('shared regeneration failure reads canonical value without discarding unrelated drafts', async () => {
  const h = sharedKeys(); await h.regenerate('bearer_token');
  assert.equal(h.state.secrets.bearer_token, 'canonical');
  assert.equal(h.state.originals.bearer_token, 'canonical');
  assert.equal(h.state.secrets.oauth_password, 'unsaved-other');
  assert.match(h.state.messages[0], /persisted, then restart failed/);
});
test('shared failed readback fails closed for the affected field', async () => {
  const h = sharedKeys({ getSharedSecret: async () => { throw new Error('read failed'); } });
  await h.regenerate('bearer_token');
  assert.equal(h.state.secrets.bearer_token ?? '', '');
  assert.equal(h.state.loadErrors.bearer_token, true);
  assert.equal(h.state.secrets.oauth_password, 'unsaved-other');
});
test('shared rotation hides old credentials while the IPC is pending', async () => {
  const wait = deferred(); const h = sharedKeys({ regenerateSharedSecret: () => wait.promise });
  const operation = h.regenerate('bearer_token');
  assert.equal(h.state.secrets.bearer_token ?? '', '');
  wait.resolve('canonical'); await operation;
});
test('shared save failure reconciles persisted key and stops the later writes', async () => {
  const calls = [];
  const h = sharedKeys({ setSharedSecret: async (key) => { calls.push(key); throw failure; } });
  h.state.secrets.bearer_token = 'new-draft'; await h.saveAll();
  assert.deepEqual(calls, ['bearer_token']);
  assert.equal(h.state.secrets.bearer_token, 'canonical');
  assert.equal(h.state.originals.bearer_token, 'canonical');
  assert.equal(h.state.secrets.oauth_password, 'unsaved-other');
  assert.match(h.state.messages[0], /persisted, then restart failed/);
});
test('shared save acknowledges the submitted snapshot, not edits made during the await', async () => {
  const wait = deferred(); const calls = [];
  const h = sharedKeys({ ALL_KEYS: [{key:'bearer_token'}], setSharedSecret: (key, value) => { calls.push([key,value]); return wait.promise; } });
  h.state.secrets.bearer_token = 'submitted';
  const operation = h.saveAll(); h.state.secrets.bearer_token = 'later-draft';
  wait.resolve(); await operation;
  assert.deepEqual(calls, [['bearer_token','submitted']]);
  assert.equal(h.state.originals.bearer_token, 'submitted');
  assert.equal(h.state.secrets.bearer_token, 'later-draft');
});
test('disposed shared mutation cannot perform a readback or publish results', async () => {
  const wait = deferred(); let reads = 0;
  const h = sharedKeys({ regenerateSharedSecret: () => wait.promise, getSharedSecret: async () => { reads++; return 'canonical'; } });
  const operation = h.regenerate('bearer_token');
  h.state.disposed = true; h.state.secrets = {}; h.state.mutationRequests.invalidate();
  wait.reject(failure); await operation;
  assert.equal(reads, 0); assert.deepEqual(h.state.secrets, {}); assert.deepEqual(h.state.messages, []);
});
