import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
import { compile } from 'svelte/compiler';
const read = (p) => readFileSync(new URL('../' + p, import.meta.url),'utf8');
function load(p, dependencies) {
  const output=ts.transpileModule(read(p), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 }});
  const exports={}; new Function('require','exports',output.outputText)((key)=>{ assert.ok(key in dependencies,key);return dependencies[key];}, exports);return exports;
}
test('workspace API sends profile and tunnel credential in one awaited IPC operation', async()=>{
  const calls=[];let fenced=0;let finish;
  const pending=new Promise((resolve)=>{finish=resolve;});
  const api=load('src/lib/api/workspaces.ts',{
    '@tauri-apps/api/core':{invoke:(...args)=>{calls.push(args);return pending;}},
    '$lib/runtime/configuration':{trackConfigurationChange:async(fn)=>{fenced++;try{return await fn();}finally{fenced--;}}},
  });
  const profile={id:'A'};const secret={key:'cloudflare_token',value:'fixture-not-a-real-secret'};
  let done=false;const operation=api.updateWorkspace(profile,secret).then(()=>{done=true;});
  assert.deepEqual(calls,[['update_workspace',{profile,tunnelSecret:secret}]]);
  assert.equal(fenced,1);assert.equal(done,false);finish();await operation;assert.equal(fenced,0);
});
test('public tunnel mutations invalidate health and credential observations, even on failure',async()=>{
  const calls=[];let count=0;
  const api=load('src/lib/api/tunnel.ts',{
    '@tauri-apps/api/core':{invoke:async(name,args)=>{calls.push([name,args]);throw new Error('fixture');}},
    '$lib/runtime/configuration':{trackConfigurationChange:async(fn)=>{count++;return fn();}},
  });
  for(const method of ['startTunnel','stopTunnel','restartTunnel','testTunnel']) await assert.rejects(api[method]('A','mcp'),/fixture/);
  assert.equal(count,4);assert.equal(calls.length,4);
});
test('tunnel form never persists a secret before its parent configuration transaction',()=>{
  const field=read('src/lib/components/SecretTokenField.svelte');
  assert.ok(!field.includes('setSecret('));assert.ok(field.includes('pendingUpdate'));
  const form=read('src/lib/components/TunnelConfigForm.svelte');
  assert.ok(form.includes('pendingUpdate'));assert.ok(!form.includes('saveIfDirty'));
  assert.ok(form.includes('targetWorkspaceId'));assert.ok(form.includes('disposed'));
});
test('both tunnel save handlers use canonical backend apply without an extra restart',()=>{
  const route=read('src/routes/workspace/[id]/+page.svelte');
  assert.ok(!route.includes('restartTunnelIfConfigured'));assert.ok(!route.includes('profile = next;'));
  for(const name of ['saveMcpTunnel','saveActionsTunnel']) {
    const body=route.slice(route.indexOf(`async function ${name}`)).split('\n  async function ')[0];
    assert.ok(body.includes('persistProfile(next, options?.tunnelSecret)'),name);
  }
});
test('changed tunnel components compile with no warnings',()=>{
  for(const p of ['src/lib/components/SecretTokenField.svelte','src/lib/components/TunnelConfigForm.svelte','src/routes/workspace/[id]/+page.svelte'])
    assert.deepEqual(compile(read(p),{generate:'client'}).warnings,[],p);
});
