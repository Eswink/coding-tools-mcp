use super::*;
#[cfg(target_os = "linux")]
use coding_tools_local_agent::{Command, ExecDecision};
#[cfg(target_os = "linux")]
use std::time::Duration;

#[cfg(target_os = "linux")]
struct AdmissionGuard<'a> {
    registry: &'a HookRegistry,
    permit: Option<crate::auth::LocalAdmissionPermit>,
}
#[cfg(target_os = "linux")]
impl AdmissionGuard<'_> {
    fn complete(&mut self) {
        self.permit.take();
    }
}
#[cfg(target_os = "linux")]
impl Drop for AdmissionGuard<'_> {
    fn drop(&mut self) {
        if let Some(permit) = self.permit.take() {
            self.registry.retain_uncertain(permit);
        }
    }
}
#[cfg(all(test, target_os = "linux"))]
pub(crate) fn simulate_uncertain_retirement(
    registry: &HookRegistry,
    permit: crate::auth::LocalAdmissionPermit,
) {
    drop(AdmissionGuard {
        registry,
        permit: Some(permit),
    });
}

#[cfg(target_os = "linux")]
pub(super) fn execute(
    invocation: &Invocation<'_>,
    hook: &RegisteredHook,
) -> Result<(), &'static str> {
    invocation.current()?;
    hook.recheck()?;
    artifacts::command_policy(invocation.ctx, &hook.policy_argv, hook.spec.timeout_ms)?;
    let command = Command::new(hook.policy_argv.clone()).map_err(|_| "HOOK_POLICY_REJECTED")?;
    require_allow(&hook.policy, &command)?;
    #[cfg(target_os = "linux")]
    {
        run_linux(invocation, hook)
    }
    #[cfg(not(target_os = "linux"))]
    {
        Err("HOOK_SANDBOX_UNAVAILABLE")
    }
}
#[cfg(target_os = "linux")]
fn require_allow(
    policy: &coding_tools_local_agent::ExecPolicy,
    command: &Command,
) -> Result<(), &'static str> {
    if policy.evaluate(command).decision != Some(ExecDecision::Allow) {
        return Err("HOOK_POLICY_REJECTED");
    }
    Ok(())
}
#[cfg(target_os = "linux")]
fn run_linux(invocation: &Invocation<'_>, hook: &RegisteredHook) -> Result<(), &'static str> {
    use coding_tools_local_agent::{ExecSpec, ExecTermination, ProcessManager};
    let ctx = invocation.ctx;
    let mut sandbox = ctx
        .linux_sandbox
        .as_ref()
        .as_ref()
        .map_err(|_| "HOOK_SANDBOX_UNAVAILABLE")?
        .clone();
    if !hook.spec.workspace_write {
        sandbox = sandbox.read_only();
    }
    let timeout = Duration::from_millis(hook.spec.timeout_ms).min(
        invocation
            .deadline
            .saturating_duration_since(Instant::now()),
    );
    if timeout.is_zero() {
        return Err("HOOK_CANCELLED_OR_EXPIRED");
    }
    let mut spec = ExecSpec::new(hook.argv.clone(), hook.cwd.clone())
        .and_then(|s| s.with_argv0(hook.spec.executable.clone()))
        .and_then(|s| s.with_timeout(timeout))
        .and_then(|s| s.with_stream_limit(4096))
        .and_then(|s| {
            s.with_stdin(
                hook.script
                    .as_ref()
                    .map(|s| s.bytes.clone())
                    .unwrap_or_default(),
            )
        })
        .map_err(|_| "HOOK_MANIFEST_INVALID")?
        .with_sandbox(sandbox)
        .with_tree_exit_confirmation();
    for (key, value) in [
        ("PATH", "/usr/bin:/bin"),
        ("HOME", "/nonexistent"),
        ("LANG", "C.UTF-8"),
        ("PYTHONDONTWRITEBYTECODE", "1"),
    ] {
        spec = spec
            .with_env(key, value)
            .map_err(|_| "HOOK_MANIFEST_INVALID")?;
    }
    let request = ctx
        .remote_request
        .as_ref()
        .ok_or("HOOK_LOCAL_AUTHORITY_REQUIRED")?;
    let ticket = request.service.issue_local_admission_ticket(
        request,
        &["exec.run"],
        &ctx.execution_gate,
    )?;
    let mut work = super::super::native_drain::current_child()?;
    // The ticket is committed inside the actual child worker; queued work cannot
    // outlive revoke/pause/deadline. Native drain owns the real child and pipes.
    let outcome = std::thread::scope(|scope| {
        scope
            .spawn(move || {
                tauri::async_runtime::block_on(async {
                    invocation.current()?;
                    let permit = request.service.commit_local_admission(
                        request,
                        &ctx.execution_gate,
                        ticket,
                    )?;
                    invocation.current()?;
                    super::super::native_drain::begin(&mut work)
                        .map_err(|_| "HOOK_CONTEXT_CHANGED")?;
                    let mut admission = AdmissionGuard {
                        registry: invocation.registry,
                        permit: Some(permit),
                    };
                    let manager = match ProcessManager::new(1) {
                        Ok(manager) => manager,
                        Err(_) => {
                            super::super::native_drain::complete(work.take());
                            admission.complete();
                            return Err("HOOK_CAPACITY");
                        }
                    };
                    let mut process = match manager.start(spec).await {
                        Ok(process) => process,
                        Err(error) => {
                            if matches!(
                                error.kind,
                                coding_tools_local_agent::ExecErrorKind::InvalidSpec
                                    | coding_tools_local_agent::ExecErrorKind::Capacity
                                    | coding_tools_local_agent::ExecErrorKind::Sandbox
                            ) {
                                super::super::native_drain::complete(work.take());
                                admission.complete();
                                return Err("HOOK_START_FAILED");
                            }
                            // AdmissionGuard retains native occupancy on this unknown
                            // post-spawn path; dropping the waiter is not cleanup.
                            return Err("HOOK_OUTCOME_UNKNOWN");
                        }
                    };
                    let mut interrupted = false;
                    let result = loop {
                        tokio::select! {
                            biased;
                            _ = tokio::time::sleep(Duration::from_millis(10)) => {
                                if invocation.current().is_err() {
                                    interrupted = true;
                                    break process.cancel().await;
                                }
                            }
                            result = process.wait() => break result,
                        }
                    };
                    if result.termination != ExecTermination::TerminationUncertain
                        && result.output_complete
                    {
                        super::super::native_drain::complete(work.take());
                        admission.complete();
                    } else {
                        return Err("HOOK_OUTCOME_UNKNOWN");
                    }
                    if interrupted {
                        return Err("HOOK_CANCELLED_OR_EXPIRED");
                    }
                    if !result.command_ok() {
                        return Err("HOOK_EXECUTION_FAILED");
                    }
                    invocation.current()
                })
            })
            .join()
    });
    match outcome {
        Ok(result) => result,
        Err(_) => {
            invocation.registry.quarantine();
            Err("HOOK_OUTCOME_UNKNOWN")
        }
    }
}
#[cfg(all(test, target_os = "linux"))]
mod tests {
    use super::*;
    use coding_tools_local_agent::{ExecPolicy, PrefixRule, TokenPattern};
    #[test]
    fn native_hook_approval_cannot_override_prompt_or_forbidden_policy() {
        let command = Command::new(vec!["/usr/bin/python3".into(), "-".into()]).unwrap();
        for decision in [ExecDecision::Prompt, ExecDecision::Forbidden] {
            let rule = PrefixRule::new(
                vec![TokenPattern::exact("/usr/bin/python3").unwrap()],
                decision,
            )
            .unwrap();
            let policy = ExecPolicy::new(vec![rule], Vec::new(), false).unwrap();
            assert!(require_allow(&policy, &command).is_err());
        }
        assert!(require_allow(
            &ExecPolicy::new(Vec::new(), Vec::new(), false).unwrap(),
            &command
        )
        .is_err());
    }
}

#[cfg(not(target_os = "linux"))]
pub(super) fn execute(
    _invocation: &Invocation<'_>,
    _hook: &RegisteredHook,
) -> Result<(), &'static str> {
    Err("HOOK_SANDBOX_UNAVAILABLE")
}
