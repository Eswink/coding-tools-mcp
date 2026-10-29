//! Host-owned isolation bridge; model/cloud parameters never supply authority.
use super::ToolContext;
use serde_json::{json, Value};

pub(crate) fn required(ctx: &ToolContext) -> bool {
    cfg!(target_os = "linux") && ctx.remote_request.is_some()
}

/// Permission modes that already grant the user's default developer
/// permissions. `safe` (安全受限) and any unknown mode stay fail-closed.
/// Accurate per the approval path: the chat session grant (exec.run scope) is
/// approved locally once; individual gateway commands are not prompted again.
pub(crate) const WINDOWS_GATEWAY_EXEC_APPROVAL_WARNING: &str =
    "Session authorization (exec.run scope) is still required; individual commands are not separately approved and are subject only to the command policy of the selected permission mode.";
const WINDOWS_UNSANDBOXED_MODES: &[&str] = &["trusted", "dangerous"];

/// Windows gateway exec has no sandbox and runs with user default permissions.
/// User decision 2026-10-29 (Q3 = B): only the Windows remote `exec.run` path
/// is opened; a user-selected restricted mode is still rejected.
fn windows_unsandboxed_for(windows: bool, ctx: &ToolContext) -> bool {
    windows
        && WINDOWS_UNSANDBOXED_MODES.contains(&ctx.permission_mode.as_str())
        && ctx.policy.permission_mode == ctx.permission_mode
}

/// Remote `exec.run` platform gate, evaluated before any admission ticket.
/// Linux keeps its mandatory per-child kernel isolation; other non-Windows
/// platforms keep the unchanged `SANDBOX_REQUIRED` refusal.
pub(crate) fn remote_exec_gate(ctx: &ToolContext) -> Result<(), &'static str> {
    remote_exec_gate_for(cfg!(target_os = "linux"), cfg!(windows), ctx)
}

fn remote_exec_gate_for(linux: bool, windows: bool, ctx: &ToolContext) -> Result<(), &'static str> {
    if linux || windows_unsandboxed_for(windows, ctx) {
        Ok(())
    } else {
        Err("SANDBOX_REQUIRED")
    }
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

pub(crate) fn environment(ctx: &ToolContext, result: Value) -> Value {
    environment_for(cfg!(target_os = "linux"), cfg!(windows), ctx, result)
}

fn environment_for(linux: bool, windows: bool, ctx: &ToolContext, mut result: Value) -> Value {
    if ctx.remote_request.is_some() && !linux && windows_unsandboxed_for(windows, ctx) {
        // Report exactly what remote_exec_gate admits: no OS isolation.
        result["workspace_exec_available"] = json!(true);
        result["workspace_exec_boundary"] = json!("unsandboxed_user_default_permissions");
        result["workspace_exec_sandbox_enforced"] = json!(false);
        result["filesystem_sandbox"] = json!({
            "available": false, "enforced": false, "required": false,
            "default_scope": "workspace", "host_scope_available": false,
            "support": "Windows gateway exec has no sandbox and runs with user default permissions"
        });
        result["warnings"] = json!([
            "Windows gateway exec has no sandbox and runs with user default permissions.",
            WINDOWS_GATEWAY_EXEC_APPROVAL_WARNING
        ]);
        return result;
    }
    if ctx.remote_request.is_some() && !linux {
        // Match NativeToolHost's actual fail-closed admission rule. A local
        // policy-only process path does not establish remote OS isolation.
        result["workspace_exec_available"] = json!(false);
        result["workspace_exec_boundary"] = json!("sandbox_unavailable");
        result["workspace_exec_unavailable_reason"] = json!("SANDBOX_REQUIRED");
        result["workspace_exec_sandbox_enforced"] = json!(false);
        result["network_allowed"] = json!(false);
        result["global_tmp_write"] = json!("denied");
        result["filesystem_sandbox"] = json!({
            "available": false, "enforced": false, "required": true,
            "default_scope": "workspace", "host_scope_available": false,
            "support": "Mandatory remote execution isolation is unavailable on this platform"
        });
        result["warnings"] = json!([
            "Remote child execution is unavailable because mandatory OS isolation is not implemented.",
            "No policy-only or unsandboxed fallback is permitted."
        ]);
        return result;
    }
    if linux && ctx.remote_request.is_some() {
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
        message: "Required workspace isolation could not be established; command was not executed."
            .into(),
        category: "security",
        retryable: false,
    };
    ctx.linux_sandbox
        .as_ref()
        .as_ref()
        .map_err(|_| failure())?
        .configure_command(command)
        .map_err(|_| failure())?;
    // Revalidate at the actual worker start, not just when an asynchronous job
    // was queued. An opaque ticket cannot be supplied by remote parameters.
    let denied = |code| super::workspace::WorkspaceError::Tool {
        code,
        message: "Local execution authority changed before child start.".into(),
        category: "permission",
        retryable: false,
    };
    let ticket = req
        .service
        .issue_local_admission_ticket(req, &["exec.run"], &ctx.execution_gate)
        .map_err(denied)?;
    let permit = req
        .service
        .commit_local_admission(req, &ctx.execution_gate, ticket)
        .map_err(denied)?;
    Ok(Some(permit))
}

