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

#[test]
fn a_failed_lifecycle_lock_still_releases_the_reservation_inside_the_lock() {
    // A1 C3 (steering 3): native::lock() Err must not free the slot outside the lock.
    let fixture = TestRepo::new();
    let slot = fixture.manager.reserve_slot().expect("reserve");
    let _ = SlotReservation::take_last_release_locked_for_test();
    WorktreeManager::fail_next_lifecycle_lock_for_test();
    fixture.manager.release_slot(slot);
    assert_eq!(
        SlotReservation::take_last_release_locked_for_test(),
        Some(true),
        "release_slot dropped the reservation outside the lifecycle lock"
    );
    assert_eq!(reservations::count(&fixture.manager.managed_root), 0);

    let slot = fixture.manager.reserve_slot().expect("reserve again");
    WorktreeManager::fail_next_lifecycle_lock_for_test();
    assert_eq!(
        fixture
            .manager
            .create_reserved(slot)
            .map(|_| ())
            .map_err(|e| e.code()),
        Err("LOCK_UNAVAILABLE")
    );
    assert_eq!(
        SlotReservation::take_last_release_locked_for_test(),
        Some(true),
        "create_reserved dropped the reservation outside the lifecycle lock"
    );
    assert_eq!(reservations::count(&fixture.manager.managed_root), 0);
    assert!(fixture.manager.list().unwrap().is_empty());
    for _ in 0..MAX_MANAGED_WORKTREES {
        fixture
            .manager
            .create_detached()
            .expect("all eight slots are free");
    }
}

#[test]
fn legacy_chat_root_worktrees_count_against_the_main_slots_and_are_never_moved() {
    // A1 C3 (steering 2, C1-b orphans): trees created before C1-b under a
    // session's `chat-v1/<key>` harness root stay where they are but are counted.
    let fixture = TestRepo::new();
    let key = "ab".repeat(32);
    let legacy_root = fixture.harness.path().join("chat-v1").join(&key);
    fs::create_dir_all(&legacy_root).expect("legacy root");
    let legacy =
        WorktreeManager::new(fixture.repo.path(), &legacy_root, WORKSPACE_ID).expect("legacy");
    let old: Vec<_> = (0..3)
        .map(|_| legacy.create_detached().expect("legacy tree"))
        .collect();
    // The native per-root listing is unchanged (no duplicates across managers).
    assert!(fixture.manager.list().unwrap().is_empty());
    for _ in 0..(MAX_MANAGED_WORKTREES - old.len()) {
        fixture.manager.create_detached().expect("main slot");
    }
    assert_eq!(
        fixture
            .manager
            .create_detached()
            .map(|_| ())
            .map_err(|e| e.code()),
        Err("CAPACITY"),
        "legacy chat-v1 worktrees were not counted against the 8 main slots"
    );
    assert_eq!(
        fixture
            .manager
            .reserve_slot()
            .map(|_| ())
            .map_err(|e| e.code()),
        Err("CAPACITY")
    );
    // Removing a legacy tree through the main root fails closed; nothing moves.
    assert_eq!(
        fixture
            .manager
            .remove_clean(&old[0].id)
            .map_err(|e| e.code()),
        Err("LEGACY_WORKTREE")
    );
    for item in &old {
        assert!(legacy_root
            .join("worktrees-v1")
            .join(WORKSPACE_ID)
            .join(&item.id)
            .join("README.md")
            .is_file());
    }
    let mut sorted = old.clone();
    sorted.sort_by(|a, b| a.id.cmp(&b.id));
    assert_eq!(legacy.list().unwrap(), sorted);
}

/// SPEC-A1 v4 §4.2 (C4): managed roots are private to the owner.
#[cfg(unix)]
#[test]
fn managed_roots_are_created_0700_and_group_writable_roots_are_rejected() {
    use std::os::unix::fs::PermissionsExt;
    let fixture = TestRepo::new();
    let worktrees = fixture.harness.path().join("worktrees-v1");
    let managed = worktrees.join(WORKSPACE_ID);
    let modes =
        [&worktrees, &managed].map(|path| fs::metadata(path).unwrap().permissions().mode() & 0o777);
    assert_eq!(modes, [0o700, 0o700]);
    // Reopening an existing owner-only root keeps working.
    assert_eq!(
        WorktreeManager::new(fixture.repo.path(), fixture.harness.path(), WORKSPACE_ID)
            .err()
            .map(|error| error.code),
        None
    );
    for (path, mode) in [(&managed, 0o770), (&managed, 0o702), (&worktrees, 0o720)] {
        fs::set_permissions(path, fs::Permissions::from_mode(mode)).unwrap();
        assert_eq!(
            WorktreeManager::new(fixture.repo.path(), fixture.harness.path(), WORKSPACE_ID)
                .err()
                .map(|error| error.code),
            Some("BOUNDARY_VIOLATION"),
            "{mode:o}"
        );
        fs::set_permissions(path, fs::Permissions::from_mode(0o700)).unwrap();
    }
}

