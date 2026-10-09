//! Actual input handles, registered before observation; no path as permission.
use super::{nt::{self, Identity, Info, Opened}, path, root::{RootLease, WindowsInputAuthority}};
use std::io::{Read, Seek};
pub(super) struct InputHandles {
    root: RootLease,
    observations: Vec<Info>,
    file: Option<Opened>,
    info: Option<Info>,
    root_id: Option<Identity>,
    cursor: u64,
    uncertain: bool,
}
impl InputHandles {
    pub fn new() -> Self {
        Self { root: RootLease::new(), observations: Vec::new(), file: None,
            info: None, root_id: None, cursor: 0, uncertain: false }
    }
    pub fn open(&mut self, authority: &WindowsInputAuthority, host: uuid::Uuid,
        profile: &str, relative: &str) -> Result<(), &'static str> {
        if !self.root.handles.is_empty() || self.file.is_some() {
            return Err("WINDOWS_INPUT_LEASE_REUSED");
        }
        let parts = path::components(relative)?;
        authority.acquire(host, profile, &mut self.root)?;
        let root = self.root.root()?;
        self.root_id = Some(root);
        for part in &parts[..parts.len()-1] {
            let parent = self.root.handles.last().ok_or("WINDOWS_INPUT_ROOT_UNAVAILABLE")?;
            let opened = nt::open(parent, part, true, false)?;
            self.root.handles.push(opened);
            let info = self.root.handles.last().ok_or("WINDOWS_INPUT_ROOT_UNAVAILABLE")?.info()?;
            if !info.directory || info.identity.volume != root.volume {
                return Err("WINDOWS_INPUT_PARENT_REJECTED");
            }
        }
        self.observations = self.root.handles.iter().map(Opened::info)
            .collect::<Result<Vec<_>, _>>()?;
        let parent = self.root.handles.last().ok_or("WINDOWS_INPUT_ROOT_UNAVAILABLE")?;
        self.file = Some(nt::open(parent, parts.last().ok_or("WINDOWS_INPUT_PATH_REJECTED")?, false, false)?);
        let info = self.file.as_ref().ok_or("WINDOWS_INPUT_HANDLE_UNAVAILABLE")?.info()?;
        self.info = Some(info);
        if info.directory || info.links != 1 || info.identity.volume != root.volume
            || info.size > super::chunks::MAXIMUM as u64 {
            return Err("WINDOWS_INPUT_FILE_REJECTED");
        }
        self.revalidate()
    }
    pub fn summary(&self) -> Result<(Identity, Info), &'static str> {
        Ok((self.root_id.ok_or("WINDOWS_INPUT_ROOT_UNAVAILABLE")?,
            self.info.ok_or("WINDOWS_INPUT_HANDLE_UNAVAILABLE")?))
    }
    pub fn revalidate(&mut self) -> Result<(), &'static str> {
        let result = (|| {
            if self.uncertain || self.observations.len() != self.root.handles.len() {
                return Err("WINDOWS_INPUT_STATE_UNKNOWN");
            }
            for (opened, expected) in self.root.handles.iter().zip(&self.observations) {
                if opened.info()? != *expected { return Err("WINDOWS_INPUT_PARENT_CHANGED"); }
            }
            let expected = self.info.ok_or("WINDOWS_INPUT_HANDLE_UNAVAILABLE")?;
            let file = self.file.as_mut().ok_or("WINDOWS_INPUT_HANDLE_UNAVAILABLE")?;
            if file.info()? != expected || file.file()?.stream_position()
                .map_err(|_| "WINDOWS_INPUT_CURSOR_UNKNOWN")? != self.cursor {
                return Err("WINDOWS_INPUT_FILE_CHANGED");
            }
            Ok(())
        })();
        if result.is_err() { self.uncertain = true; }
        result
    }
    pub fn read_next(&mut self, bytes: &mut [u8]) -> Result<usize, &'static str> {
        self.revalidate()?;
        let result = (|| {
            let n = self.file.as_mut().ok_or("WINDOWS_INPUT_HANDLE_UNAVAILABLE")?.file()?
                .read(bytes).map_err(|_| "WINDOWS_INPUT_READ_UNKNOWN")?;
            self.cursor = self.cursor.checked_add(n as u64).ok_or("WINDOWS_INPUT_SIZE_REJECTED")?;
            if self.cursor > self.info.ok_or("WINDOWS_INPUT_HANDLE_UNAVAILABLE")?.size {
                return Err("WINDOWS_INPUT_SIZE_CHANGED");
            }
            self.revalidate()?;
            Ok(n)
        })();
        if result.is_err() { self.uncertain = true; }
        result
    }
    pub fn retire(&mut self) -> bool {
        let file_closed = self.file.as_mut().is_none_or(Opened::close);
        let root_closed = self.root.retire();
        file_closed && root_closed && !self.uncertain
    }
    #[cfg(test)]
    pub fn simulate_close_unknown(&mut self) {
        if let Some(file) = self.file.as_mut() { file.simulate_close_unknown(); }
        self.uncertain = true;
    }
    #[cfg(test)]
    pub fn recovery_evidence(&self) -> (usize, bool) {
        let root = self.root.handles.iter().filter(|h| h.held().0).count();
        let file = self.file.as_ref().is_some_and(|h| h.held().0) as usize;
        (root + file, self.uncertain)
    }
}
