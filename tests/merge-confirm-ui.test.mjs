// A1 C9-§6.2 merge-confirm NARROW-B + C9 soft-nits: pending[] cards + confirm/reject (no hunk / no MCP).
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';

const source = readFileSync(new URL('../src/lib/merge-confirm.ts', import.meta.url), 'utf8');
const sharedSource = readFileSync(new URL('../src/lib/pending-integrations-shared.ts', import.meta.url), 'utf8');
const code = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 },
}).outputText;
// Rewrite $lib import to a data URL of the shared module so node:test can load it.
const sharedCode = ts.transpileModule(sharedSource, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 },
}).outputText;
const sharedUrl = `data:text/javascript;base64,${Buffer.from(sharedCode).toString('base64')}`;
const patched = code.replaceAll('$lib/pending-integrations-shared', sharedUrl);
const {
  createMergeConfirmController,
  mapPendingCard,
  closedReasonLabel,
  formatExpiresAt,
  filesCount,
  actionsDisabled,
  ROLLBACK_AVAILABLE_NOTICE,
  DO_NOT_RETRY_ERROR,
} = await import(`data:text/javascript;base64,${Buffer.from(patched).toString('base64')}`);
const { resetPendingListSlotsForTests } = await import(sharedUrl);

const ID = 'workspace-1';
const IID = 'b'.repeat(32);
const DIFF = '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef';

const integratePending = {
  kind: 'integrate',
  integration_id: IID,
  label: 'demo',
  diff_sha256: DIFF,
  files: 3,
  expires_at: 1_700_000_100,
  closed_reason: null,
};
const rollbackPending = {
  kind: 'rollback',
  integration_id: 'c'.repeat(32),
  label: 'rb',
  diff_sha256: '',
  files: 1,
  rollback_expires_at: 1_700_000_200,
  closed_reason: null,
};
const listed = { recovery: { state: 'none' }, pending: [integratePending, rollbackPending] };

function deferred() {
  let resolve;
  const promise = new Promise(r => { resolve = r; });
  return { promise, resolve };
}
function setup(reply = async cmd => cmd === 'list_pending_integrations' ? listed : { ok: true }) {
  resetPendingListSlotsForTests();
  const s = { calls: [], views: [], view: undefined };
  s.controller = createMergeConfirmController(
    ID,
    async (command, args) => { s.calls.push({ command, args }); return reply(command, args); },
    v => { s.view = v; s.views.push(v); },
  );
  return s;
}
const commands = s => s.calls.map(c => c.command);

test('maps pending cards: diff prefix 12, files count, missing sha is em dash', () => {
  const card = mapPendingCard(integratePending);
  assert.equal(card.integrationId, IID);
  assert.equal(card.kind, 'integrate');
  assert.equal(card.diffShaShort, DIFF.slice(0, 12));
  assert.equal(card.filesCount, '3');
  assert.match(card.expiresText, /失效/);
  const empty = mapPendingCard({ kind: 'rollback', integration_id: IID, files: null });
  assert.equal(empty.diffShaShort, '—');
  assert.equal(empty.filesCount, '—');
  assert.equal(empty.label, '—');
});

test('filesCount accepts only finite number; string input becomes em dash', () => {
  assert.equal(filesCount(3), '3');
  assert.equal(filesCount(0), '0');
  assert.equal(filesCount('3'), '—');
  assert.equal(filesCount('12'), '—');
  assert.equal(filesCount(Number.NaN), '—');
  assert.equal(filesCount(null), '—');
  assert.equal(mapPendingCard({ integration_id: IID, files: '9' }).filesCount, '—');
});

test('closed_reason maps to Chinese without echoing ids', () => {
  assert.match(closedReasonLabel('head_moved'), /主工作区已变更/);
  assert.match(closedReasonLabel('superseded'), /后续合入/);
  assert.match(closedReasonLabel('not_committed'), /可回滚/);
  assert.match(closedReasonLabel('other'), /已关闭/);
  assert.equal(closedReasonLabel(''), '');
  assert.doesNotMatch(closedReasonLabel('head_moved'), /SECRET|session/);
});

