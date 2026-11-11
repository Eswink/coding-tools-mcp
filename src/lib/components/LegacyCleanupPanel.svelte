<script lang="ts">
  import { untrack } from 'svelte';
  import { invoke } from '@tauri-apps/api/core';
  import {
    actionsDisabled,
    cleanupDisabled,
    createLegacyCleanupController,
    emptyLegacyCleanupView,
    HINT_FAILED_WARN,
    INTERRUPTED_BADGE,
    type LegacyCleanupView,
  } from '$lib/legacy-cleanup';

  let { workspaceId }: { workspaceId: string } = $props();
  let view = $state<LegacyCleanupView>(emptyLegacyCleanupView());
  let controller: ReturnType<typeof createLegacyCleanupController> | undefined;

  $effect(() => {
    const id = workspaceId;
    view = emptyLegacyCleanupView();
    const current = createLegacyCleanupController(id, invoke, next => { view = next; });
    controller = current;
    untrack(() => void current.refresh());
    return () => { current.dispose(); if (controller === current) controller = undefined; };
  });

  function onToggle(id: string, checked: boolean) {
    controller?.setSelected(id, checked);
  }
</script>

<section class="legacy-cleanup" aria-labelledby="legacy-cleanup-title">
  <div class="head-row">
    <h3 id="legacy-cleanup-title">清理旧版 worktree</h3>
    <button class="tx-btn-secondary" type="button"
      disabled={actionsDisabled(view)}
      onclick={() => void controller?.refresh()}>刷新预览</button>
  </div>

  {#if view.nativeDialogRequired}
    <p class="muted badge-note" role="note">将使用本机确认对话框</p>
  {/if}

  {#if view.warnings.length > 0}
    <ul class="warnings" role="note">
      {#each view.warnings as w (w.id + w.code)}
        <li class="warn-item"><code>{w.id}</code>：{w.code}</li>
      {/each}
    </ul>
  {/if}

  {#if view.candidates.length === 0}
    <p class="muted">当前没有可清理的旧版 worktree。</p>
  {:else}
    <ul class="cards">
      {#each view.candidates as item (item.id)}
        <li class="card" class:dirty={!item.clean} data-id={item.id}>
          <label class="row">
            <input type="checkbox"
              disabled={!item.selectable || actionsDisabled(view)}
              checked={view.selectedIds.includes(item.id)}
              onchange={(e) => onToggle(item.id, e.currentTarget.checked)} />
            <span class="label">{item.displayPath}</span>
            <code class="head">{item.headShort}</code>
          </label>
          <div class="badges">
            {#if item.interrupted}
              <span class="badge interrupted">{INTERRUPTED_BADGE}</span>
            {/if}
            {#if item.hint}
              <span class="badge hint">{item.hint}</span>
            {/if}
            {#if !item.clean}
              <span class="badge dirty">dirty（不可选）</span>
            {/if}
          </div>
          {#if item.hintWarn}
            <p class="warn" role="note">{HINT_FAILED_WARN}</p>
          {/if}
        </li>
      {/each}
    </ul>
    <div class="actions">
      <button class="tx-btn-secondary" type="button"
        disabled={cleanupDisabled(view)}
        onclick={() => void controller?.apply()}>确认清理所选</button>
    </div>
  {/if}

  {#if view.outcomes.length > 0}
    <ul class="outcomes" aria-label="清理结果">
      {#each view.outcomes as o (o.id)}
        <li><code>{o.id}</code> → {o.state}{#if o.code}（{o.code}）{/if}</li>
      {/each}
    </ul>
  {/if}

  {#if view.error}<p role="alert">{view.error}</p>{/if}
  {#if view.notice}<p role="status">{view.notice}</p>{/if}
</section>

<style>
  .legacy-cleanup{margin-top:1rem;padding:20px;border:1px solid var(--color-border);border-radius:var(--card-radius);background:var(--card-bg)}
  .head-row{display:flex;align-items:center;justify-content:space-between;gap:.75rem}
  h3{font-size:17px;font-weight:600;margin:0}
  .muted{font-size:.8rem;line-height:1.6;color:var(--color-text-muted);margin:.5rem 0}
  .badge-note{font-size:.75rem}
  .warnings{list-style:none;margin:.5rem 0 0;padding:0}
  .warn-item{font-size:.8rem;color:var(--danger);margin:.25rem 0}
  .cards{list-style:none;margin:.75rem 0 0;padding:0;display:grid;gap:.75rem}
  .card{padding:14px;border:1px solid var(--color-border);border-radius:12px;background:var(--card-bg)}
  .card.dirty{opacity:.85}
  .row{display:flex;align-items:center;gap:.6rem;cursor:pointer}
  .label{flex:1;font-size:.95rem}
  .head{font-size:.8rem;color:var(--color-text-muted)}
  .badges{display:flex;flex-wrap:wrap;gap:.4rem;margin-top:.5rem}
  .badge{font-size:.75rem;padding:.15rem .5rem;border-radius:999px;border:1px solid var(--color-border);color:var(--color-text-muted)}
  .badge.interrupted{border-color:var(--danger);color:var(--danger)}
  .badge.hint{border-color:var(--color-border)}
  .badge.dirty{opacity:.9}
  .warn{margin:.5rem 0 0;font-size:.8rem;color:var(--danger)}
  .actions{display:flex;gap:.5rem;margin-top:.75rem}
  .outcomes{list-style:none;margin:.75rem 0 0;padding:0;font-size:.85rem}
  .outcomes li{margin:.25rem 0}
  button{min-height:40px}
  [role="alert"]{color:var(--danger);font-size:.8rem}
  code{font-size:.8rem}
</style>
