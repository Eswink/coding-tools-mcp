//! Deterministic patch transaction commit and rollback.
use std::{
    collections::{BTreeMap, BTreeSet},
    fs, io,
    path::{Path, PathBuf},
};

use uuid::Uuid;

use crate::tools::workspace::{Workspace, WorkspaceError};

#[derive(Clone)]
struct BackupEntry {
    bytes: Option<Vec<u8>>,
    permissions: Option<fs::Permissions>,
}

#[derive(Default)]
struct Journal {
    backups: BTreeMap<PathBuf, BackupEntry>,
    temporary_files: BTreeMap<PathBuf, PathBuf>,
    created_dirs: BTreeSet<PathBuf>,
    dirty_paths: BTreeSet<PathBuf>,
}

struct PreparedTarget {
    path: PathBuf,
    temporary: Option<PathBuf>,
}

pub(super) fn commit_staged(
    workspace: &Workspace,
    staged: &BTreeMap<String, Option<String>>,
) -> Result<BTreeMap<PathBuf, Option<Vec<u8>>>, WorkspaceError> {
    let staged = staged
        .iter()
        .map(|(path, content)| {
            (
                path.clone(),
                content.as_ref().map(|value| value.as_bytes().to_vec()),
            )
        })
        .collect::<BTreeMap<_, _>>();
    commit_staged_bytes(workspace, &staged)
}

fn commit_staged_bytes(
    workspace: &Workspace,
    staged: &BTreeMap<String, Option<Vec<u8>>>,
) -> Result<BTreeMap<PathBuf, Option<Vec<u8>>>, WorkspaceError> {
    commit_staged_bytes_with_hook(workspace, staged, |_, _, _| Ok(()))
}

fn commit_staged_bytes_with_hook<F>(
    workspace: &Workspace,
    staged: &BTreeMap<String, Option<Vec<u8>>>,
    mut before_commit: F,
) -> Result<BTreeMap<PathBuf, Option<Vec<u8>>>, WorkspaceError>
where
    F: FnMut(usize, &Path, Option<&Path>) -> io::Result<()>,
{
    let mut journal = Journal::default();
    let prepared = match prepare(workspace, staged, &mut journal) {
        Ok(prepared) => prepared,
        Err(error) => {
            journal.cleanup_uncommitted();
            return Err(error);
        }
    };

    for (index, target) in prepared.iter().enumerate() {
        journal.dirty_paths.insert(target.path.clone());
        let result = before_commit(index, &target.path, target.temporary.as_deref())
            .and_then(|_| commit_target(&target.path, target.temporary.as_deref()));
        if let Err(error) = result {
            if let Err(rollback_error) = journal.rollback() {
                return Err(patch_failed(format!(
                    "Failed to write file: {error}; rollback failed: {rollback_error}"
                )));
            }
            return Err(patch_failed(format!("Failed to write file: {error}")));
        }
    }

    journal.cleanup_temporary_files();
    Ok(journal
        .backups
        .into_iter()
        .map(|(path, entry)| (path, entry.bytes))
        .collect())
}

fn prepare(
    workspace: &Workspace,
    staged: &BTreeMap<String, Option<Vec<u8>>>,
    journal: &mut Journal,
) -> Result<Vec<PreparedTarget>, WorkspaceError> {
    let mut prepared = Vec::with_capacity(staged.len());
    for (relative, content) in staged {
        workspace.reject_protected_write_path(relative)?;
        workspace.reject_write_symlink(relative)?;
        let resolved = if content.is_none() {
            workspace.resolve_existing(relative)?
        } else {
            workspace.resolve_for_write(relative)?
        };
        let path = resolved.path;
        let metadata = if path.exists() {
            let metadata = fs::metadata(&path)
                .map_err(|error| patch_failed(format!("Failed to inspect file: {error}")))?;
            if !metadata.is_file() {
                return Err(patch_failed("Patch target must be a regular file"));
            }
            Some(metadata)
        } else {
            None
        };
        let backup = if let Some(metadata) = metadata.as_ref() {
            BackupEntry {
                bytes: Some(
                    fs::read(&path)
                        .map_err(|error| patch_failed(format!("Failed to read file: {error}")))?,
                ),
                permissions: Some(metadata.permissions()),
            }
        } else {
            BackupEntry {
                bytes: None,
                permissions: None,
            }
        };
        journal.backups.insert(path.clone(), backup);

        let temporary = if let Some(bytes) = content {
            let parent = path
                .parent()
                .ok_or_else(|| patch_failed("Patch target has no parent directory"))?;
            create_missing_parents(workspace.root(), parent, &mut journal.created_dirs)?;
            let temporary = path.with_file_name(format!(
                ".{}.harness-stage-{}",
                path.file_name()
                    .and_then(|value| value.to_str())
                    .unwrap_or("file"),
                Uuid::new_v4().simple()
            ));
            journal
                .temporary_files
                .insert(path.clone(), temporary.clone());
            fs::write(&temporary, bytes)
                .map_err(|error| patch_failed(format!("Failed to stage file: {error}")))?;
            if let Some(permissions) = journal
                .backups
                .get(&path)
                .and_then(|entry| entry.permissions.clone())
            {
                fs::set_permissions(&temporary, permissions).map_err(|error| {
                    patch_failed(format!("Failed to preserve file permissions: {error}"))
                })?;
            }
            Some(temporary)
        } else {
            None
        };
        prepared.push(PreparedTarget { path, temporary });
    }
    Ok(prepared)
}

