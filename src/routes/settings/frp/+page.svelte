<script lang="ts">
  import { Server, List, Info } from "@lucide/svelte";
  import PageHeader from "$lib/components/layout/PageHeader.svelte";
  import SurfaceCard from "$lib/components/primitives/SurfaceCard.svelte";
  import { Network } from "@lucide/svelte";
  import { onMount } from "svelte";
  import { message } from "@tauri-apps/plugin-dialog";
  import {
    deleteFrpProfile,
    listFrpProfiles,
    saveFrpProfile,
    type FrpProfileDto,
  } from "$lib/api/settings";
  import SecretInput from "$lib/components/SecretInput.svelte";

  let profiles = $state<FrpProfileDto[]>([]);
  let loading = $state(true);
  let saving = $state(false);
  let editingId = $state<string | null>(null);
  let name = $state("");
  let server = $state("");
  let serverPort = $state(7000);
  let token = $state("");

  async function refresh() {
    loading = true;
    try {
      profiles = await listFrpProfiles();
    } finally {
      loading = false;
    }
  }

  function resetForm() {
    editingId = null;
    name = "";
    server = "";
    serverPort = 7000;
    token = "";
  }

  function editProfile(profile: FrpProfileDto) {
    editingId = profile.id;
    name = profile.name;
    server = profile.server;
    serverPort = profile.serverPort;
    token = "";
  }

  async function save() {
    if (!name.trim() || !server.trim()) {
      await message("请填写配置名称和服务器地址。", { title: "无法保存", kind: "warning" });
      return;
    }
    saving = true;
    try {
      await saveFrpProfile(
        {
          id: editingId ?? "",
          name: name.trim(),
          server: server.trim(),
          serverPort,
        },
        token.trim() || undefined,
      );
      resetForm();
      await refresh();
    } catch (error) {
      await message(String(error), { title: "保存失败", kind: "error" });
    } finally {
      saving = false;
    }
  }

  async function removeProfile(profile: FrpProfileDto) {
    try {
      await deleteFrpProfile(profile.id);
      if (editingId === profile.id) {
        resetForm();
      }
      await refresh();
    } catch (error) {
      await message(String(error), { title: "删除失败", kind: "error" });
    }
  }

  onMount(refresh);
</script>

<section class="page-scroll">
  <div class="page-header"><PageHeader title="FRP 配置" description="管理共享 FRP 服务器配置；工作区内选择配置并设置具体域名和本地映射。">{#snippet icon()}<Network size={30} />{/snippet}</PageHeader></div>

  <div class="page-body frp-grid">
    <SurfaceCard title={editingId ? "编辑服务器配置" : "新建服务器配置"} description="端口与认证令牌须和远端 FRPS 一致。">
      {#snippet icon()}<Server size={24} />{/snippet}
      <form
        class="mt-4 grid gap-3"
        onsubmit={(event) => {
          event.preventDefault();
          void save();
        }}
      >
        <label class="grid gap-1">
          <span class="text-xs text-[var(--color-text-muted)]">名称</span>
          <input
            type="text"
            class="tx-input"
            placeholder="公司 FRP"
            bind:value={name}
          />
        </label>
        <label class="grid gap-1">
          <span class="text-xs text-[var(--color-text-muted)]">服务器域名</span>
          <input
            type="text"
            class="tx-input tx-mono"
            placeholder="frp.example.com"
            bind:value={server}
          />
        </label>
        <label class="grid gap-1">
          <span class="text-xs text-[var(--color-text-muted)]">端口</span>
          <input
            type="number"
            min="1"
            max="65535"
            class="tx-input"
            bind:value={serverPort}
          />
        </label>
        <label class="grid gap-1">
          <span class="text-xs text-[var(--color-text-muted)]">
            Token {editingId ? "（留空则保持不变）" : ""}
          </span>
          <SecretInput
            bind:value={token}
            placeholder="frp auth token"
            showCopy={false}
          />
        </label>
        <div class="flex gap-2 pt-1">
          <button
            type="submit"
            class="tx-btn-primary"
            disabled={saving}
          >
            {saving ? "保存中…" : editingId ? "更新" : "添加"}
          </button>
          {#if editingId}
            <button
              type="button"
              class="tx-btn-ghost"
              onclick={resetForm}
            >
              取消
            </button>
          {/if}
        </div>
      </form>
    </SurfaceCard>

    <aside class="profile-sidebar">
    <SurfaceCard title="已保存的配置" description="这里只表示配置存在，不代表隧道已经连接。">
      {#snippet icon()}<List size={24} />{/snippet}
      {#if loading}
        <p class="mt-4 text-sm text-[var(--color-text-muted)]">加载中…</p>
      {:else if profiles.length === 0}
        <p class="mt-4 text-sm text-[var(--color-text-muted)]">暂无 FRP 配置。</p>
      {:else}
        <ul class="mt-4 space-y-2">
          {#each profiles as profile (profile.id)}
            <li
              class="tx-panel flex items-center justify-between gap-3 px-3 py-2"
            >
              <div class="min-w-0">
                <p class="truncate text-sm font-medium">{profile.name}</p>
                <p class="truncate font-mono text-xs text-[var(--color-text-muted)]">
                  {profile.server}:{profile.serverPort}
                  · Token {profile.hasToken ? "已配置" : "未配置"}
                </p>
              </div>
              <div class="flex shrink-0 gap-2">
                <button
                  type="button"
                  class="tx-btn-ghost"
                  onclick={() => editProfile(profile)}
                >
                  编辑
                </button>
                <button
                  type="button"
                  class="tx-btn-ghost tx-btn-destructive"
                  onclick={() => removeProfile(profile)}
                >
                  删除
                </button>
              </div>
            </li>
          {/each}
        </ul>
      {/if}
    </SurfaceCard>
    <SurfaceCard title="在工作区中连接" description="全局配置与实际运行状态分开管理。">
      {#snippet icon()}<Info size={24} />{/snippet}
      <p class="text-sm text-[var(--text-secondary)]">从左侧选择工作区，在服务的“隧道”配置中关联 FRP。公网 URL、测试连接和配置预览以该工作区的实际状态为准。</p>
    </SurfaceCard>
    </aside>
  </div>
</section>

<style>
  .frp-grid { display:grid; grid-template-columns:minmax(0,1.6fr) minmax(0,1fr); gap:20px; align-items:start; }
  .profile-sidebar { display:grid; gap:18px; min-width:0; }
  li.tx-panel { flex-wrap:wrap; }
  @media(max-width:1200px) { .frp-grid { grid-template-columns:minmax(0,1fr); } }
</style>
