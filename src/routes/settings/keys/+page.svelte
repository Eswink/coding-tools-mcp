<script lang="ts">
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
    try {
      const value = await regenerateSharedSecret(key);
      if (!disposed && mutationRequests.current(ticket)) {
        // Regeneration is already persisted and applied by the backend.
        secrets = { ...secrets, [key]: value };
        originals = { ...originals, [key]: value };
        const nextErrors = { ...loadErrors }; delete nextErrors[key]; loadErrors = nextErrors;
      }
    } catch (e) {
      if (!disposed && mutationRequests.current(ticket)) await message(String(e), { title: "重新生成失败", kind: "error" });
    } finally {
      if (!disposed && mutationRequests.current(ticket)) regenerating = null;
    }
  }

  async function saveAll() {
    if (saving || loading || regenerating || hasLoadErrors || !dirty) return;
    const ticket = mutationRequests.begin();
    saving = true;
    try {
      for (const { key } of ALL_KEYS) {
        if (!mutationRequests.current(ticket) || disposed) throw new Error("页面状态已变化，请重新保存。");
        if (!loadErrors[key] && secrets[key] !== undefined && secrets[key] !== originals[key]) {
          await setSharedSecret(key, secrets[key]);
          if (mutationRequests.current(ticket) && !disposed) originals = { ...originals, [key]: secrets[key] };
        }
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
  <header class="page-header">
    <p class="page-kicker">全局设置</p>
    <h2 class="page-title">共享密钥</h2>
    <p class="mt-2 max-w-2xl text-sm text-[var(--color-text-muted)]">
      在此统一管理所有共享密钥。各工作区可以选择使用共享密钥或自己的密钥，这样 GPT 只需配置一次
      Bearer/API Key，即可访问所有工作区。重新生成或修改密钥后，正在运行的对应服务将自动重启以生效。
    </p>
  </header>

  <div class="page-body flex flex-col gap-6">
    {#if hasLoadErrors}
      <div class="grid gap-2 rounded-md border border-red-300/50 p-3 text-sm text-red-600">
        <span>部分共享密钥读取失败。失败项已锁定且不会显示为空值，也不会被保存覆盖。</span>
        <button type="button" class="tx-btn-ghost justify-self-start" onclick={() => void loadAll()}>重新读取全部密钥</button>
      </div>
    {/if}
    <div class="flex flex-col gap-6">
      <!-- MCP keys -->
      <div class="tx-card p-4">
        <h3 class="text-sm font-semibold">MCP 认证密钥</h3>
        {#if loading}
          <p class="mt-4 text-sm text-[var(--color-text-muted)]">加载中…</p>
        {:else}
          <div class="mt-4 grid gap-4">
            {#each MCP_KEYS as { key, label }}
              <div class="grid gap-1">
                <span class="text-xs text-[var(--color-text-muted)]">{label}</span>
                <SecretInput
                  bind:value={secrets[key]}
                  disabled={loading || !!loadErrors[key] || saving}
                  onRegenerate={() => regenerate(key)}
                  regenerating={regenerating === key}
                />
                {#if loadErrors[key]}<span class="text-xs text-red-600">读取失败，禁止编辑/复制。</span>{/if}
              </div>
            {/each}
          </div>
        {/if}
      </div>

      <!-- Actions keys -->
      <div class="tx-card p-4">
        <h3 class="text-sm font-semibold">Actions 认证密钥</h3>
        {#if loading}
          <p class="mt-4 text-sm text-[var(--color-text-muted)]">加载中…</p>
        {:else}
          <div class="mt-4 grid gap-4">
            {#each ACTIONS_KEYS as { key, label }}
              <div class="grid gap-1">
                <span class="text-xs text-[var(--color-text-muted)]">{label}</span>
                <SecretInput
                  bind:value={secrets[key]}
                  disabled={loading || !!loadErrors[key] || saving}
                  onRegenerate={() => regenerate(key)}
                  regenerating={regenerating === key}
                />
                {#if loadErrors[key]}<span class="text-xs text-red-600">读取失败，禁止编辑/复制。</span>{/if}
              </div>
            {/each}
          </div>
        {/if}
      </div>
    </div>

    <div class="flex justify-end">
      <button
        type="button"
        class="rounded-md bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
        disabled={!dirty || saving || loading || !!regenerating || hasLoadErrors}
        onclick={() => saveAll()}
      >
        {saving ? "保存中…" : "保存更改"}
      </button>
    </div>
  </div>
</section>
