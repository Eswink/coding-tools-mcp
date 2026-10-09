//! Independent execution authority; never a snapshot target or RootWork identity.
use super::{
    nt::{self, Identity, Opened},
    path,
};
use std::{os::windows::ffi::OsStrExt, path::Path};
use uuid::Uuid;
pub(crate) struct WindowsInputAuthority {
    host: Uuid,
    profile: String,
    drive: u8,
    parts: Vec<String>,
    anchors: Vec<Opened>,
    ids: Vec<Identity>,
}
pub(super) struct RootLease {
    pub handles: Vec<Opened>,
}
impl RootLease {
    pub fn new() -> Self {
        Self {
            handles: Vec::new(),
        }
    }
    pub fn retire(&mut self) -> bool {
        let mut closed = true;
        for handle in self.handles.iter_mut().rev() {
            closed = handle.close() && closed;
        }
        closed
    }
    pub fn root(&self) -> Result<Identity, &'static str> {
        Ok(self
            .handles
            .last()
            .ok_or("WINDOWS_INPUT_ROOT_UNAVAILABLE")?
            .info()?
            .identity)
    }
}
impl WindowsInputAuthority {
    pub(crate) fn pin(host: Uuid, profile: &str, root: &Path) -> Result<Self, &'static str> {
        let wide: Vec<u16> = root.as_os_str().encode_wide().collect();
        let mut text = String::from_utf16(&wide).map_err(|_| "WINDOWS_INPUT_ROOT_REJECTED")?;
        if let Some(rest) = text.strip_prefix("\\\\?\\") {
            text = rest.to_owned();
        }
        let bytes = text.as_bytes();
        if bytes.len() < 4 || bytes[1] != b':' || bytes[2] != b'\\' {
            return Err("WINDOWS_INPUT_ROOT_REJECTED");
        }
        let drive = bytes[0];
        let parts = path::components(&text[3..])?
            .into_iter()
            .map(str::to_owned)
            .collect::<Vec<_>>();
        let mut lease = RootLease::new();
        let opened = (|| {
            lease.handles.push(nt::open_drive(drive, true)?);
            nt::verify_volume_root(&lease.handles[0])?;
            for part in &parts {
                let next = nt::open(
                    lease
                        .handles
                        .last()
                        .ok_or("WINDOWS_INPUT_ROOT_UNAVAILABLE")?,
                    part,
                    true,
                    true,
                )?;
                lease.handles.push(next);
            }
            let ids = lease
                .handles
                .iter()
                .map(|h| {
                    let info = h.info()?;
                    if !info.directory {
                        return Err("WINDOWS_INPUT_ROOT_REJECTED");
                    }
                    Ok(info.identity)
                })
                .collect::<Result<Vec<_>, &'static str>>()?;
            Ok(ids)
        })();
        match opened {
            Ok(ids) => Ok(Self {
                host,
                profile: profile.into(),
                drive,
                parts,
                anchors: lease.handles,
                ids,
            }),
            Err(error) => {
                if !lease.retire() {
                    return Err("WINDOWS_INPUT_ROOT_CLOSE_UNKNOWN");
                }
                Err(error)
            }
        }
    }
    pub(super) fn acquire(
        &self,
        host: Uuid,
        profile: &str,
        lease: &mut RootLease,
    ) -> Result<(), &'static str> {
        if host != self.host
            || profile != self.profile
            || !lease.handles.is_empty()
            || self.anchors.len() != self.ids.len()
        {
            return Err("WINDOWS_INPUT_ROOT_AUTHORITY_REJECTED");
        }
        // Retained originals prevent ID reuse; check them as well as each reopened name.
        for (anchor, id) in self.anchors.iter().zip(&self.ids) {
            if anchor.info()?.identity != *id {
                return Err("WINDOWS_INPUT_ROOT_CHANGED");
            }
        }
        lease.handles.push(nt::open_drive(self.drive, false)?);
        nt::verify_volume_root(&lease.handles[0])?;
        for index in 0..self.ids.len() {
            let info = lease.handles[index].info()?;
            if !info.directory || info.identity != self.ids[index] {
                return Err("WINDOWS_INPUT_ROOT_CHANGED");
            }
            if let Some(part) = self.parts.get(index) {
                let next = nt::open(
                    lease
                        .handles
                        .last()
                        .ok_or("WINDOWS_INPUT_ROOT_UNAVAILABLE")?,
                    part,
                    true,
                    false,
                )?;
                lease.handles.push(next);
            }
        }
        Ok(())
    }
}
