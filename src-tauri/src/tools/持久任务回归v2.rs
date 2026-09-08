use std::sync::Arc;
use std::time::{Duration, Instant};
use serde_json::{json, Value};
use super::{ExecTaskStore, Status};
use crate::tools::{call_tool, context::ToolContext};

fn fixture() -> (tempfile::TempDir, tempfile::TempDir, ToolContext) {
    let root = tempfile::tempdir().unwrap();
    let data = tempfile::tempdir().unwrap();
    let ctx = ToolContext::for_test(root.path().to_path_buf(), data.path().join("harness")).unwrap();
    (root, data, ctx)
}

#[test]
fn queued_record_is_encrypted_and_restart_never_replays_it() {
    let dir = tempfile::tempdir().unwrap();
    let root = dir.path().join("journal");
    let store = ExecTaskStore::shared(root.clone());
    let (job, _) = store.reserve("request-private-canary", "fp", 1000).unwrap();
    let id = job.id.clone();
    let bytes = std::fs::read(root.join(format!("{id}.json"))).unwrap();
    assert!(!String::from_utf8_lossy(&bytes).contains("request-private-canary"));
    drop(job); drop(store);
    let restored = ExecTaskStore::shared(root);
    let (same, fresh) = restored.reserve("request-private-canary", "fp", 1000).unwrap();
    assert!(!fresh); assert_eq!(same.id, id);
    assert_eq!(same.summary()["status"], "interrupted");
    assert_eq!(same.summary()["result"]["process_may_be_running"], true);
    assert_eq!(same.summary()["execution_survives_app_restart"], false);
    assert!(restored.reserve("request-private-canary", "different", 1000).is_err());
}

#[test]
fn completed_results_and_unicode_output_survive_reopen() {
    let dir = tempfile::tempdir().unwrap();
    let store = ExecTaskStore::shared(dir.path().to_path_buf());
    let (job, _) = store.reserve("finished", "fp", 1000).unwrap();
    job.finish(Status::Succeeded, json!({"command_ok":true,"stdout":"中文输出","exit_code":0}));
    store.checkpoint(&job).unwrap();
    let id = job.id.clone(); let before = job.summary();
    drop(job); drop(store);
    let restored = ExecTaskStore::shared(dir.path().to_path_buf());
    let job = restored.get(&id).unwrap();
    assert_eq!(job.summary()["status"], "succeeded");
    assert_eq!(job.summary()["created_at"], before["created_at"]);
    assert_eq!(job.summary()["completed_at"], before["completed_at"]);
    assert_eq!(job.summary()["elapsed_ms"], before["elapsed_ms"]);
    assert_eq!(job.output("stdout", 0, 100).unwrap()["text"], "中文输出");
}

#[test]
fn plaintext_or_corrupt_record_is_preserved_and_blocks_new_execution() {
    let (_workspace, dir, mut ctx) = fixture();
    let path = dir.path().join("journal");
    let store = ExecTaskStore::shared(path.clone());
    let (job, _) = store.reserve("old", "fp", 1000).unwrap();
    let file = path.join(format!("{}.json", job.id));
    drop(job); drop(store);
    let corrupt = b"{\"workspaces\": [], \"version\": 1000}";
    std::fs::write(&file, corrupt).unwrap();
    ctx.exec_tasks = ExecTaskStore::shared(path);
    let result = call_tool(&ctx, "start_exec_task", &json!({"cmd":"echo not-run", "request_id":"new"}));
    assert_eq!(result["ok"], false, "{result}");
    assert_eq!(std::fs::read(file).unwrap(), corrupt);
}

#[test]
fn future_encrypted_schema_is_not_silently_reset() {
    let dir = tempfile::tempdir().unwrap();
    let id = uuid::Uuid::new_v4().to_string();
    let archive = crate::data::TaskArchive::open(dir.path()).unwrap();
    archive.save(&id, || json!({"id":id,"version":99})).unwrap();
    drop(archive);
    let store = ExecTaskStore::shared(dir.path().to_path_buf());
    assert!(store.list(None).is_err());
    assert!(dir.path().join(format!("{id}.json")).exists());
}

