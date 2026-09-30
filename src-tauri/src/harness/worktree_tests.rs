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
    fixture
        .manager
        .remove_clean("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        .expect("absent valid ID is safe to retry");

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
        // Git 2.55 may detach maintenance while its objects/maintenance.lock
        // is still present. Fixture setup must leave no concurrent metadata
        // writer before the production boundary scanner inspects this repo.
        .args(["-c", "maintenance.auto=false"])
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

#[cfg(windows)]
#[test]
fn git_path_argument_removes_only_windows_verbatim_prefix() {
    use std::path::Path;

    let drive = Path::new(r"\\?\C:\workspace\managed\id");
    assert_eq!(
        super::super::worktree_git::git_path_arg(drive),
        std::ffi::OsString::from(r"C:\workspace\managed\id")
    );

    let unc = Path::new(r"\\?\UNC\server\share\managed\id");
    assert_eq!(
        super::super::worktree_git::git_path_arg(unc),
        std::ffi::OsString::from(r"\\server\share\managed\id")
    );

    let normal = Path::new(r"C:\workspace\managed\id");
    assert_eq!(
        super::super::worktree_git::git_path_arg(normal),
        normal.as_os_str()
    );
}

#[test]
fn repeated_removal_succeeds_and_orphan_paths_are_preserved() {
    let fixture = TestRepo::new();
    let item = fixture.manager.create_detached().unwrap();
    fixture.manager.remove_clean(&item.id).unwrap();
    fixture
        .manager
        .remove_clean(&item.id)
        .expect("idempotent remove");
    let orphan = fixture.manager.managed_root.join(&item.id);
    fs::create_dir(&orphan).unwrap();
    fs::write(orphan.join("keep.txt"), "preserve").unwrap();
    assert_eq!(
        fixture.manager.remove_clean(&item.id).unwrap_err().code(),
        "BOUNDARY_VIOLATION"
    );
    assert_eq!(
        fs::read_to_string(orphan.join("keep.txt")).unwrap(),
        "preserve"
    );
}

#[test]
fn ignored_local_content_prevents_removal() {
    let fixture = TestRepo::new();
    fs::write(fixture.repo.path().join(".gitignore"), "private.cache\n").unwrap();
    git(fixture.repo.path(), &["add", ".gitignore"]);
    git(fixture.repo.path(), &["commit", "-q", "-m", "ignore cache"]);
    let item = fixture.manager.create_detached().unwrap();
    let path = fixture.manager.managed_root.join(&item.id);
    fs::write(path.join("private.cache"), "local content").unwrap();
    assert_eq!(
        fixture.manager.remove_clean(&item.id).unwrap_err().code(),
        "DIRTY"
    );
    assert_eq!(
        fs::read_to_string(path.join("private.cache")).unwrap(),
        "local content"
    );
}

#[test]
fn reconstructed_manager_discovers_existing_worktree() {
    let fixture = TestRepo::new();
    let item = fixture.manager.create_detached().unwrap();
    let restored =
        WorktreeManager::new(fixture.repo.path(), fixture.harness.path(), WORKSPACE_ID).unwrap();
    assert_eq!(restored.list().unwrap(), vec![item.clone()]);
    restored.remove_clean(&item.id).unwrap();
    assert!(fixture.manager.list().unwrap().is_empty());
}

#[cfg(unix)]
#[test]
fn replaced_managed_root_is_refused_before_any_git_mutation() {
    use std::os::unix::fs::symlink;
    let fixture = TestRepo::new();
    let external = tempfile::tempdir().unwrap();
    fs::remove_dir(&fixture.manager.managed_root).unwrap();
    symlink(external.path(), &fixture.manager.managed_root).unwrap();
    assert_eq!(
        fixture.manager.list().unwrap_err().code(),
        "BOUNDARY_VIOLATION"
    );
    assert_eq!(
        fixture.manager.create_detached().unwrap_err().code(),
        "BOUNDARY_VIOLATION"
    );
    assert_eq!(
        fixture
            .manager
            .remove_clean("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
            .unwrap_err()
            .code(),
        "BOUNDARY_VIOLATION"
    );
    assert_eq!(fs::read_dir(external.path()).unwrap().count(), 0);
}

#[cfg(unix)]
#[test]
fn replaced_parent_root_is_refused_even_when_target_resolves_inside() {
    use std::os::unix::fs::symlink;
    let fixture = TestRepo::new();
    let original = fixture.harness.path().join("worktrees-v1");
    let renamed = fixture.harness.path().join("renamed-worktrees");
    fs::rename(&original, &renamed).unwrap();
    symlink(&renamed, &original).unwrap();
    assert_eq!(
        fixture.manager.create_detached().unwrap_err().code(),
        "BOUNDARY_VIOLATION"
    );
    assert_eq!(fs::read_dir(renamed.join(WORKSPACE_ID)).unwrap().count(), 0);
}

#[test]
fn lifecycle_supports_paths_with_spaces() {
    let repo = tempfile::Builder::new()
        .prefix("repo with spaces ")
        .tempdir()
        .unwrap();
    let harness = tempfile::Builder::new()
        .prefix("state with spaces ")
        .tempdir()
        .unwrap();
    git(repo.path(), &["init", "-q"]);
    git(
        repo.path(),
        &["config", "user.email", "tests@example.invalid"],
    );
    git(repo.path(), &["config", "user.name", "Worktree Tests"]);
    fs::write(repo.path().join("file with spaces.txt"), "baseline").unwrap();
    git(repo.path(), &["add", "."]);
    git(repo.path(), &["commit", "-q", "-m", "initial"]);
    let manager = WorktreeManager::new(repo.path(), harness.path(), WORKSPACE_ID).unwrap();
    let item = manager.create_detached().unwrap();
    assert_eq!(manager.list().unwrap(), vec![item.clone()]);
    manager.remove_clean(&item.id).unwrap();
    manager.remove_clean(&item.id).unwrap();
}

#[cfg(unix)]
#[test]
fn replaced_worktree_link_preserves_external_content() {
    use std::os::unix::fs::symlink;
    let fixture = TestRepo::new();
    let item = fixture.manager.create_detached().unwrap();
    let path = fixture.manager.managed_root.join(&item.id);
    let external = tempfile::tempdir().unwrap();
    fs::write(external.path().join("keep.txt"), "external").unwrap();
    let relocated = fixture.harness.path().join("relocated");
    fs::rename(&path, &relocated).unwrap();
    symlink(external.path(), &path).unwrap();
    assert_eq!(
        fixture.manager.remove_clean(&item.id).unwrap_err().code(),
        "BOUNDARY_VIOLATION"
    );
    assert_eq!(
        fs::read_to_string(external.path().join("keep.txt")).unwrap(),
        "external"
    );
    assert!(relocated.join("README.md").is_file());
}

#[cfg(windows)]
#[test]
fn replaced_managed_junction_is_refused_before_creation() {
    let fixture = TestRepo::new();
    let external = tempfile::tempdir().unwrap();
    fs::remove_dir(&fixture.manager.managed_root).unwrap();
    let result = Command::new("cmd")
        .args(["/C", "mklink", "/J"])
        .arg(&fixture.manager.managed_root)
        .arg(external.path())
        .output()
        .expect("create junction");
    assert!(result.status.success(), "junction creation failed");
    assert_eq!(
        fixture.manager.create_detached().unwrap_err().code(),
        "BOUNDARY_VIOLATION"
    );
    assert_eq!(fs::read_dir(external.path()).unwrap().count(), 0);
}

#[path = "worktree_security_tests.rs"]
mod security;

#[cfg(windows)]
#[path = "worktree_windows_tests.rs"]
mod windows;

#[test]
fn fixture_git_commands_do_not_start_background_maintenance() {
    const CHILD: &str = "WORKTREE_FIXTURE_MAINTENANCE_CHILD";
    if std::env::var_os(CHILD).is_some() {
        let repo = tempfile::tempdir().unwrap();
        git(repo.path(), &["init", "-q"]);
        git(repo.path(), &["config", "user.name", "Fixture"]);
        git(
            repo.path(),
            &["config", "user.email", "fixture@example.invalid"],
        );
        // Even an ambient repository preference cannot start a concurrent
        // metadata writer after the fixture's command has returned.
        git(repo.path(), &["config", "maintenance.auto", "true"]);
        fs::write(repo.path().join("fixture.txt"), "fixture").unwrap();
        git(repo.path(), &["add", "."]);
        git(repo.path(), &["commit", "-qm", "fixture"]);
        return;
    }
    let root = tempfile::tempdir().unwrap();
    let trace = root.path().join("git-events.jsonl");
    let module = module_path!().split_once("::").unwrap().1;
    let output = Command::new(std::env::current_exe().unwrap())
        .args([
            "--exact",
            &format!("{module}::fixture_git_commands_do_not_start_background_maintenance"),
            "--nocapture",
        ])
        .env(CHILD, "1")
        .env("GIT_TRACE2_EVENT", &trace)
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    assert!(String::from_utf8_lossy(&output.stdout).contains("1 passed"));
    let events: Vec<serde_json::Value> = fs::read_to_string(trace)
        .unwrap()
        .lines()
        .map(|line| serde_json::from_str(line).unwrap())
        .collect();
    assert!(events
        .iter()
        .any(|event| event["event"] == "cmd_name" && event["name"] == "commit"));
    assert!(
        !events.iter().any(|event| {
            event["event"] == "child_start"
                && event["argv"]
                    .as_array()
                    .is_some_and(|args| args.iter().any(|arg| arg == "maintenance"))
        }),
        "fixture Git spawned maintenance after writing repository metadata"
    );
}
