use super::*;
use std::sync::atomic::{AtomicUsize, Ordering};
#[cfg(windows)]
use std::sync::{atomic::AtomicBool, Arc};

fn outcome(termination: ExecTermination) -> ExecOutcome {
    ExecOutcome {
        session_id: "completion-test".into(),
        termination,
        exit_code: Some(0),
        stdout: Vec::new(),
        stderr: Vec::new(),
        stdout_total_bytes: 0,
        stderr_total_bytes: 0,
        stdout_truncated: false,
        stderr_truncated: false,
        output_complete: true,
        duration_ms: 0,
    }
}

#[tokio::test]
async fn nonzero_then_zero_requires_both_observations() {
    let mut calls = 0;
    let result = confirm_empty(
        || {
            calls += 1;
            Ok(calls == 2)
        },
        Instant::now() + Duration::from_secs(1),
    )
    .await;
    assert!(result);
    assert_eq!(calls, 2);
}

#[tokio::test]
async fn query_error_never_reaches_a_later_zero() {
    let mut calls = 0;
    let result = confirm_empty(
        || {
            calls += 1;
            if calls == 1 {
                Err(io::Error::other("injected query error"))
            } else {
                Ok(true)
            }
        },
        Instant::now() + Duration::from_secs(1),
    )
    .await;
    assert!(!result);
    assert_eq!(calls, 1);
}

#[tokio::test]
async fn exhausted_deadline_never_queries_or_accepts_zero() {
    let calls = AtomicUsize::new(0);
    let result = confirm_empty(
        || {
            calls.fetch_add(1, Ordering::SeqCst);
            Ok(true)
        },
        Instant::now(),
    )
    .await;
    assert!(!result);
    assert_eq!(calls.load(Ordering::SeqCst), 0);
}

#[tokio::test]
async fn zero_returning_after_deadline_is_uncertain() {
    let result = confirm_empty(
        || {
            std::thread::sleep(Duration::from_millis(30));
            Ok(true)
        },
        Instant::now() + Duration::from_millis(10),
    )
    .await;
    assert!(!result);
}

#[tokio::test]
async fn persistent_nonzero_exhausts_one_deadline() {
    assert!(!confirm_empty(|| Ok(false), Instant::now() + Duration::from_millis(45),).await);
}

#[tokio::test]
async fn publication_preserves_original_reasons_and_sticky_uncertainty() {
    for reason in [
        ExecTermination::Exited,
        ExecTermination::TimedOut,
        ExecTermination::Cancelled,
        ExecTermination::OutputLimit,
        ExecTermination::OutputError,
        ExecTermination::StdinError,
        ExecTermination::TerminationUncertain,
    ] {
        let (tx, rx) = watch::channel(None);
        publish(
            tx,
            outcome(reason),
            true,
            || Ok(true),
            std::time::Instant::now(),
        )
        .await;
        assert_eq!(rx.borrow().as_ref().unwrap().termination, reason);
    }
}

#[tokio::test]
async fn missing_child_or_io_settlement_prevents_confirmed_publication() {
    for (child_waited, io_joined) in [(false, true), (true, false), (false, false)] {
        let (tx, rx) = watch::channel(None);
        publish(
            tx,
            outcome(ExecTermination::Exited),
            child_waited && io_joined,
            || Ok(true),
            std::time::Instant::now(),
        )
        .await;
        let published = rx.borrow().clone().unwrap();
        assert_eq!(published.termination, ExecTermination::TerminationUncertain);
        assert!(!published.command_ok());
    }
}

#[tokio::test]
async fn failed_query_prevents_success_despite_zero_exit_and_complete_streams() {
    let (tx, rx) = watch::channel(None);
    publish(
        tx,
        outcome(ExecTermination::Exited),
        true,
        || Err(io::Error::other("owned job unavailable")),
        std::time::Instant::now(),
    )
    .await;
    let published = rx.borrow().clone().unwrap();
    assert_eq!(published.exit_code, Some(0));
    assert!(published.output_complete);
    assert_eq!(published.termination, ExecTermination::TerminationUncertain);
    assert!(!published.command_ok());
}

#[cfg(windows)]
fn help_spec() -> super::super::ExecSpec {
    super::super::ExecSpec::new(
        vec![
            std::env::current_exe().unwrap().display().to_string(),
            "--help".into(),
        ],
        std::env::current_dir().unwrap(),
    )
    .unwrap()
}

#[cfg(windows)]
async fn wait_for_query(calls: &AtomicUsize) {
    tokio::time::timeout(Duration::from_secs(5), async {
        while calls.load(Ordering::SeqCst) == 0 {
            tokio::time::sleep(Duration::from_millis(5)).await;
        }
    })
    .await
    .expect("supervisor must reach query");
}

