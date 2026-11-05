<script lang="ts">
  import { untrack } from 'svelte';
  import { invoke } from '@tauri-apps/api/core';
  import { confirm } from '@tauri-apps/plugin-dialog';
  import {
    createSubagentWorkersController,
    emptyWorkersView,
    workerStateLabels,
    WINDOWS_UNSANDBOXED_CARD_LABEL,
    LINUX_SANDBOX_DEFERRED_LABEL,
    type WorkersView,
  } from '$lib/subagent-workers';

  let { workspaceId }: { workspaceId: string } = $props();
  let view = $state<WorkersView>(emptyWorkersView());
  let controller: ReturnType<typeof createSubagentWorkersController> | undefined;

  $effect(() => {
    const id = workspaceId;
    view = emptyWorkersView();
    const current = createSubagentWorkersController(id, invoke, next => { view = next; }, confirm);
    controller = current;
    untrack(() => void current.load());
    return () => { current.dispose(); if (controller === current) controller = undefined; };
  });

  function stateText(state: string): string {
    return workerStateLabels[state] ?? state;
  }
</script>

<section class="workers" aria-labelledby="subagent-workers-title">
  <h3 id="subagent-workers-title">子代理</h3>
  {#if view.unavailable}
    <p role="status">{view.error || '暂无法列出子代理。'}</p>
  {:else if view.workers.length === 0}
    <p class="muted">当前没有子代理。</p>
  {:else}
    <ul class="cards">
      {#each view.workers as worker (worker.workerId)}
        <li class="card">
          <div class="head">
            <strong class="label">{worker.label}</strong>
            <span class="badge" data-state={worker.state}>{stateText(worker.state)}</span>
          </div>
          <dl class="meta">
            <div><dt>基线</dt><dd><code>{worker.baseHeadShort}</code></dd></div>
            <div><dt>活动</dt><dd>{worker.lastActivityText}</dd></div>
            <div title="可合入改动文件数（快照；不含 withheld/unsupported）">
              <dt>改动</dt><dd aria-label="可合入改动文件数（快照；不含 withheld/unsupported）">{worker.changedFilesText}</dd>
            </div>
          </dl>
          {#if worker.windowsUnsandboxed}
            <p class="warn" role="note">{WINDOWS_UNSANDBOXED_CARD_LABEL}</p>
          {:else if worker.linuxSandboxDeferred}
            <p class="muted" role="note">{LINUX_SANDBOX_DEFERRED_LABEL}</p>
          {/if}
          <div class="actions">
            <button class="tx-btn-secondary" type="button" disabled={view.busy || view.uncertain || worker.state !== 'ready'}
              onclick={() => void controller?.cancel(worker.workerId)}>取消</button>
            <button class="tx-btn-secondary" type="button" disabled={view.busy || view.uncertain || worker.state === 'discarded' || worker.state === 'creating' || worker.state === 'integrate_pending'}
              onclick={() => void controller?.discard(worker.workerId)}>丢弃</button>
          </div>
        </li>
      {/each}
    </ul>
  {/if}
  {#if view.error && !view.unavailable}<p role="alert">{view.error}</p>{/if}
  {#if view.notice}<p role="status">{view.notice}</p>{/if}
</section>

<style>
  .workers{margin-top:1rem;padding:20px;border:1px solid var(--color-border);border-radius:var(--card-radius);background:var(--card-bg)}
  h3{font-size:17px;font-weight:600}
  .muted{font-size:.8rem;line-height:1.6;color:var(--color-text-muted);margin:.5rem 0}
  .cards{list-style:none;margin:.75rem 0 0;padding:0;display:grid;gap:.75rem}
  .card{padding:14px;border:1px solid var(--color-border);border-radius:12px;background:var(--card-bg)}
  .head{display:flex;align-items:center;justify-content:space-between;gap:.75rem}
  .label{font-size:.95rem}
  .badge{font-size:.75rem;padding:.2rem .55rem;border-radius:999px;border:1px solid var(--color-border);color:var(--color-text-muted)}
  .meta{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.5rem;margin:.75rem 0 0;font-size:.8rem}
  .meta dt{color:var(--color-text-muted)} .meta dd{margin:.15rem 0 0}
  .warn{margin:.6rem 0 0;font-size:.8rem;color:var(--danger)}
  .actions{display:flex;gap:.5rem;margin-top:.75rem}
  button{min-height:40px}
  [role="alert"]{color:var(--danger);font-size:.8rem}
  code{font-size:.8rem}
</style>
