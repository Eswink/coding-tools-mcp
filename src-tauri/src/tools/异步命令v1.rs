//! Ordinary MCP tool polling, independent of a long-lived HTTP request.
//! This is not a declaration of the protocol-level MCP Tasks capability.
use std::sync::Arc;
use std::time::Duration;

use serde_json::{json, Value};
use sha2::{Digest, Sha256};

use crate::tools::context::ToolContext;
use crate::tools::workspace::{tool_ok, WorkspaceError};

#[path = "异步命令状态v1.rs"]
mod state;
#[path = "异步命令协议v1.rs"]
mod protocol;
use state::{Job, Status, PAGE_BYTES};
pub use state::ExecTaskStore;
pub use protocol::input_schema;

fn object<'a>(args: &'a Value, allowed: &[&str]) -> Result<&'a serde_json::Map<String, Value>, WorkspaceError> {
    let obj = args.as_object().ok_or_else(|| WorkspaceError::invalid_argument("arguments must be an object"))?;
    if obj.keys().any(|key| !allowed.contains(&key.as_str())) {
        return Err(WorkspaceError::invalid_argument("unexpected async execution argument"));
    }
    Ok(obj)
}

fn text<'a>(args: &'a Value, key: &str) -> Result<&'a str, WorkspaceError> {
    args.get(key).and_then(Value::as_str).filter(|s| !s.trim().is_empty())
        .ok_or_else(|| WorkspaceError::invalid_argument(format!("{key} must be a non-empty string")))
}

fn number(args: &Value, key: &str, default: u64, min: u64, max: u64) -> Result<u64, WorkspaceError> {
    let n = match args.get(key) {
        None => default,
        Some(value) => value.as_u64().ok_or_else(|| WorkspaceError::invalid_argument(format!("{key} must be an unsigned integer")))?,
    };
    if n < min || n > max { return Err(WorkspaceError::invalid_argument(format!("{key} out of range [{min}, {max}]"))); }
    Ok(n)
}

pub fn start(ctx: &ToolContext, args: &Value) -> Result<Value, WorkspaceError> {
    object(args, &["cmd", "request_id", "workdir", "timeout_ms", "confirm", "filesystem_scope", "reason"])?;
    let request_id = text(args, "request_id")?;
    if request_id.len() > 128 || request_id.chars().any(char::is_control) {
        return Err(WorkspaceError::invalid_argument("request_id must be 1..128 UTF-8 bytes without control characters"));
    }
    let cmd = text(args, "cmd")?;
    let timeout_ms = number(args, "timeout_ms", 600_000, 1, 600_000)?;
    if args.get("confirm").is_some_and(|v| !v.is_boolean()) {
        return Err(WorkspaceError::invalid_argument("confirm must be boolean"));
    }
    for key in ["workdir", "filesystem_scope", "reason"] {
        if args.get(key).is_some_and(|v| !v.is_string()) {
            return Err(WorkspaceError::invalid_argument(format!("{key} must be a string")));
        }
    }
    let cwd = ctx.workspace.resolve_existing(args.get("workdir").and_then(Value::as_str).unwrap_or("."))?;
    if !cwd.path.is_dir() { return Err(WorkspaceError::not_a_directory("workdir is not a directory")); }
    let fingerprint = format!("{:x}", Sha256::digest(serde_json::to_vec(&json!({
        "cmd": cmd, "cwd": cwd.path, "timeout_ms": timeout_ms,
    })).expect("serializable command")));
    let (job, created) = ctx.exec_tasks.reserve(request_id, &fingerprint, timeout_ms)?;
    if created {
        let background = ctx.background_snapshot();
        let mut command = args.clone();
        command.as_object_mut().expect("validated object").remove("request_id");
        command["workdir"] = json!(cwd.display);
        command["timeout_ms"] = json!(timeout_ms);
        command["yield_time_ms"] = json!(0);
        command["max_output_bytes"] = json!(1024);
        let worker_job = job.clone();
        tauri::async_runtime::spawn_blocking(move || {
            let outcome = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                run(&background, &worker_job, &command);
            }));
            if outcome.is_err() {
                // A failed worker must never leave the public task permanently "running".
                let session = worker_job.data.lock().ok().and_then(|d| d.session.clone());
                if let Some(session) = session {
                    tauri::async_runtime::block_on(session.kill_and_wait());
                }
                worker_job.finish(Status::Failed, json!({"command_ok": false,
                    "error": {"code": "EXEC_TASK_WORKER_FAILED", "message": "Execution worker failed; inspect workspace before retrying"}}));
            }
        });
    }
    let mut summary = job.summary();
    summary["deduplicated"] = json!(!created);
    Ok(tool_ok(summary))
}

