<script lang="ts">
  import { confirm } from "@tauri-apps/plugin-dialog";
  import { onDestroy } from "svelte";
  import ServicePanel from "$lib/components/ServicePanel.svelte";
  import GptQuickCopy from "$lib/components/GptQuickCopy.svelte";
  import Tabs from "$lib/components/Tabs.svelte";
  import TunnelConfigForm, { type TunnelFormConfig, type SaveTunnelOptions } from "$lib/components/TunnelConfigForm.svelte";
  import AuthConfigForm from "$lib/components/AuthConfigForm.svelte";
  import ActionsAuthForm from "$lib/components/ActionsAuthForm.svelte";
  import RemoteSessionSettings from "$lib/components/RemoteSessionSettings.svelte";
  import RuntimePolicyForm, { type RuntimePolicyDraft } from "$lib/components/RuntimePolicyForm.svelte";
  import ActionsPolicyForm, { type ActionsPolicyDraft } from "$lib/components/ActionsPolicyForm.svelte";
  import TaskPanel from "$lib/components/异步任务面板v2.svelte";
  import LogViewer from "$lib/components/LogViewer.svelte";
  import HealthPanel from "$lib/components/HealthPanel.svelte";
  import { originFromEndpoint } from "$lib/固定入口";
  import { actionsConfig, actionsOpenApiUrl, actionsPrivacyUrl, actionsOAuthAuthorizeUrl, actionsOAuthTokenUrl,
    type WorkspaceProfile, type RuntimeState, type AuthConfig, type ActionsAuthDraft } from "$lib/types";
  import type { FrpProfileDto } from "$lib/api/settings";
  import { showToast } from "$lib/stores/toast";

  type SubTab = "config" | "logs" | "health" | "tasks";
  interface Props {
    profile: WorkspaceProfile; service: "mcp" | "actions"; status: RuntimeState; statusMessage: string;
    busy: boolean; localEndpoint: string; publicEndpoint: string; activeOrigin?: string;
    frpProfiles: FrpProfileDto[]; tunnelConfig: TunnelFormConfig; subTab: SubTab; onTabChange: (tab: SubTab) => void;
    onToggle: () => void | Promise<void>; onPortChange: (port: number) => void | Promise<void>;
    onReload: () => void | Promise<void>; onSaveTunnel: (config: TunnelFormConfig, options?: SaveTunnelOptions) => void | Promise<void>;
    onSaveMcpAuth: (auth: AuthConfig) => Promise<void>; onSaveActionsAuth: (auth: ActionsAuthDraft) => void | Promise<void>;
    onSaveMcpPolicy: (policy: RuntimePolicyDraft) => void | Promise<void>; onSaveActionsPolicy: (policy: ActionsPolicyDraft) => void | Promise<void>;
    onBudgetSave: (milliseconds: number) => Promise<void>;
  }
  let { profile, service, status, statusMessage, busy, localEndpoint, publicEndpoint, activeOrigin,
    frpProfiles, tunnelConfig, subTab, onTabChange, onToggle, onPortChange, onReload, onSaveTunnel,
    onSaveMcpAuth, onSaveActionsAuth, onSaveMcpPolicy, onSaveActionsPolicy, onBudgetSave }: Props = $props();
  const actions = $derived(actionsConfig(profile));
  const mcp = $derived(service === "mcp");
  const tabs = [{ value: "config", label: "配置" }, { value: "logs", label: "日志" }, { value: "tasks", label: "异步任务" }, { value: "health", label: "健康" }];
  type Editor = { navigationState: () => { dirty: boolean; busy: boolean } };
  let portEditor = $state<Editor>();
  let tunnelEditor = $state<Editor>();
  let authEditor = $state<Editor>();
  let leaseEditor = $state<Editor>();
  let policyEditor = $state<Editor>();
  let taskEditor = $state<Editor>();
  let editRevision = 0;
  function navigationState() {
    const editors = [portEditor, ...(subTab === "config" ? [tunnelEditor, authEditor, leaseEditor, policyEditor] :
      subTab === "tasks" ? [taskEditor] : [])];
    const states = editors.map(editor => editor?.navigationState());
    return { dirty: states.some(state => state?.dirty), busy: states.some(state => state?.busy) };
  }
  let confirming = $state(false);
  let disposed = false;
  onDestroy(() => { disposed = true; });

  // Read authoritative form state at navigation time. A successful save is not
  // equivalent to clearing every other form's draft or cancelling an operation.
  export async function requestLeave(): Promise<boolean> {
    if (confirming || busy || disposed || navigationState().busy) return false;
    if (!navigationState().dirty) return true;
    const revision = editRevision;
    confirming = true;
    try {
      const accepted = await confirm("此服务面板有未保存的修改。切换将丢弃这些修改，已保存的配置不受影响。继续切换？",
        { title: "确认切换面板", kind: "warning", okLabel: "切换", cancelLabel: "继续编辑" });
      return accepted && !disposed && !busy && !navigationState().busy && revision === editRevision;
    } catch (error) {
      if (!disposed) showToast(String(error), { title: "无法确认切换", kind: "error" });
      return false;
    } finally { confirming = false; }
  }
  async function changeTab(next: string) {
    if (next === subTab || !tabs.some(tab => tab.value === next)) return;
    if (!await requestLeave()) return;
    onTabChange(next as SubTab);
  }
