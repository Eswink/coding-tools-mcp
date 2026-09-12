/** Behavioral unit tests for the real TS frontend boundary; not native evidence. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
import { compile, parse } from 'svelte/compiler';

const read = (p) => readFileSync(new URL('../' + p, import.meta.url), 'utf8');
function module(p, dependencies = {}) {
  const result = ts.transpileModule(read(p), { compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS,
  }, reportDiagnostics: true });
  assert.deepEqual(result.diagnostics, []);
  const exports = {};
  new Function('require', 'exports', result.outputText)((name) => {
    assert.ok(name in dependencies, name); return dependencies[name];
  }, exports);
  return exports;
}
function harness() {
  let state;
  const api = module('src/lib/runtime/configuration.ts', { 'svelte/store': {
    writable(initial) { state = initial; return { update(f) { state = f(state); } }; },
  } });
  return { ...api, snapshot: () => state };
}
function deferred() {
  let resolve, reject;
  const promise = new Promise((a,b) => { resolve=a; reject=b; });
  return { promise, resolve, reject };
}

test('apply waits for canonical refresh and never performs a second write', async () => {
  const h = harness(), delay = deferred(), events = [];
  let done = false;
  const operation = h.applyAndRefresh(async () => { events.push('apply'); }, async () => {
    events.push('refresh'); await delay.promise;
  }).then(() => { done = true; });
  await Promise.resolve(); await Promise.resolve();
  assert.deepEqual(events, ['apply','refresh']); assert.equal(done, false);
  delay.resolve(); await operation; assert.equal(done, true);
});

test('saved-but-restart failure refreshes and remains a rejection', async () => {
  const h = harness(), failure = new Error('saved but restart failed'); let refreshes = 0;
  await assert.rejects(h.applyAndRefresh(async () => { throw failure; }, async () => { refreshes++; }),
    (error) => error === failure);
  assert.equal(refreshes, 1);
});

test('refresh failure cannot mask the primary apply error or turn success into a pass', async () => {
  const h=harness(), primary=new Error('apply'), secondary=new Error('refresh');
  await assert.rejects(h.applyAndRefresh(async () => { throw primary; }, async () => { throw secondary; }),
    (error) => error === primary);
  await assert.rejects(h.applyAndRefresh(async () => {}, async () => { throw secondary; }),
    (error) => error === secondary);
});

test('configuration mutation fences overlap and invalidate on failure without recording values', async () => {
  const h=harness(), a=deferred(), b=deferred();
  const first=h.trackConfigurationChange(() => a.promise);
  const second=h.trackConfigurationChange(() => b.promise);
  assert.deepEqual(h.snapshot(), { revision: 2, pending: 2 });
  a.resolve('private-output'); assert.equal(await first, 'private-output');
  assert.equal(h.snapshot().pending,1);
  b.reject(new Error('fixture')); await assert.rejects(second);
  assert.deepEqual(h.snapshot(), { revision: 4, pending: 0 });
});

test('workspace identity wrappers reject obsolete callbacks before any mutation', async () => {
  const h=harness(); let id='A', calls=0;
  const callback=h.forCurrentWorkspace('A',()=>id,async(value)=>{calls++; return value;});
  assert.equal(await callback('first'),'first'); id='B';
  await assert.rejects(callback('wrong'), /工作区/); assert.equal(calls,1);
});

test('port validation rejects non-integers and directory values preserve filesystem roots', () => {
  const h=harness();
  for (const value of [NaN, Infinity, undefined, 1, 65536, 28766.5]) assert.equal(h.validServicePort(value),false);
  for (const value of [1024,28766,65535]) assert.equal(h.validServicePort(value),true);
  for (const root of ['/','C:\\','\\\\server\\share\\','/directory with trailing space ']) assert.equal(h.selectedDirectory(root),root);
});

test('OAuth and policy saves delegate to one awaited backend instead of restarting again', () => {
  const source=read('src/routes/workspace/[id]/+page.svelte');
  const ast=parse(source,{modern:true});
  for (const name of ['saveMcpAuth','saveActionsAuth','saveMcpPolicy','saveActionsPolicy','saveTaskBudget','saveWorkspacePath']) {
    const fn=ast.instance.content.body.find((n)=>n.type==='FunctionDeclaration' && n.id?.name===name);
    assert.ok(fn,name);
    const code=source.slice(fn.start,fn.end);
    assert.match(code,/persistProfile\(next\)/,name);
    assert.doesNotMatch(code,/restartRuntime|restartActionsRuntime|promptServiceRestart|profile = next/,name);
  }
});

test('modified configuration Svelte files compile without warnings',()=>{
  for (const file of ['src/routes/workspace/[id]/+page.svelte',
    'src/lib/components/WorkspaceMetaForm.svelte','src/lib/components/ServicePanel.svelte']) {
    const result=compile(read(file),{generate:'client'}); assert.deepEqual(result.warnings,[],file);
  }
});
