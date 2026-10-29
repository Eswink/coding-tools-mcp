import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
const source=readFileSync(new URL('../src/lib/cloud-drain-warning.ts',import.meta.url),'utf8');
const code=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022}}).outputText;
const {watchCloudDrain}=await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
test('one subscription warns once without displaying event payload and cleans up',async()=>{
 let callback,count=0,stopped=0; const messages=[];
 const dispose=watchCloudDrain(async(event,cb)=>{assert.equal(event,'cloud-drain-incomplete');callback=cb;count++;return()=>stopped++;},m=>messages.push(m));
 await Promise.resolve(); callback({payload:'SENSITIVE'}); callback(); assert.equal(count,1); assert.equal(messages.length,1); assert.doesNotMatch(messages[0],/SENSITIVE/);
 dispose(); callback(); assert.equal(stopped,1); assert.equal(messages.length,1);
});
test('late registration after unmount is immediately removed',async()=>{
 let resolve,callback,stopped=0; const messages=[];
 const dispose=watchCloudDrain((event,cb)=>{callback=cb;return new Promise(r=>resolve=r)},m=>messages.push(m));
 dispose(); resolve(()=>stopped++); await Promise.resolve(); callback(); assert.equal(stopped,1); assert.equal(messages.length,0);
});
test('subscription failure is visible without native error content',async()=>{
 const messages=[]; watchCloudDrain(async()=>{throw Error('SECRET')},m=>messages.push(m));
 await Promise.resolve(); await Promise.resolve(); assert.equal(messages.length,1); assert.doesNotMatch(messages[0],/SECRET/);
});
test('global layout mount is unconditional and warning persists until dismissed',()=>{
 const layout=readFileSync(new URL('../src/routes/+layout.svelte',import.meta.url),'utf8');
 const component=readFileSync(new URL('../src/lib/components/CloudDrainWarning.svelte',import.meta.url),'utf8');
 assert.match(layout,/<CloudDrainWarning \/>\s*<AppShell/); assert.match(component,/duration: 0/);
});
