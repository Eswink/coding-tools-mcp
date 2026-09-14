<script lang="ts">
  import { AlertTriangle, RefreshCw } from "@lucide/svelte";
  import type { StartupStatus } from "$lib/api/app-info";

  interface Props {
    status: StartupStatus;
    busy?: boolean;
    onRetry: () => void;
  }

  let { status, busy = false, onRetry }: Props = $props();
</script>

<div class="page-scroll flex items-center justify-center p-8">
  <section class="tx-card max-w-2xl p-6" aria-live="polite">
    <div class="flex items-start gap-4">
      <div class="mt-1 rounded-xl bg-[var(--warning-soft)] p-3 text-[var(--warning)]">
        <AlertTriangle size={22} aria-hidden="true" />
      </div>
      <div class="min-w-0 flex-1">
        <p class="text-[11px] font-medium uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
          Startup recovery · {status.platform}
        </p>
        <h2 class="mt-2 text-xl font-semibold">配置存储暂不可用</h2>
        <p class="mt-3 text-sm leading-relaxed text-[var(--color-text-secondary)]">{status.message}</p>
        <p class="mt-3 text-xs leading-relaxed text-[var(--color-text-muted)]">
          在恢复成功前不会启动 MCP、Actions、隧道或聊天审批后台任务，也不会创建替代密钥或把加密配置降级为明文。
        </p>
        <div class="mt-5 flex flex-wrap items-center gap-3">
          <button type="button" class="tx-btn-primary" disabled={busy} onclick={onRetry}>
            <RefreshCw size={16} class:animate-spin={busy} aria-hidden="true" />
            {busy ? "正在重试" : "修复环境后重试"}
          </button>
          <span class="text-xs text-[var(--color-text-muted)]">如果仍失败，可从启动日志确认最后完成阶段。</span>
        </div>
      </div>
    </div>
  </section>
</div>
