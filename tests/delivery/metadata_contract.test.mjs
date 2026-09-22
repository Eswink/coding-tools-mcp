// Execute the actual fixed metadata script with in-memory API/fs stubs, never a token.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const workflow=fs.readFileSync(new URL('../../.github/workflows/cloud-delivery.yml',import.meta.url),'utf8');
const source=workflow.split('          script: |\n')[1].split('\n      - uses:')[0].split('\n').map(x=>x.slice(12)).join('\n');
const sha='a'.repeat(40);
const packet=()=>({id:'request-admission',issue:49,title:'Bounded request admission',lane:'request-admission',depends_on:['outbound-client'],execution_started:false,authority:'engineering_only'});
async function run(data={revision:sha,packets:[packet()]},options={}) {
  const calls=[],files={};
  const issues={
    listForRepo:async()=>({data:options.issues??[]}),
    get:async()=>({data:{state:options.closed?'closed':'open',...(options.pr?{pull_request:{}}:{})}}),
    listComments:async()=>({data:options.comments??[]}),
    create:async args=>{calls.push(['create',args]);return{data:{number:50}};},
    createComment:async args=>{calls.push(['comment',args]);return{data:{id:1}};},
  };
  const context={process:{env:{PACKETS:JSON.stringify(data),SOURCE_HEAD:sha}},core:{notice:()=>{}},
    github:{rest:{issues,git:{getRef:async()=>({data:{object:{sha:options.stale?'b'.repeat(40):sha}}})}}},
    require:name=>{assert.equal(name,'fs');return{writeFileSync:(p,v)=>{files[p]=JSON.parse(v);}}}};
  try {await vm.runInNewContext('(async()=>{'+source+'})()',context,{timeout:1000});}
  catch(error){error.mutations=calls.length;throw error;}
  return{calls,files};
}
test('ready packet posts queue receipt, not worker launch',async()=>{
  const r=await run();assert.equal(r.calls.length,1);assert.equal(r.calls[0][0],'comment');
  assert.match(r.calls[0][1].body,/Execution has \*\*not\*\* started/);
  assert.equal(r.files['queue-receipts.json'].release_performed,false);
});
test('stale source writes nothing',async()=>assert.equal((await run(undefined,{stale:true})).calls.length,0));
test('zero packets produce empty receipt',async()=>assert.equal((await run({revision:sha,packets:[]})).files['queue-receipts.json'].receipts.length,0));
test('duplicate queue marker is idempotent',async()=>{
  const comments=[{user:{login:'github-actions[bot]'},body:'<!-- ctm-queue:request-admission:'+sha+' -->'}];
  assert.equal((await run(undefined,{comments})).calls.length,0);
});
test('closed issue does not reopen or count as implemented',async()=>{
  const r=await run(undefined,{closed:true});assert.equal(r.calls.length,0);
  assert.equal(r.files['queue-receipts.json'].receipts[0].state,'closed_needs_manifest_review');
});
test('PR cannot masquerade as issue',async()=>assert.rejects(run(undefined,{pr:true}),/not_an_issue/));
test('new issue is created once and linked to source',async()=>{
  const p=packet();p.issue=null;const r=await run({revision:sha,packets:[p]});
  assert.equal(r.calls[0][0],'create');assert.equal(r.calls[1][1].issue_number,50);
  assert.match(r.calls[0][1].body,/No coding worker has started/);
});
test('prior bot-created issue is reused',async()=>{
  const p=packet();p.issue=null;
  const r=await run({revision:sha,packets:[p]},{issues:[{number:50,user:{login:'github-actions[bot]'},body:'<!-- ctm-delivery:request-admission -->'}]});
  assert.equal(r.calls.length,1);assert.equal(r.calls[0][1].issue_number,50);
});
test('untrusted marker cannot suppress task creation',async()=>{
  const p=packet();p.issue=null;
  const r=await run({revision:sha,packets:[p]},{issues:[{number:999,user:{login:'foreign-user'},body:'<!-- ctm-delivery:request-admission -->'}]});
  assert.equal(r.calls[0][0],'create');
});
for(const [name,mutate] of [
  ['wrong source',d=>{d.revision='b'.repeat(40);}],
  ['oversized batch',d=>{d.packets=[packet(),packet(),packet(),packet()];}],
  ['bad lane',d=>{d.packets[0].lane='shell';}],
  ['fake worker',d=>{d.packets[0].execution_started=true;}],
  ['boolean issue',d=>{d.packets[0].issue=true;}],
  ['newline title',d=>{d.packets[0].title='bad\ntitle';}],
  ['invalid dependency',d=>{d.packets[0].depends_on=['../x'];}],
  ['duplicate task',d=>{d.packets.push(packet());}],
])test(name+' rejected',async()=>{const d={revision:sha,packets:[packet()]};mutate(d);await assert.rejects(run(d));});

test('invalid later packet cannot cause partial earlier writes',async()=>{
  const later={...packet(),id:'next-work',lane:'invalid-lane'};
  await assert.rejects(run({revision:sha,packets:[packet(),later]}),error=>{assert.equal(error.mutations,0);return true;});
});