fn run(ctx: &ToolContext, job: &Arc<Job>, args: &Value) {
    {
        let mut data = job.data.lock().expect("job state");
        if data.cancel_requested {
            drop(data);
            job.finish(Status::Cancelled, json!({"command_ok": false, "termination_reason": "cancelled_before_start"}));
            return;
        }
        data.status = Status::Running;
    }
    // Keep ALL policy/baseline/operation logging in the one shared execution dispatcher.
    let result = crate::tools::call_tool(ctx, "exec_command", args);
    let session = result.get("session_id").and_then(Value::as_str)
        .and_then(|id| ctx.sessions.get(id).ok());
    let Some(session) = session else {
        let status = if result.get("command_ok").and_then(Value::as_bool) == Some(true) {
            Status::Succeeded
        } else { Status::Failed };
        job.finish(status, result);
        return;
    };
    job.data.lock().expect("job state").session = Some(session.clone());
    // Noninteractive tasks cannot supply stdin. Close it so read-to-EOF programs do not hang.
    tauri::async_runtime::block_on(async {
        session.stdin.lock().await.take();
        session.mark_stdin_closed();
    });
    loop {
        tauri::async_runtime::block_on(session.refresh_status());
        if session.has_exited() { break; }
        if job.data.lock().expect("job state").cancel_requested {
            session.mark_termination_reason("killed");
            tauri::async_runtime::block_on(session.kill_and_wait());
            break;
        }
        std::thread::sleep(Duration::from_millis(50));
    }
    tauri::async_runtime::block_on(session.wait_for_readers());
    let mut final_result = session.snapshot(0);
    final_result["output_complete"] = json!(session.readers_completed());
    let status = match final_result["termination_reason"].as_str() {
        Some("timeout") => Status::TimedOut,
        Some("killed") => Status::Cancelled,
        _ if final_result["command_ok"] == true => Status::Succeeded,
        _ => Status::Failed,
    };
    if let Some(operation) = result.get("operation_id") { final_result["operation_id"] = operation.clone(); }
    job.finish(status, final_result);
    // Job owns the bounded buffers until its TTL; remove the legacy session map entry.
    ctx.sessions.remove(&session.session_id);
}

pub fn get(ctx: &ToolContext, args: &Value) -> Result<Value, WorkspaceError> {
    object(args, &["job_id", "stdout_cursor", "stderr_cursor", "limit"])?;
    let job = ctx.exec_tasks.get(text(args, "job_id")?)?;
    let out = number(args, "stdout_cursor", 0, 0, u64::MAX)?;
    let err = number(args, "stderr_cursor", 0, 0, u64::MAX)?;
    let limit = number(args, "limit", 4096, 1, PAGE_BYTES)?;
    let mut result = job.summary();
    result["stdout"] = job.output("stdout", out, limit)?;
    result["stderr"] = job.output("stderr", err, limit)?;
    Ok(tool_ok(result))
}

pub fn list(ctx: &ToolContext, args: &Value) -> Result<Value, WorkspaceError> {
    object(args, &["request_id"])?;
    let filter = if args.get("request_id").is_some() { Some(text(args, "request_id")?) } else { None };
    Ok(tool_ok(json!({"jobs": ctx.exec_tasks.list(filter), "recovery_scope": "service_instance",
        "restart_recoverable": false, "max_active": 4, "max_retained": 32})))
}

pub fn cancel(ctx: &ToolContext, args: &Value) -> Result<Value, WorkspaceError> {
    object(args, &["job_id"])?;
    let job = ctx.exec_tasks.get(text(args, "job_id")?)?;
    {
        let mut data = job.data.lock().expect("job state");
        if !data.status.terminal() {
            data.cancel_requested = true;
            data.status = Status::Cancelling;
        }
    }
    Ok(tool_ok(job.summary()))
}

#[cfg(test)]
#[path = "异步命令回归v1.rs"]
mod tests;

#[cfg(test)]
#[path = "异步命令传输v1.rs"]
mod transport_tests;
