//! A1 C2b: the native `subagent_*` handlers and the worker `change_summary`
//! (SPEC-A1 v4 §2.1). Remote callers reach these only after the chat-domain
//! interceptor proved `agents.manage` plus the tool's second scope.
use super::{
    cancel, discard, error_value, spawn_and_complete, state_error, status, WorkerError,
    WorkerRecord, WorkerState,
};
use crate::tools::{
    workspace::{tool_ok, WorkspaceError},
    ToolContext,
};
use serde_json::{json, Map, Value};

/// A1 C7-3: the bounded wait for an acknowledged projection naming a new worker.
const PROJECTION_WAIT: std::time::Duration = std::time::Duration::from_secs(3);

fn invalid(message: &'static str) -> WorkerError {
    super::invalid(message)
}
fn state_label(state: WorkerState) -> &'static str {
    match state {
        WorkerState::Creating => "creating",
        WorkerState::Ready => "ready",
        WorkerState::Cancelled => "cancelled",
        WorkerState::Failed => "failed",
        WorkerState::PendingCleanup => "pending_cleanup",
        WorkerState::Discarded => "discarded",
        WorkerState::IntegratePending => "integrate_pending",
        WorkerState::Integrated => "integrated",
    }
}
/// The bounded public view. Worktree ids and paths are never exposed.
pub(crate) fn view(record: &WorkerRecord) -> Value {
    // Read-only: an expired request shows as closed without writing the store.
    let record = &super::integration::effective(record, super::now());
    let integration = record
        .integrations
        .last()
        .map_or(Value::Null, super::integration::view);
    json!({
        "integration": integration,
        "worker_id": record.worker_id.as_str(),
        "label": record.label,
        "state": state_label(record.state),
        "base_head": record.base_head,
        "cwd": record.cwd,
        "created_at": record.created_at,
        "last_activity_at": record.last_activity_at,
        // Diff accounting arrives with collect (C5).
        "changed_files": null,
    })
}

/// Closed-schema check shared by local and remote callers (the cloud gateway
/// validates the same schema; native callers are checked here).
fn object<'a>(
    args: &'a Value,
    allowed: &[&str],
    required: &[&str],
) -> Result<&'a Map<String, Value>, WorkerError> {
    let obj = args
        .as_object()
        .ok_or_else(|| invalid("Arguments must be an object."))?;
    if obj.keys().any(|k| !allowed.contains(&k.as_str())) {
        return Err(invalid("Unknown argument."));
    }
    if required.iter().any(|k| !obj.contains_key(*k)) {
        return Err(invalid("Missing required argument."));
    }
    Ok(obj)
}
fn text<'a>(obj: &'a Map<String, Value>, key: &str) -> Result<Option<&'a str>, WorkerError> {
    match obj.get(key) {
        None => Ok(None),
        Some(Value::String(v)) => Ok(Some(v)),
        Some(_) => Err(invalid("Argument must be a string.")),
    }
}
fn hex(value: Option<&str>, width: usize) -> Result<(), WorkerError> {
    match value {
        Some(v)
            if v.len() == width
                && v.bytes()
                    .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)) =>
        {
            Ok(())
        }
        None => Ok(()),
        Some(_) => Err(invalid("Invalid identifier.")),
    }
}

pub(crate) fn call(ctx: &ToolContext, name: &str, args: &Value) -> Value {
    match run(ctx, name, args) {
        Ok(value) => tool_ok(value),
        Err(error) => error_value(&error),
    }
}