test('actionsDisabled when closedReasonText is set (soft nit)', () => {
  assert.equal(actionsDisabled({ busy: false, uncertain: false }, { closedReasonText: '' }), false);
  assert.equal(actionsDisabled({ busy: false, uncertain: false }, { closedReasonText: '回滚窗口已关闭' }), true);
  assert.equal(actionsDisabled({ busy: true, uncertain: false }, { closedReasonText: '' }), true);
  assert.equal(actionsDisabled({ busy: false, uncertain: true }, { closedReasonText: '' }), true);
});

test('expires stamps format in Asia/Shanghai', () => {
  // 1700000100 = 2023-11-14 22:15:00 UTC = 2023-11-15 06:15:00 CST
  const text = formatExpiresAt(1_700_000_100);
  assert.match(text, /2023/);
  assert.match(text, /06:15:00/);
  assert.equal(formatExpiresAt(null), '');
  assert.equal(formatExpiresAt(0), '');
});

test('a profile load calls list_pending_integrations once and renders pending[]', async () => {
  const s = setup();
  await s.controller.load();
  await s.controller.load();
  assert.deepEqual(s.calls, [{ command: 'list_pending_integrations', args: { id: ID } }]);
  assert.equal(s.view.items.length, 2);
  assert.equal(s.view.items[0].diffShaShort, DIFF.slice(0, 12));
  assert.equal(s.view.items[1].kind, 'rollback');
  assert.equal(s.view.unavailable, false);
});

test('listener failure is unavailable and never echoes SECRET', async () => {
  const s = setup(async () => { throw Error('SECRET_PATH'); });
  await s.controller.load();
  assert.equal(s.view.unavailable, true);
  assert.equal(s.view.items.length, 0);
  assert.doesNotMatch(s.view.error, /SECRET_PATH/);
  assert.doesNotMatch(JSON.stringify(s.views), /SECRET_PATH/);
});

test('confirm integrate invokes native command and shows rollback notice', async () => {
  const s = setup(async cmd => {
    if (cmd === 'list_pending_integrations') return listed;
    return { ok: true, state: 'committed' };
  });
  await s.controller.load();
  await s.controller.confirm(IID, 'integrate');
  assert.deepEqual(s.calls.at(1), { command: 'confirm_subagent_integration', args: { id: ID, integrationId: IID } });
  assert.equal(s.view.notice, ROLLBACK_AVAILABLE_NOTICE);
  assert.ok(commands(s).filter(c => c === 'list_pending_integrations').length >= 2);
});

test('confirm rollback and reject use the matching commands', async () => {
  const rid = 'c'.repeat(32);
  const s = setup(async cmd => cmd === 'list_pending_integrations' ? listed : { ok: true });
  await s.controller.load();
  await s.controller.confirm(rid, 'rollback');
  assert.deepEqual(s.calls.at(1), { command: 'confirm_subagent_rollback', args: { id: ID, integrationId: rid } });
  assert.match(s.view.notice, /已回滚/);
  await s.controller.reject(IID, 'integrate');
  assert.ok(s.calls.some(c => c.command === 'reject_subagent_integration' && c.args.integrationId === IID));
  assert.match(s.view.notice, /已拒绝/);
  await s.controller.reject(rid, 'rollback');
  assert.ok(s.calls.some(c => c.command === 'reject_subagent_rollback'));
});

test('owner cancel of native confirm changes nothing beyond notice', async () => {
  const s = setup(async cmd => cmd === 'list_pending_integrations' ? listed : null);
  await s.controller.load();
  await s.controller.confirm(IID, 'integrate');
  assert.match(s.view.notice, /已取消/);
  assert.equal(s.view.items.length, 2);
});

test('ok:false refusals surface fixed Chinese and never echo SECRET', async () => {
  const s = setup(async cmd => {
    if (cmd === 'list_pending_integrations') return listed;
    return { ok: false, error: { code: 'WORKER_STATE', message: 'SECRET_BLOB' } };
  });
  await s.controller.load();
  await s.controller.confirm(IID, 'integrate');
  assert.match(s.view.error, /不允许/);
  assert.doesNotMatch(s.view.error, /SECRET_BLOB/);
  assert.doesNotMatch(JSON.stringify(s.views), /SECRET_BLOB/);
});

