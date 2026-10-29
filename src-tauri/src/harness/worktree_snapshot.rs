//! A validated read target, not an execution-admission or quiescence lease.
use super::super::worktree_boundary::{failure, identity, FileIdentity};
use super::{boundary_error, canonical_directory, WorktreeManager, WorktreeResult};
use std::path::PathBuf;

#[derive(Clone)]
pub(crate) struct SnapshotTarget {
    pub(crate) root: PathBuf,
    pub(crate) head: String,
    pub(crate) workspace_id: String,
    pub(crate) worktree_id: String,
    manager: WorktreeManager,
    identity: FileIdentity,
}
impl WorktreeManager {
    pub(crate) fn snapshot_target(&self, id: &str) -> WorktreeResult<SnapshotTarget> {
        if !super::valid_id(id) {
            return Err(failure("INVALID_ID"));
        }
        let entry = self
            .list()?
            .into_iter()
            .find(|entry| entry.id == id)
            .ok_or_else(|| failure("NOT_FOUND"))?;
        let root = self.managed_root.join(id);
        if canonical_directory(&root, "Managed worktree is unavailable.")? != root {
            return Err(boundary_error());
        }
        Ok(SnapshotTarget {
            identity: identity(&root)?,
            root,
            head: entry.head,
            workspace_id: self.workspace_id.clone(),
            worktree_id: id.to_owned(),
            manager: self.clone(),
        })
    }
}
impl SnapshotTarget {
    /// Identity retained natively when this target was built; never IPC-supplied.
    pub(crate) fn root_identity_key(&self) -> String {
        self.identity.snapshot_key()
    }
    /// Revalidate before/after capture. This does not prevent concurrent writers.
    pub(crate) fn verify(&self) -> WorktreeResult<()> {
        let current = self.manager.snapshot_target(&self.worktree_id)?;
        if current.root != self.root
            || current.head != self.head
            || current.identity != self.identity
            || current.workspace_id != self.workspace_id
        {
            return Err(boundary_error());
        }
        Ok(())
    }
}
