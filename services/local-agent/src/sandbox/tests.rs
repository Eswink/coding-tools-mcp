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