test('busy/uncertain blocks duplicate confirm clicks', async () => {
  const pending = deferred();
  const s = setup(cmd => cmd === 'list_pending_integrations' ? Promise.resolve(listed) : pending.promise);
  await s.controller.load();
  const one = s.controller.confirm(IID, 'integrate');
  const two = s.controller.confirm(IID, 'integrate');
  pending.resolve({ ok: true });
  await Promise.all([one, two]);
  assert.equal(commands(s).filter(c => c === 'confirm_subagent_integration').length, 1);
});

test('closed_reason on a card blocks confirm and reject invokes', async () => {
  const closedListed = {
    recovery: { state: 'none' },
    pending: [{ ...integratePending, closed_reason: 'head_moved' }],
  };
  const s = setup(async cmd => cmd === 'list_pending_integrations' ? closedListed : { ok: true });
  await s.controller.load();
  assert.match(s.view.items[0].closedReasonText, /主工作区已变更/);
  await s.controller.confirm(IID, 'integrate');
  await s.controller.reject(IID, 'integrate');
  assert.deepEqual(commands(s), ['list_pending_integrations']);
});

test('unconfirmed invoke is redacted and locked against retry', async () => {
  const s = setup(async cmd => {
    if (cmd === 'list_pending_integrations') return listed;
    throw Error('SECRET_CONTENT');
  });
  await s.controller.load();
  await s.controller.confirm(IID, 'integrate');
  await s.controller.confirm(IID, 'integrate');
  assert.equal(s.view.uncertain, true);
  assert.equal(s.view.error, DO_NOT_RETRY_ERROR);
  assert.doesNotMatch(s.view.error, /SECRET_CONTENT/);
  assert.equal(commands(s).filter(c => c === 'confirm_subagent_integration').length, 1);
});

test('late list after dispose cannot publish', async () => {
  const pending = deferred();
  const s = setup(() => pending.promise);
  const op = s.controller.load();
  s.controller.dispose();
  pending.resolve(listed);
  await op;
  assert.equal(s.views.length, 0);
});

test('no hunk / path-preview helpers and panel forbids Workers merge bleed', () => {
  assert.doesNotMatch(source, /diff_preview|changed_paths|files_list|renderHunk|fileHunks/);
  const panel = readFileSync(new URL('../src/lib/components/MergeConfirmPanel.svelte', import.meta.url), 'utf8');
  assert.ok(panel.includes('合并确认'));
  assert.ok(panel.includes('合入当前分支'));
  assert.ok(panel.includes('拒绝'));
  assert.ok(panel.includes('actionsDisabled(view, item)'));
  assert.doesNotMatch(panel, /逐文件|diff preview|renderHunk/i);
  assert.doesNotMatch(panel, /console\.|localStorage|sessionStorage|setInterval|setTimeout/);
  const workers = readFileSync(new URL('../src/lib/components/SubagentWorkersPanel.svelte', import.meta.url), 'utf8');
  assert.doesNotMatch(workers, /confirm_subagent_integration|reject_subagent_integration|confirm_subagent_rollback|reject_subagent_rollback/);
});

test('workspace page mounts MergeConfirm beside Attention/Workers; page itself has no invoke names', () => {
  const page = readFileSync(new URL('../src/routes/workspace/[id]/+page.svelte', import.meta.url), 'utf8');
  assert.equal(page.match(/<MergeConfirmPanel workspaceId=\{profile\.id\} \/>/g)?.length, 1);
  assert.equal(page.match(/<IntegrationAttention workspaceId=\{profile\.id\} \/>/g)?.length, 1);
  assert.equal(page.match(/<SubagentWorkersPanel workspaceId=\{profile\.id\} \/>/g)?.length, 1);
  assert.doesNotMatch(page, /list_pending_integrations|confirm_subagent_integration|reject_subagent_integration|confirm_subagent_rollback|reject_subagent_rollback/);
  for (const cmd of [
    'confirm_subagent_integration',
    'confirm_subagent_rollback',
    'reject_subagent_integration',
    'reject_subagent_rollback',
  ]) assert.ok(source.includes(`'${cmd}'`), cmd);
  // list lives in the shared helper (exactly one command string there)
  assert.equal([...sharedSource.matchAll(/'list_pending_integrations'/g)].length, 1);
  assert.doesNotMatch(source, /invoke<[^>]*>\('list_pending_integrations'/);
});
