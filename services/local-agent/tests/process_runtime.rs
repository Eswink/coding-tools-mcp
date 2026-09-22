use coding_tools_local_agent::{
    ExecErrorKind, ExecSpec, ExecTermination, ProcessManager,
};
use std::{
    path::PathBuf,
    time::Duration,
};

fn fixture() -> String {
    env!("CARGO_BIN_EXE_process_fixture").to_owned()
}

fn cwd() -> PathBuf {
    std::env::current_dir().expect("cwd")
}

fn spec(args: &[&str]) -> ExecSpec {
    let mut argv = vec![fixture()];
    argv.extend(args.iter().map(|v| (*v).to_owned()));
    ExecSpec::new(argv, cwd()).expect("valid fixture spec")
}

fn grandchild_pid(outcome: &coding_tools_local_agent::ExecOutcome) -> u32 {
    String::from_utf8_lossy(&outcome.stdout)
        .lines()
        .find_map(|line| line.strip_prefix("grandchild_pid="))
        .and_then(|value| value.parse::<u32>().ok())
        .expect("grandchild pid")
}

#[tokio::test]
async fn captures_stdout_stderr_and_exit_code() {
    let manager = ProcessManager::default();
    let outcome = manager.run(spec(&["echo", "hello"])).await.unwrap();
    assert_eq!(outcome.termination, ExecTermination::Exited);
    assert_eq!(outcome.exit_code, Some(0));
    assert!(String::from_utf8_lossy(&outcome.stdout).contains("stdout:hello"));
    assert!(String::from_utf8_lossy(&outcome.stderr).contains("stderr:hello"));
    assert!(outcome.command_ok());
    assert!(outcome.output_complete);
}

#[tokio::test]
async fn stdin_is_bounded_delivered_exactly_then_closed() {
    let manager = ProcessManager::default();
    let input = b"alpha\nbeta\n".to_vec();
    let outcome = manager
        .run(spec(&["stdin"]).with_stdin(input.clone()).unwrap())
        .await
        .unwrap();
    assert_eq!(outcome.termination, ExecTermination::Exited);
    let expected = format!("stdin:{}:", input.len()).into_bytes();
    assert!(outcome.stdout.starts_with(&expected));
    assert_eq!(&outcome.stdout[expected.len()..], input.as_slice());
}

#[tokio::test]
async fn environment_is_cleared_except_explicit_entries() {
    let manager = ProcessManager::default();
    let outcome = manager
        .run(
            spec(&["env"])
                .with_env("CTM_TEST_VISIBLE", "visible-value")
                .unwrap(),
        )
        .await
        .unwrap();
    let text = String::from_utf8_lossy(&outcome.stdout);
    assert!(text.contains("visible=visible-value"), "{text}");
    assert!(text.contains("path=missing"), "{text}");
}

