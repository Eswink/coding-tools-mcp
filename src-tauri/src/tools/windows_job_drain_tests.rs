//! Real owned Job accounting; no saved PID, breakaway, or handle-drop proof.
use super::*;
use std::process::Stdio;
use std::time::Duration;
use tokio::io::{AsyncBufReadExt, AsyncReadExt, BufReader};

async fn wait_empty(tree: &ProcessTree) -> bool {
    let deadline = tokio::time::Instant::now() + Duration::from_secs(5);
    loop {
        match tree.is_empty() {
            Ok(true) => return true,
            Err(_) => return false,
            Ok(false) => {}
        }
        if tokio::time::Instant::now() >= deadline {
            return false;
        }
        tokio::time::sleep(Duration::from_millis(20)).await;
    }
}

#[test]
fn missing_owned_job_is_not_completion() {
    assert!(ProcessTree(None).is_empty().is_err());
}

#[tokio::test]
async fn job_remains_queryable_until_real_members_exit() {
    let mut command = Command::new("cmd.exe");
    command
        .args([
            "/D",
            "/Q",
            "/C",
            "echo ready & set /p response= & exit /b 0",
        ])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    let (mut child, mut tree) = spawn(&mut command).await.expect("owned child");
    let mut output = BufReader::new(child.stdout.take().expect("stdout"));
    let mut ready = String::new();
    let observed = tokio::time::timeout(Duration::from_secs(8), output.read_line(&mut ready)).await;
    let before = tree.is_empty();
    let terminated = tree.terminate();
    let parent = tokio::time::timeout(Duration::from_secs(8), child.wait()).await;
    let drained = wait_empty(&tree).await;
    let after = tree.is_empty();
    assert!(matches!(observed, Ok(Ok(_))) && ready.trim() == "ready");
    assert!(
        matches!(before, Ok(false)),
        "a live owned child is not an empty job"
    );
    assert!(terminated.is_ok() && matches!(parent, Ok(Ok(_))));
    assert!(
        drained && matches!(after, Ok(true)),
        "closed handle cannot substitute for queried zero members"
    );
}

#[tokio::test]
async fn parent_exit_does_not_prove_owned_descendant_or_pipe_completion() {
    let scripts = tempfile::Builder::new()
        .prefix("owned job drain fixture ")
        .tempdir()
        .unwrap();
    let parent_script = scripts.path().join("parent.cmd");
    std::fs::write(
        scripts.path().join("descendant.cmd"),
        b"@echo off\r\necho descendant-ready\r\nset /p response=\r\n",
    )
    .unwrap();
    std::fs::write(
        &parent_script,
        b"@echo off\r\nstart \"\" /B cmd.exe /D /Q /C call \"%~dp0descendant.cmd\"\r\nexit /B 0\r\n",
    )
    .unwrap();
    // Let cmd parse literal batch syntax rather than passing nested quotes
    // through Rust's C-runtime argument escaping. Both scripts remain alive
    // until the owned descendant and its inherited pipe have been drained.
    let mut command = Command::new("cmd.exe");
    command
        .args(["/D", "/Q", "/C"])
        .arg(&parent_script)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    let (mut child, mut tree) = spawn(&mut command).await.expect("owned parent");
    let mut output = BufReader::new(child.stdout.take().expect("stdout"));
    let mut ready = String::new();
    let observed = tokio::time::timeout(Duration::from_secs(8), output.read_line(&mut ready)).await;
    let parent = tokio::time::timeout(Duration::from_secs(8), child.wait()).await;
    let before = tree.is_empty();
    let terminated = tree.terminate();
    let drained = wait_empty(&tree).await;
    let mut rest = Vec::new();
    let pipes = tokio::time::timeout(Duration::from_secs(5), output.read_to_end(&mut rest)).await;
    assert!(
        matches!(observed, Ok(Ok(_))) && ready.trim() == "descendant-ready",
        "descendant must start"
    );
    assert!(
        matches!(parent, Ok(Ok(_))),
        "parent must have exited before accounting observation"
    );
    assert!(
        matches!(before, Ok(false)),
        "parent exit must not erase a living owned descendant"
    );
    assert!(terminated.is_ok() && drained);
    assert!(
        matches!(pipes, Ok(Ok(_))),
        "pipe completion is a separately observed fact"
    );
}
