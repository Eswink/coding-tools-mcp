use super::*;
use std::{
    os::fd::AsRawFd,
    path::Path,
    sync::atomic::{AtomicU64, Ordering},
};

struct Directory(PathBuf);
impl Directory {
    fn new() -> Self {
        static NEXT: AtomicU64 = AtomicU64::new(0);
        let value = std::env::temp_dir().join(format!(
            "ctm-sandbox-unit-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        std::fs::create_dir(&value).unwrap();
        Self(value)
    }
}
impl Drop for Directory {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}

#[test]
fn cloning_policy_retains_the_same_directory_object() {
    let dir = Directory::new();
    let policy = LinuxSandbox::new(&dir.0).unwrap();
    let clone = policy.clone();
    assert_eq!(clone.root.file.as_raw_fd(), policy.root.file.as_raw_fd());
    drop(policy);
    assert!(clone.root.file.metadata().unwrap().is_dir());
    assert!(!format!("{clone:?}").contains(dir.0.to_str().unwrap()));
}

#[test]
fn preparing_a_policy_does_not_restrict_the_parent() {
    let dir = Directory::new();
    let inside = dir.0.join("inside");
    std::fs::create_dir(&inside).unwrap();
    let policy = LinuxSandbox::new(&inside).unwrap();
    let _prepared = policy.prepare(Path::new("/bin/sh"), &inside).unwrap();
    std::fs::write(dir.0.join("parent-outside"), b"still-authorized").unwrap();
    assert!(std::net::TcpListener::bind("127.0.0.1:0").is_ok());
}

#[test]
fn a_policy_object_does_not_override_forbidden_execution_authority() {
    use crate::{
        Command, ExecDecision, ExecPolicy, ExecutionAuthorization, LocalAdmission, PrefixRule,
        TokenPattern, ToolCall, ToolName, VerifiedInvocation,
    };
    let dir = Directory::new();
    let _sandbox = LinuxSandbox::new(&dir.0).unwrap();
    let policy = ExecPolicy::new(
        vec![PrefixRule::new(
            vec![TokenPattern::exact("/bin/sh").unwrap()],
            ExecDecision::Forbidden,
        )
        .unwrap()],
        vec![],
        false,
    )
    .unwrap();
    let call = ToolCall::new(
        "request",
        "conversation",
        "workspace",
        ToolName::parse("exec_command").unwrap(),
        serde_json::json!({}),
    )
    .unwrap();
    let admission = LocalAdmission::fixture(
        "conversation",
        "workspace",
        [crate::Capability::ProcessExec],
        1,
        1000,
    );
    let verified = VerifiedInvocation::fixture(&admission);
    let command = Command::new(vec!["/bin/sh".into()]).unwrap();
    assert_eq!(
        policy.authorize(&command, &call, &verified, None, 1),
        ExecutionAuthorization::Forbidden
    );
}

/// `[root, common, private]` laid out like a linked Git worktree.
fn worktree_layout(dir: &Directory) -> (PathBuf, PathBuf, PathBuf) {
    let root = dir.0.join("tree");
    let common = dir.0.join("repo").join(".git");
    let private = common.join("worktrees").join("w1");
    std::fs::create_dir_all(&root).unwrap();
    std::fs::create_dir_all(&private).unwrap();
    (root, common, private)
}

fn kind(result: Result<LinuxSandbox, SandboxError>) -> Option<SandboxErrorKind> {
    result.err().map(|error| error.kind)
}

#[test]
fn simulated_landlock_abi1_fails_closed_for_every_policy_shape() {
    // SPEC-A1 v4 §4.2: the Ubuntu 22.04 GA kernel reports Landlock ABI1. That
    // rejection is a pre-existing baseline, and `for_worktree` must not relax it.
    let dir = Directory::new();
    let (root, common, private) = worktree_layout(&dir);
    let policies = [
        LinuxSandbox::new(&root).unwrap(),
        LinuxSandbox::new(&root).unwrap().read_only(),
        LinuxSandbox::for_worktree(&root, &private, &common).unwrap(),
        LinuxSandbox::for_worktree(&root, &private, &common)
            .unwrap()
            .read_only(),
    ];
    for abi in [1, 2] {
        linux::SIMULATED_ABI.with(|value| value.set(Some(abi)));
        for policy in &policies {
            let outcome = policy.prepare(Path::new("/bin/sh"), &root);
            assert_eq!(
                outcome.err().map(|error| error.kind),
                Some(SandboxErrorKind::Unavailable),
                "ABI{abi} must fail closed"
            );
        }
    }
    linux::SIMULATED_ABI.with(|value| value.set(Some(3)));
    for policy in &policies {
        assert_eq!(
            policy
                .prepare(Path::new("/bin/sh"), &root)
                .err()
                .map(|error| error.kind),
            None
        );
    }
    linux::SIMULATED_ABI.with(|value| value.set(None));
}

#[test]
fn for_worktree_only_accepts_a_private_gitdir_directly_under_common_worktrees() {
    let dir = Directory::new();
    let (root, common, private) = worktree_layout(&dir);
    assert_eq!(
        kind(LinuxSandbox::for_worktree(&root, &private, &common)),
        None
    );
    // Private gitdir not under `<common>/worktrees/`.
    let stray = dir.0.join("stray");
    std::fs::create_dir(&stray).unwrap();
    assert_eq!(
        kind(LinuxSandbox::for_worktree(&root, &stray, &common)),
        Some(SandboxErrorKind::InvalidRoot)
    );
    // Nested deeper than a direct child.
    let nested = private.join("nested");
    std::fs::create_dir(&nested).unwrap();
    assert_eq!(
        kind(LinuxSandbox::for_worktree(&root, &nested, &common)),
        Some(SandboxErrorKind::InvalidRoot)
    );
    // The common gitdir itself, or `<common>/worktrees`, is not a private gitdir.
    assert_eq!(
        kind(LinuxSandbox::for_worktree(&root, &common, &common)),
        Some(SandboxErrorKind::InvalidRoot)
    );
    assert_eq!(
        kind(LinuxSandbox::for_worktree(
            &root,
            common.join("worktrees"),
            &common
        )),
        Some(SandboxErrorKind::InvalidRoot)
    );
    // A gitdir may not contain the workspace root: that would widen reads above it.
    let outer = dir.0.join("outer");
    let inner_root = outer.join("worktrees").join("w2");
    std::fs::create_dir_all(&inner_root).unwrap();
    assert_eq!(
        kind(LinuxSandbox::for_worktree(
            &inner_root,
            outer.join("worktrees").join("w2"),
            &outer
        )),
        Some(SandboxErrorKind::InvalidRoot)
    );
    // Nor may the root contain a gitdir.
    let inside_common = root.join(".git");
    std::fs::create_dir_all(inside_common.join("worktrees").join("w3")).unwrap();
    assert_eq!(
        kind(LinuxSandbox::for_worktree(
            &root,
            inside_common.join("worktrees").join("w3"),
            &inside_common
        )),
        Some(SandboxErrorKind::InvalidRoot)
    );
    // Missing paths and system roots are rejected exactly like `new`.
    assert_eq!(
        kind(LinuxSandbox::for_worktree(
            &root,
            common.join("worktrees").join("missing"),
            &common
        )),
        Some(SandboxErrorKind::InvalidRoot)
    );
    assert_eq!(
        kind(LinuxSandbox::for_worktree(
            &root,
            "/usr/worktrees/x",
            "/usr"
        )),
        Some(SandboxErrorKind::InvalidRoot)
    );
    let policy = LinuxSandbox::for_worktree(&root, &private, &common).unwrap();
    assert!(!format!("{policy:?}").contains(dir.0.to_str().unwrap()));
}

/// A1 C4-b (SPEC-A1 v5.3 §4.2): what a sandboxed worker child actually runs
/// under, against a stand-in for the delegated `w-<id>` cgroup directory.
mod worker_resources {
    use super::{resources::WorkerResources, *};
    use std::os::unix::process::CommandExt;

    fn fake_cgroup(parent: &Path) -> PathBuf {
        let root = parent.join("scope");
        let dir = root.join("w-w1");
        std::fs::create_dir_all(&dir).unwrap();
        for file in [
            "cgroup.procs",
            "cgroup.kill",
            "memory.max",
            "pids.max",
            "cpu.max",
        ] {
            std::fs::write(dir.join(file), b"").unwrap();
        }
        root
    }

    fn run(root: &Path, resources: Option<Arc<WorkerResources>>, script: &str) -> Vec<String> {
        let mut command = std::process::Command::new("/bin/sh");
        command
            .args(["-c", script])
            .current_dir(root)
            .env_clear()
            .env("PATH", "/usr/bin:/bin");
        if let Some(resources) = resources {
            let mut policy = LinuxSandbox::new(root).unwrap();
            policy.resources = Some(resources);
            let prepared = policy.prepare(Path::new("/bin/sh"), root).unwrap();
            unsafe {
                command.pre_exec(move || prepared.apply());
            }
        }
        let output = command.output().unwrap();
        assert!(output.status.success(), "{output:?}");
        String::from_utf8(output.stdout)
            .unwrap()
            .lines()
            .map(str::to_owned)
            .collect()
    }

    const LIMITS: &str = "ulimit -v; ulimit -d; ulimit -t; ulimit -a | grep -i process | head -n 1";

    #[test]
    fn a_cgroup_worker_child_joins_w_id_first_and_gets_no_rlimit() {
        let dir = Directory::new();
        let work = dir.0.join("work");
        std::fs::create_dir(&work).unwrap();
        let scope = fake_cgroup(&dir.0);
        let resources = WorkerResources::prepare_under(Ok(&scope), "w1");
        assert_eq!(resources.report().resource_limit, "cgroup_v2");
        let procs = scope.join("w-w1/cgroup.procs");
        std::fs::write(&procs, b"").unwrap(); // drop the setup probe's pid
        let child = run(
            &work,
            Some(Arc::new(resources)),
            &format!("echo $$; {LIMITS}"),
        );
        let host = run(&work, None, LIMITS);
        assert_eq!(
            std::fs::read_to_string(&procs).unwrap(),
            format!("{}\n", child[0])
        );
        assert_eq!(child[1..], host[..]);
    }

    /// A1 C4-c D/E: the fallback sets `RLIMIT_DATA` 8 GiB and `RLIMIT_CPU`,
    /// leaves `RLIMIT_AS` and `RLIMIT_NPROC` exactly as the host has them, and
    /// reports `procs_limit: "none"`.
    #[test]
    fn a_fallback_worker_child_runs_under_data_and_cpu_rlimits_only() {
        let dir = Directory::new();
        let resources = WorkerResources::prepare_under(Err("NO_USER_SYSTEMD"), "w1");
        assert_eq!(resources.report().procs_limit, "none");
        let child = run(&dir.0, Some(Arc::new(resources)), LIMITS);
        let host = run(&dir.0, None, LIMITS);
        assert_eq!(child[0], host[0], "RLIMIT_AS must be the host's");
        assert_eq!(child[1], (FALLBACK_DATA_BYTES >> 10).to_string());
        assert_eq!(child[2], CPU_SECONDS.to_string());
        assert_eq!(child[3], host[3], "RLIMIT_NPROC must be the host's");
    }

    #[test]
    fn a_migration_refused_in_the_child_still_execs_under_every_rlimit() {
        let dir = Directory::new();
        let work = dir.0.join("work");
        std::fs::create_dir(&work).unwrap();
        let scope = fake_cgroup(&dir.0);
        let resources = Arc::new(WorkerResources::prepare_under(Ok(&scope), "w1"));
        assert_eq!(resources.report().resource_limit, "cgroup_v2");
        let procs = scope.join("w-w1/cgroup.procs");
        std::fs::remove_file(&procs).unwrap();
        std::os::unix::fs::symlink("/dev/full", &procs).unwrap(); // write(2) → ENOSPC
        let child = run(&work, Some(resources.clone()), LIMITS);
        let host = run(&work, None, LIMITS);
        assert_eq!(
            child[1..3],
            [
                (FALLBACK_DATA_BYTES >> 10).to_string(),
                CPU_SECONDS.to_string()
            ]
        );
        assert_eq!((&child[0], &child[3]), (&host[0], &host[3]));
        // A1 C4-c F: the refusal in the child reaches the report.
        let report = resources.report();
        assert_eq!(report.resource_limit, "rlimit_fallback");
        assert_eq!(report.cgroup_error.as_deref(), Some("ENOSPC"));
        assert_eq!(report.procs_limit, "none");
    }
}
