// A1 C9-2 (SPEC-A1 §0.9 nit 1, §5.1): one list_pending_integrations call when a
// workspace profile loads (it runs recovery first, so it is the startup scan),
// and the owner's local-only clear of a `needs_attention` journal. The clear is
// confirmed in a native dialog by the Rust command; this controller only asks.
export type AttentionView = { attention: boolean; busy: boolean; uncertain: boolean; error: string; notice: string };
type Invoke = <T>(command: string, args: Record<string, unknown>) => Promise<T>;
type Reply = { ok?: boolean; error?: { code?: string }; recovery?: { state?: string; journal?: string }; state?: string } | null;
export const emptyAttentionView = (): AttentionView => ({ attention: false, busy: false, uncertain: false, error: '', notice: '' });
export function needsAttention(reply: Reply): boolean {
  const recovery = reply && reply.ok !== false ? reply.recovery : undefined;
  return recovery?.state === 'needs_attention' || recovery?.journal === 'needs_attention';
}
export function createIntegrationAttentionController(id: string, invoke: Invoke, publish: (view: AttentionView) => void) {
  let alive = true, loaded = false;
  let view = emptyAttentionView();
  const emit = (patch: Partial<AttentionView>) => { if (alive) { view = { ...view, ...patch }; publish(view); } };
  async function load() {
    if (!alive || loaded) return;
    loaded = true;
    try {
      const reply = await invoke<Reply>('list_pending_integrations', { id });
      if (alive) emit({ attention: needsAttention(reply) });
    } catch { /* listener not running: no scan this load, nothing shown */ }
  }
  async function clear() {
    if (!alive || !view.attention || view.busy || view.uncertain) return;
    emit({ busy: true, error: '', notice: '' });
    try {
      const reply = await invoke<Reply>('clear_integration_attention', { id });
      if (!alive) return;
      if (reply === null) emit({ notice: '已取消。合并日志仍需处理，未做任何更改。' });
      else if (reply.ok === false && reply.error?.code === 'WORKER_STATE') emit({ attention: false, notice: '合并日志已不需要处理。' });
      else if (reply.ok === false) emit({ error: '无法清除合并日志。请在本机检查后重试。' });
      else emit({ attention: false, notice: '已清除。合并日志已回到空闲，暂存的原内容已丢弃；未写入任何工作区文件。' });
    } catch {
      emit({ uncertain: true, error: '本机操作未确认成功。不要重复提交；请重新打开工作区后核实。' });
    } finally { emit({ busy: false }); }
  }
  return { load, clear, dispose() { alive = false; } };
}
