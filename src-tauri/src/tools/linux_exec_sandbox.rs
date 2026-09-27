//! Linux policy binding for the existing desktop dispatcher, not a new tool.
use super::{workspace::WorkspaceError, ToolContext};
use serde_json::{json, Value};
use tokio::process::Command;

pub(super) fn validate_arguments(args: &Value) -> Result<(), WorkspaceError> {
    for name in [
        "sandbox",
        "disable_sandbox",
        "sandbox_policy",
        "sandbox_enforced",
        "execution_boundary",
    ] {
        if args.get(name).is_some() {
            return Err(WorkspaceError::invalid_argument(
                "Sandbox policy is host-owned; model overrides are not accepted",
            ));
        }
    }
    Ok(())
}

pub(super) fn configure(ctx: &ToolContext, command: &mut Command) -> Result<(), WorkspaceError> {
    let sandbox = ctx
        .linux_sandbox
        .as_ref()
        .as_ref()
        .map_err(|_| failed("SANDBOX_REQUIRED"))?;
    // Never copy the desktop environment into model-controlled child code.
    // Toolchain access remains bounded by the kernel policy; HOME/TMPDIR are
    // workspace-local, not the owner's credential-bearing home or global /tmp.
    command
        .env_clear()
        .env("PATH", "/usr/bin:/bin")
        .env("HOME", ctx.workspace.root())
        .env("TMPDIR", ctx.workspace.root())
        .env("LANG", "C.UTF-8")
        .env("PYTHONUTF8", "1");
    sandbox
        .configure_command(command)
        .map_err(|_| failed("SANDBOX_SETUP_FAILED"))
}

/// Revalidate the existing opaque desktop ticket at the last parent-side point
/// before spawn. This does not construct the shared library's LocalAdmission.
/// Local host calls keep their trusted-context contract; every remote call must
/// pass the production two-phase ChatAuthorizer and execution-generation gate.
pub(super) fn admit(
    ctx: &ToolContext,
) -> Result<Option<crate::auth::LocalAdmissionPermit>, WorkspaceError> {
    let Some(req) = &ctx.remote_request else {
        return Ok(None);
    };
    let ticket = req
        .service
        .issue_local_admission_ticket(req, &["exec.run"], &ctx.execution_gate)
        .map_err(authority_error)?;
    req.service
        .commit_local_admission(req, &ctx.execution_gate, ticket)
        .map(Some)
        .map_err(authority_error)
}

fn authority_error(code: &'static str) -> WorkspaceError {
    WorkspaceError::Tool {
        code,
        message: "Local execution authority changed before child start".into(),
        category: "permission",
        retryable: false,
    }
}

pub(super) fn failed(code: &'static str) -> WorkspaceError {
    WorkspaceError::ToolDetails {
        code,
        message:
            "Required Linux isolation could not be established; no unsandboxed retry was attempted"
                .into(),
        category: "security",
        retryable: false,
        details: json!({"stage":"sandbox_setup", "sandbox_enforced":false,
            "execution_boundary":"unavailable", "child_process":false,
            "automatic_retry_allowed":false}),
    }
}

pub(super) fn environment(ctx: &ToolContext, mut value: Value) -> Value {
    // Pinning a root does not establish that a future pre-exec will succeed.
    // State the required policy, not a fabricated positive kernel probe.
    value["network_allowed"] = json!(false);
    value["landlock_enabled"] = Value::Null;
    value["filesystem_sandbox"] = json!({"available":null,"enforced":false,
        "required":true,"root_pinned":ctx.linux_sandbox.is_ok(),
        "default_scope":"workspace","host_scope_available":false,
        "checked_at":"each_child_spawn"});
    value["global_tmp_write"] = json!("denied");
    value["workspace_exec_available"] = Value::Null;
    value["workspace_exec_sandbox_enforced"] = Value::Null;
    value["workspace_exec_sandbox_required"] = json!(true);
    value["workspace_exec_boundary"] = json!("landlock_seccomp_required");
    value["warnings"] = json!(["Linux child execution requires kernel isolation; unsupported or privileged hosts fail closed. Network is denied, including in trusted mode."]);
    value
}

#[cfg(test)]
#[path = "linux_exec_sandbox_tests.rs"]
mod tests;
