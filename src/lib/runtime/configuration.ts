import { writable } from "svelte/store";

// Only invalidation metadata. Configuration and credential bytes stay in their owners.
export const configurationState = writable({ revision: 0, pending: 0 });
export async function trackConfigurationChange<T>(operation: () => Promise<T>): Promise<T> {
  configurationState.update((s) => ({ revision: s.revision + 1, pending: s.pending + 1 }));
  try { return await operation(); }
  finally {
    configurationState.update((s) => ({ revision: s.revision + 1, pending: s.pending - 1 }));
  }
}

/** Persistence may succeed before runtime application fails. Always read back truth. */
export async function applyAndRefresh(apply: () => Promise<void>, refresh: () => Promise<void>): Promise<void> {
  let failed = false;
  let primary: unknown;
  try { await apply(); } catch (error) { failed = true; primary = error; }
  try { await refresh(); } catch (error) { if (!failed) throw error; }
  if (failed) throw primary;
}

/** Bind the identity now, not after a dialog, credential write or network await. */
export function forCurrentWorkspace<A extends unknown[], T>(
  id: string,
  currentId: () => string | undefined,
  action: (...args: A) => Promise<T>,
): (...args: A) => Promise<T> {
  return async (...args: A) => {
    if (id !== currentId()) throw new Error("工作区已切换，本次操作未继续。请在目标工作区重试。");
    return action(...args);
  };
}

export function validServicePort(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 1024 && value <= 65535;
}

// The native picker already supplies a path. Removing separators corrupts / and C:\ roots.
export function selectedDirectory(value: string): string { return value; }
