use super::super::super::worktree_boundary::{
    objects_scan_hooks, validate_objects_tree, validate_tree,
};
use super::super::super::worktree_objects::open_source;
use super::*;
use std::path::Path;
use std::sync::atomic::{AtomicBool, Ordering};

fn init_repo() -> (tempfile::TempDir, tempfile::TempDir) {
    let repo = tempfile::tempdir().unwrap();
    let harness = tempfile::tempdir().unwrap();
    git(repo.path(), &["init", "-q"]);
    git(
        repo.path(),
        &["config", "user.email", "tests@example.invalid"],
    );
    git(repo.path(), &["config", "user.name", "Worktree Tests"]);
    fs::write(repo.path().join("README.md"), "baseline\n").unwrap();
    git(repo.path(), &["add", "README.md"]);
    git(repo.path(), &["commit", "-q", "-m", "initial"]);
    (repo, harness)
}

fn objects_dir(repo: &Path) -> std::path::PathBuf {
    repo.join(".git/objects")
}

fn unlink_maintenance_lock(dir: &Path) {
    let path = dir.join("maintenance.lock");
    if path.exists() {
        let _ = fs::remove_file(&path);
    }
}

static CREATED: AtomicBool = AtomicBool::new(false);

fn create_maintenance_lock_once(dir: &Path) {
    if dir.file_name().is_some_and(|name| name == "objects") {
        fs::write(dir.join("maintenance.lock"), b"").unwrap();
        CREATED.store(true, Ordering::SeqCst);
    }
}

#[test]
fn objects_maintenance_lock_appearing_mid_scan_is_still_admitted() {
    let (repo, harness) = init_repo();
    let objects = objects_dir(repo.path());
    assert!(!objects.join("maintenance.lock").exists());
    CREATED.store(false, Ordering::SeqCst);
    let _guard = objects_scan_hooks::install(create_maintenance_lock_once);
    WorktreeManager::new(repo.path(), harness.path(), WORKSPACE_ID)
        .expect("open with mid-scan lock");
    assert!(
        CREATED.load(Ordering::SeqCst),
        "hook must have created the lock"
    );
    assert!(objects.join("maintenance.lock").is_file());
}

#[test]
fn objects_maintenance_lock_disappearing_mid_scan_is_still_admitted() {
    let (repo, harness) = init_repo();
    let objects = objects_dir(repo.path());
    fs::write(objects.join("maintenance.lock"), b"pid").unwrap();
    let _guard = objects_scan_hooks::install(unlink_maintenance_lock);
    WorktreeManager::new(repo.path(), harness.path(), WORKSPACE_ID)
        .expect("open after mid-scan lock unlink");
    assert!(!objects.join("maintenance.lock").exists());
}

#[test]
fn objects_maintenance_lock_symlink_or_non_regular_is_still_a_boundary_violation() {
    let (repo, harness) = init_repo();
    let objects = objects_dir(repo.path());
    let lock = objects.join("maintenance.lock");

    fs::create_dir(&lock).unwrap();
    assert_eq!(
        WorktreeManager::new(repo.path(), harness.path(), WORKSPACE_ID)
            .unwrap_err()
            .code(),
        "BOUNDARY_VIOLATION"
    );
    fs::remove_dir(&lock).unwrap();

    #[cfg(unix)]
    {
        std::os::unix::fs::symlink("/tmp/coding-tools-maintenance-lock-target", &lock).unwrap();
        assert_eq!(
            WorktreeManager::new(repo.path(), harness.path(), WORKSPACE_ID)
                .unwrap_err()
                .code(),
            "BOUNDARY_VIOLATION"
        );
        fs::remove_file(&lock).unwrap();
    }

    #[cfg(unix)]
    {
        use std::os::unix::net::UnixDatagram;
        let socket = UnixDatagram::bind(&lock).unwrap();
        assert_eq!(
            WorktreeManager::new(repo.path(), harness.path(), WORKSPACE_ID)
                .unwrap_err()
                .code(),
            "BOUNDARY_VIOLATION"
        );
        drop(socket);
        fs::remove_file(&lock).unwrap();
    }
}

#[test]
fn objects_maintenance_lock_hard_link_is_still_a_boundary_violation() {
    let (repo, harness) = init_repo();
    let objects = objects_dir(repo.path());
    let lock = objects.join("maintenance.lock");
    let scratch = repo.path().join("maintenance-lock-other");
    fs::write(&scratch, b"pid").unwrap();
    fs::hard_link(&scratch, &lock).unwrap();
    assert_eq!(
        WorktreeManager::new(repo.path(), harness.path(), WORKSPACE_ID)
            .unwrap_err()
            .code(),
        "BOUNDARY_VIOLATION"
    );
}

