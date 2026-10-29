/** Local owner IPC only. A preview or OAuth identity never grants execution. */
export type HookStatus = { enabled: boolean; count?: number; recovery_required?: boolean };
export type HookPreview = {
  pending_id: string; expires_in_seconds: number; native_dialog_required: true;
  preview: { digest: string; hooks: { manifest: Record<string, unknown>; executable_sha256: string; script_sha256: string | null; script_source: string | null }[]; runtime_only: true; network_allowed: false; requires_local_conversation_authority: true };
};
export type HookView = { status: HookStatus | null; pending: HookPreview | null; expiresAt: number; busy: boolean; uncertain: boolean; error: string; notice: string };
type Invoke = <T>(command: string, args: Record<string, unknown>) => Promise<T>;
export const emptyHookView = (): HookView => ({ status: null, pending: null, expiresAt: 0, busy: false, uncertain: false, error: '', notice: '' });
const digest = (value: unknown) => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
function status(value: HookStatus): HookStatus {
  if (!value || typeof value.enabled !== 'boolean' || (value.count !== undefined && (!Number.isInteger(value.count) || value.count < 0 || value.count > 8)) || (value.recovery_required !== undefined && typeof value.recovery_required !== 'boolean')) throw Error('Invalid status');
  return value;
}
function preview(value: HookPreview): HookPreview {
  const p = value?.preview;
  if (!value || typeof value.pending_id !== 'string' || !/^[a-f0-9-]{36}$/.test(value.pending_id) || value.native_dialog_required !== true || !Number.isFinite(value.expires_in_seconds) || value.expires_in_seconds <= 0 || value.expires_in_seconds > 60 || !p || !digest(p.digest) || !Array.isArray(p.hooks) || p.hooks.length > 8 || p.runtime_only !== true || p.network_allowed !== false || p.requires_local_conversation_authority !== true) throw Error('Invalid preview');
  for (const h of p.hooks) if (!h || !h.manifest || typeof h.manifest !== 'object' || !digest(h.executable_sha256) || (h.script_sha256 !== null && !digest(h.script_sha256)) || (h.script_source !== null && (typeof h.script_source !== 'string' || new TextEncoder().encode(h.script_source).length > 65536))) throw Error('Invalid hook');
  return value;
}
export function createHookController(id: string, invoke: Invoke, publish: (value: HookView) => void, clock = Date.now) {
  let alive = true, revision = 0, reading = false;
  let view = emptyHookView();
  const emit = (patch: Partial<HookView>) => { if (alive) { view = { ...view, ...patch }; publish(view); } };
  async function refresh() {
    if (!alive || reading || view.busy) return;
    reading = true; const ticket = revision;
    try { const result = status(await invoke<HookStatus>('get_policy_hooks', { id })); if (alive && ticket === revision) emit({ status: result, error: '' }); }
    catch { if (alive && ticket === revision) emit({ status: null, error: '无法确认本机 Hooks 状态。请先检查 MCP 服务，再手动刷新。' }); }
    finally { reading = false; }
  }
  function discard() { if (!alive || view.busy) return; ++revision; emit({ pending: null, expiresAt: 0, notice: '本次预览已放弃；本机待确认项最多 60 秒后失效。' }); }
  async function prepare(text: string) {
    if (!alive || view.busy || view.uncertain || view.status?.recovery_required) return;
    ++revision; emit({ busy: true, pending: null, error: '', notice: '' });
    try {
      if (new TextEncoder().encode(text).length > 8192) throw Error('Limit');
      const specs: unknown = JSON.parse(text);
      if (!Array.isArray(specs) || specs.length < 1 || specs.length > 8) throw Error('Manifest');
      const result = preview(await invoke<HookPreview>('preview_policy_hooks', { id, specs }));
      emit({ pending: result, expiresAt: clock() + result.expires_in_seconds * 1000 });
    } catch { emit({ error: '预览未完成。请检查 JSON 清单、路径、执行策略和本机服务；未批准 Hooks。' }); }
    finally { emit({ busy: false }); }
  }
  async function approve(reviewed: boolean) {
    if (!alive || view.busy || view.uncertain || !reviewed || !view.pending || view.status?.recovery_required) return;
    if (clock() >= view.expiresAt) { discard(); emit({ error: '预览已过期，请重新生成并核对。' }); return; }
    const selected = view.pending; ++revision;
    emit({ busy: true, pending: null, expiresAt: 0, error: '', notice: '' });
    try {
      const result = await invoke<HookStatus | null>('approve_policy_hooks', { id, pendingId: selected.pending_id, digest: selected.preview.digest });
      if (result === null) emit({ notice: '已取消本机确认。若要继续，请重新生成预览。' });
      else emit({ status: status(result), notice: '本机已批准当前清单。执行仍受聊天授权、策略和沙箱约束。' });
    } catch { emit({ uncertain: true, status: null, error: '批准结果不确定。不会重试或再次提交；请刷新并在本机核实。' }); }
    finally { emit({ busy: false }); }
  }
  async function disable() {
    if (!alive || view.busy) return;
    ++revision; emit({ busy: true, pending: null, expiresAt: 0, error: '', notice: '' });
    try { emit({ status: status(await invoke<HookStatus>('disable_policy_hooks', { id })), notice: '已停用 Hooks。停用不会清除未知执行结果或恢复锁定。' }); }
    catch { emit({ uncertain: true, status: null, error: '停用结果不确定。请在本机核实；不会自动重试。' }); }
    finally { emit({ busy: false }); }
  }
  return { refresh, prepare, approve, disable, discard, dispose() { alive = false; ++revision; view = emptyHookView(); } };
}
