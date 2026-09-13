<script lang="ts">
  import { Download, Boxes } from "@lucide/svelte";
  import PageHeader from "$lib/components/layout/PageHeader.svelte";
  import SurfaceCard from "$lib/components/primitives/SurfaceCard.svelte";
  import { Package } from "@lucide/svelte";
  import { onMount } from "svelte";
  import { message } from "@tauri-apps/plugin-dialog";
  import type { DownloadConfig, SoftwareStatus } from "$lib/api/software";
  import {
    listSoftware,
    installSoftware,
    uninstallSoftware,
    getDownloadConfig,
    setDownloadConfig,
  } from "$lib/api/software";

  let software = $state<SoftwareStatus[]>([]);
  let loading = $state(true);
  let installing = $state<string | null>(null);
  let uninstalling = $state<string | null>(null);

  let downloadConfig = $state<DownloadConfig>({
    githubMirror: "https://gh-proxy.com",
    proxyMode: "system",
    proxyUrl: "",
  });
  let configChanged = $state(false);

  async function refresh() {
    loading = true;
    try {
      software = await listSoftware();
      downloadConfig = await getDownloadConfig();
      configChanged = false;
    } finally {
      loading = false;
    }
  }

  async function install(kind: string) {
    installing = kind;
    try {
      await installSoftware(kind);
      await refresh();
    } catch (e) {
      await message(String(e), { title: "安装失败", kind: "error" });
    } finally {
      installing = null;
    }
  }

  async function uninstall(kind: string) {
    uninstalling = kind;
    try {
      await uninstallSoftware(kind);
      await refresh();
    } catch (e) {
      await message(String(e), { title: "卸载失败", kind: "error" });
    } finally {
      uninstalling = null;
    }
  }

  async function saveConfig() {
    try {
      await setDownloadConfig(downloadConfig);
      configChanged = false;
      await message("下载配置已保存。", { title: "已保存", kind: "info" });
    } catch (e) {
      await message(String(e), { title: "保存失败", kind: "error" });
    }
  }

  onMount(refresh);
</script>

<section class="page-scroll">
  <div class="page-header"><PageHeader title="软件管理" description="管理真实检测到的隧道客户端和下载设置；内嵌 MCP/Actions 随桌面应用一起更新。">{#snippet icon()}<Package size={30} />{/snippet}</PageHeader></div>

  <div class="page-body flex flex-col gap-6">
    <SurfaceCard title="本地依赖与隧道组件" description="仅显示后端实际返回的软件。已安装不等于当前运行中。">
      {#snippet icon()}<Boxes size={24} />{/snippet}
      {#if loading}<p role="status">加载中…</p>
      {:else if software.length === 0}<p class="text-sm text-[var(--text-secondary)]">暂无信息。</p>
      {:else}
        <div class="software-table" role="region" aria-label="软件安装状态">
          <table><thead><tr><th scope="col">软件名称</th><th scope="col">安装路径</th><th scope="col">状态</th><th scope="col">来源</th><th scope="col">操作</th></tr></thead>
          <tbody>{#each software as s (s.kind)}<tr>
            <th scope="row">{s.name}</th><td class="path-cell">{s.installed ? s.path : "—"}</td>
            <td><span class:installed={s.installed} class="install-state">{s.installed ? "已安装" : "未安装"}</span></td>
            <td>{s.managed ? "应用管理" : s.installed ? "系统安装" : "—"}</td>
            <td>{#if s.installed}{#if s.managed}<button type="button" class="tx-btn-ghost tx-btn-destructive" disabled={!!uninstalling || !!installing} onclick={() => uninstall(s.kind)}>{uninstalling === s.kind ? "卸载中…" : "卸载"}</button>{:else}<span class="text-xs text-[var(--text-secondary)]">由系统管理</span>{/if}
            {:else}<button type="button" class="tx-btn-primary" disabled={!!installing || !!uninstalling} onclick={() => install(s.kind)}>{installing === s.kind ? "安装中…" : "安装"}</button>{/if}</td>
          </tr>{/each}</tbody></table>
        </div>
      {/if}
    </SurfaceCard>

    <!-- Download config -->
    <SurfaceCard title="下载设置" description="用于下载隧道客户端，不更改工作区服务的代理配置。">
      {#snippet icon()}<Download size={24} />{/snippet}
      <form
        class="mt-4 grid gap-3"
        onsubmit={(e) => { e.preventDefault(); void saveConfig(); }}
      >
        <label class="grid gap-1">
          <span class="text-xs text-[var(--color-text-muted)]">GitHub 镜像</span>
          <input
            type="text"
            class="tx-input tx-mono"
            placeholder="https://gh-proxy.com"
            bind:value={downloadConfig.githubMirror}
            oninput={() => (configChanged = true)}
          />
          <span class="text-xs text-[var(--color-text-muted)]">留空则直连 GitHub，默认使用 gh-proxy.com 加速</span>
        </label>
        <label class="grid gap-1">
          <span class="text-xs text-[var(--color-text-muted)]">代理模式</span>
          <select
            class="tx-select"
            bind:value={downloadConfig.proxyMode}
            onchange={() => (configChanged = true)}
          >
            <option value="system">系统代理（默认）</option>
            <option value="none">无代理</option>
            <option value="manual">手动代理地址</option>
          </select>
        </label>
        {#if downloadConfig.proxyMode === "manual"}
          <label class="grid gap-1">
            <span class="text-xs text-[var(--color-text-muted)]">代理地址</span>
            <input
              type="text"
              class="tx-input tx-mono"
              placeholder="http://127.0.0.1:7890"
              bind:value={downloadConfig.proxyUrl}
              oninput={() => (configChanged = true)}
            />
          </label>
        {/if}
        <div class="flex justify-end pt-1">
          <button
            type="submit"
            class="tx-btn-primary"
            disabled={!configChanged}
          >
            保存设置
          </button>
        </div>
      </form>
    </SurfaceCard>
  </div>
</section>

<style>
  .software-table { max-width:100%; overflow-x:auto; border:1px solid var(--card-border); border-radius:10px; }
  table { width:100%; text-align:left; font-size:13px; border-collapse:collapse; }
  th,td { padding:15px 14px; border-bottom:1px solid var(--card-border); }
  thead { background:var(--field-bg); font-size:12px; }
  tbody tr:last-child th,tbody tr:last-child td { border-bottom:0; }
  .path-cell { font-family:Consolas,monospace; overflow-wrap:anywhere; min-width:160px; max-width:380px; color:var(--text-secondary); }
  .install-state { display:inline-flex; padding:4px 10px; background:var(--field-bg); border-radius:999px; white-space:nowrap; }
  .installed { color:var(--success); background:var(--success-soft); }
</style>
