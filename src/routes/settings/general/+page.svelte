<script lang="ts">
  import AppearanceSettings from "$lib/components/settings/AppearanceSettings.svelte";
  import { Network, MemoryStick, Package } from "@lucide/svelte";
  import PageHeader from "$lib/components/layout/PageHeader.svelte";
  import SurfaceCard from "$lib/components/primitives/SurfaceCard.svelte";
  import { Settings } from "@lucide/svelte";
  import { onMount } from "svelte";
  import { ask, message } from "@tauri-apps/plugin-dialog";
  import { ExternalLink, RefreshCw } from "@lucide/svelte";
  import { getProxy, setProxy, type ProxyConfigDto } from "$lib/api/settings";
  import { checkAppUpdate, openUrl } from "$lib/api/app-info";
  import { APP_VERSION } from "$lib/app-version";
  import { RELEASES_LATEST_URL, REPO_URL } from "$lib/app-links";
  import { getWebviewMemorySample } from "$lib/api/ui-memory";
  import { reloadUiOnly } from "$lib/ui-memory-guard";
  import { showToast } from "$lib/stores/toast";

  let proxy = $state<ProxyConfigDto>({ mode: "none", url: "" });
  let changed = $state(false);
  let saving = $state(false);
  let checkingUpdate = $state(false);
  let releasingUi = $state(false);
  let memoryHint = $state<string | null>(null);

  async function refresh() {
    try {
      proxy = await getProxy();
      changed = false;
    } catch (e) {
      await message(String(e), { title: "加载失败", kind: "error" });
    }
  }

  async function save() {
    saving = true;
    try {
      await setProxy(proxy);
      changed = false;
      await message("代理设置已保存。", { title: "已保存", kind: "info" });
    } catch (e) {
      await message(String(e), { title: "保存失败", kind: "error" });
    } finally {
      saving = false;
    }
  }

  function handleChange() {
    changed = true;
  }

  async function openLink(url: string, title: string) {
    try {
      await openUrl(url);
    } catch (e) {
      await message(String(e), { title, kind: "error" });
    }
  }

  async function handleCheckUpdate() {
    if (checkingUpdate) return;
    checkingUpdate = true;
    try {
      const result = await checkAppUpdate();
      if (result.updateAvailable) {
        const openRelease = await ask(
          `发现新版本 ${result.latestTag}（当前 v${result.currentVersion}）。是否打开 Releases 页面下载？`,
          { title: "有可用更新", kind: "info", okLabel: "打开下载页", cancelLabel: "稍后" },
        );
        if (openRelease) {
          await openUrl(result.releaseUrl || RELEASES_LATEST_URL);
        }
      } else {
        await message(`当前已是最新版本（v${result.currentVersion}）。`, {
          title: "检查更新",
          kind: "info",
        });
      }
    } catch (e) {
      await message(String(e), { title: "检查更新失败", kind: "error" });
    } finally {
      checkingUpdate = false;
    }
  }

  async function refreshMemoryHint() {
    try {
      const sample = await getWebviewMemorySample();
      if (!sample.supported) {
        memoryHint = "当前平台暂不支持界面内存采样。";
        return;
      }
      memoryHint = `界面约 ${Math.round(sample.webviewMb)} MB（${sample.webviewProcessCount} 个 WebView 进程），主进程约 ${Math.round(sample.mainMb)} MB。`;
    } catch {
      memoryHint = null;
    }
  }

  async function handleReleaseUiMemory() {
    if (releasingUi) return;
    const ok = await ask(
      "将重建界面进程（WebView）以释放内存。MCP、Actions 与 FRP 隧道会继续在后台运行，不会被停止。",
      { title: "释放界面内存", kind: "info", okLabel: "立即释放", cancelLabel: "取消" },
    );
    if (!ok) return;
    releasingUi = true;
    showToast("正在重建界面进程…", { title: "释放界面内存", kind: "info", duration: 2000 });
    await reloadUiOnly("settings-manual");
  }

  onMount(() => {
    void refresh();
    void refreshMemoryHint();
  });
