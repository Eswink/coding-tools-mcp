use super::*;
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use tokio::sync::oneshot;
const BUDGET: Duration = Duration::from_secs(3);
fn key() -> Uuid {
    Uuid::new_v4()
}
async fn stopped(mut stop: watch::Receiver<bool>) -> TaskExit {
    while !*stop.borrow_and_update() {
        if stop.changed().await.is_err() {
            break;
        }
    }
    TaskExit::Drained
}

#[test]
fn capacity_and_workspace_are_bounded() {
    assert!(matches!(
        AgentLifecycle::new(0),
        Err(LifecycleError::InvalidCapacity)
    ));
    assert!(matches!(
        AgentLifecycle::new(MAX_MANAGED_AGENTS + 1),
        Err(LifecycleError::InvalidCapacity)
    ));
    assert!(AgentLifecycle::new(MAX_MANAGED_AGENTS).is_ok());
}
#[test]
fn no_runtime_does_not_reserve_a_slot() {
    let m = AgentLifecycle::new(1).unwrap();
    let k = key();
    assert!(matches!(
        m.launch(k, stopped),
        Err(LifecycleError::RuntimeUnavailable)
    ));
    assert!(m.current(k).unwrap().is_none());
}
#[tokio::test]
async fn nil_workspace_is_rejected_without_invoking_factory() {
    let m = AgentLifecycle::new(1).unwrap();
    assert!(matches!(
        m.launch(Uuid::nil(), |_| async { panic!("must not execute") }),
        Err(LifecycleError::InvalidWorkspace)
    ));
}
#[tokio::test]
async fn shutdown_before_first_poll_never_invokes_factory() {
    let m = AgentLifecycle::new(1).unwrap();
    let calls = Arc::new(AtomicUsize::new(0));
    let c = calls.clone();
    let h = m
        .launch(key(), move |_| {
            c.fetch_add(1, Ordering::SeqCst);
            async { TaskExit::Drained }
        })
        .unwrap();
    // current-thread runtime has not polled the spawned task yet.
    assert_eq!(h.phase().unwrap(), Some(Phase::Queued));
    m.request_shutdown();
    assert_eq!(h.wait(BUDGET).await, Ok(RunOutcome::NotStarted));
    assert_eq!(calls.load(Ordering::SeqCst), 0);
}
#[tokio::test]
async fn stop_before_first_poll_never_invokes_factory_and_can_restart() {
    let m = AgentLifecycle::new(1).unwrap();
    let k = key();
    let h = m
        .launch(k, |_| async { panic!("queued factory was invoked") })
        .unwrap();
    assert_eq!(m.stop(&h, BUDGET).await, Ok(RunOutcome::NotStarted));
    let next = m.launch(k, |_| async { TaskExit::Drained }).unwrap();
    assert!(next.generation() > h.generation());
    assert_eq!(next.wait(BUDGET).await, Ok(RunOutcome::Drained));
}
#[tokio::test]
async fn permanent_shutdown_rejects_late_registration() {
    let m = AgentLifecycle::new(1).unwrap();
    m.shutdown(BUDGET).await.unwrap();
    assert!(m.is_closed());
    assert!(matches!(
        m.launch(key(), stopped),
        Err(LifecycleError::Closed)
    ));
    m.shutdown(BUDGET).await.unwrap();
}
#[tokio::test]
async fn running_task_receives_stop_before_capacity_is_released() {
    let m = AgentLifecycle::new(1).unwrap();
    let k = key();
    let (tx, rx) = oneshot::channel();
    let h = m
        .launch(k, move |cancel| async move {
            tx.send(()).unwrap();
            stopped(cancel).await
        })
        .unwrap();
    rx.await.unwrap();
    assert_eq!(h.phase().unwrap(), Some(Phase::Running));
    assert_eq!(m.stop(&h, BUDGET).await, Ok(RunOutcome::Drained));
    assert!(m.current(k).unwrap().is_none());
}
#[tokio::test]
async fn duplicate_workspace_is_rejected_not_queued() {
    let m = AgentLifecycle::new(2).unwrap();
    let k = key();
    let h = m.launch(k, stopped).unwrap();
    assert!(matches!(m.launch(k, stopped), Err(LifecycleError::Busy)));
    m.stop(&h, BUDGET).await.unwrap();
}
#[tokio::test]
async fn global_capacity_is_held_until_exit() {
    let m = AgentLifecycle::new(1).unwrap();
    let h = m.launch(key(), stopped).unwrap();
    assert!(matches!(
        m.launch(key(), stopped),
        Err(LifecycleError::Capacity)
    ));
    m.stop(&h, BUDGET).await.unwrap();
    let next = m.launch(key(), stopped).unwrap();
    m.stop(&next, BUDGET).await.unwrap();
}
#[tokio::test]
async fn stop_timeout_does_not_free_the_workspace_or_global_slot() {
    let m = AgentLifecycle::new(1).unwrap();
    let k = key();
    let (started, ready) = oneshot::channel();
    let (release, finish) = oneshot::channel();
    let h = m
        .launch(k, move |_| async move {
            started.send(()).unwrap();
            finish.await.unwrap();
            TaskExit::Drained
        })
        .unwrap();
    ready.await.unwrap();
    assert_eq!(
        m.stop(&h, Duration::from_millis(10)).await,
        Err(LifecycleError::StopTimedOut)
    );
    assert_eq!(h.phase().unwrap(), Some(Phase::Stopping));
    assert!(matches!(m.launch(k, stopped), Err(LifecycleError::Busy)));
    assert!(matches!(
        m.launch(key(), stopped),
        Err(LifecycleError::Capacity)
    ));
    release.send(()).unwrap();
    assert_eq!(h.wait(BUDGET).await, Ok(RunOutcome::Drained));
}
#[tokio::test]
async fn cancelled_stop_waiter_does_not_forget_running_task() {
    let m = Arc::new(AgentLifecycle::new(1).unwrap());
    let k = key();
    let (s, r) = oneshot::channel();
    let (tx, rx) = oneshot::channel();
    let h = m
        .launch(k, move |_| async move {
            s.send(()).unwrap();
            rx.await.unwrap();
            TaskExit::Drained
        })
        .unwrap();
    r.await.unwrap();
    let other = m.clone();
    let handle = h.clone();
    let waiter = tokio::spawn(async move { other.stop(&handle, BUDGET).await });
    tokio::time::timeout(BUDGET, async {
        while h.phase().unwrap() != Some(Phase::Stopping) {
            tokio::task::yield_now().await;
        }
    })
    .await
    .unwrap();
    waiter.abort();
    let _ = waiter.await;
    assert!(matches!(m.launch(k, stopped), Err(LifecycleError::Busy)));
    tx.send(()).unwrap();
    h.wait(BUDGET).await.unwrap();
}
#[tokio::test]
async fn foreign_manager_handle_cannot_stop_same_workspace() {
    let a = AgentLifecycle::new(1).unwrap();
    let b = AgentLifecycle::new(1).unwrap();
    let k = key();
    let ha = a.launch(k, stopped).unwrap();
    let hb = b.launch(k, stopped).unwrap();
    assert_eq!(b.request_stop(&ha), Err(LifecycleError::ForeignHandle));
    assert_eq!(hb.phase().unwrap(), Some(Phase::Queued));
    a.shutdown(BUDGET).await.unwrap();
    b.shutdown(BUDGET).await.unwrap();
}
#[tokio::test]
async fn stale_handle_cannot_stop_new_generation() {
    let m = AgentLifecycle::new(1).unwrap();
    let k = key();
    let old = m.launch(k, |_| async { TaskExit::Drained }).unwrap();
    old.wait(BUDGET).await.unwrap();
    let new = m.launch(k, stopped).unwrap();
    assert_eq!(m.request_stop(&old), Err(LifecycleError::StaleHandle));
    assert_eq!(new.phase().unwrap(), Some(Phase::Queued));
    m.stop(&new, BUDGET).await.unwrap();
}
#[tokio::test]
async fn unconfirmed_exit_is_quarantined_and_never_restarts() {
    let m = AgentLifecycle::new(1).unwrap();
    let k = key();
    let h = m.launch(k, |_| async { TaskExit::Unconfirmed }).unwrap();
    assert_eq!(
        h.wait(BUDGET).await,
        Err(LifecycleError::TerminationUnconfirmed)
    );
    assert_eq!(h.phase().unwrap(), Some(Phase::Unconfirmed));
    assert!(matches!(m.launch(k, stopped), Err(LifecycleError::Busy)));
    assert!(matches!(
        m.launch(key(), stopped),
        Err(LifecycleError::Capacity)
    ));
    assert_eq!(
        m.shutdown(BUDGET).await,
        Err(LifecycleError::TerminationUnconfirmed)
    );
}
#[tokio::test]
async fn factory_panic_is_unconfirmed_not_successful_cleanup() {
    let m = AgentLifecycle::new(1).unwrap();
    let k = key();
    let h = m
        .launch(k, |_| {
            panic!("owned fixture factory panic");
            #[allow(unreachable_code)]
            async {
                TaskExit::Drained
            }
        })
        .unwrap();
    assert_eq!(
        h.wait(BUDGET).await,
        Err(LifecycleError::TerminationUnconfirmed)
    );
    assert_eq!(h.phase().unwrap(), Some(Phase::Unconfirmed));
}
#[tokio::test]
async fn asynchronous_panic_keeps_recovery_fence() {
    let m = AgentLifecycle::new(1).unwrap();
    let h = m
        .launch(key(), |_| async {
            tokio::task::yield_now().await;
            panic!("owned fixture future panic")
        })
        .unwrap();
    assert_eq!(
        h.wait(BUDGET).await,
        Err(LifecycleError::TerminationUnconfirmed)
    );
    assert_eq!(h.phase().unwrap(), Some(Phase::Unconfirmed));
}
#[test]
fn dropping_runtime_before_first_poll_releases_only_unstarted_reservation() {
    let m = AgentLifecycle::new(1).unwrap();
    let k = key();
    let rt = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .unwrap();
    let h = m
        .launch_on(rt.handle(), k, |_| async {
            panic!("never-polled factory executed")
        })
        .unwrap();
    drop(rt);
    assert_eq!(h.outcome(), Some(RunOutcome::NotStarted));
    assert!(m.current(k).unwrap().is_none());
}
#[test]
fn dropping_runtime_after_start_quarantines_instead_of_freeing() {
    let m = AgentLifecycle::new(1).unwrap();
    let k = key();
    let rt = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .unwrap();
    let (tx, rx) = oneshot::channel();
    let h = m
        .launch_on(rt.handle(), k, move |_| async move {
            tx.send(()).unwrap();
            std::future::pending::<TaskExit>().await
        })
        .unwrap();
    rt.block_on(rx).unwrap();
    drop(rt);
    assert_eq!(h.outcome(), Some(RunOutcome::Unconfirmed));
    assert_eq!(h.phase().unwrap(), Some(Phase::Unconfirmed));
}
#[tokio::test]
async fn dropping_owner_requests_stop_even_with_outstanding_handles() {
    let m = AgentLifecycle::new(1).unwrap();
    let (tx, rx) = oneshot::channel();
    let h = m
        .launch(key(), move |stop| async move {
            tx.send(()).unwrap();
            stopped(stop).await
        })
        .unwrap();
    rx.await.unwrap();
    drop(m);
    assert_eq!(h.wait(BUDGET).await, Ok(RunOutcome::Drained));
}
#[tokio::test]
async fn explicit_drained_failure_allows_a_new_generation() {
    let m = AgentLifecycle::new(1).unwrap();
    let k = key();
    let h = m.launch(k, |_| async { TaskExit::FailedDrained }).unwrap();
    assert_eq!(h.wait(BUDGET).await, Ok(RunOutcome::FailedDrained));
    let next = m.launch(k, stopped).unwrap();
    assert!(next.generation() > h.generation());
    m.stop(&next, BUDGET).await.unwrap();
}
#[tokio::test]
async fn shutdown_timeout_is_permanent_and_does_not_drop_workers() {
    let m = AgentLifecycle::new(1).unwrap();
    let (tx, rx) = oneshot::channel();
    let (s, r) = oneshot::channel();
    let h = m
        .launch(key(), move |_| async move {
            s.send(()).unwrap();
            rx.await.unwrap();
            TaskExit::Drained
        })
        .unwrap();
    r.await.unwrap();
    assert_eq!(
        m.shutdown(Duration::from_millis(10)).await,
        Err(LifecycleError::StopTimedOut)
    );
    assert!(m.is_closed());
    assert!(matches!(
        m.launch(key(), stopped),
        Err(LifecycleError::Closed)
    ));
    tx.send(()).unwrap();
    h.wait(BUDGET).await.unwrap();
    m.shutdown(BUDGET).await.unwrap();
}
#[tokio::test]
async fn completion_is_available_to_every_waiter() {
    let m = AgentLifecycle::new(1).unwrap();
    let h = m.launch(key(), |_| async { TaskExit::Drained }).unwrap();
    let copy = h.clone();
    let (a, b) = tokio::join!(h.wait(BUDGET), copy.wait(BUDGET));
    assert_eq!(a, Ok(RunOutcome::Drained));
    assert_eq!(b, a);
}
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn racing_launch_and_shutdown_never_start_after_shutdown_completion() {
    for _ in 0..128 {
        let m = Arc::new(AgentLifecycle::new(1).unwrap());
        let barrier = Arc::new(tokio::sync::Barrier::new(2));
        let closed = Arc::new(AtomicBool::new(false));
        let late = Arc::new(AtomicBool::new(false));
        let a = m.clone();
        let ba = barrier.clone();
        let c = closed.clone();
        let l = late.clone();
        let start = tokio::spawn(async move {
            ba.wait().await;
            a.launch(key(), move |stop| {
                if c.load(Ordering::SeqCst) {
                    l.store(true, Ordering::SeqCst);
                }
                stopped(stop)
            })
        });
        barrier.wait().await;
        m.shutdown(BUDGET).await.unwrap();
        closed.store(true, Ordering::SeqCst);
        match start.await.unwrap() {
            Ok(h) => {
                h.wait(BUDGET).await.unwrap();
            }
            Err(e) => assert_eq!(e, LifecycleError::Closed),
        }
        assert!(!late.load(Ordering::SeqCst));
    }
}
#[tokio::test]
async fn handle_debug_does_not_expose_workspace_or_manager_identity() {
    let m = AgentLifecycle::new(1).unwrap();
    let k = key();
    let h = m.launch(k, stopped).unwrap();
    let text = format!("{h:?}");
    assert!(!text.contains(&k.to_string()));
    assert!(!text.contains(&m.inner.identity.to_string()));
    m.stop(&h, BUDGET).await.unwrap();
}
#[tokio::test]
async fn generation_exhaustion_does_not_wrap_or_invoke_factory() {
    let m = AgentLifecycle::new(1).unwrap();
    m.inner.state.lock().unwrap().generation = u64::MAX;
    assert!(matches!(
        m.launch(key(), |_| async { panic!("overflow factory") }),
        Err(LifecycleError::Capacity)
    ));
}
