/** Real Svelte AST wiring: checks both sides of the extracted view boundary. Not native E2E. */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { parse, compile } from 'svelte/compiler';

const page = readFileSync(new URL('../src/routes/workspace/[id]/+page.svelte', import.meta.url), 'utf8');
const view = readFileSync(new URL('../src/lib/components/workspace/WorkspaceServiceView.svelte', import.meta.url), 'utf8');
const form = readFileSync(new URL('../src/lib/components/TunnelConfigForm.svelte', import.meta.url), 'utf8');
function nodes(root, predicate) {
  const found = [];
  function walk(node) {
    if (!node || typeof node !== 'object') return;
    if (predicate(node)) found.push(node);
    for (const value of Object.values(node)) {
      if (Array.isArray(value)) value.forEach(walk);
      else if (value && typeof value === 'object') walk(value);
    }
  }
  walk(root); return found;
}
function expression(source, component, prop) {
  const ast = parse(source, { modern: true });
  const found = nodes(ast.fragment, n => n.type === 'Component' && n.name === component);
  assert.equal(found.length, 1, `exactly one ${component}`);
  const attr = found[0].attributes.find(a => a.name === prop);
  const expr = attr?.value?.expression ?? attr?.value?.[0]?.expression;
  assert.ok(expr, `missing expression ${component}.${prop}`);
  return source.slice(expr.start, expr.end);
}
const parent = prop => expression(page, 'WorkspaceServiceView', prop);
const child = (name, prop) => expression(view, name, prop);

test('父路由、抽取视图和隧道表单模板均可编译', () => {
  for (const source of [page, view, form]) assert.equal(compile(source, {generate:'client'}).warnings.length, 0);
});
test('Actions复制组件透过视图边界使用同一个运行时origin', () => {
  assert.equal(parent('activeOrigin'), 'actionsActiveOrigin');
  assert.equal(child('GptQuickCopy', 'publicActionsOrigin'), 'activeOrigin');
  assert.equal(child('GptQuickCopy', 'service'), 'service');
  assert.equal(parent('service'), 'activeService');
});
test('MCP表单展示listener的活动地址并在测试后刷新', () => {
  assert.equal(parent('publicEndpoint'), 'activeService === "mcp" ? mcpPublic : actionsPublic || actionsOpenApiUrl(profile, frpProfiles, actionsActiveOrigin)');
  assert.equal(child('GptQuickCopy', 'publicMcpEndpoint'), 'mcp ? publicEndpoint : undefined');
  assert.equal(child('TunnelConfigForm', 'activePublicOrigin'), 'mcp ? originFromEndpoint(publicEndpoint, "/mcp") : activeOrigin ?? ""');
  assert.equal(child('TunnelConfigForm', 'onTested'), 'onReload');
  assert.equal(parent('onReload'), '() => load()');
});
test('Actions表单保持临时地址与固定配置分离', () => {
  assert.equal(parent('activeOrigin'), 'actionsActiveOrigin');
  assert.equal(child('TunnelConfigForm', 'config'), 'tunnelConfig');
  assert.equal(parent('tunnelConfig'), 'activeService === "mcp" ? mcpTunnelForm : actionsTunnelForm');
  assert.match(form, /else if \(isQuick\)[\s\S]*?payload\.public_url = "";/);
  assert.doesNotMatch(form, /draft\.public_url = result\.publicUrl/);
});
test('Actions认证表单四个地址均从父路由的活动origin生成', () => {
  assert.equal(parent('activeOrigin'), 'actionsActiveOrigin');
  for (const [prop, fn] of [['openapiUrl', 'actionsOpenApiUrl'], ['privacyUrl', 'actionsPrivacyUrl'],
    ['oauthAuthorizeUrl', 'actionsOAuthAuthorizeUrl'], ['oauthTokenUrl', 'actionsOAuthTokenUrl']]) {
    assert.equal(child('ActionsAuthForm', prop), `${fn}(profile, frpProfiles, activeOrigin)`);
  }
});
test('异步预算保存锁定渲染时服务与工作区，禁止迟到写入其他服务', () => {
  assert.match(page, /\{@const currentService = activeService\}/);
  assert.equal(parent('onBudgetSave'), 'bindWorkspace(profile.id, (ms: number) => saveTaskBudget(currentService, ms))');
});
