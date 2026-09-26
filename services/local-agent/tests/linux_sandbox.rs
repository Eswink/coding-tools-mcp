#![cfg(all(target_os = "linux", target_arch = "x86_64"))]

use coding_tools_local_agent::{
    ExecErrorKind, ExecSpec, ExecTermination, LinuxSandbox, ProcessManager, PtyManager, PtySize,
    PtySpec, PtyTermination,
};
use std::{
    fs::{self, File},
    os::{
        fd::{AsRawFd, FromRawFd, OwnedFd},
        unix::fs::symlink,
    },
    path::PathBuf,
    sync::atomic::{AtomicU64, Ordering},
    time::{Duration, SystemTime, UNIX_EPOCH},
};

struct Workspace {
    parent: PathBuf,
    root: PathBuf,
    outside: PathBuf,
}
impl Workspace {
    fn new() -> Self {
        static NEXT: AtomicU64 = AtomicU64::new(0);
        let name = format!(
            "ctm-sandbox-{}-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        );
        let parent = std::env::temp_dir().join(name);
        let root = parent.join("workspace");
        let outside = parent.join("outside");
        fs::create_dir_all(&root).unwrap();
        fs::create_dir_all(&outside).unwrap();
        fs::write(outside.join("secret"), b"private").unwrap();
        symlink(&outside, root.join("escape")).unwrap();
        Self {
            parent,
            root,
            outside,
        }
    }
    fn policy(&self) -> LinuxSandbox {
        LinuxSandbox::new(&self.root).unwrap()
    }
    fn spec(&self, args: &[&str]) -> ExecSpec {
        let mut argv = vec![fixture()];
        argv.extend(args.iter().map(|value| (*value).to_owned()));
        ExecSpec::new(argv, &self.root)
            .unwrap()
            .with_sandbox(self.policy())
    }
}
impl Drop for Workspace {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.parent);
    }
}
fn fixture() -> String {
    env!("CARGO_BIN_EXE_sandbox_fixture").to_owned()
}

