<script lang="ts">
  import { onDestroy } from "svelte";
  import { message } from "@tauri-apps/plugin-dialog";
  import CopyButton from "$lib/components/CopyButton.svelte";
  import SecretInput from "$lib/components/SecretInput.svelte";
  import { latestRequest } from "$lib/runtime/latest-request";
  import { applyAndRefresh } from "$lib/runtime/configuration";
  import { getSecret, regenerateSecret, getSharedSecret, regenerateSharedSecret } from "$lib/api/secrets";
  import type { ActionsAuthDraft } from "$lib/types";

  export const ACTIONS_AUTH_OPTIONS = [
    { value: "api_key", label: "API Key / Bearer" },
    { value: "none", label: "不启用认证" },
    { value: "oauth", label: "OAuth" },
  ] as const;

  export type { ActionsAuthDraft } from "$lib/types";

  interface Props {
    workspaceId: string;
    authType: string;
    oauthClientId: string;
    oauthScopes: string;
    openapiUrl: string;
    privacyUrl: string;
    oauthAuthorizeUrl: string;
    oauthTokenUrl: string;
    useSharedSecrets?: boolean;
    onSave: (draft: ActionsAuthDraft) => void | Promise<void>;
  }

  let {
    workspaceId,
    authType,
    oauthClientId,
    oauthScopes,
    openapiUrl,
    privacyUrl,
    oauthAuthorizeUrl,
    oauthTokenUrl,
    useSharedSecrets = false,
    onSave,
  }: Props = $props();

  let draftAuthType = $state("api_key");
  let draftOauthClientId = $state("");
  let draftOauthScopes = $state("");
  let draftUseShared = $state(false);
  let apiKey = $state("");
  let loadedApiKey = $state("");
  let oauthClientSecret = $state("");
  let loadedOauthClientSecret = $state("");
  let oauthPassword = $state("");
  let loadedOauthPassword = $state("");
  let oauthTokenSecret = $state("");
  let loadedOauthTokenSecret = $state("");
  let loadingKey = $state(true);
  let loadingOAuthSecret = $state(true);
  let loadingOAuthPassword = $state(true);
  let loadingOAuthTokenSecret = $state(true);
  let regenerating = $state(false);
  let regeneratingOAuthSecret = $state(false);
  let regeneratingOAuthPassword = $state(false);
  let regeneratingOAuthTokenSecret = $state(false);
  let saving = $state(false);
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
    clearSecrets();
  });

  const credentialsBusy = $derived(loadingKey || loadingOAuthSecret || loadingOAuthPassword || loadingOAuthTokenSecret ||
    regenerating || regeneratingOAuthSecret || regeneratingOAuthPassword || regeneratingOAuthTokenSecret);
  const dirty = $derived(
    draftAuthType !== authType ||
      draftOauthClientId !== oauthClientId ||
      draftOauthScopes !== oauthScopes ||
      draftUseShared !== useSharedSecrets,
  );
  const showApiKey = $derived(draftAuthType === "api_key");
  const showOAuth = $derived(draftAuthType === "oauth");

  $effect(() => {
    draftAuthType = authType;
    draftOauthClientId = oauthClientId;
    draftOauthScopes = oauthScopes;
    draftUseShared = useSharedSecrets;
  });

  $effect(() => {
    if (suppressSecretsReload) return;
    const id = workspaceId, useShared = draftUseShared;
    void loadSecrets(id, useShared);
    return () => secretRequests.invalidate();
  });

  $effect(() => {
    const next = `${workspaceId}\u0000${draftUseShared}`;
    if (operationContextKey && operationContextKey !== next) {
      operationRequests.invalidate();
      saving = false;
      regenerating = regeneratingOAuthSecret = regeneratingOAuthPassword = regeneratingOAuthTokenSecret = false;
      suppressSecretsReload = false;
    }
    operationContextKey = next;
  });

  function currentContext(id: string, useShared: boolean) {
    return !disposed && id === workspaceId && useShared === draftUseShared;
  }

  function clearSecrets() {
    apiKey = loadedApiKey = "";
    oauthClientSecret = loadedOauthClientSecret = "";
    oauthPassword = loadedOauthPassword = "";
    oauthTokenSecret = loadedOauthTokenSecret = "";
  }

  async function loadSecrets(id: string, useShared: boolean) {
    const ticket = secretRequests.begin();
    clearSecrets();
    secretsError = "";
    loadingKey = loadingOAuthSecret = loadingOAuthPassword = loadingOAuthTokenSecret = true;
    try {
      const read = (sharedKey: Parameters<typeof getSharedSecret>[0], workspaceKey: Parameters<typeof getSecret>[1]) =>
        useShared ? getSharedSecret(sharedKey) : getSecret(id, workspaceKey);
      const [key, secret, password, tokenSecret] = await Promise.all([
        read("actions_api_key", "actions_api_key"),
        read("actions_oauth_client_secret", "actions_oauth_client_secret"),
        read("actions_oauth_password", "actions_oauth_password"),
        read("actions_oauth_token_secret", "actions_oauth_token_secret"),
      ]);
      if (!secretRequests.current(ticket) || !currentContext(id, useShared)) return;
      apiKey = loadedApiKey = key ?? "";
      oauthClientSecret = loadedOauthClientSecret = secret ?? "";
      oauthPassword = loadedOauthPassword = password ?? "";
      oauthTokenSecret = loadedOauthTokenSecret = tokenSecret ?? "";
    } catch {
      if (secretRequests.current(ticket) && currentContext(id, useShared)) {
        clearSecrets();
        secretsError = "凭据读取失败；旧值已清空。请重试后再保存或重新生成。";
      }
    } finally {
      if (secretRequests.current(ticket) && currentContext(id, useShared)) {
        loadingKey = loadingOAuthSecret = loadingOAuthPassword = loadingOAuthTokenSecret = false;
      }
    }
  }

  async function save() {
    if (saving || !dirty || credentialsBusy || secretsError) return;
    const ticket = operationRequests.begin();
    const id = workspaceId, useShared = draftUseShared;
    saving = true;
    suppressSecretsReload = true;
    try {
      const next = {
        authType: draftAuthType, oauthClientId: draftOauthClientId.trim(),
        oauthScopes: draftOauthScopes.trim(), useSharedSecrets: draftUseShared,
      };
      await applyAndRefresh(async () => { await onSave(next); }, async () => {
        if (operationRequests.current(ticket) && currentContext(id, useShared)) await loadSecrets(id, useShared);
      });
    } catch (error) {
      if (operationRequests.current(ticket) && currentContext(id, useShared)) {
        await message(String(error), { title: "保存失败", kind: "error" });
      }
    } finally {
      if (operationRequests.current(ticket)) {
        suppressSecretsReload = false;
        saving = false;
      }
    }
  }

  async function regenerateCredential(
    kind: "api" | "secret" | "password" | "token",
    sharedKey: Parameters<typeof regenerateSharedSecret>[0],
    workspaceKey: Parameters<typeof regenerateSecret>[1],
  ) {
    if (saving || credentialsBusy || secretsError) return;
    const ticket = operationRequests.begin();
    const id = workspaceId, useShared = draftUseShared;
    secretRequests.invalidate();
    if (kind === "api") regenerating = true;
    else if (kind === "secret") regeneratingOAuthSecret = true;
    else if (kind === "password") regeneratingOAuthPassword = true;
    else regeneratingOAuthTokenSecret = true;
    clearSecrets();
    try {
      // Never retain the old credential when persistence succeeds but restart fails.
      await applyAndRefresh(async () => {
        if (useShared) await regenerateSharedSecret(sharedKey);
        else await regenerateSecret(id, workspaceKey);
      }, async () => {
        if (operationRequests.current(ticket) && currentContext(id, useShared)) await loadSecrets(id, useShared);
      });
    } catch (error) {
      if (operationRequests.current(ticket) && currentContext(id, useShared)) {
        await message(String(error), { title: "重新生成失败", kind: "error" });
      }
    } finally {
      if (operationRequests.current(ticket)) {
        if (kind === "api") regenerating = false;
        else if (kind === "secret") regeneratingOAuthSecret = false;
        else if (kind === "password") regeneratingOAuthPassword = false;
        else regeneratingOAuthTokenSecret = false;
      }
    }
  }

  const regenerate = () => regenerateCredential("api", "actions_api_key", "actions_api_key");
  const regenerateOAuthSecret = () => regenerateCredential("secret", "actions_oauth_client_secret", "actions_oauth_client_secret");
  const regenerateOAuthPassword = () => regenerateCredential("password", "actions_oauth_password", "actions_oauth_password");
  const regenerateOAuthTokenSecret = () => regenerateCredential("token", "actions_oauth_token_secret", "actions_oauth_token_secret");