/// A1 C4 (N1): only real `chat-v1/<64 hex>/worktrees-v1` roots count towards
/// the legacy scan limit; past it roots are skipped (warned), never CAPACITY.
#[test]
fn legacy_scan_counts_only_real_hex_roots_and_skips_past_the_limit() {
    let fixture = TestRepo::new();
    let chat = fixture.harness.path().join("chat-v1");
    let mut legacy_ids = Vec::new();
    for key in ["ab".repeat(32), "cd".repeat(32), "ef".repeat(32)] {
        let root = chat.join(&key);
        fs::create_dir_all(&root).unwrap();
        let manager = WorktreeManager::new(fixture.repo.path(), &root, WORKSPACE_ID).unwrap();
        legacy_ids.push(manager.create_detached().unwrap().id);
    }
    legacy_ids.sort();
    // 300 each of: hex-named files, non-hex dirs with worktrees-v1, hex dirs without it.
    for n in 0..300 {
        fs::write(chat.join(format!("{n:064x}")), "file").unwrap();
        fs::create_dir_all(chat.join(format!("not-hex-{n}")).join("worktrees-v1")).unwrap();
        fs::create_dir_all(chat.join(format!("{:064x}", n + 1000))).unwrap();
    }
    LEGACY_GIT_RUNS.with(|runs| runs.set(0));
    let scan = fixture.manager.legacy_scan().map(|(items, skipped)| {
        (
            items.into_iter().map(|item| item.id).collect::<Vec<_>>(),
            skipped,
        )
    });
    assert_eq!(scan.map_err(|e| e.code()), Ok((legacy_ids.clone(), 0)));
    assert_eq!(
        LEGACY_GIT_RUNS.with(|runs| runs.get()),
        1,
        "one git run per scan"
    );

    // 300 real hex roots sorting before the three trees push them past the limit.
    for n in 0..300 {
        fs::create_dir_all(chat.join(format!("{:064x}", n + 2000)).join("worktrees-v1")).unwrap();
    }
    LEGACY_GIT_RUNS.with(|runs| runs.set(0));
    let scan = fixture
        .manager
        .legacy_scan()
        .map(|(items, skipped)| (items.len(), skipped));
    assert_eq!(scan.map_err(|e| e.code()), Ok((0, 303 - 256)));
    assert!(LEGACY_GIT_RUNS.with(|runs| runs.get()) <= 1);
    assert_eq!(
        fixture
            .manager
            .list_with_legacy()
            .map(|items| items.len())
            .map_err(|e| e.code()),
        Ok(0)
    );
    let created = fixture.manager.create_detached().map(|item| item.legacy);
    assert_eq!(created.map_err(|e| e.code()), Ok(false));
    let slot = fixture.manager.reserve_slot().map(|_| ());
    assert_eq!(slot.map_err(|e| e.code()), Ok(()));
}

/// A1 C2-ad (NB3, SPEC-A1 v5 §1.7): one broken legacy registration (the
/// registry entry survives but its tree directory was deleted by hand, or its
/// HEAD is unreadable) is skipped with a warning; list/create/reserve proceed.
#[test]
fn a_broken_legacy_registration_is_skipped_and_never_fails_list_create_or_spawn() {
    let fixture = TestRepo::new();
    let chat = fixture.harness.path().join("chat-v1");
    let mut trees = Vec::new();
    for key in ["ab".repeat(32), "cd".repeat(32), "ef".repeat(32)] {
        let root = chat.join(&key);
        fs::create_dir_all(&root).unwrap();
        let manager = WorktreeManager::new(fixture.repo.path(), &root, WORKSPACE_ID).unwrap();
        let item = manager.create_detached().unwrap();
        trees.push((root.join("worktrees-v1").join(WORKSPACE_ID), item.id));
    }
    // Tree 0: directory removed by hand, registration left behind.
    fs::remove_dir_all(trees[0].0.join(&trees[0].1)).unwrap();
    // Tree 1: registry HEAD corrupted.
    let git_dir = fixture.repo.path().join(".git").join("worktrees");
    fs::write(git_dir.join(&trees[1].1).join("HEAD"), "not an oid\n").unwrap();
    let listed = fixture.manager.list_with_legacy();
    assert!(listed.is_ok(), "list failed: {listed:?}");
    let ids: Vec<String> = listed.unwrap().into_iter().map(|i| i.id).collect();
    assert_eq!(ids, vec![trees[2].1.clone()], "only the intact legacy tree");
    let created = fixture.manager.create_detached();
    assert!(created.is_ok(), "create failed: {created:?}");
    let reserved = fixture.manager.reserve_slot().map(|_| ());
    assert!(reserved.is_ok(), "reserve (spawn) failed: {reserved:?}");
    let (_, warnings) = fixture.manager.legacy_scan_warnings_for_test();
    assert_eq!(warnings, 2, "each skipped entry is one warning");
}

