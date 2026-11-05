// A1 C17 NARROW-B: local-only legacy worktree cleanup panel.
// Invokes existing preview_legacy_cleanup / apply_legacy_cleanup only.
// Native owner confirm lives inside apply; FE must not add a second confirm.
// Never echoes SECRET / absolute paths / error.message blobs into the view.

export type LegacyCandidateCard = {
  id: string;
  displayPath: string;
  headShort: string;
  clean: boolean;
  interrupted: boolean;
  hint: string;
  /** Dirty rows cannot be selected (BE skips dirty). */
  selectable: boolean;
  /** LOCKED/PINNED still selectable but confirm will Failed with zero deletion. */
  hintWarn: boolean;
};

export type LegacyWarningCard = {
  id: string;
  code: string;
};

export type LegacyOutcomeCard = {
  id: string;
  state: string;
  code: string;
};

export type LegacyCleanupView = {
  candidates: LegacyCandidateCard[];
  selectedIds: string[];
  digest: string;
  warnings: LegacyWarningCard[];
  nativeDialogRequired: boolean;
  outcomes: LegacyOutcomeCard[];
  busy: boolean;
  uncertain: boolean;
  error: string;
  notice: string;
};

type Invoke = <T>(command: string, args: Record<string, unknown>) => Promise<T>;

type RawCandidate = {
  id?: unknown;
  display_path?: unknown;
  head_short?: unknown;
  head?: unknown;
  clean?: unknown;
  interrupted?: unknown;
  hint?: unknown;
};

type RawWarning = { id?: unknown; code?: unknown };
type RawOutcome = { id?: unknown; state?: unknown; code?: unknown };

type PreviewReply = {
  candidates?: RawCandidate[];
  digest?: unknown;
  warnings?: RawWarning[];
  native_dialog_required?: unknown;
} | null;

type ApplyReply = { outcomes?: RawOutcome[] } | null;

export const emptyLegacyCleanupView = (): LegacyCleanupView => ({
  candidates: [],
  selectedIds: [],
  digest: '',
  warnings: [],
  nativeDialogRequired: false,
  outcomes: [],
  busy: false,
  uncertain: false,
  error: '',
  notice: '',
});

export const DO_NOT_RETRY_ERROR = '本机操作未确认成功。不要重复提交；请重新打开工作区后核实。';
export const STALE_ERROR = '候选列表已变更。请重新预览后再勾选清理。';
export const HINT_FAILED_WARN = '确认会 Failed、零删除';
export const CANCEL_NOTICE = '已取消。未做任何更改。';

function text(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function bool(value: unknown): boolean {
  return value === true;
}

/** Map a preview candidate; never copies absolute path fields. */
export function mapCandidate(raw: RawCandidate): LegacyCandidateCard {
  const hint = text(raw.hint);
  const clean = bool(raw.clean);
  const hintWarn = hint === 'LOCKED' || hint === 'PINNED';
  return {
    id: text(raw.id),
    displayPath: text(raw.display_path) || '—',
    headShort: text(raw.head_short) || text(raw.head) || '—',
    clean,
    interrupted: bool(raw.interrupted),
    hint,
    selectable: clean,
    hintWarn,
  };
}

export function mapWarning(raw: RawWarning): LegacyWarningCard {
  return { id: text(raw.id), code: text(raw.code) || '—' };
}

export function mapOutcome(raw: RawOutcome): LegacyOutcomeCard {
  return {
    id: text(raw.id),
    state: text(raw.state) || '—',
    code: text(raw.code),
  };
}

export function isStaleError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error ?? '');
  return message.includes('STALE_CONFIRMATION');
}

export function actionsDisabled(view: Pick<LegacyCleanupView, 'busy' | 'uncertain'>): boolean {
  return view.busy || view.uncertain;
}

export function cleanupDisabled(
  view: Pick<LegacyCleanupView, 'busy' | 'uncertain' | 'selectedIds' | 'digest'>,
): boolean {
  return actionsDisabled(view) || view.selectedIds.length === 0 || !view.digest;
}

