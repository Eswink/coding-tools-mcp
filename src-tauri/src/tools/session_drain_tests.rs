//! Cancellation-safe join regression: handles stay in the owning session until
//! their actual tasks have joined, rather than being detached by a lost waiter.
use super::*;
use std::{sync::Arc, time::Duration};
#[cfg(unix)]
async fn held_child() -> Arc<ExecSession> {
    let mut command = tokio::process::Command::new("/bin/cat");
    command
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped());
    let (child, tree) = crate::tools::process_tree::spawn(&mut command)
        .await
        .unwrap();
    let s = Arc::new(ExecSession::new_managed(child, tree));
    s.spawn_readers().await;
    s
}
#[cfg(unix)]
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn cancelled_reader_waiter_does_not_remove_live_reader_handle() {
    let s = held_child().await;
    let copy = s.clone();
    let waiter = tokio::spawn(async move { copy.wait_for_readers().await });
    tokio::time::timeout(Duration::from_secs(2), async {
        loop {
            if s.reader_tasks.try_lock().is_err() {
                break;
            }
            tokio::task::yield_now().await;
        }
    })
    .await
    .unwrap();
    waiter.abort();
    let _ = waiter.await;
    let retained = s.reader_tasks.lock().await.len();
    s.kill_and_wait().await;
    s.wait_for_readers().await;
    assert_eq!(
        retained, 2,
        "cancelled drain collector detached a live reader"
    );
}
#[cfg(unix)]
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn cancelled_input_waiter_does_not_remove_live_writer_handle() {
    let s = held_child().await;
    // Use a controlled pending task, rather than input-buffer timing or sleep.
    let (tx, rx) = tokio::sync::oneshot::channel();
    *s.initial_stdin_task.lock().await = Some(tauri::async_runtime::spawn(async move {
        let _ = rx.await;
    }));
    let copy = s.clone();
    let waiter = tokio::spawn(async move { copy.wait_for_initial_stdin().await });
    tokio::time::timeout(Duration::from_secs(2), async {
        loop {
            if s.initial_stdin_task.try_lock().is_err() {
                break;
            }
            tokio::task::yield_now().await;
        }
    })
    .await
    .unwrap();
    waiter.abort();
    let _ = waiter.await;
    let retained = s.initial_stdin_task.lock().await.is_some();
    let _ = tx.send(());
    s.kill_and_wait().await;
    s.wait_for_readers().await;
    assert!(
        retained,
        "cancelled drain collector detached a live initial writer"
    );
}

/// A1 C4-c C / C6s: a session whose leader exits normally still has its group
/// killed: the refresh reaps the leader, then `terminate_tree` kills the group
/// once through the tree's live holder, whose membership keeps the pgid from
/// being freed or reused although the leader is already reaped.
#[cfg(target_os = "linux")]
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_normal_exit_still_kills_the_leftover_group_through_the_holder() {
    let file = std::env::temp_dir().join(format!("ctm-c4c-session-{}", std::process::id()));
    let script = format!("sleep 30 >/dev/null 2>&1 & echo $! > '{}'", file.display());
    let mut command = tokio::process::Command::new("/bin/sh");
    command.args(["-c", &script]);
    let (child, tree) = crate::tools::process_tree::spawn(&mut command)
        .await
        .unwrap();
    let s = ExecSession::new_managed(child, tree);
    let mut pid: Option<libc::pid_t> = None;
    for _ in 0..500 {
        pid = pid.or_else(|| std::fs::read_to_string(&file).ok()?.trim().parse().ok());
        s.refresh_status().await;
        if pid.is_some() && s.has_exited() {
            break;
        }
        tokio::time::sleep(Duration::from_millis(10)).await;
    }
    let _ = std::fs::remove_file(&file);
    let pid = pid.expect("straggler pid");
    assert!(s.has_exited(), "the leader never exited");
    let running = |pid: libc::pid_t| {
        std::fs::read_to_string(format!("/proc/{pid}/stat"))
            .ok()
            .and_then(|stat| {
                stat.rsplit_once(") ")
                    .map(|(_, rest)| !rest.starts_with('Z'))
            })
            .unwrap_or(false)
    };
    let mut gone = false;
    for _ in 0..100 {
        if !running(pid) {
            gone = true;
            break;
        }
        tokio::time::sleep(Duration::from_millis(10)).await;
    }
    if !gone {
        unsafe { libc::kill(pid, libc::SIGKILL) };
    }
    assert!(gone, "the leftover of a normally exited leader survived");
    assert!(!s
        .tree_cleanup_failed
        .load(std::sync::atomic::Ordering::Acquire));
}
