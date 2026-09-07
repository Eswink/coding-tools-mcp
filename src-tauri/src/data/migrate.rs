use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};

use crate::error::{AppError, AppResult};
use crate::platform::platform;
use crate::settings::AppSettings;

use super::model::{AppData, LegacyProfilesOnlyFile};

const CURRENT_SCHEMA_VERSION: u32 = 1;

const LEGACY_PROFILES_FILE: &str = "profiles.json";
const LEGACY_SETTINGS_FILE: &str = "app_settings.json";

pub fn data_file_path() -> AppResult<PathBuf> {
    Ok(platform().app_config_dir()?.join("data").join("profiles.json"))
}

pub fn load_or_migrate() -> AppResult<AppData> {
    let path = data_file_path()?;
    if path.exists() {
        let raw = fs::read_to_string(&path)?;
        return decode_data(&raw, &path);
    }

    let app_root = platform().app_config_dir()?;
    let mut data = AppData::default();

    let legacy_profiles = app_root.join(LEGACY_PROFILES_FILE);
    if legacy_profiles.exists() {
        let raw = fs::read_to_string(&legacy_profiles)?;
        let file: LegacyProfilesOnlyFile = decode_json(&raw, &legacy_profiles)?;
        data.profiles = file.profiles;
    }

    let legacy_settings = app_root.join(LEGACY_SETTINGS_FILE);
    if legacy_settings.exists() {
        let raw = fs::read_to_string(&legacy_settings)?;
        let settings: AppSettings = decode_json(&raw, &legacy_settings)?;
        merge_settings(&mut data, settings);
    }

    migrate_data(data)
}

// Malformed data must never become an empty default which a later save can overwrite.
fn decode_json<T: serde::de::DeserializeOwned>(raw: &str, path: &Path) -> AppResult<T> {
    // serde can deserialize a defaulted struct from an empty sequence; a
    // configuration file must be a JSON object, not [] or null.
    if !raw.trim_start().starts_with('{') {
        return Err(AppError::Message(format!("配置文件 {} 必须为 JSON 对象。原文件已保留。", path.display())));
    }
    serde_json::from_str(raw).map_err(|error| AppError::Message(format!(
        "配置文件 {} 无效（行 {}，列 {}）。原文件已保留，请恢复备份后重试。",
        path.display(), error.line(), error.column()
    )))
}

fn decode_data(raw: &str, path: &Path) -> AppResult<AppData> {
    migrate_data(decode_json(raw, path)?)
}

pub(super) fn migrate_data(mut data: AppData) -> AppResult<AppData> {
    if data.schema_version > CURRENT_SCHEMA_VERSION {
        return Err(AppError::Message(format!(
            "配置版本 {} 高于当前支持版本 {}，已拒绝读写，请使用更新的应用。",
            data.schema_version, CURRENT_SCHEMA_VERSION
        )));
    }
    for profile in &mut data.profiles {
        if profile.tunnel.tunnel_type == "cloudflare" && profile.tunnel.cloudflare_mode == "quick" {
            profile.tunnel.public_url.clear();
        }
        if profile.actions.tunnel_type == "cloudflare" && profile.actions.cloudflare_mode == "quick" {
            profile.actions.public_url.clear();
        }
    }
    data.schema_version = CURRENT_SCHEMA_VERSION;
    Ok(data)
}

pub fn save(data: &AppData) -> AppResult<()> {
    let path = data_file_path()?;
    write_data(&path, data)
}

/// Commit point is the same-directory rename. Never delete the destination first.
fn write_data(path: &Path, data: &AppData) -> AppResult<()> {
    let parent = path.parent().filter(|p| !p.as_os_str().is_empty()).unwrap_or(Path::new("."));
    fs::create_dir_all(parent)?;
    let normalized = migrate_data(data.clone())?;
    let text = serde_json::to_string_pretty(&normalized)?;
    let temporary = parent.join(format!(".profiles-{}.tmp", uuid::Uuid::new_v4()));
    let mut options = fs::OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options.open(&temporary)?;
    // The guard only owns the newly created path, never a pre-existing destination.
    let _cleanup = TemporaryFile(temporary.clone());
    file.write_all(text.as_bytes())?;
    file.write_all(b"\n")?;
    file.sync_all()?;
    drop(file);
    fs::rename(&temporary, path)?;
    #[cfg(unix)]
    if let Err(error) = fs::File::open(parent).and_then(|dir| dir.sync_all()) {
        // Rename already committed. Returning Err now could trigger a false rollback.
        eprintln!("配置已原子替换，但目录持久化同步失败：{error}");
    }
    Ok(())
}

struct TemporaryFile(PathBuf);

impl Drop for TemporaryFile {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.0);
    }
}

