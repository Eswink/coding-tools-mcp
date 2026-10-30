//! Read-only, bounded Git inspection. Repository configuration is untrusted.
//! This module is Linux-only; the existing Windows execution path is unchanged.
use coding_tools_local_agent::{
    ExecSpec, ExecTermination, LinuxSandbox, ProcessManager, SandboxError,
};
use std::{
    os::unix::process::ExitStatusExt,
    path::{Path, PathBuf},
    process::{ExitStatus, Output},
    sync::OnceLock,
    time::Duration,
};

/// Largest `.git` link, `commondir` or `gitdir` record this host will parse.
const GIT_LINK_LIMIT: u64 = 8192;

fn read_git_record(path: &Path) -> Option<String> {
    let metadata = std::fs::symlink_metadata(path).ok()?;
    if !metadata.is_file() || metadata.len() > GIT_LINK_LIMIT {
        return None;
    }
    let text = String::from_utf8(std::fs::read(path).ok()?).ok()?;
    let line = text.strip_suffix('\n').unwrap_or(&text);
    (!line.is_empty() && !line.contains(['\n', '\r', '\0'])).then(|| line.to_owned())
}

/// SPEC-A1 v4 §4.2 (C4). When `root` is a linked Git worktree, return its
/// `(private_gitdir, common_gitdir)`; otherwise `None`.
///
/// Every record here is workspace-controlled, so it only selects candidates;
/// it never names an arbitrary readable directory. The private gitdir must be
/// `<common>/worktrees/<name>` per its own `commondir`, and its `gitdir`
/// back-pointer must name exactly this root's `.git`, which a sandboxed
/// process cannot forge for a directory outside its own writable root.
/// Anything else (a symlinked `.git`, a plain `gitdir:` redirect, a pointer at
/// another worktree's metadata) yields `None`, i.e. the unchanged
/// root-only sandbox.
pub(crate) fn linked_worktree_gitdirs(root: &Path) -> Option<(PathBuf, PathBuf)> {
    let root = std::fs::canonicalize(root).ok()?;
    let link = root.join(".git");
    let target = read_git_record(&link)?;
    let target = target.strip_prefix("gitdir: ")?;
    let private = std::fs::canonicalize(root.join(target)).ok()?;
    let commondir = read_git_record(&private.join("commondir"))?;
    let common = std::fs::canonicalize(private.join(commondir)).ok()?;
    if private.parent()? != common.join("worktrees") || !common.is_dir() {
        return None;
    }
    let back = read_git_record(&private.join("gitdir"))?;
    if std::fs::canonicalize(private.join(back)).ok()? != link {
        return None;
    }
    Some((private, common))
}

/// The Linux sandbox for a host-owned root: `for_worktree` (gitdirs read-only)
/// for a validated linked worktree, otherwise exactly `LinuxSandbox::new`.
///
/// A1 C2-ad (NB5, SPEC-A1 v5 §1.4.2): when `for_worktree` refuses the root (a
/// main root that is itself a linked worktree and contains, or is contained
/// in, its own gitdirs), the root falls back to `LinuxSandbox::new` (the
/// pre-C4 root-only sandbox) instead of failing every exec and Git call with
/// "isolation unavailable". A failure of `new` itself still propagates.
pub(crate) fn sandbox_for_root(root: &Path) -> Result<LinuxSandbox, SandboxError> {
    match linked_worktree_gitdirs(root) {
        Some((private, common)) => {
            LinuxSandbox::for_worktree(root, private, common).or_else(|_| LinuxSandbox::new(root))
        }
        None => LinuxSandbox::new(root),
    }
}

