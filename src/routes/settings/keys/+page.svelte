<script lang="ts">
  import { Shield, Zap, AlertTriangle } from "@lucide/svelte";
  import PageHeader from "$lib/components/layout/PageHeader.svelte";
  import SurfaceCard from "$lib/components/primitives/SurfaceCard.svelte";
  import { KeyRound } from "@lucide/svelte";
  import { onMount, onDestroy } from "svelte";
  import { message } from "@tauri-apps/plugin-dialog";
  import SecretInput from "$lib/components/SecretInput.svelte";
  import { latestRequest } from "$lib/runtime/latest-request";
  import {
    getSharedSecret,
    setSharedSecret,
    regenerateSharedSecret,
    type SharedSecretKey,
  } from "$lib/api/secrets";

  const MCP_KEYS: { key: SharedSecretKey; label: string }[] = [
    { key: "oauth_client_id", label: "MCP OAuth Client ID" },
    { key: "bearer_token", label: "MCP Bearer Token" },
    { key: "oauth_client_secret", label: "MCP OAuth 客户端密钥" },
    { key: "oauth_password", label: "MCP 授权口令" },
    { key: "oauth_token_secret", label: "MCP Token Secret" },
  ];

  const ACTIONS_KEYS: { key: SharedSecretKey; label: string }[] = [
    { key: "actions_api_key", label: "Actions API Key" },
    { key: "actions_oauth_client_secret", label: "Actions OAuth 客户端密钥" },
    { key: "actions_oauth_password", label: "Actions 授权口令" },
    { key: "actions_oauth_token_secret", label: "Actions Token Secret" },
  ];

  const ALL_KEYS = [...MCP_KEYS, ...ACTIONS_KEYS];

  let secrets = $state<Record<string, string>>({});
  let originals = $state<Record<string, string>>({});
  let loadErrors = $state<Record<string, boolean>>({});
  let loading = $state(true);
  let saving = $state(false);
  let regenerating = $state<string | null>(null);
  let disposed = false;
  const loadRequests = latestRequest();
  const mutationRequests = latestRequest();
  onDestroy(() => {
    disposed = true;
    loadRequests.invalidate();
    mutationRequests.invalidate();
    secrets = {}; originals = {};
  });

  const dirty = $derived(ALL_KEYS.some(({ key }) => !loadErrors[key] && secrets[key] !== undefined && secrets[key] !== originals[key]));
  const hasLoadErrors = $derived(Object.values(loadErrors).some(Boolean));

  async function loadAll() {
    if (saving || regenerating) return;
    const ticket = loadRequests.begin();
    secrets = {}; originals = {}; loadErrors = {}; loading = true;
    try {
      const results = await Promise.all(ALL_KEYS.map(async ({ key }) => {
        try { return { key, ok: true as const, value: (await getSharedSecret(key)) ?? "" }; }
        catch { return { key, ok: false as const, value: "" }; }
      }));
      if (disposed || !loadRequests.current(ticket)) return;
      const nextSecrets: Record<string, string> = {};
      const nextOriginals: Record<string, string> = {};
      const nextErrors: Record<string, boolean> = {};
      for (const result of results) {
        if (result.ok) nextSecrets[result.key] = nextOriginals[result.key] = result.value;
        else nextErrors[result.key] = true;
      }
      secrets = nextSecrets; originals = nextOriginals; loadErrors = nextErrors;
    } finally {
      if (!disposed && loadRequests.current(ticket)) loading = false;
    }
  }

  async function regenerate(key: SharedSecretKey) {
    if (regenerating || saving || loading || loadErrors[key]) return;
    const ticket = mutationRequests.begin();
    regenerating = key;
    secrets = { ...secrets, [key]: "" };
    try {
      const value = await regenerateSharedSecret(key);
      if (!disposed && mutationRequests.current(ticket)) {
        // Regeneration is already persisted and applied by the backend.
        secrets = { ...secrets, [key]: value };
        originals = { ...originals, [key]: value };
        const nextErrors = { ...loadErrors }; delete nextErrors[key]; loadErrors = nextErrors;
      }
    } catch (e) {
      // The backend may have persisted the new value before service application failed.
      await reloadKey(key, ticket);
      if (!disposed && mutationRequests.current(ticket)) await message(String(e), { title: "重新生成失败", kind: "error" });
    } finally {
      if (!disposed && mutationRequests.current(ticket)) regenerating = null;
    }
  }

  async function reloadKey(key: SharedSecretKey, ticket: number) {
    if (disposed || !mutationRequests.current(ticket)) return;
    secrets = { ...secrets, [key]: "" };
    originals = { ...originals, [key]: "" };
    try {
      const value = (await getSharedSecret(key)) ?? "";
      if (disposed || !mutationRequests.current(ticket)) return;
      secrets = { ...secrets, [key]: value };
      originals = { ...originals, [key]: value };
      const nextErrors = { ...loadErrors }; delete nextErrors[key]; loadErrors = nextErrors;
    } catch {
      if (!disposed && mutationRequests.current(ticket)) loadErrors = { ...loadErrors, [key]: true };
    }
  }

  async function saveAll() {
    if (saving || loading || regenerating || hasLoadErrors || !dirty) return;
    const ticket = mutationRequests.begin();
    saving = true;
    const changes = ALL_KEYS
      .filter(({ key }) => !loadErrors[key] && secrets[key] !== undefined && secrets[key] !== originals[key])
      .map(({ key }) => ({ key, value: secrets[key] }));
    try {
      for (const { key, value } of changes) {
        if (!mutationRequests.current(ticket) || disposed) throw new Error("页面状态已变化，请重新保存。");
        try {
          await setSharedSecret(key, value);
        } catch (error) {
          // Reconcile only this key. Other unsaved drafts must survive a partial failure.
          await reloadKey(key, ticket);
          throw error;
        }
        if (mutationRequests.current(ticket) && !disposed) originals = { ...originals, [key]: value };
      }
    } catch (e) {
      if (!disposed && mutationRequests.current(ticket)) await message(String(e), { title: "保存失败", kind: "error" });
    } finally {
      if (!disposed && mutationRequests.current(ticket)) saving = false;
    }
  }

  onMount(loadAll);
