// A1 C17 NARROW-B: legacy-cleanup FE controller + panel wiring (no new Tauri/MCP).
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';

const source = readFileSync(new URL('../src/lib/legacy-cleanup.ts', import.meta.url), 'utf8');
const code = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 },
}).outputText;
const {
  createLegacyCleanupController,
  mapCandidate,
  mapWarning,
  mapOutcome,
  isStaleError,
  actionsDisabled,
  cleanupDisabled,
  CANCEL_NOTICE,
  DO_NOT_RETRY_ERROR,
  STALE_ERROR,
  HINT_FAILED_WARN,
  CLEANUP_SUCCESS_NOTICE,
  INTERRUPTED_BADGE,
  countFailedOutcomes,
  cleanupApplyNotice,
  cleanupRefreshFailedError,
} = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);

const SOURCE = 'workspace-1';
const DIGEST = 'a'.repeat(64);
const ID_CLEAN = 'c'.repeat(32);
const ID_DIRTY = 'd'.repeat(32);
const ID_LOCKED = 'e'.repeat(32);
const ID_INTERRUPTED = 'f'.repeat(32);

const cleanCandidate = {
  id: ID_CLEAN,
  display_path: 'agents/demo',
  head_short: 'abc1234',
  head: 'abc1234deadbeef',
  clean: true,
  interrupted: false,
  hint: null,
};
const dirtyCandidate = {
  id: ID_DIRTY,
  display_path: 'agents/dirty',
  head_short: 'bbb2222',
  clean: false,
  interrupted: false,
  hint: null,
};
const lockedCandidate = {
  id: ID_LOCKED,
  display_path: 'agents/locked',
  head_short: 'ccc3333',
  clean: true,
  interrupted: false,
  hint: 'LOCKED',
};
const interruptedCandidate = {
  id: ID_INTERRUPTED,
  display_path: 'agents/interrupted',
  head_short: 'ddd4444',
  clean: true,
  interrupted: true,
  hint: 'PINNED',
};

const previewFull = {
  candidates: [cleanCandidate, dirtyCandidate, lockedCandidate, interruptedCandidate],
  digest: DIGEST,
  warnings: [{ id: 'w1', code: 'UNCANONICAL' }],
  native_dialog_required: true,
};

function deferred() {
  let resolve;
  const promise = new Promise(r => { resolve = r; });
  return { promise, resolve };
}

function setup(reply = async cmd => {
  if (cmd === 'preview_legacy_cleanup') return previewFull;
  return { outcomes: [{ id: ID_CLEAN, state: 'removed' }] };
}) {
  const s = { calls: [], views: [], view: undefined };
  s.controller = createLegacyCleanupController(
    SOURCE,
    async (command, args) => {
      s.calls.push({ command, args });
      return reply(command, args);
    },
    v => { s.view = v; s.views.push(v); },
  );
  return s;
}
const commands = s => s.calls.map(c => c.command);

test('mapCandidate: dirty not selectable; LOCKED/PINNED hintWarn; hint kept as-is', () => {
  const clean = mapCandidate(cleanCandidate);
  assert.equal(clean.selectable, true);
  assert.equal(clean.hintWarn, false);
  assert.equal(clean.hint, '');
  const dirty = mapCandidate(dirtyCandidate);
  assert.equal(dirty.selectable, false);
  assert.equal(dirty.clean, false);
  const locked = mapCandidate(lockedCandidate);
  assert.equal(locked.selectable, true);
  assert.equal(locked.hintWarn, true);
  assert.equal(locked.hint, 'LOCKED');
  assert.notEqual(locked.hint, 'WORKTREE_PINNED');
  const pinned = mapCandidate({ ...lockedCandidate, hint: 'PINNED' });
  assert.equal(pinned.hint, 'PINNED');
  assert.equal(pinned.hintWarn, true);
  // Absolute path fields must never be copied into the card.
  const withAbs = mapCandidate({
    ...cleanCandidate,
    path: '/SECRET/abs/path',
    root: '/SECRET/root',
  });
  assert.equal(withAbs.displayPath, 'agents/demo');
  assert.equal('path' in withAbs, false);
  assert.equal('root' in withAbs, false);
  assert.doesNotMatch(JSON.stringify(withAbs), /SECRET/);
});

