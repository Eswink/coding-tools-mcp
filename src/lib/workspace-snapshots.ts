export type ManagedSnapshotTarget = { id: string; display_path: string; head: string; detached: boolean; native_profile_id: string | null };
export type WorkspaceSnapshot = { id: string; digest: string; bytes: number; entries: {path:string;directory:boolean;size:number;hash:string;mode:number}[] };
export type SnapshotPlan = {id:string;snapshot_id:string;worktree_id:string;approval_digest:string;current_digest:string;snapshot_digest:string;expires_at:number;changes:{path:string;action:string}[]};
export type SnapshotsView = {targets:ManagedSnapshotTarget[];selected:string;snapshots:WorkspaceSnapshot[];plan:SnapshotPlan|null;busy:boolean;uncertain:boolean;error:string;notice:string};
type Invoke=<T>(command:string,args:Record<string,unknown>)=>Promise<T>;
export function createWorkspaceSnapshotsController(sourceId:string,invoke:Invoke,publish:(view:SnapshotsView)=>void,onRegistered:()=>Promise<void>){
  let alive=true,epoch=0;
  let view:SnapshotsView={targets:[],selected:'',snapshots:[],plan:null,busy:false,uncertain:false,error:'',notice:''};
  const emit=(patch:Partial<SnapshotsView>)=>{if(alive){view={...view,...patch};publish(view)}};
  async function refresh(){
    if(!alive||view.busy)return;const version=++epoch;emit({busy:true,error:''});
    try{const targets=await invoke<ManagedSnapshotTarget[]>('list_managed_workspaces',{sourceId});
      if(alive&&version===epoch){emit({targets});if(view.selected&&!targets.some(t=>t.id===view.selected))emit({selected:'',snapshots:[],plan:null});}
    }catch{if(alive&&version===epoch)emit({error:'无法读取受管工作区。请在本机检查后重试。'});}
    finally{if(alive&&version===epoch)emit({busy:false});}
  }
  async function select(worktreeId:string){
    if(!alive||view.busy)return;const target=view.targets.find(t=>t.id===worktreeId);if(!target)return;
    const version=++epoch;emit({selected:worktreeId,snapshots:[],plan:null,error:'',notice:'',busy:true});
    try{if(target.native_profile_id){const snapshots=await invoke<WorkspaceSnapshot[]>('snapshot_list',{sourceId,worktreeId});if(alive&&version===epoch)emit({snapshots});}}
    catch{if(alive&&version===epoch)emit({error:'无法读取快照。可能需要恢复核查或当前平台尚不支持安全快照。'});}
    finally{if(alive&&version===epoch)emit({busy:false});}
  }
  async function act(action:'register'|'capture'|'plan'|'restore',snapshotId?:string){
    if(!alive||view.busy||view.uncertain)return;
    const target=view.targets.find(t=>t.id===view.selected);if(!target)return;
    if(action!=='register'&&!target.native_profile_id)return;
    if(action==='register'&&target.native_profile_id)return;
    if(action==='plan'&&!view.snapshots.some(s=>s.id===snapshotId))return;
    if(action==='restore'&&(!view.plan||Date.now()/1000>=view.plan.expires_at)){emit({plan:null,error:'恢复预览已过期，请重新预览差异。'});return;}
    const version=++epoch;const worktreeId=target.id;const plan=view.plan;
    emit({busy:true,error:'',notice:'',...(action==='restore'?{}:{plan:null})});
    let submitted=false;
    try{
      if(action==='register'){
        submitted=true;const profile=await invoke<{id:string}|null>('register_managed_workspace',{sourceId,worktreeId});
        if(!alive||version!==epoch)return;
        if(!profile){emit({notice:'已取消注册。'});return;}
        await onRegistered();if(!alive||version!==epoch)return;
        emit({targets:view.targets.map(t=>t.id===worktreeId?{...t,native_profile_id:profile.id}:t),notice:'已注册为独立工作区。尚未启动或授予聊天权限。'});
      }else if(action==='plan'){
        const next=await invoke<SnapshotPlan>('snapshot_plan_restore',{sourceId,worktreeId,snapshotId});
        if(alive&&version===epoch)emit({plan:next});
      }else if(action==='capture'){
        submitted=true;await invoke('snapshot_capture',{sourceId,worktreeId});
        if(!alive||version!==epoch)return;
        const snapshots=await invoke<WorkspaceSnapshot[]>('snapshot_list',{sourceId,worktreeId});
        if(alive&&version===epoch)emit({snapshots,notice:'快照已完成。仅保存允许的工作区内容；不会自动回滚。'});
      }else{
        submitted=true;const result=await invoke<unknown>('snapshot_restore',{sourceId,worktreeId,planId:plan!.id,approvalDigest:plan!.approval_digest});
        if(alive&&version===epoch)emit({plan:null,notice:result===null?'已取消恢复。':'恢复操作已完成。原内容备份仍保留，请核对工作区。'});
      }
    }catch{if(alive&&version===epoch)emit({uncertain:submitted,plan:null,error:submitted?'本机操作未确认成功。不要重复提交。请核查快照、保留备份和恢复锁；已有权限或日志不会被清除。':'无法生成恢复预览。可能存在文件冲突、受保护路径或平台限制。'});}
    finally{if(alive&&version===epoch)emit({busy:false});}
  }
  return{refresh,select,act,dispose(){alive=false;++epoch;}};
}
