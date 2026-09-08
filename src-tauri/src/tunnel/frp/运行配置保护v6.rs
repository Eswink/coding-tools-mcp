//! FRPC needs plaintext at runtime. Restrict a fresh file before writing any
//! credential, then atomically replace the previous configuration.
use std::{fs, io::Write, path::{Path, PathBuf}};
use crate::error::{AppError, AppResult};

pub(super) fn write_private_config(path: &Path, content: &str) -> AppResult<()> {
    let parent = path.parent().ok_or_else(|| AppError::Message("FRP 配置路径无父目录".into()))?;
    fs::create_dir_all(parent)?;
    if fs::symlink_metadata(path).is_ok_and(|m| m.file_type().is_symlink()) {
        return Err(AppError::Message("FRP 配置不能是符号链接".into()));
    }
    let temporary = parent.join(format!(".frpc-{}.tmp", uuid::Uuid::new_v4()));
    let mut options = fs::OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options.open(&temporary)?;
    let _guard = Temporary(temporary.clone());
    #[cfg(windows)]
    restrict_windows_acl(&temporary)?;
    file.write_all(content.as_bytes())?;
    file.sync_all()?;
    drop(file);
    fs::rename(&temporary, path)?;
    Ok(())
}

#[cfg(windows)]
fn restrict_windows_acl(path: &Path) -> AppResult<()> {
    // Fixed script; the path is data in an environment variable, not interpolated
    // PowerShell. No token, private key or user-supplied script enters argv.
    let script = r#"$ErrorActionPreference='Stop'; $sid=[System.Security.Principal.WindowsIdentity]::GetCurrent().User; $acl=New-Object System.Security.AccessControl.FileSecurity; $acl.SetOwner($sid); $acl.SetAccessRuleProtection($true,$false); $rule=New-Object System.Security.AccessControl.FileSystemAccessRule($sid,'FullControl','Allow'); $acl.AddAccessRule($rule); Set-Acl -LiteralPath $env:CODING_TOOLS_FRP_ACL_PATH -AclObject $acl; $actual=Get-Acl -LiteralPath $env:CODING_TOOLS_FRP_ACL_PATH; if(-not $actual.AreAccessRulesProtected -or @($actual.Access).Count -ne 1){throw 'ACL verification failed'}"#;
    let system = std::env::var_os("SystemRoot").ok_or_else(|| AppError::Message("无法定位Windows系统目录".into()))?;
    let status = std::process::Command::new(PathBuf::from(system).join("System32/WindowsPowerShell/v1.0/powershell.exe"))
        .args(["-NoProfile", "-NonInteractive", "-Command", script])
        .env("CODING_TOOLS_FRP_ACL_PATH", path)
        .stdin(std::process::Stdio::null()).stdout(std::process::Stdio::null()).stderr(std::process::Stdio::null())
        .creation_flags(0x08000000).status()?;
    if !status.success() { return Err(AppError::Message("FRP配置权限设置失败；未写入凭据，旧文件已保留。".into())); }
    Ok(())
}

#[cfg(windows)]
use std::os::windows::process::CommandExt;

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
