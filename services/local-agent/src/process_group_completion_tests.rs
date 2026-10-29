//! Stronger completion is opt-in. These are local process-lifecycle tests, not
//! evidence that a remote request was authorized or that kernel isolation works.
use super::*;
use std::os::unix::process::CommandExt;

#[test]
fn group_observation_is_an_explicit_strengthening() {
    let spec = ExecSpec::new(
        vec!["/bin/sh".into(), "-c".into(), "exit 0".into()],
        std::env::temp_dir(),
    )
    .unwrap();
    assert!(!spec.require_tree_exit);
    assert!(spec.with_tree_exit_confirmation().require_tree_exit);
}
#[tokio::test]
async fn invalid_group_identifiers_never_claim_completion() {
    for pid in [None, Some(0), Some(1), Some(u32::MAX)] {
        assert!(!confirm_group_exit(pid).await);
    }
}
#[tokio::test]
async fn exited_managed_child_has_confirmed_group_completion() {
    let spec = ExecSpec::new(
        vec!["/bin/sh".into(), "-c".into(), "printf confirmed".into()],
        std::env::temp_dir(),
    )
    .unwrap()
    .with_tree_exit_confirmation();
    let outcome = ProcessManager::default().run(spec).await.unwrap();
    assert_eq!(outcome.termination, ExecTermination::Exited);
    assert_eq!(outcome.exit_code, Some(0));
    assert_eq!(outcome.stdout, b"confirmed");
}
#[tokio::test]
async fn observing_a_live_owned_group_never_kills_it() {
    let mut child = std::process::Command::new("/bin/sleep")
        .arg("15")
        .process_group(0)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .unwrap();
    let pid = child.id();
    let waiting =
        tokio::time::timeout(Duration::from_millis(40), confirm_group_exit(Some(pid))).await;
    let alive = child.try_wait().unwrap().is_none();
    // Clean up only this owned Child handle even if the assertion fails.
    let _ = child.kill();
    let _ = child.wait();
    assert!(waiting.is_err());
    assert!(alive);
    assert!(confirm_group_exit(Some(pid)).await);
}
