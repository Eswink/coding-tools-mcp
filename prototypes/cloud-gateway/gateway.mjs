/** Loopback-only HTTP laboratory. Not a production gateway or OAuth service. */
import http from 'node:http';
import { createHash, timingSafeEqual } from 'node:crypto';
import { WireError, errorEnvelope, parseMessage, validateVersion, dispatchProtocol } from './protocol.mjs';
import { SyntheticWorkspace } from './state.mjs';

const MAX_BODY = 65_536;
const singletonHeaders = new Set(['host', 'origin', 'authorization', 'content-type', 'content-length',
  'transfer-encoding', 'content-encoding', 'accept', 'mcp-protocol-version', 'mcp-method', 'mcp-name']);

function checkedHeaders(req, address) {
  const counts = new Map();
  for (let i = 0; i < req.rawHeaders.length; i += 2) {
    const key = req.rawHeaders[i].toLowerCase();
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  for (const [key, count] of counts) {
    if (count > 1 && singletonHeaders.has(key)) {
      const security = ['host', 'origin', 'authorization'].includes(key);
      throw new WireError(security ? 403 : 400, security ? -32600 : -32020, 'Duplicate header');
    }
  }
  const hosts = [`127.0.0.1:${address.port}`, `localhost:${address.port}`];
  if (!hosts.includes(req.headers.host)) throw new WireError(403, -32600, 'Invalid request authority');
  if (req.headers.origin !== undefined && !hosts.map(h => `http://${h}`).includes(req.headers.origin)) {
    throw new WireError(403, -32600, 'Invalid request origin');
  }
  return req.headers;
}

function authenticate(header, expectedDigest) {
  if (typeof header !== 'string' || !/^Bearer [A-Za-z0-9_-]{32,256}$/.test(header)) return false;
  return timingSafeEqual(createHash('sha256').update(header.slice(7)).digest(), expectedDigest);
}

function acceptsBoth(value) {
  if (typeof value !== 'string') return false;
  const types = value.split(',').map(s => s.trim().toLowerCase());
  return ['application/json', 'text/event-stream'].every(type => types.some(part => {
    const [media, ...params] = part.split(';').map(s => s.trim());
    const q = params.find(s => s.startsWith('q='));
    return media === type && (q === undefined || (/^q=(?:0(?:\.\d{1,3})?|1(?:\.0{1,3})?)$/.test(q) && Number(q.slice(2)) > 0));
  }));
}

function readBody(req, timeoutMs) {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks = [];
    const cleanup = () => {
      clearTimeout(timer);
      req.off('data', data); req.off('end', end); req.off('aborted', aborted); req.off('error', aborted);
    };
    const failed = err => { cleanup(); reject(err); };
    const data = chunk => {
      size += chunk.length;
      if (size > MAX_BODY) failed(new WireError(413, -32600, 'Request too large'));
      else chunks.push(chunk);
    };
    const end = () => { cleanup(); resolve(Buffer.concat(chunks)); };
    const aborted = () => failed(new WireError(400, -32600, 'Incomplete request'));
    const timer = setTimeout(() => failed(new WireError(408, -32600, 'Request deadline exceeded')), timeoutMs);
    req.on('data', data); req.once('end', end); req.once('aborted', aborted); req.once('error', aborted);
  });
}

function send(res, status, body, headers = {}) {
  if (res.destroyed || res.writableEnded) return;
  res.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff', Connection: 'close', ...headers });
  res.end(body === undefined ? undefined : JSON.stringify(body));
}

/** The returned state is a trusted local fixture. No remote admin endpoints exist. */
export async function startLab({ lab = false, host = '127.0.0.1', port = 0, bearerToken,
  state = new SyntheticWorkspace(), readTimeoutMs = 5000 } = {}) {
  if (!lab || host !== '127.0.0.1') throw new Error('Explicit loopback laboratory mode required');
  if (typeof bearerToken !== 'string' || !/^[A-Za-z0-9_-]{32,256}$/.test(bearerToken)) {
    throw new Error('A synthetic bearer token of 32-256 URL-safe characters is required');
  }
  if (!Number.isInteger(port) || port < 0 || port > 65535
    || !Number.isInteger(readTimeoutMs) || readTimeoutMs < 50 || readTimeoutMs > 5000
    || !(state instanceof SyntheticWorkspace)) throw new TypeError('Invalid lab configuration');
  const digest = createHash('sha256').update(bearerToken).digest();
  const server = http.createServer({ maxHeaderSize: 16_384, headersTimeout: 5000, requestTimeout: 5000 },
    async (req, res) => {
      let id;
      // Keep stream errors contained even after bounded body readers are removed.
      req.on('error', () => {});
      try {
        const headers = checkedHeaders(req, server.address());
        if (req.url !== '/mcp') throw new WireError(404, -32600, 'Not found');
        if (req.method !== 'POST') {
          send(res, 405, errorEnvelope(new WireError(405, -32600, 'Method not allowed')), { Allow: 'POST' });
          return;
        }
        if (!authenticate(headers.authorization, digest)) {
          send(res, 401, { error: 'invalid_token', mode: 'synthetic-lab' },
            { 'WWW-Authenticate': 'Bearer realm="synthetic-lab"' });
          return;
        }
        if (!/^application\/json(?:\s*;\s*charset=utf-8)?$/i.test(headers['content-type'] ?? '')
          || (headers['content-encoding'] !== undefined && headers['content-encoding'] !== 'identity')) {
          throw new WireError(415, -32600, 'Unsupported content type or encoding');
        }
        if (!acceptsBoth(headers.accept)) throw new WireError(406, -32600, 'Unsupported response media types');
        const length = headers['content-length'];
        if (length !== undefined && (!/^\d+$/.test(length) || Number(length) > MAX_BODY)) {
          throw new WireError(413, -32600, 'Request too large');
        }
        const message = parseMessage(await readBody(req, readTimeoutMs));
        id = message.id;
        const version = validateVersion(message, headers);
        const response = dispatchProtocol(message, version, state);
        send(res, response === undefined ? 202 : 200, response);
      } catch (error) {
        const wire = error instanceof WireError ? error : new WireError(500, -32603, 'Internal error');
        send(res, wire.status, errorEnvelope(wire, id));
      }
    });
  server.maxConnections = 64;
  server.setTimeout(6000, socket => socket.destroy());
  server.on('checkContinue', (_req, res) => send(res, 417, { error: 'expectation_not_supported' }));
  server.on('checkExpectation', (_req, res) => send(res, 417, { error: 'expectation_not_supported' }));
  server.on('clientError', (_error, socket) => {
    if (socket.writable) socket.end('HTTP/1.1 400 Bad Request\r\nConnection: close\r\nContent-Length: 0\r\n\r\n');
    else socket.destroy();
  });
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(port, host, () => { server.off('error', reject); resolve(); });
  });
  return {
    endpoint: `http://${host}:${server.address().port}/mcp`, state,
    close: () => new Promise((resolve, reject) => {
      server.close(error => error ? reject(error) : resolve());
      server.closeAllConnections();
    }),
  };
}
