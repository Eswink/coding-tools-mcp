//! User-mode Windows native opens. Each child name is one validated component.
//! NtCreateFile / OBJECT_ATTRIBUTES layout follows Microsoft winternl.h.
use std::{
    ffi::c_void,
    fs::File,
    mem::size_of,
    os::windows::io::{AsRawHandle, FromRawHandle, IntoRawHandle},
};
type Handle = *mut c_void;
#[repr(C)]
struct UnicodeString {
    length: u16,
    maximum_length: u16,
    buffer: *mut u16,
}
#[repr(C)]
struct ObjectAttributes {
    length: u32,
    root: Handle,
    name: *mut UnicodeString,
    attributes: u32,
    security: *mut c_void,
    quality: *mut c_void,
}
#[repr(C)]
struct IoStatus {
    status: usize,
    information: usize,
}
#[repr(C)]
#[derive(Default)]
struct FileId {
    volume: u64,
    id: [u8; 16],
}
#[repr(C)]
#[derive(Default)]
struct Standard {
    allocation: i64,
    end: i64,
    links: u32,
    deleted: u8,
    directory: u8,
}
#[repr(C)]
#[derive(Default)]
struct AttributeTag {
    attributes: u32,
    tag: u32,
}
#[link(name = "ntdll")]
unsafe extern "system" {
    fn NtCreateFile(
        handle: *mut Handle,
        access: u32,
        attrs: *mut ObjectAttributes,
        status: *mut IoStatus,
        allocation: *const i64,
        file_attributes: u32,
        share: u32,
        disposition: u32,
        options: u32,
        ea: *const c_void,
        ea_len: u32,
    ) -> i32;
}
#[link(name = "kernel32")]
unsafe extern "system" {
    fn GetFileInformationByHandleEx(
        handle: Handle,
        class: i32,
        info: *mut c_void,
        size: u32,
    ) -> i32;
    fn GetFileType(handle: Handle) -> u32;
    fn GetDriveTypeW(root: *const u16) -> u32;
    fn CloseHandle(handle: Handle) -> i32;
    fn CreateFileW(
        name: *const u16,
        access: u32,
        share: u32,
        security: *const c_void,
        disposition: u32,
        flags: u32,
        template: Handle,
    ) -> Handle;
    fn GetFinalPathNameByHandleW(handle: Handle, path: *mut u16, count: u32, flags: u32) -> u32;
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(super) struct Identity {
    pub volume: u64,
    pub id: [u8; 16],
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(super) struct Info {
    pub identity: Identity,
    pub size: u64,
    pub directory: bool,
    pub links: u32,
}
pub(super) struct Opened {
    file: Option<File>,
    uncertain: bool,
    uncertain_handle: Option<usize>,
}
impl Opened {
    pub fn file(&mut self) -> Result<&mut File, &'static str> {
        self.file.as_mut().ok_or("WINDOWS_INPUT_HANDLE_UNAVAILABLE")
    }
    pub fn info(&self) -> Result<Info, &'static str> {
        let handle = self
            .file
            .as_ref()
            .ok_or("WINDOWS_INPUT_HANDLE_UNAVAILABLE")?
            .as_raw_handle();
        if unsafe { GetFileType(handle) } != 1 {
            return Err("WINDOWS_INPUT_NOT_DISK_FILE");
        }
        let mut id = FileId::default();
        let mut standard = Standard::default();
        let mut tag = AttributeTag::default();
        for (class, ptr, size) in [
            (18, (&mut id as *mut FileId).cast(), size_of::<FileId>()),
            (
                1,
                (&mut standard as *mut Standard).cast(),
                size_of::<Standard>(),
            ),
            (
                9,
                (&mut tag as *mut AttributeTag).cast(),
                size_of::<AttributeTag>(),
            ),
        ] {
            if unsafe { GetFileInformationByHandleEx(handle, class, ptr, size as u32) } == 0 {
                return Err("WINDOWS_INPUT_IDENTITY_UNAVAILABLE");
            }
        }
        if id.volume == 0
            || id.id == [0; 16]
            || tag.attributes & 0x400 != 0
            || standard.deleted != 0
            || standard.end < 0
        {
            return Err("WINDOWS_INPUT_HANDLE_REJECTED");
        }
        let directory = standard.directory != 0;
        if directory != (tag.attributes & 0x10 != 0) {
            return Err("WINDOWS_INPUT_TYPE_CONFLICT");
        }
        Ok(Info {
            identity: Identity {
                volume: id.volume,
                id: id.id,
            },
            size: standard.end as u64,
            directory,
            links: standard.links,
        })
    }
    #[cfg(test)]
    pub fn simulate_close_unknown(&mut self) {
        // Do not call CloseHandle or reuse its raw value; retain a real live
        // read-only handle while driving the same checked-failure path.
        if let Some(file) = self.file.take() {
            self.uncertain_handle = Some(file.into_raw_handle() as usize);
        }
        self.uncertain = true;
    }
    #[cfg(test)]
    pub fn held(&self) -> (bool, bool) {
        (
            self.file.is_some() || self.uncertain_handle.is_some(),
            self.uncertain_handle.is_some(),
        )
    }
    pub fn close(&mut self) -> bool {
        if self.uncertain {
            return false;
        }
        if let Some(file) = self.file.take() {
            let raw = file.into_raw_handle();
            if unsafe { CloseHandle(raw) } == 0 {
                // Never reuse a raw value after an uncertain close; the lifetime fence stays.
                self.uncertain = true;
                self.uncertain_handle = Some(raw as usize);
                return false;
            }
        }
        true
    }
}
/// Open only a native local drive root. Drive aliases necessarily use Object
/// Manager resolution; strict physical-volume classification follows on this
/// actual handle before ANY relative descent. No arbitrary absolute path API.
pub(super) fn open_drive(drive: u8, anchor: bool) -> Result<Opened, &'static str> {
    if !drive.is_ascii_alphabetic() {
        return Err("WINDOWS_INPUT_ROOT_REJECTED");
    }
    let path = format!("\\\\?\\{}:\\", drive as char);
    let wide: Vec<u16> = path.encode_utf16().chain([0]).collect();
    // OPEN_REPARSE_POINT + BACKUP_SEMANTICS, read attributes only, no inherit.
    let raw = unsafe {
        CreateFileW(
            wide.as_ptr(),
            0x100080,
            if anchor { 7 } else { 3 },
            std::ptr::null(),
            3,
            0x02200000,
            std::ptr::null_mut(),
        )
    };
    if raw.is_null() || raw as isize == -1 {
        return Err("WINDOWS_INPUT_NATIVE_OPEN_REJECTED");
    }
    Ok(Opened {
        file: Some(unsafe { File::from_raw_handle(raw) }),
        uncertain: false,
        uncertain_handle: None,
    })
}
/// Classification uses the retained handle, never a prior DOS-name probe.
pub(super) fn verify_volume_root(opened: &Opened) -> Result<(), &'static str> {
    let info = opened.info()?;
    if !info.directory {
        return Err("WINDOWS_INPUT_ROOT_REJECTED");
    }
    let handle = opened
        .file
        .as_ref()
        .ok_or("WINDOWS_INPUT_HANDLE_UNAVAILABLE")?
        .as_raw_handle();
    let mut buffer = [0u16; 128];
    let count =
        unsafe { GetFinalPathNameByHandleW(handle, buffer.as_mut_ptr(), buffer.len() as u32, 1) }
            as usize;
    if count == 0 || count >= buffer.len() {
        return Err("WINDOWS_INPUT_PHYSICAL_VOLUME_UNAVAILABLE");
    }
    let path = String::from_utf16(&buffer[..count])
        .map_err(|_| "WINDOWS_INPUT_PHYSICAL_VOLUME_UNAVAILABLE")?;
    // A mapped directory is not a physical volume root; GUID paths do not exist
    // for network shares. Never accept a suffix or lossily decoded component.
    if !path.is_ascii()
        || path.len() != 49
        || !path.starts_with("\\\\?\\Volume{")
        || !path.ends_with("}\\")
        || uuid::Uuid::parse_str(&path[11..47]).map_or(true, |id| id.is_nil())
    {
        return Err("WINDOWS_INPUT_PHYSICAL_VOLUME_REQUIRED");
    }
    let wide: Vec<u16> = path.encode_utf16().chain([0]).collect();
    if unsafe { GetDriveTypeW(wide.as_ptr()) } != 3 {
        return Err("WINDOWS_INPUT_LOCAL_FIXED_VOLUME_REQUIRED");
    }
    if opened.info()? != info {
        return Err("WINDOWS_INPUT_ROOT_CHANGED");
    }
    Ok(())
}
pub(super) fn open(
    parent: &Opened,
    name: &str,
    directory: bool,
    anchor: bool,
) -> Result<Opened, &'static str> {
    if !super::path::component(name) {
        return Err("WINDOWS_INPUT_PATH_REJECTED");
    }
    let bytes = name
        .encode_utf16()
        .count()
        .checked_mul(2)
        .ok_or("WINDOWS_INPUT_PATH_REJECTED")?;
    let length = u16::try_from(bytes).map_err(|_| "WINDOWS_INPUT_PATH_REJECTED")?;
    let mut wide: Vec<u16> = name.encode_utf16().collect();
    let mut unicode = UnicodeString {
        length,
        maximum_length: length,
        buffer: wide.as_mut_ptr(),
    };
    let root = parent
        .file
        .as_ref()
        .ok_or("WINDOWS_INPUT_HANDLE_UNAVAILABLE")?
        .as_raw_handle();
    let mut attrs = ObjectAttributes {
        length: size_of::<ObjectAttributes>() as u32,
        root,
        name: &mut unicode,
        attributes: 0x1000 | 0x40,
        security: std::ptr::null_mut(),
        quality: std::ptr::null_mut(),
    };
    let mut status = IoStatus {
        status: 0,
        information: 0,
    };
    let mut raw = std::ptr::null_mut();
    // Directories need attributes+SYNCHRONIZE only; files need read data. No inherit flag.
    let access = if directory { 0x100080 } else { 0x120089 };
    let share = if anchor {
        7
    } else if directory {
        3
    } else {
        1
    };
    let result = unsafe {
        NtCreateFile(
            &mut raw,
            access,
            &mut attrs,
            &mut status,
            std::ptr::null(),
            0,
            share,
            1,
            0x20 | if directory { 1 } else { 0x40 },
            std::ptr::null(),
            0,
        )
    };
    if result < 0 {
        return Err("WINDOWS_INPUT_NATIVE_OPEN_REJECTED");
    }
    if raw.is_null() || raw as isize == -1 {
        return Err("WINDOWS_INPUT_HANDLE_UNAVAILABLE");
    }
    // Ownership transfers once only from NtCreateFile into this File.
    Ok(Opened {
        file: Some(unsafe { File::from_raw_handle(raw) }),
        uncertain: false,
        uncertain_handle: None,
    })
}
