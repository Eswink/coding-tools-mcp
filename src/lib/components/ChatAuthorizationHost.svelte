<script lang="ts">
  import { onMount, tick } from "svelte";
  import { invoke } from "@tauri-apps/api/core";
  import { listen } from "@tauri-apps/api/event";
  import { goto } from "$app/navigation";
  import { ApprovalPresentation, canApprove, chatScopeLabels, pendingChats, remainingSeconds, type ChatInbox, type PendingChat } from "$lib/chat-authorization";
  let rows = $state<PendingChat[]>([]);
  let selectedId = $state("");
  let selectedScopes = $state<string[]>([]);
  let verified = $state(false);
  let error = $state("");
  let busy = $state(false);
  let now = $state(Date.now() / 1000);
  let dialog: HTMLDialogElement;
  let serverOffset = 0;
  let disposed = false;
  let inFlight = false;
  let queued = false;
  let forceNext = false;
  let revision = -1;
  const presentation = new ApprovalPresentation();
  const selected = $derived(rows.find(r => r.grant.id === selectedId) ?? null);
  function dismiss() { selectedId = ""; verified = false; if (dialog?.open) dialog.close(); }
  async function display(row: PendingChat) {
    selectedId = row.grant.id; selectedScopes = [...row.grant.scopes]; verified = false;
    await tick(); if (disposed || selectedId !== row.grant.id || !dialog) return;
    if (!dialog.open) dialog.showModal();
    dialog.querySelector<HTMLButtonElement>("[data-close]")?.focus();
  }
  async function refresh(force = false) {
    forceNext ||= force;
    if (disposed) return;
    if (inFlight) { queued = true; return; }
    inFlight = true;
    try {
      const snapshot = await invoke<ChatInbox>("chat_authorization_inbox");
      if (disposed || snapshot.revision < revision) return;
      revision = snapshot.revision; serverOffset = snapshot.now - Date.now() / 1000;
      now = Date.now() / 1000 + serverOffset; rows = pendingChats(snapshot); error = "";
      if (selectedId && !rows.some(r => r.grant.id === selectedId)) dismiss();
      if (!selectedId && !busy) {
        const choice = presentation.choose(rows, !document.hidden && document.hasFocus(), forceNext);
        forceNext = false; if (choice) await display(choice);
      }
    } catch { if (!disposed) { rows = []; dismiss(); error = "本机授权状态读取失败，审批已暂停。请重试。"; } }
    finally { inFlight = false; if (!disposed && queued) { queued = false; void refresh(); } }
  }
  async function decide(approve: boolean) {
    const target = selected; if (!target || busy) return;
    if (approve && !canApprove(target.grant, selectedScopes, verified, now)) return;
    const scopes = [...selectedScopes]; busy = true; error = "";
    try {
      await invoke("chat_authorization_control", { id: target.workspaceId, action: approve ? "approve" : "deny",
        requestId: target.grant.id, scopes: approve ? scopes : null, exclusive: null });
      if (!disposed) { dismiss(); await refresh(); }
    } catch (e) { if (!disposed) error = String(e); }
    finally { if (!disposed) busy = false; }
  }
  async function locate(row: PendingChat) { await goto(`/workspace/${encodeURIComponent(row.workspaceId)}`); }
  onMount(() => {
    disposed = false;
    const removers: (() => void)[] = [];
    const register = async (name: string, cb: () => void) => {
      const remove = await listen(name, cb); if (disposed) remove(); else removers.push(remove);
    };
    void (async () => {
      try {
        await Promise.all([
          register("chat-authorization-changed", () => void refresh()),
          register("chat-authorization-open", () => void refresh(true)),
          register("chat-authorization-unavailable", () => void refresh()),
        ]);
        await refresh();
      } catch { if (!disposed) error = "授权事件连接失败；保留定时核验，请打开工作区检查。"; }
    })();
    const focus = () => void refresh();
    window.addEventListener("focus", focus);
    const timer = setInterval(() => { now = Date.now() / 1000 + serverOffset; }, 250);
    const fallback = setInterval(() => { if (!document.hidden) void refresh(); }, 5000);
    return () => { disposed = true; clearInterval(timer); clearInterval(fallback); window.removeEventListener("focus", focus); for (const remove of removers) remove(); };
  });
