/** Presentation only. The authoritative grant always remains in trusted Rust IPC. */
export type ChatGrant = { id: string; fingerprint: string; status: string; scopes: string[]; created_at: number; expires_at: number; idle_expires_at: number };
export type PendingChat = { workspaceId: string; workspaceName: string; exclusive: boolean; grant: ChatGrant };
export type ChatInbox = { revision: number; now: number; pending: PendingChat[] };
export const chatScopeLabels: Record<string, string> = {
  "workspace.read": "工作区状态", "files.read": "读取文件", "files.write": "修改文件",
  "exec.run": "执行命令（可访问共享文件）", "task.read": "查看本聊天任务", "task.manage": "管理本聊天任务",
  "history.read": "读取本聊天归档", "history.write": "保存本聊天归档", "harness.write": "管理本聊天开发计划",
};
export function pendingChats(snapshot: ChatInbox): PendingChat[] {
  return snapshot.pending.filter(p => p.grant.status === "pending" && p.grant.expires_at > snapshot.now);
}
export function remainingSeconds(grant: ChatGrant, now: number): number {
  return Math.max(0, Math.ceil(Math.min(grant.expires_at, grant.idle_expires_at) - now));
}
export function canApprove(grant: ChatGrant, selected: string[], verified: boolean, now: number): boolean {
  return verified && grant.status === "pending" && remainingSeconds(grant, now) > 0 && selected.length > 0
    && selected.every(scope => grant.scopes.includes(scope));
}
export class ApprovalPresentation {
  private shown = new Set<string>();
  choose(rows: PendingChat[], focused: boolean, force = false): PendingChat | null {
    const live = new Set(rows.map(r => r.grant.id));
    this.shown = new Set([...this.shown].filter(id => live.has(id)));
    if (!focused && !force) return null;
    const row = force ? rows[0] : rows.find(r => !this.shown.has(r.grant.id));
    if (!row) return null;
    this.shown.add(row.grant.id); return row;
  }
}