#[test]
fn second_archive_owner_is_rejected_without_clearing_records() {
    let dir = tempfile::tempdir().unwrap();
    let _owner = crate::data::TaskArchive::open(dir.path()).unwrap();
    assert!(crate::data::TaskArchive::open(dir.path()).is_err());
}

#[test]
fn service_namespace_reuses_jobs_but_channels_and_profiles_are_isolated() {
    let (root, data, mut first) = fixture();
    first.enable_durable_tasks("profile", "mcp");
    let (job, _) = first.exec_tasks.reserve("same", "fp", 1000).unwrap();
    let mut again = ToolContext::for_test(root.path().to_path_buf(), data.path().join("harness")).unwrap();
    again.enable_durable_tasks("profile", "mcp");
    assert!(Arc::ptr_eq(&first.exec_tasks, &again.exec_tasks));
    assert!(again.exec_tasks.get(&job.id).is_ok());
    again.enable_durable_tasks("profile", "actions");
    assert!(again.exec_tasks.get(&job.id).is_err());
    again.enable_durable_tasks("other-profile", "mcp");
    assert!(again.exec_tasks.get(&job.id).is_err());
}

#[test]
fn interrupted_confirmation_is_explicit_and_does_not_turn_failure_into_success() {
    let (_root, dir, mut ctx) = fixture();
    let path = dir.path().join("journal");
    let store = ExecTaskStore::shared(path.clone());
    let (job, _) = store.reserve("interrupted", "fp", 1000).unwrap();
    let id = job.id.clone(); drop(job); drop(store);
    ctx.exec_tasks = ExecTaskStore::shared(path);
    let unchanged = call_tool(&ctx, "cancel_exec_task", &json!({"job_id":id}));
    assert_eq!(unchanged["result"]["process_may_be_running"], true);
    let remote = call_tool(&ctx, "cancel_exec_task", &json!({"job_id":id,"confirm_terminated":true}));
    assert_eq!(remote["ok"], false, "remote callers cannot confirm unknown local processes");
    assert_eq!(ctx.exec_tasks.get(&id).unwrap().summary()["result"]["process_may_be_running"], true);
    ctx.local_task_control = true;
    let confirmed = call_tool(&ctx, "cancel_exec_task", &json!({"job_id":id,"confirm_terminated":true}));
    assert_eq!(confirmed["status"], "interrupted");
    assert_eq!(confirmed["command_ok"], false);
    assert_eq!(confirmed["result"]["termination_confirmed_by_user"], true);
    assert_eq!(confirmed["result"]["process_may_be_running"], false);
}

#[test]
fn task_budget_does_not_expand_legacy_exec_or_accept_injected_internal_flags() {
    let (_root, _data, mut ctx) = fixture();
    let legacy = call_tool(&ctx,"exec_command", &json!({"cmd":"echo legacy","timeout_ms":600001}));
    assert_eq!(legacy["ok"], false);
    let python = if cfg!(windows) { "python" } else { "python3" };
    let async_job = call_tool(&ctx,"start_exec_task", &json!({"cmd":format!("{python} -c \"print('long-budget')\""),"request_id":"long","timeout_ms":86400000}));
    assert_eq!(async_job["ok"], true, "{async_job}");
    let until = Instant::now() + Duration::from_secs(60);
    loop {
        let result = call_tool(&ctx,"get_exec_task", &json!({"job_id":async_job["job_id"]}));
        if result["terminal"] == true {
            assert_eq!(result["status"], "succeeded", "{result}");
            assert_eq!(result["execution_timeout_ms"], 86400000);
            assert!(result["stdout"]["text"].as_str().unwrap().contains("long-budget"));
            break;
        }
        assert!(Instant::now() < until, "{result}");
        std::thread::sleep(Duration::from_millis(25));
    }
    ctx.policy.max_task_timeout_ms = 1000;
    let over = call_tool(&ctx,"start_exec_task", &json!({"cmd":"echo over","request_id":"over","timeout_ms":1001}));
    assert_eq!(over["ok"], false);
    let injected = call_tool(&ctx,"start_exec_task", &json!({"cmd":"echo injected","request_id":"injected","managed_task":true}));
    assert_eq!(injected["ok"], false);
    let ordinary = call_tool(&ctx,"exec_command", &json!({"cmd":"echo legacy","timeout_ms":600001,"managed_task":true}));
    assert_eq!(ordinary["ok"], false);
}

