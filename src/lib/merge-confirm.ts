// A1 C9-§6.2 merge-confirm (NARROW-B): local-only pending integrate/rollback cards.
// Consumes list_pending_integrations.pending[]; confirms via existing native digest cmds.
// C9 soft-nits: shared list with Attention; filesCount number-only; closedReason locks actions.
// No MCP expansion; no per-file diff preview; never echoes SECRET / error.message.
import { acquirePendingList } from '$lib/pending-integrations-shared';

export type PendingKind = 'integrate' | 'rollback' | string;

export type PendingCard = {
  integrationId: string;
  kind: PendingKind;
  label: string;
  diffShaShort: string;
  filesCount: string;
  expiresText: string;
  closedReasonText: string;
};

export type MergeConfirmView = {
  items: PendingCard[];
  busy: boolean;
  uncertain: boolean;
  unavailable: boolean;
  error: string;
  notice: string;
};

type Invoke = <T>(command: string, args: Record<string, unknown>) => Promise<T>;

type RawPending = {
  kind?: unknown;
  integration_id?: unknown;
  label?: unknown;
  diff_sha256?: unknown;
  files?: unknown;
  expires_at?: unknown;
  rollback_expires_at?: unknown;
  closed_reason?: unknown;
};

type ListReply = {
  ok?: boolean;
  pending?: RawPending[];
  recovery?: unknown;
  error?: { code?: string; message?: string };
} | null;

type ActionReply = {
  ok?: boolean;
  error?: { code?: string; message?: string };
} | null;

export const emptyMergeConfirmView = (): MergeConfirmView => ({
  items: [], busy: false, uncertain: false, unavailable: false, error: '', notice: '',
});

export const ROLLBACK_AVAILABLE_NOTICE = '可回滚（提交或下次合入后失效）';
export const DO_NOT_RETRY_ERROR = '本机操作未确认成功。不要重复提交；请重新打开工作区后核实。';

