use std::path::{Path, PathBuf};

use serde::Serialize;

use crate::error::AppResult;

/// Cross-platform OS primitives used by the desktop runtime.
///
/// Windows uses `windows-rs`. macOS and Linux live in dedicated modules.
#[allow(dead_code)]
pub trait Platform: Send + Sync {
    fn os_name(&self) -> &'static str;

    fn app_config_dir(&self) -> AppResult<PathBuf>;

    fn find_pid_listening_on_port(&self, port: u16) -> AppResult<Option<u32>>;

    /// Best-effort reclaim of a TCP listener on the given port. Windows uses
    /// `SetTcpEntry`; other platforms return `Ok(false)`.
    fn reclaim_listening_port(&self, port: u16) -> AppResult<bool> {
        let _ = port;
        Ok(false)
    }

    fn process_image_path(&self, pid: u32) -> AppResult<Option<String>>;

    fn is_process_alive(&self, pid: u32) -> bool;

    fn terminate_process_tree(&self, pid: u32) -> AppResult<()>;

    /// 清理由应用管理的同一路径进程；默认平台不做处理。
    fn terminate_processes_by_image_path(&self, _image_path: &Path) -> AppResult<usize> {
        Ok(0)
    }

    fn resolve_executable(&self, name: &str) -> Option<PathBuf>;

    fn cloudflared_candidates(&self) -> Vec<PathBuf>;

    fn frpc_candidates(&self) -> Vec<PathBuf>;
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct PlatformContext {
    pub os: &'static str,
    pub family: &'static str,
    pub arch: &'static str,
    pub distribution: Option<String>,
    pub path_style: &'static str,
    pub path_separator: &'static str,
    pub case_sensitive_paths: bool,
    pub executable_suffix: &'static str,
    pub default_shell: &'static str,
    pub shell_modes: Vec<&'static str>,
    pub command_execution: &'static str,
    pub command_guidance: &'static str,
}

#[cfg(target_os = "linux")]
mod linux;
#[cfg(target_os = "macos")]
mod macos;
#[cfg(target_os = "windows")]
pub(crate) mod windows;

mod open;
mod paths;

pub use open::{is_allowed_url, open_path_in_file_manager, open_url};

#[cfg(target_os = "linux")]
pub use linux::LinuxPlatform;
#[cfg(target_os = "linux")]
pub(crate) use linux::listen_socket_present as linux_listen_socket_present;
#[cfg(target_os = "macos")]
pub use macos::MacPlatform;
#[cfg(target_os = "windows")]
pub use windows::WindowsPlatform;

static PLATFORM: std::sync::OnceLock<Box<dyn Platform>> = std::sync::OnceLock::new();
static PLATFORM_CONTEXT: std::sync::OnceLock<PlatformContext> = std::sync::OnceLock::new();

pub fn platform() -> &'static dyn Platform {
    PLATFORM.get_or_init(create_platform).as_ref()
}

pub fn context() -> &'static PlatformContext {
    PLATFORM_CONTEXT.get_or_init(detect_context)
}

fn detect_context() -> PlatformContext {
    #[cfg(target_os = "windows")]
    {
        return PlatformContext {
            os: "windows",
            family: "windows",
            arch: std::env::consts::ARCH,
            distribution: None,
            path_style: "windows",
            path_separator: "\\",
            case_sensitive_paths: false,
            executable_suffix: ".exe",
            default_shell: "powershell",
            shell_modes: vec!["direct", "cmd", "powershell"],
            command_execution: "direct-argv",
            command_guidance: "Use Windows paths. exec_command executes argv directly; invoke cmd or PowerShell explicitly when shell syntax is required.",
        };
    }
    #[cfg(target_os = "linux")]
    {
        let bash = platform().resolve_executable("bash").is_some();
        return PlatformContext {
            os: "linux",
            family: "unix",
            arch: std::env::consts::ARCH,
            distribution: linux_distribution(),
            path_style: "posix",
            path_separator: "/",
            case_sensitive_paths: true,
            executable_suffix: "",
            default_shell: if bash { "bash" } else { "sh" },
            shell_modes: if bash { vec!["direct", "sh", "bash"] } else { vec!["direct", "sh"] },
            command_execution: "direct-argv",
            command_guidance: "Use POSIX paths and Linux commands. exec_command executes argv directly; invoke sh or bash explicitly for pipes, redirects, globs, variables, or other shell syntax. Do not emit cmd.exe, PowerShell, drive-letter, or UNC commands.",
        };
    }
    #[cfg(target_os = "macos")]
    {
        return PlatformContext {
            os: "macos",
            family: "unix",
            arch: std::env::consts::ARCH,
            distribution: None,
            path_style: "posix",
            path_separator: "/",
            case_sensitive_paths: false,
            executable_suffix: "",
            default_shell: "sh",
            shell_modes: vec!["direct", "sh"],
            command_execution: "direct-argv",
            command_guidance: "Use POSIX paths. exec_command executes argv directly; invoke sh explicitly when shell syntax is required.",
        };
    }
    #[cfg(not(any(target_os = "windows", target_os = "linux", target_os = "macos")))]
    PlatformContext {
        os: "unsupported",
        family: std::env::consts::FAMILY,
        arch: std::env::consts::ARCH,
        distribution: None,
        path_style: "unknown",
        path_separator: std::path::MAIN_SEPARATOR_STR,
        case_sensitive_paths: true,
        executable_suffix: std::env::consts::EXE_SUFFIX,
        default_shell: "unknown",
        shell_modes: vec!["direct"],
        command_execution: "direct-argv",
        command_guidance: "Unsupported host platform; do not assume Windows or POSIX shell semantics.",
    }
}

