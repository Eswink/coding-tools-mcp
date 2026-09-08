use std::collections::{HashMap, HashSet};
use std::path::PathBuf;
use std::sync::{atomic::Ordering, Arc, Mutex, OnceLock, Weak};
use std::time::Duration;
use serde_json::Value;
use crate::data::TaskArchive;
use crate::tools::workspace::WorkspaceError;
use super::{record, state::{error, Job}};

type Registry = Mutex<HashMap<PathBuf, Weak<ExecTaskStore>>>;
static STORES: OnceLock<Registry> = OnceLock::new();
static RETIRED_ROOTS: OnceLock<Mutex<HashSet<PathBuf>>> = OnceLock::new();

/// Pause admission under the same lock as reserve. Failed workspace updates
/// reopen admission; a committed removal retires stale listener handles.
pub(crate) struct TaskAdmissionGuard { store: Arc<ExecTaskStore>, committed: bool }
impl TaskAdmissionGuard {
    pub(crate) fn commit(mut self) {
        if let Some(root) = &self.store.root {
            RETIRED_ROOTS.get_or_init(|| Mutex::new(HashSet::new())).lock()
                .expect("retired task namespaces").insert(root.clone());
        }
        self.committed = true;
    }
}
impl Drop for TaskAdmissionGuard {
    fn drop(&mut self) {
        if !self.committed { self.store.inner.lock().expect("job store").accepting = true; }
    }
}

struct Inner {
    jobs: HashMap<String, Arc<Job>>,
    archive: Option<Arc<TaskArchive>>,
    initialized: bool,
    accepting: bool,
}

/// Same-process service restarts share a supervisor. A new process restores only
/// records; it never replays a command or acts on a stale PID.
pub struct ExecTaskStore {
    inner: Mutex<Inner>, root: Option<PathBuf>,
    profile_id: Mutex<Option<String>>,
    max_active: usize, max_retained: usize, ttl: Duration,
}

impl Default for ExecTaskStore {
    fn default() -> Self { Self::memory(4, 32, Duration::from_secs(3600)) }
}

impl ExecTaskStore {
    fn memory(active: usize, retained: usize, ttl: Duration) -> Self {
        Self { inner: Mutex::new(Inner {jobs: HashMap::new(), archive: None, initialized: true, accepting: true}),
            root: None, profile_id: Mutex::new(None), max_active: active, max_retained: retained, ttl }
    }

    pub(crate) fn shared(root: PathBuf) -> Arc<Self> {
        let mut stores = STORES.get_or_init(|| Mutex::new(HashMap::new())).lock().expect("task registry");
        stores.retain(|_, store| store.strong_count() > 0);
        if let Some(store) = stores.get(&root).and_then(Weak::upgrade) { return store; }
        let accepting = !RETIRED_ROOTS.get_or_init(|| Mutex::new(HashSet::new()))
            .lock().expect("retired task namespaces").contains(&root);
        let store = Arc::new(Self { root: Some(root.clone()), profile_id: Mutex::new(None),
            inner: Mutex::new(Inner { jobs: HashMap::new(), archive: None, initialized: false, accepting }),
            max_active: 4, max_retained: 32, ttl: Duration::from_secs(3600) });
        stores.insert(root, Arc::downgrade(&store));
        store
    }

    pub(crate) fn persistent(&self) -> bool { self.root.is_some() }

    pub(crate) fn bind_profile(&self, profile_id: &str) {
        *self.profile_id.lock().expect("task owner") = Some(profile_id.to_owned());
    }

    pub(crate) fn live_for_profile(profile_id: &str) -> Vec<Arc<Self>> {
        STORES.get_or_init(|| Mutex::new(HashMap::new())).lock().expect("task registry")
            .values().filter_map(Weak::upgrade)
            .filter(|store| store.profile_id.lock().expect("task owner").as_deref() == Some(profile_id)).collect()
    }

    pub(crate) fn pause_admission(self: &Arc<Self>) -> Result<TaskAdmissionGuard, WorkspaceError> {
        let mut inner = self.inner.lock().expect("job store");
        self.initialize(&mut inner)?;
        if !inner.accepting || inner.jobs.values().any(|job| job.data.lock().expect("job state").holds_capacity()) {
            return Err(error("EXEC_TASK_WORKSPACE_BUSY", "Cannot remove or relocate a workspace with active or unconfirmed tasks. Cancel/inspect tasks first.", false));
        }
        inner.accepting = false;
        Ok(TaskAdmissionGuard { store: self.clone(), committed: false })
    }


