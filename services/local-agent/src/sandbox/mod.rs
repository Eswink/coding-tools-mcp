//! Explicit, host-owned Linux isolation. This is not an authorization source.
//!
//! Callers must complete LocalAdmission and ExecPolicy first. Existing low-level
//! specs without a sandbox retain their legacy behavior. Once attached, failure
//! to establish isolation never retries execution without it.
use std::{error::Error, fmt, fs::File, path::PathBuf, sync::Arc};

#[cfg(target_arch = "x86_64")]
mod filter;
#[cfg(target_arch = "x86_64")]
mod linux;
#[cfg(target_arch = "x86_64")]
pub(crate) use linux::PreparedSandbox;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SandboxErrorKind {
    Unsupported,
    InvalidRoot,
    InvalidWorkingDirectory,
    InvalidExecutable,
    Unavailable,
    PrivilegedHost,
}

#[derive(Clone, Debug)]
pub struct SandboxError {
    pub kind: SandboxErrorKind,
}

impl fmt::Display for SandboxError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self.kind {
            SandboxErrorKind::Unsupported => "sandbox architecture unsupported",
            SandboxErrorKind::InvalidRoot => "invalid sandbox workspace",
            SandboxErrorKind::InvalidWorkingDirectory => "sandbox working directory rejected",
            SandboxErrorKind::InvalidExecutable => "sandbox executable unavailable",
            SandboxErrorKind::Unavailable => "required sandbox isolation unavailable",
            SandboxErrorKind::PrivilegedHost => "privileged sandbox host rejected",
        })
    }
}

impl Error for SandboxError {}

struct Root {
    path: PathBuf,
    file: File,
}

/// A pinned workspace chosen by a trusted local host, never by deserialization.
///
/// Linux x86_64 requires Landlock ABI3+, openat2, close_range and seccomp.
/// Network access is not configurable: every sandbox denies it. System runtime
/// files and the selected executable may be read/executed, but not modified.
#[derive(Clone)]
pub struct LinuxSandbox {
    root: Arc<Root>,
}

impl LinuxSandbox {
    pub fn new(workspace_root: impl AsRef<std::path::Path>) -> Result<Self, SandboxError> {
        #[cfg(target_arch = "x86_64")]
        {
            Ok(Self {
                root: Arc::new(linux::pin_root(workspace_root.as_ref())?),
            })
        }
        #[cfg(not(target_arch = "x86_64"))]
        {
            let _ = workspace_root;
            Err(SandboxError {
                kind: SandboxErrorKind::Unsupported,
            })
        }
    }

    /// Attach isolation to a trusted host's existing process supervisor.
    ///
    /// The host must independently authorize this exact command and retain its
    /// execution permit through cleanup. This method creates no local authority.
    /// Set the absolute program and cwd first; do not replace them afterwards.
    /// Inherited environment is cleared; any later values must be host-owned.
    /// On any error the caller must not spawn or retry without isolation.
    pub fn attach_to_command(
        &self,
        command: &mut tokio::process::Command,
    ) -> Result<(), SandboxError> {
        let program = PathBuf::from(command.as_std().get_program());
        let cwd = command
            .as_std()
            .get_current_dir()
            .ok_or(SandboxError {
                kind: SandboxErrorKind::InvalidWorkingDirectory,
            })?
            .to_path_buf();
        let prepared = self.prepare(&program, &cwd)?;
        command.env_clear();
        // All paths, descriptors and filters are prepared in the parent.
        // The child callback only applies already-owned, allocation-free state.
        unsafe {
            command.pre_exec(move || prepared.apply());
        }
        Ok(())
    }

    pub(crate) fn prepare(
        &self,
        executable: &std::path::Path,
        cwd: &std::path::Path,
    ) -> Result<PreparedSandbox, SandboxError> {
        #[cfg(target_arch = "x86_64")]
        {
            linux::prepare(&self.root, executable, cwd)
        }
        #[cfg(not(target_arch = "x86_64"))]
        {
            let _ = (executable, cwd, &self.root);
            Err(SandboxError {
                kind: SandboxErrorKind::Unsupported,
            })
        }
    }
}

impl fmt::Debug for LinuxSandbox {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("LinuxSandbox(<pinned-local-workspace>, network=denied)")
    }
}

#[cfg(not(target_arch = "x86_64"))]
pub(crate) struct PreparedSandbox;
#[cfg(not(target_arch = "x86_64"))]
impl PreparedSandbox {
    pub(crate) fn apply(&self) -> std::io::Result<()> {
        Err(std::io::ErrorKind::Unsupported.into())
    }
}

#[cfg(all(test, target_arch = "x86_64"))]
mod tests;
