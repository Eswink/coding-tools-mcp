use super::*;
use std::sync::Barrier;
use std::time::Instant;
use tempfile::TempDir;

#[cfg(windows)]
const PYTHON: &str = "python";
#[cfg(not(windows))]
const PYTHON: &str = "python3";

fn fixture() -> (TempDir, TempDir, ToolContext) {
    let root = tempfile::tempdir().unwrap();
    let harness = tempfile::tempdir().unwrap();
    let ctx = ToolContext::for_test(root.path().to_path_buf(), harness.path().to_path_buf()).unwrap();
    (root, harness, ctx)
}

fn submit(ctx: &ToolContext, key: &str, python: &str, timeout: u64) -> Value {
    crate::tools::call_tool(ctx, "start_exec_task", &json!({
        "request_id": key, "cmd": format!("{PYTHON} -c \"{python}\""), "timeout_ms": timeout,
    }))
}

fn await_terminal(ctx: &ToolContext, id: &str) -> Value {
    let deadline = Instant::now() + Duration::from_secs(12);
    loop {
        let result = crate::tools::call_tool(ctx, "get_exec_task", &json!({"job_id": id, "limit": 16384}));
        assert_eq!(result["ok"], true, "{result}");
        if result["terminal"] == true { return result; }
        assert!(Instant::now() < deadline, "job did not terminate: {result}");
        std::thread::sleep(Duration::from_millis(25));
    }
}

#[test]
fn submit_returns_before_long_command_and_keeps_result_after_context_clone() {
    let (_root, _harness, ctx) = fixture();
    let start = Instant::now();
    let accepted = submit(&ctx, "nonblocking", "import time; time.sleep(2); print('completed')", 5000);
    assert_eq!(accepted["ok"], true, "{accepted}");
    assert!(start.elapsed() < Duration::from_millis(1500));
    assert_ne!(accepted["command_ok"], true);
    let background = ctx.background_snapshot();
    drop(ctx);
    let result = await_terminal(&background, accepted["job_id"].as_str().unwrap());
    assert_eq!(result["status"], "succeeded", "{result}");
    assert_eq!(result["command_ok"], true);
    assert!(result["stdout"]["text"].as_str().unwrap().contains("completed"));
    assert_eq!(result["restart_recoverable"], false);
}

#[test]
fn concurrent_duplicate_submissions_execute_exactly_one_command_within_retention() {
    let (root, _harness, ctx) = fixture();
    let ctx = Arc::new(ctx);
    let barrier = Arc::new(Barrier::new(8));
    let handles = (0..8).map(|_| {
        let ctx = ctx.clone(); let barrier = barrier.clone();
        std::thread::spawn(move || {
            barrier.wait();
            submit(&ctx, "same-logical-request", "from pathlib import Path; p=Path('count.txt'); p.write_text(p.read_text()+'x' if p.exists() else 'x')", 5000)
        })
    }).collect::<Vec<_>>();
    let results = handles.into_iter().map(|h| h.join().unwrap()).collect::<Vec<_>>();
    let id = results[0]["job_id"].as_str().unwrap();
    for r in &results { assert_eq!(r["ok"], true, "{r}"); assert_eq!(r["job_id"], id); }
    assert_eq!(results.iter().filter(|r| r["deduplicated"] == false).count(), 1);
    assert_eq!(await_terminal(&ctx, id)["status"], "succeeded");
    assert_eq!(std::fs::read_to_string(root.path().join("count.txt")).unwrap(), "x");
    let conflict = submit(&ctx, "same-logical-request", "print('different')", 5000);
    assert_eq!(conflict["error"]["code"], "IDEMPOTENCY_CONFLICT");
}

#[test]
fn different_timeout_with_same_key_is_a_conflict() {
    let (_root, _harness, ctx) = fixture();
    let a = submit(&ctx, "budget", "print('one')", 5000);
    let b = submit(&ctx, "budget", "print('one')", 4000);
    assert_eq!(b["error"]["code"], "IDEMPOTENCY_CONFLICT");
    await_terminal(&ctx, a["job_id"].as_str().unwrap());
}