/// A1 C2-ad (NB4): a managed root the harness creates is chmod'ed to exactly
/// 0700, independent of the process umask (even one that strips owner bits).
/// Runs in a child process so the umask never leaks into parallel tests.
#[cfg(unix)]
#[test]
fn managed_roots_created_under_a_restrictive_umask_are_exactly_0700() {
    use std::os::unix::fs::PermissionsExt;
    if std::env::var_os("A1_NB4_CHILD").is_none() {
        let exe = std::env::current_exe().unwrap();
        let out = Command::new(exe)
            .args([
                "--exact",
                "harness::worktree::tests::managed_roots_created_under_a_restrictive_umask_are_exactly_0700",
                "--nocapture",
                "--test-threads=1",
            ])
            .env("A1_NB4_CHILD", "1")
            .output()
            .unwrap();
        let text = String::from_utf8_lossy(&out.stdout).into_owned()
            + &String::from_utf8_lossy(&out.stderr);
        assert!(out.status.success(), "child failed: {text}");
        assert!(
            text.contains("1 passed"),
            "child did not run the test: {text}"
        );
        return;
    }
    let fixture = TestRepo::new();
    let harness = tempfile::tempdir().unwrap();
    // 0o277 strips owner write: DirBuilder.mode(0o700) alone would give 0500.
    let previous = unsafe { libc::umask(0o277) };
    let made = WorktreeManager::new(fixture.repo.path(), harness.path(), WORKSPACE_ID).map(|_| ());
    unsafe { libc::umask(previous) };
    assert!(made.is_ok(), "{made:?}");
    let worktrees = harness.path().join("worktrees-v1");
    let managed = worktrees.join(WORKSPACE_ID);
    let modes =
        [&worktrees, &managed].map(|path| fs::metadata(path).unwrap().permissions().mode() & 0o777);
    assert_eq!(modes, [0o700, 0o700]);
}

// --- A1 C12: Windows longpaths + delete backoff helpers (Linux-runnable) ---

#[test]
fn c12_strip_windows_verbatim_matches_exec_contracts() {
    use super::super::worktree_git::{has_unrepresentable_windows_prefix, strip_windows_verbatim};

    // Drive / UNC: tip-byte-identical to exec::windows_command_path.
    for (input, expected) in [
        (r"\\?\C:\workspace\managed\id", r"C:\workspace\managed\id"),
        (r"\\?\z:\中文 workspace\x", r"z:\中文 workspace\x"),
        (r"\\?\UNC\server\share\repo", r"\\server\share\repo"),
        (r"\\?\uNc\server\share\repo", r"\\server\share\repo"),
        (
            r"\\?\UNC\server\share\中文 [workspace]\run.ps1",
            r"\\server\share\中文 [workspace]\run.ps1",
        ),
    ] {
        assert_eq!(strip_windows_verbatim(input), expected, "input={input}");
        assert!(
            !has_unrepresentable_windows_prefix(&strip_windows_verbatim(input)),
            "stripped must be representable: {input}"
        );
    }

    // Ordinary paths unchanged.
    for path in [
        r"\\server\share\repo",
        r"C:\workspace",
        "C:/workspace",
        "scripts/run.cmd",
        "",
    ] {
        assert_eq!(strip_windows_verbatim(path), path);
    }

    // Device / volume / relative-after-prefix: leave unchanged → unrepresentable.
    for path in [
        r"\\?\Volume{12345678-1234-1234-1234-123456789abc}\repo",
        r"\\?\GLOBALROOT\Device\HarddiskVolume1\repo",
        r"\\.\pipe\fixture",
        r"\\?\C:relative",
        r"\\?\中文路径",
        r"\\?\a中文",
        r"\\?\",
        r"\\?\C:",
    ] {
        assert_eq!(strip_windows_verbatim(path), path, "must leave {path}");
        assert!(
            has_unrepresentable_windows_prefix(&strip_windows_verbatim(path)),
            "must reject {path}"
        );
    }
}

