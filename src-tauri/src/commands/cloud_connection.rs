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

use crate::cloud_application::CloudConnectionStatus;

#[tauri::command]
pub async fn import_cloud_connection_files(
    state: State<'_, AppState>,
    id: String,
    config_path: String,
    private_key_path: String,
) -> AppResult<ConnectionSummary> {
    super::runtime::ensure_service_start_allowed()?;
    let _gate = super::runtime::RESTART_GATE.lock().await;
    let store = local_store(&state, &id)?;
    tauri::async_runtime::spawn_blocking(move || {
        let public = bounded_local_file(Path::new(&config_path), 16 * 1024)?;
        let private = bounded_local_file(Path::new(&private_key_path), 4096)?;
        let public = std::str::from_utf8(&public).map_err(|_| unavailable())?;
        let private = std::str::from_utf8(&private).map_err(|_| unavailable())?;
        let input = CheckedImport::parse(public, private).map_err(|_| unavailable())?;
        store
            .initialize(input)
            .map_err(|error| AppError::Message(error.to_string()))
    })
    .await
    .map_err(|_| unavailable())?
}
fn bounded_local_file(path: &Path, limit: usize) -> AppResult<Zeroizing<Vec<u8>>> {
    use std::{fs::OpenOptions, io::Read};
    if !path.is_absolute() {
        return Err(unavailable());
    }
    let metadata = std::fs::symlink_metadata(path).map_err(|_| unavailable())?;
    if !metadata.is_file() || metadata.file_type().is_symlink() {
        return Err(unavailable());
    }
    let mut options = OpenOptions::new();
    options.read(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK);
    }
    #[cfg(windows)]
    {
        use std::os::windows::fs::{MetadataExt, OpenOptionsExt};
        for ancestor in path.ancestors() {
            let attrs = std::fs::symlink_metadata(ancestor).map_err(|_| unavailable())?;
            if attrs.file_attributes() & 0x400 != 0 {
                return Err(unavailable());
            }
        }
        options.custom_flags(0x00200000); // FILE_FLAG_OPEN_REPARSE_POINT
    }
    // Keep the preflight HANDLE alive while reopening. File IDs/volume and
    // link counts are compared from actual handles, not unstable Metadata APIs.
    #[cfg(windows)]
    let preflight = options.open(path).map_err(|_| unavailable())?;
    #[cfg(windows)]
    let expected_identity = windows_file_identity(&preflight)?;
    let file = options.open(path).map_err(|_| unavailable())?;
    #[cfg(windows)]
    if windows_file_identity(&file)? != expected_identity {
        return Err(unavailable());
    }
    let actual = file.metadata().map_err(|_| unavailable())?;
    if !actual.is_file() || actual.len() == 0 || actual.len() > limit as u64 {
        return Err(unavailable());
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        if actual.dev() != metadata.dev() || actual.ino() != metadata.ino() || actual.nlink() != 1 {
            return Err(unavailable());
        }
    }
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        if actual.file_attributes() & 0x400 != 0 {
            return Err(unavailable());
        }
    }
    let mut bytes = Zeroizing::new(Vec::new());
    file.take(limit as u64 + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| unavailable())?;
    if bytes.len() > limit || bytes.is_empty() {
        return Err(unavailable());
    }
    Ok(bytes)
}

#[cfg(windows)]
fn windows_file_identity(file: &std::fs::File) -> AppResult<(u32, u32, u32)> {
    use std::os::windows::io::AsRawHandle;
    use windows::Win32::{
        Foundation::HANDLE,
        Storage::FileSystem::{GetFileInformationByHandle, BY_HANDLE_FILE_INFORMATION},
    };
    let mut info = BY_HANDLE_FILE_INFORMATION::default();
    unsafe { GetFileInformationByHandle(HANDLE(file.as_raw_handle()), &mut info) }
        .map_err(|_| unavailable())?;
    if info.dwFileAttributes & (0x400 | 0x10) != 0 || info.nNumberOfLinks != 1 {
        return Err(unavailable());
    }
    Ok((
        info.dwVolumeSerialNumber,
        info.nFileIndexHigh,
        info.nFileIndexLow,
    ))
}

