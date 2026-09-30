//! Native Windows fixtures: junction creation failure is a test failure, never a skip.
use super::*;

fn junction_path(path: &Path) -> std::ffi::OsString {
    use std::os::windows::ffi::{OsStrExt, OsStringExt};
    let units = git_path_arg(path)
        .encode_wide()
        .map(|unit| {
            if unit == b'/' as u16 {
                b'\\' as u16
            } else {
                unit
            }
        })
        .collect::<Vec<_>>();
    std::ffi::OsString::from_wide(&units)
}

fn junction(link: &Path, target: &Path) {
    let result = Command::new("cmd")
        .args(["/D", "/V:OFF", "/C", "mklink", "/J"])
        .arg(junction_path(link))
        .arg(junction_path(target))
        .output()
        .expect("native Windows junction command");
    assert!(
        result.status.success(),
        "junction fixture failed: {}",
        String::from_utf8_lossy(&result.stderr)
    );
    use std::os::windows::fs::MetadataExt;
    assert_ne!(
        fs::symlink_metadata(link).unwrap().file_attributes() & 0x0400,
        0
    );
}

#[test]
fn windows_source_object_junction_is_rejected_without_mutation() {
    let fixture = TestRepo::new();
    let objects = fixture.repo.path().join(".git/objects");
    let moved = fixture.repo.path().join("original-objects");
    fs::rename(&objects, &moved).unwrap();
    junction(&objects, &moved);
    let entries = fs::read_dir(&moved).unwrap().count();
    assert_eq!(
        fixture.manager.create_detached().unwrap_err().code(),
        "BOUNDARY_VIOLATION"
    );
    assert_eq!(fs::read_dir(&moved).unwrap().count(), entries);
    assert!(!fixture.repo.path().join(".git/worktrees").exists());
    fs::remove_dir(&objects).unwrap();
}

#[test]
fn windows_target_junction_cannot_delete_external_or_original_content() {
    let fixture = TestRepo::new();
    let item = fixture.manager.create_detached().unwrap();
    let target = fixture.manager.managed_root.join(&item.id);
    let saved = fixture.harness.path().join("retained-original");
    fs::rename(&target, &saved).unwrap();
    let external = tempfile::tempdir().unwrap();
    fs::write(external.path().join("keep.txt"), b"external").unwrap();
    junction(&target, external.path());
    assert_eq!(
        fixture.manager.remove_clean(&item.id).unwrap_err().code(),
        "BOUNDARY_VIOLATION"
    );
    assert_eq!(
        fs::read(external.path().join("keep.txt")).unwrap(),
        b"external"
    );
    assert_eq!(fs::read(saved.join("README.md")).unwrap(), b"baseline\n");
    assert!(fixture
        .repo
        .path()
        .join(".git/worktrees")
        .join(&item.id)
        .exists());
    fs::remove_dir(&target).unwrap();
}

#[test]
fn windows_ancestor_junction_is_rejected_even_when_leaf_stays_inside() {
    let fixture = TestRepo::new();
    let original = fixture.harness.path().join("worktrees-v1");
    let moved = fixture.harness.path().join("retained-parent");
    fs::rename(&original, &moved).unwrap();
    junction(&original, &moved);
    assert_eq!(
        fixture.manager.create_detached().unwrap_err().code(),
        "BOUNDARY_VIOLATION"
    );
    assert_eq!(fs::read_dir(moved.join(WORKSPACE_ID)).unwrap().count(), 0);
    fs::remove_dir(&original).unwrap();
}

#[test]
fn windows_private_pin_hardlink_cannot_become_registration_authority() {
    let fixture = TestRepo::new();
    let item = fixture.manager.create_detached().unwrap();
    let external = tempfile::tempdir().unwrap();
    let external_pin = external.path().join("pin");
    fs::write(&external_pin, b"forged-native-profile\n").unwrap();
    let marker = fixture
        .manager
        .managed_root
        .join(format!("{}.native-profile-pin", item.id));
    fs::hard_link(&external_pin, &marker).expect("native Windows hardlink fixture");
    assert_eq!(
        fixture.manager.native_profile(&item.id).unwrap_err().code(),
        "BOUNDARY_VIOLATION"
    );
    assert!(fixture.manager.remove_clean(&item.id).is_err());
    assert_eq!(fs::read(&external_pin).unwrap(), b"forged-native-profile\n");
    assert!(fixture
        .manager
        .managed_root
        .join(&item.id)
        .join("README.md")
        .exists());
}

#[test]
fn windows_junction_arguments_preserve_spaces_and_use_native_separators() {
    assert_eq!(
        junction_path(Path::new(r"\\?\C:\fixture with spaces\.git/objects")),
        std::ffi::OsString::from(r"C:\fixture with spaces\.git\objects")
    );
    assert_eq!(
        junction_path(Path::new(r"\\?\UNC\server\share\工具/objects")),
        std::ffi::OsString::from(r"\\server\share\工具\objects")
    );
}
