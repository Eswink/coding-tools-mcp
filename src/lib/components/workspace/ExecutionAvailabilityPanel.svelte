<script lang="ts">
  import type { RuntimeState } from "$lib/types";

  interface Props {
    state?: "online" | "offline";
    runtimeState: RuntimeState;
    busy?: boolean;
    onToggle: () => void | Promise<void>;
  }

  let { state, runtimeState, busy = false, onToggle }: Props = $props();

  const running = $derived(runtimeState === "running");
  const paused = $derived(state === "offline");
  const ready = $derived(running && (state === "online" || state === "offline"));
  const stateLabel = $derived(
    !running ? "Connector 未运行" : paused ? "远程执行已暂停" : state === "online" ? "远程执行在线" : "正在读取执行状态",
  );
</script>

<section class="tx-card p-5 execution-availability" aria-label="远程执行可用性">
  <div class="availability-row">
    <div class="availability-copy">
      <div class="availability-heading">
        <h3>远程执行可用性</h3>
        <span class="availability-state" class:paused class:online={state === "online" && running}>
          {stateLabel}
        </span>
      </div>
      <p class="mt-1 text-sm text-[var(--color-text-muted)]">
        暂停只阻止新的远程业务调用；MCP Connector、OAuth 控制面和已运行的隧道保持在线。
      </p>
      <p class="mt-1 text-xs text-[var(--color-text-muted)]">
        “停止”仍是硬停止，会关闭 Connector 与隧道。两种操作不会互相替代。
      </p>
    </div>

    <button
      type="button"
      class={paused ? "tx-btn-primary shrink-0" : "tx-btn-ghost shrink-0"}
      disabled={busy || !ready}
      onclick={onToggle}
    >
      {#if busy}
        处理中…
      {:else if paused}
        恢复远程执行
      {:else}
        暂停远程执行
      {/if}
    </button>
  </div>

  {#if running && paused}
    <div class="tx-alert mt-4" role="status">
      新的已授权业务调用会收到 <span class="tx-mono">WORKSPACE_OFFLINE</span>；现有授权不会因此转移或重建。
    </div>
  {/if}
</section>

<style>
  .execution-availability { min-width:0; }
  .availability-row { display:flex; align-items:flex-start; justify-content:space-between; gap:18px; }
  .availability-copy { min-width:0; }
  .availability-heading { display:flex; align-items:center; flex-wrap:wrap; gap:10px; }
  h3 { font-size:16px; font-weight:650; }
  .availability-state {
    display:inline-flex;
    align-items:center;
    min-height:26px;
    padding:3px 9px;
    border:1px solid var(--border);
    border-radius:999px;
    font-size:12px;
    font-weight:650;
    color:var(--text-muted);
    background:var(--card-bg);
  }
  .availability-state.online { border-color:var(--success); color:var(--success); }
  .availability-state.paused { border-color:var(--warning); color:var(--warning); }
  @media(max-width:760px) {
    .availability-row { flex-direction:column; }
  }
</style>
