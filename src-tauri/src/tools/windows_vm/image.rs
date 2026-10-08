//! Retained image identity. Read sharing does not prove ancestor or DLL authority.
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::fs::{File, OpenOptions};
use std::io::{Read, Seek, SeekFrom};
use std::mem::{size_of, ManuallyDrop};
use std::os::windows::ffi::OsStrExt;
use std::os::windows::fs::OpenOptionsExt;
use std::os::windows::io::{AsRawHandle, FromRawHandle, IntoRawHandle};
use std::path::Path;
use std::time::Instant;
use windows::Win32::Foundation::{
    CloseHandle, GetLastError, SetHandleInformation, HANDLE, HANDLE_FLAGS, HANDLE_FLAG_INHERIT,
};
use windows::Win32::Storage::FileSystem::{FileIdInfo, GetFileInformationByHandleEx, FILE_ID_INFO};
use windows::Win32::System::SystemInformation::{GetSystemDirectoryW, GetWindowsDirectoryW};

const MAX_IMAGE: u64 = 64 * 1024 * 1024;
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub(super) struct ImageIdentity {
    pub volume: u64,
    pub file_id: [u8; 16],
    pub size: u64,
    pub sha256: String,
}
#[derive(Debug)]
pub(super) struct ImageFailure {
    pub message: String,
    pub resources_retired: bool,
}
pub(super) fn raw_error(error: &windows::core::Error) -> u32 {
    let value = error.code().0 as u32;
    if value & 0xffff0000 == 0x80070000 {
        value & 0xffff
    } else {
        value
    }
}
pub(super) fn win_error(op: &str, error: windows::core::Error) -> String {
    format!("{op}: raw={} ({error})", raw_error(&error))
}
pub(super) fn close_file(file: File) -> Result<(), String> {
    unsafe { CloseHandle(HANDLE(file.into_raw_handle())) }.map_err(|e| win_error("CloseHandle", e))
}
pub(super) fn fingerprint(handle: HANDLE) -> Result<ImageIdentity, String> {
    if handle.is_invalid() {
        return Err("invalid image handle".into());
    }
    let mut id = FILE_ID_INFO::default();
    unsafe {
        GetFileInformationByHandleEx(
            handle,
            FileIdInfo,
            (&mut id as *mut FILE_ID_INFO).cast(),
            size_of::<FILE_ID_INFO>() as u32,
        )
    }
    .map_err(|e| win_error("FileIdInfo", e))?;
    // Borrow the actual handle without transferring its closure to this File.
    let mut file = ManuallyDrop::new(unsafe { File::from_raw_handle(handle.0) });
    let size = file
        .metadata()
        .map_err(|e| format!("image metadata: {e:?}"))?
        .len();
    if size == 0 || size > MAX_IMAGE {
        return Err("image length outside 1..64MiB".into());
    }
    file.seek(SeekFrom::Start(0))
        .map_err(|e| format!("image seek: {e:?}"))?;
    let mut digest = Sha256::new();
    let mut total = 0u64;
    let mut bytes = [0u8; 16384];
    loop {
        let n = file
            .read(&mut bytes)
            .map_err(|e| format!("image read: {e:?}"))?;
        if n == 0 {
            break;
        }
        total = total.checked_add(n as u64).ok_or("image length overflow")?;
        if total > MAX_IMAGE || total > size {
            return Err("image grew while hashing".into());
        }
        digest.update(&bytes[..n]);
    }
    if total != size {
        return Err("image changed while hashing".into());
    }
    Ok(ImageIdentity {
        volume: id.VolumeSerialNumber,
        file_id: id.FileId.Identifier,
        size,
        sha256: format!("{:x}", digest.finalize()),
    })
}
pub(super) struct RetainedImage {
    file: Option<File>,
    pub identity: ImageIdentity,
}
impl RetainedImage {
    pub fn open(path: &Path, expected_sha256: &str) -> Result<Self, ImageFailure> {
        let file = OpenOptions::new()
            .read(true)
            .share_mode(1)
            .open(path)
            .map_err(|e| ImageFailure {
                message: format!("image open: {e:?}"),
                resources_retired: true,
            })?;
        let handle = HANDLE(file.as_raw_handle());
        let checked: Result<ImageIdentity, String> = (|| {
            unsafe { SetHandleInformation(handle, HANDLE_FLAG_INHERIT.0, HANDLE_FLAGS(0)) }
                .map_err(|e| win_error("image inheritance", e))?;
            let identity = fingerprint(handle)?;
            if identity.sha256 != expected_sha256 {
                return Err("broker manifest hash mismatch".into());
            }
            Ok(identity)
        })();
        match checked {
            Ok(identity) => Ok(Self {
                file: Some(file),
                identity,
            }),
            Err(mut message) => {
                let closed = close_file(file);
                if let Err(error) = &closed {
                    message.push_str(&format!("; {error}"));
                }
                Err(ImageFailure {
                    message,
                    resources_retired: closed.is_ok(),
                })
            }
        }
    }
    pub fn close(&mut self) -> Result<(), String> {
        self.file.take().map(close_file).unwrap_or(Ok(()))
    }
}
pub(super) struct Handle(pub HANDLE);
impl Handle {
    pub fn empty() -> Self {
        Self(HANDLE::default())
    }
    pub fn close(&mut self) -> Result<(), String> {
        let raw = std::mem::take(&mut self.0);
        if raw.is_invalid() {
            return Ok(());
        }
        unsafe { CloseHandle(raw) }.map_err(|e| win_error("CloseHandle", e))
    }
    pub fn into_file(mut self) -> File {
        let raw = std::mem::take(&mut self.0);
        assert!(!raw.is_invalid());
        unsafe { File::from_raw_handle(raw.0) }
    }
}
impl Drop for Handle {
    fn drop(&mut self) {
        let _ = self.close();
    }
}

