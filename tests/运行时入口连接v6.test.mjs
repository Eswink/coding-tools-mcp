/** Svelte AST contract tests: wiring, not a claim of browser/desktop E2E. */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { parse, compile } from 'svelte/compiler';

const page = readFileSync(new URL('../src/routes/workspace/[id]/+page.svelte', import.meta.url), 'utf8');
const form = readFileSync(new URL('../src/lib/components/TunnelConfigForm.svelte', import.meta.url), 'utf8');
const ast = parse(page, { modern: true });
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
  walk(root);
  return found;
}
function component(name, service) {
  return nodes(ast.fragment, (n) => n.type === 'Component' && n.name === name)
    .find((n) => n.attributes.some((a) => a.name === 'service' && a.value?.[0]?.data === service));
}
function expression(componentNode, name) {
  assert.ok(componentNode, 'component must exist');
  const expression = componentNode.attributes.find((a) => a.name === name)?.value?.expression;
  assert.ok(expression, `missing expression prop: ${name}`);
  return page.slice(expression.start, expression.end);
}

test('两套Svelte模板可编译', () => {
  for (const source of [page, form]) {
    const result = compile(source, { generate: 'client' });
    assert.equal(result.warnings.length, 0);
  }
});
test('Actions复制组件使用运行时origin', () => {
  assert.equal(expression(component('GptQuickCopy', 'actions'), 'publicActionsOrigin'), 'actionsActiveOrigin');
});
test('MCP表单展示listener的活动地址并在测试后刷新', () => {
  const node = component('TunnelConfigForm', 'mcp');
  assert.equal(expression(node, 'activePublicOrigin'), 'originFromEndpoint(mcpPublic, "/mcp")');
  assert.equal(expression(node, 'onTested'), '() => load()');
});
test('Actions表单不把临时地址写进固定配置', () => {
  const node = component('TunnelConfigForm', 'actions');
  assert.equal(expression(node, 'activePublicOrigin'), 'actionsActiveOrigin ?? ""');
  assert.equal(expression(node, 'onTested'), '() => load()');
  assert.match(form, /else if \(isQuick\)[\s\S]*?payload\.public_url = "";/);
  assert.doesNotMatch(form, /draft\.public_url = result\.publicUrl/);
});
test('Actions认证表单的四个地址都与活动origin一致', () => {
  const node = nodes(ast.fragment, (n) => n.type === 'Component' && n.name === 'ActionsAuthForm')[0];
  for (const [prop, fn] of [['openapiUrl', 'actionsOpenApiUrl'], ['privacyUrl', 'actionsPrivacyUrl'],
    ['oauthAuthorizeUrl', 'actionsOAuthAuthorizeUrl'], ['oauthTokenUrl', 'actionsOAuthTokenUrl']]) {
    assert.equal(expression(node, prop), `${fn}(profile, frpProfiles, actionsActiveOrigin)`);
  }
});
