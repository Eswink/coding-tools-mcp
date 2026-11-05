//! A1 C5-7 (SPEC-A1 v5.2 §5 steps 4-6, §5.3, §5.4): the native side of
//! `subagent_integrate` / `subagent_rollback`. Only these commands confirm,
//! apply or reject; remote callers only ever create `*_pending` requests. The
//! approval is a native-owner dialog bound to the integration (or rollback)
//! digest, never an IPC boolean. Results keep the stable worker error codes.
use super::native_owner::{confirm, unavailable};
use crate::{
    app_state::AppState,
    error::AppResult,
    tools::{
        root_work::blocking_context,
        worktree_tools::workers::{self, error_value, integration, WorkerError},
        ToolContext,
    },
};
use serde_json::{json, Value};
use std::sync::Arc;
use tauri::{AppHandle, Manager, State};

/// The live listener context of workspace profile `id`.
fn context(state: &AppState, id: &str) -> AppResult<Arc<ToolContext>> {
    let lease =
        state.with_runtime(|runtime| runtime.mcp_context_lease(id).ok_or_else(unavailable))?;
    lease.with_live(Arc::clone).map_err(|_| unavailable())
}
/// Runs one native operation inside a root scope on a blocking thread.
async fn native<T, F>(ctx: Arc<ToolContext>, run: F) -> AppResult<Result<T, WorkerError>>
where
    T: Send + 'static,
    F: FnOnce(&ToolContext) -> Result<T, WorkerError> + Send + 'static,
{
    blocking_context(ctx, move |scoped| run(&scoped))
        .await
        .map_err(|_| unavailable())
}
fn value(out: Result<Value, WorkerError>) -> Value {
    out.unwrap_or_else(|e| error_value(&e))
}

/// Startup scan (§5.1.1 crash column) plus the pending integrate/rollback
/// cards of every owner; recovery runs first so a crashed journal never
/// leaves a card that cannot be applied.
#[tauri::command]
pub async fn list_pending_integrations(state: State<'_, AppState>, id: String) -> AppResult<Value> {
    let ctx = context(&state, &id)?;
    let out = native(ctx, |c| {
        let recovery = integration::recover(c)?;
        let pending = integration::pending(c)?;
        Ok(json!({"recovery": recovery, "pending": pending}))
    })
    .await?;
    Ok(value(out))
}

#[tauri::command]
pub async fn recover_subagent_integrations(
    state: State<'_, AppState>,
    id: String,
) -> AppResult<Value> {
    let ctx = context(&state, &id)?;
    Ok(value(native(ctx, integration::recover).await?))
}

/// The owner sees the exact card in a native dialog; only an approval for
/// this digest is applied, with every check repeated under the exclusive guard.
#[tauri::command]
pub async fn confirm_subagent_integration(
    app: AppHandle,
    id: String,
    integration_id: String,
) -> AppResult<Option<Value>> {
    let state = app.state::<AppState>();
    let ctx = context(&state, &id)?;
    let wanted = integration_id.clone();
    let card = match native(ctx.clone(), move |c| integration::prepare(c, &wanted)).await? {
        Ok(card) => card,
        Err(e) => return Ok(Some(error_value(&e))),
    };
    let summary = json!({"operation": integration::INTEGRATE_SCOPE, "card": card.summary});
    let Some(approval) = confirm(
        &app,
        integration::INTEGRATE_SCOPE,
        &card.title,
        summary,
        &card.digest,
    )
    .await?
    else {
        return Ok(None);
    };
    let out = native(ctx, move |c| integration::apply(c, &card, &approval)).await?;
    Ok(Some(value(out)))
}

#[tauri::command]
pub async fn reject_subagent_integration(
    state: State<'_, AppState>,
    id: String,
    integration_id: String,
) -> AppResult<Value> {
    let ctx = context(&state, &id)?;
    let out = native(ctx, move |c| integration::reject(c, &integration_id)).await?;
    Ok(value(out))
}

