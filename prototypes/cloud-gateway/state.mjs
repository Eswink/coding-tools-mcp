/** In-memory SYNTHETIC state only. No OAuth, devices, files or process execution. */
import { createHmac, randomBytes } from 'node:crypto';
import { isObject } from './protocol.mjs';

const messages = Object.freeze({
  WORKSPACE_OFFLINE: 'Workspace execution is unavailable. Do not retry or request OAuth.',
  EXECUTION_OUTCOME_UNKNOWN: 'Execution outcome is unknown. Do not resubmit; reconcile the original request.',
  CHAT_CONTEXT_REQUIRED: 'Conversation context is required.',
  CHAT_RECOVERY_REQUIRED: 'Workspace authorization is unavailable. Do not retry.',
  EXCLUSIVE_CHAT_LOCKED: 'Workspace is unavailable to this conversation. Do not retry or request approval.',
  CHAT_AUTHORIZATION_REQUIRED: 'This conversation is not approved.',
  CHAT_SCOPE_REQUIRED: 'This conversation lacks the required scope.',
  CHAT_AUTHORIZATION_UNAVAILABLE: 'New authorization requests are not accepted. Do not retry.',
  INVALID_ARGUMENTS: 'Invalid tool arguments.',
  AUTHORIZATION_CAPACITY_REACHED: 'Authorization capacity reached. Do not retry.',
});

export function denial(code) {
  const availability = code === 'WORKSPACE_OFFLINE' || code === 'EXECUTION_OUTCOME_UNKNOWN';
  return { ok: false, error: { code, category: availability ? 'availability' : 'permission',
    retryable: false, message: messages[code] }, requires_local_action: false };
}

export class SyntheticWorkspace {
  #key = randomBytes(32);
  #records = new Map();
  #owner = null;
  #online = false;
  #recovery = false;
  #unknown = false;
  #dispatches = 0;
  #allocations = 0;
  #clock;

  constructor({ clock = () => performance.now() } = {}) { this.#clock = clock; }

  #binding(session) {
    if (typeof session !== 'string' || session.length === 0 || session.length > 256
      || /[\x00-\x1f\x7f]/.test(session)) return null;
    return createHmac('sha256', this.#key)
      .update(JSON.stringify(['lab-principal', 'lab-workspace', session])).digest('hex');
  }

  // Fixture administration is import-only; NEVER exposed as an HTTP RPC/tool.
  setOnlineForTest(online) { this.#online = online === true; }
  setRecoveryForTest(required) { this.#recovery = required === true; }
  setUnknownOutcomeForTest(unknown) { this.#unknown = unknown === true; }
  approveForTest(session, { scopes = ['workspace.read'], ttlMs = 86_400_000 } = {}) {
    const binding = this.#binding(session);
    if (!binding || !Number.isFinite(ttlMs) || ttlMs <= 0
      || !Array.isArray(scopes) || scopes.some(s => s !== 'workspace.read')) {
      throw new TypeError('Invalid synthetic grant');
    }
    if (!this.#records.has(binding) && this.#records.size >= 64) throw new Error('Fixture capacity reached');
    this.#records.set(binding, { status: 'active', scopes: [...scopes], expires: this.#clock() + ttlMs });
    this.#owner = binding;
  }
  revokeForTest(session) {
    const record = this.#records.get(this.#binding(session));
    if (record) record.status = 'revoked';
    // Owner is deliberately retained; this does not claim real task draining.
  }
  statsForTest() { return { dispatches: this.#dispatches, pendingAllocations: this.#allocations }; }

  call(name, args, session) {
    const binding = this.#binding(session);
    if (!binding) return denial('CHAT_CONTEXT_REQUIRED');
    if (this.#recovery) return denial('CHAT_RECOVERY_REQUIRED');
    if (this.#owner && this.#owner !== binding) return denial('EXCLUSIVE_CHAT_LOCKED');
    const record = this.#records.get(binding);
    if (record && record.expires <= this.#clock() && ['active', 'pending'].includes(record.status)) {
      record.status = 'expired';
    }
    if (!isObject(args)) return denial('INVALID_ARGUMENTS');
    if (name === 'request_chat_authorization') return this.#request(binding, record, args);
    if (Object.keys(args).length !== 0) return denial('INVALID_ARGUMENTS');
    if (name === 'auth_status') return { ok: true, authorization: { status: record?.status ?? 'unauthorized' } };
    if (record?.status !== 'active') return denial('CHAT_AUTHORIZATION_REQUIRED');
    if (!record.scopes.includes('workspace.read')) return denial('CHAT_SCOPE_REQUIRED');
    if (!this.#online) return denial('WORKSPACE_OFFLINE');
    this.#dispatches += 1;
    if (this.#unknown) return denial('EXECUTION_OUTCOME_UNKNOWN');
    return { ok: true, synthetic: true, message: 'Synthetic worker responded; no local operation was performed.' };
  }

  #request(binding, record, args) {
    if (Object.keys(args).some(k => k !== 'scopes') || (args.scopes !== undefined
      && (!Array.isArray(args.scopes) || args.scopes.length !== 1 || args.scopes[0] !== 'workspace.read'))) {
      return denial('INVALID_ARGUMENTS');
    }
    if (record && ['pending', 'active'].includes(record.status)) {
      return { ok: true, authorization: { status: record.status } };
    }
    if (!this.#online) return denial('CHAT_AUTHORIZATION_UNAVAILABLE');
    if (!record && this.#records.size >= 64) return denial('AUTHORIZATION_CAPACITY_REACHED');
    this.#records.set(binding, { status: 'pending', scopes: ['workspace.read'], expires: this.#clock() + 90_000 });
    this.#owner = binding;
    this.#allocations += 1;
    return { ok: true, authorization: { status: 'pending' }, synthetic: true };
  }
}
