<script lang="ts">
  import { AlertTriangle, ClipboardCopy, RefreshCw } from "@lucide/svelte";
  import type { StartupStatus } from "$lib/api/app-info";

  interface Props {
    status: StartupStatus;
    busy?: boolean;
    onRetry: () => void;
    onCopyDiagnostics?: () => void;
  }

  let { status, busy = false, onRetry, onCopyDiagnostics }: Props = $props();

  function guidanceFor(reason: string | null): string {
    switch (reason) {
      case "session_bus_missing":
        return "请从正常的 Ubuntu 桌面登录会话启动应用；不要使用 sudo 启动 GUI。";
      case "secret_service_unavailable":
        return "请确认桌面 Secret Service（例如 GNOME Keyring）可用后重试。";
      case "secret_service_locked_or_denied":
        return "请解锁登录钥匙串或允许凭据访问，然后点击重试安全存储。";
      case "secret_service_default_collection_missing":
        return "当前 Secret Service 没有持久默认凭据库。若这是首次使用，点击下方按钮后由系统凭据服务创建；系统可能弹出 GNOME Keyring 密码窗口，应用不会读取或保存该密码。若已有加密配置，应用不会创建新的凭据库或替代密钥。";
      case "encrypted_config_key_missing":
      case "key_entry_missing":
        return "原密钥缺失时不会生成替代密钥。请使用原系统账户及其凭据备份恢复。";
      case "config_invalid_or_unsupported":
        return "原配置不会被自动覆盖。请保留当前文件并使用有效备份或兼容版本恢复。";
      case "config_permission_or_io":
        return "请检查当前用户对配置目录和文件的所有权、权限及存储状态。";
      default:
        return "可复制启动诊断以确认会话总线、凭据服务和配置文件的安全状态。";
    }
  }

  function retryLabel(reason: string | null, waiting: boolean): string {
    if (reason === "secret_service_default_collection_missing") {
      return waiting ? "等待系统凭据库" : "创建系统凭据库并重试";
    }
    return waiting ? "正在重试" : "重试安全存储";
  }
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
        {#if status.reasonCode}
          <p class="mt-2 font-mono text-xs text-[var(--color-text-muted)]">reason: {status.reasonCode}</p>
        {/if}
        <p class="mt-3 text-sm leading-relaxed text-[var(--color-text-secondary)]">{status.message}</p>
        <p class="mt-2 text-sm leading-relaxed text-[var(--color-text-secondary)]">
          {guidanceFor(status.reasonCode)}
        </p>
        <p class="mt-3 text-xs leading-relaxed text-[var(--color-text-muted)]">
          在恢复成功前不会启动 MCP、Actions、隧道或聊天审批后台任务，也不会创建替代密钥或把加密配置降级为明文。
        </p>
        <div class="mt-5 flex flex-wrap items-center gap-3">
          <button type="button" class="tx-btn-primary" disabled={busy} onclick={onRetry}>
            <RefreshCw size={16} class={busy ? "animate-spin" : ""} aria-hidden="true" />
            {retryLabel(status.reasonCode, busy)}
          </button>
          {#if onCopyDiagnostics}
            <button type="button" class="tx-btn-secondary" onclick={onCopyDiagnostics}>
              <ClipboardCopy size={16} aria-hidden="true" />
              复制启动诊断
            </button>
          {/if}
        </div>
      </div>
    </div>
  </section>
</div>