</script>

<form
  class="grid gap-3"
  onsubmit={(event) => {
    event.preventDefault();
    void save();
  }}
>
  <p class="text-xs text-[var(--color-text-muted)]">
    复制 OpenAPI、密钥等请用上方「GPT 配置」卡片；此处仅修改认证方式与密钥。
  </p>

  {#if secretsError}
    <div class="grid gap-2 rounded-md border border-red-300/50 p-3 text-xs text-red-600">
      <span>{secretsError}</span>
      <button type="button" class="tx-btn-ghost justify-self-start" onclick={() => void loadSecrets(workspaceId, draftUseShared)}>重新读取凭据</button>
    </div>
  {/if}

  <label class="grid gap-1">
    <span class="text-xs text-[var(--color-text-muted)]">认证方式</span>
    <select
      class="rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] px-2.5 py-1.5 text-sm"
      bind:value={draftAuthType}
    >
      {#each ACTIONS_AUTH_OPTIONS as option}
        <option value={option.value}>{option.label}</option>
      {/each}
    </select>
  </label>

  <label class="flex items-center gap-2">
    <input
      type="checkbox"
      class="h-4 w-4"
      bind:checked={draftUseShared}
    />
    <span class="text-xs text-[var(--color-text-muted)]">使用全局共享密钥（在「设置 → 共享密钥」中管理）</span>
  </label>

  {#if showApiKey}
    <label class="grid gap-1">
      <span class="text-xs text-[var(--color-text-muted)]">API Key（Bearer）</span>
      <SecretInput
        value={loadingKey ? "加载中…" : apiKey}
        readonly
        disabled={credentialsBusy || !!secretsError || saving}
        showCopy={!!apiKey}
        onRegenerate={() => void regenerate()}
        regenerating={regenerating}
      />
    </label>
    <p class="text-xs text-[var(--color-text-muted)]">
      在 GPT Actions 认证里选 API Key → Bearer，Key 填这里的值。
    </p>
  {:else if showOAuth}
    <label class="grid gap-1">
      <span class="text-xs text-[var(--color-text-muted)]">OAuth Client ID（填到 GPT）</span>
      <div class="flex gap-2">
        <input
          type="text"
          class="min-w-0 flex-1 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] px-2.5 py-1.5 font-mono text-sm"
          bind:value={draftOauthClientId}
        />
        {#if draftOauthClientId}
          <CopyButton value={draftOauthClientId} label="复制" />
        {/if}
      </div>
    </label>
    <label class="grid gap-1">
      <span class="text-xs text-[var(--color-text-muted)]">OAuth Client Secret（填到 GPT）</span>
      <SecretInput
        value={loadingOAuthSecret ? "加载中…" : oauthClientSecret}
        readonly
        disabled={credentialsBusy || !!secretsError || saving}
        showCopy={!!oauthClientSecret}
        onRegenerate={() => void regenerateOAuthSecret()}
        regenerating={regeneratingOAuthSecret}
      />
    </label>
    <label class="grid gap-1">
      <span class="text-xs text-[var(--color-text-muted)]">OAuth Password（服务端校验）</span>
      <SecretInput
        value={loadingOAuthPassword ? "加载中…" : oauthPassword}
        readonly
        disabled={credentialsBusy || !!secretsError || saving}
        showCopy={!!oauthPassword}
        onRegenerate={() => void regenerateOAuthPassword()}
        regenerating={regeneratingOAuthPassword}
      />
    </label>
    <label class="grid gap-1">
      <span class="text-xs text-[var(--color-text-muted)]">OAuth Token Secret（JWT 签名）</span>
      <SecretInput
        value={loadingOAuthTokenSecret ? "加载中…" : oauthTokenSecret}
        readonly
        disabled={credentialsBusy || !!secretsError || saving}
        showCopy={!!oauthTokenSecret}
        onRegenerate={() => void regenerateOAuthTokenSecret()}
        regenerating={regeneratingOAuthTokenSecret}
      />
    </label>
    <label class="grid gap-1">
      <span class="text-xs text-[var(--color-text-muted)]">Authorization URL（填到 GPT）</span>
      <div class="flex gap-2">
        <input
          type="text"
          readonly
          class="min-w-0 flex-1 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] px-2.5 py-1.5 font-mono text-xs"
          value={oauthAuthorizeUrl}
        />
        {#if oauthAuthorizeUrl}
          <CopyButton value={oauthAuthorizeUrl} label="复制" />
        {/if}
      </div>
    </label>
    <label class="grid gap-1">
      <span class="text-xs text-[var(--color-text-muted)]">Token URL（填到 GPT）</span>
      <div class="flex gap-2">
        <input
          type="text"
          readonly
          class="min-w-0 flex-1 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] px-2.5 py-1.5 font-mono text-xs"
          value={oauthTokenUrl}
        />
        {#if oauthTokenUrl}
          <CopyButton value={oauthTokenUrl} label="复制" />
        {/if}
      </div>
    </label>
    <label class="grid gap-1">
      <span class="text-xs text-[var(--color-text-muted)]">Scope（填到 GPT，空格分隔）</span>
      <input
        type="text"
        class="rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] px-2.5 py-1.5 text-sm"
        placeholder="例如：coding-tools"
        bind:value={draftOauthScopes}
      />
    </label>
    <p class="text-xs text-[var(--color-text-muted)]">
      GPT 编辑器会生成 Callback URL（<code>https://chatgpt.com/aip/g-…/oauth/callback</code>），无需在本应用配置。Token
      交换方式选默认即可。
    </p>
  {:else}
    <p class="text-xs text-[var(--color-text-muted)]">
      不校验请求认证；GPT 侧选 None。仅建议本机调试，公网暴露请用 API Key 或 OAuth。
    </p>
  {/if}

  <div class="flex justify-end pt-1">
    <button
      type="submit"
      class="rounded-md bg-[var(--color-accent)] px-3 py-1.5 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
      disabled={saving || !dirty || credentialsBusy || !!secretsError}
    >
      {saving ? "保存中…" : "保存配置"}
    </button>
  </div>
</form>
