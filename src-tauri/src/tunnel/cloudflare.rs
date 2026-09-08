use std::path::{Path, PathBuf};
use std::time::Duration;

use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::process::{Child, Command};
use tokio::sync::oneshot;
use tokio::time;

use crate::error::{AppError, AppResult};
use crate::platform::platform;
use crate::settings::ProxyConfig;

const READY_TIMEOUT: Duration = Duration::from_secs(30);

/// Handle to a supervised `cloudflared` child process.
pub struct CloudflareTunnelHandle {
    pub child: Child,
    pub public_url: String,
    pub pid: Option<u32>,
}

pub fn resolve_cloudflared() -> AppResult<PathBuf> {
    platform()
        .cloudflared_candidates()
        .into_iter()
        .find(|path| path.is_file())
        .or_else(|| cached_cloudflared_path().filter(|path| path.is_file()))
        .ok_or_else(|| {
            AppError::Message(
                "未找到 cloudflared。请到「软件管理」安装，或自行安装 Cloudflare Tunnel CLI。\n\
                 Windows 可执行：winget install Cloudflare.cloudflared"
                    .into(),
            )
        })
}

/// Path where the app caches a self-managed cloudflared binary.
pub(crate) fn cached_cloudflared_path() -> Option<PathBuf> {
    platform()
        .app_config_dir()
        .ok()
        .map(|dir| dir.join("bin").join(cloudflared_binary_name()))
}

pub(crate) fn cloudflared_binary_name() -> &'static str {
    #[cfg(windows)]
    {
        "cloudflared.exe"
    }
    #[cfg(not(windows))]
    {
        "cloudflared"
    }
}

/// GitHub release asset name for the current platform.
fn cloudflared_release_asset() -> AppResult<&'static str> {
    #[cfg(all(target_os = "windows", target_arch = "x86_64"))]
    {
        Ok("cloudflared-windows-amd64.exe")
    }
    #[cfg(all(target_os = "windows", target_arch = "aarch64"))]
    {
        Ok("cloudflared-windows-arm64.exe")
    }
    #[cfg(all(target_os = "linux", target_arch = "x86_64"))]
    {
        Ok("cloudflared-linux-amd64")
    }
    #[cfg(all(target_os = "linux", target_arch = "aarch64"))]
    {
        Ok("cloudflared-linux-arm64")
    }
    #[cfg(all(target_os = "macos", target_arch = "x86_64"))]
    {
        Ok("cloudflared-darwin-amd64.tgz")
    }
    #[cfg(all(target_os = "macos", target_arch = "aarch64"))]
    {
        Ok("cloudflared-darwin-arm64.tgz")
    }
    #[cfg(not(any(
        all(target_os = "windows", target_arch = "x86_64"),
        all(target_os = "windows", target_arch = "aarch64"),
        all(target_os = "linux", target_arch = "x86_64"),
        all(target_os = "linux", target_arch = "aarch64"),
        all(target_os = "macos", target_arch = "x86_64"),
        all(target_os = "macos", target_arch = "aarch64"),
    )))]
    {
        Err(AppError::Message(
            "当前平台暂不支持自动下载 cloudflared。".into(),
        ))
    }
}

/// Latest cloudflared release. Pinned for reproducibility; bump as needed.
const CLOUDFLARED_VERSION: &str = "2025.6.1";

/// Download cloudflared into the app cache `bin/` directory, honoring the
/// configured mirror + proxy. Windows/Linux assets are raw binaries; macOS
/// assets are `.tgz` archives that need extraction.
pub(crate) async fn download_cloudflared_to_cache() -> AppResult<PathBuf> {
    let settings = crate::settings::AppSettings::load_or_default();
    let asset = cloudflared_release_asset()?;
    let url = format!(
        "https://github.com/cloudflare/cloudflared/releases/download/{CLOUDFLARED_VERSION}/{asset}"
    );
    let dest = cached_cloudflared_path()
        .ok_or_else(|| AppError::Message("无法解析缓存目录。".into()))?;
    if let Some(parent) = dest.parent() {
        std::fs::create_dir_all(parent)?;
    }

    let bytes = crate::tunnel::download::download_release_asset(&settings, &url, "cloudflared").await?;

    if asset.ends_with(".tgz") {
        extract_cloudflared_from_tar_gz(&bytes, &dest)?;
    } else {
        std::fs::write(&dest, &bytes)?;
    }

    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        if let Ok(meta) = std::fs::metadata(&dest) {
            let mut perms = meta.permissions();
            perms.set_mode(0o755);
            let _ = std::fs::set_permissions(&dest, perms);
        }
    }

    if dest.is_file() {
        Ok(dest)
    } else {
        Err(AppError::Message("cloudflared 自动安装失败。".into()))
    }
}

