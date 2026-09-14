use std::collections::BTreeMap;

use serde::Serialize;
use tauri::{AppHandle, Manager, State};

use crate::app_state::{AppState, StartupStatus};
use crate::error::AppResult;
use crate::platform::{open_url as platform_open_url, PlatformContext};
use crate::update::{check_app_update as check_update, UpdateCheckResult};

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct EnvironmentDiagnostics {
    pub platform: PlatformContext,
    pub safe_mode: bool,
    pub diagnose_startup: bool,
    pub display_backend: String,
    pub session_bus_configured: bool,
    pub credential_store_state: String,
    pub tray_available: bool,
    pub notification_plugin_enabled: bool,
    pub executables: BTreeMap<String, bool>,
}

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
pub fn get_environment_diagnostics(app: AppHandle) -> EnvironmentDiagnostics {
    let state = app.state::<AppState>();
    let ready = state.startup_status().ready;
    let platform = crate::platform::context().clone();
    let mut executables = BTreeMap::new();
    for name in ["sh", "bash", "git", "python3", "xdg-open", "frpc", "cloudflared"] {
        executables.insert(name.to_string(), crate::platform::platform().resolve_executable(name).is_some());
    }

    #[cfg(target_os = "linux")]
    let display_backend = if std::env::var_os("WAYLAND_DISPLAY").is_some() {
        "wayland"
    } else if std::env::var_os("DISPLAY").is_some() {
        "x11"
    } else {
        "headless"
    };
    #[cfg(target_os = "windows")]
    let display_backend = "windows";
    #[cfg(target_os = "macos")]
    let display_backend = "macos";
    #[cfg(not(any(target_os = "linux", target_os = "windows", target_os = "macos")))]
    let display_backend = "unknown";

    EnvironmentDiagnostics {
        platform,
        safe_mode: crate::bootstrap::safe_mode(),
        diagnose_startup: crate::bootstrap::diagnose_startup(),
        display_backend: display_backend.into(),
        session_bus_configured: std::env::var_os("DBUS_SESSION_BUS_ADDRESS").is_some(),
        credential_store_state: if ready { "ready" } else { "locked_or_unavailable" }.into(),
        tray_available: app.tray_by_id("main-tray").is_some(),
        notification_plugin_enabled: !crate::bootstrap::safe_mode(),
        executables,
    }
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

#[cfg(test)]
mod tests {
    #[test]
    fn diagnostics_binary_names_are_non_secret_capability_probes() {
        for name in ["sh", "bash", "git", "python3", "xdg-open", "frpc", "cloudflared"] {
            assert!(!name.contains('/'));
            assert!(!name.contains('\\'));
        }
    }
}
