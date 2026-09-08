//! Versioned, encrypted-at-rest snapshots; never restart commands from records.
use std::sync::{atomic::AtomicBool, Mutex};
use std::time::{Duration, Instant};
use base64::{engine::general_purpose::STANDARD, Engine};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use super::state::{error, unix_ms, Job, JobData, Status, RETAIN_BYTES};
use crate::tools::workspace::WorkspaceError;

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Record {
    version: u32, id: String, request_id: String, fingerprint: String,
    timeout_ms: u64, created_at: u64, completed_at: Option<u64>, elapsed_ms: u64,
    status: Status, cancel_requested: bool, result: Option<Value>,
    stdout: String, stdout_total: usize, stderr: String, stderr_total: usize,
}

pub(super) fn snapshot(job: &Job) -> Value {
    let d = job.data.lock().expect("job state");
    let (stdout, ot) = d.session.as_ref().map(|s| s.retained_stream_bytes("stdout"))
        .unwrap_or_else(|| d.native_stdout.clone());
    let (stderr, et) = d.session.as_ref().map(|s| s.retained_stream_bytes("stderr"))
        .unwrap_or_else(|| d.native_stderr.clone());
    serde_json::to_value(Record {
        version: 1, id: job.id.clone(), request_id: job.request_id.clone(),
        fingerprint: job.fingerprint.clone(), timeout_ms: job.timeout_ms,
        created_at: job.created_at, completed_at: d.completed_at,
        elapsed_ms: job.restored_elapsed.unwrap_or_else(|| d.finished.unwrap_or_else(Instant::now)
            .duration_since(job.started).as_millis() as u64),
        status: d.status, cancel_requested: d.cancel_requested, result: d.result.clone(),
        stdout: STANDARD.encode(stdout), stdout_total: ot,
        stderr: STANDARD.encode(stderr), stderr_total: et,
    }).expect("task record is JSON")
}

pub(super) fn restore(value: Value) -> Result<Job, WorkspaceError> {
    let r: Record = serde_json::from_value(value).map_err(|_| invalid())?;
    if r.version != 1 || uuid::Uuid::parse_str(&r.id).map(|u| u.to_string()).ok().as_ref() != Some(&r.id)
        || r.request_id.is_empty() || r.request_id.len() > 128 || r.request_id.chars().any(char::is_control)
        || r.fingerprint.is_empty() || r.fingerprint.len() > 128 || r.timeout_ms == 0 || r.timeout_ms > 86_400_000
        || r.stdout.len() > RETAIN_BYTES.div_ceil(3) * 4 || r.stderr.len() > RETAIN_BYTES.div_ceil(3) * 4 {
        return Err(invalid());
    }
    let stdout = STANDARD.decode(&r.stdout).map_err(|_| invalid())?;
    let stderr = STANDARD.decode(&r.stderr).map_err(|_| invalid())?;
    if stdout.len() > RETAIN_BYTES || stderr.len() > RETAIN_BYTES
        || stdout.len() > r.stdout_total || stderr.len() > r.stderr_total
        || (r.status.terminal() != r.completed_at.is_some())
        || (r.status.terminal() && !r.result.as_ref().is_some_and(Value::is_object))
        || r.result.as_ref().is_some_and(|value| !value.is_object()) { return Err(invalid()); }
    let interrupted = !r.status.terminal() || r.result.as_ref().is_some_and(|v| v["process_may_be_running"] == true);
    let completed_at = r.completed_at.unwrap_or_else(unix_ms);
    let age = Duration::from_millis(unix_ms().saturating_sub(completed_at));
    let now = Instant::now();
    Ok(Job {
        id: r.id, request_id: r.request_id, fingerprint: r.fingerprint,
        timeout_ms: r.timeout_ms, created_at: r.created_at, started: now,
        persistent: true, restored_elapsed: Some(r.elapsed_ms), persistence_failed: AtomicBool::new(false),
        data: Mutex::new(JobData {
            status: if interrupted { Status::Interrupted } else { r.status },
            cancel_requested: r.cancel_requested, session: None,
            result: if interrupted { Some(json!({"command_ok":false,"output_complete":false,
                "process_may_be_running":true,"termination_reason":"application_interrupted",
                "message":"Previous executor is unavailable. Inspect local processes; never automatically repeat this command."})) } else { r.result },
            native_stdout: (stdout, r.stdout_total), native_stderr: (stderr, r.stderr_total),
            finished: Some(now.checked_sub(age.min(Duration::from_secs(3601))).unwrap_or(now)),
            completed_at: Some(completed_at),
        }),
    })
}

fn invalid() -> WorkspaceError {
    error("EXEC_TASK_RECORD_INVALID", "Task record is invalid or unsupported; preserved without re-executing commands", false)
}
