//! Real child-process regressions: no command/IPC mocks or timeout enlargement.
use coding_tools_mcp_desktop_lib::tools::{call_tool, ToolContext};
use serde_json::{json, Value};
use std::time::{Duration, Instant};

#[cfg(windows)]
const PYTHON: &str = "python";
#[cfg(not(windows))]
const PYTHON: &str = "python3";

struct Fixture {
    ctx: ToolContext,
    _workspace: tempfile::TempDir,
    _harness: tempfile::TempDir,
}

impl Fixture {
    fn new() -> Self {
        let workspace = tempfile::tempdir().expect("workspace");
        let harness = tempfile::tempdir().expect("harness");
        let ctx = ToolContext::for_test(workspace.path().into(), harness.path().into()).expect("context");
        Self { ctx, _workspace: workspace, _harness: harness }
    }

    fn exec(&self, script: &str, input: &str, timeout: u64, yield_ms: u64) -> Value {
        call_tool(&self.ctx, "exec_command", &json!({
            "cmd": format!("{PYTHON} -c \"{script}\""), "stdin": input,
            "timeout_ms": timeout, "yield_time_ms": yield_ms,
        }))
    }

    fn terminal(&self, mut result: Value) -> Value {
        assert_eq!(result["ok"], true, "{result}");
        if result["status"] != "running" { return result; }
        let id = result["session_id"].as_str().expect("session").to_owned();
        let deadline = Instant::now() + Duration::from_secs(20);
        while result["status"] == "running" && Instant::now() < deadline {
            result = call_tool(&self.ctx, "write_stdin", &json!({
                "session_id": id, "chars": "", "yield_time_ms": 50
            }));
            assert_eq!(result["ok"], true, "{result}");
        }
        if result["status"] == "running" {
            let cleanup = call_tool(&self.ctx, "kill_session", &json!({"session_id": id}));
            panic!("child exceeded the regression deadline: {cleanup}");
        }
        // Joining I/O before final assertions also detects late BrokenPipe errors.
        let session = self.ctx.sessions.get(&id).expect("retained session");
        tauri::async_runtime::block_on(session.wait_for_readers());
        call_tool(&self.ctx, "write_stdin", &json!({"session_id": id, "chars": "", "yield_time_ms": 0}))
    }
}

#[test]
fn initial_input_zero_yield_delivers_bytes() {
    let f = Fixture::new();
    let input = "initial-input\n中文 ✅\n";
    let result = f.terminal(f.exec("import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())", input, 15_000, 0));
    assert_eq!(result["command_ok"], true, "{result}");
    assert_eq!(result["stdout"], input, "{result}");
    assert_eq!(result["stdin_open"], false, "{result}");
    assert_eq!(result["termination_reason"], "exited", "{result}");
}

#[test]
fn initial_input_waiting_call_delivers_bytes_and_eof() {
    let f = Fixture::new();
    let input = "exact batch\nsecond line\n";
    let result = f.terminal(f.exec("import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())", input, 15_000, 10_000));
    assert_eq!(result["command_ok"], true, "{result}");
    assert_eq!(result["stdout"], input, "{result}");
    assert_eq!(result["stdin_open"], false, "{result}");
}

#[test]
fn blocked_initial_input_obeys_process_deadline() {
    let f = Fixture::new();
    let input = "x".repeat(8 * 1024 * 1024);
    let started = Instant::now();
    // Finite child bounds the old implementation's failure as well: it neither
    // reads stdin nor exits before four seconds, longer than this assertion.
    let result = f.exec("import time; time.sleep(4)", &input, 100, 10_000);
    assert!(started.elapsed() < Duration::from_secs(3), "blocked stdin bypassed deadline");
    assert_eq!(result["ok"], true, "{result}");
    assert_eq!(result["command_ok"], false, "{result}");
    assert_eq!(result["error"]["code"], "TIMEOUT", "{result}");
    assert_eq!(result["termination_reason"], "timeout", "{result}");
    assert_eq!(result["process_may_be_running"], false, "{result}");
}

#[test]
fn blocked_initial_input_keeps_zero_yield_responsive() {
    let f = Fixture::new();
    let input = "x".repeat(8 * 1024 * 1024);
    let started = Instant::now();
    let first = f.exec("import time; time.sleep(4)", &input, 500, 0);
    assert!(started.elapsed() < Duration::from_secs(3), "zero yield waited for the pipe");
    let result = f.terminal(first);
    assert_eq!(result["command_ok"], false, "{result}");
    assert_eq!(result["termination_reason"], "timeout", "{result}");
    assert_eq!(result["process_may_be_running"], false, "{result}");
}

#[test]
fn failed_initial_input_is_not_a_successful_command_or_spawn_failure() {
    let f = Fixture::new();
    let input = "x".repeat(8 * 1024 * 1024);
    let result = f.exec("print('child-did-not-consume-input')", &input, 15_000, 15_000);
    assert_eq!(result["ok"], true, "{result}");
    assert_eq!(result["transport_ok"], true, "{result}");
    assert_eq!(result["command_ok"], false, "{result}");
    assert_eq!(result["error"]["code"], "STDIN_WRITE_FAILED", "{result}");
    assert_eq!(result["status"], "exited", "{result}");
    assert_eq!(result["termination_reason"], "stdin_error", "{result}");
    assert_eq!(result["process_may_be_running"], false, "{result}");
}

#[test]
fn explicit_kill_is_not_overwritten_by_pending_stdin_failure() {
    let f = Fixture::new();
    let first = f.exec("import time; time.sleep(10)", &"x".repeat(8 * 1024 * 1024), 15_000, 0);
    let id = first["session_id"].as_str().expect("session");
    let session = f.ctx.sessions.get(id).expect("session");
    let killed = call_tool(&f.ctx, "kill_session", &json!({"session_id": id, "wait_ms": 2000}));
    assert_eq!(killed["ok"], true, "{killed}");
    tauri::async_runtime::block_on(session.wait_for_readers());
    let result = session.snapshot(4096);
    assert_eq!(result["termination_reason"], "killed", "{result}");
    assert_eq!(result["process_may_be_running"], false, "{result}");
    assert_eq!(result["stdin_open"], false, "{result}");
}
