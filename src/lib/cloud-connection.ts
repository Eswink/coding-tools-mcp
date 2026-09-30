/** Native IPC only. Transport connectivity never grants local execution authority. */
export type CloudPhase = 'unconfigured' | 'configured' | 'starting' | 'connected' | 'pending_approval' | 'approved' | 'paused' | 'draining' | 'recovery';
export type CloudStatus = { phase: CloudPhase; connected: boolean; generation: number | null; configured: boolean };
export type CloudView = { status: CloudStatus | null; busy: boolean; error: string; uncertain: boolean };
type Invoke = <T>(command: string, args: Record<string, unknown>) => Promise<T>;
export const cloudPhaseLabels: Record<CloudPhase, string> = {
  unconfigured: '未配置', configured: '已配置 · 未连接', starting: '正在连接', connected: '已连接 · 未授权',
  pending_approval: '待本机批准', approved: '本机已授权', paused: '远程执行已暂停', draining: '正在排空', recovery: '恢复锁定'
};
function checkedStatus(value: CloudStatus): CloudStatus {
  if (!value || !Object.hasOwn(cloudPhaseLabels, value.phase) || typeof value.connected !== 'boolean' || typeof value.configured !== 'boolean') throw new Error('Invalid native status');
  return value;
}
export function canStartCloud(view: CloudView): boolean {
  return !view.busy && !view.uncertain && !!view.status?.configured && !view.status.connected && view.status.phase === 'configured';
}
export function createCloudConnectionController(id: string, invoke: Invoke, publish: (view: CloudView) => void) {
  let alive = true, revision = 0, reading = false;
  let view: CloudView = { status: null, busy: false, error: '', uncertain: false };
  const emit = (patch: Partial<CloudView>) => { if (alive) { view = { ...view, ...patch }; publish(view); } };
  async function refresh() {
    if (!alive || reading || view.busy) return;
    reading = true;
    const ticket = revision;
    try {
      const status = checkedStatus(await invoke<CloudStatus>('get_cloud_connection_status', { id }));
      if (alive && ticket === revision) emit({ status, error: '' });
    } catch { if (alive && ticket === revision) emit({ status: null, error: '无法确认本机连接状态。请检查本机后刷新；不会自动重试连接。' }); }
    finally { reading = false; }
  }
  async function operate(kind: 'start' | 'initialize' | 'stop' | 'import', authorize: () => Promise<boolean>, selectFiles?: (stillActive: () => boolean) => Promise<{ configPath: string; privateKeyPath: string } | null>) {
    if (!alive || view.busy) return;
    if ((kind === 'start' || kind === 'initialize') && !canStartCloud(view)) return;
    if (kind === 'import' && (view.status?.configured !== false || view.uncertain)) return;
    if (kind === 'stop' && !view.status) return;
    ++revision; emit({ busy: true, error: '' });
    let submitted = false;
    try {
      if (!await authorize() || !alive) return;
      if (kind === 'import') {
        const files = await selectFiles?.(() => alive);
        if (!alive || !files) return;
        submitted = true;
        await invoke('import_cloud_connection_files', { id, ...files });
        if (alive) emit({ status: checkedStatus(await invoke<CloudStatus>('get_cloud_connection_status', { id })) });
      } else {
        submitted = true;
        const command = kind === 'stop' ? 'stop_cloud_connection' : 'start_cloud_connection';
        const args = kind === 'stop' ? { id } : { id, initializeJournals: kind === 'initialize' };
        const status = checkedStatus(await invoke<CloudStatus>(command, args));
        if (alive) emit({ status });
      }
    } catch {
      // Never render arbitrary native errors: they may contain credential content or paths.
      emit({ uncertain: submitted || view.uncertain, status: null, error: submitted
        ? '操作结果尚未确认。请刷新并在本机核实；本面板不会重试启动、导入或初始化。需要恢复时请重新打开面板。'
        : '本机确认或文件选择未完成。未提交连接操作。' });
    } finally { emit({ busy: false }); }
  }
  return { refresh, operate, dispose() { alive = false; ++revision; } };
}