</script>
<div class="service-view" oninput={() => { editRevision++; }} onchange={() => { editRevision++; }}>
  <ServicePanel bind:this={portEditor} title={mcp ? "MCP" : "Actions"} subtitle={mcp ? "Streamable HTTP · 工具运行时" : "OpenAPI 网关 · ChatGPT Actions"}
    {status} {statusMessage} port={mcp ? profile.runtime.local_port : actions.local_port} portEditable={true} busy={busy || confirming}
    tunnelType={mcp ? profile.tunnel.type : actions.tunnel_type} {localEndpoint} {publicEndpoint}
    publicLabel={mcp ? "公网 MCP" : "OpenAPI"} showToggle={!mcp} {onToggle} {onPortChange} />
  <GptQuickCopy workspaceId={profile.id} {service} {profile} {frpProfiles} publicMcpEndpoint={mcp ? publicEndpoint : undefined} publicActionsOrigin={activeOrigin} />
  <Tabs items={tabs} value={subTab} label="服务操作" idPrefix="workspace-operations" panelId="workspace-service-panel" disabled={busy || confirming} onchange={(next) => void changeTab(next)} />
  <div id="workspace-service-panel" role="tabpanel" aria-labelledby={`workspace-operations-${subTab}`}>
  {#if subTab === "config"}
    <div class="configuration-stack">
      <section class="tx-card p-5" aria-label="隧道配置">
        <h3 class="tx-section-label">隧道</h3>
        <TunnelConfigForm bind:this={tunnelEditor} workspaceId={profile.id} {service} localPort={mcp ? profile.runtime.local_port : actions.local_port}
          activePublicOrigin={mcp ? originFromEndpoint(publicEndpoint, "/mcp") : activeOrigin ?? ""}
          onTested={onReload} config={tunnelConfig} onSave={onSaveTunnel} />
      </section>
      <section class="tx-card p-5" aria-label="认证配置">
        <h3 class="tx-section-label">认证</h3>
        {#if mcp}
          <AuthConfigForm bind:this={authEditor} workspaceId={profile.id} auth={profile.auth} onSaveProfile={onSaveMcpAuth} />
          <RemoteSessionSettings bind:this={leaseEditor} workspaceId={profile.id} auth={profile.auth} onSaveProfile={onSaveMcpAuth} />
        {:else}
          <ActionsAuthForm bind:this={authEditor} workspaceId={profile.id} authType={actions.auth_type} oauthClientId={actions.oauth_client_id ?? ""}
            oauthScopes={actions.oauth_scopes ?? ""} openapiUrl={actionsOpenApiUrl(profile, frpProfiles, activeOrigin)}
            privacyUrl={actionsPrivacyUrl(profile, frpProfiles, activeOrigin)} oauthAuthorizeUrl={actionsOAuthAuthorizeUrl(profile, frpProfiles, activeOrigin)}
            oauthTokenUrl={actionsOAuthTokenUrl(profile, frpProfiles, activeOrigin)} useSharedSecrets={actions.use_shared_secrets ?? false} onSave={onSaveActionsAuth} />
        {/if}
      </section>
      <section class="tx-card p-5" aria-label="执行策略">
        <h3 class="tx-section-label">策略</h3>
        {#if mcp}
          <RuntimePolicyForm bind:this={policyEditor} toolProfile={profile.runtime.tool_profile} permissionMode={profile.runtime.permission_mode}
            allowedCommands={profile.runtime.allowed_commands ?? ""} workspaceLocalEntries={profile.runtime.workspace_local_entries ?? true}
            workspaceScriptExtensions={profile.runtime.workspace_script_extensions ?? ".exe,.bat,.cmd,.ps1"} onSave={onSaveMcpPolicy} />
        {:else}
          <ActionsPolicyForm bind:this={policyEditor} allowedCommands={actions.allowed_commands ?? ""} maxPatchBytes={actions.max_patch_bytes ?? 200_000}
            permissionMode={actions.permission_mode} onSave={onSaveActionsPolicy} />
        {/if}
      </section>
    </div>
  {:else if subTab === "tasks"}
    <TaskPanel bind:this={taskEditor} workspaceId={profile.id} channel={service} maxTimeoutMs={(mcp ? profile.runtime.max_task_timeout_ms : actions.max_task_timeout_ms) ?? 86400000} {onBudgetSave} />
  {:else if subTab === "logs"}
    <LogViewer workspaceId={profile.id} {service} />
  {:else}
    <HealthPanel workspaceId={profile.id} />
  {/if}
  </div>
</div>
<style>
  .service-view, .configuration-stack { display:grid; gap:18px; min-width:0; }
  .tx-section-label { font-size:15px; color:var(--text-main); text-transform:none; letter-spacing:0; }
</style>