#[cfg(windows)]
#[tokio::test]
async fn real_supervisor_keeps_watch_and_capacity_pending_until_job_zero() {
    use super::super::{ExecErrorKind, ProcessManager};
    let calls = Arc::new(AtomicUsize::new(0));
    let release = Arc::new(AtomicBool::new(false));
    let mut spec = help_spec().with_tree_exit_confirmation();
    let observed = calls.clone();
    let gate = release.clone();
    spec.tree_exit_query = Some(Arc::new(move || {
        observed.fetch_add(1, Ordering::SeqCst);
        Ok(gate.load(Ordering::SeqCst))
    }));
    let manager = ProcessManager::new(1).unwrap();
    let mut session = manager.start(spec).await.unwrap();
    wait_for_query(&calls).await;
    let unpublished = session.snapshot().is_none();
    let capacity = manager.start(help_spec()).await.unwrap_err().kind;
    release.store(true, Ordering::SeqCst);
    let result = session.wait().await;
    assert!(unpublished, "nonzero owned Job must hold publication");
    assert_eq!(capacity, ExecErrorKind::Capacity);
    assert!(result.command_ok(), "{result:?}");
    assert!(calls.load(Ordering::SeqCst) >= 2);
}

#[cfg(windows)]
#[tokio::test]
async fn real_supervisor_query_error_stays_uncertain_without_retry() {
    use super::super::ProcessManager;
    let calls = Arc::new(AtomicUsize::new(0));
    let observed = calls.clone();
    let mut spec = help_spec().with_tree_exit_confirmation();
    spec.tree_exit_query = Some(Arc::new(move || {
        if observed.fetch_add(1, Ordering::SeqCst) == 0 {
            Err(io::Error::other("injected first query failure"))
        } else {
            Ok(true)
        }
    }));
    let result = ProcessManager::default().run(spec).await.unwrap();
    assert_eq!(result.termination, ExecTermination::TerminationUncertain);
    assert_eq!(result.exit_code, Some(0));
    assert!(result.output_complete);
    assert!(!result.command_ok());
    assert_eq!(calls.load(Ordering::SeqCst), 1);
}

#[cfg(windows)]
#[tokio::test]
async fn real_supervisor_default_never_calls_completion_observer() {
    use super::super::ProcessManager;
    let calls = Arc::new(AtomicUsize::new(0));
    let observed = calls.clone();
    let mut spec = help_spec();
    assert!(!spec.require_tree_exit);
    spec.tree_exit_query = Some(Arc::new(move || {
        observed.fetch_add(1, Ordering::SeqCst);
        Err(io::Error::other("default must not query"))
    }));
    let result = ProcessManager::default().run(spec).await.unwrap();
    assert!(result.command_ok(), "{result:?}");
    assert_eq!(calls.load(Ordering::SeqCst), 0);
}

#[cfg(windows)]
#[tokio::test]
async fn real_supervisor_drop_keeps_capacity_until_pending_job_proof_finishes() {
    use super::super::{ExecErrorKind, ProcessManager};
    let calls = Arc::new(AtomicUsize::new(0));
    let release = Arc::new(AtomicBool::new(false));
    let observed = calls.clone();
    let gate = release.clone();
    let mut spec = help_spec().with_tree_exit_confirmation();
    spec.tree_exit_query = Some(Arc::new(move || {
        observed.fetch_add(1, Ordering::SeqCst);
        Ok(gate.load(Ordering::SeqCst))
    }));
    let manager = ProcessManager::new(1).unwrap();
    let session = manager.start(spec).await.unwrap();
    wait_for_query(&calls).await;
    drop(session);
    let capacity = manager.start(help_spec()).await.unwrap_err().kind;
    release.store(true, Ordering::SeqCst);
    let mut replacement = tokio::time::timeout(Duration::from_secs(5), async {
        loop {
            match manager.start(help_spec()).await {
                Ok(session) => break session,
                Err(error) if error.kind == ExecErrorKind::Capacity => {
                    tokio::time::sleep(Duration::from_millis(5)).await;
                }
                Err(error) => panic!("unexpected replacement failure: {error}"),
            }
        }
    })
    .await
    .unwrap();
    let result = replacement.wait().await;
    assert_eq!(capacity, ExecErrorKind::Capacity);
    assert!(result.command_ok(), "{result:?}");
}

#[cfg(windows)]
#[tokio::test]
async fn real_supervisor_deadline_publishes_uncertain_never_success() {
    use super::super::ProcessManager;
    let calls = Arc::new(AtomicUsize::new(0));
    let observed = calls.clone();
    let mut spec = help_spec().with_tree_exit_confirmation();
    spec.tree_exit_query = Some(Arc::new(move || {
        observed.fetch_add(1, Ordering::SeqCst);
        Ok(false)
    }));
    let result = ProcessManager::default().run(spec).await.unwrap();
    assert_eq!(result.termination, ExecTermination::TerminationUncertain);
    assert_eq!(result.exit_code, Some(0));
    assert!(result.output_complete);
    assert!(!result.command_ok());
    assert!(calls.load(Ordering::SeqCst) >= 2);
}
