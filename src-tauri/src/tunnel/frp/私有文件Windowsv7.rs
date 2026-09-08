//! Windows private files are secured by CreateFileW, not by a child shell.
//! The protected, current-user-only DACL is attached before a file is visible.
use std::fs::File;
use std::mem::size_of;
use std::os::windows::ffi::OsStrExt;
use std::os::windows::io::{AsRawHandle, FromRawHandle, OwnedHandle};
use std::path::Path;
use std::ptr;

use windows::core::PCWSTR;
use windows::Win32::Foundation::HANDLE;
use windows::Win32::Security::{
    AddAccessAllowedAce, EqualSid, GetAce, GetKernelObjectSecurity, GetLengthSid,
    GetSecurityDescriptorControl, GetSecurityDescriptorDacl, GetTokenInformation,
    InitializeAcl, InitializeSecurityDescriptor, SetSecurityDescriptorControl,
    SetSecurityDescriptorDacl, SetSecurityDescriptorOwner, TokenUser, ACCESS_ALLOWED_ACE,
    ACL, ACL_REVISION, DACL_SECURITY_INFORMATION, PSECURITY_DESCRIPTOR, PSID,
    SECURITY_ATTRIBUTES, SECURITY_DESCRIPTOR, SECURITY_DESCRIPTOR_CONTROL,
    SE_DACL_PROTECTED, TOKEN_QUERY, TOKEN_USER,
};
use windows::Win32::Storage::FileSystem::{
    CreateFileW, CREATE_NEW, FILE_ALL_ACCESS, FILE_ATTRIBUTE_NORMAL,
    FILE_GENERIC_READ, FILE_GENERIC_WRITE, FILE_SHARE_DELETE, FILE_SHARE_READ,
};
use windows::Win32::System::Threading::{GetCurrentProcess, OpenProcessToken};

use crate::error::{AppError, AppResult};

fn checked<T>(stage: &str, result: windows::core::Result<T>) -> AppResult<T> {
    result.map_err(|error| AppError::Message(format!(
        "FRP配置权限保护失败（{stage}，HRESULT=0x{:08X}）；未写入凭据，旧文件已保留。",
        error.code().0 as u32,
    )))
}

fn invalid_acl() -> AppError {
    AppError::Message("FRP配置的当前用户独占ACL校验失败；未写入凭据，旧文件已保留。".into())
}

/// Pointer-aligned storage for variable-length Win32 results. Never allocate an
/// unbounded amount based on an unexpected native length.
fn buffer(bytes: u32) -> AppResult<Vec<usize>> {
    if bytes == 0 || bytes > 65_536 { return Err(invalid_acl()); }
    Ok(vec![0; (bytes as usize).div_ceil(size_of::<usize>())])
}

fn current_user() -> AppResult<Vec<usize>> {
    let mut token = HANDLE::default();
    // SAFETY: the pseudo process handle is valid and token is a writable output.
    checked("OpenProcessToken", unsafe { OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &mut token) })?;
    // SAFETY: successful OpenProcessToken transfers one owned handle to us.
    let token = unsafe { OwnedHandle::from_raw_handle(token.0) };
    let handle = HANDLE(token.as_raw_handle());
    let mut bytes = 0;
    // The first call only obtains the required buffer length.
    let _ = unsafe { GetTokenInformation(handle, TokenUser, None, 0, &mut bytes) };
    if (bytes as usize) < size_of::<TOKEN_USER>() { return Err(invalid_acl()); }
    let mut data = buffer(bytes)?;
    // SAFETY: data is pointer-aligned and contains at least bytes writable bytes.
    checked("GetTokenInformation", unsafe {
        GetTokenInformation(handle, TokenUser, Some(data.as_mut_ptr().cast()), bytes, &mut bytes)
    })?;
    Ok(data)
}

