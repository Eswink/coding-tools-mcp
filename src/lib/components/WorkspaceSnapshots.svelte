<script lang="ts">
  import { untrack } from 'svelte';
  import { invoke } from '@tauri-apps/api/core';
  import { listWorkspaces } from '$lib/api/workspaces';
  import { workspaces } from '$lib/stores/app';
  import { createWorkspaceSnapshotsController, type SnapshotsView } from '$lib/workspace-snapshots';
  let { sourceId }: { sourceId:string }=$props();
  let view=$state<SnapshotsView>({targets:[],selected:'',snapshots:[],plan:null,busy:false,uncertain:false,error:'',notice:''});
  let controller:ReturnType<typeof createWorkspaceSnapshotsController>|undefined;
  const selected=$derived(view.targets.find(t=>t.id===view.selected));
  $effect(()=>{
    const id=sourceId;
    view={targets:[],selected:'',snapshots:[],plan:null,busy:false,uncertain:false,error:'',notice:''};
    const current=createWorkspaceSnapshotsController(id,invoke,next=>{view=next},async()=>{workspaces.set(await listWorkspaces())});controller=current;
    untrack(()=>void current.refresh());
    return()=>{current.dispose();if(controller===current)controller=undefined;};
  });
</script>
<section class="snapshots" aria-labelledby="snapshot-title">
  <h3 id="snapshot-title">受管工作区快照</h3>
  <p>仅针对已注册的独立受管工作区。不会复制普通任务、回滚原始仓库或清除授权与恢复日志。</p>
  <p>当前安全适配器仅支持 Linux；Windows 快照尚不可用。每次最多 256 项、16 MiB，单文件最多 1 MiB；链接、特殊文件和受保护内容会使整个快照被拒绝。需移动的只读顶层目录会在恢复预览时被拒绝。</p>
  <div class="controls">
    <button class="tx-btn-secondary" type="button" disabled={view.busy} onclick={()=>void controller?.refresh()}>刷新受管工作区</button>
    <label>工作区 <select disabled={view.busy} value={view.selected} onchange={e=>void controller?.select(e.currentTarget.value)}><option value="">请选择受管工作区</option>{#each view.targets as target (target.id)}<option value={target.id}>{target.display_path}</option>{/each}</select></label>
  </div>
  {#if !view.busy&&view.targets.length===0}<p>暂无受管工作区。先通过受管 worktree 流程创建独立工作区。</p>{/if}
  {#if view.error}<p role="alert">{view.error}</p>{/if}
  {#if view.notice}<p role="status">{view.notice}</p>{/if}
  {#if view.uncertain}<p role="alert">为避免重复操作，本面板已锁定修改。先在本机核实结果，再重新打开面板。</p>{/if}
  {#if selected}
    {#if !selected.native_profile_id}
      <p>此受管目录尚未注册为独立的本机工作区。注册不会继承原工作区的聊天权限或云连接。</p>
      <button class="tx-btn-secondary" type="button" disabled={view.busy||view.uncertain} onclick={()=>void controller?.act('register')}>在本机确认并注册独立工作区</button>
    {:else}
      <div class="controls"><a class="tx-btn-secondary" href={`/workspace/${selected.native_profile_id}`}>打开独立工作区</a><button class="tx-btn-primary" type="button" disabled={view.busy||view.uncertain} onclick={()=>void controller?.act('capture')}>创建明确快照</button></div>
      {#if view.snapshots.length===0}<p>暂无可用的完整快照。未完成或损坏的快照不能用于恢复。</p>{/if}
      {#each view.snapshots as snapshot(snapshot.id)}
        <article><p>快照 <code>{snapshot.id}</code> · {snapshot.entries.length} 项 · {snapshot.bytes} 字节</p><button class="tx-btn-secondary" type="button" disabled={view.busy||view.uncertain} onclick={()=>void controller?.act('plan',snapshot.id)}>预览恢复差异</button></article>
      {/each}
    {/if}
  {/if}
  {#if view.plan}
    <article aria-label="恢复差异预览"><h4>恢复前核查</h4><p>此计划绑定当前文件摘要和目标。有效至 {new Date(view.plan.expires_at*1000).toLocaleTimeString()}；文件变化后必须重新预览。</p>
      <p>目标快照：<code>{view.plan.snapshot_id}</code><br />当前内容摘要：<code>{view.plan.current_digest}</code></p>
      <ul>{#each view.plan.changes as change}<li>{change.action==='add'?'新增':change.action==='delete'?'移出并保留备份':'替换并保留备份'}：{change.path}</li>{/each}</ul>
      {#if view.plan.changes.length===0}<p>没有文件差异。</p>{/if}
      <p>下一步仍需本机对话框确认及真实任务排空。外部编辑器不受此锁保护；冲突会阻止恢复，原内容备份保留。不会自动重试、覆盖并发改动或清除恢复锁。</p>
      <button class="tx-btn-secondary" type="button" disabled={view.busy||view.uncertain} onclick={()=>void controller?.act('restore')}>在本机核对并确认恢复</button>
    </article>
  {/if}
</section>
<style>
  .snapshots{margin-top:1rem;padding:20px;border:1px solid var(--color-border);border-radius:var(--card-radius);background:var(--card-bg)}
  h3{font-size:17px;font-weight:600}p,li,label{font-size:.8rem;line-height:1.6;color:var(--color-text-muted)}p{margin:.5rem 0}.controls{display:flex;flex-wrap:wrap;align-items:center;gap:.7rem}button,select,a{min-height:44px}label{display:grid;gap:4px;min-width:0;max-width:100%;flex:1 1 18rem}select{max-width:100%;min-width:0;width:100%}article{border-top:1px solid var(--color-border);margin-top:1rem;padding-top:.7rem}code{overflow-wrap:anywhere}[role="alert"]{color:var(--danger)}ul{padding-left:1.5rem}a{display:inline-flex;align-items:center}
</style>