#[tauri::command]
pub async fn confirm_subagent_rollback(
    app: AppHandle,
    id: String,
    integration_id: String,
) -> AppResult<Option<Value>> {
    let state = app.state::<AppState>();
    let ctx = context(&state, &id)?;
    let wanted = integration_id.clone();
    let card = match native(ctx.clone(), move |c| {
        integration::prepare_rollback(c, &wanted)
    })
    .await?
    {
        Ok(card) => card,
        Err(e) => return Ok(Some(error_value(&e))),
    };
    let summary = json!({"operation": integration::ROLLBACK_SCOPE, "card": card.summary});
    let Some(approval) = confirm(
        &app,
        integration::ROLLBACK_SCOPE,
        &card.title,
        summary,
        &card.digest,
    )
    .await?
    else {
        return Ok(None);
    };
    let out = native(ctx, move |c| {
        integration::apply_rollback(c, &card, &approval)
    })
    .await?;
    Ok(Some(value(out)))
}

#[tauri::command]
pub async fn reject_subagent_rollback(
    state: State<'_, AppState>,
    id: String,
    integration_id: String,
) -> AppResult<Value> {
    let ctx = context(&state, &id)?;
    let out = native(ctx, move |c| {
        integration::reject_rollback(c, &integration_id)
    })
    .await?;
    Ok(value(out))
}

/// C9 (SPEC-A1 §0.9 nit 1): local only, not in the MCP tool table. Refuses
/// unless the journal is `needs_attention`; the native dialog lists the
/// journal's integration_id and entry paths, and only an approval for that
/// digest sets the journal back to `none` and drops the pre-images. No
/// workspace file is written. `None` when the owner cancelled.
#[tauri::command]
pub async fn clear_integration_attention(app: AppHandle, id: String) -> AppResult<Option<Value>> {
    let state = app.state::<AppState>();
    let ctx = context(&state, &id)?;
    let card = match native(ctx.clone(), integration::prepare_clear_attention).await? {
        Ok(card) => card,
        Err(e) => return Ok(Some(error_value(&e))),
    };
    let summary = json!({"operation": integration::ATTENTION_SCOPE, "card": card.summary});
    let Some(approval) = confirm(
        &app,
        integration::ATTENTION_SCOPE,
        &card.title,
        summary,
        &card.digest,
    )
    .await?
    else {
        return Ok(None);
    };
    let out = native(ctx, move |c| {
        integration::apply_clear_attention(c, &card, &approval)
    })
    .await?;
    Ok(Some(value(out)))
}

/// A1 C9-ui-remainder §6.1 (NARROW-B): local-only worker list for the desktop
/// cards. Same listener/lease gate as `list_pending_integrations`. Strips `cwd`
/// and `integration` so the FE cannot render paths or grow a merge UI from this
/// payload. `windows` tells the card whether to show the fixed unsandboxed label.
#[tauri::command]
pub async fn list_subagent_workers(state: State<'_, AppState>, id: String) -> AppResult<Value> {
    let ctx = context(&state, &id)?;
    let out = native(ctx, |c| Ok(list_workers_payload(c)?)).await?;
    Ok(value(out))
}

/// Optional card action: cancel a ready worker (thin wrap of `workers::cancel`).
#[tauri::command]
pub async fn cancel_subagent_worker(
    state: State<'_, AppState>,
    id: String,
    worker_id: String,
) -> AppResult<Value> {
    let ctx = context(&state, &id)?;
    let out = native(ctx, move |c| {
        let (record, killed) = workers::cancel(c, &worker_id)?;
        let snap = workers::changed_snap_for(c, &record.worker_id);
        Ok(json!({
            "worker": worker_card(&record, snap),
            "killed_tasks": killed,
        }))
    })
    .await?;
    Ok(value(out))
}

/// Optional card action: discard a worker worktree (thin wrap of `workers::discard`).
/// DIRTY passes through so the FE can show a second confirm / refusal; this
/// command never force-removes a dirty tree.
#[tauri::command]
pub async fn discard_subagent_worker(
    state: State<'_, AppState>,
    id: String,
    worker_id: String,
) -> AppResult<Value> {
    let ctx = context(&state, &id)?;
    let out = native(ctx, move |c| {
        let record = workers::discard(c, &worker_id)?;
        // A1 C11 M5: discard return is always null (cache cleared inside discard).
        Ok(json!({ "worker": worker_card(&record, None) }))
    })
    .await?;
    Ok(value(out))
}

