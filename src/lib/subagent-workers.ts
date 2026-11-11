// A1 C9-ui-remainder §6.1 (NARROW-B): local-only subagent worker cards.
// List via list_subagent_workers; optional cancel/discard thin wraps. No merge UI.
export type WorkerStateLabel =
  | 'creating' | 'ready' | 'cancelled' | 'failed'
  | 'pending_cleanup' | 'discarded' | 'integrate_pending' | 'integrated'
  | string;

export type WorkerCard = {
  workerId: string;
  label: string;
  state: WorkerStateLabel;
  baseHeadShort: string;
  lastActivityText: string;
  changedFilesText: string;
  windowsUnsandboxed: boolean;
  linuxSandboxDeferred: boolean;
};

export type WorkersView = {
  workers: WorkerCard[];
  busy: boolean;
  uncertain: boolean;
  unavailable: boolean;
  error: string;
  notice: string;
};

type Invoke = <T>(command: string, args: Record<string, unknown>) => Promise<T>;
type Confirm = (message: string, options?: Record<string, unknown>) => Promise<boolean>;
type RawWorker = {
  worker_id?: unknown;
  label?: unknown;
  state?: unknown;
  base_head?: unknown;
  last_activity_at?: unknown;
  changed_files?: unknown;
  cwd?: unknown;
};
type ListReply = { ok?: boolean; workers?: RawWorker[]; windows?: boolean; error?: { code?: string; message?: string } } | null;
type ActionReply = { ok?: boolean; worker?: RawWorker; error?: { code?: string; message?: string } } | null;

/** SPEC §6.1 Windows card label; distinct from the authorization-panel warning sentence. */
export const WINDOWS_UNSANDBOXED_CARD_LABEL = '无沙箱 · 用户默认权限';
export const LINUX_SANDBOX_DEFERRED_LABEL = 'Linux 沙箱标签延后';

export const workerStateLabels: Record<string, string> = {
  creating: '创建中',
  ready: '就绪',
  cancelled: '已取消',
  failed: '失败',
  pending_cleanup: '待清理',
  discarded: '已丢弃',
  integrate_pending: '待合入',
  integrated: '已合入',
};

export const emptyWorkersView = (): WorkersView => ({
  workers: [], busy: false, uncertain: false, unavailable: false, error: '', notice: '',
});

function text(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function shortSha(value: unknown): string {
  const sha = text(value);
  if (!sha) return '—';
  return sha.length >= 7 ? sha.slice(0, 7) : sha;
}

/** Asia/Shanghai wall clock from a unix-seconds activity stamp; missing → — */
export function formatActivityAt(unixSeconds: unknown, timeZone = 'Asia/Shanghai'): string {
  if (typeof unixSeconds !== 'number' || !Number.isFinite(unixSeconds) || unixSeconds <= 0) return '—';
  try {
    return new Intl.DateTimeFormat('zh-CN', {
      timeZone,
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
    }).format(new Date(unixSeconds * 1000));
  } catch {
    return '—';
  }
}

/** A1 C11: only finite non-negative integers render as "N（快照）"; else "—". */
export function formatChangedFiles(changed: unknown): string {
  if (typeof changed === 'number' && Number.isInteger(changed) && changed >= 0) {
    return `${changed}（快照）`;
  }
  return '—';
}

export function mapWorkerCard(raw: RawWorker, windows: boolean): WorkerCard {
  return {
    workerId: text(raw.worker_id),
    label: text(raw.label) || '—',
    state: (text(raw.state) || '—') as WorkerStateLabel,
    baseHeadShort: shortSha(raw.base_head),
    lastActivityText: formatActivityAt(raw.last_activity_at),
    changedFilesText: formatChangedFiles(raw.changed_files),
    windowsUnsandboxed: windows,
    linuxSandboxDeferred: !windows,
  };
}

function actionError(reply: ActionReply): string {
  const code = reply && reply.ok === false ? reply.error?.code : undefined;
  if (code === 'DIRTY') return '工作树有未提交改动，无法丢弃。请先处理改动后再试。';
  if (code === 'WORKER_STATE') return '当前状态不允许该操作。';
  if (code === 'WORKER_BUSY') return '子代理仍有运行中的命令，请先停止后再丢弃。';
  if (code === 'WORKER_NOT_OWNED') return '未找到该子代理。';
  return '操作未完成。请在本机检查后重试。';
}

export function createSubagentWorkersController(
  id: string,
  invoke: Invoke,
  publish: (view: WorkersView) => void,
  confirmFn?: Confirm,
) {
  let alive = true, loaded = false;
  let view = emptyWorkersView();
  const emit = (patch: Partial<WorkersView>) => {
    if (!alive) return;
    view = { ...view, ...patch };
    publish(view);
  };

  async function load() {
    if (!alive || loaded) return;
    loaded = true;
    try {
      const reply = await invoke<ListReply>('list_subagent_workers', { id });
      if (!alive) return;
      if (reply && reply.ok === false) {
        emit({ workers: [], unavailable: true, error: '无法列出子代理。请重新打开工作区后重试。' });
        return;
      }
      const windows = reply?.windows === true;
      const workers = Array.isArray(reply?.workers)
        ? reply!.workers!.map(row => mapWorkerCard(row, windows))
        : [];
      emit({ workers, unavailable: false, error: '' });
    } catch {
      // listener not running: fail closed, show unavailable (no SECRET echo)
      if (alive) emit({ workers: [], unavailable: true, error: '工作区监听未就绪，暂无法列出子代理。' });
    }
  }

  async function cancel(workerId: string) {
    if (!alive || !workerId || view.busy || view.uncertain) return;
    emit({ busy: true, error: '', notice: '' });
    try {
      const reply = await invoke<ActionReply>('cancel_subagent_worker', { id, workerId });
      if (!alive) return;
      if (reply && reply.ok === false) {
        const error = actionError(reply);
        loaded = false;
        await load();
        if (alive) emit({ error });
      } else {
        emit({ notice: '已请求取消。' });
        loaded = false;
        await load();
      }
    } catch {
      emit({ uncertain: true, error: '本机操作未确认成功。不要重复提交；请重新打开工作区后核实。' });
    } finally {
      emit({ busy: false });
    }
  }

  async function discard(workerId: string) {
    if (!alive || !workerId || view.busy || view.uncertain) return;
    // busy before confirm so double-clicks cannot race two native discards
    emit({ busy: true, error: '', notice: '' });
    try {
      const approved = confirmFn
        ? await confirmFn(
            '丢弃将删除该子代理的工作树。若有未提交改动，后端会拒绝丢弃。确定继续？',
            { title: '丢弃子代理', kind: 'warning', okLabel: '丢弃', cancelLabel: '取消' },
          )
        : true;
      if (!alive || !approved) {
        if (alive) emit({ notice: '已取消丢弃。' });
        return;
      }
      const reply = await invoke<ActionReply>('discard_subagent_worker', { id, workerId });
      if (!alive) return;
      if (reply && reply.ok === false) {
        const error = actionError(reply);
        loaded = false;
        await load();
        if (alive) emit({ error });
      } else {
        emit({ notice: '已丢弃。' });
        loaded = false;
        await load();
      }
    } catch {
      emit({ uncertain: true, error: '本机操作未确认成功。不要重复提交；请重新打开工作区后核实。' });
    } finally {
      emit({ busy: false });
    }
  }

  return {
    load,
    cancel,
    discard,
    dispose() { alive = false; },
  };
}
