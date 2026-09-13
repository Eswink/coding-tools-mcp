//! Actual managed Windows child tests; no shell/process ownership bypass.
use super::*;
use std::process::Stdio;
use std::time::Duration;
use tokio::io::{AsyncBufReadExt, BufReader};

// Kept self-contained so the same test can be appended to the old implementation
// in the failure-first job. It exercises real ResumeThread, not a mock return code.
#[tokio::test]
async fn already_running_child_is_not_a_confirmed_resume() {
    let mut command = Command::new("cmd.exe");
    command.args(["/D", "/Q", "/C", "echo ready & set /p response= & exit /b 0"])
        .stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped()).kill_on_drop(true);
    let (mut child, mut tree) = spawn(&mut command).await.expect("managed native child");
    let mut stdout = BufReader::new(child.stdout.take().expect("stdout"));
    let mut line = String::new();
    let ready = tokio::time::timeout(Duration::from_secs(8), stdout.read_line(&mut line)).await;
    // Clean up even when the readiness observation fails, before any assertion.
    let observed = if matches!(&ready, Ok(Ok(_))) && line.trim() == "ready" {
        Some(resume_primary_thread(child.id().expect("live child identity")))
    } else { None };
    let terminated = tree.terminate();
    let waited = tokio::time::timeout(Duration::from_secs(8), child.wait()).await;
    assert!(ready.is_ok() && line.trim() == "ready", "native child must really reach its stdin hold: {ready:?} {line:?}");
    assert!(terminated.is_ok() && matches!(waited, Ok(Ok(_))), "owned child cleanup must finish");
    assert!(observed.expect("readiness observation").is_err(), "already-running thread must not satisfy suspended startup");
}