fn create_missing_parents(
    workspace_root: &Path,
    parent: &Path,
    created: &mut BTreeSet<PathBuf>,
) -> Result<(), WorkspaceError> {
    let mut missing = Vec::new();
    let mut cursor = parent;
    while cursor != workspace_root && !cursor.exists() {
        missing.push(cursor.to_path_buf());
        cursor = cursor
            .parent()
            .ok_or_else(|| patch_failed("Patch parent escaped the workspace"))?;
    }
    for directory in missing.into_iter().rev() {
        match fs::create_dir(&directory) {
            Ok(()) => {
                created.insert(directory);
            }
            Err(error) if error.kind() == io::ErrorKind::AlreadyExists => {}
            Err(error) => {
                return Err(patch_failed(format!(
                    "Failed to create patch directory: {error}"
                )))
            }
        }
    }
    Ok(())
}

fn commit_target(path: &Path, temporary: Option<&Path>) -> io::Result<()> {
    if let Some(temporary) = temporary {
        return replace_file(temporary, path);
    }
    if path.exists() && path.is_file() {
        fs::remove_file(path)?;
    }
    Ok(())
}

fn remove_for_restore(path: &Path) -> io::Result<()> {
    #[cfg(windows)]
    {
        if let Ok(metadata) = fs::metadata(path) {
            let mut permissions = metadata.permissions();
            if permissions.readonly() {
                permissions.set_readonly(false);
                fs::set_permissions(path, permissions)?;
            }
        }
    }
    fs::remove_file(path)
}

fn replace_file(temporary: &Path, path: &Path) -> io::Result<()> {
    #[cfg(windows)]
    {
        if path.exists() {
            fs::remove_file(path)?;
        }
    }
    fs::rename(temporary, path)
}

impl Journal {
    fn cleanup_uncommitted(&mut self) {
        self.cleanup_temporary_files();
        self.cleanup_created_dirs();
    }

    fn rollback(&mut self) -> io::Result<()> {
        self.cleanup_temporary_files();
        for path in self.dirty_paths.iter().rev() {
            let Some(backup) = self.backups.get(path) else {
                continue;
            };
            if path.exists() {
                remove_for_restore(path)?;
            }
            if let Some(bytes) = backup.bytes.as_ref() {
                if let Some(parent) = path.parent() {
                    fs::create_dir_all(parent)?;
                }
                fs::write(path, bytes)?;
                if let Some(permissions) = backup.permissions.clone() {
                    fs::set_permissions(path, permissions)?;
                }
            }
        }
        self.cleanup_created_dirs();
        Ok(())
    }

    fn cleanup_temporary_files(&mut self) {
        for temporary in self.temporary_files.values() {
            let _ = fs::remove_file(temporary);
        }
        self.temporary_files.clear();
    }

    fn cleanup_created_dirs(&mut self) {
        let mut directories = self.created_dirs.iter().cloned().collect::<Vec<_>>();
        directories.sort_by_key(|path| std::cmp::Reverse(path.components().count()));
        for directory in directories {
            let _ = fs::remove_dir(directory);
        }
        self.created_dirs.clear();
    }
}

fn patch_failed(message: impl Into<String>) -> WorkspaceError {
    WorkspaceError::Tool {
        code: "PATCH_FAILED",
        message: message.into(),
        category: "validation",
        retryable: false,
    }
}

#[cfg(test)]
#[path = "patch_transaction_tests.rs"]
mod tests;
