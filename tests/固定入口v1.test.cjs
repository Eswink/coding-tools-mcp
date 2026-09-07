// Compile src/lib/固定入口.ts and src/lib/types.ts to a temporary CommonJS
// directory first, then set ENTRY_TEST_BUILD to that directory.
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
if (!process.env.ENTRY_TEST_BUILD) throw new Error('ENTRY_TEST_BUILD must identify compiled source, not a fixture.');
const entry = require(path.join(process.env.ENTRY_TEST_BUILD, '固定入口.js'));
const types = require(path.join(process.env.ENTRY_TEST_BUILD, 'types.js'));
const custom = (domain = 'mcp.example.com', extra = {}) => entry.defaultFrpOptions({ domain_mode: 'custom', custom_domain: domain, ...extra });

test('旧配置默认值保持兼容', () => {
  assert.equal(entry.frpOrigin('frp.example.com', 'demo'), 'https://demo.frp.example.com');
  assert.equal(entry.defaultFrpOptions().tcp_mux, true);
  assert.equal(entry.defaultFrpOptions().tls_enable, true);
  assert.equal(entry.defaultFrpOptions().use_compression, false);
});
for (const host of ['203.0.113.10', '2001:db8::10', '[2001:db8::10]']) {
  test(`服务器 ${host} 与自定义完整域名独立`, () => {
    assert.equal(entry.frpOrigin(host, '', custom('MCP.Example.COM.')), 'https://mcp.example.com');
    assert.throws(() => entry.frpOrigin(host, 'mcp'));
    assert.equal(entry.frpOrigin(host, 'mcp', { subdomain_host: 'example.com' }), 'https://mcp.example.com');
  });
}
test('非标准公网端口与大小写规范化', () => {
  assert.equal(entry.frpOrigin('203.0.113.10', '', custom('MCP.example.com', { public_port: 8443 })), 'https://mcp.example.com:8443');
  assert.equal(entry.normalizeNamedOrigin(' https://MCP.example.com.:443/ '), 'https://mcp.example.com');
});
for (const value of ['http://example.com', 'https://example.com/mcp', 'https://example.com/a/..',
  'https://example.com//', 'https://example.com/%2e%2e', 'https://@example.com',
  'https://user:password@example.com', 'https://example.com?', 'https://example.com#fragment',
  'https://example.com:0', 'https://exam\nple.com', 'https://example.com\\mcp']) {
  test(`拒绝非根地址：${JSON.stringify(value)}`, () => assert.throws(() => entry.normalizePublicOrigin(value)));
}
for (const value of ['https://random.trycloudflare.com', 'https://random.trycloudflare.com.',
  'https://trycloudflare.com', 'https://127.0.0.1', 'https://[::1]']) {
  test(`Named 拒绝临时域名或 IP：${value}`, () => assert.throws(() => entry.normalizeNamedOrigin(value)));
}
test('临时域名判断有后缀边界', () => {
  assert.equal(entry.isQuickTunnelOrigin('https://trycloudflare.com.example.com'), false);
  assert.equal(entry.isQuickTunnelOrigin('https://nottrycloudflare.com'), false);
  assert.equal(entry.isQuickTunnelOrigin('https://x.trycloudflare.com.'), true);
});
for (const value of [0, -1, 65536, 7000.5, '', undefined, NaN, Infinity]) {
  test(`端口必须是整数：${String(value)}`, () => assert.throws(() => entry.strictPort(value)));
}
for (const value of ['https://frps.example.com', 'frps.example.com:7000', '203.0.113.10/path']) {
  test(`服务器不接受 URL 或附带端口：${value}`, () => assert.throws(() => entry.normalizeServerHost(value)));
}
test('IPv6 服务器与本地地址规范化', () => {
  assert.equal(entry.normalizeServerHost('[2001:db8::1]'), '2001:db8::1');
  assert.equal(entry.normalizeServerHost('FRPS.EXAMPLE.COM.'), 'frps.example.com');
});
test('自定义域名不允许配置注入', () => {
  for (const value of ['*.example.com', 'https://mcp.example.com', 'example.com:443', 'example.com/mcp', 'x.example.com"\nserverPort=1']) {
    assert.throws(() => entry.normalizeDomain(value));
  }
});
test('HTTPS 透传不能指向内置 HTTP 端口', () => {
  const options = custom('mcp.example.com', { proxy_type: 'https', https_mode: 'local_tls' });
  assert.throws(() => entry.validateFrpOptions('203.0.113.10', '', options, 28766));
  for (const local_ip of ['127.0.0.1', '127.0.1.2', 'localhost.', '::1', '0.0.0.0', '::']) {
    assert.throws(() => entry.validateFrpOptions('203.0.113.10', '', { ...options, local_ip, local_port: 28766 }, 28766));
  }
  assert.equal(entry.validateFrpOptions('203.0.113.10', '', { ...options, local_port: 443 }, 28766).local_port, 443);
});
test('https2http 需要证书和私钥', () => {
  const options = custom('mcp.example.com', { proxy_type: 'https' });
  assert.throws(() => entry.validateFrpOptions('203.0.113.10', '', options, 28766));
  assert.throws(() => entry.validateFrpOptions('203.0.113.10', '', { ...options, tls_cert_file: '/x', tls_key_file: '/x\0' }, 28766));
});
test('HTTPS 插件预览跟随实际端口并正确转义 Windows 路径', () => {
  const options = custom('actions.example.com', {
    proxy_type: 'https', local_ip: '::1', use_compression: true,
    tls_cert_file: 'C:\\certs\\fullchain.pem', tls_key_file: 'C:\\certs\\private.key',
  });
  const preview = entry.frpConfigPreview('203.0.113.10', 7000, '', options, 8999);
  assert.ok(preview.includes('plugin.localAddr = "[::1]:8999"'));
  assert.ok(preview.includes('plugin.crtPath = "C:\\\\certs\\\\fullchain.pem"'));
  assert.ok(preview.includes('auth.token = "<REDACTED>"'));
  assert.ok(!preview.includes('localPort ='));
  assert.ok(!preview.includes('subdomain ='));
});
test('MCP 预览与 Actions URL helpers 使用同一显式域名模型', () => {
  const route = custom('actions.example.com', { public_port: 8443 });
  const profile = { id: 'test', name: 'test', path: '/tmp/test', tunnel: {}, auth: {}, runtime: {}, actions: {
    ...types.actionsConfig({}), frp_server: '203.0.113.10', frp: route,
  }};
  assert.equal(types.actionsOpenApiUrl(profile), 'https://actions.example.com:8443/openapi.json');
  assert.equal(types.actionsOAuthAuthorizeUrl(profile), 'https://actions.example.com:8443/oauth/authorize');
  assert.equal(types.actionsOAuthTokenUrl(profile), 'https://actions.example.com:8443/oauth/token');
  assert.equal(types.frpPublicUrl('frp', '', '203.0.113.10', '', [], '', custom()), 'https://mcp.example.com');
});
test('旧错误地址不会绕过 IP 后缀校验', () => {
  assert.equal(types.frpPublicUrl('frp', 'demo', '203.0.113.10', '', [], 'https://old.example.com'), '');
});
test('选中的全局配置用于连接，而不是自定义域名后缀', () => {
  const profiles = [{ id: 'main', name: 'Main', server: '203.0.113.10', serverPort: 7000 }];
  assert.equal(types.frpPublicUrl('frp', '', 'ignored.example.com', 'main', profiles, '', custom()), 'https://mcp.example.com');
});
test('自定义模式保留但不验证未启用的旧后缀', () => {
  const options = custom('mcp.example.com', { subdomain_host: 'old incomplete value' });
  assert.equal(entry.validateFrpOptions('203.0.113.10', '', options, 28766).domain_mode, 'custom');
});

// Export actual production-preview outputs for independent TOML parsing.
if (process.env.ENTRY_TEST_TOML) {
  const samples = [
    entry.frpConfigPreview('203.0.113.10', 7000, '', custom(), 28766),
    entry.frpConfigPreview('203.0.113.10', 7000, 'actions', entry.defaultFrpOptions({ subdomain_host: 'example.com', tcp_mux: false, tls_enable: false }), 8787),
    entry.frpConfigPreview('2001:db8::1', 7000, '', custom('actions.example.com', { proxy_type: 'https', local_ip: '::1', tls_cert_file: 'C:\\certs\\chain.pem', tls_key_file: 'C:\\certs\\key.pem', use_compression: true }), 8999),
  ];
  fs.writeFileSync(process.env.ENTRY_TEST_TOML, JSON.stringify(samples));
}
