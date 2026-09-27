//! Linux-only adapter for the existing desktop authorization and session model.
//! This is not an authority issuer; cloud/model data cannot construct a permit.
use super::{context::ToolContext, workspace::WorkspaceError};
use crate::auth::LocalAdmissionPermit;
use serde_json::{json, Value};
use tokio::process::Command;

pub(crate) fn required(ctx: &ToolContext) -> bool {
    ctx.remote_request.is_some()
}

pub(crate) fn validate_arguments(ctx: &ToolContext, args: &Value) -> Result<(), WorkspaceError> {
    if !required(ctx) {
        return Ok(());
    }
    let object = args
        .as_object()
        .ok_or_else(|| WorkspaceError::invalid_argument("execution arguments must be an object"))?;
    const FIELDS: &[&str] = &[
        "cmd",
        "workdir",
        "cwd",
        "stdin",
        "timeout_ms",
        "max_output_bytes",
        "yield_time_ms",
        "tty",
        "filesystem_scope",
        "confirm",
        "reason",
    ];
    if object.keys().any(|key| !FIELDS.contains(&key.as_str())) {
        return Err(WorkspaceError::invalid_argument(
            "unsupported remote execution argument; isolation is host-owned",
        ));
    }
    Ok(())
}

/// Prepare the fixed kernel boundary, then commit the original local ticket
/// immediately before the caller spawns. Dropping a failed permit cannot spawn.
pub(crate) fn prepare(
    ctx: &ToolContext,
    command: &mut Command,
) -> Result<Option<LocalAdmissionPermit>, WorkspaceError> {
    let Some(request) = ctx.remote_request.as_ref() else {
        return Ok(None);
    };
    let policy = ctx.linux_sandbox.as_ref().map_err(|_| setup_error())?;
    let ticket = request
        .service
        .issue_local_admission_ticket(request, &["exec.run"], &ctx.execution_gate)
        .map_err(admission_error)?;
    policy
        .configure_command(command)
        .map_err(|_| setup_error())?;
    request
        .service
        .commit_local_admission(request, &ctx.execution_gate, ticket)
        .map(Some)
        .map_err(admission_error)
}

pub(crate) fn setup_error() -> WorkspaceError {
    WorkspaceError::ToolDetails {
        code: "SANDBOX_SETUP_FAILED",
        message: "Required Linux isolation is unavailable; no unsandboxed retry is permitted."
            .into(),
        category: "security",
        retryable: false,
        details: json!({
            "sandbox_required": true,
            "sandbox_enforced": false,
            "execution_boundary": "not_started",
            "recoverable": false,
            "child_process": false,
            "command_ok": false
        }),
    }
}

fn admission_error(code: &'static str) -> WorkspaceError {
    WorkspaceError::Tool {
        code,
        message: "Local execution admission changed or is unavailable.".into(),
        category: if code.starts_with("WORKSPACE_") {
            "availability"
        } else {
            "permission"
        },
        retryable: false,
    }
}

/// A requirement/configuration view, deliberately not a claim that a kernel
/// probe or a child execution has already succeeded.
pub(crate) fn environment(ctx: &ToolContext) -> Value {
    json!({
        "workspace": ctx.workspace.root_display(),
        "permission_mode": ctx.permission_mode,
        "network_allowed": false,
        "landlock_enabled": Value::Null,
        "filesystem_sandbox": {
            "available": Value::Null,
            "configured": ctx.linux_sandbox.is_ok(),
            "required": true,
            "enforced": false,
            "status": "checked_at_child_start",
            "default_scope": "workspace",
            "host_scope_available": false
        },
        "global_tmp_write": "denied",
        "workspace_exec_available": ctx.linux_sandbox.is_ok(),
        "workspace_exec_sandbox_required": true,
        "workspace_exec_sandbox_enforced": false,
        "workspace_exec_boundary": "linux_sandbox_required",
        "system_command_allowlist": ctx.policy.allowed_commands.iter().cloned().collect::<Vec<_>>(),
        "workspace_local_entries": {
            "enabled": ctx.policy.workspace_local_entries,
            "script_extensions": ctx.policy.workspace_script_extensions.iter().cloned().collect::<Vec<_>>(),
            "resolution": "workdir_first"
        },
        "allowed_commands": ctx.policy.allowed_commands.iter().cloned().collect::<Vec<_>>(),
        "warnings": [
            "Every remote child must establish Landlock/seccomp or fail closed.",
            "Runtime availability is checked at each child start; this response is not a successful kernel probe.",
            "Network and external caches/home directories are unavailable; TMPDIR is the working directory.",
            "The desktop tty flag retains its existing pipe-session API; native PTY is a separate runtime API."
        ]
    })
}
