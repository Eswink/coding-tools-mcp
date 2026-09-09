//! Windows functional compatibility is not a ten-second startup benchmark.
//! Test-only: production defaults, limits and timeout handling remain unchanged.
use super::context::ToolContext;
use serde_json::json;
use std::time::{Duration, Instant};
use crate::tools::dispatch::call_tool;

const COMPAT_TIMEOUT_MS: u64 = 60_000;

pub(super) fn assert_command(ctx: &ToolContext, command: &str, expected: &str) {
    assert_command_with_yield(ctx, command, expected, 30_000);
}

fn assert_command_with_yield(ctx: &ToolContext, command: &str, expected: &str, yield_ms: u64) {
    let started = Instant::now();
    let mut output = call_tool(ctx, "exec_command", &json!({
        "cmd": command, "timeout_ms": COMPAT_TIMEOUT_MS, "yield_time_ms": yield_ms
    }));
    assert_eq!(output["ok"], true, "{command}: {output}");
    let retained = if output["status"] == "running" {
        Some(output["session_id"].as_str().expect("retained session").to_owned())
    } else {
        None
    };
    if let Some(session_id) = retained {
        // Poll only the original session: never re-submit a command after a yield.
        while output["status"] == "running" && started.elapsed() < Duration::from_secs(65) {
            output = call_tool(ctx, "write_stdin", &json!({
                "session_id": session_id, "chars": "", "yield_time_ms": 250
            }));
            assert_eq!(output["ok"], true, "{command}: {output}");
        }
        if output["status"] == "running" {
            let cleanup = call_tool(ctx, "kill_session", &json!({
                "session_id": session_id, "wait_ms": 2000
            }));
            panic!("compatibility test deadline exceeded: {command}: {cleanup}");
        }
        if let Ok(session) = ctx.sessions.get(&session_id) {
            tauri::async_runtime::block_on(session.wait_for_readers());
            output = call_tool(ctx, "write_stdin", &json!({
                "session_id": session_id, "chars": "", "yield_time_ms": 0
            }));
        }
    }
    eprintln!("windows-compat-v8 {}", json!({
        "command": command, "elapsed_ms": started.elapsed().as_millis(),
        "budget_ms": COMPAT_TIMEOUT_MS, "status": output["status"],
        "exit_code": output["exit_code"]
    }));
    assert_eq!(output["ok"], true, "{command}: {output}");
    assert_eq!(output["command_ok"], true, "{command}: {output}");
    assert_eq!(output["status"], "exited", "{command}: {output}");
    assert_eq!(output["termination_reason"], "exited", "{command}: {output}");
    assert_eq!(output["exit_code"], 0, "{command}: {output}");
    assert_eq!(output["stdout"].as_str().unwrap_or_default().trim(), expected, "{command}: {output}");
    assert_eq!(output["stdout_truncated"], false, "{command}: {output}");
    assert_eq!(output["stderr_truncated"], false, "{command}: {output}");
}

#[test]
fn windows_explicit_timeout_remains_enforced() {
    let workspace = tempfile::tempdir().expect("workspace");
    let harness = tempfile::tempdir().expect("harness");
    let ctx = ToolContext::for_test(workspace.path().to_path_buf(), harness.path().to_path_buf())
        .expect("context");
    let output = call_tool(&ctx, "exec_command", &json!({
        "cmd": "python -c \"import time; time.sleep(5)\"",
        "timeout_ms": 100, "yield_time_ms": 1000
    }));
    assert_eq!(output["ok"], true, "{output}");
    assert_eq!(output["command_ok"], false, "{output}");
    assert_eq!(output["error"]["code"], "TIMEOUT", "{output}");
    assert_eq!(output["termination_reason"], "timeout", "{output}");
    assert_eq!(output["status"], "exited", "{output}");
    assert_eq!(output["process_may_be_running"], false, "{output}");
}

#[test]
fn windows_compatibility_follows_retained_session_once() {
    let workspace = tempfile::tempdir().expect("workspace");
    let harness = tempfile::tempdir().expect("harness");
    let ctx = ToolContext::for_test(workspace.path().to_path_buf(), harness.path().to_path_buf())
        .expect("context");
    assert_command_with_yield(&ctx,
        "python -c \"from pathlib import Path; p=Path('once.txt'); p.open('a').write('once'); print('retained-ok')\"",
        "retained-ok", 0);
    assert_eq!(std::fs::read_to_string(workspace.path().join("once.txt")).unwrap(), "once");
}

#[test]
fn windows_powershell_compatibility_preserves_exact_output() {
    let workspace = tempfile::tempdir().expect("workspace");
    let harness = tempfile::tempdir().expect("harness");
    let ctx = ToolContext::for_test(workspace.path().to_path_buf(), harness.path().to_path_buf())
        .expect("context");
    assert_command(&ctx, "powershell -NoProfile -Command \"Write-Output tooling-powershell-ok\"",
                   "tooling-powershell-ok");
}
