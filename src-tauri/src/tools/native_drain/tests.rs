use super::*;
use coding_tools_cloud_agent::work::WorkDrain;
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Barrier,
};
#[tokio::test]
async fn queued_native_callback_cannot_begin_after_drain() {
    let d = WorkDrain::new();
    let called = Arc::new(AtomicBool::new(false));
    let c = called.clone();
    let future = blocking(&d, move |_| {
        c.store(true, Ordering::Release);
        Ok(())
    });
    d.seal();
    assert!(future.await.is_err());
    d.wait().await;
    assert!(!called.load(Ordering::Acquire));
}
#[tokio::test]
async fn discarded_unpolled_callback_retires_only_queued_registration() {
    let d = WorkDrain::new();
    let future = blocking(&d, |_| -> Result<(), AgentError> { panic!("must not run") });
    assert_eq!(d.status().outstanding, 1);
    drop(future);
    d.seal();
    d.wait().await;
    assert!(!d.status().unconfirmed);
}
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn lost_native_waiter_keeps_running_callback() {
    let d = WorkDrain::new();
    let gate = Arc::new(Barrier::new(2));
    let g = gate.clone();
    let (s, r) = tokio::sync::oneshot::channel();
    let future = blocking(&d, move |_| {
        let _ = s.send(());
        g.wait();
        Ok(())
    });
    let t = tokio::spawn(future);
    r.await.unwrap();
    t.abort();
    let _ = t.await;
    d.seal();
    assert!(tokio::time::timeout(Duration::from_millis(30), d.wait())
        .await
        .is_err());
    gate.wait();
    tokio::time::timeout(Duration::from_secs(2), d.wait())
        .await
        .unwrap();
}
#[tokio::test]
async fn native_panic_does_not_publish_drain_success() {
    let d = WorkDrain::new();
    assert!(blocking(&d, |_| -> Result<(), AgentError> {
        panic!("owned test panic")
    })
    .await
    .is_err());
    d.seal();
    assert!(d.status().unconfirmed);
    assert!(tokio::time::timeout(Duration::from_millis(30), d.wait())
        .await
        .is_err());
}
#[tokio::test]
async fn ordinary_native_rejection_retires_completed_callback() {
    let d = WorkDrain::new();
    assert!(blocking(&d, |_| -> Result<(), AgentError> {
        Err(AgentError::LocalAuthority)
    })
    .await
    .is_err());
    d.seal();
    d.wait().await;
    assert!(!d.status().unconfirmed);
}
#[test]
fn thread_scope_nesting_restores_parent_without_forging_a_live_call() {
    assert!(current_child().unwrap().is_none());
    let d = WorkDrain::new();
    let mut root = d.register().unwrap();
    root.begin().unwrap();
    {
        let _outer = enter(Some(root.scope()));
        let child = current_child().unwrap().unwrap();
        drop(child);
        {
            let _inner = enter(None);
            assert!(current_child().unwrap().is_none());
        }
        assert!(current_child().unwrap().is_some());
    }
    assert!(current_child().unwrap().is_none());
    root.complete();
}
#[test]
fn stale_thread_scope_is_rejected_before_helper_process_creation() {
    let d = WorkDrain::new();
    let mut root = d.register().unwrap();
    root.begin().unwrap();
    let scope = root.scope();
    root.complete();
    let _entered = enter(Some(scope));
    assert!(current_child().is_err());
}
#[test]
fn context_snapshot_preserves_descendant_scope() {
    let root = tempfile::tempdir().unwrap();
    let h = tempfile::tempdir().unwrap();
    let d = WorkDrain::new();
    let mut guard = d.register().unwrap();
    guard.begin().unwrap();
    let mut ctx = ToolContext::for_test(root.path().into(), h.path().into()).unwrap();
    ctx.native_work = Some(guard.scope());
    let copy = ctx.background_snapshot();
    let child = child(&copy).unwrap().unwrap();
    drop(child);
    guard.complete();
    assert!(self::child(&copy).is_err());
}
#[cfg(unix)]
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn native_process_and_pipes_hold_guard_until_real_child_exit() {
    let d = WorkDrain::new();
    let mut guard = d.register().unwrap();
    guard.begin().unwrap();
    let mut command = tokio::process::Command::new("/bin/cat");
    command
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped());
    let (child, tree) = super::super::process_tree::spawn(&mut command)
        .await
        .unwrap();
    let pid = child.id();
    let session = Arc::new(ExecSession::new_managed(child, tree));
    session.spawn_readers().await;
    track_process(session.clone(), Some(guard), pid);
    d.seal();
    assert!(tokio::time::timeout(Duration::from_millis(50), d.wait())
        .await
        .is_err());
    session.stdin.lock().await.take();
    tokio::time::timeout(Duration::from_secs(6), d.wait())
        .await
        .unwrap();
    assert!(session.has_exited());
    assert!(!d.status().unconfirmed);
}

