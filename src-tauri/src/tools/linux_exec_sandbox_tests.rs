use super::*;
use crate::tools::call_tool;
use std::sync::Arc;
use tempfile::TempDir;

fn context() -> (TempDir, TempDir, ToolContext) {
    let owner = tempfile::tempdir().unwrap();
    let root = owner.path().join("workspace");
    std::fs::create_dir(&root).unwrap();
    let harness = tempfile::tempdir().unwrap();
    let ctx = ToolContext::for_test(root, harness.path().to_path_buf()).unwrap();
    (owner, harness, ctx)
}
fn command(ctx: &ToolContext, cmd: &str) -> Value {
    call_tool(
        ctx,
        "exec_command",
        &json!({"cmd":cmd,"timeout_ms":10000,"yield_time_ms":10000}),
    )
}
fn script(ctx: &ToolContext, text: &str) {
    std::fs::write(ctx.workspace.root().join("probe.py"), text).unwrap();
}

#[test]
fn background_snapshots_reuse_the_exact_host_policy() {
    let (_owner, _harness, ctx) = context();
    let copy = ctx.background_snapshot();
    assert!(Arc::ptr_eq(&ctx.linux_sandbox, &copy.linux_sandbox));
}

#[test]
fn missing_host_policy_rejects_child_without_fallback() {
    let (_owner, _harness, mut ctx) = context();
    script(&ctx, "open('unexpected', 'w').write('x')\n");
    ctx.linux_sandbox = Arc::new(Err(coding_tools_local_agent::SandboxError {
        kind: coding_tools_local_agent::SandboxErrorKind::Unavailable,
    }));
    let result = command(&ctx, "python3 probe.py");
    assert_eq!(result["ok"], false, "{result}");
    assert_eq!(result["error"]["code"], "SANDBOX_REQUIRED", "{result}");
    assert!(!ctx.workspace.root().join("unexpected").exists());
}

#[test]
fn model_cannot_override_host_sandbox_policy() {
    let (_owner, _harness, ctx) = context();
    for key in [
        "sandbox",
        "disable_sandbox",
        "sandbox_policy",
        "sandbox_enforced",
        "execution_boundary",
    ] {
        let mut args = json!({"cmd":"python3 -c \"print('unexpected')\""});
        args[key] = json!(false);
        let result = call_tool(&ctx, "exec_command", &args);
        assert_eq!(result["ok"], false, "{key}: {result}");
        assert_eq!(
            result["error"]["code"], "INVALID_ARGUMENT",
            "{key}: {result}"
        );
        assert!(result["session_id"].is_null());
    }
}

#[test]
fn approved_host_execution_is_isolated_and_builtins_are_not_mislabelled() {
    let (_owner, _harness, ctx) = context();
    script(&ctx, "print('inside')\n");
    let result = command(&ctx, "python3 probe.py");
    assert_eq!(result["command_ok"], true, "{result}");
    assert_eq!(result["sandbox_enforced"], true, "{result}");
    assert_eq!(result["execution_boundary"], "landlock_seccomp", "{result}");
    let builtin = command(&ctx, "echo inside");
    assert_eq!(builtin["child_process"], false, "{builtin}");
    assert_eq!(builtin["sandbox_enforced"], false, "{builtin}");
}

#[test]
fn desktop_environment_is_not_inherited_by_the_child() {
    let (_owner, _harness, ctx) = context();
    script(
        &ctx,
        "import json, os\nprint(json.dumps(dict(os.environ)))\n",
    );
    let result = command(&ctx, "python3 probe.py");
    assert_eq!(result["command_ok"], true, "{result}");
    let env: Value = serde_json::from_str(result["stdout"].as_str().unwrap()).unwrap();
    for key in env.as_object().unwrap().keys() {
        assert!(
            ["HOME", "TMPDIR", "PATH", "LANG", "PYTHONUTF8", "LC_CTYPE"].contains(&key.as_str()),
            "inherited unexpected key {key}"
        );
    }
    assert_eq!(env["HOME"].as_str(), ctx.workspace.root().to_str());
    assert_eq!(env["TMPDIR"].as_str(), ctx.workspace.root().to_str());
}

#[test]
fn replacing_workspace_path_does_not_replace_the_pinned_directory() {
    let (owner, _harness, ctx) = context();
    script(&ctx, "print('original-root')\n");
    std::fs::rename(ctx.workspace.root(), owner.path().join("original")).unwrap();
    std::fs::create_dir(ctx.workspace.root()).unwrap();
    script(&ctx, "print('replacement-root')\n");
    let result = command(&ctx, "python3 probe.py");
    assert_eq!(result["command_ok"], true, "{result}");
    assert_eq!(
        result["stdout"].as_str().unwrap().trim(),
        "original-root",
        "{result}"
    );
    assert_eq!(result["sandbox_enforced"], true);
}

#[test]
fn dangerous_permission_mode_does_not_disable_kernel_network_denial() {
    let (_owner, _harness, mut ctx) = context();
    ctx.policy.permission_mode = "dangerous".into();
    ctx.permission_mode = "dangerous".into();
    script(&ctx, "import socket\ntry:\n socket.socket()\n print('unsafe')\nexcept PermissionError:\n print('denied')\n");
    let result = command(&ctx, "python3 probe.py");
    assert_eq!(result["command_ok"], true, "{result}");
    assert_eq!(
        result["stdout"].as_str().unwrap().trim(),
        "denied",
        "{result}"
    );
}

#[test]
fn environment_report_does_not_claim_an_unexecuted_kernel_probe() {
    let (_owner, _harness, ctx) = context();
    let report = call_tool(&ctx, "check_exec_environment", &json!({}));
    assert_eq!(report["filesystem_sandbox"]["required"], true);
    assert_eq!(report["filesystem_sandbox"]["root_pinned"], true);
    assert!(report["filesystem_sandbox"]["available"].is_null());
    assert_eq!(report["network_allowed"], false);
    assert_eq!(report["global_tmp_write"], "denied");
}

#[test]
fn server_info_and_environment_agree_on_network_and_required_isolation() {
    let (_owner, _harness, ctx) = context();
    let info = call_tool(&ctx, "server_info", &json!({}));
    let env = call_tool(&ctx, "check_exec_environment", &json!({}));
    assert_eq!(info["network_allowed"], false);
    assert_eq!(env["network_allowed"], info["network_allowed"]);
    assert_eq!(info["workspace_exec_sandbox_required"], true);
    assert_eq!(env["workspace_exec_sandbox_required"], true);
    assert!(env["workspace_exec_sandbox_enforced"].is_null());
}

#[test]
fn timeout_does_not_misreport_an_isolated_child_as_unsandboxed() {
    let (_owner, _harness, ctx) = context();
    script(&ctx, "import time\ntime.sleep(5)\n");
    let result = call_tool(
        &ctx,
        "exec_command",
        &json!({
            "cmd":"python3 probe.py", "timeout_ms":50, "yield_time_ms":500
        }),
    );
    assert_eq!(result["error"]["code"], "TIMEOUT", "{result}");
    assert_eq!(result["command_ok"], false, "{result}");
    assert_eq!(result["child_process"], true, "{result}");
    assert_eq!(result["sandbox_enforced"], true, "{result}");
    assert_eq!(result["execution_boundary"], "landlock_seccomp", "{result}");
    assert_eq!(result["automatic_retry_allowed"], false, "{result}");
}
