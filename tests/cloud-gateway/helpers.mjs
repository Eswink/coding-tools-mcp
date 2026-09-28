import http from 'node:http';
import { randomBytes } from 'node:crypto';
import { startLab } from '../../prototypes/cloud-gateway/gateway.mjs';
import { SyntheticWorkspace } from '../../prototypes/cloud-gateway/state.mjs';
import { MODERN, VERSION_META, CAPABILITIES_META } from '../../prototypes/cloud-gateway/protocol.mjs';

export async function fixture(t, options = {}) {
  const state = new SyntheticWorkspace();
  state.approveForTest('lab-owner');
  const token = randomBytes(32).toString('hex');
  const lab = await startLab({ lab: true, bearerToken: token, state, ...options });
  t.after(() => lab.close());
  return { ...lab, token };
}

export function message(method, params = {}, { version = MODERN, session = 'lab-owner', id = 1 } = {}) {
  const meta = { 'openai/session': session };
  if (version === MODERN) Object.assign(meta, { [VERSION_META]: version, [CAPABILITIES_META]: {} });
  return { jsonrpc: '2.0', id, method, params: { ...params, _meta: { ...meta, ...params._meta } } };
}

export function post(lab, body, { version = MODERN, headers = {}, path, raw, omit = [] } = {}) {
  const payload = raw ?? JSON.stringify(body);
  const base = { Authorization: `Bearer ${lab.token}`, 'Content-Type': 'application/json',
    Accept: 'application/json, text/event-stream', 'MCP-Protocol-Version': version,
    ...(version === MODERN ? { 'Mcp-Method': body?.method ?? 'tools/call',
      ...(body?.method === 'tools/call' ? { 'Mcp-Name': body.params.name } : {}) } : {}), ...headers };
  for (const name of omit) delete base[name];
  return request(lab.endpoint, { method: 'POST', headers: base, path }, payload);
}

export function request(endpoint, options, payload) {
  return new Promise((resolve, reject) => {
    const url = new URL(endpoint);
    const req = http.request({ hostname: url.hostname, port: url.port, path: url.pathname,
      ...Object.fromEntries(Object.entries(options).filter(([, v]) => v !== undefined)) }, res => {
      const chunks = [];
      res.on('data', chunk => chunks.push(chunk));
      res.on('end', () => {
        const text = Buffer.concat(chunks).toString('utf8');
        let body;
        try { body = text ? JSON.parse(text) : undefined; } catch { body = text; }
        resolve({ status: res.statusCode, headers: res.headers, body, text });
      });
      res.on('error', reject);
    });
    req.setTimeout(8000, () => req.destroy(new Error('Test request timeout')));
    req.on('error', reject);
    req.end(payload);
  });
}
export const probe = (session = 'lab-owner') => message('tools/call', { name: 'workspace_probe', arguments: {} }, { session });
