use super::*;
use std::{sync::{atomic::{AtomicBool, AtomicUsize, Ordering}, Barrier}, time::Duration};

fn fixture() -> (tempfile::TempDir, tempfile::TempDir, Arc<ToolContext>, ListenerContextLease) {
    let root = tempfile::tempdir().unwrap();
    let history = tempfile::tempdir().unwrap();
    let context = Arc::new(ToolContext::for_test(root.path().into(), history.path().into()).unwrap());
    let lease = ListenerContextLease::new(context.clone());
    (root, history, context, lease)
}

#[test]
fn returns_the_original_context_and_execution_gate_not_a_replacement() {
    let (_root, _history, context, lease) = fixture();
    lease.with_live(|bound| {
        assert!(Arc::ptr_eq(bound, &context));
        assert!(Arc::ptr_eq(&bound.execution_gate(), &context.execution_gate()));
        assert!(Arc::ptr_eq(&bound.exec_tasks, &context.exec_tasks));
        assert!(Arc::ptr_eq(&bound.sessions, &context.sessions));
    }).unwrap();
}

#[test]
fn native_pause_is_visible_through_the_same_context() {
    let (_root, _history, context, lease) = fixture();
    let generation = context.execution_gate().pause().unwrap().generation;
    lease.with_live(|bound| {
        let current = bound.execution_gate().snapshot();
        assert_eq!(current.generation, generation);
        assert_eq!(current.availability, crate::runtime::ExecutionAvailability::Offline);
    }).unwrap();
}

#[test]
fn closing_does_not_change_legacy_admitted_job_gate_semantics() {
    let (_root, _history, context, lease) = fixture();
    let before = context.execution_gate().snapshot();
    lease.close();
    let after = context.execution_gate().snapshot();
    assert_eq!(before.generation, after.generation);
    assert_eq!(before.availability, after.availability);
}

#[test]
fn close_winner_never_invokes_a_registration_factory() {
    let (_root, _history, _context, lease) = fixture();
    let calls = AtomicUsize::new(0);
    lease.close();
    assert_eq!(lease.with_live(|_| { calls.fetch_add(1, Ordering::SeqCst); }), Err(ListenerLeaseError::Closed));
    assert_eq!(calls.load(Ordering::SeqCst), 0);
    assert!(!lease.is_live());
}

#[test]
fn accepted_registration_and_close_share_one_linearization_boundary() {
    let (_root, _history, _context, lease) = fixture();
    let entered = Arc::new(Barrier::new(2));
    let release = Arc::new(Barrier::new(2));
    let closed = Arc::new(AtomicBool::new(false));
    let active = lease.clone();
    let e = entered.clone(); let r = release.clone();
    let worker = std::thread::spawn(move || active.with_live(|_| { e.wait(); r.wait(); }).unwrap());
    entered.wait();
    let target = lease.clone(); let completed = closed.clone();
    let closer = std::thread::spawn(move || { target.close(); completed.store(true, Ordering::SeqCst); });
    // The registration holds the synchronization boundary until released;
    // no sleep or assumption about how quickly the closer gets scheduled.
    assert!(!closed.load(Ordering::SeqCst));
    release.wait(); worker.join().unwrap(); closer.join().unwrap();
    assert!(closed.load(Ordering::SeqCst));
    assert_eq!(lease.with_live(|_| ()), Err(ListenerLeaseError::Closed));
}

#[test]
fn old_listener_close_cannot_close_a_successor_lease() {
    let (_root, _history, context, old) = fixture();
    let new = ListenerContextLease::new(context);
    assert_ne!(new.generation(), old.generation());
    old.close();
    assert!(new.is_live());
    assert!(new.with_live(|_| ()).is_ok());
}

#[test]
fn dropping_any_nonowning_clone_does_not_close_a_live_listener() {
    let (_root, _history, _context, lease) = fixture();
    let copy = lease.clone(); drop(copy);
    assert!(lease.is_live());
    let guard = lease.lifetime_guard(); drop(guard);
    assert!(!lease.is_live());
}

#[test]
fn retained_context_does_not_reopen_a_closed_lease() {
    let (_root, _history, _context, lease) = fixture();
    let retained = lease.with_live(Arc::clone).unwrap();
    lease.close();
    assert!(retained.workspace.root().is_dir());
    assert_eq!(lease.with_live(|_| ()), Err(ListenerLeaseError::Closed));
}

#[test]
fn panicking_registration_seals_the_lease_and_resumes_unwinding() {
    let (_root, _history, _context, lease) = fixture();
    let result = catch_unwind(AssertUnwindSafe(|| {
        let _ = lease.with_live(|_| panic!("controlled native startup panic"));
    }));
    assert!(result.is_err());
    assert!(!lease.is_live());
    assert_eq!(lease.with_live(|_| ()), Err(ListenerLeaseError::Closed));
}

#[test]
fn debug_and_errors_do_not_include_workspace_or_credentials() {
    let (root, _history, _context, lease) = fixture();
    let debug = format!("{lease:?}");
    assert!(!debug.contains(&root.path().to_string_lossy().to_string()));
    assert!(!debug.contains("ToolContext"));
    assert_eq!(ListenerLeaseError::Closed.to_string(), "listener_context_closed");
    assert_eq!(ListenerLeaseError::StateUnavailable.to_string(), "listener_context_unavailable");
}

#[tokio::test]
async fn all_waiters_observe_close_including_late_subscribers() {
    let (_root, _history, _context, lease) = fixture();
    let mut waiters = Vec::new();
    for _ in 0..8 {
        let copy = lease.clone();
        waiters.push(tokio::spawn(async move { copy.wait_closed().await; }));
    }
    lease.close(); lease.close();
    for waiter in waiters { tokio::time::timeout(Duration::from_secs(2), waiter).await.unwrap().unwrap(); }
    tokio::time::timeout(Duration::from_secs(2), lease.wait_closed()).await.unwrap();
}

#[tokio::test]
async fn cancellation_of_one_waiter_preserves_the_other_observers() {
    let (_root, _history, _context, lease) = fixture();
    let copy = lease.clone();
    let waiter = tokio::spawn(async move { copy.wait_closed().await; });
    tokio::task::yield_now().await;
    waiter.abort(); assert!(waiter.await.is_err());
    assert!(lease.is_live());
    drop(lease.lifetime_guard());
    tokio::time::timeout(Duration::from_secs(2), lease.wait_closed()).await.unwrap();
}

#[tokio::test]
async fn cancelled_never_polled_listener_future_still_invalidates_its_lease() {
    let (_root, _history, _context, lease) = fixture();
    let lifetime = lease.lifetime_guard();
    let task = tokio::spawn(async move { let _lifetime = lifetime; std::future::pending::<()>().await; });
    // Current-thread runtime: no yield occurs between spawn and abort.
    task.abort(); assert!(task.await.is_err());
    assert!(!lease.is_live());
}

#[tokio::test]
async fn listener_task_panic_invalidates_retained_context_observers() {
    let (_root, _history, _context, lease) = fixture();
    let lifetime = lease.lifetime_guard();
    let task = tokio::spawn(async move { let _lifetime = lifetime; panic!("controlled listener panic"); });
    assert!(task.await.unwrap_err().is_panic());
    tokio::time::timeout(Duration::from_secs(2), lease.wait_closed()).await.unwrap();
    assert_eq!(lease.with_live(|_| ()), Err(ListenerLeaseError::Closed));
}
