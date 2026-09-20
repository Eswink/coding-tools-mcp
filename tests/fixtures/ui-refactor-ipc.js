/* SYNTHETIC IPC ONLY. Loaded by the browser test before the actual production app.
 * Never bundled into src/, never uses a real service or credential. */
/** @typedef {{ workspaceId:string, workspaceName:string, exclusive:boolean,
 * grant:{id:string,fingerprint:string,status:string,scopes:string[],created_at:number,expires_at:number,idle_expires_at:number} }} PendingRow */
/** @typedef {{workspaces:import('../../src/lib/types').WorkspaceProfile[], profiles:import('../../src/lib/api/settings').FrpProfileDto[],
 * software:import('../../src/lib/api/software').SoftwareStatus[], proxy:import('../../src/lib/api/settings').ProxyConfigDto,
 * download:import('../../src/lib/api/software').DownloadConfig, calls:{command:string,args:Record<string,any>}[], unknown:string[],
 * pending:PendingRow[],revision:number,confirmation:boolean,healthFailure:boolean,
 * runtime:Record<'mcp'|'actions',import('../../src/lib/types').RuntimeState>,secrets:Record<string,string>}} FixtureState */
(() => {
  /** @template T @param {T} value @returns {T} */
  const clone = value => structuredClone(value);
  const policy = {exclusive:true,access_token_ttl_seconds:3600,refresh_session_ttl_seconds:2592000,chat_lease_ttl_seconds:86400,chat_idle_timeout_seconds:0,new_chat_admission:'review'};
  /** @type {import('../../src/lib/types').WorkspaceProfile} */
  const profile = {id:'fixture-workspace',name:'research-system',path:'D:\\research-system',
    tunnel:{type:'frp',public_url:'https://research.example.test',frp_server:'frp.example.test',frp_subdomain:'research',frp_server_port:7000,frp_profile_id:'fixture-frp',cloudflare_mode:'quick',cloudflare_http2:true,use_proxy:true},
    auth:{type:'oauth',oauth_client_id:'synthetic-client',oauth_redirect_uri:'https://chatgpt.com/connector_platform_oauth_redirect',use_shared_secrets:false,session_policy:policy},
    runtime:{local_port:28766,tool_profile:'default',permission_mode:'trusted',max_task_timeout_ms:86400000,allowed_commands:'python,python3,node,npm,git',workspace_local_entries:true,workspace_script_extensions:'.exe,.bat,.cmd,.ps1'},
    actions:{public_url:'https://actions.example.test',tunnel_type:'frp',frp_server:'frp.example.test',frp_subdomain:'actions',frp_server_port:7000,frp_profile_id:'fixture-frp',cloudflare_mode:'quick',local_port:8787,permission_mode:'trusted',auth_type:'oauth',oauth_client_id:'synthetic-actions-client',oauth_scopes:'mcp',use_shared_secrets:false,max_task_timeout_ms:86400000}};
  /** @type {FixtureState} */
  const state = {workspaces:[profile],profiles:[{id:'fixture-frp',name:'默认配置',server:'frp.example.test',serverPort:7000,hasToken:true}],
    software:[{kind:'frpc',name:'FRP 客户端',installed:true,path:'D:\\Tools\\frpc.exe',managed:true},
      {kind:'cloudflared',name:'Cloudflare Tunnel',installed:false,path:'',managed:false}],
    proxy:{mode:'none',url:''},download:{githubMirror:'',proxyMode:'none',proxyUrl:''},
    calls:[],unknown:[],pending:[],revision:1,confirmation:false,healthFailure:false,
    runtime:{mcp:'running',actions:'stopped'},secrets:Object.create(null)};
  let serial=0;
  let admissionArmed=false;
  let admissionExpiresAt=null;
  let admissionArmed=false;
  let admissionExpiresAt=null;
  /** @type {Map<number,(value:unknown)=>void>} */
  const callbacks=new Map();
  /** @type {Map<number,{event:string,handler:number,id:number}>} */
  const listeners=new Map();
  /** @param {string} event */
  const emit = event => {for(const entry of listeners.values())if(entry.event===event)callbacks.get(entry.handler)?.({event,id:entry.id,payload:{}});};
  /** @param {string} key */
  const secret = key => key==='oauth_client_id'?'synthetic-client':`SYNTHETIC_SECRET_${key}_NOT_REAL`;
  // Dynamic IPC arguments are a transport fixture boundary. Domain outputs below
  // are checked against actual application types and exercised by contract tests.
  /** @param {string} command @param {Record<string,any>} args @returns {Promise<unknown>} */
  async function invoke(command,args={}) {
    // Match the JSON IPC boundary for these plain configuration payloads.
    // structuredClone rejects Svelte's nested reactive proxies, unlike native
    // Tauri JSON serialization, and wrongly accepts circular arguments.
    args = JSON.parse(JSON.stringify(args));
    state.calls.push({command,args:clone(args)});
    if(command==='plugin:event|listen'){const id=++serial;listeners.set(id,{event:String(args.event),handler:Number(args.handler),id});return id;}
    if(command==='plugin:event|unlisten'){listeners.delete(args.eventId);return;}
    if(command==='plugin:window|is_minimized')return false;
    if(command==='plugin:window|is_focused')return true;
    if(command==='plugin:window|theme')return 'light';
    if(command==='plugin:dialog|message'){
      if(args.buttons && typeof args.buttons==='object')return state.confirmation?args.buttons.OkCancelCustom?.[0]??args.buttons.OkCustom??'Ok':args.buttons.OkCancelCustom?.[1]??'Cancel';
      return args.buttons==='YesNo'?(state.confirmation?'Yes':'No'):(state.confirmation?'Ok':'Cancel');
    }
    if(command==='plugin:dialog|open')return null;
    if(command==='list_workspaces')return clone(state.workspaces);
    if(command==='get_last_workspace_id')return 'fixture-workspace';
    if(command==='set_last_workspace'||command==='open_workspace_directory'||command==='open_url')return;
    if(command==='list_frp_profiles')return clone(state.profiles);
    if(command==='save_frp_profile'){
      const value={...args.profile,id:args.profile.id||'new-fixture-frp',hasToken:!!args.token||state.profiles.find(p=>p.id===args.profile.id)?.hasToken||false};
      state.profiles=[...state.profiles.filter(p=>p.id!==value.id),value];return clone(value);
    }
    if(command==='delete_frp_profile'){state.profiles=state.profiles.filter(p=>p.id!==args.id);return;}
    if(command==='update_workspace'){state.workspaces=state.workspaces.map(p=>p.id===args.profile.id?clone(args.profile):p);return;}
    if(command==='get_runtime_status'||command==='get_actions_runtime_status'){
      const mcp=command==='get_runtime_status',running=state.runtime[mcp?'mcp':'actions']==='running';
      return {state:state.runtime[mcp?'mcp':'actions'],pid:running?123:null,localMessage:'',publicMessage:'',
        localEndpoint:mcp?'http://127.0.0.1:28766/mcp':'http://127.0.0.1:8787/openapi.json',
        publicEndpoint:running?(mcp?'https://research.example.test/mcp':'https://active-actions.example.test/openapi.json'):''};
    }
    if(['start_runtime','stop_runtime','start_actions_runtime','stop_actions_runtime'].includes(command)){
      const mcp=!command.includes('actions');state.runtime[mcp?'mcp':'actions']=command.startsWith('start')?'running':'stopped';
      return invoke(mcp?'get_runtime_status':'get_actions_runtime_status',args);
    }
    if(command==='get_shared_secret'||command==='get_workspace_secret')return state.secrets[args.key]??secret(args.key);
    if(command==='set_shared_secret'||command==='set_workspace_secret'){state.secrets[args.key]=args.value;return;}
    if(command==='regenerate_shared_secret'||command==='regenerate_workspace_secret'){state.secrets[args.key]=`${secret(args.key)}_ROTATED`;return state.secrets[args.key];}
    if(command==='get_proxy')return clone(state.proxy);
    if(command==='set_proxy'){state.proxy=clone(args.proxy);return;}
    if(command==='get_download_config')return clone(state.download);
    if(command==='set_download_config'){state.download=clone(args.config);return;}
    if(command==='list_software')return clone(state.software);
    if(command==='install_software'||command==='uninstall_software'){
      const item=state.software.find(s=>s.kind===args.kind);if(!item)throw Error('Unknown synthetic software kind');item.installed=command==='install_software';item.managed=item.installed;return clone(item);
    }
    if(command==='check_app_update')return {currentVersion:'0.4.0',latestVersion:'0.4.0',latestTag:'v0.4.0',updateAvailable:false,releaseUrl:'https://example.test/release'};
    if(command==='get_webview_memory_sample')return {supported:true,mainMb:48,webviewMb:126,webviewProcessCount:3};
    if(command==='run_health_checks'){
      if(state.healthFailure)throw Error('SYNTHETIC_HEALTH_FAILURE');
      return [{label:'本地 MCP（示例检查）',ok:true,detail:'fixture HTTP 200',hint:''},{label:'公网 OAuth（示例检查）',ok:false,detail:'fixture HTTP 404',hint:'合成测试：入口路由错误。'}];
    }
    if(command==='read_workspace_logs'){
      /** @type {import('../../src/lib/api/logs').LogChunk[]} */
      const logs=[{name:'synthetic.log',content:'Synthetic log — no real process was started.'}];
      return logs;
    }
    if(command==='chat_authorization_inbox')return {revision:state.revision,now:Date.now()/1000,pending:clone(state.pending)};
    if(command==='chat_authorization_control'){
      if(args.action==='approve'||args.action==='deny'){
        state.pending=state.pending.filter(r=>r.grant.id!==args.requestId);state.revision++;emit('chat-authorization-changed');
      }
      if(args.action==='arm_new_chat'){admissionArmed=true;admissionExpiresAt=Math.floor(Date.now()/1000)+90;}
      if(args.action==='disarm_new_chat'){admissionArmed=false;admissionExpiresAt=null;}
      return {records:[],exclusive:true,oauth_ready:true,available_scopes:['files.read','files.write','exec.run'],lease_state:'free',
        policy:clone(policy),admission:{mode:policy.new_chat_admission,armed:admissionArmed,expires_at:admissionExpiresAt,single_use:true},
        recovery:{required:false,generation:0}};
    }
    state.unknown.push(command);throw Error(`UNIMPLEMENTED SYNTHETIC IPC: ${command}`);
  }
  Reflect.set(window,'__TAURI_INTERNALS__',{invoke,metadata:{currentWindow:{label:'main'},currentWebview:{label:'main'}},
    /** @param {(value:unknown)=>void} fn @param {boolean} [once] */
    transformCallback:(fn,once=false)=>{const id=++serial;callbacks.set(id,value=>{if(once)callbacks.delete(id);fn(value);});return id;},
    /** @param {number} id */
    unregisterCallback:id=>callbacks.delete(id),convertFileSrc:()=>''});
  Reflect.set(window,'__TAURI_EVENT_PLUGIN_INTERNALS__',{
    /** @param {unknown} _ @param {number} id */
    unregisterListener:(_,id)=>listeners.delete(id)});
  Reflect.set(window,'__UI_FIXTURE__',{state,emit,
    pending:()=>{const now=Date.now()/1000;state.pending=[{workspaceId:profile.id,workspaceName:profile.name,exclusive:true,
      grant:{id:'fixture-pending',fingerprint:'UI-DEMO-ONLY-7E23',status:'pending',scopes:['files.read','exec.run'],created_at:now,expires_at:now+90,idle_expires_at:now+90}}];state.revision++;emit('chat-authorization-open');}});
  addEventListener('DOMContentLoaded',()=>{
    const banner=document.createElement('div');banner.id='synthetic-ui-label';banner.textContent='UI 预览 · 合成数据 / 模拟 IPC · 非原生验收';
    Object.assign(banner.style,{position:'fixed',bottom:'0',left:'0',right:'0',height:'20px',font:'11px sans-serif',textAlign:'center',background:'#fff4da',color:'#553800',zIndex:'10020',pointerEvents:'none'});document.body.append(banner);
  });
})();
