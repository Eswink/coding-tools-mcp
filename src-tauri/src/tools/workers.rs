//! A1 C1 core (SPEC-A1 v2 §1.1–§1.6, §7.4): worker identity, ownership, the durable
//! encrypted WorkerStore, the worker state machine, the concurrency cap and the
//! managed-slot reservation. C1 exposes no tool; dispatch and `for_worker` are C2.
#![cfg_attr(not(test), allow(dead_code))]
use crate::tools::{root_work, ToolContext};
use crate::{
    data::AuthDocument,
    harness::{
        worktree::{SlotReservation, WorktreeError, WorktreeManager},
        Harness,
    },
};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeSet, HashMap},
    path::{Component, Path, PathBuf},
    sync::{Arc, Mutex, OnceLock, Weak},
    time::{SystemTime, UNIX_EPOCH},
};

pub(crate) const DEFAULT_WORKER_LIMIT: usize = 4;
pub(crate) const MAX_WORKER_LIMIT: usize = 8;
const MAX_RECORDS: usize = 64;
const MAX_REQUEST_ID: usize = 128;
const MAX_LABEL_CHARS: usize = 80;
const MAX_CWD_BYTES: usize = 1024;
const STORE_DIR: &str = "agents-v1";

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct WorkerError {
    code: &'static str,
    message: &'static str,
}
impl WorkerError {
    const fn new(code: &'static str, message: &'static str) -> Self {
        Self { code, message }
    }
    pub(crate) fn code(&self) -> &'static str {
        self.code
    }
    pub(crate) fn message(&self) -> &'static str {
        self.message
    }
}
impl From<WorktreeError> for WorkerError {
    fn from(value: WorktreeError) -> Self {
        // CAPACITY / DIRTY / boundary codes pass through unchanged.
        Self::new(value.code(), "Managed worktree operation failed.")
    }
}
fn invalid(message: &'static str) -> WorkerError {
    WorkerError::new("INVALID_ARGUMENT", message)
}
fn not_owned() -> WorkerError {
    // Unknown and foreign workers are indistinguishable (T1).
    WorkerError::new("WORKER_NOT_OWNED", "Worker not found for this owner.")
}
fn unavailable() -> WorkerError {
    WorkerError::new(
        "STORE_UNAVAILABLE",
        "Worker store is unavailable or corrupt.",
    )
}
fn state_error() -> WorkerError {
    WorkerError::new(
        "WORKER_STATE",
        "Operation not allowed in the worker's current state.",
    )
}
fn root_unavailable() -> WorkerError {
    WorkerError::new(
        "NATIVE_ROOT_UNAVAILABLE",
        "Source workspace writers are not proven quiescent; no worker operation started.",
    )
}
fn now() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_or(0, |d| d.as_secs())
}
fn hex32(value: &str) -> bool {
    value.len() == 32
        && value
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}

/// Opaque worker identity; never equal to, or derived from, the worktree id.
#[derive(Clone, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(try_from = "String", into = "String")]
pub(crate) struct WorkerId(String);
impl WorkerId {
    pub(crate) fn generate() -> Self {
        Self(uuid::Uuid::new_v4().simple().to_string())
    }
    pub(crate) fn parse(value: &str) -> Result<Self, WorkerError> {
        if hex32(value) {
            Ok(Self(value.to_owned()))
        } else {
            Err(invalid("Invalid worker identifier."))
        }
    }
    pub(crate) fn as_str(&self) -> &str {
        &self.0
    }
}
impl TryFrom<String> for WorkerId {
    type Error = &'static str;
    fn try_from(value: String) -> Result<Self, Self::Error> {
        hex32(&value).then_some(Self(value)).ok_or("worker id")
    }
}
impl From<WorkerId> for String {
    fn from(value: WorkerId) -> Self {
        value.0
    }
}

