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
    get:async()=>({data:{state:options.closed?'closed':'open',assignees:Object.hasOwn(options,'assignees')?options.assignees:[{login:'Eswink'}],...(options.pr?{pull_request:{}}:{})}}),
    listComments:async()=>({data:options.comments??[]}),
    create:async args=>{calls.push(['create',args]);return{data:{number:50}};},
    addAssignees:async args=>{calls.push(['assign',args]);if(options.assignmentError)throw Error('assignment_api_error');return{data:{assignees:options.assigned??[{login:'Eswink'}]}};},
    createComment:async args=>{calls.push(['comment',args]);return{data:{id:1}};},
  };
  const context={process:{env:{PACKETS:JSON.stringify(data),SOURCE_HEAD:sha}},core:{notice:()=>{}},
    github:{rest:{issues,git:{getRef:async()=>({data:{object:{sha:options.stale?'b'.repeat(40):sha}}})}}},
    require:name=>{assert.equal(name,'fs');return{writeFileSync:(p,v)=>{files[p]=JSON.parse(v);}}}};
  try {await vm.runInNewContext('(async()=>{'+source+'})()',context,{timeout:1000});}
  catch(error){error.mutations=calls.length;error.calls=calls;error.files=files;throw error;}
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
  const r=await run(undefined,{closed:true,assignees:[]});assert.equal(r.calls.length,0);
  assert.equal(r.files['queue-receipts.json'].receipts[0].state,'closed_needs_manifest_review');
});
test('PR cannot masquerade as issue',async()=>assert.rejects(run(undefined,{pr:true,assignees:[]}),error=>{assert.match(error.message,/not_an_issue/);assert.equal(error.mutations,0);return true;}));
test('new issue is created once and linked to source',async()=>{
  const p=packet();p.issue=null;const r=await run({revision:sha,packets:[p]});
  assert.equal(r.calls[0][0],'create');assert.equal(r.calls[1][1].issue_number,50);
  assert.match(r.calls[0][1].body,/No coding worker has started/);
  assert.equal(JSON.stringify(r.calls[0][1].assignees),JSON.stringify(['Eswink']));
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

test('unowned existing issue gets only the fixed repository owner before queue receipt',async()=>{
  const p={...packet(),assignee:'foreign-user'};
  const r=await run({revision:sha,packets:[p]},{assignees:[]});
  assert.deepEqual(r.calls.map(x=>x[0]),['assign','comment']);
  assert.equal(r.calls[0][1].issue_number,49);
  assert.equal(JSON.stringify(r.calls[0][1].assignees),JSON.stringify(['Eswink']));
  assert.deepEqual(r.files['queue-receipts.json'].receipts[0].assignees,['Eswink']);
  assert.equal(r.files['queue-receipts.json'].receipts[0].execution_started,false);
});
test('existing human ownership is preserved without adding the repository owner',async()=>{
  const r=await run(undefined,{assignees:[{login:'existing-maintainer'}]});
  assert.deepEqual(r.calls.map(x=>x[0]),['comment']);
  assert.deepEqual(r.files['queue-receipts.json'].receipts[0].assignees,['existing-maintainer']);
});
test('duplicate queue receipt can heal missing ownership without duplicate comment',async()=>{
  const comments=[{user:{login:'github-actions[bot]'},body:'<!-- ctm-queue:request-admission:'+sha+' -->'}];
  const r=await run(undefined,{comments,assignees:[]});
  assert.deepEqual(r.calls.map(x=>x[0]),['assign']);
  assert.equal(r.files['queue-receipts.json'].receipts[0].state,'already_queued');
});
test('unconfirmed assignment must not be recorded as queued',async()=>{
  await assert.rejects(run(undefined,{assignees:[],assigned:[]}),error=>{
    assert.match(error.message,/assignment_not_confirmed/);
    assert.deepEqual(error.calls.map(x=>x[0]),['assign']);
    assert.equal(Object.hasOwn(error.files,'queue-receipts.json'),false);return true;
  });
});
test('assignment API failure preserves a retryable unqueued task',async()=>{
  await assert.rejects(run(undefined,{assignees:[],assignmentError:true}),error=>{
    assert.match(error.message,/assignment_api_error/);
    assert.deepEqual(error.calls.map(x=>x[0]),['assign']);
    assert.equal(Object.hasOwn(error.files,'queue-receipts.json'),false);return true;
  });
});
test('missing assignee response is not interpreted as an unowned task',async()=>{
  await assert.rejects(run(undefined,{assignees:null}),error=>{
    assert.match(error.message,/invalid_assignee_state/);assert.equal(error.mutations,0);return true;
  });
});

// Evaluate the actual job condition; no GitHub API or token is involved.
const queueJob = workflow.split('  queue-issues:\n')[1];
const queueCondition = queueJob.split('\n').find(line => line.startsWith('    if: ')).slice(8);
function queueAllowed({ mode = 'isolated-increment', result = 'success', event = 'push',
                        ref = 'refs/heads/feat/cloud-gateway-agent-runtime',
                        repository = 'Eswink/coding-tools-mcp' } = {}) {
  return vm.runInNewContext(queueCondition, {
    needs: { plan: { result, outputs: { scope_mode: mode } } },
    github: { repository, event_name: event, ref },
  }, { timeout: 1000 });
}

test('ordinary isolated feature push retains bounded issue queue', () => {
  assert.equal(queueAllowed(), true);
});
test('reviewed cumulative feature push never opens a legacy release-work queue', () => {
  assert.equal(queueAllowed({ mode: 'reviewed-cumulative' }), false);
});
for (const mode of ['', 'unknown', undefined]) {
  test(`missing or unknown route cannot authorize queue: ${String(mode)}`, () => {
    const condition = vm.runInNewContext(queueCondition, {
      needs: { plan: { result: 'success', outputs: { scope_mode: mode } } },
      github: { repository: 'Eswink/coding-tools-mcp', event_name: 'push',
                ref: 'refs/heads/feat/cloud-gateway-agent-runtime' },
    });
    assert.equal(condition, false);
  });
}
for (const result of ['failure', 'cancelled', 'skipped']) {
  test(`failed source verification or planning cannot queue: ${result}`, () => {
    assert.equal(queueAllowed({ result }), false);
  });
}
test('PR, manual, foreign-repository and other-branch events remain read-only', () => {
  for (const options of [{ event: 'pull_request' }, { event: 'workflow_dispatch' },
                         { repository: 'other/fork' }, { ref: 'refs/heads/release/rc' }]) {
    assert.equal(queueAllowed(options), false);
  }
});
test('delivery verifies selected cumulative source and retains read-only packet tests', () => {
  const plan = workflow.split('  plan:\n')[1].split('  queue-issues:\n')[0];
  assert.match(plan, /scope_mode: \$\{\{ steps\.scope_route\.outputs\.scope_mode \}\}/);
  assert.match(plan, /--select-route[\s\S]*--github-output "\$GITHUB_OUTPUT"/);
  const verification = plan.split('      - name: Verify cumulative source before read-only delivery planning\n')[1].split('      - name:')[0];
  assert.match(verification, /if: steps\.scope_route\.outputs\.scope_mode == 'reviewed-cumulative'/);
  assert.match(verification, /reviewed_source_gate\.py --expect-sha "\$GITHUB_SHA" --output/);
  assert.doesNotMatch(verification, /--select-route|continue-on-error|\|\| true/);
  const tests = plan.split('      - name: Test deterministic scheduler and compute work packets\n')[1];
  assert.match(tests, /if: always\(\)/);
  assert.match(tests, /python -m unittest discover -s tests\/delivery -v/);
  assert.match(tests, /node --test tests\/delivery\/metadata_contract\.test\.mjs/);
  assert.match(tests, /python tools\/delivery\/dispatch\.py/);
});
test('lab selects exactly one required scope validator without branch-name exclusion', () => {
  const lab = fs.readFileSync(new URL('../../.github/workflows/cloud-gateway-lab.yml', import.meta.url), 'utf8');
  const selection = lab.split('      - name: Select exact-source scope validator\n')[1].split('      - name:')[0];
  assert.match(selection, /if: always\(\)/);
  assert.match(selection, /--expect-sha "\$GITHUB_SHA" --select-route/);
  for (const [name, mode] of [['Verify isolated increment scope and record candidate identity', 'isolated-increment'],
                            ['Verify reviewed cumulative source manifest', 'reviewed-cumulative']]) {
    const step = lab.split(`      - name: ${name}\n`)[1].split('      - ')[0];
    assert.ok(step);
    const condition = step.split('\n').find(line => line.trim().startsWith('if: ')).trim().slice(4);
    for (const actual of ['isolated-increment', 'reviewed-cumulative', '', undefined]) {
      assert.equal(vm.runInNewContext(condition, { always: () => true,
        steps: { scope_route: { outputs: { scope_mode: actual } } } }), actual === mode);
    }
    assert.doesNotMatch(step, /continue-on-error|\|\| true/);
  }
});
test('gate-only changes trigger read-only checks without expanding issue-writing push events', () => {
  const lab = fs.readFileSync(new URL('../../.github/workflows/cloud-gateway-lab.yml', import.meta.url), 'utf8');
  const labPush = lab.split('  push:\n')[1].split('  pull_request:\n')[0];
  const deliveryPr = workflow.split('  pull_request:\n')[1].split('  workflow_dispatch:')[0];
  for (const path of ['scripts/reviewed_source_gate.py', 'scripts/reviewed_source_gate_tests.py',
                     'scripts/source_provenance_gate.py', 'scripts/source_provenance_gate_tests.py',
                     'scripts/rc_version_gate.py', 'scripts/rc_version_gate_tests.py',
                     'scripts/发布版本校验v4.py', 'docs/releases/reviewed-source-manifest.json']) {
    assert.ok(labPush.includes(`- '${path}'`), path);
    assert.ok(deliveryPr.includes(`- '${path}'`), path);
  }
  assert.match(lab, /node --test tests\/delivery\/metadata_contract\.test\.mjs/);
  const deliveryPush = workflow.split('  push:\n')[1].split('  pull_request:\n')[0];
  assert.equal(deliveryPush.trim(), "branches: ['feat/cloud-gateway-agent-runtime']\n    paths: ['tools/delivery/**', 'tests/delivery/**', '.github/workflows/cloud-delivery.yml']");
});
