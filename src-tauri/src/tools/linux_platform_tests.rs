#![cfg(target_os = "linux")]

use std::os::unix::fs::PermissionsExt;
use std::time::{Duration, Instant};

use serde_json::json;
use tempfile::tempdir;

use crate::tools::{call_tool, ToolContext};

fn context() -> (tempfile::TempDir, tempfile::TempDir, ToolContext) {
    let workspace = tempdir().expect("workspace");
    let harness = tempdir().expect("harness");
    let ctx = ToolContext::for_test(
        workspace.path().to_path_buf(),
        harness.path().to_path_buf(),
    )
    .expect("context");
    (workspace, harness, ctx)
}

#[test]
fn linux_discovery_reports_posix_execution_contract() {
    let (_workspace, _harness, ctx) = context();

    let info = call_tool(&ctx, "server_info", &json!({}));
    assert_eq!(info["ok"], true, "{info}");
    assert_eq!(info["host"]["os"], "linux", "{info}");
    assert_eq!(info["host"]["pathStyle"], "posix", "{info}");
    assert_eq!(info["host"]["commandExecution"], "direct-argv", "{info}");

    let env = call_tool(&ctx, "check_exec_environment", &json!({}));
    assert_eq!(env["ok"], true, "{env}");
    assert_eq!(env["host"]["os"], "linux", "{env}");
    let allowed = env["system_command_allowlist"]
        .as_array()
        .expect("allowlist")
        .iter()
        .filter_map(|value| value.as_str())
        .collect::<Vec<_>>();
    assert!(allowed.contains(&"sh"), "{env}");
    assert!(allowed.contains(&"bash"), "{env}");
    assert!(!allowed.contains(&"cmd"), "{env}");
    assert!(!allowed.contains(&"powershell"), "{env}");
    assert!(!allowed.contains(&"pwsh"), "{env}");

    let extensions = env["workspace_local_entries"]["script_extensions"]
        .as_array()
        .expect("script extensions")
        .iter()
        .filter_map(|value| value.as_str())
        .collect::<Vec<_>>();
    assert!(extensions.contains(&".sh"), "{env}");
    for windows_extension in [".exe", ".bat", ".cmd", ".ps1"] {
        assert!(!extensions.contains(&windows_extension), "{env}");
    }
}

#[test]
fn linux_exec_runs_explicit_shell_and_workspace_script() {
    let (workspace, _harness, ctx) = context();
    let script = workspace.path().join("linux-tooling-check.sh");
    std::fs::write(&script, "#!/bin/sh\nprintf 'workspace-sh-ok\\n'\n").expect("script");
    let mut permissions = std::fs::metadata(&script).expect("metadata").permissions();
    permissions.set_mode(0o755);
    std::fs::set_permissions(&script, permissions).expect("permissions");

    for (cmd, expected) in [
        (r#"sh -c "printf explicit-sh-ok""#, "explicit-sh-ok"),
        ("linux-tooling-check.sh", "workspace-sh-ok"),
    ] {
        let output = call_tool(
            &ctx,
            "exec_command",
            &json!({"cmd": cmd, "timeout_ms": 10_000, "yield_time_ms": 10_000}),
        );
        assert_eq!(output["ok"], true, "{cmd}: {output}");
        assert_eq!(output["command_ok"], true, "{cmd}: {output}");
        assert_eq!(output["exit_code"], 0, "{cmd}: {output}");
        assert!(
            output["stdout"].as_str().unwrap_or_default().contains(expected),
            "{cmd}: {output}"
        );
    }
}

#[test]
fn linux_rejects_windows_shell_semantics_before_spawn() {
    let (_workspace, _harness, ctx) = context();
    for cmd in ["cmd /c echo nope", "powershell -NoProfile -Command echo-nope"] {
        let output = call_tool(&ctx, "exec_command", &json!({"cmd": cmd}));
        assert_eq!(output["ok"], false, "{cmd}: {output}");
        let code = output["error"]["code"].as_str().unwrap_or_default();
        let message = output["error"]["message"].as_str().unwrap_or_default();
        assert!(
            code == "PLATFORM_COMMAND_MISMATCH"
                || message.contains("PLATFORM_COMMAND_MISMATCH"),
            "{cmd}: {output}"
        );
    }
}

#[test]
fn linux_background_task_cancel_confirms_process_group_drain() {
    let (_workspace, _harness, ctx) = context();
    let started = call_tool(
        &ctx,
        "start_exec_task",
        &json!({
            "cmd": r#"sh -c "sleep 30""#,
            "request_id": "linux-process-group-cancel",
            "timeout_ms": 30_000
        }),
    );
    assert_eq!(started["ok"], true, "{started}");
    let job_id = started["job_id"].as_str().expect("job id").to_string();

    let running_deadline = Instant::now() + Duration::from_secs(5);
    loop {
        let state = call_tool(&ctx, "get_exec_task", &json!({"job_id": job_id}));
        assert_eq!(state["ok"], true, "{state}");
        if matches!(state["status"].as_str(), Some("running" | "cancelling")) {
            break;
        }
        assert!(!state["terminal"].as_bool().unwrap_or(false), "task exited too early: {state}");
        assert!(Instant::now() < running_deadline, "task never started: {state}");
        std::thread::sleep(Duration::from_millis(25));
    }

    let cancelling = call_tool(&ctx, "cancel_exec_task", &json!({"job_id": job_id}));
    assert_eq!(cancelling["ok"], true, "{cancelling}");

    let terminal_deadline = Instant::now() + Duration::from_secs(10);
    loop {
        let state = call_tool(&ctx, "get_exec_task", &json!({"job_id": job_id}));
        assert_eq!(state["ok"], true, "{state}");
        if state["terminal"].as_bool() == Some(true) {
            assert_eq!(state["status"], "cancelled", "{state}");
            assert_ne!(state["result"]["process_may_be_running"], true, "{state}");
            assert_eq!(state["result"]["output_complete"], true, "{state}");
            break;
        }
        assert!(Instant::now() < terminal_deadline, "task did not drain: {state}");
        std::thread::sleep(Duration::from_millis(25));
    }
}