#[cfg(target_os = "linux")]
pub(crate) fn retain_admission(
    session: std::sync::Arc<super::session::ExecSession>,
    permit: Option<crate::auth::LocalAdmissionPermit>,
) {
    let Some(permit) = permit else {
        return;
    };
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

    #[test]
    fn local_environment_preserves_policy_only_diagnostics() {
        let root = tempfile::tempdir().unwrap();
        let harness = tempfile::tempdir().unwrap();
        let ctx = ToolContext::for_test(root.path().into(), harness.path().into()).unwrap();
        let original = json!({
            "workspace_exec_available": true,
            "workspace_exec_boundary": "policy_only",
            "workspace_exec_sandbox_enforced": false,
            "network_allowed": true
        });
        assert_eq!(environment(&ctx, original.clone()), original);
    }

    fn remote_ctx(mode: &str) -> (tempfile::TempDir, tempfile::TempDir, ToolContext) {
        let root = tempfile::tempdir().unwrap();
        let harness = tempfile::tempdir().unwrap();
        let mut ctx = ToolContext::for_test(root.path().into(), harness.path().into()).unwrap();
        ctx.permission_mode = mode.into();
        ctx.policy.permission_mode = mode.into();
        ctx.remote_request = Some(crate::auth::chat::RemoteRequest::unresolved("q3b"));
        (root, harness, ctx)
    }

    // Q3 = B (2026-10-29): platform matrix of the remote exec.run gate.
    #[test]
    fn windows_gateway_exec_gate_admits_default_modes_and_rejects_restricted() {
        for mode in ["trusted", "dangerous"] {
            let (_r, _h, ctx) = remote_ctx(mode);
            assert_eq!(remote_exec_gate_for(false, true, &ctx), Ok(()), "{mode}");
        }
        for mode in ["safe", "", "unknown", "Trusted"] {
            let (_r, _h, ctx) = remote_ctx(mode);
            assert_eq!(
                remote_exec_gate_for(false, true, &ctx),
                Err("SANDBOX_REQUIRED"),
                "{mode}"
            );
        }
        // A policy/context mode mismatch never opens the unsandboxed path.
        let (_r, _h, mut ctx) = remote_ctx("trusted");
        ctx.policy.permission_mode = "safe".into();
        assert_eq!(
            remote_exec_gate_for(false, true, &ctx),
            Err("SANDBOX_REQUIRED")
        );
    }

    #[test]
    fn linux_and_other_platform_gate_behaviour_is_unchanged() {
        for mode in ["trusted", "dangerous", "safe", "unknown"] {
            let (_r, _h, ctx) = remote_ctx(mode);
            // Linux keeps admitting into its mandatory per-child sandbox.
            assert_eq!(remote_exec_gate_for(true, false, &ctx), Ok(()), "{mode}");
            // macOS/other non-Windows keeps the legacy refusal in every mode.
            assert_eq!(
                remote_exec_gate_for(false, false, &ctx),
                Err("SANDBOX_REQUIRED"),
                "{mode}"
            );
        }
    }

    #[test]
    fn windows_default_mode_environment_reports_no_sandbox() {
        let (_r, _h, ctx) = remote_ctx("trusted");
        let value = environment_for(false, true, &ctx, json!({"network_allowed": true}));
        assert_eq!(value["workspace_exec_available"], true);
        assert_eq!(
            value["workspace_exec_boundary"],
            "unsandboxed_user_default_permissions"
        );
        assert_eq!(value["workspace_exec_sandbox_enforced"], false);
        assert_eq!(value["filesystem_sandbox"]["required"], false);
        assert_eq!(value["network_allowed"], true);
        assert!(value["warnings"][0]
            .as_str()
            .unwrap()
            .contains("no sandbox"));
    }

    #[test]
    fn windows_default_mode_environment_warnings_are_exact() {
        for mode in ["trusted", "dangerous"] {
            let (_r, _h, ctx) = remote_ctx(mode);
            let value = environment_for(false, true, &ctx, json!({}));
            assert_eq!(
                value["warnings"],
                json!([
                    "Windows gateway exec has no sandbox and runs with user default permissions.",
                    "Session authorization (exec.run scope) is still required; individual commands are not separately approved and are subject only to the command policy of the selected permission mode."
                ]),
                "{mode}"
            );
        }
    }

    #[test]
    fn windows_restricted_mode_environment_is_the_identical_legacy_refusal() {
        let (_r, _h, legacy) = remote_ctx("trusted");
        let expected = environment_for(false, false, &legacy, json!({}));
        let (_r2, _h2, ctx) = remote_ctx("safe");
        let value = environment_for(false, true, &ctx, json!({}));
        assert_eq!(value, expected);
        assert_eq!(
            value["workspace_exec_unavailable_reason"],
            "SANDBOX_REQUIRED"
        );
        assert_eq!(value["workspace_exec_available"], false);
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn background_context_retains_identical_pinned_policy() {
        let root = tempfile::tempdir().unwrap();
        let harness = tempfile::tempdir().unwrap();
        let ctx = ToolContext::for_test(root.path().into(), harness.path().into()).unwrap();
        assert!(std::sync::Arc::ptr_eq(
            &ctx.linux_sandbox,
            &ctx.background_snapshot().linux_sandbox
        ));
    }
}
