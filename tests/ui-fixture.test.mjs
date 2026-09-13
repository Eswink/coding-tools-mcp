/** Synthetic transport contract tests. Never substituted for real native IPC. */
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const source=readFileSync(new URL('./fixtures/ui-refactor-ipc.js',import.meta.url),'utf8');
function fixture(){
  const window={};vm.runInNewContext(source,{window,structuredClone,addEventListener:()=>{}});
  return {invoke:window.__TAURI_INTERNALS__.invoke,state:window.__UI_FIXTURE__.state,window};
}
test('logs obey LogChunk[] rather than string iteration with duplicate undefined keys',async()=>{
  const {invoke}=fixture();const value=await invoke('read_workspace_logs',{id:'fixture-workspace',service:'mcp'});
  assert.ok(Array.isArray(value));assert.ok(value.length>0);
  assert.equal(new Set(value.map(row=>row.name)).size,value.length);
  for(const row of value){assert.equal(typeof row.name,'string');assert.equal(typeof row.content,'string');}
});
test('fresh transport is unapproved and never claims native authentication',async()=>{
  const {invoke,state}=fixture();const snapshot=await invoke('chat_authorization_control',{id:'fixture-workspace',action:'status'});
  assert.equal(snapshot.records.length,0);assert.equal(snapshot.lease_state,'free');assert.equal(snapshot.exclusive,true);
  assert.equal(state.pending.length,0);assert.equal(state.calls.some(c=>c.command==='run_health_checks'),false);
});
test('blank profile token keeps the stored presence instead of becoming a new plaintext token',async()=>{
  const {invoke,state}=fixture();const profile=state.profiles[0];
  const result=await invoke('save_frp_profile',{profile,token:undefined});assert.equal(result.hasToken,true);
  assert.equal(Object.hasOwn(result,'token'),false);
});
test('unimplemented commands and unknown software fail, not fake success',async()=>{
  const {invoke,state}=fixture();await assert.rejects(invoke('unimplemented-test-command'),/UNIMPLEMENTED SYNTHETIC IPC/);
  await assert.rejects(invoke('install_software',{kind:'absent'}),/Unknown synthetic software kind/);
  assert.equal(state.unknown.length,1);
});
test('dialog custom positive and cancellation labels preserve Tauri contract',async()=>{
  const {invoke,state}=fixture();const args={buttons:{OkCancelCustom:['切换','继续编辑']}};
  assert.equal(await invoke('plugin:dialog|message',args),'继续编辑');state.confirmation=true;
  assert.equal(await invoke('plugin:dialog|message',args),'切换');
});