test('mapWarning / mapOutcome / isStaleError helpers', () => {
  assert.deepEqual(mapWarning({ id: 'x', code: 'Y' }), { id: 'x', code: 'Y' });
  assert.deepEqual(mapOutcome({ id: 'a', state: 'failed', code: 'LOCKED' }), {
    id: 'a', state: 'failed', code: 'LOCKED',
  });
  assert.equal(isStaleError(new Error('旧版 worktree 清理未执行：STALE_CONFIRMATION；没有删除任何内容。')), true);
  assert.equal(isStaleError(new Error('DIRTY')), false);
  assert.equal(isStaleError('STALE_CONFIRMATION'), true);
});

test('actionsDisabled / cleanupDisabled', () => {
  assert.equal(actionsDisabled({ busy: false, uncertain: false }), false);
  assert.equal(actionsDisabled({ busy: true, uncertain: false }), true);
  assert.equal(actionsDisabled({ busy: false, uncertain: true }), true);
  assert.equal(cleanupDisabled({
    busy: false, uncertain: false, selectedIds: [ID_CLEAN], digest: DIGEST,
  }), false);
  assert.equal(cleanupDisabled({
    busy: false, uncertain: false, selectedIds: [], digest: DIGEST,
  }), true);
  assert.equal(cleanupDisabled({
    busy: false, uncertain: false, selectedIds: [ID_CLEAN], digest: '',
  }), true);
});

test('empty list: refresh with zero candidates; no preselection', async () => {
  const empty = { candidates: [], digest: '', warnings: [], native_dialog_required: false };
  const s = setup(async () => empty);
  await s.controller.refresh();
  assert.deepEqual(s.calls[0], { command: 'preview_legacy_cleanup', args: { sourceId: SOURCE } });
  assert.equal(s.view.candidates.length, 0);
  assert.deepEqual(s.view.selectedIds, []);
  assert.equal(s.view.digest, '');
});

test('preview maps interrupted badge + hint as-is + dirty disabled + warnings + dialog badge', async () => {
  const s = setup();
  await s.controller.refresh();
  assert.equal(s.view.candidates.length, 4);
  assert.deepEqual(s.view.selectedIds, []); // default no preselection
  const dirty = s.view.candidates.find(c => c.id === ID_DIRTY);
  assert.equal(dirty.selectable, false);
  const interrupted = s.view.candidates.find(c => c.id === ID_INTERRUPTED);
  assert.equal(interrupted.interrupted, true);
  assert.equal(interrupted.hint, 'PINNED');
  assert.equal(interrupted.hintWarn, true);
  const locked = s.view.candidates.find(c => c.id === ID_LOCKED);
  assert.equal(locked.hint, 'LOCKED');
  assert.equal(s.view.warnings.length, 1);
  assert.equal(s.view.warnings[0].code, 'UNCANONICAL');
  assert.equal(s.view.nativeDialogRequired, true);
  assert.doesNotMatch(JSON.stringify(s.view), /\/SECRET|WORKTREE_PINNED/);
});

test('dirty cannot be selected; clean can; apply args are {sourceId,ids,digest} only', async () => {
  const s = setup();
  await s.controller.refresh();
  s.controller.setSelected(ID_DIRTY, true);
  assert.deepEqual(s.view.selectedIds, []);
  s.controller.setSelected(ID_CLEAN, true);
  s.controller.setSelected(ID_LOCKED, true);
  assert.deepEqual(s.view.selectedIds.sort(), [ID_CLEAN, ID_LOCKED].sort());
  await s.controller.apply();
  const applyCall = s.calls.find(c => c.command === 'apply_legacy_cleanup');
  assert.ok(applyCall);
  assert.deepEqual(Object.keys(applyCall.args).sort(), ['digest', 'ids', 'sourceId']);
  assert.equal(applyCall.args.sourceId, SOURCE);
  assert.equal(applyCall.args.digest, DIGEST);
  assert.deepEqual([...applyCall.args.ids].sort(), [ID_CLEAN, ID_LOCKED].sort());
  assert.doesNotMatch(JSON.stringify(applyCall.args), /path|root|display_path|\/agents/);
});

test('notice helpers: failed count + apply/refresh copy', () => {
  assert.equal(countFailedOutcomes([{ state: 'removed' }, { state: 'Failed' }]), 1);
  assert.equal(countFailedOutcomes([{ state: 'removed' }]), 0);
  assert.equal(cleanupApplyNotice([{ state: 'removed' }]), CLEANUP_SUCCESS_NOTICE);
  assert.equal(
    cleanupApplyNotice([{ state: 'removed' }, { state: 'failed', code: 'LOCKED' }]),
    '清理结束：有 1 项失败，请核对下方结果。',
  );
  assert.equal(
    cleanupApplyNotice([{ state: 'FAILED' }, { state: 'failed' }]),
    '清理结束：有 2 项失败，请核对下方结果。',
  );
  assert.equal(cleanupRefreshFailedError([{ state: 'removed' }]), '清理已完成，但无法刷新预览。请手动刷新。');
  assert.equal(
    cleanupRefreshFailedError([{ state: 'failed' }]),
    '清理结束（有失败项），但无法刷新预览。请手动刷新。',
  );
  assert.equal(INTERRUPTED_BADGE, '中断续删');
});

