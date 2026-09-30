use super::*;
use std::{fs, path::PathBuf};
struct Target {
    root: PathBuf,
    identity: String,
    workspace: String,
    worktree: String,
}
impl TargetAuthority for Target {
    fn root(&self) -> &Path {
        &self.root
    }
    fn workspace_id(&self) -> &str {
        &self.workspace
    }
    fn worktree_id(&self) -> &str {
        &self.worktree
    }
    fn head(&self) -> &str {
        "0123456789012345678901234567890123456789"
    }
    fn verify(&self) -> Result<()> {
        if Dir::open(&self.root)?.identity()? != self.identity {
            return Err(SnapshotError::Changed);
        };
        Ok(())
    }
}
#[cfg(target_os = "linux")]
fn fixture() -> (tempfile::TempDir, Target, SnapshotStore) {
    let temp = tempfile::tempdir().unwrap();
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(temp.path(), fs::Permissions::from_mode(0o700)).unwrap();
    }
    let root = temp.path().join("managed");
    fs::create_dir(&root).unwrap();
    fs::write(root.join(".git"), b"gitdir: host-owned-control").unwrap();
    let target = Target {
        identity: Dir::open(&root).unwrap().identity().unwrap(),
        root,
        workspace: "a".repeat(32),
        worktree: "b".repeat(32),
    };
    let store = SnapshotStore::create(temp.path(), "snapshots").unwrap();
    (temp, target, store)
}
#[cfg(target_os = "linux")]
#[test]
fn captures_reopens_binary_hash_size_and_permissions() {
    use std::os::unix::fs::PermissionsExt;
    let (_tmp, target, store) = fixture();
    fs::create_dir(target.root.join("src")).unwrap();
    fs::write(target.root.join("src/data.bin"), [0, 255, 3, 0]).unwrap();
    fs::set_permissions(
        target.root.join("src/data.bin"),
        fs::Permissions::from_mode(0o751),
    )
    .unwrap();
    let snapshot = store.capture(&target).unwrap();
    assert_eq!(snapshot.bytes, 4);
    assert_eq!(snapshot.entries.len(), 2);
    assert_eq!(snapshot.entries[1].mode, 0o751);
    assert!(valid_id(&snapshot.id));
    let reopened = SnapshotStore::open(&store.path).unwrap();
    assert_eq!(reopened.list(&target).unwrap(), vec![snapshot]);
    assert_eq!(
        fs::read(target.root.join(".git")).unwrap(),
        b"gitdir: host-owned-control"
    );
}
#[cfg(target_os = "linux")]
#[test]
fn explicit_capture_only_and_empty_tree() {
    let (_tmp, target, store) = fixture();
    assert!(store.list(&target).unwrap().is_empty());
    let snap = store.capture(&target).unwrap();
    assert!(snap.entries.is_empty());
    assert_eq!(snap.bytes, 0);
}
#[cfg(target_os = "linux")]
#[test]
fn add_replace_delete_restore_keeps_backup_and_git_control() {
    let (_tmp, target, store) = fixture();
    fs::write(target.root.join("a"), b"old").unwrap();
    fs::write(target.root.join("restore-me"), b"restore").unwrap();
    let snap = store.capture(&target).unwrap();
    fs::write(target.root.join("a"), b"new").unwrap();
    fs::remove_file(target.root.join("restore-me")).unwrap();
    fs::write(target.root.join("delete-me"), b"keep backup").unwrap();
    let plan = store.plan_restore(&target, &snap.id).unwrap();
    assert_eq!(
        plan.changes
            .iter()
            .map(|c| c.action.as_str())
            .collect::<Vec<_>>(),
        vec!["replace", "delete", "add"]
    );
    let report = store.restore(&target, &plan, |_| Ok(())).unwrap();
    assert_eq!(fs::read(target.root.join("a")).unwrap(), b"old");
    assert!(!target.root.join("delete-me").exists());
    let backup = store
        .path
        .join(format!("transaction-{}", report.transaction_id))
        .join("backup");
    assert_eq!(fs::read(backup.join("a")).unwrap(), b"new");
    assert_eq!(fs::read(backup.join("delete-me")).unwrap(), b"keep backup");
    assert!(report.retained_backup);
    assert!(!store.recovery_required().unwrap());
    assert_eq!(
        fs::read(target.root.join(".git")).unwrap(),
        b"gitdir: host-owned-control"
    );
}
#[cfg(target_os = "linux")]
#[test]
fn content_change_after_plan_denies_without_displacement() {
    let (_t, target, store) = fixture();
    fs::write(target.root.join("a"), b"old").unwrap();
    let snap = store.capture(&target).unwrap();
    let plan = store.plan_restore(&target, &snap.id).unwrap();
    fs::write(target.root.join("a"), b"external edit").unwrap();
    assert_eq!(
        store.restore(&target, &plan, |_| Ok(())).unwrap_err(),
        SnapshotError::Changed
    );
    assert_eq!(fs::read(target.root.join("a")).unwrap(), b"external edit");
    assert!(!store.recovery_required().unwrap());
}
#[cfg(target_os = "linux")]
#[test]
fn missing_native_lease_denies_before_transaction() {
    let (_t, target, store) = fixture();
    let snap = store.capture(&target).unwrap();
    let plan = store.plan_restore(&target, &snap.id).unwrap();
    assert_eq!(
        store
            .restore(&target, &plan, |_| Err(SnapshotError::Approval))
            .unwrap_err(),
        SnapshotError::Approval
    );
    assert!(!store.recovery_required().unwrap());
}
#[cfg(target_os = "linux")]
#[test]
fn failure_mid_apply_preserves_bytes_and_restart_blocks_mutation() {
    let (_t, target, store) = fixture();
    for n in ["a", "b"] {
        fs::write(target.root.join(n), b"before").unwrap();
    }
    let snap = store.capture(&target).unwrap();
    for n in ["a", "b"] {
        fs::write(target.root.join(n), b"new edit").unwrap();
    }
    let plan = store.plan_restore(&target, &snap.id).unwrap();
    let mut count = 0;
    assert_eq!(
        store
            .restore(&target, &plan, |_| {
                count += 1;
                if count == 3 {
                    Err(SnapshotError::Approval)
                } else {
                    Ok(())
                }
            })
            .unwrap_err(),
        SnapshotError::RecoveryRequired
    );
    let tx = fs::read_dir(&store.path)
        .unwrap()
        .map(|e| e.unwrap().path())
        .find(|p| {
            p.file_name()
                .unwrap()
                .to_str()
                .unwrap()
                .starts_with("transaction-")
        })
        .unwrap();
    assert_eq!(fs::read(tx.join("backup/a")).unwrap(), b"new edit");
    assert_eq!(fs::read(target.root.join("b")).unwrap(), b"new edit");
    let restarted = SnapshotStore::open(&store.path).unwrap();
    assert!(restarted.recovery_required().unwrap());
    assert_eq!(
        restarted.capture(&target).unwrap_err(),
        SnapshotError::RecoveryRequired
    );
    assert_eq!(
        restarted.plan_restore(&target, &snap.id).unwrap_err(),
        SnapshotError::RecoveryRequired
    );
}
#[cfg(target_os = "linux")]
#[test]
fn concurrent_write_during_lease_recheck_fails_closed_and_preserves_content() {
    let (_t, target, store) = fixture();
    fs::write(target.root.join("a"), b"before").unwrap();
    let snap = store.capture(&target).unwrap();
    fs::write(target.root.join("a"), b"new").unwrap();
    let plan = store.plan_restore(&target, &snap.id).unwrap();
    let mut count = 0;
    assert_eq!(
        store
            .restore(&target, &plan, |_| {
                count += 1;
                if count == 2 {
                    fs::write(target.root.join("a"), b"concurrent").unwrap();
                }
                Ok(())
            })
            .unwrap_err(),
        SnapshotError::RecoveryRequired
    );
    assert_eq!(fs::read(target.root.join("a")).unwrap(), b"concurrent");
}
#[cfg(target_os = "linux")]
#[test]
fn symlink_and_hardlink_capture_are_rejected() {
    use std::os::unix::fs::symlink;
    let (temp, target, store) = fixture();
    let outside = temp.path().join("outside");
    fs::write(&outside, b"outside").unwrap();
    symlink(&outside, target.root.join("alias")).unwrap();
    assert!(store.capture(&target).is_err());
    fs::remove_file(target.root.join("alias")).unwrap();
    fs::hard_link(&outside, target.root.join("alias")).unwrap();
    assert!(store.capture(&target).is_err());
    assert_eq!(fs::read(outside).unwrap(), b"outside");
}
#[cfg(target_os = "linux")]
#[test]
fn protected_files_are_not_silently_omitted() {
    for name in [
        ".env",
        ".github",
        "private.key",
        "credentials.json",
        "authority-state",
        "execution-journal",
    ] {
        let (_t, target, store) = fixture();
        fs::write(target.root.join(name), b"sensitive").unwrap();
        assert_eq!(
            store.capture(&target).unwrap_err(),
            SnapshotError::Protected
        );
        assert!(store.list(&target).unwrap().is_empty());
    }
}
#[cfg(target_os = "linux")]
#[test]
fn fifo_rejected_without_blocking() {
    use std::os::unix::ffi::OsStrExt;
    let (_t, target, store) = fixture();
    let path = std::ffi::CString::new(target.root.join("pipe").as_os_str().as_bytes()).unwrap();
    assert_eq!(unsafe { libc::mkfifo(path.as_ptr(), 0o600) }, 0);
    assert!(store.capture(&target).is_err());
}
#[cfg(target_os = "linux")]
#[test]
fn limits_are_whole_capture_refusals() {
    let (_t, target, store) = fixture();
    fs::write(target.root.join("large"), vec![0; MAX_FILE as usize + 1]).unwrap();
    assert!(store.capture(&target).is_err());
    assert!(store.list(&target).unwrap().is_empty());
}
#[cfg(target_os = "linux")]
#[test]
fn partial_capture_never_listed() {
    let (_t, target, store) = fixture();
    let id = "c".repeat(32);
    fs::create_dir(store.path.join(&id)).unwrap();
    fs::write(store.path.join(&id).join("manifest.json"), b"{}").unwrap();
    assert!(store.list(&target).unwrap().is_empty());
    assert!(store.plan_restore(&target, &id).is_err());
}
#[cfg(target_os = "linux")]
#[test]
fn blob_corruption_never_used() {
    let (_t, target, store) = fixture();
    fs::write(target.root.join("a"), b"old").unwrap();
    let snap = store.capture(&target).unwrap();
    fs::write(
        store
            .path
            .join(&snap.id)
            .join("blobs")
            .join(&snap.entries[0].hash),
        b"bad",
    )
    .unwrap();
    assert_eq!(
        store.plan_restore(&target, &snap.id).unwrap_err(),
        SnapshotError::Corrupt
    );
}
#[cfg(target_os = "linux")]
#[test]
fn manifest_corruption_and_foreign_target_denied() {
    let (_t, mut target, store) = fixture();
    let snap = store.capture(&target).unwrap();
    target.worktree = "f".repeat(32);
    assert_eq!(
        store.plan_restore(&target, &snap.id).unwrap_err(),
        SnapshotError::Changed
    );
    target.worktree = "b".repeat(32);
    fs::write(store.path.join(&snap.id).join("manifest.json"), b"{}").unwrap();
    assert_eq!(
        store.plan_restore(&target, &snap.id).unwrap_err(),
        SnapshotError::Corrupt
    );
}
#[cfg(target_os = "linux")]
#[test]
fn tampered_or_expired_approval_is_rejected() {
    let (_t, target, store) = fixture();
    let snap = store.capture(&target).unwrap();
    let mut plan = store.plan_restore(&target, &snap.id).unwrap();
    plan.current_digest = "0".repeat(64);
    assert_eq!(
        store.restore(&target, &plan, |_| Ok(())).unwrap_err(),
        SnapshotError::Approval
    );
    plan.expires_at = 0;
    assert_eq!(
        store.restore(&target, &plan, |_| Ok(())).unwrap_err(),
        SnapshotError::Expired
    );
}
#[cfg(target_os = "linux")]
#[test]
fn root_replacement_and_symlink_ancestor_denied() {
    use std::os::unix::fs::symlink;
    let (tmp, target, store) = fixture();
    let snap = store.capture(&target).unwrap();
    fs::rename(&target.root, tmp.path().join("old-root")).unwrap();
    fs::create_dir(&target.root).unwrap();
    assert!(store.plan_restore(&target, &snap.id).is_err());
    fs::remove_dir(&target.root).unwrap();
    symlink(tmp.path().join("old-root"), &target.root).unwrap();
    assert!(store.capture(&target).is_err());
}
#[cfg(target_os = "linux")]
#[test]
fn store_lock_serializes_but_does_not_claim_editor_exclusion() {
    let (_t, target, store) = fixture();
    let _lock = store.directory.lock().unwrap();
    assert_eq!(store.capture(&target).unwrap_err(), SnapshotError::Busy);
}
#[test]
fn unsafe_manifest_paths_and_case_protected_names_rejected() {
    for path in [
        "../escape",
        "dir/../escape",
        "a:b",
        "CON",
        ".SSH/key",
        "DIR/secret.txt",
    ] {
        assert!(path.split('/').try_for_each(content_component).is_err());
    }
}
#[cfg(not(target_os = "linux"))]
#[test]
fn unsupported_platform_has_no_filesystem_write_fallback() {
    let t = tempfile::tempdir().unwrap();
    assert!(matches!(
        SnapshotStore::open(t.path()),
        Err(SnapshotError::Unsupported)
    ));
    assert!(fs::read_dir(t.path()).unwrap().next().is_none());
}
#[cfg(target_os = "linux")]
#[test]
fn directory_tree_and_readonly_permissions_restore() {
    use std::os::unix::fs::PermissionsExt;
    let (_t, target, store) = fixture();
    fs::create_dir(target.root.join("src")).unwrap();
    fs::write(target.root.join("src/file"), b"old").unwrap();
    fs::write(target.root.join(".gitignore"), b"build\n").unwrap();
    fs::set_permissions(target.root.join("src"), fs::Permissions::from_mode(0o555)).unwrap();
    let snap = store.capture(&target).unwrap();
    fs::set_permissions(target.root.join("src"), fs::Permissions::from_mode(0o755)).unwrap();
    fs::write(target.root.join("src/file"), b"new").unwrap();
    let plan = store.plan_restore(&target, &snap.id).unwrap();
    store.restore(&target, &plan, |_| Ok(())).unwrap();
    assert_eq!(fs::read(target.root.join("src/file")).unwrap(), b"old");
    assert_eq!(
        fs::metadata(target.root.join("src"))
            .unwrap()
            .permissions()
            .mode()
            & 0o777,
        0o555
    );
}
#[cfg(target_os = "linux")]
#[test]
fn atomic_move_never_replaces_recreated_destination() {
    let (t, _target, store) = fixture();
    let other = store.directory.mkdir("other").unwrap();
    store.directory.write_new("source", b"old", 0o600).unwrap();
    other
        .write_new("destination", b"concurrent", 0o600)
        .unwrap();
    assert_eq!(
        store
            .directory
            .move_new("source", &other, "destination")
            .unwrap_err(),
        SnapshotError::Changed
    );
    assert_eq!(
        fs::read(t.path().join("snapshots/other/destination")).unwrap(),
        b"concurrent"
    );
    assert_eq!(fs::read(t.path().join("snapshots/source")).unwrap(), b"old");
}
#[cfg(target_os = "linux")]
#[test]
fn total_bytes_and_entry_count_are_bounded() {
    let (_t, target, store) = fixture();
    for n in 0..17 {
        fs::write(
            target.root.join(format!("f{n:03}")),
            vec![0; MAX_FILE as usize],
        )
        .unwrap();
    }
    assert_eq!(store.capture(&target).unwrap_err(), SnapshotError::Capacity);
    let (_t, target, store) = fixture();
    for n in 0..257 {
        fs::write(target.root.join(format!("f{n:03}")), b"").unwrap();
    }
    assert_eq!(store.capture(&target).unwrap_err(), SnapshotError::Capacity);
}
#[cfg(target_os = "linux")]
#[test]
fn partial_or_forged_complete_marker_never_unlocks_recovery() {
    let (_t, target, store) = fixture();
    let tx = store.directory.mkdir("transaction-fixture").unwrap();
    tx.write_new("complete", b"", 0o600).unwrap();
    assert!(store.recovery_required().unwrap());
    assert_eq!(
        store.capture(&target).unwrap_err(),
        SnapshotError::RecoveryRequired
    );
    let (_t, target, store) = fixture();
    let tx = store.directory.mkdir("transaction-fixture").unwrap();
    tx.write_new("complete", "0".repeat(64).as_bytes(), 0o600)
        .unwrap();
    tx.write_new("plan.json", b"{}", 0o600).unwrap();
    assert!(store.recovery_required().unwrap());
    assert_eq!(
        store.capture(&target).unwrap_err(),
        SnapshotError::RecoveryRequired
    );
}
#[cfg(target_os = "linux")]
#[test]
fn readonly_original_directory_requiring_move_is_refused_during_plan() {
    use std::os::unix::fs::PermissionsExt;
    let (_t, target, store) = fixture();
    fs::create_dir(target.root.join("src")).unwrap();
    fs::write(target.root.join("src/file"), b"before").unwrap();
    let snap = store.capture(&target).unwrap();
    fs::write(target.root.join("src/file"), b"new").unwrap();
    fs::set_permissions(target.root.join("src"), fs::Permissions::from_mode(0o555)).unwrap();
    assert_eq!(
        store.plan_restore(&target, &snap.id).unwrap_err(),
        SnapshotError::Unsupported
    );
    assert!(!store.recovery_required().unwrap());
    assert_eq!(fs::read(target.root.join("src/file")).unwrap(), b"new");
}
