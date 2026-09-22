<script lang="ts">
  import { LockKeyhole } from "@lucide/svelte";
  import { untrack } from "svelte";
  import { invoke } from "@tauri-apps/api/core";
  import { confirm } from "@tauri-apps/plugin-dialog";
  type Grant = { id: string; fingerprint: string; status: string; scopes: string[]; expires_at: number; idle_expires_at: number };
  type Snapshot = {
    records: Grant[];
    exclusive: boolean;
    oauth_ready: boolean;
    available_scopes: string[];
    lease_state: string;
    policy: {
      chat_lease_ttl_seconds: number;
      chat_idle_timeout_seconds: number;
      new_chat_admission: "review" | "local_window" | "deny_new";
    };
    admission: {
      mode: "review" | "local_window" | "deny_new";
      armed: boolean;
      expires_at: number | null;
      single_use: boolean;
    };
    recovery: {required: boolean; generation: string};
  };
  let { workspaceId }: { workspaceId: string } = $props();
  let snapshot = $state<Snapshot | null>(null);
  let error = $state("");
  let busy = $state(false);
  let selections = $state<Record<string, string[]>>({});
  let verified = $state<Record<string, boolean>>({});
  let now = $state(Date.now() / 1000);
  let generation = 0;
  let mutation = 0;
  const label: Record<string, string> = { pending: "待审批", active: "已授权", denied: "已拒绝", revoked: "已撤销", expired: "已过期" };
  const scopeLabel: Record<string, string> = {
    "workspace.read": "工作区状态", "files.read": "读取文件", "files.write": "修改文件", "exec.run": "执行命令（可访问共享文件）",
    "task.read": "查看本聊天任务", "task.manage": "管理本聊天任务", "history.read": "读取本聊天归档", "history.write": "保存本聊天归档", "harness.write": "管理本聊天开发计划"
  };
  async function call(id: string, action: string, extra: Record<string, unknown> = {}): Promise<Snapshot> {
    return invoke("chat_authorization_control", { id, action, requestId: null, scopes: null, exclusive: null, ...extra });
  }
  $effect(() => {
    const id = workspaceId; const current = ++generation;
    snapshot = null; error = ""; selections = {}; verified = {}; busy = false;
    let disposed = false; let refreshing = false;
    const refresh = async () => {
      if (disposed || refreshing || busy) return;
      refreshing = true; const version = mutation;
      try { const value = await call(id, "status"); if (!disposed && generation === current && !busy && version === mutation) { snapshot = value; error = ""; } }
      catch (e) { if (!disposed && generation === current) error = String(e); }
      finally { refreshing = false; }
    };
    untrack(() => void refresh()); const timer = setInterval(() => { now = Date.now() / 1000; void refresh(); }, 2500);
    return () => { disposed = true; clearInterval(timer); };
  });
  async function act(action: string, extra: Record<string, unknown> = {}) {
    if (busy) return;
    const id = workspaceId, current = generation; ++mutation; busy = true; error = "";
    try {
      if (action === "cancel_sessions" || action === "acknowledge_recovery") {
        const message = action === "cancel_sessions" ? "终止此工作区所有已知交互进程？异步任务请另在任务面板取消。已写入文件不会回滚。"
          : "仅在已核对操作系统进程、确认旧进程及其子进程全部终止，并已处理异步任务中的未知状态后继续。此操作只解除恢复锁，不会替你终止进程。";
        if (!await confirm(message, { title: "本机工作区安全确认", kind: "warning", okLabel: "已核实并继续", cancelLabel: "取消" })) return;
        if (generation !== current || id !== workspaceId) return;
      }
      const value = await call(id, action, extra); if (generation === current) snapshot = value;
    }
    catch (e) { if (generation === current) error = String(e); }
    finally { if (generation === current) busy = false; }
  }
  function toggle(g: Grant, scope: string, enabled: boolean) {
    const selected = new Set(selections[g.id] ?? g.scopes);
    if (enabled) selected.add(scope); else selected.delete(scope);
    selections = { ...selections, [g.id]: [...selected] };
  }
</script>

