use std::ffi::OsString;
use std::fmt;
use std::fs;
use std::path::{Path, PathBuf};

use serde::Serialize;
use uuid::Uuid;

use super::worktree_git::run_git;

const MAX_MANAGED_WORKTREES: usize = 8;
const OPAQUE_ID_LEN: usize = 32;

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct ManagedWorktree {
    pub id: String,
    pub display_path: String,
    pub head: String,
    pub detached: bool,
}

#[derive(Clone, Eq, PartialEq)]
pub struct WorktreeError {
    code: &'static str,
    message: &'static str,
}

impl WorktreeError {
    pub(super) fn new(code: &'static str, message: &'static str) -> Self {
        Self { code, message }
    }
    pub fn code(&self) -> &'static str {
        self.code
    }
}

impl fmt::Debug for WorktreeError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("WorktreeError")
            .field("code", &self.code)
            .field("message", &self.message)
            .finish()
    }
}

impl fmt::Display for WorktreeError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.message)
    }
}

impl std::error::Error for WorktreeError {}

pub type WorktreeResult<T> = Result<T, WorktreeError>;

#[derive(Clone)]
pub struct WorktreeManager {
    repository_root: PathBuf,
    managed_root: PathBuf,
    workspace_id: String,
}

impl fmt::Debug for WorktreeManager {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("WorktreeManager")
            .field("workspace_id", &self.workspace_id)
            .field("max_managed", &MAX_MANAGED_WORKTREES)
            .finish()
    }
}

