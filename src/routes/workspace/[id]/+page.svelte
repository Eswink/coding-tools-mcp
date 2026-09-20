<script lang="ts">
  import { Box, Trash2 } from "@lucide/svelte";
  import PageHeader from "$lib/components/layout/PageHeader.svelte";
  import StatusBadge from "$lib/components/primitives/StatusBadge.svelte";
  import ServiceSwitcher from "$lib/components/workspace/ServiceSwitcher.svelte";
  import WorkspaceServiceView from "$lib/components/workspace/WorkspaceServiceView.svelte";
  import ExecutionAvailabilityPanel from "$lib/components/workspace/ExecutionAvailabilityPanel.svelte";
  import { defaultFrpOptions, originFromEndpoint } from "$lib/固定入口";
  import { onDestroy } from "svelte";
  import { applyAndRefresh, forCurrentWorkspace } from "$lib/runtime/configuration";
  import { goto } from "$app/navigation";
  import { page } from "$app/stores";
  import { type ActionsPolicyDraft } from "$lib/components/ActionsPolicyForm.svelte";
  import ChatAuthorizationPanel from "$lib/components/聊天授权面板v1.svelte";
  import { type RuntimePolicyDraft } from "$lib/components/RuntimePolicyForm.svelte";
  import ChatGptSessionPrompt from "$lib/components/ChatGptSessionPrompt.svelte";
  import { type TunnelFormConfig, type SaveTunnelOptions } from "$lib/components/TunnelConfigForm.svelte";
  import WorkspaceMetaForm from "$lib/components/WorkspaceMetaForm.svelte";
  import {
    deleteWorkspace,
    getActionsRuntimeStatus,
    getRuntimeStatus,
    listWorkspaces,
    pauseMcpExecution,
    resumeMcpExecution,
    startActionsRuntime,
    startRuntime,
    stopActionsRuntime,
    stopRuntime,
    updateWorkspace,
    type TunnelSecretUpdate,
  } from "$lib/api/workspaces";
  import { listFrpProfiles, setLastWorkspace, type FrpProfileDto } from "$lib/api/settings";
  import { confirm } from "@tauri-apps/plugin-dialog";
  import { runServiceToggle, notifyStartFailure } from "$lib/runtime/service";
  import { showToast } from "$lib/stores/toast";
  import { actionsRuntimeStates, mcpRuntimeStates, workspaces } from "$lib/stores/app";
  import {
    actionsConfig,
    actionsLocalEndpoint,
    actionsOpenApiUrl,
    mcpLocalEndpoint,
    type AuthConfig,
    type ActionsAuthDraft,
    type RuntimeState,
    type RuntimeStatus,
    type WorkspaceProfile,
  } from "$lib/types";

  type ServiceTab = "mcp" | "actions";
  type SubTab = "config" | "logs" | "health" | "tasks";

  let profile = $state<WorkspaceProfile | null>(null);
  let mcpStatus = $state<RuntimeState>("stopped");
  let actionsStatus = $state<RuntimeState>("stopped");
  let mcpStatusMessage = $state("");
  let actionsStatusMessage = $state("");
  let mcpBusy = $state(false);
  let mcpExecutionBusy = $state(false);
  let mcpExecutionState = $state<"online" | "offline" | undefined>(undefined);
  let mcpRuntimeGeneration = $state("");
  let actionsBusy = $state(false);
  let mcpLocal = $state("");
  let mcpPublic = $state("");
  let actionsLocal = $state("");
  let actionsPublic = $state("");
  let frpProfiles = $state<FrpProfileDto[]>([]);

  let serviceView = $state<WorkspaceServiceView>();
  let switchingService = $state(false);
  async function changeService(next: ServiceTab) {
    if (next === activeService || switchingService || configurationBusy || mcpBusy || mcpExecutionBusy || actionsBusy) return;
    const id = workspaceId;
    const view = serviceView;
    switchingService = true;
    try {
      if (view && !await view.requestLeave()) return;
      if (!disposed && id === workspaceId && view === serviceView && !configurationBusy && !mcpBusy && !mcpExecutionBusy && !actionsBusy) activeService = next;
    } finally { switchingService = false; }
  }

  let activeService = $state<ServiceTab>("mcp");
  let mcpSubTab = $state<SubTab>("config");
  let actionsSubTab = $state<SubTab>("config");
  let loadGeneration = 0;
  let disposed = false;
  let configurationBusy = $state(false);
  onDestroy(() => { disposed = true; loadGeneration += 1; });
  const currentWorkspaceId = () => disposed ? undefined : workspaceId;

  function bindWorkspace<A extends unknown[]>(id: string, action: (...args: A) => Promise<void>) {
    return forCurrentWorkspace(id, currentWorkspaceId, action);
  }

  async function persistProfile(next: WorkspaceProfile, tunnelSecret?: TunnelSecretUpdate) {
    if (disposed || next.id !== workspaceId) throw new Error("工作区已切换，请重试。");
    if (configurationBusy || mcpBusy || mcpExecutionBusy || actionsBusy) throw new Error("其他配置操作尚未完成，请稍后重试。");
    configurationBusy = true;
    loadGeneration += 1;
    try {
      await applyAndRefresh(() => updateWorkspace(next, tunnelSecret), async () => {
        if (!disposed && next.id === workspaceId) await load(next.id);
      });
    } finally { configurationBusy = false; }
  }


  const workspaceId = $derived($page.params.id);
  const actions = $derived(profile ? actionsConfig(profile) : null);
  const actionsActiveOrigin = $derived(
    actionsStatus === "running" || actionsStatus === "starting"
      ? originFromEndpoint(actionsPublic, "/openapi.json") : undefined,
  );

  const mcpTunnelForm = $derived<TunnelFormConfig>({
    type: profile?.tunnel.type ?? "none",
    public_url: profile?.tunnel.public_url ?? "",
    frp: defaultFrpOptions(profile?.tunnel.frp),
    frp_server: profile?.tunnel.frp_server ?? "",
    frp_subdomain: profile?.tunnel.frp_subdomain ?? "",
    frp_profile_id: profile?.tunnel.frp_profile_id ?? "",
    frp_server_port: profile?.tunnel.frp_server_port ?? 7000,
    cloudflare_mode: profile?.tunnel.cloudflare_mode ?? "quick",
    cloudflare_http2: profile?.tunnel.cloudflare_http2 ?? true,
    use_proxy: profile?.tunnel.use_proxy ?? true,
  });

  const actionsTunnelForm = $derived<TunnelFormConfig>({
    type: actions?.tunnel_type ?? "none",
    public_url: actions?.public_url ?? "",
    frp: defaultFrpOptions(actions?.frp),
    frp_server: actions?.frp_server ?? "",
    frp_subdomain: actions?.frp_subdomain ?? "",
    frp_profile_id: actions?.frp_profile_id ?? "",
    frp_server_port: actions?.frp_server_port ?? 7000,
    cloudflare_mode: actions?.cloudflare_mode ?? "quick",
    cloudflare_http2: actions?.cloudflare_http2 ?? true,
    use_proxy: actions?.use_proxy ?? true,
  });


  function applyMcpRuntime(runtime: RuntimeStatus, id = workspaceId) {
    if (disposed || !id || id !== workspaceId) return;
    mcpStatus = runtime.state;
    mcpStatusMessage = runtime.localMessage ?? "";
    mcpExecutionState = runtime.executionState;
    mcpRuntimeGeneration = runtime.runtimeGeneration ?? "";
    mcpLocal = runtime.localEndpoint;
    mcpPublic = runtime.publicEndpoint;
    mcpRuntimeStates.update((current) => ({ ...current, [id]: runtime.state }));
  }

  function applyActionsRuntime(runtime: RuntimeStatus, id = workspaceId) {
    if (disposed || !id || id !== workspaceId) return;
    actionsStatus = runtime.state;
    actionsStatusMessage = runtime.localMessage ?? "";
    actionsLocal = runtime.localEndpoint;
    actionsPublic = runtime.publicEndpoint;
    actionsRuntimeStates.update((current) => ({ ...current, [id]: runtime.state }));
  }

  async function load(id = workspaceId) {
    if (disposed || !id || id !== workspaceId) return;
    const generation = ++loadGeneration;
    const items = await listWorkspaces();
    if (disposed || generation !== loadGeneration || id !== workspaceId) return;
    workspaces.set(items);
    const loadedFrpProfiles = await listFrpProfiles();
    if (disposed || generation !== loadGeneration || id !== workspaceId) return;
    frpProfiles = loadedFrpProfiles;
    const nextProfile = items.find((item) => item.id === id) ?? null;
    if (disposed || generation !== loadGeneration || id !== workspaceId) return;
    profile = nextProfile;
    if (nextProfile) {
      await setLastWorkspace(nextProfile.id);
    }
    if (disposed || generation !== loadGeneration || id !== workspaceId) return;
    if (!nextProfile) {
      await goto("/");
      return;
    }

    const [mcpRuntime, actionsRuntime] = await Promise.all([
      getRuntimeStatus(id),
      getActionsRuntimeStatus(id),
    ]);
    if (disposed || generation !== loadGeneration || id !== workspaceId) return;
    applyMcpRuntime(mcpRuntime, id);
    applyActionsRuntime(actionsRuntime, id);
  }

  async function refreshProfile(id = workspaceId): Promise<WorkspaceProfile | null> {
    if (disposed || !id || id !== workspaceId) return null;
    const generation = ++loadGeneration;
    const items = await listWorkspaces();
    if (disposed || id !== workspaceId || generation !== loadGeneration) return null;
    workspaces.set(items);
    const nextProfile = items.find((item) => item.id === id) ?? null;
    profile = nextProfile;
    return nextProfile;
  }

  function tunnelConfigured(type: string | undefined): boolean {
    return type === "cloudflare" || type === "frp";
  }

  async function afterServiceStart(
    service: "mcp" | "actions",
    runtime: { state: RuntimeState; publicEndpoint: string },
    id: string,
  ) {
    const nextProfile = await refreshProfile(id);
    if (id !== workspaceId) return;
    const tunnelType =
      service === "mcp"
        ? nextProfile?.tunnel.type
        : nextProfile
          ? actionsConfig(nextProfile).tunnel_type
          : undefined;
    if (runtime.state === "running" && tunnelConfigured(tunnelType) && !runtime.publicEndpoint) {
      showToast(
        "本地服务已启动，但隧道未能自动连接。请检查代理设置与隧道配置，或查看日志。",
        { title: "隧道未连接", kind: "warning", duration: 8000 },
      );
    }
  }

  async function startMcpConnector() {
    const id = workspaceId;
    if (
      disposed
      || !id
      || mcpBusy
      || mcpExecutionBusy
      || configurationBusy
      || mcpStatus === "running"
      || mcpStatus === "starting"
      || mcpStatus === "stopping"
    ) return;

    mcpBusy = true;
    try {
      const runtime = await startRuntime(id);
      if (!disposed && id === workspaceId) {
        applyMcpRuntime(runtime, id);
        if (runtime.state === "running") {
          await afterServiceStart("mcp", runtime, id);
        } else {
          notifyStartFailure("MCP Connector", runtime);
        }
      }
    } catch (error) {
      if (!disposed && id === workspaceId) {
        showToast(String(error), {
          title: "MCP Connector 启动失败",
          kind: "error",
          duration: 8000,
        });
      }
    } finally {
      mcpBusy = false;
    }
  }

  async function stopMcpConnector() {
    const id = workspaceId;
    if (
      disposed
      || !id
      || mcpStatus !== "running"
      || mcpBusy
      || mcpExecutionBusy
      || configurationBusy
    ) return;

    mcpBusy = true;
    try {
      const confirmed = await confirm(
        "停止 Connector 会关闭 MCP/OAuth 监听器和公网隧道。\n如果只是暂时不允许远程操作，请使用“暂停远程执行”。",
        {
          title: "停止 MCP Connector",
          kind: "warning",
          okLabel: "停止 Connector",
          cancelLabel: "取消",
        },
      );
      if (!confirmed || disposed || id !== workspaceId || mcpStatus !== "running") return;

      const runtime = await stopRuntime(id);
      if (!disposed && id === workspaceId) {
        applyMcpRuntime(runtime, id);
      }
    } catch (error) {
      if (!disposed && id === workspaceId) {
        showToast(String(error), {
          title: "MCP Connector 停止失败",
          kind: "error",
          duration: 8000,
        });
      }
    } finally {
      mcpBusy = false;
    }
  }

  async function toggleMcpExecution() {
    const id = workspaceId;
    const generation = mcpRuntimeGeneration;
    if (
      disposed
      || !id
      || mcpStatus !== "running"
      || !generation
      || mcpExecutionBusy
      || mcpBusy
      || configurationBusy
    ) return;

    mcpExecutionBusy = true;
    try {
      const paused = mcpExecutionState === "offline";
      const runtime = paused
        ? await resumeMcpExecution(id, generation)
        : await pauseMcpExecution(id, generation);
      if (!disposed && id === workspaceId) {
        applyMcpRuntime(runtime, id);
        showToast(
          paused ? "远程执行已恢复，现有 Connector 与隧道未重启。" : "远程执行已暂停，Connector、OAuth 与隧道保持在线。",
          { kind: "success" },
        );
      }
    } catch (error) {
      if (!disposed && id === workspaceId) {
        showToast(String(error), { title: "远程执行状态切换失败", kind: "error" });
        try {
          applyMcpRuntime(await getRuntimeStatus(id), id);
        } catch {
          // Keep the original action error visible; a later page refresh will retry status.
        }
      }
    } finally {
      mcpExecutionBusy = false;
    }
  }

  async function toggleActions() {
    const id = workspaceId;
    if (disposed || !id || actionsBusy || configurationBusy) return;
    const wasRunning = actionsStatus === "running";
    actionsBusy = true;
    try {
      const runtime = await runServiceToggle(
        wasRunning,
        () => startActionsRuntime(id),
        () => stopActionsRuntime(id),
        "Actions",
      );
      if (!disposed && runtime && id === workspaceId) {
        applyActionsRuntime(runtime, id);
        if (!wasRunning) {
          if (runtime.state === "running") {
            await afterServiceStart("actions", runtime, id);
          } else {
            notifyStartFailure("Actions", runtime);
          }
        }
      }
    } finally {
      actionsBusy = false;
    }
  }

  async function saveMcpPort(port: number) {
    if (!profile || profile.runtime.local_port === port) return;
    const next = { ...profile, runtime: { ...profile.runtime, local_port: port } };
    await persistProfile(next);
  }

  async function saveActionsPort(port: number) {
    if (!profile) return;
    const current = actionsConfig(profile);
    if (current.local_port === port) return;
    const next = { ...profile, actions: { ...current, local_port: port } };
    await persistProfile(next);
  }

  async function saveMcpTunnel(config: TunnelFormConfig, options?: SaveTunnelOptions) {
    if (!profile) return;
    const targetWorkspaceId = workspaceId;
    if (!targetWorkspaceId) return;
    const next: WorkspaceProfile = {
      ...profile,
      tunnel: {
        ...profile.tunnel,
        type: config.type,
        public_url: config.public_url,
        frp: { ...config.frp },
        frp_server: config.frp_server,
        frp_subdomain: config.frp_subdomain,
        frp_profile_id: config.frp_profile_id,
        frp_server_port: config.frp_server_port,
        cloudflare_mode: config.cloudflare_mode,
        cloudflare_http2: config.cloudflare_http2,
        use_proxy: config.use_proxy,
      },
    };
    await persistProfile(next, options?.tunnelSecret);
  }

  async function saveActionsTunnel(config: TunnelFormConfig, options?: SaveTunnelOptions) {
    if (!profile) return;
    const targetWorkspaceId = workspaceId;
    if (!targetWorkspaceId) return;
    const current = actionsConfig(profile);
    const next: WorkspaceProfile = {
      ...profile,
      actions: {
        ...current,
        tunnel_type: config.type,
        public_url: config.public_url,
        frp: { ...config.frp },
        frp_server: config.frp_server,
        frp_subdomain: config.frp_subdomain,
        frp_profile_id: config.frp_profile_id,
        frp_server_port: config.frp_server_port,
        cloudflare_mode: config.cloudflare_mode,
        cloudflare_http2: config.cloudflare_http2,
        use_proxy: config.use_proxy,
      },
    };
    await persistProfile(next, options?.tunnelSecret);
  }

  async function saveTaskBudget(service: ServiceTab, maxTimeoutMs: number) {
    if (!profile) return;
    const next: WorkspaceProfile = service === "mcp"
      ? { ...profile, runtime: { ...profile.runtime, max_task_timeout_ms: maxTimeoutMs } }
      : { ...profile, actions: { ...actionsConfig(profile), max_task_timeout_ms: maxTimeoutMs } };
    await persistProfile(next);
  }

  async function saveMcpPolicy(draft: RuntimePolicyDraft) {
    if (!profile) return;
    const next: WorkspaceProfile = {
      ...profile,
      runtime: {
        ...profile.runtime,
        tool_profile: draft.toolProfile,
        permission_mode: draft.permissionMode,
        allowed_commands: draft.allowedCommands,
        workspace_local_entries: draft.workspaceLocalEntries,
        workspace_script_extensions: draft.workspaceScriptExtensions,
      },
    };
    await persistProfile(next);
  }

  async function saveActionsPolicy(draft: ActionsPolicyDraft) {
    if (!profile) return;
    const current = actionsConfig(profile);
    const next: WorkspaceProfile = {
      ...profile,
      actions: {
        ...current,
        allowed_commands: draft.allowedCommands,
        max_patch_bytes: draft.maxPatchBytes,
        permission_mode: draft.permissionMode,
      },
    };
    await persistProfile(next);
  }

  async function saveMcpAuth(auth: AuthConfig) {
    if (!profile) return;
    const next: WorkspaceProfile = { ...profile, auth: { ...auth } };
    await persistProfile(next);
  }

  async function saveActionsAuth(draft: ActionsAuthDraft) {
    if (!profile) return;
    const current = actionsConfig(profile);
    const next: WorkspaceProfile = { ...profile, actions: {
      ...current, auth_type: draft.authType,
      oauth_client_id: draft.oauthClientId || current.oauth_client_id,
      oauth_scopes: draft.oauthScopes, use_shared_secrets: draft.useSharedSecrets,
    } };
    await persistProfile(next);
  }

  async function saveWorkspaceName(name: string) {
    if (!profile || profile.name === name) return;
    const next = { ...profile, name };
    await persistProfile(next);
  }

  async function saveWorkspacePath(path: string) {
    if (!profile || profile.path === path) return;
    const next = { ...profile, path };
    await persistProfile(next);
    if (!disposed && next.id === workspaceId) showToast("工作区目录已更新", { kind: "success" });
  }

  async function removeWorkspace() {
    if (!profile || !workspaceId || configurationBusy || mcpBusy || mcpExecutionBusy || actionsBusy) return;
    const id = workspaceId;
    const name = profile.name;
    configurationBusy = true;
    try {
      const confirmed = await confirm(`确定删除工作区「${name}」？此操作不可撤销。`, {
        title: "删除工作区", kind: "warning", okLabel: "删除", cancelLabel: "取消",
      });
      if (!confirmed || disposed || id !== workspaceId) return;
      await deleteWorkspace(id);
      workspaces.update((items) => items.filter((item) => item.id !== id));
      for (const store of [mcpRuntimeStates, actionsRuntimeStates]) {
        store.update((states) => { const next = { ...states }; delete next[id]; return next; });
      }
      if (!disposed && id === workspaceId) await goto("/");
    } catch (error) {
      if (!disposed && id === workspaceId) {
        showToast(String(error), { title: "删除工作区失败", kind: "error" });
        await load(id).catch(() => {});
      }
    } finally { configurationBusy = false; }
  }

  $effect(() => {
    const id = workspaceId;
    if (!id) return;
    profile = null;
    void load(id).catch(() => {
      if (!disposed && id === workspaceId) showToast("工作区状态读取失败，请刷新后重试。", { kind: "error" });
    });

    return () => {
      loadGeneration += 1;
    };
  });
