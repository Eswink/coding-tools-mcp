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
        worktree_tools::workers::{error_value, integration, WorkerError},
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
