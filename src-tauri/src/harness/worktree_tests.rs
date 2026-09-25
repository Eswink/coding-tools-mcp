use super::*;
use std::fs;
use std::process::Command;

use tempfile::TempDir;

const WORKSPACE_ID: &str = "0123456789abcdef0123456789abcdef";

struct TestRepo {
    repo: TempDir,
    harness: TempDir,
    manager: WorktreeManager,
}

impl TestRepo {
    fn new() -> Self {
        let repo = tempfile::tempdir().expect("repo");
        let harness = tempfile::tempdir().expect("harness");
        git(repo.path(), &["init", "-q"]);
        git(
            repo.path(),
            &["config", "user.email", "tests@example.invalid"],
        );
        git(repo.path(), &["config", "user.name", "Worktree Tests"]);
        fs::write(repo.path().join("README.md"), "baseline\n").expect("seed file");
        git(repo.path(), &["add", "README.md"]);
        git(repo.path(), &["commit", "-q", "-m", "initial"]);
        let manager =
            WorktreeManager::new(repo.path(), harness.path(), WORKSPACE_ID).expect("manager");
        Self {
            repo,
            harness,
            manager,
        }
    }
}

#[test]
fn create_list_and_remove_are_bounded_and_stably_sorted() {
    let fixture = TestRepo::new();
    let first = fixture.manager.create_detached().expect("first");
    let second = fixture.manager.create_detached().expect("second");

    for item in [&first, &second] {
        assert_eq!(item.id.len(), 32);
        assert!(item.id.bytes().all(|byte| byte.is_ascii_hexdigit()));
        assert_eq!(item.display_path, format!("managed/{}", item.id));
        assert!(item.detached);
        assert!(!item.head.is_empty());
        assert!(!item
            .display_path
            .contains(fixture.repo.path().to_string_lossy().as_ref()));
        assert!(!item
            .display_path
            .contains(fixture.harness.path().to_string_lossy().as_ref()));
    }

    let list = fixture.manager.list().expect("list");
    assert_eq!(list.len(), 2);
    assert!(list.windows(2).all(|pair| pair[0].id < pair[1].id));

    fixture
        .manager
        .remove_clean(&first.id)
        .expect("remove first");
    fixture
        .manager
        .remove_clean(&second.id)
        .expect("remove second");
    assert!(fixture.manager.list().expect("empty").is_empty());
}

#[test]
fn remove_refuses_tracked_staged_and_untracked_changes() {
    let fixture = TestRepo::new();
    let item = fixture.manager.create_detached().expect("create");
    let path = fixture.manager.managed_root.join(&item.id);

    fs::write(path.join("README.md"), "modified\n").unwrap();
    assert_eq!(
        fixture.manager.remove_clean(&item.id).unwrap_err().code(),
        "DIRTY"
    );
    git(&path, &["reset", "--hard", "HEAD"]);

    fs::write(path.join("staged.txt"), "staged\n").unwrap();
    git(&path, &["add", "staged.txt"]);
    assert_eq!(
        fixture.manager.remove_clean(&item.id).unwrap_err().code(),
        "DIRTY"
    );
    git(&path, &["reset", "--hard", "HEAD"]);

    fs::write(path.join("untracked.txt"), "untracked\n").unwrap();
    assert_eq!(
        fixture.manager.remove_clean(&item.id).unwrap_err().code(),
        "DIRTY"
    );
    fs::remove_file(path.join("untracked.txt")).unwrap();

    fixture
        .manager
        .remove_clean(&item.id)
        .expect("clean remove");
}

