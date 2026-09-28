use crate::process_tree::ProcessTree;
use crate::pty::{PtyError, PtyErrorKind, PtySize, PtySpec};
use std::{
    collections::BTreeMap,
    ffi::{c_void, OsStr},
    fs::File,
    io::{self, Write},
    mem::size_of,
    os::windows::{
        ffi::OsStrExt,
        io::{AsRawHandle, FromRawHandle, IntoRawHandle, OwnedHandle},
    },
    path::Path,
    ptr::{null, null_mut},
};

use windows::Win32::Foundation::HANDLE;
use windows::Win32::System::Console::{COORD, HPCON};
use windows::Win32::System::Threading::{
    LPPROC_THREAD_ATTRIBUTE_LIST, PROCESS_INFORMATION, PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE,
    STARTUPINFOEXW, STARTUPINFOW_FLAGS,
};

const EXTENDED_STARTUPINFO_PRESENT: u32 = 0x0008_0000;
const CREATE_UNICODE_ENVIRONMENT: u32 = 0x0000_0400;
const CREATE_SUSPENDED: u32 = 0x0000_0004;
const STARTF_USESTDHANDLES: u32 = 0x0000_0100;
const STILL_ACTIVE: u32 = 259;

#[link(name = "kernel32")]
unsafe extern "system" {
    fn CreatePipe(
        read_pipe: *mut HANDLE,
        write_pipe: *mut HANDLE,
        attrs: *const c_void,
        size: u32,
    ) -> i32;
    fn CreatePseudoConsole(
        size: COORD,
        input: HANDLE,
        output: HANDLE,
        flags: u32,
        console: *mut HPCON,
    ) -> i32;
    fn ResizePseudoConsole(console: HPCON, size: COORD) -> i32;
    fn ClosePseudoConsole(console: HPCON);
    fn InitializeProcThreadAttributeList(
        list: *mut c_void,
        count: u32,
        flags: u32,
        bytes: *mut usize,
    ) -> i32;
    fn UpdateProcThreadAttribute(
        list: *mut c_void,
        flags: u32,
        attribute: usize,
        value: *const c_void,
        value_size: usize,
        previous: *mut c_void,
        returned: *mut usize,
    ) -> i32;
    fn DeleteProcThreadAttributeList(list: *mut c_void);
    fn CreateProcessW(
        application: *const u16,
        command_line: *mut u16,
        process_attrs: *const c_void,
        thread_attrs: *const c_void,
        inherit_handles: i32,
        creation_flags: u32,
        environment: *const c_void,
        current_directory: *const u16,
        startup: *const windows::Win32::System::Threading::STARTUPINFOW,
        process: *mut PROCESS_INFORMATION,
    ) -> i32;
    fn GetExitCodeProcess(process: HANDLE, exit_code: *mut u32) -> i32;
    fn ResumeThread(thread: HANDLE) -> u32;
    fn TerminateProcess(process: HANDLE, exit_code: u32) -> i32;
}

pub(crate) struct Spawned {
    pub(crate) reader: File,
    pub(crate) process: PlatformPty,
}

pub(crate) struct PlatformPty {
    process: OwnedHandle,
    _thread: OwnedHandle,
    tree: ProcessTree,
    writer: Option<File>,
    console: Option<PseudoConsole>,
}

struct PseudoConsole(HPCON);

impl Drop for PseudoConsole {
    fn drop(&mut self) {
        unsafe { ClosePseudoConsole(self.0) };
    }
}

struct AttributeList {
    bytes: Vec<u8>,
}

impl AttributeList {
    fn new(console: HPCON) -> io::Result<Self> {
        let mut size = 0usize;
        unsafe {
            let _ = InitializeProcThreadAttributeList(null_mut(), 1, 0, &mut size);
        }
        if size == 0 {
            return Err(io::Error::last_os_error());
        }
        let mut bytes = vec![0u8; size];
        let list = bytes.as_mut_ptr().cast::<c_void>();
        if unsafe { InitializeProcThreadAttributeList(list, 1, 0, &mut size) } == 0 {
            return Err(io::Error::last_os_error());
        }
        let value = console.0 as *const c_void;
        if unsafe {
            UpdateProcThreadAttribute(
                list,
                0,
                PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE as usize,
                value,
                size_of::<HPCON>(),
                null_mut(),
                null_mut(),
            )
        } == 0
        {
            unsafe { DeleteProcThreadAttributeList(list) };
            return Err(io::Error::last_os_error());
        }
        Ok(Self { bytes })
    }

