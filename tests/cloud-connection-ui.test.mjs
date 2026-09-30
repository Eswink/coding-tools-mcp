import test from 'node:test';
import assert from 'node:assert/strict';
import ts from 'typescript';
import { readFileSync } from 'node:fs';
const source = readFileSync(new URL('../src/lib/cloud-connection.ts', import.meta.url), 'utf8');
const code = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 } }).outputText;
const { createCloudConnectionController, canStartCloud, cloudPhaseLabels } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
const state = (phase = 'configured', connected = false) => ({ phase, connected, generation: null, configured: phase !== 'unconfigured' });
const deferred = () => { let resolve, reject; const promise = new Promise((a,b) => { resolve=a; reject=b; }); return { promise, resolve, reject }; };
const setup = (fn) => { const calls = []; let view; const controller = createCloudConnectionController('workspace-a', (command,args) => { calls.push({command,args}); return fn(command,args); }, next => { view=next; }); return {controller,calls,get view(){return view;}}; };
test('renders every native phase distinctly, connectivity is not approval', () => {
  assert.equal(Object.keys(cloudPhaseLabels).length, 9);
  assert.match(cloudPhaseLabels.connected, /未授权/);
  for (const phase of Object.keys(cloudPhaseLabels)) assert.equal(canStartCloud({status:state(phase),busy:false,uncertain:false}), phase==='configured');
});
test('read-only mount never starts, initializes, imports or approves', async () => {
  const s=setup(async()=>state()); await s.controller.refresh();
  assert.deepEqual(s.calls.map(x=>x.command), ['get_cloud_connection_status']);
});
test('explicit starts never initialize journals unless separately selected and confirmed', async () => {
  const s=setup(async()=>state()); await s.controller.refresh();
  await s.controller.operate('start',async()=>false); assert.equal(s.calls.length,1);
  await s.controller.operate('start',async()=>true);
  assert.deepEqual(s.calls.at(-1), {command:'start_cloud_connection',args:{id:'workspace-a',initializeJournals:false}});
  await s.controller.operate('initialize',async()=>true);
  assert.equal(s.calls.at(-1).args.initializeJournals,true);
});
test('repeated clicks and polling cannot compete with a pending mutation', async () => {
  const pending=deferred(); const s=setup((cmd)=>cmd==='get_cloud_connection_status'?Promise.resolve(state()):pending.promise);
  await s.controller.refresh(); const op=s.controller.operate('start',async()=>true); await Promise.resolve();
  await s.controller.operate('start',async()=>true); await s.controller.refresh();
  assert.equal(s.calls.filter(x=>x.command==='start_cloud_connection').length,1);
  pending.resolve(state('connected',true)); await op; assert.equal(s.view.status.connected,true);
});
test('late polling response cannot overwrite mutation result', async () => {
  const pending=deferred(); let reads=0; const s=setup(cmd=>cmd==='get_cloud_connection_status'?(++reads===1?Promise.resolve(state()):pending.promise):Promise.resolve(state('connected',true)));
  await s.controller.refresh(); const read=s.controller.refresh(); await s.controller.operate('start',async()=>true);
  pending.resolve(state()); await read; assert.equal(s.view.status.phase,'connected');
});
test('unmount or workspace replacement invalidates reads and in-flight confirmation', async () => {
  const p=deferred(); const s=setup(()=>p.promise); const read=s.controller.refresh(); s.controller.dispose(); p.resolve(state()); await read; assert.equal(s.view,undefined);
  const approve=deferred(); const t=setup(async()=>state()); await t.controller.refresh(); const op=t.controller.operate('start',()=>approve.promise); t.controller.dispose(); approve.resolve(true); await op;
  assert.equal(t.calls.length,1);
});
test('uncertain submit is redacted and never automatically retried, even after status refresh', async () => {
  const s=setup(async cmd=>{if(cmd==='start_cloud_connection')throw new Error('SECRET_PRIVATE_KEY'); return state();});
  await s.controller.refresh(); await s.controller.operate('initialize',async()=>true);
  assert.equal(s.view.uncertain,true); assert.doesNotMatch(s.view.error,/SECRET/);
  await s.controller.refresh(); await s.controller.operate('initialize',async()=>true); await s.controller.operate('start',async()=>true);
  assert.equal(s.calls.filter(x=>x.command==='start_cloud_connection').length,1);
});
test('file import needs confirmation, sends only paths and does not connect', async () => {
  let imported=false; const s=setup(async cmd=>{if(cmd==='import_cloud_connection_files'){imported=true; return {};} return state(imported?'configured':'unconfigured');});
  await s.controller.refresh(); await s.controller.operate('import',async()=>true,async()=>({configPath:'/synthetic/config.json',privateKeyPath:'/synthetic/key.json'}));
  assert.deepEqual(s.calls.map(x=>x.command),['get_cloud_connection_status','import_cloud_connection_files','get_cloud_connection_status']);
  assert.equal(s.view.status.configured,true);
});
test('failed or unknown status fails closed', async () => {
  const s=setup(async()=>state('unexpected')); await s.controller.refresh(); assert.equal(s.view.status,null);
  await s.controller.operate('start',async()=>true); assert.equal(s.calls.length,1);
});
test('existing native approvals are retained and new UI never renders credentials',()=>{
  const panel=readFileSync(new URL('../src/lib/components/CloudConnectionPanel.svelte',import.meta.url),'utf8');
  const existing=readFileSync(new URL('../src/lib/components/聊天授权面板v1.svelte',import.meta.url),'utf8');
  assert.match(existing,/<CloudConnectionPanel \{workspaceId\} \/>/); assert.match(existing,/chat_authorization_control/);
  assert.match(panel,/clearInterval\(timer\)/); assert.match(panel,/current\.dispose\(\)/);
  assert.doesNotMatch(panel,/console\.|localStorage|sessionStorage|type="password"|JSON\.stringify/);
});
test('dispose during file selection supplies a cancellation fence and prevents import', async () => {
  const s=setup(async()=>state('unconfigured')); await s.controller.refresh();
  const picked=deferred(); let alive;
  const op=s.controller.operate('import',async()=>true,async isAlive=>{alive=isAlive; await picked.promise; return {configPath:'config',privateKeyPath:'key'};});
  await Promise.resolve(); s.controller.dispose(); assert.equal(alive(),false); picked.resolve(); await op;
  assert.equal(s.calls.length,1);
});