export function createLegacyCleanupController(
  sourceId: string,
  invoke: Invoke,
  publish: (view: LegacyCleanupView) => void,
) {
  let alive = true;
  let view = emptyLegacyCleanupView();
  const emit = (patch: Partial<LegacyCleanupView>) => {
    if (!alive) return;
    view = { ...view, ...patch };
    publish(view);
  };

  function applyPreview(reply: PreviewReply, keepOutcomes = false) {
    const candidates = Array.isArray(reply?.candidates)
      ? reply!.candidates!.map(mapCandidate).filter(c => !!c.id)
      : [];
    const warnings = Array.isArray(reply?.warnings)
      ? reply!.warnings!.map(mapWarning)
      : [];
    emit({
      candidates,
      selectedIds: [],
      digest: text(reply?.digest),
      warnings,
      nativeDialogRequired: reply?.native_dialog_required === true,
      outcomes: keepOutcomes ? view.outcomes : [],
      error: '',
    });
  }

  async function refresh() {
    if (!alive || view.busy || view.uncertain) return;
    emit({ busy: true, error: '', notice: '' });
    try {
      const reply = await invoke<PreviewReply>('preview_legacy_cleanup', { sourceId });
      if (!alive) return;
      applyPreview(reply);
    } catch {
      if (alive) {
        emit({
          candidates: [],
          selectedIds: [],
          digest: '',
          warnings: [],
          outcomes: [],
          error: '无法预览旧版 worktree。请在本机检查后重试。',
        });
      }
    } finally {
      emit({ busy: false });
    }
  }

  function setSelected(id: string, selected: boolean) {
    if (!alive || view.busy || view.uncertain) return;
    const card = view.candidates.find(c => c.id === id);
    if (!card || !card.selectable) return;
    const next = new Set(view.selectedIds);
    if (selected) next.add(id);
    else next.delete(id);
    emit({ selectedIds: [...next], notice: '', error: '' });
  }

  async function apply() {
    if (!alive || cleanupDisabled(view)) return;
    const ids = [...view.selectedIds];
    const digest = view.digest;
    emit({ busy: true, error: '', notice: '', outcomes: [] });
    try {
      const reply = await invoke<ApplyReply>('apply_legacy_cleanup', {
        sourceId,
        ids,
        digest,
      });
      if (!alive) return;
      // Condition 2: null = user cancel → notice, NOT uncertain.
      if (reply === null) {
        emit({ notice: CANCEL_NOTICE });
        return;
      }
      const outcomes = Array.isArray(reply?.outcomes)
        ? reply!.outcomes!.map(mapOutcome)
        : [];
      emit({
        notice: '清理已完成。请核对下方结果。',
        outcomes,
        selectedIds: [],
      });
      // Condition 4: show outcomes, refresh preview, clear selection.
      try {
        const preview = await invoke<PreviewReply>('preview_legacy_cleanup', { sourceId });
        if (!alive) return;
        applyPreview(preview, true);
        emit({ outcomes, selectedIds: [], notice: '清理已完成。请核对下方结果。' });
      } catch {
        if (alive) {
          emit({
            error: '清理已完成，但无法刷新预览。请手动刷新。',
            outcomes,
            selectedIds: [],
          });
        }
      }
    } catch (error) {
      if (!alive) return;
      // Condition 2: STALE clears selection and prompts re-preview (not uncertain).
      if (isStaleError(error)) {
        emit({
          error: STALE_ERROR,
          selectedIds: [],
          digest: '',
          candidates: [],
          outcomes: [],
          notice: '',
        });
        try {
          const preview = await invoke<PreviewReply>('preview_legacy_cleanup', { sourceId });
          if (!alive) return;
          applyPreview(preview);
          emit({ error: STALE_ERROR });
        } catch {
          // Keep STALE_ERROR; candidates already cleared.
        }
        return;
      }
      // Condition 2: uncertain only after submit-then-exception; then disable clicks.
      emit({ uncertain: true, error: DO_NOT_RETRY_ERROR });
    } finally {
      emit({ busy: false });
    }
  }

  return {
    refresh,
    setSelected,
    apply,
    dispose() {
      alive = false;
    },
  };
}
