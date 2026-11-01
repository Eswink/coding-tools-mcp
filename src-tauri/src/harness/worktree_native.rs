//! Native-only registration pins in private harness storage, never source Git metadata.
//! Nothing in this module accepts cloud authority.
use super::super::worktree_boundary::{failure, read_file};
use super::{WorktreeManager, WorktreeResult};
use std::{
    fs::{self, OpenOptions},
    io::Write,
    sync::{Mutex, MutexGuard},
};

static LIFECYCLE: Mutex<()> = Mutex::new(());
/// Holds the process-wide lifecycle lock. Under test it also records, per thread,
/// that the lock is held so slot release ordering can be asserted (SPEC-A1 v4 §1.6).
pub(super) struct LifecycleGuard(#[allow(dead_code)] MutexGuard<'static, ()>);
#[cfg(test)]
thread_local! {
    static HELD: std::cell::Cell<bool> = const { std::cell::Cell::new(false) };
}
impl Drop for LifecycleGuard {
    fn drop(&mut self) {
        #[cfg(test)]
        HELD.with(|held| held.set(false));
    }
}
#[cfg(test)]
pub(super) fn held_by_current_thread() -> bool {
    HELD.with(std::cell::Cell::get)
}
#[cfg(test)]
thread_local! {
    static FAIL_NEXT: std::cell::Cell<bool> = const { std::cell::Cell::new(false) };
}
/// Test seam (A1 C3): the next `lock()` on this thread returns LOCK_UNAVAILABLE,
/// the same Err a poisoned lifecycle mutex yields, without poisoning the
/// process-wide static that parallel tests share.
#[cfg(test)]
pub(super) fn fail_next_lock_for_test() {
    FAIL_NEXT.with(|fail| fail.set(true));
}
pub(super) fn lock() -> WorktreeResult<LifecycleGuard> {
    #[cfg(test)]
    if FAIL_NEXT.with(std::cell::Cell::take) {
        return Err(failure("LOCK_UNAVAILABLE"));
    }
    let guard = LIFECYCLE.lock().map_err(|_| failure("LOCK_UNAVAILABLE"))?;
    #[cfg(test)]
    HELD.with(|held| held.set(true));
    Ok(LifecycleGuard(guard))
}
/// A1 C3: the lock for releasing a slot. It never fails: a poisoned mutex is
/// recovered (the `()` payload carries no state), so a reservation is always
/// dropped inside the lock a concurrent create counts under.
pub(super) fn lock_for_release() -> LifecycleGuard {
    let guard = LIFECYCLE
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner);
    #[cfg(test)]
    HELD.with(|held| held.set(true));
    LifecycleGuard(guard)
}
impl WorktreeManager {
    /// Serializes broker mutations in this host process. Not an execution drain proof.
    /// The closure may call snapshot_target/verify/native_profile, but not mutators.
    pub(crate) fn with_lifecycle<T>(
        &self,
        operation: impl FnOnce() -> WorktreeResult<T>,
    ) -> WorktreeResult<T> {
        let _guard = lock()?;
        self.validate_boundary()?;
        let value = operation()?;
        self.validate_boundary()?;
        Ok(value)
    }
    /// A persistent pin is created only by an explicit native-owner registration flow.
    /// A failed subsequent profile save leaves the pin in place; remote removal stays denied.
    pub(crate) fn pin_native_profile(&self, id: &str, profile: &str) -> WorktreeResult<()> {
        if profile.is_empty()
            || profile.len() > 128
            || !profile
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_')
        {
            return Err(failure("INVALID_ID"));
        }
        self.with_lifecycle(|| {
            self.snapshot_target(id)?.verify()?;
            if let Some(existing) = self.native_profile(id)? {
                return if existing == profile {
                    Ok(())
                } else {
                    Err(failure("WORKTREE_PINNED"))
                };
            }
            let marker = self.managed_root.join(format!("{id}.native-profile-pin"));
            let mut file = OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(&marker)
                .map_err(|_| failure("IO_FAILED"))?;
            file.write_all(format!("{profile}\n").as_bytes())
                .and_then(|_| file.sync_all())
                .map_err(|_| failure("IO_FAILED"))?;
            self.snapshot_target(id)?.verify()
        })
    }
    /// Read after verify under with_lifecycle when this value is used for native admission.
    pub(crate) fn native_profile(&self, id: &str) -> WorktreeResult<Option<String>> {
        self.snapshot_target(id)?.verify()?;
        let marker = self.managed_root.join(format!("{id}.native-profile-pin"));
        match fs::symlink_metadata(&marker) {
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
            Err(_) => return Err(failure("BOUNDARY_VIOLATION")),
            Ok(_) => {}
        }
        let bytes = read_file(&marker, 256)?;
        let profile = std::str::from_utf8(&bytes)
            .map_err(|_| failure("PARSE_FAILED"))?
            .trim_end_matches('\n');
        if profile.is_empty()
            || profile.len() > 128
            || !profile
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_')
        {
            return Err(failure("BOUNDARY_VIOLATION"));
        }
        Ok(Some(profile.to_owned()))
    }
}
