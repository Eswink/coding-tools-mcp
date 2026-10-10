//! New actual input lease; callers install whole Retained owner before prepare.
use super::{chunks::{ImmutableChunks, CHUNK}, nt::Identity, owner::InputHandles,
    root::WindowsInputAuthority, transfer::{InputTransfer, RunBinding}};
use std::time::Instant;
pub(super) struct InputLease {
    handles: InputHandles,
    original: ImmutableChunks,
    relative: Option<String>,
    poisoned: bool,
    prepared: bool,
    retired: bool,
    host: Option<uuid::Uuid>,
    profile: Option<String>,
}
impl InputLease {
    pub fn new() -> Self { Self { handles: InputHandles::new(), original: ImmutableChunks::new(),
        relative: None, poisoned: false, prepared: false, retired: false,
        host: None, profile: None } }
    fn checkpoint<F: Fn() -> bool>(deadline: Instant, cancelled: &F) -> Result<(), &'static str> {
        if cancelled() || Instant::now() >= deadline { Err("WINDOWS_INPUT_CANCELLED") } else { Ok(()) }
    }
    pub fn prepare<F: Fn() -> bool>(&mut self, authority: &WindowsInputAuthority,
        host: uuid::Uuid, profile: &str, relative: &str, deadline: Instant,
        cancelled: &F) -> Result<(), &'static str> {
        if self.poisoned || self.prepared || self.retired { return Err("WINDOWS_INPUT_LEASE_REUSED"); }
        let result = (|| {
            Self::checkpoint(deadline, cancelled)?;
            self.handles.open(authority, host, profile, relative)?;
            self.relative = Some(relative.into());
            self.host = Some(host); self.profile = Some(profile.into());
            let mut bytes = [0u8; CHUNK];
            loop {
                Self::checkpoint(deadline, cancelled)?;
                let count = self.handles.read_next(&mut bytes)?;
                Self::checkpoint(deadline, cancelled)?;
                if count == 0 { break; }
                self.original.append(&bytes[..count])?;
            }
            if self.original.size() as u64 != self.handles.summary()?.1.size {
                return Err("WINDOWS_INPUT_SIZE_CHANGED");
            }
            self.original.seal(); self.prepared = true;
            self.revalidate(deadline, cancelled)
        })();
        if result.is_err() { self.poisoned = true; }
        result
    }
    pub fn summary(&self) -> Result<(Identity, u64, [u8; 32]), &'static str> {
        if !self.prepared || self.poisoned || self.retired { return Err("WINDOWS_INPUT_LEASE_UNAVAILABLE"); }
        Ok((self.handles.summary()?.0, self.original.size() as u64, self.original.digest()?))
    }
    pub fn revalidate<F: Fn() -> bool>(&mut self, deadline: Instant,
        cancelled: &F) -> Result<(), &'static str> {
        Self::checkpoint(deadline, cancelled)?;
        if !self.prepared || self.poisoned || self.retired { return Err("WINDOWS_INPUT_LEASE_UNAVAILABLE"); }
        let result = self.handles.revalidate();
        if result.is_err() { self.poisoned = true; }
        result?;
        Self::checkpoint(deadline, cancelled)
    }
    pub fn transfer<F: Fn() -> bool>(&mut self, binding: RunBinding, deadline: Instant,
        cancelled: &F) -> Result<InputTransfer, &'static str> {
        self.revalidate(deadline, cancelled)?;
        if self.relative.as_deref() != Some(binding.input_relative.as_str())
            || self.host.map(|host| host.to_string()).as_deref() != Some(binding.host.as_str())
            || self.profile.as_deref() != Some(binding.profile.as_str()) {
            return Err("WINDOWS_INPUT_TRANSFER_BINDING_REJECTED");
        }
        let stop = || cancelled() || Instant::now() >= deadline;
        let detached = self.original.detached(&stop)?;
        self.revalidate(deadline, cancelled)?;
        InputTransfer::new(binding, detached)
    }
    pub fn retire(&mut self) -> bool {
        if self.retired { return true; }
        if self.handles.retire() {
            self.retired = true;
            self.original.clear_after_checked_close();
            true
        } else { false }
    }
    #[cfg(test)]
    pub fn simulate_close_unknown(&mut self) { self.handles.simulate_close_unknown(); }
    #[cfg(test)]
    pub fn recovery_evidence(&self) -> (usize, bool, bool) {
        let (held, uncertain) = self.handles.recovery_evidence();
        (held, uncertain, self.original.digest().is_ok())
    }
}