/// Returns a newly created empty file. The caller must verify its ACL before
/// writing secrets, and remove its own file if verification fails.
pub(super) fn create(path: &Path) -> AppResult<File> {
    let user = current_user()?;
    // SAFETY: current_user filled a suitably sized TOKEN_USER buffer. Its SID
    // points into that buffer, which stays alive throughout creation and check.
    let sid = unsafe { (*(user.as_ptr().cast::<TOKEN_USER>())).User.Sid };
    if sid.0.is_null() { return Err(invalid_acl()); }
    let sid_length = unsafe { GetLengthSid(sid) };
    let bytes = (size_of::<ACL>() + size_of::<ACCESS_ALLOWED_ACE>() - size_of::<u32>()) as u32 + sid_length;
    let mut acl_data = buffer(bytes)?;
    let acl = acl_data.as_mut_ptr().cast::<ACL>();
    let mut descriptor = SECURITY_DESCRIPTOR::default();
    let sd = PSECURITY_DESCRIPTOR((&mut descriptor as *mut SECURITY_DESCRIPTOR).cast());
    // SAFETY: SID, ACL and absolute security descriptor all stay allocated and
    // aligned until CreateFileW returns. The ACL contains exactly one allow ACE.
    unsafe {
        checked("InitializeAcl", InitializeAcl(acl, bytes, ACL_REVISION))?;
        checked("AddAccessAllowedAce", AddAccessAllowedAce(acl, ACL_REVISION, FILE_ALL_ACCESS.0, sid))?;
        checked("InitializeSecurityDescriptor", InitializeSecurityDescriptor(sd, 1))?;
        checked("SetSecurityDescriptorOwner", SetSecurityDescriptorOwner(sd, Some(sid), false))?;
        checked("SetSecurityDescriptorDacl", SetSecurityDescriptorDacl(sd, true, Some(acl), false))?;
        checked("SetSecurityDescriptorControl", SetSecurityDescriptorControl(sd, SE_DACL_PROTECTED, SE_DACL_PROTECTED))?;
    }
    let attributes = SECURITY_ATTRIBUTES {
        nLength: size_of::<SECURITY_ATTRIBUTES>() as u32,
        lpSecurityDescriptor: sd.0,
        bInheritHandle: false.into(),
    };
    // Canonicalizing the existing parent retains Windows' extended-length path
    // prefix and Unicode. The destination itself must not exist (CREATE_NEW).
    let parent = path.parent().filter(|p| !p.as_os_str().is_empty()).unwrap_or(Path::new("."));
    let name = path.file_name().ok_or_else(invalid_acl)?;
    let full_path = std::fs::canonicalize(parent)?.join(name);
    let mut wide: Vec<u16> = full_path.as_os_str().encode_wide().collect();
    if wide.contains(&0) { return Err(invalid_acl()); }
    wide.push(0);
    // SAFETY: wide is terminated; security buffers stay live. No handle is
    // inherited. A collision never truncates or changes an existing file.
    let handle = checked("CreateFileW", unsafe {
        CreateFileW(PCWSTR(wide.as_ptr()), FILE_GENERIC_READ.0 | FILE_GENERIC_WRITE.0,
            FILE_SHARE_READ | FILE_SHARE_DELETE, Some(&attributes), CREATE_NEW,
            FILE_ATTRIBUTE_NORMAL, None)
    })?;
    // SAFETY: this successful CreateFileW handle is uniquely owned by File.
    let file = unsafe { File::from_raw_handle(handle.0) };
    Ok(file)
}

fn verify(file: &File, sid: PSID) -> AppResult<()> {
    let handle = HANDLE(file.as_raw_handle());
    let mut bytes = 0;
    // SAFETY: read-only handle query; null output probes the required size.
    let _ = unsafe { GetKernelObjectSecurity(handle, DACL_SECURITY_INFORMATION.0, None, 0, &mut bytes) };
    let mut data = buffer(bytes)?;
    let sd = PSECURITY_DESCRIPTOR(data.as_mut_ptr().cast());
    let mut present = Default::default();
    let mut defaulted = Default::default();
    let mut control = SECURITY_DESCRIPTOR_CONTROL::default();
    let mut revision = 0;
    let mut acl = ptr::null_mut();
    // SAFETY: OS fills data and returns pointers into it; all are used only while
    // data is live. Verify protection, ACE count/type/rights and exact user SID.
    unsafe {
        checked("GetKernelObjectSecurity", GetKernelObjectSecurity(handle, DACL_SECURITY_INFORMATION.0, Some(sd), bytes, &mut bytes))?;
        checked("GetSecurityDescriptorControl", GetSecurityDescriptorControl(sd, &mut control, &mut revision))?;
        checked("GetSecurityDescriptorDacl", GetSecurityDescriptorDacl(sd, &mut present, &mut acl, &mut defaulted))?;
        if !present.as_bool() || acl.is_null() || (control.0 & SE_DACL_PROTECTED.0) == 0 || (*acl).AceCount != 1 {
            return Err(invalid_acl());
        }
        let mut ace = ptr::null_mut();
        checked("GetAce", GetAce(acl, 0, &mut ace))?;
        let allowed = &*ace.cast::<ACCESS_ALLOWED_ACE>();
        if allowed.Header.AceType != 0 || allowed.Header.AceFlags != 0 || allowed.Mask != FILE_ALL_ACCESS.0 {
            return Err(invalid_acl());
        }
        let actual_sid = PSID(ptr::addr_of!(allowed.SidStart).cast_mut().cast());
        if EqualSid(actual_sid, sid).is_err() { return Err(invalid_acl()); }
    }
    Ok(())
}

pub(super) fn verify_current_user(file: &File) -> AppResult<()> {
    let user = current_user()?;
    // SAFETY: same owned TOKEN_USER contract as create().
    let sid = unsafe { (*(user.as_ptr().cast::<TOKEN_USER>())).User.Sid };
    verify(file, sid)
}