#[tokio::test]
async fn workspace_read_write_and_symlink_escape_are_kernel_enforced() {
    let ws = Workspace::new();
    let output = ProcessManager::default()
        .run(ws.spec(&["filesystem", ws.outside.to_str().unwrap()]))
        .await
        .unwrap();
    assert!(
        output.command_ok(),
        "{output:?}: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert_eq!(fs::read(ws.root.join("allowed.txt")).unwrap(), b"inside");
    assert_eq!(fs::read(ws.outside.join("secret")).unwrap(), b"private");
    assert!(!ws.outside.join("write").exists());
    assert!(String::from_utf8_lossy(&output.stdout).contains("filesystem-confined"));
}

#[tokio::test]
async fn tcp_udp_ipv6_and_unix_sockets_are_denied() {
    let ws = Workspace::new();
    let output = ProcessManager::default()
        .run(ws.spec(&["network"]))
        .await
        .unwrap();
    assert!(
        output.command_ok(),
        "{output:?}: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(String::from_utf8_lossy(&output.stdout).contains("network-denied"));
}

#[tokio::test]
async fn session_process_group_and_namespace_escape_are_denied() {
    let ws = Workspace::new();
    let output = ProcessManager::default()
        .run(ws.spec(&["session"]))
        .await
        .unwrap();
    assert!(output.command_ok(), "{output:?}");
}

#[tokio::test]
async fn restrictions_are_inherited_by_executed_descendants() {
    let ws = Workspace::new();
    let output = ProcessManager::default()
        .run(ws.spec(&["nested"]))
        .await
        .unwrap();
    assert!(
        output.command_ok(),
        "{output:?}: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(String::from_utf8_lossy(&output.stdout).contains("descendant-confined"));
}

#[tokio::test]
async fn inherited_non_stdio_file_descriptors_are_closed_at_exec() {
    let ws = Workspace::new();
    let file = File::open(ws.outside.join("secret")).unwrap();
    // Deliberately create a descriptor without CLOEXEC, as a hostile embedding
    // might. The sandbox must not rely on every host library setting CLOEXEC.
    let raw = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_DUPFD, 100) };
    assert!(raw >= 100);
    let inherited = unsafe { OwnedFd::from_raw_fd(raw) };
    let output = ProcessManager::default()
        .run(ws.spec(&["fd", &raw.to_string()]))
        .await
        .unwrap();
    assert!(output.command_ok(), "{output:?}");
    drop(inherited);
}

#[tokio::test]
async fn cwd_outside_the_pinned_root_is_rejected_before_exec() {
    let ws = Workspace::new();
    let spec = ExecSpec::new(vec![fixture(), "marker".into()], &ws.outside)
        .unwrap()
        .with_sandbox(ws.policy());
    let error = ProcessManager::default().start(spec).await.unwrap_err();
    assert_eq!(error.kind, ExecErrorKind::Sandbox);
    assert!(!ws.outside.join("must-not-run").exists());
    assert!(!format!("{error:?}").contains(ws.parent.to_str().unwrap()));
}

#[tokio::test]
async fn replacing_workspace_path_does_not_redirect_the_retained_root() {
    let ws = Workspace::new();
    let policy = ws.policy();
    let original = ws.parent.join("original");
    fs::rename(&ws.root, &original).unwrap();
    fs::create_dir(&ws.root).unwrap();
    let spec = ExecSpec::new(vec![fixture(), "marker".into()], &ws.root)
        .unwrap()
        .with_sandbox(policy);
    let output = ProcessManager::default().run(spec).await.unwrap();
    assert!(output.command_ok(), "{output:?}");
    assert!(original.join("must-not-run").exists());
    assert!(!ws.root.join("must-not-run").exists());
}

#[test]
fn unavailable_landlock_never_falls_back_to_unsandboxed_execution() {
    let ws = Workspace::new();
    let output = std::process::Command::new(fixture())
        .arg("denied-kernel")
        .arg(&ws.root)
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(String::from_utf8_lossy(&output.stdout).contains("kernel-unavailable-failed-closed"));
    assert!(!ws.root.join("must-not-run").exists());
}

async fn ready(ws: &Workspace) {
    let until = tokio::time::Instant::now() + Duration::from_secs(5);
    while !(ws.root.join("parent-ready").exists() && ws.root.join("grandchild-ready").exists()) {
        assert!(
            tokio::time::Instant::now() < until,
            "child readiness deadline exceeded"
        );
        tokio::time::sleep(Duration::from_millis(10)).await;
    }
}

async fn assert_tree_stopped(stdout: &[u8]) {
    let pid: i32 = String::from_utf8_lossy(stdout)
        .lines()
        .find_map(|line| line.strip_prefix("grandchild_pid="))
        .expect("grandchild identity")
        .parse()
        .unwrap();
    let until = tokio::time::Instant::now() + Duration::from_secs(5);
    loop {
        let alive = unsafe { libc::kill(pid, 0) } == 0;
        if !alive {
            break;
        }
        // Linux may briefly retain a reparented, killed grandchild as a zombie.
        // A zombie cannot execute. Do not confuse it with a running escape.
        let stat = fs::read_to_string(format!("/proc/{pid}/stat")).unwrap_or_default();
        if stat
            .rsplit_once(") ")
            .is_some_and(|(_, tail)| tail.starts_with("Z "))
        {
            break;
        }
        assert!(
            tokio::time::Instant::now() < until,
            "live grandchild survived cleanup"
        );
        tokio::time::sleep(Duration::from_millis(10)).await;
    }
}

#[tokio::test]
async fn cancellation_kills_sandboxed_descendants() {
    let ws = Workspace::new();
    let mut session = ProcessManager::default()
        .start(ws.spec(&["tree"]))
        .await
        .unwrap();
    ready(&ws).await;
    let output = tokio::time::timeout(Duration::from_secs(8), session.cancel())
        .await
        .unwrap();
    assert_eq!(output.termination, ExecTermination::Cancelled);
    assert!(output.output_complete);
    assert_tree_stopped(&output.stdout).await;
}

#[tokio::test]
async fn timeout_kills_sandboxed_descendants() {
    let ws = Workspace::new();
    let output = ProcessManager::default()
        .run(
            ws.spec(&["tree"])
                .with_timeout(Duration::from_secs(2))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(output.termination, ExecTermination::TimedOut);
    assert_tree_stopped(&output.stdout).await;
}

#[tokio::test]
async fn sandboxed_output_remains_memory_bounded() {
    let ws = Workspace::new();
    let output = ProcessManager::default()
        .run(ws.spec(&["flood"]).with_stream_limit(512).unwrap())
        .await
        .unwrap();
    assert_eq!(output.termination, ExecTermination::OutputLimit);
    assert!(output.stdout.len() <= 512);
    assert!(!output.command_ok());
}

#[tokio::test]
async fn sandboxed_pty_keeps_terminal_size_and_input() {
    let ws = Workspace::new();
    let spec = PtySpec::new(vec![fixture(), "pty".into()], &ws.root)
        .unwrap()
        .with_size(PtySize::new(93, 27).unwrap())
        .unwrap()
        .with_sandbox(ws.policy());
    let mut session = PtyManager::default().start(spec).await.unwrap();
    session.write(b"ping").unwrap();
    let output = tokio::time::timeout(Duration::from_secs(8), session.wait())
        .await
        .unwrap();
    assert_eq!(output.termination, PtyTermination::Exited);
    assert_eq!(output.exit_code, Some(0));
    assert!(output.output_complete);
    let text = String::from_utf8_lossy(&output.output);
    assert!(text.contains("pty:93x27"), "{text}");
    assert!(text.contains("pty-input-ok"), "{text}");
}

#[test]
fn sandbox_debug_and_root_errors_do_not_disclose_paths() {
    let ws = Workspace::new();
    assert!(!format!("{:?}", ws.policy()).contains(ws.root.to_str().unwrap()));
    assert!(LinuxSandbox::new("/").is_err());
    assert!(LinuxSandbox::new(ws.root.join("missing")).is_err());
}

#[tokio::test]
async fn current_kernel_metadata_and_queued_signal_bypasses_are_denied() {
    let ws = Workspace::new();
    let output = ProcessManager::default()
        .run(ws.spec(&["review-boundary"]))
        .await
        .unwrap();
    assert!(
        output.command_ok(),
        "{output:?}: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(String::from_utf8_lossy(&output.stdout).contains("review-boundary-enforced"));
}
