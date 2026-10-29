use super::*;

#[tokio::test]
async fn unpolled_future_never_allocates_or_executes() {
    let f = Fixture::new();
    let host = f.host();
    let call = f.call(false, "touch marker");
    drop(host.invoke(&call, &f.admission));
    assert_eq!(host.core.slots.available_permits(), MAX_ACTIVE as usize);
    host.revoke().await.unwrap();
    assert!(!f.root.join("marker").exists());
}

#[tokio::test]
async fn revoke_winning_before_start_rejects_the_queued_call() {
    let f = Fixture::new();
    let host = f.host();
    let call = f.call(true, "touch marker");
    let lock = host.core.open.lock().await;
    let mut work = Box::pin(host.invoke(&call, &f.admission));
    assert!(
        tokio::time::timeout(Duration::from_millis(20), work.as_mut())
            .await
            .is_err()
    );
    let mut revoke = Box::pin(host.revoke());
    assert!(
        tokio::time::timeout(Duration::from_millis(20), revoke.as_mut())
            .await
            .is_err()
    );
    drop(lock);
    let (r, w) = tokio::join!(revoke, work);
    r.unwrap();
    assert_eq!(w.unwrap_err().kind, ToolErrorKind::Unauthorized);
    assert!(!f.root.join("marker").exists());
}

#[tokio::test]
async fn cancelled_queued_call_never_starts_even_for_pty() {
    let f = Fixture::new();
    let host = f.host();
    let call = f.call(true, "touch marker");
    let lock = host.core.open.lock().await;
    let mut work = Box::pin(host.invoke(&call, &f.admission));
    assert!(
        tokio::time::timeout(Duration::from_millis(20), work.as_mut())
            .await
            .is_err()
    );
    drop(work);
    drop(lock);
    host.revoke().await.unwrap();
    assert!(!f.root.join("marker").exists());
}

#[tokio::test]
async fn revoke_cancels_running_process_and_pty_and_drains() {
    for pty in [false, true] {
        let f = Fixture::new();
        let host = f.host();
        let call = f.call(pty, "sleep 30 & echo $! > child; wait");
        let mut work = Box::pin(host.invoke(&call, &f.admission));
        until_file(&f.root.join("child"), &mut work).await;
        let pid: i32 = fs::read_to_string(f.root.join("child"))
            .unwrap()
            .trim()
            .parse()
            .unwrap();
        host.revoke().await.unwrap();
        let output = value(work.await.unwrap());
        assert_eq!(output["ok"], false);
        assert_eq!(output["authorization_ended"], true, "{output}");
        assert_eq!(host.core.slots.available_permits(), MAX_ACTIVE as usize);
        // A killed orphan may briefly await init reaping; it must not run.
        let status = fs::read_to_string(format!("/proc/{pid}/stat"));
        assert!(
            status.is_err()
                || status
                    .unwrap()
                    .split(')')
                    .nth(1)
                    .unwrap()
                    .trim_start()
                    .starts_with('Z')
        );
        assert!(host.invoke(&call, &f.admission).await.is_err());
    }
}

#[tokio::test]
async fn dropping_caller_then_host_keeps_cleanup_owned() {
    for pty in [false, true] {
        let f = Fixture::new();
        let host = f.host();
        let call = f.call(pty, "echo ready > ready; sleep 30");
        let mut work = Box::pin(host.invoke(&call, &f.admission));
        until_file(&f.root.join("ready"), &mut work).await;
        drop(work);
        let core = host.core.clone();
        drop(host);
        let permit = tokio::time::timeout(
            Duration::from_secs(10),
            core.slots.clone().acquire_many_owned(MAX_ACTIVE),
        )
        .await
        .unwrap()
        .unwrap();
        drop(permit);
        assert!(*core.stop.borrow());
    }
}

#[tokio::test]
async fn expiration_is_rechecked_after_waiting_for_start() {
    let f = Fixture::new();
    let local = admission(1, now().unwrap() + 150);
    let host = SandboxedDispatch::new(&local, &f.root, policy(ExecDecision::Allow)).unwrap();
    let call = f.call(false, "touch marker");
    let lock = host.core.open.lock().await;
    let mut work = Box::pin(host.invoke(&call, &local));
    assert!(
        tokio::time::timeout(Duration::from_millis(200), work.as_mut())
            .await
            .is_err()
    );
    drop(lock);
    assert_eq!(work.await.unwrap_err().kind, ToolErrorKind::Unauthorized);
    host.revoke().await.unwrap();
    assert!(!f.root.join("marker").exists());
}

#[tokio::test]
async fn running_work_cannot_outlive_its_local_expiry() {
    let f = Fixture::new();
    let local = admission(1, now().unwrap() + 1500);
    let host = SandboxedDispatch::new(&local, &f.root, policy(ExecDecision::Allow)).unwrap();
    let call = f.call(false, "sleep 30");
    let output = complete(&host, &call, &local).await;
    assert_eq!(output["ok"], false);
    host.revoke().await.unwrap();
}

#[tokio::test]
async fn fresh_host_generation_does_not_accept_prior_generation() {
    let f = Fixture::new();
    let first = f.host();
    first.revoke().await.unwrap();
    let next = admission(2, now().unwrap() + 5000);
    let host = SandboxedDispatch::new(&next, &f.root, policy(ExecDecision::Allow)).unwrap();
    let call = f.call(false, "printf fresh");
    assert!(host.invoke(&call, &f.admission).await.is_err());
    assert_eq!(complete(&host, &call, &next).await["ok"], true);
    assert!(first.invoke(&call, &next).await.is_err());
    host.revoke().await.unwrap();
}

#[tokio::test]
async fn queued_work_has_a_hard_capacity_bound() {
    let f = Fixture::new();
    let host = f.host();
    let call = f.call(false, "touch marker");
    let lock = host.core.open.lock().await;
    let mut calls = Vec::new();
    for _ in 0..MAX_ACTIVE {
        let mut work = Box::pin(host.invoke(&call, &f.admission));
        assert!(
            tokio::time::timeout(Duration::from_millis(10), work.as_mut())
                .await
                .is_err()
        );
        calls.push(work);
    }
    assert_eq!(host.core.slots.available_permits(), 0);
    let error = host.invoke(&call, &f.admission).await.unwrap_err();
    assert_eq!(error.public_message(), "local execution capacity exhausted");
    drop(calls);
    drop(lock);
    host.revoke().await.unwrap();
    assert!(!f.root.join("marker").exists());
}

#[tokio::test]
async fn revoke_timeout_also_bounds_waiting_for_the_start_lock() {
    let f = Fixture::new();
    let host = f.host();
    let call = f.call(false, "touch marker");
    let lock = host.core.open.lock().await;
    let result = tokio::time::timeout(
        Duration::from_secs(1),
        host.revoke_bounded(Duration::from_millis(20)),
    )
    .await
    .unwrap();
    assert_eq!(
        result.unwrap_err().public_message(),
        "sandbox cleanup uncertain"
    );
    assert!(*host.core.stop.borrow());
    assert!(host.invoke(&call, &f.admission).await.is_err());
    drop(lock);
    host.revoke().await.unwrap();
    assert!(!f.root.join("marker").exists());
}
