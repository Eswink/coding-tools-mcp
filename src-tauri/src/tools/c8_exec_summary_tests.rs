//! A1 C8 (SPEC §2.3, §7 C8 row): a worker-tagged exec task summary carries
//! `worker_id`; an untagged one keeps exactly its pre-C8 bytes.
use super::state::{Job, Status};
use super::ExecTaskStore;
use serde_json::json;

/// The untagged summary keys as of C7 (b8af8834), sorted.
const UNTAGGED_KEYS: [&str; 21] = [
    "accepted",
    "cancel_requested",
    "cancellation_scope",
    "command_ok",
    "completed_at",
    "created_at",
    "elapsed_ms",
    "execution_survives_app_restart",
    "execution_timeout_ms",
    "job_id",
    "next_action",
    "persistence_failed",
    "poll_after_ms",
    "recovery_scope",
    "request_id",
    "restart_recoverable",
    "result",
    "result_ttl_ms",
    "status",
    "terminal",
    "timestamp_unit",
];

#[test]
fn c8_untagged_summary_is_unchanged_and_a_tag_only_adds_worker_id() {
    let mut job = Job::new("req-c8".into(), "fp".into(), 1000, false);
    job.finish(Status::Succeeded, json!({"stdout": "x", "stderr": ""}));
    let untagged = job.summary();
    let mut keys: Vec<&str> = untagged
        .as_object()
        .unwrap()
        .keys()
        .map(String::as_str)
        .collect();
    keys.sort_unstable();
    assert_eq!(keys, UNTAGGED_KEYS, "untagged summary key set changed");
    assert!(untagged.get("worker_id").is_none(), "{untagged}");

    let worker = "ab".repeat(16);
    job.worker_id = Some(worker.clone());
    let mut tagged = job.summary();
    assert_eq!(tagged["worker_id"], json!(worker), "{tagged}");
    tagged.as_object_mut().unwrap().remove("worker_id");
    assert_eq!(
        serde_json::to_string(&tagged).unwrap(),
        serde_json::to_string(&untagged).unwrap(),
        "the tag must be the only difference"
    );
}

#[test]
fn c8_restored_tagged_job_summary_keeps_worker_id() {
    let dir = tempfile::tempdir().unwrap();
    let root = dir.path().join("journal");
    let worker = "cd".repeat(16);
    let store = ExecTaskStore::shared(root.clone());
    let (job, fresh) = store
        .reserve_tagged("req-tagged", "fp", 1000, Some(&worker), || Ok(()))
        .unwrap();
    assert!(fresh);
    assert_eq!(job.summary()["worker_id"], json!(worker));
    let (plain, _) = store.reserve("req-plain", "fp", 1000).unwrap();
    assert!(plain.summary().get("worker_id").is_none());
    drop((job, plain, store));
    let restored = ExecTaskStore::shared(root);
    let (same, fresh) = restored
        .reserve_tagged("req-tagged", "fp", 1000, Some(&worker), || Ok(()))
        .unwrap();
    assert!(!fresh);
    assert_eq!(
        same.summary()["worker_id"],
        json!(worker),
        "{}",
        same.summary()
    );
    let (plain, fresh) = restored.reserve("req-plain", "fp", 1000).unwrap();
    assert!(!fresh);
    assert!(
        plain.summary().get("worker_id").is_none(),
        "{}",
        plain.summary()
    );
}
