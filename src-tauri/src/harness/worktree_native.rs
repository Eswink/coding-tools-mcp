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
pub(super) fn lock() -> WorktreeResult<MutexGuard<'static, ()>> {
    LIFECYCLE.lock().map_err(|_| failure("LOCK_UNAVAILABLE"))
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
