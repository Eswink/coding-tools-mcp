//! A1 C9n nit 2: no relay of this worktree outlives the native fixture.
//!
//! `native_desktop_fixture` spawns `python3 -S <gateway>/tests/host_agent_support/
//! relay.py <root>` and the tests stop the fixture with SIGKILL, so the relay is
//! bound to the fixture by `PR_SET_PDEATHSIG` (Linux only). This test starts the
//! frozen `Harness`, sees its relay (positive control), drops the harness and
//! asserts that relay is gone. Removing `die_with_fixture` turns it red.
//!
//! The check is per harness root, because other harness tests of the same binary
//! may run beside it. Deferred (SPEC v5.10): non-Linux platforms (no pdeathsig,
//! `die_with_fixture` is a no-op there) and relay.py exiting on stdin EOF
//! (relay.py is SOURCE_PINS-pinned).
use super::wss_tests::Harness;
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

/// relay.py of this worktree's gateway crate, as the fixture names it.
fn worktree_relay() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../services/cloud-gateway/tests/host_agent_support/relay.py")
        .canonicalize()
        .expect("worktree relay.py")
}

/// (pid, argv) of every live relay process of this worktree.
fn worktree_relays(relay: &Path) -> Vec<(i32, Vec<String>)> {
    let mut found = Vec::new();
    for entry in std::fs::read_dir("/proc").unwrap().flatten() {
        let Some(pid) = entry
            .file_name()
            .to_str()
            .and_then(|s| s.parse::<i32>().ok())
        else {
            continue;
        };
        let Ok(raw) = std::fs::read(entry.path().join("cmdline")) else {
            continue;
        };
        let argv: Vec<String> = raw
            .split(|b| *b == 0)
            .filter(|a| !a.is_empty())
            .map(|a| String::from_utf8_lossy(a).into_owned())
            .collect();
        let is_python = argv
            .first()
            .and_then(|a| Path::new(a).file_name())
            .and_then(|n| n.to_str())
            .is_some_and(|n| n.starts_with("python"));
        let names_relay = argv.iter().skip(1).any(|a| {
            Path::new(a).canonicalize().ok().as_deref() == Some(relay) || Path::new(a) == relay
        });
        if is_python && names_relay && !is_zombie(pid) {
            found.push((pid, argv));
        }
    }
    found
}

fn is_zombie(pid: i32) -> bool {
    std::fs::read_to_string(format!("/proc/{pid}/stat"))
        .ok()
        .and_then(|s| {
            s.rsplit_once(')')
                .map(|(_, rest)| rest.trim_start().starts_with('Z'))
        })
        .unwrap_or(true)
}

fn of_root(relays: &[(i32, Vec<String>)], root: &str) -> Vec<(i32, Vec<String>)> {
    relays
        .iter()
        .filter(|(_, argv)| argv.last().map(String::as_str) == Some(root))
        .cloned()
        .collect()
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn c9n_no_relay_of_this_worktree_outlives_the_fixture() {
    let relay = worktree_relay();
    let h = Harness::start().await;
    let root = h._root.path().canonicalize().unwrap();
    let root = root.to_str().unwrap().to_owned();
    let mine = of_root(&worktree_relays(&relay), &root);
    assert_eq!(
        mine.len(),
        1,
        "positive control: exactly one relay of this harness root {root}: {mine:?}"
    );
    let pid = mine[0].0;
    drop(h);
    let end = Instant::now() + Duration::from_secs(5);
    let left = loop {
        let left = of_root(&worktree_relays(&relay), &root);
        if left.is_empty() || Instant::now() >= end {
            break left;
        }
        tokio::time::sleep(Duration::from_millis(50)).await;
    };
    if !left.is_empty() {
        // Clean up only the processes matched above, by PID, then fail.
        for (leaked, _) in &left {
            // SAFETY: plain kill(2) on a PID read from /proc this instant.
            unsafe {
                libc::kill(*leaked, libc::SIGKILL);
            }
        }
    }
    assert!(
        left.is_empty(),
        "relay of this worktree outlived the fixture 5 s after SIGKILL \
         (spawned pid {pid}, root {root}): {left:?}"
    );
}