#[test]
fn storage_failure_refuses_submission_before_worker_spawn() {
    let (root, dir, mut ctx) = fixture();
    let path = dir.path().join("not-a-directory");
    std::fs::write(&path, "preserve").unwrap();
    ctx.exec_tasks = ExecTaskStore::shared(path.clone());
    let result = call_tool(&ctx,"start_exec_task", &json!({"cmd":"echo refused","request_id":"no-launch"}));
    assert_eq!(result["ok"], false);
    assert_eq!(std::fs::read_to_string(path).unwrap(), "preserve");
    assert_eq!(std::fs::read_dir(root.path()).unwrap().count(), 0);
}

#[cfg(any(windows, target_os = "linux"))]
fn process_running(pid: u32) -> bool {
    #[cfg(target_os = "linux")]
    {
        let stat = std::fs::read_to_string(format!("/proc/{pid}/stat")).unwrap_or_default();
        !stat.is_empty() && stat.rsplit_once(") ").is_none_or(|(_, fields)| !fields.starts_with('Z'))
    }
    #[cfg(windows)]
    {
        use std::os::windows::io::{FromRawHandle, OwnedHandle};
        use windows::Win32::System::Threading::{OpenProcess, GetExitCodeProcess, PROCESS_QUERY_LIMITED_INFORMATION};
        let Ok(raw) = (unsafe { OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, pid) }) else { return false; };
        let _owned = unsafe { OwnedHandle::from_raw_handle(raw.0) };
        let mut code = 0;
        unsafe { GetExitCodeProcess(raw, &mut code) }.is_ok() && code == 259
    }
}

#[cfg(any(windows, target_os = "linux"))]
#[test]
fn cancellation_terminates_a_real_grandchild_not_only_the_parent() {
    let (root, _data, ctx) = fixture();
    std::fs::write(root.path().join("tree.py"), "import subprocess,sys,time\nfrom pathlib import Path\nc=subprocess.Popen([sys.executable,'-c','import time; time.sleep(90)'])\nPath('child.pid').write_text(str(c.pid))\ntime.sleep(90)\n").unwrap();
    let python = if cfg!(windows) { "python" } else { "python3" };
    let accepted = call_tool(&ctx,"start_exec_task", &json!({"cmd":format!("{python} tree.py"),"request_id":"tree","timeout_ms":120000}));
    assert_eq!(accepted["ok"], true, "{accepted}");
    let deadline = Instant::now() + Duration::from_secs(45);
    let pid = loop {
        if let Ok(text) = std::fs::read_to_string(root.path().join("child.pid")) {
            if let Ok(pid) = text.parse::<u32>() { break pid; }
        }
        assert!(Instant::now() < deadline, "child tree did not start");
        std::thread::sleep(Duration::from_millis(25));
    };
    assert!(process_running(pid), "grandchild must be running before cancellation");
    let cancelled = call_tool(&ctx,"cancel_exec_task", &json!({"job_id":accepted["job_id"]}));
    assert_eq!(cancelled["ok"], true);
    let deadline = Instant::now() + Duration::from_secs(15);
    while process_running(pid) {
        assert!(Instant::now() < deadline, "grandchild survived cancellation");
        std::thread::sleep(Duration::from_millis(25));
    }
    let deadline = Instant::now() + Duration::from_secs(15);
    loop {
        let done = call_tool(&ctx,"get_exec_task", &json!({"job_id":accepted["job_id"]}));
        if done["terminal"] == true { assert_eq!(done["status"], "cancelled", "{done}"); break; }
        assert!(Instant::now() < deadline, "{done}");
        std::thread::sleep(Duration::from_millis(25));
    }
}