#[cfg(target_os = "macos")]
fn extract_cloudflared_from_tar_gz(bytes: &[u8], dest: &Path) -> AppResult<()> {
    let decoder = flate2::read::GzDecoder::new(bytes);
    let mut archive = tar::Archive::new(decoder);
    for entry in archive
        .entries()
        .map_err(|err| AppError::Message(format!("解压 cloudflared 安装包失败: {err}")))?
    {
        let mut entry =
            entry.map_err(|err| AppError::Message(format!("读取 cloudflared 安装包失败: {err}")))?;
        let path = entry
            .path()
            .map_err(|err| AppError::Message(err.to_string()))?
            .to_string_lossy()
            .replace('\\', "/");
        if path.ends_with("cloudflared") {
            let mut out = std::fs::File::create(dest)?;
            std::io::copy(&mut entry, &mut out)?;
            return Ok(());
        }
    }
    Err(AppError::Message(
        "cloudflared 安装包中未找到可执行文件。".into(),
    ))
}

#[cfg(not(target_os = "macos"))]
#[allow(dead_code)]
fn extract_cloudflared_from_tar_gz(_bytes: &[u8], _dest: &Path) -> AppResult<()> {
    Err(AppError::Message(
        "当前平台的 cloudflared 无需解压。".into(),
    ))
}

pub fn extract_trycloudflare_url(line: &str) -> Option<String> {
    const PREFIX: &str = "https://";
    const SUFFIX: &str = ".trycloudflare.com";
    let lower = line.to_ascii_lowercase();
    let mut search_from = 0;

    while let Some(rel) = lower[search_from..].find(PREFIX) {
        let start = search_from + rel;
        let Some(suffix_rel) = lower[start..].find(SUFFIX) else {
            break;
        };
        let end = start + suffix_rel + SUFFIX.len();
        let host = &line[start + PREFIX.len()..end - SUFFIX.len()];
        if host
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '-')
            && !host.is_empty()
        {
            return Some(line[start..end].trim_end_matches('/').to_string());
        }
        search_from = start + PREFIX.len();
    }
    None
}

/// Apply the global proxy to a tunnel child process environment.
pub(crate) fn apply_proxy_env(cmd: &mut Command, proxy: &ProxyConfig) {
    let url = match proxy.mode.as_str() {
        "manual" if !proxy.url.trim().is_empty() => Some(proxy.url.trim().to_string()),
        "system" => std::env::var("HTTPS_PROXY")
            .ok()
            .filter(|s| !s.is_empty())
            .or_else(|| std::env::var("HTTP_PROXY").ok().filter(|s| !s.is_empty()))
            .or_else(|| std::env::var("ALL_PROXY").ok().filter(|s| !s.is_empty())),
        _ => None,
    };
    if let Some(url) = url {
        for key in [
            "HTTPS_PROXY",
            "HTTP_PROXY",
            "https_proxy",
            "http_proxy",
            "ALL_PROXY",
            "all_proxy",
        ] {
            cmd.env(key, &url);
        }
        // Some cloudflared builds consult this dedicated variable.
        cmd.env("TUNNEL_HTTP_PROXY", &url);
    }
}