#[test]
fn c12_add_rejects_unrepresentable_windows_prefix() {
    use super::super::worktree_git::run_git;
    use std::ffi::OsString;

    let fixture = TestRepo::new();
    let managed = fixture.manager.managed_root.clone();
    // Synthesize an add whose target still carries \\?\Volume… after strip.
    let bogus = format!(
        r"\\?\Volume{{00000000-0000-0000-0000-000000000000}}\{}",
        managed.join("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa").display()
    );
    let args = vec![
        OsString::from("worktree"),
        OsString::from("add"),
        OsString::from("--detach"),
        OsString::from(&bogus),
        OsString::from("HEAD"),
    ];
    match run_git(
        fixture.repo.path(),
        &args,
        fixture.repo.path(),
        Some(&managed),
    ) {
        Err(err) => assert_eq!(err.code(), "BOUNDARY_VIOLATION"),
        Ok(_) => panic!("expected BOUNDARY_VIOLATION for unrepresentable prefix"),
    }
}

#[test]
fn c12_remove_fail_at_leaves_marker_and_list_stays_ok() {
    use super::super::worktree_git::{
        has_removing_marker, set_delete_fail_at_for_test, REMOVING_MARKER,
    };

    let fixture = TestRepo::new();
    let item = fixture.manager.create_detached().expect("create");
    let metadata = fixture.repo.path().join(".git/worktrees").join(&item.id);

    // Fail after marker is written, while deleting the target (step 0).
    set_delete_fail_at_for_test(Some(0));
    let err = fixture.manager.remove_clean(&item.id).unwrap_err();
    set_delete_fail_at_for_test(None);
    assert_eq!(err.code(), "IO_FAILED");
    assert!(
        has_removing_marker(&metadata),
        "marker must survive a mid-delete failure"
    );
    assert!(
        metadata.join(REMOVING_MARKER).is_file(),
        "marker file present"
    );

    // list() must stay Ok. Step 0 fails before anything is deleted, so the
    // registration is still valid: the tree stays listed and holds exactly one
    // slot (count_removing_under must not double-count a listed entry).
    let listed = fixture.manager.list().expect("list ok with marker");
    assert!(
        listed.iter().any(|w| w.id == item.id),
        "valid registration with marker stays listed"
    );
    assert_eq!(listed.len(), 1);
    let (used, _) = fixture.manager.slots_in_use_for_test();
    assert_eq!(used, 1, "in-progress delete holds exactly one slot");

    // Resume succeeds once the fail hook is cleared (owner-record entry point).
    fixture
        .manager
        .remove_clean_owned(&item.id)
        .expect("resume after fail-at");
    assert!(!metadata.exists(), "metadata dir gone after resume");
    assert!(fixture.manager.list().unwrap().is_empty());
}

#[test]
fn c12_resume_refuses_when_file_modified_after_marker() {
    use super::super::worktree_git::{has_removing_marker, set_delete_fail_at_for_test};

    let fixture = TestRepo::new();
    let item = fixture.manager.create_detached().expect("create");
    let target = fixture.manager.managed_root.join(&item.id);
    let metadata = fixture.repo.path().join(".git/worktrees").join(&item.id);

    set_delete_fail_at_for_test(Some(0));
    let _ = fixture.manager.remove_clean(&item.id);
    set_delete_fail_at_for_test(None);
    assert!(has_removing_marker(&metadata));

    // After the marker exists, write a new file → deletion-tolerant clean fails.
    fs::write(target.join("sneaky.txt"), "after-marker\n").unwrap();
    assert_eq!(
        fixture
            .manager
            .remove_clean_owned(&item.id)
            .unwrap_err()
            .code(),
        "DIRTY"
    );
    assert!(
        has_removing_marker(&metadata),
        "marker kept on DIRTY resume"
    );

    // Clean up the sneaky file (delete it) so only WT_DELETED-like state remains,
    // then resume by removing the untracked file and retrying.
    fs::remove_file(target.join("sneaky.txt")).unwrap();
    fixture
        .manager
        .remove_clean_owned(&item.id)
        .expect("resume after reverting post-marker write");
}

