use tauri::{AppHandle, Manager, State};

use crate::app_state::{AppState, StartupStatus};
use crate::error::AppResult;
use crate::platform::open_url as platform_open_url;
use crate::update::{check_app_update as check_update, UpdateCheckResult};

#[tauri::command]
pub fn open_url(url: String) -> AppResult<()> {
    platform_open_url(&url)
}

#[tauri::command]
pub async fn check_app_update(state: State<'_, AppState>) -> AppResult<UpdateCheckResult> {
    let settings = state.with_settings(|store| Ok(store.settings()))?;
    check_update(&settings).await
}

#[tauri::command]
pub fn get_startup_status(state: State<'_, AppState>) -> StartupStatus {
    state.startup_status()
}

#[tauri::command]
pub fn retry_startup(app: AppHandle) -> AppResult<StartupStatus> {
    let state = app.state::<AppState>();
    let became_ready = state.retry_data()?;
    let status = state.startup_status();
    if became_ready {
        crate::start_ready_services(&app);
        crate::bootstrap::record("recovery-ready");
    }
    Ok(status)
}