</script>

{#if rows.length > 0}
  <button type="button" class="approval-inbox tx-btn-primary" onclick={() => void refresh(true)}>待审批聊天 · {rows.length}</button>
{/if}
{#if error && !selected}<div class="approval-error" role="alert">{error}<button type="button" onclick={() => void refresh(true)}>重试</button></div>{/if}
<dialog bind:this={dialog} class="approval-dialog" aria-labelledby="global-approval-title" oncancel={(e) => { e.preventDefault(); dismiss(); }}>
  {#if selected}
    <header><div><p>本机安全确认</p><h2 id="global-approval-title">ChatGPT 请求访问工作区</h2></div><button data-close type="button" aria-label="暂不处理" disabled={busy} onclick={dismiss}>关闭</button></header>
    <p class="workspace-name">{selected.workspaceName}</p>
    <p>会话指纹 <code>{selected.grant.fingerprint}</code></p>
    <p class="countdown" aria-live="off">剩余 {remainingSeconds(selected.grant, now)} 秒</p>
    <p>{selected.exclusive ? "批准后，此聊天将独占当前工作区。其他聊天不能申请或使用，也不会触发新审批。" : "当前为共享模式。不同聊天仍共享真实工作区文件。"}</p>
    <fieldset disabled={busy}><legend>批准权限（可缩减，不能扩大）</legend>
      {#each selected.grant.scopes as scope}<label><input type="checkbox" value={scope} bind:group={selectedScopes} />{chatScopeLabels[scope] ?? scope}</label>{/each}
    </fieldset>
    <label class="verify"><input type="checkbox" bind:checked={verified} disabled={busy} />我已核对当前聊天返回的会话指纹和上述权限</label>
    {#if error}<p role="alert">{error}</p>{/if}
    <footer><button type="button" class="tx-btn-secondary" onclick={() => selected && void locate(selected)}>定位工作区</button><button type="button" class="tx-btn-secondary" disabled={busy} onclick={() => void decide(false)}>拒绝</button><button type="button" class="tx-btn-primary" disabled={busy || !canApprove(selected.grant, selectedScopes, verified, now)} onclick={() => void decide(true)}>{selected.exclusive ? "批准并独占" : "批准此聊天"}</button></footer>
  {/if}
</dialog>
<style>
  .approval-inbox {position:fixed;right:1.5rem;bottom:1.5rem;z-index:45;min-height:44px;box-shadow:0 8px 28px #0002;}
  .approval-error {position:fixed;right:1rem;bottom:1rem;padding:1rem;background:var(--card-bg);border:1px solid var(--danger);z-index:46;max-width:32rem;}
  .approval-dialog {width:min(620px,calc(100vw - 2rem));max-height:calc(100vh - 3rem);margin:auto;padding:1.5rem;background:var(--card-bg);color:var(--color-text);border:1px solid var(--color-border);border-radius:16px;box-shadow:0 24px 80px #0005;}
  .approval-dialog::backdrop {background:#0007;backdrop-filter:blur(3px);}
  header,footer {display:flex;align-items:center;justify-content:space-between;gap:.75rem;flex-wrap:wrap;}
  h2 {font-size:1.2rem;font-weight:650;}p {margin:.65rem 0;font-size:.9rem;line-height:1.55;overflow-wrap:anywhere;}.workspace-name {font-size:1.05rem;font-weight:600;}.countdown {font-variant-numeric:tabular-nums;}
  code {font-size:1rem;letter-spacing:.04em;}fieldset {display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:.65rem;border:1px solid var(--color-border);padding:1rem;margin:1rem 0;border-radius:10px;}legend {font-size:.85rem;}label {display:flex;align-items:center;gap:.6rem;font-size:.85rem;}input {flex-shrink:0;}.verify {padding:.75rem 0;}footer {margin-top:1rem;}button {min-height:44px;}[role=alert]{color:var(--danger);}
</style>
