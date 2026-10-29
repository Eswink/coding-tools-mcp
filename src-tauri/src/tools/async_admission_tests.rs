use super::*;
use crate::tools::{context::ToolContext, exec_tasks};
use serde_json::json;
use std::{cell::RefCell, sync::mpsc, time::Instant};

thread_local! {
    static AFTER_ACCEPTANCE: RefCell<Option<Box<dyn FnOnce()>>> = RefCell::new(None);
    static BEFORE_LOCK: RefCell<Option<Box<dyn FnOnce()>>> = RefCell::new(None);
}
pub(super) fn before_lock() {
    BEFORE_LOCK.with(|hook| {
        if let Some(hook) = hook.borrow_mut().take() {
            hook();
        }
    });
}
pub(super) fn after_acceptance() {
    AFTER_ACCEPTANCE.with(|hook| {
        if let Some(hook) = hook.borrow_mut().take() {
            hook();
        }
    });
}
fn contended_submission(expires: bool) {
    let root = tempfile::tempdir().unwrap();
    let storage = tempfile::tempdir().unwrap();
    let mut ctx = ToolContext::for_test(root.path().into(), storage.path().into()).unwrap();
    ctx.exec_tasks = ExecTaskStore::shared(storage.path().join("durable-tasks"));
    let store = ctx.exec_tasks.clone();
    // Initialization is real encrypted storage. Hold precisely the mutex that
    // reserve must acquire after the caller's first submission check.
    let mut locked = store.inner.lock().unwrap();
    store.initialize(&mut locked).unwrap();
    let (cancel, rx) = tokio::sync::watch::channel(false);
    ctx.hook_cancel = Some(rx);
    let deadline = Instant::now() + Duration::from_secs(1);
    if expires {
        ctx.hook_deadline = Some(deadline);
    }
    let (at_lock, waiting) = mpsc::channel();
    let worker = std::thread::spawn(move || {
        BEFORE_LOCK
            .with(|hook| *hook.borrow_mut() = Some(Box::new(move || at_lock.send(()).unwrap())));
        exec_tasks::start(
            &ctx,
            &json!({"request_id":"contended-new", "cmd":"python3 -c \"from pathlib import Path; Path('primary-ran').write_text('bad')\"", "timeout_ms":1000}),
        )
    });
    waiting.recv_timeout(Duration::from_secs(5)).unwrap();
    // The handshake proves the initial caller check was passed. A real held
    // reservation lock prevents acceptance while we change the predicate.
    if expires {
        while Instant::now() < deadline {
            std::thread::yield_now();
        }
    } else {
        cancel.send(true).unwrap();
    }
    drop(locked);
    let result = worker.join().unwrap();
    let until = Instant::now() + Duration::from_secs(5);
    while store.has_unfinished_work() && Instant::now() < until {
        std::thread::yield_now();
    }
    assert!(
        result.is_err(),
        "expired/cancelled waiter was accepted: {result:?}"
    );
    assert!(store.list(None).unwrap().is_empty());
    assert!(store
        .inner
        .lock()
        .unwrap()
        .archive
        .as_ref()
        .unwrap()
        .load()
        .unwrap()
        .is_empty());
    assert!(!root.path().join("primary-ran").exists());
}
#[test]
fn cancellation_while_waiting_for_reservation_never_creates_a_job() {
    contended_submission(false);
}
#[test]
fn expiry_while_waiting_for_reservation_never_creates_a_job() {
    contended_submission(true);
}

fn accepted_then_cancelled(expires: bool) {
    let root = tempfile::tempdir().unwrap();
    let storage = tempfile::tempdir().unwrap();
    let mut ctx = ToolContext::for_test(root.path().into(), storage.path().into()).unwrap();
    ctx.exec_tasks = ExecTaskStore::shared(storage.path().join("durable-tasks"));
    let (cancel, rx) = tokio::sync::watch::channel(false);
    ctx.hook_cancel = Some(rx);
    let deadline = Instant::now() + Duration::from_secs(1);
    if expires {
        ctx.hook_deadline = Some(deadline);
    }
    AFTER_ACCEPTANCE.with(|hook| {
        *hook.borrow_mut() = Some(Box::new(move || {
            if expires {
                while Instant::now() < deadline {
                    std::thread::yield_now();
                }
            } else {
                cancel.send(true).unwrap();
            }
        }))
    });
    let args = json!({"request_id":"accepted-expired", "cmd":"python3 -c \"from pathlib import Path; Path('primary-ran').write_text('bad')\"", "timeout_ms":1000});
    let result = exec_tasks::start(&ctx, &args).unwrap();
    assert_eq!(result["error"]["code"], "EXEC_TASK_SUBMISSION_EXPIRED");
    assert_eq!(result["accepted"], true);
    assert!(!root.path().join("primary-ran").exists());
    let saved = ctx
        .exec_tasks
        .inner
        .lock()
        .unwrap()
        .archive
        .as_ref()
        .unwrap()
        .load()
        .unwrap();
    assert_eq!(saved.len(), 1);
    assert_eq!(saved[0]["status"], "failed");
    // A cancelled/expired transport may reconcile an existing key, never run it.
    let duplicate = exec_tasks::start(&ctx, &args).unwrap();
    assert_eq!(duplicate["deduplicated"], true);
    assert_eq!(duplicate["job_id"], result["job_id"]);
    assert_eq!(duplicate["status"], "failed");
    assert!(!root.path().join("primary-ran").exists());
    // Drop the entire supervisor and restore the same encrypted namespace.
    let path = ctx.exec_tasks.root.clone().unwrap();
    drop(ctx);
    let reopened = ExecTaskStore::shared(path);
    let records = reopened.list(None).unwrap();
    assert_eq!(records.len(), 1);
    assert_eq!(records[0]["status"], "failed");
    let (restored, created) = reopened
        .reserve(
            "accepted-expired",
            saved[0]["fingerprint"].as_str().unwrap(),
            1000,
        )
        .unwrap();
    assert!(!created);
    assert_eq!(restored.summary()["job_id"], result["job_id"]);
}
#[test]
fn cancellation_during_persistence_consumes_key_without_primary_or_replay() {
    accepted_then_cancelled(false);
}
#[test]
fn expiry_during_persistence_consumes_key_without_primary_or_replay() {
    accepted_then_cancelled(true);
}

#[test]
fn expired_existing_key_reconciles_without_revalidating_new_acceptance() {
    let store = ExecTaskStore::default();
    let (first, _) = store.reserve("existing", "fingerprint", 1000).unwrap();
    let (same, created) = store
        .reserve_checked("existing", "fingerprint", 1000, || {
            panic!("existing records must not require a fresh acceptance")
        })
        .unwrap();
    assert!(!created);
    assert_eq!(same.id, first.id);
    assert!(store
        .reserve_checked("existing", "different", 1000, || panic!(
            "conflict is not a fresh acceptance"
        ))
        .is_err());
}
