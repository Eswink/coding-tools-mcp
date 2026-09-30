//! Numeric-only observations inside the existing LPAC fixture. No substitutions.
use std::{
    fs,
    os::windows::io::{AsRawHandle, IntoRawHandle},
    path::Path,
};
use windows::Win32::Foundation::{CloseHandle, DuplicateHandle, DUPLICATE_SAME_ACCESS, HANDLE};
use windows::Win32::System::Threading::GetCurrentProcess;

fn win32_error(error: windows::core::Error) -> i32 {
    (error.code().0 as u32 & 0xffff) as i32
}

fn read_open_and_close(path: &Path) -> (serde_json::Value, bool) {
    match fs::File::open(path) {
        Ok(file) => {
            // Consume only this newly opened File. Do not double-close in Drop.
            let handle = HANDLE(file.into_raw_handle());
            let close_error = unsafe { CloseHandle(handle) }
                .err()
                .map(win32_error)
                .unwrap_or(0);
            (
                serde_json::json!({"open_error":0,"close_error":close_error}),
                close_error == 0,
            )
        }
        Err(error) => (
            serde_json::json!({"open_error":error.raw_os_error().unwrap_or(-1),"close_error":null}),
            true,
        ),
    }
}

fn duplicate_and_close(file: &fs::File) -> (serde_json::Value, bool) {
    let mut duplicate = HANDLE::default();
    // Match Rust's stdio duplication. The source is an already-owned private
    // output file in this LPAC process; no host handle or extra access is used.
    let result = unsafe {
        DuplicateHandle(
            GetCurrentProcess(),
            HANDLE(file.as_raw_handle()),
            GetCurrentProcess(),
            &mut duplicate,
            0,
            true,
            DUPLICATE_SAME_ACCESS,
        )
    };
    match result {
        Ok(()) => {
            let close_error = unsafe { CloseHandle(duplicate) }
                .err()
                .map(win32_error)
                .unwrap_or(0);
            (
                serde_json::json!({"duplicate_error":0,"close_error":close_error}),
                close_error == 0,
            )
        }
        Err(error) => (
            serde_json::json!({"duplicate_error":win32_error(error),"close_error":null}),
            true,
        ),
    }
}

pub fn inspect(exe: &Path, stdout: &fs::File, stderr: &fs::File) -> (serde_json::Value, bool) {
    let (executable_read, executable_closed) = read_open_and_close(exe);
    // This non-inheritable read observation is NOT identical to Rust's actual
    // inheritable NUL open. It narrows hypotheses, never locates CreateProcess.
    let (nul_read_noninheritable, nul_closed) = read_open_and_close(Path::new(r"\\.\NUL"));
    let (stdout_duplicate, stdout_closed) = duplicate_and_close(stdout);
    let (stderr_duplicate, stderr_closed) = duplicate_and_close(stderr);
    (
        serde_json::json!({"stdout_create_error":0,"stderr_create_error":0,
        "executable_read":executable_read,"nul_read_noninheritable":nul_read_noninheritable,
        "stdout_duplicate":stdout_duplicate,"stderr_duplicate":stderr_duplicate}),
        executable_closed && nul_closed && stdout_closed && stderr_closed,
    )
}
