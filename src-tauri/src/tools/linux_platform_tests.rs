#![cfg(target_os = "linux")]

use std::os::unix::fs::PermissionsExt;

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
    assert_eq!(info["host"]["path_style"], "posix", "{info}");
    assert_eq!(info["host"]["command_execution"], "direct-argv", "{info}");

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
