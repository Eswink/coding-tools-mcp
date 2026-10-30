//! A1 C1 core (SPEC-A1 v4 §1.1–§1.6, §7.4): worker identity, ownership, the durable
//! encrypted WorkerStore, the worker state machine, the concurrency cap and the
//! managed-slot reservation. C2 adds `route` (dispatch stripping + for_worker) and
//! the main-root drain primitive; still no MCP tool or catalog entry (v4 §7.4).
//!
//! Scope (v4 §1.5): the store, the managed slots, the draining flag and the
//! integration journal hang off the MAIN root (`ToolContext::host`), one per main
//! root, never per chat session or epoch. Ownership is still the per-session hash.
#![cfg_attr(not(test), allow(dead_code))]
use crate::tools::{context::HostRoots, root_work, workspace::WorkspaceError, ToolContext};
use crate::{
    data::{AuthDocument, AuthDocumentReader},
    harness::worktree::{SlotReservation, WorktreeError, WorktreeManager},
};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeSet, HashMap},
    path::{Component, Path, PathBuf},
    sync::{
        atomic::{AtomicU64, Ordering},
        Arc, Mutex, MutexGuard, OnceLock,
    },
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

pub(crate) const DEFAULT_WORKER_LIMIT: usize = 4;
pub(crate) const MAX_WORKER_LIMIT: usize = 8;
const MAX_RECORDS: usize = 64;
const MAX_REQUEST_ID: usize = 128;
const MAX_LABEL_CHARS: usize = 80;
const MAX_CWD_BYTES: usize = 1024;
const STORE_DIR: &str = "agents-v1";
/// INTEGRATE_BUSY retry hint and drain budget (v4 §5.2).
pub(crate) const RETRY_AFTER_MS: u64 = 1000;
/// The integrate drain budget; the caller is C5 `subagent_integrate`.
#[allow(dead_code)]
pub(crate) const DRAIN_BUDGET: Duration = Duration::from_secs(10);
const DRAIN_BACKOFF_MS: &[u64] = &[50, 100, 200, 400, 800, 1600];
const DRAIN_BACKOFF_CAP_MS: u64 = 2000;

/// The 22 tools that accept `worker_id` (v4 §2.3/§3.1). C2b adds
/// `change_summary` (a worker-scoped summary, never main-task harness state)
/// and `list_exec_tasks` (filtered to the worker's tagged jobs).
pub(crate) const WORKER_TOOLS: &[&str] = &[
    "git_status",
    "git_diff",
    "git_log",
    "git_show",
    "git_blame",
    "check_exec_environment",
    "get_default_cwd",
    "set_default_cwd",
    "read_file",
    "list_dir",
    "list_files",
    "search_text",
    "grep_text",
    "grep",
    "view_image",
    "patch_check",
    "apply_patch",
    "exec_command",
    "exec_health_check",
    "start_exec_task",
    "change_summary",
    "list_exec_tasks",
];

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
const INVALID_WORKER_ID: &str = "Invalid worker identifier.";
/// A1 C3: the envelope of a malformed worker_id, shared by the native chat
/// outer layer and `bind` (code INVALID_ARGUMENT, category validation).
pub(crate) fn invalid_worker_id() -> Value {
    error_value(&invalid(INVALID_WORKER_ID))
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
fn busy() -> WorkerError {
    WorkerError::new(
        "INTEGRATE_BUSY",
        "An integration is draining this workspace's workers; retry later.",
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
            Err(invalid(INVALID_WORKER_ID))
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
        match ctx.remote_request.as_ref() {
            Some(request) => Self::from_request(request),
            None => Ok(Self::local()),
        }
    }
    /// The same digest from a request alone (cloud_host prepare, v4 §3.5).
    pub(crate) fn from_request(
        request: &crate::auth::chat::RemoteRequest,
    ) -> Result<Self, WorkerError> {
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
    /// A1 C3 (v4 §1.4.3): the newest `MAX_OPS` worker writes, oldest first.
    /// Stored in the record so it shares the store's encryption, transactional
    /// save and `make_room` lifetime; C2b documents load with an empty log.
    #[serde(default)]
    pub(crate) ops: Vec<WorkerOp>,
    /// Total writes ever logged for this worker (the last `seq`).
    #[serde(default)]
    pub(crate) ops_seq: u64,
}

/// Per-worker operation log bound (v4 §1.4.3 "bounded").
pub(crate) const MAX_OPS: usize = 32;
const MAX_OP_CODE: usize = 64;
/// One worker write. Never carries arguments, paths, commands or output.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct WorkerOp {
    pub(crate) seq: u64,
    pub(crate) at: u64,
    pub(crate) tool: String,
    pub(crate) ok: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub(crate) error_code: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub(crate) affected_files: Option<u64>,
}

#[derive(Clone, Serialize, Deserialize)]
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
    /// `creating` records were reconciled against `git worktree list` (memory only).
    states_recovered: bool,
}
/// One per main root for the life of the process (v4 N3): loaded and decrypted
/// once; the document lock is held until the process exits.
pub(crate) struct WorkerStore {
    state: Mutex<Inner>,
    /// Memory only (v4 §5.2): the draining flag and the in-flight worker calls of
    /// every session of this main root. Lock order: `state` before `flight`.
    flight: Mutex<Flight>,
    generation: u64,
}
#[derive(Default)]
struct Flight {
    draining: bool,
    active: HashMap<WorkerId, (WorkerOwner, usize)>,
}
/// Held for the duration of one routed worker call.
pub(crate) struct FlightGuard {
    store: Arc<WorkerStore>,
    id: WorkerId,
}
impl Drop for FlightGuard {
    fn drop(&mut self) {
        let mut flight = self.store.flight();
        if let Some(entry) = flight.active.get_mut(&self.id) {
            entry.1 -= 1;
            if entry.1 == 0 {
                flight.active.remove(&self.id);
            }
        }
    }
}
/// Holds the main-root exclusive guard and the draining flag until dropped (C5
/// integrates while holding it).
pub(crate) struct DrainGuard {
    store: Arc<WorkerStore>,
    _exclusive: root_work::RootExclusiveGuard,
}
impl Drop for DrainGuard {
    fn drop(&mut self) {
        self.store.flight().draining = false;
    }
}
/// The worker a re-rooted ToolContext is bound to (v4 §1.4.2).
#[derive(Debug)]
pub(crate) struct WorkerBinding {
    pub(crate) worker_id: WorkerId,
    /// Read by C3 (worker ops log) and C5 (integrate attribution).
    pub(crate) owner: WorkerOwner,
    #[allow(dead_code)]
    pub(crate) worktree_id: String,
    pub(crate) worktree_root: PathBuf,
    /// Worker-relative cwd at resolution time (`.` for the root).
    pub(crate) cwd: String,
}
static REGISTRY: OnceLock<Mutex<HashMap<PathBuf, Arc<WorkerStore>>>> = OnceLock::new();
static GENERATION: AtomicU64 = AtomicU64::new(1);
/// Reservations outlive any one store handle; keyed by worker id.
static PENDING: OnceLock<Mutex<HashMap<String, SlotReservation>>> = OnceLock::new();
fn pending() -> std::sync::MutexGuard<'static, HashMap<String, SlotReservation>> {
    PENDING
        .get_or_init(Default::default)
        .lock()
        .unwrap_or_else(|p| p.into_inner())
}
fn registry(
) -> Result<std::sync::MutexGuard<'static, HashMap<PathBuf, Arc<WorkerStore>>>, WorkerError> {
    REGISTRY
        .get_or_init(Default::default)
        .lock()
        .map_err(|_| unavailable())
}

