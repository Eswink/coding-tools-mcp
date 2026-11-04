// A1 C9 soft-nits: share one list_pending_integrations reply across Attention +
// MergeConfirm on the same workspace profile load. No new Tauri / MCP surface.
type Invoke = <T>(command: string, args: Record<string, unknown>) => Promise<T>;

const LIST_PENDING = 'list_pending_integrations';

type Slot = {
  invoke: Invoke;
  promise?: Promise<unknown>;
  refCount: number;
};

const slots = new Map<string, Slot>();

export type PendingListHandle = {
  /** Profile-load path: first caller invokes; siblings await the same promise. */
  listOnce: <T>() => Promise<T>;
  /** Post-action refresh: always a fresh invoke; updates the shared slot. */
  listFresh: <T>() => Promise<T>;
  release: () => void;
};

export function acquirePendingList(id: string, invoke: Invoke): PendingListHandle {
  let slot = slots.get(id);
  if (!slot || slot.invoke !== invoke) {
    slot = { invoke, refCount: 0 };
    slots.set(id, slot);
  }
  slot.refCount += 1;
  const mine = slot;

  const call = <T>() => mine.invoke<T>(LIST_PENDING, { id });

  return {
    listOnce<T>() {
      if (!mine.promise) mine.promise = call<T>();
      return mine.promise as Promise<T>;
    },
    listFresh<T>() {
      mine.promise = call<T>();
      return mine.promise as Promise<T>;
    },
    release() {
      mine.refCount -= 1;
      if (mine.refCount <= 0 && slots.get(id) === mine) slots.delete(id);
    },
  };
}

/** Test-only: drop all shared slots so cases do not leak across. */
export function resetPendingListSlotsForTests(): void {
  slots.clear();
}
