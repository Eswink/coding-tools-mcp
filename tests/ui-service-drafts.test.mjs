/** Executes the production navigation guards with synthetic local confirmation. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
function fn(path,name){
  const input=readFileSync(new URL(path,import.meta.url),'utf8').match(/<script[^>]*>([\s\S]*?)<\/script>/)[1];
  const ast=ts.createSourceFile('guard.ts',input,ts.ScriptTarget.Latest,true,ts.ScriptKind.TS);
  const node=ast.statements.find(s=>ts.isFunctionDeclaration(s)&&s.name?.text===name);assert.ok(node);
  return ts.transpileModule(node.getText(ast).replace('export ',''),{compilerOptions:{target:ts.ScriptTarget.ES2022}}).outputText;
}
const leave=fn('../src/lib/components/workspace/WorkspaceServiceView.svelte','requestLeave');
const tab=fn('../src/lib/components/workspace/WorkspaceServiceView.svelte','changeTab');
const service=fn('../src/routes/workspace/[id]/+page.svelte','changeService');
function deferred(){let resolve,reject;const promise=new Promise((r,j)=>{resolve=r;reject=j;});return {promise,resolve,reject};}
function panel(initial={}){
  const d=deferred();const h=new Function('initial','d',`
  let edited=initial.edited??true,busy=false,disposed=false,confirming=false,subTab='config';
  const tabs=[{value:'config'},{value:'logs'}],prompts=[],errors=[],changes=[];
  const confirm=(...args)=>{prompts.push(args);return d.promise;};
  const showToast=(...args)=>errors.push(args);
  const onTabChange=value=>{changes.push(value);subTab=value;};
  ${leave}\n${tab}
  return {requestLeave,changeTab,prompts,changes,errors,dispose:()=>disposed=true,setBusy:v=>busy=v,
    inspect:()=>({edited,busy,disposed,confirming,subTab})};
  `)(initial,d);return {h,d};
}
test('cancelled tab switch preserves the active panel and edited draft',async()=>{
  const {h,d}=panel();const pending=h.changeTab('logs');d.resolve(false);await pending;
  assert.deepEqual(h.changes,[]);assert.equal(h.inspect().edited,true);assert.equal(h.inspect().subTab,'config');
});
test('confirmation is single-flight and approved switching clears only the old edit flag',async()=>{
  const {h,d}=panel();const pending=h.changeTab('logs');await h.changeTab('logs');assert.equal(h.prompts.length,1);
  d.resolve(true);await pending;assert.deepEqual(h.changes,['logs']);assert.equal(h.inspect().edited,false);
});
test('clean panel changes without a confirmation, invalid/current tabs do nothing',async()=>{
  const {h}=panel({edited:false});await h.changeTab('absent');await h.changeTab('config');await h.changeTab('logs');
  assert.equal(h.prompts.length,0);assert.deepEqual(h.changes,['logs']);
});
test('disposal or a newly started mutation blocks a late confirmation',async()=>{
  for(const action of ['dispose','setBusy']){const {h,d}=panel();const pending=h.changeTab('logs');h[action](true);d.resolve(true);await pending;assert.deepEqual(h.changes,[]);}
});
test('failed local confirmation fails closed and keeps the draft',async()=>{
  const {h,d}=panel();const pending=h.changeTab('logs');d.reject(Error('synthetic confirmation failure'));await pending;
  assert.equal(h.inspect().edited,true);assert.equal(h.changes.length,0);assert.equal(h.errors.length,1);
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