/// `<main store_root>/agents-v1/<workspace_id>` (v4 §1.5); never a chat-v1 root.
fn namespace(host: &HostRoots) -> PathBuf {
    host.store_root.join(STORE_DIR).join(&host.workspace_id)
}
fn validate(doc: Document, host: &HostRoots) -> Result<Document, WorkerError> {
    if doc.version != 1
        || doc.workspace_id != host.workspace_id
        || !(1..=MAX_WORKER_LIMIT).contains(&doc.limit)
        || doc.workers.len() > MAX_RECORDS
    {
        return Err(unavailable());
    }
    Ok(doc)
}

impl WorkerStore {
    fn insert(
        registry: &mut HashMap<PathBuf, Arc<Self>>,
        namespace: PathBuf,
        disk: AuthDocument,
        doc: Document,
    ) -> Arc<Self> {
        let store = Arc::new(Self {
            state: Mutex::new(Inner {
                disk,
                doc,
                states_recovered: false,
            }),
            flight: Mutex::default(),
            generation: GENERATION.fetch_add(1, Ordering::Relaxed),
        });
        registry.insert(namespace, store.clone());
        store
    }
    /// Opens (creating on first use) the main-root store and reconciles `creating`
    /// records once. Never removes worktrees: that is `cleanup`, exclusive callers only.
    pub(crate) fn open(
        host: &HostRoots,
        manager: &WorktreeManager,
    ) -> Result<Arc<Self>, WorkerError> {
        let namespace = namespace(host);
        let store = {
            let mut registry = registry()?;
            match registry.get(&namespace) {
                Some(store) => store.clone(),
                None => {
                    // AuthDocument::open creates the namespace dirs (auth_document.rs:27-34)
                    // and takes the exclusive lock with zero wait (:39).
                    let mut disk = AuthDocument::open(&namespace).map_err(|_| unavailable())?;
                    let doc = match disk.load::<Document>().map_err(|_| unavailable())? {
                        Some(doc) => validate(doc, host)?,
                        None => {
                            let doc = Document {
                                version: 1,
                                workspace_id: host.workspace_id.clone(),
                                limit: DEFAULT_WORKER_LIMIT,
                                workers: Vec::new(),
                            };
                            disk.save(&doc).map_err(|_| unavailable())?;
                            doc
                        }
                    };
                    Self::insert(&mut registry, namespace, disk, doc)
                }
            }
        };
        store.recover_states(manager)?;
        Ok(store)
    }
    /// Read-only open (v4 §3.5): never creates directories, never writes, never
    /// recovers. An absent store is `None`; a busy lock is STORE_UNAVAILABLE.
    pub(crate) fn open_existing(host: &HostRoots) -> Result<Option<Arc<Self>>, WorkerError> {
        let namespace = namespace(host);
        let mut registry = registry()?;
        if let Some(store) = registry.get(&namespace) {
            return Ok(Some(store.clone()));
        }
        match std::fs::symlink_metadata(namespace.join("auth.json")) {
            Ok(meta) if meta.is_file() => {}
            Ok(_) => return Err(unavailable()),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
            Err(_) => return Err(unavailable()),
        }
        let disk = AuthDocument::open(&namespace).map_err(|_| unavailable())?;
        let doc = AuthDocumentReader::default()
            .load::<Document>(&disk)
            .map_err(|_| unavailable())?
            .ok_or_else(unavailable)?;
        let doc = validate(doc, host)?;
        Ok(Some(Self::insert(&mut registry, namespace, disk, doc)))
    }
    fn lock(&self) -> Result<std::sync::MutexGuard<'_, Inner>, WorkerError> {
        self.state.lock().map_err(|_| unavailable())
    }
    fn flight(&self) -> MutexGuard<'_, Flight> {
        self.flight.lock().unwrap_or_else(|p| p.into_inner())
    }
    pub(crate) fn draining(&self) -> bool {
        self.flight().draining
    }
    /// Resolves a `ready` worker of `owner` and registers one in-flight call.
    /// Ownership is checked before draining so a foreign or unknown id never
    /// learns anything (B5). `last_activity_at` moves in memory only.
    fn enter_record(
        self: &Arc<Self>,
        owner: &WorkerOwner,
        id: &WorkerId,
    ) -> Result<(FlightGuard, WorkerRecord), WorkerError> {
        let mut inner = self.lock()?;
        if inner.owned(owner, id)?.state != WorkerState::Ready {
            return Err(state_error());
        }
        let mut flight = self.flight();
        if flight.draining {
            return Err(busy());
        }
        let entry = flight
            .active
            .entry(id.clone())
            .or_insert_with(|| (owner.clone(), 0));
        entry.1 += 1;
        drop(flight);
        let record = inner
            .doc
            .workers
            .iter_mut()
            .find(|r| &r.worker_id == id)
            .ok_or_else(not_owned)?;
        record.last_activity_at = now();
        Ok((
            FlightGuard {
                store: self.clone(),
                id: id.clone(),
            },
            record.clone(),
        ))
    }
    pub(crate) fn enter(
        self: &Arc<Self>,
        owner: &WorkerOwner,
        id: &WorkerId,
    ) -> Result<FlightGuard, WorkerError> {
        self.enter_record(owner, id).map(|(guard, _)| guard)
    }
    /// Read-only resolution for cloud_host prepare: owned and `ready`.
    pub(crate) fn ready_worktree(
        &self,
        owner: &WorkerOwner,
        id: &WorkerId,
    ) -> Result<String, WorkerError> {
        let inner = self.lock()?;
        let record = inner.owned(owner, id)?;
        if record.state != WorkerState::Ready {
            return Err(not_owned());
        }
        record.worktree_id.clone().ok_or_else(not_owned)
    }
    /// Crash recovery, state part (v4 §1.5): a `creating` record with no live
    /// reservation becomes `ready` when its pinned worktree exists, otherwise `failed`.
    /// Memory only; the next commit by any writer persists it. Runs once per process.
    fn recover_states(&self, manager: &WorktreeManager) -> Result<(), WorkerError> {
        let mut inner = self.lock()?;
        if inner.states_recovered {
            return Ok(());
        }
        let live: HashMap<String, String> = manager
            .list()?
            .into_iter()
            .map(|item| (item.id, item.head))
            .collect();
        let pending = pending();
        for record in inner.doc.workers.iter_mut() {
            if record.state == WorkerState::Creating
                && !pending.contains_key(record.worker_id.as_str())
            {
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
            }
        }
        drop(pending);
        inner.states_recovered = true;
        Ok(())
    }
    #[cfg(test)]
    pub(crate) fn generation(&self) -> u64 {
        self.generation
    }
    /// Test hook (C2-b): whether this main root's singleton is registered.
    #[cfg(test)]
    pub(crate) fn registered_for_test(host: &HostRoots) -> bool {
        registry().unwrap().contains_key(&namespace(host))
    }
    /// Test hook: drop the process singleton (simulates a restart).
    #[cfg(test)]
    pub(crate) fn evict_for_test(host: &HostRoots) {
        registry().unwrap().remove(&namespace(host));
    }
    /// Test hook: persist an arbitrary record (e.g. as if the process died mid-spawn).
    #[cfg(test)]
    pub(crate) fn inject_for_test(
        &self,
        owner: &WorkerOwner,
        worktree_id: Option<&str>,
        state: WorkerState,
        last_activity_at: u64,
    ) -> Result<WorkerId, WorkerError> {
        let mut inner = self.lock()?;
        let id = WorkerId::generate();
        let record = WorkerRecord {
            worker_id: id.clone(),
            worktree_id: worktree_id.map(str::to_owned),
            workspace_id: inner.doc.workspace_id.clone(),
            owner: owner.clone(),
            spawn_request_id: format!("injected-{}", id.as_str()),
            spawn_fingerprint: String::new(),
            label: "injected".into(),
            base_head: None,
            state,
            cwd: default_cwd(),
            created_at: last_activity_at,
            last_activity_at,
            ops: Vec::new(),
            ops_seq: 0,
        };
        inner.apply(|doc| {
            doc.workers.push(record);
            Ok(())
        })?;
        Ok(id)
    }
    #[cfg(test)]
    pub(crate) fn inject_interrupted_for_test(
        &self,
        owner: &WorkerOwner,
        worktree_id: Option<&str>,
    ) -> Result<WorkerId, WorkerError> {
        self.inject_for_test(owner, worktree_id, WorkerState::Creating, now())
    }
}
impl Inner {
    /// Transactional update (v4 N4): mutate a copy, persist it, then swap. Memory
    /// never diverges from disk when the closure or the commit fails.
    fn apply<T>(
        &mut self,
        change: impl FnOnce(&mut Document) -> Result<T, WorkerError>,
    ) -> Result<T, WorkerError> {
        let mut next = self.doc.clone();
        let out = change(&mut next)?;
        self.disk.save(&next).map_err(|_| unavailable())?;
        self.doc = next;
        Ok(out)
    }
    fn owned(&self, owner: &WorkerOwner, id: &WorkerId) -> Result<&WorkerRecord, WorkerError> {
        self.doc
            .workers
            .iter()
            .find(|r| &r.worker_id == id && &r.owner == owner)
            .ok_or_else(not_owned)
    }
    fn update<T>(
        &mut self,
        owner: &WorkerOwner,
        id: &WorkerId,
        change: impl FnOnce(&mut WorkerRecord) -> Result<T, WorkerError>,
    ) -> Result<T, WorkerError> {
        self.owned(owner, id)?;
        self.apply(|doc| {
            let record = doc
                .workers
                .iter_mut()
                .find(|r| &r.worker_id == id && &r.owner == owner)
                .ok_or_else(not_owned)?;
            change(record)
        })
    }
    /// PendingCleanup retry (v4 §1.5 / N2). Exclusive callers only: it removes worktrees.
    fn cleanup(&mut self, manager: &WorktreeManager) -> Result<(), WorkerError> {
        let stuck: Vec<(WorkerId, Option<String>)> = self
            .doc
            .workers
            .iter()
            .filter(|r| r.state == WorkerState::PendingCleanup)
            .map(|r| (r.worker_id.clone(), r.worktree_id.clone()))
            .collect();
        let mut done = Vec::new();
        for (id, tree) in stuck {
            let removed = match tree.as_deref() {
                Some(tree) => manager.remove_clean(tree).is_ok(),
                None => true,
            };
            if removed {
                done.push(id);
            }
        }
        if done.is_empty() {
            return Ok(());
        }
        self.apply(|doc| {
            for record in doc
                .workers
                .iter_mut()
                .filter(|r| done.contains(&r.worker_id))
            {
                record.state = WorkerState::Discarded;
            }
            Ok(())
        })
    }
}
fn make_room(doc: &mut Document) -> Result<(), WorkerError> {
    if doc.workers.len() < MAX_RECORDS {
        return Ok(());
    }
    let oldest = doc
        .workers
        .iter()
        .enumerate()
        .filter(|(_, r)| !r.state.active())
        .min_by_key(|(_, r)| r.last_activity_at)
        .map(|(i, _)| i)
        .ok_or_else(|| WorkerError::new("WORKER_LIMIT", "Worker record capacity reached."))?;
    doc.workers.remove(oldest);
    Ok(())
}

