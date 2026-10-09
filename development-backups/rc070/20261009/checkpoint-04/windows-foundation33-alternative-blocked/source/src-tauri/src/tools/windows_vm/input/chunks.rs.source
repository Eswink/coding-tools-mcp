//! New bounded byte owner. These bytes and hashes are data, never permission.
use sha2::{Digest, Sha256};
pub(super) const MAXIMUM: usize = 1_048_576;
pub(super) const CHUNK: usize = 32_768;
pub(super) struct ImmutableChunks {
    chunks: Vec<Vec<u8>>,
    size: usize,
    sealed: bool,
}
impl ImmutableChunks {
    pub fn new() -> Self { Self { chunks: Vec::new(), size: 0, sealed: false } }
    pub fn append(&mut self, bytes: &[u8]) -> Result<(), &'static str> {
        if self.sealed || bytes.is_empty() || bytes.len() > CHUNK
            || self.size.checked_add(bytes.len()).is_none_or(|n| n > MAXIMUM)
        { return Err("WINDOWS_INPUT_CHUNK_REJECTED"); }
        self.chunks.push(bytes.to_vec());
        self.size += bytes.len();
        Ok(())
    }
    pub fn seal(&mut self) { self.sealed = true; }
    pub fn size(&self) -> usize { self.size }
    pub fn digest(&self) -> Result<[u8; 32], &'static str> {
        if !self.sealed { return Err("WINDOWS_INPUT_BYTES_UNSEALED"); }
        let mut hash = Sha256::new();
        for chunk in &self.chunks { hash.update(chunk); }
        Ok(hash.finalize().into())
    }
    pub fn detached<F: Fn() -> bool>(&self, stop: &F) -> Result<Self, &'static str> {
        if !self.sealed || stop() { return Err("WINDOWS_INPUT_COPY_REJECTED"); }
        let mut owned = Self::new();
        for chunk in &self.chunks {
            if stop() { return Err("WINDOWS_INPUT_CANCELLED"); }
            owned.append(chunk)?;
        }
        if stop() { return Err("WINDOWS_INPUT_CANCELLED"); }
        owned.seal();
        if owned.size != self.size || owned.digest()? != self.digest()? {
            return Err("WINDOWS_INPUT_COPY_REJECTED");
        }
        Ok(owned)
    }
    pub fn clear_after_checked_close(&mut self) {
        self.chunks.clear(); self.size = 0; self.sealed = false;
    }
}
