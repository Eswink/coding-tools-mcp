use coding_tools_local_agent::{
    PtyErrorKind, PtyManager, PtyOutputSnapshot, PtySize, PtySpec, PtyTermination,
};
use std::{
    path::PathBuf,
    time::{Duration, Instant},
};

fn fixture() -> String {
    env!("CARGO_BIN_EXE_pty_fixture").to_owned()
}

fn cwd() -> PathBuf {
    std::env::current_dir().expect("cwd")
}

fn spec(args: &[&str]) -> PtySpec {
    let mut argv = vec![fixture()];
    argv.extend(args.iter().map(|value| (*value).to_owned()));
    PtySpec::new(argv, cwd()).expect("valid PTY fixture spec")
}

fn text_bytes(bytes: &[u8]) -> String {
    String::from_utf8_lossy(bytes).replace("\r\n", "\n")
}

fn text(outcome: &coding_tools_local_agent::PtyOutcome) -> String {
    text_bytes(&outcome.output)
}

fn grandchild_pid(outcome: &coding_tools_local_agent::PtyOutcome) -> u32 {
    text(outcome)
        .lines()
        .find_map(|line| {
            line.find("grandchild_pid=")
                .map(|index| &line[index + 15..])
        })
        .and_then(|value| value.trim().parse().ok())
        .expect("grandchild pid")
}

#[tokio::test]
async fn terminal_presence_and_unicode_are_real() {
    let manager = PtyManager::default();
    let outcome = manager.run(spec(&["echo", "héllø-终端"])).await.unwrap();
    assert_eq!(outcome.termination, PtyTermination::Exited, "{outcome:?}");
    let output = text(&outcome);
    assert!(output.contains("terminal=true"), "{output:?}");
    assert!(output.contains("echo=héllø-终端"), "{output:?}");
    assert!(outcome.output_complete);
}

#[cfg(windows)]
#[tokio::test]
async fn windows_argv_round_trips_spaces_quotes_and_trailing_backslash() {
    let manager = PtyManager::default();
    let value = "space \"quote\" tail\\";
    let outcome = manager.run(spec(&["echo", value])).await.unwrap();
    assert_eq!(outcome.termination, PtyTermination::Exited, "{outcome:?}");
    assert!(text(&outcome).contains(&format!("echo={value}")), "{outcome:?}");
}

#[tokio::test]
async fn interactive_write_is_bounded_and_delivered() {
    let manager = PtyManager::default();
    let mut session = manager.start(spec(&["read-once"])).await.unwrap();
    #[cfg(windows)]
    session.write("héllo\r\n".as_bytes()).unwrap();
    #[cfg(not(windows))]
    session.write("héllo\n".as_bytes()).unwrap();
    let outcome = session.wait().await;
    let output = text(&outcome);
    assert!(output.contains("terminal=true"), "{output:?}");
    assert!(output.contains("input=héllo"), "{output:?}");
}

#[tokio::test]
async fn live_output_snapshot_and_explicit_close_are_bounded() {
    let manager = PtyManager::default();
    let mut session = manager.start(spec(&["read-once"])).await.unwrap();
    let deadline = Instant::now() + Duration::from_secs(2);
    loop {
        let snapshot = session.output_snapshot().unwrap();
        if text_bytes(&snapshot.output).contains("terminal=true") {
            assert!(snapshot.output_total_bytes >= snapshot.output.len() as u64);
            assert!(!snapshot.truncated);
            break;
        }
        assert!(
            Instant::now() < deadline,
            "live PTY output never became observable"
        );
        tokio::time::sleep(Duration::from_millis(10)).await;
    }
    let outcome = session.close().await;
    assert_eq!(
        outcome.termination,
        PtyTermination::Cancelled,
        "{outcome:?}"
    );
}

#[tokio::test]
async fn ambient_environment_is_cleared_and_explicit_environment_is_delivered() {
    let manager = PtyManager::default();
    let ambient = manager.run(spec(&["env", "PATH"])).await.unwrap();
    assert!(text(&ambient).contains("env=<absent>"), "{ambient:?}");

    let explicit = manager
        .run(
            spec(&["env", "PTY_EXPLICIT"])
                .with_env("PTY_EXPLICIT", "visible")
                .unwrap(),
        )
        .await
        .unwrap();
    assert!(text(&explicit).contains("env=visible"), "{explicit:?}");
}

