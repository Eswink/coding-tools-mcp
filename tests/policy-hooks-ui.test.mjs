import test from 'node:test';
import assert from 'node:assert/strict';
import ts from 'typescript';
import { readFileSync } from 'node:fs';
const source = readFileSync(new URL('../src/lib/policy-hooks.ts', import.meta.url), 'utf8');
const code = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 } }).outputText;
const { createHookController } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
const state = { enabled:false, count:0, recovery_required:false };
const packet = () => ({ pending_id:'12345678-1234-1234-1234-123456789012', expires_in_seconds:60, native_dialog_required:true, preview:{digest:'a'.repeat(64),runtime_only:true,network_allowed:false,requires_local_conversation_authority:true,hooks:[{manifest:{id:'review',event:'before_tool',tool:'exec_command',executable:'/usr/bin/python3'},executable_sha256:'b'.repeat(64),script_sha256:null,script_source:null}]} });
const input = '[{"id":"review","event":"before_tool","tool":"exec_command","executable":"/usr/bin/python3"}]';
function setup(fn, clock) {
  const calls=[];let view;
  const c=createHookController('workspace-a',async(command,args)=>{calls.push({command,args});return fn(command,args);},v=>view=v,clock);
  return {c,calls,get view(){return view;}};
}
function deferred(){let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};}
test('mount is status-only and never imports or approves',async()=>{
  const s=setup(async()=>state);await s.c.refresh();assert.deepEqual(s.calls,[{command:'get_policy_hooks',args:{id:'workspace-a'}}]);
});
test('preview is not approval and only reviewed exact native digest is submitted',async()=>{
  const s=setup(async c=>c==='preview_policy_hooks'?packet():state);
  await s.c.prepare(input);await s.c.approve(false);assert.equal(s.calls.length,1);
  await s.c.approve(true);assert.deepEqual(s.calls[1],{command:'approve_policy_hooks',args:{id:'workspace-a',pendingId:packet().pending_id,digest:'a'.repeat(64)}});assert.equal(s.view.pending,null);
});
test('oversized or non-array manifest never reaches native IPC',async()=>{
  const s=setup(async()=>packet());for(const value of ['{}','[]',' '.repeat(8193),JSON.stringify(Array(9).fill({}))])await s.c.prepare(value);assert.equal(s.calls.length,0);
});
test('native preview claiming cloud authority or network permission is rejected',async()=>{
  for(const corrupt of [p=>p.preview.network_allowed=true,p=>p.native_dialog_required=false,p=>p.preview.digest='bad',p=>p.preview.hooks[0].script_source='x'.repeat(65537)]){
    const p=packet();corrupt(p);const s=setup(async()=>p);await s.c.prepare(input);await s.c.approve(true);assert.equal(s.view.pending,null);assert.equal(s.calls.length,1);
  }
});
test('expired preview cannot submit even if checkbox remained checked',async()=>{
  let now=1;const s=setup(async()=>packet(),()=>now);await s.c.prepare(input);now+=60000;await s.c.approve(true);assert.equal(s.calls.length,1);assert.equal(s.view.pending,null);
});
test('native dialog cancellation consumes pending and never retries',async()=>{
  const s=setup(async c=>c==='preview_policy_hooks'?packet():null);await s.c.prepare(input);await s.c.approve(true);await s.c.approve(true);assert.equal(s.calls.length,2);assert.equal(s.view.uncertain,false);assert.match(s.view.notice,/取消/);
});
test('repeated approvals produce one IPC call while native dialog is pending',async()=>{
  const d=deferred();const s=setup(async c=>c==='preview_policy_hooks'?packet():d.promise);await s.c.prepare(input);const first=s.c.approve(true);await s.c.approve(true);assert.equal(s.calls.length,2);d.resolve(state);await first;
});
test('uncertain approval remains locked after successful status refresh',async()=>{
  const s=setup(async c=>{if(c==='preview_policy_hooks')return packet();if(c==='get_policy_hooks')return state;throw Error('SECRET_FIXTURE_DO_NOT_RENDER');});
  await s.c.prepare(input);await s.c.approve(true);await s.c.refresh();await s.c.prepare(input);assert.equal(s.calls.length,3);assert.equal(s.view.uncertain,true);assert.doesNotMatch(JSON.stringify(s.view),/SECRET_FIXTURE/);
});
test('disable retains native recovery and does not mint a successor approval',async()=>{
  const s=setup(async()=>({...state,recovery_required:true}));await s.c.disable();await s.c.prepare(input);assert.equal(s.calls.length,1);assert.equal(s.view.status.recovery_required,true);
});
test('workspace disposal ignores late preview and cannot approve it',async()=>{
  const d=deferred();const s=setup(async()=>d.promise);const pending=s.c.prepare(input);s.c.dispose();d.resolve(packet());await pending;await s.c.approve(true);assert.equal(s.calls.length,1);assert.equal(s.view.pending,null);
});
test('discarded preview cannot authorize a later click',async()=>{
  const s=setup(async()=>packet());await s.c.prepare(input);s.c.discard();await s.c.approve(true);assert.equal(s.calls.length,1);
});
test('late status cannot overwrite a newer approval result',async()=>{
  const d=deferred();const s=setup(async c=>c==='get_policy_hooks'?d.promise:c==='preview_policy_hooks'?packet():({...state,enabled:true,count:1}));
  const read=s.c.refresh();await s.c.prepare(input);await s.c.approve(true);d.resolve(state);await read;assert.equal(s.view.status.enabled,true);
});
test('rendered source escapes script text and stores no persistent manifest',()=>{
  const panel=readFileSync(new URL('../src/lib/components/PolicyHooksPanel.svelte',import.meta.url),'utf8');
  assert.match(panel,/\{hook.script_source\}/);assert.doesNotMatch(panel+source,/@html|localStorage|sessionStorage|console\./);assert.match(panel,/type="checkbox"/);
});
