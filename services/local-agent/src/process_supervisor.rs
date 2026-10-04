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
        #[cfg(all(test, windows))]
        let tree_exit_query = spec.tree_exit_query;
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
            // The default and PTY paths keep their original consuming termination.
            #[cfg(windows)]
            let terminated = if spec.require_tree_exit {
                tree.request_termination()
            } else {
                tree.terminate()
            };
            #[cfg(unix)]
            let terminated = tree.terminate();
            if must_terminate {
                if terminated.is_err() {
                    termination_confirmed = false;
                }
                let _ = child.start_kill();
                match tokio::time::timeout(TERMINATE_WAIT, child.wait()).await {
                    Ok(Ok(exit)) => status = Some(exit),
                    _ => termination_confirmed = false,
                }
            } else if terminated.is_err() {
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
            #[cfg(windows)]
            if spec.require_tree_exit {
                let query = || {
                    #[cfg(test)]
                    if let Some(query) = &tree_exit_query {
                        return query();
                    }
                    tree.is_empty()
                };
                completion::publish(
                    done_tx,
                    outcome,
                    status.is_some() && io.joined,
                    query,
                    start,
                )
                .await;
                return;
            }
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
    #[cfg(any(windows, test))]
    joined: bool,
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
        let stdout_result = stdout.as_mut().expect("owned stdout task").await;
        // Remove each consumed handle immediately: a later timeout must never
        // poll an already-completed JoinHandle for a second time.
        let _ = stdout.take();
        let stderr_result = stderr.as_mut().expect("owned stderr task").await;
        let _ = stderr.take();
        let stdin_result = stdin.as_mut().expect("owned stdin task").await;
        let _ = stdin.take();
        IoCompletion {
            #[cfg(any(windows, test))]
            joined: stdout_result.is_ok() && stderr_result.is_ok() && stdin_result.is_ok(),
            stdout: stdout_result.unwrap_or(false),
            stderr: stderr_result.unwrap_or(false),
            stdin: stdin_result.unwrap_or(false),
        }
    };
    match tokio::time::timeout(READER_WAIT, readers).await {
        Ok(done) => done,
        Err(_) => {
            let pending = [stdout, stderr, stdin];
            for task in pending.iter().flatten() {
                task.abort();
            }
            for task in pending.into_iter().flatten() {
                let _ = task.await;
            }
            IoCompletion::default()
        }
    }
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
mod tests {
    use super::*;

    #[tokio::test]
    async fn normally_joined_io_error_is_distinct_from_unsettled_tasks() {
        let done = join_io(
            tokio::spawn(async { false }),
            tokio::spawn(async { true }),
            tokio::spawn(async { false }),
        )
        .await;
        assert!(done.joined);
        assert!(!done.stdout && done.stderr && !done.stdin);
    }

    #[tokio::test]
    async fn panicked_io_task_never_claims_normal_settlement() {
        let done = join_io(
            tokio::spawn(async { panic!("injected reader panic") }),
            tokio::spawn(async { true }),
            tokio::spawn(async { true }),
        )
        .await;
        assert!(!done.joined && !done.stdout);
    }

    #[tokio::test]
    async fn timed_out_io_is_uncertain_even_after_abort_and_join() {
        let done = join_io(
            tokio::spawn(std::future::pending::<bool>()),
            tokio::spawn(async { true }),
            tokio::spawn(async { true }),
        )
        .await;
        assert!(!done.joined);
        assert!(!done.stdout && !done.stderr && !done.stdin);
    }

    #[tokio::test]
    async fn timeout_after_stdout_completed_does_not_poll_it_twice() {
        let done = join_io(
            tokio::spawn(async { true }),
            tokio::spawn(std::future::pending::<bool>()),
            tokio::spawn(async { true }),
        )
        .await;
        assert!(!done.joined);
    }

    #[tokio::test]
    async fn timeout_after_both_readers_completed_joins_only_pending_stdin() {
        let done = join_io(
            tokio::spawn(async { true }),
            tokio::spawn(async { true }),
            tokio::spawn(std::future::pending::<bool>()),
        )
        .await;
        assert!(!done.joined);
    }

    #[tokio::test]
    async fn panic_and_cancelled_handles_are_consumed_once_before_later_timeout() {
        let cancelled = tokio::spawn(std::future::pending::<bool>());
        cancelled.abort();
        let done = join_io(
            tokio::spawn(async { panic!("injected prior reader panic") }),
            cancelled,
            tokio::spawn(std::future::pending::<bool>()),
        )
        .await;
        assert!(!done.joined);
    }
}
