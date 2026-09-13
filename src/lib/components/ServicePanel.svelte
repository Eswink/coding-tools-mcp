<script lang="ts">
  import { Network, Power } from "@lucide/svelte";
  import StatusBadge from "$lib/components/primitives/StatusBadge.svelte";
  import { validServicePort } from "$lib/runtime/configuration";
  import { showToast } from "$lib/stores/toast";
  import CopyButton from "$lib/components/CopyButton.svelte";

  import type { RuntimeState } from "$lib/types";

  interface Props {
    title: string;
    subtitle: string;
    status: RuntimeState;
    statusMessage?: string;
    port: number;
    portEditable?: boolean;
    busy?: boolean;
    tunnelType?: string;
    localEndpoint: string;
    publicEndpoint?: string;
    publicLabel?: string;
    onToggle: () => void | Promise<void>;
    onPortChange?: (port: number) => void | Promise<void>;
  }

  let {
    title,
    subtitle,
    status,
    statusMessage = "",
    port,
    portEditable = false,
    busy = false,
    tunnelType = "none",
    localEndpoint,
    publicEndpoint = "",
    publicLabel = "公网",
    onToggle,
    onPortChange,
  }: Props = $props();

  let draftPort = $state(0);
  let savingPort = $state(false);

  $effect(() => {
    draftPort = port;
  });

  const running = $derived(status === "running");
  const showError = $derived(status === "error" && Boolean(statusMessage));
  const canEditPort = $derived(portEditable && !busy && !savingPort && !running && status !== "starting" && status !== "stopping");
  const tunnelEnabled = $derived(tunnelType === "cloudflare" || tunnelType === "frp");
  const tunnelLabel = $derived(
    tunnelType === "cloudflare" ? "Cloudflare" : tunnelType === "frp" ? "FRP" : "",
  );

  async function commitPort() {
    if (!canEditPort || !onPortChange || draftPort === port) return;
    if (!validServicePort(draftPort)) {
      draftPort = port;
      showToast("端口必须是 1024 至 65535 的整数。", { kind: "error" });
      return;
    }
    const nextPort = draftPort;
    savingPort = true;
    try { await onPortChange(nextPort); }
    catch (error) {
      draftPort = port;
      showToast(String(error), { title: "端口应用失败", kind: "error" });
    } finally { savingPort = false; }
  }

</script>

<article class="tx-card p-5">
  <div class="flex items-start justify-between gap-3">
    <div class="min-w-0">
      <div class="service-heading"><span class="service-icon" aria-hidden="true"><Network size={26} /></span><h3>{title} 服务配置</h3><StatusBadge state={status} /></div>
      <p class="mt-1 text-sm text-[var(--color-text-muted)]">{subtitle}</p>
      {#if tunnelEnabled}
        <p class="mt-1 text-xs text-[var(--color-text-muted)]">
          {tunnelLabel} 隧道随服务自动连接，停止服务时一并断开
        </p>
      {/if}
    </div>
    <button
      type="button"
      class="tx-btn-primary shrink-0"
      class:tx-btn-danger={running}
      disabled={busy || savingPort || status === "starting" || status === "stopping"}
      onclick={onToggle}
    >
      <Power size={18} aria-hidden="true" />
      {#if busy}
        处理中…
      {:else if running}
        停止
      {:else}
        启动
      {/if}
    </button>
  </div>

  {#if showError}
    <div class="tx-alert tx-alert--error mt-4" role="alert">
      {statusMessage}
    </div>
  {/if}

  <div class="endpoint-grid">
    <div class="tx-info-block">
      <div class="tx-info-row">
        <span class="tx-info-label">端口</span>
        {#if canEditPort}
          <input
            type="number"
            min="1024"
            max="65535"
            class="tx-input tx-input-inline"
            aria-label={`${title} 服务端口`}
            bind:value={draftPort}
            onchange={commitPort}
          />
        {:else}
          <span class="tx-mono text-sm">{port}</span>
        {/if}
      </div>
    </div>

    <div class="tx-info-block">
      <div class="tx-info-row">
        <span class="tx-info-label">本地地址</span>
        <CopyButton value={localEndpoint} />
      </div>
      <p class="tx-mono mt-1.5 break-all text-sm" title={localEndpoint}>{localEndpoint}</p>
    </div>

    {#if publicEndpoint || publicLabel}
      <div class="tx-info-block">
        <div class="tx-info-row">
          <span class="tx-info-label">{publicLabel}</span>
          {#if publicEndpoint}
            <CopyButton value={publicEndpoint} />
          {/if}
        </div>
        <p class="tx-mono mt-1.5 break-all text-sm text-[var(--color-text-secondary)]">
          {publicEndpoint || "未配置隧道"}
        </p>
      </div>
    {/if}
  </div>
</article>

<style>
  .service-heading { display:flex; align-items:center; flex-wrap:wrap; gap:12px; }
  .service-icon { display:grid; place-items:center; width:46px; height:46px; border-radius:12px; background:var(--primary-soft); color:var(--primary); }
  h3 { font-size:18px; font-weight:650; }
  .endpoint-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; margin-top:20px; }
  .tx-info-block { border:1px solid var(--card-border); min-width:0; padding:13px 16px; }
  .tx-info-block:last-child { grid-column:1/-1; }
  @media(max-width:1100px) { .endpoint-grid { grid-template-columns:minmax(0,1fr); } }
</style>
