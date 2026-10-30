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