/// `local` for the native UI; otherwise a domain-separated digest of profile + identity.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub(crate) struct WorkerOwner(String);
impl WorkerOwner {
    pub(crate) fn local() -> Self {
        Self("local".into())
    }
    pub(crate) fn from_context(ctx: &ToolContext) -> Result<Self, WorkerError> {
        let Some(request) = ctx.remote_request.as_ref() else {
            return Ok(Self::local());
        };
        let identity = request.identity().map_err(|_| not_owned())?;
        let mut digest = Sha256::new();
        for part in ["ctm-worker-owner-v1", &request.profile, identity] {
            digest.update((part.len() as u64).to_be_bytes());
            digest.update(part.as_bytes());
        }
        Ok(Self(format!("{:x}", digest.finalize())))
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub(crate) enum WorkerState {
    Creating,
    Ready,
    Cancelled,
    Failed,
    PendingCleanup,
    Discarded,
}
impl WorkerState {
    fn active(self) -> bool {
        !matches!(self, Self::Failed | Self::Discarded)
    }
}

fn default_cwd() -> String {
    ".".into()
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct WorkerRecord {
    pub(crate) worker_id: WorkerId,
    pub(crate) worktree_id: Option<String>,
    pub(crate) workspace_id: String,
    pub(crate) owner: WorkerOwner,
    pub(crate) spawn_request_id: String,
    pub(crate) spawn_fingerprint: String,
    pub(crate) label: String,
    pub(crate) base_head: Option<String>,
    pub(crate) state: WorkerState,
    /// Worker-relative cwd inside its worktree; `.` is the worktree root.
    #[serde(default = "default_cwd")]
    pub(crate) cwd: String,
    pub(crate) created_at: u64,
    pub(crate) last_activity_at: u64,
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Document {
    version: u32,
    workspace_id: String,
    limit: usize,
    workers: Vec<WorkerRecord>,
}

struct Inner {
    disk: AuthDocument,
    doc: Document,
}
pub(crate) struct WorkerStore {
    state: Mutex<Inner>,
}
static REGISTRY: OnceLock<Mutex<HashMap<PathBuf, Weak<WorkerStore>>>> = OnceLock::new();
/// Reservations outlive any one store handle; keyed by worker id.
static PENDING: OnceLock<Mutex<HashMap<String, SlotReservation>>> = OnceLock::new();
fn pending() -> std::sync::MutexGuard<'static, HashMap<String, SlotReservation>> {
    PENDING
        .get_or_init(Default::default)
        .lock()
        .unwrap_or_else(|p| p.into_inner())
}

fn namespace(harness: &Harness) -> PathBuf {
    harness
        .store_root()
        .join(STORE_DIR)
        .join(harness.workspace_id())
}

impl WorkerStore {
    /// One process-wide handle per namespace (the document lock is non-blocking).
    pub(crate) fn open(
        harness: &Harness,
        manager: &WorktreeManager,
    ) -> Result<Arc<Self>, WorkerError> {
        let namespace = namespace(harness);
        let mut registry = REGISTRY
            .get_or_init(Default::default)
            .lock()
            .map_err(|_| unavailable())?;
        registry.retain(|_, value| value.strong_count() > 0);
        if let Some(store) = registry.get(&namespace).and_then(Weak::upgrade) {
            return Ok(store);
        }
        let mut disk = AuthDocument::open(&namespace).map_err(|_| unavailable())?;
        let doc = match disk.load::<Document>().map_err(|_| unavailable())? {
            Some(doc) => {
                if doc.version != 1
                    || doc.workspace_id != harness.workspace_id()
                    || !(1..=MAX_WORKER_LIMIT).contains(&doc.limit)
                    || doc.workers.len() > MAX_RECORDS
                {
                    return Err(unavailable());
                }
                doc
            }
            None => {
                let doc = Document {
                    version: 1,
                    workspace_id: harness.workspace_id().to_owned(),
                    limit: DEFAULT_WORKER_LIMIT,
                    workers: Vec::new(),
                };
                disk.save(&doc).map_err(|_| unavailable())?;
                doc
            }
        };
        let store = Arc::new(Self {
            state: Mutex::new(Inner { disk, doc }),
        });
        store.recover(manager)?;
        registry.insert(namespace, Arc::downgrade(&store));
        Ok(store)
    }
    fn lock(&self) -> Result<std::sync::MutexGuard<'_, Inner>, WorkerError> {
        self.state.lock().map_err(|_| unavailable())
    }
    /// Crash recovery (SPEC-A1 v2 §1.5): a `creating` record with no live reservation
    /// becomes `ready` when its pinned worktree exists, otherwise `failed`;
    /// `pending_cleanup` retries the clean removal.
    fn recover(&self, manager: &WorktreeManager) -> Result<(), WorkerError> {
        let mut inner = self.lock()?;
        let live: HashMap<String, String> = manager
            .list()?
            .into_iter()
            .map(|item| (item.id, item.head))
            .collect();
        let pending = pending();
        let mut changed = false;
        for record in inner.doc.workers.iter_mut() {
            match record.state {
                WorkerState::Creating if !pending.contains_key(record.worker_id.as_str()) => {
                    match record.worktree_id.as_ref().and_then(|id| live.get(id)) {
                        Some(head) => {
                            record.base_head = Some(head.clone());
                            record.state = WorkerState::Ready;
                        }
                        None => {
                            record.worktree_id = None;
                            record.state = WorkerState::Failed;
                        }
                    }
                    changed = true;
                }
                WorkerState::PendingCleanup => {
                    let removed = match record.worktree_id.as_deref() {
                        Some(id) => manager.remove_clean(id).is_ok(),
                        None => true,
                    };
                    if removed {
                        record.state = WorkerState::Discarded;
                        changed = true;
                    }
                }
                _ => {}
            }
        }
        drop(pending);
        if changed {
            let Inner { disk, doc } = &mut *inner;
            disk.save(doc).map_err(|_| unavailable())?;
        }
        Ok(())
    }
    /// Test hook: persist a `creating` record as if the process died mid-spawn.
    #[cfg(test)]
    pub(crate) fn inject_interrupted_for_test(
        &self,
        owner: &WorkerOwner,
        worktree_id: Option<&str>,
    ) -> Result<WorkerId, WorkerError> {
        let mut inner = self.lock()?;
        let id = WorkerId::generate();
        let workspace_id = inner.doc.workspace_id.clone();
        inner.doc.workers.push(WorkerRecord {
            worker_id: id.clone(),
            worktree_id: worktree_id.map(str::to_owned),
            workspace_id,
            owner: owner.clone(),
            spawn_request_id: format!("interrupted-{}", id.as_str()),
            spawn_fingerprint: String::new(),
            label: "interrupted".into(),
            base_head: None,
            state: WorkerState::Creating,
            cwd: default_cwd(),
            created_at: now(),
            last_activity_at: now(),
        });
        let Inner { disk, doc } = &mut *inner;
        disk.save(doc).map_err(|_| unavailable())?;
        Ok(id)
    }
}
impl Inner {
    fn commit(&mut self) -> Result<(), WorkerError> {
        self.disk.save(&self.doc).map_err(|_| unavailable())
    }
    fn owned_mut(
        &mut self,
        owner: &WorkerOwner,
        id: &WorkerId,
    ) -> Result<&mut WorkerRecord, WorkerError> {
        self.doc
            .workers
            .iter_mut()
            .find(|r| &r.worker_id == id && &r.owner == owner)
            .ok_or_else(not_owned)
    }
    fn make_room(&mut self) -> Result<(), WorkerError> {
        if self.doc.workers.len() < MAX_RECORDS {
            return Ok(());
        }
        let oldest = self
            .doc
            .workers
            .iter()
            .enumerate()
            .filter(|(_, r)| !r.state.active())
            .min_by_key(|(_, r)| r.last_activity_at)
            .map(|(i, _)| i)
            .ok_or_else(|| WorkerError::new("WORKER_LIMIT", "Worker record capacity reached."))?;
        self.doc.workers.remove(oldest);
        Ok(())
    }
}

pub(crate) fn manager(ctx: &ToolContext) -> Result<WorktreeManager, WorkerError> {
    Ok(WorktreeManager::new(
        ctx.workspace.root(),
        ctx.harness.store_root(),
        ctx.harness.workspace_id(),
    )?)
}
fn open(ctx: &ToolContext) -> Result<(WorktreeManager, Arc<WorkerStore>), WorkerError> {
    let manager = manager(ctx)?;
    let store = WorkerStore::open(&ctx.harness, &manager)?;
    Ok((manager, store))
}
fn validate_request(request_id: &str, label: &str) -> Result<(), WorkerError> {
    if request_id.is_empty()
        || request_id.len() > MAX_REQUEST_ID
        || request_id.chars().any(char::is_control)
    {
        return Err(invalid(
            "request_id must be 1..128 bytes without control characters.",
        ));
    }
    if label.chars().count() > MAX_LABEL_CHARS || label.chars().any(char::is_control) {
        return Err(invalid(
            "label must be at most 80 characters without control characters.",
        ));
    }
    Ok(())
}
fn fingerprint(label: &str) -> String {
    let mut digest = Sha256::new();
    digest.update(b"ctm-worker-spawn-v1\0HEAD\0");
    digest.update(label.as_bytes());
    format!("{:x}", digest.finalize())
}

/// Phase 1 of spawn: validate, enforce the worker cap, reserve a managed slot under the
/// native lifecycle lock and persist a `creating` record. Returns before any Git work so
/// an async builder can never race `worktree_create` for the slot (SPEC-A1 v2 §1.3).
pub(crate) fn spawn(
    ctx: &ToolContext,
    request_id: &str,
    label: &str,
) -> Result<(WorkerRecord, bool), WorkerError> {
    validate_request(request_id, label)?;
    let owner = WorkerOwner::from_context(ctx)?;
    let _root = root_work::exclusive_context(ctx).map_err(|_| root_unavailable())?;
    let (manager, store) = open(ctx)?;
    let mut inner = store.lock()?;
    let print = fingerprint(label);
    if let Some(existing) = inner
        .doc
        .workers
        .iter()
        .find(|r| r.owner == owner && r.spawn_request_id == request_id)
    {
        return if existing.spawn_fingerprint == print {
            Ok((existing.clone(), false))
        } else {
            Err(WorkerError::new(
                "REQUEST_ID_CONFLICT",
                "request_id was already used with different arguments.",
            ))
        };
    }
    let active = inner
        .doc
        .workers
        .iter()
        .filter(|r| r.state.active())
        .count();
    if active >= inner.doc.limit {
        return Err(WorkerError::new(
            "WORKER_LIMIT",
            "Concurrent worker limit reached.",
        ));
    }
    inner.make_room()?;
    let id = WorkerId::generate();
    let reservation = manager.reserve_slot();
    let mut record = WorkerRecord {
        worker_id: id.clone(),
        worktree_id: None,
        workspace_id: ctx.harness.workspace_id().to_owned(),
        owner,
        spawn_request_id: request_id.to_owned(),
        spawn_fingerprint: print,
        label: label.to_owned(),
        base_head: None,
        state: WorkerState::Creating,
        cwd: default_cwd(),
        created_at: now(),
        last_activity_at: now(),
    };
    match reservation {
        Ok(slot) => {
            record.worktree_id = Some(slot.id().to_owned());
            inner.doc.workers.push(record.clone());
            if let Err(error) = inner.commit() {
                inner.doc.workers.pop();
                return Err(error);
            }
            pending().insert(id.as_str().to_owned(), slot);
            Ok((record, true))
        }
        Err(error) => {
            record.state = WorkerState::Failed;
            inner.doc.workers.push(record);
            inner.commit()?;
            Err(error.into())
        }
    }
}

/// Phase 2 of spawn: build the reserved worktree and mark the worker `ready`.
pub(crate) fn complete_spawn(
    ctx: &ToolContext,
    worker_id: &str,
) -> Result<WorkerRecord, WorkerError> {
    let id = WorkerId::parse(worker_id)?;
    let owner = WorkerOwner::from_context(ctx)?;
    let _root = root_work::exclusive_context(ctx).map_err(|_| root_unavailable())?;
    let (manager, store) = open(ctx)?;
    {
        let mut inner = store.lock()?;
        let record = inner.owned_mut(&owner, &id)?;
        match record.state {
            WorkerState::Creating => {}
            WorkerState::Ready => return Ok(record.clone()),
            _ => return Err(state_error()),
        }
    }
    // Lock order: store mutex is released before the native lifecycle lock is taken.
    let slot = pending().remove(id.as_str());
    let built = match slot {
        Some(slot) => manager.create_reserved(slot).map_err(WorkerError::from),
        None => Err(state_error()),
    };
    let mut inner = store.lock()?;
    let record = inner.owned_mut(&owner, &id)?;
    let result = match built {
        Ok(item) => {
            record.base_head = Some(item.head);
            record.state = WorkerState::Ready;
            record.last_activity_at = now();
            Ok(record.clone())
        }
        Err(error) => {
            record.worktree_id = None;
            record.state = WorkerState::Failed;
            record.last_activity_at = now();
            Err(error)
        }
    };
    inner.commit()?;
    result
}

pub(crate) fn status(
    ctx: &ToolContext,
    worker_id: Option<&str>,
) -> Result<Vec<WorkerRecord>, WorkerError> {
    let id = worker_id.map(WorkerId::parse).transpose()?;
    let owner = WorkerOwner::from_context(ctx)?;
    let (_, store) = open(ctx)?;
    let inner = store.lock()?;
    let records: Vec<_> = inner
        .doc
        .workers
        .iter()
        .filter(|r| r.owner == owner && id.as_ref().is_none_or(|id| &r.worker_id == id))
        .cloned()
        .collect();
    if id.is_some() && records.is_empty() {
        return Err(not_owned());
    }
    Ok(records)
}

pub(crate) fn cancel(ctx: &ToolContext, worker_id: &str) -> Result<WorkerRecord, WorkerError> {
    let id = WorkerId::parse(worker_id)?;
    let owner = WorkerOwner::from_context(ctx)?;
    let (_, store) = open(ctx)?;
    let mut inner = store.lock()?;
    let record = inner.owned_mut(&owner, &id)?;
    match record.state {
        WorkerState::Ready => {
            record.state = WorkerState::Cancelled;
            record.last_activity_at = now();
        }
        WorkerState::Cancelled => return Ok(record.clone()),
        _ => return Err(state_error()),
    }
    let out = record.clone();
    inner.commit()?;
    Ok(out)
}

/// Removes the worker's worktree only when clean. DIRTY passes through unchanged;
/// any other removal failure leaves the worker in `pending_cleanup` for recovery.
pub(crate) fn discard(ctx: &ToolContext, worker_id: &str) -> Result<WorkerRecord, WorkerError> {
    let id = WorkerId::parse(worker_id)?;
    let owner = WorkerOwner::from_context(ctx)?;
    let _root = root_work::exclusive_context(ctx).map_err(|_| root_unavailable())?;
    let (manager, store) = open(ctx)?;
    let mut inner = store.lock()?;
    let record = inner.owned_mut(&owner, &id)?;
    match record.state {
        WorkerState::Discarded => return Ok(record.clone()),
        WorkerState::Creating => return Err(state_error()),
        _ => {}
    }
    let removal = match record.worktree_id.as_deref() {
        Some(tree) => manager.remove_clean(tree),
        None => Ok(()),
    };
    match removal {
        Ok(()) => record.state = WorkerState::Discarded,
        Err(error) if error.code() == "DIRTY" => return Err(error.into()),
        Err(_) => record.state = WorkerState::PendingCleanup,
    }
    record.last_activity_at = now();
    let out = record.clone();
    inner.commit()?;
    Ok(out)
}

/// Stores a worker-relative cwd; it must name an existing directory inside the worktree.
pub(crate) fn set_cwd(
    ctx: &ToolContext,
    worker_id: &str,
    cwd: &str,
) -> Result<WorkerRecord, WorkerError> {
    let id = WorkerId::parse(worker_id)?;
    let owner = WorkerOwner::from_context(ctx)?;
    let relative = Path::new(cwd);
    if cwd.is_empty()
        || cwd.len() > MAX_CWD_BYTES
        || cwd.chars().any(char::is_control)
        || cwd.contains('\\')
        || !relative
            .components()
            .all(|c| matches!(c, Component::Normal(_) | Component::CurDir))
    {
        return Err(invalid(
            "cwd must be a relative path inside the worker worktree.",
        ));
    }
    let (manager, store) = open(ctx)?;
    let mut inner = store.lock()?;
    let record = inner.owned_mut(&owner, &id)?;
    if record.state != WorkerState::Ready {
        return Err(state_error());
    }
    let tree = record.worktree_id.clone().ok_or_else(state_error)?;
    let base = manager
        .list()?
        .into_iter()
        .find(|item| item.id == tree)
        .ok_or_else(state_error)?;
    let root = ctx
        .harness
        .store_root()
        .join("worktrees-v1")
        .join(ctx.harness.workspace_id())
        .join(&base.id)
        .canonicalize()
        .map_err(|_| invalid("cwd must exist inside the worker worktree."))?;
    let target = root
        .join(relative)
        .canonicalize()
        .map_err(|_| invalid("cwd must exist inside the worker worktree."))?;
    if !target.starts_with(&root) || !target.is_dir() {
        return Err(invalid("cwd must exist inside the worker worktree."));
    }
    let normal: Vec<_> = relative
        .components()
        .filter_map(|c| match c {
            Component::Normal(v) => v.to_str(),
            _ => None,
        })
        .collect();
    record.cwd = if normal.is_empty() {
        default_cwd()
    } else {
        normal.join("/")
    };
    record.last_activity_at = now();
    let out = record.clone();
    inner.commit()?;
    Ok(out)
}

/// Native-owner setting only; remote callers can never raise the cap.
pub(crate) fn configure_limit(ctx: &ToolContext, limit: usize) -> Result<(), WorkerError> {
    if ctx.remote_request.is_some() {
        return Err(not_owned());
    }
    if !(1..=MAX_WORKER_LIMIT).contains(&limit) {
        return Err(invalid("Worker limit must be between 1 and 8."));
    }
    let (_, store) = open(ctx)?;
    let mut inner = store.lock()?;
    inner.doc.limit = limit;
    inner.commit()
}

/// Worktree ids held by any non-discarded worker in this workspace; `worktree_*`
/// tools never list or remove these. Absent namespace means none (no store is created).
pub(crate) fn owned_worktrees(
    ctx: &ToolContext,
    manager: &WorktreeManager,
) -> Result<BTreeSet<String>, WorkerError> {
    if std::fs::symlink_metadata(namespace(&ctx.harness)).is_err() {
        return Ok(BTreeSet::new());
    }
    let store = WorkerStore::open(&ctx.harness, manager)?;
    let inner = store.lock()?;
    Ok(inner
        .doc
        .workers
        .iter()
        .filter(|r| r.state != WorkerState::Discarded)
        .filter_map(|r| r.worktree_id.clone())
        .collect())
}

#[cfg(test)]
#[path = "workers/tests.rs"]
mod tests;
