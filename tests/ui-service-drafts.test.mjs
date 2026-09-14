/** Executes production navigation guards; synthetic local dialog, no IPC authority. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
function fn(path,name){
  const input=readFileSync(new URL(path,import.meta.url),'utf8').match(/<script[^>]*>([\s\S]*?)<\/script>/)[1];
  const ast=ts.createSourceFile('guard.ts',input,ts.ScriptTarget.Latest,true,ts.ScriptKind.TS);
  const node=ast.statements.find(n=>ts.isFunctionDeclaration(n)&&n.name?.text===name);
  assert.ok(node, name);
  return ts.transpileModule(node.getText(ast).replace('export ',''),{compilerOptions:{target:ts.ScriptTarget.ES2022}}).outputText;
}
const view='../src/lib/components/workspace/WorkspaceServiceView.svelte';
const leave=fn(view,'requestLeave'), tab=fn(view,'changeTab');
const service=fn('../src/routes/workspace/[id]/+page.svelte','changeService');
function deferred(){let resolve,reject;const promise=new Promise((r,j)=>{resolve=r;reject=j;});return {promise,resolve,reject};}
function panel(initial={}){
  const d=deferred();const h=new Function('initial','d',`
  let dirty=initial.dirty??true,formBusy=false,busy=false,disposed=false,confirming=false,subTab='config',editRevision=0;
  const tabs=[{value:'config'},{value:'logs'}],prompts=[],errors=[],changes=[];
  const navigationState=()=>({dirty,busy:formBusy});
  const confirm=(...args)=>{prompts.push(args);return d.promise;};
  const showToast=(...args)=>errors.push(args);
  const onTabChange=value=>{changes.push(value);subTab=value;};
  ${leave}\n${tab}
  return {requestLeave,changeTab,prompts,changes,errors,dispose:()=>disposed=true,setBusy:v=>busy=v,
    setFormBusy:v=>formBusy=v,saved:()=>dirty=false,edit:()=>{dirty=true;editRevision++},
    inspect:()=>({dirty,busy,disposed,confirming,subTab})};
  `)(initial,d);return {h,d};
}
test('cancelled tab switch preserves the active panel and edited draft',async()=>{
  const {h,d}=panel();const pending=h.changeTab('logs');d.resolve(false);await pending;
  assert.deepEqual(h.changes,[]);assert.equal(h.inspect().dirty,true);assert.equal(h.inspect().subTab,'config');
});
test('confirmation is single-flight and accepted switching never pretends to save a draft',async()=>{
  const {h,d}=panel();const pending=h.changeTab('logs');await h.changeTab('logs');assert.equal(h.prompts.length,1);
  d.resolve(true);await pending;assert.deepEqual(h.changes,['logs']);assert.equal(h.inspect().dirty,true);
});
test('clean panel changes without a confirmation, invalid/current tabs do nothing',async()=>{
  const {h}=panel({dirty:false});await h.changeTab('absent');await h.changeTab('config');await h.changeTab('logs');
  assert.equal(h.prompts.length,0);assert.deepEqual(h.changes,['logs']);
});
test('disposal, new edit or a newly started mutation blocks a late confirmation',async()=>{
  for(const action of ['dispose','setBusy','setFormBusy','edit']){const {h,d}=panel();const pending=h.changeTab('logs');h[action](true);d.resolve(true);await pending;assert.deepEqual(h.changes,[],action);}
});
test('failed local confirmation fails closed and keeps the draft',async()=>{
  const {h,d}=panel();const pending=h.changeTab('logs');d.reject(Error('synthetic confirmation failure'));await pending;
  assert.equal(h.inspect().dirty,true);assert.equal(h.changes.length,0);assert.equal(h.errors.length,1);
});
test('completed save removes the stale edit warning without a confirmation',async()=>{
  const {h}=panel();h.saved();assert.equal(await h.requestLeave(),true);assert.equal(h.prompts.length,0);
});
test('child-owned operation blocks navigation even when no parent mutation is running',async()=>{
  const {h}=panel({dirty:false});h.setFormBusy(true);assert.equal(await h.requestLeave(),false);assert.equal(h.prompts.length,0);
});
test('aggregate reads only mounted editors for this tab and never returns credential values',()=>{
  const build=new Function('subTab','portEditor','tunnelEditor','authEditor','leaseEditor','policyEditor','taskEditor',`${fn(view,'navigationState')} return navigationState();`);
  const clean={navigationState:()=>({dirty:false,busy:false})};
  const dirty={navigationState:()=>({dirty:true,busy:false,secret:'must-not-escape'})};
  const busy={navigationState:()=>({dirty:false,busy:true})};
  assert.deepEqual(build('config',clean,clean,dirty,clean,clean,busy),{dirty:true,busy:false});
  assert.deepEqual(build('tasks',clean,dirty,dirty,dirty,busy,clean),{dirty:false,busy:false});
  assert.deepEqual(build('tasks',busy,undefined,undefined,undefined,undefined,dirty),{dirty:true,busy:true});
  assert.deepEqual(build('logs',clean,dirty,dirty,dirty,busy,dirty),{dirty:false,busy:false});
});
function route(){
 const d=deferred();const h=new Function('d',`
 let activeService='mcp',workspaceId='one',switchingService=false,configurationBusy=false,mcpBusy=false,actionsBusy=false,disposed=false;
 let serviceView={requestLeave:()=>d.promise};
 ${service}
 return {changeService,inspect:()=>({activeService,switchingService}),changeWorkspace:()=>workspaceId='two',
   replaceView:()=>serviceView={requestLeave:async()=>true},mutate:()=>configurationBusy=true,dispose:()=>disposed=true};
 `)(d);return {h,d};
}
test('MCP/Actions switch respects cancellation and does not race workspace/view replacement',async()=>{
  for(const action of ['cancel','changeWorkspace','replaceView','mutate','dispose']){
    const {h,d}=route();const pending=h.changeService('actions');if(action!=='cancel')h[action]();d.resolve(action!=='cancel');await pending;
    assert.equal(h.inspect().activeService,'mcp',action);assert.equal(h.inspect().switchingService,false);
  }
});
test('accepted service switch activates exactly the requested service',async()=>{
 const {h,d}=route();const pending=h.changeService('actions');d.resolve(true);await pending;assert.equal(h.inspect().activeService,'actions');
});
