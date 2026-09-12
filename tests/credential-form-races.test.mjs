/** Source contracts for credential-form race safety; Svelte compile is covered by the full frontend CI. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const defaultRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const root = process.env.CREDENTIAL_REVIEW_ROOT ? path.resolve(process.env.CREDENTIAL_REVIEW_ROOT) : defaultRoot;
const read = (name) => readFileSync(path.join(root, name), 'utf8');

function section(source, start, end) {
  const a = source.indexOf(start);
  assert.notEqual(a, -1, `missing section start: ${start}`);
  const b = source.indexOf(end, a + start.length);
  assert.notEqual(b, -1, `missing section end: ${end}`);
  return source.slice(a, b);
}

test('MCP auth form fences stale loads and mutations without writing shared identity', () => {
  const source = read('src/lib/components/AuthConfigForm.svelte');
  assert.match(source, /const secretRequests = latestRequest\(\);/);
  assert.match(source, /const operationRequests = latestRequest\(\);/);
  assert.match(source, /operationContextKey/);
  assert.match(source, /operationRequests\.invalidate\(\)/);
  assert.doesNotMatch(source, /setSharedSecret/);
  const load = section(source, 'async function loadSecrets', 'async function save');
  assert.match(load, /secrets = \{\};/);
  assert.match(load, /secretRequests\.current\(ticket\)/);
  assert.match(load, /currentContext\(id, authType, useShared\)/);
  assert.match(load, /secretsError = "凭据读取失败/);
  const save = section(source, 'async function save', 'async function regenerate');
  assert.match(save, /operationRequests\.begin\(\)/);
  assert.match(save, /operationRequests\.current\(ticket\)/);
  assert.match(save, /loadingSecrets \|\| secretsError \|\| regenerating/);
  assert.match(save, /oauth_client_id: useShared \? auth\.oauth_client_id/);
  const regenerate = source.slice(source.indexOf('async function regenerate'));
  assert.match(regenerate, /operationRequests\.begin\(\)/);
  assert.match(regenerate, /await loadSecrets\(id, authType, useShared\)/);
  assert.doesNotMatch(regenerate, /secrets = \{ \.\.\.secrets, \[key\]: value \}/);
});

test('Actions auth form fences old workspace/shared operations and clears stale credentials', () => {
  const source = read('src/lib/components/ActionsAuthForm.svelte');
  assert.match(source, /const secretRequests = latestRequest\(\);/);
  assert.match(source, /const operationRequests = latestRequest\(\);/);
  assert.match(source, /operationContextKey/);
  const load = section(source, 'async function loadSecrets', 'async function save');
  assert.match(load, /clearSecrets\(\);/);
  assert.match(load, /secretRequests\.current\(ticket\)/);
  assert.match(load, /currentContext\(id, useShared\)/);
  assert.match(load, /secretsError = "凭据读取失败/);
  const save = section(source, 'async function save', 'async function regenerateCredential');
  assert.match(save, /operationRequests\.begin\(\)/);
  assert.match(save, /operationRequests\.current\(ticket\)/);
  const regenerate = source.slice(source.indexOf('async function regenerateCredential'));
  assert.match(regenerate, /operationRequests\.begin\(\)/);
  assert.match(regenerate, /operationRequests\.current\(ticket\)/);
  assert.match(regenerate, /await loadSecrets\(id, useShared\)/);
});

test('shared-secret page fails closed on reads and keeps load/mutation epochs independent', () => {
  const source = read('src/routes/settings/keys/+page.svelte');
  assert.match(source, /const loadRequests = latestRequest\(\);/);
  assert.match(source, /const mutationRequests = latestRequest\(\);/);
  assert.match(source, /if \(saving \|\| regenerating\) return;/);
  assert.match(source, /if \(saving \|\| loading \|\| regenerating \|\| hasLoadErrors \|\| !dirty\) return;/);
  assert.match(source, /else nextErrors\[result\.key\] = true;/);
  assert.match(source, /读取失败，禁止编辑\/复制/);
  const regenerate = section(source, 'async function regenerate', 'async function saveAll');
  assert.match(regenerate, /mutationRequests\.begin\(\)/);
  assert.match(regenerate, /originals = \{ \.\.\.originals, \[key\]: value \}/);
  assert.doesNotMatch(regenerate, /Keep originals stale/);
});
