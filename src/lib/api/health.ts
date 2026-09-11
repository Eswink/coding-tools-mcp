import { invoke } from "@tauri-apps/api/core";

export interface HealthItem {
  label: string;
  ok: boolean;
  detail: string;
  hint: string;
  skipped?: boolean;
}

export async function runHealthChecks(workspaceId: string): Promise<HealthItem[]> {
  return invoke<HealthItem[]>("run_health_checks", { id: workspaceId });
}