/// The main-root WorktreeManager: worker worktrees and their 8 slots are shared by
/// every session of this main root (v4 N1), never a session's chat-v1 root.
pub(crate) fn manager(ctx: &ToolContext) -> Result<WorktreeManager, WorkerError> {
    let host = &ctx.host;
    Ok(WorktreeManager::new(
        &host.workspace_root,
        &host.store_root,
        &host.workspace_id,
    )?)
}
/// `<main store_root>/worktrees-v1/<workspace_id>/<worktree_id>`.
pub(crate) fn worktree_path(host: &HostRoots, worktree_id: &str) -> PathBuf {
    host.store_root
        .join("worktrees-v1")
        .join(&host.workspace_id)
        .join(worktree_id)
}
fn open(ctx: &ToolContext) -> Result<(WorktreeManager, Arc<WorkerStore>), WorkerError> {
    let manager = manager(ctx)?;
    let store = WorkerStore::open(&ctx.host, &manager)?;
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

/// Phase 1 of spawn: validate, enforce the per-session worker cap, reserve a
/// main-root managed slot under the native lifecycle lock and persist a `creating`
/// record. Returns before any Git work so an async builder can never race
/// `worktree_create` for the slot (SPEC-A1 v4 §1.3).
pub(crate) fn spawn(
    ctx: &ToolContext,
    request_id: &str,
    label: &str,
) -> Result<(WorkerRecord, bool), WorkerError> {
    validate_request(request_id, label)?;
    let owner = WorkerOwner::from_context(ctx)?;
    if WorkerStore::open_existing(&ctx.host)?.is_some_and(|store| store.draining()) {
        return Err(busy());
    }
    let _root = root_work::exclusive_context(ctx).map_err(|_| root_unavailable())?;
    let (manager, store) = open(ctx)?;
    let mut inner = store.lock()?;
    inner.cleanup(&manager)?;
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
    // WORKER_LIMIT counts this session's active workers; the device-wide bound is
    // the 8 shared main-root slots (CAPACITY).
    let active = inner
        .doc
        .workers
        .iter()
        .filter(|r| r.owner == owner && r.state.active())
        .count();
    if active >= inner.doc.limit {
        return Err(WorkerError::new(
            "WORKER_LIMIT",
            "Concurrent worker limit reached.",
        ));
    }
    let id = WorkerId::generate();
    let mut record = WorkerRecord {
        worker_id: id.clone(),
        worktree_id: None,
        workspace_id: ctx.host.workspace_id.clone(),
        owner,
        spawn_request_id: request_id.to_owned(),
        spawn_fingerprint: print,
        label: label.to_owned(),
        base_head: None,
        state: WorkerState::Creating,
        cwd: default_cwd(),
        created_at: now(),
        last_activity_at: now(),
        ops: Vec::new(),
        ops_seq: 0,
    };
    match manager.reserve_slot() {
        Ok(slot) => {
            record.worktree_id = Some(slot.id().to_owned());
            let stored = record.clone();
            // On failure the clone is discarded (make_room included) and the slot is
            // released under the native lifecycle lock before returning (C1-a).
            if let Err(error) = inner.apply(|doc| {
                make_room(doc)?;
                doc.workers.push(stored);
                Ok(())
            }) {
                manager.release_slot(slot);
                return Err(error);
            }
            pending().insert(id.as_str().to_owned(), slot);
            Ok((record, true))
        }
        Err(error) => {
            record.state = WorkerState::Failed;
            inner.apply(|doc| {
                make_room(doc)?;
                doc.workers.push(record);
                Ok(())
            })?;
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
        inner.cleanup(&manager)?;
        let record = inner.owned(&owner, &id)?;
        match record.state {
            WorkerState::Creating => {}
            WorkerState::Ready => return Ok(record.clone()),
            _ => return Err(state_error()),
        }
    }
    #[cfg(test)]
    if spawn_hooks::take(spawn_hooks::INSIDE_COMPLETE) {
        return Err(unavailable());
    }
    // Lock order: store mutex is released before the native lifecycle lock is taken.
    let slot = pending().remove(id.as_str());
    #[cfg(test)]
    if slot.is_some() && spawn_hooks::take(spawn_hooks::FAIL_BUILD_LOCK) {
        WorktreeManager::fail_next_lifecycle_lock_for_test();
    }
    let built = match slot {
        Some(slot) => manager.create_reserved(slot).map_err(WorkerError::from),
        None => Err(state_error()),
    };
    let mut inner = store.lock()?;
    inner.update(&owner, &id, |record| {
        record.last_activity_at = now();
        Ok(match built {
            Ok(item) => {
                record.base_head = Some(item.head);
                record.state = WorkerState::Ready;
                Ok(record.clone())
            }
            Err(error) => {
                record.worktree_id = None;
                record.state = WorkerState::Failed;
                Err(error)
            }
        })
    })?
}

/// A1 C2b (C1-c): spawn then complete_spawn with a Drop guard, so the reserved
/// slot is consumed or released on EVERY path: success, failure, early return
/// and unwinding. A PENDING reservation never outlives the call that made it.
pub(crate) fn spawn_and_complete(
    ctx: &ToolContext,
    request_id: &str,
    label: &str,
) -> Result<(WorkerRecord, bool), WorkerError> {
    let (record, created) = spawn(ctx, request_id, label)?;
    if record.state != WorkerState::Creating {
        return Ok((record, created));
    }
    let _completion = SpawnCompletion {
        ctx,
        id: record.worker_id.clone(),
    };
    #[cfg(test)]
    if spawn_hooks::take(spawn_hooks::BEFORE_COMPLETE) {
        return Err(unavailable());
    }
    let done = complete_spawn(ctx, record.worker_id.as_str())?;
    Ok((done, created))
}
/// Releases a still-PENDING slot (under the native lifecycle lock) and marks
/// its `creating` record failed. A no-op once complete_spawn took the slot.
struct SpawnCompletion<'a> {
    ctx: &'a ToolContext,
    id: WorkerId,
}
impl Drop for SpawnCompletion<'_> {
    fn drop(&mut self) {
        let Some(slot) = pending().remove(self.id.as_str()) else {
            return;
        };
        match manager(self.ctx) {
            Ok(manager) => manager.release_slot(slot),
            Err(_) => drop(slot),
        }
        let Ok(owner) = WorkerOwner::from_context(self.ctx) else {
            return;
        };
        if let Ok(Some(store)) = WorkerStore::open_existing(&self.ctx.host) {
            if let Ok(mut inner) = store.lock() {
                let _ = inner.update(&owner, &self.id, |record| {
                    if record.state == WorkerState::Creating {
                        record.worktree_id = None;
                        record.state = WorkerState::Failed;
                        record.last_activity_at = now();
                    }
                    Ok(())
                });
            }
        }
    }
}
/// Test-only early-return injection for the C1-c guard.
#[cfg(test)]
pub(crate) mod spawn_hooks {
    use std::cell::Cell;
    pub(crate) const BEFORE_COMPLETE: u8 = 1;
    pub(crate) const INSIDE_COMPLETE: u8 = 2;
    /// A1 C3: the native lifecycle lock fails when the reserved slot is built.
    pub(crate) const FAIL_BUILD_LOCK: u8 = 3;
    thread_local!(static ARMED: Cell<u8> = const { Cell::new(0) });
    pub(crate) fn arm(point: u8) {
        ARMED.with(|a| a.set(point));
    }
    pub(crate) fn take(point: u8) -> bool {
        ARMED.with(|a| {
            let hit = a.get() == point;
            if hit {
                a.set(0);
            }
            hit
        })
    }
}
#[cfg(test)]
pub(crate) fn pending_for_test(worker_id: &str) -> bool {
    pending().contains_key(worker_id)
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
    let record = inner.owned(&owner, &id)?;
    match record.state {
        WorkerState::Ready => {}
        WorkerState::Cancelled => return Ok(record.clone()),
        _ => return Err(state_error()),
    }
    inner.update(&owner, &id, |record| {
        record.state = WorkerState::Cancelled;
        record.last_activity_at = now();
        Ok(record.clone())
    })
}

