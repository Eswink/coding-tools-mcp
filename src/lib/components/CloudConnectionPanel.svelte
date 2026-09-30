<script lang="ts">
  import { untrack } from 'svelte';
  import { invoke } from '@tauri-apps/api/core';
  import { confirm, open } from '@tauri-apps/plugin-dialog';
  import { canStartCloud, cloudPhaseLabels, createCloudConnectionController, type CloudView } from '$lib/cloud-connection';
  let { workspaceId }: { workspaceId: string } = $props();
  let view = $state<CloudView>({ status: null, busy: false, error: '', uncertain: false });
  let controller: ReturnType<typeof createCloudConnectionController> | undefined;
  $effect(() => {
    const id = workspaceId;
    view = { status: null, busy: false, error: '', uncertain: false };
    const current = createCloudConnectionController(id, invoke, next => { view = next; });
    controller = current;
    untrack(() => void current.refresh());
    const timer = setInterval(() => void current.refresh(), 2500);
    return () => { current.dispose(); clearInterval(timer); if (controller === current) controller = undefined; };
  });
  const confirmations = {
    import: '为当前工作区导入云连接配置和签名私钥？这会保存持久连接身份，但不会连接或授权聊天。请选择可信配置文件；私钥仅由本机读取。',
    start: '启动此工作区的出站云连接？连接后仍需在本机核对指纹并批准聊天。不会初始化或修复日志。',
    initialize: '仅限首次安装：创建一次性安全日志并启动云连接？已有日志不会覆盖。若日志丢失、损坏或执行状态不明，请取消并先完成本机恢复核查。',
    stop: '停止此工作区云连接？已发生的操作不会回滚；正在执行的任务可能仍需在本机核实和终止。'
  };
  async function selectFiles(stillActive: () => boolean) {
    const configPath = await open({ title: '选择云连接配置 JSON', multiple: false, directory: false, filters: [{ name: 'JSON', extensions: ['json'] }] });
    if (!stillActive() || typeof configPath !== 'string') return null;
    const privateKeyPath = await open({ title: '选择本机签名私钥 JSON', multiple: false, directory: false, filters: [{ name: 'JSON', extensions: ['json'] }] });
    return typeof privateKeyPath === 'string' ? { configPath, privateKeyPath } : null;
  }
  function act(kind: keyof typeof confirmations) {
    void controller?.operate(kind, () => confirm(confirmations[kind], { title: '本机云连接确认', kind: 'warning', okLabel: '确认继续', cancelLabel: '取消' }), selectFiles);
  }
</script>
<section class="cloud-connection" aria-labelledby="cloud-connection-heading">
  <h3 id="cloud-connection-heading">云连接</h3>
  <p>出站连接与本机执行授权分别管理。云端、模型和 OAuth 不能批准本机权限。</p>
  <p role="status" aria-live="polite">{view.status ? cloudPhaseLabels[view.status.phase] : '连接状态尚未确认'}{view.busy ? ' · 正在处理本机操作' : ''}</p>
  {#if view.status}<p>传输连接：{view.status.connected ? '在线' : '离线'}。聊天批准、撤销和暂停仍以本机控制为准。</p>{/if}
  {#if view.error}<p role="alert">{view.error}</p>{/if}
  {#if view.uncertain}<p role="alert">上次操作结果不确定：启动、初始化和导入已锁定。刷新只读取状态，不会重复提交。</p>{/if}
  {#if view.status?.phase === 'draining'}<p>旧会话正在排空。请在本机检查未完成操作，不要让新聊天接管。</p>{/if}
  {#if view.status?.phase === 'recovery'}<p>需要本机恢复核查。初始化不能修复未知执行结果或替代恢复流程。</p>{/if}
  {#if view.status?.phase === 'pending_approval'}<p>请在下方或本机审批提示中核对聊天指纹后批准。</p>{/if}
  <div class="controls">
    <button type="button" class="tx-btn-secondary" disabled={view.busy} onclick={() => void controller?.refresh()}>刷新连接状态</button>
    {#if view.status?.configured === false}<button type="button" class="tx-btn-secondary" disabled={view.busy || view.uncertain} onclick={() => act('import')}>从本机文件导入连接</button>{/if}
    {#if view.status?.configured}
      <button type="button" class="tx-btn-primary" disabled={!canStartCloud(view)} onclick={() => act('start')}>启动云连接</button>
      <button type="button" class="tx-btn-secondary" disabled={!canStartCloud(view)} onclick={() => act('initialize')}>首次初始化并连接</button>
      <button type="button" class="tx-btn-secondary" disabled={view.busy || !view.status} onclick={() => act('stop')}>停止云连接</button>
    {/if}
  </div>
</section>
<style>
  .cloud-connection { margin-top:1rem; padding:20px; border:1px solid var(--color-border); border-radius:var(--card-radius); background:var(--card-bg); }
  h3 { font-size:17px; font-weight:600; } p { font-size:.8rem; color:var(--color-text-muted); line-height:1.6; margin:.5rem 0; }
  .controls { display:flex; flex-wrap:wrap; gap:.7rem; } button { min-height:44px; } [role="alert"] { color:var(--danger); }
</style>