#[test]
fn c12_resume_allows_partial_target_deletion() {
    use super::super::worktree_git::{has_removing_marker, set_delete_fail_at_for_test};

    let fixture = TestRepo::new();
    let item = fixture.manager.create_detached().expect("create");
    let target = fixture.manager.managed_root.join(&item.id);
    let metadata = fixture.repo.path().join(".git/worktrees").join(&item.id);

    set_delete_fail_at_for_test(Some(0));
    let _ = fixture.manager.remove_clean(&item.id);
    set_delete_fail_at_for_test(None);
    assert!(has_removing_marker(&metadata));

    // Simulate a partial delete: remove a tracked file from the worktree.
    // That surfaces as WT_DELETED, which M9 tolerates.
    fs::remove_file(target.join("README.md")).expect("tracked README.md removed");
    assert!(!target.join("README.md").exists());
    // Fresh porcelain (no owner record) sees the deletion and refuses.
    assert_eq!(
        fixture.manager.remove_clean(&item.id).unwrap_err().code(),
        "DIRTY"
    );
    assert!(has_removing_marker(&metadata));
    fixture
        .manager
        .remove_clean_owned(&item.id)
        .expect("resume with only WT_DELETED remaining");
    assert!(!metadata.exists());
    assert!(!target.exists());
}

// ---- A1 C12b nit 0: Grok S1 M11 probe (fail at steps 1..=5), merged ----
#[test]
fn c12b_fail_at_steps_1_to_5_list_ok_slot_counted_resume_ok() {
    use super::super::worktree_git::{has_removing_marker, set_delete_fail_at_for_test};
    for step in 1..=5usize {
        let fixture = TestRepo::new();
        let item = fixture.manager.create_detached().expect("create");
        let target = fixture.manager.managed_root.join(&item.id);
        let metadata = fixture.repo.path().join(".git/worktrees").join(&item.id);
        set_delete_fail_at_for_test(Some(step));
        let err = fixture.manager.remove_clean(&item.id).unwrap_err();
        set_delete_fail_at_for_test(None);
        assert_eq!(err.code(), "IO_FAILED", "step={step}");
        assert!(!target.exists(), "target gone at step={step}");
        assert!(has_removing_marker(&metadata), "marker kept step={step}");
        let listed = fixture.manager.list().expect("list ok");
        let listed_has = listed.iter().any(|w| w.id == item.id);
        let (used, _) = fixture.manager.slots_in_use_for_test();
        assert!(!listed_has, "broken registration skipped step={step}");
        assert_eq!(used, 1, "slot still counted step={step}");
        fixture
            .manager
            .remove_clean_owned(&item.id)
            .expect("resume");
        assert!(!metadata.exists(), "metadata gone step={step}");
        assert_eq!(
            fixture.manager.slots_in_use_for_test().0,
            0,
            "slot freed step={step}"
        );
    }
}

#[test]
fn c12b_unmarked_broken_registration_still_errs() {
    let fixture = TestRepo::new();
    let item = fixture.manager.create_detached().expect("create");
    let target = fixture.manager.managed_root.join(&item.id);
    fs::remove_file(target.join(".git")).unwrap();
    assert!(
        fixture.manager.list().is_err(),
        "unmarked failure must stay Err"
    );
}

