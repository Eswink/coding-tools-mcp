//! Host-owned isolation bridge; model/cloud parameters never supply authority.
use super::ToolContext;
use serde_json::{json, Value};

pub(crate) fn required(ctx: &ToolContext) -> bool {
    cfg!(target_os = "linux") && ctx.remote_request.is_some()
}

/// An operation result only reports enforcement after a successful child start.
pub(crate) fn annotate(ctx: &ToolContext, result: &mut Value, child_started: bool) {
    let required = required(ctx);
    result["sandbox_required"] = json!(required);
    result["sandbox_enforced"] = json!(required && child_started);
    result["execution_boundary"] = json!(if required {
        "landlock_seccomp"
    } else {
        "policy_only"
    });
}

pub(crate) fn environment(ctx: &ToolContext, mut result: Value) -> Value {
    if required(ctx) {
        // Configuration is not an execution proof. Kernel availability is
        // checked again for every child and reported by that child's result.
        result["network_allowed"] = json!(false);
        result["workspace_exec_boundary"] = json!("landlock_seccomp_required");
        result["workspace_exec_sandbox_enforced"] = json!(false);
        result["filesystem_sandbox"] = json!({
            "available": Value::Null, "enforced": false, "required": true,
            "default_scope": "workspace", "host_scope_available": false,
            "support": "Linux x86_64; Landlock ABI >=3, openat2, close_range, seccomp",
            "availability_check": "per_child_before_exec"
        });
        result["global_tmp_write"] = json!("denied");
        result["warnings"] = json!([
            "Remote children require kernel isolation; no unsandboxed fallback.",
            "Network and writes outside the approved workspace are denied.",
            "Legacy tty=true is a bounded pipe session, not a native PTY."
        ]);
    }
    result
}

#[cfg(target_os = "linux")]
pub(crate) fn prepare(
    ctx: &ToolContext,
    command: &mut tokio::process::Command,
) -> Result<Option<crate::auth::LocalAdmissionPermit>, super::workspace::WorkspaceError> {
    let Some(req) = ctx.remote_request.as_ref() else {
        return Ok(None);
    };
    let failure = || super::workspace::WorkspaceError::Tool {
        code: "SANDBOX_SETUP_FAILED",
        message: "Required workspace isolation could not be established; command was not executed.".into(),
        category: "security",
        retryable: false,
    };
    ctx.linux_sandbox.as_ref().as_ref().map_err(|_| failure())?
        .configure_command(command).map_err(|_| failure())?;
    // Revalidate at the actual worker start, not just when an asynchronous job
    // was queued. An opaque ticket cannot be supplied by remote parameters.
    let denied = |code| super::workspace::WorkspaceError::Tool {
        code,
        message: "Local execution authority changed before child start.".into(),
        category: "permission",
        retryable: false,
    };
    let ticket = req.service
        .issue_local_admission_ticket(req, &["exec.run"], &ctx.execution_gate)
        .map_err(denied)?;
    let permit = req.service
        .commit_local_admission(req, &ctx.execution_gate, ticket)
        .map_err(denied)?;
    Ok(Some(permit))
}

#[cfg(target_os = "linux")]
pub(crate) fn retain_admission(
    session: std::sync::Arc<super::session::ExecSession>,
    permit: Option<crate::auth::LocalAdmissionPermit>,
) {
    let Some(permit) = permit else { return; };
    tauri::async_runtime::spawn(async move {
        // Preserve established semantics: revoke/pause stops NEW work; an
        // admitted operation drains or is explicitly cancelled by its owner.
        // A failed/uncertain termination never releases the ownership fence.
        let _permit = permit;
        loop {
            session.refresh_status().await;
            if session.has_exited() {
                session.wait_for_readers().await;
                if session.snapshot(0)["process_may_be_running"] != true {
                    break;
                }
            }
            tokio::time::sleep(std::time::Duration::from_millis(25)).await;
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn local_diagnostics_do_not_claim_kernel_enforcement() {
        let root = tempfile::tempdir().unwrap();
        let harness = tempfile::tempdir().unwrap();
        let ctx = ToolContext::for_test(root.path().into(), harness.path().into()).unwrap();
        let mut value = json!({});
        annotate(&ctx, &mut value, false);
        assert_eq!(value["sandbox_enforced"], false);
        assert_eq!(value["sandbox_required"], false);
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn background_context_retains_identical_pinned_policy() {
        let root = tempfile::tempdir().unwrap();
        let harness = tempfile::tempdir().unwrap();
        let ctx = ToolContext::for_test(root.path().into(), harness.path().into()).unwrap();
        assert!(std::sync::Arc::ptr_eq(
            &ctx.linux_sandbox, &ctx.background_snapshot().linux_sandbox
        ));
    }
}
