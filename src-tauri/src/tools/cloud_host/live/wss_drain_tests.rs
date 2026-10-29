//! The real desktop host, not the FileHost adapter: cancellation of native work
//! must not unlock the execution ledger while it is still running.
use super::*;
use coding_tools_cloud_agent::{
    lifecycle::{AgentLifecycle, LifecycleError, RunHandle, RunOutcome},
    managed::AgentStart,
};
use uuid::Uuid;

async fn managed() -> (Harness, AgentLifecycle, RunHandle) {
    let mut h = Harness::start().await;
    h.stop_agent().await;
    h.wait("ready", false).await;
    let manager = AgentLifecycle::new(1).unwrap();
    let run = AgentStart::new(h.config.clone(), h.key.clone(), h.journal.clone(), false)
        .unwrap()
        .launch(&manager, Uuid::new_v4(), h.host.clone())
        .unwrap();
    h.wait("ready", true).await;
    (h, manager, run)
}
async fn sealed(h: &Harness) {
    tokio::time::timeout(Duration::from_secs(5), async {
        while !h.host.work.status().sealed {
            tokio::task::yield_now().await;
        }
    })
    .await
    .expect("native drain was not sealed");
}
fn assert_journal_locked(h: &Harness) {
    // Do not initialize/replace a ledger. Merely attempt the existing journal's
    // exclusive lock using the same trusted fixture configuration.
    assert!(HostAgent::open(&h.config, &h.key, &h.journal, false, h.host.clone()).is_err());
}
fn assert_journal_released(h: &Harness) {
    let opened = HostAgent::open(&h.config, &h.key, &h.journal, false, h.host.clone());
    assert!(
        opened.is_ok(),
        "ledger stayed locked after proven native drain"
    );
    drop(opened);
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn managed_native_approval_dispatch_and_stop_release_only_after_drain() {
    let (h, manager, run) = managed().await;
    h.approve("native-A", "eligible_a").await;
    let out = h.rpc(7080, "native-A", "workspace_probe", json!({})).await;
    assert_eq!(out["ok"], true);
    assert_eq!(out["execution"], "native_tool_dispatch");
    assert_journal_locked(&h);
    assert_eq!(
        manager.stop(&run, Duration::from_secs(6)).await,
        Ok(RunOutcome::Drained)
    );
    let status = h.host.work.status();
    assert!(status.sealed && status.outstanding == 0 && !status.unconfirmed);
    assert_journal_released(&h);
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn cancelled_native_waiter_keeps_real_journal_locked_until_callback_finishes() {
    let (h, manager, run) = managed().await;
    let (started, observed) = tokio::sync::oneshot::channel();
    let (release, held) = std::sync::mpsc::channel();
    let callback = crate::tools::native_drain::blocking(&h.host.work, move |_| {
        let _ = started.send(());
        held.recv_timeout(Duration::from_secs(12))
            .map_err(|_| AgentError::ExecutionUnknown)?;
        Ok(())
    });
    let waiter = tokio::spawn(callback);
    tokio::time::timeout(Duration::from_secs(3), observed)
        .await
        .unwrap()
        .unwrap();
    waiter.abort();
    assert!(waiter.await.unwrap_err().is_cancelled());
    manager.request_stop(&run).unwrap();
    sealed(&h).await;
    assert_eq!(
        manager.stop(&run, Duration::from_millis(40)).await,
        Err(LifecycleError::StopTimedOut)
    );
    assert_journal_locked(&h);
    assert!(h.host.work.status().outstanding >= 1);
    release.send(()).unwrap();
    assert_eq!(
        run.wait(Duration::from_secs(6)).await,
        Ok(RunOutcome::Drained)
    );
    assert_journal_released(&h);
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn queued_native_callback_after_stop_is_rejected_before_effects() {
    let (h, manager, run) = managed().await;
    let called = Arc::new(std::sync::atomic::AtomicBool::new(false));
    let observed = called.clone();
    // The returned future owns a registration but has never started a worker.
    let queued = crate::tools::native_drain::blocking(&h.host.work, move |_| {
        observed.store(true, std::sync::atomic::Ordering::SeqCst);
        Ok(())
    });
    manager.request_stop(&run).unwrap();
    sealed(&h).await;
    assert_eq!(
        run.wait(Duration::from_millis(40)).await,
        Err(LifecycleError::StopTimedOut)
    );
    assert_journal_locked(&h);
    assert_eq!(queued.await, Err(AgentError::LocalAuthority));
    assert!(!called.load(std::sync::atomic::Ordering::SeqCst));
    assert_eq!(
        run.wait(Duration::from_secs(6)).await,
        Ok(RunOutcome::Drained)
    );
    assert_journal_released(&h);
}
