//! Native-owned, durable quiescence accounting. This never grants tool authority.
//! Every context for one canonical root shares this tracker and stable disk lock.
mod dispatch;
pub(crate) use dispatch::{blocking_context, dispatch};
mod exclusive;
mod identity;
pub(crate) use exclusive::exclusive_context;
mod storage;
use super::ToolContext;
use crate::data::AuthDocument;
use coding_tools_cloud_agent::work::{WorkDrain, WorkGuard, WorkScope};
use identity::RootIdentity;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::HashMap,
    path::{Path, PathBuf},
    sync::{Arc, Mutex, OnceLock, Weak},
};
pub(crate) use storage::error_value;
use storage::{live_conflict, overlaps, persisted_conflict, private_dir, regular};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) struct RootWorkError;
impl std::fmt::Display for RootWorkError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("native_root_unavailable")
    }
}
#[derive(Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
enum Phase {
    Clean,
    Busy,
    Restore,
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Document {
    version: u32,
    binding: String,
    root: PathBuf,
    identity: (u64, u64),
    ancestors: Vec<(u64, u64)>,
    epoch: u64,
    phase: Phase,
    #[serde(default)]
    managed_reads: bool,
}
struct State {
    disk: AuthDocument,
    document: Document,
    drain: WorkDrain,
    poisoned: bool,
    chains: HashMap<uuid::Uuid, usize>,
    exclusive: Option<uuid::Uuid>,
}
pub(crate) struct RootWorkTracker {
    anchor: RootIdentity,
    root: PathBuf,
    store: PathBuf,
    state: Mutex<State>,
}
static REGISTRY: OnceLock<Mutex<HashMap<PathBuf, Weak<RootWorkTracker>>>> = OnceLock::new();
#[derive(Clone)]
pub(crate) struct RootWorkScope {
    owner: Arc<RootWorkTracker>,
    scope: WorkScope,
    epoch: u64,
    chain: uuid::Uuid,
}
pub(crate) struct RootWorkGuard {
    owner: Arc<RootWorkTracker>,
    work: Option<WorkGuard>,
    epoch: u64,
    chain: uuid::Uuid,
    accounted: bool,
}
pub(crate) struct RootRestoreGuard {
    owner: Arc<RootWorkTracker>,
    epoch: u64,
    touched: bool,
    finished: bool,
    others: Vec<RootRestoreGuard>,
}
impl RootWorkTracker {
    pub(crate) fn for_workspace(root: &Path) -> Result<Arc<Self>, RootWorkError> {
        Self::open_native(root, false)
    }
    /// Only the owner-confirmed native registration command invokes enrollment.
    /// Existing partial/corrupt namespaces are never overwritten by this path.
    pub(crate) fn enroll_managed(root: &Path) -> Result<Arc<Self>, RootWorkError> {
        let owner = Self::open_native(root, true)?;
        owner.confine_managed_reads()?;
        Ok(owner)
    }
    fn open_native(root: &Path, initialize_managed: bool) -> Result<Arc<Self>, RootWorkError> {
        let root = root.canonicalize().map_err(|_| RootWorkError)?;
        // One immutable native storage authority for every caller and chat.
        // A task/conversation Harness path can never choose a new drain ledger.
        let native_store = crate::harness::Harness::default_root().map_err(|_| RootWorkError)?;
        private_dir(&native_store)?;
        let store = native_store.canonicalize().map_err(|_| RootWorkError)?;
        let anchor = RootIdentity::open(&root)?;
        let store_identity = RootIdentity::open(&store)?;
        // Tool scopes cannot contain the host's authority/journal store.
        if store.starts_with(&root) || store_identity.ancestors.contains(&anchor.key) {
            return Err(RootWorkError);
        }
        let protected = anchor.ancestors.contains(&store_identity.key) || root.starts_with(&store);
        if protected && !storage::managed_layout(&root, &store) {
            return Err(RootWorkError);
        }
        let mut registry = REGISTRY
            .get_or_init(Default::default)
            .lock()
            .map_err(|_| RootWorkError)?;
        registry.retain(|_, value| value.strong_count() > 0);
        if let Some(owner) = registry.get(&root).and_then(Weak::upgrade) {
            owner.anchor.verify(&root)?;
            // Root identity, not caller-selected harness storage, owns the
            // process-local tracker. A second context cannot bypass its fence.
            return Ok(owner);
        }
        for owner in registry.values().filter_map(Weak::upgrade) {
            if owner.root != root && owner.anchor.key == anchor.key {
                return Err(RootWorkError);
            }
        }
        live_conflict(&registry, &root, &anchor)?;
        if registry.len() >= 256 {
            return Err(RootWorkError);
        }
        let binding = format!("{:x}", Sha256::digest(root.to_string_lossy().as_bytes()));
        let parent = store.join("native-root-work-v1");
        private_dir(&parent)?;
        persisted_conflict(&parent, &root, &anchor, &registry)?;
        let namespace = parent.join(&binding);
        if protected && !initialize_managed && std::fs::symlink_metadata(&namespace).is_err() {
            return Err(RootWorkError);
        }
        let mut builder = std::fs::DirBuilder::new();
        #[cfg(unix)]
        {
            use std::os::unix::fs::DirBuilderExt;
            builder.mode(0o700);
        }
        let initialize = match builder.create(&namespace) {
            Ok(()) => true,
            Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => false,
            Err(_) => return Err(RootWorkError),
        };
        private_dir(&namespace)?;
        #[cfg(unix)]
        {
            std::fs::File::open(&store)
                .and_then(|f| f.sync_all())
                .map_err(|_| RootWorkError)?;
            std::fs::File::open(&parent)
                .and_then(|f| f.sync_all())
                .map_err(|_| RootWorkError)?;
        }
        if !initialize {
            regular(&namespace.join("auth.json"))?;
            regular(&namespace.join("auth.lock"))?;
        }
        let mut disk = AuthDocument::open(&namespace).map_err(|_| RootWorkError)?;
        let document = if initialize {
            let d = Document {
                version: 1,
                binding,
                root: root.clone(),
                identity: anchor.key,
                ancestors: anchor.ancestors.clone(),
                epoch: 1,
                phase: Phase::Clean,
                managed_reads: initialize_managed,
            };
            disk.save(&d).map_err(|_| RootWorkError)?;
            d
        } else {
            let d: Document = disk
                .load()
                .map_err(|_| RootWorkError)?
                .ok_or(RootWorkError)?;
            if d.version != 1
                || d.binding != binding
                || d.root != root
                || d.identity != anchor.key
                || d.ancestors != anchor.ancestors
                || d.epoch == 0
                || d.phase != Phase::Clean
                || (protected && !initialize_managed && !d.managed_reads)
            {
                return Err(RootWorkError);
            }
            d
        };
        let owner = Arc::new(Self {
            anchor,
            root: root.clone(),
            store,
            state: Mutex::new(State {
                disk,
                document,
                drain: WorkDrain::new(),
                poisoned: false,
                chains: HashMap::new(),
                exclusive: None,
            }),
        });
        registry.insert(root, Arc::downgrade(&owner));
        Ok(owner)
    }
    fn persist(state: &mut State, phase: Phase) -> Result<(), RootWorkError> {
        if state.poisoned {
            return Err(RootWorkError);
        }
        state.document.phase = phase;
        if state.disk.save(&state.document).is_err() {
            state.poisoned = true;
            return Err(RootWorkError);
        }
        Ok(())
    }
    pub(crate) fn register(self: &Arc<Self>) -> Result<RootWorkGuard, RootWorkError> {
        self.anchor.verify(&self.root)?;
        let registry = REGISTRY
            .get_or_init(Default::default)
            .lock()
            .map_err(|_| RootWorkError)?;
        live_conflict(&registry, &self.root, &self.anchor)?;
        persisted_conflict(
            &self.store.join("native-root-work-v1"),
            &self.root,
            &self.anchor,
            &registry,
        )?;
        let mut state = self.state.lock().map_err(|_| RootWorkError)?;
        if state.poisoned
            || state.document.phase == Phase::Restore
            || state.drain.status().unconfirmed
        {
            return Err(RootWorkError);
        }
        let work = state.drain.register().map_err(|_| RootWorkError)?;
        if state.document.phase == Phase::Clean {
            Self::persist(&mut state, Phase::Busy)?;
        }
        let chain = uuid::Uuid::new_v4();
        state.chains.insert(chain, 1);
        Ok(RootWorkGuard {
            owner: self.clone(),
            work: Some(work),
            epoch: state.document.epoch,
            chain,
            accounted: true,
        })
    }
    fn retire_known(&self, chain: uuid::Uuid) {
        let Ok(mut state) = self.state.lock() else {
            return;
        };
        let Some(count) = state.chains.get_mut(&chain) else {
            state.poisoned = true;
            return;
        };
        *count = count.saturating_sub(1);
        if *count == 0 {
            state.chains.remove(&chain);
        }
        let status = state.drain.status();
        if !state.poisoned
            && !status.unconfirmed
            && status.outstanding == 0
            && state.document.phase == Phase::Busy
        {
            let _ = Self::persist(&mut state, Phase::Clean);
        }
    }
    pub(crate) fn restore(self: &Arc<Self>) -> Result<RootRestoreGuard, RootWorkError> {
        self.anchor.verify(&self.root)?;
        let registry = REGISTRY
            .get_or_init(Default::default)
            .lock()
            .map_err(|_| RootWorkError)?;
        persisted_conflict(
            &self.store.join("native-root-work-v1"),
            &self.root,
            &self.anchor,
            &registry,
        )?;
        let mut others = Vec::new();
        for (root, owner) in registry.iter() {
            if root != &self.root {
                if let Some(owner) = owner.upgrade() {
                    if overlaps(root, &self.root)
                        || storage::physical_overlap(&owner.anchor, &self.anchor)
                    {
                        others.push(owner.restore_single()?);
                    }
                }
            }
        }
        let mut own = self.restore_single()?;
        own.others = others;
        Ok(own)
    }
    fn restore_single(self: &Arc<Self>) -> Result<RootRestoreGuard, RootWorkError> {
        let mut state = self.state.lock().map_err(|_| RootWorkError)?;
        let status = state.drain.status();
        if state.poisoned
            || state.document.phase != Phase::Clean
            || status.outstanding != 0
            || status.unconfirmed
        {
            return Err(RootWorkError);
        }
        Self::persist(&mut state, Phase::Restore)?;
        state.drain.seal();
        Ok(RootRestoreGuard {
            owner: self.clone(),
            epoch: state.document.epoch,
            touched: false,
            finished: false,
            others: Vec::new(),
        })
    }
    pub(crate) fn confine_managed_reads(&self) -> Result<(), RootWorkError> {
        self.anchor.verify(&self.root)?;
        let mut state = self.state.lock().map_err(|_| RootWorkError)?;
        if state.poisoned
            || state.document.phase != Phase::Clean
            || state.drain.status().outstanding != 0
            || state.drain.status().unconfirmed
        {
            return Err(RootWorkError);
        }
        state.document.managed_reads = true;
        Self::persist(&mut state, Phase::Clean)
    }
    pub(crate) fn managed_reads(&self) -> bool {
        self.state
            .lock()
            .map_or(true, |s| s.poisoned || s.document.managed_reads)
    }
    pub(crate) fn native_state(&self) -> &'static str {
        if self.anchor.verify(&self.root).is_err() {
            return "recovery";
        }
        let Ok(state) = self.state.lock() else {
            return "recovery";
        };
        if state.poisoned || state.drain.status().unconfirmed {
            return "recovery";
        }
        if state.document.phase == Phase::Restore || state.exclusive.is_some() {
            "paused"
        } else {
            "available"
        }
    }
}
impl RootWorkScope {
    pub(crate) fn fork(&self) -> Result<RootWorkGuard, RootWorkError> {
        self.owner.anchor.verify(&self.owner.root)?;
        let mut state = self.owner.state.lock().map_err(|_| RootWorkError)?;
        if state.poisoned
            || state.exclusive.is_some_and(|chain| chain != self.chain)
            || state.document.phase != Phase::Busy
            || state.document.epoch != self.epoch
        {
            return Err(RootWorkError);
        }
        let work = self.scope.fork().map_err(|_| RootWorkError)?;
        *state.chains.entry(self.chain).or_default() += 1;
        Ok(RootWorkGuard {
            owner: self.owner.clone(),
            work: Some(work),
            epoch: self.epoch,
            chain: self.chain,
            accounted: true,
        })
    }
}
impl RootWorkGuard {
    pub(crate) fn begin(&mut self) -> Result<(), RootWorkError> {
        self.work
            .as_mut()
            .ok_or(RootWorkError)?
            .begin()
            .map_err(|_| RootWorkError)
    }
    pub(crate) fn scope(&self) -> RootWorkScope {
        RootWorkScope {
            owner: self.owner.clone(),
            scope: self.work.as_ref().expect("live root registration").scope(),
            epoch: self.epoch,
            chain: self.chain,
        }
    }
    pub(crate) fn complete(mut self) {
        if let Some(work) = self.work.take() {
            work.complete();
        }
        self.owner.retire_known(self.chain);
        self.accounted = false;
    }
}
impl Drop for RootWorkGuard {
    fn drop(&mut self) {
        // WorkGuard distinguishes never-started cancellation from uncertain
        // running work. Only a known empty nonpoisoned tracker clears the record.
        drop(self.work.take());
        if self.accounted {
            self.owner.retire_known(self.chain);
            self.accounted = false;
        }
    }
}
impl RootRestoreGuard {
    pub(crate) fn validate(&self) -> Result<(), RootWorkError> {
        self.owner.anchor.verify(&self.owner.root)?;
        for other in &self.others {
            other.validate()?;
        }
        let state = self.owner.state.lock().map_err(|_| RootWorkError)?;
        let status = state.drain.status();
        if self.finished
            || state.poisoned
            || state.document.phase != Phase::Restore
            || state.document.epoch != self.epoch
            || !status.sealed
            || status.outstanding != 0
            || status.unconfirmed
        {
            return Err(RootWorkError);
        }
        Ok(())
    }
    pub(crate) fn before_write(&mut self) -> Result<(), RootWorkError> {
        self.validate()?;
        self.touched = true;
        for other in &mut self.others {
            other.before_write()?;
        }
        Ok(())
    }
    pub(crate) fn commit(&mut self) -> Result<(), RootWorkError> {
        self.validate()?;
        for other in &mut self.others {
            other.commit()?;
        }
        let mut state = self.owner.state.lock().map_err(|_| RootWorkError)?;
        state.document.epoch = state.document.epoch.checked_add(1).ok_or(RootWorkError)?;
        RootWorkTracker::persist(&mut state, Phase::Clean)?;
        state.drain = WorkDrain::new();
        self.finished = true;
        Ok(())
    }
}
impl Drop for RootRestoreGuard {
    fn drop(&mut self) {
        // Known refusal before any destructive step may release its fence.
        // A crash or any uncertainty after the first move remains durable.
        if !self.finished && !self.touched {
            let _ = self.commit();
        } else if !self.finished {
            if let Ok(mut state) = self.owner.state.lock() {
                state.poisoned = true;
            }
        }
    }
}
#[cfg(test)]
mod tests;
