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
        Ok(json!({
            "worker": worker_card(&record),
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
        Ok(json!({ "worker": worker_card(&record) }))
    })
    .await?;
    Ok(value(out))
}

/// Card JSON for one worker (no cwd / no integration blob).
pub(crate) fn worker_card(record: &workers::WorkerRecord) -> Value {
    let view = workers::subagent::view(record);
    json!({
        "worker_id": view.get("worker_id").cloned().unwrap_or(Value::Null),
        "label": view.get("label").cloned().unwrap_or(Value::Null),
        "state": view.get("state").cloned().unwrap_or(Value::Null),
        "base_head": view.get("base_head").cloned().unwrap_or(Value::Null),
        "created_at": view.get("created_at").cloned().unwrap_or(Value::Null),
        "last_activity_at": view.get("last_activity_at").cloned().unwrap_or(Value::Null),
        "changed_files": Value::Null,
    })
}

fn list_workers_payload(ctx: &ToolContext) -> Result<Value, WorkerError> {
    let records = workers::status(ctx, None)?;
    Ok(json!({
        "workers": records.iter().map(worker_card).collect::<Vec<_>>(),
        "windows": cfg!(windows),
    }))
}

#[cfg(test)]
mod list_workers_tests {
    use super::worker_card;
    use crate::tools::worktree_tools::workers::{WorkerOwner, WorkerRecord, WorkerState};
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

    #[test]
    fn worker_card_strips_cwd_and_keeps_state_label() {
        let card = worker_card(&sample(WorkerState::Ready));
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
            assert_eq!(worker_card(&sample(state))["state"], json!(label));
        }
    }
}