impl WorktreeManager {
    pub fn new(
        workspace_root: &Path,
        harness_root: &Path,
        workspace_id: &str,
    ) -> WorktreeResult<Self> {
        if !valid_id(workspace_id) {
            return Err(error("INVALID_ID", "Invalid workspace identifier."));
        }
        let workspace_root = canonical_directory(workspace_root, "Workspace is unavailable.")?;
        let harness_root = canonical_directory(harness_root, "Harness state root is unavailable.")?;
        if workspace_root.starts_with(&harness_root) || harness_root.starts_with(&workspace_root) {
            return Err(boundary_error());
        }
        let repository_root = discover_repository_root(&workspace_root)?;
        if !repository_root.starts_with(&workspace_root) {
            return Err(boundary_error());
        }
        let worktrees_root = harness_root.join("worktrees-v1");
        ensure_owned_directory(&worktrees_root)?;
        let managed_root = worktrees_root.join(workspace_id);
        ensure_owned_directory(&managed_root)?;
        let managed_root = managed_root.canonicalize().map_err(|_| io_failure())?;
        if !managed_root.starts_with(&harness_root) {
            return Err(boundary_error());
        }
        Ok(Self {
            repository_root,
            managed_root,
            workspace_id: workspace_id.to_owned(),
        })
    }
    pub fn create_detached(&self) -> WorktreeResult<ManagedWorktree> {
        if self.list()?.len() >= MAX_MANAGED_WORKTREES {
            return Err(error("CAPACITY", "Managed worktree capacity reached."));
        }
        let (id, target) = (0..16)
            .find_map(|_| {
                let id = Uuid::new_v4().simple().to_string();
                let target = self.managed_root.join(&id);
                (!target.exists() && !target.is_symlink()).then_some((id, target))
            })
            .ok_or_else(|| error("CAPACITY", "Unable to allocate managed worktree."))?;
        let args = vec![
            OsString::from("worktree"),
            OsString::from("add"),
            OsString::from("--detach"),
            target.as_os_str().to_owned(),
            OsString::from("HEAD"),
        ];
        let output = run_git(&self.repository_root, &args)?;
        if !output.success {
            #[cfg(test)]
            {
                let rendered = String::from_utf8_lossy(&output.stderr)
                    .replace(self.repository_root.to_string_lossy().as_ref(), "<repo>")
                    .replace(self.managed_root.to_string_lossy().as_ref(), "<managed>")
                    .replace(target.to_string_lossy().as_ref(), "<target>");
                eprintln!("[worktree-wrapper-diagnostic] {rendered}");
            }
            cleanup_empty_directory(&target);
            return Err(git_failed());
        }
        let item = self
            .list()?
            .into_iter()
            .find(|item| item.id == id)
            .ok_or_else(|| error("GIT_FAILED", "Git did not register the managed worktree."))?;
        Ok(item)
    }
    pub fn list(&self) -> WorktreeResult<Vec<ManagedWorktree>> {
        let registry = self.registry_entries()?;
        let mut managed = Vec::new();
        for entry in registry {
            let raw_path = entry.path;
            let lexical_managed = raw_path.starts_with(&self.managed_root);
            if raw_path.is_symlink() {
                if lexical_managed {
                    return Err(boundary_error());
                }
                continue;
            }
            let canonical = match raw_path.canonicalize() {
                Ok(path) => path,
                Err(_) if lexical_managed => return Err(boundary_error()),
                Err(_) => continue,
            };
            if !canonical.starts_with(&self.managed_root) {
                continue;
            }
            if canonical.parent() != Some(self.managed_root.as_path()) {
                return Err(boundary_error());
            }
            let id = canonical
                .file_name()
                .and_then(|value| value.to_str())
                .ok_or_else(boundary_error)?;
            if !valid_id(id) || !entry.detached {
                return Err(boundary_error());
            }
            let head = entry
                .head
                .as_deref()
                .filter(|head| valid_head(head))
                .ok_or_else(|| error("PARSE_FAILED", "Git worktree metadata is invalid."))?;
            managed.push(ManagedWorktree {
                id: id.to_owned(),
                display_path: format!("managed/{id}"),
                head: head.to_owned(),
                detached: true,
            });
        }
        managed.sort_by(|left, right| left.id.cmp(&right.id));
        if managed.len() > MAX_MANAGED_WORKTREES {
            return Err(error("CAPACITY", "Managed worktree capacity exceeded."));
        }
        Ok(managed)
    }
    pub fn remove_clean(&self, id: &str) -> WorktreeResult<()> {
        if !valid_id(id) {
            return Err(error("INVALID_ID", "Invalid managed worktree identifier."));
        }
        let item = self
            .list()?
            .into_iter()
            .find(|item| item.id == id)
            .ok_or_else(|| error("NOT_FOUND", "Managed worktree was not found."))?;
        let target = self.managed_root.join(&item.id);
        let target = target.canonicalize().map_err(|_| boundary_error())?;
        if target.parent() != Some(self.managed_root.as_path()) || target.is_symlink() {
            return Err(boundary_error());
        }
        let status = run_git(
            &target,
            &[
                OsString::from("status"),
                OsString::from("--porcelain=v1"),
                OsString::from("--untracked-files=all"),
                OsString::from("-z"),
            ],
        )?;
        if !status.success {
            return Err(git_failed());
        }
        if !status.stdout.is_empty() {
            return Err(error("DIRTY", "Managed worktree contains local changes."));
        }
        let output = run_git(
            &self.repository_root,
            &[
                OsString::from("worktree"),
                OsString::from("remove"),
                target.as_os_str().to_owned(),
            ],
        )?;
        if !output.success || target.exists() || self.list()?.iter().any(|value| value.id == id) {
            return Err(git_failed());
        }
        Ok(())
    }
    fn registry_entries(&self) -> WorktreeResult<Vec<RegistryEntry>> {
        let output = run_git(
            &self.repository_root,
            &[
                OsString::from("worktree"),
                OsString::from("list"),
                OsString::from("--porcelain"),
                OsString::from("-z"),
            ],
        )?;
        if !output.success {
            return Err(git_failed());
        }
        parse_registry(&output.stdout)
    }
}

#[derive(Default)]
struct RegistryEntry {
    path: PathBuf,
    head: Option<String>,
    detached: bool,
}