/// Spawn a temporary or named tunnel. Connection readiness does not imply
/// successful DNS, origin HTTP, or OAuth health checks.
#[allow(clippy::too_many_arguments)]
pub async fn spawn_cloudflare_tunnel(
    port: u16, cwd: &Path, log_path: &Path, cloudflare_mode: &str,
    cloudflare_token: &str, named_public_url: &str, use_proxy: bool, use_http2: bool,
) -> AppResult<CloudflareTunnelHandle> {
    let quick = match cloudflare_mode {
        "quick" => true,
        "named" => false,
        _ => return Err(AppError::Message("未知 Cloudflare 模式。".into())),
    };
    let named_url = if quick {
        String::new()
    } else {
        if cloudflare_token.trim().is_empty() {
            return Err(AppError::Message("命名隧道需要 Cloudflare Tunnel Token。".into()));
        }
        crate::workspace::endpoint::normalize_named_origin(named_public_url)
            .map_err(AppError::Message)?
    };
    if port == 0 { return Err(AppError::Message("本地服务端口不能为 0。".into())); }
    let cloudflared = resolve_cloudflared()?;
    // Fail before spawning if the log target cannot be opened.
    if let Some(parent) = log_path.parent() { std::fs::create_dir_all(parent)?; }
    let log = tokio::fs::OpenOptions::new().create(true).append(true).open(log_path).await?;
    let mut cmd = Command::new(&cloudflared);
    cmd.current_dir(cwd).kill_on_drop(true);
    cmd.stdin(std::process::Stdio::null());
    cmd.stdout(std::process::Stdio::piped());
    cmd.stderr(std::process::Stdio::piped());
    #[cfg(windows)]
    cmd.creation_flags(0x00000200 | 0x08000000);
    #[cfg(unix)]
    cmd.process_group(0);
    let settings = crate::settings::AppSettings::load_or_default();
    if use_proxy { apply_proxy_env(&mut cmd, &settings.proxy); }
    configure_cloudflare_command(&mut cmd, port, quick, cloudflare_token, use_http2);

    let mut child = cmd.spawn()
        .map_err(|err| AppError::Message(format!("启动 cloudflared 失败: {err}")))?;
    let pid = child.id();
    let Some(stdout) = child.stdout.take() else {
        stop_child(child, pid).await?;
        return Err(AppError::Message("无法读取 cloudflared 输出，已停止子进程。".into()));
    };
    let stderr = child.stderr.take();
    let (ready_tx, ready_rx) = oneshot::channel();
    let token = cloudflare_token.trim().to_string();
    let reader = tokio::spawn(stream_cloudflare_output(
        stdout, stderr, log, quick, named_url, token, ready_tx,
    ));
    let ready = match time::timeout(READY_TIMEOUT, ready_rx).await {
        Ok(Ok(result)) => result,
        Ok(Err(_)) => Err("cloudflared 日志任务意外结束，未确认连接。".into()),
        Err(_) => Err(format!(
            "{} 在 {} 秒内未确认隧道连接{}；请检查 Token / 网络并查看日志：{}",
            if quick { "Quick Tunnel" } else { "Named Tunnel" },
            READY_TIMEOUT.as_secs(), if quick { "与临时地址" } else { "" }, log_path.display(),
        )),
    };
    let public_url = match ready {
        Ok(url) => url,
        Err(message) => {
            let _ = stop_child(child, pid).await;
            reader.abort();
            let _ = reader.await;
            return Err(AppError::Message(message));
        }
    };
    match child.try_wait() {
        Ok(None) => Ok(CloudflareTunnelHandle { child, public_url, pid }),
        _ => {
            let _ = stop_child(child, pid).await;
            reader.abort();
            let _ = reader.await;
            Err(AppError::Message("cloudflared 在确认连接后已退出，请检查日志。".into()))
        }
    }
}

fn configure_cloudflare_command(cmd: &mut Command, port: u16, quick: bool, token: &str, http2: bool) {
    cmd.arg("tunnel");
    push_cloudflare_protocol_args(cmd, http2);
    cmd.env_remove("TUNNEL_TOKEN_FILE");
    if quick {
        cmd.env_remove("TUNNEL_TOKEN");
        cmd.args(["--url", &format!("http://127.0.0.1:{port}")]);
    } else {
        // Supported by the pinned cloudflared version. The same OS user may
        // still inspect process environments; this is not encrypted storage.
        cmd.env("TUNNEL_TOKEN", token.trim());
        cmd.arg("run");
    }
}