#[test]
fn nonzero_exit_is_failed_not_transport_failure() {
    let (_root, _harness, ctx) = fixture();
    let a = submit(&ctx, "failure", "import sys; print('failure', file=sys.stderr); sys.exit(7)", 5000);
    let r = await_terminal(&ctx, a["job_id"].as_str().unwrap());
    assert_eq!(r["ok"], true);
    assert_eq!(r["status"], "failed", "{r}");
    assert_eq!(r["result"]["exit_code"], 7);
    assert_eq!(r["command_ok"], false);
    assert!(r["stderr"]["text"].as_str().unwrap().contains("failure"));
}

#[test]
fn process_deadline_is_not_an_http_wait_timeout() {
    let (_root, _harness, ctx) = fixture();
    let a = submit(&ctx, "deadline", "import time; time.sleep(10)", 200);
    assert_eq!(a["ok"], true);
    let r = await_terminal(&ctx, a["job_id"].as_str().unwrap());
    assert_eq!(r["status"], "timed_out", "{r}");
    assert_eq!(r["result"]["termination_reason"], "timeout");
}

#[test]
fn cancellation_is_acknowledged_quickly_then_reaches_a_terminal_state() {
    let (_root, _harness, ctx) = fixture();
    let a = submit(&ctx, "cancel", "import time; time.sleep(10)", 10000);
    let id = a["job_id"].as_str().unwrap();
    let start = Instant::now();
    let c = crate::tools::call_tool(&ctx, "cancel_exec_task", &json!({"job_id": id}));
    assert!(start.elapsed() < Duration::from_secs(1));
    assert_eq!(c["cancel_requested"], true);
    let r = await_terminal(&ctx, id);
    assert_eq!(r["status"], "cancelled", "{r}");
    let repeated = crate::tools::call_tool(&ctx, "cancel_exec_task", &json!({"job_id": id}));
    assert_eq!(repeated["status"], "cancelled");
}

#[test]
fn cancelling_completed_job_does_not_rewrite_success() {
    let (_root, _harness, ctx) = fixture();
    let a = crate::tools::call_tool(&ctx, "start_exec_task", &json!({"cmd": "echo done", "request_id": "done"}));
    let id = a["job_id"].as_str().unwrap();
    assert_eq!(await_terminal(&ctx, id)["status"], "succeeded");
    let c = crate::tools::call_tool(&ctx, "cancel_exec_task", &json!({"job_id": id}));
    assert_eq!(c["status"], "succeeded");
    assert_eq!(c["cancel_requested"], false);
}

#[test]
fn noninteractive_stdin_is_closed() {
    let (_root, _harness, ctx) = fixture();
    let a = submit(&ctx, "eof", "import sys; print('EOF:'+str(len(sys.stdin.read())))", 5000);
    let r = await_terminal(&ctx, a["job_id"].as_str().unwrap());
    assert_eq!(r["status"], "succeeded", "{r}");
    assert!(r["stdout"]["text"].as_str().unwrap().contains("EOF:0"));
}

#[test]
fn default_cwd_is_captured_at_submission() {
    let (root, _harness, ctx) = fixture();
    std::fs::create_dir(root.path().join("nested")).unwrap();
    ctx.set_default_cwd(root.path().join("nested"));
    let a = submit(&ctx, "cwd", "from pathlib import Path; Path('correct.txt').write_text('ok')", 5000);
    ctx.set_default_cwd(root.path().to_path_buf());
    assert_eq!(await_terminal(&ctx, a["job_id"].as_str().unwrap())["status"], "succeeded");
    assert!(root.path().join("nested/correct.txt").exists());
    assert!(!root.path().join("correct.txt").exists());
}

#[test]
fn byte_pages_are_repeatable_and_report_ring_buffer_gaps() {
    let first = state::page(b"6789", 10, 0, 2).unwrap();
    assert_eq!(first["cursor"], 6); assert_eq!(first["dropped_bytes"], 6);
    assert_eq!(first["next_cursor"], 8); assert_eq!(first["text"], "67");
    assert_eq!(first, state::page(b"6789", 10, 0, 2).unwrap());
    let end = state::page(b"6789", 10, 8, 10).unwrap();
    assert_eq!(end["next_cursor"], 10); assert_eq!(end["has_more"], false);
    let empty = state::page(b"6789", 10, 10, 2).unwrap();
    assert_eq!(empty["text"], ""); assert_eq!(empty["next_cursor"], 10);
    assert!(state::page(b"6789", 10, 11, 2).is_err());
}

