//! FRPC needs plaintext at runtime. Restrict a fresh file before writing any
//! credential, then atomically replace the previous configuration. Windows uses
//! a native creation-time DACL; no shell process or environment mutation is needed.
use std::{fs, io::Write, path::{Path, PathBuf}};
use crate::error::{AppError, AppResult};

pub(super) fn write_private_config(path: &Path, content: &str) -> AppResult<()> {
    let parent = path.parent().filter(|p| !p.as_os_str().is_empty()).unwrap_or(Path::new("."));
    fs::create_dir_all(parent)?;
    if fs::symlink_metadata(path).is_ok_and(|m| m.file_type().is_symlink()) {
        return Err(AppError::Message("FRP 配置不能是符号链接".into()));
    }
    let temporary = parent.join(format!(".frpc-{}.tmp", uuid::Uuid::new_v4()));
    // Arm cleanup only after exclusive creation succeeds, so even a name
    // collision cannot delete a file owned by another operation.
    let mut file = create_private_file(&temporary)?;
    let _guard = Temporary(temporary.clone());
    let written = (|| -> AppResult<()> {
        #[cfg(windows)]
        private_windows::verify_current_user(&file)?;
        file.write_all(content.as_bytes())?;
        file.sync_all()?;
        Ok(())
    })();
    // Close before cleanup on both success and failure (Windows sharing rules).
    drop(file);
    written?;
    fs::rename(&temporary, path)?;
    Ok(())
}

#[cfg(windows)]
#[path = "私有文件Windowsv7.rs"]
mod private_windows;

fn create_private_file(path: &Path) -> AppResult<fs::File> {
    #[cfg(windows)]
    { private_windows::create(path) }
    #[cfg(not(windows))]
    {
        let mut options = fs::OpenOptions::new();
        options.write(true).create_new(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        Ok(options.open(path)?)
    }
}

pub(super) fn redact(line: &str, values: &[String]) -> String {
    let mut values: Vec<&str> = values.iter().map(String::as_str).filter(|v| !v.is_empty()).collect();
    values.sort_by_key(|v| std::cmp::Reverse(v.len()));
    values.dedup();
    let mut line = line.to_string();
    for value in values { line = line.replace(value, "<REDACTED>"); }
    line
}

struct Temporary(PathBuf);
impl Drop for Temporary { fn drop(&mut self) { let _ = fs::remove_file(&self.0); } }

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn private_config_replaces_existing_file_without_temp_leaks() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("frpc.toml");
        fs::write(&path, "old").unwrap();
        write_private_config(&path, "runtime-canary-v6").unwrap();
        assert_eq!(fs::read_to_string(&path).unwrap(), "runtime-canary-v6");
        assert_eq!(fs::read_dir(dir.path()).unwrap().count(), 1);
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            assert_eq!(fs::metadata(&path).unwrap().permissions().mode() & 0o777, 0o600);
        }
    }
    #[test]
    fn failed_config_replace_preserves_original_directory() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("frpc.toml"); fs::create_dir(&path).unwrap();
        assert!(write_private_config(&path, "canary").is_err());
        assert!(path.is_dir());
        assert_eq!(fs::read_dir(dir.path()).unwrap().count(), 1);
    }
    #[test]
    fn tokens_and_proxy_credentials_are_removed_from_logs() {
        assert_eq!(redact("token=canary; proxy=http://u:canary@proxy", &["canary".into(), "http://u:canary@proxy".into(), "".into()]),
            "token=<REDACTED>; proxy=<REDACTED>");
    }
}

#[cfg(test)]
#[path = "私有配置回归v7.rs"]
mod private_config_tests;