#[test]
fn malformed_terminal_payload_is_rejected_without_starting_an_executor() {
    let store = ExecTaskStore::default();
    let (job, _) = store.reserve("shape", "fp", 1000).unwrap();
    job.finish(Status::Succeeded, json!({"command_ok":true,"exit_code":0}));
    let valid = super::record::snapshot(&job);
    for payload in [Value::Null, json!([]), json!("success")] {
        let mut bad = valid.clone(); bad["result"] = payload;
        assert!(super::record::restore(bad).is_err());
    }
}

#[test]
fn wall_clock_adjustment_does_not_invalidate_completed_records() {
    let store = ExecTaskStore::default();
    let (job, _) = store.reserve("clock", "fp", 1000).unwrap();
    job.finish(Status::Succeeded, json!({"command_ok":true,"exit_code":0}));
    let mut value = super::record::snapshot(&job);
    // Elapsed duration uses Instant. Calendar time can legitimately go backward.
    value["created_at"] = json!(super::state::unix_ms().saturating_add(60000));
    let restored = super::record::restore(value).unwrap();
    assert_eq!(restored.summary()["status"], "succeeded");
}

#[test]
fn workspace_admission_fence_rolls_back_or_retires_without_losing_results() {
    let dir = tempfile::tempdir().unwrap();
    let root = dir.path().join("tasks");
    let store = ExecTaskStore::shared(root.clone());
    let (job, _) = store.reserve("done", "fp", 1000).unwrap();
    assert!(store.pause_admission().is_err(), "active tasks prevent removal");
    job.finish(Status::Succeeded, json!({"command_ok":true,"exit_code":0}));
    store.checkpoint(&job).unwrap();
    let guard = store.pause_admission().unwrap();
    assert!(store.reserve("late", "fp", 1000).is_err());
    assert!(store.get(&job.id).is_ok(), "queries still work during fencing");
    drop(guard);
    let guard = store.pause_admission().unwrap();
    guard.commit();
    assert!(store.reserve("late", "fp", 1000).is_err());
    let id = job.id.clone(); drop(job); drop(store);
    let stale = ExecTaskStore::shared(root);
    assert!(stale.get(&id).is_ok(), "retired namespace results remain available");
    assert!(stale.reserve("late", "fp", 1000).is_err(), "recreating old context cannot bypass retirement");
}

#[test]
fn workspace_fence_and_parallel_admission_have_exactly_one_winner() {
    for _ in 0..16 {
        let store = Arc::new(ExecTaskStore::default());
        let barrier = Arc::new(std::sync::Barrier::new(2));
        let other = store.clone(); let start = barrier.clone();
        let submit = std::thread::spawn(move || { start.wait(); other.reserve("race", "fp", 1000).is_ok() });
        barrier.wait();
        let guard = store.pause_admission();
        let submitted = submit.join().unwrap();
        assert_ne!(guard.is_ok(), submitted, "removal and command admission cannot both win");
    }
}

#[test]
fn live_profile_lookup_does_not_require_the_project_directory_to_exist() {
    let dir = tempfile::tempdir().unwrap();
    let store = ExecTaskStore::shared(dir.path().join("journal"));
    let id = uuid::Uuid::new_v4().to_string();
    store.bind_profile(&id);
    let (job, _) = store.reserve("unconfirmed", "fp", 1000).unwrap();
    job.finish(Status::Interrupted, json!({"command_ok":false,"process_may_be_running":true}));
    let found = ExecTaskStore::live_for_profile(&id);
    assert_eq!(found.len(), 1);
    assert!(found[0].pause_admission().is_err(), "unknown processes still own capacity");
    assert!(ExecTaskStore::live_for_profile("different-profile").is_empty());
}
