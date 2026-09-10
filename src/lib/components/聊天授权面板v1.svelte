<script lang="ts">
  import { untrack } from "svelte";
  import { invoke } from "@tauri-apps/api/core";
  type Grant = { id: string; fingerprint: string; status: string; scopes: string[]; expires_at: number; idle_expires_at: number };
  type Snapshot = { records: Grant[]; exclusive: boolean; oauth_ready: boolean; available_scopes: string[] };
  let { workspaceId }: { workspaceId: string } = $props();
  let snapshot = $state<Snapshot | null>(null);
  let error = $state("");
  let busy = $state(false);
  let selections = $state<Record<string, string[]>>({});
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
    snapshot = null; error = ""; selections = {}; busy = false;
    let disposed = false; let refreshing = false;
    const refresh = async () => {
      if (disposed || refreshing || busy) return;
      refreshing = true; const version = mutation;
      try { const value = await call(id, "status"); if (!disposed && generation === current && !busy && version === mutation) { snapshot = value; error = ""; } }
      catch (e) { if (!disposed && generation === current) error = String(e); }
      finally { refreshing = false; }
    };
    untrack(() => void refresh()); const timer = setInterval(() => void refresh(), 2500);
    return () => { disposed = true; clearInterval(timer); };
  });
  async function act(action: string, extra: Record<string, unknown> = {}) {
    if (busy) return;
    const id = workspaceId, current = generation; ++mutation; busy = true; error = "";
    try { const value = await call(id, action, extra); if (generation === current) snapshot = value; }
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
    <div><h3 id="chat-authorization-heading">ChatGPT 聊天授权</h3>
      <p>OAuth 连接不等于当前聊天获准。核对聊天返回的指纹后，在本机批准；不要将密码或令牌发送到聊天。</p></div>
    <button type="button" class="tx-btn-secondary" disabled={busy || !snapshot} onclick={() => void act("revoke_all")}>撤销全部</button>
  </div>
  {#if error}<p role="alert">{error}</p>{/if}
  {#if snapshot}
    {#if !snapshot.oauth_ready}<p role="alert">当前未启用 OAuth。所有网络业务调用将被拒绝，请先配置 OAuth；旧 Actions 不支持聊天授权。</p>{/if}
    <label class="exclusive"><input type="checkbox" checked={snapshot.exclusive} disabled={busy}
      onchange={(e) => void act("exclusive", { exclusive: e.currentTarget.checked })} />独占聊天模式（开启会撤销现有授权）</label>
    <p>待审批 90 秒；空闲 30 分钟失效；最长 8 小时。应用重启后重新审批。撤销不回滚已执行操作，运行中任务请在异步任务面板取消。</p>
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
            <div class="controls">
              <button type="button" class="tx-btn-secondary" disabled={busy} onclick={() => void act("deny", { requestId: grant.id })}>拒绝</button>
              <button type="button" class="tx-btn-primary" disabled={busy || !snapshot.oauth_ready || (selections[grant.id] ?? grant.scopes).length === 0}
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
  .chat-authorization { margin-top: 1rem; padding: 1rem; border: 1px solid var(--color-border); border-radius: 12px; background: var(--card-bg); }
  h3 { font-size: 0.95rem; font-weight: 600; } p { font-size: 0.78rem; color: var(--color-text-muted); line-height: 1.6; margin: 0.45rem 0; }
  .heading { display: flex; align-items: center; justify-content: space-between; gap: 1rem; flex-wrap: wrap; }
  .exclusive, fieldset label { display: flex; align-items: center; gap: 0.5rem; font-size: 0.8rem; padding: 0.45rem 0; }
  fieldset { border: 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 0 0.8rem; margin: 0.6rem 0; }
  legend { font-size: 0.8rem; } .records { display: grid; gap: 0.7rem; } article { border: 1px solid var(--color-border); border-radius: 8px; padding: 0.8rem; }
  .controls { display: flex; gap: 0.7rem; } button { min-height: 44px; } code { overflow-wrap: anywhere; } input { flex-shrink: 0; }
</style>
