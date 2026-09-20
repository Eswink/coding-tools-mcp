<script lang="ts">
  import type { RuntimeState } from "$lib/types";

  interface Props {
    state?: "online" | "offline";
    runtimeState: RuntimeState;
    busy?: boolean;
    onStart: () => void | Promise<void>;
    onToggle: () => void | Promise<void>;
    onStop: () => void | Promise<void>;
  }

  let {
    state,
    runtimeState,
    busy = false,
    onStart,
    onToggle,
    onStop,
  }: Props = $props();

  const running = $derived(runtimeState === "running");
  const transitioning = $derived(runtimeState === "starting" || runtimeState === "stopping");
  const paused = $derived(state === "offline");
  const executionReady = $derived(running && (state === "online" || state === "offline"));
  const primaryDisabled = $derived(
    busy || transitioning || (running && !executionReady),
  );
  const stateLabel = $derived(
    runtimeState === "starting"
      ? "Connector 启动中"
      : runtimeState === "stopping"
        ? "Connector 停止中"
        : !running
          ? "Connector 未运行"
          : paused
            ? "远程执行已暂停"
            : state === "online"
              ? "远程执行在线"
              : "正在读取执行状态",
  );
  const primaryLabel = $derived(
    runtimeState === "starting"
      ? "启动中…"
      : runtimeState === "stopping"
        ? "停止中…"
        : running
          ? paused
            ? "恢复远程执行"
            : "暂停远程执行"
          : "启动 Connector",
  );

  function runPrimary() {
    if (primaryDisabled) return;
    if (running) {
      void onToggle();
    } else {
      void onStart();
    }
  }
</script>

<section class="tx-card p-5 execution-availability" aria-label="MCP Connector 与远程执行">
  <div class="availability-row">
    <div class="availability-copy">
      <div class="availability-heading">
        <h3>MCP Connector 与远程执行</h3>
        <span class="availability-state" class:paused class:online={state === "online" && running}>
          {stateLabel}
        </span>
      </div>

      {#if running}
        <p class="mt-1 text-sm text-[var(--color-text-muted)]">
          暂停只阻止新的远程业务调用；MCP Connector、OAuth 控制面和已运行的隧道保持在线。
        </p>
      {:else}
        <p class="mt-1 text-sm text-[var(--color-text-muted)]">
          启动 Connector 后，MCP/OAuth 控制面与已配置的公网隧道会进入可连接状态。
        </p>
      {/if}

      <p class="mt-1 text-xs text-[var(--color-text-muted)]">
        停止 Connector 会关闭 MCP/OAuth 监听器和公网隧道；如果只是暂时不允许远程操作，请使用“暂停远程执行”。
      </p>
    </div>

    <div class="availability-actions">
      <button
        type="button"
        class="tx-btn-primary shrink-0"
        disabled={primaryDisabled}
        onclick={runPrimary}
      >
        {#if busy}
          处理中…
        {:else}
          {primaryLabel}
        {/if}
      </button>

      {#if running}
        <button
          type="button"
          class="tx-btn-ghost tx-btn-destructive shrink-0"
          disabled={busy || transitioning}
          onclick={() => void onStop()}
        >
          停止 Connector
        </button>
      {/if}
    </div>
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
  .availability-actions { display:flex; align-items:center; flex-wrap:wrap; justify-content:flex-end; gap:8px; }
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
    .availability-actions { width:100%; justify-content:flex-start; }
  }
</style>