#[derive(Default)]
struct TunnelReadiness {
    public_url: Option<String>,
    connected: bool,
}

impl TunnelReadiness {
    fn observe(&mut self, line: &str, quick: bool, named_url: &str) -> Option<String> {
        if line.to_ascii_lowercase().contains("registered tunnel connection") {
            self.connected = true;
        }
        if quick && self.public_url.is_none() {
            self.public_url = extract_trycloudflare_url(line);
        }
        if !self.connected { return None; }
        if quick { self.public_url.clone() } else { Some(named_url.to_string()) }
    }
}

fn redact_cloudflare_line(line: &str, token: &str) -> String {
    if token.is_empty() { line.to_string() } else { line.replace(token, "<REDACTED>") }
}

async fn stream_cloudflare_output<R, E>(
    stdout: R, stderr: Option<E>, mut log: tokio::fs::File,
    quick: bool, named_url: String, token: String,
    ready_tx: oneshot::Sender<Result<String, String>>,
) where
    R: tokio::io::AsyncRead + Unpin + Send + 'static,
    E: tokio::io::AsyncRead + Unpin + Send + 'static,
{
    let mut ready_tx = Some(ready_tx);
    let mut readiness = TunnelReadiness::default();
    let mut out = BufReader::new(stdout).lines();
    let mut err = stderr.map(|stream| BufReader::new(stream).lines());
    let mut out_open = true;
    // One task owns both readers: no detached nested tasks or unbounded queue.
    while out_open || err.is_some() {
        let (is_stdout, result) = tokio::select! {
            result = out.next_line(), if out_open => (true, result),
            result = async { err.as_mut().expect("guarded stderr").next_line().await }, if err.is_some() => (false, result),
        };
        let line = match result {
            Ok(Some(line)) => line,
            Ok(None) => {
                if is_stdout { out_open = false; } else { err = None; }
                continue;
            }
            Err(_) => {
                if let Some(tx) = ready_tx.take() {
                    let _ = tx.send(Err("读取 cloudflared 输出失败，未确认连接。".into()));
                }
                return;
            }
        };
        let redacted = redact_cloudflare_line(&line, &token);
        if log.write_all(format!("{redacted}\n").as_bytes()).await.is_err() || log.flush().await.is_err() {
            if let Some(tx) = ready_tx.take() {
                let _ = tx.send(Err("写入 cloudflared 日志失败，未确认连接。".into()));
            }
            return;
        }
        if let Some(url) = readiness.observe(&line, quick, &named_url) {
            if let Some(tx) = ready_tx.take() { let _ = tx.send(Ok(url)); }
        }
    }
    if let Some(tx) = ready_tx.take() {
        let _ = tx.send(Err("cloudflared 输出已结束，但没有有效连接证据。".into()));
    }
}

pub async fn stop_child(mut child: Child, pid: Option<u32>) -> AppResult<()> {
    if let Some(pid) = pid {
        let _ = platform().terminate_process_tree(pid);
    }

    let _ = child.kill().await;
    let _ = time::timeout(Duration::from_secs(3), child.wait()).await;
    Ok(())
}

