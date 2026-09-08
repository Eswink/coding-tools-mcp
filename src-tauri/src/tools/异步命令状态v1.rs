use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use serde_json::{json, Value};
use serde::{Deserialize, Serialize};
use base64::{engine::general_purpose::STANDARD, Engine};
use uuid::Uuid;

use crate::tools::session::ExecSession;
use crate::tools::workspace::WorkspaceError;

pub(super) const RETAIN_BYTES: usize = 1_048_576;
pub(super) const PAGE_BYTES: u64 = 16_384;
const RESULT_TTL: Duration = Duration::from_secs(3600);

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub(super) enum Status {
    Queued,
    Running,
    Cancelling,
    Succeeded,
    Failed,
    TimedOut,
    Cancelled,
    Interrupted,
}

impl Status {
    pub fn terminal(self) -> bool {
        matches!(self, Self::Succeeded | Self::Failed | Self::TimedOut | Self::Cancelled | Self::Interrupted)
    }

    pub fn label(self) -> &'static str {
        match self {
            Self::Queued => "queued", Self::Running => "running",
            Self::Cancelling => "cancelling", Self::Succeeded => "succeeded",
            Self::Failed => "failed", Self::TimedOut => "timed_out", Self::Cancelled => "cancelled",
            Self::Interrupted => "interrupted",
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

impl JobData {
    pub(super) fn holds_capacity(&self) -> bool {
        !self.status.terminal()
            || self.result.as_ref().and_then(|r| r.get("process_may_be_running")) == Some(&Value::Bool(true))
    }
}

pub(super) struct Job {
    pub id: String,
    pub request_id: String,
    pub fingerprint: String,
    pub timeout_ms: u64,
    pub created_at: u64,
    pub started: Instant,
    pub persistent: bool,
    pub restored_elapsed: Option<u64>,
    pub persistence_failed: std::sync::atomic::AtomicBool,
    pub data: Mutex<JobData>,
}

impl Job {
    pub(super) fn new(request_id: String, fingerprint: String, timeout_ms: u64, persistent: bool) -> Self {
        Self {
            id: Uuid::new_v4().to_string(), request_id, fingerprint, timeout_ms,
            created_at: unix_ms(), started: Instant::now(), persistent, restored_elapsed: None,
            persistence_failed: std::sync::atomic::AtomicBool::new(false),
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
            "elapsed_ms": self.restored_elapsed.unwrap_or_else(|| d.finished.unwrap_or_else(Instant::now).duration_since(self.started).as_millis() as u64),
            "execution_timeout_ms": self.timeout_ms, "result_ttl_ms": RESULT_TTL.as_millis(),
            "poll_after_ms": if d.status.terminal() { 0 } else { 1000 },
            "command_ok": if d.status.terminal() { Some(d.status == Status::Succeeded) } else { None },
            "result": d.result,
            "recovery_scope": if self.persistent { "workspace_service" } else { "service_instance" },
            "restart_recoverable": self.persistent, "execution_survives_app_restart": false,
            "persistence_failed": self.persistence_failed.load(std::sync::atomic::Ordering::Acquire),
            "cancellation_scope": "process_tree",
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

pub(super) fn error(code: &'static str, message: &str, retryable: bool) -> WorkspaceError {
    WorkspaceError::Tool { code, message: message.into(), category: "runtime", retryable }
}

pub(super) fn unix_ms() -> u64 {
    SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_millis() as u64
}
