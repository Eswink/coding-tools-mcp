//! Native desktop controls only. Not part of the MCP/Actions tool registry.
use std::path::Path;

use tauri::State;
use zeroize::Zeroizing;

use crate::app_state::AppState;
use crate::cloud_connection::{CheckedImport, ConnectionStore, ConnectionSummary};
use crate::error::{AppError, AppResult};

fn unavailable() -> AppError {
    AppError::Message("云连接配置不可用；现有配置及恢复账本已保留。".into())
}

fn local_store(state: &AppState, id: &str) -> AppResult<ConnectionStore> {
    let profile = state.with_workspaces(|store| store.get(id).cloned().ok_or_else(unavailable))?;
    ConnectionStore::for_workspace(&profile.id, Path::new(&profile.path)).map_err(|_| unavailable())
}

#[tauri::command]
pub async fn import_cloud_connection(
    state: State<'_, AppState>,
    id: String,
    config_json: String,
    private_key_json: String,
) -> AppResult<ConnectionSummary> {
    // Native IPC is the existing local control trust boundary. Do not expose
    // these inputs through cloud tools, traces, clipboard helpers or errors.
    let private = Zeroizing::new(private_key_json);
    super::runtime::ensure_service_start_allowed()?;
    let input = CheckedImport::parse(&config_json, &private)
        .map_err(|error| AppError::Message(error.to_string()))?;
    let _gate = super::runtime::RESTART_GATE.lock().await;
    super::runtime::ensure_service_start_allowed()?;
    let store = local_store(&state, &id)?;
    tauri::async_runtime::spawn_blocking(move || store.initialize(input))
        .await
        .map_err(|_| unavailable())?
        .map_err(|error| AppError::Message(error.to_string()))
}

#[tauri::command]
pub async fn get_cloud_connection_configuration(
    state: State<'_, AppState>,
    id: String,
) -> AppResult<Option<ConnectionSummary>> {
    let _gate = super::runtime::RESTART_GATE.lock().await;
    let store = local_store(&state, &id)?;
    tauri::async_runtime::spawn_blocking(move || store.summary())
        .await
        .map_err(|_| unavailable())?
        .map_err(|error| AppError::Message(error.to_string()))
}
