//! Process supervision and bounded I/O; public types remain in process.rs.
use super::*;

impl ProcessManager {
    pub async fn start(&self, spec: ExecSpec) -> Result<ProcessSession, ExecError> {
        spec.validate()?;
        let cwd = std::fs::canonicalize(&spec.cwd).map_err(|_| {
            ExecError::new(ExecErrorKind::InvalidSpec, "working directory unavailable")
        })?;
        if !cwd.is_dir() {
            return Err(ExecError::new(
                ExecErrorKind::InvalidSpec,
                "working directory must be a directory",
            ));
        }
        let permit =
            self.permits.clone().try_acquire_owned().map_err(|_| {
                ExecError::new(ExecErrorKind::Capacity, "process capacity exhausted")
            })?;

        let mut command = Command::new(&spec.argv[0]);
        #[cfg(unix)]
        if let Some(argv0) = &spec.argv0 {
            use std::os::unix::process::CommandExt;
            command.as_std_mut().arg0(argv0);
        }
        command
            .args(&spec.argv[1..])
            .current_dir(&cwd)
            .env_clear()
            .envs(&spec.env)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());

        #[cfg(target_os = "linux")]
        if let Some(policy) = &spec.sandbox {
            let sandbox = policy
                .prepare(Path::new(&spec.argv[0]), &cwd)
                .map_err(|_| ExecError::new(ExecErrorKind::Sandbox, "sandbox setup rejected"))?;
            // Prepared state is owned by the closure; no allocation after fork.
            unsafe {
                command.pre_exec(move || sandbox.apply());
            }
        }

        let (mut child, tree) = process_tree::spawn(&mut command).await.map_err(|_| {
            #[cfg(target_os = "linux")]
            if spec.sandbox.is_some() {
                return ExecError::new(ExecErrorKind::Sandbox, "sandbox process startup rejected");
            }
            ExecError::new(ExecErrorKind::Spawn, "failed to spawn process")
        })?;
        #[cfg(unix)]
        let process_id = child.id();
        let stdin = child.stdin.take();
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| ExecError::new(ExecErrorKind::Spawn, "stdout pipe unavailable"))?;
        let stderr = child
            .stderr
            .take()
            .ok_or_else(|| ExecError::new(ExecErrorKind::Spawn, "stderr pipe unavailable"))?;

        let id = format!("proc-{}", self.next_id.fetch_add(1, Ordering::Relaxed));
        let stdout_state = Arc::new(Mutex::new(StreamState::default()));
        let stderr_state = Arc::new(Mutex::new(StreamState::default()));
        let (overflow_tx, mut overflow_rx) = mpsc::unbounded_channel();
        let stdout_task = tokio::spawn(read_bounded(
            stdout,
            stdout_state.clone(),
            spec.stream_limit,
            overflow_tx.clone(),
        ));
        let stderr_task = tokio::spawn(read_bounded(
            stderr,
            stderr_state.clone(),
            spec.stream_limit,
            overflow_tx,
        ));

        let (stdin_error_tx, mut stdin_error_rx) = mpsc::unbounded_channel();
        let stdin_bytes = spec.stdin;
        let stdin_task = tokio::spawn(async move {
            let result = async move {
                let mut input = stdin.ok_or_else(|| std::io::Error::other("stdin unavailable"))?;
                if !stdin_bytes.is_empty() {
                    input.write_all(&stdin_bytes).await?;
                }
                input.shutdown().await
            }
            .await;
            let complete = result.is_ok();
            if !complete {
                let _ = stdin_error_tx.send(());
            }
            complete
        });

        let (cancel_tx, mut cancel_rx) = watch::channel(false);
        let (done_tx, done_rx) = watch::channel(None);
        let supervisor_id = id.clone();
        let timeout = spec.timeout;
        tokio::spawn(async move {
            let _permit = permit;
            let start = Instant::now();
            let mut tree = tree;
            let deadline = tokio::time::sleep(timeout);
            tokio::pin!(deadline);

            let mut termination = ExecTermination::Exited;
            let mut status: Option<ExitStatus> = None;
            let mut must_terminate = false;
            tokio::select! {
                result = child.wait() => {
                    status = result.ok();
                }
                _ = &mut deadline => {
                    termination = ExecTermination::TimedOut;
                    must_terminate = true;
                }
                changed = cancel_rx.changed() => {
                    if changed.is_ok() && *cancel_rx.borrow() {
                        termination = ExecTermination::Cancelled;
                        must_terminate = true;
                    } else {
                        termination = ExecTermination::TerminationUncertain;
                        must_terminate = true;
                    }
                }
                Some(_) = overflow_rx.recv() => {
                    termination = ExecTermination::OutputLimit;
                    must_terminate = true;
                }
                Some(_) = stdin_error_rx.recv() => {
                    termination = ExecTermination::StdinError;
                    must_terminate = true;
                }
            }

            let mut termination_confirmed = true;
            if must_terminate {
                if tree.terminate().is_err() {
                    termination_confirmed = false;
                }
                let _ = child.start_kill();
                match tokio::time::timeout(TERMINATE_WAIT, child.wait()).await {
                    Ok(Ok(exit)) => status = Some(exit),
                    _ => termination_confirmed = false,
                }
            } else if tree.terminate().is_err() {
                termination_confirmed = false;
            }

            if !termination_confirmed {
                termination = ExecTermination::TerminationUncertain;
            }

            let io = join_io(stdout_task, stderr_task, stdin_task).await;
            #[cfg(unix)]
            if spec.require_tree_exit && !confirm_group_exit(process_id).await {
                termination = ExecTermination::TerminationUncertain;
            }
            let stdout = take_stream(&stdout_state);
            let stderr = take_stream(&stderr_state);
            let output_complete = io.stdout && io.stderr;
            if termination == ExecTermination::Exited {
                if stdout.truncated || stderr.truncated {
                    termination = ExecTermination::OutputLimit;
                } else if !io.stdin {
                    termination = ExecTermination::StdinError;
                } else if !output_complete {
                    termination = ExecTermination::OutputError;
                }
            }
            let duration_ms = start.elapsed().as_millis().min(u128::from(u64::MAX)) as u64;
            let outcome = ExecOutcome {
                session_id: supervisor_id,
                termination,
                exit_code: status.and_then(|value| value.code()),
                stdout: stdout.retained,
                stderr: stderr.retained,
                stdout_total_bytes: stdout.total,
                stderr_total_bytes: stderr.total,
                stdout_truncated: stdout.truncated,
                stderr_truncated: stderr.truncated,
                output_complete,
                duration_ms,
            };
            done_tx.send_replace(Some(outcome));
        });

        Ok(ProcessSession {
            id,
            cancel: cancel_tx,
            done: done_rx,
        })
    }
}

