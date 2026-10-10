//! Independent Windows execution input. Data validation cannot mint permission.
mod chunks;
mod lease;
mod nt;
mod owner;
mod path;
mod retained;
mod root;
mod transfer;
pub(crate) mod owned_run;
pub(crate) use root::WindowsInputAuthority;
pub(crate) fn check_relative(text: &str) -> Result<(), &'static str> {
    path::components(text).map(|_| ())
}
/// Build provenance only. This cannot authorize input, native VM or output.
/// A fresh CI candidate must embed the exact build SHA explicitly.
pub(crate) fn native_source() -> Result<&'static str, &'static str> {
    let source = option_env!("CTM_WINDOWS_NATIVE_SOURCE")
        .ok_or("WINDOWS_INPUT_SOURCE_UNPROVEN")?;
    if source.len() != 40 || !source.bytes().all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f')) {
        return Err("WINDOWS_INPUT_SOURCE_UNPROVEN");
    }
    Ok(source)
}
#[cfg(test)] mod chunk_tests;
#[cfg(test)] mod transfer_tests;
#[cfg(test)] mod publication_tests;
#[cfg(test)] mod tests;
