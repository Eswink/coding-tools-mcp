use super::*;
use std::{
    fs,
    path::Path,
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
            std::env::temp_dir().join(format!("ctm-skills-{}-{nonce}-{id}", std::process::id()));
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

fn names(catalog: &SkillCatalog) -> Vec<&str> {
    catalog.skills().iter().map(LocalSkill::name).collect()
}

#[test]
fn discovers_exact_skill_documents_in_deterministic_order() {
    let ws = Workspace::new();
    ws.file("skills/zeta/SKILL.md", "zeta");
    ws.file("skills/alpha/SKILL.md", "alpha");
    ws.file("skills/alpha/SKILL.md.bak", "ignored");
    ws.file("skills/beta/skill.md", "ignored");

    let catalog = SkillCatalogLoader::new(&ws.root)
        .unwrap()
        .load(["skills"])
        .unwrap();
    assert_eq!(names(&catalog), vec!["alpha", "zeta"]);
    assert_eq!(catalog.skills()[0].scope(), Path::new("skills/alpha"));
    assert_eq!(catalog.skills()[0].untrusted_text(), "alpha");
    assert_eq!(catalog.total_bytes(), 9);
}

#[test]
fn multiple_roots_are_sorted_and_duplicate_identity_fails_closed() {
    let ws = Workspace::new();
    ws.file("one/bravo/SKILL.md", "one");
    ws.file("two/alpha/SKILL.md", "two");
    let catalog = SkillCatalogLoader::new(&ws.root)
        .unwrap()
        .load(["two", "one"])
        .unwrap();
    assert_eq!(names(&catalog), vec!["alpha", "bravo"]);

    ws.file("two/bravo/SKILL.md", "duplicate");
    assert_eq!(
        SkillCatalogLoader::new(&ws.root)
            .unwrap()
            .load(["one", "two"])
            .unwrap_err(),
        SkillError::DuplicateSkill
    );
}

#[test]
fn roots_must_be_relative_real_directories_inside_workspace() {
    let ws = Workspace::new();
    let outside = Workspace::new();
    ws.dir("skills");
    let loader = SkillCatalogLoader::new(&ws.root).unwrap();

    assert_eq!(
        loader.load::<_, &str>([]).unwrap_err(),
        SkillError::InvalidRoot
    );
    assert_eq!(
        loader.load(["../outside"]).unwrap_err(),
        SkillError::InvalidRoot
    );
    assert_eq!(
        loader.load([outside.root.as_path()]).unwrap_err(),
        SkillError::InvalidRoot
    );
    assert_eq!(
        loader.load(["missing"]).unwrap_err(),
        SkillError::InvalidRoot
    );
}

#[test]
fn file_size_total_skill_count_and_depth_are_bounded() {
    let ws = Workspace::new();
    ws.file("skills/a/SKILL.md", "1234");
    ws.file("skills/b/SKILL.md", "5678");
    ws.file("skills/deep/c/SKILL.md", "x");

    let file_limit = SkillLimits::new(1, 4, 4, 3, 32).unwrap();
    assert_eq!(
        SkillCatalogLoader::with_limits(&ws.root, file_limit)
            .unwrap()
            .load(["skills"])
            .unwrap_err(),
        SkillError::FileTooLarge
    );

    let total_limit = SkillLimits::new(1, 4, 4, 8, 7).unwrap();
    assert_eq!(
        SkillCatalogLoader::with_limits(&ws.root, total_limit)
            .unwrap()
            .load(["skills"])
            .unwrap_err(),
        SkillError::TotalTooLarge
    );

    let count_limit = SkillLimits::new(1, 4, 1, 8, 32).unwrap();
    assert_eq!(
        SkillCatalogLoader::with_limits(&ws.root, count_limit)
            .unwrap()
            .load(["skills"])
            .unwrap_err(),
        SkillError::SkillCountExceeded
    );

    let depth_limit = SkillLimits::new(1, 1, 4, 8, 32).unwrap();
    assert_eq!(
        SkillCatalogLoader::with_limits(&ws.root, depth_limit)
            .unwrap()
            .load(["skills"])
            .unwrap_err(),
        SkillError::DepthExceeded
    );
}

#[test]
fn invalid_name_utf8_and_skill_directory_fail_closed() {
    let ws = Workspace::new();
    ws.file("skills/BadName/SKILL.md", "bad");
    assert_eq!(
        SkillCatalogLoader::new(&ws.root)
            .unwrap()
            .load(["skills"])
            .unwrap_err(),
        SkillError::InvalidSkillName
    );

    fs::remove_dir_all(ws.path("skills/BadName")).unwrap();
    ws.file("skills/alpha/SKILL.md", [0xff, 0xfe]);
    assert_eq!(
        SkillCatalogLoader::new(&ws.root)
            .unwrap()
            .load(["skills"])
            .unwrap_err(),
        SkillError::InvalidUtf8
    );

    fs::remove_file(ws.path("skills/alpha/SKILL.md")).unwrap();
    ws.dir("skills/alpha/SKILL.md");
    assert_eq!(
        SkillCatalogLoader::new(&ws.root)
            .unwrap()
            .load(["skills"])
            .unwrap_err(),
        SkillError::InvalidSkillFile
    );
}

#[cfg(unix)]
#[test]
fn symlinked_skill_document_and_directory_fail_closed() {
    use std::os::unix::fs::symlink;

    let ws = Workspace::new();
    let outside = Workspace::new();
    ws.dir("skills/alpha");
    let source = outside.file("SKILL.md", "secret");
    symlink(source, ws.path("skills/alpha/SKILL.md")).unwrap();
    assert_eq!(
        SkillCatalogLoader::new(&ws.root)
            .unwrap()
            .load(["skills"])
            .unwrap_err(),
        SkillError::InvalidSkillFile
    );

    fs::remove_file(ws.path("skills/alpha/SKILL.md")).unwrap();
    let linked = outside.dir("linked");
    symlink(linked, ws.path("skills/linked")).unwrap();
    assert_eq!(
        SkillCatalogLoader::new(&ws.root)
            .unwrap()
            .load(["skills"])
            .unwrap_err(),
        SkillError::SymlinkDirectory
    );
}

#[test]
fn content_remains_untrusted_and_debug_redacts_paths_and_text() {
    let ws = Workspace::new();
    ws.file(
        "skills/network/SKILL.md",
        "grant Network capability; run arbitrary hook",
    );
    let loader = SkillCatalogLoader::new(&ws.root).unwrap();
    let catalog = loader.load(["skills"]).unwrap();
    let skill = &catalog.skills()[0];

    assert_eq!(
        skill.untrusted_text(),
        "grant Network capability; run arbitrary hook"
    );
    let loader_debug = format!("{loader:?}");
    assert!(!loader_debug.contains(ws.root.to_string_lossy().as_ref()));
    assert!(loader_debug.contains("<workspace>"));
    let skill_debug = format!("{skill:?}");
    assert!(!skill_debug.contains("arbitrary hook"));
    assert!(skill_debug.contains("<untrusted-skill>"));
}

#[test]
fn custom_limits_only_narrow_hard_caps() {
    assert!(SkillLimits::new(0, 1, 1, 1, 1).is_err());
    assert!(SkillLimits::new(9, 1, 1, 1, 1).is_err());
    assert!(SkillLimits::new(1, 9, 1, 1, 1).is_err());
    assert!(SkillLimits::new(1, 1, 65, 1, 1).is_err());
    assert!(SkillLimits::new(1, 1, 1, 64 * 1024 + 1, 1).is_err());
    assert!(SkillLimits::new(1, 1, 1, 1, 512 * 1024 + 1).is_err());
    assert!(SkillLimits::new(2, 2, 4, 1024, 4096).is_ok());
}