<section class="chat-authorization" aria-labelledby="chat-authorization-heading">
  <div class="heading">
    <div class="authorization-title"><span class="authorization-icon" aria-hidden="true"><LockKeyhole size={26} /></span><div><h3 id="chat-authorization-heading">ChatGPT 聊天授权</h3>
      <p>OAuth 连接不等于当前聊天获准。核对聊天返回的指纹后，在本机批准；不要将密码或令牌发送到聊天。</p></div></div>
    <button type="button" class="tx-btn-secondary" disabled={busy || !snapshot} onclick={() => void act("revoke_all")}>撤销全部</button>
  </div>
  {#if error}<p role="alert">{error}</p>{/if}
  {#if snapshot}
    {#if !snapshot.oauth_ready}<p role="alert">当前未启用 OAuth。所有网络业务调用将被拒绝，请先配置 OAuth；旧 Actions 不支持聊天授权。</p>{/if}
    <p class="exclusive">独占聊天模式：{snapshot.exclusive ? "开启" : "关闭"}。请在“远程会话安全”中修改并保存。</p>
    {#if snapshot.admission.mode === "local_window"}
      {#if snapshot.admission.armed}
        <p role="status">
          新聊天申请：本机临时开放中；仅允许下一条新申请，剩余
          {Math.max(0, Math.ceil((snapshot.admission.expires_at ?? now) - now))} 秒。
        </p>
        <button type="button" class="tx-btn-secondary" disabled={busy} onclick={() => void act("disarm_new_chat")}>关闭新聊天申请</button>
      {:else}
        <p>新聊天申请：默认关闭。仅在你准备核对新聊天指纹时临时开放。</p>
        <button type="button" class="tx-btn-primary" disabled={busy || snapshot.recovery.required} onclick={() => void act("arm_new_chat")}>允许下一条新聊天申请（90 秒）</button>
      {/if}
    {:else if snapshot.admission.mode === "deny_new"}
      <p>新聊天申请已关闭。现有已授权聊天可继续按其租约使用；如需改变策略，请到“远程会话安全”保存设置。</p>
    {:else}
      <p>新聊天申请：自动进入本机审批（兼容模式）。陌生聊天可以创建待审批请求，但仍必须在本机核对指纹后批准。</p>
    {/if}
    <p>待审批 90 秒；新授权最长 {snapshot.policy.chat_lease_ttl_seconds / 3600} 小时；空闲释放：{snapshot.policy.chat_idle_timeout_seconds === 0 ? "关闭" : `${snapshot.policy.chat_idle_timeout_seconds / 60} 分钟`}。应用重启后重新审批，令牌刷新不会续期聊天授权。</p>
    {#if snapshot.lease_state === "draining"}
      <p role="status">排空中：旧会话仍有未结束操作或持久化尚未确认，暂不接受其他聊天申请。撤销不回滚已执行操作。</p>
      <button type="button" class="tx-btn-secondary" disabled={busy} onclick={() => void act("cancel_sessions")}>终止本工作区交互进程</button>
      <p>异步任务请在“异步任务”面板取消；未知终止状态必须先从本机核实。</p>
    {/if}
    {#if snapshot.recovery.required}
      <p role="alert">恢复锁定：检测到上次执行未留下安全结束记录。先核对旧进程和异步任务，不能直接让新聊天接管。</p>
      <button type="button" class="tx-btn-secondary" disabled={busy} onclick={() => void act("acknowledge_recovery", { requestId: snapshot?.recovery.generation })}>已在本机核实旧任务全部终止</button>
    {/if}
    {#if snapshot.records.length === 0}<p>暂无请求。仅在需要远程操作的聊天中明确申请授权。</p>{/if}
    <div class="records">
      {#each snapshot.records as grant (grant.id)}
        <article>
          <div class="heading"><strong>会话指纹 <code>{grant.fingerprint}</code></strong><span>{label[grant.status] ?? grant.status}</span></div>
          {#if grant.status === "pending"}
            <fieldset disabled={busy}><legend>批准权限（可缩减，不能扩大）</legend>
              {#each grant.scopes as scope}<label><input type="checkbox" checked={(selections[grant.id] ?? grant.scopes).includes(scope)}
                onchange={(e) => toggle(grant, scope, e.currentTarget.checked)} />{scopeLabel[scope] ?? scope}</label>{/each}
            </fieldset>
            <label class="exclusive"><input type="checkbox" checked={verified[grant.id] ?? false} disabled={busy} onchange={(e) => verified = {...verified, [grant.id]: e.currentTarget.checked}} />我已核对该聊天返回的指纹</label>
            <p>剩余 {Math.max(0, Math.ceil(grant.expires_at - now))} 秒</p>
            <div class="controls">
              <button type="button" class="tx-btn-secondary" disabled={busy} onclick={() => void act("deny", { requestId: grant.id })}>拒绝</button>
              <button type="button" class="tx-btn-primary" disabled={busy || !snapshot.oauth_ready || !verified[grant.id] || now >= grant.expires_at || (selections[grant.id] ?? grant.scopes).length === 0}
                onclick={() => void act("approve", { requestId: grant.id, scopes: selections[grant.id] ?? grant.scopes })}>核对指纹并批准</button>
            </div>
          {:else if grant.status === "active"}
            <p>{grant.scopes.map(s => scopeLabel[s] ?? s).join(" · ")}</p>
            <p>最迟失效：{new Date(Math.min(grant.expires_at, grant.idle_expires_at) * 1000).toLocaleString()}</p>
            <button type="button" class="tx-btn-secondary" disabled={busy} onclick={() => void act("revoke", { requestId: grant.id })}>撤销此聊天</button>
          {/if}
        </article>
      {/each}
    </div>
  {:else}<p aria-live="polite">正在读取本机授权状态…</p>{/if}
</section>
<style>
  .authorization-title { display:flex; align-items:center; gap:16px; flex:1; min-width:0; }
  .authorization-icon { display:grid; place-items:center; width:48px; height:48px; border-radius:12px; flex-shrink:0; color:var(--success); background:var(--success-soft); }
  .chat-authorization { margin-top: 1rem; padding: 20px; border: 1px solid var(--color-border); border-radius: var(--card-radius); box-shadow: var(--card-shadow); background: var(--card-bg); }
  h3 { font-size: 17px; font-weight: 600; } p { font-size: 0.78rem; color: var(--color-text-muted); line-height: 1.6; margin: 0.45rem 0; }
  .heading { display: flex; align-items: center; justify-content: space-between; gap: 1rem; flex-wrap: wrap; }
  .exclusive, fieldset label { display: flex; align-items: center; gap: 0.5rem; font-size: 0.8rem; padding: 0.45rem 0; }
  fieldset { border: 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 0 0.8rem; margin: 0.6rem 0; }
  legend { font-size: 0.8rem; } .records { display: grid; gap: 0.7rem; } article { border: 1px solid var(--color-border); border-radius: 8px; padding: 0.8rem; }
  .controls { display: flex; gap: 0.7rem; } button { min-height: 44px; } code { overflow-wrap: anywhere; } input { flex-shrink: 0; }
</style>