/// Removes the worker's worktree only when clean. DIRTY passes through unchanged;
/// any other removal failure leaves the worker in `pending_cleanup` for recovery.
pub(crate) fn discard(ctx: &ToolContext, worker_id: &str) -> Result<WorkerRecord, WorkerError> {
    let id = WorkerId::parse(worker_id)?;
    let owner = WorkerOwner::from_context(ctx)?;
    // A1 C3: checked before the root guard, which a running command would
    // otherwise turn into NATIVE_ROOT_UNAVAILABLE. The tagged commands live in this
    // context's own stores, so this reveals nothing about foreign workers.
    worker_idle(ctx, &id)?;
    let _root = root_work::exclusive_context(ctx).map_err(|_| root_unavailable())?;
    let (manager, store) = open(ctx)?;
    let mut inner = store.lock()?;
    inner.cleanup(&manager)?;
    let record = inner.owned(&owner, &id)?;
    match record.state {
        WorkerState::Discarded => return Ok(record.clone()),
        WorkerState::Creating => return Err(state_error()),
        _ => {}
    }
    // Re-checked under the root guard (a command may have started meanwhile).
    worker_idle(ctx, &id)?;
    let removal = match record.worktree_id.as_deref() {
        Some(tree) => manager.remove_clean(tree),
        None => Ok(()),
    };
    let next = match removal {
        Ok(()) => WorkerState::Discarded,
        Err(error) if error.code() == "DIRTY" => return Err(error.into()),
        Err(_) => WorkerState::PendingCleanup,
    };
    inner.update(&owner, &id, |record| {
        record.state = next;
        record.last_activity_at = now();
        Ok(record.clone())
    })
}

