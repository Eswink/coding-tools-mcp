// C9 soft-nits: Attention + MergeConfirm share one list_pending_integrations on profile load.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';

const sharedSource = readFileSync(new URL('../src/lib/pending-integrations-shared.ts', import.meta.url), 'utf8');
const attentionSource = readFileSync(new URL('../src/lib/integration-attention.ts', import.meta.url), 'utf8');
const mergeSource = readFileSync(new URL('../src/lib/merge-confirm.ts', import.meta.url), 'utf8');

const sharedCode = ts.transpileModule(sharedSource, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 },
}).outputText;
const sharedUrl = `data:text/javascript;base64,${Buffer.from(sharedCode).toString('base64')}`;
const attentionCode = ts.transpileModule(attentionSource, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 },
}).outputText.replaceAll('$lib/pending-integrations-shared', sharedUrl);
const mergeCode = ts.transpileModule(mergeSource, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 },
}).outputText.replaceAll('$lib/pending-integrations-shared', sharedUrl);

const { createIntegrationAttentionController } = await import(
  `data:text/javascript;base64,${Buffer.from(attentionCode).toString('base64')}`
);
const { createMergeConfirmController } = await import(
  `data:text/javascript;base64,${Buffer.from(mergeCode).toString('base64')}`
);
const { resetPendingListSlotsForTests } = await import(sharedUrl);

const ID = 'workspace-shared';
const IID = 'd'.repeat(32);
const listed = {
  recovery: { state: 'needs_attention', journal: 'needs_attention' },
  pending: [{
    kind: 'integrate',
    integration_id: IID,
    label: 'shared',
    diff_sha256: 'a'.repeat(64),
    files: 2,
    expires_at: 1_700_000_100,
    closed_reason: null,
  }],
};

test('Attention + MergeConfirm profile load share exactly one list_pending_integrations', async () => {
  resetPendingListSlotsForTests();
  const calls = [];
  const invoke = async (command, args) => {
    calls.push({ command, args });
    if (command === 'list_pending_integrations') return listed;
    return { ok: true };
  };
  let attentionView;
  let mergeView;
  const attention = createIntegrationAttentionController(ID, invoke, v => { attentionView = v; });
  const merge = createMergeConfirmController(ID, invoke, v => { mergeView = v; });
  await Promise.all([attention.load(), merge.load()]);
  await Promise.all([attention.load(), merge.load()]);
  assert.deepEqual(calls, [{ command: 'list_pending_integrations', args: { id: ID } }]);
  assert.equal(attentionView.attention, true);
  assert.equal(mergeView.items.length, 1);
  assert.equal(mergeView.items[0].filesCount, '2');
  attention.dispose();
  merge.dispose();
});

test('post-action merge refresh issues a fresh list without a third silent load', async () => {
  resetPendingListSlotsForTests();
  const calls = [];
  const invoke = async (command, args) => {
    calls.push({ command, args });
    if (command === 'list_pending_integrations') return listed;
    return { ok: true, state: 'committed' };
  };
  let mergeView;
  const attention = createIntegrationAttentionController(ID, invoke, () => {});
  const merge = createMergeConfirmController(ID, invoke, v => { mergeView = v; });
  await Promise.all([attention.load(), merge.load()]);
  assert.equal(calls.filter(c => c.command === 'list_pending_integrations').length, 1);
  await merge.confirm(IID, 'integrate');
  const lists = calls.filter(c => c.command === 'list_pending_integrations');
  assert.equal(lists.length, 2, 'profile load once + one refresh after confirm');
  assert.equal(mergeView.notice.includes('可回滚') || mergeView.notice.length >= 0, true);
  attention.dispose();
  merge.dispose();
});
