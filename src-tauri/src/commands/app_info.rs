use std::collections::BTreeMap;
use std::fs;

use serde::Serialize;
use tauri::{AppHandle, Manager, State};

use crate::app_state::{AppState, StartupStatus};
use crate::error::{classify_keyring_error, AppResult};
#[cfg(target_os = "linux")]
use crate::error::StartupFailureReason;
use crate::platform::{open_url as platform_open_url, PlatformContext};
use crate::update::{check_app_update as check_update, UpdateCheckResult};

const DIAGNOSTIC_KEYRING_SERVICE: &str = "coding-tools-mcp.startup-diagnostics.v1";
const DIAGNOSTIC_KEYRING_ACCOUNT: &str = "availability-probe";
const MAX_DIAGNOSTIC_CONFIG_BYTES: u64 = 48 * 1024 * 1024;

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct EnvironmentDiagnostics {
    pub app_version: String,
    pub package_kind: String,
    pub platform: PlatformContext,
    pub safe_mode: bool,
    pub diagnose_startup: bool,
    pub display_backend: String,
    pub desktop_session: String,
    pub session_bus_configured: bool,
    pub session_bus_original_configured: bool,
    pub session_bus_route: String,
    pub session_bus_split_detected: bool,
    pub session_bus_reachable: bool,
    pub runtime_user_bus_reachable: bool,
    pub runtime_user_bus_secret_service_available: bool,
    pub secret_service_default_collection_state: String,
    pub credential_store_state: String,
    pub startup_failure_reason: Option<String>,
    pub configuration_state: String,
    pub configuration_exists: bool,
    pub configuration_encrypted: Option<bool>,
    pub configuration_owned_by_current_user: Option<bool>,
    pub configuration_owner_only_permissions: Option<bool>,
    pub configuration_directory_writable: Option<bool>,
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
    #[cfg(target_os = "linux")]
    if std::env::var_os("DBUS_SESSION_BUS_ADDRESS").is_none() {
        return crate::error::StartupFailureReason::SessionBusMissing
            .code()
            .into();
    }

    match keyring::Entry::new(DIAGNOSTIC_KEYRING_SERVICE, DIAGNOSTIC_KEYRING_ACCOUNT)
        .and_then(|entry| entry.get_secret())
    {
        Ok(mut secret) => {
            secret.fill(0);
            "available".into()
        }
        Err(keyring::Error::NoEntry) => "available".into(),
        Err(error) => classify_keyring_error(&error).code().into(),
    }
}

fn package_kind() -> String {
    #[cfg(target_os = "linux")]
    {
        if std::env::var_os("APPIMAGE").is_some() {
            return "appimage".into();
        }
        if std::env::current_exe().ok().is_some_and(|path| {
            path == std::path::PathBuf::from("/usr/bin/coding-tools-mcp-desktop")
        }) {
            return "deb".into();
        }
    }
    "unknown".into()
}

fn display_backend() -> &'static str {
    #[cfg(target_os = "linux")]
    {
        if std::env::var_os("WAYLAND_DISPLAY").is_some() {
            return "wayland";
        }
        if std::env::var_os("DISPLAY").is_some() {
            return "x11";
        }
        return "headless";
    }
    #[cfg(target_os = "windows")]
    {
        "windows"
    }
    #[cfg(target_os = "macos")]
    {
        "macos"
    }
    #[cfg(not(any(target_os = "linux", target_os = "windows", target_os = "macos")))]
    {
        "unknown"
    }
}

fn desktop_session(display: &str) -> String {
    #[cfg(target_os = "linux")]
    {
        return match std::env::var("XDG_SESSION_TYPE").ok().as_deref() {
            Some("wayland") => "wayland".into(),
            Some("x11") => "x11".into(),
            Some("tty") => "tty".into(),
            _ if display == "wayland" => "wayland".into(),
            _ if display == "x11" => "x11".into(),
            _ => "unknown".into(),
        };
    }
    #[cfg(not(target_os = "linux"))]
    {
        display.into()
    }
}

