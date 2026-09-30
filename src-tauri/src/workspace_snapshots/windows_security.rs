//! Handle-bound Windows permissions. No filesystem SetKernelObjectSecurity use.
use super::super::model::*;
use std::{fs::File, os::windows::io::AsRawHandle};
use windows::{
    core::{BOOL, PCWSTR, PWSTR},
    Win32::{
        Foundation::{CloseHandle, LocalFree, HANDLE, HLOCAL},
        Security::{Authorization::*, *},
        System::Threading::{GetCurrentProcess, OpenProcessToken},
    },
};
const INFO: OBJECT_SECURITY_INFORMATION = OBJECT_SECURITY_INFORMATION(0x1 | 0x2 | 0x4 | 0x10);
pub struct Descriptor(pub PSECURITY_DESCRIPTOR);
impl Drop for Descriptor {
    fn drop(&mut self) {
        unsafe {
            LocalFree(Some(HLOCAL(self.0 .0)));
        }
    }
}
fn fail<T>(_: T) -> SnapshotError {
    SnapshotError::Boundary
}
pub fn wide(text: &str) -> Vec<u16> {
    text.encode_utf16().chain(Some(0)).collect()
}
pub fn parse(text: &str) -> Result<Descriptor> {
    if text.len() > 16384 || text.contains('\0') {
        return Err(SnapshotError::Corrupt);
    }
    let raw = wide(text);
    let mut descriptor = PSECURITY_DESCRIPTOR::default();
    unsafe {
        ConvertStringSecurityDescriptorToSecurityDescriptorW(
            PCWSTR(raw.as_ptr()),
            1,
            &mut descriptor,
            None,
        )
    }
    .map_err(fail)?;
    let result = Descriptor(descriptor);
    dacl(&result)?;
    supported_dacl(text)?;
    Ok(result)
}
fn descriptor(file: &File) -> Result<Descriptor> {
    let mut raw = PSECURITY_DESCRIPTOR::default();
    let status = unsafe {
        GetSecurityInfo(
            HANDLE(file.as_raw_handle()),
            SE_FILE_OBJECT,
            INFO,
            None,
            None,
            None,
            None,
            Some(&mut raw),
        )
    };
    if status.0 != 0 {
        return Err(SnapshotError::Boundary);
    }
    let value = Descriptor(raw);
    dacl(&value)?;
    Ok(value)
}
fn dacl(sd: &Descriptor) -> Result<*mut ACL> {
    let mut present = BOOL(0);
    let mut defaulted = BOOL(0);
    let mut acl = std::ptr::null_mut();
    unsafe { GetSecurityDescriptorDacl(sd.0, &mut present, &mut acl, &mut defaulted) }
        .map_err(fail)?;
    if !present.as_bool() || acl.is_null() {
        return Err(SnapshotError::Unsupported);
    }
    Ok(acl)
}
fn canonical(text: String) -> Result<String> {
    if text.len() > 16384 {
        return Err(SnapshotError::Capacity);
    }
    let start = text.find("D:").ok_or(SnapshotError::Unsupported)? + 2;
    let end = text[start..]
        .find('(')
        .map(|i| start + i)
        .ok_or(SnapshotError::Unsupported)?;
    let flags = &text[start..end];
    if flags.contains("AR") {
        return Err(SnapshotError::Unsupported);
    }
    // Preserve every supported control flag exactly; do not erase AI to force equality.
    if !matches!(flags, "" | "P" | "AI" | "PAI") {
        return Err(SnapshotError::Unsupported);
    }
    Ok(text)
}
pub fn read(file: &File) -> Result<String> {
    let sd = descriptor(file)?;
    let mut ptr = PWSTR::null();
    unsafe { ConvertSecurityDescriptorToStringSecurityDescriptorW(sd.0, 1, INFO, &mut ptr, None) }
        .map_err(fail)?;
    let value = unsafe { ptr.to_string() }.map_err(fail);
    unsafe {
        LocalFree(Some(HLOCAL(ptr.0.cast())));
    }
    canonical(value?)
}
fn sid_string(sid: PSID) -> Result<String> {
    let mut ptr = PWSTR::null();
    unsafe { ConvertSidToStringSidW(sid, &mut ptr) }.map_err(fail)?;
    let value = unsafe { ptr.to_string() }.map_err(fail);
    unsafe {
        LocalFree(Some(HLOCAL(ptr.0.cast())));
    }
    value
}
fn canonical_sid(text: &str) -> Result<String> {
    let raw = wide(text);
    let mut sid = PSID::default();
    unsafe { ConvertStringSidToSidW(PCWSTR(raw.as_ptr()), &mut sid) }.map_err(fail)?;
    let value = sid_string(sid);
    unsafe {
        LocalFree(Some(HLOCAL(sid.0)));
    }
    value
}
fn token_sid(owner: bool) -> Result<String> {
    let mut token = HANDLE::default();
    unsafe { OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &mut token) }.map_err(fail)?;
    let result = (|| -> Result<String> {
        let class = if owner { TokenOwner } else { TokenUser };
        let mut size = 0;
        let _ = unsafe { GetTokenInformation(token, class, None, 0, &mut size) };
        if size == 0 || size > 65536 {
            return Err(SnapshotError::Boundary);
        }
        let mut buffer = vec![0u64; (size as usize + 7) / 8];
        unsafe {
            GetTokenInformation(
                token,
                class,
                Some(buffer.as_mut_ptr().cast()),
                size,
                &mut size,
            )
        }
        .map_err(fail)?;
        let sid = if owner {
            unsafe { (*(buffer.as_ptr().cast::<TOKEN_OWNER>())).Owner }
        } else {
            unsafe { (*(buffer.as_ptr().cast::<TOKEN_USER>())).User.Sid }
        };
        sid_string(sid)
    })();
    unsafe {
        let _ = CloseHandle(token);
    }
    result
}
pub fn private_descriptor() -> Result<Descriptor> {
    parse(&format!(
        "D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;FA;;;{})",
        token_sid(false)?
    ))
}
pub fn private(file: &File) -> Result<()> {
    let sd = descriptor(file)?;
    let mut owner = PSID::default();
    let mut defaulted = BOOL(0);
    unsafe { GetSecurityDescriptorOwner(sd.0, &mut owner, &mut defaulted) }.map_err(fail)?;
    let owner = sid_string(owner)?;
    if owner != token_sid(true)? && owner != token_sid(false)? {
        #[cfg(test)]
        eprintln!("snapshot private-directory owner is not this token's owner/user");
        return Err(SnapshotError::Boundary);
    }
    supported_dacl(&read(file)?)
}
fn supported_dacl(text: &str) -> Result<()> {
    let start = text.find("D:").ok_or(SnapshotError::Boundary)?;
    let dacl = text[start..]
        .split("S:")
        .next()
        .ok_or(SnapshotError::Boundary)?;
    let user = token_sid(false)?;
    for ace in dacl.split('(').skip(1) {
        let body = ace.split(')').next().ok_or(SnapshotError::Boundary)?;
        let fields: Vec<_> = body.split(';').collect();
        if fields.len() != 6 || !matches!(fields[0], "A" | "D") {
            return Err(SnapshotError::Unsupported);
        }
        if fields[0] == "A" {
            // SDDL may abbreviate the actual current SID (for example LA). Compare SID identity.
            let principal = canonical_sid(fields[5])?;
            if !matches!(principal.as_str(), "S-1-5-18" | "S-1-5-32-544")
                && principal != user
                && !(principal == "S-1-3-0" && fields[1].contains("IO"))
            {
                #[cfg(test)]
                eprintln!("snapshot private-directory ACL contains an unsupported allow principal");
                return Err(SnapshotError::Boundary);
            }
        }
    }
    Ok(())
}
fn immutable_parts(text: &str) -> Result<(&str, &str)> {
    let d = text.find("D:").ok_or(SnapshotError::Corrupt)?;
    let label = text.find("S:").map(|i| &text[i..]).unwrap_or("");
    Ok((&text[..d], label))
}
pub fn validate_staged(file: &File, desired: &str) -> Result<()> {
    parse(desired)?;
    if immutable_parts(&read(file)?)? != immutable_parts(desired)? {
        return Err(SnapshotError::Unsupported);
    }
    Ok(())
}
/// Caller opens MAXIMUM_ALLOWED: documented SetSecurityInfo no-child-propagation.
/// Ownership/group/integrity label are never changed and must match before mutation.
pub fn apply(file: &File, desired: &str) -> Result<()> {
    validate_staged(file, desired)?;
    // Avoid changing inheritance control flags when the exact descriptor already matches.
    if read(file)? == desired {
        return Ok(());
    }
    let sd = parse(desired)?;
    let acl = dacl(&sd)?;
    let flags = if desired.contains("D:P") {
        PROTECTED_DACL_SECURITY_INFORMATION
    } else {
        UNPROTECTED_DACL_SECURITY_INFORMATION
    };
    let status = unsafe {
        SetSecurityInfo(
            HANDLE(file.as_raw_handle()),
            SE_FILE_OBJECT,
            DACL_SECURITY_INFORMATION | flags,
            None,
            None,
            Some(acl),
            None,
        )
    };
    if status.0 != 0 {
        return Err(SnapshotError::Unavailable);
    }
    let actual = read(file)?;
    if actual != desired {
        #[cfg(test)]
        {
            let flags = |text: &str| -> String {
                text.split("D:")
                    .nth(1)
                    .unwrap_or("")
                    .split('(')
                    .next()
                    .unwrap_or("")
                    .to_owned()
            };
            eprintln!("staged descriptor readback mismatch: immutable_equal={} dacl_flags_equal={} actual_flags={} desired_flags={}",
                immutable_parts(&actual)? == immutable_parts(desired)?,
                flags(&actual) == flags(desired), flags(&actual), flags(desired));
        }
        return Err(SnapshotError::Changed);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn well_known_aliases_compare_by_sid_identity() {
        assert_eq!(canonical_sid("SY").unwrap(), "S-1-5-18");
        assert_eq!(canonical_sid("BA").unwrap(), "S-1-5-32-544");
        let user = token_sid(false).unwrap();
        assert_eq!(canonical_sid(&user).unwrap(), user);
        let descriptor = private_descriptor().unwrap();
        drop(descriptor);
    }
    #[test]
    fn broad_grant_is_refused_without_applying_acl() {
        assert!(parse("D:P(A;;FA;;;WD)").is_err());
        assert!(parse("D:P(A;;FA;;;AU)").is_err());
        assert!(parse("D:P(A;;FA;;;BU)").is_err());
    }
    #[test]
    fn null_and_pending_inheritance_descriptors_are_refused() {
        assert!(parse("D:NO_ACCESS_CONTROL").is_err());
        assert!(canonical("O:BAG:BAD:AR(A;;FA;;;BA)".into()).is_err());
    }
}