    fn initialize(&self, inner: &mut Inner) -> Result<(), WorkspaceError> {
        if inner.initialized { return Ok(()); }
        let root = self.root.as_ref().expect("durable store path");
        let archive = Arc::new(TaskArchive::open(root).map_err(storage_error)?);
        let values = archive.load().map_err(storage_error)?;
        let mut jobs = HashMap::new();
        let mut keys = HashSet::new();
        // Validate the entire index before exposing any recovered job.
        for value in values {
            let job = Arc::new(record::restore(value)?);
            if !keys.insert(job.request_id.clone()) || jobs.insert(job.id.clone(), job).is_some() {
                return Err(error("EXEC_TASK_RECORD_INVALID", "Duplicate task identifiers; records preserved", false));
            }
        }
        inner.jobs = jobs;
        inner.archive = Some(archive);
        inner.initialized = true;
        Ok(())
    }

    fn prune(&self, inner: &mut Inner) {
        let archive = inner.archive.clone();
        inner.jobs.retain(|_, job| {
            let eligible = { let d = job.data.lock().expect("job state");
                !d.holds_capacity() && d.finished.is_some_and(|ended| ended.elapsed() >= self.ttl) };
            if !eligible { return true; }
            // A failed authenticated deletion must not permit unsafe key reuse.
            archive.as_ref().is_some_and(|a| a.remove(&job.id).is_err())
        });
    }

    pub(super) fn reserve(&self, request_id: &str, fingerprint: &str, timeout_ms: u64)
        -> Result<(Arc<Job>, bool), WorkspaceError> {
        let mut inner = self.inner.lock().expect("job store");
        self.initialize(&mut inner)?;
        self.prune(&mut inner);
        if let Some(job) = inner.jobs.values().find(|job| job.request_id == request_id) {
            if job.fingerprint != fingerprint {
                return Err(error("IDEMPOTENCY_CONFLICT", "request_id already belongs to different command parameters", false));
            }
            return Ok((job.clone(), false));
        }
        if !inner.accepting {
            return Err(error("EXEC_TASK_WORKSPACE_RETIRED", "Workspace is being changed or was removed; query existing results, do not execute through the old listener.", false));
        }
        let active = inner.jobs.values().filter(|job| job.data.lock().expect("job state").holds_capacity()).count();
        if active >= self.max_active || inner.jobs.len() >= self.max_retained {
            return Err(error("EXEC_TASK_CAPACITY", "Task capacity reached; query existing tasks and never blindly resubmit", true));
        }
        let job = Arc::new(Job::new(request_id.into(), fingerprint.into(), timeout_ms, self.persistent()));
        if let Some(archive) = &inner.archive {
            archive.save(&job.id, || record::snapshot(&job)).map_err(storage_error)?;
        }
        inner.jobs.insert(job.id.clone(), job.clone());
        Ok((job, true))
    }

    pub(super) fn checkpoint(&self, job: &Job) -> Result<(), WorkspaceError> {
        let archive = self.inner.lock().expect("job store").archive.clone();
        if let Some(archive) = archive {
            if let Err(err) = archive.save(&job.id, || record::snapshot(job)) {
                job.persistence_failed.store(true, Ordering::Release);
                return Err(storage_error(err));
            }
        }
        Ok(())
    }

    pub(super) fn get(&self, id: &str) -> Result<Arc<Job>, WorkspaceError> {
        let mut inner = self.inner.lock().expect("job store");
        self.initialize(&mut inner)?;
        self.prune(&mut inner);
        inner.jobs.get(id).cloned().ok_or_else(|| error("EXEC_TASK_NOT_FOUND",
            "Task unknown or expired in this workspace/service; do not automatically re-execute", false))
    }

    pub(super) fn list(&self, request_id: Option<&str>) -> Result<Vec<Value>, WorkspaceError> {
        let mut inner = self.inner.lock().expect("job store");
        self.initialize(&mut inner)?;
        self.prune(&mut inner);
        let mut selected = inner.jobs.values().filter(|j| request_id.is_none_or(|r| j.request_id == r)).cloned().collect::<Vec<_>>();
        selected.sort_by(|a, b| b.created_at.cmp(&a.created_at).then(a.id.cmp(&b.id)));
        Ok(selected.iter().map(|job| {
            let mut summary = job.summary();
            summary.as_object_mut().expect("summary object").remove("result");
            summary
        }).collect())
    }

    #[cfg(test)]
    pub(super) fn with_limits(active: usize, retained: usize, ttl: Duration) -> Self {
        Self::memory(active, retained, ttl)
    }
}

fn storage_error(err: crate::error::AppError) -> WorkspaceError {
    error("EXEC_TASK_STORAGE", &format!("Task storage unavailable; no automatic command retry: {err}"), false)
}