/// A1 C3: cancel does not stop a worker's commands, so discard refuses while any
/// async task or interactive session it started still runs; nothing is removed.
fn worker_idle(ctx: &ToolContext, id: &WorkerId) -> Result<(), WorkerError> {
    if ctx.exec_tasks.has_unfinished_worker_work(id.as_str())
        || ctx.sessions.has_unfinished_worker_work(id.as_str())
    {
        return Err(WorkerError::new(
            "WORKER_BUSY",
            "Worker still has running commands; stop them before discarding.",
        ));
    }
    Ok(())
}

/// Validates a worker-relative cwd: an existing directory inside `root`. Returns
/// the normalized `a/b` form (`.` for the root).
pub(crate) fn normalize_cwd(root: &Path, cwd: &str) -> Result<String, WorkerError> {
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
    let outside = || invalid("cwd must exist inside the worker worktree.");
    let root = root.canonicalize().map_err(|_| outside())?;
    let target = root.join(relative).canonicalize().map_err(|_| outside())?;
    if !target.starts_with(&root) || !target.is_dir() {
        return Err(outside());
    }
    let normal: Vec<_> = relative
        .components()
        .filter_map(|c| match c {
            Component::Normal(v) => v.to_str(),
            _ => None,
        })
        .collect();
    Ok(if normal.is_empty() {
        default_cwd()
    } else {
        normal.join("/")
    })
}