</script>

<section class="page-scroll">
  <div class="page-header"><PageHeader title="共享密钥" description="全局凭据管理。工作区可独立选择共享或私有密钥；OAuth 连接不替代本机聊天审批。">{#snippet icon()}<KeyRound size={30} />{/snippet}</PageHeader></div>

  <div class="page-body flex flex-col gap-6">
    {#if hasLoadErrors}
      <div class="grid gap-2 rounded-md border border-red-300/50 p-3 text-sm text-red-600">
        <span>部分共享密钥读取失败。失败项已锁定且不会显示为空值，也不会被保存覆盖。</span>
        <button type="button" class="tx-btn-ghost justify-self-start" onclick={() => void loadAll()}>重新读取全部密钥</button>
      </div>
    {/if}
    <div class="flex flex-col gap-6">
      <!-- MCP keys -->
      <SurfaceCard title="MCP 认证密钥" description="客户端身份、授权口令、签名密钥各自独立，不应互换。">
        {#snippet icon()}<Shield size={24} />{/snippet}
        {#if loading}
          <p class="mt-4 text-sm text-[var(--color-text-muted)]">加载中…</p>
        {:else}
          <div class="mt-4 grid gap-4">
            {#each MCP_KEYS as { key, label }}
              <div class="credential-row">
                <span class="text-xs text-[var(--color-text-muted)]">{label}</span>
                {#if loadErrors[key]}
                  <!-- A failed read has no value. Do not bind undefined into a
                       $bindable fallback or treat failure as an editable empty key. -->
                  <SecretInput label={label} value="" disabled showCopy={false} placeholder="读取失败，禁止编辑/复制。" />
                {:else}
                  <SecretInput
                    label={label}
                    bind:value={secrets[key]}
                    disabled={loading || saving || !!regenerating}
                    onRegenerate={() => regenerate(key)}
                    regenerating={regenerating === key}
                  />
                {/if}
                {#if loadErrors[key]}<span class="text-xs text-red-600">读取失败，禁止编辑/复制。</span>{/if}
              </div>
            {/each}
          </div>
        {/if}
      </SurfaceCard>

      <!-- Actions keys -->
      <SurfaceCard title="Actions 认证密钥" description="仅用于 Actions 网关，不代表 MCP 聊天授权。">
        {#snippet icon()}<Zap size={24} />{/snippet}
        {#if loading}
          <p class="mt-4 text-sm text-[var(--color-text-muted)]">加载中…</p>
        {:else}
          <div class="mt-4 grid gap-4">
            {#each ACTIONS_KEYS as { key, label }}
              <div class="credential-row">
                <span class="text-xs text-[var(--color-text-muted)]">{label}</span>
                {#if loadErrors[key]}
                  <!-- A failed read has no value. Do not bind undefined into a
                       $bindable fallback or treat failure as an editable empty key. -->
                  <SecretInput label={label} value="" disabled showCopy={false} placeholder="读取失败，禁止编辑/复制。" />
                {:else}
                  <SecretInput
                    label={label}
                    bind:value={secrets[key]}
                    disabled={loading || saving || !!regenerating}
                    onRegenerate={() => regenerate(key)}
                    regenerating={regenerating === key}
                  />
                {/if}
                {#if loadErrors[key]}<span class="text-xs text-red-600">读取失败，禁止编辑/复制。</span>{/if}
              </div>
            {/each}
          </div>
        {/if}
      </SurfaceCard>
    </div>

    <div class="key-notice"><AlertTriangle size={20} aria-hidden="true" /><p>修改共享凭据会影响使用它们的工作区，并可能重启对应服务。不要把密钥、授权口令发送到聊天或截图中。</p></div>
    <div class="flex justify-end">
      <button
        type="button"
        class="tx-btn-primary"
        disabled={!dirty || saving || loading || !!regenerating || hasLoadErrors}
        onclick={() => saveAll()}
      >
        {saving ? "保存中…" : "保存更改"}
      </button>
    </div>
  </div>
</section>

<style>
  .credential-row { display:grid; grid-template-columns:minmax(180px,.7fr) minmax(0,1.3fr); align-items:center; gap:12px; padding:12px; border:1px solid var(--card-border); border-radius:10px; }
  .credential-row>span:first-child { font-size:13px; color:var(--text-main); font-weight:600; }
  .key-notice { display:flex; gap:12px; align-items:flex-start; background:var(--warning-soft); color:var(--warning); border-radius:12px; padding:16px; font-size:13px; }
  .key-notice :global(svg) { flex-shrink:0; }
  @media(max-width:1100px) { .credential-row { grid-template-columns:minmax(0,1fr); } }
</style>
