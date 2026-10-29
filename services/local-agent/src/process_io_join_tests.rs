//! These same bytes are compiled against the unchanged production baseline.
use super::*;
use std::future::pending;

#[tokio::test]
async fn stdout_ready_stderr_pending_times_out_without_repoll() {
    let stdout = tokio::spawn(async { true });
    let stderr = tokio::spawn(pending::<bool>());
    let stdin = tokio::spawn(async { true });
    let done = join_io(stdout, stderr, stdin).await;
    assert!(!done.stdout && !done.stderr && !done.stdin);
}

#[tokio::test]
async fn both_readers_ready_stdin_pending_times_out_without_repoll() {
    let stdout = tokio::spawn(async { true });
    let stderr = tokio::spawn(async { true });
    let stdin = tokio::spawn(pending::<bool>());
    let done = join_io(stdout, stderr, stdin).await;
    assert!(!done.stdout && !done.stderr && !done.stdin);
}

#[tokio::test]
async fn failed_readers_stdin_pending_times_out_without_repoll() {
    let stdout = tokio::spawn(async { panic!("intentional reader task panic") });
    let stderr = tokio::spawn(pending::<bool>());
    stderr.abort();
    let stdin = tokio::spawn(pending::<bool>());
    let done = join_io(stdout, stderr, stdin).await;
    assert!(!done.stdout && !done.stderr && !done.stdin);
}

#[tokio::test]
async fn all_pending_timeout_control_is_incomplete() {
    let stdout = tokio::spawn(pending::<bool>());
    let stderr = tokio::spawn(pending::<bool>());
    let stdin = tokio::spawn(pending::<bool>());
    let done = join_io(stdout, stderr, stdin).await;
    assert!(!done.stdout && !done.stderr && !done.stdin);
}
