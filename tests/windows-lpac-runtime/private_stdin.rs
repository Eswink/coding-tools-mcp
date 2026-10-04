//! Additive private EOF input created and opened inside LPAC only.
use std::{fs, io::Read, os::windows::io::IntoRawHandle, path::Path};
use windows::Win32::Foundation::{CloseHandle, HANDLE};

fn close(file: fs::File) -> i32 {
    unsafe { CloseHandle(HANDLE(file.into_raw_handle())) }
        .err()
        .map(|error| (error.code().0 as u32 & 0xffff) as i32)
        .unwrap_or(0)
}

pub fn prepare(workspace: &Path) -> Result<(fs::File, serde_json::Value), serde_json::Value> {
    let path = workspace.join("runtime-stdin-empty.txt");
    let writer = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&path)
        .map_err(
            |error| serde_json::json!({"created_new":false,"create_error":error.raw_os_error()}),
        )?;
    let initial_length = writer.metadata().map(|m| m.len());
    let writer_close_error = close(writer);
    if writer_close_error != 0 || initial_length.as_ref().ok() != Some(&0) {
        return Err(
            serde_json::json!({"created_new":true,"writer_close_error":writer_close_error,
            "initial_length":initial_length.as_ref().ok(),"initial_metadata_error":initial_length.err().and_then(|e| e.raw_os_error())}),
        );
    }
    let mut input = fs::File::open(&path).map_err(|error| {
        serde_json::json!({"created_new":true,
        "writer_close_error":0,"read_open_error":error.raw_os_error()})
    })?;
    let metadata = input.metadata();
    let mut byte = [0u8; 1];
    let read = input.read(&mut byte);
    let regular = metadata.as_ref().is_ok_and(|m| m.is_file());
    let length = metadata.as_ref().ok().map(|m| m.len());
    let read_count = read.as_ref().ok().copied();
    let mut receipt = serde_json::json!({"created_new":true,"writer_close_error":0,
        "opened_read_only":true,"read_open_error":0,"regular":regular,"length":length,
        "read_count":read_count,"read_error":read.err().and_then(|e| e.raw_os_error()),
        "metadata_error":metadata.err().and_then(|e| e.raw_os_error())});
    if !regular || length != Some(0) || read_count != Some(0) {
        receipt["input_close_error"] = serde_json::json!(close(input));
        return Err(receipt);
    }
    // Ownership goes directly into Stdio; only this read-only private handle is
    // duplicated by Rust for the child. No unsandboxed handle crosses LPAC.
    Ok((input, receipt))
}
