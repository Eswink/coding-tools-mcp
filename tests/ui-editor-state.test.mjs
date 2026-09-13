/** Read-only state adapters execute production functions, never credential actions. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
function state(name, values) {
  const source = readFileSync(new URL(`../src/lib/components/${name}.svelte`, import.meta.url), 'utf8').match(/<script[^>]*>([\s\S]*?)<\/script>/)[1];
  const ast = ts.createSourceFile('editor.ts', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
  const node = ast.statements.find(n => ts.isFunctionDeclaration(n) && n.name?.text === 'navigationState');
  assert.ok(node, name);
  const code = ts.transpileModule(node.getText(ast).replace('export ', ''), {compilerOptions:{target:ts.ScriptTarget.ES2022}}).outputText;
  return new Function(...Object.keys(values), `${code};return navigationState();`)(...Object.values(values));
}
test('authentication adapters expose booleans, including child credential operations', () => {
  const auth = {dirty:false,saving:false,loadingSecrets:false,regenerating:null};
  assert.deepEqual(state('AuthConfigForm', auth), {dirty:false,busy:false});
  for (const change of [{saving:true},{loadingSecrets:true},{regenerating:'client_secret'}]) {
    assert.deepEqual(state('AuthConfigForm', {...auth,...change}), {dirty:false,busy:true});
  }
  assert.deepEqual(state('AuthConfigForm', {...auth,dirty:true}), {dirty:true,busy:false});
  assert.deepEqual(state('ActionsAuthForm', {dirty:true,saving:false,credentialsBusy:true}), {dirty:true,busy:true});
});
test('policy, port and task adapters report reverted edits and in-flight mutations', () => {
  for (const name of ['RuntimePolicyForm','ActionsPolicyForm']) {
    assert.deepEqual(state(name,{dirty:false,saving:false}), {dirty:false,busy:false});
    assert.deepEqual(state(name,{dirty:true,saving:true}), {dirty:true,busy:true});
  }
  assert.deepEqual(state('ServicePanel',{draftPort:28766,port:28766,savingPort:false,busy:false}),{dirty:false,busy:false});
  // The parent's confirmation disables controls, but is not an in-flight port save.
  assert.deepEqual(state('ServicePanel',{draftPort:28766,port:28766,savingPort:false,busy:true}),{dirty:false,busy:false});
  assert.deepEqual(state('ServicePanel',{draftPort:28767,port:28766,savingPort:true,busy:false}),{dirty:true,busy:true});
  assert.deepEqual(state('异步任务面板v2',{minutes:5,maxTimeoutMs:300000,saving:false,busy:false}),{dirty:false,busy:false});
  assert.deepEqual(state('异步任务面板v2',{minutes:undefined,maxTimeoutMs:300000,saving:false,busy:true}),{dirty:true,busy:true});
});
test('tunnel aggregates only the displayed token editor and does not expose its value', () => {
  assert.deepEqual(state('SecretTokenField',{draft:'  ',loading:false}),{dirty:false,busy:false});
  assert.deepEqual(state('SecretTokenField',{draft:'synthetic-secret',loading:true}),{dirty:true,busy:true});
  const tokenField={navigationState:()=>({dirty:true,busy:true,value:'never-escape'})};
  assert.deepEqual(state('TunnelConfigForm',{dirty:false,saving:false,testing:false,showToken:true,tokenField}),{dirty:true,busy:true});
  assert.deepEqual(state('TunnelConfigForm',{dirty:false,saving:false,testing:false,showToken:false,tokenField}),{dirty:false,busy:false});
});
test('session policy compares all actual fields including invalid numeric drafts', () => {
  const policy={exclusive:true,access_token_ttl_seconds:3600,refresh_session_ttl_seconds:2592000,chat_lease_ttl_seconds:86400,chat_idle_timeout_seconds:0};
  const clean={auth:{session_policy:policy},sessionPolicy:p=>p,exclusive:true,accessMinutes:60,refreshDays:30,leaseHours:24,idleMinutes:0,busy:false};
  assert.deepEqual(state('RemoteSessionSettings',clean),{dirty:false,busy:false});
  for (const change of [{exclusive:false},{accessMinutes:undefined},{refreshDays:31},{leaseHours:48},{idleMinutes:30}]) {
    assert.deepEqual(state('RemoteSessionSettings',{...clean,...change}),{dirty:true,busy:false});
  }
  assert.deepEqual(state('RemoteSessionSettings',{...clean,busy:true}),{dirty:false,busy:true});
});