/// All callers provide a host-owned workspace root. A resolved subdirectory is
/// only a cwd, never a replacement authority root.
pub(crate) fn run(
    root: &Path,
    cwd: &Path,
    args: &[&str],
    timeout: Duration,
) -> Result<Output, &'static str> {
    if !matches!(
        args.first().copied(),
        Some("rev-parse" | "status" | "diff" | "log" | "show" | "blame")
    ) {
        return Err("Git inspection only accepts read-only commands");
    }
    let policy = sandbox_for_root(root)
        .map_err(|_| "Git workspace isolation unavailable")?
        .read_only();
    let root = std::fs::canonicalize(root).map_err(|_| "Git workspace unavailable")?;
    let cwd = std::fs::canonicalize(cwd).map_err(|_| "Git working directory unavailable")?;
    if !cwd.starts_with(&root) {
        return Err("Git working directory escaped the workspace");
    }
    let mut argv: Vec<String> = [
        "/usr/bin/git",
        "--no-pager",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "core.pager=cat",
    ]
    .into_iter()
    .map(str::to_owned)
    .collect();
    argv.extend(args.iter().map(|value| (*value).to_owned()));
    let mut spec = ExecSpec::new(argv, cwd)
        .and_then(|value| value.with_timeout(timeout))
        .and_then(|value| value.with_stream_limit(1024 * 1024))
        .map_err(|_| "Git invocation exceeded its limits")?
        .with_sandbox(policy);
    for (key, value) in [
        ("PATH", "/usr/bin:/bin"),
        ("HOME", "/nonexistent"),
        ("LANG", "C.UTF-8"),
        ("GIT_CONFIG_NOSYSTEM", "1"),
        ("GIT_CONFIG_SYSTEM", "/dev/null"),
        ("GIT_CONFIG_GLOBAL", "/dev/null"),
        ("GIT_TERMINAL_PROMPT", "0"),
        ("GIT_OPTIONAL_LOCKS", "0"),
        ("GIT_NO_REPLACE_OBJECTS", "1"),
    ] {
        spec = spec
            .with_env(key, value)
            .map_err(|_| "Invalid host Git configuration")?;
    }
    let mut native_work = super::native_drain::current_child()?;
    if native_work.is_some() {
        spec = spec.with_tree_exit_confirmation();
    }
    super::native_drain::begin(&mut native_work)
        .map_err(|_| "Native Git drain rejected startup")?;
    // The existing public inspection APIs are synchronous and can be called
    // either inside or outside a Tokio runtime. Never nest block_on on a caller's
    // runtime thread. The worker is joined; it cannot detach from its caller.
    let outcome = std::thread::scope(|scope| {
        scope
            .spawn(move || {
                static MANAGER: OnceLock<ProcessManager> = OnceLock::new();
                let manager = MANAGER.get_or_init(|| ProcessManager::new(32).expect("fixed limit"));
                tauri::async_runtime::block_on(manager.run(spec))
            })
            .join()
    });
    let outcome = match outcome {
        Ok(Ok(outcome)) => outcome,
        Ok(Err(error)) => {
            // These errors precede execution. An unclassified spawn failure or
            // panic is conservatively quarantined rather than called drained.
            if matches!(
                error.kind,
                coding_tools_local_agent::ExecErrorKind::InvalidSpec
                    | coding_tools_local_agent::ExecErrorKind::Capacity
                    | coding_tools_local_agent::ExecErrorKind::Sandbox
            ) {
                super::native_drain::complete(native_work);
            }
            return Err("Git isolation or process startup failed");
        }
        Err(_) => return Err("Git inspection worker failed"),
    };
    if outcome.termination != ExecTermination::TerminationUncertain {
        super::native_drain::complete(native_work);
    }
    if outcome.termination != ExecTermination::Exited
        || !outcome.output_complete
        || outcome.stdout_truncated
        || outcome.stderr_truncated
    {
        return Err("Git inspection timed out or output was incomplete");
    }
    let code = outcome
        .exit_code
        .ok_or("Git process termination was uncertain")?;
    Ok(Output {
        status: ExitStatus::from_raw(code << 8),
        stdout: outcome.stdout,
        stderr: outcome.stderr,
    })
}

#[cfg(test)]
#[path = "git_runner_tests.rs"]
mod tests;
