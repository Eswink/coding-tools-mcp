//! User-mode native rename with retained destination authority and no replacement.
use super::*;
use windows::{
    Wdk::Storage::FileSystem::{
        FileRenameInformation, NtSetInformationFile, FILE_RENAME_INFORMATION,
    },
    Win32::{
        Foundation::NTSTATUS,
        System::{Threading::WaitForSingleObject, IO::IO_STATUS_BLOCK},
    },
};
#[path = "windows_rename_state.rs"]
mod completion;
const COMPLETION_WAIT_MS: u32 = 5000;
pub(super) fn move_new(from: &Dir, name: &str, to: &Dir, destination: &str) -> Result<()> {
    safe_component(name)?;
    safe_component(destination)?;
    if file_info(&from.file, true)?.dwVolumeSerialNumber
        != file_info(&to.file, true)?.dwVolumeSerialNumber
    {
        return Err(SnapshotError::Unsupported);
    }
    // No OVERLAPPED flag: this is a synchronous, DELETE-authorized source handle.
    let source = opened(&from.path.join(name), READ | 0x00010000, 1)?;
    let mut info = BY_HANDLE_FILE_INFORMATION::default();
    unsafe { GetFileInformationByHandle(HANDLE(source.as_raw_handle()), &mut info) }
        .map_err(error)?;
    let info = file_info(&source, info.dwFileAttributes & 0x10 != 0)?;
    let name: Vec<u16> = destination.encode_utf16().collect();
    let offset = std::mem::offset_of!(FILE_RENAME_INFORMATION, FileName);
    let size = std::mem::size_of::<FILE_RENAME_INFORMATION>() + (name.len() + 1) * 2;
    let mut storage = vec![0u64; size.div_ceil(8)];
    let rename = storage.as_mut_ptr().cast::<FILE_RENAME_INFORMATION>();
    let mut io = Box::<IO_STATUS_BLOCK>::default();
    io.Anonymous.Status = NTSTATUS(completion::PENDING);
    let status = unsafe {
        (*rename).Anonymous.ReplaceIfExists = false;
        (*rename).RootDirectory = HANDLE(to.file.as_raw_handle());
        (*rename).FileNameLength = (name.len() * 2) as u32;
        std::ptr::copy_nonoverlapping(
            name.as_ptr(),
            storage.as_mut_ptr().cast::<u8>().add(offset).cast::<u16>(),
            name.len(),
        );
        NtSetInformationFile(
            HANDLE(source.as_raw_handle()),
            io.as_mut(),
            rename.cast(),
            size as u32,
            FileRenameInformation,
        )
    };
    let waited = if status.0 == completion::PENDING {
        Some(unsafe { WaitForSingleObject(HANDLE(source.as_raw_handle()), COMPLETION_WAIT_MS) }.0)
    } else {
        None
    };
    let mut observed = None;
    let state = completion::classify(status.0, waited, || {
        let value = unsafe { std::ptr::read_volatile(std::ptr::addr_of!(io.Anonymous.Status)).0 };
        observed = Some(value);
        value
    });
    if state == completion::Completion::Uncertain {
        // Retain buffers and every source/destination pin on timeout, failed wait,
        // or a signaled handle whose I/O status still says pending. Never retry.
        std::mem::forget((
            io,
            storage,
            source,
            from.file.clone(),
            from.parents.clone(),
            to.file.clone(),
            to.parents.clone(),
        ));
        return Err(SnapshotError::RecoveryRequired);
    }
    if state == completion::Completion::Failed {
        #[cfg(test)]
        eprintln!(
            "snapshot native no-replace rename failed: NTSTATUS={:#x} IO_STATUS={:?}",
            status.0, observed
        );
        return Err(SnapshotError::Changed);
    }
    if identity(&file_info(&source, info.dwFileAttributes & 0x10 != 0)?) != identity(&info) {
        return Err(SnapshotError::Changed);
    }
    drop(source);
    from.sync()?;
    to.sync()
}
