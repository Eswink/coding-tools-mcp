/** Actual focus helper, synthetic DOM shapes. Real built dialog runs in browser CI. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
const source=readFileSync(new URL('../src/lib/ui/dialog-focus.ts',import.meta.url),'utf8');
const js=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText;
const {containDialogFocus}=await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`);
function fixture(){
  const doc={activeElement:null,defaultView:{getComputedStyle:el=>({visibility:el.visibility})}};
  const control=(name,props={})=>({name,tabIndex:0,disabled:false,hidden:false,inert:false,rects:1,visibility:'visible',
    matches(){return this.disabled||this.hidden;},closest(){return this.inert?{}:null;},
    getClientRects(){return Array(this.rects).fill({});},focus(){doc.activeElement=this;},...props});
  const controls=['close','scope','verify','deny'].map(name=>control(name));
  const dialog={open:true,tagName:'DIALOG',ownerDocument:doc,querySelectorAll:()=>controls,focus(){doc.activeElement=this;}};
  const key=(props={})=>{const event={key:'Tab',currentTarget:dialog,defaultPrevented:false,ctrlKey:false,metaKey:false,altKey:false,shiftKey:false,
    preventDefault(){this.defaultPrevented=true;},...props};containDialogFocus(event);return event;};
  return {doc,control,controls,dialog,key};
}
test('last forward wraps to first without invoking or approving a control',()=>{
  const f=fixture();f.controls.at(-1).focus();assert.equal(f.key().defaultPrevented,true);assert.equal(f.doc.activeElement.name,'close');
});
test('first backward wraps to last',()=>{
  const f=fixture();f.controls[0].focus();assert.equal(f.key({shiftKey:true}).defaultPrevented,true);assert.equal(f.doc.activeElement.name,'deny');
});
test('middle traversal remains native instead of stealing every key',()=>{
  const f=fixture();f.controls[1].focus();assert.equal(f.key().defaultPrevented,false);assert.equal(f.doc.activeElement.name,'scope');
});
test('disabled hidden inert detached and negative-tabindex controls never enter wrap targets',()=>{
  const f=fixture();for(const props of [{disabled:true},{hidden:true},{inert:true},{rects:0},{tabIndex:-1},{visibility:'hidden'}])f.controls.push(f.control('blocked',props));
  f.controls[0].focus();f.key({shiftKey:true});assert.equal(f.doc.activeElement.name,'deny');
});
test('busy-state disabled controls are re-evaluated for each key',()=>{
  const f=fixture();f.controls[0].focus();f.controls[3].disabled=true;f.key({shiftKey:true});assert.equal(f.doc.activeElement.name,'verify');
  f.controls[3].disabled=false;f.controls[0].focus();f.key({shiftKey:true});assert.equal(f.doc.activeElement.name,'deny');
});
test('no active control and no available controls both stay inside the dialog',()=>{
  const f=fixture();f.key();assert.equal(f.doc.activeElement.name,'close');
  f.controls.forEach(el=>el.disabled=true);assert.equal(f.key().defaultPrevented,true);assert.equal(f.doc.activeElement,f.dialog);
});
test('closed dialog unrelated keys and OS/browser shortcuts are not trapped',()=>{
  for(const props of [{key:'Escape'},{key:'Enter'},{ctrlKey:true},{altKey:true},{metaKey:true},{currentTarget:null}]){
    const f=fixture();assert.equal(f.key(props).defaultPrevented,false);assert.equal(f.doc.activeElement,null);
  }
  const f=fixture();f.dialog.open=false;assert.equal(f.key().defaultPrevented,false);
});
test('global host attaches only the presentation helper, retaining the explicit approval guard',()=>{
  const host=readFileSync(new URL('../src/lib/components/ChatAuthorizationHost.svelte',import.meta.url),'utf8');
  assert.match(host,/<dialog[^>]+onkeydown=\{containDialogFocus\}/);
  assert.match(host,/if \(approve && !canApprove\(target.grant, selectedScopes, verified, now\)\) return;/);
  assert.doesNotMatch(source,/invoke\(|\.click\(|\.submit\(|dispatchEvent\(/);
});