#[test]
fn invalid_arguments_and_policy_do_not_register_a_task() {
    let (_root, _harness, ctx) = fixture();
    for args in [
        json!({"cmd": "echo ok"}), json!({"cmd": "echo ok", "request_id": ""}),
        json!({"cmd": "echo ok", "request_id": "r", "timeout_ms": -1}),
        json!({"cmd": "echo ok", "request_id": "r", "timeout_ms": 600001}),
        json!({"cmd": "echo ok", "request_id": "r", "confirm": "yes"}),
        json!({"cmd": "echo ok", "request_id": "r", "env": {"SECRET": "x"}}),
        json!({"cmd": "echo ok", "request_id": "r", "workdir": ".."}),
        json!({"cmd": "echo ok", "request_id": "r", "filesystem_scope": "host"}),
        json!({"cmd": "echo ok", "request_id": "r", "tty": true}),
    ] {
        let r = crate::tools::call_tool(&ctx, "start_exec_task", &args);
        assert_eq!(r["ok"], false, "{args}: {r}");
    }
    assert!(ctx.exec_tasks.list(None).is_empty());
}

#[test]
fn job_ids_are_isolated_between_service_contexts() {
    let (_root, _harness, ctx) = fixture();
    let (_root2, _harness2, other) = fixture();
    let a = crate::tools::call_tool(&ctx, "start_exec_task", &json!({"cmd":"echo own", "request_id":"owner"}));
    let r = crate::tools::call_tool(&other, "get_exec_task", &json!({"job_id":a["job_id"]}));
    assert_eq!(r["error"]["code"], "EXEC_TASK_NOT_FOUND");
    await_terminal(&ctx, a["job_id"].as_str().unwrap());
}

#[test]
fn quotas_do_not_evict_active_tasks_or_unexpired_idempotency_records() {
    let store = ExecTaskStore::with_limits(1, 2, Duration::from_secs(3600));
    let (one, fresh) = store.reserve("one", "fp", 500).unwrap(); assert!(fresh);
    assert!(store.reserve("two", "fp", 500).is_err());
    assert!(!store.reserve("one", "fp", 500).unwrap().1);
    one.finish(Status::Succeeded, json!({"command_ok":true}));
    let (two, _) = store.reserve("two", "fp", 500).unwrap();
    two.finish(Status::Succeeded, json!({"command_ok":true}));
    assert!(store.reserve("three", "fp", 500).is_err());
    assert!(!store.reserve("one", "fp", 500).unwrap().1);
}

#[test]
fn expired_terminal_tasks_are_cleaned_but_live_ones_remain() {
    let store = ExecTaskStore::with_limits(2, 2, Duration::ZERO);
    let (one, _) = store.reserve("one", "fp", 500).unwrap();
    let (two, _) = store.reserve("two", "fp", 500).unwrap();
    one.finish(Status::Succeeded, json!({"command_ok":true}));
    assert!(store.get(&one.id).is_err());
    assert!(store.get(&two.id).is_ok());
    let (again, _) = store.reserve("one", "fp", 500).unwrap();
    assert_ne!(one.id, again.id);
}

#[test]
fn listing_can_recover_request_id_without_disclosing_command_or_logs() {
    let (_root, _harness, ctx) = fixture();
    let a = crate::tools::call_tool(&ctx, "start_exec_task", &json!({"cmd":"echo private-command", "request_id":"lost"}));
    await_terminal(&ctx, a["job_id"].as_str().unwrap());
    let found = crate::tools::call_tool(&ctx, "list_exec_tasks", &json!({"request_id":"lost"}));
    assert_eq!(found["jobs"].as_array().unwrap().len(), 1);
    assert_eq!(found["jobs"][0]["job_id"], a["job_id"]);
    assert!(!found.to_string().contains("private-command"));
}

