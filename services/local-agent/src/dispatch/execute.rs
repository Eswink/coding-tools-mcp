use super::{denied, execution_error, now, Arguments, Core, STREAM_LIMIT};
use crate::{ExecSpec, PtySize, PtySpec, PtyTermination, ToolError, ToolOutput};
use serde_json::{json, Value};
use std::{sync::Arc, time::Duration};
use tokio::sync::{oneshot, OwnedSemaphorePermit};

pub(super) async fn run(
    core: Arc<Core>,
    pty: bool,
    args: Arguments,
    expires: u64,
    mut reply: oneshot::Sender<Result<ToolOutput, ToolError>>,
    _slot: OwnedSemaphorePermit,
) {
    let result = run_owned(&core, pty, args, expires, &mut reply).await;
    let _ = reply.send(result.map(ToolOutput::json));
}

async fn run_owned(
    core: &Core,
    pty: bool,
    args: Arguments,
    expires: u64,
    reply: &mut oneshot::Sender<Result<ToolOutput, ToolError>>,
) -> Result<Value, ToolError> {
    let mut stop = core.stop.subscribe();
    let open = core.open.lock().await;
    let time = now()?;
    if !*open || *stop.borrow() || reply.is_closed() || time >= expires {
        return Err(denied());
    }
    let remaining = Duration::from_millis(expires - time);
    let deadline = tokio::time::Instant::now()
        .checked_add(remaining)
        .ok_or_else(denied)?;
    let timeout = Duration::from_millis(args.timeout_ms).min(remaining);
    let cwd = core.root.join(&args.cwd);
    if pty {
        let size = PtySize::new(args.columns.unwrap_or(80), args.rows.unwrap_or(24))
            .map_err(|_| super::invalid())?;
        let spec = PtySpec::new(args.argv, cwd)
            .and_then(|spec| spec.with_size(size))
            .and_then(|spec| spec.with_timeout(timeout))
            .and_then(|spec| spec.with_output_limit(STREAM_LIMIT))
            .map_err(|_| super::invalid())?
            .with_sandbox(core.sandbox.clone());
        let mut session = core.ptys.start(spec).await.map_err(|_| execution_error())?;
        drop(open);
        // Input is delivered only after a completed, owned, sandboxed start.
        if !reply.is_closed()
            && !*stop.borrow()
            && tokio::time::Instant::now() < deadline
            && !args.stdin.is_empty()
            && session.write(args.stdin.as_bytes()).is_err()
        {
            session.cancel().await;
            return Err(execution_error());
        }
        let completed = tokio::select! {
            biased;
            _ = reply.closed() => None,
            _ = stop.wait_for(|revoked| *revoked) => None,
            _ = tokio::time::sleep_until(deadline) => None,
            outcome = session.wait() => Some(outcome),
        };
        let ended = completed.is_none();
        let outcome = match completed {
            Some(outcome) => outcome,
            None => session.cancel().await,
        };
        let ok = !ended
            && outcome.termination == PtyTermination::Exited
            && outcome.exit_code == Some(0)
            && outcome.output_complete
            && !outcome.truncated;
        Ok(json!({"ok":ok,"authorization_ended":ended,"outcome":outcome}))
    } else {
        let spec = ExecSpec::new(args.argv, cwd)
            .and_then(|spec| spec.with_stdin(args.stdin.into_bytes()))
            .and_then(|spec| spec.with_timeout(timeout))
            .and_then(|spec| spec.with_stream_limit(STREAM_LIMIT))
            .map_err(|_| super::invalid())?
            .with_sandbox(core.sandbox.clone());
        let mut session = core
            .processes
            .start(spec)
            .await
            .map_err(|_| execution_error())?;
        drop(open);
        let completed = tokio::select! {
            biased;
            _ = reply.closed() => None,
            _ = stop.wait_for(|revoked| *revoked) => None,
            _ = tokio::time::sleep_until(deadline) => None,
            outcome = session.wait() => Some(outcome),
        };
        let ended = completed.is_none();
        let outcome = match completed {
            Some(outcome) => outcome,
            None => session.cancel().await,
        };
        Ok(
            json!({"ok":!ended && outcome.command_ok(),"authorization_ended":ended,"outcome":outcome}),
        )
    }
}