    fn raw(&mut self) -> *mut c_void {
        self.bytes.as_mut_ptr().cast()
    }
}

impl Drop for AttributeList {
    fn drop(&mut self) {
        unsafe { DeleteProcThreadAttributeList(self.raw()) };
    }
}

pub(crate) fn spawn(spec: &PtySpec, cwd: &Path) -> Result<Spawned, PtyError> {
    let (input_read, input_write) = pipe().map_err(|_| spawn_error())?;
    let (output_read, output_write) = pipe().map_err(|_| spawn_error())?;
    let mut hpc = HPCON::default();
    let coord = coord(spec.size());
    let hr = unsafe {
        CreatePseudoConsole(
            coord,
            raw_handle(&input_read),
            raw_handle(&output_write),
            0,
            &mut hpc,
        )
    };
    if hr < 0 {
        return Err(spawn_error());
    }
    let console = PseudoConsole(hpc);
    let mut attributes = AttributeList::new(hpc).map_err(|_| spawn_error())?;
    let mut startup = STARTUPINFOEXW::default();
    startup.StartupInfo.cb = size_of::<STARTUPINFOEXW>() as u32;
    // A console parent can otherwise have its standard handles duplicated into
    // the child even with bInheritHandles=FALSE. Explicit NULL standard handles
    // let the pseudoconsole attachment install its own console handles.
    startup.StartupInfo.dwFlags |= STARTUPINFOW_FLAGS(STARTF_USESTDHANDLES);
    startup.StartupInfo.hStdInput = HANDLE::default();
    startup.StartupInfo.hStdOutput = HANDLE::default();
    startup.StartupInfo.hStdError = HANDLE::default();
    startup.lpAttributeList = LPPROC_THREAD_ATTRIBUTE_LIST(attributes.raw());

    let app = wide(OsStr::new(&spec.argv()[0]));
    let mut command = command_line(spec.argv());
    let directory = wide(cwd.as_os_str());
    let environment = environment_block(spec.env());
    let mut info = PROCESS_INFORMATION::default();
    let flags = EXTENDED_STARTUPINFO_PRESENT | CREATE_UNICODE_ENVIRONMENT | CREATE_SUSPENDED;
    if unsafe {
        CreateProcessW(
            app.as_ptr(),
            command.as_mut_ptr(),
            null(),
            null(),
            0,
            flags,
            environment.as_ptr().cast(),
            directory.as_ptr(),
            &startup.StartupInfo,
            &mut info,
        )
    } == 0
    {
        return Err(spawn_error());
    }

    let process = unsafe { OwnedHandle::from_raw_handle(info.hProcess.0) };
    let thread = unsafe { OwnedHandle::from_raw_handle(info.hThread.0) };
    let mut tree = match ProcessTree::new() {
        Ok(tree) => tree,
        Err(_) => {
            unsafe { TerminateProcess(HANDLE(process.as_raw_handle()), 1) };
            return Err(spawn_error());
        }
    };
    if tree
        .assign_process(HANDLE(process.as_raw_handle()))
        .is_err()
    {
        unsafe { TerminateProcess(HANDLE(process.as_raw_handle()), 1) };
        let _ = tree.terminate();
        return Err(spawn_error());
    }
    let resumed = unsafe { ResumeThread(HANDLE(thread.as_raw_handle())) };
    if resumed != 1 {
        unsafe { TerminateProcess(HANDLE(process.as_raw_handle()), 1) };
        let _ = tree.terminate();
        return Err(spawn_error());
    }

    drop(input_read);
    drop(output_write);
    let reader = unsafe { File::from_raw_handle(output_read.into_raw_handle()) };
    let writer = unsafe { File::from_raw_handle(input_write.into_raw_handle()) };
    Ok(Spawned {
        reader,
        process: PlatformPty {
            process,
            _thread: thread,
            tree,
            writer: Some(writer),
            console: Some(console),
        },
    })
}