/// Stores a worker-relative cwd; it must name an existing directory inside the worktree.
pub(crate) fn set_cwd(
    ctx: &ToolContext,
    worker_id: &str,
    cwd: &str,
) -> Result<WorkerRecord, WorkerError> {
    let id = WorkerId::parse(worker_id)?;
    let owner = WorkerOwner::from_context(ctx)?;
    if cwd.is_empty() || cwd.len() > MAX_CWD_BYTES || cwd.chars().any(char::is_control) {
        return Err(invalid(
            "cwd must be a relative path inside the worker worktree.",
        ));
    }
    let (manager, store) = open(ctx)?;
    let mut inner = store.lock()?;
    let record = inner.owned(&owner, &id)?;
    if record.state != WorkerState::Ready {
        return Err(state_error());
    }
    let tree = record.worktree_id.clone().ok_or_else(state_error)?;
    if !manager.list()?.into_iter().any(|item| item.id == tree) {
        return Err(state_error());
    }
    let normal = normalize_cwd(&worktree_path(&ctx.host, &tree), cwd)?;
    inner.update(&owner, &id, |record| {
        record.cwd = normal;
        record.last_activity_at = now();
        Ok(record.clone())
    })
}

/// The worker writes that enter the ops log (v4 §1.4.3); reads and dry runs do not.
fn logged_op(name: &str, args: &Value) -> bool {
    match name {
        "exec_command" | "start_exec_task" | "set_default_cwd" => true,
        "apply_patch" => !args
            .get("dry_run")
            .and_then(Value::as_bool)
            .unwrap_or(false),
        _ => false,
    }
}
/// Appends one entry to the bound worker's ops log (A1 C3, v4 §1.4.3). Best
/// effort like the main operation log: a store failure never changes the tool
/// result. Only the tool name, outcome, a sanitized error code and an affected
/// file count are kept.
pub(crate) fn record_op(ctx: &ToolContext, name: &str, args: &Value, output: &Value) {
    let Some(binding) = ctx.worker.as_ref() else {
        return;
    };
    // The accepted start_exec_task is the logged operation; its background
    // exec_command run is not a second entry.
    if ctx.managed_task || !logged_op(name, args) {
        return;
    }
    let ok = output.get("ok").and_then(Value::as_bool) == Some(true);
    let error_code = (!ok).then(|| {
        output
            .pointer("/error/code")
            .and_then(Value::as_str)
            .filter(|c| {
                !c.is_empty()
                    && c.len() <= MAX_OP_CODE
                    && c.bytes()
                        .all(|b| b.is_ascii_uppercase() || b.is_ascii_digit() || b == b'_')
            })
            .unwrap_or("UNKNOWN")
            .to_owned()
    });
    let affected_files = output
        .get("affected_files")
        .and_then(Value::as_array)
        .map(|files| files.len() as u64);
    let Ok(Some(store)) = WorkerStore::open_existing(&ctx.host) else {
        return;
    };
    let Ok(mut inner) = store.lock() else {
        return;
    };
    let _ = inner.update(&binding.owner, &binding.worker_id, |record| {
        let at = now();
        record.ops_seq += 1;
        record.ops.push(WorkerOp {
            seq: record.ops_seq,
            at,
            tool: name.to_owned(),
            ok,
            error_code,
            affected_files,
        });
        let excess = record.ops.len().saturating_sub(MAX_OPS);
        record.ops.drain(..excess);
        record.last_activity_at = at;
        Ok(())
    });
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
    inner.apply(|doc| {
        doc.limit = limit;
        Ok(())
    })
}