/// Card JSON for one worker (no cwd / no integration blob).
/// A1 C11: `changed_files` is hitchhiked cache → integration.files → null.
pub(crate) fn worker_card(
    record: &workers::WorkerRecord,
    snap: Option<workers::ChangedSnap>,
) -> Value {
    let view = workers::subagent::view(record);
    let changed = workers::resolve_changed_files(record, snap);
    json!({
        "worker_id": view.get("worker_id").cloned().unwrap_or(Value::Null),
        "label": view.get("label").cloned().unwrap_or(Value::Null),
        "state": view.get("state").cloned().unwrap_or(Value::Null),
        "base_head": view.get("base_head").cloned().unwrap_or(Value::Null),
        "created_at": view.get("created_at").cloned().unwrap_or(Value::Null),
        "last_activity_at": view.get("last_activity_at").cloned().unwrap_or(Value::Null),
        "changed_files": changed.map_or(Value::Null, |n| json!(n)),
    })
}

fn list_workers_payload(ctx: &ToolContext) -> Result<Value, WorkerError> {
    // A1 C11 M1: status_with_changed only clones store records + memory snaps;
    // it never computes a worktree diff and never spawns a git subprocess.
    let rows = workers::status_with_changed(ctx)?;
    Ok(json!({
        "workers": rows
            .iter()
            .map(|(record, snap)| worker_card(record, *snap))
            .collect::<Vec<_>>(),
        "windows": cfg!(windows),
    }))
}

#[cfg(test)]
mod list_workers_tests {
    use super::worker_card;
    use crate::tools::worktree_tools::workers::{
        integration::{IntegrationRecord, IntegrationState},
        resolve_changed_files, ChangedSnap, WorkerOwner, WorkerRecord, WorkerState,
    };
    use serde_json::json;

