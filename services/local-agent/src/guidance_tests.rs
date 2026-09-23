use super::*;
use std::{
    fs,
    path::{Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
    time::{SystemTime, UNIX_EPOCH},
};

static NEXT_ID: AtomicU64 = AtomicU64::new(1);

struct Workspace {
    root: PathBuf,
}

impl Workspace {
    fn new() -> Self {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let id = NEXT_ID.fetch_add(1, Ordering::Relaxed);
        let root =
            std::env::temp_dir().join(format!("ctm-guidance-{}-{nonce}-{id}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        Self { root }
    }

    fn path(&self, value: &str) -> PathBuf {
        self.root.join(value)
    }

    fn dir(&self, value: &str) -> PathBuf {
        let path = self.path(value);
        fs::create_dir_all(&path).unwrap();
        path
    }

    fn file(&self, value: &str, bytes: impl AsRef<[u8]>) -> PathBuf {
        let path = self.path(value);
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).unwrap();
        }
        fs::write(&path, bytes).unwrap();
        path
    }
}

impl Drop for Workspace {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.root);
    }
}

fn texts(set: &GuidanceSet) -> Vec<(&Path, &str)> {
    set.entries()
        .iter()
        .map(|entry| (entry.scope(), entry.untrusted_text()))
        .collect()
}

#[test]
fn resolves_root_to_leaf_and_excludes_siblings() {
    let ws = Workspace::new();
    ws.file("AGENTS.md", "root");
    ws.file("a/AGENTS.md", "a");
    ws.file("a/b/AGENTS.md", "b");
    ws.file("a/sibling/AGENTS.md", "sibling");
    let target = ws.file("a/b/src/main.rs", "fn main() {}");

    let set = GuidanceResolver::new(&ws.root)
        .unwrap()
        .resolve(target)
        .unwrap();
    assert_eq!(
        texts(&set),
        vec![
            (Path::new("."), "root"),
            (Path::new("a"), "a"),
            (Path::new("a/b"), "b"),
        ]
    );
    assert_eq!(set.total_bytes(), 6);
}

#[test]
fn no_guidance_is_an_empty_success() {
    let ws = Workspace::new();
    let target = ws.file("src/main.rs", "fn main() {}");
    let set = GuidanceResolver::new(&ws.root)
        .unwrap()
        .resolve(target)
        .unwrap();
    assert!(set.is_empty());
    assert_eq!(set.total_bytes(), 0);
}

#[test]
fn lookalike_names_are_ignored() {
    let ws = Workspace::new();
    ws.file("AGENTS.md.bak", "not guidance");
    let target = ws.file("src/main.rs", "fn main() {}");
    let set = GuidanceResolver::new(&ws.root)
        .unwrap()
        .resolve(target)
        .unwrap();
    assert!(set.is_empty());
}

#[test]
fn outside_and_missing_targets_fail_closed() {
    let ws = Workspace::new();
    let other = Workspace::new();
    let outside = other.file("file.rs", "x");
    let resolver = GuidanceResolver::new(&ws.root).unwrap();
    assert_eq!(
        resolver.resolve(outside).unwrap_err(),
        GuidanceError::OutsideWorkspace
    );
    assert_eq!(
        resolver.resolve("missing/file.rs").unwrap_err(),
        GuidanceError::InvalidTarget
    );
}

#[test]
fn configurable_limits_only_narrow_hard_caps() {
    assert!(GuidanceLimits::new(0, 1, 1, 1).is_err());
    assert!(GuidanceLimits::new(65, 1, 1, 1).is_err());
    assert!(GuidanceLimits::new(1, 33, 1, 1).is_err());
    assert!(GuidanceLimits::new(1, 1, 16 * 1024 + 1, 1).is_err());
    assert!(GuidanceLimits::new(1, 1, 1, 64 * 1024 + 1).is_err());
    assert!(GuidanceLimits::new(2, 2, 8, 12).is_ok());
}

#[test]
fn file_count_and_size_bounds_fail_closed() {
    let ws = Workspace::new();
    ws.file("AGENTS.md", "1234");
    ws.file("a/AGENTS.md", "5678");
    let target = ws.file("a/file.rs", "x");

    let one = GuidanceLimits::new(2, 1, 8, 16).unwrap();
    assert_eq!(
        GuidanceResolver::with_limits(&ws.root, one)
            .unwrap()
            .resolve(&target)
            .unwrap_err(),
        GuidanceError::FileCountExceeded
    );

    let small_file = GuidanceLimits::new(2, 2, 3, 16).unwrap();
    assert_eq!(
        GuidanceResolver::with_limits(&ws.root, small_file)
            .unwrap()
            .resolve(&target)
            .unwrap_err(),
        GuidanceError::FileTooLarge
    );
}

#[test]
fn aggregate_and_depth_bounds_fail_closed() {
    let ws = Workspace::new();
    ws.file("AGENTS.md", "123456");
    ws.file("a/AGENTS.md", "abcdef");
    let target = ws.file("a/b/file.rs", "x");

    let total = GuidanceLimits::new(3, 3, 8, 10).unwrap();
    assert_eq!(
        GuidanceResolver::with_limits(&ws.root, total)
            .unwrap()
            .resolve(&target)
            .unwrap_err(),
        GuidanceError::TotalTooLarge
    );

    let depth = GuidanceLimits::new(1, 3, 8, 24).unwrap();
    assert_eq!(
        GuidanceResolver::with_limits(&ws.root, depth)
            .unwrap()
            .resolve(&target)
            .unwrap_err(),
        GuidanceError::DepthExceeded
    );
}

#[test]
fn non_utf8_and_non_file_guidance_fail_closed() {
    let ws = Workspace::new();
    ws.file("AGENTS.md", [0xff, 0xfe]);
    assert_eq!(
        GuidanceResolver::new(&ws.root)
            .unwrap()
            .resolve(&ws.root)
            .unwrap_err(),
        GuidanceError::InvalidUtf8
    );

    fs::remove_file(ws.path("AGENTS.md")).unwrap();
    ws.dir("AGENTS.md");
    assert_eq!(
        GuidanceResolver::new(&ws.root)
            .unwrap()
            .resolve(&ws.root)
            .unwrap_err(),
        GuidanceError::InvalidGuidanceFile
    );
}

#[cfg(unix)]
#[test]
fn symlink_guidance_is_never_trusted() {
    use std::os::unix::fs::symlink;

    let ws = Workspace::new();
    let external = Workspace::new();
    let source = external.file("outside.md", "secret");
    symlink(source, ws.path("AGENTS.md")).unwrap();

    assert_eq!(
        GuidanceResolver::new(&ws.root)
            .unwrap()
            .resolve(&ws.root)
            .unwrap_err(),
        GuidanceError::InvalidGuidanceFile
    );
}

#[test]
fn debug_surfaces_redact_workspace_and_guidance_text() {
    let ws = Workspace::new();
    ws.file("AGENTS.md", "secret instruction");
    let resolver = GuidanceResolver::new(&ws.root).unwrap();
    let set = resolver.resolve(&ws.root).unwrap();

    let resolver_debug = format!("{resolver:?}");
    assert!(!resolver_debug.contains(ws.root.to_string_lossy().as_ref()));
    assert!(resolver_debug.contains("<workspace>"));

    let entry_debug = format!("{:?}", &set.entries()[0]);
    assert!(!entry_debug.contains("secret instruction"));
    assert!(entry_debug.contains("<untrusted-guidance>"));

    let set_debug = format!("{set:?}");
    assert!(!set_debug.contains("secret instruction"));
}