#[test]
fn a_real_boundary_violation_under_objects_still_fails() {
    let (repo, harness) = init_repo();
    let objects = objects_dir(repo.path());
    let blob = fs::read_dir(&objects)
        .unwrap()
        .filter_map(|entry| entry.ok())
        .find_map(|entry| {
            let path = entry.path();
            if path.is_dir() && entry.file_name() != "info" && entry.file_name() != "pack" {
                fs::read_dir(&path)
                    .ok()?
                    .flatten()
                    .map(|child| child.path())
                    .find(|p| p.is_file())
            } else {
                None
            }
        })
        .expect("seed object blob");
    let evil_dir = objects.join("zz");
    fs::create_dir(&evil_dir).unwrap();
    fs::hard_link(&blob, evil_dir.join("evil")).unwrap();
    assert_eq!(
        WorktreeManager::new(repo.path(), harness.path(), WORKSPACE_ID)
            .unwrap_err()
            .code(),
        "BOUNDARY_VIOLATION"
    );
}

#[test]
fn disappearing_gc_lock_or_nested_lock_is_not_exempt() {
    let (repo, _harness) = init_repo();
    let objects = objects_dir(repo.path());
    fs::write(objects.join("gc.lock"), b"pid").unwrap();
    let _guard = objects_scan_hooks::install(unlink_gc_lock);
    match open_source(repo.path()) {
        Err(err) => assert_eq!(err.code(), "BOUNDARY_VIOLATION"),
        Ok(_) => panic!("expected BOUNDARY_VIOLATION for disappearing gc.lock"),
    }

    fs::create_dir_all(objects.join("pack")).unwrap();
    fs::write(objects.join("pack/tmp_pack_abc.lock"), b"pid").unwrap();
    let _guard = objects_scan_hooks::install(unlink_pack_lock);
    match open_source(repo.path()) {
        Err(err) => assert_eq!(err.code(), "BOUNDARY_VIOLATION"),
        Ok(_) => panic!("expected BOUNDARY_VIOLATION for disappearing pack lock"),
    }

    fs::create_dir(objects.join("zz")).unwrap();
    fs::write(objects.join("zz/maintenance.lock"), b"pid").unwrap();
    let _guard = objects_scan_hooks::install(unlink_nested_maintenance_lock);
    match open_source(repo.path()) {
        Err(err) => assert_eq!(err.code(), "BOUNDARY_VIOLATION"),
        Ok(_) => panic!("expected BOUNDARY_VIOLATION for disappearing nested maintenance.lock"),
    }
}

fn unlink_gc_lock(dir: &Path) {
    let path = dir.join("gc.lock");
    if path.exists() {
        let _ = fs::remove_file(&path);
    }
}

fn unlink_pack_lock(dir: &Path) {
    let path = dir.join("tmp_pack_abc.lock");
    if path.exists() {
        let _ = fs::remove_file(&path);
    }
}

fn unlink_nested_maintenance_lock(dir: &Path) {
    if dir.file_name().is_some_and(|name| name == "zz") {
        let path = dir.join("maintenance.lock");
        if path.exists() {
            let _ = fs::remove_file(&path);
        }
    }
}

#[test]
fn checkout_validate_tree_does_not_receive_the_objects_lock_exemption() {
    let root = tempfile::tempdir().unwrap();
    fs::write(root.path().join("README.md"), b"checkout\n").unwrap();
    fs::write(root.path().join("maintenance.lock"), b"pid").unwrap();
    let _guard = objects_scan_hooks::install(unlink_maintenance_lock);
    let err = validate_tree(root.path(), 50_000, 256 * 1024 * 1024).unwrap_err();
    assert_eq!(err.code(), "BOUNDARY_VIOLATION");

    // The same disappearing lock is skipped by the objects-scan walk.
    let objects = tempfile::tempdir().unwrap();
    fs::write(objects.path().join("pack-placeholder"), b"x").unwrap();
    fs::write(objects.path().join("maintenance.lock"), b"pid").unwrap();
    let _guard = objects_scan_hooks::install(unlink_maintenance_lock);
    validate_objects_tree(objects.path(), 50_000, 256 * 1024 * 1024)
        .expect("objects walk skips a disappearing maintenance.lock");
}