</script>

<section class="page-scroll">
  <div class="page-header"><PageHeader title="通用设置" description="配置应用外观、网络代理和界面维护，查看当前版本。">{#snippet icon()}<Settings size={30} />{/snippet}</PageHeader></div>

  <div class="page-body settings-grid">
    <AppearanceSettings />
    <SurfaceCard title="版本与更新" description="从官方仓库查看发行说明和安装包。">
      {#snippet icon()}<Package size={24} />{/snippet}
      <p class="mt-1 text-xs text-[var(--color-text-muted)]">
        当前版本 v{APP_VERSION}。仓库与新版本安装包都在 GitHub Releases。
      </p>
      <div class="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          class="tx-btn-ghost"
          onclick={() => void openLink(REPO_URL, "无法打开仓库")}
        >
          <ExternalLink size={14} strokeWidth={2} />
          打开仓库
        </button>
        <button
          type="button"
          class="tx-btn-ghost"
          onclick={() => void openLink(RELEASES_LATEST_URL, "无法打开 Releases")}
        >
          <ExternalLink size={14} strokeWidth={2} />
          打开 Releases
        </button>
        <button
          type="button"
          class="tx-btn-primary"
          disabled={checkingUpdate}
          onclick={() => void handleCheckUpdate()}
        >
          <RefreshCw size={14} strokeWidth={2} class={checkingUpdate ? "animate-spin" : ""} />
          {checkingUpdate ? "检查中…" : "检查更新"}
        </button>
      </div>
    </SurfaceCard>

    <SurfaceCard title="界面内存" description="仅维护界面进程，不停止后台服务。">
      {#snippet icon()}<MemoryStick size={24} />{/snippet}
      <p class="mt-1 text-xs text-[var(--color-text-muted)]">
        长时间运行后 WebView 可能占用较高内存。释放会重建界面进程，不会停止 MCP 或隧道。
      </p>
      {#if memoryHint}
        <p class="mt-2 text-xs text-[var(--color-text-muted)]">{memoryHint}</p>
      {/if}
      <div class="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          class="tx-btn-ghost"
          onclick={() => void refreshMemoryHint()}
        >
          刷新占用
        </button>
        <button
          type="button"
          class="tx-btn-primary"
          disabled={releasingUi}
          onclick={() => void handleReleaseUiMemory()}
        >
          <RefreshCw size={14} strokeWidth={2} class={releasingUi ? "animate-spin" : ""} />
          {releasingUi ? "刷新中…" : "释放界面内存"}
        </button>
      </div>
    </SurfaceCard>

    <SurfaceCard title="代理与网络" description="配置应用访问外部服务所使用的代理。">
      {#snippet icon()}<Network size={24} />{/snippet}
      <form
        class="mt-4 grid gap-3"
        onsubmit={(e) => { e.preventDefault(); void save(); }}
      >
        <label class="grid gap-1">
          <span class="text-xs text-[var(--color-text-muted)]">代理模式</span>
          <select
            class="tx-select"
            bind:value={proxy.mode}
            onchange={handleChange}
          >
            <option value="none">无代理</option>
            <option value="system">系统代理</option>
            <option value="manual">手动代理地址</option>
          </select>
        </label>

        {#if proxy.mode === "manual"}
          <label class="grid gap-1">
            <span class="text-xs text-[var(--color-text-muted)]">代理地址</span>
            <input
              type="text"
              class="tx-input tx-mono"
              placeholder="http://127.0.0.1:7890"
              bind:value={proxy.url}
              oninput={handleChange}
            />
            <span class="text-xs text-[var(--color-text-muted)]">
              支持 HTTP/HTTPS/SOCKS 代理，如 http://127.0.0.1:7890
            </span>
          </label>
        {/if}

        <div class="flex justify-end pt-1">
          <button
            type="submit"
            class="tx-btn-primary"
            disabled={!changed || saving}
          >
            {saving ? "保存中…" : "保存设置"}
          </button>
        </div>
      </form>
    </SurfaceCard>
  </div>
</section>
