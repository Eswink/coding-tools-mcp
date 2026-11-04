<script lang="ts">
  import { untrack } from 'svelte';
  import { invoke } from '@tauri-apps/api/core';
  import {
    actionsDisabled,
    createMergeConfirmController,
    emptyMergeConfirmView,
    type MergeConfirmView,
    type PendingKind,
  } from '$lib/merge-confirm';

  let { workspaceId }: { workspaceId: string } = $props();
  let view = $state<MergeConfirmView>(emptyMergeConfirmView());
  let controller: ReturnType<typeof createMergeConfirmController> | undefined;

  $effect(() => {
    const id = workspaceId;
    view = emptyMergeConfirmView();
    const current = createMergeConfirmController(id, invoke, next => { view = next; });
    controller = current;
    untrack(() => void current.load());
    return () => { current.dispose(); if (controller === current) controller = undefined; };
  });

  function kindText(kind: PendingKind): string {
    if (kind === 'rollback') return '待回滚';
    return '待合入';
  }

  function primaryLabel(kind: PendingKind): string {
    if (kind === 'rollback') return '确认回滚';
    return '合入当前分支';
  }
</script>

{#if view.unavailable || view.items.length > 0 || view.notice || view.error}
  <section class="merge-confirm" aria-labelledby="merge-confirm-title">
    <h3 id="merge-confirm-title">合并确认</h3>
    {#if view.unavailable}
      <p role="status">{view.error || '暂无法列出待确认项。'}</p>
    {:else if view.items.length === 0}
      <p class="muted">当前没有待合入或待回滚项。</p>
    {:else}
      <ul class="cards">
        {#each view.items as item (item.integrationId)}
          <li class="card" data-kind={item.kind}>
            <div class="head">
              <strong class="label">{item.label}</strong>
              <span class="badge">{kindText(item.kind)}</span>
            </div>
            <dl class="meta">
              <div><dt>diff</dt><dd><code>{item.diffShaShort}</code></dd></div>
              <div><dt>文件数</dt><dd>{item.filesCount}</dd></div>
            </dl>
            {#if item.expiresText}
              <p class="muted" role="note">{item.expiresText}</p>
            {/if}
            {#if item.closedReasonText}
              <p class="warn" role="note">{item.closedReasonText}</p>
            {/if}
            <div class="actions">
              <button class="tx-btn-secondary" type="button"
                disabled={actionsDisabled(view, item)}
                onclick={() => void controller?.confirm(item.integrationId, item.kind)}>{primaryLabel(item.kind)}</button>
              <button class="tx-btn-secondary" type="button"
                disabled={actionsDisabled(view, item)}
                onclick={() => void controller?.reject(item.integrationId, item.kind)}>拒绝</button>
            </div>
          </li>
        {/each}
      </ul>
    {/if}
    {#if view.error && !view.unavailable}<p role="alert">{view.error}</p>{/if}
    {#if view.notice}<p role="status">{view.notice}</p>{/if}
  </section>
{/if}

<style>
  .merge-confirm{margin-top:1rem;padding:20px;border:1px solid var(--color-border);border-radius:var(--card-radius);background:var(--card-bg)}
  h3{font-size:17px;font-weight:600}
  .muted{font-size:.8rem;line-height:1.6;color:var(--color-text-muted);margin:.5rem 0}
  .cards{list-style:none;margin:.75rem 0 0;padding:0;display:grid;gap:.75rem}
  .card{padding:14px;border:1px solid var(--color-border);border-radius:12px;background:var(--card-bg)}
  .head{display:flex;align-items:center;justify-content:space-between;gap:.75rem}
  .label{font-size:.95rem}
  .badge{font-size:.75rem;padding:.2rem .55rem;border-radius:999px;border:1px solid var(--color-border);color:var(--color-text-muted)}
  .meta{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.5rem;margin:.75rem 0 0;font-size:.8rem}
  .meta dt{color:var(--color-text-muted)} .meta dd{margin:.15rem 0 0}
  .warn{margin:.6rem 0 0;font-size:.8rem;color:var(--danger)}
  .actions{display:flex;gap:.5rem;margin-top:.75rem}
  button{min-height:40px}
  [role="alert"]{color:var(--danger);font-size:.8rem}
  code{font-size:.8rem}
</style>