#[test]
fn unicode_and_binary_pages_can_be_reconstructed_exactly() {
    use base64::{engine::general_purpose::STANDARD, Engine};
    let mut bytes = "中文输出".as_bytes().to_vec();
    bytes.extend_from_slice(&[0xff, 0x00, 0x80]);
    let mut cursor = 0;
    let mut recovered = Vec::new();
    loop {
        let page = state::page(&bytes, bytes.len(), cursor, 2).unwrap();
        recovered.extend(STANDARD.decode(page["data_base64"].as_str().unwrap()).unwrap());
        cursor = page["next_cursor"].as_u64().unwrap();
        if page["has_more"] == false { break; }
    }
    assert_eq!(recovered, bytes);
}

#[test]
fn completed_job_exposes_a_stable_bounded_output_snapshot() {
    let (_root, _harness, ctx) = fixture();
    let a = submit(&ctx, "unicode", "import sys; sys.stdout.buffer.write(bytes([228,184,173,230,150,135])); sys.stdout.flush()", 5000);
    let id = a["job_id"].as_str().unwrap();
    let r = await_terminal(&ctx, id);
    assert_eq!(r["result"]["output_complete"], true, "{r}");
    assert_eq!(r["stdout"]["text"], "中文");
    let repeated = crate::tools::call_tool(&ctx, "get_exec_task", &json!({"job_id": id, "limit": 16384}));
    assert_eq!(r["stdout"], repeated["stdout"]);
    assert_eq!(r["elapsed_ms"], repeated["elapsed_ms"]);
}

#[test]
fn cancelling_a_started_process_stops_it_without_automatic_resubmission() {
    let (root, _harness, ctx) = fixture();
    let a = submit(&ctx, "cancel-running", "from pathlib import Path; import time; Path('started.txt').touch(); time.sleep(10); Path('finished.txt').touch()", 15000);
    let id = a["job_id"].as_str().unwrap();
    let deadline = Instant::now() + Duration::from_secs(8);
    while !root.path().join("started.txt").exists() {
        assert!(Instant::now() < deadline, "child did not start: {a}");
        std::thread::sleep(Duration::from_millis(25));
    }
    let before = Instant::now();
    let c = crate::tools::call_tool(&ctx, "cancel_exec_task", &json!({"job_id":id}));
    assert!(before.elapsed() < Duration::from_secs(1));
    assert_eq!(c["cancel_requested"], true);
    let r = await_terminal(&ctx, id);
    assert_eq!(r["status"], "cancelled", "{r}");
    assert!(!root.path().join("finished.txt").exists());
    let job = ctx.exec_tasks.get(id).unwrap();
    let session = job.data.lock().unwrap().session.clone().unwrap();
    assert!(session.has_exited());
}

#[test]
fn timestamps_are_unix_milliseconds_and_do_not_drive_retention() {
    let store = ExecTaskStore::with_limits(1, 2, Duration::from_secs(3600));
    let (job, _) = store.reserve("timestamp", "fp", 1000).unwrap();
    let before = job.summary();
    assert!(before["created_at"].as_u64().unwrap() > 1_500_000_000_000);
    assert_eq!(before["timestamp_unit"], "unix_ms");
    assert!(before["completed_at"].is_null());
    job.finish(Status::Succeeded, json!({"command_ok": true}));
    assert!(job.summary()["completed_at"].as_u64().is_some());
    assert!(store.get(&job.id).is_ok());
}

#[test]
fn unconfirmed_termination_retains_capacity_and_deduplication_record() {
    let store = ExecTaskStore::with_limits(1, 2, Duration::ZERO);
    let (job, _) = store.reserve("unconfirmed", "fp", 1000).unwrap();
    job.finish(Status::Failed, json!({"command_ok": false, "process_may_be_running": true}));
    assert!(store.get(&job.id).is_ok(), "uncertain execution must not expire into an unsafe retry");
    assert!(store.reserve("another", "fp", 1000).is_err());
    assert!(!store.reserve("unconfirmed", "fp", 1000).unwrap().1);
}
