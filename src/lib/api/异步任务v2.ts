import { invoke } from "@tauri-apps/api/core";
import type { TaskLogPage } from "$lib/任务日志v2";

export type TaskChannel = "mcp" | "actions";
export interface TaskSummary {
  job_id: string; request_id: string; status: string; terminal: boolean;
  created_at: number; completed_at: number | null; elapsed_ms: number;
  execution_timeout_ms: number; cancel_requested: boolean;
  restart_recoverable: boolean; persistence_failed: boolean;
  result?: { exit_code?: number; process_may_be_running?: boolean; output_complete?: boolean; termination_confirmed_by_user?: boolean; termination_reason?: string; message?: string; error?: { code?: string; message?: string } };
}
export interface TaskDetails extends TaskSummary { stdout: TaskLogPage; stderr: TaskLogPage }

async function control<T>(id: string, channel: TaskChannel, action: string, args: Record<string, unknown>): Promise<T> {
  const value = await invoke<T & { ok: boolean; error?: { message?: string } }>("control_exec_tasks", { id, channel, action, args });
  if (!value.ok) throw new Error(value.error?.message ?? "任务管理失败；请查询现有任务，不要重新提交命令。");
  return value;
}
export function listTasks(id: string, channel: TaskChannel): Promise<{ jobs: TaskSummary[] }> {
  return control(id, channel, "list", {});
}
export function getTask(id: string, channel: TaskChannel, jobId: string, stdoutCursor: number, stderrCursor: number): Promise<TaskDetails> {
  return control(id, channel, "get", { job_id: jobId, stdout_cursor: stdoutCursor, stderr_cursor: stderrCursor, limit: 16384 });
}
export function cancelTask(id: string, channel: TaskChannel, jobId: string, confirmTerminated = false): Promise<TaskSummary> {
  return control(id, channel, "cancel", { job_id: jobId, confirm_terminated: confirmTerminated });
}
