//! Explicit native-owner snapshot operations. Never called by ordinary start_task.
mod filesystem;
mod model;
mod restore;
use filesystem::{Dir, Tree};
use model::*;
pub(crate) use model::{Manifest, RestorePlan, RestoreReport, SnapshotError, TargetAuthority};
use std::{
    collections::BTreeMap,
    path::{Path, PathBuf},
};

pub(crate) struct SnapshotStore {
    directory: Dir,
    path: PathBuf,
}
impl SnapshotStore {
    pub fn open(path: &Path) -> Result<Self> {
        let directory = Dir::open(path)?;
        directory.private()?;
        Ok(Self {
            directory,
            path: path.to_owned(),
        })
    }
    /// Native host supplies an existing private state parent, never an IPC path.
    pub fn create(parent: &Path, name: &str) -> Result<Self> {
        safe_component(name)?;
        let base = Dir::open(parent)?;
        base.private()?;
        let dir = if base.names()?.iter().any(|v| v == name) {
            base.child(name)?
        } else {
            base.mkdir(name)?
        };
        dir.private()?;
        Ok(Self {
            directory: dir,
            path: parent.join(name),
        })
    }
    fn target(&self, target: &impl TargetAuthority) -> Result<Dir> {
        target.verify()?;
        if !valid_id(target.workspace_id())
            || !valid_id(target.worktree_id())
            || target.head().is_empty()
            || target.head().len() > 64
            || !target.head().bytes().all(|b| b.is_ascii_hexdigit())
            || self.path.starts_with(target.root())
            || target.root().starts_with(&self.path)
        {
            return Err(SnapshotError::Boundary);
        }
        let current = Dir::open(&self.path)?;
        if current.identity()? != self.directory.identity()? {
            return Err(SnapshotError::Changed);
        }
        // Bind the exact opened handle to the retained identity, then recheck the pathname
        // authority and the handle again so a swap (or ABA swap) around open is refused.
        let root = Dir::open(target.root())?;
        let trusted = target.trusted_root_identity();
        if root.identity()? != trusted {
            return Err(SnapshotError::Changed);
        }
        target.verify()?;
        if root.identity()? != trusted || Dir::open(target.root())?.identity()? != trusted {
            return Err(SnapshotError::Changed);
        }
        Ok(root)
    }
    fn ready(&self) -> Result<()> {
        for name in self.directory.names()? {
            if name.starts_with("transaction-") {
                let tx = self.directory.child(&name)?;
                if !Self::transaction_complete(&tx) {
                    return Err(SnapshotError::RecoveryRequired);
                }
            }
        }
        if self.directory.names()?.len() > MAX_OBJECTS * 3 {
            return Err(SnapshotError::Capacity);
        }
        Ok(())
    }
    fn transaction_complete(tx: &Dir) -> bool {
        let verify = (|| -> Result<()> {
            let (marker, _) = tx.read("complete", 64)?;
            let (bytes, _) = tx.read("plan.json", MAX_METADATA)?;
            let plan: RestorePlan =
                serde_json::from_slice(&bytes).map_err(|_| SnapshotError::Corrupt)?;
            if marker != plan.snapshot_digest.as_bytes()
                || !valid_hash(&plan.snapshot_digest)
                || plan.approval_digest != plan_digest(&plan)?
            {
                return Err(SnapshotError::Corrupt);
            }
            Ok(())
        })();
        verify.is_ok()
    }
    pub fn recovery_required(&self) -> Result<bool> {
        for name in self.directory.names()? {
            if name.starts_with("transaction-")
                && !Self::transaction_complete(&self.directory.child(&name)?)
            {
                return Ok(true);
            }
        }
        Ok(false)
    }
    pub fn capture(&self, target: &impl TargetAuthority) -> Result<Manifest> {
        let _lock = self.directory.lock()?;
        self.ready()?;
        if self
            .directory
            .names()?
            .iter()
            .filter(|s| valid_id(s))
            .count()
            >= MAX_OBJECTS
        {
            return Err(SnapshotError::Capacity);
        }
        let root = self.target(target)?;
        let identity = root.identity()?;
        let tree = root.scan(true)?;
        let id = uuid::Uuid::new_v4().simple().to_string();
        let dir = self.directory.mkdir(&id)?;
        let blobs = dir.mkdir("blobs")?;
        for entry in &tree.entries {
            if !entry.directory && !blobs.names()?.iter().any(|name| name == &entry.hash) {
                blobs.write_new(&entry.hash, &tree.data[&entry.path], 0o600)?;
            }
        }
        let manifest = Manifest {
            version: 1,
            id,
            workspace_id: target.workspace_id().into(),
            worktree_id: target.worktree_id().into(),
            head: target.head().into(),
            root_identity: identity.clone(),
            bytes: tree.entries.iter().map(|e| e.size).sum(),
            digest: entries_digest(&tree.entries)?,
            entries: tree.entries,
        };
        if self.target(target)?.identity()? != identity
            || root.scan(true)?.entries != manifest.entries
        {
            return Err(SnapshotError::Changed);
        }
        let json = bounded_json(&manifest)?;
        dir.write_new("manifest.json", &json, 0o600)?;
        dir.write_new("complete", hash(&json).as_bytes(), 0o600)?;
        Ok(manifest)
    }
    fn load(&self, target: &impl TargetAuthority, id: &str) -> Result<(Manifest, Tree)> {
        if !valid_id(id) {
            return Err(SnapshotError::Boundary);
        }
        let root = self.target(target)?;
        let dir = self.directory.child(id)?;
        let (bytes, _) = dir.read("manifest.json", MAX_METADATA)?;
        let (marker, _) = dir.read("complete", 64)?;
        if marker != hash(&bytes).as_bytes() {
            return Err(SnapshotError::Corrupt);
        }
        let manifest: Manifest =
            serde_json::from_slice(&bytes).map_err(|_| SnapshotError::Corrupt)?;
        if manifest.version != 1
            || manifest.id != id
            || manifest.workspace_id != target.workspace_id()
            || manifest.worktree_id != target.worktree_id()
            || manifest.head != target.head()
            || manifest.root_identity != root.identity()?
        {
            return Err(SnapshotError::Changed);
        }
        validate_entries(&manifest.entries)?;
        if manifest.digest != entries_digest(&manifest.entries)?
            || manifest.bytes != manifest.entries.iter().map(|e| e.size).sum::<u64>()
        {
            return Err(SnapshotError::Corrupt);
        }
        let blobs = dir.child("blobs")?;
        let mut data = BTreeMap::new();
        for entry in &manifest.entries {
            if !entry.directory {
                let (bytes, _) = blobs.read(&entry.hash, MAX_FILE)?;
                if bytes.len() as u64 != entry.size || hash(&bytes) != entry.hash {
                    return Err(SnapshotError::Corrupt);
                };
                data.insert(entry.path.clone(), bytes);
            }
        }
        let tree = Tree {
            entries: manifest.entries.clone(),
            data,
        };
        Ok((manifest, tree))
    }
    pub fn list(&self, target: &impl TargetAuthority) -> Result<Vec<Manifest>> {
        let _lock = self.directory.lock()?;
        self.target(target)?;
        let mut out = Vec::new();
        for name in self.directory.names()? {
            if valid_id(&name) {
                let dir = self.directory.child(&name)?;
                // Partial captures are visible only as unusable storage, never snapshots.
                if !dir.names()?.iter().any(|n| n == "complete") {
                    continue;
                }
                out.push(self.load(target, &name)?.0);
            }
        }
        Ok(out)
    }
    pub fn plan_restore(
        &self,
        target: &impl TargetAuthority,
        snapshot_id: &str,
    ) -> Result<RestorePlan> {
        let _lock = self.directory.lock()?;
        self.ready()?;
        let root = self.target(target)?;
        let (manifest, _) = self.load(target, snapshot_id)?;
        let tree = root.scan(true)?;
        let before: BTreeMap<_, _> = tree.entries.iter().map(|e| (&e.path, e)).collect();
        let after: BTreeMap<_, _> = manifest.entries.iter().map(|e| (&e.path, e)).collect();
        let names: std::collections::BTreeSet<_> =
            before.keys().chain(after.keys()).copied().collect();
        let changes: Vec<Change> = names
            .into_iter()
            .filter_map(|name| {
                let a = before.get(name);
                let b = after.get(name);
                if a == b {
                    return None;
                }
                Some(Change {
                    path: name.clone(),
                    action: match (a, b) {
                        (None, _) => "add",
                        (_, None) => "delete",
                        _ => "replace",
                    }
                    .into(),
                })
            })
            .collect();
        // Linux cannot move a read-only directory between parents. Refuse before mutation.
        for entry in &tree.entries {
            if entry.directory
                && !entry.path.contains('/')
                && entry.mode & 0o200 == 0
                && changes.iter().any(|c| {
                    c.path == entry.path || c.path.starts_with(&format!("{}/", entry.path))
                })
            {
                return Err(SnapshotError::Unsupported);
            }
        }
        if root.scan(true)?.entries != tree.entries {
            return Err(SnapshotError::Changed);
        }
        let mut plan = RestorePlan {
            id: uuid::Uuid::new_v4().simple().to_string(),
            snapshot_id: manifest.id,
            workspace_id: manifest.workspace_id,
            worktree_id: manifest.worktree_id,
            head: manifest.head,
            root_identity: root.identity()?,
            current_digest: entries_digest(&tree.entries)?,
            snapshot_digest: manifest.digest,
            expires_at: now().checked_add(120).ok_or(SnapshotError::Expired)?,
            changes,
            before: tree.entries,
            approval_digest: String::new(),
        };
        plan.approval_digest = plan_digest(&plan)?;
        self.directory.write_new(
            &format!("plan-{}.json", plan.id),
            &bounded_json(&plan)?,
            0o600,
        )?;
        Ok(plan)
    }
    fn validate_plan(&self, target: &impl TargetAuthority, plan: &RestorePlan) -> Result<()> {
        if !valid_id(&plan.id) || !valid_id(&plan.snapshot_id) || plan.expires_at < now() {
            return Err(SnapshotError::Expired);
        }
        if plan.workspace_id != target.workspace_id()
            || plan.worktree_id != target.worktree_id()
            || plan.head != target.head()
            || plan.approval_digest != plan_digest(plan)?
        {
            return Err(SnapshotError::Approval);
        }
        let (saved, _) = self
            .directory
            .read(&format!("plan-{}.json", plan.id), MAX_METADATA)?;
        if serde_json::from_slice::<RestorePlan>(&saved).map_err(|_| SnapshotError::Corrupt)?
            != *plan
        {
            return Err(SnapshotError::Approval);
        }
        validate_entries(&plan.before)?;
        if entries_digest(&plan.before)? != plan.current_digest {
            return Err(SnapshotError::Corrupt);
        }
        let root = self.target(target)?;
        if root.identity()? != plan.root_identity {
            return Err(SnapshotError::Changed);
        }
        Ok(())
    }
}
#[cfg(test)]
mod tests;

#[cfg(all(test, target_os = "linux"))]
#[path = "metadata_tests.rs"]
mod metadata_tests;
