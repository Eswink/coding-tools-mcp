//! Concrete opened read-only archive leases. No returned pathname/boot owner.
use super::super::super::{
    nt::{self, Identity, Info, Opened},
    path,
    root::{RootLease, WindowsInputAuthority},
};
use super::archive_data::{APPROVED, ArchiveHasher, ArchiveSpec, CHUNK};
use std::{
    io::{Read, Seek},
    time::Instant,
};

struct ArchiveFile {
    opened: Opened,
    info: Option<Info>,
    cursor: u64,
    hash: Option<[u8; 32]>,
}
pub(super) struct ImageArchiveLease {
    root: RootLease,
    root_id: Option<Identity>,
    files: Vec<ArchiveFile>,
    poisoned: bool,
    uncertain: bool,
}
impl ImageArchiveLease {
    pub fn new() -> Self {
        Self {
            root: RootLease::new(),
            root_id: None,
            files: Vec::new(),
            poisoned: false,
            uncertain: false,
        }
    }
    pub fn prepare<F: Fn() -> bool>(
        &mut self,
        authority: &WindowsInputAuthority,
        host: uuid::Uuid,
        profile: &str,
        parent: &str,
        expected_root: Identity,
        deadline: Instant,
        cancelled: &F,
    ) -> Result<(), &'static str> {
        self.prepare_entries(
            authority,
            host,
            profile,
            parent,
            expected_root,
            &APPROVED,
            deadline,
            cancelled,
        )
    }
    // Arbitrary manifests never reach the actual claimed caller. Native unit
    // fixtures exercise this private reader only, with no claim/VM/output seal.
    fn prepare_entries<F: Fn() -> bool>(
        &mut self,
        authority: &WindowsInputAuthority,
        host: uuid::Uuid,
        profile: &str,
        parent: &str,
        expected_root: Identity,
        entries: &[ArchiveSpec],
        deadline: Instant,
        cancelled: &F,
    ) -> Result<(), &'static str> {
        let result = (|| {
            if self.poisoned || !self.root.handles.is_empty() || !self.files.is_empty() {
                return Err("WINDOWS_IMAGE_ARCHIVE_LEASE_REUSED");
            }
            Self::checkpoint(deadline, cancelled)?;
            let parts = path::components(parent)?;
            authority.acquire(host, profile, &mut self.root)?;
            let root = self.root.root()?;
            self.root_id = Some(root);
            if root != expected_root {
                return Err("WINDOWS_IMAGE_ARCHIVE_INPUT_ROOT_CONFLICT");
            }
            for part in parts {
                Self::checkpoint(deadline, cancelled)?;
                let opened = nt::open(
                    self.root
                        .handles
                        .last()
                        .ok_or("WINDOWS_INPUT_ROOT_UNAVAILABLE")?,
                    part,
                    true,
                    false,
                )?;
                self.root.handles.push(opened);
                let info = self
                    .root
                    .handles
                    .last()
                    .ok_or("WINDOWS_INPUT_ROOT_UNAVAILABLE")?
                    .info()?;
                if !info.directory || info.identity.volume != root.volume {
                    return Err("WINDOWS_IMAGE_ARCHIVE_PARENT_REJECTED");
                }
            }
            let parent_info = self
                .root
                .handles
                .last()
                .ok_or("WINDOWS_INPUT_ROOT_UNAVAILABLE")?
                .info()?;
            for entry in entries {
                Self::checkpoint(deadline, cancelled)?;
                let parent = self
                    .root
                    .handles
                    .last()
                    .ok_or("WINDOWS_INPUT_ROOT_UNAVAILABLE")?;
                if parent.info()? != parent_info {
                    return Err("WINDOWS_IMAGE_ARCHIVE_PARENT_CHANGED");
                }
                let opened = nt::open(parent, entry.leaf, false, false)?;
                // The whole concrete grant owns self; the handle is registered
                // before identity/cursor/read and is never automatically dropped.
                self.files.push(ArchiveFile {
                    opened,
                    info: None,
                    cursor: 0,
                    hash: None,
                });
                let file = self
                    .files
                    .last_mut()
                    .ok_or("WINDOWS_IMAGE_ARCHIVE_UNAVAILABLE")?;
                let info = file.opened.info()?;
                file.info = Some(info);
                if info.directory
                    || info.links != 1
                    || info.identity.volume != root.volume
                    || info.size != entry.size
                {
                    return Err("WINDOWS_IMAGE_ARCHIVE_FILE_REJECTED");
                }
                file.hash = Some(Self::read_file(
                    file,
                    entry,
                    deadline,
                    cancelled,
                    &mut self.uncertain,
                )?);
                if self
                    .root
                    .handles
                    .last()
                    .ok_or("WINDOWS_INPUT_ROOT_UNAVAILABLE")?
                    .info()?
                    != parent_info
                {
                    return Err("WINDOWS_IMAGE_ARCHIVE_PARENT_CHANGED");
                }
            }
            Self::checkpoint(deadline, cancelled)
        })();
        if result.is_err() {
            self.poisoned = true;
        }
        result
    }
    fn checkpoint<F: Fn() -> bool>(deadline: Instant, cancelled: &F) -> Result<(), &'static str> {
        if cancelled() || Instant::now() >= deadline {
            return Err("WINDOWS_IMAGE_ARCHIVE_CANCELLED");
        }
        Ok(())
    }
    fn read_file<F: Fn() -> bool>(
        file: &mut ArchiveFile,
        spec: &ArchiveSpec,
        deadline: Instant,
        cancelled: &F,
        uncertain: &mut bool,
    ) -> Result<[u8; 32], &'static str> {
        let expected = file.info.ok_or("WINDOWS_IMAGE_ARCHIVE_UNAVAILABLE")?;
        let mut hash = ArchiveHasher::new(spec.size, spec.hash)?;
        let mut bytes = [0u8; CHUNK];
        loop {
            Self::checkpoint(deadline, cancelled)?;
            let observed = file.opened.info().map_err(|e| {
                *uncertain = true;
                e
            })?;
            let offset = file.opened.file()?.stream_position().map_err(|_| {
                *uncertain = true;
                "WINDOWS_IMAGE_ARCHIVE_CURSOR_UNKNOWN"
            })?;
            if observed != expected || offset != file.cursor {
                *uncertain = true;
                return Err("WINDOWS_IMAGE_ARCHIVE_CHANGED");
            }
            // A synchronous fixed-disk read is not an interruptible IO proof.
            // Its caller retains the whole owner until it returns/checked close.
            let count = file.opened.file()?.read(&mut bytes).map_err(|_| {
                *uncertain = true;
                "WINDOWS_IMAGE_ARCHIVE_READ_UNKNOWN"
            })?;
            let after = file.opened.file()?.stream_position().map_err(|_| {
                *uncertain = true;
                "WINDOWS_IMAGE_ARCHIVE_CURSOR_UNKNOWN"
            })?;
            if after
                != file
                    .cursor
                    .checked_add(count as u64)
                    .ok_or("WINDOWS_IMAGE_ARCHIVE_LENGTH_REJECTED")?
                || file.opened.info().map_err(|e| {
                    *uncertain = true;
                    e
                })? != expected
            {
                *uncertain = true;
                return Err("WINDOWS_IMAGE_ARCHIVE_CHANGED");
            }
            Self::checkpoint(deadline, cancelled)?;
            if count == 0 {
                return hash.finish_at_eof(after, deadline, cancelled);
            }
            hash.push(file.cursor, &bytes[..count], deadline, cancelled)?;
            file.cursor = after;
        }
    }
    pub fn retire(&mut self) -> bool {
        self.poisoned = true;
        if self.uncertain {
            return false;
        }
        let mut closed = true;
        for file in self.files.iter_mut().rev() {
            closed = file.opened.close() && closed;
        }
        closed = self.root.retire() && closed;
        // Keep all Info/hash/manifest diagnostics if another source close later
        // fails; erase nothing before the whole permission owner retires.
        closed
    }
}

