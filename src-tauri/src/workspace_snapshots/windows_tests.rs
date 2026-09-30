//! Real Windows filesystem fixtures. Never a substitute for native app lease tests.
use super::*;
use std::{fs, path::PathBuf};
struct Target {
    root: PathBuf,
    identity: String,
}
impl TargetAuthority for Target {
    fn root(&self) -> &Path {
        &self.root
    }
    fn workspace_id(&self) -> &str {
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    }
    fn worktree_id(&self) -> &str {
        "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    }
    fn head(&self) -> &str {
        "0123456789012345678901234567890123456789"
    }
    fn verify(&self) -> Result<()> {
        if Dir::open(&self.root)?.identity()? != self.identity {
            return Err(SnapshotError::Changed);
        }
        Ok(())
    }
}
fn fixture() -> (tempfile::TempDir, Target, SnapshotStore) {
    let temp = tempfile::tempdir().unwrap();
    let dir = Dir::open(temp.path()).expect("pin temporary fixture ancestors");
    let private = dir
        .mkdir("private")
        .expect("create private disposable namespace");
    let root = private
        .mkdir("managed")
        .expect("create private disposable managed root");
    let target = Target {
        root: temp.path().join("private/managed"),
        identity: root.identity().unwrap(),
    };
    fs::write(
        target.root.join(".git"),
        b"gitdir: synthetic-native-owner-control",
    )
    .unwrap();
    let store = SnapshotStore::create(&temp.path().join("private"), "snapshots").unwrap();
    (temp, target, store)
}
#[test]
fn capture_reopen_and_complete_restore_preserve_descriptor_and_binary() {
    let (_temp, target, store) = fixture();
    fs::write(target.root.join("a"), [0, 255, 3, 0]).unwrap();
    fs::create_dir(target.root.join("src")).unwrap();
    fs::write(target.root.join("src/b"), b"before").unwrap();
    let snapshot = store.capture(&target).unwrap();
    assert!(snapshot
        .entries
        .iter()
        .all(|e| e.security.is_some() && e.attributes.is_some()));
    assert_eq!(
        SnapshotStore::open(&store.path)
            .unwrap()
            .list(&target)
            .unwrap()[0],
        snapshot
    );
    fs::write(target.root.join("a"), b"new").unwrap();
    fs::remove_file(target.root.join("src/b")).unwrap();
    fs::write(target.root.join("extra"), b"preserve").unwrap();
    let plan = store.plan_restore(&target, &snapshot.id).unwrap();
    let report = store.restore(&target, &plan, |_| Ok(())).unwrap();
    assert_eq!(
        Dir::open(&target.root).unwrap().scan(true).unwrap().entries,
        snapshot.entries
    );
    assert_eq!(
        fs::read(
            store
                .path
                .join(format!("transaction-{}/backup/a", report.transaction_id))
        )
        .unwrap(),
        b"new"
    );
    assert!(!target.root.join("extra").exists());
    assert_eq!(
        fs::read(target.root.join(".git")).unwrap(),
        b"gitdir: synthetic-native-owner-control"
    );
}
#[test]
fn live_pinned_handle_blocks_root_rename_and_reopen_reuses_ownership() {
    let (temp, target, store) = fixture();
    let guard = Dir::open(&target.root).unwrap();
    let second = Dir::open(&target.root).unwrap();
    assert_eq!(guard.identity().unwrap(), second.identity().unwrap());
    assert!(fs::rename(&target.root, temp.path().join("replacement")).is_err());
    drop(second);
    drop(guard);
    // The sibling store also owns ancestor pins. Release all managed handles.
    drop(store);
    fs::rename(&target.root, temp.path().join("replacement")).unwrap();
    assert!(target.verify().is_err());
}
#[test]
fn hardlinks_and_ads_refused_before_snapshot_publication() {
    let (temp, target, store) = fixture();
    let outside = temp.path().join("external");
    fs::write(&outside, b"outside").unwrap();
    fs::hard_link(&outside, target.root.join("alias")).unwrap();
    assert!(store.capture(&target).is_err());
    fs::remove_file(target.root.join("alias")).unwrap();
    fs::write(target.root.join("normal"), b"main").unwrap();
    fs::write(target.root.join("normal:extra"), b"stream").unwrap();
    assert!(store.capture(&target).is_err());
    assert!(store.list(&target).unwrap().is_empty());
    assert_eq!(fs::read(outside).unwrap(), b"outside");
}
#[test]
fn junction_escape_refused() {
    let (temp, target, store) = fixture();
    let outside = temp.path().join("external-dir");
    fs::create_dir(&outside).unwrap();
    fs::write(outside.join("value"), b"outside").unwrap();
    let result = std::process::Command::new("cmd.exe")
        .args(["/D", "/C", "mklink", "/J"])
        .arg(target.root.join("junction").to_str().unwrap().replace('/', "\\"))
        .arg(outside.to_str().unwrap().replace('/', "\\"))
        .output()
        .unwrap();
    assert!(
        result.status.success(),
        "disposable junction fixture must exist: status={:?}, stdout={}, stderr={}",
        result.status.code(), String::from_utf8_lossy(&result.stdout),
        String::from_utf8_lossy(&result.stderr)
    );
    assert!(store.capture(&target).is_err());
    assert_eq!(fs::read(outside.join("value")).unwrap(), b"outside");
}
#[test]
fn content_and_readonly_attribute_conflicts_prevent_restore() {
    let (_temp, target, store) = fixture();
    fs::write(target.root.join("a"), b"before").unwrap();
    let snapshot = store.capture(&target).unwrap();
    let plan = store.plan_restore(&target, &snapshot.id).unwrap();
    let mut permissions = fs::metadata(target.root.join("a")).unwrap().permissions();
    permissions.set_readonly(true);
    fs::set_permissions(target.root.join("a"), permissions).unwrap();
    assert_eq!(
        store.restore(&target, &plan, |_| Ok(())).unwrap_err(),
        SnapshotError::Changed
    );
    assert!(!store.recovery_required().unwrap());
}
#[test]
fn desired_readonly_attribute_is_restored_without_changing_backup() {
    let (_temp, target, store) = fixture();
    fs::write(target.root.join("a"), b"before").unwrap();
    let mut p = fs::metadata(target.root.join("a")).unwrap().permissions();
    p.set_readonly(true);
    fs::set_permissions(target.root.join("a"), p).unwrap();
    let snapshot = store.capture(&target).unwrap();
    let mut p = fs::metadata(target.root.join("a")).unwrap().permissions();
    p.set_readonly(false);
    fs::set_permissions(target.root.join("a"), p).unwrap();
    fs::write(target.root.join("a"), b"after").unwrap();
    let plan = store.plan_restore(&target, &snapshot.id).unwrap();
    let report = store.restore(&target, &plan, |_| Ok(())).unwrap();
    assert!(fs::metadata(target.root.join("a"))
        .unwrap()
        .permissions()
        .readonly());
    assert!(!fs::metadata(
        store
            .path
            .join(format!("transaction-{}/backup/a", report.transaction_id))
    )
    .unwrap()
    .permissions()
    .readonly());
}
#[test]
fn injected_mid_apply_failure_retains_original_and_blocks_restart() {
    let (_temp, target, store) = fixture();
    for name in ["a", "b"] {
        fs::write(target.root.join(name), b"before").unwrap()
    }
    let snapshot = store.capture(&target).unwrap();
    for name in ["a", "b"] {
        fs::write(target.root.join(name), b"current").unwrap()
    }
    let plan = store.plan_restore(&target, &snapshot.id).unwrap();
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
    let reopened = SnapshotStore::open(&store.path).unwrap();
    assert!(reopened.recovery_required().unwrap());
    assert_eq!(
        reopened.capture(&target).unwrap_err(),
        SnapshotError::RecoveryRequired
    );
    let tx = store
        .directory
        .names()
        .unwrap()
        .into_iter()
        .find(|s| s.starts_with("transaction-"))
        .unwrap();
    assert_eq!(
        fs::read(store.path.join(tx).join("backup/a")).unwrap(),
        b"current"
    );
    assert_eq!(fs::read(target.root.join("b")).unwrap(), b"current");
}
#[test]
fn native_authority_and_expiry_required_before_mutation() {
    let (_temp, target, store) = fixture();
    let snapshot = store.capture(&target).unwrap();
    let plan = store.plan_restore(&target, &snapshot.id).unwrap();
    assert_eq!(
        store
            .restore(&target, &plan, |_| Err(SnapshotError::Approval))
            .unwrap_err(),
        SnapshotError::Approval
    );
    let mut expired = plan;
    expired.expires_at = 0;
    assert_eq!(
        store.restore(&target, &expired, |_| Ok(())).unwrap_err(),
        SnapshotError::Expired
    );
    assert!(!store.recovery_required().unwrap());
}
#[test]
fn partial_capture_corrupt_blob_and_bad_transaction_marker_fail_closed() {
    let (_temp, target, store) = fixture();
    let incomplete = store.directory.mkdir(&"c".repeat(32)).unwrap();
    incomplete.write_new("manifest.json", b"{}", 0o600).unwrap();
    assert!(store.list(&target).unwrap().is_empty());
    drop(incomplete);
    fs::write(target.root.join("a"), b"before").unwrap();
    let snapshot = store.capture(&target).unwrap();
    fs::write(
        store
            .path
            .join(&snapshot.id)
            .join("blobs")
            .join(&snapshot.entries[0].hash),
        b"corrupt",
    )
    .unwrap();
    assert_eq!(
        store.plan_restore(&target, &snapshot.id).unwrap_err(),
        SnapshotError::Corrupt
    );
    let tx = store.directory.mkdir("transaction-incomplete").unwrap();
    tx.write_new("complete", b"", 0o600).unwrap();
    assert!(store.recovery_required().unwrap());
    assert_eq!(
        store.capture(&target).unwrap_err(),
        SnapshotError::RecoveryRequired
    );
}
#[test]
fn replacing_existing_destination_is_forbidden() {
    let (_temp, _target, store) = fixture();
    let other = store.directory.mkdir("other").unwrap();
    store.directory.write_new("source", b"old", 0o600).unwrap();
    other.write_new("destination", b"new", 0o600).unwrap();
    assert_eq!(
        store
            .directory
            .move_new("source", &other, "destination")
            .unwrap_err(),
        SnapshotError::Changed
    );
    assert_eq!(other.read("destination", 10).unwrap().0, b"new");
}
#[test]
fn unsafe_windows_roots_and_protected_content_are_refused() {
    for path in [r"\\server\share\root", r"\\.\C:\root", r"C:relative"] {
        assert!(Dir::open(Path::new(path)).is_err())
    }
    let (_temp, target, store) = fixture();
    fs::write(target.root.join(".env"), b"synthetic-private").unwrap();
    assert_eq!(
        store.capture(&target).unwrap_err(),
        SnapshotError::Protected
    );
    assert!(store.list(&target).unwrap().is_empty());
}

#[test]
fn handle_relative_moves_preserve_bytes_with_live_parent_pins() {
    let (_temp, target, _store) = fixture();
    let root = Dir::open(&target.root).unwrap();
    let destination = root.mkdir("destination").unwrap();
    root.write_new("from-file", b"preserved", 0o600).unwrap();
    root.move_new("from-file", &destination, "moved-file").unwrap();
    assert_eq!(destination.read("moved-file", 100).unwrap().0, b"preserved");
    assert!(!target.root.join("from-file").exists());
    let from = root.mkdir("from-directory").unwrap();
    from.write_new("nested", b"nested", 0o600).unwrap();
    drop(from);
    root.move_new("from-directory", &destination, "moved-directory").unwrap();
    assert_eq!(destination.child("moved-directory").unwrap().read("nested", 100).unwrap().0, b"nested");
}
