<script lang="ts">
  import { invoke } from '@tauri-apps/api/core';
  import { untrack } from 'svelte';
  import { createHookController, emptyHookView } from '$lib/policy-hooks';
  let { workspaceId }: { workspaceId: string } = $props();
  let view = $state(emptyHookView());
  let manifest = $state('');
  let reviewed = $state(false);
  let controller: ReturnType<typeof createHookController> | undefined;
  $effect(() => {
    const id = workspaceId;
    view = emptyHookView(); manifest = ''; reviewed = false;
    const current = createHookController(id, invoke, value => { view = value; if (!value.pending) reviewed = false; });
    controller = current;
    untrack(() => void current.refresh());
    return () => { current.dispose(); if (controller === current) controller = undefined; };
  });
  function edit() { reviewed = false; if (view.pending) controller?.discard(); }
</script>

<section class="hooks-panel" aria-labelledby="policy-hooks-heading">
  <h3 id="policy-hooks-heading">本机策略 Hooks</h3>
  <p>默认关闭，仅当前运行期有效。清单批准不授予聊天权限；每次执行仍检查本机授权、命令策略和沙箱，禁止网络访问。</p>
  <p role="status" aria-live="polite">{view.status ? (view.status.enabled ? `已启用 · ${view.status.count ?? '数量待确认'} 项` : '已停用') : '状态尚未确认'}{view.busy ? ' · 正在处理' : ''}</p>
  {#if view.status?.recovery_required}<p role="alert">未知执行结果仍被锁定。请在本机完成恢复核查；停用不会解除此锁定。</p>{/if}
  {#if view.uncertain}<p role="alert">上次操作结果不确定。预览和批准已锁定；刷新只读取状态，不会重新提交。</p>{/if}
  {#if view.error}<p role="alert">{view.error}</p>{/if}
  {#if view.notice}<p role="status">{view.notice}</p>{/if}
  <div class="controls">
    <button class="tx-btn-secondary" type="button" disabled={view.busy} onclick={() => void controller?.refresh()}>刷新 Hooks 状态</button>
    <button class="tx-btn-secondary" type="button" disabled={view.busy || !view.status} onclick={() => void controller?.disable()}>停用全部 Hooks</button>
  </div>
  <details>
    <summary>查看或设置本机 Hooks 清单</summary>
    <p id="hooks-manifest-help">输入 JSON 数组，最多 8 项、8 KiB。必填 id、event（before_tool / after_tool）、tool（exec_command / start_exec_task）和 executable（本机绝对路径）。可选 args、cwd、script、timeout_ms 和 workspace_write。脚本应位于当前工作区；写入权限需明确批准。</p>
    <label for="hooks-manifest">Hooks JSON 清单</label>
    <textarea id="hooks-manifest" aria-describedby="hooks-manifest-help" rows="6" spellcheck="false" disabled={view.busy || view.uncertain} bind:value={manifest} oninput={edit} placeholder="[]"></textarea>
    <button class="tx-btn-secondary" type="button" disabled={view.busy || view.uncertain || !view.status || view.status.recovery_required || !manifest.trim()} onclick={() => { reviewed = false; void controller?.prepare(manifest); }}>生成本机预览</button>
    {#if view.pending}
      <div class="preview" aria-label="本机 Hooks 精确预览">
        <h4>核对本次执行清单</h4>
        <p>预览最多 60 秒有效。以下脚本文本只显示在本机，不写入日志。点击批准后仍需完成系统原生确认。</p>
        <p class="digest">清单 SHA256：{view.pending.preview.digest}</p>
        {#each view.pending.preview.hooks as hook, index}
          <h5>Hook {index + 1}</h5>
          <pre aria-label={`Hook ${index + 1} 清单`}>{JSON.stringify(hook.manifest, null, 2)}</pre>
          <p class="digest">可执行文件 SHA256：{hook.executable_sha256}</p>
          {#if hook.script_source !== null}
            <p class="digest">脚本 SHA256：{hook.script_sha256}</p>
            <pre aria-label={`Hook ${index + 1} 完整脚本`}>{hook.script_source}</pre>
          {/if}
        {/each}
        <label class="review"><input type="checkbox" bind:checked={reviewed} disabled={view.busy} />我已核对全部命令、参数、脚本内容及写入权限</label>
        <div class="controls">
          <button class="tx-btn-primary" type="button" disabled={view.busy || !reviewed || view.uncertain} onclick={() => void controller?.approve(reviewed)}>在本机确认批准</button>
          <button class="tx-btn-secondary" type="button" disabled={view.busy} onclick={() => controller?.discard()}>放弃本次预览</button>
        </div>
      </div>
    {/if}
  </details>
</section>

<style>
  .hooks-panel { margin-top:1rem; padding:20px; border:1px solid var(--color-border); border-radius:var(--card-radius); background:var(--card-bg); min-width:0; }
  h3 { font-size:17px; font-weight:600; } h4,h5 { margin:.8rem 0; font-weight:600; }
  p { font-size:.8rem; color:var(--color-text-muted); line-height:1.6; margin:.5rem 0; }
  .controls { display:flex; flex-wrap:wrap; gap:.7rem; margin:.7rem 0; } button,summary { min-height:44px; }
  summary { display:flex; align-items:center; cursor:pointer; font-size:.9rem; } label { display:block; font-size:.85rem; margin:.6rem 0; }
  textarea,pre { box-sizing:border-box; width:100%; max-width:100%; font-family:var(--font-mono,monospace); font-size:.8rem; border:1px solid var(--color-border); border-radius:8px; padding:12px; background:var(--card-bg); color:var(--color-text); }
  textarea { resize:vertical; min-height:140px; } pre { max-height:320px; overflow:auto; white-space:pre-wrap; overflow-wrap:anywhere; }
  .digest { overflow-wrap:anywhere; font-family:var(--font-mono,monospace); } .review { display:flex; align-items:flex-start; gap:.6rem; line-height:1.6; } .review input { margin-top:.3rem; }
  .preview { border-top:1px solid var(--color-border); margin-top:1rem; padding-top:.5rem; } [role="alert"] { color:var(--danger); }
  @media (max-width:600px) { .hooks-panel { padding:14px; } .controls { flex-direction:column; } button { width:100%; } }
</style>
