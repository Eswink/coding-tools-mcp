// A1 C9-ui-remainder §6.1 NARROW-B: list_subagent_workers cards + cancel/discard.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';

const source = readFileSync(new URL('../src/lib/subagent-workers.ts', import.meta.url), 'utf8');
const code = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 },
}).outputText;
const {
  createSubagentWorkersController,
  mapWorkerCard,
  formatActivityAt,
  workerStateLabels,
  WINDOWS_UNSANDBOXED_CARD_LABEL,
  LINUX_SANDBOX_DEFERRED_LABEL,
} = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);

const ID = 'workspace-1';
const WID = 'a'.repeat(32);
const worker = {
  worker_id: WID,
  label: 'demo',
  state: 'ready',
  base_head: '0123456789abcdef0123456789abcdef01234567',
  last_activity_at: 1_700_000_100,
  changed_files: null,
};
const listed = { workers: [worker], windows: false };

function deferred() {
  let resolve;
  const promise = new Promise(r => { resolve = r; });
  return { promise, resolve };
}
function setup(reply = async cmd => cmd === 'list_subagent_workers' ? listed : { worker }, confirmFn) {
  const s = { calls: [], views: [], view: undefined, confirms: [] };
  const confirm = confirmFn ?? (async (message, options) => {
    s.confirms.push({ message, options });
    return true;
  });
  s.controller = createSubagentWorkersController(
    ID,
    async (command, args) => { s.calls.push({ command, args }); return reply(command, args); },
    v => { s.view = v; s.views.push(v); },
    confirm,
  );
  return s;
}
const commands = s => s.calls.map(c => c.command);

test('maps tip WorkerState labels and never invents busy/orphaned', () => {
  for (const state of Object.keys(workerStateLabels)) {
    assert.equal(mapWorkerCard({ ...worker, state }, false).state, state);
  }
  assert.equal('busy' in workerStateLabels, false);
  assert.equal('orphaned' in workerStateLabels, false);
});

test('missing fields render as em dash; cwd is ignored', () => {
  const card = mapWorkerCard({ worker_id: WID, cwd: '/secret' }, true);
  assert.equal(card.label, '—');
  assert.equal(card.baseHeadShort, '—');
  assert.equal(card.lastActivityText, '—');
  assert.equal(card.changedFilesText, '—');
  assert.equal(card.windowsUnsandboxed, true);
  assert.equal(card.linuxSandboxDeferred, false);
  assert.equal(WINDOWS_UNSANDBOXED_CARD_LABEL, '无沙箱 · 用户默认权限');
  assert.match(LINUX_SANDBOX_DEFERRED_LABEL, /延后/);
});

test('activity stamps format in Asia/Shanghai', () => {
  // 1700000100 = 2023-11-14 22:15:00 UTC = 2023-11-15 06:15:00 CST
  const text = formatActivityAt(1_700_000_100);
  assert.match(text, /2023/);
  assert.match(text, /06:15:00/);
  assert.equal(formatActivityAt(null), '—');
  assert.equal(formatActivityAt(0), '—');
});

test('a profile load calls list_subagent_workers exactly once with the profile id', async () => {
  const s = setup();
  await s.controller.load();
  await s.controller.load();
  assert.deepEqual(s.calls, [{ command: 'list_subagent_workers', args: { id: ID } }]);
  assert.equal(s.view.workers.length, 1);
  assert.equal(s.view.workers[0].baseHeadShort, '0123456');
  assert.equal(s.view.workers[0].changedFilesText, '—');
  assert.equal(s.view.unavailable, false);
});

test('listener failure is unavailable and never echoes SECRET', async () => {
  const s = setup(async () => { throw Error('SECRET_PATH'); });
  await s.controller.load();
  assert.equal(s.view.unavailable, true);
  assert.equal(s.view.workers.length, 0);
  assert.doesNotMatch(s.view.error, /SECRET_PATH/);
  assert.doesNotMatch(JSON.stringify(s.views), /SECRET_PATH/);
});

test('cancel passes profile id + workerId and refreshes the list', async () => {
  const s = setup(async cmd => cmd === 'list_subagent_workers' ? listed : { worker: { ...worker, state: 'cancelled' } });
  await s.controller.load();
  await s.controller.cancel(WID);
  assert.deepEqual(s.calls.at(1), { command: 'cancel_subagent_worker', args: { id: ID, workerId: WID } });
  assert.ok(commands(s).includes('list_subagent_workers'));
  assert.match(s.view.notice, /取消/);
});

test('discard requires confirmation and surfaces DIRTY without SECRET', async () => {
  let approved = false;
  const s = setup(
    async cmd => {
      if (cmd === 'list_subagent_workers') return listed;
      return { ok: false, error: { code: 'DIRTY', message: 'SECRET_TREE' } };
    },
    async (message) => { approved = true; assert.match(message, /未提交改动/); return true; },
  );
  await s.controller.load();
  await s.controller.discard(WID);
  assert.equal(approved, true);
  assert.deepEqual(s.calls.at(1), { command: 'discard_subagent_worker', args: { id: ID, workerId: WID } });
  assert.match(s.view.error, /未提交改动/);
  assert.doesNotMatch(s.view.error, /SECRET_TREE/);
});

test('owner cancel of discard confirmation changes nothing', async () => {
  const s = setup(async () => listed, async () => false);
  await s.controller.load();
  await s.controller.discard(WID);
  assert.deepEqual(commands(s), ['list_subagent_workers']);
  assert.match(s.view.notice, /已取消丢弃/);
});

test('busy/uncertain blocks duplicate discard clicks', async () => {
  const pending = deferred();
  const s = setup(cmd => cmd === 'list_subagent_workers' ? Promise.resolve(listed) : pending.promise);
  await s.controller.load();
  const one = s.controller.discard(WID);
  const two = s.controller.discard(WID);
  pending.resolve({ worker });
  await Promise.all([one, two]);
  assert.equal(commands(s).filter(c => c === 'discard_subagent_worker').length, 1);
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

test('workspace page mounts the panel beside IntegrationAttention and forbids merge commands', () => {
  const page = readFileSync(new URL('../src/routes/workspace/[id]/+page.svelte', import.meta.url), 'utf8');
  assert.equal(page.match(/<SubagentWorkersPanel workspaceId=\{profile\.id\} \/>/g)?.length, 1);
  assert.equal(page.match(/<IntegrationAttention workspaceId=\{profile\.id\} \/>/g)?.length, 1);
  assert.doesNotMatch(page, /list_subagent_workers|cancel_subagent_worker|discard_subagent_worker/);
  assert.doesNotMatch(page, /confirm_subagent_integration|reject_subagent_integration/);
  const panel = readFileSync(new URL('../src/lib/components/SubagentWorkersPanel.svelte', import.meta.url), 'utf8');
  assert.ok(panel.includes('子代理'));
  assert.ok(panel.includes('WINDOWS_UNSANDBOXED_CARD_LABEL'));
  assert.doesNotMatch(panel, /confirm_subagent_integration|reject_subagent_integration|confirm_subagent_rollback|reject_subagent_rollback/);
  assert.doesNotMatch(panel, /console\.|localStorage|sessionStorage|setInterval|setTimeout/);
  const invoked = [...source.matchAll(/invoke<[^>]*>\('([a-z_]+)'/g)].map(m => m[1]);
  assert.deepEqual(invoked, ['list_subagent_workers', 'cancel_subagent_worker', 'discard_subagent_worker']);
});
