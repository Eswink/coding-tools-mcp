//! Validate generated configuration before replacing a running route.
use std::io::Write;
use std::path::PathBuf;
use std::process::Stdio;
use std::time::Duration;

use crate::error::{AppError, AppResult};
use crate::platform::platform;
use super::{build_frpc_toml_for_routes, FrpServerConfig};

struct ValidationFile(PathBuf);
impl Drop for ValidationFile {
    fn drop(&mut self) {
        let _ = std::fs::remove_file(&self.0);
    }
}

pub(crate) async fn verify_frpc_configs(configs: &[FrpServerConfig]) -> AppResult<()> {
    for config in configs {
        let route = &config.proxy.options;
        if route.proxy_type == "https" && route.https_mode == "https2http" {
            for name in [&route.tls_cert_file, &route.tls_key_file] {
                let path = std::path::Path::new(name.trim());
                if !path.is_absolute() || !path.is_file() || std::fs::File::open(path).is_err() {
                    return Err(AppError::Message("https2http 证书 / 私钥必须是本机可读取文件的绝对路径。".into()));
                }
            }
        }
    }
    let binary = super::client::ensure_frpc().await?;
    let dir = platform().app_config_dir()?.join("frpc");
    std::fs::create_dir_all(&dir)?;
    let path = dir.join(format!("verify-{}.toml", uuid::Uuid::new_v4()));
    let mut options = std::fs::OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options.open(&path)?;
    let guard = ValidationFile(path);
    let mut checked = configs.to_vec();
    for config in &mut checked {
        if config.token.is_some() { config.token = Some("validation-only-not-a-token".into()); }
    }
    let written = file.write_all(build_frpc_toml_for_routes(&checked).as_bytes())
        .and_then(|_| file.sync_all());
    drop(file);
    written?;

    let mut command = tokio::process::Command::new(binary);
    command.arg("verify").arg("-c").arg(&guard.0)
        .stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null())
        .kill_on_drop(true);
    #[cfg(windows)]
    command.creation_flags(0x08000000);
    let mut child = command.spawn().map_err(|error| {
        AppError::Message(format!("无法启动 frpc 配置校验：{error}"))
    })?;
    let result = tokio::time::timeout(Duration::from_secs(15), child.wait()).await;
    match result {
        Ok(Ok(status)) if status.success() => Ok(()),
        Ok(Ok(status)) => Err(AppError::Message(format!(
            "frpc verify 配置校验失败（退出状态 {status}）；原有线路未被替换。请检查域名、代理类型、目标和证书。"
        ))),
        Ok(Err(error)) => {
            let _ = child.kill().await;
            let _ = child.wait().await;
            Err(AppError::Message(format!("等待 frpc 配置校验失败：{error}")))
        }
        Err(_) => {
            let _ = child.kill().await;
            let _ = child.wait().await;
            Err(AppError::Message("frpc 配置校验超时，校验进程已终止，原有线路未被替换。".into()))
        }
    }
}
