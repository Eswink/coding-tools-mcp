use std::collections::BTreeMap;

use serde::Serialize;
use tauri::{AppHandle, Manager, State};

use crate::app_state::{AppState, StartupStatus};
use crate::error::AppResult;
use crate::platform::{open_url as platform_open_url, PlatformContext};
use crate::update::{check_app_update as check_update, UpdateCheckResult};

const DIAGNOSTIC_KEYRING_SERVICE: &str = "coding-tools-mcp.startup-diagnostics.v1";
const DIAGNOSTIC_KEYRING_ACCOUNT: &str = "availability-probe";

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct EnvironmentDiagnostics {
    pub platform: PlatformContext,
    pub safe_mode: bool,
    pub diagnose_startup: bool,
    pub display_backend: String,
    pub session_bus_configured: bool,
    pub credential_store_state: String,
    pub configuration_state: String,
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

fn credential_store_state() -> String {
    match keyring::Entry::new(DIAGNOSTIC_KEYRING_SERVICE, DIAGNOSTIC_KEYRING_ACCOUNT)
        .and_then(|entry| entry.get_secret())
    {
        Ok(mut secret) => {
            secret.fill(0);
            "available".into()
        }
        Err(keyring::Error::NoEntry) => "available".into(),
        Err(_) => "locked_or_unavailable".into(),
    }
}

pub(crate) fn environment_diagnostics_snapshot(
    configuration_state: &'static str,
    tray_available: bool,
    notification_plugin_enabled: bool,
) -> EnvironmentDiagnostics {
    let platform = crate::platform::context().clone();
    let mut executables = BTreeMap::new();
    for name in ["sh", "bash", "git", "python3", "xdg-open", "frpc", "cloudflared"] {
        executables.insert(
            name.to_string(),
            crate::platform::platform().resolve_executable(name).is_some(),
        );
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
        credential_store_state: credential_store_state(),
        configuration_state: configuration_state.into(),
        tray_available,
        notification_plugin_enabled,
        executables,
    }
}

pub(crate) fn environment_diagnostics(app: &AppHandle) -> EnvironmentDiagnostics {
    let state = app.state::<AppState>();
    let status = state.startup_status();
    environment_diagnostics_snapshot(
        if status.ready { "ready" } else { "locked_or_unavailable" },
        app.tray_by_id("main-tray").is_some(),
        !crate::bootstrap::safe_mode(),
    )
}

#[tauri::command]
pub fn get_environment_diagnostics(app: AppHandle) -> EnvironmentDiagnostics {
    environment_diagnostics(&app)
}

#[tauri::command]
pub fn retry_startup(app: AppHandle) -> AppResult<StartupStatus> {
    let state = app.state::<AppState>();
    let became_ready = state.retry_data()?;
    let status = state.startup_status();
    if became_ready {
        if crate::bootstrap::safe_mode() {
            crate::bootstrap::record("recovery-ready-safe-mode");
        } else {
            crate::start_ready_services(&app);
            crate::bootstrap::record("recovery-ready");
        }
    }
    Ok(status)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn diagnostics_binary_names_are_non_secret_capability_probes() {
        for name in ["sh", "bash", "git", "python3", "xdg-open", "frpc", "cloudflared"] {
            assert!(!name.contains('/'));
            assert!(!name.contains('\\'));
        }
    }

    #[test]
    fn diagnostic_keyring_probe_uses_an_isolated_nonproduction_namespace() {
        assert_eq!(
            DIAGNOSTIC_KEYRING_SERVICE,
            "coding-tools-mcp.startup-diagnostics.v1"
        );
        assert_eq!(DIAGNOSTIC_KEYRING_ACCOUNT, "availability-probe");
    }
}
