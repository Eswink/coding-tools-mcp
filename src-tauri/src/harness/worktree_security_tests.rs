use super::*;

#[test]
fn detached_registration_is_recognized_by_trusted_git() {
    let fixture = TestRepo::new();
    let item = fixture.manager.create_detached().unwrap();
    let result = Command::new("git")
        .current_dir(fixture.repo.path())
        .args(["worktree", "list", "--porcelain"])
        .output()
        .unwrap();
    assert!(result.status.success());
    let text = String::from_utf8(result.stdout).unwrap();
    assert!(text.contains(&item.id));
    assert!(text.contains("detached"));
    let result = Command::new("git")
        .current_dir(fixture.manager.managed_root.join(&item.id))
        .args(["status", "--porcelain"])
        .output()
        .unwrap();
    assert!(result.status.success());
    assert!(result.stdout.is_empty(), "{:?}", result);
    fixture.manager.remove_clean(&item.id).unwrap();
}

#[test]
fn repository_configuration_and_helpers_are_never_opened_or_executed() {
    let fixture = TestRepo::new();
    fs::write(
        fixture.repo.path().join(".gitattributes"),
        "* filter=escape\n",
    )
    .unwrap();
    git(fixture.repo.path(), &["add", ".gitattributes"]);
    git(fixture.repo.path(), &["commit", "-qm", "attributes"]);
    let outside = tempfile::tempdir().unwrap();
    let marker = outside.path().join("MUST_NOT_EXIST");
    let script = fixture.repo.path().join(".git/hooks/post-checkout");
    fs::write(
        &script,
        format!("#!/bin/sh\nprintf escaped > '{}'\n", marker.display()),
    )
    .unwrap();
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(&script, fs::Permissions::from_mode(0o755)).unwrap();
    }
    fs::write(fixture.repo.path().join(".git/config"), format!(
        "[core]\nworktree = {}\nfsmonitor = {}\n[filter \"escape\"]\nsmudge = {}\nclean = {}\nprocess = {}\nrequired = true\n[include]\npath = {}\nTHIS IS INTENTIONALLY INVALID CONFIG\n",
        outside.path().display(), script.display(), script.display(), script.display(), script.display(), outside.path().join("private-config").display()
    )).unwrap();
    let item = fixture.manager.create_detached().unwrap();
    assert!(!marker.exists());
    fixture.manager.remove_clean(&item.id).unwrap();
    assert_eq!(fs::read_dir(outside.path()).unwrap().count(), 0);
}

#[test]
fn object_alternates_are_rejected_before_reading_external_objects() {
    let fixture = TestRepo::new();
    let external = tempfile::tempdir().unwrap();
    fs::create_dir_all(fixture.repo.path().join(".git/objects/info")).unwrap();
    fs::write(
        fixture.repo.path().join(".git/objects/info/alternates"),
        external.path().to_string_lossy().as_bytes(),
    )
    .unwrap();
    assert_eq!(
        fixture.manager.create_detached().unwrap_err().code(),
        "BOUNDARY_VIOLATION"
    );
    assert_eq!(fs::read_dir(external.path()).unwrap().count(), 0);
}

#[test]
fn hardlinked_head_metadata_is_rejected() {
    let fixture = TestRepo::new();
    let external = tempfile::tempdir().unwrap();
    let head = fixture.repo.path().join(".git/HEAD");
    let saved = fs::read(&head).unwrap();
    let external_head = external.path().join("HEAD");
    fs::write(&external_head, &saved).unwrap();
    fs::remove_file(&head).unwrap();
    fs::hard_link(&external_head, &head).unwrap();
    assert_eq!(
        fixture.manager.create_detached().unwrap_err().code(),
        "BOUNDARY_VIOLATION"
    );
    assert_eq!(fs::read(external_head).unwrap(), saved);
}

