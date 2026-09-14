/** Binding contracts from the actual shared-secret page, including failed reads. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {parse} from 'svelte/compiler';
const source=readFileSync(process.env.UI_KEYS_SOURCE ?? new URL('../src/routes/settings/keys/+page.svelte',import.meta.url),'utf8');
const ast=parse(source,{modern:true});
function nodes(root,predicate){const out=[];function walk(node){if(!node||typeof node!=='object')return;if(predicate(node))out.push(node);for(const value of Object.values(node)){if(Array.isArray(value))value.forEach(walk);else if(value&&typeof value==='object')walk(value);}}walk(root);return out;}
const components=root=>nodes(root,n=>n.type==='Component'&&n.name==='SecretInput');
const failures=()=>nodes(ast.fragment,n=>n.type==='IfBlock'&&source.slice(n.test.start,n.test.end)==='loadErrors[key]'&&components(n.consequent).length===1);
test('both key sections render failed reads through an unbound disabled input',()=>{
  const rows=failures();assert.equal(rows.length,2,'failed read must not bind undefined into a fallback prop');
  for(const row of rows){const input=components(row.consequent)[0];assert.equal(input.attributes.some(a=>a.type==='BindDirective'),false);
    assert.ok(input.attributes.some(a=>a.name==='disabled'&&a.value===true));
    assert.equal(input.attributes.some(a=>a.name==='onRegenerate'),false);}
});
test('failed inputs have an explicit failure placeholder; successful inputs keep binding',()=>{
  const rows=failures();assert.equal(rows.length,2);
  for(const row of rows){const input=components(row.consequent)[0];const placeholder=input.attributes.find(a=>a.name==='placeholder');
    assert.match(source.slice(placeholder.start,placeholder.end),/读取失败/);
    const normal=components(row.alternate)[0];assert.ok(normal.attributes.some(a=>a.type==='BindDirective'&&a.name==='value'&&source.slice(a.expression.start,a.expression.end)==='secrets[key]'));}
});
test('per-key error state and global fail-closed save checks remain enforced',()=>{
  assert.match(source,/else nextErrors\[result.key\] = true;/);
  assert.match(source,/if \(saving \|\| loading \|\| regenerating \|\| hasLoadErrors \|\| !dirty\) return;/);
  assert.doesNotMatch(source,/else nextSecrets\[result.key\]\s*=/);
});
