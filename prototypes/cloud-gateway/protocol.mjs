/** Limited modern/legacy wire contract. No production identity or execution. */
export const MODERN = '2026-07-28';
export const LEGACY = Object.freeze(['2025-11-25', '2025-06-18']);
export const VERSIONS = Object.freeze([MODERN, ...LEGACY]);
export const VERSION_META = 'io.modelcontextprotocol/protocolVersion';
export const CAPABILITIES_META = 'io.modelcontextprotocol/clientCapabilities';
export const INFO_META = 'io.modelcontextprotocol/serverInfo';
export const SERVER_INFO = Object.freeze({ name: 'coding-tools-gateway-lab', version: '0.1.0-lab' });
export const INSTRUCTIONS = 'NON-PRODUCTION synthetic protocol laboratory. No files or commands are executed. '
  + 'On offline or permission errors do not retry, request credentials, or request OAuth again.';
export const isObject = value => value !== null && typeof value === 'object' && !Array.isArray(value);

export class WireError extends Error {
  constructor(status, code, message, data) {
    super(message);
    this.status = status;
    this.code = code;
    this.data = data;
  }
}

export function errorEnvelope(error, id) {
  return {
    jsonrpc: '2.0', ...(id === undefined ? {} : { id }),
    error: { code: error.code, message: error.message,
      ...(error.data === undefined ? {} : { data: error.data }) },
  };
}

export function complete(version, data) {
  return version === MODERN
    ? { ...data, resultType: 'complete', _meta: { [INFO_META]: SERVER_INFO } }
    : data;
}

export function toolResult(version, data) {
  return complete(version, {
    content: [{ type: 'text', text: JSON.stringify(data) }],
    structuredContent: data,
    isError: data.ok === false,
  });
}

export function parseMessage(bytes) {
  let message;
  try {
    const text = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
    message = JSON.parse(text);
  } catch {
    throw new WireError(400, -32700, 'Invalid JSON');
  }
  if (!isObject(message) || message.jsonrpc !== '2.0'
    || typeof message.method !== 'string' || message.method.length > 128
    || Object.keys(message).some(key => !['jsonrpc', 'id', 'method', 'params'].includes(key))
    || (message.params !== undefined && !isObject(message.params))) {
    throw new WireError(400, -32600, 'Invalid request');
  }
  if (Object.hasOwn(message, 'id') && !(
    (typeof message.id === 'string' && message.id.length <= 256)
    || (Number.isSafeInteger(message.id)))) {
    throw new WireError(400, -32600, 'Invalid request ID');
  }
  return message;
}

export function decodeName(value) {
  if (typeof value !== 'string') return undefined;
  if (value.startsWith('=?base64?') && value.endsWith('?=')) {
    const payload = value.slice(9, -2);
    if (!/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(payload)) {
      throw new WireError(400, -32020, 'Invalid mirrored header');
    }
    try {
      const bytes = Buffer.from(payload, 'base64');
      if (bytes.toString('base64') !== payload) throw new Error('noncanonical');
      return new TextDecoder('utf-8', { fatal: true }).decode(bytes);
    } catch {
      throw new WireError(400, -32020, 'Invalid mirrored header');
    }
  }
  if (!/^[\x20-\x7e]+$/.test(value) || value.trim() !== value) {
    throw new WireError(400, -32020, 'Invalid mirrored header');
  }
  return value;
}