#[tauri::command]
pub async fn start_cloud_connection(
    state: State<'_, AppState>,
    id: String,
    initialize_journals: bool,
) -> AppResult<CloudConnectionStatus> {
    super::runtime::ensure_service_start_allowed()?;
    let _gate = super::runtime::RESTART_GATE.lock().await;
    super::runtime::ensure_service_start_allowed()?;
    let profile = state.with_workspaces(|store| store.get(&id).cloned().ok_or_else(unavailable))?;
    if profile.auth.auth_type != "oauth" {
        return Err(AppError::Message(
            "云连接需要本机 OAuth 聊天授权服务。".into(),
        ));
    }
    let lease =
        state.with_runtime(|runtime| runtime.mcp_context_lease(&id).ok_or_else(unavailable))?;
    let store = local_store(&state, &id)?;
    let material = tauri::async_runtime::spawn_blocking(move || store.runtime_material())
        .await
        .map_err(|_| unavailable())?
        .map_err(|_| unavailable())?;
    state
        .cloud_agents
        .start(&id, lease, material, initialize_journals)
}

#[tauri::command]
pub async fn stop_cloud_connection(
    state: State<'_, AppState>,
    id: String,
) -> AppResult<CloudConnectionStatus> {
    let _gate = super::runtime::RESTART_GATE.lock().await;
    let _ = local_store(&state, &id)?;
    state.cloud_agents.stop(&id).await?;
    state.cloud_agents.status(&id, true)
}

#[tauri::command]
pub async fn get_cloud_connection_status(
    state: State<'_, AppState>,
    id: String,
) -> AppResult<CloudConnectionStatus> {
    let store = local_store(&state, &id)?;
    let configured = tauri::async_runtime::spawn_blocking(move || store.summary())
        .await
        .map_err(|_| unavailable())?
        .map_err(|_| unavailable())?
        .is_some();
    state.cloud_agents.status(&id, configured)
}

#[cfg(test)]
mod file_tests {
    use super::*;
    #[test]
    fn file_import_rejects_empty_oversize_relative_and_directory_inputs() {
        let root = tempfile::tempdir().unwrap();
        let file = root.path().join("input.json");
        assert!(bounded_local_file(Path::new("input.json"), 4).is_err());
        assert!(bounded_local_file(root.path(), 4).is_err());
        std::fs::write(&file, "").unwrap();
        assert!(bounded_local_file(&file, 4).is_err());
        std::fs::write(&file, "12345").unwrap();
        assert!(bounded_local_file(&file, 4).is_err());
        std::fs::write(&file, "1234").unwrap();
        assert_eq!(&*bounded_local_file(&file, 4).unwrap(), b"1234");
    }
    #[cfg(unix)]
    #[test]
    fn file_import_rejects_symlink_and_hardlink_targets() {
        let root = tempfile::tempdir().unwrap();
        let target = root.path().join("input.json");
        std::fs::write(&target, "{}").unwrap();
        let alias = root.path().join("alias.json");
        std::os::unix::fs::symlink(&target, &alias).unwrap();
        assert!(bounded_local_file(&alias, 4096).is_err());
        std::fs::remove_file(&alias).unwrap();
        std::fs::hard_link(&target, &alias).unwrap();
        assert!(bounded_local_file(&alias, 4096).is_err());
    }
}

#[cfg(all(test, windows))]
mod windows_file_tests {
    use super::*;
    #[test]
    fn windows_handle_identity_is_stable_and_hardlink_import_is_rejected() {
        let root = tempfile::tempdir().unwrap();
        let file = root.path().join("input.json");
        std::fs::write(&file, "{}").unwrap();
        let a = std::fs::File::open(&file).unwrap();
        let b = std::fs::File::open(&file).unwrap();
        assert_eq!(
            windows_file_identity(&a).unwrap(),
            windows_file_identity(&b).unwrap()
        );
        assert!(bounded_local_file(&file, 4096).is_ok());
        std::fs::hard_link(&file, root.path().join("alias.json")).unwrap();
        assert!(bounded_local_file(&file, 4096).is_err());
    }
}
