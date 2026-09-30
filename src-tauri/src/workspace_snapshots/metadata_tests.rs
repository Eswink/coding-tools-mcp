use super::*;
use std::{
    fs,
    os::unix::{ffi::OsStrExt, fs::PermissionsExt},
};
struct Target {
    root: std::path::PathBuf,
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
        Ok(())
    }
}
fn fixture() -> (tempfile::TempDir, Target, SnapshotStore) {
    let temp = tempfile::tempdir().unwrap();
    fs::set_permissions(temp.path(), fs::Permissions::from_mode(0o700)).unwrap();
    let root = temp.path().join("managed");
    fs::create_dir(&root).unwrap();
    let store = SnapshotStore::create(temp.path(), "snapshots").unwrap();
    (temp, Target { root }, store)
}
fn attribute(path: &Path) {
    let path = std::ffi::CString::new(path.as_os_str().as_bytes()).unwrap();
    let name = std::ffi::CString::new("user.snapshot-fixture").unwrap();
    assert_eq!(
        unsafe { libc::setxattr(path.as_ptr(), name.as_ptr(), b"dummy".as_ptr().cast(), 5, 0) },
        0,
        "fixture filesystem must support owned user xattrs"
    );
}
#[test]
fn file_and_directory_xattrs_are_refused_without_silent_loss() {
    for directory in [false, true] {
        let (_temp, target, store) = fixture();
        let path = target.root.join("entry");
        if directory {
            fs::create_dir(&path).unwrap()
        } else {
            fs::write(&path, b"content").unwrap()
        }
        attribute(&path);
        assert_eq!(
            store.capture(&target).unwrap_err(),
            SnapshotError::Unsupported
        );
        assert!(store.list(&target).unwrap().is_empty());
    }
}
#[test]
fn ownership_is_recorded_and_bound() {
    let (_temp, target, store) = fixture();
    fs::write(target.root.join("a"), b"content").unwrap();
    let snapshot = store.capture(&target).unwrap();
    assert_eq!(snapshot.entries[0].uid, Some(unsafe { libc::geteuid() }));
    assert_eq!(snapshot.entries[0].gid, Some(unsafe { libc::getegid() }));
    let mut entry = snapshot.entries[0].clone();
    entry.uid = Some(entry.uid.unwrap().wrapping_add(1));
    assert_eq!(
        validate_entries(&[entry]).unwrap_err(),
        SnapshotError::Unsupported
    );
}
#[test]
fn extended_attribute_added_after_plan_prevents_any_restore() {
    let (_temp, target, store) = fixture();
    fs::write(target.root.join("a"), b"content").unwrap();
    let snapshot = store.capture(&target).unwrap();
    let plan = store.plan_restore(&target, &snapshot.id).unwrap();
    attribute(&target.root.join("a"));
    assert_eq!(
        store.restore(&target, &plan, |_| Ok(())).unwrap_err(),
        SnapshotError::Unsupported
    );
    assert!(!store.recovery_required().unwrap());
    assert_eq!(fs::read(target.root.join("a")).unwrap(), b"content");
}
