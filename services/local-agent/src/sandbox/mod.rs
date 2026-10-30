//! Explicit, host-owned Linux isolation. This is not an authorization source.
//!
//! Callers must complete LocalAdmission and ExecPolicy first. Existing low-level
//! specs without a sandbox retain their legacy behavior. Once attached, failure
//! to establish isolation never retries execution without it.
use std::{error::Error, fmt, fs::File, path::PathBuf, sync::Arc};

mod command;

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

/// SPEC-A1 v5.3 §4.2 (C4-b): the worker child's file-creation mask.
pub(crate) const WORKER_UMASK: u32 = 0o077;

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
    /// Linked-worktree metadata (`[private, common]`), read-only. See `for_worktree`.
    gitdirs: Option<Arc<[Root; 2]>>,
    read_only: bool,
    /// SPEC-A1 v5.3 §4.2 (C4-b): file-creation mask installed in the child.
    /// `for_worktree` (worker exec and worker Git) uses 0o077; `new` keeps the
    /// inherited mask.
    umask: Option<u32>,
}

impl LinuxSandbox {
    pub fn new(workspace_root: impl AsRef<std::path::Path>) -> Result<Self, SandboxError> {
        #[cfg(target_arch = "x86_64")]
        {
            Ok(Self {
                root: Arc::new(linux::pin_root(workspace_root.as_ref())?),
                gitdirs: None,
                read_only: false,
                umask: None,
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

    /// SPEC-A1 v4 §4.2 (C4): a linked Git worktree whose metadata lives outside
    /// the workspace root. The worktree root keeps exactly the rights `new`
    /// grants. The private gitdir (`<common>/worktrees/<id>`) and the common
    /// gitdir are added with read-file/read-dir only: never write, truncate,
    /// create, remove or execute, and `read_only` cannot widen that. Git inside
    /// the sandbox can therefore inspect the worktree (`status`, `diff`, `log`)
    /// but `git commit`, `add` or index refreshes fail closed.
    ///
    /// A1 C4-b (SPEC-A1 v5.3 §4.2): the child also runs with umask 077, so a
    /// file it creates is private to the desktop user (today only inside the
    /// worktree; it takes effect on Git metadata only if workers are ever
    /// allowed to write it).
    ///
    /// The caller (a trusted host) resolves the gitdirs; this constructor only
    /// pins and validates their shape: the private gitdir must be a direct child
    /// of `<common>/worktrees`, and neither gitdir may contain or be contained
    /// by the workspace root.
    pub fn for_worktree(
        workspace_root: impl AsRef<std::path::Path>,
        private_gitdir: impl AsRef<std::path::Path>,
        common_gitdir: impl AsRef<std::path::Path>,
    ) -> Result<Self, SandboxError> {
        #[cfg(target_arch = "x86_64")]
        {
            let (root, gitdirs) = linux::pin_worktree(
                workspace_root.as_ref(),
                private_gitdir.as_ref(),
                common_gitdir.as_ref(),
            )?;
            Ok(Self {
                root: Arc::new(root),
                gitdirs: Some(Arc::new(gitdirs)),
                read_only: false,
                umask: Some(WORKER_UMASK),
            })
        }
        #[cfg(not(target_arch = "x86_64"))]
        {
            let _ = (workspace_root, private_gitdir, common_gitdir);
            Err(SandboxError {
                kind: SandboxErrorKind::Unsupported,
            })
        }
    }

    /// Reduce this policy to read/execute access. There is no inverse operation.
    /// The pinned workspace is unchanged, and network remains denied.
    pub fn read_only(mut self) -> Self {
        self.read_only = true;
        self
    }

    pub(crate) fn prepare(
        &self,
        executable: &std::path::Path,
        cwd: &std::path::Path,
    ) -> Result<PreparedSandbox, SandboxError> {
        #[cfg(target_arch = "x86_64")]
        {
            linux::prepare(
                &self.root,
                self.gitdirs.as_deref(),
                executable,
                cwd,
                self.read_only,
                self.umask,
            )
        }
        #[cfg(not(target_arch = "x86_64"))]
        {
            let _ = (executable, cwd, &self.root, &self.gitdirs);
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
