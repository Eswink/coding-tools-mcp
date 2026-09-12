<script lang="ts">
  import { onDestroy } from "svelte";
  import { message } from "@tauri-apps/plugin-dialog";
  import SecretInput from "$lib/components/SecretInput.svelte";
  import { latestRequest } from "$lib/runtime/latest-request";
  import {
    getWorkspaceSecret,
    regenerateWorkspaceSecret,
    getSharedSecret,
    regenerateSharedSecret,
    type WorkspaceSecretKey,
    type SharedSecretKey,
  } from "$lib/api/secrets";
  import type { AuthConfig } from "$lib/types";

  interface Props {
    workspaceId: string;
    auth: AuthConfig;
    onSaveProfile: (auth: AuthConfig) => void | Promise<void>;
  }

  const AUTH_OPTIONS = [
    { value: "oauth", label: "OAuth" },
    { value: "bearer", label: "Bearer Token" },
    { value: "noauth", label: "不启用认证" },
  ] as const;

  let { workspaceId, auth, onSaveProfile }: Props = $props();

  let draft = $state<AuthConfig>({ type: "oauth", oauth_client_id: "", use_shared_secrets: false });
  let saving = $state(false);
  let secrets = $state<Partial<Record<WorkspaceSecretKey, string>>>({});
  let loadedSharedOauthClientId = $state("");
  let regenerating = $state<WorkspaceSecretKey | null>(null);
  let loadingSecrets = $state(true);
  let secretsError = $state("");
  let suppressSecretsReload = $state(false);
  let disposed = false;
  const secretRequests = latestRequest();
  const operationRequests = latestRequest();
  let operationContextKey = "";
  onDestroy(() => {
    disposed = true;
    secretRequests.invalidate();
    operationRequests.invalidate();
    secrets = {};
  });

  const dirty = $derived(
    draft.type !== auth.type ||
      (!draft.use_shared_secrets && draft.oauth_client_id !== auth.oauth_client_id) ||
      draft.use_shared_secrets !== !!auth.use_shared_secrets ||
      (draft.oauth_redirect_uri ?? "") !== (auth.oauth_redirect_uri ?? "https://chatgpt.com/connector_platform_oauth_redirect"),
  );

  const showOAuth = $derived(draft.type === "oauth");
  const showBearer = $derived(draft.type === "bearer");

  $effect(() => {
    draft = { type: auth.type, oauth_client_id: auth.oauth_client_id, use_shared_secrets: !!auth.use_shared_secrets, oauth_redirect_uri: auth.oauth_redirect_uri ?? "https://chatgpt.com/connector_platform_oauth_redirect" };
  });

  $effect(() => {
    if (suppressSecretsReload) return;
    const id = workspaceId;
    const authType = draft.type;
    const useShared = draft.use_shared_secrets ?? false;
    void loadSecrets(id, authType, useShared);
    return () => secretRequests.invalidate();
  });

  $effect(() => {
    const next = `${workspaceId}\u0000${draft.type}\u0000${!!draft.use_shared_secrets}`;
    if (operationContextKey && operationContextKey !== next) {
      operationRequests.invalidate();
      saving = false;
      regenerating = null;
      suppressSecretsReload = false;
    }
    operationContextKey = next;
  });

  function currentContext(id: string, authType: string, useShared: boolean) {
    return !disposed && id === workspaceId && authType === draft.type && useShared === !!draft.use_shared_secrets;
  }

  async function loadSecrets(id: string, authType: string, useShared: boolean) {
    const ticket = secretRequests.begin();
    secrets = {};
    loadedSharedOauthClientId = "";
    secretsError = "";
    loadingSecrets = true;
    try {
      const sharedClientId =
        authType === "oauth" && useShared ? await getSharedSecret("oauth_client_id") : null;
      const keys: WorkspaceSecretKey[] = [];
      if (authType === "oauth") keys.push("oauth_client_secret", "oauth_password");
      else if (authType === "bearer") keys.push("bearer_token");
      const loaded = await Promise.all(keys.map(async (key) => {
        const value = useShared
          ? await getSharedSecret(key as SharedSecretKey)
          : await getWorkspaceSecret(id, key);
        return [key, value ?? ""] as const;
      }));
      if (!secretRequests.current(ticket) || !currentContext(id, authType, useShared)) return;
      if (authType === "oauth") {
        const clientId = useShared ? sharedClientId ?? "" : auth.oauth_client_id;
        draft = { ...draft, oauth_client_id: clientId };
        loadedSharedOauthClientId = useShared ? clientId : "";
      }
      secrets = Object.fromEntries(loaded);
    } catch {
      if (secretRequests.current(ticket) && currentContext(id, authType, useShared)) {
        secrets = {};
        loadedSharedOauthClientId = "";
        secretsError = "凭据读取失败；旧值已清空。请重试后再保存或重新生成。";
      }
    } finally {
      if (secretRequests.current(ticket) && currentContext(id, authType, useShared)) loadingSecrets = false;
    }
  }

  async function save() {
    if (saving || !dirty || loadingSecrets || secretsError || regenerating) return;
    const ticket = operationRequests.begin();
    const id = workspaceId;
    const authType = draft.type;
    const useShared = !!draft.use_shared_secrets;
    saving = true;
    suppressSecretsReload = true;
    try {
      if (authType === "oauth" && useShared && !loadedSharedOauthClientId) {
        throw new Error("全局 OAuth Client ID 尚未配置或读取失败，请先在“设置 → 共享密钥”中配置。" );
      }
      const next = {
        ...draft,
        // Shared client identity belongs to the shared secret store, not this workspace profile.
        oauth_client_id: useShared ? auth.oauth_client_id : draft.oauth_client_id.trim(),
      };
      await onSaveProfile(next);
      if (operationRequests.current(ticket) && currentContext(id, authType, useShared)) {
        await loadSecrets(id, next.type, !!next.use_shared_secrets);
      }
    } catch (error) {
      if (operationRequests.current(ticket) && currentContext(id, authType, useShared)) {
        await message(String(error), { title: "保存失败", kind: "error" });
      }
    } finally {
      if (operationRequests.current(ticket)) {
        suppressSecretsReload = false;
        saving = false;
      }
    }
  }

  async function regenerate(key: WorkspaceSecretKey) {
    if (regenerating || saving || loadingSecrets || secretsError) return;
    const ticket = operationRequests.begin();
    const id = workspaceId;
    const authType = draft.type;
    const useShared = !!draft.use_shared_secrets;
    secretRequests.invalidate();
    regenerating = key;
    try {
      if (useShared) await regenerateSharedSecret(key as SharedSecretKey);
      else await regenerateWorkspaceSecret(id, key);
      if (operationRequests.current(ticket) && currentContext(id, authType, useShared)) {
        await loadSecrets(id, authType, useShared);
      }
    } catch (error) {
      if (operationRequests.current(ticket) && currentContext(id, authType, useShared)) {
        await message(String(error), { title: "重新生成失败", kind: "error" });
      }
    } finally {
      if (operationRequests.current(ticket)) regenerating = null;
    }
  }
