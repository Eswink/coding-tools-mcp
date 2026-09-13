<script lang="ts">
  import { onDestroy } from "svelte";
  import { invoke } from "@tauri-apps/api/core";
  import { confirm } from "@tauri-apps/plugin-dialog";
  import type { AuthConfig } from "$lib/types";
  import { policyFromFields, sessionPolicy } from "$lib/remote-session-policy";
  let { workspaceId, auth, onSaveProfile }: { workspaceId: string; auth: AuthConfig; onSaveProfile: (auth: AuthConfig) => Promise<void> } = $props();
  let exclusive = $state(true);
  let accessMinutes = $state<number | undefined>(60);
  let refreshDays = $state<number | undefined>(30);
  let leaseHours = $state<number | undefined>(24);
  let idleMinutes = $state<number | undefined>(0);
  let busy = $state(false);
  let error = $state("");
  let result = $state("");
  let generation = 0;
  let operation = 0;
  let loadedId = "";
  let disposed = false;
  onDestroy(() => { disposed = true; generation++; operation++; });
  $effect(() => {
    const id = workspaceId; const p = sessionPolicy(auth.session_policy);
    if (id !== loadedId) { loadedId = id; operation++; busy = false; }
    generation++; exclusive = p.exclusive; accessMinutes = p.access_token_ttl_seconds / 60;
    refreshDays = p.refresh_session_ttl_seconds / 86400; leaseHours = p.chat_lease_ttl_seconds / 3600;
    idleMinutes = p.chat_idle_timeout_seconds / 60; error = ""; result = "";
  });
  async function save() {
    if (busy) return; const id = workspaceId, current = generation, original = auth;
    let policy;
    try { policy = policyFromFields(exclusive, accessMinutes, refreshDays, leaseHours, idleMinutes); }
    catch (e) { error = String(e); return; }
    const op = ++operation; busy = true; error = ""; result = "";
    try {
      const allowed = await confirm("保存会撤销当前聊天授权，并按现有配置流程重启监听。已签发的刷新会话保留原截止时间；长任务不会自动重跑。继续？", { title: "应用远程会话策略", kind: "warning", okLabel: "保存策略", cancelLabel: "取消" });
      if (!allowed || disposed || current !== generation || id !== workspaceId) return;
      await onSaveProfile({ ...original, session_policy: policy });
      if (!disposed && id === workspaceId && op === operation) result = "策略已保存。新签发令牌和新批准聊天使用新时长；客户端自行决定刷新时机。";
    } catch (e) { if (!disposed && id === workspaceId && op === operation) error = String(e); }
    finally { if (!disposed && id === workspaceId && op === operation) busy = false; }
  }
  async function refreshStatus(revoke = false) {
    if (busy) return; const id = workspaceId, current = generation, op = ++operation; busy = true; error = "";
    try {
      if (revoke && !await confirm("撤销此工作区的所有 OAuth 刷新会话？与这些会话关联的访问令牌也将被拒绝，客户端需要重新登录。", { title: "撤销刷新会话", kind: "warning" })) return;
      if (disposed || id !== workspaceId || current !== generation) return;
      const value = await invoke<{active_families:number;latest_expiry:number|null}>("refresh_session_control", { id, action: revoke ? "revoke_all" : "status" });
      if (!disposed && id === workspaceId && current === generation && op === operation) result = `有效刷新会话：${value.active_families}；最晚截止：${value.latest_expiry ? new Date(value.latest_expiry * 1000).toLocaleString() : "无"}`;
    } catch (e) { if (!disposed && id === workspaceId && current === generation && op === operation) error = String(e); }
    finally { if (!disposed && id === workspaceId && op === operation) busy = false; }
  }
</script>
<section class="remote-session-settings" aria-labelledby="remote-session-heading">
  <h3 id="remote-session-heading">远程会话安全</h3>
  <p>刷新令牌不等于聊天操作授权。令牌刷新不会续期、转移或自动批准独占聊天。</p>
  <fieldset disabled={busy}>
    <label class="wide"><input type="checkbox" bind:checked={exclusive} />默认独占 ChatGPT 聊天（按工作区生效）</label>
    <label>访问令牌有效期（分钟）<input type="number" min="5" max="480" step="1" bind:value={accessMinutes} /></label>
    <label>刷新会话有效期（天）<input type="number" min="1" max="90" step="1" bind:value={refreshDays} /></label>
    <label>独占聊天授权有效期（小时）<input type="number" min="1" max="720" step="1" bind:value={leaseHours} /></label>
    <label>空闲自动释放（分钟，0 为关闭）<input type="number" min="0" max="1440" step="1" bind:value={idleMinutes} /></label>
  </fieldset>
  <p>待审批固定 90 秒。空闲释放默认关闭，启用时最少 30 分钟；有未结束任务时进入排空状态，不转交独占权。聊天租约不是单个命令的执行超时。</p>
  <p>刷新采用强制轮换和重放检测；客户端决定何时调用刷新接口，并非桌面端定时刷新。ChatGPT 需要请求 <code>mcp offline_access</code> 才会收到刷新令牌；不要启用 OIDC。</p>
  {#if (leaseHours ?? 0) > 24}<p class="warning">超过 24 小时的聊天授权会扩大误操作窗口；使用完毕请手动释放。</p>{/if}
  {#if error}<p role="alert">{error}</p>{/if}
  {#if result}<p role="status">{result}</p>{/if}
  <div class="controls"><button type="button" class="tx-btn-primary" disabled={busy} onclick={() => void save()}>保存远程会话策略</button><button type="button" class="tx-btn-secondary" disabled={busy} onclick={() => void refreshStatus()}>查看刷新会话</button><button type="button" class="tx-btn-secondary" disabled={busy} onclick={() => void refreshStatus(true)}>撤销刷新会话</button></div>
</section>
<style>
  .remote-session-settings{padding:1.25rem;border:1px solid var(--color-border);border-radius:12px;background:var(--card-bg);margin-top:1rem;}h3{font-size:1rem;font-weight:600;}p{font-size:.82rem;line-height:1.65;color:var(--color-text-muted);margin:.6rem 0;}fieldset{border:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:1rem;margin:1rem 0;}label{display:flex;flex-direction:column;gap:.4rem;font-size:.85rem;}label.wide{grid-column:1/-1;flex-direction:row;align-items:center;gap:.6rem;}input[type=number]{padding:.6rem;border:1px solid var(--color-border);border-radius:8px;background:var(--card-bg);min-height:44px;}[role=alert],.warning{color:var(--danger);}.controls{display:flex;flex-wrap:wrap;gap:.7rem;}button{min-height:44px;}
</style>
