<script lang="ts">
  import { configurationState } from "$lib/runtime/configuration";
  import CopyFieldRow from "$lib/components/CopyFieldRow.svelte";
  import { getSecret, getSharedSecret, credentialState } from "$lib/api/secrets";
  import { latestRequest } from "$lib/runtime/latest-request";
  import type { WorkspaceProfile } from "$lib/types";
  import {
    actionsOAuthAuthorizeUrl,
    actionsOAuthTokenUrl,
    actionsOpenApiUrl,
    actionsPrivacyUrl,
    actionsConfig,
  } from "$lib/types";

  interface Props {
    workspaceId: string;
    service: "mcp" | "actions";
    profile: WorkspaceProfile;
    publicMcpEndpoint?: string;
    publicActionsOrigin?: string;
    frpProfiles?: { id: string; name: string; server: string; serverPort: number }[];
  }

  let { workspaceId, service, profile, publicMcpEndpoint = "", publicActionsOrigin, frpProfiles = [] }: Props = $props();

  let loading = $state(true);
  let secrets = $state<Record<string, string>>({});
  let loadError = $state("");
  const requests = latestRequest();
  const actions = $derived(actionsConfig(profile));
  const auth = $derived(profile.auth);

  async function loadSecrets() {
    const id = workspaceId;
    const kind = service;
    const type = kind === "mcp" ? auth.type : actions.auth_type;
    const useShared = kind === "mcp" ? !!auth.use_shared_secrets : !!actions.use_shared_secrets;
    const clientId = auth.oauth_client_id;
    const ticket = requests.begin();
    secrets = {};
    loadError = "";
    loading = true;
    if ($credentialState.pending > 0 || $configurationState.pending > 0) return;
    const read = async (key: Parameters<typeof getSecret>[1]) =>
      (useShared ? await getSharedSecret(key as Parameters<typeof getSharedSecret>[0])
        : await getSecret(id, key)) ?? "";
    try {
      let next: Record<string, string> = {};
      if (kind === "mcp" && type === "oauth") {
        const [actualId, secret, password] = await Promise.all([
          useShared ? getSharedSecret("oauth_client_id") : Promise.resolve(clientId),
          read("oauth_client_secret"), read("oauth_password"),
        ]);
        next = { oauth_client_id: actualId ?? "", oauth_client_secret: secret, oauth_password: password };
      } else if (kind === "mcp" && type === "bearer") {
        next = { bearer_token: await read("bearer_token") };
      } else if (kind === "actions" && type === "api_key") {
        next = { actions_api_key: await read("actions_api_key") };
      } else if (kind === "actions" && type === "oauth") {
        next = { actions_oauth_client_secret: await read("actions_oauth_client_secret") };
      }
      if (requests.current(ticket) && id === workspaceId && kind === service) secrets = next;
    } catch {
      if (requests.current(ticket) && id === workspaceId && kind === service) {
        secrets = {};
        loadError = "凭据读取失败；旧值已清空。请重试，不要使用之前复制的密钥。";
      }
    } finally {
      if (requests.current(ticket) && id === workspaceId && kind === service) loading = false;
    }
  }

  $effect(() => {
    workspaceId; service; auth.type; auth.oauth_client_id; auth.use_shared_secrets;
    actions.auth_type; actions.use_shared_secrets;
    $credentialState;
    $configurationState;
    void loadSecrets();
    return () => requests.invalidate();
  });
</script>

<article class="tx-card p-5">
  <div class="mb-4">
    <p class="tx-section-label">GPT 配置</p>
    <p class="mt-1 text-xs text-[var(--color-text-muted)]">
      {service === "mcp"
        ? "复制以下内容到 ChatGPT → 设置 → 连接器 / MCP"
        : "复制以下内容到 GPT 编辑器 → Actions"}
    </p>
  </div>

  {#if loadError}
    <p class="mb-3 text-sm text-[var(--color-error)]">{loadError}</p>
    <button type="button" class="tx-btn-ghost mb-3" onclick={() => void loadSecrets()}>重新读取凭据</button>
  {/if}
  <div class="grid gap-3">
    {#if service === "mcp"}
      <CopyFieldRow
        label="公网 MCP 地址"
        value={publicMcpEndpoint}
        hint="GPT 连接器里填这个 URL"
      />
      {#if auth.type === "oauth"}
        <CopyFieldRow label="OAuth Client ID" value={secrets.oauth_client_id ?? ""} {loading} />
        <CopyFieldRow
          label="OAuth Client Secret" secret
          value={secrets.oauth_client_secret ?? ""}
          {loading}
        />
        <CopyFieldRow
          label="授权口令" secret
          value={secrets.oauth_password ?? ""}
          hint="仅在本工具的 OAuth 授权网页输入，不要发送到聊天"
          {loading}
        />
      {:else if auth.type === "bearer"}
        <CopyFieldRow label="Bearer Token" secret value={secrets.bearer_token ?? ""} {loading} />
      {:else}
        <p class="text-xs text-[var(--color-text-muted)]">当前未启用认证，仅本机调试可用。</p>
      {/if}
    {:else}
      <CopyFieldRow
        label="OpenAPI Schema URL"
        value={actionsOpenApiUrl(profile, frpProfiles, publicActionsOrigin)}
        hint="Actions → Import from URL"
      />
      <CopyFieldRow
        label="隐私政策 URL"
        value={actionsPrivacyUrl(profile, frpProfiles, publicActionsOrigin)}
        hint="GPT Actions 隐私政策字段"
      />
      {#if actions.auth_type === "api_key"}
        <CopyFieldRow
          label="API Key（Bearer）" secret
          value={secrets.actions_api_key ?? ""}
          hint="Actions 认证选 API Key → Bearer"
          {loading}
        />
      {:else if actions.auth_type === "oauth"}
        <CopyFieldRow label="OAuth Client ID" value={actions.oauth_client_id ?? ""} />
        <CopyFieldRow
          label="OAuth Client Secret" secret
          value={secrets.actions_oauth_client_secret ?? ""}
          {loading}
        />
        <CopyFieldRow
          label="Authorization URL"
          value={actionsOAuthAuthorizeUrl(profile, frpProfiles, publicActionsOrigin)}
        />
        <CopyFieldRow label="Token URL" value={actionsOAuthTokenUrl(profile, frpProfiles, publicActionsOrigin)} />
        <CopyFieldRow label="Scope" value={actions.oauth_scopes ?? ""} hint="空格分隔" />
      {:else}
        <p class="text-xs text-[var(--color-text-muted)]">当前未启用认证，公网暴露请改用 API Key 或 OAuth。</p>
      {/if}
    {/if}
  </div>
</article>
