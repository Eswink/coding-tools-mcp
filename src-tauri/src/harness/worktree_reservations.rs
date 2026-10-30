//! In-process slot reservations for not-yet-built worker worktrees (SPEC-A1 v2 §1.3/§1.6).
//! Counted against MAX_MANAGED_WORKTREES while the native lifecycle lock is held.
use std::{
    collections::BTreeMap,
    path::{Path, PathBuf},
    sync::Mutex,
};

static RESERVED: Mutex<BTreeMap<PathBuf, Vec<String>>> = Mutex::new(BTreeMap::new());

fn with<T>(run: impl FnOnce(&mut BTreeMap<PathBuf, Vec<String>>) -> T) -> T {
    let mut map = RESERVED
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner());
    run(&mut map)
}
pub(super) fn count(root: &Path) -> usize {
    with(|map| map.get(root).map_or(0, Vec::len))
}
pub(super) fn holds(root: &Path, id: &str) -> bool {
    with(|map| map.get(root).is_some_and(|ids| ids.iter().any(|v| v == id)))
}
pub(super) fn take(root: &Path, id: String) -> SlotReservation {
    with(|map| map.entry(root.to_path_buf()).or_default().push(id.clone()));
    SlotReservation {
        root: root.to_path_buf(),
        id,
    }
}

/// One reserved managed slot; released on drop.
#[derive(Debug)]
pub(crate) struct SlotReservation {
    root: PathBuf,
    id: String,
}
impl SlotReservation {
    pub(crate) fn id(&self) -> &str {
        &self.id
    }
    pub(super) fn root(&self) -> &Path {
        &self.root
    }
}
impl Drop for SlotReservation {
    fn drop(&mut self) {
        with(|map| {
            if let Some(ids) = map.get_mut(&self.root) {
                ids.retain(|value| value != &self.id);
                if ids.is_empty() {
                    map.remove(&self.root);
                }
            }
        });
    }
}
