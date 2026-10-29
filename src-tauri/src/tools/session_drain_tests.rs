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
