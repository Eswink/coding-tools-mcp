#![cfg(windows)]

// Exercise the exact production Job owner without exposing a public test API.
#[path = "../src/process_tree_windows.rs"]
mod owned_tree;

use coding_tools_local_agent::{ExecSpec, ExecTermination, ProcessManager};
use std::{
    io,
    os::windows::io::{AsRawHandle, FromRawHandle, OwnedHandle},
    path::PathBuf,
    process::Stdio,
    sync::{
        atomic::{AtomicBool, AtomicU64, Ordering},
        Arc,
    },
    time::{Duration, Instant},
};
use tokio::{io::AsyncReadExt, process::Command};
use windows::Win32::{
    Foundation::{HANDLE, WAIT_OBJECT_0, WAIT_TIMEOUT},
    System::Threading::{
        OpenProcess, TerminateProcess, WaitForSingleObject, PROCESS_SYNCHRONIZE, PROCESS_TERMINATE,
    },
};

type TestResult<T = ()> = Result<T, Box<dyn std::error::Error>>;
const SETUP_WAIT: Duration = Duration::from_secs(5);
const CLEANUP_WAIT: Duration = Duration::from_secs(3);

struct Markers(PathBuf);

impl Markers {
    fn new() -> io::Result<Self> {
        static NEXT: AtomicU64 = AtomicU64::new(0);
        let nonce = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map_err(io::Error::other)?
            .as_nanos();
        let path = std::env::temp_dir().join(format!(
            "ctm-owned-job-{}-{nonce}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        std::fs::create_dir(&path)?;
        Ok(Self(path))
    }

    fn ready(&self) -> PathBuf {
        self.0.join("ready")
    }

    fn release(&self) -> PathBuf {
        self.0.join("release")
    }

    fn argv(&self) -> Vec<String> {
        vec![
            env!("CARGO_BIN_EXE_process_fixture").to_owned(),
            "spawn-private-descendant".to_owned(),
            self.ready().to_string_lossy().into_owned(),
            self.release().to_string_lossy().into_owned(),
        ]
    }

    async fn descendant(&self) -> io::Result<Descendant> {
        let deadline = Instant::now() + SETUP_WAIT;
        while Instant::now() < deadline {
            if let Ok(marker) = std::fs::read_to_string(self.ready()) {
                if let Some(pid) = marker
                    .strip_prefix("descendant_ready=")
                    .and_then(|value| value.strip_suffix('\n'))
                    .and_then(|value| value.parse().ok())
                {
                    // An open error is a setup failure, never evidence of death.
                    return Descendant::open(pid);
                }
            }
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
        Err(io::Error::new(
            io::ErrorKind::TimedOut,
            "descendant readiness marker missing",
        ))
    }
}

impl Drop for Markers {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}

struct Descendant(OwnedHandle);

impl Descendant {
    fn open(pid: u32) -> io::Result<Self> {
        // Retain SYNCHRONIZE for all observations; TERMINATE is for RAII cleanup.
        let raw = unsafe { OpenProcess(PROCESS_SYNCHRONIZE | PROCESS_TERMINATE, false, pid) }
            .map_err(|error| io::Error::other(error.to_string()))?;
        Ok(Self(unsafe { OwnedHandle::from_raw_handle(raw.0) }))
    }

    fn handle(&self) -> HANDLE {
        HANDLE(self.0.as_raw_handle())
    }

    fn signaled(&self) -> io::Result<bool> {
        match unsafe { WaitForSingleObject(self.handle(), 0) } {
            WAIT_OBJECT_0 => Ok(true),
            WAIT_TIMEOUT => Ok(false),
            _ => Err(io::Error::last_os_error()),
        }
    }

    fn wait_signaled(&self) -> io::Result<()> {
        match unsafe { WaitForSingleObject(self.handle(), 3_000) } {
            WAIT_OBJECT_0 => Ok(()),
            WAIT_TIMEOUT => Err(io::Error::new(
                io::ErrorKind::TimedOut,
                "descendant did not signal after Job termination",
            )),
            _ => Err(io::Error::last_os_error()),
        }
    }

    fn cleanup(&self) -> io::Result<()> {
        if !self.signaled()? {
            // It may exit between the zero-time observation and termination.
            // Only the wait on this retained handle establishes cleanup.
            let _ = unsafe { TerminateProcess(self.handle(), 1) };
        }
        if unsafe { WaitForSingleObject(self.handle(), 3_000) } != WAIT_OBJECT_0 {
            return Err(io::Error::other("descendant cleanup was not confirmed"));
        }
        Ok(())
    }
}

impl Drop for Descendant {
    fn drop(&mut self) {
        let _ = self.cleanup();
    }
}

struct DescendantObserver {
    proof: Arc<AtomicBool>,
    stop: Arc<AtomicBool>,
    worker: Option<std::thread::JoinHandle<io::Result<()>>>,
}

impl DescendantObserver {
    fn start(descendant: Descendant) -> io::Result<Self> {
        let proof = Arc::new(AtomicBool::new(false));
        let stop = Arc::new(AtomicBool::new(false));
        let (observed, stopped) = (proof.clone(), stop.clone());
        let worker = std::thread::Builder::new()
            .name("owned-descendant-observer".to_owned())
            .spawn(move || {
                // Longer than the 15s execution plus all 8s cleanup stages.
                let deadline = Instant::now() + Duration::from_secs(40);
                let observation = loop {
                    if stopped.load(Ordering::Acquire) {
                        break Err(io::Error::new(
                            io::ErrorKind::Interrupted,
                            "observer stopped",
                        ));
                    }
                    if Instant::now() >= deadline {
                        break Err(io::Error::new(io::ErrorKind::TimedOut, "observer deadline"));
                    }
                    let wait = unsafe { WaitForSingleObject(descendant.handle(), 20) };
                    if stopped.load(Ordering::Acquire) {
                        break Err(io::Error::new(
                            io::ErrorKind::Interrupted,
                            "observer stopped",
                        ));
                    }
                    if Instant::now() >= deadline {
                        break Err(io::Error::new(io::ErrorKind::TimedOut, "observer deadline"));
                    }
                    match wait {
                        WAIT_OBJECT_0 => {
                            // Publish genuine native evidence BEFORE releasing the
                            // process reference that can pin Job ActiveProcesses.
                            observed.store(true, Ordering::Release);
                            break Ok(());
                        }
                        WAIT_TIMEOUT => {}
                        _ => break Err(io::Error::last_os_error()),
                    }
                };
                // A terminal stop/error/deadline is latched before cleanup. This
                // cleanup can kill the process but can never manufacture proof.
                let cleanup = descendant.cleanup();
                drop(descendant);
                observation.and(cleanup)
            })?;
        Ok(Self {
            proof,
            stop,
            worker: Some(worker),
        })
    }

    fn finish(&mut self) -> io::Result<()> {
        self.stop.store(true, Ordering::Release);
        match self.worker.take() {
            Some(worker) => worker
                .join()
                .map_err(|_| io::Error::other("descendant observer panicked"))?,
            None => Ok(()),
        }
    }
}

impl Drop for DescendantObserver {
    fn drop(&mut self) {
        // Short native waits plus bounded cleanup make joining finite even on
        // setup/test failures; no detached observer can outlive the test.
        let _ = self.finish();
    }
}

async fn wait_empty(tree: &owned_tree::ProcessTree) -> io::Result<()> {
    let deadline = Instant::now() + CLEANUP_WAIT;
    while Instant::now() < deadline {
        let empty = tree.is_empty()?;
        if Instant::now() >= deadline {
            break;
        }
        if empty {
            return Ok(());
        }
        tokio::time::sleep(Duration::from_millis(10)).await;
    }
    Err(io::Error::new(
        io::ErrorKind::TimedOut,
        "owned Job did not become empty",
    ))
}

#[test]
fn retaining_request_keeps_an_empty_job_queryable_repeatedly() -> TestResult {
    let tree = owned_tree::ProcessTree::new()?;
    let initial = tree.is_empty();
    let first = tree.request_termination();
    let after_first = tree.is_empty();
    let second = tree.request_termination();
    let after_second = tree.is_empty();
    drop(tree);
    assert!(initial?);
    first?;
    assert!(after_first?);
    second?;
    assert!(after_second?);
    Ok(())
}

#[test]
fn legacy_terminate_consumes_identity_negative_control() -> TestResult {
    // Consumption is intentional legacy behavior, not an unchanged red/green
    // regression assertion. Retaining-method behavior is tested separately.
    let mut tree = owned_tree::ProcessTree::new()?;
    let terminated = tree.terminate();
    let query = tree.is_empty();
    let retaining_request = tree.request_termination();
    let repeated_legacy = tree.terminate();
    drop(tree);
    terminated?;
    assert!(query.is_err());
    assert!(retaining_request.is_err());
    repeated_legacy?;
    Ok(())
}

#[tokio::test]
async fn parent_exit_and_captured_eof_do_not_prove_owned_job_empty() -> TestResult {
    let markers = Markers::new()?;
    let argv = markers.argv();
    let mut command = Command::new(&argv[0]);
    command
        .args(&argv[1..])
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .kill_on_drop(true);
    let (mut child, tree) = owned_tree::spawn(&mut command).await?;
    let descendant = markers.descendant().await?;
    let live_before_release = descendant.signaled().map(|signaled| !signaled);
    let mut stdout = child.stdout.take().ok_or("missing stdout")?;
    let mut stderr = child.stderr.take().ok_or("missing stderr")?;
    std::fs::write(markers.release(), b"release")?;
    let status = tokio::time::timeout(SETUP_WAIT, child.wait()).await??;
    drop(child);
    let (mut out, mut err) = (Vec::new(), Vec::new());
    tokio::time::timeout(SETUP_WAIT, async {
        stdout.read_to_end(&mut out).await?;
        stderr.read_to_end(&mut err).await?;
        io::Result::Ok(())
    })
    .await??;
    let nonempty_after_parent_and_eof = tree.is_empty().map(|empty| !empty);
    let live_after_parent_and_eof = descendant.signaled().map(|signaled| !signaled);
    let requested = tree.request_termination();
    let signaled_after_request = descendant.wait_signaled();
    let cleanup = descendant.cleanup();
    // ActiveProcesses may include a terminated process until all references
    // close, so this test's own handle must not pin the subsequent Job query.
    drop(descendant);
    let drained = wait_empty(&tree).await;
    let repeated_request = tree.request_termination();
    let repeated_empty = tree.is_empty();
    // Record observations first, then clean up before making assertions.
    drop(tree);
    cleanup?;
    assert!(live_before_release?);
    assert!(status.success());
    assert_eq!(out, b"parent_ready\n");
    assert_eq!(err, b"parent_ready\n");
    assert!(nonempty_after_parent_and_eof?);
    assert!(live_after_parent_and_eof?);
    requested?;
    signaled_after_request?;
    drained?;
    repeated_request?;
    assert!(repeated_empty?);
    Ok(())
}

async fn runtime_completion(expected: ExecTermination) -> TestResult {
    let markers = Markers::new()?;
    let manager = ProcessManager::default();
    let timeout = if expected == ExecTermination::TimedOut {
        Duration::from_secs(15)
    } else {
        Duration::from_secs(30)
    };
    let spec = ExecSpec::new(markers.argv(), std::env::current_dir()?)?
        .with_timeout(timeout)?
        .with_tree_exit_confirmation();
    let mut session = manager.start(spec).await?;
    let observations: TestResult<_> = async {
        let descendant = markers.descendant().await?;
        let live_before_trigger = descendant.signaled().map(|signaled| !signaled);
        let mut observer = DescendantObserver::start(descendant)?;
        if expected == ExecTermination::Exited {
            std::fs::write(markers.release(), b"release")?;
        }
        let outcome = tokio::time::timeout(Duration::from_secs(35), async {
            if expected == ExecTermination::Cancelled {
                session.cancel().await
            } else {
                session.wait().await
            }
        })
        .await?;
        // One immediate snapshot of prior native evidence; no wait, PID reopen,
        // sleep or cleanup between outcome return and this Acquire load.
        let immediately_signaled = observer.proof.load(Ordering::Acquire);
        let cleanup = observer.finish();
        drop(observer);
        Ok((outcome, live_before_trigger, immediately_signaled, cleanup))
    }
    .await;
    if observations.is_err() {
        // Settle the supervisor even when fixture setup or the test wait failed.
        let _ = tokio::time::timeout(Duration::from_secs(10), session.cancel()).await;
    }
    drop(session);
    let (outcome, live_before_trigger, immediately_signaled, cleanup) = observations?;
    cleanup?;
    assert!(live_before_trigger?);
    assert_eq!(outcome.termination, expected, "{outcome:?}");
    assert!(
        immediately_signaled,
        "no native exit proof at outcome return"
    );
    assert!(outcome.output_complete, "{outcome:?}");
    if expected == ExecTermination::Exited {
        assert!(outcome.command_ok(), "{outcome:?}");
    }
    Ok(())
}

#[tokio::test]
async fn confirmed_natural_exit_has_immediately_signaled_descendant() -> TestResult {
    runtime_completion(ExecTermination::Exited).await
}

#[tokio::test]
async fn confirmed_cancel_has_immediately_signaled_descendant() -> TestResult {
    runtime_completion(ExecTermination::Cancelled).await
}

#[tokio::test]
async fn confirmed_timeout_has_immediately_signaled_descendant() -> TestResult {
    runtime_completion(ExecTermination::TimedOut).await
}

#[tokio::test]
async fn stopped_live_observer_cleanup_cannot_manufacture_exit_proof() -> TestResult {
    let mut command = Command::new(env!("CARGO_BIN_EXE_process_fixture"));
    command
        .args(["sleep", "60000"])
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .kill_on_drop(true);
    let (mut child, tree) = owned_tree::spawn(&mut command).await?;
    let descendant = Descendant::open(child.id().ok_or("missing fixture pid")?)?;
    let live_before_stop = descendant.signaled().map(|signaled| !signaled);
    let mut observer = DescendantObserver::start(descendant)?;
    let stopped = observer.finish();
    let proof_after_cleanup = observer.proof.load(Ordering::Acquire);
    let reaped = tokio::time::timeout(SETUP_WAIT, child.wait()).await;
    drop(child);
    let drained = wait_empty(&tree).await;
    drop(observer);
    drop(tree);
    assert!(live_before_stop?);
    assert_eq!(stopped.unwrap_err().kind(), io::ErrorKind::Interrupted);
    assert!(
        !proof_after_cleanup,
        "cleanup must not record native exit proof"
    );
    reaped??;
    drained?;
    Ok(())
}

#[tokio::test]
async fn confirmed_output_overflow_preserves_limit_classification() -> TestResult {
    let manager = ProcessManager::default();
    let spec = ExecSpec::new(
        vec![
            env!("CARGO_BIN_EXE_process_fixture").to_owned(),
            "flood".to_owned(),
            "1048576".to_owned(),
        ],
        std::env::current_dir()?,
    )?
    .with_stream_limit(1024)?
    .with_timeout(Duration::from_secs(10))?
    .with_tree_exit_confirmation();
    let mut session = manager.start(spec).await?;
    let observed = tokio::time::timeout(Duration::from_secs(20), session.wait()).await;
    if observed.is_err() {
        let _ = tokio::time::timeout(Duration::from_secs(10), session.cancel()).await;
    }
    drop(session);
    let outcome = observed?;
    assert_eq!(
        outcome.termination,
        ExecTermination::OutputLimit,
        "{outcome:?}"
    );
    assert!(outcome.stdout_truncated);
    assert!(outcome.stdout_total_bytes > outcome.stdout.len() as u64);
    assert!(outcome.stdout.len() <= 1024);
    assert!(!outcome.command_ok());
    Ok(())
}