pub(super) fn wide(path: &Path) -> Result<Vec<u16>, String> {
    let mut value: Vec<_> = path.as_os_str().encode_wide().collect();
    if !path.is_absolute() || value.is_empty() || value.len() > 32760 || value.contains(&0) {
        return Err("invalid absolute launch path".into());
    }
    value.push(0);
    Ok(value)
}
pub(super) fn quoted(value: &[u16], out: &mut Vec<u16>) {
    out.push(34);
    let mut slashes = 0;
    for &unit in &value[..value.len() - 1] {
        if unit == 92 {
            slashes += 1;
            continue;
        }
        out.extend(std::iter::repeat_n(
            92,
            if unit == 34 { slashes * 2 + 1 } else { slashes },
        ));
        out.push(unit);
        slashes = 0;
    }
    out.extend(std::iter::repeat_n(92, slashes * 2));
    out.push(34);
}
pub(super) fn environment(temp: &[u16]) -> Result<Vec<u16>, String> {
    let mut windows = [0u16; 32768];
    let mut system = [0u16; 32768];
    let wn = unsafe { GetWindowsDirectoryW(Some(&mut windows)) } as usize;
    let windows_error = if wn == 0 {
        unsafe { GetLastError().0 }
    } else {
        0
    };
    let sn = unsafe { GetSystemDirectoryW(Some(&mut system)) } as usize;
    let system_error = if sn == 0 {
        unsafe { GetLastError().0 }
    } else {
        0
    };
    if wn == 0
        || wn >= windows.len()
        || sn == 0
        || sn >= system.len()
        || windows[wn] != 0
        || system[sn] != 0
    {
        return Err(
            format!("system-directory lookup failed: Windows raw={windows_error}, System raw={system_error}")
        );
    }
    let mut result = Vec::new();
    for (name, value) in [
        ("PATH=", &system[..sn]),
        ("SystemRoot=", &windows[..wn]),
        ("TEMP=", &temp[..temp.len() - 1]),
        ("TMP=", &temp[..temp.len() - 1]),
        ("WINDIR=", &windows[..wn]),
    ] {
        if value.contains(&0) {
            return Err("embedded environment NUL".into());
        }
        result.extend(name.encode_utf16());
        result.extend_from_slice(value);
        result.push(0);
    }
    result.push(0);
    if result.len() > 32767 {
        return Err("environment length bound".into());
    }
    Ok(result)
}

impl super::launch::LaunchReport {
    pub(super) fn observe_admission_deadline(&mut self, now: Instant, deadline: Instant) -> bool {
        if self.first_continue_succeeded || self.admission_timed_out || now < deadline {
            return false;
        }
        self.admission_timed_out = true;
        let late = now.duration_since(deadline).as_millis();
        self.admission_timeout_late_ms = Some(late.min(u64::MAX as u128) as u64);
        true
    }
}