#[test]
fn changed_real_managed_root_identity_is_rejected() {
    let fixture = TestRepo::new();
    fs::rename(
        &fixture.manager.managed_root,
        fixture.harness.path().join("original-root"),
    )
    .unwrap();
    fs::create_dir(&fixture.manager.managed_root).unwrap();
    assert_eq!(
        fixture.manager.create_detached().unwrap_err().code(),
        "BOUNDARY_VIOLATION"
    );
}

#[cfg(unix)]
#[test]
fn symlinked_object_storage_is_rejected() {
    use std::os::unix::fs::symlink;
    let fixture = TestRepo::new();
    let objects = fixture.repo.path().join(".git/objects");
    let moved = fixture.harness.path().join("external-objects");
    fs::rename(&objects, &moved).unwrap();
    symlink(&moved, &objects).unwrap();
    assert_eq!(
        fixture.manager.create_detached().unwrap_err().code(),
        "BOUNDARY_VIOLATION"
    );
}

#[test]
fn git_environment_overrides_do_not_change_engine_authority() {
    let fixture = TestRepo::new();
    let module = module_path!().split_once("::").unwrap().1;
    let result = Command::new(std::env::current_exe().unwrap())
        .args([
            "--exact",
            &format!("{module}::environment_child"),
            "--nocapture",
        ])
        .env("WORKTREE_ENGINE_TEST_ROOT", fixture.repo.path())
        .env("WORKTREE_ENGINE_TEST_STATE", fixture.harness.path())
        .env("GIT_DIR", "/forbidden-git-directory")
        .env("GIT_WORK_TREE", "/forbidden-worktree")
        .env("GIT_COMMON_DIR", "/forbidden-common")
        .env("GIT_OBJECT_DIRECTORY", "/forbidden-objects")
        .env("GIT_ALTERNATE_OBJECT_DIRECTORIES", "/forbidden-alternates")
        .env("GIT_INDEX_FILE", "/forbidden-index")
        .env("GIT_CONFIG_GLOBAL", "/forbidden-config")
        .env("GIT_CONFIG_COUNT", "1")
        .env("GIT_CONFIG_KEY_0", "core.worktree")
        .env("GIT_CONFIG_VALUE_0", "/forbidden-worktree")
        .env("PATH", "/no-executables")
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stdout)
    );
    assert!(String::from_utf8_lossy(&result.stdout).contains("1 passed"));
}

#[test]
fn environment_child() {
    let Some(root) = std::env::var_os("WORKTREE_ENGINE_TEST_ROOT") else {
        return;
    };
    let state = std::env::var_os("WORKTREE_ENGINE_TEST_STATE").unwrap();
    let manager = WorktreeManager::new(Path::new(&root), Path::new(&state), WORKSPACE_ID).unwrap();
    let item = manager.create_detached().unwrap();
    manager.remove_clean(&item.id).unwrap();
}

#[test]
fn oversized_blob_is_refused_before_checkout() {
    let fixture = TestRepo::new();
    fs::write(
        fixture.repo.path().join("large.bin"),
        vec![b'x'; 16 * 1024 * 1024 + 1],
    )
    .unwrap();
    git(fixture.repo.path(), &["add", "large.bin"]);
    git(fixture.repo.path(), &["commit", "-qm", "large fixture"]);
    assert_eq!(
        fixture.manager.create_detached().unwrap_err().code(),
        "OUTPUT_LIMIT"
    );
    assert_eq!(
        fs::read_dir(&fixture.manager.managed_root).unwrap().count(),
        0
    );
}

#[test]
fn clean_detached_commits_are_not_silently_discarded() {
    let fixture = TestRepo::new();
    let item = fixture.manager.create_detached().unwrap();
    let path = fixture.manager.managed_root.join(&item.id);
    fs::write(path.join("README.md"), "new commit\n").unwrap();
    git(&path, &["add", "README.md"]);
    git(&path, &["commit", "-qm", "detached work"]);
    assert_eq!(
        fixture.manager.remove_clean(&item.id).unwrap_err().code(),
        "DIRTY"
    );
    assert_eq!(
        fs::read_to_string(path.join("README.md")).unwrap(),
        "new commit\n"
    );
}

