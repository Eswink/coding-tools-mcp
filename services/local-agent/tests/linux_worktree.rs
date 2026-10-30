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