#[cfg(unix)]
#[test]
fn actual_exec_dispatch_keeps_drain_until_session_and_pipes_finish() {
    let d = WorkDrain::new();
    let mut root_work = d.register().unwrap();
    root_work.begin().unwrap();
    let root = tempfile::tempdir().unwrap();
    let storage = tempfile::tempdir().unwrap();
    let mut ctx = ToolContext::for_test(root.path().into(), storage.path().into()).unwrap();
    ctx.native_work = Some(root_work.scope());
    // This is local execution plumbing, not a remote authorization/sandbox test.
    let out = crate::tools::call_tool(
        &ctx,
        "exec_command",
        &serde_json::json!({
            "cmd":"python3 -c \"import sys; sys.stdin.read(); print('finished')\"",
            "tty":true,"yield_time_ms":0,"timeout_ms":15000
        }),
    );
    assert_eq!(
        out["ok"], true,
        "actual local execution dispatcher rejected fixture"
    );
    let session = ctx
        .sessions
        .get(out["session_id"].as_str().unwrap())
        .unwrap();
    root_work.complete();
    d.seal();
    tauri::async_runtime::block_on(async {
        assert!(tokio::time::timeout(Duration::from_millis(40), d.wait())
            .await
            .is_err());
        session.stdin.lock().await.take();
        tokio::time::timeout(Duration::from_secs(6), d.wait())
            .await
            .unwrap();
    });
    assert!(session.has_exited());
    assert!(!d.status().unconfirmed);
}

#[cfg(unix)]
#[test]
fn actual_async_task_retains_descendants_after_original_call_returns() {
    let root = tempfile::tempdir().unwrap();
    let storage = tempfile::tempdir().unwrap();
    std::fs::write(root.path().join("hold.py"),
        "import pathlib,time\npathlib.Path('started').write_text('ready')\nwhile not pathlib.Path('release').exists(): time.sleep(.01)\nprint('completed')\n").unwrap();
    let d = WorkDrain::new();
    let mut request = d.register().unwrap();
    request.begin().unwrap();
    let mut ctx = ToolContext::for_test(root.path().into(), storage.path().into()).unwrap();
    ctx.native_work = Some(request.scope());
    let job = crate::tools::call_tool(
        &ctx,
        "start_exec_task",
        &serde_json::json!({
            "request_id":"native-drain-async","cmd":"python3 hold.py","timeout_ms":15000
        }),
    );
    assert_eq!(job["ok"], true);
    request.complete();
    d.seal();
    let deadline = std::time::Instant::now() + Duration::from_secs(5);
    while !root.path().join("started").exists() {
        assert!(
            std::time::Instant::now() < deadline,
            "native async worker did not start"
        );
        std::thread::sleep(Duration::from_millis(10));
    }
    tauri::async_runtime::block_on(async {
        assert!(tokio::time::timeout(Duration::from_millis(40), d.wait())
            .await
            .is_err());
    });
    std::fs::write(root.path().join("release"), "release owned fixture").unwrap();
    tauri::async_runtime::block_on(async {
        tokio::time::timeout(Duration::from_secs(6), d.wait())
            .await
            .unwrap();
    });
    let done = crate::tools::call_tool(
        &ctx,
        "get_exec_task",
        &serde_json::json!({"job_id":job["job_id"]}),
    );
    assert_eq!(done["status"], "succeeded");
    assert!(!d.status().unconfirmed);
}

#[cfg(unix)]
#[test]
fn stale_native_scope_cannot_create_real_child_side_effect() {
    let root = tempfile::tempdir().unwrap();
    let storage = tempfile::tempdir().unwrap();
    let d = WorkDrain::new();
    let mut request = d.register().unwrap();
    request.begin().unwrap();
    let mut ctx = ToolContext::for_test(root.path().into(), storage.path().into()).unwrap();
    ctx.native_work = Some(request.scope());
    request.complete();
    d.seal();
    let out = crate::tools::call_tool(
        &ctx,
        "exec_command",
        &serde_json::json!({
            "cmd":"python3 -c \"from pathlib import Path; Path('unexpected').write_text('bad')\""
        }),
    );
    assert_ne!(out["ok"], true);
    assert_eq!(out["error"]["code"], "CLOUD_HOST_STOPPING");
    assert!(!root.path().join("unexpected").exists());
}