/// Worktree ids held by any non-discarded worker of this main root; `worktree_*`
/// tools never list or remove these. Read-only: an absent store means none.
pub(crate) fn owned_worktrees(ctx: &ToolContext) -> Result<BTreeSet<String>, WorkerError> {
    let Some(store) = WorkerStore::open_existing(&ctx.host)? else {
        return Ok(BTreeSet::new());
    };
    let inner = store.lock()?;
    Ok(inner
        .doc
        .workers
        .iter()
        .filter(|r| r.state != WorkerState::Discarded)
        .filter_map(|r| r.worktree_id.clone())
        .collect())
}

/// Structured tool error for a worker failure. INTEGRATE_BUSY is retryable.
pub(crate) fn error_value(error: &WorkerError) -> Value {
    let busy = error.code() == "INTEGRATE_BUSY";
    crate::tools::workspace::tool_err(WorkspaceError::ToolDetails {
        code: error.code(),
        message: error.message().into(),
        category: if error.code() == "INVALID_ARGUMENT" {
            "validation"
        } else {
            "worker"
        },
        retryable: busy,
        details: if busy {
            json!({ "retry_after_ms": RETRY_AFTER_MS })
        } else {
            json!({})
        },
    })
}

/// Dispatch stripping (v4 §1.4.1). `None` when the call carries no `worker_id`.
/// Otherwise resolves the caller's `ready` worker on the main-root store, builds
/// `ctx.for_worker(..)`, strips `worker_id` and runs the call there while it is
/// registered as in flight. Runs on the chat-scoped context (after `scoped()`).
pub(crate) fn route(
    ctx: &ToolContext,
    name: &str,
    args: &Value,
    run: impl FnOnce(&ToolContext, &Value) -> Value,
) -> Option<Value> {
    if name.starts_with("subagent_") {
        // On subagent_* worker_id names the target worker, not a routing key.
        return None;
    }
    let raw = args.as_object()?.get("worker_id")?;
    Some(match bind(ctx, name, raw, args) {
        Ok((worker_ctx, stripped, _guard)) => run(&worker_ctx, &stripped),
        Err(error) => error_value(&error),
    })
}
fn bind(
    ctx: &ToolContext,
    name: &str,
    raw: &Value,
    args: &Value,
) -> Result<(ToolContext, Value, FlightGuard), WorkerError> {
    let id = raw
        .as_str()
        .ok_or_else(|| invalid(INVALID_WORKER_ID))
        .and_then(WorkerId::parse)?;
    if !WORKER_TOOLS.contains(&name) {
        return Err(invalid("This tool does not accept worker_id."));
    }
    if ctx.worker.is_some() {
        // A worker context never re-roots again.
        return Err(state_error());
    }
    let owner = WorkerOwner::from_context(ctx)?;
    let store = WorkerStore::open_existing(&ctx.host)?.ok_or_else(not_owned)?;
    let (guard, record) = store.enter_record(&owner, &id)?;
    let worktree_id = record.worktree_id.clone().ok_or_else(state_error)?;
    let target = manager(ctx)?
        .snapshot_target(&worktree_id)
        .map_err(|_| state_error())?;
    let binding = WorkerBinding {
        worker_id: id,
        owner,
        worktree_id,
        worktree_root: target.root,
        cwd: record.cwd,
    };
    let worker_ctx = ctx
        .for_worker(Arc::new(binding))
        .map_err(|_| state_error())?;
    let mut stripped = args.clone();
    if let Some(obj) = stripped.as_object_mut() {
        obj.remove("worker_id");
    }
    Ok((worker_ctx, stripped, guard))
}