#[test]
fn invalid_unknown_and_non_repository_inputs_fail_closed() {
    let fixture = TestRepo::new();
    assert_eq!(
        fixture
            .manager
            .remove_clean("../escape")
            .unwrap_err()
            .code(),
        "INVALID_ID"
    );
    assert_eq!(
        fixture
            .manager
            .remove_clean("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
            .unwrap_err()
            .code(),
        "NOT_FOUND"
    );

    let workspace = tempfile::tempdir().unwrap();
    let harness = tempfile::tempdir().unwrap();
    let error = WorktreeManager::new(workspace.path(), harness.path(), WORKSPACE_ID).unwrap_err();
    assert_eq!(error.code(), "NOT_REPOSITORY");
    assert!(!harness.path().join("worktrees-v1").exists());
}

#[test]
fn repository_root_outside_approved_workspace_is_rejected() {
    let repo = tempfile::tempdir().unwrap();
    let workspace = repo.path().join("nested");
    fs::create_dir(&workspace).unwrap();
    let harness = tempfile::tempdir().unwrap();
    git(repo.path(), &["init", "-q"]);

    let error = WorktreeManager::new(&workspace, harness.path(), WORKSPACE_ID).unwrap_err();
    assert_eq!(error.code(), "BOUNDARY_VIOLATION");
    assert!(!harness.path().join("worktrees-v1").exists());
}

#[test]
fn capacity_is_enforced_before_a_ninth_worktree_is_created() {
    let fixture = TestRepo::new();
    for _ in 0..MAX_MANAGED_WORKTREES {
        fixture.manager.create_detached().expect("within capacity");
    }
    let error = fixture.manager.create_detached().unwrap_err();
    assert_eq!(error.code(), "CAPACITY");
    assert_eq!(fixture.manager.list().unwrap().len(), MAX_MANAGED_WORKTREES);
}

#[test]
fn oversized_dirty_status_fails_closed_without_removing_worktree() {
    let fixture = TestRepo::new();
    let item = fixture.manager.create_detached().expect("create");
    let path = fixture.manager.managed_root.join(&item.id);
    for index in 0..1700 {
        fs::write(
            path.join(format!(
                "untracked-{index:04}-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx.txt"
            )),
            "x",
        )
        .unwrap();
    }

    let error = fixture.manager.remove_clean(&item.id).unwrap_err();
    assert_eq!(error.code(), "OUTPUT_LIMIT");
    assert!(path.exists());
}

#[test]
fn debug_and_errors_do_not_disclose_host_paths() {
    let fixture = TestRepo::new();
    let debug = format!("{:?}", fixture.manager);
    assert!(!debug.contains(fixture.repo.path().to_string_lossy().as_ref()));
    assert!(!debug.contains(fixture.harness.path().to_string_lossy().as_ref()));

    let error = fixture.manager.remove_clean("invalid").unwrap_err();
    let error_debug = format!("{error:?}");
    assert!(!error_debug.contains(fixture.repo.path().to_string_lossy().as_ref()));
    assert!(!error_debug.contains(fixture.harness.path().to_string_lossy().as_ref()));
}

#[cfg(unix)]
#[test]
fn symlinked_managed_root_is_rejected() {
    use std::os::unix::fs::symlink;

    let repo = tempfile::tempdir().unwrap();
    let harness = tempfile::tempdir().unwrap();
    let external = tempfile::tempdir().unwrap();
    git(repo.path(), &["init", "-q"]);
    fs::write(repo.path().join("README.md"), "baseline\n").unwrap();
    git(
        repo.path(),
        &["config", "user.email", "tests@example.invalid"],
    );
    git(repo.path(), &["config", "user.name", "Worktree Tests"]);
    git(repo.path(), &["add", "README.md"]);
    git(repo.path(), &["commit", "-q", "-m", "initial"]);
    symlink(external.path(), harness.path().join("worktrees-v1")).unwrap();

    let error = WorktreeManager::new(repo.path(), harness.path(), WORKSPACE_ID).unwrap_err();
    assert_eq!(error.code(), "BOUNDARY_VIOLATION");
}

fn git(root: &Path, args: &[&str]) {
    let output = Command::new("git")
        .current_dir(root)
        .args(args)
        .output()
        .expect("git");
    assert!(
        output.status.success(),
        "git {:?} failed: {}",
        args,
        String::from_utf8_lossy(&output.stderr)
    );
}
