#![cfg(all(target_os = "linux", target_arch = "x86_64"))]
//! SPEC-A1 v4 §4.2 (C4): `LinuxSandbox::for_worktree` grants a linked worktree
//! exactly read access to its private and common gitdirs, and no new writes.

use coding_tools_local_agent::{ExecSpec, LinuxSandbox, ProcessManager};
use std::{
    fs,
    path::PathBuf,
    sync::atomic::{AtomicU64, Ordering},
    time::{SystemTime, UNIX_EPOCH},
};

struct Layout {
    parent: PathBuf,
    root: PathBuf,
    common: PathBuf,
    private: PathBuf,
    sibling: PathBuf,
}
impl Layout {
    fn new() -> Self {
        static NEXT: AtomicU64 = AtomicU64::new(0);
        let parent = std::env::temp_dir().join(format!(
            "ctm-worktree-{}-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        let root = parent.join("tree");
        let repo = parent.join("repo");
        let common = repo.join(".git");
        let private = common.join("worktrees").join("w1");
        fs::create_dir_all(&root).unwrap();
        fs::create_dir_all(&private).unwrap();
        fs::write(repo.join("main-checkout.txt"), b"main").unwrap();
        fs::write(common.join("config"), b"common-config\n").unwrap();
        fs::write(private.join("HEAD"), b"private-head\n").unwrap();
        let sibling = parent.join("sibling");
        fs::create_dir_all(&sibling).unwrap();
        fs::write(sibling.join("secret"), b"private").unwrap();
        Self {
            parent,
            root,
            common,
            private,
            sibling,
        }
    }
    fn policy(&self) -> LinuxSandbox {
        LinuxSandbox::for_worktree(&self.root, &self.private, &self.common).unwrap()
    }
}
impl Drop for Layout {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.parent);
    }
}

/// Runs `script` under `/bin/sh` and returns its stdout lines.
async fn probe(layout: &Layout, policy: LinuxSandbox, script: &str) -> Vec<String> {
    // argv tokens are single-line; join the probe's statements.
    let script = script.trim().lines().collect::<Vec<_>>().join("; ");
    let spec = ExecSpec::new(vec!["/bin/sh".into(), "-c".into(), script], &layout.root)
        .unwrap()
        .with_env("PATH", "/usr/bin:/bin")
        .unwrap()
        .with_env("COMMON", layout.common.to_str().unwrap())
        .unwrap()
        .with_env("PRIVATE", layout.private.to_str().unwrap())
        .unwrap()
        .with_env("SIBLING", layout.sibling.to_str().unwrap())
        .unwrap()
        .with_sandbox(policy);
    let output = ProcessManager::default().run(spec).await.unwrap();
    String::from_utf8_lossy(&output.stdout)
        .lines()
        .map(str::to_owned)
        .collect()
}

const READS: &str = r#"
cat "$COMMON/config" 2>/dev/null || echo common-unreadable
cat "$PRIVATE/HEAD" 2>/dev/null || echo private-unreadable
ls "$COMMON/worktrees" 2>/dev/null || echo common-unlistable
cat "$COMMON/../main-checkout.txt" 2>/dev/null || echo main-checkout-unreadable
cat "$SIBLING/secret" 2>/dev/null || echo sibling-unreadable
"#;

const WRITES: &str = r#"
(echo x > "$COMMON/new") 2>/dev/null && echo common-created || echo common-create-denied
(echo x >> "$COMMON/config") 2>/dev/null && echo common-appended || echo common-append-denied
(echo x > "$PRIVATE/index.lock") 2>/dev/null && echo private-created || echo private-create-denied
(echo x > "$PRIVATE/HEAD") 2>/dev/null && echo private-truncated || echo private-truncate-denied
mkdir "$PRIVATE/dir" 2>/dev/null && echo private-mkdir || echo private-mkdir-denied
rm -f "$PRIVATE/HEAD" 2>/dev/null; test -e "$PRIVATE/HEAD" && echo private-kept || echo private-removed
echo x > "inside.txt" && echo root-writable
"#;