#[derive(Debug, Default)]
struct ConfigurationFacts {
    exists: bool,
    encrypted: Option<bool>,
    owned_by_current_user: Option<bool>,
    owner_only_permissions: Option<bool>,
    directory_writable: Option<bool>,
}

fn configuration_facts() -> ConfigurationFacts {
    let Ok(root) = crate::platform::platform().app_config_dir() else {
        return ConfigurationFacts::default();
    };
    let path = root.join("data").join("profiles.json");
    let exists = path.try_exists().unwrap_or(false);
    let metadata = fs::metadata(&path).ok();
    let encrypted = metadata.as_ref().and_then(|metadata| {
        if metadata.len() > MAX_DIAGNOSTIC_CONFIG_BYTES {
            return None;
        }
        let raw = fs::read_to_string(&path).ok()?;
        let value: serde_json::Value = serde_json::from_str(&raw).ok()?;
        Some(
            value.get("format").and_then(serde_json::Value::as_str)
                == Some("coding-tools-mcp.encrypted")
                || ["ciphertext", "nonce", "key_id"]
                    .iter()
                    .all(|key| value.get(*key).is_some()),
        )
    });

    let directory_writable = path
        .ancestors()
        .skip(1)
        .find_map(|candidate| fs::metadata(candidate).ok().filter(|meta| meta.is_dir()))
        .map(|metadata| !metadata.permissions().readonly());

    #[cfg(unix)]
    let (owned_by_current_user, owner_only_permissions) = metadata
        .as_ref()
        .map(|metadata| {
            use std::os::unix::fs::{MetadataExt, PermissionsExt};
            let mode = metadata.permissions().mode() & 0o777;
            (
                metadata.uid() == unsafe { libc::geteuid() },
                mode & 0o077 == 0,
            )
        })
        .map(|(owned, mode)| (Some(owned), Some(mode)))
        .unwrap_or((None, None));
    #[cfg(not(unix))]
    let (owned_by_current_user, owner_only_permissions) = (None, None);

    ConfigurationFacts {
        exists,
        encrypted,
        owned_by_current_user,
        owner_only_permissions,
        directory_writable,
    }
}

pub(crate) fn environment_diagnostics_snapshot(
    configuration_state: &'static str,
    tray_available: bool,
    notification_plugin_enabled: bool,
) -> EnvironmentDiagnostics {
    let platform = crate::platform::context().clone();
    let mut executables = BTreeMap::new();
    for name in [
        "sh",
        "bash",
        "git",
        "python3",
        "xdg-open",
        "frpc",
        "cloudflared",
    ] {
        executables.insert(
            name.to_string(),
            crate::platform::platform()
                .resolve_executable(name)
                .is_some(),
        );
    }
    let display = display_backend();
    let configuration = configuration_facts();
    #[cfg(target_os = "linux")]
    let session_bus = crate::linux_session_bus::state();
    #[cfg(target_os = "linux")]
    let default_collection = crate::linux_secret_service::default_collection_state();

    EnvironmentDiagnostics {
        app_version: env!("CARGO_PKG_VERSION").into(),
        package_kind: package_kind(),
        platform,
        safe_mode: crate::bootstrap::safe_mode(),
        diagnose_startup: crate::bootstrap::diagnose_startup(),
        display_backend: display.into(),
        desktop_session: desktop_session(display),
        session_bus_configured: std::env::var_os("DBUS_SESSION_BUS_ADDRESS").is_some(),
        #[cfg(target_os = "linux")]
        session_bus_original_configured: session_bus.original_configured,
        #[cfg(not(target_os = "linux"))]
        session_bus_original_configured: std::env::var_os("DBUS_SESSION_BUS_ADDRESS").is_some(),
        #[cfg(target_os = "linux")]
        session_bus_route: session_bus.route.code().into(),
        #[cfg(not(target_os = "linux"))]
        session_bus_route: "platform_default".into(),
        #[cfg(target_os = "linux")]
        session_bus_split_detected: session_bus.split_detected,
        #[cfg(not(target_os = "linux"))]
        session_bus_split_detected: false,
        #[cfg(target_os = "linux")]
        session_bus_reachable: session_bus.selected_bus_reachable(),
        #[cfg(not(target_os = "linux"))]
        session_bus_reachable: true,
        #[cfg(target_os = "linux")]
        runtime_user_bus_reachable: session_bus.runtime_user_bus_reachable,
        #[cfg(not(target_os = "linux"))]
        runtime_user_bus_reachable: false,
        #[cfg(target_os = "linux")]
        runtime_user_bus_secret_service_available: session_bus
            .runtime_user_bus_secret_service_available,
        #[cfg(not(target_os = "linux"))]
        runtime_user_bus_secret_service_available: false,
        #[cfg(target_os = "linux")]
        secret_service_default_collection_state: default_collection.code().into(),
        #[cfg(not(target_os = "linux"))]
        secret_service_default_collection_state: "platform_default".into(),
        credential_store_state: credential_store_state(),
        startup_failure_reason: None,
        configuration_state: configuration_state.into(),
        configuration_exists: configuration.exists,
        configuration_encrypted: configuration.encrypted,
        configuration_owned_by_current_user: configuration.owned_by_current_user,
        configuration_owner_only_permissions: configuration.owner_only_permissions,
        configuration_directory_writable: configuration.directory_writable,
        tray_available,
        notification_plugin_enabled,
        executables,
    }
}