fn push_cloudflare_protocol_args(cmd: &mut Command, use_http2: bool) {
    if use_http2 {
        cmd.args(["--protocol", "http2", "--post-quantum=false"]);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tokio::process::Command;

    fn command_args(use_http2: bool) -> Vec<String> {
        let mut cmd = Command::new("cloudflared");
        push_cloudflare_protocol_args(&mut cmd, use_http2);
        cmd.as_std()
            .get_args()
            .map(|arg| arg.to_string_lossy().into_owned())
            .collect()
    }

    #[test]
    fn adds_http2_protocol_args_when_enabled() {
        assert_eq!(
            command_args(true),
            vec!["--protocol", "http2", "--post-quantum=false"]
        );
    }

    #[test]
    fn omits_protocol_args_when_disabled() {
        assert!(command_args(false).is_empty());
    }

    #[test]
    fn extracts_trycloudflare_url_from_log_line() {
        let line = "INF | https://abc-def.trycloudflare.com is your tunnel URL";
        assert_eq!(
            extract_trycloudflare_url(line).as_deref(),
            Some("https://abc-def.trycloudflare.com")
        );
    }

    #[test]
    fn ignores_invalid_hosts() {
        let line = "https://bad_host.trycloudflare.com";
        assert!(extract_trycloudflare_url(line).is_none());
    }
    #[test]
    fn metrics_does_not_imply_named_readiness() {
        let mut ready = TunnelReadiness::default();
        assert!(ready.observe("INF Starting metrics server", false, "https://mcp.example.com").is_none());
        assert_eq!(ready.observe("INF Registered tunnel connection connIndex=0", false, "https://mcp.example.com").as_deref(), Some("https://mcp.example.com"));
    }

    #[test]
    fn quick_needs_both_url_and_connection_in_either_order() {
        for connection_first in [false, true] {
            let mut ready = TunnelReadiness::default();
            let url = "https://example-test.trycloudflare.com";
            let connection = "INF Registered tunnel connection connIndex=0";
            let (first, second) = if connection_first { (connection, url) } else { (url, connection) };
            assert!(ready.observe(first, true, "").is_none());
            assert_eq!(ready.observe(second, true, "").as_deref(), Some(url));
        }
    }

    #[test]
    fn named_token_is_not_in_command_arguments() {
        let mut cmd = Command::new("cloudflared");
        configure_cloudflare_command(&mut cmd, 28766, false, "test-canary-not-a-real-token", true);
        let args: Vec<_> = cmd.as_std().get_args().map(|v| v.to_string_lossy().into_owned()).collect();
        assert_eq!(args, ["tunnel", "--protocol", "http2", "--post-quantum=false", "run"]);
        let token = cmd.as_std().get_envs().find(|(key, _)| *key == "TUNNEL_TOKEN").unwrap();
        assert_eq!(token.1.unwrap(), "test-canary-not-a-real-token");
        assert_eq!(redact_cloudflare_line("token=test-canary-not-a-real-token", "test-canary-not-a-real-token"), "token=<REDACTED>");
    }

    #[test]
    fn quick_does_not_inherit_named_credentials() {
        let mut cmd = Command::new("cloudflared");
        configure_cloudflare_command(&mut cmd, 28766, true, "unused", false);
        for key in ["TUNNEL_TOKEN", "TUNNEL_TOKEN_FILE"] {
            assert!(cmd.as_std().get_envs().any(|(name, value)| name == key && value.is_none()));
        }
    }

    #[tokio::test]
    async fn named_metrics_then_eof_is_an_error() {
        let dir = tempfile::tempdir().unwrap();
        let log = tokio::fs::File::create(dir.path().join("cloudflared.log")).await.unwrap();
        let (mut writer, reader) = tokio::io::duplex(1024);
        writer.write_all(b"INF Starting metrics server\n").await.unwrap();
        drop(writer);
        let (tx, rx) = oneshot::channel();
        stream_cloudflare_output(reader, None::<tokio::io::Empty>, log, false,
            "https://mcp.example.com".into(), "".into(), tx).await;
        assert!(rx.await.unwrap().is_err());
    }

    #[tokio::test]
    async fn stderr_connection_is_read_when_stdout_is_idle() {
        let dir = tempfile::tempdir().unwrap();
        let log = tokio::fs::File::create(dir.path().join("cloudflared.log")).await.unwrap();
        let (_idle_writer, stdout) = tokio::io::duplex(1024);
        let (mut writer, stderr) = tokio::io::duplex(1024);
        writer.write_all(b"INF Registered tunnel connection connIndex=0\n").await.unwrap();
        drop(writer);
        let (tx, rx) = oneshot::channel();
        let task = tokio::spawn(stream_cloudflare_output(stdout, Some(stderr), log, false,
            "https://mcp.example.com".into(), "".into(), tx));
        let result = time::timeout(Duration::from_secs(1), rx).await.unwrap().unwrap();
        assert_eq!(result.unwrap(), "https://mcp.example.com");
        task.abort();
        let _ = task.await;
    }

}
