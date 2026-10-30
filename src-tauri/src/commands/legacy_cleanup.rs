//! A1 C2-ad (N2, SPEC-A1 v5 §1.7, v5.1 NB-e/NB-i): local-only cleanup of
//! legacy `chat-v1` worktrees. The confirmer is the native owner
//! (`native_owner::confirm`, scope `legacy_cleanup`, bound to the candidate
//! list digest). No MCP tool reaches this; remote callers cannot trigger it.
use super::managed_workspace::{source_lease, NativeSourceLease};
use super::native_owner::{confirm, unavailable, OwnerApproval};
use crate::{
    app_state::AppState,
    error::{AppError, AppResult},
    harness::{
        worktree::{legacy_digest, LegacyCandidate, LegacyJournal, LegacyOutcome, WorktreeManager},
        Harness,
    },
};
use serde_json::{json, Value};
use std::path::Path;
use tauri::{AppHandle, Manager, State};

pub(crate) const SCOPE: &str = "legacy_cleanup";

/// The main-root manager (`<store_root>/worktrees-v1/<ws>`) of `source`.
fn main_manager(
    state: &AppState,
    source: &str,
    proof: &NativeSourceLease,
) -> AppResult<WorktreeManager> {
    let source_root = state.with_workspaces(|store| {
        store
            .get(source)
            .map(|p| Path::new(&p.path).canonicalize().map_err(|_| unavailable()))
            .ok_or_else(unavailable)?
    })?;
    proof.validate(&source_root)?;
    let harness = Harness::new(
        source_root.clone(),
        Harness::default_root().map_err(|_| unavailable())?,
    )
    .map_err(|_| unavailable())?;
    let base = harness
        .store_root()
        .canonicalize()
        .map_err(|_| unavailable())?;
    WorktreeManager::new(&source_root, &base, harness.workspace_id()).map_err(|_| unavailable())
}

fn code_error(code: &'static str) -> AppError {
    AppError::Message(format!(
        "旧版 worktree 清理未执行：{code}；没有删除任何内容。"
    ))
}

pub(crate) fn preview_for(manager: &WorktreeManager) -> Result<Value, &'static str> {
    let mut journal = LegacyJournal::open(manager).map_err(|e| e.code())?;
    let candidates = manager
        .legacy_candidates(&mut journal)
        .map_err(|e| e.code())?;
    Ok(json!({
        "candidates": candidates,
        "digest": legacy_digest(&candidates),
        "native_dialog_required": true,
    }))
}

/// Applies an owner approval. Refused unless `approval` is a native-owner
/// approval for [`SCOPE`] and exactly this list `digest` (NB-i).
pub(crate) fn apply_approved(
    manager: &WorktreeManager,
    approval: &OwnerApproval,
    ids: &[String],
    digest: &str,
) -> Result<Vec<LegacyOutcome>, &'static str> {
    if !approval.validates(SCOPE, digest) {
        return Err("OWNER_CONFIRMATION_REQUIRED");
    }
    let mut journal = LegacyJournal::open(manager).map_err(|e| e.code())?;
    manager
        .cleanup_legacy(&mut journal, ids, digest)
        .map_err(|e| e.code())
}

fn summary(root: &Path, candidates: &[LegacyCandidate], ids: &[String], digest: &str) -> Value {
    let selected: Vec<_> = candidates
        .iter()
        .filter(|c| ids.contains(&c.id))
        .map(|c| json!({"id":c.id,"head":c.head_short,"clean":c.clean,"path":c.path}))
        .collect();
    json!({"operation":"legacy_worktree_cleanup","canonical_root":root,
        "selected":selected,"digest":digest,
        "rule":"clean + HEAD reachable from a ref only; dirty/unreachable skipped; never --force"})
}

#[tauri::command]
pub async fn preview_legacy_cleanup(
    state: State<'_, AppState>,
    source_id: String,
) -> AppResult<Value> {
    let proof = source_lease(&state, &source_id)?;
    let manager = main_manager(&state, &source_id, &proof)?;
    tauri::async_runtime::spawn_blocking(move || preview_for(&manager))
        .await
        .map_err(|_| unavailable())?
        .map_err(code_error)
}

#[tauri::command]
pub async fn apply_legacy_cleanup(
    app: AppHandle,
    source_id: String,
    ids: Vec<String>,
    digest: String,
) -> AppResult<Option<Value>> {
    let state = app.state::<AppState>();
    let (root, candidates) = {
        let proof = source_lease(&state, &source_id)?;
        let manager = main_manager(&state, &source_id, &proof)?;
        let root = proof.root().to_path_buf();
        tauri::async_runtime::spawn_blocking(move || {
            let mut journal = LegacyJournal::open(&manager).map_err(|e| e.code())?;
            manager
                .legacy_candidates(&mut journal)
                .map(|c| (root, c))
                .map_err(|e| e.code())
        })
        .await
        .map_err(|_| unavailable())?
        .map_err(code_error)?
    };
    if legacy_digest(&candidates) != digest {
        return Err(code_error("STALE_CONFIRMATION"));
    }
    let Some(approval) = confirm(
        &app,
        SCOPE,
        "清理旧版 worktree（仅干净且可达的）",
        summary(&root, &candidates, &ids, &digest),
        &digest,
    )
    .await?
    else {
        return Ok(None);
    };
    // Re-take the source quiescence proof after the dialog; the digest is
    // recomputed under the lifecycle lock inside `cleanup_legacy`.
    let proof = source_lease(&state, &source_id)?;
    let manager = main_manager(&state, &source_id, &proof)?;
    let outcomes = tauri::async_runtime::spawn_blocking(move || {
        let result = apply_approved(&manager, &approval, &ids, &digest);
        drop(proof);
        result
    })
    .await
    .map_err(|_| unavailable())?
    .map_err(code_error)?;
    Ok(Some(json!({ "outcomes": outcomes })))
}

#[cfg(all(test, unix))]
#[path = "legacy_cleanup_tests.rs"]
mod tests;
