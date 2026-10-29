use super::*;
use std::{
    sync::{
        atomic::{AtomicBool, Ordering},
        Barrier,
    },
    time::Duration,
};
const SHORT: Duration = Duration::from_millis(30);
async fn drained(d: &WorkDrain) {
    tokio::time::timeout(Duration::from_secs(2), d.wait())
        .await
        .unwrap();
}
async fn blocked(d: &WorkDrain) {
    assert!(tokio::time::timeout(SHORT, d.wait()).await.is_err());
}
#[tokio::test]
async fn open_empty_is_not_a_shutdown_receipt() {
    let d = WorkDrain::new();
    blocked(&d).await;
    d.seal();
    drained(&d).await;
}
#[tokio::test]
async fn sealed_empty_is_drained_and_cannot_reopen() {
    let d = WorkDrain::new();
    d.seal();
    drained(&d).await;
    assert_eq!(d.register().unwrap_err(), WorkError::Closed);
}
#[tokio::test]
async fn queued_drop_is_known_not_started() {
    let d = WorkDrain::new();
    let g = d.register().unwrap();
    d.seal();
    drop(g);
    drained(&d).await;
    assert!(!d.status().unconfirmed);
}
#[tokio::test]
async fn seal_before_queued_start_rejects_without_side_effect() {
    let d = WorkDrain::new();
    let mut g = d.register().unwrap();
    d.seal();
    assert_eq!(g.begin(), Err(WorkError::Closed));
    drained(&d).await;
}
#[tokio::test]
async fn started_operation_holds_drain() {
    let d = WorkDrain::new();
    let mut g = d.register().unwrap();
    g.begin().unwrap();
    d.seal();
    blocked(&d).await;
    g.complete();
    drained(&d).await;
}
#[tokio::test]
async fn dropping_started_operation_permanently_quarantines() {
    let d = WorkDrain::new();
    let mut g = d.register().unwrap();
    g.begin().unwrap();
    drop(g);
    assert!(d.status().unconfirmed);
    assert_eq!(d.status().outstanding, 0);
    blocked(&d).await;
}
#[tokio::test]
async fn unknown_is_not_cleared_by_other_completions() {
    let d = WorkDrain::new();
    let mut a = d.register().unwrap();
    let mut b = d.register().unwrap();
    a.begin().unwrap();
    b.begin().unwrap();
    drop(a);
    b.complete();
    d.seal();
    blocked(&d).await;
}
#[tokio::test]
async fn registered_descendant_survives_parent_return() {
    let d = WorkDrain::new();
    let mut a = d.register().unwrap();
    a.begin().unwrap();
    let mut b = a.scope().fork().unwrap();
    a.complete();
    d.seal();
    b.begin().unwrap();
    blocked(&d).await;
    b.complete();
    drained(&d).await;
}
#[tokio::test]
async fn admitted_parent_can_fork_during_drain() {
    let d = WorkDrain::new();
    let mut a = d.register().unwrap();
    a.begin().unwrap();
    d.seal();
    let mut b = a.scope().fork().unwrap();
    b.begin().unwrap();
    a.complete();
    blocked(&d).await;
    b.complete();
    drained(&d).await;
}
#[test]
fn stale_scope_cannot_spawn_after_parent_completion() {
    let d = WorkDrain::new();
    let mut g = d.register().unwrap();
    g.begin().unwrap();
    let s = g.scope();
    g.complete();
    assert_eq!(s.fork().unwrap_err(), WorkError::Stale);
}
#[test]
fn queued_scope_cannot_spawn() {
    let d = WorkDrain::new();
    let g = d.register().unwrap();
    assert_eq!(g.scope().fork().unwrap_err(), WorkError::Stale);
}
#[test]
fn running_guard_cannot_begin_twice() {
    let d = WorkDrain::new();
    let mut g = d.register().unwrap();
    g.begin().unwrap();
    assert_eq!(g.begin(), Err(WorkError::Stale));
    g.complete();
}
#[test]
fn registrations_are_bounded() {
    let d = WorkDrain::new();
    let guards = (0..MAX_WORK)
        .map(|_| d.register().unwrap())
        .collect::<Vec<_>>();
    assert_eq!(d.register().unwrap_err(), WorkError::Capacity);
    drop(guards);
    assert_eq!(d.status().outstanding, 0);
}
#[test]
fn descendants_share_capacity() {
    let d = WorkDrain::new();
    let mut g = d.register().unwrap();
    g.begin().unwrap();
    let guards = (1..MAX_WORK)
        .map(|_| g.scope().fork().unwrap())
        .collect::<Vec<_>>();
    assert_eq!(g.scope().fork().unwrap_err(), WorkError::Capacity);
    drop(guards);
    g.complete();
}
#[tokio::test]
async fn cancelling_waiter_does_not_cancel_or_retire_work() {
    let d = WorkDrain::new();
    let mut g = d.register().unwrap();
    g.begin().unwrap();
    d.seal();
    let c = d.clone();
    let t = tokio::spawn(async move { c.wait().await });
    t.abort();
    let _ = t.await;
    assert_eq!(d.status().outstanding, 1);
    g.complete();
    drained(&d).await;
}
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn aborting_blocking_waiter_keeps_real_callback_registered() {
    let d = WorkDrain::new();
    let mut g = d.register().unwrap();
    let (started, rx) = tokio::sync::oneshot::channel();
    let gate = Arc::new(Barrier::new(2));
    let b = gate.clone();
    let waiting = tokio::spawn(async move {
        tokio::task::spawn_blocking(move || {
            g.begin().unwrap();
            let _ = started.send(());
            b.wait();
            g.complete();
        })
        .await
        .unwrap();
    });
    rx.await.unwrap();
    waiting.abort();
    let _ = waiting.await;
    d.seal();
    blocked(&d).await;
    gate.wait();
    drained(&d).await;
}
#[tokio::test]
async fn aborting_running_async_work_quarantines() {
    let d = WorkDrain::new();
    let mut g = d.register().unwrap();
    let (s, r) = tokio::sync::oneshot::channel();
    let t = tokio::spawn(async move {
        g.begin().unwrap();
        s.send(()).unwrap();
        std::future::pending::<()>().await;
        g.complete();
    });
    r.await.unwrap();
    t.abort();
    let _ = t.await;
    assert!(d.status().unconfirmed);
    blocked(&d).await;
}
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn multiple_waiters_all_observe_completion() {
    let d = WorkDrain::new();
    let mut g = d.register().unwrap();
    g.begin().unwrap();
    d.seal();
    let mut waiters = Vec::new();
    for _ in 0..16 {
        let c = d.clone();
        waiters.push(tokio::spawn(async move { c.wait().await }));
    }
    g.complete();
    for t in waiters {
        tokio::time::timeout(Duration::from_secs(2), t)
            .await
            .unwrap()
            .unwrap();
    }
}
#[tokio::test]
async fn completion_before_first_wait_poll_is_observed() {
    let d = WorkDrain::new();
    let mut g = d.register().unwrap();
    g.begin().unwrap();
    let f = d.wait();
    d.seal();
    g.complete();
    tokio::time::timeout(Duration::from_secs(1), f)
        .await
        .unwrap();
}
#[test]
fn concurrent_start_and_seal_never_lose_active_work() {
    for _ in 0..128 {
        let d = WorkDrain::new();
        let mut g = d.register().unwrap();
        let c = d.clone();
        let started = Arc::new(AtomicBool::new(false));
        let s = started.clone();
        let t = std::thread::spawn(move || {
            if g.begin().is_ok() {
                s.store(true, Ordering::Release);
                g
            } else {
                g
            }
        });
        c.seal();
        let g = t.join().unwrap();
        if started.load(Ordering::Acquire) {
            assert_eq!(d.status().outstanding, 1);
            g.complete();
        } else {
            assert_eq!(d.status().outstanding, 0);
        }
        assert!(!d.status().unconfirmed);
    }
}
#[test]
fn scope_debug_does_not_expose_registry_identity() {
    let d = WorkDrain::new();
    let g = d.register().unwrap();
    for s in [
        format!("{d:?}"),
        format!("{g:?}"),
        format!("{:?}", g.scope()),
    ] {
        assert!(s.contains("[REDACTED]"));
    }
}
#[tokio::test]
async fn panic_is_not_a_drain_receipt() {
    let d = WorkDrain::new();
    let mut g = d.register().unwrap();
    let _ = std::panic::catch_unwind(move || {
        g.begin().unwrap();
        panic!("test-owned work panic")
    });
    assert!(d.status().unconfirmed);
    blocked(&d).await;
}