#[tokio::test]
async fn timeout_terminates_owned_process_tree() {
    let manager = ProcessManager::default();
    let outcome = manager
        .run(
            spec(&["spawn-grandchild"])
                .with_timeout(Duration::from_millis(350))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(outcome.termination, ExecTermination::TimedOut, "{outcome:?}");
    let pid = grandchild_pid(&outcome);
    tokio::time::sleep(Duration::from_millis(150)).await;
    assert!(!process_alive(pid), "grandchild survived process-tree timeout: {pid}");
}

#[tokio::test]
async fn explicit_cancel_terminates_owned_process_tree() {
    let manager = ProcessManager::default();
    let mut session = manager
        .start(
            spec(&["spawn-grandchild"])
                .with_timeout(Duration::from_secs(30))
                .unwrap(),
        )
        .await
        .unwrap();
    tokio::time::sleep(Duration::from_millis(150)).await;
    let outcome = session.cancel().await;
    assert_eq!(outcome.termination, ExecTermination::Cancelled, "{outcome:?}");
    let pid = grandchild_pid(&outcome);
    tokio::time::sleep(Duration::from_millis(150)).await;
    assert!(
        !process_alive(pid),
        "grandchild survived explicit process-tree cancel: {pid}"
    );
}

#[tokio::test]
async fn successful_parent_exit_still_cleans_owned_grandchild() {
    let manager = ProcessManager::default();
    let outcome = manager
        .run(
            spec(&["spawn-grandchild-exit"])
                .with_timeout(Duration::from_secs(10))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(outcome.termination, ExecTermination::Exited, "{outcome:?}");
    assert!(outcome.command_ok(), "{outcome:?}");
    let pid = grandchild_pid(&outcome);
    tokio::time::sleep(Duration::from_millis(150)).await;
    assert!(
        !process_alive(pid),
        "grandchild survived successful parent exit cleanup: {pid}"
    );
}

#[tokio::test]
async fn output_overflow_is_memory_bounded_and_terminates() {
    let manager = ProcessManager::default();
    let outcome = manager
        .run(
            spec(&["flood", "1048576"])
                .with_stream_limit(1024)
                .unwrap()
                .with_timeout(Duration::from_secs(10))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(outcome.termination, ExecTermination::OutputLimit, "{outcome:?}");
    assert!(outcome.stdout_truncated);
    assert!(outcome.stdout_total_bytes > outcome.stdout.len() as u64);
    assert!(outcome.stdout.len() <= 1024);
}

#[tokio::test]
async fn zero_exit_with_output_overflow_is_never_command_ok() {
    let manager = ProcessManager::default();
    let outcome = manager
        .run(
            spec(&["flood", "8192"])
                .with_stream_limit(256)
                .unwrap()
                .with_timeout(Duration::from_secs(10))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(outcome.termination, ExecTermination::OutputLimit);
    assert!(!outcome.command_ok());
}

#[tokio::test]
async fn nonzero_exit_is_distinct_from_spawn_failure() {
    let manager = ProcessManager::default();
    let outcome = manager.run(spec(&["exit", "7"])).await.unwrap();
    assert_eq!(outcome.termination, ExecTermination::Exited);
    assert_eq!(outcome.exit_code, Some(7));
    assert!(!outcome.command_ok());

    let missing = if cfg!(windows) {
        r"C:\definitely-missing\coding-tools-fixture.exe"
    } else {
        "/definitely-missing/coding-tools-fixture"
    };
    let error = manager
        .run(ExecSpec::new(vec![missing.into()], cwd()).unwrap())
        .await
        .unwrap_err();
    assert_eq!(error.kind, ExecErrorKind::Spawn);
}

#[tokio::test]
async fn dropping_session_does_not_detach_background_process() {
    let manager = ProcessManager::default();
    let session = manager
        .start(
            spec(&["sleep", "60000"])
                .with_timeout(Duration::from_secs(30))
                .unwrap(),
        )
        .await
        .unwrap();
    let id = session.id().to_owned();
    drop(session);
    tokio::time::sleep(Duration::from_millis(250)).await;

    // The released active slot is the observable contract: dropping the only
    // cancellation sender must make the supervisor clean up its owned tree.
    let mut replacement = manager
        .start(spec(&["echo", &format!("after-{id}")]))
        .await
        .expect("dropped session must release bounded capacity after cleanup");
    let outcome = replacement.wait().await;
    assert!(outcome.command_ok(), "{outcome:?}");
}

#[tokio::test]
async fn active_process_limit_fails_closed() {
    let manager = ProcessManager::new(1).unwrap();
    let mut first = manager
        .start(
            spec(&["sleep", "60000"])
                .with_timeout(Duration::from_secs(30))
                .unwrap(),
        )
        .await
        .unwrap();
    let second = manager.start(spec(&["echo", "second"])).await.unwrap_err();
    assert_eq!(second.kind, ExecErrorKind::Capacity);
    assert_eq!(first.cancel().await.termination, ExecTermination::Cancelled);
}

#[test]
fn debug_surfaces_do_not_print_environment_or_command_arguments() {
    let spec = spec(&["echo", "super-secret-argument"])
        .with_env("SECRET_VALUE", "super-secret-env")
        .unwrap();
    let rendered = format!("{spec:?}");
    assert!(!rendered.contains("super-secret-argument"));
    assert!(!rendered.contains("super-secret-env"));
}

#[cfg(unix)]
fn process_alive(pid: u32) -> bool {
    let result = unsafe { libc::kill(pid as i32, 0) };
    if result == 0 {
        true
    } else {
        std::io::Error::last_os_error().raw_os_error() == Some(libc::EPERM)
    }
}

#[cfg(windows)]
fn process_alive(pid: u32) -> bool {
    use windows::Win32::Foundation::CloseHandle;
    use windows::Win32::System::Threading::{
        GetExitCodeProcess, OpenProcess, PROCESS_QUERY_LIMITED_INFORMATION,
    };
    const STILL_ACTIVE_CODE: u32 = 259;
    let Ok(handle) = (unsafe { OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, pid) }) else {
        return false;
    };
    let mut code = 0u32;
    let active = unsafe { GetExitCodeProcess(handle, &mut code) }.is_ok() && code == STILL_ACTIVE_CODE;
    let _ = unsafe { CloseHandle(handle) };
    active
}
