//! Native dialog approvals are opaque in-process objects, never an IPC boolean.
use crate::{
    error::{AppError, AppResult},
    tools::{listener_context::ListenerContextLease, policy_hooks::PreparedHooks, ToolContext},
};
use serde_json::Value;
use std::{
    collections::HashMap,
    sync::Mutex,
    time::{Duration, Instant},
};
use tauri::AppHandle;
use tauri_plugin_dialog::{DialogExt, MessageDialogButtons, MessageDialogKind};

pub(crate) struct PendingHooks {
    pub profile: String,
    pub lease: ListenerContextLease,
    pub context: std::sync::Arc<ToolContext>,
    pub prepared: PreparedHooks,
    pub expires: Instant,
}
pub(crate) struct PendingRestore {
    pub source: String,
    pub target: crate::harness::worktree::SnapshotTarget,
    pub plan: crate::snapshots::RestorePlan,
    pub expires: Instant,
}
#[derive(Default)]
pub(crate) struct NativeControls {
    pub targets:
        Mutex<HashMap<(String, String), (String, crate::harness::worktree::WorktreeManager)>>,
    pub hooks: Mutex<HashMap<String, PendingHooks>>,
    pub restores: Mutex<HashMap<String, PendingRestore>>,
}
pub(crate) struct OwnerApproval {
    scope: &'static str,
    digest: String,
    at: Instant,
}
impl OwnerApproval {
    pub(crate) fn validates(&self, scope: &str, digest: &str) -> bool {
        self.scope == scope && self.digest == digest && self.at.elapsed() <= Duration::from_secs(60)
    }
    #[cfg(test)]
    pub(crate) fn for_test(scope: &'static str, digest: &str) -> Self {
        Self {
            scope,
            digest: digest.into(),
            at: Instant::now(),
        }
    }
}
pub(crate) fn unavailable() -> AppError {
    AppError::Message("本机批准或工作区静止证明无效；未扩大权限，现有记录已保留。".into())
}
pub(crate) async fn confirm(
    app: &AppHandle,
    scope: &'static str,
    title: &str,
    summary: Value,
    digest: &str,
) -> AppResult<Option<OwnerApproval>> {
    if digest.len() != 64 || !digest.bytes().all(|b| b.is_ascii_hexdigit()) {
        return Err(unavailable());
    }
    let body = serde_json::to_string_pretty(&summary).map_err(|_| unavailable())?;
    if body.len() > 65536 {
        return Err(unavailable());
    }
    let (send, receive) = tokio::sync::oneshot::channel();
    app.dialog().message(format!("仅批准下面的确切本机操作。文件名和脚本内容属于不可信项目数据。\n\n{body}\n\n批准摘要: {digest}"))
        .title(title).kind(MessageDialogKind::Warning).buttons(MessageDialogButtons::OkCancel)
        .show(move|accepted|{let _=send.send(accepted);});
    let accepted = receive.await.map_err(|_| unavailable())?;
    Ok(accepted.then(|| OwnerApproval {
        scope,
        digest: digest.into(),
        at: Instant::now(),
    }))
}