#[tokio::test]
async fn for_worktree_reads_both_gitdirs_but_nothing_else_outside_the_root() {
    let layout = Layout::new();
    assert_eq!(
        probe(&layout, layout.policy(), READS).await,
        [
            "common-config",
            "private-head",
            "w1",
            "main-checkout-unreadable",
            "sibling-unreadable",
        ]
    );
    // The read-only reduction keeps the same gitdir reads.
    assert_eq!(
        probe(&layout, layout.policy().read_only(), READS).await,
        [
            "common-config",
            "private-head",
            "w1",
            "main-checkout-unreadable",
            "sibling-unreadable",
        ]
    );
}

#[tokio::test]
async fn for_worktree_adds_no_write_rights_and_keeps_the_root_writable() {
    let layout = Layout::new();
    assert_eq!(
        probe(&layout, layout.policy(), WRITES).await,
        [
            "common-create-denied",
            "common-append-denied",
            "private-create-denied",
            "private-truncate-denied",
            "private-mkdir-denied",
            "private-kept",
            "root-writable",
        ]
    );
    assert_eq!(
        fs::read(layout.common.join("config")).unwrap(),
        b"common-config\n"
    );
    assert_eq!(
        fs::read(layout.private.join("HEAD")).unwrap(),
        b"private-head\n"
    );
    assert!(!layout.common.join("new").exists());
    assert!(!layout.private.join("index.lock").exists());
}

#[tokio::test]
async fn a_plain_root_policy_still_cannot_read_the_gitdirs() {
    let layout = Layout::new();
    assert_eq!(
        probe(&layout, LinuxSandbox::new(&layout.root).unwrap(), READS).await,
        [
            "common-unreadable",
            "private-unreadable",
            "common-unlistable",
            "main-checkout-unreadable",
            "sibling-unreadable",
        ]
    );
}

/// A1 C4-b (SPEC-A1 v5.3 §4.2): a worker child (`for_worktree`) runs with umask
/// 077, so what it creates is owner-only; a plain root policy keeps the
/// inherited mask.
#[tokio::test]
async fn for_worktree_children_run_with_umask_077() {
    use std::os::unix::fs::PermissionsExt;
    let layout = Layout::new();
    const SCRIPT: &str = r#"
umask
echo x > "$NAME" && mkdir "$NAME.d" && echo created
"#;
    let worker = probe(&layout, layout.policy(), &SCRIPT.replace("$NAME", "w")).await;
    assert_eq!(worker, ["0077", "created"]);
    let mode = |name: &str| {
        fs::metadata(layout.root.join(name))
            .unwrap()
            .permissions()
            .mode()
            & 0o777
    };
    assert_eq!([mode("w"), mode("w.d")], [0o600, 0o700]);

    // Read, not set: umask(2) is process-wide and tests run concurrently.
    let status = fs::read_to_string("/proc/self/status").unwrap();
    let inherited = status
        .lines()
        .find_map(|line| line.strip_prefix("Umask:"))
        .unwrap()
        .trim()
        .to_owned();
    let plain = LinuxSandbox::new(&layout.root).unwrap();
    let root = probe(&layout, plain, &SCRIPT.replace("$NAME", "p")).await;
    assert_eq!(root, [inherited, "created".into()]);
}

/// A1 C4-b (SPEC-A1 v5.3 §4.2): `with_worker_resources` always yields a
/// report, and a worker whose cgroup cannot be delegated (this host has no user
/// systemd/D-Bus in CI) still execs, under the fallback rlimits.
#[tokio::test]
async fn worker_resources_report_and_fallback_limits_reach_the_child() {
    let layout = Layout::new();
    let id = format!("itest-{}", std::process::id());
    let policy = layout.policy().with_worker_resources(&id);
    let report = policy.resource_report().unwrap();
    let limits = probe(&layout, policy, "ulimit -v; ulimit -t").await;
    match report.resource_limit {
        "rlimit_fallback" => {
            assert!(report.cgroup_error.is_some(), "{report:?}");
            assert_eq!(limits, ["4194304", "3600"]);
        }
        "cgroup_v2" => assert!(report.cgroup_error.is_none(), "{report:?}"),
        other => panic!("unexpected resource_limit {other}"),
    }
    coding_tools_local_agent::release_worker_cgroup(&id);
}
