import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import ts from 'typescript';
import { compile } from 'svelte/compiler';

const source = readFileSync(new URL('../src/lib/runtime/oauth-routing.ts', import.meta.url), 'utf8');
const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } });
const { needsOAuthRoutingHelp, OAUTH_PROXY_PATHS } = await import(`data:text/javascript;base64,${Buffer.from(output.outputText).toString('base64')}`);
const failure = { label: '公网 MCP OAuth 授权元数据', ok: false, code: 'nginx_discovery_route_not_found' };

test('OAuth routing guidance is only shown for active public MCP discovery route failures', () => {
  assert.equal(needsOAuthRoutingHelp([failure]), true);
  assert.equal(needsOAuthRoutingHelp([{ ...failure, code: 'discovery_route_not_found' }]), true);
  for (const change of [{ok:true}, {skipped:true}, {code:'configuration_changed_during_check'},
    {code:'verified'}, {code:undefined}, {label:'本地 MCP OAuth 授权元数据'}, {label:'公网 Actions OAuth 授权元数据'}]) {
    assert.equal(needsOAuthRoutingHelp([{...failure, ...change}]), false);
  }
  assert.equal(needsOAuthRoutingHelp([]), false);
});

test('Frontend and Nginx template enumerate the same five exact OAuth routes', () => {
  const template = readFileSync(new URL('../docs/deployment/nginx-mcp-oauth.conf.template', import.meta.url), 'utf8');
  const actual = [...template.matchAll(/^location = (\S+) \{/gm)].map(m => m[1]).sort();
  assert.deepEqual(actual, [...OAUTH_PROXY_PATHS].sort());
  assert.equal([...template.matchAll(/proxy_pass __MCP_UPSTREAM__;/g)].length, 5);
  assert.doesNotMatch(template, /location\s+\^~/);
  assert.doesNotMatch(template, /auth_basic off|proxy_ssl_verify off|proxy_pass.*__MCP_UPSTREAM__\//);
});

test('Health and routing components compile with escaped request text and no warnings', () => {
  for (const name of ['HealthPanel', 'OAuthRoutingHelp', 'TunnelConfigForm']) {
    const component = readFileSync(new URL(`../src/lib/components/${name}.svelte`, import.meta.url), 'utf8');
    const result = compile(component, { filename: `${name}.svelte`, generate: 'client' });
    assert.deepEqual(result.warnings, []);
    assert.doesNotMatch(component, /\{@html/);
  }
  const health = readFileSync(new URL('../src/lib/components/HealthPanel.svelte', import.meta.url), 'utf8');
  assert.match(health, /\{item\.request\}/);
  assert.match(health, /needsOAuthRoutingHelp\(items\)/);
});

test('Stale backend diagnostics clear machine code and request as well as text', () => {
  const backend = readFileSync(new URL('../src-tauri/src/commands/health.rs', import.meta.url), 'utf8');
  assert.match(backend, /item\.code = "configuration_changed_during_check"\.into\(\)/);
  assert.match(backend, /item\.request\.clear\(\)/);
});
