use tauri::State;

use crate::app_state::AppState;
use crate::error::{AppError, AppResult};

const ALLOWED_KEYS: &[&str] = &[
    "oauth_client_secret",
    "oauth_password",
    "oauth_token_secret",
    "bearer_token",
    "cloudflare_token",
    "actions_cloudflare_token",
    "actions_api_key",
    "actions_oauth_client_secret",
    "actions_oauth_password",
    "actions_oauth_token_secret",
    "frp_token",
    "actions_frp_token",
];

fn ensure_workspace_exists(state: &AppState, id: &str) -> AppResult<()> {
    state.with_workspaces(|store| {
        if store.get(id).is_some() {
            Ok(())
        } else {
            Err(AppError::Message(format!("workspace not found: {id}")))
        }
    })
}

fn validate_key(key: &str) -> AppResult<()> {
    if ALLOWED_KEYS.contains(&key) {
        Ok(())
    } else {
        Err(AppError::Message(format!("invalid secret key: {key}")))
    }
}

#[tauri::command]
pub fn get_workspace_secret(
    state: State<'_, AppState>,
    id: String,
    key: String,
) -> AppResult<Option<String>> {
    validate_key(&key)?;
    ensure_workspace_exists(&state, &id)?;
    state.with_data(|store| store.get_workspace_secret(&id, &key))
}

#[tauri::command]
pub async fn set_workspace_secret(
    state: State<'_, AppState>,
    id: String,
    key: String,
    value: String,
) -> AppResult<()> {
    validate_key(&key)?;
    ensure_workspace_exists(&state, &id)?;
    super::configuration::write_secret(&state, Some(&id), &key, Some(&value)).await.map(|_| ())
}

#[tauri::command]
pub async fn regenerate_workspace_secret(
    state: State<'_, AppState>, id: String, key: String,
) -> AppResult<String> {
    validate_key(&key)?;
    super::configuration::write_secret(&state, Some(&id), &key, None).await
}

const SHARED_KEYS: &[&str] = &[
    "oauth_client_id",
    "bearer_token",
    "oauth_client_secret",
    "oauth_password",
    "oauth_token_secret",
    "actions_api_key",
    "actions_oauth_client_secret",
    "actions_oauth_password",
    "actions_oauth_token_secret",
];

#[tauri::command]
pub fn get_shared_secret(state: State<'_, AppState>, key: String) -> AppResult<Option<String>> {
    if !SHARED_KEYS.contains(&key.as_str()) {
        return Err(AppError::Message(format!("invalid shared key: {key}")));
    }
    state.with_data(|store| Ok(store.get_shared_secret(&key)))
}

#[tauri::command]
pub async fn set_shared_secret(
    state: State<'_, AppState>, key: String, value: String,
) -> AppResult<()> {
    if !SHARED_KEYS.contains(&key.as_str()) {
        return Err(AppError::Message(format!("invalid shared key: {key}")));
    }
    if value.is_empty() { return Err(AppError::Message("密钥不能为空。".into())); }
    super::configuration::write_secret(&state, None, &key, Some(&value)).await.map(|_| ())
}

#[tauri::command]
pub async fn regenerate_shared_secret(
    state: State<'_, AppState>, key: String,
) -> AppResult<String> {
    if !SHARED_KEYS.contains(&key.as_str()) {
        return Err(AppError::Message(format!("invalid shared key: {key}")));
    }
    super::configuration::write_secret(&state, None, &key, None).await
}
