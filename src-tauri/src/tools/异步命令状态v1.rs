use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use serde_json::{json, Value};
use base64::{engine::general_purpose::STANDARD, Engine};
use uuid::Uuid;

use crate::tools::session::ExecSession;
use crate::tools::workspace::WorkspaceError;

pub(super) const RETAIN_BYTES: usize = 1_048_576;
pub(super) const PAGE_BYTES: u64 = 16_384;
const RESULT_TTL: Duration = Duration::from_secs(3600);

#[derive(Clone, Copy, PartialEq, Eq)]
pub(super) enum Status {
    Queued,
    Running,
    Cancelling,
    Succeeded,
    Failed,
    TimedOut,
    Cancelled,
}

impl Status {
    pub fn terminal(self) -> bool {
        matches!(self, Self::Succeeded | Self::Failed | Self::TimedOut | Self::Cancelled)
    }

    pub fn label(self) -> &'static str {
        match self {
            Self::Queued => "queued", Self::Running => "running",
            Self::Cancelling => "cancelling", Self::Succeeded => "succeeded",
            Self::Failed => "failed", Self::TimedOut => "timed_out", Self::Cancelled => "cancelled",
        }
    }
}

pub(super) struct JobData {
    pub status: Status,
    pub cancel_requested: bool,
    pub session: Option<Arc<ExecSession>>,
    pub result: Option<Value>,
    pub native_stdout: (Vec<u8>, usize),
    pub native_stderr: (Vec<u8>, usize),
    pub finished: Option<Instant>,
    pub completed_at: Option<u64>,
}

pub(super) struct Job {
    pub id: String,
    pub request_id: String,
    pub fingerprint: String,
    pub timeout_ms: u64,
    pub created_at: u64,
    pub started: Instant,
    pub data: Mutex<JobData>,
}

impl Job {
    fn new(request_id: String, fingerprint: String, timeout_ms: u64) -> Self {
        Self {
            id: Uuid::new_v4().to_string(), request_id, fingerprint, timeout_ms,
            created_at: unix_ms(), started: Instant::now(),
            data: Mutex::new(JobData {
                status: Status::Queued, cancel_requested: false, session: None, result: None,
                native_stdout: (Vec::new(), 0), native_stderr: (Vec::new(), 0),
                finished: None, completed_at: None,
            }),
        }
    }

    pub fn summary(&self) -> Value {
        let d = self.data.lock().expect("job state");
        json!({
            "job_id": self.id, "request_id": self.request_id, "status": d.status.label(),
            "accepted": true, "terminal": d.status.terminal(), "cancel_requested": d.cancel_requested,
            "created_at": self.created_at, "completed_at": d.completed_at, "timestamp_unit": "unix_ms",
            "elapsed_ms": d.finished.unwrap_or_else(Instant::now).duration_since(self.started).as_millis(),
            "execution_timeout_ms": self.timeout_ms, "result_ttl_ms": RESULT_TTL.as_millis(),
            "poll_after_ms": if d.status.terminal() { 0 } else { 1000 },
            "command_ok": if d.status.terminal() { Some(d.status == Status::Succeeded) } else { None },
            "result": d.result,
            "recovery_scope": "service_instance", "restart_recoverable": false,
            "cancellation_scope": "direct_child",
            "next_action": if d.status.terminal() { "read remaining output; do not resubmit automatically" }
                           else { "get_exec_task with this job_id; a running task is not an error" },
        })
    }

    pub fn finish(&self, status: Status, mut result: Value) {
        let mut d = self.data.lock().expect("job state");
        if d.status.terminal() { return; }
        if d.session.is_none() {
            d.native_stdout = bounded_output(result.get("stdout").and_then(Value::as_str).unwrap_or(""));
            d.native_stderr = bounded_output(result.get("stderr").and_then(Value::as_str).unwrap_or(""));
        }
        if let Some(obj) = result.as_object_mut() {
            // Output is paged separately. Never publish expired legacy session references.
            for key in ["stdout", "stderr", "output_refs", "session_id", "harness_status", "next_actions"] {
                obj.remove(key);
            }
        }
        d.result = Some(result);
        d.status = status;
        d.finished = Some(Instant::now());
        d.completed_at = Some(unix_ms());
    }

    pub fn output(&self, stream: &str, cursor: u64, limit: u64) -> Result<Value, WorkspaceError> {
        let (session, native) = {
            let d = self.data.lock().expect("job state");
            let native = if d.session.is_some() { None } else {
                Some(if stream == "stdout" { d.native_stdout.clone() } else { d.native_stderr.clone() })
            };
            (d.session.clone(), native)
        };
        let (bytes, total) = match session {
            Some(session) => session.retained_stream_bytes(stream),
            None => native.unwrap_or_default(),
        };
        page(&bytes, total, cursor, limit)
    }
}