#[cfg(test)]
mod native_tests {
    use super::super::super::super::retained::Retained;
    use super::*;
    use sha2::{Digest, Sha256};
    use std::{
        sync::{
            Arc,
            atomic::{AtomicUsize, Ordering},
        },
        time::Duration,
    };
    struct Fixture {
        authority: WindowsInputAuthority,
        lease: ImageArchiveLease,
        path: std::path::PathBuf,
        host: uuid::Uuid,
        root_id: Identity,
        immutable: Vec<u8>,
        drops: Arc<AtomicUsize>,
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            self.drops.fetch_add(1, Ordering::SeqCst);
        }
    }
    fn keep(owned: Box<Fixture>) {
        let _ = Box::leak(owned);
    }
    fn fixture() -> Fixture {
        crate::tools::windows_vm::input::native_source().expect("exact native candidate required");
        let path =
            std::env::temp_dir().join(format!("ctm-archive-component-{}", uuid::Uuid::new_v4()));
        std::fs::create_dir(&path).unwrap();
        std::fs::create_dir(path.join("assets")).unwrap();
        std::fs::write(path.join("assets/fixture.bin"), b"abc").unwrap();
        let host = uuid::Uuid::new_v4();
        let authority =
            WindowsInputAuthority::pin(host, "native-archive-component", &path).unwrap();
        let mut lease = RootLease::new();
        authority
            .acquire(host, "native-archive-component", &mut lease)
            .unwrap();
        let root_id = lease.root().unwrap();
        assert!(lease.retire());
        Fixture {
            authority,
            lease: ImageArchiveLease::new(),
            path,
            host,
            root_id,
            immutable: b"abc".to_vec(),
            drops: Arc::new(AtomicUsize::new(0)),
        }
    }
    fn prepare(owned: &mut Fixture) {
        let digest = format!("{:x}", Sha256::digest(b"abc"));
        // Test data does not enter APPROVED or any actual HCS caller.
        let digest: &'static str = Box::leak(digest.into_boxed_str());
        let entry = ArchiveSpec {
            leaf: "fixture.bin",
            size: 3,
            hash: digest,
        };
        owned
            .lease
            .prepare_entries(
                &owned.authority,
                owned.host,
                "native-archive-component",
                "assets",
                owned.root_id,
                &[entry],
                Instant::now() + Duration::from_secs(5),
                &|| false,
            )
            .unwrap();
    }
    #[test]
    fn native_component_relative_full_fid_cursor_hash_rejects_new_writer() {
        let mut held = Retained::new(fixture(), keep);
        prepare(held.get_mut());
        let owned = held.get();
        let file = &owned.lease.files[0];
        assert_eq!(file.cursor, 3);
        assert_eq!(file.hash, Some(Sha256::digest(b"abc").into()));
        assert!(file.info.unwrap().identity.id != [0; 16]);
        assert!(
            std::fs::OpenOptions::new()
                .write(true)
                .open(owned.path.join("assets/fixture.bin"))
                .is_err()
        );
        assert!(held.get_mut().lease.retire());
        held.retire_known();
    }
    #[test]
    fn native_component_unknown_close_retains_whole_fixture_without_permission_claim() {
        let mut held = Retained::new(fixture(), keep);
        prepare(held.get_mut());
        let drops = held.get().drops.clone();
        assert_eq!(held.get().immutable, b"abc");
        held.get_mut().lease.files[0]
            .opened
            .simulate_close_unknown();
        assert!(!held.get_mut().lease.retire());
        assert!(held.get().lease.files[0].opened.held().1);
        drop(held);
        assert_eq!(drops.load(Ordering::SeqCst), 0);
    }
    #[test]
    fn native_component_panic_preserves_actual_archive_handle_fixture() {
        let drops = Arc::new(AtomicUsize::new(0));
        let observed = drops.clone();
        let result = std::panic::catch_unwind(move || {
            let mut value = fixture();
            value.drops = observed;
            let mut held = Retained::new(value, keep);
            prepare(held.get_mut());
            panic!("controlled native archive fixture panic");
        });
        assert!(result.is_err());
        assert_eq!(drops.load(Ordering::SeqCst), 0);
    }
}