test('apply all removed → success notice; selection cleared; preview refreshed', async () => {
  let previewCount = 0;
  const s = setup(async cmd => {
    if (cmd === 'preview_legacy_cleanup') {
      previewCount += 1;
      if (previewCount === 1) return previewFull;
      return { candidates: [dirtyCandidate], digest: 'b'.repeat(64), warnings: [], native_dialog_required: true };
    }
    return { outcomes: [{ id: ID_CLEAN, state: 'removed' }] };
  });
  await s.controller.refresh();
  s.controller.setSelected(ID_CLEAN, true);
  await s.controller.apply();
  assert.equal(s.view.selectedIds.length, 0);
  assert.equal(s.view.outcomes.length, 1);
  assert.equal(s.view.outcomes[0].state, 'removed');
  assert.equal(s.view.notice, CLEANUP_SUCCESS_NOTICE);
  assert.ok(previewCount >= 2);
  assert.equal(s.view.candidates.length, 1);
  assert.equal(s.view.candidates[0].id, ID_DIRTY);
});

test('apply with failed → soft notice with N; outcomes kept', async () => {
  let previewCount = 0;
  const s = setup(async cmd => {
    if (cmd === 'preview_legacy_cleanup') {
      previewCount += 1;
      if (previewCount === 1) return previewFull;
      return { candidates: [dirtyCandidate], digest: 'b'.repeat(64), warnings: [], native_dialog_required: true };
    }
    return { outcomes: [{ id: ID_CLEAN, state: 'removed' }, { id: ID_LOCKED, state: 'failed', code: 'LOCKED' }] };
  });
  await s.controller.refresh();
  s.controller.setSelected(ID_CLEAN, true);
  s.controller.setSelected(ID_LOCKED, true);
  await s.controller.apply();
  assert.equal(s.view.selectedIds.length, 0);
  assert.equal(s.view.outcomes.length, 2);
  assert.equal(s.view.outcomes[1].code, 'LOCKED');
  assert.equal(s.view.notice, '清理结束：有 1 项失败，请核对下方结果。');
  assert.doesNotMatch(s.view.notice, /^清理已完成/);
  assert.ok(previewCount >= 2);
});

test('apply with failed + refresh preview throws → soft refresh error', async () => {
  let previewCount = 0;
  const s = setup(async cmd => {
    if (cmd === 'preview_legacy_cleanup') {
      previewCount += 1;
      if (previewCount === 1) return previewFull;
      throw new Error('preview boom');
    }
    return { outcomes: [{ id: ID_LOCKED, state: 'FAILED', code: 'LOCKED' }] };
  });
  await s.controller.refresh();
  s.controller.setSelected(ID_LOCKED, true);
  await s.controller.apply();
  assert.equal(s.view.error, '清理结束（有失败项），但无法刷新预览。请手动刷新。');
  assert.doesNotMatch(s.view.error, /^清理已完成/);
  assert.equal(s.view.outcomes.length, 1);
});

test('cancel null → notice, NOT uncertain', async () => {
  const s = setup(async cmd => {
    if (cmd === 'preview_legacy_cleanup') return previewFull;
    return null;
  });
  await s.controller.refresh();
  s.controller.setSelected(ID_CLEAN, true);
  await s.controller.apply();
  assert.equal(s.view.notice, CANCEL_NOTICE);
  assert.equal(s.view.uncertain, false);
  assert.equal(s.view.outcomes.length, 0);
});

test('STALE_CONFIRMATION clears selection, prompts re-preview, not uncertain', async () => {
  let previewCount = 0;
  const s = setup(async cmd => {
    if (cmd === 'preview_legacy_cleanup') {
      previewCount += 1;
      return previewFull;
    }
    throw new Error('旧版 worktree 清理未执行：STALE_CONFIRMATION；没有删除任何内容。');
  });
  await s.controller.refresh();
  s.controller.setSelected(ID_CLEAN, true);
  await s.controller.apply();
  assert.equal(s.view.uncertain, false);
  assert.equal(s.view.error, STALE_ERROR);
  assert.deepEqual(s.view.selectedIds, []);
  assert.ok(previewCount >= 2, 'stale triggers re-preview');
  assert.doesNotMatch(JSON.stringify(s.views), /SECRET/);
});