fn bounded_output(text: &str) -> (Vec<u8>, usize) {
    let bytes = text.as_bytes();
    (bytes[bytes.len().saturating_sub(RETAIN_BYTES)..].to_vec(), bytes.len())
}

pub(super) fn page(bytes: &[u8], total: usize, cursor: u64, limit: u64) -> Result<Value, WorkspaceError> {
    if cursor > total as u64 {
        return Err(WorkspaceError::invalid_argument("output cursor exceeds total produced bytes"));
    }
    let base = total.saturating_sub(bytes.len()) as u64;
    let offset = cursor.max(base);
    let start = (offset - base) as usize;
    let end = start.saturating_add(limit as usize).min(bytes.len());
    let next = base + end as u64;
    Ok(json!({
        "text": String::from_utf8_lossy(&bytes[start..end]), "encoding": "utf-8-lossy",
        "data_base64": STANDARD.encode(&bytes[start..end]),
        "requested_cursor": cursor, "cursor": offset, "next_cursor": next,
        "retained_from": base, "total_bytes": total, "dropped_bytes": offset - cursor,
        "has_more": next < total as u64,
    }))
}

/// Service-instance scoped: no plaintext command/output is newly persisted to disk.
pub struct ExecTaskStore {
    jobs: Mutex<HashMap<String, Arc<Job>>>,
    max_active: usize,
    max_retained: usize,
    ttl: Duration,
}

impl Default for ExecTaskStore {
    fn default() -> Self {
        Self { jobs: Mutex::new(HashMap::new()), max_active: 4, max_retained: 32, ttl: RESULT_TTL }
    }
}

impl ExecTaskStore {
    fn prune(&self, jobs: &mut HashMap<String, Arc<Job>>) {
        jobs.retain(|_, job| {
            let d = job.data.lock().expect("job state");
            !d.finished.is_some_and(|ended| ended.elapsed() >= self.ttl)
        });
    }

    pub(super) fn reserve(&self, request_id: &str, fingerprint: &str, timeout_ms: u64)
        -> Result<(Arc<Job>, bool), WorkspaceError>
    {
        let mut jobs = self.jobs.lock().expect("job store");
        self.prune(&mut jobs);
        if let Some(job) = jobs.values().find(|job| job.request_id == request_id) {
            if job.fingerprint != fingerprint {
                return Err(error("IDEMPOTENCY_CONFLICT", "request_id already belongs to different command parameters", false));
            }
            return Ok((job.clone(), false));
        }
        let active = jobs.values().filter(|job| !job.data.lock().expect("job state").status.terminal()).count();
        if active >= self.max_active || jobs.len() >= self.max_retained {
            return Err(error("EXEC_TASK_CAPACITY", "Task capacity reached; query existing tasks or retry the same request_id later", true));
        }
        let job = Arc::new(Job::new(request_id.into(), fingerprint.into(), timeout_ms));
        jobs.insert(job.id.clone(), job.clone());
        Ok((job, true))
    }

    pub(super) fn get(&self, id: &str) -> Result<Arc<Job>, WorkspaceError> {
        let mut jobs = self.jobs.lock().expect("job store");
        self.prune(&mut jobs);
        jobs.get(id).cloned().ok_or_else(|| error("EXEC_TASK_NOT_FOUND",
            "Task not found in this service instance (unknown, expired, or service restarted); do not automatically re-execute", false))
    }

    pub(super) fn list(&self, request_id: Option<&str>) -> Vec<Value> {
        let mut jobs = self.jobs.lock().expect("job store");
        self.prune(&mut jobs);
        let mut selected = jobs.values().filter(|j| request_id.is_none_or(|r| j.request_id == r)).cloned().collect::<Vec<_>>();
        selected.sort_by(|a, b| b.created_at.cmp(&a.created_at).then(a.id.cmp(&b.id)));
        selected.iter().map(|job| {
            let mut summary = job.summary();
            // Listing never returns command arguments, output, or errors containing paths.
            summary.as_object_mut().expect("summary object").remove("result");
            summary
        }).collect()
    }

    #[cfg(test)]
    pub(super) fn with_limits(active: usize, retained: usize, ttl: Duration) -> Self {
        Self { jobs: Mutex::new(HashMap::new()), max_active: active, max_retained: retained, ttl }
    }
}

pub(super) fn error(code: &'static str, message: &str, retryable: bool) -> WorkspaceError {
    WorkspaceError::Tool { code, message: message.into(), category: "runtime", retryable }
}

fn unix_ms() -> u64 {
    SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_millis() as u64
}