pub(super) async fn read_bounded<R>(
    mut stream: R,
    state: SharedStream,
    limit: usize,
    overflow: mpsc::UnboundedSender<()>,
) -> bool
where
    R: AsyncRead + Unpin,
{
    let mut signalled = false;
    let mut buf = [0u8; 4096];
    loop {
        let read = match stream.read(&mut buf).await {
            Ok(read) => read,
            Err(_) => return false,
        };
        if read == 0 {
            return true;
        }
        let mut shared = match state.lock() {
            Ok(value) => value,
            Err(_) => return false,
        };
        shared.total = shared.total.saturating_add(read as u64);
        let remaining = limit.saturating_sub(shared.retained.len());
        let keep = remaining.min(read);
        if keep != 0 {
            shared.retained.extend_from_slice(&buf[..keep]);
        }
        if keep < read {
            shared.truncated = true;
            if !signalled {
                signalled = true;
                let _ = overflow.send(());
            }
        }
    }
}

#[derive(Clone, Copy, Debug, Default)]
struct IoCompletion {
    stdout: bool,
    stderr: bool,
    stdin: bool,
}

async fn join_io(
    stdout: JoinHandle<bool>,
    stderr: JoinHandle<bool>,
    stdin: JoinHandle<bool>,
) -> IoCompletion {
    let (mut stdout, mut stderr, mut stdin) = (Some(stdout), Some(stderr), Some(stdin));
    let readers = async {
        IoCompletion {
            stdout: join_once(&mut stdout).await,
            stderr: join_once(&mut stderr).await,
            stdin: join_once(&mut stdin).await,
        }
    };
    match tokio::time::timeout(READER_WAIT, readers).await {
        Ok(done) => done,
        Err(_) => {
            for task in [&stdout, &stderr, &stdin].into_iter().flatten() {
                task.abort();
            }
            for task in [stdout, stderr, stdin].into_iter().flatten() {
                let _ = task.await;
            }
            IoCompletion::default()
        }
    }
}

async fn join_once(task: &mut Option<JoinHandle<bool>>) -> bool {
    let result = task.as_mut().expect("unconsumed I/O task").await;
    // Remove the consumed handle before the next await can suspend.
    task.take();
    result.unwrap_or(false)
}

pub(super) fn take_stream(state: &SharedStream) -> StreamState {
    let Ok(mut guard) = state.lock() else {
        return StreamState {
            retained: Vec::new(),
            total: 0,
            truncated: true,
        };
    };
    std::mem::take(&mut *guard)
}

#[cfg(unix)]
pub(super) async fn confirm_group_exit(process_id: Option<u32>) -> bool {
    let Some(id) = process_id
        .and_then(|n| i32::try_from(n).ok())
        .filter(|n| *n > 1)
    else {
        return false;
    };
    let deadline = tokio::time::Instant::now() + TERMINATE_WAIT;
    loop {
        // Only observe. Do not kill again using a possibly recycled identifier.
        if unsafe { libc::kill(-id, 0) } < 0 {
            return std::io::Error::last_os_error().raw_os_error() == Some(libc::ESRCH);
        }
        if tokio::time::Instant::now() >= deadline {
            return false;
        }
        tokio::time::sleep(Duration::from_millis(20)).await;
    }
}

#[cfg(test)]
#[path = "process_io_join_tests.rs"]
mod io_join_tests;