pub(crate) fn environment_diagnostics(app: &AppHandle) -> EnvironmentDiagnostics {
    let state = app.state::<AppState>();
    let status = state.startup_status();
    let mut diagnostics = environment_diagnostics_snapshot(
        if status.ready {
            "ready"
        } else {
            "locked_or_unavailable"
        },
        app.tray_by_id("main-tray").is_some(),
        !crate::bootstrap::safe_mode(),
    );
    diagnostics.startup_failure_reason = status.reason_code;
    diagnostics
}

#[tauri::command]
pub fn get_environment_diagnostics(app: AppHandle) -> EnvironmentDiagnostics {
    environment_diagnostics(&app)
}

#[cfg(target_os = "linux")]
fn should_initialize_default_collection(
    reason_code: Option<&str>,
    configuration_exists: bool,
) -> bool {
    reason_code == Some(StartupFailureReason::SecretServiceDefaultCollectionMissing.code())
        && !configuration_exists
}

#[tauri::command]
pub fn retry_startup(app: AppHandle) -> AppResult<StartupStatus> {
    let state = app.state::<AppState>();
    #[cfg(target_os = "linux")]
    {
        let before = state.startup_status();
        let configuration = configuration_facts();
        if should_initialize_default_collection(before.reason_code.as_deref(), configuration.exists)
            && crate::linux_secret_service::initialize_default_collection()?
        {
            crate::bootstrap::record("secret-service-default-created");
        }
    }
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
        for name in [
            "sh",
            "bash",
            "git",
            "python3",
            "xdg-open",
            "frpc",
            "cloudflared",
        ] {
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

    #[test]
    fn package_kind_is_bounded_and_never_contains_an_executable_path() {
        let kind = package_kind();
        assert!(["appimage", "deb", "unknown"].contains(&kind.as_str()));
        assert!(!kind.contains('/'));
        assert!(!kind.contains('\\'));
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn default_collection_creation_is_only_allowed_for_fresh_missing_default_state() {
        assert!(should_initialize_default_collection(
            Some(StartupFailureReason::SecretServiceDefaultCollectionMissing.code()),
            false,
        ));
        assert!(!should_initialize_default_collection(
            Some(StartupFailureReason::SecretServiceDefaultCollectionMissing.code()),
            true,
        ));
        assert!(!should_initialize_default_collection(
            Some(StartupFailureReason::SecretServiceLockedOrDenied.code()),
            false,
        ));
    }
}