</script>

<form
  class="grid gap-3"
  onsubmit={(event) => {
    event.preventDefault();
    void save();
  }}
>
  <p class="text-xs text-[var(--color-text-muted)]">
    复制 Client ID / 密钥等请用上方「GPT 配置」卡片；此处可修改认证类型与重新生成密钥。
  </p>

  {#if secretsError}
    <div class="grid gap-2 rounded-md border border-red-300/50 p-3 text-xs text-red-600">
      <span>{secretsError}</span>
      <button type="button" class="tx-btn-ghost justify-self-start" onclick={() => void loadSecrets(workspaceId, draft.type, !!draft.use_shared_secrets)}>重新读取凭据</button>
    </div>
  {/if}

  <label class="grid gap-1">
    <span class="text-xs text-[var(--color-text-muted)]">认证类型</span>
    <select
      class="rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] px-2.5 py-1.5 text-sm"
      bind:value={draft.type}
    >
      {#each AUTH_OPTIONS as option}
        <option value={option.value}>{option.label}</option>
      {/each}
    </select>
  </label>

  <label class="flex items-center gap-2">
    <input
      type="checkbox"
      class="h-4 w-4"
      bind:checked={draft.use_shared_secrets}
    />
    <span class="text-xs text-[var(--color-text-muted)]">使用全局共享密钥（在「设置 → 共享密钥」中管理）</span>
  </label>

  {#if showOAuth}
    <label class="grid gap-1">
      <span class="text-xs text-[var(--color-text-muted)]">OAuth 精确回调地址（复制 ChatGPT 配置页显示的完整地址）</span>
      <input type="url" class="rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] px-2.5 py-1.5 font-mono text-sm" bind:value={draft.oauth_redirect_uri} required />
    </label>
    <label class="grid gap-1">
      <span class="text-xs text-[var(--color-text-muted)]">OAuth 客户端 ID</span>
      <input
        type="text"
        class="rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] px-2.5 py-1.5 font-mono text-sm"
        bind:value={draft.oauth_client_id}
        readonly={draft.use_shared_secrets}
      />
    </label>

    <div class="grid gap-1">
      <span class="text-xs text-[var(--color-text-muted)]">OAuth 客户端密钥</span>
      <SecretInput
        value={secrets.oauth_client_secret ?? ""}
        placeholder="加载中…"
        readonly
        disabled={loadingSecrets || !!secretsError || saving}
        onRegenerate={() => void regenerate("oauth_client_secret")}
        regenerating={regenerating === "oauth_client_secret"}
      />
    </div>

    <div class="grid gap-1">
      <span class="text-xs text-[var(--color-text-muted)]">授权口令</span>
      <SecretInput
        value={secrets.oauth_password ?? ""}
        placeholder="ChatGPT 首次授权时输入这个口令"
        readonly
        disabled={loadingSecrets || !!secretsError || saving}
        onRegenerate={() => void regenerate("oauth_password")}
        regenerating={regenerating === "oauth_password"}
      />
    </div>
  {/if}

  {#if showBearer}
    <div class="grid gap-1">
      <span class="text-xs text-[var(--color-text-muted)]">Bearer Token</span>
      <SecretInput
        value={secrets.bearer_token ?? ""}
        placeholder="加载中…"
        readonly
        disabled={loadingSecrets || !!secretsError || saving}
        onRegenerate={() => void regenerate("bearer_token")}
        regenerating={regenerating === "bearer_token"}
      />
    </div>
  {/if}

  <div class="flex justify-end pt-1">
    <button
      type="submit"
      class="rounded-md bg-[var(--color-accent)] px-3 py-1.5 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
      disabled={saving || !dirty || loadingSecrets || !!secretsError || !!regenerating}
    >
      {saving ? "保存中…" : "保存配置"}
    </button>
  </div>
</form>
