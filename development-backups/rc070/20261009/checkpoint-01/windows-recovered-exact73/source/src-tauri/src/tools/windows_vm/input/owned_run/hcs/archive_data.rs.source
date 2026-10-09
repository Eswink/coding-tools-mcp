//! Fixed image archive data and bounded streaming verification, never permission.
use sha2::{Digest, Sha256};
use std::time::Instant;

pub(super) const CHUNK: usize = 65_536;
pub(super) struct ArchiveSpec {
    pub leaf: &'static str,
    pub size: u64,
    pub hash: &'static str,
}
// Same approved OCI inputs as services/windows-vm-broker/owner_windows.go.
// A matching read stream is NOT authority for imported boot files or a VM.
pub(super) const APPROVED: [ArchiveSpec; 2] = [
    ArchiveSpec {
        leaf: "layer0.gz",
        size: 1_482_371_926,
        hash: "97e96e9cbeb16024139f78dc6ed542a7cf572ac80d8cea50a3308368094c4574",
    },
    ArchiveSpec {
        leaf: "layer1.gz",
        size: 914_397_517,
        hash: "67f39c55a3f42bc0569099cebb32cef6688837ca694dfacaa00053810cb810d6",
    },
];

pub(super) struct ArchiveHasher {
    expected_size: u64,
    expected_hash: [u8; 32],
    cursor: u64,
    hash: Sha256,
    denied: Option<&'static str>,
    finished: bool,
}
impl ArchiveHasher {
    pub fn new(size: u64, hash: &str) -> Result<Self, &'static str> {
        if size == 0
            || hash.len() != 64
            || !hash.bytes().all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f'))
        {
            return Err("WINDOWS_IMAGE_ARCHIVE_MANIFEST_REJECTED");
        }
        let mut expected_hash = [0; 32];
        for (index, byte) in expected_hash.iter_mut().enumerate() {
            *byte = u8::from_str_radix(&hash[index * 2..index * 2 + 2], 16)
                .map_err(|_| "WINDOWS_IMAGE_ARCHIVE_MANIFEST_REJECTED")?;
        }
        Ok(Self {
            expected_size: size,
            expected_hash,
            cursor: 0,
            hash: Sha256::new(),
            denied: None,
            finished: false,
        })
    }
    fn deny<T>(&mut self, error: &'static str) -> Result<T, &'static str> {
        self.denied = Some(error);
        Err(error)
    }
    fn checkpoint<F: Fn() -> bool>(
        &mut self,
        deadline: Instant,
        cancelled: &F,
    ) -> Result<(), &'static str> {
        if let Some(error) = self.denied {
            return Err(error);
        }
        if self.finished {
            return self.deny("WINDOWS_IMAGE_ARCHIVE_ALREADY_FINISHED");
        }
        if cancelled() || Instant::now() >= deadline {
            return self.deny("WINDOWS_IMAGE_ARCHIVE_CANCELLED");
        }
        Ok(())
    }
    pub fn push<F: Fn() -> bool>(
        &mut self,
        offset: u64,
        bytes: &[u8],
        deadline: Instant,
        cancelled: &F,
    ) -> Result<(), &'static str> {
        self.checkpoint(deadline, cancelled)?;
        if offset != self.cursor || bytes.is_empty() || bytes.len() > CHUNK {
            return self.deny("WINDOWS_IMAGE_ARCHIVE_CHUNK_REJECTED");
        }
        let Some(end) = self.cursor.checked_add(bytes.len() as u64) else {
            return self.deny("WINDOWS_IMAGE_ARCHIVE_LENGTH_REJECTED");
        };
        if end > self.expected_size {
            return self.deny("WINDOWS_IMAGE_ARCHIVE_LENGTH_REJECTED");
        }
        self.hash.update(bytes);
        self.cursor = end;
        self.checkpoint(deadline, cancelled)
    }
    /// Called only after the native caller observes actual read EOF. The return
    /// is data, not a boot, immutable-file, VM retirement or output capability.
    pub fn finish_at_eof<F: Fn() -> bool>(
        &mut self,
        actual_offset: u64,
        deadline: Instant,
        cancelled: &F,
    ) -> Result<[u8; 32], &'static str> {
        self.checkpoint(deadline, cancelled)?;
        if actual_offset != self.cursor || self.cursor != self.expected_size {
            return self.deny("WINDOWS_IMAGE_ARCHIVE_LENGTH_REJECTED");
        }
        let hash: [u8; 32] = self.hash.clone().finalize().into();
        if hash != self.expected_hash {
            return self.deny("WINDOWS_IMAGE_ARCHIVE_HASH_REJECTED");
        }
        self.checkpoint(deadline, cancelled)?;
        self.finished = true;
        Ok(hash)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{cell::Cell, time::Duration};
    fn future() -> Instant {
        Instant::now() + Duration::from_secs(5)
    }
    fn hash(data: &[u8]) -> String {
        format!("{:x}", Sha256::digest(data))
    }
    #[test]
    fn fixed_manifest_preserves_exact_pair_order_and_sizes() {
        assert_eq!(APPROVED[0].leaf, "layer0.gz");
        assert_eq!(APPROVED[1].leaf, "layer1.gz");
        assert_eq!(APPROVED[0].size + APPROVED[1].size, 2_396_769_443);
        for entry in &APPROVED {
            assert!(ArchiveHasher::new(entry.size, entry.hash).is_ok());
        }
    }
    #[test]
    fn exact_chunks_hash_and_eof_are_accepted_once_as_data() {
        let bytes = vec![19; CHUNK + 17];
        let mut state = ArchiveHasher::new(bytes.len() as u64, &hash(&bytes)).unwrap();
        state.push(0, &bytes[..CHUNK], future(), &|| false).unwrap();
        state
            .push(CHUNK as u64, &bytes[CHUNK..], future(), &|| false)
            .unwrap();
        assert_eq!(
            state.finish_at_eof(bytes.len() as u64, future(), &|| false),
            Ok(Sha256::digest(&bytes).into())
        );
        assert!(
            state
                .finish_at_eof(bytes.len() as u64, future(), &|| false)
                .is_err()
        );
        assert!(
            state
                .push(bytes.len() as u64, b"x", future(), &|| false)
                .is_err()
        );
    }
    #[test]
    fn short_eof_wrong_hash_and_wrong_actual_cursor_reject_stickily() {
        for mode in 0..3 {
            let mut state = ArchiveHasher::new(3, &hash(b"abc")).unwrap();
            let bytes = if mode == 0 {
                &b"ab"[..]
            } else if mode == 1 {
                &b"abd"[..]
            } else {
                &b"abc"[..]
            };
            state.push(0, bytes, future(), &|| false).unwrap();
            let offset = if mode == 2 { 2 } else { bytes.len() as u64 };
            assert!(state.finish_at_eof(offset, future(), &|| false).is_err());
            assert!(state.finish_at_eof(3, future(), &|| false).is_err());
        }
    }
    #[test]
    fn noncontiguous_zero_oversize_and_beyond_manifest_chunks_reject() {
        for (offset, data) in [
            (1, vec![1]),
            (0, vec![]),
            (0, vec![1; CHUNK + 1]),
            (0, vec![1; 4]),
        ] {
            let mut state = ArchiveHasher::new(3, &hash(b"abc")).unwrap();
            assert!(state.push(offset, &data, future(), &|| false).is_err());
            assert!(state.push(0, b"abc", future(), &|| false).is_err());
        }
    }
    #[test]
    fn cancelled_expired_and_cancel_during_checkpoint_never_finish() {
        for mode in 0..3 {
            let mut state = ArchiveHasher::new(3, &hash(b"abc")).unwrap();
            let calls = Cell::new(0);
            let cancel = || {
                calls.set(calls.get() + 1);
                mode == 0 || (mode == 2 && calls.get() > 1)
            };
            let deadline = if mode == 1 { Instant::now() } else { future() };
            assert!(state.push(0, b"abc", deadline, &cancel).is_err());
            assert!(state.finish_at_eof(3, future(), &|| false).is_err());
        }
    }
    #[test]
    fn malformed_manifest_rejects_without_native_resource() {
        for (size, digest) in [
            (0, hash(b"a")),
            (1, "a".repeat(63)),
            (1, "A".repeat(64)),
            (1, "z".repeat(64)),
        ] {
            assert!(ArchiveHasher::new(size, &digest).is_err());
        }
    }
}