fn run(ctx: &ToolContext, name: &str, args: &Value) -> Result<Value, WorkerError> {
    if ctx.worker.is_some() {
        // A worker never manages workers (no nesting, v4 §1.4.2).
        return Err(state_error());
    }
    match name {
        "subagent_spawn" => {
            let obj = object(args, &["request_id", "label", "base"], &["request_id"])?;
            let request_id = text(obj, "request_id")?.unwrap_or_default();
            let label = text(obj, "label")?.unwrap_or_default();
            if text(obj, "base")?.is_some_and(|b| b != "HEAD") {
                return Err(invalid("base must be HEAD."));
            }
            let (record, created) = spawn_and_complete(ctx, request_id, label)?;
            let mut out = json!({"worker": view(&record), "deduplicated": !created});
            // A1 C7-3 (SPEC v5.6 §3.3): a cloud caller learns whether the gateway
            // already accepted a projection naming the worker (bounded 3 s wait;
            // immediately "pending" with no live session). Native UI: no field.
            if ctx.remote_request.is_some() {
                let applied = super::projection_bus::wait_applied(
                    &ctx.host,
                    record.worker_id.as_str(),
                    PROJECTION_WAIT,
                );
                out["projection"] = json!(if applied { "applied" } else { "pending" });
            }
            Ok(out)
        }
        "subagent_status" => {
            let obj = object(args, &["worker_id"], &[])?;
            let id = text(obj, "worker_id")?;
            let records = status(ctx, id)?;
            // NB-a: the rollback window is evaluated read-only here.
            // C5-nit (Grok review of 209bcfea, item 3): an unreadable journal
            // (e.g. corrupt) does not hide the workers; only each integration's
            // `rollback` carries the error.
            let windows = super::integration::rollback_views(ctx, &records);
            let mut workers: Vec<Value> = records.iter().map(view).collect();
            for worker in &mut workers {
                let integration = &mut worker["integration"];
                if integration.is_null() {
                    continue;
                }
                let id = integration["integration_id"].as_str().unwrap_or_default();
                match &windows {
                    Ok(windows) => {
                        if let Some((_, window)) = windows.iter().find(|(i, _)| i == id) {
                            integration["rollback"] = window.clone();
                        }
                    }
                    Err(error) => {
                        integration["rollback"] = json!({
                            "available": false,
                            "reason": "journal_unavailable",
                            "error": {"code": error.code(), "message": error.message()},
                        });
                    }
                }
            }
            Ok(json!({"workers": workers}))
        }
        "subagent_cancel" | "subagent_discard" => {
            let obj = object(args, &["worker_id"], &["worker_id"])?;
            let id = text(obj, "worker_id")?.unwrap_or_default();
            if name == "subagent_cancel" {
                // A1 C2-a (v5 §5.2): cancel also stops the worker's background exec.
                let (record, killed) = cancel(ctx, id)?;
                return Ok(json!({"worker": view(&record), "killed_tasks": killed}));
            }
            let record = discard(ctx, id)?;
            Ok(json!({"worker": view(&record)}))
        }
        "subagent_collect" => {
            let obj = object(args, &["worker_id", "max_bytes", "cursor"], &["worker_id"])?;
            hex(text(obj, "worker_id")?, 32)?;
            if obj
                .get("max_bytes")
                .is_some_and(|v| v.as_u64().is_none_or(|n| !(256..=4096).contains(&n)))
            {
                return Err(invalid("max_bytes must be 256..4096."));
            }
            let max_bytes = obj
                .get("max_bytes")
                .and_then(Value::as_u64)
                .map_or(super::integrate::MAX_CHUNK, |n| n as usize);
            let id = text(obj, "worker_id")?.unwrap_or_default();
            super::integrate::collect(ctx, id, max_bytes, text(obj, "cursor")?)
        }
        "subagent_integrate" => {
            let obj = object(
                args,
                &["worker_id", "diff_sha256", "request_id"],
                &["worker_id", "diff_sha256", "request_id"],
            )?;
            hex(text(obj, "worker_id")?, 32)?;
            hex(text(obj, "diff_sha256")?, 64)?;
            super::integration::request(
                ctx,
                text(obj, "worker_id")?.unwrap_or_default(),
                text(obj, "diff_sha256")?.unwrap_or_default(),
                text(obj, "request_id")?.unwrap_or_default(),
            )
        }
        "subagent_rollback" => {
            let obj = object(
                args,
                &["integration_id", "request_id"],
                &["integration_id", "request_id"],
            )?;
            hex(text(obj, "integration_id")?, 32)?;
            super::integration::rollback_request(
                ctx,
                text(obj, "integration_id")?.unwrap_or_default(),
                text(obj, "request_id")?.unwrap_or_default(),
            )
        }
        _ => Err(invalid("Unknown subagent tool.")),
    }
}

/// `change_summary` on a worker context: the worker's own record and a bounded
/// git status of its worktree. Main-task ids are refused; harness task state,
/// events and baselines are never read (v4 §1.4.3).
pub(crate) fn worker_change_summary(ctx: &ToolContext, args: &Value) -> Value {
    let Some(binding) = ctx.worker.as_ref() else {
        return error_value(&state_error());
    };
    if args.as_object().is_none_or(|obj| !obj.is_empty()) {
        return error_value(&invalid(
            "A worker change_summary accepts no task_id or change_id.",
        ));
    }
    let record = match status(ctx, Some(binding.worker_id.as_str())) {
        Ok(mut records) if !records.is_empty() => records.remove(0),
        Ok(_) => return error_value(&super::not_owned()),
        Err(error) => return error_value(&error),
    };
    let mut warnings = Vec::new();
    let git_status = match crate::tools::git::git_status(&ctx.workspace, &json!({})) {
        Ok(mut value) => {
            if let Some(obj) = value.as_object_mut() {
                obj.remove("ok");
            }
            value
        }
        Err(error) => {
            warnings.push(json!({"code": error_code(&error)}));
            Value::Null
        }
    };
    tool_ok(json!({
        "worker_id": record.worker_id.as_str(),
        "label": record.label,
        "state": state_label(record.state),
        "base_head": record.base_head,
        "cwd": record.cwd,
        "git_status": git_status,
        // A1 C3 (v4 §1.4.3): the worker's own bounded ops log, oldest first.
        "operations": record.ops,
        "operations_total": record.ops_seq,
        "warnings": warnings,
    }))
}
fn error_code(error: &WorkspaceError) -> Value {
    error.to_error_value()["code"].clone()
}
