/** Actual theme store with a bounded browser API fixture, not native window evidence. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import ts from 'typescript';
const require = createRequire(import.meta.url);
const input = readFileSync(new URL('../src/lib/stores/theme.ts', import.meta.url), 'utf8');
const js = ts.transpileModule(input, {compilerOptions:{module:ts.ModuleKind.ESNext, target:ts.ScriptTarget.ES2022}}).outputText
  .replace('"svelte/store"', JSON.stringify(pathToFileURL(require.resolve('svelte/store')).href));
let counter=0;
async function fixture(stored=null, matches=false, broken=false) {
  const listeners=new Map(), mediaListeners=new Set(), writes=[];
  const media={matches, addEventListener:(_,fn)=>mediaListeners.add(fn), removeEventListener:(_,fn)=>mediaListeners.delete(fn)};
  const root={dataset:{}, classes:new Set(), setAttribute:(_,v)=>root.dataset.theme=v,
    classList:{toggle:(_,v)=>v?root.classes.add('dark'):root.classes.delete('dark')}};
  globalThis.document={documentElement:root};
  globalThis.window={localStorage:{getItem:()=>{if(broken)throw Error('synthetic denied');return stored;},
    setItem:(k,v)=>{if(broken)throw Error('synthetic denied');stored=v;writes.push([k,v]);}},
    matchMedia:()=>media, addEventListener:(name,fn)=>listeners.set(name,fn), removeEventListener:(name)=>listeners.delete(name)};
  const module=await import(`data:text/javascript;base64,${Buffer.from(js+`\n// unique fixture ${counter++}`).toString('base64')}`);
  return {module,root,writes,listeners,mediaListeners,system:(v)=>{media.matches=v;for(const fn of mediaListeners)fn();},
    storage:(v)=>listeners.get('storage')?.({key:'theme',newValue:v})};
}
const disposeGlobals=()=>{delete globalThis.window;delete globalThis.document;};
test('legacy explicit light/dark preferences survive system-theme changes', async()=>{
  for(const stored of ['light','dark']) {
    const f=await fixture(stored,stored==='light');const stop=f.module.initializeTheme();
    try {assert.equal(f.root.dataset.theme,stored);f.system(stored!=='dark');assert.equal(f.root.dataset.theme,stored);}finally{stop();disposeGlobals();}
  }
});
test('system default follows changes, explicit override remains stable, system can be restored',async()=>{
  const f=await fixture(null,true);const stop=f.module.initializeTheme();
  try {assert.equal(f.root.dataset.theme,'dark');f.system(false);assert.equal(f.root.dataset.theme,'light');
    f.module.setTheme('dark');assert.deepEqual(f.writes.at(-1),['theme','dark']);f.system(false);assert.equal(f.root.dataset.theme,'dark');
    f.module.setTheme('system');assert.equal(f.root.dataset.theme,'light');f.system(true);assert.equal(f.root.dataset.theme,'dark');
  }finally{stop();disposeGlobals();}
});
test('shell toggle and settings share one effective preference',async()=>{
  const f=await fixture('system',true);const stop=f.module.initializeTheme();
  try{f.module.toggleTheme();assert.equal(f.root.dataset.theme,'light');assert.equal(f.writes.at(-1)[1],'light');
    f.module.setTheme('dark');f.module.toggleTheme();assert.equal(f.root.dataset.theme,'light');}
  finally{stop();disposeGlobals();}
});
test('two mounted consumers share one listener and only final disposal detaches it',async()=>{
  const f=await fixture('system',false);const a=f.module.initializeTheme(),b=f.module.initializeTheme();
  try{assert.equal(f.mediaListeners.size,1);a();a();assert.equal(f.mediaListeners.size,1);f.system(true);assert.equal(f.root.dataset.theme,'dark');b();assert.equal(f.mediaListeners.size,0);assert.equal(f.listeners.size,0);}
  finally{a();b();disposeGlobals();}
});
test('storage failure does not prevent current-session theme controls',async()=>{
  const f=await fixture(null,false,true);const stop=f.module.initializeTheme();
  try{f.module.setTheme('dark');assert.equal(f.root.dataset.theme,'dark');assert.equal(f.root.classes.has('dark'),true);}
  finally{stop();disposeGlobals();}
});
test('invalid persisted preferences safely use system; valid storage updates synchronize',async()=>{
  const f=await fixture('untrusted',true);const stop=f.module.initializeTheme();
  try{assert.equal(f.root.dataset.theme,'dark');f.storage('light');assert.equal(f.root.dataset.theme,'light');
    f.module.setTheme('not-valid');assert.equal(f.root.dataset.theme,'light');f.storage(null);assert.equal(f.root.dataset.theme,'dark');}
  finally{stop();disposeGlobals();}
});
