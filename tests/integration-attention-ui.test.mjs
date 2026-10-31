// A1 C9-2: one list_pending_integrations per profile load and the local-only
// clear_integration_attention flow (SPEC-A1 §0.9 nit 1).
import test from 'node:test';import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';import ts from 'typescript';
const source=readFileSync(new URL('../src/lib/integration-attention.ts',import.meta.url),'utf8');
const code=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022}}).outputText;
const {createIntegrationAttentionController,needsAttention}=await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
const ID='workspace-1';
const first={recovery:{state:'needs_attention',from:'rolling_back',files_restored:0,rows:[{path:'m.txt',row:3}]},pending:[]};
const sticky={recovery:{state:'none',journal:'needs_attention'},pending:[]};
const idle={recovery:{state:'none',journal:'none'},pending:[]};
const cleared={integration_id:'b'.repeat(32),state:'none',entries_discarded:3,workspace_files_written:false};
function deferred(){let resolve;const promise=new Promise(r=>{resolve=r});return{promise,resolve}}
function setup(reply=async cmd=>cmd==='list_pending_integrations'?sticky:cleared){
  const s={calls:[],views:[],view:undefined};
  s.controller=createIntegrationAttentionController(ID,async(command,args)=>{s.calls.push({command,args});return reply(command,args)},v=>{s.view=v;s.views.push(v)});
  return s;
}
const commands=s=>s.calls.map(c=>c.command);

test('needs_attention is read from both recovery shapes and nothing else',()=>{
  assert.equal(needsAttention(first),true);assert.equal(needsAttention(sticky),true);
  assert.equal(needsAttention(idle),false);assert.equal(needsAttention({recovery:{state:'recovered'},pending:[]}),false);
  assert.equal(needsAttention({ok:false,error:{code:'INTEGRATE_BUSY'},recovery:{state:'needs_attention'}}),false);
  assert.equal(needsAttention(null),false);
});
test('a profile load calls list_pending_integrations exactly once with the profile id',async()=>{
  const s=setup();await s.controller.load();await s.controller.load();
  assert.deepEqual(s.calls,[{command:'list_pending_integrations',args:{id:ID}}]);
  assert.equal(s.view.attention,true);
});
test('an idle journal or a failed scan shows nothing and never clears',async()=>{
  for(const reply of [async()=>idle,async()=>({ok:false,error:{code:'STORE_UNAVAILABLE',message:'SECRET_PATH'}}),async()=>{throw Error('SECRET_PATH')}]){
    const s=setup(reply);await s.controller.load();await s.controller.clear();
    assert.deepEqual(commands(s),['list_pending_integrations']);
    assert.equal(s.view?.attention??false,false);assert.equal(s.view?.error??'','');
    assert.doesNotMatch(JSON.stringify(s.views),/SECRET_PATH/);
  }
});
test('clear passes only the profile id and an approval hides the notice',async()=>{
  const s=setup();await s.controller.load();await s.controller.clear();
  assert.deepEqual(s.calls.at(-1),{command:'clear_integration_attention',args:{id:ID}});
  assert.equal(s.view.attention,false);assert.match(s.view.notice,/未写入任何工作区文件/);
  await s.controller.clear();
  assert.deepEqual(commands(s),['list_pending_integrations','clear_integration_attention']);
});
test('an owner cancel keeps the attention notice and changes nothing',async()=>{
  const s=setup(async cmd=>cmd==='list_pending_integrations'?first:null);await s.controller.load();await s.controller.clear();
  assert.equal(s.view.attention,true);assert.match(s.view.notice,/已取消/);assert.equal(s.view.busy,false);
});
test('a journal that no longer needs attention hides the button; other refusals keep it',async()=>{
  const gone=setup(async cmd=>cmd==='list_pending_integrations'?sticky:{ok:false,error:{code:'WORKER_STATE'}});
  await gone.controller.load();await gone.controller.clear();assert.equal(gone.view.attention,false);assert.match(gone.view.notice,/不需要处理/);
  const stale=setup(async cmd=>cmd==='list_pending_integrations'?sticky:{ok:false,error:{code:'OWNER_CONFIRMATION_REQUIRED',message:'SECRET'}});
  await stale.controller.load();await stale.controller.clear();assert.equal(stale.view.attention,true);assert.match(stale.view.error,/无法清除/);assert.doesNotMatch(stale.view.error,/SECRET/);
});
test('double clicks reach the native command once',async()=>{
  const pending=deferred();const s=setup(cmd=>cmd==='list_pending_integrations'?Promise.resolve(sticky):pending.promise);
  await s.controller.load();const one=s.controller.clear();await s.controller.clear();pending.resolve(cleared);await one;
  assert.equal(commands(s).filter(c=>c==='clear_integration_attention').length,1);
});
test('an unconfirmed clear is redacted and locked against retry',async()=>{
  const s=setup(async cmd=>{if(cmd==='list_pending_integrations')return sticky;throw Error('SECRET_CONTENT')});
  await s.controller.load();await s.controller.clear();await s.controller.clear();
  assert.equal(s.view.uncertain,true);assert.doesNotMatch(s.view.error,/SECRET_CONTENT/);
  assert.equal(commands(s).filter(c=>c==='clear_integration_attention').length,1);
});
test('a late scan after the profile is left cannot publish',async()=>{
  const pending=deferred();const s=setup(()=>pending.promise);const op=s.controller.load();s.controller.dispose();pending.resolve(sticky);await op;
  assert.equal(s.views.length,0);
});
test('the workspace page mounts one attention panel per profile and the panel only names the two commands',()=>{
  const page=readFileSync(new URL('../src/routes/workspace/[id]/+page.svelte',import.meta.url),'utf8');
  assert.equal(page.match(/<IntegrationAttention workspaceId=\{profile\.id\} \/>/g)?.length,1);
  const keyed=page.slice(page.indexOf('{#key profile.id}'),page.indexOf('{/key}',page.indexOf('<IntegrationAttention')));
  assert.ok(keyed.includes('<IntegrationAttention'),'mounted inside {#key profile.id}');
  assert.doesNotMatch(page,/list_pending_integrations|clear_integration_attention/);
  const panel=readFileSync(new URL('../src/lib/components/IntegrationAttention.svelte',import.meta.url),'utf8');
  for(const term of ['本机对话框','合并编号和文件路径','不会写入或还原任何工作区文件','原内容被丢弃'])assert.ok(panel.includes(term),term);
  assert.doesNotMatch(panel,/console\.|localStorage|sessionStorage|setInterval|setTimeout/);
  const invoked=[...source.matchAll(/invoke<[^>]*>\('([a-z_]+)'/g)].map(m=>m[1]);
  assert.deepEqual(invoked,['list_pending_integrations','clear_integration_attention']);
});