impl PlatformPty {
    pub(crate) fn write(&mut self, bytes: &[u8]) -> io::Result<()> {
        self.writer
            .as_mut()
            .ok_or_else(|| io::Error::new(io::ErrorKind::BrokenPipe, "PTY input closed"))?
            .write_all(bytes)
    }

    pub(crate) fn resize(&mut self, size: PtySize) -> io::Result<()> {
        let console = self
            .console
            .as_ref()
            .ok_or_else(|| io::Error::new(io::ErrorKind::BrokenPipe, "PTY closed"))?;
        let hr = unsafe { ResizePseudoConsole(console.0, coord(size)) };
        if hr < 0 {
            Err(io::Error::last_os_error())
        } else {
            Ok(())
        }
    }

    pub(crate) fn try_wait(&mut self) -> io::Result<Option<i32>> {
        let mut code = 0u32;
        if unsafe { GetExitCodeProcess(HANDLE(self.process.as_raw_handle()), &mut code) } == 0 {
            return Err(io::Error::last_os_error());
        }
        if code == STILL_ACTIVE {
            Ok(None)
        } else {
            Ok(Some(code as i32))
        }
    }

    pub(crate) fn terminate_tree(&mut self) -> io::Result<()> {
        self.tree.terminate()
    }

    pub(crate) fn close_session(&mut self) {
        self.writer.take();
        self.console.take();
    }
}

fn pipe() -> io::Result<(OwnedHandle, OwnedHandle)> {
    let mut read = HANDLE::default();
    let mut write = HANDLE::default();
    if unsafe { CreatePipe(&mut read, &mut write, null(), 0) } == 0 {
        return Err(io::Error::last_os_error());
    }
    Ok((unsafe { OwnedHandle::from_raw_handle(read.0) }, unsafe {
        OwnedHandle::from_raw_handle(write.0)
    }))
}

fn raw_handle(handle: &OwnedHandle) -> HANDLE {
    HANDLE(handle.as_raw_handle())
}

fn coord(size: PtySize) -> COORD {
    COORD {
        X: size.columns as i16,
        Y: size.rows as i16,
    }
}

fn wide(value: &OsStr) -> Vec<u16> {
    value.encode_wide().chain(Some(0)).collect()
}

fn environment_block(env: &BTreeMap<String, String>) -> Vec<u16> {
    if env.is_empty() {
        return vec![0, 0];
    }
    let mut block = Vec::new();
    for (key, value) in env {
        block.extend(OsStr::new(&format!("{key}={value}")).encode_wide());
        block.push(0);
    }
    block.push(0);
    block
}

fn command_line(argv: &[String]) -> Vec<u16> {
    let mut value = String::new();
    for (index, arg) in argv.iter().enumerate() {
        if index != 0 {
            value.push(' ');
        }
        push_windows_arg(&mut value, arg);
    }
    OsStr::new(&value).encode_wide().chain(Some(0)).collect()
}

fn push_windows_arg(out: &mut String, arg: &str) {
    let quote = arg.is_empty() || arg.chars().any(|ch| ch == ' ' || ch == '\t' || ch == '"');
    if !quote {
        out.push_str(arg);
        return;
    }
    out.push('"');
    let mut slashes = 0usize;
    for ch in arg.chars() {
        if ch == '\\' {
            slashes += 1;
        } else if ch == '"' {
            out.extend(std::iter::repeat_n('\\', slashes * 2 + 1));
            out.push('"');
            slashes = 0;
        } else {
            out.extend(std::iter::repeat_n('\\', slashes));
            slashes = 0;
            out.push(ch);
        }
    }
    out.extend(std::iter::repeat_n('\\', slashes * 2));
    out.push('"');
}

fn spawn_error() -> PtyError {
    PtyError::new(PtyErrorKind::Spawn, "failed to spawn PTY")
}

#[cfg(test)]
mod tests {
    use super::push_windows_arg;

    #[test]
    fn windows_argument_quoting_preserves_spaces_quotes_and_trailing_backslashes() {
        let cases = [
            ("plain", "plain"),
            ("two words", "\"two words\""),
            ("a\"b", "\"a\\\"b\""),
            ("C:\\path with space\\", "\"C:\\path with space\\\\\""),
        ];
        for (input, expected) in cases {
            let mut rendered = String::new();
            push_windows_arg(&mut rendered, input);
            assert_eq!(rendered, expected, "{input:?}");
        }
    }
}