/// A1 C12b nit 3 (M9): `worktree_remove` (no owner record) never resumes from a
/// marker. An orphan marker whose registration is broken is left alone; the
/// pre-marker absence rules apply and nothing under `.git/worktrees/<id>` moves.
#[test]
fn c12b_marker_without_owner_record_does_not_resume() {
    use super::super::worktree_git::{
        has_removing_marker, set_delete_fail_at_for_test, REMOVING_MARKER,
    };
    let fixture = TestRepo::new();
    let item = fixture.manager.create_detached().expect("create");
    let target = fixture.manager.managed_root.join(&item.id);
    let metadata = fixture.repo.path().join(".git/worktrees").join(&item.id);
    // Fail after the target is gone and gitdir removal fails (step 1):
    // registration is now broken, marker present, list() skips it.
    set_delete_fail_at_for_test(Some(1));
    assert_eq!(
        fixture.manager.remove_clean(&item.id).unwrap_err().code(),
        "IO_FAILED"
    );
    set_delete_fail_at_for_test(None);
    assert!(!target.exists());
    assert!(has_removing_marker(&metadata));
    let before: Vec<_> = {
        let mut v: Vec<_> = fs::read_dir(&metadata)
            .unwrap()
            .map(|e| e.unwrap().file_name())
            .collect();
        v.sort();
        v
    };
    assert!(before.iter().any(|n| n == REMOVING_MARKER));
    // Non-owner remove: absence rule (tree gone) → Ok, but no resume happens.
    fixture
        .manager
        .remove_clean(&item.id)
        .expect("absent tree stays retry-safe");
    let after: Vec<_> = {
        let mut v: Vec<_> = fs::read_dir(&metadata)
            .unwrap()
            .map(|e| e.unwrap().file_name())
            .collect();
        v.sort();
        v
    };
    assert_eq!(before, after, "orphan marker entry untouched");
    assert!(has_removing_marker(&metadata));
    assert_eq!(
        fixture.manager.slots_in_use_for_test().0,
        1,
        "still counted"
    );
    // A target re-appearing under the id is a boundary refusal, not a resume.
    fs::create_dir(&target).unwrap();
    assert_eq!(
        fixture.manager.remove_clean(&item.id).unwrap_err().code(),
        "BOUNDARY_VIOLATION"
    );
    fs::remove_dir(&target).unwrap();
    assert!(has_removing_marker(&metadata));
    // The owner entry point does resume.
    fixture
        .manager
        .remove_clean_owned(&item.id)
        .expect("owner resume");
    assert!(!metadata.exists());
    assert_eq!(fixture.manager.slots_in_use_for_test().0, 0);
}

/// A1 C12b nit 5: resume clean check fails closed when the origin snapshot
/// (`managed-origin-head`) cannot be read.
#[test]
fn c12b_resume_rejects_unreadable_origin_snapshot() {
    use super::super::worktree_git::{has_removing_marker, set_delete_fail_at_for_test};
    let fixture = TestRepo::new();
    let item = fixture.manager.create_detached().expect("create");
    let target = fixture.manager.managed_root.join(&item.id);
    let metadata = fixture.repo.path().join(".git/worktrees").join(&item.id);
    set_delete_fail_at_for_test(Some(0));
    let _ = fixture.manager.remove_clean(&item.id).unwrap_err();
    set_delete_fail_at_for_test(None);
    assert!(has_removing_marker(&metadata));
    assert!(target.exists());
    let origin = metadata.join("managed-origin-head");
    let saved = fs::read(&origin).expect("origin snapshot present");
    fs::remove_file(&origin).unwrap();
    assert_eq!(
        fixture
            .manager
            .remove_clean_owned(&item.id)
            .unwrap_err()
            .code(),
        "DIRTY",
        "missing origin snapshot must fail closed"
    );
    assert!(target.exists() && has_removing_marker(&metadata));
    // Restoring the snapshot lets the resume finish.
    fs::write(&origin, saved).unwrap();
    fixture
        .manager
        .remove_clean_owned(&item.id)
        .expect("resume with origin restored");
    assert!(!metadata.exists());
}

/// A1 C12b nit 4: the metadata dir comes from the same libgit2-side `Source`
/// as worktree_git (`source.git/worktrees/<id>`). A gitfile `.git` source is
/// refused by `open_source` (NOT_REPOSITORY), so remove fails closed before any
/// marker probe instead of guessing `<root>/.git/worktrees`.
#[test]
fn c12b_metadata_dir_follows_source_and_gitfile_fails_closed() {
    use super::super::worktree_git::managed_metadata_dir;
    let fixture = TestRepo::new();
    let item = fixture.manager.create_detached().expect("create");
    let canonical = fixture.repo.path().canonicalize().unwrap();
    let derived = managed_metadata_dir(&canonical, &item.id).expect("derived");
    assert_eq!(
        derived,
        canonical.join(".git").join("worktrees").join(&item.id)
    );
    assert!(derived.is_dir());

    // Separate-git-dir repo: `.git` is a gitfile pointing elsewhere.
    let work = tempfile::tempdir().unwrap();
    let store = tempfile::tempdir().unwrap();
    let gitdir = store.path().join("repo.git");
    git(
        work.path(),
        &["init", "-q", "--separate-git-dir", gitdir.to_str().unwrap()],
    );
    assert!(work.path().join(".git").is_file(), "gitfile .git");
    let err = managed_metadata_dir(work.path(), "0123456789abcdef0123456789abcdef").unwrap_err();
    assert_eq!(err.code(), "NOT_REPOSITORY");
}