#[tokio::test]
async fn resize_reaches_the_terminal() {
    let manager = PtyManager::default();
    let mut session = manager.start(spec(&["size-after", "300"])).await.unwrap();
    session.resize(PtySize::new(100, 40).unwrap()).unwrap();
    let outcome = session.wait().await;
    assert!(text(&outcome).contains("size=100x40"), "{outcome:?}");
}

#[tokio::test]
async fn timeout_and_cancel_terminate_owned_tree() {
    let manager = PtyManager::default();
    let timed = manager
        .run(
            spec(&["sleep", "60000"])
                .with_timeout(Duration::from_millis(300))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(timed.termination, PtyTermination::TimedOut, "{timed:?}");

    let mut session = manager
        .start(
            spec(&["spawn-grandchild"])
                .with_timeout(Duration::from_secs(30))
                .unwrap(),
        )
        .await
        .unwrap();
    tokio::time::sleep(Duration::from_millis(250)).await;
    let outcome = session.cancel().await;
    assert_eq!(
        outcome.termination,
        PtyTermination::Cancelled,
        "{outcome:?}"
    );
    let pid = grandchild_pid(&outcome);
    tokio::time::sleep(Duration::from_millis(150)).await;
    assert!(!process_alive(pid), "PTY grandchild survived cancel: {pid}");
}

#[tokio::test]
async fn successful_parent_exit_cleans_owned_grandchild() {
    let manager = PtyManager::default();
    let outcome = manager.run(spec(&["spawn-grandchild-exit"])).await.unwrap();
    assert_eq!(outcome.termination, PtyTermination::Exited, "{outcome:?}");
    let pid = grandchild_pid(&outcome);
    tokio::time::sleep(Duration::from_millis(150)).await;
    assert!(
        !process_alive(pid),
        "PTY grandchild survived parent exit: {pid}"
    );
}

#[tokio::test]
async fn output_overflow_is_bounded_and_terminates() {
    let manager = PtyManager::default();
    let outcome = manager
        .run(
            spec(&["flood", "1048576"])
                .with_output_limit(1024)
                .unwrap()
                .with_timeout(Duration::from_secs(10))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(
        outcome.termination,
        PtyTermination::OutputLimit,
        "{outcome:?}"
    );
    assert!(outcome.truncated);
    assert!(outcome.output_total_bytes > outcome.output.len() as u64);
    assert!(outcome.output.len() <= 1024);
}

#[tokio::test]
async fn capacity_and_drop_fail_closed() {
    let manager = PtyManager::new(1).unwrap();
    let session = manager.start(spec(&["sleep", "60000"])).await.unwrap();
    let error = manager.start(spec(&["echo", "second"])).await.unwrap_err();
    assert_eq!(error.kind, PtyErrorKind::Capacity);
    drop(session);
    tokio::time::sleep(Duration::from_millis(300)).await;
    let outcome = manager.run(spec(&["echo", "after-drop"])).await.unwrap();
    assert_eq!(outcome.termination, PtyTermination::Exited, "{outcome:?}");
}

#[test]
fn spec_and_debug_surfaces_are_bounded_and_redacted() {
    let invalid = PtySpec::new(vec!["relative.exe".into()], cwd()).unwrap_err();
    assert_eq!(invalid.kind, PtyErrorKind::InvalidSpec);
    let spec = spec(&["echo", "super-secret-argument"])
        .with_env("SECRET_VALUE", "super-secret-env")
        .unwrap();
    let rendered = format!("{spec:?}");
    assert!(!rendered.contains("super-secret-argument"));
    assert!(!rendered.contains("super-secret-env"));
    assert!(!rendered.contains(&cwd().display().to_string()));
    assert!(PtySize::new(0, 24).is_err());
    assert!(PtySize::new(80, 1001).is_err());
    let snapshot = PtyOutputSnapshot {
        output: b"super-secret-terminal-output".to_vec(),
        output_total_bytes: 28,
        truncated: false,
    };
    assert!(!format!("{snapshot:?}").contains("super-secret-terminal-output"));
}

#[cfg(unix)]
fn process_alive(pid: u32) -> bool {
    let result = unsafe { libc::kill(pid as i32, 0) };
    result == 0 || std::io::Error::last_os_error().raw_os_error() == Some(libc::EPERM)
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
    let active =
        unsafe { GetExitCodeProcess(handle, &mut code) }.is_ok() && code == STILL_ACTIVE_CODE;
    let _ = unsafe { CloseHandle(handle) };
    active
}