pub fn maybe_backup_legacy_files(path: &Path) -> AppResult<()> {
    if !path.exists() {
        return Ok(());
    }
    let app_root = platform().app_config_dir()?;
    for name in [LEGACY_PROFILES_FILE, LEGACY_SETTINGS_FILE] {
        let legacy = app_root.join(name);
        if legacy.exists() {
            let backup = app_root.join(format!("{name}.bak"));
            if !backup.exists() {
                let _ = fs::rename(&legacy, &backup);
            }
        }
    }
    Ok(())
}

fn merge_settings(data: &mut AppData, settings: AppSettings) {
    data.frp_profiles = settings.frp_profiles;
    data.last_workspace_id = settings.last_workspace_id;
    data.download = settings.download;
    data.proxy = settings.proxy;
    data.shared_secrets = settings.shared_secrets;
    data.workspace_secrets = settings.workspace_secrets;
    data.app_secrets = settings.app_secrets;
}


#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn damaged_json_is_not_treated_as_an_empty_workspace() {
        for raw in ["", "{", "[]", "null", r#"{"profiles":"not-an-array"}"#] {
            assert!(decode_data(raw, Path::new("profiles.json")).is_err());
        }
    }

    #[test]
    fn valid_legacy_empty_data_remains_readable() {
        assert!(decode_data(r#"{"profiles":[]}"#, Path::new("profiles.json"))
            .unwrap().profiles.is_empty());
    }

    #[test]
    fn decoding_errors_do_not_echo_secret_values() {
        let result = decode_data(r#"{"profiles":"canary-secret-not-for-logs"}"#, Path::new("profiles.json"));
        let error = result.unwrap_err().to_string();
        assert!(error.contains("原文件已保留"));
        assert!(!error.contains("canary-secret"));
    }

    #[test]
    fn atomic_replace_writes_complete_json_and_leaves_no_temp_file() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("profiles.json");
        fs::write(&path, "old file").unwrap();
        let mut data = AppData::default();
        data.last_workspace_id = "new-workspace".into();
        write_data(&path, &data).unwrap();
        let restored = decode_data(&fs::read_to_string(&path).unwrap(), &path).unwrap();
        assert_eq!(restored.last_workspace_id, "new-workspace");
        assert_eq!(fs::read_dir(dir.path()).unwrap().count(), 1);
    }

    #[test]
    fn failed_rename_preserves_destination_and_cleans_temporary_file() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("profiles.json");
        fs::create_dir(&path).unwrap();
        fs::write(path.join("original"), b"unchanged").unwrap();
        assert!(write_data(&path, &AppData::default()).is_err());
        assert_eq!(fs::read(path.join("original")).unwrap(), b"unchanged");
        assert_eq!(fs::read_dir(dir.path()).unwrap().count(), 1);
    }

    #[cfg(unix)]
    #[test]
    fn persisted_credentials_are_owner_only_on_unix() {
        use std::os::unix::fs::PermissionsExt;
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("profiles.json");
        write_data(&path, &AppData::default()).unwrap();
        assert_eq!(fs::metadata(path).unwrap().permissions().mode() & 0o777, 0o600);
    }

    #[test]
    fn unknown_top_level_metadata_survives_a_read_write_roundtrip() {
        let data = decode_data(r#"{"extension":{"retained":true}}"#, Path::new("profiles.json")).unwrap();
        assert_eq!(data.schema_version, CURRENT_SCHEMA_VERSION);
        let value = serde_json::to_value(data).unwrap();
        assert_eq!(value["extension"]["retained"], true);
    }

    #[test]
    fn future_schema_cannot_overwrite_an_existing_file() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("profiles.json");
        fs::write(&path, b"original").unwrap();
        let mut data = AppData::default();
        data.schema_version = CURRENT_SCHEMA_VERSION + 1;
        assert!(write_data(&path, &data).is_err());
        assert_eq!(fs::read(&path).unwrap(), b"original");
    }

    #[test]
    fn migration_drops_only_temporary_urls_and_keeps_fixed_identity_and_secrets() {
        let mut data = AppData::default();
        let mut profile = crate::workspace::WorkspaceProfile::new("/tmp/migrate".into(), None);
        profile.tunnel.tunnel_type = "cloudflare".into();
        profile.tunnel.cloudflare_mode = "quick".into();
        profile.tunnel.public_url = "https://old.trycloudflare.com".into();
        profile.actions.tunnel_type = "cloudflare".into();
        profile.actions.cloudflare_mode = "named".into();
        profile.actions.public_url = "https://actions.example.com".into();
        data.profiles.push(profile);
        data.shared_secrets.insert("oauth_token_secret".into(), "unchanged-signing-key".into());
        let migrated = migrate_data(data).unwrap();
        assert!(migrated.profiles[0].tunnel.public_url.is_empty());
        assert_eq!(migrated.profiles[0].actions.public_url, "https://actions.example.com");
        assert_eq!(migrated.shared_secrets["oauth_token_secret"], "unchanged-signing-key");
    }

}
