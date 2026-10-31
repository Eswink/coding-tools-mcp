<script lang="ts">
  import { untrack } from 'svelte';
  import { invoke } from '@tauri-apps/api/core';
  import { createIntegrationAttentionController, emptyAttentionView, type AttentionView } from '$lib/integration-attention';
  let { workspaceId }: { workspaceId: string } = $props();
  let view = $state<AttentionView>(emptyAttentionView());
  let controller: ReturnType<typeof createIntegrationAttentionController> | undefined;
  $effect(() => {
    const id = workspaceId;
    view = emptyAttentionView();
    const current = createIntegrationAttentionController(id, invoke, next => { view = next; });
    controller = current;
    untrack(() => void current.load());
    return () => { current.dispose(); if (controller === current) controller = undefined; };
  });
</script>
{#if view.attention || view.notice || view.error}
  <section class="attention" aria-labelledby="integration-attention-title">
    {#if view.attention}
      <h3 id="integration-attention-title">合并日志需要处理</h3>
      <p>上次子代理合并或回滚中断，且工作区文件已被改动，恢复没有写入任何文件。请先在本机核对相关文件。</p>
      <p>清除后合并日志回到空闲，暂存的原内容被丢弃，之后无法再用它恢复；不会写入或还原任何工作区文件。下一步需在本机对话框中核对合并编号和文件路径后确认。</p>
      <button class="tx-btn-secondary" type="button" disabled={view.busy || view.uncertain} onclick={() => void controller?.clear()}>在本机核对并清除</button>
    {:else}
      <h3 id="integration-attention-title">合并日志</h3>
    {/if}
    {#if view.error}<p role="alert">{view.error}</p>{/if}
    {#if view.notice}<p role="status">{view.notice}</p>{/if}
  </section>
{/if}
<style>
  .attention{margin-top:1rem;padding:20px;border:1px solid var(--color-border);border-radius:var(--card-radius);background:var(--card-bg)}
  h3{font-size:17px;font-weight:600}p{font-size:.8rem;line-height:1.6;color:var(--color-text-muted);margin:.5rem 0}button{min-height:44px}[role="alert"]{color:var(--danger)}
</style>