    fn sample(state: WorkerState) -> WorkerRecord {
        WorkerRecord {
            worker_id: crate::tools::worktree_tools::workers::WorkerId::parse(
                "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            )
            .unwrap(),
            worktree_id: Some("wt-secret".into()),
            workspace_id: "ws".into(),
            owner: WorkerOwner::local(),
            spawn_request_id: "req".into(),
            spawn_fingerprint: "fp".into(),
            label: "demo".into(),
            base_head: Some("0123456789abcdef0123456789abcdef01234567".into()),
            state,
            cwd: "/secret/absolute/path".into(),
            created_at: 1_700_000_000,
            last_activity_at: 1_700_000_100,
            ops: vec![],
            ops_seq: 0,
            integrations: vec![],
            main_fingerprint: None,
        }
    }

    fn integration(state: IntegrationState, files: u64, expires_at: u64) -> IntegrationRecord {
        IntegrationRecord {
            integration_id: "i".repeat(32),
            request_id: "req-int".into(),
            diff_sha256: "d".repeat(64),
            state,
            prior_state: WorkerState::Ready,
            created_at: 1_700_000_000,
            expires_at,
            files,
            main_changed_since_spawn: false,
            journal_epoch: None,
            closed_reason: None,
            error_code: None,
            rollback_request_id: None,
            rollback_expires_at: None,
        }
    }

    #[test]
    fn worker_card_strips_cwd_and_keeps_state_label() {
        let card = worker_card(&sample(WorkerState::Ready), None);
        assert_eq!(card["label"], json!("demo"));
        assert_eq!(card["state"], json!("ready"));
        assert_eq!(
            card["base_head"],
            json!("0123456789abcdef0123456789abcdef01234567")
        );
        assert_eq!(card["changed_files"], json!(null));
        assert!(card.get("cwd").is_none(), "cwd must not reach the FE card");
        assert!(
            card.get("integration").is_none(),
            "integration belongs to §6.2, not the card list"
        );
        assert!(
            card.get("worktree_id").is_none(),
            "worktree id must not reach the FE card"
        );
    }

    #[test]
    fn worker_card_covers_tip_worker_states() {
        use WorkerState::*;
        for (state, label) in [
            (Creating, "creating"),
            (Ready, "ready"),
            (Cancelled, "cancelled"),
            (Failed, "failed"),
            (PendingCleanup, "pending_cleanup"),
            (Discarded, "discarded"),
            (IntegratePending, "integrate_pending"),
            (Integrated, "integrated"),
        ] {
            assert_eq!(worker_card(&sample(state), None)["state"], json!(label));
        }
    }

    #[test]
    fn cache_hit_returns_files_when_ops_seq_matches() {
        let record = sample(WorkerState::Ready);
        let snap = Some(ChangedSnap {
            files: 3,
            ops_seq: 0,
        });
        assert_eq!(resolve_changed_files(&record, snap), Some(3));
        assert_eq!(worker_card(&record, snap)["changed_files"], json!(3));
    }

    #[test]
    fn ops_seq_mismatch_invalidates_cache() {
        let mut record = sample(WorkerState::Ready);
        record.ops_seq = 2;
        let snap = Some(ChangedSnap {
            files: 9,
            ops_seq: 1,
        });
        assert_eq!(resolve_changed_files(&record, snap), None);
        assert_eq!(worker_card(&record, snap)["changed_files"], json!(null));
    }

    #[test]
    fn integration_files_fallback_for_pending_committed_rollback() {
        // Far-future expiry so effective() keeps Pending.
        let far = u64::MAX / 2;
        for (state, worker_state, files) in [
            (
                IntegrationState::Pending,
                WorkerState::IntegratePending,
                4u64,
            ),
            (IntegrationState::Committed, WorkerState::Integrated, 5),
            (
                IntegrationState::RollbackPending,
                WorkerState::Integrated,
                6,
            ),
        ] {
            let mut record = sample(worker_state);
            record.integrations = vec![integration(state, files, far)];
            assert_eq!(
                resolve_changed_files(&record, None),
                Some(files),
                "{state:?}"
            );
            assert_eq!(
                worker_card(&record, None)["changed_files"],
                json!(files),
                "{state:?}"
            );
        }
    }

    #[test]
    fn expired_rolled_back_rejected_are_null() {
        let far = u64::MAX / 2;
        // Expired Pending: expires_at in the past → effective() flips to Expired.
        let mut expired = sample(WorkerState::Ready);
        expired.integrations = vec![integration(IntegrationState::Pending, 7, 1)];
        assert_eq!(resolve_changed_files(&expired, None), None);

        for state in [
            IntegrationState::RolledBack,
            IntegrationState::Rejected,
            IntegrationState::Expired,
            IntegrationState::Failed,
        ] {
            let mut record = sample(WorkerState::Ready);
            record.integrations = vec![integration(state, 8, far)];
            assert_eq!(
                resolve_changed_files(&record, None),
                None,
                "{state:?} must not fallback"
            );
        }
    }

    #[test]
    fn gated_states_are_always_null_even_with_cache() {
        let snap = Some(ChangedSnap {
            files: 11,
            ops_seq: 0,
        });
        for state in [
            WorkerState::Creating,
            WorkerState::Failed,
            WorkerState::PendingCleanup,
            WorkerState::Discarded,
        ] {
            let record = sample(state);
            assert_eq!(resolve_changed_files(&record, snap), None, "{state:?}");
            assert_eq!(
                worker_card(&record, snap)["changed_files"],
                json!(null),
                "{state:?}"
            );
        }
    }

    #[test]
    fn cache_preferred_over_integration_fallback() {
        let far = u64::MAX / 2;
        let mut record = sample(WorkerState::IntegratePending);
        record.ops_seq = 4;
        record.integrations = vec![integration(IntegrationState::Pending, 99, far)];
        let snap = Some(ChangedSnap {
            files: 2,
            ops_seq: 4,
        });
        assert_eq!(resolve_changed_files(&record, snap), Some(2));
    }

    #[test]
    fn list_path_source_does_not_compute_diff_or_spawn_git() {
        let src = include_str!("subagent_integration.rs");
        // Only production code: the cfg(test) module's own assert strings
        // mention the forbidden tokens and would poison a whole-file scan.
        let prod = src.split("#[cfg(test)]").next().unwrap_or(src);
        assert!(
            !prod.contains("worker_diff_of"),
            "list/card path must not call worker_diff_of"
        );
        assert!(
            !prod.contains("worker_diff("),
            "list/card path must not call worker_diff"
        );
        assert!(
            !prod.contains(r#"Command::new("git")"#),
            "list/card path must not spawn git"
        );
        assert!(
            prod.contains("status_with_changed"),
            "list must read snaps via status_with_changed"
        );
    }
}