#[test]
fn snapshot_target_revalidates_identity_without_claiming_quiescence() {
    let fixture = TestRepo::new();
    let item = fixture.manager.create_detached().unwrap();
    let target = fixture.manager.snapshot_target(&item.id).unwrap();
    target.verify().unwrap();
    assert_eq!(target.worktree_id, item.id);
    fixture.manager.remove_clean(&item.id).unwrap();
    assert!(target.verify().is_err());
}

#[test]
fn native_profile_pin_is_persistent_and_remote_style_removal_is_refused() {
    let fixture = TestRepo::new();
    let item = fixture.manager.create_detached().unwrap();
    assert_eq!(fixture.manager.native_profile(&item.id).unwrap(), None);
    fixture
        .manager
        .pin_native_profile(&item.id, "native-profile-1")
        .unwrap();
    fixture
        .manager
        .pin_native_profile(&item.id, "native-profile-1")
        .unwrap();
    assert_eq!(
        fixture
            .manager
            .pin_native_profile(&item.id, "native-profile-2")
            .unwrap_err()
            .code(),
        "WORKTREE_PINNED"
    );
    let restored =
        WorktreeManager::new(fixture.repo.path(), fixture.harness.path(), WORKSPACE_ID).unwrap();
    let target = restored.snapshot_target(&item.id).unwrap();
    restored
        .with_lifecycle(|| {
            target.verify()?;
            assert_eq!(
                restored.native_profile(&item.id)?,
                Some("native-profile-1".into())
            );
            Ok(())
        })
        .unwrap();
    assert_eq!(
        restored.remove_clean(&item.id).unwrap_err().code(),
        "WORKTREE_PINNED"
    );
    assert!(target.root.join("README.md").exists());
}

#[test]
fn empty_git_object_directory_is_not_repository_discovery() {
    let workspace = tempfile::tempdir().unwrap();
    let harness = tempfile::tempdir().unwrap();
    fs::create_dir_all(workspace.path().join(".git/objects")).unwrap();
    let error = WorktreeManager::new(workspace.path(), harness.path(), WORKSPACE_ID).unwrap_err();
    assert_eq!(error.code(), "NOT_REPOSITORY");
    assert!(!harness.path().join("worktrees-v1").exists());
}

#[test]
fn explicitly_locked_git_worktree_is_not_removed() {
    let fixture = TestRepo::new();
    let item = fixture.manager.create_detached().unwrap();
    let path = fixture.manager.managed_root.join(&item.id);
    let argument = git_path_arg(&path);
    git(
        fixture.repo.path(),
        &["worktree", "lock", argument.to_str().unwrap()],
    );
    assert_eq!(
        fixture.manager.remove_clean(&item.id).unwrap_err().code(),
        "LOCKED"
    );
    assert!(path.join("README.md").exists());
}

#[test]
fn source_git_metadata_cannot_clear_or_forge_native_registration() {
    let fixture = TestRepo::new();
    let item = fixture.manager.create_detached().unwrap();
    fixture
        .manager
        .pin_native_profile(&item.id, "approved-native-profile")
        .unwrap();
    let untrusted_marker = fixture
        .repo
        .path()
        .join(".git/worktrees")
        .join(&item.id)
        .join("native-profile-pin");
    let _ = fs::remove_file(&untrusted_marker);
    fs::write(&untrusted_marker, "forged-profile\n").unwrap();
    assert_eq!(
        fixture.manager.native_profile(&item.id).unwrap(),
        Some("approved-native-profile".into())
    );
    fs::remove_file(&untrusted_marker).unwrap();
    assert_eq!(
        fixture.manager.remove_clean(&item.id).unwrap_err().code(),
        "WORKTREE_PINNED"
    );
    assert!(fixture
        .manager
        .managed_root
        .join(&item.id)
        .join("README.md")
        .exists());
}