#[cfg(target_os = "linux")]
fn linux_distribution() -> Option<String> {
    let raw = std::fs::read_to_string("/etc/os-release").ok()?;
    let mut id = None;
    let mut version = None;
    for line in raw.lines() {
        let Some((key, value)) = line.split_once('=') else { continue; };
        let value = value.trim_matches('"');
        match key {
            "ID" if !value.is_empty() => id = Some(value.to_string()),
            "VERSION_ID" if !value.is_empty() => version = Some(value.to_string()),
            _ => {}
        }
    }
    match (id, version) {
        (Some(id), Some(version)) => Some(format!("{id} {version}")),
        (Some(id), None) => Some(id),
        _ => None,
    }
}

fn create_platform() -> Box<dyn Platform> {
    #[cfg(target_os = "windows")]
    {
        Box::new(WindowsPlatform)
    }
    #[cfg(target_os = "macos")]
    {
        Box::new(MacPlatform)
    }
    #[cfg(target_os = "linux")]
    {
        Box::new(LinuxPlatform)
    }
    #[cfg(not(any(target_os = "windows", target_os = "macos", target_os = "linux")))]
    {
        struct Unsupported;
        impl Platform for Unsupported {
            fn os_name(&self) -> &'static str {
                "unsupported"
            }
            fn app_config_dir(&self) -> AppResult<PathBuf> {
                Err(crate::error::AppError::Message(
                    "unsupported operating system".into(),
                ))
            }
            fn find_pid_listening_on_port(&self, _port: u16) -> AppResult<Option<u32>> {
                Ok(None)
            }
            fn process_image_path(&self, _pid: u32) -> AppResult<Option<String>> {
                Ok(None)
            }
            fn is_process_alive(&self, _pid: u32) -> bool {
                false
            }
            fn terminate_process_tree(&self, _pid: u32) -> AppResult<()> {
                Ok(())
            }
            fn resolve_executable(&self, name: &str) -> Option<PathBuf> {
                paths::resolve_from_path(name)
            }
            fn cloudflared_candidates(&self) -> Vec<PathBuf> {
                paths::resolve_from_path("cloudflared")
                    .into_iter()
                    .collect()
            }
            fn frpc_candidates(&self) -> Vec<PathBuf> {
                paths::resolve_from_path("frpc").into_iter().collect()
            }
        }
        Box::new(Unsupported)
    }
}

#[cfg(test)]
mod context_tests {
    use super::*;

    #[test]
    fn platform_context_matches_compile_target() {
        let host = context();
        assert_eq!(host.arch, std::env::consts::ARCH);
        assert_eq!(host.command_execution, "direct-argv");
        #[cfg(target_os = "windows")]
        {
            assert_eq!(host.os, "windows");
            assert_eq!(host.path_style, "windows");
            assert!(host.shell_modes.contains(&"powershell"));
        }
        #[cfg(target_os = "linux")]
        {
            assert_eq!(host.os, "linux");
            assert_eq!(host.path_style, "posix");
            assert!(host.shell_modes.contains(&"sh"));
            assert!(host.command_guidance.contains("Do not emit cmd.exe"));
        }
    }
}