/// Integration drain (v4 §5.2): raise the main-root draining flag, wait (bounded
/// backoff 50..1600 ms then 2 s, total `budget`) until no worker call of ANY
/// session is in flight and the main-root exclusive guard is free. Running work
/// is never parked or cancelled. On timeout the flag is cleared and the result is
/// INTEGRATE_BUSY listing only the caller's own blocking worker ids; other
/// sessions appear only as `other_sessions_blocking: N` (B5).
pub(crate) fn drain_for_integrate(
    ctx: &ToolContext,
    budget: Duration,
) -> Result<DrainGuard, Value> {
    let owner = WorkerOwner::from_context(ctx).map_err(|e| error_value(&e))?;
    let (_, store) = open(ctx).map_err(|e| error_value(&e))?;
    {
        let mut flight = store.flight();
        if flight.draining {
            drop(flight);
            return Err(busy_value(&store, &owner));
        }
        flight.draining = true;
    }
    let deadline = Instant::now() + budget;
    let mut step = 0;
    loop {
        if store.flight().active.is_empty() {
            if let Ok(exclusive) = root_work::exclusive_context(ctx) {
                return Ok(DrainGuard {
                    store,
                    _exclusive: exclusive,
                });
            }
        }
        let now = Instant::now();
        if now >= deadline {
            let value = busy_value(&store, &owner);
            store.flight().draining = false;
            return Err(value);
        }
        let wait = Duration::from_millis(
            DRAIN_BACKOFF_MS
                .get(step)
                .copied()
                .unwrap_or(DRAIN_BACKOFF_CAP_MS),
        );
        step += 1;
        std::thread::sleep(wait.min(deadline - now));
    }
}
fn busy_value(store: &WorkerStore, owner: &WorkerOwner) -> Value {
    let flight = store.flight();
    let mut own: Vec<&str> = Vec::new();
    let mut others = 0usize;
    for (id, (holder, _)) in flight.active.iter() {
        if holder == owner {
            own.push(id.as_str());
        } else {
            others += 1;
        }
    }
    own.sort_unstable();
    let error = busy();
    crate::tools::workspace::tool_err(WorkspaceError::ToolDetails {
        code: error.code(),
        message: error.message().into(),
        category: "worker",
        retryable: true,
        details: json!({
            "retry_after_ms": RETRY_AFTER_MS,
            "blocking_worker_ids": own,
            "other_sessions_blocking": others,
        }),
    })
}

#[path = "workers/subagent.rs"]
pub(crate) mod subagent;

#[cfg(test)]
#[path = "workers/tests.rs"]
mod tests;
