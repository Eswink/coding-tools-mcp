import os from 'node:os'; import fs from 'node:fs'; import path from 'node:path'; import {createRequire} from 'node:module';
const root=path.resolve(process.env.PROJECT_ROOT ?? process.cwd());
const out=path.resolve(process.env.TASK_PANEL_TEST_DIR ?? fs.mkdtempSync(path.join(os.tmpdir(),'task-panel-')));
fs.mkdirSync(out,{recursive:true});
const req=createRequire(path.join(root,'package.json'));
const {build}=req('esbuild'); const {compile}=req('svelte/compiler');
fs.writeFileSync(path.join(out,'测试容器v3.svelte'), `<script>import Panel from ${JSON.stringify(path.join(root,'src/lib/components/异步任务面板v2.svelte'))};let workspaceId=$state('one');let channel=$state('mcp');window.changeView=(id,c)=>{workspaceId=id;channel=c;};</script><Panel {workspaceId} {channel} maxTimeoutMs={1800000} onBudgetSave={async(ms)=>{window.saved.push(ms);}} />`);
fs.writeFileSync(path.join(out,'测试接口v3.js'), `export const listTasks=(...a)=>window.mockApi.list(...a);export const getTask=(...a)=>window.mockApi.get(...a);export const cancelTask=(...a)=>window.mockApi.cancel(...a);`);
fs.writeFileSync(path.join(out,'对话框v3.js'), `export async function confirm(...args){window.confirmations.push(args);return window.approve;}`);
fs.writeFileSync(path.join(out,'测试入口v3.js'), `import{mount}from'svelte';import Harness from'./测试容器v3.svelte';
window.saved=[];window.cancelled=[];window.confirmations=[];window.approve=true;window.holdJob='';window.delayed=[];window.maxInFlight=0;window.inFlight=0;window.calls=[];window.errors=[];
window.jobStates={A:'running',B:'interrupted'};
function summary(w,c,j){return{job_id:j,request_id:w+'/'+c+'/'+j,status:window.jobStates[j],terminal:window.jobStates[j]!=='running',created_at:1,elapsed_ms:1000,execution_timeout_ms:60000,cancel_requested:false,restart_recoverable:true,persistence_failed:false,result:{exit_code:null,process_may_be_running:j==='B'}};}
function page(text,cursor){const b=new TextEncoder().encode(text);const tail=b.slice(cursor);return{data_base64:btoa(String.fromCharCode(...tail)),requested_cursor:cursor,cursor,next_cursor:b.length,dropped_bytes:0,has_more:false};}
window.mockApi={async list(w,c){window.calls.push(['list',w,c]);return{jobs:['A','B'].map(j=>summary(w,c,j))};},async get(w,c,j,o,e){window.calls.push(['get',w,c,j,o,e]);window.inFlight++;window.maxInFlight=Math.max(window.maxInFlight,window.inFlight);try{if(window.holdJob===j)await new Promise(r=>window.delayed.push(r));return{...summary(w,c,j),stdout:page(w+'/'+c+'/'+j+'中文🙂',o),stderr:page('stderr',e)};}finally{window.inFlight--;}},async cancel(w,c,j,confirmed){window.cancelled.push([w,c,j,confirmed]);window.jobStates[j]='cancelled';return summary(w,c,j);}};
window.releaseHeld=()=>{window.holdJob='';for(const release of window.delayed.splice(0))release();};
mount(Harness,{target:document.getElementById('app')});`);
await build({entryPoints:[path.join(out,'测试入口v3.js')],outfile:path.join(out,'面板测试v3.js'),bundle:true,format:'iife',platform:'browser',conditions:['browser'],nodePaths:[path.join(root,'node_modules')],plugins:[{name:'svelte',setup(b){b.onResolve({filter:/^\$lib\/api\/异步任务v2$/},()=>({path:path.join(out,'测试接口v3.js')}));b.onResolve({filter:/^@tauri-apps\/plugin-dialog$/},()=>({path:path.join(out,'对话框v3.js')}));b.onResolve({filter:/^\$lib\//},a=>({path:path.join(root,'src/lib',a.path.slice(5)+'.ts')}));b.onLoad({filter:/\.svelte$/},a=>({contents:compile(fs.readFileSync(a.path,'utf8'),{filename:a.path,generate:'client',dev:true}).js.code,loader:'js',resolveDir:path.dirname(a.path)}));}}]});
fs.writeFileSync(path.join(out,'面板测试v3.html'), '<meta charset="utf-8"><div id="app"></div><script src="面板测试v3.js"></script>');
console.log('production TaskPanel compiled with mock transport and dialog only');