</script>

{#if profile && actions}
  {#key profile.id}
  <section class="page-scroll" aria-label="工作区详情">
    <div class="page-header">
      <PageHeader title={profile.name} section="工作区" description="管理工作区的服务配置、授权和运行状态">
        {#snippet icon()}<Box size={32} />{/snippet}
        {#snippet status()}<StatusBadge state={mcpStatus} />{/snippet}
        {#snippet actions()}<button type="button" class="tx-btn-ghost tx-btn-destructive" disabled={configurationBusy || mcpBusy || mcpExecutionBusy || actionsBusy} onclick={() => void removeWorkspace()}><Trash2 size={17} aria-hidden="true" />删除工作区</button>{/snippet}
      </PageHeader>
      <WorkspaceMetaForm workspaceId={profile.id} name={profile.name} path={profile.path}
        onSave={bindWorkspace(profile.id, saveWorkspaceName)} onUpdatePath={bindWorkspace(profile.id, saveWorkspacePath)} />
      <div class="mt-5"><ChatGptSessionPrompt /></div>
      <ChatAuthorizationPanel workspaceId={profile.id} />
      <ServiceSwitcher value={activeService} mcpState={mcpStatus} actionsState={actionsStatus}
        disabled={switchingService || configurationBusy || mcpBusy || mcpExecutionBusy || actionsBusy} onchange={(next) => void changeService(next)} />
    </div>
    <div class="page-body">
      {#if activeService === "mcp"}
        <ExecutionAvailabilityPanel
          state={mcpExecutionState}
          runtimeState={mcpStatus}
          busy={configurationBusy || mcpBusy || mcpExecutionBusy}
          onStart={() => void startMcpConnector()}
          onToggle={() => void toggleMcpExecution()}
          onStop={() => void stopMcpConnector()}
        />
      {/if}
      {#key activeService}
      {@const currentService = activeService}
      <WorkspaceServiceView bind:this={serviceView} {profile} service={activeService}
        status={activeService === "mcp" ? mcpStatus : actionsStatus} statusMessage={activeService === "mcp" ? mcpStatusMessage : actionsStatusMessage}
        busy={configurationBusy || mcpBusy || mcpExecutionBusy || actionsBusy}
        localEndpoint={activeService === "mcp" ? mcpLocal || mcpLocalEndpoint(profile.runtime.local_port) : actionsLocal || actionsLocalEndpoint(actions.local_port)}
        publicEndpoint={activeService === "mcp" ? mcpPublic : actionsPublic || actionsOpenApiUrl(profile, frpProfiles, actionsActiveOrigin)}
        activeOrigin={actionsActiveOrigin} {frpProfiles} tunnelConfig={activeService === "mcp" ? mcpTunnelForm : actionsTunnelForm}
        subTab={activeService === "mcp" ? mcpSubTab : actionsSubTab}
        onTabChange={(next) => { if (currentService === "mcp") mcpSubTab = next; else actionsSubTab = next; }}
        onToggle={activeService === "mcp" ? startMcpConnector : toggleActions}
        onPortChange={bindWorkspace(profile.id, activeService === "mcp" ? saveMcpPort : saveActionsPort)}
        onReload={() => load()} onSaveTunnel={bindWorkspace(profile.id, activeService === "mcp" ? saveMcpTunnel : saveActionsTunnel)}
        onSaveMcpAuth={bindWorkspace(profile.id, saveMcpAuth)} onSaveActionsAuth={bindWorkspace(profile.id, saveActionsAuth)}
        onSaveMcpPolicy={bindWorkspace(profile.id, saveMcpPolicy)} onSaveActionsPolicy={bindWorkspace(profile.id, saveActionsPolicy)}
        onBudgetSave={bindWorkspace(profile.id, (ms: number) => saveTaskBudget(currentService, ms))} />
      {/key}
    </div>
    <footer class="border-t border-[var(--color-border)] px-8 py-4 text-xs text-[var(--color-text-muted)]">
      MCP 默认端口 28766，Actions 默认 8787，可同时运行。服务运行不等于当前聊天已获授权。
    </footer>
  </section>
  {/key}
{:else}
  <div class="page-body" role="status">正在读取工作区…</div>
{/if}
