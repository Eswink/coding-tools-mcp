use tauri::State;

use crate::app_state::AppState;
use crate::error::{AppError, AppResult};
use crate::health::{run_health_checks as execute_health_checks, HealthItem, HealthRuntime};
use crate::runtime::ServiceKind;
use crate::workspace::WorkspaceProfile;
use super::runtime::RESTART_GATE;

fn profile_by_id(state: &AppState, id: &str) -> AppResult<WorkspaceProfile> {
    state.with_workspaces(|store| {
        store.get(id).cloned().ok_or_else(|| AppError::Message("workspace not found".into()))
    })
}

fn snapshot(state: &AppState, id: &str) -> AppResult<(WorkspaceProfile, HealthRuntime)> {
    let profile = profile_by_id(state, id)?;
    let runtime = state.with_runtime(|runtime| Ok(HealthRuntime {
        mcp_running: runtime.is_running(id, ServiceKind::Mcp),
        actions_running: runtime.is_running(id, ServiceKind::Actions),
        mcp_origin: runtime.public_origin_handle(id, ServiceKind::Mcp).map(|h| h.snapshot()).unwrap_or_default(),
        actions_origin: runtime.public_origin_handle(id, ServiceKind::Actions).map(|h| h.snapshot()).unwrap_or_default(),
    }))?;
    Ok((profile, runtime))
}

#[tauri::command]
pub async fn run_health_checks(state: State<'_, AppState>, id: String) -> AppResult<Vec<HealthItem>> {
    let (profile, runtime) = {
        let _gate = RESTART_GATE.lock().await;
        snapshot(&state, &id)?
    };
    let before = serde_json::to_value(&profile)?;
    // No lifecycle/data/runtime lock crosses network I/O.
    let mut items = execute_health_checks(&profile, &runtime).await;
    let _gate = RESTART_GATE.lock().await;
    let stable = snapshot(&state, &id).ok().is_some_and(|(after, active)| {
        serde_json::to_value(after).ok().as_ref() == Some(&before) && active == runtime
    });
    if !stable {
        for item in &mut items {
            item.ok = false;
            item.skipped = false;
            item.detail = "configuration_changed_during_check".into();
            item.code = "configuration_changed_during_check".into();
            item.request.clear();
            item.hint = "检查期间配置、服务或隧道身份发生变化；请重新检查。".into();
        }
    }
    Ok(items)
}