function text(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function shortDiffSha(value: unknown): string {
  const sha = text(value);
  if (!sha) return '—';
  return sha.length >= 12 ? sha.slice(0, 12) : sha;
}

/** Backend files is u64; reject string / non-finite → em dash. */
export function filesCount(value: unknown): string {
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  return '—';
}

/** Asia/Shanghai wall clock from unix-seconds; missing/0 → empty (no hint). */
export function formatExpiresAt(unixSeconds: unknown, timeZone = 'Asia/Shanghai'): string {
  if (typeof unixSeconds !== 'number' || !Number.isFinite(unixSeconds) || unixSeconds <= 0) return '';
  try {
    return new Intl.DateTimeFormat('zh-CN', {
      timeZone,
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
    }).format(new Date(unixSeconds * 1000));
  } catch {
    return '';
  }
}

/** Map closed_reason codes to fixed Chinese; never echo ids or raw blobs. */
export function closedReasonLabel(reason: unknown): string {
  const code = text(reason);
  if (!code) return '';
  if (code === 'head_moved') return '主工作区已变更，回滚窗口已关闭';
  if (code === 'superseded') return '已被后续合入取代，回滚窗口已关闭';
  if (code === 'not_committed') return '未处于可回滚状态';
  return '回滚窗口已关闭';
}

export function mapPendingCard(raw: RawPending): PendingCard {
  const kind = text(raw.kind) || 'integrate';
  const expiresSource = kind === 'rollback' ? raw.rollback_expires_at : raw.expires_at;
  const expiresAt = formatExpiresAt(expiresSource);
  return {
    integrationId: text(raw.integration_id),
    kind,
    label: text(raw.label) || '—',
    diffShaShort: shortDiffSha(raw.diff_sha256),
    filesCount: filesCount(raw.files),
    expiresText: expiresAt ? `将于 ${expiresAt} 失效` : '',
    closedReasonText: closedReasonLabel(raw.closed_reason),
  };
}

/** Soft nit: closed_reason text locks confirm/reject together with busy/uncertain. */
export function actionsDisabled(view: Pick<MergeConfirmView, 'busy' | 'uncertain'>, card: Pick<PendingCard, 'closedReasonText'>): boolean {
  return view.busy || view.uncertain || !!card.closedReasonText;
}

function actionError(reply: ActionReply): string {
  const code = reply && reply.ok === false ? reply.error?.code : undefined;
  if (code === 'WORKER_STATE') return '当前状态不允许该操作。';
  if (code === 'WORKER_NOT_OWNED') return '未找到该待确认项。';
  if (code === 'OWNER_CONFIRMATION_REQUIRED') return '确认信息不匹配，未做任何更改。请重新打开后重试。';
  if (code === 'DIRTY') return '工作树有未提交改动，无法继续。';
  if (code === 'ROLLBACK_EXPIRED') return '回滚窗口已关闭。';
  if (code === 'ROLLBACK_CONFLICT') return '回滚内容与记录不符，已拒绝。';
  return '操作未完成。请在本机检查后重试。';
}

export function createMergeConfirmController(
  id: string,
  invoke: Invoke,
  publish: (view: MergeConfirmView) => void,
) {
  let alive = true, loaded = false;
  let view = emptyMergeConfirmView();
  const pending = acquirePendingList(id, invoke);
  const emit = (patch: Partial<MergeConfirmView>) => {
    if (!alive) return;
    view = { ...view, ...patch };
    publish(view);
  };

  async function applyList(reply: ListReply) {
    if (!alive) return;
    if (reply && reply.ok === false) {
      emit({ items: [], unavailable: true, error: '无法列出待确认项。请重新打开工作区后重试。' });
      return;
    }
    const items = Array.isArray(reply?.pending)
      ? reply!.pending!.map(mapPendingCard).filter(card => !!card.integrationId)
      : [];
    emit({ items, unavailable: false, error: '' });
  }

  async function refresh() {
    if (!alive) return;
    try {
      const reply = await pending.listFresh<ListReply>();
      await applyList(reply);
    } catch {
      if (alive) emit({ items: [], unavailable: true, error: '工作区监听未就绪，暂无法列出待确认项。' });
    }
  }

  async function load() {
    if (!alive || loaded) return;
    loaded = true;
    try {
      const reply = await pending.listOnce<ListReply>();
      await applyList(reply);
    } catch {
      if (alive) emit({ items: [], unavailable: true, error: '工作区监听未就绪，暂无法列出待确认项。' });
    }
  }

  function cardLocked(integrationId: string): boolean {
    const card = view.items.find(c => c.integrationId === integrationId);
    return !!card?.closedReasonText;
  }

  async function confirm(integrationId: string, kind: PendingKind) {
    if (!alive || !integrationId || view.busy || view.uncertain || view.unavailable || cardLocked(integrationId)) return;
    emit({ busy: true, error: '', notice: '' });
    try {
      const command = kind === 'rollback' ? 'confirm_subagent_rollback' : 'confirm_subagent_integration';
      const reply = await invoke<ActionReply | null>(command, { id, integrationId });
      if (!alive) return;
      if (reply === null) {
        emit({ notice: '已取消。未做任何更改。' });
      } else if (reply && reply.ok === false) {
        const error = actionError(reply);
        loaded = false;
        await refresh();
        if (alive) emit({ error });
      } else {
        emit({ notice: kind === 'rollback' ? '已回滚。' : ROLLBACK_AVAILABLE_NOTICE });
        loaded = false;
        await refresh();
      }
    } catch {
      emit({ uncertain: true, error: DO_NOT_RETRY_ERROR });
    } finally {
      emit({ busy: false });
    }
  }

  async function reject(integrationId: string, kind: PendingKind) {
    if (!alive || !integrationId || view.busy || view.uncertain || view.unavailable || cardLocked(integrationId)) return;
    emit({ busy: true, error: '', notice: '' });
    try {
      const command = kind === 'rollback' ? 'reject_subagent_rollback' : 'reject_subagent_integration';
      const reply = await invoke<ActionReply>(command, { id, integrationId });
      if (!alive) return;
      if (reply && reply.ok === false) {
        const error = actionError(reply);
        loaded = false;
        await refresh();
        if (alive) emit({ error });
      } else {
        emit({ notice: '已拒绝。' });
        loaded = false;
        await refresh();
      }
    } catch {
      emit({ uncertain: true, error: DO_NOT_RETRY_ERROR });
    } finally {
      emit({ busy: false });
    }
  }

  return {
    load,
    confirm,
    reject,
    dispose() {
      alive = false;
      pending.release();
    },
  };
}