fn discover_repository_root(workspace_root: &Path) -> WorktreeResult<PathBuf> {
    let output = run_git(
        workspace_root,
        &[
            OsString::from("rev-parse"),
            OsString::from("--show-toplevel"),
        ],
    )?;
    if !output.success {
        return Err(error(
            "NOT_REPOSITORY",
            "Workspace is not a Git repository.",
        ));
    }
    let text = std::str::from_utf8(&output.stdout)
        .map_err(|_| error("PARSE_FAILED", "Git repository metadata is invalid."))?
        .trim();
    if text.is_empty() {
        return Err(error(
            "NOT_REPOSITORY",
            "Workspace is not a Git repository.",
        ));
    }
    let root = PathBuf::from(text)
        .canonicalize()
        .map_err(|_| error("NOT_REPOSITORY", "Workspace is not a Git repository."))?;
    if !root.is_dir() {
        return Err(error(
            "NOT_REPOSITORY",
            "Workspace is not a Git repository.",
        ));
    }
    Ok(root)
}

fn parse_registry(bytes: &[u8]) -> WorktreeResult<Vec<RegistryEntry>> {
    let mut entries = Vec::new();
    let mut current: Option<RegistryEntry> = None;
    for field in bytes.split(|byte| *byte == 0) {
        if field.is_empty() {
            if let Some(entry) = current.take() {
                if entry.path.as_os_str().is_empty() {
                    return Err(parse_failed());
                }
                entries.push(entry);
            }
            continue;
        }
        let field = std::str::from_utf8(field).map_err(|_| parse_failed())?;
        if let Some(path) = field.strip_prefix("worktree ") {
            if let Some(entry) = current.take() {
                if entry.path.as_os_str().is_empty() {
                    return Err(parse_failed());
                }
                entries.push(entry);
            }
            current = Some(RegistryEntry {
                path: PathBuf::from(path),
                ..RegistryEntry::default()
            });
            continue;
        }
        let entry = current.as_mut().ok_or_else(parse_failed)?;
        if let Some(head) = field.strip_prefix("HEAD ") {
            entry.head = Some(head.to_owned());
        } else if field == "detached" {
            entry.detached = true;
        } else if field == "bare"
            || field.starts_with("branch ")
            || field.starts_with("locked")
            || field.starts_with("prunable")
        {
            // Valid Git porcelain metadata that is irrelevant to this first increment.
        } else {
            return Err(parse_failed());
        }
    }
    if let Some(entry) = current {
        if entry.path.as_os_str().is_empty() {
            return Err(parse_failed());
        }
        entries.push(entry);
    }
    Ok(entries)
}

fn canonical_directory(path: &Path, message: &'static str) -> WorktreeResult<PathBuf> {
    if path.is_symlink() {
        return Err(boundary_error());
    }
    let path = path
        .canonicalize()
        .map_err(|_| error("BOUNDARY_VIOLATION", message))?;
    if !path.is_dir() {
        return Err(error("BOUNDARY_VIOLATION", message));
    }
    Ok(path)
}

fn ensure_owned_directory(path: &Path) -> WorktreeResult<()> {
    if path.exists() || path.is_symlink() {
        let metadata = fs::symlink_metadata(path).map_err(|_| io_failure())?;
        if metadata.file_type().is_symlink() || !metadata.is_dir() {
            return Err(boundary_error());
        }
    } else {
        fs::create_dir(path).map_err(|_| io_failure())?;
    }
    Ok(())
}

fn cleanup_empty_directory(path: &Path) {
    if path.is_dir()
        && fs::read_dir(path)
            .ok()
            .is_some_and(|mut entries| entries.next().is_none())
    {
        let _ = fs::remove_dir(path);
    }
}

fn valid_id(value: &str) -> bool {
    value.len() == OPAQUE_ID_LEN
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn valid_head(value: &str) -> bool {
    !value.is_empty() && value.len() <= 64 && value.bytes().all(|byte| byte.is_ascii_hexdigit())
}

fn boundary_error() -> WorktreeError {
    error(
        "BOUNDARY_VIOLATION",
        "Managed worktree boundary validation failed.",
    )
}

fn parse_failed() -> WorktreeError {
    error("PARSE_FAILED", "Git worktree metadata is invalid.")
}

fn git_failed() -> WorktreeError {
    error("GIT_FAILED", "Git worktree operation failed.")
}

fn io_failure() -> WorktreeError {
    error("IO_FAILED", "Managed worktree I/O failed.")
}

fn error(code: &'static str, message: &'static str) -> WorktreeError {
    WorktreeError::new(code, message)
}

#[cfg(test)]
#[path = "worktree_tests.rs"]
mod tests;