test('busy double-click guard: only one apply invoke', async () => {
  const pending = deferred();
  const s = setup(cmd => {
    if (cmd === 'preview_legacy_cleanup') return Promise.resolve(previewFull);
    return pending.promise;
  });
  await s.controller.refresh();
  s.controller.setSelected(ID_CLEAN, true);
  const one = s.controller.apply();
  const two = s.controller.apply();
  pending.resolve({ outcomes: [{ id: ID_CLEAN, state: 'removed' }] });
  await Promise.all([one, two]);
  assert.equal(commands(s).filter(c => c === 'apply_legacy_cleanup').length, 1);
});

test('thrown non-stale after apply → uncertain; further clicks disabled', async () => {
  const s = setup(async cmd => {
    if (cmd === 'preview_legacy_cleanup') return previewFull;
    throw new Error('SECRET_BLOB_IO');
  });
  await s.controller.refresh();
  s.controller.setSelected(ID_CLEAN, true);
  await s.controller.apply();
  assert.equal(s.view.uncertain, true);
  assert.equal(s.view.error, DO_NOT_RETRY_ERROR);
  assert.doesNotMatch(s.view.error, /SECRET/);
  // further apply / select blocked
  s.controller.setSelected(ID_CLEAN, true);
  await s.controller.apply();
  assert.equal(commands(s).filter(c => c === 'apply_legacy_cleanup').length, 1);
});

test('HINT_FAILED_WARN constant and panel title / no second confirm / no abs paths', () => {
  assert.equal(HINT_FAILED_WARN, '确认会 Failed、零删除');
  assert.doesNotMatch(source, /confirm\(|window\.confirm|ask\(|message\(/);
  assert.doesNotMatch(source, /\bpath\b\s*:|\broot\b\s*:/);
  assert.ok(source.includes("'preview_legacy_cleanup'"));
  assert.ok(source.includes("'apply_legacy_cleanup'"));
  const panel = readFileSync(new URL('../src/lib/components/LegacyCleanupPanel.svelte', import.meta.url), 'utf8');
  assert.ok(panel.includes('清理旧版 worktree'));
  assert.ok(panel.includes('HINT_FAILED_WARN'));
  assert.ok(panel.includes('class="badge interrupted"'));
  assert.ok(panel.includes('中断续删'));
  assert.doesNotMatch(panel, />interrupted</);
  assert.ok(panel.includes('nativeDialogRequired'));
  assert.ok(panel.includes('cleanupDisabled(view)'));
  assert.doesNotMatch(panel, /confirm\(|window\.confirm|ask\(/);
  assert.doesNotMatch(panel, /console\.|localStorage|sessionStorage/);
  assert.doesNotMatch(panel, /WORKTREE_PINNED/);
});

test('workspace page mounts LegacyCleanupPanel without inner {#key}; outer page key kept; no command names', () => {
  const page = readFileSync(new URL('../src/routes/workspace/[id]/+page.svelte', import.meta.url), 'utf8');
  assert.ok(page.includes('LegacyCleanupPanel'));
  // Outer page key still wraps the scroll section.
  assert.match(page, /\{#key profile\.id\}\s*<section class="page-scroll"/);
  // Legacy must NOT be wrapped by its own inner key (C17b soft nit a).
  assert.doesNotMatch(
    page,
    /\{#key profile\.id\}\s*<LegacyCleanupPanel workspaceId=\{profile\.id\} \/>\s*\{\/key\}/,
  );
  assert.match(page, /<MergeConfirmPanel workspaceId=\{profile\.id\} \/>\s*<LegacyCleanupPanel workspaceId=\{profile\.id\} \/>\s*<SubagentWorkersPanel/);
  assert.doesNotMatch(page, /preview_legacy_cleanup|apply_legacy_cleanup/);
  assert.equal(page.match(/<MergeConfirmPanel workspaceId=\{profile\.id\} \/>/g)?.length, 1);
});

test('late preview after dispose cannot publish', async () => {
  const pending = deferred();
  const s = setup(() => pending.promise);
  const op = s.controller.refresh();
  // refresh emits busy:true synchronously before awaiting invoke
  const publishedBeforeDispose = s.views.length;
  assert.ok(publishedBeforeDispose >= 1);
  s.controller.dispose();
  pending.resolve(previewFull);
  await op;
  assert.equal(s.views.length, publishedBeforeDispose, 'no further publishes after dispose');
});
