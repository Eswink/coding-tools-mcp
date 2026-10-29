//! #86: the exact opened root handle must match the native-retained trusted identity.
//! The target's pathname check passes (as a path-only authority would) and then swaps the
//! root on a chosen verify() call, so the check/use gap is exercised deterministically.
use super::*;
use std::{cell::Cell, fs, os::unix::fs::PermissionsExt, path::PathBuf};

#[derive(Clone, Copy)]
enum Swap {
    /// Replace the root with a different directory and leave it there.
    Replace,
    /// Move the root away and move the same inode back (true ABA, identity unchanged).
    SameBack,
}
struct SwapTarget {
    root: PathBuf,
    trusted: String,
    calls: Cell<usize>,
    swap_on: Cell<usize>,
    swap: Swap,
}
impl SwapTarget {
    fn swap_now(&self) {
        let parked = self.root.with_file_name("parked");
        fs::rename(&self.root, &parked).unwrap();
        match self.swap {
            Swap::Replace => {
                fs::create_dir(&self.root).unwrap();
                fs::write(self.root.join("intruder"), b"other root").unwrap();
            }
            Swap::SameBack => fs::rename(&parked, &self.root).unwrap(),
        }
    }
}
impl TargetAuthority for SwapTarget {
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
        let n = self.calls.get() + 1;
        self.calls.set(n);
        if n == self.swap_on.get() {
            self.swap_now();
        }
        Ok(())
    }
    fn trusted_root_identity(&self) -> String {
        self.trusted.clone()
    }
}
fn fixture(swap: Swap) -> (tempfile::TempDir, SwapTarget, SnapshotStore) {
    let temp = tempfile::tempdir().unwrap();
    fs::set_permissions(temp.path(), fs::Permissions::from_mode(0o700)).unwrap();
    let root = temp.path().join("managed");
    fs::create_dir(&root).unwrap();
    fs::write(root.join("a"), b"original").unwrap();
    let trusted = Dir::open(&root).unwrap().identity().unwrap();
    let store = SnapshotStore::create(temp.path(), "snapshots").unwrap();
    let target = SwapTarget {
        root,
        trusted,
        calls: Cell::new(0),
        swap_on: Cell::new(0),
        swap,
    };
    (temp, target, store)
}
fn snapshot_ids(store: &SnapshotStore) -> Vec<String> {
    store
        .directory
        .names()
        .unwrap()
        .into_iter()
        .filter(|n| valid_id(n))
        .collect()
}
fn tree(path: &Path) -> Vec<(String, Vec<u8>)> {
    let mut out: Vec<_> = fs::read_dir(path)
        .unwrap()
        .map(|e| {
            let e = e.unwrap();
            (
                e.file_name().to_string_lossy().into_owned(),
                fs::read(e.path()).unwrap(),
            )
        })
        .collect();
    out.sort();
    out
}

#[test]
fn root_replaced_between_verify_and_open_is_refused_before_capture() {
    let (tmp, target, store) = fixture(Swap::Replace);
    target.swap_on.set(1);
    assert_eq!(store.capture(&target).unwrap_err(), SnapshotError::Changed);
    assert!(snapshot_ids(&store).is_empty());
    assert_eq!(
        tree(&tmp.path().join("parked")),
        vec![("a".into(), b"original".to_vec())]
    );
    assert_eq!(
        tree(&target.root),
        vec![("intruder".into(), b"other root".to_vec())]
    );
}
#[test]
fn root_replaced_after_open_aba_is_refused() {
    let (tmp, target, store) = fixture(Swap::Replace);
    target.swap_on.set(2);
    assert_eq!(store.capture(&target).unwrap_err(), SnapshotError::Changed);
    assert!(snapshot_ids(&store).is_empty());
    assert_eq!(
        tree(&tmp.path().join("parked")),
        vec![("a".into(), b"original".to_vec())]
    );
}
#[test]
fn same_inode_returned_is_still_the_trusted_root() {
    let (_tmp, target, store) = fixture(Swap::SameBack);
    target.swap_on.set(1);
    let snap = store.capture(&target).unwrap();
    assert_eq!(snap.root_identity, target.trusted);
    assert_eq!(snapshot_ids(&store), vec![snap.id]);
}
#[test]
fn mismatched_trusted_identity_is_refused_before_reading() {
    let (_tmp, mut target, store) = fixture(Swap::Replace);
    target.trusted = "0:0".into();
    assert_eq!(store.capture(&target).unwrap_err(), SnapshotError::Changed);
    assert_eq!(store.list(&target).unwrap_err(), SnapshotError::Changed);
    assert!(snapshot_ids(&store).is_empty());
}
#[test]
fn restore_against_replaced_root_writes_nothing() {
    let (tmp, target, store) = fixture(Swap::Replace);
    let snap = store.capture(&target).unwrap();
    fs::write(target.root.join("a"), b"edited").unwrap();
    let plan = store.plan_restore(&target, &snap.id).unwrap();
    let before_trusted = tree(&target.root);
    target.swap_on.set(target.calls.get() + 1);
    assert_eq!(
        store.restore(&target, &plan, |_| Ok(())).unwrap_err(),
        SnapshotError::Changed
    );
    assert_eq!(tree(&tmp.path().join("parked")), before_trusted);
    assert_eq!(
        tree(&target.root),
        vec![("intruder".into(), b"other root".to_vec())]
    );
    assert!(!store.recovery_required().unwrap());
}
