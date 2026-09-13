//! Test-only real-task observer and bounded lifecycle assertions.
use std::path::PathBuf;
use std::time::{Duration, Instant};
use serde_json::{json, Value};
use crate::tools::{exec_tasks, ToolContext};
use super::Server;

pub(super) const STARTUP_BUDGET: Duration = Duration::from_secs(45);
pub(super) const DRAIN_BUDGET: Duration = Duration::from_secs(15);

pub(super) struct ObservedJob {
    context: ToolContext,
    id: String,
    release: PathBuf,
}

impl ObservedJob {
    pub(super) fn attach(server: &Server, accepted: &Value) -> Self {
        let id = accepted["job_id"].as_str().expect("accepted job must have an ID").to_owned();
        let mut context = ToolContext::for_test(server.root.path().to_path_buf(),
            server.root.path().join("local-test-observer")).unwrap();
        context.local_task_control = true;
        for store in exec_tasks::ExecTaskStore::live_for_profile(&server.profile) {
            context.exec_tasks = store;
            if exec_tasks::get(&context, &json!({"job_id": id})).is_ok() {
                return Self { context, id, release: server.root.path().join("release") };
            }
        }
        panic!("accepted job must exist in its profile's local task store");
    }

    pub(super) fn snapshot(&self) -> Value {
        exec_tasks::get(&self.context, &json!({"job_id": self.id, "limit": 1024}))
            .expect("local observation must remain available after remote revoke")
    }
}

impl Drop for ObservedJob {
    fn drop(&mut self) {
        // The guard is dropped before Server/TempDir, including assertion unwinds.
        // Cancel only this fixture's job; never acknowledge an unknown process.
        let _ = std::fs::write(&self.release, "");
        let args = json!({"job_id": self.id});
        if exec_tasks::get(&self.context, &args).ok().is_some_and(|v| v["terminal"] == true) { return; }
        let _ = exec_tasks::cancel(&self.context, &args);
        let until = Instant::now() + Duration::from_secs(10);
        while Instant::now() < until {
            if exec_tasks::get(&self.context, &args).ok().is_some_and(|v| v["terminal"] == true) { return; }
            std::thread::sleep(Duration::from_millis(25));
        }
        // Never cause a second panic while handling the original assertion.
        eprintln!("drain_probe cleanup=termination_unconfirmed");
    }
}

pub(super) fn startup_observation(task: &Value, ready: bool, elapsed: Duration, budget: Duration)
    -> Result<bool, &'static str> {
    if task["ok"] != true || !task["terminal"].is_boolean() { return Err("invalid task observation during startup"); }
    if task["terminal"] == true { return Err("worker terminated before readiness; inspect task result and stderr"); }
    if elapsed >= budget { return Err("worker readiness deadline exceeded; inspect task result and stderr"); }
    match task["status"].as_str() {
        Some("running") => Ok(ready),
        Some("queued") if !ready => Ok(false),
        _ => Err("worker is not in a valid live startup state"),
    }
}

pub(super) fn drain_observation(task: &Value, lease: &str, elapsed: Duration, budget: Duration)
    -> Result<bool, &'static str> {
    if task["ok"] != true || !task["terminal"].is_boolean() { return Err("invalid task observation during drain"); }
    if elapsed >= budget { return Err("independent draining deadline exceeded"); }
    if task["terminal"] != true {
        if lease != "draining" { return Err("workspace released before the actual task terminated"); }
        return Ok(false);
    }
    if task["status"] != "succeeded" || task["command_ok"] != true
        || task["result"]["exit_code"] != 0 || task["result"]["termination_reason"] != "exited"
        || task["result"]["output_complete"] != true || task["result"]["process_may_be_running"] != false {
        return Err("worker did not exit naturally and completely after release");
    }
    match lease {
        "free" => Ok(true),
        "draining" => Ok(false),
        _ => Err("unexpected owner transition during drain"),
    }
}

#[test]
fn acceptance_and_elapsed_time_alone_do_not_prove_readiness() {
    let queued = json!({"ok":true,"terminal":false,"status":"queued"});
    assert_eq!(startup_observation(&queued, false, Duration::ZERO, STARTUP_BUDGET), Ok(false));
    assert!(startup_observation(&queued, true, Duration::ZERO, STARTUP_BUDGET).is_err());
    let running = json!({"ok":true,"terminal":false,"status":"running"});
    assert_eq!(startup_observation(&running, false, Duration::from_secs(9), STARTUP_BUDGET), Ok(false));
    assert_eq!(startup_observation(&running, true, Duration::from_secs(9), STARTUP_BUDGET), Ok(true));
}

#[test]
fn startup_failure_and_late_readiness_remain_hard_failures() {
    let failed = json!({"ok":true,"terminal":true,"status":"failed"});
    for ready in [false, true] {
        assert!(startup_observation(&failed, ready, Duration::ZERO, STARTUP_BUDGET).is_err());
        let running = json!({"ok":true,"terminal":false,"status":"running"});
        assert!(startup_observation(&running, ready, STARTUP_BUDGET, STARTUP_BUDGET).is_err());
    }
    assert!(startup_observation(&json!({"ok":false}), true, Duration::ZERO, STARTUP_BUDGET).is_err());
}

fn completed() -> Value {
    json!({"ok":true,"terminal":true,"status":"succeeded","command_ok":true,
        "result":{"exit_code":0,"termination_reason":"exited","output_complete":true,"process_may_be_running":false}})
}

#[test]
fn drain_requires_both_natural_completion_and_released_lease() {
    let running = json!({"ok":true,"terminal":false,"status":"running"});
    assert_eq!(drain_observation(&running, "draining", Duration::ZERO, DRAIN_BUDGET), Ok(false));
    assert!(drain_observation(&running, "free", Duration::ZERO, DRAIN_BUDGET).is_err());
    assert_eq!(drain_observation(&completed(), "draining", Duration::ZERO, DRAIN_BUDGET), Ok(false));
    assert_eq!(drain_observation(&completed(), "free", Duration::ZERO, DRAIN_BUDGET), Ok(true));
}

#[test]
fn timeouts_cancellation_missing_output_and_unknown_processes_cannot_pass_drain() {
    for field in ["termination_reason", "exit_code", "output_complete", "process_may_be_running"] {
        let mut task = completed();
        task["result"][field] = Value::Null;
        assert!(drain_observation(&task, "free", Duration::ZERO, DRAIN_BUDGET).is_err(), "{field}");
    }
    for status in ["timed_out", "cancelled", "failed", "interrupted"] {
        let mut task = completed(); task["status"] = json!(status);
        assert!(drain_observation(&task, "free", Duration::ZERO, DRAIN_BUDGET).is_err(), "{status}");
    }
    assert!(drain_observation(&completed(), "free", DRAIN_BUDGET, DRAIN_BUDGET).is_err());
}