export function validateVersion(message, headers) {
  const params = message.params ?? {};
  const meta = params._meta;
  const headerVersion = headers['mcp-protocol-version'];
  // Legacy initialization is the only supported headerless handshake.
  const version = headerVersion ?? (message.method === 'initialize' ? params.protocolVersion : undefined);
  if (version === undefined) throw new WireError(400, -32020, 'Missing protocol header');
  if (!VERSIONS.includes(version)) {
    throw new WireError(400, -32022, 'Unsupported protocol version', {
      supported: VERSIONS, requested: String(version).slice(0, 128),
    });
  }
  if (version === MODERN) {
    if (headerVersion !== MODERN || !isObject(meta) || meta[VERSION_META] !== MODERN
      || headers['mcp-method'] !== message.method) {
      throw new WireError(400, -32020, 'Mirrored header mismatch');
    }
    if (!isObject(meta[CAPABILITIES_META])) {
      throw new WireError(400, -32602, 'Missing client capabilities');
    }
    const client = meta['io.modelcontextprotocol/clientInfo'];
    if (client !== undefined && (!isObject(client) || typeof client.name !== 'string'
      || typeof client.version !== 'string')) {
      throw new WireError(400, -32602, 'Invalid client information');
    }
    const named = ['tools/call', 'resources/read', 'prompts/get'].includes(message.method);
    if (named && decodeName(headers['mcp-name']) !== (message.method === 'resources/read' ? params.uri : params.name)) {
      throw new WireError(400, -32020, 'Mirrored header mismatch');
    }
    if (named && headers['mcp-name'] === undefined) {
      throw new WireError(400, -32020, 'Missing mirrored header');
    }
  } else {
    // Do not let mixed-era metadata bypass modern header/body validation.
    if (isObject(meta) && (VERSION_META in meta || CAPABILITIES_META in meta)) {
      throw new WireError(400, -32020, 'Mixed protocol eras');
    }
    if (message.method === 'initialize' && params.protocolVersion !== version) {
      throw new WireError(400, -32020, 'Initialization version mismatch');
    }
  }
  return version;
}

const emptyInput = { type: 'object', properties: {}, additionalProperties: false };
const tool = (name, description, inputSchema, readOnlyHint) => ({
  name, description, inputSchema,
  annotations: { readOnlyHint, destructiveHint: false, openWorldHint: false },
});
const CATALOG = [
  tool('auth_status', 'Return only this synthetic conversation authorization status.', emptyInput, true),
  tool('request_chat_authorization', 'Request a synthetic pending grant only when explicitly asked. '
    + 'No remote approval. Offline requests are suppressed; do not retry.', {
    type: 'object', properties: { scopes: { type: 'array', minItems: 1, maxItems: 1,
      items: { type: 'string', enum: ['workspace.read'] } } }, additionalProperties: false,
  }, false),
  tool('workspace_probe', 'Synthetic availability probe. No files or commands. '
    + 'Offline is a tool result, not an OAuth failure.', emptyInput, true),
];

export function catalog() {
  return structuredClone(CATALOG);
}

export function dispatchProtocol(message, version, state) {
  const params = message.params ?? {};
  const modern = version === MODERN;
  if (message.id === undefined) {
    if (!modern && message.method === 'notifications/initialized') return undefined;
    throw new WireError(400, -32600, 'Unsupported notification');
  }
  let result;
  switch (message.method) {
    case 'server/discover':
      if (!modern) throw new WireError(400, -32601, 'Method not found');
      result = complete(version, { supportedVersions: VERSIONS, capabilities: { tools: {} },
        instructions: INSTRUCTIONS });
      break;
    case 'initialize':
      if (modern) throw new WireError(404, -32601, 'Method not found');
      if (!isObject(params.capabilities) || !isObject(params.clientInfo)
        || typeof params.clientInfo.name !== 'string' || typeof params.clientInfo.version !== 'string') {
        throw new WireError(400, -32602, 'Invalid initialization');
      }
      result = { protocolVersion: version, capabilities: { tools: { listChanged: false } },
        serverInfo: SERVER_INFO, instructions: INSTRUCTIONS };
      break;
    case 'ping':
      if (modern) throw new WireError(404, -32601, 'Method not found');
      result = {};
      break;
    case 'tools/list':
      if (params.cursor !== undefined) throw new WireError(400, -32602, 'Invalid cursor');
      result = complete(version, { tools: catalog() });
      break;
    case 'tools/call': {
      if (typeof params.name !== 'string' || !CATALOG.some(t => t.name === params.name)) {
        throw new WireError(400, -32602, 'Unknown tool');
      }
      result = toolResult(version, state.call(params.name, params.arguments === undefined ? {} : params.arguments, params._meta?.['openai/session']));
      break;
    }
    default:
      throw new WireError(modern ? 404 : 400, -32601, 'Method not found');
  }
  return { jsonrpc: '2.0', id: message.id, result };
}
